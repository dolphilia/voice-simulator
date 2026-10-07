from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from .generator_adapter import render_b9, write_render
from .measurement_adapter import evaluate_constraints, measure
from .sensitivity import REPORTED_FEATURES, _numeric_summary
from .time_structure import extract_temporal_metrics


def _halton(index: int, base: int) -> float:
    result = 0.0
    factor = 1.0 / base
    value = index
    while value:
        result += factor * (value % base)
        value //= base
        factor /= base
    return result


def _parameters(config: dict[str, Any], f0: float, amplitude: float, correlation: float) -> dict[str, float]:
    return {
        **{name: float(value) for name, value in config["fixed_parameters"].items()},
        "f0_std_fraction": float(f0),
        "amplitude_std_db": float(amplitude),
        "f0_amplitude_correlation": float(correlation),
    }


def freeze_settings(config: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = config["baseline_parameters"]
    anchors = [
        (baseline["f0_std_fraction"], baseline["amplitude_std_db"], baseline["f0_amplitude_correlation"], "baseline"),
        (0.0, 0.0, 0.5, "static-controls"),
        (0.0, 0.67, 0.5, "f0-static"),
        (0.0032, 0.67, 0.5, "f0-half"),
        (0.0128, 0.67, 0.5, "f0-double"),
        (0.0064, 0.0, 0.5, "amplitude-static"),
        (0.0064, 0.335, 0.5, "amplitude-half"),
        (0.0064, 0.67, 0.0, "correlation-zero"),
        (0.0064, 0.67, 0.25, "correlation-quarter"),
        (0.0064, 0.67, 0.75, "correlation-three-quarter"),
        (0.0064, 0.67, 1.0, "correlation-one"),
    ]
    settings = [
        {"setting_id": f"structured-{index:02d}", "method": "structured", "provenance": label,
         "parameters": _parameters(config, f0, amplitude, correlation)}
        for index, (f0, amplitude, correlation, label) in enumerate(anchors)
    ]
    bounds = config["search_axes"]
    structured_count = int(config["budget"]["structured_settings"])
    index = 1
    while len(settings) < structured_count:
        unit = (_halton(index, 2), _halton(index, 3), _halton(index, 5))
        values = [bounds[name][0] + unit[i] * (bounds[name][1] - bounds[name][0])
                  for i, name in enumerate(bounds)]
        settings.append({
            "setting_id": f"structured-{len(settings):02d}",
            "method": "structured",
            "provenance": f"halton-{index}",
            "parameters": _parameters(config, *values),
        })
        index += 1

    random_count = int(config["budget"]["stratified_random_settings"])
    rng = np.random.default_rng(int(config["setting_generation"]["random_seed"]))
    columns = []
    for name in bounds:
        unit = (np.arange(random_count, dtype=float) + rng.random(random_count)) / random_count
        rng.shuffle(unit)
        lower, upper = bounds[name]
        columns.append(lower + unit * (upper - lower))
    for row in range(random_count):
        settings.append({
            "setting_id": f"random-{row:02d}",
            "method": "stratified-random",
            "provenance": f"latin-hypercube-seed-{config['setting_generation']['random_seed']}",
            "parameters": _parameters(config, *(column[row] for column in columns)),
        })
    return settings


def _cell(values: dict[str, float | None], bins: dict[str, list[float]]) -> str | None:
    indices = []
    for feature, edges in bins.items():
        value = values.get(feature)
        if value is None or not np.isfinite(value):
            return None
        indices.append(str(int(np.digitize(float(value), np.asarray(edges), right=False))))
    return ":".join(indices)


def run_search(output_dir: Path, config: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    settings = freeze_settings(config)
    expected = int(config["budget"]["structured_settings"]) + int(config["budget"]["stratified_random_settings"])
    if len(settings) != expected:
        raise ValueError("凍結設定数が予算と一致しません")
    records = []
    for setting in settings:
        for seed in config["seed_offsets"]:
            candidate = render_b9(setting["parameters"], int(seed))
            path = output_dir / "audio" / f"{setting['setting_id']}--seed-{seed}.wav"
            digest = write_render(path, candidate)
            measured = measure(path, candidate, f"{setting['setting_id']}--seed-{seed}")
            temporal = extract_temporal_metrics(path, f"{setting['setting_id']}--seed-{seed}")
            records.append({
                "setting_id": setting["setting_id"],
                "method": setting["method"],
                "parameters": setting["parameters"],
                "seed_offset": seed,
                "wav_sha256": digest,
                "relative_audio_path": str(path.relative_to(output_dir)),
                "engineering_checks": evaluate_constraints(measured, targets),
                "values": {**{name: measured["values"].get(name) for name in REPORTED_FEATURES}, **temporal},
            })
    feature_names = tuple(config["behavior_bins"])
    summaries = []
    for setting in settings:
        rows = [row for row in records if row["setting_id"] == setting["setting_id"]]
        values = {name: _numeric_summary([row["values"].get(name) for row in rows]) for name in feature_names}
        medians = {name: summary["median"] for name, summary in values.items()}
        summaries.append({
            **setting,
            "engineering_pass_rate": sum(row["engineering_checks"]["passed"] for row in rows) / len(rows),
            "behavior_features": values,
            "behavior_cell": _cell(medians, config["behavior_bins"]),
        })
    method_summary = {}
    for method in ("structured", "stratified-random"):
        rows = [row for row in summaries if row["method"] == method]
        passing = [row for row in rows if row["engineering_pass_rate"] == 1.0]
        cells = sorted({row["behavior_cell"] for row in passing if row["behavior_cell"] is not None})
        method_summary[method] = {
            "settings": len(rows),
            "fully_engineering_qualified": len(passing),
            "occupied_behavior_cells": len(cells),
            "behavior_cells": cells,
        }
    elapsed = time.perf_counter() - started
    return {
        "schema_version": "1.0.0",
        "campaign_id": config["campaign_id"],
        "status": "a3-search-complete",
        "input_pilot_campaign_id": config["input_pilot_campaign_id"],
        "setting_count": len(settings),
        "render_count": len(records),
        "elapsed_sec": elapsed,
        "settings": summaries,
        "records": records,
        "method_summary": method_summary,
        "formal_aggregate_score": None,
        "perceptual_claim_allowed": False,
        "interpretation": "engineering-qualified behavior coverage; no naturalness ranking",
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# A3 有界特徴空間探索",
        "",
        f"- 設定数: {result['setting_count']}",
        f"- 生成数: {result['render_count']}",
        f"- 実行時間: {result['elapsed_sec']:.2f}秒",
        "",
        "| 方法 | 設定 | 全seed工学通過 | 占有特徴セル |",
        "|---|---:|---:|---:|",
    ]
    for method, summary in result["method_summary"].items():
        lines.append(f"| {method} | {summary['settings']} | {summary['fully_engineering_qualified']} | {summary['occupied_behavior_cells']} |")
    lines.extend([
        "",
        "特徴セルはF0変動、RMS包絡変動、スペクトル重心変動の三軸である。セル数は探索法の被覆比較にだけ用い、人声らしさや自然さの順位ではない。",
        "",
    ])
    return "\n".join(lines)
