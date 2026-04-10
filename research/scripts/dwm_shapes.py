from __future__ import annotations

from typing import Iterable

import numpy as np


def _build_polygon_from_width_profile(
    widths_m: Iterable[float],
    length_m: float,
    label: str,
) -> dict:
    widths = np.asarray(list(widths_m), dtype=np.float64)
    if widths.ndim != 1 or widths.size < 2:
        raise ValueError("widths_m must contain at least 2 samples.")

    xs = np.linspace(0.0, length_m, widths.size)
    half = widths / 2.0

    upper = np.column_stack([xs, half])
    lower = np.column_stack([xs[::-1], -half[::-1]])
    polygon = np.vstack([upper, lower])

    glottal_half = float(widths[0] / 2.0)
    lip_half = float(widths[-1] / 2.0)

    return {
        "label": label,
        "polygon": polygon,
        "glottal_port": np.array([[0.0, -glottal_half], [0.0, glottal_half]], dtype=np.float64),
        "lip_port": np.array([[length_m, -lip_half], [length_m, lip_half]], dtype=np.float64),
        "metadata": {
            "kind": "tube-profile",
            "length_m": float(length_m),
            "width_min_m": float(np.min(widths)),
            "width_max_m": float(np.max(widths)),
        },
    }


def make_uniform_tube_shape(length_m: float = 0.17, width_m: float = 0.03) -> dict:
    """Return a rectangular tube shape for smoke tests."""

    if length_m <= 0 or width_m <= 0:
        raise ValueError("length_m and width_m must be positive.")

    polygon = np.array(
        [
            [0.0, width_m / 2.0],
            [length_m, width_m / 2.0],
            [length_m, -width_m / 2.0],
            [0.0, -width_m / 2.0],
        ],
        dtype=np.float64,
    )

    return {
        "label": "uniform_tube",
        "polygon": polygon,
        "glottal_port": np.array([[0.0, -width_m / 2.0], [0.0, width_m / 2.0]], dtype=np.float64),
        "lip_port": np.array([[length_m, -width_m / 2.0], [length_m, width_m / 2.0]], dtype=np.float64),
        "metadata": {
            "kind": "uniform-tube",
            "length_m": float(length_m),
            "width_m": float(width_m),
        },
    }


def make_vowel_shape(vowel: str, length_m: float = 0.17) -> dict:
    """Return a coarse 2D vocal-tract polygon for a Japanese vowel."""

    profiles = {
        "a": [0.022, 0.024, 0.026, 0.030, 0.034, 0.038, 0.035, 0.030, 0.026],
        "i": [0.020, 0.024, 0.028, 0.030, 0.026, 0.018, 0.012, 0.011, 0.014],
        "u": [0.018, 0.020, 0.024, 0.028, 0.025, 0.021, 0.017, 0.015, 0.013],
        "e": [0.020, 0.023, 0.026, 0.028, 0.025, 0.019, 0.016, 0.015, 0.017],
        "o": [0.018, 0.021, 0.026, 0.031, 0.034, 0.032, 0.026, 0.020, 0.015],
    }
    key = vowel.lower()
    if key not in profiles:
        raise ValueError(f"Unsupported vowel: {vowel}")

    return _build_polygon_from_width_profile(profiles[key], length_m=length_m, label=f"vowel_{key}")


def list_available_shapes() -> list[str]:
    return ["uniform_tube", "vowel_a", "vowel_i", "vowel_u", "vowel_e", "vowel_o"]
