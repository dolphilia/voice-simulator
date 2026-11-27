# 体型補間と矢状面の寸法

固定上流のWASMは `model` で体型を読み、`BodyMix::body` で解剖パラメータを求めてから `HumanAirway::new` を作る。`frame` は同じモデルの `HumanVocalTract::compute_new` に姿勢を渡す。連続入力は成人女性の割合 `f` と子どもの割合 `c` をそれぞれ0〜1に丸める。成人男性・成人女性・子どもの重みは順に `(1−c)(1−f)`、`(1−c)f`、`c`。解剖パラメータは重み付き算術平均、既定F0は対数の加重平均をHzへ戻す。子ども端点では成人女性軸の寄与は0になる。同じ重みの表示名は成人男性、成人女性、子どもの順で選ぶ。最大重みが1のときは端点の値を取り出す。[WASMのモデル作成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L68)・[体型と重み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L265)・[既定F0](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L25)

テンプレートの点は前方 `x > 0.5` cmの分を0.86倍し、`y < 7` cmの分を体型の咽頭係数で縮め、両座標を全体係数 `k` で拡大縮小する。固定輪郭の補間曲線は、変換した制御点から作る。顎回転、舌の円と接線、軟口蓋、唇などをその座標系で構築する。例えば舌体半径は体型の半径に `k` を掛け、喉頭蓋上部の起点長は `2.4 × k × 咽頭係数` cm。軟口蓋ポートの面積は `max(0, 設定) × k²` cm²。接触補正の距離窓も `k` に従う。断面積は測った隙間から非線形に求め、喉頭蓋上部の既定面積は `k²` で変換する。したがって成人男性の完成した形状の一様縮小では、全体の断面や長さは再現できない。[座標変換と輪郭](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L654)・[測定線と接触](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L985)・[中心線・断面・再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1185)

上流の `body_mix.rs` は3端点の一致、重みの総和、既定F0と目標の中間値、/a/ のF1・F2の順序、混合声道での発声を検査する。今回のケースでは調音入力を共通にして解剖モデルの効果を測る。中立と、喉頭上昇・軟口蓋開放・舌背と唇の動きを同時に指定した固定姿勢を登録した。3端点、成人・子どもの中間、3体型混合、子ども端点での女性軸、範囲外の丸めを独立計算に照合し、輪郭・中心線・接触補正済みの断面・18＋18セルを上流と比較する。[上流のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)・[登録ケース](../cases/human-body-geometry.json)

## 実装と結果

Rustの `BodyMix` が求めたパラメータを既存の `SagittalModel` に渡し、輪郭、測定線、接触の距離、断面、等長セルをその順に計算する。CLIの名前指定は既知の端点名を受理し、二軸の指定では省略軸を0にする。既存の男性ケースの出力形式を保ちつつ、`measurement.body` で男性の補間情報も取得できる。独立側は顎の回転に複素数を使い、体型の既定F0は端点周波数の重み付きべき乗積で計算した。セルの独立計算は測った断面列を入力に、喉頭蓋上部を含む8中点の調和平均と実測格子点の閉鎖判定を再計算する。[体型のRust実装](../crates/vocal-core/src/anatomy/body.rs)・[形状](../crates/vocal-core/src/anatomy.rs)・[CLI](../crates/vocal-cli/src/geometry_case.rs)・[比較プログラム](../tools/measure_body_geometry.py)

| 体型 | 全体係数 | 咽頭係数 | 中立の咽頭長 (cm) | 中立の声道長 (cm) | 開放姿勢の軟口蓋ポート (cm²) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 成人男性 | 1.000 | 1.0000 | 8.831 | 17.130 | 0.7200 |
| 成人女性 | 0.900 | 0.8800 | 7.206 | 14.643 | 0.5832 |
| 子ども | 0.740 | 0.8000 | 5.519 | 11.606 | 0.3943 |
| 成人の中間 | 0.950 | 0.9400 | 7.997 | 15.864 | 0.6498 |
| 成人男性と子どもの中間 | 0.870 | 0.9000 | 7.084 | 14.272 | 0.5450 |
| 成人女性軸0.4・子ども軸0.3 | 0.894 | 0.9064 | 7.319 | 14.710 | 0.5754 |

8体型条件と2姿勢の全130項目が通過した。上流との差は輪郭座標の最大成分差 `3.55×10⁻¹⁵ cm`、測定格子から得た断面積で `1.87×10⁻¹⁴ cm²`、等長セルの断面積で `1.73×10⁻¹⁴ cm²`。等長セルの独立計算との差は最大 `4.44×10⁻¹⁵ cm²`。子どもの咽頭長は成人男性の値に0.74だけを掛けた場合より中立で1.016 cm、開放姿勢で1.020 cm短い。3体型混合の重みは0.42・0.28・0.30で、幾何平均で得た既定F0は169.499 Hzだった。[比較要約](../runs/body-20261120-a/summary.json)・[3体型混合と開放姿勢のCLI出力](../runs/body-20261120-a/artifacts/open-three-way/inspect.json)

`/tmp` からの再実行も130項目を通過し、生成したケース、CLI・上流の輪郭と断面、独立計算、要約など177ファイルがバイト一致した。成人男性の中立輪郭は変更前後で4ファイル、96 kHz相当のセル割当ては7ファイルが一致した。ブラウザの固定ビートの回帰も通過し、WAVと観測JSONは比較元と一致した。固定上流の `body_mix` 4項目、候補のRust整形・Clippy・ワークスペーステストも通過した。[再実行と環境](../runs/body-20261120-repeat/manifest.json)・[成人男性の輪郭](../runs/body-20261120-neutral-after/manifest.json)・[セルの回帰](../runs/body-20261120-resample-after/manifest.json)・[ブラウザの回帰](../runs/body-20261120-worklet-regression/manifest.json)

体型別の固定気道・音源は次の工程で接続する。咽頭と口腔のセル数、鼻腔・気管・側枝の長さと断面、および声門のパラメータにも体型が関わる。[上流の気道構築](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L105)

```bash
python3 tools/measure_body_geometry.py body-geometry-local-1
```
