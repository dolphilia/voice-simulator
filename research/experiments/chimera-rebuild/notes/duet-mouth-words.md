# デュエットで口元に表示する音節

## 固定上流の処理

対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`DuetPage.Head` が声部ごとに `mouthWords(() => wordAt(words, transport.time()), color, facing)` を作る。入力の時刻は可聴位置の秒。表示語は半開区間の譜面で選び、メリスマは親のキー、同じ綴りの再発音は独立のキーを使う。`AnatomyView3D` は描画フレームで形状と視点を更新し、WebGLを転写した後の2Dキャンバス上でオーバーレイを呼ぶ。[譜面と観測をつなぐ入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L154)・[描画順](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L220)・[譜面比較](duet-words.md)

上流の `faceHandles` は内唇の上下それぞれの第6点の平均に前方0.15 cmを足す。`faceView` の `project` は頭部の変換とカメラを通して口唇のcm座標をCSSピクセルへ変換する。カメラの右方向に1 cmずらして投影間隔を測る。文字の基準は口唇から前方1.2 cm。画面の端まで60 px未満なら顎の下へ移す。文字を大文字化し、基準サイズを1.7 cm相当、下限26 px、上限64 pxとし、計測した文字幅に合わせて縮小する。[口唇の位置](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy.ts#L33)・[透視投影](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L723)・[配置と描画](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/src/ui/mouthWords.ts#L43-L81)

`advanceTrail` は表示語と退場を始めた秒を最大8件保持する。次のキー又は休符で現役の語が退場し、短い空白を挟んだ同じ末尾キーは再び現役になる。退場時間を0.45秒で割った進捗 `u` で相対サイズを `1 − 0.55u`、不透明度を `0.75(1 − u)^1.5` とする。前方配置の退場は進行方向に240 px/s、上に200 px/s、下方配置は下に120 px/s。上流のシーク世代の処理は頭部の状態をリセットするが、`mouthWords` は別のクロージャに履歴を持ち、オーバーレイへの引数に世代がない。シーク後の残留は対照実験で確かめる。上流の歌詞と時計のテストは10件通過した。[状態と式](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/mouthWords.ts#L16)・[テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/words.test.ts)・[レイアウト検査](../../../../docs/reference/chimera-vocal-synth/upstream/tools/layout-lint.ts#L315)

## 測る前の予測

同じ頭部の唇の頂点を読み取って射影を独立計算する。画面幅960 pxでは文字は左右の頭部の間の方向に出る。300 pxでは前方の空きが減り、下へ移る。開始2点の差は、上流の固定カメラ構成と候補の正投影・フォントの差を持ち込まないよう、同じ投影情報と文字幅の制御入力で上流の描画命令と比較する。通常デモでは直前の非発音位置と発音位置を同一観測行から描き、撮影結果に文字だけの変化が出ることも確認する。

診断譜では男声の `Low-` が18,000〜42,000のメリスマでキー0を保ち、休符を経て66,000で同じ綴りのキー2へ替わる。診断譜の音声と旋律は歌詞比較の登録済み素材を使う。調音の効果を調べる通常デモと、語の履歴を調べる診断譜を用意し、診断譜は既存デモの観測列をレイアウトの共通入力として与える。時計の等価性、画面の幾何、シーク履歴を別々に判定する。[事前登録](../cases/duet-mouth-words.json)

## 初回計測の修正

300 pxの初回実行では、休符中に文字がなくなったことをブラウザ側で待機した後、別のコマンドで読み直した。保存したのは次の音節が始まった66,686サンプルで、ライブ判定の1項目が失敗した。待機が返す時点のデータをそのまま保存すると、判定と採取の間に次の描画が入ることを避けられる。修正は計測器に適用し、登録した譜面、判断区間、許容差は維持した。[初回の全判定](../runs/duet-mouth-words-20261120-a/summary.json)・[初回の観測](../runs/duet-mouth-words-20261120-a/artifacts/browser-mouth.json)

## 実装と実測

譜面から選んだ語を既存の歌詞一覧と頭部で共有する。Three.jsへ渡った上下内唇の中心点から、同じカメラで文字の基準を求める。文字は重ねたHTMLで描き、システムフォントの実測幅を使って縮める。上流の配置式を同じ口唇座標・画面寸法・文字幅で照合した。正投影の視点、字形、開始位置を結ぶ点線の余白は研究画面の表示に合わせた。画面幅が変わると一時停止中も投影し直す。退場中だけ別描画を予約し、経過秒は単調なブラウザ時計から得る。上流では各描画の `dt` を最大0.05秒に制限して足すため、長いフレーム停止で見え方が変わり得る。[唇からの投影](../../../../web/prototypes/chimera-research/src/duet-head-scene.ts)・[配置と退場](../../../../web/prototypes/chimera-research/src/duet-mouth-words.ts)・[上流の経過時間](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L178)

Chromiumの960 pxで両声部の文字は前方に、300 pxでは顎の下に出た。休止して幅を変更しても、新しい位置で同じ音節を表示した。停止中の70ラベルを読み、独立した射影と、同じ入力を与えた固定上流の描画命令に対する最大差は0.00050 CSS px以内。通常公演の同じ調音行で音節の開始前後を撮影すると、文字の追加により550・547画素が変化した。固定上流と現役の語が異なる位置は、既知の女声54,720・78,720サンプルの2点だった。[比較結果](../runs/duet-mouth-words-20261120-final/summary.json)・[実行記録](../runs/duet-mouth-words-20261120-final/manifest.json)・[別ディレクトリからの再実行](../runs/duet-mouth-words-20261120-repeat/manifest.json)・[三次元頭部の回帰28項目](../runs/duet-mouth-words-heads-regression-20261120/manifest.json)

人工時計では、シーク世代のリセットを無効にした候補と固定上流の履歴が全10操作で一致した。650 msでキー2からキー0へ飛ぶと、上流のオーバーレイに渡る履歴には直前のキー2が退場中として残り、候補の世代付きリセットではキー0だけが残った。同じ譜面を通常画面で再生し、キー0を保つメリスマ、休符の退場と消滅、同じ綴りを再発音するキー2を確認した。本番画面の前後シーク直後にも、シーク元の履歴を描かなかった。輪郭や気流の残像は異なる状態で、次の作業単位で扱う。[履歴の制御比較](../runs/duet-mouth-words-20261120-final/artifacts/upper-mouth.json)・[実ブラウザ観測](../runs/duet-mouth-words-20261120-final/artifacts/browser-mouth.json)
