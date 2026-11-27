# 固定三分岐と狭窄

## 上流の経路と状態

`tests/airway_adversarial.rs::nearly_closed_three_way_junction_stays_stable_at_the_working_cfl` では 8 cm・20 セルの管を三つ追加し、入口管の末端と出口管の各先頭を `AirwayNetwork::connect` で結ぶ。二つの出口に `add_radiation` で並列 R–L 負荷を付ける。`finalize` は接続辺を数え、次数3以上を分岐節点として記録する。上流テストは狭窄までの面積補間と 400 サンプルの正弦駆動を含む。この工程では同じ分岐形状の開口固定条件を採用し、微小な体積インパルスで枝の更新と負荷を検証する。時系列の参照は上流の公開状態を読み出す専用プローブで取得する。[上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)・[接続と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

圧力 `p`（dyn/cm²）はセル中心、体積速度 `U`（cm³/s）はセル間の有向枝。枝の慣性 `L` と粘性抵抗 `R` は両端の半区間を加算する。固定断面の二次損失は、流れの向きに応じ `k = ρ(1/A_left − 1/A_right)²/2` を拡大に使い、縮小ではその0.1倍。旧圧力差と旧流量で `[(L/Δt)+R]U_new + k|U_new|U_new = Δp_old + (L/Δt)U_old` を解き、各枝の流量を入口セルから引き、出口セルに足す。圧力は全枝の更新後に進める。[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

分岐の有効コンプライアンスは `C_eff = max(C, Δt²·Σ(1/L)/2.4)`。`C = max(A, 0.02 cm²)·Δx/(ρc²)` と合わせて使う。固定対称ケースのセル長0.4 cm・96 kHzでは `c·Δt/Δx ≈ 0.91146`。全断面が3 cm²の場合、分岐の下限が幾何から得る `C` より約3.85%大きい。分岐セルの断面を0.002 cm²にすると、接続枝の慣性が大きくなって `Σ(1/L)` が下がり、`C_eff` はここでは体積側の下限で決まる。この判定は次数と局所の素子に依存する。[上流の節点更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

## 比較前に登録した予測

1回の注入体積は0.001 cm³。入口から出口の節点まで39本の枝を通るため、口端放射の最早サンプルは0始まりで39。全断面が同じ対称系では枝の二次損失はゼロ。左右は同じ入力と負荷を持つため、左右の分岐枝流量と口端放射流量は一致する。固定狭窄でも左右は同じ条件であり、対称性が保たれると予測する。分岐の圧力変化と流量の収支、両方向の二次損失、上流の比較時系列は各参照系列のピークに対する誤差で判定する。[固定対称ケース](../cases/symmetric-junction.json)・[固定狭窄ケース](../cases/narrow-junction.json)

固定対称ケースでは、圧力を節点の未知量として NumPy で離散周波数領域の回路方程式を独立に解く。`z = exp(jωΔt)`、`d = 1 − z⁻¹` とおくと、節点のシャントは `C_eff·d/Δt`、枝は `z⁻¹/[R+(L/Δt)d]`。並列 R–L の終端は時刻中点を使うので、`(1+z⁻¹)/2·[1/Rᵣ+Δt(1+z⁻¹)/(2Lᵣd)]` となる。両出口の流量を加え、有限長の時系列から求めた複素 FFT ビンと比べる。固定狭窄では二次の項が有効なため、この線形判定は対称ケースに適用する。
