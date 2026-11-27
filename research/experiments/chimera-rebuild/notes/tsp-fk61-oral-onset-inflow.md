# FK61_01の発声開始時に節点41へ入る流量

[前回](tsp-fk61-branch-first-difference.md#実測)は、口端に入る枝42→43の初差3971から、節点42の3970の圧力差を経て、枝41→42までさかのぼった。節点41は3968に体積差から微小な圧力差を持ち、3969には正味流入そのものが分かれた。今回は枝40→41を含む口腔の6枝と7節点を採り、3969の節点41の流量収支を確認する。固定上流、従来の研究版、下唇内面の評価順を上流に揃えた試験版を比較する。内部96 kHz、出力48 kHz。番号は0始まり。

## 呼び出し経路と計算する量

固定上流ではテキストを発話計画に通し、`HumanVoice::render` で制御・肺圧・声門開口を更新して `AirwayNetwork::step` に入る。口腔は、咽頭の後に加えた直列の管で、鼻腔へ分かれるポートは咽頭側にある。今回の節点38〜42で測るのは、各節点への体積源と左右の直列枝・壁を通じた流量。 [上流テキストCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[口腔と鼻腔の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L150)

断面積 `A` は cm²、セル長 `d` は cm。体積は断面積に下限を適用して長さを掛けた `V=max(A,A_floor)d` で、単位は cm³。内部標本の補間で断面積と長さを更新し、体積速度は `(V_old−V_new)/Δt` で得る。上流は体積差に内部レートを掛け、研究版は時間刻みで割る。閉鎖に近いセルでは体積速度の一部を開いている隣接セルに配分する。配分後の流量 `s` を、古い状態を `z₁,z₂`、係数を `α` とする二段平滑に通す。平滑後の流量が節点への注入 `q₀` になる。 [上流の体積速度と平滑](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L833)・[研究版の体積源](../crates/vocal-core/src/airway/network/geometry.rs#L110)

\[
z'_1=z_1+\alpha(s-z_1),\qquad z'_2=z_2+\alpha(z'_1-z_2).
\]

枝は前の圧力と、前の流量・慣性が作る履歴項を読み、線形抵抗と方向別の二次損失を含む根を解く。節点へ入る左の枝流量を加え、出ていく右の枝流量と壁流量を引く。コンプライアンスを `C=V/(ρc²)` とし、圧力を `p_new = p_old + (Δt/C) q` で進める。流量の単位は cm³/s、圧力は dyn/cm²。枝は節点圧を更新する前に計算するため、3968で生じた節点圧の差が枝に入るのは3969。 [上流の枝・壁更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[独立した枝の根](../tools/measure_fixed_voice_glottal_branch.py#L261)

固定上流の `sealed_cavity_compression_follows_the_linearised_adiabatic_law` は体積を5%減らして圧力を理論値と比較する。定常狭窄と閉鎖・再開口の試験も、通常CLIの描画と同じ実行で使う。研究版の `geometry_ramp` は、声門ポートの即時更新中にも面積と長さの補間が進むかを確認する。 [上流の密閉腔試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 比較条件

3964〜3983で口腔の節点37〜43、枝37→38から42→43までと、節点38〜43の壁を採る。コンプライアンスと圧力更新は節点38〜42で測る。計測した断面積と長さから体積を再計算し、前後の体積差と配分後の流量を照合してから二段平滑を検算する。3968では節点40の古い面積と長さの積を丸めない独立計算も行う。3969では枝40→41の入力と節点41の収支を個別に交換する。先行計測との重複する節点41〜43と2枝・口端負荷を比較し、採取によるPCMへの影響を通常CLIで確認する。 [事前登録](../cases/tsp-fk61-oral-onset-inflow.json)

## 実測

3969の節点41では、試験版と固定上流の正味流入差は、上流から試験版を引いて +1.6794×10⁻¹⁶ cm³/s。枝40→41の差が +1.6794×10⁻¹⁶ cm³/s、枝41→42の差が −1.3235×10⁻²³ cm³/s だった。節点41の体積源と壁流量は一致した。枝40→41だけを上流の値へ交換すると、節点41の更新後圧力の残差は −4.24×10⁻²² dyn/cm² に縮んだ。

| 伝わった量 | 時刻と位置 | 上流から試験版を引いた差 |
| --- | --- | ---: |
| 丸めた体積から求めた体積速度 | 3968・節点40 | +2.1316×10⁻¹¹ cm³/s |
| 二段平滑後の体積源 | 3968・節点40 | +3.2744×10⁻¹⁶ cm³/s |
| 更新後の圧力 | 3968・節点40 | +2.9656×10⁻¹⁵ dyn/cm² |
| 枝の流量 | 3969・枝40→41 | +1.6794×10⁻¹⁶ cm³/s |
| 更新後の圧力 | 3969・節点41 | +2.0951×10⁻¹⁵ dyn/cm² |

3968の節点40で、体積源だけを上流に交換した圧力変化は +2.9656×10⁻¹⁵ dyn/cm²、コンプライアンスだけを交換した変化は +4.24×10⁻²¹ dyn/cm² だった。3969の枝40→41では、両端の圧力の交換で流量差が +1.32×10⁻²² cm³/s の残差に縮んだ。枝の慣性と損失を交換した効果は −1.59×10⁻²² cm³/s だった。枝40→41の更新前の流量と運動量は両版でゼロだった。 [圧力と枝の個別交換](../runs/tsp-fk61-oral-onset-inflow-20261123-registered/summary.json)

### 体積の丸め

節点40の3968の体積速度は、丸めた体積の差を使うと上流で 0.018958212578468192、試験版で 0.01895821255715191 cm³/s だった。採取した前後の断面積と長さを有理数として読み、積を丸めずに差を取ると、両版の体積速度差は +5.15×10⁻¹⁸ cm³/s だった。丸めた体積で求めた2.13×10⁻¹¹ cm³/sの差の約414万分の1に当たる。両版の長さは同じで、面積の差は前後にほぼ共通して残っていた。

採取データに `(A_old−A_new)d_old + A_new(d_old−d_new)` を適用する独立計算でも、上流と試験版の体積速度差は約7×10⁻¹⁸ cm³/sになった。次はこの展開式を節点40の3968だけに適用した一時ビルドを比較する。先行の混合体型で使った展開式を再利用し、局所の誤差、節点41・42と口端への伝搬、全発話のPCMで最初に分かれる時刻を調べる。通常版と試験版は別の実行として保存する。 [既存の差分式の比較](duet-mixed-volume-difference.md#実測)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。全116,132フレームの通常CLI・観測版・保存済みPCMを各版でビット照合した。研究ワークスペースと `/tmp` から独立に実行し、各5判定・Rustの11試験が通過して、採取系列17点と要約がバイト一致した。採取結果はRTL9210B-CGに保存した。 [初回マニフェスト](../runs/tsp-fk61-oral-onset-inflow-20261123-registered/manifest.json)・[再実行マニフェスト](../runs/tsp-fk61-oral-onset-inflow-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_oral_onset_inflow.py tsp-fk61-oral-onset-inflow-new
```
