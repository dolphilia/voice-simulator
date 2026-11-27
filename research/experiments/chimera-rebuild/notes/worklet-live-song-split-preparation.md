# Firefoxの歌唱開始前の無音量子に事前描画を分ける

48 kHzの共有AudioContextに `Pop Dee` の歌唱ノードを追加する。構築時に192フレームを連続描画したとき、試験用FirefoxがCore Audioへ返す先行音のPCMは連続したが、構築を含む256フレーム要求を処理しきれず、次の予定サンプル時刻は256フレーム飛んだ。先行音と歌唱を揃え、無音量子に同じ描画を移す条件を登録した。[前回の実測](worklet-live-song-cubeb-output.md#試験用firefoxの実測)・[事前登録](../cases/worklet-live-song-split-preparation.json)

## 上流の描画経路

- 固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` は、レートをHzで指定してContextを生成し、`addModule()` の後にコンパイル済みモジュールを `processorOptions` で渡す。`ChimeraProcessor` の構築時にモジュールをインスタンス化し、`engine_new(sampleRate)` で発声状態を1つ作る。`process()` は実際に渡された出力チャンネルの長さをフレーム数として `engine_render()` を呼ぶ。共有メモリから先頭チャンネルにfloat32 PCMを移し、ほかのチャンネルにも複製する。負荷比は、処理時間のmsを `1000 × フレーム数 ÷ サンプルレート` で割った値を平滑化して求める。[AudioEngine.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts)・[processor.ts](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[WASMのABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)
- `Engine::render()` は累積出力フレーム `pos` の128フレーム境界でシーケンサーを更新する。残りを境界までの長さで切って人またはクリーチャーの発声を進め、描画した長さだけ `pos` を加算する。人の `HumanVoice::render()` では1出力フレームごとに内部計算を `m` 回行う。このケースの48 kHzでは `m = floor(60,000 ÷ 48,000) + 1 = 2`。調音制御、肺側の圧・流量、声門開口、声道の音響網、間引きとDC除去を順に進める。`output_does_not_depend_on_the_host_block_size()` は同じ絶対フレームでコマンドを適用し、1、77、4096、48000フレームずつ描画した結果が128フレームずつ描画した結果とビット一致することを検査する。[engine.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[human_voice.rs](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs)・[エンジンのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

## 比較の設計

試験オプション `songRenderPreparation=split-192` はWASMインスタンスを歌唱本番と共用し、同じスコアを別ハンドルで初期化する。出力フレームを要求する `vocal_render()` は0フレームを入口で拒否するため、最初に同じラッパーを1,000回通しても状態は進まない。その後、先行無音の最初の量子と、そこから256、512コンテキストフレーム後に64フレームずつ進める。使い捨てPCMはハンドル内に留まり、3回目にそのハンドルを解放する。実際の歌唱は、8量子の連続確認と2,048フレームのリードを経た予定フレームから、初期状態のまま描画する。[WASMのABI](../crates/vocal-wasm/src/lib.rs)・[TypeScriptホスト](../crates/vocal-wasm/host/fixed-voice.ts)・[Workletの条件分岐](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[実時間歌唱ケース](../cases/worklet-live-song.json)

先行音が192量子以上鳴った後の構築を中心とし、前後各8要求に含まれる4,352フレームを照合する。各分割区間は開始・終了マーカーと累積描画フレームから実在を検査する。Firefoxが記録したグラフ反復に分割区間を対応づけ、左右逆相の先行音を独立計算して、Core Audio側で採取したPCMと同じ要求を特定する。歌唱の予算は128 ÷ 48,000秒、機器からの要求の予算は256 ÷ 48,000秒。歌唱先頭の短縮と構築から第3片までの各要求の予算、サンプル時刻とホスト時刻、先行音のPCMを別々に判定する。[既存の出力窓検証](../cases/worklet-live-song-cubeb-output.json)・[解析](../tools/inspect_firefox_cubeb_output.py)

## 実測

macOS 15.6.1 arm64で、cubeb計測付きNightly 157.0、Playwright 1.64.1、Node v24.19.0、Bun 1.4.4を使用した。初回と、共有Contextのグラフ反復とPCM位置の照合を厳密にして `/private/tmp` から実行した再試行は、各6試行で各109判定と固定上流の17テストを通過した。4組とも下表の傾向が再現した。[初回](../runs/worklet-live-song-split-preparation-20261121-a/summary.json)・[再試行](../runs/worklet-live-song-split-preparation-20261121-repeat/summary.json)

| 条件（各4試行） | 構築区間 | 構築を含むcubebコールバック | 機器のサンプル時刻の飛び | 歌唱の先頭量子 |
| --- | ---: | ---: | ---: | ---: |
| 未準備 | 1.16〜1.27 ms | 1.30〜1.46 ms | 0フレーム | 3.57〜3.68 ms |
| 構築中に192フレームを描画 | 6.38〜6.68 ms | 6.51〜6.83 ms | 256フレーム | 1.72〜1.80 ms |
| 64フレームずつ無音中に分割 | 1.69〜1.82 ms | 3.54〜3.80 ms | 0フレーム | 1.68〜1.82 ms |

第1片は4試行とも構築と同じ要求に入り、第2・第3片は続く別々の要求に入った。第2片を含む要求は1.68〜1.75 ms、第3片を含む要求は1.49〜1.60 ms。分割は構築をまたぐ要求から第3片まで全て5.333 ms以内で、前後8要求の窓内で機器のサンプル時刻とホスト時刻が連続した。分割時の歌唱の先頭2量子は全試行で2.667 ms以内で、歌唱を通して予算を超えた量子も0だった。未準備では毎回先頭の1量子が予算を超えた。

全12試行の歌唱WAVは保存済みの再実装基準とバイト一致し、全91,200サンプル、観測1,425行、拍、調音計画と開始条件の照合を通った。固定上流と異なる最初のビットは各条件に共通して出力フレーム4,114にあり、最大絶対誤差は2.329 × 10⁻¹⁰で、許容幅を超えたサンプルはなかった。先行音のcubeb PCMは全試行で独立計算した4,352フレームの連番と一致した。欠落、繰り返し、無音は各0だった。

分割の第1片は構築と同じ要求の残り予算を使う。次の小さな実験では、先行音を揃えたまま第1片だけを次の機器要求へ送る条件を用意し、構築を含む要求と第1片を含む要求の最大所要時間を比べる。機器から出た音は、既知PCMの校正を通過したプロセスタップで確認する工程が残る。現在の結果は48 kHz・256フレームの要求で得た。[同時観測の記録](worklet-live-song-paired-output.md)

## 再現

手元の試験用FirefoxのXULハッシュを計測の実行記録と照合する。コマンドは研究ワークスペースから実行する。`<実行ID>` には未使用の名前を指定する。

```bash
firefox=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_shared_context.py <実行ID> \
  --split-preparation --cubeb-output "$firefox"
```
