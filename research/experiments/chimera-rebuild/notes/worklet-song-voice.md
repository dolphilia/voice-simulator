# ブラウザの歌詞とMIDIから歌唱を合成する

## 固定上流の読解と事前登録

上流版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `playTune` は発音辞書を準備し、歌詞を音節列へ変換して音符に割り当てる。`planSong` が音符番号、拍数、開始時刻、BPM、ビブラート深さをRustの `plan_song` に渡し、生成したスコアを発声経路に送る。辞書はgzipを展開して使用する。歌唱のJSON APIは計画を返し、音声スレッドは時間・重み・調音目標を数値で受け取る。[上流の歌唱UI](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[WASMの歌詞と計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L138)・[辞書の展開](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/engine.ts#L115)

1拍は `60 / BPM` 秒、MIDI音高は `440 × 2^((番号 − 69) / 12)` Hz。上流の `plan_song` は節の頭子音を拍より手前に置き、母音を拍付近から始める。頭子音のF0目標は続く母音と同じ。保持母音の長さからビブラートの適用を決め、語尾で条件を満たすと呼気を残した状態で声帯を開き始める。候補CLIでは音源の初期F0を110 Hzとし、第一音のF0を基準目標として設定してから、同じ時刻のスコアを発声器に渡す。観測する呼気ゲートは無次元、開大と断面積はcm²、F0はHz。ビブラートによる偏差は `1200 × log2(瞬時F0 / 平滑化F0)` セントで分かる。[歌唱の時刻](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L167)・[語尾の開大](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L565)・[候補CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs#L185)・[歌唱処理の先行検証](sung-voice.md)

上流の `sing_fast` は頭子音が次の音高を持つこと、`sung_release` は終音の長さに応じて開大が早まることを検査する。今回は既存の長音ケース `Pop Dee` を使う。60と69を1拍ずつ、120 BPM、0.5秒開始で入力し、2拍の開始0.5秒・1.0秒と、モノラル48 kHzの91,200フレームを予測する。歌唱元ケースの測定窓で2音のF0、ビブラート深さ、終端20 msのピークを引き継ぐ。時系列は64出力フレームごとの末尾を観測する。開大が進んだ1.42秒で呼気ゲート0.98以上・開大0.05 cm²以上、1.6秒でゲート0.02以下を予測する。辞書のバイト列、計画、PCMをCLIと照合し、数値誤差があれば最初の差を記録する。調音が未対応の歌詞を入力した後の再試行も検証する。[頭子音のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L69)・[語尾のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)・[比較条件](../cases/worklet-song-voice.json)・[入力](../cases/song-voice-long.json)

## ページ側の計画とWorkletの発声

歌唱の入力欄は英語の歌詞、テンポ、ビブラート深さ、MIDI番号と拍数を受け取る。ページは初回の歌唱で辞書を取得し、先頭2バイトがgzipなら `DecompressionStream` で展開する。UTF-8バイト列と入力JSONをページ側のWASMに渡す。CLIと同じ `english_syllables`、`song::plan`、`male_score` が順に音節、拍に対する音素区間、調音・呼気・音高のジェスチャーを作る。Workletは同じ合成コアと姿勢・肺圧・乱流設定を使用し、初期F0と第一音の基準F0を設定してからジェスチャーを評価する。[歌唱フォーム](../../../../web/prototypes/chimera-research/src/main.tsx#L169)・[辞書の取得](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L49)・[共有の音節化](../crates/vocal-core/src/phonetics/song.rs#L61)・[WASMの計画](../crates/vocal-wasm/src/planning.rs)・[発声の初期化](../crates/vocal-wasm/src/lib.rs#L134)

辞書と読解用JSONはページ側で扱う。Workletはジェスチャーごとに時刻・ランプ・強さ・オプションの7値、調音の17目標、声門と呼気の5目標を並べた `f64` 列を受け取る。数値列のNaNは指定のない目標を表す。48 kHzの出力1フレームに96 kHzの内部2サンプルが対応する。記録する出力フレーム番号は0始まりで、観測値の時刻は `(frame + 1) / 48000` 秒とした。歌唱ではIPA発話の観測列に平滑化F0と開大面積を追加した。[スコアの受け渡し](../crates/vocal-wasm/host/planning.ts)・[観測列](../crates/vocal-wasm/host/fixed-voice.ts)・[Workletの時計](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)

## 比較結果

- Chromium 156.0.8078.4の通常配信で15項目が通過し、`/tmp` からの生gzip条件は16項目が通過した。両実行のWAVと観測JSONはそれぞれSHA-256が一致した。音節・計画・ジェスチャーのCLIとの差は0で、2拍は0.5秒と1.0秒。PCM91,200フレームはCLIとビット一致し、内部状態10系列は1,425観測点で差0だった。Workletは128フレーム単位で713回呼ばれ、計測区間のWASM線形メモリの増加は0回だった。[通常配信](../runs/worklet-song-voice-20261119-b/manifest.json)・[辞書をブラウザで展開](../runs/worklet-song-voice-20261119-c/manifest.json)
- 固定上流とのPCMの最初のビット差は4,114フレームで、最大絶対差は `2.33×10⁻¹⁰`。登録した許容差 `1×10⁻⁶` 以内だった。CLIと上流の全フレームの比較では、初回の0フレームですでに口唇断面積に `2.22×10⁻¹⁶ cm²`、口唇流量に `4.95×10⁻¹⁷ cm³/s` の差がある。ブラウザで採取した最初の63フレーム目にも声門流量と放射の微小な差があり、比較した全観測点が許容範囲内だった。[最初の差と最大差](../runs/worklet-song-voice-20261119-c/summary.json)
- WAVの2区間から独立のYIN計測で262.63 Hzと441.79 Hzを得た。観測点でのビブラートの最大偏差は34.57セント。1.42秒のゲートは約1.000で開大面積は0.07535 cm²、1.6秒のゲートは0.00489。終端20 msのPCM絶対ピークは `3.39×10⁻¹⁰`。スコアの寄与と平滑化を独立式で計算したとき、CLIでの全区間の最大差は平滑化F0で `1.27×10⁻¹⁰ Hz`、開大面積で `4.56×10⁻¹³ cm²` だった。[測定窓と制御値](../runs/worklet-song-voice-20261119-c/summary.json)
- 初回は辞書のハッシュ照合だけが不通過だった。Vite previewの `Content-Encoding: gzip` によって取得時点で展開されるため、圧縮ファイルのSHA-256と一致しなかった。通常実行では受信形式に応じた期待値で照合した。再実行ではテスト用の経路からgzipをHTTPの符号化指定なしで返し、ブラウザが圧縮バイト列を受け取る条件も確認した。元のケースの許容差を使い、初回の判定を保存した。[初回の判定](../runs/worklet-song-voice-20261119-a/summary.json)・[通常配信のHTTP応答](../runs/worklet-song-voice-20261119-b/artifacts/browser-run.json)・[生gzip応答](../runs/worklet-song-voice-20261119-c/artifacts/browser-run.json)
- 画面で `Strut` の未対応音素 /ɹ/ を表示した後、`Pop Dee` に差し替えて保存できた。固定上流の関連17テストと候補のRustテスト・Clippy・書式検査、ブラウザの固定発声とIPA、CLI歌唱の回帰も通過した。[固定姿勢](../runs/worklet-fixed-voice-20261119-song-regression/summary.json)・[実時間固定発声](../runs/worklet-realtime-voice-20261119-song-regression/summary.json)・[IPA発話](../runs/worklet-ipa-voice-20261119-song-regression/summary.json)・[CLI歌唱](../runs/song-voice-long-20261119-browser-song-regression/summary.json)

この検証の範囲は成人男性の初期姿勢、英語歌詞、オフラインWorkletでの二音。動的な歌唱での実時間処理予算は次の比較条件として計測する。研究ディレクトリから、実行IDを変えて再現できる。

```bash
python3 tools/measure_worklet_song.py worklet-song-voice-local-1
python3 tools/measure_worklet_song.py worklet-song-voice-raw-local-1 --raw-dictionary
```
