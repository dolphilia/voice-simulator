# 48 kHz固定発声の咽頭入口圧

## 読解と予測

固定上流の `HumanVoice::render` は48 kHzの出力1点に対して内部96 kHzで2回、肺の境界圧、声門、気道を順に更新する。声門面積は更新前の声門下圧と咽頭セル0の圧力差から求め、声門ポートに反映する。保存済みの `upstream_vowel_voice_probe.rs` は固定姿勢・固定音高で `set_gate` とこの描画入口を呼び、各出力フレームの最後の内部点を採っていた。研究版の通常CLIは `geometry_case::render_fixed_voice` で同条件を構築し、出力のゲート時刻を内部点に換算して `FixedVoice::step_source` に渡す。[上流の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[保存済み上流プローブ](../tools/upstream_vowel_voice_probe.rs#L163)・[通常CLI](../crates/vocal-cli/src/geometry_case.rs#L367)・[研究版の内部更新](../crates/vocal-core/src/voice.rs#L214)

咽頭のセル0には気管からの声門流入があり、咽頭セル1へ流出する。両実装は断面移動で生じた流量の初期値に、セル1への流出を引き、声門流入を加え、最後に壁流出を引く。枝流量と壁流量の単位はcm³/s。枝は前回の圧力と流量を持ち越し、壁はそのセルの前回圧力と壁変位・速度から半ステップの流量を得る。セル0の圧力更新は `p_next = p_prev + (dt / C) × ((U_volume − U_out) + U_glottis − U_wall)`。このセルの `C` は体積 `V = A × dx` を `ρc²` で割った値で、圧力はdyn/cm²。断面移動があれば `U_volume` は体積の時間差分を空間に配分して低域通過させた流れとなる。上流の密閉腔の試験はこの体積と圧力の関係を5%圧縮で検査し、別のホスト分割の試験は操作の適用時刻を揃えるとPCMが同じであることを検査する。[上流の枝・壁・節点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L924)・[研究版の節点](../crates/vocal-core/src/airway/network.rs#L717)・[密閉腔試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

先行実行では、出力4,102フレーム目に対応する内部8,205点目で声門上圧に初めて差が見えた。その直前の観測点は8,203点。内部8,204点または8,205点で最初の差が出ると予測し、研究版の収支に上流値を一項ずつ入れて、その時点の圧差を復元できるか調べる。トレースを付けた結果も元の出力点とPCMに戻して照合する。[事前登録](../cases/fixed-voice-pharynx-onset-48000.json)・[先行の採取](worklet-realtime-voice-48000-memory.md#再採取と差の起点)

## 最初の差はセル長から圧力へ伝わる

通常CLIの固定発声ケースに `fixed_voice_probe.internal_trace` と `fixed_voice_probe.pharynx_entry_balance` を指定して、出力4,120点分を内部8,240点のCSVとして採取した。上流には別の作業用ディレクトリで計測差分を適用し、`HumanVoice::render` の `net.step()` の直後で同じ量を読んだ。それぞれの出力フレーム末尾の既存列とPCMは保存済み実行の接頭部に一致し、CLIの128・77フレーム分割と上流の接頭PCMも4,120点すべてでビット一致した。計測指定を外した通常CSVも保存済みの4,120フレーム分とバイト一致した。[CLIの計測](../crates/vocal-cli/src/geometry_case/voice.rs#L198)・[上流に適用した差分](../runs/fixed-voice-pharynx-onset-48000-repeat/artifacts/upstream-pharynx-balance.patch)・[再実行の要約](../runs/fixed-voice-pharynx-onset-48000-repeat/summary.json)

声門上圧は発声から13内部サンプル後の8,205点目で初めて分かれた。声門流入は両版で約1.924×10⁻¹⁴ cm³/sで一致し、この点での前回圧・セル1への流出・壁流出・断面移動由来の流入はすべて0だった。研究版ではコンプライアンスが `4.1853717583716815e-7`、上流では `4.185371758371681e-7` で1 ULP異なる。独立した有理数計算で各演算をf64に丸めると、両版とも監視区間52点の圧力をビット一致で復元した。最初の差はコンプライアンスだけを置き換えて消えた。その時点の声門上圧の差は約1.010×10⁻²⁸ dyn/cm²。セル1圧・セル1への流出・壁流出の初差は1点後、声門流入の初差は5点後だった。[研究版の内部系列](../runs/fixed-voice-pharynx-onset-48000-repeat/artifacts/candidate-pharynx-balance.csv)・[上流の内部系列](../runs/fixed-voice-pharynx-onset-48000-repeat/artifacts/upstream-pharynx-balance.csv)

セル0の断面積は両方で1.3 cm²。先行の幾何記録では、咽頭の全長が研究版8.092899222322227 cm、上流8.092899222322226 cmだった。両方の全長を18で割ると今回のセル長に一致する。十進計算で研究版のセル長だけを上流の長さへ置き換え、体積・コンプライアンスから再計算した最初の圧力も上流とビット一致した。次の観測候補は咽頭と口腔の境界までの中心線距離で、境界付近の区間長と加算順でどこから全長の差が生じるかを切り分ける。[先行の上流幾何](../runs/worklet-rate-96000-20261120-native-repeat/artifacts/upstream-geometry.csv)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharynx-onset-48000.json)・[研究版の全長](../crates/vocal-core/src/anatomy/area.rs#L132)・[上流の全長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1235)

## 実行と回帰

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、研究ワークスペースと `/tmp` から実行した。各13判定に合格し、要約は一致した。固定上流の境界条件とエンジンの各6試験を実行した。最初の読み取り口の追加位置ではWASMの関数コードは一致したが、内部の行番号データと関数名の節が変化した。読み取り口を既存の描画処理の定義後に置き、通常ビルドのWASMが先行の `5f8685ad…` とバイト一致することを確認した。全体監査192判定、研究版Rust 52試験、全体監査の上流17試験も通過した。3実行の計726入力と38出力をハッシュ照合し、出力のうち6,199,861バイトをRTL9210B-CGへ保存した。[初回のマニフェスト](../runs/fixed-voice-pharynx-onset-48000-a/manifest.json)・[再実行のマニフェスト](../runs/fixed-voice-pharynx-onset-48000-repeat/manifest.json)・[全体監査の回帰](../runs/plan-completion-pharynx-onset-regression/summary.json)

```bash
CARGO_TARGET_DIR=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-pharynx-onset \
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_pharynx_onset.py fixed-voice-pharynx-onset-48000-new
```
