from __future__ import annotations

import colorsys
import warnings
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageSequence, UnidentifiedImageError


@dataclass(frozen=True)
class ThemeColors:
    """从壁纸中提取出的 AstrBot 主题色。"""

    primary: str
    secondary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "theme_primary": self.primary,
            "theme_secondary": self.secondary,
        }


@dataclass(frozen=True)
class _ColorCandidate:
    rgb: tuple[int, int, int]
    count: int
    saturation: float
    lightness: float


DEFAULT_THEME_COLORS = ThemeColors("#3c96ca", "#2f86bd")
_MAX_SAMPLE_FRAMES = 6
_MAX_SAMPLE_PIXELS = 60000


def extract_theme_colors(image_path: Path) -> ThemeColors:
    """从图片中提取适合 AstrBot UI 的主色和辅色。"""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            candidates = _collect_candidates(image_path)
    except (
        OSError,
        UnidentifiedImageError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return DEFAULT_THEME_COLORS

    if not candidates:
        return DEFAULT_THEME_COLORS

    primary = _select_primary(candidates)
    secondary = _select_secondary(candidates, primary)
    return ThemeColors(
        primary=_rgb_to_hex(_normalize_ui_color(primary.rgb)),
        secondary=_rgb_to_hex(_normalize_ui_color(secondary.rgb)),
    )


def normalize_hex_color(value: object) -> str:
    """规范化 #RRGGBB 颜色；非法值返回空字符串。"""

    if not isinstance(value, str):
        return ""
    value = value.strip()
    if len(value) != 7 or not value.startswith("#"):
        return ""
    hex_part = value[1:]
    if not all(char in "0123456789abcdefABCDEF" for char in hex_part):
        return ""
    return f"#{hex_part.lower()}"


def _collect_candidates(image_path: Path) -> list[_ColorCandidate]:
    with Image.open(image_path) as image:
        pixels: list[tuple[int, int, int]] = []
        for index, frame in enumerate(ImageSequence.Iterator(image)):
            if index >= _MAX_SAMPLE_FRAMES or len(pixels) >= _MAX_SAMPLE_PIXELS:
                break
            pixels.extend(
                _collect_frame_pixels(
                    frame,
                    remaining=_MAX_SAMPLE_PIXELS - len(pixels),
                )
            )

        if not pixels:
            return []

        palette_image = Image.new("RGB", (len(pixels), 1))
        palette_image.putdata(pixels)
        quantized = palette_image.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette()
        if palette is None:
            return []

        total = len(pixels)
        candidates: list[_ColorCandidate] = []
        for count, index in quantized.getcolors(maxcolors=12) or []:
            offset = index * 3
            rgb = tuple(int(channel) for channel in palette[offset : offset + 3])
            if len(rgb) != 3:
                continue
            hue, lightness, saturation = colorsys.rgb_to_hls(
                rgb[0] / 255,
                rgb[1] / 255,
                rgb[2] / 255,
            )
            del hue
            if count / total < 0.015:
                continue
            if lightness < 0.08 or lightness > 0.92:
                continue
            candidates.append(
                _ColorCandidate(
                    rgb=rgb,  # type: ignore[arg-type]
                    count=count,
                    saturation=saturation,
                    lightness=lightness,
                )
            )

    candidates.sort(
        key=lambda item: (
            item.count * (0.55 + item.saturation) * (1.0 - abs(item.lightness - 0.5)),
            item.saturation,
        ),
        reverse=True,
    )
    return candidates


def _collect_frame_pixels(
    frame: Image.Image,
    *,
    remaining: int,
) -> list[tuple[int, int, int]]:
    if remaining <= 0:
        return []

    preview = frame.convert("RGBA")
    preview.thumbnail((160, 160))

    pixels: list[tuple[int, int, int]] = []
    for red, green, blue, alpha in preview.getdata():
        if alpha < 32:
            continue
        hue, lightness, saturation = colorsys.rgb_to_hls(
            red / 255,
            green / 255,
            blue / 255,
        )
        del hue, saturation
        if lightness < 0.06 or lightness > 0.94:
            continue
        pixels.append((red, green, blue))
        if len(pixels) >= remaining:
            break
    return pixels


def _select_primary(candidates: list[_ColorCandidate]) -> _ColorCandidate:
    colorful = [candidate for candidate in candidates if candidate.saturation >= 0.18]
    return colorful[0] if colorful else candidates[0]


def _select_secondary(
    candidates: list[_ColorCandidate],
    primary: _ColorCandidate,
) -> _ColorCandidate:
    primary_hue = _hue(primary.rgb)
    alternatives = [
        candidate
        for candidate in candidates
        if candidate.rgb != primary.rgb and _hue_distance(primary_hue, _hue(candidate.rgb)) >= 0.08
    ]
    if alternatives:
        alternatives.sort(
            key=lambda item: (
                _hue_distance(primary_hue, _hue(item.rgb)) * 0.65
                + item.saturation * 0.25
                + (item.count / max(primary.count, 1)) * 0.10
            ),
            reverse=True,
        )
        return alternatives[0]

    return _ColorCandidate(
        rgb=_derive_secondary(primary.rgb),
        count=primary.count,
        saturation=primary.saturation,
        lightness=primary.lightness,
    )


def _normalize_ui_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    hue, lightness, saturation = colorsys.rgb_to_hls(
        rgb[0] / 255,
        rgb[1] / 255,
        rgb[2] / 255,
    )
    if saturation < 0.08:
        hue = 0.56
        saturation = 0.30
    saturation = min(max(saturation, 0.34), 0.78)
    lightness = min(max(lightness, 0.38), 0.62)
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (round(red * 255), round(green * 255), round(blue * 255))


def _derive_secondary(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    hue, lightness, saturation = colorsys.rgb_to_hls(
        rgb[0] / 255,
        rgb[1] / 255,
        rgb[2] / 255,
    )
    if saturation < 0.08:
        hue = 0.64
        saturation = 0.30
    else:
        hue = (hue + 0.08) % 1.0
    saturation = min(max(saturation * 0.92, 0.30), 0.72)
    lightness = min(max(lightness * 0.94, 0.34), 0.58)
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return (round(red * 255), round(green * 255), round(blue * 255))


def _hue(rgb: tuple[int, int, int]) -> float:
    hue, _, _ = colorsys.rgb_to_hls(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return hue


def _hue_distance(left: float, right: float) -> float:
    distance = abs(left - right)
    return min(distance, 1.0 - distance)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)
