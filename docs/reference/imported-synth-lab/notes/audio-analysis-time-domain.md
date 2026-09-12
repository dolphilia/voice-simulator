# 時間領域の解析手法

時間領域は波形の振幅変化を直接扱う。計算コストが低くリアルタイム処理向き。  
周波数成分の詳細は分からないが、音量・エンベロープ・粗さを素早く把握できる。

---

## RMS（Root Mean Square）エネルギー

**何が分かるか**  
フレーム単位の平均エネルギー・実効音量。ダイナミクス変化の追跡、音声区間検出（VAD）、コンプレッサーの動作模倣に使われる。

**計算式**

```
RMS = sqrt( (1/N) * Σ x[n]² )
```

**実装（numpy）**

```python
def rms_envelope(signal, frame_size, hop_size, sample_rate):
    n_frames = (len(signal) - frame_size) // hop_size + 1
    rms = np.array([
        np.sqrt(np.mean(signal[i*hop_size : i*hop_size+frame_size] ** 2))
        for i in range(n_frames)
    ])
    times = np.arange(n_frames) * hop_size / sample_rate
    return times, rms
```

**ポイント**
- `20 * log10(rms)` で dBFS 変換するとラウドネス近似になる
- ピーク包絡線よりノイズに頑健
- フレームサイズを大きくするほど平滑化される

---

## ZCR（Zero Crossing Rate、ゼロ交差率）

**何が分かるか**  
単位時間あたりに波形が 0 をまたぐ回数。高周波・ノイズ成分が多いほど高い。  
打楽器音 vs 有声音の識別、有声/無声判定、シンバル検出に有効。

**計算式**

```
ZCR = (1 / 2N) * Σ |sign(x[n]) - sign(x[n-1])|
```

**実装（numpy）**

```python
def zero_crossing_rate(signal, frame_size, hop_size, sample_rate):
    n_frames = (len(signal) - frame_size) // hop_size + 1
    zcr = np.array([
        np.sum(np.abs(np.diff(np.sign(
            signal[i*hop_size : i*hop_size+frame_size]
        )))) / (2 * frame_size)
        for i in range(n_frames)
    ])
    times = np.arange(n_frames) * hop_size / sample_rate
    return times, zcr
```

**ポイント**
- スペクトル重心（後述）と正の相関がある
- 周波数領域に行かずに「音の明るさ」の簡易指標として使える
- プラック音では、アタック直後に高く、サステイン部で急低下する

---

## 振幅エンベロープ（Amplitude Envelope）

**何が分かるか**  
波形の包絡線（外形）。シンセサイザーの ADSR 形状解析、アタック点検出、楽器分類に使われる。

### 手法の比較

| 手法 | 計算 | 特徴 |
|---|---|---|
| フレームピーク法 | 各フレーム内の最大振幅 | 最もシンプル |
| RMS 法 | 各フレームの RMS | ノイズに頑健 |
| ヒルベルト変換法 | 解析信号の絶対値 | 物理的に厳密・連続的 |
| ローパスフィルタ法 | 全波整流 → LPF | 平滑度をカットオフで制御可能 |

**実装（ヒルベルト変換）**

```python
from scipy.signal import hilbert

analytic_signal = hilbert(wave)
envelope = np.abs(analytic_signal)         # 瞬時振幅
inst_phase = np.unwrap(np.angle(analytic_signal))  # 瞬時位相
inst_freq  = np.diff(inst_phase) / (2 * np.pi / sample_rate)  # 瞬時周波数
```

**ポイント**
- ヒルベルト変換では瞬時振幅・瞬時位相・瞬時周波数を一度に得られる
- オンセット検出（音の立ち上がり点）の前処理として使われることが多い

---

## その他の時間領域特徴量

### AMDF（Average Magnitude Difference Function、平均振幅差分関数）

```
AMDF(τ) = (1/N) * Σ |x[n] - x[n+τ]|
```

- ACF（自己相関）より計算が軽量（乗算なし）
- ピッチ推定に使われる。最小値の遅延 τ が基本周期

```python
def amdf(signal, max_lag):
    return [np.mean(np.abs(signal[:-lag] - signal[lag:])) for lag in range(1, max_lag)]
```

### クレストファクター（Crest Factor）

```
CF = peak / RMS
```

- ピーク対 RMS 比。クリッピングやトランジェントの検出
- dB 換算 = `20 * log10(CF)`

### 尖度（Kurtosis）

- 振幅分布の「とがり度」
- 打撃音・トランジェントが多いと高くなる
- 連続的な持続音は低い値を示す

```python
from scipy.stats import kurtosis
k = kurtosis(wave)
```

---

## 実践のポイント

- **最初の確認**: 波形表示 → RMS エンベロープ の順で全体像を把握する
- **比較のベースライン**: ZCR と RMS を並べて描画すると音の特性変化がよく見える
- **計算コスト**: 時間領域の手法はすべてリアルタイム処理に使える水準

---

[← 概要に戻る](audio-analysis-overview.md)
