# 体型選択をIPAの発話計画に渡す

較正目標と可動声道を、同じ体型指定のIPA入力から駆動する。/ɑpɑ/、/ɑsɑ/、/ɑzɑ/ を、それぞれ両唇閉鎖と歯茎の狭窄の代表として登録した。[事前登録ケース](../cases/human-body-ipa.json)・[体型別の可動声道](human-body-tract-motion.md)

## 上流コードの読解

- `chimera-cli::render::speech` はIPAを分かち、音素と体型、時刻、音高を `plan_utterance` に渡す。エンジン側の既定F0は110、205、260 Hzで、混合体型では対数を重み付きで足してから指数を取る。音源の状態は110 Hzから始まり、目標へ対数補間で近づく。`render speech` サブコマンドは女性200 Hz、子ども250 Hzを明示指定するので、今回の比較は `Engine::default_f0` の値で計画と音源の目標を統一する。[上流CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[エンジンの初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L26)・[音高の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L540)
- `inventory::phoneme` は目録の基準目標に体型ごとの較正値を重ね、混合では成分ごとに加重平均を取る。/p/ は体型間で同じ `LipAp = −0.25 cm`。/s z/ は `TtX = 6.3 cm` と `Jaw = 0.3 cm` のまま、舌先高さ `TtY` を各体型の較正表から取る。座標は頭部の基準座標で、体型による実形状への写像はこの後。母音の選択には前工程で照合した `vowel_artic` が使われる。[子音目標の解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L264)・[子音の較正表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/consonantTargets.generated.json)・[母音・子音の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L320)
- `oral_gestures_into` は狭窄の主成分を強さ40のジェスチャーにする。/p/ の唇は予測した接触と開口の遅れを秒単位で先行補償する。/s z/ では別の強さ1.2の目標で舌体を前進させる。口の狭窄と同時に指示する声門開大は /s/ で0.3、/z/ で0.09 cm²。スコアで指定した開大は体型長さ比 `k` の二乗に比例して音源側で換算する。[口のジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[声門への反映](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L468)
- `HumanAirway::update_noise` は確定断面の正の最小値を選ぶ。狭窄から前後にずらす距離は `0.9k cm`。狭窄面積の遷移閾値は `k²` 倍し、歯との距離は物理距離を `k` で割って歯への衝突の重みを計算する。渦の大きさには物理距離を使い、ジェット速度 `U/A` と直径 `2√(A/π)` から歯への帯域を求める。登録後に圧力を注入するため、計画・断面・乱流源・圧力・PCMを順に照合できる。[乱流源の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L330)・[閉鎖時刻のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/stop_spans.rs#L72)・[摩擦音のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voiced_fricatives.rs#L29)

```mermaid
flowchart LR
    A["IPAと体型"] --> B["区間時刻と較正済み目標"]
    B --> C["調音・呼気・ピッチのジェスチャー"]
    C --> D["同じ体型の声道・声門"]
    D --> E["閉鎖・狭窄・乱流源"]
    E --> F["放射とPCM"]
```

## 実装と照合

CLIの `speech_voice.body` を、IPAの較正目標を選ぶ処理と可動声道の初期化へ渡す。/s z/ の舌先高さは固定上流の子音較正表を読み、他の目標は各音素の既存の定義に従う。声道は物理距離と体型で正規化した距離を分けて扱い、歯への乱流源の選択と帯域に反映する。既定F0から最初の制御時点の声門周波数を、初期音高110 Hzと時定数0.06秒で別計算した。体型以外の姿勢・音源設定・乱流シードを揃え、128と77の2通りのホストブロックでレンダーした。[発話計画](../crates/vocal-core/src/phonetics/speech.rs)・[子音較正表](../crates/vocal-core/src/phonetics/consonant-targets.generated.json)・[乱流源](../crates/vocal-core/src/airway/human/frication.rs)・[比較器](../tools/measure_body_ipa.py)・[上流のMIT通知](../LICENSE-CHIMERA)

4条件・46項目が通過した。区間時刻は全体型で一致し、ジェスチャー、圧力、選択した乱流源、放射を上流に照合できた。下表の狭窄は、区間の中央50%で歯への源が登録された時点の最小断面の中央値。全条件で中央窓の全フレームに歯への乱流が出た。独立計算した歯への上限周波数との差は最大 `3.64×10⁻¹² Hz` だった。[数値と判定](../runs/bodyipa-20261120-a/summary.json)

| 体型 | /s/ 舌先の目標（cm） | /z/ 舌先の目標（cm） | /s/ 狭窄（cm²） | /z/ 狭窄（cm²） | /p/ の計画開始から実測閉鎖まで（ms） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 成人男性 | 9.11100 | 9.09700 | 0.09781 | 0.13527 | 21.87 |
| 成人女性 | 9.11700 | 9.10400 | 0.07986 | 0.10995 | 21.81 |
| 子ども | 9.12600 | 9.11400 | 0.05520 | 0.07807 | 19.96 |
| 3体型の混合 | 9.11718 | 9.10406 | 0.07875 | 0.10952 | 21.92 |

PCMの上流との差は最大 `4.66×10⁻¹⁰`。数値差は出力フレーム0の歯までの距離にすでに観測され、4条件とも `3.56×10⁻¹⁵ cm` 未満だった。乱流源の離散的な選択は一致した。PCMのビット差が最初に観測されたのは男性16139、女性1963、子ども15980、混合15939フレーム。全条件とも許容差を超えなかった。成人男性の既存 /s/ は変更前後でWAVと観測CSVが一致し、既存ブラウザIPAの12項目も通過した。[本計測の記録](../runs/bodyipa-20261120-a/manifest.json)・[成人男性の変更前](../runs/bodyipa-20261120-s-before/manifest.json)・[変更後](../runs/bodyipa-20261120-s-after/manifest.json)・[ブラウザ](../runs/bodyipa-20261120-worklet/manifest.json)

`/tmp` からの再実行も46項目が通過し、入力・計画・観測・PCM・要約の41ファイルでSHA-256が一致した。体型を選べる入口はネイティブCLIのIPAケース。今回の発話は /p s z/ の3子音を含み、音声の検証はこの条件に対応する。[再実行](../runs/bodyipa-20261120-repeat/manifest.json)・[再開地点](../progress.md#未達の条件と次の作業)
