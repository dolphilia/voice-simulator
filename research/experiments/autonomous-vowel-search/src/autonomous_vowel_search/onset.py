from __future__ import annotations

import math
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

from comparison_eval.features import spectral_summary
from comparison_eval.signal import signal_integrity
from synthetic_vowel_baseline.synthesis import render_onset_secondary_candidates

from .generator_adapter import base_contract, write_render
from .io import read_json
from .paths import BASELINE_ROOT


ONSET_ADAPTER_VERSION = "1.1.0"


def render_gain_onset(gain_attack_ms: float, seed_offset: int) -> dict[str, Any]:
    spec, quality, correction = (deepcopy(item) for item in base_contract())
    onset = read_json(BASELINE_ROOT / "config/onset-secondary-experiment.json")
    onset["canonical_seed_offset"] = int(seed_offset)
    onset["gain_attack_ms"] = float(gain_attack_ms)
    candidate = render_onset_secondary_candidates(spec, quality, correction, onset)[1]
    candidate["condition"] = f"G{int(gain_attack_ms)}-seed-{seed_offset}"
    candidate["adapter_version"] = ONSET_ADAPTER_VERSION
    candidate["sample_rate"] = int(spec["sample_rate"])
    candidate["seed_offset"] = int(seed_offset)
    candidate["gain_attack_ms"] = float(gain_attack_ms)
    return candidate


