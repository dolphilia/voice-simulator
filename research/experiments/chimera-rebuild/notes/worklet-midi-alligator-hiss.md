# Web MIDIで鳴らすアメリカアリゲーターのHiss

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの `noteOn` は音番号60・67を約32.70・49.00 Hzに折り返し、`playCall` がWorkletの `call` とWASMの `engine_play_call` へ送る。Hissの定義は基準音高を持たず、音高・粗さに触れる制御点もない。`CreatureVoice::play_call` は倍率を1にし、現在の制御時計をコールの始点とする。`noteOff` で押下の一覧が空になっても手動呼気は0のままで、コールが指示する呼気は自動で続く。[音番号の経路](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletの処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[Hissの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L110)・[コール開始](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

開始直後の目標は開大指示1、口0.9、呼気0。開大指示と口は1.3秒で0と0.02へ向かう。呼気目標は100 msで1となり、1.2秒まで維持して1.3秒で0になる。最後の制御点から50 msを超えた更新で口と開大指示の目標が手動値へ戻る。64出力フレームごとの `control` が目標と平滑値を更新し、肺圧、声門の開大と周期振幅、口先の断面目標へ反映する。平滑開大指示を h とすると開大は 0.02＋0.8h cm²、周期振幅は 0.9(1−h) cm²。声門の開大が有声ゲートを下げる。口先の目標断面は 0.05＋12×口 cm²で、`mammal_noise` は2 cm²未満の狭窄を目標断面から探す。実断面はその後、各内部サンプルで補間する。[コール補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[Hissの制御値の反映](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)・[有声ゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱流源の登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L77)

各内部サンプルで声門を駆動した後、気道の `compute_noise` は前サンプルの枝流量 U と断面 A から Re＝2|U|/(ν√(πA)) を求める。Re が1,800を超えると、二乗差を12,000の上限スケールで飽和させ、声門の乱流係数を得る。声門源は毎サンプル最初に、口腔源は登録されている場合だけその次に乱数を取る。声門の乱数列は250 Hzハイパスと4,000 Hzローパス2段を通り、係数と流向で符号付きの枝注入圧（dyn/cm²）を得る。枝と節点を更新して口端・鼻端・壁の放射を計算し、96 kHzの内部系列を48 kHzへ間引き、DC除去を経てPCMを出す。[乱流の状態と更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[既存の独立計算](worklet-alligator-hiss.md)

固定上流のゴールデン試験はTypeScriptの波形・包絡・テレメトリを比較する。実時間試験は全コールの制御点の解決と、発音・編集・停止・観測時の割り当てを検査し、ABI試験はWorkletを通じたコールとテレメトリの配送を調べる。[音響試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

48 kHz・2.4秒で約560 ms間隔の2回の押下を採取する。採用時刻を保ったまま60と67を交換しても、各実装の波形と内部系列が全て一致すると予測する。再発音で呼気の目標は0へ戻り、平滑呼気は0.95以上で連続する。開大指示と口の平滑値は上がる一方、口先はすでに2 cm²より広い。各離鍵後25〜100 msと各押下後400〜500 msでは、口腔源が外れ、有声ゲートはほぼ0で、声門からの乱流注入圧とPCMが残ると予測する。圧力を乱数と前サンプルの流量から独立に計算し、固定上流で乱流倍率を0にした同時刻のPCM RMSが通常の10%以下になるか確かめる。[登録条件](../cases/worklet-midi-alligator-hiss.json)

## 実装と比較

研究版の「MIDIでアメリカアリゲーターを演奏」でHissを選ぶと、既存のWASM観測から、両方の内部サンプルの声門乱流レベル、枝注入圧、口腔乱流レベルを観測JSONに加える。再実行ケースにも観測指定を保存する。通常のMIDI経路が採用した時刻で109フレーム分割のCLIと固定Rustを走らせ、Bellow・Growlと共通の制御・音響比較に乱流3系列と声門注入圧の独立計算を加えた。[MIDIパネル](../../../../web/prototypes/chimera-research/src/main.tsx#L1023)・[MIDIのRust入口](../crates/vocal-core/src/airway/alligator.rs#L262)・[WASMの系列定義](../crates/vocal-wasm/host/alligator.ts#L28)・[独立計算](../tools/measure_alligator_hiss.py#L94)

音番号を交換する対照では、候補で押下・離鍵の音番号、固定Rustで各押下に渡す周波数だけを入れ替える。通常・交換入力の全WAVまたは全CSVを各実装内でSHA-256照合する。同一だった交換出力はハッシュを記録して重複分を取り除き、入力ケースは保持する。乱流倍率を0にした対照は、同じ固定Rust・入力・初期状態を使い、すべての乱流源のレベルが0であることを確認する。[比較と対照の計測コード](../tools/measure_worklet_midi_alligator_hiss.py)

## 検証結果

研究ディレクトリと`/tmp`からの実行は、いずれも89項目に合格した。48 kHzの115,200フレームはブラウザとCLIでビット一致し、1,800時点の61観測列の差は0。固定上流の通常画面で32.7032 Hz・48.9994 Hzがコールへ渡り、候補の音高目標と平滑値は28 Hzを保った。採用フレームで音番号を交換した対照では、候補のWAV・全CSVと固定上流の全CSVが各実装内で一致した。[正式判定・音番号交換のハッシュ](../runs/worklet-midi-alligator-hiss-20261121-final/summary.json)・[初回結果](../runs/worklet-midi-alligator-hiss-20261121-a/summary.json)

560 ms後の再発音で呼気目標は1から0、平滑呼気は約1から0.97802へ動いた。開大指示の平滑値は0.60051→0.61361、口先実断面は6.71252→6.71337 cm²で、口腔乱流源は外れたままだった。2回目の押下から1,350.67 ms後に演奏者の口と開大指示が目標に戻った。両離鍵後25〜100 msと両押下後400〜500 msは有声ゲート・口腔乱流レベルともに0だった。離鍵後窓の声門注入圧RMSは149.54・154.36 dyn/cm²。乱流倍率0の対照では4窓のPCM RMSが通常時の0.0581〜0.0633%に下がった。[境界、放射、乱流の対照結果](../runs/worklet-midi-alligator-hiss-20261121-final/summary.json)・[乱流倍率0の保存系列](../runs/worklet-midi-alligator-hiss-20261121-final/artifacts/muted-upstream.retained.csv)

前サンプルの断面・流量から独立に求めた声門乱流レベルとの差は0、枝注入圧の最大差は9.24×10⁻¹³ dyn/cm²だった。固定上流との最初の微差は初回押下の2番目の内部サンプル16,385に、口端流量・壁の体積流量・総放射で現れた。声門乱流レベルと注入圧に微差が出たのは内部17,757だった。口付近の最初の差を生んだ演算は未特定。正式実行のPCMは固定Rustと2フレームで最大3.64×10⁻¹²異なり、候補の放射から独立に計算したPCMは候補とビット一致した。[系列ごとの最初の差と許容差](../runs/worklet-midi-alligator-hiss-20261121-final/summary.json)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。全サンプルの判定後にCSV3本を347.6 MBから148.3 MBへ絞り、各230,400内部サンプルをRTL9210B-CGに保存した。交換出力の重複除去はこの容量差と別に行った。物理MIDIと許可画面は未検証。[コマンド・環境・保存先](../runs/worklet-midi-alligator-hiss-20261121-final/manifest.json)・[候補のCSV](../runs/worklet-midi-alligator-hiss-20261121-final/artifacts/cli.retained.csv)・[上流のCSV](../runs/worklet-midi-alligator-hiss-20261121-final/artifacts/upstream.retained.csv)

正式実行の成果20ファイルと回帰実行の成果のSHA-256を照合した。固定時刻のHissは311項目、共通計測を使うGrowlのMIDI比較は76項目、`cargo test --locked --workspace`は40件に合格した。[固定Hissの回帰](../runs/worklet-midi-alligator-hiss-20261121-fixed-regression/summary.json)・[GrowlのMIDI回帰](../runs/worklet-midi-alligator-hiss-20261121-growl-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_worklet_midi_alligator_hiss.py worklet-midi-alligator-hiss-local-1
```
