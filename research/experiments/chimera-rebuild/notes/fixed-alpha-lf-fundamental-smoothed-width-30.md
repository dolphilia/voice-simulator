# 咽頭2枝の平滑化の幅を30 cm³/sに狭める

固定 /ɑ/ の節点26→27・25→26で、損失の平滑化幅を60 cm³/sにした場合、770 Hzの偶成分のずれは無変更から12.28%減った。同じ無変更流量を使った圧力源の計算では、幅30 cm³/sに狭めると7.91%増えると予測した。幅以外の条件を揃えて再描画し、この向きの反転を検証した。 [事前登録](../cases/fixed-alpha-lf-fundamental-smoothed-width-30.json)・[幅60の再描画と固定流量による予測](fixed-alpha-lf-fundamental-smoothed-branches.md#次の幅を決める予測)

## 保存条件と枝の更新

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は、肺圧と声門開口を更新してから `AirwayNetwork::step` を呼ぶ。固定姿勢のプローブは声門流量を咽頭入口に直接与える。研究版は `vocal-cli render` → `render_fixed_airway` → `AirwayNetwork::step` → `Branch::step` で同じ観測を取る。枝の流量は前標本の節点圧と運動量を使って解き、更新した流量を節点収支に反映する。その後に壁流量、節点圧、放射負荷を進める。上流の定常狭窄試験では1セルと1/4セルの狭窄を通る流量をベルヌーイ近似と15%以内で照合する。 [通常発声の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[研究版の固定姿勢](../crates/vocal-cli/src/geometry_case.rs#L569)・[研究版の枝](../crates/vocal-core/src/airway/network.rs#L189)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

駆動圧 `c` と流量 `U` は `c = (R + L/Δt)U + F(U)` を満たす。`c` と `F(U)` は dyn/cm²、`U` は cm³/s。変更区間 `|U| ≤ w` で、元の二次損失 `K_s U|U|` に `1 − (1 − |U|/w)^3` を掛ける。ゼロと区間端で損失の二階微分まで連続で、区間内の単調な式は二分法で解く。両幅とも同じ隔離ビルドの処理を通し、設定で幅 `w` を渡す。96 kHz、標本76,800からの変更、固定LFの110 Hzだけを変えた倍率0、±1、±0.5、観測窓は幅60と揃えた。定常入力は139.8857905134376 cm³/sで、両幅の定常流観測をビット比較した。 [平滑化と隔離ビルド](../tools/measure_fixed_alpha_loss_tangent.py#L31)・[幅の比較と再実行](../tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py)

## 予測の比較方法

口端流量の最後の22周期をフーリエ変換し、660 Hz・770 Hzの正負振幅から奇成分 `O(a)` と偶成分 `E(a)` を求めた。比例からのずれは `2O(0.5) − O(1)`、二次からのずれは `4E(0.5) − E(1)`。それぞれの複素差の大きさを無変更時で割り、幅30と幅60の増減率を比較した。幅30の予測は、無変更時の枝流量に新旧の損失式を適用した圧力差を、離散節点方程式で口端まで伝えた値を使う。再描画では流量の変化も含めて複素差を求め、予測値とのずれを測った。 [圧力源の再構成と幅の個別比較](../tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py#L90)

## 実測

増減率の基準は各比較の無変更時のずれの大きさ。表は研究版で、固定上流でも4比較すべてで表の精度まで一致した。偶成分は660 Hzと770 Hzで増減が反転した。固定流量による事前予測との差は両版で最大0.020パーセントポイントだった。 [全57判定と両版の複素応答](../runs/fixed-alpha-lf-fundamental-smoothed-width-30-20261124-repeat/summary.json)

| 口端の成分 | 幅60の実測 | 幅30の実測 | 幅30の事前予測 |
| --- | ---: | ---: | ---: |
| 660 Hzの奇成分の比例からのずれ | +28.45% | +8.48% | +8.4752% |
| 660 Hzの偶成分の二次からのずれ | +4.77% | −0.78% | −0.7561% |
| 770 Hzの奇成分の比例からのずれ | +19.85% | +16.07% | +16.0758% |
| 770 Hzの偶成分の二次からのずれ | −12.28% | +7.92% | +7.9113% |

両幅と無変更の間で定常時の節点圧、枝・口端流量、放射流量の時間微分をビット照合した。動的な観測系列は研究版と上流で相対1.97×10⁻¹⁴以内だった。圧力・流量から復元した枝損失と変更した損失式の差は相対9.37×10⁻¹³以内。丸め許容差を超える負の仕事率は0標本だった。口端流量・壁流量・節点圧の複素差は、観測流量と損失式から相対3.04×10⁻⁹以内で再構成した。圧力差と慣性・粘性から推定した枝損失による口端流量の再構成は相対1.08×10⁻⁹以内だった。 [枝の収支と周波数別の復元結果](../runs/fixed-alpha-lf-fundamental-smoothed-width-30-20261124-repeat/summary.json)

幅30で最初に差が現れた標本は、倍率0・+0.5・+1では76,818で、節点25・26の圧力と枝25→26の流量だった。倍率−0.5では76,857、−1では76,858で、節点25〜27の圧力と対象2枝の流量に差が出た。

## 固定流量を使った流量帯別の探索

保存した上流の無変更流量の末尾22周期で、新しい損失から幅60の損失を引いた圧力差を各標本・各枝で求めた。その圧力差を絶対流量が30 cm³/s以下の標本と30超〜60 cm³/sの標本に分け、それぞれの離散フーリエ係数を節点方程式で伝えた。5入力の口端複素係数に上と同じ組み合わせを適用し、各流量帯の複素差を合計の複素差の方向に射影した。770 Hzの偶成分のずれに対して後者が+150.50%、前者が−50.50%だった。後者の寄与の一部を前者が打ち消した。割合は無変更流量での圧力差の寄与で、各流量帯だけを変更した再描画は未実施。 [無変更の枝流量](../runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/manifest.json)・[5条件の組み合わせ](../tools/measure_fixed_alpha_lf_fundamental_amplitude_branch_loss.py#L67)・[離散節点方程式](../tools/measure_fixed_alpha_branch_loss.py#L183)

この幅依存性は固定 /ɑ/ の結果として扱う。次の比較では、固定 /i/ に同じ5入力を与え、元の損失式で660 Hz・770 Hzの奇・偶成分を枝まで追う。共通の枝番号を仮定せず、観測した節点・枝と形状を照合する。 [固定 /i/ の形状基準](../cases/fixed-voice-centerline-i.json)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースから次を実行した。再実行は `/tmp` から、同じ Python、スクリプト、ケースを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py \
  fixed-alpha-lf-fundamental-smoothed-width-30-20261124-registered \
  --case cases/fixed-alpha-lf-fundamental-smoothed-width-30.json
```

両方の実行で事前登録の57判定と固定上流の狭窄試験に通過した。幅60の観測を従来のケースで再集計し、保存済み要約と一致することも確認した。圧縮観測を含む6成果と要約は2実行でバイト一致した。RTL9210B-CG上では6成果をハードリンクで共有し、個別のパスとSHA-256を維持した。 [初回マニフェスト](../runs/fixed-alpha-lf-fundamental-smoothed-width-30-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-alpha-lf-fundamental-smoothed-width-30-20261124-repeat/manifest.json)・[幅60のマニフェスト](../runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-repeat/manifest.json)

第25版の全体監査では、保存した観測から今回の要約を再構成し、独立した2実行の要約と6成果を照合した。第24版の判定も再現し、全166実行・2,802成果・351判定に通過した。 [第25版の監査マニフェスト](../runs/plan-completion-v25-alpha-lf-smoothed-width-30-20261124/manifest.json)
