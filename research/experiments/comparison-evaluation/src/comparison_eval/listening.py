from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import wavfile

from .signal import level_normalize, read_audio


RESPONSE_FIELDS = ("presentation_id", "evaluator_id", "phoneme_identity", "naturalness", "clarity", "voice_quality", "target_similarity", "notes")


def _write_pcm(path: Path, sample_rate: int, audio: np.ndarray) -> None:
    normalized = level_normalize(audio, -20.0)
    peak = float(np.max(np.abs(normalized))) if normalized.size else 0.0
    if peak > 0.98:
        normalized *= 0.98 / peak
    wavfile.write(path, sample_rate, np.round(np.clip(normalized, -1.0, 1.0) * 32767.0).astype(np.int16))


def _candidate_selection(benchmark: dict[str, Any], maximum: int, selection: str = "pareto") -> list[dict[str, Any]]:
    eligible = [result for result in benchmark.get("results", []) if not result.get("gate_failures")]
    if selection == "all":
        return eligible[:maximum]
    pareto = set(benchmark.get("pareto_front", []))
    front = [result for result in eligible if result["task"]["task_id"] in pareto] or eligible
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for result in front:
        by_variant.setdefault(result["task"].get("variant", "unknown"), []).append(result)
    selected: list[dict[str, Any]] = []
    while len(selected) < maximum and any(by_variant.values()):
        for variant in sorted(by_variant):
            if by_variant[variant] and len(selected) < maximum:
                selected.append(by_variant[variant].pop(0))
    return selected


