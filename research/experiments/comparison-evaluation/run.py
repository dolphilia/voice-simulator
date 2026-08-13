#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SOURCE))

from comparison_eval.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
