# CSDの録音でビブラートを測れる長音を選ぶ

先に測った調整用 `en001a` と確認用 `en005a` は、最長の連続有声区間が320・290 msだった。400 msの判定条件で録音を評価するため、CSD v1.1の英語aキーの注釈から長い音符を持つ曲を選び、選んだ後に録音を取得した。元の2曲の条件と結果も保持した。[登録した条件](../cases/csd-long-note-vibrato.json)・[元の2曲の測定](csd-vibrato-aperiodicity.md)・[データセットの著者による説明](https://github.com/equal-singer/CSD)・[CSD v1.1の配布版](https://doi.org/10.5281/zenodo.4916302)

## 注釈による選定

固定上流の `score::held_out` は曲番号が5の倍数かで区分を決める。音符の注釈は `compare::load_notes` の区切り方に合わせて読み、前の音符との間隔が80 msを超えたら次の句にする。メリスマの判定に加え、通常は音符の開始30%・末尾20%、メリスマは各10%を除いた秒座標を使う。先頭から5 ms刻みで終端を含む格子を置き、まだ音声を使わない段階で取り得る有声窓の上限とする。候補の窓数は10進数の正確な時間差でも計算して照合した。40曲の調整用と10曲の確認用をそれぞれ、100窓以上の音符数、80窓以上の音符数、最長の窓数の降順に並べ、残る同値は曲IDで解いた。[読み込みと曲の分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L160)・[確認用の分割と試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/score.rs#L81)・[上流の音符格子](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L552)

注釈50件の計7,220音符を照合し、10進式と浮動小数点式の差が出た122音符はすべて1窓差だった。ランキングに使った3個の整数値は全50曲で一致した。33曲に80窓以上の音符があった。調整用は `en012a`、確認用は `en035a` を、音響測定前に別実行のランキングとハッシュで確定した。各曲の80窓以上の音符数は44と39、100窓以上は35と30。最長の格子は216と287窓。注釈の取得にはZIPの206応答を4範囲、計458,752バイト使った。範囲と配布情報を照合し、各ZIP項目はCRC32とSHA-256を保存した。録音は確定した2件だけを、その後の実行で取得した。WAVの実体は計約44.85 MB。各ZIP項目を部分取得し、配布ZIP全体のMD5は計算対象外とした。[全曲のランキングと出典](../runs/csd-long-note-annotations-20261121-selected/summary.json)・[選定の実行記録](../runs/csd-long-note-annotations-20261121-selected/manifest.json)・[録音のハッシュと長さ](../runs/csd-long-note-recordings-20261121-a/summary.json)

## 描画と検出の条件

固定上流の通常CLI `compare csd --float` を2曲に実行した。 `compare_song` は録音を読んで録音長を求め、 `render_notes` が各句を1つの発声器に絶対時刻で予約する。再実装も同じ女性体型、60 BPM、深さ35セントとし、既存のCSDの再実装設定に注釈由来の句を渡す。候補の `inspect` で拍とMIDI、母音開始時刻、30 ms以内の採否を取得し、候補の `render-pcm --no-trace` の128・77フレーム分割を比較する。録音は44.1 kHzの2チャンネルを平均し、合成は48 kHzのfloat32。ともに時間を秒で共有し、記録した元のサンプルレートで計測する。[上流の通常描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L257)・[候補の通常描画と比較](../tools/measure_csd_long_notes.py)

ビブラートは4–9 Hzで、5 msの窓が80個以上連続して有声の音符を対象とする。最長の有声区間から直線を引き、正規化自己相関で0.5以上の最初の局所最大を補間する。深さは残差RMSの `√2` 倍（セント）。録音と固定上流は通常レポート、調整用は丸め前のスコア、確認用は区分のスコアを照合する。PCMの非周期性は電力ゲートより先に得られるYINの値を含む。既知周期の試験を持つ固定上流を再実行し、残差の独立回帰と全ラグの相関も照合する。[ビブラートの実装と既知周期の検証](csd-vibrato-aperiodicity.md)・[固定上流の測定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L667)

## 無声歯摩擦音を接続した差分

初回は固定上流が両曲を描画した後、候補の `inspect` が `en012a` の `/θ/` で停止した。注釈では第5音と第22音の語末に該当し、選定を維持した。固定上流は `inventory.rs` の較正された舌先目標を `plan_utterance` と `oral_gestures_into` で使う。歌唱の `plan_song` もこの発話計画を使う。候補に既にあった `/θ/` のIPA、長さ、較正表を使い、既存の無声摩擦音と歯摩擦音の目標を接続した。CLIの追跡とWASMの乱流スイッチに同じ音素を加えた。[停止した元実行](../runs/csd-long-note-vibrato-20261121-a/manifest.json)・[上流の音素目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L185)・[声門開大](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L496)・[歌唱から発話計画を呼ぶ箇所](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L286)・[候補の実装](../crates/vocal-core/src/phonetics/speech.rs)

単独の女性 `/θɑ/` では、摩擦音区間0.262〜0.350秒に対し、舌先X/Yは6.85/8.242 cmで、目標を0.254秒から置く。速度倍率1.3、保持45 ms。声門開大0.30 cm²のジェスチャーは0.247〜0.355秒。独立式と両版の計画が一致し、母音の拍は0.350秒だった。通常のIPA発話 `/ɑθɑ/` でも計画を通した。固定上流は一致させた初期条件の比較プローブを使い、最大PCM差は `1.46×10⁻¹¹`。候補の128・77分割はバイト一致した。計測器の初回起動時の `Path` の読み込み漏れは修正した。Rustワークスペース41試験、Clippy、リリースWASMのビルドが通った。[歯摩擦音の事前登録](../cases/csd-dental-theta.json)・[独立式と波形](../runs/csd-dental-theta-20261121-verified/summary.json)

## 録音と両合成の実測

`en012a` は185音符・46句・137.78秒、 `en035a` は109音符・76句・116.47秒。2曲で294音符、録音と両合成の計62,127窓を測った。母音開始の候補と上流報告の最大差は報告丸め幅内の4.9 msで、両曲とも注釈から30 msを超えた音符は0。候補の2種類のブロック分割でWAVが一致した。音符ごとの通常報告を再現し、調整用の丸め前の値との最大差は `3.56×10⁻¹⁴`。対象となる全249系列で独立した回帰と相関を照合し、残差の最大差は `1.14×10⁻¹³` セント、相関差は `8.89×10⁻¹⁶` 未満だった。[全音符の結果](../runs/csd-long-note-vibrato-20261121-theta/summary.json)・[上流の通常報告](../runs/csd-long-note-vibrato-20261121-theta/artifacts/upstream/report.md)

| 曲 | 波形 | 検出／評価対象 | 深さの中央値（セント） | 周波数の中央値（Hz） |
| --- | --- | ---: | ---: | ---: |
| `en012a` 調整用 | 録音 | 29／44 | 31.16 | 6.085 |
| `en012a` 調整用 | 固定上流 | 44／44 | 34.59 | 6.002 |
| `en012a` 調整用 | 再実装 | 44／44 | 34.12 | 5.995 |
| `en035a` 確認用 | 録音 | 17／39 | 39.46 | 5.840 |
| `en035a` 確認用 | 固定上流 | 37／39 | 34.79 | 5.992 |
| `en035a` 確認用 | 再実装 | 38／39 | 33.74 | 5.990 |

両曲とも、注釈で80窓以上を取れた音符すべてで、録音・固定上流・候補に連続有声区間が得られた。録音で対象に達したものの検出されなかった音符は、調整用15件と確認用22件で、いずれも相関の山が0.5に届かなかった。曲を選ぶ条件に長い安定区間を使ったため、検出割合はこの2曲の記述値とする。[通常条件の音符表](../runs/csd-long-note-vibrato-20261121-theta/summary.json)

## 第3倍音がビブラート推定に入る対照

確認用の第21音 `/lʌ/` で、両合成は同じ80窓がすべて有声だった。通常の条件では固定上流の自己相関の局所最大が探索範囲内で最大0.459にとどまり、未検出。候補は遅延34窓で0.865となり、深さ225.07セントを返した。声門に与えた設定の深さは35セント。どちらのF0系列にも譜面より700セント以上高い窓が4つあり、出現する最初の窓は固定上流が26.84078秒、候補が26.84578秒だった。[通常条件のF0・非周期性](../runs/csd-long-note-vibrato-20261121-theta/artifacts/en035a/en035a-pitch-periodicity-frames.csv)

同じ波形、窓、ゲート、探索下限を保ち、上限だけを+7から+5半音へ狭めた。両合成の最初の外れ窓では、最強周波数が約746・746 Hzで、狭い探索のF0約249 Hzの第3倍音に当たる。通常は128サンプルの遅延を選んだが、193サンプルの累積平均正規化差がさらに小さかった。対照で全有声窓を維持して、両合成の4窓ずつの外れ値が消えた。固定上流は **30.97セント・6.080 Hz**、候補は **33.08セント・6.081 Hz** を返した。録音のF0と判定に変化はなかった。この対照と全曲の通常報告は別々に保存した。[対照の登録](../cases/csd-long-note-vibrato-f0-control.json)・[80窓の比較とFFT](../runs/csd-long-note-vibrato-f0-control-20261121-a/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1。注釈の最初の試行では作業ツリー外の配布メタデータを相対パスのスナップショットへ渡して停止した。修正後は配布情報のハッシュをマニフェストに記し、元のJSONを検証済み成果として保存した。注釈3判定、録音1判定、全曲23判定、歯摩擦音5判定、F0対照3判定、固定上流20試験が通過した。固定上流のWAV・報告・スコアは候補の修正前後でバイト一致し、F0対照は `/tmp` からの再実行でもCSVと要約が一致した。全曲の正式成果は約115.24 MBで、元の録音とCSV・WAVは作業用RTL9210B-CGにある。WAVのレート、出力長、ハッシュ、ブロック分割での再現手順はマニフェストで追える。[最初の注釈取得の記録](../runs/csd-long-note-annotations-20261121-a/failure.json)・[全曲のマニフェスト](../runs/csd-long-note-vibrato-20261121-theta/manifest.json)・[対照のマニフェスト](../runs/csd-long-note-vibrato-f0-control-20261121-a/manifest.json)・[対照の再実行](../runs/csd-long-note-vibrato-f0-control-20261121-repeat/manifest.json)

`research/experiments/chimera-rebuild` から、保存した注釈の選定と録音の実行を指定して再実行できる。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_csd_long_notes.py csd-long-note-vibrato-local-1 --selection-run csd-long-note-annotations-20261121-selected --recording-run csd-long-note-recordings-20261121-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=33554432 ../../.venv/bin/python tools/measure_csd_long_note_f0_control.py csd-long-note-vibrato-f0-control-local-1
```
