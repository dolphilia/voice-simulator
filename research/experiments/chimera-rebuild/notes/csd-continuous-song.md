# CSDの先頭2句を一つの発声器で描画する

調整用 `en001a` の先頭2句を使う。1句目は2.4000秒のMIDI 61、2句目は2.9813秒のMIDI 61と3.5813秒のMIDI 68からなる。固定上流で取得済みの全曲WAVと、候補の計画までを照合した条件を引き継いだ。描画する音符を3つに絞り、録音と同じ64.8秒の時計まで発声器を進める。状態の詳細は最初の4.2秒で調べる。[登録条件](../cases/csd-continuous-song.json)・[前回のCSD計画](csd-song-planning.md)

## 上流から候補まで

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song` は録音のサンプル数を録音レートで割って秒数を得てから `render_notes` に渡す。 `render_notes` は女性の `HumanVoice` を一つ作り、基準F0を最初のMIDI音符、肺圧を9 cmH₂O、緊張を0.55に設定する。各句に対して60 BPM、注釈の絶対開始秒、ビブラート35セントで `plan_song` を呼ぶ。 `HumanVoice::schedule` はジェスチャーを順に追加する。休符中も声道、声門、乱流と出力フィルタの状態は同じ発声器で進む。録音の長さから `round(48,000 × 録音秒数)` フレームを128ずつ描画する。[上流の比較と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L259)・[上流のスコア追加](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L310)

候補の通常の `song_voice` ケースに、絶対時刻を持つ `scores` と任意の `render_end_seconds` を加えた。各項目は既存の歌唱計画で個別に処理する。各句の末尾に同じ余裕時間を取り、他の句に続く場合でも絶対時刻は保持する。ジェスチャーを入力順にまとめて既存の `ArticulatedVoice::set_score` に1回渡し、同じ描画経路で `inspect`、`render`、`render-pcm` を使う。単一の `score` を受ける経路では従来の計画JSONの形、既定の描画長さを維持した。[候補の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L237)・[候補のスコア処理](../crates/vocal-core/src/voice.rs#L401)

スコアの時計は1制御周期ごとに進む。出力48 kHz・内部96 kHzでは、64出力フレームに相当する128内部サンプルごとに制御を更新する。呼気は立ち上がり・立ち下がりの余弦で重みづけし、重み1を超えたら目標の加重平均になる。ゲートを `g`、目標を `u` とすると1回の更新は `g ← e^(−dt/τ)g + (1−e^(−dt/τ))u`。上昇は時定数25 ms、直近0.15秒に呼気ジェスチャーが有効なときの下降は20 ms、その後は70 ms。ゲートから肺圧の目標へ変換して内部サンプルで補間し、声門流量、放射流量の差分、間引きと出力処理の順に進む。吐気ゲートは無次元、声門面積はcm²、流量はcm³/s、放射の時間差分はcm³/s²。CSVは各出力フレームの最後の内部サンプルの値を記録する。[固定上流の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[候補の呼気更新](../crates/vocal-core/src/breath.rs#L90)

固定上流の `engine.rs::output_does_not_depend_on_the_host_block_size` と `sing_fast.rs`、`sung_release.rs` を実行する。上流の観測用プローブは通常の女性設定と、候補と同じ姿勢・声源変動なし・ゲインにそろえた条件を作る。通常プローブの先頭192,000フレームを既存の通常比較の全曲WAVで検証する。候補では2句を入れた波形と、第2句だけを元の時刻に入れた波形を測る。窓は2.825〜2.870秒とし、さらに3.520秒までの区間で第1句の履歴が残るかを見る。[固定版の観測プローブ](../tools/upstream_csd_continuous_probe.rs)・[計測器と独立計算](../tools/measure_csd_continuous_song.py)

## 実測

録音の2,857,680フレームを44.1 kHzから48 kHzへ換算した3,110,400フレームと同じ長さのWAVを得た。短い描画の201,600フレームは長い描画の先頭と一致し、128・77フレーム分割でもWAVと出力CSVはバイト一致した。固定上流の通常プローブの先頭192,000フレームも保存済みの全曲WAVとビット一致した。拍・分節・呼気ジェスチャーは両実装で一致し、最初の音高は277.182631 Hz、3音目は415.304698 Hz。呼気ゲートの独立計算との差は最大 `3.94×10⁻¹²` で、両版のゲートと平滑化F0は全観測点で一致した。[計測結果](../runs/csd-continuous-song-20261121-repeat/summary.json)

句間の2.825〜2.870秒のPCMのRMSは、2句を続けたときが0.025383、第2句だけを元の時刻に入れたときが0だった。第2句の拍を越えた範囲にも差が残り、観測区間2.825〜3.520秒の33,360フレームすべてでビット差があった。直前の声門や気道、フィルタの状態を引き継いだ場合に変化が残ることを示す対照で、状態ごとの寄与はこの計測では分けていない。[句間と第2句の対照](../runs/csd-continuous-song-20261121-repeat/summary.json)

通常の上流とのPCMの最大絶対差は1.1393で、最初のビット差はフレーム0、`1×10⁻⁶` 超はフレーム13だった。フレーム0では平滑化F0が両版で112.257074 Hzと等しく、瞬時F0は上流が112.262041 Hz、候補が112.257074 Hzだった。通常上流の `Drift::new` はシード4242、更新レート3 kHz、0.3・0.9・2.7 Hzの3帯域を使う。最初の乱数12個とフィルタの初期値0から、5セント設定の初回偏差 `+0.0766053` セントを独立計算し、瞬時F0の表示値を再現した。同じフレームで口端流量は通常上流0、候補 `−3.17×10⁻⁷ cm³/s`。上流の姿勢を候補と揃え、声門の変動を0とし、ゲインを揃えた対照では瞬時F0が全点一致し、PCMの最大絶対差は `1.41×10⁻¹¹` に縮んだ。残る最初の数値差は口端流量と放射にあり、各設定の寄与は個別に測る余地がある。[上流の声門変調](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱数とドリフト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L177)・[通常上流の状態](../runs/csd-continuous-song-20261121-repeat/artifacts/standard.csv)・[候補の状態](../runs/csd-continuous-song-20261121-repeat/artifacts/candidate-state.retained.csv)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4。初回と `/tmp` からの再実行で各9判定が通過した。固定上流の歌唱・描画17試験と `vocal-cli` のClippy、単一譜例 `flat` の7判定も通過した。単一譜例のWAVと `song` 計画とジェスチャーは既存の基準と一致した。全体の書式検査には未編集の `phonetics.rs` のモジュール順の指摘があり、変更したRustファイルの書式を個別に確認した。[正式マニフェスト](../runs/csd-continuous-song-20261121-repeat/manifest.json)・[単一譜例の回帰](../runs/csd-continuous-song-20261121-legacy/summary.json)

初回と再実行では要約、PCM、状態など21成果と抜粋元のCSV5件がバイト一致した。各実行で再ビルドした上流プローブの実行ファイルとログ3種類には差があり、出力は個別のSHA-256で追える。

描画用CSVの実体はRTL9210B-CGへ直接書いた。全長の候補CSVは約1.67 GB。短い状態計測を含む候補CSV5件の約1.84 GBは全区間を処理してから、フレーム0付近・音符周辺・終端の観測と元のSHA-256を保存した。正式成果は約88.1 MB。初回は作業領域2 GiBを見込み、再実行では3 GiBを指定した。長い録音を評価する際は、音響指標にはWAVを使い、高密度の観測を必要とする区間を指定できると中間CSVの量を抑えられる。[初回の出力と保存](../runs/csd-continuous-song-20261121-a/manifest.json)・[再実行の抜粋とハッシュ](../runs/csd-continuous-song-20261121-repeat/manifest.json)

`research/experiments/chimera-rebuild` から未使用の実行IDで再現する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=3221225472 ../../.venv/bin/python tools/measure_csd_continuous_song.py csd-continuous-song-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_song_voice.py csd-continuous-song-legacy-local-1 flat
cargo clippy --locked --offline -p vocal-cli -- -D warnings
```
