# 調査メモ: UTAU 音声サンプル分析の総括

## 概要

このメモは、`research/data/raw/reference/utau-samples/` に配置した UTAU 音源サンプルを用いた分析フェーズ 0〜6 の総括である。

今回の分析の目的は、UTAU 音源を合成素材として直接使うことではなく、Voice Simulator の物理ベース音声合成に使える参照値、検証データ、実装判断を得ることだった。具体的には、母音フォルマント、話者差、声質差、母音遷移タイミング、子音・息成分のノイズ特性を抽出した。

分析対象の元データ本体は Git 管理外であり、構造メモのみ `research/data/raw/reference/utau-samples/README.md` に残している。

## 生成した主な成果物

### 台帳

- `research/scripts/utau_index.py`
- `research/data/processed/analysis/utau-sample-index.csv`

UTAU サンプル全体を走査し、5,704 件の WAV を台帳化した。全件が 44,100 Hz / mono として読めた。

分類結果:

- `cv`: 2,763 件
- `vcv`: 2,588 件
- `breath`: 198 件
- `vowel`: 90 件
- `unknown`: 54 件
- `dialogue`: 11 件

### 母音フォルマント分析

- `research/scripts/utau_analyze_vowels.py`
- `research/data/processed/analysis/utau-vowel-formants.csv`
- `research/data/processed/analysis/utau-vowel-formants-summary.csv`
- `research/data/processed/analysis/utau-vowel-formant-scatter.png`
- `research/notebooks/utau-vowel-formant-analysis.ipynb`

90 件の母音サンプルを分析した。各母音は 18 件ずつである。

母音別フォルマント中央値:

| 母音 | F1 Hz | F2 Hz | F3 Hz |
| --- | ---: | ---: | ---: |
| `/a/` | 961.666 | 1396.077 | 2378.362 |
| `/i/` | 376.027 | 2830.672 | 3724.615 |
| `/u/` | 498.038 | 1326.122 | 1764.349 |
| `/e/` | 664.538 | 2354.347 | 3269.838 |
| `/o/` | 717.165 | 1041.377 | 3171.097 |

自動 LPC 推定なので欠損は残る。欠損は F1 が 28 件、F2 が 13 件、F3 が 7 件だった。結果は研究参照値として有用だが、Web 側の既定値へ反映する前に試聴と手動調整が必要である。

### Web 向け母音プリセット生成

- `research/scripts/export_vowel_presets.py`
- `research/data/processed/exports/vowel-presets.generated.json`
- `research/data/processed/exports/vowel-presets.generated.ts`
- `research/data/processed/analysis/utau-vowel-presets-comparison.csv`

`confidence >= 0.667` の分析行を使い、母音・フォルマントごとの中央値から Web 向けプリセット候補を生成した。

現行 `web/prototypes/vowel-formant-prototype/src/audio/vowels.ts` との差分は大きい。特に相対ゲインは、高い F0 や LPC 推定の影響を受けやすい。生成値はそのまま差し替えるものではなく、試聴用・比較用の候補として扱う。

### 話者スケール分析

- `research/scripts/utau_estimate_speaker_scale.py`
- `research/data/processed/analysis/utau-speaker-scale.csv`
- `research/data/processed/exports/speaker-presets.generated.json`
- `research/notebooks/utau-speaker-scale-analysis.ipynb`

基本単独音系サブセットを対象に、12 件の話者・音源プリセット候補を生成した。

Web プロトタイプでは `formant.frequency / tractScale` として効くため、実測フォルマント倍率の逆数を `tractScale` として出力した。

結果:

- `tractScale` 候補の範囲は 0.925170 から 1.061705
- 多くの話者は 1.0 近傍に収まった
- `平野文::単独音` は有効フォルマント数が少ないため `few_valid_formants` として注記した

話者差は初期 UI の大きなパラメータとしては比較的穏やかで、まずは任意スライダーよりも「話者プリセットの微調整値」として扱うのがよい。

### 声質差分析

