# 流体力学・流体音響学による音生成

---

## 1. Navier-Stokes 方程式と音響

### 基本方程式

非圧縮性流体の Navier-Stokes 方程式：

```
∂u/∂t + (u·∇)u = -∇p/ρ + ν∇²u
∇·u = 0
```

- `u` : 速度場ベクトル
- `p` : 圧力
- `ρ` : 密度
- `ν` : 動粘性係数

圧縮性流体になると密度変動が音波として伝播する。音速 `c₀` は：

```
c₀ = √(γp₀/ρ₀)   （等エントロピー条件）
```

### 音響方程式への線形化

微小擾乱（`u = u₀ + u'`, `p = p₀ + p'`, `ρ = ρ₀ + ρ'`）に対して線形化すると：

```
∂²p'/∂t² - c₀²∇²p' = 0   （均一媒質の波動方程式）
```

---

## 2. ライトヒルのアナロジー（Lighthill's Acoustic Analogy）

**M. J. Lighthill（1952）** が提案した、乱流から生成される音を記述する理論。

### 支配方程式

```
∂²ρ'/∂t² - c₀²∇²ρ' = ∂²Tᵢⱼ/∂xᵢ∂xⱼ
```

右辺の `Tᵢⱼ` は **ライトヒルテンソル（音響源項）**：

```
Tᵢⱼ = ρuᵢuⱼ + (p' - c₀²ρ')δᵢⱼ - τᵢⱼ
```

- 第1項 `ρuᵢuⱼ` : 乱流レイノルズ応力（主要音源）
- 第2項 : 圧力・密度変動
- 第3項 `τᵢⱼ` : 粘性応力テンソル

### 音のスケーリング則

| 音源タイプ | スケーリング | 例 |
|---|---|---|
| 四重極子（自由乱流） | P ∝ U⁸ / c₀⁵ | ジェット噴流 |
| 双極子（固体表面）  | P ∝ U⁶ / c₀³ | 翼端渦・風切り音 |
| 単極子（体積変動）  | P ∝ U⁴ / c₀  | 燃焼・気泡崩壊 |

フルートの発音は**双極子型**に近く、エッジトーンがその典型。

### 簡易シミュレーション

```python
import numpy as np
import scipy.signal as signal

def lighthill_jet_sound(U, sample_rate=44100, duration=1.0):
    """
    ライトヒルのアナロジーに基づく簡易ジェット音生成。
    U: 流速 [m/s]、U⁸スケーリングで音のパワーを近似。
    実際の流場計算は省略し、乱流をフィルタリングしたノイズで模倣。
    """
    n = int(sample_rate * duration)

    # 乱流の時間スケール: L/U (乱流積分スケール L ≈ 0.01 m)
    L = 0.01
    tau_turb = L / max(U, 1e-9)
    fc = 1.0 / tau_turb  # 乱流の特性周波数

    # ホワイトノイズを乱流スペクトルに整形
    noise = np.random.randn(n)
    fc_normalized = min(fc / (sample_rate / 2), 0.99)
    b, a = signal.butter(2, fc_normalized, btype='low')
    turb = signal.lfilter(b, a, noise)

    # ライトヒルのU⁸スケーリング（空気音速 340 m/s として規格化）
    c0 = 340.0
    amplitude = (U / c0) ** 4  # ∝ U^8 / c0^5 の簡易近似

    out = amplitude * turb
    peak = np.max(np.abs(out))
    return out / peak if peak > 0 else out
```

---

## 3. 渦音理論（Vortex Sound Theory）

### エッジトーン（Edge Tone）

気流がエッジに当たって交互に上下に分岐する **Kelvin-Helmholtz 不安定** により周期的な渦が生成され、音が発生する。フルート・リコーダーの発音原理。

```
f_edge ≈ U / (2·δ·n)

U : 気流速度
δ : エッジまでの距離
n : モード番号（1, 2, 3, ...）
```

### Kármán 渦列

円柱後流に形成される周期的な渦列（Kármán Vortex Street）が電線の風切り音を生成。

```
St = f·d/U ≈ 0.21   （Strouhal 数、d: 円柱直径）
```

