# 計画書：UTAU 分析後の次期実装計画

## 概要

この文書は、UTAU 音声サンプル分析、Web プロトタイプへの初期反映、波形比較ツール、反復生成実験を踏まえ、Voice Simulator を物理ベース音声合成プロジェクトとして前進させるための改訂版実装計画である。

以前の計画では、第1 Web プロトタイプへスペクトル表示を追加することを最初の実装候補としていた。しかし、その後に研究側で生成波形とリファレンス波形を比較する基盤が整い、さらに `/a/` を対象にした 10 回反復の生成・比較実験まで進んだ。

そのため、今後は次の順序を基本方針とする。

1. 研究側で数値評価・反復調整を行う
2. その結果を Web プロトタイプの `tuned` プリセットや声質制御へ反映する
3. Web 側では試聴・観察・操作性を高める
4. 調整済みの目標値を声道チューブ/波動管モデルへ橋渡しする

目標は、単に母音らしい音を出すことではない。生成音、音響指標、声道形状、音素イベントを同じ研究フローの中で比較できるようにし、分析、生成、評価、実装の往復を短くすることである。

## 現状調査

### UTAU 分析から得られている成果

`research/data/raw/reference/utau-samples/` の分析により、以下の参照値が得られている。

- UTAU WAV 5,704 件の台帳化
- 日本語 5 母音の F1/F2/F3 中央値
- Web 向け母音プリセット候補
- 話者別 `tractScale` 候補
- `brightness` / `breathiness` の初期設計に使える声質指標
- VCV 由来の母音遷移時間 166.667 ms
- `し` / `す` 系 sibilant ノイズの 6 kHz 前後の帯域特性
- 息成分の 3.4 kHz 前後 highpass ノイズ方針

主な関連文書:

- `docs/note/utau-samples-analysis-summary.md`
- `docs/plans/utau-samples-research-plan.md`

### Web プロトタイプへ反映済みの内容

`web/prototypes/vowel-formant-prototype/` には、UTAU 分析値を使った第1段の実装が入っている。

- `reference` / `utau` の母音プリセット切り替え
- UTAU 由来の 5 母音フォルマント候補
- 話者プリセットによる `tractScale` 変更
- 166 ms の母音フォルマント補間
- `brightness` と `breathiness`
- `し` / `す` の短い bandpass ノイズトリガー

ただし、この段階では「音を試せる」状態に留まっている。生成音が実際にどのスペクトルになっているか、UTAU 参照値とどれだけ近いか、子音イベントが母音へどう接続されているかを観察する機能はまだ弱い。

### 波形比較ツールの進捗

`docs/plans/waveform-comparison-tool-plan.md` に沿って、研究側の比較基盤が作成された。

追加済みの主なスクリプト:

- `research/scripts/audio_utils.py`
- `research/scripts/compare_waveforms.py`
- `research/scripts/compare_waveform_pairs.py`
- `research/scripts/iterate_vowel_match.py`

比較できる主な指標:

- `waveform_rmse`
- `normalized_cross_correlation`
- `log_spectral_distance_db`
- `spectral_convergence`
- `spectral_centroid_delta_hz`
- `spectral_slope_delta_db_per_khz`
- `f0_delta_cents`
- `formant_mae_hz`
- `peak_frequency_delta_hz`
- `spectral_flatness_delta`
- `air_band_ratio_delta`
- `dtw_log_spectral_distance_db`
- `rms_rise_delta_ms`

これにより、試聴だけでなく、生成音とリファレンス音の差分を CSV/JSON/PNG として追跡できるようになった。

### 反復生成実験の結果

UTAU 参照音声 `maoto/単独音/あ.wav` を対象に、10 回の生成・比較・調整実験を実施した。

初期実験:

- 複合スコア: `88.669039` から `54.075995`
- 改善率: `39.01%`
- `log_spectral_distance_db`: `73.054717` から `43.242226`
- `formant_mae_hz`: `396.535406` から `204.349761`
- `f0_delta_cents`: `-13.578376` から `0.000000`

改善版生成:

- 参照安定区間のスペクトル包絡をゆるく反映する `spectral_match` を追加
- 複合スコア: `88.669039` から `48.588397`
- 改善率: `45.20%`
- `spectral_convergence`: `1.102948` から `0.436571`
- `formant_mae_hz`: `396.535406` から `44.510082`
- `normalized_cross_correlation`: `0.249916` から `0.519529`

主な成果物:

- `research/data/processed/analysis/vowel-match-a-iterations.csv`
- `research/data/processed/analysis/vowel-match-a-improved-iterations.csv`
- `research/data/processed/analysis/vowel-match-a-comparisons.csv`
- `research/data/processed/analysis/vowel-match-a-improved-comparisons.csv`
- `research/data/raw/generated/vowel-match-a-improved/trial-10.wav`
- `research/data/processed/analysis/plots/vowel-match-a-improved/trial-10.png`

