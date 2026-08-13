from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import sys
import unittest
from pathlib import Path
from typing import Any

import numpy as np

from . import SCHEMA_VERSION
from .audio import read_audio, sha256_file, write_audio, write_json
from .boundaries import detect_boundaries
from .manifest import Record, load_manifest, validate_manifest
from .reporting import derive_model_parameters, markdown_analysis, markdown_model_parameters, write_summary_csv
from .stimuli import render_a_stimuli
from .synthesis import render_suite
from .trajectories import extract_trajectory, summarize_trajectory
from .validation import apply_gate


def root() -> Path:
    return Path(__file__).resolve().parents[2]


def config() -> dict[str, Any]:
    return json.loads((root() / "config/experiment.json").read_text(encoding="utf-8"))


def manifest_path() -> Path:
    return root() / "config/datasets.csv"


def result_dir() -> Path:
    return root() / "results"


def _analyze_records(records: list[Record], output_stem: str) -> list[dict[str, Any]]:
    spec = config(); analysis_spec = spec["analysis"]
    results: list[dict[str, Any]] = []
    for record in records:
        sample_rate, audio = read_audio(record.path, int(spec["sample_rate"]))
        boundaries, boundary_series = detect_boundaries(audio, sample_rate, float(analysis_spec["frame_ms"]), float(analysis_spec["hop_ms"]))
        trajectory = extract_trajectory(audio, sample_rate, float(analysis_spec["frame_ms"]), float(analysis_spec["hop_ms"]))
        summary = summarize_trajectory(trajectory, boundaries.stable_vowel_onset_sec)
        results.append({
            "schema_version": SCHEMA_VERSION, "sample_id": record.sample_id, "speaker_id": record.speaker_id,
            "take_id": record.take_id, "vowel": record.vowel, "split": record.split,
            "source_sha256": sha256_file(record.path), "sample_rate": sample_rate,
            "boundaries": boundaries.to_dict(), "boundary_series": boundary_series,
            "trajectory": trajectory, "summary": summary,
            "limitations": ["UTAU音源表情であり同一条件の別テイクではない", "stable_vowelはformant軌道で後段監査する候補境界"],
        })
    output = result_dir() / "analysis"
    write_json(output / f"{output_stem}.json", {"schema_version": SCHEMA_VERSION, "split": records[0].split if records else None, "samples": results})
    write_summary_csv(output / f"{output_stem}.csv", results)
    (output / f"{output_stem}.md").write_text(markdown_analysis(results), encoding="utf-8")
    if output_stem == "development":
        model = derive_model_parameters(results)
        write_json(output / "model-parameters.json", model)
        (output / "model-parameters.md").write_text(markdown_model_parameters(model), encoding="utf-8")
    return results


def command_validate(_: argparse.Namespace) -> int:
    errors = validate_manifest(manifest_path())
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


def command_analyze(args: argparse.Namespace) -> int:
    if args.split == "onset-holdout" and not args.allow_holdout:
        print("onset-holdout is sealed; use --allow-holdout only after candidate freeze", file=sys.stderr)
        return 2
    records = load_manifest(manifest_path(), {args.split})
    if not records:
        print(f"no records for {args.split}", file=sys.stderr); return 2
    stem = args.split.removeprefix("onset-")
    _analyze_records(records, stem)
    print(f"analyzed {len(records)} records -> {result_dir() / 'analysis' / (stem + '.json')}")
    return 0


def _load_analysis(split: str) -> tuple[list[Record], dict[str, dict[str, Any]]]:
    stem = split.removeprefix("onset-")
    path = result_dir() / "analysis" / f"{stem}.json"
    records = load_manifest(manifest_path(), {split})
    if not path.is_file():
        _analyze_records(records, stem)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return records, {item["sample_id"]: item for item in payload["samples"]}


