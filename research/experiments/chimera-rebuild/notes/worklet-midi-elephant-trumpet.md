# Web MIDIによるアフリカゾウのTrumpet

## 固定上流の読解と事前登録

Bestiaryの`KeysMode`でTrumpetを選ぶと、`noteOn`は音高の役割を持つ`pitch`の8〜45 Hzに鍵盤を割り当てる。入力のHzは`playCall`、Worklet、WASMを経由して`CreatureVoice::play_call`へ届く。倍率はそのHzをコールの基準470 Hzで割った値。`eval_call`はキーの補間後、役割付きのパラメータにだけ倍率を適用する。Trumpetのキーは`lipPitch`に380、520、470 Hzを設定する。`lipPitch`は20 msの対数平滑化と弁の固有周波数に使われる。MIDI音番号の交換で倍率そのものは変わり、声門音高と弁音高の目標は変わらないと予測した。[鍵盤の割り当て](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[Trumpetのキーとパラメータ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L129)・[倍率の適用](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L312)

64出力フレームごとに、時刻0〜0.5秒で弁の目標を380→520 Hz、0.5〜1.1秒で520→470 Hzへ指数補間する。呼気は0.05秒で最大、1.25秒までに0へ戻る。モードは1から0へ下降し、声門の開大は0.05＋3×モード cm²、振動振幅は1.6×(1−モード) cm²になる。肺圧は呼気と水柱cmをdyn/cm²へ換算した値。各サンプルで、鼻腔末端と鼻の入口の差圧にモードを掛け、まず弁速度、次に高さを半陰的Euler法で更新する。弁の高さを制限し、面積には「正の高さ×幅」と「4.5×(1−モード)」の大きい方を使う。モードが0.02以下のときの面積は4.5 cm²。1.30秒を超えた制御更新で演奏者の目標に復帰する。[制御と弁](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)・[弁の式と変数の単位](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/valves.rs#L10)・[制御の終了条件](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

固定上流のABI試験でコール命令の通過、実時間試験で状態更新中の割り当て、ゴールデン試験で移調付きコールと描画分割を照合する。既存のTrumpet計測では指定周波数だけを変えた96 kHzの固定レンダーが一致している。今回は48 kHz、通常の2つのブラウザ画面でMIDI 60を押して離し、67で再発音して離す。採用フレームと初期条件を固定した対照では、MIDI音番号だけを交換して候補と固定上流の音響系列・PCMを比較する。弁の目標は制御点、平滑値は時定数、弁の高さと速度は採取した差圧を使う独立の状態行列に照合する。弁・声門・鼻先の流量は各離鍵後25〜120 ms、弁音高は開始と250、500、1,100 msの制御刻みで観測する。最初の1,100 ms点は次の押下の後に当たるため、再発音で置き換わったことを記録する。[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[既存の固定Trumpet](worklet-elephant-trumpet.md)・[登録条件](../cases/worklet-midi-elephant-trumpet.json)

## 実装と比較

既存の「MIDIでアフリカゾウを演奏」からTrumpetを選び、Web MIDIとAudioWorkletで採用した押下・離鍵のフレームを取得する。対照には、保存した `elephant_voice.events[].midi_call.note` の60と67だけを交換してCLIで再実行する。固定版はBestiaryが発行した2つの周波数と候補の採用時刻で描画し、対照では固定版への周波数の順を交換する。各経路で全CSV、研究版ではさらにWAVのSHA-256を比較する。独立の弁計算はベースラインの圧力差から状態行列を進め、差圧・弁の高さと速度・自由開口・鼻の実断面を別々に検査する。[既存のMIDI音源](../crates/vocal-core/src/airway/elephant.rs#L268)・[コール側のパラメータ](../crates/vocal-core/src/airway/elephant/call.rs#L130)・[対照の計測器](../tools/measure_worklet_midi_elephant_trumpet.py)

## 検証結果

正式計測は48 kHz・2.65秒で15項目すべてに合格した。固定上流の画面では60・67が16.3516・24.4997 Hzとしてコールへ届いた。発音・離鍵時刻を保って音番号だけを交換すると、候補のWAVと全観測CSV、固定上流のPCM列を含む全観測CSVは交換前後で一致した。候補のブラウザと109フレーム分割のCLIも127,200フレームがビット一致し、1,988時点の46観測列はすべて差0だった。[正式判定と全CSVの照合](../runs/worklet-midi-elephant-trumpet-20261121-final/summary.json)

弁音高の目標は両方の開始で380 Hz、約250 msで444.71 Hz、500 msで520 Hzとなった。最初の押下から1,100 msの観測点は再発音で置き換わり、第2音では同じ経過時刻に470 Hzを確認した。平滑値の独立計算との最大差は3.13×10⁻¹² Hzだった。離鍵後の窓では弁の自由開口が最大と最小で0.04746・0.03324 cm²変わり、鼻先流量の交流成分のRMSは91.14・51.66 cm³/sだった。両窓を抜粋から追加集計すると、候補・固定上流とも4,560フレームずつ、実断面がすべて面積下限と一致した。独立の弁計算との差は自由開口で1.08×10⁻¹⁵ cm²、速度で1.10×10⁻¹² cm/sだった。[観測窓](../runs/worklet-midi-elephant-trumpet-20261121-final/summary.json)・[候補の抜粋](../runs/worklet-midi-elephant-trumpet-20261121-final/artifacts/cli.retained.csv)・[固定上流の抜粋](../runs/worklet-midi-elephant-trumpet-20261121-final/artifacts/upstream.retained.csv)

候補と固定RustのPCM最大差は9.31×10⁻¹⁰で、ビットが異なる値は72サンプルだった。肺圧は一致し、最初の微差は呼気上昇から3フレーム後の肺ポート流量に現れた。続いて声門の駆動差圧、弁の駆動差圧、自由開口、鼻先流量に微差が見えた。鼻の弁の実断面は全区間一致した。今回の条件で肺流量の微差を最初に生む演算は未特定。採取した放射から独立に計算した候補のPCMは全点で一致した。[系列ごとの差](../runs/worklet-midi-elephant-trumpet-20261121-final/summary.json)

第1回と`/tmp`からの再計測で判定条件は共通。環境はmacOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1。全フレームで判定してから、通常・交換対照のCSV4本を356.6 MBから94.9 MBへ絞ってRTL9210B-CGに保存した。両離鍵窓とすべての観測可能な曲線上の点が抜粋に入り、成果22ファイルのSHA-256を照合した。既存のTrumpetの回帰142項目とRust40件が合格した。物理MIDIとSqueakの個別MIDI比較は未検証。[初回](../runs/worklet-midi-elephant-trumpet-20261121-a/summary.json)・[実行コマンドと保存記録](../runs/worklet-midi-elephant-trumpet-20261121-final/manifest.json)・[既存Trumpetの回帰](../runs/worklet-midi-elephant-trumpet-20261121-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=754974720 \
  ../../.venv/bin/python tools/measure_worklet_midi_elephant_trumpet.py worklet-midi-elephant-trumpet-local-1
```
