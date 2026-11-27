# FK61_01の全発話で丸め前後の差を照合する

先行計測で、上流に体積差の展開式を適用すると、PCMフレーム16682で隣接する値の境界を越えた。全発話PCMでは、両版の展開式の最大差は別のフレーム104883で1 ULPだった。今回は同じ4条件で発話全体の変換前の値を保存し、最大差に加えて、全区間と先行計測の後半にあたる区間の誤差を同じ方法で比較する。 [16682の読解と計測](tsp-fk61-pcm16682-rounding.md)・[104883を含む保存PCM](../runs/tsp-fk61-control4992-5120-expanded-volume-paired-20261123-repeat/manifest.json)

## 通常経路と観測点

上流の `render text` が `HumanVoice::render` を呼び、内部96 kHzの `AirwayNetwork::step` が壁・口・鼻の体積速度を合算する。現標本と前標本の和の差を時間刻みの逆数で換算すると cm³/s² になる。49タップの `Decimator::push` は最も古い標本から積を加算し、2内部標本で出力1フレームを作る。104883の最終入力は内部209767。研究版の `render-pcm` も同じ段として、放射の入力、FIR、ゲイン付きの値、前者を使うDC除去、包絡とPCMを観測する。 [上流CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L225)・[上流の放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1143)・[上流のFIR](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)

DC除去はゲイン付きの現在値、同じ値の前フレーム、前フレームのDC出力から `x − x_prev + c*y_prev` を計算して状態を更新する。包絡による抑制やソフトクリップが作動しない区間では、このDC出力がPCMへの変換直前の値になる。包絡の状態を含め、再計算は発話冒頭のゼロから始める。上流のエンジン試験は出力レートによる発声の安定性を、研究版の一様管試験は壁放射の重みと伝搬の状態を照合する。 [上流の出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L397)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L104)・[研究版の出力](../crates/vocal-core/src/output.rs#L103)・[研究版の試験](../crates/vocal-core/tests/uniform_tube.rs#L32)

## 事前に決めた条件

展開式どうしの104883では、変換直前の上流値が隣接PCM値の中点より上、研究版が下になると予測した。展開式どうしでPCMが異なるフレームの99%以上は1 ULPで、全発話の変換前RMS差は両版を通常式から展開式にしても0.8〜1.2倍に収まると予測した。符号付きゼロは別に数え、ULP距離では正負のゼロを同じ位置に置く。冒頭16,704フレームと残りの区間、16682のみを除いた比較も保存する。 [ケース定義](../cases/tsp-fk61-full-pcm-rounding.json)

## 実測

4条件で通常CLI、観測版、保存PCMが全116,132フレーム一致した。内部232,264標本で全口端流量を保存済みの値に照合し、前回の冒頭16,704フレームの全観測とも一致した。放射、FIR、DC除去、包絡とPCMは独立計算で全発話を再現できた。包絡の最大は約0.324で、全条件でリミッターは作動しなかった。 [全照合結果](../runs/tsp-fk61-full-pcm-rounding-20261123-registered/summary.json)

| 上流／研究版 | 変換前のRMS差 | PCMのRMS差 | 16682を除くPCMのRMS差 | PCMが1 ULP異なる数 | PCMが複数ULP異なる数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 通常／通常 | 8.807×10⁻¹⁵ | 5.469×10⁻¹² | 1.749×10⁻¹³ | 1,400 | 955 |
| 通常／展開 | 8.850×10⁻¹⁵ | 5.469×10⁻¹² | 1.738×10⁻¹³ | 1,401 | 954 |
| 展開／通常 | 8.781×10⁻¹⁵ | 3.430×10⁻¹³ | 3.430×10⁻¹³ | 1,395 | 956 |
| 展開／展開 | 8.837×10⁻¹⁵ | 3.424×10⁻¹³ | 3.424×10⁻¹³ | 1,395 | 956 |

両版を展開式にするとPCMのRMS差は約16分の1になり、変換前のRMS差は0.34%増えた。展開式どうしの変換前の最大差は77893の9.375×10⁻¹⁴で、このフレームのPCMは一致した。4通りの比較で変換前の初差は1984、PCMの初差は2937だった。

104883のPCMは通常式どうしで一致した。両版が展開式では、変換直前の上流値が中点より+4.788×10⁻¹⁵、研究版が−4.726×10⁻¹⁵にあり、PCMに1.164×10⁻¹⁰の差が生じた。この1フレームが、展開式どうしの全PCM差の二乗和の99.52%を占めた。変換前の版間差（研究版−上流）−9.514×10⁻¹⁵のうち、前フレームのDC状態項は−9.142×10⁻¹⁵だった。 [104883を含む観測値](../runs/tsp-fk61-full-pcm-rounding-20261123-registered/summary.json)

展開式どうしでPCMの差が1 ULPだったのは2,351フレーム中1,395（59.3%）で、99%以上という予測は棄却した。複数ULPの956フレームは68548以降にあり、両版のPCM振幅の大きい方でも最大2.303×10⁻⁷だった。最大34 ULPの106323では、PCMは約6.4×10⁻⁹、絶対差は約1.51×10⁻¹⁴。複数ULPのフレームが全PCM差の二乗和に占める割合は約0.00132%だった。振幅の小さい区間では隣接値の間隔も小さく、絶対差が小さくてもULP数は増えた。 [集計に用いた全発話データ](../runs/tsp-fk61-full-pcm-rounding-20261123-registered/manifest.json)

次は同じ評価方法を、既存の確認用セットの別発話FK61_02の通常レンダーに適用する。保存済みの144,727フレームに照合し、最大PCM差の129260を含めて丸めの影響と変換前誤差を集計する。 [確認用セットの記録](../runs/tsp-held-out-matched-speech-20261123-repeat/summary.json)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各上流ビルドのエンジン試験6件、各研究ビルドの一様管試験3件と計測の5判定に通過した。集計器は符号付きゼロとその隣接値、および前回の16682の中点に照合した。採取と一時ビルドにはRTL9210B-CGを使用した。 [初回マニフェスト](../runs/tsp-fk61-full-pcm-rounding-20261123-registered/manifest.json)

作業ディレクトリを `/tmp` に変え、Pythonと計測スクリプトを絶対パスで指定して再実行した。全発話の観測系列とPCM、PCMのハッシュ記録、要約の3出力が初回とバイト一致した。 [再実行のマニフェスト](../runs/tsp-fk61-full-pcm-rounding-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_full_pcm_rounding.py tsp-fk61-full-pcm-rounding-new
```
