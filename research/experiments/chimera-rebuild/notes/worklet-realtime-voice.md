# AudioContextでの固定発声の開始・停止

## 上流と事前登録

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` を読む。上流の `AudioEngine.start` は既存Contextを再開するか、`build` で48 kHzのContextを作る。操作のジェスチャー中に `resume` を呼び、モジュールを準備できた後でWorkletを接続する。E2Eでは音声処理が `running` となり、操作後に有意なRMSのテレメトリが来ることを確認する。ゲートの操作はWorkletのメッセージでRustの `set_gate` へ渡る。出力はWorklet直後で採取できる。上流の試聴経路にはその後でフィルタとコンプレッサーが入る。[AudioEngineの準備](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L98)・[ゲート操作](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L130)・[実時間の上流E2E](../../../../docs/reference/chimera-vocal-synth/upstream/tools/e2e.ts#L641)

`HumanVoice::set_gate` は次の目標を保持し、`control` が64出力フレームごとに呼気ゲートを `g + (目標 − g)(1 − exp(−Δt/τ))` に更新する。演奏操作だけの場合、立ち上がりの時定数は25 ms、立ち下がりは70 ms。平滑化後の値を肺圧（cmH₂O）に掛け、CGSの圧力を内部サンプル間で補間する。声門はその結果の圧力差に応答する。ゲート目標を0にした直後も内部状態には余韻が残る。上流の `engine.rs` の分割テストは、名前付きの制御イベントを絶対フレームで保持したままブロック分割を変えて比較する。[呼気の制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L504)・[ブロック分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)・[候補の呼気モデル](lung-breath.md)

上流Workletでは `Date.now()` の差からレンダー時間（ms）を求め、`1000 × コールバック長 / 実出力レート` で割った負荷を平滑化して送る。上流UIは立ち上がりの2秒間を除き、平滑負荷をさらに集計して、48 kHzで負荷が高いと32 kHzを試す。今回の固定ケースはレートを48 kHzに揃え、加工前PCMとタイミングの生系列を保存する。計測時計の名称も記録する。Web Audioの `currentFrame` はコールバックの先頭なので、Context側が接続までに進んだフレームを観測値に残し、PCMの位置は最初に処理したフレームから数える。[Workletの負荷](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[負荷の監視](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L216)・[currentFrameの定義](https://www.w3.org/TR/webaudio/#dom-audioworkletglobalscope-currentframe)

保存済みの固定 /i/ の姿勢を使う。最初の4096フレームはゲート0、その後に1を適用する。再生ボタンで開始し、ヘッドレスChromiumの操作で約950 ms後に停止を押す。停止の適用フレームはブラウザで観測して、CLIと上流に同じイベントを再入力する。停止後38,400フレームを採取し、最後の2400フレームのピークが無音とみなす閾値 `10⁻⁵` 以下になると予測する。定常窓のF0、各コールバックの時間、独立計算とのゲート差、全フレームの連続性を比較する。開始後の32ブロックを処理時間の集計から外し、発声と減衰の各区間で中央値、p95、p99を記録する。受け入れ条件は発声中のp99が128フレームの時間予算以内。[登録ケース](../cases/worklet-realtime-voice.json)・[固定姿勢の入力](../cases/vowel-voice-i.json)・[先行オフライン比較](../runs/worklet-fixed-voice-20261119-b/summary.json)

## 実装と再現

「発声を開始」はクリック中に `AudioContext.resume` を呼び、非同期にWASMとWorkletを準備する。Workletは配列を初期化時に確保する。接続後は8回連続でContextのフレーム位置がつながるまでゼロを出力し、合成器と採取の時計を止めておく。準備中のコールバック数と不連続も記録する。その後、登録済みの4096フレームの無音を合成器で進め、発声に入る。ボタンでの停止は次に処理するブロック先頭でゲート目標を0にし、実際の適用フレームを保存する。ブラウザのUIでは発声が5秒に達した場合も停止する。減衰を採取し終えてからContextを閉じる。[ブラウザの入口](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts)・[Worklet](../../../../web/prototypes/chimera-research/src/live-processor.ts)

採取したフレーム番号を `gate_events` として固定発声のCLIに入力できる。各イベントは出力フレーム先頭の内部サンプルで適用する。ゲートが実際に変化するのは、イベント以降の最初の制御更新である。比較器は、その位置を制御周期へ切り上げ、オンとオフの指数応答を閉形式で求める。上流の比較プローブにも、同じ初期設定とイベントを渡す。CLIではホストブロック128と77で波形と時系列を比較する。[固定発声CLI](../crates/vocal-cli/src/geometry_case/voice.rs)・[比較器](../tools/measure_worklet_realtime.py)

## 初回と再試行で判明したこと

初回はPCMとゲート、処理時間の判定が通った一方、1.915秒の音声に対してWorklet接続から通知まで3.557秒かかった。個々のコールバックの開始時刻を初回は記録しておらず、この差の発生箇所は特定できなかった。タイミングを追加した再実行では、Bunの起動がヘルプを返して成功扱いになり、以前のビルドから採取して観測列が一致しなかった。呼び出し元が実際にWebディレクトリでビルドするよう修正した。[初回の結果](../runs/worklet-realtime-voice-20261119-a/summary.json)・[ビルド起動の失敗](../runs/worklet-realtime-voice-20261119-b/manifest.json)

新しいビルドでの再試行では、PCMはCLIとビット一致したが、Contextの初回コールバックがフレーム1024、次が1664となり、途中の512フレームに処理がなかった。WASM内のフレームと採取したPCMは連続していた。この不一致を起動時の観測に残し、連続したブロック境界で計測開始する処理を加えた。事前登録したゲート、計測長、予算、絶対時刻の連続性の判定は維持した。[初期のContext不連続](../runs/worklet-realtime-voice-20261119-c/summary.json)

## 検証結果

Chromium 156.0.8078.4で128フレームのブロックを処理した。発声窓の中央値・p95・p99は1・1・2 ms、減衰窓は1・1・1 msだった。測定にはWorkletで利用できた `Date.now` を使ったため、値の刻みは1 ms。処理時間にはWASMのレンダーとPCM・観測バッファへのコピーを含む。128フレームを48 kHzで出す時間は2.667 ms。修正後の初回では、計測区間にこの予算を超えたコールバックはなかった。コールバック開始間隔のp99は6 msだったが、最初から最後までの開始時刻の差は1922 msで、フレーム数から求めた1920 msに近かった。実機スピーカーへの伝送やドライバーの欠落は別途観測が必要で、ここでの連続性はAudioWorkletのPCMとContext上のフレーム番号を指す。[修正後の計測](../runs/worklet-realtime-voice-20261119-d/summary.json)

同じ実行では準備中にContextの不連続が1件あった。準備後はContextフレーム2432から721ブロックが連続した。PCMはビット単位でCLIと一致し、CLIのホスト分割128・77でもWAVと出力CSVが一致した。上流との最大絶対差は `4.66×10⁻¹⁰` で、最初のPCM差はフレーム7868で隣接するf32の値。観測の最初の差はフレーム4223ですでに声門流量と放射に現れ、呼気ゲートと声門位相は全点一致した。観測ゲートと独立式との差は最大 `9.99×10⁻¹⁶`。発音の閾値を超えたのはゲート操作から28フレーム後、F0は110.0016 Hz。停止後0.8秒のうち最後の50 msのPCMピークは `3.59×10⁻¹⁰` だった。[時系列と判定](../runs/worklet-realtime-voice-20261119-d/summary.json)

修正後の固定母音のオフライン出力と、ABIの分割・割り当ての検証も通過した。ブラウザの実行はPlaywrightから画面の開始・停止を操作し、そこで保存したWAVと観測JSONを使う。再実行では停止の適用フレームと処理時間は変動する。各実行の入力は個別の `replay-case.json` にある。[オフラインの回帰](../runs/worklet-fixed-voice-20261119-realtime-regression/summary.json)・[WASMの回帰](../runs/wasm-fixed-voice-20261119-realtime-regression/summary.json)・[起動と比較コマンド](../../../../web/prototypes/chimera-research/README.md)

同じコードを別ディレクトリから再実行しても、準備中に不連続が1件あり、Contextフレーム2432からの717ブロックは連続した。発声中のp99は1 ms。中央値の計測表示0 msは時計の分解能内に収まることを示す。両実行で全11判定が通過した。[再実行の計測](../runs/worklet-realtime-voice-20261119-e/summary.json)
