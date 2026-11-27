# 固定 /i/ の気管末端圧を作る体積収支

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は、肺の境界圧を更新し、気管末端と咽頭入口の更新前圧力差を声帯モデルに渡す。求まった声門面積をポートに設定してから `AirwayNetwork::step` を呼ぶ。研究版の [`FixedVoice::step_source`](../crates/vocal-core/src/voice.rs#L214) もこの順序を使う。CLIの内部トレースが記録する `pressure_sub_dyn_cm2` は節点更新後の圧力なので、内部点 `n` の測定値を声門が読むのは `n+1`。上流プローブの通常トレースは出力1フレームにつき最後の内部点だけを記録する。

[`HumanAirway::new`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L106) は断面が一様な気管を作り、末端のセルを声門ポートの入口にする。末端には肺側の直列枝が1本入り、声門枝が1本出る。壁の運動もある。上流の [`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L903) と研究版の [`AirwayNetwork::step_with_prescribed_flow`](../crates/vocal-core/src/airway/network.rs#L680) は、まず断面変化の注入を加え、枝の流量を解いて流入を加算し、声門への流出を減算する。次に更新前圧力で壁の速度を進め、壁が外側へ動く分の流量を減算する。最後に非放射・非分岐の末端セルの圧力を進める。

このセルでは `U_net = ((U_volume + U_trachea) − U_glottis) − U_wall`、`p_next = p_prev + (dt / C) × U_net`。流量は cm³/s、圧力は dyn/cm²、`dt = 1/Fs` は秒。コンプライアンス `C = V/(ρc²)` は体積差/圧力差の比で、`V` は cm³、`ρ` は g/cm³、`c` は cm/s。上流の [`sealed_cavity_compression_follows_the_linearised_adiabatic_law`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56) は密閉管の体積から圧力上昇を3%以内で検証する。[`output_does_not_depend_on_the_host_block_size`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78) はホストのブロック分割に対するPCMのビット一致を検証する。今回の52点では節点方程式自体をビット単位で照合する。

先行実験では声門流量が8,216点目まで一致し、次点の枝が読む気管圧で初差が出た。今回の[事前登録](../cases/fixed-voice-subglottal-balance-48000.json)では、8,216点目の更新前圧力と声門流出は一致し、静止した気管では正味流量の差が更新後圧力差を説明すると予測した。気管枝からの流入、壁流出、コンプライアンスを個別に置き換え、予測を検査する。

## 気管からの流入で最初の圧力差を復元

先行実験の固定母音 `/i/` を引き継ぎ、出力48 kHz・内部96 kHzで先頭の4,120出力フレームを描画した。ゲート開放は出力4,096フレーム目。観測を足した2つの隔離ビルドで、8,188〜8,239点目を採取した。両版の枝CSV、研究版の内部トレース、上流のフレーム末尾トレースとPCMは、それぞれ保存済みの同条件の出力とバイト一致した。

| 最初に分かれた観測点 | 内部サンプル番号 | 結果 |
| --- | ---: | --- |
| 気管の一つ手前のセルの更新前圧力 | 8,214 | 同じ時点の末端の更新前圧力は一致 |
| 末端へ入る直列枝の流量 | 8,215 | 1 ULPの差。末端の更新後圧力はこの点まで一致 |
| 気管末端の更新後圧力 | 8,216 | 0.015307743795696938 と 0.015307743795696934 dyn/cm²。研究版と固定上流で2 ULPの差 |
| 声門が読む気管末端圧力と、声門・壁の流量 | 8,217 | 末端の更新結果を次の内部点が読む |

8,216点目の末端セルは、更新前圧力、声門流出、壁流出、体積変化による注入、コンプライアンスが両版で一致した。気管からの流入は研究版の `0.0014435594092775058` と上流の `0.0014435594092775052` cm³/s で3 ULPの差だった。この1項だけを上流値に置き換えて体積収支を再計算すると、更新後圧力が `0.015307743795696934` dyn/cm² に一致した。コンプライアンスと壁面積は測定した52点すべてで一致した。[判定と採取値](../runs/fixed-voice-subglottal-balance-48000-repeat/summary.json)

この比較で追跡できた最も早い差は、一つ手前の気管セルが8,214点目の直列枝更新に渡す圧力。次はそのセルの8,213点目の更新と、8,214〜8,215点目の直列枝の駆動圧、持ち越し運動量、損失を採る。末端へ入る流量を直す場合も、声門スリット抵抗の丸め順の効果は別の比較で確かめる。

## 実行と検証

```bash
# 研究ワークスペースで初回を実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_subglottal_balance.py fixed-voice-subglottal-balance-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_subglottal_balance.py" \
  fixed-voice-subglottal-balance-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で両実行の11判定と上流の12試験が通過した。各実行104点の圧力・流量を、有理数と十進数の計算で演算ごとに照合した。両実行の300入力と36出力をSHA-256で照合した。観測CSV、PCM、計測差分など11点がバイト一致し、採取物4,665,713バイトはRTL9210B-CGに保存した。[初回マニフェスト](../runs/fixed-voice-subglottal-balance-48000-a/manifest.json)・[再実行マニフェスト](../runs/fixed-voice-subglottal-balance-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-subglottal-balance-48000.json)

補助検算の初回は、実行ファイルのハッシュを含む要約全体のバイト一致を要求したため停止した。差は上流プローブのハッシュ1件で、Mach-Oのセクションの内容は一致し、シンボルテーブルのロードコマンドとUUIDに差があった。補助検算を修正し、要約の計測値と判定、11保存物の一致を確認した。登録ケースの11判定は両実行で初回から通過した。[停止時のログ](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-subglottal-balance-48000-v1.log)
