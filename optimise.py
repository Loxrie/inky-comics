# This file is the result of a partial feature set conversion from
# Typescript into Python from https://github.com/paperlesspaper/epdoptimize
# and was originally licensed under the Apache 2-0 license included here as
# required:
#
# Copyright [2025] [Robert Gühne]
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

from functools import wraps
from time import perf_counter
from typing import Mapping, Sequence
from typing import Callable, ParamSpec, TypeVar

import cv2
import numpy as np
from PIL import Image

RGB = tuple[int, int, int]
PaletteEntry = Mapping[str, str]
Parameters = ParamSpec("Parameters")
ReturnValue = TypeVar("ReturnValue")

SPECTRA6_BOEBER_PALETTE: tuple[dict[str, str], ...] = (
    {"name": "black", "color": "#1f2226", "deviceColor": "#000000"},
    {"name": "white", "color": "#d6d6d6", "deviceColor": "#ffffff"},
    {"name": "blue", "color": "#416ce1", "deviceColor": "#0000ff"},
    {"name": "green", "color": "#067406", "deviceColor": "#00ff00"},
    {"name": "red", "color": "#ea4843", "deviceColor": "#ff0000"},
    {"name": "yellow", "color": "#dbd529", "deviceColor": "#ffff00"},
)

DEFAULT_CONFIG = {
    "imageAdjustmentOptions": {
        "toneMapping": {
            "exposure": 0.05,
            "saturation": 0.05,
            "contrast": 0,
            "strength": 0.92,
            "shadowBoost": 0.1,
            "highlightCompress": -0.55,
            "midpoint": 0.44,
        },
        "dynamicRangeCompression": {
            "mode": "auto",
            "strength": 1,
            "lowPercentile": 0.01,
            "highPercentile": 0.99,
        },
    },
    "canvasDitherOptions": {"pilDither": True},
    "palette": SPECTRA6_BOEBER_PALETTE,
}


def _rgb(value: str) -> RGB:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    if len(value) != 6:
        raise ValueError(f"Invalid hex color: {value!r}")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _palette_entries(palette: Sequence[PaletteEntry]) -> tuple[np.ndarray, np.ndarray]:
    calibrated = np.asarray(
        [_rgb(entry["color"]) for entry in palette], dtype=np.float64
    )
    device = np.asarray(
        [_rgb(entry["deviceColor"]) for entry in palette], dtype=np.uint8
    )
    return calibrated, device


def _array(image: Image.Image) -> np.ndarray:
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL.Image.Image")
    return np.asarray(image.convert("RGB"), dtype=np.uint8).copy()


def _image(data: np.ndarray, mode: str = "RGB") -> Image.Image:
    return Image.fromarray(np.clip(np.rint(data), 0, 255).astype(np.uint8), mode)


def _srgb_to_linear(values: np.ndarray) -> np.ndarray:
    values = values / 255.0
    return np.where(values > 0.04045, ((values + 0.055) / 1.055) ** 2.4, values / 12.92)


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb_array = np.asarray(rgb)
    original_shape = rgb_array.shape
    rgb_float = np.clip(rgb_array, 0, 255).astype(np.float32) / 255.0
    samples = rgb_float.reshape(-1, 1, 3)
    return (
        cv2.cvtColor(samples, cv2.COLOR_RGB2Lab)
        .reshape(original_shape)
        .astype(np.float64)
    )


def _lab_to_rgb(lab: np.ndarray) -> np.ndarray:
    lab_array = np.asarray(lab)
    original_shape = lab_array.shape
    lab_float = lab_array.astype(np.float32).reshape(-1, 1, 3)
    rgb = cv2.cvtColor(lab_float, cv2.COLOR_Lab2RGB).reshape(original_shape)
    return np.clip(rgb * 255.0, 0, 255).astype(np.float64)


def _point_rgb(rgb: np.ndarray, lookup: Sequence[int]) -> np.ndarray:
    lookup_arr = np.asarray(lookup, dtype=np.float64)
    indices = np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return lookup_arr[indices]


def _saturation_array(rgb: np.ndarray) -> np.ndarray:
    values = rgb.astype(np.float64) / 255
    maximum = values.max(axis=-1)
    minimum = values.min(axis=-1)
    return np.divide(
        maximum - minimum,
        maximum,
        out=np.zeros_like(maximum),
        where=maximum > 0,
    )


