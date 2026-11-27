# 口蓋帆ポートに第7〜18倍音の流量を加える

前回の帯域対照で、選択外の周波数は2,310 Hzの損失残差の方向に118.1%と110.9%を占めた。今回は既存の第1〜6・第19〜22倍音の間にある第7〜18倍音だけを口蓋帆ポートに足す。2,310 Hzは基本周波数110 Hzの第21倍音で、新しい帯域には第7＋14、第8＋13など21になる組がある。流向で係数が変わるため、二乗の和・差周波数だけで損失の全成分は決まらない。追加前後の波形に同じ時間領域の損失式を適用する。 [前回の実測](fixed-vowel-i-velum-port-bandwidth.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-port-middle-harmonics.json)

固定上流では `HumanVoice::render` が肺圧と声門面積を更新し、`AirwayNetwork::step` が前標本の圧力差と運動量から現在の枝流量、節点圧、放射流量を順に求める。`HumanAirway::new` の口蓋帆ポートは咽頭末端30から鼻腔入口49へつながる。固定面積では `I fs(U[n]−U[n−1]) + R U[n] + K(U[n])U[n]|U[n]| = Δp[n−1]`。流量 `U` は cm³/s、圧力は dyn/cm²、慣性 `I` は g/cm⁴、抵抗 `R` は dyn·s/cm⁵。順逆の `K` は収縮と下流への拡大の和で、上流は符号に応じた二次方程式の根を取り、`I U[n]` を次標本へ保持する。鼻端の並列R–L負荷を通る体積流量を、和の差分・間引きより前で読む。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[係数と枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[放射の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)

`transfer_function` は指定した枝を切断し、体積流量源を注入したときの線形応答を周波数ごとに求める。上流試験は不均一な固定管のFDTDインパルス応答と共鳴周波数・帯域幅を照合する。本比較も声門を切り分けて観測声門流量を注入する。96 kHzの離散式で `d = exp(−2πif/fs)`、枝インピーダンスは `Z = R + I fs(1−d)`。10周波数の予測で得た枝平均 `U₀` から `ΔR = 2K(U₀)|U₀|` を固定し、追加した周波数の接線解だけを求める。元の粘性節点解へ各枝のアドミタンス差 `d/(Z+ΔR)−d/Z` を接続行列で加える独立計算に照合する。 [上流の周波数応答](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L24)・[周波数と帯域幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L128)

観測窓は400〜500 ms、両肺圧の波形とも9,600内部標本。実測対照は追加する12成分を窓内フーリエ係数から求める。予測と実測の10周波数へそれぞれ追加し、予測の10周波数に実測の追加分を足す場合も測る。どの条件も他の60枝の圧力源を固定する。各条件のポート損失の2,310 Hz成分を粘性節点解に戻して鼻端を読む。仮説は実測帯域の回復率50%以上、予測帯域の損失回復率50%以上かつ鼻端誤差を半減できること。

## 実測

| 流量の比較 | 7.2 cmH₂O | 5.76 cmH₂O |
| --- | ---: | ---: |
| 実測の10周波数へ実測の中間倍音を追加したときの損失回復率 | 91.96% | 83.87% |
| 予測の10周波数へ予測の中間倍音を追加したときの損失回復率 | 103.37% | 90.16% |
| 予測の10周波数へ実測の中間倍音を追加したときの損失回復率 | 107.27% | 92.56% |
| 予測した中間倍音の流量係数のL2相対誤差 | 10.00% | 7.31% |

損失回復率は各基準から全帯域の実測までの複素差に沿った射影。基準によって残差の向きと大きさが異なる。103.37%は残差方向に行き過ぎ、位相を含む損失の誤差は残った。予測の追加前後で複素圧力差の絶対値は0.01135から0.00317 dyn/cm²、0.00668から0.00178 dyn/cm²に減った。両方の仮説を両版・両肺圧で満たした。 [各条件の複素圧力と全判定](../runs/fixed-vowel-i-velum-port-middle-harmonics-20261124-repeat/summary.json)

| ポート流量の条件 | 7.2 cmH₂Oの鼻端誤差 | 5.76 cmH₂Oの鼻端誤差 | 逆流符号の不一致（7.2 / 5.76） |
| --- | ---: | ---: | ---: |
| 予測の10周波数 | 0.24693% | 0.20181% | 165 / 156 |
| 予測の10周波数 ＋ 予測の第7〜18倍音 | 0.06559% | 0.04417% | 68 / 69 |
| 予測の10周波数 ＋ 実測の第7〜18倍音 | 0.05752% | 0.03170% | 83 / 97 |
| 実測の10周波数 | 0.29574% | 0.22546% | 148 / 149 |
| 実測の10周波数 ＋ 実測の第7〜18倍音 | 0.03724% | 0.04031% | 7 / 4 |
| 全帯域の実測 | 0.03734% | 0.01966% | 0 / 0 |

予測の追加成分だけで鼻端誤差が73.44%と78.12%減った。予測波形に実測の追加成分を入れると鼻端誤差はさらに下がり、逆流符号の不一致は増えた。追加成分の最初の差はポートの複素流量係数にあり、絶対差の上位2周波数は両肺圧とも770 Hzと1,320 Hzだった。実測流量を第1〜22倍音に限定した対照では、5.76 cmH₂Oで全帯域の実測の約2倍の鼻端誤差が残った。 [追加した流量係数、圧力、鼻端の観測](../runs/fixed-vowel-i-velum-port-middle-harmonics-20261124-repeat/summary.json)

追加波形の逆FFT、枝抵抗の差だけを接続行列で足した接線解、平均と既存係数の保持、損失のFFT、鼻端の枝源の重ね合わせ、前回の基準を照合した。数値照合の最大相対差は4.32×10⁻¹³で、両版間の誤差も事前許容差10⁻⁸以内だった。

## 次の比較

770 Hzと1,320 Hzの接線解に、各枝で予測した符号付き二次損失から接線抵抗の寄与を除いた圧力源を一度だけ入れる。無補正、予測損失での補正、実測損失と窓端項を使う対照を、両肺圧・両版で照合する。比較は上位2成分のポート流量を先に見て、補正後の波形で2,310 Hzの損失と鼻端応答まで追う。ここで測った改善は固定 /i/ の2肺圧と固定開口に限る。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。入力の時系列は通常CLIと固定上流の保存済み収録を参照した。研究ワークスペースと `/tmp` から各40判定に通過し、要約はバイト単位で一致した。固定上流の `airway_adversarial` も6試験すべてに通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-port-middle-harmonics-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-port-middle-harmonics-20261124-repeat/manifest.json)

研究ワークスペースで以下のコマンドを実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_port_middle_harmonics.py fixed-vowel-i-velum-port-middle-harmonics-20261124-repeat
```

第50版の全体監査では250実行・3,852成果の515判定に通過した。今回の3実行で1,524入力と12出力のSHA-256を照合した。保存済みの生波形を再利用し、RTL9210B-CGの追加出力は重複統合後に8ファイル分、13,649バイトだった。 [第50版の実行記録](../runs/plan-completion-v50-fixed-vowel-i-velum-port-middle-harmonics-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v50-fixed-vowel-i-velum-port-middle-harmonics-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
