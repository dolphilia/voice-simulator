# 鳴禽の持続音を実時間 AudioWorklet で観測する

上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。WASM の `engine_set_creature` は種IDとパラメータ名を解決し、`Engine::set_creature` で気道を含む新しい発声状態を作る。その際、切替前の呼気目標を引き継ぐ。WASM は切替時に管の断面積と圧力RMS、音源状態などからテレメトリの配置を決め、記憶域を確保する。Worklet の `creature` メッセージがこの切替を呼び、`process` が受け取った量子の長さで `engine_render` を呼んで f32 PCM を取り出す。テレメトリの通知は6量子ごと。上流の鳴禽の音源テレメトリは左右の開口比を返す。[WASM切替と記憶域](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L465)・[Engineの切替と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L131)・[Workletの操作と描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L158)・[鳴禽の音源テレメトリ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)

`CreatureVoice::control` は各出力64フレームの先頭で目標を読み、呼気を `g + (goal - g) × (1 - exp(-dt/τ))` で更新する。内部刻みは48 kHz出力で4倍、96 kHzで2倍。気嚢の圧力は `10000 × pressure_kpa × g` dyn/cm²。左右の無次元の開口比を `0.03 × opening` cm² のポート面積にしてから、共通気道の伝搬でポートの体積流量（cm³/s）を更新する。放射流量の時間微分を間引き、DC除去と振幅制限を経た f32 PCM が出力になる。上流のゴールデン試験はPCMと状態を比較し、実時間試験はゲート操作・レンダー・テレメトリの割り当て数を計測する。[制御と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[音響の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[割り当て試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 実装前の予測と判定

元の持続音ケースの48・96 kHzを使用する。CLIの `SongbirdVoice::render` をWASMからも呼び、イベントの絶対出力フレームでWorkletのレンダー区間を切れば、描画量子内で指示が変わってもCLIの加工前PCMとビット一致する。48 kHzでは停止11567が11584の制御で反映され、量子単位へ丸めると11648まで遅れる。96 kHzでは開始147の反映が192となり、量子単位へ丸めると256まで遅れる。61フレームごとと末尾で、出力1フレームに対応する内部サンプルの最後の状態を保存する。独立のゲート式、開口からの面積、持続中の両側流量、停止後のPCMの減衰を検査する。上流に同じ条件で観測済みのPCM・呼気・気嚢圧力・開口を照合し、左右ポートの流量は再実装のCLIで照合する。[登録ケース](../cases/worklet-songbird-sustain.json)・[持続音の原ケース](../cases/songbird-sustain-pcm.json)・[実装前CLIの298判定](../runs/songbird-sustain-before-browser-1/summary.json)

## 実装と実測

鳴禽のWASMハンドルは切替時に `SongbirdVoice` と最大128フレームの記憶域を作る。Worklet は量子の途中でもイベントと観測点で区切り、合成コアのカウンタを引き継ぐ。観測点の内部サンプル番号は `(出力フレーム + 1) × 間引き倍率 - 1`。実時間AudioContextの開始待ちを経てから出力し、同じf32値を音声出力と保存用に書く。画面から保存したケースをCLIに渡すと、`observe_syrinx` で左右ポートの実断面積と流量を追える。[WASMのC ABI](../crates/vocal-wasm/src/songbird.rs)・[実時間のWorklet](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[CLIの観測列](../crates/vocal-cli/src/songbird_voice_case.rs)

| 出力レート | 出力フレーム | 観測点 | ゲートの反映（開始・停止） | 持続区間の左右の流量RMS（cm³/s） |
| --- | ---: | ---: | --- | --- |
| 48 kHz | 36,000 | 591 | 128・11,584 | 14.72・18.95 |
| 96 kHz | 72,000 | 1,181 | 192・23,168 | 14.24・17.60 |

Chromium 156.0.8078.4 で、加工前PCMは両レートとも現在のCLI・固定上流とビット一致した。CLIと比較した8列の最大差は全て0。固定上流から得た呼気・気嚢圧・左右開口にも差がなかった。ゲートの独立計算との差は最大 `2.22e-16`、左右の面積の独立計算との差は0 cm²。末尾20 msのPCMのRMSは持続区間比で約 `4.20e-18`。ネイティブABIのレンダー中の割り当ては両レートとも0件で、WASMの線形メモリのバッファはレンダー中に変わらなかった。25項目が通過し、`/tmp` からの再実行でもWASM・WAV・再実行ケース・CLI観測の計9ファイルのSHA-256と、ブラウザの8列すべての値が一致した。[初回の合格結果](../runs/worklet-songbird-20261120-c/summary.json)・[別ディレクトリからの再実行](../runs/worklet-songbird-20261120-final/manifest.json)

初回のブラウザ計測は完了待ちがタイムアウトした。次の計測ではPCM・状態の照合は通過したが、起動待ちを各コールバックで再評価したため、発声中の `currentFrame` は1,152フレーム（9量子）ずつ進んだ。起動待ちを合成開始前だけに適用して、発声開始後の間隔は128フレームになった。修正後の処理時間は両レートでp95・p99が1 ms。計時は分解能1 msの `Date.now` で、96 kHzでは初回1量子が予算を上回り、再実行では0量子だった。[タイムアウトの記録](../runs/worklet-songbird-20261120-a/manifest.json)・[修正前の描画間隔の判定](../runs/worklet-songbird-20261120-b/summary.json)・[再実行の処理時間](../runs/worklet-songbird-20261120-repeat/summary.json)

今回の入力は固定パラメータと呼気の開始・停止。ブラウザのコール開始と途中停止では、コール識別子、キーの目標、制御時計がいつ変わるかを同じ方法で追う。現在の観測ではポート流量をCLIと比較し、同じ入力における上流のポート流量が得られれば追加で照合できる。[CLIのコール試験](songbird-calls.md)

既存の鳴禽CLIを再計測し、298判定が通過した。実装前と比べて26件の波形と時系列のSHA-256も一致した。固定母音のブラウザ回帰では、鳴禽の状態表示を加えたことで計測スクリプトの `status` の検索が複数要素に合致した。検索を固定母音の完了表示に絞った後、固定母音の12判定が通過した。[鳴禽CLIの回帰](../runs/songbird-sustain-after-browser-20261120/summary.json)・[固定母音の計測エラー](../runs/worklet-fixed-voice-songbird-regression-20261120/manifest.json)・[固定母音の再実行](../runs/worklet-fixed-voice-songbird-regression-20261120-repeat/summary.json)
