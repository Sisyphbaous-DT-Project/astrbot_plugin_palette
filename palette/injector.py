from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .constants import (
    INJECTION_END_MARKER,
    INJECTION_START_MARKER,
    PLUGIN_NAME,
    VERSION,
)
from .paths import PalettePaths

try:
    from astrbot.core.config.default import VERSION as ASTRBOT_VERSION
    from astrbot.core.utils.io import is_dashboard_dist_compatible
except Exception:  # pragma: no cover - 兼容旧版 AstrBot
    ASTRBOT_VERSION = ""
    is_dashboard_dist_compatible = None


@dataclass(frozen=True)
class InjectionStatus:
    """描述当前 WebUI 运行时补丁状态。"""

    supported: bool
    patched: bool
    index_exists: bool
    message: str
    target: str = ""
    target_compatible: bool | None = None

    def to_dict(self) -> dict[str, bool | str | None]:
        return {
            "supported": self.supported,
            "patched": self.patched,
            "index_exists": self.index_exists,
            "message": self.message,
            "target": self.target,
            "target_compatible": self.target_compatible,
        }


def ensure_dashboard_injection(paths: PalettePaths) -> InjectionStatus:
    """向 AstrBot 运行时 Dashboard 入口注入调色盘启动脚本。"""

    index_file = paths.user_dashboard_index
    target_info = _dashboard_target_info(paths)
    if not index_file.is_file():
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=False,
            message="未找到 data/dist/index.html，无法注入 WebUI 背景脚本。",
            **target_info,
        )

    try:
        content = index_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message="data/dist/index.html 不是有效 UTF-8，已停止写入以避免破坏 WebUI。",
            **target_info,
        )

    try:
        next_content = _inject_content(content)
    except ValueError as exc:
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message=str(exc),
            **target_info,
        )

    if next_content == content:
        return inspect_injection(paths)

    paths.ensure_runtime_dirs()
    _backup_index_if_needed(paths, content)
    temp_file = index_file.with_suffix(f"{index_file.suffix}.palette.tmp")
    temp_file.write_text(next_content, encoding="utf-8")
    temp_file.replace(index_file)
    return inspect_injection(paths)


def inspect_injection(paths: PalettePaths) -> InjectionStatus:
    """检测 WebUI 运行时补丁状态。"""

    index_file = paths.user_dashboard_index
    target_info = _dashboard_target_info(paths)
    if not index_file.is_file():
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=False,
            message="未找到 data/dist/index.html，无法检测调色盘注入状态。",
            **target_info,
        )

    try:
        content = index_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message="data/dist/index.html 不是有效 UTF-8，无法检测调色盘注入状态。",
            **target_info,
        )

    patched = INJECTION_START_MARKER in content and INJECTION_END_MARKER in content
    return InjectionStatus(
        supported=True,
        patched=patched,
        index_exists=True,
        message="已检测到调色盘注入标记。" if patched else "未检测到调色盘注入标记。",
        **target_info,
    )


def _inject_content(content: str) -> str:
    block = _build_injection_block()
    has_start = INJECTION_START_MARKER in content
    has_end = INJECTION_END_MARKER in content
    if has_start != has_end:
        raise ValueError("检测到不完整的调色盘注入标记，已停止写入以避免破坏 WebUI。")

    if has_start and has_end:
        pattern = re.compile(
            r"[ \t]*"
            + re.escape(INJECTION_START_MARKER)
            + r".*?"
            + re.escape(INJECTION_END_MARKER),
            flags=re.DOTALL,
        )
        matches = list(pattern.finditer(content))
        if len(matches) == 1:
            return pattern.sub(block, content, count=1)
        content_without_blocks = pattern.sub("", content)
        return _insert_block_before_head_close(content_without_blocks, block)

    return _insert_block_before_head_close(content, block)


def _insert_block_before_head_close(content: str, block: str) -> str:
    head_close = re.search(r"</head\s*>", content, flags=re.IGNORECASE)
    if head_close is None:
        raise ValueError("未找到 </head>，无法安全注入调色盘脚本。")

    return f"{content[:head_close.start()]}{block}\n  {content[head_close.start():]}"


def _backup_index_if_needed(paths: PalettePaths, content: str) -> None:
    if INJECTION_START_MARKER in content or INJECTION_END_MARKER in content:
        return
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    backup_file = paths.patch_backup_dir / f"index-{digest}.html"
    if backup_file.exists():
        return
    paths.patch_backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file.write_text(content, encoding="utf-8")


def _dashboard_target_info(paths: PalettePaths) -> dict[str, str | bool | None]:
    target = str(paths.user_dashboard_dist)
    compatible: bool | None = None
    if is_dashboard_dist_compatible is not None and ASTRBOT_VERSION:
        compatible = bool(
            is_dashboard_dist_compatible(paths.user_dashboard_dist, ASTRBOT_VERSION)
        )
    return {
        "target": target,
        "target_compatible": compatible,
    }


