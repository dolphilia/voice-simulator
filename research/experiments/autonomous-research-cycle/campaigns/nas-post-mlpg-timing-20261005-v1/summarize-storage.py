"""固定済み比較規則を、外部保存台帳で実行する。"""
from paths import *
from storage_budget import StorageBudget
import summarize as frozen
if __name__=='__main__':
    frozen.Budget=StorageBudget
    frozen.main()
