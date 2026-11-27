# 子ども声部の初期舌先と無発声時の過渡

子ども体型のデュエットで音源の変動設定をそろえても、歌唱前の断面積・流量に差が残った。今回は固定された歌唱の研究版ケースから舌先の初期座標だけを変更する。準備開始前と最初の512出力サンプルを観測する。[事前登録](../cases/duet-child-initial-tip.json)・[声門乱流の先行計測](duet-child-glottal-noise-origin.md)

## 読解と予測

- 上流の通常CLIは `HumanVoice::new` を呼ぶ。`ArticulatorBank::new` は中立姿勢で自由舌先を有効にし、舌先の位置と目標を `rest_tip` に置く。その状態で `HumanAirway::apply(…, 0)` を呼び、`snap_to_targets` で断面・体積を初期化する。研究版の `run_song` はケースの姿勢を `ArticulatorBank::new` に渡す。舌先は指定位置・速度0で気道を初期化し、最初の `step` で休止位置を目標に設定する。指定位置が休止位置と異なると、初期形状と最初の制御後の形状が異なる。[上流の初期調音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L79)・[上流の気道初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L274)・[研究版の調音初期化](../crates/vocal-core/src/articulators.rs#L208)・[研究版の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L260)
- 休止位置は基準座標で `(-2.5, 10.5)` cmを中心に `(6.45, 7.35)` cmを `−jaw/9.84` rad回し、舌体位置の中立値からのずれをx・y方向に0.30・0.35倍だけ足す。この中立姿勢の舌体補正は0。制御周期 `Δt=64/48000` 秒ごとに角周波数 `ω=2π×13` を使い、速度に `Δt(ω²(T−x)−2ωv)` を足してから、新しい速度で位置を進める。位置と速度の単位は基準座標のcm、cm/s。固定上流の `geometry_continuity` は休止位置を含む断面の推移を、`engine` は発声停止時の挙動と分割不変性を検査する。[上流の休止位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L454)・[上流の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)・[形状連続性の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L119)・[エンジンの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)
- 研究版はこの調音姿勢から得た断面を128内部サンプルで線形補間する。セルの体積 `V = Aℓ` が動くと `−ΔV/Δt` の流量を配分・平滑化して圧力更新へ渡す。ゲート0でも初期の姿勢が動けば流量と放射が生じるため、舌先を休止位置から始めたときの物理量とPCMを比べる。[研究版の形状更新](../crates/vocal-core/src/voice.rs#L588)・[面積更新と体積源](../crates/vocal-core/src/airway/network/geometry.rs)・[上流の断面初期化と補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L686)

## 実測

固定上流の初期舌先は `[6.241412821929657, 6.810460479056529] cm` で、独立計算と一致した。研究版のケース値 `[6.45, 7.30] cm` からは、最初の制御更新で `[6.44752593262018, 7.294193536865] cm` に動いた。最初の8制御周期で採取した位置・目標・速度は独立した差分式と一致し、最初の64出力サンプルの断面積は端点間の線形補間と一致した。休止位置を初期値にした条件は両実装とも舌先が静止した。[時刻別の実測](../runs/duet-child-initial-tip-20261122-a/summary.json)

| 描画前と最初の512出力サンプルの比較 | 元の舌先と固定上流の最大絶対差 | 休止位置から始めた研究版と固定上流の最大絶対差 |
| --- | ---: | ---: |
| 唇端の断面積（cm²） | 0.001125898 | 7.77×10⁻¹⁶ |
| 咽頭先頭の断面積（cm²） | 1.90×10⁻⁵ | 0 |
| 声門流量（cm³/s） | 0.00509187 | 0 |
| 放射流量の時間微分（cm³/s²） | 3927.64 | 0 |
| PCM絶対値 | 0.00145577 | 0 |

描画開始前から元のケースの断面積に差があり、最初の制御更新で舌先の移動と断面積の補間が始まった。その後にゲート0のまま声門流量と放射が発生した。休止位置にそろえると、この観測区間では両実装とも流量・放射・PCMが0になった。ゲートと乱流レベルは全条件で0。研究版で設定を変えたのは計測用ケースの `song_voice.posture.tongue_tip_cm` のみ。元のケースと両観測器の生成したジェスチャーは先行結果にそれぞれ一致した。[元の姿勢の時系列](../runs/duet-child-initial-tip-20261122-a/artifacts/case_tip-startup.csv)・[休止位置の時系列](../runs/duet-child-initial-tip-20261122-a/artifacts/resting_tip-startup.csv)

全91,200フレームのPCMには体型別ゲインを含む差が残る。探索的に保存済みの上流PCMを上流の子ども体型係数0.875で割ると、休止位置をそろえた研究版との最大差は0.0472802から `2.98×10⁻⁸` になった。出力段の入力に同じゲインを指定する比較で、丸めを含めて再確認できる。[全区間の候補PCM](../runs/duet-child-initial-tip-20261122-a/artifacts/resting_tip-pcm.f32le)・[全区間の上流PCM](../runs/duet-child-initial-tip-20261122-a/artifacts/upstream-pcm.f32le)・[上流の体型別ゲイン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L280)

後続の実行で、間引きの直後に子ども体型の係数0.875を適用すると、全区間の上流とのPCM最大絶対差は `9.09×10⁻¹³` になった。両版とも、この歌唱ではリミッターは作動しなかった。[出力ゲインを変えた計測](duet-child-output-gain.md)

混合体型でも同じ基準座標に舌先を置くと、最初の512サンプルで流量・放射・PCMが0になった。混合体型では、元の舌先から始めても咽頭先頭の断面積差はなく、初期形状差は測定した2点のうち唇端に現れた。[混合体型の追試](duet-mixed-initial-tip.md#実測)

## 再現

研究ワークスペースから実行する。固定上流を展開した作業領域と採取物はRTL9210B-CGに置く。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_child_initial_tip.py duet-child-initial-tip-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。初回と `/private/tmp` からの再実行で各10判定と3予測が成立し、固定上流は各11試験に合格した。形状連続性のうち下唇を突き出した姿勢から戻す1試験は上流で既知の断面積の段差により除外設定されている。両実行の要約・ケース・時系列・計画・音声を含む20出力がバイト一致し、保存CSVとPCMから複素数の回転式、最初の制御更新、流量・放射・PCMが0の区間を別に照合した。先行する乱流比較も11判定と固定上流10試験が通過し、以前の保存結果と27出力がバイト一致した。[初回](../runs/duet-child-initial-tip-20261122-a/manifest.json)・[再実行](../runs/duet-child-initial-tip-20261122-repeat/manifest.json)・[乱流比較の回帰](../runs/duet-child-glottal-noise-origin-20261122-tip-regression/manifest.json)

3実行の431入力と85出力のサイズとSHA-256を照合した。採取物81,090,980バイトはRTL9210B-CGに保存し、内蔵側からのリンク先と一時展開先の後片付けを確認した。
