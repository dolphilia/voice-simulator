# 48 kHz固定発声のWASMメモリ観測

## 上流と研究版の経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build` は既定48 kHzでContextを開く。`ChimeraProcessor` はContextの実レートを `engine_new` に渡し、`process` で出力チャンネル長を `engine_render` に渡す。WASMは事前確保したf32の出力領域のアドレスを返し、Workletがチャンネルにコピーする。その処理時間はミリ秒で、1量子の予算は `1000 × 128 / 48000 ≈ 2.667 ms`。`Engine::render` は持ち越す絶対出力位置 `pos` で128点の帳尻を取り、分割境界で内部処理を進める。`output_does_not_depend_on_the_host_block_size` は固定時刻の操作列を入力し、128点分割とのビット一致を1、77、4,096、48,000点分割で確認する。[Context生成](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L108)・[Workletの描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASMの出力領域](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Engine::render](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

`HumanVoice::render` の内部レートは `(floor(60000 / Fs) + 1) × Fs` で、この条件は96 kHz。64出力フレーム相当ごとに肺圧目標を更新する。今回のスコアなしゲートは、更新間隔 `dt = 64 / Fs` 秒で `g + (target − g) × (1 − exp(−dt/τ))` に進み、時定数 `τ` は立ち上がり25 ms、開放後70 ms。各内部点では肺圧の補間、声門面積、気道の更新と放射、間引きの順になる。出力点ではDC除去と振幅制限を経てPCMにする。[声道と出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[呼気制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L510)

研究版の通常画面は `startRealtimeVoice` から起動し、`LiveProcessor.process` の量子境界でゲートを適用する。`FixedVoiceEngine.renderInto` は描画直後にWASMメモリのバッファを比較し、固定発声のバッファが変わった場合はその時点でエラーにする。量子の末尾に観測をコピーし、停止後の指定フレームまで達した時点で回数と初回フレームを報告する。領域の準備時に起きる増加は観測区間の外。CoreAudio以降の出力の連続性は別の観測点で計測する。[画面からの起動](../../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts#L11)・[描画と報告](../../../../web/prototypes/chimera-research/src/live-processor.ts#L183)・[バッファの監視](../crates/vocal-wasm/host/fixed-voice.ts#L457)

## 比較条件

48 kHzの過去の要約では回数と初回フレームが省かれていた。元の `browser.json` には0回、初回なし、末尾バッファ有効とあり、4,096点で発声、52,864点で停止、91,264点までの採取が残る。手動停止にも同じ観測の集計を適用し、現行ビルドで通常画面から再採取する。停止時刻はブラウザが採用したフレームを使い、各回の上流とCLIに同じイベントを渡す。5レートの保存値は各WorkletのJSONとケースから照合し、第4版の全判定を再現する。[旧Workletの一次記録](../runs/worklet-rate-96000-20261120-48000-regression/artifacts/browser.json)・[比較条件](../cases/worklet-realtime-voice.json)・[監査の条件](../cases/plan-completion-evidence.json)

## 再採取と差の起点

Chromium 156.0.8078.4、macOS 15.6.1 arm64、Rust 1.94.1、Node 24.19.0、Bun 1.4.4、Python 3.14.4で各13判定を通過した。研究ワークスペースと `/tmp` からの両回で4,096フレーム目に発声、54,656フレーム目に手動停止し、計93,056フレームを記録した。727量子のContextフレームは連続し、WASMメモリ増加0回、初回なし、末尾バッファ有効。発声と減衰の中央値、p95、p99はともに0、1、1 msで、量子予算2.667 msを超えた観測は0件だった。時計は `Date.now`。この分解能では1 ms未満の処理時間の内訳は定量できない。[採取と比較コマンド](../runs/worklet-rate-48000-memory-current/manifest.json)・[再実行の観測値](../runs/worklet-rate-48000-memory-repeat/summary.json)

WorkletとCLIの128・77フレーム分割をWAVのf32データ列で比較し、全フレームが一致した。固定上流とのPCMの最初のビット差は7,868フレーム目で、最大絶対差は約4.66×10⁻¹⁰。両方の出力フレーム末尾のCSVを個別に読むと、最初に差が見える列は声門上圧で、出力4,102フレーム目・内部8,205点目だった。声門流量と放射流量の時間差分も出力4,105フレーム目に分かれた。ゲートの値はCLIと上流で一致している。次に圧力差の起点を切り分けるなら、内部8,204〜8,206点の声門流入と咽頭セル0の圧力収支を採る。[独立照合の結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-chimera-fixed-voice-memory.json)

保存5レートと現行48 kHzの2実行について、別のWAV読取とゲートの逐次式で計632,320フレームを照合した。独立計算のゲートの最大絶対差は3.33×10⁻¹⁶。全体監査とは別に、回数欄・初回欄の欠落、増加1回、真偽値によるゼロの代用、末尾バッファ無効、量子位置のずれの6対照が落ちることを確認した。隔離先で初回の検算はスナップショットの配置の違いで止まった。マニフェストの `source_snapshot` から位置を取得して再実行した。[初回の検算ログ](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-chimera-fixed-voice-memory-before-source-path-fix.log)・[検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-chimera-fixed-voice-memory.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_worklet_realtime.py worklet-rate-48000-memory-new \
  --output-rate 48000
```
