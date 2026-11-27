# 人間の気道で乱流源を初期確保する

## 読解と事前登録

固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` は、`HumanVoice::control()` から `HumanAirway::apply()` を呼び、接触補正で姿勢を変えた場合に `reapply()` を呼ぶ。`commit()` は声道の目標断面を計算した後に `update_noise()` で声門、最も狭い開口、その噴流が当たる歯の候補を順に登録する。狭窄の利得は最小面積（cm²）で滑らかに変わる。歯の帯域は狭窄の位置、歯までの距離（cm）と枝の体積流量（cm³/s）から求める。流速を `v = |U| / A`、噴流径を `d = 2√(A/π)`、渦の大きさを `δ = max(d, 0.17 × 歯までの距離)` として、帯域の上端は `v × d / δ²`（Hz）になる。[声道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L320)・[上流の乱流源選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)

`AirwayNetwork::set_noise_sources()` は作業側を空にして新しい一覧を書き、現在側と交換する。発生枝と前方の注入枝が等しい乱流源はハイパス用の平均 `hp` と二段ローパスの `lp1`・`lp2` を引き継ぐ。サンプルごとの `compute_noise()` は `Re = 2|U|/(ν√(πA))` で励起の強さを決め、同じ乱数列から白色雑音を生成して帯域を絞り、流れの向きに応じた枝に圧力を入れる。上流は初期化時に `noise` と `noise_next` の両方を16件分確保する。上流の `a_voiceless_affricates_frication_runs_into_the_vowel_with_no_h_after_it()` は、無声破擦音から後続母音への摩擦区間と間隔を波形から検査する。[上流の領域確保](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L427)・[状態の引き継ぎ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L785)・[圧力への変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[破擦音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs#L76)

研究版の `HumanAirway::register_turbulence()` は最大3件の候補を固定配列に並べ、`Turbulence::set_sources()` にスライスを渡す。人間用には交換先の確保を指示していなかった。通常の歌唱では開始時に一方の領域に登録済みの状態から最初の描画に入るため、初回量子で反対側の領域を確保する。哺乳類の経路で使う `reserve_noise_sources()` を人間の初期化からも呼ぶと、48 kHzの `Pop Dee` 全713量子の描画中の割り当ては1件からゼロになると予測する。[研究版の乱流源選択](../crates/vocal-core/src/airway/human/frication.rs#L39)・[領域の確保](../crates/vocal-core/src/airway/network/turbulence.rs#L56)・[基準の実行](../runs/tract-area-buffer-reuse-20261122-b/summary.json)

通常CLI4条件の断面と歌唱PCM・ABI観測を前回に照合する。登録の状態を検査する小さなケースは、96 kHzで同じ乱数シードと枝の流れを使い、乱流源を1件から最大3件へ増やし、順序と利得を変更して1件に戻す。各128内部サンプルで、二つの領域の再利用、帯域フィルタの状態と注入圧を確保なしの対照と比較する。通常の歯茎摩擦音 `/s/` は歯の帯域を独立式で計算し、PCMと観測を固定上流とも照合する。[事前登録](../cases/human-noise-source-reserve.json)・[歯茎摩擦音の設定](../cases/sibilant-s.json)

## 実装と状態の照合

`HumanAirway::with_tract()` が、乱流源を選ぶ固定配列と共通の上限3件を `reserve_noise_sources()` に渡す。確保するのは現在と次回の登録用の二つの配列。実際の登録、流れと狭窄による励起、注入圧の計算順は従来どおり。計測器では、乱流源の登録を `control` の内側かつ `apply`・`reapply` の外側として扱い、最初の量子の `turbulence` とその親の `control` から1件減ることを期待値にした。過去の内訳計測、測定線と断面標本の再利用の3実行を保存済みデータから再計算し、従来と同じ量子別CSVになった。[初期化](../crates/vocal-core/src/airway/human.rs#L272)・[計数の照合](../tools/measure_tract_limited_buffer_reuse.py#L41)

`形状と流量 → 乱流源の登録 → 帯域フィルタ → 枝への注入圧`

人間の気道の初期化を通した試験で、二つの確保先が1件、3件、順序と利得を変えた3件、1件の登録ごとに交換されることを確認した。同じシードを使う未確保の対照と、登録直後の一次ハイパス用の平均、二段ローパスの状態と励起振幅が一致した。各登録後128サンプルでも、全512内部サンプルで状態と枝の注入圧がビット一致した。テストの各区間でゼロ以外の注入圧を観測した。[3件の登録とフィルタ状態の試験](../crates/vocal-core/src/airway/network/turbulence.rs#L171)

## 結果

| 48 kHzの `Pop Dee` の描画中の割り当て | 初期確保前 | 初期確保後 |
| --- | ---: | ---: |
| 初回量子（出力フレーム0〜127） | 1 | 0 |
| 後続712量子 | 0 | 0 |
| 合計（713量子） | 1 | 0 |

登録した22判定が通過した。乱流源の登録は前後とも1,476回。他の工程の呼び出し回数と割り当ては一致した。CLIの4条件・45,360行の断面と、歌唱PCM 91,200標本、1,425点のABI全23値がバイト一致した。CSVから独立に計算した制限後の断面との差は最大2.78×10⁻¹⁷ cm²。研究ワークスペースと `/tmp` から実行し、要約・波形・ABI観測・量子別計数・断面がバイト一致した。[比較結果](../runs/human-noise-source-reserve-20261122-b/summary.json)・[量子別のCSV](../runs/human-noise-source-reserve-20261122-b/artifacts/allocations-by-quantum.csv)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-human-noise-source-reserve.py)

通常CLIの `/s/` は7判定を通過し、歯の乱流源を5,568フレームで照合した。帯域上端の独立式との差は最大3.64×10⁻¹² Hz、利得の差は8.47×10⁻²²。固定上流とのPCMの最大絶対差は3.64×10⁻¹²で、前に保存した研究版のPCMと観測CSVは今回とバイト一致した。歌唱の通常ブラウザ・CLI・固定上流の25判定と、体型・姿勢70判定も通過した。歌唱のブラウザWAVは初期確保前とバイト一致した。固定上流との歌唱PCMの最大差2.33×10⁻¹⁰と最初のビット差の出力フレーム4,114は前回と一致し、許容差を満たした。[歯茎摩擦音](../runs/sibilant-s-human-noise-source-reserve-20261122/summary.json)・[通常歌唱](../runs/worklet-live-song-human-noise-source-reserve-20261122/summary.json)・[体型の回帰](../runs/human-noise-source-reserve-body-regression-20261122/summary.json)

ブラウザの計時はp99が前後とも2 ms。予算超過は前回2量子、今回は1量子、WASMメモリ成長は前後とも0回だった。計時は1 ms刻みで各版1実行。標準のコアとABIは44試験、下唇の交差厚さを有効にしたコアは18試験、固定上流の破擦音とエンジンは9試験が通過した。5実行の806入力・156出力をサイズとSHA-256で照合し、実体531,106,329バイトをRTL9210B-CGに保存した。[保存マニフェスト](../runs/human-noise-source-reserve-20261122-b/manifest.json)

## 実行コマンド

環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、Bun 1.4.4、Chromium 156.0.8078.4。下記は研究ワークスペースから実行した。`b` は `/tmp` からPython、計測ツール、ケースを絶対パスで指定した。再計測では新しい実行IDを使う。[再実行の条件](../runs/human-noise-source-reserve-20261122-b/manifest.json)

```bash
work=/Volumes/RTL9210B-CG/voice-simulator
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=18000000 ../../.venv/bin/python tools/measure_tract_limited_buffer_reuse.py human-noise-source-reserve-20261122-a --case cases/human-noise-source-reserve.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=220000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-human-noise-source-reserve-20261122 --live
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 ../../.venv/bin/python tools/measure_sibilant.py sibilant-s-human-noise-source-reserve-20261122 s
CARGO_TARGET_DIR="$work/build/chimera-rebuild-debug" CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=500000000 ../../.venv/bin/python tools/measure_body_tract_motion.py human-noise-source-reserve-body-regression-20261122
cargo test --locked --offline -p vocal-core -p vocal-wasm --lib
cargo test --locked --offline -p vocal-core --lib --features labial-crossing-thickness
upstream=../../../docs/reference/chimera-vocal-synth/upstream
cargo test --manifest-path "$upstream/Cargo.toml" --locked --offline -p chimera --test affricates --test engine
```

次は44.1 kHzの英語発話「確認用07」で、発話コマンド適用時と描画中の割り当てをそれぞれ測る。歌唱とは入力と準備処理が異なる。保存済みの44.1 kHzのPCM 98,790標本と内部観測を基準にし、開始直後と発話中を含めて計測する。[発話の基準ケース](../cases/worklet-live-tsp-44100.json)・[保存済みの結果](../runs/worklet-live-tsp-44100-20261122-a/summary.json)
