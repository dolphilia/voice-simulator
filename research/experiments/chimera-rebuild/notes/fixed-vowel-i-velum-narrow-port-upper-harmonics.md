# 狭い口蓋帆ポートの第23〜44倍音を予測する

## 上流の読解

- `HumanVoice::render` は内部サンプルごとに肺圧を更新し、声門前後の圧力差を使って開口を求め、`AirwayNetwork::step` を呼ぶ。研究用の内部状態から声門枝流量と鼻端放射の体積流量を取り、同じサンプル番号で照合する。上流の出力音声にはその後で間引き、DC除去、振幅制御がかかる。 [human_voice.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)
- `HumanAirway` の形状構築は咽頭と口腔の接続点を鼻腔入口へ口蓋帆ポートで結ぶ。この収録では30→49を正方向とし、開口0.15 cm²と肺圧7.2 cmH₂Oを固定する。 [human_airway.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L155)
- `AirwayNetwork::step` はポートの入口収縮・出口膨張の係数を順流用と逆流用に計算する。前の節点圧力差と枝の運動量を含む駆動項の符号を使って係数を選び、二次方程式の解から当該サンプルの流量と運動量を更新する。枝流量を節点に集計した後、放射負荷と節点圧力を更新する。固定形状の抵抗・イナータンス項は周波数領域で `Z = R + I fₛ (1−d)`、`d = exp(−2πif/fₛ)` となり、1サンプル早い圧力差を位相遅れで表す。観測損失対照では実測流量と圧力を使って窓の両端のずれも補正する。 [ポートの損失係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[放射負荷の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[観測の枝方程式](../tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py#L109)
- `steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss` は既知の形状・圧力差に対する定常流を解析解と照合する。`formant_bandwidths_agree_between_fdtd_and_the_frequency_domain_model` は同じ管のインパルス応答と線形伝達から帯域幅を求める。今回の有限窓では、これらに加え、FFT、元の粘性節点解、ポート源の重ね合わせ、両版の実測係数を照合する。 [定常流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[帯域幅試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L128)

## 実装前の予測

前回の補正済み第1〜22倍音を基準にすると、実測から第23〜44倍音を加えた事後対照で鼻端誤差は0.11526%から0.00871%へ下がった。この帯域の声門流量を入力して接線解を作り、予測二次損失を一度戻せば、追加した流量係数のL2誤差は接線解から50%以上減り、鼻端では実測追加による改善量の80%以上を回復すると予測した。 [前回の読解と実測](fixed-vowel-i-velum-narrow-port-all-harmonic-feedback.md)・[事前登録](../cases/fixed-vowel-i-velum-narrow-port-upper-harmonics.json)

窓は内部96 kHzのサンプル `[38400, 48000)` とし、最初のサンプルを複素位相の原点とする。流量の単位は cm³/s、圧力と二次損失は dyn/cm²。平均流量 `Ū` の周りで `N(U)=K(U)U|U|` の接線抵抗 `2 K(Ū)|Ū|` を粘性抵抗に足す。平均と第1〜44倍音から合成した波形上で `N` を求め、追加帯域の圧力源から接線抵抗の寄与を引いて一度だけ解き直す。予測用波形の第1〜22倍音はポートだけ補正済みとし、他60枝には接線解を使う。鼻端の比較では他60枝の圧力源を先行ケースの10周波数予測に固定する。第23〜44倍音の追加が観測点2,310 Hzへ及ぼす効果は、この評価ではポート二次損失内の周波数混合に由来する。

## 実測

低域のみの基準と先行の予測を照合し、第23〜44倍音（2,530〜4,840 Hz）を加えた4条件を比較した。次の値は再実装版のもので、固定上流でも同じ丸め値だった。 [比較コード](../tools/measure_fixed_vowel_i_velum_narrow_port_upper_harmonics.py)・[再実行の要約](../runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-repeat/summary.json)

| ポートに加える第23〜44倍音 | 流量係数の相対L2誤差 | 2,310 Hzの鼻端複素相対誤差 |
| --- | ---: | ---: |
| 追加なし | 100% | 0.115257% |
| 接線解 | 7.99479% | 0.00734609% |
| 予測損失を一度戻す | 0.332596% | 0.00861075% |
| 観測損失を一度戻す | 0.00000963% | 0.00871016% |
| 実測係数 | 0% | 0.00871017% |

予測損失を戻すと流量誤差は95.84%減り、実測係数を加えた場合の鼻端改善量の100.093%を回復した。両版で事前基準の50%と80%を満たした。観測損失対照は実測係数の鼻端伝達と相対6.02×10⁻¹¹以内で一致し、FFT・節点解・重ね合わせを含む数値照合の最大相対差は2.09×10⁻¹¹だった。

接線解の鼻端誤差は、予測補正より0.001265ポイント小さかった。鼻端伝達を同じ低域と平均で実測上位倍音だけ足した対照へ照合すると、差は接線解の0.01599%から予測補正で0.0004463%へ減った。流量と鼻端伝達の両方が実測上位倍音の対照に近づいており、接線解で鼻端誤差が小さく見えるのは、残る複素誤差を一部相殺したためと考えられる。第23〜44倍音の全22成分でポート自身の圧力源が流量残差への最大寄与枝だった。補正後の流量の絶対差は2,530 Hzが最大で2.57×10⁻⁵ cm³/sだった。

## 再現手順

初回は研究ワークスペース、再実行は `/tmp` から起動し、159判定と要約を再現した。収録、線形要素、低域の予測結果はマニフェストのSHA-256を照合して読み込んだ。実行環境はmacOS 15.6.1のARM64、Python 3.14.4、NumPy 2.4.4、rustc 1.94.1。固定上流で `cargo test --locked --offline -p chimera --test airway_adversarial` を実行し、6試験に通過した。 [初回のマニフェスト](../runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-repeat/manifest.json)・[上流試験ログ](../runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-repeat/artifacts/upstream-airway-adversarial.log)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 PYTHONDONTWRITEBYTECODE=1 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_narrow_port_upper_harmonics.py \
  fixed-vowel-i-velum-narrow-port-upper-harmonics-check
```

第58版の全体監査は保存したケースと収録から159判定を再計算し、要約まで一致した。研究ワークスペースで以下を実行した。 [第58版の監査](../runs/plan-completion-v58-fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 PYTHONDONTWRITEBYTECODE=1 \
  ../../.venv/bin/python tools/audit_plan_completion.py \
  plan-completion-v58-fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 次の比較

今回は開口0.15 cm²、肺圧7.2 cmH₂O、固定 /i/、鼻端の観測点2,310 Hzで測った。次は同じ肺圧の開口0.30 cm²の保存収録に、第1〜22倍音と第23〜44倍音の補正を順に適用する。周波数を固定し、上位倍音の流量誤差、ポートの2,310 Hz損失、実測上位倍音の追加で得た鼻端改善量を比較する。 [0.30 cm²の収録](fixed-vowel-i-velum-port-selected-pair-feedback.md)・[低域補正の計算](../tools/measure_fixed_vowel_i_velum_port_loss_feedback.py#L86)
