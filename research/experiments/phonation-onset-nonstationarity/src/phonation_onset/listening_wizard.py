from __future__ import annotations

import csv
import json
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import numpy as np

from .audio import normalize, sha256_file, write_audio, write_json


WIZARD_SCHEMA_VERSION = "1.0.0"
YES_INPUTS = {"y", "yes", "はい", "ハイ"}
NO_INPUTS = {"n", "no", "いいえ", "イイエ"}


QUESTION_TEXT = {
    "more_human": "どちらが、人が実際に声を出した音に近く聞こえますか",
    "more_natural_onset": "どちらの音の始まりが、より自然に聞こえますか",
    "more_natural_sustain": "どちらの持続部分が、より自然に聞こえますか",
}

REASON_TAGS = (
    "息っぽい", "掠れ", "機械的", "楽器的", "ループ感",
    "クリック・継ぎ目", "母音が違う", "音量差が気になる", "その他",
)


class Player(Protocol):
    name: str

    def play(self, path: Path) -> None: ...


@dataclass
class CommandPlayer:
    name: str
    prefix: tuple[str, ...]

    def play(self, path: Path) -> None:
        completed = subprocess.run([*self.prefix, str(path)], check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"{self.name} failed with exit code {completed.returncode}")


@dataclass
class FakePlayer:
    name: str = "fake-player"
    played: list[str] | None = None

    def play(self, path: Path) -> None:
        if self.played is not None:
            self.played.append(str(path))


class PauseRequested(Exception):
    pass


def detect_player(explicit: str | None = None) -> Player:
    candidates: list[tuple[str, tuple[str, ...]]]
    if explicit:
        executable = shutil.which(explicit)
        if not executable:
            raise RuntimeError(f"指定されたaudio playerが見つかりません: {explicit}")
        return CommandPlayer(explicit, (executable,))
    candidates = [
        ("afplay", ("afplay",)),
        ("ffplay", ("ffplay", "-nodisp", "-autoexit", "-loglevel", "error")),
        ("mpv", ("mpv", "--no-video", "--really-quiet")),
        ("aplay", ("aplay",)),
    ]
    for name, command in candidates:
        executable = shutil.which(command[0])
        if executable:
            return CommandPlayer(name, (executable, *command[1:]))
    raise RuntimeError("audio playerが見つかりません。macOSではafplay、その他ではffplay/mpv/aplayを用意してください。")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    write_json(temporary, payload)
    temporary.replace(path)


