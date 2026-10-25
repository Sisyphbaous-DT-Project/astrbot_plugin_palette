"""新版追踪页与挂进主区域弹窗的 CSS 行为回归测试。

只断言玻璃开关、浮层可读性、覆盖顺序和布局保护等稳定行为，不做整段快照。
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from palette.attached_dialog_theme import build_attached_dialog_css  # noqa: E402
from palette.glass import NOT_COLORED  # noqa: E402
from palette.theme import build_theme_css  # noqa: E402
from palette.trace_theme import build_trace_css  # noqa: E402

_PAGE = "html.astrbot-palette-active #app .v-main .trace-page"
_EXPLORER = f"{_PAGE} .trace-explorer"
_GLASS = f"{_EXPLORER}::before"
_TABLE = f"{_EXPLORER} .trace-list-table .v-table__wrapper > table"
_HEADER = f"{_TABLE} > thead > tr > th"
_FILTER = f"{_EXPLORER} .trace-filter-panel"
_DETAIL = f"{_EXPLORER} .trace-detail"
_PANELS = ((".trace-filter-panel", "900px"), (".trace-detail", "1100px"))
_FULL_WIDTH_QUERY = "@media (max-width: 640px)"
_DIALOG = "html.astrbot-palette-active #app .v-main .v-overlay-container .v-dialog"
_CARD = f"{_DIALOG} > .v-overlay__content > .v-card{NOT_COLORED}"
_GEOMETRY = (
    "position",
    "top:",
    "bottom:",
    "left:",
    "right:",
    "width",
    "height",
    "flex",
    "z-index",
    "overflow",
    "padding",
    "margin",
    "display",
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


def _bodies(css: str, selector: str) -> list[str]:
    return [body for selectors, body in _rules(css) if selector in selectors]


def _body(css: str, selector: str) -> str:
    bodies = _bodies(css, selector)
    if len(bodies) != 1:
        raise AssertionError(f"应只有一条 {selector} 规则，实际为 {len(bodies)} 条")
    return bodies[0]


def _rule_index(css: str, selector: str) -> int:
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        selectors = [part.strip() for part in match.group(1).split(",")]
        if selector in selectors:
            return match.start()
    return -1


def _media_block(css: str, query: str, marker: str) -> str:
    start = css.index(query)
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
        start = css.find(query, end)
        if start < 0:
            raise AssertionError(f"未找到包含 {marker} 的 {query} 块")


def _desktop_css(css: str) -> str:
    for panel, breakpoint in _PANELS:
        query = f"@media (max-width: {breakpoint})"
        css = css.replace(_media_block(css, query, panel), "", 1)
    return css.replace(_media_block(css, _FULL_WIDTH_QUERY, ".trace-detail"), "", 1)


class TraceExplorerTest(unittest.TestCase):
    def test_explorer_carries_glass_on_pseudo_element(self) -> None:
        for blur in (14, 40):
            css = build_trace_css(blur)
            body = _body(css, _EXPLORER)
            self.assertIn("position: relative !important", body)
            self.assertIn("isolation: isolate !important", body)
            self.assertIn("background: transparent !important", body)
            self.assertIn("border: 1px solid rgba(var(--v-theme-on-surface)", body)
            self.assertIn("border-radius: 16px !important", body)
            self.assertIn("box-shadow: 0 16px 36px", body)
            self.assertIn("--trace-border: rgba(var(--v-theme-on-surface), 0.15)", body)
            glass = _body(css, _GLASS)
            self.assertIn('content: "" !important', glass)
            self.assertIn("position: absolute !important", glass)
            self.assertIn("inset: 0 !important", glass)
            self.assertIn("z-index: -1 !important", glass)
            self.assertIn("border-radius: inherit !important", glass)
            self.assertIn("pointer-events: none !important", glass)
            self.assertIn("background: rgba(var(--v-theme-surface), calc(0.42 +", glass)
            self.assertIn(f"backdrop-filter: blur({blur}px)", glass)
            self.assertIn(f"-webkit-backdrop-filter: blur({blur}px)", glass)

    def test_explorer_itself_never_blurs_so_inner_blur_works(self) -> None:
        # 卡片自身带模糊会成为内层模糊的取样边界，表头和浮层面板的模糊随之失效。
        for blur in (0, 14, 40):
            body = _body(build_trace_css(blur), _EXPLORER)
            self.assertIn("backdrop-filter: none !important", body, blur)
            self.assertIn("-webkit-backdrop-filter: none !important", body, blur)
            self.assertNotIn("blur(", body, blur)

    def test_zero_strength_keeps_explorer_plain(self) -> None:
        css = build_trace_css(0)
        body = _body(css, _EXPLORER)
        self.assertIn("background: transparent !important", body)
        self.assertIn("background-color: transparent !important", body)
        self.assertIn("border: 1px solid transparent !important", body)
        self.assertIn("box-shadow: none !important", body)
        self.assertNotIn("--trace-border", body)
        self.assertFalse(_bodies(css, _GLASS))
        self.assertNotIn("blur(0px)", css)

    def test_trace_rules_are_in_runtime_theme(self) -> None:
        for blur in (0, 14, 40):
            self.assertIn(build_trace_css(blur), _css(blur=blur), blur)


class TracePanelTest(unittest.TestCase):
    def test_desktop_filter_panel_is_transparent(self) -> None:
        for blur in (0, 14, 40):
            body = _body(_desktop_css(build_trace_css(blur)), _FILTER)
            self.assertIn("background: transparent !important", body)
            self.assertIn("background-color: transparent !important", body)
            self.assertIn("box-shadow: none !important", body)
            self.assertIn("backdrop-filter: none !important", body)
            self.assertIn("-webkit-backdrop-filter: none !important", body)

    def test_desktop_detail_is_rounded_card(self) -> None:
        for blur in (0, 14, 40):
            body = _body(_desktop_css(build_trace_css(blur)), _DETAIL)
            self.assertIn("margin: 10px !important", body)
            self.assertIn("border: 1px solid var(--trace-border) !important", body)
            self.assertIn("border-radius: 14px !important", body)
            self.assertIn("rgba(var(--v-theme-on-surface), 0.03)", body)
            self.assertIn("box-shadow: none !important", body)
            self.assertIn("backdrop-filter: none !important", body)

    def test_detail_drops_margin_when_full_width(self) -> None:
        css = build_trace_css(14)
        block = _media_block(css, _FULL_WIDTH_QUERY, ".trace-detail")
        self.assertIn("margin: 0 !important", _body(block, _DETAIL))

    def test_list_divider_is_cleared_next_to_detail_card(self) -> None:
        for blur in (0, 14):
            selector = f"{_EXPLORER} .trace-explorer-body.has-detail .trace-list"
            body = _body(build_trace_css(blur), selector)
            self.assertIn("border-right-color: transparent !important", body)

    def test_floating_panels_use_upstream_breakpoints(self) -> None:
        css = build_trace_css(14)
        for panel, breakpoint in _PANELS:
            block = _media_block(css, f"@media (max-width: {breakpoint})", panel)
            body = _body(block, f"{_EXPLORER} {panel}")
            self.assertIn("calc(0.54 +", body, panel)
            self.assertIn("border-color: rgba(var(--v-theme-on-surface)", body)
            self.assertIn("box-shadow: 0 16px 36px", body)
            self.assertIn("backdrop-filter: blur(14px)", body)

    def test_floating_panels_keep_floor_without_blur(self) -> None:
        css = build_trace_css(0)
        for panel, breakpoint in _PANELS:
            block = _media_block(css, f"@media (max-width: {breakpoint})", panel)
            body = _body(block, f"{_EXPLORER} {panel}")
            self.assertIn("calc(0.78 +", body, panel)
            self.assertIn("rgba(var(--v-theme-on-surface), 0.2)", body)
            self.assertIn("box-shadow: none !important", body)
            self.assertIn("backdrop-filter: none !important", body)
            self.assertNotIn("blur(", body)

    def test_panel_geometry_is_never_taken_over(self) -> None:
        # 详情卡片按设计只加间距，定位、尺寸与滚动仍沿用上游。
        for blur in (0, 14):
            css = build_trace_css(blur)
            for panel, _ in _PANELS:
                allowed = ("margin",) if panel == ".trace-detail" else ()
                for body in _bodies(css, f"{_EXPLORER} {panel}"):
                    for prop in _GEOMETRY:
                        if prop in allowed:
                            continue
                        self.assertNotIn(prop, body, f"{panel} 不应接管 {prop}")

    def test_zero_strength_keeps_native_panel_dividers(self) -> None:
        css = _desktop_css(build_trace_css(0))
        self.assertNotIn("border-color", _body(css, _FILTER))
        self.assertIn("var(--trace-border)", _body(css, _DETAIL))


class TraceTableTest(unittest.TestCase):
    def test_sticky_header_drops_surface_when_blur_is_available(self) -> None:
        for blur in (14, 40):
            body = _body(build_trace_css(blur), _HEADER)
            self.assertIn("background: transparent !important", body)
            self.assertIn("background-color: transparent !important", body)
            self.assertIn(f"backdrop-filter: blur({blur}px)", body)
            self.assertIn(f"-webkit-backdrop-filter: blur({blur}px)", body)

    def test_sticky_header_stays_transparent_without_blur(self) -> None:
        # 强度为 0 时不给表头单独铺底色，深色主题下那会是一块黑色硬框。
        body = _body(build_trace_css(0), _HEADER)
        self.assertIn("background: transparent !important", body)
        self.assertIn("background-color: transparent !important", body)
        self.assertIn("backdrop-filter: none !important", body)
        self.assertIn("-webkit-backdrop-filter: none !important", body)
        self.assertNotIn("rgba(var(--v-theme-surface)", body)

    def test_sticky_header_geometry_is_not_taken_over(self) -> None:
        for blur in (0, 14):
            body = _body(build_trace_css(blur), _HEADER)
            for prop in _GEOMETRY:
                self.assertNotIn(prop, body, f"表头不应接管 {prop}")

    def test_selected_row_and_cells_restore_native_feedback(self) -> None:
        for opacity in (0, 0.35):
            css = _css(opacity=opacity)
            row = _body(css, f"{_TABLE} > tbody > tr.trace-list-row.selected")
            self.assertIn("background: rgba(var(--v-theme-primary), 0.1)", row)
            self.assertIn(
                "background-color: rgba(var(--v-theme-primary), 0.1) !important", row
            )
            cell = _body(css, f"{_TABLE} > tbody > tr.trace-list-row.selected > td")
            self.assertIn("background: transparent !important", cell)
            self.assertIn("background-color: transparent !important", cell)

    def test_selected_row_comes_after_generic_tbody_rule(self) -> None:
        css = _css()
        generic = "html.astrbot-palette-active #app .v-main .v-table__wrapper > table > tbody > tr"
        selected = f"{_TABLE} > tbody > tr.trace-list-row.selected"
        generic_index = _rule_index(css, generic)
        selected_index = _rule_index(css, selected)
        self.assertGreaterEqual(generic_index, 0)
        self.assertGreaterEqual(selected_index, 0)
        self.assertGreater(selected_index, generic_index)

    def test_native_hover_pseudo_element_is_not_taken_over(self) -> None:
        css = build_trace_css(14)
        self.assertNotIn(":hover", css)
        self.assertNotIn("::after", css)


class TraceCompatibilityTest(unittest.TestCase):
    def test_new_rules_come_after_surface_and_legacy_rules(self) -> None:
        css = _css()
        generic_th = "html.astrbot-palette-active #app .v-main .v-data-table__th"
        legacy_card = f"{_PAGE} .trace-card"
        generic_index = _rule_index(css, generic_th)
        legacy_index = _rule_index(css, legacy_card)
        explorer_index = _rule_index(css, _EXPLORER)
        self.assertGreaterEqual(generic_index, 0)
        self.assertGreaterEqual(legacy_index, 0)
        self.assertGreaterEqual(explorer_index, 0)
        self.assertGreater(explorer_index, generic_index)
        self.assertGreater(explorer_index, legacy_index)

    def test_legacy_trace_rules_remain_for_older_astrbot(self) -> None:
        css = _css()
        self.assertTrue(any("--trace-card:" in body for body in _bodies(css, _PAGE)))
        self.assertTrue(_bodies(css, f"{_PAGE} .trace-card"))
        self.assertTrue(_bodies(css, f"{_PAGE} .trace-header"))
        for selector in (
            f"{_PAGE} .trace-displayer",
            f"{_PAGE} .trace-event",
            f"{_PAGE} .trace-event--active",
        ):
            self.assertTrue(_bodies(css, selector), selector)


class AttachedDialogTest(unittest.TestCase):
    def test_rules_exist_for_every_blur_and_surface_opacity(self) -> None:
        for blur in (0, 14):
            for opacity in (0, 0.35):
                css = _css(blur=blur, opacity=opacity)
                self.assertIn(build_attached_dialog_css(), css)
                self.assertTrue(_bodies(css, _CARD))

    def test_card_restores_native_surface_and_shadow(self) -> None:
        body = _body(build_attached_dialog_css(), _CARD)
        self.assertIn("background: rgb(var(--v-theme-surface)) !important", body)
        self.assertIn("background-color: rgb(var(--v-theme-surface)) !important", body)
        self.assertIn("0px 11px 15px -7px", body)
        self.assertIn("0px 24px 38px 3px", body)
        self.assertIn("0px 9px 46px 8px", body)
        self.assertIn("backdrop-filter: none !important", body)
        self.assertIn("-webkit-backdrop-filter: none !important", body)

    def test_inner_surfaces_are_transparent_on_solid_card(self) -> None:
        css = build_attached_dialog_css()
        for component in (".v-field", ".v-sheet", ".v-list"):
            selector = f"{_CARD} {component}{NOT_COLORED}"
            body = _body(css, selector)
            self.assertIn("background: transparent !important", body, component)
            self.assertIn("background-color: transparent !important", body, component)

    def test_rules_are_limited_to_dialogs_inside_main(self) -> None:
        for selectors, _ in _rules(build_attached_dialog_css()):
            for selector in selectors:
                self.assertIn(".v-main .v-overlay-container .v-dialog", selector)
                self.assertNotIn(".v-menu", selector)
                self.assertNotIn("tooltip", selector)

    def test_overlay_position_and_stacking_are_not_taken_over(self) -> None:
        for _, body in _rules(build_attached_dialog_css()):
            self.assertNotIn("position", body)
            self.assertNotIn("z-index", body)

    def test_card_has_specificity_chain_and_follows_generic_card(self) -> None:
        self.assertIn(NOT_COLORED, _CARD)
        css = _css()
        generic = (
            "html.astrbot-palette-active #app .v-main .v-card"
            f"{NOT_COLORED}:not(.bg-darkprimary)"
        )
        generic_index = _rule_index(css, generic)
        attached_index = _rule_index(css, _CARD)
        self.assertGreaterEqual(generic_index, 0)
        self.assertGreaterEqual(attached_index, 0)
        self.assertGreater(attached_index, generic_index)


if __name__ == "__main__":
    unittest.main()
