# Safariの歌唱予備描画で最初の2片を短くする

## 上流の負荷表示と研究版の分割

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `ChimeraProcessor.process()` は、出力チャンネル長を `engine_render()` に渡し、PCM転送後に `Date.now()` の差を取り、量子長から求めた処理予算との比を更新する。`Engine::render()` は合計出力位置 `pos` を保持し、128フレーム境界でシーケンサーを更新する。上流のブロック長試験では、操作の絶対フレームをそろえた4種類の分割を、128フレーム分割のPCMにビット照合する。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[上流の描画処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流のブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版では、`FixedVoiceEngine.advanceScorePreparation()` が16,384フレームのうち残りと今回の指定長の小さい方を採用する。Rustの `vocal_advance_score_preparation()` は同じ状態からそのフレーム数だけ声門・声道・放射・出力段を進め、残りが0になったときに譜面を予約する。最初の2量子の指定に64・64フレームを渡せるようにした。指定列が尽きた後は256フレームずつ進め、最後に残った128フレームを処理する。先行信号と歌唱を接続したContextの出力量子は各128フレームで、予備描画が終わるまでは歌唱ノードから無音を送る。256フレーム固定64片に対し、今回の条件は66片で、名目の追加時間は `2 × 128 / 48000` 秒、約5.333 msとなる。[TypeScriptの片の選択](../crates/vocal-wasm/host/fixed-voice.ts)・[Rustの予備描画](../crates/vocal-wasm/src/lib.rs#L1057)・[前回の各片の計時](worklet-safari-song-score-preparation-timing.md#実測)

第1片と第2片を短くすると、前回の過負荷が軽くなると予測した。最初の2片と最初の6片を別々に集計し、256フレームを初めて処理する第3片へピークが移る場合も残す。採取はSafariの通常歌唱画面から行い、既存の先行音と歌唱・声門の基準に照合する。すべての片をContext上のフレーム番号で対応づけ、無音を書き込むまでをミリ秒刻みの `Date.now()` で計った。2.667 msの名目予算に対し、記録値から1 msを引いても超過する片と、1 msの丸めを考慮すると判別できない片を集計する。[事前登録](../cases/worklet-safari-song-score-preparation-initial-blocks.json)・[集計処理](../tools/song_score_preparation_timing.py)

## 実測

Safari 18.6で8ペアを測った。最初の2片の最大処理時間は、同じペアで3〜4 ms短縮し、中央値は4 msだった。短い片から始めた条件では、8試行とも初めて256フレームを処理する第3片で最初の6片の最大時間に初めて達した。最初の6片での最大処理時間はペアごとに1 ms延長〜2 ms短縮し、中央値は1 ms短縮だった。先行信号で最初の6片の前後に重なる最大間隔は、ペア中央値で3 ms短くなった。[初回の要約](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-a/summary.json)・[反転順の要約](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-repeat/summary.json)

| 無音を書き込むまでの時間 | 256フレーム固定 | 最初の2片を各64フレーム |
| --- | ---: | ---: |
| 第1片 | 5〜6 ms | 2 ms |
| 第2片 | 3〜4 ms | 1〜2 ms |
| 第3片 | 2〜3 ms | 4〜6 ms |
| 第4片 | 2〜3 ms | 3〜4 ms |
| 第5〜6片 | 2〜3 ms | 2〜3 ms |
| 第7片以降の最大 | 3 ms | 3 ms |

丸めを考慮しても2.667 msを超えたのは、固定条件では第1片の8件と第2片の7件、最初の2片を短くした条件では第3片の8件と第4片の4件だった。第7片以降では両条件とも4 ms以上の記録がなかった。2〜3 msの記録では時計の精度から超過を確定できない。先行信号と歌唱の計時はWeb Audioグラフ内で、出力機器でのサンプル欠落は未測定。[第3・4片が4 msだった試行](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-a/artifacts/pair-4-initial-64-64/preparation-blocks.csv)

短い片から始めると、16,384フレームの準備に使うContext量子が2個増えた。最後の片から歌唱開始までは全16試行で3,200 Contextフレームだった。クリックから歌唱開始までの壁時計の差は、ペアごとに14 ms短縮〜13 ms延長し、中央値で1.5 ms延びた。先行信号各81,920サンプルは独立計算の連番付きPCMとビット一致し、歌唱各31,200サンプルと各488観測点・調音計画も保存基準と一致した。両条件合わせて1,040片をCSVと生の観測JSONで再照合した。[計時と観測の基準](../runs/worklet-safari-song-score-preparation-timing-20261122-repeat/manifest.json)・[反転順の実行記録](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-repeat/manifest.json)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースと `/private/tmp` から実行し、各120判定と3予測が成立した。各276入力・92出力のサイズとSHA-256を照合し、WASM・ケース・PCM・WAVなど33ファイルが再実行と一致した。採取物13,676,553バイトはRTL9210B-CGに保存した。[初回のマニフェスト](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-a/manifest.json)・[反転順のマニフェスト](../runs/worklet-safari-song-score-preparation-initial-blocks-20261122-repeat/manifest.json)

従来の128・256フレーム分割の計時は120判定と6予測を満たし、上流のブロック長試験も通過した。Bunで同じ研究版WASMを呼ぶ対照では、予備描画0・1・65・129・385フレームについて片の長さと残りの片数を確認し、一括に対して各10,240点のPCMと観測状態が一致した。範囲外の片長0、−1、1.5、4,097は初期化時に拒否された。[従来条件の回帰](../runs/worklet-safari-song-score-preparation-timing-20261122-initial-regression/manifest.json)

```bash
# 研究ワークスペース
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-initial-blocks-20261122-a --compare-initial-blocks
```

```bash
# /private/tmp
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_worklet_safari_song_split_score_preparation.py \
  worklet-safari-song-score-preparation-initial-blocks-20261122-repeat --compare-initial-blocks --reverse
```

次は最初の256フレームを64フレーム4片か128フレーム2片で処理した後に256フレームへ切り替える。切り替え時点で準備したサンプル数をそろえ、呼び出し回数の違いが最初の256フレーム片に表れるかを測る。
