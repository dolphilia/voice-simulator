# Firefoxの歌唱を同じWASMインスタンスで事前描画する

前回は先頭量子と定常部の時間差の83.1〜86.8%がWASMの描画呼び出しにあった。今回は使い捨て状態で呼び出す範囲を変え、初期化と描画のどちらに時間がかかるかを測る。Firefoxの `Code::getOrCreateInterpEntry` には必要に応じてWASMの入口を用意する分岐がある。対象のエクスポートが通る分岐や描画内部の最適化は、この分岐を見ただけでは特定できない。[前回の区間計時](worklet-live-song-render-phases.md)・[SpiderMonkeyの入口処理](https://searchfox.org/firefox-main/source/js/src/wasm/WasmCode.cpp#1781)

## 上流と候補の状態

固定上流では `ChimeraProcessor.process` が第1出力チャンネルの長さを `engine_render` に渡す。同関数は上限内のフレーム数を `Engine::render` に渡し、32ビットPCMを保持する領域のアドレスを返す。`Engine` は出力フレーム位置 `pos`、声、呼気ゲート、ビートのスケジューラーを持つ。`pos % 128` が0のときにスケジューラーを進め、次の128フレーム境界か要求の末尾まで描画する。`HumanVoice::render` は別のカウンターを管理し、内部倍率を `m` とすると、`64 * m` 内部サンプルごとに制御を更新する。制御の時間刻みはこれを内部サンプルレートで割った秒数で、スコアのブレンド、調音器、声道形状、呼気とピッチの計算に使う。`output_does_not_depend_on_the_host_block_size` は、同じ絶対フレームに操作を置いて1、77、128、4,096、48,000フレームの分割をビット単位で比べる。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L192)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流の発声制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補の `vocal_start_score_with_body` は設定と体型を使って調音モデルを組み、調音スコアを設定して、出力位置を0で始める。内部96 kHz、出力48 kHzでは1出力につき内部2サンプルを進め、出力64フレームごとに制御を更新する。`ArticulatedVoice::step_with_glottal_pressure` は、制御境界でスコア時刻をもとに目標を更新し、調音器、声道形状、乱流を更新してから、呼気・声門・気道のサンプルを進める。出力段は放射流量の時間変化を間引いてPCMにし、DC除去では `y[n] = x[n] - x[n-1] + a y[n-1]` を使う。`vocal_render` はPCMを書き出した後に累計フレームを更新し、最後の観測に声門面積（cm²）、流量（cm³/s）、F0（Hz）、調音位置などを保存する。0フレームはこの状態更新に入る前に戻る。`song_render_allocation_profile` も同じスコアを設定したABIを使い、観測の間隔で要求を分割する。[候補のABIと試験](../crates/vocal-wasm/src/lib.rs)・[調音の更新](../crates/vocal-core/src/voice.rs#L518)・[PCM出力段](../crates/vocal-core/src/output.rs#L76)

## 事前登録

通常画面の実時間歌唱を、未準備、0フレーム1,000回、0フレーム1,000回と出力256フレームの事前描画の3条件で比べる。後2条件は同じスコアを設定した使い捨て状態を構築・解放する。事前描画の要求を64フレームずつに分けて、本番の観測間隔に合わせる。事前描画が先頭量子のWASM時間の中央値を未準備の70%以下、0フレーム対照の80%以下にし、3回中2回は先頭量子が128/48,000秒以内になると予測する。コンストラクターの時間も観測し、時間の予測と信号の判定を記録する。[事前登録](../cases/worklet-live-song-render-warmup.json)・[固定発声の事前描画](worklet-wasm-dsp-warmup.md)

## 計測区間

`FixedVoiceEngine` の同じ初期化を使い捨て状態と本番で共有した。使い捨て状態の作成、0フレーム呼び出し、描画、解放を6個の印で区切る。`vocal_free` でハンドルを解放した後、同じ `WebAssembly.Instance` に本番用ハンドルとPCM・観測のビューを作る。先行無音の最後に印の間隔を測り、本番は先頭、第2、第33、第34量子を計時した。Firefoxの `AudioWorkletGlobalScope::ConstructProcessor` の区間にはオプションの復元とJSコンストラクターが含まれる。準備の印はすべて描画と同じ `GraphRunner` のこの区間内にあり、最初の `process()` は区間終了後に始まることを照合する。[ホストの状態確保と解放](../crates/vocal-wasm/host/fixed-voice.ts)・[Workletの準備](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L65)・[Firefoxの構築区間](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletGlobalScope.cpp#1214)・[解析](../tools/measure_worklet_live_song_render_phases.py)

## 再実行と処理時間

修正後と `/tmp` からの再実行は各127判定を通過した。各組の計時付き3試行の中央値を順に示す。事前描画の3件ずつは全描画量子が2.667 ms以内だった。未準備の6件と0フレーム対照の6件は、先頭量子がすべて予算を超えた。[修正後の集計](../runs/worklet-live-song-render-warmup-20261121-b/summary.json)・[別ディレクトリからの再実行](../runs/worklet-live-song-render-warmup-20261121-repeat/summary.json)

| 条件 | 先頭のWASM（ms） | 先頭のネイティブ区間（ms） | 第2量子のWASM（ms） | 構築のネイティブ区間（ms） |
| --- | ---: | ---: | ---: | ---: |
| 未準備 | 3.419 / 3.388 | 3.959 / 3.908 | 2.650 / 2.634 | 1.379 / 1.234 |
| 0フレーム | 3.352 / 3.293 | 3.887 / 3.810 | 2.535 / 2.487 | 2.101 / 2.023 |
| 256フレーム事前描画 | 1.423 / 1.420 | 1.914 / 1.861 | 1.375 / 1.381 | 8.125 / 7.873 |

事前描画で先頭量子のWASM時間は未準備の41.6%と41.9%、0フレーム対照の42.5%と43.1%に減り、登録した3つの予測を両方で満たした。使い捨て状態の描画には5.952〜6.170 ms、0フレーム呼び出し1,000回には0.094〜0.111 msかかった。描画を含む構築時間の増分は未準備に比べ中央値で6.64〜6.75 msだった。冒頭32量子を除くp99は全試行で1.735〜1.803 ms、校正で隣接する印の最大間隔は32.417 µsだった。[試行別の区間と予測](../runs/worklet-live-song-render-warmup-20261121-repeat/summary.json)

本番の91,200点のPCM、音響観測1,425行、調音計画と拍、辞書とWASMは基準に一致した。拍のフレーム位置は独立計算の24,000と48,000に一致した。観測の先頭は出力フレーム63、発声状態内の累計64で、事前描画した256フレームは本番の累計に入っていない。固定上流に対する最大PCM差は2.3283064365386963×10⁻¹⁰、ビット差の最初は出力フレーム4,114。上流の関連試験は各実行17件を通過した。[上流との差と信号の照合](../runs/worklet-live-song-render-warmup-20261121-b/summary.json)

この条件で処理時間の一部は先頭2量子から構築に移った。Firefoxの描画関数内部で、コンパイルやメモリの状態がそれぞれどれだけ影響したかは、関数全体の計時からは確定できない。事前描画は `songRenderPreparation=draw` を指定した実験で使う。次は64、128、256フレームを同じ歌唱で比べ、本番の量子内の印を外して、構築時間と先頭2量子の超過を測る。事前描画の256フレームは出力の約5.33 msで、最初の拍の0.5秒より前の区間にあたる。音符が始まる区間への効果、物理出力の遅延と人による試聴は未計測。[第2量子に対する印の影響](worklet-live-song-render-phases.md#再実行と処理時間の分布)

## 再現と保存

研究ワークスペースから、新しい実行IDで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=450000000 \
  CHIMERA_FIREFOX='/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox' \
  ../../.venv/bin/python tools/measure_worklet_live_song_render_phases.py --warmup worklet-live-song-render-warmup-next
```

macOS 15.6.1 arm64、Headless Firefox 157.0、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。初回は、予算内の件数を集計した NumPy の `int64` をJSONに書き出せず失敗した。集計をPythonの整数で数えるよう修正し、元のマニフェストと採取済みの試行は保存した。WAV、観測、Firefoxプロファイルを可逆圧縮し、作業用のRTL9210B-CGへ保存した。内蔵側には事前登録、要約、マニフェスト、ソースのスナップショットを置いた。[初回のマニフェスト](../runs/worklet-live-song-render-warmup-20261121-a/manifest.json)・[修正後](../runs/worklet-live-song-render-warmup-20261121-b/manifest.json)・[再実行](../runs/worklet-live-song-render-warmup-20261121-repeat/manifest.json)

初回の `browser.json.gz`、`browser.wav.gz`、`firefox-profile.json.gz` を展開し、同じ音声判定と `phase_timing`、`summarize_warmup` に通したところ、初回の9件も127判定を満たした。元の失敗判定を保持している。主比較3実行の全27 WAVは、基準とファイル全体で一致した。上流読解で `Engine` の128フレームと `HumanVoice` の64フレームが別の刻みであることを確認し、固定発声の事前描画ノートにも反映した。[固定発声の事前描画ノート](worklet-wasm-dsp-warmup.md)

回帰確認では96 kHzの固定発声の事前描画で292判定、既存の歌唱区間計時で58判定を通過した。5実行で入力1,356件と出力320件のSHA-256を照合した。作業用ディスクでの成果は主比較が約74.42 MB、回帰確認が約33.55 MBだった。[固定発声の回帰確認](../runs/worklet-wasm-dsp-warmup-20261121-score-regression/manifest.json)・[歌唱区間計時の回帰確認](../runs/worklet-live-song-render-phases-20261121-warmup-regression/manifest.json)
