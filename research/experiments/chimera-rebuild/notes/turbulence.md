# 狭窄で生じるシード付き乱流源

## 上流の経路と信号

`HumanAirway::commit` の `update_noise` は、声門、開いている最狭部、前歯の近くで発生する雑音の候補を選ぶ。各 `NoiseSpec` は流れを測る枝と、正流・逆流で圧力を注入する枝を持つ。 `AirwayNetwork::set_noise_sources` は制御周期で設定を差し替え、測定枝と正流の注入先の組が継続するときはフィルタ状態を保持する。 `HumanVoice` は各源の直近の振幅 `level` を観測する。上流の `tests/affricates.rs` は、その下流にある発話の摩擦が後続母音まで続くことを検査する。今回のケースは気道グラフに一つの源を直接設定する。[人の気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs)・[上流のグラフ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[上流の破擦音テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs)

`AirwayNetwork::step` は、今回の枝を解く前に `compute_noise` を呼ぶ。そこで参照する体積速度 `U` は前回の枝流量（cm³/s）、断面 `A` は前回の枝の有効面積（cm²）。通常枝では両端の最小断面の小さい方、ポートではポート自身の面積で、サンプルの枝更新後に次回用として保存される。円相当の直径と流速から `Re = 2|U|/(ν√(πA))` を得る。 `ν = μ/ρ` はcm²/s。 `A ≤ 0.0002 cm²` または `Re ≤ 1800` なら振幅は0。その他は `x = Re²−1800²` と `S = 12000²−1800²` を使い、`level = gain·scale·√(96000/fs)·x/(1+x/S)` とする。大きな流れでも振幅は飽和する。[物理定数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/physics.rs)・[上流の乱流計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

乱数は `Rng::new(12345)` で始まるMulberry32。閉鎖中やしきい値未満でも登録源ごとに1回引き、白色値を一次ハイパスと直列の二つの一次ローパスに通す。各ポールは `exp(−2πf/fs)`。帯域波形に `level` を掛け、正流側に加えるか、逆流側から引く。単位は枝方程式の圧力差と同じdyn/cm²。注入圧力はそのサンプルの枝を解く右辺に入り、枝流量を介して節点と放射に伝わる。固定上流版でグラフのシードは12345。候補では比較のため他の値も指定する。[乱数実装とテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs)・[枝への注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

## 実装前に登録した比較

30セル・12 cmの管でセル12を0.08 cm²にする。固定圧力を60 msで正または負の6 cmH₂Oまで上げ、セル12の後ろの枝12→13で乱流を駆動する。正流の注入先は前方の枝16→17、逆流は後方の枝8→9。高域の上端2600 Hzと低域の下端350 Hz、利得は人の喉頭上方の狭窄を参考にした。終盤にセル12を閉じ、前回の枝状態を参照していることと、閉鎖保持で振幅・注入がゼロになることを確かめる。[正流ケース](../cases/turbulence-forward.json)・[逆流ケース](../cases/turbulence-reverse.json)・[別シード](../cases/turbulence-alternate-seed.json)

最初の低流速区間と安定区間を比べ、開いていてもレイノルズ数がしきい値未満なら無音とする。乱数と離散フィルタをPythonで独立に計算し、観測した前サンプルの断面と流量から振幅・向き・注入圧力を再構成する。注入先は断面一定で運動損失の二次項がゼロなので、`L·(U_new−U_old)/Δt+R·U_new−(p_a−p_b)_old` から、実際に枝に加わった圧力も推定する。観測列の上流との比較はピーク相対差 `10⁻⁸` 未満、独立した源の計算は `10⁻¹⁰` 未満、運動量収支からの推定は `10⁻⁷` 未満とする。別シードでは安定区間の注入波形の差のRMSが、既定シードのRMSの0.25倍を超えることを確認する。

## 実装と結果

候補は枝の面積と流量を対にして保持し、可動断面を更新する前に読み出す。乱流圧力は枝の向きに従う符号付きの値として出力し、枝を解くときに節点圧力差へ足す。乱数のビット演算は上流と同じ列を得るために合わせた。PythonではSciPyの `lfilter` に伝達関数の係数を渡し、Rustの状態更新を呼ばずにフィルタ済みの波形を再構成する。設定変更時に継続する源のフィルタ状態を保持し、登録を解除すると圧力注入を消去することをRustテストでも確認した。[実装](../crates/vocal-core/src/airway/network/turbulence.rs)・[比較器](../tools/measure_turbulence.py)・[上流のMIT通知](../LICENSE-CHIMERA)

| 条件 | 最初の有効サンプル | 安定区間の平均Re | 注入圧力の最大絶対値 |
| --- | ---: | ---: | ---: |
| 正流・12345 | 680 | 5957.862 | 24.072 dyn/cm² |
| 逆流・12345 | 680 | 5957.852 | 24.036 dyn/cm² |
| 正流・6789 | 680 | 5957.853 | 23.884 dyn/cm² |

各7判定が通過。既定シードの正流・逆流では上流17系列の差が各列のピーク比で最大 `1.11×10⁻¹³`。独立フィルタとの最大差は3条件で `1.64×10⁻¹⁵`、枝の運動量収支の最大差は `4.83×10⁻¹⁴`。正流は枝16→17、逆流は枝8→9に注入し、しきい値未満と閉鎖保持中の注入は0だった。別シードでは、安定区間の注入波形の差のRMSが既定シードの波形のRMSの1.390倍になった。上流を使った同一波形の比較は、上流のグラフのシード12345を使う2条件が対象。[正流](../runs/turbulence-forward-20261119-b/summary.json)・[逆流](../runs/turbulence-reverse-20261119-b/summary.json)・[別シード](../runs/turbulence-alternate-seed-20261119-b/summary.json)
