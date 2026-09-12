# 弾性体振動・非線形力学・確率過程による音生成

---

## 1. 薄板・シェルの振動方程式

### Kirchhoff-Love 薄板理論

等方性薄板の曲げ振動を記述する Kirchhoff 方程式：

```
D·∇⁴w + ρh·∂²w/∂t² = p(x,y,t)

D = Eh³ / [12(1-ν²)]   （曲げ剛性）
```

- `w(x,y,t)` : 板の法線方向変位
- `D` : 曲げ剛性
- `E` : ヤング率、`ν` : ポアソン比、`h` : 板厚、`ρ` : 密度
- `p` : 外力

### 固有周波数の解析解

矩形板（両端固定）の固有周波数：

```
f_mn = π/(2L²) · √(D/ρh) · (m² + (L/W)²·n²)

m, n: 振動モード番号
L, W: 板の縦横寸法
```

**非整数倍音列**が特徴 → ベル・シンバル・太鼓の音響特性

```python
import numpy as np
from scipy.integrate import solve_ivp

def rectangular_plate_modes(L, W, h, E, nu, rho, n_modes=20):
    """
    矩形薄板のモーダル解析（解析解）。
    固有周波数と相対振幅（エッジ打撃）を返す。
    """
    D = E * h**3 / (12 * (1 - nu**2))
    modes = []
    for m in range(1, n_modes + 1):
        for n in range(1, n_modes + 1):
            # 固有周波数 [Hz]
            f_mn = (np.pi / (2 * L**2)) * np.sqrt(D / (rho * h)) * \
                   (m**2 + (L/W)**2 * n**2)
            # モード形状の節線数に基づく相対振幅（打撃点 = 中心）
            amp = (np.sin(m * np.pi / 2) * np.sin(n * np.pi / 2)) ** 2
            if amp > 1e-6:
                modes.append((f_mn, amp))

    modes.sort()
    modes = modes[:n_modes]
    return modes


def plate_modal_synth(modes, duration=3.0, sample_rate=44100, damping=0.001):
    """
    薄板のモーダル合成（解析モードを直接使用）。
    """
    n = int(duration * sample_rate)
    out = np.zeros(n)
    t = np.arange(n) / sample_rate

    for freq, amp in modes:
        decay_time = 1.0 / (damping * freq + 0.1)
        r = np.exp(-1.0 / (decay_time * sample_rate))
        omega = 2 * np.pi * freq / sample_rate
        out += amp * (r ** np.arange(n)) * np.sin(omega * np.arange(n))

    return out / (np.max(np.abs(out)) + 1e-9)


# 使用例: スチール製シンバル相当の板
STEEL_CYMBAL = {
    'L': 0.4, 'W': 0.4,  # 40 cm 正方形
    'h': 0.001,           # 1 mm 厚
    'E': 200e9,           # ヤング率（鋼）
    'nu': 0.3,            # ポアソン比
    'rho': 7800           # 密度 [kg/m³]
}
```

### FEM（有限要素法）との比較

| 手法 | 精度 | 計算コスト | 形状の自由度 |
|---|---|---|---|
| 解析解（矩形板） | 高（矩形のみ） | 非常に低い | 矩形のみ |
| FEM（FEniCS）  | 非常に高い     | 高い        | 任意形状    |
| LBM（2D/3D）  | 高い           | 非常に高い  | 任意形状    |

---

## 2. 弦の非線形大変位振動

### 線形弦の波動方程式

```
∂²y/∂t² = c²·∂²y/∂x²   （c = √(T/μ)）

T: 張力、μ: 線密度
```

### 非線形弦（Kirchhoff-Carrier 方程式）

変位が大きい場合、動的張力変化が生じ非線形項が現れる：

```
∂²y/∂t² = [T₀/μ + E·A/(2μL) · ∫₀ᴸ(∂y/∂x)²dx] · ∂²y/∂x²
```

非線形効果の特徴：
- **ピッチ上昇**: 大振幅では張力増加により基音が高くなる
- **倍音成分の増加**: ピアノの打弦直後に明瞭
- **異なるモード間のエネルギー移動**: カオス的振動への遷移

