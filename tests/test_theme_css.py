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


class AstrBot428SurfaceTest(unittest.TestCase):
    """AstrBot 4.28 新页面结构的覆盖回归测试。

    4.28 重构了配置页（config-workspace 滚动结构）、平台/提供商工作台
    （platform-workbench/provider-workbench）并新增会话工作区
    （conversation-workspace，--workspace-* 变量驱动），这些选择器必须
    持续命中，防止后续改动悄悄丢失对新页面的覆盖。
    """

    def test_conversation_workspace_variables_taken_over(self) -> None:
        bodies = _rules_bodies(_css(), ".conversation-workspace")
        self.assertTrue(bodies, "未找到 .conversation-workspace 变量接管规则")
        for variable in ("--workspace-card", "--workspace-surface", "--workspace-subtle"):
            self.assertTrue(
                any(variable in body for body in bodies),
                f".conversation-workspace 缺少 {variable} 接管",
            )
        self.assertTrue(
            any("background: transparent !important;" in body for body in bodies)
        )

    def test_new_glass_carriers_blur_by_default(self) -> None:
        css = _css()
        for selector in (
            ".conversation-workspace .workspace-card",
            ".platform-page .platform-workbench",
            ".unsaved-changes-pill",
            ".config-panel .config-standard-section__groups .v-card",
        ):
            bodies = _rules_bodies(css, selector)
            self.assertTrue(bodies, f"未找到以 {selector} 结尾的规则")
            self.assertTrue(
                any("blur(14px)" in body for body in bodies),
                f"{selector} 默认应带玻璃模糊",
            )

    def test_new_glass_carriers_respect_zero_blur(self) -> None:
        css = _css({"stats_card_blur": 0})
        for selector in (
            ".conversation-workspace .workspace-card",
            ".platform-page .platform-workbench",
            ".unsaved-changes-pill",
        ):
            bodies = _rules_bodies(css, selector)
            self.assertTrue(bodies, f"未找到以 {selector} 结尾的规则")
            self.assertTrue(
                any("backdrop-filter: none !important;" in body for body in bodies),
                f"{selector} 在 stats_card_blur=0 时必须输出 none",
            )

    def test_new_inner_surfaces_disable_filter(self) -> None:
        css = _css()
        for selector in (".config-panel .ai-disabled-state",):
            bodies = _rules_bodies(css, selector)
            self.assertTrue(bodies, f"未找到以 {selector} 结尾的规则")
            self.assertTrue(
                any("backdrop-filter: none !important;" in body for body in bodies),
                f"{selector} 内层表面不得叠加模糊",
            )

    def test_platform_page_variables_taken_over(self) -> None:
        bodies = _rules_bodies(_css(), ".platform-page")
        self.assertTrue(bodies, "未找到 .platform-page 变量接管规则")
        for variable in ("--platform-surface", "--platform-border"):
            self.assertTrue(
                any(variable in body for body in bodies),
                f".platform-page 缺少 {variable} 接管",
            )

    def test_config_toolbar_sticky_backdrop_follows_opacity(self) -> None:
        bodies = _rules_bodies(_css(), ".config-toolbar-sticky::before")
        self.assertTrue(bodies, "未找到粘性工具栏背景条规则")
        self.assertTrue(
            any(
                "rgba(var(--v-theme-containerBg)" in body and "blur(14px)" in body
                for body in bodies
            ),
            "粘性工具栏背景条应跟随透明度并玻璃化",
        )

    def test_config_workspace_border_variables_taken_over(self) -> None:
        bodies = _rules_bodies(_css(), ".config-panel .config-workspace")
        self.assertTrue(bodies, "未找到 .config-workspace 边框变量接管规则")
        for variable in ("--config-border", "--config-divider"):
            self.assertTrue(
                any(variable in body for body in bodies),
                f".config-workspace 缺少 {variable} 接管",
            )

    def test_config_profile_menu_overlay_surface(self) -> None:
        bodies = _rules_bodies(_css(), ".config-profile-menu")
        self.assertTrue(bodies, "未找到配置方案菜单 overlay 规则")
        self.assertTrue(
            any("box-shadow: none !important;" in body for body in bodies),
            "配置方案菜单应去除原生阴影",
        )