def _render_stimuli(split: str) -> list[dict[str, Any]]:
    spec = config(); stimulus_spec = spec["stimuli"]
    records, analyses = _load_analysis(split)
    output = result_dir() / "stimuli" / split.removeprefix("onset-")
    manifest: list[dict[str, Any]] = []
    for record in records:
        sample_rate, audio = read_audio(record.path, int(spec["sample_rate"]))
        boundaries = analyses[record.sample_id]["boundaries"]
        rendered = render_a_stimuli(
            audio, sample_rate, float(boundaries["acoustic_activity_onset_sec"]),
            float(boundaries["stable_vowel_onset_sec"]), float(boundaries["activity_end_sec"]),
            float(stimulus_spec["output_duration_sec"]), float(stimulus_spec["shortened_duration_sec"]),
            list(stimulus_spec["loop_lengths_ms"]), float(stimulus_spec["crossfade_ms"]), float(stimulus_spec["target_dbfs"]),
            np.asarray([np.nan if value is None else value for value in analyses[record.sample_id]["trajectory"]["f0_hz"]], dtype=float),
            np.asarray([np.nan if value is None else value for value in analyses[record.sample_id]["trajectory"]["rms_db"]], dtype=float),
        )
        for item in rendered:
            stimulus_id = f"{record.sample_id}--{item['condition']}"
            path = output / f"{stimulus_id}.wav"
            rendered_audio = item.pop("audio")
            write_audio(path, sample_rate, rendered_audio)
            passed, failures = apply_gate(item, spec["gates"])
            trajectory = extract_trajectory(rendered_audio, sample_rate, float(spec["analysis"]["frame_ms"]), float(spec["analysis"]["hop_ms"]))
            stimulus_summary = summarize_trajectory(trajectory, min(0.25, float(stimulus_spec["shortened_duration_sec"]) * 0.5))
            manifest.append({
                "stimulus_id": stimulus_id, "sample_id": record.sample_id, "speaker_id": record.speaker_id,
                "take_id": record.take_id, "split": split, "condition": item["condition"],
                "relative_path": str(path.relative_to(root())), "sha256": sha256_file(path),
                "contains_human_audio": True, "export_allowed": False,
                "gate_passed": passed, "gate_failures": failures,
                "seam_jump_ratio": item["seam_jump_ratio"], "integrity": item["integrity"], "metadata": item["metadata"],
                "trajectory_summary": stimulus_summary,
            })
    write_json(output / "manifest.json", {"schema_version": SCHEMA_VERSION, "split": split, "stimuli": manifest})
    return manifest


def command_render_stimuli(args: argparse.Namespace) -> int:
    if args.split == "onset-holdout":
        print("holdout stimuli may not be rendered before the final frozen evaluation", file=sys.stderr); return 2
    rendered = _render_stimuli(args.split)
    failed = sum(not item["gate_passed"] for item in rendered)
    print(f"rendered {len(rendered)} stimuli ({failed} gate failures)")
    return 0 if failed == 0 else 3


def _median_feature(analyses: list[dict[str, Any]], feature: str, fallback: float) -> float:
    values = [item["summary"].get(feature, {}).get("stable_median") for item in analyses]
    finite = [float(value) for value in values if value is not None and np.isfinite(value)]
    return float(np.median(finite)) if finite else fallback


