"""恢复挂进 Dashboard 主区域的弹窗原生实色表面。

AstrBot 4.29.3 的控制台 pip 弹窗，以及全屏时的诊断导出弹窗，会把 overlay 容器
挂到 `#console-wrapper` 内。通用页面规则因此把卡片和输入框染成界面底色。这里
只匹配 `.v-main` 内的 `.v-dialog`，恢复卡片实色和 Vuetify 24 级阴影；挂在 body
层的常规弹窗、菜单和 tooltip 均不受影响。规则不依赖毛玻璃强度或界面透明度。
"""

from __future__ import annotations

from .glass import NOT_COLORED

_DIALOG = "html.astrbot-palette-active #app .v-main .v-overlay-container .v-dialog"
_CARD = f"{_DIALOG} > .v-overlay__content > .v-card{NOT_COLORED}"
_SHADOW = (
    "0px 11px 15px -7px var(--v-shadow-key-umbra-color, rgba(0,0,0,.2)), "
    "0px 24px 38px 3px var(--v-shadow-key-penumbra-color, rgba(0,0,0,.14)), "
    "0px 9px 46px 8px var(--v-shadow-key-ambient-color, rgba(0,0,0,.12))"
)


def build_attached_dialog_css() -> str:
    inner_surfaces = [
        f"{_CARD} .v-field{NOT_COLORED}",
        f"{_CARD} .v-sheet{NOT_COLORED}",
        f"{_CARD} .v-list{NOT_COLORED}",
    ]
    return "\n".join(
        [
            f"{_CARD} {{",
            "  background: rgb(var(--v-theme-surface)) !important;",
            "  background-color: rgb(var(--v-theme-surface)) !important;",
            f"  box-shadow: {_SHADOW} !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            ",\n".join(inner_surfaces) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "}",
        ]
    )
