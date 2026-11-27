# FirefoxでWorkletの再開前登録と無音先行の有無を比較する

Chromiumで採取した歌唱画面の条件をFirefoxで再実行する。両条件とも `?songRegisterBeforeResume=1` で起動し、先行枝を使う場合だけ `&songSilentLead=4` を加える。Firefoxでは再開後に無音先行を4量子・8量子にした比較が済んでいる。今回は最初の合成用Workletの登録完了までContextを停止した状態に保つ。[事前登録](../cases/worklet-live-song-fast-app-silent-lead-preregister-firefox.json)・[Chromiumでの比較](worklet-live-song-fast-app-silent-lead-preregister-presence.md)・[Firefoxでの4・8量子の比較](worklet-live-song-fast-app-silent-lead-firefox.md)

## 上流の歌唱とブラウザの計測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` は既存のContextを再開する。初回の `build()` は操作の中で `resume()` を要求し、`addModule()` の完了後にコンパイル済みWASMを渡してノードを生成する。`playTune()` は準備を待ち、音高をMIDI番号、長さを拍数で渡して歌唱計画を作る。テンポ `bpm` の1拍は `60 / bpm` 秒になる。`AudioEngine.schedule()` がジェスチャー・計画の終点・置換フラグをWorkletへ送り、`writeGestures()` は秒単位の開始・終了・ランプと各目標値をWASMのリトルエンディアンのレコードへ書く。`engine_schedule()` で読み戻したレコードは、`Engine::schedule()` が `voice.clock + lead` を足してエンジンの時刻へ移す。`lead` の既定値は0.03秒。`process()` はホストの出力フレーム数を `engine_render()` へ渡し、float32のバッファをチャネルへ複写する。`Engine::render()` は累積サンプル `pos` を保ち、`pos % 128` を使って呼び出しをまたぐ内部境界をそろえる。[起動と予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[レコード](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/wire.ts#L48)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustのエンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)

