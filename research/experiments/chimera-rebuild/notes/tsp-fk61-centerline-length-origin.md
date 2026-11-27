# FK61_01の中心線の累積距離を照合する

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。対象は最初の体積流量差を含む制御更新の直後、48 kHzの出力を1985フレーム完了した状態。測定線の番号は0始まり。先行計測では、口端セルの長さ目標が両実装で2.22×10⁻¹⁶ cm異なり、累積軸上位置の初差は測定線31にあった。 [事前登録](../cases/tsp-fk61-centerline-length-origin.json)・[先行する唇前端の計測](tsp-fk61-lip-front-origin.md)

## 読解と比較条件

固定上流の通常発話では、`HumanVoice::control` が調音姿勢を `HumanAirway::apply` に渡し、`HumanAirway::commit` で声道の輪郭と断面を更新する。`HumanVocalTract::compute` は光線と内壁・外壁の交点の中点を測定線の中央とし、喉頭蓋上部までの長さを初期値に隣接する中央間の距離を足す。距離は `geom::dist` から `math::hypot` を呼ぶ。最初の口腔の測定線の累積位置が口腔の起点、最後の測定線の位置が口腔の終点となる。音響計算用の口腔長にはクーラン数を0.97以内に収める下限があり、口端セルの長さ目標は下限適用後の長さを管のセル数で割った値。 [上流の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[上流の累積位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1221)・[上流の長さ目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L312)

研究版の `ArticulatedVoice` から `TractController` を介し、`SagittalModel::area_profile_from_contacts_reusing` が中心線の距離を足す。両実装は `libm 0.2.16` の `hypot` を使う。接触補正は光線に沿った隙間に作用し、その後の面積を変える。中心線距離は測定線の中点に基づく。試験版は測定線30と31の中点が事前登録した値に完全一致するときに、31のyだけを中心線距離へ渡す直前に交換する。光線の幾何、接触後の隙間と測定線上の断面積、面積の式が参照する中点は元の値を使う。調音の連続性試験と、気道セル長の補間を確認する既存試験も実行する。 [研究版の累積距離と面積](../crates/vocal-core/src/anatomy/area.rs#L74)・[長さの補間](../crates/vocal-core/src/airway/human.rs#L341)・[上流の連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L236)・[補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

各区間は座標差の二乗和の平方根［cm］である。観測した倍精度の座標を90桁の10進演算に渡して距離を確認し、実測した距離の倍精度のビットを順に加えて累積位置を再現する。初差の測定線では、内側で丸める前の加算を有理数で実行し、隣接する倍精度値の中点に対する位置を測る。

## 実測

測定線30の中心座標と累積位置は固定上流と標準研究版で一致した。31ではxが一致し、yが8.694229196147019 cmと8.694229196147017 cmに分かれた。30→31の実測距離は0.3472301809707857 cmと0.34723018097078556 cm。累積直前の9.759234199564155 cmにそれぞれの距離を足すと、丸め前の値は隣接する2つの倍精度値の中点の上下に5.55×10⁻¹⁷ cmずつ離れた。各区間の実測距離は90桁で計算した値から最大0.735 ULP以内だった。 [観測と独立計算](../runs/tsp-fk61-centerline-length-origin-20261123-repeat/summary.json)

| 値［cm］ | 固定上流 | 標準研究版 | 試験版 |
| --- | ---: | ---: | ---: |
| 測定線31の累積位置 | 10.106464380534941 | 10.106464380534940 | 10.106464380534941 |
| 口腔起点の累積位置 | 7.205057687121059 | 7.205057687121059 | 7.205057687121059 |
| 口腔端の累積位置 | 14.673527968791160 | 14.673527968791156 | 14.673527968791158 |
| 口端セルの長さ目標 | 0.4667793926043813 | 0.46677939260438106 | 0.46677939260438117 |

試験版では31のyを距離の計算だけで交換した。30→31の距離と31の累積位置が固定上流に一致し、累積位置の初差は31から34に移った。口腔端まで一致するという予測は外れ、口端セルの長さ目標の差は1.11×10⁻¹⁶ cmに減った。標準版と試験版のPCMは全116,132フレームでビット一致した。固定上流との最初の差は両方で1989、全発話の最大差は1.86265×10⁻⁹だった。 [試験版の観測とPCM](../runs/tsp-fk61-centerline-length-origin-20261123-repeat/summary.json)

この結果を受け、先行計測のフレーム1984の長さを始点に、128内部標本分の補間を3条件で独立に再計算した。登録された目標の差は標本ごとの増分にも現れた。始点に増分を足すときに同じ値へ丸められ、128個すべての予測上の現在長が3条件で一致した。最初の2標本の計算は、フレーム1985で実測した現在長と一致した。 [補間の再計算を含む監査](../runs/stage7-evidence-update-20261123-fk61-centerline-length-origin/summary.json)

次は唇前端の演算順序を揃えた試験版を使い、なお残る発話冒頭のPCM差を内部標本3968付近の各セルの体積流量と放射に照合する。

## 再実行

観測用のRustビルドはRTL9210B-CG上の一時チェックアウトに置く。固定上流、標準版、試験版の全測定線の観測と、通常CLIのPCM照合、試験版のPCMを保存する。 [計測入口](../tools/measure_tsp_fk61_centerline_length_origin.py)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` の各実行で3判定、上流の調音連続性試験、試験版の補間試験に通過した。座標観測3ファイル、試験版のPCM、PCMハッシュ、要約の6出力はバイト一致した。 [最初の実行](../runs/tsp-fk61-centerline-length-origin-20261123/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-fk61-centerline-length-origin-20261123-repeat/manifest.json)


```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_centerline_length_origin.py fk61-centerline-length-origin-new
```
