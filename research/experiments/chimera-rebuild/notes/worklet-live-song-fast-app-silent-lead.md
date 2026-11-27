# 歌唱画面の実時間再生で8量子の無音先行を比較する

計測用の先行枝では、先行PCMを0のまま待ち時間を32から8量子に縮めても、歌唱ノードが最初の連続区間で開始した。今回の対象は歌唱画面の「実時間で歌唱」で、ボタンから歌唱先頭の描画までを測る。設定は画面のURLの `?songSilentLead=8` で選べる。`songStartupTrace=1` も指定すると、観測JSONに開始時の区間計時と歌唱先頭を処理したエポック時刻が入る。[前回の比較](worklet-live-song-fast-zero-lead-wait.md)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead.json)

## 上流の呼び出し順と時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `playTune()` は再生の準備と辞書の読み込みを待ち、歌詞から音節を得て、移調・テンポ・身体設定を反映した歌唱計画を作る。`t0` は秒、拍の長さは `60 / bpm` 秒で、各拍数を掛けて次の音符の時刻を求める。`AudioEngine.build()` は操作中にContextを再開し、WASMを渡すWorkletを登録してから既存のグラフを差し替える。`AudioEngine.schedule()` は計画IDと置き換えフラグを付けてジェスチャー列を送る。[歌唱](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)

