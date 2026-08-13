from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .models import MetricResult
from .baseline import envelope_score


FEATURE_CATEGORIES = {
    "clipping_ratio": "signal_integrity", "dc_offset": "signal_integrity", "nyquist_band_ratio": "signal_integrity",
    "f0_hz": "pitch_voicing", "voiced_ratio": "pitch_voicing",
    "f1_hz": "resonance", "f2_hz": "resonance", "f3_hz": "resonance", "b1_hz": "resonance", "b2_hz": "resonance", "b3_hz": "resonance",
    "spectral_centroid_hz": "spectral_timbre", "spectral_rolloff_hz": "spectral_timbre", "spectral_slope_db_khz": "spectral_timbre",
    "h1_h2_db": "source_voice_quality", "hnr_db": "source_voice_quality", "cpp_db": "source_voice_quality",
    "spectral_flatness": "noise_frication", "zero_crossing_rate": "noise_frication",
    "duration_sec": "timing_transition", "active_duration_sec": "timing_transition",
}


def diagnostic_recommendation(name: str, signed_value: float) -> str:
    change = "下げる" if signed_value > 0 else "上げる"
    if name.startswith("f0_"):
        return f"生成側の基本周波数を{change}方向で検証する"
    if name.startswith(("f1_", "f2_", "f3_", "b1_", "b2_", "b3_")):
        return f"対応する声道共鳴または帯域幅を{change}方向で検証する"
    if name == "level_delta_db":
        return f"出力gainを{change}方向で検証する"
    if "spectral_centroid" in name or "spectral_slope" in name or "rolloff" in name:
        return f"brightness、音源傾斜、高域filterを{change}方向で検証する"
    if "flatness" in name or "zero_crossing" in name:
        return f"breath/noise成分を{change}方向で検証する"
    if name.endswith("_delta_ms"):
        return "onset、release、transition時間を調整して再評価する"
    return "対応パラメータを一つずつ変え、既知fixtureと副作用を確認する"


def target_score(metric: MetricResult, reference_scale: float | None = None) -> float | None:
    if not metric.available or metric.value is None:
        return None
    if metric.direction == "higher":
        value = min(1.0, max(-1.0, metric.value))
        return 100.0 * max(0.0, value)
    scale = reference_scale if reference_scale and reference_scale > 0 else default_scale(metric.name)
    return 100.0 * math.exp(-abs(metric.value) / max(scale, 1e-12))


def default_scale(name: str) -> float:
    if "bark" in name:
        return 0.8
    if name.startswith(("b1_", "b2_", "b3_")):
        return 100.0
    if "formant" in name or name.startswith(("f1_", "f2_", "f3_")):
        return 150.0
    if "cent" in name:
        return 100.0
    if name.endswith("_ms"):
        return 50.0
    if "correlation" in name or "f1" == name:
        return 1.0
    if "ratio" in name or "flatness" in name or "waveform_rmse" in name:
        return 0.2
    if "mfcc" in name:
        return 40.0
    if "spectral" in name or "mel" in name or name.endswith("_db"):
        return 12.0
    return 1000.0


def build_scorecard(metrics: list[MetricResult], profile: str, reference_id: str, generated_id: str) -> dict[str, Any]:
    grouped: dict[str, list[tuple[MetricResult, float | None]]] = defaultdict(list)
    for metric in metrics:
        grouped[metric.category].append((metric, target_score(metric)))
    categories: dict[str, Any] = {}
    for category, entries in grouped.items():
        available = [(metric, score) for metric, score in entries if score is not None]
        confidence_weight = sum(metric.confidence for metric, _ in available)
        score = sum(float(item_score) * metric.confidence for metric, item_score in available) / confidence_weight if confidence_weight else None
        categories[category] = {
            "target_similarity": score,
            "human_likeness": None,
            "coverage": len(available) / len(entries),
            "confidence": confidence_weight / len(entries),
            "metrics": [{**metric.to_dict(), "target_score": item_score} for metric, item_score in entries],
            "directional_diagnostics": [
                {
                    "metric": metric.name,
                    "signed_value": metric.signed_value,
                    "unit": metric.unit,
                    "interpretation": "generated_higher_or_later" if metric.signed_value and metric.signed_value > 0 else "generated_lower_or_earlier",
                    "recommendation": diagnostic_recommendation(metric.name, metric.signed_value),
                }
                for metric, _ in sorted(entries, key=lambda item: abs(item[0].signed_value or 0.0), reverse=True)
                if metric.signed_value is not None and abs(metric.signed_value) > 1e-12
            ][:3],
        }
    return {
        "profile": profile,
        "reference_id": reference_id,
        "generated_id": generated_id,
        "categories": categories,
        "aggregate": None,
        "aggregate_reason": "listening-calibrated weights are not available; category scores must remain separate",
    }


def add_human_likeness(card: dict[str, Any], feature_bundle: dict[str, Any], baseline: dict[str, Any], label: str) -> None:
    key = f"{feature_bundle['profile']}:{label}"
    distributions = baseline.get("feature_distributions", {}).get(key, {})
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    values = dict(feature_bundle.get("scalar", {}))
    values.update({name: estimate.get("value") for name, estimate in feature_bundle.get("estimates", {}).items()})
    for name, value in values.items():
        if name not in FEATURE_CATEGORIES or name not in distributions:
            continue
        score, confidence = envelope_score(value, distributions[name])
        if score is not None:
            grouped[FEATURE_CATEGORIES[name]].append((score, confidence))
    for category, category_values in grouped.items():
        entry = card["categories"].setdefault(category, {"target_similarity": None, "coverage": 0.0, "confidence": 0.0, "metrics": []})
        total_confidence = sum(confidence for _, confidence in category_values)
        entry["human_likeness"] = sum(score * confidence for score, confidence in category_values) / total_confidence if total_confidence else None
        entry["human_likeness_coverage"] = len(category_values) / max(1, sum(1 for name, mapped in FEATURE_CATEGORIES.items() if mapped == category))
