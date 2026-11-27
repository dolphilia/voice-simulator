# FK61_01の節点42から口端に伝わる初期流量差

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行計測では、唇前端を揃えた試験版の口端流量を内部標本3972で交換すると、出力フレーム1987までのPCMが固定上流に一致した。節点42の圧力、枝42→43、終端負荷の順に差の伝搬を追う。固定上流・標準研究版・唇前端を揃えた試験版に同じ本文と発声設定を渡す。 [先行する放射の計測](tsp-fk61-lip-front-radiation.md)・[事前登録](../cases/tsp-fk61-lip-front-terminal-branch.json)

## 読解と観測位置

固定上流は `HumanVoice::render` から、研究版は `ArticulatedVoice::step` から気道の更新に入る。比較したレンダーでは、出力48 kHzに対して気道を96 kHzで進める。枝41→42と42→43はともに直列枝で、流量［cm³/s］の正方向は節点番号が増える向き。両端の旧圧力から差を取り、乱流の圧力源と前標本の運動量に由来する圧力を足して駆動圧［dyn/cm²］を作る。線形項は慣性を刻み時間で割った項と粘性抵抗の和。狭い側から出る噴流の損失は流量の二乗に比例し、駆動圧の符号で順方向・逆方向の係数を選ぶ。固定上流は慣性が減ったときだけ現在の慣性と旧流量の積に運動量を置き換え、内部レートを掛ける。研究版は旧値と新値の小さい方の慣性を刻みで割ってから旧流量を掛ける。物理式を共有する両実装でも、この演算の順序と枝係数の違いは倍精度の結果に残り得る。 [上流の発話器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の枝](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L922)・[研究版の発話器](../crates/vocal-core/src/voice.rs#L583)・[研究版の枝](../crates/vocal-core/src/airway/network.rs#L189)

枝更新の後、両節点で旧圧力から壁振動の速度と変位を進め、壁面積［cm²］と速度［cm/s］の積を体積収支から引く。節点42のコンプライアンス `C`［cm⁵/dyn］は節点体積を空気の体積弾性率 `ρc²` で割った値。旧圧力へ `(Δt/C) × 正味流量` を足す。口端節点43では、並列R–L負荷と圧力を中点法で同時に解く。開口が小さくなり負荷の慣性が増したときは、前標本の負荷流量を慣性の比で補正してから進める。口端成分は負荷に流れた抵抗枝・慣性枝の中点の流量の和で、節点の総流入や直列枝の流量とはそれぞれ異なる量である。 [上流の壁と節点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1054)・[研究版の壁と節点](../crates/vocal-core/src/airway/network.rs#L746)・[研究版のR–L負荷](../crates/vocal-core/src/airway.rs#L89)

観測器を一時チェックアウトにだけ適用した。3952〜3979を採取し、両枝の圧力源・係数・過去状態・新流量、両節点の壁状態、節点42のコンプライアンスを保存する。二次方程式、壁、R–L負荷の独立計算には倍精度丸めを明示した既存の検証器を使う。3968直前の状態から3975まで両節点を連続更新し、左境界から入る枝41→42の流量と局所の体積注入には採取値を使う。PCMへの影響は壁面・鼻端の放射を試験版のままにした出力段の対照として扱う。上流の四分の一波長、狭窄、閉塞、二次損失、研究版の幾何補間に対応する試験を通常の入口で実行する。 [観測器](../tools/tsp_fk61_terminal_branch_observation.py)・[独立計算](../tools/measure_tsp_fk61_lip_front_terminal_branch.py)・[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[上流の極端条件の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 実測

3968の節点42の正味流量は固定上流・試験版ともに −9.810485535087402×10⁻⁸ cm³/s。試験版のコンプライアンスを 6.561655806081381×10⁻⁷ から上流の 6.561655806081375×10⁻⁷ cm⁵/dyn に換えると、圧力は上流の −1.557420271304811×10⁻⁶ dyn/cm² を再現した。最初に枝42→43の流量が分かれた3969で、試験版との差は 1.3234889800848443×10⁻²³ cm³/s。左圧力を上流と揃えると流量は上流の値から2 ULPずれた。左圧力と枝の係数を併せて揃えると、試験版の演算順でも上流の −7.83686516136922×10⁻⁸ cm³/s を再現した。ここでは旧枝流量と乱流の圧力源は0で、枝の運動量の換算順は流量差を生んでいない。 [圧力・枝の記録](../runs/tsp-fk61-terminal-branch-20261123-repeat/summary.json)

同じ3969で、節点42の平滑後の体積注入は試験版で +1.6371791617710019×10⁻¹⁶ cm³/sずれた。口端節点43では体積注入が一致した。3970の枝42→43の差は +8.221095321769346×10⁻¹⁷ cm³/sとなった。事前登録したコンプライアンス、枝41→42の境界流量、枝42→43の係数の8通りの交換は、すべて1987のPCM差を残した。 [各標本の収支と登録済み対照](../runs/tsp-fk61-terminal-branch-20261123-repeat/summary.json)

採取後に追加した対照では、節点42の体積注入を内部3968〜3975で交換すると、出力1987までのPCMが上流に一致した。3969の注入1標本だけを交換した場合は、3972の口端流量差が縮み、1987のPCM差は残った。体積注入と左境界流量を同時に交換した場合、3972の口端流量差は 5.29×10⁻²³ cm³/s に縮んだ。コンプライアンスと枝係数も交換すると、その標本の口端流量が上流に一致した。口端流量だけを出力段に反映する局所比較であり、全発話でこれらの交換が及ぼす効果は未測定。 [追加の介入結果](../runs/tsp-fk61-terminal-branch-20261123-repeat/summary.json)

## 再実行

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296
../../.venv/bin/python tools/measure_tsp_fk61_lip_front_terminal_branch.py tsp-fk61-terminal-branch-new
```

初回は倍精度の出力配列をfloat32専用のビット比較に渡したため、保存済み観測との照合だけが失敗した。節点・口端の採取や二節点の再計算は初回から一致した。配列の型・形・バイト列を直接比較するように直し、初回の生データを使った再解析でも全判定に通過した。判定の要件と予測は保持した。 [初回の判定記録](../runs/tsp-fk61-terminal-branch-20261123-check/summary.json)・[初回のマニフェスト](../runs/tsp-fk61-terminal-branch-20261123-check/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。修正後は研究ワークスペースと `/tmp` の各実行で5判定とRustの11試験に通過した。各条件の通常CLI、観測器、保存済みPCMは全116,132フレームでビット一致した。枝、壁、節点、放射と出力段の観測、要約を含む18ファイルが両実行でバイト一致した。 [研究ワークスペースでの実行](../runs/tsp-fk61-terminal-branch-20261123/manifest.json)・[別ディレクトリからの再実行](../runs/tsp-fk61-terminal-branch-20261123-repeat/manifest.json)

次は3969の節点42について、新旧体積差、近隣からの流入配分、2段平滑を順に比較する。まず3968・3969の節点42と隣接節点41、43に絞り、体積差を流量に換算した値と配分後の注入を照合する。 [上流の体積注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[研究版の体積注入](../crates/vocal-core/src/airway/network/geometry.rs#L110)
