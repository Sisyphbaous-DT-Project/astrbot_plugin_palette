from __future__ import annotations

import base64
import random
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
from .palette.colors import extract_theme_colors, normalize_hex_color
from .palette.injector import ensure_dashboard_injection
from .palette.paths import PalettePaths
from .palette.theme import build_theme_css
from .palette.thumbnails import (
    delete_background_thumbnails,
    ensure_background_thumbnail,
)


@register(PLUGIN_NAME, AUTHOR, DESCRIPTION, VERSION)
class PalettePlugin(Star):
    """AstrBot 调色盘插件入口。"""

    def __init__(self, context: Context, config: Mapping[str, Any] | None = None) -> None:
        super().__init__(context)
        self.config: Mapping[str, Any] = config if config is not None else {}
        self.paths = PalettePaths()
        self.injection_status = ensure_dashboard_injection(self.paths)
        self._ensure_config_for_existing_background()

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
            f"{ROUTE_PREFIX}/theme-colors/recalculate",
            self.recalculate_theme_colors,
            ["POST"],
            "重新读取背景图主题色",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/background-preview",
            self.get_background_preview,
            ["GET"],
            "获取 AstrBot 调色盘当前背景预览",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/background-thumbnail",
            self.get_background_thumbnail,
            ["GET"],
            "获取 AstrBot 调色盘背景缩略图",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/upload-background",
            self.upload_background,
            ["POST"],
            "上传 AstrBot 调色盘背景图片",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/backgrounds/select",
            self.select_background,
            ["POST"],
            "切换 AstrBot 调色盘当前背景图片",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/backgrounds/delete",
            self.delete_background,
            ["POST"],
            "删除 AstrBot 调色盘背景图片",
        )
        context.register_web_api(
            f"{ROUTE_PREFIX}/backgrounds/random-select",
            self.random_select_background,
            ["POST"],
            "随机切换 AstrBot 调色盘背景图片",
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
            config = self._with_theme_colors(config)
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

        try:
            saved_filename = await self._save_background_upload(upload_file)
            config = self._normalize_config(self._public_config())
            background_images = self._append_background_image(
                config["background_images"],
                saved_filename,
            )
            config = {
                **config,
                "background_images": background_images,
            }
            self.injection_status = ensure_dashboard_injection(self.paths)
            self._save_config(config)
        except ValueError as exc:
            return error_response(str(exc))

        return json_response(
            {
                "message": "背景图片已加入图库。",
                "background_image": saved_filename,
                "background_url": self._background_url(saved_filename),
                "config": self._public_config(),
            }
        )

    async def select_background(self):
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("背景图片参数不正确。")

        filename = str(payload.get("background_image") or "").strip()
        if not filename:
            return error_response("请选择要切换的背景图片。")

        try:
            config = self._normalize_config(
                {
                    **self._public_config(),
                    "background_image": filename,
                }
            )
            config = self._with_theme_colors(config, force=True)
            self._save_config(config)
        except ValueError as exc:
            return error_response(str(exc))

        return json_response(
            {
                "message": "背景图片已切换。",
                "config": self._public_config(),
            }
        )

    async def delete_background(self):
        payload = await request.json(default={})
        if not isinstance(payload, dict):
            return error_response("背景图片参数不正确。")

        filename = str(payload.get("background_image") or "").strip()
        if not filename:
            return error_response("请选择要删除的背景图片。")

        try:
            config = self._normalize_config(self._public_config())
            if filename not in config["background_images"]:
                raise ValueError("背景图片不在图库中。")

            target_path = self._resolve_background(filename)
            with suppress(FileNotFoundError):
                target_path.unlink()
            delete_background_thumbnails(self.paths.thumbnail_dir, filename)

            background_images = [
                item for item in config["background_images"] if item != filename
            ]
            current_background = config["background_image"]
            next_background = current_background
            should_refresh_colors = False
            if current_background == filename:
                next_background = background_images[0] if background_images else ""
                should_refresh_colors = True

            config = {
                **config,
                "background_image": next_background,
                "background_images": background_images,
            }
            if should_refresh_colors:
                config = self._with_theme_colors(config, force=True)
            self._save_config(config)
        except ValueError as exc:
            return error_response(str(exc))

        return json_response(
            {
                "message": "背景图片已删除。",
                "config": self._public_config(),
            }
        )

    async def random_select_background(self):
        try:
            config = self._normalize_config(self._public_config())
            background_images = config["background_images"]
            if not background_images:
                raise ValueError("图库中还没有可随机的背景图片。")

            current_background = config["background_image"]
            if len(background_images) == 1 and current_background == background_images[0]:
                return json_response(
                    {
                        "message": "图库中只有当前背景，无需随机切换。",
                        "config": self._public_config(),
                    }
                )

            candidates = [
                filename
                for filename in background_images
                if filename != current_background
            ]
            if not candidates:
                candidates = background_images
            selected = random.choice(candidates)
            config = {
                **config,
                "background_image": selected,
            }
            config = self._with_theme_colors(config, force=True)
            self._save_config(config)
        except ValueError as exc:
            return error_response(str(exc))

        return json_response(
            {
                "message": "背景图片已随机切换。",
                "config": self._public_config(),
            }
        )

    async def recalculate_theme_colors(self):
        try:
            config = self._with_theme_colors(
                self._normalize_config(self._public_config()),
                force=True,
            )
            self._save_config(config)
        except ValueError as exc:
            return error_response(str(exc))

        return json_response(
            {
                "message": "主题色已重新读取。",
                "config": self._public_config(),
            }
        )

    async def get_background_preview(self):
        filename = str(
            request.query.get("filename") or self._config_str("background_image", "")
        ).strip()
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

    async def get_background_thumbnail(self):
        filename = str(
            request.query.get("filename") or self._config_str("background_image", "")
        ).strip()
        if not filename:
            return json_response(
                {
                    "background_image": "",
                    "data_url": "",
                }
            )

        try:
            path = self._resolve_background(filename, must_exist=True)
            thumbnail = ensure_background_thumbnail(
                path,
                self.paths.thumbnail_dir,
                filename,
            )
        except ValueError as exc:
            return error_response(str(exc), status_code=404)

        data = base64.b64encode(thumbnail.path.read_bytes()).decode("ascii")
        return json_response(
            {
                "background_image": filename,
                "content_type": thumbnail.content_type,
                "data_url": f"data:{thumbnail.content_type};base64,{data}",
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
        background_image = self._config_str("background_image", "").strip()
        background_images = self._public_background_images(background_image)
        if background_image and background_image not in background_images:
            background_image = ""

        return {
            "enabled": self._config_bool("enabled", True),
            "background_image": background_image,
            "background_images": background_images,
            "background_items": [
                self._background_item(filename, filename == background_image)
                for filename in background_images
            ],
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
            "random_background_on_load": self._config_bool(
                "random_background_on_load",
                False,
            ),
            "auto_theme_enabled": self._config_bool("auto_theme_enabled", True),
            "theme_primary": normalize_hex_color(
                self._config_str("theme_primary", "")
            ),
            "theme_secondary": normalize_hex_color(
                self._config_str("theme_secondary", "")
            ),
            "advanced_css": self._config_str("advanced_css", ""),
            "background_url": self._background_url(background_image),
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
        background_images = self._normalize_background_images(
            payload.get("background_images", current["background_images"])
        )
        background_image = str(
            payload.get("background_image", current["background_image"]) or ""
        ).strip()
        if background_image:
            self._resolve_background(background_image, must_exist=True)
            background_images = self._append_background_image(
                background_images,
                background_image,
            )

        background_fit = str(
            payload.get("background_fit", current["background_fit"]) or "cover"
        ).strip()
        if background_fit not in {"cover", "contain", "auto", "stretch"}:
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

        theme_primary = normalize_hex_color(
            payload.get("theme_primary", current["theme_primary"])
        )
        theme_secondary = normalize_hex_color(
            payload.get("theme_secondary", current["theme_secondary"])
        )

        return {
            "enabled": self._normalize_bool(
                payload.get("enabled", current["enabled"]),
                current["enabled"],
            ),
            "background_image": background_image,
            "background_images": background_images,
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
            "random_background_on_load": self._normalize_bool(
                payload.get(
                    "random_background_on_load",
                    current["random_background_on_load"],
                ),
                current["random_background_on_load"],
            ),
            "auto_theme_enabled": self._normalize_bool(
                payload.get("auto_theme_enabled", current["auto_theme_enabled"]),
                current["auto_theme_enabled"],
            ),
            "theme_primary": theme_primary,
            "theme_secondary": theme_secondary,
            "advanced_css": self._normalize_advanced_css(
                payload.get("advanced_css", current["advanced_css"])
            ),
        }

    def _ensure_config_for_existing_background(self) -> None:
        with suppress(ValueError):
            public_config = self._public_config()
            current = self._normalize_config(public_config)
            config = self._with_theme_colors(current)
            raw_background_images = self.config.get("background_images", [])
            if config != current or raw_background_images != config["background_images"]:
                self._save_config(config)

    def _with_theme_colors(
        self,
        config: dict[str, Any],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        filename = str(config.get("background_image") or "").strip()
        if not filename:
            if force:
                config = {**config, "theme_primary": "", "theme_secondary": ""}
            return config

        if (
            not force
            and normalize_hex_color(config.get("theme_primary"))
            and normalize_hex_color(config.get("theme_secondary"))
        ):
            return config

        background_path = self._resolve_background(filename, must_exist=True)
        colors = extract_theme_colors(background_path)
        return {
            **config,
            **colors.to_dict(),
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
        if (
            upload_file.content_length is not None
            and upload_file.content_length > MAX_BACKGROUND_BYTES
        ):
            raise ValueError("背景图片不能超过 10MB。")

        self.paths.ensure_runtime_dirs()
        background_id = uuid4().hex
        first_bytes = b""
        total_size = 0
        temp_path = self.paths.background_dir / f"background-{background_id}.upload.tmp"
        target_path: Path | None = None

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
            detected_suffix = self._detect_image_suffix(first_bytes)
            if detected_suffix is None:
                raise ValueError("仅支持 jpg、png、webp、gif 图片。")

            # 以真实文件头为准，兼容“jpg 文件名里装着 png 内容”的图片。
            filename = f"background-{background_id}{detected_suffix}"
            target_path = self.paths.resolve_background_file(filename)
            temp_path.replace(target_path)
            with suppress(Exception):
                ensure_background_thumbnail(
                    target_path,
                    self.paths.thumbnail_dir,
                    filename,
                )
        except Exception:
            with suppress(FileNotFoundError):
                temp_path.unlink()
            if target_path is not None:
                with suppress(FileNotFoundError):
                    target_path.unlink()
            raise
        return filename

    def _resolve_background(self, filename: str, *, must_exist: bool = False) -> Path:
        path = self.paths.resolve_background_file(filename)
        if path.suffix.lower() not in ALLOWED_BACKGROUND_EXTENSIONS:
            raise ValueError("背景图片文件类型不受支持。")
        if must_exist and not path.is_file():
            raise ValueError("背景图片不存在，请重新上传。")
        return path

    def _background_url(self, filename: str) -> str:
        filename = filename.strip()
        if not filename:
            return ""
        return (
            f"/api/v1/plugins/extensions/{PLUGIN_NAME}/backgrounds/"
            f"{quote(filename)}"
        )

    def _background_preview_url(self, filename: str) -> str:
        filename = filename.strip()
        if not filename:
            return ""
        return (
            f"/api/v1/plugins/extensions/{PLUGIN_NAME}/background-preview"
            f"?filename={quote(filename)}"
        )

    def _background_thumbnail_url(self, filename: str) -> str:
        filename = filename.strip()
        if not filename:
            return ""
        return (
            f"/api/v1/plugins/extensions/{PLUGIN_NAME}/background-thumbnail"
            f"?filename={quote(filename)}"
        )

    def _background_item(self, filename: str, selected: bool) -> dict[str, Any]:
        return {
            "filename": filename,
            "url": self._background_url(filename),
            "thumbnail_url": self._background_thumbnail_url(filename),
            "preview_url": self._background_preview_url(filename),
            "selected": selected,
        }

    def _public_background_images(self, current_background: str) -> list[str]:
        background_images = self._normalize_background_images(
            self.config.get("background_images", [])
        )
        if current_background:
            with suppress(ValueError):
                self._resolve_background(current_background, must_exist=True)
                background_images = self._append_background_image(
                    background_images,
                    current_background,
                )
        return background_images

    def _normalize_background_images(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []

        background_images: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            filename = item.strip()
            if not filename or filename in background_images:
                continue
            with suppress(ValueError):
                self._resolve_background(filename, must_exist=True)
                background_images.append(filename)
        return background_images

    @staticmethod
    def _append_background_image(
        background_images: list[str],
        filename: str,
    ) -> list[str]:
        filename = filename.strip()
        if not filename or filename in background_images:
            return list(background_images)
        return [*background_images, filename]

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
    def _detect_image_suffix(content: bytes) -> str | None:
        if content.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
            return ".webp"
        if content.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        return None
