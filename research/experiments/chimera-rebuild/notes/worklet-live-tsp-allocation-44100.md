# 44.1 kHzの英語発話で準備と描画の割り当てを測る

## 読解と事前登録

対象は確認用07（`FK64_08`）の女性発話で、保存済みの44.1 kHz実時間Workletケースを固定する。固定上流では `EnglishG2P` が辞書と入力から句ごとの音素を求め、`plan_phrases()` が句の時刻（秒）、休止とイントネーションから調音ジェスチャーを並べる。`Engine::schedule()` は予約時刻に声道の現在時刻と先行時間を足し、同じスコアから `Engine::render()` がブロックの境界をまたいで描画する。`output_does_not_depend_on_the_host_block_size()` はブロック長の違いで出力が変わらないことを検査する。[上流の句の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L880)・[上流の予約と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[上流の分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版ではページ側の `planEnglish()` が辞書のバイト列を `vocal_plan_dictionary()` に渡し、`vocal_english_plan_with_body()` が英語計画とスコアの数値列を用意する。スコアの各行は開始・終了などの時刻（秒）、強さと調音値を持つ。Workletの `FixedVoiceEngine` が別インスタンスの `vocal_new()`、`vocal_score_buffer()`、`vocal_start_score_prepared()` を順に呼ぶ。この発話は音高・周期・振幅の揺らぎを設定し、追加の予備描画長は0なので開始ABIの中でスコアを即時予約する。`vocal_glottal_trace_init()` と `vocal_tract_init()` が観測領域を用意する。実時間の開始待ち中は音声ABIを呼ばず、開始後は128フレーム量子を32フレーム間隔の観測に合わせて分ける。各出力フレームでは88.2 kHzの内部サンプルを2点進め、声道制御は64出力フレームごと。結果のPCMは `f32`、状態は `f64` で、声門面積はcm²、流量はcm³/s、気道内圧はdyn/cm²。[研究版の英語計画](../crates/vocal-wasm/host/planning.ts#L140)・[発話の開始と予約](../crates/vocal-wasm/src/lib.rs#L279)・[Workletの描画](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L266)

準備では割り当てが生じ、描画では歌唱で再利用を検証済みの声道領域を使うため、全772量子でゼロと予測する。ネイティブの同じ描画ABIの総件数とコアの工程別件数を採り、計測が成立したかと予測が当たったかを別々に判定する。最初の非ゼロのフレーム、全PCM、保存済みの声門と声道の観測を照合する。JavaScriptのオブジェクト生成やWASMの線形メモリ成長は、このネイティブ件数の測定範囲外にある。[事前登録](../cases/worklet-live-tsp-allocation-44100.json)・[44.1 kHzの基準](../runs/worklet-live-tsp-44100-20261122-a/summary.json)

## 実装と結果

保存済みのブラウザ入力を実行マニフェストのSHA-256で照合し、診断ビルドのネイティブテストへ渡す。辞書の展開は計数窓より前に行い、入力・辞書領域への転送、英語計画、発話ハンドルの準備、スコア開始、観測領域の確保と描画を別々に計数した。確保済みの出力配列を使い、32フレームごとの観測と768フレームごとの声道採取を含めて、通常とコア計数を有効にした条件から同じ出力を得た。計数や実行ログのシリアル化は計数窓の後で行う。[ネイティブ診断](../crates/vocal-wasm/src/tests/speech_allocation.rs)・[比較の実装](../tools/measure_worklet_live_tsp_allocation.py)

| 計数区間 | ネイティブの割り当て |
| --- | ---: |
| ページ側に相当する入力と辞書のABI領域 | 2 |
| 英語計画のABI | 3,555 |
| 描画ハンドルとスコア領域 | 3 |
| スコア開始のABI `vocal_start_score_prepared()` | 118 |
| 声門・声道の観測領域 | 2 |
| 描画と観測（772量子） | 0 |

20判定が全て通過した。出力98,790フレームのうち最後の量子は102フレーム。1,544回の制御更新と250回の接触補正後の再計算があり、全772量子で割り当てはゼロだった。保存済みのブラウザとPCM全標本、観測3,088点の17値、声門2系列の全標本、129時点の28セルの断面・圧力・流量がビット一致した。最初の非ゼロは出力フレーム2,247。固定上流との最初のビット差は出力フレーム2,593で、PCMの最大絶対差は1.16×10⁻¹⁰だった。研究ワークスペースと `/tmp` から再実行し、要約・PCM・内部観測・計画・計数がバイト一致した。標準ライブラリだけの独立検算で、WAVから取り出したPCM・各観測と量子の累積位置を再照合した。[割り当てと信号の比較](../runs/worklet-live-tsp-allocation-44100-20261122-b/summary.json)・[量子別の計数](../runs/worklet-live-tsp-allocation-44100-20261122-b/artifacts/allocations-by-quantum.csv)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-live-tsp-allocation-44100.py)

現在のFirefox 157.0でも通常の発話を再計測し、11判定を通過した。実時間・オフラインのWorkletと通常CLIで全PCMがビット一致し、保存済みの声門・声道の観測とも一致した。WASMメモリ成長は0回。`Date.now()` の計時では、今回の全量子のp99は3 msで、2.902 msの予算を超えたのは9量子。保存済みの実行はp99が2 msで予算超過は2量子だった。先頭32量子を除いたp99はどちらも2 msだった。各版1実行で、ブラウザの計時とネイティブの件数は観測点が異なる。標準のコア・ABI44試験と、固定上流のエンジン・英語11試験が通過した。3実行の521入力・54出力をサイズとSHA-256で照合し、実体41,583,296バイトをRTL9210B-CGに保存した。[Firefoxでの再計測](../runs/worklet-live-tsp-44100-allocation-regression-20261122/summary.json)・[保存済みの計時](../runs/worklet-live-tsp-44100-20261122-a/summary.json)

## 実行コマンド

環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。次を研究ワークスペースから実行した。`b` は `/tmp` からPythonと計測ツールを絶対パスで指定した。Firefoxは基準のマニフェストに記録された157.0の実行ファイルを使用した。再計測では新しい実行IDを使う。[ネイティブ実行の条件](../runs/worklet-live-tsp-allocation-44100-20261122-b/manifest.json)・[Firefox実行の条件](../runs/worklet-live-tsp-44100-allocation-regression-20261122/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_allocation.py worklet-live-tsp-allocation-44100-20261122-a
firefox=$(jq -r '.firefox_binary' runs/worklet-live-tsp-44100-20261122-a/manifest.json)
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_rate.py worklet-live-tsp-44100-allocation-regression-20261122 "$firefox"
cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
```

次は英語計画のABIで数えた3,555件を、辞書索引の構築、発音と句の計画、調音スコアと報告の生成に分ける。同じ短文と同じ辞書で工程を照合し、辞書を再利用する改善の基準を作る。[辞書索引](../crates/vocal-wasm/src/planning.rs#L278)・[英語の計画](../crates/vocal-core/src/phonetics/english.rs#L373)
