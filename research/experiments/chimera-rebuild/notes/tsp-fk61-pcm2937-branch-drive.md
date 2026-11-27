# FK61_01の枝42→43に残る流量差

[口端負荷の計測](tsp-fk61-pcm2937-terminal-load.md#実測)では、5863の口端に入る正味流入差の約97.4%を枝42→43が占めた。今回は、この直列枝の圧力駆動、慣性履歴、粘性抵抗、方向別の二次損失、乱流源を切り分けた。固定上流と、下唇内面の評価順を揃えた試験版を比較した。元の採取は内部96 kHz、PCM 48 kHz。標本番号は0始まり。

## 呼び出し経路と式

上流CLIの `render text` は発話計画をスコアにして `render_blocks` から `HumanVoice::render` を呼ぶ。声門面積と肺圧を更新してから `AirwayNetwork::step` に入る。枝42→43には両節点の更新前圧力が入る。両隣の半セルの長さと断面積から慣性を、壁の周長や粘性から線形抵抗を組み立てる。二次損失は狭い断面から接続先へ広がる噴流と収縮への補正を足し、流量の向きで係数を選ぶ。 [CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L224)・[発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝係数の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L947)

流量 `U` は cm³/s、圧力差 `Δp` と乱流圧 `p_noise` は dyn/cm²。慣性 `L` は dyn·s²/cm⁵、抵抗 `R` は dyn·s/cm⁵、二次係数 `K` は dyn·s²/cm⁸。前の刻みから持ち越す運動量 `M` は `L_prev × U_prev`。慣性が減るときは `L_now × U_prev` に変え、開口時に旧流量を保つ。次の式の `U` を符号に応じた根で更新する。更新した `U` を左から引き、右へ足した後に、壁流量、節点圧力、口端負荷が順に更新される。 [上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[研究版の枝更新](../crates/vocal-core/src/airway/network.rs#L189)

\[
B=L_{\rm now}/\Delta t+R,\quad D=(p_{42}-p_{43})+p_{\rm noise}+M/\Delta t,\quad
BU+KU|U|=D.
\]

丸めを含む逐次計算では、上流の `M × fs` と研究版の `(min(L_now, L_prev) / Δt) × U_prev` をそれぞれ再現する。独立した寄与の計算では、両版が負向きなので、`D` の差から試験版流量に掛かる `ΔB` と `ΔK` の項を引き、`B_up + K_up (|U_up| + |U_trial|)` で割る。途中の積と加減算は有理数で行う。両版が負向きの期間で、運動量履歴や圧力の差を単独の流量寄与として求められる。 [枝の逐次計算](../tools/measure_fixed_voice_glottal_branch.py#L261)・[独立した寄与の計算](../tools/measure_tsp_fk61_pcm2937_branch_drive.py)

固定上流の `steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss` は全セルと1/4セルの狭窄が同じ流量則に従うかを確認する。`a_realistic_sliding_closure_with_trapped_pressure_releases_without_spikes` は閉鎖の移動中と再開口時の圧力・放射の上限を確認する。研究版の `immediate_port_update_keeps_other_geometry_ramps_active` は声門ポートの面積を即時更新した間も他の断面積・長さ・ポートが目標へ進むかを検査する。各試験の実行ログは前の通常CLI採取に含まれる。 [上流の定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)・[採取マニフェスト](../runs/tsp-fk61-pcm2937-terminal-load-20261123-certified/manifest.json)

## 比較条件

通常CLIと観測版が各116,132フレームで一致した記録を再利用し、上流と試験版の5840〜5879を検算した。5863〜5865で入力5群を1標本ずつ交換し、各32組を保存した。次に5856から、圧力系列、枝の初期状態、慣性系列、損失系列、乱流系列の全32組で枝の流量を再計算した。口端の体積源と壁流量には試験版で採った値を用い、再計算した口端圧力を枝や壁へ戻さずに負荷の履歴を進めた。出力段へ戻したのは5863・5864の口端流量だけ。基準のままの2節点モデルも別に進めて、各版の観測記録と照合した。 [事前登録](../cases/tsp-fk61-pcm2937-branch-drive.json)

## 実測

| 内部標本 | 枝流量の差 cm³/s | 運動量履歴の寄与 cm³/s | 圧力差の寄与 cm³/s | 差分式の絶対残差 ULP |
| ---: | ---: | ---: | ---: | ---: |
| 5863 | −2.8638×10⁻¹¹ | −2.9071×10⁻¹¹ | +3.7494×10⁻¹³ | 0.028 |
| 5864 | −2.8287×10⁻¹¹ | −2.8671×10⁻¹¹ | +3.1952×10⁻¹³ | 0.849 |
| 5865 | −2.7995×10⁻¹¹ | −2.8323×10⁻¹¹ | +2.7109×10⁻¹³ | 0.599 |

差は上流から試験版を引いた値。5863では、運動量履歴の寄与が約 −2.91×10⁻¹¹ cm³/sで、節点の圧力差は逆向きに約 +3.75×10⁻¹³ cm³/s寄与した。この3標本では両版で慣性が増える方向だった。逆向き二次損失と乱流圧は両版で同値。抵抗差の寄与は約5×10⁻¹⁷ cm³/sで、単独で交換しても枝の流量は変わらなかった。独立式の残差は最大0.85 ULPだった。

5856の枝の初期状態だけを交換した場合、PCM 2937のf32変換前の値は +1.8532×10⁻¹⁴動き、冒頭から2937まで一致した。5856から圧力系列だけを交換した場合は −1.7308×10⁻¹⁵動き、2937の差が残った。圧力系列の方が大きいという予測は棄却した。32条件のうち、枝の初期状態を交換する16条件でPCMが一致した。初期状態には旧流量・旧慣性・旧運動量を一緒に入れた。5856から枝流量の観測列だけを直接交換した場合もPCMは一致し、同じPCMに丸まった変換前の値は異なった。 [結果要約](../runs/tsp-fk61-pcm2937-branch-drive-20261123-repeat/summary.json)

枝の状態に差が生じた時刻を遡る。まず採取済みの5840〜5856で開始標本を変え、旧流量と旧慣性を独立に取り替える。旧運動量には毎回その積を使い、状態の組合せを整合させる。この区間より前に差がある場合は、前の枝の採取と結び付けて観測範囲を広げる。

## 再実行

macOS arm64、固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。研究ワークスペースと `/tmp` から実行して各5判定に通過し、両要約はバイト一致した。元の観測系列はRTL9210B-CGにあり、今回の小容量の要約は実行ディレクトリに保存した。 [初回マニフェスト](../runs/tsp-fk61-pcm2937-branch-drive-20261123-registered/manifest.json)・[再実行マニフェスト](../runs/tsp-fk61-pcm2937-branch-drive-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_tsp_fk61_pcm2937_branch_drive.py tsp-fk61-pcm2937-branch-drive-new
```
