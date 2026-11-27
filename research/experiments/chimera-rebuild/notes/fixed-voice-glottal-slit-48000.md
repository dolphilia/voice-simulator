# 声門スリット抵抗の演算順を揃える

## 読解と事前の予測

上流の [`HumanAirway::new`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153) は、気管末端と咽頭入口をつなぐ声門ポートに、成人男性の基準寸法として長さ `l=0.3 cm`、スリット幅 `w=1.4 cm` を設定する。[`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L394) は、更新前の声門上下圧差から求めた開口面積 `A`（cm²）をポートへ渡し、気道を進める。[`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L995) は、閉鎖閾値を超えた開口について `i=1/A` と粘性係数 `μ` を使い、抵抗を `12 μ l w² i³` として計算する。抵抗の単位は dyn·s/cm⁵。慣性を時間換算した項へこの抵抗を足して線形係数を作り、駆動圧と二次損失係数から流量を解く。その流量は同じ内部点の気管と咽頭の体積収支に反映される。

研究版の [`branch_impedance`](../crates/vocal-core/src/airway/network.rs#L83) は `w²` と `i³` をそれぞれ先に求める。上流は `12×μ×l` に `w` を2回、`i` を3回続けて掛けるため、丸め位置が異なる。隔離ビルドでは開口の幾何更新後に声門枝だけの抵抗を上流順で再計算する。累乗の演算順以外の係数、閾値、ポートの接続と入力を対照と共通にする。上流の [`folds_held_apart_meet_for_less_of_the_cycle`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62) は声帯の開大で閉鎖の割合が減ることを確認する。今回の独立計算は開口面積を入力にし、計算された抵抗が枝流量へ伝わる箇所を照合する。

[先行の肺ポート比較](fixed-voice-lung-port-momentum-48000.md#肺境界から気管末端までの一致)では8,217点目の声門流量を線形係数の置換で上流値に復元した。今回はその抵抗を連続描画の中で変え、8,216点目までの流量を保ったまま目標点が一致するかを調べる。停止後を含む全PCMと気管の内部系列も照合する。[事前登録](../cases/fixed-voice-glottal-slit-48000.json)

## 連続描画の声門流量とPCM

固定 `/i/`、内部96 kHz、出力48 kHzの通常CLIから描画した。肺ポートの運動量まで揃えた先行実験を隔離ソースに復元し、対照の内部CSVとPCMを保存出力と照合した。変更版では、声門枝が幾何を更新した直後の抵抗だけを上流と同じ乗算順で再計算した。

| 8,217点目の量 | 対照 | 変更版と上流 |
| --- | ---: | ---: |
| スリット抵抗（dyn·s/cm⁵） | 408.97377106687344 | 408.9737710668735 |
| 慣性を時間換算した項と抵抗の和（dyn·s/cm⁵） | 2674.00131854016 | 2674.0013185401604 |
| 声門流量（cm³/s） | `8.535131922566457×10⁻⁶` | `8.535131922566455×10⁻⁶` |

8,216点目までの声門流量、8,217点目に声門枝が読む左右圧と慣性は対照と一致した。変更版の声門流量、肺境界圧、気管13枝の流量と13セルの圧力は、8,188〜8,239点目の観測区間すべてで上流とビット一致した。声門の抵抗も観測した52点すべてで独立計算と上流に照合した。

| 全PCMの上流との比較 | 対照 | スリット抵抗を変更 |
| --- | ---: | ---: |
| ビット差のあるフレーム | 15 | 17 |
| 最初のビット差の出力フレーム | 60,225 | 4,802 |
| ゲート停止後の差のあるフレーム | 15 | 16 |
| 最大絶対差 | `1.1368684×10⁻¹³` | `5.8207661×10⁻¹¹` |

両版とも128・77の分割で全93,056フレームがビット一致し、上流・対照との差は登録許容差 `5×10⁻⁷` 以内だった。PCMの差が出た4,802フレーム目は、最初の内部観測区間より後にある。別ケースとして、先頭4,810出力フレームまで観測を延ばし、固定上流と内部番号を揃えて差の伝わる順序を測る。[主比較の要約](../runs/fixed-voice-glottal-slit-48000-repeat/summary.json)・[延長観測の事前登録](../cases/fixed-voice-glottal-slit-prefix-48000.json)

## 実行と検証

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_glottal_slit.py fixed-voice-glottal-slit-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_glottal_slit.py" \
  fixed-voice-glottal-slit-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各11判定と固定上流の各15試験に合格した。各実行で節点1,352点、気管枝1,352点、声門枝104点を有理数と十進数で独立に計算した。PCM・観測CSV・差分・要約の20出力が再実行間でバイト一致した。2実行で384入力と52出力をハッシュ照合し、採取物13,456,224バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-glottal-slit-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-slit-48000.json)

## 最初のPCM差まで観測を延ばす

内部系列を先頭4,810出力フレームまで採り、固定上流の保存系列と各出力フレーム末尾の内部番号で合わせた。両版のPCMを全93,056フレームから切り出した先頭区間と比較する手順を用いた。延長比較の初回起動 `fixed-voice-glottal-slit-prefix-48000-a` は、参照マニフェストのSHA-256を `3b0fa8ca610b87b5f8e6799cbc6f93c77d50a6869613b858b8f5372e5a48ff0c` と誤記し、出力の作成前に停止した。保存済みのハッシュを再取得して登録を訂正し、同じ入力と判定条件で再実行した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_glottal_slit_prefix.py fixed-voice-glottal-slit-prefix-48000-b
```

延長描画した両版のPCMは、それぞれの全区間PCMの先頭と一致した。採取したフレーム末尾の量では、両版とも放射流量の時間微分が内部8,207点目（出力4,103フレーム目）で最初に上流と分かれ、値も両版で同じだった。変更版では次に声門上圧が8,219点目、口端流量が8,241点目、声門流量が8,339点目に分かれた。変更版で出力PCMに差が現れた4,802フレーム目は内部9,605点目に対応する。その時点の放射流量微分は変更版 `345.6739492163763`、上流 `345.67394921620576` cm³/s² だった。対照は同じ先頭4,810フレームのPCMが上流と一致した。[初差とその周辺の観測](../runs/fixed-voice-glottal-slit-prefix-48000-b/summary.json)

`/tmp` から同じコマンドを絶対パス・実行ID `fixed-voice-glottal-slit-prefix-48000-repeat` で再実行した。延長観測の各8判定に合格し、別のCSV読み取りで両版の各4,810フレームの初差を再計算した。11出力がバイト一致し、378入力と24出力をハッシュ照合した。延長観測の採取物9,062,456バイトもRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-glottal-slit-prefix-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-slit-prefix-48000.json)

次は最初の放射流量微分の差を、壁・口端・鼻端の流量和とその前回値に分けて調べる。[研究版の最後の更新](../crates/vocal-core/src/airway/network.rs#L791)は実時間刻みで割り、[固定上流の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)は内部サンプルレートを掛ける。8,207点目でこの順序と流量和のどちらが差を作るかを照合する。今回の観測が示すのは時間順で、4,802フレーム目のPCM差への寄与は引き続き調べる。
