"""固定有声支持と励振診断の固定位置。"""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from temporary_storage import ManagedStorageBudget as Budget
NAME='support-excitation-audit-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
WINDOW=ROOT/'campaigns/nas-hts-window-audit-20261008-v1'
WORLD=ROOT/'campaigns/nas-world-excitation-audit-20261008-v1'
CROSS=ROOT/'campaigns/nas-cross-factor-failure-audit-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
