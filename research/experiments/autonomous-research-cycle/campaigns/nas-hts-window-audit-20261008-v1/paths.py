"""HTS保存励振診断の論理位置。"""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from temporary_storage import ManagedStorageBudget as Budget
NAME='hts-window-audit-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
