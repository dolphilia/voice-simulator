# アフリカゾウの `trumpet`

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の公式CLIは、持続音・停止・`rumble` を一つの `CreatureVoice` で描画し、出力249,600で `trumpet` を開始する。最後のキーは1.25秒で、0.5秒の余韻を含めて84,000フレームを描画する。固定試験 `elephant-call-trumpet` は48 kHzで単発68,160フレームのPCM保存区間とテレメトリを比較する。`elephant-stop` は別のコールからの切り替えと、手動値を変更した後の停止を検証する。両試験はホスト分割1、77、128、4,096フレームでも比較する。[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[trumpetのキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L145)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)

`CreatureVoice::eval_call` は各パラメータを定義するキーだけを取り出す。直前の値を `x₀`、次の値を `x₁`、区間内の位置を `u=(t−t₀)/(t₁−t₀)` とする。次のキーに `Curve::Exp` が付き、両方の値が正なら `x₀(x₁/x₀)ᵘ` で目標を計算する。弁音高は0→0.5→1.1秒に380→520→470 Hz、呼気圧と粗さは0→1.1秒に26→34 cmH₂Oと0.1→0.6へ指数補間される。呼気圧の34→16 cmH₂Oは1.1→1.25秒の線形補間になる。モードには途中キーがなく、開始時の1から1.25秒の0へ直線で下がる。ゲートは0から0.05秒で1へ上がり、1.25秒で0へ戻る。[パラメータ別の評価](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[キーの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L150)

コールが所有するのはモード・弁音高・呼気圧・粗さ。声門音高と口・鼻の経路の目標は演奏値から取る。移調倍率 `指定音高/470` は音高の役割が付いたパラメータに適用される。役割を持つ `pitch` が `trumpet` のキーになく、`lipPitch` には役割が付いていないため、このコールでは音高指定が目標に作用しない。ゲートには振幅倍率が作用する。コール終了の判定は制御時計が1.30秒を超えたときで、停止要求では即時に所有値を演奏値へ戻す。[音高の役割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L129)・[開始と終了](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[移調の適用](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L312)

64フレームごとにコールの目標を計算し、弁音高は対数空間、モードと呼気圧、粗さは線形の一次遅れに通す。平滑モードは声門の開大・振幅・乱流係数と、鼻の入口弁への差圧の重み・実断面の下限を同時に変える。圧力境界から弁・鼻先の放射までの更新順は固定モードの弁の検証に従う。[制御順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[入口弁と発声モード](elephant-valve.md)

## 事前登録

48 kHzの公式順序、44.1 kHzで `rumble` を置き換えて途中停止する条件、96 kHzの自然終了と音高指定の有無の対照を使う。曲線はキー間の観測を含めて全フレームで見比べ、44.1 kHzでは置き換え時の所有解除と、停止時に目標が復帰してから平滑値が変わるまでを検査する。96 kHzの最初の32,768フレームは、700 Hzの指定を加えた場合と、指定を省略した場合で計測CSVとPCMが一致すると予測する。[登録した条件](../cases/elephant-trumpet.json)

## 実装と実測

コールのキーをパラメータごとの曲線として保持し、その曲線の有無から演奏値の所有を決める。既存の線形補間に区間終点の指数指定を追加し、音高の役割がある声門音高にだけ移調倍率を掛けた。独立計算はキー間の目標を対数値の加重平均で求め、別の一次遅れで平滑化した。4条件で独立計算との最大差は弁音高の目標が `6.82×10⁻¹³ Hz`、平滑値が `3.18×10⁻¹² Hz`、肺圧が `3.64×10⁻¹¹ dyn/cm²` だった。入口弁の状態行列、声門の開大、実断面と出力段も照合した。[コールの実装](../crates/vocal-core/src/airway/elephant/call.rs)・[計測器](../tools/measure_elephant_trumpet.py)・[数値差](../runs/elephant-trumpet-20261120-a/summary.json)

| 条件 | 開始要求・初回制御・所有終了の出力フレーム | PCMの最大絶対差 |
| --- | --- | ---: |
| 48 kHz、公式順序 | 249,600・249,600・312,064 | `3.73×10⁻⁹` |
| 44.1 kHz、置き換え・途中停止 | 48,021・48,064・86,011 | `1.86×10⁻⁹` |
| 96 kHz、700 Hz指定・自然終了 | 31・64・124,928 | `9.31×10⁻¹⁰` |
| 96 kHz、指定を省略した先頭32,768フレーム | 31・64・計測中は所有を継続 | `9.31×10⁻¹⁰` |

96 kHzの開始0.25秒時点では、弁音高の目標は `√(380×520) = 444.5222 Hz`、平滑値は439.0716 Hzだった。1.1秒の目標は弁470 Hz、呼気圧34 cmH₂O、粗さ0.6だった。音高指定あり・なしの対照では、候補のCSVとWAVのPCM、上流のCSVが先頭32,768フレームでそれぞれ一致した。[キー間の目標と対照](../runs/elephant-trumpet-20261120-a/summary.json)

44.1 kHzでは48,021の置き換え要求で先行する `rumble` が所有していた音高と経路が31 Hz・0.55に戻り、新しいキーは48,064で反映された。この制御でゲート目標は1から0になり、平滑ゲートは0.97610残った。62,317の手動変更で、声門音高24 Hzと経路0.7が即時に入り、弁音高・呼気圧・粗さ・モードの変更は停止86,011で復帰した。平滑値が変わったのは次の制御86,016だった。[置き換えと途中停止](../runs/elephant-trumpet-20261120-a/summary.json)

公式条件で `call_id == 2` かつ平滑モードが0.02を超える60,288フレームを抽出し、`4.5(1−m)−自由開口` を求めた。最小差は0.23639 cm²で、全区間の実断面は面積下限と一致した。平滑モードは最大0.91044で、自由開口の最大値は0.16701 cm²だった。同じ集計で44.1 kHzの途中停止と96 kHzの両条件でも面積下限が自由開口を上回った。公式条件の開始0.12〜0.30秒では自由開口の最大・最小差が0.12403 cm²、鼻先流量の平均除去後RMSが253.40 cm³/sだった。弁が動いている区間においてその開口変動のどこまでが気道に適用されるかは、並行する面積の下限で決まる。[公式条件の時系列](../runs/elephant-trumpet-20261120-a/artifacts/official-trumpet-48000/pcm-128.csv)・[各観測窓](../runs/elephant-trumpet-20261120-a/summary.json)

## 残る差と再現

公式CLIの先頭333,600フレームで異なるPCM単精度値は94フレーム、`trumpet` の84,000フレームでは44フレームだった。最大差は全体で `3.73×10⁻⁹`、`trumpet` で `9.31×10⁻¹⁰`。公式順序の最初の内部差はフレーム1の肺流量にあり、気管端圧34、声門流量35、壁面放射36へ伝わった。`trumpet` の起点では駆動差圧が249,600、自由開口が250,062で初めて異なった。実断面は候補と上流で一致し、この区間の最初のPCM差は255,193だった。固定上流プローブは公式CLIの先頭333,600フレームとビット一致した。[公式比較と最初の差](../runs/elephant-trumpet-20261120-a/summary.json)・[コマンド・環境・SHA-256](../runs/elephant-trumpet-20261120-a/manifest.json)

研究ディレクトリと `/tmp` で各359項目を通過し、要約とWAV・CSV・JSONの計測ファイル34件が一致した。ゾウの弁、`rumble`、共有の線形補間を使うアリゲーターの `dance` でも要約と計測ファイルが変更前と一致した。[再実行](../runs/elephant-trumpet-20261120-repeat/manifest.json)・[弁の回帰](../runs/elephant-valve-trumpet-regression-20261120/manifest.json)・[rumbleの回帰](../runs/elephant-rumble-trumpet-regression-20261120/manifest.json)・[danceの回帰](../runs/alligator-dance-trumpet-regression-20261120/manifest.json)
