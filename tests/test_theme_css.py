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

    def test_config_tabs_window_clips_overflow(self) -> None:
        for blur in (0, 14, 40):
            css = _css({"stats_card_blur": blur})
            bodies = _rules_bodies(css, ".config-tabs-window.v-window")
            self.assertTrue(
                any("overflow: hidden !important;" in body for body in bodies),
                f"stats_card_blur={blur} 时配置标签窗口缺少 overflow: hidden 裁剪",
            )

    def test_config_window_selectors_no_overflow_visible(self) -> None:
        css = _css()
        for suffix in (
            ".config-tabs-window.v-window",
            ".config-panel .v-window",
            ".v-window__container",
            ".v-window-item",
            ".v-tabs-window-item",
        ):
            bodies = _rules_bodies(css, suffix)
            self.assertTrue(bodies, f"未找到以 {suffix} 结尾的规则")
            for body in bodies:
                self.assertNotIn(
                    "overflow: visible",
                    body,
                    f"{suffix} 规则不允许再出现 overflow: visible: {body}",
                )

    def test_config_panel_keeps_overflow_visible(self) -> None:
        bodies = _rules_bodies(_css(), ".config-panel")
        self.assertTrue(
            any("overflow: visible !important;" in body for body in bodies),
            ".config-panel 必须保留 overflow: visible 以容纳固定按钮",
        )


class ComponentManagementGlassTest(unittest.TestCase):
    table_shell_suffix = ".v-card.rounded-lg.overflow-hidden.elevation-1"

    def test_management_scopes_cover_commands_and_tools(self) -> None:
        css = _css()
        self.assertIn(".v-card:has(.system-plugin-checkbox)", css)
        self.assertIn(".v-card:has(.builtin-tools-checkbox)", css)

    def test_management_table_uses_isolated_glass_layer(self) -> None:
        css = _css({"stats_card_blur": 14})
        shell_bodies = _rules_bodies(css, self.table_shell_suffix)
        layer_bodies = _rules_bodies(css, f"{self.table_shell_suffix}::before")
        root_bodies = _rules_bodies(css, f"{self.table_shell_suffix} > .v-data-table")
        overlay_bodies = _rules_bodies(css, f"{self.table_shell_suffix} > .v-card__overlay")

        self.assertTrue(
            any(
                "position: relative !important;" in body
                and "isolation: isolate !important;" in body
                and "backdrop-filter: none !important;" in body
                for body in shell_bodies
            ),
            "组件管理表格外壳缺少隔离层约束",
        )
        self.assertTrue(
            any(
                'content: "" !important;' in body
                and "z-index: 0 !important;" in body
                and "pointer-events: none !important;" in body
                and "blur(14px) saturate(1.08)" in body
                for body in layer_bodies
            ),
            "组件管理表格伪元素没有安全承载毛玻璃",
        )
        self.assertTrue(
            any(
                "z-index: 1 !important;" in body
                and "backdrop-filter: none !important;" in body
                for body in root_bodies
            ),
            "组件管理数据表内容层没有保持在玻璃层上方",
        )
        self.assertTrue(
            any("display: none !important;" in body for body in overlay_bodies),
            "组件管理表格仍保留 Vuetify overlay",
        )

    def test_management_and_sidebar_follow_blur_values(self) -> None:
        for blur in (0, 14, 40):
            css = _css({"stats_card_blur": blur})
            layer_bodies = _rules_bodies(css, f"{self.table_shell_suffix}::before")
            sidebar_bodies = _rules_bodies(
                css,
                ".v-navigation-drawer .v-list-item--active",
            )
            expected = (
                "backdrop-filter: none !important;"
                if blur == 0
                else f"backdrop-filter: blur({blur}px) saturate(1.08) !important;"
            )
            self.assertTrue(
                any(expected in body for body in layer_bodies),
                f"stats_card_blur={blur} 时组件管理表格滤镜不正确",
            )
            self.assertTrue(
                any(expected in body for body in sidebar_bodies),
                f"stats_card_blur={blur} 时侧栏选中项滤镜不正确",
            )
            if blur == 0:
                filter_bodies = [
                    body
                    for body in sidebar_bodies
                    if "backdrop-filter: none !important;" in body
                ]
                self.assertTrue(filter_bodies, "未找到侧栏选中项的滤镜关闭规则")
                for body in filter_bodies:
                    self.assertNotIn("background:", body)
                    self.assertNotIn("background-color:", body)

    def test_management_glass_decoration_disables_at_zero(self) -> None:
        css = _css({"stats_card_blur": 0})
        selector_suffixes = (
            (
                ".v-card:has(.builtin-tools-checkbox) > .v-card-text > "
                ".d-flex.justify-space-between.align-center.mb-6 > .v-btn-toggle"
            ),
            ".v-card:has(.builtin-tools-checkbox) .v-field",
            ".v-card:has(.system-plugin-checkbox) .v-alert.mb-4",
            self.table_shell_suffix,
            f"{self.table_shell_suffix}::before",
        )
        for suffix in selector_suffixes:
            bodies = _rules_bodies(css, suffix)
            self.assertTrue(bodies, f"未找到组件管理规则：{suffix}")
            if suffix.endswith("::before"):
                self.assertTrue(
                    any(
                        "background: transparent !important;" in body
                        and "backdrop-filter: none !important;" in body
                        for body in bodies
                    ),
                    f"stats_card_blur=0 时 {suffix} 未关闭底色或滤镜",
                )
            else:
                self.assertTrue(
                    any(
                        "background: transparent !important;" in body
                        and "box-shadow: none !important;" in body
                        for body in bodies
                    ),
                    f"stats_card_blur=0 时 {suffix} 未关闭底色或阴影",
                )

    def test_management_pagination_field_does_not_stack_blur(self) -> None:
        css = _css({"stats_card_blur": 40})
        bodies = _rules_bodies(css, ".v-data-table-footer .v-field")
        self.assertTrue(bodies, "未找到组件管理表格分页字段覆盖规则")
        for body in bodies:
            self.assertIn("box-shadow: none !important;", body)
            self.assertIn("backdrop-filter: none !important;", body)
            self.assertIn("-webkit-backdrop-filter: none !important;", body)
            self.assertNotIn("blur(", body)


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


