# ブラウザ標準のWeb MIDI許可画面

[先行の権限応答比較](worklet-midi-permission.md)では、ヘッドレスChromiumの試験コンテキストで許可と拒否を設定してアプリへの結果を観測した。今回は標準のダイアログを使い、実際の拒否、同じサイトでの直後の再試行、サイト設定でのリセット、許可、切断の順を比較する。対象は研究版の手動発声と固定上流のPlay。[事前登録](../cases/worklet-midi-browser-prompt.json)

## 固定上流の読解

- `Keys.MidiButton` がMIDIの状態を表示し、`setMidi(true)` が `connecting` に更新して `connectMidi()` を呼ぶ。処理中は同じPromiseを再利用する。ブラウザが `requestMIDIAccess({ sysex: false })` を許可すると、アクセスオブジェクトと状態変更の購読を設定し、入力ポート名を表示へ渡す。拒否時はPromiseの失敗をストアが受けて `denied` を表示する。[上流ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Keys.tsx#L113)・[状態の更新](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L388)・[標準APIの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L71)
- `disconnectMidi()` は世代番号を進め、入力ポートのイベントハンドラーと状態変更の購読を外して保持音を解放する。既存試験は仮想ポートの所有権と、待機中に切断した後の遅い許可を検証する。研究版の `useMidiConnection` は操作ごとの要求を比較し、切断後に届いた古い応答で状態を更新しない。ここで記録する量は権限の列挙値、入力数と購読数、実際に押したボタンと画面の文言である。[上流の切断処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L92)・[上流の仮想ポート試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L65)・[研究版の接続処理](../../../../web/prototypes/chimera-research/src/midi-connection.ts)

## 比較方法

研究版の通常ビルドと固定上流Playを別々のループバックポートから配信した。Google Chromeを試験専用の一時プロファイルで起動し、研究版のボタン、上流PlayのMIDIボタンから通常のWeb MIDIを要求する。ブラウザの標準許可画面をmacOSのアクセシビリティAPIで読み、拒否・許可の実際のボタンを押す。権限の初期化にはChromeのサイト設定にある当該オリジンのリセットを使う。ページに追加する観測コードではブラウザ自身の `requestMIDIAccess` を呼び、結果と購読数を記録する。Chromiumは通常のMIDI接続にも許可を要求する。[Chromeの標準動作](https://developer.chrome.com/blog/web-midi-permission-prompt)・[画面とAPIの観測器](../../../../web/prototypes/chimera-research/tools/capture-midi-browser-prompt.mjs)・[アクセシビリティの観測器](../tools/midi_permission_browser_ui.swift)

## 実測

| 操作 | Permissions API | 標準APIと研究版の画面 | 固定上流Playの表示 |
| --- | --- | --- | --- |
| 最初の接続前 | `prompt` | `MIDI未接続` | `MIDI` |
| 標準ダイアログで「ブロック」 | `denied` | `NotAllowedError`、接続の再試行が可能 | `MIDI: Blocked by the browser` |
| 同じサイトでそのまま再試行 | `denied` | `NotAllowedError`、ダイアログの再表示なし | `MIDI: Blocked by the browser` |
| Chromeの当該サイト設定で権限をリセットし、再試行 | `prompt` | 標準ダイアログが再表示 | `MIDI: Connecting…` |
| 標準ダイアログで「許可する」 | `granted` | 入力0件、SysEx無効、`MIDI入力なし` | `MIDI: Plug one in` |
| アプリの切断ボタン | — | 状態変更の購読1件→0件、`MIDI未接続` | 購読1件→0件、`MIDI` |

両実装の要求は `sysex: false` だった。Chromeの日本語画面は、この要求に対して「MIDI デバイスの操作と再プログラム」と表示した。サイト設定を変えた後には再読込を案内する帯が表示されたが、同じ画面から再度要求すると権限確認が出て、許可結果が届いた。[研究版のブロック画面](../runs/worklet-midi-browser-prompt-20261122-final-repeat/artifacts/candidate-voice-deny.png)・[固定上流の再許可画面](../runs/worklet-midi-browser-prompt-20261122-final-repeat/artifacts/upstream-play-allow.png)・[APIと購読の記録](../runs/worklet-midi-browser-prompt-20261122-final-repeat/summary.json)

## 切り分けと再現

初回はChromeのAXツリーに標準ダイアログが存在し、日本語の「許可する」が観測器のボタン名に無かった。識別を直した後は、表示要素の順番が変わって選択できない試行と、押下後の要求が保留のままの試行があった。ボタンを試験中のサイトと表示名で再同定し、その座標で入力した。次に、ダイアログ発見後に650 ms待つ条件をケース第2版に記録した。その実行で拒否を観測できた。Chromeの資料には敏感なダイアログへの表示直後の入力を無視する仕組みが記載されている。[初回のAX出力](../runs/worklet-midi-browser-prompt-20261122-a/summary.json)・[ボタン同定の失敗](../runs/worklet-midi-browser-prompt-20261122-b/summary.json)・[保留の状態](../runs/worklet-midi-browser-prompt-20261122-c/summary.json)・[Chromiumの入力保護](https://chromium.googlesource.com/chromium/src/%2B/f24d1b8dd62513b60dead55c115f6b1620af2747/docs/security/security-considerations-for-browser-ui.md)

拒否が通った試行では、サイト設定のリセット確認ボタンを確認ダイアログの子として照会するところで止まった。Chromeの設定画面で確認ダイアログを照合したうえで、スロットへ挿入された「リセット」ボタンをページから直接選ぶと操作できた。さらに初期3実行ではChromeの補助プロセスが終了後に計測ログへ追記した。元のマニフェストが指すバイト数までのログのSHA-256は一致した。ブラウザの標準エラーを一旦パイプで受け、終了時点のログを別ファイルに書いてから公開するようにした。[設定画面の停止](../runs/worklet-midi-browser-prompt-20261122-d/summary.json)・[ログ分離前に通過した実行](../runs/worklet-midi-browser-prompt-20261122-e/manifest.json)

研究ワークスペースから実行する。ChromeのプロファイルとWebビルドはRTL9210B-CG上の一時領域で作る。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_midi_browser_prompt.py worklet-midi-browser-prompt-new
```

macOS 15.6.1 arm64、Google Chrome 157.0.8103.79、Node.js 24.19.0、Python 3.14.4、Rust 1.94.1で実行した。ログを分離した最終2実行は、研究ディレクトリと `/private/tmp` のどちらからも各11判定と固定上流の2試験を通過した。権限の遷移、選択したボタン、標準APIの結果、画面表示、購読数は通過した4実行で一致した。全8実行の1,232入力・64出力を照合し、初期3ログの追記は各876バイト、最終2実行の出力はすべてマニフェストと一致した。ログと画像を含む採取物8,377,145バイトをRTL9210B-CGに保存し、一時プロファイルの消去を確認した。[最終実行](../runs/worklet-midi-browser-prompt-20261122-final/manifest.json)・[別ディレクトリからの再実行](../runs/worklet-midi-browser-prompt-20261122-final-repeat/manifest.json)
