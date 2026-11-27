# 実時間AudioWorkletでのウェッデルアザラシの `whistle`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryの再生は `AudioEngine.playCall` からWorkletの `call`、WASMの `engine_play_call` を経て、`CreatureVoice::play_call` に届く。手動変更は `cparams` がキー名を索引に引き直し、`set_params` が手動値と現在の目標を更新する。公式CLIは `trill`、`zap` の後の320,160フレームで `whistle` を指示し、声門と気道の状態を引き継いで72,000フレーム進む。上流の `seal-call-whistle` はPCM、10 ms窓のRMS、状態、ブロック分割への依存を検査する。実時間試験はコール操作と観測中の割り当て、全キーの解決を調べる。[再生ボタン](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L162)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`eval_call` は64出力フレーム間隔の累積時計（秒）でパラメータ別に前後のキーを選ぶ。音高は1,700 → 620 → 1,500 Hzを0、0.45、0.95秒のキーで結ぶ。指数補間は対数音高での直線補間に相当し、通常は10 msで比率を平滑化して声門へ渡す。ゲートには音高の中間キーがなく、開始値1から1秒の0まで直線で減衰し、呼気倍率を掛けて手動ゲートとの大きい方を採る。パルス深さ0.1と音高だけをコールが所有し、終了後に手動の目標へ復帰する。進行する位相と、平滑化した深さ・ゲートから固定肺圧（dyn/cm²）を求め、声門と気道を更新した後、放射流量の時間差分（cm³/s²）を間引き・DC除去・振幅制限してf32 PCMにする。[上流のキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L116)・[評価順序と単位](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L276)・[候補での評価](../crates/vocal-core/src/seal_voice/call.rs#L126)

## 事前登録

元のCLI基準から48 kHzの公式デモ、44.1 kHzの850 Hzへの移調と同一フレームでの手動変更、96 kHzの単独コールを再生する。目標の谷を出力フレーム341,824・19,968・43,264とし、平滑音高の谷はその後で、最初の制御から0.455〜0.465秒の範囲を予測する。44.1 kHzでは20,003でパルス周波数、デューティ、圧力の手動目標が変化し、音高1,250 Hzと深さ0.42は46,464で復帰すると予測する。全PCMと64フレームごとの観測、指示・手動変更・終了の前後を照合する。CLIとはPCMのビット一致・状態差0、上流と独立計算は元ケースの閾値を用いる。

谷は制御境界で得た音高を使って二つ確認する。前のフレームの平滑音高を初期状態として、目標をフレーム番号から対数上で補間し、保持率 `exp(−Δt/τ)` のIIRで直接平滑音高を求める。合成器を呼ばず、SciPyで対数領域の加重和を計算する。目標と平滑値の最小フレームおよび音高を照合する。連続時間の近似では、対数音高の下降・上昇の傾きの絶対値を `a`、`b` とすると、谷直前に一次遅れの定常誤差 `aτ` が残り、谷の後で `(a+b)τ exp(−s/τ)−bτ` へ移る。誤差が0になる `s=τ log(1+a/b)` を平滑値の予測遅れとする。実時間の遅れは0.45秒のキー時刻から数え、連続近似との差が1制御間隔以内という予測を検査する。[ブラウザ登録条件](../cases/worklet-seal-whistle.json)・[キー・測定区間](../cases/seal-whistle.json)・[共通の許容差](../cases/seal-trill.json)

## ブラウザの実装と実測

既存の `SealVoice` とC ABIに3レートの `whistle` ケースを接続した。44.1 kHzで同時刻の呼気と音高を、CLIと同じ呼気・音高の順で適用する。画面からのWAV・観測JSON・再実行ケースを保存し、CLIと固定上流に照合した。全560,160 PCMフレームはCLIとビット一致し、27系列の計8,771観測点も一致した。[画面とケース](../../../../web/prototypes/chimera-research/src/main.tsx)・[比較器](../tools/measure_worklet_seal_whistle.py)・[計測結果](../runs/worklet-seal-whistle-20261120-a/summary.json)

