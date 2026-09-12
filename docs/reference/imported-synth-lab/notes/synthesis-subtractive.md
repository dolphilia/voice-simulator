# サブトラクティブ合成・ウェーブテーブル合成

---

## 1. サブトラクティブ合成の概要

豊かな倍音を持つ波形をフィルターで削り、音色を作る手法。アナログシンセの標準的なアーキテクチャ。

```
[VCO] ──→ [VCF] ──→ [VCA] ──→ 出力
  ↑            ↑         ↑
[LFO]     [ENV1]    [ENV2]
               ↑
             [GATE]
```

---

## 2. VCO（Voltage Controlled Oscillator）

### 波形と倍音構成

| 波形 | 倍音列 | 振幅減衰 | 音色 |
|---|---|---|---|
| サイン波 | 基音のみ | — | 柔らかい純音（フルート・口笛） |
| 矩形波 | 奇数次（1, 3, 5...） | 1/n | ホロウ（クラリネット系） |
| 鋸歯状波 | 全倍音（1, 2, 3...） | 1/n | 明るい・倍音豊富（ブラス・弦） |
| 三角波 | 奇数次（1, 3, 5...） | 1/n² | 矩形波より柔らかい |

```python
from scipy import signal as sp_signal

def vco(freq, duration, wave='saw', duty=0.5, sample_rate=44100):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    if wave == 'sine':
        return np.sin(2*np.pi*freq*t)
    elif wave == 'square':
        return sp_signal.square(2*np.pi*freq*t, duty=duty)
    elif wave == 'saw':
        return sp_signal.sawtooth(2*np.pi*freq*t, width=1.0)
    elif wave == 'triangle':
        return sp_signal.sawtooth(2*np.pi*freq*t, width=0.5)
```

### エイリアシングとバンドリミット

デジタルで直接生成した矩形波・鋸歯状波は、ナイキスト周波数を超える倍音がエイリアシングを起こす。  
解決策：**BLIT（Band-Limited Impulse Train）** や **PolyBLEP** で不要な高次倍音を除去する。

```python
def bandlimited_saw(freq, duration, sample_rate=44100):
    """バンドリミッテッド鋸歯状波（加算合成で生成）"""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    n_harmonics = int(sample_rate / (2 * freq))  # ナイキスト以下の倍音数
    out = np.zeros_like(t)
    for n in range(1, n_harmonics + 1):
        out += ((-1)**(n+1)) * np.sin(2*np.pi*n*freq*t) / n
    return out * (2 / np.pi)
```

---

## 3. VCF（Voltage Controlled Filter）

フィルターはサブトラクティブ合成の「音色の核」。カットオフ周波数とレゾナンスで大幅に音色が変わる。

### Moog ラダーフィルター

Robert Moog が 1969 年に特許取得した 4 極（-24 dB/oct）ローパスフィルター。  
4 段のトランジスターがラダー（梯子）状に接続され、各段でコンデンサと組み合わさる。

**特徴**
- レゾナンスを上げると**自己発振**（カットオフ付近が強調されサイン波を出力）する
- 非線形の `tanh` 飽和特性が「暖かみ」を生む
- -24 dB/oct の急峻な減衰でシャープなサウンド

```python
def moog_ladder(audio, cutoff, resonance, sample_rate=44100):
    """簡略化された Moog ラダーフィルター近似"""
    f  = 2 * np.sin(np.pi * cutoff / sample_rate)
    fb = resonance * 4.0
    s1 = s2 = s3 = s4 = 0.0
    out = np.zeros_like(audio)
    for i, x in enumerate(audio):
        x   -= fb * s4
        s1  += f * (np.tanh(x)  - np.tanh(s1))
        s2  += f * (s1 - s2)
        s3  += f * (s2 - s3)
        s4  += f * (s3 - s4)
        out[i] = s4
    return out
```

### SVF（State Variable Filter）

**LP / BP / HP / ノッチを同時出力**できる 2 極（-12 dB/oct）フィルター。

