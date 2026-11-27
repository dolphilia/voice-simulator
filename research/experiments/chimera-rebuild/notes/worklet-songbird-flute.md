# 実時間AudioWorkletでの鳴禽コールの開始と途中停止

上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。操作画面の `CallActions` はコールIDを送り、再生中のIDを再度押すと停止を要求する。`AudioEngine` の `playCall` と `stopCall` がメッセージを作り、Worklet は種のコール一覧からIDを数値インデックスに引く。`engine_play_call` で未指定値を変換し、`Engine::play_call` が音高と呼気倍率を種の `CreatureVoice` に渡す。停止は同じ経路で `CreatureVoice::stop_call` に届く。上流のゴールデン試験は操作を出力フレーム順に並べ、操作の境界でレンダーを分ける。実時間試験はコール開始・停止、パラメータ更新、レンダーと状態取得の割り当てを計測する。[操作画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L54)・[メッセージ送信](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L296)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L152)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L16)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`CreatureVoice::play_call` は現在の制御時計（秒）、コールID、移調比、呼気倍率を保持する。出力64フレームごとの `eval_call` は、開始時計との差を各パラメータのキーで補間する。指数補間の音高は `p0 × (p1/p0)^u` Hzで、`u` はキー間の時刻比。後続キーが段差なら、その時刻まで前値を保持する。移調比は `3380/2600 = 1.3`、最初の音高目標は `2000 × 1.3 = 2600` Hz。その制御で音高や呼気を平滑化し、コールが所有するパラメータと演奏者のパラメータを合成する。停止は識別子を消し、所有していた目標をその場で演奏者の値へ戻す。平滑値の更新は次の64フレーム境界で行われる。コール呼気の倍率を掛けた目標と手動呼気の大きい方が呼気の無次元目標で、コール停止後も手動呼気が続く。[開始・停止と制御順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[fluteのキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L177)・[CLIの読解と測定](songbird-flute.md)

## 実装前の予測と判定

元の `stopped-48000` の32,160フレームを使う。指示73で識別子が変わり、最初のキーは128で評価される。手動変更の5,371でコールが所有しない気嚢圧パラメータの目標が1.1 kPaになり、平滑値は5,376から変化する。停止17,291で識別子0・目標音高3,000 Hz・呼気目標0.35となり、音高の平滑値は17,344で3,000 Hzへ向かう。手動呼気は24,031で目標0になり、24,064で平滑値が減衰を開始する。通常の61フレーム間隔に加え、指示と制御の直前・直後に観測点を置く。CLIと固定上流のPCM・制御を照合し、キーから独立に計算する制御と末尾20 msのRMSも検査する。上流の基準CSVで取得していない呼気目標とポート流量・実断面は、CLIと独立計算または既存の気道比較を根拠とする。[登録ケース](../cases/worklet-songbird-flute.json)・[入力ケース](../cases/songbird-flute.json)

## 実装と実測

鳴禽用WASMのC ABIから共有の `SongbirdVoice` へ制御一式、コールの開始と停止を渡す。Worklet はCLIと同じ順序でゲート、手動制御、コール操作を適用する。フレーム指定が描画量子の途中にある場合はその位置でレンダーを分ける。コールの観測を指定したケースのJSONには、制御時計、識別子、呼気目標、9個の制御の平滑値と目標を追加した。観測フレームは描画前に決め、描画中は事前確保した領域へ書く。上流の操作画面はメッセージでその場の開始・停止を送る。今回の研究用画面は入力ケースに登録した絶対フレームに従ってそれらを再生する。[C ABI](../crates/vocal-wasm/src/songbird.rs)・[Workletでの適用](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[比較器](../tools/measure_worklet_songbird_flute.py)

| 操作 | 指示フレームで観測したこと | 次の制御更新で観測したこと |
| --- | --- | --- |
| `flute` 開始 | 73で識別子が0から1になった | 128で最初のキーを評価し、移調後の音高目標は2,600 Hz |
| 手動制御 | 5,371で気嚢圧パラメータの目標が1.1 kPaになった | 5,376で平滑値が上昇した |
| 途中停止 | 17,291で識別子が0、音高目標が3,000 Hz、呼気目標が0.35になった | 17,344で平滑音高が3,346.56 Hzから3,290.87 Hzに下がった |
| 手動呼気の解除 | 24,031で呼気目標が0になった | 24,064で平滑呼気が約0.3500から0.3132に下がった |

Chromium 156.0.8078.4 の48 kHzで全32,160 PCMフレームがCLI・固定上流とビット一致した。544観測点でCLIと比較した29列の最大差は0。固定上流から共通して取得した23列も差は0で、稼働中の区間も一致した。キー定義から独立計算した音高、呼気、所有権の切り替え、制御時刻はすべて登録した許容差を満たした。末尾20 msのPCMのRMSはピーク窓の約 `9.93e-7`。ネイティブABIのレンダーと操作で割り当ては0件、WASMメモリの増加もなく、128フレーム間隔の描画で処理時間p95は1 msだった。計時の分解能は1 ms。[初回の18判定](../runs/worklet-songbird-flute-20261120-a/summary.json)

時刻の違いは、発声結果の解釈に影響する。識別子が消えた直後も、次の制御更新まで平滑音高は3,346.56 Hzに留まり、手動呼気が維持される。そのためコールの終了と無音への移行は別々のイベントで観測できる。次は `trill` で連続するゲートの周期、さらにコール切替で残る平滑値を比較する。[CLIの周期コール](songbird-calls.md)

`/tmp` からの再実行でも18判定が通過し、WASM・WAV・書き出しケース・CLIのCSVとWAVの5ファイルのSHA-256、544点の観測値が一致した。描画時間p99は初回1 ms、再実行2 msで、どちらも起動後の8量子を除いた区間で予算超過は0量子だった。既存の持続音を48・96 kHzで再実行し、25判定と前回のブラウザWAV・全観測値の一致を確認した。[コールの再実行](../runs/worklet-songbird-flute-20261120-repeat/manifest.json)・[持続音の回帰](../runs/worklet-songbird-sustain-flute-regression-20261120/summary.json)
