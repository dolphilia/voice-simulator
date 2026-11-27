# アフリカゾウの `squeak` の実時間再生と初期モード

上流の公式CLI `render creature elephant` は同じ `CreatureVoice` で持続音と3コールを順に再生する。各コールを最後のキーから0.5秒後まで描くため、最後の `squeak` は333,600から381,599までを占める。ブラウザの入口では `call` をコール番号に引き直してWASMへ渡す。固定テスト `creatures_match_typescript` はTypeScriptの保存波形とテレメトリを照合し、`valves_match_typescript` は弁単体の差圧応答、`warm_creature_voice_does_not_allocate` はリアルタイムの開始・停止を含む割り当てを確認する。[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[Workletのcall受付](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[波形と弁の固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[割り当て試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`squeak` のキーはゲート、モード、弁音高、呼気圧を持つ。弁音高は820→880 Hz、モードは1→0、呼気圧は20→16 cmH₂Oを線形補間する。ゲートは0.04秒で1、0.50秒で0まで動く。粗さはコールのキーに無いため、先行する `trumpet` を置き換える際に手動目標へ戻る。コールの開始と停止は要求フレームで所有を切り替え、目標曲線の評価と平滑値の更新は64フレームごとの制御で行う。弁音高は目標への一次遅れを対数空間で適用する。 `x` を現在値、`x*` を目標、`a=1−exp(−Δt/τ)` とすれば弁音高は `x(x*/x)^a`、モードは `x+a(x*−x)` で更新する。比例指定は音高の役割に従うため、`squeak` の1050 Hz指定はコールの弁音高を変更しない。[キーの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L158)・[演奏値の復帰と曲線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)

初期モード `m` は最初のコールより前の声門の開大・振幅と弁の作動に作用する。`Elephant::sample` は声門を更新し、`m > 0.02` なら前の鼻腔末端圧と鼻の管の入口圧の差に `m` を掛けて弁に渡す。弁は速度（cm/s）、変位（cm）の順で積分し、自由開口を `2.4 max(h,0)`（cm²）で得る。実断面は自由開口と `4.5(1−m)` の大きい値になる。条件を満たさないときは弁の内部状態を保持し、実断面を4.5 cm²にする。気道の更新後に鼻先流量（cm³/s）を取得し、全放射の時間差分（cm³/s²）を加工前PCMへ変換する。初期モードを変える対照では声門も変わるため、PCM差はモード全体の効果として扱う。[ゾウの分岐と弁](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)・[弁の積分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/valves.rs#L36)・[CLIでの先行実験](elephant-squeak.md)

## 事前登録

固定上流と照合した既存の4条件を同じ初期状態・入力で実ブラウザから再生する。CLIとの加工前PCMはビット一致、観測状態は最大絶対差0、固定上流との比較には既存の許容差を使う。128フレーム量子の連続性、有限性、起動後の処理時間p95がレート別の処理予算を下回ること、44.1 kHzの切り替え・停止を含むネイティブWASM境界での割り当て0件を判定する。[登録したブラウザ条件](../cases/worklet-elephant-squeak.json)・[上流・CLIの比較条件](../cases/elephant-squeak.json)

| 条件 | 観測と予測 |
| --- | --- |
| 48 kHzの公式順序 | 333,599〜360,064を連続観測する。333,600でコールIDが3になり、弁音高の目標は333,631まで470 Hz、次の制御333,632で820 Hzになる。所有中の弁作動25,600フレームで面積下限が実断面を決めると予測する。公式WAVの全381,600フレームと末尾の48,000フレームを照合する |
| 44.1 kHzで置き換え・停止 | 19,917の置き換えで粗さ目標0.68が復帰し、19,968で弁音高などのキーが適用される。25,123の手動編集で所有している項目は35,011の停止で復帰し、平滑値は35,072まで保持されると予測する |
| 96 kHzの初期モード0と1 | 0〜19,264を連続観測し、弁の差圧・変位・速度を状態行列で照合する。初回制御64でモード1の実断面は0.01 cm²未満になり、ゲート上昇の0〜0.04秒に自由開口が実断面を決めるフレーム数はモード0が0、モード1が754と予測する。0.04〜0.20秒の鼻先放射と加工前PCMの差、初期モード以外の入力が同じであることを確かめる |

## 実装

既存のWASMのコール入口でID 3をRustの `ElephantCall::Squeak` に対応させ、同じ観測形式で再生する。実時間画面からケース、加工前WAV、観測JSONを書き出し、CLIでケースを再実行する。48 kHzではコール境界を連続観測し、96 kHzでは初期モードの両条件を同じ区間で切り出して比較する。[WASMのコール入口](../crates/vocal-wasm/src/elephant.rs)・[ブラウザの描画](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[計測器](../tools/measure_worklet_elephant_squeak.py)

第1版の初回実行では、96 kHzの両条件で開始から0.225秒にあたる21,664を観測できなかった。このフレームは連続窓の外側にあり、64フレーム刻みにも載らない。第2版でこのフレームを追加し、入力・測定窓・閾値を保って別の実行IDで再計測した。初回のケース定義と判定は実行記録に保存した。[第1版の実行と欠測](../runs/worklet-elephant-squeak-20261120-a/manifest.json)

## 実測

| 条件 | 加工前PCMフレーム | ブラウザ観測行 | 固定上流とのPCM最大絶対差 |
| --- | ---: | ---: | ---: |
| 48 kHzの公式デモ全体 | 381,600 | 32,016 | `3.73×10⁻⁹` |
| 44.1 kHzの置き換え・途中停止 | 46,000 | 836 | `3.73×10⁻⁹` |
| 96 kHzの初期モード0・自然終了 | 96,064 | 20,466 | `9.31×10⁻¹⁰` |
| 96 kHzの初期モード1・先頭区間 | 32,768 | 19,477 | `4.66×10⁻¹⁰` |

全4条件の加工前PCM 556,432フレームはCLIとビット一致し、観測72,795行は最大差0だった。固定上流とのPCM差は許容差 `1×10⁻⁶` 内だった。48 kHzの末尾48,000フレームでは最大差は `9.31×10⁻¹⁰`。全体の最初の内部差は持続音の肺流量1フレーム目にある。末尾コールでは駆動差圧333,632、自由開口333,633、PCM337,890でそれぞれ最初に差が出た。弁の実断面は固定上流と全区間で一致した。[固定上流・CLI・ブラウザの照合](../runs/worklet-elephant-squeak-20261120-b/summary.json)・[先行のCLI調査](elephant-squeak.md#残る差と再現)

### コールの切り替え

公式デモでは333,600でコールIDが3に変わった。弁音高の目標は次の制御333,632で470 Hzから820 Hzへ移った。呼気のゲートと弁音高を独立計算した結果、弁音高の平滑値の最大差は `3.52×10⁻¹² Hz`。公式順序で弁が作動した25,600フレームのすべてで、気道の断面積を面積下限が決めた。44.1 kHzの置き換え19,917では、先行コールが保持していた粗さが手動値0.68へ復帰した。停止35,011では弁音高の目標が640 Hzに戻り、平滑値は次の制御35,072で862.90 Hzから845.04 Hzへ動いた。[ブラウザの時刻と断面の比較](../runs/worklet-elephant-squeak-20261120-b/summary.json)

### 初期モードの対照

初期モード0から1へ変えると、最初の制御フレーム64の実断面は4.40110から0.009365 cm²になった。制御起点から0.04秒までに自由開口が実断面を決めた数は0から754フレームへ増え、モード1の最初は64だった。どちらの条件でも独立した状態行列との最大差は自由開口で `1.32×10⁻¹⁶ cm²`、弁速度で `2.49×10⁻¹³ cm/s` 以下だった。[初期モードの対照と独立計算](../runs/worklet-elephant-squeak-20261120-b/summary.json)

両WAVと連続観測を先頭から照合すると、変更は最初のフレームで声門開大と入口弁の実断面に現れ、同じ肺圧のもとで声門流量188、壁面放射とPCM189、鼻腔末端圧299、弁流量300、鼻先流量558に差が出た。189のPCMは単精度の非正規化数で、ここでは数値上の差として数える。制御起点から0.04〜0.20秒では鼻先流量の最大絶対差は680.53 cm³/s、PCMは0.18109だった。ここで測った差は声門と入口弁をともに変える初期モードの効果である。[モード0の観測JSON](../runs/worklet-elephant-squeak-20261120-b/artifacts/natural-end-96000.json)・[モード1の観測JSON](../runs/worklet-elephant-squeak-20261120-b/artifacts/initial-mode-one-96000.json)・[差の要約](../runs/worklet-elephant-squeak-20261120-b/summary.json)

## 再現と実時間処理

研究ディレクトリと `/tmp` から実行し、136項目がそれぞれ通過した。72,795観測行とケース・WAV・CLI出力16件のSHA-256が一致した。CLI時系列とWAVの8件は先行の固定上流比較とも一致した。両実行の4条件で、起動時の2量子を除く処理時間のp95とp99は1 ms刻みの `Date.now` で1 ms、予算を超えた量子は0件だった。処理予算は48・44.1・96 kHzでそれぞれ約2.67・2.90・1.33 ms。44.1 kHzのネイティブWASM境界での描画時の割り当ては0件だった。[第2版の実行環境とSHA-256](../runs/worklet-elephant-squeak-20261120-b/manifest.json)・[別ディレクトリからの再実行](../runs/worklet-elephant-squeak-20261120-repeat/manifest.json)

48 kHzの公式デモの先頭333,600フレームと重なる5,214観測行は、前回の `trumpet` のブラウザ計測と一致した。`trumpet` の回帰計測も142項目が通過し、以前の実行と135,801観測行、ケース・WAV・CLI出力16件が一致した。Rustの整形・Clippy・リリース試験39件、固定上流の動物コールと割り当ての試験7件も通過した。[前回のブラウザ計測](../runs/worklet-elephant-trumpet-20261120-repeat/manifest.json)・[trumpetの回帰](../runs/worklet-elephant-trumpet-squeak-regression-20261120/manifest.json)

研究ディレクトリで固定上流と照合済みの基準を指定する。ブラウザ計測の実行IDは未使用の名前に置き換える。

```bash
python3 tools/measure_worklet_elephant_squeak.py worklet-elephant-squeak-local-1 elephant-squeak-20261120-repeat
```
