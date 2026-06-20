from __future__ import annotations

import re
from typing import Any

_ADVANCED_CSS_BLOCKED_AT_RULE = re.compile(r"@import\b", re.IGNORECASE)
_EXTERNAL_URL = re.compile(r"url\(\s*(['\"]?)(https?:|//)", re.IGNORECASE)


def build_theme_css(config: dict[str, Any]) -> str:
    """生成运行时 Dashboard 主题 CSS。"""

    enabled = "1" if config.get("enabled") is True else "0"
    background_fit = _css_value(config.get("background_fit"), "cover")
    background_position = _css_value(
        config.get("background_position"),
        "center center",
    )
    background_blur = _css_int(config.get("background_blur"), 0)
    background_dim = _css_float(config.get("background_dim"), 0.5)
    surface_opacity = _css_float(config.get("surface_opacity"), 0.0)
    text_enhancement_mode = _css_keyword(
        config.get("text_enhancement_mode"),
        {"off", "soft_shadow", "stroke"},
        "soft_shadow",
    )
    text_enhancement_strength = _css_float(
        config.get("text_enhancement_strength"),
        1.0,
    )
    background_grayscale = _css_float(config.get("background_grayscale"), 0.0)
    background_brightness = _css_ranged_float(
        config.get("background_brightness"),
        1.0,
        0.5,
        1.5,
    )
    background_contrast = _css_ranged_float(
        config.get("background_contrast"),
        1.0,
        0.5,
        1.5,
    )
    background_saturation = _css_ranged_float(
        config.get("background_saturation"),
        1.0,
        0.0,
        2.0,
    )
    background_inset = background_blur + 16 if background_blur > 0 else 0
    background_filter = _background_filter(
        background_blur,
        background_grayscale,
        background_brightness,
        background_contrast,
        background_saturation,
    )
    background_transform = "translateZ(0)" if background_blur > 0 else "none"
    text_effect = _text_effect_css(
        text_enhancement_mode,
        text_enhancement_strength,
    )
    icon_effect = _icon_effect_css(
        text_enhancement_mode,
        text_enhancement_strength,
    )

    return "\n".join(
        [
            "/* AstrBot调色盘 0.1.0 运行时主题 CSS */",
            ":root {",
            f"  --astrbot-palette-enabled: {enabled};",
            "  --astrbot-palette-background-image: none;",
            f"  --astrbot-palette-background-fit: {background_fit};",
            f"  --astrbot-palette-background-position: {background_position};",
            f"  --astrbot-palette-background-blur: {background_blur}px;",
            f"  --astrbot-palette-background-dim: {background_dim};",
            f"  --astrbot-palette-background-inset: {background_inset}px;",
            f"  --astrbot-palette-surface-opacity: {surface_opacity};",
            f"  --astrbot-palette-text-enhancement-strength: {text_enhancement_strength};",
            f"  --astrbot-palette-background-grayscale: {background_grayscale};",
            f"  --astrbot-palette-background-brightness: {background_brightness};",
            f"  --astrbot-palette-background-contrast: {background_contrast};",
            f"  --astrbot-palette-background-saturation: {background_saturation};",
            "}",
            "",
            "html.astrbot-palette-active,",
            "html.astrbot-palette-active body {",
            "  min-height: 100%;",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active body::before {",
            "  content: \"\";",
            "  position: fixed;",
            "  inset: calc(-1 * var(--astrbot-palette-background-inset, 0px));",
            "  z-index: 0;",
            "  pointer-events: none;",
            "  background-image: var(--astrbot-palette-background-image);",
            "  background-repeat: no-repeat;",
            "  background-position: var(--astrbot-palette-background-position, center center);",
            "  background-size: var(--astrbot-palette-background-fit, cover);",
            f"  filter: {background_filter};",
            f"  transform: {background_transform};",
            "}",
            "",
            "html.astrbot-palette-active body::after {",
            "  content: \"\";",
            "  position: fixed;",
            "  inset: 0;",
            "  z-index: 0;",
            "  pointer-events: none;",
            "  background: rgba(0, 0, 0, var(--astrbot-palette-background-dim, 0.5));",
            "}",
            "",
            "html.astrbot-palette-active #app {",
            "  position: relative;",
            "  z-index: 1;",
            "}",
            "",
            "html.astrbot-palette-active #app,",
            "html.astrbot-palette-active .v-application,",
            "html.astrbot-palette-active .v-application__wrap,",
            "html.astrbot-palette-active .v-main,",
            "html.astrbot-palette-active #app .page-wrapper,",
            "html.astrbot-palette-active #app .plugin-page-frame {",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .page-wrapper {",
            "  backdrop-filter: none !important;",
            "}",
            "",
            _surface_css(),
            "",
            _dashboard_shell_css(),
            "",
            _console_surface_css(),
            "",
            _page_specific_surface_css(),
            "",
            _settings_surface_css(),
            "",
            _extension_surface_css(),
            "",
            _config_dialog_surface_css(),
            "",
            _readability_css(text_effect, icon_effect),
            "",
            sanitize_advanced_css(config.get("advanced_css")),
            "",
        ]
    )


def sanitize_advanced_css(value: Any) -> str:
    """过滤会逃出本地 Dashboard 的高级 CSS。"""

    if not isinstance(value, str):
        return ""
    css = value[:20000]
    if _ADVANCED_CSS_BLOCKED_AT_RULE.search(css):
        return "/* AstrBot调色盘：已拦截 @import。 */"
    if _EXTERNAL_URL.search(css):
        return "/* AstrBot调色盘：已拦截外链 url()。 */"
    return css


def _surface_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    container = (
        "rgba(var(--v-theme-containerBg), "
        "var(--astrbot-palette-surface-opacity, 0))"
    )
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.24))"
    )
    hover = (
        "rgba(var(--v-theme-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.72))"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-navigation-drawer,",
            "html.astrbot-palette-active #app .v-app-bar.v-toolbar,",
            "html.astrbot-palette-active #app .v-main .bg-background,",
            "html.astrbot-palette-active #app .v-main .bg-surface,",
            "html.astrbot-palette-active #app .v-main .bg-containerBg,",
            "html.astrbot-palette-active #app .v-main .v-list,",
            "html.astrbot-palette-active #app .v-navigation-drawer .v-list,",
            "html.astrbot-palette-active #app .v-main .v-card:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info):not(.bg-darkprimary),",
            "html.astrbot-palette-active #app .v-main .v-sheet:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info):not(.bg-darkprimary),",
            "html.astrbot-palette-active #app .v-main .v-table:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info):not(.bg-darkprimary),",
            "html.astrbot-palette-active #app .v-main .v-field:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info):not(.bg-darkprimary),",
            "html.astrbot-palette-active #app .v-main .v-expansion-panels,",
            "html.astrbot-palette-active #app .v-main .v-expansion-panel,",
            "html.astrbot-palette-active #app .v-main .v-window,",
            "html.astrbot-palette-active #app .v-main .v-tabs,",
            "html.astrbot-palette-active #app .v-main .v-data-table,",
            "html.astrbot-palette-active #app .v-main .v-data-table__td,",
            "html.astrbot-palette-active #app .v-main .v-data-table__th,",
            "html.astrbot-palette-active #app .v-main .v-table__wrapper > table,",
            "html.astrbot-palette-active #app .v-main .v-table__wrapper > table > thead,",
            "html.astrbot-palette-active #app .v-main .v-table__wrapper > table > tbody,",
            "html.astrbot-palette-active #app .v-main .v-table__wrapper > table > tbody > tr,",
            "html.astrbot-palette-active #app .v-main .v-table__wrapper > table > tbody > tr > td,",
            "html.astrbot-palette-active #app .v-main .dashboard-card,",
            "html.astrbot-palette-active #app .v-main .welcome-card,",
            "html.astrbot-palette-active #app .v-main .chat-container,",
            "html.astrbot-palette-active #app .v-main .chat-ui,",
            "html.astrbot-palette-active #app .v-main .standalone-chat,",
            "html.astrbot-palette-active #app .v-main .chat-main,",
            "html.astrbot-palette-active #app .v-main .messages-panel,",
            "html.astrbot-palette-active #app .v-main .message-list-root,",
            "html.astrbot-palette-active #app .v-main .composer-shell,",
            "html.astrbot-palette-active #app .v-main .project-composer-shell,",
            "html.astrbot-palette-active #app .v-main .standalone-composer,",
            "html.astrbot-palette-active #app .v-main .console-page,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page,",
            "html.astrbot-palette-active #app .v-main .stats-page,",
            "html.astrbot-palette-active #app .v-main .trace-page,",
            "html.astrbot-palette-active #app .v-main .provider-page {",
            f"  background: {surface} !important;",
            "  backdrop-filter: none !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .page-wrapper,",
            "html.astrbot-palette-active #app .v-main .bg-containerBg {",
            f"  background: {container} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-app-bar .v-btn--icon:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info):not(.bg-darkprimary),",
            "html.astrbot-palette-active #app .v-navigation-drawer .v-btn:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info):not(.bg-darkprimary),",
            "html.astrbot-palette-active #app .v-main .v-list-item--active,",
            "html.astrbot-palette-active #app .v-navigation-drawer .v-list-item--active {",
            f"  background-color: {hover} !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .v-card--variant-outlined,",
            "html.astrbot-palette-active #app .v-main .v-field--variant-outlined,",
            "html.astrbot-palette-active #app .v-main .v-table {",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-chip,",
            "html.astrbot-palette-active #app .v-alert,",
            "html.astrbot-palette-active #app .bg-primary,",
            "html.astrbot-palette-active #app .bg-secondary,",
            "html.astrbot-palette-active #app .bg-success,",
            "html.astrbot-palette-active #app .bg-warning,",
            "html.astrbot-palette-active #app .bg-error,",
            "html.astrbot-palette-active #app .bg-info {",
            "  text-shadow: none !important;",
            "}",
        ]
    )


