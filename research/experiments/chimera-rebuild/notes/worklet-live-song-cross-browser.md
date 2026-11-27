# FirefoxとChromiumの48 kHz実時間歌唱

## 歌詞から処理量子まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `playTune` は、辞書を準備して歌詞から音節を作り、各音節にMIDI音高と拍数を与える。`plan_song` は先頭の拍を `t0` とし、音符ごとに `拍数 × 60 / BPM` 秒を足す。各句で頭子音と末子音の長さを収め、母音核を拍に置く。母音の基本周波数は `440 × 2^((MIDI−69)/12)` Hz。子音は付随する音符の音高を持ち、0.3秒を超える母音にはビブラートを付ける。`engine_schedule` を経て、`Engine::schedule` がジェスチャーの両端へ `voice.clock + lead` 秒を加える。`Engine::render` はホストから受け取ったフレーム数を内部の制御境界で分けて進める。[上流画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L167)・[Workletの予定](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L134)・[予約とレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L174)

上流の `fast_runs_land_on_the_beat` は、短音符を続けても母音核が拍に置かれることと最小母音長を検査する。`a_sung_phrase_ending_on_a_vowel_is_let_go_gradually` は、開大ランプの長さと呼気が保たれる順序を調べる。`output_does_not_depend_on_the_host_block_size` は同じ操作の絶対時刻を保つ場合にホストの分割を変えてもPCMが一致することを確かめる。今回の上流PCM・時系列・計画は、これらを含む既存のテストと調査用プローブから生成する。[拍の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[語尾の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L48)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[プローブ](../tools/upstream_bilabial_probe.rs)

候補では `SongPanel.run` の歌詞・音符から `prepareSongVoice` が両経路で同じ計画と初期状態を作る。辞書の内容をWASMへ渡し、Rustの `plan` と `score_with_body` が音符・音素、調音、呼気、声帯開大、ビブラートの目標を返す。実時間では `AudioContext` を48 kHzで開き、`RealtimeSpeechCapture` が8連続量子を確認した次の量子から2,048フレーム先を予約する。待機中は出力が無音で、合成器はフレーム0に留まる。`FixedProcessor` は開始後、128フレームの描画を64フレームの観測境界でも分割し、内部96 kHzで進んだ状態を出力フレーム末端で保存する。観測には唇の最小断面積（cm²）、声門流量（cm³/s）、F0（Hz）がある。最後は集計したWAVと観測用のバッファを返してエンジンを解放する。[通常画面](../../../../web/prototypes/chimera-research/src/main.tsx#L553)・[候補の歌唱計画](../crates/vocal-core/src/phonetics/song.rs#L233)・[オフラインと実時間の共通準備](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L206)・[予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[描画と終了](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L119)

## 比較の登録

`Pop Dee`、120 BPM、MIDI 60と69を各1拍、先頭の拍0.5秒、ビブラート35セントを使う。ブラウザの実際の開始フレームを `S` とすると拍は `S + 24,000` と `S + 48,000`。出力91,200フレームは713量子となり、最後の量子の64フレームを採取し、残り64フレームをゼロで埋める。実時間とオフライン、CLIの77・128分割、固定上流に照合する。F0はPCMの独立YINとMIDIの式で確かめ、開大とF0の制御目標はジェスチャーの包絡を独立に計算する。通常のApp経路で接続後0.7秒からの停止、Contextの閉鎖、再開後の完了も確認する。Geckoの診断は完了までの歌唱1回とし、内側のJS呼び出しがある外側の区間を数える。[事前登録](../cases/worklet-live-song-cross-browser.json)・[歌唱の入力と許容差](../cases/song-voice-long.json)・[独立計算](../tools/measure_song_voice.py#L58)・[音声のネイティブ計時の先例](worklet-live-ipa-cross-browser.md#firefoxのネイティブな時計との照合)

過去のChromium試験では `Strut` の /ɹ/ が拒否された。今のCLIでその歌詞の計画が通り、`...` は音節が0件で失敗することを確認した。現在の計測では `...` の拒否から復帰する。WASMと辞書の応答は最初の歌詞操作から監視する。未対応子音を検査した旧実行の入力と判定は保存した。[以前のChromium](../runs/worklet-live-song-20261120-b/manifest.json)・[音節0件の検査](../crates/vocal-core/src/phonetics/song.rs#L242)・[ブラウザの操作](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L953)

## 歌唱の結果

通常の12試行で、Firefox 157.0とChromium 156.0.8078.4の実時間・各オフライン、CLIのPCMは91,200フレームすべてビット一致した。音響観測1,425行には唇の最小断面、F0、声門流量を含み、計画・調音ジェスチャーとともに一致した。同じ入力の保存済みChromiumのWASMと現在のWASMは異なるハッシュだった。PCM・音響観測・計画のハッシュは保存済みChromiumと全試行で同じ値だった。独立計算の拍は出力フレーム24,000と48,000。接続から0.704〜0.715秒で停止した12試行はすべてContextを閉じ、再開後に完了した。[初回の判定と各出力](../runs/worklet-live-song-cross-browser-20261121-a/summary.json)・[再実行](../runs/worklet-live-song-cross-browser-20261121-repeat/summary.json)

固定上流との差はフレーム0の口端平均面積、口腔第1セル最小断面、口端流量、放射差分ですでに観測できる。口端平均面積差は2.22×10⁻¹⁶ cm²。総放射を経たPCMで最初のビット差はフレーム4,114、全区間の最大差は2.33×10⁻¹⁰。YINによるF0は262.63 Hzと441.79 Hz、ビブラート最大34.57セントだった。1.42秒では呼気ゲートが1で開大0.07535 cm²、1.6秒では呼気ゲートが0.004886。独立制御式との差は平滑F0で1.27×10⁻¹⁰ Hz、開大で4.56×10⁻¹³ cm²以内だった。固定上流17試験と候補の割り当て試験を通過した。[固定上流・CLI・音響の照合](../runs/worklet-live-song-cross-browser-20261121-a/summary.json)・[試験ログ](../runs/worklet-live-song-cross-browser-20261121-a/artifacts/reference/upstream-tests.log)

## Context上の開始と描画時間

通常の12試行で最初のWorkletコールバックはChromiumのフレーム2,048（42.7 ms）に対し、Firefoxは8,448〜9,216（176.0〜192.0 ms）だった。その後の予定位置は起動の確定位置からどちらも2,048フレーム先で、713量子にフレームの欠落はなかった。Contextの再開はWASM取得・コンパイルと並行し、計画を済ませてからWorkletを接続する。JSは展開済み辞書を再利用する。歌唱計画はWASMインスタンスを作り、そのメモリに辞書をコピーして `English::with_dictionary` で読み直す。今回の時計はContextの最初のコールバックから処理の内訳を採った。WASMの準備、辞書と計画、Workletの登録・接続のどこで差が生じるかは別の対照で測る。[Contextの開始](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L125)・[プランナーと辞書の転送](../crates/vocal-wasm/host/planning.ts#L67)・[辞書の読み直し](../crates/vocal-wasm/src/planning.rs#L278)・[初回の量子記録](../runs/worklet-live-song-cross-browser-20261121-a/summary.json)・[再実行の量子記録](../runs/worklet-live-song-cross-browser-20261121-repeat/summary.json)

Firefox診断の4試行では、外側の区間738、内側のJS呼び出し737を採った。JS呼び出しは起動待ち8、予定待ち16、採取713で、先頭から一対一に包含された。外側にだけ残った1区間は末尾にあった。以前の `/ɑpɑ/` では末尾が2区間だったため、両方のマーカーの包含関係で対応づけた。ネイティブな開始間隔では、冒頭32量子を除いて長い間隔が全試行で2量子おきに現れた。[歌唱の区間照合](../runs/worklet-live-song-cross-browser-20261121-repeat/summary.json)・[実時間IPAの区間照合](worklet-live-ipa-cross-browser.md#firefoxのネイティブな時計との照合)

通常試行の `Date.now` によるp99は、冒頭32量子を除いた区間でChromiumが毎回2.00 ms、Firefoxが2.00〜3.00 ms。Firefoxの再実行1試行で681量子中9件が3 msとなり、予算2.667 msの判定を通過しなかった。別のネイティブ診断では同区間のp99は1.710〜1.774 ms、予算超過は0件。診断の1試行で同一の歌唱に対して `Date.now` はp99が3.00 ms、ネイティブでは1.745 msと記録した。通常の不通過試行にはネイティブ計時の記録がない。冒頭のネイティブ処理は4試行すべてで最初の量子が3.601〜3.962 ms、うち2回は次の量子も予算を超えた。物理出力の途切れと、人による発話・歌唱の試聴は未計測。[通常と診断の初回値](../runs/worklet-live-song-cross-browser-20261121-a/summary.json)・[再実行の不通過と診断](../runs/worklet-live-song-cross-browser-20261121-repeat/summary.json)

同じネイティブABIの割り当ては11,809回。うち冒頭32量子後は11,296回で、既存の歌唱比較と一致した。通常の全試行でWASM線形メモリの増加は0件だった。[今回の比較](../runs/worklet-live-song-cross-browser-20261121-repeat/summary.json)・[割り当てを測る範囲](worklet-live-song.md#結果)

## 再現と保存

macOS 15.6.1 arm64、Rust 1.94.1、Bun 1.4.4、Node 24.19.0、Python 3.14.4、NumPy 2.4.4で計測した。研究ワークスペースから新しい実行IDを指定する。初回は179/179判定、`/tmp` からの再実行は178/179判定。基準を維持し、結果をそれぞれの実行IDで保存した。

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=450000000 \
  ../../.venv/bin/python tools/measure_worklet_live_song_cross_browser.py worklet-live-song-cross-browser-next
```

音声・観測・Geckoプロファイル・密なCSV・上流の生PCMを可逆圧縮し、主比較2回の約125.91 MBをRTL9210B-CGに置いた。両実行で各85成果のサイズとSHA-256を照合し、展開したブラウザWAV28点はバイト一致した。[初回マニフェスト](../runs/worklet-live-song-cross-browser-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-cross-browser-20261121-repeat/manifest.json)

従来の `measure_worklet_song.py --live --raw-dictionary` は26判定を通過した。`Content-Encoding` なしのgzip辞書を受け取る経路でも、実時間・オフライン・CLIを照合し、24成果のハッシュを確認した。共通のネイティブ計時処理は以前のIPAプロファイル2件に適用し、既存の判定値を再現した。[従来経路の回帰](../runs/worklet-live-song-20261121-cross-browser-regression/manifest.json)・[既存IPAの対象プロファイル](../runs/worklet-live-ipa-cross-browser-20261121-repeat/manifest.json)
