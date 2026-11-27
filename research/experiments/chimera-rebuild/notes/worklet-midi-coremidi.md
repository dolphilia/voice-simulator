# CoreMIDIの仮想送信元からの手動発声

Chromeの許可画面は先行実行で操作した。今回の比較では試験コンテキストに許可を設定してから、研究版の「MIDI鍵盤の発声」と固定上流のPlayで接続する。macOSのCoreMIDIに試験用の送信元を一時的に作り、通常のWeb MIDI接続が開いた入力へ音57の押鍵と離鍵を送る。[許可画面の先行実行](worklet-midi-browser-prompt.md)・[事前登録](../cases/worklet-midi-coremidi.json)

## 読解

- 固定上流の `MidiButton` から `setMidi`、`connectMidi`、`attach` へ進む。`MIDIAccess.inputs` のポートを列挙して `onmidimessage` を設定する。ポートIDと下位4ビットのチャンネルを所有者として、上位4ビットが `0x90` でベロシティが正なら押鍵、`0x80` またはベロシティ0の `0x90` なら離鍵とする。同じ音を複数の所有者が押さえているときは最初の押鍵と最後の離鍵を伝える。テストは仮想ポートで重複所有、抜線、待機中の切断を実行している。[接続ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Keys.tsx#L113)・[上流のMIDI処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L65)
- 上流Playの `noteOn` は保持音に番号を加え、`440×2^((n−69)/12)` HzでソースF0を更新する。呼気目標は保持中なら1で、保持音が空かつ呼気ボタンがオフなら0。`AudioEngine.gate` はすぐ送信し、`setSource` は同じ描画フレーム内の変更をまとめる。WorkletがRustの `engine_set_gate` と `engine_set_source` へ渡す。ゲートは無次元の平滑状態で、ピッチはHz、テレメトリの時計は秒、放射後の出力レベルはRMS。研究版は `listenMidi` の保持音を `LiveProcessor` へ送り、128フレーム境界で呼気目標とF0を同時に適用する。[上流の保持状態](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[送信の順序](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L378)・[Workletの適用](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L121)・[研究版の適用](../../../../web/prototypes/chimera-research/src/live-processor.ts#L168)
- CoreMIDIのMIDI 1.0用UMPでは1語にメッセージ種別2、グループ0、ステータス、2つのデータバイトを詰める。押鍵の `90 39 5d` と離鍵の `80 39 00` は `0x2090395d` と `0x20803900` になる。`MIDISourceCreateWithProtocol` で登録し、`MIDIReceivedEventList` で接続中のクライアントへ配信する。ブラウザ側は実際の入力の購読で `MIDIMessageEvent` を受け、バイト・信頼済みフラグ・時刻を観測する。[CoreMIDIの送信元](https://developer.apple.com/documentation/coremidi/midisourcecreatewithprotocol%28_%3A_%3A_%3A_%3A%29)・[イベントの配信](https://developer.apple.com/documentation/coremidi/midireceivedeventlist%28_%3A_%3A%29)・[Web MIDIの入力と購読](https://www.w3.org/TR/2026/WD-webmidi-20261020/#midiinput-interface)

## 比較方法と初回の結果

研究版の通常ビルドと固定上流のPlayを別々のローカルサイトで開き、それぞれの接続後に一時送信元を登録した。観測器は両アプリが登録した受信関数を包み、ブラウザが生成したイベントを渡しながら内容を記録する。アプリの購読で既に開いたポートを確認してから、無音の準備、押鍵、約650 msの保持、離鍵、約850 msの減衰を観測した。試験用の送信プロセスは各画面の計測後に終了する。[送信元](../tools/capture_coremidi_source.swift)・[ブラウザの観測](../../../../web/prototypes/chimera-research/tools/capture-midi-coremidi.mjs)

- **第1版。** CDPで通常MIDI側だけを許可したところ、Chrome 157の両画面で `NotAllowedError` が返った。送信元を登録する前に停止した。第2版で、先行のヘッドレス計測と同様に試験コンテキストの当該オリジンで2種類の権限設定を揃え、アプリの要求と取得したアクセスは `sysex: false` を照合した。[第1版の記録](../runs/worklet-midi-coremidi-20261122-a/summary.json)・[先行計測](worklet-midi-permission.md)
- **第2版。** 両アプリで信頼済みイベント2件のバイト列は一致した。CoreMIDIのタイムスタンプに0を渡すと、Chromeの `MIDIMessageEvent.timeStamp` は4件とも0だった。このため、バイト列との複合判定に含めた時刻の増加条件を満たさなかった。研究版のPCMはCLIと一致した。固定上流では、声門F0を220 Hz±0.25 Hzに直接照合すると不合格で、定常窓は219.34–220.27 Hzだった。[第2版の生データ](../runs/worklet-midi-coremidi-20261122-b/artifacts/coremidi-browser.json)・[旧判定とPCMの結果](../runs/worklet-midi-coremidi-20261122-b/summary.json)
- **第3版。** パケットに `mach_absolute_time()` のホスト時刻を入れた。上流は `HumanVoice::control` でピッチを平滑化した後、`ParametricGlottis::next` で既定のドリフト5セントに応じた係数 `2^(c/1200)` を掛けて、その値をテレメトリへ渡す。保存した音声時計から最後の内部サンプル番号を求め、既存の独立計測器でシード付きの三つの低域フィルタを再計算してこの係数を得た。観測値を係数で割り、押鍵前に110 Hzへ戻るかを先に検査した。押鍵中は補正後の値を220 Hz±0.25 Hzに照合し、生の値による旧判定も保存した。[平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L541)・[声門での変調](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[独立計算](../tools/measure_glottal_pitch.py#L26)

## 実測

新しい入力が閉じた状態で列挙され、アプリが購読すると同じポートIDが開いた。研究版と固定上流が受け取ったバイトと保持音は一致した。明示時刻を持つ第3版では、ブラウザ時刻で押鍵から離鍵まで659.7–660.5 msだった。CoreMIDIとブラウザの時計は別々に保存した。Chromeの画面で接続を切ると、計測対象の購読は1件から0件になった。送信元は終了時に `MIDIEndpointDispose` で除去し、両実行後のシステム列挙も入力・出力0件だった。

| 観測点 | 2実行の結果 |
| --- | --- |
| 研究版のWorklet | 押鍵を15,616または15,872フレーム、離鍵を47,360または47,616フレームで適用した。どちらも保持区間は31,744フレーム。平滑F0と呼気ゲートは独立計算との差が最大 `3.13×10⁻¹² Hz` と `2.22×10⁻¹⁶`。 |
| 研究版の加工前PCM | 128,000と128,256フレームをそれぞれの制御時刻でCLIに再入力し、各実行で全フレームがビット一致した。押鍵中の絶対ピークは0.2788–0.2790、減衰末尾は最大 `1.25×10⁻¹⁵`。 |
| 固定上流Play | 呼気目標は0→1→0で、離鍵後の評価窓に残る平滑ゲートは最大 `8.52×10⁻⁵`。保持中の声門F0は219.34–220.29 Hz。ドリフトを除くと219.82–219.99 Hzで、押鍵前の110 Hzとの誤差は最大 `2.85×10⁻¹⁴ Hz`。 |

両方の画面でA3の目標は220 Hzだった。音高の最初の比較差は、研究版の平滑F0に対して上流のテレメトリが声門で変調したF0を返すところにあった。固定上流Playでは初期姿勢と音声の既定値を保持した。両者の波形を直接照合するには、同じ姿勢と適用フレームを登録した別ケースが必要になる。物理鍵盤、機器出力、押鍵中のポート消失は未計測。[第3版の結果](../runs/worklet-midi-coremidi-20261122-c/summary.json)・[再実行](../runs/worklet-midi-coremidi-20261122-repeat/summary.json)

## 再現

macOSの研究ワークスペースから実行する。通常ビルドの一時生成物と計測データにRTL9210B-CGを使う。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py worklet-midi-coremidi-new
```

macOS 15.6.1 arm64、Chrome 157.0.8103.79、Node.js 24.19.0、Rust 1.94.1、Python 3.14.4で実行した。研究ディレクトリと `/private/tmp` から第3版の各26判定、固定上流の2試験を通過した。4実行の1,100入力と35出力をハッシュで照合し、作業用ディスクに44,118,094バイトの採取物を保存した。[第3版のマニフェスト](../runs/worklet-midi-coremidi-20261122-c/manifest.json)・[再実行のマニフェスト](../runs/worklet-midi-coremidi-20261122-repeat/manifest.json)
