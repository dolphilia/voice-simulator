# 接触補正後の標本を再利用する

## 読解と事前登録

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::control()` は、調音状態 `x` と制御周期 `dt`（秒）を `HumanAirway::apply()` に渡す。接触制約で調音値を変えた場合は同じ周期に `reapply()` してから気道のブロックを始める。両者が呼ぶ `commit()` は `HumanVocalTract::compute()` で側断面と測定格子を更新し、`resample()` に渡して、咽頭・口腔の平均面積と最小面積（cm²）および管長（cm）を得る。同じ周期内の再計算は、周期開始前の面積を変化量制限の基準にする。[声道への入力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L501)・[声道の確定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)

上流の `compute()` は既存の `HumanFrame::grid` に測定線を並べ、各標本の隙間 `d`（cm）をその場で直す。口蓋近くでは、測定線の外壁側端点を口蓋に射影し、舌輪郭との符号付き距離 `dc` を調べる。接触が近い場合は弧長方向の前後4点も調べ、最小の距離を採用する。舌先・舌体の押し込みに応じて弧長方向の探索幅は基準体型で片側0.1〜0.2 cmになる。非負にした距離を `dp`、滑らかな重みを `cap` と `w` とすると、`dm = d + (min(d, dp) − d) × cap`、補正後は `dm + (dp − dm) × w`。前歯より前ではさらに唇の開きと端からの距離の二乗で隙間を制限する。続く断面計算は部位ごとに補正後の隙間のべき乗や楕円開口を使い、中心線に沿った距離を付ける。`the_contact_model_engages_smoothly()` は舌体の高さを0.001 cmずつ変え、咽頭20・口腔24セルの隣接姿勢間の面積差が0.05 cm²未満か調べる。[上流の接触・断面化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1121)・[接触の回帰試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/speech_quality.rs#L97)

変更前の研究版では `contact_grid_with_scratch()` が測定線の `GridSample` と補正後の隙間を `ContactSample` にまとめる。`area_profile_from_contacts()` はその順序で `AreaSample` を作り、測定線、補正後の隙間、面積と中心線の距離を観測できるようにする。接触標本は前回まで形状の更新ごとに `Vec` を生成し、断面生成時に消費していた。今回の候補では接触標本の領域を制御器で保持し、断面生成が借りて読む。単発の公開 `contact_grid()` でも、観測用に所有する標本列を得られる形を保つ。[研究版の接触標本](../crates/vocal-core/src/anatomy/contact.rs#L18)・[断面標本](../crates/vocal-core/src/anatomy/area.rs#L66)

48 kHzの `Pop Dee` の全713量子で、1,476回の声道更新につき各1件減ると予測する。全体は2,953件から1,477件、出力フレーム44,672〜47,871の語境界25量子はそれぞれ8件から4件になる。接触グリッドの3工程の割り当ては全てゼロとなる見込み。通常CLIの4条件と歌唱PCM・ABIのほか、平行壁の形状で無効なフレームを経た後の標本と先頭断面を手計算と照合する。[基準の実行](../runs/contact-measurement-grid-reuse-20261122-b/summary.json)・[事前登録](../cases/contact-sample-buffer-reuse.json)

## 実装

`ContactGridScratch` に `Vec<ContactSample>` を加えた。初回の形状計算で最大49本分の容量を確保し、`contact_grid_into()` は毎回長さをゼロにして、その時点の測定線から標本を同じ順序で書き込む。結果の舌先・舌体の距離と法線を返し、断面生成には現在の標本をスライスで渡す。各 `AreaSample` は元の測定線と補正後の隙間を値として所有するので、接触標本の領域を次の更新に回せる。単発の公開 `contact_grid()` は同じ処理を呼び、呼び出し側に標本の所有権を渡す。[接触標本の書き込み](../crates/vocal-core/src/anatomy/contact.rs#L44)・[断面への受け渡し](../crates/vocal-core/src/airway/tract_control.rs#L217)

`測定線 → 接触補正した標本 → 断面標本と中心線 → 再標本化した管セル`

平行壁の試験では舌を遠ざけ、水平の先頭測定線の隙間を1 cmにした。外壁を測定範囲外へ移すと接触標本は0件になり、借用先の断面計算は既存のエラーを返した。元と異なる位置に外壁を戻すと、同じ確保先で隙間1.25 cmと、独立に求めた先頭の咽頭断面 `2 × 1.25^1.4` cm² を10⁻¹²以内で再現した。[平行壁の試験](../crates/vocal-core/src/anatomy/contact.rs#L237)

## 結果

| 48 kHzの `Pop Dee` の割り当て | 再利用前 | 再利用後 |
| --- | ---: | ---: |
| 接触標本 | 1,476 | 0 |
| 接触グリッド計 | 1,476 | 0 |
| 面積プロファイル | 1,476 | 1,476 |
| 初回の乱流源登録 | 1 | 1 |
| 歌唱全体（713量子） | 2,953 | 1,477 |
| 語境界（25量子、各量子） | 8 | 4 |

22判定が全て通過した。`apply()` 1,425回と `reapply()` 51回を含め、各工程の呼び出し回数は等しかった。全713量子で接触標本の基準件数だけが減った。通常CLIの4条件・45,360行の断面がバイト一致し、舌先補正ありの条件では104周期に再計算があった。CSVから独立に計算した制限後の断面との差は4条件で最大2.78×10⁻¹⁷ cm²。歌唱PCMの91,200標本と1,425点のABI全23値がビット一致した。研究ワークスペースと `/tmp` からの実行で、要約・PCM・ABI観測・量子別計数・断面がバイト一致した。[比較結果](../runs/contact-sample-buffer-reuse-20261122-b/summary.json)・[量子別のCSV](../runs/contact-sample-buffer-reuse-20261122-b/artifacts/allocations-by-quantum.csv)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-contact-sample-buffer-reuse.py)

通常のChromium・CLI・固定上流の歌唱25判定と体型・姿勢70判定が通過した。通常のネイティブ描画も1,477回で、ブラウザWAVは再利用前とバイト一致した。固定上流とのPCMの最初のビット差は以前と同じ出力フレーム4,114、最大絶対差は2.33×10⁻¹⁰で、全区間で事前の許容差内だった。Chromiumのp99は前後とも2 ms、予算超過は前回1量子、今回は2量子、WASMメモリ成長は前後とも0回。計時は1 ms刻みで各版1実行。標準のコアとABIは42試験、下唇の交差厚さを有効にしたコアは16試験、固定上流は12試験が通過した。固定上流には無視指定の下唇引き込み試験が1件ある。4実行の684入力・142出力をサイズとSHA-256で照合し、実体476,394,281バイトをRTL9210B-CGに保存した。[通常歌唱](../runs/worklet-live-song-contact-sample-buffer-reuse-20261122/summary.json)・[体型の回帰](../runs/contact-sample-buffer-reuse-body-regression-20261122/summary.json)・[保存マニフェスト](../runs/contact-sample-buffer-reuse-20261122-b/manifest.json)

## 実行コマンド

環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、Bun 1.4.4、Chromium 156.0.8078.4。次のコマンドは研究ワークスペースから実行した。`b` は `/tmp` からPython、計測ツール、ケースを絶対パスで指定した。再計測では新しい実行IDを使う。[再実行の条件](../runs/contact-sample-buffer-reuse-20261122-b/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py contact-sample-buffer-reuse-20261122-a --case cases/contact-sample-buffer-reuse.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-contact-sample-buffer-reuse-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 ../../.venv/bin/python tools/measure_body_tract_motion.py contact-sample-buffer-reuse-body-regression-20261122
cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
cargo test --locked --offline -p vocal-core --lib --features labial-crossing-thickness
upstream=../../../docs/reference/chimera-vocal-synth/upstream
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test geometry_continuity --test engine
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test speech_quality the_contact_model_engages_smoothly
```

次は断面標本 `AreaSample` の生成に残る1,476回を対象にする。断面化や再標本化が失敗したときも、観測用の最後に確定した断面を読み出せることを最小ケースに含める。
