# 発話時刻に対応する声門面積と流量の波形

## 固定上流の読解と事前登録

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`Stroboscope` が `AudioEngine.latest` から Worklet の `humanTelemetry` を受け取り、巻き戻した2周期の面積・流量と声帯の開閉を描く。`HumanVoice::render` が出力フレームごとに面積と流量を4,096点の環状バッファへ入れ、位相が周回した位置を記録する。`HumanVoice::telemetry` は発声係数が0.2を超え、有効な区間があれば直近の完了2周期を選ぶ。その他では直近1,024出力フレームを使う。どちらも256点に間引いて返す。上流の `tele.test.ts` は転送列の位置を、`engine` テストはホスト分割で音が変わらないことを検査する。[上流の表示](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Stroboscope.tsx)・[リングの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L427)・[切り出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L607)・[観測列テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts)・[分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

各内部サンプルで、声門上下の圧力差を受ける `ParametricGlottis::next` が圧力と発声係数を平滑化し、位相を進める。面積は静的開口と周期パルスの和を非負にした値（cm²）。この面積でポートを更新し、気道の枝計算が圧力差、慣性、損失に応じた体積流量（cm³/s）を進める。正は気管から咽頭へ向かう流れ。面積と流量は間引き器が出力を確定した内部ステップから採取する。候補の `OutputStage::render_frame` とCLIの既存 `render` も同じ内部ステップを観測できる。[声門面積の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[面積→枝→出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L386)・[候補の出力時計](../crates/vocal-core/src/output.rs#L65)

研究用の波形は発話の選択時刻を0 msに置き、前後12 msの実時刻を示す。開始・終端では実際に存在するフレームだけを描く。48 kHzの `ɑpɑ` で、フレーム6,750の母音では面積変動幅が0.1 cm²以上で、面積ピーク間隔が `48,000 / 平均F0` の3%以内になると予測する。閉鎖中の12,287では面積変動幅が0.002 cm²以下で、逆流のピーク絶対値が20 cm³/s以上になると予測する。全出力フレームをCLIおよび上流のレンダー後の観測と比較し、既存の低頻度系列とも照合する。960・390 CSS pxで選択、時刻、波形座標、先頭・末尾の切り詰めを独立に検査する。[登録条件](../cases/worklet-glottal-scope.json)・[発話の基準](../cases/worklet-ipa-voice.json)・[閉鎖区間の先行測定](../runs/bilabial-p-20261119-e/summary.json)

## 実装と再現手順

`vocal_glottal_trace_init` でWASMのブロック用バッファを確保し、`vocal_render` の既存のループで各出力の面積と流量を交互に書く。Workletはレンダー済みの出力番号を基準に全発話分の領域へコピーする。観測JSONの `glottal.columns` は1フレーム内の順序、`glottal.values` はフレーム0からの平坦な配列。サンプル番号 `i` の経過時刻は `(i + 1) / fs_out` 秒。画面は同じフレーム選択を使い、上下のスケールは発話全体で共通にする。通常の48 kHzの窓は両端を含む1,153点で、発話先頭と末尾では各577点になる。[WASM](../crates/vocal-wasm/src/lib.rs)・[Worklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[描画](../../../../web/prototypes/chimera-research/src/glottal-scope.tsx)

比較は既存のCLI `render` と上流観測プローブを使う。上流の `HumanVoice::render` の直後に声門面積と枝流量を直接読み、保存した全サンプルを照合する。出力ファイル・音素計画・口唇の系列も既存の発話比較手順で検査する。[比較ツール](../tools/measure_worklet_ipa.py)・[波形の判定](../tools/measure_glottal_scope.py)

```bash
python3 tools/measure_worklet_ipa.py worklet-glottal-scope-local-1 --scope
```

## 結果

`ɑpɑ` の49,828出力フレームで声門面積と流量はCLIと完全に一致し、既存の16フレーム間隔の観測にも一致した。PCMもCLIとビット一致した。固定上流との最大差は面積 `7.63×10⁻¹⁷ cm²`、流量 `2.30×10⁻¹¹ cm³/s` と許容差内。全既存系列では口端面積・放射でフレーム0、声門直上圧力で1、声門流量で2に最初の差が現れた。声門面積の最初の差はフレーム4,064だった。上流の有気指定・高速発話・ホスト分割を含む10件のテストも通過した。[初回の結果](../runs/worklet-glottal-scope-20261119-a/summary.json)・[上流テスト](../runs/worklet-glottal-scope-20261119-a/artifacts/upstream-tests.log)

フレーム6,750の窓では面積の変動幅が0.13548 cm²。ピークの間隔は2区間とも441フレームで、平均F0から求めた441.91フレームとの差は0.205%だった。フレーム12,287の閉鎖窓では面積の平均が0.37480 cm²、変動幅は0.000385 cm²。流量の最小はフレーム12,057の `−59.19 cm³/s` だった。その出力フレームの声門上下圧差は `−15.89 dyn/cm²`。面積と流量を同時に残すことで、この窓の開大、周期変動の抑制、逆流を区別できる。[窓の計測](../runs/worklet-glottal-scope-20261119-a/summary.json)・[毎フレームのCLI観測](../runs/worklet-glottal-scope-20261119-a/artifacts/voicing.csv)

960・390 CSS pxで、5つの選択時刻における描画座標と値を検査した。独立計算との差は最大 `1.14×10⁻¹³` SVG単位。2回の実行で各20判定が通過し、PCM、観測JSON、波形座標と4枚の画像はSHA-256が一致した。毎フレームの観測追加でこの1.04秒の観測JSONは約1.20 MBから3.91 MBになった。[母音の画面](../runs/worklet-glottal-scope-20261119-b/artifacts/scope-960-voiced.png)・[閉鎖の画面](../runs/worklet-glottal-scope-20261119-b/artifacts/scope-390-closure.png)・[再実行](../runs/worklet-glottal-scope-20261119-b/manifest.json)
