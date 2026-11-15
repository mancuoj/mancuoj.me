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
      Semibold is preloaded (article body is font-weight: 600).
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
    "Semibold": ("libertinus-semibold", 600, "normal"),
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



def classify_weights(markup: str) -> dict[int, set[str]]:
    """按实际渲染字重给字符分类：400 辅助信息、600 正文、700 标题与加粗。

    规则和 CSS 对齐：h1 是 font-semibold(600)，h2–h6 与 strong/b 是 700，
    `.prose` 正文是 600，其余站点 chrome（导航、日期、标签）是 400。
    """
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.stack: list[tuple[str, int | None]] = []  # (tag, weight)
            self.prose_depth = 0
            self.out: dict[int, set[str]] = {400: set(), 600: set(), 700: set()}

        def handle_starttag(self, tag, attrs):
            cls = dict(attrs).get("class") or ""
            is_prose = tag == "div" and "prose" in cls.split()
            if is_prose:
                self.prose_depth += 1
            weight = None
            if tag == "h1":
                weight = 600
            elif tag in ("h2", "h3", "h4", "h5", "h6", "strong", "b"):
                weight = 700
            elif self.prose_depth or is_prose:
                weight = 600
            else:
                weight = 400
            self.stack.append((tag, weight))
            if is_prose:
                self.stack[-1] = (tag, 600)

        def handle_endtag(self, tag):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    if tag == "div" and self.prose_depth:
                        self.prose_depth -= 1
                    del self.stack[i:]
                    break

        def handle_data(self, data):
            weight = self.stack[-1][1] if self.stack else 400
            for ch in data:
                self.out[weight].add(ch)

    parser = P()
    parser.feed(markup)
    return parser.out

def scan_content(dist: Path):
    pages = sorted(dist.rglob("*.html"))
    if not pages:
        raise SystemExit(f"error: no HTML in {dist}; run `pnpm build` first")
    counts: Counter[str] = Counter()
    head_chars: set[str] = set()
    per_page_weights: dict[str, dict[int, set[str]]] = {}
    chars_600: set[str] = set()
    chars_400: set[str] = set()
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
        # 700 档只服务标题与加粗：把渲染成 700 的元素里的字单独收集。
        for tag in ("h2", "h3", "h4", "h5", "h6", "strong", "b"):
            for inner in re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}>", markup, re.S):
                head_chars.update(strip_tags(inner))
        weights = classify_weights(markup)
        per_page_weights[page.as_posix()] = weights
        chars_600 |= weights[600]
        chars_400 |= weights[400]
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
    return (
        counts,
        head_chars,
        chars_600,
        chars_400,
        per_page_weights,
        pages_per_char,
        non_post_chars,
        post_pages,
    )


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


def static_weight(data: bytes, wght: int) -> bytes:
    """把可变字重的子集实例化成单一静态字重，体积通常能砍掉近一半。"""
    from fontTools.varLib import instancer

    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    if "fvar" not in font:
        return data
    static = instancer.instantiateVariableFont(font, {"wght": wght}, inplace=False)
    static.flavor = "woff2"
    buffer = io.BytesIO()
    static.save(buffer)
    return buffer.getvalue()


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
        (
            counts,
            head_chars,
            chars_600,
            chars_400,
            per_page_weights,
            pages_per_char,
            non_post,
            post_pages,
        ) = scan_content(args.dist)
        cjk_cmap = set(TTFont(noto, recalcTimestamp=False).getBestCmap())
        latin, cjk_core, cjk_shared, per_post = compute_charsets(
            counts, pages_per_char, non_post, post_pages, latin_cmap, cjk_cmap
        )

        # 600 档要覆盖所有 600 用字（正文 + 文章页 h1 标题）；core 每页都加载，
        # 收口在这里最省事，通常只有几个字。
        extra600 = {ord(ch) for ch in chars_600 if is_cjk_char(ch)} - (
            cjk_core | cjk_shared | (set().union(*per_post.values()) if per_post else set())
        )
        cjk_core |= extra600

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
        data = static_weight(subset_bytes(TTFont(noto, recalcTimestamp=False), chars, CJK_FEATURES), 600)
        path, name = write_font(args.out, stem, data)
        noto_files.append((stem, chars, name, "600"))
        written.append((path, chars))
    for page, chars in per_post.items():
        if not chars:
            continue
        number = Path(page).stem
        data = static_weight(subset_bytes(TTFont(noto, recalcTimestamp=False), chars, CJK_FEATURES), 600)
        path, name = write_font(args.out, f"noto-serif-sc-post-{number}", data)
        noto_files.append((f"noto-serif-sc-post-{number}", chars, name, "600"))
        written.append((path, chars))

    # 标题与加粗是 700，单独一份静态 700 的小子集，避免为它保留整条可变轴。
    is_cjk_ch = lambda ch: 0x3000 <= ord(ch) <= 0x303F or 0x4E00 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF
    bold_chars = {ord(ch) for ch in head_chars if is_cjk_ch(ch)} & set(TTFont(noto).getBestCmap())
    if bold_chars:
        data = static_weight(subset_bytes(TTFont(noto, recalcTimestamp=False), bold_chars, CJK_FEATURES), 700)
        path, name = write_font(args.out, "noto-serif-sc-bold", data)
        noto_files.append(("noto-serif-sc-bold", bold_chars, name, "700"))
        written.append((path, bold_chars))
    del noto_font

    # 站点 chrome（导航、日期、标签名）是 400，单独一份静态 400 小子集。
    noto_cmap = set(TTFont(noto).getBestCmap())
    chrome_chars = {ord(ch) for ch in chars_400 if is_cjk_char(ch)} & noto_cmap
    if chrome_chars:
        data = static_weight(
            subset_bytes(TTFont(noto, recalcTimestamp=False), chrome_chars, CJK_FEATURES), 400
        )
        path, name = write_font(args.out, "noto-serif-sc-chrome", data)
        noto_files.append(("noto-serif-sc-chrome", chrome_chars, name, "400"))
        written.append((path, chrome_chars))

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
    if bold_chars:
        missing_bold = {ord(ch) for ch in head_chars if is_cjk(ch)} - (cjk_core | cjk_shared | bold_chars)
        if missing_bold:
            raise SystemExit(f"error: 700 标题用字缺失: {sorted(missing_bold)[:8]}")
    if chrome_chars:
        missing_chrome = {ord(ch) for ch in chars_400 if is_cjk(ch)} - chrome_chars
        if missing_chrome:
            raise SystemExit(f"error: 400 chrome 用字缺失: {sorted(missing_chrome)[:8]}")
    for page, data in post_pages.items():
        covered = cjk_core | cjk_shared | per_post.get(page, set()) | bold_chars | chrome_chars
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
        face_css("Noto Serif SC", "normal", weight, name, chars)
        for _, chars, name, weight in noto_files
    ]
    css = (
        "/* Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        "   Rerun `pnpm build && pnpm fonts` after a post introduces a character\n"
        "   outside the committed subsets. */\n\n"
        + "\n".join(faces)
    )
    args.css.write_text(css, encoding="utf-8")

    preload = latin_files["libertinus-semibold"]
    body = latin_files["libertinus-semibold"]
    site = latin_files["libertinus-regular"]
    args.preload_ts.parent.mkdir(parents=True, exist_ok=True)
    args.preload_ts.write_text(
        "// Generated by scripts/fonts/subset-fonts.py. Do not edit by hand.\n"
        f'export const preloadFont = "/fonts/{site}";\n'
        f'export const preloadBodyFont = "/fonts/{body}";\n'
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