def _readability_css(text_effect: str, icon_effect: str) -> str:
    return "\n".join(
        [
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"soft_shadow\"] #app .v-main,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"soft_shadow\"] #app .v-navigation-drawer,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"soft_shadow\"] #app .v-app-bar,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"stroke\"] #app .v-main,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"stroke\"] #app .v-navigation-drawer,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"stroke\"] #app .v-app-bar {",
            f"  text-shadow: {text_effect};",
            "}",
            "",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"soft_shadow\"] #app .v-icon,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"stroke\"] #app .v-icon {",
            f"  filter: {icon_effect};",
            "}",
            "",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"off\"] #app .v-main,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"off\"] #app .v-navigation-drawer,",
            "html.astrbot-palette-active[data-astrbot-palette-text-mode=\"off\"] #app .v-app-bar,",
            "html.astrbot-palette-active #app .v-chip,",
            "html.astrbot-palette-active #app .v-alert,",
            "html.astrbot-palette-active #app .bg-primary,",
            "html.astrbot-palette-active #app .bg-secondary,",
            "html.astrbot-palette-active #app .bg-success,",
            "html.astrbot-palette-active #app .bg-warning,",
            "html.astrbot-palette-active #app .bg-error,",
            "html.astrbot-palette-active #app .bg-info {",
            "  text-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-chip .v-icon,",
            "html.astrbot-palette-active #app .v-alert .v-icon,",
            "html.astrbot-palette-active #app .bg-primary .v-icon,",
            "html.astrbot-palette-active #app .bg-secondary .v-icon,",
            "html.astrbot-palette-active #app .bg-success .v-icon,",
            "html.astrbot-palette-active #app .bg-warning .v-icon,",
            "html.astrbot-palette-active #app .bg-error .v-icon,",
            "html.astrbot-palette-active #app .bg-info .v-icon {",
            "  filter: none !important;",
            "}",
        ]
    )


