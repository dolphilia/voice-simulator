# 分割した歌唱の事前描画を2量子遅らせる

前回の48 kHz共有Contextでは、分割の第1片が4試行とも歌唱ノードの構築と同じ256フレームの機器要求に入った。最も長い要求を短くするため、先行音と `Pop Dee` を揃え、64フレーム3片を開始する時刻だけを2量子遅らせる対照を登録した。[前回の実測](worklet-live-song-split-preparation.md#実測)・[事前登録](../cases/worklet-live-song-deferred-split-preparation.json)

## 描画と開始時刻の読解

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` は、レートをHzで指定したContextにモジュールを登録し、コンパイル済みWASMを `AudioWorkletNode` に渡す。`ChimeraProcessor` は構築時に `engine_new()` で状態を作り、`process()` に渡された出力長を `engine_render()` のフレーム数として指定する。RustのABIは要求長を出力バッファの上限内に収め、`Engine::render()` が共有バッファを埋める。エンジンは出力位置 `pos` の128フレーム境界で拍の予定を更新し、次の境界まで声を進めてから `pos` に出力長を加える。JSはfloat32 PCMを出力に移し、処理時間を `1000 × フレーム数 ÷ レート` の予算と比較する。上流の `output_does_not_depend_on_the_host_block_size()` は、操作を同じ絶対フレームに固定し、1・77・4,096・48,000フレームの分割が128フレームの基準とビット一致することを検査する。[AudioEngine.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[processor.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[WASMのABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[engine.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[エンジンのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

試験用FirefoxのGecko `fdd757a2e09c9471cddf383e64e631e4ce178499` では、`AudioWorkletNode` の初期化が構築用の処理をグラフに送り、`WorkletNodeEngine::CallProcess()` が量子の処理を呼ぶ。`AudioCallbackDriver::DataCallback()` は要求されたバッファを満たせるよう、現在のグラフ時刻をWeb Audioのブロック境界まで進めて `OneIteration()` を呼ぶ。機器要求の開始・終了はcubebのコールバックで観測する。構築、Workletのフレーム、機器要求の対応は、Firefoxのグラフと先行音の連番で毎試行確認する。[AudioWorkletNode.cpp](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/webaudio/AudioWorkletNode.cpp)・[GraphDriver.cpp](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/GraphDriver.cpp)・[cubeb計測パッチ](../tools/chimera-cubeb-output-snapshot.patch)

## 比較条件

`songRenderPreparation=split-192-deferred` で、先行無音の最初の `currentFrame` を `f`、量子長を `Q` として、同じ使い捨てのWASM状態を `f + 2Q`、`f + 4Q`、`f + 6Q` に描画する。対照 `split-192` は `f`、`f + 2Q`、`f + 4Q` に描画する。両条件で第1片には0フレーム1,000回を含め、第3片の後に使い捨て状態を解放する。描画済みフレームは64・128・192と増える。先行無音はそのまま出力し、歌唱状態は連続8量子と2,048フレームのリードを経た予定フレームから進める。WASM側の演算、同時に保持する発声ハンドル、観測点は両条件で共通にした。[Worklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[開始条件](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[使い捨て状態の処理](../crates/vocal-wasm/host/fixed-voice.ts)

構築を含む機器要求を0とし、両条件とも0〜3の4要求で最長のcubeb処理時間を比較する。機器時刻とPCMは前後各8要求の窓で別々に確認する。48 kHzでは128フレームの量子が2.667 ms、256フレームの要求が5.333 msに相当する。分割を始める量子はフレームで決める。機器の要求が変わった場合の割り振りは実測が必要となる。[照合器](../tools/inspect_firefox_cubeb_output.py)

## 実測

macOS 15.6.1 arm64、計測付きFirefox Nightly 157.0、Playwright 1.64.1、Node v24.19.0、Bun 1.4.4で実行した。初回と `/private/tmp` からの再実行で、各4試行の採取と照合に関する77判定および固定上流の17テストを通過した。構築から4要求のピークは従来分割の3.76〜5.28 msから、2量子遅らせた分割の1.89〜3.53 msになった。対応する4組では各0.70・1.86・1.79・2.48 ms短縮し、全体の中央値は1.83 ms。初回と再実行の中央値はそれぞれ1.28 msと2.14 msで、事前登録の0.8 msを上回った。[初回](../runs/worklet-live-song-deferred-split-preparation-20261121-a/summary.json)・[再実行](../runs/worklet-live-song-deferred-split-preparation-20261121-repeat/summary.json)

準備片は全試行で予測どおり、従来分割では要求0・1・2、2量子遅らせた分割では要求1・2・3に対応した。歌唱開始は両条件とも最初の無音量子から3,072フレーム後。全8試行で歌唱WAVが再実装の基準とバイト一致し、観測1,425行、調音計画、拍、辞書、WASMの照合も通過した。固定上流と異なる最初のビットは全条件で出力フレーム4,114にあり、最大誤差は2.33 × 10⁻¹⁰だった。前後17要求の先行音は全試行で独立計算の連番4,352フレームと一致した。

### 名目予算の直前で発生した時刻の飛び

後ろへ移した分割の4試行で機器時刻の飛びは0、歌唱の先頭2量子の超過も0だった。再実行の従来分割 `2-split192` では、構築を含むcubebコールバックが5.283 msで、次の予定間隔が10.667 msへ伸び、機器のサンプル時刻が256フレーム飛んだ。生ログの直前の開始間隔は5.333 msだった。5.333 msの名目周期から引いた余裕は約0.050 msで、実際の次の開始は返却から5.384 ms後だった。同じ試行で歌唱の先頭量子も2.994 msだった。このため、再実行では事前登録の時間短縮条件は成立し、両条件の全試行に連続性と量子予算を求めた判定は成立しなかった。[再実行の判定と生ログ](../runs/worklet-live-song-deferred-split-preparation-20261121-repeat/manifest.json)

従来の3条件の回帰確認は109判定と固定上流の17テストを通過した。従来分割の `2-split192` では5.049 msでも次の予定サンプル時刻が256フレーム飛んだ。回帰確認の歌唱WAV全6本も基準とバイト一致した。全3実行の入力857件と出力225件のサイズ・SHA-256を照合し、約59.77 MBの計測データをRTL9210B-CGに保存した。[回帰確認](../runs/worklet-live-song-split-preparation-20261121-deferred-regression/manifest.json)

2回とも、飛びの最初の観測点は構築と第1片を含む要求の次の機器時刻だった。cubebの計測はコールバック内の処理時間を表す。ドライバ内部の締め切りの位置を調べるには、既知PCMのまま処理時間だけを変える対照が必要になる。プロセスタップの校正は直近の実行で成立しておらず、機器から出た音の連続性は保留した。[既知PCMのcubeb対照](cubeb-output-callback-probe.md)・[プロセスタップの校正記録](../runs/worklet-live-song-process-tap-20261121-calibration-recheck/manifest.json)

## 再現

研究ワークスペースから実行する。`<実行ID>` に未使用の名前を入れる。

```bash
firefox=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=120000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_shared_context.py <実行ID> \
  --deferred-split-preparation --cubeb-output "$firefox"
```
