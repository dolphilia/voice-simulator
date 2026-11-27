# Web MIDIによるアフリカゾウのRumble

## 固定上流の読解と事前登録

Bestiaryの`KeysMode`でRumbleを選ぶと、`noteOn`は`pitch`の8〜45 Hzに鍵盤を割り当て、`playCall`から選んだIDとHzを送る。Workletは`engine_play_call`を呼び、WASMの発声器にコールを設定する。離鍵では押下の一覧を更新し、Breatheがオフなら手動の呼気目標は0のまま。振幅は既定1で、キー速度はここで使われない。ABI試験ではWorkletへコールとパラメータを送り、ゴールデン試験は固定波形と描画分割を、実時間試験は開始・終了とテレメトリ経路の割り当てを検査する。[鍵盤とストア](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletの入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)

`CreatureVoice::play_call`は前のコールの目標を演奏者へ返し、現在の制御時計を起点に次のコールを始める。Rumbleの基準は14 Hz。開始から2.7秒にかけて15→12 Hzの音高目標を線形に補間し、鍵盤周波数÷14 Hzを掛けて8〜45 Hzに収める。鼻側の割合は1、発声モードは0。呼気の目標は0〜300 msで0→1、2.7秒まで1、3.1秒で0となる。3.15秒を超えた次の更新で、音高・鼻への配分・モードの目標を演奏者の値へ返す。Rumbleの移調は、音高の役割を持つ声門の`pitch`に適用される。弁の`lipPitch`は制御点で設定されたHzで動く。[コールの条件](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L129)・[コール所有と補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[既存のRumble単独比較](worklet-elephant-rumble.md)

64出力フレームごとにコール目標を評価し、音高は対数空間で50 ms、呼気は上昇12 ms・減衰60 msで平滑化する。固定肺圧は16 cmH₂O×980.665×呼気でdyn/cm²に換算する。各内部サンプルは声門位相や気道の圧力・流量を引き継いで進む。モード0では鼻の弁の開口を4.5 cm²に固定し、鼻先・口端・壁面の流量の時間微分を合成してPCMを得る。48 kHz設定では出力フレームと内部サンプルが一対一に対応する。[更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[肺圧・弁・放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)

48 kHzで60を押して390 ms後に離し、初回の780 ms後に67で再発音する。最初の音高目標が約17.52 Hzと26.25 Hzになり、再発音時には呼気目標が0へ戻っても実際の呼気と声門位相は続くと予測した。各離鍵後25〜120 msの声門開口、呼気、鼻先・口端の流量とPCM、自然終了後220〜350 msの呼気とPCMを測る。ケースの初期姿勢は鼻側の割合1、モード0の既定値なので、自然終了時に目標値が切り替わることを音高で観測する。鼻の配分とモードは公開された目標を照合する。[登録条件](../cases/worklet-midi-elephant-call.json)

## 実装と計測

「MIDIでアフリカゾウを演奏」の音色選択にRumble、Trumpet、Squeakを加えた。押下と解放は `elephant_voice.events[].midi_call` にコールID、音番号、押下状態と採用フレームを保存する。CLIとWorkletは `ElephantVoice::midi_call` を共有し、押下では既存の `play_call` を呼び、離鍵は自動呼気に作用しない。固定版のBestiaryが実際に送った2つの音高で、候補の採用時刻にそろえて上流の音源を描画する。独立モデルは登録した制御点から、2回の開始・離鍵後の継続・自然終了までを求める。[候補の音源](../crates/vocal-core/src/airway/elephant.rs)・[CLIの入力](../crates/vocal-cli/src/elephant_case.rs)・[通常画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[計測器](../tools/measure_worklet_midi_elephant_call.py)

## 検証結果

48 kHz・4.65秒の正式計測は16項目すべてに合格した。ブラウザと109フレーム分割のCLIで、WAVの223,200フレームはビット一致し、3,488時点の46観測列の差は0。独立計算との差は音高目標で最大7.11×10⁻¹⁵ Hz、平滑音高で1.14×10⁻¹³ Hz、肺圧で5.46×10⁻¹² dyn/cm²だった。採取した放射から独立に得たPCMも全サンプルで一致した。[正式結果](../runs/worklet-midi-elephant-call-20261121-onset/summary.json)

MIDI 60・67の開始目標は17.5196・26.2497 Hz。再発音の境界で呼気目標は1→0、実測呼気は1→0.9780、平滑音高は16.57→16.77 Hzとなった。同じ1フレームで声門位相は0.000344周期進み、鼻先流量は628.72→629.51 cm³/sだった。弁は4.5 cm²を維持した。離鍵後の窓で、鼻先流量RMSは1,122.95・1,080.88 cm³/s、PCMのRMSは0.101・0.159だった。2回目の開始から約3.151秒で自然終了し、音高目標は14 Hzへ戻った。終了後220〜350 msの呼気は最大0.00163だった。[採用境界と離鍵後の時系列](../runs/worklet-midi-elephant-call-20261121-onset/summary.json)

固定RustとのPCM最大差は3.73×10⁻⁹で、ビットの異なる値は26サンプルだった。肺圧は全区間一致し、最初の微差は呼気上昇の2フレーム後、肺ポートの3サンプル目の流量に現れた。入口のコンプライアンス、直列枝、壁の流量を含む独立式では、両方の気管入口圧が3.3611238061212765 dyn/cm²に丸まった。肺ポートの前回の運動量項は研究版の `(慣性 ÷ 刻み) × 流量` と固定版の `(慣性 × 流量) × 刻みの逆数` で差が出た。研究版1.6990150140465283、固定版1.6990150140465279 cm³/sを再現し、独立計算で運動量項だけを固定版の値に置き換えると固定版と一致した。後続系列では気管末端圧、声門流量、壁面放射の順に微差が見えた。[最初の3サンプルと差の位置](../runs/worklet-midi-elephant-call-20261121-onset/summary.json)・[固定版の枝・壁の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)・[研究版の枝の式](../crates/vocal-core/src/airway/network.rs#L189)

第1版は作業ディレクトリと `/tmp` の両方から再実行して15項目が合格した。第2版では肺ポートの3サンプル目の独立式を加えた。macOS 15.6.1 arm64、Chromium 156.0.8078.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使用した。CSV2本は全点で比較した後に229.6 MBから76.7 MBに絞ってRTL9210B-CGへ保存した。再発音、離鍵、終了後の窓が両方の抜粋に入り、成果17ファイルのSHA-256を照合した。既存Rumble回帰68項目、持続音MIDI回帰14項目、Rust40件も合格した。物理MIDIと、Trumpet・SqueakそれぞれのMIDIによる弁の挙動は未検証。[第1版](../runs/worklet-midi-elephant-call-20261121-a/summary.json)・[第1版の再実行](../runs/worklet-midi-elephant-call-20261121-final/summary.json)・[第2版と保存記録](../runs/worklet-midi-elephant-call-20261121-onset/manifest.json)・[既存Rumbleの回帰](../runs/worklet-midi-elephant-call-20261121-rumble-regression/summary.json)・[持続音MIDIの回帰](../runs/worklet-midi-elephant-call-20261121-held-regression/summary.json)

研究ディレクトリから再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 \
  ../../.venv/bin/python tools/measure_worklet_midi_elephant_call.py worklet-midi-elephant-call-local-1
```
