# 数学的手法・変換理論による音生成

---

## 1. フラクショナルフーリエ変換（FrFT）

### 概要

通常のフーリエ変換を「時間-周波数平面の 90°回転」と見なし、それを**任意の角度 α = aπ/2 の回転**に一般化した変換。

```
(F^a f)(u) = ∫ K_a(u, t) f(t) dt

K_a(u, t) = √(1 - i·cot α) / √(2π) · exp(i(u² + t²)/2 · cot α - i·u·t/sin α)

α = π/2 のとき: 通常のフーリエ変換
α = π   のとき: 時間反転
α = 0   のとき: 恒等変換
```

### 音響応用

| 応用 | 効果 |
|---|---|
| チャープ信号の分析 | 線形チャープが特定の a 角でデルタ関数になる |
| 時間-周波数融合音色 | a を 0→1 の間でモーフィングすると時間領域と周波数領域の中間表現 |
| ピッチシフト + タイムストレッチ同時操作 | 分数次変換空間での操作 |
| 反響・残響の設計 | FrFT ドメインでのフィルタリング |

```python
import numpy as np
from scipy.linalg import dft

def frft_discrete(x, a):
    """
    離散フラクショナルフーリエ変換（DFrFT）。
    Ozaktas らの数値実装に基づく。
    a: 変換次数（a=1 で通常の DFT に対応）
    """
    N = len(x)
    alpha = a * np.pi / 2

    if abs(alpha % np.pi) < 1e-10:
        # α が π の倍数の場合
        return np.roll(x[::-1] if round(a) % 2 else x, 0)

    # サンプリング間隔の正規化
    delta_t = 1.0 / N
    delta_u = 1.0 / N

    t = np.arange(-N//2, N//2) * delta_t
    u = np.arange(-N//2, N//2) * delta_u

    # チャープ乗算
    cot_a = np.cos(alpha) / np.sin(alpha)
    csc_a = 1.0 / np.sin(alpha)

    chirp_t = np.exp(1j * np.pi * cot_a * t**2)
    chirp_u = np.exp(1j * np.pi * cot_a * u**2)

    # 入力にチャープを乗算
    x_shifted = np.fft.ifftshift(x)
    x_chirped = np.fft.ifftshift(chirp_t) * x_shifted

    # FFT
    X = np.fft.fft(x_chirped)

    # 周波数チャープと正規化
    freqs = np.fft.fftfreq(N)
    H_chirp = np.exp(-1j * np.pi * freqs**2 / np.tan(alpha) * N)
    X_filtered = X * H_chirp

    # 逆 FFT + チャープ除去
    result = np.fft.ifft(X_filtered)
    result = result * chirp_u

    # 位相因子
    phase_factor = np.exp(-1j * (np.pi/4) * np.sign(np.sin(alpha)) + 1j * alpha / 2)
    result *= phase_factor / np.sqrt(abs(np.sin(alpha)) * N)

    return np.fft.fftshift(result)


def frft_synthesis(signal, a_start=0.0, a_end=1.0,
                   n_frames=50, sample_rate=44100):
    """
    FrFT 次数をモーフィングしながら再合成。
    a_start → a_end の間を補間して変換し、
    実部を時間信号として出力する（チャープモーフィング効果）。
    """
    n = len(signal)
    frame_size = n // n_frames
    output = np.zeros(n)
    a_vals = np.linspace(a_start, a_end, n_frames)

    for i, a in enumerate(a_vals):
        start = i * frame_size
        end = min(start + frame_size, n)
        frame = signal[start:end]

        # ゼロパディングしてべき乗の長さに
        N = 2 ** int(np.ceil(np.log2(len(frame))))
        frame_padded = np.pad(frame, (0, N - len(frame)))

        transformed = frft_discrete(frame_padded, a)
        output[start:end] = np.real(transformed[:end-start])

    return output / (np.max(np.abs(output)) + 1e-9)
```

### チャープ音生成への応用

```python
def chirp_via_frft(f_center, bandwidth, duration=1.0, sample_rate=44100, a=0.5):
    """
    FrFT ドメインのガウシアン包絡線を時間領域に変換してチャープを生成。
    a=0.5 で 45° 回転 → 時間-周波数平面上の斜め方向のガウシアン
    """
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate

    # 時間-周波数平面上のガウシアン（FrFT ドメイン）
    u = np.linspace(-1, 1, n)
    gaussian = np.exp(-u**2 / (2 * bandwidth**2))

    # FrFT の逆変換で時間信号を生成
    chirp_signal = np.real(frft_discrete(gaussian, -a))

    # 中心周波数にシフト
    carrier = np.exp(2j * np.pi * f_center * t)
    modulated = chirp_signal * np.real(carrier)

    return modulated / (np.max(np.abs(modulated)) + 1e-9)
```

