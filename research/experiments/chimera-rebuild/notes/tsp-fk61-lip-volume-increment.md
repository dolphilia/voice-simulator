# FK61_01の口端で体積差分の求め方を比較する

対象は96 kHzの内部標本3952〜3979と、48 kHzの発話全116,132フレーム。固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。標準の研究版と同じ女性体型、発話、辞書・音源設定を使う。 [事前登録](../cases/tsp-fk61-lip-volume-increment.json)・[前回の口端計測](tsp-fk61-lip-onset.md)

## 読解と実装

上流の通常CLIは英文をスコアにし、`HumanVoice::render` を呼ぶ。制御標本で `HumanVoice::control` が目標断面を更新し、`AirwayNetwork::begin_block` が平均面積・最小面積・セル長の標本ごとの増分を計算する。`AirwayNetwork::step` は増分適用後の断面積に下限を設けてセル長を掛け、体積をcm³で保存する。前の体積との差を毎秒の体積流量に換算し、狭いセルから開いている近隣への配分、60 Hzの平滑化2段、枝、壁、節点と放射負荷の順に処理する。密閉空洞を5%だけ圧縮するテストでは、上流の圧力を断熱圧縮の積分式に照合している。 [上流のCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs)・[上流の制御と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の体積源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L835)・[密閉空洞の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L54)

研究版の `vocal-cli render-pcm` から発話器を経て、`HumanAirway::begin_tract_block` が `MovingAreas` にセルごとの補間目標を渡す。試験版は、`HumanAirway` の口端番号を使い、口端セル1節点の `MovingAreas::step` だけで以下の体積差を選ぶ。A₀・A₁は更新前後の平均面積に同じ下限を適用した値［cm²］、L₀・L₁は更新前後の長さ［cm］。結果を秒単位の内部刻みで割り、押し出しの流量［cm³/s］として後段へ渡す。 [通常CLI](../crates/vocal-cli/src/main.rs#L452)・[補間の入口](../crates/vocal-core/src/airway/human.rs#L341)・[試験版のRust差分](../tools/patches/candidate-tsp-lip-volume-increment.patch)

```text
A₀L₀ − A₁L₁ = (A₀ − A₁)L₀ + A₁(L₀ − L₁)
```

この形では面積と長さの差を先に取り、小さい2項を足す。前の断面から計算した体積が保存体積と違う場合は保存体積を始点にする。保存する体積は従来の積を使い、放射負荷や気道の他セルの演算も同じ処理を通す。Rustの単体試験は面積・長さが同時に変わる場合の正負両方向と、両断面が下限に掛かる場合を照合する。既存の補間試験では、長さと枝開口を同じ標本で更新し、途中の入力拒否が進行中の補間を妨げないことを検査する。 [研究版の体積と補間](../crates/vocal-core/src/airway/network/geometry.rs#L110)・[既存の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 実測

口端の観測28標本は、標準版と試験版で面積・長さ・保存体積と放射負荷の係数が一致した。内部標本3968の生の体積流量は、同じ断面の積差を有理数で求めた値に対して、絶対誤差が9.3999×10⁻¹²から7.0152×10⁻²⁰ cm³/sに減った。この誤差は試験版の観測28標本で最大だった。放射差分はこの標本で最初に変わり、固定上流との差は4.4728×10⁻¹²から5.2802×10⁻¹³ cm³/s²へ縮んだ。壁面の流量が最初に変わるのは次の内部標本。鼻端の流量は観測した先頭4096内部標本で一致した。 [要約](../runs/tsp-fk61-lip-volume-increment-20261123-recheck/summary.json)

| 比較 | 最初にPCMが異なる出力フレーム | 異なる全フレーム数 | PCMの最大絶対差 |
| --- | ---: | ---: | ---: |
| 固定上流と標準版 | 1989 | 2257 | 1.86265×10⁻⁹ |
| 固定上流と試験版 | 1987 | 2258 | 1.86265×10⁻⁹ |
| 標準版と試験版 | 1987 | 9 | 1.45519×10⁻¹¹ |

「固定上流と最初に異なるPCMフレームが遅くなる」という予測は外れた。フレーム1987で固定上流と標準版の変換直前値はfloat32の同じ丸め区間に入り、試験版は隣の区間に入った。丸めの境界は2.3286818437093237×10⁻¹²で、境界からの距離は固定上流で+3.95×10⁻²²、標準版で+8.08×10⁻²²、試験版で−1.22×10⁻²¹だった。放射差分は標本3968の1点で縮み、そこから出力1987までに履歴を含むFIR・DC除去を通った値が別のfloat32へ丸められた。 [丸めと出力段の要約](../runs/tsp-fk61-lip-volume-increment-20261123-recheck/summary.json)

次にこの発話の標準版で、発話前の口端の面積を測定線、音響セルへの再標本化、開口速度の制限、ネットワークの初期値の順に比べる。口端の面積差がその経路のどこで最初に出たかを確かめる。 [上流の断面更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L230)・[研究版の断面制御](../crates/vocal-core/src/airway/tract_control.rs#L180)

## 再実行

研究ワークスペースから新しい実行IDを指定する。差分を適用した一時チェックアウトとCargoの生成物はRTL9210B-CGに置く。照合後は、試験版のPCMと先頭の内部時系列、口端の28標本、通常CLIと観測器のPCMハッシュ、試験ログを保存する。 [計測の入口](../tools/measure_tsp_fk61_lip_volume_increment.py)

初回は、既存のライブラリ単体試験がコンパイル時に読み込むケース2件が一時チェックアウトに不足して停止した。追加後の2実行では観測と描画を保存でき、NumPyの真偽値が要約のJSONへの変換を妨げた。真偽値の入力をPythonの数値に揃えて再実行し、元のPCMと観測列を照合した。事前登録の判定条件は初回から同じ。 [コンパイル失敗](../runs/tsp-fk61-lip-volume-increment-20261123/manifest.json)・[観測が残った実行](../runs/tsp-fk61-lip-volume-increment-20261123-verified/manifest.json)・[要約まで保存した再実行](../runs/tsp-fk61-lip-volume-increment-20261123-recheck/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` の2実行は各5判定・Rustの2試験に通過し、要約、観測列、発話とその先頭の内部時系列、PCMハッシュの4出力がバイト一致した。 [作業ディレクトリでの実行](../runs/tsp-fk61-lip-volume-increment-20261123-a/manifest.json)・[別ディレクトリでの実行](../runs/tsp-fk61-lip-volume-increment-20261123-recheck/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_lip_volume_increment.py fk61-lip-volume-increment-new
```
