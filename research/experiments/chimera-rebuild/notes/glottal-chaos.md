# 声門のロジスティック写像と周期倍化

## 固定上流の経路と状態

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のワニのモデルでは、`control` が `CHAOS` の無次元値を `glottis_src.params.chaos` へ渡し、同じ操作値からジッタとシマーも設定する。`sample` は `mammal::step_glottis` で声門前後の圧力差（dyn/cm²）を `ParametricGlottis::next` へ渡し、面積（cm²）をポートに適用して気道を1サンプル進める。今回は写像を直接指定し、まず一定差圧の声門で調べる。[ワニの制御と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)・[ポートとの接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)

初期値は `x=0.37`、周期長倍率と振幅倍率は1。強さ `c` が正のとき、位相が折り返すたびに `r=2.9+1.1·min(c,1)`、`x←(r·x)·(1−x)` と更新する。値が開区間 `(0,1)` から外れた場合は `0.37` に戻す。`c=0` では状態を進めない。更新後の `x` から、周期長倍率には `0.45c(x−0.5)`、面積振幅倍率には `1.1c(x−0.5)` を加える。ジッタ、シマー、交互周期の寄与を合成した後に倍率を制限する。同じ折り返しサンプルは旧周期の倍率で位相を進め、新しい振幅倍率で面積を作る。`f0_now` は倍率を反映する前の値で、`reset` は写像の状態を保持する。[初期状態とリセット](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L113)・[周期境界の処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L183)

上流の `the_creatures_hold_at_the_lighter_rate` はワニを含む各音源の初回の鳴き声を32 kHzと48 kHzでレンダーし、有限性とRMSを確認する。`the_alligator_dies_to_zero` は無音への復帰を確認するx86_64向けのテスト。写像そのものは、固定版ライブラリを呼ぶプローブの位相、面積、圧差、流量を使って照合する。[上流のレート試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L118)・[上流の無音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L185)

## 実装前に登録した比較

内部96 kHz、一定差圧7000 dyn/cm²、固定124 Hz、開大0 cm²で、ジッタ、シマー、交互周期、ピッチ変動を0にする。336,000サンプルを採り、240,000サンプル以降の完全な周期を使う。別のPython計算で初期値から状態を反復し、位相増分から逆算した状態、周期長、面積波形に照合する。状態 `x` と `k` 周期後の値の差のRMSで反復を判定し、`log|r(1−2x)|` の区間平均も計測する。

| 設定値 `c` | 写像係数 `r` | 予測する並び |
| --- | --- | --- |
| 0.05 | 2.955 | 約0.66159の1点に収束。1・2・4周期ずらした差が小さい。[固定点](../cases/glottal-chaos-fixed-point.json) |
| 0.30 | 3.230 | 2点の間を交互に移動。1周期差が大きく、2周期差が小さい。[周期2](../cases/glottal-chaos-period-2.json) |
| 0.55 | 3.505 | 4点を反復。2周期差も大きく、4周期差が小さい。[周期4](../cases/glottal-chaos-period-4.json) |
| 0.80 | 3.780 | 1・2・4周期差が大きく、有限区間のリアプノフ指数が正。[非周期](../cases/glottal-chaos-aperiodic.json) |

結合ケースは交互周期の固定声道ケースに `c=0.8` を追加し、ジッタ・シマー・交互周期と合わせた倍率を検証する。位相からの逆算ではジッタと交互周期の寄与を独立計算で除き、面積の照合ではシマーも再構成する。位相の1サンプル進行量は周期境界で切り替わり、折り返し端数を持ち越すため、整数の周期長には1.6サンプルの許容差を設ける。候補の77・128フレーム分割で48 kHzのPCMと出力段の時系列を照合する。[声道との結合](../cases/glottal-chaos-voiced.json)

## 実装と計測結果

Rustコアに無次元の写像状態を追加し、ケースから `glottis.params.chaos` を0〜1で指定できるようにした。位相の折り返し直後の増分を公称増分で割った比の逆数から周期長倍率を得る。ジッタと交互周期が作る倍率を引くと `0.45c(x−0.5)` が得られ、状態を逆算できる。面積については、独立に反復した状態から振幅倍率を作り、観測位相と差圧を使って再計算した。`chaos-orbit.csv` に完全な周期の開始サンプル、周期長倍率、逆算値、独立計算値を保存した。[Rustの実装](../crates/vocal-core/src/glottis.rs)・[独立計測](../tools/measure_glottal_cycle.py)・[周期4の状態CSV](../runs/chaos-period-4-20261119-a/artifacts/chaos-orbit.csv)

| ケース | 状態の最小〜最大 | ずらした状態との差のRMS | リアプノフ指数の区間平均 |
| --- | --- | --- | ---: |
| 固定点 | 0.66159051〜0.66159054 | 1周期で `1.09×10⁻⁸` | −0.0460。[結果](../runs/chaos-fixed-point-20261119-a/summary.json) |
| 周期2 | 0.50211〜0.80749 | 1周期で0.30537、2周期で `1.17×10⁻¹⁵` | −1.8247。[結果](../runs/chaos-period-2-20261119-a/summary.json) |
| 周期4 | 0.38021〜0.87620 | 2周期で0.09438、4周期で `9.34×10⁻¹⁶` | −0.4829。[結果](../runs/chaos-period-4-20261119-a/summary.json) |
| 非周期 | 0.19660〜0.94496 | 1周期で0.45929、2周期で0.30436、4周期で0.35811 | +0.3673。[結果](../runs/chaos-aperiodic-20261119-a/summary.json) |
| 声道との結合 | 0.19985〜0.94399 | 1周期で0.45559、2周期で0.29236、4周期で0.34350 | +0.4134。[結果](../runs/chaos-voiced-20261119-a/summary.json) |

5ケースの57項目が通過した。位相から逆算した状態と独立反復の最大絶対差は `1.48×10⁻¹⁴` 未満、固定上流の時系列との最大差は系列ピーク比 `1.22×10⁻¹³` 未満だった。結合ケースは77・128フレームのどちらも同じモノラルf32 WAVと出力段CSVを生成した。上流の32・48 kHzレート試験は通過した。ワニの無音試験はx86_64向けで、arm64の実行では対象テスト数が0だった。今回の声道結合は固定声道を使い、ワニ固有の形状、操作、鳴き声は派生機能の段階で扱う。[結合の実行記録](../runs/chaos-voiced-20261119-a/manifest.json)・[上流の無音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L185)
