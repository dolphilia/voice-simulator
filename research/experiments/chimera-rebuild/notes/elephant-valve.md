# アフリカゾウの鼻の入口弁と発声モード

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `CreatureVoice::control` は64フレームごとに演奏値を平滑化して `Elephant::control` に渡す。演奏値 `mode` は線形で時定数0.03秒、`lipPitch` は対数空間で0.02秒。声門開大は `0.05+3m` cm²、振幅は `1.6(1−m)` cm²、声門の乱流係数は `4×10⁻⁷(1−m)` になる。入口弁の中心周波数を `lipPitch` とし、減衰比0.08、静止隙間0.003 cm、幅2.4 cm、有効受圧面積÷質量40 cm²/gを使う。声門の振動と鼻の弁の振動を一つの連続したモードで制御する。[演奏値の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)・[ゾウの制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)

`LipReed::next` は差圧 `p`（dyn/cm²）を受け、変位 `h`（cm）、速度 `v`（cm/s）を保持する。固有角周波数 `ω=2πf` として加速度は `40p−2ζωv−ω²(h−h₀)`。半陰的オイラー法で先に `v` を進め、更新後の速度で `h` を進める。変位が−0.05 cm未満または0.8 cm超なら境界へ戻し、外向きの速度をゼロにする。自由開口は `w max(0,h)` cm²。変位と速度はゼロから始まる。上流の `valves_match_typescript` には開口だけを比較する弁単体の差圧系列があり、`elephant-held` は気道内の手動モード切り替えをPCMとテレメトリで比較する。[弁の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/valves.rs#L10)・[弁の固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L216)・[動物音声の固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)

`Elephant::sample` はまず声門の開口を更新する。モード `m>0.02` では前サンプルの鼻の基部圧と鼻の管の入口圧の差を `m` 倍して弁に与え、実断面を `max(自由開口, 4.5(1−m))` cm²にする。閾値以下では弁の状態を保持し、管には4.5 cm²を設定する。続いて気道の圧力・流量を進め、壁、口端、鼻端の放射流量の差分をPCMへ送る。テレメトリの弁は `min(1, 自由開口/1.2)` なので、面積下限を含む実断面と別に観測する。[サンプル更新とテレメトリ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L94)・[放射経路と出力段](elephant-fixed-voice.md)

## 事前登録

弁単体は一定差圧の線形区間を行列計算で再現し、静止釣り合い `h₀+40p/ω²` と、強い正負の差圧での衝突を照合する。気道では48 kHzのモード1、44.1 kHzの手動切り替えと面積下限、96 kHzの高い弁音高を比べる。差圧には同一フレームの更新前の圧力を使い、開口、声門の制御、実断面、放射、PCMを段ごとに比較する。[登録した入力・観測区間・許容差](../cases/elephant-valve.json)

## 実装と実測

弁単体の状態を `render` で記録し、同じ弁をゾウの気道に接続した。乱流の利得を更新するときは、同じ音源のフィルタ状態と乱数列を保つ。固定上流プローブは実発声の実断面と正規化した自由開口を読み取り、同じ差圧を上流の `LipReed` で再演した自由開口と照合する。変位・速度の比較は別に組んだ状態行列で行った。[弁単体の実装](../crates/vocal-core/src/lip_reed.rs#L71)・[気道との接続](../crates/vocal-core/src/airway/elephant.rs#L334)・[固定上流プローブ](../tools/upstream_elephant_probe.rs)・[独立計算](../tools/measure_elephant_valve.py)

48 kHzの差圧ステップ3,200フレームで、自由開口は固定上流と一致した。独立計算との差は、変位が最大 `3.33×10⁻¹⁶ cm`、速度が `1.36×10⁻¹² cm/s`。400 dyn/cm²の静止釣り合いは0.00483470 cmで、観測窓の平均は0.00483386 cmだった。負圧ステップ後の2,414で下限−0.05 cm、正圧ステップ後の2,818で上限0.8 cmに当たり、そのサンプルで外向きの速度がゼロになった。[弁単体の判定](../runs/elephant-valve-20261120-a/summary.json)

| 気道の条件 | 自由開口の最大・最小差 | 鼻先流量のRMS | 上流との最大PCM差 |
| --- | ---: | ---: | ---: |
| 48 kHz、470 Hzの弁でモード1 | `2.38×10⁻⁶ cm²` | 977.36 cm³/s | `1.16×10⁻¹⁰` |
| 44.1 kHz、手動モード切り替えの後半 | `2.78×10⁻³ cm²` | 745.17 cm³/s | `3.73×10⁻⁹` |
| 96 kHz、850 Hzの弁でモード1 | `2.28×10⁻⁵ cm²` | 298.75 cm³/s | `1.16×10⁻¹⁰` |

各値はケースに登録した窓で測った。48 kHz・470 Hzでは鼻先流量の平均が977.36 cm³/s、平均を除いたRMSは0.00239 cm³/s、自由開口の平均は0.19781 cm²だった。この固定条件では大きな定常流が持続し、開口と流量の変動は小さかった。[観測窓の判定](../runs/elephant-valve-20261120-a/summary.json)・[48 kHzの観測値](../runs/elephant-valve-20261120-a/artifacts/held-valve-48000/pcm-128.csv)

44.1 kHzでは5,952で平滑モードが0.00742から0.03304へ上がって弁を駆動し始め、実断面は4.5から4.35131 cm²へ切り替わった。12,352では自由開口0.01138 cm²に対して実断面は2.04344 cm²だった。35,136でモードが閾値を下回ると、自由開口0.00720 cm²、変位、速度を保持したまま、実断面は4.40614から4.5 cm²へ戻った。自由開口の上限は `2.4 × 0.8 = 1.92 cm²` なので、モードが約0.573以下の有効区間では面積下限が自由開口以上になる。[モード別の判定](../runs/elephant-valve-20261120-a/summary.json)・[44.1 kHzの時系列](../runs/elephant-valve-20261120-a/artifacts/mode-switch-44100/pcm-128.csv)

## 残る差と再現

気道3条件の候補と上流で自由開口の最大差は `7.22×10⁻¹⁶ cm²`、鼻先流量の最大差は `2.36×10⁻¹¹ cm³/s` だった。48 kHzでは最初の上流との差がフレーム1の肺流量に現れ、弁の駆動差圧は83、自由開口は131、PCMは4,634で初めて異なった。44.1 kHzと96 kHzの最初の差も、それぞれ4と129の肺流量にあった。独立計算では全3レートで、候補の前サンプルの圧力から求めた弁の駆動差圧と面積下限込みの実断面が候補の観測と一致した。[最初の差と各段の最大値](../runs/elephant-valve-20261120-a/summary.json)

研究ディレクトリと `/tmp` からの実行は各216項目を通過した。要約とWAV・CSV・JSONの計測ファイル28件が一致した。`rumble` と固定発声の回帰でも要約と計測ファイルが変更前に一致した。[初回のコマンドとSHA-256](../runs/elephant-valve-20261120-a/manifest.json)・[再実行](../runs/elephant-valve-20261120-repeat/manifest.json)・[rumbleの回帰](../runs/elephant-rumble-valve-regression-20261120/manifest.json)・[固定発声の回帰](../runs/elephant-fixed-voice-valve-regression-20261120/manifest.json)
