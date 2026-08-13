from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

import numpy as np


CORE_VOWELS = {"あ", "い", "う", "え", "お"}
DEFAULT_CLASSIFICATION_FEATURES = ("f1_hz", "f2_hz", "f3_hz", "spectral_slope_db_khz", "spectral_centroid_hz")


def estimation_failure_report(features: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for bundle in features:
        metadata = bundle.get("metadata", {})
        group_keys = ("overall", f"profile:{bundle.get('profile', 'unknown')}", f"label:{metadata.get('label', 'unknown')}", f"speaker:{metadata.get('speaker_id', 'unknown')}")
        f0 = bundle.get("estimates", {}).get("f0_hz", {})
        formants = bundle.get("estimates", {}).get("formants", {})
        statuses = {
            "samples": True,
            "f0_failed": f0.get("value") is None,
            "formants_incomplete": float(formants.get("confidence", 0.0)) < 1.0,
            "invalid_audio": not bundle.get("metadata", {}).get("validation", {}).get("valid", False),
        }
        for key in group_keys:
            for status, applies in statuses.items():
                grouped[key][status] += int(applies)
    result = {}
    for key, counts in grouped.items():
        samples = max(1, counts["samples"])
        result[key] = {**dict(counts), "f0_failure_rate": counts["f0_failed"] / samples, "formant_incomplete_rate": counts["formants_incomplete"] / samples, "invalid_audio_rate": counts["invalid_audio"] / samples}
    return result


def leave_one_speaker_out(features: list[dict[str, Any]], feature_names: tuple[str, ...] = DEFAULT_CLASSIFICATION_FEATURES) -> dict[str, Any]:
    samples = [bundle for bundle in features if bundle.get("metadata", {}).get("label") in CORE_VOWELS and bundle.get("metadata", {}).get("kind") == "human"]
    speakers = sorted({bundle["metadata"]["speaker_id"] for bundle in samples})
    folds = []
    predictions = []
    for held_out in speakers:
        train = [bundle for bundle in samples if bundle["metadata"]["speaker_id"] != held_out]
        test = [bundle for bundle in samples if bundle["metadata"]["speaker_id"] == held_out]
        if not train or not test:
            continue
        global_values = {name: [float(item["scalar"][name]) for item in train if isinstance(item.get("scalar", {}).get(name), (int, float)) and math.isfinite(item["scalar"][name])] for name in feature_names}
        scales = {name: max(float(np.median(np.abs(np.asarray(values) - np.median(values)))) * 1.4826, 1e-6) for name, values in global_values.items() if values}
        centroids: dict[str, dict[str, float]] = defaultdict(dict)
        for label in CORE_VOWELS:
            label_samples = [item for item in train if item["metadata"]["label"] == label]
            for name in feature_names:
                values = [float(item["scalar"][name]) for item in label_samples if isinstance(item.get("scalar", {}).get(name), (int, float)) and math.isfinite(item["scalar"][name])]
                if values:
                    centroids[label][name] = float(np.median(values))
        fold_correct = 0
        for item in test:
            distances = {}
            for label, centroid in centroids.items():
                components = [abs(float(item["scalar"][name]) - center) / scales[name] for name, center in centroid.items() if name in scales and isinstance(item.get("scalar", {}).get(name), (int, float)) and math.isfinite(item["scalar"][name])]
                if components:
                    distances[label] = float(np.mean(components))
            prediction = min(distances, key=distances.get) if distances else None
            correct = prediction == item["metadata"]["label"]
            fold_correct += int(correct)
            predictions.append({"sample_id": item["sample_id"], "speaker_id": held_out, "actual": item["metadata"]["label"], "predicted": prediction, "correct": correct, "distances": distances})
        folds.append({"held_out_speaker": held_out, "sample_count": len(test), "accuracy": fold_correct / len(test)})
    accuracy = sum(item["correct"] for item in predictions) / len(predictions) if predictions else None
    return {"feature_names": list(feature_names), "speaker_count": len(speakers), "folds": folds, "accuracy": accuracy, "chance_accuracy": 1.0 / len(CORE_VOWELS), "predictions": predictions}
