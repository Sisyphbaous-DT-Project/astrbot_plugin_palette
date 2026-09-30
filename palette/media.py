"""动态背景素材的类型识别、SVG 清洗与封面处理。

素材类型：静态图片、动图（GIF/动态 WebP）、视频（MP4/WebM）、SVG。
封面是一张静态代表画面：动图由服务端取代表帧生成，视频和 SVG 由
浏览器在上传时生成并与原素材一次提交，服务端校验合法性后落盘，供静态兜底、
缩略图和主题色提取复用。
"""

from __future__ import annotations

import asyncio
import re
import warnings
from collections import OrderedDict
from contextlib import suppress
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from .constants import (
    COVER_MAX_EDGE,
    MAX_BACKGROUND_BYTES,
    MAX_COVER_SOURCE_BYTES,
    MAX_SVG_BYTES,
    MAX_VIDEO_BYTES,
    MAX_UPLOAD_BYTES,
    MEDIA_BUNDLE_MAGIC,
    SVG_BACKGROUND_EXTENSIONS,
    VIDEO_BACKGROUND_EXTENSIONS,
)

MEDIA_TYPE_IMAGE = "image"
MEDIA_TYPE_ANIMATED = "animated_image"
MEDIA_TYPE_VIDEO = "video"
MEDIA_TYPE_SVG = "svg"

_COVER_SUFFIXES = (".webp", ".jpg")
_COVER_CONTENT_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg"}
# 浏览器提交的封面源图单边上限，防止伪造超大尺寸撑爆解码。
_COVER_MAX_SOURCE_EDGE = 4096
_COVER_SOURCE_FORMATS = {"JPEG", "PNG", "WEBP"}

_RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")

# 事件处理与可执行内容一律拒绝；a/handler/listener 在图片模式下虽不会
# 触发，但直读 SVG 时可能导航或监听事件，一并排除。
_BLOCKED_SVG_ELEMENTS = {
    "a",
    "audio",
    "base",
    "embed",
    "foreignobject",
    "handler",
    "iframe",
    "link",
    "listener",
    "meta",
    "object",
    "script",
    "video",
}
_SVG_REFERENCE_ATTRS = {"href", "src"}
# CSS 中的外部引用和脚本入口；url(#id) 内部引用允许。
_DANGEROUS_CSS = re.compile(
    r"@import\b|expression\s*\(|javascript\s*:|behavior\s*:|-moz-binding|"
    r"url\(\s*['\"]?\s*(?:[a-z][a-z0-9+.-]*:|//)",
    re.IGNORECASE,
)
_SVG_DATA_IMAGE = re.compile(r"^data:image/(?:png|jpeg|gif|webp);base64,", re.I)
_SVG_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"

# 动图探测结果缓存：按路径 + mtime 记忆，避免每次公开配置都重开文件。
_animated_probe_cache: OrderedDict[str, tuple[int, bool]] = OrderedDict()


def detect_background_suffix(content: bytes) -> str | None:
    """按真实文件头识别素材类型，返回规范扩展名；无法识别返回 None。"""

    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    # MP4 是 ISO BMFF 容器：前 4 字节为 box 大小，第 5～8 字节固定为 ftyp。
    if (
        len(content) >= 16
        and content[4:8] == b"ftyp"
        and 16 <= int.from_bytes(content[:4], "big") <= 4096
    ):
        return ".mp4"
    # WebM 是 EBML 容器，magic 为 1A45DFA3。
    if content.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    if _looks_like_svg(content):
        return ".svg"
    return None


def _looks_like_svg(content: bytes) -> bool:
    head = content[:4096]
    try:
        # 分块头可能在中文字符中间截断，不完整尾字符不影响根节点探测。
        text = head.decode("utf-8-sig", errors="ignore")
    except UnicodeDecodeError:
        return False
    text = text.lstrip()
    if not text.startswith("<"):
        return False
    if text.startswith("<svg"):
        return True
    # 允许 XML 声明和注释出现在根节点之前。
    if text.startswith(("<?xml", "<!--")) and "<svg" in text:
        return True
    return False


def upload_limit_for_suffix(suffix: str) -> int:
    """按素材类型返回上传大小上限（字节）。"""

    suffix = suffix.lower()
    if suffix in VIDEO_BACKGROUND_EXTENSIONS:
        return MAX_VIDEO_BYTES
    if suffix in SVG_BACKGROUND_EXTENSIONS:
        return MAX_SVG_BYTES
    return MAX_BACKGROUND_BYTES


