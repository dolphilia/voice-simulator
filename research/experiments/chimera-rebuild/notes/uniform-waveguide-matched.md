# 並列R–L終端をそろえた一様管の比較

## 固定上流の経路と数値更新

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `tests/airway.rs` は、`uniform_tube` から `AirwayNetwork::new`、`add_tube`、`add_radiation`、`finalize` を呼ぶ。 `fdtd_peaks` では入口セルの `ext_flow` に1サンプルだけ `fs` を加え、`step` の放射差分をFFTに掛け、角周波数で割って放射流量のピークを求める。 `uniform_tube_resonances_match_quarter_wave_theory` は端補正付き四分の一波長、`fdtd_impulse_response_agrees_with_frequency_domain_model` は連続時間の回路モデルに照合する。今回は `radiated_flow` から時間差分の前の体積流量も直接取り出す。[上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)・[既存の一様管読解](uniform-tube.md)

均一断面では枝の非線形損失が消える。圧力 `pₙ` と前の枝流量 `Uₙ₋₁` から、`(L/Δt + R)Uₙ = pₙ,left − pₙ,right + (L/Δt)Uₙ₋₁` を解く。節点は正味流入を `Δt/C` 倍して圧力を更新する。放射端では終端セルの圧力と並列R–Lの慣性枝流量を中点で連立し、放射流量 `Uᵣ` と前ステップとの差分を出す。単位は圧力が dyn/cm²、流量が cm³/s、流量差分が cm³/s²。上流の `TubeSpec::viscous(0)` は枝の粘性抵抗 `R` を0にする。候補の `vocal-cli` でも `tube.viscous_scale=0` を指定でき、`inspect` が適用後の枝抵抗を返す。放射端の抵抗は有効なまま使う。[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L924)・[上流の放射端と出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1121)・[一様管のCLI](../crates/vocal-cli/src/main.rs)・[再実装の管係数と更新](../crates/vocal-core/src/airway.rs)

## 双方向遅延と共通の終端

