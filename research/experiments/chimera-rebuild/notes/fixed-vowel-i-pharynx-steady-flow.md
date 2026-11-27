# 声門の平均流量から声門上の定常分流を求める

前回の離散節点解は、観測した各枝の平均流量で接線抵抗を計算し、咽頭の10周波数と逆流を再現した。今回は枝ごとの平均を定常解に置き換える。入口の声門流量は両肺圧の観測値を使う。事前基準は、61枝の平均流量のL2相対誤差5%以内、各出口の相対誤差10%以内、咽頭の複素流量のL2相対誤差1%以内とし、逆流枝の全検出および符号不一致1%以下も確認する。 [前回の測定](fixed-vowel-i-pharynx-from-glottal-flow.md#実測)・[事前登録](../cases/fixed-vowel-i-pharynx-steady-flow.json)

固定上流の `HumanVoice::render` は各内部標本で声門開口を渡し、`AirwayNetwork::step` が枝流量・壁・節点圧・放射を更新する。固定形状の定常極限では慣性項が消え、枝を向き付き流量 `U` として `Pₐ−Pᵦ = R U + K(U)U|U|` を満たす。口端と鼻端の放射は並列R–Lなので、定常ではインダクタの圧力が0になり、両端のゲージ圧を0に置く。梨状窩と上顎洞は行き止まりで定常流量を0とする。圧力は dyn/cm²、流量は cm³/s。上流の定常狭窄試験は、全セルと1/4セルの狭窄の流量をベルヌーイ近似と照合している。 [声門と気道の逐次更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L954)・[口端・鼻端と側枝](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L151)・[放射の状態更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

声門枝を切ったときの声門上の木を使い、観測声門流量の平均を咽頭入口で注入する。口端への分流と鼻端への分流の和を入口流量とし、2経路の圧力損失差が0になる分流を求める。共有枝は経路差で相殺される。独立に、全自由節点の圧力を未知数として各枝の単調な圧力式を逆に解き、流量保存から同じ分流を求める。

400〜500 msでは二次損失の時間平均と平均流量に二次式を適用した値に差が出うる。比較用には観測した二次損失の時間平均、枝慣性の窓端差、前標本に対応する口端・鼻端の平均圧を圧力条件に入れて分流を解き、定常解の差がどこから生じるかを調べる。 [枝の有限窓の収支](fixed-vowel-i-velum-supraglottal-loss.md)

## 実測

400〜500 msの声門平均流量134.138、109.501 cm³/sを入口に入れた。口端と鼻端への2経路から求めた定常流量は、各自由節点の圧力を解いた方法と両版で相対10⁻⁸以内で一致した。自由節点での流量保存残差は入口流量を基準に3.46×10⁻¹²以下だった。 [定常解と比較の実装](../tools/measure_fixed_vowel_i_pharynx_steady_flow.py)

| 肺圧 | 実測の口端・鼻端流量（cm³/s） | 定常解の口端・鼻端流量（cm³/s） | 全61枝のL2相対誤差 |
| --- | ---: | ---: | ---: |
| 7.2 cmH₂O | 102.145、31.992 | 99.066、35.072 | 2.71% |
| 5.76 cmH₂O | 82.793、26.708 | 80.802、28.699 | 2.15% |

鼻端流量は実測より9.63%と7.45%多く、両肺圧で事前の10%以内だった。咽頭の共有枝を相殺した口側と鼻側の経路について、二次損失の時間平均と平均流量を二次式に入れた値の差を集計すると、口側から鼻側を引いた値は−16.24、−10.32 dyn/cm²だった。窓端の慣性項は約7.6×10⁻⁷と6.5×10⁻⁷ dyn/cm²、測定窓の口端・鼻端の平均圧の絶対値は最大2.39×10⁻⁸ dyn/cm²。観測損失の時間平均と窓端項・終端平均圧を使う対照では、枝平均は実測に相対1.12×10⁻¹⁰以内で一致した。 [平均流量と圧力収支](../runs/fixed-vowel-i-pharynx-steady-flow-20261124-repeat/summary.json)

定常解を10周波数の計算に使うと、咽頭17枝×10周波数の複素流量の相対誤差は0.1736%と0.1328%だった。実測の枝平均を使った前回の値は0.1834%と0.1386%。逆流枝は5/5本と4/4本を検出し、過検出は0本、符号不一致は212と69標本だった。両版の測定で、定常分流と10周波数・逆流の事前基準を満たした。

鼻端の分流には二次損失の時間平均による偏りが残る。次は声門流量から予測した10周波数で各枝の流量波形を再構成し、流向別の二次損失を平均した圧力補正で定常分流がどこまで改善するか測る。観測した枝の二次損失の平均を使う診断を比較基準にする。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。既存の通常CLIと固定上流の収録を参照し、研究ワークスペースと `/tmp` の各実行で20判定が通り、要約がバイト単位で一致した。固定上流の定常狭窄試験にも通過した。再計測では末尾の実行IDを変更する。 [初回マニフェスト](../runs/fixed-vowel-i-pharynx-steady-flow-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-pharynx-steady-flow-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_pharynx_steady_flow.py fixed-vowel-i-pharynx-steady-flow-20261124-repeat
```

第46版の全体監査は238実行・3,804成果・491判定を通過した。今回の3実行の1,460入力と12出力をSHA-256で照合した。観測時系列はRTL9210B-CGの既存データを参照し、追加出力は重複統合後に8ファイル、計13,106バイトだった。 [第46版の実行記録](../runs/plan-completion-v46-fixed-vowel-i-pharynx-steady-flow-20261124/manifest.json)
