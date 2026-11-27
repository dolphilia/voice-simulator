# Web MIDIでウェッデルアザラシのコールを鳴らす

## 固定上流の読解と事前登録

Bestiary の `KeysMode` でLaser chirpを選ぶと、`noteOn` はアザラシの40〜6,000 Hzの発声域に音番号を割り当て、`AudioEngine.playCall` へIDとHzを送る。Workletは `engine_play_call` を呼び、固定Rustの `CreatureVoice::play_call` が今の制御時計から選択したコールを開始する。離鍵はストアの保持一覧を更新する。演奏者がBreatheを押していない条件では鍵盤からの手動呼気は0で、コールの呼気はフレーズが制御する。キー速度はこの経路の振幅に使われない。[MIDIの振り分け](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[コールのWASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)・[上流の再発音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)

Laser chirpのIDは `zap`。制御点は開始時の6,000 Hz・呼気1・パルス深さ0、150 msの1,100 Hz、170 msの呼気0。目標音高は開始から150 msかけて指数補間し、各点を「鍵盤から得た周波数÷6,000 Hz」で移調する。呼気は170 msまで線形に下がり、その後は0。出力64フレームごとに目標を更新し、音高は10 msの時定数で平滑化する。呼気の時定数は上昇6 ms、減衰30 ms。たとえば再発音で呼気目標が1へ戻っても、平滑化後の呼気は直前の値から立ち上がる。末尾制御点から50 msを超えた更新で、コールが所有していた目標を演奏者の値に戻す。[zapのキー定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L115)・[包絡・補間・平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L268)・[割り当て試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)

48 kHzで60を押して45 ms後に離し、最初の押下から135 ms後に67でコールをやり直す。第1音の開始目標は約523.25 Hz、第2音は約783.99 Hz。第2音で150 msを迎えた音高目標は約143.73 Hz。再発音で目標が先頭へ戻ること、平滑化値が前の発声から続くこと、解放後も声門が開いてPCMが続くことを検査する。音高と呼気の独立計算には、固定版の公開キー定義と既存のパルス・出力計算を使う。[時刻と判定条件](../cases/worklet-midi-seal-call.json)・[先行するコールの比較](worklet-seal-zap.md)・[上流のキー定義](../runs/seal-zap-before-worklet-1/artifacts/upstream-zap.json)

## 実装と計測

「MIDIでウェッデルアザラシを演奏」の「鍵盤で鳴らす音」から4種のコールまたは持続音を選ぶ。コールの押下・解放と採用フレームを `seal_voice.events[].midi_call` として書き出す。候補の `SealVoice::midi_call` は鳴禽と共通の鍵盤写像で周波数を求め、押下を既存のコールへ渡す。解放もイベントとして記録し、包絡はその時点から進み続ける。CLIとWorkletがこのRustの処理を共有する。[研究版のUI](../../../../web/prototypes/chimera-research/src/main.tsx)・[共有の鍵盤写像](../crates/vocal-core/src/creature_midi.rs)・[アザラシのコール](../crates/vocal-core/src/seal_voice.rs)・[CLIのイベント](../crates/vocal-cli/src/seal_voice_case.rs)

固定版ブラウザでは通常のBestiaryの画面から仮想MIDIを送り、コール命令が音源へ渡る際のIDと音高を記録する。研究版の採用フレームで、その押下命令を固定版の公開Rustレンダーへ入れる。声門の枝面積・壁と口鼻の放射は実際のネットワークから読み、位相・瞬時F0の観測用声門の面積も実際の枝面積と照合する。候補のPCMは別の109フレーム分割のCLIと独立の放射からの出力計算にも照合する。[通常画面の比較](../../../../web/prototypes/chimera-research/tools/capture-midi-songbird.mjs)・[固定版の声門と放射](../tools/upstream_seal_voice_probe.rs)・[独立計算と判定](../tools/measure_worklet_midi_seal_call.py)

## 検証結果

別ディレクトリから再実行して11項目が合格した。採用フレーム8,064と14,464の開始目標は523.25 Hzと783.99 Hz。再発音の直前は音高130.70 Hz、呼気0.392で、採用直後は音高163.45 Hz、呼気0.513へ進んだ。目標値を783.99 Hz・呼気1に切り替えてからも平滑化が続いた。第2音は150 ms後に143.73166 Hzへ達し、フレーム25,024で終了して演奏者の900 Hzへ戻った。解放後13〜37 msの採取窓では2回とも声門が0.24 cm²以上開き、PCMのRMSは0.0581と0.0666だった。採用間隔の登録値との差は最大3.33 ms。[開始、解放、終了の測定値](../runs/worklet-midi-seal-call-20261121-final/summary.json)

ブラウザと109フレーム分割のCLIは43,200フレームのWAVがビット一致し、観測675点の比較系列も差0だった。固定上流のネイティブ実行は離鍵イベントを送らずに同じフレームから呼び出し、PCMの最大差は1.39×10⁻¹⁷だった。固定版との最初の微差は最初の押下から19出力フレーム後の壁面放射で、放射の時間微分の最大差は6.57×10⁻⁸ cm³/s²。微差が生じる内部演算は未特定。独立計算では音高目標の最大差4.32×10⁻¹² Hz、呼気目標の最大差1.48×10⁻¹⁴で、放射から計算したPCMは全サンプルで一致した。[比較と独立計算の判定](../runs/worklet-midi-seal-call-20261121-final/summary.json)

初回はブラウザ録音とCLIを照合できたが、声門観測用の粗さの時定数を独立計算へ渡しておらず、判定前に停止した。既存のアザラシの粗さの設定を参照して再実行し、初回の出力と例外も残した。正式試行は全フレームで判定してから、CSV2本を36.2 MBから13.9 MBへ抜粋した。WAV、ケース、環境、コマンドと元CSVのSHA-256は作業用RTL9210B-CGの実行から参照できる。[初回の停止](../runs/worklet-midi-seal-call-20261121-a/failure.json)・[正式マニフェスト](../runs/worklet-midi-seal-call-20261121-final/manifest.json)

アザラシの持続音MIDI回帰11項目、既存zap回帰72項目、鳴禽のコールMIDI回帰12項目、Rust40件が通過した。物理MIDI機器とLaser chirp以外のアザラシコールの個別MIDI比較は残る。[持続音回帰](../runs/worklet-midi-seal-call-20261121-held-regression/summary.json)・[既存zap回帰](../runs/worklet-midi-seal-call-20261121-zap-regression/summary.json)・[鳴禽コール回帰](../runs/worklet-midi-seal-call-20261121-songbird-regression/summary.json)

研究ディレクトリで次のコマンドを実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=402653184 \
  python3 tools/measure_worklet_midi_seal_call.py worklet-midi-seal-call-local-1
```