def _dashboard_shell_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    primary_soft = (
        "rgba(var(--v-theme-primary), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.14))"
    )
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    border_strong = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.24))"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-main .dashboard-page {",
            "  --dashboard-bg: transparent;",
            f"  --dashboard-surface: {surface};",
            f"  --dashboard-border: {border};",
            f"  --dashboard-border-strong: {border_strong};",
            f"  --dashboard-soft: {primary_soft};",
            f"  --dashboard-soft-strong: {primary_soft};",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .dashboard-shell,",
            "html.astrbot-palette-active #app .v-main .dashboard-card,",
            "html.astrbot-palette-active #app .v-main .dashboard-pill,",
            "html.astrbot-palette-active #app .v-main .dashboard-dialog-card,",
            "html.astrbot-palette-active #app .v-main .setting-card,",
            "html.astrbot-palette-active #app .v-main .agent-panel,",
            "html.astrbot-palette-active #app .v-main .inner-card,",
            "html.astrbot-palette-active #app .v-main .selector-card,",
            "html.astrbot-palette-active #app .v-main .persona-preview-wrap,",
            "html.astrbot-palette-active #app .v-main .unsaved-banner,",
            "html.astrbot-palette-active #app .v-main .empty-card {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .dashboard-card-icon {",
            f"  background: {primary_soft} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .dashboard-header,",
            "html.astrbot-palette-active #app .v-main .dashboard-section-head {",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .dashboard-dialog-card {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
        ]
    )


