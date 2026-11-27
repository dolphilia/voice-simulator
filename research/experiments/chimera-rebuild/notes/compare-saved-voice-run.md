# 保存済みの実行を合成せずに比較する

## 固定上流と既存計測の読解

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`chimera-cli/src/main.rs` から `compare.rs` に進む既存比較は、合成した音声とTSP・CSDなどの参照を、同じサンプルレートの音声として解析する。保存WAVを読む `read_wav` はRIFFの `fmt ` と `data` を探し、量子化されたPCMと浮動小数点を扱う。複数チャンネルは平均する。保存形を作る `wav::write` は通常16ビットの量子化WAVを出し、`--float` では合成器のf32を書き出す。研究版の `network_case::pcm::write_frames` はモノラルf32をそのまま保存し、出力フレーム番号と末尾内部サンプル番号を別の列に書く。[上流のCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs)・[上流の参照読み出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L330)・[研究版のWAV出力](../crates/vocal-cli/src/network_case/pcm.rs)

上流の `tests/common/mod.rs::compare_audio` は基準ピークに対する最大差と最初の分岐、および10 ms窓のRMS包絡を検査する。`output_does_not_depend_on_the_host_block_size` はブロックの切り方を変えたf32波形をビット単位で確認する。研究版の手動MIDI比較は `measure_wasm_fixed.compare_pcm` でビット差と絶対差、`measure_uniform_tube.compare_series` で観測量ごとの基準ピーク比を測る。今回の比較CLIは、すでに記録されたこの2種類の判定を同じフレームで再現する。[比較テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/common/mod.rs#L86)・[ブロックテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[手動MIDIの計測](../tools/measure_worklet_midi_pitch.py)

WAVの値と呼気ゲートは無次元、声門位相は周期、声門流量はcm³/s、放射流量の時間微分はcm³/s²。出力フレーム番号をゼロ始まりの整数 `f`、内部倍率を `m` とすると、末尾内部サンプルは `(f+1)m−1`。候補CSVに内部全件、上流CSVに末尾だけが入った場合も、この座標が同じ点を比べる。ビット差はf32の符号・仮数を含み、絶対差はf64に変換して引き算する。状態量は測定区間内の上流ピークで正規化する。ピーク0のときは全差が0なら合格する。非有限値、必須の座標の欠落、波形長・レートの不一致は比較入力エラーとして扱う。

## 実装前の登録

手動MIDIの正式実行の基準／候補WAVは48 kHzで各124,416フレーム。上流の観測は内部番号1, 3, …、候補は0, 1, …と記録されている。出力フレーム全区間を比較し、同じ4列の最大差と判定が既存の記録と一致すると予測する。上流／候補PCMのビット差は13,082点、最初はフレーム0、最大絶対差は約2.18×10⁻¹¹。候補ブラウザ／CLIのWAVは全フレームでビット一致すると予測する。マニフェストのサイズとSHA-256、選択区間内の座標、`/tmp` からの再現、欠損・異常入力の判定も確かめる。[判定条件](../cases/compare-saved-voice-run.json)・[参照結果](../runs/worklet-midi-voice-pitch-20261121-final/summary.json)

## 実装と再実行

`vocal-cli compare <基準の実行> <候補の実行> <比較ケース.json>` に接続した。「実行」はディレクトリか、そこにあるマニフェストを指定する。同じ実行の中の上流版と候補版を比較する場合は、両引数に同じ実行を指定して、ケースに別々の成果パスを書く。成果パスは実行内の相対パス。ファイルを読む際にサイズとSHA-256を検査し、外部ディスク上の実体も保存先へリンクした元のパスから読める。比較のために出力物を複製する必要はない。比較で許容差を超えた場合は判定JSONを返して終了コード1、入力エラーでは理由を標準エラーに返す。[CLIの集計](../crates/vocal-cli/src/saved_compare.rs)・[ファイルの読み出し](../crates/vocal-cli/src/saved_compare/input.rs)

波形の区間は出力フレームの半開区間。WAVのレートと総フレーム数を確認し、範囲内のf32ビットとf64で計算した絶対差を記録する。CSVは基準と候補それぞれに `internal_sample` または `frame` の座標を指定する。最初に基準を読み、区間内で各列の最大絶対値を求める。次の走査で必須の座標を基準・候補から逐次読み、最初の差と許容差を超えた最初のフレームを求める。基準ピーク0で値が分岐した場合、相対値はJSONで `null`、判定は不合格。比較器は波形を1サンプルずつ、観測値を1行ずつ処理する。範囲外のバイトもSHA-256の対象とする。

初回は全区間と一部区間を測定した後、異常入力用のファイルを準備するPythonスクリプトで `shutil` のインポートが不足して停止した。生成済みの比較JSONは保存し、同じ比較ケースでインポートを修正して再実行した。[初回の停止と成果](../runs/compare-saved-voice-20261121-a/failure.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。RustのCSV解析には `csv 1.4.0`、照合には `sha2 0.10.9` を使用し、Cargoのロックファイルに記録した。波形・CSVはRTL9210B-CG上の保存済みファイルを読み、比較結果と小さな対照データは内蔵の実行ディレクトリに出力した。

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
cargo run --locked --release -p vocal-cli -- compare \
  runs/worklet-midi-voice-pitch-20261121-final \
  runs/worklet-midi-voice-pitch-20261121-final/manifest.json \
  cases/compare-saved-voice-run.json
../../.venv/bin/python tools/measure_saved_voice_compare.py compare-saved-voice-local-1
```

## 結果

48 kHz・124,416フレームの固定上流／候補で、最初のPCMビット差は出力0フレーム、ビット差13,082点、最大絶対差は \(2.1756321726552463\times10^{-11}\) だった。既存の数値とSciPy・NumPyの独立計算と一致し、事前に指定した許容差5×10⁻⁷に収まった。候補のブラウザ／CLIの対照は全フレームでビット一致した。[全区間の比較JSON](../runs/compare-saved-voice-20261121-verified/artifacts/full.json)・[ビット一致の対照](../runs/compare-saved-voice-20261121-verified/artifacts/exact.json)

4列とも以前のピーク相対差を再現した。ゲートと声門位相に数値差はなく、最初の放射差は内部サンプル1（出力0）、声門流量の最初の差は内部サンプル5（出力2）だった。いずれも押下前。出力30,208〜30,847の640フレームではPCMがビット一致し、観測列の最大差と上流ピークは同区間を抽出した独立計算に一致した。全区間の放射ピーク519,865.95 cm³/s²は、この区間では381,469.42 cm³/s²だった。[一部区間の比較JSON](../runs/compare-saved-voice-20261121-verified/artifacts/window.json)・[手動MIDIの初期差](worklet-midi-voice-pitch.md)

作業ツリーと `/tmp` の2回で各10項目に合格し、別の実行ID・座標方式の組み合わせと区間外の同サイズ改変を加えた再検証で12項目に合格した。全区間の比較JSONは作業場所と実行ディレクトリ／マニフェストの指定方法を変えてもバイト一致した。合格した出力は上流と候補のCSVを行番号で対応させず、必須サンプルに揃えている。短い対照では欠けた観測座標、異なるWAV長、同サイズのファイル改変を拒否した。符号付きゼロの対照は数値差0・ビット差1となり、ビット一致を要求した比較では不合格になった。基準ピーク0の流量列も差が生じた出力2フレームを不合格として記録した。[最初の合格](../runs/compare-saved-voice-20261121-b/summary.json)・[正式の判定](../runs/compare-saved-voice-20261121-verified/summary.json)・[不合格JSONの対照](../runs/compare-saved-voice-20261121-verified/artifacts/zero-and-sign.json)

Rustのワークスペース試験40件と `vocal-cli` のClippyが通過した。保存済みCSV約80 MBを参照する全区間比較で、単発の `/usr/bin/time -l` は実時間0.45秒、最大RSS約2.42 MBだった。比較JSONは3,041バイト。入力のWAV・CSVは既存の外部実体を使用し、今回の29成果物は小さな検証用データを含めて32,305バイトだった。[正式実行とハッシュ](../runs/compare-saved-voice-20261121-verified/manifest.json)

この計測ではモノラルIEEE float32 WAVと、最上位に成果一覧を持つ実行記録を使った。初期の固定上流基準 `upstream-20261119-a` のケース別成果とPCM16 WAVは、後続の比較で確認した。[PCM16の読解と実測](compare-upstream-pcm16.md)
