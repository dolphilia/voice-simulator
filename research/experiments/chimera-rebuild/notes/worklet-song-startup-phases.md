# 実時間歌唱を開始するまでの処理時間

## 固定上流と候補の経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `playTune` は音声の準備を待ち、`EnglishG2P.load` で辞書を読み、音節とMIDIを歌唱計画に渡す。辞書はロードしたWASMのページ内の状態に残り、`AudioEngine.build` は初回にContextを作ってすぐに `resume` を開始し、Worklet登録・ノード生成・接続へ進む。歌唱の予定は `AudioEngine.schedule` から既存エンジンの時計に載せる。`fast_runs_land_on_the_beat` は母音核が予定拍に来る条件、`output_does_not_depend_on_the_host_block_size` はホスト分割に対するPCMの不変性を調べる。[上流の歌唱入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[辞書を保持する入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/engine.ts#L76)・[上流のContext準備](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[歌唱の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)・[ホスト分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補の `SongPanel.run` は `Pop Dee` と各1拍のMIDI 60・69を `renderRealtimeSongVoice` に渡す。`withRealtimeContext` は48 kHzでContextを作り、`loadFixedModule` と `resume` を並行して待つ。`loadDictionary` は展開済みの辞書バイト列をページ内で保持する。歌詞を渡すたびに `planSong` は新規WASMインスタンスにJSONと辞書をコピーする。`prepare_song` が辞書のTSVから語と発音を取り出し、音節を選んでから調音ジェスチャーを計画する。構造化音節を渡す場合はその音節からジェスチャーを作る。拍は `先頭の拍 + 先行音符の拍数の合計 × 60 / BPM` 秒。120 BPMの今回の拍は0.5秒と1秒である。[候補のContextと歌唱準備](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[WASMホスト](../crates/vocal-wasm/host/planning.ts)・[WASMの計画入口](../crates/vocal-wasm/src/planning.rs#L313)・[辞書のTSV処理](../crates/vocal-core/src/phonetics/english.rs#L47)