def upload_limit_message(suffix: str) -> str:
    suffix = suffix.lower()
    if suffix in VIDEO_BACKGROUND_EXTENSIONS:
        return "视频素材不能超过 100MiB。"
    if suffix in SVG_BACKGROUND_EXTENSIONS:
        return "SVG 素材不能超过 10MiB。"
    return "图片素材不能超过 10MiB。"


def sanitize_svg(content: bytes) -> bytes:
    """校验 SVG 为可安全以图片方式呈现的自包含文档。

    通过时返回已检查 XML 树的序列化内容；包含脚本、事件属性、外部引用、实体定义等
    内容时抛出带中文原因的 ValueError。
    """

    # 拒绝 DOCTYPE：同时挡住内部实体定义（含实体扩展攻击）和外部 DTD。
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("SVG 请使用 UTF-8 编码。") from exc
    if re.search(r"<!DOCTYPE|<!ENTITY|<\?xml-stylesheet", text, re.I):
        raise ValueError("SVG 包含 DOCTYPE 或实体定义，已拒绝。")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError("SVG 解析失败，文件可能已损坏。") from exc
    if _local_name(root.tag).lower() != "svg":
        raise ValueError("文件不是有效的 SVG 素材。")

    for element in root.iter():
        name = _local_name(element.tag).lower()
        if element.tag.startswith("{") and not element.tag.startswith(
            "{" + _SVG_NAMESPACE + "}"
        ):
            raise ValueError("SVG 包含非 SVG 命名空间元素，已拒绝。")
        if name in _BLOCKED_SVG_ELEMENTS:
            raise ValueError(f"SVG 包含不允许的元素 <{name}>，已拒绝。")
        for attribute, value in element.attrib.items():
            local = _local_name(attribute).lower()
            if local.startswith("on"):
                raise ValueError("SVG 包含事件处理属性，已拒绝。")
            if local == "base" and value.strip():
                raise ValueError("SVG 不允许修改资源的基础路径。")
            if local in _SVG_REFERENCE_ATTRS:
                _check_svg_reference(value)
            if (
                name in {"animate", "set", "animatetransform"}
                and local == "attributename"
            ):
                if value.lower().split(":")[-1] in {
                    "href",
                    "src",
                    "style",
                } or value.lower().startswith("on"):
                    raise ValueError("SVG 动画不能修改资源引用或事件属性。")
            # fill/filter 等展示属性也可以包含 url()。
            _check_svg_css(value)
        if name == "style":
            _check_svg_css("".join(element.itertext()))
    # 序列化只保留已检查的 XML 树，丢弃处理指令与文档声明。
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _check_svg_css(value: str) -> None:
    # 禁止转义与注释拼接绕过；本版支持常规声明式样式，不解释任意 CSS。
    if "\\" in value or "/*" in value or _DANGEROUS_CSS.search(value):
        raise ValueError("SVG 包含不支持或不安全的样式引用。")
    for match in _SVG_URL.finditer(value):
        if not match[2].strip().startswith("#"):
            raise ValueError("SVG 样式引用了外部资源，已拒绝。")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _check_svg_reference(value: str) -> None:
    reference = value.strip()
    # 文档内部片段引用（渐变、滤镜、复用元素）是合法的。
    if not reference or reference.startswith("#"):
        return
    # 自包含 SVG 允许内嵌位图；其余 data 内容（如 HTML）不允许。
    if _SVG_DATA_IMAGE.match(reference):
        return
    raise ValueError("SVG 引用了外部资源，已拒绝。")


def is_animated_image(path: Path) -> bool:
    """判断 GIF/WebP 是否包含多帧动画；结果按路径和修改时间缓存。"""

    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return False
    key = str(path)
    cached = _animated_probe_cache.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    animated = False
    with suppress(
        OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError
    ):
        with Image.open(path) as image:
            animated = bool(getattr(image, "is_animated", False)) and (
                getattr(image, "n_frames", 1) > 1
            )
    _animated_probe_cache[key] = (mtime, animated)
    _animated_probe_cache.move_to_end(key)
    if len(_animated_probe_cache) > 256:
        _animated_probe_cache.popitem(last=False)
    return animated


