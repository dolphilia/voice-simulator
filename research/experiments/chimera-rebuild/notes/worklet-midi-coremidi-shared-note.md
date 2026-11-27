# CoreMIDIの2入力で同じ音を保持する

前回は単一のCoreMIDI仮想入力を押鍵中に外すと、研究版と固定上流Playが保持を解除した。今回は同じA3を2入力から送り、先に押したAを先に外す。Bが所有を引き継いでいる区間と、Bを外した後の減衰を別々に観測する。[登録ケース](../cases/worklet-midi-coremidi-shared-note.json)・[単一入力の削除](worklet-midi-coremidi-unplug.md)

## 読解と予測

- 固定上流の `press` は音番号ごとに所有者の集合を持つ。所有者は入力IDとステータス下位4ビットのチャンネルの組で、集合が空のときに限り演奏側の `noteOn` を呼ぶ。`attach` は接続中のポートIDを集め、消えたポートの所有者を `liftWhere` で取り除く。`lift` は最後の所有者が消えたときに `noteOff` を通知する。既存の仮想入力試験は同音の所有をポート・チャンネル別に数え、先に一部を解放しても、その音の `noteOff` が出ないことを確認している。[上流の所有者集合](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L21)・[仮想入力の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L84)
- 研究版の `listenMidi` は、入力オブジェクトごと・チャンネルごとの保持音集合と、全入力を合算した音ごとの所有数を持つ。AとBが同じチャンネルのA3を押せば所有数は0→1→2、AとBを外すと2→1→0。選択音は1回目の押鍵で57、最後の削除で `null` になる。Workletは次の128出力フレーム境界で更新し、ゲート目標0からの減衰は `G(t+Δt)=G(t) exp(−Δt/0.07)`。単位は音番号、無次元ゲート、音声時計の秒で記録する。[研究版の保持と解除](../../../../web/prototypes/chimera-research/src/midi-input.ts#L8)・[音源での適用](../../../../web/prototypes/chimera-research/src/live-processor.ts#L168)
- AとBは同じノート番号・チャンネルでベロシティを93・67に分ける。受信バイトとポートIDを照合し、2件目も実際にブラウザへ届いたことを確認する。Aの削除後350 msはBを残し、固定上流の音声時計ではAが消えてから50–300 msのゲートを取る。研究版では立ち上がりを過ぎてから最後の解放まで全量子を検査し、途中のゲート低下や余分なWorklet更新があれば判定に残す。

## 実測

4回の画面操作で、Aの `[144, 57, 93]` とBの `[144, 57, 67]` が異なるIDから信頼済みイベントとして1件ずつ届いた。CoreMIDI送信プロセスの記録も各入力で追加・押鍵・削除の3操作だった。ブラウザの入力一覧と購読はA・Bの2件、Bのみの1件、0件の順に変わった。Aの切断後からBの削除を始める直前までの354.1–357.3 msに保持音57を確認した。Bの切断後に初めて保持音が空になった。[初回の詳細](../runs/worklet-midi-coremidi-shared-note-20261122-a/artifacts/coremidi-browser.json)・[再実行の詳細](../runs/worklet-midi-coremidi-shared-note-20261122-repeat/summary.json)

| 観測点 | 2実行の結果 |
| --- | --- |
| 研究版の発声 | Workletが採用した音の状態は57と `null` の2件。定常区間のゲートは全量子で0.99999989以上、連続した50 ms窓23本のPCM RMSは最低0.11627だった。 |
| 固定上流Playの発声 | 呼気目標が1になったのはAの押鍵、0になったのはBの切断の各1回。A切断後50–300 msの全観測でゲートは丸めて1.0000、出力RMSは0.25025以上だった。 |
| 最後の入力が消えた後 | 研究版では単一入力の削除と、解除後128、768、3,456、9,600フレームの正規化ゲートが完全に一致した。上流の減衰時定数はどちらも70.0 msだった。 |
| CLI再生 | 研究版の加工前PCMをWorkletが採用した時刻でCLIに再入力した。両実行とも171,776フレームが各回のCLI出力とビット一致した。 |

保持とゲートの応答は両実装で一致した。今回の削除順はA→Bで、逆の順序や実際の鍵盤を使う場合は未観測。[初回の判定](../runs/worklet-midi-coremidi-shared-note-20261122-a/summary.json)・[再実行の判定](../runs/worklet-midi-coremidi-shared-note-20261122-repeat/summary.json)

## 再現

研究ワークスペースから実行する。ChromeとCoreMIDIを使うMacで、固定した単一入力の削除対照のケースと採取物を検証してからRTL9210B-CGに保存する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_coremidi.py --shared-note worklet-midi-coremidi-shared-note-new
```

macOS 15.6.1 arm64、Chrome 157.0.8103.79、Node.js 24.19.0、Rust 1.94.1、Python 3.14.4で実行した。研究ワークスペースと `/private/tmp` から各31判定に合格した。単一入力の削除と通常のNote Offの回帰は35・26判定を通過し、4実行とも固定上流の2試験が通過した。1,122入力・40出力をサイズとSHA-256で照合し、採取物68,928,791バイトをRTL9210B-CGに保存した。実行後のCoreMIDI入力・出力は0件だった。[再実行](../runs/worklet-midi-coremidi-shared-note-20261122-repeat/manifest.json)・[単一入力削除の回帰](../runs/worklet-midi-coremidi-unplug-20261122-shared-regression/manifest.json)・[通常離鍵の回帰](../runs/worklet-midi-coremidi-20261122-shared-regression/manifest.json)
