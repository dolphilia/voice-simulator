# 実時間のビート再生と操作の記録

固定上流のストアは `setBeatTempo` と `setBeatPlaying` で画面状態を更新し、`AudioEngine::setBeat` からBPM、スウィング（0〜0.6）、再生状態をWorkletに送る。Workletのメッセージ受信側は選択項目を `engine_set_beat` へ伝え、指定のないBPM・スウィングはNaNで保持する。開始時には音源時計に先読み200 msを加えて最初の打音の支点を作る。停止は予約・進行中のスコアを消す。気道と出力段の状態は次の描画へ引き継ぐ。上流の `process` はメッセージ処理後にPCMを生成し、6量子ごとに到来済みのステップ番号を含む観測を返す。[画面の操作](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts#L226)・[メッセージ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L352)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L148)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L414)

`BeatPlayer::set_tempo` は予約済みの時刻を保持し、未予約の最初のステップに対応する無スウィング時刻を旧BPMで求めてから、新しい16分音符長 `15 / BPM` 秒を適用する。スウィングは奇数番号のステップだけに `設定値 × 16分音符長 / 2` 秒加える。音源時計は64出力フレームごとの制御更新で進む。Engineはホスト幅にかかわらず絶対出力フレームの128刻みで先読み予約を行う。上流テストは同じ操作を絶対サンプル番号に置いてホスト幅間のビット一致を確認し、WASMの回帰ではテンポ・再生操作を含む描画経路の割り当てを数える。[予約と停止](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L234)・[テンポと先読み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L85)・[Engineのチャンク分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L36)・[テンポのテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs#L90)・[WASMの試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/tests/realtime.rs#L44)

研究版では受信順に操作を次の描画量子の先頭へ適用し、適用した出力フレームとAudioContextフレームを記録する。既存の `RealtimeSpeechCapture` で開始前に時計の連続を確認し、出力フレーム0以降の加工前PCMを保存する。実際の画面操作時刻にはばらつきがあるので、登録した範囲内で操作を行い、合成の比較時刻には実測した適用フレームを使う。停止中は一貫して再生位置−1となり、先読み済みの未来の打音が消える。停止前の圧力・呼気・調音を引き継いで音源を動かし続けるので、出力は徐々に減衰する。再開後の最初の打音はその時点から200 ms後に戻り、停止中に設定した100 BPMと保持したスウィングが次の予約に反映される。独立時刻表、CLI・固定上流、ブラウザの3経路に加え、量子の連続性と処理時間を照合する。[登録ケース](../cases/worklet-live-beatbox.json)・[固定テンポのブラウザ計測](worklet-beatbox-pattern.md)・[CLIの操作](beatbox-transport.md)

## 実装と計測

Workletは最初の描画量子と操作の直後、および6量子ごとに再生位置を画面へ返す。画面から受け取った操作はFIFOで処理し、WASMで受理されたものを採取結果に含める。WASMとCLIは同じRustの `BeatPlayer::set_tempo`・`set_playing`・`prepare_frame` と音源のスコア消去を使う。再実行ケースにはPCMの始点を0としたフレーム番号を、観測JSONには対応するAudioContext側の番号も保存する。停止から再開の間も音源の時計と放射は進む。[Workletの処理](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[WASMの操作入口](../crates/vocal-wasm/src/lib.rs)・[画面で保存する入力](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)

`/tmp` から実施した最初の通過実行では、120→160 BPM、スウィング0.4、停止、停止中に100 BPMへ変更、再開の各操作を、出力フレーム17,536・29,568・59,008・79,232・100,736で採用した。Contextと録音区間の起点差は3,456フレーム。停止時には予定時刻1.23125秒と1.41875秒の打音を取り消した。停止直後のPCMの絶対ピークは0.0819、停止260〜480 ms後のPCM RMSは `4.24×10⁻⁸`。再開後の発声窓のRMSは0.0752で、最初に到来したステップは0だった。[実測した操作を含むケース](../runs/worklet-live-beatbox-20261120-b/artifacts/browser-case.json)・[結果](../runs/worklet-live-beatbox-20261120-b/summary.json)

48 kHz・192,000サンプルの加工前PCMは、保存ケースを読み込んだCLIとビット一致。休符込みの再生位置と8系列の音響状態も3,000観測点で一致した。固定上流との差はPCM最大 `1.16×10⁻¹⁰`、最初のビット差はフレーム532で、最初の画面操作より前だった。この差は固定ビートのときから、まず口端放射流量と声門上圧で観測されている。CLIと上流はそれぞれ、ホスト幅77・128・4,096を変えても波形がバイト一致した。[実時間の要約](../runs/worklet-live-beatbox-20261120-b/summary.json)・[従来の差の観測](worklet-beatbox-pattern.md#結果)

最初の通過実行では1,500量子に欠けがなく、WASM線形メモリの増加は0回。Workletの `Date.now()` で計測した描画時間はp50が1 ms、p95とp99が2 ms、最大4 msで、2.667 msを超えた量子は3件だった。描画開始からPCMコピーまでを計り、その後の画面への通知は集計に含めていない。初回はNumPyの真偽値を要約JSONへ書き込めず失敗した。真偽値の変換を修正し、初回の入力・WAV・観測を保存した。音響の合否条件は同じ登録を使った。[初回の失敗記録](../runs/worklet-live-beatbox-20261120-a/manifest.json)・[通過の記録](../runs/worklet-live-beatbox-20261120-b/manifest.json)

研究ディレクトリからの再実行も13項目すべて通過した。停止は58,752フレーム、再開は100,224フレームに変わり、実測の操作列ごとにCLIとブラウザのPCMが一致した。固定上流との差は最大 `2.33×10⁻¹⁰`。1,500量子は連続、p99は2 ms、最大4 ms、処理予算を超えた量子は1件だった。実行環境はmacOS arm64、Chromium 156.0.8078.4、Node 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。固定上流の `beatbox`・`engine` とWASMの `realtime`、候補のRust整形・Clippy・ワークスペーステストも通過した。[再実行の要約](../runs/worklet-live-beatbox-20261120-repeat/summary.json)・[環境とコマンド](../runs/worklet-live-beatbox-20261120-repeat/manifest.json)・[画面](../runs/worklet-live-beatbox-20261120-repeat/artifacts/browser-beat-live.png)

既存のオフラインビート17項目、実時間歌唱25項目、CLIのビート操作18項目は回帰を通過した。オフラインビートの64・77間隔のWAVと観測JSON、歌唱のWAVと観測値、CLIの設定・時系列・PCMは、それぞれの以前の通過実行に一致した。[オフラインビート](../runs/worklet-live-beatbox-20261120-offline-regression/manifest.json)・[実時間歌唱](../runs/worklet-live-beatbox-20261120-song-regression/manifest.json)・[CLI](../runs/worklet-live-beatbox-20261120-cli-regression/manifest.json)

今回の比較は成人男性・48 kHzのパターンに対するテンポ、スウィング、停止、再開を対象とした。上流の再生中のパターン編集と単発パッドは今後の対応項目に残る。

```bash
python3 tools/measure_worklet_live_beatbox.py worklet-live-beatbox-local-1
cargo run --locked --release -p vocal-cli -- render-pcm worklet-live-beatbox-case.json beat-replay.wav beat-replay.csv 128
```
