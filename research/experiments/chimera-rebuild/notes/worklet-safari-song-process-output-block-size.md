# Safariの歌唱準備の分割長とプロセス出力

## 読解と比較条件

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` では、`AudioEngine.build()` が接続するWorkletの `ChimeraProcessor.process()` が、出力量子の長さを `engine_render()` に渡す。Rustでは `Engine::render()` が絶対フレーム `pos` で制御更新を揃え、音声状態を進めてから `pos` を加算する。上流試験は、同じ絶対フレームで操作した場合のホスト分割長を変えてPCMを照合する。[構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L181)・[WASM境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホストブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の通常の実時間歌唱では、URLの準備片設定を `renderRealtimeSongVoice()` からWorkletへ渡せる。`FixedVoiceEngine` は冒頭のリストを先に使い切り、その後の片を指定長で進める。区間の末尾では残りフレーム数に制限する。Rustに `vocal_advance_score_preparation()` を渡し、同じ声門・気道・放射・出力段の状態を持続させ、残量が0になった時点で譜面を内部時計に予約する。予備描画中にWorkletがContextへ返す量は毎回128フレームで、歌唱枝の値はゼロである。次の量子から既存の連続描画の条件を満たした後、歌唱出力を始める。[歌唱画面の入口](../../../../web/prototypes/chimera-research/src/main.tsx#L627)・[描画設定](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L329)・[片の選択](../crates/vocal-wasm/host/fixed-voice.ts#L390)・[Rustの状態更新](../crates/vocal-wasm/src/lib.rs#L1057)・[量子更新](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L157)

総準備量16,384フレームを、均等128フレームの128片と、最初の64フレーム4片に続く256フレーム63片で比較した。後者は均等128に比べ61量子少なく、48 kHzでは名目上162.67 ms短い。先行音は同じContextの別枝で逆相に出す。歌唱のモノラルPCMは左右へ同じ値で流れるため、タップの左右の差から先行音を、左右の平均から歌唱を抽出した。先行音は準備窓の低振幅区間と、準備前後の位相差を測った。歌唱立ち上がりは128フレームのRMSが5×10⁻⁵を初めて超える窓とし、加工前波形の同じ位置から4,096フレームを取って相関で照合した。予約出力の先頭と、音として現れる立ち上がりを別に記録した。[事前登録](../cases/worklet-safari-song-process-output-block-size.json)・[採取と照合](../tools/measure_worklet_safari_song_process_output.py)・[Web Audioのチャンネル変換](https://www.w3.org/TR/webaudio-1.1/#channel-up-mixing-and-down-mixing)・[Core Audioのタップ](https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps)

## 実測

Safari 18.6で各4ペア、順序を反転して計8ペア測った。準備解放からタップで観測した歌唱立ち上がりまでの時間は、全8ペアで256フレームを使う条件が162.2〜204.0 ms短く、ペア差の中央値は168.8 msだった。準備区間の短縮は中央値164.5 msで、名目差162.67 msに近かった。加工前の参照では歌唱立ち上がりは12,440フレームで、タップ波形の相関は全試行で0.9993以上、振幅で検出した位置と相関位置の差は各1フレームだった。[初回](../runs/worklet-safari-song-process-output-block-size-20261122-a/summary.json)・[反転順](../runs/worklet-safari-song-process-output-block-size-20261122-repeat/summary.json)

| 項目 | 均等128フレーム | 冒頭64×4、以降256フレーム |
| --- | ---: | ---: |
| 準備片の数 | 128 | 67 |
| 第1片から準備完了 | 339〜344 ms | 175〜177 ms |
| 準備解放から予約出力の先頭 | 411〜426 ms | 245〜250 ms |
| 準備解放からタップの歌唱立ち上がり | 708.3〜745.5 ms | 537.1〜549.3 ms |
| 準備窓の先行音の低振幅の最長区間 | 92〜860フレーム | 0〜219フレーム |
| 準備窓の両チャンネル完全ゼロの最長区間 | 33〜801フレーム | 0〜161フレーム |

タップの低振幅区間の最長は8ペアとも同等か短くなり、短縮の中央値は110.5フレームだった。この値は、各条件自身の準備時間を含む長さの異なる観測窓に対する値である。位相の遅れの絶対量は中央値で約256フレーム減ったが、1ペアでは約128フレーム増えた。準備前のグラフからタップまでの時刻差で補正すると、128フレーム以上続いた各試行の最長低振幅区間のうち、11件中10件の開始は第1片の前8.7 ms〜後2.4 msに集中した。均等128の1件は約314 ms後だった。比較した二つのスケジュールでは冒頭の長さと後続の長さがともに変わるため、先行音の差をどちらに帰属できるかは未確定である。[各試行の位相・低振幅区間](../runs/worklet-safari-song-process-output-block-size-20261122-repeat/summary.json)

16試行で、最後の準備片から3,200フレーム後に歌唱を予約した。歌唱31,200サンプルは保存基準とビット一致し、各488観測点と譜面も一致した。先行音各229,376点とタップ時刻も事前の比較条件を満たした。今回の測定点はグラフとプロセスタップで、機器端子の波形や聴感は未測定である。

## 実行と保存

macOS 15.6.1 arm64、Safari 18.6、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用した。研究ワークスペースから新しい実行IDで起動する。別ディレクトリから起動する場合はPython・スクリプト・ケースの絶対パスを指定し、各ペアの順を反転する場合は `--reverse` を加える。

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_safari_song_process_output.py \
  worklet-safari-song-process-output-block-size-example \
  /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app \
  --case cases/worklet-safari-song-process-output-block-size.json
```

2実行は各208判定に合格し、準備時間・グラフの開始・タップの立ち上がり・低振幅区間・位相の5予測が両方で成立した。従来の準備なし・一括・分割の回帰は73判定に合格した。固定上流のホストブロック長試験と、研究版WASMの予備描画の末尾片を含む試験も通過した。回帰を含む3実行の848入力・395出力のサイズとSHA-256を照合し、採取物47,086,670バイトはRTL9210B-CGに置いた。比較16試行の歌唱WAVと、3実行のWASMのSHA-256も一致した。[初回の実行記録](../runs/worklet-safari-song-process-output-block-size-20261122-a/manifest.json)・[反転順の実行記録](../runs/worklet-safari-song-process-output-block-size-20261122-repeat/manifest.json)・[従来条件の回帰](../runs/worklet-safari-song-process-output-20261122-block-size-regression/manifest.json)
