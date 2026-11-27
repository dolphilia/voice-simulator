# Safariの歌唱構築中に先行信号が進むか

## 構築と先行信号の観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の歌唱Workletは、`engine_schedule()` でエンジン時計に譜面を置き、`process()` で `engine_render()` のPCMを出力する。研究版では歌唱のWorklet構築中に `vocal_start_score_prepared()` が、予備描画の分だけ声門・声道・出力段を進めた状態を作る。その後で最初の歌唱出力を予約する。48 kHz出力の128フレームは約2.667 msだが、予備描画の計算はまとめて合成器の構築中に進む。この計算を実行中に同じContextの別の枝を描画できるかを調べた。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[研究版WASMの準備](../crates/vocal-wasm/src/lib.rs#L270)・[前回の構築時間](worklet-safari-song-prepared-pause.md#実測)

Safariの採取器に、既存の先行信号の観測ノードを接続した。先行信号は `AudioBufferSourceNode` から観測用Workletへ渡し、その出力を歌唱と同じContextの出力ノードにつなぐ。開始位置から数えたサンプル番号を `i` として、振幅を `((421 × i + 173) mod 65521 − 32760) / 524288` とした。歌唱のWorkletを構築する前に先行信号を48量子採取する。観測用WorkletにはPCM、各量子の `currentFrame`、入力長と、コールバック開始時の `Date.now()` を保存する選択肢を追加した。Safariで `addModule()` の計測用差し替えが利用できるよう、AudioWorkletのラッパーをContextの存続中に保持する。[先行信号の接続](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)・[先行信号の観測点](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)・[Safariの採取](../../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs)

合成器構築の開始・終了と先行信号の描画開始は、Worklet内で同じエポック時計を参照する。分析では、構築区間と重なる先行信号の隣接コールバック間隔から最大値を取り、構築前の24間隔と比較する。先行信号のサンプル列はNumPyで別に生成する。Safariの歌唱PCM・声門観測・スコアは、同じ予備描画量の保存済みSafari基準に照合する。比較位置は出力機器の前のWeb Audioグラフ内部である。[事前登録](../cases/worklet-safari-song-prepared-shared-context.json)・[解析器](../tools/measure_worklet_safari_song_prepared_shared_context.py)・[以前のFirefoxでの先行信号比較](worklet-live-song-shared-context.md)

## 初回の結果保存

初回は全8試行のWAV、時刻、先行信号を保存したが、一部の判定をNumPyの真偽値のまま要約に渡したためJSONの保存で失敗した。判定器でPythonの真偽値へ変換し、初回の8試行を保存ファイルから読み直してから再採取した。[初回の保存エラーと成果一覧](../runs/worklet-safari-song-prepared-shared-context-20261122-a/manifest.json)

## 比較結果

48 kHzのSafari 18.6で、0と16,384フレームを4ペアずつ、ペア内の順序を反転して2回測った。構築前のコールバック間隔の中央値は全試行で3 msだった。構築に重なる最大間隔のペア内増加は8ペアで130〜153 ms、中央値132.5 msだった。予備描画ありの8試行すべてで、構築の開始から終了までが先行信号の1つのコールバック間隔に収まった。[比較1](../runs/worklet-safari-song-prepared-shared-context-20261122-b/summary.json)・[順序反転](../runs/worklet-safari-song-prepared-shared-context-20261122-repeat/summary.json)

| 予備描画 | Worklet内での構築時間 | 構築と重なる先行信号の最大コールバック間隔 |
| ---: | ---: | ---: |
| 0フレーム | 3〜5 ms | 4〜6 ms |
| 16,384フレーム | 132〜157 ms | 134〜159 ms |

最大間隔を挟む `currentFrame` の差は全16試行で128フレームだった。全試行で先行信号のPCM各51,200サンプルは独立計算とビット一致し、歌唱PCM各31,200サンプルと声門などの488観測点も同じ予備描画量のSafari基準に一致した。観測点はWeb Audioグラフ内で、出力機器での欠落や聴感は未測定。エポック時計はミリ秒精度で、構築時間にはWASMインスタンスの生成と合成器の初期化を含む。[取得と判定](../tools/measure_worklet_safari_song_prepared_shared_context.py)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6の同梱WebDriver、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。修正後の1回目の作業ディレクトリは研究ワークスペース、順序反転時は `/private/tmp` とした。両実行とも80件の取得判定と2件の事前予測を満たした。各273入力と84出力のサイズ・SHA-256を再照合し、WASM・ケース・PCM・WAVの25ファイルが2実行間で一致した。採取物はRTL9210B-CGに合格2実行で11,232,071バイト、初回を含めて16,847,950バイト保存した。要約とソーススナップショットはローカルの実行ディレクトリに保存した。[比較1のマニフェスト](../runs/worklet-safari-song-prepared-shared-context-20261122-b/manifest.json)・[順序反転のマニフェスト](../runs/worklet-safari-song-prepared-shared-context-20261122-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_prepared_shared_context.py \
  worklet-safari-song-prepared-shared-context-20261122-b
```

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  /Users/dolphilia/github/voice-simulator/research/.venv/bin/python \
  /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild/tools/measure_worklet_safari_song_prepared_shared_context.py \
  worklet-safari-song-prepared-shared-context-20261122-repeat --reverse
```

次は16,384フレームの予備描画を同じ合成器に保持したまま量子ごとに分割する。分割前後で先行信号の最大間隔、歌唱開始までの時間、歌唱PCMと声門の観測値を照合する。既存の予備計算分割は一時的な試行用の合成器を使うため、歌唱に使う合成器を保ち続ける条件を別に登録する。[既存の分割準備](worklet-live-song-split-preparation.md)
