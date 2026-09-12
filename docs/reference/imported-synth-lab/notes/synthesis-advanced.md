# 高度・現代的な合成手法

---

## 1. Formant 合成（FOF / CHANT）

ヒューマンボイスの声道特性（フォルマント）を直接モデル化する合成手法。  
Xavier Rodet が IRCAM の CHANT システム（1984 年）で開発した FOF（Fonctions d'onde formantique）法が代表的。

### フォルマントとは

声道は共鳴腔として特定の周波数帯域（フォルマント）を強調する。  
通常 3〜5 個のフォルマント（F1〜F5）でほとんどの母音を表現できる。

| フォルマント | 役割 |
|---|---|
| F1 + F2 | 母音識別に最重要 |
| F3 | 話者の個性 |
| F4, F5 | 音声の輝き・存在感 |

### 日本語母音のフォルマント概算値（Hz）

| 母音 | F1 | F2 | F3 |
|---|---|---|---|
| あ | 700 | 1220 | 2600 |
| い | 280 | 2250 | 3000 |
| う | 300 | 870 | 2240 |
| え | 400 | 1900 | 2550 |
| お | 450 | 750 | 2400 |

### FOF の仕組み

各フォルマントを**減衰サイン波**の時間領域表現でモデル化する。

```
fof(t) = exp(-α·t) · sin(2π·ff·t) × window(t)
```

基音周期ごとに FOF インパルスを発射し、複数のフォルマントを加算する。

```python
def fof_synthesis(f0, formants, duration, sample_rate=44100):
    """FOF フォルマント合成
    formants: [(freq, bandwidth, amplitude), ...]
    """
    n      = int(duration * sample_rate)
    output = np.zeros(n)
    period = int(sample_rate / f0)

    for onset in range(0, n, period):
        for freq, bw, amp in formants:
            t_len = min(int(3.0 / bw * sample_rate), n - onset)
            if t_len <= 0:
                continue
            t     = np.arange(t_len) / sample_rate
            alpha = np.pi * bw
            fof   = amp * np.exp(-alpha * t) * np.sin(2*np.pi*freq*t)
            output[onset:onset + t_len] += fof * np.hanning(t_len)

    return output
```

### LPC との関係

- **LPC**（線形予測符号化）も声道をフィルターとしてモデル化するが、FOF はより物理的なモード表現
- LPC は分析手法として音声の声道特性を抽出するのに使い、合成段階は Formant モデルで行うハイブリッドアプローチが一般的

---

## 2. Concatenative 合成（コーパスベース合成）

大規模な音声データベース（コーパス）から最適なセグメントを選択・連結して新しい音を生成する手法。

### 処理フロー

```
1. コーパス構築: 音源を分割 → 特徴量（MFCC・スペクトル重心・ピッチ等）を抽出・インデックス化
2. ターゲット分析: 生成したい音の特徴量シーケンスを算出
3. マッチング: 最近傍探索で最適セグメントを選択
4. 連結: クロスフェードで滑らかに接続
```

### 特徴

| 項目 | 詳細 |
|---|---|
| 強み | コーパスに含まれる音の質感をそのまま活かせる |
| 弱み | コーパスの規模・品質に大きく依存する |
| 主な用途 | 音声合成（TTS）、テクスチャー生成、実験的音楽 |
| 代表実装 | IRCAM CataRT、Max/MSP の catart-mubu |

---

## 3. Feedback FM / カオティックオシレーター

### Feedback FM

オペレーターが自己変調（自分自身の出力を変調信号として使う）する特殊な FM 形態。  
詳細は [synthesis-additive-modulation.md](synthesis-additive-modulation.md) を参照。

β の値に応じて音色が段階的に変化する。

| β 範囲 | 挙動 |
|---|---|
| 0〜0.5 | ほぼ正弦波 |
| 0.5〜2 | 倍音が増加、鋸歯状波に近づく |
| 2〜4 | 金属的・複雑な倍音 |
| 4〜 | カオス的ノイズへ遷移 |

### ローレンツアトラクターなどのカオスオシレーター

カオス的な微分方程式（ローレンツ系・ダフィング振動子等）を音声信号の生成源として使う実験的手法。  
決定論的でありながら非周期的で複雑な波形を生成する。

```python
def lorenz_audio(sigma=10, rho=28, beta_l=8/3,
                 duration=1.0, sample_rate=44100):
    """ローレンツアトラクターを音源として使用"""
    n   = int(duration * sample_rate)
    dt  = 1.0 / sample_rate
    x, y, z = 0.1, 0.0, 0.0
    out = np.zeros(n)
    for i in range(n):
        dx = sigma * (y - x)
        dy = x * (rho - z) - y
        dz = x * y - beta_l * z
        x += dx * dt; y += dy * dt; z += dz * dt
        out[i] = x
    # 正規化
    return out / (np.max(np.abs(out)) + 1e-9)
```

