# 計画書：UTAU 分析後の次期実装計画

## 概要

この文書は、UTAU 音声サンプル分析、Web プロトタイプへの初期反映、既存の声道チューブ/波動管プロトタイプを踏まえ、Voice Simulator を物理ベース音声合成プロジェクトとして前進させるための次期作業計画である。

目標は、単に母音らしい音を出すことではない。生成音、音響指標、声道形状、音素イベントを同じ画面または同じ成果物上で比較できるようにし、研究から実装への往復を速くすることである。

## 現状調査

### 既に得られている研究成果

`research/data/raw/reference/utau-samples/` の分析により、以下の参照値が得られている。

- UTAU WAV 5,704 件の台帳化
- 日本語 5 母音の F1/F2/F3 中央値
- Web 向け母音プリセット候補
- 話者別 `tractScale` 候補
- `brightness` / `breathiness` の初期設計に使える声質指標
- VCV 由来の母音遷移時間 166.667 ms
- `し` / `す` 系 sibilant ノイズの 6 kHz 前後の帯域特性
- 息成分の 3.4 kHz 前後 highpass ノイズ方針

これらの成果は `docs/note/utau-samples-analysis-summary.md` と `docs/plans/utau-samples-research-plan.md` にまとまっている。

### 既に Web へ反映されている内容

`web/prototypes/vowel-formant-prototype/` には、UTAU 分析値を使った第1段の実装が入っている。

- `reference` / `utau` の母音プリセット切り替え
- UTAU 由来の 5 母音フォルマント候補
- 話者プリセットによる `tractScale` 変更
- 166 ms の母音フォルマント補間
- `brightness` と `breathiness`
- `し` / `す` の短い bandpass ノイズトリガー

ただし、この段階では「音を試せる」状態に留まっている。生成音が実際にどのスペクトルになっているか、UTAU 参照値とどれだけ近いか、子音イベントが母音へどう接続されているかを観察する機能が不足している。

### 既存プロトタイプの状態

`web/prototypes/` には以下のプロトタイプが存在する。

- `vowel-formant-prototype/`: 3 バンドフォルマントフィルタの軽量試聴機
- `tube-vocal-tract/`: Kelly-Lochbaum 系の声道チューブモデル試作
- `waveguide-vocal-tract/`: 改良版波動管、LF 音源、損失モデルを目指す試作
- `acoustic-fdtd-2d/`: 2D 音響シミュレーション系の試作

このため、次に新規プロトタイプを増やすよりも、まずは第1プロトタイプを観察・評価の実験台として強化し、そこで得た調整値を `tube-vocal-tract` / `waveguide-vocal-tract` に渡せる形に整理するのが現実的である。

### ドキュメント上の注意点

`web/README.md` は現在 `vowel-formant-prototype` と `acoustic-fdtd-2d` だけを列挙しており、`tube-vocal-tract` と `waveguide-vocal-tract` が反映されていない。次期作業の中で、プロトタイプ一覧と役割を更新する必要がある。

## 次期方針

次期作業の中心は、次の 3 つである。

1. 第1プロトタイプを「UTAU 分析値の試聴・観察・調整台」にする
2. 子音と母音を一回押しのノイズではなく、音素イベントとして扱う
3. 第1プロトタイプの調整値を、声道チューブ/波動管プロトタイプへ橋渡しする

リアルタイム操作は引き続き有用だが、第4プロトタイプ以降の方針として、重い処理はオフライン生成も許容する。短期的にはリアルタイム第1プロトタイプを整え、中期的にはオフライン比較・WAV 書き出しへ進む。

## 実施フェーズ

### フェーズ 0：現状整理と導線整備

目的:

既存成果物の場所と役割を明確にし、以降の実装で迷わない状態にする。

作業:

- `web/README.md` に現在存在する全プロトタイプを列挙する
- `docs/note/utau-samples-analysis-summary.md` から、Web 実装済み項目と未実装項目を分けて追記する
- 第1プロトタイプの README に UTAU 分析モードの説明を追加する
- `docs/plans/` 内の第2/第3プロトタイプ計画との関係をこの計画書から参照できるようにする

完了条件:

- どのプロトタイプが何を検証するものか、README から判断できる
- UTAU 分析値がどこで生成され、どこへ反映されたかが追える