```python
def nonlinear_string(f0, amplitude, duration=2.0, sample_rate=44100,
                     nonlinearity=0.01):
    """
    非線形弦振動の簡易シミュレーション。
    Duffing 型の非線形項を追加したモーダル方程式。
    """
    n = int(duration * sample_rate)
    dt = 1.0 / sample_rate
    out = np.zeros(n)

    n_modes = 10
    freq = [f0 * m for m in range(1, n_modes + 1)]
    x = np.zeros(n_modes)   # 変位
    v = np.zeros(n_modes)   # 速度
    x[0] = amplitude        # 初期変位（基音モードのみ）

    for i in range(n):
        total_energy = np.sum(x**2)
        for m in range(n_modes):
            omega = 2 * np.pi * freq[m]
            # 非線形ばね定数（大振幅で張力増加）
            omega_eff = omega * (1 + nonlinearity * total_energy)
            damping = 0.001 * omega  # モード減衰
            ax = -omega_eff**2 * x[m] - damping * v[m]
            v[m] += ax * dt
            x[m] += v[m] * dt

        out[i] = np.sum(x * np.array([1/(m+1) for m in range(n_modes)]))

    return out / (np.max(np.abs(out)) + 1e-9)
```

---

## 3. van der Pol 振動子

### 方程式

```
ẍ - μ(1 - x²)ẋ + ω₀²x = F(t)

μ: 非線形減衰係数
```

- `μ` が小さい → ほぼ正弦波
- `μ` が大きい → リラクセーション振動（ノコギリ波に近い波形）

**クラリネット・オーボエのリードの自励振動**を記述するモデルとして使われる。

```python
def van_der_pol(mu, f0, duration=2.0, sample_rate=44100, F_amp=0.0, F_freq=0.0):
    """
    van der Pol 振動子による音生成。
    mu: 非線形パラメーター（0.1 = ほぼ正弦, 5.0 = リラクセーション振動）
    """
    omega0 = 2 * np.pi * f0
    n = int(duration * sample_rate)
    dt = 1.0 / sample_rate

    def deriv(t, y):
        x, xdot = y
        forcing = F_amp * np.sin(2 * np.pi * F_freq * t) if F_freq > 0 else 0
        xddot = mu * (1 - x**2) * xdot - omega0**2 * x + forcing
        return [xdot, xddot]

    from scipy.integrate import solve_ivp
    t_eval = np.arange(n) * dt
    sol = solve_ivp(deriv, [0, duration], [0.1, 0.0],
                    t_eval=t_eval, method='RK45',
                    max_step=dt, dense_output=False)

    out = sol.y[0]
    return out / (np.max(np.abs(out)) + 1e-9)
```

### 結合 van der Pol（複数リードのモデル）

複数の van der Pol 振動子を結合させると、フルート・オルガンパイプの複雑な発音過程を模倣できる。

---

## 4. Duffing 振動子

### 方程式

```
ẍ + δẋ + αx + βx³ = γcos(ωt)

α: 線形ばね定数、β: 非線形ばね定数、δ: 減衰、γ: 強制振幅
```

| パラメーター設定 | 挙動 |
|---|---|
| α > 0, β > 0 | 超調和共鳴（ハードスプリング）|
| α > 0, β < 0 | 軟化特性（ソフトスプリング）|
| α < 0, β > 0 | ダブルウェルポテンシャル（カオス遷移）|

```python
def duffing_oscillator(alpha, beta, delta, gamma, omega_drive,
                       duration=3.0, sample_rate=44100):
    """
    Duffing 振動子による音生成。
    非線形共鳴・打楽器的クラッシュ音の生成に使用。
    """
    from scipy.integrate import solve_ivp

    n = int(duration * sample_rate)
    dt = 1.0 / sample_rate

    def deriv(t, y):
        x, xdot = y
        xddot = (-delta * xdot - alpha * x - beta * x**3
                 + gamma * np.cos(omega_drive * t))
        return [xdot, xddot]

    t_eval = np.arange(n) * dt
    sol = solve_ivp(deriv, [0, duration], [0.0, 0.0],
                    t_eval=t_eval, method='RK45',
                    max_step=dt * 5)

    # 指定点数に補間（solve_ivp の適応ステップに対応）
    from scipy.interpolate import interp1d
    f_interp = interp1d(sol.t, sol.y[0], kind='linear',
                        bounds_error=False, fill_value=0)
    out = f_interp(t_eval)
    return out / (np.max(np.abs(out)) + 1e-9)


# ダブルウェル Duffing のカオス的音生成例
# duffing_oscillator(alpha=-1.0, beta=1.0, delta=0.3, gamma=0.5, omega_drive=1.2)
```