---

## 2. ウェーブレット理論と音合成

### 離散ウェーブレット変換（DWT）

```
DWT の多重解像度解析:
  信号 → [近似係数 cA] + [詳細係数 cD₁, cD₂, ..., cDₙ]
  
  各レベルでフィルタリング + 2倍ダウンサンプリング
  
  cA → 低周波（低音域の成分）
  cD₁ → 最高周波数帯（16kHz帯）
  cD₂ → 次の帯域（8kHz帯）
  cDₙ → 低周波帯
```

### ウェーブレット合成

```python
import pywt

def wavelet_synthesis(n_samples=44100, wavelet='db4', levels=10, seed=42):
    """
    ウェーブレット係数から逆変換で音を生成。
    係数の設定方法によって様々な音色を生成できる。
    """
    rng = np.random.default_rng(seed)

    # ウェーブレット係数の生成（各レベルで周波数帯のエネルギーを制御）
    # レベルごとのエネルギープロファイル（ピンクノイズ的）
    coeffs = []
    current_len = n_samples

    for i in range(levels):
        current_len = current_len // 2
        # 高域ほどエネルギーを減らす（1/f スペクトルに近似）
        energy = 1.0 / (2 ** (i * 0.5))
        detail = rng.normal(0, energy, current_len)
        coeffs.insert(0, detail)

    # 近似係数（最低周波数帯）
    approx = rng.normal(0, 0.1, current_len)
    coeffs.insert(0, approx)

    # 逆ウェーブレット変換
    reconstructed = pywt.waverec(coeffs, wavelet)
    reconstructed = reconstructed[:n_samples]

    return reconstructed / (np.max(np.abs(reconstructed)) + 1e-9)


def wavelet_spectral_sculpting(audio, level_gains, wavelet='db4'):
    """
    ウェーブレット分解 → 各周波数帯のゲイン調整 → 再合成。
    物理的なイコライザーとは異なる「マルチスケール成形」効果。

    level_gains: 各レベルのゲイン（長さ = 分解レベル数 + 1）
    """
    n = len(audio)
    n_levels = len(level_gains) - 1

    # ウェーブレット分解
    coeffs = pywt.wavedec(audio, wavelet, level=n_levels)

    # ゲイン調整
    coeffs_modified = []
    for i, (coef, gain) in enumerate(zip(coeffs, level_gains)):
        coeffs_modified.append(coef * gain)

    # 再合成
    reconstructed = pywt.waverec(coeffs_modified, wavelet)
    return reconstructed[:n]


def continuous_wavelet_synthesis(scales, sample_rate=44100, duration=2.0,
                                 wavelet='cmor1.5-1.0'):
    """
    連続ウェーブレット変換（CWT）の逆変換による音合成。
    時間-スケール表現から直接音を生成する。
    """
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate

    out = np.zeros(n, dtype=complex)
    for scale in scales:
        # Morlet ウェーブレットを合成基底として使用
        freq = sample_rate / (scale * 4)
        sigma = scale
        wavelet_fn = np.exp(-t**2 / (2 * sigma**2)) * \
                     np.exp(2j * np.pi * freq * t)
        out += wavelet_fn

    return np.real(out) / (np.max(np.abs(np.real(out))) + 1e-9)
```

### ウェーブレットパケット合成

より細かい周波数分割（対数スケールに限らない均等分割も可能）：

```python
def wavelet_packet_synthesis(profile_func, n_samples=44100, wavelet='db4',
                              max_level=8):
    """
    ウェーブレットパケット木の末端ノードに係数を配置して再合成。
    profile_func(node_path) → amplitude: 各周波数ノードの振幅を指定する関数。

    例: profile_func = lambda path: 1.0 if sum(path) == 3 else 0.1
        → 特定の時間-周波数タイルのみ活性化
    """
    from pywt import WaveletPacket

    # ゼロ信号でツリーを構築
    dummy = np.zeros(n_samples)
    wp = WaveletPacket(data=dummy, wavelet=wavelet, maxlevel=max_level)

    # 末端ノードに係数を設定
    leaf_nodes = [node.path for node in wp.get_level(max_level, 'natural')]

    for path in leaf_nodes:
        node = wp[path]
        amp = profile_func(path)
        # 係数にランダムノイズを設定（振幅制御）
        node.data = np.random.randn(len(node.data)) * amp

    # 再合成
    reconstructed = wp.reconstruct(update=True)
    return reconstructed[:n_samples] / (np.max(np.abs(reconstructed[:n_samples])) + 1e-9)
```