def _console_surface_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-main .console-displayer-wrapper,",
            "html.astrbot-palette-active #app .v-main .console-term,",
            "html.astrbot-palette-active #app .v-main #console-wrapper,",
            "html.astrbot-palette-active #app .v-main [style*=\"background-color: #1e1e1e\"],",
            "html.astrbot-palette-active #app .v-main [style*=\"background-color:#1e1e1e\"],",
            "html.astrbot-palette-active #app .v-main [style*=\"background: #1e1e1e\"],",
            "html.astrbot-palette-active #app .v-main [style*=\"background:#1e1e1e\"] {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #console-wrapper:fullscreen,",
            "html.astrbot-palette-active #console-wrapper:fullscreen::backdrop {",
            f"  background: {surface} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .command-suggestion-panel,",
            "html.astrbot-palette-active #app .v-main .command-suggestion-panel.is-dark {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            f"  border-color: {border} !important;",
            "}",
        ]
    )


def _page_specific_surface_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    primary_soft = (
        "rgba(var(--v-theme-primary), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.12))"
    )
    neutral_soft = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.08))"
    )
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-main .provider-workbench,",
            "html.astrbot-palette-active #app .v-main .provider-workbench__sidebar,",
            "html.astrbot-palette-active #app .v-main .provider-workbench__main,",
            "html.astrbot-palette-active #app .v-main .provider-config-shell,",
            "html.astrbot-palette-active #app .v-main .provider-config-header,",
            "html.astrbot-palette-active #app .v-main .provider-config-body,",
            "html.astrbot-palette-active #app .v-main .provider-section,",
            "html.astrbot-palette-active #app .v-main .provider-sources-panel,",
            "html.astrbot-palette-active #app .v-main .provider-sources-list,",
            "html.astrbot-palette-active #app .v-main .provider-sources-empty,",
            "html.astrbot-palette-active #app .v-main .provider-source-item,",
            "html.astrbot-palette-active #app .v-main .provider-empty-state,",
            "html.astrbot-palette-active #app .v-main .provider-chat-panel,",
            "html.astrbot-palette-active #app .v-main .provider-drawer-card,",
            "html.astrbot-palette-active #app .v-main .provider-drawer-header,",
            "html.astrbot-palette-active #app .v-main .provider-drawer-content,",
            "html.astrbot-palette-active #app .v-main .platform-page .traceback-box,",
            "html.astrbot-palette-active #app .v-main .stats-page .stat-card,",
            "html.astrbot-palette-active #app .v-main .stats-page .chart-card,",
            "html.astrbot-palette-active #app .v-main .stats-page .provider-row,",
            "html.astrbot-palette-active #app .v-main .trace-page .v-card,",
            "html.astrbot-palette-active #app .v-main .trace-page .trace-displayer,",
            "html.astrbot-palette-active #app .v-main .trace-page .trace-event,",
            "html.astrbot-palette-active #app .v-main .settings-page .v-card,",
            "html.astrbot-palette-active #app .v-main .config-page .v-card,",
            "html.astrbot-palette-active #app .v-main .config-container,",
            "html.astrbot-palette-active #app .v-main .config-section,",
            "html.astrbot-palette-active #app .v-main .config-item,",
            "html.astrbot-palette-active #app .v-main .config-item-wrapper,",
            "html.astrbot-palette-active #app .v-main .array-item,",
            "html.astrbot-palette-active #app .v-main .object-item,",
            "html.astrbot-palette-active #app .v-main .session-management-page .v-card,",
            "html.astrbot-palette-active #app .v-main .kb-detail-page,",
            "html.astrbot-palette-active #app .v-main .knowledge-base-page .v-card,",
            "html.astrbot-palette-active #app .v-main .persona-manager .v-card {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .provider-workbench__divider,",
            "html.astrbot-palette-active #app .v-main .v-divider {",
            f"  background: {border} !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .provider-source-item--active,",
            "html.astrbot-palette-active #app .v-main .provider-source-item:hover,",
            "html.astrbot-palette-active #app .v-main .stats-page .provider-row:hover,",
            "html.astrbot-palette-active #app .v-main .trace-page .trace-event--active,",
            "html.astrbot-palette-active #app .v-main .chat-sidebar .conversation-item--active,",
            "html.astrbot-palette-active #app .v-main .chat-sidebar .conversation-item:hover {",
            f"  background: {primary_soft} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .standalone-composer::before {",
            "  background: linear-gradient(",
            "    180deg,",
            "    rgba(var(--v-theme-background), 0),",
            "    rgba(var(--v-theme-background), var(--astrbot-palette-surface-opacity, 0))",
            "  ) !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .docs-markdown pre,",
            "html.astrbot-palette-active #app .v-main .docs-markdown code,",
            "html.astrbot-palette-active #app .v-main .command-cell code,",
            "html.astrbot-palette-active #app .v-main .persona-preview-wrap .preview-card,",
            "html.astrbot-palette-active #app .v-main .storage-cleanup-panel,",
            "html.astrbot-palette-active #app .v-main .template-list-editor,",
            "html.astrbot-palette-active #app .v-main .object-editor,",
            "html.astrbot-palette-active #app .v-main .config-item-card,",
            "html.astrbot-palette-active #app .v-main .list-config-item {",
            f"  background: {neutral_soft} !important;",
            "  box-shadow: none !important;",
            "}",
        ]
    )