def _tone_lookup(options: Mapping[str, float]) -> list[int]:
    mode = options.get("mode")
    contrast = 1 + float(options.get("contrast", 0))
    strength = float(options.get("strength", 0.92))
    midpoint = float(options.get("midpoint", 0.5))
    shadow_exp = np.clip(
        1 - strength * float(options.get("shadowBoost", 0)) * 1.5, 0.15, 3
    )
    highlight_exp = np.clip(
        1 - strength * float(options.get("highlightCompress", -1.5)), 0.15, 3
    )
    lookup = []
    for value in range(256):
        tone_value = value
        if mode != "off" and (mode is None or mode == "contrast"):
            tone_value = min(255, max(0, round((value - 128) * contrast + 128)))
        if mode == "off":
            lookup.append(value)
            continue
        normalized = tone_value / 255
        if mode == "scurve" or (mode is None and strength != 0):
            if normalized <= midpoint:
                mapped = (normalized / midpoint) ** shadow_exp * midpoint
            else:
                mapped = midpoint + (
                    ((normalized - midpoint) / (1 - midpoint)) ** highlight_exp
                ) * (1 - midpoint)
            tone_value = min(255, max(0, round(mapped * 255)))
        lookup.append(tone_value)
    return lookup


def _tone_mapping(rgb: np.ndarray, options: Mapping[str, float]) -> np.ndarray:
    if options.get("mode") == "off":
        return rgb.copy()
    exposure = 2 ** float(options.get("exposure", 0))
    exposure_lookup = [
        min(255, max(0, round(value * exposure))) for value in range(256)
    ]
    exposed = _point_rgb(rgb, exposure_lookup)
    result = exposed / 255
    saturation_factor = 1 + float(options.get("saturation", 0))

    # With neutral saturation, exposure and tone mapping are both per-channel
    # operations and can be fused into one Pillow lookup-table pass.
    if saturation_factor == 1:
        tone_lookup = _tone_lookup(options)
        combined_lookup = [tone_lookup[exposure_lookup[value]] for value in range(256)]
        return _point_rgb(rgb, combined_lookup)

    hls = cv2.cvtColor(result.astype(np.float32), cv2.COLOR_RGB2HLS)
    hls[..., 2] = np.clip(hls[..., 2] * saturation_factor, 0, 1)
    result = cv2.cvtColor(hls, cv2.COLOR_HLS2RGB)
    result = (result * 255).clip(0, 255)
    return _point_rgb(result, _tone_lookup(options))


def apply_image_adjustments(
    image: Image.Image,
    options: Mapping | None = None,
    palette: Sequence[PaletteEntry] = SPECTRA6_BOEBER_PALETTE,
) -> Image.Image:
    options = options or DEFAULT_CONFIG["imageAdjustmentOptions"]
    data = _array(image)
    tone_options = options.get("toneMapping", {})
    range_options = options.get("dynamicRangeCompression", {})
    if range_options is True:
        range_options = {"mode": "display", "strength": 1}
    if not isinstance(range_options, Mapping):
        range_options = {}

    source_luma = data @ np.asarray([0.2126, 0.7152, 0.0722])
    source_saturation = _saturation_array(data)
    white_mask = source_saturation <= float(
        range_options.get("whitePreserveMaxSaturation", 0.18)
    )
    white_lumas = source_luma[white_mask]
    preserve_white = range_options.get("preserveWhite") is True and white_lumas.size > 0
    source_white_luma = (
        float(
            np.percentile(
                white_lumas,
                100 * float(range_options.get("whitePreservePercentile", 0.99)),
            )
        )
        if preserve_white
        else 0
    )
    preserve_white = preserve_white and source_white_luma >= float(
        range_options.get("whitePreserveMinLuma", 150)
    )

    rgb = _tone_mapping(data, tone_options)
    calibrated, _ = _palette_entries(palette)
    lab = _rgb_to_lab(rgb)
    if range_options.get("mode", "display") != "off":
        palette_lab = _rgb_to_lab(calibrated)
        black_luma = float(palette_lab[:, 0].min())
        white_luma = float(palette_lab[:, 0].max())
        mode = range_options.get("mode", "display")
        if mode == "auto":
            low, high = np.percentile(
                lab[..., 0],
                [
                    100 * float(range_options.get("lowPercentile", 0.01)),
                    100 * float(range_options.get("highPercentile", 0.99)),
                ],
            )
        else:
            low, high = 0.0, 100.0
        if high > low and white_luma > black_luma:
            target = (
                np.clip((lab[..., 0] - low) / (high - low), 0, 1)
                * (white_luma - black_luma)
                + black_luma
            )
            strength = np.clip(float(range_options.get("strength", 1)), 0, 1)
            chroma_protection = np.clip((source_saturation - 0.18) / 0.5, 0, 1) * 0.85
            lab[..., 0] += (target - lab[..., 0]) * strength * (1 - chroma_protection)
    data = _lab_to_rgb(lab)
    if preserve_white:
        output_luma = data @ np.asarray([0.2126, 0.7152, 0.0722])
        target_white = calibrated[
            np.argmax(calibrated @ np.asarray([0.2126, 0.7152, 0.0722]))
        ]
        restore_mask = (
            white_mask
            & (source_luma >= source_white_luma)
            & (output_luma < target_white @ np.asarray([0.2126, 0.7152, 0.0722]))
        )
        data[restore_mask] = target_white
    return _image(data)


