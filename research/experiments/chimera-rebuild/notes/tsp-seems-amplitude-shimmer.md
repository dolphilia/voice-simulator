# seems の周期ごとの振幅の揺らぎ

ドリフトと周期長ジッターを0にそろえた上流版と研究版で、シマーを0と0.042に切り替える。対象は `seems` の /i/ の1.1525〜1.1775秒。前回は、周期長ジッターまで揃えた条件で、瞬時F0と位相が先頭113,200内部標本で一致した。シマーは上流0.042、研究版0で、高域LPC極の版間差は2.3033 Hzだった。[事前登録](../cases/tsp-seems-amplitude-shimmer.json)・[周期長ジッターの比較](tsp-seems-period-jitter.md)

## 上流の読解

- `crates/chimera-cli/src/render.rs` の `say` は発話計画を `HumanVoice` に渡す。`crates/chimera/src/voice/human_voice.rs` の `apply_source` は、roughness 0.1から無次元のシマー係数 `0.02 + 0.22 × 0.1 = 0.042` を計算する。粗さの設定を変える方法では周期長ジッターも変わるため、離した比較では既存の観測器から上流の周期長ジッター、シマー、ドリフトを個別に指定する。
- `crates/chimera/src/sources/glottis.rs` の `ParametricGlottis::next` は96 kHzで瞬時F0から位相を進め、1周期を越えた標本で振幅倍率を更新する。初期倍率は1。このケースでは倍周期化とカオスを0にしており、倍率は `max(0.12, 1 + shimmer × g₂)`。`math.rs` の種777のMulberry32で、先に周期長用の4乱数を消費し、次の4乱数の和から2を引いて1.7320508を掛けた値が `g₂` になる。係数が0でも両方を消費する。変更直後の倍率は同じ境界標本のパルスへ適用され、次の境界まで保持される。
- 面積は声帯の有効振幅（cm²）、周期振幅倍率、有声度、位相に応じたパルス形状の積に静的開口を加えて算出する。圧差（dyn/cm²）と有声度は別の平滑状態で、振幅変化は面積パルスを介して気道の状態へ伝わる。`HumanVoice::render` は面積を声門枝に反映した後、`AirwayNetwork::step` の流量（cm³/s）と放射の時間差分を更新し、間引き・DC除去・レベル調整で48 kHz PCMを得る。
- `tests/voice_source.rs` は閉鎖形状と高域出力、`tests/golden_voice.rs` は固定発話PCMとブロック分割時の一致、`tests/golden_analysis.rs` はLPC出力を検証する。研究版の `timing_case/speech_voice.rs` は `source_variation.amplitude_shimmer` を既存の `set_amplitude_shimmer` に渡す。研究版の `Glottis::step` でも境界で周期用・振幅用の順に乱数を消費し、境界標本の面積に振幅倍率を適用する。

## 実測

固定上流では既存の観測器の `zero` 条件でドリフト、ジッター、シマーを0にした。先行の上流ジッター0条件はシマー0.042を保持している。研究版では既定入力と、`source_variation.amplitude_shimmer` に0.042だけを指定した入力を通常CLIで描画した。両版の既定出力と研究版の追加条件で、通常CLIと観測付きの全116,132 PCMフレームを照合した。先行の4条件も、全PCMのハッシュと保存窓に一致した。

| シマー | 固定上流の高域LPC極（Hz） | 研究版の高域LPC極（Hz） | 版間差（Hz） |
| --- | ---: | ---: | ---: |
| 0 | 2,212.4484516344 | 2,212.4484516344 | 0 |
| 0.042 | 2,210.1451457646 | 2,210.1451457646 | 0 |

両版ともシマーを加えると高域LPC極が2.3033058698 Hz下がった。シマーの値を揃えた両組で、25 ms窓のLPC入力300標本がバイト単位で一致した。声門流量の1,950〜2,600 Hz内のパワー分布の版間距離は、シマー0で1.84×10⁻¹⁴、0.042で2.15×10⁻¹⁴だった。シマーを加えたことによる版内の距離は両版とも約0.01409。窓の声門面積は2,400標本すべてで一致し、声門流量の版間差は最大1.11×10⁻¹¹ cm³/sだった。独立した放射・出力計算で各条件の先頭56,600 PCMフレームを再現した。

先頭113,200内部標本で、実測F0から独立に計算した位相と振幅倍率が一致した。最初の周期境界である第871内部標本でシマー切り替えによる振幅差が生じた。両版とも面積と声門流量は第8,081標本、圧差と有声度は第8,082標本で初めて異なった。瞬時F0と位相は一致した。シマー係数を揃えた2組では振幅倍率もビット単位で一致した。計測8判定と事前登録の3仮説は通過した。[計測要約](../runs/tsp-seems-amplitude-shimmer-20261123-repeat/summary.json)

全発話の版間PCMには差があり、シマーを揃えた条件でも第0フレームで最初の差、第13フレームで初めて1×10⁻⁷を超える差が出た。冒頭の第0内部標本で舌先位置と口端流量、第1内部標本で声門上下の圧力差が異なった。次は両版の初期調音姿勢と気道断面を照合し、初期姿勢だけをそろえた条件で最初の放射とPCMを比較する。

## 再実行

`research/experiments/chimera-rebuild` で別の実行IDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_seems_amplitude_shimmer.py tsp-seems-amplitude-shimmer-new
```

実行環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。周期の観測は `cycle-traces.npz`、解析窓とスペクトルは `drift-windows.npz` と `drift-spectra.npz` にある。研究版の追加条件の入力、計画、固定上流のLPC、試験ログはマニフェストから辿れる。ビルドと一時波形・計測成果にはRTL9210B-CGを使った。[初回](../runs/tsp-seems-amplitude-shimmer-20261123-a/manifest.json)・[再実行](../runs/tsp-seems-amplitude-shimmer-20261123-repeat/manifest.json)

実験ディレクトリと `/tmp` の実行で、要約、周期系列、解析窓、スペクトル、LPC、発話計画がバイト単位で一致した。両方で上流4試験と研究版17試験を通過した。共通の観測器から先行のジッター比較を再実行し、周期系列・窓・スペクトル・LPC・要約が保存出力と一致した。[先行ケースの再確認](../runs/tsp-seems-period-jitter-20261123-recheck-after-shimmer/manifest.json)
