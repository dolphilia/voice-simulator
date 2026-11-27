# 固定上流CHIMERAの通常の歌唱録画をSafariで停止・再開する

## 上流の入口と時計

固定コミットは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。 `SingPanel.sing()` の「Record video」は、Contextの準備と `AudioEngine.quiet()` を待ってから `playTune()` に譜面を渡す。 `quiet()` は直前の音がRMS 0.003未満に150 ms留まったかを20 msごとに壁時計で調べる。 `playTune()` は最初の拍を0.35秒に置いて歌唱ジェスチャーを作り、`onStart` で録画を作成してから `engine.schedule()` を呼ぶ。 `Clip.begin()` は顔のキャンバスのコピーから30 fpsの映像を採り、マスター出力の音声分岐と一緒に録画する。歌唱の進行を追う `tickSinging()` は譜面の末尾からエンジン時計で0.4秒経過すると `onEnd` を呼び、最後のチャンクを待って「Save」を出す。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/SingPanel.tsx#L157)・[歌唱の予約と終了](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[quietと音声分岐](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L323)・[Clip](../../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts#L60)

音声側は `ChimeraProcessor.handle()` が主スレッドから譜面を受け取り、WASMの `engine_schedule()` を呼ぶ。Rustの `Engine::schedule()` はエンジン時刻に30 msの先行時間を足した値を譜面の時刻0にし、各ジェスチャーの開始・終了時刻を移す。 `process()` は出力バッファ長を `engine_render()` に渡して、そのPCMを出力にコピーする。観測では、譜面受信後の最初の描画でContextの絶対フレームを `C`、エンジンの時刻を48,000倍して丸めたフレームを `E` とした。譜面の時刻0はContext上で `C + round(譜面の予約時刻 × 48,000) − E`。2つの時計の初期差もこの式に含む。固定上流の試験は描画ブロック長に依存しないPCMと短音の拍位置をそれぞれ検証する。[Workletの予約](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L198)・[Rustの時刻移動](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[拍位置の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L30)

## 事前登録と取得方法

研究版の保存結果に合わせて「Pop Dee」、240 BPM、MIDI 60・64を各0.25拍、48 kHz出力とした。固定上流の通常の歌唱画面にテスト用の譜面をブラウザ内の曲リストに追加し、Safariの信頼済み操作で「Record video」を押した。固定上流の先行区間は0.35秒、研究版は0.50秒なので、研究版の停止目標28,672フレームからその差7,200フレームを引いて上流の目標を指定した。停止完了から再開要求まで120 msを目安に待つ。肺圧、調音の初期設定、乱流などは上流の通常画面の設定を使った。合成波形は各実装の録画直前のものを基準にし、比較は同じ拍からの停止位置と録画時刻に絞った。[登録ケース](../cases/upstream-safari-song-recording-pause.json)・[研究版の基準](worklet-live-song-fast-safari-recording-pause.md)

固定上流の作業ツリーは変更せず、Viteで配信するWorkletに計測を追加した。WASMの描画結果をメモリーから複写し、量子のContextフレーム、エンジンフレーム、コピーしたサンプル数、コールバック時の壁時計を保存した。録画キャンバスの一角に壁時計とContext時計を白黒マスで描き、通常の「Save」が参照するBlobを取得した。音声は譜面の時刻0を基準にした0.32〜0.43秒と0.50〜0.62秒を使い、AACを復号したサンプル順と、そのサンプルに対応する整数PTSの両方でオフセットを算出した。録画の音声に停止時間が加わらず、停止の両端12 msを除いて録画に残る映像が2枚以上でPTS幅60 ms以下になると予測した。[採取](../../../../web/prototypes/chimera-research/tools/capture-upstream-safari-recording-pause.mjs)・[解析](../tools/measure_upstream_safari_recording_pause.py)

## 実測

窓を修正した2実行の各36件の取得判定と6件の予測はすべて通過した。停止あり4試行の保持時間は120〜122 ms、止まった位置は研究版換算28,672〜28,928フレームだった。Contextの番号は停止中同じ値に留まり、前後のWorkletとエンジンの番号はともに128フレーム刻みで続いた。隣接する描画コールバックの壁時計間隔は停止を挟むと142〜147 ms、連続試行の最大は各3 msだった。[修正後の初回](../runs/upstream-safari-song-recording-pause-20261121-b/summary.json)・[別ディレクトリからの再実行](../runs/upstream-safari-song-recording-pause-20261121-repeat-b/summary.json)

| 観測 | 固定上流の結果 | 研究版の保存結果 |
| --- | --- | --- |
| 録画音声 | 停止前後の窓間オフセットの変化は全8試行で0サンプル。隣接AACフレームの時刻はサンプル数から求めた値と一致 | 復号音声とPTSに停止分の増加は0 |
| 停止付近の録画映像 | 停止中に描画された壁時計65〜84 ms幅の3枚が、各試行でPTS3.33 ms幅に収まった | 停止位置付近の進捗バー4〜5枚のPTS幅は5.0〜8.3 ms |

固定上流は壁時計マーカーで描画時点を選び、研究版は進捗バーの位置でフレームを選んでいる。どちらも音声と映像に壁時計どおりの停止時間は加わらず、映像に停止中の描画が短いPTS幅で残った。上流のAACを各試行のPCMに照合した正規化相関は0.9957〜0.9995。AACの総サンプル数は録画の開始・終了時刻に応じて変動するため、停止時間の算入は同一試行内の前後の窓間差とフレームPTSで確認した。[上流の停止付き動画](../runs/upstream-safari-song-recording-pause-20261121-repeat-b/artifacts/1-paused/recording.mp4)・[研究版の比較](../runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/summary.json)

### 加工前PCMに現れた差

連続と停止を組ごとに比べると、修正後の4組のうち1組は全29,760サンプルでビット一致した。差が出た3組は譜面の時刻0から11,692〜14,262サンプルで最初のビット差が出て、絶対差が0.000001を初めて超えた位置は14,317〜14,342サンプル。上流の停止位置は時刻0から約21,500フレームであり、差は停止より前にあった。音素の種類と開始・終了フレームは全試行で同じだった。

同じエンジンフレームで譜面の描画を受けた試行を集めると、8,064フレームで開始した4試行は停止あり・なしを含めてビット一致し、7,936フレームの連続条件2試行も一致した。上流の気道は、出力への乱流注入が0のときでも内部の乱数とフィルタを更新する。録画前に描画がどこまで進んだかで内部状態が変わることと、今回の結果は整合する。声門の位相や乱流源のどれが最初の差を作ったかは未特定。[Quiet](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L323)・[乱流の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[声門の周期更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L182)

## 取得範囲の修正と独立照合

修正前の初回と再実行では、Workletのコピーが譜面末尾0.475秒に120 msを足した0.595秒までだった。後半の登録窓が0.62秒まであるため、既存の配列切り出しは不足した25 msを取り込まずに判定を通した。コピーは譜面の末尾に加える時間と登録窓の末尾の、長い方まで延ばし、後半まで揃わない場合は解析を失敗にした。測定窓と判定基準は事前登録のまま。変更前の2実行も保存した。[修正前の初回](../runs/upstream-safari-song-recording-pause-20261121-a/summary.json)・[修正前の再実行](../runs/upstream-safari-song-recording-pause-20261121-repeat/summary.json)

保存動画から、マスの中央を縮小なしで読み直し、整数PTSと時間単位からフレーム間隔を有理数で照合した。サンプル数から各AACフレームの時刻を再計算し、復号PCMをゲイン補正した二乗誤差で整列して、相関法との差が1サンプル以内であることを確認した。固定上流でWASMを再ビルドし、Safariが取得したファイルのSHA-256とビット一致を確認した。ブロック長と拍位置のテストは各1件通過し、共通解析の変更後の前回9録画の要約も保存済みとバイト一致した。[再実行の証跡](../runs/upstream-safari-song-recording-pause-20261121-repeat-b/manifest.json)・[共通解析の回帰比較](../runs/safari-recording-pause-clock-split-20261121-upstream-regression/manifest.json)

## 再現と保存先

Safari 18.6（20621.3.11.11.3）、macOS 15.6.1 arm64、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1、FFmpeg 7.1。固定上流に構築済みの依存とWASMを使う。研究ワークスペースから未使用の実行IDを指定する。別ディレクトリでの再実行ではPythonとスクリプトを絶対パスで指定した。固定上流の4実行で各18入力・27出力をサイズとSHA-256で照合し、9,631,129バイトをRTL9210B-CGに保存した。前回の回帰比較3,804,298バイトも同じディスクに保存した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=30000000 ../../.venv/bin/python \
  tools/measure_upstream_safari_recording_pause.py <実行ID>
```

次の対照は、固定上流の同じ譜面をエンジンの同じフレームに受け渡し、連続描画と途中停止を比較する。通常画面からの今回の結果を残し、描画開始から譜面を受け取るまでのフレーム数だけを固定して、図形や録画の時刻と独立にPCMの一致を調べる。
