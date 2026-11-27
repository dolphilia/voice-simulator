# 平均流量で口蓋帆ポートの二次損失を線形化する

前回、ポートだけを開いた固定 /i/ の2,310 Hzで、離散線形モデルと通常発声の総放射複素比に1.90%の相対差があった。残差方向への射影は鼻端が82.74%を占めた。今回は400〜500 msの平均ポート流量を動作点に、同じ輪郭と同じ音響ポートを使って開口枝の抵抗だけを補正する。 [前回の2,310 Hzの観測](fixed-vowel-i-velum-harmonic-transfer.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-mean-flow-tangent.json)

固定上流の `HumanVoice::render` は声門開口と肺圧を更新して、`AirwayNetwork::step` に渡す。気道モデルは、咽頭末端から鼻腔入口に向かう流量を正に置く。ポートの二次損失の係数 `K` は、面積による入口損失と、下流断面への拡大損失の和。逆流すると下流として咽頭側を使う。前標本の両端圧と枝の運動量を駆動項とし、当該標本の流量 `u` について `L Δu/Δt + R u + K u|u|` を解く。 `u` は cm³/s、`K u|u|` は dyn/cm²。枝を解いてから節点圧と放射を更新する。上流の狭窄試験は同じ二次損失を含む定常圧力差をベルヌーイ型の式と照合している。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流のポートと枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L990)・[上流の定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[研究版の更新式](../crates/vocal-core/src/airway/network.rs#L145)

平均流量 `ū` のまわりでは、`K u|u|` の傾きは `2K|ū|` で、これを元の枝の抵抗に加える。観測した二次損失を使う対照では、離散の枝インピーダンスを `Z = R + Ls` とし、二次圧力損失の複素係数 `N` による枝流量の補正 `−N/Z` を節点方程式へ入れる。咽頭側と鼻腔側に大きさが等しく符号の反対の注入として表現できる。この対照は実測したポート流量を使うため、残差を調べるための計算になる。 [離散応答の導出](fixed-vowel-i-velum-harmonic-transfer.md)

## 実測

固定 /i/ の閉条件と同じ輪郭でポート面積だけを0.30 cm²にした。400〜500 msの9,600内部標本で、平均流量は31.992 cm³/s、RMSは69.908 cm³/s、順方向は5,216標本、逆方向は4,384標本だった。流向別の `K` は順方向0.00586489、逆方向0.00658788。平均まわりの接線抵抗は元の0.465861に0.375263 dyn·s/cm⁵を加える。前標本と窓端の補正を含めた圧力収支の相対残差は、研究版と固定上流の両方で9.44×10⁻¹⁴以下だった。

通常発声で観測した各放射流量の2,310 Hz複素係数を、同じ窓の声門流量の係数で割った値を基準にした。表の振幅差と位相差は、各計算値の基準に対する比から求めた。複素相対誤差は複素数の差の絶対値を基準の絶対値で割った値。

| ポートの損失 | 鼻端の複素相対誤差 | 鼻端の振幅差 | 鼻端の位相差 | 総放射の複素相対誤差 |
| --- | ---: | ---: | ---: | ---: |
| ゼロ流量で線形化 | 1.030% | +0.0682 dB | +0.378° | 1.902% |
| 平均流量で線形化 | 0.430% | +0.0161 dB | +0.222° | 0.882% |
| 観測した損失の複素係数を再投入 | 0.268% | +0.0050 dB | −0.150° | 0.335% |

鼻端の複素誤差は58.28%減り、事前登録の10%を満たした。抵抗を直接変えた解と、追加圧力の流量への帰還を含む独立計算は、登録した相対許容差10⁻⁹以内で一致した。固定上流でも丸めの範囲で同じ値を得た。前回の「通常発声と微小信号の総放射複素比の差が3%以上」という仮説は不成立のまま保存した。 [今回の判定と観測値](../runs/fixed-vowel-i-velum-mean-flow-tangent-20261124-repeat/summary.json)・[前回の判定](../runs/fixed-vowel-i-velum-harmonic-transfer-20261124-repeat/summary.json)

接線抵抗を観測流量に掛けた2,310 Hzの圧力係数は `−0.00846 + 0.02596i` dyn/cm²、流向別係数で計算した二次損失は `−0.03464 + 0.03417i` dyn/cm²だった。平均が正でも窓の45.67%が逆流しており、平均付近だけで決まる傾きでは二次損失の振幅と位相に差が残る。観測した損失を再投入した計算は、その流量を入力とする診断で、単独の予測精度は評価していない。観測した損失を戻しても残る鼻端の0.268%について、次は口腔・鼻腔の固定枝の二次損失を同じ窓で求め、窓端項を含めた圧力収支と鼻端の複素差への寄与を照合する。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースからの初回と `/tmp` から絶対パスで呼んだ再実行で、測定結果と6点のCLI出力が一致した。通常CLIの `render`、`render-pcm --no-trace 128`、`inspect`、`transfer` を使用し、固定上流の通常発声は前回保存した時系列を読んだ。固定上流の `steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss` は再実行して通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-mean-flow-tangent-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-mean-flow-tangent-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_mean_flow_tangent.py fixed-vowel-i-velum-mean-flow-tangent-20261124-repeat
```

再計測時は末尾の実行IDを新しい値にする。波形、WAV、CLIと上流試験のログの実体は作業用外部SSDのRTL9210B-CGにある。 [再実行の成果物](../runs/fixed-vowel-i-velum-mean-flow-tangent-20261124-repeat/artifacts/)

全体監査の第38版は212実行・3,643成果・439判定を通過した。今回の3実行の1,529入力と24出力をSHA-256で照合し、外部SSDの21出力パスは、同じ内容をハードリンクでまとめて14ファイル、計21,178,507バイトになった。 [第38版の監査結果](../runs/plan-completion-v38-fixed-vowel-i-velum-mean-flow-tangent-20261124/summary.json)
