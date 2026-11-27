# Safariの描画スレッドが歌唱準備中に待つ箇所

## 呼び出しと観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では `AudioEngine.build()` が `AudioContext` にWorkletをつなぐ。`ChimeraProcessor.process()` はWASMの `engine_render()` で出力を作り、`Engine::render()` は絶対フレーム数を保持しながら128フレーム境界で制御を更新する。ホストの要求長を変えても操作を絶対フレームでそろえるとPCMが一致することを上流テストで確かめる。今回の観測はこの描画の下流にあたる。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

公開WebKitの `RemoteAudioDestinationProxy` はGPUからのMachセマフォ待ちが終わると、累計と前回の累計との差から処理すべきフレーム数を求める。FIFOから取り出したフレームを共有リングに書き、その後に描画コールバックを呼ぶ。共有の出力アダプターは `SharedAudioDestination::sharedRender()` へ処理を渡す。Workletへ処理を送る分岐では、アダプターがバス、フレーム数、出力位置をWorkletのタスクに渡し、手元の `BinarySemaphore` を待つ。Workletはコールバックから戻った後に同じセマフォを通知する。この内部の条件変数待ちは、GPU通知を受け取る最初のMachセマフォ待ちとは別に記録する。[GPU通知を受け取る順序](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L88-L109)・[FIFOと共有リング](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L224-L251)・[共有出力とWorkletの完了待ち](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/SharedAudioDestination.cpp#L314-L331)

先行信号の開始前後で同じユーザーの `com.apple.WebKit.WebContent` を調べ、`RemoteAudioDestinationProxy render thread` と `WebCore: AudioWorklet` をそろえて持つようになったPIDにSystem Call Traceを付ける。準備前90〜10 ms、準備、完了後10〜90 msで、描画スレッドのMach待機の復帰間隔と、内部の `psynch_cvwait` の時刻・長さ・スタックを記録する。ブラウザ側の境界はミリ秒単位、トレース内の時刻と差分はナノ秒単位とする。公開版の呼び出し順と、試験機のバイナリから得たスタックの関数名を照合し、異なる実行間は各イメージのUUIDとロードアドレスからの相対位置で照合する。[事前登録](../cases/worklet-safari-song-webcontent-waits.json)・[PID選定](../tools/chimera_webkit_audio_threads.swift)・[待機の解析](../tools/measure_safari_webcontent_waits.py)・[AppleのSystem Call Traceの説明](https://developer.apple.com/documentation/audiotoolbox/analyzing-audio-performance-with-instruments)

## 実測

実行順を反転した2組、計4試行で、同じWebContent内に別々の描画スレッドとAudioWorkletを記録した。全試行の先行PCM各229,376サンプル、歌唱PCM各31,200サンプル、声門などの488観測点が基準に一致した。準備窓での先行音のグラフ内の最大間隔は一括139・141 ms、分割は両方7 msだった。録音許可を要するプロセスタップは使わず、既知波形はブラウザ内で照合した。[初回の採取](../runs/worklet-safari-song-webcontent-waits-20261122-a/summary.json)・[順序反転の採取](../runs/worklet-safari-song-webcontent-waits-20261122-repeat/summary.json)

| 準備窓の観測値 | 一括 | 分割 |
| --- | ---: | ---: |
| 先行音の最大間隔 | 139・141 ms | 7・7 ms |
| Web側のMachセマフォ待機復帰数 | 1・1件 | 67・68件 |
| 準備に重なるMach待機復帰間隔の最大 | 137.091・139.484 ms | 4.735・6.418 ms |
| その間に完了した条件変数待ち | 137.053・139.470 ms | 4.716・6.402 ms |
| 条件変数待ちの準備窓内の合計 | 134.957・137.847 ms | 140.510・135.409 ms |

初回解析では、一括の復帰数が各1件で登録した12件に届かなかった。長い復帰間隔の開始が構築時刻より0.033・1.143 ms後だったため、準備窓全体をまたぐという補助条件も成立しなかった。反転順の一括では基準窓の先頭約5.8 msも採取範囲の前だった。これらの判定と25 ms以下という予測の初回の未判定を保存した。そのうえで、記録された単一の完了済み待機が準備窓に25 msを超えて入るかを判定した。[当初の判定と時刻](../runs/worklet-safari-song-webcontent-waits-20261122-analysis/summary.json)

最長の4待機と、保存済みの分割試行で得た7.143 msの待機は、`SharedAudioDestination::sharedRender()` と `WTF::BinarySemaphore::waitUntil()` のスタック位置がイメージUUID・相対アドレスとも一致した。WebCoreイメージ内の `sharedRender` の相対位置は `0x2514f28` だった。分割の2試行では待機の合計が約135〜141 msに達し、1回あたりの最長待機は約4.7〜6.4 msだった。同じ呼び出し元で一括処理の長い待機が、分割では複数回の短い待機に分かれた。[保存済みの分割と今回のスタック](../runs/worklet-safari-song-webcontent-waits-20261122-analysis/artifacts/waits.json)

補助解析では、同じWebContentの同一条件変数アドレスへのWorklet側の `WTF::BinarySemaphore::signal()` を、対象の条件変数待ちの終了前に各試行1件ずつ特定した。通知のシステムコール開始から描画スレッドの待機復帰までは3.5〜8.0 µsだった。ブラウザ時計の境界を両端各1 ms内側に取っても、一括の単一待機は準備窓に133.0・136.8 ms重なった。これは25 ms以下という予測を反証する。`psynch_cvwait` と `psynch_cvsignal` の第1引数はともに条件変数アドレスで、比較は試行内の同一PIDに限った。[補助解析](../runs/worklet-safari-song-webcontent-waits-20261122-completed-waits/summary.json)・[XNUのシステムコール定義](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/syscalls.master#L456-L457)

準備後の80 msには、一括で83・84件のMach待機が完了し、うち連続する復帰の間隔が100 µs以下の組は55・57組だった。分割は両試行とも30件で、100 µs以下の組は0組だった。次の計測で照合したいのは、復帰が密集した期間に共有リングへ実際に書かれたフレーム数と出力PCMである。[準備後の時刻と件数](../runs/worklet-safari-song-webcontent-waits-20261122-completed-waits/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6、xctrace 26.0（17C52）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Swift 6.2.3、Python 3.14.4を使用した。採取は研究ワークスペースと `/private/tmp` から順序を反転して実行し、各31判定に合格した。補助解析では4試行すべてで待機と通知を照合し、元の一括2試行の観測窓判定は未達のまま保存した。4実行の計1,218入力と396出力をサイズ・SHA-256で照合した。RTL9210B-CGに実体71,711,094バイトを置き、新規トレースのXMLは解析時だけ展開した。固定上流のホストブロック長の試験も通過した。[初回](../runs/worklet-safari-song-webcontent-waits-20261122-a/manifest.json)・[反転順](../runs/worklet-safari-song-webcontent-waits-20261122-repeat/manifest.json)・[補助解析](../runs/worklet-safari-song-webcontent-waits-20261122-completed-waits/manifest.json)

```bash
# 研究ワークスペースで採取し、新しい実行IDを指定
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_audio_client.py \
  worklet-safari-song-webcontent-waits-local --case cases/worklet-safari-song-webcontent-waits.json

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=200000000 \
  ../../.venv/bin/python tools/measure_safari_webcontent_waits.py \
  worklet-safari-song-webcontent-waits-local-analysis worklet-safari-song-webcontent-waits-local --completed-wait-check
```
