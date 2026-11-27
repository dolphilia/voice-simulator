# 固定発声の放射流量微分を壁と開口の流量に分ける

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は、内部サンプルごとの `AirwayNetwork::step` の戻り値を間引き器に渡す。上流の [壁と放射負荷の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053) は、更新前の節点圧 `p` と壁の速度 `v`・変位 `y` から新しい速度を求める。式は `v_new = ((m×Fs − r/2)×v + p − k×y)/(m×Fs + r/2)`。`m` は面密度（g/cm²）、`r` は抵抗、`k` は剛性、`v` は cm/s、`y` は cm。変位を `dt×v_new` だけ進め、壁面積（cm²）を速度に掛けて流量（cm³/s）を得る。咽頭と口腔の壁は、この流量の0.25を放射に加える。各放射端の更新後流量を口端、鼻端の順に足し、前回の全放射流量との差を `Fs` 倍して出力する。得られる単位は cm³/s²。[上流の放射率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L119)・[出力の時間換算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)

研究版も [`WallMotion::step`](../crates/vocal-core/src/airway.rs#L286) の後に口端と鼻端の放射負荷を更新する。[`AirwayNetwork::step_with_prescribed_flow`](../crates/vocal-core/src/airway/network.rs#L745) は、壁の質量の時間換算と全流量差の時間換算で `dt` を除数に使う。上流の [`fdtd_impulse_response_agrees_with_frequency_domain_model`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68) は、壁あり・なしの一様管で放射を含む時間応答と周波数領域計算を比較する。今回は既存の固定 `/i/` で、壁、各開口、合計、微分を連続した内部番号で対応させる。

先行実験の出力フレーム末尾では、内部8,207点目で研究版の正の微分が上流より小さかった。96 kHzでは二進64ビットの `dt×96,000 − 1 = −77/2⁶¹` なので、両版の入力差分が同じ正数なら、丸めた `dt` で割った結果が `96,000` 倍より小さくなることはない。現在または前回の流量和に差があると予測し、時間換算と個々の流量を置き換えて確かめる。観測窓にはフレーム末尾で記録されていなかった偶数の内部番号も含める。[先行の初差](fixed-voice-glottal-slit-48000.md#最初のpcm差まで観測を延ばす)・[事前登録](../cases/fixed-voice-radiation-balance-48000.json)

## 初差は咽頭入口の壁面積から放射へ伝わる

声門抵抗まで揃えた先行の固定 `/i/` を、出力48 kHz・内部96 kHzの同じ条件で延長描画した。内部8,188〜8,239点目と、PCMが初めて分かれたフレームを含む9,598〜9,609点目で放射を採取した。観測を追加した隔離ビルドの音声と内部系列は、両版とも保存出力を再現した。

| 観測点 | 流量収支と置換結果 |
| --- | --- |
| 内部8,206点目 | 今回初めて観測した最初の微分差。前回の合計流量と口・鼻流量はすべてゼロ。壁流量の合計と時間換算の両方を上流順にすると、上流の `1.8026365693127845×10⁻¹³` cm³/s² に一致した |
| 内部8,207点目 | フレーム末尾で最初に観測した差。口・鼻流量はゼロ。今回の壁流量の合計だけを上流値にすると、上流の `4.6714487007811036×10⁻¹²` cm³/s² に一致した |
| 内部9,605点目 | 出力4,802フレーム目に対応。口端流量と前回の合計流量を同時に置き換えると、上流の `345.67394921620576` cm³/s² に一致した |

8,206・8,207点目で両版の放射寄与が異なる壁は、咽頭入口の節点13だけだった。この壁の断面積 `1.3 cm²`、セル長 `0.44960551235123475 cm`、圧力と速度は両版で一致した。上流の [`AirwayNetwork::finalize`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L560) は周長係数 `q×2×√π` を先に求め、更新中に `√A×dx` を順に掛ける。研究版の [`Section::wall_surface`](../crates/vocal-core/src/airway/network.rs#L34) は `2×√(π×A)×dx×q` としている。ここで `A` は断面積、`dx` はセル長、`q=1.25` は咽頭の周長補正係数。十進計算で各演算を二進64ビットに丸めると、研究版 `2.271528804858699 cm²` と上流 `2.2715288048586992 cm²` の壁面積を再現できた。節点13の面積だけを上流値にした計算で、両点の壁流量和が上流値に一致した。[流量と微分の置換](../runs/fixed-voice-radiation-balance-48000-repeat/summary.json)・[壁面積の検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-radiation-surface-48000.json)

次は咽頭入口の壁面積の計算順を変えた隔離描画で、後続の壁流量・口端放射・PCMを見る。微分の時間換算は独立の対照にし、8,206点目の局所置換の組合せと照合する。

## 実行と検証

初回 `-a` は保存差分を読み込む箇所で、差分の作成用関数に保存パスを誤って渡し、`AttributeError: 'PosixPath' object has no attribute 'items'` でビルド前に停止した。保存差分を適用する関数に差し替えて `-b` を実行した。事前登録の条件はそのまま使用した。

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_radiation_balance.py fixed-voice-radiation-balance-48000-b

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_radiation_balance.py" \
  fixed-voice-radiation-balance-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、各6判定と固定上流の各9試験に合格した。各実行で両版の壁4,608点と放射流量の微分128点を有理数と十進数で再計算した。PCM、計測CSV、観測差分を含む10出力が再実行間でバイト一致した。上流プローブの実行ファイルのハッシュは再ビルド間で異なり、計測値と判定は一致した。成功した2実行の386入力と36出力をハッシュ照合し、採取物10,963,041バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-radiation-balance-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-radiation-balance-48000.json)
