# 他分野の科学知見による音生成

---

## 1. 電磁気・回路理論アナロジー（WDF）

### 波動デジタルフィルター（Wave Digital Filter）

アナログ回路の**波動変数（入射波・反射波）**表現によるデジタル実装。  
クルト・フェッテルライン（Alfred Fettweis, 1972）が開発。

#### アナロジーの対応関係

| 電気系 | 機械系 | 音響系 |
|---|---|---|
| 電圧 V | 力 F | 音圧 p |
| 電流 I | 速度 v | 体積速度 U |
| 抵抗 R | 機械抵抗 Rm | 音響抵抗 Ra |
| コンデンサ C | コンプライアンス Cm | 音響コンプライアンス Ca |
| インダクタ L | 質量 M | 音響質量 Ma |

#### 1ポート WDF 素子

```python
import numpy as np

class WDF_Resistor:
    def __init__(self, R):
        self.R = R
    def reflected_wave(self, incident):
        return 0.0  # 反射なし
    def voltage(self, incident):
        return incident / 2
    def current(self, incident):
        return incident / (2 * self.R)


class WDF_Capacitor:
    def __init__(self, C, sample_rate=44100):
        self.C = C
        self.T = 1.0 / sample_rate
        self.R_eq = self.T / (2 * C)  # 離散化（双線形変換）
        self.state = 0.0

    def reflected_wave(self, incident):
        reflected = self.state
        self.state = incident
        return reflected


class WDF_Series:
    """直列接続（2ポート）"""
    def __init__(self, port_a, port_b):
        self.a = port_a
        self.b = port_b

    def scatter(self, a_in, b_in):
        sum_ab = a_in + b_in
        Ra = getattr(self.a, 'R_eq', 1.0)
        Rb = getattr(self.b, 'R_eq', 1.0)
        gamma = 2 * Ra / (Ra + Rb)
        a_out = a_in - gamma * sum_ab
        b_out = b_in - (2 - gamma) * sum_ab
        return a_out, b_out


def rc_lowpass_wdf(fc, input_signal, sample_rate=44100):
    """
    WDF による RC ローパスフィルター（1次）。
    fc: カットオフ周波数 [Hz]
    """
    R = 1.0
    C = 1.0 / (2 * np.pi * fc * R)
    T = 1.0 / sample_rate

    # 双線形変換
    R_C = T / (2 * C)

    output = np.zeros(len(input_signal))
    state = 0.0  # コンデンサの状態

    for i, x in enumerate(input_signal):
        # 入射波
        a_R = x  # ソース抵抗からの入射（簡略化）
        a_C = state

        # 散乱
        port_sum = a_R + a_C
        b_R = a_R - (2 * R / (R + R_C)) * port_sum
        b_C = a_C - (2 * R_C / (R + R_C)) * port_sum

        # コンデンサの更新
        state = b_C

        # 出力電圧（コンデンサ端子）
        output[i] = (a_C + b_C) / 2

    return output
```

#### 非線形 WDF（ダイオードクリッピング）

```python
def diode_clipper_wdf(input_signal, sample_rate=44100, Is=1e-15, Vt=0.026):
    """
    WDF によるダイオードクリッパー（非線形）。
    ギター・チューブアンプの歪みエミュレーションの基礎。
    """
    output = np.zeros(len(input_signal))
    R_s = 1000.0  # ソース抵抗 [Ω]

    for i, x in enumerate(input_signal):
        a = x  # 入射波（簡略化）

        # ニュートン法でダイオード方程式を解く
        b = 0.0
        for _ in range(10):
            V = (a - b) / 2
            I = Is * (np.exp(V / Vt) - 1)
            f = b + 2 * R_s * I - a
            df = 1 + 2 * R_s * Is / Vt * np.exp(V / Vt)
            b -= f / df

        output[i] = (a + b) / 2

    return output
```

---

## 2. 量子力学・量子コンピューティング

### 量子調和振動子

量子調和振動子のエネルギー固有値：

```
Eₙ = ℏω(n + 1/2)   (n = 0, 1, 2, ...)
```

**離散的なエネルギー準位** → 正確な倍音構造（アディティブ合成の量子力学的類似）

