# IPA発話の音素・口唇・PCMを同じ時間軸に表示する

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。発話画面の `SpeakPanel` が `ScoreView` を描く。`speakPhrases` が秒単位の音素区間と調音ジェスチャーを計画し、`AudioEngine.schedule` を通じてWorkletへ渡す。WorkletはRust側で実際に使用した開始オフセットを `planned` として返し、テレメトリに合成時計を含める。`ScoreView.planNow` は合成時計から開始オフセットを引き、計画時計へ戻す。横位置は `left + (t − T0) × (right − left) / (T1 − T0)`。ジェスチャーのランプと保持を台形で描き、音素区間は `t0 ≤ t < t1` で選択する。上流の `humanTelemetry` は断面積、圧力、流れ、声門波形などを一定の間隔で渡す。上流の発話E2Eは音声が発話後に無音へ戻ること、Rustの `aspiration`・`fast_speech` テストは有気の目標と、破裂音に挟まれた母音で口が開くことを確認する。[発話画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SpeakPanel.tsx#L220)・[発話計画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L53)・[時計の受け渡し](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[上流の横軸とカーソル](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/ScoreView.tsx#L34)・[テレメトリ](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L214)・[発話E2E](../../../../docs/reference/chimera-vocal-synth/upstream/tools/e2e.ts#L95)・[有気のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/aspiration.rs)・[高速発話のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/fast_speech.rs)

候補のオフライン発話は `OfflineAudioContext` のフレーム0から始まり、計画・観測・保存PCMの時計は共通。出力レート48 kHzで、計画秒数 `t` は経過フレーム `t × 48000` に変換する。Workletの観測は0始まりフレーム `n` の末尾で、横軸の座標は経過フレーム `n + 1`。音声は全サンプルを384区間に分け、区間 `b` の整数境界を `floor(b × N / B)` と `floor((b + 1) × N / B)` で決め、その区間の振幅最小・最大を中心に表示する。カーソルの口唇値は選択フレームまでに取得した最後の点を使い、観測フレームを併記する。

`ɑpɑ` のフレーム数は49,828。先行比較では閉鎖と再開口のブラウザ観測は11,119・13,903フレーム、CLIでは11,118・13,888フレーム。閉鎖の閾値は0.0002 cm²で、観測間隔は16フレーム。画面には固定上流と同じ `ɑ p ɑ` の計画区間と、閾値未満になった観測点から再開口の最初の観測点までの範囲を表示する。予定の /p/ 開始は0.20938024秒、最初の閉鎖観測は0.23166667秒となる見込み。幅960・390 CSS pxのChromiumで、描画座標を保存済みPCMと上流の音素区間、保存済み状態から独立に計算し、カーソルの値と対応をE2Eで照合する。[今回のケース](../cases/worklet-ipa-timeline.json)・[元の入力](../cases/worklet-ipa-voice.json)・[先行のIPA実測](../runs/worklet-ipa-voice-20261119-manual-regression/summary.json)

## 表示と検証

Reactで計画音素の矩形、口唇の最小断面積の折れ線、PCMの区間ごとの最小・最大をSVGに配置する。共通の横軸は経過フレームを画面座標に線形変換する。口唇の帯は閾値をまたいだ観測点で区切る。フレームを選択するスライダーは左右キーで1フレームずつ移動できる。表示中の観測フレームは二分探索で選び、最初の観測より前は空欄相当のダッシュを表示する。表示は既存の発話レポートとPCMを読み、Rustの合成やAudioWorkletの周期には処理を追加しない。[時系列コンポーネント](../../../../web/prototypes/chimera-research/src/ipa-timeline.tsx)・[ブラウザの操作と図形の取得](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs)・[独立比較](../tools/measure_ipa_timeline.py)

Chromium 156.0.8078.4で初回と `/tmp` からの再実行が各15項目を通過した。幅960・390 CSS pxの両方で、音素区間、閉鎖の帯、口唇3,115観測点、PCM384区間の全座標を照合した。固定上流の計画、保存済みWAV、観測JSONから計算した座標との差は最大 `1.14×10⁻¹³` SVG単位だった。クリックで選んだ位置と目標位置の差は最大0.858 CSS px。キーボードでは最初のフレーム、最後のフレームとその1つ手前を正確に選べた。2回のWAV・観測JSON・図形を採取したJSONのSHA-256は一致した。[初回](../runs/worklet-ipa-timeline-20261119-a/manifest.json)・[再実行](../runs/worklet-ipa-timeline-20261119-b/manifest.json)・[デスクトップ幅](../runs/worklet-ipa-timeline-20261119-b/artifacts/timeline-960.png)・[スマートフォン幅](../runs/worklet-ipa-timeline-20261119-b/artifacts/timeline-390.png)

| 読み取る位置 | 計画時刻 | 断面積から求めた時刻 | 差 |
| --- | ---: | ---: | ---: |
| /p/ 開始と最初の閉鎖観測 | 209.380 ms | 231.667 ms | +22.286 ms |
| /p/ 終了と最初の再開口観測 | 289.130 ms | 289.667 ms | +0.536 ms |

CLIの全出力フレームで求めた閉鎖・再開口と比べると、ブラウザの最初の観測は1・15フレーム後だった。48 kHzで16フレームごとに採取するため、閉鎖の帯端には最大15フレーム分の採取遅れが含まれる。PCMは候補CLIと49,828フレームでビット一致。固定上流との差が最初に観測できたのは出力フレーム0の口唇面積・口唇流量・放射微分で、PCMでは13,291フレーム目に最初のビット差があり、最大絶対差は `1.82×10⁻¹²` だった。[計画・観測・PCMの結果](../runs/worklet-ipa-timeline-20261119-b/summary.json)

固定母音とブラウザ歌唱の回帰も通過した。現時点の時系列表示はIPA発話の音素、口唇の最小断面積、出力PCMを扱う。圧力・流量・声門波形やスペクトルを同じ時刻で観察する条件は後続で扱う。[固定母音](../runs/worklet-fixed-voice-20261119-timeline-regression/summary.json)・[歌唱](../runs/worklet-song-voice-20261119-timeline-regression/summary.json)

```bash
python3 tools/measure_worklet_ipa.py worklet-ipa-timeline-local-1 --timeline
```
