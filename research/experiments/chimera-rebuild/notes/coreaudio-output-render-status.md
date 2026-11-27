# Audio Clientで出力コールバックの戻り値を観測できるか

## 呼び出しと観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では `AudioEngine.build()` がWorkletを出力に接続し、`ChimeraProcessor.process()` が要求フレーム数をWASMの `engine_render()` に渡してfloat32の出力を作る。`Engine::render()` は絶対フレーム位置を保持し、128フレーム境界で予定を更新してから次のブロックを生成する。ホストの要求長を変えても操作位置が同じならPCMが一致することを固定上流テストで確認している。このPCMより後の機器側への受け渡しを音声クライアントで調べる。[上流の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[描画ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

公開WebKitの `AudioOutputUnitAdaptor::inputProc()` は機器のサンプル時刻、ホスト時刻、要求フレーム数、書き込み先を渡し、描画の `OSStatus` をAudioUnitへ返す。GPUプロセスの `RemoteAudioDestination::render()` は、読み出し位置を `r`、要求長を `N`、リングの有効範囲を半開区間 `[s,e)` とすると、`s ≤ r` かつ `r + N ≤ e` のときだけPCMを取り出して `r += N` する。その後、成功・不足のどちらでも要求累計に `N` を加えてWeb側に通知する。Web側の `RemoteAudioDestinationProxy` はその累計と前回値の差を取り、`pullRendered()`、共有リングへの書き込み、次の描画要求、書き込み位置の加算の順に処理する。公開テストは `CARingBuffer` の有効範囲、PCMコピー、周回時の古い範囲の更新などを検査する。[AudioUnitのアダプター](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/cocoa/AudioOutputUnitAdaptor.cpp#L61-L73)・[GPU側](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L179-L208)・[読み出し条件](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/cocoa/CARingBuffer.cpp#L252-L259)・[Web側の書き込み](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L226-L251)・[リングの公開テスト](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Tools/TestWebKitAPI/Tests/WebCore/CARingBufferTest.cpp#L102-L156)

公開修正 `c315a7167580` の前は、リング不足のときに出力配列をそのままにして `-1` を返す実装だった。修正後は最初の不足で最後の出力値から無音へ下げ、さらに不足が続けば無音を書いて `-1` を返す。いずれでも要求累計は進む。この変化から、不足時の波形とコールバックの開始間隔を独立に考える必要がある。試験機ではSafariとWebKitのバンドル版 `20621.3.11.11.3` を取得したが、公開版との厳密な対応は未確定である。[修正前](https://github.com/WebKit/WebKit/blob/5f7ab40afc2d8c7dd20253955edbe834a91db32e/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L184-L201)・[公開修正](https://github.com/WebKit/WebKit/commit/c315a716758008c2e11d996fe2e663db6097d114)

対照実験では、既存のSwift製の出力用AudioUnitを48 kHzで動かす。両条件で同じPCMを書き、処理の待機を入れず、比較の16要求だけ `-1` を返す。PCMの値はサンプル番号 `n` から `(((421*n + 173) mod 65521) - 32760) / 8388608` で作り、右は左と逆相とする。機器のサンプル時刻の差から前回要求長を引き、サンプルの時刻飛びを別に求める。Audio Clientの開始時刻、I/O処理、負荷、注目点の表を保存する。戻り値だけを変えたときにI/O時計と表に何が現れるかを較正し、その結果をSafari歌唱の保存済みトレースを読む際に使う。[事前登録](../cases/coreaudio-output-render-status.json)・[既存の出力対照](worklet-live-song-output-pcm.md)・[AppleのAudio Client解説](https://developer.apple.com/documentation/audiotoolbox/analyzing-audio-performance-with-instruments)

## 採取を始める手順

予備試行で `xctrace record --launch` を使うと、制限時刻までに対照のJSONが書かれず、目次に対象の終了理由 `SIGKILL` が残った。AudioUnitを初期化した子プロセスを標準入力で待機させ、先にそのPIDへアタッチする方法に切り替えた。Darwinの記録開始通知を受けたところで1バイトを渡して再生を始める。再生直前に `mach_absolute_time` で挟んだエポック時刻を保存し、ネイティブとxctraceの時計を対応づける。各コールバックの開始を含むI/O区間を前後1.5 msの幅で照合する。予備試行のトレースと直接起動の対照は作業用ディスクに保存した。[予備試行の目次](/Volumes/RTL9210B-CG/voice-simulator/scratch/coreaudio-status-pilot.AiR2lIoj/toc.xml)・[採取と時刻の照合](../tools/measure_coreaudio_output_render_status.py)

## 実測

3実行の6試行で、既定出力は48 kHz・1要求512フレームだった。エラー条件では1試行あたり16要求、8,192フレーム相当の処理が `-1` を返した。試行ごとにエラー窓の前後を含む32要求、計192要求をAudio ClientのI/O区間へ一意に照合した。ネイティブ記録から独立に差し引いた機器のサンプル時刻の飛びは0フレームだった。ネイティブでの開始間隔の最大値は、各試行内の中央値の1.040〜1.113倍で、登録した1.25倍以下を満たした。エラー窓のI/Oサイクルと `IOProc` は各16件で、注目点は0件だった。負荷表も通常という表示で、4表に戻り値の列やエラー時に固有のイベントは見つからなかった。機器へ実際に渡ったPCMは未測定である。[初回の結果](../runs/coreaudio-output-render-status-20261122-a/summary.json)・[反転順の結果](../runs/coreaudio-output-render-status-20261122-repeat/summary.json)・[保存窓の再集計を加えた実行](../runs/coreaudio-output-render-status-20261122-archive-audit/summary.json)

保存済みSafariの一括条件1試行からAudio Clientの4表を再出力すると、準備窓には通常のI/Oサイクル54件と `IOProc` 54件があり、注目点は0件だった。全収録範囲には `Cycle; Overload` が2件あった。前回の集計は説明が `Cycle` と完全一致する行を読んでいたので、8試行の保存済みサイクル表に対して付記込みでも集計した。6試行に合計12件があり、いずれも準備開始の約225〜272 ms前だった。基準・準備・準備後の全24窓では付記を含めても最大間隔の値が一致した。Audio Clientが表示する `Overload` と、WebKitが共有リングの不足時に返す `-1` は、それぞれを直接観測して照合する必要がある。[Safariの4表と全試行の再集計](../runs/coreaudio-output-render-status-20261122-archive-audit/summary.json)

以前の14 ms待機条件は従来のCLI引数で再実行した。待機した要求の次の機器サンプル時刻だけが512フレーム飛び、待機なしの対照は連続した。固定上流のブロック長独立試験も通過した。今回の `-1` を返す条件ではそのような時刻飛びは生じなかった。[待機条件の回帰](../runs/worklet-live-song-output-deadline-20261122-render-status-regression/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Swift 6.2.3、xctrace 26.0（17C52）、Python 3.14.4を使用した。最初はネイティブ対照、反転順では保存済みSafariの4表の再出力を加えた。予測と比較窓を維持し、最後に8試行の保存窓を再集計する処理を加えた。3実行の16・17・18判定と2予測ずつが成立し、従来の待機条件の8判定も通過した。4実行の計201入力・585出力をサイズとSHA-256で照合した。採取物124,435,338バイトはRTL9210B-CGに実体を置き、ローカルにはマニフェスト、要約、ソースのスナップショットと採取物へのリンクを残した。[初回](../runs/coreaudio-output-render-status-20261122-a/manifest.json)・[反転順](../runs/coreaudio-output-render-status-20261122-repeat/manifest.json)・[全保存窓の再集計](../runs/coreaudio-output-render-status-20261122-archive-audit/manifest.json)

```bash
# 研究ワークスペースで実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=180000000 \
  ../../.venv/bin/python tools/measure_coreaudio_output_render_status.py \
  coreaudio-output-render-status-20261122-archive-audit
```

```bash
# /private/tmp で順序を反転して実行する場合は新しい実行IDを指定
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=180000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_coreaudio_output_render_status.py \
  coreaudio-output-render-status-local-reverse --reverse
```
