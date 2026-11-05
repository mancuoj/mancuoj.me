#!/usr/bin/env python3
"""Rebuild the self-hosted Libertinus Serif + Noto Serif SC subsets.

Run by hand when a post introduces a character outside the committed subsets,
or when an upstream font version is bumped:

    pnpm build
    pnpm fonts          # same as: python3 scripts/fonts/subset-fonts.py

This is deliberately NOT part of `pnpm build`. The script rewrites
public/fonts/*.woff2, src/styles/fonts.css and src/lib/font-preload.ts, all of
which are committed. CI runs it after building and commits the result with
`[skip ci]` when the subsets change, so a new article cannot ship with missing
glyphs; running it locally is still supported. It scans the built HTML in dist/ for the characters the
site actually renders:

  libertinus-{regular,bold,italic}-<hash>.woff2
      Latin text (ASCII, Latin-1, Latin Extended-A, typographic punctuation).
      Regular is preloaded.
  noto-serif-sc-core-<hash>.woff2
      CJK shared by non-post pages (titles, tags, 404) plus all CJK punctuation.
      Preloaded.
  noto-serif-sc-shared-<hash>.woff2
      CJK used by two or more article bodies.
  noto-serif-sc-post-<n>-<hash>.woff2
      CJK used by exactly one article body. Only that article requests it.

Every face is gated by an exact unicode-range, so an article downloads core +
shared + its own shard instead of every Chinese character on the site. File
names carry a content hash and public/_headers marks /fonts/* immutable, so
repeat visits never revalidate a font.

Code keeps the system monospace stack. Run `pnpm build` before this script so
the scan sees the current content.

Requires fonttools + brotli: `pip install -r scripts/fonts/requirements.txt`.
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

FONT_GLOBS = ("libertinus-*.woff2", "noto-serif-sc-*.woff2")


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


def strip_tags(markup: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def prose_text(markup: str) -> str:
    match = re.search(r'<div class="prose"[^>]*>', markup)
    if not match:
        return ""
    start = match.end()
    depth = 1
    index = start
    while depth and index < len(markup):
        opening = markup.find("<div", index)
        closing = markup.find("</div>", index)
        if closing == -1:
            break
        if opening != -1 and opening < closing:
            depth += 1
            index = opening + 4
        else:
            depth -= 1
            index = closing + 6
    return strip_tags(markup[start : index - 6])


def scan_content(dist: Path):
    pages = sorted(dist.rglob("*.html"))
    if not pages:
        raise SystemExit(f"error: no HTML in {dist}; run `pnpm build` first")
    counts: Counter[str] = Counter()
    pages_per_char: dict[str, int] = Counter()
    non_post_chars: set[str] = set()
    post_pages: dict[str, dict[str, set[str]]] = {}
    for page in pages:
        markup = page.read_text(encoding="utf-8")
        # UI copy injected by inline scripts (theme toggle labels) still triggers
        # a font download although it is absent from the static markup.
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
        text = strip_tags(markup)
        chars = set(text)
        counts.update(text)
        counts.update(script_cjk)
        for ch in chars | script_cjk:
            pages_per_char[ch] += 1
        is_post = "/post/" in page.as_posix()
        if not is_post:
            non_post_chars |= chars | script_cjk
        else:
            post_pages[page.as_posix()] = {
                "all": chars | script_cjk,
                "prose": set(prose_text(markup)),
            }
    return counts, pages_per_char, non_post_chars, post_pages


def compute_charsets(
    counts: Counter,
    pages_per_char: dict[str, int],
    non_post_chars: set[str],
    post_pages: dict[str, dict[str, set[str]]],
    latin_cmap: set[int],
    cjk_cmap: set[int],
):
    used = {ord(ch) for ch in counts}
    latin = {cp for block in LATIN_BLOCKS for cp in block}
    latin |= {ord(ch) for ch in CORE_PUNCTUATION}
    latin |= {cp for cp in used if cp in latin_cmap}
    latin &= latin_cmap

    is_cjk = lambda cp: cp in cjk_cmap and cp not in latin
    punct = {cp for cp in CJK_PUNCT if cp in cjk_cmap}

    core = {ord(ch) for ch in non_post_chars if is_cjk(ord(ch))}
    for page in post_pages.values():
        core |= {ord(ch) for ch in page["all"] - page["prose"] if is_cjk(ord(ch))}
    core |= punct

    body = {
        path: {ord(ch) for ch in data["prose"] if is_cjk(ord(ch))}
        for path, data in post_pages.items()
    }
    body_all = set().union(*body.values()) if body else set()
    assignable = body_all - core
    shared = {cp for cp in assignable if pages_per_char[chr(cp)] >= 2}
    per_post = {
        path: {cp for cp in chars if cp in assignable and cp not in shared}
        for path, chars in body.items()
    }
    return latin, core, shared, per_post


def subset_bytes(font: TTFont, chars: set[int], features: list[str]) -> bytes:
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

    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=sorted(chars))
    subsetter.subset(font)
    font.flavor = "woff2"
    buffer = io.BytesIO()
    font.save(buffer)
    data = buffer.getvalue()
    if data[:4] != b"wOF2":
        raise SystemExit("error: subsetter did not produce WOFF2")
    return data


def write_font(out: Path, stem: str, data: bytes) -> tuple[Path, str]:
    digest = hashlib.sha256(data).hexdigest()[:8]
    name = f"{stem}-{digest}.woff2"
    path = out / name
    path.write_bytes(data)
    return path, name


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
    parser.add_argument(
        "--preload-ts",
        type=Path,
        default=ROOT / "src" / "lib" / "font-preload.ts",
    )
    args = parser.parse_args()

    libertinus = fetch(LIBERTINUS_URL, LIBERTINUS_ZIP, LIBERTINUS_SHA256)
    noto = fetch(NOTO_URL, NOTO_TTF, NOTO_SHA256)

    with zipfile.ZipFile(libertinus) as archive:
        def read_otf(style: str) -> TTFont:
            data = archive.read(LIBERTINUS_OTF.format(style=style))
            return TTFont(io.BytesIO(data), recalcTimestamp=False)

        latin_cmap = set(read_otf("Regular").getBestCmap())
        counts, pages_per_char, non_post, post_pages = scan_content(args.dist)
        cjk_cmap = set(TTFont(noto, recalcTimestamp=False).getBestCmap())
        latin, cjk_core, cjk_shared, per_post = compute_charsets(
            counts, pages_per_char, non_post, post_pages, latin_cmap, cjk_cmap
        )

        written: list[tuple[Path, set[int]]] = []
        latin_files: dict[str, str] = {}
        for style, (stem, weight, slant) in LIBERTINUS_STYLES.items():
            data = subset_bytes(read_otf(style), latin, LATIN_FEATURES)
            path, name = write_font(args.out, stem, data)
            latin_files[stem] = name
            written.append((path, latin))

    noto_font = TTFont(noto, recalcTimestamp=False)
    noto_files: list[tuple[str, set[int], str]] = []
    for stem, chars in (
        ("noto-serif-sc-core", cjk_core),
        ("noto-serif-sc-shared", cjk_shared),
    ):
        if not chars:
            continue
        data = subset_bytes(TTFont(noto, recalcTimestamp=False), chars, CJK_FEATURES)
        path, name = write_font(args.out, stem, data)
        noto_files.append((stem, chars, name))
        written.append((path, chars))
    for page, chars in per_post.items():
        if not chars:
            continue
        number = Path(page).stem
        data = subset_bytes(TTFont(noto, recalcTimestamp=False), chars, CJK_FEATURES)
        path, name = write_font(args.out, f"noto-serif-sc-post-{number}", data)
        noto_files.append((f"noto-serif-sc-post-{number}", chars, name))
        written.append((path, chars))
    del noto_font

    # Verify cmaps and page coverage before writing any CSS.
    for path, wanted in written:
        got = set(TTFont(path).getBestCmap())
        if got != wanted:
            raise SystemExit(
                f"error: {path.name} cmap mismatch: missing "
                f"{sorted(wanted - got)[:8]} extra {sorted(got - wanted)[:8]}"
            )
    is_cjk = lambda ch: 0x3000 <= ord(ch) <= 0x303F or 0x4E00 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF
    non_post_cjk = {ord(ch) for ch in non_post if is_cjk(ch)}
    if non_post_cjk - cjk_core:
        raise SystemExit(f"error: non-post CJK missing from core: {sorted(non_post_cjk - cjk_core)[:8]}")
    for page, data in post_pages.items():
        covered = cjk_core | cjk_shared | per_post.get(page, set())
        missing = {ord(ch) for ch in data["all"] if is_cjk(ch)} - covered
        if missing:
            raise SystemExit(f"error: {page} missing CJK: {sorted(missing)[:8]}")

    # Drop fonts from previous runs, keeping only the files just written.
    expected = {path.name for path, _ in written}
    for pattern in FONT_GLOBS:
        for old in args.out.glob(pattern):
            if old.name not in expected:
                old.unlink()

    faces = [
        face_css("Libertinus Serif", slant, str(weight), latin_files[stem], latin, "104%")
        for stem, weight, slant in LIBERTINUS_STYLES.values()
    ]
    faces += [
        face_css("Noto Serif SC", "normal", "200 900", name, chars)
        for _, chars, name in noto_files
    ]
    css = (
        "/* Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        "   Rerun `pnpm build && pnpm fonts` after a post introduces a character\n"
        "   outside the committed subsets. */\n\n"
        + "\n".join(faces)
    )
    args.css.write_text(css, encoding="utf-8")

    preload = latin_files["libertinus-regular"]
    args.preload_ts.parent.mkdir(parents=True, exist_ok=True)
    args.preload_ts.write_text(
        "// Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        f'export const preloadFont = "/fonts/{preload}";\n'
        f'export const preloadCjkFont = "/fonts/{noto_files[0][2]}";\n',
        encoding="utf-8",
    )

    print(
        f"content: {sum(counts.values()):,} chars, {len(latin)} Latin + "
        f"{len(cjk_core) + len(cjk_shared) + sum(len(v) for v in per_post.values())} CJK codepoints"
    )
    for path, _ in written:
        print(describe(path))
    print(f"css: {args.css.relative_to(ROOT)}")
    print(f"preload: {args.preload_ts.relative_to(ROOT)}")

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
