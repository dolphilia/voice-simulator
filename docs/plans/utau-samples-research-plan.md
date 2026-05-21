# 計画書：UTAU 音声サンプルを用いた母音・声質分析

## 概要

この文書は、`research/data/raw/reference/utau-samples/` に配置した UTAU 音源サンプルを、Voice Simulator の物理ベース音声合成へ活用するための研究計画である。

目的は、UTAU 音源をそのまま合成素材として使うことではない。実音声から母音フォルマント、話者差、声質差、遷移成分、子音・息成分を観察し、Web プロトタイプや将来の声道モデルに使えるパラメータ、検証データ、比較基準を作ることである。

初期段階では、現在の Web プロトタイプが持つ `frequency`、`tractScale`、`gain`、`vowel`、3 バンドフォルマントフィルタに直結する分析を優先する。

## 背景

現在の Web プロトタイプは、以下の単純な構成で母音らしい音を生成している。

```text
OscillatorNode のこぎり波 -> 3 バンドフォルマントフィルタ -> GainNode -> 出力
```

この構成は軽量で扱いやすいが、母音プリセットや `tractScale` はまだ実測データに強く結びついていない。UTAU 音源の単独音・連続音を分析することで、次の改善に使える。

1. 日本語 5 母音の F1/F2/F3 プリセットを実測参照ベースにする
2. 話者差を `tractScale` や話者プリセットとして扱う
3. 声色差を `brightness`、`breathiness`、`tension` などの将来パラメータへ整理する
4. 連続音から母音遷移や子音から母音への時間変化を観察する
5. 子音・息成分を、将来のノイズ源や乱流モデルの参照にする

## 対象データ

対象データは、Git 管理外のローカル参照データとして配置する。

```text
research/data/raw/reference/utau-samples/
```

このディレクトリの構造と注意点は、以下の README にまとめる。

```text
research/data/raw/reference/utau-samples/README.md
```

主な特徴は次の通り。

- WAV: 5,704 files
- FRQ: 5,680 files
- `oto.ini`: 40 files
- 総容量: 約 1.4 GB
- 代表的な WAV 形式: Microsoft PCM / 16 bit / mono / 44,100 Hz
- UTAU 系テキストファイルは CP932 として読む必要があるものが多い

## 研究の主成果物

この研究では、実装に渡せる形の成果物を優先する。

### 1. 母音フォルマント表

UTAU 単独音から、日本語 5 母音 `/a/ /i/ /u/ /e/ /o/` の F1/F2/F3、帯域幅、相対ゲインを推定する。

成果物:

```text
research/data/processed/analysis/utau-vowel-formants.csv
research/data/processed/analysis/utau-vowel-formants-summary.csv
research/data/processed/exports/vowel-presets.generated.json
```

Web 反映先:

```text
web/prototypes/vowel-formant-prototype/src/audio/vowels.ts
```

### 2. 話者差・声道スケール表

同一母音のフォルマント位置を音源間で比較し、話者ごとの全体的なフォルマント倍率を推定する。

成果物:

```text
research/data/processed/analysis/utau-speaker-scale.csv
research/data/processed/exports/speaker-presets.generated.json
```

Web 反映候補:

- `tractScale` の初期値・プリセット化
- 話者プリセット UI
- 母音プリセットと話者スケールの分離

### 3. 声質指標表

同じ音源内の `light`、`vivid`、`Dark`、`Boyish`、`Breathy` などの派生サブセットを比較し、声色差を定量化する。

候補指標:

- スペクトル重心
- スペクトル傾斜
- H1-H2 または低次倍音の相対差
- 高域エネルギー比
- 非周期成分または息成分の比率

成果物:

```text
research/data/processed/analysis/utau-voice-quality.csv
```

Web 反映候補:

- `brightness`
- `breathiness`
- `tension`
- 声門波形・ノイズ源の追加方針

### 4. 連続音遷移データ

`連続音/` と `oto.ini` を使い、母音遷移や子音から母音への遷移区間を切り出す。

成果物:

```text
research/data/processed/analysis/utau-vowel-transitions.csv
research/data/processed/exports/vowel-transition-curves.generated.json
```

Web 反映候補:

- 母音切り替え時の補間カーブ
- 動的フォルマント遷移
- 子音イベント導入時のタイミングモデル

### 5. 子音・息成分の参照スペクトル

`子音/`、`息/`、`おまけ/`、摩擦音を含む単独音を分析し、ノイズ源や乱流成分の基準を作る。