### 既存プロトタイプの状態

`web/prototypes/` には以下のプロトタイプが存在する。

- `vowel-formant-prototype/`: 3 バンドフォルマントフィルタの軽量試聴機
- `tube-vocal-tract/`: Kelly-Lochbaum 系の声道チューブモデル試作
- `waveguide-vocal-tract/`: 改良版波動管、LF 音源、損失モデルを目指す試作
- `acoustic-fdtd-2d/`: 2D 音響シミュレーション系の試作

次に新規プロトタイプを増やすよりも、まずは研究側の比較・最適化結果を第1プロトタイプへ反映し、その調整済み目標値を `tube-vocal-tract` / `waveguide-vocal-tract` に渡すのが現実的である。

### ドキュメント上の注意点

`web/README.md` は現在 `vowel-formant-prototype` と `acoustic-fdtd-2d` だけを列挙しており、`tube-vocal-tract` と `waveguide-vocal-tract` が反映されていない。次期作業の中で、プロトタイプ一覧と役割を更新する必要がある。

## 改訂後の方針

次期作業の中心は、次の 4 つである。

1. 研究側の比較・反復調整を正式な評価基盤にする
2. 評価で得た `tuned` 値を Web プロトタイプへ反映する
3. 子音と母音を一回押しのノイズではなく、音素イベントとして扱う
4. 第1プロトタイプの調整値を、声道チューブ/波動管モデルへ橋渡しする

リアルタイム操作は引き続き有用だが、高精度化や探索は研究側のオフライン生成を優先する。Web 側は、研究結果を触って確認するための試聴・観察台として整備する。

## 実施フェーズ

### フェーズ 0：現状整理と導線整備

目的:

既存成果物の場所と役割を明確にし、以降の実装で迷わない状態にする。

作業:

- `web/README.md` に現在存在する全プロトタイプを列挙する
- 第1プロトタイプの README に UTAU 分析モード、比較ツール、反復生成実験の説明を追加する
- `docs/note/utau-samples-analysis-summary.md` に Web 実装済み項目、比較ツール、反復実験の概要を追記する
- この計画書から以下の関連文書へ明示的に誘導する
  - `docs/plans/utau-samples-research-plan.md`
  - `docs/plans/waveform-comparison-tool-plan.md`
  - `docs/plans/tube-vocal-tract-prototype-plan.md`
  - `docs/plans/waveguide-vocal-tract-prototype-plan.md`

完了条件:

- どのプロトタイプが何を検証するものか README から判断できる
- UTAU 分析値、比較ツール、反復実験、Web 実装の関係が追える

成果物:

- `web/README.md`
- `web/prototypes/vowel-formant-prototype/README.md`
- `docs/note/utau-samples-analysis-summary.md`

### フェーズ 1：比較・反復調整結果の整理

目的:

研究側の比較ツールと反復実験を、今後の母音・声質調整の正式な入力にする。

作業:

- `vowel-match-a-improved-iterations.csv` から最終パラメータと改善指標を整理する
- `/a/` 以外の `/i/ /u/ /e/ /o/` についても同じ反復実験を実施できるよう、`iterate_vowel_match.py` を母音汎用にする
- `spectral_match` をそのまま Web へ移植せず、以下の制御へ分解する方針をまとめる
  - フォルマント周波数
  - フォルマント帯域幅
  - フォルマントゲイン
  - source tilt
  - 帯域別ゲイン
- 反復実験の要約メモを作成する

完了条件:

- `/a/` について、初期値、UTAU 値、改善後値の比較表がある
- `spectral_match` の扱いが「上限確認用」か「実装候補」か明確になっている
- 反復実験の評価指標と改善率が文書化されている

成果物:

- `docs/note/vowel-matching-experiment-summary.md`
- 必要に応じて `research/scripts/iterate_vowel_match.py`
- `research/data/processed/analysis/vowel-match-a-improved-iterations.csv`

### フェーズ 2：第1プロトタイプの `tuned` プリセット反映

目的:

UTAU 由来プリセットをそのまま使うのではなく、比較ツールと反復実験で得た調整結果を Web 側へ反映する。

作業:

- `reference` / `utau` / `tuned` の 3 セット構成に拡張する
- `/a/` の `tuned` 値に、反復実験の最終候補を反映する
- `/i/ /u/ /e/ /o/` は初期状態では `utau` と同値にし、後続実験の反映先とする
- `source_tilt` や帯域別ゲインの Web 実装方法を検討する
- UI に現在の F1/F2/F3、帯域幅、ゲイン、プリセット種別を表示する

完了条件:

