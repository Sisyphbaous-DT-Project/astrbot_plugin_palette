from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
from contextlib import suppress as contextlib_suppress
from dataclasses import dataclass
from pathlib import Path

from .constants import (
    INJECTION_END_MARKER,
    INJECTION_START_MARKER,
    PLUGIN_NAME,
    VERSION,
)
from .paths import PalettePaths

try:
    from astrbot.core.config.default import VERSION as ASTRBOT_VERSION
    from astrbot.core.utils.io import (
        get_bundled_dashboard_dist_path,
        is_dashboard_dist_compatible,
        should_use_bundled_dashboard_dist,
    )
except Exception:  # pragma: no cover - 兼容旧版 AstrBot
    ASTRBOT_VERSION = ""
    get_bundled_dashboard_dist_path = None
    is_dashboard_dist_compatible = None
    should_use_bundled_dashboard_dist = None


_PREPARED_FALLBACK_DISTS: set[str] = set()
_FALLBACK_RESTART_MARKER = ".palette-restart-required"
_PROCESS_START_TIME = time.time()


@dataclass(frozen=True)
class InjectionStatus:
    """描述当前 WebUI 运行时补丁状态。"""

    supported: bool
    patched: bool
    index_exists: bool
    message: str
    target: str = ""
    target_compatible: bool | None = None
    target_source: str = ""
    restart_required: bool = False
    fallback_target: str = ""

    def to_dict(self) -> dict[str, bool | str | None]:
        return {
            "supported": self.supported,
            "patched": self.patched,
            "index_exists": self.index_exists,
            "message": self.message,
            "target": self.target,
            "target_compatible": self.target_compatible,
            "target_source": self.target_source,
            "restart_required": self.restart_required,
            "fallback_target": self.fallback_target,
        }


@dataclass(frozen=True)
class DashboardTarget:
    """描述本次应注入的 Dashboard 入口。"""

    dist: Path
    index: Path
    source: str
    compatible: bool | None
    restart_required: bool = False
    fallback_target: str = ""


def ensure_dashboard_injection(paths: PalettePaths) -> InjectionStatus:
    """向 AstrBot 运行时 Dashboard 入口注入调色盘启动脚本。"""

    target = _resolve_dashboard_target(paths, allow_copy_fallback=True)
    index_file = target.index
    target_info = _dashboard_target_info(target)
    if not index_file.is_file():
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=False,
            message=f"未找到 {target.source} WebUI 入口，无法注入背景脚本。",
            **target_info,
        )

    try:
        content = index_file.read_text(encoding="utf-8")
    except OSError as exc:
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message=f"无法读取 {target.source} WebUI 入口：{exc}",
            **target_info,
        )
    except UnicodeDecodeError:
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message=f"{target.source} WebUI 入口不是有效 UTF-8，已停止写入以避免破坏 WebUI。",
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
        return _inspect_target(target)

    temp_file = index_file.with_suffix(f"{index_file.suffix}.palette.tmp")
    try:
        paths.ensure_runtime_dirs()
        _backup_index_if_needed(paths, index_file, content)
        temp_file.write_text(next_content, encoding="utf-8")
        temp_file.replace(index_file)
    except OSError as exc:
        with contextlib_suppress(FileNotFoundError):
            temp_file.unlink()
        if target.source == "bundled":
            try:
                fallback = _prepare_user_dist_fallback(paths, target)
            except OSError as fallback_exc:
                return InjectionStatus(
                    supported=False,
                    patched=False,
                    index_exists=True,
                    message=(
                        f"无法写入 {target.source} WebUI 入口，"
                        f"复制到 data/dist 也失败：{fallback_exc}"
                    ),
                    **target_info,
                )
            if fallback is not None:
                return _inject_prepared_fallback(paths, fallback)
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message=f"无法写入 {target.source} WebUI 入口：{exc}",
            **target_info,
        )
    return _inspect_target(target)


def inspect_injection(paths: PalettePaths) -> InjectionStatus:
    """检测 WebUI 运行时补丁状态。"""

    target = _resolve_dashboard_target(paths, allow_copy_fallback=False)
    return _inspect_target(target)


