# キックとハイハットを同じパターンで予約する

固定上流の `parse_beat` は空白と小節線でトークンを分け、休符を空のセルにする。末尾の `>` をアクセント1.3として外し、表の音色IDを照合する。大小文字の直接一致がなければ小文字で照合し、音色表の表記へ正規化する。 `B T> | - t` は、キック1.0、ハイハット1.3、休符、ハイハット1.0の4セルになる。[記譜と音色ID](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L270)・[解析のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L37)

`Engine::render` は通算128出力フレームごとに、音源の時計を使って `BeatPlayer::tick` を呼ぶ。再生器は200 msの先読み内に入った各セルを順に処理し、再生位置用の記録に休符も含める。打音セルでは現在の絶対時刻、音色ID、アクセント、次の打音までの長さを音色表の生成関数へ渡す。持続可能時間は `(1 + 続く休符数) × 16分音符の長さ` 秒で、今回の `B` と `t` はこの長さを参照しない。ジェスチャーの時刻は `hit − latency` を加えて移し、 `B` の遅延は10 ms、 `t` は−5 ms。生成した一組を同じ音源のスコアへ追加する。[描画と予約の接点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[予約と音色別の時刻補正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)

音源は64出力フレームごとに、制御成分ごとに `重み = 余弦ランプの活性 × strength` を足し、目標値の重み付き平均を求める。キックの声門閉鎖とハイハットの開大は異なる成分なので、同じフレームで両方の指示が入る。肺のゲートは呼気成分を平滑化して進める。声道の形状と声門面積が同じ空気の流れに作用するので、PCMでは重なったジェスチャーから新たに伝搬を計算する。上流の予約テストは混在パターンの予約時刻を、Engineテストはホスト幅を変えた描画と既定パターンの波形を照合している。[成分ごとの合成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/score.rs#L402)・[声門と呼気の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L456)・[混在パターンの時刻テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L69)・[Engineの検証](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L13)

240 BPMでは16分音符は62.5 ms、スウィング0.4で奇数セルは12.5 ms遅れる。打音時刻0.400秒の `t` から次の `B` までは50 ms。0.395–0.450秒の観測窓で、開大と呼気が残る間に次のキックの喉頭が上がると予測した。0.84秒までに11セルの時刻が来て8打音が含まれる。先読みで試料終端の先も予約されるので、予約数は14件とした。休符、打音時刻、開大と呼気の独立計算、乱流、上流とのPCM、ホスト幅128と77の一致を比較する。[事前登録ケース](../cases/beatbox-pattern-mixed-kit.json)

## 実装と独立計算

Rustコアの `BeatStep` が音色IDとアクセントを保持する。 `BeatSound::append_gestures` は単発、パターン計画の出力、音源への逐次予約から共通に呼ばれる。再生側は一組分のスクラッチ領域を再利用し、検証済みのジェスチャーを次の制御更新に向けて同じスコアへ移す。既存のケース出力の `slot_accents` を保ち、 `slot_sounds` と各予約の `sound` を追加した。混在時のCSVには舌先、口腔断面、声門開大と流量、三種類の乱流振幅も入る。[音色の入口](../crates/vocal-core/src/phonetics/beatbox.rs)・[予約器](../crates/vocal-core/src/phonetics/beatbox/player.rs)・[CLIの接続](../crates/vocal-cli/src/timing_case/speech_voice/beat_pattern.rs)

独立計算は有理数の16分音符グリッドから各打音時刻を求めた。各ハイハットの呼気ランプ活性を `wⱼ` として、演奏者のゲートが0のときの呼気目標は `Σ(1.25 × accentⱼ × wⱼ) / max(1, Σwⱼ)` になる。声門開大の目標値はどのハイハットでも0.36 cm²なので、開大ランプ活性の合計を `a` とすると、開大指示は `0.00225 + 0.36 × min(1, 3a)` cm²。得られた呼気目標を単発と同じ時定数で平滑化し、全フレームで呼気と開大を照合した。[測定器](../tools/measure_beatbox_pattern.py)・[呼気と開大の独立計算](../tools/measure_beatbox_hat.py)

## 結果

- 48 kHz・40,320フレームで15項目を2回とも通過した。休符を含む再生位置と、11打音の予約フレームおよびジェスチャーが固定上流に一致した。11打音のうち8件の時刻が区間内にある。先読みには出力終了後の3打音も含まれ、そのうち2件の準備動作が終了前に始まる。[初回](../runs/mixed-20261120-a/summary.json)・[ルートからの再実行](../runs/mixed-20261120-root/manifest.json)
- 0.395–0.450秒の2,641採取点すべてで、喉頭0.8 cm以上、開大0.1 cm²以上、呼気ゲート0.15以上が同時に観測された。呼気と開大の独立計算との最大差は `2.80×10⁻¹³` と `3.30×10⁻¹⁴ cm²`。固定上流とのPCM最大差は `2.91×10⁻¹¹`、声門上圧の最大差は `1.07×10⁻⁹ dyn/cm²` だった。[内部系列とPCM](../runs/mixed-20261120-a/summary.json)
- 128と77フレームのホスト幅でWAVと索引CSVはバイト一致した。診断用の声門F0に最大0.475 Hzの差があり、声帯振動は全区間0だった。単発 `B`・`t` と既存のキックパターンの回帰は、従来のWAVと観測CSVに一致した。整形、Rustワークスペースのテスト、Clippy、上流の予約・Engineテストも通過した。[キック](../runs/mixed-20261120-kick-regression/manifest.json)・[ハイハット](../runs/mixed-20261120-hat-regression/manifest.json)・[既存パターン](../runs/mixed-20261120-kick-pattern-regression/manifest.json)

例えば0.450秒のフレーム末尾では、喉頭は1.548 cm、開大指示は0.36225 cm²で、実際の声門面積は0.0299800000012 cm²だった。キックの閉鎖指示が飽和し、声帯振動が0のとき、上流の静的面積式は `(開大指示 + 後部隙間) × (1 − 0.92)`。この値は `(0.36225 + 0.0125) × 0.08 = 0.02998 cm²` になる。鼻口腔と声門の流れを比較するときは、時間が重なった指示と実面積の両方が必要になる。[声門面積の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L220)・[観測CSVの所在とハッシュ](../runs/mixed-20261120-a/manifest.json)

今回の比較範囲は、成人男性の `B` と `t` の固定テンポ再生。演奏中のテンポ変更、停止、ブラウザの実時間接続は今後の比較対象。

```bash
python3 tools/measure_beatbox_pattern.py beat-pattern-mixed-local-1 --condition mixed
```
