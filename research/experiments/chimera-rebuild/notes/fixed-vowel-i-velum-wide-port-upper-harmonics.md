# 口蓋帆ポートを0.30 cm²に広げて第23〜44倍音を比較する

## 上流の読解

- `HumanVoice::render` は肺圧の補間と呼気流の状態を更新し、声門前後の圧力差から声門面積を更新して声道網を1サンプル進める。0.30 cm²と0.15 cm²では同じ肺圧を与えても、それぞれの声道で結合した声門流量が入力になる。比較には出力の間引きや振幅制御前に取得した声門枝流量と鼻端の体積流量を使う。 [human_voice.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)
- `HumanAirway` は咽頭と口腔の継ぎ目から鼻腔入口にポートを張る。上流の `AirwayNetwork::step` はポート面積から粘性抵抗、イナータンス、順流・逆流別の収縮と膨張の係数を計算する。このスリット幅がゼロのポートでは粘性抵抗は面積の `−3/2` 乗に比例し、入口の二次損失係数は面積の `−2` 乗に比例する。出口側の係数も下流節点面積との比で変わる。 [human_airway.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L155)・[network.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1003)
- 各枝で直前の節点圧力と枝運動量から当該サンプルの流量を解き、枝流量を足し引きした節点で圧力を更新する。鼻端の並列R–L負荷では更新前と更新後の圧力で負荷流量を求める。研究側では固定形状の `Z=R+Ifₛ(1−exp(−2πif/fₛ))` とこの放射負荷を節点方程式に使う。観測窓の両端の圧力差と枝の運動量差は観測圧力源対照に含める。流量は cm³/s、圧力は dyn/cm²、周波数は Hz。 [枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)・[放射負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[観測窓の補正](../tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py#L109)
- `steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss` は狭窄長が1区間と1/4区間の場合の定常流をベルヌーイ流量と比較する。有限窓での倍音混合は、実測係数、FFT、元の粘性節点解、ポート源の重ね合わせで別途照合する。 [狭窄の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

## 実装前の予測

0.15 cm²では上位の予測補正で流量係数のL2誤差が95.84%減り、鼻端では実測上位倍音を加えた場合の改善量の100.09%を回復した。0.30 cm²でも二次損失を一度戻すと、上位の流量係数の誤差が接線解から50%以上減り、鼻端で実測上位追加による改善量の80%以上を回復すると予測した。鼻端の絶対誤差は複素残差の向きにも依存するため、同じ平均と低域を使った場合の実測上位追加と予測追加の複素伝達差も測る。 [0.15 cm²の比較](fixed-vowel-i-velum-narrow-port-upper-harmonics.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-wide-port-upper-harmonics.json)

同じ固定 /i/、肺圧7.2 cmH₂O、内部96 kHzでサンプル `[38400, 48000)` を測る。まず平均流量の周りで符号付きの二次損失 `K(U)U|U|` を接線近似し、第1〜22倍音を予測する。同じ波形上の二次損失のうち接線に含まれる寄与を引き、各周波数の節点解へ一度戻す。次の第23〜44倍音の補正では、ポートにだけこの補正済み低域を使う。鼻端の2,310 Hzでは、ポートの平均、補正済み低域、他60枝の基準圧力源を全条件で固定する。

## 実測

再実装・固定上流の内部収録のケース定義を照合し、音響ポート面積の上書きだけが異なることを確認した。0.30 cm²のポートの第1〜22倍音で二次損失を補正すると、流量係数のL2相対誤差は1.539%から0.04356%に、2,310 Hzの鼻端複素相対誤差は0.06559%から0.03379%になった。以下はその低域を固定した比較で、両版が丸め精度内で一致した。 [比較コード](../tools/measure_fixed_vowel_i_velum_wide_port_upper_harmonics.py)・[保存要約](../runs/fixed-vowel-i-velum-wide-port-upper-harmonics-20261124-repeat/summary.json)

| ポートに加える第23〜44倍音 | 流量係数の相対L2誤差 | 2,310 Hzの鼻端複素相対誤差 |
| --- | ---: | ---: |
| 追加なし | 100% | 0.0337936% |
| 接線解 | 2.92644% | 0.0357811% |
| 予測損失を一度戻す | 0.0258068% | 0.0385661% |
| 観測損失を一度戻す | 0.00001161% | 0.0385721% |
| 収録から抽出した係数 | 0% | 0.0385721% |

上位倍音の流量誤差は99.12%減り、50%の事前基準を満たした。収録から抽出した係数を使う対照でも鼻端誤差が14.14%増えたため、80%回復の仮説は両版で不成立とし、回復率は欠測にした。予測した係数を足した鼻端伝達と収録係数を足した場合との差は相対1.25×10⁻⁷で、収録係数の追加に伴う鼻端伝達変化の0.01935%だった。観測損失対照と収録係数を加えた鼻端伝達との差は相対5.79×10⁻¹¹だった。FFT、粘性節点解、重ね合わせを含む計算照合の最大相対差は1.28×10⁻¹¹だった。

### 鼻端誤差の増加を複素伝達から調べる

保存要約の複素伝達を事後に分解した。低域だけの伝達と全収録の鼻端伝達の差を後者で割った値を `E`、上位倍音の追加による伝達の変化を同じ値で割ったものを `Δ` とする。鼻端の二乗誤差の変化は `2 Re(conj(E) Δ) + |Δ|²` になる。0.30 cm²では2項が −3.798×10⁻⁷ と +4.144×10⁻⁷ で、差し引き +3.458×10⁻⁸。0.15 cm²では −2.820×10⁻⁶ と +1.499×10⁻⁶ で、差し引き −1.321×10⁻⁶ だった。上位倍音を加えると両開口で元の誤差の向きの成分が減った。0.30 cm²では伝達変化の大きさによる二乗項が、その減少分を上回った。 [0.15 cm²の保存要約](../runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-repeat/summary.json)

## 再現手順

初回は研究ワークスペース、再実行は `/tmp` から起動した。macOS 15.6.1 ARM64、Python 3.14.4、NumPy 2.4.4、rustc 1.94.1を使用した。固定上流の `cargo test --locked --offline -p chimera --test airway_adversarial` は6件通過した。両実行の310判定のうち、鼻端の80%回復だけが不成立で要約はバイト単位で一致した。 [初回のマニフェスト](../runs/fixed-vowel-i-velum-wide-port-upper-harmonics-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-velum-wide-port-upper-harmonics-20261124-repeat/manifest.json)・[試験ログ](../runs/fixed-vowel-i-velum-wide-port-upper-harmonics-20261124-repeat/artifacts/upstream-airway-adversarial.log)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 PYTHONDONTWRITEBYTECODE=1 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_wide_port_upper_harmonics.py \
  fixed-vowel-i-velum-wide-port-upper-harmonics-check
```

第59版の監査に、310判定と鼻端改善の不成立を復元する比較を追加した。 [全体監査](../runs/plan-completion-v59-fixed-vowel-i-velum-wide-port-upper-harmonics-20261124/manifest.json)

## 次の比較

0.30 cm²の同じ収録で、ポートの上位倍音の有無と、他60枝の2,310 Hz圧力源の予測・観測を独立に切り替える。ポートの平均と補正済み低域を固定し、4条件で鼻端の複素残差と上式の2項を比べる。他枝の残差が加わったときに上位倍音の効果がどちらへ向くかを確認できる。 [鼻端の圧力源の切り替え](../tools/measure_fixed_vowel_i_velum_narrow_port_upper_harmonics.py#L38)・[観測圧力源](../tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py#L109)
