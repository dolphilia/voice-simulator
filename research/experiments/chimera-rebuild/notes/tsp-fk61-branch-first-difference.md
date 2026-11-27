# FK61_01の口端に入る枝流量の初差

[前回の比較](tsp-fk61-pcm2937-branch-seed.md#実測)では、5840の時点で枝42→43に残っていた旧流量を上流の値に交換すると、PCMの冒頭から2937までが揃った。今回は描画開始まで観測範囲を広げ、枝41→42と枝42→43の値が分かれる最初の標本を探す。固定上流、従来の研究版、下唇内面の三次ベジェ曲線の評価順を上流に揃えた試験版で比較する。内部96 kHz、PCM 48 kHz。時刻と節点番号は0始まり。

## 観測する計算と順序

上流の `render text` は `say` で音素と調音を計画し、`render_blocks` から `HumanVoice::render` を呼ぶ。各内部標本で制御、肺圧、声門面積を更新して `AirwayNetwork::step` に入る。まず断面積と長さを補間し、体積差から得た流量を配分と二段平滑に通す。枝には節点の更新前圧力と乱流圧が入り、両側の半セルから慣性と粘性抵抗を作る。枝の正向きと逆向きで、狭い断面からどの節点へ流出するかに応じた二次損失を使う。 [上流のCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の気道の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)

流量 `U` は cm³/s。圧力差 `p_a-p_b` と乱流圧 `p_noise` は dyn/cm²。枝の慣性 `L` は dyn·s²/cm⁵、粘性抵抗 `R` は dyn·s/cm⁵、二次係数 `K` は dyn·s²/cm⁸。古い慣性を `L₀`、古い流量を `U₀` とすると、履歴項に入る運動量は `M = min(L,L₀) × U₀`。断面が狭まって `L` が増えると運動量を引き継ぎ、広がって `L` が減ると新しい慣性と古い流量の積に更新する。

\[
 (L/\Delta t+R)U+KU|U|=(p_a-p_b)+p_{\mathrm{noise}}+M/\Delta t.
\]

この式の根で枝を更新し、左側節点の収支から枝流量を引いて右側に足す。壁の運動から決まる流量を引き、圧力を更新する。口端の圧力と慣性枝流量は並列R–L負荷の連成式を通る。可能な限り各版の演算順を独立に再現し、初差の入力を変えずに相手の版の演算順を使った結果も求める。枝を先に、壁・節点・口端の順で検算することで、下流の圧力差が枝の駆動に戻るタイミングを区別できる。 [上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[研究版の枝更新](../crates/vocal-core/src/airway/network.rs#L189)・[独立した根の計算](../tools/measure_fixed_voice_glottal_branch.py#L261)

通常CLIで基準PCMと一致させた上で、固定上流の定常狭窄、再開口、周波数応答の回帰試験を含む `airway` と `airway_adversarial` を実行する。研究版と試験版では、声門の面積を即時変更しても、他の面積と長さが目標へ進むことを `geometry_ramp` で確認する。 [固定上流の定常狭窄と閉鎖解除](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 比較条件

先頭から5879までの枝41→42・42→43、節点41〜43、節点42・43の壁、口端負荷を採取する。実験用の観測器に節点番号を指定し、対象の3節点だけをCSVに保存する。5840〜5879を先行計測と照合し、冒頭3072出力フレームと全発話のPCMも検査する。流量の最初の数値差の前後3標本で、節点の圧力差、過去の流量と運動量、慣性、損失、乱流圧の全組合せを比較する。 [事前登録](../cases/tsp-fk61-branch-first-difference.json)・[観測器](../tools/tsp_fk61_terminal_branch_observation.py#L34)

## 実測

| 固定上流との比較 | 枝41→42の初差 | 枝42→43の初差 | 口端放射流量の初差 |
| --- | ---: | ---: | ---: |
| 研究版 | 3969 | 3969 | 3968 |
| 下唇の評価順を揃えた試験版 | 3969 | 3971 | 3971 |

試験版の枝42→43が初めて分かれた3971では、上流から試験版を引いた流量差が +4.5245×10⁻¹⁷ cm³/sだった。旧流量・旧運動量と口端43の旧圧は一致し、節点42の旧圧に +1.4304×10⁻¹⁵ dyn/cm² の差があった。この旧圧を上流の値に交換すると、枝の流量はビット一致した。慣性と損失を交換しても枝の流量は動かなかった。同じ観測入力を両版の丸め順で計算した対照も、3971のそれぞれの枝流量に一致した。

節点42の圧力差は1標本前の3970で生じた。その時点では上流との正味流入差 +9.0103×10⁻¹⁷ cm³/s の全量が枝41→42の差で説明できる。試験版の3970でこの枝の流量だけを上流に交換すると節点42の更新後圧力が一致した。枝41→42は3969に既に −1.3235×10⁻²³ cm³/s の差があった。3969の差はその標本の節点42の流量収支を丸める際に消え、圧力に現れなかった。

節点41では、3968に正味流入が両版で同じ 1.2311568580757485×10⁻⁸ cm³/s でも、体積差 −4.4409×10⁻¹⁶ cm³ から圧力差 +5.2940×10⁻²³ dyn/cm² が生じた。両版の体積から `C = V/(ρc²)` を計算して、節点式 `p' = p + (Δt/C)q` でこの圧力差を再現した。3969には節点41へ入る正味流量に +1.6794×10⁻¹⁶ cm³/s の差が現れ、更新後の圧力差は +2.0951×10⁻¹⁵ dyn/cm² になった。その増分の出所を絞るため、次は節点41に入る側の枝40→41と節点40の体積源・圧力を同じ標本で採る。 [初差と枝の交換結果](../runs/tsp-fk61-branch-first-difference-20261123-registered/summary.json)・[試験版の節点CSV](../runs/tsp-fk61-branch-first-difference-20261123-registered/artifacts/trial-nodes.csv)

通常CLI、観測版、保存済みPCMは各版の116,132フレームで一致した。3版で各5,880内部標本の枝・壁・節点・口端負荷を再計算し、5840〜5879は先行の採取と一致した。節点CSVは以前の全71節点から3節点に絞り、各標本で保存する節点の行数を約95.8%減らした。

## 再実行

macOS arm64、固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースと `/tmp` から通常CLIと観測版を描画し、両実行で各5判定とRustの11試験が通過した。採取系列17点と結果要約がバイト一致した。出力はRTL9210B-CGの `voice-simulator/scratch/chimera-runs/` に保存した。 [初回マニフェスト](../runs/tsp-fk61-branch-first-difference-20261123-registered/manifest.json)・[再実行マニフェスト](../runs/tsp-fk61-branch-first-difference-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_branch_first_difference.py tsp-fk61-branch-first-difference-new
```