```python
def quantum_harmonic_oscillator_sound(omega0, n_levels=8,
                                      duration=2.0, sample_rate=44100):
    """
    量子調和振動子のエネルギー準位を倍音構造として使用。
    古典的なアディティブ合成に量子的重み付けを適用。
    """
    hbar = 1.0545718e-34  # ℏ [J·s]

    # エネルギー準位と対応する周波数
    levels = np.arange(n_levels)
    energies = hbar * omega0 * (levels + 0.5)

    # ボルツマン分布による重み（温度パラメーターで制御）
    kT = hbar * omega0 * 3  # 熱エネルギー（音色の明るさを制御）
    weights = np.exp(-energies / kT)
    weights /= weights.sum()

    # 各レベルの遷移周波数を倍音として使用
    n_samples = int(duration * sample_rate)
    t = np.arange(n_samples) / sample_rate
    out = np.zeros(n_samples)

    for n, w in zip(levels[1:], weights[1:]):
        freq = omega0 / (2 * np.pi) * n
        out += w * np.sin(2 * np.pi * freq * t)

    return out / (np.max(np.abs(out)) + 1e-9)
```

### 量子フーリエ変換（QFT）による音生成

```python
def qft_audio_synthesis(n_qubits=8, duration=1.0, sample_rate=44100):
    """
    量子フーリエ変換の出力確率分布をスペクトルとして使用。
    Qiskit が必要: pip install qiskit qiskit-aer
    """
    try:
        from qiskit import QuantumCircuit
        from qiskit_aer import AerSimulator

        n = n_qubits
        qc = QuantumCircuit(n)

        # ランダムな初期状態（音楽的な初期化）
        for i in range(n):
            qc.h(i)  # アダマールゲートで重ね合わせ

        # 量子フーリエ変換
        def qft(circuit, n):
            for i in range(n-1, -1, -1):
                circuit.h(i)
                for j in range(i-1, -1, -1):
                    circuit.cp(np.pi / 2**(i-j), j, i)
            # ビット反転スワップ
            for i in range(n // 2):
                circuit.swap(i, n - i - 1)

        qft(qc, n)
        qc.measure_all()

        # シミュレーション
        sim = AerSimulator()
        job = sim.run(qc, shots=1024)
        counts = job.result().get_counts()

        # 測定結果を倍音振幅として使用
        n_harmonics = 2**n
        amplitudes = np.zeros(n_harmonics)
        for state, count in counts.items():
            idx = int(state, 2)
            amplitudes[idx] = count / 1024.0

        # アディティブ合成
        n_samples = int(duration * sample_rate)
        t = np.arange(n_samples) / sample_rate
        f0 = 440.0
        out = np.zeros(n_samples)
        for h, amp in enumerate(amplitudes[:64], start=1):
            if amp > 0:
                out += amp * np.sin(2 * np.pi * f0 * h * t)

        return out / (np.max(np.abs(out)) + 1e-9)

    except ImportError:
        print("Qiskit が必要です: pip install qiskit qiskit-aer")
        return np.zeros(int(duration * sample_rate))
```

---

## 3. 地震学・地球物理学のソニフィケーション

### 地震波形の直接可聴化

```python
def seismic_sonification(waveform, original_sample_rate=100,
                         target_sample_rate=44100, speed_up=500):
    """
    地震波形を可聴域にアップサンプリングして音化する。
    元の地震波（0.01〜10 Hz）を人間の可聴域（20〜20000 Hz）にマッピング。

    speed_up: 時間加速率（500倍で1 Hz → 500 Hz）
    """
    from scipy.signal import resample_poly
    from math import gcd

    # 周波数マッピング: f_audio = f_seismic × speed_up
    # サンプルレート比
    new_sr = int(original_sample_rate * speed_up)
    g = gcd(new_sr, target_sample_rate)
    up = target_sample_rate // g
    down = new_sr // g

    # リサンプリング
    resampled = resample_poly(waveform, up, down)
    return resampled / (np.max(np.abs(resampled)) + 1e-9)


def download_seismic_data(network='IU', station='ANMO', channel='BHZ',
                          start='2024-01-01', duration_hours=1):
    """
    IRIS データセンターから地震波形を取得。
    ObsPy が必要: pip install obspy
    """
    try:
        from obspy import UTCDateTime
        from obspy.clients.fdsn import Client

        client = Client("IRIS")
        t = UTCDateTime(start)
        st = client.get_waveforms(network, station, '*', channel,
                                  t, t + duration_hours * 3600)
        tr = st[0]
        return tr.data, tr.stats.sampling_rate
    except ImportError:
        print("ObsPy が必要です: pip install obspy")
        return np.zeros(1000), 100.0
```

