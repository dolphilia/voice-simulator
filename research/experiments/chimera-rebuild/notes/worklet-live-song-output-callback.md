# Firefoxの出力要求と歌唱ノード構築の時間を対応づける

共有Contextに192フレームの事前描画をする歌唱ノードを追加したとき、先行音のコールバック間隔は構築時間の増分に近い約5.2 msだけ延びた。予備照合では歌唱ノード構築を含むFirefoxの出力コールバックが5.333 msの予算を超えた。今回は出力要求のフレーム数、対応するグラフ反復と先行音のフレーム位置、後続の要求が始まる時刻を並べる。[共有Contextの前回の結果](worklet-live-song-shared-context.md)

## 読解

固定上流の `AudioEngine.build` はAudioContextでWorkletを登録し、WASMモジュールを渡してノードを構築する。`ChimeraProcessor.process` は出力チャンネルの長さを `engine_render` に渡す。`Engine::render` は累計出力位置 `pos` と `pos % SUB_BLOCK` を使い、128フレーム境界でビートの予約を更新してから音声を進める。上流の `output_does_not_depend_on_the_host_block_size` は絶対フレームに同じ操作を与え、ホストの分割長を変えた出力のビット一致を確かめる。候補の歌唱側は出力128フレームが2.667 msに当たり、観測の64フレーム境界でWASMのレンダーを区切る。[上流のノード生成](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Geckoの `AudioCallbackDriver::DataCallback_s` は、cubebが渡した `aFrames` と出力バッファを `DataCallback` に渡す。`DataCallback` は残りのサンプルをバッファに入れ、残りの要求と `mStateComputedTime` を足した位置をWeb Audioブロック境界へ切り上げてグラフを進める。`MixerCallback` は要求分をバッファへ書き、ブロックの余りを `mScratchBuffer` に保持する。`GraphRunner::OneIteration` はAudioIPC側からグラフスレッドを起こし、反復の完了を待つ。呼び出し側の待機区間の内側にグラフの処理区間があり、歌唱ノードの構築もそのグラフ内で起こる。[要求と予算](https://searchfox.org/firefox-main/source/dom/media/GraphDriver.cpp#2328)・[グラフとバッファの更新](https://searchfox.org/firefox-main/source/dom/media/GraphDriver.cpp#2508)・[バッファへの書き込み](https://searchfox.org/firefox-main/source/dom/media/GraphDriver.cpp#2834)・[グラフ実行側への引き渡し](https://searchfox.org/firefox-main/source/dom/media/GraphRunner.cpp#615)

`AudioCallbackDriver real-time budget` の長さは `aFrames / sampleRate`、グラフの `MTG graph advance` は反復で進めるフレームの `aStateTime - mStateComputedTime` をサンプルレートで割った時間。記録ではマイクロ秒単位に整数化される。48 kHzの1フレームは約20.833 µsなので、マーカー長から最も近い整数フレームを求め、時間へ戻した誤差を確認できる。先行音プロセッサーの `currentFrame` 印でもグラフ反復内の128フレーム量子を数える。Geckoの波形ダンプは出力バッファにアクセスする別の診断経路であり、今回のプロファイルに波形は含まれない。[グラフ前進の計測点](https://searchfox.org/firefox-main/source/dom/media/MediaTrackGraph.cpp#3648)・[計時マーカーの単位](https://searchfox.org/firefox-main/source/dom/media/AsyncLogger.h#1240)・[WAVダンプの条件と量子化](https://searchfox.org/firefox-main/source/dom/media/WavDumper.h#892)

## 事前登録

保存済みの再実行の第1組を予備に読み、192フレーム条件では構築を含む要求の次の開始が12.52 ms後、その後は次々に約5.33 ms間隔だった。未準備では直後も5.34 ms間隔だった。正式比較は同じケースの保存2実行と追加の採取を分けて集計する。構築の前後8要求で要求フレーム、グラフが進めたフレーム、先行音のフレーム位置を照合する。事前描画の少なくとも3/4試行で、予算超過、直後の2 ms以上の開始遅れ、後続の間隔の中央値誤差0.25 ms以内、8回先でも2 ms以上の開始のずれを予測する。[ケース定義](../cases/worklet-live-song-output-callback.json)

## 結果

保存済みの16試行と新規採取の8試行で、構築前後の408要求を照合した。すべて256フレームの要求に対し、グラフは連続する128フレームの先行音量子を2個ずつ処理した。窓全体で要求とグラフ前進の累計フレームは一致した。先行音各65,536点とフレーム位置は独立計算と一致し、24本の歌唱WAVはCLI基準とバイト単位で一致した。音響観測1,425行・歌詞の調音計画・拍も一致した。[全要求の照合結果](../runs/worklet-live-song-output-callback-20261121-a/summary.json)

| 採取元 | 未準備の構築を含む処理（ms） | 192フレームの構築を含む処理（ms） | 192フレームで次の開始のずれ（ms） | 192フレームで8回先の開始のずれ（ms） |
| --- | ---: | ---: | ---: | ---: |
| 保存・修正後 | 1.678 | 6.819 | 7.278 | 7.260 |
| 保存・別ディレクトリからの再実行 | 1.426 | 6.656 | 7.102 | 7.093 |
| 新規採取 | 1.877 | 7.243 | 5.338 | 5.349 |

表は各条件4試行の中央値。未準備の次の開始は予定の−0.026〜+0.030 msに収まった。事前描画の次の開始は構築を含む要求の開始から10.64〜12.76 ms後で、256フレーム分の予定に対して5.31〜7.43 ms遅れた。その後の開始間隔は5.333 msに戻り、各試行で間隔誤差の絶対値の中央値は0.020 ms未満だった。8回先の開始時刻には5.32〜7.40 msのずれが残った。事前描画の12試行すべてで4つの予測を満たし、予備に読んだ1組を除いても結果は同じだった。[条件別の開始時刻と予算差](../runs/worklet-live-song-output-callback-20261121-repeat/summary.json)

新規採取の事前描画4試行では次の開始がほぼ2要求分の時刻に揃い、保存済みの事前描画8試行では2要求分をさらに1.60〜2.10 ms超えた。構築を含むコールバックは事前描画で6.600〜9.226 ms。最長の9.226 msを記録した試行では、その内側の構築に9.086 msかかった。構築を含む要求以外の処理は比較したすべての窓で予算内だった。Firefoxのグラフでは経過時刻のずれとフレームの連続性を区別できた。音声機器への出力の欠落は未測定。[要求ごとのフレーム、コールバック、グラフ反復の時刻](../runs/worklet-live-song-output-callback-20261121-a/summary.json)

## 再現と保存

研究ワークスペースで次を実行する。新規採取実行には未使用のIDを使う。解析は保存済みの生プロファイル、参照波形、歌唱レポートを入力とし、各入力を元の実行のマニフェストで検証する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  CHIMERA_FIREFOX='/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox' \
  ../../.venv/bin/python tools/measure_worklet_live_song_shared_context.py worklet-live-song-output-fresh-next

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 \
  ../../.venv/bin/python tools/measure_worklet_live_song_output_callback.py worklet-live-song-output-analysis-next \
  --fresh-run worklet-live-song-output-fresh-next
```

macOS 15.6.1 arm64、Headless Firefox 157.0（BuildID `20261002115412`）、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4で新規採取を行った。新規採取は133判定と固定上流試験17件を通過した。解析は通常の作業ディレクトリと `/tmp` からの実行で各242判定を通過し、結果のJSONまでバイト単位で一致した。3実行の入力558件と出力79件のハッシュを照合した。新規採取の成果約26.7 MBをRTL9210B-CGへ保存し、解析実行では参照する生データのハッシュを記録した。[新規採取](../runs/worklet-live-song-shared-context-20261121-output-fresh/manifest.json)・[解析](../runs/worklet-live-song-output-callback-20261121-a/manifest.json)・[別ディレクトリからの再解析](../runs/worklet-live-song-output-callback-20261121-repeat/manifest.json)
