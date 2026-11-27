# 実時間AudioWorkletでのウェッデルアザラシの `zap` とコール切り替え

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの再生は `AudioEngine.playCall` から `call` をWorkletに送る。Workletは種の定義から索引を取り、`engine_play_call` 経由で `CreatureVoice::play_call` を呼ぶ。手動入力は `cparams` から `set_params` に届く。上流のCLIは一つの音源を継続して使い、先行する `trill` を含む288,000フレームを経て `zap` に入る。上流のゴールデン試験は `seal-call-zap` の波形、10 ms窓のRMS、状態と分割長の影響を検査する。実時間試験は再生中の値変更・停止・観測を含めて割り当てを数える。[再生ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`play_call` は `end_call` で前のコールが持つ目標を手動値へ戻してから、新しい識別子、開始時計（秒）、移調比、呼気倍率を設定する。次の64出力フレーム境界でキーを評価し、目標、平滑値、半正弦の呼気位相、固定肺圧の順に更新する。`zap` の音高（Hz）は `6000 × (1100/6000)^(t/0.15)` に移調比を掛けて範囲制限される。無次元の呼気目標は `max(手動ゲート, 呼気倍率 × max(0, 1−t/0.17))`。音高だけが指定された0.15秒のキーはゲートの線形減衰を変えない。パルス深さは20 msの時定数で0に近づき、深さ0でも位相は進む。肺圧（dyn/cm²）は cmH₂O から換算した圧力基準値、平滑ゲート、パルス倍率の積。声門・気道の状態を引き継ぎ、壁・口端・鼻端の流量（cm³/s）の和を差分して総放射（cm³/s²）を作り、間引き・DC除去・振幅制限を通して単精度PCMを生成する。[コールのキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L115)・[目標の所有と復帰](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[候補のキー評価](../crates/vocal-core/src/seal_voice/call.rs)・[CLIの読解と実測](seal-zap.md)

## 事前登録

48 kHzでは公式デモ先頭の320,160フレームと `zap` 区間288,000以降を比較する。44.1 kHzでは8,301で識別子と音高・パルス深さの目標が変わり、8,320で新しいキーと平滑値・肺圧が変わると予測する。9,437で手動のパルス周波数・デューティ・圧力目標が変わり、深さの目標0は18,048の終了まで保たれる。96 kHzでは位相が進みながら肺圧が `9806.65 × 平滑ゲート` と一致し、21,184で終了すると予測する。全PCMを保存し、観測は64フレーム間隔と指示・終了の前後を選ぶ。CLIとはPCMのビット一致、観測差0で判定し、固定上流・独立計算の許容差は元ケースを使う。

44.1 kHzでは `zap` 指示だけを省いたCLI対照を作る。8,301より前の状態、8,320より前の全PCMと総放射は一致し、次の制御までの `[8320, 8384)` に最初の総放射とPCMの差が現れると予測する。この区間は全出力フレームで両内部サンプルを観測する。初回のビット差と絶対差が `1e-6` を初めて超えるフレームを記録する。処理時間のp95は先頭8量子を除き、128フレームの予算と比較する。[ブラウザの登録条件](../cases/worklet-seal-zap.json)・[元ケース](../cases/seal-zap.json)・[共通の許容差](../cases/seal-trill.json)

## ブラウザの実装と実測

研究画面に3レートの `zap` ケースを加えた。既存のアザラシ用C ABIと同じ `SealVoice` に、あらかじめ登録したフレームでコールと手動制御を渡す。比較器は画面から保存したケースをCLIで再生し、全PCMと観測値を照合する。上流のパルスとキーをフレーム番号から独立に補間した値、CLIの総放射から独立に再構成した間引きとDC除去、PCMも比較した。[画面と再実行ケース](../../../../web/prototypes/chimera-research/src/main.tsx)・[比較器](../tools/measure_worklet_seal_zap.py)

| 出力レート | PCMフレーム・観測点 | `zap` の指示 → 初回制御 → 終了 | 観測結果 |
| --- | --- | --- | --- |
| 48 kHz | 320,160・5,006 | 288,000 → 288,000 → 298,624 | 公式デモの `zap` 区間32,160フレームがビット一致 |
| 44.1 kHz | 28,000・516 | 8,301 → 8,320 → 18,048 | 指示で音高目標1,200 Hz・深さ目標0.25に戻り、初回制御で4,200 Hz・0に更新 |
| 96 kHz | 32,000・505 | 17 → 64 → 21,184 | パルス位相は2回折り返し、深さ0の肺圧は全観測点で `9806.65 × 平滑ゲート` に一致 |

380,160 PCMフレームはブラウザとCLIでビット一致し、27系列の計6,027観測点も一致した。44.1 kHzの手動変更では9,437でパルス周波数の目標31 Hz・デューティ比の目標0.72が反映され、深さの目標はコール終了まで0に保たれた。深さの平滑値は8,320の0.83698から9,437の0.24377へ下がり、18,048で目標が手動の0.45へ復帰した。[ブラウザの状態と独立照合](../runs/worklet-seal-zap-20261120-a/summary.json)

### 切り替えからPCMへ伝わる順序

比較器は8,301の `zap` 指示だけを省いたCLIケースを保存した。続けて `trill` を再生する対照と比べると、8,301で識別子、音高目標、深さ目標に最初の差が出た。平滑音高、平滑深さ、ゲート、肺圧の差は次の制御境界8,320。総放射の最初の差は同じ出力フレームの2番目の内部サンプル16,641で、間引き後とDC除去後の値にも8,320で差が出た。単精度PCMの最初のビット差は8,323で、絶対差が `1e-6` を初めて超えたのは8,343だった。[対照の判定](../runs/worklet-seal-zap-20261120-a/summary.json)

ブラウザの観測JSONと対照CSVについて、8,320〜8,383の各フレームで `wall_0/1` と `oral_0/1` を内部サンプル順に比較した。壁面流量は16,641、口端流量は16,692で初めて異なり、鼻端の列にはこの区間の差がなかった。口端の差が出る前にPCMの差が `1e-6` を超えた。壁面と口端を個別に出力段へ入れる対照を登録すれば、立ち上がりの波形に対する放射経路の寄与を定量化できる。[ブラウザの観測JSON](../runs/worklet-seal-zap-20261120-a/artifacts/switch-44100.json)・[切り替えを省いた対照CSV](../runs/worklet-seal-zap-20261120-a/artifacts/zap-omitted.csv)

### 固定上流との差

44.1 kHzは固定上流ともPCMがビット一致した。48 kHzの全区間では `zap` より前の `trill` 終了後に既知の差が2フレーム残り、最大 `2.78e-17`。96 kHzでは `zap` 終了後24,631の1フレームに `1.78e-15` の差があった。この条件の識別子、平滑値、肺圧は固定上流と全フレームで一致し、最初の数値差は内部104の壁面と総放射で観測した。上流とCLIそれぞれの総放射を同じ出力段に入力すると、DC除去後の値が隣接する単精度値に丸められることをネイティブの基準計測で確認した。[全PCMと差の位置](../runs/worklet-seal-zap-20261120-a/summary.json)・[上流との基準計測](../runs/seal-zap-before-worklet-1/summary.json)

### 実時間と再実行

研究ディレクトリと `/tmp` から実行し、各72項目を通過した。WAV、ケース、CLIのCSV、WASM、切り替えを省いた対照の計16ファイルのハッシュと、ブラウザの全観測行が一致した。44.1 kHzのネイティブ切り替え試験で割り当ては0。計測中の128フレーム量子は連続し、開始後8量子を除いたp95は3レートとも1 ms、最大は48 kHzの再実行で2 msだった。時計は1 ms分解能の `Date.now`。アザラシの `trill` 65項目と鳴禽のコール切り替え22項目の回帰も通過し、WAV・観測行・CLIのCSV・書き出したケースが変更前と一致した。[初回](../runs/worklet-seal-zap-20261120-a/manifest.json)・[別ディレクトリでの再実行](../runs/worklet-seal-zap-20261120-repeat/manifest.json)・[trillの回帰](../runs/worklet-seal-trill-zap-regression-20261120/manifest.json)・[鳴禽の回帰](../runs/worklet-songbird-switch-seal-zap-regression-20261120/manifest.json)

```bash
python3 tools/measure_seal_zap.py seal-zap-local-1
python3 tools/measure_worklet_seal_zap.py worklet-seal-zap-local-1 seal-zap-local-1
```
