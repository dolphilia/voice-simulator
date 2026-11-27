# FK61_01の節点42で体積注入が分かれる演算

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行計測では、唇前端だけを揃えた試験版の節点42で、平滑後の体積注入を内部3968〜3975の8標本分交換すると、局所再計算で出力フレーム1987までのPCMが上流に一致した。今回はその入力の起点を、標準研究版を含む3条件で照合する。 [先行計測](tsp-fk61-lip-front-terminal-branch.md)・[事前登録](../cases/tsp-fk61-node42-volume-source.json)

## 読解と再計算

上流では `HumanVoice::render` が48 kHzの出力1フレームごとに `AirwayNetwork::step` を2回走らせる。`set_tube_targets` と制御ブロックの開始で面積・最小面積・長さの補間を用意し、内部標本ごとに面積を非負へ、最小面積を平均断面積以下へ制限する。節点体積は平均断面積［cm²］に下限を設けてセル長［cm］を掛けた値［cm³］。旧体積と新体積の差を96 kHzで換算して体積速度［cm³/s］を作る。縮む向きが正。研究版の経路は `ArticulatedVoice`、`AirwayNetwork`、`MovingAreas::set_targets` と `MovingAreas::step`。研究版の換算は刻み時間での除算。観測器を一時ビルドへ組み込み、通常CLIのPCMと、以前採った節点・口端・出力段を照合する。 [上流の発話器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の補間先と気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L647)・[研究版の気道更新](../crates/vocal-core/src/airway/network.rs#L675)・[研究版の体積源](../crates/vocal-core/src/airway/network/geometry.rs)

最小断面積が0.12 cm²未満のセルでは、最小断面積を閾値で割った比 `s` から、元の節点へ残す割合を `s² × (3 − 2s)` で求める。残りは、現在値または補間先の最小断面積が閾値以上の近隣で等分する。配分先の現在値は節点を更新する順序に依存する。独立計算では接続表の順に加算し、先に更新した節点と更新前の節点の断面積をその時点の値で参照する。近隣へ配れなかった分は配分されず、そのセルに残す割合だけが注入に入る。全節点の配分が済んだ後、60 Hz相当の一次平滑を直列に2段適用する。係数を `c` とすると各段は旧値に `c × (入力 − 旧値)` を足し、第2段は第1段の新値を読む。 [上流の配分と平滑](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[研究版の配分と平滑](../crates/vocal-core/src/airway/network/geometry.rs#L110)

3952〜3979の全節点で、更新前の幾何と状態、実際に計算された生の体積速度、配分先と配分量、平滑後の流量を照合する。上流の閉鎖腔の圧縮試験は体積変化と圧力の対応を、研究版のポート更新試験は面積・長さの補間が別の更新で中断されないことを確認している。3968〜3975の局所再計算では節点42の生の体積速度だけを操作し、平滑後の注入から口端負荷までを再計算する。PCMを比較するときは試験版の壁面・鼻端の放射を保持する。 [上流の閉鎖腔試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L55)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)・[観測器](../tools/tsp_fk61_node_volume_observation.py)・[計測入口](../tools/measure_tsp_fk61_node42_volume_source.py)

## 実測

3条件とも、調べた28標本で近隣への配分は0件だった。節点42の3969の最小断面積は約1.730 cm²で、配分を始める閾値0.12 cm²を上回る。小開口で実際に配分が生じる条件は、既存の `moving-aperture-release` で別途照合している。 [今回の観測](../runs/tsp-fk61-node42-volume-source-20261123-repeat/summary.json)・[小開口の既存対照](moving-area.md)

3968の節点42では固定上流と試験版の各体積は異なり、丸め済みの体積の差はどちらも −6.6527991116061×10⁻⁸ cm³ だった。3969で体積差が −6.652799322548475×10⁻⁸ と −6.652799311446245×10⁻⁸ cm³ に分かれた。差はその体積域の倍精度1 ULPにあたる 2⁻⁵³ cm³。丸め済みの体積の引き算は両版で有理数による引き算に一致し、時間換算も96,000を掛ける式と刻みで割る式で同じ値を返した。面積と長さの積をそれぞれ丸める段階が、ここでの体積差に効いている。 [節点42の系列と再計算](../runs/tsp-fk61-node42-volume-source-20261123-repeat/summary.json)

3969で試験版から上流を引いた生の体積速度差は +1.0658141036401503×10⁻¹¹ cm³/s。面積と長さの両方を記録済みの値に固定し、前後の積を有理数で計算してから引くと、差は −1.734723475976807×10⁻¹⁸ cm³/s になった。平滑の1段目と2段目には同じ3969から差が出た。標準版は3969の体積速度と平滑の2段が上流と一致し、この標本での分岐は唇前端を揃えた試験版に現れた。 [三条件の比較](../runs/tsp-fk61-node42-volume-source-20261123-repeat/summary.json)

| 独立計算で移し替えた入力 | 3972の口端流量差（試験版 − 上流、cm³/s） | 出力1987までのPCM |
| --- | ---: | --- |
| 試験版の入力 | +1.3877×10⁻¹⁶ | 1987で差 |
| 節点42の生の体積速度を3969だけ上流へ交換 | −1.4866×10⁻¹⁶ | 一致 |
| 節点42の生の体積速度を8標本とも上流へ交換 | −1.2526×10⁻¹⁶ | 一致 |
| 試験版の面積と長さから積の途中の丸めを省いて計算 | +2.0233×10⁻¹⁷ | 一致 |

先行計測で平滑後の3969だけを交換した場合は1987のPCM差が残った。今回の平滑前の1標本交換は2段の状態を更新するため、この後の標本にも影響が残り、1987で隣接するfloat32値の中点をまたいだ。局所の4条件の比較で、全発話への介入は未実施。 [局所再計算](../runs/tsp-fk61-node42-volume-source-20261123-repeat/summary.json)・[平滑後の1標本交換](tsp-fk61-lip-front-terminal-branch.md#実測)

## 再実行

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296
../../.venv/bin/python tools/measure_tsp_fk61_node42_volume_source.py tsp-fk61-node42-volume-source-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` の各実行で5判定・Rustの11試験に通過した。通常CLI・観測器・保存済みPCMは、各条件で全116,132フレームがビット一致し、実行ログを除く21出力が再実行でもバイト一致した。 [初回実行](../runs/tsp-fk61-node42-volume-source-20261123/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-fk61-node42-volume-source-20261123-repeat/manifest.json)

体積計算には3968の時点で節点42の断面積差が入っている。長さは3968・3969の両版で一致した。次は補間開始時の現在断面積と目標断面積を分け、口端の1セル手前に入る測定線と面積の集約を確認する。 [全節点の幾何観測](../runs/tsp-fk61-node42-volume-source-20261123-repeat/artifacts/trial-geometry.csv)・[既存の口端セルの観測](tsp-fk61-lip-area-origin.md)