---

## 3. スパース表現・圧縮センシング

### 過完備辞書による音表現

音信号 `y` を辞書 `D` の列ベクトルのスパース線形結合で表現する：

```
y = D · α,   α はスパース（ほとんどの成分 = 0）

D: [n × K] 辞書行列（K >> n: 過完備）
α: [K × 1] スパース係数ベクトル
```

### マッチング追跡法（OMP: Orthogonal Matching Pursuit）

```python
def omp(y, D, n_nonzero):
    """
    直交マッチング追跡（Orthogonal Matching Pursuit）。
    辞書 D からの最良スパース近似 α を求める。

    y: [n] 入力信号
    D: [n × K] 辞書（各列は L2 正規化済み）
    n_nonzero: スパース係数の非ゼロ数
    """
    n, K = D.shape
    residual = y.copy()
    support = []
    alpha = np.zeros(K)

    for _ in range(n_nonzero):
        # 最も相関の高い辞書原子を選択
        correlations = np.abs(D.T @ residual)
        k = np.argmax(correlations)
        support.append(k)

        # 選択済み原子への直交投影で係数を更新
        D_S = D[:, support]
        alpha_S, _, _, _ = np.linalg.lstsq(D_S, y, rcond=None)

        # 残差を更新
        residual = y - D_S @ alpha_S

    alpha[support] = alpha_S
    return alpha


def build_audio_dictionary(sample_rate=44100, atom_duration_ms=23,
                            n_atoms=512, f_min=100, f_max=8000):
    """
    音声用の過完備辞書を構築。
    ガボール原子（変調ガウシアン）を中心周波数・時間シフトの格子点に配置。
    """
    n = int(atom_duration_ms * sample_rate / 1000)
    t = np.arange(n) / sample_rate
    freqs = np.logspace(np.log10(f_min), np.log10(f_max), n_atoms // 2)
    phases = [0, np.pi / 2]  # cos と sin

    atoms = []
    for freq in freqs:
        for phase in phases:
            sigma = atom_duration_ms / 1000 / 4
            gaussian = np.exp(-t**2 / (2 * sigma**2))
            atom = gaussian * np.cos(2 * np.pi * freq * t + phase)
            atom /= np.linalg.norm(atom)
            atoms.append(atom)

    D = np.column_stack(atoms)  # [n × n_atoms]
    return D


def sparse_audio_synthesis(coefficients, dictionary, total_duration=2.0,
                            hop_size=256, sample_rate=44100):
    """
    スパース係数と辞書から音を合成する。
    OLA（オーバーラップアッド）で各フレームを結合。
    """
    n_out = int(total_duration * sample_rate)
    atom_length = dictionary.shape[0]
    output = np.zeros(n_out)
    window = np.hanning(atom_length)

    for frame_idx, alpha in enumerate(coefficients):
        pos = frame_idx * hop_size
        if pos + atom_length > n_out:
            break
        recon = dictionary @ alpha * window
        output[pos:pos + atom_length] += recon

    return output / (np.max(np.abs(output)) + 1e-9)
```

### K-SVD：辞書学習

```python
def ksvd_step(Y, D, alpha, n_iter=1):
    """
    K-SVD アルゴリズムの 1 ステップ（辞書更新フェーズ）。
    Y: [n × N] データ行列（N 個の信号）
    D: [n × K] 辞書（更新対象）
    alpha: [K × N] スパース係数行列
    """
    n, K = D.shape

    for k in range(K):
        # k 番目の原子を使用しているサンプルを特定
        used = np.where(np.abs(alpha[k, :]) > 1e-10)[0]
        if len(used) == 0:
            continue

        # k 番目の原子を除いた残差
        alpha_k = alpha.copy()
        alpha_k[k, :] = 0
        E_k = Y[:, used] - D @ alpha_k[:, used]

        # SVD で最良の原子と係数を求める
        U, s, Vt = np.linalg.svd(E_k, full_matrices=False)
        D[:, k] = U[:, 0]
        alpha[k, used] = s[0] * Vt[0, :]

    return D, alpha
```

---

## 4. トポロジカルデータ解析（TDA）

### 持続ホモロジー（Persistent Homology）

データの位相的特徴（連結成分・穴・空洞）をスケールに依存せず捉える手法。