- 3 種類の母音プリセットセットを切り替えられる
- `/a/` の `tuned` 値が Web 側で試聴できる
- `npm run build` が通る
- 比較 CSV から Web 反映値の由来が追える

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/vowels.ts`
- `web/prototypes/vowel-formant-prototype/src/audio/engine.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/app.ts`
- `docs/note/vowel-preset-listening-notes.md`

### フェーズ 3：第1プロトタイプのスペクトル観察機能

目的:

研究側の比較結果を Web 上でも確認しやすくする。

作業:

- `VoiceEngine` に `AnalyserNode` を追加し、UI から参照できるようにする
- `ui/spectrum-view.ts` を追加するか、既存の `tube-vocal-tract` / `waveguide-vocal-tract` の `SpectrumView` を移植する
- 0〜4 kHz のスペクトル表示を追加する
- 選択中母音プリセットの F1/F2/F3 を縦線で表示する
- `reference` / `utau` / `tuned` の目標値差が画面上で比較できるようにする

完了条件:

- Start 後にスペクトルがリアルタイム表示される
- 選択中母音の F1/F2/F3 がスペクトル上に重なる
- `reference` / `utau` / `tuned` を切り替えながら視覚的に比較できる
- `npm run build` が通る
- ブラウザで Start/Stop、母音切り替え、プリセット切り替えが動作する

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/engine.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/spectrum-view.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/app.ts`
- `web/prototypes/vowel-formant-prototype/src/styles.css`

### フェーズ 4：音素イベントとしての `し/す + 母音`

目的:

現在の `し` / `す` ボタンを一回限りのノイズトリガーから、子音から母音へ接続する最小の音素イベントに拡張する。

作業:

- `triggerConsonant()` を `triggerSyllable()` または同等の API に整理する
- `shi` / `su` と後続母音を組み合わせられるようにする
- ノイズの開始、ピーク、減衰、母音ゲイン立ち上がりを 1 つの時間軸で制御する
- `oto.ini` 由来の `preutterance` / `overlap` の考え方を簡易的に反映する
- UI に `し-a`、`し-i`、`す-a`、`す-u` などのテストボタンを追加する
- `compare_waveforms.py --mode transition` で、生成した音素イベントと UTAU 参照を比較する

完了条件:

