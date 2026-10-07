from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .io import sha256_file


SELECTED_CANDIDATES = ("structured-04", "random-27", "structured-01", "random-13")
ANCHOR = "structured-00"
PACKAGE_SEED = 5401
STIMULUS_F0_HZ = 220
STIMULUS_SEED_OFFSET = 1701


def freeze_listening_package(robustness: dict[str, Any], robustness_dir: Path) -> dict[str, Any]:
    records = {
        row["candidate_id"]: row
        for row in robustness["records"]
        if int(row["f0_hz"]) == STIMULUS_F0_HZ and int(row["seed_offset"]) == STIMULUS_SEED_OFFSET
    }
    needed = {ANCHOR, *SELECTED_CANDIDATES}
    missing = sorted(needed - records.keys())
    if missing:
        raise ValueError(f"A5に必要なA4音声がありません: {missing}")
    for candidate_id in sorted(needed):
        path = robustness_dir / records[candidate_id]["relative_audio_path"]
        if not path.is_file() or sha256_file(path) != records[candidate_id]["wav_sha256"]:
            raise ValueError(f"A5音声hashを検証できません: {candidate_id}")
    logical_pairs = [
        {"pair_id": f"candidate-{index + 1}-vs-anchor", "left": candidate, "right": ANCHOR, "duplicate_of": None}
        for index, candidate in enumerate(SELECTED_CANDIDATES)
    ]
    logical_pairs.extend([
        {"pair_id": "hidden-duplicate", "left": "structured-04", "right": ANCHOR, "duplicate_of": "candidate-1-vs-anchor"},
        {"pair_id": "boundary-contrast", "left": "structured-04", "right": "random-27", "duplicate_of": None},
    ])
    rng = random.Random(PACKAGE_SEED)
    rng.shuffle(logical_pairs)
    presentations = []
    for index, pair in enumerate(logical_pairs, start=1):
        left, right = pair["left"], pair["right"]
        if rng.choice((False, True)):
            left, right = right, left
        presentations.append({
            "presentation_id": f"P{index:02d}",
            "pair_id": pair["pair_id"],
            "duplicate_of": pair["duplicate_of"],
            "a": _stimulus(records[left], robustness_dir),
            "b": _stimulus(records[right], robustness_dir),
        })
    return {
        "schema_version": "1.0.0",
        "package_id": "avs-a220-search-v1-listening-v1",
        "source_campaign_id": robustness["campaign_id"],
        "status": "not_queued",
        "queue_reason": "single-listener longitudinal adoption-confirmation session is active",
        "listener_scope": "single listener; exploratory calibration only",
        "random_seed": PACKAGE_SEED,
        "selected_candidate_ids": list(SELECTED_CANDIDATES),
        "anchor_candidate_id": ANCHOR,
        "presentation_count": len(presentations),
        "playback_policy": "A, B, and pair playback may be repeated without a fixed limit",
        "answer_contract": {
            "binary": ["y", "yes", "n", "no"],
            "relative": ["a", "b", "same", "unsure"],
            "questions": [
                "Aは明瞭な母音「あ」に聞こえるか (y/n)",
                "Bは明瞭な母音「あ」に聞こえるか (y/n)",
                "Aは人の声らしく聞こえるか (y/n)",
                "Bは人の声らしく聞こえるか (y/n)",
                "どちらがより人間の母音「あ」に近いか (a/b/same/unsure)"
            ]
        },
        "presentations": presentations,
        "perceptual_claim_allowed_before_answer": False,
    }


def _stimulus(record: dict[str, Any], robustness_dir: Path) -> dict[str, Any]:
    return {
        "candidate_id": record["candidate_id"],
        "source_audio_path": str(robustness_dir / record["relative_audio_path"]),
        "wav_sha256": record["wav_sha256"],
        "f0_hz": record["f0_hz"],
        "seed_offset": record["seed_offset"],
    }


def markdown_readme(package: dict[str, Any]) -> str:
    return "\n".join([
        "# A5 探索用試聴package",
        "",
        f"状態: `{package['status']}`",
        "",
        "4候補、B9アンカー、隠し重複を含む6提示を固定した。現在は既存の別日反復試聴が有効なため開始しない。",
        "",
        "開始時は最初に音量確認を行い、A/B/ペアを必要なだけ再生できるようにする。二択質問は `y`/`yes` と `n`/`no` を受け付け、相対比較には `same` と `unsure` を残す。条件名、左右対応、重複位置は試聴者に表示しない。",
        "",
        "相対比較で選ばれても、明瞭な「あ」と人声性の双方がyesでなければ採用候補にしない。回答は探索用でありrelease判定へ直接合算しない。",
        "",
    ])
