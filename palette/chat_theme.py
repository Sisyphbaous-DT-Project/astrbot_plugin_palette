"""ChatUI 外框与导航控件的透明化规则。"""

from __future__ import annotations


def build_chat_theme_css() -> str:
    """只接管聊天外框，不改变输入框、消息内容及浮层侧栏的布局。"""
    prefix = "html.astrbot-palette-active #app"
    chat_app = (
        f"{prefix} .v-application"
        ":has(> .v-application__wrap > .top-header.chat-mode-header)"
    )
    sidebar_buttons = (
        f"{prefix} .chat-ui .chat-sidebar "
        ":is(.new-chat-btn, .settings-btn, .chat-sidebar-brand-toggle)"
    )
    header_buttons = (
        f"{prefix} .top-header.chat-mode-header "
        ":is(.chat-action-btn, .chat-mobile-sidebar-toggle)"
    )
    return "\n".join(
        [
            # 当前 Chat 路由的共同祖先铺底；路由切换后规则自动失配。
            f"{chat_app} {{",
            "  background: rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0)) !important;",
            "}",
            "",
            # 欢迎语与输入框外壳只是布局容器，重复染色会形成全宽横带。
            f"{chat_app} > .v-application__wrap > .v-main > .page-wrapper,",
            f"{prefix} .v-main .chat-ui,",
            f"{prefix} .v-main .chat-ui .chat-main,",
            f"{prefix} .v-main .chat-ui .messages-panel,",
            f"{prefix} .v-main .chat-ui .message-list-root,",
            f"{prefix} .v-main .chat-ui .composer-shell,",
            f"{prefix} .v-main .chat-ui .project-composer-shell {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "}",
            "",
            # temporary 侧栏仍由 mobile_sidebar_glass 提供遮挡，不清除其底色。
            f"{prefix} .chat-ui .chat-sidebar:not(.v-navigation-drawer--temporary) {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  border-color: transparent !important;",
            "}",
            "",
            # 保留原生紧凑尺寸及圆角；两组控件的状态不依赖毛玻璃开关。
            f"{sidebar_buttons},",
            f"{header_buttons} {{",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            f"{sidebar_buttons}:is(:hover, :focus-visible, .sidebar-workspace-btn--active, [aria-expanded=\"true\"]),",
            f"{header_buttons}:is(:hover, :focus-visible, .workspace-files-trigger--active, [aria-expanded=\"true\"]) {{",
            "  background: rgba(var(--v-theme-on-surface), 0.08) !important;",
            "  background-color: rgba(var(--v-theme-on-surface), 0.08) !important;",
            "}",
        ]
    )