class AstrBot428TransparencyDetailTest(unittest.TestCase):
    """0.4.17：AstrBot 4.28.0 透明化细节补齐的回归测试。

    覆盖机器人标题栏、窄屏配置导航、模型选择菜单、人设能力列表
    （正文与弹窗两处入口）、Trace 卡片与吸顶表头、供应商列表选中态、
    旧版会话详情消息容器。只断言行为约束，不做整段快照。
    """

    def test_bot_editor_header_transparent(self) -> None:
        bodies = _rules_bodies(_css(), ".platform-page .bot-editor__header")
        self.assertTrue(bodies, "未找到机器人标题栏覆盖规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "background-color: transparent !important;" in body
                and "box-shadow: none !important;" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                for body in bodies
            ),
            "机器人标题栏应透明且不再叠加滤镜或阴影",
        )

    def test_mobile_config_nav_rules_only_inside_720_media(self) -> None:
        css = _css()
        block = _media_block(css, "@media (max-width: 720px)")
        self.assertIn(".config-panel .config-workspace__nav-item", block)
        outside = css.replace(block, "")
        self.assertNotIn(
            "config-workspace__nav-item",
            outside,
            "配置导航覆盖只允许出现在 720px 媒体查询内，桌面规则不变",
        )

    def test_mobile_config_nav_states(self) -> None:
        block = _media_block(_css(), "@media (max-width: 720px)")
        normal = _rules_bodies(block, ".config-panel .config-workspace__nav-item")
        hover = _rules_bodies(block, ".config-panel .config-workspace__nav-item:hover")
        active = _rules_bodies(
            block, ".config-panel .config-workspace__nav-item--active"
        )
        self.assertTrue(
            any("background: transparent !important;" in body for body in normal),
            "窄屏导航普通态应透明",
        )
        self.assertTrue(
            any(
                "rgba(var(--v-theme-on-surface), 0.045)" in body for body in hover
            ),
            "窄屏导航悬停应保留原生 0.045 半透明底",
        )
        self.assertTrue(
            any(
                "rgba(var(--v-theme-on-surface), 0.07)" in body for body in active
            ),
            "窄屏导航选中应保留原生 0.07 底色",
        )
        self.assertGreater(
            block.index(".config-workspace__nav-item--active"),
            block.index(".config-workspace__nav-item:hover"),
            "选中规则必须位于悬停规则之后，保证选中优先于悬停",
        )

    def test_mobile_config_nav_active_hover_combo(self) -> None:
        # 单独的 --active 选择器特异度（1-4-1）低于 :hover（1-4-2），
        # 缺少 --active:hover 组合规则时，选中项悬停会退回 0.045 悬停色；
        # 该断言确保误删组合选择器时测试失败。
        block = _media_block(_css(), "@media (max-width: 720px)")
        combo = _rules_bodies(
            block, ".config-panel .config-workspace__nav-item--active:hover"
        )
        self.assertTrue(
            combo,
            "缺少 --active:hover 组合规则，选中且悬停时会被普通悬停色盖住",
        )
        self.assertTrue(
            any(
                "background: rgba(var(--v-theme-on-surface), 0.07) !important;"
                in body
                and "background-color: rgba(var(--v-theme-on-surface), 0.07)"
                " !important;" in body
                for body in combo
            ),
            "--active:hover 组合态应输出 0.07 选中底色，"
            "并同时覆盖 background/background-color",
        )

    def test_provider_menu_card_outer_glass(self) -> None:
        bodies = _rules_bodies(_css(), ".v-menu .provider-menu-card")
        self.assertTrue(bodies, "未找到模型菜单外层卡片规则")
        self.assertTrue(
            any(
                "rgba(var(--v-theme-surface), calc(0.54" in body
                and "blur(14px) saturate(1.08)" in body
                and "border-color:" in body
                and "box-shadow:" in body
                for body in bodies
            ),
            "模型菜单外层应复用 surface_strong 玻璃表面并承担模糊",
        )

    def test_provider_menu_card_blur_bounds(self) -> None:
        max_bodies = _rules_bodies(
            _css({"stats_card_blur": 40}), ".v-menu .provider-menu-card"
        )
        self.assertTrue(
            any("blur(40px) saturate(1.08)" in body for body in max_bodies),
            "stats_card_blur=40 时模型菜单应输出 blur(40px)",
        )
        zero_bodies = _rules_bodies(
            _css({"stats_card_blur": 0, "surface_opacity": 1}),
            ".v-menu .provider-menu-card",
        )
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in zero_bodies
            ),
            "stats_card_blur=0 时模型菜单必须关闭玻璃，且不被 surface_opacity 重新染色",
        )

    def test_provider_menu_inner_surfaces_transparent(self) -> None:
        css = _css()
        for suffix in (
            ".provider-menu-card .provider-menu-list",
            ".provider-menu-card .selected-provider-list",
            ".provider-menu-card .provider-search .v-field",
        ):
            bodies = _rules_bodies(css, suffix)
            self.assertTrue(bodies, f"未找到以 {suffix} 结尾的规则")
            self.assertTrue(
                any(
                    "background: transparent !important;" in body
                    and "backdrop-filter: none !important;" in body
                    and "blur(" not in body
                    for body in bodies
                ),
                f"{suffix} 应透明且无独立模糊",
            )

    def test_persona_capability_list_transparent_in_main(self) -> None:
        css = _css()
        shell = _rules_bodies(css, ".persona-preview-card .capability-list")
        items = _rules_bodies(
            css, ".persona-preview-card .capability-list .capability-list__items"
        )
        self.assertTrue(shell, "未找到正文人设能力列表外壳规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                and "rgba(var(--v-theme-on-surface)" in body
                for body in shell
            ),
            "正文能力列表外壳应透明并复用主题边框",
        )
        self.assertTrue(items, "未找到正文人设能力列表内部列表规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in items
            ),
            "正文能力列表内部 v-list 应透明且无独立模糊",
        )

    def test_persona_capability_list_transparent_in_dialog(self) -> None:
        css = _css()
        shell = _rules_bodies(
            css, ".v-overlay-container .v-dialog .persona-form-card .capability-list"
        )
        items = _rules_bodies(
            css,
            ".v-overlay-container .v-dialog .persona-form-card "
            ".capability-list .capability-list__items",
        )
        self.assertTrue(shell, "未找到弹窗人设能力列表外壳规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                for body in shell
            ),
            "弹窗能力列表外壳应透明且不带滤镜",
        )
        self.assertTrue(items, "未找到弹窗人设能力列表内部列表规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in items
            ),
            "弹窗能力列表内部 v-list 应透明且无独立模糊",
        )

    def test_trace_card_variable_taken_over(self) -> None:
        bodies = _rules_bodies(_css(), ".trace-page")
        self.assertTrue(bodies, "未找到 .trace-page 规则")
        self.assertTrue(
            any(
                "--trace-card: rgba(var(--v-theme-surface), calc(0.42" in body
                and "!important" in body
                for body in bodies
            ),
            ".trace-page 应以 !important 接管 --trace-card 为普通玻璃表面",
        )

    def test_trace_card_blur_lifecycle(self) -> None:
        default_bodies = _rules_bodies(_css(), ".trace-page .trace-card")
        self.assertTrue(
            any("blur(14px) saturate(1.08)" in body for body in default_bodies),
            "Trace 主卡片默认应承担玻璃模糊",
        )
        max_bodies = _rules_bodies(
            _css({"stats_card_blur": 40}), ".trace-page .trace-card"
        )
        self.assertTrue(
            any("blur(40px) saturate(1.08)" in body for body in max_bodies),
            "stats_card_blur=40 时 Trace 主卡片应输出 blur(40px)",
        )
        zero_bodies = _rules_bodies(
            _css({"stats_card_blur": 0, "surface_opacity": 1}),
            ".trace-page .trace-card",
        )
        self.assertTrue(
            any(
                "backdrop-filter: none !important;" in body
                and "border: 1px solid transparent !important;" in body
                and "box-shadow: none !important;" in body
                and "blur(" not in body
                for body in zero_bodies
            ),
            "stats_card_blur=0 时 Trace 主卡片的滤镜、边框、阴影均应关闭",
        )

    def test_trace_header_inner_surface_without_filter(self) -> None:
        bodies = _rules_bodies(_css(), ".trace-page .trace-header")
        self.assertTrue(bodies, "未找到 Trace 表头规则")
        self.assertTrue(
            any(
                "rgba(var(--v-theme-surface), calc(0.30" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                for body in bodies
            ),
            "Trace 吸顶表头应复用内层半透明表面并显式关闭滤镜",
        )

    def test_provider_source_item_state_rules(self) -> None:
        css = _css()
        state_bodies = _rules_bodies(
            css, ".provider-page .provider-source-item--active"
        )
        self.assertTrue(state_bodies, "未找到供应商列表选中态规则")
        self.assertTrue(
            any(
                "background: rgba(var(--v-theme-on-surface), 0.05) !important;"
                in body
                and "background-color: rgba(var(--v-theme-on-surface), 0.05)"
                " !important;" in body
                for body in state_bodies
            ),
            "选中态应使用原生 on-surface 0.05 并同时覆盖 background/background-color",
        )
        hover_bodies = _rules_bodies(
            css, ".provider-page .provider-source-item:hover"
        )
        self.assertTrue(
            any(
                "rgba(var(--v-theme-on-surface), 0.05)" in body
                for body in hover_bodies
            ),
            "悬停态应使用原生 on-surface 0.05",
        )

    def test_provider_source_item_state_after_plain_glass(self) -> None:
        css = _css()
        plain_marker = (
            ".provider-page .provider-source-item,\n"
            "html.astrbot-palette-active #app .v-main "
            ".extension-page .extension-card,"
        )
        plain_index = css.index(plain_marker)
        state_index = css.index(".provider-page .provider-source-item--active {")
        self.assertGreater(
            state_index,
            plain_index,
            "选中态规则必须输出在普通项玻璃规则之后，否则仍会被盖住",
        )

    def test_provider_source_item_state_survives_zero_blur(self) -> None:
        css = _css({"stats_card_blur": 0})
        state_bodies = _rules_bodies(
            css, ".provider-page .provider-source-item--active"
        )
        self.assertTrue(
            any(
                "rgba(var(--v-theme-on-surface), 0.05)" in body
                for body in state_bodies
            ),
            "选中态底色不随毛玻璃关闭而消失",
        )

    def test_conversation_messages_container_transparent(self) -> None:
        css = _css()
        bodies = _rules_bodies(
            css, ".conversation-detail-card .conversation-messages-container"
        )
        self.assertTrue(bodies, "未找到旧版会话消息容器规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "background-color: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                for body in bodies
            ),
            "旧版会话消息容器应透明且无新增模糊",
        )
        self.assertIn(
            ".v-overlay-container .v-dialog "
            ".conversation-detail-card .conversation-messages-container",
            css,
            "消息容器规则必须限定在会话详情弹窗 overlay 作用域内",
        )
        self.assertNotIn(
            ".v-main .conversation-messages-container",
            css,
            "消息容器规则不得泄漏到正文作用域",
        )


