# 咽頭入口から次セルへ向かう直列枝の流量差

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L394) は、声門に圧力差を渡した後に [`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L955) を進める。咽頭を構築すると、入口の節点13と次の節点14の間に直列枝が置かれる。流量 `U`（cm³/s）の正方向は入口から咽頭内へ向かう。線形係数は現在の慣性 `L`（g/cm⁴）を時間換算した項と粘性抵抗 `R` の和。駆動圧は左右圧の差、乱流圧、前回運動量の時間換算を加えた値で、二次損失 `K` は流れの向きで選ぶ。これらを使って二次式を解き、枝の流量と運動量を更新する。[上流の更新式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)

研究版は [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) で同じ根を求める。`L/dt` と `(L_carry/dt)×U_prev` の時間換算、各半セルから求める粘性抵抗と収縮・拡大損失には演算順の違いがありうる。枝の更新後、この流出を声門からの流入や壁流出とともに入口セルの体積収支に入れる。得られた入口圧は次の内部点で壁運動に使用される。上流の [`steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92) は短い狭窄で流量とジェット損失の関係を検証する。今回は過渡の小さい差を観測するため、各項と独立計算を同じ内部番号で照合する。

[先行の放射微分比較](fixed-voice-radiation-derivative-48000.md#残った微分差は咽頭入口の圧力差から伝わる) と保存済みの咽頭収支では、8,218点目に流出差が見え、8,219点目に入口圧が分かれた。保存された8,217・8,218点目の入口圧と次セルの圧力は両版で一致している。新しい計測では枝の左右圧を直接確認し、線形係数・持ち越し圧・二次損失の組み合わせを置き換える。通常の描画とPCMも照合し、観測が演算を変えていないことを確かめる。[事前登録](../cases/fixed-voice-pharyngeal-entry-branch-48000.json)

## 最初の流量差は持ち越し運動量の時間換算から生じる

固定 `/i/` の出力48 kHz・内部96 kHzで、節点13→14の枝と入口圧を内部8,188〜8,239点目の52点で照合した。8,218点目は左右圧、前回流量、現在の慣性、抵抗、駆動方向の損失がビット一致した。持ち越し運動量そのものも同じ値で、時間換算後の圧力だけが `0.00010324040669968513` と `0.00010324040669968514` dyn/cm² に分かれた。上流は `(L_carry×U_prev)×Fs`、研究版は `(L_carry/dt)×U_prev` の順で丸める。逆方向の損失にも1 ULPの差があった。この点の駆動圧は正で、流量計算には一致している前進側の損失を使った。[枝・幾何・置換の観測値](../runs/fixed-voice-pharyngeal-entry-branch-48000-repeat/summary.json)

8,218・8,219点目の流量は、その点で観測した持ち越し圧を上流値に置換するだけで復元できた。8,219点目の持ち越し圧には、すでに8,218点目で分かれた前回流量が入っている。この点の枝流量を上流の `1.579771614944532×10⁻⁵` cm³/s にすると、咽頭入口の体積収支から上流圧 `0.0013183272113715156` dyn/cm² を再現できた。入口圧は次の8,220点目の壁速度と放射に伝わる。[咽頭収支の一次記録](../runs/fixed-voice-pharynx-onset-48000-repeat/manifest.json)・[壁入力圧の先行検算](fixed-voice-radiation-derivative-48000.md#残った微分差は咽頭入口の圧力差から伝わる)

## 咽頭の一枝を上流順にした連続描画

隔離ビルドでは声門枝の出口から次セルに向かう直列枝を選び、その枝の持ち越し圧を描画の全区間で `(L_carry×U_prev)×Fs` にした。現在の慣性の時間換算には既存の `L/dt` を使った。通常CLIで再描画すると、登録した2点の枝流量、入口圧と放射微分が上流にビット一致した。[事前登録](../cases/fixed-voice-pharyngeal-entry-momentum-48000.json)・[実験用のRust差分](../runs/fixed-voice-pharyngeal-entry-momentum-48000-a/artifacts/candidate-tracheal-history.patch)

| 内部点 | 観測値 | 対照 | 変更版と上流 |
| --- | --- | --- | --- |
| 8,218 | 枝流量（cm³/s） | 6.565581129143410×10⁻⁶ | 6.565581129143412×10⁻⁶ |
| 8,219 | 枝流量（cm³/s） | 1.5797716149445316×10⁻⁵ | 1.579771614944532×10⁻⁵ |
| 8,219 | 入口圧（dyn/cm²） | 0.0013183272113715158 | 0.0013183272113715156 |
| 8,220 | 放射流量微分（cm³/s²） | 0.0007515525574101968 | 0.0007515525574101965 |

枝流量の最初の差は8,229点目、放射を採った区間での微分の最初の差は8,231点目へ移った。8,229点目は持ち越し圧・左圧・線形係数・前進側の損失が一致した。右の節点14の圧力だけを上流値にすると流量を再現できた。保存済みの上流収支と比較すると、節点14の更新後圧は8,214点目で最初に分かれていた。次はその点の前回圧、前後の枝流量、壁流量、体積変化とコンプライアンスを同じ番号で採る。[連続描画の要約](../runs/fixed-voice-pharyngeal-entry-momentum-48000-a/summary.json)

全93,056フレームで、対照と変更版はそれぞれホスト分割128・77間でビット一致した。上流とのビット差は停止後の15から12フレームへ減り、初差は55,880から61,467フレーム目へ移った。最大絶対差は `5.8207661×10⁻¹¹` から `2.2737368×10⁻¹³` へ減った。対照と変更版の間で異なるPCMは停止後の7フレームだった。[生PCMからの独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-entry-momentum-48000.json)

## 実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_pharyngeal_entry_branch.py fixed-voice-pharyngeal-entry-branch-48000-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_pharyngeal_entry_momentum.py fixed-voice-pharyngeal-entry-momentum-48000-a

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_pharyngeal_entry_branch.py" \
  fixed-voice-pharyngeal-entry-branch-48000-repeat
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_pharyngeal_entry_momentum.py" \
  fixed-voice-pharyngeal-entry-momentum-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各8判定に合格した。固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のテストは、枝の採取で `airway`・`airway_adversarial` の各9件、連続描画で `airway_adversarial`・`engine` の各12件が通過した。枝の採取は両実装の各52点で流量と入口圧を再計算し、加えて断面から慣性・抵抗・両方向の損失を十進数で照合した。連続描画は両条件の各52点で流量と入口圧を十進数でも照合し、WAVのPCMから差の数・位置・最大値を再計算した。[枝の採取マニフェスト](../runs/fixed-voice-pharyngeal-entry-branch-48000-repeat/manifest.json)・[連続描画のマニフェスト](../runs/fixed-voice-pharyngeal-entry-momentum-48000-repeat/manifest.json)

再実行で枝の採取の10出力、連続描画の13出力がバイト一致した。固定上流の一時プローブの実行ファイルはハッシュが異なり、観測CSVとPCMのハッシュは一致した。全4実行の832入力と84出力をハッシュ照合し、実体29,218,515バイトをRTL9210B-CGに保存した。マニフェストには実行コマンドと保存先、リポジトリ側には要約と成果物へのリンクがある。[枝の採取の独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-entry-branch-48000.json)・[連続描画の独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-entry-momentum-48000.json)
