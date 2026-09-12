# クラシカルなデジタル音源（PSG・FM・PCM）

---

## 1. PSG 音源（Programmable Sound Generator）

矩形波とノイズを組み合わせた最もシンプルなデジタル音源チップ。  
1980年代のゲーム機・パソコン（MSX、ZX Spectrum、ファミコン等）のサウンドの源。

### 仕組み

**トーン生成**  
クロック信号をレジスタ値で分周（カウントダウン）することで矩形波を生成する。
周波数 = マスタークロック / (2 × レジスタ値)

```python
def psg_tone(freq, duration, sample_rate=44100, duty=0.5):
    """矩形波（デューティ比指定可能）"""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return np.where((t * freq % 1.0) < duty, 1.0, -1.0).astype(np.float32)
```

**LFSR ノイズ**  
線形フィードバックシフトレジスタ（LFSR）で擬似ランダム 2 値列を生成する。  
タップ位置が音色を決定する（白色ノイズ / 周期ノイズの切り替え）。

```python
def lfsr_noise(n_samples, bits=17, taps=(0, 2)):
    """LFSR ノイズ生成"""
    state = (1 << bits) - 1
    out = np.zeros(n_samples)
    for i in range(n_samples):
        feedback = 0
        for tap in taps:
            feedback ^= (state >> tap) & 1
        state = ((state >> 1) | (feedback << (bits - 1))) & ((1 << bits) - 1)
        out[i] = float((state & 1) * 2 - 1)
    return out
```

### 倍音構成

矩形波は**奇数次倍音のみ**を含む（1f, 3f, 5f, 7f ...）。  
振幅は n 次倍音に対して 1/n で減衰する。  
デューティ比が 50% から外れると偶数次倍音も出現し、音色が変化する。

### 代表的な実装・機材

| チップ | 搭載機器 | 特徴 |
|---|---|---|
| AY-3-8910 | MSX, ZX Spectrum, Amstrad CPC | 3ch トーン + 1ch ノイズ + HW エンベロープ |
| SN76489 | Sega Master System, Mega Drive | 3ch トーン + 1ch ノイズ、4bit 音量制御 |
| 2A03 | NES（ファミコン） | 2ch 矩形波 + 1ch 三角波 + ノイズ + DPCM |

---

## 2. FM 音源

John Chowning（スタンフォード, 1973）が発見した音楽応用。  
キャリアオシレーターの位相をモジュレーターで変調し、豊かな倍音列を少ないオシレーターで生成する。

### 仕組み

```
y(t) = A · sin(2π·fc·t + β·sin(2π·fm·t))
```

- `fc` : キャリア周波数
- `fm` : モジュレーター周波数  
- `β`（変調インデックス）: 倍音の豊かさ。β→0 で正弦波、β↑ で倍音増加
- 実際には FM ではなく **PM（位相変調）** で実装されることが多い（DX7 も PM）

### C:M 比と音色

| C:M 比 | 倍音構造 | 音色傾向 |
|---|---|---|
| 1:1 | 整数倍音列 | オルガン、ブラス系 |
| 1:2 | 奇数倍音が強調 | クラリネット系 |
| 2:1 | 基音の半音上シフト | 鐘、金属系 |
| 1:1.5 | 非整数倍音列 | 打楽器的 |
| 非整数比 | 非調和 | ベル、シンバル系 |

### DX7 のアルゴリズム構造

6 つのオペレーター（それぞれ独立の正弦波 + エンベロープ）を 32 種のアルゴリズム（接続パターン）で組み合わせる。  
**キャリア**（最終出力に直結するオペレーター）と**モジュレーター**（他のオペレーターの位相を変調）の役割で構成される。

### OPL2/OPL3（Yamaha YM3812/YMF262）

| 項目 | OPL2 | OPL3 |
|---|---|---|
| チャンネル数 | 9ch | 18ch |
| オペレーター数/ch | 2 | 2 または 4 |
| 波形選択 | 4 種 | 8 種 |
| 搭載例 | AdLib, PC-9801 | Sound Blaster 16, FM 音源ボード |

