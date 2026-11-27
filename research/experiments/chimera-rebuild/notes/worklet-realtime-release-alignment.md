# 96 kHzの描画量子とWASMへの呼び出し

## 固定上流と候補の描画経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor.process` は、Web Audioの出力チャンネルの長さをフレーム数として `engine_render` を呼ぶ。Rustの `Engine::render` は64出力フレームを上限に分け、その単位で `HumanVoice::render` に渡す。96 kHzでは内部レートも96 kHzで、呼気ゲートと制御の更新、各サンプルの肺圧補間、声門と気道の更新、放射と出力段の順に進む。上流は各コールバックの処理時間を `Date.now` の差で計り、観測用の送信は6回に1回。テストではホストブロックの分割を変えた出力の一致、倍率1と気道の安定範囲を確認している。[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[WASM ABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[HumanVoice](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs)・[上流のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

候補は `startRealtimeVoice` で Worklet を接続し、`LiveProcessor.process` が起動時に連続した量子を待つ。採取を始めた後は、出力フレーム数を使って既定時刻の開始と停止を採用してから、固定発声の `renderInto` が `vocal_render` を量子ごとに1回呼ぶ。PCMを出力チャンネルと確保済みの収録バッファへコピーし、量子末尾の観測値を記録する。出力のフレーム番号は採取内の相対位置で、`currentFrame` はAudioContext内の絶対位置。経過時間は ms で、今回のWorkletには `Date.now` の1 ms刻みが使われた。予算は `128 / 96000` 秒、約1.333 ms。ブラウザ計測の `process_ms` にはRustの合成に加え、呼び出しとコピー・観測の時間も入る。[実時間の入口](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts)・[起動待ち](../../../../web/prototypes/chimera-research/src/worklet-clock.ts)・[量子処理](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[固定発声のホスト](../crates/vocal-wasm/host/fixed-voice.ts)

## 呼気停止時刻の比較

既存3実行は停止後183量子、採取開始から1,000量子目の出力フレーム127,872で2・3・4 msを記録した。固定 /i/・110 Hz・肺圧7.2 cmH₂O、ゲート開始66量子目の境界（0始まり）のまま、停止を624・816・1,072へ動かした。3条件はすべて1,728量子を採取し、以前と同じ1,416量子・停止816も比較した。固定番号999と停止後183量子それぞれの前後1量子を見て、早期・後期の両方で各3回のうち2回以上という基準を事前登録した。[以前の96 kHz計測](worklet-realtime-voice-96000.md)・[呼気停止の事前登録](../cases/worklet-realtime-release-alignment.json)

ブラウザ画面の通常の開始・保存を操作した。計測ツールがノード作成時に最大発声と減衰のフレーム数を指定し、標準画面からの設定と適用後の設定を両方保存した。各PCMを候補CLIのホスト分割128・77で再描画し、固定上流の96 kHzプローブと照合した。さらに呼気ゲートの64サンプルごとの更新を独立に計算し、量子末尾の観測点に合わせた。[取得コード](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs)・[比較コード](../tools/measure_worklet_release_alignment.py)

ゲート `g` は無次元で、目標 `u` は開始時1、停止時0。64サンプルごとに `g ← u + (g − u) exp(−64 / (96000 × τ))` と更新する。時定数 `τ` は立ち上がり0.025秒、減衰0.070秒。独立計算は再帰を繰り返さず、開始境界から停止境界までの更新回数を `n`、停止以降を `m` として `(1 − exp(−64n / (96000 × 0.025))) exp(−64m / (96000 × 0.070))` を求める。このため呼気停止をずらすと同じ描画番号でもゲートが異なる。[ゲートの独立計算](../tools/measure_worklet_realtime.py#L39)・[時定数の入力](../cases/worklet-realtime-voice-96000.json)

12回、合計19,800量子で予算を超えたのは2回。従来長の1回目では停止から183量子後で3 ms、ゲート0.0301。停止を遅らせた1回目では停止73量子前の発声中で2 ms、ゲートは約1だった。どちらも採取の1,000量子目だった。事前登録した繰り返し数には届かず、帰属判定は `inconclusive`。全試行で発声中のp99は1 ms、Contextフレームは連続、WASM線形メモリの成長は0件だった。PCMは候補CLIと全フレームでビット一致し、固定上流との差は最大2.92×10⁻¹¹未満。独立計算とのゲート差は2.11×10⁻¹⁵以下。137の通常判定を通過した。[判定と各試行](../runs/worklet-release-alignment-20261121-a/summary.json)

## V8の呼び出し回数を動かす対照

V8の汎用JS→WASMラッパーは、エクスポート関数を呼ぶたびに残り回数を1減らす。既定値は1,000回。0になった呼び出しで `TierUpJSToWasmWrapper` に入り、シグネチャのラッパーがキャッシュに無ければ、そのスレッドでコンパイルして差し替える。トレースの `wasm.CompileJSToWasmWrapper` はコンパイルの実行区間で、最適化済みラッパーの登録などはこの区間の外側にもある。Rustの合成器の内部サンプル数や音響状態と独立の、JSからWASMへ入る境界の処理である。[既定値](https://chromium.googlesource.com/v8/v8/%2B/refs/heads/lkgr/src/wasm/wasm-constants.h)・[呼び出し予算の更新](https://chromium.googlesource.com/v8/v8/%2B/3a18fc10da54a9f1c961da2acdb386de29531b1f/src/builtins/js-to-wasm.tq#510)・[ランタイムのキャッシュ参照](https://chromium.googlesource.com/v8/v8/%2B/main/src/runtime/runtime-wasm.cc)・[コンパイルの計測点](https://chromium.googlesource.com/v8/v8/%2B/refs/heads/main/src/wasm/function-compiler.cc)

停止816・全1,728量子の条件を固定し、Chromiumの起動引数でV8の呼び出し予算を既定、640、1,200に設定した。各回は独立したブラウザを起動し、各条件を2回ずつ測る。起動待ちの回数と採取回数の合計をChromium側のコールバック件数と照合し、採取に対応する区間内にあるコンパイルだけを数える。ブラウザのトレースは開始時刻と長さを µs で記録する。既定で1,000量子目、変更時は640・1,200量子目の前後1量子に同期コンパイルを1回ずつ観測し、PCMと呼気停止時刻に差が出ないことを判定する。[回数変更の事前登録](../cases/worklet-wasm-wrapper-threshold.json)・[判定コード](../tools/measure_worklet_wrapper_threshold.py)・[ChromiumのWorklet計測点](https://chromium.googlesource.com/chromium/src/%2B/main/third_party/blink/renderer/modules/webaudio/audio_worklet_processor.cc)・[DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/tot/Tracing/)

6回とも、ブラウザのコールバック1,737件を起動待ち9件とPCM採取1,728件に照合できた。コンパイルは指定回数と完全一致し、トレースは全回で欠損なし。コンパイル自体の計測区間は0.274〜1.343 msだった。[トレースの集計](../runs/worklet-wasm-wrapper-threshold-20261121-a/summary.json)

| 呼び出し予算 | コンパイルした量子（1始まり） | コンパイル時間（ms） | そのコールバック全体（ms） |
| --- | ---: | ---: | ---: |
| 既定 | 1,000・1,000 | 0.652・0.546 | 1.512・0.902 |
| 640 | 640・640 | 0.274・0.466 | 0.545・1.165 |
| 1,200 | 1,200・1,200 | 1.343・0.479 | 1.673・0.816 |

コールバックが予算を超えたのは、コンパイルを含む2件と、採取末尾の1件（2.091 ms）。末尾の量子は完了通知とバッファ転送も行うため、Workletの報告とChromiumのトレースでは計測区間にも差がある。コンパイルがある2件を、従来のWorklet時計はともに1 msと記録した。640の2回目ではWorkletの記録に2 ms、トレースには1.165 msが出た。トレースの値も計測自体の負荷を含む。比較によって特定したのは同期コンパイルの位置と、今回いくつかの量子の予算を超えたこと。過去の2〜4 msすべての内訳と物理出力の欠音の有無は未測定。[試行ごとの時刻と判定](../runs/worklet-wasm-wrapper-threshold-20261121-a/summary.json)・[採取の終了処理](../../../../web/prototypes/chimera-research/src/live-processor.ts)

6回のWAVは同じSHA-256で、CLIとビット一致した。固定上流との最大差は2.92×10⁻¹¹未満。呼気ゲートの式との最大差は2.11×10⁻¹⁵、Contextフレームの飛びとWASM線形メモリ成長は0件。85判定を通過した。トレースと回数指定を外した既存の96 kHz計測も13判定を通過し、その1回ではWorklet時計上の予算超過を観測しなかった。[トレースの確定実行](../runs/worklet-wasm-wrapper-threshold-20261121-a/manifest.json)・[通常手順での回帰確認](../runs/worklet-rate-96000-20261121-wrapper-regression/summary.json)

## 再現と保存

候補のViteビルドをHeadless Chromium 156.0.8078.4、V8 15.6.75、macOS 15.6.1 arm64で実行。Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。以下は研究ワークスペースから再計測する例で、実行IDは新しく指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 \
  ../../.venv/bin/python tools/measure_worklet_release_alignment.py worklet-release-alignment-next
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  ../../.venv/bin/python tools/measure_worklet_wrapper_threshold.py worklet-wasm-wrapper-threshold-next
```

ブラウザWAV、観測JSON、Chromiumの生トレースは、計測後にgzipで可逆圧縮した。比較実行の成果の実体はRTL9210B-CG上にあり、呼気停止の12回は約11.99 MB、トレースの6回は約7.85 MB。内蔵にケース、ソースのスナップショット、マニフェストと結果要約を保存し、そこから実体を参照できる。[呼気停止の保存記録](../runs/worklet-release-alignment-20261121-a/manifest.json)・[トレースの保存記録](../runs/worklet-wasm-wrapper-threshold-20261121-a/manifest.json)

`/tmp` からの再実行でも85判定を通過し、6回のコンパイル位置とPCMのハッシュが初回と一致した。両実行の計12回で、コンパイルを含む4量子と末尾の2量子がトレース上で予算を超えた。再実行の成果は約7.86 MBで、同じ作業用ディスクに保存した。通常の96 kHz回帰確認も既存の保存手順で約114.36 MBを同ディスクに置いた。4実行の計131出力をマニフェストのサイズとSHA-256に照合した。[再実行の結果](../runs/worklet-wasm-wrapper-threshold-20261121-repeat/summary.json)・[再実行の保存記録](../runs/worklet-wasm-wrapper-threshold-20261121-repeat/manifest.json)・[通常手順の保存記録](../runs/worklet-rate-96000-20261121-wrapper-regression/manifest.json)

後続の対照では、同じWASMインスタンスのレンダー関数を0フレームで呼び、同期コンパイルを採取前へ移せることを確認した。[起動時の事前呼び出し](worklet-wasm-wrapper-warmup.md)
