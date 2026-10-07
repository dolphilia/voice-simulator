"""新campaignの保存先と、読み取り専用の旧参照。"""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import Budget,read,digest,encode
NAME='boundary-policy-v1'
PREP=ROOT/'campaigns/nas-partial-spectrum-20261004-v1'
SHARED=REPO/'research/experiments/saved-waveform-shared-control'
SRES=SHARED/'results/nas-saved-wave-shared-20261003-v1'
EVAL=REPO/'research/experiments/saved-shared-control-evaluation'
ERES=EVAL/'results/nas-saved-shared-eval-20261003-v1'
COUNTER=REPO/'research/experiments/source-filter-counterfactual'
CRES=COUNTER/'results/nas-source-filter-20261003-v1'
OLD=REPO/'research/experiments/autonomous-speech-synthesis'
PILOT=REPO/'research/experiments/neural-control-distillation'
BUNDLE=REPO/'research/experiments/neural-control-extension/results/nas-extension-20261002-v1/acoustic-revision/bundle'
REVIEW=REPO/'research/experiments/saved-control-objective-review/results/nas-control-review-20261004-v1'

CURRENT=ROOT/'campaigns/nas-partial-spectrum-20261004-v2'

PREVIOUS=ROOT/'campaigns/nas-prosody-only-20261004-v2'

CONTROL=PREVIOUS
PREVIOUS=ROOT/'campaigns/nas-source-identity-20261004-v1'

WORLD=ROOT/'campaigns/nas-world-control-20261004-v1'
PREVIOUS=WORLD

JP=ROOT/'campaigns/nas-japanese-teacher-20261004-v1'
PREVIOUS=JP
