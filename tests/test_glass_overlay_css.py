"""页面玻璃、设置页、下拉菜单与新增弹窗规则的回归测试。

只断言稳定的行为约束（选择器是否命中、0 值是否真正关闭等），
不对整段 CSS 做快照。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palette.glass import build_glass_tokens  # noqa: E402
from palette.overlay_theme import build_overlay_css  # noqa: E402
from palette.page_glass_theme import build_page_glass_css  # noqa: E402
from palette.theme import build_theme_css  # noqa: E402

_TINT = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"


def _css(blur: int = 14, opacity: float = 0.35) -> str:
    return build_theme_css({"surface_opacity": opacity, "stats_card_blur": blur})


def _rules(css: str) -> list[tuple[list[str], str]]:
    """把 CSS 拆成（选择器列表，规则体）；媒体查询内的规则一并展开。"""
    result = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [part.strip() for part in match.group(1).split(",")]
        selectors = [item for item in selectors if item and not item.startswith("@")]
        if selectors:
            result.append((selectors, match.group(2)))
    return result


def _bodies(css: str, fragment: str) -> list[str]:
    """返回所有「某个选择器包含 fragment」的规则体。

    fragment 之后不能紧跟选择器字符（字母、数字、下划线、连字符），
    否则 `.items-panelX` 之类写错的选择器会被误判为命中。
    """
    pattern = re.compile(re.escape(fragment) + r"(?![\w-])")
    return [
        body
        for selectors, body in _rules(css)
        if any(pattern.search(selector) for selector in selectors)
    ]


def _media_block(css: str, media_query: str, marker: str) -> str:
    start = css.index(media_query)
    while True:
        depth, end = 0, len(css)
        for index in range(start, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        block = css[start:end]
        if marker in block:
            return block
        start = css.find(media_query, end)
        if start < 0:
            raise ValueError(f"未找到包含 {marker} 的 {media_query} 块")


class GlassTokensTest(unittest.TestCase):
    def test_disabled_tokens_never_emit_blur(self) -> None:
        tokens = build_glass_tokens(0)
        self.assertFalse(tokens.enabled)
        self.assertEqual(tokens.surface, _TINT)
        self.assertEqual(tokens.shadow, "none")

    def test_enabled_tokens_follow_stats_highlight_values(self) -> None:
        tokens = build_glass_tokens(14)
        self.assertTrue(tokens.enabled)
        self.assertIn("0.42 +", tokens.surface)
        self.assertIn("0.54 +", tokens.surface_strong)

    def test_floating_tokens_keep_a_readable_floor_without_blur(self) -> None:
        # 悬浮菜单没有遮罩衬托，强度为 0 时仍要有最低底色、边框，且不带模糊与阴影。
        off = build_glass_tokens(0)
        self.assertIn("0.78 +", off.floating_surface)
        self.assertIn("0.2)", off.floating_border)
        self.assertEqual(off.floating_shadow, "none")
        # 开启玻璃时与信息框玻璃一致
        on = build_glass_tokens(14)
        self.assertEqual(on.floating_surface, on.surface_strong)
        self.assertEqual(on.floating_border, on.border)
        self.assertEqual(on.floating_shadow, on.shadow)


class PageGlassTest(unittest.TestCase):
    CARRIERS = [
        ".session-management-page > .v-container > .v-card",
        ".persona-manager .persona-card",
        ".persona-manager .base-folder-card",
        ".outlined-action-list-item:not(.mcp-server-list-item--selected)",
        ".subagent-page .setting-card",
        ".subagent-page .agent-panel",
        ".subagent-page .empty-card",
        ".kb-detail-page .v-card--variant-outlined",
        ".document-detail-page .v-card--variant-outlined",
        ".skills-page .neo-filter-card",
        ".skills-page .neo-table-card",
        ".persona-manager .empty-state .v-card",
    ]

    def test_blur_zero_emits_nothing(self) -> None:
        self.assertEqual(build_page_glass_css(0), "")
        css = _css(blur=0)
        for fragment in self.CARRIERS:
            for body in _bodies(css, fragment):
                self.assertNotIn("blur(", body, fragment)

    def test_carriers_get_blur_with_matching_strength(self) -> None:
        for blur in (14, 40):
            css = build_page_glass_css(blur)
            for fragment in self.CARRIERS:
                bodies = _bodies(css, fragment)
                self.assertTrue(bodies, f"缺少玻璃规则: {fragment}")
                self.assertTrue(
                    any(f"blur({blur}px)" in body for body in bodies), fragment
                )

    def test_v_card_carriers_carry_specificity_chain(self) -> None:
        # 通用 .v-card 复位规则带 :not 链，载体不带链会被 backdrop-filter: none 压住。
        css = build_page_glass_css(14)
        for selectors, body in _rules(css):
            if "blur(" not in body:
                continue
            for selector in selectors:
                if selector.endswith(":hover"):
                    continue
                if (
                    ".v-card" in selector
                    or "persona-card" in selector
                    or ("base-folder-card" in selector)
                    or "outlined-action-list-item" in selector
                ):
                    self.assertIn(":not(.bg-primary)", selector, selector)

    def test_selected_mcp_item_is_not_taken_over(self) -> None:
        css = build_page_glass_css(14)
        self.assertNotIn(
            ".outlined-action-list-item.mcp-server-list-item--selected", css
        )
        self.assertIn(":not(.mcp-server-list-item--selected)", css)

    def test_hoverable_items_restore_hover_feedback(self) -> None:
        css = build_page_glass_css(14)
        for fragment in (
            ".persona-card",
            ".base-folder-card",
            ".outlined-action-list-item",
        ):
            self.assertTrue(
                any(
                    ":hover" in s and fragment in s for ss, _ in _rules(css) for s in ss
                ),
                fragment,
            )

    def test_nested_cards_and_tables_are_cleared(self) -> None:
        css = build_page_glass_css(14)
        for fragment in (
            ".subagent-page .inner-card",
            ".subagent-page .selector-card",
            ".kb-detail-page .config-item",
            ".kb-detail-page .v-card .v-list",
            ".session-management-page > .v-container > .v-card:not(.bg-primary)"
            ":not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error)"
            ":not(.bg-info) .v-data-table",
        ):
            bodies = _bodies(css, fragment)
            self.assertTrue(bodies, fragment)
            self.assertTrue(
                any(
                    "background: transparent !important;" in body
                    and "backdrop-filter: none !important;" in body
                    for body in bodies
                ),
                fragment,
            )

    def test_kb_tables_carry_specificity_chain(self) -> None:
        # 通用 .v-main .v-table:not(...) 染色规则特异度为 1-10-1，清透明的规则
        # 必须带同样的 :not 链，否则知识库表格会留一块灰底。
        css = build_page_glass_css(14)
        for page in (".kb-detail-page", ".document-detail-page"):
            roots = [
                selector
                for selectors, _ in _rules(css)
                for selector in selectors
                if f"{page} .v-card--variant-outlined" in selector
                and selector.endswith(" .v-table")
            ]
            self.assertTrue(roots, f"{page} 缺少表格根选择器")
            for selector in roots:
                self.assertIn(":not(.bg-primary)", selector, selector)
                self.assertIn(":not(.bg-info)", selector, selector)

    def test_page_wrappers_become_transparent(self) -> None:
        css = build_page_glass_css(14)
        for fragment in (
            ".skills-page",
            ".subagent-page .dashboard-shell",
            ".cron-page .dashboard-shell",
            ".kb-detail-page",
            ".kb-detail-page .v-tabs",
            ".kb-detail-page .v-window",
            ".skills-page .skills-list",
            ".extension-page > div > .v-card",
            ".plugin-section-page > .v-row > div > .v-card",
        ):
            bodies = _bodies(css, fragment)
            self.assertTrue(bodies, fragment)
            self.assertTrue(
                any("background: transparent !important;" in b for b in bodies),
                fragment,
            )

    def test_component_toggle_is_rounded_like_filter_fields(self) -> None:
        for blur in (0, 14):
            css = _css(blur=blur)
            toggle = (
                ".v-card:has(.system-plugin-checkbox) > .v-card-text > "
                ".d-flex.justify-space-between.align-center.mb-6 > .v-btn-toggle"
            )
            bodies = [b for b in _bodies(css, toggle) if "border-radius" in b]
            self.assertTrue(bodies, "切换条应设置圆角")
            self.assertTrue(any("border-radius: 14px !important;" in b for b in bodies))
            self.assertTrue(
                any(
                    "border-radius: 14px 0 0 14px !important;" in b
                    for b in _bodies(css, f"{toggle} > .v-btn:first-child")
                )
            )
            self.assertTrue(
                any(
                    "border-radius: 0 14px 14px 0 !important;" in b
                    for b in _bodies(css, f"{toggle} > .v-btn:last-child")
                )
            )


class SettingsPageGlassTest(unittest.TestCase):
    PAGE = ".settings-page"

    def test_cards_follow_glass_strength(self) -> None:
        css = _css(blur=14)
        for fragment in (
            f"{self.PAGE} .settings-list-card",
            f"{self.PAGE} .storage-cleanup-card",
            f"{self.PAGE} .system-config-group .v-card:not(.bg-primary)",
        ):
            bodies = _bodies(css, fragment)
            self.assertTrue(any("blur(14px)" in body for body in bodies), fragment)

    def test_blur_zero_keeps_plain_tint(self) -> None:
        css = _css(blur=0)
        for fragment in (
            f"{self.PAGE} .settings-list-card",
            f"{self.PAGE} .system-config-restart-bar",
        ):
            for body in _bodies(css, fragment):
                self.assertNotIn("blur(", body, fragment)
        self.assertNotIn("blur(0px)", css)

    def test_inner_rows_are_transparent_only_when_glass_is_on(self) -> None:
        glass = _bodies(_css(blur=14), f"{self.PAGE} .settings-item")
        self.assertTrue(
            any("background: transparent !important;" in body for body in glass)
        )
        plain = _bodies(_css(blur=0), f"{self.PAGE} .settings-item")
        self.assertTrue(any(f"background: {_TINT} !important;" in b for b in plain))

    def test_nested_config_items_follow_the_inner_row_rule(self) -> None:
        # 嵌套对象配置的行包装层与行同属内层：玻璃开启时透明，关闭时保持染色。
        fragment = f"{self.PAGE} .system-config-group .config-item"
        glass = _bodies(_css(blur=14), fragment)
        self.assertTrue(any("background: transparent !important;" in b for b in glass))
        plain = _bodies(_css(blur=0), fragment)
        self.assertTrue(any(f"background: {_TINT} !important;" in b for b in plain))

    def test_restart_bar_is_glass(self) -> None:
        bodies = _bodies(_css(blur=14), f"{self.PAGE} .system-config-restart-bar")
        self.assertTrue(any("blur(14px)" in body for body in bodies))

    def test_nav_states_keep_native_fixed_colors(self) -> None:
        css = _css(blur=14)
        # 选中竖条与桌面悬停/选中底色不再随透明度缩放，透明度为 0 时仍可见。
        self.assertEqual(
            _bodies(css, f"{self.PAGE} .settings-nav__item--active::before"), []
        )
        block = _media_block(css, "@media (max-width: 720px)", "settings-nav__item")
        normal = _bodies(block, f"{self.PAGE} .settings-nav__item")
        self.assertTrue(any("background: transparent !important;" in b for b in normal))
        hover = _bodies(block, f"{self.PAGE} .settings-nav__item:hover")
        self.assertTrue(any("0.045" in b for b in hover))
        active = _bodies(block, f"{self.PAGE} .settings-nav__item--active")
        self.assertTrue(any("0.07" in b for b in active))
        # 导航项覆盖只允许出现在窄屏媒体查询内
        outside = css.replace(block, "")
        self.assertNotIn(".settings-nav__item", outside)


class OverlayGlassTest(unittest.TestCase):
    SURFACES = [
        ".v-menu > .v-overlay__content > .v-list",
        ".v-menu > .v-overlay__content > .v-card",
        ".v-menu > .v-overlay__content > .v-sheet",
    ]
    PLAIN_DIALOGS = [
        ".v-dialog .selector-dialog-card",
        ".v-dialog .account-dialog",
        ".v-dialog .provider-config-dialog",
        ".v-dialog .workspace-dialog-preview",
        ".v-dialog .v-card:has(.system-prompt-content)",
        ".v-dialog .v-card.dashboard-dialog-card",
        ".v-dialog .v-card.persona-form-card",
    ]

    def test_dropdowns_and_menus_follow_glass_strength(self) -> None:
        for blur in (14, 40):
            css = build_overlay_css(blur)
            for fragment in self.SURFACES:
                bodies = _bodies(css, fragment)
                self.assertTrue(bodies, fragment)
                self.assertTrue(any(f"blur({blur}px)" in b for b in bodies), fragment)

    def test_menus_and_dropdowns_are_rounded_like_other_controls(self) -> None:
        for blur in (0, 14):
            css = build_overlay_css(blur)
            for fragment in self.SURFACES:
                bodies = _bodies(css, fragment)
                self.assertTrue(
                    any("border-radius: 14px !important;" in b for b in bodies),
                    fragment,
                )
            # 容器自带 overflow: hidden，必须一起改圆角，否则内部圆角会被裁成直角。
            shells = _bodies(css, ".v-menu > .v-overlay__content:has(")
            self.assertTrue(any("border-radius: 14px !important;" in b for b in shells))
            for selectors, _ in _rules(css):
                for selector in selectors:
                    if ".v-overlay__content:has(" in selector:
                        self.assertIn(":not(:has(> .provider-menu-card))", selector)

    def test_blur_zero_keeps_a_readable_floor_for_menus(self) -> None:
        # 下拉与小菜单悬在正文上方、没有遮罩，强度为 0 也不能退回全透明。
        css = build_overlay_css(0)
        self.assertNotIn("blur(", css)
        for fragment in self.SURFACES:
            bodies = _bodies(css, fragment)
            self.assertTrue(
                any(
                    "0.78 +" in b
                    and "border: 1px solid rgba(var(--v-theme-on-surface), 0.2)" in b
                    and "backdrop-filter: none !important;" in b
                    and "box-shadow: none !important;" in b
                    for b in bodies
                ),
                fragment,
            )

    def test_every_menu_surface_and_shell_branch_is_covered(self) -> None:
        css = build_overlay_css(14)
        for child in (".v-list", ".v-card", ".v-sheet"):
            self.assertTrue(
                any(
                    "border-radius: 14px !important;" in b
                    for b in _bodies(
                        css,
                        f".v-menu > .v-overlay__content:has(> {child})"
                        ":not(:has(> .provider-menu-card))"
                        ":not(:has(> .provider-source-menu))",
                    )
                ),
                f"外层容器 {child} 分支",
            )
        for inner in (".v-list", ".v-sheet"):
            self.assertTrue(
                any(
                    "background: transparent !important;" in b
                    for b in _bodies(
                        css,
                        ".v-menu > .v-overlay__content > .v-card"
                        ":not(.provider-menu-card):not(.provider-source-menu) " + inner,
                    )
                ),
                f"卡片菜单内嵌 {inner}",
            )

    def test_provider_menu_keeps_dedicated_rules(self) -> None:
        css = build_overlay_css(14)
        for fragment in self.SURFACES:
            for selectors, _ in _rules(css):
                for selector in selectors:
                    if (
                        selector.endswith(fragment.split(" > ")[-1])
                        or fragment in selector
                    ):
                        self.assertIn(":not(.provider-menu-card)", selector)
                        self.assertIn(":not(.provider-source-menu)", selector)
        # 模型选择菜单的原有玻璃规则仍在完整输出里
        full = _css(blur=14)
        self.assertTrue(
            any("blur(14px)" in b for b in _bodies(full, ".v-menu .provider-menu-card"))
        )

    def test_nested_lists_inside_card_menus_are_transparent(self) -> None:
        css = build_overlay_css(14)
        bodies = _bodies(
            css, "> .v-card:not(.provider-menu-card):not(.provider-source-menu) .v-list"
        )
        self.assertTrue(
            any(
                "background: transparent !important;" in b
                and "backdrop-filter: none !important;" in b
                for b in bodies
            )
        )

    def test_plain_dialogs_are_fully_transparent_at_any_strength(self) -> None:
        for blur in (0, 14, 40):
            css = build_overlay_css(blur)
            for fragment in self.PLAIN_DIALOGS:
                bodies = _bodies(css, fragment)
                self.assertTrue(bodies, fragment)
                self.assertTrue(
                    any(
                        "background: transparent !important;" in b
                        and "border-color: transparent !important;" in b
                        and "box-shadow: none !important;" in b
                        and "backdrop-filter: none !important;" in b
                        and "blur(" not in b
                        for b in bodies
                    ),
                    f"{fragment} @blur={blur}",
                )

    def test_titled_dialogs_clear_title_text_and_actions_bands(self) -> None:
        # 常规弹窗规则会给这三块各染一层底色，只清外壳会重新拼出一个灰框。
        title = ":has(> .v-card-title.text-h3.pa-4.pb-0.pl-6)"
        for head in (
            ".v-dialog .v-card:has(.system-prompt-content)",
            ".v-dialog .v-card.dashboard-dialog-card",
            ".v-dialog .v-card.persona-form-card",
        ):
            for part in (".v-card-title", ".v-card-text", ".v-card-actions"):
                bodies = _bodies(build_overlay_css(14), f"{head}{title} > {part}")
                self.assertTrue(
                    any("background: transparent !important;" in b for b in bodies),
                    f"{head} > {part}",
                )

    def test_dialogs_sharing_regular_title_beat_regular_rule(self) -> None:
        # 人格详情与未来任务弹窗同时命中常规弹窗的标题条件，必须带同样的条件
        # 并位于其后，才能压过它。
        title = ":has(> .v-card-title.text-h3.pa-4.pb-0.pl-6)"
        regular = ".v-dialog .v-card" + title
        for head in (
            ".v-dialog .v-card:has(.system-prompt-content)",
            ".v-dialog .v-card.dashboard-dialog-card",
            ".v-dialog .v-card.persona-form-card",
        ):
            selector = head + title
            for blur in (0, 14):
                bodies = _bodies(build_overlay_css(blur), selector)
                self.assertTrue(
                    any("background: transparent !important;" in b for b in bodies),
                    selector,
                )
            full = _css(blur=14)
            self.assertGreater(full.index(selector), full.index(regular), selector)

    def test_persona_form_expansion_panel_is_transparent(self) -> None:
        # 「预设对话」折叠面板原生是实色 surface，不清掉会在透明弹窗里留黑块；
        # 只清底色，边框与圆角保持原生，所以规则里不能带 border / radius 声明。
        for blur in (0, 14):
            bodies = _bodies(
                build_overlay_css(blur),
                ".v-dialog .v-card.persona-form-card .v-expansion-panel",
            )
            self.assertTrue(bodies)
            self.assertTrue(
                any("background: transparent !important;" in b for b in bodies)
            )
            for body in bodies:
                self.assertNotIn("border", body)

    def test_persona_selector_inner_panel_is_transparent(self) -> None:
        bodies = _bodies(
            build_overlay_css(14), ".v-dialog .selector-dialog-card .items-panel"
        )
        self.assertTrue(any("background: transparent !important;" in b for b in bodies))

    def test_regular_dialogs_stay_tint_only(self) -> None:
        # 其余常规弹窗按设计只染色不加模糊，新增规则不得改变这一点。
        for blur in (0, 14, 40):
            css = _css(blur=blur)
            bodies = _bodies(
                css, ".v-dialog .v-card:has(> .v-card-title.text-h3.pa-4.pb-0.pl-6)"
            )
            plain = [b for b in bodies if "markdown" not in b]
            self.assertTrue(plain)
            self.assertTrue(
                any(
                    "backdrop-filter: none !important;" in b and "blur(" not in b
                    for b in plain
                )
            )

    def test_dead_about_dialog_is_not_targeted(self) -> None:
        # beta.2 的关于弹窗没有任何打开入口，不为它写规则。
        self.assertNotIn("font-weight-bold", build_overlay_css(14))

    def test_no_zero_pixel_blur_anywhere(self) -> None:
        for blur in (0, 14):
            self.assertNotIn("blur(0px)", _css(blur=blur))


if __name__ == "__main__":
    unittest.main()