---

## 5. カオス・ロジスティック写像

### ロジスティック写像

```
x_{n+1} = r · x_n · (1 - x_n)
```

| r の値 | 挙動 |
|---|---|
| r < 3.0 | 固定点収束（直流） |
| 3.0 < r < 3.57 | 周期倍分岐 |
| r ≈ 3.57 | カオスの始まり |
| 3.57 < r < 4.0 | カオス（窓構造あり）|
| r = 4.0 | 完全カオス |

```python
def logistic_map_audio(r, duration=2.0, sample_rate=44100, x0=0.5):
    """
    ロジスティック写像を音波として出力。
    r=3.5 → 周期4、r=3.9 → カオスノイズ
    """
    n = int(duration * sample_rate)
    out = np.zeros(n)
    x = x0
    for i in range(n):
        x = r * x * (1 - x)
        out[i] = x * 2 - 1  # [-1, 1] に正規化
    return out


def logistic_sweep(r_start=3.4, r_end=4.0, duration=5.0, sample_rate=44100):
    """
    r をスイープしてカオスへの遷移を音として体験する。
    """
    n = int(duration * sample_rate)
    r_vals = np.linspace(r_start, r_end, n)
    out = np.zeros(n)
    x = 0.5
    for i in range(n):
        x = r_vals[i] * x * (1 - x)
        out[i] = x * 2 - 1
    return out
```

### ローレンツアトラクター

```
dx/dt = σ(y - x)
dy/dt = x(ρ - z) - y
dz/dt = xy - βz

（σ=10, ρ=28, β=8/3 で「バタフライアトラクター」）
```

```python
def lorenz_audio(sigma=10, rho=28, beta=8/3,
                 duration=1.0, sample_rate=44100, axis='x'):
    """ローレンツアトラクターを音源として使用（軸を選択可能）"""
    n = int(duration * sample_rate)
    dt = 1.0 / sample_rate
    x, y, z = 0.1, 0.0, 0.0
    out = np.zeros(n)
    for i in range(n):
        dx = sigma * (y - x)
        dy = x * (rho - z) - y
        dz = x * y - beta * z
        x += dx * dt
        y += dy * dt
        z += dz * dt
        out[i] = {'x': x, 'y': y, 'z': z}[axis]
    return out / (np.max(np.abs(out)) + 1e-9)
```

---

## 6. 1/f ノイズ・フラクタルノイズ

### カラーノイズの分類

```
パワースペクトル S(f) ∝ 1/f^β

β = 0: ホワイトノイズ（フラット）
β = 1: ピンクノイズ（1/f ノイズ）
β = 2: ブラウンノイズ（レッドノイズ）
β > 2: 平滑なランダム
```

**ピンクノイズ（β=1）** は自然現象（雨音・川音・人間の音楽）に最も近い統計的分布を持つ。

```python
def colored_noise(beta, n_samples, sample_rate=44100):
    """
    1/f^beta カラーノイズ生成（スペクトル整形法）。
    """
    # ホワイトノイズの FFT
    white = np.random.randn(n_samples)
    fft_w = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n_samples, 1.0 / sample_rate)

    # 1/f^beta スペクトル整形
    freqs[0] = 1  # DC 成分を保護
    power = freqs ** (-beta / 2)
    power[0] = 0  # DC を除去

    fft_colored = fft_w * power
    out = np.fft.irfft(fft_colored, n=n_samples)
    return out / (np.std(out) + 1e-9)


def pink_noise(n_samples, sample_rate=44100):
    """Voss-McCartney アルゴリズムによるピンクノイズ（低コスト）"""
    n_octaves = 16
    keys = np.zeros(n_octaves)
    out = np.zeros(n_samples)
    running_sum = 0.0
    for i in range(n_samples):
        last_key = 0
        diff = i ^ (i - 1) if i > 0 else 0xFFFF
        # 変化したビット数に対応するホワイトソースを更新
        for j in range(n_octaves):
            if diff & (1 << j):
                running_sum -= keys[j]
                keys[j] = np.random.uniform(-1, 1)
                running_sum += keys[j]
        out[i] = running_sum / n_octaves + np.random.uniform(-1/n_octaves, 1/n_octaves)
    return out / (np.max(np.abs(out)) + 1e-9)
```