上流の `fast_runs_land_on_the_beat()` は240 BPM・4分の1拍を含む入力で、母音開始が計算上の拍から `10⁻⁶` 秒未満のずれに収まり、母音区間を20 ms以上保つことを調べる。`output_does_not_depend_on_the_host_block_size()` は128サンプル刻みのPCMを基準に、1、77、4,096、48,000サンプル刻みでも同じビット列を返すことを確かめる。ブラウザの停止中に登録できるかは、今回の画面操作で別途確認する。[上流の短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[ブロック分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `withRealtimeContext()` は、新しいContextを停止してから合成Workletを登録する。登録のPromiseが解決するとContextを再開する。再開と別途始めたWASM読み込みがそろったあと辞書を読み、譜面を準備する。`renderRealtimeSongVoice()` が先行枝を使う場合、0で初期化したAudioBufferを出力する枝をつなぎ、128フレームの有効入力4量子を待つ。どちらも同じ `captureWorklet()` で合成ノードを作る。停止から再開までの状態とページ上のミリ秒時刻は `startSongTrace()` に残り、Contextフレーム表示は `round(currentTime × sampleRate)` で求める。歌唱ノード内部の予約はWorklet自身の絶対フレームを使う。最初から連続なら `8 × 128 + 2,048 = 3,072` フレーム後に歌唱を開始する。[画面の入口](../../../../web/prototypes/chimera-research/src/main.tsx#L615)・[フェーズの記録](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L42)・[停止、登録、再開](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L167)・[歌唱の予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)

取得スクリプトに、同じ先行条件を試した別ブラウザの保存結果を照合元として指定できるようにした。確定済みのChromium実行をマニフェストから読み、量子数、試行順、並列観測条件と、連続した開始・PCM一致の判定を検査する。計測では直接出力のクリックと初回歌唱を `Date.now()` で、譜面準備とノード生成の間をページの `performance.now()` で取る。並列観測では出力当たり128フレームの生PCMと絶対フレームを別のWorkletで保存する。[取得と保存基準の照合](../tools/measure_worklet_live_song_app_silent_lead.py)・[並列の出力観測](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs#L1)

## 実測

短音「Pop Dee」、240 BPM、出力48 kHz・内部96 kHz。歯フィルタ下限は1,200 Hz、乱流の全体倍率1、声門由来と狭窄由来のゲイン倍率は0とした。初回と再実行で計32試行を取得した。すべての試行で登録開始・完了時のContextは `suspended` で、表示フレームは0だった。再開後の歌唱側の開始待ちの欠落は0で、最初のコールバックから3,072フレーム後に描画を開始した。4量子の16試行では、先行枝は最初の有効入力から連続し、通知位置と歌唱側の初回フレームは一致した。[初回の結果](../runs/worklet-live-song-fast-app-silent-lead-preregister-firefox-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-app-silent-lead-preregister-firefox-20261121-repeat/summary.json)

無音先行ありから先行なしを引いた組内差を示す。正の値は先行なしで短縮したことを示す。

| 観測区間 | 経路 | 初回の中央値 | 再実行の中央値 | 8組の中央値と範囲 |
| --- | --- | ---: | ---: | ---: |
| クリックから歌唱先頭の描画 | 直接出力 | 24.5 ms | 21.5 ms | 21.5 ms（−2〜49 ms） |
| 譜面準備完了からノード生成開始 | 直接出力 | 22 ms | 21 ms | 21.5 ms（18〜23 ms） |
| クリックから歌唱先頭の描画 | 並列観測 | 21 ms | 30 ms | 28 ms（14〜32 ms） |
| 譜面準備完了からノード生成開始 | 並列観測 | 22 ms | 21.5 ms | 22 ms（20〜27 ms） |

直接出力では、クリックからの時間は8組中7組で短縮し、1組で2 ms延びた。譜面準備からノード生成までは8組すべてで短縮した。無音先行ありの直接出力で、先行用モジュールの登録はFirefoxで中央値11 ms、保存済みChromiumで2.85 ms。先行枝の接続直前から通知まではそれぞれ10 msと8.05 msだった。両ブラウザとも通知位置から歌唱ノードの初回までのフレーム差は0だった。Firefoxで増えた譜面準備後の時間は登録区間にも表れた。HTTP取得・モジュール評価など登録時間の内訳までは今回の計測点で分離できない。[Firefoxの計時](../runs/worklet-live-song-fast-app-silent-lead-preregister-firefox-20261121-repeat/summary.json)・[Chromiumの計時](../runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-repeat/summary.json)

オフライン、Firefox全32試行、保存済みのChromium全32試行のWAVを独立に読み直し、PCM49,200フレームすべてのビット一致を確認した。状態769点と歌唱計画、提供された辞書とWASMのハッシュも両ブラウザで一致した。Firefoxの並列観測16試行では生PCMから予約位置を切り出し、開始待ちと前後の無音、最終量子の80フレームの補完を照合した。固定上流との差は最初のビット差が4,114フレーム、最大絶対差が `2.757307142019272 × 10⁻³`、`10⁻⁶` を超える最初の差が27,939フレームで、歯フィルタ下限1,200 Hzの基準と同じだった。Safariでの登録と再開、機器からの出音、聴感は未測定。[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)・[固定上流PCM](../runs/song-voice-fast-constriction-source-20261121-repeat/manifest.json)

## 再現と保存先

研究ワークスペースから実行する。`<実行ID>` は未使用のIDを指定する。再実行は `/private/tmp` からPython、スクリプト、ケースを絶対パスで指定した。

```bash
CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox \
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-preregister-firefox.json
```

macOS 15.6.1 arm64、Headless Firefox 157.0（アプリのBuildID `20261002115412`）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各回の取得判定346件と予測6件が通過し、失敗と欠測は0だった。各回の入力285件と出力132件をサイズとSHA-256で照合し、大容量成果2回分をRTL9210B-CGに26,025,505バイト保存した。固定上流のチェックアウトで `cargo test --locked -p chimera --test engine output_does_not_depend_on_the_host_block_size` と `cargo test --locked -p chimera --test sing_fast fast_runs_land_on_the_beat` を実行し、各1件が通過した。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-preregister-firefox-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-preregister-firefox-20261121-repeat/manifest.json)
