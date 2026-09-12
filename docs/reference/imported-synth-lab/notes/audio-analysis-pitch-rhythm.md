# ピッチ推定・リズム解析

---

## 1. ピッチ・基本周波数（F0）推定

単音の基本周波数を推定する手法。  
いずれも「倍音列の周期性」を異なる方法で検出するという共通の原理を持つ。

### ACF（自己相関法）

**何が分かるか**: 波形の周期性から基本周波数を推定する最もシンプルな手法。

```
r[τ] = Σ_n x[n] · x[n + τ]
```

最初の顕著なピークの遅延 τ が基本周期 T₀ = τ / Fs。

```python
def autocorr_f0(signal, sample_rate, min_hz=80, max_hz=800):
    corr = np.correlate(signal, signal, 'full')[len(signal)-1:]
    lo = int(sample_rate / max_hz)
    hi = int(sample_rate / min_hz)
    peak_lag = lo + np.argmax(corr[lo:hi])
    return sample_rate / peak_lag
```

**欠点**: オクターブエラー（基音を誤って2倍周波数で検出）が起きやすい。

---

### YIN アルゴリズム

**何が分かるか**: 自己相関ベースの改良版。オクターブエラーを軽減した実用的な F0 推定。

**計算ステップ**

1. 差分関数 `d[τ] = Σ(x[n] - x[n+τ])²`
2. 累積平均正規化差分関数（CMNDF）
3. パラボリック補間で精度向上

```python
# scipy のみで自前実装可能（差分関数ベース）
# librosa を使う場合：
# f0 = librosa.yin(y, fmin=80, fmax=2000)
```

---

### PYIN（Probabilistic YIN）

**何が分かるか**: YIN を確率論的に拡張。隠れマルコフモデル（HMM）＋ビタビデコーディングで有声/無声判定を同時に実施。  
現在の実用標準的な F0 推定法。

```python
# f0 は有声区間のみ、無声区間は NaN
# f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=80, fmax=2000, sr=sr)
```

---

### HPS（Harmonic Product Spectrum、高調波積スペクトル）

**何が分かるか**: FFT スペクトルを倍数周波数で折り畳んで積を取り、基本周波数成分を強調する。多重倍音のある楽器音に有効。

```
HPS(f) = |X(f)| · |X(2f)| · |X(3f)| · ... · |X(Hf)|
```

```python
def hps(signal, sample_rate, n_harmonics=5):
    X = np.abs(np.fft.rfft(signal))
    result = X.copy()
    for h in range(2, n_harmonics + 1):
        downsampled = X[::h]
        result[:len(downsampled)] *= downsampled
    N = len(signal)
    df = sample_rate / N
    return np.argmax(result[:N//2]) * df
```

---

### ケプストラム法

**何が分かるか**: スペクトルの対数を IFFT することで、ピッチ（基本周期）と声道特性（フォルマント）を分離して推定。  
ケフレンシー軸の顕著なピーク位置 = 1/F0。

```
c[n] = IFFT{ log|X(f)| }
```

倍音列が周期 f₀ で並ぶと、その対数スペクトルも周期的になる → ケプストラムにピークが立つ。

---

### CREPE（深層学習ベース）

**何が分かるか**: 畳み込みニューラルネットワーク（CNN）による F0 推定。PYIN より高精度。ノイズ環境や声楽に対して頑健。

```python
# pip install crepe
# time, freq, confidence, activation = crepe.predict(y, sr, viterbi=True)
```

---

### F0 推定手法の比較

| 手法 | 精度 | 計算速度 | ノイズ耐性 | 特記 |
|---|---|---|---|---|
| ACF | 中 | 最速 | 低 | オクターブエラーあり |
| YIN | 高 | 速い | 中 | 実装が容易 |
| PYIN | 非常に高 | 中 | 高 | 現在の標準手法 |
| HPS | 中 | 速い | 低 | 多倍音楽器に強い |
| ケプストラム | 中 | 速い | 中 | フォルマント分離も同時に可 |
| CREPE | 最高 | 低速（GPU推奨） | 非常に高 | 追加インストールが必要 |

