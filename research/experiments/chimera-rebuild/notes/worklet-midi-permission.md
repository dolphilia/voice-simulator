# Web MIDIの権限と接続の取り消し

## 上流の経路と観測

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `Keys.MidiButton()` は、現在の `midi.status` を表示して `setMidi()` を呼ぶ。`setMidi(true)` は状態を `connecting` にして `connectMidi()` を呼ぶ。モジュールは処理中のPromiseを再利用し、`requestMIDIAccess({ sysex: false })` が返した `MIDIAccess` に、ポートが入れ替わったときの購読とMIDIイベントの処理を設定する。内部の `disconnectMidi()` は世代番号を進め、購読と保持音を解放する。解決時に世代番号が違えば、その接続結果を捨てる。所有者の単位はポートとチャンネルで、同じ音は最後の所有者が離れたときだけ離鍵する。既存テストはポートの抜き差し、複数所有、待機中の切断後に遅れて届く許可を照合する。[ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Keys.tsx#L113)・[画面の状態](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L387)・[接続と切断](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L71)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L65)

比較対象はブラウザの権限状態、要求の引数と結果、接続ボタン、エラー、`statechange` 購読の個数。研究版は手動発声・鍵盤歌唱の共通画面、ビートボックス、鳴禽、ウェッデルアザラシ、アメリカアリゲーター、アフリカゾウの6パネルを使う。ループバックで配信した各画面をChromiumの新しい試験コンテキストで開き、DevTools Protocolの `Browser.setPermission` で許可と拒否を与えた。待機中の切断では、クリック時に標準APIを呼んだ後、Chromium自身の結果をアプリへ渡す時点だけを制御した。今回のブラウザはヘッドレスで、物理ポートは0件だった。[事前登録](../cases/worklet-midi-permission.json)・[ブラウザの観測器](../../../../web/prototypes/chimera-research/tools/capture-midi-permission.mjs)・[Chromeの権限説明](https://developer.chrome.com/blog/web-midi-permission-prompt)・[DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/tot/Browser/#method-setPermission)

## 実装前に確かめた差

最初の試行は通常MIDIだけをDevToolsから許可し、`MIDI入力なし` が出るのを待ったところでタイムアウトした。別の最小ページでは、通常MIDIの権限照会が `granted` でも `requestMIDIAccess({ sysex: false })` は `NotAllowedError` を返した。このChromeの試験コンテキストでは通常MIDIとSysExの設定を同じ方向にそろえると、許可と拒否を再現できた。第2版のケースに設定の差を記録し、各アプリの要求が `sysex: false`、許可された実接続の `sysexEnabled` が `false` であることを確認した。権限の設定は各試験コンテキストに限定した。[初回の停止](../runs/worklet-midi-permission-20261122-before/manifest.json)・[改訂したケース](../cases/worklet-midi-permission.json)

変更前の研究版は6パネルともブラウザの拒否と許可後の再試行を処理できた。手動発声の画面は接続を待つ間も切断でき、遅れて届いた結果を無視した。ビートボックスと動物の5パネルでは待機中のボタンが無効なため、切断と遅延結果に関する2項目ずつが未達だった。[変更前の判定](../runs/worklet-midi-permission-20261122-before-v2/summary.json)

固定上流の画面では待機中の二度押しで要求は増えず、表示も接続待ちだった。ストアの `setMidi(false)` を直接呼んでから許可結果を返すと、購読は0のままになった。古い拒否を保持したまま切断して再試行し、その拒否を先に返すと、新しい要求が待機中でも画面が一度拒否を表示した。古い拒否を処理するストアが現在の表示状態 `connecting` を見ており、モジュールの世代番号を参照しないことと対応する。新しい許可の到着後は機器待ちに戻った。[固定上流の状態遷移](../runs/worklet-midi-permission-20261122-before-v2/artifacts/midi-permission.json)

## 研究版の変更と実測

3系統で管理していた接続を `useMidiConnection()` にまとめた。接続操作ごとのオブジェクトが現在の要求かを比較し、許可・拒否を受け取った時点で現在の要求にだけ表示と購読を適用する。切断では、以前の要求を無効にして購読を解除し、接続先と保持音を初期化する。待機中も切断ボタンを使えるようにした。押鍵所有者の処理は既存の `listenMidi()` を使い、ビートの `bass_key` や各動物の音高・打鍵先を選ぶ処理は元の呼び出しから渡す。[接続の共通処理](../../../../web/prototypes/chimera-research/src/midi-connection.ts)・[パネルとの接続](../../../../web/prototypes/chimera-research/src/main.tsx)

変更後は6パネルとも遅い許可の後で接続が復活せず、購読は0だった。取り消した要求の拒否を、新しい要求の許可より先に渡したときも、全パネルが新しい接続待ちを表示し、エラー欄は空だった。次の許可が届くとポート0件の機器待ちになり、購読は1個、切断すると0個になった。許可・切断だけの比較では手動発声の保持音は空だった。[変更後の21判定](../runs/worklet-midi-permission-20261122-after/summary.json)

## 再現

macOS 15.6.1 arm64、Chrome 157.0.8103.79、Node.js 24.19.0、Bun 1.4.4、Python 3.14.4で実行した。研究ディレクトリと `/private/tmp` で各21判定が通過し、ブラウザの観測JSONと要約はバイト一致した。固定上流の既存試験2件も通過した。音響経路の回帰では、2台の仮想ポートによる手動発声16項目、ビートボックス17項目、鳴禽のコール14項目に通過し、ブラウザの出力がCLIの再演とビット一致した。失敗と回帰を含めた7実行の1,395入力・64出力をサイズとSHA-256で確認し、採取物222,388,352バイトをRTL9210B-CGに保存した。[別ディレクトリからの再実行](../runs/worklet-midi-permission-20261122-repeat/manifest.json)・[手動発声の回帰](../runs/worklet-midi-permission-20261122-voice-regression/manifest.json)・[ビートボックスの回帰](../runs/worklet-midi-permission-20261122-beat-regression/manifest.json)・[鳴禽の回帰](../runs/worklet-midi-permission-20261122-songbird-regression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=67108864 ../../.venv/bin/python \
  tools/measure_worklet_midi_permission.py worklet-midi-permission-local
```

この対照は許可画面のボタンを人が押す実験と、物理ポートの接続を含まない。Chromeの試験用コンテキストで許可結果を再現し、実際に届いた権限応答に対するアプリの挙動を比較した。
