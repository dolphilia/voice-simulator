# Research Workspace

このディレクトリは、研究・解析用の作業領域です。

初期フェーズでは、主に以下を扱います。

- 音声解析ノートブック
- 参考音声の読み込みと比較
- 実験用スクリプト
- 前処理済みデータや中間生成物

現時点では、最小の音声解析ノートブックを最初の到達点とします。

最初のノートブック案:

- `notebooks/audio-analysis-starter.ipynb`

想定する依存関係は `requirements.txt` に記載します。

データ配置の方針:

- `data/raw/reference/`: 公開の参照音声
- `data/raw/recorded/`: 手元で録音した音声
- `data/raw/generated/`: 他実験や外部ツールで生成した未加工音声
- `data/processed/analysis/`: 解析前処理済み音声
- `data/processed/exports/`: 比較用の書き出し音声

各ファイルの由来は `data/sample-index.csv` で管理します。