def _settings_surface_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    primary_soft = (
        "rgba(var(--v-theme-primary), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.12))"
    )
    neutral_soft = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.08))"
    )
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    divider = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.14))"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-main .settings-page {",
            "  --settings-border: "
            "rgba(var(--v-theme-on-surface), "
            "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18));",
            "  --settings-divider: "
            "rgba(var(--v-theme-on-surface), "
            "calc(var(--astrbot-palette-surface-opacity, 0) * 0.14));",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-list-card,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-item,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .v-card,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .config-section,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .config-row,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .property-info .v-list-item,",
            "html.astrbot-palette-active #app .v-main .settings-page .api-key-panel,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap .v-table,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap table,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap thead,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap tbody,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap tr,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap th,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap td,",
            "html.astrbot-palette-active #app .v-main .settings-page .storage-cleanup-panel,",
            "html.astrbot-palette-active #app .v-main .settings-page .storage-cleanup-card {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-item,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .config-divider,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .collapsed-config-toggle-row,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap th,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-table-wrap td {",
            f"  border-color: {divider} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-nav__item:hover,",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-nav__item--active,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .config-row:hover,",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-group .collapsed-config-toggle-row,",
            "html.astrbot-palette-active #app .v-main .settings-page .api-key-name-cell code,",
            "html.astrbot-palette-active #app .v-main .settings-page .storage-cleanup-chip,",
            "html.astrbot-palette-active #app .v-main .settings-page .storage-cleanup-action {",
            f"  background: {neutral_soft} !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-nav__item--active::before {",
            "  background: "
            "rgba(var(--v-theme-on-surface), "
            "calc(var(--astrbot-palette-surface-opacity, 0) * 0.52)) !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-restart-bar {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            f"  border: 1px solid {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .settings-page .system-config-restart-bar__button {",
            f"  background: {neutral_soft} !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .settings-page .api-key-panel .v-chip:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info),",
            "html.astrbot-palette-active #app .v-main .settings-page .api-key-panel .v-btn:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info),",
            "html.astrbot-palette-active #app .v-main .settings-page .settings-item__control .v-btn:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info) {",
            f"  background: {primary_soft} !important;",
            "  box-shadow: none !important;",
            f"  border-color: {border} !important;",
            "}",
        ]
    )


