# 計画書：生成波形とリファレンス波形の比較ツール

> **Status: Implemented baseline**
> この文書に記載したフェーズ 0〜4 は、現行比較 CLI の基礎として実装済みである。自己比較を超えた校正、複数参照、人間音声の基準分布、holdout、知覚評価を含む次段階は [`comparison-evaluation-framework-plan.md`](comparison-evaluation-framework-plan.md) を参照する。

## 概要

この文書は、Voice Simulator が生成した WAV と、UTAU などのリファレンス WAV を比較し、近似度や相違を数値・図で確認するための研究ツール計画である。

目的は、生成音が「どれだけ似ているか」を単一スコアで断定することではない。波形、スペクトル、フォルマント、F0、声質、ノイズ成分、時間変化を複数の観点で比較し、どの部分が近く、どの部分が離れているかを実装判断に使える形で出すことである。

## 背景

現状の研究スクリプトには、以下の処理が既に存在する。

- WAV 読み込み: `scipy.io.wavfile`
- mono float 正規化
- 無音トリム
- 安定中央区間の切り出し
- F0 推定
- LPC による F1/F2/F3 推定
- スペクトル重心、ロールオフ、高域比、非周期成分近似
- 摩擦音・息成分のスペクトル指標

依存関係は `numpy`、`scipy`、`matplotlib` のみで足りている。最初の比較ツールもこの範囲で実装できる。

## 重要な前提

### 生波形だけを比較しない

同じ母音に聞こえる音でも、位相、開始位置、基本周波数、音量が少し違うだけで、時間領域の RMSE は大きく悪化する。したがって、生波形差分は参考値に留め、主評価はスペクトル包絡や特徴量差分に置く。

### 比較対象によって評価方法を変える

母音の安定区間、子音から母音への遷移、息や摩擦音では見るべき指標が異なる。

- 母音: F0、F1/F2/F3、スペクトル包絡、倍音傾斜
- 子音: 高域ノイズ、スペクトル重心、ピーク周波数、ゼロ交差率
- 遷移: 時間方向のスペクトログラム差、フォルマント軌跡、DTW 距離
- 声質: brightness、breathiness に対応する高域比・非周期比・スペクトル傾斜

## 比較ツールの構成

### 入力

最小入力は、生成 WAV と参照 WAV の 2 ファイルとする。

```bash
python research/scripts/compare_waveforms.py \
  --generated research/data/raw/generated/example.wav \
  --reference research/data/raw/reference/utau-samples/.../あ.wav \
  --label a
```

将来的には CSV で複数ペアを一括比較できるようにする。

```bash
python research/scripts/compare_waveforms.py \
  --pairs research/data/processed/analysis/generated-reference-pairs.csv
```

### 出力

単一ペア比較:

- `research/data/processed/analysis/waveform-comparison.csv`
- `research/data/processed/analysis/waveform-comparison-summary.json`
- `research/data/processed/analysis/plots/<comparison_id>.png`

一括比較:

- 1 行 1 ペアの CSV
- ラベル別・モデル別の集計 CSV
- 波形、スペクトル、スペクトログラム差分の PNG

## 前処理

### 1. 読み込みと正規化

- WAV を mono float に変換する
- サンプルレートが異なる場合は `scipy.signal.resample_poly` で参照側または生成側へ合わせる
- DC オフセットを除去する
- peak 正規化ではなく RMS 正規化を基本にする

推奨:

- 比較用の音量正規化は RMS -20 dBFS 相当を基準にする
- 出力 CSV には元 RMS と正規化後 RMS の両方を残す

### 2. 無音トリム

既存の `trim_silence()` を流用する。

- 母音: 中央安定区間を切り出す
- 子音/遷移: 先頭を残し、短すぎる無音だけ落とす
- 息: 中央区間を使う

### 3. 時間位置合わせ

最初は相互相関で全体の遅延を合わせる。

```text
lag = argmax(correlate(reference, generated))
```

