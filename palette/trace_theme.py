"""AstrBot 4.29.3 起新版追踪页的玻璃与表格可读性规则。

新版 `.trace-explorer` 取代旧 `.trace-card`，作为本页唯一的玻璃载体。玻璃画在
`::before` 伪元素上，卡片本身不带 `backdrop-filter`：带模糊的元素会成为内层模糊
的取样边界，吸顶表头和窄屏浮层面板的模糊就取不到背后的列表，只剩一层半透明底色
而文字叠在一起。强度为 0 时卡片透明且无装饰，继续由 `.trace-page` 的界面底色承担
染色，避免双层叠色。

吸顶表头始终不铺底色：强度大于 0 时只靠模糊挡住滚到下面的行；强度为 0 时与旧版
`.trace-header` 一致完全透明，不给它单独铺一条底色（深色主题下会是一块黑色硬框），
代价是滚动中的行会与表头文字短暂重叠。右侧详情面板做成带间距的圆角卡片，去掉
列表与它之间的分隔线；上游把它改成绝对定位浮层的窄屏断点下改用悬浮表面，手机
全宽时取消间距。筛选面板桌面端只清除实色，浮层断点同样使用悬浮表面。

选中行需要带 `!important` 恢复主色底，并清掉选中行单元格的通用界面底色；Vuetify
的悬停色画在单元格 `::after` 上，这里不接管该伪元素。面板与表头的定位、尺寸和
滚动均沿用上游。旧版 `.trace-card` / `.trace-header` 规则仍保留在 theme.py，供
4.28～4.29.1 使用。
"""

from __future__ import annotations

from .glass import backdrop_filter_lines, build_glass_tokens

_EXPLORER = "html.astrbot-palette-active #app .v-main .trace-page .trace-explorer"
_FILTER = f"{_EXPLORER} .trace-filter-panel"
_DETAIL = f"{_EXPLORER} .trace-detail"
_TABLE = f"{_EXPLORER} .trace-list-table .v-table__wrapper > table"
# 与上游把面板改为浮层、详情改为全宽的断点保持一致。
_FILTER_FLOATING = "900px"
_DETAIL_FLOATING = "1100px"
_DETAIL_FULL_WIDTH = "640px"


def build_trace_css(stats_card_blur: int) -> str:
    blur = max(0, min(40, stats_card_blur))
    tokens = build_glass_tokens(blur)
    border = tokens.border if tokens.enabled else "transparent"

    rules = [
        f"{_EXPLORER} {{",
        # 定位与隔离只为承载下方的玻璃伪元素，不改变卡片自身的布局。
        "  position: relative !important;",
        "  isolation: isolate !important;",
        "  background: transparent !important;",
        "  background-color: transparent !important;",
        f"  border: 1px solid {border} !important;",
        "  border-radius: 16px !important;",
        f"  box-shadow: {tokens.shadow} !important;",
        "  backdrop-filter: none !important;",
        "  -webkit-backdrop-filter: none !important;",
    ]
    if tokens.enabled:
        # 强度为 0 时保留上游 0.1 分隔线，不随界面透明度降到不可见。
        rules.append(f"  --trace-border: {tokens.divider} !important;")
    rules.append("}")

    if tokens.enabled:
        rules.extend(
            [
                "",
                f"{_EXPLORER}::before {{",
                '  content: "" !important;',
                "  position: absolute !important;",
                "  inset: 0 !important;",
                "  z-index: -1 !important;",
                "  border-radius: inherit !important;",
                "  pointer-events: none !important;",
                f"  background: {tokens.surface} !important;",
                f"  background-color: {tokens.surface} !important;",
                *backdrop_filter_lines(blur),
                "}",
            ]
        )

    rules.extend(
        [
            "",
            f"{_FILTER} {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            f"{_DETAIL} {{",
            "  margin: 10px !important;",
            "  border: 1px solid var(--trace-border) !important;",
            "  border-radius: 14px !important;",
            "  background: rgba(var(--v-theme-on-surface), 0.03) !important;",
            "  background-color: rgba(var(--v-theme-on-surface), 0.03) !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            # 详情已是独立卡片，列表右侧的分隔线会与卡片边框叠成两条。
            f"{_EXPLORER} .trace-explorer-body.has-detail .trace-list {{",
            "  border-right-color: transparent !important;",
            "}",
            "",
            f"{_TABLE} > thead > tr > th {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            *backdrop_filter_lines(blur),
            "}",
            "",
            f"{_TABLE} > tbody > tr.trace-list-row.selected {{",
            "  background: rgba(var(--v-theme-primary), 0.1) !important;",
            "  background-color: rgba(var(--v-theme-primary), 0.1) !important;",
            "}",
            "",
            f"{_TABLE} > tbody > tr.trace-list-row.selected > td {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "}",
        ]
    )

    floating_blur = [f"  {line}" for line in backdrop_filter_lines(blur)]
    for panel, breakpoint in (
        (_FILTER, _FILTER_FLOATING),
        (_DETAIL, _DETAIL_FLOATING),
    ):
        rules.extend(
            [
                "",
                f"@media (max-width: {breakpoint}) {{",
                f"  {panel} {{",
                f"    background: {tokens.floating_surface} !important;",
                f"    background-color: {tokens.floating_surface} !important;",
                f"    border-color: {tokens.floating_border} !important;",
                f"    box-shadow: {tokens.floating_shadow} !important;",
                *floating_blur,
                "  }",
                "}",
            ]
        )

    rules.extend(
        [
            "",
            f"@media (max-width: {_DETAIL_FULL_WIDTH}) {{",
            f"  {_DETAIL} {{",
            "    margin: 0 !important;",
            "  }",
            "}",
        ]
    )

    return "\n".join(rules)