def _rms_envelope(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    window = max(1, int(round(0.005 * sample_rate)))
    hop = max(1, int(round(0.001 * sample_rate)))
    starts = np.arange(0, max(1, audio.size - window + 1), hop)
    values = np.asarray([np.sqrt(np.mean(np.square(audio[start:start + window]))) for start in starts])
    times_ms = (starts + window / 2.0) * 1000.0 / sample_rate
    return times_ms, values


def _first_crossing(times: np.ndarray, values: np.ndarray, threshold: float) -> float | None:
    indices = np.flatnonzero(values >= threshold)
    return float(times[indices[0]]) if indices.size else None


def onset_diagnostics(audio: np.ndarray, sample_rate: int, stable_start_sec: float) -> dict[str, float | None]:
    stable_start = int(round(stable_start_sec * sample_rate))
    stable_end = audio.size - int(round(0.01 * sample_rate))
    stable = audio[stable_start:stable_end]
    leading = audio[:min(audio.size, int(round(0.15 * sample_rate)))]
    stable_rms = float(np.sqrt(np.mean(np.square(stable))))
    leading_rms = float(np.sqrt(np.mean(np.square(leading))))
    times, envelope = _rms_envelope(audio[:min(audio.size, int(round(0.15 * sample_rate)))], sample_rate)
    stable_envelope = float(np.median(_rms_envelope(stable, sample_rate)[1]))
    crossings = {level: _first_crossing(times, envelope, stable_envelope * level) for level in (0.1, 0.5, 0.9)}
    rise = crossings[0.9] - crossings[0.1] if crossings[0.1] is not None and crossings[0.9] is not None else None
    return {
        "rms_rise_10_ms": crossings[0.1],
        "rms_rise_50_ms": crossings[0.5],
        "rms_rise_90_ms": crossings[0.9],
        "rms_10_to_90_ms": rise,
        "leading_to_stable_rms_db": 20.0 * math.log10(max(leading_rms, 1e-12) / max(stable_rms, 1e-12)),
        "stable_rms_dbfs": 20.0 * math.log10(max(stable_rms, 1e-12)),
        "leading_spectral_centroid_hz": spectral_summary(leading, sample_rate)["spectral_centroid_hz"],
        "stable_spectral_centroid_hz": spectral_summary(stable, sample_rate)["spectral_centroid_hz"],
    }


def run_onset_sensitivity(output_dir: Path, config: dict[str, Any]) -> dict[str, Any]:
    records = []
    started = time.perf_counter()
    canonical = render_gain_onset(config["canonical_regression"]["gain_attack_ms"], config["canonical_regression"]["seed_offset"])
    canonical_path = output_dir / "audio/canonical-g40.wav"
    canonical_hash = write_render(canonical_path, canonical)
    if canonical_hash != config["canonical_regression"]["wav_sha256"]:
        raise ValueError("G40 canonical WAVを再現できません")
    for duration in config["axis"]["values"]:
        for seed in config["seed_offsets"]:
            candidate = render_gain_onset(float(duration), int(seed))
            path = output_dir / "audio" / f"gain-{int(duration)}ms--seed-{seed}.wav"
            digest = write_render(path, candidate)
            diagnostics = onset_diagnostics(candidate["audio"], candidate["sample_rate"], config["scope"]["stable_normalization_start_sec"])
            integrity = signal_integrity(candidate["audio"], candidate["sample_rate"])
            limits = config["hard_constraints"]
            failures = []
            if integrity["clipping_ratio"] > limits["maximum_clipping_ratio"]: failures.append("clipping")
            if integrity["peak_dbfs"] > limits["maximum_peak_dbfs"]: failures.append("peak")
            if abs(integrity["dc_offset"]) > limits["maximum_dc_offset"]: failures.append("dc")
            if max(abs(float(candidate["audio"][0])), abs(float(candidate["audio"][-1]))) > limits["maximum_endpoint_absolute"]: failures.append("endpoint")
            records.append({
                "gain_attack_ms": duration,
                "seed_offset": seed,
                "sha256": digest,
                "relative_audio_path": str(path.relative_to(output_dir)),
                "engineering_passed": not failures,
                "engineering_failures": failures,
                "integrity": integrity,
                "diagnostics": diagnostics,
            })

    # 定常部を揃えた比較であることを、同一 seed の attack=0 ms を基準に検査する。
    # v1.0.0 は設定にこの制約を持ちながら判定していなかったため、ここで明示的に
    # 診断値と工学ゲートの双方へ反映する。
    stable_rms_by_seed = {
        row["seed_offset"]: row["diagnostics"]["stable_rms_dbfs"]
        for row in records
        if float(row["gain_attack_ms"]) == 0.0
    }
    maximum_delta = float(config["hard_constraints"]["maximum_stable_rms_delta_db"])
    for row in records:
        delta = float(row["diagnostics"]["stable_rms_dbfs"] - stable_rms_by_seed[row["seed_offset"]])
        row["diagnostics"]["stable_rms_delta_db"] = delta
        if abs(delta) > maximum_delta:
            row["engineering_failures"].append("stable_rms_delta")
        row["engineering_passed"] = not row["engineering_failures"]
    summaries = {}
    for duration in config["axis"]["values"]:
        rows = [row for row in records if row["gain_attack_ms"] == duration]
        summaries[str(int(duration))] = {
            "engineering_pass_rate": sum(row["engineering_passed"] for row in rows) / len(rows),
            "diagnostics": {
                name: {
                    "median": float(np.median([row["diagnostics"][name] for row in rows if row["diagnostics"][name] is not None])),
                    "minimum": float(np.min([row["diagnostics"][name] for row in rows if row["diagnostics"][name] is not None])),
                    "maximum": float(np.max([row["diagnostics"][name] for row in rows if row["diagnostics"][name] is not None])),
                }
                for name in config["diagnostics"]
            },
        }
    return {
        "schema_version": "1.1.0",
        "campaign_id": config["campaign_id"],
        "adapter_version": ONSET_ADAPTER_VERSION,
        "canonical_g40_sha256": canonical_hash,
        "canonical_regression_passed": True,
        "render_count": len(records),
        "elapsed_sec": time.perf_counter() - started,
        "records": records,
        "summaries": summaries,
        "formal_aggregate_score": None,
        "perceptual_claim_allowed": False,
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# G40 onset 感度pilot",
        "",
        f"canonical G40 hash回帰: {'pass' if result['canonical_regression_passed'] else 'fail'}",
        "",
        "| attack ms | 工学通過率 | 10% ms | 50% ms | 90% ms | 10–90% ms | leading/stable dB | stable RMS差 dB |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for duration, summary in result["summaries"].items():
        d = summary["diagnostics"]
        lines.append(f"| {duration} | {summary['engineering_pass_rate']:.2f} | {d['rms_rise_10_ms']['median']:.2f} | {d['rms_rise_50_ms']['median']:.2f} | {d['rms_rise_90_ms']['median']:.2f} | {d['rms_10_to_90_ms']['median']:.2f} | {d['leading_to_stable_rms_db']['median']:.2f} | {d['stable_rms_delta_db']['median']:.4f} |")
    lines.extend(["", "測定値は実現した包絡の診断であり、自然さの自動得点ではない。既存試聴方向は別契約として保持する。", ""])
    return "\n".join(lines)