- `research/scripts/utau_analyze_voice_quality.py`
- `research/data/processed/analysis/utau-voice-quality.csv`
- `research/data/processed/analysis/utau-voice-quality-summary.csv`
- `research/notebooks/utau-voice-quality-analysis.ipynb`

90 件の母音サンプルに対して、スペクトル重心、高域比、低域・中域比、スペクトル傾斜、倍音減衰傾き、非周期エネルギー近似比、F0/RMS 安定性を計算した。

主な傾向:

- `maoto::単独音vivid` は高域・非周期寄り
- `金田朋子::単独音-Dark` は低域寄り
- `真田アサミ::単独音-Boyish` は通常単独音より明るさ・鋭さ方向に寄る可能性がある
- `水原薫::単独音-vivid` は名前ほど高域寄りに出なかった

声質名は音源横断の正解ラベルとしては扱いにくい。音源内比較と実測指標を優先するべきである。

Web プロトタイプに追加する声質パラメータ候補は、まず次の 2 つに絞る。

- `brightness`: スペクトル重心、高域比、スペクトル傾斜で制御
- `breathiness`: 非周期エネルギー比、RMS/F0 安定性、息成分ノイズで制御

### 母音遷移分析

- `research/scripts/utau_parse_oto.py`
- `research/scripts/utau_analyze_transitions.py`
- `research/data/processed/analysis/utau-oto-index.csv`
- `research/data/processed/analysis/utau-vowel-transitions.csv`
- `research/data/processed/exports/vowel-transition-curves.generated.json`
- `research/notebooks/utau-transition-analysis.ipynb`

40 個の `oto.ini` から 17,298 行の原音設定を UTF-8 CSV 化した。そのうち、`a め` のような VCV エイリアスから 7,241 件の母音遷移を抽出した。

結果:

- 25 種類の母音ペア `a/e/i/o/u -> a/e/i/o/u` をすべて確認
- `transition_ms = preutterance_ms - overlap_ms`
- 遷移時間の中央値は 166.667 ms
- 平均は 175.511 ms

Web プロトタイプ向けの推奨デフォルト母音補間時間は 166.667 ms とした。

今回の出力は `oto.ini` のタイミングに基づく補間カーブであり、実測 F1/F2/F3 時系列の直接推定ではない。実測フォルマント軌跡は後続の詳細分析に回す。

### 子音・息・ノイズ成分分析

- `research/scripts/utau_analyze_noise_components.py`
- `research/data/processed/analysis/utau-noise-components.csv`
- `research/data/processed/analysis/utau-noise-components-summary.csv`
- `research/data/processed/analysis/utau-noise-components-by-label.csv`
- `research/data/processed/exports/noise-component-presets.generated.json`
- `research/notebooks/utau-noise-components-analysis.ipynb`

`さ/し/す/せ/そ`、`は/ひ/ふ/へ/ほ`、`息`、`子音`、`おまけ` 系の 237 件を分析した。

カテゴリ別内訳:

- `sibilant`: 90 件
- `h_fricative`: 90 件
- `bonus`: 38 件
- `breath`: 11 件
- `consonant`: 8 件

主な結果:

- `し`: スペクトル重心 5631.452628 Hz、高域比 0.773016
- `す`: スペクトル重心 5642.463190 Hz、高域比 0.380391、air band 比 0.246339
- `息`: スペクトル重心 3403.985293 Hz、高域比 0.446745、スペクトル平坦度 0.163012

最初に実装すべき子音カテゴリは `し/す` 系の sibilant ノイズである。候補フィルタは 6 kHz 前後の bandpass ノイズがよい。息成分は 3.4 kHz 前後の highpass ノイズを薄く混ぜる方向が妥当である。

## 実装への示唆

### 1. 母音プリセットは「自動生成値 + 試聴調整」で扱う

UTAU から得たフォルマント値は、現在の手入力プリセットより実データに近い。ただし、LPC の欠損や高い F0 の影響があるため、そのまま置き換えるのは危険である。

