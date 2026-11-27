# 休符とスウィングを含むビートの予約

固定上流の `Engine::render` は、ホストから受け取る長さにかかわらず通算128出力フレームごとに `sub_block_start` へ入り、`voice.clock` を `BeatPlayer::tick` に渡してから音源を描画する。CLIのパターンレンダーも128フレームごとに同じ予約関数を呼ぶ。音源の時計は64出力フレームごとに制御区間の秒数を加算して進む。44.1 kHzなどでは、この足し算で得た時計と通算フレームからの除算は丸めの位置が異なり得る。[Engineの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L710)・[音源時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L456)

`parse_beat` は空白と小節線で分割し、ピリオドとハイフンを休符、末尾の `>` をアクセント1.3と読む。 `B . | - b>` は `B`、休符、休符、アクセント付き `B` の4ステップ。上流は未認識のトークンも休符にする。今回の入力は成人男性の既存キックで構成する。[記譜の解析](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/beatbox.rs#L331)

`BeatPlayer` は開始時の時計に先読み幅0.2秒を足し、ステップ0の打音時刻を固定する。BPMから16分音符の長さ `d = 60 / BPM / 4` 秒を得る。一定テンポでステップ `n` の時刻は `anchor + n × d + (nが奇数なら swing × d / 2)` 秒。パターンの繰り返しでは剰余でセルを選ぶ一方、奇偶判定には通算番号を使う。 `tick` は各予定時刻を現在時刻から0.2秒以内に入った順に取り出し、休符を含む全件の時刻を32件の循環記録に残す。過ぎた打音の追加は省略する。非休符では次の休符の数から持続可能時間を求め、音色の遅延補正を含むジェスチャーを音源スコアへ追加する。 `step_at` は予約済みで時刻が到来した最後のセルを返す。[時刻計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L83)・[予約と再生位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L146)

先読みの幅は最も早い準備ジェスチャーに間に合うように取る。今回のキックは打音137 ms前から準備を始めるので、128フレームの量子化を含めても事前に予約されると予測した。120 BPMでは `d = 0.125 s`、奇数の遅延は31.25 ms。1.16秒に対して、10ステップが予約の範囲に入り、8ステップの時刻が到来する。時刻が到来した打音は0.20000、0.60625、0.70000、1.10625秒。0.60625と0.70000秒の間隔は93.75 msなので、二つの打音の準備・解除が重なり得る。128と77のホスト幅で比較する。[事前登録ケース](../cases/beatbox-pattern-swing.json)・[上流の予約テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L69)・[Engineの描画テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 実装と観測

Rustコアの `BeatPlayer` は、固定テンポのループ、総ステップ番号、直近32件の予約を持つ。CLIは音源が処理した内部サンプル数で予約の境界をそろえ、128出力フレームごとに現在の音源時計で打音を追加する。上流の打音と同様、既に鳴っているジェスチャーと新しいジェスチャーを一つのスコアで合成する。候補は新規打音を加える際に速度保持まで終わったジェスチャーを捨てる。 `inspect` は同じ予約機構を音源なしで走らせ、計画時刻、予約したフレーム、休符、持続可能時間を出力する。 `render` のCSVには各フレームの再生位置と次の予約番号が入る。[Rustの予約器](../crates/vocal-core/src/phonetics/beatbox/player.rs)・[CLIの接続](../crates/vocal-cli/src/timing_case/speech_voice/beat_pattern.rs)・[既存スコアへの追加](../crates/vocal-core/src/voice.rs)

予約時刻は有理数による独立計算と照合した。先読みの境界が128フレームの区切りと厳密に同時になる場合は、浮動小数点時計の丸めで次の区間に入ることを許容し、固定上流の実際の予約フレームとは完全一致を求めた。通算ステップ8の打音は1.2秒。理想計算で先読み内に入るフレーム48,000では、累積時計が `0.9999999999999897` 秒のためまだ条件外だった。上流と候補のどちらも次のフレーム48,128で予約し、打音時刻と準備用ジェスチャーの時刻は変わらなかった。[独立比較](../tools/measure_beatbox_pattern.py)・[初回結果](../runs/beat-pattern-20261120-a/summary.json)

## 結果と残る範囲

- 登録した12項目を2回とも通過。48 kHz・55,680フレームの再生位置は休符も含め固定上流と一致した。観測区間で予約した10ステップには、区間後の打音1件と休符1件も含まれる。区間内の4打音には上記の秒指定でジェスチャーが予約された。[初回の結果](../runs/beat-pattern-20261120-a/summary.json)・[リポジトリルートからの再実行](../runs/beat-pattern-20261120-root/manifest.json)
- 固定上流とのPCM最大差は `1.46×10⁻¹¹`、声門上圧の最大差は `8.42×10⁻¹⁰ dyn/cm²`。候補の128・77フレームのWAVとフレーム索引はバイト一致し、固定上流の通常Engineも2種類のホスト幅でPCMがビット一致した。診断用の声門F0には最大0.475 Hzの差があり、ゲートと声門面積は固定上流と一致した。[観測と判定](../runs/beat-pattern-20261120-a/summary.json)
- 既存の単発キックは13項目を再度通過し、従来のWAVと観測CSVに一致した。固定上流のビートボックス・Engineテスト14件と候補のRustテスト・Clippyも通過した。[単発の回帰](../runs/beat-pattern-20261120-kick-final/manifest.json)・[上流の実行記録](../runs/beat-pattern-20261120-a/manifest.json)

この実装の入力は `B`、`B>` と休符を含む固定テンポのループ。未対応音色は入力エラーにする。再生中のテンポ変更、停止、体型変更時の再予約、WASM・ブラウザ接続は引き続き未検証。現在のCLIはジェスチャーのラベルに文字列を確保するため、実時間接続時には音源への追加を含む割り当て数を計測する。

```bash
python3 tools/measure_beatbox_pattern.py beat-pattern-local-1
```
