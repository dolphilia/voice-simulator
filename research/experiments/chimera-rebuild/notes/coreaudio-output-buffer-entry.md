# AudioUnitの要求バッファを保持したときの出力

## 呼び出しと比較条件

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` はAudioContextにWorkletを接続する。`ChimeraProcessor.process()` は1量子の出力長を `engine_render()` に渡す。Rustの `Engine::render()` は累計フレームに沿って制御状態とPCMを書き、固定上流の試験は入力イベントを同じフレームに置いたままホストのブロック長を変えて出力を照合する。今回の観測点はその下流で、ネイティブのAudioUnitが出力バッファをコールバックに渡す時点である。[構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御位置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

試行機のSafari 18.6とビルド番号末尾が一致するApple公開版の `AudioOutputUnitAdaptor::inputProc()` は、要求フレーム数、時刻、出力バッファを `RemoteAudioDestination::render()` に渡し、その戻り値を返す。共有リング側は開始位置から要求全体を読み出せるときだけPCMをコピーして位置を進める。読み出せない場合は出力バッファと読み出し位置を保ち、要求累計を加算してWeb側へ通知し、`-1` を返す。戻り値を変えた前回の対照では、バッファに書き込んだ減衰が両条件ともタップに届いた。今回はその書き込みを省いた場合を比較する。[公開版のコールバック](https://github.com/apple-oss-distributions/WebKit/blob/e97539821b38379d82a51b6740d90191d5d0b7af/Source/WebCore/platform/audio/cocoa/AudioOutputUnitAdaptor.cpp#L61-L73)・[公開版のリング読み出し](https://github.com/apple-oss-distributions/WebKit/blob/e97539821b38379d82a51b6740d90191d5d0b7af/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L157-L171)・[Appleのコールバック仕様](https://developer.apple.com/documentation/audiotoolbox/aurendercallback)・[前回の比較](coreaudio-output-error-pcm.md)

前回のSwift製 `DefaultOutput` と48 kHzの逆相試験信号を使い、0起算80〜83番の4要求で `-1` を返す。前後2要求を含む範囲で、コールバックが受け取った左右のゼロのサンプル数、直近8要求に自分が書いたPCMとの一致、直前と同じバッファかを記録した。保持条件は全ゼロか確認済みのPCMだけを書き換えず返す。未知の内容はゼロに置き換えて件数を記録する。明示的ゼロ条件は4要求の全サンプルをゼロに書き換える。出力前後の連番からタップ上での位置を決め、各要求の中央半分を照合する。[事前登録](../cases/coreaudio-output-buffer-entry.json)・[ネイティブの観測点](../tools/chimera_output_deadline_probe.swift)・[採取と照合](../tools/measure_coreaudio_output_error_pcm.py)

## 実測

順序を反転した2組、計4試行で、既定出力の要求長は512フレームだった。対象の4要求と前後を合わせた計32要求で、入口の左右各512サンプルがすべてゼロだった。同じバッファが直前にも使われていた。イベントの16要求は予定どおり `-1` を返し、保持条件で未知の内容をゼロに置き換えた件数は0だった。保持・明示的ゼロとも、タップで各要求の中央255点が完全にゼロだった。要求とタップのサンプル時刻は連続し、前後の波形で求めた位置差は最大0.057フレームだった。[同順](../runs/coreaudio-output-buffer-entry-20261122-a/summary.json)・[反転順](../runs/coreaudio-output-buffer-entry-20261122-repeat/summary.json)

採取の全区間も、生の左右PCMから数え直した。イベント先頭を前側の既知波形で推定し、2,048フレームの無音の中点を含む完全ゼロの連続区間を採った。全4試行で1,953フレームだった。ゼロの開始は推定位置より約47.06フレーム後で、終了は書き出した無音の終点に対応する位置より約47.94フレーム手前だった。Safariの保存波形でも、先のモデルの6,400・3,968フレームの区間に対して、完全ゼロの区間がそれぞれ95フレーム短かった。今回の自作対照では、2,048フレームをゼロで返しても、タップに届くまでに境界付近が非ゼロになることを確認した。Safariの無音区間に同じ境界の影響が加わった可能性と整合する。Safari自身が受け取ったバッファ、境界が変化した処理段、スピーカー・端子の波形は未観測である。[Safariの二つの無音区間](webkit-output-underrun.md#保存済みsafariの波形との照合)

## 実行と保存

macOS 15.6.1 arm64、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4を使用した。下記は研究ワークスペースからの実行例。別ディレクトリから順を反転する場合はPython、スクリプト、ケースの絶対パスを使い、`--reverse` を加える。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 \
  ../../.venv/bin/python tools/measure_coreaudio_output_error_pcm.py \
  coreaudio-output-buffer-entry-example \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app \
  --case cases/coreaudio-output-buffer-entry.json
```

生PCMの完全ゼロ区間は次の手順で再計算できる。

```sh
../../.venv/bin/python - <<'PY'
import json
from pathlib import Path
import numpy as np

for suffix in ('a', 'repeat'):
    run = Path('runs') / f'coreaudio-output-buffer-entry-20261122-{suffix}'
    summary = json.loads((run / 'summary.json').read_text())
    for mode, trial in summary['trials'].items():
        tap = np.fromfile(run / 'artifacts' / mode / 'tap.f32le', dtype='<f4').reshape(-1, 2)
        anchor = trial['tap']['pre_anchor']['event_tap_frame']
        nonzero = np.flatnonzero(np.any(tap != 0, axis=1))
        index = np.searchsorted(nonzero, anchor + 1024)
        start, end = int(nonzero[index - 1]) + 1, int(nonzero[index])
        print(suffix, mode, end - start, start - anchor, anchor + 2048 - end)
PY
```

2実行は各74判定、変更後に再実行した戻り値と減衰の対照は41判定に合格した。出力デバイスを動かさない小さな確認で、既知PCMの保持と未知内容のゼロ置換も確認した。固定上流のホストブロック長試験は通過した。3実行の60入力・84出力をサイズとSHA-256で照合し、採取物11,099,869バイトはRTL9210B-CGに保存した。[初回](../runs/coreaudio-output-buffer-entry-20261122-a/manifest.json)・[再実行](../runs/coreaudio-output-buffer-entry-20261122-repeat/manifest.json)・[従来条件の回帰](../runs/coreaudio-output-error-pcm-20261122-entry-regression/manifest.json)
