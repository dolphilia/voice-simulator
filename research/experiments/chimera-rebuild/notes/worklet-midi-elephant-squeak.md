# Web MIDIによるアフリカゾウのSqueak

## 固定上流の読解と事前登録

Bestiaryの鍵盤からSqueakを選ぶと、ストアの`noteOn`が音高の役割を持つ声門の`pitch`の範囲8〜45 HzにMIDIを割り当てる。MIDI 60と67から得た16.35・24.50 HzはWorkletとWASMを経由して`CreatureVoice::play_call`に届く。コールはそのHzを基準850 Hzで割った倍率を持つ。倍率は役割のあるパラメータのみに掛かるため、Squeakの弁は`lipPitch`に設定された820→880 Hzの曲線を使う。離鍵の手動呼気は0で、コールは自動呼気を続ける。[鍵盤の割り当て](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[コールの入り口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[値と音高ロール](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L129)・[倍率の適用](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L312)

発音後40 msで呼気目標が1に達し、500 msまでに0になる。弁音高は450 msで880 Hz、モードは500 msで0、呼気圧は同時刻に16 cmH₂Oへ戻る。コールの再発音はこれらの目標の時計を先頭に戻す。平滑値は64フレームごとに進み、弁音高は対数空間で20 ms、モードは30 msで追従する。`Elephant::sample`では前回の鼻腔末端と鼻の入口の圧力差（dyn/cm²）にモードを掛け、弁の速度（cm/s）、高さ（cm）の順に更新する。高さの制限を適用した後、自由開口は2.4×max(高さ, 0) cm²。モードが0.02を超えると、鼻の実断面は自由開口と面積下限4.5×(1−モード)の大きい方になる。弁と声門を更新した後に気道を計算し、鼻先の流量と放射を得る。[Squeakの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L157)・[制御時刻と平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[弁と声門の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L94)・[弁の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/valves.rs#L10)

48 kHzで60、240 ms後に67を押す。再発音の最初の更新でモード目標が1、呼気目標が0に戻り、面積下限が小さくなると予測した。再発音前後の実断面、差圧、弁の高さ・速度と声門状態を観測する。各押下後0〜40 msで実断面を決める項を数え、各離鍵から20〜100 msで鼻先と口端の流量、弁とPCMを採取する。弁の状態行列は観測した差圧を入力に、履歴を持つ場合と再発音時に高さと速度を0にする一更新の対照で比較する。後者は弁の一更新を切り分ける計算で、再計算した気道の波形の比較には使わない。音番号だけを交換する対照には両実装の通常の音源で全フレームの一致を求める。[既存のSqueak基準](worklet-elephant-squeak.md)・[登録条件](../cases/worklet-midi-elephant-squeak.json)

上流のABI試験でコールの配送を、ゴールデン試験で動物コールと弁単体の応答を、実時間試験で発音中のメモリ割り当てを確認する。既存48 kHzの公式順序では、Squeakの弁作動中25,600フレームの実断面を面積下限が決めた。今回は通常画面で短い間隔の再発音を採取し、その間の弁の状態がどこまで引き継がれるかを調べる。[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)

## 実装と比較

既存の「MIDIでアフリカゾウを演奏」からSqueakを選び、採用フレームをCLIへ渡す。Trumpetと同じ計測処理が、通常画面の入力、固定上流、ブラウザとCLI、音番号だけを交換した対照を比較する。Squeak専用の計測は、最初と2回目の開始後に自由開口と面積下限を集計する。再発音の一更新を同じ差圧・固有周波数で計算し、弁の履歴を引き継ぐ計算と高さ・速度を0から始める計算を観測値と照合する。[研究版のMIDI入口](../crates/vocal-core/src/airway/elephant.rs#L268)・[共通計測](../tools/measure_worklet_midi_elephant_trumpet.py)・[Squeakの比較処理](../tools/measure_worklet_midi_elephant_squeak.py)

## 検証結果

48 kHz・1.35秒で18項目すべてに合格した。ブラウザと109フレーム分割のCLIは64,800フレームがビット一致し、1,013時点の46観測列は差0だった。固定上流の画面ではMIDI 60・67が16.3516・24.4997 Hzとしてコールに届き、弁は両方とも820 Hzから始まった。最初の450 ms点は再発音で置き換わり、第2音ではその時点で880 Hzを確認した。採用フレームを固定して音番号を交換した前後で、候補のWAVと全CSV、固定上流のPCM列を含む全CSVがそれぞれ一致した。[正式判定と交換対照](../runs/worklet-midi-elephant-squeak-20261121-final/summary.json)

240 ms後の再発音で、実際のモードは0.5810→0.5992、呼気は0.6894→0.6742となった。呼気目標は0へ戻り、弁の自由開口は0.007692→0.007691 cm²、実断面は1.88556→1.80359 cm²に変わった。再発音時の差圧と固有周波数で弁を0から一更新すると自由開口は約0.0000949 cm²になった。履歴を引き継ぐ場合も、一更新だけ0にする場合も、実断面は同じ面積下限1.80359 cm²だった。離鍵後のPCM RMSは0.00918と0.00959で、鼻先と口端の流量を引き続き観測した。[再発音直前・直後と離鍵後](../runs/worklet-midi-elephant-squeak-20261121-final/summary.json)

各押下後0〜40 msの各1,920フレームで面積下限が実断面を決めた。最小実断面は初回1.34291、再発音後0.65375 cm²で、同じ窓の鼻先流量RMSは206.88・1,441.61 cm³/s。再発音の窓はすでに通気・放射が続いている状態から始まる。全時系列の抜粋を追加集計すると、モードが0.02を超えた37,120フレームで両実装とも面積下限が実断面を決めた。状態行列との自由開口の最大差は4.16×10⁻¹⁷ cm²、独立に求めた実断面との差は0だった。[観測窓](../runs/worklet-midi-elephant-squeak-20261121-final/summary.json)・[候補の保存系列](../runs/worklet-midi-elephant-squeak-20261121-final/artifacts/cli.retained.csv)・[固定上流の保存系列](../runs/worklet-midi-elephant-squeak-20261121-final/artifacts/upstream.retained.csv)

固定RustとのPCM最大差は9.31×10⁻¹⁰で、23サンプルのビットが異なった。肺圧は全区間で一致し、最初の微差は呼気上昇の5フレーム後に肺ポートの流量へ現れた。声門の駆動差圧、弁の駆動差圧、鼻先流量、自由開口の順に差が観測された。弁の実断面は全区間一致した。今回の初期条件で肺流量の微差を最初に生む演算は未特定。独立の放射から得たPCMは候補の全フレームと一致した。[系列ごとの差](../runs/worklet-midi-elephant-squeak-20261121-final/summary.json)

作業ツリーと`/tmp`から再実行した。macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使用した。全サンプルで判定してから通常・交換対照のCSV4本の列を絞り、163.8 MBから56.9 MBへ減らしてRTL9210B-CGへ保存した。全64,800フレームを保持し、成果22ファイルのSHA-256を照合した。固定時刻のSqueakの回帰136項目、共通化したTrumpetのMIDI回帰15項目、Rust40件が合格した。物理MIDIは未検証。[初回](../runs/worklet-midi-elephant-squeak-20261121-a/summary.json)・[実行コマンドと保存記録](../runs/worklet-midi-elephant-squeak-20261121-final/manifest.json)・[既存Squeakの回帰](../runs/worklet-midi-elephant-squeak-20261121-fixed-regression/summary.json)・[TrumpetのMIDI回帰](../runs/worklet-midi-elephant-squeak-20261121-trumpet-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=503316480 \
  ../../.venv/bin/python tools/measure_worklet_midi_elephant_squeak.py worklet-midi-elephant-squeak-local-1
```
