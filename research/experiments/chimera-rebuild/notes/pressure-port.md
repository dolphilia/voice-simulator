# 固定圧力境界と狭窄ポート

## 上流の経路と状態

上流の `steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss` は、長さ12 cmの30セル管の手前に `add_pressure_node` で固定節点を追加する。固定節点の幾何は長さ1 cm・面積100 cm²。`add_port` で管の入口につなぎ、末端には `add_radiation` を付ける。96 kHzで0.25秒更新し、肺側の圧力はサンプル番号に応じ0から20 msで6 cmH₂Oへ上げる。固定圧力は枝を解く前に書き込み、節点の流量収支では更新しない。圧力はdyn/cm²、体積速度はcm³/s。[上流のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)・[境界とポート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

```text
固定圧力の節点 → 独自の断面・長さを持つポート → 管の入口 → 狭窄セル → 放射端
   枝の右辺へ p を与える          L、R、二次損失       平均と最小を別々に保持
```

ポートの `L = ρℓ/A` に、設定によって両隣の半区間の慣性を加える。円形の `R` は周長・長さ・逆面積の二乗と粘性から求める。スリットを指定した場合は `R = 12μℓw²/A³` を使い、指定された追加抵抗を足す。流れの向きごとの二次係数は、入口の `ρ k_entrance/(2A²)` と、出口の正の逆面積差の二乗に比例する損失の和。枝の慣性を掛ける流量は、前回の状態を引き継ぐ。通常のセル間の枝とは同じ二次方程式で `Uⁿ⁺½` を解く。[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

上流の `set_tube_targets` は平均 `A` と最小 `Amin` をそれぞれ補間する。平均は体積・慣性・粘性、最小は閉鎖判定と二次損失に効く。セルの一部だけ狭いとき、流れの向きと狭窄前後の断面によっては、同じ枝に縮小と拡大の寄与が両方入る。今回は狭窄セルの平均を `1/(f/0.08+(1−f)/3)` cm²、最小を0.08 cm²とし、`f=1` と `f=1/4` を比べる。[面積目標と枝の損失](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

## 比較前に登録した判定

- 上流のテストと同じ Bernoulli 流量 `0.08√(2P/ρ)` に15%未満で一致することを確認する。上流テストの観測は1セルで243.66 cm³/s、1/4セルで249.80 cm³/s。短い狭窄では、事前に登録した判定として4 cm³/s以上の流量増を確認する。[1セル](../cases/steady-constriction-full.json)・[1/4セル](../cases/steady-constriction-quarter.json)
- 全経路の正流方向に対して、定常の圧力差を `ΣR·U + Σk·U²` として独立に合計する。放射端の並列慣性枝は直流でゼロ圧力に近づくため、`U` の正根を別に求められる。最後の1,920サンプルで各枝の平均流量、固定節点から放射端までの圧力差、狭窄前後の圧力差を測る。上流との時系列比較は、固定圧力・各セル圧力・流量・放射・平均面積と最小面積を対象とする。

## 実装と測定

通常枝とポートは枝の流量更新を共有し、素子係数を別々に求める。固定圧力の節点は枝に圧力を与え、枝の計算後に行う節点の圧力更新を飛ばす。平均と最小の到達断面は共通の制御ブロックで補間し、最小断面を平均以下に保つ。最小断面は閉鎖と隣接セルへの体積源配分にも反映する。候補と上流プローブはいずれも補間後の両断面を観測系列に出す。[気道グラフ](../crates/vocal-core/src/airway/network.rs)・[面積補間](../crates/vocal-core/src/airway/network/geometry.rs)・[上流プローブ](../tools/upstream_network_probe.rs)

| 条件 | 定常流量 (cm³/s) | Bernoulli 近似との相対差 | 定常抵抗式との相対差 | 上流時系列との最大相対差 |
| --- | ---: | ---: | ---: | ---: |
| 1セル | 243.66268 | 5.20% | `2.38×10⁻¹⁰` | `1.12×10⁻¹³` |
| 1/4セル | 249.80233 | 2.81% | `1.85×10⁻¹¹` | `2.19×10⁻¹³` |

時系列の差は、24,000サンプルの最大絶対差を上流同列のピークで割った値。狭窄を短くすると流量は6.13964 cm³/s増えた。両ケースの全経路の圧力差を定常損失で予測した差は駆動圧の `4.76×10⁻¹⁰` 未満。測定範囲は、両側の半区間を含む円形の固定ポートと、狭窄前後の通常枝。このポートでは二次損失係数をともにゼロに設定した。[計測器](../tools/measure_pressure_port.py)・[1セル結果](../runs/steady-full-20261119-b/summary.json)・[1/4セル結果](../runs/steady-quarter-20261119-a/summary.json)
