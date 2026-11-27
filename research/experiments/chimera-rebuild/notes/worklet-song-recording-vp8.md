# 歌唱録画のVP8/Opus選択

## 読解と事前登録

固定上流の `SingActions` は `playTune` の開始フックで `Clip` を作る。フックはスコアを送る直前に呼ばれ、開始前に中止した場合は呼ばれない。 `AudioEngine.recordStream` は音声マスターから収録用の音声を分岐する。 `Clip.begin` は顔のキャンバスを720×1280の録画用キャンバスへ縦横比を保って描き、`captureStream(30)` の映像と音声を `MediaRecorder` に渡す。映像の要求は5,000,000 bit/s、塊の受け取りは500 ms間隔。完走は最後の `dataavailable` と `stop` を待って蓄積した塊を連結する。中止は所有する映像トラックを終了し、エンジンの共有音声トラックを次の収録に残す。開始フックの単体試験と、実ブラウザ上の `Clip` の完走・中止を確認する。[歌唱画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L165)・[歌唱の予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[音声の分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L85)・[形式と収録](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts)・[開始フックの試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L195)

`pickType` と候補の `songRecordingType` は `MediaRecorder.isTypeSupported` が真になった最初の形式を返す。問い合わせ順は、H.264/AACを明示したMP4、コンテナだけのMP4、VP9/Opus、VP8/Opus、コンテナだけのWebM。候補の録画も48 kHzの音声と720×1280・30 fpsのキャンバスを使い、描画時の `AudioContext.currentTime` に48,000を掛けて丸め、歌唱開始のContextフレームを引いて現在の出力時刻を得る。閉鎖と母音の断面および32ビットの識別欄は、採取済み測定線の同一フレームから描く。候補は専有する音声と映像を両方終了する。[候補の形式・描画・停止](../../../../web/prototypes/chimera-research/src/song-recording.ts)・[断面と識別欄](../../../../web/prototypes/chimera-research/src/recorded-tract.ts)

登録した条件は、同じChromiumでMP4の二つとVP9/Opusの対応結果を偽にすること。候補と上流には同じ拒否条件を適用する。ほかの形式は実ブラウザに問い合わせ、生成したファイルをEBMLヘッダー、ffprobe、ブラウザの再生で確認する。二拍の `Pop Dee`、出力48 kHz、固定VP9対照と同じ加工前PCM全91,200フレームを使う。拍の音声整列誤差は85 ms、固定VP9からの変化も85 ms以内と予測する。映像の最大PTS間隔は170 ms、二つの唇閉鎖と二つの母音の復号輪郭は独立投影に対して95パーセンタイル距離5.5 px以下。これらの閾値とOpusの復号時刻・音声の前後の無音条件は先行の録画ケースと共通にする。[事前登録](../cases/worklet-song-recording-vp8.json)・[時刻と音声の基準](../cases/worklet-song-recording.json)・[輪郭と4区間の基準](../cases/worklet-song-tract-recording.json)・[固定VP9の結果](../runs/worklet-song-webm-20261120-c/summary.json)

## 初回と描画時刻の切り分け

既存の計測に `--vp8` を追加した。候補の歌唱画面と固定上流の `Clip` を別々に開き、指定されたMIME型の問い合わせに限り試験ページで拒否を返す。最初から最後まで各問い合わせの順を記録し、`MediaRecorder` に実際に渡された型と復号されたコーデックを確認する。固定VP9のマニフェストと、そこに記録されたWAVと判定データのハッシュを照合してから比較に使う。候補の歌唱・録画の実装は従来の入口を使う。[収録と復号の入口](../tools/measure_worklet_song_recording.py)・[MIME型と復号の検証](../tools/measure_webm_recording.py)・[ブラウザの採取](../../../../web/prototypes/chimera-research/tools/capture-song-recording.mjs)

従来と同じPlaywrightのChromium 156.0.8078.4とSwiftShaderで、VP9対照の再計測は45項目中8項目が基準外だった。映像の空白が候補で202 ms（PTS 0.874〜1.076秒）、固定上流で900 ms（0.677〜1.577秒）。候補の作画時刻にも200 msの空白があった。その環境の最初のVP8試行では候補の全観測が基準内だった。候補は29.06 fps、最大映像間隔65 ms、復号した断面56時点で輪郭差は最大3.891 px。固定上流はVP8/Opusを選んでおり、復号音声の時刻誤差は3 msだったが、映像はPTS 0.579〜2.093秒の1.514秒間にフレームがなく、第1拍が欠測になった。[VP9対照の再計測](../runs/worklet-song-vp9-reference-20261120/summary.json)・[VP8の初回](../runs/worklet-song-vp8-20261120-a/summary.json)・[固定上流の復号時刻](../runs/worklet-song-vp8-20261120-a/artifacts/upstream-clip-ffprobe.json)

次のVP8試行では、固定上流の `Clip` が取り込むキャンバスへの `drawImage` 直後に、AudioContextのフレーム番号と単調時計を記録した。上流の復号映像の空白はPTS 0.804〜1.516秒で712 ms。これに重なる録画開始から0.853〜1.515秒の間は、実際の作画にも661 msの空白があった。候補でも、作画に約253 msの空白があり、同じ区間で復号映像の空白が255 msになった。この試行では、録画に渡すキャンバスの作画段階ですでに間隔が延びていた。最大作画間隔と該当区間はマニフェストから参照できる復号・描画の記録に残した。[再試行の判定](../runs/worklet-song-vp8-20261120-b/summary.json)・[固定上流の作画時刻](../runs/worklet-song-vp8-20261120-b/artifacts/recording-browser.json)・[候補の作画時刻](../runs/worklet-song-vp8-20261120-b/artifacts/recorded-input.json)

## Chromeでの実測

インストール済みのChrome 157.0.8103.79にも同じ計測を適用した。通常のヘッドレス起動とブラウザ既定の描画設定を使い、両実装の条件をそろえた。最初の試行は最大映像間隔が候補261 ms、固定上流180 msで、48項目中のこの2項目が基準外。再試行では48項目すべてに合格した。候補では形式の完全な問い合わせ順を16回、上流では3回観測した。どちらも最初の三つの形式が拒否された後にVP8/Opusを選び、EBMLのDocTypeはWebMだった。候補はブラウザ内で動画を再生でき、準備中と録画中の中止および再録画も確認した。[Chromeの初回](../runs/worklet-song-vp8-20261120-chrome/summary.json)・[全項目通過の実行](../runs/worklet-song-vp8-20261120-chrome-repeat/summary.json)・[問い合わせと録画状態の記録](../runs/worklet-song-vp8-20261120-chrome-repeat/artifacts/recording-browser.json)

| 観測値 | 候補 | 固定上流の `Clip` |
| --- | ---: | ---: |
| 復号映像のフレーム数・実効fps | 66・29.94 | 68・29.98 |
| 映像の最大PTS間隔 | 37 ms | 35 ms |
| 整列した音声の第1拍・第2拍に対する映像の時差 | −23.2・−23.2 ms | −25.5・−24.5 ms |
| 固定VP9対照からの拍時差の最大変化 | 7.34 ms未満 | 3.01 ms未満 |
| 復号音声PTSと累積サンプル数による時刻の最大差 | 4 ms | 2 ms |

候補の加工前PCMは全91,200フレームでCLIとビット一致し、固定VP9・MP4のWAVとハッシュが一致した。候補の119時点の保存格子から、映像の識別欄で58種類の出力フレームを復元し、二つの唇閉鎖・二つの母音を個別に比較した。独立投影した輪郭との95パーセンタイル距離は全画像で最大3.963 px、識別した断面の時刻差は−50.2〜+9.9 ms。固定上流の録画は拍を描いた比較用キャンバスを用い、上流声道の測定線はCLIプローブから取得した。[PCMと各区間の判定](../runs/worklet-song-vp8-20261120-chrome-repeat/summary.json)・[第2母音の復号画像](../runs/worklet-song-vp8-20261120-chrome-repeat/artifacts/decoded-tract-second_vowel.png)

同じChromeでVP9の対照を撮り、その後のVP8再実行も48項目すべてに合格した。VP9は45項目、H.264/AACのMP4回帰は33項目に合格し、4本の加工前WAVはバイト一致した。Chromeで通過したVP8の2回とも58種類の識別欄を復元し、輪郭の最大距離は3.992 px未満、両実装の映像間隔は51 ms未満だった。ソフトウェア描画とChromeの既定描画はブラウザの版も異なる。今回の試行から、描画方式だけが空白を生じさせたかは切り分けられない。[VP8の最終実行](../runs/worklet-song-vp8-20261120-chrome-final/summary.json)・[同じChromeでのVP9対照](../runs/worklet-song-vp9-20261120-chrome-control/summary.json)・[MP4回帰](../runs/worklet-song-vp8-mp4-regression-20261120/summary.json)

研究用仮想環境を有効にし、研究ディレクトリから新しい実行IDを指定する。出力ファイルのサイズ、ハッシュ、各コマンド、Chromeの起動設定はマニフェストに残した。上のChromeの条件で再現するときは、実行ファイルと描画方式を明示する。[環境とコマンド](../runs/worklet-song-vp8-20261120-chrome-repeat/manifest.json)

```bash
CHIMERA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  CHIMERA_RECORDING_GRAPHICS=native \
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  python3 tools/measure_worklet_song_recording.py worklet-song-vp8-local-1 --vp8
```