成果物:

```text
research/data/processed/analysis/utau-noise-components.csv
```

Web 反映候補:

- 摩擦音用ノイズ源
- 息成分ミックス
- 子音ごとの簡易フィルタプリセット

## 実施フェーズ

### フェーズ 0：データ台帳と読み込み基盤

目的:

UTAU サンプルを安全に走査し、分析対象を CSV として管理できる状態を作る。

作るもの:

```text
research/scripts/utau_index.py
research/data/processed/analysis/utau-sample-index.csv
```

`utau-sample-index.csv` の列:

| 列 | 内容 |
| --- | --- |
| `speaker_dir` | トップディレクトリ名 |
| `subset` | `単独音`、`連続音`、`単独音-vivid` など |
| `filename` | WAV ファイル名 |
| `path` | リポジトリルートからの相対パス |
| `label` | ファイル名または `oto.ini` 由来の発音ラベル |
| `kind` | `vowel`, `cv`, `vcv`, `breath`, `dialogue`, `unknown` |
| `sample_rate` | サンプルレート |
| `channels` | チャンネル数 |
| `duration_sec` | 長さ |
| `has_frq` | 対応する `.frq` の有無 |
| `has_oto` | 同階層 `oto.ini` の有無 |

完了条件:

- 全 WAV を列挙できる
- CP932 の `oto.ini` を読める
- `.DS_Store`、`.bak`、キャッシュ類を分析対象から除外できる
- 音声データ本体を Git に含めない

実施結果:

- `research/scripts/utau_index.py` を追加した
- `research/data/processed/analysis/utau-sample-index.csv` を生成した
- 5,704 件の WAV を台帳化した
- 全件が 44,100 Hz / mono として読めることを確認した
- WAV 読み込みエラーは 0 件だった
- 分類結果は `vowel` 90 件、`cv` 2,763 件、`vcv` 2,588 件、`breath` 198 件、`dialogue` 11 件、`unknown` 54 件だった

### フェーズ 1：単独音 5 母音の初期分析

目的:

各音源の `単独音` 系サブセットから `/a/ /i/ /u/ /e/ /o/` を抽出し、F0 と F1/F2/F3 を推定する。

作るもの:

```text
research/scripts/utau_analyze_vowels.py
research/data/processed/analysis/utau-vowel-formants.csv
research/notebooks/utau-vowel-formant-analysis.ipynb
```

分析対象:

- `あ.wav`
- `い.wav`
- `う.wav`
- `え.wav`
- `お.wav`

優先サブセット:

1. `単独音`
2. `単独音A`
3. `単独音B`
4. `単独音_PLANE`

推定方法:

1. WAV を mono float に正規化して読み込む
2. 無音区間を除外する
3. 中央の安定区間を切り出す
4. F0 を推定する
5. LPC またはピーク検出で F1/F2/F3 候補を出す
6. 母音ごとの妥当範囲で外れ値を除外する
7. 結果を CSV に保存する

`utau-vowel-formants.csv` の列:

| 列 | 内容 |
| --- | --- |
| `speaker_dir` | トップディレクトリ名 |
| `character_name` | `character.txt` 由来の音源名 |
| `subset` | サブセット名 |
| `vowel` | `a`, `i`, `u`, `e`, `o` |
| `path` | WAV の相対パス |
| `f0_hz` | 基本周波数 |
| `f1_hz` | 第 1 フォルマント |
| `f2_hz` | 第 2 フォルマント |
| `f3_hz` | 第 3 フォルマント |
| `b1_hz` | F1 帯域幅 |
| `b2_hz` | F2 帯域幅 |
| `b3_hz` | F3 帯域幅 |
| `rms_db` | 音量指標 |
| `confidence` | 推定信頼度 |
| `notes` | 外れ値・手動確認メモ |

完了条件:

- 5 母音すべてについて複数話者の F1/F2/F3 が取れる
- 明らかな誤推定を可視化で確認できる
- 現行 `vowels.ts` と比較できるグラフがある

実施結果:

- `research/scripts/utau_analyze_vowels.py` を追加した
- `research/data/processed/analysis/utau-vowel-formants.csv` を生成した
- `research/data/processed/analysis/utau-vowel-formants-summary.csv` を生成した
- `research/data/processed/analysis/utau-vowel-formant-scatter.png` を生成した
- `research/notebooks/utau-vowel-formant-analysis.ipynb` を追加した
- 90 件の母音サンプルを分析した。内訳は各母音 18 件ずつ
- 推定信頼度は `1.000` が 45 件、`0.667` が 42 件、`0.333` が 3 件だった
- 欠損は F1 が 28 件、F2 が 13 件、F3 が 7 件だった。自動 LPC 推定の限界を示すため、欠損は空欄と `notes` に残している
- 母音別中央値は `/a/`: F1=961.666 Hz, F2=1396.077 Hz, F3=2378.362 Hz、`/i/`: F1=376.027 Hz, F2=2830.672 Hz, F3=3724.615 Hz、`/u/`: F1=498.038 Hz, F2=1326.122 Hz, F3=1764.349 Hz、`/e/`: F1=664.538 Hz, F2=2354.347 Hz, F3=3269.838 Hz、`/o/`: F1=717.165 Hz, F2=1041.377 Hz, F3=3171.097 Hz だった

### フェーズ 2：Web プロトタイプ向け母音プリセット生成

目的:

フェーズ 1 の分析結果から、Web プロトタイプに渡せる母音プリセットを生成する。

作るもの:

```text
research/scripts/export_vowel_presets.py
research/data/processed/exports/vowel-presets.generated.json
research/data/processed/exports/vowel-presets.generated.ts
research/data/processed/analysis/utau-vowel-presets-comparison.csv
```

生成方針:

- 各母音について F1/F2/F3 の中央値を基本値とする
- 外れ値は除外する
- ゲインは各フォルマント近傍の相対ピークから推定する
- 帯域幅は推定値が不安定な場合、母音ごとの固定初期値を使う
- Web 反映前に手動レビューを前提とする

TypeScript 出力例:

```ts
export const generatedVowels = {
  a: {
    label: "/a/",
    formants: [
      { frequency: 730, bandwidth: 80, gain: 1.0 },
      { frequency: 1150, bandwidth: 90, gain: 0.7 },
      { frequency: 2500, bandwidth: 140, gain: 0.35 },
    ],
  },
};
```

完了条件:

- 現行 `src/audio/vowels.ts` と差分比較できる
- 生成プリセットで Web プロトタイプを試聴できる
- 既存プリセットより母音識別性が落ちない

実施結果:

- `research/scripts/export_vowel_presets.py` を追加した
- `research/data/processed/exports/vowel-presets.generated.json` を生成した
- `research/data/processed/exports/vowel-presets.generated.ts` を生成した
- `research/data/processed/analysis/utau-vowel-presets-comparison.csv` を生成した
- `confidence >= 0.667` の分析行を使い、母音・フォルマントごとに中央値で周波数、帯域幅、相対ゲインを出した
- 現行 `web/prototypes/vowel-formant-prototype/src/audio/vowels.ts` との差分を CSV 化した
- 生成値は研究出力として扱い、Web 側の既定プリセットはまだ置き換えていない。特に相対ゲインは LPC 推定や高い F0 の影響を受けるため、試聴と手動調整が必要である

### フェーズ 3：話者スケールと `tractScale` の推定

目的:

話者ごとのフォルマント全体の高低を推定し、`tractScale` の実測参照値を作る。

作るもの:

```text
research/scripts/utau_estimate_speaker_scale.py
research/data/processed/analysis/utau-speaker-scale.csv
research/notebooks/utau-speaker-scale-analysis.ipynb
```

推定方法:

1. フェーズ 1 の全母音フォルマントを使う
2. 全体基準の母音フォルマント中央値を作る
3. 各話者について、同じ母音・同じフォルマントの倍率を計算する
4. ロバスト平均または中央値で話者スケールを推定する
5. `tractScale` へ変換する

注意:

現在の `tractScale` はフォルマント周波数を直接スケールする近似である。物理的な声道長とは逆方向の関係になる可能性があるため、UI 表示名と内部値の意味を整理する。

完了条件:

- 話者ごとの推定スケールが表で確認できる
- 極端な値を外れ値として扱える
- Web 側で話者プリセットの試作ができる

実施結果:

