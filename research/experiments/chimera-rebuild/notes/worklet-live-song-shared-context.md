# 先行音と同じFirefoxのAudioContextで歌唱ノードを構築する

192フレームの事前描画をすると歌唱の先頭量子は1.779〜1.866 msに収まった。構築の中央値は6.8〜6.9 msだった。この構築がすでに再生中の同じContextで先行音の処理間隔を広げるか、先行音の波形と時刻を対応づけて調べる。[単独歌唱の比較](worklet-live-song-render-warmup-frames.md)・[既存の96 kHz固定発声の方法](worklet-wasm-wrapper-shared-context.md)

## 読解

固定上流の `AudioEngine.build` はContextの再開を要求し、モジュールを登録し、コンパイル済みのWASMモジュールを渡してノードを構築する。構築成功後に既存エンジンを置き換え、出力先へつなぐ。`ChimeraProcessor` がインスタンスと発声ハンドルを作り、`process` が出力チャンネルの長さを `engine_render` に渡す。音声の状態はハンドルにあり、ホストが要求するフレームの分割を変えても固定フレームの操作が同じPCMを作ることを上流の試験が確認する。[上流のAudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[上流の分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補の `withRealtimeContext` は48 kHzのContextを再開し、準備したWASMモジュールと調音スコアを `captureWorklet` から歌唱ノードへ渡す。実験用の先行音は `AudioBufferSourceNode` から別の観測Workletに入れ、その出力を同じContextの出力へ接続する。入力をその量子の出力にコピーし、Context上のフレーム番号とコピーした `Float32` を保存する。先行音の予定開始を `s` フレームとしたとき、サンプル位置 `i` に期待する値は `((421 * (i - s) + 173) % 65521 - 32760) / 524288` を `f32` にした値。128フレームで量子が進むと観測フレームは毎回128増え、48 kHzでは量子当たりの時間は `128 / 48000` 秒となる。歌唱は別のノードから出力され、先行音はそのミックスより前で採取される。[候補のContextと出力](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[既存の先行音Worklet](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)

Geckoの `WorkletNodeEngine::CallProcess` は処理の区間にプロセッサー名を持つ。`WorkletNodeEngine::ProcessBlock` はその外側を囲み、`AudioWorkletGlobalScope::ConstructProcessor` はオプションの復元からJSコンストラクターまでを含む。先行音の各 `currentFrame` と呼び出しを同一スレッド上で対応づけ、隣接する外側の区間の開始時刻の差を取る。構築を含む差はコールバック開始の間隔であり、Web Audioグラフが複数量子を続けて処理するときの配分と構築処理の両方を含む。[Geckoの名前付き呼び出し](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletNode.cpp#1476)・[Geckoの構築区間](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletGlobalScope.cpp#1214)

## 事前登録

未準備と192フレームの事前描画を交互に4組採る。どちらも先行音を192量子以上採ってから歌唱を構築する。構築を含む先行音の隣接開始時刻の差を同じ組で引き、事前描画で中央値が2 ms以上増すと予測する。先行音512量子のPCMとフレーム列は基準の式に一致し、歌唱のPCMも基準と一致すると予測する。先頭2量子がともに2.667 ms以内の事前描画試行が4回中3回以上になることを確認する。時間の予測は生データを照合できたかどうかの判定と個別に記録する。[ケース定義](../cases/worklet-live-song-shared-context.json)

## 区間の対応

計測ページは通常の歌唱モジュールを登録する際に先行音を同じContextへ接続し、観測Workletから採取開始後192量子の通知を受けて歌唱側の登録待ちを解除する。先行音の `currentFrame` を記した印を `chimera-shared-context-marker` の `CallProcess` へ、歌唱のコールバックを `chimera-fixed-voice` の `CallProcess` へ対応づける。両方の名前付き区間を無記名の `ProcessBlock` に一意に対応づけ、起動待ちと先行無音の長さから歌唱の先頭2量子を特定する。前後の先行音の量子の範囲内に、同じContextフレームを報告する歌唱のコールバックがあることも確かめる。先行音の印は両条件で同じ頻度で記録する。[計測ページの接続](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)・[区間の照合](../tools/measure_worklet_live_song_shared_context.py)

## 結果

修正後と `/tmp` からの再実行で各133判定を通過した。表は各4試行の中央値を修正後、再実行の順に示す。[修正後の結果](../runs/worklet-live-song-shared-context-20261121-b/summary.json)・[再実行の結果](../runs/worklet-live-song-shared-context-20261121-repeat/summary.json)

| 条件 | 構築をまたぐ先行音の間隔（ms） | Worklet構築（ms） | 歌唱の先頭量子（ms） | 全歌唱量子が予算内 |
| --- | ---: | ---: | ---: | ---: |
| 未準備 | 6.777 / 6.641 | 1.481 / 1.308 | 3.652 / 3.630 | 0/4、0/4 |
| 192フレーム | 12.007 / 11.861 | 6.714 / 6.559 | 1.810 / 1.777 | 4/4、4/4 |

先行音の間隔は同じ組で引いた増分の中央値で5.221 ms、5.228 ms長くなった。各組でこの増分と構築時間の増分を比較すると、8組の差はすべて0.056 ms以内だった。構築をまたぐ間隔から構築時間を引いた残りは各試行で5.262〜5.356 msとなり、構築周辺を除く先行音のp99である5.314〜5.357 msに近い。事前描画の全8試行で歌唱の全量子が2.667 ms以内だった。[先行音の間隔と構築時間の対応](../runs/worklet-live-song-shared-context-20261121-repeat/summary.json)

先行音の65,536点と512件のフレーム番号は独立計算と一致した。歌唱のPCM全91,200点・音響観測1,425行・拍・調音計画も基準と一致した。拍の位置は独立計算の24,000と48,000に一致し、固定上流との差は最大2.3283064365386963×10⁻¹⁰、最初のビット差は出力フレーム4,114だった。固定上流の関連試験は各17件を通過した。[信号とタイミングの照合](../runs/worklet-live-song-shared-context-20261121-b/summary.json)

### 出力コールバックの予備照合

修正後と再実行のプロファイル16件を試読した。`AudioIPC Client Callback` と同じプロセスの `GraphRunner` を時刻で結ぶと、全16件で歌唱ノードの構築を含む `DataCallback` と、その内部の `GraphRunner::OneIteration` が各1件あった。予算マーカーの開始と `DataCallback` の開始との差は最大0.625 µs。記録された予算5.333 msに対し、構築を含む `DataCallback` は未準備の8試行で1.283〜2.225 ms、事前描画の8試行で6.600〜6.958 msだった。この照合は事前登録の比較に含めていなかった。次は出力側の要求フレーム数、コールバックの開始間隔、構築前後に渡したバッファの時刻と波形を照合する。機器からの出力の欠落や聴感は未測定。[Geckoの出力コールバックと予算マーカー](https://searchfox.org/firefox-main/source/dom/media/GraphDriver.cpp#2328)

## 再現と保存

以下を研究ワークスペースで実行する。先行音の波形は `marker.f32le.gz`、採取したContextフレームは `marker.json`、ネイティブの生プロファイルは `firefox-profile.json.gz` にある。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  CHIMERA_FIREFOX='/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox' \
  ../../.venv/bin/python tools/measure_worklet_live_song_shared_context.py worklet-live-song-shared-context-next
```

初回は、時刻の比較から返ったNumPyの真偽値を結果のJSONに書き出せず、要約の保存に失敗した。比較結果をPythonの真偽値にして修正した。初回の判定と採取した波形・観測・プロファイルは保持した。[初回実行のマニフェスト](../runs/worklet-live-song-shared-context-20261121-a/manifest.json)

初回の生データを修正後の計測関数と独立計算で読み直し、133判定をすべて照合できた。主比較3実行の24試行で先行音が独立計算とビット一致し、24本の歌唱WAVが基準ファイルとバイト単位で一致した。96 kHzの共有Context固定発声と先行音を加えない歌唱区間計時は166判定と58判定を通過した。macOS 15.6.1 arm64、Headless Firefox 157.0、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4で採取した。入力1,366件と出力326件のSHA-256を照合し、5実行の成果約107.75 MBをRTL9210B-CGに保存した。[修正後](../runs/worklet-live-song-shared-context-20261121-b/manifest.json)・[再実行](../runs/worklet-live-song-shared-context-20261121-repeat/manifest.json)・[固定発声の回帰確認](../runs/worklet-wasm-wrapper-shared-context-20261121-song-regression/manifest.json)・[先行音を加えない歌唱の回帰確認](../runs/worklet-live-song-render-phases-20261121-shared-context-regression/manifest.json)
