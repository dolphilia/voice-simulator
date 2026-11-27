# Web MIDIによるアメリカアリゲーターの持続音

## 固定上流の読解と事前登録

BestiaryのHeld voiceでは、`noteOn` が保持音を記録して音高と呼気目標を更新する。音高は `creatureKeyHz` が発声域の幾何平均に中央のドを近づける整数オクターブを求め、許容域を外れた値を2倍か半分に折り返す。`noteOff` は最新の保持音へ復帰し、全解放では呼気を0にして音高目標を保つ。アメリカアリゲーターの `pitch` は12〜120 Hz、既定28 Hzなので3オクターブ下がる。MIDI 60と67の目標は約32.70 Hzと49.00 Hz。音番号0は1 Hz程度の値から16.35 Hzへ折り返される。[固定版の入力と音域計算](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L95)・[保持順の更新](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[種の定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L84)

固定版の `CreatureVoice::control` は64出力フレームごとに音高を対数上で50 ms、呼気を上昇12 ms・解放60 msで更新する。続く `Alligator::control` は固定肺圧に水柱cmの設定値と980.665、平滑化した呼気ゲートを掛けて dyn/cm²とし、声門に平滑化後の音高と周期の変動を渡す。内部96 kHzで、`step_glottis` が気管末端と咽頭入口の圧力差から声門面積（cm²）を更新し、同じ内部サンプルで気道を進める。口端・鼻端・壁面の体積流量の時間微分を間引き・DC除去・振幅制限してf32のPCMを出す。固定上流のABIテストではWorkletを経由して管とパラメータが正しく届くことを照合し、既存のゴールデン試験ではPCM・状態と描画分割を比較する。[固定版の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[肺圧・声門・鼻腔](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L45)・[声門と気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)・[ABIテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)

条件は48 kHz、60→67→60→全解放の後に0を押して解放する。保持音の変化から250〜370 msで音高の目標と平滑値、声門・壁面・口鼻の放射およびPCMを計測し、解放後330〜405 msでは減衰を観測する。持ち替えで呼気が保たれ、全解放後にゲートが0.0045以下へ下がると予測した。実測の声門F0には周期変動が入るため、独立の50 ms平滑値との比較は音源に渡したF0で行う。出力段は内部放射系列を入力に、別のFIRとDC除去式で検査する。[登録ケースと判定条件](../cases/worklet-midi-alligator.json)・[固定発声の音響](alligator-fixed-voice.md)

## 実装と比較

「MIDIでアメリカアリゲーターを演奏」は共通のMIDI所有管理で、保持中の最後のキーと全解放を得る。Workletは次の描画量子の先頭に採用し、出力フレームとAudioContextフレームを保存する。`AlligatorVoice::select_midi_note` は他種と共有する鍵盤写像を12〜120 Hzに対して呼び、通常の `set_params` と `set_gate` を使う。書き出した `alligator_voice.events[].held_midi.note` をCLIで再実行しても、同じRustの入力と気道の描画を使う。[画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[共通写像](../crates/vocal-core/src/creature_midi.rs)・[音源](../crates/vocal-core/src/airway/alligator.rs)・[CLI](../crates/vocal-cli/src/alligator_case.rs)

固定ブラウザのMIDIキーで設定した周波数とゲートを、候補の採用フレームに揃えて固定Rustの通常PCMを得る。同時に固定上流で声門枝の面積・流量と壁面・口鼻の放射を採取し、同じ駆動差圧を与えた観測用声門で位相・瞬時F0を確認する。48 kHzで1出力フレームに対応する2内部サンプルを分けて観測する。候補のWAVは109フレーム分割のCLIからも得る。[固定版の観測器](../tools/upstream_alligator_probe.rs)・[ブラウザ比較の入口](../../../../web/prototypes/chimera-research/tools/capture-midi-songbird.mjs)・[測定器](../tools/measure_worklet_midi_alligator.py)

## 検証結果

Chromium 156.0.8078.4、48 kHzの3秒、仮想MIDIの6操作で、事前登録した10項目すべてを満たした。採用時刻の最初の押下からの相対差は入力予定に対して最大2.00 msだった。候補のWorkletとCLIは144,000フレームのWAVがビット一致し、2,250時点の観測33列の差はすべて0。壁面と口鼻の内部放射を独立計算のFIR・DC除去・振幅制限に渡したときも、出力PCMの差は0だった。独立の平滑化式との最大差は、音高で2.34×10⁻¹³ Hz、肺圧で3.64×10⁻¹² dyn/cm²だった。[正式結果](../runs/worklet-midi-alligator-20261121-coordinate/summary.json)

声門の瞬時F0の保持窓の中央値は、60→67→60→0の順に32.68、48.98、32.53、16.42 Hz。キー0でも声門面積は最大1.39 cm²になり、壁面・口端・鼻端の流量RMSはそれぞれ354.81、621.23、492.01 cm³/sだった。全解放から330〜405 msの窓で呼気ゲートは最大0.00404、解放後のPCMのRMSは直前の保持窓の0.0063%以下だった。[時系列と測定窓](../runs/worklet-midi-alligator-20261121-coordinate/summary.json)

固定RustとのPCM最大差は9.31×10⁻¹⁰。制御値と声門の位相・瞬時F0は一致した。最初の微差は押下採用から47サンプル後の内部サンプル14,639で、声門の駆動差圧と流量に同時に現れた。次の内部サンプルで壁面と総放射に現れ、口端では14,730、鼻端では14,734だった。駆動差圧の最大差は2.11×10⁻¹⁰ dyn/cm²、放射の時間微分の最大差は3.93×10⁻⁷ cm³/s²。駆動差圧と流量のどの演算で最初に差が生じたかは未特定。[固定Rustとの差](../runs/worklet-midi-alligator-20261121-coordinate/summary.json)

初回と別ディレクトリからの再実行も全10項目が合格した。最初の2回の結果では最初の微差の座標欄を `first_nonzero_frame` と記録していたため、正式計測では `first_nonzero_internal_sample` に改めた。計算と判定条件は初回から共通。固定発声86項目、Bellow 234項目、アザラシコールMIDI 11項目、Rust40件の回帰確認も通過した。[初回](../runs/worklet-midi-alligator-20261121-a/summary.json)・[別ディレクトリからの再実行](../runs/worklet-midi-alligator-20261121-final/summary.json)・[固定発声](../runs/worklet-midi-alligator-20261121-fixed-regression/summary.json)・[Bellow](../runs/worklet-midi-alligator-20261121-bellow-regression/summary.json)・[アザラシコールMIDI](../runs/worklet-midi-alligator-20261121-seal-regression/summary.json)

実行環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。高密度CSV2本は全内部サンプルの比較後、登録済みの列と窓を268.6 MBから72.9 MBへ抜粋した。RTL9210B-CGに保存した成果14ファイルのサイズとSHA-256を照合した。再計測には研究ワークスペースで以下を実行する。[コマンドと保存先の記録](../runs/worklet-midi-alligator-20261121-coordinate/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 \
  ../../.venv/bin/python tools/measure_worklet_midi_alligator.py worklet-midi-alligator-local-1
```
