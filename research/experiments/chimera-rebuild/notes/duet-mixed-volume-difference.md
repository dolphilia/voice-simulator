# 可動壁の流量をセル体積差の展開から求める

通常レベルの混合体型で見つけた口端流量の微小差について、体積差の式を展開したときの演算誤差とレンダーへの影響を測る。休止舌先、音源の変動0、体型ゲインをそろえた先行入力を固定した。口端負荷の観測を96 kHzの内部サンプル50,033〜50,304へ拡張し、初出点50,049と後続50,081〜50,304を評価する。[事前登録](../cases/duet-mixed-volume-difference.json)・[先行の流入比較](duet-mixed-lip-load-origin.md#実測)

## 読解と予測

上流の `render::notes` は歌唱の計画を生成して `HumanVoice::render` に渡す。`HumanVoice::control` と `HumanAirway::commit` が断面積、最小断面積、管長を目標へ更新し、`AirwayNetwork::set_tube_targets` と `begin_block` がセル単位の補間に変換する。`render` は内部サンプルごとに肺圧、声門のポート面積、`AirwayNetwork::step` の順に更新し、放射の時間差分を間引き・出力段に通す。研究版でも `HumanAirway` の調音更新から `set_geometry_targets` を介して `MovingAreas::step` に入る。[上流の歌唱入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[上流の発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の管の目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L320)・[研究版の調音と管の目標](../crates/vocal-core/src/airway/human.rs#L368)

各セルで補間済みの面積を `A`［cm²］、長さを `ℓ`［cm］とする。体積の計算では `A` を0.02 cm²で下限処理する。基準では倍精度の `Aℓ`［cm³］を前回値として保存し、次の補間後の体積と引き算する。体積の減少を正の流入 `q`［cm³/s］とし、上流は逆時間刻みを掛け、研究版は刻みで割る。狭窄の判定には代表面積と別に補間した最小断面積を用いる。0.12 cm²未満のセルでは滑らかな重みで `q` の一部を開いた近隣へ配り、配り終えた流量を各セルの60 Hz・一次平滑器2段に通す。2段目の値を節点の収支に加えてから枝と壁と放射を更新する。研究版は補間区間が終わっても平滑器の状態を進める。[上流の断面更新と流量源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[研究版の体積下限](../crates/vocal-core/src/airway/network.rs#L30)・[研究版の平滑化](../crates/vocal-core/src/airway/network/geometry.rs#L113)

展開式 `(A旧−A新)ℓ旧 + A新(ℓ旧−ℓ新)` は、各ステップで更新前の面積と長さを読み、同じ体積差を小さな面積差と長さ差から作る。別々に丸めた体積を差し引く場合より、実際に入力された幾何から求めた厳密値に近づくと予測した。この式は面積と長さの寄与が逆符号で打ち消し合う場合にも丸めを含む。合否には観測区間内の最大絶対誤差を使い、静止後の初出点の平滑値を別に再現する。閉鎖と再開口、無放射の密閉圧縮は既存ケースの判定を再利用する。上流の `airway_adversarial` では断熱圧縮の近似、圧力を閉じ込めた状態での再開口、閉鎖を速めたときの圧力上限なども調べている。[研究版の展開差分](../tools/patches/candidate-expanded-volume-difference.patch)・[上流の境界条件テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)

## 再現

基準の研究版と展開式を適用した研究版をRTL9210B-CGの別々の一時ディレクトリに置く。各版で通常の `vocal-cli render-pcm` と `vocal-cli render` を実行してから、過去の口端観測差分を適用する。観測器の出力は同条件の通常CLIに全フレームで照合する。固定上流との比較ではハッシュを確認した先行の口端系列とPCM、および開閉・密閉の時系列を読む。幾何から流量だけを再計算する比較ではPythonの `Fraction` で入力の倍精度値を分数として読み、体積差と時間差分を厳密に計算する。[計測CLI](../tools/measure_duet_mixed_volume_difference.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_duet_mixed_volume_difference.py duet-mixed-volume-difference-new
```

## 実測

| 観測した口端の幾何 | 基準の最大絶対誤差（cm³/s） | 展開式の最大絶対誤差（cm³/s） |
| --- | ---: | ---: |
| 内部サンプル50,049 | 6.85×10⁻¹² | 3.68×10⁻¹⁶ |
| 後続50,081〜50,304の224ステップ | 9.40×10⁻¹² | 3.44×10⁻¹⁵ |

後続区間の値は、観測した面積・セル長を使った移動壁の局所流量に対する誤差で、近隣への配分と平滑化の前で求めた。面積、セル長、口端負荷の解の有無、ジェスチャーは両条件で一致した。最初に変わった観測は50,049の断面更新直後の流入で、同じサンプルの口端流量に伝わった。前ステップの流入は0で、展開式の局所流量を2段の平滑器に通すと、実測した流入 `1.439078838783335×10⁻⁴ cm³/s` をビット一致で再現した。[誤差と初出点](../runs/duet-mixed-volume-difference-20261122-a/summary.json)

固定上流との初出点の流入差は、展開式を研究版に適用すると `1.64×10⁻¹⁶` から `5.85×10⁻¹⁷ cm³/s` に縮んだ。両版の幾何に展開式を当てはめた独立計算では差は `1.90×10⁻¹⁹ cm³/s` だった。上流に展開式を適用したレンダーはこの比較に含めていない。全97,920フレームのPCMは、展開式と基準で最大 `1.14×10⁻¹³` 異なり、最初の差は0始まりの出力フレーム58,948だった。固定上流とのPCM最大差は両条件とも `1.46×10⁻¹¹` だった。閉鎖・再開口と密閉圧縮は両条件とも各8判定を通過した。[PCMと既存ケースの結果](../runs/duet-mixed-volume-difference-20261122-a/summary.json)

展開式は研究用の比較差分として保存する。今回の変更は局所流量の丸めを減らしたが、固定上流とのPCM最大差は同じだった。面積と長さの寄与がほぼ完全に打ち消し合う条件での精度は未測定。最小の対照では、面積増加と長さ減少を同時に与え、厳密な体積差が0に近い2状態に対して両式を比較できる。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。研究ワークスペースと `/private/tmp` を起点とした2実行で、それぞれ8判定と固定上流の `airway_adversarial` 6試験が通過した。要約・PCM・観測CSVなど18出力がバイト一致した。計290入力と42出力のサイズとSHA-256を照合し、採取物20,067,162バイトをRTL9210B-CGに保存した。[初回実行](../runs/duet-mixed-volume-difference-20261122-a/manifest.json)・[別の作業場所からの再実行](../runs/duet-mixed-volume-difference-20261122-repeat/manifest.json)
