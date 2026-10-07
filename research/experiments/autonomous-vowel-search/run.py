#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

EXPERIMENT_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = EXPERIMENT_ROOT.parents[2]

for source in (
    EXPERIMENT_ROOT / "src",
    REPOSITORY_ROOT / "research/experiments/synthetic-vowel-baseline/src",
    REPOSITORY_ROOT / "research/experiments/comparison-evaluation/src",
):
    sys.path.insert(0, str(source))

from autonomous_vowel_search.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

