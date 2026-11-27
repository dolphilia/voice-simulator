# IPA発話を実時間AudioWorkletで再生する

## 固定上流の読解と事前登録

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`speakPhrases` がメインスレッドで音素からジェスチャーを計画する。Workletの `schedule` 分岐は配列をWASMの記録領域へ書き、`engine_schedule` が `Engine::schedule` を呼ぶ。各ジェスチャーの開始・終了時刻に `voice.clock + lead` 秒を加え、置き換えの指定があれば直前のスコアを解除する。そのオフセットを予定音素区間にも加えて返す。`Engine::render` はホストの分割と独立に内部の境界でサブブロックを区切り、`HumanVoice` は制御更新ごとに発声時計を進める。`process` は量子ごとに `engine_render` を呼び、先頭チャンネルのPCMを出力する。負荷の単位は処理ミリ秒を `1000 × blockFrames / sampleRate` で割った値。上流の分割テストは同じ絶対フレームで操作を適用した出力をブロック長1・77・128などで比較する。[発話の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L53)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L134)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L198)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L176)・[分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

候補では今回の一発話に専用の合成器を作る。既存の `planIpa` と `vocal_start_score` で発話内のスコアを準備し、Contextの描画が8量子連続した境界から2,048フレーム後を発話の出力フレーム0に対応させる。待機中は無音を返し、合成器の初期状態を保つ。発話中は `ArticulatedVoice::step` が制御境界でスコア、調音、形状を更新し、`OutputStage` が内部96 kHzを48 kHzのPCMにする。Context上の絶対位置を処理時間の各行に保存し、表示・保存WAVの音素と観測は発話起点で揃える。最後の量子では実データ36フレームまでを採取し、残りをゼロにする。[既存のスコア準備](../crates/vocal-wasm/src/lib.rs#L177)・[制御更新](../crates/vocal-core/src/voice.rs#L322)・[既存の開始時計](../../../../web/prototypes/chimera-research/src/live-processor.ts)

48 kHz、量子128の `ɑpɑ` で、予告した境界からの欠落なし、CLIの49,828フレームとのビット一致、上流との既存の許容差、閉鎖・再開口、末尾の減衰を検査する。最初の32量子を含む分布を保存し、以降のp99を2.667 msの予算で判定する。初回WASMメモリ増加のフレーム、予算超過の件数、最大値も保存する。Context上の量子連続性はWorkletの観測値で検査し、物理デバイスへの到達は測定範囲外とする。[今回の登録](../cases/worklet-live-ipa.json)・[発話ケース](../cases/worklet-ipa-voice.json)・[既存の実時間測定](../cases/worklet-realtime-voice.json)

メモリ増加の観測に加え、ネイティブで同じRust ABIと観測間隔を通し、既存の計数アロケータで量子ごとの割り当て・再割り当ても数える。

## 実装と再現手順

IPA欄の「IPAを実時間で発声」で `renderRealtimeIpaVoice` が `AudioContext` を開き、オフラインと同じ `FixedProcessor` に準備済みスコアを渡す。Workletは予定フレームの到来までゼロを出し、到来後の波形と内部状態を既存の間隔で保存する。「IPAを停止」で準備中または再生中のContextを閉じ、同じ入力欄から再開できる。観測JSONの `output_frame` は発話内のフレーム番号、`realtime.blocks` の `context_frame` は量子先頭のContext上の絶対フレーム番号。`scheduledContextFrame` が両者の原点を結ぶ。処理時間には合成器、波形・観測バッファへのコピーを含め、完了時の転送はその後に行う。[ブラウザ側の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[Workletの収録](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[計測器](../tools/measure_worklet_live_ipa.py)

```bash
python3 tools/measure_worklet_ipa.py worklet-live-ipa-local-1 --live
```

## 結果

48 kHzで `ɑpɑ` の49,828フレームを収録した。実時間・オフライン・CLIのPCMはビット一致し、ブラウザ2経路の調音・声門・断面・圧力と流量も一致した。上流PCMとの差は出力フレーム13,291から現れ、最大 `1.82×10⁻¹²` だった。閉鎖・開口は16フレーム間隔の観測で11,119・13,903に現れた。末尾2,400フレームのPCMピークは `4.67×10⁻¹¹`。全390量子は発話の開始後に連続し、最後は36フレームを保存して残り92フレームをゼロにした。[発話とスケジュールの結果](../runs/worklet-live-ipa-20261119-c/summary.json)

初回通過では、開始前にContextのフレームが1回飛んだ。連続量子を確認し直し、Contextフレーム2,688の境界から2,048フレーム後の4,736で発話を開始した。処理時間はWorkletの `Date.now` でms単位に計測し、冒頭32量子以降の中央値・p95・p99は1・2・2 ms。量子予算2.667 msを、この区間では1量子、全区間では2量子が超過した。最大は出力フレーム0の4 ms。ここで確認した連続性はブラウザの量子番号と収録PCMに基づく。[量子ごとの観測JSON](../runs/worklet-live-ipa-20261119-c/artifacts/browser.json)

レンダー中のWASM線形メモリ増加は0回だった。ネイティブで同じABIの `vocal_render` と断面観測を計数すると、割り当て・再割り当ては全45,656回で、冒頭32量子以降にも41,752回あった。断面算出の `Ray::fan_floor` は走査線ごとに交差を `Vec` へ集め、`measurement_grid` と再標本化も一時ベクタを作る。次の比較では収録結果を固定し、交差配列の再利用で割り当てがどこまで減るか測る。[計数ログ](../runs/worklet-live-ipa-20261119-c/artifacts/native-allocations.log)・[交差の実装](../crates/vocal-core/src/anatomy/grid.rs#L143)・[再標本化](../crates/vocal-core/src/anatomy/resample.rs#L59)

先行の実行aはIPAプランナーへの速度引数が欠けて型検査で終了した。bではブラウザ収録は終わり、ネイティブ計数ログの出力先が比較ツールの読むファイルと異なったため判定が終了した。引数とログの出力先を修正し、同じ登録条件で再実行した。[先行a](../runs/worklet-live-ipa-20261119-a/manifest.json)・[先行b](../runs/worklet-live-ipa-20261119-b/manifest.json)・[通過c](../runs/worklet-live-ipa-20261119-c/manifest.json)

研究ディレクトリと `/tmp` からの実行で各19判定が通過した。再実行でも発話中の量子は連続し、冒頭32量子以降の中央値・p95・p99は1・2・2 ms、初回量子の最大は4 ms、WASM線形メモリ増加は0回だった。[再実行d](../runs/worklet-live-ipa-20261119-d/manifest.json)
