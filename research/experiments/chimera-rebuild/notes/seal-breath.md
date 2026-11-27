# ウェッデルアザラシの呼気パルス

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。今回は、ウェッデルアザラシの演奏制御から肺の固定圧力境界までを照合する。[事前登録](../cases/seal-breath.json)

## 呼び出しと式

上流CLIの `render creature seal` は種の定義から `CreatureVoice` を作り、持続音と停止、各コールを出す。アザラシは通常2倍で内部計算を行い、出力60 kHz超では内部と出力が同率。制御間隔 `Δt=64/fs_out` はどちらでも64出力フレームに相当する。`CreatureVoice::new` はゲート0で `Seal::control` を1回呼ぶため、初期位相0の振動子が、最初の出力フレームをレンダーする前に1制御周期進む。[CLIの持続音とコール](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[制御の初期化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L148)

演奏の目標値は次の制御境界で読み、呼気ゲートを立ち上がり6 ms、立ち下がり30 msで更新する。パルス周波数は比率による平滑化、深さ・デューティ比・呼気圧は値の差による平滑化を行う。平滑化の時定数は周波数・深さ・デューティ比が20 ms、呼気圧が10 ms。手動ゲート指示は0〜1.5に制限する。ここでパルス周波数は、声門振動の基本周波数と別の制御量。[演奏値の適用](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L214)・[平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[種ごとの時定数と範囲](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L89)

`Seal::control` は無次元位相 `φ` にパルス周波数（Hz）と `Δt` の積を加え、その整数部分を引く。更新後の `φ` がデューティ比 `d` 未満なら `h=sin(πφ/d)`、それ以降は0。深さを `m` とするとパルス倍率は `1−m+mh`。肺の境界圧は `P_cmH2O×980.665×g×(1−m+mh)` dyn/cm² で、`g` は平滑化した呼気ゲート。呼気の指示と深さが0でも位相は進む。肺圧を設定した後に声門パラメータと声道断面を更新し、各内部サンプルで `step_glottis` が声門前後の圧差から開口を計算する。肺の値は制御区間の固定圧力で、声門流量は後段の計算に属する。[パルスと圧力の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[換算係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L65)・[肺と声門の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L51)

## 事前の予測

位相が均一に進む1周期で、半正弦の平均は `2d/π`、パルス倍率の平均は `1−m+2md/π`。デューティ比0.15と1の対照で平均と活動時間を測り、深さ0でゲートと圧力の積だけが残ることを調べる。位相増分が1/16になる条件では、折り返し、半正弦の頂点0.25と終端0.5を同じ制御格子で観測できる。44.1 kHzで制御境界の途中に置いた変更と再始動、96 kHzの無呼気も登録した。固定上流の `golden_creatures` はアザラシの持続、制御変更、コール、停止を波形とテレメトリで照合し、`creature_realtime` は実時間の割り当てを検査する。[測定区間と許容差](../cases/seal-breath.json)・[上流の波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[上流の実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 実装と実測

`SealBreath` は演奏パラメータを平滑化し、制御フレームごとの位相と固定肺圧を返す。比較プローブは上流の `CreatureVoice::render` 自体を実行し、公開された `sim.net().p` の `lungs` 節点を読む。肺と気管をつなぐポートとは別の節点で、上流はここに制御値を代入する。非公開のパルス位相と包絡は、前回値の残存率で制御値を求め、周波数の積分から位相を算出する独立計算で照合した。上流実装の利用条件は MIT。[再実装](../crates/vocal-core/src/seal_breath.rs)・[上流比較プローブ](../tools/upstream_seal_breath_probe.rs)・[肺の節点とポート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L51)・[ライセンス](../LICENSE-CHIMERA)

44.1・48・96 kHzの7条件、計3,901制御フレームで、固定上流の肺圧、ゲート、平滑化した4パラメータは再実装と全値が一致した。48 kHzの標準条件では、初期化で位相0.024、フレーム0で0.048になり、初回の肺圧は1,099.09 dyn/cm²。96 kHzの無呼気では256制御フレームで肺圧0を維持し、位相は3回折り返した。1/16刻みでは位相0、0.25、0.5を各8回観測し、倍率は順に0、1、0だった。[128項目の判定と全数値](../runs/seal-breath-20261120-b/summary.json)

| 48 kHzの定常条件 | 500制御フレームでの平均倍率 | 連続時間の式 | 半正弦区間の割合 |
| --- | ---: | ---: | ---: |
| 深さ0.6、デューティ比0.55 | 0.61007 | 0.61008 | 0.552 |
| 深さ1、デューティ比0.15 | 0.09540 | 0.09549 | 0.152 |
| 深さ1、デューティ比1 | 0.63659 | 0.63662 | 1.000 |

深さ0ではパルス倍率が常に1で、肺圧はパルス適用前の圧力と一致した。44.1 kHzで73、6,079、10,009、17,017フレームに出した指示は、順に128、6,080、10,048、17,024で制御に反映された。停止指示が反映された時点でも平滑ゲートは0.95278で、肺圧は77.31 dyn/cm²だった。再開指示のゲート2は目標1.5に制限された。[制御イベントの観測値](../runs/seal-breath-20261120-b/summary.json)

初回はデューティ比0.15の独立計算で通常の累積加算を使った。位相差は最大 `2.91×10⁻¹³` で、半正弦の位相勾配の上限 `π/d` が大きいため、圧力差は最大 `5.87×10⁻⁸ dyn/cm²` まで増えた。制御番号629（出力40,256フレーム）から許容差 `5×10⁻⁸ dyn/cm²` を超え、候補・上流それぞれと独立計算を比較した2項目が不合格だった。位相の積分に補償加算を使うと、この条件の圧力差は `1.92×10⁻⁹ dyn/cm²`、全条件の最大は `1.38×10⁻⁸ dyn/cm²` に収まり、128項目が通過した。ケース、しきい値、レンダーは同じものを使った。[初回の判定](../runs/seal-breath-20261120-a/summary.json)・[補償加算での判定](../runs/seal-breath-20261120-b/summary.json)

固定上流の既存試験7件が通過し、上流CLIで48 kHz・461,760フレームのモノラルf32 WAVを生成できた。候補の比較範囲は固定肺圧まで。次は気管と咽頭の圧差、声門開口、声門流量を内部サンプルごとに追い、肺のパルスが気道内の流れに伝わる時刻を調べる。[実行環境と出力ファイル](../runs/seal-breath-20261120-b/manifest.json)・[声門の結合順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L115)
