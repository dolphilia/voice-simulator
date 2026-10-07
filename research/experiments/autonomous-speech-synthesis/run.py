#!/usr/bin/env python3
"""独立した無人音声研究の入口。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from autonomous_speech_synthesis.cli import main

if __name__ == "__main__":
    main()