```
フィルトレーション（半径 r を増加させながら単体複体を構築）:
  r₀ < r₁ < r₂ < ... < rₙ

各スケールで誕生・消滅するトポロジー特徴:
  (birth, death) ペアを記録 → パーシステンスダイアグラム
  
death - birth が大きい特徴 = 頑健なトポロジー構造
```

### 音響信号への応用

```python
def audio_tda_features(audio, embed_dim=3, tau_samples=100, max_edge=0.5):
    """
    音響信号の位相的特徴量抽出。
    遅延埋め込みで時系列を多次元点群に変換し、持続ホモロジーを計算する。

    embed_dim: 埋め込み次元
    tau_samples: 時間遅延（サンプル数）
    """
    try:
        import gudhi

        # 遅延埋め込み（Takens の埋め込み定理）
        n = len(audio) - (embed_dim - 1) * tau_samples
        if n <= 0:
            return None

        point_cloud = np.zeros((n, embed_dim))
        for i in range(embed_dim):
            point_cloud[:, i] = audio[i * tau_samples:i * tau_samples + n]

        # サブサンプリング（計算コスト削減）
        max_points = 500
        if len(point_cloud) > max_points:
            idx = np.random.choice(len(point_cloud), max_points, replace=False)
            point_cloud = point_cloud[idx]

        # Rips 複体の構築
        rips = gudhi.RipsComplex(points=point_cloud, max_edge_length=max_edge)
        simplex_tree = rips.create_simplex_tree(max_dimension=2)

        # 持続ホモロジーの計算
        simplex_tree.compute_persistence()

        # 各次元のパーシステンスダイアグラムを取得
        diagrams = {}
        for dim in range(3):
            pairs = simplex_tree.persistence_intervals_in_dimension(dim)
            if len(pairs) > 0:
                # 無限大を除去
                finite_pairs = [(b, d) for b, d in pairs if d != float('inf')]
                diagrams[dim] = finite_pairs

        return diagrams

    except ImportError:
        print("gudhi が必要です: pip install gudhi")
        return None


def tda_sonification(audio, sample_rate=44100, embed_dim=3, tau=100):
    """
    音響信号の位相的特徴量（バーコード）を別の音に変換する。
    パーシステンスペアの「誕生・消滅」時刻を音のイベントとして使用。
    """
    diagrams = audio_tda_features(audio, embed_dim=embed_dim, tau_samples=tau)
    if diagrams is None:
        return np.zeros(len(audio))

    n = len(audio)
    output = np.zeros(n)

    # H₁（1次元穴: ループ）のバーコードを音符に変換
    if 1 in diagrams:
        for birth, death in diagrams[1]:
            persistence = death - birth
            if persistence < 0.01:
                continue

            # 持続時間を周波数にマッピング（440 Hz を中心に）
            freq = 440.0 * (1.0 + persistence * 5.0)
            duration_samples = min(int(persistence * sample_rate * 0.5), n // 10)
            start = min(int(birth * n), n - duration_samples)

            if start + duration_samples <= n:
                t = np.arange(duration_samples) / sample_rate
                env = np.hanning(duration_samples)
                output[start:start + duration_samples] += \
                    env * np.sin(2 * np.pi * freq * t) * persistence

    return output / (np.max(np.abs(output)) + 1e-9) if np.max(np.abs(output)) > 0 else output
```

### パーシステンスランドスケープ

```python
def persistence_landscape(diagram, n_layers=3, resolution=100):
    """
    パーシステンスダイアグラムをランドスケープ関数に変換。
    数値演算（平均・分散）が可能な安定的な特徴量表現。
    """
    if not diagram:
        return np.zeros((n_layers, resolution))

    births = np.array([b for b, d in diagram])
    deaths = np.array([d for b, d in diagram])
    t_min = births.min()
    t_max = deaths.max()

    t = np.linspace(t_min, t_max, resolution)
    landscape = np.zeros((n_layers, resolution))

    for ti, tv in enumerate(t):
        values = []
        for b, d in diagram:
            if b <= tv <= d:
                values.append(min(tv - b, d - tv))
            else:
                values.append(0.0)
        values.sort(reverse=True)
        for layer in range(min(n_layers, len(values))):
            landscape[layer, ti] = values[layer]

    return landscape
```

---

## 5. 非可換調和解析と群論

### 抽象的フーリエ解析

通常の DFT は **Z/NZ（循環群）** 上の調和解析。これを任意の群に拡張できる。

```
コンパクト群 G 上のフーリエ変換:
  f̂(ρ) = ∫_G f(g) · ρ(g)* dg

ρ: 既約ユニタリ表現
```

