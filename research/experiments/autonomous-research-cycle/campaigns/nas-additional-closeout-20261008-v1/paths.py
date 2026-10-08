"""追加4枠の結果統合と包括終了監査。"""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from temporary_storage import ManagedStorageBudget as Budget
NAME='additional-closeout-v1'
PREVIOUS=ROOT/'campaigns/nas-cross-factor-failure-audit-20261008-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
WINDOW=ROOT/'campaigns/nas-hts-window-audit-20261008-v1'
WORLD=ROOT/'campaigns/nas-world-excitation-audit-20261008-v1'
SUPPORT=ROOT/'campaigns/nas-support-excitation-audit-20261008-v1'
