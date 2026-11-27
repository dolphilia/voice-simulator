# 体型補間を固定気道へ接続する

上流の較正コマンドは `calibrate::formants` で `HumanAirway::apply(a, 0)` を呼び、`linear_elements` の体積流量源を咽頭入口へ置いて声門枝を切る。同じ線形系をWASMの伝達関数と `body_mix.rs` の体型比較も使う。時間領域で固定姿勢を使うときは、`snap_to_targets` で面積、最小面積、セル長、ポート開度を実状態にも入れてからゼロ状態を励振する。制御周期が0の場合は断面の変化率制限を適用しない。[較正の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/calibrate.rs#L138)・[目標の確定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[線形要素](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1199)・[体型テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)

`HumanAirway::new` は全体係数 `k` と咽頭係数 `h`、内部レート `Fₛ` を使う。設計セル長は `Δx_design = (c/Fₛ)/0.93` cm。咽頭は想定最短長 `k(8.7(0.55+0.45h)−1.6)`、口腔は `k(8.3−1.0)` を設計セル長で割って切り捨て、各8セル以上とする。気管・鼻腔の長さは12と11.4 cmに `k` を掛け、断面は `k²`。気管と鼻腔は設計セル長と、それぞれ `0.9k`・`0.5k` cmの大きい方からセル数を求める。梨状窩は `2k` cmを設計セル長で割った切り捨てを1〜3に収める。上顎洞の体積は `14k³` cm³、頸部は長さ `0.5k` cm、面積 `0.12k²` cm²。肺境界の音響抵抗は気管断面に反比例する。壁や放射負荷は、その管の寸法を使って枝・節点の係数へ変換する。[建設時の寸法と接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L107)・[空洞・肺境界の節点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L465)

形状計算で得た咽頭長・口腔長と最小断面は、そのセル数への再標本化に使う。実際の音響セルが `(c/Fₛ)/0.97` cmより短くなる管は、音響計算で使う長さだけを延ばす。位置表示や解剖寸法には元の長さを保つ。体型を子どもにすると64 kHz・梨状窩長1.48 cm。3セルのままならクーラン数は約1.109、計算式による2セルなら約0.739になる。短い口腔を与える別の子ども例では、9セルの長さの合計が約5.074 cmに制限されると予測する。[管長の安定性下限](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L306)・[極端な姿勢の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

固定した一つの /ɑ/ の姿勢で成人男性・成人女性・子どもと2つの混合点を比較し、鼻端放射は子どもの開いた軟口蓋でも測る。体型別に較正した母音は次の工程の入力として扱う。今回は体型による管の差を、音源を取り除いた同じ調音入力で測る。周波数領域は60 Hz〜8 kHzの対数360点。口・鼻・壁の放射を複素数として加え、枝を含む全節点のアドミタンス行列を別に解く。時間領域では咽頭入口に `10⁻⁶ cm³` を一度注入し、8192サンプルの圧力・流量と末尾の減衰を比較する。[登録ケース](../cases/human-body-airway.json)・[線形応答の定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L13)・[幾何の前段](human-body-geometry.md)

## 実装と結果

断面プロファイルが持つ体型を `HumanAirway::fixed_from_profile` に渡す。体型と内部レートから `TractSampling` がセル数と計算長を決め、気管・鼻腔・梨状窩、上顎洞とポートも同じ体型で構成する。CLIの `inspect`・`render`・`transfer` がこの経路を通る。独立計算では、測定した断面を8中点と実測格子点で再標本化し、長さ・断面積・コンプライアンスとクーラン数を確認した。インパルス直後の咽頭入口圧は注入体積を幾何コンプライアンスで割った値、全放射の差分は口・鼻・壁の流量の和を差分した値と照合した。[固定気道のRust実装](../crates/vocal-core/src/airway/human.rs)・[音響格子](../crates/vocal-core/src/airway/tract_control.rs)・[比較プログラム](../tools/measure_body_airway.py)

| 同一 /ɑ/ 姿勢・96 kHz | 咽頭セル | 口腔セル | 第1共鳴 (Hz) | 第2共鳴 (Hz) |
| --- | ---: | ---: | ---: | ---: |
| 成人男性 | 18 | 18 | 730.71 | 1337.11 |
| 成人女性 | 15 | 16 | 823.85 | 1599.74 |
| 子ども | 11 | 13 | 1001.20 | 2073.23 |
| 成人男性と子どもの中間 | 14 | 16 | 846.17 | 1644.82 |
| 成人女性軸0.4・子ども軸0.3 | 15 | 16 | 823.97 | 1584.98 |

7条件の全100項目が通過した。固定上流との伝達振幅の最大ピーク相対誤差は `1.25×10⁻¹⁴`、圧力レベルの最大絶対差は `4.97×10⁻¹³ dB`。独立計算との複素流量の最大ピーク相対誤差は `2.62×10⁻¹³`、固定上流とのインパルス時系列の最大ピーク相対誤差は `4.36×10⁻¹⁴` だった。[結果と各観測値](../runs/airbody-20261120-a/summary.json)

64 kHzの子どもの梨状窩は2セルでクーラン数0.739。3セルのままの値は1.109になる。短い口腔では解剖長4.572 cmに対し計算長5.074 cmとなり、最大クーラン数を0.970に保った。子どもの /ɑ/ で軟口蓋を0.30に設定した64 kHz条件のポート面積は0.16428 cm²。インパルス後に口端は16、鼻端は21サンプル目で放射を始め、鼻端のピーク流量は口端の6.40%だった。[短い口腔の詳細](../runs/airbody-20261120-a/artifacts/child-short-64k/inspect.json)・[開いた軟口蓋のインパルス](../runs/airbody-20261120-a/artifacts/child-open-64k/impulse.csv)

`/tmp` からの再実行も全100項目を通過し、入力ケース・観測CSV・比較要約など106ファイルがバイト一致した。macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。固定上流の `body_mix` 4項目と `engine` 6項目、候補のRust整形、Clippy、ワークスペーステストが通過した。成人男性のインパルスと伝達関数、体型の幾何、ブラウザの固定発声も回帰を通過し、WAV、観測値、要約も該当する基準と一致した。[再実行と環境](../runs/airbody-20261120-repeat/manifest.json)・[成人男性の気道](../runs/airbody-20261120-male-after/manifest.json)・[伝達関数](../runs/airbody-20261120-vowel-after/manifest.json)・[幾何](../runs/airbody-20261120-geometry-regression/manifest.json)・[ブラウザの固定発声](../runs/airbody-20261120-worklet-regression/manifest.json)

この固定気道の測定は声門を閉じた線形応答とインパルスを対象にした。体型別の声帯振動と呼気を接続した結果は、別の固定発声ケースで確認した。[体型別の固定発声](human-body-fixed-voice.md)

```bash
python3 tools/measure_body_airway.py body-airway-local-1
```