def dither_canvas(
    image: Image.Image,
    options: Mapping | None = None,
    palette: Sequence[PaletteEntry] = SPECTRA6_BOEBER_PALETTE,
) -> Image.Image:
    options = options or {}
    fastDither = bool(options.get("pilDither", False))
    if fastDither:
        calibrated, _ = _palette_entries(palette)
        palette_image = Image.new("P", (1, 1))
        palette_image.putpalette(calibrated.astype(np.uint8).flatten())
        return image.quantize(palette=palette_image, dither=Image.FLOYDSTEINBERG)
    else:
        return image


def colour_mapping(
    image: Image.Image, palette: Sequence[PaletteEntry] = SPECTRA6_BOEBER_PALETTE
) -> Image.Image:
    data = _array(image)
    calibrated, device = _palette_entries(palette)
    for source, target in zip(calibrated.astype(np.uint8), device):
        data[np.all(data == source, axis=-1)] = target
    return _image(data)


class Optimise:
    """Apply the image-processing pipeline through a fluent interface."""

    def __init__(self, config: Mapping):
        self.image_adjustment_options = config.get(
            "imageAdjustmentOptions", DEFAULT_CONFIG["imageAdjustmentOptions"]
        )
        self.canvas_dither_options = config.get(
            "canvasDitherOptions", DEFAULT_CONFIG["canvasDitherOptions"]
        )
        self.palette = config.get("palette", SPECTRA6_BOEBER_PALETTE)

    def load(self, image):
        if isinstance(image, (str, bytes)):
            image = Image.open(image)
        if isinstance(image, str):
            image = Image.open(image)
        if not isinstance(image, Image.Image):
            raise TypeError("config['image'] must be a PIL image or image path")

        self.image = image.convert("RGB")
        return self

    def apply_image_adjustments(self) -> "Optimise":
        self.image = apply_image_adjustments(
            self.image,
            options=self.image_adjustment_options,
            palette=self.palette,
        )
        return self

    def dither_canvas(self) -> "Optimise":
        self.image = dither_canvas(
            self.image,
            options=self.canvas_dither_options,
            palette=self.palette,
        )
        return self

    def colour_mapping(self) -> "Optimise":
        self.image = colour_mapping(self.image, palette=self.palette)
        return self

    def get_image(self) -> Image.Image:
        """Return the current image as an indexed PIL image without quantizing."""
        data = _array(self.image)
        _, device = _palette_entries(self.palette)
        matches = np.all(data[..., None, :] == device[None, None, :, :], axis=-1)
        if not np.all(matches.any(axis=-1)):
            raise ValueError("image contains colours outside the configured palette")

        indexed = Image.new("P", self.image.size)
        indexed.putpalette(device.flatten().tolist() + [0, 0, 0] * (256 - len(device)))
        indexed.putdata(np.argmax(matches, axis=-1).astype(np.uint8).ravel().tolist())
        return indexed

    def save(self, path: str, **kwargs) -> "Optimise":
        self.image.save(path, **kwargs)
        return self


__all__ = ["DEFAULT_CONFIG", "SPECTRA6_BOEBER_PALETTE", "Optimise"]
