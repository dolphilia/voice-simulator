# 無声後部歯茎摩擦音 /ʃ/ の調音と乱流

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。元のTSP調整用 `FA01_02` と `MA01_02` は `/ʃ/` だけが未対応だった。事前に発話、歌唱、`/ɕ/` と `/tʃ/` の対照、乱流倍率0を登録した。録音の発話区間長は別の比較で扱う。[入力検査](../runs/tsp-active-duration-inspect-20261121-rhotic/summary.json)・[登録条件](../cases/postalveolar-fricative-sh.json)

## 固定上流の処理順序

`chimera-cli/src/main.rs::run` から、本文は `render::text` → `say`、譜面は `render::notes` → `plan_song` へ進む。`EnglishG2P` の辞書読みでは `SH` を `/ʃ/` にし、`plan_utterance` は音素と体型から `inventory::phoneme` の調音目標を読む。`durations::klatt_durations` の `/ʃ/` の基準長は105 ms、最短80 ms。語頭以外や子音に隣接するときは、基準長と最短長の差の部分に倍率を掛ける。標準の `ɑʃɑ` と語末の `ɑʃ` では、他の子音に隣接せず語頭以外なので `80 + (105 − 80) × 0.85 = 101.25 ms`。話速も区間長に作用する。[本文の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[CMU辞書の変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs#L43)・[時間配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L182)

舌先Xは5.7 cm、舌先Yの較正値は成人男性9.512、成人女性9.521、子ども9.538 cm。顎は0.35 cm、唇の突出は0.75 cm、幅は無次元の0.2。5軸すべてを支配軸とし、`oral_gestures_into` は音素の時間 `[a,b)` に対し `a−8 ms` から `max(b,a+10 ms)` まで、強さ40、速度1.3で目標を与える。立ち上がり30 ms、立ち下がり18 ms、解放保持45 ms。声門の開大は独立に `a−15 ms` から `b+5 ms`、両側30 ms、強さ6、加算目標0.30 cm²。話速が1を超えるとランプと保持を話速で割る。口蓋化では支配軸と重ならない舌体2軸に `/j/` の目標を重ねる。[調音目標と較正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L191)・[ジェスチャーと声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L443)・[ランプ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L749)

`/tʃ/` は初めに舌先の閉鎖を計画し、分割点 `a+0.45(b−a)` に対して `max(a,分割点−15 ms)` から `/ʃ/` の目標へ移る。`/ɕ/` は舌体にも強く働き、唇突出目標0 cm・幅0.7。`/ʃpt/` では `/p/` の唇閉鎖中に、先々行の `/ʃ/` が調音した舌先を使えるため、`/t/` の閉鎖の狙いを `min(25 ms,max(0,d−30 ms))` 遅らせる。句末 `/ʃ/` は一般の阻害音として終端の15 ms後に `exhale` の目標を置く。[破擦音と終端](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L483)・[先行配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L779)

`HumanVoice::control` が出力64フレームごとに声道形状を更新し、`HumanAirway::apply` から `update_noise` が咽頭・口腔の最小の開断面を探す。体型の長さ倍率で歯までの距離を、倍率の二乗で狭窄面積を正規化する。歯の手前で流れが当たる幾何なら、最小断面の枝を音源の参照にし、別の歯の枝へ圧力を注入する。流量 `U` は cm³/s、枝の面積 `A` は cm²。噴流速度は `|U|/A`、径 `D` は `2√(A/π)`、渦の尺度 `δ` は `max(D,0.17×歯までの距離)`。帯域の上限は `(|U|/A)D/δ²` Hzとし、幾何の重みと `√(5000/max(上限,1200))` を歯のゲインに掛ける。内部96 kHzの `AirwayNetwork::compute_noise` は各枝のレイノルズ数から振幅を決め、フィルター済みの乱数を流れる向きに入れる。その後の伝搬、放射流量の時間差分、間引きを経て48 kHzのPCMになる。[歯の音源選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L328)・[圧力注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)

上流の `lung_port.rs::a_fricative_keeps_the_lungs_pressure_at_its_folds` は成人男女の `ɑʃɑ` で声門下圧を動的に調べる。`sound_marks.rs` は `/ʃʲ/` の舌体ジェスチャーが支配軸に干渉しないこと、`affricates.rs` は `/tʃ/` の実音響に摩擦区間が残ること、`consonant_artifacts.rs` は語頭や子音群で追加の放射ピークが出ないことを検査する。候補では既存の `/tʃ/` の解放目標と同じ関数を使い、CLIとWASMの通常経路で `/ʃ/` の自動乱流を有効にした。[声門下圧の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L35)・[口蓋化の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sound_marks.rs#L145)・[破擦音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs#L75)・[再実装](../crates/vocal-core/src/phonetics/speech.rs)

## 計画と摩擦の実測

IPA9条件、歌唱1条件、TSP本文2条件を通常のCLIで生成し、固定上流では観測用プローブで初期姿勢・音源・出力倍率をそろえた。12条件、合計831,685フレームで118判定が通過した。強さ、ランプと開大、体型別の目標を独立に計算して照合した。混合体型の口蓋化では舌先Yの目標9.5212 cmと補助の舌体2軸が一致した。`/ɑʃptɑ/` の `/t/` の目標閉鎖は25 ms遅れ、句末 `/ɑʃ/` の `exhale` は15 ms後だった。歌唱 `Show cash` は `/ʃ/` を初音の母音核が始まる0.500秒の手前と、第2音の核が終わる1.354秒の後に置いた。[計測器](../tools/measure_postalveolar_fricative.py)・[時刻と状態量の全比較](../runs/postalveolar-fricative-sh-20261121-a/summary.json)

| 母音間条件 | 口腔最小断面積の中央値 cm² | 唇突出の中央値 cm | 声門下圧の中央値 cmH₂O | 歯への圧力のRMS dyn/cm² |
| --- | ---: | ---: | ---: | ---: |
| 成人男性 `/ʃ/` | 0.2143 | 0.7354 | 6.594 | 30.37 |
| 成人女性 `/ʃ/` | 0.1745 | 0.7354 | 6.552 | 21.06 |
| 子ども `/ʃ/` | 0.1132 | 0.7355 | 6.444 | 21.81 |
| 成人男性 `/ʃ/`、乱流倍率0 | 0.2143 | 0.7354 | 6.594 | 0 |
| 成人男性 `/ɕ/` | 0.1838 | 0.0003 | 6.660 | 31.74 |

母音間 `/ʃ/` の中央25〜75%では、成人男女と子ども全員で歯への乱流が全フレームで活動した。成人男性で乱流倍率を0にすると、歯の圧力注入が消え、PCMの3〜15 kHzのパワーが49.23 dB下がった。最小断面積と唇の突出は表の精度で一致した。独立計算で歯の帯域上限の最大誤差は `1.82×10⁻¹² Hz`、ゲインは `2.12×10⁻²¹`。成人男性 `/tʃ/` の前半には438フレームの閉鎖があり、解放の目標は `/ʃ/` と一致した。先行 `/tʃ/` の128・77フレーム分割のWAVと上流のPCMは、新しい実行でバイト一致した。[乱流と閉鎖の測定](../runs/postalveolar-fricative-sh-20261121-a/summary.json)・[先行の破擦音](../runs/postalveolar-affricate-20261120-repeat/manifest.json)

全条件の固定上流との最大PCM差は `FA01_02` の `4.66×10⁻¹⁰`。成人男性の母音間条件は、舌先Yと唇突出が全フレームで一致した。放射量の時間微分にはフレーム0で `4.75×10⁻¹² cm³/s²` の差があった。これは摩擦の準備より前で、同条件の口腔最小断面積の最初の数値差はフレーム11,383で `2.66×10⁻¹⁵ cm²`、歯の音源の帯域上限と圧力の差は13,632、PCMの最初のビット差は4,097だった。放射の最初の微小差の原因は残る。WASMホストのIPA・歌唱・TSP本文の3条件は、CLIと合計278,656フレームがビット一致した。先行の `/ɹ/` の3条件でもビット一致を再確認した。[差が出たフレーム](../runs/postalveolar-fricative-sh-20261121-a/summary.json)・[WASM照合](../runs/postalveolar-fricative-sh-20261121-wasm/summary.json)

## TSPと保存先

4話者の240本文の入力ハッシュは先行検査と一致し、合成可能だった130件の計画フレーム数も維持した。未対応から `/ʃ/` だけが外れ、合成可能な本文は170件になった。元の調整用 `FA01_02` と `MA01_02` は各133,824フレームを描画した。元の登録8件の入力検査は `/dʒ/` を要する確認用 `FK61_02` と `MK61_02` が残るため不合格で保存した。録音比較と人による試聴は未実施。[再検査](../runs/tsp-active-duration-inspect-20261121-sh/summary.json)・[14録音の比較](tsp-active-duration-after-rhotic.md)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4で実行した。固定上流29試験、候補41試験とClippyが通過した。高密度CSV48件の約1.71 GBをRTL9210B-CGに書き、全フレームを判定した。原CSVのハッシュと、先頭64フレームおよび対象音素の開始・中央・終了の前後64フレームを保存した。合成WAVなどを含む保存成果は約14.4 MB。全成果のパス、サイズ、ハッシュを照合し、時系列が外部ディスクへ保存されたことを確認した。[計測マニフェスト](../runs/postalveolar-fricative-sh-20261121-a/manifest.json)・[WASMの実行記録](../runs/postalveolar-fricative-sh-20261121-wasm/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 ../../.venv/bin/python tools/measure_postalveolar_fricative.py postalveolar-fricative-sh-local-1
cargo build --locked --offline --release --target wasm32-unknown-unknown -p vocal-wasm
npx --offline --yes --package=bun@1.4.4 bun tools/compare_dental_wasm.ts target/wasm32-unknown-unknown/release/vocal_wasm.wasm runs/postalveolar-fricative-sh-local-1/artifacts cases/postalveolar-fricative-sh-wasm.json
../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-active-duration-inspect-sh-local-1
cargo test --locked --offline --workspace
cargo clippy --locked --offline --workspace --all-targets -- -D warnings
```
