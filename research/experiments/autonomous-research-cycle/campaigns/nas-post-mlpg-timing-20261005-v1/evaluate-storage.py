"""固定済みASR評価の保存バックエンドだけを外部対応へ差し替える。"""
from paths import *
from storage_budget import StorageBudget
import evaluate as frozen
if __name__=='__main__':
    frozen.Budget=StorageBudget
    frozen.main()
