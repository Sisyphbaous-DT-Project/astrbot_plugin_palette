from __future__ import annotations

PLUGIN_NAME = "astrbot_plugin_palette"
DISPLAY_NAME = "AstrBot调色盘"
VERSION = "0.5.3"
THEME_CACHE_VERSION = "20261002-astrbot429"
AUTHOR = "C₂₂H₂₅NO₆"
DESCRIPTION = "AstrBot调色盘是一个 AstrBot WebUI 美化插件"
ROUTE_PREFIX = f"/{PLUGIN_NAME}"

INJECTION_START_MARKER = f"<!-- {PLUGIN_NAME}:start -->"
INJECTION_END_MARKER = f"<!-- {PLUGIN_NAME}:end -->"

# 浏览器生成的封面：源图不大于 4MB，落盘前压到 1280px 以内。
MAX_COVER_SOURCE_BYTES = 4 * 1024 * 1024
COVER_MAX_EDGE = 1280
MEDIA_BUNDLE_MAGIC = b"PALETTE-MEDIA-1\n"

IMAGE_BACKGROUND_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
VIDEO_BACKGROUND_EXTENSIONS = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
SVG_BACKGROUND_EXTENSIONS = {
    ".svg": "image/svg+xml",
}
ALLOWED_BACKGROUND_EXTENSIONS = {
    **IMAGE_BACKGROUND_EXTENSIONS,
    **VIDEO_BACKGROUND_EXTENSIONS,
    **SVG_BACKGROUND_EXTENSIONS,
}
