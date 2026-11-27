# 肺圧を下げた固定 /i/ で平滑化の効果を声門面積まで追う

前回の通常発声は肺圧7.2 cmH₂Oで、30 Hzでフィルタした声門上下圧差は5,718〜7,326 dyn/cm²だった。これは声門の圧力ゲートが上限に達する3,922.66 dyn/cm²を上回る。圧力差を半分とした目安がゲートの遷移域に入るため、今回は肺圧を3.6 cmH₂Oにした。固定 /i/、110 Hz、声門と気道の結合、内部96 kHz、出力48 kHzを維持し、内部標本38,400から口腔の34→35・35→36へ幅60 cm³/sの平滑化を適用する。 [事前登録](../cases/fixed-vowel-i-low-pressure-smoothing.json)・[7.2 cmH₂Oの結果](fixed-vowel-i-coupled-smoothing.md)

## 声門上下圧から面積に至る式

上流の `HumanVoice::render` は直前の声門下圧と咽頭入口圧の差 `Δp` を `ParametricGlottis::next` に渡し、返った面積を声門ポートに反映してから気道を進める。研究版も `vocal-cli render-pcm` → `render_fixed_voice` → `FixedVoice::step_source` → `Glottis::step` の順で処理する。切替後に変わる元の圧力源は2枝の二次損失で、枝の流量・節点圧を進めた次の標本から声門がその圧力変化を読む。上流の狭窄試験は定常流量をベルヌーイ近似から15%以内か判定し、肺ポートの試験は有声区間の声門下圧と努力値を確認する。 [上流の発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[上流の狭窄と肺ポートの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[肺ポートの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L48)・[研究版の声門結合](../crates/vocal-core/src/voice.rs#L213)・[研究版の声門](../crates/vocal-core/src/glottis.rs#L221)

`Δp` を30 Hzの一次フィルタに通して `P[n]` を得る。圧力ゲートの下限は1,961.33 dyn/cm²、上限は3,922.66 dyn/cm²。上下限で正規化し0〜1に制限した値 `x` に `x²(3−2x)` を適用する。開大0.00225 cm²は接触ゲートの遷移下限0.08 cm²より小さく、閉鎖指令は0なので、この条件で有声度の目標値は圧力ゲートだけで決まる。目標値を25 Hzで平滑化して有声度 `V[n]` を得る。声門面積 `A[n]`（cm²）は位相に応じた振動項と、時定数4 msで0.01475 cm²へ近づく静的な開口 `S[n]` の和になる。圧力差に対する有声度増分を `ΔV[n]` とすると、同じ位相・呼気指令の比較では無変更時の面積と有声度から `ΔA[n] = (A[n]−S[n])ΔV[n]/V[n]` を予測できる。 [上流の平滑化と開口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L217)・[smoothstepの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L155)・[研究版の観測と独立計算](../tools/measure_fixed_vowel_i_coupled_smoothing.py)

隔離ビルドで両版のフィルタ状態と有声度を採取し、前標本の圧力差から別に計算した値と照合する。声門面積差、枝損失、放射から再構成したPCMも比較する。切替前は無変更と平滑化の時系列をビット照合する。肺圧だけの変更は、実際にCLIへ渡したケースと前回の計測設定から照合する。

## 実測

切替後の27,136標本すべてで、フィルタ後の声門上下圧差がゲートの遷移域に入った。無変更で2,986.98〜3,633.63 dyn/cm²、平滑化後は2,986.98〜3,633.63 dyn/cm²で、標本ごとの差の最大値は0.001906 dyn/cm²。有声度は最大7.141×10⁻⁷、声門面積は最大6.727×10⁻⁸ cm²変化した。両版の圧力・有声度・面積差の独立再構成は、絶対誤差がそれぞれ1.46×10⁻¹¹ dyn/cm²、5.67×10⁻¹⁵、5.00×10⁻¹⁶ cm²以内だった。 [観測と仮説の判定](../runs/fixed-vowel-i-low-pressure-smoothing-20261124-registered/summary.json)

| 観測 | 初めて値が変わった時刻 | 切替からの内部標本数 |
| --- | ---: | ---: |
| 対象2枝の流量と節点34〜36の圧力 | 38,400 | 0 |
| 放射流量の微分 | 38,401 | 1 |
| 口端流量 | 38,412 | 12 |
| 咽頭入口圧とPCMフレーム19,210の内部終端 | 38,421 | 21 |
| フィルタ後の声門上下圧差と声門流量 | 38,422 | 22 |
| 有声度と声門面積 | 38,423 | 23 |

表の時刻は両版で一致した。最初の声門面積差（1.73×10⁻¹⁸ cm²）は浮動小数点の分解能に近く、面積差の最大値は標本57,973に現れた。PCMは面積が分かれる前のフレームで差が生じ、出力差のRMSは全フレームの無変更PCMの0.000416%だった。7.2 cmH₂Oの0.00179%より小さかった。3.6 cmH₂Oでは声門面積への経路が加わり、出力差の大きさは放射や枝流量を含む全体の応答で決まった。平滑化による全PCM差は上流と研究版で一致し、両版の全PCMを記録した放射流量から独立に再構成できた。 [低肺圧の観測](../runs/fixed-vowel-i-low-pressure-smoothing-20261124-registered/manifest.json)・[7.2 cmH₂Oの比較](../runs/fixed-vowel-i-coupled-smoothing-20261124-repeat/summary.json)

次は3.6 cmH₂Oの平滑化を保ち、声門モデルに入る圧力差だけを無変更観測に置き換える。咽頭から戻る圧力のうち、声門面積を通る経路が切替後のPCM差へどれだけ寄与するかを比較する。気道が解く実際の声門上下圧と枝流量は引き続き更新する。 [既存の圧力差置換の計測](../tools/measure_glottal_feedback.py)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースから実行した。再実行は `/tmp` から Python、スクリプト、ケースを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_coupled_smoothing.py fixed-vowel-i-low-pressure-smoothing-20261124-registered \
  --case cases/fixed-vowel-i-low-pressure-smoothing.json
```

両実行で13判定と固定上流の狭窄・肺ポート試験に通過した。要約と8成果はバイト一致し、8成果は元の実行パスを保ちながらRTL9210B-CG上で実体を共有した。7.2 cmH₂Oの保存観測も同じスクリプトで再集計し、以前の要約と一致した。 [初回マニフェスト](../runs/fixed-vowel-i-low-pressure-smoothing-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-low-pressure-smoothing-20261124-repeat/manifest.json)

第29版の全体監査で固定 /i/ の圧力・枝・PCMの照合を再計算し、独立した2実行の成果と第28版の全判定を照合した。178実行・2,930成果・375判定に通過した。 [第29版の全体監査](../runs/plan-completion-v29-fixed-vowel-i-low-pressure-smoothing-20261124/manifest.json)
