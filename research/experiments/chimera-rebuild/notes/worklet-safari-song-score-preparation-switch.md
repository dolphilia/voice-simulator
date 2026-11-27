# Safariで歌唱の予備描画を同じ位置から256フレームへ切り替える

## 比較した状態と計時点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor.process()` は、その呼び出しで出力するフレーム数をRustへ渡し、PCMをコピーした後に128フレーム相当の時間予算との比を更新する。`Engine::render()` は呼び出しをまたいでフレーム位置を保持し、その位置が128フレーム境界に達するごとにシーケンサーを更新する。上流のブロック長試験は、操作を同じ絶対フレームに置き、呼び出し長を変えてもPCMが一致することを確認する。[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[上流レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `FixedVoiceEngine.advanceScorePreparation()` は各量子で指定されたフレーム数を `vocal_advance_score_preparation()` へ渡す。Rustは声門・声道と出力段を同じハンドル上で進める。48 kHz出力・96 kHz内部レートで予備描画256フレームは512内部サンプルに相当し、両条件で同じ4回の調音制御更新を経てから256フレーム片へ切り替える。切り替え前の描画を2片か4片に分けるため、その時点のContextフレームは最初の準備量子からそれぞれ256、512フレーム進んでいる。累積描画量をそろえ、呼び出し回数と量子の経過時間を一緒に変える比較である。[TypeScriptの片の選択](../crates/vocal-wasm/host/fixed-voice.ts#L390)・[Rustの予備描画](../crates/vocal-wasm/src/lib.rs#L1057)・[前回の第3片でのピーク](worklet-safari-song-score-preparation-initial-blocks.md#実測)

累積256フレームの直後の最初の256フレーム片と、その後の2片を検査する。各片ではWASM呼び出しと無音出力までの時間、同じContextフレームの先行信号の前後の間隔を採る。先行音は独立計算、歌唱は保存済みの256フレーム基準と照合する。`Date.now()` は1 ms刻みで、2.667 msの量子予算に対して2・3 msを記録した片では超過を区別できない。4 ms以上の記録は1 msを引いても予算を超える。[事前登録](../cases/worklet-safari-song-score-preparation-switch.json)・[切り替えの検出と計時](../tools/song_score_preparation_timing.py)

## 実測

Safari 18.6で順序を反転した2実行、計8ペアを測った。最初の256フレーム片は128フレーム2片の条件で7試行が4 ms、1試行が3 ms。64フレーム4片の条件では全8試行で3 msだった。ペアでの記録値の差は0〜1 msの短縮、中央値は1 ms。丸めを考慮しても予算を超えた記録は7件から0件になった。64フレーム4片で切り替えた最初の片は全件が3 msのため、予算内に収まったかは判別できない。[初回](../runs/worklet-safari-song-score-preparation-switch-20261122-a/summary.json)・[反転順](../runs/worklet-safari-song-score-preparation-switch-20261122-repeat/summary.json)

| 無音出力までの処理時間など | 128フレーム×2 | 64フレーム×4 |
| --- | ---: | ---: |
| 切り替え前の最大時間 | 3〜4 ms | 1〜2 ms |
| 最初の256フレーム片 | 3〜4 ms | 3 ms |
| 2番目の256フレーム片 | 2〜3 ms | 2〜3 ms |
| 3番目の256フレーム片 | 2 ms | 2 ms |
| 最初の256フレーム片の前後での先行信号の最大間隔 | 3〜5 ms | 3〜5 ms |

第2片以降の256フレーム片は両条件とも2.667 msを超えたと確定できる記録がなかった。最初の256フレーム片の前後での先行信号の最大間隔は同じペアで1 ms短縮〜1 ms延長し、中央値は0.5 ms短縮。64フレーム4片で歌唱開始に使う量子は2個増え、録った壁時計では、クリックから歌唱開始までの差が2 ms短縮〜9 ms延長、中央値で3 ms延長だった。1 ms刻みの記録からは、呼び出し回数と経過した量子数のどちらが切り替え後の差に関係したかは分からない。計測点はWeb Audioグラフ内で、出力機器の欠落は未測定。[128フレーム×2の時系列例](../runs/worklet-safari-song-score-preparation-switch-20261122-a/artifacts/pair-1-initial-128x2/preparation-blocks.csv)・[64フレーム×4の時系列例](../runs/worklet-safari-song-score-preparation-switch-20261122-a/artifacts/pair-1-initial-64x4/preparation-blocks.csv)

全16試行で先行信号の各81,920サンプルは独立計算とビット一致し、歌唱各31,200サンプル、各488観測点と調音計画は保存基準に一致した。両条件で計1,056片を生の観測JSONと突合CSVで再照合した。Bunで同じ譜面を使い、予備描画を切り替え位置の256フレームで止めて歌唱へ進む対照も行った。一括・128フレーム2片・64フレーム4片のPCM31,200点と観測488点が一致し、切り替え位置での音響状態が後続描画で一致することを確かめた。[保存基準のマニフェスト](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-repeat/manifest.json)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースと `/private/tmp` から実行し、各128判定と4予測が成立した。各276入力・92出力のサイズとSHA-256を照合し、WASM・ケース・PCM・WAVなど33ファイルが再実行と一致した。採取物13,681,615バイトはRTL9210B-CGに保存した。[初回のマニフェスト](../runs/worklet-safari-song-score-preparation-switch-20261122-a/manifest.json)・[反転順のマニフェスト](../runs/worklet-safari-song-score-preparation-switch-20261122-repeat/manifest.json)

256フレーム固定と最初の2片だけ64フレームにする従来の比較を再実行し、120判定と3予測を照合した。上流の `cargo test --locked -p chimera --test engine output_does_not_depend_on_the_host_block_size` も通過した。回帰実行の276入力・92出力をハッシュで照合し、採取物6,837,982バイトを作業用ディスクに保存した。[従来条件の回帰](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-switch-regression/manifest.json)

```bash
# 研究ワークスペース
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-switch-20261122-a --compare-switch
```

```bash
# /private/tmp
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-switch-20261122-repeat --compare-switch --reverse
```

グラフの外側で欠落を観測するため、次は既知のステレオ信号だけをSafariから再生し、既存のCore Audioのプロセスタップが対象プロセスとPCMを正しく取得できるかを較正する。歌唱の負荷条件は較正を通った取得経路に接続する。[既存の出力PCM検証と採取結果](worklet-live-song-output-pcm.md)
