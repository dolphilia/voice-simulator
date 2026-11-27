# デュエットの三次元声道に圧力を表示する

## 固定上流

固定版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。デュエットの `Head.frame` が可聴位置に対応するCHTL行を読み、描画ループがその調音行から `VoiceModel.frame` を作る。再生中は同じ行の圧力RMSも `Anatomy3D.airway` に渡す。一時停止中は `tele=null` になり、形状を保って中立色に戻す。圧力は咽頭・口腔の順のf32、単位はdyn/cm²。CHTLの `phLen`、`orLen` は音響モデルの各領域の長さ（cm）。`VoiceModel.nodeS` は、咽頭の `(i+0.5)×phLen/nPh`、口腔の `phLen+(i+0.5)×orLen/nOr` を節点の声門からの距離とする。`nodeValueAtS` は測定線の距離 `s` との差が最小の節点を選び、同距離では先に現れた節点を使う。咽頭・口腔の境で長さをまとめて割る処理や、隣り合う圧力を混ぜる処理は入らない。[デュエットの入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L154)・[節点の位置](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L126)・[最近傍の探索](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1377)

三次元では接触を補正した有効隙間を `d` とし、外側交点から測定方向に `d/2` 戻した点を楕円の中心にする。方向は内側から外側への単位ベクトルで、交点差が0.0001 cm以下なら直前の向きを保持する。左右の半径は `min(3.5 × 体型スケール, 2A/(πd))`。有効隙間が0.01 cm以下では、左右方向をつぶす。測定線は一つおきに24分割の輪で描く。圧力は40〜4,000 dyn/cm²を対数で0〜1に写し、0.85乗した値で琥珀色の段階を補間する。不透明度は `(0.25+0.65×色レベル)×(1−0.65×視線の成分²)`。成分は輪の面に垂直な方向とカメラ方向の内積の絶対値。停止時は青色で不透明度の基準を0.45にする。線材へ渡す前に単精度の頂点に変換する。[輪と圧力表示](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/src/ui/render/anatomy3d.ts#L1089-L1131)・[圧力と色](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/colors.ts#L29)

上流試験はCHTLの36・31節点のような声部固有の配列の読み方を定義し、表情試験は閉鎖の位置によって口腔圧が違うことを実合成で検査する。固定形状の試験は測定線の隙間・距離・面積と再標本化を比較する。既存の固定母音の研究表示では楕円の中心の計算を検証済み。今回の試験は声部ごとの節点の位置から実際の色までをつなぐ。[CHTL試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts)・[閉鎖と口腔圧](../../../../docs/reference/chimera-vocal-synth/upstream/tests/expression.test.ts)・[形状基準](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs)・[固定母音の検証](worklet-tract-3d.md)

## 測る前の予測

サンプル30,720で、女声の末端3点目は約7,984 dyn/cm²、最終節点は0 dyn/cm²で、最終セルの面積は0 cm²。男声の末端は同時刻に開いており、最終節点は約305 dyn/cm²。女声の34,560では開口が戻り、閉鎖中の強い圧力色が弱くなる。固定上流と同じ形状を与えた対照では色・不透明度・xyzが一致する。実録音の調音で形状が離れる場合は、節点距離を共通化した条件を使い、色に差が出る最初の箇所を追う。[事前登録](../cases/duet-head-pressure.json)

## 実装と実測

候補はRustの接触補正済み `AreaSample` をWASMの `vocal_duet_head_compute` から受け取る。`DuetHead` が可聴時刻に対応する調音行を適用し、`createDuetPressureView` が同じ行の咽頭長・口腔長と圧力から輪を着色する。描画前にカメラ位置を鏡像と頭部回転を含む頭部の座標系へ戻す。停止時は幾何と位置を保持して圧力入力を外す。CLIの `area` は同じ調音行から断面を直接計算する。[WASMの頭部計算](../crates/vocal-wasm/src/duet_head.rs#L43)・[観測行の適用](../../../../web/prototypes/chimera-research/src/duet-heads.tsx#L155)・[描画](../../../../web/prototypes/chimera-research/src/duet-head-pressure.ts)

48 kHzの同じ二声の録音で、CLI、固定上流の `Anatomy3D.airway` が `Beams.poly` へ渡した輪、Chromiumの通常画面を照合した。PythonはCHTLのバイト列を独立に読み、CLIの断面から描画座標・最近傍の節点・色・不透明度を求めた。960・390 CSS pxで、CLIとWASMの測定線は全列一致。節点位置の最大差は `1.78×10⁻¹⁵ cm`。実ブラウザの輪の頂点は独立計算に対して最大約 `6.28×10⁻¹⁶ cm`、不透明度の差は `1.11×10⁻¹⁶` だった。診断用の不均等な節点では、1.0 cmで同距離の二点から先に現れた節点0を選び、0.01 cm以下の隙間で左右半径が0になった。固定上流に候補の格子を渡す対照では、全リングの色が一致し、不透明度の差は `2.22×10⁻¹⁶` 以下だった。[結果](../runs/duet-head-pressure-20261120-c/summary.json)・[実行条件と成果のハッシュ](../runs/duet-head-pressure-20261120-c/manifest.json)

30,720サンプルでは女声の輪42が7,984.26 dyn/cm²を読み、色が上限に達した。輪46と48は0 dyn/cm²の末端節点を読み、左右半径も0 cmだった。同じ時刻の男声の末端は305.10 dyn/cm²で、輪48の左右半径は2.26 cmだった。女声は34,560サンプルで末端が73.24 dyn/cm²、輪48の左右半径が1.94 cmに戻った。実ブラウザでは再生開始、前後6回のシーク直後、停止保持、表示切り替えを確認した。表情を固定した女声の30,720サンプルをキャンバスの描画バッファから採取し、再生中と停止中でRGB成分が8以上変わった画素は幅960 pxで1,586、幅390 pxで1,110だった。[二声の末端圧力と画素数](../runs/duet-head-pressure-20261120-c/summary.json)

女声の46,080サンプルでは、固定上流の `VoiceModel.frame` が43,008サンプルと同じ小数3桁キーを使い、先に描いた格子を保持した。直接計算に対する最大差は距離 `4.39×10⁻⁶ cm`、面積 `1.00×10⁻⁵ cm²`。キャッシュを通さず上流WASMから計算すると、候補CLI・WASMとの最大差は距離 `1.54×10⁻¹⁴ cm`、面積 `5.69×10⁻¹⁴ cm²` 以下だった。節点の割り当てはこの区間でも同じだった。[生の格子と描画へ渡る格子](../runs/duet-head-pressure-20261120-c/artifacts/upstream-pressure.json)・[上流の形状キャッシュ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L78)

## 初回計測と再実行

- 実装直後のビルドでは、npmキャッシュの容量不足とBunの子プロセスからの解決失敗があった。デバッグキャッシュの整理後に、Bun 1.4.4を `PATH` に加えた環境でWASM・TypeScript・Viteを再ビルドした。
- 初回の390 pxでは、停止した位置に同じ値を入力したためシーク世代が進まず待機がタイムアウトした。比較位置とは別の登録済み位置を一度経由するよう採取手順を変更した。[初回の実行](../runs/duet-head-pressure-20261120-a/manifest.json)・[採取ログ](../runs/duet-head-pressure-20261120-a/artifacts/cargo.log)
- 次の実行では、DOM要素のスクリーンショットが描画バッファより縦1 px大きかった。停止・再生・非表示とも描画直後のバッファを `toDataURL` で採ることで揃えた。同一ポーズを使う条件と画素数の閾値は事前登録のまま比較した。[2回目の実行](../runs/duet-head-pressure-20261120-b/manifest.json)
- 修正後の独立した2実行で28項目すべてに合格し、2画面幅の画素数も一致した。[再実行の結果](../runs/duet-head-pressure-20261120-repeat/summary.json)・[実行記録](../runs/duet-head-pressure-20261120-repeat/manifest.json)
- 同じ結果を確認するには、研究ディレクトリで `python3 tools/measure_duet_head_pressure.py duet-head-pressure-local-1` を実行する。Pythonの研究環境とBun 1.4.4、Chromiumを使う。[比較スクリプト](../tools/measure_duet_head_pressure.py)

今回の再実行では研究用のPythonを使い、npmにあるBun 1.4.4を子プロセスの `PATH` に加えた。

```bash
npx --offline --yes --package=bun@1.4.4 -- ../../.venv/bin/python \
  tools/measure_duet_head_pressure.py duet-head-pressure-20261120-repeat
```
