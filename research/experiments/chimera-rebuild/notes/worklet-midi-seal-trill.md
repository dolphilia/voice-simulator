# Web MIDIで鳴らすウェッデルアザラシのDescending trill

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。BestiaryでDescending trillを選ぶと、`noteOn` が音高ロールの40〜6,000 Hzに鍵盤を合わせ、音番号60・67を1オクターブ上げた523.25・783.99 Hzを `playCall` に渡す。WorkletとWASMを経由する `CreatureVoice::play_call` は、現在の制御時計をコール開始にし、渡されたHzを基準3,600 Hzで割る。離鍵時に手動呼気は0のままで、コールの呼気を打ち切らない。[音番号割り当て](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L100)・[MIDIからコール](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[開始時刻と音高比](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

コールの最初の制御点は音高3,600 Hz、パルス42 Hz、深さ0.9、デューティ0.5、呼気1。3.6秒まで音高とパルス周波数を指数補間し、終点は95 Hzと6 Hz。役割が設定された音高だけに鍵盤の倍率を掛け、40〜6,000 Hzへ制限する。呼気は3.6秒まで1、3.9秒で0になり、そこから50 msを超えた最初の制御更新で演奏者の目標へ戻る。64出力フレームごとに音高とパルス周波数を対数空間で平滑化し、深さ・デューティ・呼気を線形で追従させる。[制御点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L97)・[補間、平滑化、レンダーの順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)

`Seal::control` は周期単位のパルス位相に「平滑パルス周波数×制御間隔」を加え、1周期に折り返す。位相がデューティ未満なら正弦項は sin(π×位相÷デューティ)、それ以外は0。肺圧は「呼気圧×980.665×平滑呼気×(1−深さ＋深さ×正弦項)」dyn/cm²。再発音はコールの経過時計を変え、パルスの累積位相を引き継ぐ。各内部サンプルでは前の圧力差で声門を更新し、気道を一歩進めて放射、間引き・DC除去、単精度PCMの順につなぐ。48 kHzでは1出力フレームにつき内部2サンプルを評価する。[パルス位相と肺圧](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[声門と気道](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)・[放射以降](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L365)

上流のゴールデン試験は単発Descending trillの48 kHz・195,360フレームをTypeScript基準の波形・包絡・観測値に照合する。実時間試験は開始・手動編集・停止と観測中に割り当てがないことを調べ、ABI試験はWorkletからのコール選択とテレメトリを検証する。[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)

48 kHz・6秒でMIDI 60を鳴らし、約1.41秒後に67で再発音する。同じ経過時間では音高目標が鍵盤の倍率で異なり、パルス周波数目標は一致すると予測する。再発音の同じ制御入力で、位相を引き継ぐ場合と0から一更新する場合の肺圧を計算する。第2音は約2.95秒で音高下限40 Hzに達する一方、パルス周波数目標は3.6秒の6 Hzまで低下すると予測する。両離鍵後25〜100 msの発声と、同じ採用フレームでのCLI・固定上流の系列を照合する。[登録条件](../cases/worklet-midi-seal-trill.json)・[固定時刻の基準](worklet-seal-trill.md)

## 実装と比較

研究版と固定上流の通常画面でDescending trillを選び、仮想MIDIを入力する。研究版の採用フレームを保存し、109フレームずつCLIで再実行する。同じ採用フレームと上流画面が送った周波数を固定Rustへ渡す。Laser chirpのMIDI計測を共通にし、Descending trillの2本の曲線と位相の検証を加えた。固定Rustの比較用CSVでは肺圧とパルス周波数を照合し、研究版のパルス位相をブラウザ、CLI、独立計算で比較する。位相を0にする対照は一制御更新分の肺圧を計算する。[研究版のMIDI画面](../../../../web/prototypes/chimera-research/src/main.tsx#L1041)・[呼気の実装](../crates/vocal-core/src/seal_breath.rs#L112)・[共通計測](../tools/measure_worklet_midi_seal_call.py)・[曲線と再発音の検査](../tools/measure_worklet_midi_seal_trill.py)

## 初回の判定と閾値の改訂

第1版は、独立に計算した平滑ゲートの差が許容値1.00×10⁻¹²を超えた。最初に超えたのは、第2音の開始から3.672秒後の出力251,520。ここでフレーム差は3.672秒、累積制御時計の差は3.6719999999996675秒だった。0.3秒の下降の傾きで換算したゲート目標差は約1.11×10⁻¹²となり、候補0.7600000000011085と独立計算0.7599999999999997の差を説明した。全下降区間のゲート目標差の上限は1.192×10⁻¹²程度で、平滑ゲートの最大差は1.1813×10⁻¹²、固定Rustと候補の差は0だった。独立ゲートの閾値だけを2.00×10⁻¹²へ改訂した。初回の判定と元の全CSVは作業用ディスクに保存した。[第1版の判定](../runs/worklet-midi-seal-trill-20261121-a/summary.json)・[第1版の入力と実行記録](../runs/worklet-midi-seal-trill-20261121-a/manifest.json)・[第2版の条件](../cases/worklet-midi-seal-trill.json)

## 検証結果

第2版は15項目に合格した。48 kHzの288,000フレームはブラウザとCLIでビット一致し、4,500時点の31観測列は差0だった。固定上流の通常画面でMIDI 60・67から523.2511・783.9909 Hzが送られ、採用フレームは8,320、30,336、75,904、93,312だった。両離鍵後25〜100 msのPCM RMSは0.02403・0.05031で、コールと呼気が継続した。[正式判定と採用フレーム](../runs/worklet-midi-seal-trill-20261121-final/summary.json)

押下後0.2507・0.8・1.2秒の3点で、第2音の音高目標は第1音の約1.498倍で、パルス周波数目標はそれぞれ36.678、27.255、21.956 Hzで一致した。第2音は開始2.948秒後の出力217,408で40 Hzの下限に達した。その時点のパルス周波数目標は8.5351 Hzで、開始3.6秒後に6 Hzに達した。3.9507秒後に音高900 Hz、パルス周波数18 Hzなどの手動目標が戻った。[移調と下限の観測](../runs/worklet-midi-seal-trill-20261121-final/summary.json)

再発音でパルス周波数の目標は19.635→42 Hz、平滑値は19.842→20.825 Hzになり、位相は0.42090→0.44867周期へ進んだ。肺圧は5,188.64→3,778.10 dyn/cm²となった。直前の位相から一更新した独立式は3,778.10 dyn/cm²に一致し、位相だけを0にしてから一更新した対照は2,512.65 dyn/cm²だった。初回は半正弦の上り側で再発音を採用し、肺圧は9,197.73→9,631.35 dyn/cm²へ上がった。どちらも平滑呼気は約1で、位相を引き継ぐ式が実測した肺圧に一致した。[正式実行の再発音](../runs/worklet-midi-seal-trill-20261121-final/summary.json)・[初回の再発音](../runs/worklet-midi-seal-trill-20261121-a/summary.json)

固定Rustとの最初の微差は第1音の開始から39内部サンプル後、出力8,339の2番目の内部サンプルで壁面流量と総放射に現れた。肺圧は固定上流と一致した。差を生む個別の演算は未特定で、PCMには6フレームで最大1.42×10⁻¹⁴の差が残った。独立計算したパルス位相の最大差は2.75×10⁻¹²周期、肺圧は1.48×10⁻⁷ dyn/cm²だった。放射から独立に計算したPCMは研究版とビット一致した。[系列ごとの差と独立計算](../runs/worklet-midi-seal-trill-20261121-final/summary.json)

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。正式実行は `/tmp` から起動し、全サンプルを判定した後、CSV2本を277.0 MBから147.8 MBに絞った。各222,464行をRTL9210B-CGに保存し、正式実行の成果15ファイルのSHA-256を照合した。物理MIDIと許可画面は未検証。[コマンド・環境と保存先](../runs/worklet-midi-seal-trill-20261121-final/manifest.json)・[候補の時系列](../runs/worklet-midi-seal-trill-20261121-final/artifacts/cli.retained.csv)・[上流の時系列](../runs/worklet-midi-seal-trill-20261121-final/artifacts/upstream.retained.csv)

固定時刻のTrill回帰は65項目、共通計測を使うLaser chirpのMIDI回帰は13項目、`cargo test --locked --workspace`は40件が合格した。[固定時刻の回帰](../runs/worklet-midi-seal-trill-20261121-fixed-regression/summary.json)・[Laser chirpの回帰](../runs/worklet-midi-seal-trill-20261121-zap-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1342177280 \
  ../../.venv/bin/python tools/measure_worklet_midi_seal_trill.py worklet-midi-seal-trill-local-1
```
