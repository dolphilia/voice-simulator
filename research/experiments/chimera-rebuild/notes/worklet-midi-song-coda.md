# Web MIDIによる鍵盤歌唱の語末 /p/

## 固定上流の読解

対象の固定版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。接続処理の `connectMidi` から `store.noteOn`・`noteOff` が受け取った音番号は、歌唱モードで `singNoteOn`・`singNoteOff` へ進む。歌詞は `lyricsToSyllables` で頭子音・母音核・末子音に分かれる。押下では `startNote` が母音を30秒まで保つジェスチャーを組み、調音・呼気と音高・ビブラートを別タグにする。現在の鍵盤を離しても他に保持音があれば `glide` で音高だけを切り替える。最後の離鍵では両タグを解放し、次が母音継続でなければ `plan_note_off` の語尾を別タグで足す。声門を開く末尾の `exhale` は、次の押下で単独で終了できるタグを持つ。[MIDI入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[歌唱時の状態とタグ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L207)・[押下・離鍵の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L404)

`tail` は下降二重母音の後半があれば最初に足し、その後に末子音を置く。capの母音核は単母音 /æ/ なので、今回の離鍵計画の音素は /p/ だけ。明示された時間がなければ、子音の長さは発話の既定値の0.7倍。/p/ の既定85 msから59.5 msとなる。計画基準 `LIVE_T0=-0.045` 秒に60 msの余裕とWorkletへの6 msの先読みを足すと、離鍵採用から音素開始は21 ms。前の音素が無い単独の計画で、子音の閉鎖目標を追加する遅れは0。`oral_gestures_into` は唇の閉鎖ジェスチャーを音素開始より22 ms早く、下降の始まりを音素末尾より19 ms早く置く。強度40の重みを使い、30 msの余弦の立ち上がりと18 msの減衰で調音目標に重ねる。口唇開度はcm、気道の最小断面はcm²。実際の閉鎖時刻は調音速度と声道形状で決まる。[子音の持続時間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs)・[閉鎖の時間補償](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[時間の移動](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L176)

`HumanVoice::control` は64出力フレームごとにジェスチャーの目標を合成し、調音・呼気・声門を更新する。96 kHzの内部レンダーでは、この後に声門面積、圧力・流量、放射を各サンプルで進める。口端流量はcm³/s、総放射の時間微分はcm³/s²。間引き・直流除去・制限の後に48 kHzのf32 PCMを出す。上流テスト `live_notes_match_typescript` は、押下・離鍵・母音継続が出すジェスチャーを固定の比較資料と照合する。`singing-live.test.ts` は開音節・レガート・離鍵後の無音を測る。今回の比較は閉音節を最後まで一音だけ保持し、末子音を除いた対照で閉鎖と流量を検証する。[制御と音響](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[計画テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_planning.rs#L190)・[鍵盤歌唱テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/singing-live.test.ts#L79)

## 事前登録

成人男性でMIDI 45を0.14秒に押し、0.65秒に離す。音高は110 Hz、ベロシティ96、ビブラート0で、出力48 kHz・内部96 kHz。閉鎖ジェスチャーの上限に達するのは採用時刻の1 ms前に置かれ、下降は61.5 ms後と予測した。後者が正確な計画時刻で、ジェスチャーは離鍵まで追加されないため、姿勢と波形が変わるのは採用以降になる。唇の実閉鎖、再開口、口端流量、声門、末尾PCMを離鍵からの窓で観測する。音韻、入力、採用フレームと判定閾値を固定し、同じ各エンジンで語末だけを省く対照を実行する。[ケース定義](../cases/worklet-midi-song-coda.json)

## 実装と再実行

候補と固定上流の通常画面に仮想ポートAから押下・離鍵を送った。候補は既存のAudioWorkletの採用時刻と加工前WAVを書き出した。CLIの `observe_gestures` を指定すると、採用したイベントの直後のスコアをタグ付きで読める。既存の内部観測列に口端流量、声門面積、声門流量、放射の時間微分を追加した。[候補のスコア](../crates/vocal-core/src/phonetics/live_song.rs)・[採用時刻の再実行と観測](../crates/vocal-cli/src/live_song_case.rs)

固定上流の画面が送ったジェスチャーとタグ解放を、既存のメッセージ送信を通しながら保存した。固定Rustの `Engine::schedule` と `release` に同じ順序で渡し、候補の採用フレームに時刻を揃えた。固定Rustのレンダーには候補の初期姿勢・初期F0 110 Hz・音源設定を渡し、ドリフト・ジッタ・シマーを0にした。候補の対照は音節の末子音配列だけを空にし、固定上流の対照は離鍵時のタグ解放を残して語尾を追加するメッセージを省いた。閉鎖時の口端流量は、口端放射の慣性による出入り口付近の成分を避けるため、最小断面0.05 cm²未満の連続区間の中央半分で測った。[上流の画面の採取](../../../../web/prototypes/chimera-research/tools/capture-midi-song.mjs)・[固定Rustの再生](../tools/upstream_live_song_probe.rs)・[計測器](../tools/measure_worklet_midi_song_coda.py)

macOS 15.6.1 arm64とRust 1.94.1、Node 24.19.0、Bun 1.4.4、Python 3.14.4、NumPy 2.4.4を使用した。作業用のRTL9210B-CGは書き込み可能で空き886 GiB。作業時の最大見積もりを1 GiBとし、時系列と対照を外部ディスクへ直接出力した。最初の実行はケースファイル名と合格済み実行のケースIDを照合する箇所で停止した。拡張子を除いて比較するよう変更した。[初回の停止](../runs/worklet-midi-song-coda-20261121-a/failure.json)

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_worklet_midi_song_coda.py worklet-midi-song-coda-local-1
```

## 結果

両方の画面はcapを1音節として扱い、MIDI 45の押下で持続し、離鍵で解除した。正式実行の採用フレームは13,568と37,888。上流は母音のタグ2・3を解放し、唇の閉鎖をタグ4で足した。候補でも閉鎖にタグ4が加わった。唇の目標−0.25 cm、強度40、計画の上限到達時刻−1 msと下降開始61.5 msが両方で一致した。これは計画の時刻で、閉鎖ジェスチャーを追加したのは離鍵採用時だった。[計画と採用フレーム](../runs/worklet-midi-song-coda-20261121-final/summary.json)

| 観測 | 候補 | 固定上流 |
| --- | ---: | ---: |
| 唇の最小断面が0.05 cm²を初めて下回る | 離鍵52.354 ms後 | 離鍵52.354 ms後 |
| 同じ閾値へ戻る | 離鍵96.000 ms後 | 離鍵96.000 ms後 |
| 閉鎖窓中央の口端RMS／持続母音の口端RMS | 0.04958% | 0.04958% |
| 離鍵300〜500 msのPCM RMS／持続母音のPCM RMS | 9.51×10⁻⁸ | 9.51×10⁻⁸ |
| 語末を省いた離鍵後200 msの唇の最小断面 | 1.57105 cm² | 1.57105 cm² |

語末を省いた対照とのPCMは、離鍵より前が両版ともビット一致した。離鍵採用フレームに唇・呼気・放射の差が現れ、正式実行のPCM差は5出力フレーム後に \(10^{-6}\) を超えた。作業ツリーでの計測では6フレーム後だった。正式実行の語末あり／なしの波形差を両版で求めると、その差分どうしの最大絶対差は \(5.82\times10^{-11}\)。[候補と対照の観測](../runs/worklet-midi-song-coda-20261121-final/artifacts/no-coda-voice.retained.csv)・[固定上流の対照](../runs/worklet-midi-song-coda-20261121-final/artifacts/upstream-no-coda-voice.retained.csv)

追加集計では、正式実行の断面0の区間は両版とも出力40,959〜42,303で、1,345フレーム。口端流量は0.423675から \(5.96\times10^{-7}\) cm³/sへ減った。既存の両唇破裂音計測と同じ放射の減衰式 \(U_n=U_0\cdot0.995^{2n}\) は全区間で上流・候補とも最大 \(3.89\times10^{-16}\) cm³/s以内だった。最初の実行では断面0の区間は1,281フレーム。閾値0.05 cm²の閉鎖・開放時刻は離鍵に対して安定していた。これらは結果を読んだ後の追加集計で、事前判定には含めていない。[候補の閉鎖系列](../runs/worklet-midi-song-coda-20261121-final/artifacts/cli-voice.retained.csv)・[上流の閉鎖系列](../runs/worklet-midi-song-coda-20261121-final/artifacts/upstream-voice.retained.csv)・[放射慣性の基準検証](bilabial-stop.md)

候補のブラウザとCLIは正式実行の108,288 PCMフレームがビット一致し、846時点の6観測列も一致した。固定Rustと候補では最初の口端流量と総放射に微差があり、出力PCMの最初のビット差は押下前の4,114フレーム。正式実行のPCM最大差は \(9.31\times10^{-10}\)。唇の開度、呼気、声門面積は一致し、初期の放射差を生む演算は未特定。物理MIDI機器と許可画面も未検証。[正式結果](../runs/worklet-midi-song-coda-20261121-final/summary.json)・[作業ツリーからの結果](../runs/worklet-midi-song-coda-20261121-b/summary.json)

Chromium 156.0.8078.4を使用した。最初の32量子を除いた正式実行の814量子でp95・p99は各2 ms、最大3 ms。1 ms刻みの計時で約2.67 msを超えた量子は1件で、採取フレームの欠落は0。4本の観測CSVは全行で判定してから主要列に絞り、合計83.9 MBから77.8 MBに減らした。[実行と保存記録](../runs/worklet-midi-song-coda-20261121-final/manifest.json)

作業ツリーと `/tmp` から各13項目、開音節・レガート・母音継続のMIDI回帰16項目、`cargo test --locked --workspace` 40件に合格した。変更箇所のRust整形とJavaScript構文も確認した。ワークスペース全体の整形確認では、前工程と同じハッシュの `phonetics.rs` に既存のモジュール順の差が残った。[開音節の回帰](../runs/worklet-midi-song-coda-20261121-open-regression/summary.json)
