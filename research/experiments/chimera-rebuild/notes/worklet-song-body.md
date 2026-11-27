# ブラウザの歌唱で体型を選ぶ

## 上流の読解

- `playTune` は歌詞を音節化し、拍長を持つ音符へ対応させる。組み込み曲では `nearestBody` を使い適したオクターブに移調できる。WASM APIは音符と `SongOptions` を受け取り、体型を `plan_song` に渡す。研究画面では手入力したMIDIをそのまま使い、体型を変えても同じ譜面を比較できるようにする。[曲を再生する入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[WASMの歌唱API](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L156)・[歌唱の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L167)
- 拍長は `60 / BPM` 秒。母音の先頭は拍の開始に置き、頭子音はその直前に置く。子音に次の母音と同じ `440 × 2^((m−69)/12)` Hzを設定し、母音を始める前にF0を移行させる。子音が収まらない場合は長さを圧縮する。母音目標と /s z/ の舌先は体型で選び、声帯開大の面積には長さ比の二乗を掛ける。第1音の周波数を基準に、声門の初期音高110 Hzから制御時計ごとにスコアを反映して放射を計算する。[音符と頭子音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L188)・[調音計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L287)・[声門制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)
- `sing_fast` は短い音の母音開始と頭子音の音高を、`sung_release` は語尾の長さに応じた開大・呼気の落ち方を検査する。先行のCLIケースは /pɑ sɑ zɑ/ と長い終音を固定し、拍時刻とF0を独立計算している。[拍と音高のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[語尾のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L49)・[体型別先行ケース](human-body-song.md)

## 事前登録

同じ譜面で音節の調音を揃えるため、CLIと同形式の構造化IPA音節を画面から使う。母音開始を0.300、0.800、1.300秒、二つのF0の中間点を0.736、1.260秒付近と予測する。声門・放射・口唇の観測間隔は64出力フレームとし、毎フレームのCLIで求めた頭子音中の変化から最大63フレーム後に検出されると見込む。4体型のオフライン・実時間でケースの保存操作を行い、同じCLI入力でのPCMと全観測点を照合する。[登録ケース](../cases/worklet-song-body.json)・[入力・窓・許容差](../cases/human-body-song.json)・[固定上流の先行実行](../runs/bodysong-20261120-repeat/manifest.json)

## 実装

ページの歌唱WASMに成人内女性比・子ども比を渡し、CLIと共通の `song::score_with_body` でジェスチャーを作る。Workletにも同じ体型を渡して声道と声門を初期化する。英語の歌詞には従来の辞書を使用し、明示したIPA音節は `Syllable` として直接パースする。譜面には最初の拍の秒数も入れ、音響計算の開始前に入力を確定する。観測用JSONと別に、姿勢・体型・譜面・音源を含むCLI形式のケースを保存できる。[WASMの歌唱入口](../crates/vocal-wasm/src/planning.rs#L132)・[ブラウザの合成と保存](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L195)

初回は計測器の参照名を修正する必要があった。体型表の定数を歌唱計測器に直接求めたため、ブラウザ起動前に終了した。既存のIPA計測器が保持する体型表への参照に修正し、同じ事前登録条件で再試行した。[初回の欠測記録](../runs/worklet-bodysong-20261120-a/manifest.json)

## 実測結果

Chromiumのオフラインと実時間で4体型を歌わせた。各条件は48 kHzで129,600フレーム。各体型で保存した2つのケースはバイト一致し、保存ケースをCLIの通常入口に渡すと、計画・ジェスチャー・PCMがブラウザと一致した。内部状態10系列の2,025点も同値だった。明示音節の場合は辞書のネットワーク要求が各条件で0件。実時間での開始は予定量子境界に一致し、停止後にContextが閉じることと再開始も確認した。[全条件の判定](../runs/worklet-bodysong-20261120-b/summary.json)・[子どもの保存ケース](../runs/worklet-bodysong-20261120-b/artifacts/child-live-case.json)

母音は0.300、0.800、1.300秒に始まり、頭子音 /p s z/ は0.232、0.704、1.228秒から次の母音と同じMIDI周波数を受け取った。平滑化F0が第1・第2音と第2・第3音の幾何平均を超えたのは、毎フレームのCLIで0.73602、1.26002秒。64フレーム間隔のブラウザでは0.73733、1.26133秒。どちらも計画上の頭子音区間内だった。両方の移行は64フレームの制御更新の先頭に起き、ブロック末尾で観測した結果、検出は63フレーム（1.3125 ms）遅れた。[頭子音と音高の照合](../runs/worklet-bodysong-20261120-b/summary.json)

| 体型 | /p/ の閉鎖開始のCLIフレーム | /p/ の閉鎖開始のブラウザ観測フレーム | 3音のPCMから求めたF0（Hz） |
| --- | ---: | ---: | --- |
| 成人男性 | 10677 | 10687 | 218.92・260.91・329.31 |
| 成人女性 | 10666 | 10687 | 218.71・261.27・329.22 |
| 子ども | 10616 | 10623 | 219.07・260.63・329.62 |
| 混合 | 10663 | 10687 | 218.73・261.17・329.30 |

独立計算との最大差は平滑化F0で `4.78×10⁻¹¹ Hz`、声門開大で `2.39×10⁻¹³ cm²`。最終音の開大と呼気の条件も通過し、末尾20 msのPCM絶対ピークは最大 `3.47×10⁻¹⁰`。固定上流とのPCMの最大絶対差は `9.31×10⁻¹⁰` だった。ブラウザが最初に観測した63番フレームでは、成人男性の声門流量に `8.21×10⁻¹⁶ cm³/s` の差があった。先行の全フレーム照合では、初期フレーム0の歯までの距離にも微小な差が見つかっている。この比較では計画と観測が許容差内に入った。上流の関連15テストも通過した。[PCMと内部状態の比較](../runs/worklet-bodysong-20261120-b/summary.json)・[全フレームの先行照合](human-body-song.md#実装と結果)

修正後の初回と `/tmp` からの再実行は各112項目を通過した。入力・PCM・CLIの出力・WASM・要約を含む38ファイルのSHA-256が一致した。実時間の観測JSONとブラウザ実行記録の計5ファイルには、Contextの開始位置・経過時間・停止操作の時刻といった時計に依存する値の差が残った。音声の出力フレームで揃えた観測と計画は一致した。[修正後の実行](../runs/worklet-bodysong-20261120-b/manifest.json)・[再実行](../runs/worklet-bodysong-20261120-repeat/manifest.json)

既存の実時間歌唱の初回回帰では、固定した旧版オフライン観測とのJSONのバイト一致だけが不合格だった。旧版は成人男性を暗黙に使い、新版は `body: "male"` を明示する。比較したWAVのSHA-256と他の全JSON項目は一致していた。固定上流と旧版の成果物を保持し、計測器で旧JSONの既定体型を補ったうえで観測を厳密照合する。WAVのバイト一致は同じ基準で調べる。[初回回帰の判定](../runs/worklet-bodysong-20261120-live-regression/summary.json)

比較器の修正後は既存の実時間歌唱の25項目が通過した。既存IPA発話の12項目、体型別英語発話の86項目、Cargoのワークスペーステスト、Clippy、WASMとブラウザのビルドも通過した。[実時間歌唱の再試行](../runs/worklet-bodysong-20261120-live-regression-body-default/summary.json)・[IPAの回帰](../runs/worklet-bodysong-20261120-ipa-regression/summary.json)・[英語発話の回帰](../runs/worklet-bodysong-20261120-english-body-regression/summary.json)

```bash
python3 tools/measure_worklet_song_body.py worklet-song-body-local-1
```
