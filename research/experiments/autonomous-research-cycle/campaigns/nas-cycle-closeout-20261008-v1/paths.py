"""MCP後処理実験の論理位置。旧成果は読み取り専用で参照する。"""
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parents[2]
sys.path.insert(0, str(ROOT))
from budget import read, digest, encode
from temporary_storage import ManagedStorageBudget as Budget
NAME = 'cycle-closeout-v1'
PREVIOUS = ROOT / 'campaigns/nas-cross-factor-failure-audit-20261008-v1'
TIMING = ROOT / 'campaigns/nas-post-mlpg-timing-20261005-v1'
SOURCE = ROOT / 'campaigns/nas-source-identity-20261004-v1'
WORLD = ROOT / 'campaigns/nas-world-control-20261004-v1'
OLD = REPO / 'research/experiments/autonomous-speech-synthesis'
PILOT = REPO / 'research/experiments/neural-control-distillation'
BUNDLE = REPO / 'research/experiments/neural-control-extension/results/nas-extension-20261002-v1/acoustic-revision/bundle'
PYTHON = OLD / '.venv-eval/bin/python'

LATEST = ROOT / 'campaigns/nas-gv-ap-interaction-20261008-v1'

PERIOD = ROOT / 'campaigns/nas-source-period-audit-20261008-v1'