```python
def karman_vortex_sound(U, d, sample_rate=44100, duration=1.0):
    """
    カルマン渦列による風切り音生成。
    Strouhal数 St ≈ 0.21 を使用して基本周波数を計算。
    """
    St = 0.21
    f_karman = St * U / d

    n = int(sample_rate * duration)
    t = np.arange(n) / sample_rate

    # 基本周波数＋乱れ成分
    noise = np.random.randn(n) * 0.1
    b, a = signal.butter(2, f_karman * 2 / (sample_rate / 2))
    noise = signal.lfilter(b, a, noise)

    # 擬似周期音＋乱れ
    out = np.sin(2 * np.pi * f_karman * t) + noise

    # 幅広いスペクトルに整形（渦の不規則性）
    b2, a2 = signal.butter(2, [f_karman * 0.5 / (sample_rate / 2),
                                min(f_karman * 3 / (sample_rate / 2), 0.99)],
                           btype='band')
    out = signal.lfilter(b2, a2, out)
    return out / (np.max(np.abs(out)) + 1e-9)
```

### 渦の音響効率

ポールの公式（Powell 1964）による渦音の音響パワー：

```
W ≈ ρ·U⁶ / (12π·c₀³·L²)   （L: 渦のスケール）
```

---

## 4. 格子ボルツマン法（Lattice Boltzmann Method: LBM）

### 概要

流体分子の確率分布関数を離散化した格子上で時間発展させる数値流体力学手法。  
Navier-Stokes 方程式を直接解かずに、**粒子の衝突・移流**のルールから巨視的流体現象を再現する。

音響シミュレーションへの応用では、圧力擾乱の伝播を直接捉えることができる。

### D2Q9 モデル（2次元・9速度）

```
格子速度ベクトル（c_i, i = 0..8）:
  c₀ = (0,0)
  c₁ = (1,0),  c₂ = (0,1),  c₃ = (-1,0), c₄ = (0,-1)
  c₅ = (1,1),  c₆ = (-1,1), c₇ = (-1,-1), c₈ = (1,-1)
```

LBM の基本方程式：

```
f_i(x + c_i·Δt, t + Δt) = f_i(x, t) - [f_i - f_i^eq] / τ
```

- `f_i` : 分布関数
- `f_i^eq` : 平衡分布関数（Maxwell-Boltzmann 分布の離散近似）
- `τ` : 緩和時間（粘性に対応）

### 平衡分布関数

```
f_i^eq = w_i · ρ · [1 + 3(c_i·u)/c² + 9(c_i·u)²/(2c⁴) - 3u²/(2c²)]
```

| 方向 | 重み w_i |
|---|---|
| 静止（i=0） | 4/9 |
| 軸方向（i=1-4） | 1/9 |
| 対角方向（i=5-8） | 1/36 |

### Python 実装（簡易 2D LBM）

```python
import numpy as np

def lbm_2d_acoustic(nx=200, ny=100, n_steps=1000,
                    tau=0.6, c_s=1/np.sqrt(3)):
    """
    D2Q9 格子ボルツマン法による2D音響シミュレーション。
    圧力パルスを中心に配置して音波の伝播を観察する。
    """
    # D2Q9 速度ベクトルと重み
    e = np.array([[0,0],[1,0],[0,1],[-1,0],[0,-1],
                  [1,1],[-1,1],[-1,-1],[1,-1]])
    w = np.array([4/9, 1/9, 1/9, 1/9, 1/9,
                  1/36, 1/36, 1/36, 1/36])

    # 初期化（密度=1, 速度=0）
    rho = np.ones((nx, ny))
    ux  = np.zeros((nx, ny))
    uy  = np.zeros((nx, ny))

    # 中心に圧力パルスを配置
    cx, cy = nx // 2, ny // 2
    rho[cx-2:cx+2, cy-2:cy+2] += 0.1

    def feq(rho, ux, uy):
        """平衡分布関数の計算"""
        f = np.zeros((9, nx, ny))
        for i in range(9):
            eu = e[i,0] * ux + e[i,1] * uy
            f[i] = w[i] * rho * (1 + 3*eu + 4.5*eu**2 - 1.5*(ux**2 + uy**2))
        return f

    f = feq(rho, ux, uy)
    pressure_history = []

    for step in range(n_steps):
        # 衝突ステップ
        f_eq = feq(rho, ux, uy)
        f = f - (f - f_eq) / tau

        # 移流ステップ
        f_new = np.zeros_like(f)
        for i in range(9):
            f_new[i] = np.roll(np.roll(f[i], e[i,0], axis=0), e[i,1], axis=1)
        f = f_new

        # マクロ量の更新
        rho = np.sum(f, axis=0)
        ux  = np.sum(f * e[:,0,np.newaxis,np.newaxis], axis=0) / rho
        uy  = np.sum(f * e[:,1,np.newaxis,np.newaxis], axis=0) / rho

        # 観測点（端部）での圧力を記録
        pressure_history.append(rho[nx-5, cy] - 1.0)

    return np.array(pressure_history)
```