### P 波・S 波の音響的違い

| 波型 | 速度 | 媒質 | 周波数域 | 音的性格 |
|---|---|---|---|---|
| P 波（縦波） | 6-8 km/s | 固体・液体 | 1-10 Hz | 低音のゴロゴロ |
| S 波（横波） | 3-5 km/s | 固体のみ | 0.1-5 Hz | 横揺れのうねり |
| 表面波（Love/Rayleigh） | 2-4 km/s | 表面 | 0.01-1 Hz | 長周期のうねり |

### 理論的地震波形生成

```python
def synthetic_seismogram(M0, depth_km, distance_km, duration=60.0,
                         sample_rate=100.0):
    """
    理論地震波形の簡易生成（点震源モデル）。
    M0: モーメント規模、depth_km: 震源深さ、distance_km: 震央距離
    """
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate

    # P波到達時刻（簡易計算）
    vp = 6.5  # km/s
    vs = 3.7  # km/s
    dist = np.sqrt(distance_km**2 + depth_km**2)
    t_P = dist / vp
    t_S = dist / vs

    # 地震モーメントから変位振幅を推定（簡易）
    amplitude = M0 / (4 * np.pi * 2800 * vp**3 * dist * 1000)

    # P 波（縦波：高周波成分が多い）
    fc = 1.0  # コーナー周波数 [Hz]
    out = np.zeros(n)
    mask_P = t > t_P
    t_P_rel = np.maximum(t - t_P, 0)
    out += amplitude * t_P_rel * np.exp(-t_P_rel * fc) * \
           np.sin(2 * np.pi * fc * t_P_rel) * mask_P

    # S 波（横波：低周波成分が多い）
    mask_S = t > t_S
    t_S_rel = np.maximum(t - t_S, 0)
    out += amplitude * 0.6 * t_S_rel * np.exp(-t_S_rel * fc * 0.5) * \
           np.sin(2 * np.pi * fc * 0.5 * t_S_rel) * mask_S

    return out / (np.max(np.abs(out)) + 1e-9)
```

---

## 4. 天文学（重力波・日震学・惑星音）

### 重力波の可聴化（LIGO チャープ）

連星合体（BNS / BBH）が放射する重力波は 20-150 Hz のチャープ音として可聴化できる。

```python
def gravitational_wave_chirp(M1=30, M2=30, duration=2.0,
                              sample_rate=44100, f_start=20.0):
    """
    連星ブラックホール合体の重力波チャープ音生成。
    PyCBC または GWpy なしの解析的近似実装。

    M1, M2: 各天体の質量（太陽質量単位）
    """
    G = 6.674e-11   # 重力定数
    c = 3e8         # 光速
    M_sun = 1.989e30

    M_chirp = (M1 * M2)**0.6 / (M1 + M2)**0.2 * M_sun

    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate

    # 合体までの時間（終端：f → ∞）を推定
    # 後退時間 t_c からの逆算で位相を計算
    t_c = duration  # 合体時刻を終端に設定
    tau = t_c - t
    tau = np.maximum(tau, 1e-6)

    # 周波数の時間発展（ポスト-ニュートン近似）
    f_gw = (1 / (8 * np.pi)) * (5 / 256) ** (3/8) * \
           (G * M_chirp / c**3) ** (-5/8) * tau ** (-3/8)

    # 最大周波数を制限（ISCO 周波数相当）
    f_ISCO = c**3 / (6**(3/2) * np.pi * G * (M1 + M2) * M_sun)
    f_ISCO_Hz = f_ISCO  # 実際は数十〜数百 Hz
    f_gw = np.minimum(f_gw, 2000.0)  # 可聴域に制限

    # 位相の積分
    phase = 2 * np.pi * np.cumsum(f_gw) / sample_rate
    chirp = np.sin(phase)

    # 振幅エンベロープ（合体直前で増大）
    amplitude = (tau + 1e-6) ** (-1/4)
    amplitude /= amplitude.max()
    chirp *= amplitude

    return chirp


def ligo_data_sonification(event='GW150914'):
    """
    LIGO オープンデータから重力波イベントを取得して可聴化。
    GWpy が必要: pip install gwpy
    """
    try:
        from gwpy.timeseries import TimeSeries
        data = TimeSeries.fetch_open_data('H1',
                                          *TimeSeries.find_open_data(event),
                                          verbose=True)
        # ホワイトニング
        white = data.whiten(4, 2)
        # バンドパスフィルター（20-300 Hz）
        filtered = white.bandpass(20, 300)
        return np.array(filtered.value), int(filtered.sample_rate.value)
    except ImportError:
        print("GWpy が必要です: pip install gwpy")
        return gravitational_wave_chirp(), 44100
```

