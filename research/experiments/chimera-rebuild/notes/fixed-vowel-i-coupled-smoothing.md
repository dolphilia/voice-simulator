# 声門と気道を結合した固定 /i/ で口腔2枝を平滑化する

前回は咽頭入口に5種類の声門流量を直接与え、口腔の節点34→35・35→36の二次損失を平滑化した。今回は同じ声道形状に、7.2 cmH₂O、基準音高110 Hzの通常の固定母音発声を使う。声門流量は各描画で声門と気道の相互作用から求める。内部96 kHz、出力48 kHz、内部標本38,400で変更を有効にし、65,536標本・32,768フレームを保存する。 [事前登録](../cases/fixed-vowel-i-coupled-smoothing.json)・[前回の固定流量の入力と結果](fixed-vowel-i-lf-smoothed-branches.md)

## 通常発声での更新と観測

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は、肺の境界圧を進め、前の声門下圧と咽頭入口圧の差から声門面積 `a`（cm²）を求める。面積を声門ポートに反映し、`AirwayNetwork::step` で枝流量（cm³/s）、壁流量、節点圧（dyn/cm²）、放射の体積流量の微分（cm³/s²）を更新する。研究版の通常の入口は `vocal-cli render-pcm` → `render_fixed_voice` → `FixedVoice::step_source`。肺境界、前標本の声門上下圧、声門面積、気道、放射の順で対応する。上流の狭窄試験はベルヌーイ近似と定常流量を比較し、肺ポートの試験は有声区間の声門下圧と努力値を照合する。 [上流の発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[狭窄の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[肺ポートの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L48)・[研究版の入口](../crates/vocal-cli/src/geometry_case.rs#L441)・[研究版の声門結合](../crates/vocal-core/src/voice.rs#L213)

対象枝の流量 `U[n]` は、静的な声道なら `p_a[n−1]−p_b[n−1] = L(U[n]−U[n−1])/Δt + R U[n] + F(U[n])` を満たす。元の損失 `F(U)=K_s U|U|` は向き別の係数 `K_s` を用いる。両版の隔離ビルドで同じ平滑化式を使い、幅60 cm³/s内ではこの損失に `1−(1−|U|/60)^3` を掛ける。更新前の駆動圧を幅境界の値と比べ、境界に達するまでの正の流量の大きさを二分法で解いて符号を戻す。流量が幅外の標本は従来の二次式で解く。 [平滑化の実装](../tools/measure_fixed_alpha_loss_tangent.py#L31)・[隔離ビルドと計測](../tools/measure_fixed_vowel_i_coupled_smoothing.py)

## 差が出る標本の予測

切替後の無変更流量を調べ、2枝のいずれかが初めて `0<|U|<60` を満たす内部標本を、最初の局所差と予測した。圧力の更新は枝流量の更新に続くため、入口圧の差が声門流量に戻るのは少なくとも次の内部標本になる。PCMを出す前に、放射微分へFIR、2対1の間引き、ゲイン、25 Hzの直流除去、包絡リミッターを適用する。保存済みの無変更PCMを両版それぞれで照合し、記録した放射微分からも同じ出力段をNumPyとSciPyで独立に計算する。 [通常発声の保存ケース](../cases/vowel-voice-i.json)・[無変更の実行](../runs/vowel-voice-i-20261119-j/manifest.json)・[研究版の出力段](../crates/vocal-core/src/output.rs)

## 実測

切替時の無変更流量は34→35で−14.06、35→36で−13.69 cm³/sだった。両枝とも幅内にあり、予測した標本38,400で枝流量と節点34〜36の圧力に差が出た。切替以降27,136標本のうち無変更流量が幅内に入ったのは、34→35が10,210標本（37.63%）、35→36が10,187標本（37.54%）。各段で最初に値が変わった標本は両版で一致した。 [結果と判定](../runs/fixed-vowel-i-coupled-smoothing-20261124-registered/summary.json)

| 観測 | 最初の差 | 切替からの内部標本数 |
| --- | ---: | ---: |
| 対象2枝の流量と節点34〜36の圧力 | 38,400 | 0 |
| 放射流量の微分 | 38,401 | 1 |
| 口端流量 | 38,412 | 12 |
| 咽頭入口圧 | 38,421 | 21 |
| PCMのフレーム19,210の内部終端 | 38,421 | 21 |
| 声門流量と声門下圧 | 38,422 | 22 |

放射の微分には声道壁の寄与が含まれる。口端流量の差が現れる前に、総放射の微分に差が出た。無変更のPCMと出力時刻の観測は両版で保存値にビット一致し、切替前もすべて一致した。最大PCM差は1.976×10⁻⁵、差のRMSは全フレームの無変更PCMの0.00179%。放射の微分から計算した独立PCMは、4条件の全標本で描画されたPCMに一致した。上流と研究版のPCM変化量の最大差は2.33×10⁻¹⁰。対象2枝の圧力損失を独立に再構成した相対誤差は4.00×10⁻¹²未満で、丸め許容差を超えた負の仕事率は0標本だった。 [生観測のマニフェスト](../runs/fixed-vowel-i-coupled-smoothing-20261124-registered/manifest.json)

## 声門面積が同じまま流量が変わる理由

声門面積は全65,536標本で一致した。保存した声門上下圧の差を1標本ずらし、上流と同じ30 Hzの一次フィルタで独立に平滑化したところ、切替後は両対照とも5,718〜7,326 dyn/cm²だった。声門の圧力ゲートが上限に達する3,922.66 dyn/cm²を全標本で上回っており、圧力差の変化は駆動面積に伝わらなかった。 [上流の圧力ゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)

最初に声門流量が分かれた38,422では、声門面積と前標本の声門流量が一致していた。前標本の声門上下圧の差の変化は−8.55836×10⁻⁷ dyn/cm²。両条件が順流で共通のポート慣性・抵抗・二次係数を持つため、差分の式は `ΔU = ΔP / (L/Δt + R + K_s(U_{基準}+U_{平滑化}))` となる。上流のスリット・半セルの幾何から得た予測は−3.49212×10⁻¹⁰ cm³/s、上流の観測は−3.49214×10⁻¹⁰ cm³/sだった。次は肺圧だけを下げ、圧力ゲートが上限に達する前の区間でこの平滑化が声門面積まで伝わるかを確認する。 [声門ポートの形状](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[声門の慣性と二次損失](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1007)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4の研究ワークスペースから実行した。再実行は `/tmp` から Python とスクリプトを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_coupled_smoothing.py fixed-vowel-i-coupled-smoothing-20261124-registered
```

両実行で12判定と固定上流の狭窄・肺ポート試験に通過した。要約と7成果はバイト一致し、外部ディスクRTL9210B-CGで7成果の実体を共有した。元の実行パスとSHA-256は両方照合した。 [初回のマニフェスト](../runs/fixed-vowel-i-coupled-smoothing-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-coupled-smoothing-20261124-repeat/manifest.json)

全体監査第28版で、2実行の観測から圧力とPCMの照合をやり直し、前版の判定も再現した。175実行・2,900成果・369判定に通過した。 [第28版の全体監査](../runs/plan-completion-v28-fixed-vowel-i-coupled-smoothing-20261124/manifest.json)
