# 実時間AudioWorkletでのウェッデルアザラシの `trill`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの再生ボタンは `AudioEngine.playCall`、停止ボタンは `stopCall` を使う。Workletは名前を種ごとの番号に引き直し、WASMの `engine_play_call` と `engine_stop_call` に渡す。音高の省略値は `NaN` から `None` へ変換され、呼気倍率は省略時1。Rustの `CreatureVoice::play_call` は現在の制御時計（秒）を原点にして、キーを次の制御更新から適用する。上流の試験は固定のTS基準とPCM・包絡・観測を比較し、実時間試験で再生・手動操作・停止中の割り当て、全コールのキー解決を調べる。[画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

コールが所有する音高、パルス周波数、深さ、デューティは演奏値と別に目標を持つ。音高とパルス周波数は3.6秒の間に `x₀ × (x₁/x₀)^u` で下降し、音高だけに移調比を掛けて40〜6,000 Hzに収める。コールと手動のゲートの大きい方を6/30 msで平滑化し、半正弦の位相で変調した固定肺圧（dyn/cm²）を気道に渡す。所有していない呼気圧の手動目標（cmH₂O）は再生中も更新される。手動停止では指定フレームで目標が戻り、平滑値は次の64出力フレーム境界で追従する。自然終了は3.9秒のキーから0.05秒経過した後、最初の制御評価で戻る。この制御結果を使って声門、気道、放射、間引き、DC除去、単精度PCMを順に更新する。[上流のキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L108)・[時計と目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[候補コア](../crates/vocal-core/src/seal_voice.rs#L156)・[CLIでの実測](seal-trill.md)

## 事前登録

元のCLIの3条件をそのまま使う。48 kHzの公式デモ先頭6秒で、76,800に開始、163,200で音高584.80766 Hz・パルス15.87451 Hz、266,432に自然終了を予測する。44.1 kHzでは開始指示73、最初の制御128、23,221で目標が1,250 Hz・27 Hzへ戻り、23,232で平滑値が変わる。圧力目標の14 cmH₂Oは10,731で直ちに更新する。手動ゲート0.8がコール0.6を上回り、手動0.35に戻すとコール0.6に戻る。96 kHzでは最初の制御64で音高6,000 Hz、パルス42 Hz、ゲート1.7を予測する。元ケースの全PCM、定期64フレームと操作の前後、末尾の制御・放射を採取し、ブラウザとCLIのPCMのビット一致・状態の差0、固定上流と独立計算は元ケースの絶対許容差で判定する。描画128フレームの連続性と先頭8量子を除いたp95、ネイティブの割り当て数も前回と同じ方法で確認する。[登録条件](../cases/worklet-seal-trill.json)・[キー・閾値と基準入力](../cases/seal-trill.json)

## ブラウザの実装と照合

C ABIから同じ `SealVoice` にパルス制御、手動音高、コールの開始と停止を渡す。ブラウザは登録ケースを読み、呼気イベントとコールイベントが同じフレームにあればCLIと同じ順で呼気から適用する。音高、振幅倍率と開始・停止は登録した出力フレームで再現する。既存の持続音と同じ描画関数で、コール選択時は識別子、制御時計、音高と呼気の目標・平滑値、パルス位相の14列を追加する。WAVと観測JSON、CLIへ渡せるケースを画面から保存できる。[WASM C ABI](../crates/vocal-wasm/src/seal.rs)・[時刻付き再生](../../../../web/prototypes/chimera-research/src/render-creature.ts)・[比較器](../tools/measure_worklet_seal_trill.py)

| 出力レート | PCMフレーム・観測点 | 開始指示 → 最初の制御 | 得られた結果 |
| --- | --- | --- | --- |
| 48 kHz | 288,000・4,506 | 76,800 → 76,800 | 曲線の中点で584.80766 Hz・15.87451 Hz。266,432で自然終了し、900 Hz・18 Hzの手動目標へ復帰 |
| 44.1 kHz | 50,000・799 | 73 → 128 | 1,800 Hzへ移調。23,221で1,250 Hz・27 Hzの手動目標へ復帰し、23,232で平滑値・肺圧が変化 |
| 96 kHz | 12,000・192 | 17 → 64 | 指定7,200 Hzに対して、音高目標6,000 Hz、パルス目標42 Hz、呼気ゲート目標1.7 |

全350,000 PCMフレームがCLIとビット一致し、27系列5,497点の差は0。対数上で補間したキー、サンプル番号から求めた時刻、独立した平滑化と肺圧、および総放射から再構成した出力も登録閾値を満たした。独立肺圧との差は最大 `1.57e-7 dyn/cm²`。48 kHzでゲート終端の264,000に `1.21e-12` が残り、次の264,064で0になった。固定上流も同じで、キー時刻を整数フレームから求める独立計算では264,000で0になる。差は独立照合の許容差内だった。[実測と独立計算](../runs/worklet-seal-trill-20261120-a/summary.json)

### 途中停止直後の肺圧

44.1 kHzのフレーム23,221でコール識別子が0、パルス深さの目標が0.9から0.2になった。次の制御更新23,232では、平滑ゲートが0.60506から0.59302に下がる一方、肺圧は830.71から1,213.07 dyn/cm²に上がった。パルス位相は更新前後ともデューティより大きく、半正弦の成分は0。圧力の基準値は約14 cmH₂Oのままで、深さの平滑値が0.90000から0.85101に下がって、静止区間の倍率 `1−depth` が0.10000から0.14899に上がった。ゲート低下を上回る倍率の上昇が肺圧を押し上げた。停止時に手動値へ戻るパラメータが声門前の圧力へ別々に効く例として、同じ停止時刻で手動の深さだけを0.9にした対照を次の調査候補に残す。[保存されたブラウザの状態](../runs/worklet-seal-trill-20261120-a/artifacts/manual-restore-44100.json)・[呼気の式](../crates/vocal-core/src/seal_breath.rs#L100)

### 固定上流との差

44.1・96 kHzは固定上流ともPCMがビット一致した。48 kHzは自然終了後の2フレームに差があり、最初は274,236、最大は `2.78e-17`。コールの制御と肺圧は全出力フレームで固定上流と一致し、最初の数値差はコールより前の壁面と総放射（内部39）にあった。固定上流と候補それぞれの総放射を独立の同じ出力段に入れると、対応する2フレームがそれぞれの実測値に丸められることをCLI基準で確認した。[差の位置](../runs/worklet-seal-trill-20261120-a/summary.json)・[独立計算による差の再現](seal-trill.md#実装と実測)

### 実時間と再実行

研究ディレクトリと `/tmp` で各65項目が通過し、WAV、再実行ケース、CLIのCSV、WASMの13ファイルと全ブラウザ観測行が一致した。ネイティブの44.1 kHzの開始・手動変更・途中停止中の割り当ては0。ブラウザで計測中の128フレーム量子は連続し、p95は48・44.1・96 kHzの順に2・2・1 msで予算内。時計は1 ms分解能の `Date.now`。48 kHzでは両実行で4 msの予算超過を各1回記録した。共通Workletを使うアザラシの持続音44項目と鳴禽 `buzz → trill` 22項目も通過し、WAV、観測行、再実行ケース、CLIのCSVが変更前と一致した。[初回](../runs/worklet-seal-trill-20261120-a/manifest.json)・[別ディレクトリでの再実行](../runs/worklet-seal-trill-20261120-repeat/manifest.json)・[持続音の回帰](../runs/worklet-seal-sustain-trill-regression-20261120/summary.json)・[鳴禽の回帰](../runs/worklet-songbird-switch-seal-trill-regression-20261120/summary.json)

```bash
python3 tools/measure_seal_trill.py seal-trill-local-1
python3 tools/measure_worklet_seal_trill.py worklet-seal-trill-local-1 seal-trill-local-1
```
