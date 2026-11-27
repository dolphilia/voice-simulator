# TSP録音の第2フォルマントに人が注釈を付ける

`MK61_01` の `seems` と `FK61_01` の `again` では、プリエンファシスだけでLPCが別のF2候補を採る窓があった。同じ6窓について録音を試聴し、上流の採択値を伏せた図から、帯の位置と判断の根拠を記録できるようにする。既知の極を持つ合成対照を1窓混ぜる。[事前登録](../cases/tsp-f2-annotation.json)・[録音の感度比較](tsp-lpc-pre-emphasis-recordings.md#実測)

## 固定上流の読解と観測条件

`compare::tsp::measure_pair` は録音と合成の波形を読み、`match_phones` で対応した音素を `Sig` に渡す。`Sig::new` は48 kHzのPCMを低域通過後に4分の1へ間引く。`Sig::formants` は母音区間の35・50・65%の時刻を12 kHzの標本に切り捨てて変換し、各中心の前後150標本を選ぶ。`estimate_formants` はプリエンファシス、Hamming窓、自己相関、ラグ窓、Levinson–Durbin法、多項式の根の順に進む。極の位相から周波数、半径から帯域幅を求め、両方をHzで保持する。上流は周波数の低い適格な極をF1、F1より200 Hz以上高い適格な極をF2として取り、得られた値の中央値を返す。録音別の次数は12または14。`golden_analysis` は固定信号の出力をTypeScript版と照合する。[上流の音素対応と音響比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓と採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[LPCの計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L94)

注釈用の表示は元のPCM16を使う。母音の手前と後ろを45 msずつ含めた切り出しを試聴し、破線で整列済みの母音区間、色付きの25 ms区間で採択対象を示す。表示時刻は各切り出しの先頭からのms。図は8 msのHann窓を2 ms間隔で進めたスペクトログラム、その窓と同じPCMを使う波形、および対象25 msのHann窓のスペクトルを表示する。周波数はHz、スペクトルは各図内のピークに対する電力比 `10 log10(P/Pmax)`。周波数軸を密に描くためゼロ詰めする。分解能は観測窓の長さで決まる。LPCの候補や帯域幅から色や印を付ける処理は入れない。[資料生成と集計](../tools/measure_tsp_f2_annotation.py)

## 使い方

判定者には同じ `review/` 内の `index.html`、音声、画像をそろえて渡す。ページで音声を聴き、対象区間のF2周波数と根拠を記入する。帯が競合して決められないときは「判断困難」、境界や音声の問題で評価できないときは「音声・区間が不適」を選び、理由を残す。回答せずに空欄のまま残した窓も区別する。回答はCSVで保存し、判定者ごとに別のファイルを用いる。集計担当は判定終了後に、資料IDに対応する `reference.json` で録音の時刻・上流の採択値・合成対照の既知F2へ対応付ける。

集計結果は窓ごとに回答数、状態別の件数、F2中央値、判定者の最大値と最小値の差を記録する。比較可能な測定値が2件以上の場合に限り、その差を事前登録した100 Hzに照合する。合意幅は判定者間の再現性であり、録音の真値は別途必要になる。人が出した回答は `--kind human`、動作確認で作った回答は `--kind synthetic` として記録する。

既存の資料を評価するときは、[判定者向けページ](../runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)を開き、下の `--packet` には `tsp-f2-annotation-20261122-repeat` を指定する。人手の入口では記入済みの判定があることと、資料に付随する既知の試験回答との一致を検査する。実録音の判定件数は合成対照と分けて記録する。[取込の検証](tsp-f2-human-intake.md)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_annotation.py prepare tsp-f2-annotation-new

CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_annotation.py collect tsp-f2-responses-new \
  --packet tsp-f2-annotation-new --kind human --response 'rater-a=/path/to/observations.csv'
```

## 実測と保存先

録音2語の6窓を固定上流の比較と同じMFA区間・12 kHz上の300標本へ対応付けた。各録音の試聴用PCMは元の48 kHz標本と一致した。FFT表示を同じ標本から直接計算したDFTと比較し、窓付き波形の絶対値和で割った複素振幅の最大誤差は `1.54×10⁻¹⁵`。既知のF2が2,075 Hzの合成対照では、母音区間内で25 ms窓の電力を平均し、登録帯域1,500〜2,500 Hzで2,126.95 Hzを得た。既知の極との差51.95 Hzは事前条件120 Hz以内だった。ここでの差には単一の極と有限長のスペクトルピークの違いが含まれる。[生成結果](../runs/tsp-f2-annotation-20261122-repeat/summary.json)

Chromeで7枚の画像と7音声の再生を確認し、390 px幅で横スクロールが無いこと、理由欄のカンマ・引用符・改行がCSV往復後も残ることを検証した。試験用の2人分の入力を通常の取込CLIにも通し、70 Hz差は一致、200 Hz差は不一致と判定した。判断困難、音声・区間が不適、無回答を別々に保存した。重複ID、別資料のID、非有限値は受け付けなかった。[判定者向けページ](../runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)・[試験回答の取込結果](../runs/tsp-f2-annotation-20261122-fixtures/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1、Matplotlib 3.10.8、Chrome 157.0.8103.79で実行した。研究ワークスペースと `/private/tmp` から各8判定、固定上流1試験が通過し、判定者向け資料を含む23出力がバイト一致した。録音WAVの補助チャンクをSciPyが読み飛ばす警告があったため、試聴用PCMの一致を再読込で確認した。監査した48入力・54出力の採取物3,134,838バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-f2-annotation-20261122-a/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-f2-annotation-20261122-repeat/manifest.json)・[試験回答](../runs/tsp-f2-annotation-20261122-fixtures/manifest.json)

人の回答は0件。2,075 Hzは合成対照だけの既知値で、実録音6窓のF2候補の正誤は未判定。判定が集まったら、同じ帯を見たかを理由とともに点検してから、上流の既定条件とプリエンファシス0条件に対応付ける。

合成対照の励振は125 Hzの周期インパルス列。2,126.95 Hzのピークは、この条件で最強となる倍音2,125 Hzの近くにあった。同じ共鳴でF0を変えると帯域ピークが164.06 Hz動いたため、図では単一の倍音ピークに加えて前後の帯も確認する。[F0だけを変更した対照](tsp-f2-harmonic-spacing.md#実測)