Workletの `schedule` はジェスチャーをWASMのレコードへ書き、待ち時間を省略した場合は0.03秒を渡す。Rustの `Engine::schedule()` は `voice.clock + lead` を各ジェスチャーの両端に加え、必要なら以前の計画を破棄してから予約する。`process()` は出力長を `engine_render()` に渡し、内部メモリのPCMを各出力チャンネルへコピーする。`Engine::render()` は累積サンプル位置 `pos` を保持し、内部ブロックの始点で次の処理を予約する。`fast_runs_land_on_the_beat()` は音符が短くても計画上の母音が拍に揃うことを、`output_does_not_depend_on_the_host_block_size()` はホストが要求するブロック分割を変えてもPCMがビット一致することを検査する。[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[短音のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[分割のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 画面側の接続と観測

`SongPanel.run()` がURLの設定を読み、`renderRealtimeSongVoice()` が同じ歌唱経路でContext再開、WASMコンパイル、辞書読み込み、計画、歌唱Worklet登録を進める。無音先行を選んだ場合は歌唱Worklet登録の後、同じContextの単チャンネルバッファをループし、1入力の先行Workletを通して出力先に接続する。先行Workletの出力バッファは初期値の0を保つ。入力長またはサンプル値が条件から外れたり、フレームが飛んだりしたら連続区間を数え直す。連続する8回分の絶対フレームを受け取ったら歌唱ノードを作る。先行枝は歌唱中も動かし、終了または中止で止める。[画面の入口](../../../../web/prototypes/chimera-research/src/main.tsx#L616)・[歌唱経路](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L270)・[先行枝](../../../../web/prototypes/chimera-research/src/song-silent-lead.ts)・[先行Worklet](../../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts)

歌唱ノードは先行枝と独立に連続8量子を確認する。量子長を `Q = 128`、連続区間の先頭を `C` とすると、予約は `C + 8Q + 2,048` フレーム。最初の歌唱Workletの呼び出しを `V`、待ちのコールバック数を `K`、待ちを終えたフレームを `A` とすると、飛んだフレーム数は `A − V − KQ`。並列観測では絶対フレームの差が `Q` を超えた分を足して同じ値を出す。歌唱PCMは予約からの相対位置で揃え、絶対位置で2量子以上の前後と最終量子の補完を検査する。最初の音符の位置も譜面の秒から別途求めて予約に加える。[歌唱の開始時計](../../../../web/prototypes/chimera-research/src/worklet-clock.ts)・[PCMの採取](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[比較コード](../tools/measure_worklet_live_song_app_silent_lead.py)

クリック時刻には文書のキャプチャ段階の `Date.now()`、歌唱先頭には予約に到達したWorkletコールバックのエポック時刻を使う。この差はPCM先頭の描画を始めるまでの時間で、実機経由の出力や音符の立ち上がりは別の観測になる。並列観測で追加するWorkletの登録時間が混ざらないよう、クリック時間の主判定は直接出力の試行で行う。事前の計測用先行枝からは開始待ちの飛びが減ると予測し、ボタンからは先行枝の登録と待ちが増えるため処理開始まで長くなると予測した。

## 実測

2回の実行で、直接出力と並列観測でそれぞれ8組を比較した。各試行はページを開き直し、辞書の初回読み込みと新しいContextを使った。

| 観測 | 通常 | 無音先行8量子 |
| --- | ---: | ---: |
| 開始待ちに飛びがあった試行、直接出力 | 7 / 8 | 0 / 8 |
| 開始待ちに飛びがあった試行、並列観測 | 4 / 8 | 0 / 8 |
| クリックから歌唱先頭の描画、直接出力 | 254〜301 ms | 271〜306 ms |

直接出力の組内差（無音先行から通常を引いた値）の中央値は初回 +16 ms、再実行 +29.5 ms、2回を合わせて +24 ms。8組中7組で延び、初回の1組は30 ms短かった。並列観測では組内差の中央値が +26 ms。直接出力で有効化した先行枝は、先行Worklet登録の開始から準備完了までに32.3〜41.2 msかかった。8量子は48 kHzで約21.33 msに相当し、計測区間には登録とグラフの稼働開始、通知も含む。最初に観測した先行量子から歌唱先頭までは4,096〜4,224フレーム。歌唱ノード自身は16回すべて最初の呼び出しから3,072フレーム後に開始した。通常経路で飛んだ量は直接出力で256〜512フレーム、並列観測で256フレームだった。[初回の結果](../runs/worklet-live-song-fast-app-silent-lead-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-fast-app-silent-lead-20261121-repeat/summary.json)

全32試行で、保存WAVの49,200フレームが同じ設定のオフラインPCMとビット一致し、769点の状態と歌唱計画も一致した。並列観測16試行では前後の無音、最終量子の補完80フレーム、絶対フレームでの予約と飛びも確認した。標準ライブラリでWAVのデータチャンクと並列観測の生PCMを読み直して同じ位置で照合した。固定上流との最大差は全試行で `2.7573 × 10⁻³`、`10⁻⁶` を初めて超えた位置は27,939フレームで、歯のフィルタ下限を1,200 Hzにしたオフライン条件で保存していた差と同じだった。[オフライン基準](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)・[並列観測の一例](../runs/worklet-live-song-fast-app-silent-lead-20261121-repeat/artifacts/observed-1-silent/output-probe.json)

停止操作は追加のChromium試験で確認した。Playwrightの `addInitScript` で初回だけ先行ノードの `MessagePort.onmessage` を捕捉し、8量子の通知をアプリに渡さず「歌唱を停止」を押した。歌唱ノード生成0回、先行音源停止1回、Contextは `closed`。同じページで次の通知は通常どおり通すと、歌唱を完了してWAVの保存リンクが表示された。ページエラーは0件だった。

今回の切り替えは試験設定として扱う。次の比較では8量子の条件と先行枝の接続順を固定し、先行Workletの登録だけを歌唱Workletの登録と並行させる。クリックからの時間、先行枝の準備区間、絶対フレームの飛び、PCMを再測定する。他のブラウザ、音声機器からの出力、聴感は未確認。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID>
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回と `/private/tmp` からの再実行は各282判定・7予測を満たした。両実行の入力546件と出力264件をサイズとSHA-256で照合した。実行時の大容量成果25.59 MBはRTL9210B-CGに保存した。TypeScript検査とビルドは完了し、Viteは既存の声道3Dのチャンクサイズに警告を出した。[初回マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-20261121-a/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-20261121-repeat/manifest.json)
