from __future__ import annotations

import re
from typing import Any

_ADVANCED_CSS_BLOCKED_AT_RULE = re.compile(r"@import\b", re.IGNORECASE)
_EXTERNAL_URL = re.compile(r"url\(\s*(['\"]?)(https?:|//)", re.IGNORECASE)


def build_theme_css(config: dict[str, Any]) -> str:
    """生成运行时 Dashboard 主题 CSS。"""

    enabled = "1" if config.get("enabled") is True else "0"
    background_fit = _background_fit_value(config.get("background_fit"))
    background_position = _css_value(
        config.get("background_position"),
        "center center",
    )
    background_blur = _css_int(config.get("background_blur"), 0)
    background_dim = _css_float(config.get("background_dim"), 0.5)
    surface_opacity = _css_float(config.get("surface_opacity"), 0.0)
    stats_card_blur = _css_int(config.get("stats_card_blur"), 14)
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
            "/* AstrBot调色盘 0.4.8 运行时主题 CSS */",
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
            "html.astrbot-palette-active {",
            "  min-height: 100%;",
            "  background-color: transparent !important;",
            "  background-image: none !important;",
            "  background-attachment: fixed !important;",
            "}",
            "",
            "html.astrbot-palette-active body {",
            "  min-height: 100%;",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active #astrbot-palette-background {",
            "  position: fixed;",
            "  inset: 0;",
            "  z-index: 0;",
            "  pointer-events: none;",
            "  overflow: hidden;",
            "}",
            "",
            "html.astrbot-palette-active #astrbot-palette-background .astrbot-palette-background-layer {",
            "  content: \"\";",
            "  position: fixed;",
            "  left: calc(-1 * var(--astrbot-palette-background-inset, 0px));",
            "  top: calc(-1 * var(--astrbot-palette-background-inset, 0px));",
            "  width: calc(100vw + (2 * var(--astrbot-palette-background-inset, 0px)));",
            "  height: calc(100vh + (2 * var(--astrbot-palette-background-inset, 0px)));",
            "  z-index: 0;",
            "  pointer-events: none;",
            "  opacity: 0;",
            "  background-image: none;",
            "  background-repeat: no-repeat;",
            "  background-position: var(--astrbot-palette-background-position, center center);",
            "  background-size: var(--astrbot-palette-background-fit, cover);",
            f"  filter: {background_filter};",
            f"  transform: {background_transform};",
            "  transition: opacity 650ms cubic-bezier(0.22, 1, 0.36, 1);",
            "  will-change: opacity;",
            "}",
            "",
            "html.astrbot-palette-active #astrbot-palette-background .astrbot-palette-background-layer.is-active {",
            "  opacity: 1;",
            "}",
            "",
            "html.astrbot-palette-active body::before {",
            "  content: none !important;",
            "}",
            "",
            "html.astrbot-palette-active body::after {",
            "  content: \"\";",
            "  position: fixed;",
            "  inset: 0;",
            "  width: 100vw;",
            "  height: 100vh;",
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
            _floating_scrollbar_css(),
            "",
            _surface_css(),
            "",
            _top_header_css(),
            "",
            _tabs_readability_css(),
            "",
            _dashboard_shell_css(),
            "",
            _console_surface_css(),
            "",
            _page_specific_surface_css(),
            "",
            _token_stats_detail_css(),
            "",
            _config_tabs_css(),
            "",
            _settings_surface_css(),
            "",
            _extension_surface_css(),
            "",
            _stats_highlight_css(stats_card_blur),
            "",
            _config_dialog_surface_css(),
            "",
            _platform_dialog_surface_css(),
            "",
            _extension_dialog_surface_css(stats_card_blur),
            "",
            _extension_loading_dialog_css(),
            "",
            _astrbot_update_dialog_surface_css(),
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


def _floating_scrollbar_css() -> str:
    thumb = (
        "rgba(var(--v-theme-primary), "
        "calc(0.42 + var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    thumb_hover = (
        "rgba(var(--v-theme-primary), "
        "calc(0.62 + var(--astrbot-palette-surface-opacity, 0) * 0.16))"
    )
    thumb_active = "rgba(var(--v-theme-primary), 0.86)"
    thumb_shadow = "rgba(var(--v-theme-primary), 0.22)"
    return "\n".join(
        [
            "html.astrbot-palette-active {",
            "  --astrbot-scrollbar-track: transparent;",
            f"  --astrbot-scrollbar-thumb: {thumb};",
            f"  --astrbot-scrollbar-thumb-hover: {thumb_hover};",
            f"  --astrbot-scrollbar-thumb-active: {thumb_active};",
            "  --astrbot-scrollbar-thumb-border: transparent;",
            f"  --astrbot-scrollbar-thumb-shadow: {thumb_shadow};",
            "  scrollbar-color: var(--astrbot-scrollbar-thumb) transparent;",
            "  scrollbar-gutter: auto;",
            "}",
            "",
            "html.astrbot-palette-active,",
            "html.astrbot-palette-active body,",
            "html.astrbot-palette-active #app,",
            "html.astrbot-palette-active #app .v-application,",
            "html.astrbot-palette-active #app .v-application__wrap,",
            "html.astrbot-palette-active #app .v-main,",
            "html.astrbot-palette-active #app .page-wrapper,",
            "html.astrbot-palette-active #app .v-navigation-drawer,",
            "html.astrbot-palette-active #app .v-overlay-container,",
            "html.astrbot-palette-active .v-overlay-container {",
            "  scrollbar-color: var(--astrbot-scrollbar-thumb) transparent !important;",
            "  scrollbar-gutter: auto !important;",
            "}",
            "",
            "html.astrbot-palette-active * {",
            "  scrollbar-color: var(--astrbot-scrollbar-thumb) transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active::-webkit-scrollbar,",
            "html.astrbot-palette-active *::-webkit-scrollbar {",
            "  width: 8px !important;",
            "  height: 8px !important;",
            "  background: transparent !important;",
            "  border: 0 !important;",
            "}",
            "",
            "html.astrbot-palette-active::-webkit-scrollbar-track,",
            "html.astrbot-palette-active::-webkit-scrollbar-track-piece,",
            "html.astrbot-palette-active::-webkit-scrollbar-corner,",
            "html.astrbot-palette-active *::-webkit-scrollbar-track,",
            "html.astrbot-palette-active *::-webkit-scrollbar-track-piece,",
            "html.astrbot-palette-active *::-webkit-scrollbar-corner {",
            "  background: transparent !important;",
            "  border: 0 !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active::-webkit-scrollbar-thumb,",
            "html.astrbot-palette-active *::-webkit-scrollbar-thumb {",
            "  background-color: var(--astrbot-scrollbar-thumb) !important;",
            "  background-clip: border-box !important;",
            "  border: 0 !important;",
            "  border-radius: 999px !important;",
            "  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.16) !important;",
            "  min-height: 48px !important;",
            "}",
            "",
            "html.astrbot-palette-active::-webkit-scrollbar-thumb:hover,",
            "html.astrbot-palette-active *::-webkit-scrollbar-thumb:hover {",
            "  background-color: var(--astrbot-scrollbar-thumb-hover) !important;",
            "  box-shadow: 0 0 8px var(--astrbot-scrollbar-thumb-shadow) !important;",
            "}",
            "",
            "html.astrbot-palette-active::-webkit-scrollbar-thumb:active,",
            "html.astrbot-palette-active *::-webkit-scrollbar-thumb:active {",
            "  background-color: var(--astrbot-scrollbar-thumb-active) !important;",
            "}",
            "",
            "html.astrbot-palette-active .hidden-scrollbar,",
            "html.astrbot-palette-active .hidden-scrollbar * {",
            "  scrollbar-width: none !important;",
            "}",
            "",
            "html.astrbot-palette-active .hidden-scrollbar::-webkit-scrollbar,",
            "html.astrbot-palette-active .hidden-scrollbar *::-webkit-scrollbar {",
            "  display: none !important;",
            "}",
        ]
    )


