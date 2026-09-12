# アディティブ合成・変調系合成

---

## 1. アディティブ合成

フーリエの定理に基づき、正弦波を重ね合わせて任意の音色を作る手法。  
理論上はあらゆる音を合成できる。

### 基本式

```
y(t) = Σ Aₙ(t) · sin(2π · n · f₀ · t + φₙ(t))
```

各倍音の振幅 Aₙ と位相 φₙ を独立かつ時間変化させることで、豊かな音色ダイナミクスを表現できる。

### ハモンドオルガン

アディティブ合成の最古の商業実装例。9 本のドローバーが各倍音の音量を 0〜8 の 9 段階で制御する。

| ドローバー | 表記 | 倍音番号 |
|---|---|---|
| 16' | サブオクターブ | 0.5倍 |
| 8' | 基音 | 1倍 |
| 5⅓' | 第3倍音（5度上） | 1.5倍 |
| 4' | 第2倍音（オクターブ上） | 2倍 |
| 2⅔' | 第3倍音 | 3倍 |
| 2' | 第4倍音 | 4倍 |
| 1⅗' | 第5倍音 | 5倍 |
| 1⅓' | 第6倍音 | 6倍 |
| 1' | 第8倍音 | 8倍 |

```python
def additive(freq, harmonics_amp, duration, sample_rate=44100):
    """加算合成（各倍音の振幅リストを指定）"""
    t   = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    out = sum(a * np.sin(2*np.pi*n*freq*t)
              for n, a in enumerate(harmonics_amp, start=1))
    mx = np.max(np.abs(out))
    return out / mx if mx > 0 else out


def hammond(freq, drawbars, duration, sample_rate=44100):
    """ハモンドオルガン ドローバーシミュレーション"""
    ratios = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return sum((db/8.0) * np.sin(2*np.pi*freq*r*t)
               for db, r in zip(drawbars, ratios))
```

### 実装上の課題と最適化

| 課題 | 解決策 |
|---|---|
| 計算量が O(n) | FFT 法（逆フーリエ変換で一括生成） |
| リアルタイム性 | GPU 並列（CuPy 等）、BLAS 最適化 |
| 倍音の時間変化 | フレームごとに振幅を補間 |

---

## 2. FM / PM 合成（詳細）

→ 基本は [synthesis-classic.md](synthesis-classic.md) を参照。ここでは実践的な音色設計の観点を補足する。

### β の役割と音色変化

```
β が小さい（0〜1）: 正弦波に近い、クリーンな音
β が中程度（1〜5）: 倍音が豊富、ブラス・パッド系
β が大きい（5〜）:  金属・打楽器系、ノイズに近づく
```

アタックで β を大きくし、サステインで小さくすることで自然な「鳴り始めが明るく、落ち着いていく」ブラスサウンドを作れる。

### Feedback FM

オペレーターが自己変調（自分自身を変調信号として使う）する特殊な FM 形態。

```python
def feedback_fm(freq, beta, duration, sample_rate=44100):
    """フィードバック FM: y[n] = sin(2π·f·n/sr + β·y[n-1])"""
    n   = int(duration * sample_rate)
    out = np.zeros(n)
    phase     = 0.0
    phase_inc = 2*np.pi*freq / sample_rate
    prev      = 0.0
    for i in range(n):
        out[i] = np.sin(phase + beta * prev)
        prev   = out[i]
        phase += phase_inc
    return out
```

β が小さい間は調和的な音色。大きくするにつれてカオス的ノイズへと遷移する。  
**フィードバック経路に LPF を挿入**するとエイリアシングを防ぎながら豊かな倍音を保持できる。

---

## 3. AM 合成 / リングモジュレーション

### AM（振幅変調）

キャリア信号の振幅をモジュレーターで変調する。

```
y(t) = [1 + m·sin(2π·fm·t)] · sin(2π·fc·t)
```

展開すると **fc, fc+fm, fc-fm** の 3 成分が生成される。

```python
def am_synth(fc, fm, mod_index, duration, sample_rate=44100):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return (1 + mod_index * np.sin(2*np.pi*fm*t)) * np.sin(2*np.pi*fc*t)
```

### リングモジュレーション（100% AM）

キャリアとモジュレーターの**積**のみを取る。元のキャリア成分が消え、差音と和音のみが残る。

```
y(t) = sin(2π·fc·t) · sin(2π·fm·t)
     = 0.5 · [cos(2π(fc-fm)t) - cos(2π(fc+fm)t)]
```

