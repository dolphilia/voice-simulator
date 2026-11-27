# 実時間AudioWorkletでのアメリカアリゲーターの固定発声

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの種選択と呼気操作は `AudioEngine` から `creature` と `gate` をWorkletに送り、WASMの `engine_set_creature`、`engine_set_gate` を経て `CreatureVoice` に届く。公式CLIは同じモデルを1.2秒発声させて0.4秒減衰させた後、コールを再生する。ゴールデン試験は登録した操作位置でレンダーを区切り、波形・RMS・テレメトリ・分割長の同一性を確認する。実時間試験は通常の描画・操作で割り当てを数え、減衰試験は無励振時の微小状態を調べる。[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L130)・[種選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L465)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)・[減衰試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L187)

固定肺圧を気管と声門ポートから咽頭へつなぎ、咽頭末端で口腔と鼻腔へ分岐する。ゲート `g` は64出力フレームごとに `g += (目標−g) × (1−exp(−Δt/τ))` で更新する。時定数は立ち上がり12 ms、停止60 ms。肺境界の圧力は `pressure_cm_h2o × 980.665 × g` dyn/cm²。各内部サンプルは先に気管端と咽頭入口の差圧で声門面積（cm²）を更新し、その開口を使って気道の流量（cm³/s）と圧力を進める。口先断面は `0.05+12×mouth`、鼻腔ポートは `0.4+1.6×nostrils` cm²。口腔の終端セルを除く最小断面が2 cm²未満なら口腔の乱流源を登録する。`hiss=1` では声門振動振幅 `0.9×(1−hiss)` が0になり、静的開口は0.826 cm²へ近づく。壁・口端・鼻端の放射流量を合計して時間差分を取り、間引き、DC除去、振幅制限を経てf32 PCMになる。[アリゲーターの制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L24)・[気道と声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L51)・[更新順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[CLIの読解と第2版の実測](alligator-fixed-voice.md)

## 事前登録

第2版の5条件を使う。48 kHzの公式デモ先頭で内部0に肺圧、47に声門流、48に壁面、82に鼻腔ポート、139に口端、143に鼻端の開始を予測する。上流の固定姿勢で制御境界の微小値消去を省く対照では、口端128と鼻端132を予測する。口を広げると口先が6.05 cm²になって口腔乱流の登録が外れ、鼻孔最小でもポート面積0.4 cm²と鼻端放射は残る。44.1 kHzの `hiss=1` は指示73から次の制御128まで待ち、内部256から肺圧が生じる。無呼気の96 kHzは肺圧・流量・放射・PCMが0で、声門面積の指数応答を測る。各条件の開始後192出力フレームを連続観測する。96 kHzの無呼気は全フレームを採取し、他の条件の残りは64フレーム間隔と停止指示直前を保存する。CLIとビット単位のPCMおよび観測系列の差0を要求し、固定上流・独立計算の許容差は第2版を使う。[ブラウザ登録条件](../cases/worklet-alligator-fixed-voice.json)・[固定上流と独立計算の条件](../cases/alligator-fixed-voice-v2.json)

## ブラウザの実装と実測

既存の `AlligatorVoice` をC ABIから呼び、最大128出力フレームのバッファにPCMを保持する。各観測点ではゲート目標・平滑値、口腔乱流の登録、間引きとDC除去の値、内部サンプルごとの肺圧・声門・各放射など41列を保存する。内部倍率1の2番目の枠は0になる。共通の動物用Workletはイベントと観測窓で分割し、気道と制御の時計を引き継ぐ。画面の再実行ケースを変更せずCLIに渡し、全120,878 PCMフレームがビット一致した。比較できる観測値も全4,666点でCLIと一致し、ゲート目標・口先断面・乱流登録などは独立式でも確認した。[C ABI](../crates/vocal-wasm/src/alligator.rs)・[Worklet](../../../../web/prototypes/chimera-research/src/creature-processor.ts)・[比較器](../tools/measure_worklet_alligator_fixed_voice.py)

| 条件 | PCMフレーム・観測点 | 肺圧／声門流／壁面／鼻腔ポート／口端／鼻端の開始（内部サンプル） |
| --- | --- | --- |
| 48 kHz、標準の開始・停止 | 76,800・1,391 | 0／47／48／82／139／143 |
| 48 kHz、口を開く | 14,400・415 | 0／47／48／82／139／143 |
| 48 kHz、鼻孔最小 | 14,400・415 | 0／47／48／82／139／144 |
| 44.1 kHz、`hiss=1` | 13,230・397 | 256／299／300／331／373／376 |
| 96 kHz、無呼気 | 2,048・2,048 | 肺圧・流量・放射は0 |

48 kHzの標準条件で、壁面放射は内部48、PCMは出力24で最初に現れた。口端と鼻端の最初の非ゼロ値は、制御境界の `begin_block` を省いた上流の対照の128・132より両方とも11内部サンプル遅れた。これは内部96 kHzで約0.115 msで、その時刻に現れる流量は極小値だった。停止後の末尾RMSは発声区間の `2.96e-5` 倍だった。[到達位置と対照の比較](../runs/worklet-alligator-fixed-20261120-a/summary.json)・[制御境界と微小値の消去](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)

口を開く条件では口先断面6.05 cm²で口腔の乱流源が外れ、鼻孔最小の条件では鼻腔ポート0.4 cm²を通って鼻端放射が残った。44.1 kHzの `hiss=1` では肺圧が指示から55出力フレーム後に反映され、声門の発声ゲートは0のままだった。ブラウザで取得した開口面積は0.826 cm²への独立指数応答と一致した。96 kHzの無呼気でも0.026 cm²への静的開口を確認し、全PCMと肺圧・流量・放射は0だった。[条件ごとの観測と独立式](../runs/worklet-alligator-fixed-20261120-a/summary.json)

再実行の両条件で先頭192出力フレームの `nasal_cm3_s_0/1` を内部順に並べ、鼻端の始まりを追加集計した。標準と鼻孔最小で最初の非ゼロ値は内部143と144で、絶対流量はそれぞれ `9.24e-37` と `2.77e-36 cm³/s`。第2版の流量比較に使った絶対許容差 `2e-7 cm³/s` を横切る時刻は187と189だった。最初の非ゼロ値とは別に、同じ単位の閾値で立ち上がりを測ると差が2サンプルになる。この追加集計は到達判定を改訂せずに、別の指標として記録した。[標準のブラウザ観測](../runs/worklet-alligator-fixed-20261120-repeat/artifacts/official-sustain-48000.json)・[鼻孔最小のブラウザ観測](../runs/worklet-alligator-fixed-20261120-repeat/artifacts/minimum-nostrils-48000.json)

### 固定上流との差

標準では肺境界圧が一致し、最初の数値差は内部サンプル1の肺ポート流量で、声門流量47、壁面放射48にも差が現れた。声門位相と瞬時F0は一致した。公式デモ先頭のPCM差は停止後73,414の1フレームで `7.11e-15`。全5条件では3フレームに差があり、最大は口を開いた条件の `9.31e-10` だった。いずれも登録した出力の許容差内だった。[最初の差と最大差](../runs/worklet-alligator-fixed-20261120-a/summary.json)

### 実時間と再実行

研究ディレクトリと `/tmp` の両方で各86項目が通過した。WAV、CLIのCSV、書き出したケースとWASMの21ファイルのハッシュと、全観測行が一致した。48 kHzの標準のネイティブ描画は割り当て0。128フレーム量子は計測中に連続し、先頭8量子を除くp95は全条件で1 ms。計時には1 ms分解能の `Date.now` を使った。96 kHzは無呼気約21 msの短い条件で、先頭8量子を除く計時は8量子を対象とした。アザラシの持続音44項目と鳴禽のコール切り替え22項目の回帰も通過した。[初回](../runs/worklet-alligator-fixed-20261120-a/manifest.json)・[再実行](../runs/worklet-alligator-fixed-20261120-repeat/manifest.json)・[アザラシの回帰](../runs/worklet-seal-sustain-alligator-regression-20261120/manifest.json)・[鳴禽の回帰](../runs/worklet-songbird-switch-alligator-regression-20261120/manifest.json)

```bash
python3 tools/measure_alligator_fixed_voice.py alligator-fixed-local-1 --revision 2
python3 tools/measure_worklet_alligator_fixed_voice.py worklet-alligator-fixed-local-1 alligator-fixed-local-1
```
