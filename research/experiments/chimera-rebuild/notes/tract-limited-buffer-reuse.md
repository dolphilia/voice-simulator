# 咽頭・口腔の断面制限用バッファを再利用する

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::control()` は調音目標を適用した後に接触を補正し、補正されたときだけ `HumanAirway::reapply()` を呼ぶ。上流の `apply()` は制御周期が正のとき、前の咽頭・口腔の平均・最小断面を基準に保存する。 `commit()` では今回の形状を同じセル数の出力配列に再標本化し、`reapply()` でも制御周期の開始時の基準に対して増減を制限する。入力は姿勢と制御周期（秒）、出力は咽頭・口腔のセル面積（cm²）と管長（cm）。上流の閉鎖試験は制限を含む圧力過渡を検査する。[上流の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs:499)・[断面・基準の扱い](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs:214)・[閉鎖の検証](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs:233)

研究版は制限前の `raw` と制限後の `limited` を通常CLIから個別に観測できる。口腔と咽頭のセル数は `HumanTractControl` の初期化時に決まり、同じ制御器では保たれる。`apply()` の制限に必要なのは更新直前の `current.limited`。旧 `baseline` はここで役目を終え、複製先に使える。制限後に旧 `current.limited` を次の `baseline` へ移す。`reapply()` はこの `baseline` を使うので、同じ周期内で導出したばかりの `current.limited` を複製先に使える。面積の制限式は、開口で `min(G, A + (r(A) + 40G) dt)`、閉鎖で `max(G, A - (r(A) + 40A) dt)`。平均と最小の両方に適用し、最小を0〜平均に収める。形状の計算と再標本化に成功してからセル領域を取り出せば、そこでエラーになった場合も既存の確定断面と基準が残る。[研究版の声道更新](../crates/vocal-core/src/airway/tract_control.rs)・[通常CLIの観測](../crates/vocal-cli/src/articulation_case/tract.rs)・[断面制限の詳細](tract-area-control.md)

[事前登録](../cases/tract-limited-buffer-reuse.json)では、変更前の4ケースの生CSVと、前回計測した `Pop Dee` の生PCM、全ABI観測、段階別の件数を基準にする。咽頭と口腔のセル複製の2件を1,476回の更新から取り除き、11,809回から8,857回になると予測する。制限前後の系列と再計算の順序を先に確認し、ブラウザの描画時間は別の観測として扱う。[変更前の段階別計測](../runs/song-render-allocation-phases-20261122-b/summary.json)

## 実装と比較

`copy_into_cell_buffer()` では、役目を終えた断面列から `Vec` を取得し、既存容量へ `raw` のセルをコピーする。初期化時に作った2組を用いる。初回の形状計算のように再利用先を持たない場合は、従来の複製で確保する。毎回の幾何計算と再標本化は、格子の検査を終えてから再利用先に触る。咽頭・口腔の解剖上の管長はコピー元から引き継ぐ。以前と同じ制御周期の基準を渡して断面制限を適用する。[バッファの受け渡し](../crates/vocal-core/src/airway/tract_control.rs:157)・[セルへのコピー](../crates/vocal-core/src/airway/tract_control.rs:238)

| 項目 | 変更前 | 再利用後 |
| --- | ---: | ---: |
| 声道更新1回当たりの割り当て・再割り当て | 8 | 6 |
| 通常の128出力フレーム量子 | 16 | 12 |
| 語境界の25量子（各量子） | 32 | 24 |
| 歌唱全体（713量子） | 11,809 | 8,857 |
| 断面制限用セル列のコピー内 | 2,952 | 0 |

声道更新の1,476回で、各2件の削減を確認した。`apply()` は1,425回で11,400件から8,550件、`reapply()` は51回で408件から306件。輪郭・接触・再標本化・乱流源登録の件数は今回の変更前の計数と一致した。量子ごとの削減はすべて従来の複製の件数に一致した。計測の有無および変更前後で、Float32のPCM 91,200標本とFloat64の1,425観測点・全23値がビット一致した。[変更前の歌唱計測](../runs/song-render-allocation-phases-20261122-b/summary.json)・[変更後の要約](../runs/tract-limited-buffer-reuse-20261122-b/summary.json)・[量子別の計数](../runs/tract-limited-buffer-reuse-20261122-b/artifacts/allocations-by-quantum.csv)

変更前の現行コードから通常のCLIで保存した4ケースと、変更後の候補で出したCSV全45,360行がバイト一致した。独立検算では、各制御周期の冒頭で確定済みの面積を保持し、再計算にも同じ面積を渡す式を生CSVに適用した。舌先補正を有効にしたケースは再計算104フレームで一致した。独立の面積制限との差は最大2.78×10⁻¹⁷ cm²。通常ディレクトリと `/tmp` 起動の判定、PCM、観測、量子別CSVはバイト一致した。[変更前の断面系列](../runs/tract-limited-buffer-reuse-20261122-reference/manifest.json)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-tract-limited-buffer-reuse.py)

通常のWASM・ブラウザ・CLIでの歌唱比較は25判定に合格し、ブラウザの加工前PCMとCLIはビット一致した。通常のネイティブ計数も8,857件だった。今回の1 ms刻みのブラウザ計測では、変更前と変更後はいずれもp99が2 ms、予算を超えた量子が2件だった。体型の回帰は成人男性・成人女性・子どもの2条件・3体型混合の全5条件で70判定に合格した。固定上流のエンジン・境界条件12試験と再実装のコア・ABI38試験が通過した。主要5実行の807入力・148出力を照合し、実体484,596,157バイトをRTL9210B-CGに保存した。[ブラウザの回帰](../runs/worklet-live-song-limited-buffer-reuse-20261122/summary.json)・[体型別の回帰](../runs/tract-limited-buffer-reuse-body-regression-20261122/summary.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py tract-limited-buffer-reuse-20261122-reference --geometry-baseline
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py tract-limited-buffer-reuse-20261122-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-limited-buffer-reuse-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 ../../.venv/bin/python tools/measure_body_tract_motion.py tract-limited-buffer-reuse-body-regression-20261122
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
```

最初のコマンドはバッファ再利用を入れる前の作業状態で実行した。保存済みの比較をたどるときは、変更前のマニフェストとソーススナップショットを用いる。次は再標本化で `raw` の咽頭・口腔セル容量を引き継ぐ候補を比較する。今回と同じ1,476回の更新なら、再標本化の2,952件が削減候補になる。`raw`、`limited` と周期冒頭の基準を個別に比較する。