ただし、F0 や声質が違うと相互相関は不安定になる。母音比較ではスペクトル包絡比較を主とし、相互相関は波形 RMSE 用の補助にする。

後続では、フレーム特徴量の DTW を追加する。

## 指標

### 基本指標

| 指標 | 目的 |
| --- | --- |
| `duration_delta_ms` | 長さの差 |
| `rms_delta_db` | 音量差 |
| `peak_delta_db` | ピーク差 |
| `zero_crossing_delta` | ノイズ/摩擦性の差 |
| `alignment_lag_ms` | 位置合わせで必要だった遅延 |

### 波形指標

| 指標 | 目的 | 注意 |
| --- | --- | --- |
| `waveform_rmse` | 時間領域の差 | 位相に弱い |
| `normalized_cross_correlation` | 波形形状の相関 | ピッチ差に弱い |
| `snr_db` | 参照に対する差分比 | 同一長・整列後のみ有効 |

波形指標は、同じ合成器のバージョン比較には有用だが、UTAU 参照音声との絶対比較には過信しない。

### スペクトル指標

| 指標 | 目的 |
| --- | --- |
| `log_spectral_distance_db` | 周波数ごとの対数スペクトル差 |
| `spectral_convergence` | スペクトル全体の近さ |
| `spectral_centroid_delta_hz` | 明るさの差 |
| `spectral_rolloff_delta_hz` | 高域分布の差 |
| `low/mid/high_band_ratio_delta` | 帯域別エネルギー差 |
| `spectral_slope_delta_db_per_khz` | 倍音・声質傾向の差 |

初期実装では、0〜8 kHz の範囲を基本にする。母音フォルマント確認では 0〜4 kHz、摩擦音では 3〜12 kHz も見る。

### フォルマント指標

| 指標 | 目的 |
| --- | --- |
| `f1_delta_hz` |
| `f2_delta_hz` |
| `f3_delta_hz` |
| `formant_mae_hz` |
| `formant_relative_error` |

既存の `utau_analyze_vowels.py` の LPC 推定を共通関数化して使う。母音ラベルが分かっている場合は、母音別の妥当範囲で F1/F2/F3 を選ぶ。

### F0 指標

| 指標 | 目的 |
| --- | --- |
| `f0_delta_hz` | 基本周波数差 |
| `f0_delta_cents` | 知覚に近い音高差 |
| `f0_std_delta_cents` | 揺れ・安定度の差 |

生成音と参照音の F0 が大きく違う場合、スペクトル差の解釈が難しくなる。そのため、F0 差は必ず出力する。

### 声質指標

既存の `utau_analyze_voice_quality.py` の指標を流用する。

- `harmonic_slope_db_per_harmonic`
- `nonharmonic_energy_ratio`
- `high_band_ratio`
- `spectral_slope_db_per_khz`
- `rms_std_db`
- `f0_std_cents`

これにより、`brightness` と `breathiness` の調整結果を数値で追える。

### 遷移指標

子音から母音、母音から母音への遷移では、時間平均スペクトルだけでは不十分である。

初期:

- フレームごとの log spectrum 差の平均
- スペクトログラム差分画像
- onset から安定母音までの RMS 立ち上がり時間差

後続:

- MFCC 風のメルケプストラム特徴量を実装する
- DTW で時間伸縮を許して距離を出す
- 短時間 LPC で F1/F2/F3 軌跡を比較する

`librosa` は便利だが依存関係が増える。最初は `numpy/scipy` でメルフィルタバンクと DCT を実装できるため、外部依存は増やさない。

## スコア設計

単一の総合スコアは、最初から作らない。

代わりに、以下のカテゴリ別スコアを出す。

| スコア | 主な構成要素 |
| --- | --- |
| `pitch_score` | F0 cents 差、F0 安定度差 |
| `vowel_shape_score` | F1/F2/F3 差、log spectral distance |
| `timbre_score` | spectral centroid、slope、高域比、非周期比 |
| `noise_score` | flatness、zero crossing、高域/air band |
| `timing_score` | duration、onset、DTW 距離 |

