# 咽頭の次セルで圧力が分かれる最初の収支

## 読解と事前の予測

固定上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は内部1点ごとに肺圧と声門開口を設定し、気道網を進める。[`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827) は断面と体積ソースを更新し、前回節点圧を使って枝流量を求めてから、壁を進めて圧力を更新する。今回の節点14は咽頭の入口に続く開いた中間セルで、枝13→14が流入、枝14→15が流出となる。圧力は dyn/cm²、体積流量は cm³/s。壁速度は cm/s、変位は cm、壁面積は cm² で、速度と面積の積が壁への体積流出となる。[枝と壁の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1031)

節点14では体積変化の流量源に枝の流入を加え、流出と壁流量を引く。体積 `V` と空気の体積弾性率 `ρc²` の比 `C=V/(ρc²)` がコンプライアンス。前回圧に `(dt/C)×正味流量` を加え、次の内部点の枝と壁が新しい圧力を読む。研究版では [`AirwayNetwork::step_with_prescribed_flow`](../crates/vocal-core/src/airway/network.rs#L675) が同じ内点の更新を行う。各項は二進64ビットで丸まり、微小な項の差が加減算の途中で消える場合がある。上流の [密閉空洞の断熱圧縮テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56) は体積変化による圧力増加を解析式に照合し、[狭窄の定常流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92) は枝の流量と非線形損失を照合する。

前回の隔離ビルドと固定上流では、8,213・8,214点目の枝13→14の流量が一致していた。節点14の圧力は8,214点目に最初に分かれ、8,229点目の入口側の枝流量差を節点14の圧力の置換で再現できた。今回の観測では、8,214点目の流入と更新前圧の一致を確認し、流出、壁、体積変化、コンプライアンスのどの置換で圧力を復元できるかを調べる。[先行比較](fixed-voice-pharyngeal-entry-branch-48000.md#咽頭の一枝を上流順にした連続描画)・[事前登録](../cases/fixed-voice-pharyngeal-second-cell-48000.json)

## 流出の差が圧力に現れるまで

8,214点目の圧力は研究版 `2.8941281493271147×10⁻⁶`、固定上流 `2.8941281493271143×10⁻⁶` dyn/cm² だった。前回圧、流入、壁流量、体積ソース、コンプライアンスは一致した。枝14→15の流出だけを `1.8620148991217054×10⁻⁸` から上流の `1.8620148991217058×10⁻⁸` cm³/s に置換すると、正味流量と更新後圧が上流とビット一致した。前点の8,213でも流出は異なったが、加減算を終えた正味流量と圧力は一致した。壁流量の初差は次の8,215点目に現れた。[圧力収支と置換](../runs/fixed-voice-pharyngeal-second-cell-48000-c/summary.json)

枝14→15の流量は8,207点目で初めて分かれた。左右の圧力と持ち越し圧は同じで、現在の慣性 `0.00047158438269489107` g/cm⁴ も一致した。線形項に入る慣性の換算が、研究版の `L/dt` で `45.27210073870955`、上流の `L×Fs` で `45.27210073870954` になった。この係数だけを上流値に置換すると8,207点目の流量 `7.393769321880806×10⁻¹⁵` cm³/s を復元した。8,214点目でも同じ係数の単独置換で流出が一致した。次にこの枝1本の現在慣性の換算順を変え、連続更新でも8,214点目の圧力と8,229点目の入口側の流量が一致するかを比較する。[枝の初差と8,214点目の観測](../runs/fixed-voice-pharyngeal-second-cell-48000-c/summary.json)

## 実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_pharyngeal_second_cell.py fixed-voice-pharyngeal-second-cell-48000-c

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_pharyngeal_second_cell.py" \
  fixed-voice-pharyngeal-second-cell-48000-repeat
```

初回の `-a` は候補ソースのスナップショット参照が誤っており、描画前に終了した。参照を元のビルド入力のマニフェストに接続し直した。続く `-b` では、8,229点目の右圧の置換結果をPythonのタプルで保持しながら配列と比較したため、8判定のうち1件が誤って失敗になった。取得済みの結果には右圧の単独置換が記録されていたので、計測と事前登録を保ったまま判定側の型を修正した。[初回のログ](/Volumes/RTL9210B-CG/voice-simulator/scratch/fixed-voice-pharyngeal-second-cell-48000-a-preflight.log)・[修正前の判定](../runs/fixed-voice-pharyngeal-second-cell-48000-b/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各8判定と固定上流の各9試験に合格した。全52点ずつで壁流量・節点圧・前後2本の枝流量を復元し、別の十進計算でも、両版あわせて各104点の壁と節点、各208点の枝を照合した。8,207・8,213・8,214点目の枝14→15の慣性項の置換と、8,214点目の流出の置換も十進計算で確認した。要約の置換欄は1項以上を置換したときの一致を記録している。8,213点目は置換前の正味流量と圧力も一致した。[再実行の判定](../runs/fixed-voice-pharyngeal-second-cell-48000-repeat/summary.json)・[独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-48000.json)

PCMの先頭4,810フレームと保存済みの通常描画を照合した。再実行間でCSV・PCM・実験用差分の14出力がバイト一致した。固定上流の一時プローブの実行ファイルは再実行間でハッシュが異なった。成功した2実行で380入力と44出力のハッシュを検証し、採取物9,287,311バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-pharyngeal-second-cell-48000-repeat/manifest.json)

## 現在慣性だけを変える連続描画の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は肺圧・声門面積を内部点ごとに更新し、気道網の放射を間引き器に渡す。[`AirwayNetwork::step` の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029) では、現在慣性 `L`（g/cm⁴）とレート `Fs` を掛け、抵抗を加えて線形項 `B` を作る。左右の圧差に乱流圧と持ち越し運動量の換算値を足した駆動圧を `D` とする。流量 `U`（cm³/s）は、方向別の損失 `K` を選び、`D = B×U + K×|U|×U` の根を求める。枝流量を両端節点の体積収支に入れ、壁流出を差し引いて次の圧力を求める。[上流の狭窄流量試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

研究版の [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) では時間刻み `dt` で除算する。内部96 kHzでは `dt=1/Fs` を二進64ビットに丸めるため、演算順による差が生じる。節点14から15へ向かう直列枝だけで `B` に入る慣性を `L×Fs` で求める。8,207点目は前回流量がゼロで他の入力も一致するため、この点の流出は上流に一致すると予測する。8,214点目の節点圧と8,229点目の入口側の流入も採り、連続更新の中で残る差を確認する。PCMは発声と停止を含む93,056フレームを比較する。[上流のホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[事前登録](../cases/fixed-voice-pharyngeal-second-cell-inertance-48000.json)

## 連続描画で一致した量と残った差

前回の隔離版に、声門の出口から数えて2本目にあたる枝14→15の現在慣性の換算を加えた。枝の選択は描画の全区間で有効。持ち越し圧は対照と同じ式で換算した。通常CLIで描画すると、8,207点目の流出 `7.393769321880806×10⁻¹⁵` cm³/s、8,214点目の節点14の圧力 `2.8941281493271143×10⁻⁶` dyn/cm²、8,229点目の枝13→14の流入 `0.005927820418724875` cm³/s が上流とビット一致した。[変更差分](../runs/fixed-voice-pharyngeal-second-cell-inertance-48000-repeat/artifacts/candidate-second-cell-inertance.patch)・[連続描画の測定値](../runs/fixed-voice-pharyngeal-second-cell-inertance-48000-repeat/summary.json)

枝14→15の流出の初差は8,207から8,218点目へ移った。8,218点目の前回流量・持ち越し運動量・左右圧・現在慣性は同じで、持ち越し圧だけが `0.00003202848779843471` と `0.0000320284877984347` dyn/cm² に分かれた。持ち越し圧を上流値にすると流出を復元できた。節点14の圧力は8,222点目、入口側の枝の流量は8,228点目に初差が現れた。[最初に残る枝と節点の比較](../runs/fixed-voice-pharyngeal-second-cell-inertance-48000-repeat/summary.json)

放射流量微分の初差は8,231から8,221点目へ早まった。この点の壁流量和を再計算すると、枝の出口にあたる節点15の壁流量だけを上流値にした場合に微分が一致した。壁面積と壁速度はどちらも異なり、この両方を上流値にすると壁流量を再現できた。壁面積または壁速度の単独置換でも、合算と微分の丸めを通した値は上流と一致した。節点15のこの時点の壁入力圧は一致していた。[壁流量和の独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-radiation-48000.json)

全93,056フレームで上流とビットが異なるPCMは両版とも停止後の12フレームだった。変更版で最初の差は61,467から55,880フレーム目へ早まり、最大絶対差は `2.2737368×10⁻¹³` から `5.8207661×10⁻¹¹` に増えた。変更版と対照の間で異なるPCMは停止後の8フレーム。両版ともホスト分割128・77の間でビット一致し、既存の許容差 `5×10⁻⁷` に収まった。早期の放射差から停止後のPCM差までの伝播は未追跡。[生PCMの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-inertance-48000.json)

## 慣性換算の実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_pharyngeal_second_cell_inertance.py \
  fixed-voice-pharyngeal-second-cell-inertance-48000-a

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_pharyngeal_second_cell_inertance.py" \
  fixed-voice-pharyngeal-second-cell-inertance-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、各9判定と固定上流の各12試験に合格した。各実行で両条件の壁・節点各104点と枝208点を十進数で検算した。放射を採った64点では各壁の速度・変位と壁流量和・放射微分を有理数でも再現した。再実行で19出力がバイト一致し、計392入力と56出力のハッシュを照合した。採取データ20,882,248バイトをRTL9210B-CGに保存した。[最初の実行](../runs/fixed-voice-pharyngeal-second-cell-inertance-48000-a/manifest.json)・[再実行](../runs/fixed-voice-pharyngeal-second-cell-inertance-48000-repeat/manifest.json)

## 同じ枝の持ち越し圧を揃える予測

固定上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) が声門面積を渡すたびに、気道網の [枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029) が前回流量と運動量を読む。慣性 `L` が小さくなるときは現在の `L` に前回流量を掛け、ほかの場合は保存済みの運動量を使う。運動量に `Fs` を掛けた値は圧力（dyn/cm²）で、左右の圧差と乱流圧に加える。現在慣性の換算値と抵抗、方向別損失から流量を解き、次回用の流量・運動量・慣性を保存する。その後、壁流量と節点圧を更新する。[狭窄の流量試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[ホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

8,218点目で前回流量は両版とも `7.074663484976963×10⁻⁷` cm³/s、持ち越し運動量は `3.336300812336948×10⁻¹⁰` g/(cm·s) だった。前回の現在慣性の変更版を対照にし、枝14→15の持ち越し項を `(L_carry/dt)×U_prev` から `(L_carry×U_prev)×Fs` に切り替える。この点の流出の一致を予測する。8,221点目の節点15の壁入力圧・速度・面積・流量と放射微分を比較し、壁面積の差が放射に残るかを観測する。[前回の残差](../runs/fixed-voice-pharyngeal-second-cell-inertance-48000-repeat/summary.json)・[事前登録](../cases/fixed-voice-pharyngeal-second-cell-history-48000.json)

## 持ち越し圧を揃えた連続描画の結果

隔離版の枝14→15で持ち越し圧だけを上流と同じ順にした。8,218点目の流出 `1.992494179942867×10⁻⁶` cm³/s が上流と一致した。内部8,188〜8,239の52点すべてで、枝13→14と14→15の流量、節点14の圧力と壁流量が上流とビット一致した。枝14→15が読む節点15の圧力には8,232点目から差があり、この区間内では枝流量の丸め結果に差が生じなかった。[実験差分](../runs/fixed-voice-pharyngeal-second-cell-history-48000-repeat/artifacts/candidate-second-cell-history.patch)・[観測値](../runs/fixed-voice-pharyngeal-second-cell-history-48000-repeat/summary.json)

8,221点目の節点15で、壁運動の更新に入る前回速度・変位と、更新後の速度が上流に一致した。面積は変更版 `2.0290595968318863`、上流 `2.029059596831886` cm² で、面積と速度の積である壁流量は1 ULP異なった。壁流量の合算後、放射微分は上流の `0.001655375271559177` cm³/s² に一致した。観測した64点で放射微分の初差は8,221から8,237点目へ移った。この点では節点17と21の壁流量を同時に上流値へ置換すると、残る放射微分を復元できた。節点17の壁面積と壁速度、節点21の壁入力圧と速度には差があった。[壁の置換の独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-history-radiation-48000.json)

全93,056フレームで上流とビットが異なるPCMは停止後の12から13フレームへ増えた。最初の差は出力55,880フレーム目、最大絶対差は `5.8207661×10⁻¹¹` で両条件とも同じだった。対照と変更版の間で異なるPCMは停止後の7フレーム。ホスト分割128・77は各条件でビット一致した。停止後の差を追うには、出力55,880フレーム目に対応する内部111,761点目の周辺で、放射、間引き、直流除去と出力制限の値を採る。[生PCMの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-history-48000.json)

## 持ち越し圧の実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_pharyngeal_second_cell_inertance.py \
  fixed-voice-pharyngeal-second-cell-history-48000-a \
  --case cases/fixed-voice-pharyngeal-second-cell-history-48000.json

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_pharyngeal_second_cell_inertance.py" \
  fixed-voice-pharyngeal-second-cell-history-48000-repeat \
  --case "$experiment/cases/fixed-voice-pharyngeal-second-cell-history-48000.json"
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各9判定と固定上流の各12試験に合格した。両条件の壁と節点各104点、枝208点の更新を十進数で独立に再計算した。再実行間で19出力にバイト差がなく、計404入力と56出力のハッシュを照合した。採取データ20,882,400バイトをRTL9210B-CGに保存した。[最初の実行](../runs/fixed-voice-pharyngeal-second-cell-history-48000-a/manifest.json)・[再実行](../runs/fixed-voice-pharyngeal-second-cell-history-48000-repeat/manifest.json)
