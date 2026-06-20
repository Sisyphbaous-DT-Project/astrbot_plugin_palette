from __future__ import annotations

import base64
from contextlib import suppress
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from urllib.parse import quote
from uuid import uuid4

from astrbot.api.star import Context, Star, register
from astrbot.api.web import (
    error_response,
    file_response,
    json_response,
    request,
    stream_response,
)

from .palette.constants import (
    ALLOWED_BACKGROUND_EXTENSIONS,
    AUTHOR,
    DESCRIPTION,
    MAX_BACKGROUND_BYTES,
    PLUGIN_NAME,
    ROUTE_PREFIX,
    VERSION,
)
from .palette.injector import ensure_dashboard_injection
from .palette.paths import PalettePaths
from .palette.theme import build_theme_css


@register(PLUGIN_NAME, AUTHOR, DESCRIPTION, VERSION)
class PalettePlugin(Star):
    """AstrBot 调色盘插件入口。"""

    def __init__(self, context: Context, config: Mapping[str, Any] | None = None) -> None:
        super().__init__(context)
        self.config: Mapping[str, Any] = config if config is not None else {}
        self.paths = PalettePaths()
        self.injection_status = ensure_dashboard_injection(self.paths)

        context.register_web_api(
            f"{ROUTE_PREFIX}/status",
            self.get_status,
            ["GET"],
            "获取 AstrBot 调色盘状态",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/theme.css",
            self.get_theme_css,
            ["GET"],
            "获取 AstrBot 调色盘主题 CSS",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/config",
            self.get_config,
            ["GET"],
            "获取 AstrBot 调色盘配置摘要",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/config",
            self.save_config,
            ["POST"],
            "保存 AstrBot 调色盘配置",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/background-preview",
            self.get_background_preview,
            ["GET"],
            "获取 AstrBot 调色盘当前背景预览",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/upload-background",
            self.upload_background,
            ["POST"],
            "上传 AstrBot 调色盘背景图片",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/backgrounds/<filename>",
            self.get_background,
            ["GET"],
            "读取 AstrBot 调色盘背景图片",
        )

    async def get_status(self):
        injection_status = ensure_dashboard_injection(self.paths)
        self.injection_status = injection_status
        return json_response(
            {
                "plugin": {
                    "name": PLUGIN_NAME,
                    "version": VERSION,
                    "enabled": self._config_bool("enabled", True),
                },
                "paths": self.paths.to_public_dict(),
                "injection": injection_status.to_dict(),
            }
        )

    async def get_config(self):
        return json_response(self._public_config())

    async def save_config(self):
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("配置格式不正确。")

        try:
            config = self._normalize_config(payload)
            self.injection_status = ensure_dashboard_injection(self.paths)
            self._save_config(config)
        except ValueError as exc:
            return error_response(str(exc))

        return json_response(
            {
                "message": "设置已保存。",
                "config": self._public_config(),
            }
        )

    async def upload_background(self):
        files = await request.files()
        upload_file = files.get("file")
        if upload_file is None:
            return error_response("请选择要上传的背景图片。")

        previous_background = self._config_str("background_image", "")
        try:
            saved_filename = await self._save_background_upload(upload_file)
            config = self._normalize_config(
                {
                    **self._public_config(),
                    "background_image": saved_filename,
                }
            )
            self.injection_status = ensure_dashboard_injection(self.paths)
            self._save_config(config)
            self._cleanup_replaced_background(previous_background, saved_filename)
        except ValueError as exc:
            return error_response(str(exc))

        return json_response(
            {
                "message": "背景图片已上传。",
                "background_image": saved_filename,
                "background_url": self._background_url(saved_filename),
                "config": self._public_config(),
            }
        )

    async def get_background_preview(self):
        filename = self._config_str("background_image", "")
        if not filename:
            return json_response(
                {
                    "background_image": "",
                    "data_url": "",
                }
            )

        try:
            path = self._resolve_background(filename, must_exist=True)
        except ValueError as exc:
            return error_response(str(exc), status_code=404)

        content_type = ALLOWED_BACKGROUND_EXTENSIONS[path.suffix.lower()]
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return json_response(
            {
                "background_image": filename,
                "data_url": f"data:{content_type};base64,{data}",
            }
        )

    async def get_background(self, filename: str):
        try:
            path = self._resolve_background(filename)
        except ValueError as exc:
            return error_response(str(exc), status_code=404)

        if not path.is_file():
            return error_response("背景图片不存在。", status_code=404)

        content_type = ALLOWED_BACKGROUND_EXTENSIONS[path.suffix.lower()]
        return file_response(
            path,
            content_type=content_type,
            headers={
                "Cache-Control": "private, max-age=300",
                "X-Content-Type-Options": "nosniff",
            },
        )

    async def get_theme_css(self):
        css = build_theme_css(self._public_config())
        return stream_response(
            [css],
            content_type="text/css; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    def _public_config(self) -> dict[str, Any]:
        return {
            "enabled": self._config_bool("enabled", True),
            "background_image": self._config_str("background_image", ""),
            "background_fit": self._config_str("background_fit", "cover"),
            "background_position": self._config_str(
                "background_position",
                "center center",
            ),
            "background_blur": self._config_int("background_blur", 0),
            "background_dim": self._config_float("background_dim", 0.5),
            "surface_opacity": self._config_float("surface_opacity", 0.0),
            "text_enhancement_mode": self._config_str(
                "text_enhancement_mode",
                "soft_shadow",
            ),
            "text_enhancement_strength": self._config_float(
                "text_enhancement_strength",
                1.0,
            ),
            "background_grayscale": self._config_float("background_grayscale", 0.0),
            "background_brightness": self._config_float(
                "background_brightness",
                1.0,
            ),
            "background_contrast": self._config_float("background_contrast", 1.0),
            "background_saturation": self._config_float(
                "background_saturation",
                1.0,
            ),
            "advanced_css": self._config_str("advanced_css", ""),
            "background_url": self._background_url(
                self._config_str("background_image", ""),
            ),
        }

    def _config_bool(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        return value if isinstance(value, bool) else default

    def _config_str(self, key: str, default: str) -> str:
        value = self.config.get(key, default)
        return value if isinstance(value, str) else default

    def _config_int(self, key: str, default: int) -> int:
        value = self.config.get(key, default)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return default

    def _config_float(self, key: str, default: float) -> float:
        value = self.config.get(key, default)
        if isinstance(value, bool):
            return default
        if isinstance(value, int | float):
            return float(value)
        return default

    def _normalize_config(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        current = self._public_config()
        background_image = str(
            payload.get("background_image", current["background_image"]) or ""
        ).strip()
        if background_image:
            self._resolve_background(background_image, must_exist=True)

        background_fit = str(
            payload.get("background_fit", current["background_fit"]) or "cover"
        ).strip()
        if background_fit not in {"cover", "contain", "auto"}:
            raise ValueError("背景填充方式不正确。")

        background_position = str(
            payload.get("background_position", current["background_position"])
            or "center center"
        ).strip()
        if not background_position or len(background_position) > 80:
            raise ValueError("背景位置不正确。")

        text_enhancement_mode = str(
            payload.get(
                "text_enhancement_mode",
                current["text_enhancement_mode"],
            )
            or "soft_shadow"
        ).strip()
        if text_enhancement_mode not in {"off", "soft_shadow", "stroke"}:
            raise ValueError("文字增强模式不正确。")

        return {
            "enabled": self._normalize_bool(
                payload.get("enabled", current["enabled"]),
                current["enabled"],
            ),
            "background_image": background_image,
            "background_fit": background_fit,
            "background_position": background_position,
            "background_blur": self._clamp_int(
                payload.get("background_blur", current["background_blur"]),
                0,
                40,
            ),
            "background_dim": self._clamp_float(
                payload.get("background_dim", current["background_dim"]),
                0.0,
                0.95,
            ),
            "surface_opacity": self._clamp_float(
                payload.get("surface_opacity", current["surface_opacity"]),
                0.0,
                1.0,
            ),
            "text_enhancement_mode": text_enhancement_mode,
            "text_enhancement_strength": self._clamp_float(
                payload.get(
                    "text_enhancement_strength",
                    current["text_enhancement_strength"],
                ),
                0.0,
                1.0,
            ),
            "background_grayscale": self._clamp_float(
                payload.get("background_grayscale", current["background_grayscale"]),
                0.0,
                1.0,
            ),
            "background_brightness": self._clamp_float(
                payload.get(
                    "background_brightness",
                    current["background_brightness"],
                ),
                0.5,
                1.5,
            ),
            "background_contrast": self._clamp_float(
                payload.get("background_contrast", current["background_contrast"]),
                0.5,
                1.5,
            ),
            "background_saturation": self._clamp_float(
                payload.get(
                    "background_saturation",
                    current["background_saturation"],
                ),
                0.0,
                2.0,
            ),
            "advanced_css": self._normalize_advanced_css(
                payload.get("advanced_css", current["advanced_css"])
            ),
        }

    def _save_config(self, config: dict[str, Any]) -> None:
        if hasattr(self.config, "save_config"):
            self.config.save_config(config)  # type: ignore[attr-defined]
            return
        if isinstance(self.config, MutableMapping):
            self.config.clear()
            self.config.update(config)
            return
        self.config = config

    async def _save_background_upload(self, upload_file) -> str:
        source_name = upload_file.filename or "background.png"
        suffix = Path(source_name).suffix.lower()
        if suffix not in ALLOWED_BACKGROUND_EXTENSIONS:
            raise ValueError("仅支持 jpg、png、webp、gif 图片。")

        if (
            upload_file.content_length is not None
            and upload_file.content_length > MAX_BACKGROUND_BYTES
        ):
            raise ValueError("背景图片不能超过 10MB。")

        filename = f"background-{uuid4().hex}{suffix}"
        self.paths.ensure_runtime_dirs()
        target_path = self.paths.resolve_background_file(filename)
        first_bytes = b""
        total_size = 0
        temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")

        try:
            await upload_file.seek(0)
        except Exception:
            pass

        try:
            with temp_path.open("wb") as output:
                while True:
                    chunk = await upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > MAX_BACKGROUND_BYTES:
                        raise ValueError("背景图片不能超过 10MB。")
                    if len(first_bytes) < 16:
                        first_bytes += chunk[: 16 - len(first_bytes)]
                    output.write(chunk)

            if total_size == 0:
                raise ValueError("背景图片内容为空。")
            if not self._looks_like_image(first_bytes, suffix):
                raise ValueError("图片内容与文件类型不匹配。")

            temp_path.replace(target_path)
        except Exception:
            with suppress(FileNotFoundError):
                temp_path.unlink()
            raise
        return filename

    def _resolve_background(self, filename: str, *, must_exist: bool = False) -> Path:
        path = self.paths.resolve_background_file(filename)
        if path.suffix.lower() not in ALLOWED_BACKGROUND_EXTENSIONS:
            raise ValueError("背景图片文件类型不受支持。")
        if must_exist and not path.is_file():
            raise ValueError("背景图片不存在，请重新上传。")
        return path

    def _cleanup_replaced_background(
        self,
        previous_filename: str,
        current_filename: str,
    ) -> None:
        previous_filename = previous_filename.strip()
        if not previous_filename or previous_filename == current_filename:
            return
        with suppress(ValueError, FileNotFoundError):
            previous_path = self._resolve_background(previous_filename)
            previous_path.unlink()

    def _background_url(self, filename: str) -> str:
        filename = filename.strip()
        if not filename:
            return ""
        return (
            f"/api/v1/plugins/extensions/{PLUGIN_NAME}/backgrounds/"
            f"{quote(filename)}"
        )

    @staticmethod
    def _normalize_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off", ""}:
                return False
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        return default

    @staticmethod
    def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            return minimum
        try:
            number = int(value)
        except (TypeError, ValueError):
            return minimum
        return min(max(number, minimum), maximum)

    @staticmethod
    def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
        if isinstance(value, bool):
            return minimum
        try:
            number = float(value)
        except (TypeError, ValueError):
            return minimum
        return min(max(number, minimum), maximum)

    @staticmethod
    def _normalize_advanced_css(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value[:20000]

    @staticmethod
    def _looks_like_image(content: bytes, suffix: str) -> bool:
        if suffix in {".jpg", ".jpeg"}:
            return content.startswith(b"\xff\xd8\xff")
        if suffix == ".png":
            return content.startswith(b"\x89PNG\r\n\x1a\n")
        if suffix == ".webp":
            return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        if suffix == ".gif":
            return content.startswith((b"GIF87a", b"GIF89a"))
        return False