`captureWorklet` は `audioWorklet.addModule`、ノード構築、`connect` の順に進む。`RealtimeSpeechCapture` はWorklet側の `currentFrame` で起動時の連続性を確かめ、確定位置に2,048フレームを足して描画を予約する。メインスレッドは `performance.now()` のミリ秒と `round(context.currentTime × sampleRate)` を同じ印に記録する。Context上の最初のWorkletフレームと接続時点に読んだContext時刻は別の位置であり、メッセージ伝達と量子境界の影響を受ける。経過時間の集計ではWASMと再開を重ねて表示し、両方を待ち終えた時点までの一区間として足す。[接続と計測](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[Worklet側のフレーム観測](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[集計コード](../tools/measure_worklet_song_startup.py)

## 事前登録と対照

各ブラウザの新しいページで、歌詞の入力エラーから復帰する従来経路を計時の有無で比べる。さらに、有効な歌詞を最初に入力する条件と、同じ2音節の確定済みJSONを最初に入力する条件を計時する。後者の音節は、CLI・上流・オフラインとの比較に合格した `worklet-live-song-cross-browser-20261121-a` からハッシュを検査して取得する。試行順を変えて各条件3回ずつ実時間歌唱を採り、停止・再開とオフラインの照合は別の検査で実行する。予測は辞書が取得済みの条件でブラウザの接続までの時間差の半分以上を計画WASM呼び出しの差が占め、未取得歌詞から構造化音節に替えると同呼び出し時間が80%以上短くなるというもの。計時で予定開始・最初のコールバックの中央値が動く範囲を1,024フレーム以内とし、PCM、音響観測、予定拍は既存基準に照合する。[事前登録](../cases/worklet-song-startup-phases.json)・[基準実行](../runs/worklet-live-song-cross-browser-20261121-a/manifest.json)

## 初回の比較

FirefoxとChromiumの全24試行で、加工前PCM 91,200点と音響観測1,425行がCLIと照合済みの基準にビット一致した。歌詞・構造化音節の入力は各条件の指定値と一致し、その後の音節・予定拍・ジェスチャーは同じだった。固定上流PCMとの差は最大2.33×10⁻¹⁰で既存の許容差内。上流の17試験は再実行で通過した。[初回の全判定](../runs/worklet-song-startup-phases-20261121-a/summary.json)・[上流試験ログ](../runs/worklet-song-startup-phases-20261121-a/artifacts/upstream-tests.log)

辞書取得済みの計時では、Context作成から接続までの中央値がChromium 54.9 ms、Firefox 206 ms。差151.1 msのうち、歌唱計画のWASM呼び出しの差は2.1 ms（1.4%）で、半分以上という予測には届かなかった。並行準備の差は127.4 ms。ChromiumではWASMが、FirefoxではContextの `resume()` が最後に完了した。Firefoxの再開の中央値は147 msだった。各区間の中央値は別々に集計しているため、区間の差の和と総時間の差には端数以外のずれも生じる。[境界別の中央値と全観測](../runs/worklet-song-startup-phases-20261121-a/summary.json)

未取得の歌詞と確定済み音節を比べると、計画のWASM呼び出しはChromiumで27.8から6.2 ms（77.7%減）、Firefoxで24から記録上0 msに短縮した。Firefoxの値はブラウザ時計の分解能以下を含む。WASMへの辞書コピーと呼び出し後の計画読み出しは別の印で採った。呼び出し内の辞書解析、音節化、メモリ管理の時間の内訳までは分けていない。[歌詞と音節の対照](../runs/worklet-song-startup-phases-20261121-a/summary.json)

初回は123/125判定。Firefoxの辞書取得済みの対照で、最初のWorklet呼び出しと予定開始の中央値が計時ありで各1,536フレーム（32 ms）早く、上限1,024フレームの2判定を通過しなかった。ラウンド別の最初の呼び出しは、計時ありからなしを引いて−384、+1,024、−1,792フレームで、変化の向きは揃わなかった。開始時刻のばらつきと計時自体の寄与をこの3対から分離できないため、その判定を保存した。[計時の対照](../runs/worklet-song-startup-phases-20261121-a/summary.json)

## 別ディレクトリからの再実行

`/tmp` で再実行した24試行は125/125判定。計時ありとなしで、最初のWorklet呼び出しの中央値差はChromium 256フレーム、Firefox 128フレームだった。予定開始の差は各0、128フレーム。初回と再実行の展開済みWAV 48本が同じバイト列で、音響観測・音節・ジェスチャー・拍も一致した。[再実行の各判定](../runs/worklet-song-startup-phases-20261121-repeat/summary.json)

辞書取得済みのFirefoxで、接続までの待ちが長く現れる区間が入れ替わった。再開と登録を個々の試行で足してから中央値を取ると、Firefoxは初回179 ms、再実行177 msだった。Chromiumは同じ定義で8.7 msと8.8 ms。Firefoxの再開と登録それぞれに共通する待ちがあるかは、今回の計測からは確定しない。[初回の区間値](../runs/worklet-song-startup-phases-20261121-a/summary.json)・[再実行の区間値](../runs/worklet-song-startup-phases-20261121-repeat/summary.json)

| 辞書取得済みの計時の中央値 | Chromium 初回 / 再実行 | Firefox 初回 / 再実行 |
| --- | ---: | ---: |
| Context作成から接続まで | 54.9 / 53.2 ms | 206 / 202 ms |
| Context再開 | 0.4 / 0.4 ms | 147 / 20 ms |
| Worklet登録 | 8.3 / 8.4 ms | 25 / 149 ms |
| 歌唱計画のWASM呼び出し | 23.9 / 23.0 ms | 26 / 25 ms |

再実行で接続までの差は148.8 ms、計画WASM呼び出しの差は2.0 ms（1.34%）だった。未取得の歌詞から確定済み音節に替えると、計画WASM呼び出しはChromiumで76.6%減、Firefoxで95.7%減。80%減の予測は二回ともFirefoxで成立し、Chromiumでは76.6〜77.7%に留まった。歌唱のPCMを維持したまま辞書を経由する計画の費用は減った。ブラウザ間の大きい差は、今回の条件ではContext再開とWorklet登録の周囲に現れた。次は固定上流と同様に再開を要求した直後からWorkletを登録し、現行の順序と同じ歌唱で比べると、待ちが重なるかを検証できる。[再実行の数値と予測の判定](../runs/worklet-song-startup-phases-20261121-repeat/summary.json)・[固定上流の待ち方](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L112)

## 再現と保存

研究ワークスペースで以下を実行する。`/tmp` からの再実行には同じPythonとスクリプトを絶対パスで指定した。初回と再実行の各150成果についてサイズとSHA-256を照合した。圧縮した観測・音声などの実体約30.35 MBはRTL9210B-CGに保存した。計測の端点はメインスレッドの経過時間とWorkletのフレームで、音の物理的な到達時刻や出力の途切れは未測定。[初回のマニフェスト](../runs/worklet-song-startup-phases-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/worklet-song-startup-phases-20261121-repeat/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=160000000 \
  ../../.venv/bin/python tools/measure_worklet_song_startup.py worklet-song-startup-phases-next
```

従来の `node tools/capture-worklet.mjs` の歌唱ケースをChromiumで実行し、実時間・オフラインの出力と停止後の再開を照合した。`Content-Encoding` なしのgzip辞書も同じハッシュで受け取り、計時を指定しない観測JSONには開始計時の項目がなかった。再実行が出力した音節ケースは `vocal-cli render-pcm <音節ケース> <出力> --no-trace 128` でも描画し、歌詞入力のCLI WAVとバイト一致した。[歌唱の採取入口](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs)・[音節ケース](../runs/worklet-song-startup-phases-20261121-repeat/artifacts/syllables-case.json)