成果物:

- `web/README.md`
- `web/prototypes/vowel-formant-prototype/README.md`
- `docs/note/utau-samples-analysis-summary.md`

### フェーズ 1：第1プロトタイプのスペクトル観察機能

目的:

試聴だけでなく、生成音のスペクトルと推定ピークを確認できるようにする。

作業:

- `VoiceEngine` に `AnalyserNode` を追加し、UI から参照できるようにする
- `ui/spectrum-view.ts` を追加するか、既存の `tube-vocal-tract` / `waveguide-vocal-tract` の `SpectrumView` を移植する
- 0〜4 kHz のスペクトル表示を追加する
- 現在選択中の母音プリセットの F1/F2/F3 を縦線で表示する
- `reference` と `utau` の差が画面上で比較できるようにする

完了条件:

- Start 後にスペクトルがリアルタイム表示される
- 選択中母音の F1/F2/F3 がスペクトル上に重なる
- `npm run build` が通る
- ブラウザで Start/Stop、母音切り替え、プリセット切り替えが動作する

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/engine.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/spectrum-view.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/app.ts`
- `web/prototypes/vowel-formant-prototype/src/styles.css`

### フェーズ 2：母音プリセット比較と試聴メモ化

目的:

UTAU 由来プリセットをそのまま使うか、手動調整するかを判断するための比較基盤を作る。

作業:

- `reference` / `utau` / `tuned` の 3 セット構成に拡張する
- `tuned` は初期状態では `utau` と同値にし、試聴後の調整先とする
- UI に現在の F1/F2/F3、帯域幅、ゲインを表示する
- 調整メモ用の Markdown を作成し、母音ごとに「聴感」「スペクトル」「採用判断」を記録する
- UTAU CSV と Web 側手入力値の関係を整理する

完了条件:

- 3 種類の母音プリセットセットを切り替えられる
- 少なくとも 5 母音すべてについて初回の比較メモがある
- 手動調整値を後から追跡できる

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/vowels.ts`
- `docs/note/vowel-preset-listening-notes.md`

### フェーズ 3：音素イベントとしての `し/す + 母音`

目的:

現在の `し` / `す` ボタンを一回限りのノイズトリガーから、子音から母音へ接続する最小の音素イベントに拡張する。

作業:

- `triggerConsonant()` を `triggerSyllable()` または同等の API に整理する
- `shi` / `su` と後続母音を組み合わせられるようにする
- ノイズの開始、ピーク、減衰、母音ゲイン立ち上がりを 1 つの時間軸で制御する
- `oto.ini` 由来の `preutterance` / `overlap` の考え方を簡易的に反映する
- UI に `し-a`、`し-i`、`す-a`、`す-u` などのテストボタンを追加する

完了条件:

