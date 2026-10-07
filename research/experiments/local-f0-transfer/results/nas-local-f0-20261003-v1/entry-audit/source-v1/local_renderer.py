"""対応版C shimで状態・LF0・波形を独立に扱う非ニューラル入口。"""
import ctypes as C
from pathlib import Path
import numpy as np
from scipy import signal
import pyopenjtalk.htsengine
ROOT = Path(__file__).resolve().parent
_original = C.CDLL(pyopenjtalk.htsengine.__file__, mode=C.RTLD_GLOBAL)
_lib = C.CDLL(str(ROOT/'local_hts.dylib'))
P, S, D = C.c_void_p, C.c_size_t, C.c_double


def bind(name, result, arguments):
    fn = getattr(_lib, name)
    fn.restype, fn.argtypes = result, arguments
    return fn


new = bind('local_new', P, [C.c_char_p])
free = bind('local_free', None, [P])
states = bind('local_states', C.c_int, [P, C.POINTER(C.c_char_p), S, D, D])
for _name in ('nstate', 'total_state', 'nstream', 'fperiod', 'fs', 'nsamples', 'frames'):
    globals()[_name] = bind('local_'+_name, S, [P])
vector = bind('local_vector', S, [P, S])
windows = bind('local_windows', S, [P, S])
duration = bind('local_duration', S, [P, S])
mean = bind('local_mean', D, [P, S, S, S])
msd = bind('local_msd', D, [P, S])
apply = bind('local_apply', C.c_int, [P, C.POINTER(D), S])
wave = bind('local_wave', C.c_int, [P])
parameter = bind('local_parameter', D, [P, S, S, S])
copy_audio = bind('local_copy_audio', None, [P, C.POINTER(D), S])


class StateEngine:
    def __init__(self, row, voice, speed=1., half_tone=0.):
        self.pointer = None
        labels = row['full_context_labels']
        if not 3 <= len(labels) <= 122 or not .5 <= speed <= 2 or not -12 <= half_tone <= 12 or not np.isfinite([speed, half_tone]).all():
            raise ValueError('ラベル数・速度・F0指定が範囲外です')
        if any(not isinstance(x, str) or '\0' in x or len(x) > 2000 for x in labels):
            raise ValueError('ラベル入力が不正です')
        self.pointer = new(str(voice).encode())
        if not self.pointer:
            raise RuntimeError('HMM読込失敗')
        try:
            encoded = [x.encode() for x in labels]
            lines = (C.c_char_p*len(labels))(*encoded)
            if not states(self.pointer, lines, len(labels), speed, half_tone):
                raise RuntimeError('状態列生成失敗')
            self.count, self.per_phone = total_state(self.pointer), nstate(self.pointer)
            if self.per_phone != 5 or self.count != len(labels)*5 or nstream(self.pointer) != 3 or fs(self.pointer) != 48000 or fperiod(self.pointer) != 240:
                raise ValueError('状態・ストリーム・周期が既定Meiと一致しません')
            self.layout = [(vector(self.pointer, s), windows(self.pointer, s)) for s in range(3)]
            if self.layout[1] != (1, 3):
                raise ValueError('LF0ストリームが想定と一致しません')
        except BaseException:
            self.close()
            raise

    def snapshot(self):
        if self.pointer is None:
            raise RuntimeError('終了済みです')
        return {'duration': [duration(self.pointer, i) for i in range(self.count)],
            'msd': [msd(self.pointer, i) for i in range(self.count)], 'layout': self.layout,
            'means': [[[mean(self.pointer, s, i, v) for v in range(length*win)] for i in range(self.count)]
                      for s, (length, win) in enumerate(self.layout)]}

    def modify(self, deltas):
        x = np.asarray(deltas, dtype=np.float64)
        if x.shape != (self.count,) or not np.isfinite(x).all() or np.max(abs(x)) > 3:
            raise ValueError('残差の形状・有限性・±3半音の検査に不通過')
        if not apply(self.pointer, x.ctypes.data_as(C.POINTER(D)), len(x)):
            raise ValueError('残差の内部範囲検査に不通過')

    def generate(self):
        if not wave(self.pointer):
            raise RuntimeError('パラメータ・波形列生成失敗')
        audio = np.empty(nsamples(self.pointer), dtype=np.float64)
        copy_audio(self.pointer, audio.ctypes.data_as(C.POINTER(D)), len(audio))
        lf0 = np.array([parameter(self.pointer, 1, f, 0) for f in range(frames(self.pointer))])
        audio = signal.resample_poly(audio/32768, 1, 2)
        n = min(round(.012*24000), len(audio)//2)
        env = np.sin(np.linspace(0, np.pi/2, n))**2
        audio[:n] *= env
        audio[-n:] *= env[::-1]
        return audio, lf0

    def close(self):
        if self.pointer is not None:
            free(self.pointer)
            self.pointer = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
