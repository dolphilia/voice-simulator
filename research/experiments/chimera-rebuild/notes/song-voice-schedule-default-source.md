# 上流既定の音源を使った短い歌唱のネイティブ・Safari・CLI比較

## 入口と時計

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のWorkletは、主スレッドからの音源設定を `engine_set_source()` へ、歌唱ジェスチャーを `engine_schedule()` へ渡す。Rustの `Engine::schedule()` がエンジン時計に先行時間0.03秒を足して譜面の時刻0を決める。Workletの `process()` は `engine_render()` から戻ったサンプルを出力チャンネルへコピーする。保存したSafari 18.6の観測は、その32ビット浮動小数点のPCMである。WASM内の出力レートは48 kHzで、声道と声門の内部レートは96 kHz。過去の採取では、譜面を予約するエンジン位置を16,384または16,512フレームにそろえた。[Worklet入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L121)・[WASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジンの予約時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[Safariの採取](upstream-safari-song-fixed-schedule-frame.md)

研究版は、通常の歌唱CLIで予備描画を進め、声門・気道・出力段の状態を保持したまま譜面を渡す。Safariの採取列にはContextのフレーム番号とエンジンのフレーム番号がある。今回、比較の軸には後者を使い、採取範囲が連続していることを各ブロックの開始フレームと長さで確かめた。譜面の時刻0から比較するネイティブの範囲と、予約位置から比較できるSafariとCLIの範囲を、それぞれ1,440サンプルの先行時間でそろえた。振幅はPCMの保存値を使い、位置は時計から整数サンプルで決めた。[研究版での予備描画と予約](../crates/vocal-cli/src/timing_case/speech_voice.rs#L652)・[Safariのフレーム検証](../tools/measure_song_schedule_default_source.py#L34)

## 音源設定と事前登録

男声中立姿勢、基準F0 110 Hz、肺圧7.2 cmH₂O、初期の呼気ゲート0で、240 BPMの「Pop Dee」2音を使った。前回の研究版のケースから、ドリフトだけを0から上流既定の5セントに変更した。粗さ0.1に対応する周期ジッター0.00455とシマー0.042は前回と同じ。予備描画2位置と乱流注入量0・1の4条件をネイティブ基準に通し、通常乱流ではSafariの連続・途中停止を各2試行照合した。[事前登録](../cases/song-voice-schedule-default-source.json)・[ネイティブの入力](../runs/upstream-song-schedule-state-20261121-repeat-b/artifacts/native-input.json)・[Safariの入力](../runs/upstream-safari-song-fixed-schedule-frame-20261121-repeat/artifacts/capture-input.json)

上流の5セントの設定は、シード4,242の乱数から3つの低域フィルタで得るドリフト値をセントに換える係数である。96 kHzの内部32ステップごとに更新し、セント値を `c` とすると基準F0に `2^(c/1200)` を掛ける。Pythonで予備描画と先行区間のF0を独立計算し、予約後の観測F0とつないで位相を積分した。各折り返しはシード777から計算した周期倍率と面積振幅倍率に対応する。上流の既存試験でブロック長独立性と短音の拍を再確認した。[上流のドリフトと位相](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[独立したF0計算](../tools/measure_glottal_pitch.py#L26)・[周期倍率と振幅倍率](../tools/measure_glottal_cycle.py#L41)・[上流のブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[上流の短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

## 実測

ネイティブ基準とCLIで、4条件それぞれの31,200点のF0と位相はビット一致した。予約直後のF0は、予備描画16,384フレームで109.891759704 Hz、16,512で109.889694350 Hz。独立計算との誤差は採取したF0、位相、振幅倍率の数値で0だった。登録した声門面積・流量・放射・PCMの閾値を超えた実装間の差は0件。有声窓21,000〜21,599サンプルのPCMは4条件すべてでビット一致した。[初回の物理量とPCM](../runs/song-voice-schedule-default-source-20261122-a/summary.json)

| 予約前のエンジン位置 | Safariの連続・停止と固定ネイティブのPCM | SafariとCLIのビット差の点数と最大差 |
| --- | --- | --- |
| 16,384フレーム | 譜面時刻0以降の29,760点が各試行で一致 | 先行時間を含む31,200点中9点、3.64×10⁻¹² |
| 16,512フレーム | 譜面時刻0以降の29,760点が各試行で一致 | 先行時間を含む31,200点中4点、7.28×10⁻¹² |

Safariの先行1,440サンプルはCLIとすべてビット一致した。予約前の描画量を128フレーム変えると、通常乱流では14,268サンプルで最初にビット差が出て、14,330サンプルでPCM差が10⁻⁶を超えた。固定ネイティブ、Safari、CLIで同じだった。Safariが停止する最も早い21,472サンプルより7,142サンプル早い。乱流注入量0では固定ネイティブとCLIが20,903サンプルで閾値を超えた。[停止位置を含むSafariの元記録](../runs/upstream-safari-song-fixed-schedule-frame-20261121-repeat/summary.json)・[今回の比較](../runs/song-voice-schedule-default-source-20261122-a/summary.json)

同じ予約位置の実装間に残ったPCM差は、乱流を止めた条件も含めて4〜9点で、最大2.91×10⁻¹¹だった。最初のビット差は全4条件で11,692サンプル。保存した物理量では11,104サンプルで放射差分に4.7×10⁻¹² cm³/s²、11,113サンプルで声門流量に8.84×10⁻²⁹ cm³/sの絶対差が見えた。ドリフト0の前回も同じ位置で差が出た。内部96 kHzの個々のステップに分けた最初の差は未特定である。[ドリフト0の残差](song-voice-schedule-shimmer.md#閾値を下回る残差)・[通常設定の状態CSV](../runs/song-voice-schedule-default-source-20261122-a/artifacts/frame-16384-noise-1/voicing.csv)

## 再実行

以下は研究ワークスペースからの初回。再実行は `/private/tmp` からPythonとスクリプトを絶対パスで指定し、実行IDを `song-voice-schedule-default-source-20261122-repeat` に替えた。ブラウザ側はハッシュを照合した保存結果を使用した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 \
  ../../.venv/bin/python tools/measure_song_schedule_default_source.py song-voice-schedule-default-source-20261122-a
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各33判定（予測19件を含む）を通過し、各165入力・30出力のサイズとSHA-256を照合した。両実行でPCM・CSV・要約21件と、出力段CSV8件の抜粋前ハッシュが一致した。全区間を比較した後、出力段CSVは各回15,873,188バイトから1,371,938バイトに絞った。外部ディスクRTL9210B-CGへの保存は両実行で計192,429,130バイト。上流の `engine` と `sing_fast` の計12テストも通過し、共有の独立計算で前回のドリフト0の2条件の振幅倍率を再現した。[初回](../runs/song-voice-schedule-default-source-20261122-a/manifest.json)・[再実行](../runs/song-voice-schedule-default-source-20261122-repeat/manifest.json)

次は研究版のWASM歌唱入口でも、予備描画を保持した状態に同じ3つの音源設定を適用できるようにし、既存の歌唱経路から加工前PCMと声門の状態をCLIに照合する。
