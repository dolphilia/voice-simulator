# 96 kHzの固定母音と倍率1の出力段

## 上流の経路

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のWorkletは実際の `sampleRate` を `engine_new` に渡し、`Engine::make_voice` が `oversample_for` の倍率で `HumanVoice` を作る。96 kHzでは `floor(60000 / 96000) + 1 = 1` となり、内部も96 kHzで進む。固定版の既定ブラウザ出力は48 kHz。今回は96 kHzを明示した研究条件として、上流の `HumanVoice` を同じ内部・出力レートで実行する。[Workletの初期化](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L52)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L138)・[倍率の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L212)・[既定のレート](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L19)

`HumanVoice::render` は `64 × 倍率` 内部サンプルごとに呼気のゲートを更新し、各内部サンプルで肺圧を補間して声門、伝搬、放射を進める。96 kHzの制御間隔は64内部サンプル、約0.667 ms。気道のセル数は内部レートで決まり、咽頭と口腔は各18セルの見込み。上流のテストは倍率の一覧に96 kHzの1を含み、96 kHzの気道で姿勢と体型を変えてクーラン数を検査する。別のブロック分割テストは同じ時刻の操作でPCMが一致することを確認する。[声の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ブロック分割と倍率のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L77)・[気道の安定性テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L175)

