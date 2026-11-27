# 矢状面から隙間を測る半極座標格子

## 上流の入出力と測定順序

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanAirway::apply` は `commit` を呼ぶ。`HumanVocalTract::compute` で得た輪郭と格子が `resample` に渡され、咽頭・口腔の管へ変換される。この単位では輪郭から格子へ進む箇所を扱う。内壁・外壁は頭部座標の折れ線（cm）。各測定線を始点 `o` と単位方向 `d` で定義し、`o+t·d` の `t`（cm）に沿って交差を探す。出力は内側の測定点、外側の交点、それらの中点、補正前の隙間 `GridSample::ray`（cm）と領域番号。測定後に `GridSample::d` が舌や唇の接触で補正され、面積計算に使われる。[気道の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[上流の格子](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L935)

成人男性では咽頭を12本の水平線で前から後ろへ測る。口腔では31本を180°から36°へ回し、途中で測定線の始点を奥から前へ三次の滑らかな重みで動かす。扇形のうち150°を超える線は咽頭側に入る。最後に6本の垂直線を上切歯から唇に向かって配置する。外壁の交差が見つからない線は格子に加わらない。[格子の配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1025)

`ray_polyline` と `ray_crossings` は、線の左右で符号が変わる輪郭線分だけを交差として数える。線上の頂点は同じ側に数えるため、かすめるだけなら交差は0件か同じ距離の入口・出口になり、横切る場合は1件になる。`measure` は始点に最も近い外壁の交点から、咽頭と歯・唇では測定範囲内で最も遠い内壁の交点を引く。内壁が外壁を越えた場合は隙間を0にする。[交差の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L104)・[交点の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L988)

扇形の線は舌の内側から始まるのが通常で、最初に舌から出る点を内側の境界にする。始点が舌から外れた場合は逆向きの交差を探す。線が途中で舌を再び横切る場合は、入口と出口の間の組織の厚さを空気の距離から差し引く。出力上の内側の測定点はその厚さの分だけ調整した点になる。垂直線が下唇の端より前へ出る場合は、唇の外面を延長して下側の点を再構成し、引き込みの強さと端からの距離で開きを滑らかに増す。[扇形の線の交差](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L948)・[下唇より前の垂直線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1059)

上流では頂点をかすめる線で組織が増減しないことと、下唇が上切歯の下へ入るときに断面積が飛ばないことを検査する。今回の比較は公開フレームの `grid.ray` と座標を用い、NumPyでは線分の端点の高さを補間して交点を求める。[上流の頂点テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L206)・[上流の下唇のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L236)

## 実装前に登録した比較

すべて成人男性の固定1フレーム。先に実装済みの輪郭を独立計算に通し、咽頭・口腔・歯と唇の領域別の点数を19・24・6と予測した。座標と隙間の絶対差は各列 `10⁻⁹ cm` 未満とする。

| 条件 | 予測 |
| --- | --- |
| 中立 | 最小の隙間は唇付近の0.78〜0.80 cm。[ケース](../cases/grid-neutral.json) |
| 顎開き | 歯の近くで中立より隙間が増え、最小は0.80〜0.81 cm。[ケース](../cases/grid-open-jaw.json) |
| 前下方の舌体と上げた舌先 | 扇形の線17本で逆方向を測り、1本で途中の組織の厚さを差し引く。[ケース](../cases/grid-shifted-tongue.json) |
| 口蓋と重なる舌 | 最小の隙間が0になり、その位置の内側と外側の点が重なる。[ケース](../cases/grid-closed-roof.json) |
| 上切歯の下へ引き込んだ下唇 | 垂直線4本が下唇の前に出る。最小の隙間は0.22〜0.24 cm。[ケース](../cases/grid-labiodental.json) |

## 実装と結果

Rustの `measurement_grid` は矢状面フレームを読み、領域ごとの測定線を生成する。交差距離は行列式で計算し、扇形の線で距離が等しい交差は輪郭順を保つ。CSVの `ray_cm` は上流の公開フレームと同じ観測点を使う。Pythonは輪郭の各線分を測定線と直交する座標へ投影し、端点を線形補間して交差を計算する。頂点通過とかすめ、途中の組織の差し引きはRustの単体テストにも登録した。[Rustの測定格子](../crates/vocal-core/src/anatomy/grid.rs)・[比較器](../tools/measure_grid.py)

| 状態 | 領域1／2／3の点数 | 最小の隙間と観測 |
| --- | --- | --- |
| 中立 | 19／24／6 | 0.7871 cm。0始まりの最終行48。[計測](../runs/grid-neutral-20261119-a/summary.json) |
| 顎開き | 19／24／6 | 0.8034 cm。上切歯に最も近い垂直線では1.1263 cmから1.5098 cmへ増加。[計測](../runs/grid-open-jaw-20261119-a/summary.json) |
| 前下方の舌体と上げた舌先 | 19／24／6 | 0.3757 cm。17本で逆向きの交差を探し、行37の60°の線では途中の舌組織0.3252 cmを引いた。[計測](../runs/grid-shifted-tongue-20261119-a/summary.json)・[座標CSV](../runs/grid-shifted-tongue-20261119-a/artifacts/trace.csv) |
| 口蓋と重なる舌 | 19／24／6 | 0 cm。行20〜28の9本で内側と外側の点が重なった。[計測](../runs/grid-closed-roof-20261119-a/summary.json) |
| 上切歯の下へ引き込んだ下唇 | 19／24／6 | 0.2294 cm。下唇の端より前の4本で外面を延長し、前端に近い線では2.7964 cmまで広がった。[計測](../runs/grid-labiodental-20261119-a/summary.json) |

5条件とも固定上流との全列の最大差は `3.56×10⁻¹⁵ cm` 未満、独立計算との差は `2.23×10⁻¹⁵ cm` 未満で、全50項目が通過した。上流の頂点をかすめる条件と下唇を引き込む条件のテストも通過した。研究ケースで照合した範囲は固定姿勢の `ray` と測定点。音響断面と接触後の `d` は今後実装する。[中立の実行記録](../runs/grid-neutral-20261119-a/manifest.json)・[引き込んだ下唇の実行記録](../runs/grid-labiodental-20261119-a/manifest.json)
