# Safariのプロセス出力を滑らかな既知信号で較正

## 呼び出しと観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` は2チャンネルのAudioWorkletをAudioContextへ接続する。`ChimeraProcessor.process()` は各量子で `engine_render()` を呼び、返されたfloat32の波形を各チャンネルへ同じ値で設定する。WASM境界には描画するフレーム数と永続するエンジンのハンドルが渡り、`Engine::render()` は累計フレームで制御更新の境界を保つ。上流の試験は1・77・4,096・48,000フレームずつ呼んだときのPCMを128フレームずつの出力と照合する。今回の較正は同じWeb Audioから下流の経路だけを使った。Workletで左へ既知信号、右へ逆相を流し、歌唱との同時採取では左右の差から既知信号を取り出せるようにする。[AudioEngine](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[WASM境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Safariの再生・停止・再開に出力状態が追従する `com.apple.WebKit.GPU` を指定し、既存の署名済みアプリでステレオの `CATapDescription` と非公開の集約デバイスを作る。開始後は入力コールバックごとに、32ビット浮動小数のPCM、採取開始からのサンプル時刻、Machホスト時刻を記録する。採取開始直前のホスト時刻とエポック時刻の対応を使うと、後続の歌唱比較でブラウザの準備時刻と同じ時間軸に置ける。[Appleのプロセスタップ手順](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)・[採取コールバック](../tools/chimera_process_tap.swift#L46)・[採取開始と時刻の基準](../tools/chimera_process_tap.swift#L123)

## 試験信号と判定

固定シードから得た4,095個の二値を16フレームごとの節点に配置する。節点間の比率を `t` とし、`3t² − 2t³` で補間する。値と傾きは節点と65,520フレーム周期の境界で連続する。最大振幅は1/256とした。Safariの `AudioBufferSourceNode` が48 kHzでループし、Workletがグラフ内のPCMと時刻を保存する。[事前登録](../cases/safari-process-tap-smooth-marker.json)・[Safariの信号生成](../../../../web/prototypes/chimera-research/tools/capture-safari-process-tap.mjs)

採取PCMは `(L − R) / 2` を1,024フレームずつ切り出し、参照一周期との正規化相関で整数位相を選ぶ。近傍を除いた最大競合ピークとの差を確認し、選んだ位相の±1フレームで参照を補間して相対RMS残差とゲインを求める。採用できた隣接窓で、位相差が採取フレーム差に合う区間を連続とした。0.25フレームずらした対照は0.000001フレーム以内で復元できた。17,408点に挿入した欠落・重複対照では位相差がそれぞれ+128・−128フレーム。無音置換ではその窓が棄却され、前後で位相差は連続した。[照合器と対照](../tools/smooth_tap_marker.py)・[対照の結果](../runs/safari-process-tap-smooth-marker-20261122-repeat/summary.json)

## 実測

従来の段差のある試験音で採取を再試行したところ、今回は48 kHzのステレオPCMを47,104フレーム取得できた。採取時刻は512フレームずつ連続した。波形の急な段差の周りでは振動が見え、採取のピーク0.00476は入力の最大値0.00391を上回った。従来の振幅からフレーム番号を直接求める判定は最長69点で、条件の16,384点に届かなかった。波形が変化する段はグラフでの観測より下流にある。発生箇所は未特定。[段差のある試験音の結果](../runs/safari-process-tap-calibration-20261122-output-position-followup/summary.json)

滑らかな試験音の初回ではグラフ内20,480点のうち参照値がゼロの15点だけに最大5.18×10⁻¹⁷の差があり、開始用・再開後の両方で当初の全点ビット一致を満たさなかった。元の結果を保存し、グラフの参照値がゼロの点に限って絶対誤差1×10⁻¹⁴以下を認めた。採取側の相関・連続長・残差の基準は事前登録の値を使った。[初回の判定](../runs/safari-process-tap-smooth-marker-20261122-a/manifest.json)・[改訂理由](../cases/safari-process-tap-smooth-marker.json)

| 試行 | タップのPCM | 最長連続区間 | 許容範囲を超えた位相の変化 |
| --- | ---: | ---: | --- |
| 初回 | 47,104点 | 41,984点 | 採取45,056点からの窓で約−128フレーム |
| ゼロ近傍の判定を追加 | 47,104点 | 37,888点 | 採取9,216点からの窓で約−256フレーム |
| `/private/tmp` から再実行 | 47,104点 | 45,056点 | 観測なし |

改訂後の2試行では各26判定を通過した。採用窓の相関は0.99963以上、相対RMS残差は0.00031以下だった。左右の和はゼロで、サンプル時刻は全ブロックで連続し、ホスト時刻も単調だった。表の負の位相差は、その前に続いていた信号の連番に対する遅れを表す。歌唱の予備描画を入れていない初回と2回目にも現れた。グラフの描画、WebKitの共有リング、Core Audioによる採取のどこでこの差が生じたかは未確定で、表の位置は変化直後の採用窓の先頭を示す。[較正1](../runs/safari-process-tap-smooth-marker-20261122-b/summary.json)・[較正2](../runs/safari-process-tap-smooth-marker-20261122-repeat/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6、Node.js 24.19.0、Swift 6.2.3、Python 3.14.4で実行した。下記を研究ワークスペースで実行する。別ディレクトリから実行するときはPython、スクリプト、ケースを絶対パスで指定する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 \
  ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py \
  safari-process-tap-smooth-marker-example \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app \
  --case cases/safari-process-tap-smooth-marker.json
```

採取4回とグラフ対照1回の計77入力・76出力をサイズとSHA-256で照合し、実体計2,945,867バイトをRTL9210B-CGに置いた。滑らかな信号のグラフPCMは採取3回の開始用・再開後の計6ファイルで同じハッシュだった。従来のグラフ対照は17判定に合格し、固定上流のホストブロック長試験も通過した。[従来の試験音の回帰](../runs/safari-process-tap-calibration-20261122-smooth-regression/manifest.json)

次の歌唱比較ではタップ採取開始と連番の安定を確認してから一括・分割の準備を解放する。同じ採取経路で歌唱準備なしの対照を取り、準備時刻前後の位相変化と無音区間を照合する。公開WebKitでは共有リングの不足時に直前の末尾サンプルから減衰し、リングの読み出し位置を保つ分岐がある。上流のFIFOがリングへ書く無音と区別できる条件を先行信号で検証する。[公開WebKitの読み出しと減衰](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L186-L248)・[FIFOの無音補完](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/PushPullFIFO.cpp#L80-L125)
