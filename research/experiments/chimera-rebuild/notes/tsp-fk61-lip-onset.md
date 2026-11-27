# FK61_01の最初の口端流量差

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。同じ女性体型、英文、辞書、発話設定で描画する。[測定の事前登録](../cases/tsp-fk61-lip-onset.json)・[前回の放射とPCMの照合](tsp-fk61-pcm-first-difference.md)

## 読解

固定上流の通常入口は `chimera render text … female --float`。英文のスコアを `HumanVoice` に渡す。`HumanVoice::render` は48 kHzの出力1標本を96 kHzの2標本から作る。`ctrl_counter` が0のとき、`control` がスコアを現在時刻で混合し、調音器と気道を更新してから `AirwayNetwork::begin_block` に繋ぐ。`begin_block` は口端を含む各節点で現在値と目標値の差を128で割って、平均面積・最小面積・長さの各増分を求める。そのブロックの最初の内部標本から `AirwayNetwork::step` が増分を加える。[上流のCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs)・[上流の発話器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L372)・[上流の補間と気道の解法](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L707)

研究版の通常入口は `vocal-cli render-pcm`。`ArticulatedVoice::step_with_glottal_pressure` は制御周期の先頭で姿勢を進め、`TractController::apply` から得た統合目標を `HumanAirway::begin_tract_block` に渡す。内部標本の処理は `FixedVoice::step_source` から `AirwayNetwork::step_with_prescribed_flow`、`MovingAreas::step` へ進む。`set_targets` が各増分を保存し、`step` が現在値を1標本進める。下限 `A_floor` を使ってセル体積を `max(A, A_floor) × length` [cm³] とし、`(V_old − V_new) / dt` [cm³/s] を体積流量にする。固定上流は `−(V_new − V_old) × 96000` として計算する。[研究版の発話器](../crates/vocal-core/src/voice.rs#L589)・[研究版の気道](../crates/vocal-core/src/airway/network.rs#L675)・[移動する断面](../crates/vocal-core/src/airway/network/geometry.rs#L110)

最小面積が0.12 cm²を下回るセルでは、閉じ具合に応じて体積流量の一部を開いている近隣にも配る。各セルに届いた押し出しの合計 `spill` [cm³/s] に対し、`s₁ ← s₁ + α(spill − s₁)`、`s₂ ← s₂ + α(s₁ − s₂)` を順に適用する。係数は `α = 1 − exp(−2π·60·dt)`。枝の流量を足し引きし、壁への流量を引いた口端節点の収支と、旧圧力 [dyn/cm²]・放射慣性側の旧流量 [cm³/s]・コンプライアンス・放射抵抗・慣性を使ってR–L終端を解く。出力の口端流量は終端の抵抗側と慣性側の中点流量の和。[上流の体積流量](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L836)・[研究版の体積流量](../crates/vocal-core/src/airway/network/geometry.rs#L122)・[R–L解法の独立計算](../tools/measure_fixed_voice_release_lip_load.py#L100)

上流の `airway_adversarial` にはセルの圧縮で密閉空洞の圧力が体積比に応じて変わる対照があり、`airway` には一様管の共鳴・周波数領域解との照合がある。研究版の `geometry_ramp` は長さと開口の補間が同じ標本で進むことを確かめる。今回の試験では同一発話の起動区間に観測を挿入し、これらの量を一つの時間軸で照合する。[上流の圧縮テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L54)・[上流の気道テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[研究版の補間テスト](../crates/vocal-core/tests/geometry_ramp.rs)

## 実測

0始まりの内部標本3952〜3979を採取した。最初の口端流量差は128標本の制御更新の境界3968で生じた。直前の圧力、放射慣性側の流量、2段の低域通過フィルターの状態は両実装とも0だった。[初回の時系列と判定](../runs/tsp-fk61-lip-onset-20261123/summary.json)

| 標本3968の値 | 固定上流 | 研究版 |
|---|---:|---:|
| 更新前の面積 [cm²] | 1.3749486460641938 | 1.3749486460641942 |
| 更新後の面積 [cm²] | 1.3749485339887353 | 1.3749485339887357 |
| 更新後の長さ [cm] | 0.4667781147791914 | 0.4667781147791914 |
| 更新前後の体積差 [cm³] | 3.8480166386634096×10⁻⁸ | 3.84801664976564×10⁻⁸ |
| 体積差分からの流量 [cm³/s] | 0.003694095973116873 | 0.0036940959837750142 |
| 平滑化後の流量 [cm³/s] | 5.6744403279102334×10⁻⁸ | 5.6744403442820296×10⁻⁸ |
| 口端の放射流量 [cm³/s] | 1.614853805056832×10⁻⁸ | 1.6148538097159804×10⁻⁸ |

口端セルの最小面積は約1.227 cm²で、各セルの体積流量を配分した後の口端流量は、口端セル自身の生の体積流量と一致した。枝と壁の更新前後で口端の収支は変わらず、平滑化後の量がそのまま終端に入った。元の抵抗・慣性などを使い、平滑化後の流量だけ交換すると、相手側の口端流量を両方向とも1 ULPの差まで再現した。事前登録した2仮説はいずれも成立した。[比較の計算と時系列の仕様](../tools/measure_tsp_fk61_lip_onset.py)

実測後に、観測した倍精度の面積と長さを有理数に変換し、中間の積を丸めずに体積差分を計算した。生の流量の研究版−固定上流は約−4.29×10⁻¹⁹ cm³/sだった。倍精度の積を保存してから引くと、体積差分が1.11×10⁻¹⁶ cm³異なり、流量差は約+1.07×10⁻¹¹ cm³/sになった。同じ体積差分で `×96000` と `÷(1/96000)` を切り替えても、この標本では同じ倍精度値になった。体積の積を個別に丸めると、次の差分に丸め誤差が現れる。[丸めの独立計算を含む再実行](../runs/tsp-fk61-lip-onset-20261123-repeat/summary.json)

口端の断面差は比較区間の開始時点で既に存在していた。この断面差の上流側での発生箇所と、体積差分の式を変えたときの発話全体への影響は未測定。次の最小ケースは、保存した変化前後の断面を固定したまま、`A_old L_old − A_new L_new` を `(A_old − A_new)L_old + A_new(L_old − L_new)` に置き換え、3968での高精度値への接近と平滑化・口端流量を調べる。低断面では体積に使う下限を適用した面積を使う。

## 再実行

研究ワークスペースで新しい実行IDを指定する。通常CLIと試験用のRustビルドはRTL9210B-CGに一時出力し、PCM本体は保存済みのものを参照する。口端の28標本の観測、照合用PCMハッシュ、試験ログを残す。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` の2実行は、要約、列定義、PCMハッシュ、各実装の時系列の5出力がバイト一致した。実行コマンドと入力・出力ハッシュをマニフェストから確認できる。 [初回](../runs/tsp-fk61-lip-onset-20261123/manifest.json)・[試験を含む実行](../runs/tsp-fk61-lip-onset-20261123-verified/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-fk61-lip-onset-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_lip_onset.py tsp-fk61-lip-onset-new
```
