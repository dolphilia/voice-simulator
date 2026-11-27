# CHIMERA の研究用再実装

固定した CHIMERA の音響モデルを Rust で再実装し、上流の出力と独立計算に照合する研究ワークスペースです。一様管と可動気道、声門を含む母音の波形を生成し、圧力・流量・断面積をCSVに保存できます。IPA入力から計画した発話区間、母音の調音ジェスチャー、調音器の追従はJSONで観察できます。発話レンダーでは母音・両唇と歯茎の破裂音・歯茎と声門の摩擦音・両唇鼻音・両唇軟口蓋接近音・側音をつなぎ、閉鎖・開放・乱流・鼻腔への流れを波形と内部時系列で確認できます。[計画書](../../../docs/plans/chimera-research-rebuild-plan.md)・[進捗と次の検証](progress.md)・[発見と調査候補](findings.md)

## 実行

このディレクトリを作業場所とし、Rust/Cargo と Python 3.11 以降を使います。一様管の計測には `research/requirements.txt` の NumPy を、母音ベンチマークと発話区間の計測には NumPy と SciPy を使います。上流の取得方法は[調査ガイド](../../../docs/reference/chimera-vocal-synth/README.md)を参照してください。

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/uniform-tube-rigid.json
cargo test --locked --workspace
python3 tools/measure_sagittal.py sagittal-neutral-local-1 sagittal-neutral
python3 tools/measure_sagittal.py sagittal-open-jaw-local-1 sagittal-open-jaw
python3 tools/measure_grid.py grid-neutral-local-1 grid-neutral
python3 tools/measure_grid.py grid-shifted-local-1 grid-shifted-tongue
python3 tools/measure_grid.py grid-labiodental-local-1 grid-labiodental
python3 tools/measure_contact.py contact-raised-tip-local-1 contact-raised-tip
python3 tools/measure_contact.py contact-compressed-lips-local-1 contact-compressed-lips
python3 tools/measure_contact.py contact-tuck-handover-local-1 contact-tuck-handover
python3 tools/measure_area.py area-neutral-local-1 area-neutral
python3 tools/measure_area.py area-wide-lips-local-1 area-wide-lips
python3 tools/measure_area.py area-lateral-local-1 area-lateral
python3 tools/measure_resample.py resample-neutral-local-1 resample-neutral
python3 tools/measure_resample.py resample-compressed-lips-local-1 resample-compressed-lips
python3 tools/measure_fixed_airway.py fixed-airway-neutral-local-1 fixed-airway-neutral
python3 tools/measure_fixed_airway.py fixed-airway-short-local-1 fixed-airway-short
python3 tools/measure_vowel_transfer.py vowel-transfer-i-local-1 vowel-transfer-i
python3 tools/measure_vowel_transfer.py vowel-transfer-i-open-velum-local-1 vowel-transfer-i-open-velum
python3 tools/measure_vowel_voice.py vowel-voice-i-local-1 vowel-voice-i
python3 tools/measure_vowel_voice.py vowel-voice-u-local-1 vowel-voice-u
python3 tools/measure_vowel_benchmark.py vowels-reference-local-1
python3 tools/measure_ipa_tokenization.py ipa-tokenization-local-1
python3 tools/measure_speech_timing.py speech-timing-local-1
python3 tools/measure_vowel_gesture_score.py vowel-gesture-score-local-1
python3 tools/measure_bilabial_stop.py bilabial-p-local-1 p
python3 tools/measure_sibilant.py sibilant-s-local-1 s
python3 tools/measure_sibilant.py sibilant-s-muted-local-1 s-muted --enabled-run sibilant-s-local-1
python3 tools/measure_bilabial_nasal.py bilabial-nasal-m-local-1 m
python3 tools/measure_bilabial_nasal.py bilabial-nasal-vcv-local-1 vcv
python3 tools/measure_english_frontend.py english-frontend-local-1
python3 tools/measure_alveolar_stop.py alveolar-d-local-1 d
python3 tools/measure_glottal_frication.py glottal-h-local-1 h
python3 tools/measure_glottal_frication.py glottal-h-muted-local-1 h-muted --enabled-run glottal-h-local-1
python3 tools/measure_labial_velar.py approximant-w-local-1 w
python3 tools/measure_lateral.py lateral-l-local-1 l
python3 tools/measure_lateral.py lateral-l-closed-local-1 l-closed --enabled-run lateral-l-local-1
python3 tools/measure_lateral.py lateral-hello-local-1 hello
python3 tools/measure_song_plan.py song-plan-local-1
python3 tools/measure_song_voice.py song-voice-long-local-1 long
python3 tools/measure_song_voice.py song-voice-flat-local-1 flat
python3 tools/measure_song_voice.py song-voice-fast-local-1 fast
python3 tools/measure_song_voice.py song-voice-stop-local-1 stop
python3 tools/measure_beatbox_kick.py kick-b-local-1
python3 tools/measure_beatbox_hat.py hat-t-local-1
python3 tools/measure_beatbox_open_hat.py open-hat-single-local-1
python3 tools/measure_beatbox_snare.py snare-pf-local-1
python3 tools/measure_beatbox_rimshot.py rimshot-k-local-1
python3 tools/measure_beatbox_inward_snare.py inward-snare-local-1
python3 tools/measure_beatbox_tongue_click.py tongue-click-local-1
python3 tools/measure_beatbox_lip_pop.py lip-pop-local-1
python3 tools/measure_beatbox_crash.py crash-local-1
python3 tools/measure_beatbox_hum.py hum-local-1
python3 tools/measure_beatbox_pattern.py beat-pattern-local-1
python3 tools/measure_beatbox_pattern.py beat-pattern-mixed-local-1 --condition mixed
python3 tools/measure_beatbox_pattern.py snare-pattern-local-1 --condition snare
python3 tools/measure_beatbox_pattern.py rimshot-pattern-local-1 --condition rimshot
python3 tools/measure_beatbox_pattern.py inward-snare-pattern-local-1 --condition inward-snare
python3 tools/measure_beatbox_pattern.py tongue-click-pattern-local-1 --condition tongue-click
python3 tools/measure_beatbox_pattern.py lip-pop-pattern-local-1 --condition lip-pop
python3 tools/measure_beatbox_pattern.py crash-short-local-1 --condition crash-short
python3 tools/measure_beatbox_pattern.py crash-long-local-1 --condition crash-long
python3 tools/measure_beatbox_pattern.py hum-pattern-local-1 --condition hum
python3 tools/measure_beatbox_pattern.py transport-local-1 --condition transport
python3 tools/measure_beatbox_pattern.py open-hat-short-local-1 --condition open-short
python3 tools/measure_beatbox_pattern.py open-hat-long-local-1 --condition open-long
python3 tools/measure_articulation.py articulation-vowels-free-local-1 articulation-vowels-free
python3 tools/measure_articulation.py articulation-jaw-pace-local-1 articulation-jaw-pace
python3 tools/measure_tract_control.py tract-slew-lips-local-1 tract-slew-lips
python3 tools/measure_tract_control.py tract-slew-contact-local-1 tract-slew-contact
python3 tools/measure_tract_motion.py tract-motion-vowels-local-1 tract-motion-vowels
python3 tools/measure_voiced_vowel_motion.py vowel-motion-voice-vowels-local-1 vowel-motion-voice-vowels
python3 tools/upstream_baseline.py upstream-local-1
python3 tools/measure_uniform_tube.py uniform-tube-local-1 upstream-local-1
python3 tools/measure_uniform_tube.py soft-wall-local-1 upstream-local-1 --rigid-run uniform-tube-local-1
python3 tools/measure_junction.py symmetric-junction-local-1 symmetric-junction
python3 tools/measure_junction.py narrow-junction-local-1 narrow-junction
python3 tools/measure_moving_area.py sealed-cavity-local-1 sealed-cavity-compression
python3 tools/measure_moving_area.py moving-aperture-local-1 moving-aperture-release
python3 tools/measure_network_wall.py network-wall-local-1 --uniform-run soft-wall-local-1
python3 tools/measure_pressure_port.py steady-full-local-1 steady-constriction-full
python3 tools/measure_pressure_port.py steady-quarter-local-1 steady-constriction-quarter --full-run steady-full-local-1
python3 tools/measure_sliding_closure.py sliding-closure-local-1
python3 tools/measure_turbulence.py turbulence-forward-local-1 turbulence-forward
python3 tools/measure_turbulence.py turbulence-reverse-local-1 turbulence-reverse
python3 tools/measure_turbulence.py turbulence-alternate-seed-local-1 turbulence-alternate-seed
python3 tools/measure_nasal_network.py nasal-closed-local-1 nasal-network-closed
python3 tools/measure_nasal_network.py nasal-detached-local-1 nasal-network-open-detached
python3 tools/measure_nasal_network.py nasal-open-local-1 nasal-network-open --controls nasal-closed-local-1 nasal-detached-local-1
python3 tools/measure_glottal_coupling.py glottal-abduction-local-1 glottal-abduction
python3 tools/measure_glottal_coupling.py glottal-closure-local-1 glottal-oral-closure
python3 tools/measure_lung_breath.py lung-uncompensated-local-1 lung-uncompensated
python3 tools/measure_lung_breath.py lung-compensated-local-1 lung-compensated --uncompensated-run lung-uncompensated-local-1
python3 tools/measure_lung_breath.py lung-voiced-local-1 lung-voiced
python3 tools/measure_pcm_output.py pcm-impulse-local-1 pcm-impulse
python3 tools/measure_pcm_output.py pcm-voiced-local-1 pcm-voiced
python3 tools/measure_glottal_cycle.py cycle-jitter-local-1 glottal-cycle-jitter
python3 tools/measure_glottal_cycle.py cycle-shimmer-local-1 glottal-cycle-shimmer
python3 tools/measure_glottal_cycle.py cycle-voiced-local-1 glottal-cycle-voiced
python3 tools/measure_glottal_cycle.py diplophonia-control-local-1 glottal-diplophonia-control
python3 tools/measure_glottal_cycle.py diplophonia-fixed-local-1 glottal-diplophonia-fixed
python3 tools/measure_glottal_cycle.py diplophonia-voiced-local-1 glottal-diplophonia-voiced
python3 tools/measure_glottal_cycle.py chaos-fixed-point-local-1 glottal-chaos-fixed-point
python3 tools/measure_glottal_cycle.py chaos-period-2-local-1 glottal-chaos-period-2
python3 tools/measure_glottal_cycle.py chaos-period-4-local-1 glottal-chaos-period-4
python3 tools/measure_glottal_cycle.py chaos-aperiodic-local-1 glottal-chaos-aperiodic
python3 tools/measure_glottal_cycle.py chaos-voiced-local-1 glottal-chaos-voiced
python3 tools/measure_glottal_pitch.py pitch-drift-local-1 glottal-pitch-drift
python3 tools/measure_glottal_pitch.py pitch-vibrato-local-1 glottal-pitch-vibrato
python3 tools/measure_glottal_pitch.py pitch-voiced-local-1 glottal-pitch-voiced
python3 tools/measure_glottal_fry.py fry-control-local-1 glottal-fry-control
python3 tools/measure_glottal_fry.py fry-threshold-local-1 glottal-fry-threshold
python3 tools/measure_glottal_fry.py fry-overlap-local-1 glottal-fry-overlap
python3 tools/measure_glottal_fry.py fry-strong-local-1 glottal-fry-strong
python3 tools/measure_glottal_fry.py fry-low-f0-local-1 glottal-fry-low-f0
```

矢状面は `body` と `posture` のある姿勢ケースから計算します。`geometry` は部位名、0始まりの点番号、前方 `x_cm` と上方 `y_cm` を出力し、`inspect` は部位の点数と入力を表示します。この段階のケースは時刻に依存しない1フレームです。[矢状面の読解ノート](notes/sagittal-geometry.md)・[中立姿勢](cases/sagittal-neutral.json)

```bash
cargo run --locked --release -p vocal-cli -- geometry cases/sagittal-neutral.json contours.csv
```

体型は `"male"`、`"female"`、`"child"` または `{"female": 0.4, "child": 0.3}` のような二軸で指定できます。輪郭・接触・断面・再標本化を比較でき、混合重みと既定F0は `inspect` に出ます。名前で指定した `"male"` の補間情報を表示するには `measurement.body` を追加します。[体型補間の読解と計測](notes/human-body-geometry.md)

```bash
python3 tools/measure_body_geometry.py body-geometry-local-1
```

同じ姿勢ケースを `grid` に渡すと、測定線ごとの領域、内側の測定点、外壁との交点、中点、接触補正前の隙間 `ray_cm` を出力します。領域番号は咽頭1、口腔2、歯・唇3。上流の `GridSample::ray` と照合できます。[格子の読解ノート](notes/semipolar-grid.md)・[舌を前下方へ移したケース](cases/grid-shifted-tongue.json)

```bash
cargo run --locked --release -p vocal-cli -- grid cases/grid-neutral.json grid.csv
```

`contact` は同じ測定点に接触補正後の `gap_cm` を加えます。`measurement.contact` があるケースの `inspect` では、舌先と舌体の符号付き距離と声道へ向く単位法線も確認できます。[接触補正の読解ノート](notes/soft-tissue-contact.md)

```bash
cargo run --locked --release -p vocal-cli -- contact cases/contact-raised-tip.json contact.csv
```

`area` は補正後の隙間から求めた断面積 `area_cm2` と中心線に沿った距離 `s_cm` を出力します。`measurement.area` があるケースの `inspect` では声道全長、咽頭の長さ、切歯と唇の位置、唇の面積を確認できます。`posture.lateral` を指定すると、舌先近くの面積に舌側面の開口が加わります。[断面積と中心線の読解ノート](notes/area-profile.md)

```bash
cargo run --locked --release -p vocal-cli -- area cases/area-neutral.json area.csv
```

`resample` は格子上の断面を、`cells.pharynx` と `cells.oral` で指定した等長セルへ割り当てます。CSVには声門を原点とする左右の境界、8点の調和平均、格子点も含めた最小面積を出力します。セル番号は管ごとに0から始まります。閉鎖セルでは両面積が0になり、`inspect` では各管の解剖学的な長さとセル数を確認できます。姿勢の `epilarynx` と `ventricular` は声門上の狭め方を指定する0〜1の制御値です。[読解と測定結果](notes/resampled-tract.md)

```bash
cargo run --locked --release -p vocal-cli -- resample cases/resample-compressed-lips.json tract-cells.csv
```

`fixed_airway` のある姿勢ケースを `render` に渡すと、断面を気管・咽頭・口腔・鼻腔・側枝の気道グラフに接続し、咽頭入口に1サンプルの体積インパルスを入れます。体型と内部サンプルレートからセル数を決め、必要に応じて音響計算用の管長を伸ばします。`inspect` は解剖学的な管長、音響計算用の管長、各セルの断面、クーラン数を表示します。時系列CSVの圧力は dyn/cm²、流量は cm³/s、放射差分は cm³/s² です。[固定姿勢の読解と比較](notes/fixed-human-airway.md)・[体型と内部レートの比較](notes/human-body-airway.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/fixed-airway-short.json
cargo run --locked --release -p vocal-cli -- render cases/fixed-airway-short.json short-trace.csv
```

