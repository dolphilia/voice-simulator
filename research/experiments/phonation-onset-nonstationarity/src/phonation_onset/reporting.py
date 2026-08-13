from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np


def write_summary_csv(path: Path, analyses: list[dict[str, Any]]) -> None:
    rows = []
    for item in analyses:
        boundaries = item["boundaries"]
        row = {
            "sample_id": item["sample_id"], "speaker_id": item["speaker_id"], "take_id": item["take_id"],
            "boundary_confidence": boundaries["confidence"],
            "activity_onset_sec": boundaries["acoustic_activity_onset_sec"],
            "periodicity_onset_sec": boundaries["periodicity_onset_sec"],
            "stable_pitch_onset_sec": boundaries["stable_pitch_onset_sec"],
            "stable_source_onset_sec": boundaries["stable_source_onset_sec"],
            "stable_vowel_onset_sec": boundaries["stable_vowel_onset_sec"],
        }
        for feature in ("f0_hz", "periodicity", "rms_db", "hnr_db", "h1_h2_db", "spectral_slope_db_khz", "f1_hz", "f2_hz"):
            values = item["summary"].get(feature, {})
            row[f"{feature}_onset"] = values.get("onset_median")
            row[f"{feature}_stable"] = values.get("stable_median")
            row[f"{feature}_delta"] = values.get("start_to_stable_delta")
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["sample_id"])
        writer.writeheader(); writer.writerows(rows)


def markdown_analysis(analyses: list[dict[str, Any]]) -> str:
    speakers = defaultdict(int)
    confidences = []
    for item in analyses:
        speakers[item["speaker_id"]] += 1
        confidences.append(float(item["boundaries"]["confidence"]))
    lines = [
        "# 発声開始 development 自動解析", "",
        "この結果は知覚自然さの判定ではなく、試聴前の刺激生成と軌道設計に使う。", "",
        f"- 解析数: {len(analyses)}", f"- 話者数: {len(speakers)}",
        f"- 境界信頼度中央値: {sorted(confidences)[len(confidences)//2]:.3f}" if confidences else "- 境界信頼度中央値: —", "",
        "| sample | speaker | activity ms | periodicity ms | stable pitch ms | stable source ms | stable vowel ms | confidence |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in analyses:
        b = item["boundaries"]
        value = lambda key: "—" if b[key] is None else f"{1000 * float(b[key]):.1f}"
        lines.append(f"| {item['sample_id']} | {item['speaker_id']} | {value('acoustic_activity_onset_sec')} | {value('periodicity_onset_sec')} | {value('stable_pitch_onset_sec')} | {value('stable_source_onset_sec')} | {value('stable_vowel_onset_sec')} | {float(b['confidence']):.2f} |")
    lines += ["", "## 制約", "", "- 同一話者の2件は別テイクではなく、UTAUの音源表情差を含む。", "- stable vowel境界は初期版の候補であり、formant軌道のcoverageと併記する。", "- onset-holdoutはこの解析に含めていない。", ""]
    return "\n".join(lines)


def derive_model_parameters(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    def values(feature: str, field: str) -> list[float]:
        output = []
        for item in analyses:
            value = item.get("summary", {}).get(feature, {}).get(field)
            if value is not None and np.isfinite(value):
                output.append(float(value))
        return output

    def robust(feature: str, field: str, fallback: float) -> dict[str, float | int]:
        data = values(feature, field)
        if not data:
            return {"median": fallback, "mad": 0.0, "count": 0}
        array = np.asarray(data)
        median = float(np.median(array))
        return {"median": median, "mad": float(np.median(np.abs(array - median))), "count": len(data)}

    durations = []
    for item in analyses:
        boundaries = item["boundaries"]
        start, stable = boundaries.get("acoustic_activity_onset_sec"), boundaries.get("stable_vowel_onset_sec")
        if start is not None and stable is not None:
            durations.append(float(stable) - float(start))
    duration = float(np.median(durations)) if durations else 0.16
    change_features = ["f0_hz", "rms_db", "periodicity", "hnr_db", "spectral_slope_db_khz", "f1_hz", "f2_hz"]
    matrix = []
    complete_features = []
    for feature in change_features:
        column = values(feature, "start_to_stable_delta")
        if len(column) == len(analyses):
            matrix.append(column); complete_features.append(feature)
    correlation = np.corrcoef(np.asarray(matrix)) if len(matrix) >= 2 else np.empty((0, 0))
    return {
        "schema_version": "0.1.0", "sample_count": len(analyses),
        "evidence_level": "exploratory-development; UTAU voice-style variants; not a population estimate",
        "onset_duration_sec": {"median": duration, "count": len(durations)},
        "stable": {
            "f0_hz": robust("f0_hz", "stable_median", 180.0),
            "f1_hz": robust("f1_hz", "stable_median", 800.0),
            "f2_hz": robust("f2_hz", "stable_median", 1300.0),
            "f3_hz": robust("f3_hz", "stable_median", 2500.0),
            "periodicity": robust("periodicity", "stable_median", 0.8),
            "hnr_db": robust("hnr_db", "stable_median", 10.0),
            "spectral_slope_db_khz": robust("spectral_slope_db_khz", "stable_median", -6.0),
        },
        "start_to_stable": {feature: robust(feature, "start_to_stable_delta", 0.0) for feature in change_features},
        "complete_case_correlation": {
            "features": complete_features,
            "matrix": correlation.astype(float).tolist(),
            "warning": "n=6の探索値。相関変動の候補作成にだけ使い、知覚効果や一般性を主張しない。",
        },
    }


def markdown_model_parameters(model: dict[str, Any]) -> str:
    lines = [
        "# 発声開始の低次元記述", "",
        "development 6件から得た探索的な記述である。知覚自然さや人間一般の分布を表すものではない。", "",
        f"- onset duration中央値: {1000 * float(model['onset_duration_sec']['median']):.1f} ms", "",
        "| 特徴 | stable中央値 | start→stable変化中央値 | coverage count |",
        "| --- | ---: | ---: | ---: |",
    ]
    for feature, stable in model["stable"].items():
        change = model["start_to_stable"].get(feature, {"median": 0.0})
        lines.append(f"| {feature} | {float(stable['median']):.4f} | {float(change['median']):.4f} | {int(stable['count'])} |")
    lines += [
        "", "## モデルへの移し方", "",
        "- onset duration、stable F0、stable formantはC系列の代表値に使う。",
        "- F0、RMS、周期性、声質、formantを共有進行度で動かすC6と、独立軌道のC7を対照にする。",
        "- n=6の相関係数をそのまま生成係数へせず、相関の有無という仮説だけを移す。",
        "- 自動値の良否ではなく、凍結後の試聴でH3〜H5を判断する。", "",
    ]
    return "\n".join(lines)
