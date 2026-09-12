# 物理モデリング・スペクトル合成・グラニュラー合成

---

## 1. Karplus-Strong 法

1983 年に Karplus & Strong が提案した弦楽器の物理インスパイアドモデル。  
詳細な実験は [ノートブック 01](../../../../research/notebooks/imported-synth-lab/01_audio_analysis.ipynb) に記録されている。

### 仕組み

遅延線（リングバッファ）とフィードバックフィルターの組み合わせ。

```
[ホワイトノイズで初期化した遅延バッファ（長さ N = Fs/f₀）]
       ↓
  出力 ← バッファ先頭
       ↓
  フィードバック = decay × 0.5 × (sample[n] + sample[n+1])  ← 1次 LP フィルター
       ↓
  バッファ末尾に追加 → ループ
```

高周波成分がローパスフィルターによって早く減衰 → 弦の物理挙動を模倣。

### 拡張 KS（EKS）

| パラメーター | 効果 |
|---|---|
| `stretch` 係数 | 遅延長を確率的に変動させてデチューン感を出す |
| `pick_pos`（爪弾き位置） | 弦上の位置で特定倍音をキャンセル |
| 減衰フィルターの変種 | 1次 LP → 2次 LP / Allpass フィルター / Comb フィルター |

---

## 2. DWG（Digital Waveguide Synthesis）

Julius O. Smith III（Stanford CCRMA）が開発。  
1 次元波動方程式の進行波解を**双方向の遅延線**でデジタル実装する手法。

### 仕組み

```
[右進行波 +] → 反射フィルター（ブリッジ）
        ↑                          ↓
[左進行波 −] ← 反射フィルター（ナット）
```

- 2 本の遅延線（右進行 / 左進行）が境界条件で結合される
- 損失と分散はフィルターとして遅延線に組み込む
- 弦の場合：両端の反射フィルターで音色・減衰を決定
- 管楽器の場合：ベル（開口端）と気柱の接合部のスキャタリング接合

### 管楽器モデルの構成

```
[リード / 唇（励振部）] ↔ [気柱遅延線] ↔ [ベル放射フィルター]
          ↑________________フィードバック________________↑
```

- **円筒ボア**（クラリネット）: 単純な 1 方向遅延線
- **円錐ボア**（サクソフォン・オーボエ）: 截頭円錐セクションで近似

### KS との比較

| 項目 | Karplus-Strong | DWG |
|---|---|---|
| モデルの厳密さ | 近似的 | 物理的に厳密 |
| 計算コスト | 非常に低い | 中程度 |
| 制御できるパラメーター | 少ない | 豊富（ボア形状・開口端等） |
| 主な用途 | 弦楽器の軽量実装 | 弦・管楽器の高品質実装 |

---

## 3. Modal 合成（共鳴モード合成）

振動体の固有振動モードを解析し、それを 2 極共鳴フィルターの集合として実装する手法。  
打楽器（鐘・マリンバ・ハンパン）や板・膜のモデリングに特に適する。

### 仕組み

各モードの伝達関数：

```
Hₖ(z) = Aₖ / (1 - 2rₖcos(ωₖ)z⁻¹ + rₖ²z⁻²)
```

- `ωₖ` : k 番目のモード周波数
- `rₖ` : 減衰係数（Q 値に対応）
- `Aₖ` : 励振点でのモード形状の重み

インパルス応答 = `Σ Aₖ · rₖⁿ · sin(ωₖ · n)`

```python
def modal_synth(modes, duration, sample_rate=44100):
    """モーダル合成
    modes: [(freq_hz, decay_sec, amplitude), ...]
    """
    n   = int(duration * sample_rate)
    out = np.zeros(n)
    t   = np.arange(n)
    for freq, decay_time, amp in modes:
        omega = 2*np.pi*freq / sample_rate
        r     = np.exp(-1.0 / (decay_time * sample_rate))
        out  += amp * (r ** t) * np.sin(omega * t)
    return out


# 鐘のモード例（非整数倍音列）
BELL_MODES = [
    (440,  5.0, 1.0),
    (1050, 3.0, 0.6),
    (1680, 2.0, 0.3),
    (2250, 1.5, 0.2),
]
```

