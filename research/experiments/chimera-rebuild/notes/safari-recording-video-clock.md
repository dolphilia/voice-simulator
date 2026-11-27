# Safariの録画に音声を含めると映像の停止区間が縮むか

## 固定上流と公開WebKitでの時刻の受け渡し

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `SingPanel.sing()` は、`playTune()` の開始通知で `AudioEngine.recordStream()` と画面の顔キャンバスを `Clip` に渡す。 `AudioEngine.recordStream()` はマスター出力を録画用の音声トラックにも分岐する。 `Clip.begin()` は顔のキャンバスを描画し、そのコピーから30 fpsで採る映像トラックと音声トラックを同じ `MediaRecorder` に入れる。 `rec.start(500)` の500 msはBlob通知の間隔。上流の `Worklet.process()` は描画要求に応じてWASMからPCMを受け取る。上流のブロック長試験と短音の拍位置試験はそれぞれPCMの連続性と歌唱計画を扱う。動画のPTSはブラウザで別途測った。[歌唱の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L162)・[音声分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L85)・[Clip](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L60)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[拍位置の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

公開WebKitのコミット `4366e9326ff6` では `MediaRecorderPrivateEncoder::appendAudioSampleBuffer()` が受け取ったサンプル数をレートで割って音声の時刻を進める。 `appendVideoFrame()` は、音声付きならキューに最後に入った音声の時刻、映像のみなら単調時計の経過から映像の時刻を決める。同じ時刻が連続した場合は単調増加になるよう補正する。同コミットのWebM回帰テストは、短い録画チャンクから音声・映像を受け取り再生できることを確認する。今回のH.264/MP4での停止時刻の比較は、そのコードから得た予測をSafariで検証したもの。インストール済みSafariと公開版のソースの厳密な対応は未確認。[公開コードの音声時刻](https://github.com/WebKit/WebKit/blob/4366e9326ff6/Source/WebCore/platform/mediarecorder/MediaRecorderPrivateEncoder.cpp#L289-L302)・[映像時刻の分岐と補正](https://github.com/WebKit/WebKit/blob/4366e9326ff6/Source/WebCore/platform/mediarecorder/MediaRecorderPrivateEncoder.cpp#L420-L497)・[WebKitの回帰テスト](https://github.com/WebKit/WebKit/blob/4366e9326ff6/LayoutTests/http/wpt/mediarecorder/MediaRecorder-webm-AV-audio-video-dataavailable.html#L79-L139)

## 事前登録と計測

前回と同じ48 kHz・1.35秒のチャープを使い、開始から0.62秒付近で `AudioContext.suspend()` を呼び、完了から240 ms後に再開を要求する。両条件で同じ音声グラフを作り、録画に渡す `MediaStream` から音声トラックを外すかだけを変える。キャンバスの大きさは224×80 px、30 fps。上下の2行に、`performance.now()` から計算した経過ミリ秒と、音声の開始予定からのContextミリ秒を白黒のマスで描く。順序を反転した2組を取得し、別ディレクトリから再実行した。両条件で同じH.264/AACの形式を要求でき、映像のみではSafariがAACを除いた形式を返した。事前に許容した形式の再指定は発生しなかった。[登録ケース](../cases/safari-recording-video-clock.json)・[前回の条件](safari-recording-pause-clock-split.md)・[計測ページ](../../../../web/prototypes/chimera-research/tools/capture-safari-recording-clock-split.mjs)

停止の両端25 msを除いた区間に描かれた最初と最後の録画フレームを選び、2枚のマーカーが表す壁時計差と、MP4の表示時刻（PTS）の差を求める。壁時計幅は100 ms以上を取得条件にした。音声付きのPTS幅は50 ms以下、映像のみでは壁時計幅との差が35 ms以内、組ごとの差は90 ms以上と予測した。音声付きはチャープの停止前後を復号後PCMに照合し、サンプル順とPTSの両方で窓間オフセットの変化を求めた。[解析](../tools/measure_safari_recording_video_clock.py)・[音声と映像の共通解析](../tools/measure_safari_recording_pause_clock_split.py)

## 実測

2回の実行で各42件の取得判定と8件の予測が通過した。8試行で停止完了から再開要求までの240〜242 msの間、Contextの絶対フレーム番号は同じ値に留まった。停止中に描いた映像は、境界を除いた集計でどちらも5〜6枚残った。

| 録画トラック | 同じ2枚が示す壁時計幅 | 録画ファイル上のPTS幅 |
| --- | --- | --- |
| 音声と映像 | 134〜183 ms | 6.7〜8.3 ms |
| 映像のみ | 131〜168 ms | 131.7〜166.7 ms |

映像のみでは、各試行の壁時計幅とPTS幅の差は最大1.34 ms。音声付きとの差は4組で123.3〜160.0 msだった。停止前の最後と停止後の最初のフレームで比較しても、音声付きのPTS幅は壁時計幅より238.3〜258.7 ms短く、映像のみの差は最大1.34 msだった。音声付きの4試行は停止前後で復号サンプル順のオフセット変化が0サンプル。各AACフレームのPTS差はサンプル数を48,000で割った値と厳密に一致した。[初回の結果](../runs/safari-recording-video-clock-20261121-a/summary.json)・[再実行の結果](../runs/safari-recording-video-clock-20261121-repeat/summary.json)

別の読み取りで、縮小フィルタを通さず元の画素のマス中央を読み、FFprobeの整数PTSに時間単位を掛けた有理数から区間幅を再計算した。8本すべての映像はH.264 Constrained Baseline、yuv420p、224×80 px、時刻単位1/600秒で一致した。生成したチャープのSHA-256も8試行で同じだった。今回の取得に欠測はなかった。共通解析の変更後に前回の9録画を再解析し、保存済みの要約とのバイト一致も確認した。固定上流のブロック長と拍位置の試験は各1件通過した。[今回の再実行](../runs/safari-recording-video-clock-20261121-repeat/manifest.json)・[前回の回帰確認](../runs/safari-recording-pause-clock-split-20261121-video-clock-regression/manifest.json)

この計測では、追加した音声トラックの有無によって映像PTSの進み方が変わった。音声付きの録画で、停止中に続いていた壁時計の表示が数ミリ秒に収まる現象は、公開WebKitの時計選択と整合する。歌唱が続く通常録画で研究版と固定上流に同じ停止を入れた比較、他ブラウザ、音声入力と独立した映像時計での録画は残っている。

## 再現と保存先

Safari 18.6（20621.3.11.11.3）、macOS 15.6.1 arm64、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4、FFmpeg 7.1。研究ワークスペースから未使用の実行IDを指定する。再実行は `/private/tmp` からPythonとスクリプトを絶対パスで指定した。各12件の入力と25件の出力のハッシュとサイズを確認し、比較2回の4,262,758バイトをRTL9210B-CGに保存した。[初回のマニフェスト](../runs/safari-recording-video-clock-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/safari-recording-video-clock-20261121-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python \
  tools/measure_safari_recording_video_clock.py <実行ID>
```

次は固定上流の通常の歌唱録画に短い停止を入れ、研究版の通常歌唱録画と比較する。 `SingPanel` の開始通知から `Clip` とWorkletのContextをたどり、元の計測にある120 msの停止前後で、合成PCMと動画のPTSを照合する。