各スコアは 0〜1 の正規化値にできるが、初期段階では生の差分値を重視する。重み付き総合点は、指標の信頼性が見えてから追加する。

## 最初に作る CLI

### `compare_waveforms.py`

責務:

- WAV 2 件を読み込む
- 前処理する
- 指標を計算する
- CSV/JSON/PNG を出力する

想定オプション:

```text
--generated PATH
--reference PATH
--label a|i|u|e|o|shi|su|breath
--mode vowel|noise|transition|auto
--output-csv PATH
--output-json PATH
--plot PATH
--sample-rate 44100
```

### `compare_waveform_pairs.py`

責務:

- ペア CSV を読み込む
- 複数比較を実行する
- 集計 CSV を出す

ペア CSV 例:

```csv
comparison_id,generated_path,reference_path,label,mode,model,preset,notes
vowel_a_utau_001,research/data/raw/generated/a.wav,research/data/raw/reference/utau-samples/.../あ.wav,a,vowel,vowel-formant,utau,
```

## 実装フェーズ

### フェーズ 0：共通音声ユーティリティ化

目的:

既存スクリプトに重複している WAV 読み込み、無音トリム、RMS、スペクトル計算を共通化する。

作業:

- `research/scripts/audio_utils.py` を追加する
- `read_mono_float()`
- `trim_silence()`
- `stable_middle_segment()`
- `rms_db()`
- `spectrum()`
- `resample_to()`

完了条件:

- 既存スクリプトから流用しやすい関数群ができる
- まだ既存スクリプトの大規模改修はしない

実施結果:

- `research/scripts/audio_utils.py` を追加した
- WAV 読み込み、mono float 化、DC 除去、リサンプリング、無音トリム、安定中央区間切り出し、RMS 正規化を実装した
- 相互相関による時間位置合わせを実装した
- スペクトル、帯域比、スペクトル重心、ロールオフ、スペクトル傾斜、log spectral distance、spectral convergence を実装した
- F0 推定、LPC フォルマント推定、formant MAE を共通関数として実装した
- 既存の UTAU 分析スクリプトはまだ大規模改修していない

### フェーズ 1：単一ペア比較

目的:

生成 WAV と参照 WAV の 1 対 1 比較を成立させる。

作業:

- `research/scripts/compare_waveforms.py` を追加する
- 母音モードで基本指標、波形指標、スペクトル指標、F0、フォルマント差を出す
- 比較 PNG を生成する

PNG 内容:

- 上段: 整列後の波形重ね描き
- 中段: log spectrum 重ね描き
- 下段: spectrogram または差分スペクトル

完了条件:

- UTAU の `あ.wav` と生成 `a.wav` を比較できる
- CSV と PNG が出る
- F0 やフォルマント欠損時も落ちずに空欄または `nan` を出す

実施結果:

- `research/scripts/compare_waveforms.py` を追加した
- `--generated`、`--reference`、`--label`、`--mode`、`--sample-rate`、`--output-csv`、`--output-json`、`--plot` を受け取る CLI とした
- 単一ペア比較で CSV、JSON、PNG を出力できる
- PNG には整列後の波形重ね描き、log spectrum 重ね描き、スペクトログラム差分を出す
- `research/data/raw/reference/sample.wav` 同士の自己比較で動作確認した
- 自己比較では `waveform_rmse=0`、`normalized_cross_correlation=1`、`log_spectral_distance_db=0`、`spectral_convergence=0`、`f0_delta_cents=0` を確認した

実行例:

```bash
research/.venv/bin/python research/scripts/compare_waveforms.py \
  --generated research/data/raw/reference/sample.wav \
  --reference research/data/raw/reference/sample.wav \
  --label a \
  --output-csv research/data/processed/analysis/waveform-comparison-selftest.csv \
  --output-json research/data/processed/analysis/waveform-comparison-selftest.json \
  --plot research/data/processed/analysis/plots/waveform-comparison-selftest.png
```

