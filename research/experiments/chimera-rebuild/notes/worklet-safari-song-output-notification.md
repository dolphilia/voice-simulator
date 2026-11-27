# Safariの歌唱準備中に出力側の描画通知を追う

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AudioEngine.build()` がWorkletを `AudioContext` の出力へ接続する。`ChimeraProcessor.process()` が `engine_render()` を呼んで出力PCMを受け取り、`Engine::render()` が絶対サンプル位置に基づいて128フレーム境界で予約を更新する。ホストからの要求長を変えても、絶対フレームで操作位置をそろえれば生成PCMが一致することを固定上流のテストで確認する。今回はWorkletのサンプル列がブラウザの出力へ渡る間の通知を観測する。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

公開WebKitの `RemoteAudioDestination::render()` はGPUプロセスのI/Oスレッドで共有リングを読み、成功時に読み出し位置を要求長だけ進める。読み出し結果にかかわらず要求フレームの累計を加え、Darwinの `semaphore_signal` を呼ぶ。Webコンテンツ側の `RemoteAudioDestinationProxy` は待機明けに累計と前回値の差から要求フレーム数を求める。内部FIFOを取り出して共有リングに書いた後、`AudioDestinationResampler::render()` を呼んで後続の描画を依頼する。Workletがある構成では、依頼先のWorkletスレッドが128フレームずつ描画してFIFOを補充する。FIFOが不足すると、取り出し側は足りないフレームを無音で埋める。GPUのリングとWeb側のFIFOは別の保持領域であり、セマフォの通知や共有リングの書き込みが続いている場合にも、FIFOが返したPCMの内容は未観測である。[GPUの更新順](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L179-L208)・[Darwinの通知と待機](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/Platform/IPC/darwin/IPCSemaphoreDarwin.cpp#L68-L79)・[Web側の待機](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L88-L109)・[共有リングへの書き込み](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L226-L251)・[Workletへの依頼](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/AudioDestinationResampler.cpp#L101-L143)・[FIFOの読み出しと無音埋め](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/PushPullFIFO.cpp#L80-L126)

48 kHzのSafari歌唱で、同じ予備描画16,384フレームを一括処理と67片に分ける条件を比較する。先行信号を流したままAudio ClientとSystem Call Traceを同時に始め、時刻をナノ秒でそろえる。GPU側のPIDは先行信号の出力開始で同定し、I/OサイクルのスレッドIDとトラップを対応づける。Web側は公開ソースと採取表で一致するスレッド名を使い、Mach待機の開始・終了を集計する。2プロセスのMachポート名はプロセスごとに扱い、同名の数値を受け渡しの証拠には使わない。ブラウザ側の準備窓は1 ms刻みの構築・準備時刻から決め、採れた歌唱PCM、先行信号と観測状態を保存基準に照合する。[事前登録](../cases/worklet-safari-song-output-notification.json)・[計測器の説明](https://developer.apple.com/documentation/audiotoolbox/analyzing-audio-performance-with-instruments)・[先行するAudio Client単独の結果](worklet-safari-song-audio-client.md)

## 実測

プロセスタップを再試行した。先行音の開始・停止・再開で同じWebKit GPUの出力フラグが切り替わり、グラフの各20,480点と欠落・重複・無音の対照を再確認した。採取アプリのPIDを得たが、8秒で開始通知が届かず、17判定のうちタップ開始・終了の1件が欠測した。今回の対象PIDで絞ったOSログには録音許可の要求や許可状態を確定できる記録は得られなかった。[タップの再試行](../runs/safari-process-tap-calibration-20261122-render-status-followup/summary.json)

同時計測では、最初の2試行とも保存待ち25秒を超えた。出力された生トレースを保持し、待ちを90秒に延ばして順序を反転した。再試行では両トレースの保存が完了した一方、採取表の末尾は一括で構築の約159 ms前、分割で約64 ms前にあった。準備前の実データを使う補助集計を作り、別途、GPUのPIDだけを対象にした同時計測と、System Call Trace単独も試した。過去の基準・準備・確認窓の判定は維持した。[最初の採取](../runs/worklet-safari-song-output-notification-20261122-a/summary.json)・[順序反転の採取](../runs/worklet-safari-song-output-notification-20261122-repeat/summary.json)・[GPUに絞った同時計測](../runs/worklet-safari-song-output-notification-20261122-gpu/summary.json)

順序反転の両条件で、準備前の連続区間に一括47件、分割76件のI/Oサイクルがあった。全123件のサイクル内でGPUのI/Oスレッドによる `semaphore_signal_trap` を1回ずつ記録し、Web側の `RemoteAudioDestinationProxy render thread` の待機完了も同じ件数だった。各待機完了と直前のGPU通知の時差は中央値約9.7〜9.8 µs、最大20.4 µs。Web側では同じプロセスの別スレッドに `WebCore: AudioWorklet` が現れた。プロセスを越えたセマフォの同一性は、時刻と件数の一致に基づく推定である。[対象スレッドと先行区間の照合](../runs/worklet-safari-song-output-notification-20261122-all-analysis/summary.json)

全プロセスのSystem Call Trace単独では、分割の準備中を採取できた。一括は構築の約31 ms前に記録が途切れた。分割の準備中はGPU通知68件、Web側の描画スレッドの待機完了68件だった。最大7.158 msの待機完了間隔の間にGPUから2件の通知があり、Web側ではその間の7.143 msを `psynch_cvwait` に費やしていた。次のセマフォ待機自体は約0.4 µsで戻った。待機対象の条件変数や、その前後のPCMは未特定である。[単独計測の区間](../runs/worklet-safari-song-output-notification-20261122-syscalls-analysis/summary.json)・[分割試行の抽出結果](../runs/worklet-safari-song-output-notification-20261122-syscalls-analysis/artifacts/worklet-safari-song-output-notification-20261122-syscalls/pair-1-split.json)

GPUのPIDだけに絞ったSystem Call Traceで、記録開始通知から解放までの待ちを200 msから20 msに短縮した。実行順を反転した2組全4試行で基準・準備・準備後の3窓を覆った。一括の準備窓で通知は51・52件、分割では両試行68件だった。各試行の最大通知間隔は一括2.682〜2.690 ms、分割2.684〜2.697 ms。先行音のグラフでの最大間隔は一括141〜142 ms、分割7〜13 msで、ペアごとに128・135 ms短縮した。各試行で先行PCM229,376サンプル、歌唱PCM31,200サンプル、声門など488観測点が基準に一致した。この2組で観測したのはGPUの通知とグラフ内の歌唱・先行音であり、通知の各回に対応するI/Oサイクルと一括準備中のWeb側の処理は未取得である。[2組の計時](../runs/worklet-safari-song-output-notification-20261122-gpu-20-series/summary.json)

公開版の内部FIFOの最大長は96量子、48 kHzでは12,288フレーム相当である。以前の一括準備中に見えた143〜148 msのグラフ間隔は、48 kHz換算で約6,864〜7,104フレームに当たる。実機のFIFO残量、共有リングの書き込み内容、無音埋めのフレーム数と実際のPCMは未観測である。[公開実装のFIFO長](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/AudioDestinationResampler.cpp#L37-L46)・[前回のグラフ実測](worklet-safari-song-audio-client.md#実測)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6、xctrace 26.0（17C52）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4を使用した。最終の比較は研究ワークスペースと `/private/tmp` から実行し、各31判定を通過した。分析では全4試行が3窓を覆い、各実行で登録したグラフ間隔と通知間隔の2予測が成立した。目次・生トレースと必要なスレッドの抽出結果をRTL9210B-CGに保存した。最後の2組では、一時XMLを解析時に展開する方式に切り替えた。固定上流のホストブロック長試験も通過した。[研究ワークスペースの採取](../runs/worklet-safari-song-output-notification-20261122-syscalls-gpu-20-forward/manifest.json)・[別ディレクトリの採取](../runs/worklet-safari-song-output-notification-20261122-syscalls-gpu-20/manifest.json)・[解析のマニフェスト](../runs/worklet-safari-song-output-notification-20261122-gpu-20-series/manifest.json)

初回の採取失敗などを含む12実行について、2,181入力と1,571出力をマニフェストに照合した。RTL9210B-CGに残した正式採取物は計2,150,421,065バイトで、このうち最終の2組とその解析は40,732,931バイトだった。初回に別途展開した予備XML約471 MBは、生トレースから再生成できることを確認して整理した。

```bash
# 研究ワークスペースで、採取・分析ごとに新しい実行IDを指定
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_audio_client.py \
  worklet-safari-song-output-notification-local --case cases/worklet-safari-song-output-notification.json \
  --system-calls-only --attach-gpu-only --release-delay-ms 20 --defer-syscall-export

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_safari_output_notifications.py \
  worklet-safari-song-output-notification-local-analysis worklet-safari-song-output-notification-local
```

次はWeb側の描画スレッドとWorkletを一括準備窓で同時に追い、分割で見えた条件変数待ちの呼び出し元を確認する。出力PCMを判定するには、試験音を使ったプロセスタップの較正が必要になる。[出力PCMの較正手順](safari-process-tap-calibration.md#実行と保存)