class AstrBot4281SurfaceTest(unittest.TestCase):
    """AstrBot 4.28.1 新增界面适配的回归测试。

    覆盖聊天设置弹窗外壳、模型来源筛选菜单与吸顶分组标题、添加供应商
    弹窗内的来源卡片。只断言行为约束，不做整段快照。
    """

    def test_chat_settings_shell_glass_default_and_max(self) -> None:
        default_bodies = _rules_bodies(_css(), ".v-dialog .chat-settings")
        self.assertTrue(default_bodies, "未找到聊天设置弹窗外壳规则")
        self.assertTrue(
            any(
                "rgba(var(--v-theme-surface), calc(0.54" in body
                and "blur(14px) saturate(1.08)" in body
                and "box-shadow:" in body
                for body in default_bodies
            ),
            "聊天设置外壳默认应复用 surface_strong 玻璃表面并承担 blur(14px)",
        )
        max_bodies = _rules_bodies(
            _css({"stats_card_blur": 40}), ".v-dialog .chat-settings"
        )
        self.assertTrue(
            any("blur(40px) saturate(1.08)" in body for body in max_bodies),
            "stats_card_blur=40 时聊天设置外壳应输出 blur(40px)",
        )

    def test_chat_settings_shell_zero_blur_stays_transparent(self) -> None:
        bodies = _rules_bodies(
            _css({"stats_card_blur": 0, "surface_opacity": 1}),
            ".v-dialog .chat-settings",
        )
        self.assertTrue(bodies, "未找到聊天设置弹窗外壳规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "background-color: transparent !important;" in body
                and "border-color: transparent !important;" in body
                and "box-shadow: none !important;" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in bodies
            ),
            "stats_card_blur=0 时聊天设置外壳必须恢复透明，"
            "且不被 surface_opacity 重新染色",
        )

    def test_chat_settings_border_variables_follow_toggle(self) -> None:
        default_bodies = _rules_bodies(_css(), ".v-dialog .chat-settings")
        self.assertTrue(
            any(
                "--settings-border: rgba(var(--v-theme-on-surface), calc(0.20"
                in body
                and "--settings-divider: rgba(var(--v-theme-on-surface), calc(0.20"
                in body
                for body in default_bodies
            ),
            "默认应接管 --settings-border/--settings-divider 为玻璃边框",
        )
        zero_bodies = _rules_bodies(
            _css({"stats_card_blur": 0, "surface_opacity": 1}),
            ".v-dialog .chat-settings",
        )
        self.assertTrue(
            any(
                "--settings-border: transparent !important;" in body
                and "--settings-divider: transparent !important;" in body
                for body in zero_bodies
            ),
            "stats_card_blur=0 时 --settings-* 变量应跟随关闭为透明",
        )

    def test_chat_settings_layout_and_nav_not_overridden(self) -> None:
        css = _css()
        bodies = _rules_bodies(css, ".v-dialog .chat-settings")
        self.assertTrue(bodies, "未找到聊天设置弹窗外壳规则")
        for body in bodies:
            for forbidden in (
                "display:",
                "grid",
                "overflow",
                "height",
                "padding",
                "margin",
                "border-radius",
            ):
                self.assertNotIn(
                    forbidden,
                    body,
                    f"聊天设置外壳规则不得接管布局属性 {forbidden}",
                )
        self.assertEqual(
            css.count(".chat-settings"),
            1,
            "聊天设置只允许外壳一条规则，不新增内部或响应式批量覆盖",
        )
        self.assertNotIn(
            "#app .v-main .chat-settings",
            css,
            "聊天设置规则必须按 overlay 结构定向，不依赖 #app .v-main 祖先",
        )

    def test_source_menu_shell_glass_default_and_max(self) -> None:
        default_bodies = _rules_bodies(_css(), ".v-menu .provider-source-menu")
        self.assertTrue(default_bodies, "未找到来源筛选菜单外壳规则")
        self.assertTrue(
            any(
                "rgba(var(--v-theme-surface), calc(0.54" in body
                and "blur(14px) saturate(1.08)" in body
                and "border-color:" in body
                and "box-shadow:" in body
                for body in default_bodies
            ),
            "来源菜单外壳默认应复用 surface_strong 玻璃表面并承担 blur(14px)",
        )
        max_bodies = _rules_bodies(
            _css({"stats_card_blur": 40}), ".v-menu .provider-source-menu"
        )
        self.assertTrue(
            any("blur(40px) saturate(1.08)" in body for body in max_bodies),
            "stats_card_blur=40 时来源菜单外壳应输出 blur(40px)",
        )

    def test_source_menu_shell_zero_blur_stays_transparent(self) -> None:
        bodies = _rules_bodies(
            _css({"stats_card_blur": 0, "surface_opacity": 1}),
            ".v-menu .provider-source-menu",
        )
        self.assertTrue(bodies, "未找到来源筛选菜单外壳规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "border-color: transparent !important;" in body
                and "box-shadow: none !important;" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in bodies
            ),
            "stats_card_blur=0 时来源菜单外壳必须透明关闭，"
            "不被 surface_opacity 染实",
        )

    def test_source_menu_mounted_as_independent_overlay(self) -> None:
        css = _css()
        self.assertIn(
            "html.astrbot-palette-active .v-overlay-container "
            ".v-menu .provider-source-menu {",
            css,
            "来源菜单应按独立挂载的 overlay 匹配",
        )
        self.assertNotIn(
            ".provider-menu-card .provider-source-menu",
            css,
            "来源菜单不是主模型卡片的后代，不得写成嵌套选择器",
        )
        self.assertNotIn(
            "#app .v-main .provider-source-menu",
            css,
            "来源菜单规则不得依赖 #app .v-main 祖先",
        )

    def test_source_menu_inner_list_transparent(self) -> None:
        css = _css()
        bodies = _rules_bodies(css, ".provider-source-menu .v-list")
        self.assertTrue(bodies, "未找到来源菜单内部列表规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "background-color: transparent !important;" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in bodies
            ),
            "来源菜单内部 v-list 应透明且无独立模糊",
        )
        self.assertNotIn(
            ".provider-source-menu .v-list-item",
            css,
            "列表项 active/hover 交互态保留原生，不新增覆盖",
        )

    def test_source_header_inner_surface_without_filter(self) -> None:
        bodies = _rules_bodies(_css(), ".provider-menu-card .provider-source-header")
        self.assertTrue(bodies, "未找到来源分组吸顶标题规则")
        self.assertTrue(
            any(
                "rgba(var(--v-theme-surface), calc(0.30" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in bodies
            ),
            "吸顶标题应复用内层半透明表面并显式关闭滤镜",
        )

    def test_source_header_zero_blur_transparent(self) -> None:
        bodies = _rules_bodies(
            _css({"stats_card_blur": 0, "surface_opacity": 1}),
            ".provider-menu-card .provider-source-header",
        )
        self.assertTrue(bodies, "未找到来源分组吸顶标题规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "background-color: transparent !important;" in body
                for body in bodies
            ),
            "stats_card_blur=0 时吸顶标题应透明，不被 surface_opacity 染实",
        )

    def test_source_header_keeps_virtual_list_geometry(self) -> None:
        bodies = _rules_bodies(_css(), ".provider-menu-card .provider-source-header")
        self.assertTrue(bodies, "未找到来源分组吸顶标题规则")
        for body in bodies:
            for forbidden in (
                "height",
                "min-height",
                "padding",
                "margin",
                "position",
                "top:",
                "z-index",
                "overflow",
                "transform",
            ):
                self.assertNotIn(
                    forbidden,
                    body,
                    f"吸顶标题规则不得覆盖几何/定位属性 {forbidden}"
                    "（虚拟列表依赖原生 32px 高度与 sticky 定位）",
                )

    def test_source_card_transparent_without_filter(self) -> None:
        bodies = _rules_bodies(_css(), ".source-dialog .source-card")
        self.assertTrue(bodies, "未找到来源卡片规则")
        self.assertTrue(
            any(
                "background: transparent !important;" in body
                and "background-color: transparent !important;" in body
                and "box-shadow: none !important;" in body
                and "backdrop-filter: none !important;" in body
                and "-webkit-backdrop-filter: none !important;" in body
                and "blur(" not in body
                for body in bodies
            ),
            "来源卡片普通态应透明、沿用主题边框且无新增滤镜/阴影",
        )

    def test_source_card_hover_state_preserved(self) -> None:
        for config in ({}, {"stats_card_blur": 0, "surface_opacity": 1}):
            css = _css(config)
            hover = _rules_bodies(css, ".source-dialog .source-card:hover")
            self.assertTrue(hover, f"未找到来源卡片 hover 规则: {config}")
            self.assertTrue(
                any(
                    "background: rgba(var(--v-theme-on-surface), 0.045)"
                    " !important;" in body
                    and "background-color: rgba(var(--v-theme-on-surface), 0.045)"
                    " !important;" in body
                    and "border-color: rgba(var(--v-theme-on-surface), 0.2)"
                    " !important;" in body
                    for body in hover
                ),
                f"hover 应补回原生 0.045 底色与 0.2 边框: {config}",
            )
            self.assertGreater(
                css.index(".source-dialog .source-card:hover"),
                css.index(".source-dialog .source-card {"),
                f"hover 规则必须位于普通态规则之后: {config}",
            )

    def test_source_card_interaction_layer_untouched(self) -> None:
        css = _css()
        self.assertEqual(
            css.count(".source-card"),
            2,
            "来源卡片只允许普通态与 hover 两条规则",
        )
        for forbidden in (".source-card__select", ".source-card__link"):
            self.assertNotIn(
                forbidden,
                css,
                f"不得接管点击层或链接行为: {forbidden}",
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
