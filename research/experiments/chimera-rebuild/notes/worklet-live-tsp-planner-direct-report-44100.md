# 英語計画の報告を直接シリアライズする

## 読解と事前登録

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` は `planPhrases` の入力を句と計画オプションに復元し、`plan_phrases()` の出力を `serde_json::Value` に変換する。句の開始・終了・休止、ジェスチャーの開始・終了と前後のランプは秒。ジェスチャーには適用する調音・声門の目標、重み、速度倍率とラベルがある。上流の `Targets::serialize()` は現在値を持つ成分のみをキー付きで出力する。APIは結果をUTF-8のJSONバイト列として状態に保持し、そのポインタと長さを呼び出し側に渡す。固定上流の英語テストは強勢・句分割・辞書外語の処理、エンジンテストはブロック幅の違いで同一出力になることを検査する。[上流の計画API](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L149)・[上流の結果バッファ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L207)・[上流の目標とジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/score.rs#L207)・[英語の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/english.rs#L26)・[エンジンの分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `PlanBuffers::store()` は、数値スコアを格納した後、計画値とジェスチャーを一つの `serde_json::Value` に組み立て、`to_string().into_bytes()` で報告を返していた。ホストの `readResult()` はJSONとF64スコアを別々に読み、エラー報告があればそのメッセージを通知する。報告の各オブジェクトのキー順は、`Value` での辞書順に由来する。直接出力に変える際は報告用の借用表現にその順序を保ち、省略可能なフィールドと調音目標の扱いを照合する。発音計画自体の変換や、戻り値の保持期間と数値スコアの構造は同じ条件で比較する。[研究版の格納](../crates/vocal-wasm/src/planning.rs#L191)・[ホストの読出し](../crates/vocal-wasm/host/planning.ts#L86)

確認用07を女性体型・同じ辞書・44.1 kHzで実行した基準では、初回3,555回、再計画2,010回のうち、中間の報告値が各1,282回、JSON文字列化が各13回だった。今回は出力領域を報告ごとに確保する条件を維持し、中間の報告値の割り当てがゼロ、JSON文字列化が13回以下になると予測する。計画JSONのバイト列、数値スコア、全PCMと内部観測を基準に照合する。[事前登録](../cases/worklet-live-tsp-planner-direct-report-44100.json)・[基準の実行](../runs/worklet-live-tsp-planner-allocation-44100-20261122-c/summary.json)

## 実装

`PlanBuffers::store()` がF64スコアを書いた後、既存の計画値とジェスチャーを借りる `PlanReport` を `serde_json::to_vec()` で直接出力する。報告全体とジェスチャーのフィールドは従来の辞書順に定義し、調音目標は報告ごとにスタック上の制御成分配列を一度だけ名前順に並べて使う。`label`、`speed`、`releaseHold` は値がある場合に出力する。出力バイト列は報告ごとに確保する。テストでは全調音成分、各フィールドの有無、負のゼロ、引用符と非ASCII文字を含むラベルを従来の `Value` 経路とバイト比較した。エラー・上限超過・空のスコアでは既存の形式とスコア長のリセットを検証した。[報告の格納](../crates/vocal-wasm/src/planning.rs#L192)・[借用する報告と比較試験](../crates/vocal-wasm/src/planning/report.rs)

## 結果

| 英語計画ABI内の工程 | 基準の初回 / 再計画 | 直接出力の初回 / 再計画 |
| --- | ---: | ---: |
| 辞書索引 | 17 / 17 | 17 / 17 |
| 発音と句の計画 | 1,715 / 171 | 1,715 / 171 |
| 計画の報告値の構築 | 527 / 527 | 527 / 527 |
| 数値スコアの格納 | 1 / 0 | 1 / 0 |
| ジェスチャー入り報告値の構築 | 1,282 / 1,282 | 0 / 0 |
| 報告のJSON文字列化 | 13 / 13 | 9 / 9 |
| 合計 | 3,555 / 2,010 | 2,269 / 724 |

初回・再計画ともに1,286回減少し、英語計画ABI全体でそれぞれ36.2%、64.0%減った。17,014バイトの報告JSONと数値スコアは基準とバイト一致した。全PCM 98,790標本、ネイティブの観測と声門・声道の時系列、量子別計数も一致し、全772量子で描画の割り当てはゼロだった。登録した31判定を研究ワークスペースと `/tmp` から再現した。標準ライブラリだけで工程差、WAVのPCM、発話開始位置と観測時刻を再検算した。[通常計数](../runs/worklet-live-tsp-planner-direct-report-44100-20261122-a/summary.json)・[再実行](../runs/worklet-live-tsp-planner-direct-report-44100-20261122-b/summary.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-live-tsp-planner-direct-report-44100.py)

通常のFirefoxの英語発話は11判定、Chromiumの歌唱 `Pop Dee` は25判定を通過した。両方でブラウザPCMと観測が保存済みの出力と一致した。固定上流とのPCMの最大絶対差は英語発話で1.16×10⁻¹⁰、歌唱で2.33×10⁻¹⁰だった。全量子のp99は英語発話・歌唱とも今回2 msで、各条件で処理予算を超えた量子は2件だった。計時は1 ms刻み、各条件1実行。標準のコア・ABIの46試験と、ブラウザ比較で実行した固定上流の英語・エンジン・歌唱・音節化の試験も通過した。4実行の836入力・86出力を照合し、実体211,700,911バイトをRTL9210B-CGに保存した。[英語の通常実行](../runs/worklet-live-tsp-44100-direct-report-regression-20261122/summary.json)・[歌唱の通常実行](../runs/worklet-live-song-direct-report-regression-20261122/summary.json)

## 実行コマンド

環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、Firefox 157.0、Chromium 156.0.8078.4。下記の `a` は研究ワークスペースから実行した。`b` は `/tmp` からPythonと計測ツールを絶対パスで指定した。再計測には新しい実行IDを使う。[再実行の条件](../runs/worklet-live-tsp-planner-direct-report-44100-20261122-b/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_allocation.py worklet-live-tsp-planner-direct-report-44100-20261122-a --direct-report
firefox=$(jq -r '.firefox_binary' runs/worklet-live-tsp-44100-20261122-a/manifest.json)
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_rate.py worklet-live-tsp-44100-direct-report-regression-20261122 "$firefox"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-direct-report-regression-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
```

次は英語計画 `TextPlan` 自体を報告値に変える工程の527回を対象にする。英語用の報告値の中間変換だけを省き、時刻表・音素・ジェスチャーを含む既存JSONと数値スコアのバイト一致を判定する。報告バッファの再利用は別の比較で扱う。[計画値を組み立てる位置](../crates/vocal-wasm/src/planning.rs#L310)・[型の定義](../crates/vocal-core/src/phonetics/english.rs)
