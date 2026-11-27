# 固定上流の3D頭部を使った歌唱録画

## 読解と比較条件

上流の `App.LeftScreen` は `threeD` が有効なとき `AnatomyView3D` を使い、歌唱画面では音高の数値と口元の歌詞を渡す。`SingActions` の「Record video」は `AudioEngine.start` と直前の音の減衰を待つ。 `playTune` は歌詞をメロディーに当てはめ、開始フックで `Clip` を作った後に、音素とジェスチャーをWorkletへ予約する。Workletが返す `planned.t0` はシンセサイザーの秒時計における予約の原点で、各音符はそこに0.35秒とそれまでの拍数×60/BPMを足した時刻に始まる。上流の試験では、準備中に中止したときに開始フックを呼ばず、予定した歌唱の終了または停止に対応することを確認する。[上流画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/App.tsx#L125)・[録画ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L136)・[予約と終了](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L321)・[フックの試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L195)

`Clip` は毎回 `.screen.left canvas` の現在の画像を読み、720×1280 pxの録画面へ縦横比を保って中央に配置する。高さは下部のロゴ用150 pxを除いて割り付ける。30 fpsを要求した映像と、音声マスターから分岐した共有トラックを `MediaRecorder` に入れる。 `recording.owner` は現在の `Clip` の識別に使う。 `AnatomyView3D` は次の描画でそれを参照し、実時間の頭部では格子と測定線のフラグ、フォルマント等の数値の描画を止める。テレメトリと調音状態の選び方はそのまま使うので、発声と頭部の更新が続くと予測した。完走・中止では映像トラックと所有を解放し、音声は再録画に使えると予測した。[Clipの作画とトラック](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L50)・[音声共有](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L85)・[頭部の描画順](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L173)・[数値の描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/readouts.ts#L26)

Chromiumで成人男性の `Joyful` を選び、歌詞を空欄にして全28音を `la` で歌わせる。速度1、104 BPM、幅960 CSS px、3D・Measurements・Gridを有効にする。完走して保存した後に別の収録を1.2秒以上流して中止する。実際の作画から同じ頭部・同じ調音テレメトリを観測し、復号した3区間の頭部の画素と4音の母音中央のF0を照合する。画像の時刻の探索は採取点の前後200 ms、縮小画像のRGB平均絶対誤差は8階調以下、F0は40セント以内、復号音声とエンジン出力の包絡相関は0.65以上を事前に設定した。[登録条件](../cases/worklet-song-recording-upstream-head.json)・[Joyfulの譜面](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/tunes.ts#L38)

## 計測の実装

固定上流をビルドした後、同じソースをViteで配信し、通常のブラウザ画面から録画した。計測ページは、`Anatomy3D.update` に届いた描画設定と調音、頭部Canvasへの `drawImage` と数値の `fillText`、`Clip` がその頭部Canvasをコピーした時刻を記録する。録画用Canvasの3点は90×160 pxで採取し、FFmpegで同じ大きさに縮小した映像の対応点と比較した。ロゴの帯を画素計測から外した。MediaRecorderの状態採取は二拍の録画比較で使うヘルパーと共通にした。[ブラウザでの計測](../../../../web/prototypes/chimera-research/tools/capture-upstream-head-recording.mjs)・[録画状態の採取](../../../../web/prototypes/chimera-research/tools/observe-song-recorder.mjs)

復号音声の20 msごとのRMSと、Workletのフレームに記録した `outRms` を相関で整列した。開始位置は最初のコピー時の声の秒時計を使い、補正量は±180 msを2 ms刻みで探索した。語頭子音を避けた母音中央の120 msで、独立した自己相関のピークから周期を推定し、同時刻に頭部が読んだF0の中央値と比較した。画面が読む調音は17軸、F0はHz、`voicing` は無次元、画像の画素値は0〜255。[音声と画素の照合](../tools/measure_upstream_head_recording.py)・[Workletの観測値](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L215)・[出力RMS](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L634)

## 実測

Chrome 157の初回は全12項目に合格した。28音の予約は譜面の音高・拍と一致し、録画中も調音の17軸とF0が更新された。3Dの描画は両試行とも所有中に格子・測定線・数値を抑え、完走後と中止後にはF1等の数値と表示フラグが戻った。完走と中止は同じ音声トラックを使い、それぞれの録画用映像トラックを終了した。[初回判定](../runs/worklet-song-upstream-head-20261120-a/summary.json)・[描画とトラックの記録](../runs/worklet-song-upstream-head-20261120-a/artifacts/head-recording-browser.json)

初回の保存映像はH.264/AACの720×1280 pxで、578フレーム、実効30.00 fps、映像と復号音声の末尾の差が約29 msだった。画素を比較した3点のRGB平均誤差は1.86〜1.99階調。RMS包絡の最大相関は0.9968、整列に使った時刻補正は34 msだった。母音中央の4音では、復号音声のF0と3D頭部が参照したF0の差は最大21.5セント未満だった。[初回の復号と照合](../runs/worklet-song-upstream-head-20261120-a/summary.json)

`Clip.begin` は作成中に一度コピーしてから `captureStream` を作る。最初のコピーには、所有が設定される前に描いた頭部が使われた。完走・中止とも、その次のコピーから計測の表示が消えた。最終版の完走動画では、先頭画像にF1〜F3の数値が写り、次の画像で消えた。数値欄のx座標635〜714、y座標275〜332の領域で、RGBの最大成分が28を超える画素は216個から0個になった。録画開始を最初の計測なし描画まで待たせる対照は改善候補に残す。上流の録画は頭部の表示を取り込み、研究版の既存の歌唱録画では同じ時刻の声道断面とフレーム識別欄を取り込む。[最初のコピーのデータ](../runs/worklet-song-upstream-head-20261120-final/summary.json)・[最初の復号画像](../runs/worklet-song-upstream-head-20261120-final/artifacts/decoded-lead-01.png)・[2枚目の復号画像](../runs/worklet-song-upstream-head-20261120-final/artifacts/decoded-lead-02.png)・[研究版の録画比較](worklet-song-tract-recording.md)

再計測で配信WASMの検証を加えた際、ViteがURLを返すために生成したJavaScript応答を採取し、ハッシュの1項目に失敗した。最終実行では `application/wasm` の応答を選び、固定上流ビルドと配信バイト列のSHA-256が一致した。最終実行は13項目すべて合格し、映像は577枚・29.99 fps、RGB平均誤差は最大2.02階調未満、音声包絡の相関は0.9962、母音4点のF0差は最大11.5セント未満だった。共有の録画採取器を使う研究版の二拍・断面録画も33項目を通過した。[採取条件の失敗](../runs/worklet-song-upstream-head-20261120-repeat/summary.json)・[最終判定](../runs/worklet-song-upstream-head-20261120-final/summary.json)・[配信時の応答型](../runs/worklet-song-upstream-head-20261120-final/artifacts/head-recording-browser.json)・[研究版の回帰](../runs/worklet-song-upstream-head-20261120-tract-regression/summary.json)

## 再実行

Chromeの実行ファイルと既定の描画設定を指定し、研究用の仮想環境で新しい実行IDを使う。動画、復号音声、縮小フレーム、ブラウザ状態は作業用RTL9210B-CGに直接保存する。[最終実行のコマンドと環境](../runs/worklet-song-upstream-head-20261120-final/manifest.json)

```bash
CHIMERA_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  CHIMERA_RECORDING_GRAPHICS=native \
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 \
  python3 tools/measure_upstream_head_recording.py worklet-song-upstream-head-local-1
```