既存の `tube_render` は断面積から反射係数 `k` と透過係数 `√(1−k²)` を決め、両方向の波を一区間ずつ進める。同じ断面積が続く場合は `k=0` で、各方向の区間列は固定長の遅延にまとめられる。既存の入口反射0.75・口端反射−0.85は元のC実装との照合に使用した。物理量で比較する場合は圧力波 `a,b` と特性インピーダンス `Z₀=ρc/A` から `p=a+b` と `U=(a−b)/Z₀` を求める。入口では体積流量 `U_in` を与えるので、遅延から戻った波に `Z₀U_in` を足して送り出す。駆動終了後の入口は流量0、圧力反射+1となる。[既存のC実装](../../autonomous-research-cycle/campaigns/nas-waveguide-tract-mechanism-20261008-v1/waveguide_tract.c)・[Smithの平面波の境界式](https://www.dsprelated.com/freebooks/pasp/Plane_Wave_Scattering.html)・[正規化散乱](https://www.dsprelated.com/freebooks/pasp/Normalized_Scattering_Junctions.html)

口端で慣性枝の旧流量を `w`、入射圧力波を `a` とする。中点の負荷流量は `U=w+(Δt/(2Lᵣ)+1/Rᵣ)p`。口端の結合式 `p=2a−Z₀U` と連立して圧力を決める。続いて `w←w+Δt·p/Lᵣ` と更新し、反射波 `b=p−a` を入口向きの遅延に戻す。上流と同じ面積から求めた `Lᵣ,Rᵣ` を使う。FDTDの口端圧力は時刻更新後のセル中心、波動管の口端圧力は負荷との接点で定義される。方式間の複素応答を比べる観測量は、入口の指定流量に対する並列R–Lへ流れる全流量の比とした。[実行するRustの比較器](../tools/upstream_uniform_waveguide_probe.rs)

## 事前登録と独立計算

一様管は17.5 cm・3 cm²、音速35,000 cm/s、密度0.00114 g/cm³。96 kHzの40セルと192 kHzの80セルを比較した。波動管の片道はそれぞれ48・96サンプルで、実時間は両方0.5 ms。体積0.001 cm³を初回の1サンプルで注入し、各条件を0.5秒測る。最初の非ゼロと主波束の到達は別々に記録する。主波束は対称ガウス包絡で平滑化し、包絡の中央時刻を差し引いた。最初の4共鳴、250〜3,750 Hzの指定8周波数の複素応答、末尾0.1秒を比較する。96 kHzでは既定の粘性抵抗を戻した対照も採った。[事前登録](../cases/uniform-waveguide-matched.json)

独立計算は `z=exp(jωΔt)` とおく。FDTDでは枝のアドミタンスを `1/(R+(L/Δt)(1−1/z))`、節点を `C(z−1)/Δt` として、三重対角の節点圧力方程式を解く。中点の放射アドミタンスは `Yᵣ=1/Rᵣ + 1/(j·2fs·tan(ωΔt/2)·Lᵣ)` で、FDTDの節点方程式に入る放射項は `Yᵣ(z+1)/2`。波動管の反射係数は `Γ=(1−Z₀Yᵣ)/(1+Z₀Yᵣ)`。片道を `D` 点とすると、流量の伝達は `(1−Γ)z⁻ᴰ/(1−Γz⁻²ᴰ)`。流量差分はそれぞれの複素応答に `(1−1/z)/Δt` を掛けて照合する。[独立計算と判定](../tools/measure_uniform_waveguide.py)

## 打ち切り漏れを追った対照

0.5秒では、波動管と粘性を切ったFDTDで末尾に減衰が残り、FFTに生じた細かな山を共鳴として数えた。96 kHzの末尾0.1秒の最大流量は全区間の最大値に対して波動管0.289%、FDTD 0.572%。波動管の分母の極から最低モード約477.45 Hzの振幅時定数0.1503秒を求め、同じ閾値で3秒まで測り直した。波動管は4共鳴に収まり、末尾比は1.74×10⁻¹⁰以下になった。[0.5秒の全結果](../runs/uniform-waveguide-matched-20261121-b/summary.json)・[3秒の事前登録](../cases/uniform-waveguide-matched-long.json)・[3秒の全結果](../runs/uniform-waveguide-matched-20261121-long/summary.json)

192 kHzの粘性なしFDTDでは、3秒に延ばしても小さな山が混入した。末尾0.1秒の口端流量の最大周波数成分は、96 kHzで30,070 Hz、192 kHzで60,190 Hz。粘性なしの内部の枝式と節点式を空間正弦波に代入すると `sin(ωΔt/2)=(cΔt/Δx)sin(kΔx/2)`。この分散式から伝搬帯域上限は30,102.77 Hzと60,205.54 Hzになる。格子の上限付近では群速度が0へ近づく。放射が弱く高周波が記録の末尾に残ったという解釈は、末尾スペクトルと上限の差が33 Hz未満であることに基づく。[元波形での末尾診断とフィルタ係数](../runs/uniform-waveguide-matched-20261121-bandlimited-b/summary.json)

比較対象の上限4 kHzより高い6 kHzに遮断周波数を固定した因果FIRを全方式へ適用した。各レートでFIRの片側を0.5 msにそろえ、総注入体積0.001 cm³を保持した。線形条件なので、同じフィルタを保存済みの入力と応答に畳み込めば、その入力を最初から与えた場合の応答になる。時間比較では共通の遅延を引き、周波数比較では実際の入力の複素成分で割る。処理前の判定は上記の実行IDに保持した。[帯域制限の事前登録](../cases/uniform-waveguide-matched-bandlimited.json)

## 照合結果と残る差

| 管内粘性なし | 96 kHz・40セル | 192 kHz・80セル |
| --- | ---: | ---: |
| 生の口端流量の初回非ゼロ点 FDTD / 波動管 | 39 / 48 | 79 / 96 |
| 帯域制限後の主波束の到達差 FDTD − 波動管 | −4.21 µs | −2.25 µs |
| 共鳴1〜4の最大相対周波数差 | 1.201% | 0.597% |
| 指定8周波数の最大振幅差 | 1.487 dB | 0.823 dB |
| 指定8周波数の最大位相差 | 2.06° | 1.26° |

帯域制限後は両レートとも4共鳴になり、時間波形から求めた複素応答と離散式の相対差は流量と流量差分を含めて4.0×10⁻⁹以内だった。192 kHzでは一致の条件をすべて満たした。96 kHzは3,250 Hzの振幅差が約1.49 dBあり、事前登録した0.9 dBを超えた。2,750〜3,750 Hzの3点で測った最大複素差は格子を細かくすると42.30%低下した。上流FDTDとの生の時系列の相対ピーク誤差は最大6.12×10⁻¹⁵、既存C実装との固定反射の誤差は1.98×10⁻¹⁸。96 kHzの粘性を戻すと、第1共鳴は483.19→483.12 Hz、ピークの伝達は48.92→37.92 dBとなった。下がった主な指標は共鳴の高さで、周波数の差は約0.07 Hzだった。[帯域制限後の34判定と複素応答](../runs/uniform-waveguide-matched-20261121-bandlimited-b/summary.json)

入口の指定流量は両方式で同じで、最初の波形差はサンプル0の入口圧に出た。96 kHzではFDTDの入口セルの圧縮が1,064 dyn/cm²、波動管の送り出した圧力波が1,276.8 dyn/cm²。FDTDは局所のコンプライアンス、波動管は特性インピーダンスから決まる。口端の最初の差も粒度が異なる。FDTDでは旧圧力を一ステップで隣へ伝えるためセル数−1、波動管は管長と音速から決まる片道点数で始まる。観測全体の主波束は4.3 µs以内にそろった。3,250 Hzの差は、減衰尾部を抑えても残り、独立の離散計算でも現れた。今回の格子変更はセル長と時間刻みを同時に半分にしたため、端の半セルと内部の離散分散の寄与を分けるには別の対照が必要になる。[長いインパルスの記録](../runs/uniform-waveguide-matched-20261121-long/manifest.json)・[数値と初回差分位置](../runs/uniform-waveguide-matched-20261121-bandlimited-b/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Apple Clang 17.0.0、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1。上流の公開APIを使い、一時パッチは不要だった。候補41試験と上流3試験、ClippyとWASMのコンパイル検査に通過した。`viscous_scale` を省いた従来ケースのCSVは保存済みの基準とバイト一致し、倍率が0、0.5、1、2のときに管内の枝抵抗だけが倍率に従うことも確認した。負倍率と文字列は出力前に拒否した。[従来ケースの回帰とCLI実行記録](../runs/uniform-waveguide-matched-20261121-long/manifest.json)

最初のCビルドはHomebrew版ClangからSDKヘッダを読めず止まった。AppleのSDKを `xcrun --sdk macosx` で選んで再実行した。最初の帯域制限解析は共有CSV読込がgzipに非対応だったため停止し、圧縮を透過的に読めるよう変更した。0.5秒の9系列は、3秒の各系列の先頭と展開後にバイト一致した。短い実行は26.48 MB、長い実行は144.11 MB、帯域制限の追加計測は約30 kB。全長の時系列を可逆圧縮してRTL9210B-CGに置き、追加解析は長い時系列を参照した。[Cビルド時のログ](../runs/uniform-waveguide-matched-20261121-a/manifest.json)・[gzip読込の停止記録](../runs/uniform-waveguide-matched-20261121-bandlimited/manifest.json)・[帯域制限の確定記録](../runs/uniform-waveguide-matched-20261121-bandlimited-b/manifest.json)

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=130000000 ../../.venv/bin/python tools/measure_uniform_waveguide.py uniform-waveguide-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=750000000 ../../.venv/bin/python tools/measure_uniform_waveguide.py uniform-waveguide-local-2 --long-window
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=12000000 ../../.venv/bin/python tools/measure_uniform_waveguide.py uniform-waveguide-local-3 --bandlimited
```

各コマンドは新しい実行IDを使う。延長ケースは登録済みの短い実行を、帯域制限ケースは登録済みの3秒の計測をハッシュで確認して使う。96 kHzの振幅判定は不通過のため、成功項目と数値がそろった実行でも総合ステータスは `fail` となる。

帯域制限の確定実行は `/tmp` から行い、研究ワークスペースから再実行した。要約と3条件のFIR係数の計4ファイルがSHA-256まで一致した。[再実行](../runs/uniform-waveguide-matched-20261121-bandlimited-repeat/manifest.json)
