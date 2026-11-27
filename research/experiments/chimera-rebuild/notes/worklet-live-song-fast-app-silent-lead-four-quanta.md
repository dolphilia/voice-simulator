# 歌唱画面の無音先行を8量子から4量子に短縮する

前回、8量子の先行を維持したままWorklet登録を重ねても、クリックから歌唱先頭までの短縮は安定しなかった。今回は直列登録を使い、先行枝が通知するまでの連続量子数だけを8から4に変える。48 kHz・128フレームの1量子は約2.667 msで、4量子の差は512フレーム、約10.667 msに当たる。歌唱画面で `?songSilentLead=4` または `?songSilentLead=8` を指定すると各条件を試せる。[前回の実測](worklet-live-song-fast-app-silent-lead-registration.md#改訂後の計測)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead-four-quanta.json)

## 上流の歌唱と出力の時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` は既存のContextを再開し、初回は `build()` がContextの再開と合成Workletの登録を進める。登録後にコンパイル済みWASMを渡してノードを作る。歌唱ボタンから呼ばれる `playTune()` は使用する音節、MIDI番号、音価、BPMを決め、`60 / bpm` 秒に各音の拍数を掛けて音符の時刻を求める。`AudioEngine.schedule()` は相対秒のジェスチャー列をWorkletへ送る。WorkletはABIのレコード領域に書き、`engine_schedule()` がRust側に渡す。`Engine::schedule()` は `voice.clock + lead` を各端点に加え、必要なら以前の計画を破棄してから予約する。[歌唱ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L192)・[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)

上流の `process()` は出力チャンネルのフレーム数を `engine_render()` に渡し、ABIが返すPCMをコピーする。`Engine::render()` は `pos % SUB_BLOCK` でブロック内の位置を復元し、要求をまたいで声の状態を進める。`fast_runs_land_on_the_beat()` は短音の計画が拍に揃うこと、`output_does_not_depend_on_the_host_block_size()` は128フレームの出力が1、77、4,096、48,000フレームの分割でもビット一致することを調べる。ゼロPCMを使う先行枝は候補独自の起動条件で、固定上流との差は保存済みの同じ短音ケースで比較する。[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[ABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 候補の4量子条件と比較式

`SongPanel.run()` はURLの4または8を選び、`prepareSongSilentLead()` がその値を `processorOptions` で先行Workletへ渡す。先行枝は同じContextで128フレームの0入力を連続して数える。入力の欠落・非ゼロ値、または絶対フレームの飛びがあればその連続区間を数え直す。通知には最初に条件を満たした有効入力の位置、通知までに見た有効入力の数、最後に連続した4または8量子を含める。歌唱側は通知後に従来の `WorkletStartup.ready()` を使い、連続8量子を確認してから2,048フレームを待つ。[画面の入口](../../../../web/prototypes/chimera-research/src/main.tsx#L615)・[先行枝](../../../../web/prototypes/chimera-research/src/song-silent-lead.ts)・[量子の計数](../../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts)・[歌唱の予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)

先行枝の最後の連続区間の先頭を `L`、先行の量子数を `N`、歌唱Workletの初回を `V`、歌唱の開始予約を `S`、量子長を `Q = 128` とする。先行枝が準備を終えるフレームは `L + NQ`。開始までの `S − L` を `NQ + (V − (L + NQ)) + (S − V)` に分け、通知後のノード作成に相当する区間と歌唱側の待ちを照合する。歌唱側に飛びがなければ `S − V = 3,072`。組内で `S − L` が512フレーム短くなり、ばらつきが1量子以内と予測した。別時計で採るクリック時刻はContextやWASM、辞書の準備も含むため、直接出力では中央値の符号を判定する。並列観測では二つのWorkletの切断を採取末尾まで保持し、歌唱の絶対位置と前後の無音を独立照合する。[計測コード](../tools/measure_worklet_live_song_app_silent_lead.py)

## 実測

2回の計測で、直接出力と並列観測を合わせて32試行を取得した。4量子と8量子の各16試行で、歌唱側の開始待ちの飛びは0。通知位置から歌唱Workletの初回までは0〜128フレーム、初回から歌唱開始までは全試行で3,072フレームだった。先行枝の連続区間の先頭から歌唱開始までは4量子条件で3,584〜3,712フレーム、8量子条件で4,096〜4,224フレーム。組内の短縮は384〜640フレーム（8.0〜13.33 ms）、中央値512フレーム（10.67 ms）で、全16組の誤差が1量子以内だった。[初回の結果](../runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-repeat/summary.json)

| 観測点 | 4量子にしたときの時間差 |
| --- | ---: |
| クリックから歌唱PCMの先頭まで、直接出力8組 | 中央値 −20.5 ms、範囲 −39〜+5 ms |
| 先行枝の接続直前から通知まで、同じ直接出力8組 | 中央値 約 −9.1 ms、範囲 −20.4〜−4.1 ms |
| クリックから歌唱PCMの先頭まで、並列観測8組 | 中央値 −6.5 ms、範囲 −20〜+5 ms |

直接出力のクリック時間の中央値は初回 −11.5 ms、再実行 −21.0 ms。8組中2組は全体で4 msと5 ms延びた。どちらも、量子数が効く前のContext作成開始から先行枝接続までが約9.5 msと12.3 ms長かった。先行枝の接続直前から通知までの時間は8組すべてで短く、クリック時間の中央値にはその前の準備時間のばらつきも含まれる。

先行枝では、初めて有効な入力が届いてから通知するまでに、4量子の13/16試行と8量子の14/16試行で有効入力を観測できない256〜512フレームがあった。その後の連続区間で通知が成立した。今回のログでは、その区間にコールバックがなかったか、入力を有効と判定できない量子があったかまでは区別できない。歌唱ノードは通知の後に生成され、全試行で連続した。

全32試行のPCM49,200フレームと状態769点、歌唱計画はオフライン基準と一致した。標準ライブラリでも保存WAVを読み直し、並列観測16試行で同じPCMが予約位置からビット一致することと、前後の無音および末尾の補完80フレームを確認した。固定上流との最大PCM差は `2.7573 × 10⁻³`、差が `10⁻⁶` を初めて超えた位置は27,939フレームで、歯のフィルタ下限1,200 Hzを用いた基準と揃った。追加のブラウザ操作では、既存の8量子と並行登録の併用が動き、値5では通常通り49,200フレームを保存できた。[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)・[並列観測の例](../runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-repeat/artifacts/observed-1-four/output-probe.json)

次は既存のFirefox実時間歌唱の入口で同じ4量子と8量子を比較し、Chromiumで確認した歌唱開始の連続性とPCMが再現するか調べる。Firefoxでの今回の設定、機器からの波形、聴感は未測定。[既存のブラウザ間比較](worklet-live-song-cross-browser.md)

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-four-quanta.json
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回と `/private/tmp` からの再実行は各338件の取得判定と7件の予測を通過した。入力558件と出力264件のサイズ・SHA-256を確認し、大容量成果25.61 MBをRTL9210B-CGへ保存した。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-repeat/manifest.json)