| 出力レート | PCMフレーム・観測点 | 0.45秒のキーに相当するフレーム | 目標が最低のフレーム・音高 | 平滑値が最低のフレーム・音高 | 観測された谷の間隔 |
| --- | --- | ---: | ---: | ---: | ---: |
| 48 kHz | 392,160・6,133 | 341,792 | 341,824・620.731 Hz | 342,144・629.041 Hz | 6.67 ms |
| 44.1 kHz | 56,000・883 | 19,973 | 19,968・310.079 Hz | 20,288・314.512 Hz | 7.26 ms |
| 96 kHz | 112,000・1,755 | 43,264 | 43,264・620.000 Hz | 44,032・629.034 Hz | 8.00 ms |

48 kHzではキー時刻が二つの制御境界の中間に落ちる。上昇側の対数音高の傾きが緩やかなので、同じ32フレーム離れている前後の境界のうち、後ろの境界が620 Hzに近かった。44.1 kHzでは直前の境界で目標が最低になり、96 kHzではキー時刻が制御境界に一致した。独立した対数IIRは全条件で目標と平滑値の谷のフレームを再現し、音高の最大絶対差は `2.77e-10 Hz`。連続時間の近似による遅れ8.19 msに対し、キー時刻から数えた実測は7.33・7.14・8.00 ms。連続近似との差はそれぞれ0.64・0.72・0.29制御間隔だった。[二つの参照計算と谷の位置](../runs/worklet-seal-whistle-20261120-a/summary.json)

44.1 kHzの20,003フレームで、パルス周波数、デューティ、圧力の目標は24 Hz、0.7、12 cmH₂Oへ変わった。その時点の平滑パルス周波数は18 Hzのままで、20,032から18.366 Hzに変化した。コール中の深さ目標0.1と音高曲線は維持され、46,464で手動目標の1,250 Hzと0.42に戻った。コールの呼気が弱くなってからも、手動ゲート0.25が下限として働いた。[操作前後のブラウザ観測](../runs/worklet-seal-whistle-20261120-a/summary.json)

### 固定上流との差

44.1 kHzは固定上流とも全PCMがビット一致した。48 kHzの公式 `whistle` 区間72,000フレームでは15フレームに差が出た。区間内の最初の内部放射の差は640,320、最初のPCM差は365,111、最大絶対差は `8.88e-16`。96 kHzでは最初の壁面と総放射の差を内部103、PCM差を2,938で観測した。PCMは2フレームに差があり、最大は `5.68e-14`。両レートとも観測した制御時計、音高・呼気の制御値と肺圧は固定上流と一致した。ネイティブの基準計測では、双方の放射を同じ独立出力段へ通すと最初の差の箇所でそれぞれの単精度値を再現できた。[ブラウザのPCM差](../runs/worklet-seal-whistle-20261120-a/summary.json)・[放射からの再構成](../runs/seal-whistle-before-worklet-1/summary.json)

### 実時間と再実行

研究ディレクトリと `/tmp` から実行し、各101項目が通過した。44.1 kHzのネイティブ試験ではコール開始、手動変更、自然終了を挟んで割り当て0。ブラウザは計測中に128フレームずつ連続して描画し、先頭8量子を除いたp95は3レートとも1 msだった。時計は1 ms分解能の `Date.now`。開始待ち中の不連続数も計測記録に残した。[初回](../runs/worklet-seal-whistle-20261120-a/manifest.json)・[別ディレクトリでの再実行](../runs/worklet-seal-whistle-20261120-repeat/manifest.json)

再実行でWAV・書き出したケース・CLIのCSV・WASMの13ファイルのハッシュとブラウザ観測の全行が一致した。`zap` の72項目と鳴禽の切り替え22項目も通過し、保存した波形・観測行・ケース・CSVは変更前と一致した。Rustの整形、Clippy、ワークスペース試験29件を確認した。[zapの回帰](../runs/worklet-seal-zap-whistle-regression-20261120/manifest.json)・[鳴禽の回帰](../runs/worklet-songbird-switch-seal-whistle-regression-20261120/manifest.json)

```bash
python3 tools/measure_seal_whistle.py seal-whistle-local-1
python3 tools/measure_worklet_seal_whistle.py worklet-seal-whistle-local-1 seal-whistle-local-1
```