```python
def svf(audio, cutoff, q, sample_rate=44100):
    """ステートバリアブルフィルター"""
    f = 2 * np.sin(np.pi * cutoff / sample_rate)
    lp = bp = 0.0
    result = {'lp': [], 'bp': [], 'hp': []}
    for x in audio:
        lp += f * bp
        hp  = x / q - lp / q - bp
        bp += f * hp
        result['lp'].append(lp)
        result['bp'].append(bp)
        result['hp'].append(hp)
    return {k: np.array(v) for k, v in result.items()}
```

### フィルター種類の比較

| フィルター | 傾き | 特徴 | 代表的な搭載機 |
|---|---|---|---|
| Moog ラダー | -24 dB/oct | 自己発振、暖かみ、非線形 | Minimoog, Sub 37 |
| SVF | -12 dB/oct | LP/BP/HP 同時、安定した発振 | Oberheim, Prophet-5 |
| Sallen-Key | -12 dB/oct | Op-Amp ベース、シンプル | 汎用回路 |
| CEM3320 | -24 dB/oct | OTA ベース、クリーン | Prophet-5, Juno-106 |

---

## 4. VCA + ADSR エンベロープ

ADSR エンベロープが VCA（音量）と VCF（フィルター）の両方を制御することで、音の時間的形状が決まる。

| パラメーター | 説明 |
|---|---|
| Attack | キーオン → 最大音量までの時間 |
| Decay | 最大音量 → サステインレベルまでの時間 |
| Sustain | キーホールド中の音量（レベル指定） |
| Release | キーオフ → 無音までの時間 |

```python
def adsr(n_samples, attack, decay, sustain, release, sample_rate=44100):
    """線形 ADSR エンベロープ"""
    a = int(attack  * sample_rate)
    d = int(decay   * sample_rate)
    r = int(release * sample_rate)
    s = max(0, n_samples - a - d - r)
    return np.concatenate([
        np.linspace(0,       1,       a),
        np.linspace(1,       sustain, d),
        np.full(s,           sustain),
        np.linspace(sustain, 0,       r),
    ])[:n_samples]


def adsr_exp(n_samples, attack, decay, sustain, release, sample_rate=44100):
    """指数カーブ ADSR（より自然な聴感）"""
    a = int(attack  * sample_rate)
    d = int(decay   * sample_rate)
    r = int(release * sample_rate)
    s = max(0, n_samples - a - d - r)
    a_env = 1 - np.exp(-np.linspace(0, 5, max(a, 1)))
    a_env = a_env / a_env[-1]
    d_env = sustain + (1 - sustain) * np.exp(-np.linspace(0, 5, max(d, 1)))
    r_env = sustain * np.exp(-np.linspace(0, 5, max(r, 1)))
    return np.concatenate([a_env, d_env, np.full(s, sustain), r_env])[:n_samples]
```

---

## 5. LFO による変調

LFO（Low Frequency Oscillator）は可聴域以下（0.1〜20 Hz）で動作するオシレーター。  
音色パラメーターを周期的に変化させる。

| LFO の変調先 | 効果 |
|---|---|
| VCO ピッチ | ビブラート |
| VCF カットオフ | ワウ効果 |
| VCA 音量 | トレモロ |
| パンポット | オートパン |
| PWM デューティ比 | コーラス感 |

```python
def lfo(rate, shape='sine', duration=1.0, depth=1.0, sample_rate=44100):
    """LFO 信号の生成"""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    if shape == 'sine':
        return depth * np.sin(2*np.pi*rate*t)
    elif shape == 'square':
        return depth * np.sign(np.sin(2*np.pi*rate*t))
    elif shape == 'saw':
        return depth * (2 * (t * rate % 1.0) - 1)
    elif shape == 'triangle':
        return depth * (2 * np.abs(2 * (t * rate % 1.0) - 1) - 1)
    elif shape == 'sh':  # Sample & Hold
        steps = int(duration * rate)
        vals  = np.random.uniform(-depth, depth, steps + 1)
        return np.interp(np.linspace(0, steps, len(t)),
                         np.arange(steps + 1), vals)
```

