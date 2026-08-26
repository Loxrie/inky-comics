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
from math import log2
from typing import Any, Literal, Mapping, Sequence

import cv2
import numpy as np
from PIL import Image

from optimise import SPECTRA6_BOEBER_PALETTE

Intent = Literal["natural", "vivid", "readable", "faithful", "lowNoise", None]
Preset = Literal[
    "auto",
    "balanced",
    "dynamic",
    "vivid",
    "soft",
    "grayscale",
    "restore",
    "posterScan",
]


def _exposure(multiplier: float) -> float:
    return round(log2(multiplier), 3)


def _linear(multiplier: float) -> float:
    return round(multiplier - 1, 3)


class Suggestion:
    def __init__(
        self,
        image: Image.Image,
        palette: Sequence[Mapping[str, str]] = SPECTRA6_BOEBER_PALETTE,
        max_sample_dimension: int = 160,
        intent: Intent = "natural",
    ) -> None:
        if not isinstance(image, Image.Image):
            raise TypeError("image must be a PIL image")
        if max_sample_dimension < 1:
            raise ValueError("max_sample_dimension must be at least 1")
        if intent not in {"natural", "vivid", "readable", "faithful", "lowNoise", None}:
            raise ValueError(f"unsupported intent: {intent!r}")

        self.image = image.convert("RGB")
        self.palette = palette
        self.intent = intent if intent is not None else "natural"
        self._metrics = self._measure(max_sample_dimension)
        self._palette_profile = self._measure_palette()
        self.image_kind = self._classify()
        self._recommendation = self._build_recommendation()

    def tone_mapping(self) -> dict[str, Any]:
        """Return the suggested ``toneMapping`` options."""
        return dict(self._recommendation["toneMapping"])

    def dynamic_range_compression(self) -> dict[str, Any]:
        """Return the suggested ``dynamicRangeCompression`` options."""
        return dict(self._recommendation["dynamicRangeCompression"])

    def suggest(self, preset: Preset | str = "auto") -> dict[str, dict[str, Any]]:
        """Return adjustment settings for ``auto`` or a named preset.

        ``auto`` uses the image classification and intent rules. Named
        presets bypass classification and return stable preset settings.
        """
        normalized = "".join(
            character for character in preset.lower() if character.isalnum()
        )
        if normalized == "auto":
            return {
                "toneMapping": self.tone_mapping(),
                "dynamicRangeCompression": self.dynamic_range_compression(),
            }

        recommendation = self._preset_recommendation(normalized)
        self._enforce_white_preservation(recommendation)
        return recommendation

    def _preset_recommendation(self, preset: str) -> dict[str, dict[str, Any]]:
        presets: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
            "balanced": (
                {"mode": "contrast", "exposure": 0, "saturation": 0, "contrast": 0},
                {"mode": "display", "strength": 1},
            ),
            "dynamic": (
                {
                    "mode": "scurve",
                    "exposure": 0,
                    "saturation": _linear(1.3),
                    "strength": 0.9,
                    "shadowBoost": 0,
                    "highlightCompress": -1.5,
                    "midpoint": 0.5,
                },
                {"mode": "off"},
            ),
            "vivid": (
                {
                    "mode": "scurve",
                    "exposure": _exposure(1.1),
                    "saturation": _linear(1.6),
                    "strength": 0.7,
                    "shadowBoost": 0.1,
                    "highlightCompress": -1.3,
                    "midpoint": 0.5,
                },
                {"mode": "off"},
            ),
            "soft": (
                {
                    "mode": "contrast",
                    "exposure": 0,
                    "saturation": _linear(1.1),
                    "contrast": _linear(0.9),
                },
                {"mode": "display", "strength": 1},
            ),
            "grayscale": (
                {
                    "mode": "scurve",
                    "exposure": 0,
                    "saturation": -1,
                    "strength": 0.8,
                    "shadowBoost": 0.1,
                    "highlightCompress": -1.4,
                    "midpoint": 0.5,
                },
                {"mode": "display", "strength": 1},
            ),
            "restore": (
                {
                    "mode": "scurve",
                    "exposure": _exposure(1.08),
                    "saturation": _linear(0.9),
                    "strength": 1,
                    "shadowBoost": 0.25,
                    "highlightCompress": -0.75,
                    "midpoint": 0.46,
                },
                {
                    "mode": "auto",
                    "strength": 0.9,
                    "lowPercentile": 0.02,
                    "highPercentile": 0.98,
                },
            ),
            "posterscan": (
                {
                    "mode": "scurve",
                    "exposure": _exposure(1.04),
                    "saturation": _linear(1.05),
                    "strength": 0.92,
                    "shadowBoost": 0.08,
                    "highlightCompress": -0.55,
                    "midpoint": 0.44,
                },
                {
                    "mode": "auto",
                    "strength": 1,
                    "lowPercentile": 0.015,
                    "highPercentile": 0.985,
                },
            ),
        }
        try:
            tone, dynamic = presets[preset]
        except KeyError as error:
            available = ", ".join(["auto", *presets])
            raise ValueError(
                f"unsupported preset {preset!r}; choose one of: {available}"
            ) from error
        return {"toneMapping": dict(tone), "dynamicRangeCompression": dict(dynamic)}

    def _build_recommendation(self) -> dict[str, dict[str, Any]]:
        recommendation = self._base_recommendation()
        if self._is_restorable_low_contrast():
            self._apply_restore(recommendation)
        else:
            self._apply_kind_adjustments(recommendation)
        self._apply_learned_tuning(recommendation)
        self._apply_poster_scan_tuning(recommendation)
        self._apply_palette_tuning(recommendation)
        self._apply_intent(recommendation)
        self._enforce_minimum_contrast(recommendation)
        self._enforce_white_preservation(recommendation)
        return recommendation

    def _base_recommendation(self) -> dict[str, dict[str, Any]]:
        presets: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {
            "balanced": (
                {"mode": "contrast", "exposure": 0, "saturation": 0, "contrast": 0},
                {"mode": "display", "strength": 1},
            ),
            "vivid": (
                {
                    "mode": "scurve",
                    "exposure": _exposure(1.1),
                    "saturation": _linear(1.6),
                    "strength": 0.7,
                    "shadowBoost": 0.1,
                    "highlightCompress": -1.3,
                    "midpoint": 0.5,
                },
                {"mode": "off"},
            ),
            "soft": (
                {
                    "mode": "contrast",
                    "exposure": 0,
                    "saturation": _linear(1.1),
                    "contrast": _linear(0.9),
                },
                {"mode": "display", "strength": 1},
            ),
            "restore": (
                {
                    "mode": "scurve",
                    "exposure": _exposure(1.08),
                    "saturation": _linear(0.9),
                    "strength": 1,
                    "shadowBoost": 0.25,
                    "highlightCompress": -0.75,
                    "midpoint": 0.46,
                },
                {
                    "mode": "auto",
                    "strength": 0.9,
                    "lowPercentile": 0.02,
                    "highPercentile": 0.98,
                },
            ),
            "grayscale": (
                {
                    "mode": "scurve",
                    "exposure": 0,
                    "saturation": -1,
                    "strength": 0.8,
                    "shadowBoost": 0.1,
                    "highlightCompress": -1.4,
                    "midpoint": 0.5,
                },
                {"mode": "display", "strength": 1},
            ),
        }
        preset = (
            "restore"
            if self.image_kind == "lowContrastPhoto"
            else (
                "soft"
                if self.image_kind == "highContrastPhoto"
                else (
                    "vivid"
                    if self.image_kind in {"flatIllustration", "pixelArt"}
                    else "balanced"
                )
            )
        )
        tone, dynamic = presets[preset]
        return {"toneMapping": dict(tone), "dynamicRangeCompression": dict(dynamic)}

    def _apply_kind_adjustments(
        self, recommendation: dict[str, dict[str, Any]]
    ) -> None:
        metrics = self._metrics
        if self.image_kind == "lowContrastPhoto":
            recommendation["toneMapping"] = {
                "mode": "scurve",
                "exposure": _exposure(1.06),
                "saturation": _linear(0 if metrics["gray_ratio"] >= 0.72 else 0.9),
                "strength": 1 if metrics["luma_range"] <= 70 else 0.9,
                "shadowBoost": 0.2 if metrics["luma_p05"] >= 55 else 0.28,
                "highlightCompress": -0.75,
                "midpoint": 0.44 if metrics["luma_p95"] <= 190 else 0.46,
            }
            recommendation["dynamicRangeCompression"] = {
                "mode": "auto",
                "strength": 0.96 if metrics["luma_range"] <= 70 else 0.88,
                "lowPercentile": 0.02,
                "highPercentile": 0.98,
            }
        elif self.image_kind == "highContrastPhoto":
            recommendation["toneMapping"] = {
                "mode": "contrast",
                "exposure": 0,
                "saturation": _linear(1.05),
                "contrast": 0,
            }
            recommendation["dynamicRangeCompression"] = {
                "mode": "display",
                "strength": 0.85,
            }
        elif self.image_kind == "photo":
            if metrics["luma_std"] <= 42:
                recommendation["toneMapping"] = {
                    "mode": "scurve",
                    "exposure": _exposure(1.04),
                    "saturation": _linear(1.12),
                    "strength": 0.66,
                    "shadowBoost": 0.05,
                    "highlightCompress": -1.2,
                    "midpoint": 0.49,
                }
                recommendation["dynamicRangeCompression"] = {
                    "mode": "auto",
                    "strength": 0.68,
                    "lowPercentile": 0.01,
                    "highPercentile": 0.99,
                }
            elif metrics["luma_std"] >= 70:
                recommendation["dynamicRangeCompression"] = {
                    "mode": "display",
                    "strength": 0.78,
                }
            else:
                recommendation["dynamicRangeCompression"] = {
                    "mode": "display",
                    "strength": 0.7,
                }
        elif self.image_kind == "flatIllustration":
            recommendation["toneMapping"] = {
                "mode": "scurve",
                "exposure": _exposure(1.06),
                "saturation": _linear(
                    1.35 if metrics["high_saturation_ratio"] >= 0.28 else 1.45
                ),
                "strength": 0.68,
                "shadowBoost": 0.06,
                "highlightCompress": -1.2,
                "midpoint": 0.5,
            }
            recommendation["dynamicRangeCompression"] = {"mode": "off"}
        elif self.image_kind == "textOrUi":
            recommendation["toneMapping"] = {
                "mode": "contrast",
                "exposure": _exposure(1.04),
                "saturation": _linear(0.85 if metrics["gray_ratio"] >= 0.7 else 1),
                "contrast": _linear(1.2),
            }
            recommendation["dynamicRangeCompression"] = {
                "mode": "display",
                "strength": 0.72,
            }
        elif self.image_kind == "lineArt":
            narrow = metrics["luma_range"] <= 96
            recommendation["toneMapping"] = {
                "mode": "contrast",
                "exposure": 0,
                "saturation": _linear(0.75),
                "contrast": _linear(1.42 if narrow else 1.25),
            }
            recommendation["dynamicRangeCompression"] = {
                "mode": "auto" if narrow else "display",
                "strength": 0.9 if narrow else 0.65,
                **({"lowPercentile": 0.02, "highPercentile": 0.98} if narrow else {}),
            }
        elif self.image_kind == "pixelArt":
            recommendation["toneMapping"] = {
                "mode": "off",
                "exposure": 0,
                "saturation": 0,
            }
            recommendation["dynamicRangeCompression"] = {"mode": "off"}

    def _apply_restore(self, recommendation: dict[str, dict[str, Any]]) -> None:
        metrics = self._metrics
        recommendation["toneMapping"] = {
            "mode": "scurve",
            "exposure": _exposure(1.1 if metrics["luma_p95"] <= 190 else 1.06),
            "saturation": _linear(0 if metrics["gray_ratio"] >= 0.72 else 0.9),
            "strength": 1 if metrics["luma_range"] <= 70 else 0.92,
            "shadowBoost": 0.2 if metrics["luma_p05"] >= 55 else 0.28,
            "highlightCompress": -0.75,
            "midpoint": 0.44 if metrics["luma_p95"] <= 190 else 0.46,
        }
        recommendation["dynamicRangeCompression"] = {
            "mode": "auto",
            "strength": 0.96 if metrics["luma_range"] <= 70 else 0.9,
            "lowPercentile": 0.02,
            "highPercentile": 0.98,
        }

    def _apply_learned_tuning(self, recommendation: dict[str, dict[str, Any]]) -> None:
        metrics = self._metrics
        if self.intent != "natural" or self._is_restorable_low_contrast():
            return
        if (
            self.image_kind == "flatIllustration"
            and metrics["gray_ratio"] >= 0.82
            and metrics["top_color_coverage"] >= 0.9
            and metrics["edge_density"] >= 0.16
        ):
            recommendation["toneMapping"] = {
                "mode": "contrast",
                "exposure": _exposure(1.03),
                "saturation": _linear(0.9),
                "contrast": _linear(1.2),
            }
            recommendation["dynamicRangeCompression"] = {
                "mode": "display",
                "strength": 0.75,
            }

    def _apply_poster_scan_tuning(
        self, recommendation: dict[str, dict[str, Any]]
    ) -> None:
        metrics = self._metrics
        is_graphic = (
            self.image_kind in {"flatIllustration", "textOrUi", "lineArt"}
            or metrics["flat_ratio"] >= 0.5
        )
        has_ink = (
            metrics["dark_neutral_ratio"] >= 0.025
            or metrics["red_ratio"] >= 0.008
            or metrics["edge_density"] >= 0.05
        )
        if metrics["warm_paper_ratio"] < 0.18 or not has_ink or not is_graphic:
            return
        recommendation["toneMapping"] = {
            "mode": "scurve",
            "exposure": _exposure(1.04),
            "saturation": _linear(1.05),
            "strength": 0.92,
            "shadowBoost": 0.08,
            "highlightCompress": -0.55,
            "midpoint": 0.44,
        }
        recommendation["dynamicRangeCompression"] = {
            "mode": "auto",
            "strength": 1,
            "lowPercentile": 0.015,
            "highPercentile": 0.985,
        }

    def _apply_palette_tuning(self, recommendation: dict[str, dict[str, Any]]) -> None:
        profile = self._palette_profile
        if not profile:
            return
        if profile["color_count"] <= 2:
            recommendation["toneMapping"] = {
                "mode": "scurve",
                "exposure": 0,
                "saturation": -1,
                "strength": 0.8,
                "shadowBoost": 0.1,
                "highlightCompress": -1.4,
                "midpoint": 0.5,
            }
            recommendation["dynamicRangeCompression"] = {
                "mode": "display",
                "strength": 1,
            }
        elif (
            profile["luma_range"] <= 150
            and recommendation["dynamicRangeCompression"].get("mode") == "off"
        ):
            recommendation["dynamicRangeCompression"] = {
                "mode": "display",
                "strength": 0.7,
            }

    def _apply_intent(self, recommendation: dict[str, dict[str, Any]]) -> None:
        if self.intent == "vivid":
            tone = recommendation["toneMapping"]
            tone.update(
                {
                    "mode": "scurve",
                    "saturation": max(tone.get("saturation", 0), _linear(1.45)),
                    "strength": tone.get("strength", 0.72),
                    "shadowBoost": tone.get("shadowBoost", 0.08),
                    "highlightCompress": tone.get("highlightCompress", -1.3),
                    "midpoint": tone.get("midpoint", 0.5),
                }
            )
        elif self.intent == "readable":
            recommendation["toneMapping"]["mode"] = "contrast"
            recommendation["toneMapping"]["contrast"] = max(
                recommendation["toneMapping"].get("contrast", 0), 0
            )
        elif self.intent == "lowNoise":
            recommendation["toneMapping"] = {
                "mode": "contrast",
                "exposure": 0,
                "saturation": _linear(1.1),
                "contrast": _linear(0.9),
            }
            recommendation["dynamicRangeCompression"] = {
                "mode": "display",
                "strength": 1,
            }

    def _enforce_minimum_contrast(
        self, recommendation: dict[str, dict[str, Any]]
    ) -> None:
        tone = recommendation["toneMapping"]
        if tone.get("mode") == "contrast":
            tone["contrast"] = max(tone.get("contrast", 0), 0)

    def _enforce_white_preservation(
        self, recommendation: dict[str, dict[str, Any]]
    ) -> None:
        dynamic = recommendation["dynamicRangeCompression"]
        if dynamic.get("mode") != "off":
            dynamic.update(
                {
                    "preserveWhite": True,
                    "whitePreservePercentile": 0.99,
                    "whitePreserveMinLuma": 150,
                }
            )

    def _is_restorable_low_contrast(self) -> bool:
        metrics = self._metrics
        if self.image_kind == "lowContrastPhoto":
            return True
        if (
            metrics["luma_range"] > 96
            or metrics["luma_std"] > 32
            or self.image_kind == "pixelArt"
        ):
            return False
        if metrics["gray_ratio"] < 0.5 and metrics["saturation_mean"] > 0.18:
            return False
        return metrics["edge_density"] >= 0.015 or metrics["flat_ratio"] >= 0.04

    def _measure_palette(self) -> dict[str, float] | None:
        colors = []
        for entry in self.palette:
            value = entry.get("color", "").lstrip("#")
            if len(value) == 3:
                value = "".join(channel * 2 for channel in value)
            if len(value) == 6:
                colors.append(
                    tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))
                )
        if not colors:
            return None
        rgb = np.asarray(colors, dtype=np.float64)
        lumas = rgb @ np.asarray([0.2126, 0.7152, 0.0722])
        saturation = (rgb.max(axis=1) - rgb.min(axis=1)) / np.maximum(
            rgb.max(axis=1), 1
        )
        return {
            "color_count": float(len(colors)),
            "luma_range": float(lumas.max() - lumas.min()),
            "average_saturation": float(saturation.mean()),
        }

    def _measure(self, max_dimension: int) -> dict[str, float]:
        image = self.image.copy()
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.BILINEAR)
        data = np.asarray(image, dtype=np.uint8)
        red, green, blue = [data[..., index].astype(np.float64) for index in range(3)]
        luma = red * 0.2126 + green * 0.7152 + blue * 0.0722
        hsv = cv2.cvtColor(data, cv2.COLOR_RGB2HSV)
        saturation = hsv[..., 1].astype(np.float64) / 255
        edges = cv2.Canny(data, 50, 150)
        flatness = cv2.Laplacian(luma, cv2.CV_64F) ** 2 <= 100
        warm_paper = (
            (red >= green)
            & (green >= blue)
            & ((red - blue) >= 8)
            & (luma >= 150)
            & (saturation <= 0.56)
        )
        red_pixels = (red >= green * 1.18) & (red >= blue * 1.18) & (saturation >= 0.25)
        dark_neutral = (luma <= 88) & (saturation <= 0.36)
        quantized = (data // 16).reshape(-1, 3)
        _, counts = np.unique(quantized, axis=0, return_counts=True)
        return {
            "luma_range": float(np.percentile(luma, 95) - np.percentile(luma, 5)),
            "luma_std": float(luma.std()),
            "luma_p05": float(np.percentile(luma, 5)),
            "luma_p95": float(np.percentile(luma, 95)),
            "gray_ratio": float((saturation <= 0.08).mean()),
            "saturation_mean": float(saturation.mean()),
            "high_saturation_ratio": float((saturation >= 0.72).mean()),
            "edge_density": float((edges > 0).mean()),
            "flat_ratio": float(flatness.mean()),
            "warm_paper_ratio": float(warm_paper.mean()),
            "red_ratio": float(red_pixels.mean()),
            "dark_neutral_ratio": float(dark_neutral.mean()),
            "top_color_coverage": float(counts.max() / quantized.shape[0]),
        }

    def _classify(self) -> str:
        metrics = self._metrics
        if (
            metrics["luma_range"] <= 96
            and metrics["luma_std"] <= 32
            and metrics["gray_ratio"] >= 0.5
        ):
            return "lowContrastPhoto"
        if metrics["luma_std"] >= 70:
            return "highContrastPhoto"
        if metrics["flat_ratio"] >= 0.7 and metrics["edge_density"] >= 0.1:
            return "flatIllustration"
        if metrics["gray_ratio"] >= 0.76 and metrics["edge_density"] >= 0.12:
            return "lineArt"
        return "photo"


__all__ = ["Suggestion"]
