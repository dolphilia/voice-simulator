# Research Workspace

このディレクトリは、仮説の検証、手法の比較、参照音声の解析、パラメータ推定、評価、自動化を行うための研究・実験領域です。使用する言語、ランタイム、実行形式は限定しません。課題に応じて Python、TypeScript、Rust、Julia、その他の適切な技術を選択できます。

## 基本方針

- 再現可能な処理は、原則としてスクリプト、CLI、ライブラリ、テストなどの通常のプログラムとして実装する
- Notebook を研究の既定形式にはしない
- Notebook は、人が出力を順に観察する、パラメータを操作して試す、説明・可視化・音声を一体で提示する場合に使用する
- 初期探索で Notebook を使用した場合も、繰り返し利用する処理は必要に応じて通常のプログラムへ切り出す
- 実験では、目的、入力、手順、評価方法、結果、残された課題を記録する
- 特定の言語へ統一することより、再現性と役割の明確さを優先する

## ディレクトリ

- `experiments/`: 仮説や手法ごとの自己完結した実験。新しい実験は原則としてここに置く
- `scripts/`: 既存の解析、データ変換、比較、出力用プログラム。複数実験で再利用するものも当面ここに置く
- `notebooks/`: 人による目視、試聴、対話的操作に価値がある Notebook
- `data/raw/reference/`: 比較・測定に使用する参照音声
- `data/raw/recorded/`: このプロジェクトのために収録した音声
- `data/raw/generated/`: 実験や外部ツールで生成した未加工音声
- `data/processed/analysis/`: 解析結果、表、プロットなどの派生データ
- `data/processed/exports/`: Web プロトタイプなど他の領域へ渡すデータ

既存の `scripts/` や `notebooks/` は直ちに移動しません。新しい方針を今後の実験から適用し、既存資産は修正や再利用の機会に段階的に整理します。

`notebooks/imported-synth-lab/` は、旧 `synth-lab` から移管した出力込みの探索記録です。正式な実験や共通ツールとは区別し、再利用する処理は検証後に `experiments/`、`scripts/`、またはライブラリへ移してください。

## 実験の推奨構成

規模のある実験は、次のように実験単位でまとめます。必要のないディレクトリまで作る必要はありません。

```text
experiments/<experiment-name>/
├── README.md
├── src/
├── config/
└── results/
```

実験の `README.md` には、少なくとも次を記録します。

- 検証する仮説または問い
- 入力データと由来
- 実行方法と依存関係
- 評価指標または観察方法
- 結果の要約
- 最終実装へ採用できる部分と、実験限定の部分

正式な知見や複数実験にまたがる結論は、`docs/note/` に要約します。

2026-08-13 時点までの調査、解析、数値実験、Web プロトタイプを横断した評価は、[`docs/note/research-review-2026-08-13.md`](../docs/note/research-review-2026-08-13.md) にまとめています。

人の逐次試聴を必須にせず、非ニューラル生成と研究側のAI評価を組み合わせる2026-10-02の提案は、[再調査メモ](../docs/note/autonomous-non-neural-speech-research-2026-10-02.md)と[実装・検証計画](../docs/plans/autonomous-non-neural-speech-plan-2026-10-02.md)を参照してください。既存の凍結結果・知覚評価を保持し、別の自動検証契約で研究を進める計画です。 実装と初回3 campaignの結果は[実行報告](../docs/note/autonomous-non-neural-speech-execution-report-2026-10-02.md)に保存しています。生成の独立性は検証済みですが、品質目標は未達です。[追加検証](../docs/note/autonomous-non-neural-speech-followup-2026-10-02.md)を含む途中経過は4 campaign・2,596レンダーです。[サイクル終了結果](../docs/note/autonomous-non-neural-speech-cycle-result-2026-10-02.md)では、計画上限の6 campaign・2,730台帳レンダーを完了し、品質未達で終了しています。

