# アフリカゾウの `trumpet` を実時間で観測する

公式CLIの `render creature elephant` は一つの発声器で持続発声、停止、`rumble` を順に描画し、249,600フレームで `trumpet` に切り替える。`CreatureVoice::play_call` は先行コールの所有を解除して制御時計を起点として記録する。`eval_call` は目標を補間し、`control` は64フレームごとに目標を平滑化してから `Elephant::control` に渡す。弁音高は380→520→470 Hzと指数補間される。移調倍率は音高の役割が付いたキーだけに掛かり、`lipPitch` にはその役割がない。置き換え・停止のフレームでは手動目標が復帰し、平滑値は次の制御で更新される。[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[コールの開始と評価](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[ゾウのキーと音高の役割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L126)・[CLIでの読解と実測](elephant-trumpet.md)

`Elephant::control` は平滑モード `m` で声門の開大、振幅、乱流係数を変え、弁モデルに平滑弁音高 `f` を設定する。`Elephant::sample` は声門を更新した後、`m > 0.02` なら気道の前回状態から鼻腔末端圧と鼻の管の入口圧の差 `ΔP` を読み、`m ΔP`（dyn/cm²）を `LipReed::next` に渡す。`ω=2πf`、組織の変位 `h`（cm）、速度 `v`（cm/s）、自然開口高 `h₀`（cm）、時間刻み `Δt=1/fₛ` のとき、加速度は `(S/M)mΔP−2ζωv−ω²(h−h₀)`。半陰的 Euler 法で速度を先に更新し、その速度で変位を進める。変位を −0.05〜0.8 cm に制限し、境界を越える向きの速度を0にする。自由開口は `w max(h,0)`（cm²）。気道に渡す実断面は `max(自由開口, 4.5(1−m))`（cm²）で決める。`m ≤ 0.02` では弁の状態を保持し、実断面を4.5 cm²にする。気道を1サンプル進めてから鼻先流量（cm³/s）と全放射の時間微分（cm³/s²）を観測し、出力段でPCMを得る。[ゾウの制御とサンプル更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L64)・[弁の更新式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/valves.rs#L36)

上流の `golden_creatures.rs` は保存された単発コールのPCMとテレメトリに加え、弁単体の入力差圧を使って TypeScript の保存値と照合する。`warm_creature_voice_does_not_allocate` は開始・編集・停止・観測を含む描画について48と96 kHzで割り当て数を調べる。[コールの固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[弁単体の固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L216)・[描画時の割り当て](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 事前登録

48 kHzの公式順序、44.1 kHzの置き換えと停止、96 kHzの700 Hz指定と指定なしの対照を、既存CLIケースの初期状態・入力・長さで再生する。ブラウザは通常の再生操作で AudioWorklet を開始し、加工前PCMと状態をCLIとビットまたは数値で一致させる。固定上流との比較は既存の許容差を適用する。[今回の計測条件](../cases/worklet-elephant-trumpet.json)・[上流とCLIの固定条件](../cases/elephant-trumpet.json)

| 条件 | 観測点と判定 |
| --- | --- |
| 公式順序 | フレーム249,599から312,064まで連続観測する。開始直前の弁状態を確かめたうえで、差圧、変位、速度、自由開口を独立計算する。コール所有中かつ弁作動中の全サンプルで面積下限が自由開口を上回り、実断面が下限と一致すると予測する。開始0.12〜0.30秒では自由開口に変動があり、鼻先流量の平均除去後RMSが正になると予測する |
| 置き換えと途中停止 | 要求48,021と初回制御48,064、編集62,317、停止86,011と次の制御86,016を含む窓を連続観測する。所有項目と平滑値がCLIと同じサンプルで変わると予測する |
| 音高指定の対照 | 両条件の先頭32,768フレームを連続観測し、初期状態からの独立計算と比較する。指定の有無で全観測列とPCMが一致すると予測する |

実ブラウザで登録レートと128フレーム量子を確認し、加工前PCMの長さ・有限性・量子の連続性を確認する。起動時の2量子を除いて描画時間のp95を各レートの処理予算未満とする。ネイティブのWASM境界では、44.1 kHzのイベント列を描画して割り当て0件を確認する。

## 実装

既存のRust合成器に、WASMのコールIDと初期・手動の弁パラメータを渡す。WASM観測形式を第3版にし、固定発声と `rumble` が使う列に続けて、モード・弁音高の目標と平滑値、声門の開大・振幅・乱流係数、弁の駆動差圧・自由開口・変位・速度を追加する。Workletは量子内のイベントと観測点の直前でレンダーを分け、Rust側の制御時計を継続する。再生操作から取り出した加工前WAVと観測JSONを、同じケースを読み直したCLIおよび固定上流の計測に照合する。[WASMの入口と観測](../crates/vocal-wasm/src/elephant.rs)・[Workletの描画](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[照合手順](../tools/measure_worklet_elephant_trumpet.py)

最初の実行では描画時の割り当てを数えるテストの引数型をコンパイラが推論できず、WASMと画面のビルド後に計測が止まった。フレーム番号を `usize` と明示して別の実行IDで再試行した。[初回の失敗](../runs/worklet-elephant-trumpet-20261120-a/manifest.json)

## 実測

| 条件 | 加工前PCMフレーム | ブラウザ観測行 | 固定上流とのPCM最大絶対差 |
| --- | ---: | ---: | ---: |
| 48 kHzの公式順序 | 333,600 | 66,703 | `3.73×10⁻⁹` |
| 44.1 kHzの置き換え・途中停止 | 98,000 | 1,635 | `1.86×10⁻⁹` |
| 96 kHzの700 Hz指定・自然終了 | 156,000 | 34,695 | `9.31×10⁻¹⁰` |
| 96 kHzの指定なしの先頭区間 | 32,768 | 32,768 | `9.31×10⁻¹⁰` |

全4条件でブラウザの加工前PCMはCLIとビット一致し、観測列も最大差0だった。固定上流とのPCM差は既存の許容差 `1×10⁻⁶` 内だった。公式順序の最初の内部差はフレーム1の肺流量、最初のPCM差は12,783。trumpet開始後は駆動差圧が249,600、自由開口が250,062、PCMが255,193で初めて分かれた。入口弁の実断面は全区間で一致した。[内部状態と出力の比較](../runs/worklet-elephant-trumpet-20261120-b/summary.json)・[固定CLIの差の伝搬](elephant-trumpet.md#残る差と再現)

### 弁の自由開口と気道の実断面

公式順序で弁が作動した60,288フレームすべてで、面積下限 `4.5(1−m)` が自由開口を上回った。差が最小になる254,848フレームでも0.236392 cm²あり、実断面と下限の差は0だった。開始0.12〜0.30秒の8,640フレームでは自由開口が最大と最小で0.124035 cm²変動し、鼻先流量の平均除去後RMSは253.40 cm³/sだった。自由開口が気道の実断面を決めない範囲でも鼻先の放射を観測できた。1.32〜1.50秒の放射統計は64フレーム刻みの135点から求め、早い区間の全点統計と観測密度が異なる。[公式ケースの連続観測と集計](../runs/worklet-elephant-trumpet-20261120-b/summary.json)

連続観測した直前圧力から駆動差圧を計算し、弁の変位・速度を独立した状態行列で積分した。48 kHzの公式区間と96 kHzの両先頭区間で駆動差圧・実断面は最大差0、自由開口は最大 `9.16×10⁻¹⁶ cm²`、弁速度は最大 `1.11×10⁻¹² cm/s` だった。44.1 kHzのブラウザはイベント窓と64フレーム刻みで観測した。連続積分は同じ入力で全サンプルを出したCLI側で確認した。[独立計算と比較](../runs/worklet-elephant-trumpet-20261120-b/summary.json)

### コールの所有と音高指定

44.1 kHzの置き換え48,021では、コールIDが1から2に移り、声門音高・経路の手動目標が31 Hzと0.55に戻った。次の制御48,064で弁音高の目標は380 Hz、平滑値は590.12 Hzになった。編集62,317では声門音高24 Hzと経路0.7が即時に入り、停止86,011で弁音高の手動目標655 Hzが復帰した。平滑弁音高491.06 Hzは次の制御86,016に501.06 Hzへ動いた。[切り替え前後のブラウザ観測](../runs/worklet-elephant-trumpet-20261120-b/summary.json)

96 kHzでは700 Hz指定ありと指定なしの先頭32,768フレームで、加工前PCMと全観測列が一致した。コール開始から0.25秒の24,064フレームで目標は `√(380×520)=444.5222 Hz`、平滑値は439.0716 Hzだった。ブラウザの制御観測と独立計算の最大差は、4条件で弁音高が `3.18×10⁻¹² Hz` だった。[音高指定の対照と補間](../runs/worklet-elephant-trumpet-20261120-b/summary.json)

## 実時間処理と再現手順

研究ディレクトリと `/tmp` から実行し、各142項目が通過した。1 ms刻みの `Date.now` で計った128フレーム量子のp95は、48 kHzで1 ms、44.1 kHzで2 ms、96 kHzの2条件で1 msだった。各レートの処理予算は約2.67、2.90、1.33 msで、起動時の2量子を除いた計測区間で予算超過は0件だった。44.1 kHzのネイティブWASM境界の割り当ては0件だった。[初回合格のコマンドと環境](../runs/worklet-elephant-trumpet-20261120-b/manifest.json)・[別ディレクトリでの再実行](../runs/worklet-elephant-trumpet-20261120-repeat/manifest.json)

2回の実行で観測135,801行と16件のケース・PCM・CLI時系列のSHA-256が一致した。ブラウザから保存した入力で生成したCLI時系列とPCMの8件は、固定上流と比較した既存実行の対応ファイルとも一致した。固定発声の回帰80項目と `rumble` の回帰68項目が通過し、観測行と対照を含む計測ファイルは以前の実行と一致した。Rustの整形・Clippy・リリース試験38件と、固定上流のコール・弁・割り当ての試験7件も通過した。[固定発声の回帰](../runs/worklet-elephant-fixed-trumpet-regression-20261120/manifest.json)・[rumbleの回帰](../runs/worklet-elephant-rumble-trumpet-regression-20261120/manifest.json)

固定上流と照合済みの基準を使い、研究ディレクトリで次を実行する。`worklet-elephant-trumpet-local-1` は未使用の実行IDに置き換える。

```bash
python3 tools/measure_worklet_elephant_trumpet.py worklet-elephant-trumpet-local-1 elephant-trumpet-20261120-repeat
```
