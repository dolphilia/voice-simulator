# Safariの二つの無音区間と共有リング・FIFOの照合

## 呼び出しと位置の更新

固定CHIMERAの `AudioEngine.build()` が開いたAudioContextで、`ChimeraProcessor.process()` は1量子の出力長を `engine_render()` に渡す。Rustの `Engine::render()` は絶対フレームの制御境界を進めてPCMを書き、同じ時刻で操作する限りホストの分割長に依存しない。今回の保存試行では、通常の歌唱画面で同じ保存基準の加工前PCMと観測点が得られている。先行音は同じAudioContextの別の枝で、歌唱準備前から鳴っている。[固定上流の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[WASM境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジンの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流のブロック長試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[プロセスタップの実測](worklet-safari-song-process-output.md#実測)

公開WebKitのGPU側 `RemoteAudioDestination::render()` は、要求長を `N`、読み出し位置を `r`、共有リングの有効範囲を `[s,e)` とすると、`s ≤ r` かつ `r + N ≤ e` の場合にだけPCMを取り出す。成功時は `r += N` となり、失敗時は読み出し位置を据え置いて `-1` を返す。公開版は失敗時にも出力バッファを書き、最後のサンプル `x` を起点に `x/N` ずつ減じる。次の失敗はゼロから始まる。成否にかかわらず機器の要求累計に `N` を加え、Web側へ通知する。公開テストは既知波形で有効範囲とPCMのコピーを照合し、周回と容量超過も確認する。[GPUの処理順と減衰](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/GPUProcess/media/RemoteAudioDestinationManager.cpp#L179-L248)・[リングの読み出し条件](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/cocoa/CARingBuffer.cpp#L252-L259)・[リングの公開テスト](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Tools/TestWebKitAPI/Tests/WebCore/CARingBufferTest.cpp#L102-L156)

Web側の `RemoteAudioDestinationProxy` は通知後に累計要求との差を読み、最大4,096フレームに分ける。各片ではまずFIFOから取り出し、不足分をゼロで埋め、片全体を現在の書き込み位置に置く。その後、片の大きさから残ったFIFOのフレーム数を引いた不足分の描画を依頼し、書き込み位置を進める。描画は128フレーム量子でFIFOへ戻る。共有出力がWorkletへ描画を渡す分岐では、応答まで待つ。したがって共有リングに書かれたゼロをGPUが読み出せた場合は、読み出し位置が進み、戻り値は成功になる。[累計の差分](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L88-L105)・[片の上限](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L52-L56)・[書き込みと描画](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebKit/WebProcess/GPU/media/RemoteAudioDestinationProxy.cpp#L224-L251)・[FIFOのゼロ補完と戻り値](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/PushPullFIFO.cpp#L80-L125)・[FIFOへの描画](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/AudioDestinationResampler.cpp#L101-L143)・[共有出力の待機](https://github.com/WebKit/WebKit/blob/1392437bb060048807e94d171c0fdf45e7d27301/Source/WebCore/platform/audio/SharedAudioDestination.cpp#L314-L331)

## 対照モデル

48 kHz、128フレームの要求が続く区間に絞り、有効なリングの先頭1量子に信号を置く。FIFOにはその続きの1量子を置き、最初の要求の後でリングへ書き、描画の補充を待つ。長い停止は、先頭から52要求を受けて、次の要求の直前に補充が間に合う条件とした。その時点で未処理の要求は `51 × 128 = 6,528` フレームある。4,096フレームの第1片は補充済み128フレームとFIFOの不足3,968フレームを含む。残り2,432フレームの第2片は、第1片の後に描画したFIFOから満たせる。リングの周回、他の出力ストリーム、再サンプリング、OSがコールバックのエラーを処理する箇所はこの実験の範囲外とした。モデルにはリングとFIFOの独立した位置、要求の累計、PCMの由来、成立した読み出しを記録した。[事前登録](../cases/webkit-output-underrun.json)・[モデルと比較手順](../tools/measure_webkit_output_underrun.py)

| 条件 | リングの読み出し失敗（フレーム） | 回復後に通る信号（フレーム） | FIFOから書いた無音（フレーム） | 信号位相の遅れ（フレーム） |
| --- | ---: | ---: | ---: | ---: |
| 連続 | 0 | — | 0 | 0 |
| FIFOの初期残量0 | 0 | — | 128 | 128 |
| 短い停止 | 640 | 128 | 640 | 1,280 |
| 長い停止 | 6,400 | 128 | 3,968 | 10,368 |
| 長い停止・書き込み上限2,048 | 6,400 | 128 | 1,920 | 8,320 |

リング読み出し失敗の最初の128フレームは、閉形式 `x(1 − (j+1)/128)` に一致した。残りの失敗区間とFIFO不足の無音は両チャンネルがゼロだった。モデル内で短い信号と回復後の信号をつなぐと、元の先行音の連番とビット一致した。上限だけを小さくした対照ではFIFOによる無音が2,048フレーム減った。機器側の初期残量と補充順を固定したモデル上の比較である。[条件別の計算結果](../runs/webkit-output-underrun-20261122-a/summary.json)

## 保存済みSafariの波形との照合

一括2試行の完全ゼロ区間は6,305・3,873フレームで、モデルの二つの不足区間よりそれぞれ95フレーム短かった。低振幅区間の開始間隔は両試行で6,528フレームだった。二つの区間の間で通った信号の中央80点を、準備前に確認した位相とモデルが予測する6,400フレームの遅れで照合した。準備前後の窓から求めた微小なドリフトとゲインを考慮すると、相対RMS残差は0.000352・0.000371だった。準備前後を通した位相の遅れは10,368フレームの予測からそれぞれ0.083・0.085フレームずれた。[2試行の照合結果](../runs/webkit-output-underrun-20261122-repeat/summary.json)

最初の不足位置を二つの無音の間の信号から推定し、前後16フレームずらして、最初の不足量子の64〜95点を比較した。直前の信号の絶対振幅が0.001以上になる候補は33件と30件あった。すべての候補で観測した32点は完全ゼロだった。公開版の減衰をそのまま通す参照は、この区間でRMS約0.00050〜0.00148の非ゼロ波形を予測した。この照合はタップに現れた形を示す。実行中のSafari側での減衰処理の有無と、AudioUnitがエラーを受けたときの出力バッファの扱いは未確定である。[採用した候補と残差](../runs/webkit-output-underrun-20261122-repeat/summary.json)・[出力の戻り値を変えた対照](coreaudio-output-render-status.md)

後続の実機対照では、既定出力へ減衰を書いた自作のAudioUnitは、戻り値が `-1` の場合にも同じ減衰をプロセスタップまで届けた。Safari 18.6の試行機とビルド番号末尾が一致するAppleの公開版には不足時に減衰を書く処理がなく、後年の公開WebKitで追加されたことも確認した。[対照の結果と版差](coreaudio-output-error-pcm.md)

次の既定出力の対照では、書き込み前に左右がゼロだったバッファを保持する場合と、ゼロを明示的に書く場合を比較した。どちらも返した2,048フレームに対し、タップの完全ゼロが1,953フレームで、差は95フレームだった。[要求バッファと境界の照合](coreaudio-output-buffer-entry.md#実測)

## 実行と保存

macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4で実行した。保存済みの2組はSafari 18.6で採取した。研究ワークスペースで実行IDを新しくして実行する。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=10000000 \
  ../../.venv/bin/python tools/measure_webkit_output_underrun.py webkit-output-underrun-example
```

研究ワークスペースと `/private/tmp` からの実行で各38判定に合格。各実行のPCM・位置記録・要約の11出力が同じSHA-256だった。2実行の30入力・22出力を照合し、採取物1,518,694バイトをRTL9210B-CGに保存した。固定上流のホストブロック長試験も通過した。[初回](../runs/webkit-output-underrun-20261122-a/manifest.json)・[再実行](../runs/webkit-output-underrun-20261122-repeat/manifest.json)
