# 押鍵中にCoreMIDI送信元を外す

先行ケースのA3の離鍵操作だけをCoreMIDI送信元の削除に置き換える。押鍵のバイト列、通常のブラウザ画面、観測窓は先行ケースから引き継ぐ。試験中はChromeのMIDI接続を維持する。[事前登録](../cases/worklet-midi-coremidi-unplug.json)・[Note Offの対照](worklet-midi-coremidi.md)

## 読解と予測

- 固定上流Playでは、`connectMidi` が `MIDIAccess.onstatechange` に `attach` を登録する。`attach` は現在接続中の入力IDの集合を作り、`liftWhere` が消えた入力IDを含む所有者をすべて解放する。単一入力で一つの音を保持している場合、最後の所有者を失った `lift` が `noteOff(note)` を呼ぶ。`noteOff` を受けたストアは保持音からその番号を消し、`hold` がオフなら呼気目標を0にする。入力一覧を通知する前にこの解放が走る。既存試験は仮想ポートBを入力マップから外し、所有が残るC4と同時にBから追加したE4が解放されることを確認する。[上流MIDI](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L33)・[ストアの解放](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L365)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L84)
- 研究版の `listenMidi.refresh` は同じ状態変化を受け、現在の入力一覧にない `MIDIInput` からイベントリスナーを外す。音ごとの所有数を減らして最後の保持が消えたとき、残った最新の音または `null` を公開する。手動発声では `null` が届いた後の128出力フレーム境界で呼気目標が0になる。平滑ゲートは無次元で、音声時計の秒を `t` とすると、減衰は `G(t+Δt)=G(t) exp(−Δt/0.07)` に従う。選択音の変化から同じ音源処理に入るため、離鍵との違いは入力側で判別でき、ゲート曲線は解放時刻を揃えると一致するはずである。[入力の購読解除](../../../../web/prototypes/chimera-research/src/midi-input.ts#L56)・[Workletの適用](../../../../web/prototypes/chimera-research/src/live-processor.ts#L168)・[上流の呼気更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L516)
- CoreMIDIでは `MIDIEndpointDispose` で今回の仮想送信元を除去する。Web MIDIの仕様では物理状態 `disconnected` とポートの接続状態を別に扱う。ブラウザの入力一覧から消えた後も、計測器は切断通知の `MIDIInput` を参照して状態とハンドラーの設定を採る。[CoreMIDIの削除](https://developer.apple.com/documentation/coremidi/midiendpointdispose%28_%3A%29)・[Web MIDIのポート状態](https://www.w3.org/TR/2026/WD-webmidi-20261020/#midiport-interface)

## 実測

各画面へ届いたメッセージは信頼済みのNote On `[144, 57, 93]` 1件だった。送信元の除去後、同じIDの `statechange` が `disconnected`・`pending` を報告し、入力一覧からそのIDが消えた。両画面は接続したまま入力待ちに戻り、保持音は57から空になった。固定上流で外れたポートの `onmidimessage` は値を保ち、研究版は旧入力のリスナーを明示的に解除した。ポートのコールバック設定は観測器が旧オブジェクトを参照して読んだ値である。両アプリとも音の所有は解放された。Chromeの `MIDIPort::SetState` は開いていた切断ポートに `pending` を設定し、ポートとアクセスの両方へ通知する。[第1版の実行](../runs/worklet-midi-coremidi-unplug-20261122-a/summary.json)・[Chrome 157の状態更新](https://github.com/chromium/chromium/blob/157.0.8103.79/third_party/blink/renderer/modules/webmidi/midi_port.cc#L121)

| 観測 | Note Offとの比較 |
| --- | --- |
| 研究版の呼気 | 解除から128、768、3,456、9,600出力フレームで、解除直前のゲートで割った値は0.962621、0.795669、0.357517、0.057433。対応するNote Offの値と最大 `1.67×10⁻¹⁶` の差だった。 |
| 固定上流Playの呼気 | 目標は通知後に1から0に移った。音声時計の80–300 msのゲートの対数から、削除とNote Offの両方の時定数が70.0 msになった。 |
| 研究版の加工前PCM | 削除＋通知の第2版は2実行とも140,800フレームで、各回のWorkletが採用した時刻を戻したCLI波形とビット一致した。 |

## 通知までの時間

第1版で、CoreMIDIの削除操作の開始からChromeに切断イベントが現れるまでの推定が250.7–253.3 msだった。実行中のChrome 157の `MidiManagerMac::ReceiveMidiNotify` は、CoreMIDIの `kMIDIMsgObjectRemoved` を受けると入力状態を変更する。Blinkの `MIDIAccess` が受けた状態をポートへ渡す。この経路の読解を踏まえ、第2版では送信元とは別プロセスのCoreMIDIクライアントを作り、Chromeと同じ `MIDIClientCreate` のランループで削除通知を観測した。[第1版の再実行](../runs/worklet-midi-coremidi-unplug-20261122-repeat/artifacts/coremidi-browser.json)・[Chrome 157のCoreMIDI受信](https://github.com/chromium/chromium/blob/157.0.8103.79/media/midi/midi_manager_mac.cc#L272)・[Blinkの状態受信](https://github.com/chromium/chromium/blob/157.0.8103.79/third_party/blink/renderer/modules/webmidi/midi_access.cc#L139)

第2版の4観測では `MIDIEndpointDispose` が0.10–0.14 msで戻り、別クライアントのCoreMIDI通知は削除開始の251.62–252.38 ms後に届いた。Chromeのイベントまでの時間は、共通のNote Onを起点にしたホスト時計とブラウザ時計の差分から推定し、ネイティブ側との差は1 ms未満だった。この条件では、観測された約250 msの待ちが、ブラウザ内の音源処理より前のCoreMIDI通知でも生じた。通知が遅れるCoreMIDI内部の処理と、物理鍵盤の抜き差しでの時間は未観測。[別クライアントを使った結果](../runs/worklet-midi-coremidi-unplug-20261122-notification/summary.json)・[別ディレクトリからの再実行](../runs/worklet-midi-coremidi-unplug-20261122-notification-repeat/summary.json)

## 再現

macOSの研究ワークスペースから実行する。固定したNote Off対照のケース定義と採取物を検証してから、作業用ディスクに実時間計測を保存する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py --unplug worklet-midi-coremidi-unplug-new
```

macOS 15.6.1 arm64、Chrome 157.0.8103.79、Node.js 24.19.0、Rust 1.94.1、Python 3.14.4で実行した。研究ワークスペースと `/private/tmp` から第1版は各33判定、第2版は各35判定を通過した。通常のNote Offの回帰は26判定に合格し、全5回で固定上流の2試験が通過した。1,401入力・50出力のサイズとSHA-256を照合し、採取物78,763,126バイトをRTL9210B-CGに保存した。送信元と観測クライアントを終了した後、CoreMIDIの入力と出力は0件だった。[第2版のマニフェスト](../runs/worklet-midi-coremidi-unplug-20261122-notification-repeat/manifest.json)・[Note Offの回帰](../runs/worklet-midi-coremidi-20261122-unplug-regression/manifest.json)