---

## 2. リズム・テンポ解析

### オンセット検出（Onset Detection）

**何が分かるか**: 音の立ち上がり（アタック開始点）の時刻。ビートトラッキング・音符の分節化・リズムパターン解析の前処理。

**主要なオンセット検出関数（ODF）**

| 手法 | 計算方法 | 適した音源 |
|---|---|---|
| スペクトルフラックス | フレーム間のスペクトル変化量 | 全般 |
| HFC（高周波成分） | 高周波エネルギーの急増 | 打楽器 |
| 複素領域法 | 位相変化 + 振幅変化 | 有声音 |
| 位相偏差 | 位相の 2 次差分 | 有声音 |
| RMS エネルギー微分 | RMS の急増 | トランジェント全般 |

**実装（スペクトルフラックスによるオンセット検出）**

```python
from scipy.signal import find_peaks

def spectral_flux_onset(signal, sample_rate, n_fft=2048, hop=512):
    """正方向スペクトルフラックスによるオンセット強度の計算"""
    frames = [
        np.abs(np.fft.rfft(signal[i:i+n_fft] * np.hanning(n_fft)))
        for i in range(0, len(signal) - n_fft, hop)
    ]
    flux = np.array([
        np.sum(np.maximum(frames[i] - frames[i-1], 0) ** 2)
        for i in range(1, len(frames))
    ])
    # 正規化 + ピーク検出
    flux /= flux.max()
    peaks, _ = find_peaks(flux, distance=int(0.1 * sample_rate / hop), height=0.1)
    onset_times = peaks * hop / sample_rate
    return onset_times, flux
```

---

### BPM 推定・テンポ推定

**何が分かるか**: 音楽の 1 分あたりの拍数（テンポ）。

**アルゴリズム（自己相関ベース）**

1. オンセット強度包絡を計算
2. 自己相関 or フーリエ変換で周期性を検出
3. BPM 範囲（通常 60〜200 BPM）内のピークを BPM に変換

```python
def estimate_bpm(onset_env, sample_rate, hop_size, bpm_range=(60, 200)):
    """自己相関によるテンポ推定"""
    corr = np.correlate(onset_env, onset_env, 'full')[len(onset_env)-1:]
    # BPM範囲をラグ範囲に変換
    lo = int(60 / bpm_range[1] * sample_rate / hop_size)
    hi = int(60 / bpm_range[0] * sample_rate / hop_size)
    best_lag = lo + np.argmax(corr[lo:hi])
    bpm = 60 / (best_lag * hop_size / sample_rate)
    return bpm
```

**テンポグラム**: 時間ごとのテンポ分布を2次元で表現したもの。テンポが変化する曲の解析に使う。

---

### ビートトラッキング

**何が分かるか**: 拍（ビート）の位置を連続的に追跡。テンポが揺れるパフォーマンス音源に対応できる。

**主要アルゴリズム**

| 手法 | 概要 | 特徴 |
|---|---|---|
| 動的計画法（Ellis 2007） | ビート間隔の滑らかさを最適化 | 古典的手法。librosa 標準 |
| PLP（Predominant Local Pulse） | 複数テンポ候補を統合 | 頑健性が高い |
| RNN + CRF（madmom） | 深層学習による追跡 | 現在の最高精度 |

---

### ダウンビート・小節解析

**何が分かるか**: 小節の先頭拍（ダウンビート）の検出と拍子（4/4、3/4 等）の推定。  
コード進行解析や楽曲構造分析の前処理として使われる。

---

## リズム解析のフロー

```
音声入力
  │
  ├─ オンセット強度包絡を計算（スペクトルフラックス等）
  │
  ├─ BPM 推定（自己相関 / フーリエ変換）
  │
  ├─ ビートトラッキング（動的計画法 / PLP / RNN）
  │
  └─ ダウンビート検出 → 小節・拍子の特定
```

---

[← 概要に戻る](audio-analysis-overview.md)
