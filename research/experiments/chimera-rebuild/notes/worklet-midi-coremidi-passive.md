# 既存のCoreMIDI入力を受動観測する

## 上流の呼び出し順と今回の観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `src/ui/components/Keys.tsx` のMIDIボタンから `setMidi` を通り、`src/ui/midi.ts` の `connectMidi` と `attach` で `MIDIAccess.inputs` を購読する。ステータスの上位4ビットが `0x90` でベロシティが正なら押鍵、`0x80` またはベロシティ0の `0x90` なら離鍵。ポートIDとチャンネル番号で保持者を区別し、同じ音を保持する最後の入力が離れたときに解放する。`tests/live-control.test.ts` は複数入力で同じ音を保持する動作、抜線による解除、許可待ちの切断を確認する。

再実装のMIDI鍵盤パネルは同じWeb MIDI入力で保持音を更新し、実時間WorkletへF0とゲートを送る。均等律の式は `440 × 2^((note−69)/12)` Hzで、音57は220 Hz。入力の時刻はCoreMIDIのホストtick、ブラウザの単調時計のms、Workletの出力フレームで記録する。前二者はそれぞれの順序を確認し、出力は48 kHzの採用フレームを基準に比較する。ブラウザが保存する再実行ケースでネイティブCLIのPCMと照合する手順は既存の仮想送信元の比較で成立している。[上流からの呼び出しと仮想対照](worklet-midi-coremidi.md)

従来の計測スクリプトは計測自身が仮想送信元を作り、押鍵と離鍵を送る。今回は既存入力に接続して受信記録を取る経路を追加する。実機では選択した入力から操作者が音57を押して離し、CoreMIDI受信と信頼済みのWeb MIDIイベントを独立に照合する。接続機器がない環境では既知の仮想入力で受信経路を検証する。[事前登録](../cases/worklet-midi-coremidi-passive.json)

## 既存入力の選択と受信

Swiftのヘルパーに、入力の固有ID・名前・エンティティ・機器とドライバーを列挙する `--list-inputs` と、選んだエンドポイントにMIDI 1.0の入力ポートを接続する `--listen-notes` を追加した。受信したUMPを `MIDIEventListForEachEvent` で解釈し、押鍵・離鍵のバイトとホスト時刻を記録する。通常のMIDI鍵盤パネルは同じ入力から受けたイベント、Workletが採用したフレーム、録音と再実行ケースを書き出す。受動計測の結果には、仮想対照の `virtual_fixture`、接続入力の `attached_device`、入力が見つからなかった `unobserved` を記録する。接続入力を物理鍵盤の証拠として登録する際は、採取時に確認した実機との対応も参照する。[CoreMIDIの受信](../tools/capture_coremidi_source.swift)・[通常画面の計測](../../../../web/prototypes/chimera-research/tools/capture-midi-coremidi.mjs)・[判定と再実行](../tools/measure_worklet_midi_coremidi.py)

## 実行と結果

macOS 15.6.1 arm64、Swift 6.2.3、Rust 1.94.1、Node 24.19.0。ワークスペースと `/tmp` から仮想入力の対照を実行し、それぞれ12判定が通った。CoreMIDIとWeb MIDIの両方で `90 39 5D` の押鍵と `90 39 00` の離鍵を受信し、通常画面は未保持→57→未保持と移った。CoreMIDIの受信時計で保持は約685 msと663 ms。48 kHzで採用フレームは128点の量子境界にあり、220 Hzの目標とゲートを独立計算と照合した。各129,024・128,000フレームのブラウザPCMが、保存ケースのCLI再実行とビット一致した。固定上流も含む従来の仮想送信元の比較は26判定に合格した。[受動計測の再実行](../runs/worklet-midi-coremidi-passive-fixture-20261122-repeat/summary.json)・[従来経路の回帰](../runs/worklet-midi-coremidi-passive-existing-regression-20261122/summary.json)

