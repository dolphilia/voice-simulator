# 口蓋帆ポートの上位倍音と他枝の圧力源を独立に切り替える

## 上流の読解

- `HumanVoice::render` は肺圧と呼気の状態を更新し、声門前後の圧力差で開口を進めてから `AirwayNetwork::step` を呼ぶ。鼻端と声門は同じ内部レートの収録を比較する。形状は `HumanAirway` が咽頭と口腔の継ぎ目から口蓋帆ポートを鼻腔入口へ接続した固定 /i/ を使う。 [human_voice.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[human_airway.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L155)
- `AirwayNetwork::step` では枝の流量を前の節点圧力差と枝の運動量から求め、流向ごとの二次損失 `K(U)U|U|` を課す。その後、節点に流量を集めて圧力と並列R–Lの鼻端放射を更新する。観測した枝流量と圧力差から、粘性と慣性を引いた値が二次損失になる。圧力は dyn/cm²、体積流量は cm³/s。 [損失係数と枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[鼻端の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)
- `AirwayNetwork::linear_elements` は固定形状から枝の粘性抵抗とイナータンスを取り出す。上流の `transfer_function` は連続周波数の木構造で伝達を計算する。今回の研究用節点解は、時間更新と符号をそろえるため、1サンプル遅れ `d = exp(−2πif/fₛ)` と枝の `Z = R + Ifₛ(1−d)` を使う。観測圧力源では `(Ifₛ(U末−U前) + Δp末−Δp前) / N` を足して、時間差分と遅れの窓端を扱う。録音した声門流量を注入し、鼻端の流量をそれで割った複素伝達を観測する。 [linear_elements](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1199)・[transfer_function](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L24)・[圧力源と窓端](../tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py#L109)
- 上流の狭窄試験は固定圧力での流量をベルヌーイ流量に照合する。フォルマント帯域幅の試験は形状を固定した管のインパルスと線形周波数応答を比較する。今回の複素圧力源の重ね合わせは、同じ収録の枝方程式、FFT、複数右辺の直接解、転置行列から求める鼻端の読み出しを使い照合する。 [狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[帯域幅試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L128)

## 実装前の予測

先行する0.30 cm²の比較では、他60枝を予測した場合に、収録から抽出した上位倍音をポートへ加えると鼻端誤差が0.03379%から0.03857%へ増えた。収録の圧力源を全枝に使った先行比較で鼻端伝達が再現できていたため、他60枝を収録由来にすると、同じ上位倍音の追加で誤差が減ると予測した。相対誤差の差が `1e-8` を超えて符号が逆転するかを両版で判定する。 [0.30 cm²の上位倍音](fixed-vowel-i-velum-wide-port-upper-harmonics.md#実測)・[全枝の圧力源の照合](fixed-vowel-i-velum-supraglottal-loss.md)・[事前登録](../cases/fixed-vowel-i-velum-wide-port-nose-source-swap.json)

固定 /i/、肺圧7.2 cmH₂O、ポート開口0.30 cm²で、内部96 kHzのサンプル `[38400, 48000)` を使う。ポートの平均と補正済み第1〜22倍音を固定し、収録の第23〜44倍音を加える前後で二次損失の2,310 Hz係数を求める。他60枝の圧力源は、10周波数で予測した二次損失か、収録した全帯域の二次損失と窓端補正の和を選ぶ。合計4条件に同じ線形要素と声門流量を使うため、ポートの切り替えによる複素伝達の変化は両方で等しい。鼻端で観測した伝達を基準とする相対二乗誤差では、他枝の差を `B`、ポートの追加の差を `D` とすると、両者の組み合わせは `2 Re(conj(B) D)` で現れる。ここでは `B` と `D` を鼻端の観測伝達で正規化する。
