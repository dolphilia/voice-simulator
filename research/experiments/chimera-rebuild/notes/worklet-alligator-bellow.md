# 実時間AudioWorkletでのアメリカアリゲーターの `bellow`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの呼び声の再生・停止から `AudioEngine` が `call`・`stopCall` を送る。Workletはコール名を索引にし、WASMの `engine_play_call`・`engine_stop_call` を呼ぶ。`cparams` は手動演奏値を更新する。公式CLIは持続・停止から同じモデルの状態を引き継ぎ、48 kHzの76,800フレームで `bellow` を始める。上流の `alligator-call-bellow` は104,160フレームを描画し、PCM・RMS・内部観測とホスト分割の影響を調べる。実時間試験は操作・描画・テレメトリの割り当て、キーの解決を検査する。[画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

64出力フレームごとに時計（秒）からキーを評価する。ゲートは0.15秒で1、1.6秒まで保持、2秒で0に戻る。音高の目標は30→24 Hz、粗さの目標は0.55→0.95に1.6秒で直線変化する。移調は基準28 Hzに対する比を音高だけに掛け、12〜120 Hzに制限する。ゲートは呼気倍率を掛けてから手動値との大きい方を採る。コールは音高、粗さ、口、`hiss` の目標を所有し、停止で手動値へ戻す。肺圧（dyn/cm²）は平滑呼気圧（cmH₂O）・換算係数980.665・平滑ゲートの積。口と鼻腔の断面はその制御ブロック内で補間するが、口腔乱流源の登録はブロック終点の目標断面で決める。[上流のキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L102)・[手動目標と所有](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)・[気道の更新と乱流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L77)

