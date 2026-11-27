# TSP確認用4発話の強勢付き単母音と測定窓

[事前登録](../cases/tsp-stressed-vowel-formants-held-out.json)の対象は、前回の[MFAの照合](tsp-phone-boundaries-held-out.md)を通過した2本文・2話者。録音・固定上流の合成・研究版の合成で対応した主強勢の単母音だけを採る。本文 `61_01` では `plea`・`funds`・`seems`・`come`・`again` の5か所、`61_02` では `lent` の1か所が該当する。波形は前回入力した録音のPCM16と、[元の発話区間長比較](tsp-active-duration-original.md)でCLIから保存した合成のfloat32。合成の区間はMFAに渡したノイズ添加波形から得ており、LPCには対応する添加前の波形を使う。

## 固定上流の読解

- CLIの `run` は `compare tsp` を `tsp::run` に渡す。録音に保存済みのMFA注釈を読み、同じ本文を体型別に合成し、合成側に辞書制約付きMFAを適用する。`measure_pair` は録音と合成の音素列をIPAの編集距離で対応させる。逆向きに辿る際は同コストなら対角、録音の音素を飛ばす方向の順で選ぶ。対応した両側には合成側の第1強勢判定を与える。この実験は前回のMFAで整列した録音を使い、固定CLIによる通常実行ではリポジトリに同梱の録音注釈を使う。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[録音注釈](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L49)・[対応と測定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L761)
- `read_wav` はPCM16を32768で割り、float32は値を拡張して扱う。`Sig::new` は音声に中心対称のBlackman窓付きsincのFIR（95タップ、カットオフ5400 Hz）をかけ、4標本につき1標本を残す。畳み込みの中心は入力時刻に揃い、ファイル外の入力はゼロとして扱う。結果の12 kHz列 `lo` は発話全体で作られるので、母音を終点で切ってからフィルタリングする場合と結果が変わる。F0と雑音床も `Sig::new` で得るが、`Sig::formants` の採否はLPC極の条件で決まる。[WAV読み込み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L331)・[前処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L438)
- `measure` は単母音で `Sig::formants` を呼ぶ。母音開始 `t0`・終了 `t1` の単位は秒。中心は `t = t0 + q × (t1 − t0)`、開始標本は `trunc(t × 12000) − 150`、長さは300標本。固定の `q` は0.35、0.50、0.65。窓が波形外なら飛ばす。母音境界は切り詰めに使わないため、短い母音は基準窓にも前後が混ざり得る。[測定対象](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L731)・[窓](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)
- `estimate_formants` は窓の先頭で前標本をゼロとし、`x[n] − 0.97 x[n−1]` にHamming窓を掛ける。ラグごとに積を足した自己相関に `exp(−0.5 × (2π × 40 × lag / fs)²)` を掛ける。Levinson–Durbinは予測誤差を `r[0] × (1 + 10⁻⁹) + 10⁻³⁰` で初期化し、次数を一つずつ上げて反射係数と残差を更新する。F系列は12次、M系列は14次。続いて `poly_roots` がDurand–Kerner法で多項式の根を求める。上半平面の極から `arg(z) × fs / (2π)` と `−log(|z|) × fs / π` を取り、周波数と帯域幅をHzで得る。[自己相関と係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L6)・[極の探索](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L54)・[推定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)
- 150 Hz以上・帯域幅600 Hz以下の極を周波数順に並べる。F1は1300 Hz未満・帯域幅500 Hz未満の最初の極。F2はF1＋200 Hzより高く3500 Hz未満の最初の極。両方がある窓だけを採り、F1とF2の中央値を個別に取る。1窓だけでも値が出て、0窓なら両値が欠測になる。集計側の `F1`・`F2` 項目は第1強勢の同じ母音に絞る。既存試験は対応の順序、欠測の扱い、TypeScript基準の自己相関・LPC係数・極・推定値を検査する。[母音の集計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1013)・[中央値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L410)・[比較試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1528)・[LPCの基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)

## 窓を変えた比較

固定ソースを `git archive` から外部ディスク上の作業用ディレクトリに展開し、CLIへ[観測用の入口](../tools/upstream_tsp_formant_probe.rs)を足した。元の `match_phones`・`Sig::new`・`Sig::formants` を直接実行する。窓別の極と採否も同じRustライブラリで出力する。

[研究CLI](../tools/measure_tsp_stressed_vowel_formants.py)は、ND配列の畳み込みと自己相関、SciPyで組んだToeplitz行列の直接解法、NumPyのコンパニオン行列の固有値で独立に推定する。基準の3窓で各母音の中央値を出し、10%と90%の各窓は50%窓と個別に比較する。窓の12 kHz標本区間のうちMFAの母音区間外に出た長さをmsで記録する。窓が波形外、F1なし、F2なしは別の欠測理由とした。フィルタが片側47入力標本を参照する影響やMFA区間そのものの誤差は残る。

## 実測

