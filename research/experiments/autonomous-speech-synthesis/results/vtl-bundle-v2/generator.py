"""共有物理モデルと実行時のジェスチャ規則。参照・AI評価を含めない。"""
import ctypes as ct
import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile

def sampa_segments(phones, speed):
    mapping = {'sh': 'S', 'ch': 'tS', 'j': 'dZ', 'y': 'j', 'w': 'u', 'r': 'l', 'N': 'N', 'I': 'i', 'U': 'u', 'pau': ''}
    supported = set('aiueo') | {'m', 'n', 's', 'h', 'f', 'p', 't', 'k', 'b', 'd', 'g', 'z', 'ts'}
    output = [('', 0.05)]
    for i, p in enumerate(phones):
        if p == 'Q':
            next_phone = phones[i + 1] if i + 1 < len(phones) else None
            if next_phone not in ('p', 't', 'k', 's', 'sh', 'ch', 'ts'):
                raise ValueError('この促音文脈はVTL前段で未対応です')
            output.append((mapping.get(next_phone, next_phone), 0.1 / speed))
            continue
        duration = (0.12 if p.lower() in 'aiueo' else 0.14 if p == 'pau' else 0.1 if p == 'N' else 0.065) / speed
        if p in ('ky', 'gy', 'ny', 'hy', 'my', 'ry'):
            base = {'ky': 'k', 'gy': 'g', 'ny': 'n', 'hy': 'h', 'my': 'm', 'ry': 'l'}[p]
            output.extend([(base, duration * 0.55), ('j', duration * 0.45)])
        elif p in mapping or p in supported:
            output.append((mapping.get(p, p), duration))
        else:
            raise ValueError(f'VTL写像の未対応音素: {p}')
    output.append(('', 0.1))
    return output

def timed_segments(analysis, mora_seconds=0.2):
    segments = [('', 0.05)]
    pitch = [(0.05, False)]
    phone_times = []
    time = 0.05
    phone_cursor = 0
    mapping = {'sh': 'S', 'ch': 'tS', 'j': 'dZ', 'y': 'j', 'w': 'u', 'r': 'l', 'N': 'N', 'I': 'i', 'U': 'u', 'A': 'a', 'E': 'e', 'O': 'o'}
    for phrase in analysis['phrases']:
        if phrase.get('pause'):
            segments.append(('', 0.14))
            pitch.append((0.14, False))
            time += 0.14
            phone_cursor += 1
            continue
        allphones = analysis['phonemes']
        for mora in phrase['moras']:
            phones = mora['phones']
            duration = mora_seconds
            if len(phones) > 2:
                raise ValueError('3音素以上のモーラは未対応です')
            if phones == ['Q']:
                following = allphones[phone_cursor + 1] if phone_cursor + 1 < len(allphones) else ''
                if following not in ('p', 't', 'k', 's', 'sh', 'ch', 'ts'):
                    raise ValueError('促音の後続文脈が未対応です')
                items = [(mapping.get(following, following), duration, 'Q')]
            else:
                items = []
                for p in phones:
                    d = duration if len(phones) == 1 else duration * 0.3 if p != phones[-1] else duration * 0.7
                    if p in ('ky', 'gy', 'ny', 'hy', 'my', 'ry', 'by', 'py'):
                        b = {'ky': 'k', 'gy': 'g', 'ny': 'n', 'hy': 'h', 'my': 'm', 'ry': 'l', 'by': 'b', 'py': 'p'}[p]
                        items.extend([(b, d * 0.55, p), ('j', d * 0.45, p)])
                    else:
                        items.append((mapping.get(p, p), d, p))
            for s, d, p in items:
                segments.append((s, d))
                phone_times.append({'phone': p, 'start': time, 'end': time + d})
                time += d
            pitch.append((duration, mora['high']))
            phone_cursor += len(phones)
    segments.append(('', 0.1))
    pitch.append((0.1, False))
    return (segments, pitch, phone_times)

