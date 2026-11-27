# 声道断面に節点圧力と枝流量を対応させる

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `TubeView` はWorkletの `humanTelemetry` を介して、`HumanVoice::render` が4内部サンプルごとに蓄積した節点圧力二乗の窓内RMSで各セルを着色する。`HumanVoice::telemetry` は平方根を取った後、蓄積と件数をリセットする。今回観察するのは発話時刻の符号付き瞬時値。図の圧力点は各セル中心、流量点は口側の境界に置く。単位はそれぞれ dyn/cm²、cm³/s。[上流の図](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/TubeView.tsx)・[圧力の蓄積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L438)・[観測の取り出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L597)

`HumanVoice::render` は制御と声門面積を更新し、`AirwayNetwork::step` を間引き器への入力ごとに呼ぶ。気道の長さと断面積を補間した後、枝では時刻 `n` の圧力差から半ステップの流量を求める。枝の係数を固定した1回の更新は `(L/Δt + R)U + K|U|U = p_a − p_b + p_src + m_prev/Δt`。枝の始点から `U` を引き、終点へ足し、壁流量などを含む正味流入で節点の圧力 `p(n+1)` を更新する。開いた放射端は並列R–L負荷と節点を同時に解く。同じ出力フレーム末尾から読む圧力と流量には、この離散更新の半ステップ差がある。[レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L386)・[枝と節点の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L923)

符号の正は声門側から口端側。咽頭の末尾は口腔への接続枝、口腔の末尾は放射負荷から外気への流量 `rad_u` を読む。咽頭と口腔の内部枝の順序は `Tube::branch` と `add_tube`、接続の向きは `HumanAirway::new` と `LinearElements` の端点から追える。上流の `a_realistic_sliding_closure_with_trapped_pressure_releases_without_spikes` は開いたセルの圧力と閉鎖・再開口時の放射ピークを検査する。[接続順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L148)・[管内部の枝](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L440)・[閉鎖のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L165)

事前登録では `ɑpɑ` の48 kHz出力・内部96 kHzで、断面と同じ768出力フレーム間隔と末尾に全セルを採取する。唇端が閉じているフレーム11,519〜13,823では、直前の枝流量が0になる。唇端の観測圧力は最初の2時点間で `0.98^1536` 倍、放射流量は閉鎖中の各隣接時点間で `0.995^1536` 倍と予測する。閉鎖中の圧力比較は極小値の丸めを避けるため最初の1区間を使う。再開口後のフレーム14,591では口端放射流量の絶対値が100 cm³/s以上へ復帰すると予測する。全時点でCLI、固定上流および既存の声門直上圧力と口端放射流量に照合し、2画面幅で圧力と流量のプロット座標も検査する。[今回の条件](../cases/worklet-tract-acoustics.json)・[採取間隔と画面幅](../cases/worklet-tract-profile.json)・[先行の密な口唇観測](../runs/bilabial-p-20261119-e/summary.json)

## 実装と再現手順

`HumanAirway::tract_acoustics` は咽頭・口腔の各節点圧力と、声門から口端へ並べた枝の符号付き流量を返す。WASMの `vocal_tract_snapshot` は従来の断面データにこの系列を続けて書く。Workletは同じ出力フレームで事前に確保した領域へコピーする。観測JSONでは `tract.rows` の断面列に対応して、`tract.acoustics.rows` にフレーム番号とセルごとの圧力・流量を保存する。圧力と流量は発話全体のそれぞれの最大絶対値で軸を固定する。咽頭・口腔の境界を挟むセルや口端の値は「観測セル」の選択欄から読める。[コアの位置対応](../crates/vocal-core/src/airway/human.rs)・[WASMのスナップショット](../crates/vocal-wasm/src/lib.rs)・[図の実装](../../../../web/prototypes/chimera-research/src/tract-acoustics.tsx)

CLIケースに `speech_voice.tract_profile_frames` と `speech_voice.tract_profile_acoustics: true` を指定して `render` すると、従来の断面CSVに `pressure_dyn_cm2,outward_flow_cm3_s` が加わる。固定上流のプローブは `LinearElements` の節点対から咽頭・口腔の接続枝を特定し、内部枝には `Tube::branch`、口端には `rad_u[rad_lips]` を使う。[CLIの観測](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[上流の観測プローブ](../tools/upstream_bilabial_probe.rs)

```bash
python3 tools/measure_worklet_tract_profile.py worklet-tract-acoustics-local-1 --acoustics
```

## 結果

全65時点・各36セルの圧力と流量はブラウザとCLIで一致し、PCMもビット一致した。固定上流との差は最初の観測フレーム767の咽頭先頭セルですでに現れ、全観測における最大差は圧力 `1.54×10⁻¹⁰ dyn/cm²`、流量 `2.16×10⁻¹¹ cm³/s` と許容差内。声門直上の圧力と口端の放射流量は、従来の毎フレーム観測と一致した。固定上流の関連17テストが通過し、既知の下唇の段差を扱う1件は上流の設定で除外された。[測定値](../runs/worklet-tract-acoustics-20261119-a/summary.json)・[上流テスト](../runs/worklet-tract-acoustics-20261119-a/artifacts/upstream-tests.log)

256 msの閉鎖中、口端セルの圧力は `−2.66×10⁻¹⁹ dyn/cm²`、外気側への放射流量は `3.75×10⁻⁶ cm³/s`、2セル奥の圧力は `7,092.04 dyn/cm²` だった。口端の直前の枝流量は閉鎖中の全4観測点で0。口端圧力の減衰は最初の区間で、放射流量の減衰は3区間で独立式と相対誤差 `4.0×10⁻¹⁵` 以内で一致した。再開口後の出力フレーム14,591（304 ms）で口端放射流量は `1,060.97 cm³/s` だった。[初回の結果](../runs/worklet-tract-acoustics-20261119-a/summary.json)

960・390 CSS pxで圧力点をセル中心、流量点を口側境界に置けていることを確認した。両幅の最大座標差は `2.27×10⁻¹³` SVG単位。セル選択で咽頭末端、口腔先頭、口端の符号と単位を照合した。[390 pxの閉鎖](../runs/worklet-tract-acoustics-20261119-a/artifacts/profile-390-closed.png)・[960 pxの開口](../runs/worklet-tract-acoustics-20261119-a/artifacts/profile-960-open.png)

研究ディレクトリと `/tmp` からの実行で各20判定が通過し、PCM、観測JSON、図の座標、要約のSHA-256が一致した。閉鎖時のキャプチャ画像には960 pxで2画素、390 pxで3画素の色差があった。断面のみの既存比較とIPA時系列・英語発話の回帰比較も通過した。[初回](../runs/worklet-tract-acoustics-20261119-a/manifest.json)・[再実行](../runs/worklet-tract-acoustics-20261119-b/manifest.json)