- `research/scripts/utau_estimate_speaker_scale.py` を追加した
- `research/data/processed/analysis/utau-speaker-scale.csv` を生成した
- `research/data/processed/exports/speaker-presets.generated.json` を生成した
- `research/notebooks/utau-speaker-scale-analysis.ipynb` を追加した
- 基本単独音系サブセット `単独音`、`単独音A`、`単独音B`、`単独音_PLANE` を対象にした
- `confidence >= 0.667` の 57 行を基準値と話者スケール推定に使った
- 12 件の話者・音源プリセット候補を生成した
- `tractScale` 候補の範囲は 0.925170 から 1.061705 だった
- `平野文::単独音` は有効フォルマント数が少ないため `few_valid_formants` として注記した
- Web プロトタイプでは `formant.frequency / tractScale` として効くため、実測フォルマント倍率の逆数を `tractScale` として出力した

### フェーズ 4：声質差の分析

目的:

同一話者または近い音源の派生サブセットから、声質差に対応する音響特徴を抽出する。

対象例:

- `単独音-light`
- `単独音-vivid`
- `単独音-Dark`
- `単独音-Boyish`
- `連続音-Breathy`
- `単独音soft`

作るもの:

```text
research/scripts/utau_analyze_voice_quality.py
research/data/processed/analysis/utau-voice-quality.csv
research/data/processed/analysis/utau-voice-quality-summary.csv
research/notebooks/utau-voice-quality-analysis.ipynb
```

分析指標:

- スペクトル重心
- 低域・中域・高域のエネルギー比
- 倍音列の減衰傾き
- 周期成分と非周期成分の比率
- F0 揺れ
- RMS の安定性

完了条件:

- `vivid` が高域寄り、`Dark` が低域寄り、`Breathy` が非周期成分多め、のような傾向を確認できる
- Web プロトタイプへ追加する声質パラメータ候補を 2 つ以内に絞れる

実施結果:

- `research/scripts/utau_analyze_voice_quality.py` を追加した
- `research/data/processed/analysis/utau-voice-quality.csv` を生成した
- `research/data/processed/analysis/utau-voice-quality-summary.csv` を生成した
- `research/notebooks/utau-voice-quality-analysis.ipynb` を追加した
- 90 件の母音サンプルを対象に、スペクトル重心、高域比、低域・中域比、スペクトル傾斜、倍音減衰傾き、非周期エネルギー近似比、F0/RMS 安定性を出した
- `maoto::単独音vivid` はスペクトル重心 1770.870059 Hz、高域比 0.236568、非周期エネルギー比 0.127054 で、派生サブセットの中でも明確に高域・非周期寄りだった
- `金田朋子::単独音-Dark` はスペクトル重心 513.619180 Hz で低域寄りだった
- `真田アサミ::単独音-Boyish` は通常単独音よりスペクトル重心と高域比が高く、明るさ・鋭さ方向の差として扱える可能性がある
- `水原薫::単独音-vivid` は名前ほど高域寄りに出なかったため、声質名を横断的な正解ラベルとして扱わず、音源内比較と実測指標を優先する
- Web プロトタイプに追加する声質パラメータ候補は、まず `brightness` と `breathiness` の 2 つに絞る。`brightness` はスペクトル重心・高域比・スペクトル傾斜、`breathiness` は非周期エネルギー比・RMS/F0 安定性を手がかりにする

### フェーズ 5：連続音と `oto.ini` による遷移分析

目的:

静的な母音だけでなく、実音声の時間変化を観察し、母音補間や子音から母音への遷移モデルに使う。

作るもの:

```text
research/scripts/utau_parse_oto.py
research/scripts/utau_analyze_transitions.py
research/data/processed/analysis/utau-oto-index.csv
research/data/processed/analysis/utau-vowel-transitions.csv
research/data/processed/exports/vowel-transition-curves.generated.json
research/notebooks/utau-transition-analysis.ipynb
```

`oto.ini` から使う情報:

- WAV ファイル名
- エイリアス
- オフセット
- 子音部
- ブランク
- 先行発声
- オーバーラップ

分析内容:

- VCV サンプルの母音区間切り出し
- 子音から母音への F1/F2/F3 時系列
- 母音間遷移の時間幅
- 遷移カーブの平均形状

完了条件:

- 母音切り替え時の補間時間の目安を出せる
- Web 側の母音切り替えが瞬時変更から滑らかな変化へ改善できる

実施結果:

- `research/scripts/utau_parse_oto.py` を追加した
- `research/scripts/utau_analyze_transitions.py` を追加した
- `research/data/processed/analysis/utau-oto-index.csv` を生成した
- `research/data/processed/analysis/utau-vowel-transitions.csv` を生成した
- `research/data/processed/exports/vowel-transition-curves.generated.json` を生成した
- `research/notebooks/utau-transition-analysis.ipynb` を追加した
- 40 個の `oto.ini` から 17,298 行の原音設定を UTF-8 CSV 化した
- `a め` のような VCV エイリアスから 7,241 件の母音遷移行を抽出した
- 25 種類の母音ペア `a/e/i/o/u -> a/e/i/o/u` をすべて確認できた
- `transition_ms = preutterance_ms - overlap_ms` として算出した遷移時間の中央値は 166.667 ms、平均は 175.511 ms だった
- Web プロトタイプ向けの推奨デフォルト母音補間時間は 166.667 ms とした
- 今回の出力は `oto.ini` のタイミングに基づく補間カーブであり、実測 F1/F2/F3 時系列の直接推定は次段階の詳細分析に回す

### フェーズ 6：子音・息・ノイズ源の予備分析

目的:

将来の子音、乱流、息漏れモデルに向けた参照スペクトルを作る。

対象例:

- `さ`, `し`, `す`, `せ`, `そ`
- `は`, `ひ`, `ふ`, `へ`, `ほ`
- `子音/`
- `息/`
- `おまけ/`

作るもの:

```text
research/scripts/utau_analyze_noise_components.py
research/data/processed/analysis/utau-noise-components.csv
research/data/processed/analysis/utau-noise-components-summary.csv
research/data/processed/analysis/utau-noise-components-by-label.csv
research/data/processed/exports/noise-component-presets.generated.json
research/notebooks/utau-noise-components-analysis.ipynb
```

分析内容:

- 摩擦音区間のスペクトル包絡
- 高域エネルギー比
- 無声音と有声音の違い
- 息成分の帯域分布
- 母音フィルタへ混ぜるノイズ量の目安

完了条件:

- 最初に実装すべき子音カテゴリを決められる
- ノイズ源の帯域制限フィルタ候補を作れる

実施結果:

- `research/scripts/utau_analyze_noise_components.py` を追加した
- `research/data/processed/analysis/utau-noise-components.csv` を生成した
- `research/data/processed/analysis/utau-noise-components-summary.csv` を生成した
- `research/data/processed/analysis/utau-noise-components-by-label.csv` を生成した
- `research/data/processed/exports/noise-component-presets.generated.json` を生成した
- `research/notebooks/utau-noise-components-analysis.ipynb` を追加した
- `さ/し/す/せ/そ`、`は/ひ/ふ/へ/ほ`、`息`、`子音`、`おまけ` 系の 237 件を分析した
- カテゴリ別内訳は `sibilant` 90 件、`h_fricative` 90 件、`bonus` 38 件、`breath` 11 件、`consonant` 8 件だった
- `し` と `す` は高域ノイズとして明確で、`し` はスペクトル重心 5631.452628 Hz、高域比 0.773016、`す` はスペクトル重心 5642.463190 Hz、高域比 0.380391、air band 比 0.246339 だった
- `さ/せ/そ` は先頭区間にも母音成分が混ざりやすく、最初の子音モデルとしては `し/す` より扱いにくい
- `息` 系はスペクトル重心 3403.985293 Hz、高域比 0.446745、スペクトル平坦度 0.163012 で、breathiness 用 highpass ノイズの参照に使える
- 最初に実装すべき子音カテゴリは `し/す` 系の sibilant ノイズとし、候補フィルタは 6 kHz 前後の bandpass ノイズとする
- 息成分は 3.4 kHz 前後の highpass ノイズを薄く混ぜる方向を候補にする

## 推奨ディレクトリ構成

研究用のコードと成果物は、次の構成に寄せる。

```text
research/
├── data/
│   ├── raw/
│   │   └── reference/
│   │       └── utau-samples/              # Git 管理外。README.md のみ追跡
│   └── processed/
│       ├── analysis/                      # CSV、集計結果
│       └── exports/                       # Web 反映用 JSON/TS
├── notebooks/
│   ├── utau-vowel-formant-analysis.ipynb
│   ├── utau-speaker-scale-analysis.ipynb
│   ├── utau-voice-quality-analysis.ipynb
│   └── utau-noise-components-analysis.ipynb
└── scripts/
    ├── utau_index.py
    ├── utau_parse_oto.py
    ├── utau_analyze_vowels.py
    ├── utau_estimate_speaker_scale.py
    ├── utau_analyze_voice_quality.py
    ├── utau_analyze_transitions.py
    ├── utau_analyze_noise_components.py
    └── export_vowel_presets.py
```