def _extension_surface_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    mcp_surface = "rgba(var(--v-theme-mcpCardBg), var(--astrbot-palette-surface-opacity, 0))"
    hover = (
        "rgba(var(--v-theme-primary), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.12))"
    )
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-main .extension-page,",
            "html.astrbot-palette-active #app .v-main .extension-page .v-card,",
            "html.astrbot-palette-active #app .v-main .extension-detail-width,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .detail-header--stuck::before,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .plugin-summary-card,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .handler-card,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .handler-card .v-table,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .handler-card tbody,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .handler-card tr,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .handler-card td,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .docs-card,",
            "html.astrbot-palette-active #app .v-main .plugin-page-page,",
            "html.astrbot-palette-active #app .v-main .plugin-page-state,",
            "html.astrbot-palette-active #app .v-main .plugin-page-frame,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-card-text,",
            "html.astrbot-palette-active #app .v-main .extension-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-handler-item,",
            "html.astrbot-palette-active #app .v-main .outlined-action-list-item,",
            "html.astrbot-palette-active #app .v-main .mcp-server-card,",
            "html.astrbot-palette-active #app .v-main .skill-card,",
            "html.astrbot-palette-active #app .v-main .component-panel,",
            "html.astrbot-palette-active #app .v-main .component-card,",
            "html.astrbot-palette-active #app .v-main .skills-section,",
            "html.astrbot-palette-active #app .v-main .skills-page,",
            "html.astrbot-palette-active #app .v-main .skills-toolbar,",
            "html.astrbot-palette-active #app .v-main .skills-list,",
            "html.astrbot-palette-active #app .v-main .skills-card,",
            "html.astrbot-palette-active #app .v-main .skill-card__body,",
            "html.astrbot-palette-active #app .v-main .mcp-servers-section,",
            "html.astrbot-palette-active #app .v-main .mcp-section-card {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main [style*=\"rgb(var(--v-theme-mcpCardBg))\"] {",
            f"  background: {mcp_surface} !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-card:hover,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card:hover,",
            "html.astrbot-palette-active #app .v-main .outlined-action-list-item:hover {",
            f"  background: {hover} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .docs-markdown th,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .docs-markdown pre,",
            "html.astrbot-palette-active #app .v-main .plugin-detail-page .docs-markdown code,",
            "html.astrbot-palette-active #app .v-main .market-install-source,",
            "html.astrbot-palette-active #app .v-main .plugin-platform-chip,",
            "html.astrbot-palette-active #app .v-main .mcp-server-card .v-list,",
            "html.astrbot-palette-active #app .v-main .skills-section .payload-preview,",
            "html.astrbot-palette-active #app .v-main .skills-section .skill-payload,",
            "html.astrbot-palette-active #app .v-main .skills-section .code-block {",
            f"  background: {hover} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-page [style*=\"background-color: rgb(var(--v-theme-background))\"],",
            "html.astrbot-palette-active #app .v-main .extension-page [style*=\"background-color:rgb(var(--v-theme-background))\"],",
            "html.astrbot-palette-active #app .v-main .extension-page [style*=\"background: rgb(var(--v-theme-surface))\"],",
            "html.astrbot-palette-active #app .v-main .extension-page [style*=\"background:rgb(var(--v-theme-surface))\"] {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "}",
        ]
    )