### 球面調和関数による音場表現

3 次元音場のアンビソニックス表現に球面調和関数を使用：

```python
def spherical_harmonics_ambisonics(audio_channels, order=3, sample_rate=44100):
    """
    アンビソニックス（球面調和関数）による音場表現。
    order: 空間分解能（3次 = 16チャンネル）

    音源方向 (theta, phi) から 3D 音場を符号化・復号する。
    """
    from scipy.special import sph_harm

    # 球面調和関数の次数 l, m の組み合わせ
    sh_components = []
    for l in range(order + 1):
        for m in range(-l, l + 1):
            sh_components.append((l, m))

    n_components = len(sh_components)  # (order+1)²

    def encode(signal, theta, phi):
        """音源信号を方向(theta, phi)でアンビソニックスに符号化"""
        ambi = np.zeros((n_components, len(signal)))
        for i, (l, m) in enumerate(sh_components):
            Y_lm = np.real(sph_harm(abs(m), l, phi, theta))
            if m < 0:
                Y_lm = np.imag(sph_harm(-m, l, phi, theta)) * np.sqrt(2)
            elif m > 0:
                Y_lm = np.real(sph_harm(m, l, phi, theta)) * np.sqrt(2)
            ambi[i] = signal * Y_lm
        return ambi

    def decode(ambi, theta, phi):
        """アンビソニックスから方向(theta, phi)の信号を復元"""
        output = np.zeros(ambi.shape[1])
        for i, (l, m) in enumerate(sh_components):
            Y_lm = np.real(sph_harm(abs(m), l, phi, theta))
            if m < 0:
                Y_lm = np.imag(sph_harm(-m, l, phi, theta)) * np.sqrt(2)
            elif m > 0:
                Y_lm = np.real(sph_harm(m, l, phi, theta)) * np.sqrt(2)
            output += ambi[i] * Y_lm
        return output

    return encode, decode
```

---

## 6. 情報幾何学・確率多様体

### 音色空間の測地線補間

音色パラメーター空間を**リーマン多様体**として扱い、2 つの音色を測地線（最短経路）で補間する。

```python
def information_geometric_morph(params_A, params_B, n_steps=50):
    """
    フィッシャー情報計量に基づく音色パラメーターのモーフィング。
    スペクトル包絡をガウス混合モデルとして表現し、
    Wasserstein 測地線（最適輸送）で補間する。

    params_A, params_B: GMM パラメーター (means, variances, weights)
    """
    means_A, vars_A, weights_A = params_A
    means_B, vars_B, weights_B = params_B

    interpolated = []
    for t in np.linspace(0, 1, n_steps):
        # Wasserstein-2 測地線（1次元ガウス混合の場合の近似）
        means_t   = (1 - t) * means_A   + t * means_B
        stds_t    = ((1-t) * np.sqrt(vars_A) + t * np.sqrt(vars_B)) ** 2
        weights_t = (1 - t) * weights_A + t * weights_B
        weights_t /= weights_t.sum()
        interpolated.append((means_t, stds_t, weights_t))

    return interpolated


def gmm_to_spectrum(means, stds, weights, n_freqs=1024, f_max=22050):
    """
    GMM パラメーターをスペクトル包絡に変換してアディティブ合成に使用。
    """
    freqs = np.linspace(0, f_max, n_freqs)
    spectrum = np.zeros(n_freqs)
    for mu, sigma, w in zip(means, stds, weights):
        spectrum += w * np.exp(-0.5 * ((freqs - mu) / max(sigma, 1.0))**2)
    return spectrum
```

---

## 参考文献・リソース

| 資料 | 内容 |
|---|---|
| Ozaktas et al. (2001) "The Fractional Fourier Transform" | FrFT の包括的教科書 |
| Mallat (2009) "A Wavelet Tour of Signal Processing" | ウェーブレット理論の標準教科書 |
| Aharon et al. (2006) "K-SVD: An Algorithm for Designing..." | K-SVD 辞書学習 |
| Edelsbrunner & Harer (2010) "Computational Topology" | TDA の教科書 |
| Carlsson (2009) "Topology and Data" | TDA の概観 |
| Amari & Nagaoka (2000) "Methods of Information Geometry" | 情報幾何学 |
| Villani (2009) "Optimal Transport" | 最適輸送理論 |
| GUDHI ライブラリ公式ドキュメント | TDA の実装リファレンス |
| PyWavelets 公式ドキュメント | ウェーブレット変換の実装 |

---

[← 概要に戻る](sound-from-physics-overview.md)