## 実装上の注意

### 文字コード

UTAU の `readme.txt`、`character.txt`、`oto.ini` は CP932 として読む。

Python では次のように扱う。

```python
text = path.read_text(encoding="cp932", errors="replace")
```

### ファイル名

日本語ファイル名には結合濁点を含むものがある。macOS では Unicode 正規化の違いが出やすいため、文字列で決め打ちせず、候補ファイルを列挙してから比較する。

### 権利条件

音源ごとの `readme.txt` には利用条件がある。研究用の解析結果は扱いやすいが、元音声の再配布、生成音声の公開、商用利用には個別確認が必要である。

### `.frq` の扱い

`.frq` は UTAU 側の周波数情報として参照価値がある。ただし形式や信頼性にばらつきがある可能性があるため、初期フェーズでは補助情報として扱い、WAV からの F0 推定結果と比較する。

### 分析精度

自動推定だけでフォルマントを確定しない。特に高い F0 の音声、息成分が多い音声、短いサンプルでは誤推定が起こりやすい。初期成果物には `confidence` と `notes` を入れ、後で手動確認できる形にする。

## Web プロトタイプへの反映手順

1. `utau-vowel-formants-summary.csv` で母音別の中央値と外れ値を確認する
2. `vowel-presets.generated.ts` を生成する
3. 既存の `src/audio/vowels.ts` と比較する
4. Web プロトタイプで試聴する
5. 母音識別性、音量差、耳障りな共鳴を確認する
6. 必要なら帯域幅とゲインを手動調整する
7. 調整理由を `docs/plans/` または `docs/note/` に残す

初回の反映では、完全な自動生成を目指さない。分析結果を根拠として使い、人間が試聴して最終調整する。

## 優先順位

最短でプロジェクトに効く順序は次の通り。

1. フェーズ 0：データ台帳
2. フェーズ 1：単独音 5 母音の初期分析
3. フェーズ 2：Web 向け母音プリセット生成
4. フェーズ 3：話者スケール推定
5. フェーズ 4：声質差の分析
6. フェーズ 5：連続音遷移分析
7. フェーズ 6：子音・息・ノイズ源の予備分析

最初の実装単位としては、フェーズ 0 からフェーズ 2 までを 1 つのまとまりにするのがよい。ここまで進むと、現在の Web プロトタイプの音に直接反映できる。

## 最初のマイルストーン

### M1：母音フォルマント分析の最小成果

作るもの:

- `research/scripts/utau_index.py`
- `research/scripts/utau_analyze_vowels.py`
- `research/data/processed/analysis/utau-sample-index.csv`
- `research/data/processed/analysis/utau-vowel-formants.csv`
- `research/notebooks/utau-vowel-formant-analysis.ipynb`

到達条件:

- 少なくとも 8 音源以上から 5 母音を抽出できる
- F1/F2/F3 の散布図を確認できる
- 現行 `vowels.ts` の値との差分を表にできる

### M2：Web 反映用プリセット

作るもの:

- `research/scripts/export_vowel_presets.py`
- `research/data/processed/exports/vowel-presets.generated.ts`

到達条件:

- 生成した母音プリセットで Web プロトタイプを動かせる
- `/a/ /i/ /u/ /e/ /o/` の違いが試聴で確認できる
- 既存プリセットとの差分理由を説明できる

### M3：話者プリセットの試作

作るもの:

- `research/scripts/utau_estimate_speaker_scale.py`
- `research/data/processed/analysis/utau-speaker-scale.csv`
- `research/data/processed/exports/speaker-presets.generated.json`

到達条件:

- 話者ごとの `tractScale` 候補を出せる
- Web UI に話者プリセットを追加する仕様を決められる

## この計画でまだ決めないこと

以下は、フェーズ 1 から 3 の結果を見てから決める。

- LPC とスペクトルピーク検出のどちらを主推定にするか
- `.frq` を主データとして使うか、補助データに留めるか
- 声質パラメータを何個 Web UI に出すか
- 連続音遷移を現在のフォルマントフィルタ方式で扱うか、波動管モデル側で扱うか
- 研究成果をどの時点で Web プロトタイプへコミットするか

## 備考

この計画は、UTAU 音源を素材として利用する計画ではなく、実音声から合成モデルのパラメータと検証基準を得るための研究計画である。元音声データの権利条件を尊重し、リポジトリには分析コード、集計値、設計判断のみを残す。
