# 声道目標を音響サンプルに反映する

2026-11-19、固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の成人男性。単位は cm、cm²、cm³、cm³/s、dyn/cm²。各ケースは96 kHz、128サンプル×288フレーム。形状変更による圧力・流量と放射を観測するため、声門ポートは閉じ、肺圧は0、乱流源は登録解除、外部流量は0とする。

## 読んだ経路と処理順

1. [HumanVoice::render](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L377) は制御周期の先頭で [HumanVoice::control](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457) を呼ぶ。調音器が動き、[HumanAirway::apply と reapply](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214) が目標を決める。接触補正で2回計算した場合も、次の音響ブロックに使う目標は最後に確定した1組。
2. [set_tube_targets と set_port_target](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L647) は平均・最小断面、音響用管長をセル数で割った長さ、軟口蓋ポート断面を目標値として持つ。初期化の `snap_to_targets` は補間を省略し、体積を更新して無励振の初期状態を作る。`begin_block` は現在値と目標値の差をブロック長で割り、1サンプル分の増分を得る。
3. [AirwayNetwork::step](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827) の冒頭でセルの断面と長さを1回分進める。0始まりの内部サンプル `fN+j` が観測する形状は、フレーム `f` の開始形状から `(j+1)/N` だけ目標に近づいたもの。平均断面に非負の下限を設け、最小断面を0以上かつ平均以下にする。体積 `V=max(A,0.02) dx` を求め、直前の体積との差から流量 `-(V-V_previous)/dt` を作る。最小断面が0.12 cm²を下回るセルでは、開いている隣へ分けてから、60 Hzの一次フィルター2段で滑らかにする。断面と長さが両方変わると、体積はサンプル番号の二次式になる。
4. [ポート枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L989) は軟口蓋の開口面積を1回分進めてから、その面積と両端セルの形状で枝の慣性、粘性、損失を更新する。軟口蓋の枝、その他の流量、壁速度、[節点圧力と放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1070) の順で進む。ポートは0.0002 cm²未満で流量が0になる。放射端の閉鎖時には直前の放射負荷の流量が漸減する。
5. 上流の [airway_adversarial.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L165) では、`a_realistic_sliding_closure_with_trapped_pressure_releases_without_spikes` が加圧下での閉鎖移動と再開口、`fast_but_articulator_limited_closure_gives_bounded_piston_pressure` が可動壁による圧力の上限を調べる。

## 実装前の予測と判定

固定上流版の予備計測と、前工程で確定した全セルの目標を使って予測を登録した。各内部サンプルで咽頭入口、口腔中央、口腔の狭窄位置、唇、軟口蓋を観測する。閉鎖・開放は面積が0.0002 cm²の閾値を横切る時刻で判定する。

- [唇の閉鎖と再開口](../cases/tract-motion-lips.json) では4,799で閉鎖、18,944を最後に再開口する見込み。鼻端流量はゼロ。口腔中央のセル長は約0.00253 cm変わる。
- [母音遷移](../cases/tract-motion-vowels.json) では軟口蓋の音響ポートが10,241〜22,004で開く見込み。鼻端流量の絶対値の最大は約22.7 cm³/s。咽頭・口腔のセル長の変動幅は約0.0365 cm、0.132 cm。
- [舌先の接触補正](../cases/tract-motion-contact.json) では、最終目標の補間から口腔セル11の閉鎖を6,878〜18,690と予測した。中央セル8の圧力と、両側の枝流量・壁流量を観測する。
- 独立計算は、前工程の確定した目標をサンプル時刻へ直接補間して `V` を求める。口腔中央セル8と隣の7・9では、全期間を通じて最小断面が0.12 cm²を超える。このセルの体積流量は `-ΔV/dt` の二段フィルター応答となる。圧力差に `V/(ρc² dt)` を掛け、枝と壁の流量を差し引いて体積源を逆算する。声道の長さを固定した場合との差も記録する。

許容差は形状・ポートの絶対差 `1e-9`（cmまたはcm²）、圧力・流量・放射は各上流系列のピーク比 `1e-7`、独立計算で求めた体積源との差は `1e-7 cm³/s` とした。

## 実装と結果

[HumanAirway::begin_tract_block](../crates/vocal-core/src/airway/human.rs) は同一姿勢で初期化した気道へ、制御フレームで確定した咽頭・口腔のセル断面と安定長、軟口蓋の面積を渡す。[気道グラフ](../crates/vocal-core/src/airway/network.rs) は既存の[面積補間](../crates/vocal-core/src/airway/network/geometry.rs)にセル長を加え、枝更新前に軟口蓋の開口も進める。ポートの即時設定は指定したポートの補間を取り消せる。他のポートとセルの補間は継続し、新しい目標の検証に失敗した場合も現在の補間を続ける。[回帰テスト](../crates/vocal-core/tests/geometry_ramp.rs)

| 条件 | 内部サンプルの観測 | 実行 |
| --- | --- | --- |
| 唇の閉鎖と再開口 | サンプル4,799〜18,944で口端が閉鎖。鼻端流量は全期間ゼロ。口腔セル長の差は0.002526 cm | [要約](../runs/tract-motion-lips-20261119-b/summary.json) |
| 母音遷移 | サンプル10,241〜22,004で軟口蓋ポートが開く。鼻端流量の絶対値の最大は22.72 cm³/s。長さの差だけが体積変化に寄与する項は口腔中央で最大40.17 cm³/s | [要約](../runs/tract-motion-vowels-20261119-b/summary.json) |
| 舌先の接触補正 | 補正後の目標に沿って口腔セル11がサンプル6,878〜18,690で閉鎖。唇は開口を保った | [要約](../runs/tract-motion-contact-20261119-b/summary.json) |

全39項目が通過。110,592内部サンプルで、固定上流版との形状の最大絶対差は `2.30×10⁻¹³`（観測列ごとの cm または cm²）。圧力・流量・放射の最大差は各上流系列のピーク比 `2.42×10⁻¹²`。圧力収支から求めた口腔中央の体積源と独立計算との差は最大 `1.19×10⁻¹¹ cm³/s`。長さによる平滑化前の流量は `-A[n](dx[n]-dx[n−1])/dt` として面積の項から分けた。音響ポートで流量が止まった直後も、鼻端には蓄えられた振動による放射が残った。

[上流プローブ](../tools/upstream_articulation_probe.rs)は固定版の `HumanAirway` を呼び、接触補正を行った後にネットワークを進める。`HumanVoice::render` の肺・声門・間引きはここで扱う駆動条件の外にある。有声PCMとの照合は後続の工程で行う。