def _top_header_css() -> str:
    return "\n".join(
        [
            "html.astrbot-palette-active #app .top-header,",
            "html.astrbot-palette-active #app .v-app-bar.top-header,",
            "html.astrbot-palette-active #app .v-app-bar.v-toolbar.top-header {",
            "  background: transparent !important;",
            "  border-bottom: 0 !important;",
            "  box-shadow: none !important;",
            "  outline: 0 !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .top-header::before,",
            "html.astrbot-palette-active #app .top-header::after,",
            "html.astrbot-palette-active #app .v-app-bar.top-header::before,",
            "html.astrbot-palette-active #app .v-app-bar.top-header::after {",
            "  background: transparent !important;",
            "  border: 0 !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .top-header .v-toolbar__content {",
            "  border-bottom: 0 !important;",
            "  box-shadow: none !important;",
            "  outline: 0 !important;",
            "}",
        ]
    )


def _tabs_readability_css() -> str:
    tab_shadow = (
        "0 1px 4px rgba(0, 0, 0, 0.44), "
        "0 -1px 4px rgba(255, 255, 255, 0.18)"
    )
    primary_soft = "rgba(var(--v-theme-primary), 0.12)"
    primary_border = "rgba(var(--v-theme-primary), 0.58)"
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-main .v-tabs,",
            "html.astrbot-palette-active #app .v-main .v-tabs.v-slide-group,",
            "html.astrbot-palette-active #app .v-main .v-tabs .v-slide-group,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs.v-slide-group,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs .v-slide-group {",
            "  background: transparent !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .v-tabs .v-btn.v-tab,",
            "html.astrbot-palette-active #app .v-main .v-tab,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs .v-btn.v-tab,",
            "html.astrbot-palette-active .v-overlay-container .v-tab {",
            "  background: transparent !important;",
            "  border: 1px solid transparent !important;",
            "  border-radius: 0 !important;",
            "  box-shadow: none !important;",
            "  color: rgb(var(--v-theme-on-surface)) !important;",
            "  margin-inline: 2px !important;",
            "  opacity: 0.88 !important;",
            f"  text-shadow: {tab_shadow} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .v-tabs .v-btn.v-tab:hover,",
            "html.astrbot-palette-active #app .v-main .v-tab:hover,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs .v-btn.v-tab:hover,",
            "html.astrbot-palette-active .v-overlay-container .v-tab:hover {",
            "  background: transparent !important;",
            "  border-color: transparent !important;",
            f"  border-bottom-color: {primary_border} !important;",
            "  color: rgb(var(--v-theme-primary)) !important;",
            "  opacity: 1 !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .v-tabs .v-btn.v-tab.v-tab--selected,",
            "html.astrbot-palette-active #app .v-main .v-tab.v-tab--selected,",
            "html.astrbot-palette-active #app .v-main .v-tabs .v-btn.v-tab.v-btn--active,",
            "html.astrbot-palette-active #app .v-main .v-tab.v-btn--active,",
            "html.astrbot-palette-active #app .v-main .v-tabs .v-btn.v-tab.v-slide-group-item--active,",
            "html.astrbot-palette-active #app .v-main .v-tab.v-slide-group-item--active,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs .v-btn.v-tab.v-tab--selected,",
            "html.astrbot-palette-active .v-overlay-container .v-tab.v-tab--selected,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs .v-btn.v-tab.v-btn--active,",
            "html.astrbot-palette-active .v-overlay-container .v-tab.v-btn--active,",
            "html.astrbot-palette-active .v-overlay-container .v-tabs .v-btn.v-tab.v-slide-group-item--active,",
            "html.astrbot-palette-active .v-overlay-container .v-tab.v-slide-group-item--active {",
            "  background: linear-gradient(to bottom, transparent calc(100% - 3px), "
            f"{primary_soft} calc(100% - 3px)) !important;",
            "  border-color: transparent !important;",
            f"  border-bottom-color: {primary_border} !important;",
            "  color: rgb(var(--v-theme-primary)) !important;",
            "  opacity: 1 !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .v-tab__slider,",
            "html.astrbot-palette-active .v-overlay-container .v-tab__slider {",
            "  background: rgb(var(--v-theme-primary)) !important;",
            "  border-radius: 999px !important;",
            "  box-shadow: 0 0 8px rgba(var(--v-theme-primary), 0.45) !important;",
            "  height: 3px !important;",
            "}",
        ]
    )


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
            "html.astrbot-palette-active #app .v-main .composer-shell::before,",
            "html.astrbot-palette-active #app .v-main .project-composer-shell::before,",
            "html.astrbot-palette-active #app .v-main .standalone-composer::before {",
            "  background: transparent !important;",
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