2026-10-08の長期包括承認前は28件の実験終了で旧campaign上限に達し、研究を休止していました。その後、長期包括予算v1が明示承認され、累計192時間・有限の総資源上限と終了専用12時間を同じ台帳へ適用し、件数による停止を撤廃して研究を継続しています。[適用後の継続入口v3](../docs/plans/autonomous-research-continuation-prompt-2026-10-08-v3.md)と最新台帳を優先してください。科学36件終了時点でも品質未達・知覚資格なし・P5未開封です。[第6回レビュー](experiments/autonomous-research-cycle/campaigns/nas-long-horizon-review-20261008-v6/report.md)でLFと文脈韻律の不採択を封印しました。[LF比較](experiments/autonomous-research-cycle/campaigns/nas-hts-lf-comparison-20261008-v1/report.md)はE0 29/32、pitch 27/32、欠測3/720、Whisper悪化26/33群、Reazon悪化16/33群です。[固定Fujisaki文脈韻律比較](experiments/autonomous-research-cycle/campaigns/nas-fujisaki-context-comparison-20261008-v1/report.md)はE0 32/32、pitch 28/32、欠測4/696、Whisper悪化18/33群、Reazon悪化20/33群です。機構や全保存frameが整合しても内容を保護できず、両コホートの係数/phase/LPF/指令時刻/中央値/gainの救済を凍結します。[新4知覚資料の監査](experiments/autonomous-research-cycle/campaigns/nas-perceptual-new-four-20261008-v1/report.md)も適格0/4でした。[独立二方向声道伝搬](experiments/autonomous-research-cycle/campaigns/nas-waveguide-tract-mechanism-20261008-v1/report.md)は静的圧力波・一様管解析・複素応答・動的正規化エネルギー・因果前半の全条件を通過しました。人工形状の通過を母音や日本語自然さの資格へ拡張せず、公開一次の共有声道形状と有限帯域駆動へ進めます。旧全極/共有HMMなどの不採択と全凍結を保持し、[旧28件の科学終了報告](experiments/autonomous-research-cycle/cycle-closeout-report-20261008-0002.md)も履歴として残します。[2026-10-08改訂研究計画](../docs/plans/neural-assisted-non-neural-speech-plan-2026-10-08.md)の作成時状態より、最新台帳と終了結果を優先してください。[長期案対応の継続プロンプトv2](../docs/plans/autonomous-research-continuation-prompt-2026-10-08-v2.md)を使い、承認hashと旧版は保持します。

小刻みな追加承認を減らす[長期包括予算案 v1](../docs/plans/autonomous-research-long-horizon-budget-proposal-2026-10-08.md)を履歴として保存しています。文書作成時の未承認表示より、[明示承認と適用記録](experiments/autonomous-research-cycle/long-horizon-approval-20261008-v1.json)および最新台帳を優先します。累計192時間と有限の総資源で管理し、campaign件数による停止を撤廃しました。承認範囲には、測定・生成改善・知覚資格検証・条件を満たした独立P5確認へ自律的に進めることを含みます。提案文書だけでなく明示承認・管理検証を経て適用しています。指定外部保存、一時ファイルの不要時削除、まとまった成果ごとのcommit・push originは維持します。

## Notebook の選択基準

次のような場合は Notebook が適しています。

- 波形、スペクトル、スペクトログラムなどを順に目視する
- 音声をセルごとに再生して聴き比べる
- ユーザーがパラメータを変更しながら挙動を確認する
- 数式、説明、コード、結果を一続きの資料として提示する
- 一度限りの初期探索を行う

次のような処理は、通常のプログラムを優先します。

- 複数ファイルの一括解析
- パラメータスイープ
- データ変換やプリセット出力
- 自動評価、回帰テスト、ベンチマーク
- CI や他のプログラムから実行する処理
- 複数の実験で再利用する処理

## 音声データの利用方針

人間の音声はリファレンスとして扱い、測定、比較、評価、パラメータ推定、テストに利用できます。フォルマント、基本周波数、帯域幅、スペクトル傾斜、タイミングなど、生成モデルを校正するための明示的な特徴量を抽出することも許容します。

