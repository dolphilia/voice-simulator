# Web MIDIで鳴禽のコールを鳴らす

## 固定上流の読解と事前登録

Bestiary の `KeysMode` で「Flute phrase」を選ぶと、MIDIの `noteOn` は音番号を種の音域へ割り当て、ストアの `playCall` から `AudioEngine.playCall` へコールIDと周波数を渡す。WorkletはIDを固定版のコール番号に変換し、`engine_play_call` を呼ぶ。Held voiceではキーの押下と解放が呼気ゲートに届く。コールモードでは `updateGate` が鍵盤による呼気を除外し、`noteOff` は保持一覧を更新する。音源がまだ起動していないときは、押したキーが起動時点でも保持されていればコールを送る。[Bestiaryの鍵盤モード](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L79)・[入力の振り分け](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[Workletのコール入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L171)

`CreatureVoice::play_call` は前のコールが所有していた目標値を演奏者の値へ返し、新しいコールの開始時計を現在の制御時計に合わせる。音高倍率は入力周波数÷コールの基準周波数で、fluteの基準は2,600 Hz。各制御更新で `eval_call` はコール開始からの秒を使って各パラメータの前後のキーを探す。次のキーの指定に応じて線形、指数、段差のいずれかで補間し、入力周波数が変わっても補間曲線の時刻は保たれる。音高だけを倍率で伸縮して400〜9,000 Hzへ制限する。演奏者とコールの呼気目標の大きい方を使う。出力64フレームごとの平滑化と既存の気道・鳴管は再発音後も連続して進み、コールの最後の制御点から50 msを過ぎた更新で演奏者の目標に戻る。[固定版のコール処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[fluteの目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L176)・[ブラウザの既存ABI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/creature-abi.test.ts)・[固定版の割り当て試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)

48 kHzで60を押して解放し、最初の押下から0.63秒後に67で同じコールを再開して解放する。固定版の公開定義では最初の音高点が2,000 Hzなので、音番号から計算した倍率を掛けると、2回の開始時の音高目標は約1,610 Hzと2,412 Hzになると予測した。採用フレーム直前、再開始の制御境界、解放後10〜50 ms、自然終了後を比較する。独立計算は固定版のキー定義を読み、補間と平滑化を各制御境界で再計算する。[ケースと事前の判定条件](../cases/worklet-midi-songbird-call.json)・[既存の独立計算](../tools/measure_songbird_flute.py)

## 実装と比較方法

「MIDIで鳴禽を演奏」の「鍵盤で鳴らす音」で持続音または4種のコールを選ぶ。コールモードでは、所有管理から届いた押下・解放と、選んだコールIDをWorkletに渡す。採用フレームは合成を始めてからの出力とAudioContextの両方で記録する。共有Rustの `SongbirdVoice::midi_call` は持続音と同じ鍵盤の写像で周波数を計算し、押下時に通常の `play_call` へ音高を渡す。解放は入力履歴に残り、コールの包絡は進み続ける。CLIの `midi_call` とブラウザは同じ処理を使う。[研究版の画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[共有Rustの処理](../crates/vocal-core/src/songbird_voice.rs)・[CLIイベント](../crates/vocal-cli/src/songbird_voice_case.rs)

固定上流のブラウザでもMIDIとFlute phraseを通常の画面から操作し、`AudioEngine.playCall` へ送られた引数を、元の呼び出しを通したまま記録した。そのコールだけを研究版の採用フレームに置き、固定Rust版の公開PCMを採取した。固定版のブラウザテレメトリはコール名・F0・呼気を、固定版のネイティブ観測は気嚢圧と左右の鳴管の開口・実断面・流量を比較する。候補WAVは113フレーム単位で描画したCLIと照合した。[通常画面の操作](../../../../web/prototypes/chimera-research/tools/capture-midi-songbird.mjs)・[ネイティブ観測](../tools/upstream_songbird_voice_probe.rs)・[計測入口](../tools/measure_worklet_midi_songbird_call.py)

## 検証結果

初回と、別の作業ディレクトリから行った再実行で、登録12項目がすべて合格した。再実行の開始はフレーム8,448と38,656。入力の音域割り当ては2,093.00 Hzと3,135.96 Hz、コールの最初の音高目標は1,610.00 Hzと2,412.28 Hzだった。再発音の直前は前のコールの目標が2,665.27 Hz、呼気は0.962だった。再発音した制御更新で目標は最初のキーへ戻り、呼気目標は0から始まった。平滑化後の音高と呼気は直前の値から追従した。[初回の判定](../runs/worklet-midi-songbird-call-20261121-a/summary.json)・[再実行の採用フレームと目標](../runs/worklet-midi-songbird-call-20261121-final/summary.json)

解放後10〜50 msでは、2回ともコールIDが保たれ、PCMのRMSは0.158と0.124だった。最後はフレーム98,688で自動終了し、演奏者の2,600 Hzへ戻った。最後の30 msのPCMのRMSは1.47×10⁻¹⁵だった。独立計算と比較した音高目標の最大差は7.73×10⁻¹² Hz、平滑値は1.36×10⁻¹¹ Hz、包絡の目標とコールIDの差は0だった。再実行のMIDI採用間隔と登録値の差は最大4.67 msだった。[コールの呼気・自然終了・独立計算](../runs/worklet-midi-songbird-call-20261121-final/summary.json)

研究版のWAV 117,600フレームはCLIとビット一致し、WorkletとCLIの1,838時点・13系列も差0だった。解放の指示なしで固定版の通常コールを同じフレームから描画したPCMとは全サンプルで一致した。固定版との気嚢圧、F0、左右の実断面積が一致し、流量だけに左・右ともフレーム8,455から微差が出た。最大差は約1.35×10⁻¹³ cm³/sで、内部演算の差が生じた位置は未特定。[PCMと観測列の比較](../runs/worklet-midi-songbird-call-20261121-final/summary.json)

持続音のMIDI回帰17項目、既存のflute回帰18項目、Rust40件が合格した。全フレームの判定後にCSV2本を108.3 MBから33.1 MBへ抜粋し、RTL9210B-CGへ保存した。元のSHA-256と再実行の環境・コマンドはマニフェストにある。実機MIDI、flute以外のコールの個別のMIDI比較と、他の動物の鍵盤経路が後続に残る。[マニフェスト](../runs/worklet-midi-songbird-call-20261121-final/manifest.json)・[持続音回帰](../runs/worklet-midi-songbird-call-20261121-held-regression/summary.json)・[コール回帰](../runs/worklet-midi-songbird-call-20261121-flute-regression/summary.json)・[アザラシの登録条件](../cases/worklet-midi-seal.json)

研究ディレクトリで仮想環境を有効にして再計測する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=402653184 \
  python3 tools/measure_worklet_midi_songbird_call.py worklet-midi-songbird-call-local-1
```
