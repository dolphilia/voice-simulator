# 確認用発話FK61_02の丸め前とPCMの誤差を照合する

FK61_01では変換前の最大差とPCMの最大差が別のフレームに現れ、複数ULP差は信号の小さい区間に集まった。別の確認用発話FK61_02について、同じ評価指標を固定上流と研究版の通常レンダーに適用する。参照するのは実録音から選んだ発話ケースと、それに対応する保存済みの合成PCM。 [FK61_01の全発話比較](tsp-fk61-full-pcm-rounding.md)・[FK61_02の入力](../runs/tsp-held-out-matched-speech-20261123-repeat/artifacts/FK61_02/matched-case.json)

## 通常経路と独立計算

上流の `render text` は `say` で英語の発話計画を作り、`HumanVoice::render` を通じて内部96 kHzで気道を進める。気道の `step` は壁と口・鼻の放射体積速度を cm³/s で合計し、前標本からの変化を cm³/s² に換算する。49タップのFIRを最古の入力から加算し、2内部標本ごとに出力を作る。研究版の `render-pcm` では `OutputStage::push` が同じ順に出力を作る。 [上流の発話CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[上流の放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1143)・[FIR](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[研究版の出力](../crates/vocal-core/src/output.rs#L103)

ゲインを掛けた `x` と前の `x`、前のDC出力 `y_prev` から `x − x_prev + c*y_prev` を再計算し、包絡と保持時間も冒頭のゼロから復元する。抑制・クリップの非作動を検査し、DC除去後の値の `f32` 変換をPCMに照合する。上流のエンジン試験は出力レートを変えた発声のRMSと有限性を、研究版の一様管試験は壁放射と管内の状態を検査する。 [上流の出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L397)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L104)・[研究版の試験](../crates/vocal-core/tests/uniform_tube.rs#L32)

## 事前に決めた条件

48 kHzの全144,727フレームで、PCMの初差31350、最大絶対差129260、差のある1,992フレームを保存済みの照合結果から登録した。変換前とPCMの最大差が別の位置に現れ、129260では隣接値の中点をまたぐと予測した。複数ULP差の95%以上はPCM振幅が10⁻⁶以下で、放射と変換前にはPCMの初差より早く差が出ると予測した。 [ケース定義](../cases/tsp-fk61-02-full-pcm-rounding.json)

## 実測

両版とも通常CLI・観測版・保存済みPCMが全144,727フレームでビット一致した。全289,454内部標本から、放射の和・差分、FIR、ゲイン、DC除去、包絡、PCMを再計算できた。包絡の最大は約0.404で、リミッターは作動しなかった。上流と研究版の声門流量の初差は内部標本4879、壁の放射流量と放射の初差は4880だった。口と鼻の放射流量の初差は後続の4907と40733。FIRと変換前の初差はフレーム2440で、最初のPCM差31350より約0.602秒早かった。 [全発話の再計算と初差](../runs/tsp-fk61-02-full-pcm-rounding-20261124-registered/summary.json)

| 指標 | FK61_01（両版で面積を直接補間） | FK61_02（両版の通常レンダー） |
| --- | ---: | ---: |
| 変換前のRMS差 | 8.807×10⁻¹⁵ | 8.156×10⁻¹⁵ |
| 変換前の最大差 | 8.312×10⁻¹⁴（26939） | 9.021×10⁻¹⁴（31148） |
| PCMのRMS差 | 5.469×10⁻¹² | 4.896×10⁻¹² |
| PCMの最大差 | 1.863×10⁻⁹（16682） | 1.863×10⁻⁹（129260） |
| PCM差が1 ULPのフレーム | 1,400 | 1,311 |
| PCM差が複数ULPのフレーム | 955 | 681 |

FK61_02の変換前の最大差31148は母音 /ɪ/ の区間にあり、PCMは一致した。最大PCM差129260は母音 /ɝ/ の区間にあり、変換前の差は4.056×10⁻¹⁵だった。両版の変換前の値が隣接するPCM値の中点から−9.923×10⁻¹⁶と+3.064×10⁻¹⁵にあり、PCMで1 ULPの差になった。この1フレームはPCM差の二乗和の99.999%を占め、除いたときのRMS差は1.541×10⁻¹⁴だった。 [フレーム別の比較](../runs/tsp-fk61-02-full-pcm-rounding-20261124-registered/summary.json)・[保存済みの音素時刻](../runs/tsp-held-out-matched-speech-20261123-repeat/summary.json)

複数ULP差の681フレームはすべて両版のPCM振幅が10⁻⁶以下で、振幅の最大も4.818×10⁻⁸だった。最大159 ULPの141907はPCM振幅が約2.62×10⁻¹⁰で、絶対差は4.413×10⁻¹⁵だった。複数ULPフレームの最大絶対差は2.132×10⁻¹⁴。四つの事前予測を確認した。次は同文の男性体型MK61_02に同じ指標を適用し、体型と発声設定が異なる条件で最大差の位置と低振幅区間の傾向を照合する。 [全発話の観測データ](../runs/tsp-fk61-02-full-pcm-rounding-20261124-registered/manifest.json)・[男性体型の入力](../runs/tsp-held-out-matched-speech-20261123-repeat/artifacts/MK61_02/matched-case.json)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。上流のエンジン試験6件と研究版の一様管試験3件、計測の4判定に通過した。集計器は既知の1 ULP、2 ULP、符号の異なるゼロも分類できることを確かめた。採取と一時ビルドにはRTL9210B-CGを使用した。 [初回マニフェスト](../runs/tsp-fk61-02-full-pcm-rounding-20261124-registered/manifest.json)

作業ディレクトリを `/tmp` に変え、Pythonと計測スクリプトを絶対パスで指定して再実行した。全発話の観測系列、PCMのハッシュ記録、要約の3出力が初回とバイト一致した。 [再実行のマニフェスト](../runs/tsp-fk61-02-full-pcm-rounding-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_02_full_pcm_rounding.py tsp-fk61-02-full-pcm-rounding-new
```
