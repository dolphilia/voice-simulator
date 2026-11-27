# Chromiumの無音先行で入力が見えなかった量子を調べる

前回のFirefox対応後、Chromiumの16試行中12件で、無音先行の最初の有効入力から準備通知までに有効入力が観測されない256フレームがあった。歌唱ノードの開始待ちは全試行で連続した。今回は歌唱画面の `songSilentLead=4` または `songSilentLead=8` に `songSilentLeadTrace=1` を加え、先行枝のコールバックと入力を同じ絶対フレームで記録する。[前回の比較](worklet-live-song-fast-app-silent-lead-firefox.md#実測)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead-input-trace.json)

## 上流と今回の観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` はContextを再開し、初回は `build()` で合成Workletを登録してからノードを作る。`playTune()` は音節、MIDI番号、拍数、テンポからジェスチャーを計画する。拍の長さは `60 / bpm` 秒。Workletへ送る計画は相対秒で、`Engine::schedule()` が `voice.clock + lead` を各ジェスチャーの両端に加える。Workletの `process()` はフレーム数をWASMへ渡し、そのPCMを出力にコピーする。Rustの `Engine::render()` は `pos % SUB_BLOCK` で内部ブロックの位相を保持する。`fast_runs_land_on_the_beat()` は短音における母音と拍の一致、`output_does_not_depend_on_the_host_block_size()` は描画要求の分割によらないPCMの一致を検査する。無音先行は候補側で実験している起動経路で、音声は同じ短音の固定上流の保存PCMへ照合する。[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補の `SongSilentLeadProcessor.process()` は、128フレームの出力と同じ長さの入力がすべて0であれば有効と数える。形状または値が異なるか、絶対フレームが128ずつ進まなければ連続区間を数え直す。指定した4または8量子分が連続した呼び出しで準備を通知し、歌唱ノードを接続する。歌唱側は独立に連続8量子を数え、2,048フレームを加えた位置で描画を始める。今回の観測は先行Worklet内で入力を数える前に、フレーム番号、出力長、入力チャンネル数、先頭チャンネル長、非ゼロ値の有無の5列を保存する。128件分の配列をあらかじめ確保し、通知と一緒に返す。上限を超えた件数も返し、上限を超えた場合は完全な時系列として扱わない。[先行Worklet](../../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts)・[歌唱側の時計](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)

先行枝の最初の有効入力のフレームを `F`、通知する量子の末尾を `R`、有効と数えた量子数を `K` とする。これまでの差は `R − F − 128K`。今回の独立計算では、`F` から `R − 128` までを128刻みで並べ、時系列の記録がない境界と、記録はあるが有効条件に合わない境界を別々に数える。その合計に128を掛けて前回方式の差と照合する。さらに、有効な記録だけから初めて4または8量子が連続した区間を求め、準備通知の位置と照合する。最初の有効入力より前に走ったコールバックは別に数える。これにより、対象となるコンテキスト時刻の `process()` 記録の欠落と、呼び出された上での入力不成立を調べる。機器への出力時刻は別の時計となる。[照合コード](../tools/measure_worklet_live_song_app_silent_lead.py)

## 実測

2回で32試行を取得し、初回11件、再実行12件の計23件で256フレームの欠測があった。23件すべてで、先行Workletの最初の有効な呼び出しを `F` とすると `F + 128` と `F + 256` に記録がなく、`F + 384` から連続した。直接出力では16試行中12件、並列観測では16試行中11件でこの欠測が出た。記録された215件はすべて128フレームの出力と単チャンネル128フレームの0入力を持っていた。最初の有効入力より前の記録、入力不成立、採取上限超過は0件。どの有効入力から数え直したかも時系列から復元できた。[初回の結果](../runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-repeat/summary.json)

初回の直接出力・8量子の一例では、先行Workletの最初の記録は2,048、次は2,432だった。2,176と2,304の呼び出しが記録されず、2,432から3,328までの8件で準備が成立した。末尾3,456から歌唱Workletの初回までの差は128フレーム。同じ差は欠測を伴う23件すべてで見られ、欠測のなかった9件では0だった。いずれの試行でも歌唱ノードの初回から歌唱開始までの差は3,072フレームで、歌唱の開始待ちは連続していた。[例の観測JSON](../runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-a/artifacts/direct-1-eight/browser.json)

4量子条件では、先行枝の最後の連続区間の先頭から歌唱開始までが8量子条件より384〜640フレーム短く、中央値は512フレームだった。クリックから歌唱先頭までは、直接出力8組で中央値12.5 ms短縮した（組内差 −26〜+6 ms）。全32試行の歌唱PCM49,200フレーム、状態769点、歌唱計画は同じオフライン基準と一致した。並列観測16試行では予約位置の生PCM、末尾の補完80フレーム、前後の連続性と無音を確認した。標準ライブラリで観測列と保存WAVを読み直し、フレームの差集合とPCMを別に照合した。固定上流との差は歯のフィルタ下限1,200 Hzの基準と同じで、最大差 `2.7573 × 10⁻³`、差が `10⁻⁶` を初めて超えた位置は27,939フレームだった。[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)・[並列観測の例](../runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-repeat/artifacts/observed-1-four/output-probe.json)

人工データでも、同じ窓に呼び出し欠落1量子と入力なしの呼び出し1量子があると、出力が128フレームずつに分かれることを確認した。128件の上限を超えたときは全件取得の判定を拒む。画面上の追加試験では、`songSilentLeadTrace` を有効にした場合だけ観測JSONに入力列が入り、両方の設定から保存したWAVのSHA-256は一致した。

今回の観測で特定したのは、対象のコンテキスト時刻に先行Workletの `process()` の記録がないこと。次は既存のChromiumトレースから描画要求とWorkletの呼び出しを同じ再生で採り、グラフ全体の時計が進んだのか、先行ノードの呼び出しだけが欠けたのかを照合する。機器からの波形と聴感は未計測。[既存のトレース入口](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L415)

後続の同時トレースでは、フレーム番号が飛んだ23件すべてで、その前後の呼び出しは同じ描画要求の隣り合う量子だった。この記録の欠番は `currentFrame` の値に現れた。[後続の照合](worklet-live-song-fast-app-silent-lead-native-trace.md#実測)

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-input-trace.json
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回と `/private/tmp` からの再実行は各370件の取得判定・9予測を通過した。両実行の入力564件と出力264件のサイズ・SHA-256を確認し、大容量成果25.64 MBをRTL9210B-CGに保存した。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-repeat/manifest.json)
