# 下唇の断面積の段差が発声へ伝わる経路

## 固定上流の呼び出しと単位

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。 `HumanVoice::render` は出力64サンプルに一度 `control` を実行する。48 kHz出力を2倍で計算する今回の条件では、内部クロックは96 kHz、1制御周期は128サンプル（1.333 ms）。引き込みの位置と速度は調音器の状態で、この軸の固有周波数は10 Hz。重みと速度倍率を適用した目標に向けて、速度を先に、位置を後に更新する。引き込み量は無次元。舌先を固定し、唇の引き込みだけに目標変更を渡す。[発声と制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L370)・[調音器の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)

`HumanAirway::apply → commit` は前制御周期の平均・最小面積を保存し、姿勢から新しい目標を求める。接触で位置を補正するときは `reapply` で同じ基準から計算し、上限を二重に使わない。開く方向は面積が十分大きいとき `45 + 40 × 新しい面積` cm²/s、閉じる方向は `45 + 40 × 前の面積` cm²/sで制限する。閉鎖近傍は断面に応じ、口端付近の開き始めの基礎速度は7 cm²/sまで下がる。最小断面は平均断面以下、かつ非負にする。管長はクーラン数が0.97を越えない長さまで延ばし、面積とともに次のブロックへ渡す。固定姿勢の既知試験は20咽頭・24口腔セルで、実時間の今回の体型とレートでは18・18セルになる。[気道の目標と速度制限](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[静止時の段差](lip-tuck-area-continuity.md)

`AirwayNetwork::begin_block` は現在値と目標値の差を128等分する。 `step` はまず面積・最小面積・セル長を一刻み動かし、体積変化による流量源を分配・低域通過させ、枝の体積流量と節点圧を更新する。圧力は dyn/cm²、流量は cm³/s。口端と鼻端は放射負荷を介して外へ流れ、咽頭・口腔壁では壁流量の0.25倍も放射に加わる。合計体積流量の1サンプル差を96,000 s⁻¹倍した値がエンジンの出力段へ渡る。放射は cm³/s² の微分で、音圧に比例する観測値。間引き、25 Hzの直流除去、リミッタ、f32変換を経た値をPCMとして保存する。[ブロックの補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)・[1サンプルの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L826)・[放射の微分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)

```mermaid
flowchart LR
  A["引き込み量"] --> B["平均・最小面積の目標"]
  B --> C["前周期を基準に速度制限"]
  C --> D["128刻みで面積と長さを補間"]
  D --> E["圧力と口端流量"]
  E --> F["壁・口・鼻の流量微分"]
  F --> G["48 kHz PCM"]
```

上流の `fast_but_articulator_limited_closure_gives_bounded_piston_pressure` は8 msの閉鎖で変形由来の圧力が20 cmH₂O未満か確認する。 `output_does_not_depend_on_the_host_block_size` はホストが分けるブロックのサイズにかかわらず同じPCMを得ることを確認する。今回のケースでは、同じ気道と出力段を使い、前突した下唇の既知の切り替えを発声中に通過する。[変形と圧力の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L233)・[ホストブロックの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

## 事前に登録した条件と計測

成人男性、顎0.3 cm、唇開き0.05 cm、前突0.2 cm、広がり0.5。呼気ゲート1、肺圧設定7.2 cmH₂O、110 Hz。乱流と周期の変動を切り、初期の引き込み量0.86117で128 ms発声した後、目標を0.863へ変える。固定対照は初期姿勢を保つ。速度制限を緩める上流の対照は、開大・閉鎖・唇の基礎面積速度を10⁸ cm²/sに設定し、通常条件と同じ目標・圧力・補間で発声する。比較に含める最初の20 msでは、圧力と流量の応答、PCMの残差、0–2・2–8・8–24 kHzの残差を測る。観測セルはすべて0始まり。[ケース定義](../cases/lip-tuck-voiced-radiation.json)

再実装の通常の `render` に口腔セルの任意選択を追加した。選択したセルの平均・最小面積と圧力、下唇の引き込み量、口端圧、壁からの放射を内部サンプル単位で保存する。固定上流は既存の発声プローブを通し、出力サンプルを確定する内部サンプル（2刻みに1回）で同じ列を取得した。速度制限前と後の目標は両方の形状専用の入口から採り、通常の発声中の適用面積に一致するか確認する。独立計算は、ばね・減衰つき調音、断面の速度制限、128刻みの線形補間、全放射流量の時間差分、PCMのFIR・直流除去・リミッタを照合する。[CLIの観測](../crates/vocal-cli/src/articulation_case/voiced.rs)・[固定上流の観測](../tools/upstream_articulation_probe.rs)・[比較と独立計算](../tools/measure_lip_tuck_radiation.py)

## 発声中の段差と出力

制御フレーム96（128 ms、内部サンプル12,288、出力フレーム6,144）で、引き込み量が0.861170000から0.861182844へ進み、静止測定で得た境界0.86117943を越えた。口腔セル13の変化を以下に示す。端点間の補間は通常の候補と固定上流、および上流の速度制限を緩めた対照で照合し、観測した3セルの平均・最小断面の最大誤差は5.60×10⁻¹⁴ cm²だった。口腔のセル長は0.480551から0.469242 cmへ短くなり、長さの補間も最大3.56×10⁻¹⁵ cmで独立計算と一致した。[段差と気道の照合](../runs/lip-tuck-voiced-radiation-20261121-a/summary.json)

| 口腔セル13の変化 | 平均面積の増加 cm² | 最小面積の増加 cm² |
| --- | ---: | ---: |
| 姿勢から求めた目標 | 0.317891 | 0.419227 |
| 通常の速度制限後の目標 | 0.237033 | 0.216967 |
| 通常条件の最初の内部サンプルで適用 | 0.001852 | 0.001695 |

通常条件の固定対照との差は、口腔セル13の圧力・口端圧と流量・全放射の微分で、出力フレーム6,144から検出された。PCMは6,145、声門上の圧力は6,154から。時刻は48 kHzの共通観測点とケースで登録した検出下限に従う。候補と固定上流の最初の厳密な数値差は、初期の口端最小面積に出た（内部サンプル1で2.18×10⁻¹⁴ cm²）。音響観測のピーク比での最大差は2.25×10⁻¹³以下で、両条件とも11,520フレームのf32 PCMはビット一致した。[固定条件と引き込み条件](../runs/lip-tuck-voiced-radiation-20261121-a/artifacts/)・[共通時計での比較](../runs/lip-tuck-voiced-radiation-20261121-a/summary.json)

| 上流の条件と唇固定との差 | 最初の1.33 msのPCM RMS | 最初の1.33 msのPCM最大差 | 最初の20 msのPCM RMS | 最初の20 msのPCM最大差 |
| --- | ---: | ---: | ---: | ---: |
| 速度制限あり | 0.007696 | 0.015637 | 0.005937 | 0.018010 |
| 面積の速度制限を緩和 | 0.006644 | 0.014668 | 0.006139 | 0.036097 |

最初の1制御周期では、速度制限を緩めたときの口腔セル13の圧力差のRMSは41.98から58.14 dyn/cm²へ増えたが、口端流量差は9.38から8.05 cm³/sへ減った。20 ms内のPCM最大差は通常条件で切り替えの81フレーム後、対照で77フレーム後に出た。差の大小は観測点や時間窓で変わる。0〜20 msのPCM残差は、両設定ともHann窓を掛けた0–2 kHz帯が最も大きかった。速度制限だけを変えた残差のRMSは0〜20 msで0.001685、20〜40 msでは0.0000129まで下がった。数値は位相のそろった単一条件での波形差。聴取上の評価は未実施。[窓ごとの圧力・流量・帯域別残差](../runs/lip-tuck-voiced-radiation-20261121-a/summary.json)

## 再現と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1。測定の15判定、上流の圧力とホストブロックの2試験、候補ワークスペース41試験、従来の有声母音遷移26判定が通過した。追加の口腔セルを重複指定した場合と範囲外を指定した場合はCSV作成前にエラーを返すことを確認した。今回のRustファイルの整形とPythonの構文検査も通過した。正式実行と `/tmp` からの再実行で、各35出力のSHA-256と保存先を照合し、計測CSV・WAV・要約など決定的な30出力はバイト一致した。各計測の実体約20.19 MBはRTL9210B-CGにあり、全内部サンプル列はgzipで保存した。[正式実行](../runs/lip-tuck-voiced-radiation-20261121-a/manifest.json)・[別ディレクトリからの再実行](../runs/lip-tuck-voiced-radiation-20261121-repeat/manifest.json)・[従来の母音遷移](../runs/lip-tuck-voiced-regression-20261121-a/summary.json)

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_lip_tuck_radiation.py lip-tuck-voiced-local-1
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_voiced_vowel_motion.py lip-tuck-voiced-regression-local-1 vowel-motion-voice-vowels
cargo test --workspace --locked
```

次は、前方の縦線に現れる交差対がかすめる極限で厚さ0から増えることを利用し、その組織厚さだけを隙間から引く候補を、現行の交差選択とは別条件で評価する。まず前回の静止12条件と既存の通常の引き込み・閉鎖を用い、次に今回の動的条件と唇歯摩擦音で閉鎖・再開口の時刻、摩擦、放射差を記録する。