### KS / DWG との違い

- KS/DWG は**波の伝播**をモデル化（分散モデル）
- Modal は**共鳴周波数の重ね合わせ**（モードモデル）
- Modal は任意形状の振動体に対してモード解析さえできれば実装可能

---

## 4. FDTD（有限差分時間領域）法

時間・空間の偏微分を差分で近似し、波動方程式をグリッド上で数値解析する手法。  
2D/3D の空間的音場シミュレーションが可能で、任意形状の物理系をモデル化できる。

| 比較項目 | DWG | FDTD |
|---|---|---|
| 計算コスト | 低〜中 | 高（グリッド全体） |
| 柔軟性 | 1D 波動のみ | 任意の 2D/3D 空間 |
| 主な用途 | 楽器音のリアルタイム合成 | 音響空間のシミュレーション |

---

## 5. WDF（Wave Digital Filter）

集中定数アナログ回路（抵抗・コンデンサ・インダクタ）を波動変数（入射波・反射波）で表現したデジタルフィルター。  
アナログ回路の**非線形特性**をデジタルで精密にエミュレートするために使用される。

- Moog ラダーフィルター、真空管回路のデジタル再現に活用
- WDF-NL（非線形 WDF）でダイオードクリッピング等も実装可能
- 「Virtually Analog」な音色再現の理論的基盤

---

## 6. 位相ボコーダー（Phase Vocoder）

1966 年に Flanagan & Golden が開発。STFT で分析・操作・再合成することで音を変換する。

### タイムストレッチの原理

分析ホップサイズ `Ha` と合成ホップサイズ `Hs` の比がストレッチ率。  
`Hs/Ha > 1` → 時間伸長（遅くなる）、`Hs/Ha < 1` → 時間圧縮（速くなる）。  
**位相連続性の保持**が音質のカギ。

```python
def phase_vocoder_stretch(audio, stretch, n_fft=2048, hop=512, sample_rate=44100):
    """位相ボコーダーによるタイムストレッチ"""
    hop_out    = int(hop * stretch)
    window     = np.hanning(n_fft)
    n_out      = int(len(audio) * stretch)
    output     = np.zeros(n_out + n_fft)
    phase_acc  = np.zeros(n_fft//2 + 1)
    prev_phase = np.zeros(n_fft//2 + 1)
    omega      = 2*np.pi * np.arange(n_fft//2 + 1) * hop / n_fft

    a_pos = s_pos = 0
    while a_pos + n_fft <= len(audio):
        spec    = np.fft.rfft(audio[a_pos:a_pos+n_fft] * window)
        mag, ph = np.abs(spec), np.angle(spec)
        d_ph    = ph - prev_phase - omega
        d_ph    = ((d_ph + np.pi) % (2*np.pi)) - np.pi   # ラッピング
        prev_phase = ph.copy()
        phase_acc += d_ph * stretch + omega * stretch
        synth = mag * np.exp(1j * phase_acc)
        frame = np.fft.irfft(synth) * window
        output[s_pos:s_pos+n_fft] += frame
        a_pos += hop
        s_pos += hop_out

    return output[:n_out]
```

### 主な応用

| 応用 | 方法 |
|---|---|
| タイムストレッチ | `Ha ≠ Hs` で時間のみ変換 |
| ピッチシフト | 合成後に再サンプリング |
| モーフィング | 2 音のスペクトルを線形補間 |
| ロボット声 | 位相をランダム化（位相情報を破棄） |

---

## 7. SMS（Spectral Modeling Synthesis）

Xavier Serra（Stanford CCRMA, 1989）が開発。音を「正弦波成分 + 確率的残差」にモデル化する。

### モデル

```
元の音 = [正弦波トラック群（Sinusoidal）] + [残差（Stochastic / Noise）]
```

1. **分析**: STFT → スペクトルピーク検出 → ピーク追跡で正弦波トラックを形成
2. **残差**: 元の音から再合成した正弦波を引き算 → 残差をフィルタードノイズとしてモデル化
3. **合成**: トラックを逆 FFT で合成 + フィルタードノイズを加算

### KS / DWG / Modal との比較

