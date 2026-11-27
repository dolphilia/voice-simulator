# 固定 /i/ の肺ポートから気管末端への圧力伝搬

## 読解と事前の予測

上流の [`HumanAirway::new`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L106) は肺を固定圧の境界節点にし、肺ポートで一様断面の気管とつなぐ。ポート抵抗は気管の特性インピーダンスの半分を使う。低周波で音響終端用の抵抗がそのまま呼気を減らすのを避けるため、[`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は前回のポート流量 `U_prev` の低域成分 `U_lp` を `U_lp + α(U_prev − U_lp)` として更新し、肺の基準圧に `R_excess × U_lp` を加える。単位は圧力が dyn/cm²、流量が cm³/s、流量に掛かる抵抗が dyn·s/cm⁵。研究版も [`FixedVoice::step_source`](../crates/vocal-core/src/voice.rs#L214) から [`Breath::step`](../crates/vocal-core/src/breath.rs#L121) に前回の肺ポート流量を渡し、今回の境界圧を求める。

[`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L955) は、この境界圧と各節点の更新前圧力を使って各枝を解く。通気中の駆動圧は `p_left − p_right + p_noise + M/dt`、線形係数は `L/dt + R`。保持する運動量 `M = L×U` は、口径と慣性が変わる場合に調整される。気管のような静的な直列区間では断面は一定で、両側の断面差から作る二次損失はゼロになる。流量を加減し、壁流出を引いた後、各セルの圧力を `p_next = p_prev + dt/C × U_net` で進める。肺ポートは気管内の直列枝より後に加算されるため、第0セルの収支では先に末端向きの流出を引く。声門側の端の流出には同じ内部点の声門流量を使う。

上流の [`the_port_moves_neither_the_folds_pressure_nor_their_effort`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L48) は定常に近い母音区間で声門下圧が所定範囲にあり、声帯の力みの初期値が保たれることを確認する。今回の観測は、ゲート直後の過渡リプレイでその圧の伝わり方を追う。先行実験で8,213点目に観察した枝の左圧差を手がかりに、肺境界から気管末端までを同じ内部番号で並べる。先行の4点はゲート開放前でゼロと予測し、開放後の最初の流量差を作る変数を置換して調べる。[事前登録](../cases/fixed-voice-tracheal-onset-48000.json)

## 最初の差は気管の最初の直列枝で生じる

固定 `/i/` を出力48 kHz、内部96 kHzで描画し、出力4,096フレーム目にゲートを開いた。先頭の4,120出力フレームのうち、内部8,188〜8,239点目を採取した。計測用の隔離ビルドで、肺側から0〜12の13セルと各セルへ入る枝を記録した。枝0は肺ポート、枝1はセル0からセル1へ向かう最初の直列枝。ゲート開放前の4点では圧力と流量はすべてゼロだった。先行実験の計測行と描画出力は保存済みデータと一致した。

| 観測された初差 | 内部サンプル |
| --- | ---: |
| 最初の直列枝の流量とセル1の更新後圧力 | 8,196 |
| 気管入口のセル0の更新後圧力 | 8,199 |
| 肺ポートの流量 | 8,202 |
| 末端の一つ手前のセル11の更新後圧力 | 8,213 |
| 声門手前の末端セル12の更新後圧力 | 8,216 |
| 肺ポートで読む固定圧境界 | 8,220 |

8,196点目の枝1は左右の圧力、前回流量 `0.07259206065414107` cm³/s、慣性 `0.0004209230769230769` g/cm⁴、慣性と抵抗を足した線形係数 `40.4264911920194` が一致した。抵抗の丸め差は線形係数の値には残らなかった。

研究版の持ち越し圧は `(L/dt)×U_prev = 2.933344658949858` dyn/cm²、上流は `(L×U_prev)×Fs = 2.9333446589498586` dyn/cm²。各演算を二進64ビットへ丸めてこの差を復元した。持ち越し圧だけを上流値に替えると、流量が `0.14451558366174816` から上流の `0.1445155836617482` cm³/s に一致した。同じ内部点で、その流入をセル1の体積収支へ入れると、更新後圧力は上流の `1.409117402697833` dyn/cm² に一致した。肺境界の圧力差はこの24点後に現れた。[全セル・全枝の初差と局所置換](../runs/fixed-voice-tracheal-onset-48000-b/summary.json)

次はこの直列枝だけの運動量換算を上流順にした隔離ビルドで、最初の差が解消するか、圧力とPCMの次の差がどこへ移るかを観測する。

## 実行と検証

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_tracheal_onset.py fixed-voice-tracheal-onset-48000-b

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_tracheal_onset.py" \
  fixed-voice-tracheal-onset-48000-repeat
```

初回 `-a` は研究版の観測コードで、照合すべき節点番号と探索中の節点番号を同じ変数名にしていた。節点0の重複と他の節点の欠測を検出し、実行を不合格として保存した。変数名を分けた `-b` では全13セルの52点を取得できた。ケース定義と判定条件は初回から同じものを使用した。[初回の失敗マニフェスト](../runs/fixed-voice-tracheal-onset-48000-a/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で `-b` と `-repeat` の各8判定と固定上流の各9試験が通過した。各実行について両版の節点1,352点と枝1,352点を有理数および十進数で再計算した。採取CSV、上流PCM、計測差分を含む13出力がバイト一致した。上流プローブの実行ファイルのハッシュは再ビルド間で異なり、計測値と判定を含む要約のその他の項は一致した。成功した2実行の360入力と40出力をハッシュ照合し、採取物7,339,349バイトをRTL9210B-CGに保存した。節点テーブルの読み出しには `trachea_outflow` を使う。局所置換結果には、末端収支と同じ計算器を使ったときの互換名 `glottal_outflow` も併記される。[再実行マニフェスト](../runs/fixed-voice-tracheal-onset-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-onset-48000.json)