def _config_dialog_surface_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    neutral_soft = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.08))"
    )
    primary_soft = (
        "rgba(var(--v-theme-primary), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.12))"
    )
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.object-config),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.simple-config),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .v-card-actions,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .config-section,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .object-config,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .simple-config,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .config-item,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .config-row,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .nested-container,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .selected-plugins-full-width {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .config-row:hover,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .collapsed-config-toggle-row,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .plugin-set-display-row,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .persona-preview-row {",
            f"  background: {neutral_soft} !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .selected-plugins-full-width,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) .editor-fullscreen-btn {",
            f"  background: {primary_soft} !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) [style*=\"background-color: rgb(var(--v-theme-background))\"],",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) [style*=\"background-color:rgb(var(--v-theme-background))\"],",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) [style*=\"background: rgb(var(--v-theme-surface))\"],",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.config-section) [style*=\"background:rgb(var(--v-theme-surface))\"] {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "}",
        ]
    )


def _background_filter(
    background_blur: int,
    grayscale: float,
    brightness: float,
    contrast: float,
    saturation: float,
) -> str:
    filters: list[str] = []
    if background_blur > 0:
        filters.append(f"blur({background_blur}px)")
    if grayscale > 0:
        filters.append(f"grayscale({_css_number(grayscale)})")
    if brightness != 1.0:
        filters.append(f"brightness({_css_number(brightness)})")
    if contrast != 1.0:
        filters.append(f"contrast({_css_number(contrast)})")
    if saturation != 1.0:
        filters.append(f"saturate({_css_number(saturation)})")
    return " ".join(filters) if filters else "none"


def _text_effect_css(mode: str, strength: float) -> str:
    if mode == "off" or strength <= 0:
        return "none"
    if mode == "stroke":
        dark_alpha = 0.16 + 0.44 * strength
        light_alpha = 0.08 + 0.16 * strength
        return (
            f"0 1px 2px rgba(0, 0, 0, {_css_number(dark_alpha)}), "
            f"0 -1px 1px rgba(255, 255, 255, {_css_number(light_alpha)}), "
            f"1px 0 1px rgba(0, 0, 0, {_css_number(dark_alpha)}), "
            f"-1px 0 1px rgba(0, 0, 0, {_css_number(dark_alpha)})"
        )

    dark_alpha = 0.12 + 0.26 * strength
    light_alpha = 0.06 + 0.14 * strength
    blur = 1 + round(4 * strength, 2)
    return (
        f"0 1px {blur}px rgba(0, 0, 0, {_css_number(dark_alpha)}), "
        f"0 -1px {blur}px rgba(255, 255, 255, {_css_number(light_alpha)})"
    )


def _icon_effect_css(mode: str, strength: float) -> str:
    if mode == "off" or strength <= 0:
        return "none"
    if mode == "stroke":
        dark_alpha = 0.18 + 0.42 * strength
        light_alpha = 0.08 + 0.16 * strength
        blur = 1
    else:
        dark_alpha = 0.12 + 0.28 * strength
        light_alpha = 0.04 + 0.12 * strength
        blur = 2
    return (
        f"drop-shadow(0 1px {blur}px rgba(0, 0, 0, {_css_number(dark_alpha)})) "
        f"drop-shadow(0 -1px {blur}px rgba(255, 255, 255, {_css_number(light_alpha)}))"
    )


def _css_value(value: Any, default: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    cleaned = value.replace("\n", " ").replace("\r", " ").strip()
    if any(char in cleaned for char in "{};"):
        return default
    return cleaned


def _css_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(value, 0)
    return default


def _css_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return min(max(float(value), 0.0), 1.0)
    return default


def _css_ranged_float(
    value: Any,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return min(max(float(value), minimum), maximum)
    return default


def _css_keyword(value: Any, allowed: set[str], default: str) -> str:
    if not isinstance(value, str):
        return default
    cleaned = value.strip()
    return cleaned if cleaned in allowed else default


def _css_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")
