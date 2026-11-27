# Safariで歌唱の予備描画を128・256フレームで分割する

## 出力量子と合成器を進める量

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor.process()` は、Contextが渡した出力配列の長さを `engine_render()` に渡し、PCMを配列にコピーする。Rustの `Engine::render()` は `pos` を保持し、128フレームの境界ごとにシーケンサーを更新する。上流の `output_does_not_depend_on_the_host_block_size()` は、操作の絶対フレームを保てば1、77、4,096、48,000フレームの各分割で128フレームとPCMがビット一致することを確認する。[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[上流レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の実時間歌唱では、構築後の最初の `FixedProcessor.process()` から `advanceScorePreparation()` を量子ごとに呼ぶ。WASMの `vocal_advance_score_preparation()` は残りフレームと指定長の小さい方を使い、同じ声門・声道・放射・出力段を進める。最後の片で内部の制御時計に譜面を載せ、その次のContext量子から歌唱予約用の連続量子を数える。予備描画中にContextへ出す配列は128フレームの無音で、合成器内の計算はこの間に256フレームまで進められる。ブラウザ側の条件をWASMの既存上限4,096フレームに合わせ、歌唱の音源設定が必要な条件は維持した。[Workletの準備](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L152)・[WASMの入力条件](../crates/vocal-wasm/src/lib.rs#L362)・[前回の一括比較](worklet-safari-song-split-score-preparation.md)

総量16,384フレームでは、128フレームずつの準備を128量子、256フレームずつの準備を64量子で終える。48 kHzで1量子は `128 / 48,000` 秒なので、差は約170.67 msになる。クリックから最初の歌唱出力も短くなると予測した。先行信号の時刻は、量子を `Q=128`、第1片のContextフレームを `F` として、`F−Q` から `F`、`F` から `F+Q`、第2片以降の間隔の最大を別々に集計した。構築開始から予備描画完了までを含む全体の最大も記録した。既知の先行信号と歌唱のPCM、声門・放射などの状態、調音計画を同時に照合する。[事前登録](../cases/worklet-safari-song-score-preparation-block-size.json)・[採取と照合](../tools/measure_worklet_safari_song_split_score_preparation.py)

## 実測

Safari 18.6で4ペアずつ、順序を反転して2回測った。256フレーム分割は全8ペアで歌唱開始を147〜216 ms短縮し、中央値は167.5 ms。分割準備の開始から終了までは165〜169 ms短縮し、中央値167 msで名目差170.67 msから3.67 ms以内だった。クリックから第1片までのペア差は−21〜48 ms、最後の片から歌唱出力までのペア差は0〜2 msだった。両条件とも最後の片のContextフレームから3,200フレーム後に歌唱を開始した。[初回の要約](../runs/worklet-safari-song-score-preparation-block-size-20261122-a/summary.json)・[反転順の要約](../runs/worklet-safari-song-score-preparation-block-size-20261122-repeat/summary.json)

| 計測項目 | 128フレームずつ | 256フレームずつ |
| --- | ---: | ---: |
| 分割準備の回数 | 128 | 64 |
| クリックから歌唱開始 | 663〜731 ms | 499〜524 ms |
| 構築開始から準備完了までの先行信号の最大間隔 | 4〜19 ms | 6〜11 ms |
| 第1片と同じフレームの直前の間隔 | 4〜19 ms | 4〜11 ms |
| 第1片と同じフレームの直後の間隔 | 2〜7 ms | 4〜7 ms |
| 第2片から最終片の間での最大間隔 | 3〜8 ms | 3〜6 ms |

第2片以降の最大間隔は同じペアで−5〜3 ms変わり、増加の中央値は1 msだった。計測窓全体で最長だった間隔は、128フレーム分割の8試行で第1片のフレームの直前、256フレーム分割では直前と直後が各4試行だった。これらの時刻は先行信号用Workletが描画を開始した時刻で、歌唱準備の処理時間や出力機器での連続性は個別に測る必要がある。[先行信号と歌唱の採取データ](../runs/worklet-safari-song-score-preparation-block-size-20261122-repeat/manifest.json)

全16試行で先行信号各81,920サンプルは独立計算とビット一致した。歌唱各31,200サンプルと488観測点・調音計画は、保存済みの128フレーム分割と一致した。WASMの線形メモリの拡張は0回だった。結果を保存済みの一括比較・CLIにたどることができ、元の比較では固定上流との残差も記録した。[参照した128フレーム分割](../runs/worklet-safari-song-split-score-preparation-20261122-repeat/manifest.json)・[通常の歌唱での固定上流との照合](worklet-song-prepared-source.md)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。各104判定と3予測を満たし、各275入力・84出力のサイズ・SHA-256を照合した。2実行で、WASM・歌唱ケース・PCM・WAVなど33ファイルのハッシュが一致した。採取物13,356,461バイトをRTL9210B-CGに保存した。[初回のマニフェスト](../runs/worklet-safari-song-score-preparation-block-size-20261122-a/manifest.json)・[反転順のマニフェスト](../runs/worklet-safari-song-score-preparation-block-size-20261122-repeat/manifest.json)

従来の一括と128フレーム分割の回帰実行も100判定と2予測を通過した。274入力と84出力をハッシュで照合し、採取物6,676,922バイトを作業用ディスクに保存した。研究版の端数片を含むWASMの単体試験と、固定上流のブロック長に依存しないことを確認する試験も再実行した。[従来条件の回帰実行](../runs/worklet-safari-song-split-score-preparation-20261122-block-size-regression/manifest.json)

```bash
# 研究ワークスペース
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-block-size-20261122-a --compare-block-sizes
```

```bash
# /private/tmp
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-block-size-20261122-repeat --compare-block-sizes --reverse
```

次は歌唱Worklet内で各準備片の開始・終了を記録し、48 kHz・128フレームの2.667 ms予算に対して128と256フレームの各片に残る時間を測る。第1片と後続片の計時を分け、先行信号の各間隔にContextフレームで対応づける。