各行の分母は12母音に対する2つの境界寄りの窓。周波数差は同一波形の50%窓を引いた絶対値で、両方でF1・F2が得られたときだけ集計した。35・50・65%の108窓はすべて母音区間内にあり、全窓でF1・F2が揃った。

| 波形 | 母音区間をはみ出した窓 | F1・F2が揃った窓 | F1かF2が100 Hz超動いた窓 | `|ΔF1|`・`|ΔF2|` の中央値 |
| --- | ---: | ---: | ---: | ---: |
| 録音 | 22 / 24 | 23 / 24 | 18 / 23 | 27.6・155.8 Hz |
| 固定上流の合成 | 24 / 24 | 24 / 24 | 8 / 24 | 26.2・33.4 Hz |
| 研究版の合成 | 20 / 24 | 24 / 24 | 9 / 24 | 26.1・33.2 Hz |

- 境界寄りの72窓中66窓が母音区間をはみ出した。録音 `FK61_02` の `lent` の90%窓は終了を4.42 ms過ぎ、最も低い候補の帯域幅が510.63 Hzだった。F1の500 Hz未満という条件を満たす極が無く、今回唯一の欠測になった。
- 録音 `MK61_01` の `seems` で50%と10%を比べると、F2は993.37 Hzから2318.26 Hzに変わった。50%窓には帯域幅508.89 Hzの993.37 Hzと帯域幅59.45 Hzの2323.81 Hzの極があり、固定のF2選択は低い方を採った。10%窓では前者が候補一覧から消え、後者に相当する極が採られた。基準3窓でも2309–2324 Hzの狭いピークが続いており、PCM上の振幅や母音の共鳴そのものを解釈するには、どの極をF2と呼ぶかも調べる必要がある。
- 基準3窓の中央値で、研究版と固定上流の絶対差は12か所の中央値でF1 1.54 Hz、F2 3.97 Hz、最大で16.24・16.43 Hzだった。各合成と録音の絶対差の中央値は固定上流で44.08・123.11 Hz、研究版で42.73・119.28 Hz。この4録音では `61_02` の対象が `lent` だけで、母音ごとの偏りや合成の品質評価はこの集計から判断できない。

### 初回の不一致と判定の改訂

[初回の判定](../runs/tsp-stressed-vowel-formants-held-out-20261122-a/manifest.json)は、極の一覧が8窓で異なり不合格だった。該当は `MK61_01` の両合成のみ。最初の差は固定上流の `funds` の50%窓（12 kHzの開始標本9389）で、Rustが周波数6000.0 Hz・帯域幅317.10786 Hzの極を返した。直接解法の負の実根 `−0.920333988535` は帯域幅317.10786 Hzに相当し、多項式の絶対残差は約 `1.18×10⁻¹⁴`。ほかの7窓も同じ帯域幅を持つ負の実根で説明できた。Rustは虚部が厳密に正の根を採り、負の実軸に近い根で虚部の丸めが採否に影響する。極の差はF2の上限3500 Hzより高く、F1・F2を選ぶ段には伝わらなかった。[初回の数値](../runs/tsp-stressed-vowel-formants-held-out-20261122-a/summary.json)

ケース第2版では、ナイキストから `10⁻⁸ Hz` 以内で、かつ負の実根と帯域幅が0.05 Hz以内で一対一に対応する極を軸上の差として記録する。全極の初回判定、軸上の差が出た窓、元の固定Rustの出力は保存した。F1・F2と欠測を比較する基準は0.05 Hzのまま。改訂後は180窓と36母音の中央値が一致し、最大差は極の周波数・帯域幅で `9.17×10⁻⁹ Hz` 未満、中央値で `7.94×10⁻¹¹ Hz` 未満だった。無音の対照では窓が波形外で3件、F1が無く2件の欠測を得た。[改訂後の数値](../runs/tsp-stressed-vowel-formants-held-out-20261122-final/summary.json)・[固定Rustの全極](../runs/tsp-stressed-vowel-formants-held-out-20261122-final/artifacts/upstream-formants.json)

## 再現

研究ワークスペースで以下を実行する。固定上流のソースコピーとCargoの一時出力をRTL9210B-CGに置き、実行後に取り除く。入力の12 WAVはすべて過去の実行をマニフェストのSHA-256で照合して読む。作成した解析結果は実行マニフェストに残る。録音のWAVには補助チャンクがあり、SciPyはそのチャンクを読み飛ばす。固定上流のWAV読み込みも未知のチャンクを読み飛ばす。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_tsp_stressed_vowel_formants.py tsp-stressed-vowel-formants-held-out-new
```

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1、rustc 1.94.1で実行した。改訂後と `/private/tmp` からの再実行で各4判定と固定上流7試験を通過し、要約と固定Rustの全極のJSONがバイト一致した。TSP試験ログでは並列試験の1件の表示順が入れ替わった。初回を含む3実行の90入力・15出力をサイズとSHA-256で照合し、外部ディスクに175,908バイトの採取物を保存した。[改訂後](../runs/tsp-stressed-vowel-formants-held-out-20261122-final/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-stressed-vowel-formants-held-out-20261122-repeat/manifest.json)
