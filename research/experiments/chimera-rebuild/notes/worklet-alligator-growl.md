# 実時間AudioWorkletでのアメリカアリゲーターの `growl`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryのボタンは `AudioEngine` を経由して `call`、手動操作は `cparams` をWorkletに送る。Workletは種のコール・パラメータ一覧から索引を引き、WASMの `engine_play_call`・`engine_creature_param` を呼ぶ。公式CLIは同じ `CreatureVoice` を持続音から使い続け、出力48 kHzの196,800で `growl` を開始する。上流の波形試験は `alligator-call-growl` と70 Hz・倍率0.6の `alligator-pitched` のPCM、区間RMS、内部観測を照合する。実時間試験は、全コールのキー解決と再生・手動編集・停止中に割り当てが発生しないことを検査する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Workletの操作](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASMの操作](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`CallDef::resolve` は各キーに現れる名前から所有マスクを作る。演奏値・目標・平滑値を別に持ち、手動編集は演奏値に保存して、現コールの未所有項目だけ目標へ反映する。`play_call` は旧コールを終了して所有項目を手動目標に戻し、新しいコールの開始時計を保存する。`growl` の所有は音高・粗さ・口で、`bellow` が所有していた `hiss` は手動値を使い続ける。64出力フレームごとに処理する `control` で新しいキーを評価し、その後に平滑化する。コール時計は秒、平滑係数は `1−exp(−64/(fs·τ))`。通常のパラメータは線形に、正の音高は比のべき乗で近づける。`hiss` の時定数は40 ms。ゲート目標は手動ゲートと倍率を掛けたコールゲートの大きい方を採る。[所有の解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs#L179)・[目標と制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)

`growl` の音高は45→38 Hzを0.5秒で直線補間して保持し、移調倍率を掛けて12〜120 Hzに制限する。ゲートは0.6秒で1→0、粗さと口の目標は0.7と0.15。所有は終端に50 msを加えた時刻を厳密に超えた制御境界で解除される。平滑な口の値は目標断面 `0.05+12·口` cm²になり、平滑 `hiss` は声門開大 `0.02+0.8·hiss` cm²と駆動振幅 `0.9(1−hiss)` cm²に入る。声門・気道を内部サンプルごとに更新し、放射の差分、間引き、DC除去、振幅制限を経て加工前の単精度PCMを出す。[気道への指示とキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)・[キーから出力までのCLI読解](alligator-growl.md)

## 事前登録

48 kHzは公式デモ先頭と `growl` 区間、96 kHzは指定音高150 Hzに対する120 Hzの上限と自然終了を確認する。44.1 kHzは全65,000出力フレームの内部2サンプルを観測する。23,617で `bellow` から移ると手動目標 `hiss=0.62`、音高31 Hzが見え、23,680でゲート・音高などの `growl` のキーと平滑化が反映される。27,137の手動編集で `hiss=0.05`・肺圧24 cmH₂Oの目標が変わり、27,200で平滑値が動く。音高・粗さ・口の手動目標は52,352の自然終了時に反映される。PCMはCLIとビット一致、内部観測は最大差0、固定上流と独立計算には既登録の許容差を使う。

単一要因の対照として、44.1 kHzのケースの12,001に指定した `hiss` だけを0.62から0に変え、同じCLIで描画する。両系列の `hiss` 目標は切り替えの23,617で初めて分かれ、平滑値は23,680、声門面積は内部47,360で初めて分かれると予測する。加工前PCMと放射は声門面積より先に分かれず、ゲート、音高目標、平滑ピッチ、肺圧、口先・軟口蓋の断面は一致すると予測する。PCM差の発生はビット差と `1e-6` 超過の両方で記録する。[ブラウザの登録条件](../cases/worklet-alligator-growl.json)・[共通の入力と独立計算](../cases/alligator-growl.json)

## ブラウザへの接続

