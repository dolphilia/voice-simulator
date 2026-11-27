# FK61_01の唇前端を揃えた後の放射差を追う

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。女性の同じ発話を、固定上流、標準研究版、唇前端一箇所の体型変換だけを固定上流の順序にした試験版で比較する。先行計測で試験版の初期口端セル面積は固定上流に一致し、最初のPCM差は出力フレーム1987だった。 [事前登録](../cases/tsp-fk61-lip-front-radiation.json)・[唇前端の先行計測](tsp-fk61-lip-front-origin.md)・[標準版の口端流量](tsp-fk61-lip-onset.md)

## 読解と観測位置

上流の通常発話では、`HumanVoice::render` が出力1フレームを作るたびに `AirwayNetwork::step` を2回通す。ネットワークはまず、面積［cm²］と長さ［cm］を補間し、前後の体積差［cm³］を内部の時間刻みで流量［cm³/s］に換算する。狭窄付近では近隣へ配分し、合計を2段のローパスに入れる。各枝の圧力差と損失から流量を更新して節点の収支へ加え、壁が吸い込む体積流量を引く。壁面の流量に節点ごとの放射係数を掛けた値と、口端・鼻端のR–L放射負荷が返す流量の和を微分して出力段へ渡す。 [上流の発話器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の体積注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[壁・節点・放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1054)

研究版では `ArticulatedVoice` が気道を更新し、`MovingAreas::step` が体積差分と2段平滑、`AirwayNetwork::step_with_prescribed_flow` が枝流量、壁、放射負荷を処理する。枝に流量を指定した場合も、元の枝と同じ両端と符号で収支を更新する。壁は更新前の節点圧力［dyn/cm²］で速度を進め、壁の面積［cm²］と速度［cm/s］から流量を求める。節点の圧力を進めた後、壁・口端・鼻端の順に足した流量の1標本差分を出力段へ渡す。再計算では上流が逆刻み時間を掛け、研究版が刻み時間で割る各演算を再現する。 [研究版の体積注入](../crates/vocal-core/src/airway/network/geometry.rs#L110)・[枝・壁・節点](../crates/vocal-core/src/airway/network.rs#L675)・[壁速度の更新](../crates/vocal-core/src/airway.rs#L286)

口端は前回と同じ終端観測を使い、全節点では更新前後の体積と圧力、配分後の流量、2段の平滑値、枝と壁を適用する前後の収支を採る。放射の各成分から倍精度で差分、間引き、ゲイン、直流除去を再計算し、1987フレーム終了までのPCMを比較する。上流の一様管・狭窄を含む既存試験と、各研究版のセル長・ポートの補間試験も実行する。 [上流の管の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)・[先行するPCM出力段の検証](tsp-fk61-pcm-first-difference.md)

## 実測

唇前端を揃えた試験版では、内部標本3968で口端の体積差分、2段平滑後の流量、枝・壁を加えた後の終端への流量が固定上流に一致した。口端のR–L負荷の入力と口端の放射流量1.614853805056832×10⁻⁸ cm³/sも一致した。その標本では壁・鼻端はともに0で、総放射流量も一致した。 [口端の観測](../runs/tsp-fk61-lip-front-radiation-20261123-repeat/summary.json)

| 固定上流との最初の差 | 標準研究版 | 唇前端を揃えた試験版 |
| --- | ---: | ---: |
| 口端の放射流量の内部標本 | 3968 | 3969 |
| 壁面放射流量の内部標本 | 3969 | 3969 |
| 鼻端放射流量の内部標本 | 先頭4096標本で一致 | 先頭4096標本で一致 |
| 総放射流量の時間差分の内部標本 | 3968 | 3968 |
| PCMの出力フレーム | 1989 | 1987 |

試験版と固定上流で3968の総放射流量は同じだった。時間差分を `×96000` と `÷(1/96000)` で計算すると、0.0015502596528545586と0.0015502596528545588 cm³/s²の隣接倍精度値になった。残る放射差が3969の壁面放射から始まるという予測は外れた。3969の口端と壁には流量の差があり、口端では枝の更新後に初めて差が出た。3968で口端より手前の6節点に現れた体積注入の差も保存した。 [全節点の流量と圧力](../runs/tsp-fk61-lip-front-radiation-20261123-repeat/artifacts/trial-nodes.csv)

1987フレームの変換直前値は、float32の中点に対して固定上流で+3.9475×10⁻²²、試験版で−4.9593×10⁻²²となった。試験版の口端放射流量だけを固定上流に差し替えた独立計算で、1987フレームまでのPCMが固定上流に一致した。逆方向の交換でも試験版の値を再現した。壁面と鼻端の単独交換では元の丸め結果が続いた。 [成分交換と丸め中点](../runs/tsp-fk61-lip-front-radiation-20261123-repeat/summary.json)

事後の対照では、同じ総放射流量のまま時間換算の演算順だけを交換した。3968の微分値は相手側と揃い、最初に異なるPCMフレームは試験版で1987のままだった。3968〜3975の口端流量を1標本ずつ交換した8条件では、3972を交換した場合に1987フレームまでが固定上流と一致した。この試験は出力段への入力の交換として行った。 [時間差分と1標本交換の再計算](../runs/stage7-evidence-update-20261123-fk61-lip-front-radiation/summary.json)

次は口端節点43の直前にある口腔節点42を調べる。3968で42の平滑後の体積流量は一致し、新圧力に差が出た。3969で42の体積注入が分かれた。42–43の枝の圧差と更新式を照合すれば、口端流量が分かれた経路を絞れる。 [節点と流量の列定義](../runs/tsp-fk61-lip-front-radiation-20261123-repeat/artifacts/node-columns.json)

## 再実行

観測用のRustビルドはRTL9210B-CG上の一時チェックアウトに置く。試験版は既存の前端の差分を適用し、標準版・試験版とも同じ出力レート・辞書・本文で描画する。 [計測入口](../tools/measure_tsp_fk61_lip_front_radiation.py)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。各条件で全116,132フレームの通常CLI・観測器・保存済みPCMがビット一致。研究ワークスペースと `/tmp` の実行はいずれも5判定とRustの11試験に通過し、口端・節点・放射の観測、定義、要約を含む10出力がバイト一致した。 [初回](../runs/tsp-fk61-lip-front-radiation-20261123/manifest.json)・[別ディレクトリでの実行](../runs/tsp-fk61-lip-front-radiation-20261123-repeat/manifest.json)


```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_lip_front_radiation.py fk61-lip-front-radiation-new
```
