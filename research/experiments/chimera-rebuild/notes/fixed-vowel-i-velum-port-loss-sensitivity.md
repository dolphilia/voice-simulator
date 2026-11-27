# 口蓋帆ポートの倍音が2,310 Hzの鼻端誤差に与える影響

前回はポート流量の絶対差が大きい770 Hzと1,320 Hzを補正すると、両成分の流量誤差が95%以上減った。鼻端の残差は10.5%と11.7%減った。今回は補正前の同じ基準を使い、鼻端の複素残差を減らす方向への寄与で倍音を選ぶ。7.2 cmH₂Oの再実装版から上位2成分を決め、5.76 cmH₂Oでもその周波数を用いる。 [前回の比較](fixed-vowel-i-velum-port-loss-feedback.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-port-loss-sensitivity.json)

固定上流の `HumanVoice::render` から `AirwayNetwork::step` に進むと、枝は前標本の節点圧と運動量を受け、流向で係数が切り替わる二次方程式を解く。口蓋帆ポートでは咽頭末端から鼻腔入口への枝を使い、開口0.30 cm²を固定する。この場合、枝の式は `I fs(U[n]−U[n−1]) + R U[n] + K(U[n])U[n]|U[n]| = Δp[n−1]`。流量は cm³/s、圧力は dyn/cm²。枝が更新した流入量で節点圧と鼻端のR–L終端を更新する。鼻端の体積流量は放射の和を時間微分する前に得る。上流の短い狭窄の試験は定常流量をベルヌーイ近似に、別の固定管試験は共鳴と帯域幅を線形応答に照合する。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[鼻端放射の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

96 kHzの400〜500 msの窓で、予測したポート波形を `U₀[n]=Ū+Σ 2 Re(cₖ exp(iωₖ n/fs))` と置く。流向別の損失 `N(U)=K(U)U|U|` の微分は `N'(U)=2K(U)|U|`。流量係数の実部・虚部による波形の微分はそれぞれ `2 cos(ωₖ n/fs)`、`−2 sin(ωₖ n/fs)`。これらに `N'(U₀)` を掛け、2,310 Hzを複素投影すると損失の微分を得る。0.001 cm³/sの中央差分を独立参照にする。さらに微分に観測と予測の係数差を掛け、有限の差し替えで実際に損失を再計算した変化と照合する。

ポート以外の60枝の損失源を前回の基準に固定し、ポート損失から鼻端伝達への複素ゲインを粘性節点解で求める。各変化を観測鼻端伝達と予測の複素差の方向へ射影し、7.2 cmH₂Oの再実装版で上位2成分を固定する。個別差し替えによる二次損失の複素変化には10%のL2相対誤差、選んだ2成分には鼻端誤差の25%以上の低下と前回の2成分を上回ることを事前基準とした。 [圧力源と節点解](fixed-vowel-i-velum-port-loss-feedback.md)

## 実測

第1〜22倍音を個別に実測値へ置き換えたときの二次損失変化は、微分の予測と7.2 cmH₂OでL2相対誤差7.37%、5.76 cmH₂Oで2.05%だった。両版で10%基準を通過した。実部・虚部の微分と中央差分の最大相対差は1.01×10⁻⁸。前回の基準、係数と平均の保持、FFT、鼻端の枝源の重ね合わせは最大相対差7.23×10⁻¹¹で一致した。両版の照合も許容差10⁻⁸以内だった。 [複素係数、微分、判定](../runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-repeat/summary.json)

| 口蓋帆ポートで実測値に差し替える範囲 | 7.2 cmH₂Oの鼻端誤差 | 5.76 cmH₂Oの鼻端誤差 |
| --- | ---: | ---: |
| 基準の22倍音を予測 | 0.06559% | 0.04417% |
| 2,420 Hzのみ | 0.05159% | 0.03993% |
| 前回の770 Hzと1,320 Hz | 0.05840% | 0.03887% |
| 7.2 cmH₂Oで選んだ110 Hzと2,420 Hz | 0.05831% | 0.05665% |
| 第1〜22倍音 | 0.03580% | 0.04101% |
| 全帯域と平均 | 0.03734% | 0.01966% |

単独差し替えで最も鼻端誤差が減ったのは両肺圧で2,420 Hz。流量係数の誤差は0.00188と0.00133 cm³/s、鼻端誤差の減少率は21.34%と9.59%だった。事後計算では、基準波形での損失の傾き `s[n]=N'(U₀[n])` の周波数成分を `S`、差し替える流量係数差を `δc` とすると、2,310 Hzへの効果は `S(2310−f)δc + S(2310+f)conj(δc)`。保存した実部・虚部の微分を `Jᵣ,Jᵢ` とすると両係数は `(Jᵣ−iJᵢ)/2` と `(Jᵣ+iJᵢ)/2` で取り出せる。2,420 Hzでは差の項（−110 Hz）の絶対値が和の項（4,730 Hz）の473倍と844倍だった。 [各倍音の差し替えと微分](../runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-repeat/summary.json)

射影順位で選んだ110 Hzと2,420 Hzは7.2 cmH₂Oで鼻端誤差を11.09%減らし、5.76 cmH₂Oでは28.27%増やした。25%基準は両肺圧で不成立。7.2 cmH₂Oで110 Hzだけを差し替えた変化は、補正前の複素残差の大きさを1とすると改善方向に0.430、直交方向に0.742だった。5.76 cmH₂Oでは改善方向の成分が−0.145、直交方向が0.550だった。2成分を同時に変えた結果と個別の変化の和との差は補正前の残差に対して0.030%未満だった。この組では、改善方向への射影による順位付けで見落とした直交成分と肺圧による向きの変化が、最終誤差の大きさを左右した。 [鼻端の複素流量比](../runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-repeat/summary.json)

## 次の比較

各2成分の微分による複素変化の和から補正後の残差の絶対値を求め、7.2 cmH₂Oで最小の組を選ぶ。その組の有限差し替えを別肺圧でも測り、2,420 Hz単独と今回の射影順位の組を対照にする。今回分かったのは固定 /i/ と2肺圧での実測差し替えの効果で、別の開口形状への一般化と予測値だけでの補正は次の検証課題とする。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。初回の起動は先行実行の参照検査で停止し、`保存実行が登録値と一致しません` と表示された。先行実行が鼻端仮説の不成立を保存した実行だったため、参照を固定コミットとSHA-256、および指定した1判定だけの不成立で検証する形に修正した。修正後の研究ワークスペースと `/tmp` の実行は、各44判定中43件が通り、2成分の選択基準だけが偽で終了コード1となった。両要約はバイト単位で一致し、固定上流の `airway_adversarial` は6試験すべてに通った。 [初回マニフェスト](../runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-repeat/manifest.json)

研究ワークスペースで以下を実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_port_loss_sensitivity.py fixed-vowel-i-velum-port-loss-sensitivity-20261124-repeat
```

第52版の全体監査は2成分の選択基準の不成立も復元し、256実行・3,876成果の527判定に通過した。今回の3実行の1,556入力と12出力をSHA-256で照合した。RTL9210B-CGの追加出力は重複統合後に8ファイル分、13,649バイトだった。 [第52版の実行記録](../runs/plan-completion-v52-fixed-vowel-i-velum-port-loss-sensitivity-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v52-fixed-vowel-i-velum-port-loss-sensitivity-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