def _inspect_target(target: DashboardTarget) -> InjectionStatus:
    """检测指定 Dashboard 入口的注入状态。"""

    index_file = target.index
    target_info = _dashboard_target_info(target)
    if not index_file.is_file():
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=False,
            message=f"未找到 {target.source} WebUI 入口，无法检测调色盘注入状态。",
            **target_info,
        )

    try:
        content = index_file.read_text(encoding="utf-8")
    except OSError as exc:
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message=f"无法读取 {target.source} WebUI 入口：{exc}",
            **target_info,
        )
    except UnicodeDecodeError:
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message=f"{target.source} WebUI 入口不是有效 UTF-8，无法检测调色盘注入状态。",
            **target_info,
        )

    patched = INJECTION_START_MARKER in content and INJECTION_END_MARKER in content
    message = "已检测到调色盘注入标记。" if patched else "未检测到调色盘注入标记。"
    if patched and target.restart_required:
        message = "已准备 data/dist WebUI 注入，重启 AstrBot 后生效。"
    elif patched and target.source == "bundled":
        message = "已注入 AstrBot 内置 WebUI 入口。"
    elif patched and target.source == "custom":
        message = "已注入自定义 WebUI 入口。"
    if patched and not target.restart_required and target.source == "data/dist":
        _clear_restart_marker(target.dist)
    return InjectionStatus(
        supported=True,
        patched=patched,
        index_exists=True,
        message=message,
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
            return pattern.sub(lambda _: block, content, count=1)
        content_without_blocks = pattern.sub("", content)
        return _insert_block_before_head_close(content_without_blocks, block)

    return _insert_block_before_head_close(content, block)


def _insert_block_before_head_close(content: str, block: str) -> str:
    head_close = re.search(r"</head\s*>", content, flags=re.IGNORECASE)
    if head_close is None:
        raise ValueError("未找到 </head>，无法安全注入调色盘脚本。")

    return f"{content[:head_close.start()]}{block}\n  {content[head_close.start():]}"


def _backup_index_if_needed(paths: PalettePaths, index_file: Path, content: str) -> None:
    if INJECTION_START_MARKER in content or INJECTION_END_MARKER in content:
        return
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
    target_digest = hashlib.sha256(str(index_file).encode("utf-8")).hexdigest()[:8]
    backup_file = paths.patch_backup_dir / f"index-{target_digest}-{digest}.html"
    if backup_file.exists():
        return
    paths.patch_backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file.write_text(content, encoding="utf-8")


def _dashboard_target_info(target: DashboardTarget) -> dict[str, str | bool | None]:
    return {
        "target": str(target.dist),
        "target_compatible": target.compatible,
        "target_source": target.source,
        "restart_required": target.restart_required,
        "fallback_target": target.fallback_target,
    }


def _resolve_dashboard_target(
    paths: PalettePaths,
    *,
    allow_copy_fallback: bool,
) -> DashboardTarget:
    custom_dist = _custom_dashboard_dist()
    if custom_dist is not None:
        return _target_from_dist(custom_dist, "custom")

    user_target = _target_from_dist(paths.user_dashboard_dist, "data/dist")
    if _is_compatible(user_target.dist):
        if allow_copy_fallback and _is_prepared_fallback(paths):
            bundled_target = _bundled_dashboard_target()
            return _target_from_dist(
                paths.user_dashboard_dist,
                "data/dist",
                restart_required=True,
                fallback_target=str(bundled_target.dist) if bundled_target else "",
            )
        return user_target

    bundled_target = _bundled_dashboard_target()
    if bundled_target is not None:
        if _should_use_bundled(paths.user_dashboard_dist) or _is_compatible(
            bundled_target.dist
        ):
            return bundled_target

    return user_target


def _target_from_dist(
    dist: Path,
    source: str,
    *,
    restart_required: bool = False,
    fallback_target: str = "",
) -> DashboardTarget:
    return DashboardTarget(
        dist=dist,
        index=dist / "index.html",
        source=source,
        compatible=_compatibility(dist),
        restart_required=restart_required,
        fallback_target=fallback_target,
    )


def _custom_dashboard_dist() -> Path | None:
    cli_dist = _webui_dir_from_argv(sys.argv[1:])
    if not cli_dist:
        return None
    dist = Path(cli_dist).expanduser()
    if dist.exists():
        return dist.resolve()
    return None


def _webui_dir_from_argv(argv: list[str]) -> str | None:
    for idx, arg in enumerate(argv):
        if arg.startswith("--webui-dir="):
            return arg.split("=", 1)[1].strip() or None
        if arg != "--webui-dir":
            continue
        if idx + 1 >= len(argv):
            return None
        value_parts: list[str] = []
        for value_arg in argv[idx + 1 :]:
            if value_arg.startswith("-"):
                break
            if value_arg:
                value_parts.append(value_arg)
        return " ".join(value_parts).strip() or None
    return None


def _bundled_dashboard_target() -> DashboardTarget | None:
    if get_bundled_dashboard_dist_path is None:
        return None
    try:
        dist = Path(get_bundled_dashboard_dist_path())
    except Exception:
        return None
    return _target_from_dist(dist, "bundled")


def _compatibility(dist: Path) -> bool | None:
    if is_dashboard_dist_compatible is None or not ASTRBOT_VERSION:
        return None
    try:
        return bool(is_dashboard_dist_compatible(dist, ASTRBOT_VERSION))
    except Exception:
        return False


def _is_compatible(dist: Path) -> bool:
    return _compatibility(dist) is True


def _should_use_bundled(user_dist: Path) -> bool:
    if should_use_bundled_dashboard_dist is None or not ASTRBOT_VERSION:
        return False
    try:
        return bool(should_use_bundled_dashboard_dist(user_dist, ASTRBOT_VERSION))
    except Exception:
        return False


def _is_prepared_fallback(paths: PalettePaths) -> bool:
    if str(paths.user_dashboard_dist.resolve()) in _PREPARED_FALLBACK_DISTS:
        return True
    marker = paths.user_dashboard_dist / _FALLBACK_RESTART_MARKER
    if not marker.is_file():
        return False
    try:
        if marker.stat().st_mtime >= _PROCESS_START_TIME:
            return True
    except OSError:
        return False
    _clear_restart_marker(paths.user_dashboard_dist)
    return False


def _clear_restart_marker(dist: Path) -> None:
    with contextlib_suppress(OSError):
        (dist / _FALLBACK_RESTART_MARKER).unlink()


def _prepare_user_dist_fallback(
    paths: PalettePaths,
    source_target: DashboardTarget,
) -> DashboardTarget | None:
    if not source_target.index.is_file():
        return None
    if source_target.dist.resolve() == paths.user_dashboard_dist.resolve():
        return None
    paths.ensure_runtime_dirs()
    _ensure_safe_user_dist_path(paths)
    staging_dist = _copy_dist_to_staging(paths, source_target)
    backup_target: Path | None = None
    try:
        if paths.user_dashboard_dist.exists():
            backup_target = _move_existing_user_dist_to_backup(paths)
        shutil.move(str(staging_dist), str(paths.user_dashboard_dist))
        (paths.user_dashboard_dist / _FALLBACK_RESTART_MARKER).write_text(
            "restart AstrBot to serve this prepared dashboard dist\n",
            encoding="utf-8",
        )
    except OSError:
        if backup_target is not None and not paths.user_dashboard_dist.exists():
            with contextlib_suppress(OSError):
                shutil.move(str(backup_target), str(paths.user_dashboard_dist))
        _cleanup_staging_dist(staging_dist)
        raise
    _PREPARED_FALLBACK_DISTS.add(str(paths.user_dashboard_dist.resolve()))
    return _target_from_dist(
        paths.user_dashboard_dist,
        "data/dist",
        restart_required=True,
        fallback_target=str(source_target.dist),
    )


def _ensure_safe_user_dist_path(paths: PalettePaths) -> None:
    data_root = paths.data_root.resolve()
    user_dist = paths.user_dashboard_dist.resolve(strict=False)
    expected = data_root / "dist"
    if user_dist != expected:
        raise OSError(f"data/dist 路径异常，已停止自动复制：{user_dist}")


def _copy_dist_to_staging(
    paths: PalettePaths,
    source_target: DashboardTarget,
) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256(str(source_target.dist).encode("utf-8")).hexdigest()[:8]
    staging_dist = paths.data_root / f"dist.palette-copying-{timestamp}-{digest}"
    counter = 1
    while staging_dist.exists():
        staging_dist = (
            paths.data_root / f"dist.palette-copying-{timestamp}-{digest}-{counter}"
        )
        counter += 1
    try:
        shutil.copytree(source_target.dist, staging_dist)
    except OSError:
        _cleanup_staging_dist(staging_dist)
        raise
    return staging_dist


def _cleanup_staging_dist(staging_dist: Path) -> None:
    if not staging_dist.exists():
        return
    if staging_dist.is_symlink() or staging_dist.is_file():
        with contextlib_suppress(OSError):
            staging_dist.unlink()
        return
    with contextlib_suppress(OSError):
        shutil.rmtree(staging_dist)


def _move_existing_user_dist_to_backup(paths: PalettePaths) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256(str(paths.user_dashboard_dist).encode("utf-8")).hexdigest()[
        :8
    ]
    backup_target = paths.patch_backup_dir / f"dist-{timestamp}-{digest}"
    counter = 1
    while backup_target.exists():
        backup_target = paths.patch_backup_dir / f"dist-{timestamp}-{digest}-{counter}"
        counter += 1
    shutil.move(str(paths.user_dashboard_dist), str(backup_target))
    return backup_target


def _inject_prepared_fallback(
    paths: PalettePaths,
    target: DashboardTarget,
) -> InjectionStatus:
    index_file = target.index
    target_info = _dashboard_target_info(target)
    if not index_file.is_file():
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=False,
            message="已复制 WebUI，但未找到 data/dist/index.html。",
            **target_info,
        )
    try:
        content = index_file.read_text(encoding="utf-8")
        next_content = _inject_content(content)
        if next_content != content:
            _backup_index_if_needed(paths, index_file, content)
            temp_file = index_file.with_suffix(f"{index_file.suffix}.palette.tmp")
            temp_file.write_text(next_content, encoding="utf-8")
            temp_file.replace(index_file)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        with contextlib_suppress(NameError, FileNotFoundError):
            temp_file.unlink()
        return InjectionStatus(
            supported=False,
            patched=False,
            index_exists=True,
            message=f"已复制 WebUI，但注入 data/dist 失败：{exc}",
            **target_info,
        )
    return _inspect_target(target)