`Decimator` は倍率1のとき係数 `[1]`、位相の上限1で、入力と同じ番号で放射差分（cm³/s²）を返す。FIRの群遅延は0サンプル。その後にゲインを掛け、DC除去の `y[n] = x[n] − x[n−1] + exp(−2π × 25 / 96000) y[n−1]`、ピークの保持と減衰を持つリミッターを通し、出力を32ビット浮動小数点に丸める。依存する状態は前回入力、DC除去出力、包絡、保持フレーム数にある。ブラウザの128出力フレームは128内部サンプルに対応し、量子ごとの処理予算は約1.333 ms。[上流の1タップ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L50)・[出力の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L394)・[候補の出力段](../crates/vocal-core/src/output.rs#L27)

## 事前登録

成人男性の固定 /i/、肺圧7.2 cmH₂O、F0 110 Hzで開始する。以前の16 kHz条件と操作を秒でそろえ、96 kHzの出力フレーム8,448でゲートを1、104,448で0にする。減衰76,800フレームを含め合計181,248フレーム、128フレームずつ1,416量子。定常窓は開始後24,000〜40,000フレーム、無音判定は末尾4,800フレームとする。[登録した測定条件](../cases/worklet-realtime-voice-96000.json)・[共通の姿勢と音源](../cases/vowel-voice-i.json)

倍率1と係数 `[1]` を予測する。CLIの全フレームで内部サンプル番号と出力フレーム番号、放射差分と間引き後の値が一致することを検査する。出力段はゲイン後の差分、一次帰還、包絡とPCMへの丸めまで独立計算する。上流とのPCM・状態差、ホスト分割、気道と無音への減衰を計測する。ブラウザはCLIとPCMがビット一致し、発声中の処理時間p99が約1.333 ms以内、ネイティブの描画中の割り当てとWASMメモリ成長が0件と予測する。時間の記録ではクロックの種類と、Contextのフレームの連続性も保存する。

## 再実装と先行CLI検証

実時間発声のレート一覧に96 kHzを加え、固定 /i/ の姿勢とゲート時刻を既存の描画経路へ渡した。CLIは通常の `render` と `render-pcm` を使い、両方のフレームをそろえて放射と出力段を比較した。出力段の独立計算ではゲイン後の入力差分を一次帰還に通し、包絡の保持・減衰とPCMへの丸めを再計算した。[描画を開始する画面](../../../../web/prototypes/chimera-research/src/main.tsx)・[計測器](../tools/measure_worklet_realtime.py)

先行CLIは17項目を通過した。内部サンプルと出力フレームの番号はいずれも0〜181,247、倍率1の出力係数は `[1]`。放射差分と間引き段出力、独立計算とCLIのDC除去・リミッター包絡・保持フレーム数・PCMは全フレームで一致した。DC除去の係数は0.9983650917472037。異なるホスト分割77・128フレームの結果はバイト一致し、ネイティブABIの描画中の割り当ては0件だった。咽頭と口腔は各18セルで、最大クーラン数は咽頭の0.810896。固定上流と独立計算の差は `2.22×10⁻¹⁶` 以下だった。[先行CLI](../runs/worklet-rate-96000-20261120-native/summary.json)

固定上流とのPCMの最初のビット差は出力フレーム9,496、全区間の最大差は `2.91×10⁻¹¹`。密な状態系列では、ゲート開始の13フレーム後の8,461で声門下圧に `6.20×10⁻²⁵ dyn/cm²`、声門上圧に `1.01×10⁻²⁸ dyn/cm²` の差が現れた。次の8,462で声門流量と放射差分にも差を観測した。定常PCMの推定F0は109.99975 Hz、末尾50 msのピークは `3.16×10⁻¹⁰`。[固定上流と候補の時系列・PCM](../runs/worklet-rate-96000-20261120-native/manifest.json)

## ブラウザと再実行

研究ワークスペースと `/tmp` から、ブラウザの13項目がそれぞれ通過した。AudioContext、Worklet、WAVは実測96,000 Hz。181,248フレームのPCMはCLIとビット一致し、声門・呼気など1,416観測点がCLIと一致した。両回で量子のContextフレームは連続し、WAVとフレームごとの音響観測も一致した。WASM線形メモリの成長は両回0件だった。[ブラウザ初回](../runs/worklet-rate-96000-20261120-a/summary.json)・[ブラウザ再実行](../runs/worklet-rate-96000-20261120-b/summary.json)

発声中のp95・p99は両回1 msで、128フレームの予算約1.333 msを下回った。時間はWorkletの `Date.now` で1 ms刻み。全区間の予算超過は初回2件、再実行1件だった。描画開始直後の1件に加え、両回とも減衰中の出力フレーム127,872からの量子で2 msと3 msを観測した。出力フレーム127,872はゲートを閉じて244 ms後で、合成開始後の1,000量子目にも当たる。次の切り分けではゲートを閉じる量子をずらし、外れ値の位置が減衰時刻と量子通算のどちらに追随するかを調べられる。[量子別の元データとハッシュ](../runs/worklet-rate-96000-20261120-b/manifest.json)・[各量子の描画](../../../../web/prototypes/chimera-research/src/live-processor.ts#L55)

CLIの再実行でも17項目を通過し、WAV、間引き段のCSV、内部状態と気道の比較が初回と一致した。[CLIの再実行](../runs/worklet-rate-96000-20261120-native-repeat/manifest.json)

第6段階の確認として、親リポジトリのルートから登録ケースを再実行した。13項目を通過し、PCMと観測は前の2回と一致。発声中のp99は1 ms、減衰中の同じ出力フレーム127,872で4 msを観測した。Contextフレームは連続し、WASM線形メモリの成長は0件だった。48 kHzの実時間固定発声、IPA、歌唱の回帰も通過した。[ルートからの再実行](../runs/worklet-rate-96000-20261120-stage6-root/summary.json)・[48 kHz固定発声](../runs/worklet-rate-96000-20261120-48000-regression/manifest.json)・[IPA](../runs/worklet-rate-96000-20261120-ipa-regression/manifest.json)・[歌唱](../runs/worklet-rate-96000-20261120-song-regression/manifest.json)

後続の計測では呼気停止をずらし、V8のラッパーの呼び出し予算を変えた。既定の1,000量子目に現れる同期コンパイルと、Worklet時計・Chromiumトレースの計測区間の違いを記録した。[呼気停止とラッパーの切り分け](worklet-realtime-release-alignment.md)
