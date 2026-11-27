# 実時間歌唱の声道断面を動画へ収める

## 読解と事前登録

上流の `playTune` は演奏を予約する直前に `SingPanel` の `onStart` を呼びます。録画時は `Clip` が現在の顔キャンバスを毎描画周期に取得し、720×1280の2Dキャンバスへ写します。三次元表示自体も `AnatomyView3D` が最新の調音から形状を計算し、WebGLから表示用の2Dキャンバスへ写しています。録画の映像は30 fpsのキャンバストラック、音声は共有マスターの分岐です。固定上流の歌唱テストは開始待ちの取り消し、開始・完走・中止の通知を検査しています。[歌唱の予約とフック](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L342)・[録画の呼び出し元](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L165)・[WebGLを写す描画ループ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L185)・[Clipの合成](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L63)・[テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L195)

再実装では、768出力フレームごとと末尾に、合成に使った測定線とセルを採ります。拍の時刻と同じ `AudioContext` 上で、録画側は音声処理が終わっている最新の観測点を使います。その三次元画像、出力フレーム番号の表示、同じ番号を読み取る32セルの識別欄を一つの2Dキャンバスへ描く設計とします。観測点のない先頭は識別欄を0とし、番号が0始まりなので有効な値はフレーム番号に1を加えます。WebGLの描画バッファは既定の保存設定で描画の直後にコピーし、次の観測点まで2D画像を繰り返し使います。[実時間の観測と時計](worklet-tract-3d-live.md)・[既存の録画対照](worklet-song-recording.md)・[キャンバスの映像採取](https://www.w3.org/TR/mediacapture-fromelement/#html-canvas-element-media-capture-extensions)・[WebGLの描画バッファ](https://registry.khronos.org/webgl/specs/latest/1.0/#2.2)

事前確認した `Pop Dee` のCLIでは、最初の唇閉鎖は19,967〜23,807、最初の母音に相当する26,879〜39,167では末端面積が6 cm²を超えました。第2拍前にも43,007〜45,311で閉鎖があり、48,383以降に再び開きます。二つの閉鎖期に点、二つの母音期に環が現れると予測します。復号した識別欄から画像が表す観測点を取得し、同じ測定線の外側端、有効隙間、面積から独立に計算した投影と比較します。音声は前回と同じ正規化相互相関で整列し、復号した動画PTSから音声上の観測時刻との差を測ります。[事前登録と許容差](../cases/worklet-song-tract-recording.json)・[歌唱スコアの入力](../cases/song-voice-long.json)・[固定録画の実行](../runs/worklet-song-recording-20261120-final/manifest.json)

## 初回の録画と修正の予測

最初の起動は計測スクリプトの変数名が一致せず、マニフェストを書き出す前に停止しました。修正後の初回録画は、119点の計測、PCM、映像内の識別欄と時刻を照合できました。映像の最大フレーム間隔は255.8 msでした。出力1,535では、復号画像に残った橙色から期待輪郭への95パーセンタイル距離は1.07 pxでしたが、期待輪郭から橙色への距離は19.57 pxでした。輪郭の一部が薄くなっており、特に第2母音では往復の距離が5.5 pxの基準を超えました。[初回録画](../runs/worklet-song-tract-recording-20261120-b/summary.json)

WebGLが使った三次元頂点から末端輪郭を2Dへ投影し、録画用の画像上で4 px幅の線にします。閉鎖の位置には同じ投影の点を描きます。他の断面を描くWebGLバッファは各辺を半分にし、合成用の画像へ拡大します。これで色の判別に足る輪郭を保ちつつ、WebGLからコピーする画素数を4分の1に減らせます。音響・時刻と画面位置の許容差はそのまま使います。

この変更後は4区間の輪郭を復号でき、最大投影差は3.78 pxでした。映像の249.7 msの欠落に対応する作画時刻の差が250.7 msあり、動画エンコーダーへ渡す前から画像更新が滞っていました。測定線の送信・保存は全119点でした。収録終了後に最後の画像へ識別欄を残したため、無音の末尾では映像と参照音声との差が123.5 msに達しました。次は同じ三次元頂点をThree.jsのカメラで投影し、線を録画用の2Dキャンバスへ直接描きます。合成済み音声の末尾を過ぎたフレームでは最後の画像を残し、現在のサンプルを示す識別欄を0に戻します。許容差はそのまま使い、作画時刻と映像PTSを再度比較します。[輪郭修正後の実行](../runs/worklet-song-tract-recording-20261120-c/summary.json)

2Dへ直接作画した最初の試行は、全119点を保存した一方、復号された映像が24枚で終端も短くなりました。動画の収録中にPlaywrightのプレビュー画像を撮っていたため、次は収録中の画像採取を省き、プレビューも同じ動画の復号結果から保存します。この試行では録画と描画の実装を固定し、計測操作が作画に干渉するかを確認します。[2D合成の初回](../runs/worklet-song-tract-recording-20261120-d/summary.json)

収録中の撮影を外すと最大間隔は121.8 msに収まりましたが、平均13.4 fpsでした。色ごとに線をまとめ、各辺半分の描画面に作画しても平均14.4 fpsで、既存の20 fpsの基準に届きませんでした。次は第2試行のWebGLで全断面を描く構成に戻し、プレビューの復号と、歌唱終了で識別欄を消す変更は引き継ぎます。さらに、録画を始める前にWebGLから2Dへの転写を一度完了させ、初回転写の負荷も発声区間の外に置きます。[プレビューを復号に移した対照](../runs/worklet-song-tract-recording-20261120-e/summary.json)・[2Dの線をまとめた対照](../runs/worklet-song-tract-recording-20261120-f/summary.json)

WebGLへ戻した最初の試行では、AudioWorkletが出力に接続される前に合成を始めました。合成開始のContextフレーム7,680に対して録画開始は18,688で、差は229.33 msでした。描画を準備している間にも処理が進んでいました。次は描画と転写の準備をノード生成より前に移し、録画の開始が合成の開始より先であることを検査します。[時計と録画開始が逆転した試行](../runs/worklet-song-tract-recording-20261120-g/artifacts/recorded-input.json)

## 実装と実測

「録画に声道の三次元断面を含める」を選ぶと、合成を始める前にWebGLの線と点、および2Dへの転写を準備します。Workletは既存の4本の転送バッファを使い、音響セルと測定線を768フレームごとに採取します。録画の合成処理は出力済みの最新観測を選びます。三次元断面を描いた直後に転写し、末端の輪郭を同じ頂点から投影します。閉鎖点の印も同じ投影を使います。画像、フレーム番号、識別欄は同じ作画で更新し、歌唱完了後は最後の断面を保持して識別欄を消します。録画の開始より前に合成が始まった場合は保存時のエラーにします。[Workletとの接続](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[録画と時刻の管理](../../../../web/prototypes/chimera-research/src/song-recording.ts)・[断面の作画と識別欄](../../../../web/prototypes/chimera-research/src/recorded-tract.ts)

開始順を修正した実行では、録画が合成より48.0 ms先に始まりました。H.264/AACの縦長MP4は62画像、実効28.96 fpsで、独立に読めた出力フレーム番号は55種類でした。119時点の測定線と音響セルはCLIと数値が一致し、固定上流の測定線との差は最大 `9.10×10⁻¹⁴` でした。映像画像の橙色と、CLIの測定線から計算した輪郭の双方向距離は、95パーセンタイルの最大で3.90 pxでした。音声相互相関で整列した時刻に対し、識別欄を持つ画像は29.5〜44.6 ms早く現れました。加工前PCMは91,200フレームすべてがCLIと既存の録画対照とビット一致しました。[録画と検証結果](../runs/worklet-song-tract-recording-20261120-h/summary.json)

固定上流との比較には二つの出力を使いました。上流の `Clip` に同じ二音の合成音声と拍マーカーを渡した録画で動画と音声のタイミングを比較し、固定上流の歌唱エンジンから取り出した断面を研究CLIと照合しました。顔を含むアニメーションの画素比較は未実施です。独立計算では、CLIの有効隙間を `d`、断面積を `A` として半径 `d/2` と `A/(πd/2)` から末端を再構成し、保存されたカメラの行列で画素へ変換しました。復号できた画像の識別欄から比較する出力フレームを選び、色を抽出した画像と双方向に距離を計算しました。比較スクリプトはCLIと上流の格子・セル・映像PTS・復号画像を別々に保存します。[独立した比較器](../tools/measure_recorded_tract.py)・[既存の固定上流の録画対照](worklet-song-recording.md)

実時間IPAの回帰では、960 pxの最初の描画後に次の受信まで437.3 msかかり、Workletの保存は維持された一方で23件の送信が省略されました。表示用キャンバスは発声前にレイアウトから外れ、最初の観測で実寸に変わっていました。発声前から表示寸法を確保し、同じ幅・高さ・画素比ではWebGLの描画面を作り直さない形で再確認します。[実時間IPAの回帰判定](../runs/worklet-tract-live-song-recording-regression-20261120/summary.json)・[そのときの受信時刻](../runs/worklet-tract-live-song-recording-regression-20261120/artifacts/browser-live-tract.json)

作業ディレクトリを変えた実行と最終の実行で33項目すべてを通過しました。最終の動画では、56種類の出力フレーム番号を復号し、動画の実効描画頻度は29.56 fpsでした。CLIの投影との差は画像ごとの95パーセンタイルで最大4.01 pxでした。識別欄を持つ画像は整列した音声の対応時刻より33.9〜48.7 ms早く、85 msの許容差内です。直前の試行では候補が全条件を満たしましたが、固定上流 `Clip` の最大動画間隔が267.2 msとなって既存基準を超えたため、その実行も保存しました。[最終結果](../runs/worklet-song-tract-recording-20261120-final-retry/summary.json)・[復号したプレビュー](../runs/worklet-song-tract-recording-20261120-final-retry/artifacts/recording-preview.png)・[保存したMP4](../runs/worklet-song-tract-recording-20261120-final-retry/artifacts/worklet-song.mp4)・[別ディレクトリからの実行](../runs/worklet-song-tract-recording-20261120-repeat/manifest.json)・[固定上流の間隔超過](../runs/worklet-song-tract-recording-20261120-final/summary.json)

表示寸法を発声前に準備した回帰では、960 pxと390 pxの両方で65点を受信し、各61点を表示しました。停止対照を含む実時間IPAの47項目と、三次元断面なしの歌唱録画の23項目が通過しました。[実時間IPAの再検証](../runs/worklet-tract-live-song-recording-regression-20261120-b/summary.json)・[既存録画の回帰](../runs/worklet-song-tract-baseline-regression-20261120/manifest.json)

WebM経路を追加で検証する際に、録画用キャンバスの作画を軽くし、合成終了後の目標映像2周期に最後の断面の識別欄を残すようにしました。現在は最後の観測点91,199もMP4・WebMの両方で復号でき、動画の終端では識別欄が0になります。[録画パイプラインの変更とWebMの検証](worklet-song-recording-webm.md#実装と実測)・[更新後のMP4](../runs/worklet-song-webm-mp4-regression-20261120-final/summary.json)
