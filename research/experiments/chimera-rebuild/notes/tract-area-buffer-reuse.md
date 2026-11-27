# 断面標本の領域を再利用する

## 読解と事前登録

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::control()` は、調音値と制御周期（秒）で `HumanAirway::apply()` を呼ぶ。接触制約で調音値が変わると `reapply()` を呼び、同じ制御周期の先頭の面積を変化量制限の基準とする。`commit()` は以前の `HumanFrame` を作業先に使い、`HumanVocalTract::compute()` が測定格子の各標本に面積と中心線の距離を記録する。[制御の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L499)・[声道の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)

面積（cm²）の入力は、接触補正後の隙間 `d`（cm）、測定線の部位、舌先と前歯の位置、唇の幅など。咽頭では `a × d^b`、口腔では舌先の前後に応じた二つのべき乗則の補間、前歯から唇にかけてはべき乗則と楕円の開口 `π/4 × d × 唇幅` の補間を使う。隣接標本の大きい方の1.35倍で孤立した面積のピークを抑え、側音では舌先の近くに横の開口を加える。喉頭上部の管長から始めて隣接する中点間の距離を足し、中心線上の位置 `s`（cm）と咽頭端・前歯・唇の位置を得る。`resample()` は各セルの8分割点で面積を補間し、調和平均 `8 / Σ(1/A)` と最小値を求める。格子点または分割点に閉鎖があればそのセルを閉じる。`no_area_jumps_on_the_way_between_calibrated_vowels()` は体型別の母音間遷移の断面を300分割して、急変が疑われる区間で細分化した面積差を検証する。[上流の断面化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1184)・[再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[母音間の連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L155)

研究版の `area_profile_from_contacts()` は、領域別の係数を使って `AreaSample` を作る。確定後の断面列は `TractTargets::area_samples` が所有し、CLIやWASMの観測に使われる。計算中の標本列は、断面生成や再標本化が失敗した場合にも、その確定済みの列とは別に保持する。96 kHz・成人男性で口腔のセル数を固定し、唇を後退させて口腔長が不足すると、`TractSampling::resample_reusing()` は `c / (fs × セル長)` が0.97を超える姿勢を拒む。この条件を `apply()` と `reapply()` で試し、続く有効な更新で確定済みと作業用の領域が交換されることを確認する。[研究版の断面生成](../crates/vocal-core/src/anatomy/area.rs#L60)・[研究版の声道制御](../crates/vocal-core/src/airway/tract_control.rs#L176)・[観測の入口](../crates/vocal-core/src/voice.rs#L575)

48 kHzの `Pop Dee` では、1,476回の声道更新で面積プロファイルが各1件ずつ割り当てを行う。断面標本用の領域を2つ確保して繰り返し使うと、全713量子の描画は1,477件から乱流源の初回登録1件だけになると予測する。出力フレーム44,672以上47,872未満の語境界25量子は各4件から0件。通常CLIの4条件の断面、歌唱PCMと全ABI観測を基準版に照合する。[基準の実行](../runs/contact-sample-buffer-reuse-20261122-b/summary.json)・[事前登録](../cases/tract-area-buffer-reuse.json)

## 実装とエラー時の観測

初期化時に最大49本分の領域を二つ確保する。`area_profile_from_contacts_reusing()` が作業側の長さをゼロにし、前回と同じ順序で現在の標本を書き込む。断面生成に成功すると作業領域を `AreaProfile` が引き継ぐ。再標本化が失敗したときは作業領域として戻す。成功すると `apply()` または `reapply()` が新しい断面を確定し、それまで確定していた領域を次の計算に回す。単発の `area_profile()` は一時領域で同じ計算を行い、呼び出し側が所有する断面を返す。[断面生成](../crates/vocal-core/src/anatomy/area.rs#L74)・[再標本化への受け渡し](../crates/vocal-core/src/airway/tract_control.rs#L225)

`接触標本 → 作業中の断面 → 再標本化と制限 → 確定済みの断面`

平行壁の外壁を測定範囲の外へ移す試験では断面標本がゼロ件になり、領域を保持したままエラーを返した。外壁を戻すと同じ領域で隙間1.25 cmと `2 × 1.25^1.4` cm²の断面を10⁻¹²以内で得た。別の試験では96 kHzの成人男性で唇を1.6 cm突き出し、解剖上の口腔長でクーラン数0.97以下となる最大の口腔セル数を選んだ。そのセル数のまま唇の値を−0.2 cmに変えると `apply()` と `reapply()` の両方が拒否した。各エラーの前後で確定済み全標本の11値がビット一致し、確定済みと作業用の確保先を保持した。途中に有効な姿勢を入れると2つの領域が交代した。[平行壁の試験](../crates/vocal-core/src/anatomy/contact.rs#L237)・[口腔長不足の試験](../crates/vocal-core/src/airway/tract_control.rs#L365)

## 結果

| 48 kHzの `Pop Dee` の割り当て | 再利用前 | 再利用後 |
| --- | ---: | ---: |
| 面積プロファイル | 1,476 | 0 |
| 語境界（25量子、各量子） | 4 | 0 |
| 初回の乱流源登録 | 1 | 1 |
| 歌唱全体（713量子） | 1,477 | 1 |

登録した22判定が通過した。`apply()` 1,425回と `reapply()` 51回の全てで割り当てがゼロとなり、713量子のうち712量子で割り当てがなかった。通常CLIの4条件・45,360行の断面と、歌唱PCMの91,200標本、1,425点のABI全23値はバイト一致した。舌先補正ありのCLI条件では104周期で `reapply()` があり、4条件のCSVから独立に計算した制限後の断面は最大誤差2.78×10⁻¹⁷ cm²で一致した。研究ワークスペースと `/tmp` からそれぞれ実行し、要約・PCM・ABI観測・量子別計数・断面の一致を確認した。[比較結果](../runs/tract-area-buffer-reuse-20261122-b/summary.json)・[量子別のCSV](../runs/tract-area-buffer-reuse-20261122-b/artifacts/allocations-by-quantum.csv)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-tract-area-buffer-reuse.py)

通常のChromium・CLI・固定上流の歌唱25判定と体型・姿勢70判定が通過した。ブラウザWAVは変更前とバイト一致し、通常のネイティブ描画も割り当て1回だった。固定上流とのPCMの最初のビット差は従来と同じ出力フレーム4,114、最大絶対差2.33×10⁻¹⁰で、全区間が許容差内だった。ブラウザのp99は前後とも2 ms、予算超過は前後とも2量子、WASMメモリ成長は前後とも0回だった。計時は1 ms刻みで各版1実行。標準のコアとABIは43試験、下唇の交差厚さを有効にしたコアは17試験、固定上流は12試験が通過した。固定上流では既知の下唇引き込み試験1件に無視指定がある。4実行の684入力・142出力をサイズとSHA-256で照合し、実体476,395,215バイトをRTL9210B-CGに保存した。[通常歌唱](../runs/worklet-live-song-tract-area-buffer-reuse-20261122/summary.json)・[体型の回帰](../runs/tract-area-buffer-reuse-body-regression-20261122/summary.json)・[保存マニフェスト](../runs/tract-area-buffer-reuse-20261122-b/manifest.json)

## 実行コマンド

環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、Bun 1.4.4、Chromium 156.0.8078.4。下記は研究ワークスペースから実行した。別ディレクトリからの実行 `b` では `/tmp` からPython、計測ツール、ケースを絶対パスで指定した。再計測では新しい実行IDを使う。[再実行の条件](../runs/tract-area-buffer-reuse-20261122-b/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py tract-area-buffer-reuse-20261122-a --case cases/tract-area-buffer-reuse.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-tract-area-buffer-reuse-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 ../../.venv/bin/python tools/measure_body_tract_motion.py tract-area-buffer-reuse-body-regression-20261122
cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
cargo test --locked --offline -p vocal-core --lib --features labial-crossing-thickness
upstream=../../../docs/reference/chimera-vocal-synth/upstream
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test geometry_continuity --test engine
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test speech_quality the_contact_model_engages_smoothly
```

次は描画開始時の乱流源登録1件を追う。人間の経路では声門・狭窄・歯の最大3件を候補にする。哺乳類で使っている `reserve_noise_sources()` は、登録時に交換する両方の領域を初期確保する。人間にもその入口を使えるかを調べ、初回量子の件数と、乱流源の更新で引き継ぐフィルタ状態、同じシードのPCMを照合する。[人間の乱流源選択](../crates/vocal-core/src/airway/human/frication.rs#L39)・[乱流源の領域とフィルタ状態](../crates/vocal-core/src/airway/network/turbulence.rs#L56)
