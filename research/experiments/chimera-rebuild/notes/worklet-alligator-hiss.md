# 実時間AudioWorkletでのアメリカアリゲーターの `hiss`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryのコール再生と演奏値の編集は、`AudioEngine` からWorkletの `call`・`cparams`、WASMの `engine_play_call`・`engine_creature_param` を経て同じ `CreatureVoice` に届く。公式CLIは持続音から同じ声門・気道・フィルタを保ち、48 kHzの249,600で `hiss` を始める。固定試験の単発 `alligator-call-hiss` は70,560フレームのPCMと区間RMS・テレメトリを照合し、実時間試験はキーの解決、再生・編集・停止と観測中の割り当てを検査する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Workletの操作](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASMの操作](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

64出力フレームごとにゲートと所有項目を更新する。`hiss` のキーは開大指示1→0、口0.9→0.02を1.3秒で線形補間し、ゲートは0.1秒で1、1.2秒まで保持して1.3秒で0に戻る。所有は最後のキーから50 ms経過後の制御境界で解除される。指定音高を掛けるキーがないため、`growl` から切り替えると旧コールの音高・粗さは手動目標に復帰する。平滑開大指示を `h` とすると声門開大は `0.02+0.8h` cm²、声門振幅は `0.9(1−h)` cm²。開大による抑制は有声ゲートに作用する。口先目標は `0.05+12·mouth` cm²。口端セルを除く最小の正の目標断面が2 cm²未満なら、対応する枝に口腔乱流源を登録する。気道がその断面に達するまでには内部レートでの補間が残る。[コールのキーと開大](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)・[所有と制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)・[有声ゲート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱流源の登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L77)

