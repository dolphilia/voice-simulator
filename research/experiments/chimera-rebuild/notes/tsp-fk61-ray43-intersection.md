# FK61_01の測定線43と下側輪郭の交差

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行計測では、描画前の測定線43の面積を交換すると節点42の平均断面積が上流に一致した。今回の観測対象は、同じ発話の固定上流、標準研究版、唇前端の体型変換だけを揃えた試験版の測定線43。 [前回の断面積の照合](tsp-fk61-node42-area-origin.md)・[比較条件](../cases/tsp-fk61-ray43-intersection.json)

## 呼び出しと交差の計算

上流の `HumanVoice::render` は制御境界で `control` を実行し、`HumanAirway::commit` が `HumanTract::compute` で音響用の上下輪郭と測定線を作る。研究版では `ArticulatedVoice` の制御更新から `HumanTractControl`、`SagittalModel::compute_into`、`measurement_grid_into` を通る。前方の6本は上向きの垂直線で、最初は上顎の切歯位置に体型倍率の0.03倍を足したx座標から出る。下唇が引き込まれるなどの条件では下側交点を補正する経路もある。今回のモデルは観測した上下の交差を先に再現し、接触前の座標・隙間とも照合する。 [上流の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[上流の前方測定線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1051)・[研究版の輪郭](../crates/vocal-core/src/anatomy.rs#L266)・[研究版の前方測定線](../crates/vocal-core/src/anatomy/grid.rs#L92)

光線の原点 `O`、輪郭線分の端点 `A`、`B` はcmで保持する。光線と線分の二次元外積で端点が別々の側にあることを確かめる。光線と平行な場合を除き、交差距離 `t = cross(A − O, B − A) / cross(d, B − A)` を求める。方向 `d` は単位ベクトルで、今回の `t` は原点からの高さ［cm］。上側は範囲内で最小の `t`、下側は上側に体型倍率の1.5倍を足した範囲内で最大の `t` を選ぶ。交点は原点に方向と距離の積を足し、接触補正前の隙間は上下の距離差から得る。光線が輪郭の頂点をかすめる場合の入口・出口の対を確認する既存の試験も読んだ。 [上流の交差処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L107)・[研究版の交差と選択](../crates/vocal-core/src/anatomy/grid.rs#L136)・[上流の頂点試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L206)・[研究版の頂点試験](../crates/vocal-core/src/anatomy/grid.rs#L347)

描画前および1984・1985・2048フレームで実際の光線、上下輪郭、補正前の距離を採取し、独立計算で採用線分を選び直す。描画前では光線、下側線分の始点、終点を交換する全8条件を比較する。各条件で垂直線と線分の交点を有理数で計算して丸めたy座標も記録する。口唇面積則とセルの面積集約は既存の独立計算を使う。一時ビルドの観測は各条件の通常CLI、保存済みPCM、前回の断面観測に照合する。 [観測器](../tools/tsp_fk61_ray43_observation.py)・[独立比較の入口](../tools/measure_tsp_fk61_ray43_intersection.py)

## 実測

描画前は3条件とも原点［5.60088, 3.6］cm、方向［0, 1］で、上側の交差距離は3.6177906976744194 cmだった。下側には下唇内面の7標本のうち添字1→2を結ぶ線分を採用した。同じ番号の線分でも、固定上流と試験版で端点座標に差があった。試験版の始点だけを上流に揃えると、下側の交差距離が2.604158750658351 cmから上流の2.604158750658352 cmへ移り、補正前の隙間、測定線43の面積、節点42の平均断面積も上流に一致した。終点だけの交換では同じ交点が続いた。両版の実際の線分で有理数から直接計算したyを最後に丸めても、上流6.204158750658352 cm、試験版6.204158750658351 cmの差が再現された。 [線分と交換結果](../runs/tsp-fk61-ray43-intersection-20261123-repeat/summary.json)

採取後の比較では、下唇内面の始端・終端と各実装のオフセットから4制御点を復元した。復元した制御点は上流と試験版で一致した。上流の `bezier3` は各標本でBernstein基底の重みを求め、制御点の座標に掛けた4項を順に足す。研究版の `bezier` は隣接する制御点を同じ比で3段補間するde Casteljau法。添字1と2の標本を両方の演算順で計算すると、各版の実測した端点を再現した。試験版の線分をBernstein基底で評価した座標へ交換すると、下側交差と測定線43の面積、節点42の平均断面積が上流に一致した。上流の制御点をde Casteljau法で評価すると、試験版の交差距離と節点42の平均断面積を再現した。 [上流の3次曲線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L159)・[研究版の内側輪郭](../crates/vocal-core/src/anatomy.rs#L529)・[研究版の曲線評価](../crates/vocal-core/src/anatomy.rs#L565)・[評価方法の追加対照](../runs/stage7-evidence-update-20261123-fk61-ray43-intersection/summary.json)

この追加対照は記録した制御点から採用線分を再計算したもの。次は唇前端を揃えた試験版で、下唇内面の7標本だけを上流と同じ演算順で求め、通常CLIで初期座標、節点42の面積、3969の体積速度、全発話のPCMを照合する。

## 再実行

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296
../../.venv/bin/python tools/measure_tsp_fk61_ray43_intersection.py tsp-fk61-ray43-intersection-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から実行した。両実行で5判定とRustの2試験に通過し、観測した4時点の距離、交点座標、隙間が独立計算に一致した。3条件それぞれの通常CLI、観測器、保存済みPCMは全116,132フレームでビット一致し、観測・PCM・要約の6出力も実行間でバイト一致した。 [初回実行](../runs/tsp-fk61-ray43-intersection-20261123/manifest.json)・[別作業ディレクトリからの実行](../runs/tsp-fk61-ray43-intersection-20261123-repeat/manifest.json)