def _build_injection_block() -> str:
    config_url = f"/api/v1/plugins/extensions/{PLUGIN_NAME}/config"
    theme_url = f"/api/v1/plugins/extensions/{PLUGIN_NAME}/theme.css"
    return "\n".join(
        [
            "  " + INJECTION_START_MARKER,
            (
                '  <script id="astrbot-palette-bootstrap" '
                f'data-version="{VERSION}">'
            ),
            _build_bootstrap_script(config_url, theme_url),
            "  </script>",
            "  " + INJECTION_END_MARKER,
        ]
    )


def _build_bootstrap_script(config_url: str, theme_url: str) -> str:
    config_url_json = json.dumps(config_url)
    theme_url_json = json.dumps(theme_url)
    return f"""(function () {{
    "use strict";

    var CONFIG_URL = {config_url_json};
    var THEME_URL = {theme_url_json};
    var STYLE_ID = "astrbot-palette-theme";
    var ACTIVE_CLASS = "astrbot-palette-active";
    var DARK_THEME_BOOTSTRAP_KEY = "astrbot_palette_dark_theme_bootstrapped";
    var lastToken = null;
    var lastBackgroundUrl = "";
    var currentObjectUrl = "";
    var loading = false;
    var pendingRefresh = false;

    function bootstrapRecommendedDarkTheme() {{
      try {{
        if (window.localStorage.getItem(DARK_THEME_BOOTSTRAP_KEY) === "1") {{
          return;
        }}
        window.localStorage.setItem("themeMode", "dark");
        window.localStorage.setItem("uiTheme", "PurpleThemeDark");
        window.localStorage.setItem(DARK_THEME_BOOTSTRAP_KEY, "1");
      }} catch (_) {{
      }}
    }}

    function getToken() {{
      try {{
        return window.localStorage.getItem("token") || "";
      }} catch (_) {{
        return "";
      }}
    }}

    function buildHeaders(token, accept) {{
      var headers = {{}};
      if (token) {{
        headers.Authorization = "Bearer " + token;
      }}
      if (accept) {{
        headers.Accept = accept;
      }}
      return headers;
    }}

    function isExpectedAuthFailure(error) {{
      return error && (
        error.message === "HTTP 401" ||
        error.message === "HTTP 403" ||
        error.message === "HTTP 404" ||
        error.message === "HTTP 405"
      );
    }}

    function withCacheBust(url) {{
      return url + (url.indexOf("?") === -1 ? "?" : "&") + "_palette=" + Date.now();
    }}

    function ensureStyleElement(css) {{
      var style = document.getElementById(STYLE_ID);
      if (!style) {{
        style = document.createElement("style");
        style.id = STYLE_ID;
        style.type = "text/css";
        document.head.appendChild(style);
      }}
      if (style.textContent !== css) {{
        style.textContent = css;
      }}
    }}

    function removeStyleElement() {{
      var style = document.getElementById(STYLE_ID);
      if (style) {{
        style.remove();
      }}
    }}

    function revokeObjectUrl() {{
      if (!currentObjectUrl) {{
        return;
      }}
      URL.revokeObjectURL(currentObjectUrl);
      currentObjectUrl = "";
    }}

    function setInactive() {{
      document.documentElement.classList.remove(ACTIVE_CLASS);
      document.documentElement.removeAttribute("data-astrbot-palette-text-mode");
      [
        "--astrbot-palette-background-image",
        "--astrbot-palette-background-fit",
        "--astrbot-palette-background-position",
        "--astrbot-palette-background-blur",
        "--astrbot-palette-background-dim",
        "--astrbot-palette-background-inset",
        "--astrbot-palette-surface-opacity",
        "--astrbot-palette-text-enhancement-strength",
        "--astrbot-palette-background-grayscale",
        "--astrbot-palette-background-brightness",
        "--astrbot-palette-background-contrast",
        "--astrbot-palette-background-saturation",
      ].forEach(function (name) {{
        document.documentElement.style.removeProperty(name);
      }});
      lastBackgroundUrl = "";
      revokeObjectUrl();
    }}

    function clampNumber(value, minimum, maximum, fallback) {{
      var number = Number(value);
      if (!Number.isFinite(number)) {{
        return fallback;
      }}
      return Math.min(Math.max(number, minimum), maximum);
    }}

    function normalizeFit(value) {{
      return ["cover", "contain", "auto"].indexOf(value) === -1 ? "cover" : value;
    }}

    function applyConfig(config, imageUrl) {{
      var root = document.documentElement;
      root.style.setProperty("--astrbot-palette-background-image", imageUrl ? 'url("' + imageUrl + '")' : "none");
      root.style.setProperty("--astrbot-palette-background-fit", normalizeFit(config.background_fit));
      root.style.setProperty("--astrbot-palette-background-position", config.background_position || "center center");
      var backgroundBlur = clampNumber(config.background_blur, 0, 40, 0);
      root.style.setProperty("--astrbot-palette-background-blur", backgroundBlur + "px");
      root.style.setProperty("--astrbot-palette-background-inset", (backgroundBlur > 0 ? backgroundBlur + 16 : 0) + "px");
      root.style.setProperty("--astrbot-palette-background-dim", String(clampNumber(config.background_dim, 0, 0.95, 0.5)));
      root.style.setProperty("--astrbot-palette-surface-opacity", String(clampNumber(config.surface_opacity, 0, 1, 0)));
      root.style.setProperty("--astrbot-palette-text-enhancement-strength", String(clampNumber(config.text_enhancement_strength, 0, 1, 1)));
      root.style.setProperty("--astrbot-palette-background-grayscale", String(clampNumber(config.background_grayscale, 0, 1, 0)));
      root.style.setProperty("--astrbot-palette-background-brightness", String(clampNumber(config.background_brightness, 0.5, 1.5, 1)));
      root.style.setProperty("--astrbot-palette-background-contrast", String(clampNumber(config.background_contrast, 0.5, 1.5, 1)));
      root.style.setProperty("--astrbot-palette-background-saturation", String(clampNumber(config.background_saturation, 0, 2, 1)));
      root.setAttribute("data-astrbot-palette-text-mode", config.text_enhancement_mode || "soft_shadow");
      root.classList.toggle(ACTIVE_CLASS, Boolean(config.enabled && imageUrl));
    }}

    async function fetchText(url, token) {{
      var response = await fetch(withCacheBust(url), {{
        cache: "no-store",
        credentials: "same-origin",
        headers: buildHeaders(token, "text/css,application/json"),
      }});
      if (!response.ok) {{
        throw new Error("HTTP " + response.status);
      }}
      return response.text();
    }}

    async function fetchJson(url, token) {{
      var response = await fetch(withCacheBust(url), {{
        cache: "no-store",
        credentials: "same-origin",
        headers: buildHeaders(token, "application/json"),
      }});
      if (!response.ok) {{
        throw new Error("HTTP " + response.status);
      }}
      return response.json();
    }}

    async function fetchBackground(url, token) {{
      if (!url) {{
        lastBackgroundUrl = "";
        revokeObjectUrl();
        return "";
      }}
      if (url === lastBackgroundUrl && currentObjectUrl) {{
        return currentObjectUrl;
      }}
      var response = await fetch(withCacheBust(url), {{
        cache: "no-store",
        credentials: "same-origin",
        headers: buildHeaders(token, "image/*"),
      }});
      if (!response.ok) {{
        throw new Error("HTTP " + response.status);
      }}
      var blob = await response.blob();
      revokeObjectUrl();
      currentObjectUrl = URL.createObjectURL(blob);
      lastBackgroundUrl = url;
      return currentObjectUrl;
    }}

    async function refreshPalette() {{
      if (loading) {{
        pendingRefresh = true;
        return;
      }}
      loading = true;
      try {{
        var token = getToken();
        lastToken = token;
        var config = await fetchJson(CONFIG_URL, token);

        if (!config.enabled || !config.background_url) {{
          setInactive();
          removeStyleElement();
          return;
        }}

        var css = await fetchText(THEME_URL, token);
        var imageUrl = "";
        try {{
          imageUrl = await fetchBackground(config.background_url, token);
        }} catch (error) {{
          setInactive();
          removeStyleElement();
          throw error;
        }}
        ensureStyleElement(css);
        applyConfig(config, imageUrl);
      }} catch (error) {{
        setInactive();
        removeStyleElement();
        if (!isExpectedAuthFailure(error)) {{
          console.warn("[AstrBot调色盘] 背景刷新失败：", error);
        }}
      }} finally {{
        loading = false;
        if (pendingRefresh) {{
          pendingRefresh = false;
          window.setTimeout(refreshPalette, 80);
        }}
      }}
    }}

    window.addEventListener("message", function (event) {{
      if (event.origin !== window.location.origin) {{
        return;
      }}
      if (event && event.data && event.data.type === "astrbot-palette:refresh") {{
        refreshPalette();
      }}
    }});
    window.addEventListener("storage", function (event) {{
      if (!event || event.key === "token") {{
        refreshPalette();
      }}
    }});
    window.addEventListener("visibilitychange", function () {{
      if (document.visibilityState === "visible") {{
        refreshPalette();
      }}
    }});
    window.addEventListener("hashchange", refreshPalette);
    window.addEventListener("beforeunload", revokeObjectUrl);

    window.setInterval(function () {{
      var token = getToken();
      if (token !== lastToken) {{
        refreshPalette();
      }}
    }}, 1500);

    bootstrapRecommendedDarkTheme();
    refreshPalette();
  }})();"""
