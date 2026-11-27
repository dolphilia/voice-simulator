# SafariでAudioContextの停止とMediaRecorderの一時停止を比べる

## 歌唱の録画経路とブラウザの時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` は、`SingPanel.sing()` が `playTune()` の開始通知を受けて `AudioEngine.recordStream()` の音声と顔のキャンバスを `Clip` に渡す。 `Clip.begin()` はキャンバスを `requestAnimationFrame()` で更新し、30 fpsのキャプチャと音声を同じMediaStreamに入れる。録画開始時に500 msのチャンク間隔を指定し、終了時に最後の通知を受けてファイル化する。歌唱経路の停止操作は歌唱を中止し、録画も破棄する。今回は2つの停止APIを個別に操作できる計測ページを使った。上流のRustの試験は、Workletが渡すサンプル数を変えてもPCMがビット一致することと、短音の母音が拍位置に着くことをそれぞれ確認している。[歌唱の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L157)・[音声の分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L85)・[Clip](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L60)・[ブロック分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[短音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

ブラウザの仕様では、AudioContextの停止中は描画の処理が止まる。MediaRecorderの一時停止は、開始済みのBlobへのデータ収集を止め、再開で収集を続ける。公開WebKitのコミット `4366e9326ff6` では、`MediaStreamAudioDestinationNode::process()` が描画中の入力をトラックへ渡す。録画側の `appendAudioSampleBuffer()` は受け取ったサンプル数をレートで割って音声時計を進める。 `appendVideoFrame()` は音声トラックがあるとき、最後にキューへ入った音声の時刻を映像に使う。同じ時刻が続くと単調増加になるよう補正する。音声トラックがない分岐は単調時計を使う。公開版の回帰テストは音声と映像を含む短いチャンクの受け渡しを検査する。このソースは動作を説明する参照で、インストール済みSafariのバイナリと同一のリビジョンかは未確認。[Web Audioの停止仕様](https://webaudio.github.io/web-audio-api/#dom-audiocontext-suspend)・[MediaRecorderの一時停止仕様](https://www.w3.org/TR/mediastream-recording/#dom-mediarecorder-pause)・[WebKitの音声分岐](https://github.com/WebKit/WebKit/blob/4366e9326ff6/Source/WebCore/Modules/webaudio/MediaStreamAudioDestinationNode.cpp#L70-L73)・[音声の時刻](https://github.com/WebKit/WebKit/blob/4366e9326ff6/Source/WebCore/platform/mediarecorder/MediaRecorderPrivateEncoder.cpp#L289-L302)・[映像の時刻](https://github.com/WebKit/WebKit/blob/4366e9326ff6/Source/WebCore/platform/mediarecorder/MediaRecorderPrivateEncoder.cpp#L420-L439)・[同一時刻の補正](https://github.com/WebKit/WebKit/blob/4366e9326ff6/Source/WebCore/platform/mediarecorder/MediaRecorderPrivateEncoder.cpp#L487-L495)・[公開回帰テスト](https://github.com/WebKit/WebKit/blob/4366e9326ff6/LayoutTests/http/wpt/mediarecorder/MediaRecorder-webm-AV-audio-video-dataavailable.html#L76-L139)

## 比較条件

前回の通常歌唱録画では120 msのAudioContext停止が録画音声の長さに表れず、進捗バーが停止位置に留まる映像だけが短いPTS間隔で残った。今回は壁時計と音声時計を同じ映像に数値として書き、停止時間は30 fpsで複数のフレームを取れる240 msに延ばした。連続条件を含む3条件を順序交代で試した。各試行の信頼済みクリックでContext・キャンバス・録画インスタンスを新設し、48 kHzの1.35秒のチャープを録音トラックへ送る。トラックはこの計測ページの `MediaStreamDestination` の既定の2チャンネルで、解析はモノラル。通常歌唱の720×1,280 pxに対し、今回の224×80 pxのキャンバスは時計を読むためのもの。MP4のH.264/AAC、30 fps、500 ms間隔の録画開始、音声末尾の230 msは前回の条件を使った。[事前登録](../cases/safari-recording-pause-clock-split.json)・[前回の通常録画](worklet-live-song-fast-safari-recording-pause.md)・[Safariの採取](../../../../web/prototypes/chimera-research/tools/capture-safari-recording-clock-split.mjs)

- 音声は、サンプル番号を48,000で割った秒数を `t` とし、`0.12 × sin(2π × (347t + 3901t² / 2))` で生成する。信号開始から0.62秒で停止を要求し、完了から240 ms後に再開を要求する。連続条件は同じ区間で両方の時計を観測する。停止前の0.30〜0.44秒と停止後の0.95〜1.09秒を、独立に計算した波形と照合する。各照合位置を復号サンプル順と整数PTSの両方で求める。前後のオフセットの差が負の場合は、その分だけ元の信号区間が詰まったことを示す。
- 映像は壁時計の経過ミリ秒と、音声開始予定位置からのContextの経過ミリ秒を、12個の白黒マスが並ぶ2行で描く。録画をフレーム単位で復号し、マス中央を読んで各描画のログに照合する。停止の境界から25 ms以上内側にある描画の枚数と最初から最後のPTS幅を記録する。

AudioContextを止めた場合は加工後の音声に時間差が増えず、映像には固定されたContext値と進む壁時計値が残り、PTS幅は120 ms以下と予測した。録画だけを一時停止した場合は停止中の映像がほぼ欠け、音声の窓間オフセットもその間に進んだContext時間に近い分だけ短くなると予測した。音声の許容差は50 ms。[測定と判定](../tools/measure_safari_recording_pause_clock_split.py)

## 実測

| 条件 | 停止中のContext時計 | 録画音声で欠けた元信号 | 録画に残った停止中の映像 |
| --- | --- | --- | --- |
| 連続 | 壁時計に沿って進行 | 0サンプル | 5〜6枚。PTS幅は約152〜183 ms |
| AudioContextだけ停止 | 同じフレームに固定 | 0サンプル | Context値が同じで壁時計値の異なる5〜6枚。PTS幅は6.7〜8.3 ms |
| MediaRecorderだけ一時停止 | 壁時計に沿って進行 | 9,216〜9,472サンプル（192.0〜197.3 ms） | 0枚 |

初回修正後と別ディレクトリからの再実行の18試行は各72件の取得判定と30件の予測を通過した。どの条件でも、隣り合うAACフレームのPTS差は各フレームのサンプル数とレートを使った値に厳密に一致した。連続とAudioContextだけ停止の計12試行の録画で、チャープ全体をそれぞれの開始位置に合わせると11試行の復号PCMがビット一致した。残る連続試行は開始オフセットが5.3 ms短く、整列後の最大絶対差は0.00832だった。録画だけを止めた条件では、Contextが進んだ時間より45.3〜48.0 ms少なく元の信号が欠けた。この差の発生位置は未特定。AudioContextだけを止めた映像では、壁時計が30 ms前後ずつ異なるフレームが映像PTSでは1.667 ms刻みで並ぶ例があった。この観測は公開WebKitの音声時計を参照する実装と整合する。その時刻がMP4の刻みに変換される位置は未計測。[初回修正後](../runs/safari-recording-pause-clock-split-20261121-b/summary.json)・[再実行](../runs/safari-recording-pause-clock-split-20261121-repeat-b/summary.json)・[停止した映像の例](../runs/safari-recording-pause-clock-split-20261121-repeat-b/artifacts/1-context/recording.mp4)

## 取得時の失敗と独立照合

最初の起動はJSON読み取り元の指定を誤り、取得前に停止した。初回の計測はSafari WebDriverのセッション開始1件が失敗し、残り8件はBlobの形式名のカンマを転送側が誤認して、動画の復号まで進めなかった。正常な動画ではコンテナの形式名だけをBlobに付け、バイナリに戻した長さも照合した。セッション開始だけを1回再試行可能にし、その事象を結果に残すようにした。ブラウザの停止条件と判定閾値は事前登録のまま。[初回の失敗](../runs/safari-recording-pause-clock-split-20261121-a/summary.json)・[初回のログ](../runs/safari-recording-pause-clock-split-20261121-a/artifacts/cargo.log)

保存動画からFFprobeの整数PTSを取り、音声の連続性をサンプル数と有理数で独立に照合した。音声の整列は、復号PCMと生成信号を窓ごとに平均二乗誤差でも比較し、相関で求めた境界との差が1サンプル以内であることを確認した。映像は縮小フィルタを通した読取りに加え、元サイズを復号して各マスの中心を直接読み、同じ値が取れることを確認した。画素書き出し側が時間単位を粗く取り直すと警告が発生したため、フィルタ側の時間単位を明示した。保存済み18本でその前後の画素がバイト単位で一致し、警告が解消した。映像PTSはFFprobeから取得している。[再実行の証跡](../runs/safari-recording-pause-clock-split-20261121-repeat-b/manifest.json)

時間単位を修正してからの追加取得は、7試行が完了した後にWebDriverがタイムアウトし、次の試行と次の実行はSafariに他のセッションが接続済みという応答で止まった。完了済み録画をハッシュ確認して再解析できる `--from-run` を追加し、保存済み9試行で72件の判定を通過した。再解析の要約は再取得時とバイト一致した。[追加取得の記録](../runs/safari-recording-pause-clock-split-20261121-c/summary.json)・[セッション開始失敗の結果](../runs/safari-recording-pause-clock-split-20261121-d/summary.json)・[再解析の結果](../runs/safari-recording-pause-clock-split-20261121-reanalysis/manifest.json)

## 再現と次の比較

Safari 18.6（20621.3.11.11.3）、macOS 15.6.1 arm64、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4、FFmpeg 7.1。固定上流のブロック分割と短音のテストも各1件通過した。研究ワークスペースで実行IDに未使用の値を指定する。再実行は `/private/tmp` からPythonとスクリプトを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=35000000 ../../.venv/bin/python \
  tools/measure_safari_recording_pause_clock_split.py <実行ID>
```

録画済みの入力から再解析する場合は、未使用の実行IDに加えて `--from-run safari-recording-pause-clock-split-20261121-repeat-b` を指定する。失敗と再解析を含む6実行の大容量出力23,662,530バイトをRTL9210B-CGに保存し、各マニフェストの入力・出力をサイズとSHA-256で照合した。

次は同じ停止操作で音声トラック付きと映像のみの録画を比較する。音声時計を選ぶ公開WebKitの分岐が、このSafariの映像PTSの違いを説明できるかを、同じ壁時計マーカーで検証する。
