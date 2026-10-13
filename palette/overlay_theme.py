"""下拉选项、小菜单与此前未被接管的弹窗。

- 下拉选项列表（v-select / v-autocomplete / v-combobox）和各类 v-menu 悬浮在页面
  正文上方，没有遮罩衬托，必须有可读的玻璃底：跟随界面毛玻璃强度，强度为 0 时
  退回跟随界面透明度的普通染色。
- 少数弹窗没有任何规则覆盖，暗色主题下被 AstrBot 刷成实色；这里把外壳恢复为
  完全透明、不加模糊，靠原生遮罩衬托文字。人格详情弹窗原本被常规弹窗规则染成
  一层淡灰底框，同样改为透明。
"""

from __future__ import annotations

from .glass import backdrop_filter_lines, build_glass_tokens

_OVERLAY = "html.astrbot-palette-active .v-overlay-container"
# 模型选择菜单已有专用玻璃规则（含内部列表透明与吸顶标题），不重复接管。
_NOT_PROVIDER_MENU = ":not(.provider-menu-card):not(.provider-source-menu)"
_MENU_RADIUS = "14px"


def _join(selectors: list[str]) -> str:
    return ",\n".join(selectors)


def build_overlay_css(stats_card_blur: int) -> str:
    blur = max(0, min(40, stats_card_blur))
    tokens = build_glass_tokens(blur)

    # 菜单内容区的直接子元素才是可见的表面：v-select 等下拉直接是 v-list，
    # 自定义菜单（含共用的 StyledMenu）是 v-card 或 v-sheet。
    menu_surfaces = [
        f"{_OVERLAY} .v-menu > .v-overlay__content > .v-list{_NOT_PROVIDER_MENU}",
        f"{_OVERLAY} .v-menu > .v-overlay__content > .v-card{_NOT_PROVIDER_MENU}",
        f"{_OVERLAY} .v-menu > .v-overlay__content > .v-sheet{_NOT_PROVIDER_MENU}",
    ]
    # 下拉与菜单的外层容器：原生只有 4px 直角，且 v-select 等容器自带
    # overflow: hidden，不一起改圆角会把内部 14px 的圆角裁成直角。
    menu_shells = [
        f"{_OVERLAY} .v-menu > .v-overlay__content:has(> {child})"
        ":not(:has(> .provider-menu-card)):not(:has(> .provider-source-menu))"
        for child in (".v-list", ".v-card", ".v-sheet")
    ]

    # 卡片菜单里再嵌的 v-list / v-sheet 原生也是实色，需恢复透明。
    menu_inner = [
        f"{_OVERLAY} .v-menu > .v-overlay__content > .v-card{_NOT_PROVIDER_MENU} .v-list",
        f"{_OVERLAY} .v-menu > .v-overlay__content > .v-card{_NOT_PROVIDER_MENU} .v-sheet",
    ]

    # 以下弹窗外壳保持完全透明：选择人格、账户、聊天内的模型配置与工作区
    # 文件预览此前没有任何规则，各自都有专属类名；人格详情弹窗没有类名，借
    # 内部独有的 system-prompt-content 定位；这两处和未来任务弹窗原本都被
    # 常规弹窗规则染成淡灰底框，需带上相同的标题条件把特异度抬过它。
    # 常规弹窗规则还会给标题条、正文区和按钮区各染一层底色，外壳透明后这三块
    # 会重新拼出一个灰框，这几类弹窗需要连同三块一起清掉。
    regular_title = ":has(> .v-card-title.text-h3.pa-4.pb-0.pl-6)"
    titled_dialogs = [
        f"{_OVERLAY} .v-dialog .v-card:has(.system-prompt-content){regular_title}",
        # 未来任务的「新建任务」与「支持的消息平台」弹窗共用的外壳类。
        f"{_OVERLAY} .v-dialog .v-card.dashboard-dialog-card{regular_title}",
        # 人格的新建与编辑共用一个表单弹窗。
        f"{_OVERLAY} .v-dialog .v-card.persona-form-card{regular_title}",
    ]
    titled_parts = [
        f"{dialog} > {part}"
        for dialog in titled_dialogs
        for part in (".v-card-title", ".v-card-text", ".v-card-actions")
    ]
    plain_dialogs = [
        f"{_OVERLAY} .v-dialog .selector-dialog-card",
        f"{_OVERLAY} .v-dialog .account-dialog",
        f"{_OVERLAY} .v-dialog .provider-config-dialog",
        f"{_OVERLAY} .v-dialog .workspace-dialog-preview",
        *titled_dialogs,
    ]

    return "\n".join(
        [
            _join(menu_surfaces) + " {",
            f"  background: {tokens.floating_surface} !important;",
            f"  background-color: {tokens.floating_surface} !important;",
            f"  border: 1px solid {tokens.floating_border} !important;",
            f"  box-shadow: {tokens.floating_shadow} !important;",
            # 与管理行为页的切换条、筛选框统一为 14px 圆角。
            f"  border-radius: {_MENU_RADIUS} !important;",
            *backdrop_filter_lines(blur),
            "}",
            "",
            _join(menu_shells) + " {",
            f"  border-radius: {_MENU_RADIUS} !important;",
            "}",
            "",
            _join(menu_inner) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            _join(plain_dialogs) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  border-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            _join(titled_parts) + " {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            # 人格表单的「预设对话」折叠面板原生是实色 surface，弹窗外壳透明后会
            # 留下一块黑底；只清底色，保留原生的边框和圆角。
            f"{_OVERLAY} .v-dialog .v-card.persona-form-card .v-expansion-panel {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "}",
            "",
            # 选择人格弹窗右侧列表区原生写死实色 surface，外壳透明后必须一并清掉，
            # 否则会在透明外壳里留下一整块黑底。
            f"{_OVERLAY} .v-dialog .selector-dialog-card .items-panel {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "}",
        ]
    )
