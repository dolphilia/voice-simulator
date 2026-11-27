# CSDの咽頭セル7で枝の流量履歴を照合する

前回は `en001a` の咽頭セル7（節点20）のコンプライアンスを内部標本0だけ交換した。研究版の全節点の圧力が標本2で通常描画と一致した後、標本3で圧力差が再び現れた。局所モデルは、標本2の枝19→20と20→21の流量差がその圧力差を運ぶと予測した。今回は固定上流と研究版でその値を直接採り、ゆらぎ・幾何の更新後に枝の前回流量を通常描画の値に戻す。壁の速度と変位を戻す対照も描画する。 [事前登録](../cases/csd-en001a-pharynx-cell7-branch-history.json)・[前回の予測](csd-en001a-pharynx-cell7-compliance-pulse.md#標本3で圧力差が戻る理由の検算)

## 式と更新順

上流の `HumanVoice::render` は96 kHzの内部時計で制御・声門の後に `AirwayNetwork::step` を呼ぶ。気道では動く断面の体積源を加えて乱流圧を更新し、枝、壁、節点の順に進む。枝の正方向は節点番号が小さい方から大きい方。枝の前回流量は cm³/s、慣性は g/cm⁴、その積が流量履歴として保存される運動量（g/(cm·s)）。上流は枝が閉じる方向では前回の運動量を、開く方向では現慣性と前回流量の積を使う。研究版の `Branch::step` は前回慣性と現慣性の小さい方を選び、時刻幅で割ってから前回流量を掛ける。枝を駆動する圧力（dyn/cm²）は左右の圧力差、乱流圧とこの履歴項の和。粘性抵抗と方向別の二次損失を含む方程式を解き、左右の節点の流量収支に逆符号で足す。 [上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L923)・[研究版の枝更新](../crates/vocal-core/src/airway/network.rs#L179)・[定常狭窄の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L91)

壁は前回速度（cm/s）、変位（cm）、更新前の節点圧力から動き、壁面積との積で体積速度を求める。節点19〜22は開いた非放射節点なので、枝の流量と体積源から壁への流量を引いた値に `dt/C` を掛け、前回圧力へ足す。したがって節点圧力が同じでも、枝の流量や壁の状態を次の標本へ持ち越すとその次の圧力は変わり得る。比較では標本3の枝の求解直前または壁の求解直前にだけ履歴を変更する。枝を元に戻す操作は乱流の計算後なので、その標本の乱流圧を含む他の入力を採取して照合する。 [上流の壁・節点更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1050)・[研究版の壁・節点更新](../crates/vocal-core/src/airway/network.rs#L744)・[枝・壁の独立計算](../tools/measure_tsp_fk61_lip_front_terminal_branch.py#L82)

## 実測

標本2の圧力は両版とも、通常とコンプライアンス交換で全71節点が一致した。研究版では、枝19→20の流量に −1.0587911840678754×10⁻²²、枝20→21に +2.117582368135751×10⁻²² cm³/sの差が残った。局所モデルの事前予測と一致した。上流は標本2の両枝の流量も一致し、今回のどの履歴交換でも全PCMと標本3〜7の圧力は通常描画と一致した。 [初回の測定結果](../runs/csd-en001a-pharynx-cell7-branch-history-20261124-registered/summary.json)

研究版で通常描画からの差を比較した結果を示す。圧力は96 kHzの内部標本3、PCMは48 kHzの全201,600フレームで比較した。

| 標本3の更新に渡した履歴 | 節点20の圧力差（dyn/cm²） | 節点21の圧力差（dyn/cm²） | PCM差のフレーム数 |
| --- | ---: | ---: | ---: |
| 一値交換時のまま | −6.776×10⁻²¹ | +6.776×10⁻²¹ | 22,334 |
| 左枝だけ通常へ戻す | −3.388×10⁻²¹ | +6.776×10⁻²¹ | 22,334 |
| 右枝だけ通常へ戻す | −3.388×10⁻²¹ | 0 | 21,015 |
| 両枝を通常へ戻す | 0 | 0 | 0 |
| 壁だけ通常へ戻す | −6.776×10⁻²¹ | +6.776×10⁻²¹ | 22,334 |

両枝を戻すと標本3〜7の全71節点の圧力が一致し、PCMの全ビットが一致した。左枝だけを戻すと節点20の標本3の圧力差は半分になったものの、全PCMは一値交換の波形とビット一致した。右枝だけを戻すと、節点21は標本3で一致し、標本4で再び差が出た。右枝だけを戻したPCMは、通常との21,015フレームに加え、一値交換との31,104フレームで異なった。壁だけを戻した全PCMも一値交換の波形とビット一致した。局所の連続値で差を小さくした場合でも、その順序を全区間のfloat32 PCMから直接読み取れない。

両枝の操作で消えたのは、調整曲 `en001a` の標本0に入れたコンプライアンス一値の影響。次は確認曲 `en005a` の同設定描画で、丸め前とPCMの差を採り、曲頭で最初に分かれる処理と確認曲全体への影響を照合する。 [確認曲の通常描画条件](../cases/csd-acoustic-f0-en005a.json)・[確認曲の冒頭条件](../cases/csd-acoustic-f0-en005a-startup.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。事前登録のSHA-256は `851f16d794d7f697c3a7c9580f4d605bf9f5f647cc13ed66ea176f9e44f0bb5b`。計測の一時ビルドと採取物の実体はRTL9210B-CGに保存した。両版で通常とコンプライアンス一値交換の圧力・PCM・歌唱計画を前回と照合し、全条件の先頭8標本で5枝と4節点の局所方程式を採取値から再計算した。両版の4つの履歴交換で、他の標本3の入力が一値交換時と一致することも照合した。 [初回のマニフェスト](../runs/csd-en001a-pharynx-cell7-branch-history-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/csd-en001a-pharynx-cell7-branch-history-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_csd_en001a_pharynx_cell7_branch_history.py csd-pharynx-branch-history-new
```
