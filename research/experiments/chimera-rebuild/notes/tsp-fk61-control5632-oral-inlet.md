# FK61_01の咽頭から口腔へ入る流量と口腔の体積源

[前回の六節点の比較](tsp-fk61-control5632-upstream-drive.md#実測)では、5863の枝41→42の流量差に対して、枝37→38から入る流量系列の影響が最大だった。今回は境界を口腔の咽頭側の接続まで移し、咽頭から入った差と、口腔で生じた体積源の差を分ける。固定上流・研究版・下唇内面の評価順を上流に揃えた試験版を、同じ通常テキストCLIで比較する。内部96 kHz、出力48 kHz。節点と標本の番号は0始まり。

## 口腔入口の収支と状態更新

通常テキストCLIが発話計画を作り、`HumanVoice::render` が制御・肺圧・声門開口を更新して気道を進める。女性設定の96 kHzでは気管が13、咽頭が15、口腔が16セルで、口腔は節点28〜43。咽頭端の節点27から接続枝27→28が入る。上流の `add_tube` は管内の枝を先に登録し、`connect` が管どうしの枝を後から登録する。研究版も管内の接続を作った後に咽頭から口腔への枝を加える。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の管のセル数と接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L108)・[上流の枝登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L440)・[研究版の接続](../crates/vocal-core/src/airway/human.rs#L210)

各標本では幾何を補間し、体積差から求めた流量を配分・二段平滑して節点に加える。次に旧圧力、枝の旧流量・慣性、新しい係数と乱流圧から枝流量を得る。その後に壁流量を引き、圧力を更新する。口腔入口の節点28では、体積源 `q₀` に対し、まず枝28→29への流出を引き、次に枝27→28からの流入を足す。口腔内の他の内部節点では、流入枝が流出枝より先に登録されている。

\[
q_{28}=(q_0-U_{28\to29})+U_{27\to28}-U_{\rm wall},\qquad
p_{\rm new}=p_{\rm old}+(\Delta t/C)q_{28},\qquad C=V/(\rho c^2).
\]

流量は cm³/s、圧力は dyn/cm²、コンプライアンスは cm⁵/dyn。口端43は圧力と慣性枝流量を並列R–L負荷で連成する。採取した枝の行順で入口の加算順を検証し、同じ順で16節点を計算する。枝27→28の流量は観測値から与える。 [上流の気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[上流のR–L負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1123)・[逐次計算](../tools/measure_tsp_fk61_control5632_upstream_drive.py#L24)

通常CLIと観測版を照合し、上流の密閉腔・定常狭窄・再開口の試験と研究版の幾何補間試験を実行する。局所の体積源、枝、壁、圧力、口端負荷は独立した計算でも照合する。 [上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 比較条件

観測窓は5630〜5875、逐次計算は5632〜5875。初期状態、咽頭の枝27→28、節点28〜37の体積源、節点38〜43の体積源、局所係数と乱流圧の5群を上流と交換する全32組を比較する。体積源を口腔の各節点で単独交換する16条件も測る。先行の六節点比較の境界枝37→38を上流値に固定した条件と、それに節点38〜41の体積源の交換を加えた条件も再現する。口端流量の5863・5864を出力段に戻す場合と、5632〜5875を戻す場合を比べる。壁と鼻端の放射は試験版の観測値を使う。 [事前登録](../cases/tsp-fk61-control5632-oral-inlet.json)

## 実測

3版とも観測した枝27→28の行が管内の15枝より後にあった。局所計算と、固定上流・試験版の口腔16節点を連成した244標本の計算が、枝・壁・節点圧・口端負荷の観測値に一致した。以前の六節点と重なる観測と、枝37→38を固定した2条件も一致した。

| 内部標本 | 固定上流と試験版の枝37→38の差（cm³/s） | 咽頭流入だけを交換した変化（cm³/s） | 節点28〜37の体積源だけを交換した変化（cm³/s） |
| ---: | ---: | ---: | ---: |
| 5675 | −2.274×10⁻¹³ | +1.485×10⁻¹² | −1.716×10⁻¹² |
| 5723 | −6.853×10⁻¹² | +2.302×10⁻¹² | −9.504×10⁻¹² |
| 5863 | −2.300×10⁻¹¹ | −4.096×10⁻¹² | −1.867×10⁻¹¹ |

5863の枝37→38の流量差は、節点28〜37の体積源だけで約81.2%、咽頭流入だけで約17.8%、両方の組合せで約99.0%を再現した。咽頭流入が最大という事前予測は棄却した。観測した枝流量の差の絶対値が10⁻¹² cm³/s以上となる最初の標本は、枝29→30から33→34までが計算窓の冒頭5632、咽頭の枝27→28が5660、枝37→38が5686だった。16節点の体積源単独交換では節点34が最大で、5863の枝37→38を −4.501×10⁻¹² cm³/s 動かした。 [結果要約](../runs/tsp-fk61-control5632-oral-inlet-20261123-repeat/summary.json)・[保存した軌道](../runs/tsp-fk61-control5632-oral-inlet-20261123-repeat/artifacts/trajectories.npz)

口端流量を2標本だけ戻すと12組、全244標本を戻すと5組で、PCMが冒頭から2937まで固定上流と一致した。全区間で一致した5組には咽頭流入と節点28〜37の体積源の交換が含まれた。この2群だけを交換した場合、PCM 2937の変換前の値は +1.421×10⁻¹⁴ 動き、丸めの境目までの差 +1.410×10⁻¹⁴ を約1.09×10⁻¹⁶ 上回った。PCM 2938以降はこの交換比較の判定範囲外。 [出力の再計算](../runs/tsp-fk61-control5632-oral-inlet-20261123-repeat/summary.json)

保存した形状を追加で調べると、5632・5675・5760・5863の各標本で、口腔16節点が同じ長さの差を共有した。節点34では、面積と長さの積を丸めず体積速度を求めても、固定上流と試験版の差は5632で −3.678×10⁻¹¹ cm³/s、5760で +3.677×10⁻¹¹ cm³/sだった。次はこの2つの制御境界の前後で目標口腔長・補間開始値・標本あたりの長さ増分を採取する。面積と長さを個別に交換し、節点34の体積源にどちらが効くかを判定する。 [上流の口腔長と断面積の設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L306)・[研究版の目標設定](../crates/vocal-core/src/airway/human.rs#L350)・[体積速度の有理数検算](../tools/measure_tsp_fk61_oral_onset_inflow.py#L140)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。研究ワークスペースと `/tmp` で実行し、各5判定とRustの11試験に通過した。各版の全116,132フレームで通常CLIと観測版がビット一致した。初回と再実行で採取系列17点・状態軌道・結果要約がバイト一致した。採取系列と状態軌道はRTL9210B-CGに保存した。 [初回マニフェスト](../runs/tsp-fk61-control5632-oral-inlet-20261123-registered/manifest.json)・[再実行マニフェスト](../runs/tsp-fk61-control5632-oral-inlet-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_control5632_oral_inlet.py tsp-fk61-control5632-oral-inlet-new
```
