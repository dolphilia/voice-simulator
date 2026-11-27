# AudioUnitがエラーを返すときの減衰PCM

## 呼び出しと比較条件

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` が作るAudioContextで、Workletの `ChimeraProcessor.process()` は出力量子のフレーム数をWASMの `engine_render()` に渡す。永続するエンジンは絶対フレーム `pos` に沿って制御とPCM生成を進める。固定上流のブロック長試験は、同じフレームで指示したときの出力が分割長に依存しないことを確認する。今回の対象は、このPCMより下流のAudioUnitの出力コールバックである。[上流の構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Workletの描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[WASM境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流のブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

公開WebKitの `AudioOutputUnitAdaptor::inputProc()` は、ホスト時刻とサンプル時刻、要求フレーム数、出力バッファを `RemoteAudioDestination::render()` へ渡し、その `OSStatus` をAudioUnitへ返す。公開版 `1392437` ではリング不足時に読み出し位置を保ち、直前の末尾サンプルから減衰をバッファへ書いて `-1` を返す。Pythonの対照モデルでは減衰が生じたが、保存済みSafari 18.6のタップでは同じ位置が無音だった。[WebKitのコールバックと戻り値](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/cocoa/AudioOutputUnitAdaptor.cpp#L61-L73)・[公開版の不足時の処理](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L186-L248)・[Safariの採取とモデルの比較](webkit-output-underrun.md#保存済みsafariの波形との照合)・[AppleのAURenderCallback](https://developer.apple.com/documentation/audiotoolbox/aurendercallback)

既存のSwift製 `DefaultOutput` AudioUnitを48 kHzステレオfloat32で動かす。左右逆相の既知波形を流し、0起算80番の要求で直前の末尾 `x` から `x/N` ずつ減じる。続く3要求にはゼロを書き、84番から元の絶対フレームに対応する波形に戻る。出力フレームを進める順序を保ち、4要求の戻り値だけを0か `-1` にする。出力バッファへ書いたPCMは事前確保した領域に複製する。タップは同じ出力プロセスへ事前に付け、ホスト時刻とサンプル時刻も保存する。前後の既知波形を照合して減衰の開始位置を推定し、減衰の中央半分を閉形式 `x(1 − (j+1)/N)` と比較する。[事前登録](../cases/coreaudio-output-error-pcm.json)・[出力対照](../tools/chimera_output_deadline_probe.swift)・[タップ採取と照合](../tools/measure_coreaudio_output_error_pcm.py)・[Appleのプロセスタップ手順](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)

## 実測

実行順を反転した2組で、全条件の要求長は512フレームだった。減衰と前後を含む3,072フレームの出力バッファは4試行でビット一致し、512点の減衰は閉形式と一致した。毎回、後続の1,536フレームにはゼロを書いた。ネイティブとタップの両方でサンプル時刻が連続した。前後の波形で求めたタップの位置差は0.050フレーム以内だった。[初回](../runs/coreaudio-output-error-pcm-20261122-a/summary.json)・[反転順](../runs/coreaudio-output-error-pcm-20261122-repeat/summary.json)

| 該当する4要求の戻り値 | 減衰のRMS振幅比（採取／参照） | 減衰中央の相対RMS残差 | 後続の無音の中央 |
| --- | ---: | ---: | --- |
| 0 | 0.999928・0.999925 | 7.51×10⁻⁵・7.82×10⁻⁵ | 両チャンネルがゼロ |
| −1 | 0.999931・0.999923 | 7.25×10⁻⁵・8.08×10⁻⁵ | 両チャンネルがゼロ |

この既定出力経路では、`-1` を返した場合にも書き込んだ減衰がプロセスタップまで届いた。戻り値だけを変えても、前回のSafariで観測した無音は再現しなかった。物理出力と、Safari内の戻り値は採取していない。

後続の対照では、コールバックに渡ったバッファは再利用時にも全サンプルがゼロだった。保持と明示的ゼロの両方で、タップに現れた完全ゼロの区間は返した区間より95フレーム短かった。[バッファ入口と採取境界の比較](coreaudio-output-buffer-entry.md#実測)

## Safariと公開ソースの版

試行機のSafariは18.6で、SafariとWebKitの `CFBundleVersion` は共に `20621.3.11.11.3` だった。Appleの公開ソースに末尾の番号が一致する `WebKit-7621.3.11.11.3`（2025-08-15、コミット `e97539821b38379d82a51b6740d90191d5d0b7af`）がある。この版の `RemoteAudioDestination::render()` はリング不足時に読み出し位置を保つ。出力バッファに減衰を書き込む分岐はなく、要求累計と通知を更新して `-1` を返す。減衰を追加した後年の変更は2026-07-27の `c315a716758008c2e11d996fe2e663db6097d114` に見える。公開ソースの版差は、Safari 18.6の採取で減衰が見えなかったことと整合する。稼働バイナリとの厳密な対応と、不足時点のバッファ内容は未確認である。[AppleのSafari 18.6リリースノート](https://developer.apple.com/documentation/safari-release-notes/safari-18_6-release-notes)・[Apple公開版の描画関数](https://github.com/apple-oss-distributions/WebKit/blob/e97539821b38379d82a51b6740d90191d5d0b7af/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L157-L171)・[減衰を加えた変更](https://github.com/WebKit/WebKit/commit/c315a716758008c2e11d996fe2e663db6097d114)

## 実行と保存

macOS 15.6.1（24G90、arm64）、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースで実行する。実行場所と順序を変える際はスクリプトとPythonを絶対パスで指定し、`--reverse` を加える。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 \
  ../../.venv/bin/python tools/measure_coreaudio_output_error_pcm.py \
  coreaudio-output-error-pcm-example \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
```

2実行の各41判定、従来の出力コールバックの計測8判定、固定上流のホストブロック長試験が通過した。対象の3実行の45入力・60出力をサイズとSHA-256で照合し、採取物7,368,458バイトをRTL9210B-CGに保存した。4試行の比較波形と、2実行の出力対照バイナリはそれぞれSHA-256が一致した。[初回](../runs/coreaudio-output-error-pcm-20261122-a/manifest.json)・[反転順](../runs/coreaudio-output-error-pcm-20261122-repeat/manifest.json)・[従来の計測の回帰](../runs/coreaudio-output-deadline-20261122-error-pcm-regression/manifest.json)
