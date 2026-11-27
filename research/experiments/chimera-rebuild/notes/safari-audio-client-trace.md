# Safariの試験音をAudio ClientのI/O時刻に対応づける

## 計測点と比較条件

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` は、ブラウザの `AudioContext` に `AudioWorkletNode` を接続する。`ChimeraProcessor.process()` は `engine_render()` で要求された数のフレームを作り、float32 PCMを出力配列へ書き込む。上流のブロック長試験は、操作を同じフレームへ置くとホスト側の分割が変わってもPCMが一致することを確認する。Safariの研究用グラフで採るサンプル列に加え、今回はその先でCore Audioが音声クライアントのI/O処理を呼ぶ時刻を観測する。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[上流のブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

前回の較正では、Safariの逆相ステレオ試験音を開始、停止、再開すると同じ `com.apple.WebKit.GPU` プロセスがCore Audioで出力の有無を切り替えた。今回はその手順で対象PIDを決め、Xcodeの `xctrace` に `Audio Client` 計測器だけを載せて、そのPIDへアタッチする。停止中は1秒、再生中は2秒を記録し、`audio-hal-client-io-cycle` の `Cycle` 行から、開始と処理時間のナノ秒値、I/OスレッドIDを読む。同梱のAudio System Trace全体で採るときのシステムコールなどは収録対象に加えない。`Audio Client` はクライアント側のI/O区間を記録する計測点で、OSの録音許可を要するタップとは取得するデータが異なる。[前回のPCM較正](safari-process-tap-calibration.md)・[AppleのAudio Client解説](https://developer.apple.com/documentation/audiotoolbox/analyzing-audio-performance-with-instruments)・[FirefoxでのI/O時刻の先行計測](worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)

再生中にSafariのグラフから、128フレームごとの `currentFrame` とミリ秒刻みの `Date.now()`、計230,400サンプルを採る。xctraceの目次から開始時のエポック時刻を読み、I/O区間の両端がグラフ観測の時刻範囲にあるか判定する。I/O開始間隔の中央値に48 kHzを掛け、グラフの量子長128フレームと比較する。この換算は時間の目安であり、サイクルが運んだ実フレーム数やスピーカーでの欠落を求めるには追加の計測が必要となる。記録されたPCMは保存基準・独立計算に照合する。[事前登録](../cases/safari-audio-client-trace.json)・[時刻とPCMの照合](../tools/measure_safari_audio_client_trace.py)

## 実測

同じWebKit GPUプロセスを計測し、停止中は両実行とも0件、再生中は770件・771件のI/Oサイクルを得た。再生中の区間は全件がグラフ観測の4,797 msの範囲内にあり、各実行で単一のI/Oスレッド上に並んでいた。I/O開始間隔の中央値は約2.667 msで、48 kHz相当の約128フレームだった。最初の試験音各20,480サンプルと再開後の各230,400サンプルのPCMは独立計算とビット一致し、再実行と同じバイト列だった。[初回の要約](../runs/safari-audio-client-trace-20261122-a/summary.json)・[再実行の要約](../runs/safari-audio-client-trace-20261122-repeat/summary.json)

| 休止中／再生中の観測量 | 初回 | 再実行 |
| --- | ---: | ---: |
| 停止中のI/Oサイクル | 0 | 0 |
| 再生中のI/Oサイクル | 770 | 771 |
| 再生中のI/O開始間隔の中央値 | 2.66675 ms | 2.66646 ms |
| 再生中のI/O開始間隔のp99・最大 | 2.68324・4.77842 ms | 2.68943・5.14871 ms |
| GPUプロセスのI/O処理時間の中央値 | 6.458 µs | 6.042 µs |

最長間隔は両実行とも15番目と16番目のI/O開始の間で、トレース開始から約0.31秒で生じた。直後の間隔は0.539 msと0.366 msだった。負荷を加えた歌唱との比較では、短い対照の時点ですでにこの程度の間隔変動が出ることを考慮する。このデータからはサンプル欠落の有無を判定していない。[初回のI/O区間の表](../runs/safari-audio-client-trace-20261122-a/artifacts/active-cycles.xml)・[再実行のI/O区間の表](../runs/safari-audio-client-trace-20261122-repeat/artifacts/active-cycles.xml)

公開WebKitの `1392437bb060048807e94d171c0fdf45e7d27301` では、GPUプロセスの `RemoteAudioDestination::render()` は共有リングバッファから指定フレームを読み、累積した要求フレーム数を更新してセマフォを通知する。Web側の `RemoteAudioDestinationProxy` は通知後に累積フレーム数の差から処理量を求め、共有バッファにPCMを書く。この実装ならGPU側I/Oの処理時間にWorkletの計算全体が現れないことを説明できる。インストール済みSafari 18.6とのソースの厳密な対応は未確認で、今回確認したのはGPU側I/Oの時刻である。リングバッファと実際の出力サンプルを検証するには別の観測が必要となる。[公開WebKitのGPU側](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L172-L192)・[Web側の通知待ちと描画](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L82-L101)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、Node.js 24.19.0、xctrace 26.0（17C52）、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースと `/private/tmp` から各17判定を通過し、各17入力・159出力のサイズとSHA-256を照合した。2実行から実機のログ、トレース、Audio Client表、グラフPCMなど83,954,029バイトをRTL9210B-CGに保存した。以前のFirefoxのAudio Client表でも、既知のPIDから70区間、別のPIDから0区間を抽出できることを確認した。[初回のマニフェスト](../runs/safari-audio-client-trace-20261122-a/manifest.json)・[再実行のマニフェスト](../runs/safari-audio-client-trace-20261122-repeat/manifest.json)

Audio Clientを起動しない従来のグラフ対照も再実行した。17判定に合格し、両再生のPCMが従来のグラフ対照とビット一致した。14入力・9出力のハッシュを照合し、採取物276,988バイトを作業用ディスクに保存した。[従来経路の回帰確認](../runs/safari-process-tap-calibration-20261122-audio-client-regression/manifest.json)

```bash
# 研究ワークスペースで実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=200000000 \
  ../../.venv/bin/python tools/measure_safari_audio_client_trace.py safari-audio-client-trace-20261122-a
```

```bash
# /private/tmp で実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=200000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_safari_audio_client_trace.py \
  safari-audio-client-trace-20261122-repeat
```

次は先行音の動いている歌唱の比較にこの計時を接続し、歌唱ノードの構築・予備描画片の区間を同じエポック時計で重ねる。一括と分割の条件でI/O開始間隔・処理時間を比較し、PCMの欠落の判定は録音許可が揃ったタップの較正に引き継ぐ。
