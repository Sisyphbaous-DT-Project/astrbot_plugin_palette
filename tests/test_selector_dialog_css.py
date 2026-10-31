"""AstrBot 4.29.4 选择弹窗与滚动条规则的回归测试。

只断言稳定的行为约束（选择器是否命中、0 值是否保留底色、特异度与作用范围），
不对整段 CSS 做快照。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palette.glass import build_glass_tokens  # noqa: E402
from palette.selector_dialog_theme import build_selector_dialog_css  # noqa: E402
from palette.theme import build_theme_css  # noqa: E402

_CARD = (
    "html.astrbot-palette-active .v-overlay-container .v-dialog"
    " > .v-overlay__content > .v-card"
)
_SELECTOR_MARKERS = (".umo-selection", ".sender-selection")
_REGULAR_CARD = (
    "html.astrbot-palette-active .v-overlay-container .v-dialog"
    " .v-card:has(> .v-card-title.text-h3.pa-4.pb-0.pl-6)"
)
_WEBKIT_GUARD = "@supports not selector(::-webkit-scrollbar)"
_THIN_AREAS = (".attachments-preview", ".sent-attachments", ".source-dialog__body")


def _css(blur: int = 14, opacity: float = 0.35) -> str:
    return build_theme_css(
        {"enabled": True, "surface_opacity": opacity, "stats_card_blur": blur}
    )


def _rules(css: str) -> list[tuple[list[str], str]]:
    """把 CSS 拆成（选择器列表，规则体）；@ 规则内的规则一并展开。"""
    result = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [part.strip() for part in match.group(1).split(",")]
        selectors = [item for item in selectors if item and not item.startswith("@")]
        if selectors:
            result.append((selectors, match.group(2)))
    return result


def _card_rule(css: str, marker: str) -> str:
    """返回以指定已选区域定位的弹窗卡片规则体。"""
    bodies = [
        body
        for selectors, body in _rules(css)
        if any(
            sel.startswith(_CARD) and sel.endswith(f":has({marker})")
            for sel in selectors
        )
    ]
    if len(bodies) != 1:
        raise AssertionError(f"{marker} 卡片规则数量为 {len(bodies)}")
    return bodies[0]


def _block(css: str, head: str) -> str:
    """返回以 head 开头、按花括号配对的完整块。"""
    start = css.index(head)
    depth = 0
    for index in range(start, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[start : index + 1]
    raise ValueError(head)


def _specificity(selector: str) -> tuple[int, int, int]:
    """计算不含逗号参数的选择器特异度，:not/:has/:is 取其参数的特异度。"""
    ids = classes = types = 0
    rest = selector
    while True:
        match = re.search(r":(not|has|is)\(", rest)
        if not match:
            break
        depth, end = 0, len(rest)
        for index in range(match.end() - 1, len(rest)):
            if rest[index] == "(":
                depth += 1
            elif rest[index] == ")":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        inner = _specificity(rest[match.end() : end].lstrip("> "))
        ids, classes, types = ids + inner[0], classes + inner[1], types + inner[2]
        rest = rest[: match.start()] + rest[end + 1 :]
    ids += len(re.findall(r"#[\w-]+", rest))
    classes += len(re.findall(r"\.[\w-]+", rest))
    classes += len(re.findall(r"\[[^\]]+\]", rest))
    classes += len(re.findall(r"(?<!:):(?!:)[\w-]+", rest))
    types += len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][\w-]*)", rest))
    return ids, classes, types


class SelectorDialogTest(unittest.TestCase):
    def test_cards_use_floating_glass_at_every_strength(self) -> None:
        for blur in (0, 14, 40):
            tokens = build_glass_tokens(blur)
            css = build_selector_dialog_css(blur)
            for marker in _SELECTOR_MARKERS:
                body = _card_rule(css, marker)
                self.assertIn(
                    f"background: {tokens.floating_surface} !important;", body
                )
                self.assertIn(
                    f"border: 1px solid {tokens.floating_border} !important;", body
                )
                if blur:
                    self.assertIn(f"backdrop-filter: blur({blur}px)", body)
                else:
                    # 强度 0 仍保留可读底线，但不得输出任何模糊。
                    self.assertIn("0.78", body)
                    self.assertIn("backdrop-filter: none !important;", body)
                    self.assertNotIn("blur(", body)

    def test_rules_are_part_of_the_theme_at_every_strength(self) -> None:
        for blur in (0, 14, 40):
            css = _css(blur=blur, opacity=0.0)
            for marker in _SELECTOR_MARKERS:
                _card_rule(css, marker)
            self.assertNotIn("blur(0px)", css)

    def test_cards_beat_the_regular_dialog_tint(self) -> None:
        # 两个选择弹窗的标题与常规弹窗一致，卡片和三块分区都必须压过常规规则。
        regular = _specificity(_REGULAR_CARD)
        regular_part = _specificity(_REGULAR_CARD + " > .v-card-text")
        css = build_selector_dialog_css(14)
        selectors = [sel for sels, _ in _rules(css) for sel in sels]
        cards = [sel for sel in selectors if sel.endswith("-selection)")]
        parts = [sel for sel in selectors if re.search(r"-selection\) > ", sel)]
        self.assertEqual(len(cards), 2)
        self.assertEqual(len(parts), 6)
        for sel in cards:
            self.assertGreater(_specificity(sel), regular, sel)
        for sel in parts:
            self.assertGreater(_specificity(sel), regular_part, sel)

    def test_bands_and_inner_lists_are_transparent(self) -> None:
        css = build_selector_dialog_css(14)
        for marker in _SELECTOR_MARKERS:
            for part in (".v-card-title", ".v-card-text", ".v-card-actions", ".v-list"):
                bodies = [
                    body
                    for selectors, body in _rules(css)
                    if any(
                        sel.endswith(f":has({marker}) > {part}")
                        or sel.endswith(f":has({marker}) {part}")
                        for sel in selectors
                    )
                ]
                self.assertTrue(bodies, f"{marker} {part}")
                self.assertIn("background: transparent !important;", bodies[0])

    def test_semantic_colored_cards_are_excluded(self) -> None:
        for selectors, _ in _rules(build_selector_dialog_css(14)):
            for sel in selectors:
                self.assertIn(":not(.bg-primary)", sel)


class ScrollbarColorScopeTest(unittest.TestCase):
    def test_global_color_is_limited_to_browsers_without_webkit_scrollbars(
        self,
    ) -> None:
        css = _css()
        block = _block(css, _WEBKIT_GUARD)
        self.assertIn("html.astrbot-palette-active *", block)
        self.assertIn(
            "scrollbar-color: var(--astrbot-scrollbar-thumb) transparent", block
        )

        # 去掉火狐专用块后，只剩上游设了 thin 的区域还带颜色。
        outside = css.replace(block, "")
        colored = [sels for sels, body in _rules(outside) if "scrollbar-color" in body]
        self.assertEqual(len(colored), 1)
        self.assertEqual(
            sorted(colored[0]),
            sorted(f"html.astrbot-palette-active {area}" for area in _THIN_AREAS),
        )

    def test_webkit_scrollbar_design_is_kept(self) -> None:
        css = _css()
        widths = [
            body
            for sels, body in _rules(css)
            if "html.astrbot-palette-active *::-webkit-scrollbar" in sels
        ]
        self.assertTrue(widths)
        self.assertIn("width: 8px !important;", widths[0])
        thumbs = [
            body
            for sels, body in _rules(css)
            if "html.astrbot-palette-active *::-webkit-scrollbar-thumb" in sels
        ]
        self.assertIn("border-radius: 999px !important;", thumbs[0])

    def test_plugin_never_widens_or_thins_scrollbars(self) -> None:
        # 任何非 auto 的 scrollbar-width 都会让 Chromium 忽略 webkit 样式，
        # 插件只允许用 none 隐藏滚动条。
        for _, body in _rules(_css()):
            for value in re.findall(r"scrollbar-width:\s*([^;!]+)", body):
                self.assertEqual(value.strip(), "none")


if __name__ == "__main__":
    unittest.main()
