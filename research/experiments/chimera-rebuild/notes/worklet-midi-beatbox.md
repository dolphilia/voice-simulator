# Web MIDIによるビートボックスの低音とハムの予約

## 固定上流の読解と事前登録

`connectMidi` は入力ポートとチャンネルごとにキーを管理し、音番号が初めて押された時点と最後に解放された時点を `useStore.noteOn`・`noteOff` へ渡す。ビートボックスへ切り替えると `beatReady` の準備姿勢を適用し、保持呼気を解除する。最初のキーで口唇開度の目標を −0.25 cm、軟口蓋の目標を0.9 cm²にする。キーの速度は低音の分岐では使われず、保持中の呼気目標は1になる。F0は `440 × 2^((MIDI−69)/12)` Hz。保持順の末尾が現在の基準F0を決め、最後の解放では準備姿勢の口唇開度0.25 cm、中立の軟口蓋 −0.15 cm²、呼気目標0へ戻す。発声中の基準F0の平滑化時定数は60 ms、低音の押下・最終解放で呼気ゲートが追従する時定数はそれぞれ25 msと70 ms。声道形状、呼気、声門の更新を経て、次の内部サンプルが声門流と口・鼻の放射流を進める。[MIDI入力と所有](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[ストアの処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[準備姿勢](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L31)・[上流の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)

`bassNote` の初期値は40で、押下だけがこの値を更新する。`toggleBeatStep` はハムを追加するとき、その時点の値をセルに書き込む。`Engine::set_beat_steps` が新しいセルを `BeatPlayer::set_steps` に渡し、`tick` は音源時計の200 ms先までを予約する。編集前に予約したジェスチャーは予約時の内容で鳴る。ハムでは打点の前から唇を閉じ、軟口蓋と呼気のジェスチャーを重ねる。譜面のF0の時定数は30 ms。上流の既存試験からはビートボックスを離れたときの姿勢の復帰を確認した。MIDIによる低音とグリッドの編集は今回のブラウザ比較で通した。[セル更新](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L216)・[予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)・[ハムのジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L259)・[姿勢の復帰試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts)

成人男性・48 kHz、8休符、120 BPM、スウィング0で、40を押し、47を重ね、47を離してからハムを追加し、40を離す。押下直後のグライドを除いた測定窓で、声門F0の中央値とPCMのYIN推定を照合する。ハムを置く時点で音高は40へ戻り、後続ループの2.2秒で47のハムが始まると予測した。低音3区間では唇端の最小断面積が0.05 cm²以下、軟口蓋ポートが0.10 cm²以上、鼻端流量が口端より大きくなると予測した。解放後はゲート0.03以下、同じフレームの候補・上流で鼻端流量RMSの相対差は10⁻⁶以下とした。[入力時刻・測定窓・判定基準](../cases/worklet-midi-beatbox.json)

## 実装と再実行

「ビートボックス」でMIDI入力を接続し、実時間再生中にキーを押すと低音を出せる。「ハムを切り替えるステップ」の番号を指定すると、同じハムを取り除くか、最後に押した音番号でセルへ追加する。MIDI入力はポートのイベントを購読して使うため、別パネルの購読を上書きせず、切断時はその購読で保持していたキーを解放する。Workletは低音とセルの操作を受信順に描画量子の先頭で適用し、合成開始からのフレームとAudioContextのフレームを記録する。Rustの `BeatPlayer` が保持音、最後に押した音番号、今後の予約に使うセルを管理する。CLIは書き出した `bass_key`・`toggle_hum` を同じRustの経路に渡す。[画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[MIDI入力の購読](../../../../web/prototypes/chimera-research/src/midi-input.ts)・[Rustの時間管理](../crates/vocal-core/src/phonetics/beatbox/player.rs)・[CLIの操作入力](../crates/vocal-cli/src/timing_case/speech_voice/beat_pattern.rs)

通常の固定上流の画面でも、同じ仮想MIDIとハムのグリッドを操作した。固定上流のブラウザは公開テレメトリでF0と軟口蓋を観測した。鼻端流量と唇端の最小断面は、固定上流のRust `Engine` に候補の採用フレームと同じ調音・呼気・セル操作を渡して採取した。ブラウザ比較では上流のMic FXをオフにし、同時刻のネイティブ比較では研究版の既存ビート条件の肺圧と出力利得を両方に指定した。[ブラウザ実行](../../../../web/prototypes/chimera-research/tools/capture-midi-beatbox.mjs)・[固定版のネイティブ実行](../tools/upstream_beatbox_pattern_probe.rs)

## 検証結果

正式試行は17項目に合格した。40 → 47 → 40と戻るとき、PCMのYIN推定は82.33 → 123.16 → 82.69 Hz。追加したハムの音番号は47で、2.2秒に打点を迎え、同じ手法で123.31 Hzを得た。保持中の唇端最小断面は0 cm²、軟口蓋ポートは約0.90 cm²、鼻端流量RMSは170〜190 cm³/sだった。最後の解放後の窓では軟口蓋ポートが0 cm²、ゲートの最大値は0.02093だった。[実測値・判定・採用フレーム](../runs/worklet-midi-beatbox-20261121-b/summary.json)

研究版のWAVは48 kHzの139,200フレームで、113フレーム単位で描画したCLIとビット一致した。2,175時点で比較した9系列はすべて差0。固定上流のネイティブ実行と照合すると、呼気、口唇開度、口唇最小断面積、軟口蓋ポート、瞬時F0は差0で、鼻端流量の最大差は3.04×10⁻¹¹ cm³/s、PCMの最大差は7.28×10⁻¹²だった。鼻端の差が最初に生じる演算は未特定。固定Engine自身の1・113・128フレーム分割はビット一致した。キーの相対採用時刻と登録した間隔との差は最大4.67 msだった。この値にはブラウザの準備完了から最初の押下までの待ち時間を含めていない。[比較の集計](../runs/worklet-midi-beatbox-20261121-b/summary.json)

初回はブラウザ録音とCLIの照合後に、固定版の入力JSONを作る処理が存在しない関数を呼んで停止した。標準ライブラリのJSON出力へ変更して再計測し、初回の出力とソースの控えも保存した。正式試行の計測CSV2本は、全フレームの判定後に列と区間を抜粋したため、合計214.3 MBから25.6 MBになった。元CSVのSHA-256、抜粋の区間、環境、全コマンドはマニフェストにある。加工前WAV、観測JSON、再実行ケースはRTL9210B-CGに置いた。[初回の障害と再現条件](../runs/worklet-midi-beatbox-20261121-a/failure.json)・[正式試行のマニフェスト](../runs/worklet-midi-beatbox-20261121-b/manifest.json)

手動発声と鍵盤歌唱のMIDI回帰は各16項目、ビートのテンポ・停止・再開の回帰は13項目、RustのコアとWASMは計40件が通過した。[手動発声](../runs/worklet-midi-beatbox-20261121-manual-regression/summary.json)・[鍵盤歌唱](../runs/worklet-midi-beatbox-20261121-singing-regression/summary.json)・[ビートの回帰](../runs/worklet-midi-beatbox-20261121-transport-regression/summary.json)

研究ディレクトリで仮想環境を有効にして再実行する。Web MIDIの実機、許可画面、低音と有声打音が同時に鳴る条件は残る。次は鳴禽の持続音で、音域への折り返しとキー解放時の呼気を照合する。[次の登録ケース](../cases/worklet-midi-songbird.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=402653184 \
  python3 tools/measure_worklet_midi_beatbox.py worklet-midi-beatbox-local-1
```
