# Safariの歌唱で予備描画片ごとの処理時間を測る

## 上流の負荷表示と今回の計時

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor.process()` は、`engine_render()` の呼び出し前から、先頭チャンネルへのPCM転送と各チャンネルへのコピーが済むまでを `Date.now()` で計る。出力配列長を `N`、サンプルレートを `f_s` として、1量子の予算を `1000 × N / f_s` msと置く。負荷を測定時間と予算の比で表し、1量子ごとに係数0.05で平滑化する。上流Rustの `Engine::render()` は声の現在位置を持ち、128フレーム境界で拍の予定を更新する。ブロック長比較では同じフレームに操作を置いた4通りの分割を128フレームのPCMへビット照合する。[上流Workletの負荷表示](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[上流Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `FixedProcessor.process()` では、`advanceScorePreparation()` で声門・声道・放射・出力段を指定フレーム分進める。最後の片では同じ声道時計へ譜面を置く。その量子は無音を返し、次の量子から歌唱開始に必要な連続量子を数える。前回は準備全体の時刻を保存した。今回は `songScorePreparationTiming` を付け、各片についてContextフレーム、量子長、予備描画フレーム数、コールバック開始、WASMを呼ぶ `advanceScorePreparation()` の前後、出力配列への無音の書き込み直後を配列へ記録した。記録領域は構築時に確保し、結果は歌唱完了時にまとめて渡す。無音の書き込み後に記録した値の保存処理は時間差に含まれない。[前回の分割長比較](worklet-safari-song-score-preparation-block-size.md)・[Workletの計時](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[WASMの準備](../crates/vocal-wasm/src/lib.rs#L1057)

Safari 18.6のWorkletでは、先行信号と歌唱の両方がミリ秒単位の `Date.now()` を使用した。予算は48 kHz・128フレームで約2.667 ms。記録された差を `d` msとして、生の超過件数と、両端の時刻の丸めにより `max(0, d−1)`〜`d+1` msの範囲をとると仮定した判定を保存する。このモデルでは0・1 msの記録は予算内、4 ms以上は予算超過、2・3 msは境界を判別できない。前後の先行信号の時刻は同じContextフレームとその±128フレームから照合した。これはWorklet上の時刻の比較で、機器への転送や機器側の締切は別に観測する必要がある。[事前登録](../cases/worklet-safari-song-score-preparation-timing.json)・[分布と時計の判定](../tools/song_score_preparation_timing.py)

## 実測

Safari 18.6で4ペアずつ、ペア内の順序を反転して2回測った。両実行で各120判定と6予測が成立し、計1,536片の時刻を先行信号に対応づけた。256フレーム分割では、後続片のWASM呼び出しの平均がペア中央値で約0.95 ms増え、歌唱開始はペア中央値で169.5 ms早まった。全16試行で先行信号各81,920サンプルは独立計算と、歌唱各31,200サンプル・488観測点は保存基準と一致した。[初回](../runs/worklet-safari-song-score-preparation-timing-20261122-a/summary.json)・[反転順](../runs/worklet-safari-song-score-preparation-timing-20261122-repeat/summary.json)

| 分割長と範囲 | 片の数 | 無音出力までの中央値 / p95 / p99 | 実測値が予算超過 | 1 ms差し引いても超過 | 丸めで未確定 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 128フレーム・第1片 | 8 | 4 / 5 / 5 ms | 8 | 6 | 2 |
| 128フレーム・後続 | 1,016 | 1 / 2 / 2 ms | 5 | 0 | 72 |
| 256フレーム・第1片 | 8 | 6.5 / 7.65 / 7.93 ms | 8 | 8 | 0 |
| 256フレーム・後続 | 504 | 2 / 3 / 4 ms | 27 | 8 | 436 |

第1片を無音出力まで計ると、128フレーム分割は3〜5 ms、256フレーム分割は5〜8 msだった。256フレーム分割で後続片の下限が予算を超えた8件は、各試行の第2片に集中した。第2片は4〜5 msで、直前の先行信号の間隔は4〜8 ms、直後は3〜4 msだった。第3片以降の最大記録は両条件とも3 msで、名目予算を上回った記録は128フレーム条件で3/1,008片、256フレーム条件で19/496片。1 msの丸めを考慮するとこれらの超過は判別できない。第1片の前後に合成と先行信号のコールバックが実行される順番は、同じミリ秒に入った試行が多く、時刻だけでは区別できない。[第1・2片が8・4 msだった試行の突合](../runs/worklet-safari-song-score-preparation-timing-20261122-a/artifacts/pair-2-split-256/preparation-blocks.csv)・[反転順の突合例](../runs/worklet-safari-song-score-preparation-timing-20261122-repeat/artifacts/pair-1-split-256/preparation-blocks.csv)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使った。研究ワークスペースと `/private/tmp` から実行し、各276入力・92出力のサイズとSHA-256を照合した。WASM・ケース・PCM・WAVなど33ファイルが再実行と一致し、計時のCSVとWAVを含む採取物13,823,579バイトをRTL9210B-CGに保存した。CSVから各区間を独立に引き直し、時刻、フレーム番号、先行信号の対応を全片で確認した。[初回のマニフェスト](../runs/worklet-safari-song-score-preparation-timing-20261122-a/manifest.json)・[反転順のマニフェスト](../runs/worklet-safari-song-score-preparation-timing-20261122-repeat/manifest.json)

片ごとの計時を省いた従来の分割長比較も104判定と3予測を通過し、観測JSONに片ごとの計時列が含まれないことを確認した。276入力・84出力のハッシュを照合し、採取物6,678,351バイトを作業用ディスクに保存した。固定上流の `engine` の6テストと研究版WASMの端数片のテストを通過した。[従来条件の回帰実行](../runs/worklet-safari-song-score-preparation-block-size-20261122-timing-regression/manifest.json)

```bash
# 研究ワークスペース
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-timing-20261122-a --measure-block-times
```

```bash
# /private/tmp
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-timing-20261122-repeat --measure-block-times --reverse
```

次は256フレーム固定の対照に対し、最初の2片を各64フレーム、後続を256フレームにする。総量16,384フレームは維持され、最後の片が128フレームになる。負荷のピークが第3片以降へ移る可能性も含めて最初の6片と先行信号の時刻を比較し、歌唱開始時間とPCMを照合する。
