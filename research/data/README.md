# Research Data Layout

研究用の音声データは、このディレクトリ配下で管理します。

初期段階では、次の原則で運用します。

- 元データは `raw/` に置く
- 前処理済みデータや解析用派生物は `processed/` に置く
- 由来の異なる音声はサブディレクトリを分ける
- データの出典、収録条件、ライセンスは必ずメモとして残す

## ディレクトリ構成

### `raw/reference/`

公開コーパス、公開デモ音声、比較用の参照音声を置きます。

### `raw/recorded/`

このプロジェクトのために手元で録音した音声を置きます。

### `raw/generated/`

外部ツールや別実験で生成した未加工音声を置きます。

### `processed/analysis/`

リサンプリング済み音声、切り出し済み音声、解析前処理済み音声を置きます。

### `processed/exports/`

解析結果と合わせて保存したい出力音声や比較用書き出しを置きます。

## 命名方針

ファイル名は、最低限次の情報が分かる形を推奨します。

`source-label_subject_token_condition_sr.wav`

例:

- `reference_hillenbrand_female01_a_16k.wav`
- `recorded_self_a_neutral_48k.wav`
- `generated_webproto_vowel-a_test01_48k.wav`

## メタデータ

各ファイルの由来を追えるように、`sample-index.csv` を更新して管理します。

最低限記録したい項目:

- relative_path
- category
- source
- subject
- token
- sample_rate
- channels
- license
- notes

## Git に入れるもの

初期段階では、軽量なサンプルや、自前で用意した小さな音声のみを Git 管理対象にします。

大きなデータや配布条件の曖昧なデータは、原則として直接コミットせず、取得方法だけを記録します。

## 初期サンプルについて

現時点では、ノートブックの動作確認用として `raw/reference/sample.wav` を置いています。
これは比較研究用の正式な参照音声ではなく、解析パイプラインを最小構成で回すための自前生成サンプルです。今後、適切な公開音声や自前収録音声で置き換えることを前提とします。
