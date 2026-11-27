# ブラウザの手動調音をCLIケースに書き出す

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。ブラウザは `AudioEngine.setArtic` で受け取った部分目標をまとめて送り、Workletの `artic` 処理が `engine_set_artic` を呼ぶ。`process` の `engine_render` が目標変更後のサンプルを生成する。上流CLIの `render notes` も時刻を付けた操作をブロックの前に適用する。上流の `engine.rs` のテスト `session` は操作時刻を出力サンプル番号で固定し、その位置でレンダーを区切ると、ホストの分割を変えてもPCMが一致することを確かめる。上流の `.tele` は描画用の観測結果を時刻付きで保存する形式で、今回の候補のJSONは再合成するための初期条件と操作を保存する。[上流の操作集約](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L383)・[Workletの入力](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L112)・[描画ブロック](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[CLIの操作時刻](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L312)・[上流の時刻と分割のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L35)・[観測ファイル](../../../../docs/reference/chimera-vocal-synth/upstream/src/show/tele.ts)

候補ブラウザは開始・停止と舌体X・Y・口唇開度の適用時刻を、安定した合成開始から数えた0始まりの出力フレームで記録する。位置はcm、呼気ゲートは無次元。CLIの制御フレームはこの出力番号を1制御更新の出力サンプル数で割った値。登録ケースでは48 kHz出力で64サンプル、96 kHz内部で128サンプルごとに更新する。CLIは制御境界で呼気目標と調音目標を更新してから、臨界減衰の追従、声道断面の計算、声門と気道の計算を進める。ブラウザで採用された目標だけを保存し、停止と同フレームの調音は一つのCLIイベントにまとめる。[候補のWorklet処理順](../../../../web/prototypes/chimera-research/src/live-processor.ts#L100)・[CLIのケース定義](../crates/vocal-cli/src/articulation_case.rs)・[CLIの更新順](../crates/vocal-cli/src/articulation_case/voiced.rs#L54)・[手動調音の先行検証](worklet-manual-articulation.md)

既存の3操作と開始・停止を画面から行い、「再実行ケースを保存」で得たJSONを変換せずにCLIへ渡す。独立に復元した各イベントの整数時刻・数値、初期姿勢・音源、全長と一致し、両ホスト分割のCLIでブラウザPCMとビット一致すると予測する。ブラウザの観測点、固定上流、調音と呼気の独立式には元ケースの許容差を適用する。あわせて固定時刻の境界入力で、調音と呼気が同一フレームの場合は昇順で重複のない2件にまとまること、調音操作がない場合も開始・停止を再生できること、64の倍数でない時刻は丸めずエラーとすることを検査する。[今回の比較条件](../cases/worklet-manual-case-export.json)・[既存の3操作](../cases/worklet-manual-articulation.json)

## 保存する内容と再合成

WASMは制御更新の周期を出力フレーム数で返す。ブラウザはWorklet完了時の適用ログ、実際に渡した初期姿勢・音源、出力長を組み合わせてケースを作り、「再実行ケースを保存」でJSONをダウンロードする。イベントの制御フレームと全長は、合成時に採用した出力フレームを実際の制御周期で割る。1制御更新あたりの内部サンプル数は、出力制御周期に内部レートと出力レートの比を掛けて求める。舌先は自由、口蓋との接触補正は有効、初期ゲートは0。手動操作の再生にはスコアがなく、基準重みは追従式に影響しないため、既存の上流プローブと同じ1.0を保存する。保存時刻は合成器の時計に沿い、AudioContextの立ち上がりや入力受付の壁時計は観測JSONに残る。[WASMの制御周期](../crates/vocal-wasm/src/lib.rs)・[保存形式](../../../../web/prototypes/chimera-research/src/manual-replay.ts)・[完了時の組み立て](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts)

ダウンロードしたファイルを研究ワークスペースから直接CLIに渡せる。以下ではファイルをカレントディレクトリに置き、出力ファイル名を指定している。

```bash
cargo run --locked --release -p vocal-cli -- inspect worklet-articulation-case.json
cargo run --locked --release -p vocal-cli -- render worklet-articulation-case.json replay-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm worklet-articulation-case.json replay.wav replay-pcm.csv 128
```

## 実測結果

Chromium 156.0.8078.4で初回と `/tmp` からの再実行が各20項目を通過した。両回のダウンロードケースは同じSHA-256だった。開始、舌体Y、舌体X、口唇開度、停止が出力フレーム4,096、20,352、32,640、44,928、63,872で適用され、JSONには制御フレーム64、318、510、702、998として入った。終了後の減衰を含む全長は1,598制御フレーム、48 kHzのPCMでは102,272フレーム。[初回の実行](../runs/worklet-manual-case-export-20261119-a/manifest.json)・[再実行](../runs/worklet-manual-case-export-20261119-b/manifest.json)・[実際のダウンロード](../runs/worklet-manual-case-export-20261119-b/artifacts/browser-case.json)

ダウンロードしたJSONをCLIの `inspect`、`render`、`render-pcm` にそのまま渡した。128・77の両ホスト分割の加工前PCMはブラウザとビット一致し、799観測点の内部状態12系列も一致した。固定上流とのPCM最大絶対差は `3.73×10⁻⁹`（許容差 `5×10⁻⁷`）だった。最初の差は出力フレーム0に対応する内部サンプル1の放射微分 `−2.00×10⁻¹¹ cm³/s²` で、先行の手動調音比較でも同じだった。[数値差と観測値](../runs/worklet-manual-case-export-20261119-b/summary.json)

固定時刻の境界入力では、制御フレーム64と128でそれぞれ呼気と調音を一つのイベントにまとめ、CLIが両方を受理した。調音なしのケースも開始と停止の2件を受理した。停止に8,193出力フレームを与えると、整数制御境界から外れるため書き出し前にエラーになった。この境界検査は、画面での操作とは別に固定した時刻で実行した。[同一境界の入力](../runs/worklet-manual-case-export-20261119-b/artifacts/boundary-case.json)・[調音なしの入力](../runs/worklet-manual-case-export-20261119-b/artifacts/no-motion-case.json)・[境界外の結果](../runs/worklet-manual-case-export-20261119-b/artifacts/export-boundary-result.json)

固定母音の実時間発声とブラウザIPAの時系列表示の回帰も通過した。ブラウザの再実行ケース保存は手動調音の結果画面にある。[実時間発声](../runs/worklet-realtime-voice-20261119-case-export-regression/summary.json)・[IPAの時系列](../runs/worklet-ipa-timeline-20261119-case-export-regression/summary.json)

```bash
python3 tools/measure_worklet_manual_articulation.py worklet-manual-case-export-local-1 --case-export
```