def _stats_highlight_css(stats_card_blur: int) -> str:
    blur = max(0, min(40, stats_card_blur))
    surface = (
        "rgba(var(--v-theme-surface), "
        "calc(0.42 + var(--astrbot-palette-surface-opacity, 0) * 0.32))"
    )
    surface_strong = (
        "rgba(var(--v-theme-surface), "
        "calc(0.54 + var(--astrbot-palette-surface-opacity, 0) * 0.28))"
    )
    config_outer_surface = (
        "rgba(var(--v-theme-surface), "
        "calc(0.18 + var(--astrbot-palette-surface-opacity, 0) * 0.16))"
    )
    config_shell_surface = (
        "rgba(var(--v-theme-surface), "
        "calc(0.20 + var(--astrbot-palette-surface-opacity, 0) * 0.18))"
    )
    config_row_surface = (
        "rgba(var(--v-theme-surface), "
        "calc(0.30 + var(--astrbot-palette-surface-opacity, 0) * 0.22))"
    )
    primary_soft = (
        "rgba(var(--v-theme-primary), "
        "calc(0.14 + var(--astrbot-palette-surface-opacity, 0) * 0.12))"
    )
    primary_ring = "rgba(var(--v-theme-primary), 0.34)"
    border = (
        "rgba(var(--v-theme-on-surface), "
        "calc(0.20 + var(--astrbot-palette-surface-opacity, 0) * 0.12))"
    )
    text = "rgb(var(--v-theme-on-surface))"
    muted = "rgba(var(--v-theme-on-surface), 0.78)"
    subtle = "rgba(var(--v-theme-on-surface), 0.66)"
    shadow = (
        "0 16px 36px rgba(0, 0, 0, 0.26), "
        "inset 0 1px 0 rgba(255, 255, 255, 0.12)"
    )
    hover_shadow = (
        "0 20px 44px rgba(0, 0, 0, 0.32), "
        "0 0 0 1px rgba(var(--v-theme-primary), 0.22), "
        "inset 0 1px 0 rgba(255, 255, 255, 0.16)"
    )
    return "\n".join(
        [
            "html.astrbot-palette-active #app .v-main .platform-page,",
            "html.astrbot-palette-active #app .v-main .provider-page,",
            "html.astrbot-palette-active #app .v-main .extension-page,",
            "html.astrbot-palette-active #app .v-main .config-page,",
            "html.astrbot-palette-active #app .v-main .stats-page {",
            "  --stats-bg: transparent !important;",
            f"  --stats-surface: {surface} !important;",
            f"  --stats-text: {text} !important;",
            f"  --stats-muted: {muted} !important;",
            f"  --stats-subtle: {subtle} !important;",
            f"  --stats-border: {border} !important;",
            f"  --stats-border-strong: {primary_ring} !important;",
            f"  --stats-soft: {primary_soft} !important;",
            f"  --stats-soft-strong: {primary_soft} !important;",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .platform-page .item-card,",
            "html.astrbot-palette-active #app .v-main .platform-page .v-card:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info),",
            "html.astrbot-palette-active #app .v-main .platform-page .console-displayer-wrapper,",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper,",
            "html.astrbot-palette-active #app .v-main .platform-page .console-term,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-workbench,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-sources-panel,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-source-item,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-config-shell,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-section,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-chat-panel,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-empty-state,",
            "html.astrbot-palette-active #app .v-main .extension-page .extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-card,",
            "html.astrbot-palette-active #app .v-main .v-card.extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-card-text,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-page .plugin-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .plugin-card,",
            "html.astrbot-palette-active #app .v-main .v-card.plugin-card,",
            "html.astrbot-palette-active #app .v-main .plugin-card .plugin-card-content,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-page .neo-table-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .neo-filter-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-filter-control,",
            "html.astrbot-palette-active #app .v-main .extension-page .plugin-summary-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .handler-card,",
            "html.astrbot-palette-active #app .v-main .config-page .config-panel,",
            "html.astrbot-palette-active #app .v-main .config-panel,",
            "html.astrbot-palette-active #app .v-main .config-page .config-toolbar,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-toolbar,",
            "html.astrbot-palette-active #app .v-main .config-page .config-section,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-section,",
            "html.astrbot-palette-active #app .v-main .config-page .config-row,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-row,",
            "html.astrbot-palette-active #app .v-main .config-page .config-item,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item,",
            "html.astrbot-palette-active #app .v-main .config-page .config-item-wrapper,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item-wrapper,",
            "html.astrbot-palette-active #app .v-main .config-page .config-tabs-window,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs-window,",
            "html.astrbot-palette-active #app .v-main .config-panel .v-window,",
            "html.astrbot-palette-active #app .v-main .config-panel .v-window-item,",
            "html.astrbot-palette-active #app .v-main .config-panel .v-field,",
            "html.astrbot-palette-active #app .v-main .stats-page .meta-pill,",
            "html.astrbot-palette-active #app .v-main .stats-page .range-switch,",
            "html.astrbot-palette-active #app .v-main .stats-page .stat-card {",
            f"  background: {surface} !important;",
            f"  background-color: {surface} !important;",
            f"  border-color: {border} !important;",
            f"  box-shadow: {shadow} !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions {",
            "  border-top: 0 !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .platform-page .item-card,",
            "html.astrbot-palette-active #app .v-main .platform-page .console-term,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-source-item,",
            "html.astrbot-palette-active #app .v-main .extension-page .extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-page .plugin-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .plugin-card,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .config-page .config-section,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-section,",
            "html.astrbot-palette-active #app .v-main .config-page .config-row,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-row,",
            "html.astrbot-palette-active #app .v-main .stats-page .overview-card {",
            f"  background: {surface_strong} !important;",
            f"  background-color: {surface_strong} !important;",
            f"  border-color: {primary_ring} !important;",
            "  position: relative;",
            "  overflow: hidden;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-toolbar,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-toolbar {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  border-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-panel > .config-content,",
            "html.astrbot-palette-active #app .v-main .config-panel > .config-content > div,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-slide-group__container,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-slide-group__content,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs-window,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs-window > .v-window__container,",
            "html.astrbot-palette-active #app .v-main .config-panel .v-tabs-window-item {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  background-image: none !important;",
            "  border: 0 !important;",
            "  border-radius: 0 !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-panel > .config-content::before,",
            "html.astrbot-palette-active #app .v-main .config-panel > .config-content::after,",
            "html.astrbot-palette-active #app .v-main .config-panel > .config-content > div::before,",
            "html.astrbot-palette-active #app .v-main .config-panel > .config-content > div::after {",
            "  content: none !important;",
            "  display: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-panel,",
            "html.astrbot-palette-active #app .v-main .mt-4.config-panel,",
            "html.astrbot-palette-active #app .v-main .config-panel {",
            f"  background: {config_outer_surface} !important;",
            f"  background-color: {config_outer_surface} !important;",
            "  border: 1px solid rgba(var(--v-theme-on-surface), 0.16) !important;",
            "  border-radius: 24px !important;",
            "  box-shadow: 0 20px 54px rgba(0, 0, 0, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.10) !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "  background-clip: padding-box !important;",
            "  padding: 18px !important;",
            "  overflow: hidden !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-tabs-window,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs-window,",
            "html.astrbot-palette-active #app .v-main .config-panel .v-window,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-tabs-window > .v-window__container,",
            "html.astrbot-palette-active #app .v-main .config-panel .v-window-item,",
            "html.astrbot-palette-active #app .v-main .config-panel .v-tabs-window-item {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  border-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "  overflow: visible !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-section,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-section {",
            f"  background: {config_shell_surface} !important;",
            f"  background-color: {config_shell_surface} !important;",
            "  border: 1px solid rgba(var(--v-theme-on-surface), 0.16) !important;",
            "  border-radius: 18px !important;",
            "  box-shadow: 0 18px 46px rgba(0, 0, 0, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.10) !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "  margin: 18px 0 28px !important;",
            "  padding: 14px 18px !important;",
            "  overflow: visible !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-row,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-row {",
            f"  background: {config_row_surface} !important;",
            f"  background-color: {config_row_surface} !important;",
            "  border: 1px solid rgba(var(--v-theme-on-surface), 0.15) !important;",
            "  border-radius: 14px !important;",
            "  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.09) !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "  margin: 10px 0 !important;",
            "  overflow: hidden !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-item,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item,",
            "html.astrbot-palette-active #app .v-main .config-page .config-item-wrapper,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item-wrapper {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  border-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-toolbar::before,",
            "html.astrbot-palette-active #app .v-main .config-page .config-toolbar::after,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-toolbar::before,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-toolbar::after,",
            "html.astrbot-palette-active #app .v-main .config-page .config-item::before,",
            "html.astrbot-palette-active #app .v-main .config-page .config-item::after,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item::before,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item::after,",
            "html.astrbot-palette-active #app .v-main .config-page .config-item-wrapper::before,",
            "html.astrbot-palette-active #app .v-main .config-page .config-item-wrapper::after,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item-wrapper::before,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-item-wrapper::after {",
            "  content: none !important;",
            "  display: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .config-page .config-row::before,",
            "html.astrbot-palette-active #app .v-main .config-page .config-row::after,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-row::before,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-row::after {",
            "  display: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .stats-page .overview-card::before {",
            "  content: \"\";",
            "  position: absolute;",
            "  inset: 0;",
            "  pointer-events: none;",
            "  border-radius: inherit;",
            "  background: linear-gradient(135deg, rgba(255, 255, 255, 0.14), transparent 44%);",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .stats-page .overview-card > * {",
            "  position: relative;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .platform-page .item-card:hover,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-source-item:hover,",
            "html.astrbot-palette-active #app .v-main .extension-page .extension-card:hover,",
            "html.astrbot-palette-active #app .v-main .extension-card:hover,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions:hover,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions:hover,",
            "html.astrbot-palette-active #app .v-main .extension-page .plugin-card:hover,",
            "html.astrbot-palette-active #app .v-main .plugin-card:hover,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions:hover,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions:hover,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card:hover,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions:hover,",
            "html.astrbot-palette-active #app .v-main .config-page .config-row:hover,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-row:hover,",
            "html.astrbot-palette-active #app .v-main .stats-page .stat-card:hover {",
            f"  box-shadow: {hover_shadow} !important;",
            "  transform: translateY(-1px);",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .platform-page .item-card,",
            "html.astrbot-palette-active #app .v-main .platform-page .console-term,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-source-item,",
            "html.astrbot-palette-active #app .v-main .provider-page .provider-section,",
            "html.astrbot-palette-active #app .v-main .extension-page .extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-page .plugin-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .plugin-card,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .config-page .config-section,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-section,",
            "html.astrbot-palette-active #app .v-main .config-page .config-row,",
            "html.astrbot-palette-active #app .v-main .config-panel .config-row,",
            "html.astrbot-palette-active #app .v-main .stats-page .stat-card,",
            "html.astrbot-palette-active #app .v-main .stats-page .meta-pill,",
            "html.astrbot-palette-active #app .v-main .stats-page .range-switch {",
            "  transition: background-color 180ms ease, border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .stats-page .card-icon {",
            f"  background: {primary_soft} !important;",
            "  color: rgb(var(--v-theme-primary)) !important;",
            "  box-shadow: 0 0 0 1px rgba(var(--v-theme-primary), 0.18), 0 8px 20px rgba(var(--v-theme-primary), 0.16) !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .stats-page .card-value,",
            "html.astrbot-palette-active #app .v-main .stats-page .metric-value,",
            "html.astrbot-palette-active #app .v-main .stats-page .section-title {",
            f"  color: {text} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .stats-page .card-label,",
            "html.astrbot-palette-active #app .v-main .stats-page .metric-label,",
            "html.astrbot-palette-active #app .v-main .stats-page .section-subtitle,",
            "html.astrbot-palette-active #app .v-main .stats-page .provider-name {",
            f"  color: {muted} !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .stats-page .card-note,",
            "html.astrbot-palette-active #app .v-main .stats-page .empty-state,",
            "html.astrbot-palette-active #app .v-main .stats-page .system-row,",
            "html.astrbot-palette-active #app .v-main .stats-page .system-meta-item {",
            f"  color: {subtle} !important;",
            "}",
            "",
            "@media (max-width: 640px) {",
            "  html.astrbot-palette-active #app .v-main .platform-page .item-card:hover,",
            "  html.astrbot-palette-active #app .v-main .provider-page .provider-source-item:hover,",
            "  html.astrbot-palette-active #app .v-main .extension-page .extension-card:hover,",
            "  html.astrbot-palette-active #app .v-main .extension-card:hover,",
            "  html.astrbot-palette-active #app .v-main .extension-card .extension-actions:hover,",
            "  html.astrbot-palette-active #app .v-main .extension-card .v-card-actions:hover,",
            "  html.astrbot-palette-active #app .v-main .extension-page .plugin-card:hover,",
            "  html.astrbot-palette-active #app .v-main .plugin-card:hover,",
            "  html.astrbot-palette-active #app .v-main .plugin-card .extension-actions:hover,",
            "  html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions:hover,",
            "  html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card:hover,",
            "  html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions:hover,",
            "  html.astrbot-palette-active #app .v-main .config-page .config-row:hover,",
            "  html.astrbot-palette-active #app .v-main .config-panel .config-row:hover,",
            "  html.astrbot-palette-active #app .v-main .stats-page .stat-card:hover {",
            "    transform: none;",
            "  }",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-card-text,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-card-text:hover,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions:hover,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions:hover,",
            "html.astrbot-palette-active #app .v-main .plugin-card .plugin-card-content,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-text,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .plugin-card .plugin-card-content:hover,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-text:hover,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions:hover,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions:hover,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .plugin-card-content,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-text,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .plugin-card-content:hover,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-text:hover,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions:hover {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  background-image: none !important;",
            "  border: 0 !important;",
            "  border-top: 0 !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "  transform: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-card-text::before,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-card-text::after,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions::before,",
            "html.astrbot-palette-active #app .v-main .extension-card .extension-actions::after,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions::before,",
            "html.astrbot-palette-active #app .v-main .extension-card .v-card-actions::after,",
            "html.astrbot-palette-active #app .v-main .plugin-card .plugin-card-content::before,",
            "html.astrbot-palette-active #app .v-main .plugin-card .plugin-card-content::after,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-text::before,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-text::after,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions::before,",
            "html.astrbot-palette-active #app .v-main .plugin-card .extension-actions::after,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions::before,",
            "html.astrbot-palette-active #app .v-main .plugin-card .v-card-actions::after,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .plugin-card-content::before,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .plugin-card-content::after,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-text::before,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-text::after,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions::before,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card .v-card-actions::after {",
            "  content: none !important;",
            "  display: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-page .extension-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .plugin-card,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card,",
            "html.astrbot-palette-active #app .v-main .v-card.extension-card,",
            "html.astrbot-palette-active #app .v-main .v-card.plugin-card {",
            "  position: relative !important;",
            "  isolation: isolate !important;",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            f"  border: 1px solid {primary_ring} !important;",
            "  border-radius: 20px !important;",
            f"  box-shadow: {shadow} !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "  overflow: hidden !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-page .extension-card::before,",
            "html.astrbot-palette-active #app .v-main .extension-page .plugin-card::before,",
            "html.astrbot-palette-active #app .v-main .extension-page .market-plugin-card::before,",
            "html.astrbot-palette-active #app .v-main .v-card.extension-card::before,",
            "html.astrbot-palette-active #app .v-main .v-card.plugin-card::before {",
            "  content: \"\" !important;",
            "  display: block !important;",
            "  position: absolute !important;",
            "  inset: 0 !important;",
            "  z-index: 0 !important;",
            "  pointer-events: none !important;",
            f"  background: {surface_strong} !important;",
            f"  background-color: {surface_strong} !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-card > *,",
            "html.astrbot-palette-active #app .v-main .plugin-card > *,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card > * {",
            "  position: relative !important;",
            "  z-index: 1 !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .extension-card > .v-card__underlay,",
            "html.astrbot-palette-active #app .v-main .plugin-card > .v-card__underlay,",
            "html.astrbot-palette-active #app .v-main .market-plugin-card > .v-card__underlay {",
            "  background: transparent !important;",
            "  opacity: 0 !important;",
            "  display: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .platform-page .console-displayer-wrapper#console-wrapper:not(:fullscreen) {",
            "  box-sizing: border-box !important;",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  background-image: none !important;",
            "  border: 0 !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "  padding: 14px !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper .filter-controls,",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper .console-term {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  background-image: none !important;",
            "  border: 0 !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper:not(:fullscreen)::before,",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper:not(:fullscreen)::after,",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper .filter-controls::before,",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper .filter-controls::after,",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper .console-term::before,",
            "html.astrbot-palette-active #app .v-main .platform-page #console-wrapper .console-term::after {",
            "  content: none !important;",
            "  display: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .console-page .console-display.console-displayer-wrapper,",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper {",
            "  position: relative !important;",
            "  isolation: isolate !important;",
            "  box-sizing: border-box !important;",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            f"  border: 1px solid {primary_ring} !important;",
            "  border-radius: 20px !important;",
            f"  box-shadow: {shadow} !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "  padding: 14px !important;",
            "  overflow: hidden !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .console-page .console-display.console-displayer-wrapper::before,",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper::before {",
            "  content: \"\" !important;",
            "  display: block !important;",
            "  position: absolute !important;",
            "  inset: 0 !important;",
            "  z-index: 0 !important;",
            "  pointer-events: none !important;",
            f"  background: {surface_strong} !important;",
            f"  background-color: {surface_strong} !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper > * {",
            "  position: relative !important;",
            "  z-index: 1 !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper .filter-controls,",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper .console-term {",
            "  background: transparent !important;",
            "  background-color: transparent !important;",
            "  background-image: none !important;",
            "  border: 0 !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "  -webkit-backdrop-filter: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper .filter-controls::before,",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper .filter-controls::after,",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper .console-term::before,",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper .console-term::after {",
            "  content: none !important;",
            "  display: none !important;",
            "}",
            "",
            "html.astrbot-palette-active #app .v-main .console-page #console-wrapper:fullscreen {",
            f"  background: {surface_strong} !important;",
            "  border-radius: 0 !important;",
            "}",
        ]
    )


def _config_tabs_css() -> str:
    tab_shadow = (
        "0 1px 4px rgba(0, 0, 0, 0.44), "
        "0 -1px 4px rgba(255, 255, 255, 0.18)"
    )
    primary_border = "rgba(var(--v-theme-primary), 0.72)"
    base_tabs = [
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs",
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs.v-tabs",
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-slide-group",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs.v-tabs",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-slide-group",
    ]
    tab_buttons = [
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-tab",
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-btn.v-tab",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-tab",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-btn.v-tab",
    ]
    active_tabs = [
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-tab.v-tab--selected",
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-tab.v-btn--active",
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-tab.v-slide-group-item--active",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-tab.v-tab--selected",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-tab.v-btn--active",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-tab.v-slide-group-item--active",
    ]
    overlays = [
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-tab .v-btn__overlay",
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-tab .v-btn__underlay",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-tab .v-btn__overlay",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-tab .v-btn__underlay",
    ]
    sliders = [
        "html.astrbot-palette-active #app .v-main .config-panel .config-tabs .v-tab__slider",
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card .config-tabs .v-tab__slider",
    ]
    return "\n".join(
        [
            ",\n".join(base_tabs)
            + " {\n"
            "  background: transparent !important;\n"
            "  border: 0 !important;\n"
            "  box-shadow: none !important;\n"
            "}",
            "",
            ",\n".join(tab_buttons)
            + " {\n"
            "  background: transparent !important;\n"
            "  border: 0 !important;\n"
            "  box-shadow: none !important;\n"
            "  outline: 0 !important;\n"
            "  opacity: 0.9 !important;\n"
            "  position: relative !important;\n"
            f"  text-shadow: {tab_shadow} !important;\n"
            "}",
            "",
            "@media (min-width: 768px) {",
            ",\n".join(tab_buttons)
            + " {\n"
            "  padding-inline-start: 18px !important;\n"
            "}",
            "}",
            "",
            ",\n".join(overlays)
            + " {\n"
            "  background: transparent !important;\n"
            "  opacity: 0 !important;\n"
            "}",
            "",
            ",\n".join(sliders)
            + " {\n"
            "  display: none !important;\n"
            "}",
            "",
            ",\n".join(active_tabs)
            + " {\n"
            "  background: transparent !important;\n"
            "  border: 0 !important;\n"
            "  box-shadow: inset 2px 0 0 "
            f"{primary_border} !important;\n"
            "  color: rgb(var(--v-theme-primary)) !important;\n"
            "  opacity: 1 !important;\n"
            "}",
            "",
            ",\n".join([f"{selector}:hover" for selector in tab_buttons])
            + " {\n"
            "  background: transparent !important;\n"
            "  border: 0 !important;\n"
            "  box-shadow: none !important;\n"
            "  color: rgb(var(--v-theme-primary)) !important;\n"
            "  opacity: 1 !important;\n"
            "}",
            "",
            ",\n".join([f"{selector}:hover" for selector in active_tabs])
            + " {\n"
            "  box-shadow: inset 2px 0 0 "
            f"{primary_border} !important;\n"
            "}",
        ]
    )


def _token_stats_detail_css() -> str:
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    primary_soft = "rgba(var(--v-theme-primary), 0.12)"
    return "\n".join(
        [
            "html.astrbot-palette-token-stats-active #app .v-main .stats-page .astrbot-palette-token-detail-panel {",
            f"  background: {surface} !important;",
            "  border: 0 !important;",
            "  border-radius: 0 !important;",
            "  box-shadow: none !important;",
            "  display: grid !important;",
            "  gap: 20px !important;",
            "  margin-top: 24px !important;",
            "  min-width: 0 !important;",
            "  overflow: visible !important;",
            "  padding: 8px 0 0 !important;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-detail-head {",
            "  align-items: start;",
            "  display: flex;",
            "  gap: 16px;",
            "  justify-content: space-between;",
            "  min-width: 0;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-range {",
            f"  background: {primary_soft};",
            "  border-radius: 999px;",
            "  color: rgb(var(--v-theme-primary));",
            "  flex: 0 0 auto;",
            "  font-size: 12px;",
            "  font-weight: 700;",
            "  padding: 6px 10px;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-total-grid {",
            "  display: grid;",
            "  gap: 12px;",
            "  grid-template-columns: repeat(5, minmax(0, 1fr));",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-metric {",
            "  border: 0;",
            "  border-radius: 14px;",
            "  display: grid;",
            "  gap: 8px;",
            "  min-width: 0;",
            "  padding: 14px;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-metric span,",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-head {",
            "  color: rgba(var(--v-theme-on-surface), 0.66);",
            "  font-size: 12px;",
            "  font-weight: 700;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-metric strong {",
            "  color: rgb(var(--v-theme-on-surface));",
            "  font-size: clamp(18px, 2vw, 26px);",
            "  font-variant-numeric: tabular-nums;",
            "  overflow-wrap: anywhere;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-table {",
            "  display: grid;",
            "  gap: 8px;",
            "  min-width: 0;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-row {",
            "  border: 0;",
            "  border-radius: 14px;",
            "  display: grid;",
            "  gap: 12px;",
            "  grid-template-columns: minmax(180px, 1.6fr) repeat(5, minmax(72px, 0.7fr));",
            "  min-width: 0;",
            "  padding: 12px 14px;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-row > span,",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-row > strong {",
            "  align-self: center;",
            "  color: rgb(var(--v-theme-on-surface));",
            "  font-variant-numeric: tabular-nums;",
            "  min-width: 0;",
            "  overflow-wrap: anywhere;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-name {",
            "  display: grid;",
            "  gap: 3px;",
            "  min-width: 0;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-name strong {",
            "  color: rgb(var(--v-theme-on-surface));",
            "  min-width: 0;",
            "  overflow-wrap: anywhere;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-name span {",
            "  color: rgba(var(--v-theme-on-surface), 0.62);",
            "  font-size: 12px;",
            "  overflow-wrap: anywhere;",
            "}",
            "",
            "html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-empty {",
            "  border: 0;",
            "  border-radius: 14px;",
            "  color: rgba(var(--v-theme-on-surface), 0.72);",
            "  padding: 18px;",
            "  text-align: center;",
            "}",
            "",
            "@media (max-width: 960px) {",
            "  html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-total-grid {",
            "    grid-template-columns: repeat(2, minmax(0, 1fr));",
            "  }",
            "  html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-detail-head {",
            "    display: grid;",
            "  }",
            "  html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-table {",
            "    overflow-x: auto;",
            "    padding-bottom: 4px;",
            "  }",
            "  html.astrbot-palette-token-stats-active #app .v-main .astrbot-palette-token-model-row {",
            "    grid-template-columns: minmax(180px, 1.4fr) repeat(5, minmax(82px, 0.7fr));",
            "    min-width: 720px;",
            "  }",
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


def _platform_dialog_surface_css() -> str:
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
    route_card = (
        "html.astrbot-palette-active .v-overlay-container .v-dialog "
        ".v-card:has(.route-source-cell)"
    )
    config_drawer = (
        "html.astrbot-palette-active .v-overlay-container .config-drawer-card"
    )

    solid_surfaces = [
        route_card,
        f"{route_card} > .v-card-item",
        f"{route_card} > .v-card-title",
        f"{route_card} > .v-card-text",
        f"{route_card} > .v-card-actions",
        f"{route_card} .v-data-table",
        f"{route_card} .v-table",
        f"{route_card} .v-table__wrapper",
        f"{route_card} .v-table__wrapper > table",
        f"{route_card} .v-table__wrapper > table > thead",
        f"{route_card} .v-table__wrapper > table > thead > tr",
        f"{route_card} .v-table__wrapper > table > tbody",
        f"{route_card} .v-table__wrapper > table > tbody > tr",
        f"{route_card} .v-table__wrapper > table > tbody > tr > td",
        f"{route_card} .v-table__wrapper > table > thead > tr > th",
        f"{route_card} .v-data-table-footer",
        f"{config_drawer}",
        f"{config_drawer} .config-drawer-header",
        f"{config_drawer} .config-drawer-content",
        f"{config_drawer} .config-page",
        f"{config_drawer} .config-panel",
        f"{config_drawer} .config-toolbar",
        f"{config_drawer} .config-content",
        f"{config_drawer} .config-section",
        f"{config_drawer} .config-item",
        f"{config_drawer} .config-item-wrapper",
        f"{config_drawer} .nested-container",
        f"{config_drawer} .object-config",
        f"{config_drawer} .simple-config",
        f"{config_drawer} .array-item",
        f"{config_drawer} .object-item",
        f"{config_drawer} .v-banner.unsaved-changes-banner",
    ]
    soft_surfaces = [
        f"{route_card} .v-table__wrapper > table > tbody > tr:hover",
        f"{route_card} .v-field",
        f"{route_card} .v-list",
        f"{route_card} .route-source-mode-link",
        f"{config_drawer} .v-card",
        f"{config_drawer} .config-page .v-card",
        f"{config_drawer} .config-row:hover",
        f"{config_drawer} .collapsed-config-toggle-row",
        f"{config_drawer} .plugin-set-display-row",
        f"{config_drawer} .persona-preview-row",
        f"{config_drawer} .selected-plugins-full-width",
        f"{config_drawer} .template-list-editor",
        f"{config_drawer} .object-editor",
        f"{config_drawer} .config-item-card",
        f"{config_drawer} .list-config-item",
        f"{config_drawer} .storage-cleanup-panel",
        f"{config_drawer} .v-field",
        f"{config_drawer} .v-list",
        f"{config_drawer} .v-list-item",
    ]
    bordered = [
        f"{route_card} .v-data-table",
        f"{route_card} .v-table",
        f"{route_card} .v-table__wrapper",
        f"{route_card} .v-table__wrapper > table > thead > tr > th",
        f"{route_card} .v-table__wrapper > table > tbody > tr > td",
        f"{route_card} .v-field",
        f"{config_drawer}",
        f"{config_drawer} .v-divider",
        f"{config_drawer} .config-section",
        f"{config_drawer} .config-row",
        f"{config_drawer} .config-item",
        f"{config_drawer} .nested-container",
        f"{config_drawer} .v-field",
    ]

    return "\n".join(
        [
            ",\n".join(solid_surfaces)
            + " {\n"
            f"  background: {surface} !important;\n"
            "  box-shadow: none !important;\n"
            "  backdrop-filter: none !important;\n"
            f"  border-color: {border} !important;\n"
            "}",
            "",
            ",\n".join(soft_surfaces)
            + " {\n"
            f"  background: {neutral_soft} !important;\n"
            "  box-shadow: none !important;\n"
            f"  border-color: {border} !important;\n"
            "}",
            "",
            ",\n".join(bordered)
            + " {\n"
            f"  border-color: {border} !important;\n"
            "}",
            "",
            f"{route_card} .v-btn:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info) "
            "{\n"
            f"  background: {primary_soft} !important;\n"
            "  box-shadow: none !important;\n"
            f"  border-color: {border} !important;\n"
            "}",
        ]
    )


def _extension_dialog_surface_css(stats_card_blur: int) -> str:
    blur = max(0, min(40, stats_card_blur))
    surface = "rgba(var(--v-theme-surface), var(--astrbot-palette-surface-opacity, 0))"
    docs_surface = (
        "rgba(var(--v-theme-surface), "
        "calc(0.46 + var(--astrbot-palette-surface-opacity, 0) * 0.30))"
    )
    docs_surface_soft = (
        "rgba(var(--v-theme-surface), "
        "calc(0.32 + var(--astrbot-palette-surface-opacity, 0) * 0.22))"
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
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h2.pa-4.pl-6.pb-0),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has([style*=\"max-height: 60vh\"]),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h3.pa-4.pb-0.pl-6),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h2.pa-4.pl-6.pb-0) > .v-card-title,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h2.pa-4.pl-6.pb-0) > .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h2.pa-4.pl-6.pb-0) > .v-card-actions,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has([style*=\"max-height: 60vh\"]) [style*=\"max-height: 60vh\"],",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h3.pa-4.pb-0.pl-6) > .v-card-title,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h3.pa-4.pb-0.pl-6) > .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(> .v-card-title.text-h3.pa-4.pb-0.pl-6) > .v-card-actions,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) > .v-card-title,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) > .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) > .v-card-actions,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) .v-tabs,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) .v-window,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) .v-window-item,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) > .v-card-title,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) > .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) > .v-card-actions {",
            f"  background: {surface} !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            f"  border-color: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) .market-install-confirm,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.market-install-confirm) .market-install-source,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body .table-container,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body .copy-code-btn,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body details,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body code,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body pre.shiki,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body table th,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body table tr:nth-child(2n) {",
            f"  background: {neutral_soft} !important;",
            "  box-shadow: none !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body img,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body pre.shiki code {",
            "  background: transparent !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body .table-container,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body table,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body table th,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body table td,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body details,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body blockquote,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body pre.shiki {",
            f"  border-color: {border} !important;",
            "  --markdown-border: "
            "rgba(var(--v-theme-on-surface), "
            "calc(var(--astrbot-palette-surface-opacity, 0) * 0.18)) !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) .markdown-body hr {",
            f"  background: {border} !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.markdown-body),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.docs-markdown),",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has([class*=\"markdown\"]) {",
            f"  background: {docs_surface} !important;",
            f"  background-color: {docs_surface} !important;",
            f"  border-color: {border} !important;",
            "  box-shadow: 0 24px 72px rgba(0, 0, 0, 0.36), inset 0 1px 0 rgba(255, 255, 255, 0.12) !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) > .v-card-title,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) > .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.v-card-title .text-h2.pa-2) > .v-card-actions,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.markdown-body) > .v-card-title,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.markdown-body) > .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.markdown-body) > .v-card-actions,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.docs-markdown) > .v-card-title,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.docs-markdown) > .v-card-text,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .v-card:has(.docs-markdown) > .v-card-actions {",
            f"  background: {docs_surface_soft} !important;",
            f"  background-color: {docs_surface_soft} !important;",
            "  box-shadow: none !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "}",
            "",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .markdown-body,",
            "html.astrbot-palette-active .v-overlay-container .v-dialog .docs-markdown {",
            f"  background: {docs_surface_soft} !important;",
            f"  background-color: {docs_surface_soft} !important;",
            f"  border-color: {border} !important;",
            f"  backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            f"  -webkit-backdrop-filter: blur({blur}px) saturate(1.08) !important;",
            "}",
        ]
    )


