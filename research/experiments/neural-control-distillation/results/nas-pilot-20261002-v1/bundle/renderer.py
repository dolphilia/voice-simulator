"""音素ごとの低次元制御を、実行時にVTLジェスチャへ展開する。"""
import ctypes as ct
import math
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import numpy as np
from scipy import signal
from scipy.io import wavfile


PHONE_MAP = {'sh': 'S', 'ch': 'tS', 'j': 'dZ', 'y': 'j', 'w': 'u', 'r': 'l',
             'N': 'N', 'I': 'i', 'U': 'u', 'pau': ''}
PALATAL = {'ky': 'k', 'gy': 'g', 'ny': 'n', 'hy': 'h', 'my': 'm', 'ry': 'l', 'by': 'b', 'py': 'p'}
PLAIN = set('aiueo') | {'m', 'n', 's', 'h', 'f', 'p', 't', 'k', 'b', 'd', 'g', 'z', 'ts'}


def validate(phones, durations, f0):
    d, f = np.asarray(durations, dtype=float), np.asarray(f0, dtype=float)
    if not phones or d.shape != (len(phones),) or f.shape != d.shape:
        raise ValueError('音素と制御の数が一致しません')
    if not np.all(np.isfinite(d)) or not np.all(np.isfinite(f)):
        raise ValueError('制御に非有限値があります')
    if np.any((d < .025) | (d > .6)) or np.any((f < 70) | (f > 450)):
        raise ValueError('継続長またはF0が検証範囲外です')
    return d, f


def segments(phones, durations):
    out = [('', .05)]
    for i, (phone, duration) in enumerate(zip(phones, durations)):
        if phone == 'Q':
            following = phones[i + 1] if i + 1 < len(phones) else None
            if following not in ('p', 't', 'k', 's', 'sh', 'ch', 'ts'):
                raise ValueError('未対応の促音文脈です')
            out.append((PHONE_MAP.get(following, following), float(duration)))
        elif phone in PALATAL:
            out.extend([(PALATAL[phone], float(duration) * .55), ('j', float(duration) * .45)])
        elif phone in PHONE_MAP or phone in PLAIN:
            out.append((PHONE_MAP.get(phone, phone), float(duration)))
        else:
            raise ValueError(f'未対応音素: {phone}')
    out.append(('', .1))
    return out


def baseline(analysis, f0=220., speed=1.):
    durations, frequencies = [], []
    for phrase in analysis['phrases']:
        if phrase.get('pause'):
            durations.append(.14/speed)
            frequencies.append(f0)
            continue
        for mora in phrase['moras']:
            for i, phone in enumerate(mora['phones']):
                fraction = 1 if len(mora['phones']) == 1 else (.7 if i == len(mora['phones'])-1 else .3)
                durations.append(.2 * fraction / speed)
                frequencies.append(f0 * 2**((1.5 if mora['high'] else -1.5)/12))
    validate(analysis['phonemes'], durations, frequencies)
    return np.array(durations), np.array(frequencies)


def render(vtl, phones, durations, f0, seed=20261002):
    d, f = validate(phones, durations, f0)
    segs = segments(phones, d)
    with tempfile.TemporaryDirectory(prefix='nas-vtl-') as tmp:
        root = Path(tmp)
        seg, ges, wav = root/'input.seg', root/'score.ges', root/'output.wav'
        seg.write_text('\n'.join(f'name = {p}; duration_s = {duration:.8f};' for p, duration in segs)+'\n')
        vtl.lib.vtlSegmentSequenceToGesturalScore.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_bool]
        vtl.lib.vtlGesturalScoreToAudio.argtypes = [ct.c_char_p, ct.c_char_p,
            ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.c_bool]
        vtl.check(vtl.lib.vtlSegmentSequenceToGesturalScore(str(seg).encode(), str(ges).encode(), False))
        tree = ET.parse(ges)
        seq = tree.getroot().find("gesture_sequence[@type='f0-gestures']")
        for child in list(seq):
            seq.remove(child)
        for duration, frequency in zip([.05, *d, .1], [f[0], *f, f[-1]]):
            ET.SubElement(seq, 'gesture', value=f'{12*math.log2(frequency):.8f}', slope='0',
                          duration_s=f'{duration:.8f}', time_constant_s='.025', neutral='0')
        tree.write(ges, encoding='unicode')
        ct.CDLL(None).srand(ct.c_uint(seed))
        vtl.check(vtl.lib.vtlGesturalScoreToAudio(str(ges).encode(), str(wav).encode(), None, None, False))
        fs, x = wavfile.read(wav)
        if fs != 44100 or x.dtype != np.int16:
            raise ValueError('VTLの音声形式が想定と異なります')
        audio = signal.resample_poly(x.astype(float)/32768, 80, 147) * .5
        fade = min(round(.012*24000), len(audio)//2)
        env = np.sin(np.linspace(0, np.pi/2, fade))**2
        audio[:fade] *= env
        audio[-fade:] *= env[::-1]
        return audio, {'phones': phones, 'durations_seconds': d.tolist(), 'f0_hz': f.tolist(),
                       'seed': seed, 'segments': segs, 'runtime_neural': False,
                       'limitations': ['日本語rは側音近似', '非円唇uと無声化は未校正',
                                       '声質と声道標的は既存JD3のまま']}