### フラクタルブラウン運動（fBm）

Hurst 指数 `H` によって相関構造を制御する一般化ブラウン運動。

```
H = 0.5: 標準ブラウン運動（ブラウンノイズ）
H > 0.5: 長距離正相関（滑らかな変動）
H < 0.5: 長距離負相関（ラフな変動）
```

```python
def fbm_audio(H=0.7, duration=2.0, sample_rate=44100):
    """
    フラクタルブラウン運動を音源に使用。
    beta = 2H + 1 の関係でカラーノイズと等価。
    """
    from fbm import FBM  # pip install fbm
    n = int(duration * sample_rate)
    f = FBM(n=n, hurst=H, length=duration, method='daviesharte')
    fgn = f.fgn()  # fBm の増分（フラクタルガウスノイズ）
    return fgn / (np.std(fgn) + 1e-9)
```

---

## 7. ブラウン運動・ランジュバン方程式

### ランジュバン方程式

粒子の熱振動を記述する確率微分方程式：

```
m·ẍ = -γẋ + F_ext + ξ(t)

ξ(t): 白色ガウスノイズ（<ξ(t)ξ(t')> = 2kTγ·δ(t-t')）
```

音への応用：微小粒子（空気分子・粉体）の集団振動をソニフィケーション。

```python
def langevin_audio(m=1e-15, gamma=1e-10, kT=4e-21,
                   duration=1.0, sample_rate=44100):
    """
    ランジュバン方程式による熱ノイズ音生成。
    パラメーターは分子スケールのデフォルト値。
    """
    n = int(duration * sample_rate)
    dt = 1.0 / sample_rate
    x = 0.0
    v = 0.0
    out = np.zeros(n)
    noise_amp = np.sqrt(2 * kT * gamma / dt)

    for i in range(n):
        xi = np.random.randn() * noise_amp
        a = (-gamma * v + xi) / m
        v += a * dt
        x += v * dt
        out[i] = x

    # 可聴域にスケーリング
    out -= np.mean(out)
    return out / (np.max(np.abs(out)) + 1e-9)
```

---

## 8. 確率共鳴（Stochastic Resonance）

### 原理

**非線形システムにおいて、適切な強さのノイズを加えることで弱い信号への応答が最大化される現象。**

```
2 状態システムの例:
    V(x) = -x²/2 + x⁴/4 - A·cos(2π·f·t)·x + ξ(t)
```

閾値型ニューロン・感覚器でよく観察される。

```python
def stochastic_resonance(signal_freq, signal_amp, noise_level,
                         duration=2.0, sample_rate=44100):
    """
    閾値型ニューロンモデルでの確率共鳴。
    信号が閾値以下でもノイズの助けで検出可能になる。
    """
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate

    signal = signal_amp * np.sin(2 * np.pi * signal_freq * t)
    noise = noise_level * np.random.randn(n)
    total = signal + noise

    # 閾値型フィルター（バイナリニューロン発火）
    threshold = 0.5
    output = np.where(total > threshold, 1.0, -1.0)

    # 発火パターンをバンドパスで整形
    from scipy import signal as sp_signal
    b, a = sp_signal.butter(2, [signal_freq * 0.5 / (sample_rate / 2),
                                 signal_freq * 3.0 / (sample_rate / 2)],
                            btype='band')
    out = sp_signal.lfilter(b, a, output.astype(float))
    return out / (np.max(np.abs(out)) + 1e-9)
```

---

## 参考文献・リソース

| 資料 | 内容 |
|---|---|
| Kirchhoff (1850) "Über das Gleichgewicht und die Bewegung einer elastischen Scheibe" | 薄板理論の基礎 |
| Valette & Cuesta (1993) "Mécanique de la corde vibrante" | 非線形弦振動 |
| Van der Pol (1926) "On Relaxation-Oscillations" | van der Pol 振動子の原著 |
| May (1976) "Simple mathematical models with very complicated dynamics" | ロジスティック写像の古典的論文 |
| Bak et al. (1987) "Self-organized criticality" | 1/f ノイズの自己組織化臨界理論 |
| Mandelbrot (1982) "The Fractal Geometry of Nature" | フラクタル・fBm の基礎 |
| Gammaitoni et al. (1998) "Stochastic resonance" | 確率共鳴のレビュー論文 |

---

[← 概要に戻る](sound-from-physics-overview.md)
