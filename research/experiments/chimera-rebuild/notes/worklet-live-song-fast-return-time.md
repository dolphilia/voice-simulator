# 短い音符の歌唱で事前描画と返却時刻を比較する

歌唱画面の「短い音符」プリセットから、既存の `song-voice-fast` を実行する。歌詞は従来と同じ `Pop Dee`。240 BPMの4分の1拍は62.5 msで、音高はMIDI 60と64、最初の拍は0.5秒、乱流係数は0。従来の長い音符に対してテンポ、音符の長さ、第2音の音高、乱流係数が異なる。[既存の歌唱ケース](../cases/song-voice-fast.json)・[事前登録](../cases/worklet-live-song-fast-return-time.json)

## 短い音符の計画から出力まで

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、歌唱画面の `singing.ts` が歌詞を音節に分け、旋律に割り当てた音節を `planSong` へ渡す。WASMの `api.rs` は `planSong` をRustの `plan_song()` に渡す。Rust側は `60 ÷ BPM` を秒で求め、各音符の `beats` を掛けて拍時刻を積算する。`fit()` は前の語尾と次の語頭を同じ音符間に収める。母音の計画上の最小長さは20 ms。句末は `min(50 ms, 最終音符の30%)` を末尾から引いて、このケースの呼気の句末を0.60625秒にする。その後に開大を開始する。`fast_runs_land_on_the_beat()` は240 BPM・4分の1拍でも母音核が拍と合い、母音長が20 msを下回らない例を検査する。`too_many_consonants_degrade_gently()` は子音が収まりきらない例のずれの上限を検査する。[上流の歌唱画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts)・[WASMの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs)・[短音の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs)・[短い音符の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)

再実装の `SongPanel` は同じケースから歌詞と音符を読み込み、通常のボタンから歌唱を開始する。`prepareSongVoice()` がRustの計画結果を取得してから、合成用のスコアにプリセットの乱流係数を渡す。既定の長音では計画が返す係数1を使う。CLIの `run_song()` も同じケースの係数で準備し、レンダー側が `enable_turbulence()` に渡してから調音スコアを適用する。拍の時刻は0.5秒と0.5625秒で、48 kHzでは24,000と27,000フレーム。歌唱PCMは49,200フレーム、観測を64フレーム間隔で採ると最終行を含め769行になる。[歌唱画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[計画からWorkletへの接続](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[CLIの読み込み](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[オフライン比較条件](../cases/worklet-song-voice-fast.json)

## 基準と比較条件

CLIの128・77フレーム分割は一致し、固定上流と計画・観測・PCMの照合を通過した。オフラインWorkletのPCMはCLIとビット一致し、上流との差は最大2.91 × 10⁻¹¹だった。ビブラートは観測で0セントだった。冒頭の唇閉鎖は、CLIと上流の両方で第1母音の計画区間をまたぐ。これらを音と計画の基準に使い、Firefoxでは同じプリセットを通常の実時間歌唱で再生する。[CLIと上流](../runs/song-voice-fast-20261121-return-reference/summary.json)・[オフラインWorklet](../runs/worklet-song-voice-fast-20261121-return-reference/summary.json)

同じ先行音と48 kHz・256フレーム要求で、192フレームの一括事前描画、64フレームずつの分割、第1片を2量子遅らせた分割を比べる。先行音から構築を含む要求を対応づける。予定ホスト時刻までの残り時間は固定済みの既知PCMの範囲1.826250〜1.829500 msを使う。構築直後の時刻の飛び、歌唱の開始までのフレーム、PCMと計画の一致を別々に検査する。[残り時間の前回比較](worklet-live-song-cubeb-return-time.md#実測)・[測定入口](../tools/measure_worklet_live_song_shared_context.py)

## 実時間の結果

最初の2実行では各6試行・120判定を通過した。再実行の通常分割では、構築と第1片を含む要求の処理が5.080250 ms、返却前から予定ホスト時刻までの残りが1.792875 msだった。名目周期は5.333333 ms。次の機器時刻の差が最初の飛びの観測点で、予定サンプル時刻は256フレーム飛んだ。既知PCMから決めた範囲による方法はこの回も正しく判別した。第1片を遅らせた場合は毎回構築の次の要求に入り、歌唱開始までの3,072フレームは両方の分割で揃った。[初回](../runs/worklet-live-song-fast-return-time-20261121-a/summary.json)・[別ディレクトリからの再実行](../runs/worklet-live-song-fast-return-time-20261121-repeat/summary.json)

初回と再実行の採取設定には、末尾の補完フレーム数に長音の64が残っていた。短音の49,200フレームは385量子で、末尾の補完は80フレームになる。採取設定をこの長さに合わせて更新し、6試行で再確認した。最初の2実行のPCMと量子の連番も読み直し、出力フレーム数と末尾の位置を確認した。[採取設定の再確認](../runs/worklet-live-song-fast-return-time-20261121-schedule-confirmation/manifest.json)

| 事前描画（各6試行） | 構築を含む要求の直後の飛び | 構築から4要求までのピーク |
| --- | ---: | ---: |
| 構築中に一括 | 6 / 6 | 6.68〜8.89 ms |
| 無音中で分割 | 1 / 6 | 3.61〜5.08 ms |
| 分割開始を2量子遅らせる | 0 / 6 | 1.95〜3.04 ms |

短音の全18試行で、残り時間を使う方法は飛び7回と連続11回を判別した。名目周期だけの方法は17回正答した。分割開始を遅らせた6組のピーク短縮は0.71〜3.13 ms、中央値は1.82 ms。全18試行の歌唱PCMはCLIの基準とバイト一致し、歌唱の観測と計画の照合に合格した。先行音の前後各8要求に含まれる4,352フレームの連番も、左右の差から独立に照合した。長音を使う従来の分割比較は77判定と固定上流の17テストを通過した。全6実行の入力1,556件と出力384件のサイズとSHA-256を確認し、採取と基準データ約261.0 MBをRTL9210B-CGへ保存した。[長音の回帰確認](../runs/worklet-live-song-deferred-split-preparation-20261121-fast-regression/manifest.json)

短音と長音の結果にはスコアと乱流係数の両方の違いがある。次は短音のスコアを固定し、乱流係数だけを0と1にして観測する。プロセスタップの校正が通った場合は、機器から実際に出た音の連続性も照合する。

## 再現

研究ワークスペースから実行する。各 `<実行ID>` に未使用の名前を指定する。

```bash
firefox=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=190000000 ../../.venv/bin/python \
  tools/measure_song_voice.py <CLI実行ID> fast
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=190000000 ../../.venv/bin/python \
  tools/measure_worklet_song.py <オフライン実行ID> --case cases/worklet-song-voice-fast.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python \
  tools/measure_worklet_live_song_shared_context.py <実時間実行ID> \
  --deferred-split-preparation --fast-song-reference <オフライン実行ID> --cubeb-output "$firefox"
```
