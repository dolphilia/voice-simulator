from __future__ import annotations

import argparse
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from . import SCHEMA_VERSION
from .synthesis import (
    render_candidates,
    render_corrected_variation_candidates,
    render_f0_generalization_candidates,
    render_gain_attack_scaling_candidates,
    render_onset_secondary_candidates,
    render_two_mass_candidate,
    render_voice_quality_candidates,
    render_waveguide_candidate,
    render_vowel_generalization_candidates,
)
from .longitudinal import (
    aggregate_runs,
    hours_since_previous,
    parse_timestamp,
    run_session_path,
    study_config,
    summarize_run,
    validate_run_number,
)
from .generalization_evaluation import (
    summarize_f0_listening,
    summarize_gain_scaling_listening,
    summarize_vowel_listening,
)


def root() -> Path:
    return Path(__file__).resolve().parents[2]


ONSET_SOURCE = root().parent / "phonation-onset-nonstationarity/src"
if str(ONSET_SOURCE) not in sys.path:
    sys.path.insert(0, str(ONSET_SOURCE))

from phonation_onset.audio import integrity, sha256_file, write_audio, write_json
from phonation_onset.listening_wizard import (
    ListeningWizard,
    analyze_wizard_session,
    detect_player,
    prepare_candidate_wizard_session,
)
from phonation_onset.trajectories import extract_trajectory, summarize_trajectory


def config() -> dict[str, Any]:
    return json.loads((root() / "config/experiment.json").read_text(encoding="utf-8"))


def session_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or "/" in value:
        return candidate.resolve()
    return (root() / "results/listening" / value).resolve()