### 日震学（Helioseismology）の音化

太陽内部を伝わる音響波（5分振動）のソニフィケーション。

```python
def helioseismology_tones(duration=5.0, sample_rate=44100):
    """
    太陽の5分振動（p モード）の音化。
    代表的なモードを重ね合わせて擬似的な太陽音を生成。
    """
    # GONG/BiSON データより抜粋した代表的な p モード周波数 [μHz]
    # 実際のデータは例: 2090, 2170, 2250 μHz (l=0, n=11-13)
    p_mode_frequencies_uHz = [
        1726, 1836, 1949, 2063, 2181, 2302, 2425, 2550,
        2676, 2803, 2932, 3063, 3196, 3330, 3466
    ]

    # 時間加速率: 約 40000 倍で可聴域（μHz → Hz 相当）
    speed_up = 42000
    audio_freqs = [f * 1e-6 * speed_up for f in p_mode_frequencies_uHz]

    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate
    out = np.zeros(n)

    for freq in audio_freqs:
        amp = np.random.uniform(0.3, 1.0)
        phase = np.random.uniform(0, 2 * np.pi)
        out += amp * np.sin(2 * np.pi * freq * t + phase)

    return out / (np.max(np.abs(out)) + 1e-9)
```

### 惑星磁気圏波動

| 波動種別 | 周波数域 | 発生機構 |
|---|---|---|
| コーラス | 0.1-0.5 fce | 電子サイクロトロン共鳴 |
| ホイッスラー波 | 0.01-1 fce | 落雷→磁力線誘導伝播 |
| ヘム（Hiss） | 100-2000 Hz | 放射線帯で生成 |
| ELF ハム | 0.1-10 Hz | 太陽風由来 |

```python
def whistler_wave(duration=3.0, sample_rate=44100,
                  f_start=8000, f_end=300, dispersion=0.5):
    """
    ホイッスラー波（落雷から発生した電磁波が磁気圏を通過する際の分散）。
    高周波が先に到着し、周波数が時間とともに低下する特徴的なチャープ音。
    """
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate

    # 分散関係: t ∝ 1/sqrt(f)
    # 到達時刻 t(f) = D / sqrt(f) （D: 分散定数）
    freq_at_t = (dispersion / (t + 0.01)) ** 2
    freq_at_t = np.clip(freq_at_t, f_end, f_start)

    phase = 2 * np.pi * np.cumsum(freq_at_t) / sample_rate

    # 振幅エンベロープ
    env = np.exp(-t * 0.5)
    return env * np.sin(phase)
```

---

## 5. 生物学・神経科学

### 蝸牛モデル（Cochlear Model）

**ガンマトーン（Gammatone）フィルターバンク**は蝸牛の周波数選択性を近似する。

```
g(t) = t^(n-1) · exp(-2πbt) · cos(2πf_c·t + φ)

n: フィルター次数（通常 4）
b: バンド幅（ERBスケール）
f_c: 中心周波数
```

**ERB（Equivalent Rectangular Bandwidth）スケール**：

```
ERB(f) = 24.7 × (4.37×10⁻³ × f + 1)   [Hz]
```

