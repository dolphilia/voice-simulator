# FK61_01の口腔体積源を断面積とセル長に分ける

[口腔16節点の比較](tsp-fk61-control5632-oral-inlet.md#実測)で、5863の枝37→38の流量差に節点28〜37の体積源が大きく効いた。体積源の単独交換では節点34の影響が最大だった。今回は制御境界5632・5760の目標を採り、断面積とセル長のどちらの変化が節点34の体積速度に伝わったかを調べる。比較は女性設定のFK61_01、内部96 kHz、出力48 kHz。節点と標本は0始まり。

## 調音目標から体積流量まで

通常の `render text` は英語の発話計画を `HumanVoice` に渡す。各制御境界で `HumanVoice::control` が姿勢を更新し、`HumanAirway::apply` が形状を計算する。舌の接触補正が入る場合は `reapply` で目標を再設定してから `AirwayNetwork::begin_block` が増分を確定する。上流の `HumanVocalTract::resample` は声道の弧長を咽頭と口腔に分け、代表断面積を各セル内8点の調和平均から求める。最小面積は別に採り、閉鎖の判定と配分に使う。解剖学的な口腔長は唇までの弧長から分岐位置の弧長を引いたもの。長さが音速と刻みで決まる安定条件を下回るときは、計算上の管を伸ばす。 [通常CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[制御と接触補正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L495)・[断面の再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[計算上の口腔長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L310)

`set_tube_targets` が計算上の口腔長を16等分し、全セルの長さ目標を設定する。各セルの代表面積・最小面積・長さについて、現在値を \(x_0\)、目標を \(x_t\)、内部標本数を \(N\) とすると、ブロック開始時の増分は \(\delta x=(x_t-x_0)(1/N)\)。各標本でその増分を直前の値に加え、断面積と最小面積を許容範囲に収める。この発話の \(N\) は128。研究版も `begin_tract_block` から `set_geometry_targets`、`MovingAreas::set_targets` の順で増分を作る。 [上流の目標と増分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L647)・[研究版の口腔目標](../crates/vocal-core/src/airway/human.rs#L341)・[研究版の補間](../crates/vocal-core/src/airway/network/geometry.rs#L47)

```mermaid
flowchart LR
    A["調音姿勢と接触補正"] --> B["断面積と計算上の口腔長"]
    B --> C["制御境界で面積・長さの増分を設定"]
    C --> D["毎標本でセル体積を更新"]
    D --> E["体積速度を開口状態に応じて配分"]
    E --> F["二段平滑して節点に加える"]
```

面積 \(A\) は cm²、長さ \(L\) は cm、体積 \(V=\max(A,A_{\min})L\) は cm³。\(A_{\min}\) は体積がゼロになることを防ぐ下限で、幾何として採るセル内最小面積とは別の定数。正の体積速度は収縮を表す。固定上流は \((V_{n-1}-V_n)\Delta t^{-1}\)、研究版は \((V_{n-1}-V_n)/\Delta t\) を用いる。単位は cm³/s。狭いセルで近隣へ配分した後、60 Hzの一極平滑を二段通す。前の丸め済み体積と二つの平滑状態が次標本の入力になる。 [上流の更新と配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L832)・[研究版の体積速度と平滑](../crates/vocal-core/src/airway/network/geometry.rs#L104)

通常CLIと隔離ビルドのPCMを全発話で照合する。上流の一様管、密閉空洞圧縮、閉鎖移動と再開口の試験と、研究版のポート即時更新と他の形状補間の併存試験を使う。観測器は最後に採取した目標を使い、実際の開始状態から増分を計算し、加算後の断面積・最小面積・セル長を照合する。 [上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[上流の閉鎖試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 交換条件

目標と増分は5632・5760、更新前後の系列は5630〜5875を観測する。体積源の再計算は5632〜5875。5631の交換後形状を初期体積とし、二つの平滑状態は試験版から始める。節点34のみと節点28〜37の各範囲で、無交換・面積のみ・長さのみ・両方を比較する。枝、壁、コンプライアンス、乱流圧を試験版のままにして、咽頭流入が試験版と固定上流の場合を測る。体積の積を丸めない分数計算で、面積の変化、長さの変化、交互作用を区別する。口端流量を全区間戻したときの出力をPCM 2937まで比較する。 [事前登録ケース](../cases/tsp-fk61-control5632-oral-geometry.json)・[計測器](../tools/measure_tsp_fk61_control5632_oral_geometry.py)

## 実測

5632の口腔セル長は更新直前まで同じだった。上流の長さ目標は試験版より +1.110×10⁻¹⁶ cm、増分は +8.674×10⁻¹⁹ cm 大きく、最初の加算後の長さが1 ULP分かれた。5760では長さ目標の差が +2.220×10⁻¹⁶ cm、開始時の長さの差が +7.105×10⁻¹⁵ cm だった。増分差は −5.378×10⁻¹⁷ cm に反転した。両境界で、管の長さの差は解剖学的な長さの時点で現れ、計算上の長さを安定条件で伸ばす処理は働かなかった。全16節点が同じ長さ目標を共有した。 [採取した目標と増分](../runs/tsp-fk61-control5632-oral-geometry-20261123-repeat/summary.json)

| 節点34の内部標本 | 断面積だけ交換した体積速度の変化（cm³/s） | 長さだけ交換した体積速度の変化（cm³/s） | 両方を交換した変化（cm³/s） |
| ---: | ---: | ---: | ---: |
| 5632 | −1.995×10⁻¹¹ | −1.682×10⁻¹¹ | −3.678×10⁻¹¹ |
| 5760 | +1.995×10⁻¹¹ | +1.682×10⁻¹¹ | +3.677×10⁻¹¹ |

これは積を丸めない計算。交互作用は両標本とも絶対値7×10⁻²⁵ cm³/s未満だった。全16節点の最小面積は観測窓を通じて配分の閾値以上だった。節点34単独で長さの寄与が面積より大きいという予測は棄却した。節点28〜37をまとめて交換し、5863の枝37→38で比較すると、長さだけで −1.678×10⁻¹¹ cm³/s、面積だけで −1.950×10⁻¹² cm³/s 動いた。長さを揃えた効果は約8.6倍で、観測した流量差の約73%に相当した。 [交換結果と保存系列](../runs/tsp-fk61-control5632-oral-geometry-20261123-repeat/summary.json)・[状態軌道](../runs/tsp-fk61-control5632-oral-geometry-20261123-repeat/artifacts/trajectories.npz)

節点28〜37の面積・長さと咽頭流入を揃えても、初差はPCM 2937に残った。変換前の値の変化は +1.234×10⁻¹⁴ で、丸めの境目までの +1.410×10⁻¹⁴ に届かなかった。第84版で交換した体積源には、5632より前の平滑状態の差も含まれていた。追加比較では、試験版の初期値のまま体積速度の乗除順と平滑係数を固定上流へ揃えても、PCM 2937の結果は同じだった。平滑器の二つの初期値を固定上流にすると、試験版と固定上流のどちらの演算設定でも変換前の値が +1.421×10⁻¹⁴ 動き、PCMが冒頭から2937まで一致した。節点34の5863で、両方の形状を交換した後に残った平滑済み流量差 +5.101×10⁻¹³ cm³/s は、初期値を揃えるとゼロになった。 [第85版で再計算した平滑状態の対照](../runs/stage7-evidence-update-20261123-fk61-control5632-oral-geometry/summary.json)

次は5632の一つ前の制御境界5504を採り、5632の平滑開始値の差が前ブロックのどこまでで生じるかを追う。口腔の共通長さを決める唇までの弧長と咽頭端の弧長を個別に採ると、解剖学的な長さ目標の差と、その後の反復加算で広がる差を分けられる。 [上流の弧長と分岐位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1234)・[研究版の弧長と分岐位置](../crates/vocal-core/src/anatomy/area.rs#L131)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。最初の2実行は研究版の隔離ビルドがRustの借用エラーE0502で停止した。観測器が既存の可変参照を保持したまま口腔の範囲を再借用したため、目標配列が持つ参照を使うように修正した。 [初回の失敗](../runs/tsp-fk61-control5632-oral-geometry-20261123-registered/manifest.json)・[二回目の失敗](../runs/tsp-fk61-control5632-oral-geometry-20261123-csv/manifest.json)

修正後、研究ワークスペースと `/tmp` で各4判定とRustの11試験に通過した。3版それぞれで通常CLIと観測版の全116,132フレームおよび先行観測17点が一致した。成功した2実行で採取・軌道・要約の25出力がバイト一致し、採取と軌道はRTL9210B-CGに保存した。 [初回成功](../runs/tsp-fk61-control5632-oral-geometry-20261123-geometry/manifest.json)・[再実行](../runs/tsp-fk61-control5632-oral-geometry-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_control5632_oral_geometry.py tsp-fk61-control5632-oral-geometry-new
```
