# Safariの歌唱準備後に公開出力位置が進む量

## 呼び出しと観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AudioEngine.build()` のAudioWorkletが `ChimeraProcessor.process()` から `engine_render()` を呼ぶ。`Engine::render()` は出力フレームの累計を持ち、128フレーム境界で制御を進める。ブロック長の上流テストは、同じ絶対フレームで操作を適用するとPCMが一致することを確かめる。今回も通常の歌唱画面と先行音の比較を通り、合成器の出力と、それより下流のWebKitが公開する出力時刻を同じ時計で観測する。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

公開WebKitでは、GPUのI/Oスレッドが要求ごとにフレーム累計 `F` を増やす。WebContent側の `RemoteAudioDestinationProxy` はMach待機を抜けるたびに、その回の処理量を `F − 前回のF` として求める。`renderAudio()` は最大4,096フレームずつFIFOから出力を取り出して共有リングへ書く。書き込み開始位置 `m_currentFrame` を出力レートで割った秒数と、その開始時のホスト時刻を描画に渡す。公開版のFIFOは要求に足りないサンプルを無音で埋める。[GPUの累計更新](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L179-L208)・[累計の差分と書き込み](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L88-L109)・[区切りの上限](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L51-L56)・[出力時刻の起点](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L224-L251)・[FIFOの無音埋め](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/PushPullFIFO.cpp#L82-L125)

`AudioDestinationResampler` がその時刻をグラフへ渡す。`BaseAudioContext::handlePreRenderTasks()` が描画前にロックを取れたときに `m_outputPosition` を更新し、メインスレッドの `AudioContext::getOutputTimestamp()` は出力位置とホスト時刻を返す。`contextTime` は公開時に `currentTime` 以下へ切り詰められ、`performanceTime` はクロックの精度が落とされる。今回は `getOutputTimestamp()` の前後に `currentTime` を採った。両方のグラフ位置より小さい公開位置を採用すると、読解した実装の切り詰めから独立した位置差を計算できる。`performanceTime + performance.timeOrigin` をエポック時刻に変換し、WebContentのSystem Call Trace、ブラウザ側の準備時刻、先行音の量子を対応づける。読み飛ばした公開更新、共有リング内の波形、音声機器のPCMは別に扱う。[リサンプラーの時刻受け渡し](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/AudioDestinationResampler.cpp#L109-L143)・[グラフへの位置公開](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/Modules/webaudio/BaseAudioContext.cpp#L603-L626)・[公開APIの実装](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/Modules/webaudio/AudioContext.cpp#L220-L234)・[事前登録](../cases/worklet-safari-song-output-position.json)

## 実測

Safariの通常の歌唱画面で、16,384フレームの予備描画を一括と67片への分割で各2回実行した。プロセスを絞ったSystem Call Traceには全試行で描画スレッドとWorkletが現れた。先行PCM各229,376サンプル、歌唱PCM各31,200サンプル、声門などの各488観測点は基準に一致した。今回の先行音の最大間隔は一括144・142 ms、分割7・11 msだった。公開時刻を採らなかった以前の2組では一括139・141 ms、分割7・7 msだった。[採取1](../runs/worklet-safari-song-output-position-20261122-a/summary.json)・[採取2](../runs/worklet-safari-song-output-position-20261122-repeat/summary.json)・[以前のグラフとの比較値](../runs/worklet-safari-song-output-position-20261122-publications/summary.json)

全試行で構築前・準備・準備後を観測した。取得点の最大間隔は各窓9 ms以下、取得前後に記録された時刻差は最大1 msだった。一方、取得前後のグラフ位置をともに下回り、時刻が更新された連続点は基準窓で順に8・1・0・0組だった。当初の基準4組を満たしたのは初回の一括のみで、その試行では準備終了付近の切り詰めのない連続点から4,096フレームの差を読み取れた。分割2試行では準備と準備後の全取得点でグラフ位置による制約を除けず、分割の最大差および両条件の倍率を未判定として保存した。[当初の取得点判定](../runs/worklet-safari-song-output-position-20261122-analysis/summary.json)

取得した `performanceTime` が同じ値で続く点をまとめ、その中で切り詰めのない出力位置がすべて一致した場合だけ、位置を採用し直した。両端の位置を採用できた隣接グループでは、順序を反転した一括2試行とも4,096フレーム進んだ。公開時刻の差は11 msと10 msだった。一括の準備中は公開位置と時刻が同時に約136 ms据え置かれ、分割では1 msと5 msだった。分割に対応する切り詰めのない差は補助解析でも欠測した。[公開時刻のグループを使った判定](../runs/worklet-safari-song-output-position-20261122-alignment/summary.json)

| 一括試行 | 進んだ公開位置（フレーム） | 二つの公開時刻の差 | その間のMach待機完了 | その間のWorkletの先行音量子 |
| --- | ---: | ---: | ---: | ---: |
| 研究ワークスペース | 124,416 → 128,512 | 11 ms | 1件 | 33件 |
| `/private/tmp` | 108,928 → 113,024 | 10 ms | 1件 | 32件 |

4,096フレームは128フレーム量子の32個分であり、公開版の一回の書き込み上限と同じ値だった。表は記録された時刻で区切った件数で、区間の両端を最大1 ms前後させると、Workletはそれぞれ8〜34件と30〜33件になる。Mach待機完了はどちらの区間でも1件で、先頭の公開時刻から1.650 msと1.078 ms後に記録された。公開位置の差と同じ区間に複数の量子を観測できた。共有リングへの個別の書き込み、無音補完の量、出力側のPCMは未測定である。[2組の時刻照合](../runs/worklet-safari-song-output-position-20261122-alignment/summary.json)

## 実行と保存

macOS 15.6.1（arm64）、Safari 18.6、xctrace 26.0（17C52）、Bun 1.4.4、Node.js 24.19.0、Rust 1.94.1、Python 3.14.4で実行した。48 kHzの歌唱は同じ入力・予備描画量で採取順だけを反転した。タイマーは2 ms間隔を要求し、取得前後の時刻を保存した。出力位置は生の取得点から秒をフレームへ変換し直し、先行音のコールバック件数も生の時刻から数え直した。

研究ワークスペースから実行する。実行IDには未使用の値を指定する。2組目の採取には `--reverse` を加え、別ディレクトリから起動するときはPython・スクリプト・ケースを絶対パスで指定する。元の判定を再現する場合は、別の実行IDで解析を行い `--publication-groups` を外す。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_audio_client.py worklet-safari-song-output-position-example-a \
  --case cases/worklet-safari-song-output-position.json

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_safari_output_positions.py worklet-safari-song-output-position-example-analysis \
  worklet-safari-song-output-position-20261122-a \
  worklet-safari-song-output-position-20261122-repeat --publication-groups
```

採取2回は各31判定に合格し、当初の解析は20判定中3件が未達だった。補助解析2回は各18判定に合格した。当初の判定と生の観測データを保存し、全5実行の計1,573入力・400出力をサイズとSHA-256で照合した。採取物の実体71,412,812バイトはRTL9210B-CGに置いた。固定上流の `output_does_not_depend_on_the_host_block_size` も通過した。[採取1](../runs/worklet-safari-song-output-position-20261122-a/manifest.json)・[採取2](../runs/worklet-safari-song-output-position-20261122-repeat/manifest.json)・[当初の解析](../runs/worklet-safari-song-output-position-20261122-analysis/manifest.json)・[公開時刻別の補助解析](../runs/worklet-safari-song-output-position-20261122-publications/manifest.json)・[時刻照合を追加した解析](../runs/worklet-safari-song-output-position-20261122-alignment/manifest.json)
