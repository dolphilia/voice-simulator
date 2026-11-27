# FK61_01の節点42へ入る測定線と面積の集約

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行計測では、口端の一つ手前にある節点42の平均断面積が体積の丸めに効き、内部3969で体積速度が分かれた。このセルを固定上流、標準版、唇前端だけを揃えた試験版で比較する。 [体積速度の先行計測](tsp-fk61-node42-volume-source.md)・[事前登録](../cases/tsp-fk61-node42-area-origin.json)

## 読解と比較の条件

固定上流では `HumanVoice::render` が内部標本の制御境界を検出し、声道更新で `HumanAirway::commit` が矢状面の形状と測定線を計算して `HumanTract::resample` に渡す。咽頭の終点から唇までを等長の16セルに分ける。このケースでは口腔の添字14、気道全体の節点42を観測する。各セルの幅を8等分し、中点に対応する軸上距離［cm］の前後から面積［cm²］を線形補間する。中点の8面積の逆数を順に加え、8をその和で割った調和平均を平均断面積に使う。最小面積は中点とセル内の元の測定線から選ぶ。面積が10⁻⁵ cm²以下になった箇所を閉鎖として扱う。 [上流の発話器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[幾何の確定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)

研究版では `HumanTractControl` が `AreaProfile::resample_reusing` を呼ぶ。速度制限で閉鎖・開口に応じて面積を抑え、`HumanAirway::begin_tract_block` が制限後の面積と安定条件を反映した長さを気道へ登録する。補間の増分は「目標値−現在値」にブロック長の逆数を掛けた値で、各内部標本で繰り返し加算する。描画前、1984・1985・2048フレームを観測し、3968の開始から128内部標本の加算を再計算する。補間の初期部分は先行計測の状態に、最後の値は今回のスナップショットに照合する。 [研究版の形状更新と制限](../crates/vocal-core/src/airway/tract_control.rs#L225)・[研究版のセル集約](../crates/vocal-core/src/anatomy/resample.rs#L95)・[気道への登録](../crates/vocal-core/src/airway/human.rs#L340)・[切り替えと補間の試験](../crates/vocal-core/tests/geometry_ramp.rs)

試験版に対して、セル境界、測定線の軸位置、測定線上の面積をそれぞれ上流へ切り替える全8条件を計算する。1本ずつの面積交換も行う。調和平均の逐次加算は倍精度で再現し、同じ8面積から有理数で計算した平均も記録する。観測用の変更は一時ビルドに適用し、上流の唇の連続性試験、試験版の幾何補間試験、各条件の通常CLIと観測器の全PCMを照合する。 [上流の連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L236)・[観測器](../tools/tsp_fk61_node42_area_observation.py)・[比較の入口](../tools/measure_tsp_fk61_node42_area_origin.py)

## 面積の初差

描画前には測定線42〜45が寄与する。試験版の節点42の平均断面積は1.9631065757587380 cm²で、固定上流の1.9631065757587363 cm²との差は1.78×10⁻¹⁵ cm²だった。セル境界の交換と測定線の軸位置の交換で平均断面積は動かなかった。測定線の面積を交換すると上流に一致し、1本ずつ交換した条件では43の交換だけで一致した。 [セルと測定線の観測](../runs/tsp-fk61-node42-area-origin-20261123-repeat/summary.json)

開始後の1985フレームでは、平均断面積の目標が固定上流で1.9631194026750410 cm²、試験版で1.9631194026750414 cm²。セル境界、測定線位置、面積のいずれか1種類の交換では差が残り、3種類を揃えると一致した。測定線位置だけの交換で差が4.88×10⁻¹⁵ cm²に増えたことから、この時点の実際の面積差には複数の小さな差の相殺が含まれる。描画前と1985フレームとも、再標本化した面積は速度制限と気道への登録を同じ値で通った。 [時点別の交換結果](../runs/tsp-fk61-node42-area-origin-20261123-repeat/summary.json)

補間開始時の面積だけを上流に揃えると、独立計算で3969の体積速度 −0.006386687349646536 cm³/sを再現した。目標面積だけを揃えた場合は試験版の −0.006386687338988395 cm³/sのままだった。比較は先行計測で差が出た局所標本に限る。128標本の反復加算は、先行計測が残る初期区間と、今回採取した2048フレームの終点に一致した。 [開始面積と目標面積の交換](../runs/tsp-fk61-node42-area-origin-20261123-repeat/summary.json)

事後に描画前の測定線43だけを調べると、交点のx座標と上側のy座標は同じで、下側のy座標が6.204158750658352 cmから6.204158750658351 cmへ変わっていた。接触補正前後の隙間は各版で等しく、上流の1.0136319470160675 cmと試験版の1.0136319470160684 cmに分かれた。既存の `front_area` の独立計算で両版の面積をそれぞれ再現した。次は描画前の測定線43の下側交点を決める輪郭線分と、光線交差の演算を照合する。 [描画前の測定線](../runs/tsp-fk61-node42-area-origin-20261123-repeat/artifacts/trial.jsonl)・[上流の面積則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1185)・[研究版の測定線](../crates/vocal-core/src/anatomy/grid.rs)・[研究版の面積則](../crates/vocal-core/src/anatomy/area.rs#L96)

## 再実行

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296
../../.venv/bin/python tools/measure_tsp_fk61_node42_area_origin.py tsp-fk61-node42-area-origin-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から実行した。両実行で5判定とRustの2試験に通過した。上流、標準版、試験版それぞれの通常CLI、観測器、保存済み基準のPCMを全116,132フレームでビット照合した。観測・PCM・要約の6ファイルは実行間でバイト一致した。 [初回実行](../runs/tsp-fk61-node42-area-origin-20261123/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-fk61-node42-area-origin-20261123-repeat/manifest.json)