### 音響 LBM の特徴

| 特徴 | 詳細 |
|---|---|
| 並列化 | GPUに非常に適している（各格子点が独立して計算） |
| 境界条件 | 複雑形状の壁面・開口端を格子で表現 |
| 音速 | 格子音速 `c_s = c / √3`（`c`: 格子速度）に固定 |
| 非線形効果 | 弱い非線形音響まで対応可能 |
| 主な制約 | 低マッハ数（Ma < 0.3）に限定 |

### 応用：フルートの発音シミュレーション

```
[気流入口] → [唇の形状（形状境界）] → [エッジ] → [管腔] → [開口端（放射）]
                                           ↑
                                       渦の形成・崩壊 → 音響励振
```

- 管内の気柱共鳴と渦音源の相互作用を LBM で直接シミュレート
- 格子解像度：エッジ付近は 0.1 mm 以下が必要（高コスト）
- GPU（CUDA/OpenCL）を使用して実用的な計算時間を実現

### 推奨ライブラリ

| ライブラリ | 特徴 |
|---|---|
| `pylbm` | Python ネイティブ LBM、学習用途に最適 |
| `lettuce` | PyTorch ベース、GPU 対応 |
| `OpenLB` | C++ 実装、研究・HPC 用途 |
| `palabos` | 高機能 C++ LBM フレームワーク |

---

## 5. DNS（直接数値シミュレーション）

Navier-Stokes 方程式をコルモゴロフスケールまで解像して乱流を直接解析する手法。  
格子ボルツマン法や有限差分法で実装されることが多い。

### 要求計算量

```
必要格子点数 ∝ Re^(9/4)  （Re: レイノルズ数）

フルートの実際の管内流 Re ≈ 10^4 → 格子点数 ≈ 10^9
```

---

## 6. 実践的な音生成パイプライン

### 簡易フルート音生成（物理ベース近似）

```python
def flute_physical_model(f0, breath_pressure, duration=2.0, sample_rate=44100):
    """
    簡易フルート物理モデル。
    気流 → エッジトーン励振 → 管腔共鳴のフィードバックループを簡略化。
    """
    n = int(sample_rate * duration)
    # 管長から基音周波数を計算（両端開管: L = c/(2f)）
    c0 = 343.0  # 音速 m/s
    tube_length = c0 / (2 * f0)
    delay_samples = int(sample_rate * tube_length / c0)
    delay_samples = max(2, delay_samples)

    # ホワイトノイズ（乱流励振）
    noise = np.random.randn(n) * breath_pressure

    # 非線形エッジ応答（気流の折り返し効果）
    def edge_nonlinearity(x, threshold=0.5):
        return np.tanh(x / threshold) * threshold

    # 遅延フィードバックによる管腔共鳴
    output = np.zeros(n + delay_samples)
    for i in range(n):
        excitation = edge_nonlinearity(noise[i] + 0.4 * output[i])
        output[i + delay_samples] = excitation * 0.98

    out = output[delay_samples:delay_samples + n]

    # ハイパスフィルター（直流成分除去）
    b, a = signal.butter(1, 20 / (sample_rate / 2), btype='high')
    out = signal.lfilter(b, a, out)

    peak = np.max(np.abs(out))
    return out / peak if peak > 0 else out
```

---

## 参考文献・リソース

| 資料 | 内容 |
|---|---|
| Lighthill (1952) "On Sound Generated Aerodynamically" | ライトヒルアナロジーの原著論文 |
| Powell (1964) "Theory of Vortex Sound" | 渦音理論 |
| Howe (2003) "Theory of Vortex Sound" | 教科書（Cambridge） |
| Aidun & Clausen (2010) "Lattice-Boltzmann Method" | LBM の包括的レビュー |
| Kühnelt (2007) "Simulating the mechanism of sound generation..." | LBM によるフルート発音シミュレーション |

---

[← 概要に戻る](sound-from-physics-overview.md)