研究途中の原理検証、比較、問題の切り分けでは、既存音声の加工や一時的なサンプル利用を許容します。その場合は、音声の由来、ライセンス、加工内容、使用目的、最終方式への採用可否を記録してください。

録音断片、加工済み音声、高密度なスペクトル表現、話者埋め込みなどを、最終的な合成音の主要な供給源として使用することは対象外です。

## 生成 AI の利用方針

生成 AI は、次のような研究支援に利用できます。

- 新しいリファレンスやテストケースの作成
- 実験コード、解析、データ整理の自動化
- ラベルやメタデータの候補作成
- 比較対象や異常系の生成

生成 AI が作成したデータも、由来と生成条件を記録して、人間の録音と区別します。大量の音声で学習した生成モデルやニューラルボコーダを、最終的な音声生成器として組み込むことは対象外です。機械学習を測定や研究補助に使う場合も、その出力を可能な範囲で独立した指標や人による観察によって検証します。

## 既存の Python 環境

既存の Python 実験を実行する場合は、必要に応じて次を使用します。

```bash
pip install -r requirements.txt
```

Notebook を開く必要がある場合に限り、Jupyter を起動します。

```bash
jupyter notebook
```

各音声ファイルの由来は、既存の `data/sample-index.csv` または各実験の `README.md` で管理します。

## 大容量データの保存先

2026-10-06以降は、[承認済みの外部保存・容量追補](../docs/plans/autonomous-research-external-storage-amendment-2026-10-06.md)に従い、大容量音声・解析配列・研究用モデルを `/Volumes/CCCOMA_X64FRE_JA-JP_DV9/voice-simulator-data/` に保存します。コード、主資料、計画、台帳、メタデータとhash一覧は内蔵に残します。包括研究サイクルでは `StorageBudget` を使い、専用領域の識別と両保存先の予約・監査を共有します。メディアが利用できない場合は停止し、内蔵へ自動的に代替保存しません。既存成果の移動については、次の2026-10-08追補を適用します。

2026-10-08の既存データ移動指示は、[保存方針の追補](../docs/plans/repository-data-storage-amendment-2026-10-08.md)に記録しています。既存の大容量データも内容・論理パス・封印を保持したまま外部へ移し、元のファイルを個別のシンボリックリンクへ置き換えます。コード・文書・設定・台帳、仮想環境、展開済みライブラリ、小容量の最終モデルは内蔵に残します。従来のパスでデータを読むには指定メディアの接続が必要です。

移動一覧・処理段階・SHA-256と最終照合結果は `storage-migrations/2026-10-08-v1/` に保存します。包括サイクルの位置台帳も更新しますが、研究の回数・既存論理容量・科学的結果は引き継ぎます。今後の独立性試験は、外部専用領域全体も参照データの読取禁止対象に含めます。

## Gitで管理する研究成果

コード・文書・実験契約・入力分割・集計結果・共有モデル係数・manifest・封印hash・回答はGitの追跡候補に残します。`control/state.json` と `control/jobs.jsonl` の予算・操作記録も保持します。

音声・解析配列・研究用重み・取得アーカイブに加え、生成音声ごとの高密度なJSON、探索の全履歴、ASR個票などはデータとして保管し、Gitから除外します。対象は `.gitignore` に明示した出力ディレクトリ内に限り、`results/` やJSON全体を一括除外しません。コード、契約、集計JSON、manifest等は同じ実験の中でも残します。除外は実体の削除や科学的な封印の変更を意味しません。

`control/files.sqlite` と移動台帳の `manifest.sqlite` は、ローカルのmtime・inode・外部保存先に依存する索引としてGitから除外します。実験再開や移動検証には引き続き必要なので、実体は内蔵に残し、研究データとともに別途保管します。移動前の端末状態と一時的な権限操作の記録もローカルに残します。移動の方針・結果・hash照合結果はGitの追跡候補に残します。
