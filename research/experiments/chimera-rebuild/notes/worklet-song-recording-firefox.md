# Firefoxが選ぶ歌唱の録画形式

## 読解と比較条件

固定上流の `SingActions` は、`playTune` が発声を予約する直前の開始フックで `Clip` を生成する。開始前の中止とフックが例外を投げた場合の扱いは、上流の歌唱試験で確認する。 `pickType` は、H.264/AACを明示したMP4、コンテナだけのMP4、VP9/Opus、VP8/Opus、コンテナだけのWebMの順で問い合わせる。 `Clip.begin` で720×1280のキャンバスから30 fpsの映像を取り、音声マスターから分岐するトラックと合わせて `MediaRecorder` に渡す。停止時は最後のデータを連結し、共有音声トラックは次の収録に残す。[上流の録画開始](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L165)・[歌唱の開始フック](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[形式と録画](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L13)・[開始フックの試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L195)

候補の `SongRecording` は同じ順序で形式を選ぶ。AudioContextのフレームから歌唱の開始フレームを引いた時刻で拍を切り替え、採取済みの測定線と、その出力フレームを示す32ビットの識別欄を同じ画像に描く。収録完了・中止時は今回の映像と音声を終了する。Firefoxの試験では `isTypeSupported` の結果をすべて記録し、返り値をそのまま返す。通常の歌唱画面と固定上流の `Clip` が優先順で最初に対応した型を選ぶこと、および復号したコンテナとストリームがその型に対応することを予測した。[候補の録画実装](../../../../web/prototypes/chimera-research/src/song-recording.ts)・[録画する断面と識別欄](../../../../web/prototypes/chimera-research/src/recorded-tract.ts)・[事前登録](../cases/worklet-song-recording-firefox.json)

同じ二拍の `Pop Dee` を出力48 kHzで合成し、加工前の91,200フレームと、16 msごとの119時点の格子を固定Chromiumに照合する。復号した音声は二つの発声区間の相互相関で加工前PCMに整列し、0.5秒と1.0秒の映像の拍がそれぞれ85 ms以内に現れること、前後の無音、終端、閉鎖と母音の4区間の輪郭を従来と同じ基準で確認する。輪郭は識別欄から出力番号を読み、CLIの同じ時刻の断面を独立に投影する。[録画と音声の判定](../cases/worklet-song-recording.json)・[断面の4区間](../cases/worklet-song-tract-recording.json)・[固定Chromiumの判定](../runs/worklet-song-vp8-20261120-chrome-final/summary.json)

音声の復号フレームのPTSは、整数のPTSにトラックの時刻単位を掛けて秒にそろえる。PTSと比較するサンプル位置は、先頭復号フレームのPTSにそれまでの復号サンプル数をレートで割った値を足す。隣接の許容差は128サンプルと時刻単位1刻みの和、先頭基準と終端では128サンプル2個と時刻単位1刻みの和を使う。Opusでは圧縮パケットが仮の先頭サンプルを含むことがあるため、音声との整列では復号側の時刻を使う。[WebMでの先行計測](worklet-song-recording-webm.md)・[MatroskaのOpusマッピング](https://www.matroska.org/technical/codec_specs.html)・[Opusの先頭の破棄サンプル](https://datatracker.ietf.org/doc/html/rfc7845#section-4.2)

## 実測と残る差

Playwrightの固定バージョン1.64.1で配布されるFirefox 157.0を作業用RTL9210B-CGに配置した。最初の単独の対応確認は、立ち上がっていないローカルURLに移動したため評価前に失敗した。空のHTMLページで確認し直すと、WebGL2と `captureStream` を取得できた。録画本体の初回と、異なる作業ディレクトリからの再実行は46項目すべて通過した。音声時刻の計測を共通化した後のChrome VP8も48項目を通過した。[初回の判定](../runs/worklet-song-firefox-20261120-a/summary.json)・[再実行の判定](../runs/worklet-song-firefox-20261120-repeat/summary.json)・[再実行の環境とコマンド](../runs/worklet-song-firefox-20261120-repeat/manifest.json)・[Chromeの回帰](../runs/worklet-song-firefox-vp8-regression-20261120/summary.json)

ブラウザはMP4の2形式とVP9/Opusを非対応、VP8/OpusとコンテナだけのWebMを対応と返した。候補と固定上流の全問い合わせは最初に真を返すVP8/Opusで終了し、MediaRecorderへ同じ型を指定した。EBMLのDocTypeは `webm` で、実際に復号したコーデックはVP8とOpusだった。候補の再生、準備中・収録中の中止と再録画、固定上流の共有音声トラックの保持を確認した。[形式とトラックの記録](../runs/worklet-song-firefox-20261120-repeat/artifacts/recording-browser.json)

| 観測値 | 候補の2回 | 固定上流の2回 |
| --- | ---: | ---: |
| 実効映像fps | 23.02〜23.54 | 22.54〜22.80 |
| 映像の最大PTS間隔 | 50 ms | 50〜51 ms |
| 整列後の音声に対する2拍の映像の時差 | −3.0〜+36.0 ms | −0.7〜+32.4 ms |
| 先頭復号フレームと累積サンプル数による時刻の最大差 | 0.5 ms | 0.5 ms |

加工前PCMは全91,200フレームがCLIとビット一致し、WAVのハッシュと119時点の声道格子が固定Chromiumと一致した。候補の前後の無音と復号終端は既存基準の範囲内だった。映像から両回とも45種類の出力フレーム番号を復元した。閉鎖と母音を含む4区間で輪郭とCLIの独立投影を比較すると、95パーセンタイル距離は全画像で最大4.103 px未満、断面の映像時刻は整列した音声に対して−5〜+19 msだった。[復号と輪郭の判定](../runs/worklet-song-firefox-20261120-repeat/summary.json)・[復号した断面の例](../runs/worklet-song-firefox-20261120-repeat/artifacts/decoded-tract-second_vowel.png)

同じVP8/Opusを収録した固定Chromiumでは復号音声が2,880サンプル（60 ms）単位、Firefoxは先頭を除き960サンプル（20 ms）単位だった。Firefox初回の両動画では、最初の圧縮パケットのPTSが−1 ms、先頭の復号PTSが+6 msで、復号フレームは648サンプルだった。 `ffprobe -v error -select_streams a:0 -show_entries stream=extradata -show_data -of json` で音声トラックの `OpusHead` を読み、オフセット10のリトルエンディアン2バイトの値が312サンプルであることを確認した。960−312と一致する。固定Chromiumの同フィールドは0だった。これらはブラウザごとの録画で観測された値。[Firefoxのパケット](../runs/worklet-song-firefox-20261120-a/artifacts/worklet-song-audio-packets.json)・[Firefoxのストリームと復号フレーム](../runs/worklet-song-firefox-20261120-a/artifacts/worklet-song-ffprobe.json)・[Chromiumのパケット](../runs/worklet-song-vp8-20261120-chrome-final/artifacts/worklet-song-audio-packets.json)・[OpusHeadの定義](https://datatracker.ietf.org/doc/html/rfc7845#section-5.1)

Firefoxの初回映像の間隔は33〜34 msと50 msに集中した。同区間の上流キャンバスへの作画は出力映像より多く、作画の最長間隔は約37 msだった。固定Chromiumの候補はほぼ30 fpsだった。Firefoxのどの段で50 ms間隔になるかは今回の録画だけでは確定していない。同じブラウザで周期と色番号だけを回す軽量のCanvasを使い、描画番号と復号PTSを30 fpsと60 fpsの要求で比較できる。[Firefoxの作画と復号時刻](../runs/worklet-song-firefox-20261120-a/summary.json)・[Chromiumの映像間隔](../runs/worklet-song-vp8-20261120-chrome-final/summary.json)

## 再実行

PlaywrightのFirefoxはWebプロトタイプで配置する。録画の計測は研究用仮想環境を有効にし、研究ディレクトリで新しい実行IDを指定する。動画・復号フレーム・CSVはRTL9210B-CGへ直接書き出す。[コマンドと保存先](../runs/worklet-song-firefox-20261120-repeat/manifest.json)

```bash
PLAYWRIGHT_BROWSERS_PATH=/Volumes/RTL9210B-CG/voice-simulator/build/playwright \
  node node_modules/playwright-core/cli.js install firefox
```

```bash
PLAYWRIGHT_BROWSERS_PATH=/Volumes/RTL9210B-CG/voice-simulator/build/playwright \
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  python3 tools/measure_worklet_song_recording.py worklet-song-firefox-local-1 --firefox
```
