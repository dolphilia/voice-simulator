# 512フレーム要求の名目周期と時刻が飛ぶまでの余裕

48 kHz・256フレームの比較では、時刻が連続した最長の処理が5.051500 ms、飛びがあった最短の処理が5.051833 msだった。名目周期5.333 msから約0.282 ms手前に当たる。同じ機器と既知PCMで要求長だけを512フレームに変え、この差が一定時間の場合と周期に比例する場合を比較する。[256フレームの実測](cubeb-output-callback-deadline-sweep.md#実測)・[512フレームの事前登録](../cases/cubeb-output-callback-deadline-sweep-512.json)

## 描画量子と機器の要求長

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` はサンプルレートをHzで指定してAudioContextを作る。`ChimeraProcessor.process()` は受け取ったフレーム数で `engine_render()` を呼び、Rustの `Engine::render()` がWASMのfloat32出力を埋める。`Engine::render()` は累積出力位置 `pos` の128フレーム境界で拍を更新し、境界まで声を進めてから `pos` を加算する。上流の `output_does_not_depend_on_the_host_block_size()` は操作の絶対フレームを揃え、ホストの分割を変えてもPCMがビット一致することを検査する。[AudioEngine.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[processor.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[WASMのABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[エンジンのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

固定版cubeb `840f69c1b3f95accd582555e10abcef8ee67514b` の `AudioUnitContext::stream_init()` はコンテキストの `LatencyController` に要求長を渡す。最初のストリームで128〜512フレームに収め、`CoreStreamData::setup()` が出力に `set_buffer_size_sync()` で反映する。`audiounit_output_callback()` に入る時刻で実際の `output_frames` と `AudioTimeStamp` を受け、`CubebResampler::fill()` 経由でデータコールバックに出力先を渡す。有効に返ったフレーム数だけ `frames_queued` を進め、必要な混合の後で計測パッチがPCMと時刻を保存する。固定版の `test_ops_context_min_latency()` はコンテキストが返した最小レイテンシを検査し、`test_minimum_resampling_input_frames_equal_input_output_rate()` は等レート時の必要フレーム数が出力要求に等しいことを検査する。[固定版のバックエンド](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-coreaudio-rs/src/backend/mod.rs)・[リサンプラー](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-coreaudio-rs/src/backend/resampler.rs)・[インターフェース試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-coreaudio-rs/src/backend/tests/interfaces.rs)・[等レート試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-coreaudio-rs/src/backend/tests/api.rs)

既知PCMの試験プログラムは、実際に要求された長さだけ自分の累積フレーム位置を進め、整数の剰余から生成した左PCMとその逆相の右PCMを返す。0始まりで65番のデータコールバックだけ、PCMを書く前に指定µs分スピンする。機器の要求長を分析の入力にする。512フレームを指定した無待機の予備採取では、保存した24要求すべてが512フレームだった。[Rustの試験プログラム](../tools/chimera-cubeb-output-probe.rs)・[予備採取の実体](/Volumes/RTL9210B-CG/voice-simulator/scratch/cubeb-512-preflight.FoNP5q/probe.json)

## 比較の判定

保存済みの256フレームの2実行から、連続の最長と飛びの最短を求める。`T` を名目周期、`b` をその観測範囲の端とする。周期と端の差を一定とした512フレーム側の予測は `b + (T512 − T256)`、差が周期に比例するときは `b × T512 ÷ T256`。予測範囲を上下0.075 ms広げ、512フレーム側の観測範囲と比較する。試験の成否は各要求のフレーム数、2時計、左右PCMを照合して決め、予測の判定を別に保存する。[計測入口と照合](../tools/measure_cubeb_output_callback.py)

## 実測

macOS 15.6.1（24G90）arm64のMacBook Pro内蔵スピーカーを既定出力として、256フレームの比較と同じ試験用バイナリを用いた。SHA-256は `cbe303957a4f5e81e1c125f88bd6ff695ed5cc66c9eef42158892b9c9e041f94`。初回と `/private/tmp` からの再実行では各40試行を行い、各600判定に合格した。待機0と9.9 msの16試行は機器時刻が連続し、残る64試行は対象要求の直後に512フレーム飛んだ。実測区間の2実行を合わせると、連続した最長は9.911417 ms、飛びがあった最短は10.084042 msだった。[初回](../runs/cubeb-output-deadline-sweep-512-20261121-a/summary.json)・[再実行](../runs/cubeb-output-deadline-sweep-512-20261121-repeat/summary.json)

事前登録の許容幅を加えた予測範囲は、一定時間の余裕で10.309833〜10.460167 ms、比例する余裕で10.028000〜10.178667 ms。初回と再実行では比例する範囲だけが実測範囲と交差した。初回の範囲が約0.17 ms広かったため、512フレームの待機値をさらに約10.0 msに集中させた別ケースを登録した。元の2実行と同じ式で判定し、各判定は別々に残す。[追加比較の事前登録](../cases/cubeb-output-callback-deadline-sweep-512-refined.json)

細かく振った40試行は600判定に合格した。実測10.005000 msで次の機器サンプル時刻が512フレーム飛び、これより長い10.064250 msで連続した試行があった。時間範囲は約0.0593 ms重なった。予定ホスト時刻の間隔は連続時に10.667 ms、飛んだ試行で21.333 ms。飛びは対象回の直後に限られた。処理時間で連続と飛びを一線で分けられなかったため、追加比較での事前登録の判定は「二つの予測を区別できない」だった。[追加比較の判定](../runs/cubeb-output-deadline-sweep-512-20261121-refined/summary.json)

### 予定ホスト時刻と返却時刻の差

探索として、対象要求の残り時間を `mHostTime − 返却前の計時点` として計算した。これは `scheduled_host_minus_entry_ms − callback_ms` に等しい。10.005000 msで飛んだ回の残りは2.036792 msで、10.064250 msで連続した回は2.096792 msだった。細かく刻んだ40試行では、飛んだ回の残り時間の最大2.092667 msと、連続した回の最小2.096792 msが離れていた。512フレームの全120試行を合わせると、初回に残り2.087292 msで連続した回があり、約0.0054 ms重なった。処理時間だけで比べた場合の約0.0593 msより重なりが小さい。この差は機器のタイムスタンプとcubebの記録点から求めた観測値で、ドライバの実際の締め切りの位置は未特定。[初回の時刻](../runs/cubeb-output-deadline-sweep-512-20261121-a/summary.json)・[追加比較の時刻](../runs/cubeb-output-deadline-sweep-512-20261121-refined/summary.json)

全120試行で、各8,704フレームの左右PCMが独立計算とビット一致した。生PCMの整数値を剰余逆数でフレーム番号に復元し、生CSVの機器サンプル時刻差とホスト時刻差も照合した。256フレームの従来条件で56判定、固定版cubebの2テスト、固定上流CHIMERAのホスト分割試験が通った。実行記録の入力39件、出力504件のサイズとSHA-256を確認し、採取データ約64.98 MBをRTL9210B-CGに保存した。[従来条件の回帰](../runs/cubeb-output-callback-20261121-size-regression/manifest.json)・[cubebの試験ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/cubeb-deadline-size-test-20261121.log)・[CHIMERAの試験ログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/chimera-deadline-size-engine-test-20261121.log)

## 再現

研究ワークスペースから実行する。`<実行ID>` は未使用の名前に置き換える。[試験用バイナリの作り方](cubeb-output-callback-probe.md#再現)

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=40000000 ../../.venv/bin/python \
  tools/measure_cubeb_output_callback.py <実行ID> \
  "$build/target/release/examples/chimera-output-probe" \
  --case cases/cubeb-output-callback-deadline-sweep-512.json
```

待機をさらに細かく振る場合は `--case cases/cubeb-output-callback-deadline-sweep-512-refined.json` を指定する。
