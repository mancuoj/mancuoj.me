#!/usr/bin/env python3
"""Rebuild the self-hosted 屏显臻宋 (Clear Han Serif) subsets.

Run by hand when a post introduces a character outside the committed subsets,
or when an upstream font version is bumped:

    pnpm build
    pnpm fonts          # same as: python3 scripts/fonts/subset-fonts.py

This is deliberately NOT part of `pnpm build`. The script rewrites
public/fonts/*.woff2, src/styles/fonts.css and src/lib/font-preload.ts, all of
which are committed. CI runs it after building and commits the result with
`[skip ci]` when the subsets change, so a new article cannot ship with missing
glyphs; running it locally is still supported. It scans the built HTML in dist/
for the characters the site actually renders:

  clear-han-latin-<hash>.woff2
      Latin text (ASCII, Latin-1, Latin Extended-A, typographic punctuation).
      Preloaded.
  clear-han-core-<hash>.woff2
      CJK shared by non-post pages (titles, tags, 404) plus all CJK punctuation.
      Preloaded.
  clear-han-shared-<hash>.woff2
      CJK used by two or more article bodies.
  clear-han-post-<n>-<hash>.woff2
      CJK used by exactly one article body. Only that article requests it.

Every face is gated by an exact unicode-range, so an article downloads core +
shared + its own shard instead of every Chinese character on the site. File
names carry a content hash and public/_headers marks /fonts/* immutable, so
repeat visits never revalidate a font.

The font ships a single Regular weight. The site uses it for everything and
never synthesizes bold (`font-synthesis: none`). Code keeps the system
monospace stack. Run `pnpm build` before this script so the scan sees the
current content.

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
from collections import Counter
from pathlib import Path

try:
    from fontTools import subset
    from fontTools.ttLib import TTFont
except ImportError:  # pragma: no cover
    sys.exit("error: missing fonttools/brotli; run: pip install fonttools brotli")

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "fonts"

# Upstream source, pinned so reruns are reproducible.
CLEAR_HAN_URL = (
    "https://raw.githubusercontent.com/airinghost/clear-han-serif-subset/"
    "main/ttf/clearhanserif.original.v1.10.ttf"
)
CLEAR_HAN_SHA256 = "9f1441ee49036fb326ffc5e78145ccf6b59fd0b71974e98f3b702042826c44b4"
CLEAR_HAN_TTF = CACHE / "ClearHanSerif.ttf"

FAMILY = "Clear Han Serif"
WEIGHT = 400

# Latin: full ASCII + Latin-1 + Latin Extended-A, plus the typographic
# punctuation the site can render. Kept as a safety net for future copy.
LATIN_BLOCKS = [range(0x20, 0x7F), range(0xA0, 0x180)]
CORE_PUNCTUATION = "‘’“”–—…·©"

# CJK punctuation and fullwidth forms are needed by every Chinese page.
CJK_PUNCT = list(range(0x3000, 0x3040)) + list(range(0xFF01, 0xFF5F))

# Clear Han keeps Source Han's shaping tables. `halt` lets text-spacing-trim
# collapse punctuation; dlig/hist are decorative and stay out of the subsets.
FONT_FEATURES = ["ccmp", "locl", "liga", "kern", "mark", "mkmk", "halt"]

FONT_GLOBS = (
    "clear-han-*.woff2",
    # Files from the previous Libertinus + Noto Serif SC setup.
    "libertinus-*.woff2",
    "noto-serif-sc-*.woff2",
)


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


def is_cjk_char(ch: str) -> bool:
    cp = ord(ch)
    return 0x3000 <= cp <= 0x303F or 0x4E00 <= cp <= 0x9FFF or 0xFF00 <= cp <= 0xFFEF


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
        # UI copy injected by inline scripts still triggers a download although
        # it is absent from the static markup.
        script_cjk = {
            ch
            for block in re.findall(r"<script\b.*?</script>", markup, re.S)
            for ch in block
            if is_cjk_char(ch)
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
        if "/post/" in page.as_posix():
            post_pages[page.as_posix()] = {
                "all": chars | script_cjk,
                "prose": set(prose_text(markup)),
            }
        else:
            non_post_chars |= chars | script_cjk
    return counts, pages_per_char, non_post_chars, post_pages


def compute_charsets(
    counts: Counter,
    pages_per_char: dict[str, int],
    non_post_chars: set[str],
    post_pages: dict[str, dict[str, set[str]]],
    cmap: set[int],
):
    used = {ord(ch) for ch in counts}
    latin = {cp for block in LATIN_BLOCKS for cp in block}
    latin |= {ord(ch) for ch in CORE_PUNCTUATION}
    latin |= {cp for cp in used if cp in cmap and not is_cjk_char(chr(cp))}
    latin &= cmap

    is_cjk = lambda cp: cp in cmap and cp not in latin
    punct = {cp for cp in CJK_PUNCT if cp in cmap}

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


def subset_bytes(font: TTFont, chars: set[int]) -> bytes:
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = FONT_FEATURES
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


def write_font(out: Path, stem: str, data: bytes) -> Path:
    digest = hashlib.sha256(data).hexdigest()[:8]
    path = out / f"{stem}-{digest}.woff2"
    path.write_bytes(data)
    return path


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
    return (
        f"{path.name}: {path.stat().st_size:,} B, cmap {len(font.getBestCmap())} cps, "
        f"glyphs {len(font.getGlyphOrder())}"
    )


def face_css(file: str, chars: set[int]) -> str:
    return (
        "@font-face {\n"
        f'  font-family: "{FAMILY}";\n'
        "  font-style: normal;\n"
        "  font-display: swap;\n"
        f"  font-weight: {WEIGHT};\n"
        f'  src: url("/fonts/{file}") format("woff2");\n'
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

    source = fetch(CLEAR_HAN_URL, CLEAR_HAN_TTF, CLEAR_HAN_SHA256)
    cmap = set(TTFont(source, recalcTimestamp=False).getBestCmap())

    counts, pages_per_char, non_post, post_pages = scan_content(args.dist)
    latin, cjk_core, cjk_shared, per_post = compute_charsets(
        counts, pages_per_char, non_post, post_pages, cmap
    )

    written: list[tuple[Path, set[int]]] = []
    files: list[tuple[str, set[int]]] = []
    for stem, chars in (
        ("clear-han-latin", latin),
        ("clear-han-core", cjk_core),
        ("clear-han-shared", cjk_shared),
    ):
        if not chars:
            continue
        data = subset_bytes(TTFont(source, recalcTimestamp=False), chars)
        path = write_font(args.out, stem, data)
        files.append((path.name, chars))
        written.append((path, chars))
    for page, chars in per_post.items():
        if not chars:
            continue
        number = Path(page).stem
        data = subset_bytes(TTFont(source, recalcTimestamp=False), chars)
        path = write_font(args.out, f"clear-han-post-{number}", data)
        files.append((path.name, chars))
        written.append((path, chars))

    # Verify cmaps and page coverage before writing any CSS.
    for path, wanted in written:
        got = set(TTFont(path).getBestCmap())
        if got != wanted:
            raise SystemExit(
                f"error: {path.name} cmap mismatch: missing "
                f"{sorted(wanted - got)[:8]} extra {sorted(got - wanted)[:8]}"
            )
    is_cjk = is_cjk_char
    non_post_cjk = {ord(ch) for ch in non_post if is_cjk(ch)}
    if non_post_cjk - cjk_core:
        raise SystemExit(f"error: non-post CJK missing from core: {sorted(non_post_cjk - cjk_core)[:8]}")
    for page, data in post_pages.items():
        covered = cjk_core | cjk_shared | per_post.get(page, set())
        missing = {ord(ch) for ch in data["all"] if is_cjk(ch)} - covered
        if missing:
            raise SystemExit(f"error: {page} missing CJK: {sorted(missing)[:8]}")

    # Same family + weight faces must not overlap: the browser downloads every
    # face whose range hits, and overlap only adds requests.
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            common = files[i][1] & files[j][1]
            if common:
                raise SystemExit(
                    f"error: {FAMILY} {WEIGHT} 的 unicode-range 重叠："
                    f"{files[i][0]} ∩ {files[j][0]} = {sorted(common)[:8]}"
                )

    # Drop fonts from previous runs, keeping only the files just written.
    expected = {path.name for path, _ in written}
    for pattern in FONT_GLOBS:
        for old in args.out.glob(pattern):
            if old.name not in expected:
                old.unlink()

    css = (
        "/* Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        "   Rerun `pnpm build && pnpm fonts` after a post introduces a character\n"
        "   outside the committed subsets. */\n\n"
        + "\n".join(face_css(name, chars) for name, chars in files)
    )
    args.css.write_text(css, encoding="utf-8")

    latin_file = next(name for name, chars in files if chars == latin)
    core_file = next(name for name, chars in files if chars == cjk_core)
    args.preload_ts.parent.mkdir(parents=True, exist_ok=True)
    args.preload_ts.write_text(
        "// Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        f'export const preloadFont = "/fonts/{latin_file}";\n'
        f'export const preloadCjkFont = "/fonts/{core_file}";\n',
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

    fallback = sorted(cp for cp in map(ord, counts) if cp > 0x7F and cp not in cmap)
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
