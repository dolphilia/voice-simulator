# 開ハイハットの摩擦と呼気の長さ

固定上流の音色表で `tss` を選ぶと、`BeatPlayer::gestures` は打音の遅延−5 msを補正し、音色関数 `open_hat` に持続可能時間 `L` 秒とアクセントを渡す。CLIの単発キットは `L = 0.15 s` を渡す。パターンは `BeatPlayer::tick` が現在セルより後に連続する休符をループ境界も含めて数え、`L = (1 + 休符数) × (15 / BPM)` 秒を渡す。後続打音が現在セルの次なら `L` は16分音符1個分になる。スウィングの補正は打音時刻に作用し、この長さには入らない。[単発キットの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L619)・[パターンの予約と長さ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)・[音色と遅延](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L270)

`open_hat` は相対終端 `E = max(0.09, min(0.26, 1.6 × L))` 秒を求める。歯茎閉鎖は短い `t` と共通で、強い舌先目標を立上り30 ms、減衰10 ms、速度3.5で動かす。解除後の /s/ は相対0.012秒から `E` までの摩擦を作り、舌先・顎の目標は8 msの立上りと速度1.4で動く。舌体補助も立上りは8 ms。声門開大は0.4 cm²を上乗せし、呼気の目標は `1.2 × accent`。呼気の保持は `E` までで、そこから90 msの余弦で減衰する。開大は `E + 0.11 s` まで保持し、続く30 msで弱まる。出力は計7ジェスチャーで、絶対時刻への変換後に同じ音源のスコアへ追加する。[開ハイハットと呼気](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L166)・[調音のタイミング](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)

