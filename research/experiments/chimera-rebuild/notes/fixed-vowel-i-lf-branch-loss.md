# 同じ固定LFの声門入力を固定 /i/ へ戻す

固定 /ɑ/ の比較では、660 Hz・770 Hzで比例・二次から外れた成分の大半を、異なる入力条件の間で流向が分かれる標本の枝損失から再構成した。今回は保存した5入力と元の圧力損失を使い、形状だけを成人男性の固定 /i/ に替えた。閉じた鼻咽腔、96 kHz、定常流量139.8857905134376 cm³/s、励振開始の標本76,800を揃えた。 [比較条件の事前登録](../cases/fixed-vowel-i-lf-branch-loss.json)・[固定 /ɑ/ の条件と結果](fixed-alpha-lf-fundamental-amplitude-branch-loss.md)

## 上流と研究版での更新

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の通常発声は、`HumanVoice::render` から制御、肺圧、声門開口を更新して `AirwayNetwork::step` を呼ぶ。固定姿勢のプローブは `HumanAirway::apply` で座標から咽頭・口腔の断面積、最小面積、セル長を決め、`snap_to_targets` の後に咽頭入口へ声門流量の標本を直接与える。研究版は通常の `vocal-cli render` の `render_fixed_airway` から同じ周期列をネットワークへ渡す。解析対象は放射負荷を流れる口端の体積流量で、単位は cm³/s。 [通常発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[姿勢から形状を作る処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[固定上流の観測](../tools/upstream_sagittal_probe.rs#L269)・[研究版のCLI](../crates/vocal-cli/src/geometry_case.rs#L569)

枝 `a→b` は前標本の節点圧 `p_a, p_b` と運動量を使って流量 `U[n]` を更新する。固定姿勢では慣性 `L` と抵抗 `R` が一定なので、`p_a[n−1] − p_b[n−1] = L(U[n] − U[n−1])/Δt + R U[n] + K_s U[n]|U[n]|` が成り立つ。圧力と損失は dyn/cm²、`K_s` は流向別の係数。流量は枝の両端で逆符号で節点収支に入り、壁流と放射を伴う節点圧が次に進む。上流の狭窄試験は1セルと1/4セル相当の狭窄で、定常流量がベルヌーイ近似から15%以内に収まることを確かめる。 [上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L923)・[研究版の枝更新](../crates/vocal-core/src/airway/network.rs#L189)・[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

## 圧力源の逆算と位置の比較

基準波形の末尾22周期に対して、110 Hzの複素係数だけを倍率−1、−0.5、0、+0.5、+1で変える。口端流量のフーリエ係数を `Y(a)` とすると、奇成分は `(Y(a) − Y(−a))/2`、偶成分は `(Y(a) + Y(−a))/2 − Y(0)`。比例・二次のずれはそれぞれ半振幅の奇成分を2倍、偶成分を4倍した値から全振幅の値を引く。指定周波数では入力差がほぼゼロなので、この複素差を枝損失の変化から再構成できる。

線形化した離散節点方程式に、幾何と流量から計算した枝損失、または隣接節点の圧力から慣性と粘性を引いて得た枝損失を圧力源として与える。逆流補正は全条件が逆流する標本と条件間で流向が異なる標本に分ける。寄与は口端の複素差の方向へ射影するので、負の寄与と100%を超す寄与が同時にありうる。枝は両版で向き付き端点を照合し、比較表では管名と咽頭入口セルの中心から枝境界までの距離も使う。 [固定 /i/ の姿勢の基準](../cases/fixed-voice-centerline-i.json)・[線形要素の保存実行](../runs/vowel-transfer-i-20261119-f/manifest.json)・[計測コード](../tools/measure_fixed_vowel_i_lf_branch_loss.py)・[節点方程式](../tools/measure_fixed_alpha_branch_loss.py)

## 実測

全4比較で口端のずれの寄与上位3枝が口腔の34→35、35→36、33→34に移った。枝境界は咽頭入口から9.30〜10.25 cm。/ɑ/ の上位3枝は咽頭の26→27、25→26、17→18だった。/i/ では3枝の寄与を口端差の方向に射影した合計が52.24〜60.96%。流向が条件間で異なる標本の逆流補正は99.30〜99.92%を占めた。上位3枝に口腔枝が入る事前予測と、流向反転が過半を占める事前予測はともに満たした。 [周波数別の要約](../runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/summary.json)・[枝別の複素寄与](../runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/artifacts/branch-contributions.csv)

| 口端流量の成分 | /ɑ/ のずれの大きさ（cm³/s） | /i/ のずれの大きさ（cm³/s） | /i/ のうち流向反転の補正 |
| --- | ---: | ---: | ---: |
| 660 Hz、奇成分の比例からのずれ | 1.272×10⁻⁴ | 6.773×10⁻⁵ | 99.30% |
| 660 Hz、偶成分の二次からのずれ | 1.603×10⁻⁴ | 8.355×10⁻⁵ | 99.84% |
| 770 Hz、奇成分の比例からのずれ | 2.389×10⁻⁴ | 9.097×10⁻⁵ | 99.74% |
| 770 Hz、偶成分の二次からのずれ | 3.333×10⁻⁴ | 6.810×10⁻⁵ | 99.92% |

両版の時系列は各系列の最大値に対して相対4.16×10⁻¹³以内。口端の複素差の再構成誤差は、幾何と流量による損失で相対5.84×10⁻¹¹以内、観測圧力から逆算した損失で1.68×10⁻¹¹以内だった。最初の圧力差は標本76,800の咽頭入口（節点13）、最初の枝流量と圧力残差の差は76,801の枝13→14だった。 [時系列の判定](../runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/summary.json)

## 最も狭い位置と寄与の最大点

慣性が最大の枝37→38は最狭部に隣接し、セルの最小面積は0.5044・0.5016 cm²。寄与が最大の34→35では0.9928・0.6894 cm²で、狭窄に近づく側の面積差が大きい。保存した上流の観測から770 Hzの偶成分のずれを分解したところ、二次損失の残差は34→35で7.188×10⁻⁴ dyn/cm²、37→38で4.790×10⁻⁶ dyn/cm²だった。両枝から口端への線形応答の大きさはそれぞれ0.02324・0.02303 cm³/s/(dyn/cm²)。最大寄与の位置は、枝損失の圧力源におよそ150倍の差が生じたことと対応する。 [上流の節点幾何](../runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/artifacts/upstream-geometry.csv)・[枝別の複素寄与](../runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/artifacts/branch-contributions.csv)

次は34→35と35→36の平滑化を事前登録する。条件間で流向が分かれる標本の絶対流量は両枝とも49 cm³/s未満だった。既存の幅60 cm³/sで、定常流を保ちながら、元の流量に新しい損失式を適用した予測が再描画を説明するか比較する。 [既存の平滑化](fixed-alpha-lf-fundamental-smoothed-branches.md)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で研究ワークスペースから実行した。再実行は `/tmp` から同じ Python とスクリプトを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_lf_branch_loss.py fixed-vowel-i-lf-branch-loss-20261124-registered
```

両実行で26判定と上流の狭窄試験に通過した。固定 /ɑ/ の保存観測も共通の解析で再集計し、元の要約と枝別CSVに一致した。両実行でバイト一致した圧縮観測とケースなど計15成果をRTL9210B-CG上でハードリンクにまとめ、元の実行別パスからそれぞれのマニフェストと同じSHA-256で読めることを確認した。 [初回のマニフェスト](../runs/fixed-vowel-i-lf-branch-loss-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/manifest.json)

第26版の全体監査で今回の要約と枝別CSVを再構成し、独立した2実行と第25版の判定を照合した。169実行・2,848成果・357判定に通過した。 [第26版の監査](../runs/plan-completion-v26-fixed-vowel-i-lf-20261124/manifest.json)
