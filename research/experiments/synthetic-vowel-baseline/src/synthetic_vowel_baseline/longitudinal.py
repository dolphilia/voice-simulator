from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def study_config(experiment_root: Path) -> dict[str, Any]:
    path = experiment_root / "config/single-listener-longitudinal.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_run_number(value: int, planned_runs: int) -> int:
    if not 1 <= value <= planned_runs:
        raise ValueError(f"runは1〜{planned_runs}で指定してください")
    return value


def run_session_path(experiment_root: Path, spec: dict[str, Any], run: int) -> Path:
    validate_run_number(run, int(spec["planned_runs"]))
    return experiment_root / "results/generalization" / spec["study_id"] / f"run-{run:02d}"


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def hours_since_previous(previous_completed_at: str, now: datetime) -> float:
    previous = parse_timestamp(previous_completed_at)
    if previous.tzinfo is None or now.tzinfo is None:
        raise ValueError("日時にはタイムゾーンが必要です")
    return (now - previous).total_seconds() / 3600.0


def _selected(row: dict[str, Any], answer: Any) -> Any:
    if isinstance(answer, str) and answer in {"A", "B"}:
        return row[answer]["condition"]
    if isinstance(answer, dict):
        return {row[side]["condition"]: bool(value) for side, value in answer.items()}
    return answer


def normalized_presentations(private: dict[str, Any], responses: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in private["presentations"]:
        attempts = responses["attempts"].get(key["presentation_id"], [])
        clean = next((item for item in reversed(attempts) if not item.get("interference")), None)
        if clean is None:
            raise ValueError(f"{key['presentation_id']}: 外乱のない有効回答がありません")
        answers = {name: _selected(key, answer) for name, answer in clean["answers"].items()}
        artifacts = {
            key[side]["condition"]: bool(clean["artifact"][side]) for side in ("A", "B")
        }
        rows.append({
            "presentation_id": key["presentation_id"],
            "pair_id": key["pair_id"],
            "answers": answers,
            "artifacts": artifacts,
        })
    return rows


def summarize_run(
    run: int,
    spec: dict[str, Any],
    private: dict[str, Any],
    responses: dict[str, Any],
    duplicate_consistency_rate: float,
) -> dict[str, Any]:
    rows = normalized_presentations(private, responses)
    pair_results: dict[str, Any] = {}
    for pair in spec["pairs"]:
        pair_rows = [row for row in rows if row["pair_id"] == pair["pair_id"]]
        if len(pair_rows) != 2:
            raise ValueError(f"{pair['pair_id']}: 提示数は2件である必要があります")
        target = pair["target"]
        choices = [row["answers"][pair["comparison_axis"]] for row in pair_rows]
        vowel = [bool(row["answers"]["vowel_identity"].get(target)) for row in pair_rows]
        human = [bool(row["answers"]["human_voice_identity"].get(target)) for row in pair_rows]
        artifact_free = [not bool(row["artifacts"].get(target)) for row in pair_rows]
        comparison_passed = all(choice in pair["acceptable_choices"] for choice in choices)
        pair_results[pair["pair_id"]] = {
            "target": target,
            "comparison_axis": pair["comparison_axis"],
            "choices": choices,
            "target_wins": sum(choice == target for choice in choices),
            "comparison_passed": comparison_passed,
            "target_vowel_identity": vowel,
            "target_human_voice_identity": human,
            "target_artifact_free": artifact_free,
            "passed": comparison_passed and all(vowel) and all(human) and all(artifact_free),
        }
    return {
        "run": run,
        "completed_at": responses["completed_at"],
        "presentation_count": len(rows),
        "duplicate_consistency_rate": duplicate_consistency_rate,
        "pairs": pair_results,
    }


def aggregate_runs(spec: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    planned = int(spec["planned_runs"])
    minimum_passes = int(spec["advance_gate"]["minimum_passing_runs_per_target"])
    pair_totals: dict[str, Any] = {}
    for pair in spec["pairs"]:
        results = [run["pairs"][pair["pair_id"]] for run in runs]
        passes = sum(bool(item["passed"]) for item in results)
        pair_totals[pair["pair_id"]] = {
            "target": pair["target"],
            "passing_runs": passes,
            "required_passing_runs": minimum_passes,
            "passed": len(runs) == planned and passes >= minimum_passes,
            "target_wins": sum(int(item["target_wins"]) for item in results),
            "presentation_count": 2 * len(results),
        }
    consistency = (
        sum(float(run["duplicate_consistency_rate"]) for run in runs) / len(runs) if runs else 0.0
    )
    complete = len(runs) == planned
    passed = (
        complete
        and consistency >= float(spec["advance_gate"]["minimum_duplicate_consistency_rate"])
        and all(item["passed"] for item in pair_totals.values())
    )
    return {
        "schema_version": spec["schema_version"],
        "study_id": spec["study_id"],
        "design": spec["design"],
        "listener_count": 1,
        "completed_runs": len(runs),
        "planned_runs": planned,
        "complete": complete,
        "mean_within_run_duplicate_consistency_rate": consistency,
        "pairs": pair_totals,
        "advance_gate_passed": passed,
        "inference_scope": "single-listener within-person stability only",
        "population_generalization_allowed": False,
        "runs": runs,
    }