def _render_synthesis() -> list[dict[str, Any]]:
    spec = config(); analysis_file = result_dir() / "analysis/development.json"
    if not analysis_file.is_file():
        _analyze_records(load_manifest(manifest_path(), {"onset-development"}), "development")
    analyses = json.loads(analysis_file.read_text(encoding="utf-8"))["samples"]
    model_path = result_dir() / "analysis/model-parameters.json"
    model = json.loads(model_path.read_text(encoding="utf-8")) if model_path.is_file() else derive_model_parameters(analyses)
    f0 = float(model["stable"]["f0_hz"]["median"])
    formants = tuple(float(model["stable"][name]["median"]) for name in ("f1_hz", "f2_hz", "f3_hz"))
    onset_sec = float(model["onset_duration_sec"]["median"])
    rendered = render_suite(int(spec["sample_rate"]), float(spec["stimuli"]["output_duration_sec"]), f0, formants, int(spec["seed"]), onset_sec)
    output = result_dir() / "generated"
    manifest: list[dict[str, Any]] = []
    for item in rendered:
        path = output / f"{item['condition']}.wav"
        rendered_audio = item.pop("audio")
        write_audio(path, int(spec["sample_rate"]), rendered_audio)
        passed, failures = apply_gate(item, spec["gates"])
        trajectory = extract_trajectory(rendered_audio, int(spec["sample_rate"]), float(spec["analysis"]["frame_ms"]), float(spec["analysis"]["hop_ms"]))
        summary = summarize_trajectory(trajectory, onset_sec)
        manifest.append({**item, "stimulus_id": item["condition"], "relative_path": str(path.relative_to(root())), "sha256": sha256_file(path), "gate_passed": passed, "gate_failures": failures, "trajectory_summary": summary})
    write_json(output / "manifest.json", {"schema_version": SCHEMA_VERSION, "reference_parameters": {"f0_hz": f0, "formants_hz": formants}, "stimuli": manifest})
    lines = ["# C系列 自動比較", "", "自動値は操作成立の確認にだけ使い、自然さを順位付けしない。", "", "| condition | F0 start→stable | periodicity start→stable | HNR start→stable | slope start→stable | gate |", "| --- | ---: | ---: | ---: | ---: | --- |"]
    for item in manifest:
        summary = item["trajectory_summary"]
        def delta(name: str) -> str:
            value = summary.get(name, {}).get("start_to_stable_delta")
            return "—" if value is None else f"{float(value):.3f}"
        lines.append(f"| {item['condition']} | {delta('f0_hz')} | {delta('periodicity')} | {delta('hnr_db')} | {delta('spectral_slope_db_khz')} | {'pass' if item['gate_passed'] else 'fail'} |")
    (output / "automatic-comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def command_render_synthesis(_: argparse.Namespace) -> int:
    rendered = _render_synthesis(); failed = sum(not item["gate_passed"] for item in rendered)
    print(f"rendered {len(rendered)} fully synthetic ablations ({failed} gate failures)")
    return 0 if failed == 0 else 3


def command_freeze(_: argparse.Namespace) -> int:
    spec = config()
    checkpoint = _render_stimuli("onset-checkpoint")
    generated_manifest_path = result_dir() / "generated/manifest.json"
    generated = json.loads(generated_manifest_path.read_text(encoding="utf-8"))["stimuli"] if generated_manifest_path.is_file() else _render_synthesis()
    by_sample_condition = {(item["sample_id"], item["condition"]): item for item in checkpoint if item["gate_passed"]}
    by_generated = {item["condition"]: item for item in generated if item["gate_passed"]}
    pairs: list[dict[str, Any]] = []
    for sample_id in sorted({item["sample_id"] for item in checkpoint}):
        def human_pair(pair_id: str, hypothesis: str, left: str, right: str, question: str) -> None:
            pairs.append({"pair_id": f"{sample_id}--{pair_id}", "hypothesis": hypothesis, "question": question, "left": by_sample_condition[(sample_id, left)], "right": by_sample_condition[(sample_id, right)]})
        human_pair("onset-vs-stable", "H1", "A1-onset-shortened", "A2-stable-only", "開始部を残す効果")
        human_pair("original-vs-shortened", "control", "A0-original", "A1-onset-shortened", "短縮処理自体の影響")
        human_pair("long-loop", "H6", "A1-onset-shortened", "A3-loop-long", "長いループの影響")
        human_pair("short-loop", "H6", "A1-onset-shortened", "A4-loop-short-40ms", "短いループの影響")
        human_pair("variation-relationship", "H4", "A5-loop-correlated-variation", "A6-loop-independent-variation", "変動の時間関係")
    pairs += [
        {"pair_id": "synthetic--gain-vs-coupled", "hypothesis": "H3", "question": "ゲイン包絡と複合開始モデル", "left": by_generated["C1-gain"], "right": by_generated["C6-coupled"]},
        {"pair_id": "synthetic--correlated-vs-independent", "hypothesis": "H4", "question": "合成変動の相関構造", "left": by_generated["C6-coupled"], "right": by_generated["C7-independent"]},
        {"pair_id": "synthetic--formant-ablation", "hypothesis": "H5", "question": "formant収束軌道", "left": by_generated["C6-coupled"], "right": by_generated["C6-no-formant"]},
    ]
    if len(pairs) != 13:
        print(f"unexpected pair count: {len(pairs)}", file=sys.stderr); return 3
    rng = random.Random(int(spec["seed"]))
    for pair in pairs:
        if rng.random() < 0.5:
            pair["left"], pair["right"] = pair["right"], pair["left"]
    duplicate_indices = rng.sample(range(len(pairs)), 2)
    presentations = pairs + [{**pairs[index], "duplicate_of": pairs[index]["pair_id"]} for index in duplicate_indices]
    rng.shuffle(presentations)
    session = result_dir() / "listening/checkpoint"
    audio_dir = session / "audio"; audio_dir.mkdir(parents=True, exist_ok=True)
    for stale in audio_dir.glob("*.wav"):
        stale.unlink()
    key_rows = []; response_rows = []
    for position, pair in enumerate(presentations, 1):
        presentation_id = f"T{position:02d}"
        row = {"presentation_id": presentation_id, "pair_id": pair["pair_id"], "hypothesis": pair["hypothesis"], "question": pair["question"], "duplicate_of": pair.get("duplicate_of", "")}
        for side, candidate in (("A", pair["left"]), ("B", pair["right"])):
            source = root() / candidate["relative_path"]
            destination = audio_dir / f"{presentation_id}-{side}.wav"
            shutil.copy2(source, destination)
            row[f"{side.lower()}_stimulus_id"] = candidate["stimulus_id"]
            row[f"{side.lower()}_condition"] = candidate["condition"]
            row[f"{side.lower()}_sha256"] = sha256_file(destination)
        key_rows.append(row)
        response_rows.append({"presentation_id": presentation_id, "more_human": "", "more_natural_onset": "", "more_natural_sustain": "", "artifact": "", "confidence": "", "notes": ""})
    session.mkdir(parents=True, exist_ok=True)
    for filename, rows in (("presentation-key.csv", key_rows), ("responses.csv", response_rows)):
        with (session / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    locked_files = [session / "presentation-key.csv", session / "responses.csv", root() / "config/experiment.json", root() / "config/evidence-contract.md"]
    lock = {
        "schema_version": SCHEMA_VERSION, "status": "frozen-awaiting-listening", "seed": spec["seed"],
        "presentation_count": len(presentations), "unique_pair_count": len(pairs), "duplicate_count": 2,
        "files": {str(path.relative_to(root())): sha256_file(path) for path in locked_files},
        "audio": {f"{row['presentation_id']}-{side}": row[f"{side.lower()}_sha256"] for row in key_rows for side in ("A", "B")},
        "holdout_opened": False,
    }
    write_json(session / "lock.json", lock)
    (session / "README.md").write_text(
        "# 第1試聴チェックポイント\n\n自動工程で15提示（13比較＋重複2）を凍結済みです。各 `Txx-A.wav` と `Txx-B.wav` を比較します。\n\n"
        "`responses.csv` の回答規則:\n\n"
        "- `more_human`, `more_natural_onset`, `more_natural_sustain`: `A`, `B`, `TIE`\n"
        "- `artifact`: 加工由来の違和感が強い側を `A`, `B`, `BOTH`, `NEITHER`\n"
        "- `confidence`: 1（ほぼ分からない）〜5（明確）\n"
        "- `notes`: 掠れ、息、舌足らず、楽器的、ループ感など任意の理由\n\n"
        "音量を固定し、提示順に評価してください。疲れた場合は途中で中断できます。 `presentation-key.csv` は解析用であり、ブラインド試聴前には参照しません。\n",
        encoding="utf-8",
    )
    print(f"frozen {len(pairs)} unique pairs / {len(presentations)} presentations -> {session}")
    return 0


def command_test(_: argparse.Namespace) -> int:
    suite = unittest.defaultTestLoader.discover(str(root() / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def command_analyze_listening(args: argparse.Namespace) -> int:
    session = Path(args.session).resolve()
    key_path, responses_path, lock_path = session / "presentation-key.csv", session / "responses.csv", session / "lock.json"
    if not all(path.is_file() for path in (key_path, responses_path, lock_path)):
        print("listening session is incomplete", file=sys.stderr); return 2
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    for relative, expected in lock.get("files", {}).items():
        if relative.endswith("responses.csv"):
            continue
        locked_path = root() / relative
        if not locked_path.is_file() or sha256_file(locked_path) != expected:
            print(f"locked file changed or missing: {relative}", file=sys.stderr); return 2
    for audio_id, expected in lock.get("audio", {}).items():
        audio_path = session / "audio" / f"{audio_id}.wav"
        if not audio_path.is_file() or sha256_file(audio_path) != expected:
            print(f"locked audio changed or missing: {audio_id}", file=sys.stderr); return 2
    with key_path.open(newline="", encoding="utf-8") as handle:
        keys = {row["presentation_id"]: row for row in csv.DictReader(handle)}
    with responses_path.open(newline="", encoding="utf-8") as handle:
        responses = list(csv.DictReader(handle))
    errors: list[str] = []
    allowed_choice = {"A", "B", "TIE"}; allowed_artifact = {"A", "B", "BOTH", "NEITHER"}
    if len(responses) != int(lock["presentation_count"]):
        errors.append(f"response count: {len(responses)} != {lock['presentation_count']}")
    combined = []
    for row in responses:
        presentation_id = row.get("presentation_id", "")
        if presentation_id not in keys:
            errors.append(f"unknown presentation: {presentation_id}"); continue
        for field in ("more_human", "more_natural_onset", "more_natural_sustain"):
            if row.get(field) not in allowed_choice:
                errors.append(f"{presentation_id}: {field} must be A/B/TIE")
        if row.get("artifact") not in allowed_artifact:
            errors.append(f"{presentation_id}: artifact must be A/B/BOTH/NEITHER")
        try:
            confidence = int(row.get("confidence", ""))
            if not 1 <= confidence <= 5:
                raise ValueError
        except ValueError:
            errors.append(f"{presentation_id}: confidence must be 1..5")
        combined.append({**keys[presentation_id], **row})
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2)); return 2

    def selected_condition(row: dict[str, str], field: str) -> str:
        choice = row[field]
        return "TIE" if choice == "TIE" else row[f"{choice.lower()}_condition"]

    pair_groups: dict[str, list[dict[str, str]]] = {}
    for row in combined:
        pair_groups.setdefault(row["pair_id"], []).append(row)
    duplicate_differences = []
    for pair_id, rows in pair_groups.items():
        if len(rows) > 1:
            for field in ("more_human", "more_natural_onset", "more_natural_sustain"):
                duplicate_differences.append({"pair_id": pair_id, "axis": field, "consistent": selected_condition(rows[0], field) == selected_condition(rows[1], field)})
    hypotheses: dict[str, dict[str, Any]] = {}
    for row in combined:
        if row.get("duplicate_of"):
            continue
        entry = hypotheses.setdefault(row["hypothesis"], {"comparisons": []})
        entry["comparisons"].append({
            "pair_id": row["pair_id"],
            "more_human": selected_condition(row, "more_human"),
            "more_natural_onset": selected_condition(row, "more_natural_onset"),
            "more_natural_sustain": selected_condition(row, "more_natural_sustain"),
            "artifact": row["artifact"], "confidence": int(row["confidence"]), "notes": row["notes"],
        })
    output = {
        "schema_version": SCHEMA_VERSION, "status": "checkpoint-analyzed", "session": str(session),
        "response_sha256": sha256_file(responses_path), "presentation_key_sha256": sha256_file(key_path),
        "duplicate_consistency": duplicate_differences,
        "duplicate_consistency_rate": sum(item["consistent"] for item in duplicate_differences) / max(1, len(duplicate_differences)),
        "hypotheses": hypotheses,
        "holdout_opened": False,
    }
    write_json(Path(args.output), output)
    print(f"listening responses valid -> {Path(args.output).resolve()}")
    return 0


def command_pipeline(_: argparse.Namespace) -> int:
    steps = [
        (command_validate, argparse.Namespace()),
        (command_analyze, argparse.Namespace(split="onset-development", allow_holdout=False)),
        (command_render_stimuli, argparse.Namespace(split="onset-development")),
        (command_render_synthesis, argparse.Namespace()),
        (command_freeze, argparse.Namespace()),
    ]
    for function, arguments in steps:
        code = function(arguments)
        if code:
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="発声開始と非定常性の研究CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, function in (("test", command_test), ("validate-manifest", command_validate), ("render-synthesis", command_render_synthesis), ("freeze-candidates", command_freeze), ("pipeline", command_pipeline)):
        child = commands.add_parser(name); child.set_defaults(function=function)
    analyze = commands.add_parser("analyze"); analyze.add_argument("--split", default="onset-development", choices=sorted({"onset-development", "onset-checkpoint", "onset-holdout"})); analyze.add_argument("--allow-holdout", action="store_true"); analyze.set_defaults(function=command_analyze)
    render = commands.add_parser("render-stimuli"); render.add_argument("--split", default="onset-development", choices=["onset-development", "onset-checkpoint"]); render.set_defaults(function=command_render_stimuli)
    listening = commands.add_parser("analyze-listening"); listening.add_argument("--session", default=str(result_dir() / "listening/checkpoint")); listening.add_argument("--output", default=str(result_dir() / "listening/checkpoint-analysis.json")); listening.set_defaults(function=command_analyze_listening)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.function(args))
