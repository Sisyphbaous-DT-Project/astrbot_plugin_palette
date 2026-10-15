"""控制台页「过滤器」侧栏的玻璃规则。

AstrBot 4.29 起控制台页（仅工作区模式）新增日志过滤侧栏，原生底色是 96% 不透明
的 surface。日志卡片已被玻璃化，侧栏嵌在里面会拼出一块实色底板，这里把它恢复
透明，只保留与卡片内分隔线同强度的边框。

窄屏（≤768px）下上游会把侧栏改成浮在日志上方的绝对定位面板，透明会让日志文字
透出来叠在选项上，因此该宽度改用悬浮表面令牌，强度为 0 时仍保留最低底色。
全屏时上游自带固定深灰底，不接管。
"""

from __future__ import annotations

from .glass import backdrop_filter_lines, build_glass_tokens

_PANEL = (
    "html.astrbot-palette-active #app .v-main .console-page "
    "#console-wrapper:not(:fullscreen) .console-filter-panel"
)
# 与上游侧栏改为浮层的断点保持一致。
_FLOATING_BREAKPOINT = "768px"


def build_console_css(stats_card_blur: int) -> str:
    blur = max(0, min(40, stats_card_blur))
    tokens = build_glass_tokens(blur)
    floating_blur = [f"  {line}" for line in backdrop_filter_lines(blur)]

    return "\n".join(
        [
            f"{_PANEL} {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            f"  border-color: {tokens.divider} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            f"@media (max-width: {_FLOATING_BREAKPOINT}) {{",
            f"  {_PANEL} {{",
            f"    background: {tokens.floating_surface} !important;",
            f"    background-color: {tokens.floating_surface} !important;",
            f"    border-color: {tokens.floating_border} !important;",
            f"    box-shadow: {tokens.floating_shadow} !important;",
            *floating_blur,
            "  }",
            "}",
        ]
    )
