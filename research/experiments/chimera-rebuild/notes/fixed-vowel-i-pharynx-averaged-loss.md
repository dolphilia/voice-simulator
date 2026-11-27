# 予測した10周波数で二次損失の時間平均を求める

前回の定常解では、7.2と5.76 cmH₂Oの鼻端平均流量を9.63%と7.45%多く見積もった。観測した二次損失の平均を入れるとこの差は消えた。今回は声門入口の平均・10周波数と固定形状から予測した枝流量だけを使い、分流誤差が半分以下になるかを調べる。 [前回の定常分流](fixed-vowel-i-pharynx-steady-flow.md#実測)・[事前登録](../cases/fixed-vowel-i-pharynx-averaged-loss.json)

固定上流の `HumanVoice::render` は各内部標本で声門開口を更新し、`AirwayNetwork::step` は枝の実効面積、慣性・粘性抵抗、流向別の二次損失係数を使って、その標本の枝流量を求める。通常枝の二次圧力項は `K(U)U|U|` で、向きに応じて `K₊` または `K₋` を使う。口端・鼻端の放射は並列R–Lとして処理する。定常狭窄試験は、一様管中のセル全体と1/4セルを占める狭窄の流量をベルヌーイ近似と照合する。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝損失と流向](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L954)・[並列R–Lの放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

時間平均流量を `μ`、予測した10周波数の変動の和を `u′`、試行中の波形を `U=μ+u′` と置く。圧力損失の時間平均は `K₊(μ²+〈u′²〉)−(K₊+K₋)〈U²·1[U<0]〉` で、単位は dyn/cm²。各枝で複素流量係数 `aₖ` の正の周波数だけを用い、`〈u′²〉=2Σ|aₖ|²` を直接構成した波形と照合する。分流を求めている間は前回方式の定常平均で求めた `u′` を保ち、試行ごとに `μ` と逆流区間を更新する。分流の確定後、補正後の平均で10周波数を計算し直す。 [先行する離散節点解](fixed-vowel-i-pharynx-from-glottal-flow.md)

## 実測

両肺圧で、周波数から計算した分散と再構成波形の二乗平均が相対10⁻⁹以内で一致した。符号付き損失の直接平均と、分散・逆流項への展開も同じ許容差を満たした。補正した分流は、入口流量の保存と口端・鼻端に向かう経路の同じ平均圧力差を満たした。 [平均損失の計算](../tools/measure_fixed_vowel_i_pharynx_averaged_loss.py)・[全判定と各枝の値](../runs/fixed-vowel-i-pharynx-averaged-loss-20261124-repeat/summary.json)

| 肺圧 | 鼻端平均流量の観測値（cm³/s） | 定常解の鼻端誤差 | 平均二乗で補正した鼻端誤差 | 流向別に平均した鼻端誤差 |
| --- | ---: | ---: | ---: | ---: |
| 7.2 cmH₂O | 31.9923 | 9.6267% | 2.5039% | 0.1565% |
| 5.76 cmH₂O | 26.7079 | 7.4536% | 1.7128% | 0.0843% |

流向別の平均を使った鼻端の予測値は31.9422、26.6854 cm³/s。定常解からの鼻端誤差の減少率は98.37%と98.87%だった。全61枝の平均流量のL2相対誤差は2.711%から0.0441%、2.150%から0.0243%に下がり、両版が事前の50%改善基準を満たした。

口側と鼻側の経路に生じた損失の差を、観測した平均補正と比べた。7.2 cmH₂Oでは、予測から得た分散の項は−20.446 dyn/cm²、流向の切り替えは+3.944 dyn/cm²で、合計−16.503 dyn/cm²になった。観測値は−16.239 dyn/cm²だった。5.76 cmH₂Oでは−12.690と+2.250 dyn/cm²の合計が−10.440 dyn/cm²になり、観測値−10.323 dyn/cm²に近かった。両肺圧で流向の項が分散項の一部を相殺することが、平均二乗だけの条件との差になった。

補正後の咽頭の10周波数のL2相対誤差は0.1835%と0.1387%、符号不一致は215と69標本だった。5枝と4枝の逆流をすべて検出し、過検出は0枝。両版で倍音・逆流に関する事前基準を満たした。今回の評価対象は固定 /i/ の2肺圧における分流と枝流量。次は同じ予測波形に二次損失式を適用して2,310 Hzの圧力源を求め、鼻端の複素放射の観測に照合する。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。既存の通常CLIと固定上流の収録を参照し、研究ワークスペースと `/tmp` から各20判定に通過した。2回の要約はバイト単位で一致し、上流の定常狭窄試験にも通過した。再計測時は末尾の実行IDを変更する。 [初回マニフェスト](../runs/fixed-vowel-i-pharynx-averaged-loss-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-pharynx-averaged-loss-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_pharynx_averaged_loss.py fixed-vowel-i-pharynx-averaged-loss-20261124-repeat
```

第47版の全体監査は241実行・3,816成果・497判定を通過した。今回の3実行の1,474入力と12出力をSHA-256で照合した。RTL9210B-CGの収録を参照し、外部SSDに追加した出力は重複統合後に8ファイル、計13,142バイトだった。 [第47版の実行記録](../runs/plan-completion-v47-fixed-vowel-i-pharynx-averaged-loss-20261124/manifest.json)
