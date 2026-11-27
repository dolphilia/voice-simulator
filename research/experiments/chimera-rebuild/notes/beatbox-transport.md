# ビート再生のテンポ変更、停止と再開

固定上流では `Engine::render` がホストの要求を内部の128出力フレーム単位に分ける。各区間の先頭で `BeatPlayer::tick` を呼び、音源の制御時刻から200 ms先までのステップを予約する。予約された休符も再生位置の履歴に入る。音源時計は64出力フレーム分の調音制御を開始するたび進むので、制御境界の途中から見える時計は次の制御境界を指す。イベントはホスト幅に関係なく指定した出力フレームを描画する前に適用する。上流の回帰試験もコマンドの位置で出力チャンクを切る。[Engineの描画と予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[予約のループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L162)・[音源時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L455)・[上流のチャンク分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)

16分音符の長さは `60 / BPM / 4` 秒。プレーヤーは支点の時刻と通算ステップ番号、次の未予約ステップ、予約済みの履歴を持つ。再生中にBPMが変わると、古い16分音符の長さで次の未予約ステップの無スウィング時刻を求め、そこへ支点を移してから新しいBPMを適用する。奇数ステップには `swing × 16分音符の長さ / 2` を足すので、同時にスウィングを変えるか、新旧BPMで奇数ステップの遅れが変わる場合には、最初の未予約ステップにも時刻差が出る。すでに予約された履歴と流し込んだジェスチャーは以前の時刻を保つ。[テンポ、支点、再生位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L85)・[テンポ変更試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L90)

停止時は `BeatPlayer::stop` で新しい予約を止め、`Engine::set_beat_playing` が音源のスコアを消す。再生位置は直ちに−1。停止前の気道圧、呼気、調音器と出力段の状態は次の制御・音響更新に引き継がれる。演奏者ゲート0では、直前にスコアの呼気があった場合は時定数20 msで呼気が減衰する。再開は現在の音源時計に200 msを足した時刻から、第0ステップと新しい予約履歴で始まる。[Engineの開始と停止](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L245)・[スコアの消去](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L315)・[呼気の減衰](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L509)・[停止中の再生位置の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L107)

48 kHz、`m:43> . B . | t . m:47 .` の登録条件では、次の順で出力フレームの境界にコマンドを入れる。

| 出力フレーム | 操作 | 入力に対する予測 |
| ---: | --- | --- |
| 15,317 | 120→160 BPM | 先に予約した0.450秒のキックは時刻が変わらず、未予約だった第3ステップの無スウィング時刻は0.575秒 |
| 20,171 | スウィングを0.4にする | 奇数の第5ステップは0.78125秒になり、偶数の第4・6ステップは0.66875秒・0.85625秒 |
| 33,589 | 停止 | 再生位置は−1。第6ステップのMIDI 47は予約済みなので、そのスコアを消した後の呼気とPCMの減衰を確認 |
| 50,001 | 停止中に100 BPMへ変更 | 停止中の波形に新しい励振を加えず、設定は次の開始に使う |
| 53,003 | 再開 | 音源時計1.105333秒を基準に、1.305333秒から第0ステップを予約。奇数の第1ステップは新しい0.150秒間隔とスウィングで1.485333秒 |

有理数で各予約の時刻と再生位置を計算する。停止後の早い窓では残留するPCM、取り消した打音の区間では呼気ゲートとPCMの小ささ、再開後はMIDI 43の波形が再び立ち上がることを確認する。上流の通常Engineを使い、ホスト幅77・128・4096でPCMを比較する。[登録ケース](../cases/beatbox-pattern-transport.json)

## 実装と結果

Rustの `BeatPlayer` に支点と再生状態を持たせ、CLIの `beatbox_pattern.events` でBPM、スウィング、再生状態を出力フレーム単位で指定できるようにした。同一フレームの操作は記載順に適用する。停止は音源スコアの区間を消去し、音響更新を継続する。イベントのないケースでは従来の設定JSONを保つ。上流は通常の `Engine` を変更せず使い、別の `BeatPlayer` で予約を観測した。独立計算はステップ0の無スウィング時刻を有理数で表し、浮動小数点で加算される時計との丸めを見込んで再生位置を照合した。[再生器](../crates/vocal-core/src/phonetics/beatbox/player.rs)・[CLIの操作](../crates/vocal-cli/src/timing_case/speech_voice/beat_pattern.rs)・[上流の観測器](../tools/upstream_beatbox_pattern_probe.rs)・[独立計算](../tools/measure_beatbox_transport.py)

| 観測 | 再実装と固定上流の結果 |
| --- | --- |
| テンポ変更 | 予約済みのキックは450 msを保持し、未予約の第3ステップは575 ms。後続の第5ステップはスウィングを足した781.25 msに予約された |
| 停止 | フレーム33,589で再生位置が−1になり、そのまま再開まで維持。予約済みのMIDI 47（856.25 ms）は発音に至らなかった |
| 停止後の音響 | 701〜730 msのPCM絶対ピークは0.08593。870〜1,080 msのPCM RMSは約 `7.80×10⁻⁷`、ゲートの最大値は約0.000501。停止直後の105回の制御更新では、20 msの時定数から求めたゲートとの差は最大 `3.47×10⁻¹⁸` |
| 再開 | フレーム53,003の出力時刻は1.104229秒。開始の支点に使う音源時計は53フレーム先の1.105333秒。そこから200 ms先の1.305333秒に第0ステップを置き、その後は100 BPM・スウィング0.4で進んだ。1.36〜1.42秒のPCM RMSは0.07001 |
| 全体 | 予約12件のうち区間内に到来したステップは9件（打音5、休符4）。打音ジェスチャーの照合差は0。88,800フレームのPCM差は最大 `5.82×10⁻¹¹`。各実装の波形はホスト幅77・128・4,096フレーム間でバイト一致した |

初回と `/tmp` からの再実行で登録18項目が通過した。macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。上流の `beatbox`・`engine`、候補の `cargo fmt --all --check`、`cargo clippy --locked --workspace --all-targets -- -D warnings`、`cargo test --locked --workspace` も通過した。実行ディレクトリ、コマンド、設定と出力のハッシュは各実行のマニフェストにある。[初回の要約](../runs/transport-20261120-1/summary.json)・[初回のマニフェスト](../runs/transport-20261120-1/manifest.json)・[再実行のマニフェスト](../runs/transport-20261120-2/manifest.json)

初回と再実行で、要約、設定、候補・上流の時系列と波形など15ファイルがバイト一致した。固定テンポの `m` とスウィングの回帰は、変更前後で各12ファイルが一致。混在パターンも現在の音源設定の基準と12ファイルが一致した。それ以前の混在パターンの実行と比べると、すでに記録済みの声門の瞬時F0ドリフトの導入分が時系列と要約に現れる。[音高付きパターンの変更前](../runs/transport-20261120-hum-before/manifest.json)・[変更後](../runs/transport-20261120-hum-after/manifest.json)・[スウィングの変更前](../runs/transport-20261120-swing-before/manifest.json)・[変更後](../runs/transport-20261120-swing-after/manifest.json)・[混在パターンの基準](../runs/rim-20261120-mixed-source/manifest.json)・[回帰](../runs/transport-20261120-mixed/manifest.json)・[瞬時F0の実装記録](beatbox-rimshot-k.md#実装と検証)

```bash
python3 tools/measure_beatbox_pattern.py transport-local-1 --condition transport
```