```python
def ring_mod(fc, fm, duration, sample_rate=44100):
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    return np.sin(2*np.pi*fc*t) * np.sin(2*np.pi*fm*t)
```

**整数比（fc:fm）** → 調和的・楽器的サウンド  
**非整数比** → 非調和的な金属・ベル系サウンド

### AM / RM と FM の比較

| 項目 | AM / RM | FM |
|---|---|---|
| 生成成分 | 差音・和音（サイドバンド 2 本） | ベッセル関数由来の多倍音 |
| 制御のしやすさ | 直感的 | 習熟が必要 |
| 音色の複雑さ | 中 | 高 |
| 計算コスト | 低 | 低 |

---

## 4. Phase Distortion（PD 合成）

1984 年に Casio が開発（CZ-101 等）。サイン波の**位相を非線形にゆがめる**ことで倍音を生成。  
`DCW`（Digital Control Waveform）エンベロープで歪み量を時間変化させ、VCF なしでフィルタースイープに相当する音色変化を実現する。

### 仕組み

位相インデックスの進み方を変える。前半を速く進め後半をゆっくり進めると鋸歯状波に近いスペクトルが得られる。

```python
def phase_distortion(freq, distortion, mode='saw', duration=1.0, sample_rate=44100):
    """Phase Distortion 合成"""
    n     = int(sample_rate * duration)
    phase = np.linspace(0, 2*np.pi, n, endpoint=False)

    if mode == 'saw':
        # 前半を加速し後半を通常速度に
        threshold = np.pi * (1.0 - distortion * 0.9)
        d_phase = np.where(
            phase < threshold,
            phase * np.pi / max(threshold, 1e-9),
            np.pi + (phase - threshold) * np.pi / max(2*np.pi - threshold, 1e-9)
        )
    elif mode == 'resonant':
        # 共鳴型：折り返しで高調波を生成
        d_phase = (phase * (1 + distortion * 4)) % (2*np.pi)

    return np.sin(d_phase)
```

### FM との違い

| 項目 | Phase Distortion | FM |
|---|---|---|
| スペクトル構造 | 比較的予測可能な線形的変化 | ベッセル関数由来の非線形変化 |
| アナログとの類似性 | アナログシンセの音色に近い | デジタル的・独自の音色 |
| フィルター | DCW エンベロープで代替 | 不要（倍音を直接制御） |

---

## 5. PWM（パルス幅変調）

矩形波のデューティ比（パルス幅）を変化させて音色を変える手法。

- デューティ比 50% → 完全な矩形波（奇数次倍音のみ）
- デューティ比 0% / 100% → 極薄パルス（全倍音が均等に増加）
- LFO で緩やかにデューティ比を変化 → 独特の「コーラス感・うねり」

```python
def pwm_osc(freq, duty_env, duration, sample_rate=44100):
    """PWM オシレーター（デューティ比をエンベロープで変化）"""
    n = int(sample_rate * duration)
    t = np.arange(n) / sample_rate
    phase = (t * freq) % 1.0
    return np.where(phase < duty_env[:n], 1.0, -1.0).astype(np.float32)
```

---

## 6. ベクターシンセシス（Vector Synthesis）

1986 年に Sequential Circuits Prophet-VS で初採用。  
4 つの波形（オシレーター A/B/C/D）をジョイスティックで 2 次元的にブレンドする。

```
        B
        |
   A ---+--- C
        |
        D

X 位置 → A:C または B:D のブレンド率
Y 位置 → 上ペアと下ペアのブレンド率
```

**バイリニア補間**

```python
def vector_mix(waves, x, y):
    """4 つの波形をベクター合成（x, y はそれぞれ 0.0〜1.0）"""
    # A:上左, B:上右, C:下左, D:下右
    a, b, c, d = waves
    top    = a * (1-x) + b * x
    bottom = c * (1-x) + d * x
    return top * (1-y) + bottom * y
```

ジョイスティックのオートメーションで時間的に変化する音色モーフィングを実現する。

---

## 変調系手法の選択指針

| 目的 | 推奨手法 |
|---|---|
| 倍音豊富なデジタル音色（EP・ブラス・ベル） | FM 合成 |
| 金属・ベル系の非調和音 | AM / リングモジュレーション |
| アナログライクでフィルタースイープ感のある音 | Phase Distortion |
| 動きのある矩形波系サウンド | PWM |
| 音色が時間で変化する複雑なサウンド | ベクターシンセ / ウェーブテーブル |
| 精密な倍音コントロール | アディティブ合成 |

---

[← 概要に戻る](synthesis-overview.md)
