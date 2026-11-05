#!/usr/bin/env python3
"""Rebuild the self-hosted Libertinus Serif + Noto Serif SC subsets.

Run by hand when a post introduces a character outside the committed subsets,
or when an upstream font version is bumped:

    pnpm build
    pnpm fonts          # same as: python3 scripts/fonts/subset-fonts.py

This is deliberately NOT part of `pnpm build`. The script rewrites
public/fonts/*.woff2 and src/styles/fonts.css, which are committed. It scans the
built HTML in dist/ for the characters the site actually renders:

  libertinus-{regular,bold,italic}.woff2
      Latin text (ASCII, Latin-1, Latin Extended-A, typographic punctuation).
      Replaces the old Schibsted Grotesk faces; regular is preloaded.
  noto-serif-sc-core.woff2
      CJK characters used by non-post pages (titles, tags, 404) plus CJK
      punctuation. Variable wght 200-900, gated by unicode-range.
  noto-serif-sc-ext.woff2
      Remaining CJK characters used in posts. Only article pages request it.

No web font is added for code: code keeps the system monospace stack.

Requires fonttools + brotli (`pip install fonttools brotli`).
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import re
import sys
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

try:
    from fontTools import subset
    from fontTools.ttLib import TTFont
except ImportError:  # pragma: no cover
    sys.exit("error: missing fonttools/brotli; run: pip install fonttools brotli")

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "fonts"

# Upstream sources, pinned so reruns are reproducible.
LIBERTINUS_URL = (
    "https://github.com/alerque/libertinus/releases/download/v7.051/Libertinus-7.051.zip"
)
LIBERTINUS_SHA256 = "4d9be29b5cb380c35af8ba967abcc752ad1e07be1f738a9789c33e0dd7478c92"
LIBERTINUS_ZIP = CACHE / "Libertinus-7.051.zip"
LIBERTINUS_OTF = "Libertinus-7.051/static/OTF/LibertinusSerif-{style}.otf"
LIBERTINUS_STYLES = {
    "Regular": ("libertinus-regular", 400, "normal"),
    "Bold": ("libertinus-bold", 700, "normal"),
    "Italic": ("libertinus-italic", 400, "italic"),
}

NOTO_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    "2e61f4355afd22b801791b0df176065082423b87/ofl/notoserifsc/NotoSerifSC%5Bwght%5D.ttf"
)
NOTO_SHA256 = "050080d9255a86808f2945bffac582b31ef32bc36411ce29563b4961670c66f9"
NOTO_TTF = CACHE / "NotoSerifSC[wght].ttf"

# Latin: full ASCII + Latin-1 + Latin Extended-A, plus the typographic
# punctuation the site can render. Kept as a safety net for future copy.
LATIN_BLOCKS = [range(0x20, 0x7F), range(0xA0, 0x180)]
CORE_PUNCTUATION = "‘’“”–—…·©"

# CJK punctuation and fullwidth forms are needed by every Chinese page.
CJK_PUNCT = list(range(0x3000, 0x3040)) + list(range(0xFF01, 0xFF5F))

# Default shaping features; tnum is used by .tabular-nums on dates. Libertinus
# only ships GPOS kern/mark/mkmk. Noto keeps halt/chws so text-spacing-trim works.
LATIN_FEATURES = ["kern", "mark", "mkmk"]
CJK_FEATURES = ["ccmp", "locl", "kern", "mark", "mkmk", "chws", "halt"]


def fetch(url: str, path: Path, sha256: str) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {url}")
        urllib.request.urlretrieve(url, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != sha256:
        raise SystemExit(
            f"error: {path.name} sha256 {digest} != pinned {sha256}; "
            "delete the cached file if the upstream pin was bumped"
        )
    return path


def scan_content(dist: Path) -> tuple[Counter, dict[str, int], set[str]]:
    pages = sorted(dist.rglob("*.html"))
    if not pages:
        raise SystemExit(f"error: no HTML in {dist}; run `pnpm build` first")
    counts: Counter[str] = Counter()
    pages_per_char: dict[str, int] = Counter()
    non_post_chars: set[str] = set()
    for page in pages:
        markup = page.read_text(encoding="utf-8")
        # UI copy can be injected by inline scripts (e.g. the theme toggle's
        # "切换到深色" aria-label), so its CJK characters still trigger a font
        # download even though they never appear in the static markup.
        script_cjk = {
            ch
            for block in re.findall(r"<script\b.*?</script>", markup, re.S)
            for ch in block
            if 0x3000 <= ord(ch) <= 0x303F
            or 0x4E00 <= ord(ch) <= 0x9FFF
            or 0xFF00 <= ord(ch) <= 0xFFEF
        }
        body = re.search(r"<body.*?</body>", markup, re.S)
        markup = body.group(0) if body else markup
        markup = re.sub(r"<(script|style)\b.*?</\1>", "", markup, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", "", markup))
        counts.update(text)
        counts.update(script_cjk)
        for ch in set(text) | script_cjk:
            pages_per_char[ch] += 1
        if "/post/" not in page.as_posix():
            non_post_chars |= set(text) | script_cjk
    return counts, pages_per_char, non_post_chars


def compute_charsets(
    counts: Counter,
    pages_per_char: dict[str, int],
    non_post_chars: set[str],
    latin_cmap: set[int],
    cjk_cmap: set[int],
):
    used = {ord(ch) for ch in counts}
    latin = {cp for block in LATIN_BLOCKS for cp in block}
    latin |= {ord(ch) for ch in CORE_PUNCTUATION}
    latin |= {cp for cp in used if cp in latin_cmap}
    latin &= latin_cmap

    used_cjk = {cp for cp in used if cp in cjk_cmap and cp not in latin}
    punct = {cp for cp in CJK_PUNCT if cp in cjk_cmap}
    core = {cp for cp in used_cjk if chr(cp) in non_post_chars} | punct
    ext = used_cjk - core
    return latin, core, ext


def subset_font(
    font: TTFont,
    chars: set[int],
    out: Path,
    features: list[str],
    *,
    drop_tables: list[str] | None = None,
) -> None:
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = features
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.notdef_outline = True
    options.recalc_timestamp = False
    options.canonical_order = True
    options.layout_closure = True
    if drop_tables:
        options.drop_tables += drop_tables

    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=sorted(chars))
    subsetter.subset(font)
    font.flavor = "woff2"  # Options.flavor alone does not affect TTFont.save()
    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(out)
    if out.read_bytes()[:4] != b"wOF2":
        raise SystemExit(f"error: {out} is not a WOFF2 file")


def unicode_range(codepoints: set[int]) -> str:
    cps = sorted(codepoints)
    parts: list[str] = []
    start = prev = cps[0]
    for cp in cps[1:]:
        if cp == prev + 1:
            prev = cp
            continue
        parts.append(f"U+{start:04X}" if start == prev else f"U+{start:04X}-{prev:04X}")
        start = prev = cp
    parts.append(f"U+{start:04X}" if start == prev else f"U+{start:04X}-{prev:04X}")
    return ",".join(parts)


def describe(path: Path) -> str:
    font = TTFont(path)
    size = path.stat().st_size
    axes = (
        ", ".join(f"{a.axisTag} {a.minValue:g}-{a.maxValue:g}" for a in font["fvar"].axes)
        if "fvar" in font
        else "static"
    )
    features = sorted(
        {
            r.FeatureTag
            for table in ("GSUB", "GPOS")
            if table in font
            for r in font[table].table.FeatureList.FeatureRecord
        }
    )
    return (
        f"{path.name}: {size:,} B, cmap {len(font.getBestCmap())} cps, "
        f"glyphs {len(font.getGlyphOrder())}, axes [{axes}], features {features}"
    )


def face_css(
    family: str,
    style: str,
    weight: str,
    file: str,
    chars: set[int],
    size_adjust: str | None = None,
) -> str:
    adjust = f"  size-adjust: {size_adjust};\n" if size_adjust else ""
    return (
        "@font-face {\n"
        f'  font-family: "{family}";\n'
        f"  font-style: {style};\n"
        "  font-display: swap;\n"
        f"  font-weight: {weight};\n"
        f'  src: url("/fonts/{file}") format("woff2");\n'
        f"{adjust}"
        f"  unicode-range: {unicode_range(chars)};\n"
        "}\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--out", type=Path, default=ROOT / "public" / "fonts")
    parser.add_argument("--css", type=Path, default=ROOT / "src" / "styles" / "fonts.css")
    args = parser.parse_args()

    libertinus = fetch(LIBERTINUS_URL, LIBERTINUS_ZIP, LIBERTINUS_SHA256)
    noto = fetch(NOTO_URL, NOTO_TTF, NOTO_SHA256)

    with zipfile.ZipFile(libertinus) as archive:
        def read_otf(style: str) -> TTFont:
            data = archive.read(LIBERTINUS_OTF.format(style=style))
            return TTFont(io.BytesIO(data), recalcTimestamp=False)

        latin_cmap = set(read_otf("Regular").getBestCmap())
        counts, pages_per_char, non_post = scan_content(args.dist)
        cjk_cmap = set(TTFont(noto, recalcTimestamp=False).getBestCmap())
        latin, cjk_core, cjk_ext = compute_charsets(
            counts, pages_per_char, non_post, latin_cmap, cjk_cmap
        )

        written: list[tuple[Path, set[int]]] = []
        for style, (name, weight, slant) in LIBERTINUS_STYLES.items():
            path = args.out / f"{name}.woff2"
            subset_font(read_otf(style), latin, path, LATIN_FEATURES)
            written.append((path, latin))

    noto_font = TTFont(noto, recalcTimestamp=False)
    for name, chars in (("noto-serif-sc-core", cjk_core), ("noto-serif-sc-ext", cjk_ext)):
        path = args.out / f"{name}.woff2"
        subset_font(TTFont(noto, recalcTimestamp=False), chars, path, CJK_FEATURES)
        written.append((path, chars))
    del noto_font

    # Verify the generated files rather than trusting the subsetter.
    for path, wanted in written:
        got = set(TTFont(path).getBestCmap())
        if got != wanted:
            raise SystemExit(
                f"error: {path.name} cmap mismatch: missing "
                f"{sorted(wanted - got)[:8]} extra {sorted(got - wanted)[:8]}"
            )
        if not got:
            raise SystemExit(f"error: {path.name} is empty")
    if cjk_core & cjk_ext:
        raise SystemExit("error: CJK core and ext ranges overlap")

    faces = [
        face_css("Libertinus Serif", slant, str(weight), f"{name}.woff2", latin, "104%")
        for name, weight, slant in LIBERTINUS_STYLES.values()
    ]
    faces.append(
        face_css("Noto Serif SC", "normal", "200 900", "noto-serif-sc-core.woff2", cjk_core)
    )
    faces.append(
        face_css("Noto Serif SC", "normal", "200 900", "noto-serif-sc-ext.woff2", cjk_ext)
    )
    css = (
        "/* Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        "   Rerun `pnpm build && pnpm fonts` after a post introduces a character\n"
        "   outside the committed subsets. */\n\n"
        + "\n".join(faces)
    )
    args.css.write_text(css, encoding="utf-8")

    print(f"content: {sum(counts.values()):,} chars, {len(latin)} Latin + "
          f"{len(cjk_core) + len(cjk_ext)} CJK codepoints")
    for path, _ in written:
        print(describe(path))
    print(f"css: {args.css.relative_to(ROOT)}")

    fallback = sorted(cp for cp in map(ord, counts) if cp > 0x7F and cp not in latin_cmap | cjk_cmap)
    if fallback:
        blocks = Counter()
        for cp in fallback:
            if 0x4E00 <= cp <= 0x9FFF:
                blocks["CJK"] += 1
            elif 0x3000 <= cp <= 0x303F:
                blocks["CJK punctuation"] += 1
            elif 0xFF00 <= cp <= 0xFFEF:
                blocks["fullwidth forms"] += 1
            else:
                blocks[unicodedata.name(chr(cp), f"U+{cp:04X}")] += 1
        print(f"system fallback (no glyph upstream): {dict(blocks)}")


if __name__ == "__main__":
    main()
