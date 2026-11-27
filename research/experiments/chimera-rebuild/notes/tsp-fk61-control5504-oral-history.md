# FK61_01の口腔の中心線と体積源の平滑履歴

[前回の形状交換](tsp-fk61-control5632-oral-geometry.md#実測)で、5632より前の平滑状態がPCMフレーム2937に効くことを確認した。今回は一つ前の制御境界5504から5631までを再計算する。比較は女性設定のFK61_01、内部96 kHz、出力48 kHz。節点・標本・格子点の番号は0始まり。

## 中心線から体積源まで

通常CLIの英語テキストは発話計画を作り、`HumanVoice::control` が128内部標本ごとに姿勢を更新する。接触補正がある制御境界では気道形状を計算し直し、最後の形状で次の補間を準備する。上流の `HumanVocalTract::compute` は測定線の内側と外側の交点の中点を順に並べる。格子先頭の弧長を喉頭前庭の長さとし、隣接する中点の距離を加算する。口腔側への切り替えは後ろから前へ回す測定線の角度で決まり、その位置までの弧長が咽頭長になる。唇の弧長は最後の格子点の値。研究版でも `AreaProfile` が同じ格子中点の距離を足し、最初の口腔側の格子点を咽頭端として使う。 [通常CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[制御境界と接触補正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L495)・[上流の測定線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1036)・[上流の弧長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1222)・[研究版の断面と弧長](../crates/vocal-core/src/anatomy/area.rs#L78)

唇までの弧長を \(s_l\)、咽頭端までの弧長を \(s_p\) とすると、解剖学的な口腔長は \(s_l-s_p\) cm。安定条件による延長がないとき、これを16等分した値が全口腔節点のセル長目標になる。上流の `begin_block` と研究版の `MovingAreas::set_targets` は現在値との差を128で割って増分を作り、各標本で反復加算する。各節点の体積は下限付きの断面積とセル長の積。体積が減ると正の流量が生じ、配分の後に一極フィルターを二段通して節点へ加える。 [上流の再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1378)・[上流の増分と配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)・[研究版の再標本化](../crates/vocal-core/src/anatomy/resample.rs#L72)・[研究版の補間と平滑](../crates/vocal-core/src/airway/network/geometry.rs#L47)

```mermaid
flowchart LR
    A["測定線の中点"] --> B["咽頭端と唇の累積弧長"]
    B --> C["口腔長の目標と128回の加算"]
    C --> D["節点体積の標本差"]
    D --> E["二段平滑の状態"]
    E --> F["次の制御ブロックとPCM"]
```

平滑係数を \(\alpha\)、\(d=1-\alpha\) とする。入力を固定して初期状態だけを交換すると、\(k\) 標本後の第一極の差は \(d^k\Delta p_1\)、第二極の差は \(d^k(\Delta p_2+k\alpha\Delta p_1)\) となる。第二極は同じ標本で更新済みの第一極を受け取る。極と入力の単位は cm³/s。この離散式で、形状から再計算した流量と初期状態の残存分を分ける。 [上流の二段平滑](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L899)・[研究版の二段平滑](../crates/vocal-core/src/airway/network/geometry.rs#L158)

上流の形状連続性試験は測定線の移動に対する断面積を比較しており、密閉空洞試験は断面積の変化から生じた圧力の積分を解析式に照合する。今回の通常CLI照合では一様管試験と気道の境界条件試験を実行し、研究版では幾何補間中にポートを変更する試験を実行する。 [上流の形状連続性](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L119)・[上流の密閉空洞試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 比較条件

制御境界5504・5632・5760で、中心線の中点・領域・累積弧長・咽頭端と形状目標を採る。5504〜5631の節点28〜37で、平滑器の開始値、面積系列、セル長の開始値、唇と咽頭端それぞれの弧長目標の5群を交換する。32組それぞれで5631終了時の平滑状態を求める。5632以降は前回の全形状と咽頭流入の交換条件で揃え、上流の5631の体積と、各組から受け取った平滑器の状態で次区間を開始する。比較は口端流量を出力段へ戻したときのPCM 2937まで。 [事前登録](../cases/tsp-fk61-control5504-oral-history.json)・[計測器](../tools/measure_tsp_fk61_control5504_oral_history.py)

## 実測

3版とも49格子点で、咽頭端は格子点19だった。中点の距離から求めた弧長と採取値の差は最大1.78×10⁻¹⁵ cm。固定上流と試験版の5504では、座標は格子点2、累積弧長は格子点29で最初に分かれた。両端では一致し、5504のセル長の開始値・目標値と5631終了時のセル長も一致した。採取した制御境界のうち、口腔長の差は5632の唇側で初めて現れた。固定上流の唇までの弧長は5632で +1.776×10⁻¹⁵ cm、5760で +3.553×10⁻¹⁵ cm 長く、咽頭端までの弧長は両境界で一致した。5504で唇側の差が強く効くという予測と、同ブロックの反復加算が長さ目標の差を広げるという予測を棄却した。 [中心線と交換結果](../runs/tsp-fk61-control5504-oral-history-20261123-first/summary.json)

| 5504〜5631での交換条件 | 5631の第二極10節点の変化のL2ノルム（cm³/s） | PCM 2937の変換前の変化（無交換の試験版に対して） | PCM 2937までの一致 |
| --- | ---: | ---: | --- |
| 5503終了時の平滑状態のみ | 9.377×10⁻¹³ | +1.400×10⁻¹⁴ | 2937で差 |
| 断面積のみ | 1.404×10⁻¹⁴ | +1.238×10⁻¹⁴ | 2937で差 |
| 平滑状態と断面積 | 9.435×10⁻¹³ | +1.421×10⁻¹⁴ | 一致 |

5503終了時の平滑状態による5631の変化は断面積のみの約67倍で、区間内の形状が優勢という予測を棄却した。第一極と第二極の初期値交換を離散式で独立計算すると、逐次計算との差は最大8.04×10⁻¹⁶ cm³/sだった。全5群を交換したときの5631の両極は固定上流と一致した。PCMが冒頭から2937まで一致した8組は、平滑の開始値と断面積の両方を交換した条件だった。残る3群のセル長の開始値と両端の弧長は5504で一致しており、交換しても出力は変わらなかった。 [状態軌道](../runs/tsp-fk61-control5504-oral-history-20261123-first/artifacts/trajectories.npz)

断面積だけの交換による変化は、保存した `history_area` と `history_unchanged` の生の体積速度の差からも検算した。5631から \(j\) 標本前の差に重み \(\alpha^2(j+1)(1-\alpha)^j\) を掛け、標本順に足す。5631の第二極の予測と逐次計算との差は最大2.28×10⁻¹⁶ cm³/s だった。この重みを使うと、さらに前の期間を採取した際も、5503に残った変化を標本や制御ブロックごとに集計できる。 [保存した体積速度と第二極](../runs/tsp-fk61-control5504-oral-history-20261123-repeat/artifacts/trajectories.npz)

次は発声初期を含む3968〜5503をまとめて採り、5503に残った平滑状態を、区間内で生じた生の体積速度の差と採取開始時から残る状態に分ける。開始点を動かして寄与の大きい範囲を特定し、同じ区間の形状と出力で照合する。 [発声初期の体積源での採取](tsp-fk61-oral-onset-inflow.md)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。研究ワークスペースと `/tmp` で各4判定とRustの11試験に通過した。3版それぞれで通常CLI・観測版・保存済みPCMの全116,132フレームが一致した。2実行で中心線を含む採取系列・状態軌道・要約の28出力がバイト一致した。採取系列と状態軌道はRTL9210B-CGに保存した。 [初回のマニフェスト](../runs/tsp-fk61-control5504-oral-history-20261123-first/manifest.json)・[再実行のマニフェスト](../runs/tsp-fk61-control5504-oral-history-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_control5504_oral_history.py tsp-fk61-control5504-oral-history-new
```