CoreMIDIの入出力数は各0件だった。入力UID 0を指定して測ると、入力一覧が空で `selected_attached_input_present` が不合格になり、音声の採取は未観測として保存された。独立検算で、受信バイト列、保持時間、採用フレーム÷64で得る再実行ケースの制御位置、WAVの全PCM、4実行の1,146入力と32出力を照合した。成果の実体44,117,519バイトはRTL9210B-CGに保存した。[入力なしの記録](../runs/worklet-midi-coremidi-passive-no-input-20261122/summary.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-midi-coremidi-passive.py)

研究ワークスペースから仮想対照を再現するコマンド。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=90000000 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py worklet-midi-coremidi-passive-new --passive-fixture
```

実機では接続した入力の `uid` を一覧から選ぶ。計測はChromeの画面で音57の押鍵と離鍵を案内する。機種と接続方法を確認できたら、操作者が確認した情報として `--physical-device-label` に記録する。

```bash
/usr/bin/xcrun swift tools/capture_coremidi_source.swift --list-inputs
read -r -p '一覧から入力のuidを入力してください。' chimera_midi_uid
read -r -p '鍵盤の機種と接続方法を入力してください。' chimera_midi_device
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=90000000 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py worklet-midi-coremidi-attached-new \
  --physical-source "$chimera_midi_uid" --physical-device-label "$chimera_midi_device"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-midi-new \
  --physical-midi-run worklet-midi-coremidi-attached-new
```

機器名を省略した計測も照合できる。監査は `coverage.physical_midi_capture` に接続入力とPCMを記録し、操作者の機器情報が無い場合の状態を `partial` とする。音声の取得点は48 kHzのWorklet PCM。[第7段階での照合](plan-evidence-stage7.md#第9版で物理midiの収録を照合する)

## 端子名と表示名が異なる入力

固定上流では鍵盤パネルのMIDIボタンがストアの `setMidi` を呼び、`connectMidi` が `MIDIAccess.inputs` を取得する。`attach` は接続中の入力IDごとに購読し、IDと0始まりのチャンネル番号を押鍵の所有者にする。正のベロシティを持つノートオンは押鍵、ノートオフとベロシティ0のノートオンは離鍵として処理する。同じ音を保持している最後の入力が離れると音が止まる。複数入力の試験は、片方が離れても残る音と、抜線で解放される音を確認する。[上流の接続と所有者](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L48)・[複数入力の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L83)

研究版の収録はCoreMIDIのUIDで1端子を選び、Swiftが返す `name` と `displayName` をChromeで同じ端子を探す候補に使う。2つの名前が異なる場合に、Chromeの1端子を確認できても端子を2つ待って止まると予測した。仮想送信元を1つ追加し、もう一方の表示名を検索候補だけに加えて再現する。押鍵・離鍵のバイト、ブラウザのms、48 kHzのWorklet出力フレームを保存し、修正後は既存の音57・220 Hz・停止後の無音・CLI波形の合否を適用する。共有ノートを2入力で保持する試験も同じ採取器で照合する。[事前登録](../cases/worklet-midi-coremidi-input-aliases.json)・[CoreMIDIの名前取得](../tools/capture_coremidi_source.swift#L98)・[Chromeの収録](../../../../web/prototypes/chimera-research/tools/capture-midi-coremidi.mjs)

修正前はChromeに `open` の端子1件があり、ネイティブの受信ポートも接続済みだった。候補名2件を端子2件として待ち、60秒後にタイムアウトした。最初に止まった場所は押鍵前の端子数の照合だった。待つ端子数を選択した入力の数に合わせると、同じ候補名2件・端子1件で、仮想送信元の `90 39 5D` と `90 39 00` がCoreMIDIとChromeの両方に届いた。収録の別名検索は通常の受動計測でも使う。[修正前の記録](../runs/worklet-midi-coremidi-alias-before-20261123/artifacts/coremidi-browser.json)・[修正後の記録](../runs/worklet-midi-coremidi-alias-20261123-repeat/artifacts/coremidi-browser.json)

研究ワークスペースと `/tmp` から各12判定に通過した。CoreMIDI時計の保持は約662.41 msと664.04 ms。各127,744・128,256フレームのデジタルPCMが、同じ実行の保存ケースを描画したCLIとビット一致した。WAVのデータチャンク、保持時間、128フレーム量子の採用点は既存の独立検算でも一致した。2入力で同じ音を保持する試験は31判定、固定上流の `live-control.test.ts` は2試験を通過した。CoreMIDI入出力は各0件で、今回の候補名2件は仮想入力で模擬した。[別ディレクトリの再実行](../runs/worklet-midi-coremidi-alias-20261123-repeat/summary.json)・[2入力の回帰](../runs/worklet-midi-coremidi-alias-shared-regression-20261123/summary.json)・[名前と端子数の独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-midi-coremidi-input-aliases-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=90000000 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py worklet-midi-aliases-new --passive-fixture
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py worklet-midi-aliases-shared-new --shared-note
```

