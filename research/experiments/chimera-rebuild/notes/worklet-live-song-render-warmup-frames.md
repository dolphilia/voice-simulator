# Firefoxの歌唱開始に必要な事前描画フレーム数

前回は256フレームを事前描画すると、Firefoxの歌唱の先頭量子のWASM時間が3.39〜3.42 msから1.42 ms前後に下がった。構築時間の中央値は6.64〜6.75 ms増えた。量子内の計時マーカーが第2量子の予算超過回数に影響したため、今回はネイティブの区間だけで本番の描画時間を測る。事前描画の長さだけを変え、構築中に使い捨て状態を進める時間と本番の先頭2量子を比較する。[256フレームでの区間計時](worklet-live-song-render-warmup.md)・[量子内マーカーの比較](worklet-live-song-render-phases.md)

## 呼び出しと制御周期

固定上流の `ChimeraProcessor.process` は出力チャンネルの長さを `engine_render` に渡し、返ったPCMをチャンネルへコピーする。`Engine::render` は出力位置 `pos` を状態として持ち、`pos % 128 == 0` でビートの予約を更新する。`HumanVoice::render` は内部倍率を `m` として、出力1点につき内部で `m` 回進み、`64 * m` 内部サンプルごとに調音と呼気を更新する。その後、肺圧と声門面積を更新して声道を進め、放射を間引いて出力する。末尾では出力ゲイン、DC除去、振幅の制限を適用する。上流の `output_does_not_depend_on_the_host_block_size` は、操作位置を固定してホストの要求長1、77、128、4,096、48,000で出力がビット一致することを確かめている。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L192)・[Engine::render](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[HumanVoice::render](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補の `FixedProcessor` は48 kHzで128フレーム、約2.667 msの量子を受け取る。64フレームの観測境界で `renderInto` を呼び、`vocal_render` が内部96 kHzのサンプルを進め、PCMと最後の観測を書き出す。出力フレーム64につき制御は1回更新され、観測には累計フレーム、声門面積（cm²）、声門流量（cm³/s）、F0（Hz）などが入る。0フレーム呼び出しは状態を進めずに戻る。準備対象の状態は本番と同じスコアで開始し、実験で指定されたフレーム数を描画して解放する。その後、同じWASMインスタンスで本番状態を新しく作る。最初の制御更新は出力時刻0秒から始まり、64フレーム分は48 kHzで約1.333 msに相当する。[描画の分割](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[WASMの入口](../crates/vocal-wasm/src/lib.rs#L775)・[状態の作成と解放](../crates/vocal-wasm/host/fixed-voice.ts)

## 事前登録

未準備、64、128、256出力フレームを4組で対照する。事前描画の3条件では64フレームごとの同じABIを使い、0フレーム呼び出し回数もそろえる。先頭2量子を両方2.667 ms以内に収めた試行が4回中3回以上ある最短の長さを求める。128フレームで達成し、64フレームでは達成しないと予測する。128フレームの構築区間は、同じ組の256フレームより差の中央値で0.5 ms以上短いと予測する。量子内と先行無音で計時印を追加せず、Geckoの `WorkletNodeEngine::ProcessBlock` を外側の区間として使う。準備の印はコンストラクター内で照合する。[ケース定義](../cases/worklet-live-song-render-warmup-frames.json)・[Geckoの描画区間](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletNode.cpp#841)・[Geckoの構築区間](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletGlobalScope.cpp#1214)

## 計測の対応

画面の実時間歌唱に使う `songRenderPreparation` でフレーム数を選ぶ。使い捨て状態の処理が完了した後でフレーム数・ブロック長・0フレームの呼び出し回数を印に記録する。構築全体、描画開始と終了、使い捨て状態の解放を同じ `GraphRunner` の時刻で照合する。本番の区間は、起動待ち量子と先行無音量子の数を除いて、出力フレーム0、128以降に対応づける。`CallProcess` が該当する `ProcessBlock` 内に収まることを全コールバックで検査する。物理機器の出力時刻はこの対応に含まれない。[歌唱の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[印を入れる箇所](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L65)・[計時と比較のコマンド](../tools/measure_worklet_live_song_render_phases.py)

拍の位置は、音符の前までの累計拍数を `B`、テンポを `bpm`、譜面の開始時刻を秒で `s` として `round(48000 * (s + 60 * B / bpm))` で独立計算する。今回の2拍は出力フレーム24,000と48,000に対応する。観測の行番号を1始まりの `i` とすると、観測位置は `64 * i - 1`、状態に記録される累計は `64 * i` となる。使い捨て状態のフレームが本番に加算されていれば、この対応とPCMに差が生じる。[音符とテンポの入力](../cases/song-voice-long.json)・[CLIと通常ブラウザの基準](../runs/worklet-live-song-cross-browser-20261121-a/manifest.json)

## 64・128・256フレームの比較

初回と `/tmp` からの再実行は各157判定を通過した。時間の表は各4試行の中央値を初回、再実行の順に示す。[初回の結果](../runs/worklet-live-song-render-warmup-frames-20261121-a/summary.json)・[再実行の結果](../runs/worklet-live-song-render-warmup-frames-20261121-repeat/summary.json)

| 事前描画 | 先頭量子（ms） | 第2量子（ms） | Worklet構築（ms） | 先頭2量子とも予算内 |
| --- | ---: | ---: | ---: | ---: |
| 未準備 | 3.631 / 3.622 | 2.591 / 2.571 | 1.193 / 1.198 | 0/4、0/4 |
| 64フレーム | 3.241 / 3.226 | 1.871 / 1.869 | 3.614 / 3.594 | 0/4、0/4 |
| 128フレーム | 2.834 / 2.764 | 1.441 / 1.443 | 5.204 / 5.118 | 0/4、0/4 |
| 256フレーム | 1.662 / 1.636 | 1.360 / 1.332 | 7.750 / 7.659 | 4/4、4/4 |

128フレームの事前描画で先頭2量子が予算内に入るという予測は外れた。最初の量子は128フレーム条件で2.723〜2.923 ms、第2量子は全条件が2.667 ms以内だった。256フレーム条件の8試行では先頭2量子を含む全量子が予算内だった。Worklet構築は、256フレームより128フレームの方が同じ組の差の中央値で2.57 ms、2.55 ms短かった。冒頭32量子を除くp99の条件別中央値は1.69〜1.73 msに収まった。[量子ごとの予算超過と予測の判定](../runs/worklet-live-song-render-warmup-frames-20261121-repeat/summary.json)

## 192フレームの追加比較

各64フレームで調音制御を1回進めるため、128と256の間には192フレーム、3回の制御更新がある。この条件を追加登録し、256フレームとの交互比較を行う。128フレームで残った最初の量子の余分な処理が、3回目の描画を追加すると変わることを予測した。先頭2量子が予算内の試行が4回中3回以上になり、構築時間が同じ組の差の中央値で0.5 ms以上短くなるかを判定する。[192フレームの事前登録](../cases/worklet-live-song-render-warmup-intermediate.json)

初回と `/tmp` からの再実行は各81判定を通過した。192フレームの先頭量子は1.779〜1.866 ms、全8試行で全量子が2.667 ms以内だった。256フレームも全8試行で全量子が予算内。192フレームの構築時間の中央値は初回6.805 ms、再実行6.899 msだった。同じ組で256フレームから引いた構築時間の差の中央値は1.169 msと1.052 msで、登録した0.5 ms以上の短縮を両方で満たした。[追加比較の初回](../runs/worklet-live-song-render-warmup-intermediate-20261121-a/summary.json)・[追加比較の再実行](../runs/worklet-live-song-render-warmup-intermediate-20261121-repeat/summary.json)

この歌唱で、観測と同じ64フレーム刻みのなかで予算を満たした最短は192フレームだった。64・128フレームでも第2量子は短縮したが、最初の量子に負荷が残った。192フレームで先頭量子を短縮できても、構築に中央値で約6.8〜6.9 msかかる。次はFirefoxの48 kHzで基準音を鳴らし続けるContextに歌唱ノードを追加し、未準備と192フレームで構築をまたぐ基準音の波形とコールバック間隔を照合する。WASM内部で先頭だけ重くなる原因、機器への出力遅延と人による試聴は未確認。[先行音が鳴るContextの測り方](worklet-wasm-wrapper-shared-context.md)

## 再現と保存

研究ワークスペースから、空いている実行IDで試す。4条件の比較には `--warmup-frames`、追加の2条件には `--warmup-intermediate` を使う。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 \
  CHIMERA_FIREFOX='/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox' \
  ../../.venv/bin/python tools/measure_worklet_live_song_render_phases.py --warmup-frames worklet-live-song-render-warmup-frames-next

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 \
  CHIMERA_FIREFOX='/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox' \
  ../../.venv/bin/python tools/measure_worklet_live_song_render_phases.py --warmup-intermediate worklet-live-song-render-warmup-intermediate-next
```

macOS 15.6.1 arm64、Headless Firefox 157.0、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4で実行した。比較の4実行では固定上流の関連試験が各17件を通過した。PCM、観測JSON、Firefoxプロファイルを可逆圧縮した。比較の成果約129.24 MBを作業用ディスクのRTL9210B-CGに書き出し、内蔵側にマニフェストと判定の要約、ソースのスナップショットを置いた。[4条件の初回](../runs/worklet-live-song-render-warmup-frames-20261121-a/manifest.json)・[4条件の再実行](../runs/worklet-live-song-render-warmup-frames-20261121-repeat/manifest.json)・[追加比較の初回](../runs/worklet-live-song-render-warmup-intermediate-20261121-a/manifest.json)・[追加比較の再実行](../runs/worklet-live-song-render-warmup-intermediate-20261121-repeat/manifest.json)

PCM全91,200点、観測1,425行、調音計画、拍、辞書、WASMは基準と一致した。固定上流との最大PCM差は全試行で2.3283064365386963×10⁻¹⁰、最初のビット差は出力フレーム4,114だった。以前の `songRenderPreparation=zero` と `draw` による比較も、未準備を含め127判定を通過した。比較と回帰確認を合わせた57本のWAVを展開して基準ファイルとバイト単位で照合し、入力1,365件と出力424件のSHA-256を再計算した。回帰確認の分を含む計測成果は約154.04 MBだった。[既存指定の回帰確認](../runs/worklet-live-song-render-warmup-20261121-frame-option-regression/manifest.json)
