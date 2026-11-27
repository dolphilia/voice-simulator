# 固定 /i/ の口腔2枝でゼロ流量付近の損失を平滑化する

固定 /i/ の無変更描画で、660 Hz・770 Hzの振幅則からのずれに最も寄与した口腔内の節点34→35・35→36（咽頭入口から9.77・10.25 cm）を選んだ。成人男性の姿勢、5種類の声門流量、96 kHz、標本76,800の切替を保つ。観測するのは切替直前1標本と直後128標本、末尾22周期と直前の1標本。定常流だけの対照には、動的な比較と同じ平均流量139.8857905134376 cm³/sを使う。 [事前登録](../cases/fixed-vowel-i-lf-smoothed-branches.json)・[固定 /i/ の無変更比較](fixed-vowel-i-lf-branch-loss.md)

## 上流の計算と平滑化

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`HumanVoice::render` が肺圧と声門開口を更新して `AirwayNetwork::step` に進む。固定姿勢のプローブは形状を設定して咽頭入口に流量を与える。研究版は通常CLIの `render_fixed_airway` から `AirwayNetwork::step`、`Branch::step` を通る。どちらも前標本の節点圧と運動量から枝流量、壁流量、節点圧と放射流量の順で更新する。定常狭窄試験は1セルと1/4セル相当の形状でベルヌーイ近似の15%以内か判定する。 [通常発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝から壁・節点への更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[研究版の入口](../crates/vocal-cli/src/geometry_case.rs#L569)

枝の流量 `U`（cm³/s）は、節点間の圧力差と前の運動量による駆動圧 `c` から `c = (L/Δt + R)U + K_s U|U|` を満たすよう更新する。圧力の単位は dyn/cm²。隔離した両方のビルドで、選んだ枝の絶対流量が幅 `w = 60 cm³/s` 以下の場合に、向き別の二次損失 `K_s U|U|` へ `1−(1−|U|/w)^3` を掛ける。元の式を解いた流量が幅内かどうかは、駆動圧の絶対値と幅の境界に対応する圧力を比較して判定する。幅内は正の流量の大きさで単調な式を二分法で解き、最後に符号を戻す。幅境界とゼロでは損失の二階微分まで連続になる。 [試験用ビルドと二分法](../tools/measure_fixed_alpha_loss_tangent.py#L31)・[研究版の枝](../crates/vocal-core/src/airway/network.rs#L189)

## 予測と再描画の対応

切替後の口端流量（cm³/s）の複素係数から、正負の5入力を組み合わせて比例・二次からのずれを得る。実装前に、固定上流の保存済み流量で圧力差 `F_s(U)−F(U)` を求め、FFTで660 Hz・770 Hzを取り出した。離散節点方程式で枝ごとの圧力差を口端に伝え、無変更の複素係数に足して、ずれの大きさの増減率を登録した。

再描画の分析では直接DFTを使い、元の流量を固定した寄与と、平滑化後の流量変化が加えた寄与を求める。摩擦・慣性を節点圧差から取り除いて推定した枝損失でも複素差を独立に再構成する。予測の再計算と、流量変化を含む再描画が予測の範囲に収まるかは個別に判定する。 [周波数応答の計測](../tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py#L95)・[固定流量の予測値との照合](../tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py)

## 実測

増減率の分母は各比較における無変更時のずれの大きさ。4比較とも予想した方向に変化した。660 Hzの奇成分だけ、再描画と固定流量予測の差が0.259パーセントポイントで、事前の0.2ポイント基準を上回った。残る3比較は0.101〜0.133ポイント。流量変化による項の絶対値は、4比較の複素差に対して0.279〜0.664%だった。表は研究版で、固定上流も表示精度内で同じ値だった。 [両版の予測と実測](../runs/fixed-vowel-i-lf-smoothed-branches-20261124-registered/summary.json)

| 口端流量の成分 | 固定流量による予測 | 再描画 |
| --- | ---: | ---: |
| 660 Hzの奇成分の比例からのずれ | +18.02% | +18.28% |
| 660 Hzの偶成分の二次からのずれ | +26.18% | +26.28% |
| 770 Hzの奇成分の比例からのずれ | −17.27% | −17.15% |
| 770 Hzの偶成分の二次からのずれ | +29.10% | +29.23% |

無変更の観測は保存した5入力の系列とビット一致し、定常流だけを使った無変更と平滑化もビット一致した。両版の動的な系列は相対3.20×10⁻¹⁴以内、枝の圧力収支は2.74×10⁻¹²以内だった。丸め許容差を超えた負の仕事率は0標本。口端流量の複素差は、流量と損失式から相対4.41×10⁻¹⁰以内、圧力から逆算した損失で4.48×10⁻¹¹以内に再構成した。

最初に差を検出した標本は倍率−1で76,829、−0.5で76,861、0と+0.5で76,862、+1で76,885。最初の4入力では節点34・35の圧力と枝34→35の流量、+1では節点35・36の圧力に現れた。位相によって幅内へ入る時刻が異なる。 [切替直後の観測](../runs/fixed-vowel-i-lf-smoothed-branches-20261124-registered/summary.json)

## 複素差の向きと流量変化

固定流量による複素差 `D` と無変更のずれ `B` から、`|B+D|²/|B|²−1 = 2 Re(D/B)+|D/B|²` を求めた。770 Hzの偶成分では `D` の `B` に対する位相が固定 /ɑ/ の−132.89°、固定 /i/ の+43.63°。このため内積に相当する項が負から正に変わり、幅60の再描画で /ɑ/ は12.28%減、/i/ は29.23%増になった。 /ɑ/ と /i/ ではそれぞれの寄与上位2枝を変更しているため、位相の差には選択枝と声道形状の両方が関わる。 [固定 /ɑ/ の幅60の観測](../runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-repeat/summary.json)

660 Hzの奇成分の予測差0.259ポイントは、流量変化による項を加えると再現できた。保存した上流の5系列で、平滑化後と無変更時の流量へ同じ平滑化式を適用して差を取り、定常点の接線を差し引いて枝ごとに伝搬させた。流量変化による項の方向に射影すると、変更対象より口端側の44→45と43→44が26.18%と21.71%を占めた。対象2枝だけの損失式を変えた場合にも、流量の応答を通じて別の枝の圧力源が変わる。 [枝流量と節点圧の保存先](../runs/fixed-vowel-i-lf-smoothed-branches-20261124-registered/manifest.json)

次の比較では通常の固定 /i/ 発声で同じ2枝を観測し、声門と気道を相互に結合した状態で幅60に入る標本を数える。無変更対照と同じ声門・肺圧の設定で、咽頭入口圧、声門流量、口端流量とPCMのどの順で差が出るか確認する。 [通常の固定 /i/ のケース](../cases/vowel-voice-i.json)・[研究版の固定発声入口](../crates/vocal-cli/src/geometry_case.rs#L441)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4の研究ワークスペースから実行した。再実行では `/tmp` から Python、スクリプト、ケースを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py \
  fixed-vowel-i-lf-smoothed-branches-20261124-registered \
  --case cases/fixed-vowel-i-lf-smoothed-branches.json
```

両方とも数値比較の56判定と固定上流の狭窄試験に通過した。660 Hz奇成分の予測差の仮説は不成立として要約に保存した。要約と6成果はバイト一致し、6成果をRTL9210B-CG上でハードリンクにまとめて元の実行パスとSHA-256を照合した。固定 /ɑ/ の幅60・30でも従来の要約を保存観測から再集計し、元の要約に一致した。 [初回マニフェスト](../runs/fixed-vowel-i-lf-smoothed-branches-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-lf-smoothed-branches-20261124-repeat/manifest.json)

第27版の全体監査では観測から今回の要約を再構成し、独立した2実行と第26版の判定を照合した。172実行・2,872成果・363判定に通過した。 [第27版の監査](../runs/plan-completion-v27-fixed-vowel-i-lf-smoothing-20261124/manifest.json)