def command_prepare(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    candidate_dir = root() / "results/candidates"
    manifest: list[dict[str, Any]] = []
    by_condition: dict[str, dict[str, Any]] = {}
    gates = spec["gates"]
    for candidate in render_candidates(spec):
        audio = candidate.pop("audio")
        path = candidate_dir / f"{candidate['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        entry = {
            **candidate,
            "stimulus_id": candidate["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "gate_passed": not failures,
            "gate_failures": failures,
            "parameters": {key: spec[key] for key in ("sample_rate", "duration_sec", "edge_fade_ms", "target_dbfs", "f0_hz", "formants_hz", "bandwidths_hz")},
        }
        manifest.append(entry)
        by_condition[entry["condition"]] = entry
    for left_index, left in enumerate(manifest):
        for right in manifest[left_index + 1 :]:
            _, a = _read(left, root())
            _, b = _read(right, root())
            difference = float(np.sqrt(np.mean((a - b) ** 2)))
            if difference < float(gates["minimum_pair_rms_difference"]):
                print(f"候補が実質的に同一です: {left['condition']} / {right['condition']}", file=sys.stderr)
                return 3
    if any(not item["gate_passed"] for item in manifest):
        print(json.dumps({"gate_failures": [{"condition": item["condition"], "failures": item["gate_failures"]} for item in manifest if not item["gate_passed"]]}, ensure_ascii=False), file=sys.stderr)
        return 3
    write_json(candidate_dir / "manifest.json", {"schema_version": SCHEMA_VERSION, "stimuli": manifest})

    def side(condition: str) -> dict[str, Any]:
        item = by_condition[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    pairs = [
        {"pair_id": "parallel-source-effect", "hypothesis": "baseline-source", "left": side("B0-saw-parallel"), "right": side("B1-lf-parallel")},
        {"pair_id": "cascade-source-effect", "hypothesis": "baseline-source", "left": side("B2-saw-cascade"), "right": side("B3-lf-cascade")},
        {"pair_id": "saw-filter-effect", "hypothesis": "baseline-filter", "left": side("B0-saw-parallel"), "right": side("B2-saw-cascade")},
        {"pair_id": "lf-filter-effect", "hypothesis": "baseline-filter", "left": side("B1-lf-parallel"), "right": side("B3-lf-cascade")},
    ]
    try:
        result = prepare_candidate_wizard_session(
            pairs, session, int(spec["seed"]),
            ["parallel-source-effect", "lf-filter-effect"],
            provenance={
                "experiment": "synthetic-vowel-baseline",
                "candidate_manifest": "results/candidates/manifest.json",
                "candidate_manifest_sha256": sha256_file(candidate_dir / "manifest.json"),
                "experiment_config_sha256": sha256_file(root() / "config/experiment.json"),
                "evidence_contract_sha256": sha256_file(root() / "config/evidence-contract.md"),
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=3,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _read(item: dict[str, Any], base: Path) -> tuple[int, np.ndarray]:
    from phonation_onset.audio import read_audio
    return read_audio(base / item["relative_path"])


def command_listen(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    try:
        return ListeningWizard(session, detect_player(args.player)).run(check_only=bool(args.check_only))
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2


def command_prepare_physical(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    two_mass_path = root() / "config/two-mass-experiment.json"
    spec["two_mass"] = json.loads(two_mass_path.read_text(encoding="utf-8"))
    baseline = next(item for item in render_candidates(spec) if item["condition"] == "B2-saw-cascade")
    physical = render_two_mass_candidate(spec)
    output = root() / "results/physical-source-candidates"
    candidates: dict[str, dict[str, Any]] = {}
    for item in (baseline, physical):
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        if health["clipping_ratio"] > 0.0 or health["peak_dbfs"] > -1.0 or abs(health["dc_offset"]) > 0.01:
            print(f"signal gate failure: {item['condition']}", file=sys.stderr)
            return 3
        candidates[item["condition"]] = {
            **item, "stimulus_id": item["condition"], "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path), "integrity": health,
        }
    diagnostics = candidates["B4-two-mass-cascade"]["diagnostics"]
    if not 180.0 <= diagnostics["measured_f0_hz"] <= 260.0 or diagnostics["closed_ratio"] <= 0.01:
        print(f"two-mass oscillation gate failure: {diagnostics}", file=sys.stderr)
        return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "bounded physical-source comparison after baseline candidates failed human-voice gate",
        "stimuli": list(candidates.values()),
    })
    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}
    pair = {"pair_id": "saw-vs-two-mass-cascade", "hypothesis": "baseline-physical-source", "left": side("B2-saw-cascade"), "right": side("B4-two-mass-cascade")}
    try:
        result = prepare_candidate_wizard_session(
            [pair], session, int(spec["seed"]) + 1, [pair["pair_id"]],
            provenance={
                "experiment": "synthetic-vowel-baseline-physical-source",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "two_mass_config_sha256": sha256_file(two_mass_path),
                "contains_human_audio": False, "holdout_opened": False,
            },
            duplicate_minimum_separation=1,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_waveguide(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    waveguide_path = root() / "config/waveguide-experiment.json"
    waveguide = json.loads(waveguide_path.read_text(encoding="utf-8"))
    baselines = {
        item["condition"]: item
        for item in render_candidates(spec)
        if item["condition"] in {"B0-saw-parallel", "B2-saw-cascade"}
    }
    candidates_to_render = [
        baselines["B0-saw-parallel"],
        baselines["B2-saw-cascade"],
        render_waveguide_candidate(spec, waveguide),
    ]
    output = root() / "results/waveguide-tract-candidates"
    candidates: dict[str, dict[str, Any]] = {}
    gates = spec["gates"]
    for item in candidates_to_render:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "gate_passed": True,
        }
    for baseline_condition in ("B0-saw-parallel", "B2-saw-cascade"):
        _, baseline_audio = _read(candidates[baseline_condition], root())
        _, waveguide_audio = _read(candidates["B5-saw-waveguide"], root())
        difference = float(np.sqrt(np.mean((baseline_audio - waveguide_audio) ** 2)))
        if difference < float(gates["minimum_pair_rms_difference"]):
            print(f"候補が実質的に同一です: {baseline_condition} / B5-saw-waveguide", file=sys.stderr)
            return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "saw source fixed; compare tract topology after source comparison was perceptually inconclusive",
        "stimuli": list(candidates.values()),
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    pairs = [
        {
            "pair_id": "cascade-vs-waveguide",
            "hypothesis": "baseline-waveguide-tract",
            "left": side("B2-saw-cascade"),
            "right": side("B5-saw-waveguide"),
        },
        {
            "pair_id": "parallel-vs-waveguide",
            "hypothesis": "baseline-waveguide-tract",
            "left": side("B0-saw-parallel"),
            "right": side("B5-saw-waveguide"),
        },
    ]
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 2,
            ["cascade-vs-waveguide"],
            provenance={
                "experiment": "synthetic-vowel-baseline-waveguide-tract",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "waveguide_config_sha256": sha256_file(waveguide_path),
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=2,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_voice_quality(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    reference = (root() / quality["reference_measurement"]["relative_path"]).resolve()
    if not reference.is_file() or sha256_file(reference) != quality["reference_measurement"]["sha256"]:
        print(f"測定リファレンスが欠損または変更されています: {reference}", file=sys.stderr)
        return 3
    baseline = next(item for item in render_candidates(spec) if item["condition"] == "B2-saw-cascade")
    output = root() / "results/voice-quality-candidates"
    candidates: dict[str, dict[str, Any]] = {}
    gates = spec["gates"]
    for item in (baseline, *render_voice_quality_candidates(spec, quality)):
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        summary = summarize_trajectory(extract_trajectory(audio, int(spec["sample_rate"])), 0.2)
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "gate_passed": True,
            "acoustic_summary": {
                key: summary[key]["stable_median"]
                for key in ("f0_hz", "periodicity", "h1_h2_db", "hnr_db", "cpp_proxy", "spectral_centroid_hz", "spectral_flatness")
            },
        }
    ordered = [
        "B2-saw-cascade",
        "B6-tilted-saw-cascade",
        "B7-tilted-varied-saw-cascade",
        "B8-tilted-varied-aspirated-saw-cascade",
    ]
    for left, right in zip(ordered, ordered[1:]):
        _, a = _read(candidates[left], root())
        _, b = _read(candidates[right], root())
        if float(np.sqrt(np.mean((a - b) ** 2))) < float(gates["minimum_pair_rms_difference"]):
            print(f"候補が実質的に同一です: {left} / {right}", file=sys.stderr)
            return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "additive voice-quality ablation after source and tract topology candidates failed human-voice identity",
        "contains_human_audio": False,
        "reference_used_for_measurement_only": True,
        "stimuli": [candidates[name] for name in ordered],
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    pairs = [
        {"pair_id": "spectral-tilt-effect", "hypothesis": "baseline-voice-quality", "left": side(ordered[0]), "right": side(ordered[1])},
        {"pair_id": "microvariation-effect", "hypothesis": "baseline-voice-quality", "left": side(ordered[1]), "right": side(ordered[2])},
        {"pair_id": "aspiration-effect", "hypothesis": "baseline-voice-quality", "left": side(ordered[2]), "right": side(ordered[3])},
        {"pair_id": "total-voice-quality-effect", "hypothesis": "baseline-voice-quality", "left": side(ordered[0]), "right": side(ordered[3])},
    ]
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 3,
            ["total-voice-quality-effect"],
            provenance={
                "experiment": "synthetic-vowel-baseline-voice-quality",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "voice_quality_config_sha256": sha256_file(quality_path),
                "reference_sha256": sha256_file(reference),
                "reference_used_for_measurement_only": True,
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=4,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_voice_quality_validation(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    validation_path = root() / "config/voice-quality-validation.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    output = root() / "results/voice-quality-validation-candidates"
    gates = spec["gates"]
    anchor = render_voice_quality_candidates(spec, quality)[0]
    rendered: list[dict[str, Any]] = [anchor]
    variant_names: list[str] = []
    for offset in validation["seed_offsets"]:
        variant_quality = {**quality, "seed_offset": int(offset)}
        item = render_voice_quality_candidates(spec, variant_quality)[1]
        item["condition"] = f"B7-seed-{int(offset)}"
        item["diagnostics"] = {**item["diagnostics"], "seed_offset": int(offset)}
        rendered.append(item)
        variant_names.append(item["condition"])
    candidates: dict[str, dict[str, Any]] = {}
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        summary = summarize_trajectory(extract_trajectory(audio, int(spec["sample_rate"])), 0.2)
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "gate_passed": True,
            "acoustic_summary": {
                key: summary[key]["stable_median"]
                for key in ("f0_hz", "periodicity", "h1_h2_db", "hnr_db", "cpp_proxy", "spectral_centroid_hz", "spectral_flatness")
            },
        }
    for index, left in enumerate(variant_names):
        for right in variant_names[index + 1 :]:
            _, a = _read(candidates[left], root())
            _, b = _read(candidates[right], root())
            if float(np.sqrt(np.mean((a - b) ** 2))) < float(gates["minimum_pair_rms_difference"]):
                print(f"異なるseed候補が実質的に同一です: {left} / {right}", file=sys.stderr)
                return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "unseen-seed validation of the minimal passing B7 candidate family",
        "contains_human_audio": False,
        "stimuli": [candidates["B6-tilted-saw-cascade"], *[candidates[name] for name in variant_names]],
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    anchor_pair_id = "b6-vs-b7-seed-301"
    pairs = [{
        "pair_id": anchor_pair_id,
        "hypothesis": "baseline-voice-quality-validation",
        "left": side("B6-tilted-saw-cascade"),
        "right": side(variant_names[0]),
    }]
    for index, left in enumerate(variant_names):
        for right in variant_names[index + 1 :]:
            pairs.append({
                "pair_id": f"{left}-vs-{right}",
                "hypothesis": "baseline-voice-quality-validation",
                "left": side(left),
                "right": side(right),
            })
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 4,
            [anchor_pair_id],
            provenance={
                "experiment": "synthetic-vowel-baseline-voice-quality-validation",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "voice_quality_config_sha256": sha256_file(quality_path),
                "validation_config_sha256": sha256_file(validation_path),
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=4,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_voice_quality_correction(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    legacy = render_voice_quality_candidates(spec, quality)
    rendered = [legacy[0], legacy[1], *render_corrected_variation_candidates(spec, quality, correction)]
    output = root() / "results/voice-quality-correction-candidates"
    gates = spec["gates"]
    candidates: dict[str, dict[str, Any]] = {}
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        summary = summarize_trajectory(extract_trajectory(audio, int(spec["sample_rate"])), 0.2)
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "gate_passed": True,
            "acoustic_summary": {
                key: summary[key]["stable_median"]
                for key in ("f0_hz", "periodicity", "h1_h2_db", "hnr_db", "cpp_proxy", "spectral_centroid_hz", "spectral_flatness")
            },
        }
    frozen_manifest = json.loads((root() / "results/voice-quality-candidates/manifest.json").read_text(encoding="utf-8"))
    frozen_hashes = {item["condition"]: item["sha256"] for item in frozen_manifest["stimuli"]}
    for condition in ("B6-tilted-saw-cascade", "B7-tilted-varied-saw-cascade"):
        if candidates[condition]["sha256"] != frozen_hashes[condition]:
            print(f"凍結候補を再現できません: {condition}", file=sys.stderr)
            return 3
    ordered = [
        "B6-tilted-saw-cascade",
        "B7-tilted-varied-saw-cascade",
        "B9-corrected-subtle-variation",
        "B10-corrected-matched-variation",
    ]
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            _, a = _read(candidates[left], root())
            _, b = _read(candidates[right], root())
            if float(np.sqrt(np.mean((a - b) ** 2))) < float(gates["minimum_pair_rms_difference"]):
                print(f"候補が実質的に同一です: {left} / {right}", file=sys.stderr)
                return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "correct the legacy B7 control-scale bias and separate intended from observed F0 variation",
        "contains_human_audio": False,
        "legacy_frozen_hashes_verified": True,
        "stimuli": [candidates[name] for name in ordered],
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    control_shape_pair = "legacy-b7-vs-corrected-b10"
    pairs = [
        {"pair_id": "b6-vs-corrected-b9", "hypothesis": "baseline-voice-quality-correction", "left": side(ordered[0]), "right": side(ordered[2])},
        {"pair_id": "b6-vs-corrected-b10", "hypothesis": "baseline-voice-quality-correction", "left": side(ordered[0]), "right": side(ordered[3])},
        {"pair_id": "corrected-b9-vs-b10", "hypothesis": "baseline-voice-quality-correction", "left": side(ordered[2]), "right": side(ordered[3])},
        {"pair_id": control_shape_pair, "hypothesis": "baseline-voice-quality-correction", "left": side(ordered[1]), "right": side(ordered[3])},
    ]
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 5,
            [control_shape_pair],
            provenance={
                "experiment": "synthetic-vowel-baseline-voice-quality-correction",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "voice_quality_config_sha256": sha256_file(quality_path),
                "correction_config_sha256": sha256_file(correction_path),
                "legacy_response_sha256": "421ed7b45c13fbf27faf59abe058674644c0a6c310867ac479af7aa6ad52e363",
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=4,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_b9_seed_validation(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    validation_path = root() / "config/b9-seed-validation.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    output = root() / "results/b9-seed-validation-candidates"
    anchor = render_voice_quality_candidates(spec, quality)[0]
    rendered: list[dict[str, Any]] = [anchor]
    variant_names: list[str] = []
    for offset in validation["seed_offsets"]:
        item = render_corrected_variation_candidates(spec, quality, {**correction, "seed_offset": int(offset)})[0]
        item["condition"] = f"B9-seed-{int(offset)}"
        item["diagnostics"] = {**item["diagnostics"], "seed_offset": int(offset)}
        rendered.append(item)
        variant_names.append(item["condition"])
    gates = spec["gates"]
    candidates: dict[str, dict[str, Any]] = {}
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        summary = summarize_trajectory(extract_trajectory(audio, int(spec["sample_rate"])), 0.2)
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "gate_passed": True,
            "acoustic_summary": {
                key: summary[key]["stable_median"]
                for key in ("f0_hz", "periodicity", "h1_h2_db", "hnr_db", "cpp_proxy", "spectral_centroid_hz", "spectral_flatness")
            },
        }
    for index, left in enumerate(variant_names):
        for right in variant_names[index + 1 :]:
            _, a = _read(candidates[left], root())
            _, b = _read(candidates[right], root())
            if float(np.sqrt(np.mean((a - b) ** 2))) < float(gates["minimum_pair_rms_difference"]):
                print(f"異なるseed候補が実質的に同一です: {left} / {right}", file=sys.stderr)
                return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "unseen-seed validation of corrected minimal passing B9 family",
        "contains_human_audio": False,
        "stimuli": [candidates["B6-tilted-saw-cascade"], *[candidates[name] for name in variant_names]],
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    anchor_pair = "b6-vs-b9-seed-402"
    pairs = [{
        "pair_id": anchor_pair,
        "hypothesis": "baseline-b9-seed-validation",
        "left": side("B6-tilted-saw-cascade"),
        "right": side(variant_names[0]),
    }]
    for index, left in enumerate(variant_names):
        for right in variant_names[index + 1 :]:
            pairs.append({
                "pair_id": f"{left}-vs-{right}",
                "hypothesis": "baseline-b9-seed-validation",
                "left": side(left),
                "right": side(right),
            })
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 6,
            [anchor_pair],
            provenance={
                "experiment": "synthetic-vowel-baseline-b9-seed-validation",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "voice_quality_config_sha256": sha256_file(quality_path),
                "correction_config_sha256": sha256_file(correction_path),
                "validation_config_sha256": sha256_file(validation_path),
                "source_response_sha256": "43745b767ea98946b2adfa9e8932c829f0996e80e7a4c617628805d86fea5427",
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=4,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_onset_secondary(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    onset_path = root() / "config/onset-secondary-experiment.json"
    release_path = root() / "results/baseline-release-v1/manifest.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    onset = json.loads(onset_path.read_text(encoding="utf-8"))
    release = json.loads(release_path.read_text(encoding="utf-8"))
    output = root() / "results/onset-secondary-candidates"
    gates = spec["gates"]
    candidates: dict[str, dict[str, Any]] = {}
    stable_start = int(round(float(onset["stable_normalization_start_sec"]) * int(spec["sample_rate"])))
    stable_end = int(round(float(spec["duration_sec"]) * int(spec["sample_rate"]))) - int(round(float(spec["edge_fade_ms"]) * int(spec["sample_rate"]) / 1000.0))
    stable_levels: list[float] = []
    for item in render_onset_secondary_candidates(spec, quality, correction, onset):
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        stable_rms = float(np.sqrt(np.mean(audio[stable_start:stable_end] ** 2)))
        stable_levels.append(stable_rms)
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "stable_rms_dbfs": 20.0 * np.log10(max(stable_rms, 1e-12)),
            "gate_passed": True,
        }
    if max(stable_levels) / max(min(stable_levels), 1e-12) > 10.0 ** (0.1 / 20.0):
        print("stable RMS gate failure: onset candidates differ by more than 0.1 dB", file=sys.stderr)
        return 3
    if candidates["O0-b9-common-edge"]["sha256"] != release["audio_sha256"]:
        print("標準B9音声を再現できません", file=sys.stderr)
        return 3
    ordered = ["O0-b9-common-edge", "O1-b9-gain-attack", "O2-b9-gain-aspiration", "O3-b9-coupled-onset"]
    for left, right in zip(ordered, ordered[1:]):
        _, a = _read(candidates[left], root())
        _, b = _read(candidates[right], root())
        if float(np.sqrt(np.mean((a - b) ** 2))) < float(gates["minimum_pair_rms_difference"]):
            print(f"候補が実質的に同一です: {left} / {right}", file=sys.stderr)
            return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "secondary onset-naturalness ablation on the accepted B9 sustain baseline",
        "primary_axis": "more_natural_onset",
        "contains_human_audio": False,
        "canonical_b9_hash_verified": True,
        "stimuli": [candidates[name] for name in ordered],
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    total_pair = "o0-vs-o3-total-onset"
    pairs = [
        {"pair_id": "o0-vs-o1-gain", "hypothesis": "onset-secondary", "left": side(ordered[0]), "right": side(ordered[1])},
        {"pair_id": "o1-vs-o2-aspiration", "hypothesis": "onset-secondary", "left": side(ordered[1]), "right": side(ordered[2])},
        {"pair_id": "o2-vs-o3-f0-settlement", "hypothesis": "onset-secondary", "left": side(ordered[2]), "right": side(ordered[3])},
        {"pair_id": total_pair, "hypothesis": "onset-secondary", "left": side(ordered[0]), "right": side(ordered[3])},
    ]
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 7,
            [total_pair],
            provenance={
                "experiment": "synthetic-vowel-baseline-onset-secondary",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "baseline_release_sha256": sha256_file(release_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "voice_quality_config_sha256": sha256_file(quality_path),
                "correction_config_sha256": sha256_file(correction_path),
                "onset_config_sha256": sha256_file(onset_path),
                "b9_validation_response_sha256": "04913d3d242411afb9a1a10c0bc59bdf493bc5220ee45d4804d5742c4bda2d4a",
                "contains_human_audio": False,
                "holdout_opened": False,
                "scope": "secondary onset naturalness; does not reopen H1 human-likeness hypothesis",
            },
            duplicate_minimum_separation=4,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_onset_aspiration_validation(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    onset_path = root() / "config/onset-secondary-experiment.json"
    validation_path = root() / "config/onset-aspiration-validation.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    onset = json.loads(onset_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    first_render = render_onset_secondary_candidates(spec, quality, correction, {**onset, "seed_offset": int(validation["seed_offsets"][0])})
    control = first_render[1]
    rendered: list[dict[str, Any]] = [control]
    variant_names: list[str] = []
    for offset in validation["seed_offsets"]:
        item = render_onset_secondary_candidates(spec, quality, correction, {**onset, "seed_offset": int(offset)})[2]
        item["condition"] = f"O2-aspiration-seed-{int(offset)}"
        item["aspiration_seed_offset"] = int(offset)
        rendered.append(item)
        variant_names.append(item["condition"])
    output = root() / "results/onset-aspiration-validation-candidates"
    gates = spec["gates"]
    candidates: dict[str, dict[str, Any]] = {}
    stable_start = int(round(float(onset["stable_normalization_start_sec"]) * int(spec["sample_rate"])))
    stable_end = int(round(float(spec["duration_sec"]) * int(spec["sample_rate"]))) - int(round(float(spec["edge_fade_ms"]) * int(spec["sample_rate"]) / 1000.0))
    stable_levels: list[float] = []
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        stable_rms = float(np.sqrt(np.mean(audio[stable_start:stable_end] ** 2)))
        stable_levels.append(stable_rms)
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "stable_rms_dbfs": 20.0 * np.log10(max(stable_rms, 1e-12)),
            "gate_passed": True,
        }
    if max(stable_levels) / max(min(stable_levels), 1e-12) > 10.0 ** (0.1 / 20.0):
        print("stable RMS gate failure: aspiration validation candidates differ by more than 0.1 dB", file=sys.stderr)
        return 3
    for index, left in enumerate(variant_names):
        for right in variant_names[index + 1 :]:
            _, a = _read(candidates[left], root())
            _, b = _read(candidates[right], root())
            if float(np.sqrt(np.mean((a - b) ** 2))) < 1e-5:
                print(f"異なるaspiration seedが実質的に同一です: {left} / {right}", file=sys.stderr)
                return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "unseen-seed validation of O2 decaying aspiration onset improvement",
        "contains_human_audio": False,
        "stimuli": [candidates["O1-b9-gain-attack"], *[candidates[name] for name in variant_names]],
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    pairs = []
    for name in variant_names:
        pairs.append({
            "pair_id": f"o1-vs-{name}",
            "hypothesis": "onset-secondary",
            "left": side("O1-b9-gain-attack"),
            "right": side(name),
        })
    anchor_pair = pairs[0]["pair_id"]
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 8,
            [anchor_pair],
            provenance={
                "experiment": "synthetic-vowel-baseline-onset-aspiration-validation",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "voice_quality_config_sha256": sha256_file(quality_path),
                "correction_config_sha256": sha256_file(correction_path),
                "onset_config_sha256": sha256_file(onset_path),
                "validation_config_sha256": sha256_file(validation_path),
                "source_response_sha256": "a0790f74ead4d909fd290724aec22beb5ba66b6c782cc66ea6a2766a7709bddc",
                "contains_human_audio": False,
                "holdout_opened": False,
                "scope": "secondary onset naturalness; aspiration seed robustness only",
            },
            duplicate_minimum_separation=3,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_gain_attack_duration(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    onset_path = root() / "config/onset-secondary-experiment.json"
    duration_path = root() / "config/gain-attack-duration-experiment.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    onset = json.loads(onset_path.read_text(encoding="utf-8"))
    duration = json.loads(duration_path.read_text(encoding="utf-8"))
    canonical_render = render_onset_secondary_candidates(spec, quality, correction, onset)
    rendered: list[dict[str, Any]] = [canonical_render[0]]
    attack_names: list[str] = []
    for milliseconds in duration["durations_ms"]:
        item = render_onset_secondary_candidates(spec, quality, correction, {**onset, "gain_attack_ms": float(milliseconds)})[1]
        name = f"G{int(milliseconds)}-b9-gain-attack"
        item["condition"] = name
        item["gain_attack_ms"] = float(milliseconds)
        rendered.append(item)
        attack_names.append(name)
    output = root() / "results/gain-attack-duration-candidates"
    gates = spec["gates"]
    candidates: dict[str, dict[str, Any]] = {}
    stable_start = int(round(float(onset["stable_normalization_start_sec"]) * int(spec["sample_rate"])))
    stable_end = int(round(float(spec["duration_sec"]) * int(spec["sample_rate"]))) - int(round(float(spec["edge_fade_ms"]) * int(spec["sample_rate"]) / 1000.0))
    stable_levels: list[float] = []
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(spec["sample_rate"]), audio)
        health = integrity(audio, int(spec["sample_rate"]))
        stable_rms = float(np.sqrt(np.mean(audio[stable_start:stable_end] ** 2)))
        stable_levels.append(stable_rms)
        failures = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        if failures:
            print(f"signal gate failure: {item['condition']}: {', '.join(failures)}", file=sys.stderr)
            return 3
        candidates[item["condition"]] = {
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "stable_rms_dbfs": 20.0 * np.log10(max(stable_rms, 1e-12)),
            "gate_passed": True,
        }
    if max(stable_levels) / max(min(stable_levels), 1e-12) > 10.0 ** (0.1 / 20.0):
        print("stable RMS gate failure: gain attack candidates differ by more than 0.1 dB", file=sys.stderr)
        return 3
    original_manifest = json.loads((root() / "results/onset-secondary-candidates/manifest.json").read_text(encoding="utf-8"))
    original_hashes = {item["condition"]: item["sha256"] for item in original_manifest["stimuli"]}
    if candidates["O0-b9-common-edge"]["sha256"] != original_hashes["O0-b9-common-edge"] or candidates["G60-b9-gain-attack"]["sha256"] != original_hashes["O1-b9-gain-attack"]:
        print("凍結O0またはO1を再現できません", file=sys.stderr)
        return 3
    for left, right in zip(attack_names, attack_names[1:]):
        _, a = _read(candidates[left], root())
        _, b = _read(candidates[right], root())
        if float(np.sqrt(np.mean((a - b) ** 2))) < float(gates["minimum_pair_rms_difference"]):
            print(f"持続時間候補が実質的に同一です: {left} / {right}", file=sys.stderr)
            return 3
    manifest_path = output / "manifest.json"
    write_json(manifest_path, {
        "schema_version": SCHEMA_VERSION,
        "purpose": "gain attack duration sensitivity after aspiration failed strict seed validation",
        "contains_human_audio": False,
        "frozen_o0_o1_hashes_verified": True,
        "stimuli": [candidates["O0-b9-common-edge"], *[candidates[name] for name in attack_names]],
    })

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    primary_pair = "o0-vs-g60"
    pairs = [
        {"pair_id": primary_pair, "hypothesis": "onset-secondary", "left": side("O0-b9-common-edge"), "right": side("G60-b9-gain-attack")},
        {"pair_id": "o0-vs-g40", "hypothesis": "onset-secondary", "left": side("O0-b9-common-edge"), "right": side("G40-b9-gain-attack")},
        {"pair_id": "g40-vs-g60", "hypothesis": "onset-secondary", "left": side("G40-b9-gain-attack"), "right": side("G60-b9-gain-attack")},
        {"pair_id": "g60-vs-g80", "hypothesis": "onset-secondary", "left": side("G60-b9-gain-attack"), "right": side("G80-b9-gain-attack")},
    ]
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 9,
            [primary_pair],
            provenance={
                "experiment": "synthetic-vowel-baseline-gain-attack-duration",
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "base_config_sha256": sha256_file(root() / "config/experiment.json"),
                "voice_quality_config_sha256": sha256_file(quality_path),
                "correction_config_sha256": sha256_file(correction_path),
                "onset_config_sha256": sha256_file(onset_path),
                "duration_config_sha256": sha256_file(duration_path),
                "source_response_sha256": "9d377111f22909aa17da4d45e410e60b036cd8d17fca01d8c885427141df99d5",
                "contains_human_audio": False,
                "holdout_opened": False,
                "scope": "secondary onset naturalness; deterministic gain duration sensitivity",
            },
            duplicate_minimum_separation=4,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_prepare_g40_final(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    spec = config()
    source_manifest_path = root() / "results/gain-attack-duration-candidates/manifest.json"
    confirmation_path = root() / "config/g40-final-confirmation.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    candidates = {item["condition"]: item for item in source_manifest["stimuli"]}
    required = {"O0-b9-common-edge", "G40-b9-gain-attack", "G80-b9-gain-attack"}
    if not required <= set(candidates):
        print("最終確認に必要な凍結候補が欠損しています", file=sys.stderr)
        return 3
    for name in required:
        item = candidates[name]
        path = root() / item["relative_path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            print(f"凍結候補が変更または欠損しています: {name}", file=sys.stderr)
            return 3

    def side(condition: str) -> dict[str, Any]:
        item = candidates[condition]
        return {"path": root() / item["relative_path"], "condition": condition, "stimulus_id": condition}

    primary_pair = "o0-vs-g40-final"
    pairs = [
        {"pair_id": primary_pair, "hypothesis": "onset-secondary", "left": side("O0-b9-common-edge"), "right": side("G40-b9-gain-attack")},
        {"pair_id": "g40-vs-g80-final", "hypothesis": "onset-secondary", "left": side("G40-b9-gain-attack"), "right": side("G80-b9-gain-attack")},
    ]
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["seed"]) + 10,
            [primary_pair],
            provenance={
                "experiment": "synthetic-vowel-baseline-g40-final-confirmation",
                "source_manifest_sha256": sha256_file(source_manifest_path),
                "confirmation_config_sha256": sha256_file(confirmation_path),
                "source_response_sha256": "26d447998d505e6999e18c111f1210e65f7937bfe61ecd1b7f4d7c2196c8ac08",
                "contains_human_audio": False,
                "holdout_opened": False,
                "amendment": "candidate-side identity is decisive after control-side O0 identity varied in the prior duplicate",
            },
            duplicate_minimum_separation=2,
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_analyze(args: argparse.Namespace) -> int:
    session = session_path(args.session)
    try:
        result = analyze_wizard_session(session)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    write_json(session / "analysis.json", result)
    print(f"listening wizard responses valid -> {session / 'analysis.json'}")
    return 0


def _longitudinal_session(run: int) -> tuple[dict[str, Any], Path]:
    spec = study_config(root())
    validate_run_number(run, int(spec["planned_runs"]))
    return spec, run_session_path(root(), spec, run)


def command_prepare_longitudinal(args: argparse.Namespace) -> int:
    try:
        spec, session = _longitudinal_session(int(args.run))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    stimuli: dict[str, dict[str, Any]] = {}
    for condition, item in spec["stimuli"].items():
        path = root() / item["relative_path"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            print(f"凍結音源が変更または欠損しています: {condition}", file=sys.stderr)
            return 3
        stimuli[condition] = {
            "path": path, "condition": condition, "stimulus_id": condition,
        }
    pairs = [{
        "pair_id": pair["pair_id"],
        "hypothesis": pair["hypothesis"],
        "left": stimuli[pair["control"]],
        "right": stimuli[pair["target"]],
    } for pair in spec["pairs"]]
    run = int(args.run)
    config_path = root() / "config/single-listener-longitudinal.json"
    try:
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(spec["study_seed"]) + run,
            [pair["pair_id"] for pair in spec["pairs"]],
            provenance={
                "experiment": spec["study_id"],
                "design": spec["design"],
                "listener_count": 1,
                "run": run,
                "study_config_sha256": sha256_file(config_path),
                "contains_human_audio": False,
                "holdout_opened": False,
                "inference_scope": "single-listener within-person stability only",
            },
            duplicate_minimum_separation=int(spec["duplicate_minimum_separation"]),
        )
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"準備完了: run-{run:02d}。条件名を見ず、listen-longitudinalで試聴してください。")
    return 0


def command_listen_longitudinal(args: argparse.Namespace) -> int:
    run = int(args.run)
    try:
        spec, session = _longitudinal_session(run)
        if run > 1:
            previous = run_session_path(root(), spec, run - 1) / "responses.json"
            if not previous.is_file():
                raise ValueError(f"先にrun-{run - 1:02d}を完了してください")
            completed_at = json.loads(previous.read_text(encoding="utf-8"))["completed_at"]
            elapsed = hours_since_previous(completed_at, datetime.now(timezone.utc))
            required = float(spec["minimum_interval_hours"])
            if elapsed < required:
                remaining = required - elapsed
                raise ValueError(
                    f"前回から{elapsed:.1f}時間です。記憶の影響を減らすため、あと{remaining:.1f}時間あけてください"
                )
        return ListeningWizard(session, detect_player(args.player)).run(check_only=bool(args.check_only))
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2


def command_analyze_longitudinal(_: argparse.Namespace) -> int:
    try:
        spec = study_config(root())
        summaries: list[dict[str, Any]] = []
        for run in range(1, int(spec["planned_runs"]) + 1):
            session = run_session_path(root(), spec, run)
            completion_path = session / "completion.json"
            if not completion_path.is_file():
                continue
            completion = json.loads(completion_path.read_text(encoding="utf-8"))
            if not completion.get("complete"):
                continue
            analysis = analyze_wizard_session(session)
            write_json(session / "analysis.json", analysis)
            private = json.loads((session / "private-session-key.json").read_text(encoding="utf-8"))
            responses = json.loads((session / "responses.json").read_text(encoding="utf-8"))
            summaries.append(summarize_run(
                run, spec, private, responses, float(analysis["duplicate_consistency_rate"]),
            ))
        aggregate = aggregate_runs(spec, summaries)
        output = root() / "results/generalization" / spec["study_id"] / "aggregate.json"
        write_json(output, aggregate)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "completed_runs": aggregate["completed_runs"],
        "planned_runs": aggregate["planned_runs"],
        "advance_gate_passed": aggregate["advance_gate_passed"],
        "aggregate": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


def command_prepare_f0_preflight(_: argparse.Namespace) -> int:
    output = root() / "results/f0-generalization-candidates"
    if output.exists():
        print(f"出力先がすでに存在します。既存候補は上書きしません: {output}", file=sys.stderr)
        return 2
    base = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    onset_path = root() / "config/onset-secondary-experiment.json"
    f0_path = root() / "config/f0-generalization.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    onset = json.loads(onset_path.read_text(encoding="utf-8"))
    f0_spec = json.loads(f0_path.read_text(encoding="utf-8"))
    rendered = render_f0_generalization_candidates(
        base, quality, correction, onset, [float(value) for value in f0_spec["f0_values_hz"]],
    )
    output.mkdir(parents=True)
    candidates: list[dict[str, Any]] = []
    gates = base["gates"]
    stable_start = int(round(float(onset["stable_normalization_start_sec"]) * int(base["sample_rate"])))
    stable_end = int(round(float(base["duration_sec"]) * int(base["sample_rate"]))) - int(round(float(base["edge_fade_ms"]) * int(base["sample_rate"]) / 1000.0))
    stable_by_f0: dict[float, list[float]] = {}
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(base["sample_rate"]), audio)
        health = integrity(audio, int(base["sample_rate"]))
        failures: list[str] = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        stable_rms = float(np.sqrt(np.mean(audio[stable_start:stable_end] ** 2)))
        stable_by_f0.setdefault(float(item["f0_hz"]), []).append(stable_rms)
        diagnostics = item.get("diagnostics")
        if diagnostics:
            mean_error = abs(float(diagnostics["rendered_f0_mean_hz"]) / float(item["f0_hz"]) - 1.0)
            std_error = abs(float(diagnostics["rendered_f0_std_fraction"]) - float(correction["conditions"][0]["f0_std_fraction"]))
            if mean_error > float(f0_spec["signal_gates"]["maximum_f0_mean_relative_error"]): failures.append("f0-mean")
            if std_error > float(f0_spec["signal_gates"]["maximum_f0_std_fraction_error"]): failures.append("f0-variation")
        candidates.append({
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "stable_rms_dbfs": 20.0 * np.log10(max(stable_rms, 1e-12)),
            "gate_passed": not failures,
            "gate_failures": failures,
        })
    maximum_delta = float(f0_spec["signal_gates"]["maximum_stable_rms_delta_db"])
    for f0_hz, levels in stable_by_f0.items():
        delta_db = 20.0 * np.log10(max(levels) / max(min(levels), 1e-12))
        if delta_db > maximum_delta:
            for item in candidates:
                if float(item["f0_hz"]) == f0_hz:
                    item["gate_passed"] = False
                    item["gate_failures"].append("stable-rms-match")
    frozen = f0_spec["frozen_220_hashes"]
    hashes = {item["condition"]: item["sha256"] for item in candidates}
    frozen_verified = all(hashes.get(condition) == digest for condition, digest in frozen.items())
    if not frozen_verified or any(not item["gate_passed"] for item in candidates):
        print(json.dumps({"frozen_220_verified": frozen_verified, "failures": [item for item in candidates if not item["gate_passed"]]}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "purpose": f0_spec["purpose"],
        "stage": f0_spec["stage"],
        "promotion_blocked_until_longitudinal_gate": True,
        "frozen_220_hashes_verified": True,
        "contains_human_audio": False,
        "config_hashes": {
            "base": sha256_file(root() / "config/experiment.json"),
            "voice_quality": sha256_file(quality_path),
            "correction": sha256_file(correction_path),
            "onset": sha256_file(onset_path),
            "f0_generalization": sha256_file(f0_path),
        },
        "stimuli": candidates,
    }
    write_json(output / "manifest.json", manifest)
    print(json.dumps({
        "output": str(output), "candidate_count": len(candidates),
        "signal_gates_passed": True, "frozen_220_hashes_verified": True,
        "perceptual_status": "not-yet-evaluated",
    }, ensure_ascii=False, indent=2))
    return 0


def command_prepare_vowel_preflight(_: argparse.Namespace) -> int:
    output = root() / "results/vowel-generalization-candidates"
    if output.exists():
        print(f"出力先がすでに存在します。既存候補は上書きしません: {output}", file=sys.stderr)
        return 2
    base = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    onset_path = root() / "config/onset-secondary-experiment.json"
    vowel_path = root() / "config/vowel-generalization.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    onset = json.loads(onset_path.read_text(encoding="utf-8"))
    vowel_spec = json.loads(vowel_path.read_text(encoding="utf-8"))
    base["f0_hz"] = float(vowel_spec["f0_hz"])
    rendered = render_vowel_generalization_candidates(
        base, quality, correction, onset, vowel_spec["profiles"],
    )
    output.mkdir(parents=True)
    gates = base["gates"]
    stable_start = int(round(float(onset["stable_normalization_start_sec"]) * int(base["sample_rate"])))
    stable_end = int(round(float(base["duration_sec"]) * int(base["sample_rate"]))) - int(round(float(base["edge_fade_ms"]) * int(base["sample_rate"]) / 1000.0))
    candidates: list[dict[str, Any]] = []
    sustain_audio: dict[str, np.ndarray] = {}
    stable_by_vowel: dict[str, list[float]] = {}
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(base["sample_rate"]), audio)
        health = integrity(audio, int(base["sample_rate"]))
        failures: list[str] = []
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        spacing = min(np.diff(np.asarray(item["formants_hz"], dtype=float)))
        if spacing < float(vowel_spec["signal_gates"]["minimum_formant_spacing_hz"]): failures.append("formant-spacing")
        stable_rms = float(np.sqrt(np.mean(audio[stable_start:stable_end] ** 2)))
        stable_by_vowel.setdefault(item["vowel"], []).append(stable_rms)
        if item["condition"].endswith("B9-sustain"):
            sustain_audio[item["vowel"]] = audio
        candidates.append({
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "stable_rms_dbfs": 20.0 * np.log10(max(stable_rms, 1e-12)),
            "gate_passed": not failures,
            "gate_failures": failures,
        })
    rms_limit = float(vowel_spec["signal_gates"]["maximum_stable_rms_delta_db"])
    for vowel, levels in stable_by_vowel.items():
        delta_db = 20.0 * np.log10(max(levels) / max(min(levels), 1e-12))
        if delta_db > rms_limit:
            for item in candidates:
                if item["vowel"] == vowel:
                    item["gate_passed"] = False
                    item["gate_failures"].append("stable-rms-match")
    distinct_limit = float(vowel_spec["signal_gates"]["minimum_between_vowel_rms_difference"])
    vowel_names = list(sustain_audio)
    minimum_difference = float("inf")
    for index, left in enumerate(vowel_names):
        for right in vowel_names[index + 1:]:
            difference = float(np.sqrt(np.mean((sustain_audio[left] - sustain_audio[right]) ** 2)))
            minimum_difference = min(minimum_difference, difference)
    distinct = minimum_difference >= distinct_limit
    hashes = {item["condition"]: item["sha256"] for item in candidates}
    frozen_verified = all(hashes.get(condition) == digest for condition, digest in vowel_spec["frozen_a220_hashes"].items())
    if not frozen_verified or not distinct or any(not item["gate_passed"] for item in candidates):
        print(json.dumps({"frozen_a220_verified": frozen_verified, "between_vowel_distinct": distinct, "failures": [item for item in candidates if not item["gate_passed"]]}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "purpose": vowel_spec["purpose"],
        "stage": vowel_spec["stage"],
        "promotion_blocked_until_prior_gates": True,
        "frozen_a220_hashes_verified": True,
        "between_vowel_minimum_rms_difference": minimum_difference,
        "contains_human_audio": False,
        "config_hashes": {
            "base": sha256_file(root() / "config/experiment.json"),
            "voice_quality": sha256_file(quality_path),
            "correction": sha256_file(correction_path),
            "onset": sha256_file(onset_path),
            "vowel_generalization": sha256_file(vowel_path),
        },
        "stimuli": candidates,
    }
    write_json(output / "manifest.json", manifest)
    print(json.dumps({
        "output": str(output), "candidate_count": len(candidates),
        "signal_gates_passed": True, "frozen_a220_hashes_verified": True,
        "perceptual_status": "not-yet-evaluated",
    }, ensure_ascii=False, indent=2))
    return 0


def command_prepare_gain_scaling_preflight(_: argparse.Namespace) -> int:
    output = root() / "results/gain-attack-scaling-candidates"
    if output.exists():
        print(f"出力先がすでに存在します。既存候補は上書きしません: {output}", file=sys.stderr)
        return 2
    base = config()
    quality_path = root() / "config/voice-quality-experiment.json"
    correction_path = root() / "config/voice-quality-correction.json"
    onset_path = root() / "config/onset-secondary-experiment.json"
    scaling_path = root() / "config/gain-attack-scaling.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    correction = json.loads(correction_path.read_text(encoding="utf-8"))
    onset = json.loads(onset_path.read_text(encoding="utf-8"))
    scaling = json.loads(scaling_path.read_text(encoding="utf-8"))
    rendered = render_gain_attack_scaling_candidates(
        base, quality, correction, onset,
        [float(value) for value in scaling["f0_values_hz"]],
        float(scaling["fixed_duration_ms"]),
        float(scaling["cycle_reference"]["cycles"]),
    )
    output.mkdir(parents=True)
    stable_start = int(round(float(onset["stable_normalization_start_sec"]) * int(base["sample_rate"])))
    stable_end = int(round(float(base["duration_sec"]) * int(base["sample_rate"]))) - int(round(float(base["edge_fade_ms"]) * int(base["sample_rate"]) / 1000.0))
    candidates: list[dict[str, Any]] = []
    audio_by_f0: dict[float, list[np.ndarray]] = {}
    stable_by_f0: dict[float, list[float]] = {}
    for item in rendered:
        audio = item.pop("audio")
        path = output / f"{item['condition']}.wav"
        write_audio(path, int(base["sample_rate"]), audio)
        health = integrity(audio, int(base["sample_rate"]))
        failures: list[str] = []
        gates = base["gates"]
        if health["clipping_ratio"] > float(gates["maximum_clipping_ratio"]): failures.append("clipping")
        if health["peak_dbfs"] > float(gates["maximum_peak_dbfs"]): failures.append("peak")
        if abs(health["dc_offset"]) > float(gates["maximum_dc_offset"]): failures.append("dc")
        if max(abs(float(audio[0])), abs(float(audio[-1]))) > float(gates["maximum_endpoint_absolute"]): failures.append("endpoint")
        stable_rms = float(np.sqrt(np.mean(audio[stable_start:stable_end] ** 2)))
        audio_by_f0.setdefault(float(item["f0_hz"]), []).append(audio)
        stable_by_f0.setdefault(float(item["f0_hz"]), []).append(stable_rms)
        candidates.append({
            **item,
            "stimulus_id": item["condition"],
            "relative_path": str(path.relative_to(root())),
            "sha256": sha256_file(path),
            "integrity": health,
            "stable_rms_dbfs": 20.0 * np.log10(max(stable_rms, 1e-12)),
            "gate_passed": not failures,
            "gate_failures": failures,
        })
    pair_differences: dict[str, float] = {}
    for f0_hz, audio_pair in audio_by_f0.items():
        difference = float(np.sqrt(np.mean((audio_pair[0] - audio_pair[1]) ** 2)))
        pair_differences[str(int(round(f0_hz)))] = difference
        stable_delta = 20.0 * np.log10(max(stable_by_f0[f0_hz]) / max(min(stable_by_f0[f0_hz]), 1e-12))
        expected_identical = f0_hz == float(scaling["cycle_reference"]["f0_hz"])
        invalid_difference = difference != 0.0 if expected_identical else difference < float(scaling["signal_gates"]["minimum_nonreference_pair_rms_difference"])
        if stable_delta > float(scaling["signal_gates"]["maximum_stable_rms_delta_db"]) or invalid_difference:
            for item in candidates:
                if float(item["f0_hz"]) == f0_hz:
                    item["gate_passed"] = False
                    item["gate_failures"].append("scaling-pair")
    fixed_hashes = {
        item["condition"]: item["sha256"] for item in candidates if item["gain_attack_rule"] == "fixed"
    }
    f0_manifest = json.loads((root() / "results/f0-generalization-candidates/manifest.json").read_text(encoding="utf-8"))
    expected_fixed = {
        item["condition"].replace("F", "A", 1).replace("-G40-onset", "-fixed-gain-attack"): item["sha256"]
        for item in f0_manifest["stimuli"] if item["condition"].endswith("G40-onset")
    }
    fixed_verified = fixed_hashes == expected_fixed
    if not fixed_verified or any(not item["gate_passed"] for item in candidates):
        print(json.dumps({"fixed_hashes_verified": fixed_verified, "failures": [item for item in candidates if not item["gate_passed"]]}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    write_json(output / "manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "purpose": scaling["purpose"],
        "stage": scaling["stage"],
        "promotion_blocked_until_prior_gates": True,
        "fixed_40ms_hashes_verified": True,
        "reference_pair_identical": pair_differences["220"] == 0.0,
        "pair_rms_differences": pair_differences,
        "contains_human_audio": False,
        "config_hashes": {
            "base": sha256_file(root() / "config/experiment.json"),
            "voice_quality": sha256_file(quality_path),
            "correction": sha256_file(correction_path),
            "onset": sha256_file(onset_path),
            "gain_attack_scaling": sha256_file(scaling_path),
        },
        "stimuli": candidates,
    })
    print(json.dumps({
        "output": str(output), "candidate_count": len(candidates),
        "signal_gates_passed": True, "fixed_40ms_hashes_verified": True,
        "reference_pair_identical": True, "perceptual_status": "not-yet-evaluated",
    }, ensure_ascii=False, indent=2))
    return 0


def command_generalization_status(_: argparse.Namespace) -> int:
    longitudinal_spec = study_config(root())
    aggregate_path = root() / "results/generalization" / longitudinal_spec["study_id"] / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8")) if aggregate_path.is_file() else {
        "completed_runs": 0, "planned_runs": int(longitudinal_spec["planned_runs"]),
        "advance_gate_passed": False,
    }
    runs: list[dict[str, Any]] = []
    next_eligible_at: str | None = None
    for run in range(1, int(longitudinal_spec["planned_runs"]) + 1):
        session = run_session_path(root(), longitudinal_spec, run)
        completion_path = session / "completion.json"
        complete = False
        if completion_path.is_file():
            complete = bool(json.loads(completion_path.read_text(encoding="utf-8")).get("complete"))
        runs.append({
            "run": run,
            "prepared": (session / "lock.json").is_file(),
            "complete": complete,
        })
        if run > 1 and not complete and next_eligible_at is None:
            previous_responses = run_session_path(root(), longitudinal_spec, run - 1) / "responses.json"
            if previous_responses.is_file():
                previous_completed = json.loads(previous_responses.read_text(encoding="utf-8"))["completed_at"]
                eligible = parse_timestamp(previous_completed) + timedelta(hours=float(longitudinal_spec["minimum_interval_hours"]))
                next_eligible_at = eligible.astimezone(ZoneInfo("Asia/Tokyo")).isoformat()

    def preflight(relative: str) -> dict[str, Any]:
        path = root() / relative
        if not path.is_file():
            return {"prepared": False, "signal_qualified": False}
        manifest = json.loads(path.read_text(encoding="utf-8"))
        stimuli = manifest.get("stimuli", [])
        return {
            "prepared": True,
            "candidate_count": len(stimuli),
            "signal_qualified": bool(stimuli) and all(item.get("gate_passed") for item in stimuli),
            "stage": manifest.get("stage"),
        }

    f0_listening_spec = json.loads((root() / "config/f0-listening.json").read_text(encoding="utf-8"))
    f0_session = root() / "results/generalization" / f0_listening_spec["study_id"]
    vowel_listening_spec = json.loads((root() / "config/vowel-listening.json").read_text(encoding="utf-8"))
    vowel_session = root() / "results/generalization" / vowel_listening_spec["study_id"]
    gain_listening_spec = json.loads((root() / "config/gain-attack-scaling-listening.json").read_text(encoding="utf-8"))
    gain_session = root() / "results/generalization" / gain_listening_spec["study_id"]

    payload = {
        "longitudinal": {
            "completed_runs": aggregate.get("completed_runs", 0),
            "planned_runs": aggregate.get("planned_runs", int(longitudinal_spec["planned_runs"])),
            "advance_gate_passed": bool(aggregate.get("advance_gate_passed")),
            "next_eligible_at": next_eligible_at,
            "runs": runs,
        },
        "preflight": {
            "f0": preflight("results/f0-generalization-candidates/manifest.json"),
            "vowels": preflight("results/vowel-generalization-candidates/manifest.json"),
            "gain_attack_scaling": preflight("results/gain-attack-scaling-candidates/manifest.json"),
        },
        "listening_stages": {
            "f0": {
                "prepared": (f0_session / "lock.json").is_file(),
                "authorized": _longitudinal_gate_passed(),
                "complete": (f0_session / "completion.json").is_file(),
                "passed": _f0_listener_gate_passed(),
            },
            "vowels": {
                "prepared": (vowel_session / "lock.json").is_file(),
                "authorized": _f0_listener_gate_passed(),
                "complete": (vowel_session / "completion.json").is_file(),
                "passed": bool(
                    json.loads((vowel_session / "analysis.json").read_text(encoding="utf-8")).get("all_tested_vowels_passed")
                ) if (vowel_session / "analysis.json").is_file() else False,
            },
            "gain_attack_scaling": {
                "prepared": (gain_session / "lock.json").is_file(),
                "authorized": _vowel_listener_gate_passed(),
                "complete": (gain_session / "completion.json").is_file(),
                "decision_valid": bool(
                    json.loads((gain_session / "analysis.json").read_text(encoding="utf-8")).get("decision_valid")
                ) if (gain_session / "analysis.json").is_file() else False,
            },
        },
        "promotion": {
            "listener_qualified": bool(aggregate.get("advance_gate_passed")),
            "release_allowed": False,
            "reason": "反復ゲートと各次元の知覚評価が必要です",
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _longitudinal_gate_passed() -> bool:
    spec = study_config(root())
    path = root() / "results/generalization" / spec["study_id"] / "aggregate.json"
    if not path.is_file():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")).get("advance_gate_passed"))


def command_prepare_f0_listening(_: argparse.Namespace) -> int:
    listening_path = root() / "config/f0-listening.json"
    listening = json.loads(listening_path.read_text(encoding="utf-8"))
    session = root() / "results/generalization" / listening["study_id"]
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    manifest_path = root() / "results/f0-generalization-candidates/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_condition = {item["condition"]: item for item in manifest["stimuli"]}

    def side(condition: str) -> dict[str, Any]:
        item = by_condition[condition]
        path = root() / item["relative_path"]
        if not item.get("gate_passed") or not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"信号合格済み候補が変更または欠損しています: {condition}")
        return {"path": path, "condition": condition, "stimulus_id": condition}

    try:
        pairs = [{
            "pair_id": pair["pair_id"],
            "hypothesis": "onset-secondary",
            "left": side(pair["sustain"]),
            "right": side(pair["onset"]),
        } for pair in listening["pairs"]]
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(listening["seed"]),
            [pair["pair_id"] for pair in listening["pairs"]],
            provenance={
                "experiment": listening["study_id"],
                "study_config_sha256": sha256_file(listening_path),
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "prerequisite": listening["prerequisite"],
                "listening_authorized": False,
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=int(listening["duplicate_minimum_separation"]),
        )
    except (KeyError, FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    (session / "PREREQUISITE.md").write_text(
        "# 試聴前提条件\n\n"
        "このセッションは準備済みですが、単一試聴者の別日反復ゲートを通るまで試聴しません。\n"
        "`listen-f0-generalization` が前提条件を自動確認します。\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "prepared": True, "listening_authorized": _longitudinal_gate_passed()}, ensure_ascii=False, indent=2))
    return 0


def command_listen_f0_generalization(args: argparse.Namespace) -> int:
    try:
        listening = json.loads((root() / "config/f0-listening.json").read_text(encoding="utf-8"))
        if not _longitudinal_gate_passed():
            raise ValueError("単一試聴者の別日反復ゲートが未完了または未合格のため、F0試聴はまだ開始できません")
        session = root() / "results/generalization" / listening["study_id"]
        return ListeningWizard(session, detect_player(args.player)).run(check_only=bool(args.check_only))
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2


def command_analyze_f0_generalization(_: argparse.Namespace) -> int:
    listening_path = root() / "config/f0-listening.json"
    listening = json.loads(listening_path.read_text(encoding="utf-8"))
    session = root() / "results/generalization" / listening["study_id"]
    try:
        analysis = analyze_wizard_session(session)
        private = json.loads((session / "private-session-key.json").read_text(encoding="utf-8"))
        responses = json.loads((session / "responses.json").read_text(encoding="utf-8"))
        result = summarize_f0_listening(
            listening, private, responses, float(analysis["duplicate_consistency_rate"]),
        )
        result["response_sha256"] = analysis["response_sha256"]
        write_json(session / "analysis.json", result)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "all_tested_pitches_passed": result["all_tested_pitches_passed"],
        "analysis": str(session / "analysis.json"),
    }, ensure_ascii=False, indent=2))
    return 0


def _f0_listener_gate_passed() -> bool:
    spec = json.loads((root() / "config/f0-listening.json").read_text(encoding="utf-8"))
    path = root() / "results/generalization" / spec["study_id"] / "analysis.json"
    if not path.is_file():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")).get("all_tested_pitches_passed"))


def command_prepare_vowel_listening(_: argparse.Namespace) -> int:
    listening_path = root() / "config/vowel-listening.json"
    listening = json.loads(listening_path.read_text(encoding="utf-8"))
    session = root() / "results/generalization" / listening["study_id"]
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    manifest_path = root() / "results/vowel-generalization-candidates/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_condition = {item["condition"]: item for item in manifest["stimuli"]}

    def side(condition: str) -> dict[str, Any]:
        item = by_condition[condition]
        path = root() / item["relative_path"]
        if not item.get("gate_passed") or not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"信号合格済み候補が変更または欠損しています: {condition}")
        return {"path": path, "condition": condition, "stimulus_id": condition}

    try:
        pairs = [{
            "pair_id": pair["pair_id"],
            "hypothesis": f"vowel-generalization-{pair['vowel']}",
            "left": side(pair["sustain"]),
            "right": side(pair["onset"]),
        } for pair in listening["pairs"]]
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(listening["seed"]),
            [pair["pair_id"] for pair in listening["pairs"]],
            provenance={
                "experiment": listening["study_id"],
                "study_config_sha256": sha256_file(listening_path),
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "prerequisite": listening["prerequisite"],
                "listening_authorized": False,
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=int(listening["duplicate_minimum_separation"]),
        )
    except (KeyError, FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    (session / "PREREQUISITE.md").write_text(
        "# 試聴前提条件\n\n"
        "このセッションは準備済みですが、F0一般化試聴を通るまで試聴しません。\n"
        "`listen-vowel-generalization` が前提条件を自動確認します。\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "prepared": True, "listening_authorized": _f0_listener_gate_passed()}, ensure_ascii=False, indent=2))
    return 0


def command_listen_vowel_generalization(args: argparse.Namespace) -> int:
    try:
        listening = json.loads((root() / "config/vowel-listening.json").read_text(encoding="utf-8"))
        if not _f0_listener_gate_passed():
            raise ValueError("F0一般化試聴が未完了または未合格のため、5母音試聴はまだ開始できません")
        session = root() / "results/generalization" / listening["study_id"]
        return ListeningWizard(session, detect_player(args.player)).run(check_only=bool(args.check_only))
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2


def command_analyze_vowel_generalization(_: argparse.Namespace) -> int:
    listening = json.loads((root() / "config/vowel-listening.json").read_text(encoding="utf-8"))
    session = root() / "results/generalization" / listening["study_id"]
    try:
        analysis = analyze_wizard_session(session)
        private = json.loads((session / "private-session-key.json").read_text(encoding="utf-8"))
        responses = json.loads((session / "responses.json").read_text(encoding="utf-8"))
        result = summarize_vowel_listening(
            listening, private, responses, float(analysis["duplicate_consistency_rate"]),
        )
        result["response_sha256"] = analysis["response_sha256"]
        write_json(session / "analysis.json", result)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "all_tested_vowels_passed": result["all_tested_vowels_passed"],
        "analysis": str(session / "analysis.json"),
    }, ensure_ascii=False, indent=2))
    return 0


def _vowel_listener_gate_passed() -> bool:
    spec = json.loads((root() / "config/vowel-listening.json").read_text(encoding="utf-8"))
    path = root() / "results/generalization" / spec["study_id"] / "analysis.json"
    if not path.is_file():
        return False
    return bool(json.loads(path.read_text(encoding="utf-8")).get("all_tested_vowels_passed"))


def command_prepare_gain_scaling_listening(_: argparse.Namespace) -> int:
    listening_path = root() / "config/gain-attack-scaling-listening.json"
    listening = json.loads(listening_path.read_text(encoding="utf-8"))
    session = root() / "results/generalization" / listening["study_id"]
    if session.exists():
        print(f"出力先がすでに存在します。既存セッションは上書きしません: {session}", file=sys.stderr)
        return 2
    manifest_path = root() / "results/gain-attack-scaling-candidates/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_condition = {item["condition"]: item for item in manifest["stimuli"]}

    def side(condition: str) -> dict[str, Any]:
        item = by_condition[condition]
        path = root() / item["relative_path"]
        if not item.get("gate_passed") or not path.is_file() or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"信号合格済み候補が変更または欠損しています: {condition}")
        return {"path": path, "condition": condition, "stimulus_id": condition}

    try:
        pairs = [{
            "pair_id": pair["pair_id"],
            "hypothesis": "onset-secondary",
            "left": side(pair["fixed"]),
            "right": side(pair["cycle"]),
        } for pair in listening["pairs"]]
        result = prepare_candidate_wizard_session(
            pairs,
            session,
            int(listening["seed"]),
            [pair["pair_id"] for pair in listening["pairs"]],
            provenance={
                "experiment": listening["study_id"],
                "study_config_sha256": sha256_file(listening_path),
                "candidate_manifest_sha256": sha256_file(manifest_path),
                "prerequisite": listening["prerequisite"],
                "listening_authorized": False,
                "contains_human_audio": False,
                "holdout_opened": False,
            },
            duplicate_minimum_separation=int(listening["duplicate_minimum_separation"]),
        )
    except (KeyError, FileExistsError, FileNotFoundError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    (session / "PREREQUISITE.md").write_text(
        "# 試聴前提条件\n\n"
        "このセッションは準備済みですが、5母音一般化試聴を通るまで試聴しません。\n"
        "`listen-gain-scaling` が前提条件を自動確認します。\n",
        encoding="utf-8",
    )
    print(json.dumps({**result, "prepared": True, "listening_authorized": _vowel_listener_gate_passed()}, ensure_ascii=False, indent=2))
    return 0


def command_listen_gain_scaling(args: argparse.Namespace) -> int:
    try:
        listening = json.loads((root() / "config/gain-attack-scaling-listening.json").read_text(encoding="utf-8"))
        if not _vowel_listener_gate_passed():
            raise ValueError("5母音一般化試聴が未完了または未合格のため、gain attackスケーリング試聴はまだ開始できません")
        session = root() / "results/generalization" / listening["study_id"]
        return ListeningWizard(session, detect_player(args.player)).run(check_only=bool(args.check_only))
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2


def command_analyze_gain_scaling(_: argparse.Namespace) -> int:
    listening = json.loads((root() / "config/gain-attack-scaling-listening.json").read_text(encoding="utf-8"))
    session = root() / "results/generalization" / listening["study_id"]
    try:
        analysis = analyze_wizard_session(session)
        private = json.loads((session / "private-session-key.json").read_text(encoding="utf-8"))
        responses = json.loads((session / "responses.json").read_text(encoding="utf-8"))
        result = summarize_gain_scaling_listening(
            listening, private, responses, float(analysis["duplicate_consistency_rate"]),
        )
        result["response_sha256"] = analysis["response_sha256"]
        write_json(session / "analysis.json", result)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps({
        "decision_valid": result["decision_valid"],
        "selected_rule": result["selected_rule"],
        "analysis": str(session / "analysis.json"),
    }, ensure_ascii=False, indent=2))
    return 0


def command_test(_: argparse.Namespace) -> int:
    suite = unittest.defaultTestLoader.discover(str(root() / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="完全生成母音ベースライン実験")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare"); prepare.add_argument("--session", default="baseline-wizard-v2"); prepare.set_defaults(function=command_prepare)
    physical = commands.add_parser("prepare-physical-source"); physical.add_argument("--session", default="physical-source-wizard-v1"); physical.set_defaults(function=command_prepare_physical)
    waveguide = commands.add_parser("prepare-waveguide"); waveguide.add_argument("--session", default="waveguide-tract-wizard-v1"); waveguide.set_defaults(function=command_prepare_waveguide)
    voice_quality = commands.add_parser("prepare-voice-quality"); voice_quality.add_argument("--session", default="voice-quality-wizard-v1"); voice_quality.set_defaults(function=command_prepare_voice_quality)
    correction = commands.add_parser("prepare-voice-quality-correction"); correction.add_argument("--session", default="voice-quality-correction-wizard-v1"); correction.set_defaults(function=command_prepare_voice_quality_correction)
    b9_validation = commands.add_parser("prepare-b9-seed-validation"); b9_validation.add_argument("--session", default="b9-seed-validation-wizard-v1"); b9_validation.set_defaults(function=command_prepare_b9_seed_validation)
    onset_secondary = commands.add_parser("prepare-onset-secondary"); onset_secondary.add_argument("--session", default="onset-secondary-wizard-v1"); onset_secondary.set_defaults(function=command_prepare_onset_secondary)
    aspiration_validation = commands.add_parser("prepare-onset-aspiration-validation"); aspiration_validation.add_argument("--session", default="onset-aspiration-validation-wizard-v1"); aspiration_validation.set_defaults(function=command_prepare_onset_aspiration_validation)
    gain_duration = commands.add_parser("prepare-gain-attack-duration"); gain_duration.add_argument("--session", default="gain-attack-duration-wizard-v1"); gain_duration.set_defaults(function=command_prepare_gain_attack_duration)
    g40_final = commands.add_parser("prepare-g40-final"); g40_final.add_argument("--session", default="g40-final-wizard-v1"); g40_final.set_defaults(function=command_prepare_g40_final)
    listen = commands.add_parser("listen"); listen.add_argument("--session", default="baseline-wizard-v2"); listen.add_argument("--player"); listen.add_argument("--check-only", action="store_true"); listen.set_defaults(function=command_listen)
    analyze = commands.add_parser("analyze-listening"); analyze.add_argument("--session", default="baseline-wizard-v2"); analyze.set_defaults(function=command_analyze)
    longitudinal_prepare = commands.add_parser("prepare-longitudinal"); longitudinal_prepare.add_argument("--run", type=int, required=True); longitudinal_prepare.set_defaults(function=command_prepare_longitudinal)
    longitudinal_listen = commands.add_parser("listen-longitudinal"); longitudinal_listen.add_argument("--run", type=int, required=True); longitudinal_listen.add_argument("--player"); longitudinal_listen.add_argument("--check-only", action="store_true"); longitudinal_listen.set_defaults(function=command_listen_longitudinal)
    longitudinal_analyze = commands.add_parser("analyze-longitudinal"); longitudinal_analyze.set_defaults(function=command_analyze_longitudinal)
    f0_preflight = commands.add_parser("prepare-f0-preflight"); f0_preflight.set_defaults(function=command_prepare_f0_preflight)
    vowel_preflight = commands.add_parser("prepare-vowel-preflight"); vowel_preflight.set_defaults(function=command_prepare_vowel_preflight)
    gain_scaling_preflight = commands.add_parser("prepare-gain-scaling-preflight"); gain_scaling_preflight.set_defaults(function=command_prepare_gain_scaling_preflight)
    status = commands.add_parser("generalization-status"); status.set_defaults(function=command_generalization_status)
    f0_listening_prepare = commands.add_parser("prepare-f0-listening"); f0_listening_prepare.set_defaults(function=command_prepare_f0_listening)
    f0_listening = commands.add_parser("listen-f0-generalization"); f0_listening.add_argument("--player"); f0_listening.add_argument("--check-only", action="store_true"); f0_listening.set_defaults(function=command_listen_f0_generalization)
    f0_analyze = commands.add_parser("analyze-f0-generalization"); f0_analyze.set_defaults(function=command_analyze_f0_generalization)
    vowel_listening_prepare = commands.add_parser("prepare-vowel-listening"); vowel_listening_prepare.set_defaults(function=command_prepare_vowel_listening)
    vowel_listening = commands.add_parser("listen-vowel-generalization"); vowel_listening.add_argument("--player"); vowel_listening.add_argument("--check-only", action="store_true"); vowel_listening.set_defaults(function=command_listen_vowel_generalization)
    vowel_analyze = commands.add_parser("analyze-vowel-generalization"); vowel_analyze.set_defaults(function=command_analyze_vowel_generalization)
    gain_listening_prepare = commands.add_parser("prepare-gain-scaling-listening"); gain_listening_prepare.set_defaults(function=command_prepare_gain_scaling_listening)
    gain_listening = commands.add_parser("listen-gain-scaling"); gain_listening.add_argument("--player"); gain_listening.add_argument("--check-only", action="store_true"); gain_listening.set_defaults(function=command_listen_gain_scaling)
    gain_analyze = commands.add_parser("analyze-gain-scaling"); gain_analyze.set_defaults(function=command_analyze_gain_scaling)
    test = commands.add_parser("test"); test.set_defaults(function=command_test)
    args = parser.parse_args()
    return int(args.function(args))
