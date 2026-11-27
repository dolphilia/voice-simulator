# 鼻端の複素誤差で口蓋帆ポートの2倍音を選ぶ

前回の射影順位は鼻端残差を減らす成分の大きさを使った。110 Hzは残差に直交する変化も大きく、7.2 cmH₂Oで選んだ110 Hzと2,420 Hzの組は、5.76 cmH₂Oで誤差が増えた。今回は第1〜22倍音の231組から、7.2 cmH₂Oの再実装版で微分が予測する補正後の複素誤差が最小の組を一度だけ選ぶ。有限差し替えで最良の組に5ポイント以内で近づき、同じ選択が両肺圧で25%以上改善すると事前登録した。 [前回の計測](fixed-vowel-i-velum-port-loss-sensitivity.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-port-complex-pair.json)

上流の `HumanVoice::render` は各内部標本で肺圧と声門の開口を更新し、`AirwayNetwork::step` に進む。固定した口蓋帆ポートの枝では `I fs(U[n]−U[n−1]) + R U[n] + K(U[n])U[n]|U[n]| = Δp[n−1]`。流量は cm³/s、圧力と損失は dyn/cm²で、`K` は収縮と下流セルへの拡大の係数を含む。上流は流向別の根で現在流量を求めて運動量を保存し、節点と鼻端の並列R–L負荷を更新する。鼻端の観測点は放射流量の和を時間差分する前。狭窄の定常試験はベルヌーイ近似と、共鳴試験は固定管のFDTDと線形周波数解で照合する。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)・[鼻端の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

ポートの流量係数を実測側に動かしたときの線形化した2,310 Hz損失変化を `δNₖ`、ポート損失から鼻端への複素ゲインを `G`、補正前の観測値と予測値の差を `r` とする。`|r−G(δNᵢ+δNⱼ)|` を最小にする組を選ぶ。絶対値の二乗を展開すると `|r|²−2Re(G(δNᵢ+δNⱼ)conj(r))+|G(δNᵢ+δNⱼ)|²` で、改善方向への射影と変化全体の大きさをともに取り込める。 [微分と鼻端ゲイン](fixed-vowel-i-velum-port-loss-sensitivity.md)

有限差し替えでは400〜500 msの96 kHz系列を使い、2成分を同時に実測の複素係数へ置き換える。ポート平均、残り20成分、他60枝の圧力源を固定する。二次損失を時間領域で再計算し、その2,310 Hz成分の変化を粘性節点方程式に入れる。同じ変化を保存済みのゲインで求めた値と照合する。全231組の有限解は診断用に保存し、5.76 cmH₂Oでの組の再選択には使わない。

## 実測

| 口蓋帆ポートで実測値に差し替える範囲 | 7.2 cmH₂Oの鼻端誤差 | 5.76 cmH₂Oの鼻端誤差 |
| --- | ---: | ---: |
| 基準の22倍音を予測 | 0.06559% | 0.04417% |
| 複素残差で固定した1,320 Hzと2,420 Hz | 0.04509% | 0.03639% |
| その肺圧で有限差し替えが最良の組 | 0.04509% | 0.03630% |
| 2,420 Hz単独 | 0.05159% | 0.03993% |
| 前回の射影順位で選んだ110 Hzと2,420 Hz | 0.05831% | 0.05665% |

7.2 cmH₂Oの再実装版で、微分が最小の複素誤差を予測したのは1,320 Hzと2,420 Hzの組だった。改善率は予測31.30%、有限差し替え31.26%で、有限差し替えでも231組中の1位だった。5.76 cmH₂Oでも同じ組が予測17.62%、有限差し替え17.61%の改善を示し、231組中の3位だった。その肺圧で最良の550 Hzと1,320 Hzは17.80%の改善で、全231組で25%基準に届く組はなかった。固定した組は2,420 Hz単独と射影順位の組を両肺圧で上回り、25%の低下を求める仮説は5.76 cmH₂Oで不成立だった。 [231組の予測と有限差し替え](../runs/fixed-vowel-i-velum-port-complex-pair-20261124-repeat/summary.json)

固定した組の鼻端変化を補正前の複素残差で割ると、7.2 cmH₂Oで改善方向が0.313、直交方向が0.012だった。5.76 cmH₂Oではそれぞれ0.210と0.235になり、誤差の減少が小さかった。全231組で予測した改善率と有限差し替えの改善率との差の二乗平均平方根は1.14ポイントと0.30ポイント。最大差は110 Hzを含む組で4.11ポイントと2.03ポイントだった。 [鼻端変化の複素値と改善率](../runs/fixed-vowel-i-velum-port-complex-pair-20261124-repeat/summary.json)

保存した流量係数、ポート損失、鼻端ゲイン、2成分だけの差し替えと平均の保持、損失のFFT、節点の直接解を照合した。数値照合の最大相対差は1.50×10⁻¹³。再実装版と固定上流では、231組の鼻端誤差がL2相対許容差10⁻⁸以内で、微分と有限差し替えの最良組がそれぞれ一致した。

## 次の比較

1,320 Hzと2,420 Hzの接線解に、接線抵抗までで計上した圧力を引いた予測二次損失を一度戻す。声門の観測流量を入力に、ポート側の観測係数を使った有限差し替えで得られた改善率と比較する。今回の5.76 cmH₂Oでの17.80%は、固定開口・固定平均の下で、第1〜22倍音のうち2成分を実測値に差し替えた231組の最大値。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。通常CLIと固定上流の保存済み系列を参照した。研究ワークスペースと `/tmp` の各52判定のうち51件が通り、両肺圧で25%改善する判定だけが偽で終了コード1となった。両実行の要約はバイト単位で一致し、固定上流の `airway_adversarial` の6試験にも通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-port-complex-pair-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-port-complex-pair-20261124-repeat/manifest.json)

研究ワークスペースで以下を実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_port_complex_pair.py fixed-vowel-i-velum-port-complex-pair-20261124-repeat
```

第53版の全体監査は5.76 cmH₂Oで改善率の基準が不成立だったことも復元し、259実行・3,888成果の533判定に通過した。今回の3実行について1,568入力と12出力をSHA-256で照合した。既存の時系列を再利用し、RTL9210B-CG上の追加出力は重複統合後に8ファイル分、13,577バイトだった。 [第53版の実行記録](../runs/plan-completion-v53-fixed-vowel-i-velum-port-complex-pair-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v53-fixed-vowel-i-velum-port-complex-pair-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
