# 初期ディレクトリ設計と最初のファイル群

## 概要

この文書は、[initial-execution-plan-safe-a.md](/Users/dolphilia/github/voice-simulator/docs/plans/initial-execution-plan-safe-a.md) をもとに、初期フェーズで採用するディレクトリ設計と、最初に置くファイル群を整理したものである。

この段階では、研究環境と Web プロトタイプを明確に分けつつ、将来の共通化を急がないことを基本方針とする。まだ共通コアや最終プロダクトの構成は確定していないため、最初から複雑な monorepo 構成にせず、小さく始められる形を優先する。

## 設計方針

初期構成では、以下を重視する。

1. 研究環境と Web プロトタイプの責務を分ける
2. 後から見て役割が分かるディレクトリ名にする
3. 将来の再編成がしやすいように、早すぎる共通化を避ける
4. 空ディレクトリではなく、最低限の説明ファイルやプレースホルダを置く

## 初期ディレクトリ構成

初期段階では、以下のような構成を採用する。

```text
.
├── README.md
├── docs/
│   ├── notes/
│   ├── plans/
│   └── spec/
├── research/
│   ├── README.md
│   ├── notebooks/
│   ├── scripts/
│   └── data/
│       ├── raw/
│       └── processed/
└── web/
    ├── README.md
    └── prototypes/
        └── vowel-formant-prototype/
            ├── README.md
            ├── public/
            └── src/
                ├── audio/
                ├── ui/
                └── lib/
```

## 各ディレクトリの役割

### `research/`

研究・解析用の作業領域である。Python ベースの実験、音声解析、比較用データの整理、ノートブックによる検証をここに置く。

### `research/notebooks/`

Jupyter notebook など、観察と実験の中心になるファイルを置く。最初の音声解析ノートブックもここに置く。

### `research/scripts/`

ノートブックから切り出した補助処理や、データ整形、共通関数などを置く。初期段階では空でもよいが、ノートブックだけに処理を閉じ込めないための逃げ道として用意する。

### `research/data/raw/`

参照音声や比較用音声など、元データを置く場所である。原則として手作業で取得した入力データを置く。

### `research/data/processed/`

前処理済みのデータや、解析の中間生成物を置く場所である。

### `web/`

 Web ベースの試作をまとめる上位ディレクトリである。

### `web/prototypes/`

個別の Web プロトタイプを置く。

### `web/prototypes/vowel-formant-prototype/`

最初の母音プロトタイプ本体を置く。

### `web/prototypes/vowel-formant-prototype/public/`

静的ファイルや、必要に応じたサンプル資産を置く。

### `web/prototypes/vowel-formant-prototype/src/audio/`

音声生成や Web Audio API 周りの処理を置く。UI と分離しておくことで、後から音声コアを差し替えやすくする。

### `web/prototypes/vowel-formant-prototype/src/ui/`

スライダー、ボタン、表示パネルなどの UI を置く。

### `web/prototypes/vowel-formant-prototype/src/lib/`

ユーティリティや、小さな共通処理を置く。初期段階では無理に多用しないが、構造を荒らさないために確保しておく。

## 最初に置くファイル群

### `research/README.md`

研究環境の役割、置くもの、置かないものを簡単に説明する。

### `research/notebooks/.gitkeep`

最初の解析ノートブックをここに置く前段階として、ディレクトリを保持する。

### `research/scripts/.gitkeep`

補助スクリプト置き場を確保する。

### `research/data/raw/.gitkeep`

参照用の未加工データ置き場を確保する。

### `research/data/processed/.gitkeep`

加工済みデータ置き場を確保する。

### `web/README.md`

Web ワークスペース全体の役割と、個別プロトタイプへの導線を説明する。

### `web/prototypes/vowel-formant-prototype/README.md`

最初の Web プロトタイプの役割、起動方法、ディレクトリの意味を簡単に説明する。

### `web/prototypes/vowel-formant-prototype/public/.gitkeep`

静的ファイル置き場を確保する。

### `web/prototypes/vowel-formant-prototype/src/audio/.gitkeep`

音声処理コード置き場を確保する。

### `web/prototypes/vowel-formant-prototype/src/ui/.gitkeep`

UI コード置き場を確保する。

### `web/prototypes/vowel-formant-prototype/src/lib/.gitkeep`

小さな共通処理置き場を確保する。

## この段階でまだ作らないもの

以下は、まだ早いと判断して初期構成には含めない。

- 共通 DSP コア用のトップレベル `packages/`
- 最終プロダクトを想定した `apps/`
- 3D 可視化専用ディレクトリ
- 自動評価やベンチマーク用の専用構成
- 研究環境と Web 環境を最初から強く結びつける共有ライブラリ

## この構成の意図

この構成は、将来の完成形を先取りするためのものではなく、初期段階の試行錯誤を混線させないためのものである。

研究環境は「観察と分析の場」、Web は「触って確かめる場」として分けておくことで、初期フェーズの目的に合った進め方をしやすくする。また、後で必要になれば `research` のスクリプトや `web` の音声処理を共通化する余地も残している。

## 次に着手するファイル候補

この構成を作った次の段階では、以下のファイルに着手するのが自然である。

1. `research/notebooks/` に最小の音声解析ノートブックを追加する
2. `web/prototypes/vowel-formant-prototype/` に最小の TypeScript ベースの雛形を追加する
3. `web/prototypes/vowel-formant-prototype/src/audio/` に最小の音出し処理を追加する
4. `web/prototypes/vowel-formant-prototype/src/ui/` に音の開始・停止とスライダーを持つ最小 UI を追加する

## 備考

この文書は、初期フェーズのディレクトリ構成を固めるための草稿であり、実際の実装開始後に必要に応じて更新する前提の計画メモである。
