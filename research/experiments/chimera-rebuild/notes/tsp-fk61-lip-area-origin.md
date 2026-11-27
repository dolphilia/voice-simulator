# FK61_01の口端セルの面積差を測定線まで追う

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。標準の研究版と同じ成人女性体型、発話、辞書、96 kHz内部レートで比較する。口端の体積流量差が出た内部標本3968に加えて、音声を作る前の初期値を採取する。 [事前登録](../cases/tsp-fk61-lip-area-origin.json)・[先行する口端流量の観測](tsp-fk61-lip-onset.md)・[体積差分の比較](tsp-fk61-lip-volume-increment.md)

## 読解

上流の `chimera render text` は英文をスコアにして `HumanVoice` を作る。コンストラクターで `HumanAirway::apply` に中立姿勢と `dt=0` を渡し、`snap_to_targets` で面積とセル長を気道に直接設定する。描画中は128内部標本ごとに `HumanVoice::control` が姿勢を更新し、`HumanAirway::commit` へ進む。声道の計算は `HumanVocalTract::compute` で測定線の座標、光線で測った隙間、接触補正後の隙間と面積を確定し、`resample` が気道の等長セルへ割り当てる。制御周期中には、直前に確定した面積を基準に開口・閉鎖速度を制限し、`set_tube_targets` と `begin_block` で次の標本から補間する。 [上流の通常CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs)・[初期化・制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L274)・[声道の確定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[目標の登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L647)

研究版の `vocal-cli render-pcm` は `ArticulatedVoice` を使う。調音制御の `geometry` は姿勢から矢状断の輪郭、接触補正、軸上距離に並べた面積を求める。等長セルへ再標本化した直後の値を `raw` に置き、開閉速度の制限後を `limited` に置く。初期化では `HumanAirway::from_targets` でその断面を直接使う。描画中は `begin_tract_block` が制限済みの平均面積・最小面積［cm²］と音響セル長［cm］を登録する。 [研究版の通常CLI](../crates/vocal-cli/src/main.rs#L452)・[研究版の調音制御](../crates/vocal-core/src/airway/tract_control.rs#L180)・[気道への登録](../crates/vocal-core/src/airway/human.rs#L341)

両実装の再標本化は、口腔の開始位置と口端位置から等長セルを作り、各セルの8つの小区間の中点で面積を線形補間する。その8値の調和平均を平均面積にし、元の測定線と8中点の最小面積を合わせて絞りの判定に使う。面積が1×10⁻⁵ cm²以下の箇所があればセルを閉じる。末端の測定線は軸上の位置に1×10⁻⁶ cmの余裕を設けて閉鎖の確認に含める。独立計算は採取した軸上の位置と面積から、末端セルの8中点を再構築する。上流の幾何ゴールデン試験は測定線・輪郭・再標本化を照合し、研究版の補間試験は長さとポート開口を同じ標本で更新することを照合する。 [上流の再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs)・[研究版の再標本化](../crates/vocal-core/src/anatomy/resample.rs#L87)・[補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 実測

| 状態 | 固定上流の口端平均面積［cm²］ | 研究版の口端平均面積［cm²］ |
| --- | ---: | ---: |
| 描画前・再標本化直後 | 1.3749486460641938 | 1.3749486460641942 |
| 描画前・気道の初期値 | 1.3749486460641938 | 1.3749486460641942 |
| 標本3968の制御更新で登録した面積目標 | 1.3749343004054988 | 1.3749343004054988 |
| 標本3968の更新直後 | 1.3749485339887353 | 1.3749485339887357 |

初期の差は、口腔16セルの境界を決める値が一致した状態で、口端を作る測定線の面積に既にあった。0始まりの測定線45と46に差があり、測定線47・48の面積と4本の軸上位置は一致した。両側の元データで8中点から平均と最小面積を再現した。初期の面積だけを交換すると、両方向で相手側のセル面積になった。標本3968の目標平均面積は両版で一致し、速度制限の前後も一致した。先行実行の標本3968・3969の現在値を旧面積からの補間で再現した。 [観測と独立再計算](../runs/tsp-fk61-lip-area-origin-20261123-ray-repeat/summary.json)

測定した後に、初期の面積差が出た測定線を1本ずつ交換した。研究版に対する測定線46の面積だけの交換で固定上流の平均面積を再現した。逆方向では45と46の両方を交換すると一致した。46の唇の幅は両者とも2.475 cmで、補正後の隙間が0.7288049712と0.7288049712000005 cmだった。この隙間を楕円面積の式に入れて測定線46の差を再現した。45では補正後の隙間が一致し、測定線中央のx座標の差が歯列から唇へ切り替える補間の重みに伝わった。 [交換の記録](../runs/tsp-fk61-lip-area-origin-20261123-ray-repeat/summary.json)

制御更新後の口端の軸上位置は、研究版が約3.55×10⁻¹⁵ cm短かった。両側で口腔の開始位置は一致した。8中点の面積は各実装の境界と測定線を組み合わせると一致し、面積目標も一致した。長さの目標は2.22×10⁻¹⁶ cm異なった。口端の初期差に寄与した測定線45・46で、座標と補正後の隙間を分ける数値の発生箇所は未特定。次は描画前に絞り、唇端の位置、測定線中央のx座標、`aperture + depth²/(1.2·scale)` の上限を順に比べる。 [上流の唇接触](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1165)・[研究版の接触上限](../crates/vocal-core/src/anatomy/contact.rs#L60)

## 再実行

研究ワークスペースで新しい実行IDを指定する。観測用のRustビルドはRTL9210B-CG上の一時チェックアウトに置く。各側5時点の測定線と断面、独立計算の結果、PCMハッシュ、試験ログを保存する。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。通常CLI・観測器・保存済みPCMは各側の全116,132フレームでビット一致した。研究ワークスペースと `/tmp` の再実行は各4判定、固定上流の幾何試験、研究版の補間試験に通過し、観測2ファイル、列定義、PCMハッシュ、要約の5出力がバイト一致した。初回と事後の交換を加えた実行の観測列も一致した。 [初回](../runs/tsp-fk61-lip-area-origin-20261123/manifest.json)・[再実行](../runs/tsp-fk61-lip-area-origin-20261123-ray-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_lip_area_origin.py fk61-lip-area-origin-new
```
