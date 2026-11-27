# 半分に狭めた口蓋帆ポートで2倍音の補正を検証する

0.30 cm²の固定 /i/ では、1,320 Hzと2,420 Hzの予測補正で鼻端誤差が7.2 cmH₂Oのとき30.82%減った。今回は同じ肺圧・声道輪郭で音響ポート面積だけを0.15 cm²にする。周波数を選び直さず、流量誤差を50%以上減らし、鼻端を実測係数で補正した場合の改善量を80%以上回復すると事前登録した。 [0.30 cm²の結果](fixed-vowel-i-velum-port-selected-pair-feedback.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-narrow-port-feedback.json)

固定上流の `HumanVoice::render` は肺圧と声門開口を更新して `AirwayNetwork::step` を呼ぶ。`HumanAirway::new` が咽頭末端と鼻腔入口をポートでつなぐ。固定開口では `I fs(U[n]−U[n−1])+R U[n]+K(U[n])U[n]|U[n]|=Δp[n−1]`。流量は cm³/s、圧力は dyn/cm²。慣性 `I` はポート管と隣接半セルの慣性の和、丸い断面の粘性抵抗 `R` は面積 `A` の `A^(−3/2)` に比例する。二次係数 `K` には `A^(−2)` に比例する入口収縮と、下流セルとの面積差による拡大が入り、逆流時は拡大先が入れ替わる。根から現在の流量を求め、運動量を次標本へ保存し、節点圧と鼻端のR–L終端を更新する。固定上流の短い狭窄試験は定常流量をベルヌーイ近似で照合し、鼻音化の試験では開口が生じたときの第一フォルマント帯域の比を評価する。 [発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L990)・[狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[鼻音化試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sound_marks_acoustic.rs#L94)

候補のCLIは輪郭の計算後に音響ポート面積を上書きする。上流は固定コミットの一時コピーに観測用の差分を当て、同じ輪郭のまま制御ブロックでポートの目標面積を上書きする。独立した上流の線形要素出力でも同じ面積の上書きを使う。96 kHz、400〜500 msに前標本を含め、収録の圧力と流量から観測損失の対照を計算する。予測側は声門流量と新しい開口の線形要素から22倍音の枝流量を組み直し、二次損失から接線抵抗の寄与を除いて同じ2周波数に一度戻す。 [CLIの開口の上書き](../crates/vocal-cli/src/geometry_case.rs#L271)・[上流の観測差分](../tools/measure_fixed_vowel_i_velum_radiation.py#L48)・[固定開口の線形要素](../tools/upstream_vowel_probe.rs#L96)・[一度の補正と有限窓項](fixed-vowel-i-velum-port-loss-feedback.md)

## 実測

音響開口を0.30から0.15 cm²にすると、観測平均ポート流量は31.99から21.16 cm³/sへ33.85%減った。ポートの慣性は1.963倍、粘性抵抗は2.828倍、二次係数は順流で4.364倍、逆流で4.114倍だった。粘性抵抗の比は面積比による `2^(3/2)` と一致した。入力、輪郭、節点、他の枝は先行条件と一致した。新しい線形要素を別々に取得した両版間で、圧力・流量系列の最大相対差は2.79×10⁻¹³、PCMの全標本は数値一致だった。 [幾何・時系列と判定](../runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-repeat/summary.json)

| ポートの2倍音の条件 | 流量のL2相対誤差 | 2,310 Hzの鼻端複素誤差 |
| --- | ---: | ---: |
| 無補正 | 30.02% | 0.52758% |
| 予測損失による補正 | 1.473% | 0.51012% |
| 2成分だけ実測係数に置き換える対照 | 0% | 0.50662% |

予測損失で2成分の流量誤差が95.09%、鼻端誤差が3.31%減った。実測係数の差し替えでは鼻端誤差が3.97%減った。予測補正はその改善量の83.30%を回復し、事前の流量50%減少と鼻端改善量80%回復を両版で満たした。前回の0.30 cm²では鼻端誤差そのものが30.82%減った。狭い開口では1,320 Hzと2,420 Hzの係数が正確でも、2,310 Hzに残る誤差の大半が残る。 [予測補正と実測対照](../runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-repeat/summary.json)

観測の圧力損失を接線解に与えた対照は、実測の係数をL2相対差8.42×10⁻⁸以内で再現し、鼻端流量比は係数を直接置き換えた対照と相対3.16×10⁻¹⁰以内で一致した。FFT、枝源の重ね合わせ、粘性モデルでの独立解と波形係数・平均の保持も照合した。0.30 cm²の先行実行は共通計算の変更後も、保存した全60判定と要約を再現した。

### 鼻端に残る差の事後対照

無補正の鼻端解を使い、観測窓で `prior.branch_pressure` が求める各枝の観測二次損失と窓端項の和を `Pobs`、ポートの22倍音と他60枝の10周波数から求めた予測圧力源を `P0` とした。2,310 Hzの粘性節点行列を `M`、枝源の節点への割り当てを `D`、鼻端の読出しを `n`、声門流量の係数を `Ug` とすると、各枝の圧力源の差が鼻端流量比に与える変化は `(solve(M.T,n) @ D) * (Pobs−P0) / Ug` で求まる。この内積をポートの枝だけに適用する対照で、鼻端誤差は0.52758%から0.05419%へ89.7%減った。全枝の観測損失を使うと相対5.49×10⁻⁸まで下がった。ポートの変化を補正前の複素残差で割ると `0.963−0.096i` で、ここで比較した枝群で最も大きかった。これらは再実装版と上流版で一致し、事前の判定とは別に記録した。 [計測入力と各対照の実行記録](../runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-registered/manifest.json)

## 次の比較

0.15 cm²の今回の収録を使い、ポートの基準の22倍音の予測波形に対して平均だけを実測にする場合、平均と同じ22倍音を実測にする場合、全帯域を実測にする場合を順に比べる。鼻端への誤差寄与の大きいポートで、平均、同じ帯域内の係数、選択外成分のどれが2,310 Hzの損失を変えるかを切り分ける。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。通常CLIと固定上流の新規収録をRTL9210B-CGに直接書き出した。前回の収録密度を基に各実行の出力を約50 MBと見積もり、ビルドを含む必要空き容量を512 MiBとして実行前に確認した。研究ワークスペースと `/tmp` からの各38判定が通り、要約と再収録の主要成果はバイト単位で一致した。 [初回マニフェスト](../runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-repeat/manifest.json)

研究ワークスペースで以下を実行する。再計測時は末尾の実行IDを変更する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_narrow_port_feedback.py fixed-vowel-i-velum-narrow-port-feedback-20261124-repeat
```

第55版の全体監査は265実行・3,956成果の545判定に通過した。今回の3実行について1,855入力と56出力をSHA-256で照合し、同じバイト列の19出力を外部ボリューム上のハードリンクで統合した。RTL9210B-CG上の追加出力は統合後に34ファイル分、51,800,343バイト。後続で枝圧力を読み直せるよう、収録した全列を観測窓と前標本の範囲で保持した。 [第55版の実行記録](../runs/plan-completion-v55-fixed-vowel-i-velum-narrow-port-feedback-20261124/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v55-fixed-vowel-i-velum-narrow-port-feedback-20261124 \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
