# Safariの歌唱準備とCore AudioのI/O時刻を照合する

## 呼び出しと観測区間

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` は `AudioContext` を作り、WASMを渡した `AudioWorkletNode` を出力につなぐ。上流の `ChimeraProcessor.process()` は要求されたフレーム数を `engine_render()` に渡し、float32 PCMを出力チャンネルに書く。`Engine::render()` は出力フレーム位置を保持して128フレーム境界で予定を更新する。上流のブロック長試験では、操作を同じフレームに置いたときにさまざまなブロック長のPCMがビット一致することを確認する。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[上流の描画ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流のブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版では `Handle::advance_score_preparation()` が、同じハンドル上で声門・声道を進め、放射の体積流量の時間微分（cm³/s²）を出力段に渡す。処理した出力フレーム数を残量から引き、残量が0になったところで譜面のジェスチャーを予約する。一括ではWorklet構築中に16,384フレームを進め、分割の `FixedProcessor.process()` では最初の64フレーム4片の後に256フレーム63片を進める。比較する歌唱の設定、譜面、準備総量はそろえる。[事前登録](../cases/worklet-safari-song-audio-client.json)・[WASMの予備描画](../crates/vocal-wasm/src/lib.rs#L1057)・[Workletの準備](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L169)

先行信号を同じContextで流し、48量子を受け取った時点で歌唱ノードの生成を保留する。開始前に出力していなかったWebKitのCore Audioプロセスのうち、先行信号の開始後に出力が有効になったプロセスを一意に選ぶ。Audio ClientをそのPIDに付け、Darwinの記録開始通知から200 ms後に生成を再開する。試験音の較正では同じ計測点で停止中0件、再生中770・771件のI/Oサイクルを確認済みである。先行信号の照合では、開始からのサンプル番号 `n` に対して `(((421*n + 173) mod 65521) - 32760) / 524288` をfloat32に丸めた値を独立に計算する。[先行信号の照合](../tools/measure_worklet_safari_song_prepared_shared_context.py#L26)・[試験音の較正](safari-audio-client-trace.md)・[AppleのAudio Client解説](https://developer.apple.com/documentation/audiotoolbox/analyzing-audio-performance-with-instruments)

比較は、構築開始の前90〜10 ms、構築開始から最後の準備完了まで、完了後10〜90 msの3窓とした。先行信号と歌唱Workletは `Date.now()` でミリ秒を記録する。Audio Client表の開始時刻はトレース開始からのナノ秒なので、目次の開始エポック時刻を基準に窓を対応づける。GPU側は各窓に重なる開始間隔と、その窓内で始まったコールバックの処理時間を別々に集計する。公開WebKitではGPU側が共有リングバッファからPCMを読み出す経路があり、I/O開始間隔が連続しても読み出されたPCMの連続は別に測る必要がある。[解析器](../tools/measure_worklet_safari_song_audio_client.py)・[公開WebKitのPCM読み出し](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L172-L192)

## 実測

Safariの実時間歌唱画面で `Pop Dee` を48 kHzで実行した。2実行でペア内の順を反転して、各2ペアを採取した。構築から準備完了までは一括140〜145 ms、分割181〜183 msだった。構築を挟む準備窓のグラフの最大間隔は、分割で各ペア135〜141 ms短縮した。ペア中央値は初回136.5 ms、再実行138 msで、登録した70 ms以上を両回で満たした。[初回の要約](../runs/worklet-safari-song-audio-client-20261122-a/summary.json)・[反転順の要約](../runs/worklet-safari-song-audio-client-20261122-repeat/summary.json)

| 準備窓の観測値（各条件4試行の範囲） | 一括 | 分割 |
| --- | ---: | ---: |
| Safariの先行信号の最大コールバック間隔 | 143〜148 ms | 6〜10 ms |
| GPUのI/O開始間隔の最大値 | 2.678〜2.698 ms | 2.680〜2.689 ms |
| GPUのI/O処理時間の中央値 | 4.25〜4.85 µs | 5.52〜6.38 µs |
| GPUのI/O処理時間の最大値 | 11.00〜16.33 µs | 13.75〜16.00 µs |

準備窓では各試行54〜70個のI/O開始間隔を得た。全試行で中央値は2.6659〜2.6666 ms。基準窓での最大値は2.676〜2.689 ms、準備後の窓では2.678〜2.687 msだった。準備窓の最大値の条件別中央値は両実行で2.682〜2.688 msで、登録した10 ms以下を満たした。一括の4試行では準備窓内に先行信号のコールバックが0件だった。この窓に対応するGPU側のI/O時刻には、グラフ側と同程度の中断は現れなかった。[初回の要約](../runs/worklet-safari-song-audio-client-20261122-a/summary.json)・[反転順の要約](../runs/worklet-safari-song-audio-client-20261122-repeat/summary.json)

後続の再集計で、最初の集計が使った `Cycle` に `Cycle; Overload` を加えて全24窓を照合した。付記のある12件は6試行の準備開始約225〜272 ms前にあり、全24窓の最大開始間隔は変わらなかった。[エラー対照と再集計](coreaudio-output-render-status.md#実測)

全8試行で、先行信号の各229,376サンプルは独立計算に、歌唱の各31,200サンプルは予備描画16,384フレームのSafari保存基準にビット一致した。声門・放射などの各488点も一致した。分割の4試行で予定どおり67片と準備完了後の歌唱予約を確認した。計測したI/Oの開始時刻は、公開WebKitのGPU側で共有リングから取り出したPCMや機器出力の連続性までは示さない。Safariの試験音で記録したmacOSの録音許可待ちが残っており、今回の歌唱で出力側のサンプル欠落・繰り返し・無音と聴感は未判定である。[基準との照合](../tools/measure_worklet_safari_song_audio_client.py)・[試験音での録音許可待ち](safari-process-tap-calibration.md#実測)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、xctrace 26.0（17C52）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。Safariに追跡の保留を加えるのは `audio_client_trace` を指定した場合だけである。2実行とも70判定と2予測が成立し、各276入力・374出力のサイズとSHA-256を照合した。両実行のケース・WASM・WAV・先行PCMの17ファイルが一致し、保存済みのAudio Client表から8試行の3窓すべてを再集計して同じ結果を得た。実体173,769,470バイトをRTL9210B-CGに保存した。このうち159,043,588バイトがxctraceのトレースで、ローカルにはマニフェスト、要約、ソースのスナップショットと採取物へのリンクを残した。[初回のマニフェスト](../runs/worklet-safari-song-audio-client-20261122-a/manifest.json)・[反転順のマニフェスト](../runs/worklet-safari-song-audio-client-20261122-repeat/manifest.json)

従来の計時なしの経路を確認した最初の8試行は、WebDriverのクリック後にページへ押下イベントが届かず、全試行が開始前にタイムアウトした。ボタンの押下が800 ms以内に観測できない場合に同じボタンをSpaceで押す処理を、従来の経路でも使うようにした。再実行は80判定と2予測を通過し、以前の従来経路とWASM・歌唱WAV・先行PCMの17ファイルがビット一致した。失敗時の36出力と再実行の84出力、各273入力をハッシュ照合した。両回の採取物計7,120,094バイトは同じ作業用ディスクに置いた。固定上流の `output_does_not_depend_on_the_host_block_size` も通過した。[タイムアウトした回帰実行](../runs/worklet-safari-song-prepared-shared-context-20261122-audio-client-regression/manifest.json)・[回帰の再実行](../runs/worklet-safari-song-prepared-shared-context-20261122-audio-client-regression-retry/manifest.json)

```bash
# 研究ワークスペースで実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=600000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_audio_client.py \
  worklet-safari-song-audio-client-20261122-a
```

```bash
# /private/tmp で実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=600000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_worklet_safari_song_audio_client.py \
  worklet-safari-song-audio-client-20261122-repeat --reverse
```

```bash
# 研究ワークスペースで従来経路を確認
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_prepared_shared_context.py \
  worklet-safari-song-prepared-shared-context-20261122-audio-client-regression-retry
```
