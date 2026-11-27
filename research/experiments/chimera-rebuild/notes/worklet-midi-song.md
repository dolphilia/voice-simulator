# Web MIDIによる鍵盤歌唱

## 読解と事前登録

固定上流では `connectMidi` が入力・チャンネルごとの保持を管理し、最初の押下と最後の解放を `useStore.noteOn`・`noteOff` に渡す。歌唱モードでは `singNoteOn` が歌詞のカーソルを一つ進める。 `singNoteOff` は解放した音番号が現在の発声音と異なるときは保持一覧だけを更新し、発声音を解放すると直近の保持音へ戻る。 `la ma -` は /lɑ/、/mɑ/、直前の母音の継続の順で、継続を使うと発声中の音節名は `ma` のまま進む。[上流のMIDI入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[モードごとの振り分け](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L335)・[歌唱の保持と解放](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L189)

上流の `plan_note_on` は前の発声が残っていればその末子音、次の頭子音、保持する母音を順に計画する。音高は `440×2^((MIDI−69)/12)` Hz。30秒の保持を表すジェスチャーに調音・呼気用のタグと、その次の番号の音高・ビブラート用タグを付ける。 `plan_melisma` と保持音に戻る処理は音高のタグだけを解放する。ジェスチャーを立ち上がりの途中で解放したときは、余弦の下降側から同じ活性になる時刻を求めて、そこから減衰させる。上流の試験では、/m/ の閉唇、母音を保った転調、古い押下の解放、最後の解放から300 ms以降のRMSを照合する。[音符ごとの計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L382)・[タグの解放](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/score.rs#L334)・[上流の歌唱試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L80)

成人男性・48 kHz出力でMIDI 45、48、52を重ね、先に45を解放し、後で52を解放して48へ戻る。最終的に48を解放する。観測窓は安定した母音の区間、48の押下後180 ms以内の閉唇、母音を継続している区間、最後の解放の300 ms以降。安定窓の音高差は30セント以内、有声度は0.5超、閉唇は0.05 cm²未満、再開口と母音継続は0.2 cm²超、解放のRMSは発声中の最大RMSの0.3%未満を予測した。[事前登録とイベント時刻](../cases/worklet-midi-song.json)

## 研究版の実装

研究版では既存のMIDI入力の保持管理を共有し、鍵盤歌唱で押下と解放を別々にWorkletへ送る。Rustの `LiveSong` は、歌詞カーソル・押下順・現在の音節とMIDI番号・タグ付きジェスチャーを持つ。同じ描画量子に複数のイベントが届く場合は順序を保つ。合成前の出力フレームで適用し、音源の秒時計へ6 msの先読みを足して配置する。母音用の呼気は速度96で `0.62 + 0.4 = 1.02`。母音継続と保持音への復帰でこの呼気と母音の姿勢を保持する。[Rustの歌唱状態](../crates/vocal-core/src/phonetics/live_song.rs)・[MIDI入力](../../../../web/prototypes/chimera-research/src/midi-input.ts)・[Workletでの採用順](../../../../web/prototypes/chimera-research/src/live-processor.ts)

歌詞は既存の発音辞書で音節化し、UTF-8の音節JSONをページからWorkletへ送る。最初の実機計測は、AudioWorkletの実行環境にない `TextEncoder` を使って準備中に失敗した。UTF-8への変換をページへ移した後は初期化して録音できた。出力の `live_song_voice` ケースには音節、初期姿勢、サンプルレート、採用フレーム付きの入力、録音の停止境界が入る。同じRustの状態でCLIが実行でき、観測CSVで呼気、唇端の最小断面積、音高、有声度、鼻端流量を読める。[失敗の記録](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs/.midi-song-probe.iyAAQG/midi-song-browser.json)・[ブラウザの書き出し](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts)・[CLIの実行](../crates/vocal-cli/src/live_song_case.rs)

## 比較結果

最初の公式実行では15項目が通過した。仮想MIDIを実際のブラウザで受け、研究版のCLIと固定上流でそれぞれ `45 la → 48 ma → 古い45を解放 → 52 ma → 48 ma → 解放` になった。音節カーソルは1、2、2、0、0、0。CLIとWorkletの6系列の観測差は0、加工前WAVは173,312フレームのビット一致だった。実時間の操作をCLIで再生するときは採用済みのフレームを使い、CLIは異なる113フレーム出力ブロックで実行した。[初回の判定](../runs/worklet-midi-song-20261120-a/summary.json)・[固定上流の操作と時系列](../runs/worklet-midi-song-20261120-a/artifacts/midi-song-browser.json)

初回の /m/ で研究版の唇端最小面積は0 cm²、固定上流の公開テレメトリの口腔末端面積は0.00273 cm²まで下がった。観測位置の系列はそれぞれの実装で定義が異なる。母音継続後から最後の解放までは、研究版で6.51 cm²以上、固定上流で6.77 cm²以上を観測した。最後の解放から300 ms以降の最大RMSは発声区間に比べて、研究版で約 `2.23×10⁻⁷`、固定上流で約 `7.72×10⁻⁷` だった。[初回の観測値と判定窓](../runs/worklet-midi-song-20261120-a/summary.json)

異なる作業ディレクトリからの最終計測は16項目すべてに合格した。加工前WAVは173,824フレームのビット一致。波形にYINを適用すると、安定した母音の音高は110.00、130.74、164.63、130.76 Hzで、理論値との差は最大1.95セント未満だった。Workletの相対採用時刻は登録した間隔から最大5.34 msずれた。手動MIDIの回帰は16項目に合格し、Rustのコア試験15件、WASM試験25件も通過した。解放ランプの試験では立ち上がり途中でも活性が連続し、解放したタグの未開始のジェスチャーが消えることを確認した。[最終計測](../runs/worklet-midi-song-20261120-final/summary.json)・[手動MIDIの回帰](../runs/worklet-midi-song-20261120-manual-regression/summary.json)

最終試行では最初の音を採用した量子の処理に4 msかかり、48 kHz・128フレームの約2.67 msを上回った。後続の採用量子は1〜2 msだった。合成時計と保存PCMは連続した。最初の押下は音節計画と調音・声道更新を同じスレッドで行うため、先に計画を用意する場合と比較し、各段の処理時間と音の一致を測る余地がある。今回は開音節と母音継続を比較し、末子音のある語尾と物理MIDIでの測定を残した。[採用量子と音声の計測](../runs/worklet-midi-song-20261120-final/summary.json)

仮想環境を有効にし、研究ディレクトリで次のように再実行する。WAV・CSV・採取時刻とソースの控えは作業用RTL9210B-CGへ直接書き出す。[実行コマンド・環境・出力ハッシュ](../runs/worklet-midi-song-20261120-final/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 \
  python3 tools/measure_worklet_midi_song.py worklet-midi-song-local-1
```
