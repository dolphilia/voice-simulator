# 接触グリッドの口蓋沿い累積距離を再利用する

## 読解と事前登録

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `human_airway.rs` の `commit()` は、調音値 `HumanArtic` を `HumanVocalTract::compute()` に渡してフレームを更新し、`resample()` で咽頭・口腔の面積と管長を求める。`compute()` は形状計算用の `sc` に舌・口蓋の輪郭と累積距離を保持する。接触を求めるときは口蓋の先頭を0 cmとし、`cum[i] = cum[i−1] + hypot(Δx, Δy)` で隣接点間の距離を順次足す。`closest_approach()` は舌先・舌体から各区間へ射影し、最短の符号付き距離と法線を接触補正に渡す。口蓋に近い測定線では射影点の弧長から前後を補間して舌との隙間を求め、元の測定線の隙間と滑らかに混ぜる。`the_contact_model_engages_smoothly()` は舌体を0.001 cmずつ進め、咽頭20・口腔24セルの1ステップ当たりの最大面積差が0.05 cm²未満であることを照合する。[上流の声道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[累積距離と接触](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1090)・[接触の回帰試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/speech_quality.rs#L97)

研究版では `HumanTractControl::geometry()` が輪郭を計算し、`SagittalModel::contact_grid()` が口蓋沿いの累積距離、舌先・舌体の距離と法線、測定線ごとの隙間（cm）を計算する。接触情報は `area_profile_from_contacts()` に渡り、平均・最小断面へ変換される。呼び出す側の `apply()` と `reapply()` は、声道セルを制限する周期の基準を共有する。前回はこの接触グリッドが歌唱の声道更新1,476回で4,428件を占めた。内訳の予測は口蓋沿い距離1件、測定線1件、接触付き標本1件。まず計数点の追加だけで前回の断面・PCM・既存の計数を照合する。[内訳の事前登録](../cases/contact-grid-allocation-breakdown.json)・[前回の計数](../runs/tract-resample-buffer-reuse-20261122-b/summary.json)

次の比較では口蓋沿い距離の領域だけを制御器に保持し、計算のたびに長さをリセットして上書きする。最初の形状計算で容量を確保しておけば、同じ輪郭点数の更新で追加確保が不要になると予測する。48 kHzの `Pop Dee` の予測は5,905件から4,429件、語境界の25量子が各16件から12件。通常CLIの4ケースと歌唱で断面・PCM・内部観測を比較する。[再利用の事前登録](../cases/contact-roof-buffer-reuse.json)

## 実装

`HumanTractControl` が `Vec<f64>` を保持し、初回の形状計算と `apply()`・`reapply()` で渡す。`Roof::new()` は要素数をゼロへ戻し、口蓋の現在の点数に必要な容量を確保してから、距離を元と同じ順で積算する。射影と補間には当該フレームのスライスを借りる。幾何を単発で求める公開の `contact_grid()` も同じ計算を使う。新しい単体試験は点数を減らし、重複点を含めたときの累積距離と補間を照合して、確保先も維持されることを確認する。[声道制御](../crates/vocal-core/src/airway/tract_control.rs#L107)・[累積距離と試験](../crates/vocal-core/src/anatomy/contact.rs#L102)

## 結果

| 48 kHzの `Pop Dee` での観測点 | 内訳を追加した時点 | 累積距離を再利用した時点 |
| --- | ---: | ---: |
| 口蓋沿い累積距離 | 1,476 | 0 |
| 測定線 | 1,476 | 1,476 |
| 接触標本 | 1,476 | 1,476 |
| 接触グリッド計 | 4,428 | 2,952 |
| 面積プロファイル | 1,476 | 1,476 |
| 初回の乱流源登録 | 1 | 1 |
| 歌唱全体の割り当て（713量子） | 5,905 | 4,429 |
| 語境界の割り当て（25量子、各量子） | 16 | 12 |

内訳を追加した時点で、3工程は1,476回ずつ呼ばれ、各工程の1回の割り当てが全量子で接触グリッドの合計を説明した。再利用後は全713量子で、減った件数が変更前の累積距離の件数と一致した。`apply()` 1,425回、`reapply()` 51回を含め工程ごとの呼び出し回数は等しかった。内訳と再利用の両ケースで事前登録の22判定を通過した。[内訳](../runs/contact-grid-allocation-breakdown-20261122-a/summary.json)・[再利用](../runs/contact-roof-buffer-reuse-20261122-b/summary.json)・[量子別のCSV](../runs/contact-roof-buffer-reuse-20261122-b/artifacts/allocations-by-quantum.csv)

通常CLIの4ケースは制限前後の平均・最小断面など全45,360行がバイト一致した。舌先補正ありは104周期で `reapply()` が起き、CSVから独立に求めた制限後の断面との差は全ケースで最大2.78×10⁻¹⁷ cm²だった。歌唱PCM 91,200標本とABIの1,425点・各23値は変更前後でビット一致した。研究ワークスペースと `/tmp` からの再実行でも、要約・PCM・ABI観測・量子別CSVが一致した。[再実行のマニフェスト](../runs/contact-roof-buffer-reuse-20261122-b/manifest.json)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-contact-roof-buffer-reuse.py)

Chromium 156.0.8078.4を使った通常歌唱の25判定と、成人男性・成人女性・子ども・混合を含む5条件の70判定が通過した。計測機能を指定しないネイティブ描画も4,429回だった。ブラウザの1 ms刻みの計時では変更前後ともp99は2 ms、予算を超えた量子は2件、WASMメモリ成長は0回だった。再実装のコア・ABIの40試験と、固定上流の形状連続性・エンジン・接触の12試験が通過した。固定上流の下唇引き込み試験1件には無視指定がある。5実行の822入力・156出力をサイズとSHA-256で照合し、実体486,674,297バイトをRTL9210B-CGに保存した。[通常歌唱の回帰](../runs/worklet-live-song-contact-roof-buffer-reuse-20261122/summary.json)・[体型の回帰](../runs/contact-roof-buffer-reuse-body-regression-20261122/summary.json)

## 実行コマンド

研究ワークスペースで実行した。環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。内訳の採取時点のソースは当該実行の `artifacts/source` にある。再採取時は新しい実行IDを使う。[計数のみの実行](../runs/contact-grid-allocation-breakdown-20261122-a/manifest.json)・[候補の実行](../runs/contact-roof-buffer-reuse-20261122-a/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
# 内訳の計測は再利用を入れる前のコードで実行する。
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py contact-grid-allocation-breakdown-20261122-a --case cases/contact-grid-allocation-breakdown.json
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py contact-roof-buffer-reuse-20261122-a --case cases/contact-roof-buffer-reuse.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-contact-roof-buffer-reuse-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 ../../.venv/bin/python tools/measure_body_tract_motion.py contact-roof-buffer-reuse-body-regression-20261122
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
upstream=../../../docs/reference/chimera-vocal-synth/upstream
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test geometry_continuity --test engine
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test speech_quality the_contact_model_engages_smoothly
```

測定線と接触標本には各1,476件残る。次は測定線を構成する `GridSample` の領域を保持するケースを登録し、量子別の削減数と接触断面を照合する。
