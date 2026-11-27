# CSDの咽頭セル7で初期面積と目標面積の影響を分ける

測定線5のx座標の交換で、6番の累積弧長だけが1 ULP変わった。再標本化の事後計算では、咽頭の0始まりのセル7で代表面積が変わると見積もった。今回はそのセルの初期面積と最初の目標面積を実測し、両者を個別に交換して最初の体積速度と出力の変化を追う。 [中心座標交換の測定](csd-en001a-centerline-coordinate-swap.md#交換が伝わった範囲)・[ケース定義](../cases/csd-en001a-pharynx-cell7-source.json)

## 面積から体積速度まで

上流の `HumanAirway::commit` は `HumanVocalTract::resample` で咽頭の代表面積と最小断面を出し、開閉速度を制限して `set_tube_targets` に渡す。咽頭を等長に区切った各セルでは、8区間の中点で断面を補間し、調和平均を代表面積とする。閉鎖を見落とさないため、区間内の測定線も最小値の判定に使う。研究版は `HumanTractControl` で `AreaProfile::cell` を通った値を保持し、初期化では `HumanAirway::from_targets` に、その後は `begin_tract_block` に渡す。 [上流の再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[上流の目標への反映](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[研究版の再標本化](../crates/vocal-core/src/anatomy/resample.rs#L95)・[研究版の気道更新](../crates/vocal-core/src/airway/human.rs#L67)

1標本の面積更新は初期面積と目標の差の1/128を足して計算する。長さ（cm）と面積（cm²）の積がセル体積（cm³）になる。上流は前値からの体積差に内部レートを掛け、研究版は内部標本周期で割って、壁の移動が気道に与える体積速度（cm³/s）を求める。閉鎖に近いときは最小断面に応じて流量を隣接節点へ配分する。配分後の体積速度を60 Hzの二段平滑に通し、気道の流量収支へ加える。代表面積はこの経路に加え、枝の慣性や節点のコンプライアンスにも作用する。ここで面積交換からPCMを再現できた場合も、体積速度だけの寄与は別に照合する。 [上流の補間・体積源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L833)・[研究版の面積補間・体積源](../crates/vocal-core/src/airway/network/geometry.rs#L50)・[研究版の枝・節点の更新](../crates/vocal-core/src/airway/network.rs)・[上流の幾何の基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs)

## 事前に決めた条件

測定線5の座標交換で動く咽頭断面をセル7の代表面積と予測した。目標面積だけを交換しても、128分割した最初の増分では体積差が変わらないと予測した。初期面積と目標面積を共に渡したとき、PCMが測定線5の座標を交換した対照を再現するかも検証する。先行の格子から独立計算した面積を交換入力に使い、実行中に採取する面積にも照合する。 [事前登録の条件と合否基準](../cases/csd-en001a-pharynx-cell7-source.json)

## 実測

初期化直後と最初の制御更新後の両方で、測定線5の座標交換によって咽頭15セルのうち代表面積が変わったのはセル7だけだった。最小断面は全セルで一致した。セル7・8の実測値は、保存された格子から独立に求めた8点の再標本化にビット一致した。 [全セルの測定値](../runs/csd-en001a-pharynx-cell7-source-20261124-registered/artifacts/observations.json)

| 測定線5の交換によるセル7の面積差 | 上流 | 研究版 |
| --- | ---: | ---: |
| 初期面積（cm²） | −8.882×10⁻¹⁶ | +1.332×10⁻¹⁵ |
| 最初の目標面積（cm²） | −8.882×10⁻¹⁶ | +8.882×10⁻¹⁶ |

**セル7の初期面積だけの交換で、両版とも測定線5の交換と201,600 PCMフレームすべてがビット一致した。** 最初の目標面積だけの交換では、両版とも通常描画と全PCMが一致した。初期面積と目標をともに交換したときも測定線5の交換を再現した。通常描画と比べた最大絶対差は両版とも出力フレーム134,534で7.276×10⁻¹²（1 ULP）だった。 [条件別の結果](../runs/csd-en001a-pharynx-cell7-source-20261124-registered/summary.json)・[PCMのハッシュ](../runs/csd-en001a-pharynx-cell7-source-20261124-registered/artifacts/pcm-digests.json)

内部標本0・1では、初期面積を交換した条件でセル7の体積が変わった。各標本の体積差から得た速度は全条件で一致し、標本0で−0.02350429689812472 cm³/s、標本1で−0.023504297878673697 cm³/sだった。二段平滑後の体積速度も一致した。目標面積だけを交換すると1標本分の増分の変化は約6.94×10⁻¹⁸ cm²で、面積の加算が同じ値に丸められた。65フレーム完了時には咽頭の目標と格子が通常条件と一致していた。 [体積速度と更新後の独立計算](../runs/csd-en001a-pharynx-cell7-source-20261124-registered/summary.json)

採取した最初の面積・長さ・体積と補間増分から、事後に最初の制御ブロックの128標本を逐次再計算した。各標本で面積と長さに増分を加え、倍精度の積で新しい体積を作り、直前との差を体積速度に換算した。標本0・1は実測と一致した。初期面積だけの交換で局所の配分前の体積速度が通常条件から分かれるのは、上流で標本12、研究版で標本8と予測された。128標本中それぞれ20・32標本で差が生じ、最大差の予測は両版で2.132×10⁻¹¹ cm³/sだった。 [再計算の入力](../runs/csd-en001a-pharynx-cell7-source-20261124-registered/artifacts/observations.json)・[上流の体積差の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L851)・[研究版の体積差の計算](../crates/vocal-core/src/airway/network/geometry.rs#L124)

次は、セル7とその前後の枝で最初の制御ブロックの128標本を読む。体積速度が標本12・8で分かれるという事後予測を実測と照合し、コンプライアンス、枝の慣性・抵抗、圧力と流量も追う。最初に分かれた入力だけを交換して、初期面積の差が後続PCMへ届く経路を切り分ける。

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使った。上流の基準幾何と気道の7試験、研究版の再標本化の1試験を通過した。作業用のRTL9210B-CGで上流と研究版を別々にビルドし、両版各5条件のPCM、内部状態、ハッシュと観測差分を保存した。 [実行条件と保存先](../runs/csd-en001a-pharynx-cell7-source-20261124-registered/manifest.json)

研究ワークスペースと `/tmp` からの2実行で各3判定を通り、内部状態、PCMハッシュと計画、圧縮PCM、両版の観測差分、要約の6出力はバイト一致した。 [再実行の記録](../runs/csd-en001a-pharynx-cell7-source-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_csd_en001a_pharynx_cell7_source.py csd-en001a-pharynx-cell7-source-new
```
