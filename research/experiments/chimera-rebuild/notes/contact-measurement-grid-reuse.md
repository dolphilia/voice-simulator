# 接触補正前の測定線を再利用する

## 読解と事前登録

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice` の制御処理は、調音値を `HumanAirway::apply()` に渡し、舌先・舌体の接触で値が変わると同じ周期に `reapply()` する。共通の `commit()` が `HumanVocalTract::compute()` と `resample()` を順に呼ぶ。`compute()` は現在の輪郭から `HumanFrame::grid` を `clear()` して再構成し、接触補正、前後方向の距離と断面への変換を同じフレーム内で行う。`resample()` の出力は咽頭・口腔の断面と管長で、同じ周期の制限基準がその後に適用される。[制御処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L501)・[声道の確定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[上流の測定線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L936)

測定線は咽頭の水平12本、始点を移動させながら180°から36°へ振る扇状31本、前歯から唇に向かう垂直6本を順に試す。距離と座標はcm。測定線の方向を `d`、その始点から輪郭線分の始端までのベクトルを `a`、輪郭線分のベクトルを `e` とすると、交点までの距離は `cross(a,e) / cross(d,e)`。外壁の最寄り交点 `t_out` がなければ標本を飛ばす。扇状の線では内側の交差を距離順に並べ、最初の組織の退出点か反対向きの探索を内壁の起点にし、途中で通る組織の厚さを足して `t_in` を求める。隙間は `max(0, t_out − t_in)`、中点は両端の平均。前方の線では下唇の引き込みに応じて内壁を補う。`a_ray_grazing_a_polyline_vertex_sees_no_tissue_layer_that_is_not_there()` は接するだけの頂点で架空の組織が計上されないことと、調音を微小に動かしたときの断面差を検査する。[上流の交差と隙間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L946)・[かすめる線の回帰試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L206)

研究版は `SagittalModel::measurement_grid()` の `GridSample` に両端、中点、隙間と部位を持ち、`contact_grid_reusing_roof()` が順に接触補正を施し、`area_profile_from_contacts()` がcm²に変換する。測定線を生成する `Vec<GridSample>` は最大49件と決まっている。現状は計測のたびに領域を確保していたので、前のフレームの容量を次のフレームで使う。空の輪郭で測定線がすべて除外される場合も、前の標本が残らず、その次の形状で同じ確保先が使えることを確認する。[研究版の測定線](../crates/vocal-core/src/anatomy/grid.rs#L41)・[接触補正](../crates/vocal-core/src/anatomy/contact.rs#L29)・[断面化](../crates/vocal-core/src/anatomy/area.rs#L66)

比較の基準は口蓋沿い累積距離まで再利用した直近の合格実行。48 kHzの `Pop Dee` 全713量子で、測定線1,476件の割り当てがなくなり、歌唱全体は4,429件から2,953件と予測する。出力フレーム44,672以上47,872未満の語境界25量子は各12件から8件。通常CLIの4条件の断面、歌唱PCMと全ABI観測を比較する。[基準の実行](../runs/contact-roof-buffer-reuse-20261122-b/summary.json)・[事前登録](../cases/contact-measurement-grid-reuse.json)

## 実装

`HumanTractControl` の `ContactGridScratch` に口蓋沿い累積距離と測定線の `Vec<GridSample>` を保持する。初回の `geometry()` で最大49本分を確保し、`apply()` と `reapply()` では `measurement_grid_into()` が長さをゼロにして現在の交差だけを書き込む。接触補正は測定線を順に借り、`Copy` 値として `ContactSample` に渡す。形状を単発で調べる公開の `measurement_grid()` と `contact_grid()` は、同じ計算を一時領域で実行する。[測定線の書き込み](../crates/vocal-core/src/anatomy/grid.rs#L41)・[接触補正](../crates/vocal-core/src/anatomy/contact.rs#L25)

`輪郭 → 測定線 → 舌と唇の接触補正 → 断面積 → 制限後の管セル`

独立に答えが分かる平行な内・外壁の試験を加えた。内壁を横座標2 cm、外壁を1 cmに置くと、水平の12本は全て隙間1 cmとなる。外壁を空にしたフレームは測定線を0件にし、外壁を0.75 cmに戻すと隙間1.25 cm、中点の横座標1.375 cmとなる。各フレームで測定線の確保先が同じことも検証した。[平行壁の試験](../crates/vocal-core/src/anatomy/grid.rs#L308)

## 結果

| 48 kHzの `Pop Dee` の割り当て | 再利用前 | 再利用後 |
| --- | ---: | ---: |
| 測定線 | 1,476 | 0 |
| 接触標本 | 1,476 | 1,476 |
| 接触グリッド計 | 2,952 | 1,476 |
| 面積プロファイル | 1,476 | 1,476 |
| 初回の乱流源登録 | 1 | 1 |
| 歌唱全体（713量子） | 4,429 | 2,953 |
| 語境界（25量子、各量子） | 12 | 8 |

比較の22判定が全て通過した。`apply()` 1,425回と `reapply()` 51回を含む全工程の呼び出し回数が一致し、全713量子で測定線の割り当て数だけ総数が減った。再利用前と後のCLI断面は4条件・45,360行がバイト一致した。舌先補正ありのケースは104周期で `reapply()` が起きた。独立計算した制限後の断面との差は4条件を通じて最大2.78×10⁻¹⁷ cm²だった。歌唱のPCM 91,200標本と1,425時点のABI全23値は変更前とビット一致した。研究ワークスペースと `/tmp` から再実行し、要約とPCM・観測・量子別計数・断面がバイト一致した。[要約](../runs/contact-measurement-grid-reuse-20261122-b/summary.json)・[量子別のCSV](../runs/contact-measurement-grid-reuse-20261122-b/artifacts/allocations-by-quantum.csv)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-contact-measurement-grid-reuse.py)

通常のChromium・CLI・固定上流による歌唱の25判定と体型別70判定が通過した。計測用の機能を指定しないネイティブ描画も2,953回。ブラウザWAVは変更前とバイト一致した。固定上流との最初のビット差は前回と同じ出力フレーム4,114で、PCMの最大絶対差は2.33×10⁻¹⁰。全区間で事前の許容差を満たした。Chromiumの1 ms刻みの計時ではp99は前後とも2 ms、予算超過は前回2量子、今回は1量子、WASMメモリ成長は前後とも0回だった。計時は各版1実行からの観察値。4実行の684入力・142出力をサイズとSHA-256で照合し、実体476,395,009バイトをRTL9210B-CGに保存した。[通常歌唱](../runs/worklet-live-song-contact-measurement-grid-reuse-20261122/summary.json)・[体型の回帰](../runs/contact-measurement-grid-reuse-body-regression-20261122/summary.json)・[保存のマニフェスト](../runs/contact-measurement-grid-reuse-20261122-b/manifest.json)

## 実行コマンド

再実装は標準のコア・ABIの41試験と、下唇の交差厚さを有効にしたコアの15試験を通過した。固定上流では形状連続性・エンジン・接触の12試験が通過し、突き出した下唇を引き込む既知の1試験に無視指定がある。[上流の形状連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L275)

環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、Bun 1.4.4、Chromium 156.0.8078.4。研究ワークスペースで次を実行した。`b` は `/tmp` を起点にPython、計測ツール、ケースを絶対パスで指定した。再実行時は新しい実行IDを使う。[再実行のマニフェスト](../runs/contact-measurement-grid-reuse-20261122-b/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py contact-measurement-grid-reuse-20261122-a --case cases/contact-measurement-grid-reuse.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-contact-measurement-grid-reuse-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 ../../.venv/bin/python tools/measure_body_tract_motion.py contact-measurement-grid-reuse-body-regression-20261122
cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
cargo test --locked --offline -p vocal-core --lib --features labial-crossing-thickness
upstream=../../../docs/reference/chimera-vocal-synth/upstream
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test geometry_continuity --test engine
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test speech_quality the_contact_model_engages_smoothly
```

次は接触後の標本 `ContactSample` を保持し、断面の生成がそのスライスを参照する候補を別ケースで試す。減るべき件数は接触標本に残る1,476件で、今回の断面とPCMを比較の基準にする。
