from __future__ import annotations

PLUGIN_NAME = "astrbot_plugin_palette"
DISPLAY_NAME = "AstrBot调色盘"
VERSION = "0.1.0"
AUTHOR = "C₂₂H₂₅NO₆"
DESCRIPTION = "AstrBot WebUI 美化插件，支持运行时背景图、透明界面和可读性增强。"
ROUTE_PREFIX = f"/{PLUGIN_NAME}"

INJECTION_START_MARKER = f"<!-- {PLUGIN_NAME}:start -->"
INJECTION_END_MARKER = f"<!-- {PLUGIN_NAME}:end -->"

MAX_BACKGROUND_BYTES = 10 * 1024 * 1024
ALLOWED_BACKGROUND_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