---

## 4. ニューラル音声合成

### WaveNet（DeepMind, 2016）

自己回帰型の因果的畳み込みニューラルネットワークで、1 サンプルずつ波形を生成する。  
**拡張因果畳み込み（Dilated Causal Convolutions）** により長距離依存関係をモデル化。

```
層の拡張率: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512 （繰り返し）
受容野 = 2^10 = 1024 サンプル × 繰り返し数
```

| 特徴 | 詳細 |
|---|---|
| 音質 | 非常に高い（当時の SOTA） |
| 推論速度 | 非常に遅い（リアルタイム困難） |
| 後継技術 | WaveRNN、WaveGrad、DiffWave |

### NSynth（Google Magenta, 2017）

WaveNet ベースの**自己エンコーダー**で楽器音の潜在表現を学習。  
305,000 個の単音サンプル（1006 楽器）で学習。

- 異なる楽器音の**潜在ベクトルを補間**することで「ピアノとギターの中間音」を生成
- 楽器の音色・ピッチ・速度を独立した潜在次元に分離

### DDSP（Differentiable DSP, 2020）

Engel ら（Google Magenta）が提案した画期的フレームワーク。  
**微分可能な古典 DSP 素子を深層学習と統合**し、End-to-End で学習可能にした。

#### アーキテクチャ

```
[入力: F0 + Loudness の時系列]
         ↓
[ニューラルネットワーク（LSTM/MLP）]
         ↓
[DSP パラメーター（倍音振幅時系列 + ノイズフィルター係数）]
         ↓
[加算合成器]   +   [フィルタードノイズ]
         ↓               ↓
              [加算合成]
                  ↓
              [リバーブ（FIR）]
                  ↓
              [出力波形]
```

#### 特徴

| 項目 | WaveNet / NSynth | DDSP |
|---|---|---|
| パラメーター数 | 数百万〜数千万 | 数万（軽量） |
| 推論速度 | 遅い | 高速（リアルタイム可能） |
| 音楽的制御性 | 難しい（潜在空間） | 直接的（F0・Loudness） |
| 学習の効率 | 大量データ必要 | 少量でも可 |

```python
def ddsp_additive(f0_contour, amplitudes, sample_rate=16000, frame_size=64):
    """DDSP 風加算合成器（教育的簡易実装）
    f0_contour: 基音周波数の時系列 [n_frames]
    amplitudes: 倍音振幅の時系列 [n_frames, n_harmonics]
    """
    n_frames, n_harmonics = amplitudes.shape
    n_samples = n_frames * frame_size

    # フレーム → サンプル補間
    f0 = np.interp(np.arange(n_samples),
                   np.arange(n_frames) * frame_size, f0_contour)
    output = np.zeros(n_samples)

    for h in range(1, n_harmonics + 1):
        harm_freq = np.clip(f0 * h, 0, sample_rate / 2)
        phase = np.cumsum(2*np.pi * harm_freq / sample_rate)
        amp_h = np.interp(np.arange(n_samples),
                          np.arange(n_frames) * frame_size,
                          amplitudes[:, h-1])
        output += amp_h * np.sin(phase)

    return output
```

#### 応用

- **ティンバー変換**: バイオリン → フルートなどのリアルタイム音色変換
- **楽器モデリング**: 少量のサンプルから楽器をモデル化
- **音楽生成**: 楽譜情報（F0 + Loudness）から自然な演奏音を合成

---

## 各手法の研究・実装リソース

| 手法 | 参考資料 |
|---|---|
| FOF / CHANT | IRCAM 論文「Chant: MIDI to Sound Synthesis」(1984) |
| Concatenative | CataRT（IRCAM）, sms-tools |
| WaveNet | DeepMind Blog (2016), WaveNet Paper（arXiv:1609.03499） |
| NSynth | Google Magenta NSynth Paper（arXiv:1704.01279） |
| DDSP | ICLR 2020 Paper（arXiv:2001.04643）、[ddsp ライブラリ](https://github.com/magenta/ddsp) |

---

## 現代的なハイブリッドアプローチ

最新の研究・製品では複数手法を組み合わせることが主流。

| 組み合わせ | 特徴 |
|---|---|
| ウェーブテーブル + FM | Waldorf Blofeld など。テーブルを FM で変調 |
| アディティブ + グラニュラー | スペクトルを制御しながらテクスチャーを追加 |
| 物理モデル + PCM | 弦の振動モデル + 実録音の残響 |
| DDSP + アディティブ | ML でパラメーターを推定、古典 DSP で合成 |
| サブトラクティブ + スペクトル | VCF の代わりに位相ボコーダーでスペクトル整形 |

---

[← 概要に戻る](synthesis-overview.md)