def _build_injection_block() -> str:
    config_url = f"/api/v1/plugins/extensions/{PLUGIN_NAME}/config"
    random_select_url = f"/api/v1/plugins/extensions/{PLUGIN_NAME}/backgrounds/random-select"
    theme_url = f"/api/v1/plugins/extensions/{PLUGIN_NAME}/theme.css"
    token_stats_url = f"/api/v1/plugins/extensions/{PLUGIN_NAME}/token-stats"
    return "\n".join(
        [
            "  " + INJECTION_START_MARKER,
            (
                '  <script id="astrbot-palette-bootstrap" '
                f'data-version="{VERSION}">'
            ),
            _build_bootstrap_script(
                config_url,
                random_select_url,
                theme_url,
                token_stats_url,
            ),
            "  </script>",
            "  " + INJECTION_END_MARKER,
        ]
    )


def _build_bootstrap_script(
    config_url: str,
    random_select_url: str,
    theme_url: str,
    token_stats_url: str,
) -> str:
    config_url_json = json.dumps(config_url)
    random_select_url_json = json.dumps(random_select_url)
    theme_url_json = json.dumps(theme_url)
    token_stats_url_json = json.dumps(token_stats_url)
    return f"""(function () {{
    "use strict";

    var CONFIG_URL = {config_url_json};
    var RANDOM_SELECT_URL = {random_select_url_json};
    var THEME_URL = {theme_url_json};
    var TOKEN_STATS_URL = {token_stats_url_json};
    var STYLE_ID = "astrbot-palette-theme";
    var THEME_COLOR_STYLE_ID = "astrbot-palette-theme-colors";
    var TOKEN_STATS_PANEL_ID = "astrbot-palette-token-detail-panel";
    var ACTIVE_CLASS = "astrbot-palette-active";
    var TOKEN_STATS_ACTIVE_CLASS = "astrbot-palette-token-stats-active";
    var DARK_THEME_BOOTSTRAP_KEY = "astrbot_palette_dark_theme_bootstrapped";
    var THEME_COLOR_ACTIVE_KEY = "astrbot_palette_theme_colors_active";
    var PREVIOUS_PRIMARY_KEY = "astrbot_palette_theme_previous_primary";
    var PREVIOUS_SECONDARY_KEY = "astrbot_palette_theme_previous_secondary";
    var PREVIOUS_PRIMARY_RGB_KEY = "astrbot_palette_theme_previous_primary_rgb";
    var PREVIOUS_SECONDARY_RGB_KEY = "astrbot_palette_theme_previous_secondary_rgb";
    var PREVIOUS_DARKPRIMARY_RGB_KEY = "astrbot_palette_theme_previous_darkprimary_rgb";
    var PREVIOUS_DARKSECONDARY_RGB_KEY = "astrbot_palette_theme_previous_darksecondary_rgb";
    var BACKGROUND_CONTAINER_ID = "astrbot-palette-background";
    var lastToken = null;
    var lastBackgroundUrl = "";
    var lastBackgroundObjectUrl = "";
    var currentBackgroundUrl = "";
    var currentObjectUrl = "";
    var backgroundObjectUrlCache = {{}};
    var backgroundDecodedUrlCache = {{}};
    var backgroundActiveLayer = null;
    var backgroundRequestSeq = 0;
    var backgroundTransitionToken = 0;
    var backgroundResizeTimer = 0;
    var lastConfig = null;
    var restoredThemeStyleActive = false;
    var restoredThemePrimary = "";
    var restoredThemeSecondary = "";
    var detailedTokenStatsEnabled = false;
    var tokenStatsObserver = null;
    var tokenStatsRefreshTimer = 0;
    var tokenStatsPollTimer = 0;
    var tokenStatsClickListenerReady = false;
    var tokenStatsInFlight = false;
    var tokenStatsLastFetchKey = "";
    var tokenStatsLastFetchAt = 0;
    var tokenStatsMutationMuted = false;
    var loading = false;
    var pendingRefresh = false;
    var initialRandomPending = true;

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

    function buildThemeColorCss(primaryRgb, secondaryRgb, darkPrimaryRgb, darkSecondaryRgb) {{
      return [
        ":root {{",
        "  --v-theme-primary: " + primaryRgb + " !important;",
        "  --v-theme-secondary: " + secondaryRgb + " !important;",
        "  --v-theme-darkprimary: " + darkPrimaryRgb + " !important;",
        "  --v-theme-darksecondary: " + darkSecondaryRgb + " !important;",
        "}}",
        ".v-theme--PurpleTheme, .v-theme--PurpleThemeDark {{",
        "  --v-theme-primary: " + primaryRgb + " !important;",
        "  --v-theme-secondary: " + secondaryRgb + " !important;",
        "  --v-theme-darkprimary: " + darkPrimaryRgb + " !important;",
        "  --v-theme-darksecondary: " + darkSecondaryRgb + " !important;",
        "}}",
      ].join("\\n");
    }}

    function ensureThemeColorRgbStyle(primaryRgb, secondaryRgb, darkPrimaryRgb, darkSecondaryRgb) {{
      var style = document.getElementById(THEME_COLOR_STYLE_ID);
      if (!style) {{
        style = document.createElement("style");
        style.id = THEME_COLOR_STYLE_ID;
        style.type = "text/css";
        document.head.appendChild(style);
      }}
      var css = buildThemeColorCss(
        primaryRgb,
        secondaryRgb,
        darkPrimaryRgb || primaryRgb,
        darkSecondaryRgb || secondaryRgb
      );
      if (style.textContent !== css) {{
        style.textContent = css;
      }}
    }}

    function ensureThemeColorStyle(primary, secondary) {{
      var primaryRgb = hexToRgbTuple(primary);
      var secondaryRgb = hexToRgbTuple(secondary);
      if (!primaryRgb || !secondaryRgb) {{
        removeThemeColorStyle();
        return;
      }}
      ensureThemeColorRgbStyle(primaryRgb, secondaryRgb, primaryRgb, secondaryRgb);
    }}

    function removeThemeColorStyle() {{
      var style = document.getElementById(THEME_COLOR_STYLE_ID);
      if (style) {{
        style.remove();
      }}
      restoredThemeStyleActive = false;
      restoredThemePrimary = "";
      restoredThemeSecondary = "";
    }}

    function revokeObjectUrls() {{
      backgroundRequestSeq += 1;
      Object.keys(backgroundObjectUrlCache).forEach(function (url) {{
        try {{
          URL.revokeObjectURL(backgroundObjectUrlCache[url]);
        }} catch (_) {{
        }}
      }});
      backgroundObjectUrlCache = {{}};
      backgroundDecodedUrlCache = {{}};
      lastBackgroundUrl = "";
      lastBackgroundObjectUrl = "";
      currentBackgroundUrl = "";
      currentObjectUrl = "";
    }}

    function removeBackgroundContainer() {{
      var container = document.getElementById(BACKGROUND_CONTAINER_ID);
      if (container) {{
        container.remove();
      }}
    }}

    function ensureBackgroundContainer() {{
      var container = document.getElementById(BACKGROUND_CONTAINER_ID);
      if (!container) {{
        container = document.createElement("div");
        container.id = BACKGROUND_CONTAINER_ID;
        container.setAttribute("aria-hidden", "true");
        for (var index = 0; index < 2; index += 1) {{
          var layer = document.createElement("div");
          layer.className = "astrbot-palette-background-layer";
          container.appendChild(layer);
        }}
        document.body.prepend(container);
      }}
      return container;
    }}

    function getViewportOrientation() {{
      try {{
        if (window.matchMedia && window.matchMedia("(orientation: portrait)").matches) {{
          return "portrait";
        }}
      }} catch (_) {{
      }}
      return window.innerHeight > window.innerWidth ? "portrait" : "landscape";
    }}

    function pickBackgroundUrl(config, orientation) {{
      if (orientation === "portrait") {{
        return config.portrait_background_url || config.background_url || config.landscape_background_url || config.fallback_background_url || "";
      }}
      return config.landscape_background_url || config.background_url || config.portrait_background_url || config.fallback_background_url || "";
    }}

    function nextBackgroundFrame() {{
      return new Promise(function (resolve) {{
        window.requestAnimationFrame(function () {{
          window.requestAnimationFrame(resolve);
        }});
      }});
    }}

    function decodeBackgroundImage(objectUrl) {{
      if (!objectUrl) {{
        return Promise.resolve();
      }}
      if (backgroundDecodedUrlCache[objectUrl]) {{
        return backgroundDecodedUrlCache[objectUrl];
      }}
      var promise = new Promise(function (resolve) {{
        var image = new Image();
        var done = function () {{
          resolve();
        }};
        image.onload = function () {{
          if (image.decode) {{
            image.decode().then(done).catch(done);
          }} else {{
            done();
          }}
        }};
        image.onerror = done;
        image.src = objectUrl;
      }});
      backgroundDecodedUrlCache[objectUrl] = promise;
      return promise;
    }}

    async function applyBackgroundLayer(objectUrl, animate, isCurrent) {{
      var container = ensureBackgroundContainer();
      var layers = container.querySelectorAll(".astrbot-palette-background-layer");
      if (layers.length < 2) {{
        removeBackgroundContainer();
        container = ensureBackgroundContainer();
        layers = container.querySelectorAll(".astrbot-palette-background-layer");
      }}
      var currentLayer = backgroundActiveLayer;
      if (!currentLayer || !container.contains(currentLayer)) {{
        currentLayer = container.querySelector(".astrbot-palette-background-layer.is-active");
      }}
      var nextLayer = currentLayer || layers[0];
      if (animate && currentLayer) {{
        Array.prototype.some.call(layers, function (layer) {{
          if (layer !== currentLayer) {{
            nextLayer = layer;
            return true;
          }}
          return false;
        }});
      }}
      nextLayer.style.backgroundImage = objectUrl ? 'url("' + objectUrl + '")' : "none";
      if (animate && currentLayer && currentLayer !== nextLayer) {{
        var transitionToken = backgroundTransitionToken + 1;
        backgroundTransitionToken = transitionToken;
        nextLayer.classList.remove("is-active");
        container.appendChild(nextLayer);
        void nextLayer.offsetWidth;
        await nextBackgroundFrame();
        if (
          backgroundTransitionToken !== transitionToken ||
          (isCurrent && !isCurrent())
        ) {{
          nextLayer.classList.remove("is-active");
          nextLayer.style.backgroundImage = "none";
          return false;
        }}
        nextLayer.classList.add("is-active");
        currentLayer.classList.remove("is-active");
        backgroundActiveLayer = nextLayer;
        window.setTimeout(function () {{
          if (
            backgroundTransitionToken === transitionToken &&
            !currentLayer.classList.contains("is-active")
          ) {{
            currentLayer.style.backgroundImage = "none";
          }}
        }}, 760);
      }} else {{
        backgroundTransitionToken += 1;
        container.appendChild(nextLayer);
        Array.prototype.forEach.call(layers, function (layer) {{
          var isNextLayer = layer === nextLayer;
          layer.classList.toggle("is-active", isNextLayer);
          if (!isNextLayer) {{
            layer.style.backgroundImage = "none";
          }}
        }});
        backgroundActiveLayer = nextLayer;
      }}
      return true;
    }}

    function setInactive() {{
      document.documentElement.classList.remove(ACTIVE_CLASS);
      document.documentElement.classList.remove(TOKEN_STATS_ACTIVE_CLASS);
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
      removeBackgroundContainer();
      revokeObjectUrls();
      lastConfig = null;
      restoreThemeColors();
      stopTokenStatsEnhancement();
    }}

    function clampNumber(value, minimum, maximum, fallback) {{
      var number = Number(value);
      if (!Number.isFinite(number)) {{
        return fallback;
      }}
      return Math.min(Math.max(number, minimum), maximum);
    }}

    function normalizeFit(value) {{
      if (value === "stretch") {{
        return "100% 100%";
      }}
      return ["cover", "contain", "auto"].indexOf(value) === -1 ? "cover" : value;
    }}

    function normalizeHexColor(value) {{
      if (typeof value !== "string") {{
        return "";
      }}
      var color = value.trim();
      return /^#[0-9a-fA-F]{{6}}$/.test(color) ? color.toLowerCase() : "";
    }}

    function hexToRgbTuple(value) {{
      var color = normalizeHexColor(value);
      if (!color) {{
        return "";
      }}
      return [
        parseInt(color.slice(1, 3), 16),
        parseInt(color.slice(3, 5), 16),
        parseInt(color.slice(5, 7), 16),
      ].join(", ");
    }}

    function getThemeVariableSource() {{
      return document.querySelector(".v-theme--PurpleTheme, .v-theme--PurpleThemeDark") || document.documentElement;
    }}

    function normalizeRgbTuple(value) {{
      if (typeof value !== "string") {{
        return "";
      }}
      var parts = value.trim().split(",").map(function (part) {{
        var number = Number(part.trim());
        return Number.isFinite(number) ? Math.round(number) : NaN;
      }});
      if (parts.length !== 3 || parts.some(function (part) {{ return !Number.isFinite(part) || part < 0 || part > 255; }})) {{
        return "";
      }}
      return parts.join(", ");
    }}

    function readThemeRgbVariable(name) {{
      try {{
        return normalizeRgbTuple(
          window.getComputedStyle(getThemeVariableSource()).getPropertyValue(name)
        );
      }} catch (_) {{
        return "";
      }}
    }}

    function storePreviousThemeColors() {{
      try {{
        if (window.localStorage.getItem(THEME_COLOR_ACTIVE_KEY) === "1") {{
          return;
        }}
        var currentPrimary = window.localStorage.getItem("themePrimary") || "";
        var currentSecondary = window.localStorage.getItem("themeSecondary") || "";
        window.localStorage.setItem(PREVIOUS_PRIMARY_KEY, currentPrimary);
        window.localStorage.setItem(PREVIOUS_SECONDARY_KEY, currentSecondary);
        window.localStorage.setItem(
          PREVIOUS_PRIMARY_RGB_KEY,
          readThemeRgbVariable("--v-theme-primary") || hexToRgbTuple(currentPrimary)
        );
        window.localStorage.setItem(
          PREVIOUS_SECONDARY_RGB_KEY,
          readThemeRgbVariable("--v-theme-secondary") || hexToRgbTuple(currentSecondary)
        );
        window.localStorage.setItem(
          PREVIOUS_DARKPRIMARY_RGB_KEY,
          readThemeRgbVariable("--v-theme-darkprimary") ||
            readThemeRgbVariable("--v-theme-primary") ||
            hexToRgbTuple(currentPrimary)
        );
        window.localStorage.setItem(
          PREVIOUS_DARKSECONDARY_RGB_KEY,
          readThemeRgbVariable("--v-theme-darksecondary") ||
            readThemeRgbVariable("--v-theme-secondary") ||
            hexToRgbTuple(currentSecondary)
        );
        window.localStorage.setItem(THEME_COLOR_ACTIVE_KEY, "1");
      }} catch (_) {{
      }}
    }}

    function applyThemeColors(config) {{
      var primary = normalizeHexColor(config.theme_primary);
      var secondary = normalizeHexColor(config.theme_secondary);
      var currentBackground = (
        config.landscape_background_image ||
        config.portrait_background_image ||
        config.background_image
      );
      var shouldApply = Boolean(
        config.enabled &&
        config.auto_theme_enabled &&
        currentBackground &&
        primary &&
        secondary
      );
      if (!shouldApply) {{
        restoreThemeColors();
        return;
      }}
      restoredThemeStyleActive = false;
      restoredThemePrimary = "";
      restoredThemeSecondary = "";
      try {{
        storePreviousThemeColors();
        window.localStorage.setItem("themePrimary", primary);
        window.localStorage.setItem("themeSecondary", secondary);
      }} catch (_) {{
      }}
      ensureThemeColorStyle(primary, secondary);
    }}

    function restoreThemeColors() {{
      try {{
        if (window.localStorage.getItem(THEME_COLOR_ACTIVE_KEY) !== "1") {{
          if (!restoredThemeStyleActive) {{
            removeThemeColorStyle();
          }}
          return;
        }}
        var previousPrimary = window.localStorage.getItem(PREVIOUS_PRIMARY_KEY);
        var previousSecondary = window.localStorage.getItem(PREVIOUS_SECONDARY_KEY);
        var previousPrimaryRgb = normalizeRgbTuple(
          window.localStorage.getItem(PREVIOUS_PRIMARY_RGB_KEY) || ""
        );
        var previousSecondaryRgb = normalizeRgbTuple(
          window.localStorage.getItem(PREVIOUS_SECONDARY_RGB_KEY) || ""
        );
        var previousDarkPrimaryRgb = normalizeRgbTuple(
          window.localStorage.getItem(PREVIOUS_DARKPRIMARY_RGB_KEY) || ""
        );
        var previousDarkSecondaryRgb = normalizeRgbTuple(
          window.localStorage.getItem(PREVIOUS_DARKSECONDARY_RGB_KEY) || ""
        );
        if (previousPrimary) {{
          window.localStorage.setItem("themePrimary", previousPrimary);
        }} else {{
          window.localStorage.removeItem("themePrimary");
        }}
        if (previousSecondary) {{
          window.localStorage.setItem("themeSecondary", previousSecondary);
        }} else {{
          window.localStorage.removeItem("themeSecondary");
        }}
        if (previousPrimaryRgb && previousSecondaryRgb) {{
          ensureThemeColorRgbStyle(
            previousPrimaryRgb,
            previousSecondaryRgb,
            previousDarkPrimaryRgb || previousPrimaryRgb,
            previousDarkSecondaryRgb || previousSecondaryRgb
          );
          restoredThemeStyleActive = true;
          restoredThemePrimary = previousPrimary || "";
          restoredThemeSecondary = previousSecondary || "";
        }} else {{
          removeThemeColorStyle();
        }}
        window.localStorage.removeItem(THEME_COLOR_ACTIVE_KEY);
        window.localStorage.removeItem(PREVIOUS_PRIMARY_KEY);
        window.localStorage.removeItem(PREVIOUS_SECONDARY_KEY);
        window.localStorage.removeItem(PREVIOUS_PRIMARY_RGB_KEY);
        window.localStorage.removeItem(PREVIOUS_SECONDARY_RGB_KEY);
        window.localStorage.removeItem(PREVIOUS_DARKPRIMARY_RGB_KEY);
        window.localStorage.removeItem(PREVIOUS_DARKSECONDARY_RGB_KEY);
      }} catch (_) {{
        removeThemeColorStyle();
      }}
    }}

    function dropRestoredThemeStyleIfUserChangedColors() {{
      if (!restoredThemeStyleActive) {{
        return;
      }}
      try {{
        if (window.localStorage.getItem(THEME_COLOR_ACTIVE_KEY) === "1") {{
          return;
        }}
        var currentPrimary = window.localStorage.getItem("themePrimary") || "";
        var currentSecondary = window.localStorage.getItem("themeSecondary") || "";
        if (
          currentPrimary !== restoredThemePrimary ||
          currentSecondary !== restoredThemeSecondary
        ) {{
          removeThemeColorStyle();
        }}
      }} catch (_) {{
      }}
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
      root.classList.toggle(
        ACTIVE_CLASS,
        Boolean(config.enabled && imageUrl)
      );
      root.classList.toggle(
        TOKEN_STATS_ACTIVE_CLASS,
        Boolean(config.enabled && config.detailed_token_stats_enabled)
      );
      applyThemeColors(config);
      updateTokenStatsEnhancement(Boolean(config.detailed_token_stats_enabled));
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

    function getCurrentStatsRange() {{
      var activeChip = document.querySelector(".stats-page .range-chip.active");
      var label = activeChip ? (activeChip.textContent || "") : "";
      if (/7|周|week/i.test(label)) {{
        return 7;
      }}
      if (/3|three/i.test(label)) {{
        return 3;
      }}
      return 1;
    }}

    function formatTokenNumber(value) {{
      var number = Number(value || 0);
      try {{
        return new Intl.NumberFormat(document.documentElement.lang || navigator.language || "zh-CN").format(number);
      }} catch (_) {{
        return String(Math.round(number));
      }}
    }}

    function formatTokenRate(value) {{
      var number = Number(value || 0);
      if (!Number.isFinite(number) || number <= 0) {{
        return "0.0%";
      }}
      return (number * 100).toFixed(1) + "%";
    }}

    function clearTokenStatsPanel() {{
      var panel = document.getElementById(TOKEN_STATS_PANEL_ID);
      if (panel) {{
        panel.remove();
      }}
    }}

    function stopTokenStatsEnhancement() {{
      detailedTokenStatsEnabled = false;
      clearTokenStatsPanel();
      document.documentElement.classList.remove(TOKEN_STATS_ACTIVE_CLASS);
      tokenStatsLastFetchKey = "";
      tokenStatsLastFetchAt = 0;
      tokenStatsInFlight = false;
      tokenStatsMutationMuted = false;
      if (tokenStatsRefreshTimer) {{
        window.clearTimeout(tokenStatsRefreshTimer);
        tokenStatsRefreshTimer = 0;
      }}
      if (tokenStatsPollTimer) {{
        window.clearInterval(tokenStatsPollTimer);
        tokenStatsPollTimer = 0;
      }}
      if (tokenStatsObserver) {{
        tokenStatsObserver.disconnect();
        tokenStatsObserver = null;
      }}
    }}

    function updateTokenStatsEnhancement(enabled) {{
      if (!enabled) {{
        stopTokenStatsEnhancement();
        return;
      }}
      detailedTokenStatsEnabled = true;
      ensureTokenStatsObserver();
      ensureTokenStatsClickListener();
      scheduleTokenStatsRefresh(120);
    }}

    function ensureTokenStatsObserver() {{
      if (tokenStatsObserver) {{
        return;
      }}
      tokenStatsObserver = new MutationObserver(function () {{
        if (!detailedTokenStatsEnabled || tokenStatsMutationMuted) {{
          return;
        }}
        scheduleTokenStatsRefresh(240);
      }});
      tokenStatsObserver.observe(document.body, {{
        childList: true,
        subtree: true,
      }});
      tokenStatsPollTimer = window.setInterval(function () {{
        if (detailedTokenStatsEnabled) {{
          scheduleTokenStatsRefresh(0);
        }}
      }}, 60000);
    }}

    function ensureTokenStatsClickListener() {{
      if (tokenStatsClickListenerReady) {{
        return;
      }}
      tokenStatsClickListenerReady = true;
      document.addEventListener("click", function (event) {{
        if (!detailedTokenStatsEnabled) {{
          return;
        }}
        var target = event.target && event.target.closest ? event.target.closest(".stats-page .range-chip") : null;
        if (target) {{
          scheduleTokenStatsRefresh(520, true);
        }}
      }}, true);
    }}

    function scheduleTokenStatsRefresh(delay, force) {{
      if (!detailedTokenStatsEnabled) {{
        return;
      }}
      if (tokenStatsRefreshTimer) {{
        window.clearTimeout(tokenStatsRefreshTimer);
      }}
      tokenStatsRefreshTimer = window.setTimeout(function () {{
        tokenStatsRefreshTimer = 0;
        refreshTokenStatsPanel(Boolean(force));
      }}, delay || 0);
    }}

    function shouldShowTokenStatsPanel() {{
      return Boolean(document.querySelector(".stats-page .token-grid"));
    }}

    function ensureTokenStatsPanel() {{
      var tokenGrid = document.querySelector(".stats-page .token-grid");
      if (!tokenGrid) {{
        clearTokenStatsPanel();
        return null;
      }}
      var panel = document.getElementById(TOKEN_STATS_PANEL_ID);
      if (!panel) {{
        panel = document.createElement("section");
        panel.id = TOKEN_STATS_PANEL_ID;
        panel.className = "astrbot-palette-token-detail-panel";
      }}
      if (panel.parentElement !== tokenGrid.parentElement || panel.previousElementSibling !== tokenGrid) {{
        tokenStatsMutationMuted = true;
        tokenGrid.insertAdjacentElement("afterend", panel);
        window.setTimeout(function () {{
          tokenStatsMutationMuted = false;
        }}, 0);
      }}
      return panel;
    }}

    function renderTokenStatsLoading(panel) {{
      panel.innerHTML = [
        '<div class="astrbot-palette-token-detail-head">',
        '  <div>',
        '    <div class="section-title">模型 Token 明细</div>',
        '    <div class="section-subtitle">正在读取每个模型的输入、输出与缓存命中。</div>',
        '  </div>',
        '</div>',
        '<div class="astrbot-palette-token-empty">正在加载...</div>',
      ].join("");
    }}

    function renderTokenStatsUnavailable(panel, message) {{
      panel.innerHTML = [
        '<div class="astrbot-palette-token-detail-head">',
        '  <div>',
        '    <div class="section-title">模型 Token 明细</div>',
        '    <div class="section-subtitle">当前环境无法读取模型 Token 明细。</div>',
        '  </div>',
        '</div>',
        '<div class="astrbot-palette-token-empty">' + escapeHtml(message || "当前 AstrBot 版本暂不支持。") + '</div>',
      ].join("");
    }}

    function renderTokenStatsPanel(panel, data, range) {{
      if (!data || data.supported === false) {{
        renderTokenStatsUnavailable(panel, data && data.message);
        return;
      }}
      var totals = data.totals || {{}};
      var models = Array.isArray(data.models) ? data.models : [];
      var modelRows = models.length
        ? models.map(function (model) {{
            return [
              '<div class="astrbot-palette-token-model-row">',
              '  <div class="astrbot-palette-token-model-name">',
              '    <strong>' + escapeHtml(model.provider_model || "Unknown") + '</strong>',
              '    <span>' + escapeHtml(model.provider_id || "unknown") + '</span>',
              '  </div>',
              '  <span>' + formatTokenNumber(model.calls) + '</span>',
              '  <span>' + formatTokenNumber(model.input_tokens) + '</span>',
              '  <span>' + formatTokenNumber(model.output_tokens) + '</span>',
              '  <span>' + formatTokenNumber(model.cached_tokens) + '</span>',
              '  <strong>' + formatTokenRate(model.cache_hit_rate) + '</strong>',
              '</div>',
            ].join("");
          }}).join("")
        : '<div class="astrbot-palette-token-empty">这个时间范围内还没有模型 Token 记录。</div>';
      panel.innerHTML = [
        '<div class="astrbot-palette-token-detail-head">',
        '  <div>',
        '    <div class="section-title">模型 Token 明细</div>',
        '    <div class="section-subtitle">最近 ' + formatTokenNumber(range) + ' 天，每个模型的输入、输出与缓存命中。</div>',
        '  </div>',
        '  <div class="astrbot-palette-token-range">跟随系统统计范围</div>',
        '</div>',
        '<div class="astrbot-palette-token-total-grid">',
        tokenMetricHtml("总 Token", totals.total_tokens),
        tokenMetricHtml("输入", totals.input_tokens),
        tokenMetricHtml("输出", totals.output_tokens),
        tokenMetricHtml("缓存命中", totals.cached_tokens),
        tokenMetricHtml("命中率", formatTokenRate(totals.cache_hit_rate), true),
        '</div>',
        '<div class="astrbot-palette-token-model-table">',
        '  <div class="astrbot-palette-token-model-row astrbot-palette-token-model-head">',
        '    <span>模型</span><span>调用</span><span>输入</span><span>输出</span><span>缓存命中</span><span>命中率</span>',
        '  </div>',
        modelRows,
        '</div>',
      ].join("");
    }}

    function tokenMetricHtml(label, value, raw) {{
      return [
        '<div class="astrbot-palette-token-metric">',
        '  <span>' + escapeHtml(label) + '</span>',
        '  <strong>' + escapeHtml(raw ? String(value) : formatTokenNumber(value)) + '</strong>',
        '</div>',
      ].join("");
    }}

    async function refreshTokenStatsPanel(force) {{
      if (!detailedTokenStatsEnabled) {{
        return;
      }}
      if (!shouldShowTokenStatsPanel()) {{
        clearTokenStatsPanel();
        return;
      }}
      var range = getCurrentStatsRange();
      var fetchKey = range + ":" + getToken();
      var now = Date.now();
      if (!force && fetchKey === tokenStatsLastFetchKey && now - tokenStatsLastFetchAt < 5000) {{
        return;
      }}
      if (tokenStatsInFlight) {{
        return;
      }}
      var panel = ensureTokenStatsPanel();
      if (!panel) {{
        return;
      }}
      tokenStatsInFlight = true;
      if (!panel.dataset.loaded) {{
        renderTokenStatsLoading(panel);
      }}
      try {{
        var token = getToken();
        var data = await fetchJson(TOKEN_STATS_URL + "?days=" + range, token);
        renderTokenStatsPanel(panel, data, range);
        panel.dataset.loaded = "1";
        tokenStatsLastFetchKey = fetchKey;
        tokenStatsLastFetchAt = Date.now();
      }} catch (error) {{
        if (!isExpectedAuthFailure(error)) {{
          console.warn("[AstrBot调色盘] 模型 Token 明细读取失败：", error);
        }}
        tokenStatsLastFetchKey = fetchKey;
        tokenStatsLastFetchAt = Date.now();
        tokenStatsMutationMuted = true;
        renderTokenStatsUnavailable(panel, "读取失败，请稍后重试。");
        window.setTimeout(function () {{
          tokenStatsMutationMuted = false;
        }}, 0);
      }} finally {{
        tokenStatsInFlight = false;
      }}
    }}

    function escapeHtml(value) {{
      return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {{
        return {{
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        }}[char] || char;
      }});
    }}

    async function postJson(url, token, body) {{
      var headers = buildHeaders(token, "application/json");
      headers["Content-Type"] = "application/json";
      var response = await fetch(withCacheBust(url), {{
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: headers,
        body: JSON.stringify(body || {{}}),
      }});
      if (!response.ok) {{
        throw new Error("HTTP " + response.status);
      }}
      return response.json();
    }}

    async function fetchBackground(url, token) {{
      if (!url) {{
        lastBackgroundUrl = "";
        lastBackgroundObjectUrl = "";
        return "";
      }}
      if (backgroundObjectUrlCache[url]) {{
        lastBackgroundUrl = url;
        lastBackgroundObjectUrl = backgroundObjectUrlCache[url];
        return lastBackgroundObjectUrl;
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
      var objectUrl = URL.createObjectURL(blob);
      backgroundObjectUrlCache[url] = objectUrl;
      lastBackgroundUrl = url;
      lastBackgroundObjectUrl = objectUrl;
      return objectUrl;
    }}

    async function applyDirectionalBackground(config, token, animate) {{
      var requestSeq = backgroundRequestSeq + 1;
      backgroundRequestSeq = requestSeq;
      var orientation = getViewportOrientation();
      var backgroundUrl = pickBackgroundUrl(config, orientation);
      if (!backgroundUrl) {{
        currentBackgroundUrl = "";
        currentObjectUrl = "";
        await applyBackgroundLayer("", false);
        applyConfig(config, "");
        return "";
      }}
      if (backgroundUrl === currentBackgroundUrl && currentObjectUrl) {{
        await applyBackgroundLayer(currentObjectUrl, false);
        applyConfig(config, currentObjectUrl);
        return currentObjectUrl;
      }}
      var imageUrl = "";
      try {{
        imageUrl = await fetchBackground(backgroundUrl, token);
      }} catch (error) {{
        if (requestSeq !== backgroundRequestSeq) {{
          return currentObjectUrl || "";
        }}
        throw error;
      }}
      await decodeBackgroundImage(imageUrl);
      if (
        requestSeq !== backgroundRequestSeq ||
        pickBackgroundUrl(config, getViewportOrientation()) !== backgroundUrl
      ) {{
        return currentObjectUrl || "";
      }}
      var applied = await applyBackgroundLayer(imageUrl, Boolean(animate), function () {{
        return (
          requestSeq === backgroundRequestSeq &&
          pickBackgroundUrl(config, getViewportOrientation()) === backgroundUrl
        );
      }});
      if (!applied) {{
        return currentObjectUrl || "";
      }}
      currentBackgroundUrl = backgroundUrl;
      currentObjectUrl = imageUrl;
      applyConfig(config, imageUrl);
      return imageUrl;
    }}

    async function resolveConfigForRefresh(token, allowInitialRandom) {{
      var config = await fetchJson(CONFIG_URL, token);
      var orientation = getViewportOrientation();
      var orientationImages = orientation === "portrait"
        ? config.portrait_background_images
        : config.landscape_background_images;
      var currentImage = orientation === "portrait"
        ? config.portrait_background_image
        : config.landscape_background_image;
      var fallbackImages = config.background_images;
      var otherImages = orientation === "portrait"
        ? config.landscape_background_images
        : config.portrait_background_images;
      var hasRandomPool = (
        (Array.isArray(orientationImages) && (
          orientationImages.length > 1 ||
          (orientationImages.length === 1 && !currentImage)
        )) ||
        (Array.isArray(fallbackImages) && fallbackImages.length > 0) ||
        (Array.isArray(otherImages) && otherImages.length > 0)
      );
      if (
        allowInitialRandom &&
        initialRandomPending &&
        config.enabled &&
        config.random_background_on_load &&
        hasRandomPool
      ) {{
        initialRandomPending = false;
        try {{
          var randomResponse = await postJson(RANDOM_SELECT_URL, token, {{
            orientation: orientation,
          }});
          if (randomResponse && randomResponse.config) {{
            return randomResponse.config;
          }}
        }} catch (error) {{
          if (!isExpectedAuthFailure(error)) {{
            console.warn("[AstrBot调色盘] 随机背景切换失败：", error);
          }}
        }}
      }}
      if (allowInitialRandom) {{
        initialRandomPending = false;
      }}
      return config;
    }}

    async function refreshPalette(options) {{
      if (loading) {{
        pendingRefresh = true;
        return;
      }}
      loading = true;
      try {{
        var token = getToken();
        lastToken = token;
        var config = await resolveConfigForRefresh(
          token,
          Boolean(options && options.allowInitialRandom) || initialRandomPending
        );

        if (!config.enabled) {{
          setInactive();
          removeStyleElement();
          return;
        }}

        var css = await fetchText(THEME_URL, token);
        ensureStyleElement(css);
        lastConfig = config;
        try {{
          await applyDirectionalBackground(
            config,
            token,
            Boolean(options && options.animateBackground)
          );
        }} catch (error) {{
          if (!currentObjectUrl) {{
            setInactive();
            removeStyleElement();
          }}
          throw error;
        }}
      }} catch (error) {{
        if (!currentObjectUrl) {{
          setInactive();
          removeStyleElement();
        }}
        if (!isExpectedAuthFailure(error)) {{
          console.warn("[AstrBot调色盘] 背景刷新失败：", error);
        }}
      }} finally {{
        loading = false;
        if (pendingRefresh) {{
          pendingRefresh = false;
          window.setTimeout(function () {{
            refreshPalette();
          }}, 80);
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
    function scheduleDirectionalBackgroundRefresh() {{
      if (!lastConfig || !lastConfig.enabled) {{
        return;
      }}
      window.clearTimeout(backgroundResizeTimer);
      backgroundResizeTimer = window.setTimeout(function () {{
        applyDirectionalBackground(lastConfig, lastToken || getToken(), true).catch(function (error) {{
          if (!isExpectedAuthFailure(error)) {{
            console.warn("[AstrBot调色盘] 方向背景切换失败：", error);
          }}
        }});
      }}, 150);
    }}

    window.addEventListener("resize", scheduleDirectionalBackgroundRefresh, {{ passive: true }});
    window.addEventListener("orientationchange", scheduleDirectionalBackgroundRefresh, {{ passive: true }});
    try {{
      var orientationMedia = window.matchMedia("(orientation: portrait)");
      if (orientationMedia && orientationMedia.addEventListener) {{
        orientationMedia.addEventListener("change", scheduleDirectionalBackgroundRefresh);
      }} else if (orientationMedia && orientationMedia.addListener) {{
        orientationMedia.addListener(scheduleDirectionalBackgroundRefresh);
      }}
    }} catch (_) {{
    }}
    window.addEventListener("beforeunload", revokeObjectUrls);

    window.setInterval(function () {{
      dropRestoredThemeStyleIfUserChangedColors();
      var token = getToken();
      if (token !== lastToken) {{
        refreshPalette();
      }}
    }}, 1500);

    bootstrapRecommendedDarkTheme();
    refreshPalette({{ allowInitialRandom: true }});
  }})();"""