def _extension_loading_dialog_css() -> str:
    # 插件安装/更新耗时取决于后端网络和依赖安装，这里只增强弹窗可读性。
    loading_card = (
        "html.astrbot-palette-active .v-overlay-container .v-dialog "
        ".v-card:has(.console-displayer-wrapper):has(> .v-card-title.text-h5)"
    )
    return "\n".join(
        [
            f"{loading_card} {{",
            "  background: rgba(var(--v-theme-surface), 0.9) !important;",
            "  border: 1px solid rgba(var(--v-theme-on-surface), 0.14) !important;",
            "  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.32) !important;",
            "  backdrop-filter: blur(18px) saturate(130%) !important;",
            "  -webkit-backdrop-filter: blur(18px) saturate(130%) !important;",
            "  color: rgb(var(--v-theme-on-surface)) !important;",
            "}",
            "",
            f"{loading_card} > .v-card-title,",
            f"{loading_card} > .v-card-text,",
            f"{loading_card} > .v-card-actions {{",
            "  background: transparent !important;",
            "  color: rgb(var(--v-theme-on-surface)) !important;",
            "  text-shadow: none !important;",
            "}",
            "",
            f"{loading_card} .v-divider {{",
            "  opacity: 1 !important;",
            "  border-color: rgba(var(--v-theme-on-surface), 0.12) !important;",
            "}",
            "",
            f"{loading_card} .v-progress-linear {{",
            "  opacity: 1 !important;",
            "  background: rgba(var(--v-theme-on-surface), 0.12) !important;",
            "}",
            "",
            f"{loading_card} .console-displayer-wrapper,",
            f"{loading_card} #console-wrapper {{",
            "  background: transparent !important;",
            "  border-color: transparent !important;",
            "  box-shadow: none !important;",
            "  backdrop-filter: none !important;",
            "}",
            "",
            f"{loading_card} .console-term {{",
            "  position: relative;",
            "  background: rgba(18, 18, 20, 0.94) !important;",
            "  border: 1px solid rgba(255, 255, 255, 0.1) !important;",
            "  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;",
            "  color: #e8e8e8 !important;",
            "  text-shadow: none !important;",
            "}",
            "",
            f"{loading_card} .console-term:empty::before {{",
            "  content: \"等待后端日志...\";",
            "  position: absolute;",
            "  inset: 0;",
            "  display: flex;",
            "  align-items: center;",
            "  justify-content: center;",
            "  color: rgba(232, 232, 232, 0.58);",
            "  font-size: 13px;",
            "  letter-spacing: 0;",
            "  pointer-events: none;",
            "}",
            "",
            f"{loading_card} .v-chip {{",
            "  text-shadow: none !important;",
            "}",
            "",
            f"{loading_card} .v-btn {{",
            "  text-shadow: none !important;",
            "}",
        ]
    )


