# 声門ピッチのドリフトとビブラート

## 上流の経路と状態

`HumanVoice::apply_source` は基本周波数・ビブラート・ドリフトを声門に設定する。 `control` は歌唱などの制御点を反映し、`render` は毎サンプルの声門前後の差圧を `ParametricGlottis::next` に渡す。今回の比較は固定した基本周波数・深さ・速度から始め、低速の変動が声門の位相と面積に加わる経路を分離する。[上流の音源設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs)・[上流の声門更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs)

`next` は内部サンプル0から32サンプルごとにドリフトとビブラートを更新する。 `Drift::step` は別シード4242の乱数から、0.3・0.9・2.7 Hzの一次フィルタを進める。制御レートを `fs/32` とすると、極 `a=exp(−2πf/(fs/32))` に対し状態を `a·旧状態 + √(1−a²)·乱数` で進める。各フィルタに使う乱数は一様乱数4個の和から求め、三つの出力を `(y₀ + y₁/2 + y₂/3)/1.4` として混ぜる。この値は無次元で、ジッタとシマーの乱数状態とは独立している。[ドリフトと乱数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs)・[周期変動の読解](glottal-cycle.md)

ビブラートの位相は周回単位。更新ごとの増分は `vibrato_rate·32/fs·(1+0.04·drift_value)`。ドリフトの深さを0にしても、ドリフト値によるビブラート速度の揺らぎは残る。深さの指定はセントで、`cents = vibrato_depth·sin(2π·phase) + drift_cents·drift_value`、`f0_now = f0·2^(cents/1200)`。この周波数を次の更新まで保持して、周期倍率で割った位相増分に使う。面積は引き続き差圧で駆動される声門パルスと隙間の和。上流のエンジンのテストは、これらの低速状態を含むレンダーを複数のホストブロックで比較する。[声門の位相計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs)・[上流のブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

## 実装前に登録した比較

96 kHz・基本125 Hzで、独立した一定差圧ケースのドリフト14セントのみと、ビブラート36セント・6 Hzのみを比較する。ドリフトのセント値の標準偏差は0.25以上、ビブラートの幅は70セント以上で正方向のゼロ交差から推定する周波数は5.5〜6.5 Hzと予測する。揺らぎのない6 Hzの正弦波とのセント差のRMSが0.2を超えることも確認する。[ドリフト](../cases/glottal-pitch-drift.json)・[ビブラート](../cases/glottal-pitch-vibrato.json)

固定声道との結合ケースはドリフト5セント、ビブラート36セント・6 Hz、ジッタ0.4%・シマー3%を同時に使う。F0の変更はサンプル0から32サンプル間隔で起こり、独立した三つのIIR、ビブラート位相の累積、セントからHzへの換算と一致すると予測する。上流の公開された `f0_now` を含む観測列、独立計算した位相増分と面積、声道と結合した場合のPCMの77・128フレーム分割を照合する。[声道と結合](../cases/glottal-pitch-voiced.json)

## 実装と結果

コアは32サンプル間保持するピッチ倍率を声門位相の計算前に適用する。毎周期の倍率とドリフトの乱数状態は別々に進める。計測器はPythonで生成した乱数をSciPyの3本のIIRに通し、ビブラートの位相をNumPyで累積して瞬時F0を再構成する。声門位相は観測値の差分で照合し、面積の独立計算には観測した位相と独立計算した周期ごとの振幅倍率を使う。[Rustの実装](../crates/vocal-core/src/glottis.rs)・[Pythonの計測](../tools/measure_glottal_pitch.py)

| ケース | 観測結果 |
| --- | --- |
| ドリフトのみ | セント値の標準偏差は9.29セント、最大と最小の差は51.54セント。8判定を通過。[計測](../runs/pitch-drift-20261119-a/summary.json) |
| ビブラートのみ | 正方向のゼロ交差から5.931 Hz、最大と最小の差は72.00セント。一定速度の6 Hz正弦波との差はRMSで12.02セント。10判定を通過。[計測](../runs/pitch-vibrato-20261119-a/summary.json) |
| 呼気・固定声道との結合 | 上流の22系列に対し、最大差は放射流量の時間差分でピーク比 `1.19×10⁻¹³`。候補側の77・128フレーム分割でWAVと出力段CSVがバイト一致し、48 kHzのf32 PCMは96,000フレーム。9判定を通過。[計測](../runs/pitch-voiced-20261119-a/summary.json) |

3条件とも瞬時F0の6,000回の更新を確認し、各192,000サンプルのF0が上流と数値で完全に一致した。独立した瞬時F0との差はピーク比 `4.24×10⁻¹⁵` 未満、位相増分の絶対差は `1.15×10⁻¹⁶` 未満だった。これらは内部96 kHz、基本125 Hzで、ピッチ設定を時間変化させない場合の結果。歌唱などでのピッチ目標の更新は、スコアと調音の接続時に検証する。[ドリフトの実行記録](../runs/pitch-drift-20261119-a/manifest.json)・[ビブラートの実行記録](../runs/pitch-vibrato-20261119-a/manifest.json)・[結合の実行記録](../runs/pitch-voiced-20261119-a/manifest.json)
