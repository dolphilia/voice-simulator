# WebMの形式選択と歌唱録画

## 読解と事前登録

固定上流の `SingActions` は前の音が消えるまで待ち、`playTune` がスコアの予約を送る直前に `onStart` を呼びます。`AudioEngine.recordStream` は音声マスターを共有の `MediaStreamAudioDestinationNode` に分岐し、`Clip` は顔キャンバスを720×1280の2D画像に合成して30 fpsの映像トラックを取得します。`pickType` はMIME型の対応検査を順に行い、H.264/AACのMP4、型だけのMP4、VP9/OpusのWebM、VP8/OpusのWebM、型だけのWebMの順で最初に通った型を渡します。`Clip` は映像5,000,000 bit/sを要求し、500 msごとにデータを受け、`stop` までのチャンクを一つの `File` に結合します。開始前の中止が `onStart` を呼ばず、開始時の例外で合成も予約されないことは固定上流の `singing-live.test.ts` で検査しています。固定上流の `Clip` 自体は実ブラウザに読み込み、比較用の二音PCMを音声トラックへ渡して形式選択と終了処理を実行します。[歌唱画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L165)・[スコアの予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[音声分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L85)・[形式と録画](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L13)・[歌唱の開始フックのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L195)

再実装は歌唱パネルと録画開始時に `songRecordingType` を呼びます。音声は48 kHzで、同じ `AudioContext` の開始フレームを起点に二拍（0.5秒、1.0秒）、声道断面、音声を観測します。録画クラスは `scheduledFrame` と描画済み拍を次の画像へ引き継ぎ、完走後の230 msは値0の音源でトラックを保ちます。完走時は `stop` を待ってファイルを作り、取り消し時は両方の専有トラックを解放します。固定上流では映像だけが `Clip` の所有で、音声トラックは次の録画にも使えます。[歌唱画面](../../../../web/prototypes/chimera-research/src/main.tsx#L619)・[録画クラス](../../../../web/prototypes/chimera-research/src/song-recording.ts)・[既存の録画対照](worklet-song-tract-recording.md)

比較は二音の `Pop Dee`、三次元断面付きの候補と固定上流の `Clip` に統一します。候補と上流のページでMP4の二つの対応判定だけを偽にし、残りの型はブラウザ本来の結果を返します。両方が最初のWebM候補を選び、ブラウザが作ったファイルのEBML DocType、VP9とOpus、再生時刻を確認します。既存MP4のマニフェストと加工前WAVを照合し、同じ91,200フレームであることを確かめます。拍、末尾、4区間の輪郭は既存の許容差を使います。拍のずれをMP4の対応する値と比較し、85 ms以内と予測します。[事前登録](../cases/worklet-song-recording-webm.json)・[固定MP4](../runs/worklet-song-tract-recording-20261120-final-retry/manifest.json)・[MediaRecorderの形式判定](https://www.w3.org/TR/mediastream-recording/)

音声は、復号された各フレームの先頭PTSを `P₀ + それまでの復号サンプル数 / 48000` と照合し、最後のPTSにそのフレームの長さを加えた時刻も総サンプル数と比べます。PTSが1 ms単位でも差は2 ms以内と予測します。音声と映像の先頭PTSの差は85 ms以内で、整列後に先頭と終端の無音が残ると予測します。最初のOpusパケットのPTSも別に保存します。WebMではコーデック遅延の取り扱いがあるため、PCMとの整列には復号フレームの時刻を使います。[WebMの時刻とコーデック遅延](https://www.webmproject.org/code/specs/container/)・[ffprobeのパケットとフレーム](https://ffmpeg.org/ffprobe.html)

## 初回結果と修正前の予測

研究用仮想環境に入る前の実行は `numpy` の読み込みで停止しました。仮想環境で実行すると両方の実ファイルでWebM、VP9、Opusを確認でき、ブラウザ内でも約0.55秒まで再生しました。一方、候補の録画は19枚、実効9.93 fpsで、第1拍が音声より97.5 ms遅れ、映像の推定終端が音声より303 ms早くなりました。固定上流の映像は約29.99 fpsでした。Workletは119件をすべて送り、録画側の作画に使った観測は20件でした。VP9のファイルができることと、映像を時間どおり供給できることを個別に追います。[初回の判定](../runs/worklet-song-webm-20261120-a/summary.json)・[ブラウザの観測](../runs/worklet-song-webm-20261120-a/artifacts/recording-browser.json)

最初の圧縮パケットと復号音声のPTSはこの試行では同じでした。音声フレームは両方が60 ms（2,880サンプル）ずつで、音声PTSの差分は57、60、63 msなどになりました。先頭からのサンプル数との最大差は固定上流でも3 ms、候補では4 msでした。ChromiumのOpusエンコーダーは60 ms分をまとめ、入力バッファの取得時刻を使って出力時刻を付けます。観測した128サンプルの刻み（約2.67 ms）とコンテナの1 ms刻みを足し、隣接フレームにはその和、先頭を基準にした各位置と終端には二つの境界の誤差として合成ブロック2個とコンテナ1刻みを許容します。音声フレームのサンプル数一致と厳密な時刻順、拍・無音・映像終端の既存基準は引き継ぎます。[事前登録の初版](../runs/worklet-song-webm-20261120-a/artifacts/source/research/experiments/chimera-rebuild/cases/worklet-song-recording-webm.json)・[ChromiumのOpus実装](https://chromium.googlesource.com/chromium/src/%2B/0d8e2b17d6af4df8f33fc23003fd09c59a7dfba2/third_party/blink/renderer/modules/mediarecorder/audio_track_opus_encoder.cc)

録画用のWebGLでは49断面を口腔と咽頭の線分へまとめます。元の断面頂点、カメラ、2Dに描く唇の輪郭は引き続き同じ入力を使います。録画用の小さい描画面ではWebGLのマルチサンプリングを省きます。これで断面更新ごとの描画と転写の負荷が減り、30 fpsの採取と音声のタイミングに近づくと予測します。録画キャンバスへ実際に作画した時刻も保存して、映像が少ないときに作画側と圧縮側を比較します。

この変更で24.88 fps・45項目通過の実行を得ました。別ディレクトリからの再実行では26.18 fpsでしたが、映像PTSの0.110〜0.386秒の間に276 msの空白がありました。その区間には音声時計上でも断面の作画間隔256 msがあり、119点はすべて受信しました。映像の圧縮を始めた直後のキャンバス転送を切り分けるため、録画用2DキャンバスにCPUからの読み出しを優先する指定を加えます。また、色別にまとめた描画バッファからカメラの範囲を求めると未使用の頂点と準備時の形状が混ざるため、範囲は従来の各断面とガイドの点列だけから求めます。[最初の通過](../runs/worklet-song-webm-20261120-b/summary.json)・[再実行の映像間隔超過](../runs/worklet-song-webm-20261120-repeat/summary.json)

## 実装と実測

録画用2Dキャンバスに `willReadFrequently` と不透明な背景を指定した実行では、64枚・29.91 fps、映像の最大間隔48 ms、作画の最大間隔21.3 msでした。途中で録画ファイルの作成を取り消し、その後に再度保存できることも含め、全45項目が通過しました。同じブラウザでMP4に対応していること、候補と上流の両方が拒否された二つのMP4を順に問い合わせ、次のVP9/Opusを使うこと、保存したファイルが実際にWebMであることを確かめました。環境はmacOS 15.6.1のarm64、PlaywrightのChromium 156.0.8078.4、Three.jsのソフトウェア描画です。ビルド・取得・復号を含むコマンドと出力ハッシュはマニフェストにあります。[実行と環境](../runs/worklet-song-webm-20261120-c/manifest.json)・[判定](../runs/worklet-song-webm-20261120-c/summary.json)・[動画](../runs/worklet-song-webm-20261120-c/artifacts/worklet-song.webm)

候補の先頭PTSは映像が0 ms、Opusの最初のパケットと復号フレームが39 msでした。復号フレームの音声時刻とサンプル数からの計算との差は候補で最大4 ms、固定上流で最大3 msでした。整列後の0.10〜0.25秒と1.78〜1.87秒のRMSは、候補では発声区間の0.0015%未満です。整列した音声より第1拍の画像が30.5 ms、第2拍が29.5 ms先行し、固定上流では両方とも27.5 ms先行しました。候補の拍のずれは固定MP4の対応する値から最大11.7 ms変化しました。加工前PCMは全91,200フレームがCLIとビット一致し、固定MP4のWAVとハッシュが一致しました。[音声と拍](../runs/worklet-song-webm-20261120-c/summary.json)・[Opusの圧縮パケット](../runs/worklet-song-webm-20261120-c/artifacts/worklet-song-audio-packets.json)

57種類の出力フレーム番号を読み取り、二つの唇閉鎖と二つの母音の全区間を照合しました。描画輪郭とCLIから独立に投影した輪郭の差は、画像ごとの95パーセンタイルで最大3.93 pxでした。画像の識別欄は整列した音声の対応時刻より32.5〜49.5 ms先に現れました。固定上流との比較では、`Clip` の拍・音声と歌唱エンジンの測定線を使いました。上流の顔アニメーション、VP8への切り替え、他ブラウザや長い歌唱での性能には測定が残ります。今回の各描画変更の寄与を分ける場合は、最終実装からいずれか一つの設定だけを元に戻し、作画の最大間隔と復号PTSを比較します。[復号したプレビュー](../runs/worklet-song-webm-20261120-c/artifacts/recording-preview.png)・[映像のPTS](../runs/worklet-song-webm-20261120-c/artifacts/worklet-song-ffprobe.json)

別のWebM試行では候補の全判定が通りましたが、固定上流の映像間隔が185 ms、映像終端と音声終端の差が359 msになりました。変更後のMP4回帰では、最終観測の91,199は作画されましたが、この時点で合成済みのため識別欄はすでに0でした。直前に復号できた番号88,319は許容している末尾1,536フレームより早く、判定を外れました。末尾の観測は合成した直後に届くため、合成終了後の最初の目標映像2周期は識別欄を残します。その後は既存どおり0で保存します。復号時の85 msの許容差と、終端が識別欄0である条件は維持します。[固定上流のWebMの間隔・終端超過](../runs/worklet-song-webm-20261120-d/summary.json)・[MP4の最終識別欄](../runs/worklet-song-webm-mp4-regression-20261120-b/summary.json)

最終構成を `/tmp` から2回実行し、両方で45項目を通過しました。実効29.84〜29.93 fpsで、映像の最大間隔は54 msでした。両方で58種類の識別番号を復号でき、最後の観測91,199を含み、動画の末尾は識別欄0でした。輪郭の最大差は3.94 px未満で、音声上の対応時刻との差は−49.9〜+7.2 msでした。MP4回帰も33項目を通過し、末尾の観測91,199を復号できました。[最終実行](../runs/worklet-song-webm-20261120-final/summary.json)・[最終の再実行](../runs/worklet-song-webm-20261120-final-repeat/summary.json)・[MP4の回帰](../runs/worklet-song-webm-mp4-regression-20261120-final/summary.json)

通常録画の23項目と、960 px・390 pxの実時間IPA三次元表示の47項目も通過しました。表示の比較モジュール `measure_live_tract.py` の直接実行では測定が始まらず、実際の入口 `measure_worklet_tract_profile.py --live-3d` から実行し直しました。[通常録画の回帰](../runs/worklet-song-webm-plain-regression-20261120-final/manifest.json)・[実時間表示の回帰](../runs/worklet-tract-live-webm-regression-20261120/manifest.json)

後続の比較では、同じ歌唱をVP8/Opusへ切り替えて、Chromeでの形式選択、作画と復号の間隔、固定VP9からの拍の変化を測りました。[VP8の実測](worklet-song-recording-vp8.md)