音源は出力64フレームごとの更新で、呼気目標をゲートの状態に反映する。ゲートの上り時定数は25 msで、呼気スコアの有効期間と終了直後の下りは20 msになる。肺境界から声門へ流れが生じ、声道の狭窄と歯に置かれた乱流源が帯域雑音を発生させる。スコア上の摩擦終端、呼気目標がゼロになる時刻、PCMの減衰はそれぞれ異なる観測点になる。上流のテストは音色ごとの準備と余韻が打音をまたぐこと、混在スコアの予約とEngineの出力が分割幅に依存しないことを検査する。[音源の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L456)・[乱流の配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[予約テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L55)・[Engineの分割幅テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 事前登録

成人男性、出力48 kHz・内部96 kHz、アクセント1で比較する。パターン2条件は240 BPMで、最初の打音は0.200秒。単発キットは打音0.250秒。

| 条件 | `L` | `E` | 絶対摩擦終端 | 呼気目標がゼロになる予定時刻 |
| --- | ---: | ---: | ---: | ---: |
| 直後に `B` | 62.5 ms | 100 ms | 305 ms | 395 ms |
| 7休符の後に `B` | 500 ms | 260 ms | 465 ms | 555 ms |
| 単発キット | 150 ms | 240 ms | 495 ms | 585 ms |

短いパターンでは400–440 msで呼気が減衰し、長いパターンでは同じ窓で呼気と摩擦が続くと予測した。両パターンで閾値0.1を下回る最初の呼気ゲートのフレームを測る。単発では比例計算、閉鎖解除後の摩擦と歯の乱流、公式のWAVとの一致を確認する。パターンの上限240 BPMでは最短でも `E = 100 ms` になるので、90 msの下限は単発で `L = 50 ms` を指定して計画を検査する。配布CLIの0.5秒の単発クリップには呼気の減衰が最後まで入らないため、減衰の比較には0.84秒のパターンを使う。[短いパターン](../cases/beatbox-open-hat-short.json)・[長いパターン](../cases/beatbox-open-hat-long.json)・[単発キット](../cases/beatbox-open-hat-single.json)

## 実装と検証

単発のケースは `step_seconds`、パターンは予約時に求めた `length_seconds` を共通の `BeatSound::append_gestures` へ渡す。 `t` と `tss` は歯茎閉鎖と摩擦用の調音手順を共有し、摩擦終端、速度、呼気倍率、開大と減衰を音色ごとの係数にした。調音目標を既存の声道へ追加し、声門や肺圧、乱流に作用させる。初回のパターンケースでは単発用の `accent` をパターン入力にも残したため、両方とも読み込みで停止した。アクセントは記譜から決まるのでフィールドを除き、同じ入力意図と判定基準で再試行した。[共通の音色入口](../crates/vocal-core/src/phonetics/beatbox.rs)・[パターンからの接続](../crates/vocal-cli/src/timing_case/speech_voice/beat_pattern.rs)・[短い条件の初回エラー](../runs/open-hat-20261120-short-a/manifest.json)・[長い条件の初回エラー](../runs/open-hat-20261120-long-a/manifest.json)

パターンでは有理数で求めた打音時刻と持続可能時間から、呼気と開大の各ランプを独立に計算した。呼気ゲートは制御周期 `Δt` ごとに `g₁ = G + (g₀ − G) exp(−Δt/τ)` で更新した。開大は、ランプの活性を重み6で合成し、合計重みが2に達するまで目標値を線形に効かせる。2条件の最大絶対差はゲート `4.97×10⁻¹⁴`、開大 `1.31×10⁻¹³ cm²` だった。[独立計算](../tools/measure_beatbox_hat.py)・[パターンの比較](../tools/measure_beatbox_pattern.py)

| 観測 | 短いパターン | 7休符を含むパターン |
| --- | ---: | ---: |
| 摩擦と呼気の保持終端 | 305 ms | 465 ms |
| 呼気ゲートが最初に0.1を下回る時刻 | 409.354 ms | 569.354 ms |
| 400–440 msの平均ゲート | 0.0670 | 1.2000 |
| 400–440 msのPCMのRMS | 0.00201 | 0.02720 |
| 同窓の歯の乱流振幅ピーク | 0 | 86.15 |
| 固定上流とのPCM最大差 | `5.82×10⁻¹¹` | `7.28×10⁻¹²` |

呼気ランプの終了からゲートが0.1を下回るまでは、両パターンで約14.35 msだった。後続する `B` の時刻も変わるので、表のPCMは各パターン全体の観測値である。ゲートには `tss` の呼気ジェスチャーだけが寄与し、摩擦保持終端の160 ms差がゲートの閾値通過にも現れた。出力48 kHz・40,320フレームで声帯振動は両方とも0だった。診断用の声門F0には最大0.475 Hzの差が残る。[短い結果](../runs/open-hat-20261120-short-b/summary.json)・[長い結果](../runs/open-hat-20261120-long-b/summary.json)

単発キットは13項目、パターンは各16項目を通過した。単発150 msの保持終端495 msと、50 msで下限に達する保持終端345 msは、候補と固定上流の計画で一致した。150 ms条件では固定上流の通常CLIと上流プローブのPCMはビット一致し、候補との差は最大 `2.91×10⁻¹¹` だった。すべての条件で128と77フレームのホスト幅を比較し、候補のWAVと索引CSVはバイト一致した。単発 `t` と既存の混在パターンの回帰、候補のRustテスト・整形・Clippyも通過した。[単発](../runs/open-hat-20261120-single-a/summary.json)・[単発 t の回帰](../runs/open-hat-20261120-hat-regression/summary.json)・[混在パターンの回帰](../runs/open-hat-20261120-mixed-regression/summary.json)

リポジトリルートから3条件を再実行し、それぞれ結果要約、観測CSV、WAVと索引CSVが先行の通過実行にバイト一致した。[単発の再実行](../runs/open-hat-20261120-single-root/manifest.json)・[短いパターンの再実行](../runs/open-hat-20261120-short-root/manifest.json)・[長いパターンの再実行](../runs/open-hat-20261120-long-root/manifest.json)

```bash
python3 tools/measure_beatbox_open_hat.py open-hat-single-local-1
python3 tools/measure_beatbox_pattern.py open-hat-short-local-1 --condition open-short
python3 tools/measure_beatbox_pattern.py open-hat-long-local-1 --condition open-long
```