def prepare_session(benchmark: dict[str, Any], output: Path, seed: int = 20260813, maximum: int = 6, duplicate_ratio: float = 0.2, selection: str = "pareto") -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    audio_dir = output / "audio"
    audio_dir.mkdir(exist_ok=True)
    for stale_audio in audio_dir.glob("*.wav"):
        stale_audio.unlink()
    selected = _candidate_selection(benchmark, maximum, selection)
    rng = random.Random(seed)
    presentations = list(selected)
    duplicate_count = min(len(selected), max(1, round(len(selected) * duplicate_ratio))) if selected else 0
    presentations.extend(rng.sample(selected, duplicate_count))
    rng.shuffle(presentations)
    key: list[dict[str, Any]] = []
    public_map: list[dict[str, str]] = []
    reference_files: dict[str, str] = {}
    response_rows = []
    for index, result in enumerate(presentations, 1):
        task = result["task"]
        presentation_id = f"P{index:02d}"
        candidate_path = Path(task["generated_path"]).resolve()
        reference_path = Path(task["reference_path"]).resolve()
        candidate_rate, candidate = read_audio(candidate_path)
        candidate_name = f"{presentation_id}-candidate.wav"
        _write_pcm(audio_dir / candidate_name, candidate_rate, candidate)
        reference_key = hashlib.sha256(str(reference_path).encode()).hexdigest()[:8]
        if reference_key not in reference_files:
            reference_rate, reference = read_audio(reference_path)
            reference_name = f"R{len(reference_files) + 1:02d}-reference.wav"
            _write_pcm(audio_dir / reference_name, reference_rate, reference)
            reference_files[reference_key] = reference_name
        key.append({"presentation_id": presentation_id, "task_id": task["task_id"], "variant": task["variant"], "candidate": candidate_name, "reference": reference_files[reference_key]})
        public_map.append({"presentation_id": presentation_id, "candidate": candidate_name, "reference": reference_files[reference_key]})
        response_rows.append({field: presentation_id if field == "presentation_id" else "evaluator-1" if field == "evaluator_id" else "" for field in RESPONSE_FIELDS})
    with (output / "responses.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESPONSE_FIELDS)
        writer.writeheader()
        writer.writerows(response_rows)
    with (output / "presentation-map.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("presentation_id", "candidate", "reference"))
        writer.writeheader(); writer.writerows(public_map)
    (output / "session-key.json").write_text(json.dumps({"seed": seed, "items": key}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    protocol = """# ブラインド試聴手順

`session-key.json` は評価完了まで開かない。`presentation-map.csv` に示されたcandidateとreferenceを比較し、回答を `responses.csv` に記入する。

- 静かな環境と同じ再生機器・音量を使う。
- 1〜5（低い〜高い）で、音素同一性、自然さ、明瞭さ、声質の人間らしさ、参照類似性を別々に評価する。
- 候補間で音量を変えない。各項目は必要なら数回聴いてよいが、モデル名や生成条件は確認しない。
- 同じ候補が重複することがある。前の回答を探して合わせず、その時点の判断を記録する。
- 疲労を感じたら中断し、再開時も同じ機器を使う。
"""
    (output / "README.md").write_text(protocol, encoding="utf-8")
    return {"selected_candidates": len(selected), "presentations": len(presentations), "duplicate_count": duplicate_count, "output": str(output)}


def analyze_responses(session: Path) -> dict[str, Any]:
    key_data = json.loads((session / "session-key.json").read_text(encoding="utf-8"))
    key = {item["presentation_id"]: item for item in key_data["items"]}
    with (session / "responses.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    scored = []
    for row in rows:
        if row["presentation_id"] not in key:
            continue
        scores = {}
        for field in RESPONSE_FIELDS[2:-1]:
            if row.get(field):
                value = float(row[field])
                if not 1.0 <= value <= 5.0:
                    raise ValueError(f"{row['presentation_id']}:{field} must be 1..5")
                scores[field] = value
        scored.append({**key[row["presentation_id"]], "evaluator_id": row.get("evaluator_id") or "evaluator-1", "scores": scores, "notes": row.get("notes", "")})
    by_task: dict[str, list[dict[str, float]]] = {}
    by_evaluator_task: dict[tuple[str, str], list[dict[str, float]]] = {}
    for item in scored:
        if item["scores"]:
            by_task.setdefault(item["task_id"], []).append(item["scores"])
            by_evaluator_task.setdefault((item["evaluator_id"], item["task_id"]), []).append(item["scores"])
    aggregates = {}
    for task_id, task_scores in by_task.items():
        aggregates[task_id] = {field: float(np.mean([scores[field] for scores in task_scores if field in scores])) for field in RESPONSE_FIELDS[2:-1] if any(field in scores for scores in task_scores)}
    consistency = []
    for (evaluator_id, task_id), task_scores in by_evaluator_task.items():
        if len(task_scores) >= 2:
            shared = set.intersection(*(set(scores) for scores in task_scores))
            consistency.append({"evaluator_id": evaluator_id, "task_id": task_id, "mean_absolute_repeat_difference": float(np.mean([abs(task_scores[0][field] - task_scores[1][field]) for field in shared])) if shared else None})
    evaluator_rankings: dict[str, dict[str, float]] = {}
    for evaluator in sorted({item["evaluator_id"] for item in scored}):
        evaluator_items = [item for item in scored if item["evaluator_id"] == evaluator and item["scores"]]
        by_task_evaluator: dict[str, list[float]] = {}
        for item in evaluator_items:
            if "naturalness" in item["scores"]:
                by_task_evaluator.setdefault(item["task_id"], []).append(item["scores"]["naturalness"])
        evaluator_rankings[evaluator] = {task: float(np.mean(values)) for task, values in by_task_evaluator.items()}
    between = []
    evaluator_ids = sorted(evaluator_rankings)
    for first_index, first in enumerate(evaluator_ids):
        for second in evaluator_ids[first_index + 1 :]:
            shared = sorted(set(evaluator_rankings[first]) & set(evaluator_rankings[second]))
            if len(shared) >= 3:
                from scipy import stats
                coefficient = float(stats.spearmanr([evaluator_rankings[first][task] for task in shared], [evaluator_rankings[second][task] for task in shared]).statistic)
                between.append({"first": first, "second": second, "axis": "naturalness", "spearman": coefficient, "task_count": len(shared)})
    expected = len(key) * max(1, len(evaluator_ids))
    return {"responses": scored, "task_aggregates": aggregates, "repeat_consistency": consistency, "between_evaluator_agreement": between, "complete": len(scored) == expected and all(item["scores"] for item in scored)}


def prepare_perceptual_suite(rendered: dict[str, Any], benchmark: dict[str, Any], output: Path, seed: int = 20260813) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    audio_dir = output / "audio"
    audio_dir.mkdir(exist_ok=True)
    for stale in audio_dir.glob("*.wav"):
        stale.unlink()
    rng = random.Random(seed)
    identification = [record for record in rendered["records"] if record["kind"] in {"vowel-identification", "cv-identification"}]
    rng.shuffle(identification)
    key_items, response_rows = [], []
    for index, record in enumerate(identification, 1):
        presentation_id = f"I{index:02d}"
        sample_rate, audio = read_audio(Path(record["path"]))
        filename = f"{presentation_id}.wav"
        _write_pcm(audio_dir / filename, sample_rate, audio)
        key_items.append({"presentation_id": presentation_id, "task_type": record["kind"], "correct_label": record["label"], "file": filename})
        response_rows.append({"presentation_id": presentation_id, "task_type": record["kind"], "answer": "", "confidence": "", "notes": ""})
    attribute_records = {record["label"]: record for record in rendered["records"] if record["kind"] == "attribute-order"}
    for pair_index, (axis, low, high) in enumerate((("brightness", "brightness-low", "brightness-high"), ("breathiness", "breathiness-low", "breathiness-high")), 1):
        order = [low, high]
        rng.shuffle(order)
        presentation_id = f"O{pair_index:02d}"
        files = []
        for side, label in zip(("A", "B"), order, strict=True):
            sample_rate, audio = read_audio(Path(attribute_records[label]["path"]))
            filename = f"{presentation_id}-{side}.wav"
            _write_pcm(audio_dir / filename, sample_rate, audio)
            files.append(filename)
        correct = "A" if order[0] == high else "B"
        key_items.append({"presentation_id": presentation_id, "task_type": "attribute-order", "axis": axis, "correct_answer": correct, "files": files})
        response_rows.append({"presentation_id": presentation_id, "task_type": f"which-is-more-{axis}", "answer": "", "confidence": "", "notes": ""})
    eligible = [result for result in benchmark.get("results", []) if not result.get("gate_failures")]
    original = next((item for item in eligible if item["task"].get("variant") == "original"), None)
    improved = next((item for item in eligible if item["task"].get("variant") == "spectral-match"), None)
    if original and improved:
        candidates = [original, improved]
        rng.shuffle(candidates)
        presentation_id = "A01"
        files = []
        for side, result in zip(("A", "B"), candidates, strict=True):
            sample_rate, audio = read_audio(Path(result["task"]["generated_path"]))
            filename = f"{presentation_id}-{side}.wav"
            _write_pcm(audio_dir / filename, sample_rate, audio)
            files.append(filename)
        reference_rate, reference = read_audio(Path(original["task"]["reference_path"]))
        reference_name = f"{presentation_id}-reference.wav"
        _write_pcm(audio_dir / reference_name, reference_rate, reference)
        key_items.append({"presentation_id": presentation_id, "task_type": "ab-reference-similarity", "A": candidates[0]["task"]["task_id"], "B": candidates[1]["task"]["task_id"], "files": files, "reference": reference_name})
        response_rows.append({"presentation_id": presentation_id, "task_type": "closer-to-reference-A-or-B", "answer": "", "confidence": "", "notes": ""})
    with (output / "responses.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("presentation_id", "task_type", "answer", "confidence", "notes"))
        writer.writeheader(); writer.writerows(response_rows)
    (output / "session-key.json").write_text(json.dumps({"seed": seed, "items": key_items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text("""# 知覚評価スイート

`session-key.json` は回答完了まで開かない。

- `Ixx`: 音声を聴き、聞こえた音素を `answer` に記入する。選択肢は `あ/い/う/え/お` または `し/す`。
- `Oxx`: A/Bのうち、`task_type` に示された属性がより強い方を `A` または `B` で記入する。
- `Axx`: referenceを聴いた後、referenceへより近い候補を `A` または `B` で記入する。
- confidenceは1〜5、notesは任意。同じ機器・音量を維持し、モデル条件を調べない。
""", encoding="utf-8")
    return {"presentations": len(response_rows), "identification": len(identification), "attribute_pairs": 2, "ab_pairs": int(bool(original and improved)), "output": str(output)}


def analyze_perceptual_suite(session: Path) -> dict[str, Any]:
    key_data = json.loads((session / "session-key.json").read_text(encoding="utf-8"))
    key = {item["presentation_id"]: item for item in key_data["items"]}
    with (session / "responses.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    errors, scored, confusion = [], [], {}
    for row in rows:
        item = key.get(row["presentation_id"])
        answer = (row.get("answer") or "").strip()
        if not item:
            errors.append(f"unknown presentation: {row['presentation_id']}")
            continue
        confidence_text = (row.get("confidence") or "").strip()
        if not answer:
            continue
        if confidence_text and not 1 <= float(confidence_text) <= 5:
            errors.append(f"{row['presentation_id']}: confidence must be 1..5")
        task_type = item["task_type"]
        correct = None
        if task_type in {"vowel-identification", "cv-identification"}:
            allowed = {"あ", "い", "う", "え", "お"} if task_type == "vowel-identification" else {"し", "す"}
            if answer not in allowed:
                errors.append(f"{row['presentation_id']}: answer must be one of {sorted(allowed)}")
                continue
            correct = answer == item["correct_label"]
            confusion.setdefault(item["correct_label"], {}).setdefault(answer, 0)
            confusion[item["correct_label"]][answer] += 1
        elif task_type == "attribute-order":
            if answer not in {"A", "B"}:
                errors.append(f"{row['presentation_id']}: answer must be A or B")
                continue
            correct = answer == item["correct_answer"]
        elif task_type == "ab-reference-similarity" and answer not in {"A", "B"}:
            errors.append(f"{row['presentation_id']}: answer must be A or B")
            continue
        selected_target = item.get(answer) if task_type == "ab-reference-similarity" else None
        scored.append({"presentation_id": row["presentation_id"], "task_type": task_type, "answer": answer, "selected_target": selected_target, "correct": correct, "confidence": float(confidence_text) if confidence_text else None})
    classifiable = [item for item in scored if item["correct"] is not None]
    return {"complete": len(scored) == len(key) and not errors, "answered": len(scored), "expected": len(key), "errors": errors, "classification_accuracy": sum(item["correct"] for item in classifiable) / len(classifiable) if classifiable else None, "confusion": confusion, "responses": scored}


def merge_listening_analyses(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    responses = [response for analysis in analyses for response in analysis.get("responses", [])]
    grouped: dict[str, list[dict[str, float]]] = {}
    for response in responses:
        if response.get("scores"):
            grouped.setdefault(response["task_id"], []).append(response["scores"])
    aggregates = {
        task_id: {axis: float(np.mean([scores[axis] for scores in scores_list if axis in scores])) for axis in sorted({axis for scores in scores_list for axis in scores})}
        for task_id, scores_list in grouped.items()
    }
    return {"responses": responses, "task_aggregates": aggregates, "source_analysis_count": len(analyses), "complete": all(analysis.get("complete", False) for analysis in analyses)}
