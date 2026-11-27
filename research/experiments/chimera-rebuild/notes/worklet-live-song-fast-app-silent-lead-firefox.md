# Firefoxの歌唱画面で無音先行の4量子と8量子を比較する

Chromiumでは、短音の同じ歌唱で無音先行を8量子から4量子にすると、先行枝の最後の連続区間から歌唱開始までが中央値512フレーム短くなった。開始待ちの飛びは両条件とも0だった。本対照ではブラウザをFirefoxに変え、4または8を選んだ同じアプリの「実時間で歌唱」から、開始位置とPCMを調べる。クリック時間は各ブラウザ内の組内差で比較する。[Chromiumの結果](worklet-live-song-fast-app-silent-lead-four-quanta.md#実測)・[事前登録](../cases/worklet-live-song-fast-app-silent-lead-firefox.json)

## 固定上流と比較対象

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AudioEngine.start()` が既設Contextを再開し、初回の `build()` では再開の要求後に合成Workletを登録し、コンパイル済みWASMを渡してノードを作る。`playTune()` は音節・MIDI番号・拍数から計画を作り、1拍 `60 / bpm` 秒を音符の時刻に反映する。Workletは `schedule` でジェスチャーをABIの領域に書き、`Engine::schedule()` が `voice.clock + lead` 秒を計画の端点に加える。描画コールバックは `engine_render()` に出力フレーム数を渡してPCMをコピーする。Rust側は累積フレーム位置 `pos` の内部ブロック長に対する剰余で処理を続ける。[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[Engine](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)

上流の `fast_runs_land_on_the_beat()` は短い音符の母音が拍に揃うことを、`output_does_not_depend_on_the_host_block_size()` はホストの描画要求を異なるサイズに分けてもPCMがビット一致することを検査する。上流は歌唱前の無音先行ノードを使わないため、上流との照合は、同じ短音で保存済みのPCMに対して行う。先行と歌唱ノードの絶対フレームの関係は、候補内で式と観測に照合する。[短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## ブラウザを変える箇所

計測側は `measure_worklet_live_song_cross_browser.py` の `capture()` にケースで指定したエンジンを渡す。Node側はPlaywrightのFirefoxで歌唱画面を開き、実時間ボタンを操作して観測JSON・再実行ケース・WAVを保存する。先行Workletへ渡る入力は全サンプル0、歌唱入力とWASM・辞書はChromiumのケースと同じ。両ブラウザのPCMは同じオフライン基準とのビット比較を行う。[ブラウザ起動と取得](../tools/measure_worklet_live_song_cross_browser.py#L29)・[起動比較](../tools/measure_worklet_live_song_app_silent_lead.py)・[画面の歌唱操作](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L1008)

先行枝の連続区間の先頭を `L`、先行量子数を `N`、歌唱Workletの初回を `V`、描画予約を `S` とする。通知位置は `L + N × 128`、歌唱側でフレームが飛ばなければ `S = V + 8 × 128 + 2,048`。各組の `S − L` の短縮を512フレームと照合し、誤差1量子を許容する。クリックと歌唱先頭はエポック時刻で測る。並列観測では歌唱Worklet出力を絶対フレームで採り、前後の無音と末尾を検査する。歌唱の初回と予約が同じページ内の時計にあるため、ブラウザのContext作成時からの経過を混ぜずに比較できる。[先行枝](../../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts)・[歌唱の予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)・[比較コード](../tools/measure_worklet_live_song_teeth_lowpass_floor.py#L23)

## 起動失敗と空の入力チャンネル

初回は既定キャッシュにPlaywrightの `firefox-1555` が存在せず、全16試行でブラウザの起動前に停止した。WASMと辞書の2件は照合できた。作業ディスクの既存ビルド `firefox-1555` を確認し、`CHIMERA_FIREFOX` で実行ファイルを指定した。実行ファイルはFirefox 157.0、アプリのビルドIDは `20261002115412`。ケースの判定条件は維持した。[起動失敗](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-a/manifest.json)・[エラーログ](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-a/artifacts/cargo.log)

実行ファイルを指定した修正前の16試行では、歌唱画面から先行Workletを登録できたが、4量子と8量子の各8試行とも通知がなく、約5秒で画面にエラーが出た。プレビューで同名の観測Workletを配信し、先頭16コールバックのフレーム番号・入力と出力の形状・0かどうかを記録した。Firefoxは連続した128フレームの出力を受け取ったが入力チャンネルが空で、Chromiumは全16コールバックに128フレームの0入力を受け取った。単独の `AudioBufferSourceNode → AudioWorkletNode → destination` でも、Firefoxのバッファ長128、129、256、512、1,024や、開始予定を現在・過去・1〜16量子先に変えた条件で空の入力が再現した。比較に使った0の `ConstantSourceNode` では128フレームの入力が届いた。[修正前の失敗](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-b/manifest.json)・[画面の形状観測](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-firefox-silent-lead-20261121-pilot/comparison.json)・[バッファ長の対照](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-firefox-silent-lead-20261121-pilot/loop-matrix.json)・[予定時刻の対照](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-firefox-silent-lead-20261121-pilot/schedule-matrix.json)

Playwrightの `addInitScript` で `AudioBufferSourceNode.prototype.buffer` の設定前または設定後に `buffer.getChannelData(0).fill(0)` を加える対照を行った。Firefoxでは設定後の変更は通知がなく、設定前に0で埋めると4量子と8量子とも通知・歌唱が完了した。Chromiumの設定前4量子も完了し、この予備試験で成功した3件のWAVは同じSHA-256だった。別途読んだ作業用Geckoソース `fdd757a2e0` では、`AudioBufferSourceNode::SendBufferParameterToTrack()` がバッファ設定時に `GetThreadSharedChannelsForRate()` を使う。チャンネル配列がまだ作られていなければ内部の取得が `nullptr` を返す。アプリは設定前に配列を作って0で埋めるよう変更し、先行枝への入力が128フレームの0であることを従来と同じ判定で確認する。[割り当て前後の対照](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-firefox-silent-lead-20261121-pilot/app-buffer-order.json)・[Geckoの受け渡し](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/webaudio/AudioBufferSourceNode.cpp#L729)・[配列の取得](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/webaudio/AudioBuffer.cpp#L422)・[アプリの修正](../../../../web/prototypes/chimera-research/src/song-silent-lead.ts#L13)

修正前の計測が読む配信先を保ち、`vite build --outDir` で修正版のプレビューを作業ディスクの別ディレクトリに生成した。修正版のFirefoxとChromiumで、4量子・8量子それぞれに歌唱出力の並列観測を1回実行した。全4試行で歌唱の開始待ちの飛びは0、並列観測448量子は連続し、49,200フレームのPCMのSHA-256も一致した。この予備試験は歌唱画面の短音プリセットと既定の乱流設定で行った。[修正版の予備試験](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-firefox-silent-lead-20261121-pilot/fixed-isolated-dist.json)

## 実測

修正後のFirefoxの正式な2実行で、4量子と8量子を各16試行、直接出力と並列観測を各16試行ずつ取得した。全32試行で、先行枝は最初に有効な入力が届いたフレームから通知まで連続した。先行枝の通知位置と歌唱Workletの初回は同じ絶対フレーム、歌唱開始はその3,072フレーム後だった。先行枝の連続区間先頭から歌唱開始までは4量子条件3,584フレーム、8量子条件4,096フレーム。全16組で短縮は512フレーム（10.67 ms）だった。[修正後の結果](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-c/summary.json)・[別ディレクトリからの再実行](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-repeat/summary.json)

| 4量子から8量子の時間を引いた差 | 組内差の中央値 | 範囲 |
| --- | ---: | ---: |
| クリックから歌唱先頭、直接出力8組 | −11.5 ms | −18〜+2 ms |
| クリックから歌唱先頭、並列観測8組 | −9.0 ms | −17〜+1 ms |

直接出力のクリック時間は8組中7組で短くなった。先行枝の接続直前から通知までは直接出力で4量子が10〜11 ms、8量子が21〜22 ms。定数512フレームの差は先行枝の通知を早めた分で、歌唱Worklet自身の開始待ちは両条件で同じだった。

Firefoxの保存WAV32件と以前のChromiumの32件を標準ライブラリで読み直し、全件が同じオフラインPCM49,200フレームにビット一致することを確認した。Firefoxの状態769点・歌唱計画も一致した。Firefoxの並列観測16試行では、予約位置の生PCM、歌唱前後の無音、末尾の補完80フレーム、フレーム列の連続性を確認した。固定上流との差は歯のフィルタ下限1,200 Hzの基準と同じで、最大差 `2.7573 × 10⁻³`、差が `10⁻⁶` を初めて超えた位置は27,939フレームだった。[固定上流とオフラインの照合](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)・[並列観測の例](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-repeat/artifacts/observed-1-four/output-probe.json)

同じ修正版をChromium 156.0.8078.4でも16試行した。全試行で歌唱側の開始待ちの飛びは0、PCMと状態・計画は基準と一致。直接出力4組のクリック時間の中央値は −9.5 msだった。先行枝の最初の有効入力から通知までに256フレームの有効入力が観測されなかった試行が12件あった。Chromiumでは通知位置から歌唱ノードの初回までも同じ12試行で128フレーム離れた。Firefoxの32試行ではどちらの差も0だった。Chromiumの先行枝で、欠けた256フレームにコールバック自体がなかったか、入力の有効条件に合わなかったかを次に調べる。音声機器からの出力、聴感、Safariは未検証。[同じ修正版のChromium](../runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-buffer-init/summary.json)

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_FIREFOX='/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox' \
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_app_silent_lead.py <実行ID> \
  --case cases/worklet-live-song-fast-app-silent-lead-firefox.json
```

macOS 15.6.1 arm64、Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。修正後の初回と `/private/tmp` からの再実行は各338件の取得判定・7予測を通過した。起動失敗と修正前の計測を含むFirefoxの4実行で入力1,146件・出力352件のサイズとSHA-256を確認し、大容量成果29.05 MBをRTL9210B-CGに保存した。固定上流の `cargo test --locked -p chimera --test engine output_does_not_depend_on_the_host_block_size` と `cargo test --locked -p chimera --test sing_fast fast_runs_land_on_the_beat` は、作業ディスクを `CARGO_TARGET_DIR` に指定し、各1件が通過した。[修正後マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-c/manifest.json)・[再実行マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-repeat/manifest.json)

Chromiumでは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python tools/measure_worklet_live_song_app_silent_lead.py <実行ID> --case cases/worklet-live-song-fast-app-silent-lead-four-quanta.json` を実行した。338件の取得判定と7予測が通過し、入力279件と出力132件のサイズとSHA-256を確認した。大容量成果12.81 MBを同じ作業ディスクに保存した。Firefoxの再実行とChromiumの保存ソースで、無音先行の実装ファイルのSHA-256が一致することも確認した。[Chromium再検証マニフェスト](../runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-buffer-init/manifest.json)
