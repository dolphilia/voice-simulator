"""既存WORLD励振観測の固定位置。"""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from temporary_storage import ManagedStorageBudget as Budget
NAME='world-excitation-audit-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
CONVERT=ROOT/'campaigns/nas-mcp-postfilter-20261008-v1/runtime-bundle'
PRIMARY=ROOT/'campaigns/nas-world-control-20261004-v1/upstream'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
