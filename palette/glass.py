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


# 模糊声明统一走 CSS 变量：视频壁纸下只要把这个变量改成 none，就能让全站
# 的 backdrop-filter 整组让位，不必逐条规则覆盖（!important 同权重时比的是
# 选择器特异度，逐条覆盖很容易压不住）。
GLASS_FILTER_VAR = "--astrbot-palette-glass-filter"
SIDEBAR_FILTER_VAR = "--astrbot-palette-sidebar-filter"


def glass_filter_token(blur: int) -> str:
    """变量里存的模糊值；0 表示不启用模糊。"""
    return f"blur({max(0, min(40, blur))}px) saturate(1.08)" if blur > 0 else "none"


def backdrop_filter_lines(blur: int, variable: str = GLASS_FILTER_VAR) -> list[str]:
    """生成背景模糊声明；为 0 时必须输出 none，blur(0px) 仍会触发滤镜合成。

    每条规则先写字面值、再写一层 `var(..., 字面值)`：后者覆盖前者（同权重时
    后者胜），变量正常时行为与写死一致；视频壁纸下把变量改成 none 就能让全站
    的模糊一起让位，不需要逐条选择器去比特异度（带 :not 链的规则很难压过）。
    """

    if blur <= 0:
        return [
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
        ]
    literal = f"blur({blur}px) saturate(1.08)"
    return [
        f"  backdrop-filter: {literal} !important;",
        f"  -webkit-backdrop-filter: {literal} !important;",
        f"  backdrop-filter: var({variable}, {literal}) !important;",
        f"  -webkit-backdrop-filter: var({variable}, {literal}) !important;",
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
