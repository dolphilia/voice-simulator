# 混合体型の口端放射負荷に最初の差が入る箇所

通常レベルで口端流量に最初の差が生じた内部サンプル50,049を調べた。固定上流と研究版で休止舌先、音源の変動0、体型ゲインをそろえ、両版の終端セルが実際に読む入力と、更新後の口端流量を比較する。[事前登録](../cases/duet-mixed-lip-load-origin.json)・[放射の成分別比較](duet-mixed-radiation-origin.md#実測)

## 読解と予測

- 上流CLIの `render::notes` は歌唱のジェスチャーを `HumanVoice` に渡し、内部96 kHzで `AirwayNetwork::step` を進める。混合体型は先行実行と同じ歌唱観測器から指定する。気道の1ステップは、断面の更新とセル体積の変化から生じる流量、接続枝の流量、壁の運動の順に収支を作り、終端で圧力と放射流量を更新する。研究版の `ArticulatedVoice` と `AirwayNetwork` も通常の歌唱CLIから同じ更新経路を通る。口端の圧力（dyn/cm²）、慣性枝と節点への流量（cm³/s）、力学的なコンプライアンス（cm⁵/dyn）、放射抵抗（dyn·s/cm⁵）と慣性（g/cm⁴）を採る。[上流の歌唱入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[上流の内部更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の終端処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[研究版の気道更新](../crates/vocal-core/src/airway/network.rs#L675)
- 上流の口端放射は並列の抵抗 `R` と慣性 `L` を終端セルのコンプライアンス `C` と中点で結合する。慣性が増えた場合は、更新前の慣性枝流量に古い慣性と新しい慣性の比を掛ける。計測する `U₀` はその補正後の値。中点圧力を `P_m`、更新前圧力を `P₀`、終端セルへの正味流入を `I` とすると、圧縮と放射の収支から `(2C/Δt + 1/R + Δt/(2L))P_m = 2C P₀/Δt + I − U₀` が得られる。新しい節点圧力は `2P_m−P₀`、慣性枝は `U₀+Δt P_m/L`、放射流量は `U₀+(1/R+Δt/(2L))P_m`。実装の新しい圧力を直接求める式と同じ離散化を、中点圧力から十進多倍長で解き直す。[上流の放射負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1117)・[研究版の放射負荷](../crates/vocal-core/src/airway.rs#L78)
- 直前の放射成分が0だったため、初出点の更新前圧力と慣性枝流量も0で、流入か幾何に依存する負荷値に差が出ると予測した。入力を片側から入れ替えた場合と逆順で入れ替えた場合の平均を取り、流入とそれ以外の入力の寄与を求める。実測差から高精度の計算差を引いた残りで、実装の演算順序や丸めの寄与を評価する。上流試験は一様管の共鳴・非一様管の安定性・ブロック分割、研究版は壁放射と一様管の動作を確認する。[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[上流のエンジン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[研究版の一様管試験](../crates/vocal-core/tests/uniform_tube.rs)

## 再現

両版ともRTL9210B-CGの一時ディレクトリにソースを展開し、口端負荷の計測差分を適用する。断面更新後、枝更新後、壁更新後の流入を分けて採り、並列負荷を解いたことを示す列と実際の入力・出力を内部サンプル50,033〜50,080で保存する。放射負荷を解かなかった行は `solved=0` とする。通常CLIと前回の保存PCM全97,920フレーム、および先行実行の口端流量系列に照合する。研究版の通常CLIと固定上流の参照チェックアウトは無変更で比較に使う。[計測CLI](../tools/measure_duet_mixed_lip_load_origin.py)・[研究版の計測差分](../tools/patches/candidate-duet-lip-solve.patch)・[固定上流の計測差分](../tools/patches/upstream-duet-lip-solve.patch)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_mixed_lip_load_origin.py duet-mixed-lip-load-origin-new
```

## 実測

内部サンプル50,049の更新前圧力と慣性枝流量は両版とも0だった。最初の正味流入は研究版 `1.4390788387843876×10⁻⁴ cm³/s`、固定上流 `1.4390788387827504×10⁻⁴ cm³/s`。差 `1.63715×10⁻¹⁶ cm³/s` は断面更新後の時点ですでにあり、そのステップでは枝と壁の更新を通して流入値が変化しなかった。口端の面積・セル長・コンプライアンス・抵抗には直前から微小差があった。[独立計算と採取値](../runs/duet-mixed-lip-load-origin-20261122-repeat/summary.json)

| 50,049での口端流量差（研究版 − 上流） | cm³/s |
| --- | ---: |
| 実測 | +4.686464×10⁻¹⁷ |
| 流入の寄与 | +4.690032×10⁻¹⁷ |
| コンプライアンス・抵抗・慣性などの寄与 | −3.512838×10⁻²⁰ |
| 実測から中点式での再計算を引いた残差 | −5.517999×10⁻²² |

各版とも独立計算による48点の口端流量再現誤差は `1.43×10⁻¹⁷ cm³/s` 未満だった。初出点に限ると、観測した両版の流入差を入れると口端流量差のほぼ全量を説明できた。放射負荷を解く時点で実測に残る丸め差は上表のとおりだった。

追加の解析では、50,048と50,049の断面積とセル長から、先に倍精度でそれぞれの体積 `Aℓ` を計算した。体積減少の両版差は `1.1102230246251565×10⁻¹⁶ cm³` で、体積0.6256 cm³付近のFloat64の1刻み分に相当する。これを96 kHzの時間差分にし、60 Hzの1次平滑器2段を初期値0から同じ順序で適用すると、採取した断面更新後の流入を両版ともビット一致で再現できた。同じ断面積とセル長から積を丸めずに体積差分を計算する対照では、流入差は `1.90×10⁻¹⁹ cm³/s` だった。この初出点では、流入差は小さな幾何の差が体積の丸めを経て現れたものと説明できる。代替の体積差分を実際のレンダーに通したときの影響は未検証。[体積の予備計算](../runs/duet-mixed-lip-load-origin-20261122-repeat/summary.json)・[研究版の体積流量と平滑化](../crates/vocal-core/src/airway/network/geometry.rs#L130)・[上流の体積流量と平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L868)

初回は口端の観測を終えた後、先行系列を読み込む関数のインポート漏れで停止した。採取物を元のパスへ公開し、停止理由と16出力のSHA-256を記録した。読み込みを直した段階の9出力は初回の対応する出力と一致した。[初回の停止記録](../runs/duet-mixed-lip-load-origin-20261122-a/failure.json)・[修正後](../runs/duet-mixed-lip-load-origin-20261122-b/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/private/tmp` から各6判定・3予測、研究版3試験と固定上流9試験が通過した。10出力がバイト一致し、通常CLIと保存済みの両版のPCM全97,920フレームへの照合も通過した。独立した厳密分数計算でも、初出点の流入寄与と丸め残差を照合した。成功した3実行の447入力と、初回の保全分を含む4実行の67出力をサイズとSHA-256で照合し、採取物14,568,725バイトをRTL9210B-CGに保存した。[最終実行](../runs/duet-mixed-lip-load-origin-20261122-final/manifest.json)・[再実行](../runs/duet-mixed-lip-load-origin-20261122-repeat/manifest.json)

後続の比較では、体積差の展開式を研究版の通常CLIで実行し、初出点の流入を独立計算で再現した。後続224点の局所流量の誤差、全区間のPCM、閉鎖・再開口と密閉圧縮への影響も照合した。[体積差の展開式を使った実測](duet-mixed-volume-difference.md#実測)
