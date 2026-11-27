# Safariの歌唱録画で停止前後の音声と映像の時刻を照合する

## 固定上流と研究版の録画経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `SingPanel.sing()` は譜面を `playTune()` に渡し、`onStart` で顔のキャンバスと `AudioEngine.recordStream()` を `Clip` に渡す。録画用の音声分岐は最初の録画時に作り、後続の録画でも共有する。Workletの `process()` は出力バッファの長さをサンプル数として `engine_render()` に渡し、結果を出力にコピーする。`Clip` は描画要求ごとに顔を720×1,280 pxのキャンバスへ描き、`captureStream(30)` の映像と音声を合わせる。MP4のH.264/AACを先に試し、対応状況に応じて候補を切り替える。`MediaRecorder.start(500)` でチャンク間隔をms単位で指定し、歌唱終了後の `stop()` で最後のデータを待ってファイルにする。描画要求と所有する映像トラックは終了時に片づける。[録画の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L157)・[音声分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L85)・[Workletの描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[Clip](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L35)

研究版は通常の「歌唱を録画」操作から `SongRecording` を作り、合成ノードを出力と録画用の `MediaStreamDestination` に接続する。録画側に振幅0の音源を足してトラックを保持する。描画のたびに `round(currentTime × 出力レート)` でContextの絶対フレームを求め、そこから歌唱予約フレームを引いて歌唱位置を得る。進捗バーの横幅は、その位置を歌唱区間内に収めて総フレーム数で割り、500 pxを掛けた値。予約を受け取った後は拍とバーをこの位置で更新する。歌唱完了後に230 ms待って録画を止め、保存用のBlobを返す。今回の変更は録画を採る入口と解析に加えた。[歌唱の録画操作](../../../../web/prototypes/chimera-research/src/main.tsx#L723)・[音声分岐の作成順](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L497)・[SongRecording](../../../../web/prototypes/chimera-research/src/song-recording.ts#L47)

```text
歌唱Worklet ─┬─ PCM・状態の出力              オフライン基準と照合
             └─ 録画用の音声トラック ─┐
Contextの時計 → 進捗バー → 映像トラック ─┴─ MediaRecorder → 音声・映像のPTS
```

上流の `output_does_not_depend_on_the_host_block_size()` は1、77、4,096、48,000サンプル単位の描画を128サンプル基準とビット照合する。`fast_runs_land_on_the_beat()` は短音の母音が拍位置に0.000001秒以内で着くことを確認する。どちらも通過した。今回の録画時刻はSafariの通常画面で測った。固定上流の同じSafariでの停止付き録画は今後の比較に残る。[上流のブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[上流の拍位置試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

## 比較条件と判定

事前登録した条件は短音「Pop Dee」、240 BPM、48 kHz出力・96 kHz内部、歯フィルタ下限1,200 Hz。連続録画と、歌唱出力28,672フレームを目標にContextを停止して120 ms後に再開する録画を、順序を反転して2組ずつ採る。各試行はページとContextを新設し、保存リンクから動画を取得する。停止中にContextのフレームが固定され、再開したときに128フレーム刻みとPCMが続くと予測した。録画が停止時間を壁時計どおり保持するなら、音声と映像は連続条件より60 ms以上延び、実測保持時間との差は70 ms以内になると事前に定めた。[事前登録](../cases/worklet-live-song-fast-safari-recording-pause.json)・[非録画での先行比較](worklet-live-song-fast-safari-mid-song-pause.md)

停止前の0.47〜0.58秒と停止後の0.65〜0.77秒を加工前PCMに合わせる。正規化相関は、候補窓と基準窓の内積を双方の二乗和の平方根の積で割る。探索範囲は−35〜500 ms、各窓の最低相関は0.75。対応した復号サンプルの番号と、音声フレームの整数PTSにトラックの時間単位を掛けてフレーム内サンプルの秒数を足した値を記録する。映像は進捗バーの中央1行から明るい画素を数え、歌唱位置24,000・34,000フレームを最初に越える2枚のPTS差を取る。停止位置から±2 pxのフレームも記録する。同じ組で停止ありと連続との差を算出する。[録画の採取](../../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs)・[解析](../tools/measure_worklet_safari_recording_pause.py)

## 実測

修正後の2実行は各70件の取得判定を通過し、計8試行の加工前PCM49,200フレーム、状態769点、歌唱計画がオフラインと一致した。停止した4試行は出力28,672で1件、28,800で3件。保持実測は120〜121 msで、停止前後の描画コールバックの間隔は136〜147 msだった。停止中にContextは同じフレーム番号に留まり、前後は128刻みだった。固定上流PCMとの差は歯フィルタ下限1,200 Hzの基準と同じで、最大 `0.002757307142019272`、差が `1e-6` を最初に超えるのは27,939フレーム。[初回修正後](../runs/worklet-live-song-fast-safari-recording-pause-20261121-b/summary.json)・[再実行](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/summary.json)

**録画音声。** 全8試行でMP4内の48 kHz AACを復号すると66,560サンプルになり、PCMはバイト単位で一致した。停止前後の窓はともに加工前PCMから5,312サンプル（110.667 ms）遅れ、相関は順に0.999999、0.999928。先頭の音声PTSは0、隣り合うPTSの差は前フレームのサンプル数を48,000で割った値と厳密に一致した。停止条件で増えたサンプルと音声時刻はいずれも0。AACを再符号化せずに取り出した場合も全試行で同じSHA-256になった。[停止試行の録画](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/artifacts/1-paused/recording.mp4)・[音声と映像のフレーム情報](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/artifacts/1-paused/recording-ffprobe.json)

**録画映像。** 停止した全4試行で、停止位置±2 pxに当たるフレームを4〜5枚ずつ確認した。最初から最後までのPTS幅は5.0〜8.3 ms。停止点を挟む2つのバー位置間の長さを連続条件から引いた値は、4組で順に+21.7、−1.7、−35.0、−3.3 msだった。壁時計の停止時間を保つ予測は音声・映像とも支持されなかった。映像PTSは連続条件でも比較位置のフレーム選択によって変わる。短い同位置フレームが生成される内部の経路は未特定。[比較の値とバーの実測](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/summary.json)

## 解析の不具合と再照合

変更前の2実行では、停止後窓を既存の累積二乗和とFFTで探すと、ほぼ無音の区間で正規化相関が2.734となった。その値が下限0.75を上回り、当初の取得判定を通過していた。振幅が大きい区間の後に累積値を引くと微小な窓の電力が桁落ちする。共有の相関関数で窓ごとの二乗和と内積を直接計算するようにし、整数PTSに時間単位を掛ける方法に切り替え、小数表示の時刻を読み取る際の丸め誤差も除いた。事前登録の窓と基準は同じ。既存の通常録画ケースで、研究版と上流の保存済みPCMの整列位置は変わらず、相関差は両窓とも0.000000001未満だった。[変更前の初回](../runs/worklet-live-song-fast-safari-recording-pause-20261121-a/summary.json)・[変更前の再実行](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat/summary.json)・[既存の通常録画](../runs/worklet-song-recording-20261120-final/summary.json)

WAVのRIFFヘッダとPCMを別の読み取りで照合した。音声PTSの連続性は、FFprobeの整数PTS差とトラックの時間単位から有理数で計算し、各フレームのサンプル数から求めた秒数と比較した。AACは `ffmpeg -v error -i recording.mp4 -map 0:a:0 -c copy -f adts pipe:1` の出力をハッシュ化した。映像のバー幅は保存したRGBを別に集計し、PTSと組み直して測定結果と照合した。既存の非録画の並列観測付き停止条件も1試行し、保存済みWAVと `cmp` で一致を確認した。[再実行の出力ハッシュ](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/manifest.json)

## 再現と保存先

`safaridriver` が利用可能なmacOSで研究ワークスペースから実行する。実行IDには未使用の名前を指定する。再実行は `/private/tmp` からPythonとスクリプトを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=90000000 ../../.venv/bin/python \
  tools/measure_worklet_safari_recording_pause.py <実行ID>
```

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、FFmpeg 7.1。4実行とも入力277件・出力52件をサイズとSHA-256で照合した。修正後の2回分10,739,818バイトと変更前の2回分10,729,463バイトをRTL9210B-CGの `voice-simulator/scratch/chimera-runs` に保存した。[修正後の初回マニフェスト](../runs/worklet-live-song-fast-safari-recording-pause-20261121-b/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/manifest.json)

次はSafariで、音声Contextの停止だけを行う条件と `MediaRecorder.pause()` だけを行う条件を短い目印付きの信号で比較する。停止前後の音声サンプルと映像PTSに加え、壁時計で描く目印とContextの時計で描く目印を同じ動画から読む。
