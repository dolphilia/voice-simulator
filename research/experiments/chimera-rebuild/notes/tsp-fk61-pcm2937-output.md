# FK61_01のPCM2937で生じる丸めを放射入力まで追う

下唇内面を固定上流の演算順で評価した試験版で、固定上流との最初のPCM差が1987から2937フレームへ移った。今回の比較は固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` と、この試験版に限る。以前は2048までだった上流の採取範囲を3072フレームに広げる。 [全発話の比較](tsp-fk61-lower-lip-bernstein-render.md)・[事前登録](../cases/tsp-fk61-pcm2937-output.json)

## 読解と照合

固定上流では、`HumanVoice::render` が内部96 kHzで `AirwayNetwork::step` を呼ぶ。気道は壁面・口端・鼻端の放射流量を足した総流量［cm³/s］を保存し、直前値との差に内部レートを掛けて放射入力［cm³/s²］を得る。研究版では刻み時間による除算で同じ量を求める。上流の `Decimator::push` はこの量を保持し、2内部標本につき1出力フレームで、49タップのFIRを古い標本から順に加算する。出力2937のFIR入力は内部5827〜5875、その出力フレームで受け取った入力は5874と5875。この間引きの直後に出力ゲインを掛ける。 [上流の放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1073)・[上流の間引き](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L41)・[研究版の放射](../crates/vocal-core/src/airway/network.rs)・[研究版の出力段](../crates/vocal-core/src/output.rs#L103)

DC除去は `現在のゲイン適用後の値 − 前フレームのゲイン適用後の値 + DC係数 × 前フレームのDC出力` で、更新した値を次へ引き継ぐ。続くリミッターはピーク包絡を保持し、閾値を超えた時に出力を減衰する。その後float32へ変換する。保存された入力と係数から倍精度のFIR・ゲイン・DC除去・包絡を再計算する。固定上流は通常CLIで描画したPCMを観測器と既存の保存済み全PCMに照合し、ホスト側のブロック長を変えても上流エンジンの出力が一致する既存試験を実行する。 [上流の出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L396)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[既存の出力段再計算](../tools/measure_tsp_fk61_pcm_first_difference.py#L29)

2937の丸めへの寄与を分けるため、DC除去の入力3項を独立に交換する。放射差分の交換では、現在の内部2標本、FIR範囲の古い標本、その範囲より前を分け、試験版の放射を上流の値に交換して出力を最初から再計算する。放射の3成分と時間差分の演算順は、別の対照で交換する。それぞれの対照で2937のPCMと、冒頭から2937までの一致を記録する。 [比較の入口](../tools/measure_tsp_fk61_pcm2937_output.py)

## 実測

上流と試験版の間引き係数、DC係数、リミッターの減衰係数は一致した。放射入力は内部3968で、口端の放射流量は3971で初めて分かれた。間引き後とDC除去後の倍精度値はともに出力1984で初差が出た。各版の放射差分を共通の出力段へ与えた独立計算は、先頭3072フレームの双方の倍精度出力とPCMを再現した。 [各段の初差と再計算](../runs/tsp-fk61-pcm2937-output-20261123-verified-repeat/summary.json)

2937では上流の変換直前値2.4556801482612716×10⁻⁶が、float32の中点を1.9208161909721033×10⁻¹⁵上回った。試験版の値は中点を1.409947072967101×10⁻¹⁴下回った。いずれも隣接するfloat32へ変換された。2937のゲイン適用後の値だけを上流に交換すると差は縮み、中点の約2.38×10⁻¹⁶下に残った。2936のDC出力だけを交換すると2937の丸めが上流に揃った。 [中点とDC状態の交換](../runs/tsp-fk61-pcm2937-output-20261123-verified-repeat/summary.json)

放射成分の交換では、口端の放射流量だけを上流に揃える条件で先頭2938フレームのPCMが一致した。壁面のみ、鼻端のみ、総流量を固定して時間差分の演算順だけを揃えた各条件では、2937の差が残った。放射差分の時間範囲を分けた対照では、内部0〜5873を交換すると一致し、現在の2標本だけ、FIRに入る古い47標本だけ、それより前の履歴だけの各交換では差が残った。現在のFIR出力に対する入力差×係数の絶対値が最大だったのは内部5851。ここは2937の残差に関係する口端の流量と以前のDC状態をさらに調べる際の観測位置になる。 [放射成分・時刻別の対照](../runs/tsp-fk61-pcm2937-output-20261123-verified-repeat/summary.json)

## 再実行

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296
../../.venv/bin/python tools/measure_tsp_fk61_pcm2937_output.py tsp-fk61-pcm2937-output-new
```

初回は描画後の集計で、以前の放射配列のキーを `upstream_state` として読んだため停止した。実際のキー `upstream_source` に直し、再描画の前に必要な配列があることを確かめるようにした。先に採取した2組の波形を再解析し、修正後と同じ判定を確認した。 [初回の採取データ](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs/tsp-fk61-pcm2937-output-20261123-repeat/artifacts/upstream-prefix.npz)・[初回の計測スナップショット](../runs/tsp-fk61-pcm2937-output-20261123-repeat/artifacts/source/research/experiments/chimera-rebuild/tools/measure_tsp_fk61_pcm2937_output.py)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から実行した。各実行の4判定と固定上流のRust試験1件が通過した。通常CLI・観測ビルド・保存済みPCMは上流全116,132フレームでビット一致した。配列・係数・PCMの照合結果・要約の4出力が再実行でバイト一致した。 [研究ワークスペースからの実行](../runs/tsp-fk61-pcm2937-output-20261123-verified/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-fk61-pcm2937-output-20261123-verified-repeat/manifest.json)
