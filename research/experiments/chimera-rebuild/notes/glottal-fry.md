# ボーカルフライの周期と面積パルス

## 固定上流の経路

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`HumanVoice::set_source` が `SourcePatch` を適用し、`apply_source` が `VoiceSource.fry` を声門に渡す。`render` は内部サンプルごとに声門下圧と声門上圧の差を dyn/cm² で渡し、返された声門面積を cm² で気道グラフのポートに適用してから流量を解く。`telemetry` が公開するF0は `ParametricGlottis::f0_now`、周期境界は位相の折り返しから得る。[上流の音源設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L305)・[上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

`ParametricGlottis::next` はドリフトとビブラートを反映した `f` に、無次元のフライの強さ `w`（0〜1）を使って `f·(1−w)+min(f,48 Hz)·w` を適用する。式の折れ目は48 Hz。声門が保持する周期位相（0〜1周）は、このF0を内部レートと周期倍率で割った分だけ進む。フライ専用の位相状態はなく、第2パルスは同じ周期上に置く。ジッタとシマーを0に固定すると周期倍率と振幅倍率は1になる。[上流の周期更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)

開大と発声の強さを反映した通常の開口率 `q` を、フライで `q·(1−w)+0.28·w` に変える。`shape` はこの開口率の内側で余弦を使って立ち上がりと閉鎖を表し、開口率に対して `skew` の位置で最大になる。`w>0.3` かつ周期位相が0.38を越えると、同じ形を位相0.38だけ遅らせ、開口長を0.8倍、振幅を `0.55·smoothstep(0.3,0.8,w)` 倍にして加える。二つのパルスの和に平滑化した発声ゲートと面積振幅を掛け、隙間面積を足す。面積が隙間を越える時間は、パルスの支持区間の和集合で決まる。[上流の面積更新と波形](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L204)・[補間式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L155)

上流の `folds_held_apart_meet_for_less_of_the_cycle` は一定差圧で、開大の違いによる閉鎖時間の比率を面積から求める。今回も面積と隙間から開口時間を測り、別途フライに対応する予測を登録した。上流のフライ波形は固定版の `ParametricGlottis` を呼ぶ比較用プローブで採取する。[上流の開口時間テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L62)

## 実装前に登録した比較

内部96 kHz・差圧7000 dyn/cm²・開大0 cm²で、ジッタ・シマー・ドリフト・ビブラートを0にする。観測は96,000サンプル、24,000以降の完全な周期で開口時間とパルスを測る。位相差は周回境界をまたいで比較し、個別の周期長は量子化による1サンプルの差を許容する。面積・ゲートの独立計算、上流の声門と枝流量も照合する。

| 入力 | F0と予測した開口 |
| --- | --- |
| 125 Hz、フライ0 | 125 Hz、開口の割合0.584、ピーク1回。[ケース](../cases/glottal-fry-control.json) |
| 125 Hz、フライ0.3 | 101.9 Hz、開口の割合0.4928、ピーク1回。[ケース](../cases/glottal-fry-threshold.json) |
| 125 Hz、フライ0.8 | 63.4 Hz、主パルス0.3408周期、第2パルス0.27264周期。合計0.61344で対照の0.584を上回る。[ケース](../cases/glottal-fry-strong.json) |
| 40 Hz、フライ1 | 40 Hz、主パルス0.28周期、第2パルス0.224周期。[ケース](../cases/glottal-fry-low-f0.json) |

パルスの間に閉鎖区間がある条件では、最初のパルスが閉じている位相から第2パルスの開始を探す。面積が隙間より `10⁻⁸ cm²` を超えた最初の位相は0.38〜0.382、ピーク比は0.548〜0.552と予測した。開口の割合は同じ面積しきい値で測る。

コア実装後、補間範囲の内部とパルスの重なりを確かめるため、フライ0.6のケースを計測前に追加した。125 Hzから78.8 Hzへ下がり、主パルスの開口は0.4016周期。第2パルスは位相0.38から0.70128まで続くため、どちらかが開口している割合を0.70128と予測した。二つのパルスが重なる区間では、合成した面積から第2パルスの開始を直接測れないため、合計開口率と二つのピーク位相・ピーク比0.3564を照合する。[重なる条件](../cases/glottal-fry-overlap.json)

## 実装と結果

ケースJSONの `glottis.params.fry` を通常の `inspect` と `render` で読み、範囲は0〜1とした。第2パルスは既存の面積波形関数を使い、ピッチ変動を反映した周波数を変更してから、従来の位相更新へ進む。Python側は固定条件の位相をサンプル番号から直接求め、圧力・制御の平滑化をSciPyのIIR、面積波形をNumPyで独立計算した。観測したピークは位相が折り返した時刻で区切って数えた。[Rustの声門](../crates/vocal-core/src/glottis.rs)・[計測器](../tools/measure_glottal_fry.py)

| 入力 | 瞬時F0 | 平均周期 | 開口時間の割合 | ピーク数／周期 |
| --- | ---: | ---: | ---: | ---: |
| 125 Hz、フライ0 | 125.0 Hz | 8.000 ms | 58.33% | 1。[結果](../runs/fry-control-20261119-b/summary.json) |
| 125 Hz、フライ0.3 | 101.9 Hz | 9.814 ms | 49.27% | 1。[結果](../runs/fry-threshold-20261119-b/summary.json) |
| 125 Hz、フライ0.6 | 78.8 Hz | 12.690 ms | 70.12% | 2。[結果](../runs/fry-overlap-20261119-b/summary.json) |
| 125 Hz、フライ0.8 | 63.4 Hz | 15.773 ms | 61.34% | 2。[結果](../runs/fry-strong-20261119-b/summary.json) |
| 40 Hz、フライ1 | 40.0 Hz | 25.000 ms | 50.33% | 2。[結果](../runs/fry-low-f0-20261119-b/summary.json) |

フライ0.8では第2パルスが位相0.38004〜0.38069で開き始め、面積ピークは主パルスの約55%。0.6ではピーク比が約35.64%となり、補間が作用していることを確認した。固定した上流との11系列の最大差は全ケースでピーク比 `8.31×10⁻¹⁶` 未満、独立計算との面積差は `2.38×10⁻¹¹` 未満。観測範囲は一定差圧と固定フライの条件。歌唱や操作中のフライ設定の遷移は今後の比較対象となる。[強いフライの実行記録](../runs/fry-strong-20261119-b/manifest.json)・[重なる条件の実行記録](../runs/fry-overlap-20261119-b/manifest.json)
