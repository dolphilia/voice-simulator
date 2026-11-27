# 一様管の軟壁振動

## 上流の経路

`tests/airway.rs::fdtd_impulse_response_agrees_with_frequency_domain_model` は、同じ管を剛体と軟壁で二回実行する。軟壁の条件では `TubeSpec::wall(Some(...))` が単位面積あたりの質量・抵抗・剛性を渡し、`AirwayNetwork::finalize` が各節点に展開する。既定の `TubeSpec::wall_radiation` は 0 なので、このテストの出力放射は口端だけである。人間の咽頭・口腔では `HumanAirway::new` が壁放射の係数を 0.25 に設定する。[一様管テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[ネットワーク](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[人間の気道モデル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs)

`WallParams` の上流のコメントでは、軟壁の係数の出典が Ishizaka、French、Flanagan の壁インピーダンス測定（1975年）とされている。今回の固定一様管では上流テストと同じ `m = 1.5 g/cm²`、`r = 1600 dyn·s/cm³`、`k = 3×10⁵ dyn/cm³` を使う。[物理定数と壁モデル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/physics.rs)

## 入出力と更新順

```text
旧節点圧力 pⁿ ──→ 枝流量 Uⁿ⁺½ ──→ 通常の正味流入
       └─→ 壁速度 vⁿ⁺½ ──→ 壁流量 Uwall ─┘（差し引く）
                    └─→ 壁変位 yⁿ⁺¹          ↓
                             圧力 pⁿ⁺¹ と口端の並列 R–L
```

入口の体積インパルスは剛体ケースと共通で、初期の圧力、枝流量、壁変位、壁速度はゼロ。壁は各セルの圧力で駆動される局所的な質量・ばね・ダンパで、壁が外に動くとき `v` と壁流量は正。`m·dv/dt = p − r·v − k·y` の抵抗項を旧新の平均で扱うと、`[m/Δt+r/2] v_new = [m/Δt−r/2] v_old + p_old−k·y_old` となる。変位は `y_new = y_old+Δt·v_new`。セルの円周と長さの積 `S = 2√(πA)Δx` を速度に掛けた `S·v_new` が壁の体積速度で、正味流入から引く。口端の圧力は、この壁流量を含めた流入と並列 R–L の平均放射流量を使って更新する。[時間更新 `AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

線形解析では各セルの `jωC` に `Ywall = S/(r+j(ωm−k/ω))` を加える。壁を駆動する圧力と壁体積速度の比はこの連続時間の式から求め、Rust の時間更新とは別に終端から縦続回路を解く。壁放射が有効な場合は `壁放射係数 × ΣUwall` を口端放射流量へ足してから差分をとる。壁流量を節点収支に入れることと、壁が外部へ放射する成分を出力に入れることは別の操作である。[周波数領域 `transfer_function`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs)

## 比較前に登録した予測

[軟壁ケース](../cases/uniform-tube-soft-wall.json)は剛体と同じ 17.5 cm、3 cm²、40セル、96 kHz、48,000サンプル。口端の応答がサンプル39で始まること、壁流量が有限で非ゼロであること、壁の直接放射がゼロであること、末尾の減衰を確認する。第1ピークは剛体より30 Hz以上高いと予測する。方向と下限は実装前の上流テストで確認した差約44.70 Hzを根拠とする。

ピーク5件を周波数順に照合する。時間と独立線形計算の相対誤差は 1.2% 未満、上流のログの丸めを含む絶対差は 0.0051 Hz 未満とする。公開された圧力・枝流量・壁流量と `radiated_flow` を取得し、各軌跡の最大絶対差を各上流軌跡のピークで割る。ゼロ基準はゼロ一致とし、相対誤差の上限は `10⁻¹⁰`。入口・口端の有限差分の圧力変化と正味流入の収支も同じ上限で検査する。四分の一波長近似の剛体判定は、同じツールチェーンで剛体ケースを再実行して確認する。
