# TSPのF2選択と同じ窓のスペクトル包絡

[前回の照合](tsp-stressed-vowel-formants-held-out.md)で録音 `MK61_01` の `seems` は、発話の50%窓と10%窓でF2が1324.89 Hz動いた。今回はこの録音の `seems`（音素番号13）と、同じ話者が同じ文で発音した `plea`（音素番号3）の主強勢 /i/ を使う。35・50・65%の25 ms窓だけを取り、前回のWAV、MFA区間、12 kHzの開始標本を照合する。[事前登録](../cases/tsp-f2-bandwidth-envelope.json)

## 固定上流の読解

- CLIの `compare tsp` から `tsp::run`、`measure_pair`、`measure`、`Sig::formants` の順に進む。固定上流は録音と合成の対応音素をIPAの編集距離で選び、合成側の主強勢判定をスコアで両方に用いる。今回の入力は前回検証した録音側の時刻と原音。発話全体を前処理して48 kHzから12 kHzへ落とした後、母音内の3中心から各300標本を切り出す。[固定上流のCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[音素対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[F1・F2の窓](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L528)
- `estimate_formants` は前標本を0で初期化し、係数0.97のプリエンファシス、Hamming窓、自己相関、40 Hzのラグ窓の順で計算する。`levinson` は次数ごとに反射係数、予測係数列、残差エネルギーを更新する。今回は男性録音なので14次。根を周波数・帯域幅（Hz）へ変換し、150 Hz以上かつ帯域幅600 Hz以下の極を周波数順に並べる。[LPC係数と残差](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L28)・[極の推定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)
- `Sig::formants` は1300 Hz未満かつ帯域幅500 Hz未満の最初の極をF1とする。F2はF1＋200 Hzより上かつ3500 Hz未満の最初の極で、周波数順の探索に独自の帯域幅条件はない。両方が採れた窓だけで周波数の中央値を出す。既存試験では音素対応と欠測を確認し、Rustの自己相関・係数・予測残差・極・包絡をTypeScriptの基準データと照合する。[F2の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L541)・[欠測と対応の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)・[包絡の基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)

## 比較条件

F2の条件に帯域幅300 Hz未満を一つ加えた。LPCの係数も極も両方の選択で共通。固定上流の `estimate_formants` を新しい[観測用Rustプログラム](../tools/upstream_tsp_f2_envelope_probe.rs)から実行し、前回の固定Rust出力と、独立の直接解法で得たLPC極の両方に照合した。低い極の帯域幅がちょうど300 Hzの例、次の極へ進む例、F1が無い例、周波数上限上のF2候補も別に検査する。

包絡は0–6000 Hzを5 Hz刻みで測る。固定Rustの `lpc_envelope_db` は、同じ処理で得た係数と予測残差から周波数ごとに `10 log10(残差 / |A(exp(−j·2πf/fs))|²)` を評価する。符号は複素指数を展開した形で、Rustでは実部と虚部を個別に足す。NumPyの複素多項式評価で同じ計算と照合する。零除算を避ける微小項は固定上流と同じ `10⁻³⁰`。[固定上流の包絡計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L167)

もう一つの観測では同じプリエンファシス・Hamming窓を使い、FFTと直接DFTで窓の電力スペクトルを計算する。電力を周波数方向に標準偏差100 Hzのガウス核で平滑化してdBへ換算し、LPCの極を使わずに局所最大を探す。5 Hzは評価点の間隔。元の25 msの観測時間と平滑化の幅が、どの程度近いピークを区別できるかに関わる。包絡の強さは窓・発声源・プリエンファシスを含む観測量として扱う。[スペクトル包絡の推定方法](https://www.dsprelated.com/freebooks/sasp/spectral_envelope_extraction.html)

## 実測

`seems` の基準3窓で、固定のF2は986–993 Hz、帯域幅は471–509 Hzだった。LPCの包絡は650–1250 Hzに局所最大を持たなかった。平滑化ピリオドグラムには925–1030 Hzにも局所最大があったが、1900–2700 Hzの局所最大はそれより10.81–13.68 dB高かった。幅の条件を加えた後は、3窓すべてでその高域の山に近い極が採られた。F1は全窓で同一で、F2の欠測は両規則とも0件だった。

| `seems` の窓中心 | 固定F2・帯域幅 | 帯域幅条件付きF2・帯域幅 | LPC包絡の高域ピーク | ピリオドグラムの高域ピーク |
| ---: | ---: | ---: | ---: | ---: |
| 35% | 986.41・471.46 Hz | 2284.01・65.80 Hz | 2285 Hz | 2275 Hz |
| 50% | 993.37・508.89 Hz | 2323.81・59.45 Hz | 2325 Hz | 2330 Hz |
| 65% | 993.17・486.83 Hz | 2309.23・49.05 Hz | 2310 Hz | 2305 Hz |

対照の `plea` は、基準3窓で固定・帯域幅条件付きの両方が2341–2353 Hzの同じ極を選んだ。65%窓のピリオドグラムでは低域に局所最大が無かった。これはF2の欠測と区別して保存した。「高域」は事前に登録した1900–2700 Hzの範囲であり、全帯域の最大を指していない。[6窓の要約](../runs/tsp-f2-bandwidth-envelope-20261122-repeat/summary.json)・[50%窓の図](../runs/tsp-f2-bandwidth-envelope-20261122-repeat/artifacts/midpoint-envelopes.png)

窓、極、F1を固定したまま、差はF2の候補を周波数順に採る段で初めて生じた。波形に関する4項目の予測はこの2語で支持された。既知の極では周波数条件を満たす候補がすべて帯域幅上限に達すると欠測が増える。今回の2語は差を調べるために選んだ同一話者の /i/ であり、300 Hzを全母音に適用した場合の精度や、録音の真の共鳴周波数は未確定。

## 再現

研究ワークスペースで次のコマンドを実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_bandwidth_envelope.py tsp-f2-bandwidth-envelope-new
```

macOS 15.6.1 arm64、Python 3.14.4、rustc 1.94.1、NumPy 2.4.4、SciPy 1.17.1、Matplotlib 3.10.8を使用した。固定上流の極と前回の極の最大差は `8.78×10⁻¹¹ Hz` 未満。LPC包絡の計算差は `2.68×10⁻¹³ dB`、平滑FFTと直接DFTの差は `1.16×10⁻¹² dB` 以下だった。先行実行と同じ録音を使い、WAVの補助チャンクをSciPyが読み飛ばす警告が出た。

初回と `/private/tmp` からの再実行で各7判定と固定上流の基準試験1件が通過した。要約、固定RustのJSON、圧縮CSV、図がバイト一致し、保存した6窓・7206点から両包絡の候補帯域の局所最大を別に再集計した。2実行の38入力・12出力をサイズとSHA-256で照合した。採取物802,610バイトはRTL9210B-CGにあり、録音と合成の波形は先行実行から参照する。[初回マニフェスト](../runs/tsp-f2-bandwidth-envelope-20261122-a/manifest.json)・[再実行マニフェスト](../runs/tsp-f2-bandwidth-envelope-20261122-repeat/manifest.json)・[包絡データ](../runs/tsp-f2-bandwidth-envelope-20261122-repeat/artifacts/spectra.csv.gz)
