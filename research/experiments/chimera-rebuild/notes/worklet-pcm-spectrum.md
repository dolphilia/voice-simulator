# 選択時刻のPCMスペクトル

## 固定上流の読解と事前登録

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine` では、AudioWorkletの出力が直接、または近接マイクを模したフィルタ・コンプレッサーを経由して、ゲイン0.8のマスターに入る。そのマスターに通常スペクトル用の4,096点・平滑係数0.6の `AnalyserNode` と、スペクトログラム用の2,048点・平滑なしのノードが接続される。`SpectrumView` は `getFloatFrequencyData` を読み、有声ならF0の整数倍の周辺の最大値を抜き、その他では連続した周波数帯を描く。表示ごとの最大値を0 dBに揃え、声道の線形伝達関数を重ねる。 `Spectrogram` は2,048点の結果を周波数帯ごとの最大値として時間軸に保存する。 [音声グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L140)・[スペクトル](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SpectrumView.tsx#L53)・[短い窓の使用](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Spectrogram.tsx#L38)

上流の `AnalyserNode` の周波数分析は、直近Nフレームに周期的Blackman窓を掛け、FFTの絶対値を平滑化してからデシベルに変換する。別の `tests/airway.rs::fdtd_peaks` は、気道のインパルス応答を上流のRust製 `Fft::transform` に通して共鳴を検査する。こちらの入力は放射流量の時間微分なので、共鳴の検査では絶対値を角周波数で割る。 `tests/engine.rs::output_does_not_depend_on_the_host_block_size` はPCMのブロック分割不変性を検査する。[Web Audio仕様の窓・FFT・平滑化](https://www.w3.org/TR/webaudio/#fft-windowing-and-smoothing-over-time)・[上流のRust FFT](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/fft.rs)・[上流の共鳴テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L23)・[分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

今回は保存WAVと同じモノラルの合成PCMを使う。この信号は音源の間引き・DC除去・リミッタの後にあり、ブラウザの再生ゲインより前にある。中心の出力フレームを `c` として `[c-1024,c+1024)` の2,048点を取り、発話外はゼロで埋める。窓は `w[n] = 0.42 − 0.5 cos(2πn/N) + 0.08 cos(4πn/N)`。FFTの大きさを `Σw` で割り、中間ビンは2倍する。周波数は `k fs / N`、画面の単位は `20 log10(A)` dBFS。軸は60–8,000 Hzと−120–0 dBFSを共通に使い、ダウンロードにはDCからナイキストまでの線形振幅を保存する。[候補の出力段](../crates/vocal-core/src/output.rs)・[WAVの出力](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[登録条件](../cases/worklet-pcm-spectrum.json)

48 kHzの `ɑpɑ` で、フレーム6,750の窓の最大ビンは650–900 Hz、12,287の閉鎖窓では最大値が母音より50 dB以上低くなり、14,591の再開口側を含む窓では20 dB以上戻ると予測する。先頭と末尾のゼロ埋めを含む5選択点で、ブラウザとCLI・固定上流PCMの独立FFTを全ビン照合する。既知振幅のビン一致正弦波、DC、ナイキスト、無音で正規化を検査する。幅960・390 CSS pxで書き出しと描画の座標を照合する。[発話と閉鎖の基準](../cases/worklet-ipa-voice.json)・[閉鎖の先行結果](../runs/worklet-glottal-scope-20261119-b/summary.json)

## 実装と再現手順

`IpaTimeline` の選択フレームを `SpeechSpectrum` に渡し、共通の `pcmSpectrum` が窓を作る。FFTは既存の波動管プロトタイプで使っていた基数2の実装を `web/shared/audio/fft.ts` に移して再利用した。固定上流のPCMとChimera再実装の保存WAV・CLIの出力はPython側で同じ区間を抽出し、SciPyの周期窓と実FFTに通す。画面は保存WAVと同じPCMであることを示し、選択フレームごとにJSONを保存できる。JSONの `sourceFirstFrame` は実データの開始、`sourceEndFrame` は終了の次のフレーム。`firstFrame` はゼロ埋めを含めた窓全体の開始。線形振幅 `amplitudes[k]` の周波数は `k * sampleRate / fftSize` Hz。[スペクトル計算](../../../../web/prototypes/chimera-research/src/pcm-spectrum.ts)・[共通FFT](../../../../web/shared/audio/fft.ts)・[比較ツール](../tools/measure_pcm_spectrum.py)

```bash
python3 tools/measure_worklet_ipa.py worklet-pcm-spectrum-local-1 --spectrum
```

## 結果

48 kHzで窓長は42.667 ms、ビン間隔は23.4375 Hz。両画面幅で選択5件の全1,025ビンを照合した。独立FFTとの差はCLI・ブラウザWAVを基準に最大 `6.05×10⁻¹⁶`、固定上流PCMを基準に最大 `1.93×10⁻¹⁵` の線形振幅。元のPCMの最初の差は出力フレーム13,291で、閉鎖窓のうち窓重みが小さい末尾付近に入った。ブラウザWAVと固定上流を同じSciPyの処理に通した場合、閉鎖窓の振幅の最大差は `9.05×10⁻²¹`、末尾窓では `1.93×10⁻¹⁵`。描画座標は独立計算と一致し、正弦波0.5、DC 0.25、ナイキスト0.125、無音0の振幅判定が通過した。固定上流の気道・有気指定・高速発話・分割の13テストと、FFTを共有した波動管プロトタイプのビルドも通過した。[全ケース](../runs/worklet-pcm-spectrum-20261119-c/summary.json)・[上流テスト](../runs/worklet-pcm-spectrum-20261119-c/artifacts/upstream-tests.log)

| 選択フレーム | 解析窓 | 表示帯域で最も強いビン | 振幅 |
| --- | --- | --- | --- |
| 6,750 | 最初の母音 | 773.44 Hz | −23.82 dBFS |
| 12,287 | 口唇閉鎖のみ | 70.31 Hz | −83.30 dBFS |
| 14,591 | 再開口を含む | 70.31 Hz | −33.16 dBFS |

母音から閉鎖まで59.47 dB低下し、再開口を含む窓で50.14 dB戻った。閉鎖窓はCLIの口唇最小断面が全2,048点で閉鎖閾値未満だった。先頭窓の実データは1,024点、末尾窓は1,025点。残りはゼロ埋めし、画面表示の下限から外れた末尾窓の値もJSONに保存した。[母音の表示](../runs/worklet-pcm-spectrum-20261119-c/artifacts/spectrum-960-voiced.png)・[閉鎖の表示](../runs/worklet-pcm-spectrum-20261119-c/artifacts/spectrum-390-closure.png)・[末尾のデータ](../runs/worklet-pcm-spectrum-20261119-c/artifacts/spectrum-960-49827.json)

初回の2実行ではWAVと観測JSONを含む10件が保存された後、11件目のダウンロード通知がタイムアウトした。2実行目で通常のダウンロードリンクに移行した後も同じ箇所で再現した。390 pxだけを独立したセッションで試すと5件すべて保存できたため、計測を幅ごとの独立したブラウザセッションにした。登録条件と合否基準は維持し、初回の部分出力も保存した。[初回a](../runs/worklet-pcm-spectrum-20261119-a/manifest.json)・[初回b](../runs/worklet-pcm-spectrum-20261119-b/manifest.json)・[通過c](../runs/worklet-pcm-spectrum-20261119-c/manifest.json)

研究ディレクトリと `/tmp` からの実行で各19判定が通過した。PCM、10件のスペクトルJSON、描画座標、4枚の画面画像、結果要約はハッシュが一致した。[再実行d](../runs/worklet-pcm-spectrum-20261119-d/manifest.json)
