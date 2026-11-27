# 低肺圧の固定 /i/ で声門の入力圧力差を置換する

前回の3.6 cmH₂O、110 Hzの固定 /i/ では、口腔2枝を平滑化すると、切替23標本後に声門面積にも差が出た。今回は平滑化を維持し、声門モデルが読む圧力差だけを無変更の観測列に置換する。無変更、通常の平滑化、圧力差だけを置換した平滑化の3条件を固定上流と研究版で描画する。形状、肺圧、声門設定、標本38,400からの切替、内部96 kHzと出力48 kHzは前回と同じ。 [事前登録](../cases/fixed-vowel-i-pressure-replay.json)・[低肺圧の実測](fixed-vowel-i-low-pressure-smoothing.md#実測)

## 気道で解く圧力と声門が読む圧力

固定上流の `HumanVoice::render` は肺境界圧を更新し、前標本の声門下圧・咽頭入口圧の差を `ParametricGlottis::next` に渡す。声門は30 Hzで圧力差を平滑化し、圧力ゲートと25 Hzで平滑化した有声度を経て面積（cm²）を求める。その面積を声門ポートに渡してから `AirwayNetwork::step` を呼び、枝流量（cm³/s）、節点圧（dyn/cm²）、放射の体積流量の微分（cm³/s²）を進める。研究版は `vocal-cli render-pcm` → `render_fixed_voice` → `FixedVoice::step_source` の順で、既存の `pressure_override` が声門モデルに渡す値を選ぶ。このとき流量指定を無効にしたので、声門枝は面積から設定された開口と、気道が解いた実圧力差で進む。上流の狭窄試験はベルヌーイ近似で定常流を比較し、肺ポートの試験は発声時の声門下圧・努力値を照合する。 [上流の発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[声門ゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[研究版の圧力入力](../crates/vocal-core/src/voice.rs#L214)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[肺ポートの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L48)

置換系列は各版の保存済み無変更の声門上下圧を引き、1標本遅らせたf64の列。標本0の入力は0とした。切替前は各条件とも物理圧力差を用い、切替後の置換条件だけが同じ標本番号の保存値を用いる。実圧力差とモデル入力を別々に採取し、実圧力差を描画した節点圧から再計算する。置換によりモデル入力が無変更とビット一致すれば、フィルタ・有声度・面積も無変更に一致すると予想した。 [既存の圧力置換の対照](../tools/measure_glottal_feedback.py#L40)・[今回の計測](../tools/measure_fixed_vowel_i_coupled_smoothing.py)

## PCM差の比較

無変更のPCMを `B`、通常の平滑化を `S`、入力圧力差を置換した平滑化を `R` とする。全変化 `C=S−B` に対し、面積差を固定して残る変化を `D=R−B`、声門面積が応答できる場合に加わる変化を `M=S−R` として、切替後のRMSと `C` の方向への射影を計算する。後者は `⟨M,C⟩/⟨C,C⟩`。エネルギーには `2⟨D,M⟩` の交差項があるため、各差のRMSをそのまま足すと全変化のRMSにはならない。各描画のPCMは放射微分にFIR、間引き、ゲイン、直流除去、包絡リミッターを適用する独立計算にも照合する。 [出力の独立計算](../tools/measure_pcm_output.py)・[PCMの事前判定](../cases/fixed-vowel-i-pressure-replay.json)

## 実測

無変更と通常の平滑化は各版の保存観測とビット一致した。圧力差を置換した平滑化では、声門のフィルタ後の圧力差・有声度・面積が無変更と全65,536標本でビット一致し、モデルに渡した圧力差も指定列に一致した。一方、気道が解いた実圧力差とモデル入力は標本38,422で最初に分かれ、最大差は0.004366 dyn/cm²だった。置換後も声門枝流量は無変更から最大7.293×10⁻⁵ cm³/s変化した。 [結果と判定](../runs/fixed-vowel-i-pressure-replay-20261124-registered/summary.json)

| 切替後のPCMの差 | RMS |
| --- | ---: |
| 通常の平滑化 − 無変更 | 1.767×10⁻⁷ |
| 圧力差を置換した平滑化 − 無変更 | 1.728×10⁻⁷ |
| 通常の平滑化 − 圧力差を置換した平滑化 | 2.338×10⁻⁸ |

面積を介する成分のRMSは全変化の13.23%。全PCM差と同じ方向への射影は+3.06%、両成分の交差項は全変化のエネルギーの+2.62%だった。表は両版で一致し、面積を介するPCM差の版間誤差は全フレームで0だった。置換条件の枝の圧力収支も相対9.59×10⁻¹²未満で、丸めの許容差を超える負の仕事率は0標本。独立に計算したPCMは全6描画で各版のPCMと一致した。 [再実行の生データとコードの差分](../runs/fixed-vowel-i-pressure-replay-20261124-repeat/manifest.json)

通常の平滑化と圧力差を置換した平滑化で、最初のPCM差はどちらもフレーム19,210に現れた。両条件の面積は内部標本38,423、放射微分は38,429で分かれた。それに対して、両条件の32ビットPCMの差は19,325フレームで初めて観測された。出力段の直流除去後の振幅は全描画で最大0.06596程度で、リミッターは動作しなかった。放射微分の差にFIR・間引き・直流除去を直接適用した独立計算では、丸め前の差はフレーム19,214から生じた。32ビットPCMで差を検出する前の最大値は9.52×10⁻¹¹で、最初に記録された差1.86×10⁻⁹はそのフレームの1 ULPだった。丸め前のRMS比は13.23%、射影は+3.07%だった。 [放射とPCMの保存観測](../runs/fixed-vowel-i-pressure-replay-20261124-repeat/manifest.json)・[出力段の処理](../crates/vocal-core/src/output.rs)

次は同じ3条件で壁、口端、鼻端の放射流量を直接採取する。総放射を差分から逆算する場合の丸めの影響を避け、各成分を共通の出力段に通して最初のPCM差と窓全体のRMSを分解する。 [上流の放射流量の合算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1071)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で研究ワークスペースから実行した。再実行では `/tmp` からPython、スクリプト、ケースを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_coupled_smoothing.py fixed-vowel-i-pressure-replay-20261124-registered \
  --case cases/fixed-vowel-i-pressure-replay.json
```

両実行で27判定と固定上流の狭窄・肺ポート試験に通過した。要約と10成果がバイト一致し、RTL9210B-CG上で10成果の実体を共有した。保存された7.2・3.6 cmH₂Oの従来の要約も、現在のスクリプトによる再集計と一致した。 [初回のマニフェスト](../runs/fixed-vowel-i-pressure-replay-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-pressure-replay-20261124-repeat/manifest.json)

第30版の全体監査で、置換した入力圧、気道の圧力収支、PCMの照合を保存観測から再計算し、独立した2実行の成果と第29版の判定を照合した。181実行・2,964成果・381判定に通過した。 [第30版の全体監査](../runs/plan-completion-v30-fixed-vowel-i-pressure-replay-20261124/manifest.json)
