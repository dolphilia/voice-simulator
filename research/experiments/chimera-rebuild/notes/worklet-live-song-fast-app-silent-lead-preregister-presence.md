# Workletを再開前に登録した場合の無音先行の有無

Chromiumの歌唱画面で、合成Workletを停止中に登録する `?songRegisterBeforeResume=1` と、同じ設定に `&songSilentLead=4` を加えた経路を比べる。前回のネイティブトレースでは、再開前登録の16試行で先行Workletの初回フレーム番号が連続した。今回の比較では合成Workletの登録順をそろえる。[前回の比較](worklet-live-song-fast-app-silent-lead-register-before-resume.md#実測)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead-preregister-presence.json)

## 上流の再開と描画

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.start()` は既存のContextを再開する。初回は `build()` が操作中に `resume()` を要求し、モジュールを登録してからコンパイル済みWASMを渡してノードを作る。`playTune()` は準備完了を待ち、音節、MIDI音高、音符の拍数、テンポからジェスチャーを作る。譜面上の区間は `60 / bpm` 秒を1拍として積算する。Workletは `schedule` メッセージのジェスチャーをWASMに書き、`Engine::schedule()` が声の経過秒 `voice.clock` と待ち秒 `lead` を加えた時刻に各ジェスチャーを予約する。`process()` は出力チャネルのフレーム数を `engine_render()` に渡し、返るfloat32 PCMをチャネルへコピーする。`Engine::render()` は累積フレーム `pos` を進め、`pos % SUB_BLOCK` で内部処理の境界を保つ。`fast_runs_land_on_the_beat()` は短音で母音開始が拍に収まること、`output_does_not_depend_on_the_host_block_size()` は別のブロック長でも128フレーム刻みと同じPCMになることを検証する。[起動](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[譜面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[ブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 研究版の比較経路

通常の歌唱ボタンから `renderRealtimeSongVoice()` を呼ぶ。両条件で `withRealtimeContext()` は新しいContextの `suspend()` 完了を待ち、合成用の `addModule()` を完了してから `resume()` を呼ぶ。再開とWASM取得の完了後に辞書を読み、譜面を準備する。無音先行を指定すると、先行用モジュールを登録し、0で埋めた1チャネルのバッファを繰り返し流して4量子の連続入力を待つ。無音先行の指定を省く経路は譜面準備後に `captureWorklet()` へ進む。どちらも登録済みの合成モジュールを使い、入力0チャネルの歌唱ノードを作る。今回追加した比較処理は取得ツールにあり、歌唱画面の既存経路を呼び出す。[歌唱ボタン](../../../../web/prototypes/chimera-research/src/main.tsx#L620)・[再開順と歌唱経路](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L167)・[先行枝](../../../../web/prototypes/chimera-research/src/song-silent-lead.ts#L4)・[取得と比較](../tools/measure_worklet_live_song_app_silent_lead.py)

歌唱Workletの `WorkletStartup` は初回のContextフレームを保持し、途中で飛びを検出すると連続回数を戻す。連続した8量子の次のコールバックで `RealtimeSpeechCapture` がそのフレームに `leadFrames` を足し、初回出力を予約する。今回は128フレームの8量子と2,048フレームの待ちで、飛びが無ければ初回から `8 × 128 + 2,048 = 3,072` フレーム、48 kHzで64 ms後となる。開始後の観測区間は歌唱49,200フレーム。直接出力ではクリックから最初の歌唱コールバックまでと、譜面準備完了からノード生成開始までを計時する。並列観測では別のWorkletで取得した絶対フレームとPCMを使い、予約に対する歌唱区間、前後の無音、最終量子の補完を照合する。[連続量子の状態](../../../../web/prototypes/chimera-research/src/worklet-clock.ts#L1)・[歌唱の予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)・[並列観測](../../../../web/prototypes/chimera-research/tools/song-output-probe.mjs#L1)

## 実測

短音「Pop Dee」、240 BPM、出力48 kHz・内部96 kHz、歯フィルタ下限1,200 Hzで2回実行し、各回で直接出力4組と並列観測4組を採取した。全32試行で停止中に合成Workletの登録を完了した。先行枝ありの16試行は4連続量子で通知し、先行枝なしの16試行では先行枝の観測と起動マーカーが現れなかった。全試行で歌唱側の開始待ちの欠落は0で、初回から3,072フレーム後に歌唱を開始した。PCM49,200フレームは全区間でオフラインとビット一致し、状態769点と歌唱計画も一致した。並列観測16試行の絶対フレームとfloat32の生データを別に読み、歌唱前後の無音と最終量子の80フレームの補完を確認した。[初回](../runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-a/summary.json)・[再実行](../runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-repeat/summary.json)・[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)

表は無音先行ありから先行なしを引いた組内差。正の値は無音先行を省いた方が短いことを示す。

| 観測区間 | 経路 | 初回の中央値 | 再実行の中央値 | 8組の中央値と範囲 |
| --- | --- | ---: | ---: | ---: |
| クリックから歌唱先頭の描画 | 直接出力 | 9.5 ms | 11 ms | 9.5 ms（−1〜30 ms） |
| 譜面準備完了からノード生成開始 | 直接出力 | 10.45 ms | 11.15 ms | 10.95 ms（9.5〜13.7 ms） |
| クリックから歌唱先頭の描画 | 並列観測 | 5.5 ms | 11 ms | 8.5 ms（−7〜17 ms） |
| 譜面準備完了からノード生成開始 | 並列観測 | 9.6 ms | 11.85 ms | 10.2 ms（9.4〜13.6 ms） |

直接出力のクリック時間は8組中7組で短縮した。譜面準備からノード生成までは全8組で短縮し、条件ごとの中央値は先行なし0.2 ms、先行あり11.15 msだった。先行枝の接続直前から通知までの中央値は8.05 msで、4量子のPCMに対応する `4 × 128 / 48,000 ≈ 10.67 ms` とは測定する区間が異なる。接続時刻と最初の入力量子の境界がずれるため、4本の入力を受け取るまでを接続直後から10.67 msに固定して予測することはできない。[各組の区間](../runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-repeat/summary.json)

固定上流PCMとの最大絶対差は `2.757307142019272 × 10⁻³`。最初のビット差は4,114フレーム、差が `10⁻⁶` を超える最初の位置は27,939フレームだった。両条件が歯フィルタ下限1,200 Hzのオフライン基準とビット一致し、今回の起動条件を変えても既知の差は変わらなかった。測定範囲はHeadless Chromiumの歌唱Workletとグラフまで。Firefox・Safariでの再開前登録、機器の出音と聴感は未検証。[1,200 Hz条件の比較](worklet-song-fast-teeth-lowpass-floor.md)・[固定上流のPCM](../runs/song-voice-fast-constriction-source-20261121-repeat/manifest.json)

## 再現と保存先

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。2回目は `/private/tmp` から、Python、スクリプト、ケースを絶対パスで指定して同じ手順を実行した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-preregister-presence.json
```

macOS 15.6.1 arm64、Headless Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各回の取得判定346件と予測6件をすべて通過した。入力285件と出力132件のサイズ・SHA-256を各回で照合した。うち18件の既存実行への入力参照は、最初の独立照合でソースのスナップショットにもあると仮定して読み出せず、保存元の実行にあるファイルへ参照を戻して照合した。大容量成果はRTL9210B-CGに2回分で25,638,848バイト保存した。実行の失敗や欠測はなかった。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-repeat/manifest.json)
