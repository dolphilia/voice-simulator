# 256フレームの機器要求で時刻が飛ぶ処理時間の範囲

試験用Firefoxでは、歌唱ノードの構築と事前描画が同じ出力要求に入り、cubebのコールバック内が5.049 msまたは5.283 msだった試行でも、次の予定サンプル時刻が256フレーム飛んだ。同じcubeb版を使う単独プログラムで、既知PCMを返すデータコールバックの待機だけを変え、この観測を切り分ける。[Firefoxの実測](worklet-live-song-deferred-split-preparation.md#名目予算の直前で発生した時刻の飛び)・[比較条件の事前登録](../cases/cubeb-output-callback-deadline-sweep.json)

## 入力から機器要求まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AudioEngine.build()` がレートをHzで設定したContextにWorkletを作る。`ChimeraProcessor.process()` は出力チャンネルの長さをフレーム数として `engine_render()` に渡す。ABIはRustの `Engine::render()` が埋めたfloat32 PCMのアドレスを返す。`Engine::render()` は累積出力フレーム `pos` の128フレーム境界で拍を処理し、その後に声と `pos` を進める。`output_does_not_depend_on_the_host_block_size()` は固定したフレームで操作を適用し、異なるホストブロック長でもPCMがビット一致することを検査する。今回の対照は、この後段に当たるcubebをFirefoxと同じ `840f69c1b3f95accd582555e10abcef8ee67514b` に固定する。[AudioEngine.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[processor.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[WASMのABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[エンジンのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[Geckoとcubebの版](cubeb-output-callback-probe.md#読解)

固定版cubebの `AudioUnitContext::stream_init()` は出力を初期化し、コンテキスト内の最初のストリームで `LatencyController` が選んだ要求長を `set_buffer_size_sync()` で適用する。`audiounit_output_callback()` には機器から要求された `output_frames` と `AudioTimeStamp` が渡る。`CubebResampler::fill()` がデータコールバックにつながり、返された有効長で `frames_queued` を進める。欠けたフレームはドレイン時に0で埋め、必要に応じてミキサーを通す。計測パッチは通常のデータ分岐の末尾で左右のPCM、時刻、実際のフレーム数を記録する。等レートで必要な入力フレーム数を求める固定版の `test_minimum_resampling_input_frames_equal_input_output_rate()` は、出力要求と同じ長さを返すことを検証する。[固定版のバックエンド](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-coreaudio-rs/src/backend/mod.rs)・[リサンプラー](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-coreaudio-rs/src/backend/resampler.rs)・[固定版のテスト](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-coreaudio-rs/src/backend/tests/api.rs)・[計測パッチ](../tools/chimera-cubeb-output-snapshot.patch)

対照の `render()` は対象の65番目だけ `Instant` の経過時間が設定µsに達するまでスピンし、それから累積PCM位置 `frames` を要求長だけ進める。出力フレーム番号 `i` に対し、左を `(((421i + 173) mod 65,521) − 32,760) / 8,388,608`、右をその負値にする。最後に `callbacks` を1増やす。機器の `mSampleTime` をPCM位置の計算に使わないので、予定時刻の飛びと返却PCMの欠落を区別できる。実験の待機はデータコールバック内、実測の処理時間はcubebの入口からPCMコピー後の計時点までを含む。[Rustの試験プログラム](../tools/chimera-cubeb-output-probe.rs)

## 測定と判定

48 kHz・前後8要求で、256フレームの名目周期 `1000 × 256 ÷ 48,000 = 5.333… ms` と、実際の処理を比較する。予定サンプル差は `次の mSampleTime − 今回の mSampleTime`、機器時刻の飛びはその差から要求長を引いた値。`mHostTime` は `mach_timebase_info` でmsに換算し、予定サンプル差と照合する。コールバックの実開始、返却前、次の実開始も同じホスト時計で別に記録する。生PCMは左右を独立計算とビット比較する。時間に関する予測と採取の妥当性は実行記録の別欄に残す。[計測入口と照合](../tools/measure_cubeb_output_callback.py)

## 実測

macOS 15.6.1（24G90）arm64のMacBook Pro内蔵スピーカーを既定出力として、Rust 1.94.1で作った試験プログラムを使用した。バイナリのSHA-256 `cbe303957a4f5e81e1c125f88bd6ff695ed5cc66c9eef42158892b9c9e041f94` は、前回の採取上限の回帰確認と一致した。研究ワークスペースと `/private/tmp` からそれぞれ40試行を実施し、各600判定に合格した。[前回のバイナリ](../runs/cubeb-output-callback-20261121-block-limit-regression/manifest.json)・[初回](../runs/cubeb-output-deadline-sweep-20261121-a/summary.json)・[再実行](../runs/cubeb-output-deadline-sweep-20261121-repeat/summary.json)

| 設定した待機 | 対象回の実測時間 | 直後に256フレーム飛んだ回数 |
| --- | --- | ---: |
| 0、4.600、4.800、4.950 ms | 約0〜4.953 ms | 0 / 32 |
| 5.050 ms | 5.0507〜5.0528 ms | 5 / 8 |
| 5.175、5.280 ms | 5.176〜5.284 ms | 16 / 16 |
| 5.333、5.500、8.400 ms | 5.334〜8.403 ms | 24 / 24 |

最短の飛びは5.051833 msで、飛びのなかった最長は5.051500 msだった。実測の2群が重ならなかった差は約0.33 µsで、5.05 ms近傍の8試行には飛びの有無が両方あった。名目周期からの差は最短の飛びで約0.2815 ms。飛びのある45試行では、対象回の次の予定間隔が1周期分の5.333 msから2周期分の10.667 msになった。飛びが現れた最初の観測点は対象回からその次への機器時刻で、前後の他の要求に飛びはなかった。Firefoxで見つかった名目予算内の飛びを、固定版cubebと既知PCMでも再現できた。

全80試行の各4,352フレームで左右PCMが独立計算とビット一致した。別にPCMの整数値を剰余逆数でフレーム連番に戻し、サンプル時刻差と生ホスト時刻差を照合した。既存の無待機・8.4 msの4試行は56判定を通過し、固定版の等レート試験1件も合格した。3実行の入力20件と出力342件のサイズとSHA-256を確認し、採取データ約22.70 MBをRTL9210B-CGに保存した。[従来条件の回帰](../runs/cubeb-output-callback-20261121-deadline-regression/manifest.json)・[等レート試験ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-deadline-sweep-test-20261121.log)

観測した範囲は48 kHz・256フレームの組み込み出力に対応する。次の対照ではcubeb版とPCMを揃えて512フレームを要求し、実際の機器要求長を確認する。名目周期と飛び始める時間との差が256フレームの場合と近いか、周期とともに伸びるかを比較する。機器の実出力はプロセスタップを校正してから照合する。[タップの校正状況](worklet-live-song-paired-output.md)

## 再現

研究ワークスペースから実行する。固定版cubebの試験用バイナリの作り方は既知PCMの対照を参照する。`<実行ID>` には未使用の名前を指定する。[試験用バイナリの作り方](cubeb-output-callback-probe.md#再現)

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python \
  tools/measure_cubeb_output_callback.py <実行ID> \
  "$build/target/release/examples/chimera-output-probe" \
  --case cases/cubeb-output-callback-deadline-sweep.json
```