def patch_taps(root, duration=0.028):
    """側音区間の中央だけを短い有声の舌尖閉鎖へ置換。声門系列は保持する。"""
    seq = root.find("gesture_sequence[@type='tongue-tip-gestures']")
    n = 0
    for g in list(seq):
        if 'lateral' not in g.get('value', ''):
            continue
        total = float(g.get('duration_s'))
        width = min(duration, total)
        before = (total - width) / 2
        after = total - before - width
        index = list(seq).index(g)
        seq.remove(g)
        replacements = []
        for d, value, neutral, tau in [(before, '', 1, 0.007), (width, 'tt-alveolar-closure', 0, 0.007), (after, '', 1, 0.007)]:
            if d > 1e-08:
                replacements.append(ET.Element('gesture', value=value, slope='0', duration_s=f'{d:.8f}', time_constant_s=str(tau), neutral=str(neutral)))
        for j, item in enumerate(replacements):
            seq.insert(index + j, item)
        n += 1
    return n

def render_japanese(vtl, analysis, variant, seed):
    if variant == 'baseline':
        segments = sampa_segments(analysis['phonemes'], 0.85)
        pitch = []
        timing = []
    else:
        segments, pitch, timing = timed_segments(analysis)
    with tempfile.TemporaryDirectory(prefix='ans-ja-v2-') as temp:
        temp = Path(temp)
        seg = temp / 'text.seg'
        ges = temp / 'generated.ges'
        wav = temp / 'raw.wav'
        seg.write_text('\n'.join((f'name = {p}; duration_s = {d:.8f};' for p, d in segments)) + '\n')
        vtl.lib.vtlSegmentSequenceToGesturalScore.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_bool]
        vtl.lib.vtlGesturalScoreToAudio.argtypes = [ct.c_char_p, ct.c_char_p, ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.c_bool]
        vtl.check(vtl.lib.vtlSegmentSequenceToGesturalScore(str(seg).encode(), str(ges).encode(), False))
        tree = ET.parse(ges)
        root = tree.getroot()
        seq = root.find("gesture_sequence[@type='f0-gestures']")
        for g in list(seq):
            seq.remove(g)
        total = sum((d for _, d in segments))
        base = 12 * math.log2(160.0)
        if variant in ('baseline', 'mora'):
            points = [(0.12 * total, -1.5), (0.48 * total, 1.0), (0.4 * total, -2.0)]
        else:
            points = [(d, 1.5 if high else -1.5) for d, high in pitch]
        for d, offset in points:
            ET.SubElement(seq, 'gesture', value=f'{base + offset:.8f}', slope='0', duration_s=f'{d:.8f}', time_constant_s='.025', neutral='0')
        taps = patch_taps(root) if variant == 'accent-tap' else 0
        tree.write(ges, encoding='unicode')
        score = ges.read_text()
        ct.CDLL(None).srand(ct.c_uint(seed))
        vtl.check(vtl.lib.vtlGesturalScoreToAudio(str(ges).encode(), str(wav).encode(), None, None, False))
        fs, x = wavfile.read(wav)
        if fs != 44100:
            raise ValueError('VTL標本化周波数が想定と異なります')
        audio = signal.resample_poly(x.astype(float) / 32768, 80, 147) * 0.5
        fade = min(round(0.012 * 24000), len(audio) // 2)
        env = np.sin(np.linspace(0, np.pi / 2, fade)) ** 2
        audio[:fade] *= env
        audio[-fade:] *= env[::-1]
        return (audio, {'version': 'vtl-japanese-gesture-v2', 'variant': variant, 'phonemes': analysis['phonemes'], 'phrase_moras': analysis['phrases'], 'segments': segments, 'phone_times': timing, 'tap_gestures': taps, 'gestural_score_generated_at_runtime': score, 'f0_hz': 160, 'seed': seed, 'backend': vtl.metadata, 'limitations': ['短い舌尖閉鎖は弾音の研究近似。側方流路や実測接触は未校正', '非円唇uと無声化I/Uは未対応', '句内二値F0は辞書アクセント規則の近似であり自然韻律認定なし']}, 24000)

class Backend:
    def __init__(self):
        root=Path(__file__).resolve().parent
        self.lib=ct.CDLL(str(root/'libVocalTractLabApi.dylib'))
        self.lib.vtlInitialize.argtypes=[ct.c_char_p]
        self.check(self.lib.vtlInitialize(str(root/'JD3.speaker').encode()))
        self.metadata={'model':'VocalTractLab/JD3','runtime':'non-neural','shared_physical_model':True}
    @staticmethod
    def check(value):
        if value!=0:raise RuntimeError(f'VTL APIの失敗: {value}')
    def close(self):self.check(self.lib.vtlClose())