- 子音ノイズと母音が時間的につながって聞こえる
- 子音単体トリガーよりも発音イベントに近い API になっている
- 音量過多やクリックノイズがない
- `dtw_log_spectral_distance_db`、`rms_rise_delta_ms` などで遷移差を確認できる

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/engine.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/app.ts`
- 必要なら `web/prototypes/vowel-formant-prototype/src/audio/phonemes.ts`
- `research/data/processed/analysis/*transition*.csv`

### フェーズ 5：声質パラメータの整理

目的:

`brightness` と `breathiness` を仮実装から研究値に結びついた制御へ近づける。

作業:

- `utau-voice-quality-summary.csv` から代表的な明るい/暗い/息っぽい音源を整理する
- `brightness` が高次フォルマントゲインだけで十分か、励振源の `source_tilt` 側で制御すべきかを比較する
- `breathiness` の highpass ノイズ量、カットオフ、母音ゲイン補正量を比較ツールで評価しながら調整する
- 声質プリセット候補を `neutral`、`bright`、`dark`、`breathy` 程度にまとめる

完了条件:

- 声質パラメータの効果が母音差と独立して確認できる
- `brightness` / `breathiness` / `source_tilt` の推奨範囲が文書化されている
- 声質プリセットを UI で切り替えられる
- 声質差が比較 CSV で追跡できる

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/engine.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/app.ts`
- `docs/note/voice-quality-control-notes.md`

### フェーズ 6：第1プロトタイプから声道モデルへの橋渡し

目的:

フォルマントフィルタの知見を、声道形状・波動管モデルへ渡せる形にする。

作業:

- 第1プロトタイプの `reference` / `utau` / `tuned` F1/F2/F3 を、声道モデル側の目標フォルマントとして整理する
- `tube-vocal-tract` と `waveguide-vocal-tract` の母音プリセットが現在どのフォルマントを目指しているかを確認する
- 既存の `SpectrumView` とフォルマント表示の重複を整理する
- 声道断面積プリセットの調整メモを作成する
- `tuned` フォルマント値と声道断面積プリセットが一致しない場合、どちらを優先するかを明記する

完了条件:

- 第1プロトタイプの母音目標値と、第2/第3プロトタイプの母音目標値が比較できる
- どの値を採用するか、または併記するかの判断が文書化されている
- 声道モデル側で生成した WAV も比較ツールで評価できる

成果物:

- `docs/note/formant-targets-for-vocal-tract-models.md`
- 必要に応じて `web/prototypes/tube-vocal-tract/src/audio/vowel-presets.ts`
- 必要に応じて `web/prototypes/waveguide-vocal-tract/src/audio/vowel-presets.ts`

### フェーズ 7：生成物と評価結果の管理方針

目的:

反復実験で増える WAV、PNG、CSV を整理し、Git 管理の範囲を明確にする。

作業:

- 生成 WAV、比較 PNG、詳細 CSV、要約 CSV の保存方針を決める
- Git 管理するものとしないものを明確にする
- `.gitignore` の対象を必要に応じて見直す
- 研究成果として残すべき要約 CSV とメモを選別する

推奨方針:

- スクリプトは Git 管理する
- 要約 CSV と重要な最終比較結果は Git 管理候補にする
- 大量の生成 WAV と比較 PNG は原則 Git 管理外にする
- 再生成可能な中間出力は必要時のみ保持する

完了条件:

- 生成物の置き場所と管理方針が文書化されている
- 不要に大きな音声・画像ファイルが Git に混入しない

成果物:

- `.gitignore`
- `docs/note/research-artifact-management.md`

## 優先順位

次に着手すべき順序は以下とする。

1. フェーズ 0: README と導線更新
2. フェーズ 1: 比較・反復調整結果の整理
3. フェーズ 2: 第1プロトタイプの `tuned` プリセット反映
4. フェーズ 3: Web スペクトル観察機能
5. フェーズ 4: `し/す + 母音` の音素イベント化
6. フェーズ 5: 声質パラメータ整理
7. フェーズ 6: 声道モデルへの橋渡し
8. フェーズ 7: 生成物と評価結果の管理方針

理由は、まず研究側で「何がどれだけ改善したか」を確定し、その結果を Web 側へ反映する方が、聴感だけで試行錯誤するより再現性が高いためである。

## 実装上の判断基準

- 第1プロトタイプは軽量な試聴・観察台として保つ
- 高精度な探索や比較は研究側の Python スクリプトで行う
- 音響コア、可視化、UI、研究データ由来のプリセットを分離する
- UTAU 分析値は正解ではなく、候補値・比較基準として扱う
- `spectral_match` は参照にどこまで近づけられるかを見る補正であり、Web 実装へは直接移植せず、物理的または制御的に解釈できるパラメータへ分解する
- 調整値は必ずメモまたは CSV/JSON として由来を残す
- 子音は最初から全音素を狙わず、`し` / `す` の成功を先に固める
- 声道モデルへの反映は、フォルマント目標値を整理してから行う

## 数値的な完了基準

今後の調整では、以下を目安として使う。

- 初期値から `formant_mae_hz` が 30% 以上改善する
- 初期値から `log_spectral_distance_db` が改善する
- `f0_delta_cents` が 20 cents 未満に収まる
- 声質調整では `spectral_centroid_delta_hz` と `spectral_slope_delta_db_per_khz` が改善する
- 遷移調整では `dtw_log_spectral_distance_db` または `rms_rise_delta_ms` が改善する

今回の `/a/` 改善版では、`formant_mae_hz` が `396.535406` から `44.510082` まで改善しており、上記基準を満たしている。

## リスクと対策

### UTAU 由来フォルマントの誤推定

LPC 推定には欠損や入れ替わりがある。Web 側の `utau` セットはそのまま最終値にせず、`tuned` セットで比較・試聴調整する。

### `spectral_match` が参照音声に寄りすぎる

スペクトル包絡補正は有効だが、そのまま使うと物理ベース合成という目的から離れる。補正結果は、フォルマントゲイン、帯域別ゲイン、source tilt などへ分解して扱う。

### UI が研究機能で肥大化する

第1プロトタイプは研究用操作盤として割り切る。ただし、音響コアと表示部品は分離し、第2/第3プロトタイプへ移植しやすくする。

### 子音ノイズが母音から浮く

子音だけを鳴らすのではなく、母音ゲインの立ち上がり、フォルマント遷移、ノイズ減衰を同じイベント内で扱う。比較時は `mode=transition` を使う。

### 声道モデル側と第1プロトタイプ側の目標値がずれる

第1プロトタイプのフォルマント値を声道モデル側の正解にしない。文献値、UTAU 分析値、反復調整値、聴感調整値を併記し、用途別に使い分ける。

## 直近の実装候補

次に実装へ入るなら、フェーズ 0〜2 をまとめて進める。

最小タスク:

1. `web/README.md` を現状に合わせて更新する
2. 第1プロトタイプ README に UTAU 分析モード、比較ツール、反復生成実験の説明を追加する
3. `/a/` の反復実験結果を `docs/note/vowel-matching-experiment-summary.md` にまとめる
4. `vowels.ts` に `tuned` プリセットセットを追加する
5. `/a/` の `tuned` 値を Web で試聴できるようにする
6. `npm run build` とブラウザ動作確認を行う

この作業により、研究側で改善できた値を Web 側で触れる状態になり、今後の `/i/ /u/ /e/ /o/` 反復調整や子音イベント化へ進みやすくなる。