- 子音ノイズと母音が時間的につながって聞こえる
- 子音単体トリガーよりも発音イベントに近い API になっている
- 音量過多やクリックノイズがない

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/engine.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/app.ts`
- 必要なら `web/prototypes/vowel-formant-prototype/src/audio/phonemes.ts`

### フェーズ 4：声質パラメータの整理

目的:

`brightness` と `breathiness` を仮実装から研究値に結びついた制御へ近づける。

作業:

- `utau-voice-quality-summary.csv` から代表的な明るい/暗い/息っぽい音源を整理する
- `brightness` が高次フォルマントゲインだけで十分か、励振源のスペクトル傾斜側で制御すべきかを比較する
- `breathiness` の highpass ノイズ量、カットオフ、母音ゲイン補正量を試聴で調整する
- 声質プリセット候補を `neutral`、`bright`、`dark`、`breathy` 程度にまとめる

完了条件:

- 声質パラメータの効果が母音差と独立して確認できる
- `brightness` / `breathiness` の推奨範囲が文書化されている
- 声質プリセットを UI で切り替えられる

成果物:

- `web/prototypes/vowel-formant-prototype/src/audio/engine.ts`
- `web/prototypes/vowel-formant-prototype/src/ui/app.ts`
- `docs/note/voice-quality-control-notes.md`

### フェーズ 5：第1プロトタイプから声道モデルへの橋渡し

目的:

フォルマントフィルタの知見を、声道形状・波動管モデルへ渡せる形にする。

作業:

- 第1プロトタイプの `reference` / `utau` / `tuned` F1/F2/F3 を、声道モデル側の目標フォルマントとして整理する
- `tube-vocal-tract` と `waveguide-vocal-tract` の母音プリセットが現在どのフォルマントを目指しているかを確認する
- 既存の `SpectrumView` とフォルマント表示の重複を整理する
- 声道断面積プリセットの調整メモを作成する

完了条件:

- 第1プロトタイプの母音目標値と、第2/第3プロトタイプの母音目標値が比較できる
- どの値を採用するか、または併記するかの判断が文書化されている

成果物:

- `docs/note/formant-targets-for-vocal-tract-models.md`
- 必要に応じて `web/prototypes/tube-vocal-tract/src/audio/vowel-presets.ts`
- 必要に応じて `web/prototypes/waveguide-vocal-tract/src/audio/vowel-presets.ts`

### フェーズ 6：オフライン生成・比較基盤の調査

目的:

リアルタイム制約を外した高精度実験へ進むため、オフライン生成の最小構成を決める。

作業:

- JavaScript の `Float32Array` 直接生成、`OfflineAudioContext`、Python 生成の 3 案を比較する
- 最初の対象を「母音 1 秒生成 + WAV 書き出し」に限定する
- 生成 WAV を `research/data/raw/generated/` または `research/data/generated/` のどちらへ置くか整理する
- 生成結果を既存の UTAU 分析スクリプトで再分析できるようにする

完了条件:

- オフライン生成の採用方針が決まっている
- 最小実装のファイル構成と入出力パスが決まっている

成果物:

- `docs/plans/offline-synthesis-comparison-plan.md`
- 必要なら `research/scripts/analyze_generated_voice.py`

## 優先順位

最初に着手すべき順序は以下とする。

1. フェーズ 0: README と導線更新
2. フェーズ 1: スペクトル観察機能
3. フェーズ 2: 母音プリセット比較
4. フェーズ 3: `し/す + 母音` の音素イベント化
5. フェーズ 4: 声質パラメータ整理
6. フェーズ 5: 声道モデルへの橋渡し
7. フェーズ 6: オフライン生成調査

理由は、まず「何が出ているかを見えるようにする」ことが、以降の調整と物理モデル化の前提になるためである。観察機能なしに声道モデルや子音モデルを増やすと、聴感だけに判断が寄りやすい。

## 実装上の判断基準

- 第1プロトタイプは軽量な試聴・観察台として保つ
- 音響コア、可視化、UI、研究データ由来のプリセットを分離する
- UTAU 分析値は正解ではなく、候補値・比較基準として扱う
- 調整値は必ずメモまたは CSV/JSON として由来を残す
- 子音は最初から全音素を狙わず、`し` / `す` の成功を先に固める
- 声道モデルへの反映は、フォルマント目標値を整理してから行う

## リスクと対策

### UTAU 由来フォルマントの誤推定

LPC 推定には欠損や入れ替わりがある。Web 側の `utau` セットはそのまま最終値にせず、`tuned` セットで試聴調整する。

### UI が研究機能で肥大化する

第1プロトタイプは研究用操作盤として割り切る。ただし、音響コアと表示部品は分離し、第2/第3プロトタイプへ移植しやすくする。

### 子音ノイズが母音から浮く

子音だけを鳴らすのではなく、母音ゲインの立ち上がり、フォルマント遷移、ノイズ減衰を同じイベント内で扱う。

### 声道モデル側と第1プロトタイプ側の目標値がずれる

第1プロトタイプのフォルマント値を声道モデル側の正解にしない。文献値、UTAU 分析値、聴感調整値を併記し、用途別に使い分ける。

## 直近の実装候補

次に実装へ入るなら、フェーズ 0 とフェーズ 1 をまとめて進める。

最小タスク:

1. `web/README.md` を現状に合わせて更新する
2. 第1プロトタイプに `AnalyserNode` を追加する
3. `SpectrumView` を追加して 0〜4 kHz のリアルタイムスペクトルを表示する
4. 選択中母音の F1/F2/F3 をスペクトルに重ねる
5. `npm run build` とブラウザ動作確認を行う

この作業により、今後の母音調整、声質調整、子音イベント化の判断材料が揃う。
