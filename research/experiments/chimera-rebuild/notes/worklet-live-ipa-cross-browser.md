# FirefoxとChromiumで実時間IPA発話を照合する

## 発話と描画の経路

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `speakPhrases` は、音素列から音素区間と調音ジェスチャーを計画し、`AudioEngine.schedule` へ渡す。音素の長さを決めてから母音の連続目標を展開する。Workletの `schedule` は時刻と目標をWASM記録領域へ書き、`engine_schedule` がジェスチャーの始端・終端に `voice.clock + lead` 秒を足す。結果のオフセットで予定音素と発声時計を対応づける。Rustの分割試験は同一時刻の操作を異なるホストブロック長でレンダーし、発話試験は無声破裂音を含むスコアと有気性を検査する。[呼び出し元](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L53)・[音素の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L320)・[Workletのスケジュール](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L134)・[発声時計への移動](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L176)・[ブロック分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[有気性の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/aspiration.rs)

候補では `renderRealtimeIpaVoice` が48 kHzのContextを開き、`prepareIpaVoice` の出力を `FixedProcessor` に渡す。発話スコアは専用合成器のフレーム0から始まり、Context上では起動時に8量子の連続を確認したフレームから2,048フレーム後に対応させる。待機中は無音のまま合成状態を進めない。予定境界に到達すると、出力128フレームずつのコールバックを16フレーム間隔の観測境界でも分けて `renderInto` を呼ぶ。内部96 kHzで進む声門・声道の状態は倍率2の出力段を通り、最後は36フレームを保存して残り92をゼロにする。発話内の時刻は `context_frame − scheduledContextFrame` で得られ、最小唇面積はcm²、声門流量はcm³/sで記録する。停止ボタンは `AbortSignal` 経由で今回のContextを閉じる。停止させた試行の実際の最終出力フレームは保存対象外。[候補のIPA入口と停止処理](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L110)・[予定位置と観測の取得](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts)・[量子内の分割](../../../../web/prototypes/chimera-research/src/fixed-processor.ts)・[Web Audioの時計](https://www.w3.org/TR/webaudio-1.1/#AudioWorklet)

## 事前登録と比較点

以前の実時間Chromiumの入力と成果をハッシュで照合した。今回も通常のIPA画面で未対応入力から復帰し、`ɑpɑ` を実時間とオフラインで保存する。FirefoxとChromiumの試行順は入れ替え、WASMは1ビルドを使う。全PCM49,828点のビット列、16フレームごとの観測、音素とジェスチャー、収録した声門と声道を比べる。唇の閉鎖は最小面積が0.0002 cm²を下回った最初のフレーム、再開口は最初に閾値以上へ戻ったフレームとする。CLIの1フレーム単位の検出に対し、16フレームごとのブラウザ観測には0〜15フレームの遅れを許す。固定上流とCLIのホスト分割は既存の比較を使う。[事前登録](../cases/worklet-live-ipa-cross-browser.json)・[閾値つきの参照ケース](../cases/worklet-ipa-voice.json)・[CLIの閉鎖検出](../tools/measure_bilabial_stop.py)・[以前の実時間Chromium](../runs/worklet-live-ipa-20261119-d/summary.json)

実時間の処理時間は1量子の予算 `1000 × 128 / 48,000 = 2.667 ms` に対し、採取の最初の32量子を除いたp99で判定する。追加のFirefoxプロファイルでは通常画面から最初の発話を一度だけ行い、Geckoの `WorkletNodeEngine::ProcessBlock` を起動待ち・予定待ち・採取量子の合計で照合する。プロファイラーを使う条件は通常の判定と分けた。採取中のフレーム列と物理出力への到達時刻は別の観測量である。[比較コード](../tools/measure_worklet_live_ipa_cross_browser.py)・[Geckoの描画区間](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletNode.cpp)・[既存のFirefox計時の診断](worklet-realtime-cross-browser-96000.md#firefoxのネイティブな時計との照合)

## 拒否からの復帰試験を修正

初回は両ブラウザとも `ɑɹɑ` で警告を出さず、対象の `ɑpɑ` を計測できなかった。`segment_gestures` は現在 `ɹ` に舌のジェスチャーを割り当てる。CLIの `plan ʘ` では該当する音素が0件で、WASMの `prepare_ipa` はこの状態を「発声できるIPA音素がありません」として返すため、拒否の確認を `ʘ` 一字に変えた。警告と発話完了のどちらかを待ち、拒否を期待する入力が描画された場合はその入力を含むエラーを残す。発話本体、測定区間、判定基準は事前登録と同じ。[初回の中断](../runs/worklet-live-ipa-cross-browser-20261121-a/interruption.json)・[子音のジェスチャー](../crates/vocal-core/src/phonetics/speech.rs#L135)・[WASMでの拒否条件](../crates/vocal-wasm/src/planning.rs#L221)・[ブラウザ操作](../../../../web/prototypes/chimera-research/tools/capture-worklet.mjs#L818)

入力変更後はChromiumで保存できたが、Firefoxの復帰試験では、計測器が復帰操作の後に新しい `.wasm` 応答を検知する前提を置いていた。WASMの取得は音素の検査より前なので、応答の待機を最初の入力より前に登録した。これにより、キャッシュが効く場合でも最初の実体をハッシュ対象にできる。[二回目の中断とChromiumの取得結果](../runs/worklet-live-ipa-cross-browser-20261121-b/interruption.json)・[WASMを取得する順序](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L110)

## 音声とフレーム位置の照合

通常画面からChromium 156.0.8078.4とFirefox 157.0で `/ɑpɑ/` を交互に採取した。48 kHz・128フレームで全390量子が連続し、各試行は3840〜4480の間のContextフレームで採取を開始した。起動の確定位置からの差は全試行で2,048フレーム。PCM全49,828点は両ブラウザ、各オフライン、CLIの77・128フレーム分割でビット一致した。3,115行の音響観測と発話の計画・声門・声道系列はブラウザ間で一致した。保存済みChromiumのWASMは別のハッシュを持つが、これらの音声・観測・計画のハッシュは同じだった。[最初の全試行](../runs/worklet-live-ipa-cross-browser-20261121-c/summary.json)

最小唇面積が0.0002 cm²を下回った位置と、戻った位置はブラウザで11,119と13,903フレーム。CLIと固定上流のフレームごとの独立検出は11,118と13,888で、16フレームの観測間隔から予測した1と15フレームの遅れに収まった。最初に差が見える観測点は0フレームの唇の平均断面積・口端流量・放射差分で、唇の平均断面積差は2.22×10⁻¹⁶ cm²だった。放射段を経たPCMで初めてビットが異なるのは13,291フレームで、差は約1.11×10⁻¹⁵、全区間の最大差は1.82×10⁻¹²だった。計画と閉鎖・再開口は既存の許容差内に収まった。上流3組10試験と候補の割り当て計測1試験を通過した。[段ごとの差と判定](../runs/worklet-live-ipa-cross-browser-20261121-repeat/summary.json)・[試験記録](../runs/worklet-live-ipa-cross-browser-20261121-repeat/manifest.json)

## Firefoxのネイティブな時計との照合

生のプロファイルは2試行とも `ProcessBlock` が416区間、内側の `CallProcess` が414区間だった。先頭から414組が一対一に包含され、対応しない2区間は末尾にあった。`FixedProcessor.process` は結果を返してから `false` を返し、Geckoは入力のない非活動状態でJavaScriptを呼ばずに無音を供給する。最初の集計は外側の区間数を直接照合して失敗したため、その判定を保存した。修正後は両方の区間を読み、JSの実行を含む外側の区間で起動待ち8、予定待ち16、採取390の対応を検証する。[最初の判定と生プロファイル](../runs/worklet-live-ipa-cross-browser-20261121-c/manifest.json)・[候補の終了処理](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L212)・[Geckoの活動判定と無音処理](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletNode.cpp#1507)

通常は初回と再実行の各6試行で、冒頭32量子を除いた `Date.now` のp99が2.00 msだった。初回のFirefoxではこの区間でも3 msと記録された量子が4件あり、再実行は0件だった。Firefoxのプロファイル4試行では、同じ区間のネイティブp99は1.284〜1.344 ms、2.667 msを超えた量子はなかった。全区間では各試行で採取開始の1量子が3.566〜3.624 msだった。4試行のうち二つに、`Date.now` で3 msを記録してネイティブ側で予算内の量子が各1件あった。開始間隔を両時計で照合した平均絶対差は0.283〜0.393 msで、前後に1量子ずらすと2.821〜2.908 msに増えた。[通常初回の処理時間](../runs/worklet-live-ipa-cross-browser-20261121-c/summary.json)・[通常再実行とネイティブ区間](../runs/worklet-live-ipa-cross-browser-20261121-repeat/summary.json)

再実行では、冒頭32量子を除いた長いコールバック間隔が両ブラウザとも2量子おきで、`Date.now` の最大は5 msだった。長い間隔の閾値は1量子の予算2.667 msを使い、初回の最大値に基づく集計と併記した。Firefoxのネイティブ区間でも各試行で2量子周期が177件ずつ現れた。比較した96 kHzの固定発声では4量子と8量子だったため、周期をブラウザ単位で固定できない。発声条件とレートを分けるには、同じ出力先・48 kHzの固定発声とIPAの間隔を直接比べる必要がある。[48 kHzの採取結果](../runs/worklet-live-ipa-cross-browser-20261121-repeat/summary.json)・[96 kHzの比較](worklet-realtime-cross-browser-96000.md#通常条件の結果)

ネイティブの割り当て計測は390量子で6,232回、冒頭32量子を除くと5,720回だった。WASMの線形メモリはすべての通常試行で増えなかった。割り当て数は以前の輪郭領域を再利用した比較と一致する。冒頭の約3.6 msの内訳と物理出力への影響は未確認。人による発話・歌唱の試聴も残る。[既存の割り当て削減の比較](contour-buffer-reuse.md)・[今回の記録](../runs/worklet-live-ipa-cross-browser-20261121-repeat/summary.json)

## 再現と保存

macOS 15.6.1 arm64、Rust 1.94.1、Bun 1.4.4、Node 24.19.0、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースから新しい実行IDを指定する。同じスクリプトを絶対パスで `/tmp` から実行し、129判定が通過した。最初の全計測は129件中127件。修正版で生のFirefoxトレースも読み直し、取得済みの414組を照合した。

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 \
  ../../.venv/bin/python tools/measure_worklet_live_ipa_cross_browser.py worklet-live-ipa-cross-browser-next
```

両方の全試行で生成した成果と要約は各85点のサイズとSHA-256を再照合し、WAVは展開後も実時間とオフラインが一致した。音声・観測・プロファイル・密なCSVを可逆圧縮し、全計測2回の実体約76.03 MBをRTL9210B-CGに置いた。初回の2件の中断も各ファイルのハッシュを保って同じディスクに置いた。[確定実行](../runs/worklet-live-ipa-cross-browser-20261121-repeat/manifest.json)・[最初の全試行](../runs/worklet-live-ipa-cross-browser-20261121-c/manifest.json)・[初回の中断](../runs/worklet-live-ipa-cross-browser-20261121-a/interruption.json)・[二回目の中断](../runs/worklet-live-ipa-cross-browser-20261121-b/interruption.json)
