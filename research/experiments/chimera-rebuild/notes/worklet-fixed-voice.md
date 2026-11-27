# 固定姿勢のAudioWorkletレンダー

## 固定上流の読解

対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。上流の `AudioEngine.build` はContextを用意し、`audioWorklet.addModule` の後で、コンパイル済みWASMを `AudioWorkletNode` の `processorOptions` に渡す。Workletのコンストラクタがインスタンス化し、実サンプルレート、体型、声道セル数を `ready` で返す。先に登録やコンストラクタが失敗した場合、次の操作でContextから作り直せる。上流E2Eは初回だけ `addModule` を拒否し、同じボタンの再操作でテレメトリが戻ることを検査する。[AudioEngine.build](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Workletの準備](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L40)・[再試行のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tools/e2e.ts#L282)

`ChimeraProcessor.process` は出力チャンネルに渡された実長だけWASMを進め、線形メモリのf32を最初のチャンネルへ書く。追加チャンネルへは同じ波形を複製する。Web Audioの加工前のPCMを取り出すには、上流でWorkletから解析器やフィルタへ分岐する位置を観測する。通常の上流テレメトリは6ブロックに一度で、RMSの集計区間と声門波形の位相を持つ。今回の固定姿勢ABIでは、呼気ゲート、声門開口面積（cm²）、流量（cm³/s）、位相、発声ゲート、F0（Hz）、放射の流量差分（cm³/s²）を、WASMが最後に処理した出力フレームの値として観測する。[ブロック処理](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[音声グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L141)・[固定姿勢ABI](wasm-fixed-voice.md)

Web Audioでは `currentFrame` が処理中ブロックの先頭を表す。ブロック内オフセットを `o`、今回処理した長さを `n` としたとき、観測点は `currentFrame + o + n − 1`。WASMのカウンタは処理済みフレーム数なので、観測点が同期していればブラウザの0始まり番号より1大きい。間引き率2では、CLIの内部サンプル番号は `2 × frames_rendered − 1` になる。オフラインの開始前にメッセージの受け手を登録し、完了はPCMの返却とWorkletの観測通知の両方で確かめる。[Web AudioのcurrentFrame](https://www.w3.org/TR/webaudio/#dom-audioworkletglobalscope-currentframe)・[オフラインレンダー](https://www.w3.org/TR/webaudio/#dom-offlineaudiocontext-startrendering)

## 実装前の登録

前回の固定姿勢 /i/ のケースをそのまま使用する。96 kHzの内部サンプルを48 kHzのモノラルPCMへ変換する。Web Audioに加工ノードを挟まず、ブラウザのオフライン出力とCLIを32,768フレーム全体でビット比較する。固定上流とのPCM・状態の許容差は既存のWASM比較と同じ。観測は前回の相互比較と同じ7系列を使い、今回は128フレームごとの末尾256点とする。実際のコールバック長、先頭番号、時計の連続性、WASMバッファの安定性、開始後の有効なF0を検査する。上流と同じ初回のWorklet読み込み失敗を注入し、再操作で同じPCMと観測値が得られることも確認する。[今回の比較条件](../cases/worklet-fixed-voice.json)・[入力姿勢](../cases/vowel-voice-i.json)・[前回のWASM結果](../runs/wasm-fixed-voice-20261119-c/summary.json)

## 実装

Reactの画面は登録済みの固定母音ケースを読み込む。Viteで配布したWASMをページでコンパイルし、モノラルの `OfflineAudioContext` のWorkletに渡す。Workletは既存の固定声道ABIに対して、出力バッファの長さと次の観測時刻までの距離で処理量を決める。観測用の配列は初期化時に確保する。周期ごとのスナップショットをその配列にコピーし、完了時に配列全体を送る。この条件では観測間隔とコールバック長が同じ128フレームなので、WASMとWeb Audioのコールバックは1対1になる。ページは両方の完了を受け、IEEE Float WAVと観測JSONを保存できる状態にする。再レンダー時には新しいContextを作り、古い音声・観測のURLを解放する。[Worklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[レンダーの入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[Viteのバンドル設定](../../../../web/prototypes/chimera-research/vite.config.ts)

## 検証結果

- Chromium 156.0.8078.4、48 kHzモノラルの128フレームのコールバックを256回観測した。ブラウザの開始フレームは0、欠落は0、観測はフレーム127〜32,767。ブラウザの番号、WASMの累積フレーム数、CLIの内部サンプル番号は式どおりに対応した。
- WAVの32,768フレームはネイティブCLI・固定上流とビット一致し、ブラウザとCLIのWAVファイルはヘッダーを含めて同じハッシュになった。観測7系列のCLIとの差は0。上流との差は各系列のピーク比で最大1.90×10⁻¹³だった。
- 発音開始の閾値を越えたのはフレーム39。定常区間のF0は声門位相から110.0000 Hz、PCMのYINから110.0016 Hz。配布されたWASMのハッシュはC ABIのビルド出力と一致し、メモリとバッファの位置は安定した。
- 初回のWorklet読み込み失敗を画面に表示した。同じボタンで再試行すると、通常時と同一のWAVと観測JSONを生成した。初回と別ディレクトリからの再実行で12判定が通過した。[初回](../runs/worklet-fixed-voice-20261119-a/manifest.json)・[再実行](../runs/worklet-fixed-voice-20261119-b/manifest.json)・[ネイティブ対WASMの回帰](../runs/wasm-fixed-voice-20261119-worklet-regression/summary.json)

この計測はブラウザのオフライン出力を扱う。実時間の起動・停止、持続時の処理時間、ほかのブラウザやレート、発話・歌唱と調音操作は今後の条件として残す。再実行の準備とブラウザ比較のコマンドはWebワークスペースに記載した。[起動と計測](../../../../web/prototypes/chimera-research/README.md)
