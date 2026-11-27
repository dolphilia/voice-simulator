# 混合体型の放射差とその成分

通常レベルの混合体型で休止舌先、音源変動0、体型ゲインをそろえても、固定上流と研究版の間で25,025出力フレームの1点目に微小な放射差が残った。同じ入力を使い、出力段に入る前の口端・鼻端・声道壁の流量と、その和の時間差分を内部96 kHzで照合する。[事前登録](../cases/duet-mixed-radiation-origin.json)・[出力ゲインの実測](duet-mixed-output-gain.md#実測)

## 読解と予測

- 固定上流の `render::notes` は譜面をジェスチャーに展開して `HumanVoice` に登録する。混合体型は先行する観測器の入力から指定する。`HumanVoice::render` は声門面積と肺圧を気道に渡し、`AirwayNetwork::step` を2回呼ぶ。研究版は通常CLIの `run_song` から同じコアを使い、`VoiceSample` に口端・鼻端流量と `NetworkSample` の壁流量・総流量・時間微分を返す。計測はそれぞれのソルバーをそのまま進め、総流量を更新した直後の値を採る。[上流の歌唱入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[研究版の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L260)・[研究版の内部出力](../crates/vocal-core/src/voice.rs#L229)
- 気道は枝流量を更新した後、節点の圧力から壁面速度と変位を進め、壁面積と速度を掛けた体積流量を各節点の収支から引く。壁からの放射には咽頭・口腔の壁流量をそれぞれ0.25倍して加える。続いて口端と鼻端では、節点圧力と放射負荷の並列抵抗・慣性を連立して新しい圧力と流量を求める。放射負荷の流量は、慣性枝の新旧流量の平均と抵抗枝の流量の和。開口が閉じた場合は慣性枝の流量を減衰させる。総流量（cm³/s）は壁・口端・鼻端の和、その時間微分（cm³/s²）は直前の総流量との差を内部周期で割った値。総流量が毎ステップ丸められるため、各成分の差分を取って足すと、総流量を先に足した実装と微小な差が生じ得る。[上流の壁と放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[上流の放射荷重の位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L162)・[研究版の壁・放射と差分](../crates/vocal-core/src/airway/network.rs#L747)
- 軟口蓋が閉じた初出点では鼻端の流量が0で、口端または壁成分に差が出ると予測した。総流量とその時間微分を先に照合し、成分間の相殺や総和の丸めを別に記録する。固定上流の `airway` は時間・周波数領域の共鳴と狭窄での安定性を、`engine` はホスト分割と安定性を確認する。研究版の `wall_radiation_weights_output_without_changing_acoustic_state` は壁放射の重みが出力にだけ現れることを確認する。[上流の気道の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[上流の描画試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[研究版の壁放射試験](../crates/vocal-core/tests/uniform_tube.rs#L32)

## 再現

通常CLIは既存の `render-pcm` を使う。両版の観測器は内部サンプル先頭50,304点の口端・鼻端・壁・総流量、時間微分と軟口蓋の枝面積を記録する。固定上流の場合は、作業用に展開したソースに壁流量と総流量を採る差分を適用する。PCMは全97,920フレームを通常CLIと先行実行に照合する。解析では `math.fsum` による独立な合算と、独立した時間差分を使う。出力フレームと内部サンプルは1起算で、出力フレーム25,025内の内部サンプルは50,049・50,050。数値差の初出は絶対差0を基準に調べる。[計測CLI](../tools/measure_duet_mixed_radiation_origin.py)・[固定上流への計測差分](../tools/patches/upstream-duet-child-output-stage.patch)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_mixed_radiation_origin.py duet-mixed-radiation-origin-new
```

## 実測

最初に異なった成分は口端流量で、内部サンプル50,049（出力フレーム25,025）だった。直前は両版とも全成分が0。初出点での口端流量は研究版 `4.122618654589623×10⁻⁵ cm³/s`、固定上流 `4.1226186545849366×10⁻⁵ cm³/s` で、差は `+4.68646×10⁻¹⁷ cm³/s`。この1ステップの流量差から得た時間微分の差 `+4.499005×10⁻¹² cm³/s²` は、実測の差 `+4.499068×10⁻¹² cm³/s²` と `6.25×10⁻¹⁷ cm³/s²` 未満の差で一致した。この点では鼻端と壁が両版とも0なので、差は口端の流量ですでに生じていた。[初出点と前後の値](../runs/duet-mixed-radiation-origin-20261122-a/summary.json)

壁成分は次の内部サンプル50,050で初めて差が出た。鼻端と軟口蓋枝面積は採取した全50,304点を通じて0だった。観測窓の成分別の時間微分差は、口端の最大 `2.47×10⁻⁹ cm³/s²` に対し壁は `3.80×10⁻¹¹ cm³/s²`。両実装とも独立に合算した総流量は記録値と一致し、時間差分の再計算の最大誤差は `4.55×10⁻¹³ cm³/s²` 未満だった。口端への流入、節点圧力、放射負荷の係数のどこが先に変わったかは次の比較で測る。[研究版の成分系列](../runs/duet-mixed-radiation-origin-20261122-a/artifacts/candidate-radiation.csv)・[固定上流の成分系列](../runs/duet-mixed-radiation-origin-20261122-a/artifacts/upstream-radiation.csv)

後続の計測では、最初の口端流量差を作る流入差は断面更新後にすでに生じていた。セル体積の時間差分と60 Hzの平滑化から、両版の初出点の流入を再現した。[口端放射負荷の追試](duet-mixed-lip-load-origin.md#実測)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/private/tmp` から各5判定、3予測、研究版3試験と固定上流9試験が通過し、8出力がバイト一致した。標準ライブラリで全50,304点を再読込し、先行の内部放射と合算を照合してから、初出点の成分差を多倍長の十進演算でも再計算した。先行のピーク制限の回帰は9判定と固定上流10試験に合格し、28出力が一致した。3実行の435入力・66出力をサイズとSHA-256で照合し、採取物56,128,036バイトをRTL9210B-CGに保存した。[初回](../runs/duet-mixed-radiation-origin-20261122-a/manifest.json)・[再実行](../runs/duet-mixed-radiation-origin-20261122-repeat/manifest.json)・[ピーク制限の回帰](../runs/duet-mixed-limiter-gain-order-20261122-radiation-regression/manifest.json)