---

## 6. ウェーブテーブル合成

Wolfgang Palm（PPG）が 1970 年代後半に開発。  
複数の 1 サイクル波形をメモリに格納し、テーブルポジションを動かすことで音色をモーフィングする。

### 仕組み

```
[波形テーブル 0] ─┐
[波形テーブル 1]  ├→ [線形補間] → [オシレーター] → 出力
        ...      │    ↑
[波形テーブル N] ─┘  ポジション（LFO/ENV で変化）
```

テーブルポジションが動く = スペクトルが変化する「動いている音」になる。

### 代表的な機材

| 機材 | テーブルサイズ | 精度 | 特徴 |
|---|---|---|---|
| PPG Wave 2.2 | 128 サンプル | 8 bit | デジタルな質感が個性 |
| PPG Wave 2.3 | 128 サンプル | 12 bit | 改良版 |
| Waldorf Microwave | 128 サンプル | 12 bit | PPG の後継 |
| Xfer Serum（ソフト） | 2048 サンプル | 32 bit | 画像/音声からテーブル生成可能 |

### 実装

```python
def create_wavetable(waveform_list, table_size=2048):
    """複数波形をリサンプリングしてウェーブテーブルを作成"""
    table = np.zeros((len(waveform_list), table_size))
    for i, w in enumerate(waveform_list):
        x_orig = np.linspace(0, 1, len(w))
        x_new  = np.linspace(0, 1, table_size)
        resampled = np.interp(x_new, x_orig, w)
        mx = np.max(np.abs(resampled))
        table[i] = resampled / mx if mx > 0 else resampled
    return table


def wavetable_osc(table, position, freq, duration, sample_rate=44100):
    """ウェーブテーブルオシレーター（2テーブル間の線形補間）"""
    n_tables, table_size = table.shape
    n_samples  = int(duration * sample_rate)
    phase_inc  = freq * table_size / sample_rate

    pos_idx = np.clip(position * (n_tables - 1), 0, n_tables - 1)
    lo      = int(pos_idx)
    hi      = min(lo + 1, n_tables - 1)
    frac    = pos_idx - lo
    blended = (1 - frac) * table[lo] + frac * table[hi]

    out   = np.zeros(n_samples)
    phase = 0.0
    for i in range(n_samples):
        idx    = int(phase) % table_size
        f_part = phase - int(phase)
        s1, s2 = blended[idx], blended[(idx + 1) % table_size]
        out[i] = s1 + f_part * (s2 - s1)
        phase += phase_inc
    return out
```

### ウェーブテーブルのスキャン

テーブルポジションを LFO やエンベロープで動かすことで、音色が時間とともに変化する。  
この「音色のモーフィング」がウェーブテーブル合成の最大の特徴。

---

## サブトラクティブ合成の完全な信号フロー

```python
def subtractive_patch(freq, note_duration=1.5, sample_rate=44100):
    """VCO → VCF → VCA のシンプルなサブトラクティブパッチ"""
    # VCO：鋸歯状波
    wave = vco(freq, note_duration + 0.3, 'saw', sample_rate=sample_rate)
    n    = len(wave)

    # フィルターエンベロープ（VCF）
    f_env = adsr(n, 0.005, 0.15, 0.3, 0.3, sample_rate)
    cutoff_base, cutoff_peak = 400, 3000
    # カットオフをフレームごとに変化させる簡易版
    filtered = moog_ladder(wave, cutoff_base + (cutoff_peak - cutoff_base) * f_env.mean(),
                           resonance=0.3, sample_rate=sample_rate)

    # アンプエンベロープ（VCA）
    a_env = adsr(n, 0.005, 0.1, 0.7, 0.3, sample_rate)
    return filtered * a_env
```

---

[← 概要に戻る](synthesis-overview.md)
