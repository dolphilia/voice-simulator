# Vowel Formant Prototype

このディレクトリは、初期 Web プロトタイプの作業領域です。

目的:

- Web Audio API を用いた最小の音出し
- 母音らしい連続音の生成
- 最小のインタラクティブ UI

現段階では、励振源と簡易フォルマントフィルタを組み合わせ、母音プリセットと `tractScale` による粗い声道長変化を試しています。

関連資料:

- `../../../docs/plans/web-vowel-design-first-step.md`
- `../../../docs/plans/web-vowel-listening-checklist.md`

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
