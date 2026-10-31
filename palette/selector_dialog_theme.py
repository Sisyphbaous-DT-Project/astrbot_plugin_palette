"""会话来源与发送者选择弹窗的悬浮玻璃表面。

AstrBot 4.29.4 起，会话来源（UMO）与发送者选择改为独立的 `v-dialog`，替代原先的
下拉列表，常在「新建任务」「分组」「添加机器人」等弹窗里再打开一层。这两个弹窗
的标题与常规弹窗相同，会被常规弹窗规则按界面透明度染色（默认为 0 即完全透明），
叠在外层弹窗上时两层的输入框与文字会交叠。它们承担的是原下拉列表的角色，这里
与下拉、小菜单共用悬浮令牌：毛玻璃强度为 0 时也保留最低底色，不输出模糊。
"""

from __future__ import annotations

from .glass import NOT_COLORED, backdrop_filter_lines, build_glass_tokens

_CARD = (
    "html.astrbot-palette-active .v-overlay-container .v-dialog"
    f" > .v-overlay__content > .v-card{NOT_COLORED}"
)
# 两个组件的已选区域在有、无已选项时都会渲染，作为弹窗卡片的定位依据。
# 分开写成两条选择器：:is() 内的逗号会被测试的简易选择器解析拆开。
_SELECTOR_CARDS = [
    f"{_CARD}:has(.umo-selection)",
    f"{_CARD}:has(.sender-selection)",
]


def _join(selectors: list[str]) -> str:
    return ",\n".join(selectors)


def build_selector_dialog_css(stats_card_blur: int) -> str:
    blur = max(0, min(40, stats_card_blur))
    tokens = build_glass_tokens(blur)

    # 常规弹窗规则会给标题条、正文区和按钮区各染一层底色，需一并清掉，
    # 否则会在玻璃卡片里重新拼出一层底框。
    parts = [
        f"{card} > {part}"
        for card in _SELECTOR_CARDS
        for part in (".v-card-title", ".v-card-text", ".v-card-actions")
    ]
    # 列表原生是实色 surface，会在玻璃卡片里留下整块底色。
    inner_lists = [f"{card} .v-list" for card in _SELECTOR_CARDS]

    return "\n".join(
        [
            _join(_SELECTOR_CARDS) + " {",
            f"  background: {tokens.floating_surface} !important;",
            f"  background-color: {tokens.floating_surface} !important;",
            f"  border: 1px solid {tokens.floating_border} !important;",
            f"  box-shadow: {tokens.floating_shadow} !important;",
            *backdrop_filter_lines(blur),
            "}",
            "",
            _join(parts) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            _join(inner_lists) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "}",
        ]
    )