class MobileSidebarGlassTest(unittest.TestCase):
    """窄屏 temporary 浮层侧栏的独立玻璃效果。"""

    _SUFFIX = ".v-navigation-drawer.v-navigation-drawer--temporary"
    _ACTIVE_SUFFIX = (
        ".v-navigation-drawer.v-navigation-drawer--temporary"
        ".v-navigation-drawer--active"
    )

    def _sidebar_bodies(self, css: str) -> list[str]:
        # endswith 不会命中 --active 阴影规则，只取基础 temporary 规则。
        bodies = _rules_bodies(css, self._SUFFIX)
        self.assertTrue(bodies, "缺少 temporary 侧栏目标规则")
        return bodies

    def _active_bodies(self, css: str) -> list[str]:
        return _rules_bodies(css, self._ACTIVE_SUFFIX)

    def test_default_renders_glass(self) -> None:
        bodies = self._sidebar_bodies(_css())
        self.assertTrue(
            any(
                "blur(18px) saturate(1.08)" in body
                and "-webkit-backdrop-filter: blur(18px) saturate(1.08) !important;" in body
                and "calc(0.72 + var(--astrbot-palette-surface-opacity, 0) * 0.24)"
                in body
                for body in bodies
            )
        )

    def test_shadow_only_on_active(self) -> None:
        # 外层阴影只挂在打开态：关闭态 drawer 只是平移出视口，
        # 常挂阴影会在屏幕左缘残留淡影；基础规则不负责阴影。
        css = _css()
        for body in self._sidebar_bodies(css):
            self.assertNotIn("box-shadow", body)
        active_bodies = self._active_bodies(css)
        self.assertTrue(active_bodies, "缺少 active 态阴影规则")
        self.assertTrue(
            any(
                "box-shadow: 0 16px 36px rgba(0, 0, 0, 0.26)" in body
                and body.count("box-shadow") == 1
                for body in active_bodies
            )
        )

    def test_max_value_renders_and_over_limit_clamps(self) -> None:
        for config in ({"mobile_sidebar_glass": 40}, {"mobile_sidebar_glass": 99}):
            bodies = self._sidebar_bodies(_css(config))
            self.assertTrue(any("blur(40px)" in body for body in bodies))
            self.assertFalse(any("blur(99px)" in body for body in bodies))

    def test_zero_outputs_transparent_and_none(self) -> None:
        css = _css({"mobile_sidebar_glass": 0})
        bodies = self._sidebar_bodies(css)
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "background-color: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                for body in bodies
            )
        )
        self.assertFalse(any("blur(0px)" in body for body in bodies))
        self.assertFalse(any("box-shadow" in body for body in bodies))
        # 关闭时不输出 active 阴影规则，由旧全局规则的 box-shadow: none 兜底。
        self.assertFalse(self._active_bodies(css))

    def test_zero_stays_transparent_with_surface_opacity(self) -> None:
        # 0 值必须显式盖掉旧侧栏规则，surface_opacity 调高也不能重新染色。
        bodies = self._sidebar_bodies(
            _css({"mobile_sidebar_glass": 0, "surface_opacity": 1.0})
        )
        self.assertTrue(
            any("background: transparent !important;" in body for body in bodies)
        )

    def test_selector_does_not_require_active_class(self) -> None:
        # 侧滑拖拽中间态没有 active class，玻璃底色选择器只绑定 temporary，
        # 保证拖拽过程中仍覆盖实底和滤镜，不出现透明穿透。
        css = _css()
        self.assertIn(
            "#app .v-navigation-drawer.v-navigation-drawer--temporary {",
            css,
        )
        for body in self._sidebar_bodies(css):
            self.assertIn("backdrop-filter", body)

    def test_overrides_carry_important(self) -> None:
        # 旧 .v-navigation-drawer 规则全是 !important，覆盖声明必须同级。
        css = _css()
        for body in self._sidebar_bodies(css) + self._active_bodies(css):
            for line in body.split(";"):
                line = line.strip()
                if line:
                    self.assertTrue(
                        line.endswith("!important"),
                        f"缺少 !important: {line}",
                    )

    def test_independent_from_stats_card_blur(self) -> None:
        bodies = self._sidebar_bodies(_css({"stats_card_blur": 0}))
        self.assertTrue(any("blur(18px)" in body for body in bodies))
        bodies = self._sidebar_bodies(
            _css({"stats_card_blur": 40, "mobile_sidebar_glass": 0})
        )
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                for body in bodies
            )
        )

    def test_surface_opacity_formula_bounds(self) -> None:
        # surface_opacity 合法范围 0~1，底色透明度因此落在 0.72~0.96。
        bodies = self._sidebar_bodies(_css({"surface_opacity": 1.0}))
        self.assertTrue(
            any(
                "calc(0.72 + var(--astrbot-palette-surface-opacity, 0) * 0.24)"
                in body
                for body in bodies
            )
        )


class CssIntegrityTest(unittest.TestCase):
    def test_braces_are_balanced(self) -> None:
        for config in (
            {},
            {"stats_card_blur": 0},
            {"stats_card_blur": 40},
            {"mobile_sidebar_glass": 0},
            {"mobile_sidebar_glass": 40},
        ):
            css = _css(config)
            self.assertEqual(css.count("{"), css.count("}"))


if __name__ == "__main__":
    unittest.main()
