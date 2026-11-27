# 固定一様管の読解ノート

## 対象と測るもの

上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`tests/airway.rs` の `uniform_tube` が `AirwayNetwork::new` → `add_tube` → `add_radiation` → `finalize` を呼びます。入口セルの `ext_flow` に 1 サンプルだけ `fs` を入れると、注入体積は `fs·Δt = 1 cm³` です。`step()` の出力は体積速度の時間微分です。共鳴比較では時間応答の FFT を `2πf` で割り、線形計算が返す体積速度の比と同じ量を近似します。CLI の WAV 基準は別経路で、`render::vowels` などが `HumanVoice` を駆動しています。[一様管テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[上流 CLI のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs)

```text
入口流入 q → [p₀, C] ── U₀, L, R ── [p₁, C] ── … ── [p₃₉, C] → 並列の Rᵣ と Lᵣ
                                          セル中心の圧力                ↓
                                                             口端の Uᵣ と ΔUᵣ/Δt
```

## 状態と時間更新

- 物理定数は CGS で `ρ = 1.14×10⁻³ g/cm³`、`c = 35000 cm/s`、`μ = 1.86×10⁻⁴ g/(cm·s)`。セル長 `Δx = ℓ/N`、セルのコンプライアンス `C = AΔx/(ρc²)`、隣接セル間の慣性 `L = ρΔx/A`。固定一様管では両隣の半区間が等しく、上流の線形抵抗は `R = (2√(πA))Δx√(ρμω₀/2)/A²`（`ω₀ = 2π·700 s⁻¹`）。ここでの壁は剛体で、壁そのものの振動を切っても粘性抵抗は残る。[定数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/physics.rs)・[ネットワーク](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)
- 圧力 `p` は整数時刻、枝の体積速度 `U` は半時刻。毎ステップ初期化する正味流入に入口の外部流量を足す。旧圧力差で全枝を更新し、同じ `U` を上流セルから引き下流へ足す。均一な断面では二次損失の係数がゼロなので、枝更新は `U_new = (p_left − p_right + (L/Δt)U_old)/(L/Δt + R)` に簡約できる。口端以外は `p_new = p_old + (Δt/C)q_net`。圧力は dyn/cm²、流量は cm³/s。[`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)
- 口端の開口半径は `a = √(A/π)`。放射負荷の `Lᵣ = 8ρ/(3π²a)`、`Rᵣ = 128ρc/(9π²A)` を使う。節点の収支と `Lᵣ dU_L/dt = p` を旧・新の中点値で連立すると、`C(p_new−p_old)/Δt = q_net − (U_L,new+U_L,old)/2 − (p_new+p_old)/(2Rᵣ)`。これを新しい圧力について解いてから新しい `U_L` を求める。抵抗と慣性の平均流量の和を `Uᵣ` とし、前ステップとの差を `Δt` で割る。最終節点と放射の時間更新が結合するため、短い開口を動かす拡張でもここが比較点になる。[`AirwayNetwork::step` の節点更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)
- 最初の 4 モードの基準値は `fₘ = (2m−1)c/(4(ℓ+8a/(3π)))`。端補正は放射慣性を等価な管長に読み替えた量で、管全体を閉端・開端の近似で扱う。基準ケースの `c/(fs·Δx)` は約 0.8333。入口セルに有限体積のインパルスを入れた場合、枝が各ステップで一つずつ先へ影響を渡すため、40 セルでは放射差分の最初の非ゼロ値を 0 始まりのサンプル 39 と予測する。これは離散ステンシルの因果境界であり、主波の到達時間の定義とは区別する。[上流の 1/4 波長近似](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)

## 別経路の線形応答

`linear_elements` で静止形状から `C`、枝の `R,L`、口端面積を取り出し、`transfer_function` が各周波数で `jωC`、`R+jωL`、`1/Rᵣ+1/(jωLᵣ)` を使って解く。上流は根から木を作り、末端の子のアドミタンスを親へ畳み込み、入口の単位流量を決めて末端へ解を戻す。一様管に限る初回は独立した小規模な直列・並列の二端子対行列から放射流量を求められる。時間更新の出力を共用しない比較を作る。ピークは周波数を昇順に対応付け、欠測も確認する。[線形素子](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[周波数応答](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs)

[基準ケース](../cases/uniform-tube-rigid.json)では、まず 96 kHz・0.5 秒の時間応答を測り、最終 0.1 秒の最大絶対値を全区間の最大絶対値と比較する。計画書の 3% と 1.2% をそれぞれ解析近似と時間・周波数領域の共鳴判定に使う。壁の振動を追加する段階では、同じ入出力の定義で比較を再実行する。