画面の `growl` 用の再生条件から、既存のアリゲーター用WASM・AudioWorkletへ接続した。イベントと観測位置で分けて描画し、切り替え前後も同じ合成器を保持する。画面から保存したケースをCLIで実行し、加工前PCMとブラウザの列を比較する。同じCLI全系列は固定上流の観測値、独立の制御・断面・周期・出力計算へ照合する。44.1 kHzの `hiss` 対照ではブラウザの全内部観測から声門面積・流量・放射を検査する。[再生画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[共通の照合手順](../tools/measure_worklet_alligator_call.py)・[growlの対照実験](../tools/measure_worklet_alligator_growl.py)

## 実測

Chromium 156.0.8078.4の実時間AudioWorkletから保存した加工前PCMは、同じ入力のCLIと全396,392フレームでビット一致した。70,186観測点の制御・気道状態も最大差0だった。固定上流との数値差は次の表のとおりで、各系列が登録した許容差内だった。音高上限のケースでは、開始指示29から最初の制御64を経て、自然終了62,464までコール区間の目標音高は120 Hzだった。全3条件でCLIの声門位相から得た280周期の倍率を独立の周期モデルと最大差 `2.22×10⁻¹⁶` で照合した。[測定値と判定](../runs/worklet-alligator-growl-20261120-a/summary.json)

| 条件 | 出力フレーム | 観測点 | 固定上流との差が最初に出た内部サンプル | 固定上流とのPCM最大絶対差 |
| --- | ---: | ---: | --- | ---: |
| 公式デモ先頭 48 kHz | 249,600 | 3,903 | 肺流量の1 | `9.31×10⁻¹⁰` |
| 切り替え 44.1 kHz | 65,000 | 65,000 | 肺流量の386 | `4.55×10⁻¹³` |
| 音高上限 96 kHz | 81,792 | 1,283 | 口端流量・総放射の64 | `3.64×10⁻¹²` |

公式デモ先頭の最初のPCM差は出力73,414。先行する持続音・停止・`bellow` に計6差分フレームがあり、`growl` 開始後の52,800フレームは固定上流とビット一致した。44.1 kHzの最初のPCM差は出力51,367で1件、96 kHzは29,069から計2件だった。[固定上流との差](../runs/worklet-alligator-growl-20261120-a/summary.json)

### 手動目標と声門への伝達

44.1 kHzの切り替え指示23,617で、音高目標は31 Hz、`hiss` の目標は0.62へ戻り、63フレームの間、平滑値は直前のまま進んだ。制御境界23,680で音高目標は70 Hz、ゲート目標は1から0.6、平滑 `hiss` は0から0.02209に進んだ。27,137で `hiss` と呼気圧の目標だけが即時に変わり、平滑 `hiss` は27,200で0.53571から0.51840に下がった。52,352の自然終了では音高32 Hz・粗さ0.27・口0.26が手動目標に戻った。[切り替えと編集の全観測](../runs/worklet-alligator-growl-20261120-a/summary.json)

先行する手動 `hiss` を0にしたCLI対照との差は、目標で23,617、平滑値で23,680。その制御境界に対応する内部47,360で声門面積と声門流量が分かれ、次の内部サンプル47,361で声門差圧・壁面・総放射に差が出た。口端は内部47,443、鼻端は47,446で差が出た。PCMがビット単位で初めて異なったのは出力23,682で、`1e-6` を初めて超えたのは23,693。制御上のゲート・音高、肺圧、口先・軟口蓋の実断面は対照と一致した。声門の有声ゲートが初めて違ったのは内部48,073で、最初の放射差はその前に観測された。[対照の入力](../runs/worklet-alligator-growl-20261120-a/artifacts/switch-hiss-zero-case.json)・[系列別の最初の差](../runs/worklet-alligator-growl-20261120-a/summary.json)

### 共通化後の回帰

照合手順を共通化した直後は、`bellow` の継承先1件を示す文字列を配列として走査し、先頭1文字をファイル名として開いて失敗した。文字列は1件、配列は記載順の複数件として読むようにした。次の回帰では、44.1 kHzの追加判定に内部レートの倍率を渡していなかったため、ブラウザからデータを取得した後に判定が停止した。観測した出力フレーム数と内部サンプル数から倍率を求めて判定へ渡した。[継承読み込みの失敗](../runs/worklet-alligator-bellow-growl-regression-20261120/manifest.json)・[倍率の受け渡しの失敗](../runs/worklet-alligator-bellow-growl-regression-20261120-retry/manifest.json)・[共通の照合手順](../tools/measure_worklet_alligator_call.py)・[bellowの追加判定](../tools/measure_worklet_alligator_bellow.py)

修正後の `bellow` は234項目を通過した。71,383観測行、WASM、再生ケース、ブラウザWAV、CLIのWAV・CSVの計13ファイルが変更前と一致した。Rustの整形確認、Clippy、ワークスペースの試験33件も通過した。[修正後の回帰](../runs/worklet-alligator-bellow-growl-regression-20261120-final/manifest.json)

### 実時間と再実行

`growl` は研究ディレクトリと `/tmp` の両方で285項目を通過した。70,186観測行、WASM、各ケースのWAV・CSV・再生入力、`hiss` 対照の入力と出力の計16ファイルが一致した。44.1 kHzでコール切り替え、手動編集、自然終了を含むネイティブの割り当て計測は0回だった。128フレームの描画時間p95は48・44.1・96 kHzの順に2・2・1 msで、各予算2.67・2.90・1.33 msを下回った。計時は `Date.now` の1 ms刻みで行った。[固定上流とCLIの基準](../runs/alligator-growl-before-worklet-1/manifest.json)・[ブラウザ初回](../runs/worklet-alligator-growl-20261120-a/manifest.json)・[修正後の再実行](../runs/worklet-alligator-growl-20261120-final/manifest.json)

固定上流のディレクトリで `cargo test --locked --release -p chimera --test golden_creatures --test creature_realtime` を実行した。波形・テレメトリの4件とキー解決・実時間の3件が通過した。[波形とテレメトリの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs)・[実時間の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs)
