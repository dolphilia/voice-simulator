# 発話時刻に対応した声道断面を表示する

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `TubeView` は `AudioEngine.latest` から咽頭と口腔の断面列・管長を取得し、面積 `A` cm²を円の相当直径 `2√(A/π)` cmに直して描く。Workletは128フレーム6回ごとに `humanTelemetry` を呼び、WASMの観測列から各管の面積と圧力などを読み出す。`HumanVoice::telemetry` が返す `ph_areas`・`or_areas` と管長は形状目標側の値で、管長は解剖由来。セル数は通常姿勢の最短見込みと `dx_min = (35000 / fs) / 0.93` で決まる。成人男性・内部96 kHzでは咽頭18セル、口腔18セルになる。[上流の描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/TubeView.tsx)・[Workletの受信値](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L202)・[観測元](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L597)・[セル数と管長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L107)

候補の `HumanTractControl::apply` は調音状態から平均として使う調和平均断面と最小断面を再標本化し、変化速度を制限する。舌の接触補正後に `HumanAirway::begin_tract_block` が気道へ形状目標を設定する。気道は各内部サンプルの冒頭で、長さ・面積を目標へ線形補間してから圧力と流量を更新する。表示するのは出力フレーム末尾の**音響格子で実際に使った値**。横軸は声門からの累積セル長、平均断面と最小断面は相当直径で描く。固定上流も同じ比較では `net.dx`・`net.area`・`net.amin` をレンダー直後に観測する。上流の `geometry_continuity` は母音遷移と口唇付近の面積連続性、`engine` はレンダー分割への不変性を検査する。[候補の断面目標](../crates/vocal-core/src/airway/tract_control.rs)・[候補の気道更新](../crates/vocal-core/src/airway/human.rs)・[上流の補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[連続性テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs)・[分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

既存の `ɑpɑ` で48 kHzの出力768フレームごとと末尾の断面を保存する。選択フレーム以前の最後の採取を表示し、採取前は欠測。既存の閉鎖観測は11,119〜13,903フレームなので、12,287フレームでは唇端セルの最小断面が0.0002 cm²以下、16,895フレームでは0.1 cm²以上と予測する。均一な時間間隔と末尾の観測、セル数、全セルの形状とPCMを比較し、幅960・390 CSS pxで選択時刻・図形の座標を独立計算に照合する。[今回の条件](../cases/worklet-tract-profile.json)・[既存の発話条件](../cases/worklet-ipa-voice.json)・[口唇閉鎖の先行結果](../runs/worklet-ipa-timeline-20261119-b/summary.json)

## 実装と再現手順

`HumanAirway::tract_sections` が咽頭、口腔の順に現在の音響セルを返す。WASMの `vocal_tract_init` が観測領域を確保し、`vocal_tract_snapshot` がレンダー直後に値を書き込む。Workletは既存の16フレーム間隔の口唇などの観測に加え、断面全体を16 msごとと最後に採取する。発話完了後に保存できる観測JSONでは、`tract.counts` に咽頭と口腔のセル数、`tract.rows` に出力フレーム番号と各セルの `[長さ cm, 平均面積 cm², 最小面積 cm²]` が並ぶ。出力フレーム `i` の観測時刻は `(i + 1) / fs_out` 秒。開始前を含め、過去の観測がない選択位置には欠測を表示する。断面図は発話全体で共通の軸を使い、選択を変えても縮尺を保つ。[WASMの観測](../crates/vocal-wasm/src/lib.rs#L234)・[Worklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[断面図](../../../../web/prototypes/chimera-research/src/tract-profile.tsx)

CLIは `speech_voice.tract_profile_frames` が指定されたケースを `render` に渡すと、出力フレーム、管名、0始まりのセル番号、セル長、平均面積、最小面積のCSVを保存する。比較ツールはこのケースを事前登録した間隔から生成し、固定上流側の観測プローブにも渡す。ブラウザで実際に入力・保存し、スライダーの選択結果、両画面幅の図形座標、PCM、全セルを検査する。[CLIの観測](../crates/vocal-cli/src/timing_case/speech_voice.rs#L518)・[上流の観測プローブ](../tools/upstream_bilabial_probe.rs#L393)・[比較ツール](../tools/measure_worklet_tract_profile.py)

```bash
python3 tools/measure_worklet_tract_profile.py worklet-tract-profile-local-1
```

## 結果

合計49,828フレームの `ɑpɑ` で、フレーム767から末尾49,827まで65時点を採取した。咽頭・口腔各18セルの長さ・平均面積・最小面積は全点でCLIと数値が一致し、同じ観測時刻の口唇系列も一致した。固定上流との差は、セル長が最大 `5.55×10⁻¹⁷ cm`、平均面積が `2.27×10⁻¹³ cm²`、最小面積が `2.31×10⁻¹³ cm²`。最初の差はいずれもフレーム767の咽頭セルで現れ、許容差を超えた点はなかった。PCMはCLIの77・128フレーム分割とビット一致し、固定上流との差はフレーム13,291から現れ、最大 `1.82×10⁻¹²` だった。[初回の計測](../runs/worklet-tract-profile-20261119-a/summary.json)

| 出力フレーム | 時刻 | 声門から口端まで | 唇端セルの平均面積 | 唇端セルの最小面積 |
| --- | --- | --- | --- | --- |
| 12,287 | 256 ms | 16.346 cm | 0 cm² | 0 cm² |
| 16,895 | 352 ms | 16.170 cm | 6.6801 cm² | 6.4176 cm² |

960・390 CSS pxで6つの選択位置を検査した。フレーム0では欠測、12,500を選ぶと12,287の断面、最終フレームでは末尾の断面が表示された。表示した矩形座標と、累積セル長・円の相当直径から独立に計算した座標との差は最大 `2.27×10⁻¹³` SVG単位。固定上流の関連テストは11件通過し、既知の下唇の段差を扱う1件は上流の設定どおり除外された。[960 pxの閉鎖](../runs/worklet-tract-profile-20261119-a/artifacts/profile-960-closed.png)・[390 pxの開口](../runs/worklet-tract-profile-20261119-a/artifacts/profile-390-open.png)・[上流テスト](../runs/worklet-tract-profile-20261119-a/artifacts/upstream-tests.log)

研究ディレクトリと `/tmp` からの実行は、いずれも12判定が通過した。保存された断面のCSVとJSON、波形、画面の図形座標と画像、要約のSHA-256は両実行で一致した。[初回の記録](../runs/worklet-tract-profile-20261119-a/manifest.json)・[再実行の記録](../runs/worklet-tract-profile-20261119-b/manifest.json)

断面列は16 ms刻みの観測なので、閉鎖・開口の時刻を測る場合は引き続き16フレーム間隔の口唇系列を使う。ここで検証した図は声門から口端までで、鼻腔・側枝は図の対象外。圧力・流量を重ねるときは節点と枝の位置を区別し、符号付き瞬時値と窓内RMSの時刻定義を先に決める。
