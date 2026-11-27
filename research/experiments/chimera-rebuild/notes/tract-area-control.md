# 制御フレームから可動声道の断面目標を作る

2026-11-19。対象は固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の成人男性モデル。単位は cm、cm²、s。

## 読んだ経路と処理順

1. [human_voice.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L488) の `HumanVoice::control` は調音器を進め、`HumanAirway::apply` を呼ぶ。[`enforce_contacts`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L556) はその形状の舌先・舌体の接触距離と法線を使う。食い込みが0.1 cmを超えた点を上限へ戻し、接触面へ向かう速度成分を除去する。口腔側 x の変位・速度には座標変換の係数 `1/0.86` を使う。目標値は保持される。補正が起きたフレームだけ `reapply` が呼ばれる。
2. [human_airway.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214) の `apply` は前の制御フレームで確定した平均・最小断面を保存する。`commit` は矢状断形状を等長セルへ再標本化し、この保存値を基準に断面の増減を制限する。`reapply` でも同じ基準と制御周期を使う。初期化で経過時間を0とすると幾何形状をそのまま目標にできる。
3. [network.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L647) の `set_tube_targets` に制限後の断面と音響用管長が渡る。`begin_block` 以降に面積・最小断面・セル長のサンプルごとの補間が始まる。今回の観測点は制御側で目標を確定した時点。

## 断面制限の式

- 前フレームの面積を `A`、今回の幾何上の面積を `G`、制御周期を `dt` とする。閉鎖方向に減らせる面積は `(r(A) + 40A) dt`。基礎速度 `r` は `A < 0.03` で `5 sqrt(A/0.03)`。0.03 から 0.4 cm² の間では三次補間で 5 から 45 cm²/s に増え、それ以上は 45 cm²/s。
- 開口方向に増やせる面積は `(r(A) + 40G) dt`。基礎速度は通常 45 cm²/s。口腔の歯より前のセルでは、0.03 から 0.06 cm² の間で 7 から 45 cm²/s へ三次補間する。歯より前のセルは歯列の中心線上の距離と口腔長から各フレームで判定する。
- 平均断面と最小断面の両方に同じ式を適用する。最後に最小断面を 0 以上、制限後の平均断面以下に収める。音響用の管長は解剖学的管長と `セル数 × (35000 / 内部サンプルレート) / 0.97` の大きい方を使い、軟口蓋ポートの目標は幾何から渡す。

## 実装前の予測と判定

96 kHz、128サンプルごと、288フレーム。固定上流版の予備計測に基づき、ここに記した数値範囲をケースに登録した。平均断面・最小断面は全セル、長さは咽頭・口腔、接触距離と軟口蓋は各更新で観測する。固定上流との絶対許容差は面積で `1e-9 cm²`、長さで `1e-9 cm`。面積制限は Python/NumPy による独立計算にも照合する。

- [母音遷移](../cases/tract-slew-vowels.json) は自由舌先の3母音。断面の補正量は最大1 cm²を超え、追加した軟口蓋の開閉でポート目標が0.48〜0.501 cm²に達する。
- [唇の閉鎖と再開口](../cases/tract-slew-lips.json) は口腔末端セルの最小断面を追う。`1e-5 cm²` を閉鎖の判定閾値とする。予備計測の閉鎖は幾何がフレーム22、制限後が37、再開口は両者148。フレーム150で制限後の最小断面は幾何上の値の約20%。
- [舌先補正あり](../cases/tract-slew-contact.json) はフレーム40〜143で補正が続くと予測する。2回目の計算で1回目の出力を基準に流用すると、確定断面に0.05 cm²を超える差が出ると予測する。
- [舌先補正なし](../cases/tract-slew-contact-off.json) は同じ舌先目標を適用する対照条件。再計算は0回で、最も深い食い込みは約0.32 cmと予測する。

上流の [airway_adversarial.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs) の `fast_but_articulator_limited_closure_gives_bounded_piston_pressure` は、面積の変化に伴う圧力を別の閉鎖条件で検証する。予備実行で最大5,882.6 dyn/cm²、閾値19,613.3 dyn/cm²だった。[speech_quality.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/speech_quality.rs#L97) の `the_contact_model_engages_smoothly` は舌先接触の発生と出力を検証する。

## 実装と結果

[声道の制御](../crates/vocal-core/src/airway/tract_control.rs) は成人男性のセル分割と安定長を固定声道と共有する。各更新で幾何上の断面と制限後の断面を保持する。接触補正を使う場合は、[調音器](../crates/vocal-core/src/articulators.rs) が観測した法線で位置と速度を補正し、同じ制御周期内で目標を再計算する。[上流プローブ](../tools/upstream_articulation_probe.rs) は固定版ライブラリの `HumanAirway::apply`・`reapply` と公開の調音状態を使う。接触補正の呼び出し部分は `HumanVoice` の非公開処理に合わせてプローブに置いた。元の上流テストも固定版で別途実行した。

| 条件 | 主な観測 | 実行 |
| --- | --- | --- |
| 自由舌先の母音遷移 | 最大断面補正は1.46234 cm²。軟口蓋目標の最大値は0.49466 cm² | [要約](../runs/tract-slew-vowels-20261119-b/summary.json) |
| 唇の閉鎖と再開口 | 閉鎖はフレーム22から37へ20 ms遅れた。再開口は両方148。フレーム150の制限後の最小断面は幾何上の20.15% | [要約](../runs/tract-slew-lips-20261119-b/summary.json) |
| 舌先補正あり | フレーム40〜143の104回で再計算。補正後の舌先距離は最小−0.10000 cm。1回目の出力を基準にすると、2回目は最大0.15261 cm²ずれる | [要約](../runs/tract-slew-contact-20261119-b/summary.json) |
| 舌先補正なし | 再計算は0回。舌先距離は最小−0.31594 cm | [要約](../runs/tract-slew-contact-off-20261119-b/summary.json) |

全37項目が通過。上下限による独立計算と制限後の面積の最大差は `2.78×10⁻¹⁷ cm²`。固定上流版との最大絶対差は断面で `1.03×10⁻¹³ cm²`、長さと位置で `1.43×10⁻¹⁴ cm`。この4条件の管長は安定長の下限を上回った。短い管を伸ばす分岐は[固定姿勢の短管](fixed-human-airway.md)で検証済み。今回観測した閉鎖時刻は制御フレーム内で確定した断面に対する値で、実際の音響セルとPCMの閉鎖・再開口は後続工程で追う。
