from __future__ import annotations

from typing import Any

from .longitudinal import normalized_presentations


def summarize_f0_listening(
    spec: dict[str, Any],
    private: dict[str, Any],
    responses: dict[str, Any],
    duplicate_consistency_rate: float,
) -> dict[str, Any]:
    rows = normalized_presentations(private, responses)
    pitches: list[dict[str, Any]] = []
    for pair in spec["pairs"]:
        pair_rows = [row for row in rows if row["pair_id"] == pair["pair_id"]]
        if len(pair_rows) != 2:
            raise ValueError(f"{pair['pair_id']}: 提示数は2件である必要があります")
        conditions = (pair["sustain"], pair["onset"])
        choices = [row["answers"]["more_natural_onset"] for row in pair_rows]
        identity: dict[str, dict[str, list[bool]]] = {}
        for condition in conditions:
            identity[condition] = {
                "vowel": [bool(row["answers"]["vowel_identity"].get(condition)) for row in pair_rows],
                "human_voice": [bool(row["answers"]["human_voice_identity"].get(condition)) for row in pair_rows],
                "artifact_free": [not bool(row["artifacts"].get(condition)) for row in pair_rows],
            }
        onset_not_worse = all(choice in pair["acceptable_onset_choices"] for choice in choices)
        identity_passed = all(
            all(values)
            for condition in identity.values()
            for values in condition.values()
        )
        pitches.append({
            "pair_id": pair["pair_id"],
            "f0_hz": pair["f0_hz"],
            "choices": choices,
            "onset_wins": sum(choice == pair["onset"] for choice in choices),
            "onset_not_worse": onset_not_worse,
            "identity": identity,
            "passed": onset_not_worse and identity_passed,
        })
    passed = len(pitches) == len(spec["pairs"]) and all(item["passed"] for item in pitches)
    return {
        "schema_version": spec["schema_version"],
        "study_id": spec["study_id"],
        "status": "listener-qualified" if passed else "listener-gate-failed",
        "presentation_count": len(rows),
        "duplicate_consistency_rate": duplicate_consistency_rate,
        "all_tested_pitches_passed": passed,
        "inference_scope": "single-listener tested-pitch generalization only",
        "population_generalization_allowed": False,
        "pitches": pitches,
    }


def summarize_vowel_listening(
    spec: dict[str, Any],
    private: dict[str, Any],
    responses: dict[str, Any],
    duplicate_consistency_rate: float,
) -> dict[str, Any]:
    rows = normalized_presentations(private, responses)
    vowels: list[dict[str, Any]] = []
    for pair in spec["pairs"]:
        pair_rows = [row for row in rows if row["pair_id"] == pair["pair_id"]]
        if len(pair_rows) != 2:
            raise ValueError(f"{pair['pair_id']}: 提示数は2件である必要があります")
        sustain, onset = pair["sustain"], pair["onset"]
        choices = [row["answers"]["more_natural_onset"] for row in pair_rows]
        identity: dict[str, dict[str, list[bool]]] = {}
        for condition in (sustain, onset):
            identity[condition] = {
                "vowel": [bool(row["answers"]["vowel_identity"].get(condition)) for row in pair_rows],
                "human_voice": [bool(row["answers"]["human_voice_identity"].get(condition)) for row in pair_rows],
                "artifact_free": [not bool(row["artifacts"].get(condition)) for row in pair_rows],
            }
        onset_not_worse = all(choice in {onset, "SAME"} for choice in choices)
        identity_passed = all(
            all(values)
            for condition in identity.values()
            for values in condition.values()
        )
        vowels.append({
            "pair_id": pair["pair_id"],
            "vowel": pair["vowel"],
            "choices": choices,
            "onset_wins": sum(choice == onset for choice in choices),
            "onset_not_worse": onset_not_worse,
            "identity": identity,
            "passed": onset_not_worse and identity_passed,
        })
    passed = len(vowels) == len(spec["pairs"]) and all(item["passed"] for item in vowels)
    return {
        "schema_version": spec["schema_version"],
        "study_id": spec["study_id"],
        "status": "listener-qualified" if passed else "listener-gate-failed",
        "presentation_count": len(rows),
        "duplicate_consistency_rate": duplicate_consistency_rate,
        "all_tested_vowels_passed": passed,
        "inference_scope": "single-listener tested-vowel generalization only",
        "population_generalization_allowed": False,
        "vowels": vowels,
    }


def summarize_gain_scaling_listening(
    spec: dict[str, Any],
    private: dict[str, Any],
    responses: dict[str, Any],
    duplicate_consistency_rate: float,
) -> dict[str, Any]:
    rows = normalized_presentations(private, responses)
    pitches: list[dict[str, Any]] = []
    for pair in spec["pairs"]:
        pair_rows = [row for row in rows if row["pair_id"] == pair["pair_id"]]
        if len(pair_rows) != 2:
            raise ValueError(f"{pair['pair_id']}: 提示数は2件である必要があります")
        fixed, cycle = pair["fixed"], pair["cycle"]
        choices = [row["answers"]["more_natural_onset"] for row in pair_rows]
        conditions_ok = True
        identity: dict[str, dict[str, list[bool]]] = {}
        for condition in (fixed, cycle):
            identity[condition] = {
                "vowel": [bool(row["answers"]["vowel_identity"].get(condition)) for row in pair_rows],
                "human_voice": [bool(row["answers"]["human_voice_identity"].get(condition)) for row in pair_rows],
                "artifact_free": [not bool(row["artifacts"].get(condition)) for row in pair_rows],
            }
            conditions_ok = conditions_ok and all(all(values) for values in identity[condition].values())
        preference_consistent = choices[0] == choices[1]
        outcome = (
            "fixed" if preference_consistent and choices[0] == fixed
            else "cycle" if preference_consistent and choices[0] == cycle
            else "same" if preference_consistent and choices[0] == "SAME"
            else "inconsistent"
        )
        pitches.append({
            "pair_id": pair["pair_id"],
            "f0_hz": pair["f0_hz"],
            "choices": choices,
            "outcome": outcome,
            "preference_consistent": preference_consistent,
            "identity": identity,
            "valid": preference_consistent and conditions_ok,
        })
    valid = len(pitches) == len(spec["pairs"]) and all(item["valid"] for item in pitches)
    outcomes = [item["outcome"] for item in pitches]
    if not valid:
        selection = "inconclusive"
    elif outcomes == ["cycle", "cycle"]:
        selection = "cycle"
    elif set(outcomes) == {"fixed", "cycle"}:
        selection = "pitch-dependent"
    else:
        selection = "fixed"
    return {
        "schema_version": spec["schema_version"],
        "study_id": spec["study_id"],
        "status": "decision-valid" if valid else "listener-gate-failed",
        "presentation_count": len(rows),
        "duplicate_consistency_rate": duplicate_consistency_rate,
        "decision_valid": valid,
        "selected_rule": selection,
        "inference_scope": "single-listener tested-pitch scaling preference only",
        "population_generalization_allowed": False,
        "pitches": pitches,
    }
