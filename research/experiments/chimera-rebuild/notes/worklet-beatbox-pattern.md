# AudioWorkletでの固定ビートパターン

固定上流の画面は `setBeatPlaying(true)` から `AudioEngine::setBeat` を呼び、パターン・BPM・スウィング・再生状態をメッセージでWorkletに渡す。Workletの `beat` ハンドラーは各ステップを共有レコード領域に書き、WASMの `engine_set_beat` を呼ぶ。休符は先頭バイト255、MIDI音高とアクセントは各1個の倍精度値で、NaNは省略を表す。WASMはステップ置換、テンポ更新、開始または停止の順に適用する。テレメトリには最新の `engine_beat_step` を含める。[UIの状態](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L217)・[メッセージ送信](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L352)・[レコード形式](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/wire.ts#L91)・[Workletの受信](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L148)・[WASMの操作と観測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L400)

`Engine::render` は通算出力フレームの128ごとに、内部サンプルを進める前の音源時計を読む。次のステップが200 msの先読み内なら休符も履歴に追加し、打音だけ調音ジェスチャーにして音源スコアへ入れる。16分音符は `60 / (4 × BPM)` 秒、スウィングは奇数番号にその半分の指定倍率を加える。調音時計は64出力フレーム構成の制御更新を先に行ってから進む。Workletに返る再生位置は描画後の時計で到来済みのステップ番号をパターン長で剰余した値で、開始前は−1。描画後の値を末尾サンプルに付けると、秒換算した打音時刻より早いサンプルに新しい位置が見えることがある。[描画と予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[履歴とスコア](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L145)・[音源の制御時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L455)

上流の `output_does_not_depend_on_the_host_block_size` は同じ絶対フレームに操作を入れ、1〜48,000フレームの呼び出し分割でビット一致を確認する。WASMの `the_audio_thread_abi_does_not_allocate` は休符のないビートの装填・描画・表示の問い合わせ・停止を含めて割り当てを数える。TypeScript側には256ステップを最後まで再生するテストもある。[Engineのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)・[上流ABIのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/tests/realtime.rs#L44)・[長いパターンのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/wasm-engine.test.ts#L94)

今回はオフラインのAudioWorkletで、`m:43> . . M:47 | . . . . | B . . .` の固定条件を再現する。観測間隔64と77ではWASMを呼ぶ位置が違うため、観測点の違いと、合成の時計やPCMへの影響を分けて比較できる。観測点には出力フレームとWASMの累積フレーム数を残す。音源状態はゲート、声門面積・流量・有声化、瞬時と平滑化のF0、唇端の最小面積・鼻端流量を照合する。2つの鼻音の定常区間ではPCMの自己相関でMIDI 43と47を区別する。絶対時刻を付けたテンポ変更・停止の操作と実時間の処理予算は次の条件で扱う。[登録ケース](../cases/worklet-beatbox-pattern.json)・[CLIの入力と測定窓](../cases/beatbox-pattern-hum.json)

## 実装

画面で入力したパターンをページ側でUTF-8に符号化し、Workletで共有メモリに書く。Rustの `BeatPlayer::starting` がCLIと同じ記譜を解釈する。初期F0（110 Hz）と基準F0（100 Hz）を別に設定し、準備姿勢、声門の揺らぎと乱流は `ArticulatedVoice::configure_beatbox` をCLI・WASMで共有する。予約とスコアへの追加は `BeatPlayer::prepare_frame` で行う。WASMは通算出力フレームを基準に呼び、休符を含む到来済みの位置と、次に予約する通算ステップを線形メモリの観測列に追加する。他の発声モードは同じ観測領域の従来の先頭部分を読む。[WASMの入口](../crates/vocal-wasm/src/lib.rs)・[共通の予約](../crates/vocal-core/src/phonetics/beatbox/player.rs)・[波形取得](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)

## 結果

| 観測 | 結果 |
| --- | --- |
| 出力とクロック | モノラル48 kHz・62,400フレーム。両条件のWorklet呼び出しは488回で128フレームの量子。64間隔では975点、77間隔では811点を保存。どの観測点でもContextの0始まりの末尾フレームに1を加えた値がWASMの累積フレームと一致 |
| 波形と音源 | ブラウザとCLIのPCMは全フレームでビット一致。2つの観測間隔のWAVもバイト一致。8系列の音源状態はCLIと差0。描画中のWASMメモリの増加は両条件で0回 |
| 再生位置 | 両方とも開始待ちと0〜8の9ステップを観測し、休符を含め固定上流・CLI・独立計算と照合。CLIで最初に0が現れるフレームは9,600。同じ変化を画面では64間隔で9,663、77間隔で9,624に表示 |
| 二つの音高 | PCM自己相関のF0はMIDI 43で97.959 Hz、MIDI 47で123.711 Hz。最大相関は0.967と0.995 |

固定上流とのPCM差は最大 `7.28×10⁻¹²`。最初のビット差は出力フレーム532で約 `2.84×10⁻¹⁴`。出力フレームごとの時系列では、それより前のフレーム1に口端放射流量の差 `1.54×10⁻¹⁶ cm³/s`、フレーム2に声門上圧の差 `2.32×10⁻¹⁶ dyn/cm²` が見えた。唇端の最小面積とF0は全区間で一致し、口端流量の差はブラウザ接続前のパターンでも確認できる。内部サンプル単位でどの演算から差が始まるかは未調査。[初回通過の要約](../runs/worklet-beatbox-20261120-b/summary.json)・[ネイティブ時系列](../runs/worklet-beatbox-20261120-b/artifacts/trace.csv)・[固定上流の時系列](../runs/worklet-beatbox-20261120-b/artifacts/upstream-trace.csv)・[接続前の基準](../runs/transport-20261120-hum-after/manifest.json)

初回のブラウザ操作は観測間隔の選択欄をラベルで特定できず時間切れになった。選択欄のアクセシブル名を明示し、役割と名前で指定するように修正した。入力・観測条件・閾値の変更は不要だった。修正後と `/tmp` からの再実行で各17項目が通過。実行環境はmacOS arm64、Chromium 156.0.8078.4、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。上流の `beatbox`・`engine` とWASMの `realtime`、候補のRust整形・Clippy・ワークスペーステストも通過した。[初回の時間切れ](../runs/worklet-beatbox-20261120-a/manifest.json)・[修正後](../runs/worklet-beatbox-20261120-b/manifest.json)・[再実行](../runs/worklet-beatbox-20261120-repeat/manifest.json)・[操作画面](../runs/worklet-beatbox-20261120-repeat/artifacts/browser-beat.png)

初回通過と再実行のWAV、観測JSON、WASM、要約など18ファイルがバイト一致した。音高付きパターンは共通予約関数を適用する前後でネイティブ・上流の11ファイルが一致した。テンポ変更・停止のCLI回帰も基準と14ファイルが一致し、ブラウザの固定母音・IPAのWAVと観測JSONは各基準と一致した。[音高付きパターンの基準](../runs/transport-20261120-hum-after/manifest.json)・[動的テンポの回帰](../runs/worklet-beatbox-20261120-transport-regression/manifest.json)・[固定母音の回帰](../runs/worklet-beatbox-20261120-fixed-regression/manifest.json)・[IPAの回帰](../runs/worklet-beatbox-20261120-ipa-regression/manifest.json)・[IPAの基準となるオフライン計測](../runs/worklet-rate-96000-20261120-ipa-regression/manifest.json)

```bash
python3 tools/measure_worklet_beatbox.py worklet-beatbox-local-1
```