def media_type_for_filename(filename: str, *, animated: bool = False) -> str:
    """按扩展名归类素材；GIF/WebP 需用 animated 区分动图与静态图。"""

    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_BACKGROUND_EXTENSIONS:
        return MEDIA_TYPE_VIDEO
    if suffix in SVG_BACKGROUND_EXTENSIONS:
        return MEDIA_TYPE_SVG
    if suffix in {".gif", ".webp", ".png"} and animated:
        return MEDIA_TYPE_ANIMATED
    return MEDIA_TYPE_IMAGE


def probe_media_type(path: Path) -> str:
    """读取真实文件归类素材类型。"""

    suffix = path.suffix.lower()
    if suffix in {".gif", ".webp", ".png"}:
        return media_type_for_filename(path.name, animated=is_animated_image(path))
    return media_type_for_filename(path.name)


def validate_media_file(path: Path, suffix: str) -> None:
    """校验完整图片或视频容器；视频编码由上传浏览器实际解码确认。"""

    if suffix == ".mp4":
        with path.open("rb") as stream:
            boxes = list(_mp4_boxes(stream, 0, path.stat().st_size))
            if not boxes or boxes[0][0] != b"ftyp":
                raise ValueError("MP4 容器头不正确。")
            stream.seek(boxes[0][1])
            brands = stream.read(boxes[0][2] - boxes[0][1])
            if len(brands) < 8 or len(brands) % 4:
                raise ValueError("MP4 格式标识不完整。")
            if not any(box[0] == b"mdat" for box in boxes):
                raise ValueError("MP4 缺少媒体数据。")
            video_track = False
            for kind, start, end in boxes:
                if kind != b"moov":
                    continue
                for track_kind, track_start, track_end in _mp4_boxes(
                    stream, start, end
                ):
                    if track_kind != b"trak":
                        continue
                    for media_kind, media_start, media_end in _mp4_boxes(
                        stream, track_start, track_end
                    ):
                        if media_kind != b"mdia":
                            continue
                        for child, child_start, _ in _mp4_boxes(
                            stream, media_start, media_end
                        ):
                            if child == b"hdlr":
                                stream.seek(child_start + 8)
                                video_track |= stream.read(4) == b"vide"
            if not video_track:
                raise ValueError("MP4 中未发现视频轨道。")
        return
    if suffix == ".webm":
        with path.open("rb") as stream:
            length = path.stat().st_size
            header = _ebml_element(stream, length)
            if header[0] != 0x1A45DFA3 or header[2] > 4096:
                raise ValueError("WebM 容器头不正确。")
            doctype = b""
            while stream.tell() < header[2]:
                kind, start, end = _ebml_element(stream, header[2])
                if kind == 0x4282:
                    doctype = stream.read(end - start)
                stream.seek(end)
            if doctype != b"webm":
                raise ValueError("仅支持 WebM，不支持其他 Matroska 容器。")
            segment = _ebml_element(stream, length)
            if segment[0] != 0x18538067:
                raise ValueError("WebM 缺少 Segment。")
            has_video = has_cluster = False
            while stream.tell() < segment[2]:
                kind, start, end = _ebml_element(stream, segment[2])
                if kind == 0x1F43B675:
                    has_cluster = True
                elif kind == 0x1654AE6B:
                    while stream.tell() < end:
                        track, _, track_end = _ebml_element(stream, end)
                        if track == 0xAE:
                            while stream.tell() < track_end:
                                field, field_start, field_end = _ebml_element(
                                    stream, track_end
                                )
                                if field == 0x83 and field_end - field_start <= 8:
                                    has_video |= (
                                        int.from_bytes(
                                            stream.read(field_end - field_start), "big"
                                        )
                                        == 1
                                    )
                                stream.seek(field_end)
                        stream.seek(track_end)
                stream.seek(end)
            if not has_video or not has_cluster:
                raise ValueError("WebM 缺少视频轨道或媒体数据。")
        return
    if suffix == ".svg":
        path.write_bytes(sanitize_svg(path.read_bytes()))
        return
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                image.verify()
    except (
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("图片内容损坏或尺寸过大，无法读取。") from exc


def _mp4_boxes(stream, start: int, end: int):
    stream.seek(start)
    while stream.tell() < end:
        position = stream.tell()
        head = stream.read(8)
        if len(head) != 8:
            raise ValueError("MP4 容器已截断。")
        size = int.from_bytes(head[:4], "big")
        if size == 1:
            extended = stream.read(8)
            if len(extended) != 8:
                raise ValueError("MP4 容器已截断。")
            size = int.from_bytes(extended, "big")
        elif size == 0:
            size = end - position
        data_start = stream.tell()
        if size < data_start - position or position + size > end:
            raise ValueError("MP4 数据块长度不正确。")
        yield head[4:8], data_start, position + size
        stream.seek(position + size)


def _ebml_element(stream, limit: int) -> tuple[int, int, int]:
    def read_vint(*, identifier=False):
        first = stream.read(1)
        if not first or first == b"\x00":
            raise ValueError("WebM 容器已截断。")
        width = 9 - first[0].bit_length()
        rest = stream.read(width - 1)
        if len(rest) != width - 1:
            raise ValueError("WebM 容器已截断。")
        value = int.from_bytes(first + rest, "big")
        if identifier:
            return value
        value &= (1 << (width * 7)) - 1
        return None if value == (1 << (width * 7)) - 1 else value

    kind = read_vint(identifier=True)
    size = read_vint()
    start = stream.tell()
    end = limit if size is None else start + size
    if end > limit or end < start:
        raise ValueError("WebM 数据块长度不正确。")
    return kind, start, end


async def save_background_upload(upload, paths) -> str:
    """单次接收原素材与封面，校验完整后才返回可入库的文件名。"""

    async def read_exact(size):
        parts = bytearray()
        while len(parts) < size:
            chunk = await upload.read(size - len(parts))
            if not chunk:
                break
            parts.extend(chunk)
        return bytes(parts)

    if (
        getattr(upload, "content_length", None)
        and upload.content_length > MAX_UPLOAD_BYTES
    ):
        raise ValueError("上传超过限制：图片/SVG 10MiB，视频 100MiB，封面 4MiB。")
    paths.ensure_runtime_dirs()
    background_id = uuid4().hex
    temp = paths.background_dir / f"background-{background_id}.upload.tmp"
    target = None
    filename = ""
    cover_data = None
    try:
        await upload.seek(0)
        prefix = await read_exact(len(MEDIA_BUNDLE_MAGIC))
        if prefix == MEDIA_BUNDLE_MAGIC:
            size_bytes = await read_exact(4)
            if len(size_bytes) != 4:
                raise ValueError("素材上传包不完整。")
            cover_size = int.from_bytes(size_bytes, "big")
            if not 0 < cover_size <= MAX_COVER_SOURCE_BYTES:
                raise ValueError("封面必须为不超过 4MiB 的图片。")
            cover_data = await read_exact(cover_size)
            if len(cover_data) != cover_size:
                raise ValueError("素材封面已截断。")
            prefix = b""
        total_size = len(prefix)
        first_bytes = prefix
        suffix = None
        with temp.open("wb") as output:
            output.write(prefix)
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if len(first_bytes) < 4096:
                    first_bytes += chunk[: 4096 - len(first_bytes)]
                suffix = suffix or detect_background_suffix(first_bytes)
                limit = upload_limit_for_suffix(suffix) if suffix else MAX_VIDEO_BYTES
                if total_size > limit:
                    raise ValueError(upload_limit_message(suffix or ".mp4"))
                await asyncio.to_thread(output.write, chunk)
        suffix = suffix or detect_background_suffix(first_bytes)
        if not suffix or not total_size:
            raise ValueError("素材内容为空或格式不支持；支持图片、MP4、WebM 和 SVG。")
        if total_size > upload_limit_for_suffix(suffix):
            raise ValueError(upload_limit_message(suffix))
        await asyncio.to_thread(validate_media_file, temp, suffix)
        filename = f"background-{background_id}{suffix}"
        target = paths.resolve_background_file(filename)
        temp.replace(target)
        media_type = probe_media_type(target)
        if media_type in {MEDIA_TYPE_VIDEO, MEDIA_TYPE_SVG}:
            if cover_data is None:
                raise ValueError("视频/SVG 需要静态封面，请通过调色盘设置页上传。")
            cover = await asyncio.to_thread(load_cover_upload, cover_data)
        else:
            # 原图解码后的代表帧同时用于动图静态兜底，封面不信任上传方。
            cover = await asyncio.to_thread(build_cover_from_animated_image, target)
        await asyncio.to_thread(save_cover_image, cover, paths.cover_dir, filename)
        return filename
    except BaseException:
        with suppress(OSError):
            temp.unlink()
        if target:
            with suppress(OSError):
                target.unlink()
        if filename:
            delete_background_cover(paths.cover_dir, filename)
        raise


def find_cover(cover_dir: Path, background_filename: str) -> Path | None:
    """查找素材已生成的封面文件。"""

    for suffix in _COVER_SUFFIXES:
        path = cover_dir / _cover_filename(background_filename, suffix)
        if path.is_file():
            return path
    return None


def cover_content_type(path: Path) -> str:
    return _COVER_CONTENT_TYPES.get(path.suffix.lower(), "image/jpeg")


def delete_background_cover(cover_dir: Path, background_filename: str) -> None:
    """删除素材对应的封面缓存。"""

    for suffix in _COVER_SUFFIXES:
        with suppress(OSError):
            (cover_dir / _cover_filename(background_filename, suffix)).unlink()


def save_cover_image(
    image: Image.Image,
    cover_dir: Path,
    background_filename: str,
) -> Path:
    """把封面图压到 1280px 以内并落盘，返回最终文件路径。"""

    cover_dir.mkdir(parents=True, exist_ok=True)
    cover = image
    if max(cover.size) > COVER_MAX_EDGE:
        cover = image.copy()
        cover.thumbnail((COVER_MAX_EDGE, COVER_MAX_EDGE), _RESAMPLE_LANCZOS)

    webp_path = cover_dir / _cover_filename(background_filename, ".webp")
    jpg_path = cover_dir / _cover_filename(background_filename, ".jpg")
    try:
        _save_cover_webp(cover, webp_path)
    except Exception:
        _save_cover_jpeg(cover, jpg_path)
        with suppress(FileNotFoundError):
            webp_path.unlink()
        return jpg_path
    with suppress(FileNotFoundError):
        jpg_path.unlink()
    return webp_path


def build_cover_from_animated_image(source_path: Path) -> Image.Image:
    """从 GIF/动态 WebP 取代表帧（第 0 帧）作为封面图。"""

    if not source_path.is_file():
        raise ValueError("背景素材不存在，请重新上传。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source_path) as image:
                image.seek(0)
                frame = ImageOps.exif_transpose(image)
                cover = frame.copy()
    except (
        OSError,
        UnidentifiedImageError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("封面生成失败。") from exc
    if _has_alpha(cover):
        return cover.convert("RGBA")
    return cover.convert("RGB")


def load_cover_upload(data: bytes) -> Image.Image:
    """校验浏览器提交的封面字节，返回解码后的图片。"""

    if not data:
        raise ValueError("封面内容为空。")
    if len(data) > MAX_COVER_SOURCE_BYTES:
        raise ValueError("封面图片不能超过 4MiB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in _COVER_SOURCE_FORMATS:
                    raise ValueError("封面图片格式不受支持。")
                if max(image.size) > _COVER_MAX_SOURCE_EDGE:
                    raise ValueError("封面图片尺寸过大。")
                cover = ImageOps.exif_transpose(image).copy()
    except (
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("封面图片无法识别。") from exc
    if _has_alpha(cover):
        return cover.convert("RGBA")
    return cover.convert("RGB")


def _cover_filename(background_filename: str, suffix: str) -> str:
    stem = Path(background_filename).stem
    if not stem:
        raise ValueError("背景素材文件名不正确。")
    digest = sha256(background_filename.encode("utf-8")).hexdigest()[:16]
    return f"cover-{stem}-{digest}{suffix}"


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        return image.getchannel("A").getextrema()[0] < 255
    return image.mode == "P" and "transparency" in image.info


def _save_cover_webp(image: Image.Image, target_path: Path) -> None:
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    try:
        image.save(temp_path, "WEBP", quality=80, method=4)
        temp_path.replace(target_path)
    except Exception:
        with suppress(FileNotFoundError):
            temp_path.unlink()
        raise


def _save_cover_jpeg(image: Image.Image, target_path: Path) -> None:
    temp_path = target_path.with_name(f"{target_path.name}.tmp")
    try:
        if image.mode == "RGBA":
            flattened = Image.new("RGB", image.size, (246, 246, 246))
            flattened.paste(image, mask=image.getchannel("A"))
            image = flattened
        else:
            image = image.convert("RGB")
        image.save(temp_path, "JPEG", quality=82, optimize=True, progressive=True)
        temp_path.replace(target_path)
    except Exception as exc:
        with suppress(FileNotFoundError):
            temp_path.unlink()
        raise ValueError("封面保存失败。") from exc
