# 口蓋帆ポートの予測誤差を平均・選択周波数・帯域に分ける

前回、全61枝の予測波形から二次損失を求めたとき、鼻端の2,310 Hzの複素誤差に最も大きく寄与した枝は、両肺圧とも口蓋帆ポート30→49だった。今回はその波形を4通りに置き換え、平均流量、選んだ10周波数の複素係数、選択外の周波数の影響を1条件ずつ測る。帯域制限が、残差方向への射影の50%以上を占めると事前登録した。 [前回の枝別誤差](fixed-vowel-i-pharynx-predicted-radiation.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-port-bandwidth.json)

固定上流の `HumanVoice::render` は声門の開口を更新し、`AirwayNetwork::step` は前標本の圧力差と運動量から各枝の流量を求める。口蓋帆ポートは咽頭末端と鼻腔入口を結ぶ。面積、入口の収縮、出口から下流セルに向けた拡大で流向別の二次係数が決まり、現在の流量に対して `K(U)U|U|` が圧力損失になる。定常狭窄試験では、短い狭窄を通過する流量をベルヌーイ近似に照合する。鼻端放射の観測はR–Lの負荷を通る流量で、PCM段より前に採る。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[ポート損失と枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L990)・[放射流量](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

開口を0.30 cm²に固定した場合、枝の式は `I fs(U[n]−U[n−1]) + R U[n] + K(U[n])U[n]|U[n]| = Δp[n−1]` になる。流量 `U` は cm³/s、圧力 `Δp` は dyn/cm²、内部標本化周波数 `fs` は96 kHz。上流は流向に応じた二次方程式の根から `U[n]` を求め、運動量 `I U[n]` を保存し、その流量で節点圧と放射を更新する。入口収縮係数0.3と出口拡大係数0.8から求まる二次係数は順方向0.00586489、逆方向0.00658788 dyn·s²/cm⁸だった。 [係数と根の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1014)

400〜500 msの各波形で、二次損失の2,310 Hz成分を複素圧力 `N` として求める。予測、平均だけ実測、平均と10周波数が実測、全帯域が実測の順に `N₁` から `N₄` と置く。 `N₁−N₂`、`N₂−N₃`、`N₃−N₄` を `N₁−N₄` の方向に射影する。射影は符号付きで合計1になる。鼻端への影響を見るときだけ、枝の窓端項を別枠で加える。鼻端の比較では他の60枝を前回と同じ予測入力に固定する。 [節点方程式と前回の計算](fixed-vowel-i-pharynx-predicted-radiation.md)

## 実測

| 2,310 Hzのポート損失残差方向への射影 | 7.2 cmH₂O | 5.76 cmH₂O |
| --- | ---: | ---: |
| 平均流量の差 | +0.60% | +0.59% |
| 選んだ10周波数内の複素係数の差 | −18.70% | −11.52% |
| 選択外の周波数を省いた影響 | +118.10% | +110.93% |

選択外の成分による50%以上の射影という事前基準を両版で満たした。同じ10周波数内の複素係数の差は逆向きで、帯域を絞った影響の一部を相殺していた。予測した10周波数そのものの実測に対するL2相対誤差は1.54%と1.15%だった。 [複素圧力・射影・全判定](../runs/fixed-vowel-i-velum-port-bandwidth-20261124-repeat/summary.json)

| 口蓋帆ポートの流量条件 | 7.2 cmH₂Oの鼻端誤差 | 5.76 cmH₂Oの鼻端誤差 | 逆流標本数（7.2 / 5.76） |
| --- | ---: | ---: | ---: |
| 全予測 | 0.24693% | 0.20181% | 4,369 / 4,425 |
| 平均だけ実測 | 0.24520% | 0.20053% | 4,360 / 4,418 |
| 平均と10周波数を実測 | 0.29574% | 0.22546% | 4,302 / 4,362 |
| 全帯域を実測 | 0.03734% | 0.01966% | 4,384 / 4,443 |

鼻端誤差は元の粘性節点モデルで、声門流量の2,310 Hz成分に対する鼻端放射流量比を観測値と照合した値。ポートの差し替えだけで全予測時の誤差が84.9%と90.3%減った。同じ10周波数だけを実測に合わせると鼻端誤差が一度増え、全帯域を戻すと下がった。ポートの窓端項は絶対値4.61×10⁻⁸と9.36×10⁻⁸ dyn/cm²だった。 [鼻端流量比と窓端項](../runs/fixed-vowel-i-velum-port-bandwidth-20261124-repeat/summary.json)

ポートの専用観測とネットワークの枝流量、抽出波形と逆FFT、損失の直接射影とFFT、前回の全予測とポート残差、鼻端の直接求解と枝源の重ね合わせを照合した。数値照合の最大相対差は6.80×10⁻¹³で事前許容差10⁻⁹以内。両版の比較も事前許容差10⁻⁸以内だった。

## 次の比較

ポートに第7〜18倍音（770〜1,980 Hz）を追加して既存の第1〜6・第19〜22倍音の間を埋める。実測から抽出した波形と声門流量から予測した波形の双方を作り、他の60枝と窓を固定して圧力源と鼻端を照合する。今回の比較で特定したのは、選択外の全周波数を戻す効果まで。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。既存の通常CLIと固定上流の収録をRTL9210B-CGから参照し、新しい生波形の保存は省いた。研究ワークスペースと `/tmp` からの各35判定が通り、要約はバイト単位で一致した。固定上流の `steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss` にも通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-port-bandwidth-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-port-bandwidth-20261124-repeat/manifest.json)

研究ワークスペースで以下のコマンドを実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_port_bandwidth.py fixed-vowel-i-velum-port-bandwidth-20261124-repeat
```

第49版の全体監査では247実行・3,840成果の509判定がすべて通った。この比較と監査の3実行で1,508入力・12出力をSHA-256で照合した。RTL9210B-CGの追加出力は重複を統合して8ファイル分、13,124バイトだった。 [第49版の実行記録](../runs/plan-completion-v49-fixed-vowel-i-velum-port-bandwidth-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v49-fixed-vowel-i-velum-port-bandwidth-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
