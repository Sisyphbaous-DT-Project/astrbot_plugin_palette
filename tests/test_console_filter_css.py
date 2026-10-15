"""控制台页过滤器侧栏玻璃规则的回归测试。

只断言稳定的行为约束（桌面透明、窄屏浮层可读、全屏不接管、0 值真正关闭模糊等），
不对整段 CSS 做快照。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palette.console_theme import build_console_css  # noqa: E402
from palette.theme import build_theme_css  # noqa: E402

_PANEL = ".console-filter-panel"
# 侧栏的位置、尺寸与滚动属于上游布局（窄屏下绝对定位成浮层），不能接管。
_GEOMETRY = (
    "position",
    "top:",
    "bottom:",
    "left:",
    "right:",
    "width",
    "height",
    "z-index",
    "overflow",
    "padding",
    "margin",
    "flex",
    "display",
    "border-radius",
)


def _css(blur: int = 14, opacity: float = 0.35) -> str:
    return build_theme_css({"surface_opacity": opacity, "stats_card_blur": blur})


def _rules(css: str) -> list[tuple[list[str], str]]:
    result = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [part.strip() for part in match.group(1).split(",")]
        selectors = [item for item in selectors if item and not item.startswith("@")]
        if selectors:
            result.append((selectors, match.group(2)))
    return result


def _panel_rules(css: str) -> list[tuple[list[str], str]]:
    pattern = re.compile(re.escape(_PANEL) + r"(?![\w-])")
    return [
        (selectors, body)
        for selectors, body in _rules(css)
        if any(pattern.search(selector) for selector in selectors)
    ]


def _split_media(css: str, query: str) -> tuple[str, str]:
    """返回（媒体块之外的 CSS，媒体块内部）；块内不再嵌套大括号以外的结构。"""
    start = css.index(query)
    depth, end = 0, len(css)
    for index in range(start, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    return css[:start] + css[end:], css[start:end]


class ConsoleFilterPanelTest(unittest.TestCase):
    def test_desktop_panel_is_transparent_for_every_blur(self) -> None:
        for blur in (0, 14, 40):
            css = build_console_css(blur)
            outside, _ = _split_media(css, "@media (max-width: 768px)")
            rules = _panel_rules(outside)
            self.assertEqual(len(rules), 1, blur)
            body = rules[0][1]
            self.assertIn("background: transparent !important", body, blur)
            self.assertIn("background-color: transparent !important", body, blur)
            self.assertIn("box-shadow: none !important", body, blur)
            self.assertIn("backdrop-filter: none !important", body, blur)
            self.assertIn("-webkit-backdrop-filter: none !important", body, blur)

    def test_desktop_border_follows_inner_divider_strength(self) -> None:
        # 开启玻璃时与卡片内分隔线一致；强度为 0 时只跟随界面透明度。
        on = build_console_css(14)
        self.assertIn("border-color: rgba(var(--v-theme-on-surface), 0.15)", on)
        off = build_console_css(0)
        self.assertIn("var(--astrbot-palette-surface-opacity, 0) * 0.14", off)

    def test_panel_geometry_is_never_taken_over(self) -> None:
        for blur in (0, 14):
            for _, body in _panel_rules(build_console_css(blur)):
                for prop in _GEOMETRY:
                    self.assertNotIn(prop, body, f"blur={blur} 不应接管 {prop}")

    def test_fullscreen_keeps_upstream_surface(self) -> None:
        # 全屏时上游给侧栏写死深灰底，所有规则都必须排除 :fullscreen。
        css = build_console_css(14)
        for selectors, _ in _panel_rules(css):
            for selector in selectors:
                self.assertIn("#console-wrapper:not(:fullscreen)", selector)
                self.assertIn(".console-page", selector)
        self.assertNotIn(":fullscreen .console-filter-panel", css)

    def test_floating_panel_keeps_readable_surface_on_narrow_screens(self) -> None:
        # 窄屏侧栏浮在日志上方，强度为 0 时也要有最低底色和边框，且不带模糊。
        _, off_block = _split_media(build_console_css(0), "@media (max-width: 768px)")
        off_rules = _panel_rules(off_block)
        self.assertEqual(len(off_rules), 1)
        off_body = off_rules[0][1]
        self.assertIn("calc(0.78 +", off_body)
        self.assertIn("0.2)", off_body)
        self.assertIn("backdrop-filter: none !important", off_body)
        self.assertNotIn("blur(", off_body)

        for blur in (14, 40):
            _, block = _split_media(
                build_console_css(blur), "@media (max-width: 768px)"
            )
            body = _panel_rules(block)[0][1]
            self.assertIn("calc(0.54 +", body, blur)
            self.assertIn(f"backdrop-filter: blur({blur}px)", body, blur)
            self.assertIn(f"-webkit-backdrop-filter: blur({blur}px)", body, blur)

    def test_breakpoint_matches_upstream_floating_layout(self) -> None:
        self.assertIn("@media (max-width: 768px)", build_console_css(14))

    def test_no_zero_blur_is_ever_emitted(self) -> None:
        self.assertNotIn("blur(0px)", build_console_css(0))

    def test_rules_are_scoped_to_console_page_only(self) -> None:
        # 过滤器侧栏只存在于控制台页，不应出现在其它页面的规则里。
        css = build_console_css(14)
        for selectors, _ in _rules(css):
            for selector in selectors:
                self.assertIn(".v-main .console-page #console-wrapper", selector)
                self.assertNotIn(".platform-page", selector)


class ConsoleFilterPanelIntegrationTest(unittest.TestCase):
    def test_rules_are_part_of_runtime_theme_for_every_blur(self) -> None:
        for blur in (0, 14, 40):
            self.assertIn(build_console_css(blur), _css(blur=blur), blur)

    def test_panel_rules_come_after_existing_console_surface_rules(self) -> None:
        # 先于旧的控制台通配规则会被它们的 !important 覆盖掉。
        css = _css()
        console_wrapper = css.index(
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper {"
        )
        panel = css.index(build_console_css(14))
        self.assertGreater(panel, console_wrapper)


class ConsolePageOuterTintTest(unittest.TestCase):
    _MAIN = "html.astrbot-palette-active #app .v-main"

    def _page_bodies(self, css: str, page: str) -> list[str]:
        selector = f"{self._MAIN} {page}"
        return [body for selectors, body in _rules(css) if selector in selectors]

    def test_console_page_container_has_no_own_tint(self) -> None:
        # 最外层容器比卡片宽一圈，再铺底色会在卡片背后露出一圈深色边框。
        for blur in (0, 14, 40):
            self.assertEqual(
                self._page_bodies(_css(blur=blur), ".console-page"), [], blur
            )

    def test_other_page_containers_keep_their_tint(self) -> None:
        # 只处理控制台页，其它页面容器的底色规则不能被一并移除。
        css = _css()
        for page in (
            ".stats-page",
            ".trace-page",
            ".provider-page",
            ".plugin-detail-page",
        ):
            bodies = self._page_bodies(css, page)
            self.assertTrue(
                any("background:" in body for body in bodies), f"{page} 丢失底色规则"
            )

    def test_console_card_keeps_its_own_surface(self) -> None:
        # 去掉外层底色后，卡片自身仍由 console-page #console-wrapper 规则承担玻璃。
        css = _css(blur=14)
        card = self._page_bodies(css, ".console-page #console-wrapper::before")
        self.assertTrue(card)
        self.assertTrue(any("blur(14px)" in body for body in card))


if __name__ == "__main__":
    unittest.main()
