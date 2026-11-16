#!/usr/bin/env python3
"""逐页校验字体切片：每个汉字都必须落在某个 @font-face 的 unicode-range 里，
且该 face 指向的 woff2 的 cmap 真的包含它。

    pnpm build
    pnpm verify:fonts

任何一项不满足都会以非零退出码结束，并列出页 / 字 / 文件。
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

try:
    from fontTools.ttLib import TTFont
except ImportError:  # pragma: no cover
    sys.exit(
        "error: 缺少 fonttools。先装依赖再跑：\n"
        "  python3 -m venv .venv-fonts && .venv-fonts/bin/pip install -r scripts/fonts/requirements.txt\n"
        "  .venv-fonts/bin/python scripts/fonts/verify-fonts.py\n"
        "（CI 里由 workflow 的 `Install font tools` 自动装好，不需要手动处理。）"
    )

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"


def load_classifier():
    spec = importlib.util.spec_from_file_location(
        "subset_fonts", Path(__file__).with_name("subset-fonts.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.classify_weights


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


def check_light_weights(css_text: str) -> list[str]:
    """全站只有 600/700 两档中文字重。出现 400/500 的普通声明，就意味着
    Libertinus regular（25.6 KB）会被重新下载——这条把那种回退变成构建失败。
    `code`/`pre` 例外：等宽字体被钉在 400，防止合成假粗体。
    """
    problems: list[str] = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_text):
        selector, body = m.group(1).strip(), m.group(2)
        if selector.startswith("@font-face") or "font-weight" not in body:
            continue
        if re.search(r"font-weight:\s*(400|500)\b", body):
            if any(tag in selector for tag in ("code", "pre", "kbd", "samp")):
                continue
            problems.append(selector[:80])
    return problems


def main() -> None:
    pages = sorted(DIST.rglob("*.html"))
    if not pages:
        sys.exit("error: dist 里没有 HTML，先跑 pnpm build")

    css_files = sorted((DIST / "_astro").glob("*.css"))
    if not css_files:
        sys.exit("error: dist/_astro 里没有 CSS，先跑 pnpm build")

    classify_weights = load_classifier()

    blocks = []
    light: list[str] = []
    for css in css_files:
        text = css.read_text(encoding="utf-8")
        blocks.extend(face_blocks(text))
        light.extend(check_light_weights(text))
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

    # 3) 全站只有 600/700：多出 400/500 的普通声明会让西文 regular 重新被下载。
    if light:
        print("✗ 构建产物里出现 400/500 字重的普通声明（会让 Libertinus regular 25.6 KB 重新下载）：")
        for sel in sorted(set(light)):
            print(f"    {sel}")
        print("    改法：把该选择器改成 600，或改用颜色分层次；code/pre 内的 400 是允许的。")
        problems += 1
    else:
        print("✓ 全站没有 400/500 的普通字重声明（code/pre 例外）")

    by_weight: dict[str, set[int]] = {}
    for b in blocks:
        by_weight.setdefault(b["weight"], set()).update(b["range"])

    covered = set().union(*cmaps) if cmaps else set()

    # 2) 逐页：按字重分别校验（400 chrome / 600 正文 / 700 标题）。
    for page in pages:
        markup = page.read_text(encoding="utf-8")
        body = re.search(r"<body.*?</body>", markup, re.S)
        markup = body.group(0) if body else markup
        markup = re.sub(r"<(script|style)\b.*?</\1>", "", markup, flags=re.S)
        weights = classify_weights(markup)
        rel = page.relative_to(DIST)
        bad = []
        total = 0
        # 独立判据：先不管字重，只看「这页所有汉字是否都在任何一份切片里」。
        # 少字这一类错，字重分类可能一起吃错，所以这条单独算一遍。
        all_cjk = {ord(ch) for chars in weights.values() for ch in chars if is_cjk(ch)}
        uncovered = sorted(all_cjk - covered)
        if uncovered:
            sample = "".join(chr(c) for c in uncovered[:12])
            bad.append(
                f"有 {len(uncovered)} 个字不在任何切片里（如「{sample}」）。"
                "如果它们在代码块里：`.prose code` 固定 400，而全站只有 600/700 中文字重——"
                "要么去掉那条 font-weight: 400，要么把中文移出代码块；否则会回落到系统宋体。"
            )
        for weight, chars in sorted(weights.items()):
            cjk = {ord(ch) for ch in chars if is_cjk(ch)}
            total += len(cjk)
            allowed = by_weight.get(str(weight), set())
            missing = sorted(cjk - allowed)
            if missing:
                sample = "".join(chr(c) for c in missing[:8])
                hint = ""
                if str(weight) == "400":
                    hint = "（400 档只有代码块用；若这些字在 <code>/<pre> 里，见上面的改法）"
                bad.append(f"{weight} 字重缺「{sample}」{hint}")
        status = "✓" if not bad else "✗"
        print(f"{status} {rel}: {total} 个汉字" + ("，" + "；".join(bad) if bad else ""))
        problems += 1 if bad else 0

    if problems:
        sys.exit(1)
    print("all pages covered")


if __name__ == "__main__":
    main()