次の進め方がよい。

1. 生成済み `vowel-presets.generated.ts` を試験的に Web 側へ接続する
2. 現行プリセットと切り替えて試聴できる UI を用意する
3. 周波数は生成値を参照し、ゲインと帯域幅は耳で調整する
4. 調整後の値だけを `src/audio/vowels.ts` に反映する

### 2. `tractScale` は話者プリセットとして扱う

話者ごとの `tractScale` 候補は 0.925〜1.062 程度で、極端な差ではなかった。UI 上では大きな音色変化を担わせるより、話者プリセットの微調整値として使う方が自然である。

### 3. 声質パラメータはまず 2 つでよい

声質差から見て、最初に追加する価値が高いパラメータは次の 2 つである。

- `brightness`
- `breathiness`

`brightness` はフォルマントフィルタのゲイン配分、高域補正、または励振源のスペクトル傾斜で制御できる。`breathiness` はノイズ源のミックスと highpass フィルタで導入できる。

### 4. 母音遷移は 166 ms 前後の補間から始める

現在の Web プロトタイプは母音切り替えがパラメータ即時変更に近い。UTAU の VCV 設定から見ると、母音遷移は 166 ms 前後で滑らかに補間するのが初期値として妥当である。

最初はフォルマント周波数、帯域幅、ゲインを同じ補間時間で変化させればよい。複雑な音素別遷移カーブは後で足せる。

### 5. 子音は `し/す` 系から始める

`さ/せ/そ` は先頭区間にも母音成分が混ざりやすく、最初のノイズモデルとしては扱いづらい。一方で `し/す` は高域ノイズとして明確に分離できる。

最初の子音実装は、以下のように進めるのがよい。

- ホワイトノイズまたはピンクノイズを生成する
- 6 kHz 前後の bandpass をかける
- 短いエンベロープで母音前に混ぜる
- `し` と `す` を最初の対象にする

### 6. 息成分は breathiness として先に入れられる

息成分は 3.4 kHz 前後の highpass ノイズとして扱いやすい。子音より先に、声質パラメータ `breathiness` として導入できる可能性が高い。

## 制約と注意点

### 自動推定の限界

フォルマント推定は完全ではない。高 F0、息成分、短いサンプル、音源ごとの録音差により、LPC のピークが欠損したり入れ替わったりする。

そのため、今回の CSV は「正解表」ではなく「実装判断の根拠」として扱う。

### 声質名は絶対ラベルではない

`vivid` や `Dark` などの名前は、音源内では傾向を持つことがあるが、音源横断では必ずしも同じ音響特徴を意味しない。声質パラメータは名前ではなく実測指標から設計する。

### `oto.ini` は音響軌跡ではなくタイミング情報

VCV 分析から得たのは、主に遷移タイミングである。実際の F1/F2/F3 がどう動くかは別途、短時間 LPC やスペクトログラム追跡で見る必要がある。

### 元音声の権利条件

UTAU 音源の元データは Git 管理外であり、音源ごとの `readme.txt` に利用条件がある。公開資料や生成音声への利用、商用利用、再配布には個別確認が必要である。

## 次にやるべきこと

今回の分析から、次の実装順が現実的である。

1. Web プロトタイプに母音プリセット切り替え機能を追加する
2. 生成済み UTAU 母音プリセットを試聴できるようにする
3. 母音パラメータを 166 ms 前後で補間する
4. `brightness` と `breathiness` を最小実装する
5. 6 kHz 前後の bandpass ノイズで `し/す` 系子音を試作する
6. 試聴結果をもとに `vowels.ts` と研究 CSV の関係を整理する

この順序なら、現行の 3 バンドフォルマントフィルタ構成を大きく崩さず、分析結果を段階的に Web プロトタイプへ反映できる。

## 備考

このメモは、UTAU 音源分析フェーズ 0〜6 の完了時点での総括である。今後 Web 実装に反映した結果、試聴評価、追加分析に応じて更新する。