| 項目 | KS / DWG / Modal | SMS |
|---|---|---|
| アプローチ | 物理現象のモデル化 | 録音音の分析・再合成 |
| 制御 | 物理パラメーター | スペクトルパラメーター |
| 任意の音源 | 不可 | 可（分析が先に必要） |
| リアルタイム性 | 高い | 難しい（高計算コスト） |

---

## 8. PSOLA（Pitch Synchronous Overlap and Add）

音声の**ピッチに同期**しながらオーバーラップアッドを行う技術。音声の韻律変換（ピッチ・時間変換）に使用。

### TD-PSOLA（時間領域 PSOLA）

1. 基音周期に同期した分析マーク（グリルカード）を設定
2. 各マーク周辺の波形を約 2 基音周期で切り出す
3. 新しいピッチ / 時間に応じてオーバーラップアッドで再合成

音声合成（TTS）の韻律変換や歌声編集（Auto-Tune の原理的基礎）に使われる。

---

## 9. グラニュラー合成

Dennis Gabor（1947）の量子論的音響理論に由来。  
音を 1〜100 ms の微小な断片（グレイン）に分割・再構成することで新しい音を生成する。

### グレインのパラメーター

| パラメーター | 説明 | 典型的な範囲 |
|---|---|---|
| Grain Size | グレインの長さ | 1〜200 ms |
| Grain Pitch | ピッチ変換率 | ±2 オクターブ |
| Density | 1 秒あたりのグレイン数 | 1〜200 |
| Position | ソース内の読み出し位置 | 0.0〜1.0 |
| Scatter | 位置のランダム散布量 | 0.0〜1.0 |
| Envelope | グレインのフェードイン/アウト | Hanning・Gaussian |

### 非同期 vs 同期グラニュラー

| 種類 | 特徴 |
|---|---|
| 同期（Synchronous） | 規則的タイミング。より予測可能な音色 |
| 非同期（Asynchronous） | ランダムなタイミング。霧のような質感（Truax の「グレインクラウド」） |

### 実装

```python
def granular(source, grain_ms, density, position,
             pitch=1.0, scatter=0.1, duration=2.0, sample_rate=44100):
    """グラニュラー合成"""
    g_size   = int(grain_ms * sample_rate / 1000)
    n_out    = int(duration * sample_rate)
    output   = np.zeros(n_out)
    interval = int(sample_rate / density)
    env      = np.hanning(g_size)
    cur      = 0

    while cur < n_out:
        base   = int(position * len(source))
        jitter = int(scatter * g_size * (np.random.rand()*2 - 1))
        src    = max(0, min(base + jitter, len(source) - g_size))
        grain  = source[src:src + g_size].copy()

        if pitch != 1.0:
            new_size = int(g_size / pitch)
            grain    = np.interp(np.linspace(0, 1, new_size),
                                 np.linspace(0, 1, g_size), grain)

        g_env  = np.hanning(len(grain))
        grain *= g_env
        end    = min(cur + len(grain), n_out)
        output[cur:end] += grain[:end - cur]
        cur += max(1, int(interval * (1 + 0.1*np.random.randn())))

    return output


def granular_timestretch(audio, stretch, grain_ms=50, overlap=4, sample_rate=44100):
    """グラニュラーによるタイムストレッチ"""
    g_size   = int(grain_ms * sample_rate / 1000)
    hop_a    = g_size // overlap
    hop_s    = int(hop_a * stretch)
    n_out    = int(len(audio) * stretch)
    output   = np.zeros(n_out + g_size)
    env      = np.hanning(g_size)
    a_pos = s_pos = 0

    while a_pos + g_size <= len(audio) and s_pos + g_size <= n_out:
        output[s_pos:s_pos + g_size] += audio[a_pos:a_pos + g_size] * env
        a_pos += hop_a
        s_pos += hop_s

    return output[:n_out]
```

### タイムストレッチとピッチシフトへの応用

- **タイムストレッチ**: ソース読み出し速度はそのまま、グレイン間隔だけ変える → 速度を変えずにピッチを保持
- **ピッチシフト**: ソース速度を変えずにグレインのリサンプリングでピッチを変換 → 音長を変えずにピッチを変換

---

[← 概要に戻る](synthesis-overview.md)
