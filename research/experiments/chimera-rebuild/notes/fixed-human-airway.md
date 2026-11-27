# 固定姿勢の断面を人間の気道へ接続する

## 上流の呼び出し順と状態

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::new` は `HumanAirway::new` で管・ポート・放射端を作り、初期姿勢を `HumanAirway::apply(a, 0.0)` に渡す。`commit` は矢状面、格子、各セルの平均と最小断面を計算し、管長と断面を次の目標値へ書き込む。軟口蓋ポートの断面は成人男性の場合 `max(velum, 0)` cm²。続く `snap_to_targets` が現状態へ即時反映し、体積変化による流量を発生させずに初期化する。動的更新では `HumanVoice::control` が正の時間幅で姿勢を適用し、`begin_block` が面積とセル長をサンプルごとに補間する。本検証の初期化は静止姿勢の経路を対象にする。[音声生成の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L276)・[制御ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L499)・[形状の設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[気道の目標値と即時反映](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L647)

成人男性ではセル数の設計に `dx = (c / fs) / 0.93` を使い、咽頭は `floor(7.1 / dx)`、口腔は `floor(7.3 / dx)`（ともに8セル以上）。サンプルレート `fs` は内部 Hz、音速 `c` は35000 cm/s。姿勢によって管が縮む場合は音響計算側の長さを `max(解剖学的な長さ, N × c / (fs × 0.97))` にし、各セル長をその `1/N` にする。咽頭・口腔の解剖学的な長さと断面列は解剖の出力として保持する。補正後のセル長は、コンプライアンス `max(A, 0.02) × Δx / (ρc²)`、枝慣性に入る半セル長、粘性抵抗、壁面積に反映される。[セル数と管の物性](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L104)・[長さの安定性下限](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L310)・[要素の計算式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1196)

気管・咽頭・口腔・鼻腔・梨状窩の順に節点を割り当て、最後に肺と上顎洞を置く。咽頭と口腔、咽頭と梨状窩は普通の枝でつなぐ。肺入口、声門、軟口蓋、上顎洞の頸部は独自の長さと断面を持つポート。唇・鼻端には放射負荷を置き、咽頭・口腔の壁からも放射がある。枝流量は cm³/s、節点圧力は dyn/cm²、放射差分は cm³/s²。上流の安定性テストは内部64〜96 kHzの複数姿勢でクーラン数が0.971以下になることと、問題を再現した姿勢への移動後に無声出力が落ち着くことを確認する。[上流の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L149)・[極端な姿勢のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L154)

## 実装前に登録した比較

初期圧力と流量は0、声門は閉鎖、肺圧0、乱流なし。咽頭の声門側に内部サンプル0でだけ `10⁻⁶ cm³` を注入する。各ケースで8192サンプルを記録し、7168から末尾までの放射差分ピークを全区間のピークで割る。固定上流の節点の実面積・最小断面・セル長に加え、咽頭入口・分岐・唇・鼻端・上顎洞の圧力、口腔接続・軟口蓋・上顎洞の流量、放射の各成分を照合する。上流から得た解剖学的な長さと既存の格子上の断面を使った独立計算で、セル長下限とコンプライアンスも照合する。

| ケース | 事前の予測 |
| --- | --- |
| [中立96 kHz](../cases/fixed-airway-neutral.json) | 咽頭と口腔が18セルずつ。ともに伸長しない。口端の流量はサンプル35で初めて現れ、鼻端は0のまま |
| [軟口蓋開放](../cases/fixed-airway-velum-open.json) | ポート断面0.3 cm²。鼻端はサンプル39から流れ、上顎洞の頸部にも流量が現れる |
| [短い口腔96 kHz](../cases/fixed-airway-short.json)・[64 kHz](../cases/fixed-airway-short-64k.json) | 約5.30 cmの口腔だけを約6.77 cmに伸ばし、クーラン数を0.97に抑える。96 kHzで18セル、64 kHzで12セルなので下限管長は一致する |
| [唇の閉鎖](../cases/fixed-airway-closed-lips.json) | 口腔セル17が閉鎖。口端と鼻端の流量は0で、咽頭・口腔の壁面放射は観測される |

## 実装と測定結果

再実装は姿勢を既存の `SagittalModel` と `AreaProfile::resample` へ通し、解剖学的な長さを保存する。伸長が必要な管ではセル長だけを変更し、調和平均・最小断面の配列をその長さで `Section` に割り当てる。初期化済みの断面を `AirwayNetwork::new` に渡すため、初期化時の補間や体積励振は生じない。計測した応答は、静止状態に外部体積を注入した後の圧力・流量・放射。[気道の組み立て](../crates/vocal-core/src/airway/human.rs)・[CLIの処理](../crates/vocal-cli/src/geometry_case.rs)

| 固定条件 | 口腔のセル数 | 解剖学的な長さ → 音響計算用の長さ (cm) | 気道の最大クーラン数 | 口端・鼻端の放射開始サンプル |
| --- | ---: | ---: | ---: | --- |
| [中立96 kHz](../runs/fixed-airway-neutral-20261119-e/summary.json) | 18 | 8.2990 → 8.2990 | 0.79076 | 35、流量0 |
| [軟口蓋開放96 kHz](../runs/fixed-airway-velum-open-20261119-e/summary.json) | 18 | 8.1862 → 8.1862 | 0.80165 | 35、39 |
| [短い口腔96 kHz](../runs/fixed-airway-short-20261119-e/summary.json) | 18 | 5.3034 → 6.7655 | 0.97000 | 35、39 |
| [短い口腔64 kHz](../runs/fixed-airway-short-64k-20261119-e/summary.json) | 12 | 5.3034 → 6.7655 | 0.97000 | 23、30 |
| [唇の閉鎖96 kHz](../runs/fixed-airway-closed-lips-20261119-e/summary.json) | 18 | 8.3226 → 8.3226 | 0.78852 | 両端とも流量0 |

短い口腔を解剖学的な長さのまま計算した場合のクーラン数は両レートで約1.23742。音響計算側の管長を1.46210 cm（27.57%）伸ばすと0.97になった。唇の閉鎖では口腔のセル17が閉じ、口端・鼻端の流量は測定区間を通じて0だった。壁面放射のピークは約 `2.448×10⁻⁴ cm³/s`、放射差分の末尾1024サンプルのピークは全区間の約6.10%まで減衰した。[短い口腔](../runs/fixed-airway-short-20261119-e/summary.json)・[唇の閉鎖](../runs/fixed-airway-closed-lips-20261119-e/summary.json)

各19項目、合計95項目を通過した。節点の解剖学的な管長・音響計算用の管長・セル長の上流との差は `1.78×10⁻¹⁵ cm` 未満、両面積は `3.91×10⁻¹⁴ cm²` 未満。12観測系列×8192サンプルで、上流の列ピークに対する最大差は `6.74×10⁻¹⁴` 未満。独立計算では格子上の断面をもとにセル面積と長さを再計算し、体積からコンプライアンスと初回の圧力、口端・鼻端・壁面の流量和から放射差分を求めて照合した。[計測器](../tools/measure_fixed_airway.py)・[実行記録](../runs/fixed-airway-short-20261119-e/manifest.json)

研究ディレクトリと `/tmp` からの再実行で、設定、候補と上流の時系列、節点・格子・独立計算のCSV、要約の35ファイルが一致した。既存13ケースでは直前の通過版と90ファイルが一致した。また、短い口腔の入力体積だけを0にしたときは全8192サンプルの観測値が0だった。[研究ディレクトリからの実行](../runs/fixed-airway-short-20261119-d/manifest.json)・[別ディレクトリからの実行](../runs/fixed-airway-short-20261119-e/manifest.json)・[固定声道PCMの回帰](../runs/pcm-voiced-20261119-m/manifest.json)

中立の初回は、上流と再実装のCSVを保存した後、NumPyの真偽値をJSONに変換できず測定要約の保存に失敗した。真偽値の変換を修正して同じケース定義で実行し直した。上流の事前確認では、直接の `rustc` 呼び出しでリリースプロファイルの panic 設定と LLVM ビットコードのリンクに失敗したため、事前試算にはデバッグライブラリを使った。登録ケースの比較は既存の Cargo とリンク時最適化の手順で固定版のリリースライブラリを使用した。[初回の失敗記録](../runs/fixed-airway-neutral-20261119-a/manifest.json)・[通過した比較の環境とコマンド](../runs/fixed-airway-neutral-20261119-e/manifest.json)

```bash
python3 tools/measure_fixed_airway.py fixed-airway-short-local-1 fixed-airway-short
python3 tools/measure_fixed_airway.py fixed-airway-short-64k-local-1 fixed-airway-short-64k
```
