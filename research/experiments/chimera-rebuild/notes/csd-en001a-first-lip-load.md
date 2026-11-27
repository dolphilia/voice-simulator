# CSDの最初の口端流量差を追う

`en001a` の先頭2句では出力フレーム0に対応する内部標本0の時点で口の放射体積速度が異なった。この時点で声門前後の差圧・声門流量、壁・鼻の放射は0だった。今回は最初の制御更新と2内部標本を取り出し、上流と研究版の口端流量が分かれた入力を追う。 [先行の全出力の測定](csd-en001a-two-phrase-pcm-rounding.md#実測)・[ケース定義](../cases/csd-en001a-first-lip-load.json)

## 呼び出しと更新順

上流は歌唱計画のジェスチャーを `HumanVoice` に予約する。同設定対照では `HumanAirway::apply` を初期姿勢に適用し、`snap_to_targets` がセル面積（cm²）、セル長（cm）、体積（cm³）を初期姿勢に揃える。研究版の通常CLIは `run_song` から `ArticulatedVoice::for_speech_with_body` を呼び、同じ姿勢から気道を組み、調音スコアを渡す。上流の `HumanVoice::control` と研究版の `step_with_glottal_pressure` はそれぞれ標本0で調音を進め、接触補正まで済ませて128内部標本の目標を登録する。 [同設定の上流入口](../tools/upstream_csd_continuous_probe.rs#L52)・[上流の声道目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[上流の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[研究版の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L270)・[研究版の調音更新](../crates/vocal-core/src/voice.rs#L589)

気道の計算では目標までの差の1/128を現在値に足し、体積を面積と長さから更新する。1標本で減少した体積を秒あたりに換算し、狭窄セルから近隣へ配る処理の後に60 Hzの一極平滑を二段通す。その流量と枝流量を足し、可動壁への流出を引いた値が口端負荷に入る（cm³/s）。口端セルのコンプライアンス（cm⁵/dyn）は体積に比例する。放射負荷の慣性（g/cm⁴）は開口面積の平方根に反比例し、抵抗（dyn·s/cm⁵）は面積に反比例する。両版は並列R–L負荷とセル圧力（dyn/cm²）を中点で解き、圧力、慣性流量、放射流量を更新する。慣性が増えた場合は先に慣性流量を補正する。 [上流の体積差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L831)・[上流の口端負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1118)・[研究版の移動体積](../crates/vocal-core/src/airway/network/geometry.rs#L84)・[研究版の中点式](../crates/vocal-core/src/airway.rs#L89)

上流の一様管試験は、放射負荷を含んだ共鳴ピークを解析式および周波数領域モデルに照合する。狭窄の試験は断面を変えたときの流量と安定性を検査する。今回の独立計算は歌唱冒頭の口端セルに絞り、R–L式は先行の停止後観測で使った、有理数で各演算の倍精度丸めを再現する計算を使う。 [上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[放射負荷の独立計算](../tools/measure_fixed_voice_release_lip_load.py#L100)

体積を `V`、内部標本の時間幅を `T` とすると、平滑前の口端の体積速度は `(V_old − V_new) / T`。分配後の値を入力 `x` とし、先に `s1 += α(x − s1)`、次に `s2 += α(s1 − s2)` を実行する。`α = 1 − exp(−2π·60·T)` で、更新後の `s2` を流量へ足す。

口端のコンプライアンスを `C`、並列負荷の慣性・抵抗を `L, R`、正味流入を `Q` とする。`h = T/(2L)`、`g = 1/(2R)` を使って `p_new = (p_old(C/T − h/2 − g) + Q − U_old)/(C/T + h/2 + g)`、`U_new = U_old + h(p_old + p_new)`、放射流量 `q_rad = (U_old + U_new)/2 + g(p_old + p_new)` の順に解く。上流は `C·fs` を使い、研究版は `C/T` を使う。上流は左右の係数へ `h/2` と `g` を順に作用させ、研究版は両者の和を先に作る。交換実験ではこの演算順も独立した条件にする。

## 事前に決めた条件

休止状態からの標本0では、圧力と慣性流量の履歴、枝と壁による口端への正味追加入力は0と予測した。初回の口端流量の差は体積差分から平滑段へ伝わり、負荷の入口流量だけを交換すると差の95%以上が消えると予測した。押さえる区間は内部標本0と1。PCMの比較は48 kHzの全201,600フレームで行う。 [予測と合否基準](../cases/csd-en001a-first-lip-load.json)

## 実測

両版で口端は節点43だった。最初の制御更新より前から、研究版の口端面積は上流より2.220×10⁻¹⁶ cm²（1 ULP）大きく、セル長は2.220×10⁻¹⁶ cm（4 ULP）短かった。面積目標の差は4.441×10⁻¹⁶ cm²で、長さ目標の差は−2.220×10⁻¹⁶ cm。標本0の長さの増分と最小断面は一致した。保存された姿勢から形状を作る過程のうち、どの演算で両版が分かれたかは今回の観測点より前にある。 [口端の前値、目標、更新値](../runs/csd-en001a-first-lip-load-20261124-registered/artifacts/lip-observations.json)

| 標本0の観測量 | 上流 | 研究版 |
| --- | ---: | ---: |
| 更新前の面積（cm²） | 1.3740223635728994 | 1.3740223635728996 |
| 更新前のセル長（cm） | 0.4648206150541990 | 0.4648206150541988 |
| 平滑前の体積速度（cm³/s） | −0.002721331576083230 | −0.002721331565425089 |
| 負荷へ入る流量（cm³/s） | −4.180192868111401×10⁻⁸ | −4.180192851739605×10⁻⁸ |
| 口の放射流量（cm³/s） | −1.193286531633145×10⁻⁸ | −1.193286526959618×10⁻⁸ |

観測した面積・長さから体積を有理数で計算し、積を丸めずに引いた場合の体積速度差は研究版から上流を引いて−1.996×10⁻¹⁹ cm³/sだった。保存された倍精度の体積を引くと、差は+1.066×10⁻¹¹ cm³/sになった。体積を丸めることで両版差の符号が反転し、絶対値は約5.34×10⁷倍になった。同一の丸め済み体積差を出発点に、内部サンプルレートを掛ける計算と標本幅で割る計算を試すと、両版それぞれで一致した。口端の配分後の体積速度は局所計算と一致し、平滑係数も両版で一致した。標本1では平滑前の局所体積速度が両版で一致し、標本0の履歴が二段平滑の流量に残った。 [体積の計算と二段平滑の照合](../runs/csd-en001a-first-lip-load-20261124-registered/summary.json)

標本0では圧力と慣性流量の前値がいずれも0で、枝と壁を処理した後の口端負荷への流量は二段平滑の出力と一致した。負荷に入る流量だけを相互に交換すると、両方向で口端流量差4.674×10⁻¹⁷ cm³/sの99.99999%が解消した。交換後の残差は両方向で絶対値3.309×10⁻²⁴ cm³/sだった。負荷の係数、履歴、演算順を含めた全交換では、相手の口端流量とビット一致した。 [入力の往復交換と判定](../runs/csd-en001a-first-lip-load-20261124-registered/summary.json)

## 再現と次の観測

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使った。上流の一様管と狭窄の9試験、研究版の幾何補間の1試験を通過した。同設定上流の試験入口と研究版の通常 `render-pcm` から描画し、計装あり・なしの全PCMと歌唱計画を先行実行と照合した。作業用のRTL9210B-CGでビルドし、全レンダーは一時領域で照合した。保持した主出力は最初の2標本の口端観測、PCMのハッシュと歌唱計画、観測パッチ。 [実行コマンドと保存先](../runs/csd-en001a-first-lip-load-20261124-registered/manifest.json)

研究ワークスペースと `/tmp` から別々にビルドし、各4判定と3つの事前予測を確認した。要約と上記4出力は2実行でバイト一致した。 [再実行のマニフェスト](../runs/csd-en001a-first-lip-load-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_csd_en001a_first_lip_load.py csd-en001a-first-lip-load-new
```

次は同じ姿勢を一度適用し、最後の口腔セルの面積とセル長に入力する断面標本と中心線弧長を初期化時に採取する。面積と長さを個別に交換し、最初の体積差分の符号と絶対差を再計算する。 [上流の声道形状から断面を作る処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[研究版の体型・姿勢からの初期化](../crates/vocal-core/src/voice.rs#L326)