```python
def gammatone_filterbank(n_filters=64, f_low=100, f_high=8000,
                         order=4, sample_rate=44100):
    """
    ガンマトーンフィルターバンク（蝸牛の周波数分析モデル）。
    入力音をコクリアグラムに変換する基礎。
    """
    from scipy import signal as sp_signal

    # ERB スケールで等間隔な中心周波数
    def hz_to_erb(f):
        return 21.4 * np.log10(4.37e-3 * f + 1)

    def erb_to_hz(e):
        return (10**(e / 21.4) - 1) / 4.37e-3

    erbs = np.linspace(hz_to_erb(f_low), hz_to_erb(f_high), n_filters)
    center_freqs = erb_to_hz(erbs)

    filters = []
    for f_c in center_freqs:
        b_erb = 24.7 * (4.37e-3 * f_c + 1)
        b_coef = 1.019 * b_erb  # 定数係数
        # 近似として IIR ローパスフィルターを使用
        b, a = sp_signal.butter(order, f_c / (sample_rate / 2), btype='low')
        filters.append((b, a, f_c))

    def apply_filterbank(audio):
        output = np.zeros((n_filters, len(audio)))
        for i, (b, a, f_c) in enumerate(filters):
            # 各フィルターに通し、中心周波数で変調して包絡線を抽出
            filtered = sp_signal.lfilter(b, a, audio)
            t = np.arange(len(audio)) / sample_rate
            demod = filtered * np.cos(2 * np.pi * f_c * t)
            output[i] = np.abs(sp_signal.hilbert(demod))
        return output

    return center_freqs, apply_filterbank


def cochlear_synthesis(cochleagram, center_freqs, sample_rate=44100):
    """
    コクリアグラムから音を再合成（蝸牛逆モデル）。
    cochleagram: [n_filters × n_samples] の活性化マップ
    """
    n_samples = cochleagram.shape[1]
    t = np.arange(n_samples) / sample_rate
    out = np.zeros(n_samples)

    for i, f_c in enumerate(center_freqs):
        env = cochleagram[i]
        carrier = np.cos(2 * np.pi * f_c * t)
        out += env * carrier

    return out / (np.max(np.abs(out)) + 1e-9)
```

### Hodgkin-Huxley モデル（神経発火）

ニューロンの活動電位（スパイク）を記述するイオンチャネルモデル。

```
C_m · dV/dt = I_ext - g_Na·m³h(V-E_Na) - g_K·n⁴(V-E_K) - g_L(V-E_L)
```

```python
def hodgkin_huxley(I_ext, duration=0.5, sample_rate=44100):
    """
    Hodgkin-Huxley ニューロンモデルによる発火パターン音生成。
    I_ext: 外部電流 [μA/cm²]（10-15 で繰り返し発火）
    """
    from scipy.integrate import solve_ivp

    # HH モデルパラメーター
    C_m = 1.0    # 膜容量 [μF/cm²]
    g_Na = 120.0; E_Na = 50.0   # ナトリウムチャネル
    g_K  = 36.0;  E_K  = -77.0  # カリウムチャネル
    g_L  = 0.3;   E_L  = -54.4  # 漏れチャネル

    def alpha_m(V): return 0.1*(V+40)/(1-np.exp(-(V+40)/10)+1e-9)
    def beta_m(V):  return 4*np.exp(-(V+65)/18)
    def alpha_h(V): return 0.07*np.exp(-(V+65)/20)
    def beta_h(V):  return 1/(np.exp(-(V+35)/10)+1)
    def alpha_n(V): return 0.01*(V+55)/(1-np.exp(-(V+55)/10)+1e-9)
    def beta_n(V):  return 0.125*np.exp(-(V+65)/80)

    def hh(t, y):
        V, m, h, n = y
        dVdt = (I_ext - g_Na*m**3*h*(V-E_Na)
                - g_K*n**4*(V-E_K)
                - g_L*(V-E_L)) / C_m
        dmdt = alpha_m(V)*(1-m) - beta_m(V)*m
        dhdt = alpha_h(V)*(1-h) - beta_h(V)*h
        dndt = alpha_n(V)*(1-n) - beta_n(V)*n
        return [dVdt, dmdt, dhdt, dndt]

    # 初期条件（静止電位付近）
    y0 = [-65.0, 0.05, 0.6, 0.32]
    t_span = (0, duration)
    t_eval = np.linspace(0, duration, int(duration * sample_rate))

    sol = solve_ivp(hh, t_span, y0, t_eval=t_eval,
                    method='RK45', max_step=1e-4)

    V_trace = sol.y[0]
    # 膜電位を可聴音として正規化
    return (V_trace - V_trace.mean()) / (np.std(V_trace) + 1e-9) * 0.8
```

### HH モデルによる音楽的応用

| パラメーター | 音楽的効果 |
|---|---|
| `I_ext` 増大 | 発火頻度増加 → ピッチ上昇 |
| 複数 HH 結合 | 神経集団の同期発火 → コーラス効果 |
| ノイズ付加 | 確率共鳴 → テクスチャー生成 |
| パラメーター変調 | 神経バースティング → リズムパターン |

### 発声器官のモデル（Two-Mass Model）

Ishizaka-Flanagan 2 質量モデルによる声帯振動：

