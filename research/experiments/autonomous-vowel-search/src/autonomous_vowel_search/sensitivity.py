from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from .generator_adapter import render_b9, write_render
from .measurement_adapter import evaluate_constraints, measure


REPORTED_FEATURES = (
    "spectral_centroid_hz",
    "spectral_slope_db_khz",
    "h1_h2_db",
    "hnr_db",
    "cpp_db",
    "spectral_flatness",
    "f0_hz",
    "rendered_f0_std_fraction",
    "rendered_amplitude_std_db",
    "rendered_control_correlation",
)


def _settings(campaign: dict[str, Any]) -> list[dict[str, Any]]:
    baseline = campaign["baseline_parameters"]
    settings = [{"setting_id": "baseline", "axis": None, "value": None, "parameters": dict(baseline)}]
    for name, axis in campaign["parameter_axes"].items():
        if not axis["status"].startswith("pilot"):
            continue
        for value in axis["pilot_values"]:
            if float(value) == float(baseline[name]):
                continue
            parameters = dict(baseline)
            parameters[name] = float(value)
            settings.append({
                "setting_id": f"{name}-{float(value):g}",
                "axis": name,
                "value": float(value),
                "parameters": parameters,
            })
    return settings


def _numeric_summary(values: list[float | None]) -> dict[str, float | int | None]:
    available = np.asarray([float(value) for value in values if value is not None and np.isfinite(value)], dtype=float)
    return {
        "median": float(np.median(available)) if available.size else None,
        "minimum": float(np.min(available)) if available.size else None,
        "maximum": float(np.max(available)) if available.size else None,
        "available": int(available.size),
        "total": len(values),
    }


def run_sensitivity(output_dir: Path, campaign: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    records = []
    for setting in _settings(campaign):
        for seed in campaign["seed_sets"]["pilot"]:
            before = time.perf_counter()
            candidate = render_b9(setting["parameters"], int(seed))
            audio_path = output_dir / "audio" / f"{setting['setting_id']}--seed-{seed}.wav"
            digest = write_render(audio_path, candidate)
            measurement = measure(audio_path, candidate, f"{setting['setting_id']}--seed-{seed}")
            constraints = evaluate_constraints(measurement, targets)
            records.append({
                "setting_id": setting["setting_id"],
                "axis": setting["axis"],
                "value": setting["value"],
                "parameters": setting["parameters"],
                "seed_offset": seed,
                "wav_sha256": digest,
                "relative_audio_path": str(audio_path.relative_to(output_dir)),
                "elapsed_sec": time.perf_counter() - before,
                "engineering_checks": constraints,
                "values": {name: measurement["values"].get(name) for name in REPORTED_FEATURES},
                "states": {name: measurement["states"].get(name, "unsupported") for name in REPORTED_FEATURES},
            })
    grouped: dict[str, dict[str, Any]] = {}
    for setting in _settings(campaign):
        rows = [row for row in records if row["setting_id"] == setting["setting_id"]]
        grouped[setting["setting_id"]] = {
            "axis": setting["axis"],
            "value": setting["value"],
            "constraint_pass_rate": sum(row["engineering_checks"]["passed"] for row in rows) / len(rows),
            "features": {name: _numeric_summary([row["values"].get(name) for row in rows]) for name in REPORTED_FEATURES},
        }
    local_effects = []
    baseline = campaign["baseline_parameters"]
    for name, axis in campaign["parameter_axes"].items():
        if not axis["status"].startswith("pilot"):
            local_effects.append({"axis": name, "status": axis["status"], "reason": "range provenance is insufficient"})
            continue
        center = float(baseline[name])
        lower_values = [float(value) for value in axis["pilot_values"] if float(value) < center]
        upper_values = [float(value) for value in axis["pilot_values"] if float(value) > center]
        lower = max(lower_values) if lower_values else None
        upper = min(upper_values) if upper_values else None
        effect: dict[str, Any] = {"axis": name, "status": "measured", "center": center, "lower": lower, "upper": upper, "slopes": {}}
        center_features = grouped["baseline"]["features"]
        for feature in REPORTED_FEATURES:
            center_value = center_features[feature]["median"]
            slopes: dict[str, float | None] = {"backward": None, "forward": None}
            if center_value is not None and lower is not None:
                lower_value = grouped[f"{name}-{lower:g}"]["features"][feature]["median"]
                if lower_value is not None:
                    slopes["backward"] = (center_value - lower_value) / (center - lower)
            if center_value is not None and upper is not None:
                upper_value = grouped[f"{name}-{upper:g}"]["features"][feature]["median"]
                if upper_value is not None:
                    slopes["forward"] = (upper_value - center_value) / (upper - center)
            effect["slopes"][feature] = slopes
        local_effects.append(effect)
    total_elapsed = time.perf_counter() - started
    storage = sum(path.stat().st_size for path in (output_dir / "audio").glob("*.wav"))
    return {
        "schema_version": "1.0.0",
        "campaign_id": campaign["campaign_id"],
        "status": "a2-sensitivity-complete",
        "render_count": len(records),
        "setting_count": len(_settings(campaign)),
        "elapsed_sec": total_elapsed,
        "mean_elapsed_sec_per_render": total_elapsed / max(1, len(records)),
        "wav_storage_bytes": storage,
        "mean_wav_bytes_per_render": storage / max(1, len(records)),
        "records": records,
        "setting_summaries": grouped,
        "local_effects": local_effects,
        "interpretation": "finite-difference diagnostics; no human-likeness or adoption conclusion",
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# A2 感度pilot",
        "",
        f"- campaign: `{result['campaign_id']}`",
        f"- 設定数: {result['setting_count']}",
        f"- 生成数: {result['render_count']}",
        f"- 総実行時間: {result['elapsed_sec']:.2f}秒",
        f"- 1音あたり平均: {result['mean_elapsed_sec_per_render']:.3f}秒",
        f"- WAV保存量: {result['wav_storage_bytes']} bytes",
        "",
        "この結果は生成器と測定器の局所感度であり、人声らしさの評価ではない。",
        "",
        "## 軸",
        "",
        "| 軸 | 状態 | 下側 | 中心 | 上側 |",
        "|---|---|---:|---:|---:|",
    ]
    for effect in result["local_effects"]:
        lines.append(
            f"| {effect['axis']} | {effect['status']} | {effect.get('lower', '-')} | {effect.get('center', '-')} | {effect.get('upper', '-')} |"
        )
    lines.extend(["", "詳細な指標別勾配、seed別測定、欠損状態は `sensitivity.json` に保存した。", ""])
    return "\n".join(lines)