平滑粗さ `c` と写像の状態 `x` は声門の位相が一周したときに周期長倍率を更新する。`x ← (2.9+1.1c)x(1−x)` を進め、ジッターの乱数 `J` に `0.01+0.05c` を掛け、`0.45c(x−0.5)` とともに倍率1へ加える。内部レートを `fs` とすると、位相が一周した次の増分は `(f₀/fs)/L`。位相と瞬時F0（Hz）から `L` を復元できる。声門・気道の状態を更新した後、放射流量の差分、間引き、DC除去、振幅制限を経て加工前f32 PCMになる。[位相と写像](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L181)・[更新順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[CLIの読解と実測](alligator-bellow.md)

## 事前登録

48 kHzの公式デモ先頭、44.1 kHzの移調・手動変更・途中停止、96 kHzの音高下限を同じ入力で再生する。48・96 kHzは64出力フレームごとと開始・終了の前後、44.1 kHzは最初から全65,000出力フレームの内部2サンプルを観測する。9,901で呼気圧22 cmH₂Oと鼻孔0.25の目標が変わり、音高34 Hz・粗さ0.2・口0.35・`hiss=0.4` の目標は停止の53,107で戻ると予測する。ゲートは11,072で手動0.72が優先し、停止後の平滑値は53,120から変化する。44.1 kHzの位相から全周期の倍率を復元して独立の乱数列・写像と照合し、口腔乱流の登録・解除（内部1,664・108,672）と実断面が2 cm²を通過する順序を検査する。PCMのビット一致とCLIの観測差0を要求し、上流と独立計算の許容差は元ケースを使う。[ブラウザの登録条件](../cases/worklet-alligator-bellow.json)・[制御と周期倍率の条件](../cases/alligator-bellow.json)・[音響比較の閾値](../cases/alligator-fixed-voice-v2.json)

## ブラウザへの接続

研究用WASMのアリゲーターABIに手動目標、コール開始・停止を追加した。CLIと同じ合成器に、手動目標、ゲート、開始または停止の順で渡す。Workletはイベントと観測点で描画を分割する。コア側の64フレームごとの制御時計はそのまま進む。観測ABIの第2版では既存の41列に、コールIDと制御時計、6項目の平滑値と目標の計14列を加えた。固定発声では既存の41列を保存する。[WASMの操作と観測](../crates/vocal-wasm/src/alligator.rs)・[TypeScriptの受け渡し](../crates/vocal-wasm/host/alligator.ts)・[Workletの分割](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[照合手順](../tools/measure_worklet_alligator_bellow.py)

### 最初の乱流源登録で生じた割り当て

最初の実行は44.1 kHzの描画と操作で1回割り当てがあり、ブラウザ計測に進む前に不合格となった。次の実行では内部サンプル1,664を描く1出力フレームを個別に計測し、そのフレームに1回が集中することを確認した。合成器は登録内容を二つの可変長バッファに交互に書く。固定上流は両バッファを初期化時に確保する。再実装の動物気道も、声門と、対応する機種では口腔の乱流源を登録できる容量を両方に確保した。[最初の不合格](../runs/worklet-alligator-bellow-20261120-a/manifest.json)・[フレームを絞った計測](../runs/worklet-alligator-bellow-20261120-allocation-diagnostic/artifacts/cargo.log)・[上流の確保](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L427)・[動物気道の確保](../crates/vocal-core/src/airway/mammal.rs)

## 実測

Chromium 156.0.8078.4のAudioWorkletから保存した加工前PCMは、書き出したケースをCLIで再生した波形と全473,000フレームでビット一致した。同じCLIとブラウザの71,383観測点では、制御値と各内部サンプルの主な気道状態の最大差は0だった。固定上流・独立計算には再生時の同条件のCLI全系列を使い、ブラウザ側も44.1 kHzでは全内部サンプルから周期倍率を復元した。[初回の測定値と判定](../runs/worklet-alligator-bellow-20261120-b/summary.json)

| 条件 | 出力フレーム | 観測点 | 開始指示 / 最初の制御 / コール解除（出力フレーム） | 固定上流とのPCM最大絶対差 |
| --- | ---: | ---: | --- | ---: |
| 公式デモ先頭 48 kHz | 196,800 | 3,078 | 76,800 / 76,800 / 175,232 | `9.31×10⁻¹⁰` |
| 手動操作と途中停止 44.1 kHz | 65,000 | 65,000 | 73 / 128 / 53,107 | 0 |
| 移調時の音高下限 96 kHz | 211,200 | 3,305 | 17 / 64 / 196,928 | `7.28×10⁻¹²` |

固定上流との最初の数値差は、48 kHzで内部1の肺流量、44.1 kHzで内部257の口端流量・総放射、96 kHzで内部129の肺流量に現れた。PCMの最初の差は48 kHzで出力73,414、96 kHzで47,540。公式デモ内の `bellow` 区間では開始から17,150フレーム後に最初のPCM差があり、120,000フレームのうち5サンプルのビットが異なった。各差は登録した許容差内だった。[差の時刻と最大差](../runs/worklet-alligator-bellow-20261120-b/summary.json)

### 所有の解除と周期長

44.1 kHzの9,901で肺圧・鼻孔の目標は手動値に変わり、音高・粗さ・口・`hiss` の目標はコールに従い続けた。11,072から手動ゲート0.72が優先した。途中停止の53,107でコールIDは0、粗さ目標は約0.85005から0.2へ戻った。平滑粗さは約0.83773を保持し、次の制御境界53,120で約0.81948へ変わった。96 kHzでは10 Hzを指定した移調の目標に12 Hzの下限が適用された。[停止前後の全演奏値](../runs/worklet-alligator-bellow-20261120-b/summary.json)

44.1 kHzのブラウザで、声門位相から復元した56周期の倍率は、独立の乱数列とロジスティック写像から得た倍率と最大差 `2.22×10⁻¹⁶` で一致した。CLIの3条件合計では189周期を同じモデルで照合した。48 kHzのコール中、写像由来の倍率成分のRMSは0.3〜0.7秒で0.08188、1.2〜1.6秒で0.13237だった。[周期倍率と区間集計](../runs/worklet-alligator-bellow-20261120-b/summary.json)

### 口腔乱流源の切り替えと実断面

44.1 kHzのコールでは、口先の実断面が2.03363 cm²の内部1,664で乱流源が登録され、実断面は87サンプル後の1,751で2 cm²を下回った。停止後は断面が1.96915 cm²の内部108,672で登録が外れ、61サンプル後の108,733で実断面が閾値以上になった。先行時間は内部88.2 kHzで約0.99 msと0.69 ms。乱流源の登録状態と瞬時の流量から決まる雑音の強さは別の観測値である。実断面を判定に使う対照で、乱流の注入圧と口端放射の差がどこから出るかを調べられる。[断面と登録の観測](../runs/worklet-alligator-bellow-20261120-b/summary.json)

### 実時間と再実行

事前登録した234項目を研究ディレクトリと `/tmp` の両方で通過した。44.1 kHzのネイティブ割り当て計測は初回の乱流源登録フレームと全区間で0回だった。処理時間は128フレームの量子を `Date.now` で測った。初回のp95は48・44.1・96 kHzの順に2・2・1 msで、各予算の2.67・2.90・1.33 msを下回った。1 ms刻みの計時で96 kHzの余裕は細かく分解できない。[初回の計測](../runs/worklet-alligator-bellow-20261120-b/manifest.json)・[別ディレクトリからの再実行](../runs/worklet-alligator-bellow-20261120-repeat/manifest.json)

再実行でもp95は2・2・1 ms、71,383観測行は一致した。3条件のブラウザWAV、再生ケース、CLIのWAV・CSVとWASM、計13ファイルのSHA-256が一致した。CLIのWAV・CSV計6ファイルはバッファ確保前の基準実行とも一致した。[修正前の基準](../runs/alligator-bellow-before-worklet-1/manifest.json)・[再実行の要約](../runs/worklet-alligator-bellow-20261120-repeat/summary.json)

アリゲーターの固定発声86項目、アザラシの持続音44項目、ゾウの公式デモ末尾までの361項目が通過した。固定発声の計測ファイル20件と4,666観測行、アザラシの8件と2,116観測行、ゾウの34件と結果要約がそれぞれ変更前と一致した。Rustでは `cargo fmt --all --check`、`cargo clippy --locked --workspace --all-targets -- -D warnings`、`cargo test --locked --workspace --release` を実行し、試験32件が通過した。[固定発声の回帰](../runs/worklet-alligator-fixed-bellow-regression-20261120/manifest.json)・[アザラシの回帰](../runs/worklet-seal-sustain-bellow-regression-20261120/manifest.json)・[ゾウの回帰](../runs/elephant-squeak-bellow-regression-20261120/manifest.json)
