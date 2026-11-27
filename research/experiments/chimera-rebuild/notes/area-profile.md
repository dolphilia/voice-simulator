# 半極格子上の断面積と中心線

## 固定上流の経路と計算順序

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`HumanAirway::apply` が `commit` を呼ぶ。`HumanVocalTract::compute` が測定格子の `d`（接触補正後の隙間、cm）を `area`（cm²）に換算し、中点から `s`（声門から中心線に沿った距離、cm）を付ける。`commit` は続けて `resample` を呼び、位置と面積の点列を管の断面積と最小狭窄へ割り当てる。この単位ではその入力となる格子上の断面積と距離を扱う。[気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[格子上の面積と距離](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1185)・[セルへの割り当て](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)

咽頭では `A=2d^1.4`。口腔では `2.6d^1.4` を基本とし、中点が舌先より前へ出る0〜0.4 cmの区間で `1.6d^1.4` に滑らかに移す。歯と唇の領域では、切歯から前方0.45 cmまでの距離で線形補間し、歯列の `2d^1.4` から、縦径が隙間 `d`、横径が `1.1+(4.6−1.1)·lip_spread` cmの楕円断面に移す。口腔前方と咽頭で異なる係数を使うため、同じ矢状面の隙間でも面積は領域で変わる。[面積換算の既定値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L668)・[唇の横幅と面積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1080)

全点を換算した後、中間の各点を後方から前方へ走査し、面積が両隣の大きい方の1.35倍を超えればそこまで下げる。左側に参照する値には直前の更新を含む。その後、舌の横を通る開口の制御値 `lateral` が正なら、口腔と前方の点で中点が舌先の1.4 cm以内にあるものに `0.35·lateral` cm²の下限を設ける。平滑化後の面積だけを変え、中点の座標や隙間の値は再計算しない。[ピーク抑制と舌側面](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1204)

成人男性の最初の `s` は喉頭蓋付近までの2.4 cm。以降は前後の中点間を直線で結ぶ距離を順番に足す。最初の口腔点は咽頭の終端、最初の垂直線は切歯位置、最終点は唇の位置と声道全長を表す。上流の `no_area_jumps_on_the_way_between_calibrated_vowels` は較正済み母音間を補間し、セルの面積に急な変化がないかを調べる。この単位では前段の格子値と中心線を公開フレームから直接観測する。[中心線と境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1222)・[母音間の形状テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L155)

## 実装前に登録した比較

固定上流と独立計算で成人男性の静止1フレームを6条件確認する。領域点数は咽頭19、口腔24、歯・唇6。点と距離は `10⁻⁹ cm`、面積は `10⁻⁹ cm²` 未満の差で照合する。各点の抑制前後の面積、舌側面で増える点、閉鎖位置、最初と最後の距離も記録する。

| 条件 | 予測 |
| --- | --- |
| 中立 | 声道長17.12〜17.14 cm、唇の断面積1.56〜1.58 cm²。[ケース](../cases/area-neutral.json) |
| 唇を横に広げる | 最終点の隙間は約0.7013 cm。唇の面積は2.52〜2.55 cm²へ増える。[ケース](../cases/area-wide-lips.json) |
| 唇の圧縮 | 前方の点46〜48で面積が0になる。[ケース](../cases/area-compressed-lips.json) |
| 舌体が口蓋に重なる | 点20〜28で面積が0。点17の孤立ピークを抑える。[ケース](../cases/area-closed-roof.json) |
| 舌先を上げる | 最小面積は0.19〜0.21 cm²で、点42のピークを抑える。[ケース](../cases/area-raised-tip.json) |
| 舌側面の開口 | 舌先を上げる条件に `lateral=0.8` を追加し、点38・39を0.28 cm²へ広げる。[ケース](../cases/area-lateral.json) |

## 実装と結果

Rustの `area_profile` は接触補正の格子から各点の面積と `s` を求める。`area` はこの値と接触補正前後の隙間をCSVへ書き、`inspect` は各境界を記録する。独立計算は `geometry` の舌先と切歯、`contact` の補正済み格子を入力に使う。同じ輪郭と隙間を入力として換算と距離を調べられるよう、換算直後、ピーク抑制後、舌側面の開口を含めた面積を `independent-area.csv` に保存した。上流と同じ順序で走査し、距離はNumPyで中点間の長さを累積した。[Rustの断面プロファイル](../crates/vocal-core/src/anatomy/area.rs)・[独立比較](../tools/measure_area.py)

| 条件 | 声道全長 | 最小面積 | 唇の面積と観測 |
| --- | ---: | ---: | --- |
| 中立 | 17.1296 cm | 1.5699 cm² | 唇1.5699 cm²、咽頭終端は8.8306 cm、切歯は16.2298 cm。[結果](../runs/area-neutral-20261119-a/summary.json) |
| 唇を横に広げる | 17.0838 cm | 2.1716 cm² | 唇2.5338 cm²、前端の隙間は中立と同じ0.7013 cm。[結果](../runs/area-wide-lips-20261119-a/summary.json) |
| 唇の圧縮 | 16.9645 cm | 0 cm² | 最後の3点が閉じた。[結果](../runs/area-compressed-lips-20261119-a/summary.json) |
| 舌体が口蓋に重なる | 19.0865 cm | 0 cm² | 点20〜28が閉じ、点17は1.0962から0.6418 cm²へ抑制された。[結果](../runs/area-closed-roof-20261119-a/summary.json)・[独立計算CSV](../runs/area-closed-roof-20261119-a/artifacts/independent-area.csv) |
| 舌先を上げる | 17.6603 cm | 0.2008 cm² | 点42は3.5277から3.2140 cm²へ抑制された。[結果](../runs/area-raised-tip-20261119-a/summary.json) |
| 舌側面の開口 | 17.6603 cm | 0.2800 cm² | 点38・39の面積が増え、中点、隙間、`s` は舌先を上げた対照と一致した。[結果](../runs/area-lateral-20261119-a/summary.json) |

6条件の全90項目が通過した。固定上流との差は断面積で最大 `4.67×10⁻¹⁴ cm²` 未満、格子上の距離で `5.33×10⁻¹⁵ cm` 未満。独立計算との差は断面積で `8.89×10⁻¹⁶ cm²` 未満、距離で `7.11×10⁻¹⁵ cm` 未満だった。上流の較正済み母音間の連続性試験も通過した。候補側の照合は固定姿勢の格子上までで、管のセルに割り当てた面積や母音遷移は今後検証する。[中立の実行記録](../runs/area-neutral-20261119-a/manifest.json)・[舌側面の実行記録](../runs/area-lateral-20261119-a/manifest.json)
