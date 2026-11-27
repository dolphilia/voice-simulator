# FK61_01のPCM2937に効く口端放射の時間範囲

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。固定上流と下唇内面の評価順を上流に揃えた試験版では、全発話の最初のPCM差が2937フレームにあった。先行計測で口端の放射流量をすべて上流へ交換すると、冒頭から2937までのPCMが一致した。今回は交換する時間範囲を限定する。 [先行実測](tsp-fk61-pcm2937-output.md)・[事前登録](../cases/tsp-fk61-pcm2937-lip-window.json)

## 出力段の読み方と比較条件

上流の `HumanVoice::render` は、96 kHzの気道計算から出る総放射流量の時間差分を `Decimator::push` へ入れる。気道の口端では、圧縮性と並列R–L放射負荷の中点更新で口端流量［cm³/s］を求める。放射3成分を加算したあと、内部標本間の差分を取るため、ある標本の口端流量の交換は、その標本と次の標本の放射差分［cm³/s²］を変更する。出力は49タップのFIRで間引き、ゲインを掛け、現在の値と前回の値の差に前回のDC出力×係数を足す。リミッターが作動しない観測範囲では、この値がfloat32へ変換される。 [上流の放射と終端負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1073)・[上流のFIR](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L41)・[上流の出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L396)・[研究版のR–L負荷](../crates/vocal-core/src/airway.rs#L89)・[上流のブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

通常CLIと観測器をビット照合した先行実行の系列を入力に使う。内部5800〜5875の全連続区間について、壁面と鼻端を試験版の系列に固定し、区間内の口端流量を上流へ交換する。出力2899のゲイン適用後の値とDC出力、直前のFIR入力で状態を初期化し、出力2900から2937まで既存の演算順で進める。2937のPCMの一致と先頭2938フレームすべての一致を区別する。代表区間は冒頭からの再計算にも通し、同じ結果になることを確認する。 [実装と検証](../tools/measure_tsp_fk61_pcm2937_lip_window.py)

別に、2937への線形な寄与を逆算する。過去のFIR出力に対する係数は、DC係数を `p`、ゲインを `g`、目標フレームを `f` とすると、現在フレームで `g`、過去フレーム `k` で `g × (p−1) × p^(f−k−1)`。そこからFIRの各タップをたどり、隣接内部標本に掛かる係数の差を内部レートで換算すると、口端流量を交換したときの寄与を標本ごとに見積もれる。倍精度で順に再計算した値との残差も測る。

## 実測

内部5800〜5875に収まる全2,926連続区間のうち、2937のPCMが上流と一致したのは1,044区間。冒頭から2937までがすべて一致したのは73区間だった。後者の最短は内部5863・5864の2標本で、この長さで一致した区間はこの1件だった。単一標本では2937で一致した条件が8件あり、すべてに2937より前のPCM差が残った。 [全区間の表](../runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/artifacts/window-scan.npz)・[区間別の要約](../runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/summary.json)

上流から試験版を引いた口端流量差は5863で−2.9431×10⁻¹¹ cm³/s、5864で−2.9061×10⁻¹¹ cm³/s。それぞれを上流に交換すると2937の変換直前値は+1.1841×10⁻¹⁴、+7.3637×10⁻¹⁵だけ動いた。どちらも単独では中点までの1.4099×10⁻¹⁴に届かず、2標本の同時交換では+1.9204×10⁻¹⁴動いて中点を越えた。口端流量の最初の版間差は先行計測で確認した3971にある。 [口端流量の元データ](../runs/tsp-fk61-pcm2937-output-20261123-verified-repeat/artifacts/upstream-prefix.npz)・[交換条件と変換直前値](../runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/summary.json)

前回の5851は放射差分とFIR係数の積の差が最大の標本だった。今回の口端流量の単一標本交換では、二つの時間差分とDC状態までを含めた線形寄与が最大なのは5849で、+4.3270×10⁻¹³だった。5851の口端流量だけを交換すると、PCMの最初の差は2934へ前進した。線形寄与を5800〜5875のすべてで合計すると+1.5480×10⁻¹⁴で、大きさと符号の異なる寄与が相殺された。線形近似と逐次再計算の最大残差は2.99×10⁻¹⁹だった。 [時間窓の交換と線形再計算](../runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/summary.json)

次は5863・5864、時間差分が変わる5865を含め、口端の終端流入、旧圧力、R–L負荷の状態を採って、口端流量の差の経路を調べる。

## 再実行

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/measure_tsp_fk61_pcm2937_lip_window.py tsp-fk61-pcm2937-lip-window-new
```

初回は区間の計算後、NumPyの真偽値を要約のJSONへ直接渡したため保存が止まった。比較値をPythonの数値型に揃えて再実行し、保存済み走査配列は失敗時の4実行から修正後の2実行までSHA-256が一致した。 [初回の失敗](../runs/tsp-fk61-pcm2937-lip-window-20261123-repeat/manifest.json)・[修正後の実行](../runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/tmp` から実行した。先行の通常CLIと観測器のPCMの照合記録を入力にし、区間計算と線形近似の4判定は両実行で通過した。走査配列と要約の2出力がバイト一致した。 [研究ワークスペースでの実行](../runs/tsp-fk61-pcm2937-lip-window-20261123-certified/manifest.json)・[別ディレクトリでの実行](../runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/manifest.json)