### フェーズ 2：ノイズ・子音比較

目的:

`し` / `す`、息成分、摩擦音の比較を可能にする。

作業:

- `mode=noise` を追加する
- `utau_analyze_noise_components.py` の指標を再利用する
- 3〜12 kHz の比較を重視した PNG を追加する

完了条件:

- 生成した `し` / `す` ノイズと UTAU 参照を比較できる
- peak frequency、centroid、高域比、flatness が出る

実施結果:

- `mode=noise` で 3〜12 kHz を重視した指標を出すようにした
- `research/scripts/audio_utils.py` に `peak_frequency()` と `spectral_flatness()` を追加した
- `compare_waveforms.py` の出力 CSV に以下を追加した
  - `generated_peak_frequency_hz`
  - `reference_peak_frequency_hz`
  - `peak_frequency_delta_hz`
  - `generated_spectral_flatness`
  - `reference_spectral_flatness`
  - `spectral_flatness_delta`
  - `generated_air_band_ratio`
  - `reference_air_band_ratio`
  - `air_band_ratio_delta`
  - `generated_noise_band_ratio`
  - `reference_noise_band_ratio`
  - `noise_band_ratio_delta`
- noise モードの log spectrum プロットに 3〜8 kHz high band と 8〜12 kHz air band の補助帯を追加した
- `research/data/raw/reference/utau-samples/maoto/単独音/し.wav` 同士の自己比較で動作確認した
- 自己比較では peak frequency、spectral flatness、高域比、air band 比、noise band 比の差分が 0 になることを確認した

実行例:

```bash
research/.venv/bin/python research/scripts/compare_waveforms.py \
  --generated 'research/data/raw/reference/utau-samples/maoto/単独音/し.wav' \
  --reference 'research/data/raw/reference/utau-samples/maoto/単独音/し.wav' \
  --label shi \
  --mode noise \
  --output-csv research/data/processed/analysis/waveform-comparison-noise-selftest.csv \
  --output-json research/data/processed/analysis/waveform-comparison-noise-selftest.json \
  --plot research/data/processed/analysis/plots/waveform-comparison-noise-selftest.png
```

### フェーズ 3：一括比較と集計

目的:

複数生成結果をまとめて評価し、モデルやプリセットの比較に使えるようにする。

作業:

- `research/scripts/compare_waveform_pairs.py` を追加する
- ペア CSV を入力にする
- ラベル別、モデル別、プリセット別の平均・中央値を出す

完了条件:

- 5 母音の生成結果を一括比較できる
- `reference` / `utau` / `tuned` の差を集計できる

実施結果:

- `research/scripts/compare_waveform_pairs.py` を追加した
- ペア CSV を入力し、複数の生成/参照 WAV ペアをまとめて比較できるようにした
- 出力は詳細 CSV と、`label` / `mode` / `model` / `preset` 単位の集計 CSV に分けた
- `--plots` を指定した場合は、各ペアの比較 PNG も生成できる
- `research/data/processed/analysis/waveform-comparison-pairs-selftest.csv` を追加し、母音自己比較と `し` ノイズ自己比較の 2 件で動作確認した
- 自己比較 2 件では、主要な差分指標が 0、相関が 1 になることを確認した

実行例:

```bash
research/.venv/bin/python research/scripts/compare_waveform_pairs.py \
  --pairs research/data/processed/analysis/waveform-comparison-pairs-selftest.csv \
  --output-csv research/data/processed/analysis/waveform-comparison-batch-selftest.csv \
  --summary-csv research/data/processed/analysis/waveform-comparison-batch-summary-selftest.csv
```

### フェーズ 4：遷移比較

目的:

母音切り替え、`し/す + 母音`、VCV 的な遷移を比較する。

作業:

