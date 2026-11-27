# Chromiumの描画トレースで無音先行のフレーム番号を照合する

前回はChromiumの先行Workletで、初回の `currentFrame` 直後の2量子に記録がない試行を32件中23件観測した。今回は同じ歌唱画面から先行Workletの各呼び出しにフレーム番号を付け、Chromiumのトレースで描画要求から作者コードまでを同時に取得する。予測は、記録がない2量子にもグラフ描画があり、先行Workletの作者コード実行が欠けるというものだった。[前回の観測](worklet-live-song-fast-app-silent-lead-input-trace.md#実測)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead-native-trace.json)

## 固定上流とブラウザの時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` は既存のContextを再開し、初回の `build()` はWorkletを登録してからWASMモジュールを渡す。`playTune()` は音節とMIDI番号・拍数・BPMを使い、`60 / bpm` 秒を1拍として歌唱計画を作る。Workletが相対秒で受け取ったジェスチャーは `Engine::schedule()` で `voice.clock + lead` だけ移動する。`process()` は要求されたフレーム数を `engine_render()` へ渡し、Rustの `Engine::render()` は累積位置 `pos` の剰余でブロック位相を保持する。固定上流の短音試験は母音と拍の一致、ホスト分割試験は分割を変えたときのPCMのビット一致を検査している。今回のネイティブ観測は候補の無音先行で行い、歌唱PCMは同じ短音の保存済み上流へ照合する。[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

実行したHeadlessChromeは `156.0.8078.4`、リビジョンは `f842f52ef39fd97b449eb27cff414bf05a98ddce`。その版の `AudioDestination::Render()` は音声出力側の要求を受け、Worklet用のタスクランナーがある場合は `RequestRender()` を別スレッドに渡す。要求された範囲を `RealtimeAudioDestinationHandler::Render()` が128フレーム単位で処理する。ここでグラフを描画し、Contextのサンプル位置を量子長だけ進めてからWorkletのグローバルな時計を更新する。Worklet内で見える `currentFrame` はそのグローバルな値。最初はWorklet用オブジェクトの作成時に読んだContextのサンプル位置で初期化し、その後の更新にはグラフロックの取得とスレッドの一致が必要になる。実時間で動作中にWorkletが準備されると、Chromiumは描画先を再起動してWorklet用スレッドへ切り替える。[出力要求とグラフ描画](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/platform/audio/audio_destination.cc#L661)・[量子のサンプル位置更新](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/realtime_audio_destination_handler.cc#L259)・[初期値の取得](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/audio_worklet_messaging_proxy.cc#L154)・[グローバルへの反映](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/audio_worklet_object_proxy.cc#L34)・[描画先の切り替えと更新条件](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/base_audio_context.cc#L890)

## 同一再生内の照合

CDPの `Tracing.start` を歌唱画面を開く前に実行し、再生と通常のWAV・観測保存を終えてからトレースを回収する。試験設定 `songSilentLeadNativeTrace=1` の時だけ、先行Workletの通知までの各呼び出しにフレーム番号付きの `console.timeStamp()` を発行する。絶対フレームはサンプル単位、ネイティブトレースのタイムスタンプはµs。各マーカーを、同一スレッド上で包含する作者コード実行、128フレームの描画、描画要求に結び付ける。マーカー列が入力記録のフレーム列と一致することも確認する。隣り合うマーカーのフレーム番号が384離れる場合、その間に128フレームの描画が2件と作者コード実行が0件あれば事前予測を支持する。両端が隣接した描画に対応する場合は、描画数に対してフレーム番号が飛んだ事例として記録する。[画面取得](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L415)・[マーカー](../../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts#L30)・[解析](../tools/worklet_song_native_trace.py)

小規模の予備計測では、4量子条件の先頭が2,048と2,688、8量子条件では2,048と2,432だった。どちらも同じ描画要求の隣接した2件で、間に追加の描画も作者コード実行もなかった。最初のマーカー2,048は登録要求時のContextフレームと一致し、先行枝の接続直前の時計はそれぞれ2,560、2,304だった。正式な取得ではこの結果を別の実行で確かめ、事前の予測は元の判定のまま保存する。[4量子の予備トレース](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-song-native-trace-pilot-20261121/four/trace.json)・[8量子の予備トレース](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-song-native-trace-pilot-20261121/eight/trace.json)

## 実測

2回で32試行の全215マーカーを、同じ再生の作者コード実行、グラフ描画、描画要求に一意に対応づけた。CDPの欠落報告は全試行で0。初回12件、再実行11件の計23試行で、先行Workletの最初の `currentFrame` から次の値までが384フレーム離れ、フレーム番号に256の欠番があった。23件すべてで作者コード実行は同じ256フレームの描画要求に入り、対応する128フレームの描画は隣り合っていた。両者の間の描画も作者コード実行も0件。マーカーの実時間差は65〜218 µsだった。事前予測を満たす事例は0件だった。[初回の照合](../runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-a/summary.json)・[再実行の照合](../runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-repeat/summary.json)

フレーム番号が飛んだ23件はすべて、Worklet用スレッドに切り替わってからの最初の描画だった。最初の `currentFrame` はアプリのWorklet登録要求時のContextフレームと一致し、2回目の値は先行枝の接続直前のContextフレームに128を加えた値と一致した。たとえば初回の直接出力・8量子条件の1組目では、登録要求時が1,280、接続直前が1,536、最初の2回のWorklet値は1,280と1,664。2回の作者コードは256フレームの同じ要求の中にあった。これらの結果は、初回にWorklet生成時の値が見え、その描画の後でContextの時計に更新されたという解釈と整合する。ロック取得の成否や、時計を書き換えた一行を直接計測した結果は含まない。[代表試行の観測](../runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-a/artifacts/direct-1-eight/browser.json)・[代表試行のトレース](../runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-a/artifacts/direct-1-eight/trace.json.gz)・[Chromiumの時計の更新](https://github.com/chromium/chromium/blob/f842f52ef39fd97b449eb27cff414bf05a98ddce/third_party/blink/renderer/modules/webaudio/base_audio_context.cc#L913)

前回から引き継いだ取得指標は、`currentFrame` ごとに入力やマーカーが観測されなかった位置を数える。その欠番を実際の呼び出し欠落として扱う事前予測は今回外れた。全32試行で歌唱側の開始待ちと歌唱中の呼び出しは連続し、PCM49,200フレーム、状態769点、歌唱計画は保存済みのオフライン基準と一致した。並列観測16試行では予約位置のPCM、補完80フレーム、前後の無音を確認した。トレースとWAVを標準ライブラリで読み直して照合した。固定上流との最大PCM差は `2.7573 × 10⁻³`、`10⁻⁶` を初めて超えた位置は27,939フレームで、歯のフィルタ下限1,200 Hzを適用した基準の差と一致した。[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)・[並列観測の例](../runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-repeat/artifacts/observed-1-four/output-probe.json)

次は、Chromiumで初回のWorklet登録をContextの再開前に行う条件を用意し、再開後に登録する既存経路と比べる。最初の `currentFrame` と描画順、再開からの時間、PCMを照合する。機器からの波形と聴感は未計測。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-native-trace.json
```

macOS 15.6.1 arm64、HeadlessChrome 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回と `/private/tmp` からの再実行は各402件の取得判定を通過した。グラフ描画だけが進むという予測は両実行で外れた。両実行の入力574件と出力296件のサイズとSHA-256を照合し、大容量成果30.10 MBをRTL9210B-CGに保存した。CDPのトレースは試行ごとに gzip で全件保持した。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-repeat/manifest.json)
