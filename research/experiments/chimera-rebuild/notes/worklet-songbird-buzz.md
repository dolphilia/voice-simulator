# 実時間AudioWorkletでの鳴禽コール buzz の初回パルス

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`AudioEngine.playCall` は識別子、指定音高（Hz）、呼気倍率（無次元）をWorkletへ送信する。`call` の分岐が識別子を種のコール一覧で解決し、`engine_play_call` と `Engine::play_call` を介して `CreatureVoice::play_call` へ渡す。状態にはコールの開始時計（秒）、音高と呼気の倍率を保持する。上流のゴールデン試験はコールの開始や移調、停止、状態観測を固定サンプルで実行し、128・1・77・4,096フレームに分けたPCMを照合する。実時間試験は開始・停止とレンダー・テレメトリ中の割り当てを測る。[操作の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L296)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[WASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L152)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`songbird::def` の `buzz` は初期キーで呼気0、基準音高1,200 Hz、駆動0.95、張力0.15、純度0.1、左右の音程差0.5半音を設定する。各周期 `P=0.07 s` の `iP+0.02 s` で呼気1、`iP+0.06 s` で0.35を指定し、全体の末尾キー0.6秒で0にする。`eval_call` は補間値に呼気倍率を掛け、手動呼気の目標との最大値を平滑化する。音高目標は基準1,200 Hzに `1500/1200` を掛けて1,500 Hz。出力96 kHzは内部192 kHzの2倍で計算し、制御は64出力フレームごと。目標の評価、呼気の平滑化、気嚢圧への反映、鳴管と気道・放射、間引きとDC除去、f32 PCMの順に進む。[キー生成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L148)・[内部レート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L148)・[コール制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[平滑化と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[再実装のキー](../crates/vocal-core/src/songbird_voice/call.rs#L156)

## 実装前の予測と判定

`buzz-96000` の105,600フレームを使う。指示147の前後と191、0から64フレーム刻みの制御更新直後、末尾を観測する。最初の制御は192。呼気倍率0.8に対して目標の閾値0.6は、キー値0.75に相当する。最初の交差は `0.02×0.75=0.015 s`、2回目は `0.06+0.03×(0.75−0.35)/(1−0.35)` 秒。したがって理想の初回間隔は約6,092.31フレーム、後続間隔は6,720フレームとなる。独立した線形補間と64フレーム格子、および既存のキー列から計算する制御系列で照合する。終了は経過時計が0.65秒を超える最初の制御で、格子境界の丸めを1制御刻み以内として評価する。ブラウザとCLIはPCMのビット一致、固定上流とのPCMは `1e-6` 以内を判定に使う。CLIの基準で記録済みの減衰部の微小差を、放射、間引きとDC除去の順に調べる。実時間評価は起動後8量子を除き、128フレーム描画のp95を約1.33 msの予算と比較する。[登録ケース](../cases/worklet-songbird-buzz.json)・[第2版の起動条件](../cases/songbird-calls-v2.json)・[固定上流とCLIの基準](../runs/songbird-buzz-before-worklet-1/summary.json)

## 実装と実測

ブラウザの「鳴禽のコール」に `buzz` の登録ケースを加え、既存のWorkletとC ABIで音高と呼気倍率を渡した。観測点1,654個に加え、加工前PCMとCLI用の再実行ケースを保存する。比較器は登録した立ち上がりを有理数で解き、呼気目標と平滑呼気の上向き交差を検出する。ネイティブの割り当て試験には同じ96 kHzの入力を開始から末尾まで追加した。[ブラウザのケース選択](../../../../web/prototypes/chimera-research/src/main.tsx)・[周期と合成段の比較器](../tools/measure_worklet_songbird_buzz.py)

呼気目標0.6の上向き交差は1,664、7,744、14,464、21,184、27,904、34,624、41,344、48,064フレーム。全8回が有理数モデルを64フレーム格子に丸めた位置と一致した。初回間隔6,080フレームは連続時刻からの予測と約12.31フレーム差、後続6間隔は6,720フレーム。平滑呼気が0.6に達するのは目標より初回320フレーム、後続は384フレーム遅い。識別子は開始147で4となり、192の最初のキーで音高目標が1,500 Hzになった。呼気目標の最大は0.8だった。[交差と制御の実測](../runs/worklet-songbird-buzz-20261120-repeat/summary.json)

自然終了は62,592フレームだった。経過時刻を厳密な有理数とした場合、62,592で0.65秒ちょうどになり、`elapsed > 0.65` を満たすのは次の62,656になる。実際の累積時計は62,592で約 `3.35e-15` 秒進み、同じ判定が一つ早い制御で成立した。キーの実時間を変更しても同様な境界が生じるか、整数フレーム時計と現行時計の対照で調べられる。[終了時計の観測](../runs/worklet-songbird-buzz-20261120-repeat/summary.json)

## PCMの比較と実時間評価

ブラウザとCLIは全105,600フレームでビット一致。固定上流との最大差は、減衰中の81,552フレームにある1サンプルの約 `5.56e-22` だった。CLIと共通の29列、固定上流と共通の24列は全観測点で差が0。独立計算との差は呼気目標最大 `1.11e-16`、平滑呼気最大 `2.78e-16` だった。[波形と内部状態の判定](../runs/worklet-songbird-buzz-20261120-repeat/summary.json)

CLIと固定上流で最初に観測できた微小差は、放射の内部サンプル391と、間引き・DC除去後の出力フレーム195だった。195で両者の呼気と気嚢圧は0。最初の正の呼気目標は256で、左右の開口、平滑音高、気嚢圧、呼気の各時系列は上流と一致した。再実装の口腔食道腔では、フレーム128と192の観測値を体積の式に代入すると目標体積が0.394707から0.422964 cm³に変わる。気嚢からの加圧前にも可動断面が体積流量を生む経路があり、最初の放射差はこの区間にある。差の由来を絞るには、呼気を0に保ったまま口腔食道腔の目標体積を固定する対照を作り、節点圧と放射を比較する。[口腔食道腔の目標](../crates/vocal-core/src/airway/songbird.rs#L82)・[体積流量の計算](../crates/vocal-core/src/airway/network/geometry.rs#L134)・[合成段の差](../runs/worklet-songbird-buzz-20261120-repeat/summary.json)

Chromiumヘッドレスシェル156.0.8078.4で、研究ディレクトリと `/tmp` からの両回とも20項目を通過した。WASM、再実行ケース、ブラウザとCLIのWAV、CLIのCSVの計5ファイルのSHA-256と全観測値が一致した。起動直後の8量子を除く817量子のp95・p99は両回1 ms、128フレームの描画間隔は連続した。計時は `Date.now` の1 ms刻みで、最初の実行は1量子が1.33 msの予算を超え、再実行での超過は0だった。ネイティブのレンダー中の追加割り当ては0。`chirps` と `trill` のWAVと観測値も回帰確認した。[最初の実行](../runs/worklet-songbird-buzz-20261120-a/manifest.json)・[別ディレクトリからの再実行](../runs/worklet-songbird-buzz-20261120-repeat/manifest.json)・[chirps回帰](../runs/worklet-songbird-chirps-buzz-regression-20261120/summary.json)・[trill回帰](../runs/worklet-songbird-trill-buzz-regression-20261120/summary.json)
