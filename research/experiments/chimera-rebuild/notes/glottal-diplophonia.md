# 交互周期による声門面積の変動

## 固定上流の経路と更新順序

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`HumanVoice::set_source` が `SourcePatch` を適用し、`apply_source` が粗さ `roughness` から `diplophonia` を決める。粗さが0.5までは0、0.5を超えると `1.4·(roughness−0.5)` になる。ジッタとシマーも同じ粗さから別に決まる。今回の固定ケースは声門の `diplophonia` を直接指定し、ほかの変動を0に固定する。`render` は声門の前後圧差（dyn/cm²）で `ParametricGlottis::next` を進め、返された面積（cm²）をポートに設定した後で気道を解く。[上流の音源設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L330)・[上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L394)

初期状態は位相0、周期番号0、周期長倍率と振幅倍率は1。各サンプルで、フライとピッチ変動を反映した `f0_now`（Hz）を内部レートと現在の周期長倍率で割り、位相（周）を進める。1周を越えたら位相の端数を持ち越し、周期番号を更新する。最初の折り返し後は奇数。交互周期の強さを無次元の `d` とすると、ジッタとシマーを0にしたとき、奇数周期は長さ倍率 `1+0.08d`、振幅倍率 `1−0.35d`、偶数周期は `1−0.08d` と `1` になる。同じ折り返しサンプルでは位相増分に旧周期の長さ倍率、面積に新周期の振幅倍率を使う。直接観測する `f0_now` は周期ごとの長さ倍率を適用する前の値。[初期状態](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L113)・[位相と倍率の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L171)

ジッタ、シマー、交互周期を使う場合は、それぞれの寄与を足してから長さ倍率を `[0.55, 1.8]`、振幅倍率を下限0.12で制限する。周期ごとの乱数は長さ用、振幅用の順に引く。声門面積の周期成分だけに振幅倍率を掛け、静的な隙間はその後に足す。上流の `reset` は位相と圧力・発声の平滑値を戻し、周期番号と倍率を保持する。今回は毎回初期状態からレンダーする。[折り返しと面積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L183)・[リセット](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L142)

上流の `folds_held_apart_meet_for_less_of_the_cycle` は一定差圧で声門面積から開口時間を計測し、`output_does_not_depend_on_the_host_block_size` はイベント時刻をそろえてレンダー経路を比較する。交互周期を直接観測するため、固定上流ライブラリを呼ぶプローブで全サンプルの位相・面積・F0・流量を採取する。[開口時間のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62)・[ブロック分割のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 実装前に登録した比較

一定差圧7000 dyn/cm²、内部96 kHz、固定124 Hz、開大0 cm²の声門で、`d=0` と `d=0.7` を比較する。サンプル774の最初の折り返しで位相に端数が残るため、0.7の条件ではそのサンプルの面積を、振幅の変更を次サンプルまで遅らせた独立計算とも比較する。24,000から120,000サンプルの測定窓で、完全な周期の長さと隙間を引いた面積ピークを偶奇ごとに集計する。

| ケース | 予測と観測点 |
| --- | --- |
| 交互周期なし | 奇数・偶数とも約774.19サンプルで、面積ピーク比は1。面積の62 Hz成分は124 Hz成分の0.1%以下。[ケース](../cases/glottal-diplophonia-control.json) |
| 交互周期0.7 | 奇数周期約817.55、偶数周期約730.84サンプル、ピーク比0.755。周期対を連続波形として数値積分すると、62 Hz対124 Hzの振幅比は0.1160と予測できる。位相増分は最初のサンプルから照合する。[ケース](../cases/glottal-diplophonia-fixed.json) |
| 呼気・声道・出力との結合 | 125 Hz、交互周期0.7、ジッタ0.4%・シマー3%。乱数と交互差を合成した倍率を独立計算し、安定発声区間の平均で奇数周期が約86サンプル長くなると予測する。77・128フレーム分割のPCMも照合する。[ケース](../cases/glottal-diplophonia-voiced.json) |

## 実装と結果

Rustコアは周期番号の偶奇を真偽値として保持し、折り返しごとに反転する。`inspect` と `render` が読むケースJSONに、0〜1の `glottis.params.diplophonia` を追加した。Pythonは乱数列と偶奇を配列で構成し、観測位相の差分に対して周期長倍率を、観測位相から再計算した面積に対して振幅倍率を全区間で確認した。面積のスペクトル比は、安定区間の平均を引いた波形にハン窓を掛け、62 Hzと124 Hzへ直接投影して求めた。[Rustの声門](../crates/vocal-core/src/glottis.rs)・[独立計測](../tools/measure_glottal_cycle.py)

| ケース | 奇数周期の平均 | 偶数周期の平均 | 奇数／偶数の面積ピーク比 | 補足 |
| --- | ---: | ---: | ---: | --- |
| 一定差圧、交互周期なし | 774.18サンプル | 774.19サンプル | 1.00000 | 62 Hz／124 Hzの振幅比は `2.55×10⁻⁹`。[結果](../runs/diplophonia-control-20261119-a/summary.json) |
| 一定差圧、交互周期0.7 | 817.44サンプル | 730.94サンプル | 0.75500 | 62 Hz／124 Hzの振幅比は0.11605。振幅変更を遅らせた計算との最初の折り返しでの面積差は `3.74×10⁻⁷ cm²`。[結果](../runs/diplophonia-fixed-20261119-a/summary.json) |
| 呼気・固定声道、交互周期0.7 | 811.81サンプル | 726.11サンプル | 0.75238 | 候補の77・128フレーム分割は同一のPCMと出力段CSVを生成。48 kHz、96,000フレーム。[結果](../runs/diplophonia-voiced-20261119-a/summary.json) |

算出した非整数の周期長と、整数のサンプル番号で数えた長さとの差は全ケースで1サンプル未満だった。折り返し直後に残る位相を `φ₁`、次の折り返し直後を `φ₂` とすると、観測した長さは `公称周期長·周期長倍率·(1+φ₂−φ₁)` になる。長短の周期で位相増分が交互に変わるため、丸めの影響は偶奇の平均にも残り得る。上流との最大差は各系列のピーク比 `9.77×10⁻¹⁴` 未満で、`glottal_f0_hz` はどのケースも設定値と一致した。確認した範囲は、ケースから交互周期の値を直接指定する固定入力。粗さの操作からジッタ・シマー・交互周期を同時に変える入力経路は、今後の制御との接続で検証する。[固定ケースの実行記録](../runs/diplophonia-fixed-20261119-a/manifest.json)・[声道結合の実行記録](../runs/diplophonia-voiced-20261119-a/manifest.json)