`transfer` は固定姿勢の気道を線形化し、咽頭入口の単位流量に対する口端・鼻端・壁面と合計の複素流量比を出力します。`transfer.start_hz`、`end_hz`、`points` で対数間隔の掃引を指定します。CSVには周波数、実部・虚部、合計の振幅、放射圧力に比例する相対レベルが入ります。`inspect` では枝と節点の線形要素も確認できます。計測スクリプトは固定上流・独立計算との照合と、ピーク周波数・−3 dB帯域幅の抽出を行います。[固定母音の読解と比較](notes/vowel-transfer.md)

固定気道では、既定の3体型や `{"female": 0.4, "child": 0.3}` の混合体型を `body` に指定できます。体型比較の実行は、固定姿勢のインパルス・線形応答と、作成した個別の入力ケースをまとめて保存します。[体型別の固定気道](notes/human-body-airway.md)

```bash
python3 tools/measure_body_airway.py body-airway-local-1
```

```bash
cargo run --locked --release -p vocal-cli -- transfer cases/vowel-transfer-i.json vowel-i-response.csv
```

`voice` を含む姿勢ケースでは、呼気・声門で固定気道を駆動します。`render` は肺圧、声門上下の圧力、声門面積・流量・位相、放射を、各PCMフレームが確定した内部サンプルに対応させて出力します。`render-pcm` はモノラルf32 WAVと間引き・出力段のCSVを保存します。計測スクリプトは定常窓のF0、LPCの周波数・帯域幅を抽出し、同じ姿勢の線形共鳴も記録します。[固定発声の読解と比較](notes/fixed-vowel-voice.md)

```bash
cargo run --locked --release -p vocal-cli -- render-pcm cases/vowel-voice-i.json vowel-i.wav vowel-i-output.csv 128
```

固定発声ケースの `fixed_voice_probe.radiation_components` を `true` にすると、`render` のCSVに壁の放射流量 `wall_radiation_flow_cm3_s` と、壁・口端・鼻端を足した `radiation_flow_cm3_s` が加わります。各流量の単位は cm³/s です。`internal_trace` を `true` にすると全内部標本を保存し、省略すると各PCMフレーム末尾の内部標本を保存します。`render-pcm` は同じ発声ケースからWAVと出力段のCSVを保存します。 [固定 /i/ の放射観測ケース](cases/fixed-vowel-i-cli-radiation.json)

```bash
cargo run --locked --release -p vocal-cli -- render cases/fixed-vowel-i-cli-radiation.json vowel-i-radiation.csv
```

同じケースをWasmホストまたはブラウザの `renderFixedVoice` に渡すと、放射流量4値と微分を出力フレームごとに採取できます。ブラウザの報告は `radiation.columns` に列名、`radiation.values` にフレーム順の値を持ちます。配列の最初の5値がフレーム0です。通常の固定 /i/ ではフレーム `k` が内部標本 `2k+1` に対応します。全内部標本を調べる場合はCLIの `internal_trace` を使います。 [WasmとWorkletの計測手順](notes/fixed-vowel-i-wasm-radiation.md)

固定母音画面で「放射流量を観測する」を選んでレンダーすると、PCM・放射成分・放射微分に共通のカーソルが表示されます。スライダーまたはグラフで時刻を選び、「表示範囲」で全区間と20 msを切り替えられます。WAV、全フレームの観測JSON、同じ設定でCLIから再実行できるケースを保存できます。 [画面の操作と検証](notes/fixed-vowel-i-radiation-screen.md)

固定発声ケースの `fixed_voice_probe.velum_port` を `true` にすると、`render` のCSVに口蓋帆ポートの面積・鼻腔へ向かう流量・咽頭側と鼻腔側の圧力を追加します。`internal_trace` と併用すれば、ポート流量が生じてから鼻端で観測されるまでの標本数を調べられます。 [口蓋帆の開閉比較](notes/fixed-vowel-i-velum-radiation.md)

固定発声CLIの `fixed_voice_probe.velum_area_override_cm2` に非負の面積を指定すると、`posture.velum_cm2` で計算した輪郭を使い、鼻腔への音響ポートだけを指定面積に設定します。 `inspect` の `fixed_airway.velum_port_cm2` で実効面積を確認できます。 [輪郭とポート面積の対照](notes/fixed-vowel-i-velum-port-only.md)

`fixed_voice_probe.internal_trace` を `true` にして `network_trace_range` に内部標本の半開区間 `[開始, 終了)` を指定すると、`render` は指定区間だけをCSVに保存し、全節点の圧力と全枝の流量を追加します。列名は `node_<節点番号>_pressure_dyn_cm2` と `branch_<枝番号>_flow_cm3_s` です。CSVの標本番号は発声開始から数えます。 `inspect` は観測範囲を表示します。 [固定 /i/ での計測手順](notes/fixed-vowel-i-velum-oral-nasal-loss.md)

固定発声の `body` には3体型と混合体型を指定できます。`voice.f0_hz` を省略すると体型の既定音高を使います。固定姿勢を揃えた体型別のPCM、声門面積と流量、肺圧の比較は次のコマンドで再実行できます。[条件と読解](notes/human-body-fixed-voice.md)

```bash
python3 tools/measure_body_fixed_voice.py body-fixed-voice-local-1
```

姿勢ケースの `posture` を `{"vowel": "a"}` とすると、`body` の較正済み部分目標を中立姿勢に適用します。`inspect` の `vowel_targets` で補間後の成分を確認でき、そのケースを `transfer` や `render-pcm` に渡せます。[体型別の較正目標](notes/human-body-calibrated-vowels.md)

```bash
python3 tools/measure_body_calibrated_vowels.py body-calibrated-vowels-local-1
```

基準10母音は `measure_vowel_benchmark.py` でまとめて測れます。固定姿勢の線形応答と発声の実行記録、隣接9遷移、上流CLIの母音列を採取します。一覧は親実行の `artifacts/vowels.csv`、個別実行の所在・帯域幅の欠測・原因調査は同じ実行の `summary.json` に記録します。個別に再実行する場合は、まず `measure_vowel_transfer.py` で線形応答を生成し、次に `measure_vowel_voice.py` に同じ姿勢の `--linear-run <実行ID>` を指定します。[基準10母音の条件と結果](notes/ten-vowel-benchmark.md)

