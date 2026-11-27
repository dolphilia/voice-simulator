# 歌唱に使う合成器で予備描画を分割する

## 上流の時計と研究版の状態

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor` は、主スレッドから調音ジェスチャーを受け取ると `engine_schedule()` を呼ぶ。`Engine::schedule()` は内部の声道時計にリード時間を足した秒数を返し、各ジェスチャーの `t0`・`t1` にその秒数を加える。実時間の `process()` は出力配列長を `engine_render()` に渡す。Rust側は保持した `pos` を128フレームの境界まで進め、境界でシーケンサーを更新する。`output_does_not_depend_on_the_host_block_size()` は操作を同じ絶対フレームに置き、1・77・4,096・48,000フレームの分割で128フレームのPCMとビット一致することを確認する。[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[上流Rustエンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版では `vocal_start_score_preparation()` が、初期姿勢と音源設定から `ArticulatedVoice` と `OutputStage` を作り、調音スコアと残り出力フレーム数を同じハンドルに持つ。`vocal_advance_score_preparation()` は、声道・声門を進めて放射流量変化率（cm³/s²）を得る処理と、間引き・DC除去・リミッターを順に進める処理を最大で指定フレーム分繰り返す。内部96 kHz、出力48 kHzなので、出力16,384フレームで内部32,768サンプル進む。声道時計は制御境界で64 / 48,000秒ずつ進む。最後の片で、同じ声道時計を `t0`・`t1` に加えて譜面を予約する。歌唱出力は独立したフレーム番号0から始まる。既存の一括ABIでも同じ準備・予約処理を使う。[研究版の準備と予約](../crates/vocal-wasm/src/lib.rs#L324)・[調音更新](../crates/vocal-core/src/voice.rs#L575)・[出力段](../crates/vocal-core/src/output.rs#L76)

実時間歌唱のオプション `songScorePreparationBlock` はWorkletの1回の呼び出しで進める出力フレーム数を指定する。分割片の量子では歌唱ノードから無音を出し、完了翌量子から連続8量子と2,048フレームのリードを経て歌唱を始める。同じContextの先行信号は各量子の時刻とPCMを取り続ける。Safariでの比較は16,384フレームの一括と128フレーム×128片を対象とする。比較する最大間隔の窓は、両条件ともWorklet内の構築開始から最後の予備描画までとした。構築時間に加えて、クリックから歌唱最初の出力までの経過を保存する。[事前登録](../cases/worklet-safari-song-split-score-preparation.json)・[Worklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[実時間の予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)

## 実測

Safari 18.6で4ペアずつ、ペア内の順を反転して2回測った。各実行の100判定と2予測が成立した。全8ペアで分割すると先行信号の最大間隔が118〜135 ms短縮し、中央値は132 msだった。歌唱開始は256〜284 ms遅くなり、中央値は275.5 msだった。[初回](../runs/worklet-safari-song-split-score-preparation-20261122-a/summary.json)・[反転順](../runs/worklet-safari-song-split-score-preparation-20261122-repeat/summary.json)

| 16,384フレームの予備描画 | 構築時間 | 先行信号の最大間隔 | クリックから歌唱開始 |
| --- | ---: | ---: | ---: |
| 一括 | 132〜140 ms | 134〜141 ms | 379〜457 ms |
| 128フレームずつ | 3〜15 ms | 4〜23 ms | 658〜738 ms |

分割は8試行とも128量子にまたがり、開始から最後の片の完了まで337〜341 msだった。最大間隔は全8試行で第1片と同じContextフレームの直前にあり、第1片のフレームから最終片までを挟む間隔に限ると試行ごとの最大は3〜11 msだった。最長の23 msは、構築開始の3 ms前から20 ms後までにあり、この中に15 msの構築と第1片の開始が入った。WASMの線形メモリの拡張は全16試行で0回だった。機器出力の欠落と聴感は未測定で、計時はミリ秒精度の `Date.now()` を使用した。[初回の23 msを含む試行](../runs/worklet-safari-song-split-score-preparation-20261122-a/artifacts/pair-3-split/browser.json)・[先行信号の時刻](../runs/worklet-safari-song-split-score-preparation-20261122-a/artifacts/pair-3-split/marker.json)

全16試行で、先行信号の81,920サンプルは独立計算とビット一致した。歌唱の31,200サンプルと各488点の声門・放射などの系列は、保存済みの16,384フレームのSafari基準に一致した。Rustのテストでは、0と257フレームを入力し、128フレームで割り切れない257フレームの末尾も一括とPCMが一致した。準備途中の通常描画、0フレームや上限超過の準備片、準備完了後の重複呼び出しは拒否された。研究版WASMの全27テストと固定上流のブロック長比較も通過した。[保存基準のマニフェスト](../runs/worklet-safari-song-prepared-shared-context-20261122-repeat/manifest.json)・[研究版のテスト](../crates/vocal-wasm/src/lib.rs#L1172)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。各274入力・84出力のサイズとSHA-256を照合した。WASM・ケース・PCM・WAVの33ファイルが2実行間で一致した。2実行の採取物13,354,455バイトはRTL9210B-CGに保存した。[初回のマニフェスト](../runs/worklet-safari-song-split-score-preparation-20261122-a/manifest.json)・[反転順のマニフェスト](../runs/worklet-safari-song-split-score-preparation-20261122-repeat/manifest.json)

分割の指定を省いた従来のSafari比較も再実行した。予備描画0と16,384フレームの計8試行で80判定と2予測を満たし、273入力と84出力のハッシュを確認した。実行コマンドと追加の採取物5,617,828バイトの所在はマニフェストに記録した。[従来経路の回帰確認](../runs/worklet-safari-song-prepared-shared-context-20261122-split-regression/manifest.json)

```bash
# 研究ワークスペースで実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-split-score-preparation-20261122-a
```

```bash
# /private/tmp で実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-split-score-preparation-20261122-repeat --reverse
```

次は分割長を128と256フレームで比較する。16,384フレームを64量子で進めてもPCM・声門状態が一致することを確認し、第1片を含む区間と分割中の間隔を個別に測る。これにより、準備片を長くした場合の歌唱開始時間と先行信号への影響を比較できる。
