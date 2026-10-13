"""毛玻璃配色令牌，供页面、浮层等运行时 CSS 模块共用。

数值与 `theme._stats_highlight_css` 中的信息框玻璃保持一致；毛玻璃强度为 0 时
退回只跟随界面透明度的普通染色，不输出任何模糊。悬浮的下拉与小菜单例外：它们
没有遮罩衬托，强度为 0 时仍保留最低底色和边框，保证选项文字可读。
"""

from __future__ import annotations

from dataclasses import dataclass

# 界面透明度（0–1）由注入脚本写入根节点的自定义属性。
_OPACITY = "var(--astrbot-palette-surface-opacity, 0)"

# 语义色块（主色、成功、警告等）不接管，沿用通用规则的排除链。
NOT_COLORED = (
    ":not(.bg-primary):not(.bg-secondary):not(.bg-success)"
    ":not(.bg-warning):not(.bg-error):not(.bg-info)"
)

# 下拉与小菜单在毛玻璃关闭时的最低底色透明度，不随界面透明度降到更低。
FLOATING_FLOOR = "0.78"

# 与界面透明度联动的普通染色表面，毛玻璃关闭时的基础底色。
TINT = f"rgba(var(--v-theme-surface), {_OPACITY})"
TINT_BORDER = f"rgba(var(--v-theme-on-surface), calc({_OPACITY} * 0.18))"
TINT_DIVIDER = f"rgba(var(--v-theme-on-surface), calc({_OPACITY} * 0.14))"


def backdrop_filter_lines(blur: int) -> list[str]:
    """生成背景模糊声明；为 0 时必须输出 none，blur(0px) 仍会触发滤镜合成。"""
    if blur <= 0:
        return [
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
        ]
    return [
        f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
        f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
    ]


@dataclass(frozen=True)
class GlassTokens:
    """一组玻璃表面所需的颜色、边框与阴影。"""

    enabled: bool
    surface: str
    surface_strong: str
    border: str
    divider: str
    shadow: str
    hover_shadow: str
    hover_border: str
    # 悬浮在正文上方的下拉与小菜单专用：没有遮罩衬托，强度为 0 时也必须保留
    # 最低底色和边框，否则选项文字会直接压在页面文字上。
    floating_surface: str
    floating_border: str
    floating_shadow: str


def build_glass_tokens(blur: int) -> GlassTokens:
    """按毛玻璃强度生成令牌；强度不大于 0 时返回普通染色版本。"""
    if blur <= 0:
        return GlassTokens(
            enabled=False,
            surface=TINT,
            surface_strong=TINT,
            border=TINT_BORDER,
            divider=TINT_DIVIDER,
            shadow="none",
            hover_shadow="none",
            hover_border=TINT_BORDER,
            floating_surface=(
                f"rgba(var(--v-theme-surface), calc({FLOATING_FLOOR} + {_OPACITY} * 0.2))"
            ),
            floating_border="rgba(var(--v-theme-on-surface), 0.2)",
            floating_shadow="none",
        )
    return GlassTokens(
        enabled=True,
        surface=(f"rgba(var(--v-theme-surface), calc(0.42 + {_OPACITY} * 0.32))"),
        surface_strong=(
            f"rgba(var(--v-theme-surface), calc(0.54 + {_OPACITY} * 0.28))"
        ),
        border=(f"rgba(var(--v-theme-on-surface), calc(0.20 + {_OPACITY} * 0.12))"),
        divider="rgba(var(--v-theme-on-surface), 0.15)",
        shadow=(
            "0 16px 36px rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.12)"
        ),
        hover_shadow=(
            "0 20px 44px rgba(0, 0, 0, 0.32), "
            "0 0 0 1px rgba(var(--v-theme-primary), 0.22), "
            "inset 0 1px 0 rgba(255, 255, 255, 0.16)"
        ),
        hover_border="rgba(var(--v-theme-primary), 0.34)",
        floating_surface=(
            f"rgba(var(--v-theme-surface), calc(0.54 + {_OPACITY} * 0.28))"
        ),
        floating_border=(
            f"rgba(var(--v-theme-on-surface), calc(0.20 + {_OPACITY} * 0.12))"
        ),
        floating_shadow=(
            "0 16px 36px rgba(0, 0, 0, 0.26), inset 0 1px 0 rgba(255, 255, 255, 0.12)"
        ),
    )
