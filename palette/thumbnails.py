from __future__ import annotations

import warnings
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


THUMBNAIL_MAX_SIZE = 320
THUMBNAIL_CONTENT_TYPES = {
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
}

_THUMBNAIL_SUFFIXES = (".webp", ".jpg")
_RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


@dataclass(frozen=True)
class ThumbnailResult:
    """已生成或命中的缩略图文件。"""

    path: Path
    content_type: str


def ensure_background_thumbnail(
    source_path: Path,
    thumbnail_dir: Path,
    background_filename: str,
) -> ThumbnailResult:
    """生成并返回背景图的 320px 缩略图缓存。"""

    if not source_path.is_file():
        raise ValueError("背景图片不存在，请重新上传。")

    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    cached = _find_fresh_thumbnail(source_path, thumbnail_dir, background_filename)
    if cached is not None:
        return cached

    try:
        thumbnail = _build_thumbnail_image(source_path)
    except (
        OSError,
        UnidentifiedImageError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("缩略图生成失败。") from exc

    webp_path = thumbnail_dir / _thumbnail_filename(background_filename, ".webp")
    jpg_path = thumbnail_dir / _thumbnail_filename(background_filename, ".jpg")

    try:
        _save_webp(thumbnail, webp_path)
    except Exception:
        _save_jpeg(thumbnail, jpg_path)
        with suppress(FileNotFoundError):
            webp_path.unlink()
        return ThumbnailResult(jpg_path, THUMBNAIL_CONTENT_TYPES[".jpg"])

    with suppress(FileNotFoundError):
        jpg_path.unlink()
    return ThumbnailResult(webp_path, THUMBNAIL_CONTENT_TYPES[".webp"])


def delete_background_thumbnails(thumbnail_dir: Path, background_filename: str) -> None:
    """删除某张背景图对应的缩略图缓存。"""

    for suffix in _THUMBNAIL_SUFFIXES:
        with suppress(OSError):
            (thumbnail_dir / _thumbnail_filename(background_filename, suffix)).unlink()


def _find_fresh_thumbnail(
    source_path: Path,
    thumbnail_dir: Path,
    background_filename: str,
) -> ThumbnailResult | None:
    source_mtime = source_path.stat().st_mtime
    for suffix in _THUMBNAIL_SUFFIXES:
        path = thumbnail_dir / _thumbnail_filename(background_filename, suffix)
        if path.is_file() and path.stat().st_mtime >= source_mtime:
            return ThumbnailResult(path, THUMBNAIL_CONTENT_TYPES[suffix])
    return None


def _thumbnail_filename(background_filename: str, suffix: str) -> str:
    stem = Path(background_filename).stem
    if not stem:
        raise ValueError("背景图片文件名不正确。")
    digest = sha256(background_filename.encode("utf-8")).hexdigest()[:16]
    return f"{stem}-{digest}{suffix}"


def _build_thumbnail_image(source_path: Path) -> Image.Image:
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source_path) as image:
            image.seek(0)
            frame = ImageOps.exif_transpose(image)
            thumbnail = frame.copy()

    thumbnail.thumbnail(
        (THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE),
        _RESAMPLE_LANCZOS,
    )
    if _has_alpha(thumbnail):
        return thumbnail.convert("RGBA")
    return thumbnail.convert("RGB")


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        alpha = image.getchannel("A")
        return alpha.getextrema()[0] < 255
    return image.mode == "P" and "transparency" in image.info


def _save_webp(image: Image.Image, target_path: Path) -> None:
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    try:
        image.save(temp_path, "WEBP", quality=72, method=4)
        temp_path.replace(target_path)
    except Exception:
        with suppress(FileNotFoundError):
            temp_path.unlink()
        raise


def _save_jpeg(image: Image.Image, target_path: Path) -> None:
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    try:
        jpeg_image = _flatten_for_jpeg(image)
        jpeg_image.save(
            temp_path,
            "JPEG",
            quality=78,
            optimize=True,
            progressive=True,
        )
        temp_path.replace(target_path)
    except Exception as exc:
        with suppress(FileNotFoundError):
            temp_path.unlink()
        raise ValueError("缩略图生成失败。") from exc


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        return image.convert("RGB")

    background = Image.new("RGB", image.size, (246, 246, 246))
    background.paste(image, mask=image.getchannel("A"))
    return background
