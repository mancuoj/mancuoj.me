#!/usr/bin/env python3
"""Rebuild the self-hosted Schibsted Grotesk subsets committed in public/fonts/.

Run by hand when a post introduces an in-font character outside ASCII, Latin-1
or Latin Extended-A (arrows, Greek, more punctuation, ...), or when the upstream
font version is bumped:

    pnpm build
    pnpm fonts          # same as: python3 scripts/fonts/subset-fonts.py

This is deliberately NOT part of `pnpm build`. The script rewrites
public/fonts/*.woff2 and src/styles/fonts.css, which are committed. It scans the
built HTML in dist/ for the characters the site actually renders, keeps the used
characters plus Latin-1 and Latin Extended-A as a safety net, and splits the font
into:

  core.woff2  ASCII + Latin-1 + core punctuation -> preloaded by BaseLayout
  ext.woff2   Latin Extended-A -> unicode-range gated

Requires fonttools + brotli (`pip install fonttools brotli`).
"""
from __future__ import annotations

import argparse
import hashlib
import html
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

# Upstream variable font, pinned so reruns are reproducible.
SOURCE_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    "cc054e5ee906ac9b9024971b64d821aa2561c582/ofl/schibstedgrotesk/SchibstedGrotesk%5Bwght%5D.ttf"
)
SOURCE_SHA256 = "6ceeadf6be8e1fd7687011c7fa38ed0edd1abe967a0b73d97caec183552e823d"
SOURCE_CACHE = ROOT / ".cache" / "fonts" / "SchibstedGrotesk[wght].ttf"

# Weights rendered by the site: 400 body, 500 font-medium/h4, 600
# font-semibold/h2/h3/strong (700 for Tailwind preflight's bolder). The wght
# axis is deliberately NOT range-limited: fontTools'
# varLib.instancer drifts this font's interpolation when an axis range is
# restricted (max 0.9 font units at wght 700, which changes antialiasing at
# 152px). The full 400-900 axis keeps rasterization bit-identical.
WGHT_RANGE = (400, 900)

# Shaping features the site needs: ccmp/locl/liga are on by default, kern/mark/
# mkmk are default positioning, tnum is switched on by `.tabular-nums` on dates.
# The previously shipped latin face had no calt, while the latin-ext face did,
# so each output keeps the feature set of the face it replaces.
# dlig/aalt/case/ordn/sups/zero/frac/numr/dnom/pnum are never enabled.
CORE_FEATURES = ["ccmp", "locl", "liga", "tnum", "kern", "mark", "mkmk"]
EXT_FEATURES = ["calt", "ccmp", "locl", "kern", "mark", "mkmk"]

# Latin-1 stays in the same face as ASCII: that is how the previously shipped
# fontsource subsets were split (latin face = U+0000-00FF, latin-ext face =
# U+0100+), and moving accented letters to a second face would stop Chrome from
# kerning them against ASCII (measured word-width drift up to 0.7px). Latin
# Extended-A is kept as a safety net in the gated file, again matching the old
# face assignment.
LATIN1 = range(0xA0, 0x100)
LATIN_EXT_A = range(0x100, 0x180)

# Typographic punctuation that belongs in the preloaded core even when the
# current content does not use it: curly quotes, en/em dash, ellipsis.
CORE_PUNCTUATION = "‘’“”–—…"

# Use the preloaded core for any extra glyph outside Latin-1/Ext-A that shows
# up on >= 2 pages, so ordinary pages never fetch the extended file.
CORE_PAGE_THRESHOLD = 2


