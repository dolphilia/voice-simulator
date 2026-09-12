# 高度・特殊な解析手法

シンセサイザー研究において特に関連が深い、より専門的な解析手法をまとめる。

---

## 1. ラフネス（Roughness、粗さ）

**何が分かるか**  
音の「ざらつき感」。2音の差音が 20〜300 Hz の範囲に収まると発生する知覚的な不協和感。  
音楽の協和/不協和を客観的に定量化できる。FM合成・AM合成・ウェーブシェーピングの音色設計で非常に重要。

**Sethares（1993）モデル**

```
Roughness = Σ_{i,j} A_i · A_j · f(|f_i - f_j|)
f(x) = e^(-a·x) - e^(-b·x)   ただし x = |Δf| / (0.021 · min(f_i, f_j) + 19)
a = 3.5, b = 5.75
```

```python
def roughness_sethares(freqs, amps):
    roughness = 0.0
    a, b = 3.5, 5.75
    for i in range(len(freqs)):
        for j in range(i + 1, len(freqs)):
            denom = 0.021 * min(freqs[i], freqs[j]) + 19
            x = abs(freqs[j] - freqs[i]) / denom
            r = amps[i] * amps[j] * (np.exp(-a * x) - np.exp(-b * x))
            roughness += max(0.0, r)
    return roughness
```

**応用**
- 倍音列の間隔（= 音律・チューニング）と粗さの関係を可視化
- FM合成の C:M 比（Carrier:Modulator）ごとの粗さを比較
- 和音の協和性（コンソナンス）の定量評価

---

## 2. 非調和性（Inharmonicity）

**何が分かるか**  
倍音が純整数倍（f₀, 2f₀, 3f₀...）からどれだけ逸脱しているか。ピアノ高音域・金属打楽器・ベルで顕著に現れる。  
シンセサイザーの FM/AM パラメータや物理モデリングの非線形性の解析指標になる。

```
B = Σ_{n=1}^{N} |f_n - n · f₀|² / (n · f₀)²  · (A_n / Σ A_k)
```

```python
def inharmonicity(f0, partials_freq, partials_amp):
    """振幅加重の非調和性指標"""
    expected = f0 * np.arange(1, len(partials_freq) + 1)
    weights  = partials_amp / np.sum(partials_amp)
    return np.sum(weights * ((partials_freq - expected) / expected) ** 2)
```

---

## 3. スペクトルエントロピー

**何が分かるか**  
スペクトルの一様性・複雑さ。純音（単一正弦波）→ 最小。白色雑音 → 最大。  
音のテクスチャ分類（音声 / 音楽 / 環境音の区別）に使われる。

```
H = -Σ P_k · log₂(P_k)   ただし P_k = |X[k]|² / Σ|X[k]|²
```

```python
def spectral_entropy(signal, n_fft=2048):
    X     = np.abs(np.fft.rfft(signal * np.hanning(len(signal)))) ** 2
    P     = X / (np.sum(X) + 1e-10)
    return -np.sum(P * np.log2(P + 1e-10))
```

**フラットネスとの違い**: フラットネスは幾何/算術平均比（0〜1）、エントロピーはシャノン情報量（単位: ビット）。

---

## 4. 位相スペクトル・グループ遅延

### 位相スペクトル

**何が分かるか**  
各周波数成分の時間的な「ズレ」。人間の聴覚には振幅スペクトルほど敏感でないが、信号の再合成・音質評価では不可欠。

```python
X         = np.fft.rfft(signal * np.hanning(len(signal)))
phase     = np.angle(X)
unwrapped = np.unwrap(phase)

# 瞬時周波数（位相の時間微分）
hop = 512
IF = np.diff(unwrapped_phase_in_stft, axis=1) * sample_rate / (2 * np.pi * hop)
```

### グループ遅延（Group Delay）

**何が分かるか**  
周波数ごとの信号遅延量（位相の周波数微分）。スペクトル包絡のより精密な推定に利用。MFCC と組み合わせて音声認識で使われることがある。

```
τ(ω) = -d(phase) / dω
```

```python
def group_delay(signal, sample_rate):
    X     = np.fft.rfft(signal)
    phase = np.unwrap(np.angle(X))
    freqs = np.fft.rfftfreq(len(signal), 1 / sample_rate)
    gd    = -np.gradient(phase, freqs[1] - freqs[0])
    return freqs, gd
```

---

## 5. バイスペクトル（Bispectrum）

**何が分かるか**  
3次統計量のフーリエ変換。**非線形相互作用**（2次位相結合）を検出する。  
ガウス性・線形性からの逸脱の定量化に使える。  
FM 合成・ウェーブシェーパー・ディストーションなど非線形シンセシスの特性解析に特に有用。

```
B(f₁, f₂) = E[ X(f₁) · X(f₂) · X*(f₁+f₂) ]
```

通常のパワースペクトル（2次統計量）では見えない、2つの周波数成分が相互作用して新たな周波数を生む様子を可視化できる。

```python
def bispectrum(signal, n_fft=512):
    X = np.fft.fft(signal, n_fft)
    N = n_fft // 2
    B = np.zeros((N, N), dtype=complex)
    for k1 in range(N):
        for k2 in range(k1, N):
            k3 = (k1 + k2) % n_fft
            B[k1, k2] = X[k1] * X[k2] * np.conj(X[k3])
    return B
```

**注意**: 計算量が O(N²) になるため、フレームを短く切り取ってから適用するのが現実的。

---

## 6. 非線形解析

Karplus-Strong のような再帰的フィードバック系や、ウェーブシェーピング・オーバードライブは非線形系であり、線形解析（FFT等）だけでは特性を捉えきれない。

### 最大リアプノフ指数（Lyapunov Exponent）

```python
# pip install nolds
import nolds
le = nolds.lyap_r(signal, emb_dim=10)
# 正の値 → カオス的。負の値 → 安定な周期運動
```

### フラクタル次元・ハースト指数

```python
hurst   = nolds.hurst_rs(signal)       # 0.5 = ランダム, 1.0 = 強い持続性
corr_d  = nolds.corr_dim(signal, emb_dim=10)  # 相関次元
dfa_exp = nolds.dfa(signal)             # デトレンド変動解析
```

### 再帰定量化解析（RQA）

時系列の再帰パターンを 2D マップ（再帰プロット）で可視化・定量化する。  
リズムの周期性・複雑さ・非定常性の解析に使われる。

---

## シンセサイザー研究への応用マトリクス

| 合成手法 | 特に有効な解析 |
|---|---|
| Karplus-Strong | 倍音解析・非調和性・RMS エンベロープ・スペクトログラム |
| FM 合成 | バイスペクトル・ラフネス・スペクトルフラットネス |
| グラニュラー | スペクトルエントロピー・ZCR・スペクトログラム |
| 物理モデリング | 非調和性・ケプストラム・位相スペクトル |
| アナログシミュレーション | グループ遅延・LPC・フォルマント解析 |
| PCM / ウェーブテーブル | MFCC・クロマ・Mel スペクトログラム |

---

[← 概要に戻る](audio-analysis-overview.md)