```python
def two_mass_vocal_fold(f0_target=150, duration=1.0, sample_rate=44100):
    """
    Ishizaka-Flanagan 2 質量モデルによる声帯振動。
    声道フィルター（フォルマント）と組み合わせて母音を合成する。
    """
    from scipy.integrate import solve_ivp

    # モデルパラメーター（男性声帯の標準値）
    m1, m2 = 0.125e-3, 0.025e-3  # 質量 [g]
    k1, k2 = 80.0, 8.0           # ばね定数 [N/m]（近似値）
    r1, r2 = 0.02, 0.002         # 減衰係数
    kc = 25.0                     # 結合ばね定数

    def model(t, y):
        x1, v1, x2, v2 = y
        # 接触力（声帯が閉じている場合）
        F_contact1 = -kc * min(0, x1 + x2) * 0.5
        F_contact2 = -kc * min(0, x1 + x2) * 0.5

        ax1 = (-k1*x1 - r1*v1 + kc*(x2-x1) + F_contact1) / m1
        ax2 = (-k2*x2 - r2*v2 + kc*(x1-x2) + F_contact2) / m2
        return [v1, ax1, v2, ax2]

    t_eval = np.linspace(0, duration, int(duration * sample_rate))
    sol = solve_ivp(model, (0, duration), [0.1e-3, 0, 0.05e-3, 0],
                    t_eval=t_eval, method='RK45', max_step=1e-5)

    glottal_flow = np.maximum(sol.y[0] + sol.y[2], 0)  # 声門開口面積
    return glottal_flow / (np.max(glottal_flow) + 1e-9)
```

---

## 6. クジラ・コウモリの音響モデル

### コウモリのエコーロケーション

コウモリは 20-100 kHz の超音波をチャープ変調して物体を検知する。

```python
def bat_echolocation_chirp(f_start=80000, f_end=25000,
                            duration=0.003, sample_rate=192000):
    """
    コウモリのFMチャープ（周波数変調超音波）。
    sample_rate を 192000 Hz に上げることで超音波域を扱える（学術用途）。
    可聴化には 10 倍加速（time stretching）が必要。
    """
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate

    # 指数的周波数スイープ（生物音響的により正確）
    f = np.exp(np.linspace(np.log(f_start), np.log(f_end), n))
    phase = 2 * np.pi * np.cumsum(f) / sample_rate

    # ガウシアンエンベロープ
    env = np.exp(-((t - duration/2) / (duration/4))**2)
    return env * np.sin(phase)


def whale_song_segment(call_type='humpback', duration=5.0, sample_rate=44100):
    """
    クジラの歌の近似モデル（ザトウクジラの繰り返しユニット）。
    """
    n = int(duration * sample_rate)
    t = np.arange(n) / sample_rate
    out = np.zeros(n)

    if call_type == 'humpback':
        # ザトウクジラの典型的な音型：LF パルス列 + FM うなり
        # ユニット1: 低周波スウープ (140-80 Hz)
        segment = int(duration * 0.3 * sample_rate)
        f_sweep = np.linspace(140, 80, segment)
        phase = 2 * np.pi * np.cumsum(f_sweep) / sample_rate
        out[:segment] += np.sin(phase) * np.hanning(segment)

        # ユニット2: FM ブループ (80-200 Hz)
        s2 = int(duration * 0.3 * sample_rate)
        offset = int(duration * 0.35 * sample_rate)
        f2 = np.linspace(80, 200, s2)
        ph2 = 2 * np.pi * np.cumsum(f2) / sample_rate
        end = min(offset + s2, n)
        out[offset:end] += np.sin(ph2[:end-offset]) * np.hanning(end - offset)

    return out / (np.max(np.abs(out)) + 1e-9)
```

---

## 参考文献・リソース

| 資料 | 内容 |
|---|---|
| Fettweis (1986) "Wave Digital Filters" | WDF の包括的解説 |
| Hodgkin & Huxley (1952) "A quantitative description..." | HH モデルの原著論文 |
| Patterson et al. (1992) "Auditory filterbank" | ガンマトーンフィルターバンク |
| Ishizaka & Flanagan (1972) "Synthesis of voiced sounds..." | 声帯 2 質量モデル |
| Abbott et al. (2016) "Observation of Gravitational Waves" | LIGO GW150914 |
| Duvall et al. (1993) "Asymmetries of solar oscillation..." | 日震学入門 |
| GWpy 公式ドキュメント | 重力波データ処理 |
| ObsPy 公式ドキュメント | 地震波データ処理 |

---

[← 概要に戻る](sound-from-physics-overview.md)
