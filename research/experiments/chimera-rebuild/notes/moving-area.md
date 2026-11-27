# 可動断面と体積流量源

## 上流の経路

`tests/airway_adversarial.rs::sealed_cavity_compression_follows_the_linearised_adiabatic_law` は、両端を密閉した長さ4 cm・10セル・断面2 cm²の管を96 kHzで更新する。`set_tube_targets` で64サンプル先の断面を設定し、`begin_block` が現在面積から目標へ向かう1サンプルあたりの加算量を作る。1,920サンプルかけて全断面を1.9 cm²に縮め、残り1,920サンプルは保持する。上流テストでは最終の平均圧力が72,368.80 dyn/cm²、体積比から求めた連続近似が71,631.09 dyn/cm²だった。[密閉管のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)・[面積目標と `begin_block`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

## 状態と時刻

各サンプルでは面積を先に更新し、`V = Δx max(A, 0.02 cm²)` を計算する。上流の枝は新しい面積で慣性・抵抗を更新する。同じ流量に対する運動エネルギーが開口変更で増えないよう、慣性が増すときには旧運動量、減るときには旧流量と新慣性の積を枝の右辺に使う。枝が閉じる閾値は0.0002 cm²である。[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

```text
断面目標と補間 → Aⁿ⁺¹ → Vⁿ⁺¹ → -(Vⁿ⁺¹−Vⁿ)/Δt
                    ├→ 枝の慣性・抵抗の更新              ↓
                    └→ セルのコンプライアンス   近隣へ配分 → 2段の平滑化
                              ↓                          ↓
                         pⁿ⁺¹ ← 枝の正味流入 + 平滑化後の体積流量源
```

生の体積流量は `−ΔV/Δt`（cm³/s）。体積が減ると正になる。セルが0.12 cm²未満なら、自分に残す比率を `s²(3−2s)`（`s=A/0.12`）とし、残りを開いた隣接セルへ等分する。近隣の現在面積または目標面積が0.12 cm²以上なら配分先になる。配分先がない場合は、上流では残りが吸収される。各セルの配分後の流量は、係数 `1−exp(−2π·60·Δt)` の一次ローパスを二段通す。入口流量や枝の差分と足した後、`C=V/(ρc²)` によって圧力を進める。[体積源と平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

放射端が閉じている間は節点圧力と放射流量を減衰させる。開いた端では、開口が小さくなって放射慣性が増えたとき、慣性枝の流量を旧慣性と新慣性の比で補正する。内部閉鎖セルの圧力は開いた近隣の平均に緩やかに追従する。[閉鎖節点と放射境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

## 比較前に登録した判定

- [密閉管](../cases/sealed-cavity-compression.json)は外部励振なし。全節点が同じ面積と体積源を持つので枝流量はゼロで、独立に二段フィルタを計算して `p[n]−p[n−1] = Δt·U_volume[n]/C[n]` を積分できる。圧力、面積、体積流量源を比較する。最終圧力は `ρc² ln(1/0.95)` と3%未満で一致し、外部への放射はゼロと予測する。
- [放射端の開閉](../cases/moving-aperture-release.json)は同じ管の末端セルだけを動かす。完全に閉じている区間では末端へつながる枝の流量がゼロで、再開口区間で枝流量と放射が復帰すると予測する。末端とその手前への配分を独立に再計算し、平滑化後の体積流量源を比較する。上流とは公開状態で得られる圧力・断面・枝流量・放射を照合する。

両ケースともセル長は固定で、平均断面と最小断面を同じ値に設定する。肺圧などの固定圧力境界を使う開閉の比較は、圧力境界とポートを追加した段階で行う。
