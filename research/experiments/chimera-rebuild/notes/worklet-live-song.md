# 英語歌詞とMIDIの実時間歌唱

## 上流の予約と描画

固定コミットは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。`playTune` は音節とMIDIの音符を組み合わせ、テンポの `60 / bpm` を1拍の秒数とする。各音符の拍数を掛けて次の開始時刻を求め、歌唱計画を `AudioEngine.schedule` に渡す。ページで作ったジェスチャーには、秒単位の開始・終了、包絡、速度、調音・呼気・音高などの目標がある。表示は予約の応答に含まれる時刻から進める。[上流の歌唱](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[ページの予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L277)

Workletは数値列をWASMの記録領域に置き、`engine_schedule` でジェスチャーを復元する。`Engine::schedule` が現在の声の時計に準備時間を足し、その差を全ジェスチャーの時刻に加えてスコアを予約する。停止ではスコアを解除する。レンダーはホストから指定されたサンプル数を内部ブロック境界で区切り、ホストの呼び出し方に依存せず制御更新を進める。上流テストはブロック分割、短い連続音符の拍と子音、語尾の声帯開大と音量を検査する。[Workletの予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L198)・[エンジンの時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L174)・[ブロック分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)・[短い音符](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L29)・[語尾](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L48)

## 事前登録

既存の歌唱ケース `Pop Dee` を使う。120 BPM、MIDI 60と69を各1拍、先頭の母音拍は0.5秒、ビブラート35セント。対象は48 kHzの出力91,200フレーム、内部96 kHz、観測間隔64出力フレーム。Context時計から独立した歌唱位置を `絶対Contextフレーム − 予約フレーム` で求める。128フレームの713量子を見込み、最後の量子は歌唱64フレームと末尾のゼロ64フレーム。既存の発話と同じく8量子以上の連続を確認してから2,048フレーム先に開始を予約する。[実時間の登録](../cases/worklet-live-song.json)・[歌唱入力と独立計測条件](../cases/song-voice-long.json)

同じ初期姿勢・スコアで、実時間、オフライン、ネイティブCLIの加工前PCMと同位置の状態が一致すると予測する。CLIとのPCMはビット一致を要求し、固定上流とは既存の許容差で評価する。MIDIの `440 × 2^((n−69)/12)`、音高の変調、語尾の呼気と開大、最後の無音を同じ条件で照合する。停止は描画ノード接続後0.7秒以降に操作し、Contextの閉鎖と操作可能状態への復帰を観測する。描画開始から32量子を除いたp99を量子の予算以内、WASM線形メモリの増加は0件と予測し、同じABIを動かすネイティブの割り当ても量子別に記録する。

## 再実装

オフラインと実時間は `prepareSongVoice` で同じ辞書・歌詞・MIDIから同じスコアと初期音高を作る。`FixedProcessor` はスコアを受け取ってWASMの音声状態を初期化する。実時間では既存の量子予約を使い、予約前は出力をゼロにし、合成器を出力フレーム0の状態で待たせる。予約境界から出力PCMと観測を保存し、歌唱中に停止が指示されると、その操作で開始した `AudioContext` を閉じる。上流の予約は既存の声の時計へジェスチャーを移動し、研究用の有限長レンダーではContext上の開始フレームを別に記録して、合成器の時計を0から進める。これにより、歌唱計画の時刻を変更せずCLIとのサンプル比較ができる。[共通の歌唱準備と実時間ホスト](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[描画](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[量子の予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)

UIの停止検査では、ブラウザの描画ノードがContextに接続された時刻を採取する。0.7秒以上たった状態で停止を押し、Contextが閉じ、入力欄が操作可能になり、再度の歌唱が完了することを確認する。準備中のキャンセル時もContextを閉じられるよう、辞書取得を含む実時間処理にキャンセルを伝える。[画面操作と採取](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs)

ネイティブ計数では、ブラウザと同じ圧縮辞書を展開して歌唱プランナーを呼び、同じスコア・音高・乱流設定をC ABIに渡す。初期化後に各量子を観測間隔と末尾境界で分割して `vocal_render` を呼び、割り当てと再割り当てをスレッドごとに数える。ブラウザでは各量子の処理時間とWASM線形メモリの増加を採取する。[ネイティブ計数](../crates/vocal-wasm/src/lib.rs)・[比較コマンド](../tools/measure_worklet_song.py)

## 結果

変更前にオフライン歌唱を再計測し、既存の15項目を通過した。実時間の比較は研究ワークスペースと `/tmp` から各25項目を通過。加工前PCM 91,200フレームはCLI・オフラインとビット一致し、64フレーム間隔の1,425観測点も一致した。拍は歌唱の出力フレーム24,000と48,000で、Context上の位置は実測した開始フレームを足して求められた。開始後の713量子にフレームの飛びはなく、最後は歌唱64フレームとゼロ埋め64フレームだった。描画ノード接続後0.72秒と0.715秒で停止し、両回ともContextが閉じ、同じ入力で再び完了した。[変更前](../runs/worklet-live-song-20261120-baseline/manifest.json)・[初回](../runs/worklet-live-song-20261120-a/summary.json)・[再実行](../runs/worklet-live-song-20261120-b/summary.json)

固定上流の歌唱と照合した計画音素・拍・対象ジェスチャーは一致。PCMの最大差は `2.33×10⁻¹⁰`、最初のビット差は出力フレーム4,114で、オフライン基準と同じだった。詳細系列では、最初のフレームで口端面積と口腔第1セルの最小断面にそれぞれ `2.22×10⁻¹⁶ cm²`、`1.78×10⁻¹⁵ cm²` の差がすでにあり、口端流量・放射差分にも差があった。波形から独立に推定したF0は262.63 Hzと441.79 Hz、ビブラートの最大絶対値は34.57セント、末尾20 msのPCMピークは `3.39×10⁻¹⁰`。語尾では1.42秒に呼気ゲート1のまま声帯の開大を観測した。[独立計算、上流差と観測](../runs/worklet-live-song-20261120-a/summary.json)

冒頭32量子を除いた処理時間の中央値・p95・p99は両回とも1・2・2 ms。48 kHzの予算約2.67 msを超えた量子は各2件で、WASM線形メモリの増加は各0回だった。ネイティブでは11,809回の割り当てがあり、そのうち冒頭32量子後は11,296回。通常の量子は16回だが、語境界の /p/ から /d/ にかけて、出力フレーム44,672〜47,744の25量子で32回を数えた。接触補正後の形状再計算が関与するかは、同じ語境界の直前と途中で `apply` と `reapply` を別々に数えると確かめられる。[量子別の記録](../runs/worklet-live-song-20261120-a/manifest.json)・[接触補正の経路](../crates/vocal-core/src/voice.rs#L322)

既存の実時間IPAは19項目が通過し、直前のWAV・主要な内部状態・割り当て件数と一致した。ブラウザがgzip辞書を展開するオフライン歌唱も16項目を通過し、WAVと観測JSONは通常の配信経路とバイト一致した。[IPAの回帰](../runs/worklet-live-song-20261120-ipa-regression/manifest.json)・[gzipの回帰](../runs/worklet-live-song-20261120-raw-regression/manifest.json)
