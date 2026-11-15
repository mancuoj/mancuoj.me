#!/usr/bin/env python3
"""逐页校验字体切片：每个汉字都必须落在某个 @font-face 的 unicode-range 里，
且该 face 指向的 woff2 的 cmap 真的包含它。

    pnpm build
    pnpm verify:fonts

任何一项不满足都会以非零退出码结束，并列出页 / 字 / 文件。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"


def is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return 0x3000 <= cp <= 0x303F or 0x4E00 <= cp <= 0x9FFF or 0xFF00 <= cp <= 0xFFEF


def parse_ranges(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part.startswith("U+"):
            continue
        if "-" in part:
            a, b = part[2:].split("-")
            out.update(range(int(a, 16), int(b, 16) + 1))
        else:
            out.add(int(part[2:], 16))
    return out


def face_blocks(css_text: str) -> list[dict]:
    blocks = []
    for m in re.finditer(r"@font-face\s*\{(.*?)\}", css_text, re.S):
        body = m.group(1)
        fam = re.search(r'font-family:\s*"([^"]+)"', body) or re.search(
            r"font-family:\s*([^;}]+)", body
        )
        if not fam or fam.group(1).strip().strip('"') != "Noto Serif SC":
            continue
        weight = re.search(r"font-weight:\s*([^;}]+)", body)
        src = re.search(r'url\(\s*"?([^")]+)"?\s*\)', body)
        rng = re.search(r"unicode-range:\s*([^;}]+)", body)
        if not (src and rng):
            continue
        blocks.append(
            {
                "weight": (weight.group(1).strip() if weight else "?"),
                "file": src.group(1),
                "range": parse_ranges(rng.group(1)),
            }
        )
    return blocks


def main() -> None:
    pages = sorted(DIST.rglob("*.html"))
    if not pages:
        sys.exit("error: dist 里没有 HTML，先跑 pnpm build")

    css_files = sorted((DIST / "_astro").glob("*.css"))
    if not css_files:
        sys.exit("error: dist/_astro 里没有 CSS，先跑 pnpm build")

    blocks = []
    for css in css_files:
        blocks.extend(face_blocks(css.read_text(encoding="utf-8")))
    if not blocks:
        sys.exit("error: 构建产物里找不到 Noto Serif SC 的 @font-face")

    # 1) 每个 face 的 unicode-range 必须和它指向的 woff2 的 cmap 完全一致。
    problems = 0
    cmaps: list[set[int]] = []
    for b in blocks:
        path = DIST / b["file"].lstrip("/")
        if not path.exists():
            print(f"✗ {b['file']} 不存在（CSS 引用了没写进 dist 的文件）")
            problems += 1
            cmaps.append(set())
            continue
        cmap = set(TTFont(path).getBestCmap())
        cmaps.append(cmap)
        if cmap != b["range"]:
            miss = sorted(b["range"] - cmap)[:6]
            extra = sorted(cmap - b["range"])[:6]
            print(f"✗ {path.name}: unicode-range 与 cmap 不一致，缺 {miss} 多 {extra}")
            problems += 1
    print(f"faces: {len(blocks)} 个，range/cmap 一致 {len(blocks) - problems}/{len(blocks)}")

    covered = set().union(*cmaps) if cmaps else set()

    # 2) 逐页：正文里每个汉字都必须被某个 face 覆盖。
    for page in pages:
        markup = page.read_text(encoding="utf-8")
        body = re.search(r"<body.*?</body>", markup, re.S)
        markup = body.group(0) if body else markup
        markup = re.sub(r"<(script|style)\b.*?</\1>", "", markup, flags=re.S)
        text = re.sub(r"<[^>]+>", "", markup)
        chars = {ch for ch in text if is_cjk(ch)}
        missing = sorted(ord(ch) for ch in chars - {chr(cp) for cp in covered})
        status = "✓" if not missing else "✗"
        rel = page.relative_to(DIST)
        print(f"{status} {rel}: {len(chars)} 个汉字" + (f"，缺 {missing[:8]}" if missing else ""))
        problems += len(missing) and 1 or 0

    if problems:
        sys.exit(1)
    print("all pages covered")


if __name__ == "__main__":
    main()
