# 短音の歌唱で歯の乱流フィルタの設定をWorkletへ渡す

CLIで確認した `Pop Dee` の歯の低域通過周波数の対照を、同じ歌唱画面から再現する。全体係数1、声門・狭窄のゲイン倍率0を揃え、歯の下限0 Hzと1,200 Hzを比較する。参照する固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。[前回のCLI比較](song-voice-fast-teeth-lowpass-floor.md#実測)・[事前登録](../cases/worklet-song-fast-teeth-lowpass-floor.json)

## 歌唱の設定がPCMに届く経路

固定上流の `playTune()` は歌詞を音節に割り当て、`planSong()` を呼んで音符とテンポをジェスチャーに変換する。TypeScriptの `planSong()` はWASMの `api.rs` を通じてRustの `sing::plan_song()` に渡す。`AudioEngine` が送った `schedule` をWorkletが受け取ると、ジェスチャーを線形メモリに書き、`engine_schedule()` で発声時刻の起点を予約する。`process()` は出力バッファのフレーム数を `engine_render()` に渡し、WASMが持つ `f32` をチャンネルへコピーする。`Engine::render()` は描画要求ごとの位置を保ちながら内部の区切りで発声を進める。[上流の歌唱画面](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts)・[計画の橋渡し](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/engine.ts)・[上流WASMの計画API](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs)・[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts)・[音声のC ABI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)

この再実装では計画済みのスコアと発声設定を `prepareSongVoice()` から `OfflineAudioContext` のノードに渡し、`FixedVoiceEngine` が合成前にWASMハンドルを初期化する。歌唱画面の「乱流源の設定」で入力した声門・狭窄の倍率と歯の下限（Hz）は `vocal_start_score_with_turbulence()` に渡り、既存CLIと同じ `TurbulenceSettings` で `ArticulatedVoice` の初期化時に適用する。ゲイン倍率と下限を省略したときは従来のC ABIを使用する。保存する再実行ケースにも設定を書き出す。[歌唱画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[歌唱の初期化](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)・[TypeScriptホスト](../crates/vocal-wasm/host/fixed-voice.ts)・[候補のC ABI](../crates/vocal-wasm/src/lib.rs)

乱流の配置は出力64フレームごとに更新する。出力48 kHzの1フレームにつき96 kHzの状態を2回進め、制御境界で歯の低域通過周波数を `max(v d / δ², 下限)` とする。フィルタ状態と注入圧から放射を求め、間引きと出力段を通してPCMを得る。Workletの処理量子は128フレームでも、画面の観測間隔は64フレームのため `process()` は観測位置をまたがないよう分けてWASMを呼ぶ。観測はその区間の末尾で記録する。[乱流源の配置](../crates/vocal-core/src/airway/human/frication.rs)・[候補のWorklet](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[前回のフィルタ計算](song-voice-fast-teeth-lowpass-floor.md#呼び出しと独立計算)

比較には固定上流の `sing_fast` の短音の拍、`sung_release` の終音、`engine` のホスト分割に関する試験を通した前回の基準を用いる。今回の独立計算では最初の拍を0.5秒とし、拍間隔を `0.25 × 60/240` 秒として48 kHzのフレームに換算する。MIDI音高は `440 × 2^((MIDI番号 − 69)/12)` Hzで照合する。WASMで指定する下限の効果は、固定上流の0 Hzと候補CLIの各条件の出力を使って確認する。[上流の短音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)・[上流の終音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs)・[上流の分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[計測コード](../tools/measure_worklet_song_teeth_lowpass_floor.py)

## 実測

Chromiumの歌唱画面で短い音符を選び、全体係数0、声門・狭窄を抑えた下限0 Hz、同じ設定で下限1,200 Hzを順にレンダーした。全条件でCLIと49,200フレームのPCMがビット一致した。128フレーム量子は385回、観測点は769点。全観測点で、呼気ゲート、声門の面積・流量・振動率・F0、放射流量の時間微分、唇の開きと最小断面、平滑化F0、声門の開大の10列がCLIと数値一致した。描画はコンテキストフレーム0で始まり、最初の状態をフレーム63で採取した。途中の時刻の飛びとWASMメモリの拡張は0回だった。[判定と観測値](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/summary.json)

| 条件 | 全体係数0に対してPCMが初めて異なるフレーム | 絶対差が10⁻⁶を超える最初のフレーム |
| --- | ---: | ---: |
| 下限0 Hz | 27,968 | 27,972 |
| 下限1,200 Hz | 27,927 | 27,939 |

閉鎖末尾の27,840〜27,903フレームは3条件でPCMが揃った。下限1,200 Hzでは、0 Hzとの最初の差も27,927フレームで、差の最大は `2.7573 × 10⁻³`。固定上流との照合では、下限0 Hzの最大差は `2.91 × 10⁻¹¹`、下限1,200 Hzの最大差は `2.7573 × 10⁻³` で、固定上流との差が10⁻⁶を超えた最初は27,939フレームだった。固定上流と下限1,200 HzのWorklet観測が登録許容差を最初に超えたのは、27,967フレームで採取した声門流量だった。CLIの高密度観測では前回の対照どおり、先に歯の枝圧と放射が分岐している。Workletの64フレーム間隔では放射の分岐時刻を1フレーム単位で観測できない。[測定結果](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/summary.json)・[CLIの高密度観測](song-voice-fast-teeth-lowpass-floor.md#実測)

拍の位置は独立計算と同じ24,000・27,000フレームで、計画音高は261.625565・329.627557 Hz（計算誤差0 Hz）。WAVの `data` チャンクを別途読み、PCMの初回差と閉鎖区間の一致を再確認した。歌唱画面からダウンロードした3件の再実行ケースを別の作業ディレクトリからCLIでレンダーした結果も、各Workletとビット一致した。[下限0 Hzの再実行ケース](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/artifacts/floor0/browser-case.json)・[下限1,200 Hzの再実行ケース](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/artifacts/floor1200/browser-case.json)

確認したのはChromiumのオフライン処理。実時間AudioContextでの開始位置、開始前後の連続性、機器から出た波形と聴感は未確認。次は同じ2条件を既存の実時間歌唱の入口から実行し、開始を絶対フレームに揃えて、今回のオフラインPCMと照合する。

## 再現

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=80000000 ../../.venv/bin/python \
  tools/measure_worklet_song_teeth_lowpass_floor.py <実行ID>
cargo test --locked --workspace
```

macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。初回と `/private/tmp` からの再実行で各50件の取得判定と4件の予測を満たし、結果JSON、ブラウザから保存したWAV・観測・再実行ケースがバイト一致した。Cargoワークスペースの41試験を通過。入力578件、出力42件のサイズ・SHA-256を照合し、6.26 MBをRTL9210B-CGに保存した。[初回のマニフェスト](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)
