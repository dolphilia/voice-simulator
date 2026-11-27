# 冒頭をそろえたSafari歌唱の予備描画

## 読解

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `AudioEngine.build()` はWorkletを接続する。`ChimeraProcessor.process()` が出力バッファの長さを `engine_render()` に渡す。Rustの `Engine::render()` は絶対サンプル位置 `pos` が制御ブロックの先頭に来ると予約を更新し、次の境界まで音声状態と出力を進めた後に `pos` を加算する。上流試験 `output_does_not_depend_on_the_host_block_size()` は同じ絶対フレームに操作を置き、128に対する1・77・4,096・48,000フレームの各ホスト幅でPCMをビット比較する。この試験が固定するのはサンプル順と値で、実時間の到着時刻は実機の別の観測量になる。[接続](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の歌唱画面は `songScorePreparationBlock` と `songScorePreparationInitialBlocks` を `renderRealtimeSongVoice()` に渡す。`FixedVoiceEngine.advanceScorePreparation()` は冒頭リストを優先し、片の長さを残りフレーム数で制限する。Rustの `Handle::advance_score_preparation()` はフレームごとに声源・気道を一歩進め、放射の体積流量の時間微分を出力段に渡す。残量を更新し、ゼロになった時点で譜面を内部時計に予約する。Workletは準備片を1回進めるたびに歌唱枝へ128フレーム分のゼロを返し、次の量子から歌唱開始に向けた連続量子を数える。WASM試験は部分的な末尾片を含む分割で、譜面の描画開始時の状態が一括準備と一致することを確認する。[画面の入口](../../../../web/prototypes/chimera-research/src/main.tsx#L627)・[片の選択](../crates/vocal-wasm/host/fixed-voice.ts#L390)・[Rustの更新](../crates/vocal-wasm/src/lib.rs#L1057)・[Workletの処理](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L157)・[WASM試験](../crates/vocal-wasm/src/lib.rs#L1172)

## 事前登録と測り方

前回は均等128と冒頭64×4＋256を比較した。今回は冒頭256フレームをどちらも64フレーム4片で処理し、残り16,128フレームの片だけを128・256に切り替えた。準備は130対67量子になり、差の名目値は `63 × 128 ÷ 48,000 = 0.168 s`。双方の予約出力とタップの歌唱立ち上がりは、準備解放からのペア差で中央値120 ms以上早まると予測した。第1片の開始から最終片の完了までの短縮は名目の25 ms以内を判定条件とした。[前回の比較](worklet-safari-song-process-output-block-size.md)・[今回の事前登録](../cases/worklet-safari-song-process-output-matched-start.json)・[Web Audioの描画量子](https://www.w3.org/TR/webaudio-1.1/#rendering-loop)

歌唱はPop Dee・48 kHz・31,200フレーム・乱流係数1。共通の先行音を左右逆相で流す。タップでは左右差の半分から先行音、平均から歌唱を得る。歌唱の開始は128フレームの前向きRMSが5×10⁻⁵を初めて超える位置とし、4,096フレームの参照波形の相関と照合する。先行音は絶対振幅1×10⁻⁵以下を低振幅とし、従来の全体窓で最長区間・両チャンネルの完全ゼロ・準備前後の位相差を記録する。[計測コード](../tools/measure_worklet_safari_song_process_output.py)・[Web Audioのチャンネル変換](https://www.w3.org/TR/webaudio-1.1/#channel-up-mixing-and-down-mixing)・[Core Audioのタップ](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)

グラフでは第1片の1量子前から第5片までと、第5片から準備完了の次の量子までを分け、先行音のコールバックの開始間隔を測る。タップの切り替え位置は、第5片のグラフ時刻に準備前の較正で得たグラフからタップまでの遅れを足して推定する。その前後8 msを境界に取り、冒頭は推定した第1片の20 ms前から境界手前、後続は境界の後ろ120 msを比較する。境界と、準備完了の推定タップ時刻までの後続全体についても最長区間を保存する。準備中に遅れが変化し得るため、区間別の値はタップ上での近似である。先行音の全体窓・後続120 msの低振幅と全体の位相差は、増加のペア中央値がそれぞれ128フレーム以下、冒頭はペア差の中央値の絶対値が128フレーム以下を予測した。[区間と判定](../cases/worklet-safari-song-process-output-matched-start.json)

## 実測

Safari 18.6で4ペアずつ、ペア内の順を反転して計8ペア測った。256フレームの条件でタップの歌唱立ち上がりは全ペアで162.7〜220.4 ms早まり、ペア差の中央値は182.8 msだった。準備自体は中央値167.5 ms短縮し、名目の168 msに近い。準備解放から予約出力の先頭までは中央値172.5 ms短縮した。全16試行で最後の準備片から3,200フレーム後に歌唱を予約し、歌唱の31,200サンプル、各488観測点、譜面は保存基準と一致した。タップの歌唱立ち上がりの相関は最小0.999875で、振幅による検出位置と相関位置との差は全試行で1フレームだった。[初回](../runs/worklet-safari-song-process-output-matched-start-20261122-a/summary.json)・[反転順](../runs/worklet-safari-song-process-output-matched-start-20261122-repeat/summary.json)

| 観測値 | 64×4＋128 | 64×4＋256 |
| --- | ---: | ---: |
| 準備片の数 | 130 | 67 |
| 第1片から準備完了 | 341〜348 ms | 174〜177 ms |
| 準備解放から予約出力の先頭 | 412〜441 ms | 246〜249 ms |
| 準備解放からタップの歌唱立ち上がり | 704.6〜768.2 ms | 541.6〜547.9 ms |
| グラフでの冒頭の最大間隔 | 5〜36 ms | 7〜10 ms |
| グラフでの後続の最大間隔 | 3〜16 ms | 3〜4 ms |
| タップでの冒頭の最長低振幅区間 | 0〜799フレーム | 91〜219フレーム |
| タップでの境界の最長低振幅区間 | 0〜685フレーム | 1〜206フレーム |
| タップでの後続120 msの最長低振幅区間 | 0〜687フレーム | 0フレーム |

冒頭の最長低振幅区間のペア差は、初回の中央値で128フレーム短く、反転順では410フレーム短かった。反転順では、冒頭をそろえれば差の中央値の絶対値が1量子以内に収まるという予測が外れた。全体窓で128フレーム以上続いた最長低振幅区間は8試行にあり、その開始はそれぞれ推定切り替え位置の9.9〜38.3 ms前だった。128フレーム条件の2試行で後続120 msにも191・687フレームの区間があった。どちらも境界から後続へ伸びた区間だった。両条件で同じ片を処理する冒頭にも差があり、後続片のサイズからその差を説明することはできない。観測した最大のグラフ間隔とタップの差には、切り替え前の実行ごとの変動が含まれる。[反転順の予測と試行別の区間](../runs/worklet-safari-song-process-output-matched-start-20261122-repeat/summary.json)

全体窓の先行音では、低振幅の最長区間と完全ゼロの最長区間がともにペア中央値で192フレーム短かった。準備前後の位相の遅れの絶対量は中央値で約384フレーム小さかったが、1ペアでは約256フレーム増えた。計測したのはSafariのグラフとプロセスタップで、機器端子の波形と聴感は未測定である。タップの左右平均について畳み込みでRMSを再計算し、工学単位に換算した各ブロックのホスト時刻から区間内の連続点を数え直した。全16試行で歌唱立ち上がりと区間別の点数・最長区間が記録と一致した。

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースで新しい実行IDを指定する。別ディレクトリから実行する場合はPython、スクリプト、ケースを絶対パスで渡し、`--reverse` で各ペアの順を反転する。採取器は保存済みの較正実行と実行ファイル・設定のSHA-256が一致する署名済みアプリを使う。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_process_output.py \
  worklet-safari-song-process-output-matched-start-example \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app \
  --case cases/worklet-safari-song-process-output-matched-start.json
```

採取・同一性は2実行の各216判定に合格した。事前予測は初回が7件中7件、反転順が7件中6件で成立し、外れた冒頭の予測は値と判定を保存した。既定の準備なし・一括・分割を同じツールの `--case` 指定なしで実行し、73判定と3予測が成立した。3実行の848入力・395出力をサイズとSHA-256で照合し、採取物47,077,995バイトをRTL9210B-CGに保存した。比較16試行の歌唱WAVが同一で、回帰を含む3実行のWASMも同一だった。[初回の記録](../runs/worklet-safari-song-process-output-matched-start-20261122-a/manifest.json)・[反転順の記録](../runs/worklet-safari-song-process-output-matched-start-20261122-repeat/manifest.json)・[既定ケースの回帰](../runs/worklet-safari-song-process-output-20261122-matched-start-regression/manifest.json)

固定上流のディレクトリでは `CARGO_TARGET_DIR=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-upstream-debug cargo test --locked -p chimera --test engine output_does_not_depend_on_the_host_block_size` が通過した。研究ワークスペースでは `CARGO_TARGET_DIR=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-rebuild-debug cargo test --locked -p vocal-wasm score_preparation_keeps_the_same_state_through_partial_last_block` が通過した。
