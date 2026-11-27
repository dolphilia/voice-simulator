# 英語の型付き発話計画を直接報告する

## 固定上流と再実装の呼び出し順

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `src/ui/speech.ts` の `speakText` は辞書を読み、`speakPhrases` は句と体型・話速・F0を `src/wasm/engine.ts` の `planPhrases` に渡す。`crates/chimera-wasm/src/api.rs` の `planPhrases` 分岐はJSONから句列とオプションを読み、`to_json` でRustの結果を `serde_json::Value` にする。UIは調音ジェスチャーと区間、終了時刻をエンジンに渡し、句の読みと語の境界を表示する。

`crates/chimera/src/phonetics/planner.rs` の `plan_phrases` は句の開始を `t0` から進める。`plan_utterance` は元の音素に対してKlatt規則で時間を割り当て、下降二重母音なら55/45、上昇二重母音なら30/70に配分する。句の終了時刻に休止秒を足すと次の句の開始になる。再実装の `crates/vocal-core/src/phonetics/english.rs` の `plan_phrases` もこの順で `Timing` と句のF0ジェスチャーを作り、最後の句の終了に0.30秒を足してレンダー終了とする。時刻と音素長は秒、F0はHz、話速と雑音倍率は無次元。上流の `crates/chimera/tests/english.rs` は強勢・異音・句末・語境界を、`tests/words.test.ts` はブラウザ側の語区間を、`crates/chimera/tests/engine.rs` はブロック長と出力レートに関する性質を確認する。

再実装の `crates/vocal-wasm/src/planning.rs` の `prepare_english` は入力と辞書を検証し、型付き `TextPlan` と調音スコアを作る。明示的な初期ピッチ110 Hzと雑音倍率を加える際に、型付き計画全体を中間JSON値に変換していた。直前の実行ではこの工程の割り当てが初回と再計画で各527回だった。報告のバイト列と `f64` の調音スコアは別の領域に格納する。型付き計画をそのまま報告に渡し、句の平坦化、入れ子のフィールド順、音素の省略条件を従来の報告に合わせれば、発声の式とスコアに影響せず中間変換を省けると予測した。[基準の実行](../runs/worklet-live-tsp-planner-direct-report-44100-20261122-b/summary.json)・[事前登録](../cases/worklet-live-tsp-planner-direct-text-plan-44100.json)

## 実装と境界条件

`EnglishReport` が `TextPlan` を受け取り、`PlanReport` から借用して直接シリアライズする。句・区間・音素のキーを従来の辞書順で列挙し、配列は借用のイテレータから書く。句のピッチ列には外側の調音スコアと同じジェスチャーのシリアライズを使う。前回のように `Value` を渡す呼び出しも同じ `PlanReport` で扱う。[英語報告の実装と試験](../crates/vocal-wasm/src/planning/report/english.rs)・[計画ABI](../crates/vocal-wasm/src/planning.rs)

初回のコンパイルでは、雑音倍率を `f64` としたため `noise_scale` の戻り値 `Option<f64>` と一致せず、E0308が出た。`Option<f64>` を保持し、倍率ありと `null` の両方の出力を試験した。試験では質問を含む3句を使い、辞書と規則による音素、省略可能な音素の全項目、明示的な `false`、符号付きゼロ、エスケープを含む文字列と未配備音素を従来の `Value` 経由の出力に照合する。

## 実行と照合

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4。確認用07（FK64_08）、女性体型、話速1、出力44,100 Hz、内部88,200 Hz、出力128フレーム／量子。以下は研究ワークスペースから実行したコマンド。２回目の計数は `/tmp` から同じスクリプトとPythonを絶対パスで実行し、実行ID末尾を `-b` とした。

```bash
export CARGO_TARGET_DIR=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-rebuild-debug
cargo test --locked --offline -p vocal-core -p vocal-wasm --lib --quiet
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_allocation.py worklet-live-tsp-planner-direct-text-plan-44100-20261122-a --direct-text-plan
firefox=$(jq -r '.firefox_binary' runs/worklet-live-tsp-44100-20261122-a/manifest.json)
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_rate.py worklet-live-tsp-44100-direct-text-plan-regression-20261122 "$firefox"
```

| 計画ABIの工程 | 初回の基準 → 今回 | 再計画の基準 → 今回 |
| --- | ---: | ---: |
| 辞書索引 | 17 → 17 | 17 → 17 |
| 発音と句の計画 | 1,715 → 1,715 | 171 → 171 |
| 中間の英語計画値 | 527 → 0 | 527 → 0 |
| 数値スコアの格納 | 1 → 1 | 0 → 0 |
| 中間の報告値 | 0 → 0 | 0 → 0 |
| JSON出力 | 9 → 9 | 9 → 9 |
| 合計 | 2,269 → 1,742 | 724 → 197 |

2回の計数で31判定と削減予測3項目が成立し、結果要約も一致。17,014バイトの報告、数値スコア、98,790フレームのPCM、ABI・声門・声道観測、量子別の計数が基準にバイト一致し、772量子の描画中の割り当てはゼロだった。固定上流とのPCM最大絶対差は1.1641532182693481×10⁻¹⁰、閾値10⁻⁶を超えるフレームはゼロ。標準ライブラリの独立検算で全JSONキーの順序、呼気の先行0.06秒と音素長÷話速による22区間の開始・終了、最後の句の終了1.9401362000000002秒からの余韻0.30秒、六工程の和と527回差を照合した。[計数の再実行](../runs/worklet-live-tsp-planner-direct-text-plan-44100-20261122-b/summary.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-live-tsp-planner-direct-text-plan-44100.py)

通常のFirefox発話11判定、固定上流11試験、再実装47試験が通過した。FirefoxのPCMとCLI・オフラインのPCMはビット一致し、基準のブラウザ観測も一致した。Firefoxの単回計時ではp99は前後とも2 ms、2.902 msの予算超過は前回2量子、今回は7量子だった。3実行の574入力と62出力をサイズ・SHA-256で検証し、成果の実体41,670,866バイトをRTL9210B-CGに保存した。[Firefoxの比較](../runs/worklet-live-tsp-44100-direct-text-plan-regression-20261122/summary.json)・[成果一覧](../runs/worklet-live-tsp-planner-direct-text-plan-44100-20261122-b/manifest.json)