- フレームごとの log spectrum 差を計算する
- 簡易 DTW を実装する
- onset、RMS 立ち上がり、母音安定到達時間を出す

完了条件:

- 遷移が速すぎる、遅すぎる、ノイズが母音から浮いている、などの判断材料が出る

実施結果:

- `research/scripts/audio_utils.py` にフレーム単位の log spectrum 列を作る `frame_log_spectra()` を追加した
- フレームごとの log spectrum 差を平均する `mean_frame_log_spectral_distance()` を追加した
- 簡易 DTW 距離を出す `dtw_distance()` を追加した
- RMS エンベロープと 10% onset / 90% stable 到達時間を出す `rms_envelope()`、`rms_rise_times()` を追加した
- `compare_waveforms.py` の出力 CSV に以下を追加した
  - `frame_log_spectral_distance_db`
  - `dtw_log_spectral_distance_db`
  - `generated_onset_sec`
  - `reference_onset_sec`
  - `onset_delta_ms`
  - `generated_stable_sec`
  - `reference_stable_sec`
  - `stable_delta_ms`
  - `generated_rms_rise_sec`
  - `reference_rms_rise_sec`
  - `rms_rise_delta_ms`
- `compare_waveform_pairs.py` の集計対象にも遷移指標を追加した
- `research/data/raw/reference/sample.wav` 同士を `mode=transition` で自己比較し、フレームスペクトル距離、DTW 距離、onset/rise 差分が 0 になることを確認した
- `research/data/processed/analysis/waveform-comparison-pairs-selftest.csv` に transition 自己比較を追加し、一括比較でも集計できることを確認した

実行例:

```bash
research/.venv/bin/python research/scripts/compare_waveforms.py \
  --generated research/data/raw/reference/sample.wav \
  --reference research/data/raw/reference/sample.wav \
  --label a \
  --mode transition \
  --output-csv research/data/processed/analysis/waveform-comparison-transition-selftest.csv \
  --output-json research/data/processed/analysis/waveform-comparison-transition-selftest.json \
  --plot research/data/processed/analysis/plots/waveform-comparison-transition-selftest.png
```

## 初期実装で採用する指標セット

最初の `compare_waveforms.py` は、以下に絞る。

- `duration_delta_ms`
- `rms_delta_db`
- `alignment_lag_ms`
- `waveform_rmse`
- `normalized_cross_correlation`
- `log_spectral_distance_db`
- `spectral_convergence`
- `spectral_centroid_delta_hz`
- `spectral_slope_delta_db_per_khz`
- `f0_delta_cents`
- `f1_delta_hz`
- `f2_delta_hz`
- `f3_delta_hz`
- `formant_mae_hz`

この範囲なら、現行依存関係だけで実装でき、母音プリセット調整の判断にすぐ使える。

## 注意点

### 参照音声は正解ではない

UTAU 音源は録音条件、声質、F0、話者差を含む。生成音を UTAU に完全一致させるのではなく、母音らしさや声質差を観察するための参照として扱う。

### ピッチ差を別扱いする

生成音の F0 と参照音声の F0 が違うと、スペクトル差が大きく見える。比較時には、まず F0 を揃えた生成音を使うか、F0 差を評価結果から分離して読む。

### 位相差に過敏な指標を主評価にしない

`waveform_rmse` や `snr_db` は同じ合成アルゴリズムの回帰テストには向くが、自然音声参照との類似度には向きにくい。主評価は log spectrum、フォルマント、声質指標に置く。

## 直近の推奨作業

次に実装するなら、以下の順で進める。

1. `research/scripts/audio_utils.py` を追加する
2. `research/scripts/compare_waveforms.py` を追加する
3. 母音 1 ペアで CSV/JSON/PNG 出力を確認する
4. 5 母音の生成 WAV が用意できた段階で一括比較へ拡張する

この比較ツールを先に用意しておけば、今後のスペクトル表示、母音プリセット調整、子音イベント化、声道モデル調整の結果を数値で追跡できる。
