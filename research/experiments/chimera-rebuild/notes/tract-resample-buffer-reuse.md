# 再標本化で咽頭・口腔のセル容量を再利用する

## 読解と予測

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::control()` は調音を進め、`HumanAirway::apply()` を呼ぶ。接触補正が起きた場合は同じ制御周期内に `reapply()` する。`commit()` は保持済みの形状と面積の領域を使い、`HumanVocalTract::resample()` に咽頭・口腔の平均と最小断面を書き込む。位置・管長はcm、断面はcm²。管の区間をセル数で割り、セルごとの8点の調和平均 `8 / Σ(1/A)` と、測定点・補間点の最小断面を求める。断面が `1e-5 cm²` 以下の測定点または補間点は、セルを閉鎖する。固定上流の形状連続性試験も、固定長の咽頭・口腔配列へ再標本化して、姿勢を変えたときの面積差を観測する。[呼び出し順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs:499)・[再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs:1305)・[形状連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs:23)

研究版は `TractSampling` がセル数と指定口腔格子の安定長を検査し、`AreaProfile::resample()` がプロファイルの長さ、距離順、面積の有限性と非負を検査する。断面制限前の `raw` は通常CLIの観測点と制限後の `limited` の入力。制限には前周期の `limited` が要るため、今回の形状が有効と確定した時点で旧 `raw` のセル領域を使える。[研究版の再標本化](../crates/vocal-core/src/anatomy/resample.rs)・[断面目標の更新](../crates/vocal-core/src/airway/tract_control.rs)

[事前登録](../cases/tract-resample-buffer-reuse.json)では、制限用のセル領域を再利用済みの版を基準にする。咽頭・口腔の再標本化先だけを再利用し、48 kHzの歌唱 `Pop Dee` の全1,476更新で各2件、計2,952件を減らす。予測は8,857件から5,905件。前の比較で観測した語境界の25量子は、各24件から16件。PCM、全ABI観測、および通常CLIの4ケースで保存した制限前後の断面と長さを照合する。[基準の計数と断面照合](../runs/tract-limited-buffer-reuse-20261122-b/summary.json)

## 実装と結果

制御周期の `apply()` と接触補正後の `reapply()` の両方から、前の `current.raw` を再標本化へ渡す。指定格子の安定長、プロファイルの長さ・距離順・面積を先に検査し、成功した場合にだけ咽頭・口腔の `Vec` を取り出す。各ベクターの要素を消して同じセル計算の出力で埋め、得られた管長とともに新しい `raw` に収める。初期化時や面積配列を新規に返す公開APIでは空の領域から同じ処理を通る。無効な面積を末尾に置くテストでは、検査で失敗した直後のセル値・管長を照合し、有効な入力に戻すと両方とも元のセル領域を再利用できた。[再標本化先の切り替え](../crates/vocal-core/src/anatomy/resample.rs:46)・[制御経路からの接続](../crates/vocal-core/src/airway/tract_control.rs:166)・[エラーと再試行のテスト](../crates/vocal-core/src/anatomy/resample.rs:185)

| 項目 | 変更前 | 再利用後 |
| --- | ---: | ---: |
| 再標本化の確保・再確保 | 2,952 | 0 |
| 声道更新1回当たりの割り当て | 6 | 4 |
| 通常の128出力フレーム量子 | 12 | 8 |
| 語境界の25量子（各量子） | 24 | 16 |
| 歌唱全体（713量子） | 8,857 | 5,905 |

全713量子で、減った件数は変更前に再標本化が占めていた件数と一致した。接触グリッド4,428件、面積プロファイル1,476件、初回量子の乱流登録1件が残った。更新回数は `apply()` が1,425回、`reapply()` が51回。各段階の呼び出し回数を保存し、出力開始から終了まで照合した。[変更後の割り当て内訳](../runs/tract-resample-buffer-reuse-20261122-b/summary.json)・[量子別のCSV](../runs/tract-resample-buffer-reuse-20261122-b/artifacts/allocations-by-quantum.csv)

通常CLIの4ケースで、制限前後の平均・最小断面、管長、接触、軟口蓋の全45,360行が変更前とバイト一致した。舌先補正ありでは104周期で `reapply()` が起き、独立に計算した制限後の断面との差は全ケースで最大2.78×10⁻¹⁷ cm²。歌唱のPCM 91,200標本とABIの1,425点・各23値は、計測の有無と変更前後でビット一致した。研究ワークスペースと `/tmp` からの再実行でも、生データ・要約がバイト一致した。[変更前の断面と歌唱](../runs/tract-limited-buffer-reuse-20261122-b/manifest.json)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-tract-resample-buffer-reuse.py)

通常のブラウザ・CLI・固定上流を比較する歌唱の25判定と、成人男性・女性、子どもと混合を含む5条件の70判定が通過した。計測機能を指定しないネイティブの歌唱でも割り当ては5,905回だった。ブラウザの1 ms刻みの計測では、変更前後ともp99は2 ms、予算超過は2量子、WASMメモリ成長は0回。再実装のコア・ABIの39試験、固定上流の境界・エンジン・連続性の17試験が通過した。固定上流で既知の下唇引き込み試験1件には無視指定がある。今回の4実行は684入力・142出力をサイズとSHA-256で照合し、実体476,140,493バイトをRTL9210B-CGに保存した。[通常歌唱の回帰](../runs/worklet-live-song-resample-buffer-reuse-20261122/summary.json)・[体型の回帰](../runs/tract-resample-buffer-reuse-body-regression-20261122/summary.json)・[保存マニフェスト](../runs/tract-resample-buffer-reuse-20261122-b/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py tract-resample-buffer-reuse-20261122-a --case cases/tract-resample-buffer-reuse.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-resample-buffer-reuse-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 ../../.venv/bin/python tools/measure_body_tract_motion.py tract-resample-buffer-reuse-body-regression-20261122
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
```

次は、最も件数の多い接触グリッドの内訳を、口蓋沿い累積距離の準備、測定線の生成、接触付き標本への変換に分ける。各段階が1,476回の呼び出しで確保する領域を確認し、まず累積距離の領域を再利用する候補を別ケースで比較する。