OPL は正弦波以外に「半サイン波」「絶対値サイン波」「パルスサイン波」なども選択でき、DX7 とは異なる特有の音色を持つ。

### 実装

```python
def fm_synth(fc, fm_ratio, beta, duration, sample_rate=44100):
    """基本的な FM 合成（1キャリア + 1モジュレーター）"""
    fm = fc * fm_ratio
    t  = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return np.sin(2*np.pi*fc*t + beta * np.sin(2*np.pi*fm*t))


def fm_with_env(fc, fm_ratio, beta_max, duration,
                attack=0.01, decay=0.1, sustain=0.5, release=0.2,
                sample_rate=44100):
    """エンベロープ付き FM（β も ADSR で変化）"""
    n   = int(sample_rate * duration)
    t   = np.linspace(0, duration, n, endpoint=False)
    env = adsr_linear(n, attack, decay, sustain, release, sample_rate)
    mod = (beta_max * env) * np.sin(2*np.pi*fc*fm_ratio*t)
    return np.sin(2*np.pi*fc*t + mod)


def fm_4op_cascade(f_base, ratios, betas, duration, sample_rate=44100):
    """4 オペレーター直列 FM（op4 → op3 → op2 → op1 → out）"""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    mod = betas[3] * np.sin(2*np.pi*f_base*ratios[3]*t)
    for i in range(2, -1, -1):
        mod = betas[i] * np.sin(2*np.pi*f_base*ratios[i]*t + mod)
    return mod
```

### 他手法との比較

- フィルターを使わず**倍音構成そのもの**を変調で直接設計する点でサブトラクティブと根本的に異なる
- β の時間変化（アタック時に多く、サステインで少なく）でブラスやピアノの自然な音量-倍音連動を表現できる
- Feedback FM（自己変調）はカオス的なノイズまで生成可能

---

## 3. PCM / サンプリング音源

実際の楽器を録音した波形データを再生する。デジタル的には「テーブルルックアップ」の発展形。

### 主要技術

**ループポイント**  
サステイン区間を繰り返し再生する。種類：
- フォワードループ（単純折り返し）
- ピンポンループ（往復）
- クロスフェードループ（継ぎ目を滑らかに）

**マルチサンプリング**  
音域ごとに異なるサンプルを配置（通常 5〜6 度間隔）。  
移調量が大きいと音色の不自然さが出るため、より密にサンプリングすることで品質が向上する。

**ピッチシフト（レート変換）**  
サンプルの再生速度を変えて音程を変化させる。  
補間の質で音質が大きく変わる。

| 補間手法 | 品質 | CPU 負荷 |
|---|---|---|
| 線形補間 | 低 | 低 |
| Hermite（3次スプライン） | 中 | 中 |
| 8点 Sinc フィルター | 高（エイリアシング抑制） | 高 |

```python
def pitch_shift_pcm(audio, semitones):
    """レート変換によるピッチシフト（線形補間）"""
    ratio   = 2 ** (semitones / 12.0)
    n_orig  = len(audio)
    n_new   = int(n_orig / ratio)
    x_orig  = np.linspace(0, n_orig - 1, n_orig)
    x_new   = np.linspace(0, n_orig - 1, n_new)
    return np.interp(x_new, x_orig, audio)


def loop_sample(audio, loop_start, loop_end, total_length):
    """ループ再生"""
    out  = list(audio[:loop_start])
    loop = audio[loop_start:loop_end]
    while len(out) < total_length:
        out.extend(loop)
    return np.array(out[:total_length])
```

### 代表的な実装・機材

| 機材 / フォーマット | 特徴 |
|---|---|
| Roland D-50 | PCM + デジタルシンセ（LA 合成） |
| Korg M1 | PCM + デジタルフィルター、ワークステーション時代の先駆け |
| E-mu Proteus | 高品質サンプラー音源 ROM |
| General MIDI / SF2（SoundFont） | 標準 PCM フォーマット |

---

[← 概要に戻る](synthesis-overview.md)
