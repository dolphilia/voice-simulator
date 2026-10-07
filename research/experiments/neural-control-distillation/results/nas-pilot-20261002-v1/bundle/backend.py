"""VTLの非ニューラルC ABIを読み込む。"""
import ctypes as ct
from pathlib import Path

class Backend:

    def __init__(self):
        root = Path(__file__).resolve().parent
        self.lib = ct.CDLL(str(root / 'libVocalTractLabApi.dylib'))
        self.lib.vtlInitialize.argtypes = [ct.c_char_p]
        self.check(self.lib.vtlInitialize(str(root / 'JD3.speaker').encode()))
        self.metadata = {'model': 'VocalTractLab/JD3', 'runtime': 'non-neural', 'shared_physical_model': True}

    @staticmethod
    def check(value):
        if value != 0:
            raise RuntimeError(f'VTL APIの失敗: {value}')

    def close(self):
        self.check(self.lib.vtlClose())
