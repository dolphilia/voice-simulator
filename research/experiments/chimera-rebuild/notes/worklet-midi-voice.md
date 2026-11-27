# Web MIDI の所有と実時間発声

固定上流の `Keys.MidiButton` は `setMidi` を呼び、`connectMidi` はWeb MIDI入力を購読する。ステータスの上位4ビットで Note On、Note Off、Control Change を区別し、下位4ビットをチャンネル番号として使う。Note Onのベロシティ0は解放、CC 120と123はその入力・チャンネルの全音解放として扱う。同一音の最初の押下と最後の解放だけが演奏側の押下・解放になる。入力が外れた場合はその入力の所有を解放する。接続許可を待つ間に切断した要求は無効にする。上流の `tests/live-control.test.ts` はこれらのうち重複所有、抜線、遅れた許可を仮想入力で試験する。[入力の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Keys.tsx#L114)・[接続と所有](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L65)

手動発声では最新の保持音 `n` から `f=440×2^((n−69)/12)` Hzを求める。最新音を離すと前の保持音に移り、保持音が空になると呼気目標は0になる。ベロシティは上流の手動呼気の倍率にならない。上流では状態を `AudioEngine` がフレームごとにまとめ、Workletで音源に適用する。研究用では既存の128出力フレームの量子境界で最新のメッセージを取り、基準F0（Hz）と呼気目標（無次元）を適用する。64出力フレームごとの制御でF0は時定数0.06秒の対数一次遅れ、呼気は既存の立ち上がりと減衰の時定数で更新される。基準F0を `f*` とすると、制御を1回進めたF0は `f(f*/f)^(1−exp(−Δt/0.06))` になる。気道・放射・PCMは既存の発声経路を通る。[演奏側の保持音](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[上流のWorkletの音源入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L121)・[研究用音源の平滑化](../crates/vocal-core/src/voice.rs#L177)

## 事前登録

48 kHzの出力、96 kHzの内部計算、男性の `/i/`、初期F0 110 Hzから始める。仮想の2入力を使い、A2・A3の重複所有、レガート復帰、ベロシティ0、全音消音、入力の抜き差しを既定の順で送る。上流の入力処理と研究用のブラウザで選択音の列を照合する。描画量子で適用されたイベントから制御更新ごとのF0とゲートを独立に計算し、観測値を照合する。PCMと内部状態が同じ時刻を指すこと、書き出しケースのCLIによる加工前PCMのビット一致、無音と発声の窓、観測の有限性を検査する。[登録ケース](../cases/worklet-midi-voice.json)・[既定の実時間条件](../cases/worklet-realtime-voice.json)

第1版では準備区間の加工前PCMがすべて厳密な0という判定だけが未達だった。最初の音より前のゲートは0だったが、口腔セル断面と肺境界圧が初期化後にわずかに変わり、PCMピークは `1.3842×10⁻⁷` だった。第2版は初音より前のゲート0、既存の減衰末尾と同じ実用上の静音閾値 `1×10⁻⁵`、MIDI音を一切送らないCLI対照とのビット一致を判定にした。第1版の判定、ケース、時系列を実行記録に保存した。[最初の判定](../runs/worklet-midi-voice-20261120-a/summary.json)・[初期化直後の時系列](../runs/worklet-midi-voice-20261120-a/artifacts/native-state.csv)

## 実装と測定

「MIDI鍵盤の発声」の接続操作で入力を購読し、計測開始の操作で実時間AudioContextを起動する。入力ごと・チャンネルごとの集合と、音ごとの所有数から鳴らす音を選ぶ。切断時はその入力の購読と所有を解放する。Workletは各量子に届いた最新の音を採用し、初音まで呼気目標0を保つ。MIDI番号を基準F0へ変換してRustの手動発声へ渡し、採用したフレーム・番号を保存する。書き出しケースは制御フレームに換算した `f0_hz` と `gate` を持ち、CLIはその境界で値を設定する。[ブラウザの入力](../../../../web/prototypes/chimera-research/src/midi-input.ts)・[Workletの適用](../../../../web/prototypes/chimera-research/src/live-processor.ts)・[書き出し](../../../../web/prototypes/chimera-research/src/manual-replay.ts)・[CLIの再生](../crates/vocal-cli/src/articulation_case/voiced.rs)

14操作すべてで固定上流とブラウザの選択音が一致し、実際の音源に届いた変化は MIDI 45 → 57 → 45 → 休止 → 48 → 休止の6件だった。57の最後の所有をCC 120で解放すると保持中の45へ戻り、Bを抜くと呼気が下がった。Bをつなぎ直すと48の演奏が可能になり、CC 123で停止した。手動発声のベロシティは検証時も呼気倍率に使わなかった。第2版の実行では最初の制御がフレーム7,040。50,560で音高目標が110から220 Hzに変わった量子の末尾で、平滑F0は113.365 Hz、ゲートは1を保った。呼気ゲート・平滑F0の独立計算との差は最大 `2.22×10⁻¹⁶` と `5.97×10⁻¹³ Hz` だった。[入力と選択音](../runs/worklet-midi-voice-20261120-b/artifacts/upstream-midi.json)・[適用フレームと比較結果](../runs/worklet-midi-voice-20261120-b/summary.json)

出力167,552フレームの加工前PCMと、1,309点のゲート、声門F0、声門流量、放射の時間差分はCLIと一致した。最初の7,040フレームはMIDIを省いた対照とビット一致し、準備区間の微小信号も再現した。最後の2,400フレームの最大絶対PCMは `2.31×10⁻¹¹`。この実行の `Date.now` の1 ms刻みの計時では、起動時の32量子を除いたp95・p99は2 msで、2.67 msを超えた量子は0だった。[MIDIを省いた対照](../runs/worklet-midi-voice-20261120-b/artifacts/no-notes-case.json)・[観測値と実行条件](../runs/worklet-midi-voice-20261120-b/manifest.json)

上流と比較したのはMIDI入力から選択音まで。入力は仮想ポート2台を使い、候補のUI、AudioWorklet、WASM、音声書き出しは実ブラウザで実行した。物理機器とブラウザの許可画面、上流エンジンを含む動的ピッチの波形差、歌唱・動物・ビートボックスへのMIDI入力は未測定。

## 再実行と回帰

研究ディレクトリと `/tmp` から各16項目が通過した。WASMと固定上流の選択音・コールバックのJSONは両実行でSHA-256が一致した。ブラウザへ送ったイベントの実際の適用フレームと出力長は実行ごとに変動した。各回でその時刻を書き出してCLIに渡すと、各WAVはビット一致した。既存の舌・唇の操作と書き出しの回帰20項目、固定上流の `tests/live-control.test.ts` の2件、Rustの整形・Clippy・試験39件が通過した。[初回合格](../runs/worklet-midi-voice-20261120-b/manifest.json)・[別ディレクトリの再実行](../runs/worklet-midi-voice-20261120-repeat/manifest.json)・[既存の手動操作の回帰](../runs/worklet-manual-midi-regression-20261120/manifest.json)

```bash
python3 tools/measure_worklet_midi.py worklet-midi-local-1
```