## 選択外の入力が接続された状態での購読解除

固定上流では `Keys.tsx` のMIDIボタン、ストアの `setMidi`、`connectMidi` の順に接続する。`attach` は `MIDIAccess.inputs` を列挙し、端子IDと0始まりのチャンネルを押鍵の所有者にする。押鍵には音番号とベロシティを受け取り、同じ音の最後の所有者が解放されたときに離鍵する。`disconnectMidi` は各端子の `onmidimessage` をクリアして状態変更の購読を外し、保持を解除する。固定上流の試験は、複数端子とチャンネル、抜線、許可待ちの切断を扱う。[上流の画面入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Keys.tsx#L116)・[ストア](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L388)・[購読と解除](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L48)・[複数入力の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L83)

研究版の `listenMidi` は端子ごとに `addEventListener` で購読登録し、返した解除関数が同じ端子・コールバックで `removeEventListener` を呼ぶ。収録の `observeMidi` は受動計測時に全端子のコールバックをラップするが、解除時は選択端子名だけに同じラッパーを渡していた。選択外に無操作の端子を1つ追加した場合、計測を止めてMIDIを切断しても、選択外端子の購読が1件残ると予測した。音57の押鍵・離鍵はチャンネル1、時刻は受信のns、ブラウザのms、Workletの出力フレームで照合する。音高目標は `440 × 2^((57−69)/12) = 220 Hz`。PCMは切断前に書き出し、解除の差を発声の差と区別する。[事前登録](../cases/worklet-midi-coremidi-idle-input.json)・[研究版の登録と解除](../../../../web/prototypes/chimera-research/src/midi-input.ts#L57)・[収録の観測器](../../../../web/prototypes/chimera-research/tools/capture-midi-coremidi.mjs#L23)

修正前は2端子の購読から選択対象の1件だけが解除された。新しい失敗は `page_and_subscriptions_are_clean` の1判定で、選択した音57の受信、無音復帰、全128,000フレームのCLIとのPCM一致は成立した。修正後は実際に登録した端子とラッパーを参照して解除し、接続で2件、切断後で0件になった。別の `EventTarget` 上に保存済みの修正前後の観測器を読み込み、切断後に同じ入力へイベントを直接送った。修正前は選択外のコールバックが実際に1回呼ばれ、修正後はどちらも呼ばれなかった。[修正前の結果](../runs/worklet-midi-coremidi-idle-before-20261123/summary.json)・[修正後のChrome記録](../runs/worklet-midi-coremidi-idle-20261123-repeat/artifacts/coremidi-browser.json)・[コールバックの独立対照](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-midi-idle-listeners-20261123.json)

研究ワークスペースと `/tmp` から各13判定に通過した。CoreMIDIとChromeの押鍵・離鍵は `90 39 5D` と `90 39 00` で一致し、無操作端子の送信は0件。ネイティブ時計の保持は約663.72 msと662.61 ms。各128,256・129,024フレームでCLIとのPCM一致を独立に確認した。既存の1端子条件は12判定、2端子で共有ノートを保持する条件は31判定、固定上流の `live-control.test.ts` は2試験に通過した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Node 24.19.0で、出力をRTL9210B-CGに保存した。[再実行の要約](../runs/worklet-midi-coremidi-idle-20261123-repeat/summary.json)・[1端子の回帰](../runs/worklet-midi-coremidi-idle-single-regression-20261123/summary.json)・[共有ノートの回帰](../runs/worklet-midi-coremidi-idle-shared-regression-20261123/summary.json)・[PCMと元記録の照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-midi-idle-pcm-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=90000000 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py worklet-midi-idle-new \
  --passive-fixture-with-idle-input
```

## 同名の入力を受信イベントで照合する

固定上流では `Keys.tsx` のMIDIボタンからストアの `setMidi`、`connectMidi`、`attach` へ進む。入力の名前は画面に表示し、保持者は `input.id` とステータスバイト下位4ビットのチャンネルで区別する。上流の複数端子試験は、音番号とベロシティを含む3バイトの入力を使い、片方が離れても最後の保持者まで音が続くことを確かめる。研究版も購読と保持状態を入力オブジェクトごとに記録する。[上流のボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Keys.tsx#L116)・[ストアの接続](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L388)・[IDと保持の処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L48)・[複数入力の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L83)

収録ではCoreMIDIの選択UIDから受信する端子を決め、Chrome側では端子名または表示名で候補を探す。同じ名前の2端子がChromeに出ると、候補を1件待つ旧条件は押鍵前に停止すると予測した。同名の仮想入力を2件作り、選んだ端子のチャンネル1、音57だけを操作する。収録中のノートイベント全体を確認し、選択端子の押鍵と離鍵がChromeの同じ候補IDの2受信に対応する条件を測る。受信時刻はCoreMIDIとブラウザの各時計で順序を確認し、音高とゲートを48 kHzの出力フレームで照合する。受信元が分かれたり余分なノートが届いたりする対照も使う。[事前登録](../cases/worklet-midi-coremidi-same-name.json)・[CoreMIDIの端子情報](../tools/capture_coremidi_source.swift#L98)・[受動収録の判定](../tools/measure_worklet_midi_coremidi.py#L320)

修正前は同名の2端子が `open` で、選択UIDと同じ文字列のChrome IDが候補にあった。CoreMIDIが聴取を開始した後、ブラウザは端子数の照合で12秒後にタイムアウトした。今回の環境で観測したUIDの一致を追加条件にし、ネイティブの押鍵・離鍵のバイト列と時刻を保ってChrome側の送信元だけを同名の別IDへ付け替えた対照を事前登録に加えた。[修正前の記録](../runs/worklet-midi-coremidi-same-name-before-20261123/artifacts/coremidi-browser.json)

修正後は同名候補を開いたまま、CoreMIDIで受信した押鍵と離鍵をChromeの同じIDに照合した。今回のChromeは両端子ともCoreMIDI UIDの文字表現をIDに使っており、選択UIDと受信IDは両実行で一致した。UIDと一致する候補がある場合はそのIDを要求し、IDの表現が異なる場合は選択したCoreMIDI端子の押鍵・離鍵と、同じ候補IDの信頼済み2イベントを照合する。離鍵だけ別端子、両イベントを別端子へ付け替え、別端子から追加の押鍵・離鍵が混ざるという3対照を再照合し、いずれも送信元の判定が不合格になることを確認した。[Chromeの候補と受信記録](../runs/worklet-midi-coremidi-same-name-20261123-repeat/artifacts/coremidi-browser.json)・[独立照合と対照](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-worklet-midi-same-name-20261123.json)

研究ワークスペースと `/tmp` から各13判定を通過した。ネイティブの保持は約662.28 msと663.48 ms。各128,256・128,384フレームのデジタルPCMが同じ実行のCLIとビット一致し、両方の購読が切断時に解除された。別名の無操作入力は13判定、2入力で同じ音を保持する試験は31判定、固定上流の2試験を通過した。macOS 15.6.1 arm64、Chrome 157.0.8103.79、Rust 1.94.1、Python 3.14.4、Node 24.19.0を使った。この比較は仮想入力で実施した。物理MIDI鍵盤での採取は後日行う。[再実行の要約](../runs/worklet-midi-coremidi-same-name-20261123-repeat/summary.json)・[別名の回帰](../runs/worklet-midi-coremidi-same-name-idle-regression-20261123/summary.json)・[2入力の回帰](../runs/worklet-midi-coremidi-same-name-shared-regression-20261123/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=90000000 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py worklet-midi-same-name-new \
  --passive-fixture-with-same-name-input
```