def parse_yes_no(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in YES_INPUTS:
        return True
    if normalized in NO_INPUTS:
        return False
    return None


def _comparison_question(question_id: str) -> dict[str, str]:
    return {"id": question_id, "kind": "comparison", "prompt": QUESTION_TEXT[question_id]}


def _side_question(question_id: str, prompt: str) -> dict[str, str]:
    return {"id": question_id, "kind": "side_yes_no", "prompt": prompt}


def question_route(row: dict[str, str]) -> list[dict[str, str]]:
    hypothesis = row["hypothesis"]
    pair_id = row["pair_id"]
    if hypothesis.startswith("vowel-generalization-"):
        vowel = hypothesis.removeprefix("vowel-generalization-")
        if vowel not in {"a", "i", "u", "e", "o"}:
            raise ValueError(f"未対応の目的母音です: {vowel}")
        return [
            _comparison_question("more_natural_onset"),
            _side_question("vowel_identity", f"この音は、目的の母音 /{vowel}/ として聞こえますか"),
            _side_question("human_voice_identity", "この音は、楽器音ではなく人の声として聞こえますか"),
        ]
    if hypothesis in {"H1", "H1-reaudit", "H1-external-reaudit", "H3"}:
        return [_comparison_question("more_human"), _comparison_question("more_natural_onset")]
    if hypothesis == "onset-secondary":
        return [
            _comparison_question("more_natural_onset"),
            _side_question("vowel_identity", "この音は、目的の母音 /a/ として聞こえますか"),
            _side_question("human_voice_identity", "この音は、楽器音ではなく人の声として聞こえますか"),
        ]
    if hypothesis.startswith("baseline-"):
        return [
            _comparison_question("more_human"),
            _side_question("vowel_identity", "この音は、目的の母音 /a/ として聞こえますか"),
            _side_question("human_voice_identity", "この音は、楽器音ではなく人の声として聞こえますか"),
        ]
    if hypothesis == "H4":
        return [_comparison_question("more_human"), _comparison_question("more_natural_sustain")]
    if hypothesis == "H5":
        return [
            _comparison_question("more_natural_onset"),
            _side_question("vowel_identity", "この音は、目的の母音として自然に聞こえますか"),
        ]
    if hypothesis == "H6":
        return [_comparison_question("more_natural_sustain"), _comparison_question("more_human")]
    if hypothesis == "control" or "original-vs-shortened" in pair_id:
        return [_comparison_question("more_human")]
    return [_comparison_question("more_human")]


def _select_duplicate_pairs(rows: list[dict[str, str]], rng: random.Random) -> list[str]:
    selected: list[str] = []
    predicates = (
        lambda row: row["hypothesis"] == "H1",
        lambda row: row["hypothesis"] == "H6",
        lambda row: row["hypothesis"] == "H4" and not row["pair_id"].startswith("synthetic--"),
        lambda row: row["pair_id"].startswith("synthetic--"),
    )
    for predicate in predicates:
        choices = [row["pair_id"] for row in rows if predicate(row) and row["pair_id"] not in selected]
        if choices:
            selected.append(rng.choice(choices))
    for row in rows:
        if len(selected) >= 4:
            break
        if row["pair_id"] not in selected:
            selected.append(row["pair_id"])
    return selected[:4]


def _schedule(
    rows: list[dict[str, Any]],
    duplicate_pair_ids: list[str],
    rng: random.Random,
    minimum_separation: int = 5,
) -> list[tuple[dict[str, Any], bool]]:
    by_pair = {row["pair_id"]: row for row in rows}
    entries = [(row, False) for row in rows] + [(by_pair[pair_id], True) for pair_id in duplicate_pair_ids]
    for _ in range(20000):
        candidate = entries.copy()
        rng.shuffle(candidate)
        positions: dict[str, list[int]] = {}
        for index, (row, _) in enumerate(candidate):
            positions.setdefault(row["pair_id"], []).append(index)
        if all(len(indices) == 1 or indices[1] - indices[0] >= minimum_separation for indices in positions.values()):
            return candidate
    raise RuntimeError("重複提示を十分に離した順序を生成できませんでした")


def _calibration_audio(sample_rate: int = 48000) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    time_axis = np.arange(sample_rate, dtype=float) / sample_rate
    envelope = np.minimum(1.0, time_axis / 0.04) * np.minimum(1.0, (1.0 - time_axis) / 0.08)
    harmonic = sum(np.sin(2.0 * np.pi * 180.0 * harmonic_index * time_axis) / harmonic_index for harmonic_index in range(1, 8))
    rng = np.random.default_rng(20260825)
    noise = rng.standard_normal(sample_rate)
    smoothed = np.convolve(noise, np.ones(9) / 9.0, mode="same")
    calibration = normalize(envelope * (harmonic + 0.025 * smoothed), -23.0)
    practice_a = calibration * 0.32
    practice_b = calibration * 0.9
    return calibration, practice_a, practice_b


def prepare_wizard_session(legacy_session: Path, output_session: Path, seed: int = 20260914) -> dict[str, Any]:
    legacy_session = legacy_session.resolve()
    output_session = output_session.resolve()
    if output_session.exists():
        raise FileExistsError(f"出力先がすでに存在します。既存セッションは上書きしません: {output_session}")
    key_path = legacy_session / "presentation-key.csv"
    lock_path = legacy_session / "lock.json"
    responses_path = legacy_session / "responses.csv"
    if not all(path.is_file() for path in (key_path, lock_path, responses_path)):
        raise FileNotFoundError("旧チェックポイントに必要なkey、lock、responsesがありません")
    with key_path.open(newline="", encoding="utf-8") as handle:
        legacy_rows = list(csv.DictReader(handle))
    with responses_path.open(newline="", encoding="utf-8") as handle:
        legacy_responses = list(csv.DictReader(handle))
    if any(any((value or "").strip() for key, value in row.items() if key != "presentation_id") for row in legacy_responses):
        raise RuntimeError("旧チェックポイントには回答があります。未回答移行として処理できません")
    unique_rows = [row for row in legacy_rows if not row.get("duplicate_of")]
    if len(unique_rows) != 13:
        raise RuntimeError(f"13ユニーク比較を期待しましたが{len(unique_rows)}件でした")

    rng = random.Random(seed)
    duplicate_pair_ids = _select_duplicate_pairs(unique_rows, rng)
    scheduled = _schedule(unique_rows, duplicate_pair_ids, rng)
    audio_dir = output_session / "audio"
    calibration_dir = output_session / "calibration"
    audio_dir.mkdir(parents=True)
    calibration_dir.mkdir(parents=True)

    blinded_presentations: list[dict[str, Any]] = []
    private_presentations: list[dict[str, Any]] = []
    audio_hashes: dict[str, str] = {}
    for index, (row, duplicate) in enumerate(scheduled, 1):
        presentation_id = f"W{index:02d}"
        source_candidates = [
            {
                "legacy_side": "A", "condition": row["a_condition"], "stimulus_id": row["a_stimulus_id"],
                "path": legacy_session / "audio" / f"{row['presentation_id']}-A.wav",
            },
            {
                "legacy_side": "B", "condition": row["b_condition"], "stimulus_id": row["b_stimulus_id"],
                "path": legacy_session / "audio" / f"{row['presentation_id']}-B.wav",
            },
        ]
        if rng.random() < 0.5:
            source_candidates.reverse()
        private_row: dict[str, Any] = {
            "presentation_id": presentation_id,
            "pair_id": row["pair_id"],
            "hypothesis": row["hypothesis"],
            "duplicate_of": row["pair_id"] if duplicate else None,
            "questions": question_route(row),
        }
        audio_files: dict[str, str] = {}
        for side, candidate in zip(("A", "B"), source_candidates, strict=True):
            if not candidate["path"].is_file():
                raise FileNotFoundError(candidate["path"])
            destination = audio_dir / f"{presentation_id}-{side}.wav"
            shutil.copy2(candidate["path"], destination)
            digest = sha256_file(destination)
            audio_files[side] = str(destination.relative_to(output_session))
            audio_hashes[str(destination.relative_to(output_session))] = digest
            private_row[side] = {
                "condition": candidate["condition"], "stimulus_id": candidate["stimulus_id"], "sha256": digest,
            }
        blinded_presentations.append({
            "presentation_id": presentation_id,
            "audio": audio_files,
            "questions": question_route(row),
        })
        private_presentations.append(private_row)

    calibration, practice_a, practice_b = _calibration_audio()
    calibration_path = calibration_dir / "volume-check.wav"
    practice_a_path = calibration_dir / "practice-A.wav"
    practice_b_path = calibration_dir / "practice-B.wav"
    write_audio(calibration_path, 48000, calibration)
    write_audio(practice_a_path, 48000, practice_a)
    write_audio(practice_b_path, 48000, practice_b)
    for path in (calibration_path, practice_a_path, practice_b_path):
        audio_hashes[str(path.relative_to(output_session))] = sha256_file(path)

    blinded = {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "session_id": output_session.name,
        "presentation_count": len(blinded_presentations),
        "break_every_presentations": 5,
        "calibration_audio": str(calibration_path.relative_to(output_session)),
        "practice_audio": {"A": str(practice_a_path.relative_to(output_session)), "B": str(practice_b_path.relative_to(output_session))},
        "presentations": blinded_presentations,
    }
    private = {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "session_id": output_session.name,
        "source_session": str(legacy_session),
        "seed": seed,
        "duplicate_pair_ids": duplicate_pair_ids,
        "presentations": private_presentations,
    }
    blinded_path = output_session / "blinded-session.json"
    private_path = output_session / "private-session-key.json"
    write_json(blinded_path, blinded)
    write_json(private_path, private)
    lock = {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "status": "frozen-awaiting-listening",
        "session_id": output_session.name,
        "seed": seed,
        "presentation_count": len(blinded_presentations),
        "unique_pair_count": len(unique_rows),
        "duplicate_count": len(duplicate_pair_ids),
        "files": {
            "blinded-session.json": sha256_file(blinded_path),
            "private-session-key.json": sha256_file(private_path),
        },
        "audio": audio_hashes,
        "holdout_opened": False,
    }
    write_json(output_session / "lock.json", lock)
    write_json(output_session / "migration.json", {
        "status": "supersedes-unanswered-presentation-method",
        "source_session": str(legacy_session),
        "source_lock_sha256": sha256_file(lock_path),
        "source_key_sha256": sha256_file(key_path),
        "source_responses_sha256": sha256_file(responses_path),
        "candidate_audio_unchanged": True,
        "reason": "CLIウィザード、二択質問、非隣接重複、自動保存へ移行するため",
    })
    (output_session / "README.md").write_text(
        "# 第1試聴 CLIウィザードセッション\n\n"
        "このセッションは未回答の旧チェックポイントと同じ13比較を、操作しやすいCLIウィザード用に再配置したものです。\n\n"
        "```bash\n"
        "research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py listen\n"
        "```\n\n"
        "音量確認、練習、本番、保存、再開はウィザードが案内します。音声ファイルやresponses.csvを手動で開く必要はありません。\n",
        encoding="utf-8",
    )
    return {"session": str(output_session), "presentations": len(blinded_presentations), "duplicates": len(duplicate_pair_ids)}


def prepare_candidate_wizard_session(
    pairs: list[dict[str, Any]],
    output_session: Path,
    seed: int,
    duplicate_pair_ids: list[str],
    provenance: dict[str, Any] | None = None,
    duplicate_minimum_separation: int = 5,
) -> dict[str, Any]:
    """新規候補ペアから、既存ウィザードと互換の凍結セッションを作る。"""
    output_session = output_session.resolve()
    if output_session.exists():
        raise FileExistsError(f"出力先がすでに存在します。既存セッションは上書きしません: {output_session}")
    if not pairs or len({pair["pair_id"] for pair in pairs}) != len(pairs):
        raise ValueError("pair_idは空でなく、一意である必要があります")
    known_pair_ids = {pair["pair_id"] for pair in pairs}
    if len(set(duplicate_pair_ids)) != len(duplicate_pair_ids) or not set(duplicate_pair_ids) <= known_pair_ids:
        raise ValueError("duplicate_pair_idsは一意な既存pair_idである必要があります")

    rng = random.Random(seed)
    scheduled = _schedule(pairs, duplicate_pair_ids, rng, duplicate_minimum_separation)
    audio_dir = output_session / "audio"
    calibration_dir = output_session / "calibration"
    audio_dir.mkdir(parents=True)
    calibration_dir.mkdir(parents=True)
    blinded_presentations: list[dict[str, Any]] = []
    private_presentations: list[dict[str, Any]] = []
    audio_hashes: dict[str, str] = {}

    for index, (pair, duplicate) in enumerate(scheduled, 1):
        presentation_id = f"W{index:02d}"
        candidates = [dict(pair["left"]), dict(pair["right"])]
        if rng.random() < 0.5:
            candidates.reverse()
        questions = question_route({"hypothesis": pair["hypothesis"], "pair_id": pair["pair_id"]})
        private_row: dict[str, Any] = {
            "presentation_id": presentation_id,
            "pair_id": pair["pair_id"],
            "hypothesis": pair["hypothesis"],
            "duplicate_of": pair["pair_id"] if duplicate else None,
            "questions": questions,
        }
        audio_files: dict[str, str] = {}
        for side, candidate in zip(("A", "B"), candidates, strict=True):
            source = Path(candidate["path"]).resolve()
            if not source.is_file():
                raise FileNotFoundError(source)
            destination = audio_dir / f"{presentation_id}-{side}.wav"
            shutil.copy2(source, destination)
            digest = sha256_file(destination)
            relative = str(destination.relative_to(output_session))
            audio_files[side] = relative
            audio_hashes[relative] = digest
            private_row[side] = {
                "condition": candidate["condition"],
                "stimulus_id": candidate["stimulus_id"],
                "sha256": digest,
            }
        blinded_presentations.append({
            "presentation_id": presentation_id,
            "audio": audio_files,
            "questions": questions,
        })
        private_presentations.append(private_row)

    calibration, practice_a, practice_b = _calibration_audio()
    for filename, value in (
        ("volume-check.wav", calibration),
        ("practice-A.wav", practice_a),
        ("practice-B.wav", practice_b),
    ):
        path = calibration_dir / filename
        write_audio(path, 48000, value)
        audio_hashes[str(path.relative_to(output_session))] = sha256_file(path)

    blinded = {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "session_id": output_session.name,
        "presentation_count": len(blinded_presentations),
        "break_every_presentations": 5,
        "calibration_audio": "calibration/volume-check.wav",
        "practice_audio": {"A": "calibration/practice-A.wav", "B": "calibration/practice-B.wav"},
        "presentations": blinded_presentations,
    }
    private = {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "session_id": output_session.name,
        "seed": seed,
        "duplicate_pair_ids": duplicate_pair_ids,
        "provenance": provenance or {},
        "presentations": private_presentations,
    }
    blinded_path = output_session / "blinded-session.json"
    private_path = output_session / "private-session-key.json"
    write_json(blinded_path, blinded)
    write_json(private_path, private)
    write_json(output_session / "lock.json", {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "status": "frozen-awaiting-listening",
        "session_id": output_session.name,
        "seed": seed,
        "presentation_count": len(blinded_presentations),
        "unique_pair_count": len(pairs),
        "duplicate_count": len(duplicate_pair_ids),
        "duplicate_minimum_separation": duplicate_minimum_separation,
        "files": {
            "blinded-session.json": sha256_file(blinded_path),
            "private-session-key.json": sha256_file(private_path),
        },
        "audio": audio_hashes,
        "holdout_opened": False,
    })
    (output_session / "README.md").write_text(
        "# ブラインド試聴CLIウィザード\n\n"
        "候補と比較を凍結したブラインドセッションです。条件名や重複位置は本番中に表示されません。\n",
        encoding="utf-8",
    )
    return {
        "session": str(output_session),
        "presentations": len(blinded_presentations),
        "unique_pairs": len(pairs),
        "duplicates": len(duplicate_pair_ids),
    }


class ListeningWizard:
    def __init__(
        self,
        session: Path,
        player: Player,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self.session = session.resolve()
        self.player = player
        self.input = input_fn
        self.output = output_fn
        self.blinded = json.loads((self.session / "blinded-session.json").read_text(encoding="utf-8"))
        self.lock = json.loads((self.session / "lock.json").read_text(encoding="utf-8"))
        self.progress_path = self.session / "progress.json"
        self.events_path = self.session / "events.jsonl"
        self.progress = self._load_progress()
        self._active_presentation: str | None = None

    def _load_progress(self) -> dict[str, Any]:
        lock_digest = sha256_file(self.session / "lock.json")
        if self.progress_path.is_file():
            progress = json.loads(self.progress_path.read_text(encoding="utf-8"))
            if progress.get("lock_sha256") != lock_digest:
                raise RuntimeError("session lockが変わっているため、既存progressを再開できません")
            return progress
        return {
            "schema_version": WIZARD_SCHEMA_VERSION,
            "session_id": self.blinded["session_id"],
            "lock_sha256": lock_digest,
            "calibration_complete": False,
            "practice_complete": False,
            "current_index": 0,
            "runtime_order": [item["presentation_id"] for item in self.blinded["presentations"]],
            "retry_counts": {},
            "attempts": {},
            "drafts": {},
            "playback_counts": {},
            "completed": False,
        }

    def verify(self) -> None:
        if self.blinded.get("schema_version") != WIZARD_SCHEMA_VERSION:
            raise RuntimeError("未対応のwizard session schemaです")
        for relative, expected in self.lock.get("files", {}).items():
            path = self.session / relative
            if not path.is_file() or sha256_file(path) != expected:
                raise RuntimeError(f"locked fileが変更または欠損しています: {relative}")
        for relative, expected in self.lock.get("audio", {}).items():
            path = self.session / relative
            if not path.is_file() or sha256_file(path) != expected:
                raise RuntimeError(f"locked audioが変更または欠損しています: {relative}")
        blinded_text = json.dumps(self.blinded, ensure_ascii=False)
        for forbidden in ("hypothesis", "pair_id", "condition", "duplicate_of", "stimulus_id"):
            if forbidden in blinded_text:
                raise RuntimeError(f"blinded sessionに非公開情報が含まれています: {forbidden}")

    def _event(self, event: str, **payload: Any) -> None:
        record = {"timestamp": _now(), "event": event, **payload}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _save(self) -> None:
        _atomic_json(self.progress_path, self.progress)

    def _pause(self, message: str) -> None:
        self.output(message)
        self._event("paused", reason=message)
        self._save()
        raise PauseRequested

    def _ask_yes_no(self, prompt: str, playback: dict[str, Path] | None = None) -> bool:
        while True:
            suffix = " [y/n/q]" if playback is None else " [y/n/a/b/p/r/q]"
            answer = self.input(prompt + suffix + " ")
            parsed = parse_yes_no(answer)
            if parsed is not None:
                return parsed
            normalized = answer.strip().lower()
            if normalized == "q":
                self._pause("回答を保存して中断しました。次回は続きから再開できます。")
            if playback and normalized in {"a", "b", "p", "r"}:
                self._play(normalized, playback)
                continue
            self.output("`y`（はい）または `n`（いいえ）で答えてください。日本語の「はい」「いいえ」も使えます。")

    def _ask_ab(self, prompt: str, playback: dict[str, Path]) -> str:
        while True:
            answer = self.input(prompt + " [1=A / 2=B / a/b/p/r/q] ").strip().lower()
            if answer in {"1", "a-choice"}:
                return "A"
            if answer in {"2", "b-choice"}:
                return "B"
            if answer == "q":
                self._pause("回答を保存して中断しました。次回は続きから再開できます。")
            if answer in {"a", "b", "p", "r"}:
                self._play(answer, playback)
                continue
            self.output("`1`でA、`2`でBを選んでください。音を聞く場合は`a`、`b`、`p`を使えます。")

    def _play(self, action: str, audio: dict[str, Path]) -> None:
        if action == "r":
            action = str(self.progress.get("last_play_action") or "p")
        try:
            if action == "p":
                self.output("Aを再生します。")
                self.player.play(audio["A"])
                time.sleep(0.2)
                self.output("Bを再生します。")
                self.player.play(audio["B"])
            else:
                side = action.upper()
                self.output(f"{side}を再生します。")
                self.player.play(audio[side])
            self.progress["last_play_action"] = action
            total_count = None
            if self._active_presentation:
                counts = self.progress.setdefault("playback_counts", {}).setdefault(self._active_presentation, {})
                counts[action] = int(counts.get(action, 0)) + 1
                total_count = sum(int(value) for value in counts.values())
                if total_count == 8:
                    self.output("8回再生しました。判断が難しい場合は、休憩やUNSUREを選んでも問題ありません。")
            self._event(
                "audio_played", action=action, player=self.player.name,
                presentation_id=self._active_presentation, presentation_play_count=total_count,
            )
            self._save()
        except Exception as error:
            self._event("player_error", action=action, player=self.player.name, error=str(error))
            raise RuntimeError(f"音声を再生できませんでした: {error}") from error

    def _ready_to_answer(self, audio: dict[str, Path]) -> None:
        self.output("  [a] Aを聞く  [b] Bを聞く  [p] A→B  [r] もう一度  [c] 回答へ  [q] 中断")
        while True:
            action = self.input("操作を選んでください: ").strip().lower()
            if action == "c":
                return
            if action == "q":
                self._pause("回答を保存して中断しました。次回は続きから再開できます。")
            if action in {"a", "b", "p", "r"}:
                self._play(action, audio)
                continue
            self.output("`a`、`b`、`p`で再生し、準備ができたら`c`を入力してください。")

    def _comparison(self, question: dict[str, str], audio: dict[str, Path]) -> str:
        self.output("\n評価すること:")
        self.output(f"「{question['prompt']}」")
        difference = self._ask_yes_no("この観点で、AとBに差を感じましたか?", audio)
        if difference:
            return self._ask_ab("より当てはまるのはどちらですか?", audio)
        same = self._ask_yes_no("AとBは、同じくらいだと思いますか?", audio)
        return "SAME" if same else "UNSURE"

    def _side_answers(self, prompt: str, audio: dict[str, Path]) -> dict[str, bool]:
        return {
            "A": self._ask_yes_no(f"Aについて: {prompt}", audio),
            "B": self._ask_yes_no(f"Bについて: {prompt}", audio),
        }

    def _reason_tags(self) -> list[str]:
        self.output("理由タグ（任意、複数はカンマ区切り、Enterで省略）:")
        for index, tag in enumerate(REASON_TAGS, 1):
            self.output(f"  {index}. {tag}")
        while True:
            answer = self.input("番号: ").strip()
            if not answer:
                return []
            try:
                indices = [int(item.strip()) for item in answer.split(",")]
            except ValueError:
                self.output("番号を入力してください。例: 1,4")
                continue
            if all(1 <= index <= len(REASON_TAGS) for index in indices):
                return [REASON_TAGS[index - 1] for index in dict.fromkeys(indices)]
            self.output(f"1〜{len(REASON_TAGS)}の番号を入力してください。")

    def _calibrate(self) -> None:
        if self.progress["calibration_complete"]:
            same_device = self._ask_yes_no("前回と同じ再生機器と音量ですか?")
            if same_device:
                return
            self.output("音量確認をやり直します。")
            self.progress["calibration_complete"] = False
        self.output("\nまず再生環境と音量を確認します。これは聴力検査ではありません。")
        if not self._ask_yes_no("静かな環境ですか?"):
            self._pause("静かな環境で再開してください。")
        if not self._ask_yes_no("同じ再生機器を最後まで使えますか?"):
            self._pause("同じ再生機器を使えるときに再開してください。")
        while not self._ask_yes_no("システム音量を低めにしましたか?"):
            self.output("音量を低めにしてから続けてください。")
        calibration = self.session / self.blinded["calibration_audio"]
        while True:
            self.output("校正音を再生します。")
            self.player.play(calibration)
            self._event("calibration_played", player=self.player.name)
            audible = self._ask_yes_no("音は明瞭に聞こえましたか?")
            comfortable = self._ask_yes_no("大きすぎず、快適ですか?") if audible else False
            if audible and comfortable:
                break
            self.output("音量を安全で快適な範囲に調整して、もう一度確認します。")
        self.progress["calibration_complete"] = True
        self._event("calibration_completed", player=self.player.name)
        self._save()

    def _practice(self) -> None:
        if self.progress["practice_complete"]:
            return
        self.output("\n操作練習です。この回答は研究結果に含まれません。")
        audio = {side: self.session / path for side, path in self.blinded["practice_audio"].items()}
        self._active_presentation = "practice"
        while True:
            self._ready_to_answer(audio)
            selected = self._ask_ab("練習: より大きく聞こえるのはどちらですか?", audio)
            if selected == "B":
                break
            self.output("この練習ではBが明確に大きくなるよう作られています。再生操作をもう一度確認します。")
        self.output("練習は完了です。本番では正解はなく、判断できないと答えても問題ありません。")
        self._active_presentation = None
        self.progress["practice_complete"] = True
        self._event("practice_completed")
        self._save()

    def _trial(self, item: dict[str, Any], position: int, total: int) -> dict[str, Any]:
        audio = {side: self.session / path for side, path in item["audio"].items()}
        self._active_presentation = item["presentation_id"]
        while True:
            self.output(f"\n提示 {position} / {total}")
            self._ready_to_answer(audio)
            drafts = self.progress.setdefault("drafts", {})
            draft = drafts.setdefault(item["presentation_id"], {"answers": {}, "artifact": {}})
            answers: dict[str, Any] = draft["answers"]
            if answers or draft["artifact"]:
                self.output("この提示は保存済みの途中回答から続けます。")
            for question in item["questions"]:
                if question["id"] in answers:
                    continue
                if question["kind"] == "comparison":
                    answers[question["id"]] = self._comparison(question, audio)
                else:
                    answers[question["id"]] = self._side_answers(question["prompt"], audio)
                self._save()
            artifact = draft["artifact"]
            for side in ("A", "B"):
                if side not in artifact:
                    artifact[side] = self._ask_yes_no(
                        f"{side}について: クリック・継ぎ目・不自然なノイズなどの加工違和感がありましたか?",
                        audio,
                    )
                    self._save()
            if "interference" not in draft:
                draft["interference"] = self._ask_yes_no("外の音、音切れ、操作ミスなど、判断を妨げることがありましたか?")
                self._save()
            interference = bool(draft["interference"])
            difficult = any(value == "UNSURE" for value in answers.values() if isinstance(value, str))
            if "reason_tags" not in draft:
                draft["reason_tags"] = self._reason_tags() if difficult or any(artifact.values()) or interference else []
                self._save()
            tags = list(draft["reason_tags"])
            self.output("\n回答を保存する前に確認します。")
            for question in item["questions"]:
                self.output(f"  {question['prompt']}: {answers[question['id']]}")
            self.output(f"  Aの加工違和感: {'あり' if artifact['A'] else 'なし'}")
            self.output(f"  Bの加工違和感: {'あり' if artifact['B'] else 'なし'}")
            self.output(f"  外乱: {'あり' if interference else 'なし'}")
            if self._ask_yes_no("この回答で次へ進みますか?"):
                return {
                    "presentation_id": item["presentation_id"],
                    "answers": answers,
                    "artifact": artifact,
                    "interference": interference,
                    "reason_tags": tags,
                    "completed_at": _now(),
                }
            self.output("この提示を最初から回答し直します。")
            self._event("trial_restarted", presentation_id=item["presentation_id"])
            drafts[item["presentation_id"]] = {"answers": {}, "artifact": {}}
            self._save()

    def _write_results(self) -> None:
        payload = {
            "schema_version": WIZARD_SCHEMA_VERSION,
            "session_id": self.blinded["session_id"],
            "completed_at": _now(),
            "attempts": self.progress["attempts"],
            "playback_counts": self.progress.get("playback_counts", {}),
        }
        _atomic_json(self.session / "responses.json", payload)
        rows: list[dict[str, str]] = []
        for presentation_id in [item["presentation_id"] for item in self.blinded["presentations"]]:
            attempts = self.progress["attempts"].get(presentation_id, [])
            valid = next((attempt for attempt in reversed(attempts) if not attempt["interference"]), attempts[-1] if attempts else None)
            if not valid:
                continue
            answers = valid["answers"]
            rows.append({
                "presentation_id": presentation_id,
                "more_human": str(answers.get("more_human", "")),
                "more_natural_onset": str(answers.get("more_natural_onset", "")),
                "more_natural_sustain": str(answers.get("more_natural_sustain", "")),
                "vowel_identity_a": str(answers.get("vowel_identity", {}).get("A", "")),
                "vowel_identity_b": str(answers.get("vowel_identity", {}).get("B", "")),
                "artifact_a": str(valid["artifact"]["A"]),
                "artifact_b": str(valid["artifact"]["B"]),
                "interference": str(valid["interference"]),
                "reason_tags": "|".join(valid["reason_tags"]),
            })
        csv_path = self.session / "responses.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["presentation_id"])
            writer.writeheader()
            writer.writerows(rows)
        completion = {
            "schema_version": WIZARD_SCHEMA_VERSION,
            "session_id": self.blinded["session_id"],
            "presentation_count": len(self.blinded["presentations"]),
            "response_count": len(rows),
            "complete": len(rows) == len(self.blinded["presentations"]),
            "responses_sha256": sha256_file(self.session / "responses.json"),
            "csv_sha256": sha256_file(csv_path),
        }
        write_json(self.session / "completion.json", completion)

    def run(self, check_only: bool = False) -> int:
        self.verify()
        self._event("wizard_started", player=self.player.name, check_only=check_only)
        self.output("Voice Simulator ブラインド試聴")
        self.output("条件名や正解は表示されません。音は何度でも聞けます。")
        try:
            self._calibrate()
            self._practice()
            if check_only:
                self.output("音量確認と操作練習が完了しました。本番回答は保存していません。")
                self._event("check_only_completed")
                return 0
            presentations = {item["presentation_id"]: item for item in self.blinded["presentations"]}
            while self.progress["current_index"] < len(self.progress["runtime_order"]):
                index = int(self.progress["current_index"])
                presentation_id = self.progress["runtime_order"][index]
                item = presentations[presentation_id]
                attempt = self._trial(item, index + 1, len(self.progress["runtime_order"]))
                self.progress["attempts"].setdefault(presentation_id, []).append(attempt)
                self.progress.setdefault("drafts", {}).pop(presentation_id, None)
                if attempt["interference"] and int(self.progress["retry_counts"].get(presentation_id, 0)) < 1:
                    self.progress["runtime_order"].append(presentation_id)
                    self.progress["retry_counts"][presentation_id] = 1
                    self.output("外乱があったため、この提示は後でもう一度だけ確認します。")
                self.progress["current_index"] = index + 1
                self._event("trial_completed", presentation_id=presentation_id, interference=attempt["interference"])
                self._save()
                break_every = int(self.blinded.get("break_every_presentations", 5))
                if self.progress["current_index"] < len(self.progress["runtime_order"]) and self.progress["current_index"] % break_every == 0:
                    if self._ask_yes_no("ここで休憩しますか?"):
                        answer = self.input("休憩してください。再開するにはEnter、保存して終了するにはq: ").strip().lower()
                        if answer == "q":
                            self._pause("回答を保存して中断しました。次回は続きから再開できます。")
                        self._event("break_completed")
            self.progress["completed"] = True
            self._save()
            self._write_results()
            self._event("wizard_completed")
            self.output(f"試聴は完了しました。{len(self.blinded['presentations'])}提示の回答を保存しました。")
            self.output("結果は別のanalyze-listeningコマンドで確認できます。")
            return 0
        except PauseRequested:
            return 0


def analyze_wizard_session(session: Path) -> dict[str, Any]:
    session = session.resolve()
    lock = json.loads((session / "lock.json").read_text(encoding="utf-8"))
    private = json.loads((session / "private-session-key.json").read_text(encoding="utf-8"))
    responses = json.loads((session / "responses.json").read_text(encoding="utf-8"))
    for relative, expected in lock.get("files", {}).items():
        path = session / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"locked fileが変更または欠損しています: {relative}")
    for relative, expected in lock.get("audio", {}).items():
        path = session / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"locked audioが変更または欠損しています: {relative}")

    attempts_by_id = responses["attempts"]
    combined: list[dict[str, Any]] = []
    errors: list[str] = []
    for key in private["presentations"]:
        attempts = attempts_by_id.get(key["presentation_id"], [])
        clean = next((attempt for attempt in reversed(attempts) if not attempt.get("interference")), None)
        if clean is None:
            errors.append(f"{key['presentation_id']}: 外乱のない有効回答がありません")
            continue
        combined.append({**key, "response": clean, "attempt_count": len(attempts)})
    if errors:
        raise ValueError("; ".join(errors))

    def selected(row: dict[str, Any], question_id: str) -> str | dict[str, bool] | None:
        value = row["response"]["answers"].get(question_id)
        if isinstance(value, str) and value in {"A", "B"}:
            return row[value]["condition"]
        if isinstance(value, dict) and set(value) <= {"A", "B"}:
            return {row[side]["condition"]: bool(answer) for side, answer in value.items()}
        return value

    by_pair: dict[str, list[dict[str, Any]]] = {}
    for row in combined:
        by_pair.setdefault(row["pair_id"], []).append(row)
    consistency: list[dict[str, Any]] = []
    for pair_id, rows in by_pair.items():
        if len(rows) < 2:
            continue
        shared_questions = set(rows[0]["response"]["answers"]) & set(rows[1]["response"]["answers"])
        for question_id in sorted(shared_questions):
            consistency.append({
                "pair_id": pair_id,
                "axis": question_id,
                "first": selected(rows[0], question_id),
                "second": selected(rows[1], question_id),
                "consistent": selected(rows[0], question_id) == selected(rows[1], question_id),
            })

    hypotheses: dict[str, dict[str, Any]] = {}
    for row in combined:
        if row.get("duplicate_of"):
            continue
        mapped_answers = {question["id"]: selected(row, question["id"]) for question in row["questions"]}
        artifact_conditions = [row[side]["condition"] for side in ("A", "B") if row["response"]["artifact"][side]]
        hypotheses.setdefault(row["hypothesis"], {"comparisons": []})["comparisons"].append({
            "pair_id": row["pair_id"],
            "answers": mapped_answers,
            "artifact_conditions": artifact_conditions,
            "reason_tags": row["response"].get("reason_tags", []),
            "attempt_count": row["attempt_count"],
            "playback_counts": responses.get("playback_counts", {}).get(row["presentation_id"], {}),
        })
    unsure_count = sum(
        value == "UNSURE"
        for row in combined
        for value in row["response"]["answers"].values()
        if isinstance(value, str)
    )
    comparison_count = sum(
        1
        for row in combined
        for value in row["response"]["answers"].values()
        if isinstance(value, str)
    )
    return {
        "schema_version": WIZARD_SCHEMA_VERSION,
        "status": "checkpoint-analyzed",
        "session": str(session),
        "response_sha256": sha256_file(session / "responses.json"),
        "private_key_sha256": sha256_file(session / "private-session-key.json"),
        "presentation_count": len(combined),
        "unsure_rate": unsure_count / max(1, comparison_count),
        "playback_counts": responses.get("playback_counts", {}),
        "duplicate_consistency": consistency,
        "duplicate_consistency_rate": sum(item["consistent"] for item in consistency) / max(1, len(consistency)),
        "hypotheses": hypotheses,
        "holdout_opened": False,
    }
