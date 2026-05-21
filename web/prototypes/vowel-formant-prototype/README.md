# Vowel Formant Prototype

このディレクトリは、初期 Web プロトタイプの作業領域です。

目的:

- Web Audio API を用いた最小の音出し
- 母音らしい連続音の生成
- 最小のインタラクティブ UI

現段階では、励振源と簡易フォルマントフィルタを組み合わせ、母音プリセットと `tractScale` による粗い声道長変化を試しています。

現在は UTAU 音声サンプル分析の結果も取り込み、以下を試せます。

- `reference` / `utau` / `tuned` の母音プリセット切り替え
- UTAU 由来の話者 `tractScale` プリセット
- 166 ms の母音遷移補間
- `brightness` / `breathiness`
- `し` / `す` の sibilant ノイズ試作
- `し-a` / `し-i` / `す-u` などの簡易音素イベント
- 0〜4 kHz のスペクトル表示と F1/F2/F3 マーカー

`tuned` プリセットは、研究側の波形比較ツールと反復生成実験の結果を Web で試聴するための調整候補です。現時点では `/a/` に `research/data/processed/analysis/vowel-match-a-improved-iterations.csv` の結果を反映し、他の母音は UTAU 値を初期値として残しています。

関連資料:

- `../../../docs/plans/web-vowel-design-first-step.md`
- `../../../docs/plans/web-vowel-listening-checklist.md`
- `../../../docs/plans/utau-informed-next-implementation-plan.md`
- `../../../docs/plans/waveform-comparison-tool-plan.md`
- `../../../docs/note/vowel-matching-experiment-summary.md`
- `../../../docs/note/vowel-preset-listening-notes.md`
- `../../../docs/note/sibilant-syllable-event-notes.md`

## 主なファイル

- `package.json`
- `tsconfig.json`
- `index.html`
- `src/main.ts`
- `src/audio/engine.ts`
- `src/audio/vowels.ts`
- `src/ui/app.ts`

## 起動方法

このディレクトリで以下を実行します。

```bash
npm install
npm run dev
```

起動後、Vite が表示するローカル URL をブラウザで開きます。

本番ビルドだけ確認したい場合:

```bash
npm run build
```

補足:

- ブラウザの音声再生は、通常はユーザー操作後に有効になります
- 最初は `Start` ボタンを押して音を開始してください
- 音が出ない場合は、ブラウザの自動再生制限や音量設定も確認してください
