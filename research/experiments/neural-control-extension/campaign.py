"""承認された追加campaignの契約、台帳、凍結済み資産の参照。"""
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parent
PILOT=ROOT.parent/'neural-control-distillation'
PRIOR=PILOT/'results/nas-pilot-20261002-v1'
sys.path.insert(0,str(PILOT))
from budget import Budget,save,digest
RESULT=ROOT/'results/nas-extension-20261002-v1'
LIMITS={'seconds':7200,'bytes':1_000_000_000,'teacher':24,'render':400,'ai':300}


class ExtensionBudget(Budget):
    def __init__(self):super().__init__(ROOT,RESULT)
    def initialize(self):
        with self.locked():
            path=self.result/'contract.json'
            if not path.exists():
                save(path,{'campaign':RESULT.name,'started_epoch':time.time(),'limits':LIMITS,
                    'authorization':'ユーザー「承認します。作業を続けてください」による評価上限改訂と継続の承認',
                    'campaign_count':1,'scope':'追加領域の全ファイルを容量に含む。既存の固定資産は読み取り再利用',
                    'previous_campaign_unchanged':True,'final_generator_non_neural':True,
                    'perception_qualification_not_relaxed':True,'unattended':True})
            return json.loads(path.read_text())
