"""AstrBot 4.29 各业务页卡片的毛玻璃规则。

这些页面此前只由通用规则按界面透明度染色，没有背景模糊。这里把每页最外层的
卡片当作玻璃载体，内层嵌套的卡片、表格恢复透明，避免模糊和底色叠两层。
毛玻璃强度为 0 时不输出任何规则，页面保持原有的纯染色表现。
"""

from __future__ import annotations

from .glass import NOT_COLORED, backdrop_filter_lines, build_glass_tokens

_MAIN = "html.astrbot-palette-active #app .v-main"
# 当前选中的 MCP 条目由 theme.py 单独恢复选中底色与边框（不带模糊与阴影），这里不接管。
_NOT_SELECTED = ":not(.mcp-server-list-item--selected)"


def _join(selectors: list[str]) -> str:
    return ",\n".join(selectors)


def _table_parts(root: str) -> list[str]:
    """通用规则会给表格各层染色，嵌在玻璃卡片内时需逐层恢复透明。"""
    return [
        f"{root} .v-data-table",
        f"{root} .v-data-table__td",
        f"{root} .v-data-table__th",
        f"{root} .v-table",
        f"{root} .v-table__wrapper > table",
        f"{root} .v-table__wrapper > table > thead",
        f"{root} .v-table__wrapper > table > tbody",
        f"{root} .v-table__wrapper > table > tbody > tr",
        f"{root} .v-table__wrapper > table > tbody > tr > td",
    ]


def build_page_glass_css(stats_card_blur: int) -> str:
    blur = max(0, min(40, stats_card_blur))
    if blur <= 0:
        return ""
    tokens = build_glass_tokens(blur)

    # v-card 载体：通用规则的 :not 链特异度为 (1,10,1)，这里带同样的链并靠
    # 后置顺序胜出，否则背景模糊会被它的 backdrop-filter: none 压住。
    session_cards = (
        f"{_MAIN} .session-management-page > .v-container > .v-card{NOT_COLORED}"
    )
    kb_cards = [
        f"{_MAIN} .kb-detail-page .v-card--variant-outlined{NOT_COLORED}",
        f"{_MAIN} .document-detail-page .v-card--variant-outlined{NOT_COLORED}",
    ]
    # 人格卡片与文件夹卡片、各类 OutlinedActionListItem 条目（未来任务、
    # 知识库、MCP、技能）都是可悬停的条目，需要同时补回悬停反馈。
    hover_cards = [
        f"{_MAIN} .persona-manager .persona-card{NOT_COLORED}",
        f"{_MAIN} .persona-manager .base-folder-card{NOT_COLORED}",
        f"{_MAIN} .outlined-action-list-item{_NOT_SELECTED}{NOT_COLORED}",
    ]
    static_cards = [
        session_cards,
        *kb_cards,
        f"{_MAIN} .persona-manager .empty-state .v-card{NOT_COLORED}",
        f"{_MAIN} .skills-page .neo-filter-card{NOT_COLORED}",
        f"{_MAIN} .skills-page .neo-table-card{NOT_COLORED}",
    ]
    # 子代理页的卡片不是 v-card，没有通用 :not 规则压制，直接匹配即可。
    plain_cards = [
        f"{_MAIN} .subagent-page .setting-card",
        f"{_MAIN} .subagent-page .agent-panel",
        f"{_MAIN} .subagent-page .empty-card",
    ]

    inner_cards = [
        f"{session_cards} .v-card{NOT_COLORED}",
        f"{_MAIN} .subagent-page .inner-card",
        f"{_MAIN} .subagent-page .selector-card",
        f"{_MAIN} .subagent-page .persona-preview-wrap",
        # 知识库设置标签里的配置行、概览里的信息列表：卡片内再叠一层灰。
        f"{_MAIN} .kb-detail-page .config-item",
        f"{_MAIN} .kb-detail-page .v-card .v-list",
    ]
    inner_tables = [
        *_table_parts(session_cards),
        # 外层 .v-table 同时被通用 .v-table:not(...) 规则染色（特异度 1-10-1），
        # 这里必须带同样的 :not 链才能压过它，否则表格会留一块灰底。
        *_table_parts(
            f"{_MAIN} .kb-detail-page .v-card--variant-outlined{NOT_COLORED}"
        ),
        *_table_parts(
            f"{_MAIN} .document-detail-page .v-card--variant-outlined{NOT_COLORED}"
        ),
    ]

    # 页面外层容器原本被通用规则整块染色；卡片换成玻璃后，背后会露出一块
    # 硬边的深色底板，这里恢复透明，由卡片自身承担底色。
    wrappers = [
        f"{_MAIN} .skills-page",
        # 技能列表容器包着每张技能卡片，同样被通用规则整块染色。
        f"{_MAIN} .skills-page .skills-list",
        f"{_MAIN} .subagent-page .dashboard-shell",
        f"{_MAIN} .cron-page .dashboard-shell",
        # 知识库详情页：页面根容器、标签页和标签页窗口各被通用规则染了一层，
        # 叠在玻璃卡片后面会拼出一整块底板。
        f"{_MAIN} .kb-detail-page",
        f"{_MAIN} .kb-detail-page .v-tabs",
        f"{_MAIN} .kb-detail-page .v-window",
    ]

    # 插件页「已安装 / 插件市场」两个标签共用一张最外层大卡片作为容器，里面
    # 每个插件才是真正的卡片；容器同样恢复透明，边框与阴影一并去掉。
    extension_shell = [
        f"{_MAIN} .extension-page > div > .v-card{NOT_COLORED}",
        # 「管理行为」页同样用一张透明内联样式的外层卡片包住指令表与筛选器，
        # 被通用规则染色后会露出整块底板。
        f"{_MAIN} .plugin-section-page > .v-row > div > .v-card{NOT_COLORED}",
    ]

    return "\n".join(
        [
            _join(wrappers) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "}",
            "",
            _join(extension_shell) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  border-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            # 外层玻璃载体：这一组才执行真实的背景模糊。
            _join([*hover_cards, *static_cards, *plain_cards]) + " {",
            f"  background: {tokens.surface} !important;",
            f"  background-color: {tokens.surface} !important;",
            f"  border-color: {tokens.border} !important;",
            f"  box-shadow: {tokens.shadow} !important;",
            *backdrop_filter_lines(blur),
            "}",
            "",
            # 可悬停条目：通用规则的 !important 会盖住原生悬停底色，补回玻璃态。
            _join([f"{selector}:hover" for selector in hover_cards]) + " {",
            f"  background: {tokens.surface_strong} !important;",
            f"  background-color: {tokens.surface_strong} !important;",
            f"  border-color: {tokens.hover_border} !important;",
            f"  box-shadow: {tokens.hover_shadow} !important;",
            "}",
            "",
            # 内层卡片、表格：只保留分割线，不再叠加底色与滤镜。
            _join([*inner_cards, *inner_tables]) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            _join(inner_cards) + " {",
            f"  border-color: {tokens.divider} !important;",
            "}",
        ]
    )
