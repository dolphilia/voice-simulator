# CSD全4曲でのYIN閾値の比較

## 上流の経路と比較条件

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `compare_song()` は、録音・合成にそれぞれ `Analyzer` を作り、音符を `Analyzer::note()` で計測する。`note()` が作る5 ms格子の窓中心と譜面音高に対し、`Analyzer::pitch()` がPCM窓の平均二乗電力を求め、譜面の±7半音を `yin_pitch()` に渡す。`Analyzer::new()` に設定される閾値は0.2で、`yin_pitch()` 単体で設定を省略した場合は0.15。録音は44.1 kHz、両合成は48 kHzで、時刻は秒、F0はHz、ラグは整数サンプルを基準とする。[曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[初期化と窓の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L476)・[YIN](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/pitch.rs#L24)

`yin_pitch()` は各ラグ `τ` で固定個数のPCM対の二乗差 `D(τ)` を足す。累積和を更新し、無次元のCMNDを `τD(τ) ÷ ΣD(1..τ)` とする。探索の短い側からCMNDが閾値を厳密に下回る最初の点を探し、隣のラグでCMNDが下がり続ける間だけ進む。停止点を両隣から放物線補間し、標本化周波数を補間後のラグで割る。閾値を通る点がなければ、上流のF0は0で、非周期性として探索範囲内の最小CMNDを返す。原論文の第4段階では、この場合に大域最小から周期を返す。今回の計測は固定上流の挙動を使う。電力ゲートはその後のF0を遮り、`note()` は残った有声窓を連続区間のビブラートと2窓おきのH1−H2に渡す。[YINの原論文](https://www.ee.columbia.edu/~dpwe/papers/deChevK02-yin.pdf)・[音符の集計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L552)・[YINの参照値試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L229)・[ビブラート試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)

事前登録で、同一PCM、探索範囲、電力ゲートのままCMNDの閾値だけを0.2から0.15に下げた。4曲486音符と前回の焦点2窓・補助1窓を対象にした。窓別のF0欠測は探索内に閾値を通る候補がない場合と電力ゲート以下で分け、双方で有声の窓はラグとHzを比較する。各曲で変化した全窓と一定間隔の窓を、PCMからラグごとの内積でCMNDを計算する別実装に照合する。同じFFTからH1−H2を取り、ビブラートの定義と無声で区間を分割する規則を保持した。基準の0.2は既存の全曲CSV、固定上流の比較報告、丸め前の音符別スコアに照合した。[事前登録](../cases/csd-f0-yin-threshold.json)・[計測CLI](../tools/measure_csd_f0_yin_threshold.py)・[全曲の基準](csd-f0-continuity-songs.md#実測)

## 実測

4曲の録音・固定上流・再実装を合わせた88,344窓を照合した。電力ゲート以下の549窓は同じ位置だった。CMND閾値の変更で有声85,940窓のうち109窓が欠測に移り、録音37、固定上流40、再実装32だった。両条件で有声の632窓が長いラグへ移り、録音220、固定上流207、再実装205だった。電力ゲート以下でF0に現れずラグまたはCMNDだけが変わった窓が2つあった。[4曲の測定値と最初の差](../runs/csd-f0-yin-threshold-20261122-repeat/summary.json)

| 曲の分割 | 全窓 | 長いラグへ移動 | 有声から欠測 | 譜面より600セント以上高い窓 0.2 → 0.15 |
| --- | ---: | ---: | ---: | ---: |
| 調整曲 `en001a`・`en012a` | 48,357 | 256 | 61 | 431 → 269 |
| 確認曲 `en005a`・`en035a` | 39,987 | 376 | 48 | 246 → 0 |
| 合計 | 88,344 | 632 | 109 | 677 → 269 |

減った408窓はいずれもF0が得られたまま長いラグに移った。残った269窓はすべて調整曲 `en001a` の両合成で、固定上流129窓、再実装140窓だった。H1−H2は263窓、延べ75音符の中央値で変わった。整列が確認された `en035a` の長音では、ビブラートを検出した音符が固定上流で37→39、再実装で38→39、録音で17→17だった。検出数は計測器の出力で、音源の違いを聴いた結果は未取得である。[調整曲の窓別CSV](../runs/csd-f0-yin-threshold-20261122-repeat/artifacts/en001a-yin-threshold.csv.gz)・[確認曲の窓別CSV](../runs/csd-f0-yin-threshold-20261122-repeat/artifacts/en035a-yin-threshold.csv.gz)

`en001a` の録音で最初に欠測したのは第2音 `/bi/` の3.33130秒。電力はゲートの約48倍で、閾値0.2は157ラグで通過し、159ラグの277.95 Hzを返した。この窓の最小CMNDは0.170544で、0.15では範囲内の全ラグが閾値を通らない。電力、採択位置に対応するCMND、PCMを保ったまま、報告上のF0が欠測になる例を確認した。全109窓の最小CMNDは0.150121〜0.199825だった。[欠測の最初の例と窓別測定](../runs/csd-f0-yin-threshold-20261122-repeat/summary.json)

独立照合した焦点では `en001a` が348.39→316.83 Hz、`en035a` が301.06→276.30 Hzと前回を再現した。`en035a` の49.69506秒では最初の閾値通過が150→153ラグへ動いても、どちらも154で止まり287.01 Hzだった。既知409.35 Hzの倍音付き波形は両条件とも最大誤差0.0231 Hz。基本波が弱くなる200 Hz波形では、400 Hz付近が両条件で12窓残った。評価した固定閾値には、録音で支持された長い周期への移行、既知の短い周期の残留、F0欠測という複数の作用がある。[既知波形のCSV](../runs/csd-f0-yin-threshold-20261122-repeat/artifacts/known-tone-threshold.csv)・[前回の独立周期観測](csd-f0-recording-period-evidence-held-out.md#実測)

## 再現

初回の `csd-f0-yin-threshold-20261122-a` はユーティリティのインポート元を誤り、計測開始前に `ImportError: cannot import name 'error' from 'measure_speech_timing'` で停止した。インポート先を既存の `measure_csd_envelope_timing` に修正して `-b` で実行した。閾値・判定・事前登録は同じ版を使った。

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1、Rust 1.94.1で実行した。作業用ディスクの空き382 GiBと既存成果のサイズを照合し、20,000,000バイトを見積もった。研究ワークスペースでは次のコマンドを使う。`/private/tmp` ではPythonとスクリプトを絶対パスで指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python \
  tools/measure_csd_f0_yin_threshold.py csd-f0-yin-threshold-local
```

両実行で各51判定・5予測と固定上流20試験が通過した。変化した全窓を含む1,101窓と既知波形202窓を独立計算で照合した。全曲の圧縮CSV4本・既知波形CSV・要約はバイト一致し、別集計でも窓数、ラグの変化、有声欠測を再現した。2実行の140入力・18出力をサイズとSHA-256で確認し、採取物8,875,888バイトをRTL9210B-CGに保存した。曲のWAVは保存済みファイルを参照した。[修正後の初回](../runs/csd-f0-yin-threshold-20261122-b/manifest.json)・[別ディレクトリからの再実行](../runs/csd-f0-yin-threshold-20261122-repeat/manifest.json)