def _astrbot_update_dialog_surface_css() -> str:
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
    update_card = (
        "html.astrbot-palette-active .v-overlay-container .v-dialog "
        ".v-card:has(.update-summary)"
    )
    release_card = (
        "html.astrbot-palette-active .v-overlay-container .v-dialog "
        ".v-card:has(> .v-card-title.text-h3.pa-4)"
        ":has(> .v-card-text[style*=\"max-height: 400px\"])"
    )
    changelog_card = (
        "html.astrbot-palette-active .v-overlay-container .v-dialog "
        ".v-card:has([style*=\"max-height: 70vh\"])"
    )

    solid_surfaces = [
        update_card,
        release_card,
        changelog_card,
        f"{update_card} > .v-card-title",
        f"{update_card} > .v-card-text",
        f"{update_card} > .v-card-actions",
        f"{update_card} .v-container",
        f"{update_card} .update-summary",
        f"{update_card} .update-progress-panel",
        f"{update_card} .dashboard-update-banner",
        f"{update_card} .release-message-preview",
        f"{update_card} .advanced-update-settings",
        f"{update_card} .v-data-table",
        f"{update_card} .v-table",
        f"{update_card} .v-table__wrapper",
        f"{update_card} .v-table__wrapper > table",
        f"{update_card} .v-table__wrapper > table > thead",
        f"{update_card} .v-table__wrapper > table > tbody",
        f"{update_card} .v-table__wrapper > table > tbody > tr",
        f"{update_card} .v-table__wrapper > table > tbody > tr > td",
        f"{update_card} .v-table__wrapper > table > thead > tr > th",
        f"{update_card} .v-data-table-footer",
        f"{release_card} > .v-card-title",
        f"{release_card} > .v-card-text",
        f"{release_card} > .v-card-actions",
        f"{release_card} .markdown-content",
        f"{release_card} .code-block-container",
        f"{release_card} .code-block-shell-content",
        f"{release_card} .code-block-content",
        f"{release_card} .table-node",
        f"{release_card} .mermaid-block-container",
        f"{release_card} .d2-block-container",
        f"{release_card} .infographic-block-container",
        f"{changelog_card} > .v-card-title",
        f"{changelog_card} > .v-card-text",
        f"{changelog_card} > .v-card-actions",
        f"{changelog_card} .changelog-content",
        f"{changelog_card} .markdown-content",
        f"{changelog_card} .code-block-container",
        f"{changelog_card} .code-block-shell-content",
        f"{changelog_card} .code-block-content",
        f"{changelog_card} .table-node",
        f"{changelog_card} .mermaid-block-container",
        f"{changelog_card} .d2-block-container",
        f"{changelog_card} .infographic-block-container",
        f"{changelog_card} [style*=\"max-height: 70vh\"]",
    ]
    soft_surfaces = [
        f"{update_card} .release-message-preview .markdown-content",
        f"{update_card} .release-message-preview .code-block-header",
        f"{update_card} .v-data-table .v-data-table__tr:hover",
        f"{update_card} .v-data-table tr:hover",
        f"{update_card} .v-field",
        f"{release_card} .markdown-content pre",
        f"{release_card} .markdown-content code",
        f"{release_card} .markdown-content table th",
        f"{release_card} .markdown-content table tr:nth-child(2n)",
        f"{release_card} .code-block-header",
        f"{release_card} .code-block-container pre",
        f"{release_card} .code-block-container code",
        f"{release_card} .table-node table th",
        f"{release_card} .table-node table tr:nth-child(2n)",
        f"{changelog_card} .v-field",
        f"{changelog_card} .markdown-content pre",
        f"{changelog_card} .markdown-content code",
        f"{changelog_card} .markdown-content table th",
        f"{changelog_card} .markdown-content table tr:nth-child(2n)",
        f"{changelog_card} .code-block-header",
        f"{changelog_card} .code-block-container pre",
        f"{changelog_card} .code-block-container code",
        f"{changelog_card} .table-node table th",
        f"{changelog_card} .table-node table tr:nth-child(2n)",
    ]
    bordered = [
        f"{update_card} .update-progress-panel",
        f"{update_card} .dashboard-update-banner",
        f"{update_card} .release-message-preview",
        f"{update_card} .v-table",
        f"{update_card} .v-table__wrapper",
        f"{update_card} .v-table__wrapper > table > thead > tr > th",
        f"{update_card} .v-table__wrapper > table > tbody > tr > td",
        f"{release_card} .markdown-content table",
        f"{release_card} .markdown-content table th",
        f"{release_card} .markdown-content table td",
        f"{release_card} .markdown-content pre",
        f"{release_card} .markdown-content blockquote",
        f"{release_card} .code-block-container",
        f"{release_card} .code-block-header",
        f"{release_card} .table-node",
        f"{release_card} .mermaid-block-container",
        f"{release_card} .d2-block-container",
        f"{release_card} .infographic-block-container",
        f"{changelog_card} .markdown-content table",
        f"{changelog_card} .markdown-content table th",
        f"{changelog_card} .markdown-content table td",
        f"{changelog_card} .markdown-content pre",
        f"{changelog_card} .markdown-content blockquote",
        f"{changelog_card} .code-block-container",
        f"{changelog_card} .code-block-header",
        f"{changelog_card} .table-node",
        f"{changelog_card} .mermaid-block-container",
        f"{changelog_card} .d2-block-container",
        f"{changelog_card} .infographic-block-container",
    ]

    return "\n".join(
        [
            ",\n".join(solid_surfaces)
            + " {\n"
            f"  background: {surface} !important;\n"
            "  box-shadow: none !important;\n"
            "  backdrop-filter: none !important;\n"
            "}",
            "",
            ",\n".join(soft_surfaces)
            + " {\n"
            f"  background: {neutral_soft} !important;\n"
            "  box-shadow: none !important;\n"
            "}",
            "",
            ",\n".join(bordered)
            + " {\n"
            f"  border-color: {border} !important;\n"
            "}",
            "",
            f"{update_card} .release-message-preview::after,"
            f"\n{update_card} .update-progress-panel::before "
            "{\n"
            "  background: transparent !important;\n"
            "  opacity: 0 !important;\n"
            "}",
            "",
            f"{update_card} .advanced-settings-toggle,"
            f"\n{update_card} .v-btn:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info),"
            f"\n{changelog_card} .v-btn:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info),"
            f"\n{release_card} .v-btn:not(.bg-primary):not(.bg-secondary):not(.bg-success):not(.bg-warning):not(.bg-error):not(.bg-info) "
            "{\n"
            f"  background: {primary_soft} !important;\n"
            "  box-shadow: none !important;\n"
            f"  border-color: {border} !important;\n"
            "}",
            "",
            f"{update_card} .v-alert,"
            f"\n{update_card} .v-chip,"
            f"\n{changelog_card} .v-alert,"
            f"\n{changelog_card} .v-chip "
            "{\n"
            "  text-shadow: none !important;\n"
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


def _background_fit_value(value: Any) -> str:
    fit = _css_keyword(
        value,
        {"cover", "contain", "auto", "stretch"},
        "cover",
    )
    if fit == "stretch":
        return "100% 100%"
    return fit


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