内部サンプルの乱流計算は直前の枝流量 `U`（cm³/s）と断面 `A`（cm²）を使う。`Re=2|U|/(ν√(πA))` が1,800を超えた場合、`q=Re²−1800²` として声門係数を `6×10⁻⁶√(96000/fs)·q/(1+q/(12000²−1800²))` とする。各登録源は係数0でも一様乱数を毎サンプル1個ずつ取り、声門源は口腔源より先に取る。250 Hzの一次ハイパスと4,000 Hzのローパス2段を通した波形を係数でスケールし、順方向の枝へ加えて逆方向では反対側の枝から引く。観測する注入圧と乱流レベルは dyn/cm²。登録が変わっても残った声門源のフィルタ状態は保持する。放射は枝と節点を更新した後で計算し、間引き・DC除去・振幅制限を経て単精度PCMを出す。[乱流源の状態更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L785)・[乱流係数と圧力注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[CLIの読解と実測](alligator-hiss.md)

## 事前登録

48 kHzの公式順序、44.1 kHzの `growl` からの切り替え、96 kHzの単独コールを再生する。各条件の出力をCLIとビット一致、観測値を最大差0で照合する。固定上流と独立式には既登録の許容差を使う。口腔乱流の登録と実断面を2 cm²の両側で確認できるよう、登録・解除を含む制御ブロックを全内部サンプルで観測する。44.1 kHzでは19,009で手動音高55 Hzに戻り、19,072のコール最初の制御でも55 Hzを保ち、24,001で60 Hzへ目標が変わると予測する。

96 kHzでは最初から109,568フレームを連続観測し、各サンプルの乱流レベルと注入圧を独立計算する。開始0.4〜0.7秒は口腔源が外れ、有声ゲートは `1e-8` 以下で、声門注入圧とPCMが残ると予測する。乱流を消した固定上流の同区間ではPCM RMSがブラウザの0.1倍以下になる。乱数を各サンプル2個ずつ消費する仮定の対照では同じ流量・面積を使い、声門乱流レベルを保つ。注入圧の差が `1e-6 dyn/cm²` を超えるのは、最初の口腔源解除の次サンプルから測定窓の開始までの間と予測する。開始0.7秒後から有声ゲート0.5への回復時刻を探し、放気のゲート目標が解放に入る前か確かめる。[ブラウザの登録条件](../cases/worklet-alligator-hiss.json)・[上流と独立計算の登録条件](../cases/alligator-hiss.json)

## ブラウザへの接続

WASM観測形式の第3版は、既存の55列の後ろに、内部サンプルごとの声門乱流レベル・枝への注入圧・口腔乱流レベルを6列追加した。ブラウザで乱流の観測を指定すると、登録に関係する口・`hiss` の制御値も出る。固定発声と既存コールの観測には従来の列を使う。Web画面から保存したケースをCLIで再生し、加工前PCMと内部状態を直接照合する。基準の固定上流は同じ入力の観測CSVと公式デモのWAV、乱流倍率0の対照で確認する。[WASMの観測](../crates/vocal-wasm/src/alligator.rs)・[かたちと単位の対応](../crates/vocal-wasm/host/alligator.ts)・[再生画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[ブラウザの比較手順](../tools/measure_worklet_alligator_hiss.py)

## 実測

Chromium 156.0.8078.4で保存した加工前PCMは、48・44.1・96 kHzの全558,800フレームでCLIとビット一致した。116,978観測点の状態は、追加した乱流3系列を含めてCLIとの差が0だった。公式 `hiss` 区間86,400フレームで固定上流との差は最大 `5.68×10⁻¹⁴` だった。公式デモ先頭からの比較では、先行する保持音の内部1で肺流量に最初の差があり、PCMの最大差は `9.31×10⁻¹⁰`。44.1・96 kHzの最初の差は内部256・64の口端流量と総放射にあり、PCMの最大差はそれぞれ `2.27×10⁻¹³`、`3.73×10⁻⁹`。各差は登録した許容差内だった。[結果と差の発生箇所](../runs/worklet-alligator-hiss-20261120-a/summary.json)

44.1 kHzでは切り替えの19,009で手動音高55 Hzが復帰し、19,072でも55 Hzを保持した。再生時に指定した110 Hzは目標へ入らず、24,001の手動編集で60 Hzへ変わった。平滑音高が次に動いたのは24,064。自然終了78,656では手動の口0.25と `hiss=0.17` が目標に戻った。[制御と目標の記録](../runs/worklet-alligator-hiss-20261120-a/summary.json)

### 口腔乱流源の切り替え

どの条件も、口腔乱流源は実断面が2 cm²を通過する前に、制御時の目標断面に従って切り替わった。表は内部サンプル番号で、48・44.1 kHzは各出力フレームに内部サンプルが2つある。[ブラウザで測った切り替えと断面](../runs/worklet-alligator-hiss-20261120-a/summary.json)

| 条件 | 解除 → 断面の上向き通過 | 解除の先行 | 再登録 → 断面の下向き通過 | 再登録の先行 |
| --- | --- | ---: | --- | ---: |
| 48 kHz | 499,968 → 500,051 | 83 | 608,640 → 608,655 | 15 |
| 44.1 kHz | 38,144 → 38,218 | 74 | 138,624 → 138,711 | 87 |
| 96 kHz | 896 → 915 | 19 | 109,440 → 109,486 | 46 |

### 乱数の消費順と無声区間

96 kHzの連続109,568サンプルで、ブラウザから得た流量・開口・口腔源の登録状態を使って声門乱流を独立に計算した。レベルの差は0、声門注入圧の最大差は `8.53×10⁻¹³ dyn/cm²`。乱数を常に2個消費する対照では、口腔源を外した896以降も2個ずつ進めたため、注入圧は1,444で最初に `1e-6 dyn/cm²` を超えて分かれた。開始0.4〜0.7秒の注入圧の誤差RMSは208.95 dyn/cm²で、実測した注入圧のRMSは149.41 dyn/cm²だった。同じレイノルズ数を使う乱流レベルは両方の計算で一致した。[独立計算と一定消費の対照](../runs/worklet-alligator-hiss-20261120-a/summary.json)

同じ0.4〜0.7秒で有声ゲートと口腔乱流レベルは0だった。通常のブラウザPCM RMS 0.11869に対し、乱流倍率を0にした固定上流の対照では `4.16×10⁻⁵`、通常値の約0.035%だった。有声ゲートが0.5に戻ったのは出力109,418で、その時点のゲート目標は1。口腔源が再登録される22サンプル前、ゲートが解放に入る約61 ms前だった。[無声区間と有声ゲートの回復](../runs/worklet-alligator-hiss-20261120-a/summary.json)

連続観測の `glottal_noise_pressure_dyn_cm2_0` を先頭から読み、0以外になった最初のサンプルも1,444であることを確認した。乱数の位置がずれ始めるのは口腔源を解除した次の897で、注入圧に差が見えるのは声門の流れが乱流係数を生じた時点だった。[96 kHzの連続観測JSON](../runs/worklet-alligator-hiss-20261120-repeat/artifacts/standalone-96000.json)

### 実時間と再実行

固定上流とのCLI基準は280項目、ブラウザ比較は研究ディレクトリと `/tmp` で各311項目を通過した。116,978観測行、3条件のブラウザWAV・書き出しケース・CLI WAVとCSV、WASMの計13ファイルは同一だった。CLIの音声と観測CSVの計6ファイルは変更前の基準実行とも一致した。処理時間のp95は48・44.1・96 kHzの順に2・2・1 msで、各予算2.67・2.90・1.33 msを下回った。Worklet内の計時は `Date.now` の1 ms刻みだった。ネイティブで96 kHzの解除・再登録を含む区間の割り当ては0回だった。[固定上流とのCLI基準](../runs/alligator-hiss-before-worklet-1/manifest.json)・[ブラウザの別ディレクトリからの再実行](../runs/worklet-alligator-hiss-20261120-repeat/manifest.json)

観測形式の拡張後も、固定発声86項目と `growl` の285項目が通過した。固定発声の20ファイルと4,666観測行、`growl` の対照を含む15ファイルと70,186観測行は、それぞれ変更前と一致した。Rustの整形確認、Clippy、ワークスペースの試験34件も通過した。[固定発声の回帰](../runs/worklet-alligator-fixed-hiss-regression-20261120/manifest.json)・[growlの回帰](../runs/worklet-alligator-growl-hiss-regression-20261120/manifest.json)
