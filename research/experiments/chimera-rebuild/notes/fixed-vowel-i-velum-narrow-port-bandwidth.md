# 狭い口蓋帆ポートの残差を平均・22倍音・選択外成分に分ける

0.15 cm²の固定 /i/ では、1,320 Hzと2,420 Hzの補正が両成分の流量誤差を95.1%減らした。鼻端放射の誤差の減少は3.31%だった。ポートの全帯域の観測損失を使った事後対照で鼻端誤差が0.528%から0.0542%に下がったため、今回はポートの波形を平均、22倍音の係数、選択外成分に分けて差し替える。選択外の成分が2,310 Hzのポート損失残差の減少方向に50%以上を占めると事前登録した。 [先行計測の対照](fixed-vowel-i-velum-narrow-port-feedback.md#鼻端に残る差の事後対照)・[事前登録](../cases/fixed-vowel-i-velum-narrow-port-bandwidth.json)

上流の `HumanVoice::render` は肺圧と声門開口を更新して `AirwayNetwork::step` を呼ぶ。咽頭末端と鼻腔入口を結ぶ口蓋帆ポートの流量 `U[n]` は、開口固定で `I fs(U[n]−U[n−1])+R U[n]+K(U[n])U[n]|U[n]|=Δp[n−1]` を満たす。流量は cm³/s、圧力は dyn/cm²。流向によって拡大先が変わり、上流はその方向の係数で根を求めて運動量を保存する。更新した流量で節点圧と鼻端の並列R–L終端を更新する。計測は放射の合計を時間差分する前の鼻端流量で行う。上流の定常狭窄試験はベルヌーイ近似に対して流量を確認する。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L990)・[放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

96 kHzの400〜500 msの窓で22倍音の予測ポート波形を基準とし、実測平均との差、同じ22倍音の係数差、実測から平均と22倍音を除いた残りを加える。3つの変化の有無を組み合わせて8波形を作り、`K(U)U|U|` を計算してから2,310 Hzへ射影する。二次損失は波形の差し替え順で個々の寄与が変わるため、事前に定めた順のほか、全6順の平均も求める。ポートの全差に対する符号付き複素射影で、寄与の方向を保つ。全帯域までの変化を評価した後、第23倍音以上の整数倍音だけを戻す対照で、選択外成分の内訳も測る。8波形の鼻端比較ではポート以外の60枝を先行実行の予測源に固定する。全帯域の損失を戻す対照では窓端項を併せて用い、ポートだけを差し替える対照と全枝を差し替える対照をそれぞれ照合する。 [前回の帯域比較の式](fixed-vowel-i-velum-port-bandwidth.md)

## 実測

| ポートの2,310 Hz損失残差を減らす方向への寄与 | 事前に定めた順 | 全6順の平均 |
| --- | ---: | ---: |
| 平均流量 | −4.46% | −2.51% |
| 第1〜22倍音の複素係数 | 100.04% | 96.21% |
| 選択外の周波数 | 4.42% | 6.30% |

寄与は補正前の損失と全帯域から求めた損失の複素差への射影。平均流量の差し替えによる変化が逆向きのため、所定の順では22倍音内の寄与が100%をわずかに超えた。選択外の周波数が50%以上を占めるという仮説は両版で不成立だった。選択外の損失変化のほぼ全量は第23倍音以上の整数倍音で再現でき、他のFFTビンの寄与は射影で約0.00001%だった。 [全8条件と平均の計算結果](../runs/fixed-vowel-i-velum-narrow-port-bandwidth-20261124-repeat/summary.json)

| ポート波形の差し替え | 2,310 Hzの鼻端誤差 |
| --- | ---: |
| 予測の平均と22倍音 | 0.52758% |
| 平均だけ実測 | 0.55490% |
| 22倍音の係数だけ実測 | 0.11525% |
| 平均と22倍音の係数を実測 | 0.07784% |
| 22倍音内と選択外の係数を実測、平均は予測 | 0.01553% |
| 全帯域と平均を実測 | 0.05419% |

22倍音内の係数だけを実測にすると鼻端誤差が78.15%、平均も合わせると85.25%減った。全周波数を実測にして平均を予測に保った条件では、予測した他60枝を含む鼻端の合成誤差がさらに小さくなった。ここでの鼻端誤差には、他60枝を予測に保った影響も含まれる。全枝に窓端項を含む観測損失を入れると、鼻端流量比を相対5.49×10⁻⁸以内で再現できた。ポート波形の再構成、別経路のポート流量、損失のFFT、枝の圧力収支、節点解の重ね合わせの最大相対差は1.97×10⁻¹³だった。 [複素鼻端応答と独立照合](../runs/fixed-vowel-i-velum-narrow-port-bandwidth-20261124-repeat/summary.json)

## 次の比較

0.15 cm²の平均と他60枝の鼻端への圧力源を今回の予測に固定する。ポートの22倍音すべての接線解に、接線抵抗の寄与を引いた予測二次損失を一度戻す。先行する2成分の予測補正と、22成分の実測係数への差し替えを対照にし、0.52758%から0.11525%までの誤差減少量のうち予測で回復できる割合を測る。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。狭開口の収録をRTL9210B-CGから参照した。研究ワークスペースと `/tmp` からの2実行で各24判定中23件が通り、選択外の50%基準だけが偽で終了コード1となった。要約はバイト単位で一致し、固定上流の `airway_adversarial` の6試験にも通過した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-narrow-port-bandwidth-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-narrow-port-bandwidth-20261124-repeat/manifest.json)

研究ワークスペースで以下を実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_narrow_port_bandwidth.py fixed-vowel-i-velum-narrow-port-bandwidth-20261124-repeat
```

第56版の全体監査は選択外の50%基準の不成立も復元し、268実行・3,968成果の551判定に通過した。今回の3実行について1,641入力と12出力をSHA-256で照合した。生の時系列を再利用し、RTL9210B-CGの追加出力は重複統合後に8ファイル分、13,649バイトだった。 [第56版の実行記録](../runs/plan-completion-v56-fixed-vowel-i-velum-narrow-port-bandwidth-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v56-fixed-vowel-i-velum-narrow-port-bandwidth-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
