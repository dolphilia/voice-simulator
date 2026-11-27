# 固定母音の声道断面を三次元で表示する

固定上流では `App` が `AnatomyView3D` を遅延読込する。描画ループは体型に対応する `VoiceModel`、調音状態、またはテレメトリから `frame()` を作り、`Anatomy3D.update` に渡す。地の形・圧力表示・カメラ・テレメトリは別の状態を持つ。`VoiceModel.frame` は調音値の小数3桁でキャッシュし、WASMの `HumanVocalTract::compute` で得た輪郭・格子を再利用する。固定試験 `geometry_matches_typescript` は、測定線の領域、隙間、面積、声門からの距離、輪郭と再標本化した値を照合する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/App.tsx#L24)・[描画ループ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L196)・[モデルのキャッシュ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L81)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs#L15)

上流の各測定線には、内側・外側の交点と中点（cm）、幾何学的な測定線の長さ（cm）、接触を考慮した有効隙間 `d`（cm）、計算面積 `A`（cm²）、声門からの距離 `s`（cm）がある。`s` は喉頭上部の長さから始まり、測定線の中点の間隔を足す。表示では測定線の方向を内側から外側へ向かう単位ベクトル `u` とし、外側交点 `o` から `d/2` だけ内側へ戻した `c=o−u d/2` を中心にする。正中矢状面上の半径を `a=d/2`、左右方向を `b=A/(πa)` とすれば、断面積が `A` の楕円になる。上流は描画時に半径 `b` に体型スケールに応じた上限を掛け、有効隙間が0.01 cm以下では幅を0にする。[測定線の型](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L465)・[三次元の断面リング](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1090)

研究用の表示は固定姿勢から求めた計算面積をそのまま表示するため、正の隙間には上限を掛けずに幅を求める。音響エンジンのセルには格子の再標本化が入るため、ここで描くリングはその前の測定線を表す。音響格子のセルの平均面積と最小面積は従来の断面表示で確認できる。[断面積と距離の実装](../crates/vocal-core/src/anatomy/area.rs#L28)・[既存の音響セル表示](worklet-tract-profile.md)

## 事前登録

固定母音 `/i/` の同じ入力から口唇開度1.046 cmと0.30 cmの2条件を作る。測定線49本すべてについて、WASMから取得する計測列をCLIと固定上流の `--area` プローブに照合する。口唇開度を下げると、最終断面の面積は少なくとも2 cm²、中心は上方へ少なくとも0.08 cm変化すると予測する。描画は64頂点。リングの頂点から独立に復元した中心・隙間と、正多角形近似の補正係数 `64 sin(2π/64)/(2π)` を掛けた面積を比較する。実ブラウザで960 pxと390 pxの画面、カメラの切り替え、断面選択を試す。カメラを変えても計測値と保存する頂点は一致すると予測する。[登録ケースと許容差](../cases/worklet-tract-3d.json)

## 実装と実測

固定姿勢のWASMから、CLIと同じ断面プロファイルの測定列を読み取る。この処理は表示を開いたときに行う。Three.jsは上流と同じ0.186.1を使い、画面操作まで遅延読込する。外側交点と有効隙間から計算した64頂点で各測定線の輪を描き、楕円の中心列と左右の輪郭を結ぶ。画面から保存するJSONにはWASMの測定列と、描画に使った単精度頂点が入る。画面幅や視点を変更しても、同じ形状を数値で追跡できる。[WASMの固定姿勢の入口](../crates/vocal-wasm/src/lib.rs)・[頂点と描画](../../../../web/prototypes/chimera-research/src/tract-3d-scene.ts)・[観測JSONの書き出し](../../../../web/prototypes/chimera-research/src/tract-3d.tsx)

初回の自動計測は、WASM応答を待つ処理がタイムアウトした。選択欄の名前を明示し、画面のエラーと応答を記録できるようにして、同じ入力・許容差で再試行した。[初回失敗のログと条件](../runs/worklet-tract-3d-20261120-a/manifest.json)

| 条件 | 末端の有効隙間 | 末端の計算面積 | 末端の中心の高さ | 声門からの距離 |
| --- | ---: | ---: | ---: | ---: |
| 固定 `/i/` | 1.04733 cm | 3.78384 cm² | 7.63166 cm | 16.66578 cm |
| 口唇開度0.30 cm | 0.30133 cm | 1.08867 cm² | 7.76257 cm | 16.70457 cm |

末端の計算面積は2.69517 cm²減り、中心は0.13091 cm上がった。口唇幅に関わる入力は同じで、末端の左右方向の直径はどちらも4.60 cmだった。固定 `/i/` の末端では、測定線の幾何中点より表示楕円の中心が0.03705 cm高かった。有効隙間1.04733 cmは測定線の幾何学的な長さ1.12143 cmより短く、描画の中心は外側交点を基準に定まる。声門からの距離の積算には引き続き幾何中点を使う。[形状と独立計算の結果](../runs/worklet-tract-3d-20261120-b/summary.json)

両姿勢の全49測定線で、WASMとCLIの11列は最大差0だった。固定上流との最大差は `7.11×10⁻¹⁵`。最初の数値差は描画より前の測定線0の内側X座標にあり、その差は `8.88×10⁻¹⁶ cm` だった。描画頂点から再計算した中心座標の最大差は `2.33×10⁻⁷ cm`、多角形補正後の面積の最大差は `1.10×10⁻⁶ cm²` だった。試した2姿勢では上流の描画幅の上限に達する測定線がなかった。2画面幅と斜め・側面の両視点で同じ観測JSONを得た。[比較の全判定](../runs/worklet-tract-3d-20261120-b/summary.json)・[表示の例](../runs/worklet-tract-3d-20261120-b/artifacts/browser-tract-3d.png)

## 再実行と回帰

ChromiumのSwiftShaderによるWebGL 2で、研究ディレクトリと `/tmp` から各57項目を通過した。両実行の要約、計測・入力・WASMの15ファイル、キャプチャ画像9枚が一致した。従来の `ɑpɑ` の二次元断面表示の回帰12項目も通過し、WAV・CLIの系列・描画座標・比較の要約が以前と一致した。物理GPUでの描画、発話中の更新、頭部の表示には別の検証が必要になる。[初回合格](../runs/worklet-tract-3d-20261120-b/manifest.json)・[別ディレクトリからの再実行](../runs/worklet-tract-3d-20261120-repeat/manifest.json)・[二次元表示の回帰](../runs/worklet-tract-profile-3d-regression-20261120/manifest.json)

```bash
python3 tools/measure_worklet_tract_3d.py worklet-tract-3d-local-1
```
