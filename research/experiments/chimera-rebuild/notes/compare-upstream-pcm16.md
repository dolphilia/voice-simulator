# 初期の固定上流のPCM16成果を比較する

## 固定上流の読解

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のCLIは、`run` が `render vowels` を `render::vowels` へ振り分ける。成人男性はF0 110 Hzで、母音10個を各0.6秒、48 kHzで合成し、各母音の終わり0.12秒は呼気目標0にする。内部は96 kHz。母音の調音姿勢は較正表から取り、1本のモノラル波形へ続けて出力する。`Ctx::write_wav` を通じて `wav::write` にf32の無次元振幅を渡す。既定の書き出しは有限値を±1で制限し、\(q=\operatorname{floor}(32767\,x+0.5)\) をリトルエンディアンの符号付き16ビットとして保存する。`--float` は同じ合成波形をf32で保存する。[CLIの分岐](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[母音レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L827)・[WAVの出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/wav.rs)

上流のTSP・CSD比較が使う `compare.rs::read_wav` はRIFFのチャンクを走査し、PCM16なら読み取った整数を32,768で割る。16ビット符号付きの範囲は−32,768〜32,767なので、無次元振幅の範囲は−1から \(1-1/32768\)。読み出しの分母と書き出しの倍率は1だけ異なる。このため制限にかからない元の値 \(x\) と読み出した値との差の上限は \((0.5+|x|)/32768\)。`tests/cli.rs::render_speech_writes_a_sounding_wav_of_the_planned_length` は既定の出力の形式タグ、ビット幅、チャンネル数、フレーム数と有音を検査する。`math::tests::js_round_halves_up` は半整数の丸めを照合する。これらを根拠に、元のfloat32、PCM16への丸め、読み出した値の三段を切り分ける。[上流の読み出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L330)・[CLIテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/tests/cli.rs#L29)・[丸めの検査](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L284)

研究ワークスペースの `tools/upstream_baseline.py` が作った初期マニフェストでは、同じ実行に一様管テスト、母音、発話、旋律が入る。各ケースに `id`・`status`・`outputs` があり、実行の最上位には成果一覧がない。比較の基準は母音ケースの `artifacts/vowels.wav`。48 kHzの288,000フレームを保存し、SHA-256はマニフェストと一致した。保存済み比較ではこの来歴を残しつつ、全バイトのハッシュとサイズを確認する。[初期の取得処理](../tools/upstream_baseline.py)・[初期のマニフェスト](../runs/upstream-20261119-a/manifest.json)

## 事前登録

保存済みPCM16を自分自身と比べると差0、独立に \(q/32768\) を計算して保存したfloat32と比べても振幅差0を予測した。異形式の生ビットは比較値を欠測とし、同一形式では既存のビット判定を使う。固定上流をPCM16とfloat32で再レンダーし、保存した整数が独立計算と一致するかと、量子化前後の最大差が理論上限内かを確かめる。境界の整数−32,768・−1・0・1・32,767、異形式にビット一致を求めた入力、成果パスの重複も小さな対照で調べる。[ケース定義](../cases/compare-upstream-pcm16.json)

## 実装と再実行

`vocal-cli compare` が、最上位の `outputs` に加え、`cases[].outputs` を実行の基準ディレクトリに対する相対パスで読むようにした。報告には成果のケースIDと保存時の状態を含める。成果パスが複数の場所に登録されている場合は曖昧な入力として処理する。元の記録とサイズ・SHA-256はそのまま保った。

WAVの形式タグ、ビット幅、チャンネル数、レート、フレームのバイト数を読んでから、各サンプルを逐次処理する。PCM16の整数は32,768で割っても全値をf32で正確に表せる。同一形式ならビット差と絶対差を同じ区間で測る。異形式では数値の最初の差と最大差を出し、元のビット列の比較値はJSONの `null` とする。異形式に対する `require_pcm_bit_exact` は入力エラー。初回のビルドではWAV形式タグを読み取る配列の型推論がエラー `E0282` で止まった。タグとビット幅をそれぞれリトルエンディアンの `u16` として読む形に直した。[実装](../crates/vocal-cli/src/saved_compare/input.rs)・[比較結果の構造](../crates/vocal-cli/src/saved_compare.rs)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実施した。旧基準のPCM16を参照し、Pythonの標準ライブラリで独立に読み、NumPyで振幅へ換算した。固定上流の同じ入口で両形式を再出力し、元の成果は変更しなかった。再取得と対照の作業先はUUIDを確認したRTL9210B-CGで、出力と一時領域を64 MiBと見積もった。

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
cargo run --locked --release -p vocal-cli -- compare \
  runs/upstream-20261119-a runs/upstream-20261119-a cases/compare-upstream-pcm16.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=67108864 \
  ../../.venv/bin/python tools/measure_saved_pcm16_compare.py compare-upstream-pcm16-local-1
```

## 結果

初期実行のケースIDは `vowels`、保存時の状態は `pass`、形式はモノラルPCM16として取得できた。48 kHzの288,000フレームは、自分自身との比較でも、固定上流をPCM16で再レンダーした比較でもビット差0だった。再レンダーしたWAVのSHA-256は初期実行と一致。保存PCM16の整数を32,768で割って作ったfloat32対照とは振幅差0で、−32,768と32,767を含む小さな境界対照でも一致した。旧実行とWAVのハッシュに変化はなかった。[初期のWAVの自己比較](../runs/compare-upstream-pcm16-20261121-final/artifacts/archive-self.json)・[PCM16の再レンダー比較](../runs/compare-upstream-pcm16-20261121-final/artifacts/archive-vs-rerendered.json)・[独立した振幅の換算](../runs/compare-upstream-pcm16-20261121-final/artifacts/archive-vs-decoded.json)

量子化前の固定上流float32から丸め式でPCM16を再計算し、保存済みの全整数と一致した。浮動小数点の保存波形とPCM16を読み戻した値の最初の差はフレーム0。最大差はフレーム76,668の \(2.4378299713134766\times10^{-5}\) だった。そこでの元の値は−0.29909664392471313、PCM16は−9,800、読み戻した値は−0.299072265625。全点で \((0.5+|x|)/32768\) の上限内で、読み出しや再レンダーの差として残る値は観測されなかった。[量子化前との比較](../runs/compare-upstream-pcm16-20261121-final/artifacts/archive-vs-raw-float.json)・[式とフレームの集計](../runs/compare-upstream-pcm16-20261121-final/summary.json)

作業ツリーと `/tmp` の各11項目、既存のfloat32・時系列比較の回帰12項目、Rustワークスペース試験40件、`vocal-cli` のClippy、固定上流のWAV出力テストが通過した。異形式にビット一致を要求した入力と、ケース別成果のパスを重複させた入力は終了コード1で拒否した。同じ実行をディレクトリ／マニフェストの指定で入れ替えてもJSONは同じバイト列だった。正式実行の26成果は合計約2.91 MBで全ハッシュを照合した。RTL9210B-CGの再レンダーを元の実行パスのリンクから比較した場合も、採取時のJSONと一致した。[正式実行の記録](../runs/compare-upstream-pcm16-20261121-final/manifest.json)・[固定上流のテスト](../runs/compare-upstream-pcm16-20261121-final/artifacts/upstream-wav-test.log)・[既存のfloat32回帰](../runs/compare-upstream-pcm16-20261121-float-regression/summary.json)

比較CLIは研究用のモノラルPCM16とIEEE float32で検証した。PCM24・PCM32整数、複数チャンネルの混合は今回の検証範囲に含めていない。
