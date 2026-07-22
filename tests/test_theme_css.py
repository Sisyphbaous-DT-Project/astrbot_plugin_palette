"""`palette.theme.build_theme_css` 的行为回归测试。

只断言稳定的行为约束（选择器是否命中、0 值是否真正关闭等），
不对整段 CSS 文本做快照。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palette.theme import build_theme_css  # noqa: E402


def _css(config: dict | None = None) -> str:
    return build_theme_css(config or {})


def _rules_bodies(css: str, selector_suffix: str) -> list[str]:
    """返回所有存在某个选择器以 `selector_suffix` 结尾的规则体。"""
    bodies = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors, body = match.group(1), match.group(2)
        if any(part.strip().endswith(selector_suffix) for part in selectors.split(",")):
            bodies.append(body)
    return bodies


def _media_block(css: str, media_query: str) -> str:
    """按大括号配平提取整个媒体查询块。"""
    start = css.index(media_query)
    depth = 0
    for index in range(start, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[start : index + 1]
    return css[start:]


class StatsCardBlurTest(unittest.TestCase):
    def test_blur_default_value_renders(self) -> None:
        self.assertIn("blur(14px) saturate(1.08)", _css({"stats_card_blur": 14}))

    def test_blur_max_value_renders(self) -> None:
        self.assertIn("blur(40px) saturate(1.08)", _css({"stats_card_blur": 40}))

    def test_blur_zero_outputs_none_instead_of_blur_zero(self) -> None:
        css = _css({"stats_card_blur": 0})
        self.assertNotIn("blur(0px)", css)
        self.assertIn("backdrop-filter: none !important;", css)
        self.assertIn("-webkit-backdrop-filter: none !important;", css)

    def test_blur_zero_removes_card_glass_decoration(self) -> None:
        css = _css({"stats_card_blur": 0})
        card_bodies = _rules_bodies(css, ".v-card.plugin-card")
        glass_bodies = _rules_bodies(css, ".v-card.plugin-card::before")
        hover_bodies = _rules_bodies(css, ".plugin-card:hover")

        self.assertTrue(
            any(
                "border: 1px solid transparent !important;" in body
                and "box-shadow: none !important;" in body
                for body in card_bodies
            )
        )
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                for body in glass_bodies
            )
        )
        self.assertTrue(
            any(
                "box-shadow: none !important;" in body
                and "transform: none;" in body
                for body in hover_bodies
            )
        )

    def test_blur_zero_removes_config_and_overview_decoration(self) -> None:
        css = _css({"stats_card_blur": 0})
        panel_bodies = _rules_bodies(css, ".config-panel")
        section_bodies = _rules_bodies(css, ".config-panel .config-section")
        overview_bodies = _rules_bodies(css, ".stats-page .overview-card::before")

        self.assertTrue(
            any(
                "border: 1px solid transparent !important;" in body
                and "box-shadow: none !important;" in body
                for body in panel_bodies
            )
        )
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "border: 1px solid transparent !important;" in body
                and "box-shadow: none !important;" in body
                for body in section_bodies
            )
        )
        self.assertTrue(any("background: none;" in body for body in overview_bodies))

    def test_blur_zero_removes_markdown_dialog_decoration(self) -> None:
        css = _css({"stats_card_blur": 0})
        bodies = _rules_bodies(css, '.v-card:has([class*="markdown"])')
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "border-color: transparent !important;" in body
                and "box-shadow: none !important;" in body
                for body in bodies
            )
        )

    def test_settings_preview_disables_full_card_glass_at_zero(self) -> None:
        root = Path(__file__).resolve().parent.parent
        script = (root / "pages/settings/app.js").read_text(encoding="utf-8")
        style = (root / "pages/settings/style.css").read_text(encoding="utf-8")

        self.assertIn(
            'classList.toggle("is-card-glass-disabled", statsCardBlur <= 0)',
            script,
        )
        self.assertRegex(
            style,
            r"\.is-card-glass-disabled\s+\.sample-card\s*\{[^}]*"
            r"background:\s*transparent;[^}]*border-color:\s*transparent;[^}]*"
            r"box-shadow:\s*none;",
        )


class ConfigPanelSafetyTest(unittest.TestCase):
    def test_config_panel_itself_has_no_containing_block_props(self) -> None:
        bodies = _rules_bodies(_css(), ".config-panel")
        self.assertTrue(bodies, "未找到直接命中 .config-panel 的规则")
        forbidden = [
            r"backdrop-filter\s*:\s*(?!none\b)[^\s;]",
            r"(?<![-\w])filter\s*:",
            r"(?<![-\w])transform\s*:",
            r"(?<![-\w])perspective\s*:",
            r"(?<![-\w])contain\s*:",
            r"(?<![-\w])will-change\s*:",
            r"overflow\s*:\s*hidden",
        ]
        for body in bodies:
            for pattern in forbidden:
                self.assertIsNone(
                    re.search(pattern, body),
                    f".config-panel 规则不允许出现 {pattern}: {body}",
                )

    def test_config_panel_pseudo_element_carries_blur_by_default(self) -> None:
        bodies = _rules_bodies(_css(), ".config-panel::before")
        self.assertTrue(bodies, "未找到 .config-panel::before 玻璃层规则")
        self.assertTrue(any("blur(14px)" in body for body in bodies))


class PluginDetailSelectorTest(unittest.TestCase):
    def test_detail_page_selectors_exist(self) -> None:
        css = _css()
        self.assertIn(".plugin-detail-page .plugin-summary-card", css)
        self.assertIn(".plugin-detail-page .handler-card", css)
        self.assertIn(".plugin-detail-page .docs-card", css)

    def test_unreachable_extension_page_selectors_removed(self) -> None:
        css = _css()
        self.assertNotIn(".extension-page .plugin-summary-card", css)
        self.assertNotIn(".extension-page .handler-card", css)


class ReducedMotionTest(unittest.TestCase):
    def test_reduced_motion_disables_new_transition_and_transform(self) -> None:
        css = _css()
        self.assertIn("prefers-reduced-motion: reduce", css)
        block = _media_block(css, "@media (prefers-reduced-motion: reduce)")
        self.assertIn("transition: none !important;", block)
        self.assertIn("transform: none !important;", block)


class CssIntegrityTest(unittest.TestCase):
    def test_braces_are_balanced(self) -> None:
        for config in ({}, {"stats_card_blur": 0}, {"stats_card_blur": 40}):
            css = _css(config)
            self.assertEqual(css.count("{"), css.count("}"))


if __name__ == "__main__":
    unittest.main()