def load_source() -> TTFont:
    if not SOURCE_CACHE.exists():
        SOURCE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {SOURCE_URL}")
        urllib.request.urlretrieve(SOURCE_URL, SOURCE_CACHE)
    digest = hashlib.sha256(SOURCE_CACHE.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise SystemExit(
            f"error: {SOURCE_CACHE} sha256 {digest} != pinned {SOURCE_SHA256}; "
            "delete the cache file if the upstream pin was bumped"
        )
    return TTFont(SOURCE_CACHE, recalcTimestamp=False)


def scan_content(dist: Path) -> tuple[Counter, dict[str, int]]:
    pages = sorted(dist.rglob("*.html"))
    if not pages:
        raise SystemExit(f"error: no HTML in {dist}; run `pnpm build` first")
    counts: Counter[str] = Counter()
    pages_per_char: dict[str, int] = Counter()
    for page in pages:
        markup = page.read_text(encoding="utf-8")
        body = re.search(r"<body.*?</body>", markup, re.S)
        markup = body.group(0) if body else markup
        markup = re.sub(r"<(script|style)\b.*?</\1>", "", markup, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", "", markup))
        counts.update(text)
        for ch in set(text):
            pages_per_char[ch] += 1
    return counts, pages_per_char


def compute_charsets(counts: Counter, pages_per_char: dict[str, int], cmap: set[int]):
    used_in_font = {ord(ch) for ch in counts if ord(ch) in cmap}
    core = set(range(0x20, 0x7F))
    core |= {cp for cp in LATIN1 if cp in cmap}
    core |= {ord(ch) for ch in CORE_PUNCTUATION if ord(ch) in cmap}
    core |= {cp for cp in used_in_font if cp not in core and pages_per_char[chr(cp)] >= CORE_PAGE_THRESHOLD}
    extended = {cp for cp in LATIN_EXT_A if cp in cmap}
    # Any remaining used glyph outside Latin-1/Ext-A must live somewhere.
    extended |= {cp for cp in used_in_font if cp not in core}
    extended -= core
    return core, extended, used_in_font


def subset_font(source: Path, chars: set[int], out: Path, features: list[str]) -> None:
    font = TTFont(source, recalcTimestamp=False)

    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = features
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.notdef_outline = True
    options.recalc_timestamp = False  # reproducible head.modified
    options.canonical_order = True
    options.layout_closure = True
    # Upstream ships zero hinting bytecode (no fpgm/cvt, no instructions), so
    # there is nothing to strip beyond the vestigial prep table.
    options.drop_tables += ["prep"]

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
    axes = ", ".join(
        f"{a.axisTag} {a.minValue:g}-{a.maxValue:g}" for a in font["fvar"].axes
    ) if "fvar" in font else "static"
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--out", type=Path, default=ROOT / "public" / "fonts")
    parser.add_argument("--css", type=Path, default=ROOT / "src" / "styles" / "fonts.css")
    args = parser.parse_args()

    upstream = load_source()
    cmap = set(upstream.getBestCmap())
    counts, pages_per_char = scan_content(args.dist)
    core, extended, used_in_font = compute_charsets(counts, pages_per_char, cmap)

    if not used_in_font:
        raise SystemExit("error: no content characters found in the font cmap")

    core_path = args.out / "schibsted-grotesk-core.woff2"
    ext_path = args.out / "schibsted-grotesk-ext.woff2"
    subset_font(SOURCE_CACHE, core, core_path, CORE_FEATURES)
    subset_font(SOURCE_CACHE, extended, ext_path, EXT_FEATURES)

    # Verify the generated files rather than trusting the subsetter.
    for path, wanted in ((core_path, core), (ext_path, extended)):
        got = set(TTFont(path).getBestCmap())
        if got != wanted:
            raise SystemExit(
                f"error: {path.name} cmap mismatch: missing "
                f"{sorted(wanted - got)[:8]} extra {sorted(got - wanted)[:8]}"
            )
        if not got:
            raise SystemExit(f"error: {path.name} is empty")
    if core & extended:
        raise SystemExit("error: core and extended ranges overlap")

    face = (
        '@font-face {{\n'
        '  font-family: "Schibsted Grotesk Variable";\n'
        '  font-style: normal;\n'
        '  font-display: swap;\n'
        '  font-weight: {wght[0]} {wght[1]};\n'
        '  src: url("/fonts/{file}") format("woff2-variations");\n'
        '  unicode-range: {ranges};\n'
        '}}\n'
    )
    css = (
        "/* Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        "   Rerun `pnpm build && python3 scripts/fonts/subset-fonts.py` after a post\n"
        "   introduces a Latin character outside the committed subsets. */\n\n"
        + "\n".join(
            face.format(wght=WGHT_RANGE, file=path.name, ranges=unicode_range(chars))
            for path, chars in ((core_path, core), (ext_path, extended))
        )
    )
    args.css.write_text(css, encoding="utf-8")

    print(f"content: {sum(counts.values()):,} chars, {len(used_in_font)} distinct in-font codepoints")
    print(describe(core_path))
    print(describe(ext_path))
    print(f"css: {args.css.relative_to(ROOT)}")

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
    uncovered = sorted(cp for cp in used_in_font if cp not in core | extended)
    if uncovered:
        raise SystemExit(f"error: in-font characters not emitted: {uncovered}")


if __name__ == "__main__":
    main()