`articulators` のあるケースでは、`render` が17成分の位置、速度、基準目標、有効目標、速度倍率を制御フレームごとにCSVへ出力します。各イベントは指定フレームの先頭で適用され、`targets` と `speeds` は指定した成分を更新します。`tip_free` は舌先の追従を切り替え、`blend` は合成済み目標を一括で置き換えます。`blend: {}` で合成目標を解除できます。`inspect` には初期姿勢の調音量、単位、可動域、固有周波数が入ります。[調音器の読解と測定](notes/articulator-dynamics.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/articulation-vowels-free.json articulation.csv
```

`articulators` と `area_control` を含むケースでは、`render` が咽頭と口腔の全セルについて、幾何上と変化率制限後の平均・最小断面、管長、接触距離、軟口蓋面積をCSVへ出力します。初期姿勢は `seed`、各フレームの計算は `apply`、舌と口蓋の接触で位置を補正した後は `reapply` として記録します。`area_control.project_contacts: false` で接触補正を無効にした対照を実行できます。観測時点は制御フレームで断面目標が決まった時点です。[断面制限の読解と計測](notes/tract-area-control.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/tract-slew-lips.json tract-targets.csv
```

`area_control.acoustics: true` を追加したケースでは、確定した平均・最小断面、セル長、軟口蓋ポートを内部サンプル単位で補間し、唇・鼻端の放射、圧力、枝と壁の流量をCSVへ出力します。声門を閉じて形状変化による体積速度だけで駆動します。比較スクリプトはケース指定の通過済み断面目標を読み、固定上流版と独立した補間・圧力収支に照合します。[音響への接続と計測](notes/moving-human-tract.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/tract-motion-vowels.json tract-samples.csv
```

可動声道のケースも、`body` に3つの既定体型や `{"female": 0.4, "child": 0.3}` を指定できます。接触補正と断面の変化速度は体型に応じて変わります。`voice` を付けると動く声道を呼気と声門で駆動し、`voice.f0_hz` を省略した場合は体型の既定値を使います。体型ごとの母音目標から比較用ケースを生成し、制御時点の目標と内部サンプルの断面・圧力・PCMを保存するコマンドです。[可動声道の体型比較](notes/human-body-tract-motion.md)

```bash
python3 tools/measure_body_tract_motion.py body-tract-motion-local-1
```

ケースに記録された断面目標の出力が手元にない場合は、対応する `tract-slew-*` を新しい実行IDで生成し、`--control-run` で指定できます。同じ姿勢・制御入力と、通過済みの実行を使います。

```bash
python3 tools/measure_tract_control.py tract-slew-vowels-local-1 tract-slew-vowels
python3 tools/measure_tract_motion.py tract-motion-vowels-local-2 tract-motion-vowels --control-run tract-slew-vowels-local-1
```

`articulators` と `voice` を含むケースを指定すると、同じ時間軸で調音と声門を進めます。`render` は全内部サンプルの調音位置、断面と長さ、呼気、声門、口端・鼻端の放射をCSVへ出力します。`render-pcm` は同じ入力からモノラルf32のWAVと出力段のCSVを作ります。[母音遷移の読解と比較](notes/voiced-vowel-motion.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/vowel-motion-voice-vowels.json vowel-motion-internal.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/vowel-motion-voice-vowels.json vowel-motion.wav vowel-motion-output.csv 128
```

IPAの字句解析は `ipa` に文字列を渡すか、`ipa.inputs` を持つケースを `render` へ渡して実行します。音素・修飾、スラッシュごとの発話、未知記号と適用外の記号をJSONで確認できます。`start_byte` と `end_byte` は入力全体のUTF-8バイト位置です。`end_byte` は範囲に含みません。[IPAの規則と比較](notes/ipa-tokenization.md)

```bash
cargo run --locked --release -p vocal-cli -- ipa 'ˈɑpɑ/ˈɑbɑ'
cargo run --locked --release -p vocal-cli -- render cases/ipa-tokenization.json ipa-results.json
```

`plan` はIPAから音素の長さと発話区間を秒単位で出力します。ケースの `speech_timing.inputs` にはIPA文字列 `text` または構造化音素列 `segments` を指定できます。`durations_seconds` は入力音素の長さ、`segments[].segment.dur` は二重母音などに配分した長さ、区間の `start_seconds` と `end_seconds` は話速を反映した時刻です。`input_index` をたどると元の音素とUTF-8位置を照合できます。長さ表・目録の既定値・展開先は固定上流版に由来します。[発話区間の読解と検証](notes/speech-timing.md)・[上流のMIT通知](LICENSE-CHIMERA)

```bash
cargo run --locked --release -p vocal-cli -- plan 'ɑpɑ / ɑbɑ' 1.25
cargo run --locked --release -p vocal-cli -- render cases/speech-timing.json speech-timing-results.json
```

`speech_timing.observe_score` を指定すると、成人男性の母音ジェスチャーと、指定した制御周期での目標の合成、調音器の位置・速度・有効目標が `score` に加わります。`activation` の順番は `score.gestures` と同じです。入力ごとの `additional_gestures` で、重みや速度の保持を単独で実験できます。[母音ジェスチャーの読解と検証](notes/vowel-gesture-score.md)・[上流のMIT通知](LICENSE-CHIMERA)

```bash
cargo run --locked --release -p vocal-cli -- render cases/vowel-gesture-score.json vowel-gesture-score-results.json
```

`speech_voice` のケースは、`inspect` で発話区間とジェスチャーを確認し、`render` で唇の開き・最小断面・圧力・声門と放射を出力フレームごとのCSVに保存します。`render-pcm` は同じスコアを通ってWAVと出力段のCSVを作ります。計測スクリプトの条件は `p`、`b`、`p-unaspirated`、`p-fast` です。[両唇破裂音の読解と検証](notes/bilabial-stop.md)

IPAと英語テキストの発話では `speech_voice.body` に `"male"`、`"female"`、`"child"`、または `{"female": 0.4, "child": 0.3}` のような比率を指定できます。選んだ体型を母音・/s z/ の較正目標と可動声道、声門、乱流源に使います。`voice.f0_hz` を省略すると発話の種類に応じた既定音高が使われます。[体型を選んだIPA発話の比較](notes/human-body-ipa.md)

```bash
python3 tools/measure_body_ipa.py body-ipa-local-1
```

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/bilabial-p.json
cargo run --locked --release -p vocal-cli -- render cases/bilabial-p.json bilabial-p-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/bilabial-p.json bilabial-p.wav bilabial-p-output.csv 128
```

/d t/ を含む発話のCSVでは、舌先の座標、口腔セルごとの最小断面、最も狭いセルを確認できます。計測スクリプトは `d`、`t`、`t-fast`、`t-placed`、`d-english` に対応します。[歯茎破裂音の読解と照合](notes/alveolar-stop.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/alveolar-d.json alveolar-d-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/alveolar-d-english.json dad.wav dad-pcm.csv 128
```

/k g/ を含む発話・歌唱では、舌背の座標に加え、咽頭・口腔の最小断面積をCSVで確認できます。韓国語の `먹어` と `먹 어` は同じ二音で歌唱し、閉鎖音が頭子音または末子音として割り当てられる違いを検証できます。[舌背閉鎖の読解と照合](notes/velar-stops.md)

```bash
python3 tools/measure_velar_stops.py velar-stops-local-1
```

/s z/ を含む発話では、調音から乱流源を自動で設定します。`speech_voice.turbulence.scale` は乱流の倍率です。/s z/ を含む場合の既定値は1で、0を指定すると源の配置・帯域を観測しながら圧力注入を止められます。乱流を設定したケースのCSVに、断面の最小値、歯までの距離、励起枝・注入先・帯域と圧力を追加します。[歯茎摩擦音の読解と照合](notes/sibilant-frication.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/sibilant-s.json sibilant-s-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/sibilant-z.json sibilant-z.wav sibilant-z-output.csv 128
```

/h ɦ/ を含む発話も、既定でシード付き乱流の倍率1を使います。CSVには声門開大、有声化係数、声門枝の面積、咽頭側・気管側への圧力注入が出ます。`h-muted` は乱流倍率0で同じ調音を走らせ、`--enabled-run` に比較する倍率1の実行IDを取ります。`h-48k` は前サンプルの枝状態から振幅を照合し、`h-english` は辞書経由の `Hi.` を出力します。[声門摩擦音の読解と照合](notes/glottal-frication.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/glottal-h.json glottal-h-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/glottal-h-english.json hi.wav hi-pcm.csv 128
```

/w/ を含む発話のCSVでは、唇の開き・突き出し・幅、舌体座標、口腔セルごとの最小断面を追えます。計測器は `w`、`w-fast`、`w-english`、`w-final` の4条件で、内側の観測に加え、PCMの短い窓で推定したF1またはF2を出します。[両唇軟口蓋接近音の読解と照合](notes/labial-velar-approximant.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/approximant-w.json approximant-w-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/approximant-w-english.json we.wav we-pcm.csv 128
```

/j ɰ/ を含む発話・歌唱では顎、舌背、咽頭と口腔の最小断面をCSVで比較できます。ブラウザの歌唱でも、これらの渡り音を含む計画では舌背位置を保存します。比較用スクリプトは `ɑjɑ` と `ɑɰɑ`、`빵야 ~` と `의사` を生成し、渡り音から母音への移行を測ります。[舌背の渡り音の読解と計測](notes/tongue-glides.md)

```bash
python3 tools/measure_tongue_glides.py tongue-glides-local-1
```

/ɕ ʑ/ を含む発話では、舌先・舌体・顎・唇の制御値、口腔セルの最小断面、歯に注入する乱流圧力、声門開大をCSVで追えます。比較用スクリプトは IPA の母音間の /ɕ ʑ/ と韓国語歌唱の「시야」を生成し、固定上流と実ブラウザの出力を照合します。[歯茎硬口蓋摩擦音の読解と計測](notes/alveolopalatal-fricatives.md)

```bash
python3 tools/measure_alveolopalatal_fricatives.py alveolopalatal-fricatives-local-1
```

唇歯摩擦音 /f v/ のCSVでは、唇歯寄せと下唇端の矢状面座標、口腔セルの最小断面、狭窄音源と歯での衝突音源、声門の状態を観測できます。比較用スクリプトは /ɑfɑ ɑvɑ/ とロシア語の「ве́тер」を合成します。[唇歯摩擦音の読解と計測](notes/labiodental-fricatives.md)

```bash
python3 tools/measure_labiodental_fricatives.py labiodental-fricatives-local-1
```

軟口蓋摩擦音 /x/ は IPA 発話とロシア語歌唱で使えます。比較用スクリプトは /ɑxɑ ixi ɑxʲɑ/ と「ти́хо」を合成し、体型別の舌背、咽頭・口腔の断面、乱流音源の登録と活動を固定上流に照合します。第2版が既定で、初回の条件は `--revision 1` で再実行できます。ブラウザを省く場合は `--native-only` を付けます。[軟口蓋摩擦音の読解と計測](notes/velar-fricative.md)

```bash
python3 tools/measure_velar_fricative.py velar-fricative-local-1
```

/tɕ dʑ/ を含む発話は、口腔セルの最小断面と各セル間の流量をCSVに出します。比較用スクリプトは IPA の母音間の破擦音と韓国語歌唱の「아주 자 차 짜」を使い、閉鎖、歯の乱流、周期的な声門開閉が戻る時刻を照合します。[破擦音の読解と計測](notes/alveolopalatal-affricates.md)

```bash
python3 tools/measure_alveolopalatal_affricates.py alveolopalatal-affricates-local-1
```

後部歯茎破擦音 /tʃ/ はIPA発話と歌唱で使えます。比較用スクリプトは母音間の閉鎖と解放を測り、ロシア語デモ「Ночной ветер」の16音節を実時間のAudioWorkletとCLIで照合します。成人の通常発話はPCMの10 ms窓でも摩擦と母音復帰を計測します。CLIと固定上流だけを検証する場合は `--native-only` を付けます。[後部歯茎破擦音の読解と計測](notes/postalveolar-affricate.md)

```bash
python3 tools/measure_postalveolar_affricate.py postalveolar-affricate-local-1
```

歯茎破擦音 /ts/ はIPA発話と中国語歌唱で使えます。 `render` のCSVで舌先・舌体、口腔セルの最小断面と枝流量、歯への乱流、声門開大を確認できます。比較用スクリプトは「资」「词」を同じMIDI番号で一音ずつ歌い、声門開大の計画と周期発声の再開を比較します。二音を続けた譜例は実ブラウザで歌い、保存ケースをCLIで再演します。 `--native-only` を付けるとCLIと固定上流の比較を実行できます。[読解と計測](notes/alveolar-affricate.md)・[登録ケース](cases/alveolar-affricate.json)

```bash
python3 tools/measure_alveolar_affricate.py alveolar-affricate-local-1
```

そり舌摩擦音 /ʂ/ はIPA発話と中国語歌唱で使えます。 `render` の `tongue_tip_curl` は舌先の反りを表す無次元の状態です。同じ母音に挟まれた /s/ と /ʂ/ を比べ、乱流を切った対照で形状と圧力注入を確認できます。「四 是」の歌唱では、拍の前後の舌先と母音の周期性を測り、実ブラウザの保存ケースをCLIで再演します。[読解と計測](notes/retroflex-fricative.md)・[登録ケース](cases/retroflex-fricative.json)

```bash
python3 tools/measure_retroflex_fricative.py retroflex-fricative-local-1
```

そり舌破擦音 /tʂ/ はIPA発話と中国語歌唱で使えます。 `render` のCSVで舌先の反り、閉鎖セルに隣接する枝流量、解放後の狭窄・歯の乱流、周期的な声門開閉を観測できます。自然な歌詞の「知」「吃」と声母を112 msにそろえた対照で、有気・無気の開大と周期復帰を比較します。二音の譜例はブラウザの保存ケースもCLIで再演します。[読解と計測](notes/retroflex-affricate.md)・[登録ケース](cases/retroflex-affricate.json)

```bash
python3 tools/measure_alveolar_affricate.py retroflex-affricate-local-1 --retroflex
```

そり舌接近音 /ɻ/ はIPA発話、中国語の頭子音と児化韻尾に使えます。CSVで舌先の反り `tongue_tip_curl`、口腔・咽頭の最小断面、声門の周期を観測できます。「日 哪儿」「哪儿 妈」とメリスマを使い、音節と音符の境界、韻尾への発声のつながりを検査します。ブラウザから保存した譜例はCLIで再演できます。[読解と計測](notes/retroflex-approximant.md)・[登録ケース](cases/retroflex-approximant.json)

```bash
python3 tools/measure_retroflex_approximant.py retroflex-approximant-local-1
```

声門閉鎖音 /ʔ/ はIPA発話と中国語歌唱で使えます。CSVで閉鎖指示と周期位相、声門断面と流量、口腔断面を同時に調べられます。比較スクリプトは発話4条件と歌唱3譜例を測り、「人爱」「四是吃字人爱」のブラウザ出力と保存ケースをCLIで照合します。[読解と計測](notes/glottal-stop.md)・[登録ケース](cases/glottal-stop.json)

```bash
python3 tools/measure_glottal_stop.py glottal-stop-local-1
```

/ɾ/ を含む発話では、舌先と舌体の座標、口腔セルの最小断面と枝流量をCSVで調べられます。比較用スクリプトは同じ母音に挟んだ /ɾ t d/ と「싫어」を合成し、狭窄をまたぐ声門振動と出力を照合します。[歯茎弾き音の読解と計測](notes/alveolar-tap.md)

```bash
python3 tools/measure_alveolar_tap.py alveolar-tap-local-1
```

/l ɫ/ を含む発話では、側方開きの位置・合成目標と口腔セルの断面積を記録します。`speech_voice.lateral_opening_scale` は0〜1で側方開きの初期値と目標に掛ける倍率です。0にすると、舌先や舌体の目標をそろえて側方開きの効果を調べられます。[側音と英語文の読解・検証](notes/lateral-approximants.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/lateral-l.json lateral-l-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/lateral-hello.json hello-world.wav hello-world-pcm.csv 128
```

/m n ŋ/ を含む発話・歌唱のCSVには、軟口蓋の位置・有効目標・実際のポート面積・流量と、口腔セルの最小の平均断面積が加わります。/n/ は舌先、/ŋ/ は舌背で閉じ、鼻端と口端の流量を比較できます。鼻音を含むブラウザ歌唱は、鼻端流量と鼻腔ポート面積も観測JSONに保存します。[両唇鼻音の読解と照合](notes/bilabial-nasal.md)・[舌先・舌背の鼻音と韓国語歌唱](notes/lingual-nasals.md)

```bash
cargo run --locked --release -p vocal-cli -- render cases/bilabial-nasal-m.json nasal-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/bilabial-nasal-vcv.json vcv.wav vcv-pcm.csv 128
python3 tools/measure_lingual_nasals.py lingual-nasals-local-1
```

英語は `english` で直接入力するか、`english_text` のケースを `render` へ渡します。各語の出典、強勢と語境界付きの音素、句の休止、F0目標、現在の発声で追加が必要な音素がJSONに出ます。`speech_voice.language` を `english` にすると、対応済みの音素からなる文をWAVにできます。[発音変換の読解と検証](notes/english-frontend.md)・[辞書のライセンス](data/CMUDICT-LICENSE.txt)

英語テキスト発話の既定F0は成人男性112 Hz、成人女性205 Hz、子ども250 Hzで、混合では対数補間します。`voice.f0_hz` の指定があれば優先します。[体型別の英語テキスト発話](notes/human-body-english.md)

```bash
python3 tools/measure_body_english.py body-english-local-1
```

```bash
cargo run --locked --release -p vocal-cli -- english 'Is it on? Yes, it is.'
cargo run --locked --release -p vocal-cli -- render cases/english-frontend.json english-results.json
cargo run --locked --release -p vocal-cli -- render-pcm cases/english-mom-pop.json mom-pop.wav mom-pop-pcm.csv 128
```

`speech_voice.source_variation` で、`pitch_drift_cents`（セント）、`period_jitter`（周期長の変動係数）、`amplitude_shimmer`（声門面積パルスの振幅変動係数）を個別に指定できます。各値は0以上の有限値です。各項目を省略すると、その変動は0です。固定上流の通常発話を照合した条件には、順に5、0.00455、0.042を指定しました。[確認用07の実測](notes/tsp-active-duration-original.md#確認用07で上流既定の音源変動を適用)

英語発話画面の「英語発話ケースをレンダー」では、`speech_voice.language` が `english` のCLIケースを選ぶとオフラインで描画します。続けて「読み込んだケースを実時間で発声」から同じケースを再生できます。調音の初期姿勢、体型、ゲイン、揺らぎの指定は「再実行ケースを保存」からCLIに戻せます。[確認用07のブラウザとCLIの照合](notes/worklet-english-voice.md#確認用07の発話ケースの読み込みと再演)・[実時間の開始と停止](notes/worklet-english-voice.md#確認用07の実時間発声と開始時刻)

`song_plan.scores` に英語・韓国語・ロシア語・中国語の `lyrics` または `syllables`、`notes` のMIDI番号と拍長、テンポ `bpm`、最初の拍 `start_seconds` を指定します。`inspect` と `render` で、音節の頭・核・末子音、音符の拍、実際の母音開始位置、音素区間、F0目標をJSONで確認できます。歌詞の音節は、音符の数に合わせて先頭から繰り返します。[歌唱の時間計画](notes/song-timing.md)・[譜例](cases/song-plan.json)

韓国語は完成形のハングルと分解した現代字母を受け取り、一つのハングルを一音節にします。音節の綴りを保持し、同じ語の中で連音化、鼻音化、帯気化などを反映します。音響比較は現在の調音器で対応する音素を使った `불 풀 뿔.` で実行できます。[韓国語歌詞の読解と検証](notes/korean-lyrics.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/song-plan.json
cargo run --locked --release -p vocal-cli -- render cases/song-plan.json song-plan-results.json
python3 tools/measure_korean_lyrics.py korean-lyrics-local-1
```

ロシア語の歌詞からは、結合アキュートで指定した強勢、軟音の /j/、子音群、語末・句末を音節JSONで確認できます。歌唱計画の `unavailable_speech_symbols` に音響合成の未対応音素が出ます。比較用スクリプトは「мо-ло-ко́ ~ рыба」と「лук люк」をCLIとブラウザで実行します。[ロシア語歌詞の読解と検証](notes/russian-lyrics.md)

```bash
python3 tools/measure_russian_lyrics.py russian-lyrics-local-1
```

中国語は固定の漢字読み辞書と、声調記号または数字を含むピンインを使えます。音節JSONで帯気、児化、韻尾の長さと境界を確認でき、`song_plan.mandarin_words` に漢字列を指定すると変調後の読み番号を観測できます。「你好」などの歌唱をCLIと実時間ブラウザで照合します。初回の条件は `--revision 1` で再実行できます。[中国語歌詞の読解と検証](notes/mandarin-lyrics.md)・[辞書のライセンス通知](data/MANDARIN-PINYIN-LICENSE.txt)

```bash
python3 tools/measure_mandarin_lyrics.py mandarin-lyrics-local-1
```

中国語の鼻音韻尾 /n/・/ŋ/ では、母音中からの鼻への流量、舌体の移動と句末閉鎖を観測できます。`song_voice` の `tract_profile_frames` に出力フレーム番号を渡し、`tract_profile_acoustics` を有効にすると、`render` は断面ごとの圧力と枝流量を保存します。「班」「帮」「东」の実測、メリスマ、次句がある場合、16 kHzの対照を再実行できます。[鼻音韻尾の読解と実測](notes/mandarin-nasal-rhymes.md)

```bash
python3 tools/measure_mandarin_nasal_rhymes.py mandarin-nasal-rhymes-local-1
```

歌唱を発声まで進めるには `song_voice.score` に1譜例を指定し、初期姿勢、サンプルレート、肺圧などを加えます。基準F0は初音のMIDI番号から決まり、`vibrato_cents` の既定値は35です。`inspect` で予定時刻とジェスチャー、`render` で唇の最小断面積・呼気・開大・声門流量・ビブラート前後のF0、`render-pcm` でWAVとPCMのCSVを保存します。計測スクリプトは波形からF0を求め、閉鎖・開口と発声開始の実測時刻をJSONに残します。[二音のケース](cases/song-voice-long.json)・[歌唱音声の読解と検証](notes/sung-voice.md)

録音と時刻を揃える場合は、`song_voice.scores` に `score` と同じ形式の譜例を開始時刻順に指定します。各 `start_seconds` はWAV先頭からの絶対時刻で、各句を計画してから一つの発声器で描画します。`render_end_seconds` を指定すると、録音などの基準とWAVの長さを揃えられます。[CSDの2句を描画する実例](notes/csd-continuous-song.md)

全曲の音響比較など、共有PCM出力でWAVだけを取得する場合は、`render-pcm <ケース.json> <出力.wav> --no-trace` を使えます。[全曲のF0と保存量の比較](notes/csd-acoustic-f0-en001a.md)

`song_voice.body` には3つの既定体型、または `{"female": 0.4, "child": 0.3}` のような比率を指定できます。MIDI音符と拍の指定に従い、選んだ体型の調音目標・声道・声門で発声します。[体型別の歌唱計画と計測](notes/human-body-song.md)

```bash
python3 tools/measure_body_song.py body-song-local-1
```

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/song-voice-long.json
cargo run --locked --release -p vocal-cli -- render cases/song-voice-long.json song-trace.csv
cargo run --locked --release -p vocal-cli -- render-pcm cases/song-voice-long.json song.wav song-pcm.csv 128
```

固定母音のWASMは `vocal-wasm` のC ABIから実行できます。`wasm32-unknown-unknown` ターゲットとNode 24を用意すると、同じ `vowel-voice-i.json` をネイティブCLIとWASMで実行し、PCMとフレームに対応した声門・放射の差を計測できます。[ABIの読解と結果](notes/wasm-fixed-voice.md)・[登録した比較条件](cases/wasm-fixed-voice.json)

```bash
cargo build --locked --release -p vocal-wasm --target wasm32-unknown-unknown
python3 tools/measure_wasm_fixed.py wasm-fixed-voice-local-1
```

ブラウザでの固定母音は [Webワークスペース](../../../web/prototypes/chimera-research/README.md) から試せます。AudioWorklet出力を試聴し、Web Audioでの加工前PCMとフレーム番号付きの観測を保存できます。起動手順とChromiumの準備はWeb側のREADMEを参照してください。[ブラウザとCLIの照合結果](notes/worklet-fixed-voice.md)

```bash
python3 tools/measure_worklet_fixed.py worklet-fixed-voice-local-1
python3 tools/measure_worklet_realtime.py worklet-realtime-voice-local-1
```

実時間の固定発声は停止操作後の減衰まで記録します。比較器は実際に適用されたゲート変更を、出力フレーム番号の `gate_events` として固定発声ケースへ書き出します。これをCLIの `render` や `render-pcm` に渡すと、観測した音声の操作時刻を再現できます。[実時間の比較](notes/worklet-realtime-voice.md)

44.1 kHzの固定発声は、同じ姿勢を内部88.2 kHzで動かします。ネイティブ比較では間引き係数、制御周期と描画中の割り当てを検査し、ブラウザ比較では画面でレートを選び、発声から減衰までのWAVと観測を取得します。[44.1 kHzのケース](cases/worklet-realtime-voice-44100.json)・[読解と結果](notes/worklet-realtime-voice-44100.md)

```bash
python3 tools/measure_worklet_realtime.py worklet-rate-44100-native-local-1 --rate-44100 --native-only
python3 tools/measure_worklet_realtime.py worklet-rate-44100-browser-local-1 --rate-44100
```

32 kHzでは内部64 kHzに設定し、咽頭と口腔のセル数、管ごとのセル長とクーラン数も固定上流と照合します。[32 kHzのケース](cases/worklet-realtime-voice-32000.json)・[検証結果](notes/worklet-realtime-voice-32000.md)

```bash
python3 tools/measure_worklet_realtime.py worklet-rate-32000-native-local-1 --output-rate 32000 --native-only
python3 tools/measure_worklet_realtime.py worklet-rate-32000-browser-local-1 --output-rate 32000
```

16 kHzでは内部64 kHzを保って4倍に間引きます。ネイティブ検証は固定した32 kHz実行の出力を読み、気道と、共通の内部時刻で観測した呼気ゲートを比較します。[16 kHzのケース](cases/worklet-realtime-voice-16000.json)・[32 kHzの参照実行](runs/worklet-rate-32000-20261120-native-repeat/manifest.json)・[読解と比較](notes/worklet-realtime-voice-16000.md)

```bash
python3 tools/measure_worklet_realtime.py worklet-rate-16000-native-local-1 --output-rate 16000 --native-only
python3 tools/measure_worklet_realtime.py worklet-rate-16000-browser-local-1 --output-rate 16000
```

96 kHzでは出力と内部を同じレートにし、1タップの出力段と、放射からPCMまでのフレーム対応を照合します。ネイティブ比較はDC除去、リミッターとPCMを独立に再計算します。[96 kHzのケース](cases/worklet-realtime-voice-96000.json)・[読解と比較](notes/worklet-realtime-voice-96000.md)

```bash
python3 tools/measure_worklet_realtime.py worklet-rate-96000-native-local-1 --output-rate 96000 --native-only
python3 tools/measure_worklet_realtime.py worklet-rate-96000-browser-local-1 --output-rate 96000
```

Webの「舌と唇の操作」では、発声中に舌体X・Yと口唇開度の目標をcm単位で動かせます。観測JSONの `articulation` に、Workletが目標を採用した出力フレームと3つの目標値を保存します。「再実行ケースを保存」は同じ操作をCLIで受理できるケースJSONに書き出します。可動声道CLIでは `articulators.events[].gate` に0〜1.5の呼気目標を指定でき、同じイベントで `targets` も更新できます。この `frame` は制御フレーム番号です。[手動操作の読解と検証](notes/worklet-manual-articulation.md)・[ケースの書き出しと再合成](notes/worklet-manual-case-export.md)

手動発声中に体型を選ぶと、調音と呼気の目標を引き継いで声道を作り直します。観測JSONの `bodyChanges` に適用した出力フレームと咽頭・口腔のセル数を記録し、保存ケースの `articulators.events[].body` で同じ切り替えを再生できます。[体型切り替えの読解と検証](notes/worklet-manual-body-switch.md)

```bash
python3 tools/measure_worklet_manual_articulation.py worklet-manual-articulation-local-1
python3 tools/measure_worklet_manual_articulation.py worklet-manual-case-export-local-1 --case-export
python3 tools/measure_worklet_manual_body_switch.py worklet-manual-body-switch-local-1
```

Webの「MIDI鍵盤の発声」では接続した入力から音高と呼気を制御し、量子境界に採用した音を観測JSONの `midiNotes` に保存します。書き出す再実行ケースは `articulators.events[].f0_hz` と `gate` を使います。[MIDIの入力と再生](notes/worklet-midi-voice.md)・[持ち替え時の音高と固定上流の照合](notes/worklet-midi-voice-pitch.md)・[操作と表示の対応表](notes/interaction-presentation.md)

同じ画面で「MIDIで歌唱する」を有効にすると、押下で歌詞の音節が進み、`-` は直前の母音を継続します。発声中のキーを離すと、残っているキーの音高に戻ります。観測JSONの `songKeys` と書き出した `live_song_voice` ケースに、Workletが採用したフレームと各キーのイベントを保存します。末子音のある音節では、最後の離鍵で語尾の調音を開始します。次が母音継続なら、語尾は継続の終わりまで待ちます。保存ケースの `live_song_voice.observe_gestures` を有効にして `inspect` すると、各採用時刻のスコアをタグ付きで確認できます。[鍵盤歌唱の読解と比較](notes/worklet-midi-song.md)・[語末/p/の観測](notes/worklet-midi-song-coda.md)

「ビートボックス」でMIDIを接続し、実時間再生中にキーを押すと、唇を閉じて鼻に抜ける低音を出します。重ねたキーを離すと保持中のキーの音高へ戻ります。「ハムを切り替える」で指定したステップには最後に押したキーの音番号が入ります。観測JSONの `beatEvents` と再実行ケースの `beatbox_pattern.events` に採用フレームを保存します。[ビートボックスのMIDIとハムを再実行する手順](notes/worklet-midi-beatbox.md)

```bash
python3 tools/measure_worklet_midi.py worklet-midi-local-1
```

Webの「IPA発話」では、CLIと同じRustの区間計画と調音計画を使い、口唇・声門の時系列をWAVとともに保存できます。検証はブラウザの入力欄に `ɑpɑ` を入れて行います。[IPA発話の読解と検証](notes/worklet-ipa-voice.md)

成人男性・成人女性・子ども・混合の体型を選べます。基準F0を空欄にするとIPA用の体型別既定値を使います。オフラインと実時間の両方でCLI用ケースを保存できます。摩擦音を含む発話の観測JSONには、歯への乱流源の枝、最小断面積、乱流の励起レベルと注入圧力も含まれます。[体型を選んだブラウザIPAの検証](notes/worklet-ipa-body.md)

```bash
python3 tools/measure_worklet_ipa.py worklet-ipa-voice-local-1
python3 tools/measure_worklet_ipa_body.py worklet-ipa-body-local-1
```

IPA発話の時系列は、予定した音素区間と実測の口唇断面積、PCMの最小値・最大値を共通の出力時刻に表示します。選択したフレームと、状態を採取したフレームを画面で確認できます。`--timeline` で2種類の画面幅における図形とカーソルを、保存されたWAV・観測JSONと固定上流の計画から独立に照合します。[登録条件と結果](notes/worklet-ipa-timeline.md)

```bash
python3 tools/measure_worklet_ipa.py worklet-ipa-timeline-local-1 --timeline
```

IPA・英語発話の声道断面には、選択時刻までに採取した最後の咽頭・口腔セルの長さ、平均面積、最小面積を表示します。保存する観測JSONの `tract` から同じ図を再構成できます。CLIでは `speech_voice.tract_profile_frames` を指定して `render` すると、対応する断面のCSVを保存します。[声道断面の読解と比較](notes/worklet-tract-profile.md)

```bash
python3 tools/measure_worklet_tract_profile.py worklet-tract-profile-local-1
```

「声道の三次元断面」は固定姿勢の測定線を位置・有効隙間・計算面積を保って楕円として描きます。観測JSONの測定列と描画頂点はCLIの `area` と固定上流の格子に照合できます。[三次元表示の読解と実測](notes/worklet-tract-3d.md)

```bash
python3 tools/measure_worklet_tract_3d.py worklet-tract-3d-local-1
```

IPA発話で「三次元断面を観測する」を選ぶと、時系列で選択した時刻までに採取した最後の測定線を描きます。音響セルと採取フレームを共有し、発話全体の測定線は観測JSONの `tract.grid` に入ります。「発話の三次元観測JSONを保存」では、選択時刻と描画頂点も保存できます。CLIの発話ケースで `tract_profile_frames` を指定し `tract_profile_grid` を有効にすると、`render` からフレーム番号・測定線番号・11列の測定値をCSVに出力します。[発話時刻の三次元断面と比較手順](notes/worklet-tract-3d-dynamic.md)

```bash
python3 tools/measure_worklet_tract_profile.py worklet-tract-3d-dynamic-local-1 --dynamic-3d
```

同じ設定で「IPAを実時間で発声」を選ぶと、発声中の測定線が音響セルと同じ出力フレームで更新されます。完了後は表示できなかった採取点も含めて時系列を見直せます。観測JSONの `tractLive` には発声中の送信数と省略数が入ります。[実時間の採取と検証](notes/worklet-tract-3d-live.md)

```bash
python3 tools/measure_worklet_tract_profile.py worklet-tract-3d-live-local-1 --live-3d
```

実時間IPAの子ども・混合体型で、異なる音響セル数から同じ49本の測定線を読み、切り替え後の最初の描画と閉鎖・再開口を検証できます。CLIの `speech_voice.tract_profile_posture` を使うと、`tract_profile_frames` の17軸を測定線と同じ出力フレームでCSVに出力でき、固定上流と同じ姿勢での比較に使えます。音響セルや格子を出すフラグとは個別に指定します。[体型の比較と再実行手順](notes/worklet-tract-3d-body.md)

声道断面と同じ時刻の節点圧力と口側境界の流量は、観測JSONの `tract.acoustics` に入ります。CLIの断面CSVにも `speech_voice.tract_profile_acoustics: true` で追加できます。[観測点・単位と閉鎖の検証](notes/worklet-tract-acoustics.md)

```bash
python3 tools/measure_worklet_tract_profile.py worklet-tract-acoustics-local-1 --acoustics
```

発話時系列の「声門波形」は、選択フレームの前後12 msの声門面積と符号付き流量を表示します。観測JSONの `glottal.values` には出力フレーム0からの面積と流量が交互に入り、CLIの発話ケースの `render` でも声門の毎フレーム観測を取得できます。[声門波形の読解と比較](notes/worklet-glottal-scope.md)

```bash
python3 tools/measure_worklet_ipa.py worklet-glottal-scope-local-1 --scope
```

発話の「PCMスペクトル」は保存WAVと同じPCMから、選択フレームを中心に2,048点のBlackman窓で計算します。画面はdBFS、選択点ごとに保存するJSONは全1,025ビンの線形振幅と窓の範囲を含みます。[PCMスペクトルの読解と検証](notes/worklet-pcm-spectrum.md)

```bash
python3 tools/measure_worklet_ipa.py worklet-pcm-spectrum-local-1 --spectrum
```

IPAの「IPAを実時間で発声」は、AudioContextの描画量子に発話の起点を予約して再生します。WAVは発話の起点からの合成PCM、観測JSONの `realtime` はContext上の開始時刻、量子ごとの処理時間、WASMメモリ増加を含みます。[実時間IPAの読解と計測](notes/worklet-live-ipa.md)

```bash
python3 tools/measure_worklet_ipa.py worklet-live-ipa-local-1 --live
```

扇状走査線の固定長配列は、当時の候補で実時間IPAの割り当てを約49%削減しました。その実行と登録した60%に対する判定は、実行ごとの入力スナップショットから確認できます。[走査線の比較](notes/fan-crossing-allocations.md)

現在の輪郭領域の再利用は、次のコマンドで比較できます。登録した発話の区間別計数、実時間AudioWorkletのPCMと観測、矢状面・母音・口唇・舌接触のCLIを、固定した実行結果と照合します。[輪郭領域の比較](notes/contour-buffer-reuse.md)

```bash
python3 tools/measure_contour_buffers.py contour-buffer-reuse-local-1
```

Webの「英語発話」はCLIと同じ辞書とRustの句計画を使い、音素列と時系列を表示します。観測JSONには発音の出典、句の休止と抑揚の設定、声門や口唇、鼻端の流量、軟口蓋のポート面積を保存します。ブラウザに `Mom? Pop.` を入力する比較では、同じCLIケースと固定上流の計画・PCMに照合します。[英語発話の読解と測定](notes/worklet-english-voice.md)

同じ画面で成人男性・成人女性・子ども・混合の体型を選べます。混合の2つの比率は0〜1で指定します。基準F0を空欄にすると選んだ体型の英語用既定値を使います。レンダー結果の「再実行ケースを保存」で、テキスト・体型・音源設定を含むCLI用JSONを取得できます。[体型選択と保存ケースの照合](notes/worklet-english-body.md)

```bash
python3 tools/measure_worklet_english.py worklet-english-voice-local-1
python3 tools/measure_worklet_english_body.py worklet-english-body-local-1
cargo run --locked --release -p vocal-cli -- render-pcm worklet-english-case.json english-replay.wav english-replay.csv 128
```

Webの「歌唱」では英語・韓国語・ロシア語・中国語の歌詞、テンポ、ビブラート、1行に1音のMIDI番号と拍数を指定します。WAVと観測JSONで音節・拍・調音スコア、呼気ゲート、声帯の開大、平滑化F0と瞬時F0を照合できます。英語には固定上流と同じ圧縮済み発音辞書を使い、韓国語はハングルを発音規則で読みます。英語の計測では、通常配信に加え、`--raw-dictionary` でブラウザ自身がgzipを展開する場合も検証できます。[英語歌唱の読解と検証](notes/worklet-song-voice.md)・[韓国語の音節化と歌唱](notes/korean-lyrics.md)

歌唱でも成人男性・成人女性・子ども・混合の体型を選べます。入力形式を「IPA音節 JSON」にすると、研究CLIと同じ頭子音・母音・末子音の定義を使えます。体型を変えても、入力したMIDI番号はそのまま使います。オフラインと実時間の結果から「再実行ケースを保存」で譜面と実行条件をCLI用JSONとして取得できます。[体型別の歌唱とケースの検証](notes/worklet-song-body.md)

```bash
python3 tools/measure_worklet_song.py worklet-song-voice-local-1
python3 tools/measure_worklet_song.py worklet-song-voice-raw-local-1 --raw-dictionary
python3 tools/measure_worklet_song_body.py worklet-song-body-local-1
```

「実時間で歌唱」は同じスコアを量子境界で開始します。実時間版の保存結果と、CLI・オフライン版のPCMおよび音響観測を、次のコマンドで照合できます。開始予約、歌唱中の停止と再開、処理時間とネイティブの割り当ても記録します。[実時間歌唱の比較](notes/worklet-live-song.md)

```bash
python3 tools/measure_worklet_song.py worklet-live-song-local-1 --live
```

「歌唱を録画」は実時間の歌声と拍・時刻の表示を縦長の動画に保存します。対応する形式はブラウザが選びます。FFmpegとffprobeが使える環境では、固定上流と候補の動画をデコードし、加工前PCMとの整列、映像の拍、末尾の無音、準備中と録画中の中止を再検証できます。[録画の読解と検証](notes/worklet-song-recording.md)

```bash
python3 tools/measure_worklet_song_recording.py worklet-song-recording-local-1
```

「録画に声道の三次元断面を含める」を選ぶと、音声と同じ出力フレームに採取した断面を動画で確認できます。合成区間の画像には出力フレームの表示と識別欄が付きます。観測JSONには測定線、音響セル、作画時刻、投影行列が含まれます。復号用の比較は固定上流とCLIの歌唱ケースを参照します。[三次元断面を含む録画の検証](notes/worklet-song-tract-recording.md)

```bash
python3 tools/measure_worklet_song_recording.py worklet-song-tract-recording-local-1 --tract
```

`--webm` では、テスト用ChromiumでMP4の対応判定を無効にし、三次元断面付き歌唱を通常のボタンからWebMに保存します。固定上流の `Clip` にも同じ判定条件を適用し、VP9/Opus、音声フレームとパケットの時刻、拍、復号画像の輪郭、加工前PCMを照合します。[WebMの形式選択と検証](notes/worklet-song-recording-webm.md)

```bash
python3 tools/measure_worklet_song_recording.py worklet-song-webm-local-1 --webm
```

`--vp8` ではMP4とVP9/Opusの対応結果をテストページで無効にし、同じ歌唱と録画の入口からVP8/Opusを選ぶ条件を測れます。固定VP9と加工前WAV・二拍の時差を照合し、固定上流のキャンバス作画時刻と復号後の映像時刻も保存します。[VP8の読解・実測・再実行手順](notes/worklet-song-recording-vp8.md)

`--firefox` では、PlaywrightのFirefoxでブラウザ本来の対応判定を記録し、実際に選んだ形式で三次元断面付きの歌唱を録画します。固定Chromiumと加工前WAV・格子を照合し、復号した拍、音声時刻、輪郭を比較します。[Firefoxの実測と再実行手順](notes/worklet-song-recording-firefox.md)

固定上流の歌唱画面で実際の3D頭部を録画する計測では、表示設定、Canvasへのコピー、調音テレメトリ、保存動画の画素と音声を同じ実行から採ります。録画の前後での計測表示と、完走・中止後のトラック解放も検証します。[固定上流の頭部録画の比較](notes/worklet-song-recording-upstream-head.md)

研究画面の「デュエットの再生時計」から二声の `Pop Dee` を開けます。開始・一時停止・シーク・再開のたびに、混合音源の秒とサンプル番号を確認できます。比較スクリプトは、Rust CLIで作り直した48 kHzのWAV、固定上流と候補の仮想時計、Chromiumの可聴時刻とグラフ内の波形を照合します。[デュエットの再生時計](notes/duet-transport.md)

```bash
python3 tools/measure_duet_transport.py duet-transport-local-1
```

同梱デモのWAVを意図的に作り直す場合は `python3 tools/measure_duet_transport.py --prepare-demo` を実行します。

デュエットには二声の `.tele` も同梱しています。`render-pcm-tele` は歌唱ケースからWAV・PCM計測CSVと `CHTL v1` の採取列を保存します。画面では混合音源の時刻に対応する各声部の観測番号・F0・口唇開度を読めます。比較は固定上流のCLIと読出し、独立したCLIトレース、実ブラウザを通します。[デュエットのテレメトリ](notes/duet-telemetry.md)

```bash
cargo run --locked --release -p vocal-cli -- render-pcm-tele cases/song-voice-long.json voice.wav pcm.csv voice.tele 128
python3 tools/measure_duet_telemetry.py duet-telemetry-local-1
```

同梱の二声の `.tele` を再作成する場合は `python3 tools/measure_duet_telemetry.py --prepare-demo` を実行します。

デュエットの各声部に旋律ファイルを関連付けると、再生位置の歌詞を表示します。音節の明示と辞書を使う歌詞入力を比較し、休符、メリスマ、拍の前後、再生中のシークを実ブラウザで確認できます。[歌詞と拍境界の検証](notes/duet-words.md)

```bash
python3 tools/measure_duet_words.py duet-words-local-1
```

デュエットの「声部別の三次元頭部」は、二声の調音姿勢を再生時計に従って描きます。一時停止では形状を保持し、シークでは新しい位置の観測行を適用します。取得済みの固定上流のWASMを使い、CLIとブラウザが描いた11部位、左右の視点、口唇の変位を照合できます。[三次元頭部の読解と計測](notes/duet-heads.md)

```bash
python3 tools/measure_duet_heads.py duet-heads-local-1
```

頭部には再生位置の音節が表示されます。前方の空きが狭いときは顎の下に移り、通常の音節切り替えでは前の文字が薄れて移動します。シークでは移動先の文字を表示します。計測では実画面の休符・メリスマ・シークと、固定上流に同じ座標を渡した文字の配置を照合します。[口元の文字の読解と計測](notes/duet-mouth-words.md)

```bash
python3 tools/measure_duet_mouth_words.py duet-mouth-words-local-1
```

各頭部は再生中、最近の舌・下顎・唇と開いた口の輪郭を薄く重ねます。一時停止で残像が消え、シーク後は新しい位置から採取を始めます。固定上流に同じ表示時計を与え、三次元の頂点と実画面の画素を再検証できます。[残像の採取と実測](notes/duet-head-echoes.md)

```bash
python3 tools/measure_duet_head_echoes.py duet-head-echoes-local-1
```

デュエットの「表情と頭部の動き」は、観測行の口腔圧・音高と公演の拍を使います。チェックを外すと、表情を固定して調音姿勢を観察できます。固定上流・独立計算と状態を比較し、通常再生とシークの描画を再実行できます。[表情の読解と実測](notes/duet-head-expression.md)

```bash
python3 tools/measure_duet_head_expression.py duet-head-expression-local-1
```

デュエットの「声道の圧力」は、声門からの距離で最も近いCHTL節点を選び、輪を圧力RMSで着色します。一時停止では輪の姿勢を保って中立色に戻ります。比較スクリプトは接触補正済みの測定線をCLIと照合し、固定上流が描く輪と、実ブラウザの停止・色の切り替え・シークを検査します。[圧力表示の読解と実測](notes/duet-head-pressure.md)

```bash
python3 tools/measure_duet_head_pressure.py duet-head-pressure-local-1
```

「気流の軌跡」は、各声部の流量と面積を使って三次元声道内を結ぶ短い線分を描きます。比較スクリプトでは正流・逆流と低速域の移動、停止時の保持、シーク直後の軌跡の切り替えを固定上流と照合します。[粒子の読解と実測](notes/duet-head-airflow.md)

```bash
python3 tools/measure_duet_head_airflow.py duet-head-airflow-local-1
```

「乱流源」は、生成時の気道グラフに従って各声部の最大乱流源を三次元声道に描きます。公開デモを再採取する `tools/measure_duet_telemetry.py --prepare-demo` は、`vocal-cli inspect` が返す `noise_branches` を公演の声部に書きます。既存のCHTL形式を使い、声部に枝情報を付けると乱流表示が利用できます。[枝の由来と三次元描画の比較](notes/duet-head-turbulence.md)

```bash
python3 tools/measure_duet_head_turbulence.py duet-head-turbulence-local-1
```

Webの「ビートボックス」では、記譜、テンポ、スウィングを指定して1.3秒のパターンをオフラインで生成します。WAVと観測JSONを保存でき、休符を含む再生位置の変化を出力フレームで確認できます。観測間隔64と77は、同じ合成を異なる間隔で読み取る比較条件です。[ビートボックスの読解と比較](notes/worklet-beatbox-pattern.md)

```bash
python3 tools/measure_worklet_beatbox.py worklet-beatbox-local-1
```

「実時間でビートを再生」では、採取中にテンポ・スウィングの適用、ビートの停止と再開ができます。停止中の減衰も保存し、Workletが操作を適用した出力フレームとAudioContextフレームを観測JSONへ記録します。「再実行ケースを保存」で出力したJSONはCLIの `render-pcm` にそのまま渡せます。[実時間ビートの読解と比較](notes/worklet-live-beatbox.md)

```bash
python3 tools/measure_worklet_live_beatbox.py worklet-live-beatbox-local-1
cargo run --locked --release -p vocal-cli -- render-pcm worklet-live-beatbox-case.json beat-replay.wav beat-replay.csv 128
```

一様管の計測スクリプトは `inspect` と `render` を実行し、連番、入口流量、入口・口端圧力、口端放射流量、放射流量の時間微分を CSV に保存します。入力の JSON と出力先 CSV を指定すれば、`render` 単独でも実行できます。登録したケースは 96 kHz、48,000 サンプルです。流量と圧力は CGS で記録しています。[ケース定義](cases/uniform-tube-rigid.json)・[単位と離散化](notes/uniform-tube.md)

`--rigid-run` を指定すると、軟壁ケースを同じ実装で通過した剛体ケースと比べます。壁流量と端の枝流量を CSV に追加し、上流の公開状態を取得するプローブと、Python の独立線形計算にも照合します。上流側のプローブは固定版を Cargo でビルドしたライブラリにリンクします。[軟壁ケース](cases/uniform-tube-soft-wall.json)・[読解ノート](notes/uniform-tube-soft-wall.md)・[上流計測プローブ](tools/upstream_wall_probe.rs)

分岐ケースでも同じ CLI の `inspect <ケース.json>` と `render <ケース.json> <出力.csv>` を使います。管順に並ぶ0始まりのセル番号で接続と測定位置を指定し、`observe.branches` の流量は指定した順方向を正とします。分岐の計測スクリプトは、上流の圧力・流量、分岐点の体積収支、左右の対称性を照合します。対称な一様断面条件では離散周波数応答も比較します。[対称ケース](cases/symmetric-junction.json)・[固定狭窄ケース](cases/narrow-junction.json)・[分岐の読解ノート](notes/static-junction.md)

可動断面は `area_ramps` に、開始サンプル、補間時間、制御ブロック長、対象セルと到達面積を指定します。`observe.area_nodes` と `observe.volume_source_nodes` で計測対象を選べます。密閉管の圧縮と放射端の開閉は、入口からの外部励振を使わず断面変化だけで駆動します。[読解ノート](notes/moving-area.md)・[密閉管](cases/sealed-cavity-compression.json)・[放射端の開閉](cases/moving-aperture-release.json)

気道グラフの壁物性は `network.tubes[].wall` で管ごとに指定します。`observe.wall_nodes` を指定すると、選んだ節点の壁変位・速度・流量と、グラフ全体の壁面放射を記録します。軟壁グラフの計測では、同じ候補ソースの単管で通過した実行を `--uniform-run` に渡します。[ケース](cases/network-tube-soft-wall.json)・[読解ノート](notes/network-wall.md)

`network.pressure_nodes` の節点には全管セルの直後から番号を振ります。`network.ports` に接続先、ポートの面積と長さ、損失係数を指定します。`area_ramps` ではセルの平均と最小の到達断面を別々に指定でき、`observe.minimum_area_nodes` で最小断面を記録します。1/4セル狭窄は `--full-run` で同じ実装の1セル狭窄の計測を指定し、定常流量の増分を確認します。[読解ノート](notes/pressure-port.md)・[1セル](cases/steady-constriction-full.json)・[1/4セル](cases/steady-constriction-quarter.json)

移動する狭窄には `sliding_constriction` を使えます。対象の管、制御ブロック長、幅のほか、中心のセル位置と深さをそれぞれ `[サンプル番号, 値]` の時刻列で指定します。各ブロックの終端で目標断面を求め、ブロック内で線形に補間します。加圧した軟壁管のケースは、閉鎖中に保持された圧力と再開口時の放射を比較します。[閉鎖ケース](cases/sliding-closure.json)・[読解ノート](notes/sliding-closure.md)

`network.turbulence` にシード、倍率、各源の観測枝・正流時と逆流時の注入枝、利得、帯域を指定できます。乱流源の枝は接続時と同じ節点順で指定します。`observe.noise_sources` と `observe.noise_branches` で振幅と符号付き注入圧力を記録します。乱流の比較器はNumPyとSciPyを使います。[乱流の読解ノート](notes/turbulence.md)・[上流のMIT通知](LICENSE-CHIMERA)

管ごとの `perimeter_factor` は壁面積と通常枝の粘性抵抗に、`viscous_factor` は通常枝の粘性抵抗に掛けます。既定値はいずれも1です。鼻腔の開放ケースでは `--controls` に閉鎖と側枝切離の通過済み実行を渡し、鼻端放射と側枝の周波数応答への影響を測ります。[鼻腔と側枝の読解ノート](notes/nasal-network.md)

固定声道の声門は、`glottis` にポートの節点、声門のパラメータ、開大ステップを指定します。圧力差は枝計算前に、声門流量は枝計算後に出力されます。声門面積・発声ゲート・位相も同じCSVで確認できます。[声門の読解ノート](notes/glottal-coupling.md)

`glottis.params` に `jitter`（周期長の比率）と `shimmer`（面積振幅の比率）を加えられます。既定はともに0で、`cycle_seed` の既定は上流と同じ777です。比較器は観測した位相の折り返しから周期長を取り、乱数列・面積・流量を照合します。[周期変動の読解ノート](notes/glottal-cycle.md)

`glottis.params.diplophonia` は交互周期の強さです。範囲は0〜1で既定は0です。最初の折り返し後から奇数周期を長く弱くし、偶数周期を短くします。`glottal_f0_hz` は周期長の倍率を適用する前の値です。各周期の平均的な繰り返し時間は `glottal_phase` の折り返しから測れます。[交互周期の読解ノート](notes/glottal-diplophonia.md)

`glottis.params.chaos` はロジスティック写像の強さです。範囲は0〜1で既定は0です。位相が折り返すたびに状態を更新し、周期長と面積振幅の倍率に反映します。比較器は位相から逆算した状態と独立計算の状態を `artifacts/chaos-orbit.csv` に記録します。[ロジスティック写像の読解ノート](notes/glottal-chaos.md)

ピッチの変動は `glottis.params` に `drift_cents` と `vibrato_depth_cents`（ともに既定0）、`vibrato_rate_hz`（既定6 Hz）を指定します。変動倍率は内部サンプル0から32サンプルごとに更新されます。`observe.glottal_f0` を `true` にすると、この倍率を適用した瞬時F0が `glottal_f0_hz` 列に加わります。ジッタによる周期長倍率は、そのF0から位相を進める際に適用されます。[ピッチ変動の読解ノート](notes/glottal-pitch.md)

ボーカルフライの強さは `glottis.params.fry` に0〜1で指定します。既定は0です。フライを加えると、48 Hzを超える瞬時F0が48 Hzへ近づき、主パルスの開口率は0.28へ近づきます。0.3を超えると同じ周期内に第2パルスが加わります。`glottal_f0_hz` はフライ適用後の値です。[フライの読解ノート](notes/glottal-fry.md)

`breath` は既存の肺ポートを選び、設定圧、体型スケール、制御ブロック長、低周波補償の有無を指定します。制御点は `[サンプル番号, 操作ゲート, スコアの値, スコアの有効度]`。各制御ブロックの先頭に、その時点までの最後の制御点を適用します。CSVには呼気のゲートと基礎圧、平滑流量、実際の肺境界圧、声門の強さが加わります。[肺と呼気の読解ノート](notes/lung-breath.md)

`pcm` に出力レートとゲインを指定したネットワークケースは、`render-pcm` でモノラルf32 WAVと出力段のCSVを保存できます。内部レートは出力レートの整数倍で、内部サンプル数はその倍数に合わせます。CLIの最後の引数でホスト側のブロックサイズをフレーム単位で指定でき、既定は128です。[PCMの読解ノート](notes/pcm-output.md)

```bash
cargo run --locked --release -p vocal-cli -- render-pcm cases/pcm-voiced.json voice.wav voice-output.csv 128
```

実行 ID は新しい名前を指定します。各実行の `manifest.json` と計測要約は `runs/<実行ID>/` に、再生成可能な WAV、CSV、コンパイラとテストのログはその配下の `artifacts/` に入ります。候補の実行に使用したソース、ケース、計測器はローカルの `artifacts/source/` に保存し、該当するマニフェストの入力ハッシュで照合できます。Python のスクリプトは、別の作業ディレクトリからスクリプト自体のパスを渡しても実行できます。

### 保存済み実行の比較

`vocal-cli compare <基準の実行> <候補の実行> <比較ケース.json>` は、マニフェストに登録されたモノラルPCM16・float32 WAVと任意の観測CSVを同時刻で比較します。初期の上流実行は、ケース別の成果一覧から読み出せます。異なるWAV形式間では無次元振幅の差を測ります。実行ディレクトリとマニフェストのどちらも指定できます。ケースで出力フレームの区間、観測列、許容差を選びます。比較は最初の差、最大差、判定をJSONに出力します。許容差を超えた場合も判定JSONを出力して終了コード1を返します。外部保存の時系列はマニフェストのSHA-256に照合します。[比較ケース](cases/compare-saved-voice-run.json)・[読み方と再実行](notes/compare-saved-voice-run.md)・[初期のPCM16を比較する](notes/compare-upstream-pcm16.md)

```bash
cargo run --locked --release -p vocal-cli -- compare \
  runs/worklet-midi-voice-pitch-20261121-final \
  runs/worklet-midi-voice-pitch-20261121-final \
  cases/compare-saved-voice-run.json
```

### TSPのF2候補を調べる

強勢付き単母音の計測に `--f2-candidates` を指定すると、各窓の公開LPC極、F2の候補順、採択理由、中央値への寄与が `artifacts/f2-candidates.json` に出ます。周波数と帯域幅はHz、窓開始は間引き後の12 kHzの標本番号です。[読み方と実行例](notes/tsp-f2-candidate-report.md#診断の実行)

### 大容量計測とCSVの保存

`record_measurement` を使う計測スクリプトと `tools/upstream_baseline.py` では、作業用ディスクへ直接出力できます。以下は約1 GiBを見積もった実行例です。見積もりには候補、上流、一時ファイルの最大使用量を含めます。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  python3 tools/measure_grid.py grid-neutral-external-1 grid-neutral
```

この設定では成果の実体とサブプロセスの一時領域をRTL9210B-CG上に作ります。内蔵にケースのスナップショット、マニフェスト、結果要約を置き、`runs/<実行ID>/artifacts/` のファイル単位リンクから成果を参照できます。指定したディスクのUUID、書き込み可否、空き容量を照合してから実行します。通常の出力先は内蔵です。[ディスクごとの運用](../../../docs/plans/chimera-research-rebuild-plan.md#保存先と容量管理)

後続の比較で元のCSVを使わないケースでは、登録JSONに `retain_csv` を加えて、合格後に保存する列とサンプル区間を指定できます。キーは `artifacts/` からの相対パスで、範囲は開始を含み終了を含みません。次の例は `voicing.csv` の先頭4800フレームから声門面積と流量を保存します。

```json
{
  "retain_csv": {
    "voicing.csv": {
      "columns": ["frame", "glottal_area_cm2", "glottal_flow_cm3_s"],
      "sample_column": "frame",
      "sample_ranges": [[0, 4800]]
    }
  }
}
```

判定は全区間で行い、成功した実行では `voicing.retained.csv` と元のCSVのSHA-256を記録します。失敗した実行や `retain_csv` を省略した実行は、元のCSVを保存します。過去の同一CSVを再度統合するときは、実行が終わってから `python3 tools/deduplicate_run_csv.py <新しい台帳.jsonl> --groups 10` のように実行できます。ハードリンクで統合したパスは確定済みの計測結果として扱います。

## 鳴禽の鳴管音源

`syrinx_labia` のケースは片側の鳴管を指定します。`inspect` は駆動・張力に対応する無次元周期、変位範囲、積分回数を出力します。`render` は積分後の変位、無次元時間に対する変位の微分、平滑化ゲート、無次元の開口率を内部サンプルごとにCSVに保存します。入力の `events` には新しい制御一式と適用するサンプル番号を指定できます。[登録ケース](cases/songbird-syrinx.json)・[式と計測結果](notes/songbird-syrinx.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/songbird-syrinx.json
cargo run --locked --release -p vocal-cli -- render cases/songbird-syrinx.json songbird-syrinx.csv
python3 tools/measure_songbird_syrinx.py songbird-syrinx-local-1
```

`songbird_airway` のケースは左右の音源を共通気管に接続します。`inspect` で管ごとのセル数やクーラン数を確認し、`render` で左右の開口・ポート面積・枝流量、気管と口腔食道腔の圧力、くちばし先の放射を保存できます。`events` は制御ブロック境界で適用され、空気嚢圧は即時、口腔食道腔とくちばしの面積はブロック内で補間します。[登録ケース](cases/songbird-airway.json)・[読解と計測](notes/songbird-airway.md)

`songbird_airway.observe_bronchus_end_balance` を `true` にすると、左右の気管支末端について手前のセル圧、直列枝からの流入、断面積、セル長を `render` のCSVに追加できます。既存の末端圧と鳴管流量を合わせると、前回圧とこの標本の流入・流出から末端圧を再計算できます。[観測のケースと検証](notes/songbird-chirps-onset-radiation.md#左右の気管支末端の圧力を直列枝流量から再計算する)

`songbird_airway.observe_bronchus_interior_cells` に入口の0から末端の手前までの番号を指定すると、左右それぞれのセル圧、流入・流出、上流側の圧力、セルの断面積と長さを追加できます。番号0の流入と上流側の圧力は、空気嚢ポートの流量と空気嚢の圧力です。3セルの気管支では番号1が中央セルです。列は指定した番号の順で、番号ごとに左、右の順で並びます。[入口の比較](notes/songbird-chirps-onset-radiation.md#空気嚢ポートと左右の気管支セル0の圧力収支)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/songbird-airway.json
cargo run --locked --release -p vocal-cli -- render cases/songbird-airway.json songbird-airway.csv
python3 tools/measure_songbird_airway.py songbird-airway-local-1
```

`songbird_voice` は呼気と演奏パラメータを平滑化し、鳴禽の持続音と停止をモノラルf32 WAVへ出力します。`events` には出力フレーム番号、呼気ゲート、必要に応じて制御パラメータ一式を指定できます。観測CSVでは各フレームの呼気、内部レートの放射、間引き後の値、DC除去後の値を追えます。内部レートの放射は `radiation_0` から順に並び、内部2倍の条件では後ろの2列が0になります。[登録ケース](cases/songbird-sustain-pcm.json)・[読解と測定](notes/songbird-sustain-pcm.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/songbird-sustain-pcm.json
cargo run --locked --release -p vocal-cli -- render-pcm cases/songbird-sustain-pcm.json songbird-sustain.wav songbird-sustain.csv 128
python3 tools/measure_songbird_sustain_pcm.py songbird-sustain-local-1
```

`songbird_voice.observe_syrinx` を有効にすると、出力フレームの最後の内部サンプルで、左右ポートの実断面積（cm²）と流量（cm³/s）をCSVに加えます。ブラウザの「鳴禽の持続音」で書き出したケースは、そのまま `render-pcm` に渡せます。ブラウザ比較には、持続音PCMの計測で生成した上流の基準実行IDを指定します。[ブラウザの読解と実測](notes/worklet-songbird-sustain.md)

「MIDIで鳴禽を演奏」でMIDI入力を接続し、「鍵盤で鳴らす音」で持続音を選び、計測中に鍵盤を押すと、鳴禽の音域に割り当てられた音高で発声します。最新のキーを離すと保持中の音へ戻り、すべて離すと呼気が閉じます。観測JSONの `midiEvents` と、再実行ケースの `songbird_voice.events[].held_midi.note` に採用フレームを記録します。`note: null` が全解放です。[音域と再実行の検証](notes/worklet-midi-songbird.md)

「鍵盤で鳴らす音」でコールを選ぶと、押下でフレーズ全体を移調して鳴らし、次の押下で先頭から再発音します。解放後もコールの呼気包絡は進みます。保存した `songbird_voice.events[].midi_call` にはコールID・音番号・押下状態が入り、CLIで同じ音を再実行できます。[Flute phraseのMIDI比較](notes/worklet-midi-songbird-call.md)・[Canary trillのパルスと左右の鳴管](notes/worklet-midi-songbird-trill.md)・[Chirp cascadeのキー順とMIDI再発音](notes/worklet-midi-songbird-chirps.md)・[Finch buzzの呼気パルスと再発音](notes/worklet-midi-songbird-buzz.md)

```bash
python3 tools/measure_worklet_songbird.py worklet-songbird-local-1 songbird-sustain-local-1
```

鳴禽の `flute`、`trill`、`chirps`、`buzz` は `songbird_voice.events` の `play_call` で再生し、`stop_call: true` で停止できます。`play_call` は `id` と任意の `pitch_hz`、`amplitude` を受け取ります。コールを指定したCSVでは、制御時計、コールの有効状態、平滑化前のパラメータ目標、呼気目標も観測できます。`songbird_voice.observe_call_id` を有効にすると識別子の列が加わります。値は再生中のコールなしが0、`flute` が1、`trill` が2、`chirps` が3、`buzz` が4です。比較スクリプトは初回の呼気立ち上がりを区別する第2版で実行します。`--revision 1` で元の判定を再演できます。[代表コールの入力例](cases/songbird-flute.json)・[周期コールと切り替えの入力例](cases/songbird-calls.json)・[第2版の条件](cases/songbird-calls-v2.json)・[キー生成と照合](notes/songbird-calls.md)

```bash
cargo run --locked --release -p vocal-cli -- render-pcm cases/songbird-flute.json songbird-flute.wav songbird-flute.csv 128
cargo run --locked --release -p vocal-cli -- render-pcm cases/songbird-calls.json songbird-trill.wav songbird-trill.csv 128
python3 tools/measure_songbird_flute.py songbird-flute-local-1
python3 tools/measure_songbird_calls.py songbird-calls-local-1
```

ブラウザの「鳴禽のコール」では、`flute` の途中停止ケースを実時間再生して、加工前PCM、識別子、平滑値と目標値を保存できます。CLIと固定上流の比較には、先に作成した `flute` の基準実行IDを指定します。[実時間の読解と測定](notes/worklet-songbird-flute.md)

```bash
python3 tools/measure_worklet_songbird_flute.py worklet-songbird-flute-local-1 songbird-flute-local-1
```

`trill` は「再生ケース」から選べます。出力フレーム0から64フレームごとに制御更新直後を観測し、呼気パルス18回の間隔と自然終了を確認できます。比較には上で生成した `songbird-calls` 第2版の基準実行IDを指定します。[実時間の周期比較](notes/worklet-songbird-trill.md)

```bash
python3 tools/measure_worklet_songbird_trill.py worklet-songbird-trill-local-1 songbird-calls-local-1
```

`trill` の観測対照では、同じ入力で64フレーム刻みの先頭・末尾と128フレーム量子末尾を比べます。加工前PCM、共通観測点、WASMの量子別呼び出し回数、描画処理時間を保存します。[観測位置と処理時間の比較](notes/worklet-songbird-trill-observation.md)

```bash
python3 tools/measure_worklet_songbird_trill_observation.py worklet-songbird-trill-observation-local-1 songbird-calls-local-1
```

`chirps` は同じ「再生ケース」から選べます。44.1 kHzのブラウザ比較には、同じ第2版の基準実行IDを使います。比較器は宣言順と時刻順の目標をCLIで再生し、加工前WAVと時系列をそれぞれ保存します。[キー順の実時間比較](notes/worklet-songbird-chirps.md)

```bash
python3 tools/measure_worklet_songbird_chirps.py worklet-songbird-chirps-local-1 songbird-calls-local-1
```

`buzz` は同じ画面で96 kHz、音高1,500 Hz、呼気倍率0.8のケースを再生します。比較では呼気目標の初回間隔と定常時の間隔、自然終了、加工前PCMと固定上流の差を出力します。[初回パルスの読解と実測](notes/worklet-songbird-buzz.md)

```bash
python3 tools/measure_worklet_songbird_buzz.py worklet-songbird-buzz-local-1 songbird-calls-local-1
```

`buzz → trill` は48 kHzで旧コールの再生中に手動値を送り、同じ合成器で新コールに切り替えるケースです。比較器は切り替えを省いたCLIのPCMも保存し、目標、平滑値、放射、波形の変化時刻を照合します。[切り替えの読解と検証](notes/worklet-songbird-switch.md)

```bash
python3 tools/measure_worklet_songbird_switch.py worklet-songbird-switch-local-1 songbird-calls-local-1
```

`seal_breath` はウェッデルアザラシの手動制御から固定肺圧までを実行します。`events` には出力フレーム番号とゲートまたは制御値一式を指定します。CSVは64出力フレームごとに位相、パルス倍率、呼気ゲートの目標と平滑値、変調前後の肺圧を出力します。肺圧の単位は dyn/cm² です。[登録ケース](cases/seal-breath.json)・[読解と測定](notes/seal-breath.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/seal-breath.json
cargo run --locked --release -p vocal-cli -- render cases/seal-breath.json seal-breath.csv
python3 tools/measure_seal_breath.py seal-breath-local-1
```

`seal_airway` は同じ呼気入力を気管、声門、口鼻腔につなぎます。`breath` に出力フレームを基準とする制御、`shape` に初期音高・明るさ・粗さ・口の開きを指定します。内部サンプルごとに肺ポート流量、更新前の声門差圧、声門開口と流量、更新後の節点圧、放射流量の時間差分を観測できます。圧力は dyn/cm²、流量は cm³/s です。[登録ケース](cases/seal-airway.json)・[構造と検証](notes/seal-airway.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/seal-airway.json
cargo run --locked --release -p vocal-cli -- render cases/seal-airway.json seal-airway.csv
python3 tools/measure_seal_airway.py seal-airway-local-1
```

`seal_voice` は気道の放射を間引き・DC除去・振幅制限へ渡し、持続音と停止をモノラルf32 WAVに出力します。`breath` と `shape` は気道のケースと同じ形式で、`level` は出力ゲインに掛ける倍率です。CSVは出力フレームごとにゲート、肺圧、内部サンプル別の壁・口端・鼻端の放射流量と総放射流量の差分、間引き後の値、DC除去後の値、PCMを保存します。1倍レートのときは添字1の列が0になります。[登録ケース](cases/seal-sustain-pcm.json)・[出力段の読解と検証](notes/seal-sustain-pcm.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/seal-sustain-pcm.json
cargo run --locked --release -p vocal-cli -- render-pcm cases/seal-sustain-pcm.json seal-sustain.wav seal-sustain.csv 128
python3 tools/measure_seal_sustain_pcm.py seal-sustain-local-1
```

「ウェッデルアザラシの持続音」の実時間ブラウザ比較では、48・96 kHzの加工前PCMと、呼気目標、肺圧、壁面・口端・鼻端・総放射を同じケースでCLIと照合します。上のCLI比較の実行IDを渡します。[読解と計測](notes/worklet-seal-sustain.md)

「MIDIでウェッデルアザラシを演奏」では、計測中に押したキーを40〜6,000 Hzの発声域に割り当てます。重ねたキーを離すと保持中の音へ戻り、全解放すると呼気が減衰します。書き出した `seal_voice.events[].held_midi.note` は採用フレームからの再実行に使え、`note: null` は全解放を表します。[鍵盤と再実行の検証](notes/worklet-midi-seal.md)

「鍵盤で鳴らす音」でLaser chirpなどのコールを選ぶと、押下がコールの移調と開始、次の押下が再発音になります。離鍵後もコールの包絡が続きます。書き出した `seal_voice.events[].midi_call` にコールID、音番号、押下状態と採用フレームが入り、CLIで再実行できます。[Laser chirpのMIDI比較](notes/worklet-midi-seal-call.md)・[Descending trillの音高・パルス周波数・肺圧](notes/worklet-midi-seal-trill.md)・[U whistleの移調と音高の谷](notes/worklet-midi-seal-whistle.md)・[Chugの呼気と声門周期](notes/worklet-midi-seal-chug.md)

```bash
python3 tools/measure_worklet_seal_sustain.py worklet-seal-sustain-local-1 seal-sustain-local-1
```

アザラシのコール `trill`・`zap`・`whistle`・`chug` は `seal_voice.events` の `play_call` で開始できます。開始には `id` と任意の `pitch_hz`・`amplitude` を指定します。再生中に別のコールを開始すると、そのフレームで切り替わります。`stop_call: true` は途中停止、イベント直下の `pitch_hz` と `roughness` はそれぞれ手動の音高と粗さです。呼気とパルスの手動入力は `breath.events` に置きます。`seal_voice.events` を使うと、CSVにコールの有効状態、制御時計、音高と呼気の目標・平滑値、パルス位相が加わります。`observe_call_id: true` で識別子も出力し、コールなしは0、`trill` は1、`zap` は2、`whistle` は3、`chug` は4です。[trillの入力例](cases/seal-trill.json)・[zapと切り替えの入力例](cases/seal-zap.json)・[whistleの入力例](cases/seal-whistle.json)・[chugの入力例](cases/seal-chug.json)

`observe_glottis: true` で粗さの平滑値と目標値、内部サンプルごとの声門位相、瞬時F0（Hz）、実際の開口面積（cm²）をCSVに加えます。列末尾の `_0` と `_1` は同じ出力フレーム中の内部サンプル順です。間引き倍率1では `_0` を使います。

`measure_seal_chug.py` は[第2版の測定条件](cases/seal-chug-v2.json)を使います。変更前の独立肺圧の判定は `--revision 1` で再実行できます。[条件を改訂した経緯](notes/seal-chug.md#実装と実測)

```bash
cargo run --locked --release -p vocal-cli -- render-pcm cases/seal-trill.json seal-trill.wav seal-trill.csv 128
python3 tools/measure_seal_trill.py seal-trill-local-1
python3 tools/measure_worklet_seal_trill.py worklet-seal-trill-local-1 seal-trill-local-1
python3 tools/measure_seal_zap.py seal-zap-local-1
python3 tools/measure_worklet_seal_zap.py worklet-seal-zap-local-1 seal-zap-local-1
python3 tools/measure_seal_whistle.py seal-whistle-local-1
python3 tools/measure_worklet_seal_whistle.py worklet-seal-whistle-local-1 seal-whistle-local-1
python3 tools/measure_seal_chug.py seal-chug-local-1
python3 tools/measure_worklet_seal_chug.py worklet-seal-chug-local-1 seal-chug-local-1
```

「ウェッデルアザラシの trill」のブラウザ比較は、48 kHzの自然終了、44.1 kHzの移調・手動制御・途中停止と、96 kHzの音高上限を確認します。観測JSONのコール識別子、目標と平滑値、肺圧および加工前PCMを、書き出したケースでCLIから再現できます。[読解と測定](notes/worklet-seal-trill.md)

「ウェッデルアザラシの zap」のブラウザ比較は、公式デモの先頭、再生中の `trill → zap` の切り替え、初期パルス深さ0の3条件を照合します。比較器は切り替え指示を省いたCLI対照も保存し、制御・内部放射・加工前PCMに初めて差が現れる位置を記録します。[読解と測定](notes/worklet-seal-zap.md)

「ウェッデルアザラシの whistle」のブラウザ比較は、下降から上昇へ転じる時刻、平滑音高の谷、復帰する手動目標を照合します。比較器は、対数音高の一次フィルタによる独立計算と、連続時間での平滑化の遅れも記録します。[読解と測定](notes/worklet-seal-whistle.md)

「ウェッデルアザラシの chug」のブラウザ比較では、粗さの目標・平滑値、呼気位相、内部サンプル別の声門位相・瞬時F0・開口面積を追加で観測します。96 kHzでは全フレームの観測から周期長倍率を復元できます。CLIで固定上流と比較した第2版の実行IDを使います。[読解と測定](notes/worklet-seal-chug.md)

`alligator_voice` はアメリカアリゲーターの固定姿勢で、肺圧の開始・停止を描画します。`shape` に音高、声門の不規則性、呼気圧、口・鼻孔の開き、`hiss` を指定し、`events` にゲートを変更する出力フレームを置きます。`inspect` はセル数、口先と鼻腔ポートの面積、口腔乱流源のセルを表示します。CSVは内部サンプルごとに、肺圧、声門差圧・開口・流量、鼻腔ポート、壁面・口端・鼻端の放射を保存します。間引き後の値は、各出力フレームの最後の内部サンプルの行に入ります。[入力例](cases/alligator-fixed-voice-v2.json)・[読解と検証](notes/alligator-fixed-voice.md)

「MIDIでアメリカアリゲーターを演奏」では、鍵盤を12〜120 Hzの発声域へ割り当てます。重ねたキーを離すと保持中の音へ戻り、全解放で呼気が減衰します。書き出した `alligator_voice.events[].held_midi.note` で採用フレームから再実行でき、`note: null` は全解放です。[音域・声門・放射の比較](notes/worklet-midi-alligator.md)

同じパネルの「鍵盤で鳴らす音」ではBellow、Growl、Hiss、Water danceを選べます。コールでは次の押下で包絡が先頭から進み、解放後も発声が続きます。書き出した `alligator_voice.events[].midi_call` に発声のID、MIDI音番号、押下状態が入ります。Hissの観測JSONは、各観測時点の内部2サンプル分の声門・口腔乱流レベルと声門注入圧を含みます。[Bellowの移調と再発音の比較](notes/worklet-midi-alligator-call.md)・[Growlの呼気と口先断面](notes/worklet-midi-alligator-growl.md)・[Hissの音番号交換と乱流の対照](notes/worklet-midi-alligator-hiss.md)・[Water danceの声門周期と放射](notes/worklet-midi-alligator-dance.md)

```bash
cargo run --locked --release -p vocal-cli -- render-pcm cases/alligator-fixed-voice-v2.json alligator.wav alligator.csv 128
python3 tools/measure_alligator_fixed_voice.py alligator-fixed-local-1 --revision 2
python3 tools/measure_worklet_alligator_fixed_voice.py worklet-alligator-fixed-local-1 alligator-fixed-local-1
```

ブラウザの固定発声は同じ5条件を再生し、開始時の気道状態を連続で保存してCLIと照合します。[ブラウザの読解と検証](notes/worklet-alligator-fixed-voice.md)

`alligator_voice.events` の `play_call` に `{"id": "bellow"}`、`{"id": "growl"}`、`{"id": "hiss"}`、`{"id": "dance"}` のいずれかを渡すと、コールを始められます。基準音高があるコールでは任意の `pitch_hz` が移調を指定し、`amplitude` はゲート倍率です。`params` に手動で変更する演奏値を指定し、`stop_call: true` で途中停止します。再生中に別のコールを指定すると、前のコールが制御していた目標が手動値に戻り、新しいコールのキーが次の制御境界で反映されます。`observe_call: true` のCSVには、コール識別子（停止中は0、`bellow` は1、`growl` は2、`hiss` は3、`dance` は4）、制御時計、演奏値の目標と平滑値、口先断面と口腔乱流源の登録を追加します。[bellowの入力例](cases/alligator-bellow.json)・[growlと切り替えの入力例](cases/alligator-growl.json)・[hissと切り替えの入力例](cases/alligator-hiss.json)・[danceを含む公式デモ順序](cases/alligator-dance.json)

`observe_noise: true` では、声門・口腔の乱流レベルと声門乱流の枝への注入圧を内部サンプルごとに保存します。単位は dyn/cm² です。[hissの読解と検証](notes/alligator-hiss.md)

```bash
python3 tools/measure_alligator_bellow.py alligator-bellow-local-1
python3 tools/measure_worklet_alligator_bellow.py worklet-alligator-bellow-local-1 alligator-bellow-local-1
python3 tools/measure_alligator_growl.py alligator-growl-local-1
python3 tools/measure_worklet_alligator_growl.py worklet-alligator-growl-local-1 alligator-growl-local-1
python3 tools/measure_alligator_hiss.py alligator-hiss-local-1
python3 tools/measure_worklet_alligator_hiss.py worklet-alligator-hiss-local-1 alligator-hiss-local-1
python3 tools/measure_alligator_dance.py alligator-dance-local-1
python3 tools/measure_worklet_alligator_dance.py worklet-alligator-dance-local-1 alligator-dance-local-1
```

ブラウザの `bellow` は48 kHzの公式デモ先頭、44.1 kHzの手動操作と途中停止、96 kHzの音高下限を再生します。画面から保存したケースをCLIへ渡し、加工前PCMと主要な観測値を照合します。44.1 kHzでは全内部サンプルの声門位相と口先断面を保存し、周期長と口腔乱流源の切り替わりを確認できます。[読解・登録・実測](notes/worklet-alligator-bellow.md)

ブラウザの `growl` は48 kHzの公式デモ先頭、44.1 kHzの `bellow` からの切り替え、96 kHzの音高上限を再生します。切り替えケースでは、切り替え前に設定した `hiss` の手動値だけを0にした対照と比べ、目標・声門・放射・PCMに差が現れる時刻を調べます。[読解・登録・実測](notes/worklet-alligator-growl.md)

ブラウザの `hiss` は48 kHzの公式デモ先頭、44.1 kHzの `growl` からの切り替え、96 kHzの単独コールを再生します。乱流の観測を有効にすると、各内部サンプルで声門・口腔の乱流レベルと声門の注入圧が得られます。96 kHzでは注入圧を独立計算で照合し、固定上流の乱流を消した対照で同じ区間のPCMを比べます。[読解・登録・実測](notes/worklet-alligator-hiss.md)

ブラウザの `dance` は48 kHzの公式デモ全体、44.1 kHzの `hiss` からの切り替え、96 kHzの単独コールを再生します。声門面積・気道圧・各放射経路の低域を同じ区間で測り、96 kHzでは壁・口端・鼻端の流量から放射差分とPCMを再構成します。[読解・登録・実測](notes/worklet-alligator-dance.md)

`elephant_voice` はアフリカゾウの固定発声を描画します。`shape` には `pitch_hz`、`pressure_cm_h2o`、`trunk`、`chaos` を指定します。`trunk` は0で口側、1で鼻側へ放射を振り分けます。出力フレームを指定した `events` の `gate` と `params` で呼気や放射経路を変えられます。CSVには、声門前後の圧力、口先と軟口蓋の断面、鼻の基部・入口・先端の圧力と弁の流量、壁・口端・鼻先の放射が含まれます。[入力例](cases/elephant-fixed-voice.json)・[読解と検証](notes/elephant-fixed-voice.md)

「MIDIでアフリカゾウを演奏」では鍵盤を声門の8〜45 Hzへ割り当てます。ブラウザから保存した `elephant_voice.events[].held_midi.note` をCLIで読み、採用フレームの音高と呼気を再現できます。番号0も演奏でき、`note: null` は全解放です。[ゾウの持続音MIDIの比較](notes/worklet-midi-elephant.md)

「鍵盤で鳴らす音」からRumble、Trumpet、Squeakを選べます。コール選択時の押下と離鍵は `elephant_voice.events[].midi_call` に書き出されます。Rumbleは鍵盤の音高に応じて移調し、離鍵後も呼気包絡が進みます。[RumbleのMIDI比較](notes/worklet-midi-elephant-call.md)

Trumpetでは鼻の弁がコールの音高曲線に従います。同じ時刻でMIDI 60と67を交換した比較では、固定上流と研究版の両方で音響出力が一致しました。[TrumpetのMIDI比較](notes/worklet-midi-elephant-trumpet.md)

Squeakでは短い間隔で再発音し、モードの平滑値が上がると鼻の実断面が小さくなることを観測しました。弁の自由開口と、モードから求める面積下限を分けて比較できます。[SqueakのMIDI比較](notes/worklet-midi-elephant-squeak.md)

```bash
cargo run --locked --release -p vocal-cli -- inspect cases/elephant-fixed-voice.json
cargo run --locked --release -p vocal-cli -- render-pcm cases/elephant-fixed-voice.json elephant.wav elephant.csv 128
python3 tools/measure_elephant_fixed_voice.py elephant-fixed-voice-local-1
python3 tools/measure_worklet_elephant_fixed_voice.py worklet-elephant-fixed-local-1 elephant-fixed-voice-local-1
```

ブラウザの固定発声は48 kHzの公式冒頭と無呼気、44.1 kHzの経路変更、96 kHzの口側固定を再生できます。観測JSONから鼻の基部・入口・先端への到達と口端・鼻先の放射を調べ、書き出したケースでCLIのPCMを再現します。[ブラウザの読解と検証](notes/worklet-elephant-fixed-voice.md)

`elephant_voice.events` に `{"frame": 76800, "play_call": {"id": "rumble"}}` を置くと `rumble` を再生します。`play_call.pitch_hz` は基準14 Hzからの移調、`play_call.amplitude` はゲート倍率を指定します。`stop_call: true` で停止すると、コールに保持されていた音高と経路の目標が手動値に戻ります。`observe_call: true` を指定すると、CSVにコールID（停止中は0、`rumble` は1）、制御時計、各演奏値の目標、制御時のゲート目標が加わります。[登録ケース](cases/elephant-rumble.json)・[キーと制御の読解](notes/elephant-rumble.md)

```bash
python3 tools/measure_elephant_rumble.py elephant-rumble-local-1
python3 tools/measure_worklet_elephant_rumble.py worklet-elephant-rumble-local-1 elephant-rumble-local-1
```

ブラウザの `rumble` は公式冒頭、移調と途中停止、自然終了を再生します。開始後の最初の制御区間を連続観測し、肺圧が0の間に断面を動かした場合と固定した場合の放射を比べます。[ブラウザの読解と対照](notes/worklet-elephant-rumble.md)

`elephant_voice.shape` と `events.params` に `mode`（0〜1、既定0）と `lip_pitch_hz`（150〜900 Hz、既定470 Hz）を指定できます。入口弁を観測する `observe_valve: true` では、モードと弁音高の目標・平滑値、弁を駆動する差圧、変位、速度、自由開口がCSVに加わります。気道に適用した面積は `trunk_valve_area_cm2` 列で確認できます。`lip_reed` を持つ入力では、`render` で段階的な差圧に対する弁単体の応答を出力できます。[入力と測定条件](cases/elephant-valve.json)・[弁の式と接続](notes/elephant-valve.md)

```bash
cargo run --locked --release -p vocal-cli -- render-pcm cases/elephant-valve.json elephant-valve.wav elephant-valve.csv 128
python3 tools/measure_elephant_valve.py elephant-valve-local-1
```

`play_call.id: "trumpet"` では、モード、弁音高、呼気圧、粗さがコールのキーに従います。ゲートには `play_call.amplitude` が適用されます。弁音高はキーで指定した380→520→470 Hzの軌跡を通り、声門音高と口・鼻の経路は演奏値から取ります。コールIDは2です。[公式順序と途中停止のケース](cases/elephant-trumpet.json)・[補間と演奏値の読解](notes/elephant-trumpet.md)

```bash
python3 tools/measure_elephant_trumpet.py elephant-trumpet-local-1
python3 tools/measure_worklet_elephant_trumpet.py worklet-elephant-trumpet-local-1 elephant-trumpet-local-1
```

ブラウザの `trumpet` は48 kHzの公式順序、44.1 kHzの置き換えと途中停止、96 kHzの音高指定の対照を再生します。観測JSONから入口弁の自由開口と気道に適用する実断面を個別に確認できます。[ブラウザの観測条件と読解](notes/worklet-elephant-trumpet.md)

`play_call.id: "squeak"` はコールID 3で、弁音高820→880 Hz、モード1→0、呼気圧20→16 cmH₂Oをキーに沿って動かします。`elephant-squeak.json` には、持続音から `rumble`、`trumpet`、`squeak` までを一つの気道で再生する公式順序が入っています。[公式順序と初期モードの対照](cases/elephant-squeak.json)・[squeakの読解と計測](notes/elephant-squeak.md)

```bash
python3 tools/measure_elephant_squeak.py elephant-squeak-local-1
python3 tools/measure_worklet_elephant_squeak.py worklet-elephant-squeak-local-1 elephant-squeak-local-1
```

ブラウザの `squeak` では48 kHzの公式デモ全体、44.1 kHzの置き換えと途中停止、96 kHzの初期モード0と1を再生できます。96 kHzの両ケースで断面・差圧・放射を先頭から連続観測し、自由開口と面積下限のどちらが実断面を決めるかを確認します。[ブラウザの観測条件と読解](notes/worklet-elephant-squeak.md)
