# ブラウザの英語テキストを発話へ接続する

## 固定上流の読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。画面の `speakText` は `EnglishG2P.load` で辞書を取得し、WASMの `g2pLoad`、`g2pPhrases` を呼ぶ。Rustの `to_phrases` はアポストロフィと数を正規化し、句読点で区切って辞書と発音規則を適用し、語末・強勢・異音を付ける。`?` は疑問で、`.`、`!`、`?` の後の休止は0.35秒。続く `plan_phrases` は句ごとの計画を連結し、次の開始を前の終了と休止の和にする。画面は計画済みのジェスチャーをWorkletへ予約する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L53)・[辞書の読込と句への変換](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/engine.ts#L76)・[WASM API](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/api.rs#L126)・[上流の句分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs#L132)・[句の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L880)

発話計画の疑問・平叙では句末方向のF0目標を基準の1.35倍・0.82倍とする。112 Hzなら151.2 Hzと91.84 Hz。実際の声門F0は制御周期ごとの対数補間と音高目標の有効度に従う。軟口蓋のポート面積はcm²、外へ放射される鼻端の体積速度はcm³/s。軟口蓋に開きの目標を受けた後に声道形状とポートを更新し、気道の音響状態を進めてから観測を採取する。上流の `words.test.ts` は句間の時刻と語末対応、`consonant_artifacts.rs` は語からの発音変換を通した子音、`engine.rs` は入力と時刻が同じ場合の分割不変性を検査する。[句末のF0](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L637)・[語の時間対応](../../../../docs/reference/chimera-vocal-synth/upstream/tests/words.test.ts)・[子音のRustテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/consonant_artifacts.rs)・[分割不変性](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

既存の `Mom? Pop.` を使う。出力48 kHz、内部96 kHz、79,222フレーム、32フレーム間隔で観測。辞書から2語を得て `mˈɑm? | pˈɑp` を出力し、基準F0の112 Hzには発声開始時の110 Hzから追従する。句の計画・ジェスチャーをCLIに照合し、PCMのビット一致を予測する。独立YINで0.30〜0.39秒のF0が145〜156 Hz、1.19〜1.26秒が87〜101 Hz。0.135〜0.17秒には鼻端流量100 cm³/s以上、ポート0.3 cm²以上のピークがあると予測する。句間と語尾の静かな区間も測り、未対応の `Strut` のエラー後に同じ画面から再試行する。固定上流との比較は既存ケースの許容差を使用する。[今回の条件](../cases/worklet-english-voice.json)・[既存CLIケース](../cases/english-mom-pop.json)・[CLI・上流の先行結果](../runs/english-frontend-20261119-g/summary.json)

## ブラウザの計画と観測

画面メインスレッドから、歌唱と共通のローダーで辞書を取得する。gzipの展開済みUTF-8とテキストを計画用WASMへ渡す。辞書未取得時は画面にエラーを出し、再試行で読込をやり直せるようにした。CLIとWASMは `english::plan_voice` を共有し、辞書と句の計画から同じ調音・声門・呼気ジェスチャーを得る。Workletはその数値スコアを受け取り、初期F0を110 Hzとして制御を開始する。軟口蓋のポート面積と鼻端流量は計画から推定せず、声道と音響を進めた後の状態を出力フレームに対応させて保存した。画面では発音と口唇・PCMの時系列を表示する。[共通の英語発話計画](../crates/vocal-core/src/phonetics/english.rs)・[WASMの英語計画](../crates/vocal-wasm/src/planning.rs)・[WASMの音響観測](../crates/vocal-wasm/src/lib.rs)・[ブラウザの入力と辞書](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts)

## 実測結果

Chromium 156.0.8078.4で初回と `/tmp` からの再実行は各15項目を通過した。両回のWAVと観測JSONのSHA-256は一致した。表示は `mˈɑm? | pˈɑp` で、両語とも辞書由来。句間の計画休止は0.350秒。発話計画とジェスチャーのCLIとの差は0で、固定上流の音素区間とジェスチャーにも一致した。ブラウザで保存したPCM 79,222フレームはCLIにビット一致し、2,476点の内部状態10系列も差0だった。まず `Strut` の /ɹ/ を未対応と表示し、そのまま `Mom? Pop.` に差し替えて再試行できた。[初回](../runs/worklet-english-voice-20261119-a/manifest.json)・[再実行](../runs/worklet-english-voice-20261119-b/manifest.json)・[画面](../runs/worklet-english-voice-20261119-b/artifacts/browser.png)

| 量 | 区間 | 実測値 |
| --- | --- | ---: |
| 疑問句のPCMからのF0 | 0.30〜0.39秒 | 150.38 Hz |
| 平叙句のPCMからのF0 | 1.19〜1.26秒 | 93.96 Hz |
| /m/ の軟口蓋ポートの最大面積 | 0.135〜0.17秒 | 0.4480 cm² |
| /m/ の鼻端流量の絶対ピーク | 0.135〜0.17秒 | 310.96 cm³/s |
| 句の間のPCM絶対ピーク | 0.72〜0.79秒 | `1.40×10⁻⁶` |
| 語尾減衰後のPCM絶対ピーク | 1.60〜1.65秒 | `1.70×10⁻⁸` |

固定上流とのPCM最大絶対差は `2.33×10⁻¹⁰`（許容差 `1×10⁻⁶`）。最初のPCMビット差は27,864フレームで、内部系列では出力フレーム0ですでに口唇断面積に `2.22×10⁻¹⁶ cm²`、放射微分に `4.75×10⁻¹² cm³/s²` の差があった。固定上流の関連19テストも通過した。[数値と最初の差](../runs/worklet-english-voice-20261119-b/summary.json)

CLIの発音変換、ブラウザIPAの時系列、歌唱、手動調音ケースの書き出しの回帰も通過した。英文の計測は対応済み音素からなる二句のオフライン発話を対象とする。[CLI英語](../runs/english-frontend-20261119-web-regression/summary.json)・[IPAの時系列](../runs/worklet-ipa-timeline-20261119-english-regression/summary.json)・[歌唱](../runs/worklet-song-voice-20261119-english-regression/summary.json)・[ケース書き出し](../runs/worklet-manual-case-export-20261119-english-regression/summary.json)

```bash
python3 tools/measure_worklet_english.py worklet-english-voice-local-1
```

## 確認用07の発話ケースの読み込みと再演

英語発話画面にCLIの発話ケースを開く入力を加えた。確認用07は、成人女性、舌先の休止位置 (6.241412821929657, 6.810460479056529) cm、ゲイン `4.8125×10⁻⁷`、ドリフト5セント、周期ジッター0.00455、振幅シマー0.042を指定した全107,527フレームの既存ケースを使った。発話は既存のオフライン経路を使い、量子128フレームの中で既存の32フレーム間隔の観測を採取した。全PCMのCLIとのビット一致と、冒頭440 msの声門状態を独立に保存した周期境界へ照合することを事前に登録した。[登録ケース](../cases/worklet-tsp-source-defaults.json)・[読み込むCLIケース](../runs/tsp-fine-source-defaults-20261122-final/artifacts/source-defaults-case.json)

固定上流の `speakText` は辞書で英文を音素句へ変換し、`speakPhrases` が時刻0を原点とした調音・呼気・音高の計画を作ってエンジンに渡す。今回の音響基準は、女性体型の声門を生成し50 msの開始時刻で発話計画を渡す上流のオフライン `render::say` の保存結果を使った。上流テストでは辞書によるストレス・異音、句と疑問イントネーション、ホストのブロック長に対する出力の不変性を確認した。[上流のブラウザ入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L53)・[上流のCLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[英語の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/english.rs#L26)・[ブロック長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `readEnglishSpeechCase` が発話の本文、体型、姿勢、音源と出力の各設定を読み、`renderEnglishVoice` が辞書とWASM計画器で発音列と調音スコアを作る。Workletへ初期F0 110 Hz、基準205 Hz、揺らぎの3値を渡す。 `vocal_start_score_prepared` は声門に各係数を設定し、事前描画0フレームでスコアを開始する。位相は内部サンプルごとに `F0 / (96000 × 周期倍率)` だけ進む。声門の面積（cm²）と流量（cm³/s）を計算し、放射の時間差分を間引いて48 kHzのPCMを作る。観測の出力フレーム `n` には、そのフレームを確定した内部サンプル `2n+1` の状態を記録する。PCMは1チャンネルのオフライン出力から、そのままWAVへ保存した。[ケース入力](../../../../web/prototypes/chimera-research/src/english-speech-case.ts#L35)・[英語描画](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L222)・[WASM声門の初期化](../crates/vocal-wasm/src/lib.rs#L384)・[WASMの出力と観測](../crates/vocal-wasm/src/lib.rs#L965)・[Workletの観測時計](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L246)

Chromiumの加工前PCMは、ダウンロードしたケースをCLIで再演したPCMと、元のCLI保存PCMの両方に全フレームでビット一致した。発話の本文・音素・ジェスチャーが一致し、再実行ケースには揺らぎ3値、休止位置、ゲインを含むすべての発声設定が残った。元ケースが省略した開始時刻は既定の0.05秒として明示された。観測3,361点のうち冒頭440 msの660点で、呼気・F0・位相・声門面積・流量・放射が研究版CLIの内部状態と一致した。独立計算の折り返し90回を観測の時刻に対応付けた。最初の内部サンプル830の折り返しは、出力の観測フレーム415で見えた。[波形・計画・状態の照合](../runs/worklet-tsp-source-defaults-20261122-a/summary.json)・[ブラウザが保存したケース](../runs/worklet-tsp-source-defaults-20261122-a/artifacts/browser-case.json)

固定上流との最初のPCMビット差は出力フレーム53,463で、全発話の最大絶対差は `1.16×10⁻¹⁰`、二重母音区間では差0だった。冒頭440 msのブラウザ観測上、最初の内部物理量の差は出力フレーム2,463の声門流量と放射の時間差分だった。両版のF0・位相・面積はこの窓で一致した。実時間の発声時計と機器出力は未観測。[波形と状態の差](../runs/worklet-tsp-source-defaults-20261122-repeat/summary.json)・[ブラウザの表示](../runs/worklet-tsp-source-defaults-20261122-repeat/artifacts/browser.png)

既存の英語発話テストの初回は、/ɹ/ を含む `Strut` が現在のコアで発声できるため、拒否を待っている段階で停止した。初回のケースとログを保存した。CLIの発音計画で `Measure.` の /ʒ/ が現行の未対応一覧に入ることを確認し、第2版は拒否確認の文だけを変更した。拒否の表示後に `Mom? Pop.` へ差し替え、15判定と固定上流19試験が通過した。ブラウザのPCM、CLIと上流の状態系列など9出力は先行の基準とバイト一致した。[初回の中断](../runs/worklet-english-voice-20261122-tsp-source-defaults-regression/manifest.json)・[第2版の回帰](../runs/worklet-english-voice-20261122-tsp-source-defaults-regression-v2/summary.json)

確認用07は研究ワークスペースと `/private/tmp` から各10判定、上流16試験・研究版WASM 27試験を通過した。要約・ケース・PCM・観測・画面など9出力が一致した。macOS 15.6.1 arm64、Chromium 156.0.8078.4、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。4実行の1,090入力・49出力をサイズとSHA-256で照合し、採取物103,241,798バイトをRTL9210B-CGに保存した。[初回](../runs/worklet-tsp-source-defaults-20261122-a/manifest.json)・[別ディレクトリからの再実行](../runs/worklet-tsp-source-defaults-20261122-repeat/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456
../../.venv/bin/python tools/measure_worklet_tsp_source_defaults.py worklet-tsp-source-defaults-new
../../.venv/bin/python tools/measure_worklet_english.py worklet-english-tsp-regression-new
```

## 確認用07の実時間発声と開始時刻

前回ブラウザから書き出した確認用07の英語ケースを読み込み、「読み込んだケースを実時間で発声」から再生する。舌先の休止位置、ゲイン、ドリフト、ジッター、シマー、本文、発話内の開始時刻は保存ケースと同じ。ChromiumとFirefoxでオフライン版・CLIと同じPCMを得られ、準備完了から2,048フレーム後に採取を開始し、発話内の最初の非ゼロが2,439フレームになると事前に登録した。[事前登録](../cases/worklet-live-tsp-source-defaults.json)・[前回のブラウザケース](../runs/worklet-tsp-source-defaults-20261122-repeat/artifacts/browser-case.json)

上流の `speakPhrases` はメインスレッドの計画を `AudioEngine.schedule` へ渡す。Workletの `schedule` メッセージは `engine_schedule` を呼び、既定0.03秒を現在の発声時計に加え、その秒数を各ジェスチャーの始端と終端に加えて登録する。発話開始と音素境界を同じオフセットでメインスレッドに返す。 `Engine::render` はホストの出力要求を内部の制御ブロック境界で区切る。既存テストは辞書による音素・句の計画と、ホスト要求長が変わっても発声出力が変化しないことを確かめる。[上流の操作](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/speech.ts#L53)・[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[上流の時刻加算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L175)・[ホスト分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版は、オフラインと実時間で `prepareEnglishVoice` を共有する。実時間では連続した8量子を確認した次の境界を `armed` とし、`armed + 2,048` をContext上の採取開始とする。待機中の出力は無音で、専用合成器は進めない。採取時はContextの第 `k` 量子が `scheduled + 128k`、発話内の有効フレーム累計が `min(128(k+1), 107527)` になる。48 kHzの出力番号 `n` に内部96 kHzのサンプル `2n+1` の状態を記録する。WAVに保存するのはWorkletから出力したFloat32の有効区間で、停止は `AbortSignal` 経由でContextを閉じる。上流の0.03秒は現在の発声時計への加算、研究版の2,048フレームは新しいContextの安定後の待ち時間である。[共通の英語発話計画](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L232)・[準備時計](../../../../web/prototypes/chimera-research/src/worklet-clock.ts#L3)・[開始とPCM記録](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)

初回のChromiumでは実時間PCMがオフライン版と一致した。Firefoxでは、最初のオフライン描画に続くWASM取得をPlaywrightの新しい応答イベントで待ち、30秒で止まった。ブラウザのエラー欄は空だった。再計測は、最初の応答と、オフライン・実時間の各 `WebAssembly.compile` に届いたバイト列のSHA-256を保存する。これにより同じURLからキャッシュを経由したときも両方の実体を照合できる。[初回の中断](../runs/worklet-live-tsp-source-defaults-20261122-a/manifest.json)・[Firefoxの中断ログ](../runs/worklet-live-tsp-source-defaults-20261122-a/artifacts/firefox/browser-error.json)

ChromiumとFirefoxの実時間PCMは全107,527フレームでバイト一致し、各ブラウザの保存ケースを通常CLIで再演したPCMと、前回のオフラインPCMにも一致した。発話内の観測3,361行と声門系列もオフライン版とビット一致した。固定上流とは出力フレーム53,463で最初のビット差が出て、最大絶対差は `1.16×10⁻¹⁰`。両ブラウザとも先頭50 msが無音で、最初の非ゼロは発話内フレーム2,439（50.8125 ms）。採取する841量子に欠落はなく、最終量子は先頭7フレームだけを保存した。別の再生では実時間Contextが進んでいることを確認して停止し、両ブラウザのContextが閉じることを確かめた。[両ブラウザの比較](../runs/worklet-live-tsp-source-defaults-20261122-b/summary.json)・[ChromiumのContext時計](../runs/worklet-live-tsp-source-defaults-20261122-b/artifacts/chromium/browser.json)・[FirefoxのContext時計](../runs/worklet-live-tsp-source-defaults-20261122-b/artifacts/firefox/browser.json)

| 観測量 | Chromium | Firefox |
| --- | ---: | ---: |
| 採取開始のContextフレーム | 5,760、6,016 | 4,992、4,864 |
| 準備完了から採取開始までのフレーム数 | 2,048 | 2,048 |
| 連続した8量子を確定する前の時計の不連続 | 両試行で1回 | 両試行で0回 |
| 冒頭32量子を除いた処理時間のp99 | 2 ms、2 ms | 2 ms、3 ms |
| 同じ区間で2.667 msを超えた計測値の件数 | 0、0 | 7、14 |

時間の値はWorklet内の `Date.now()` で記録した。Firefoxの再実行のp99はこの時計で量子予算を超えた。3 msの記録はミリ秒刻みのため、同じ量子のネイティブ処理時間の照合が残る。Contextの採取時計、保存PCM、処理時間は測定済み。音声機器端子の到達時刻と聴感は未観測。[初回合格の計時](../runs/worklet-live-tsp-source-defaults-20261122-b/summary.json)・[別ディレクトリの計時](../runs/worklet-live-tsp-source-defaults-20261122-repeat/summary.json)

研究ワークスペースと `/private/tmp` から各21判定、上流11試験と研究版WASM 27試験が通過した。実時間の両ケース、両WAV、CLI再演など13出力がバイト一致した。オフラインの回帰も10判定を通過し、前回の要約、PCM、観測JSONなど8出力がバイト一致した。macOS 15.6.1 arm64、Chromium 156.0.8078.4、Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。初回の中断分を含む4実行の1,104入力・66出力をサイズとSHA-256で照合し、採取物59,262,298バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](../runs/worklet-live-tsp-source-defaults-20261122-repeat/manifest.json)・[オフラインの回帰](../runs/worklet-tsp-source-defaults-20261122-live-regression/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456
../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-source-defaults-new
../../.venv/bin/python tools/measure_worklet_tsp_source_defaults.py worklet-tsp-source-defaults-live-regression-new
```

## 確認用07のFirefoxネイティブ計時

通常の確認用07で、Firefoxの再実行は最初の32採取量子を除く809量子のp99が3 msだった。各量子の予算は `1,000 × 128 / 48,000 = 2.667 ms`。同じ保存ケースを読み込み、実時間再生1回のWorklet記録とGeckoプロファイルを同時に採った。冒頭32量子以降のネイティブp99が予算内に収まり、`Date.now()` の超過の一部は同じ量子のネイティブ計時で予算内に収まると予測した。[事前登録](../cases/worklet-live-tsp-firefox-native-clock.json)・[通常再生の計測](../runs/worklet-live-tsp-source-defaults-20261122-repeat/summary.json)

固定上流の `process` はホストから渡された出力チャンネルの長さを `engine_render` へ渡し、WASMのFloat32を出力へコピーする。 `Date.now` の経過ミリ秒を量子予算で割り、平滑化した負荷をテレメトリに使う。Rustの入口は許容フレーム数の範囲でエンジンを進め、PCM領域のポインタを返す。固定上流のテストは128フレーム分割の基準と1、77、4,096、48,000フレーム分割のPCMをビット照合している。今回の処理時間は入力ケースを再生する研究版Firefoxの中で測り、前回の通常再生を音声比較の基準とした。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASMの描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[ホスト分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Geckoの `WorkletNodeEngine::ProcessBlock` は、ポートの準備や出力処理を含む外側の区間。内側の `AudioWorkletNodeEngine::CallProcess` はJavaScriptの `process` 呼び出しを含む。研究版の `Date.now()` は `FixedProcessor.process` 内の開始からPCMとタイミング行を記録する段までを計る。プロファイルの外側・内側の開始と終了はミリ秒で取得し、起動待ち・予定待ち・採取841量子の順に対応付けた。内側の各区間が別々の外側の区間に含まれることを検査し、開始間隔の平均絶対差を前後1量子ずらした対照と比較した。Workletが停止した後にJavaScript呼び出しを伴わない区間は採取量子に含めない。[Geckoの外側の処理](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletNode.cpp#841)・[GeckoのJavaScript呼び出し](https://searchfox.org/firefox-main/source/dom/media/webaudio/AudioWorkletNode.cpp#1476)・[研究版の時計](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L50)

初回は2試行分のPCM、プロファイル、量子対応表を保存した後、集計のJSON書き出しでNumPyの真偽値をエンコードできず終了した。量子予算をPythonの浮動小数点数に変換してから判定し、試験条件と許容差を維持して再実行した。初回の表を読み直した結果、定常区間のネイティブp99は1.772、1.713 msで、`Date.now()` だけが超過を示した定常量子は0、3件だった。採取開始の最初の量子は3.395、3.627 msで、両試行ともネイティブ時計で予算を超えた。[初回の中断記録](../runs/worklet-live-tsp-firefox-native-clock-20261122-a/manifest.json)・[初回の量子表1](../runs/worklet-live-tsp-firefox-native-clock-20261122-a/artifacts/firefox-1/aligned-quanta.csv)・[初回の量子表2](../runs/worklet-live-tsp-firefox-native-clock-20261122-a/artifacts/firefox-2/aligned-quanta.csv)

修正後の4試行では、オフライン描画のスレッドにはJavaScript呼び出しが841件あり、実時間スレッドには865件あった。起動待ち8件と予定待ち16件を除くと841件。採取区間のすべてで内部の呼び出しが外部の処理区間に一対一で含まれていた。開始間隔の平均絶対差は0.416〜0.446 msで、前後に1量子ずらすと2.695〜2.879 msになった。PCM、発話内の観測と計画、WASM、保存し直したケースは通常再生の保存結果と一致した。[最初の合格](../runs/worklet-live-tsp-firefox-native-clock-20261122-b/summary.json)・[別ディレクトリの再実行](../runs/worklet-live-tsp-firefox-native-clock-20261122-repeat/summary.json)

| 試行 | 定常区間の `Date.now()` p99 | 定常区間のネイティブp99 | `Date.now()` だけで予算を超えた定常量子 | 採取開始のネイティブ時間 |
| --- | ---: | ---: | ---: | ---: |
| 最初の合格1 | 2 ms | 1.681 ms | 1 | 3.633 ms |
| 最初の合格2 | 3 ms | 1.767 ms | 11 | 4.020 ms |
| 再実行1 | 2 ms | 1.680 ms | 5 | 3.553 ms |
| 再実行2 | 2 ms | 1.683 ms | 3 | 3.659 ms |

定常区間のネイティブ超過は4試行とも0件だった。採取開始の最初の量子は4試行すべてで実際に予算を超え、うち1試行は次の量子も2.679 msだった。外側と内側の両マーカーで同じ超過を確認した。最初の量子では、内側と外側の差は0.004 ms未満だった。負荷がJavaScriptの呼び出しに含まれることまでは確認できた。WASM入出力、音響コア、テレメトリの内訳は未計測。プロファイラーを使っていない過去の試行は、各量子のネイティブ時間を復元できない。[p99が3 msとなった同一試行の量子表](../runs/worklet-live-tsp-firefox-native-clock-20261122-b/artifacts/firefox-2/aligned-quanta.csv)・[対応する圧縮プロファイル](../runs/worklet-live-tsp-firefox-native-clock-20261122-b/artifacts/firefox-2/firefox-profile.json.gz)

研究ワークスペースと `/private/tmp` から、各13判定と固定上流11試験が通過した。通常再生の回帰は21判定を通過し、前回のPCM、保存ケース、再演など12出力がバイト一致した。以前のIPAの保存プロファイルを今回の比較器で読み直し、定常区間の外側と内側の時間の集計が旧比較器と一致することも確認した。macOS 15.6.1 arm64、Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。4実行の1,103入力・82出力をサイズとSHA-256で照合し、採取物55,558,340バイトをRTL9210B-CGへ保存した。圧縮した12ファイルを展開し、量子表の差分とp99を再計算した。[再実行の記録](../runs/worklet-live-tsp-firefox-native-clock-20261122-repeat/manifest.json)・[通常再生の回帰](../runs/worklet-live-tsp-source-defaults-20261122-native-clock-regression/manifest.json)・[再計算したIPAの保存プロファイル](../runs/worklet-live-ipa-cross-browser-20261121-repeat/artifacts/native-firefox-1/firefox-profile.json.gz)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_native_clock.py worklet-live-tsp-firefox-native-clock-new
../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-native-regression-new
```

## 確認用07の先頭量子の処理内訳

確認用07をFirefoxで再生し、マーカーのない対照とマーカーを入れた診断を順序を変えて採る。出力フレーム0、128、4,096、4,224から始まる4量子を選んだ。先頭量子のJavaScript呼び出し時間を定常の2量子の中央値と比較し、その増分の半分以上がWASMの `vocal_render` の呼び出しで説明できると予測した。ケース、発話計画、辞書、WASM、観測間隔は共通。音声と発声状態は通常時の保存結果へ照合する。[事前登録](../cases/worklet-live-tsp-firefox-render-phases.json)・[前回の量子対応表](../runs/worklet-live-tsp-firefox-native-clock-20261122-repeat/summary.json)

固定上流のWorkletは出力チャンネル長を `engine_render` に渡し、WASMのFloat32領域から出力へコピーする。Rustの入口はその出力フレーム数だけ `Engine::render` を進める。ブロック長のテストは分割間でPCMがビット一致することを確かめる。研究版の `FixedProcessor` は128出力フレームの量子を観測境界で32フレームずつの4区間に切る。各区間の `vocal_render` は内部96 kHzで64サンプルを進め、PCM、声門系列、最後の観測値をWASM内に書く。ホスト側はPCMをWeb Audioへコピーし、声門系列と状態観測を保存する。量子の最後は `RealtimeSpeechCapture.record` が採取用のPCMとフレーム時計を記録する。[上流Workletの描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[上流の分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[研究版WASMの描画](../crates/vocal-wasm/src/lib.rs#L965)・[ホストへのコピー](../crates/vocal-wasm/host/fixed-voice.ts#L444)

歌唱の計測で使ったタイムスタンプの仕組みを、英語発話の診断時にも使えるようにした。 `vocal_render` 前後、Web AudioへのPCMコピー、声門系列転送、状態観測、実時間採取に印を付ける。診断では各印を同じ `GraphRunner` の `CallProcess` 区間に対応付け、予定待ちの最後の量子にも連続8個の校正用の印を置いた。PCMや観測の保存に使う領域と、描画の分割は両条件で共通。選んだ4量子には768フレーム間隔の声道断面の取得は入らなかった。WASMの計時区間には呼び出し境界とABI内で観測値を作る処理も含まれる。[Workletの印と分割](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L241)・[実時間PCMの採取](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L50)・[解析コード](../tools/measure_worklet_live_tsp_firefox_render_phases.py)

| 先頭量子の観測値 | 診断4試行の範囲 |
| --- | ---: |
| JavaScript呼び出し全体 | 3.757〜3.962 ms |
| `vocal_render` 4回の合計 | 3.262〜3.419 ms |
| Web AudioへのPCMコピーの合計 | 0.090〜0.126 ms |
| 声門系列のコピーの合計 | 0.057〜0.070 ms |
| 状態観測（声門系列の転送を除く） | 0.041〜0.050 ms |
| 実時間PCMと時計の採取 | 0.026〜0.035 ms |

定常2量子の中央値に対し、先頭のJavaScript呼び出しは2.273〜2.383 ms長かった。そのうち `vocal_render` の増分は1.965〜2.140 msで、全体の85.6〜89.8%を占めた。PCMコピーの増分は0.062〜0.098 ms。状態観測は−0.012〜0.029 ms、声門系列の転送は0.042〜0.053 msだった。印の隣接間隔は最大0.0196 ms。マーカーを入れた条件と対照の先頭量子の中央値差は、実行ごとに0.121 msと0.321 msで、事前の0.6 ms以内だった。印を付けた4試行すべてでPCM、状態観測、ケースは通常再生と一致した。[最初の計測](../runs/worklet-live-tsp-firefox-render-phases-20261122-a/summary.json)・[別ディレクトリの計測](../runs/worklet-live-tsp-firefox-render-phases-20261122-repeat/summary.json)

差は最初の32フレームを描画する呼び出しで既に現れた。この区間だけで定常部の同じ位置より0.718〜0.795 ms長かった。0・64フレームから始まる呼び出しは声道などの制御更新を含む。2区間の増分の和は、位置ごとに定常部を引いたWASM増分の約64〜65%だった。32・96フレームから始まる区間でも時間が増えた。今回の時刻の境界はWASM呼び出しまでなので、制御更新、気道の内部ステップ、WASM呼び出しの初期コストの内訳はまだ測っていない。[声道を更新する制御ブロック](../crates/vocal-core/src/voice.rs#L605)・[WASMの制御フレーム数](../crates/vocal-wasm/src/lib.rs#L27)・[4区間の記録](../runs/worklet-live-tsp-firefox-render-phases-20261122-repeat/summary.json)

歌唱の既存試験の初回は58判定中57件が通過し、旧基準実行のWASMと現在のWASMのハッシュ照合が不合格だった。現在のWASMは変更前の確認用07の記録と一致した。歌唱の旧基準と、変更前に同じ現行WASMで採取したオフライン基準では、PCM・観測・発話計画のハッシュが一致する。既存の歌唱比較にオフライン基準を明示する引数を加え、現行WASMを持つ基準で改めて採取して58判定と固定上流17試験を通過した。初回の不合格も保存した。[旧基準での回帰](../runs/worklet-live-song-render-phases-20261122-speech-regression/summary.json)・[現行WASMの保存基準](../runs/worklet-song-voice-20261122-paired-reference/manifest.json)・[現行基準での回帰](../runs/worklet-live-song-render-phases-20261122-speech-current-reference/summary.json)

確認用07の計時は研究ワークスペースと `/private/tmp` から実行し、各39判定と固定上流11試験が通過した。両実行で保存ケース、PCMなど21出力がバイト一致した。マーカー時刻の差を再計算し、WASM・コピー・観測の時間と増分の割合を要約と照合した。macOS 15.6.1 arm64、Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。歌唱の回帰も含めた4実行の1,115入力・168出力をサイズとSHA-256で照合し、採取物79,386,865バイトをRTL9210B-CGへ保存した。[確認用07の実行記録](../runs/worklet-live-tsp-firefox-render-phases-20261122-repeat/manifest.json)・[歌唱の実行記録](../runs/worklet-live-song-render-phases-20261122-speech-current-reference/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_phases.py worklet-live-tsp-firefox-render-phases-new
../../.venv/bin/python tools/measure_worklet_live_song_render_phases.py worklet-live-song-render-phases-speech-new \
  --offline-reference-run worklet-song-voice-20261122-paired-reference
```

## 確認用07のWASM内の調音制御と気道伝搬

前回の先頭量子で長かった `vocal_render` を、同じ発話でWASM内まで計時した。通常WASM、計測用WASMを印なしで使う対照、同じ計測用WASMで印を有効にする条件を、順序を反転して採取した。出力フレーム0、128、4,096、4,224から始まる量子に絞り、各32出力フレームのループと調音・断面更新、内部0・32サンプル目の気道ステップに境界を置く。先頭量子で制御更新を含む区間が特に長くなると予測し、調音・断面更新の増分だけでループ全体の増分の半分以上を説明できるかを判定した。[事前登録](../cases/worklet-live-tsp-firefox-wasm-core-phases.json)・[前回のWASM呼び出しの計測](../runs/worklet-live-tsp-firefox-render-phases-20261122-repeat/summary.json)

固定上流の `HumanVoice::render` は、内部サンプルごとに制御カウンタを見て、境界に来たときだけ `control` を呼ぶ。スコアの目標と調音器を更新して声道断面を計算し、次の制御境界までの気道の補間を準備する。各内部サンプルでは声門前後の圧差から面積を求め、声門ポートに反映して `AirwayNetwork::step` を進め、放射を間引き器へ渡す。研究版も更新間隔を64出力フレームとしており、48 kHz出力・96 kHz内部では128内部サンプル、約1.333 msごと。固定上流のエンジン試験はホストのブロック長を変えてもPCMがビット一致することを確認している。[上流の内部ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[上流のホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

計測用WASMは `render-phase-probe` を有効にして別にビルドした。通常WASMのインポートには計時関数がない。診断時は `vocal_render_traced` が共通の描画を呼び、内部サンプルの番号と処理境界をFirefoxのプロファイラーに送る。調音・断面の印はスコア適用から断面の補間準備までを囲む。声門ポートの設定と気道の更新を測る印は内部0・32サンプル目だけに出す。外側のループには声門の計算、間引きとPCMの書き出しも含まれ、制御を引いた残りはこれらを含む。各印が先行して取得したホストの `vocal_render` 区間の内側にあり、番号の並びが32出力・64内部フレームの分割に合うことを確認した。[診断用の境界](../crates/vocal-core/src/render_phase_probe.rs)・[調音・断面更新](../crates/vocal-core/src/voice.rs#L587)・[声門ポートと気道の更新](../crates/vocal-core/src/voice.rs#L225)・[WASMのループ](../crates/vocal-wasm/src/lib.rs#L965)

研究版の気道へ渡す声門面積は cm²、声門前後の圧力差は dyn/cm²。気道の更新から得た放射流量の時間微分（cm³/s²）を内部サンプルごとに間引き器へ渡し、内部2サンプルから出力1フレームを確定する。境界の整合を確認するため、各32フレーム区間の末尾で内部カウンタが64、先頭と64フレーム目の区間だけで調音・断面更新が1回ずつ記録されることを検査した。声門ポートと気道の計時区間は、同じ内部サンプルの声門面積が確定した後に始まる。[呼気・声門・気道の順序](../crates/vocal-core/src/voice.rs#L212)・[放射からPCMへの変換](../crates/vocal-core/src/output.rs#L76)

先頭量子から定常2量子の中央値を引いた。計時を有効にした4試行すべてで調音・断面更新は増分の24.6〜26.2%となり、半分以上を占めるという予測は成立しなかった。4つの描画区間すべてで先頭量子のループが長かった。気道の計時は1量子当たり8ステップで、各試行のステップ中央値は先頭が11.1〜16.4 µs、定常の各量子が5.7〜7.9 µsだった。全256内部サンプルのうち8ステップを採っているため、気道全体の増分の推定には使わない。[初回の区間表と判定](../runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-a/summary.json)・[再実行の区間表と判定](../runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-repeat/summary.json)

| 試行 | ループの増分 | 調音・断面の増分 | 調音・断面を引いた増分 | ループの増分に占める調音・断面 |
| --- | ---: | ---: | ---: | ---: |
| 初回1 | 1.799 ms | 0.459 ms | 1.340 ms | 25.5% |
| 初回2 | 2.037 ms | 0.501 ms | 1.536 ms | 24.6% |
| 再実行1 | 2.344 ms | 0.615 ms | 1.729 ms | 26.2% |
| 再実行2 | 1.983 ms | 0.497 ms | 1.486 ms | 25.1% |

JavaScriptの先頭量子の中央値は通常WASMから計測用WASMの印なしに切り替えると初回で −0.040 ms、再実行で −0.029 ms。計測用WASMで内部印を有効にすると +0.052 ms、+0.497 ms。いずれも事前に設定した絶対差0.6 msの範囲に収まったが、再実行では印による変動が大きく、処理時間の小さな差を比較するときはこの幅を考慮する。GCやWASMの最適化への切替時点はこの実験では対応付けていない。[条件別の先頭量子](../runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-repeat/summary.json)

全12試行で全107,527フレームのPCM、保存ケース、発話計画と観測が従来の通常再生にビット一致した。通常WASMのSHA-256は前回と異なった。セクションを比較すると差はデータの9バイトとカスタムセクションのLLVMシンボル名にある14バイトで、コードセクションは一致した。通常再生の回帰ではChromiumとFirefoxともオフライン版とCLIにビット一致し、固定上流との差は出力フレーム53,463からで最大 `1.16×10⁻¹⁰` だった。[通常WASMと計測用WASMの記録](../runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-repeat/manifest.json)・[両ブラウザの回帰](../runs/worklet-live-tsp-source-defaults-20261122-wasm-core-regression/summary.json)

研究ワークスペースと `/private/tmp` から実行して各89判定と固定上流11試験が通過した。通常再生の回帰は21判定、研究版のWASM 27試験も通過した。圧縮したGeckoプロファイルの印から表の時間を独立に再計算し、3実行の844入力・130出力をサイズとSHA-256で照合した。採取物89,349,005バイトをRTL9210B-CGに保存した。macOS 15.6.1 arm64、Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。[初回の実行記録](../runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-a/manifest.json)・[再実行の記録](../runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-repeat/manifest.json)・[回帰の記録](../runs/worklet-live-tsp-source-defaults-20261122-wasm-core-regression/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_wasm_core_phases.py worklet-live-tsp-firefox-wasm-core-phases-new
../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-wasm-core-regression-new
```

## 確認用07の先頭量子と事前描画

固定上流のWorkletはコンストラクターで `WebAssembly.Instance` と `engine_new(sampleRate)` を実行し、準備完了を通知する。通常の `process` はContextが要求した出力フレーム数を `engine_render` へ渡し、WASMの共有メモリからFloat32のPCMをコピーする。上流のABIで要求数を0にすると、長さ0の出力スライスを受けた `Engine::render` はループに入らず、出力位置 `pos` を進めない。1以上では `pos % SUB_BLOCK` から内部ブロックの残りを求め、発声器へ分割した区間を渡し、進んだフレーム数を `pos` に足す。上流のホスト分割試験は128フレームずつの基準と1、77、4,096、48,000フレームずつの波形がビット一致することを確かめている。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L49)・[上流のWASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[上流のブロック分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流のホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `vocal_render` は0フレームを入口で拒否して0を返す。正の要求では音源と調音スコア、気道、間引き器、`rendered` が進む。歌唱の比較で使った `FixedVoiceEngine` の使い捨てハンドルを英語発話にも使い、同じWASMインスタンスで準備なし、0フレームの1,000回呼び出し、その呼び出しに続けて32フレームずつ256フレームを描画する条件を比べる。準備した256フレームは48 kHzで5.333 ms、96 kHzでは512内部サンプルに当たり、発話内の先頭50 msの無音区間に収まる。本番の時計、観測領域と出力は新しいハンドルで始める。正のフレーム数で使う計算が事前に実行されると、本番の先頭量子でWASMにかかる時間が短くなると予測した。[研究版のWASM入口](../crates/vocal-wasm/src/lib.rs#L965)・[歌唱での比較条件](../cases/worklet-live-song-render-warmup.json)・[発話の事前登録](../cases/worklet-live-tsp-firefox-render-preparation.json)

実時間の英語発話では保存ケースを読み込み、全条件で同じ調音スコアと初期状態を本番用ハンドルへ渡す。同期の事前描画を選んだときは、声門系列と声道断面の観測領域を確保する前に、使い捨てハンドルを作成して破棄する。Workletの構築時間と事前描画の区間は同じFirefoxのプロファイルで照合する。構築後は連続8量子を確認し、確定したContextフレームからさらに2,048フレーム後に採取する。条件間では発話時計とこの相対的な開始条件を照合し、Context自体の進み方は構築から採取までの壁時計と待機中の量子に記録する。[英語発話からWorkletへの設定](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L233)・[ハンドルと観測領域の作成順](../crates/vocal-wasm/host/fixed-voice.ts#L307)・[Workletの採取時計](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L31)

初回と再実行は各3組、合計18試行を順番を入れ替えながら採った。256フレームを事前描画した6試行は、先頭の `ProcessBlock` が1.898〜2.073 msで、全841採取量子が2.667 ms以下だった。準備なしと0フレームのみは、先頭量子がいずれも予算を超えた。先頭量子のWASM描画の中央値は、事前描画で準備なしの41.8〜42.4%、0フレームのみの43.5〜44.3%となり、事前登録した3つの予測を両実行で満たした。PCM・発話の計画・観測・保存ケースは全18試行で従来の再生に一致した。固定上流との差はPCMの出力フレーム53,463から現れ、最大 `1.16×10⁻¹⁰` だった。[初回の集計](../runs/worklet-live-tsp-firefox-render-preparation-20261122-a/summary.json)・[再実行の集計](../runs/worklet-live-tsp-firefox-render-preparation-20261122-repeat/summary.json)

| 条件 | 先頭量子の中央値 | Worklet構築の中央値 | 構築開始から先頭量子完了までの中央値 |
| --- | ---: | ---: | ---: |
| 準備なし | 3.722・3.884 ms | 1.171・1.192 ms | 67.734・67.917 ms |
| 0フレームを1,000回 | 3.638・3.640 ms | 1.860・1.888 ms | 67.658・67.670 ms |
| 0フレーム呼び出しと256フレームの事前描画 | 1.927・1.935 ms | 7.551・7.470 ms | 71.273・71.284 ms |

表の値は初回、再実行の順。256フレームのWASM描画そのものは5.60〜5.73 ms、使い捨て状態の作成・解放を含む準備全体は6.38〜6.53 msだった。事前描画で構築時間の中央値は準備なしから6.28〜6.38 ms増え、先頭採取量子の完了も3.37〜3.54 ms遅れた。構築後の待機量子の最大値は全条件で0.165 ms以下、冒頭32採取量子を除くp99は1.669〜1.946 msだった。負担が構築区間へ移ったため、この同期の準備は診断用の比較条件として保持する。構築を含む機器側のコールバックと実際の音声出力、WASM最適化の切替時点はこの実験の観測範囲外。次は256フレームの事前描画を待機量子に分け、構築と待機の両方で負担を測る。[準備と待機の各試行](../runs/worklet-live-tsp-firefox-render-preparation-20261122-repeat/summary.json)・[歌唱の分割準備](worklet-live-song-split-preparation.md)

研究ワークスペースと `/private/tmp` から実行し、各151判定と固定上流11試験が通過した。準備を指定しない通常再生の回帰はChromiumとFirefoxで21判定、WASMの27試験が通過した。歌唱の保存済みプロファイルでも準備マーカーの照合を確認した。生プロファイルの印と量子表から先頭量子、構築、WASMの時間を別集計し、3実行の853入力・174出力をサイズとSHA-256で照合した。採取物118,275,574バイトをRTL9210B-CGへ保存した。macOS 15.6.1 arm64、Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。[初回の実行記録](../runs/worklet-live-tsp-firefox-render-preparation-20261122-a/manifest.json)・[再実行の記録](../runs/worklet-live-tsp-firefox-render-preparation-20261122-repeat/manifest.json)・[通常再生の回帰](../runs/worklet-live-tsp-source-defaults-20261122-render-preparation-regression/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=400000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py worklet-live-tsp-firefox-render-preparation-new
../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-source-defaults-preparation-regression-new
```

## 確認用07の待機量子に事前描画を分ける

固定上流の `AudioEngine.build` はWorkletを登録し、出力のチャンネル構成とWASMモジュールをノードへ渡す。Workletは先頭チャンネルの実フレーム数を `engine_render` に渡し、返されたアドレスのFloat32 PCMを各出力へ複製する。Rustでは `pos % SUB_BLOCK` から制御ブロック内の位置を求め、実際に描画した長さだけ `pos` を進める。固定上流のホスト分割テストは同じ発声イベントを絶対フレームで適用し、要求長を1、77、4,096、48,000にしても128フレーム分割と同じPCMを得る。先行無音を挟む今回の研究版では、WorkletのContext時計と、発声器ごとの累積描画位置を別に扱う。[上流のノード作成](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流の描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[Rustの分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト分割テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版は連続8量子を確認したContextフレームを `A` とし、`A + 2,048` で採取を始める。48 kHz・128フレームの量子予算は `1,000 × 128 / 48,000 = 2.667` ms。使い捨て発声器だけを `A + 256k`（`k = 0…7`）で32フレームずつ進める。第1片でABIへの0フレーム呼び出しを1,000回行い、第8片の累計256フレームで使い捨てハンドルを解放する。第8片を始めるのは `A + 1,792`、採取の2量子前。本番用ハンドルの発声位置は0のままにする。前回の同期条件に比べ、構築の中央値が4 ms以上短くなり、待機中と先頭採取量子が3試行中2回以上で予算内に収まると予測する。[発話の採取時計](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L31)・[同期条件の実測](../runs/worklet-live-tsp-firefox-render-preparation-20261122-repeat/summary.json)・[歌唱の分割準備](worklet-live-song-split-preparation.md)・[事前登録](../cases/worklet-live-tsp-firefox-split-preparation.json)

構築時に同じWASMインスタンスの中へ別々の発声ハンドルを作る。声門面積・流量と声道断面の領域は本番用ハンドルに確保する。待機中は使い捨てハンドルにだけ `vocal_render` を呼び、Contextの出力チャンネルへゼロを返す。使い捨てハンドルの解放後にWASMの線形メモリが変わっていれば、本番用のPCMと観測のビューを同じアドレスで作り直す。準備の印はContextフレームと累積描画数を含み、それぞれの `CallProcess` 内に開始・終了の印が順にあることを検査する。外側の `ProcessBlock` は処理予算の判定に使う。[WASMホストの準備完了処理](../crates/vocal-wasm/host/fixed-voice.ts#L431)・[Workletの待機処理](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L205)・[準備の計時](../tools/measure_worklet_live_tsp_firefox_render_preparation.py#L31)

条件順を変えて2実行、各9試行を採った。分割した6試行で、待機中の最長量子は1.219〜1.334 ms、先頭の採取量子は1.812〜2.056 msだった。待機中も全841採取量子も2.667 ms以内に収まった。同期条件に対して構築時間の中央値は5.67〜5.73 ms短く、構築開始から先頭採取量子完了までも約5.33 ms短かった。事前登録した3つの予測を両実行で満たした。全18試行で採取開始は `A + 2,048`、最初の非ゼロは発話内フレーム2,439だった。通常再生と全PCM・計画・声門・声道の観測値が一致した。固定上流との最初のPCM差はフレーム53,463、最大差は `1.16×10⁻¹⁰` だった。[初回の集計](../runs/worklet-live-tsp-firefox-split-preparation-20261122-a/summary.json)・[再実行の集計](../runs/worklet-live-tsp-firefox-split-preparation-20261122-repeat/summary.json)

| 条件 | 構築時間の中央値 | 最も重い待機量子の中央値 | 先頭採取量子の中央値 | 構築開始から先頭採取量子完了までの中央値 |
| --- | ---: | ---: | ---: | ---: |
| 準備なし | 1.160・1.189 ms | 0.155・0.145 ms | 3.800・3.951 ms | 67.808・67.970 ms |
| 構築中に描画 | 7.524・7.504 ms | 0.140・0.123 ms | 1.843・1.927 ms | 71.199・71.264 ms |
| 待機中に分割 | 1.798・1.833 ms | 1.295・1.235 ms | 1.883・1.924 ms | 65.866・65.929 ms |

表の値は初回、再実行の順。第1片が6試行すべてで最も重い待機量子になった。32フレーム片を先頭から2つずつ比べると、制御更新がある側の外側区間の方が全24対で長かった。先頭には0フレーム呼び出しも含まれる。今回は片単位の計時なので、この差の全量を制御更新へ帰属できるかは未検証。採取中のWASM線形メモリ拡張は全分割試行で0件。別の動作確認では `node --experimental-transform-types` で実際のWASMと母音 /i/ の設定を使い、最初の32フレームの準備後に `memory.grow(1)` を実行した。8片が完了すると観測ビューが復帰し、本番の最初の2,048フレームのPCM、声門、声道は拡張していない対照と一致した。[各片の時間](../runs/worklet-live-tsp-firefox-split-preparation-20261122-repeat/summary.json)・[64フレームごとの制御更新](../crates/vocal-wasm/src/lib.rs#L27)・[動作確認に使用した母音設定](../cases/vowel-voice-i.json)

今回の予算判定は英語発話Workletの `ProcessBlock` が対象。構築や待機と同じ機器要求に含まれる別ノードや出力処理の時間、機器側の欠落は測っていない。次は同一Contextに先行音を加え、構築中の描画と待機中の分割で、機器要求の時計と先行音PCMの連続性を照合する。[歌唱の機器側での採取](worklet-live-song-cubeb-output.md)

研究ワークスペースと `/private/tmp` からの実行は各157判定を通過した。通常再生の回帰はChromiumとFirefoxで21判定とWASMの27試験、固定上流は11試験を通過した。元のプロファイルと量子表を使って、分割6試行の48片すべての時刻と累計フレームを再計算した。3実行の861入力・174出力をサイズとSHA-256で照合し、採取物118,322,767バイトをRTL9210B-CGへ保存した。macOS 15.6.1 arm64、Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。[初回の実行記録](../runs/worklet-live-tsp-firefox-split-preparation-20261122-a/manifest.json)・[再実行の記録](../runs/worklet-live-tsp-firefox-split-preparation-20261122-repeat/manifest.json)・[通常再生の回帰](../runs/worklet-live-tsp-source-defaults-20261122-split-preparation-regression/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=400000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py worklet-live-tsp-firefox-split-preparation-new --split
../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-source-defaults-split-preparation-regression-new
```

## 確認用07を共有Contextで機器出力バッファまで照合する

固定上流の `AudioEngine.build` は `AudioContext` のサンプルレートをHzで指定し、Workletの出力2チャンネルをContextへ接続する。 `ChimeraProcessor.process` は出力チャンネルのフレーム数を `engine_render` に渡し、返された共有メモリのFloat32 PCMを両チャンネルへコピーする。Rustの `Engine::render` は累積出力位置と内部ブロック境界に合わせて発声を進め、ホスト分割試験は同じ絶対位置の操作でPCMがビット一致することを比較する。上流の負荷表示が計る範囲はWorkletの描画と転送。機器側の要求は複数ノードの処理を含むため別に計る。[上流のノード構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流の描画と負荷表示](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASMの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[固定上流のホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

既存の歌唱採取と同じ試験用Firefoxで、通常の確認用07のボタン操作を使う。先行音はフレーム添字 `i` に対して `((421i + 173) mod 65521 - 32760) / 524288` とし、左右に逆相で加える。前後の出力窓を先行音で対応付け、48 kHz、256フレームの1要求に `1,000 × 256 / 48,000 = 5.333` msを割り当てる。予定サンプル時刻の差から要求のフレーム数を引くと、時計上の飛びをフレーム単位で数えられる。PCMの欠落は左右差から復元する先行音の連番で別に数える。歌唱で採れた条件を根拠に、同期の構築時には予算超過と時計の飛びが起き、分割時には窓内のサンプル時刻とPCMが連続すると予測する。[事前登録](../cases/worklet-live-tsp-firefox-device-preparation.json)・[歌唱での機器要求とPCMの採取](worklet-live-song-cubeb-output.md)・[機器要求の照合](../tools/inspect_firefox_cubeb_output.py)

最初は先行音設定を書き出すPythonの `json` インポートが欠け、ブラウザを起動する前に終了した。修正後の第1版の9試行ではPCMとWorkletの照合を通った。出力先はシステムの既定の44.1 kHzヘッドフォンで、プロファイラーとcubebの生データには48 kHzのバッファで278〜279フレームの要求が記録された。グラフの前進は256または384フレームだった。第1版は全9試行で固定256フレームの窓の判定に不合格。出力先の設定を維持したまま、第2版の判定を別の採取で行うことにした。[初回の中断](../runs/worklet-live-tsp-firefox-device-preparation-20261122-a/failure.json)・[固定フレーム条件の判定](../runs/worklet-live-tsp-firefox-device-preparation-20261122-b/summary.json)・[第2版の事前登録](../cases/worklet-live-tsp-firefox-device-preparation-v2.json)

第2版ではグラフ側で先行音の添字を決め、cubebのPCMで復元した最初の添字が同じになる要求を探す。すでに生成済みのPCMの残量を `q`、グラフ前進を `g`、要求長を `r` とすると、次の要求までに残る量は `q + g - r`。各境界でこの値が0〜127フレームに入り、要求長の列と最後のPCM境界まで一致する場合に対応を認める。Core Audioのホスト時計はMachの時間単位からmsに換算し、PCMバッファの48 kHzで求めたサンプル時計の間隔と照合する。予算は278フレームで5.792 ms、279フレームで5.813 ms。グラフが384フレーム進む要求では、同じ要求へ複数の準備片が入る場合も残す。[要求の対応付けと時計](../tools/inspect_firefox_cubeb_output.py#L31)・[cubebのバッファ採取](../tools/chimera-cubeb-output-snapshot.patch)

第2版の18試行では、構築の前後各16要求を生データと一意に照合した。準備なしの6試行では、最初の発話量子を含む要求の直後に256フレームの時計の飛びが出た。同期描画の6試行では構築を含む要求が各予算を超えて、その直後に256フレーム飛んだ。うち1試行は先頭の発話量子を含む要求の直後にも飛んだ。分割した6試行では構築から第8片までの要求が各予算内に収まった。採取窓全体で時計が連続したのは5試行。全18試行でcubebが返した先行音PCMに欠落、反復、無音はなく、発話WorkletのPCMと声門・声道の観測値は通常再生に一致した。固定上流とのPCMの最大差は `1.16×10⁻¹⁰`。[第2版の集計](../runs/worklet-live-tsp-firefox-device-preparation-20261122-v2/summary.json)・[再実行の集計](../runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/summary.json)

| 条件（各6試行） | 構築を含む要求の時間 | 構築直後の時計の飛び | 先頭の採取を含む要求の直後の飛び |
| --- | ---: | ---: | ---: |
| 準備なし | 1.371〜1.701 ms | 0件 | 6件 |
| 構築中に同期描画 | 7.866〜9.874 ms | 6件 | 1件 |
| 待機中に分割描画 | 1.950〜2.762 ms | 0件 | 1件 |

分割の再実行で時計が飛んだ要求は、第8片を含む要求の次だった。この要求で48 kHzのグラフは384フレームを処理した。先頭の発話3量子はそれぞれ2.294、1.892、1.651 msで、合計だけで5.837 msに達した。279フレームの要求予算5.813 msに対し、cubebのコールバックは5.979 ms。その次の予定時刻が256フレーム飛んだ。分割時の残る課題は、先頭の発話量子が同じ機器要求に集まるときの合計負荷。分割で2つの準備片が同じ384フレームのグラフ反復に入った場合も記録した。物理出力の連続性はプロセスタップや機器側で別途検証する。[再実行の要求別の記録](../runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/summary.json)・[該当する量子の表](../runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/artifacts/2-split/aligned-quanta.csv)

研究ワークスペースと `/private/tmp` からの第2版は各196判定を通過した。通常再生の回帰はChromiumとFirefoxで21判定とWASMの27試験、固定上流で11試験が通過した。既存の歌唱の固定要求でも保存済みの判定を再現した。独立計算で18試行の594要求のバッファ残量と時計差を再計算し、先行音のPCMをビット照合した。第1版の採取を含む4実行の1,207入力・413出力をサイズとSHA-256で照合し、採取物207,507,660バイトをRTL9210B-CGへ保存した。macOS 15.6.1 arm64、試験用Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。[試験用Firefoxと実行記録](../runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/manifest.json)・[通常再生の回帰](../runs/worklet-live-tsp-source-defaults-20261122-device-preparation-regression/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=400000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py worklet-live-tsp-firefox-device-preparation-new --device-variable
CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox \
  ../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-source-defaults-device-regression-new
```

## 確認用07の採取開始を1量子ずらす

固定上流の `ChimeraProcessor.handle` はメインスレッドのジェスチャーをWASMに渡し、`Engine::schedule` が声の時計とリード秒数の和を各ジェスチャーの開始・終了時刻に足す。描画のたびに `Engine::render` は出力フレーム位置を進める。固定上流の試験は同じ出力位置で操作を適用し、ホストの要求長を変えたときのPCMを比較する。研究版の今回の対照では、発話内のジェスチャーと時刻を固定し、Workletの採取が始まるContextフレームを128だけ遅らせる。48 kHzでは2.667 ms。8片の事前描画は採取時計が確定するフレーム `A` から従来どおり始まり、最後は `A + 1,792`。採取は `A + 2,048` または `A + 2,176` で始まる。[上流の予約メッセージ](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L136)・[合成器の時計とリード](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L175)・[固定上流のホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[研究版の採取時計](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)

前回の分割6試行のうち4試行では先頭の発話3量子が1要求に入った。保存したグラフ反復で開始位置だけを1量子後ろに置くと、同じ要求に残るのは2量子だった。残る2試行は2量子から1量子になる。実行ごとにグラフ反復の割り当てが変わり得るため、この計算を仮説として独立した試行を行う。先頭3量子の少なくとも1つを含む機器要求を調べ、1要求への集中と、コールバック時間からフレーム数に応じた予算を引いた値を比較する。[前回の機器要求](../runs/worklet-live-tsp-firefox-device-preparation-20261122-v2/summary.json)・[前回の再実行](../runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/summary.json)・[事前登録](../cases/worklet-live-tsp-firefox-device-onset.json)

先頭3量子のContextフレームが先行音で復元した添字にあり、発話ノードの処理区間全体が該当するグラフ反復に含まれることを確かめた。要求ごとに発話Worklet処理の合計と、別ノードも含むcubebコールバック全体の時間を記録する。時計を照合する際は指定した追加量子を予定時刻へ足し、841量子と発話内の最初の非ゼロ位置を通常のケースに照合した。1量子の遅延は分割描画の実験用オプション。[Workletへの条件指定](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L232)・[先頭量子と機器要求の対応](../tools/measure_worklet_tsp_device_preparation.py#L121)

初回と再実行で各4組を採った。従来の開始では8試行中7試行で先頭3量子が1要求に集中した。1量子遅らせると8試行とも2要求に分かれた。内訳は前の要求に2量子・後ろの要求に1量子が5試行、逆の組み合わせが3試行。負担が最も大きい要求の予算余裕の中央値は、初回で0.647 msから2.113 ms、再実行で0.363 msから2.013 msへ増え、事前登録した2つの予測を両実行で満たした。全16試行で先行音は独立計算に、発話のPCM・ジェスチャー・声門と声道の観測値は通常再生に一致した。発話内の最初の非ゼロは2,439フレーム、固定上流とのPCMの最大差は `1.16×10⁻¹⁰` だった。[初回の集計](../runs/worklet-live-tsp-firefox-device-onset-20261122-a/summary.json)・[再実行の集計](../runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/summary.json)

| 分割描画後の採取開始 | 先頭3量子が1要求に入った試行 | 予算余裕の中央値（初回・再実行） | 先頭3量子を含む要求の予算超過 | 同じ要求の直後に予定時計が飛んだ試行 |
| --- | ---: | ---: | ---: | ---: |
| `A + 2,048` | 7/8 | 0.647・0.363 ms | 1件 | 2/8 |
| `A + 2,176` | 0/8 | 2.113・2.013 ms | 0件 | 0/8 |

時計の飛びはどちらも256フレームで、従来の開始の再実行3組目・4組目に現れた。両方とも先頭3量子を含む384フレームのグラフ反復だった。279フレームの要求予算5.813 msに対し、コールバック時間は5.877 msと5.492 ms。後者は予算内だったが、次の要求のホスト時計の予定間隔は11.610 ms、実際の呼び出し間隔は11.618 msだった。返却までの所要時間だけで時計の飛びを判定できない。全試行で観測窓のcubebのPCMは連続した。時計の飛びの発生率とヘッドフォンでの実出力は引き続き照合する。[再実行の要求別結果](../runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/summary.json)・[4組目の量子表](../runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/artifacts/4-split/aligned-quanta.csv)

研究ワークスペースと `/private/tmp` から実行して各185判定、通常再生の回帰はChromiumとFirefoxで21判定が通過した。固定上流11試験と研究版WASM 27試験も通過した。機器側の528要求を元のPCM・時計から検算し、開始予定、8片の準備位置、先頭3量子と要求予算を量子表から再照合した。3実行の905入力・254出力をサイズとSHA-256で照合し、採取物132,256,568バイトをRTL9210B-CGへ保存した。macOS 15.6.1 arm64、試験用Firefox 157.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。[初回の実行記録](../runs/worklet-live-tsp-firefox-device-onset-20261122-a/manifest.json)・[再実行の記録](../runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/manifest.json)・[通常再生の回帰](../runs/worklet-live-tsp-source-defaults-20261122-device-onset-regression/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=400000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py worklet-live-tsp-firefox-device-onset-new --device-onset
CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox \
  ../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-source-defaults-onset-regression-new
```

## 確認用07の出力要求をAudio ClientとAudio Serverへ対応付ける

固定上流の `AudioEngine.build` はContextへWorkletを接続し、`ChimeraProcessor.process` は出力フレーム数を `engine_render` に渡す。Rustの `Engine::render` は制御境界で区切って累計出力位置を進め、ホスト分割試験は発声操作を同じ出力位置に適用したときのPCMを比較する。今回調べる時刻はこの描画の後段にある。cubebの採取版はCore Audioの出力要求からサンプル時刻とホスト時刻を受け取り、入った時刻とバッファを返す直前のMach時刻を記録する。[上流のContextとノード](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流の描画と負荷表示](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[固定上流のホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[cubebの採取箇所](../tools/chimera-cubeb-output-snapshot.patch)

着手時の既定出力は前回と同じ外部ヘッドフォンで、現在の表示は48 kHzだった。機器設定を保ち、実測の要求長ごとに `1,000 × フレーム数 / 48,000` msを処理予算にする。Audio Clientの表はFirefoxの親プロセスで実行されたI/O区間を、Audio Serverの表は音声サーバーのクライアント処理と出力ホスト時刻を記録する。同期描画で時計が飛ぶ場合、次のクライアントI/O開始も通常より遅れると予測した。対応する音声サーバーの区間が同じ間隔で飛ぶかは別に調べる。[前回の採取時刻](../runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/summary.json)・[歌唱でのAudio Clientの検証](worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)・[事前登録](../cases/worklet-live-tsp-firefox-device-io.json)

トレースはブラウザを起動する前に開始し、先行音の準備や発話の開始に待ち時間を加えない。Machの単調時計で実時間の読取りを挟み、トレースの開始時刻との対応を求める。Firefox親プロセスのI/O候補をスレッドごとに調べ、cubebの入口間隔と照合する。窓内の全入口・返却がI/O開始・終了に収まる共通の時刻差を求める。サーバー側は別に、cubebの予定ホスト時刻とサーバー表の出力ホスト時刻をMachの単位で直接照合する。スレッドが一意なときに、同じ出力スレッドの書き込み記録を調べる。[同時採取と時計の読取り](../tools/measure_worklet_tsp_device_io.py#L24)・[クライアント区間の照合](../tools/measure_worklet_tsp_device_io.py#L49)

初回と再実行はともに2組で、計8試行すべての機器要求は256フレームだった。構築前後の33要求と次の要求を、FirefoxのI/O区間および音声サーバーの要求に一意に対応付けた。同期描画は4試行とも構築直後に時計が飛び、うち2試行は採取開始時にも飛んだ。分割描画は4試行とも構築直後の飛びがなく、1試行では採取開始時に飛んだ。計7件の飛びは256フレームが5件、512フレームが2件。7件すべてでFirefoxのI/O開始にも同じ間隔が現れ、中間のFirefoxのI/O区間は観測されなかった。同じ期間の音声サーバーの出力スレッドには、256フレームずつ連続するサンプル位置への書き込みがあった。[初回の要求別結果](../runs/worklet-live-tsp-firefox-device-io-20261122-a/summary.json)・[再実行の要求別結果](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)

再実行の2組目の同期描画では、採取開始を含む要求でcubebが5.269 ms、FirefoxのI/O区間が5.275 msで、256フレームの予算5.333 msに収まった。次のFirefoxのI/Oは10.667 ms後に始まり、次のcubeb入口も10.678 ms後だった。Firefoxの2つのI/O区間の間は5.392 msで、次のI/Oには `Overload` の印が付いていた。音声サーバーには飛んだ256フレームに対応する書き込みがあった。前回の44.1 kHzでの事象に加え、今回は48 kHzでも、コールバックが予算内であっても次のI/O開始が1周期分遅れる事例を採れた。[該当試行のI/O時刻](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)・[該当試行のWorklet量子表](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/artifacts/2-draw/aligned-quanta.csv)

全試行でcubebが返した先行音PCMは連続し、発話PCM・ジェスチャー・発声状態は通常再生に一致した。固定上流との最大PCM差は `1.16×10⁻¹⁰`。今回採取した音声サーバーの記録は書き込み時刻とサンプル位置を含む。書き込まれたバッファの内容と遅れの原因となった締切時刻は未確定である。[サーバーの書き込み記録](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/artifacts/2-draw/audio-hal-io-cycle-hardware.xml)・[歌唱でのプロセスタップとの照合](worklet-live-song-paired-output.md)

研究ワークスペースと `/private/tmp` からの実行は各97判定、通常再生の回帰はChromiumとFirefoxで21判定が通過した。固定上流11試験と研究版WASM 27試験も通過した。生のcubeb時刻を読み直し、全8試行のI/O区間との包含関係と7件の飛びに対応するサーバーの書き込み位置を独立に検算した。3実行の915入力・1,350出力をサイズとSHA-256で照合し、採取物351,992,385バイトをRTL9210B-CGへ保存した。macOS 15.6.1 arm64、試験用Firefox 157.0、Instruments 26.0、Node.js 24.19.0、Bun 1.4.4、Rust 1.94.1、Python 3.14.4。[初回の実行記録](../runs/worklet-live-tsp-firefox-device-io-20261122-a/manifest.json)・[再実行の記録](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/manifest.json)・[通常再生の回帰](../runs/worklet-live-tsp-source-defaults-20261122-device-io-regression/manifest.json)

```bash
export CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=600000000
../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py worklet-live-tsp-firefox-device-io-new --device-io
CHIMERA_FIREFOX=/Volumes/RTL9210B-CG/voice-simulator/build/playwright/firefox-1555/firefox/Nightly.app/Contents/MacOS/firefox \
  ../../.venv/bin/python tools/measure_worklet_live_tsp_source_defaults.py worklet-live-tsp-source-defaults-io-regression-new
```

## 確認用07のI/O時刻とプロセスタップのPCMを照合する

固定上流の `AudioEngine.build()` はインタラクティブ遅延のContextを指定したサンプル率で開き、WASMモジュール付きのステレオWorkletを接続する。`ChimeraProcessor.process()` は片チャンネルの出力長をWASMに渡す。`engine_render()` が上限で長さを切り詰め、`Engine::render()` は絶対フレーム位置 `pos` の128フレーム境界でシーケンサーを更新してから音声を描き、描いたフレーム数だけ位置を進める。Workletは同じFloat32を左右に出し、経過ミリ秒を `1000 × フレーム数 / サンプル率` の予算で割って負荷を更新する。上流のホスト幅試験は1、77、4,096、48,000フレームを128フレーム基準へ照合する。今回の逆相の先行音は研究用の同じContextに置く独立した枝で、左右差の半分から発話が重なる区間でも観測できる。[上流のグラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

試験用Firefoxで、同期256フレーム描画と32フレームずつ8片の分割描画を比較する。構築前後16要求の滑らかな先行音を、cubebの返却直前とCore Audioが同じ親PIDから採るプロセスタップの両方へ合わせる。各端の1,024フレームで相関と分数位相を求め、タップ入力時刻とcubeb予定時刻の差をミリ秒から48 kHzのフレームへ換算する。二つの端でこの差が0.5フレーム以内でそろう場合、平均の差をサーバー側クライアント行のホスト時計に足し、タップの区間へ写す。同じ出力サンプル位置を持つハードウェア表のWriteから長さを取得する。別計算では、先行音全体にゼロを挿入する位置を二通りに置き、ゲインを合わせた波形残差を比べる。予測はcubeb側が連続し、タップのPCMには予定時計の飛びと同じ長さの挿入があり、直前の要求側に無音が合うというもの。[事前登録](../cases/worklet-live-tsp-firefox-device-tap.json)・[校正](../runs/safari-process-tap-smooth-marker-20261122-repeat/manifest.json)・[同時採取の照合](../tools/measure_worklet_tsp_device_tap.py)

初回の分割1試行は待機上限の0.65秒までにタップから準備通知が届かなかった。先行音が強くなる前の点が左端の照合窓に入り、右端だけが有効だった。初回は116判定中115通過で保存した。第2版では待機上限を0.95秒にし、準備後100 msの待機と波形照合の閾値を維持した。タップが構築前に準備できたかも明示的に判定する。[第1版の結果](../runs/worklet-live-tsp-firefox-device-tap-20261122-a/summary.json)・[準備通知の記録](../runs/worklet-live-tsp-firefox-device-tap-20261122-a/artifacts/1-split/trace-release.json)・[第2版のケース](../cases/worklet-live-tsp-firefox-device-tap.json)

### 実測

macOS 15.6.1 arm64の試験用Firefox 157.0とInstruments 26.0で、外部ヘッドフォンを既定の48 kHz・256フレームのまま使った。研究ワークスペースと `/private/tmp` から各4試行を実行した。タップ窓を確定できた同期描画4試行と分割描画3試行では、cubebの先行PCMが連続し、タップ入力のサンプル時計も連続した。同じ先行音を観測した時間の差は26.104〜26.245 msで、各試行内の両端の変化は1 µs以内だった。全8試行で、発話WAVの107,527サンプルと観測3,361点が通常の発話に一致し、固定上流とのPCM最大絶対差は `1.1641532182693481e-10` だった。[初回](../runs/worklet-live-tsp-firefox-device-tap-20261122-a/summary.json)・[再実行](../runs/worklet-live-tsp-firefox-device-tap-20261122-repeat/summary.json)

| 観測 | 同期描画 | 分割描画 |
| --- | ---: | ---: |
| I/Oとタップの窓を照合できた試行 | 4/4 | 3/4 |
| 構築直後のcubeb予定時計 | 4試行で256フレーム飛んだ | 4試行で連続 |
| グラフとcubebで対応した先行音 | 8,448フレーム | 8,448フレーム |
| タップで対応した先行音 | 8,704フレーム | 8,448フレーム |
| タップPCMで左右とも完全にゼロ | 161フレーム | 0フレーム |
| サーバーの中間Writeに対応するタップの完全ゼロ | 256フレーム中0 | 中間Writeの照合対象なし |

同期描画で無音が現れた位置は、飛びの直前の要求に対応する256フレームのうち `[47, 208)` だった。ゼロ挿入モデルの相対RMS残差は直前の要求の先頭で0.42〜0.47%、次の予定位置で23.66〜25.56%だった。別計算では、保存したcubebのPCMを三次補間し、挿入位置を1フレームずつ変えた。全4件で窓先頭から4,096フレームの位置が最も合い、同じ位置を得た。サーバーの中間Writeに対応するタップの256点は、直前の要求でcubebが返した先行音の256点と、相対RMS残差0.83〜0.91%で一致した。したがってこの条件では、次の予定要求が飛んだ時刻と、無音が現れた出力位置は1要求分ずれていた。トレースはサーバーの書き込み位置を示し、PCMはFirefoxのプロセスタップで観測した。全プロセスのミックス、機器端子の波形、境界の95フレームを変えた処理段は引き続き未観測。[再実行の対応表](../runs/worklet-live-tsp-firefox-device-tap-20261122-repeat/summary.json)・[歌唱で観測した同じ境界](worklet-live-song-paired-output.md#実測)

飛びの4件ではcubebの返却に7.631〜8.941 msを要し、いずれも5.333 msの予算を超えた。前回の予算内で飛んだ事例にこのPCMの比較を適用するには、先頭3量子が同じ機器要求に入る従来開始と、開始を1量子遅らせた発話を同じ採取に入れる。[前回の予算内の飛び](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)・[1量子ずらした条件](#確認用07の採取開始を1量子ずらす)

第2版の123判定、通常発話のChromium・Firefoxの21判定、固定上流11試験、研究版WASMの27試験が通過した。共用した採取処理を歌唱でも確認した。歌唱2試行はタップの先行音まで照合でき、同期事前描画で256フレームの挿入と161フレームの完全ゼロが再現した。歌唱の登録ケースは以前のオフライン基準とWASMのSHA-256が異なり、40判定中39通過だった。現行WASMでオフライン基準を通常画面から再取得すると15判定が通過し、同時採取の両試行とWASM、WAVの91,200サンプル、1,425観測点、歌唱計画が一致した。5実行の1,518入力と1,493出力をサイズとSHA-256で照合した。記録した出力の合計は530,490,453バイトで、実体はRTL9210B-CGにある。[通常発話の回帰](../runs/worklet-live-tsp-source-defaults-20261122-device-tap-regression/manifest.json)・[歌唱の同時採取](../runs/worklet-live-song-paired-output-smooth-20261122-device-tap-regression/manifest.json)・[現行WASMの歌唱基準](../runs/worklet-song-voice-20261122-device-tap-reference/manifest.json)

### 再現

`research/experiments/chimera-rebuild` から試験用Firefoxと校正済みの採取器を指定する。明示した容量は4試行の収録に使う見積もりで、採取物の実体は作業用外部ディスクへ保存する。

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build
export CHIMERA_FIREFOX="$build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=600000000 \
  ../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py \
  worklet-live-tsp-firefox-device-tap-local --device-tap "$build/chimera-process-tap/CHIMERA-PCM-Probe.app"
```

## 確認用07の発話開始を1量子ずらして出力を同時採取する

固定上流の `AudioEngine.build()` はサンプル率とインタラクティブ遅延を指定してContextを開き、ステレオ出力の `ChimeraProcessor` を接続する。`process()` は左チャンネルの長さをWASMの `engine_render()` へ渡し、戻ったFloat32を左右に複写する。Rustは内部位置 `pos` を描画済みフレーム数だけ進める。`pos % 128 == 0` で先にシーケンサーを更新し、次の境界まで描画する。上流の `output_does_not_depend_on_the_host_block_size()` はイベント位置をサンプル単位で固定し、128フレームずつ描画した波形と、1、77、4,096、48,000フレームずつの波形をビット照合する。[上流のグラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の `renderRealtimeEnglishVoice()` は、診断用の分割条件でだけ開始待機を128フレーム延ばせる。`RealtimeSpeechCapture.ready()` は連続する起動量子を確認したフレームを `A` とし、`A + 2048` または `A + 2176` まで発声器の描画を待つ。分割事前描画は同じ使い捨て発声器を `A + 256k` で32フレームずつ進める（`k = 0…7`）。発話内の `0, 128, 256` フレームはどちらの条件でも同じで、Context上の最初の要求に対する位置だけが変わる。256フレームずつグラフが進むなら、最初の発話量子が要求先頭のときは2量子と1量子、要求の後半に移れば1量子と2量子に分かれる。量子の所属はこの見込みに加えて、プロファイルの処理区間が該当するグラフ反復内に入ることでも照合する。[開始待機の引数](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L236)・[開始と採取の状態](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)・[分割描画](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L204)

4組の両条件で、48 kHz・256フレームの機器予算は `1,000 × 256 / 48,000` ms。先頭3量子を含む各要求の統計は `cubebの返却時刻 − 入口時刻 − 機器予算` の最大値を試行ごとに取り、その中央値を比べる。予定時刻の飛びは次の予定サンプル位置と当該要求の終端の差で求め、FirefoxのI/O、サーバーのWrite位置、プロセスタップのPCMへ対応付ける。タップのグラフ窓を構築前後20要求に広げ、発話開始を含む要求が両端の相関窓の外にあることを判定する。これにより発話開始の付近に飛びが出ても、端点の照合をその区間から離せる。48 kHzの既存記録に対し、正しい組、片方の欠測、構築中の飛び、前後16要求のときに相関窓と重なる発話開始を対照とした。[事前登録](../cases/worklet-live-tsp-firefox-device-tap-onset.json)・[出力の照合と集計](../tools/measure_worklet_tsp_device_tap.py)

### 実測

macOS 15.6.1 arm64の試験用Firefox 157.0とInstruments 26.0で、同じ外部ヘッドフォンを48 kHz・256フレームのまま使った。研究ワークスペースと `/private/tmp` から各4組を採取した。全8組で、最初の3量子の機器要求への配分は通常開始で2＋1、1量子遅らせると1＋2になった。16試行とも分割事前描画の8片が `A + 256k` に収まり、107,527サンプルのWAVは通常再生とバイト一致した。観測3,361点と発話計画は一致し、発話内の最初の非ゼロは2,439フレームだった。固定上流とのPCM最大絶対差は `1.1641532182693481e-10`。[初回](../runs/worklet-live-tsp-firefox-device-tap-onset-20261122-a/summary.json)・[再実行](../runs/worklet-live-tsp-firefox-device-tap-onset-20261122-repeat/summary.json)

| 先頭3量子を含む最も重い機器要求の予算余裕 | 通常開始の中央値 | 1量子遅延の中央値 | 余裕の増加 |
| --- | ---: | ---: | ---: |
| 初回 | 1.222 ms | 2.138 ms | 0.916 ms |
| 再実行 | 1.354 ms | 2.071 ms | 0.717 ms |

1量子遅延はContext上で2.667 msの開始待機を増やす。8組中7組で予算余裕が増えた。再実行の1組目では予算余裕が1.800 msから1.238 msへ減った。量子の配分はその組でも予測どおりだった。16試行の観測窓では予定サンプル時刻の飛びとタップの追加フレーム・完全ゼロはいずれも0件だった。cubebの返却とFirefoxのI/O区間、サーバーの予定ホスト時刻を672要求で検算した。タップの10,496フレーム窓では、グラフで採った先行PCMを三次補間してゲインと遅延を独立に最適化し、相対RMS残差0.148〜0.212%で連続した先行音に一致した。[初回の要求別の時間](../runs/worklet-live-tsp-firefox-device-tap-onset-20261122-a/summary.json)・[再実行の量子表の一例](../runs/worklet-live-tsp-firefox-device-tap-onset-20261122-repeat/artifacts/1-split-late/aligned-quanta.csv)

今回の分割描画では、予算内の飛びとその時点のタップPCMを同時採取できなかった。既存の48 kHzの同期描画を集計の対照に入れると、cubebが5.269 ms、クライアントI/Oが5.275 msで、予算内のまま256フレーム飛んだ既知の1件を選別した。この既存実行ではタップPCMが欠測である。次はこの同期描画を陽性対照にして、構築時の飛びと発話開始付近の飛びを同じタップ窓の中で追う。[既存の予算内の飛び](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)・[同期描画でのタップの実測](#確認用07のio時刻とプロセスタップのpcmを照合する)

初回と再実行は各255判定と固定上流11試験を通過した。2実行の672入力・2,794出力をサイズとSHA-256で確認し、採取物650,877,203バイトをRTL9210B-CGへ保存した。[初回のマニフェスト](../runs/worklet-live-tsp-firefox-device-tap-onset-20261122-a/manifest.json)・[再実行のマニフェスト](../runs/worklet-live-tsp-firefox-device-tap-onset-20261122-repeat/manifest.json)

### 再現

`research/experiments/chimera-rebuild` から、通常発話の基準に登録されたWASMと、48 kHzで校正済みのタップを使う。8試行の採取物は作業用外部ディスクに直接書き出す。

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build
export CHIMERA_FIREFOX="$build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1000000000 \
  ../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py \
  worklet-live-tsp-firefox-device-tap-onset-local --device-tap-onset "$build/chimera-process-tap/CHIMERA-PCM-Probe.app"
```

## 確認用07の同期描画で発話開始付近の飛びを採る

固定上流の `AudioEngine.build()` は指定レートのContextを起動し、WASMモジュールを持つ2チャンネルのWorkletを接続する。`ChimeraProcessor.process()` はチャンネルのフレーム数で `engine_render()` を呼ぶ。WASMが返したFloat32を左右へ複写し、処理ミリ秒を `1,000 × フレーム数 / サンプル率` で割って負荷を更新する。Rustの `Engine::render()` は発声内の位置 `pos` を128フレーム周期の境界で読み、シーケンサーが次のジェスチャーを予約してから描画し、描いたフレーム数を `pos` に加える。上流試験はイベントの絶対サンプルを固定し、128フレームの基準と1、77、4,096、48,000フレームの呼び出しをビット照合する。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究版の通常画面から診断用の同期描画を指定すると、構築時に使い捨ての発声器を256フレーム進め、発話用の描画は武装から2,048フレーム後に始まる。発話用WASMの位置と保存WAVは通常再生を基準に照合する。48 kHz・256フレームの機器予算は約5.333 ms。以前の48 kHzの同期描画では構築を含む要求と、先頭3量子のうち2量子を含む要求の両方で飛びが出た。後者の1件ではcubebが5.269 ms、クライアントI/Oが5.275 msだった。今回は先頭3量子を含む要求が両端の相関窓に入らない前後各20要求で、cubeb、FirefoxのI/O、サーバーのWrite、タップの順に照合する。[診断の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L236)・[過去のI/Oの実測](#確認用07の出力要求をaudio-clientとaudio-serverへ対応付ける)・[事前登録](../cases/worklet-live-tsp-firefox-device-tap-draw.json)

複数の飛びを同じタップ窓に含む場合は、タップの増分が予定サンプル位置の全増分と一致することを確かめる。1件ずつ、直前の返却バッファの先頭と次の予定位置にゼロを挿入する候補を比べる。二つの候補の前後512フレームを上限に、隣接する飛びを避けた局所窓でゲインを最小二乗で合わせる。残差は `||観測 − ゲイン × 候補|| / ||観測||` とする。前後128フレームを確保し、残差0.025以下、候補間で0.03以上離れた場合に位置を選ぶ。独立に生成した2個の256点の挿入を別々の候補へ置いた対照では、両方を正しく選んだ。既存の構築直後の飛び4件を再解析すると、全件で直前の要求位置を選び、完全ゼロの161点を再計数できた。[局所比較の実装](../tools/measure_worklet_tsp_device_tap.py)・[既存の同時採取](#確認用07のio時刻とプロセスタップのpcmを照合する)

過去のタップなしの同期描画4試行では、構築を含む機器要求は先行音の24,576フレームから始まった。タップ付きの既存4試行では30,720〜37,888フレームで、128〜277 ms遅かった。先行音側は192量子の完了と採取側の解放の両方を待つ。採取側は同じFirefoxのタップが準備できてから100 ms待って解放する。派生ケースではタップ起動依頼を第64量子から第1量子へ早め、192量子と100 msの待機は維持する。構築を含む要求の位置が元の時点から256フレーム以内に入った試行を数える。[先行音のゲート](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs#L61)・[タップの準備通知](../tools/measure_worklet_live_song_process_tap.py#L283)・[早期起動の登録](../cases/worklet-live-tsp-firefox-device-tap-draw-early.json)

### 実測

macOS 15.6.1 arm64、試験用Firefox 157.0、Instruments 26.0で、同じ外部ヘッドフォンを48 kHz・256フレームに保った。第64量子からの起動は作業ディレクトリから8試行、第1量子からの起動は `/private/tmp` から8試行を実行した。早期起動の7試行で、構築を含む要求が過去のタップなしと同じ24,576フレーム目から始まった。残る1試行は28,160フレームから始まった。全16試行で通常発話とWAVの107,527サンプル、観測3,361点と計画が一致した。固定上流とのPCM最大絶対差は `1.1641532182693481e-10`。[第64量子起動の結果](../runs/worklet-live-tsp-firefox-device-tap-draw-20261122-a/summary.json)・[第1量子起動の結果](../runs/worklet-live-tsp-firefox-device-tap-draw-early-20261122-a/summary.json)

| 観測 | 第64量子からタップ起動 | 第1量子からタップ起動 |
| --- | ---: | ---: |
| 構築を含む要求の先行音位置の中央値 | 31,744フレーム | 24,576フレーム |
| 元の位置から256フレーム以内 | 0/8 | 7/8 |
| 先頭3量子を含む最長要求の中央値 | 3.759 ms | 4.283 ms |
| 構築直後の予定時刻の飛び | 8/8 | 8/8 |
| 発話開始付近の予定時刻の飛び | 0/8 | 0/8 |

16件の構築時の飛びはいずれも256フレームだった。タップに増えた256フレームのうち完全ゼロは161〜162点で、局所比較は全件で飛ぶ直前の要求の先頭を選んだ。保存したcubebの波形を三次補間する別計算でも、直前に挿入したときの相対RMS残差は0.67〜0.93%、次の予定位置に挿入したときは58.4〜62.0%だった。サーバーの中間Writeに対応するタップの256点には完全ゼロがなく、cubebが直前に返した先行音との残差は0.76〜0.91%だった。タップとサーバーの時計が対応した位置で、Firefoxのプロセス出力を観測している。[初回の対応表](../runs/worklet-live-tsp-firefox-device-tap-draw-20261122-a/summary.json)・[早期起動の対応表](../runs/worklet-live-tsp-firefox-device-tap-draw-early-20261122-a/summary.json)

発話開始の最長要求は同時採取16試行で3.521〜4.819 msだった。過去のタップなしの同期描画4試行の範囲は4.813〜5.545 ms。早期起動で構築位置を元に戻した条件でも、先頭のWASM処理は中央値1.625 msで、タップなしの2実行の中央値1.979 msと2.082 msより短かった。差は機器要求へ返す前のWorklet計時にも現れている。起動時点に加えてタップの有無と先行音が異なるため、次は同じ滑らかな先行音と同じ構築位置でタップの有無を比較する。予算内で飛んだ時点のタップPCMは未観測のまま残る。[従来のI/Oの初回](../runs/worklet-live-tsp-firefox-device-io-20261122-a/summary.json)・[従来のI/Oの再実行](../runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)

2実行の各256判定と固定上流の各11試験を確認した。672機器要求の時刻、16件の挿入位置、サーバー中間位置のPCMを生データから検算した。673入力・2,794出力のサイズとSHA-256を照合し、出力669,232,343バイトをRTL9210B-CGへ保存した。[第64量子起動のマニフェスト](../runs/worklet-live-tsp-firefox-device-tap-draw-20261122-a/manifest.json)・[第1量子起動のマニフェスト](../runs/worklet-live-tsp-firefox-device-tap-draw-early-20261122-a/manifest.json)

### 再現

`research/experiments/chimera-rebuild` から試験用Firefoxと校正済みタップを指定する。早期起動は別の実行IDで最後に `--draw-case cases/worklet-live-tsp-firefox-device-tap-draw-early.json` を加える。

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build
export CHIMERA_FIREFOX="$build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1000000000 \
  ../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py \
  worklet-live-tsp-firefox-device-tap-draw-local --device-tap-draw "$build/chimera-process-tap/CHIMERA-PCM-Probe.app"
```

## 確認用07の同期描画でタップの有無を比較する

固定上流の `AudioEngine.build()` は指定レートのContextに2チャンネルの `ChimeraProcessor` を接続する。各 `process()` はチャンネルのフレーム数で `engine_render()` を呼び、WASMが返したFloat32を左右へ複写する。Rustの `Engine::render()` は絶対フレーム位置が128の倍数でシーケンサーを更新し、次の境界まで描画して位置を進める。ホスト幅の試験はイベントの絶対位置を固定し、128フレームの基準と1、77、4,096、48,000フレームの呼び出しをビット照合する。研究版は同じ保存済みの発話入力と同期事前描画を共用し、タップの扱いをブラウザ外のゲートで切り替える。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[Rust描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

両条件とも同じ滑らかな先行音と、1量子目で依頼して192量子目まで待つゲートを使う。タップ付きは採取アプリからの準備通知の後に100 ms待つ。タップなしは依頼から100 ms待ち、アプリの起動を省いて解放する。ブラウザは先行192量子と外部ゲートの両方を待つ。構築の機器要求の先頭が両条件で一致し、先行音24,576フレームから256フレーム以内であり、発話の最初の2量子が同じ相対位置の要求に入る組を選ぶ。外部ゲートの解放時刻と、構築を含む実際の機器要求の位置は別々に保存する。[先行音のゲート](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs#L61)・[採取側の制御](../tools/measure_worklet_live_song_process_tap.py#L283)・[事前登録](../cases/worklet-live-tsp-firefox-device-tap-draw-control.json)

各段の値は、最初の2量子のWASM呼び出し時間の和、二つのWorklet外枠の和、対応するグラフ反復の経過時間、同じcubeb要求の入口から返却まで、対応するAudio Client I/O区間とする。単位はms。タップ付きからタップなしを引いて対応差を求め、中央値の絶対値が0.25 ms以上かつ少なくとも3組で同方向の段を記録する。これは今回の比較で事前に定めた判定基準である。発話開始時に時刻の飛びが出た場合は、機器の時間予算と、タップが付いた側のPCMも別に調べる。[段ごとの計時](../tools/measure_worklet_live_tsp_firefox_render_phases.py#L61)・[対応差の集計](../tools/measure_worklet_tsp_device_tap.py)

### 初回の配置と発話開始のPCM

初回はタップなしの4試行がすべて24,576フレームにそろい、タップ付きは1試行だけが同じ位置だった。残りは26,112、34,816、36,864フレーム。外部ゲートの依頼から解放まで、タップなしでは109〜119 ms、タップ付きでは489〜757 msだった。組の条件は維持し、構築をそろえられなかった3組を集計から外した。次のケースでは、先行音の開始を設定時点のContextより128量子先に置き、先行音が鳴る前に両条件の外部ゲートへ依頼する。同じ先行音と192量子の待機を保ち、発話開始までの準備時間を確保する。[初回の組別判定](../runs/worklet-live-tsp-firefox-device-tap-draw-control-20261122-a/summary.json)・[先行音前の依頼ケース](../cases/worklet-live-tsp-firefox-device-tap-draw-control-early.json)

初回1組目のタップ付きでは、構築直後に512フレーム、発話開始の最初の2量子を含む要求で256フレーム飛んだ。後者のcubebは5.6515 ms、Audio ClientのI/Oは5.6591 msで、いずれも時間予算5.333 msを超えた。タップの増分は合計768フレームだった。二つの飛びをそれぞれ局所比較すると、発話開始の飛びでは直前の要求の先頭に挿入したときの残差が1.053%、次の予定位置で59.072%。161フレームの完全ゼロは前者の候補位置にあり、サーバーの中間Writeに対応するタップ区間には完全ゼロがなかった。同じ入力の発話WAVは通常再生とバイト一致した。この試行の構築位置は組の比較条件から外れている。[初回の局所比較](../runs/worklet-live-tsp-firefox-device-tap-draw-control-20261122-a/summary.json)・[該当試行の2量子の計時](../runs/worklet-live-tsp-firefox-device-tap-draw-control-20261122-a/artifacts/1-tap/aligned-quanta.csv)

### 先行音前から準備した実測

macOS 15.6.1 arm64、試験用Firefox 157.0、Instruments 26.0、同じ48 kHz・256フレームの外部ヘッドフォンで、先行音前の依頼を `/private/tmp` から試した。8試行すべてで、先行音の開始16,384フレーム前に外部ゲートへ依頼し、構築の機器要求は先行音の24,576フレームから始まった。発話の先頭2量子は各試行とも構築から数えて12番目の後続要求に入った。タップなしの4試行では採取プロセスの起動・出力ファイルがなく、タップ付き4試行では取得PCMを照合できた。[再実行の比較表](../runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/summary.json)

| 発話の先頭2量子に対応する計時 | タップ付きからタップなしを引いた4組の中央値 |
| --- | ---: |
| WASM呼び出しの和 | +0.041 ms |
| Worklet外枠の和 | +0.005 ms |
| グラフ反復 | +0.015 ms |
| cubebコールバック | +0.019 ms |
| Audio Client I/O | +0.019 ms |

全ての段で短くなった組と長くなった組が各2組だった。WASMの対応差は−0.723〜+0.913 msで、0.25 ms以上かつ3組で同方向という事前基準に達した段は0件だった。初回の条件を満たした1組は、この4組へ加えずに保存した。[組ごとの時間](../runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/summary.json)・[初回の比較可否](../runs/worklet-live-tsp-firefox-device-tap-draw-control-20261122-a/summary.json)

### 予算内の飛びとタップPCM

先行音前の依頼の第2組と第4組のタップ付きで、最初の2量子を含む要求の処理時間が予算内に収まった後、予定時刻が256フレーム飛んだ。いずれも次のFirefox I/Oまでの間に中間I/Oが見つからず、次のI/Oに `Overload` が記録された。サーバーには飛びに対応する中間Writeがあった。[同時採取の実行結果](../runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/summary.json)

| 観測 | 第2組 | 第4組 |
| --- | ---: | ---: |
| cubebの処理時間 | 5.119 ms | 5.246 ms |
| Audio Client I/O区間 | 5.126 ms | 5.257 ms |
| cubebの返却から予定出力まで | 1.752 ms | 1.607 ms |
| 次のI/O開始まで | 10.678 ms | 10.666 ms |
| 飛びの直前の要求位置に対応する完全ゼロ | 161フレーム | 161フレーム |

各試行には構築直後にも256フレームの飛びがあり、全窓でタップの採取長は合計512フレーム増えた。発話開始の飛びを独立に比較すると、cubebから採った波形を三次補間したゼロ挿入モデルは直前の要求位置で残差0.96〜1.05%、次の予定位置で約60.0%だった。中間Writeに対応するタップ区間には完全ゼロがなく、cubebが直前に返した先行音と0.62〜0.68%の残差で一致した。予算を超えた初回1組目の発話開始でも同じ位置に無音が出た。今回確認したのはFirefoxのプロセス出力。全プロセスの混合波形、ヘッドフォン端子、次のFirefox I/Oが1周期遅れた仕組みの確認が残る。[第2組のタップ記録](../runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/artifacts/2-tap/tap.json)・[第4組のI/O記録](../runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/artifacts/4-tap/audio-hal-client-io-cycle.xml)

2実行の各244判定と固定上流の各11試験が通過した。16試行で発話WAVは通常再生とバイト一致し、発話状態も一致した。固定上流とのPCM最大絶対差は `1.1641532182693481e-10`。生PCMと計時から672要求を検算した。677入力と2,754出力をサイズとSHA-256で照合した。記録した出力668,214,246バイトはRTL9210B-CGへ保存した。[初回の実行記録](../runs/worklet-live-tsp-firefox-device-tap-draw-control-20261122-a/manifest.json)・[先行音前の依頼の実行記録](../runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/manifest.json)

### 再現

`research/experiments/chimera-rebuild` から実行する。初回の対照を再実行する場合は `--draw-case` に `cases/worklet-live-tsp-firefox-device-tap-draw-control.json` を指定し、新しい実行IDを使う。

```bash
build=/Volumes/RTL9210B-CG/voice-simulator/build
export CHIMERA_FIREFOX="$build/chimera-cubeb-output/obj-gecko/dist/Nightly.app/Contents/MacOS/firefox"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1000000000 \
  ../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py \
  worklet-live-tsp-firefox-device-tap-draw-control-early-local \
  --device-tap-draw "$build/chimera-process-tap/CHIMERA-PCM-Probe.app" \
  --draw-case cases/worklet-live-tsp-firefox-device-tap-draw-control-early.json
```

## 確認用07で次のFirefox I/Oが飛んだ周期を照合する

固定上流の `AudioEngine.build()` が作るContextでは、`ChimeraProcessor.process()` が要求されたフレーム数を `engine_render()` に渡し、Rustの `Engine::render()` から返ったFloat32を左右へ複写する。Rustは位置 `pos` が128の倍数でシーケンサーを更新し、描画後に進めたフレーム数を `pos` に足す。ホスト幅の試験は入力イベントの絶対位置を固定し、呼び出し幅を変えたPCMを比較する。ここでは通常画面の発話WAVが一致する収録を使い、Workletより下流の機器要求を解析した。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

保存済みの8試行から、同期描画の要求を0として11、12、13番目の24要求を比較した。12番目に発話の先頭2量子が入る。48 kHzの256フレーム周期は約5.333 ms。cubebの予定ホスト刻みとサーバー側クライアント表を対応付け、現在のサーバー出力サンプル位置に256を足した次の周期を選ぶ。ハードウェア表では、同じスレッド・エンジン・ストリームのWriteをサンプル位置で結ぶ。現Firefox I/Oの開始を原点に置き、cubebのMach時刻は元のI/O照合から得たトレース原点の幅を使って範囲で示す。8試行の発話WAVは通常再生とバイト一致し、固定上流との差は最大 `1.1641532182693481e-10` だった。[事前登録](../cases/worklet-live-tsp-firefox-io-deadline.json)・[生データとの時刻照合](../tools/measure_worklet_tsp_io_deadline.py)・[I/O時刻表](../runs/worklet-live-tsp-firefox-io-deadline-20261122-a/artifacts/io-events.csv)

| 発話開始の要求 | 現Firefox I/O終了から1周期後のサーバー処理開始まで | そのサーバー処理開始から同じ周期のWrite開始まで |
| --- | ---: | ---: |
| 予算内で飛んだ第2組・タップ付き | +207.5 µs | 7.5 µs |
| 予算内で飛んだ第4組・タップ付き | +58.5 µs | 6.5 µs |
| 予算を超えて飛んだ第2組・タップなし | −174.0 µs | 184.5 µs |
| 飛ばなかった発話開始要求5件 | +293.9〜1,785.7 µs | 2,661.8〜3,040.8 µs |

予算内の2件で「現在のFirefox I/Oが次のサーバー処理開始まで残っていた」という予測は外れた。cubebの返却も、トレース原点の不確かさを含めて第2組で209.6〜213.0 µs、第4組で61.1〜64.7 µs先行した。別計算ではWrite表の `current-host-time` とイベント時刻からトレース原点を求め、24要求すべてで元の原点区間に収まること、返却の順序が変わらないことを確認した。サーバー側は1周期の間隔で処理を続け、飛んだ周期のWriteを次に観測されたFirefox I/Oの開始前に行った。飛ばなかった発話開始要求のWriteは、次のFirefox I/Oの終了の13.1〜21.7 µs後だった。観測上の差は、前のI/Oの返却から次のサーバー周期へ移ったところで、FirefoxのI/Oが見つからないままWriteへ進んだことにある。[照合結果と予測の判定](../runs/worklet-live-tsp-firefox-io-deadline-20261122-a/summary.json)

### サーバーのClient StartとFirefoxのIOProc

同じトレースから `audio-hal-io-cycle-client-start` と `audio-hal-client-io-cycle-ioproc` を抽出した。24要求に対応する51件のサーバー処理は、同じサーバースレッド、予定出力位置とホスト時刻でClient Startへ一意に結び付いた。51件すべてで両表の時刻がナノ秒単位まで一致した。予算内の2件と予算を超えた1件で、欠けた周期にもサーバーのClient Startが1件ずつあり、対応するFirefox親PID・I/OスレッドのIOProcは0件だった。Client Startの時刻はサーバー処理区間の開始と一致するため、この観測で確定できる境界はサーバーの処理開始からFirefoxのIOProcまで。OSの通知、起床、実行開始のどこで差が出たかは次の観測に残す。[追加照合の事前登録](../cases/worklet-live-tsp-firefox-io-client-start.json)・[全件の結果](../runs/worklet-live-tsp-firefox-io-client-start-20261122-a/summary.json)・[周期ごとの対応表](../runs/worklet-live-tsp-firefox-io-client-start-20261122-a/artifacts/client-start-slots.csv)

予算内で飛んだ第2組の `kdebug` 表も抽出した。134,043行のクラス値は7、31、33で、SDKがスケジューラ記録に割り当てるMachクラス1はなかった。現行のInstrumentsには `Thread State Trace` があるため、次の収録では `Audio Client`、`Audio Server` と合わせ、欠けた周期のFirefox I/Oスレッドの実行可能化と実行開始を対応付ける。[元のI/Oトレース](../runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/artifacts/2-tap/io-toc.xml)・[インストール済みSDKのクラス定義](/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX26.2.sdk/usr/include/sys/kdebug.h#L102)

時刻軸の再解析は研究ワークスペースと `/private/tmp` から各56判定を通過し、要約JSONと時刻表がバイト一致した。Client StartとIOProcは24判定を通過した。XMLを別に読み直して、51件の開始時刻と3件の欠けたIOProcを検算した。3実行の1,341入力・23出力をサイズとSHA-256で照合した。追加抽出したトレース表と結果約11 MBはRTL9210B-CGに保存した。[時刻軸の初回](../runs/worklet-live-tsp-firefox-io-deadline-20261122-a/manifest.json)・[別ディレクトリからの再解析](../runs/worklet-live-tsp-firefox-io-deadline-20261122-repeat/manifest.json)・[Client Startの実行](../runs/worklet-live-tsp-firefox-io-client-start-20261122-a/manifest.json)

### 再現

`research/experiments/chimera-rebuild` から保存済みのトレースを読む。実行IDは実行ごとに変える。Client Startのケースにある時刻軸の実行IDは、本文のマニフェストを参照する。

```bash
../../.venv/bin/python tools/measure_worklet_tsp_io_deadline.py worklet-live-tsp-firefox-io-deadline-local
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 \
  ../../.venv/bin/python tools/measure_worklet_tsp_io_client_start.py worklet-live-tsp-firefox-io-client-start-local
```

## 確認用07で欠けた周期のFirefox I/Oスレッドの状態を読む

固定上流の `AudioEngine.build()` は指定レートのContextを起動し、`ChimeraProcessor.process()` が要求されたフレーム数をWASMの `engine_render()` に渡す。Rustの `Engine::render()` は出力位置が128フレーム境界に来たところでシーケンサーを更新してから描き、位置を描画分だけ進める。上流のホスト幅試験は絶対位置を固定したイベントとPCMを照合する。この比較でもブラウザの通常画面で同じ英語発話を再生し、同期事前描画、音声WAV、固定上流との差を保ったまま、機器側に `Thread State Trace` を追加した。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

最初の6試行は、`Audio Client`、`Audio Server`、`Thread State Trace` を9秒の指定で起動した。トレースの目次にスレッド状態とコンテキストスイッチの表はあった。音声I/O表の最後の記録は開始後0.536〜1.309秒で、6試行ともFirefox親PIDに対応する行は0件だった。ブラウザとタップはPCMを取得できていたが、この収録から対象のI/Oスレッドの状態を判定することはできなかった。次の収録ではブラウザとタップを起動してからトレースを始め、開始のDarwin通知を受けて140 ms後に構築を解放する。1秒の短い収録で、構築前後20要求と発話開始を覆う条件を登録した。[最初の条件](../cases/worklet-live-tsp-firefox-io-thread-state-capture.json)・[初回の欠測](../runs/worklet-live-tsp-firefox-io-thread-state-capture-20261122-a/summary.json)・[収録開始を移した条件](../cases/worklet-live-tsp-firefox-io-thread-state-capture-gated.json)

各要求について、サーバー出力位置を256フレームずつ進めて次の二つの周期を特定する。その開始から開始までを対象区間とし、先行25 µsと、前のFirefox I/Oの終了までの重なりを分けて記録する。Firefox親PIDとAudio ClientのI/Oスレッドを、同じトレース上のIOProcと `thread-state` に対応させる。状態の区間を切り出し、待機、実行可能、実行中の時間と、状態表の空白を数える。実行中の区間が前のI/Oの持ち越しに当たる場合は、前のI/Oが終了した後の状態で判定する。人工の区間で、待機と空白を別の結果として照合した。[状態の比較ケース](../cases/worklet-live-tsp-firefox-io-thread-state.json)・[状態表の解析](../tools/measure_worklet_tsp_io_thread_state.py)

ブラウザとタップの準備後に収録した4試行では、発話開始前のゲートで2.754〜3.499秒待った。cubebの計測は最初の256コールバック、48 kHz・256フレームでは約1.365秒分を保持する。2試行でFirefox親PIDのAudio Client行を46件、96件取得したが、cubebに残った区間と照合できなかった。残り2試行も構築前後のグラフ窓の照合に失敗した。発話WAVは4試行とも通常再生に一致した。[4試行の実測](../runs/worklet-live-tsp-firefox-io-thread-state-capture-gated-20261122-a/summary.json)・[欠測4件の判定](../runs/worklet-live-tsp-firefox-io-thread-state-20261122-a/summary.json)・[cubebの保存上限](../tools/chimera-cubeb-output-snapshot.patch)

実時間の再生ボタンを押す前にゲートを設けた。ブラウザで保存ケースの読込みとオフライン再生を済ませてから計測器を起動し、Darwinの開始通知を受けて実時間のAudioContextを作る。先行音の準備を192量子から80量子へ短縮した。プロセスタップを起動せず、先行音、cubeb、Audio Client、Audio Server、スレッド状態を照合する。タップありの実測は既存の別条件として参照する。[再生前に収録するケース](../cases/worklet-live-tsp-firefox-io-thread-state-capture-preplay.json)・[最初のタップPCM比較](#確認用07の同期描画でタップの有無を比較する)

再生前に収録した4試行のうち、第1・3・4試行は、構築前後20要求のcubeb、Audio Client、Audio Serverを一意に照合できた。第2試行はFirefoxのAudio Client行が58件あり、トレース時刻1,009 msで途切れた。構築前後のcubeb窓は892〜1,116 msに渡り、発話開始はAudio Clientの記録範囲外だった。照合した3試行では、構築直後に256フレームずつ予定位置が飛んだ。このときのcubeb処理は7.963〜8.489 msで、256フレームの5.333 msを超えていた。4試行とも発話WAVと発声状態は通常再生に一致した。[再生前収録の要約](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-20261122-a/summary.json)・[収録コマンドと環境](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-20261122-a/manifest.json)

| 試行 | 前のI/Oがサーバー周期開始を越えた時間 | I/O終了後も続いた同じ実行区間 | その後の待機 | 欠けた周期のIOProc |
| --- | ---: | ---: | ---: | ---: |
| 第1試行 | 2.305 ms | 2.542 µs | 2.691 ms | 0 |
| 第3試行 | 2.892 ms | 3.625 µs | 2.159 ms | 0 |
| 第4試行 | 2.393 ms | 3.250 µs | 2.615 ms | 0 |

第2版はAudio Clientの終了後に計上された実行を `running_without_ioproc` と判定した。3件とも元の状態行はAudio Clientの終了前に始まっていた。状態の空白や重複はなかった。第3版では同じ行が続いた数µsを表示し、その後の状態を `blocked_after_previous_run` と記録した。発話開始付近の連続する9周期は、それぞれ1回のIOProcと実行区間を含んでいた。予算内で飛んだ既存2件のスレッド状態は依然として欠測。[第2版の判定](../runs/worklet-live-tsp-firefox-io-thread-state-20261122-preplay/summary.json)・[同じXMLから再判定した第3版](../runs/worklet-live-tsp-firefox-io-thread-state-20261122-continuations/summary.json)

欠けた3周期のAudio Serverの実測開始間隔は4.998〜5.055 msで、予定5.333 msとの許容差0.100 msを外れた。連続する9周期はこの許容差内だった。出力位置とホスト時刻は256フレームの周期に沿っており、状態の集計窓には各サーバー行の実測開始時刻を用いた。条件を外れた3件と第2試行の欠測を、不合格の理由として解析に保存した。[予定時刻と実測時刻](../runs/worklet-live-tsp-firefox-io-thread-state-20261122-continuations/summary.json)・[構築で先行した3件の機器記録](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-20261122-a/summary.json)

## 確認用07の先行音を56量子にしてI/Oの収録範囲を測る

固定上流の `AudioEngine.build()` はContextの生成と再開、モジュールの読込み、発声ノードの構築を順に行う。`ChimeraProcessor.process()` は出力バッファの長さからWASMの `engine_render()` にフレーム数を渡し、戻り値の指す `f32` のPCMをチャンネルに送る。Rustの `Engine::render()` は通算位置 `pos` を128フレームで割った余りから次の区切りまでの長さを求め、区切りの先頭でシーケンサーを更新する。描画した分だけ `pos` を進めるので、ホストが一度に求める長さを変えても絶対位置で制御できる。上流試験は1、77、128、4,096、48,000フレームの要求でPCMのビットを照合する。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

研究用の `SharedContextMarker.process()` はContextの `currentFrame` が先行音の開始位置に達してから量子を数え、指定した個数に達すると `ready` を通知する。ブラウザ側の `installSharedContextMarker()` はこの通知を受けるまで `addModule()` の処理を保留し、その後に通常の発声ノードが構築される。80量子の相対位置10,240フレームを56量子の7,168フレームに移せば、差は3,072フレームで48 kHzでは64 msになる。発声エンジンの開始サンプルと入力は固定する。先行音の開始はContextの現在位置から8量子先に予約するため、実時間上の差にはContextの準備時間のばらつきも入る。[先行音の観測器](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js#L13)・[ブラウザの待機処理](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs#L32)・[56量子の収録条件](../cases/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q.json)

音声I/O表の末尾からcubebの発話開始要求までの余裕を、各トレースのMach時計に換算して比べる。メタデータで換算したトレース起点の誤差は従来どおり2 msを見込む。前後20要求の全窓は従来の基準で判定し、照合できない場合は登録した10〜16番目の要求とその次の要求を同じ許容差で照合する。Audio Clientは各コールバックを実測の開始間隔と前後の包含関係で、Audio Serverは予定ホスト時刻と256フレーム間隔で対応させる。発話の最初の3量子を含む要求をすべて集計する。[解析の登録条件](../cases/worklet-live-tsp-firefox-io-thread-state-preplay-56q.json)・[既存のI/O照合を使う解析](../tools/measure_worklet_tsp_io_thread_state.py)

56量子の6試行すべてで、先行音の開始から7,168フレームで構築した。80量子の4試行は10,240フレームだった。発話の先頭3量子は各試行で要求12と13に入り、cubebの予定時刻はこの2要求の前後で連続していた。発話WAVと発声状態は6試行とも通常再生に一致した。固定上流との差は全107,527フレームで最大 `1.164×10⁻¹⁰`。固定上流の11試験も通過した。[収録と実行環境](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q-20261122-a/manifest.json)・[発話と機器要求の結果](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q-20261122-a/summary.json)

全窓を照合できたのは80量子が3/4、56量子が1/6だった。56量子の第1〜5試行では、Firefoxの最終Audio Client行が先頭発話量子のcubeb要求より5.385〜301.966 ms早く終わり、事前に指定した局所窓も欠測した。第6試行では発話開始付近の連続する3周期に各1回のIOProcがあり、構築直後の予算超過で飛んだ周期には前の実行区間の末尾と、その後の待機があった。既存の0.100 msのサーバー周期許容差は、この構築直後の周期で外れた。[第1版の照合](../runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-a/summary.json)・[サーバーとスレッド状態の詳細](../runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-cutoffs/summary.json)

| 試行 | Audio Clientの最後 | Audio Serverの最後 | 機器Writeの最後 | トレース目次の期間 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 491.853 ms | 491.862 ms | 492.467 ms | 1,308.362 ms |
| 2 | 662.597 ms | 662.602 ms | 657.544 ms | 1,314.312 ms |
| 3 | 779.072 ms | 779.085 ms | 778.980 ms | 1,310.996 ms |
| 4 | 656.151 ms | 656.155 ms | 656.471 ms | 1,314.294 ms |
| 5 | 772.443 ms | 772.453 ms | 772.544 ms | 1,317.880 ms |
| 6 | 935.213 ms | 935.221 ms | 930.277 ms | 1,329.551 ms |

トレース時刻はnsをmsに換算し、各表の最終値は対象プロセスを限定せずに行の開始と継続時間を加えて求めた。音声I/Oの3表は全試行で最大5.058 ms以内に途切れ、トレース目次が報告した期間より短かった。実行ログは指定時間への到達を記録した。Firefoxと他プロセスのAudio Client行を含めて途切れているため、次は先行音56量子と収録時間を固定し、Thread State Traceの有無で3表の最終時刻を比べる。現時点では収録範囲を制限した原因は未特定。[最終時刻を追加した再解析のコマンドと入出力](../runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-cutoffs/manifest.json)・[第1試行のトレース目次](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q-20261122-a/artifacts/1-draw/io-toc.xml)・[Audio Client](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q-20261122-a/artifacts/1-draw/audio-hal-client-io-cycle.xml)・[Audio Server](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q-20261122-a/artifacts/1-draw/audio-hal-io-cycle-client.xml)・[機器Writeを含む表](../runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q-20261122-a/artifacts/1-draw/audio-hal-io-cycle-hardware.xml)

## 確認用07でThread State Traceの有無を比較する

固定上流は `AudioEngine.build()` で指定レートのContextを再開してから、Workletモジュールを読み込み発声ノードを構築する。`ChimeraProcessor.process()` は出力バッファのフレーム数でWASMの `engine_render()` を呼び、戻り値の指す `f32` PCMを出力する。`Engine::render()` は通算の出力位置を128フレーム単位で区切り、各区切りの先頭でシーケンサーの時刻を更新する。上流のホスト幅試験は可変長の要求と128フレーム要求のPCMをビット単位で照合する。今回の条件では同じ発話入力と量子を使い、この描画経路の外で起動するトレースの収録器だけを切り替える。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

再生前のDarwin通知、先行音56量子、同期事前描画、全プロセスの1秒収録を固定する。各組でAudio Client・Audio Serverを収録し、片方だけにThread State Traceを足す。4組で実行順を交互に反転する。Firefoxの最後のAudio Client行の終了時刻から、先頭発話量子を含むcubeb要求の入口時刻を引く。トレース起点は各収録のMach時計へ換算し、許容誤差は各2 msとする。音声I/Oのみの条件で差が4 msを超えて増えた組が3組以上あり、発話開始の照合窓が増えれば予測を支持すると事前に定めた。両端の波形と状態、構築位置、要求12と13を確認してから組内の差を比較する。[収録条件と予測](../cases/worklet-live-tsp-firefox-trace-instruments-56q.json)・[収録起動](../tools/capture_worklet_system_pair.py#L56)・[比較コード](../tools/measure_worklet_tsp_io_trace_instruments.py)

| 組 | 併用条件の発話開始からAudio Client末尾まで | 音声I/Oのみの条件での同じ余裕 | 組内の実測差 | 実際の構築位置 |
| --- | ---: | ---: | ---: | --- |
| 1 | −261.213 ms | 551.753 ms | +812.966 ms | 両条件とも7,168フレーム |
| 2 | +34.957 ms | 546.480 ms | +511.523 ms | 両条件とも7,168フレーム |
| 3 | −101.475 ms | 562.687 ms | +664.162 ms | 併用条件が128フレーム後 |
| 4 | −74.088 ms | 546.992 ms | +621.079 ms | 音声I/Oのみの条件が256フレーム後 |

音声I/Oのみの4試行では構築前後20要求の全窓を照合でき、3表はトレース目次上の末尾から4 ms以内まで残った。併用条件では3表の末尾がトレース開始後約0.678〜0.879秒にあり、全窓の照合は0/4だった。全8試行の発話WAVと発声状態は通常再生に一致し、固定上流との差は最大 `1.164×10⁻¹⁰`。構築位置が一致した2組の差は+511.523 msと+812.966 msだった。全4組がそろうという解析条件を満たさなかったため、登録した予測の最終判定は保留した。第3・4組の差は実測値として保存した。[初版の判定](../runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-cutoffs/summary.json)・[構築位置と余裕を別に検算した実行](../runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-followup/summary.json)

先行音の観測器は全8試行で相対7,168フレームに達するまでの56量子を採取した。観測器が送った `ready` はポートから非同期に受け取り、その後にブラウザが発声ノードの構築へ進む。今回の第3・4組では機器要求に対応するグラフの構築位置が56量子を処理した境界から1〜2量子後ろにあった。第2組の併用条件では登録した局所窓を照合でき、発話開始付近で状態を照合した2周期に各1回のIOProcがあり、実行時間は28.708 µsと20.666 µsだった。今回の8試行の発話開始ではcubebの予定位置の飛びはなかった。保存済みの生データを同じ解析で読み、以前に観測した予算内の256フレームの飛び2件を再検出した。[先行音の通知](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js#L25)・[ノード構築前の待機](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs#L71)・[局所窓のスレッド状態](../runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-followup/summary.json)

Xcode 26.2のローカルの `xctrace help record` では `--window` で終了直前のイベント保持範囲を指定できる。今回のcubeb窓を各トレースの時計に換算すると、末尾900 msの開始時刻は全8試行で比較窓の最初の要求より159.7 ms以上早い。次は3つの収録器を併用したまま保持窓を設定し、音声I/Oの3表とFirefoxの状態が同じ発話区間を覆うか測る。比較窓の最初の要求も採取できるかを同時に確認する。[今回のトレース時刻と収録経路](../runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-a/manifest.json)・[末尾の集計](../runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-followup/summary.json)

## 確認用07で終了前900 msの保持窓を比較する

固定上流の `AudioEngine.build()` はContextを再開してからWorkletを読み込み、発声ノードを構築する。実時間の `ChimeraProcessor.process()` はホストの出力フレーム数をWASMの `engine_render()` へ渡し、`f32` のPCMを出力チャンネルに書く。Rustの `Engine::render()` は通算出力位置の128フレーム境界でシーケンサーを更新してから次の区間を描く。上流試験はホストの要求長を変え、同じ通算位置のPCMをビット単位で照合する。この比較で切り替えるのは、再生前に動かす `xctrace record` の終了前保持窓だけである。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

確認用07を先行音56量子、48 kHz、256フレームの機器要求で再生する。3つの収録器、全プロセス、1秒の制限、Darwinの開始通知を固定し、4組で `--window 900ms` の有無と順番を切り替える。準備の境界は7,168フレームで、実際の構築は1機器要求分の遅れまで許容した。実測したcubeb要求の入口を基準に、音声I/O各表の始点と終点、全窓と局所窓の照合、同じ周期のスレッド状態を比較する。前の比較で遅れが観測された条件と判定は保持する。[収録条件と予測](../cases/worklet-live-tsp-firefox-retained-trace-window-56q.json)・[xctraceの起動処理](../tools/capture_worklet_system_pair.py#L56)・[比較コード](../tools/measure_worklet_tsp_io_trace_instruments.py)

収録途中の検算では、900 msを指定した第1組のトレース目次の期間が33.235 msだった。トレース目次の開始時刻を壁時計からMach時計に換算した値と、機器Writeが持つ絶対ホスト時刻を比較する。各Writeについて `round(current-host-time × Mach tickのns換算) − Write行のstart(ns)` を求めると、その行が示すトレース起点になる。音声サーバーの予定ホスト時刻とcubebの予定ホスト時刻が一致する行も探し、音声側の相対時刻の移動を別経路で確認する。時計起点が登録済みの2 msを超えてずれる試行の時刻差は、時計の検算を加えた判定では欠測にする。Writeから換算した値を使い、発話窓そのものが保持されたかを後から確認する。[機器Writeの抽出](../tools/measure_worklet_tsp_device_io.py#L133)・[時計起点の検算](../tools/measure_worklet_tsp_io_trace_instruments.py)

| 組 | 900 ms指定で残った期間 | Write換算の起点と目次の起点の差 | 保持区間が始まる何ms前に発話が始まったか |
| --- | ---: | ---: | ---: |
| 1 | 33.235 ms | +1,346.199 ms | 473.641 ms |
| 2 | 19.525 ms | +1,354.033 ms | 463.049 ms |
| 3 | 34.204 ms | +1,345.201 ms | 470.759 ms |
| 4 | 19.744 ms | +1,363.492 ms | 497.968 ms |

Write行から得た起点の幅は、保持窓ありの4試行では0.084〜0.250 µsだった。音声サーバーの予定ホスト時刻をcubebの生データに照合した3〜6行も、同じ起点で差が2 ms以内だった。保持窓なしの4試行では、目次とWriteの起点の絶対差は最大0.285 msで、4試行中2試行の全窓で音声I/Oと状態を照合できた。保持窓ありでは発話開始は全試行で実際の保持区間より前にあり、全窓と局所窓は0/4だった。[時計を検算した実行](../runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-write-clock/summary.json)

目次の時刻で比較した初版は4組を数え、予測を支持しなかった。起点の検算後は、登録した時計の許容範囲で比較できる4組がそろわないため、余裕の差の正式判定を保留した。各条件の実際の収録範囲と照合可否は初版から変わらない。全8試行で準備境界と構築位置は7,168フレーム、発話WAVと発声状態は通常再生と一致した。固定上流の11試験を通過した。今回の発話開始にcubebの予定位置の飛びはなかった。[初版](../runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-coverage/summary.json)・[収録コマンドと環境](../runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-a/manifest.json)・[依存する収録物を記録した再解析](../runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-write-clock/manifest.json)

使った収録器は3つを維持した。次は保持窓なしで、全プロセスを収録した条件と、計測用FirefoxのPIDを渡す `xctrace --attach` を比べる。Firefoxの状態とAudio Clientに加え、別プロセスである音声サーバーの行と機器Writeも残るかを最初に確かめる。[Firefox子プロセスを特定する既存処理](../tools/measure_worklet_live_song_process_tap.py#L271)・[xctraceへの対象指定](../tools/capture_worklet_system_pair.py#L56)

## 確認用07で計測用Firefoxへのアタッチを比較する

固定上流の `AudioEngine.build()` はContextを再開し、Workletの読込み後に発声ノードを作る。`ChimeraProcessor.process()` はホストの要求フレーム数をWASMの `engine_render()` に渡し、得られた `f32` PCMを出力する。Rustの `Engine::render()` は通算位置の128フレーム境界でシーケンサーを更新し、次の区間を描いてから通算位置を進める。上流のホスト幅試験は描画の分割を変えても、同じ通算位置のPCMがビット一致することを確かめる。今回の収録対象の切替はこの描画経路の外側で行う。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

計測用Firefoxが再生前の準備を通知したら、ブラウザ起動処理の直下にある親Firefoxを一意に特定する。PIDを小さな準備ファイルで渡し、その後にDarwinの録画開始通知で再生を許可する。同じPIDの識別を全プロセス条件でも行い、片方だけ `xctrace --attach` に渡す。発話、先行音56量子、48 kHzと256フレーム要求、1秒制限、3収録器を固定し、4組で順序を反転する。トレース目次のアタッチ先とcubebの保存先が示すFirefox PIDを照合する。[事前登録](../cases/worklet-live-tsp-firefox-attached-trace-56q.json)・[FirefoxのPID取得](../tools/measure_worklet_live_song_process_tap.py#L271)・[トレース起動とDarwin通知](../tools/measure_worklet_tsp_device_io.py#L47)

機器の要求周期は約5.333 msである。観測したcubebの各要求にAudio Clientを対応させ、予定ホスト時刻のずれ25 µs以内でAudio Serverの周期を選ぶ。対応する予定サンプル位置と要求長の機器Writeが、同じエンジンとストリームで一意に続くことを確かめる。Writeの絶対ホスト時刻から求めたトレース起点は、目次の起点と2 ms以内かも照合する。発話の先頭3量子を含む要求12と13でスレッド状態まで対応させ、初めて同時収録に数える。[サーバーとWriteの照合](../tools/measure_worklet_tsp_io_deadline.py#L91)・[収録範囲の判定](../tools/measure_worklet_tsp_io_trace_instruments.py)

| 組 | 全プロセスの発話開始からAudio Client末尾まで | アタッチの同じ収録余裕 | 組内差 |
| --- | ---: | ---: | ---: |
| 1 | −165.436 ms | −84.805 ms | +80.630 ms |
| 2 | −74.112 ms | +535.726 ms | +609.839 ms |
| 3 | −175.730 ms | Firefoxの行なし | 欠測 |
| 4 | −90.406 ms | −192.151 ms | −101.745 ms |

アタッチ条件の全4試行で、目次に記録されたPIDは準備時およびcubebのPIDと一致した。Audio Server、機器Write、Thread Stateの表も全4試行で取得した。全計測窓を音声I/Oと状態に照合できたのは、第2組のアタッチ条件だけだった。発話開始の要求12・13のサーバー予定位置と機器Writeは、256フレームずつ進む同じ出力ストリームで一致した。状態を照合した2周期にはそれぞれ1回のIOProcがあり、対象スレッドが実行状態にあった時間は25.000 µsと26.083 µsだった。全8試行の発話WAVと発声状態は通常再生に一致し、固定上流の11試験を通過した。第3組の欠測により、登録した4組での予測判定は保留した。[収録と実行環境](../runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-a/manifest.json)・[全試行の時計と同時照合](../runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-coverage/summary.json)

Thread State表の行数は全プロセス条件で88,636〜122,809、アタッチ条件で4,985〜25,437だった。PIDが判別できたFirefox以外の行は、全プロセス条件で47,311〜61,050、アタッチ条件で240〜480だった。アタッチ条件で目次のプロセス数は5〜6、状態表で正のPIDに結び付くプロセス数は92〜138だった。状態表に残ったプロセスの範囲は目次の件数だけからは判断できない。アタッチの目次は起動環境のメタデータも含む。集計は対象PIDとI/O、スレッド状態の時刻を使用した。[状態表に含まれる行の集計](../runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-state-scope/summary.json)・[集計コマンドと入出力](../runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-state-scope/manifest.json)

状態表の最後の区間は目次上のトレース末尾近くまで続いていた。正の継続時間を持つ状態行の開始を集計すると、最後の開始時刻は音声I/Oの3表で最も遅い終了時刻から0.620〜4.129 ms後だった。第3組のアタッチ条件では、最後の新しい状態行は466.380 msに始まり、最後の機器Writeから2.981 ms後だった。音声I/Oと新しい状態行の収録末尾は、全8試行で1機器周期の範囲に収まった。[状態の開始を集計した実行](../runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-state-scope-late-rows/summary.json)

Firefoxの行が欠測した第3組のアタッチ条件では、機器Writeの末尾がトレース開始後463.399 msで、Darwinの開始通知は502.843 ms、cubebの最初のデータコールバックは675.621 msだった。いずれも機器Writeの時計起点から換算した。トレース開始からDarwin通知までは全8試行で299.099〜502.843 msだった。次は標準出力の開始行とDarwin通知の両方を同じ単調時計で取り、再生を許可できる最初の時点と実際の音声I/O収録範囲の関係を調べる。[機器時計とDarwin通知](../runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-coverage/summary.json)・[既存の標準出力待機](../tools/capture_worklet_system_pair.py)

## 確認用07でトレースの二つの開始通知を照合する

固定上流の `AudioEngine.build()` ではContextを再開した後にWorkletを読み込み、発声ノードを構築する。`ChimeraProcessor.process()` はホストの出力バッファのフレーム数で `engine_render()` を呼び、返された `f32` PCMをチャンネルに書く。Rustの `Engine::render()` は通算位置が128フレーム境界のときにシーケンサーを更新し、次の境界までの区間を描いてから位置を進める。上流試験はホストの要求長を1、77、128、4,096、48,000フレームに変えてPCMのビット一致を確認する。今回追加する観測はこの描画の前にある収録の準備処理に置く。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

標準出力パイプとDarwin通知のFDを同じselectorで待ち、読み取り可能になった時点を `time.monotonic_ns()` で記録する。同じ待機の返却で両方を検出した場合は同じ時刻を付ける。`Starting recording` の語句を読めた時点と、改行まで届いた時点を区別する。再生は従来どおりDarwin通知で許可し、ゲートへの通知とブラウザの解放ファイルの時刻も収録する。先行音56量子、1秒、3収録器、保持窓なしを固定し、全プロセスとFirefoxへのアタッチを2組で交互に試す。4試行中3試行で開始行が10 ms以上早く読めるかを判定する。[事前登録](../cases/worklet-live-tsp-firefox-trace-start-signals-56q.json)・[二つの開始通知の観測](../tools/capture_worklet_system_pair.py)・[再生解放](../tools/measure_worklet_live_song_process_tap.py)

機器Writeの `current-host-time` をMach時計のnsに換算し、対応する行のトレース相対時刻を引いて起点を求める。cubebの最初のデータコールバックと先頭発話量子の時刻も同じ時計へ換算する。標準出力を受けた時点へゲートを移した場合は、今回のゲート後の処理時間と機器Writeの末尾が同じと仮定して、発話窓とトレース起点の関係を換算する。この換算は再生時点を実際に切り替えた収録と区別して保存する。[時計と発話の照合](../tools/measure_worklet_tsp_trace_start_signals.py)

| 組 | 収録対象 | Darwin通知に対する開始行の先行 | 開始行から機器時計の起点まで | 全窓が入る追加待機の換算範囲 |
| --- | --- | ---: | ---: | ---: |
| 1 | 全プロセス | 798.042 ms | 350.064 ms | 0〜737.195 ms |
| 1 | Firefox | 1,550.192 ms | 336.391 ms | 41.205〜690.095 ms |
| 2 | Firefox | 847.062 ms | 338.592 ms | 50.802〜706.293 ms |
| 2 | 全プロセス | 639.943 ms | 326.735 ms | 21.002〜351.213 ms |

実測の中央値は822.552 ms先行で、4試行すべてが登録した10 msを超えた。4試行とも開始語句と改行は同じ観測時刻で、Darwin通知後に再生を開始した。機器時計の起点と目次の差は最大0.413 ms。Darwin通知を使った4試行は、発話窓の音声I/Oを最後まで対応させられなかった。観測した処理時間で開始行をそのままゲートにすると、先頭発話量子は時計起点の約125〜211 ms後、全窓の先頭は4試行中3試行で起点より前に来る。全窓が入る追加待機の共通範囲は50.802〜351.213 msだった。開始行と起点の差、発話WAV・発声状態の一致、固定上流11試験を確認した。[採取のコマンドと入出力](../runs/worklet-live-tsp-firefox-trace-start-signals-56q-20261122-a/manifest.json)・[計算と判定](../runs/worklet-live-tsp-firefox-trace-start-signals-56q-20261122-timing/summary.json)

## 確認用07で開始行から200 ms後に再生を許可する

前の同時観測で求めた待機範囲の中点付近から200 msを選び、両条件とも計測用Firefoxへアタッチする。再生に用いる合図だけを切り替え、3収録器、先行音56量子、1秒、保持窓なし、通常の発話入力を固定する。実測したゲート時刻は開始行の受信時刻に200 msを足した値と照合する。Darwin通知の時刻も同じselectorで保存し、ゲートを開いた後に届いた場合も順序を復元できる。機器Writeのホスト時刻から起点を求め、発話の先頭3量子のAudio Client、Audio Server、機器Writeと対象スレッドの状態を同じ要求で照合する。時計で比較できる2組で音声I/Oの余裕の差を判定する。[先行再生の事前登録](../cases/worklet-live-tsp-firefox-stdout-release-200ms.json)・[通知とゲートの実装](../tools/capture_worklet_system_pair.py)・[同時照合](../tools/measure_worklet_tsp_io_trace_instruments.py)

開始行から200.843 msと201.065 msでゲートを開けた。Darwin通知はゲートより1,064.427 msと627.518 ms後に到着した。この条件ではFirefoxのAudio Clientが83行と91行残った。Darwin条件の2試行は対象PIDのAudio Clientが0行だった。4試行の発話WAVと状態は通常再生に一致し、固定上流の11試験が通過した。4試行の先頭発話量子付近にはcubeb予定時刻の飛びがなく、同じ開始条件の音声I/Oとスレッド状態を全窓または局所窓で一意に照合できた試行はなかった。相手の条件に対象PIDの行がないため、登録した2組で余裕を比較する判定は保留した。[実行の環境と入力](../runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-a/manifest.json)・[初版の判定](../runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage/summary.json)

| 先行再生の組 | 発話入口から最初のFirefox Audio Client行まで | I/Oと機器Writeが残った発話開始要求 | 全窓に必要な追加待機の換算範囲 |
| --- | ---: | --- | ---: |
| 1 | +59.348 ms | 12、13ともに欠測 | 238.149〜453.122 ms |
| 2 | +5.330 ms | 13のみ | 185.966〜432.094 ms |

第2組の要求13は、同じ予定ホスト時刻・サンプル位置にAudio Client、Audio Server、機器Writeが各1件あった。要求12は同じ対応が見つからなかった。機器Writeで補正した収録前端を使うと、200 msの先行条件では全窓の一部が収録開始より前にあった。音声I/O各表の前端と末尾を固定して換算した追加待機の共通範囲は238.149〜432.094 ms、開始行からの待機時間に足すと約438〜632 msだった。次はこの範囲の500 msを登録し、前端と末尾を実際に照合する。[要求ごとの照合と追加待機の換算](../runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage-onset-edges/summary.json)・[原データと再解析コマンドの記録](../runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage-onset-edges/manifest.json)

## 確認用07で開始行から500 ms後に再生を許可する

固定上流の `AudioEngine.build()` は指定レートのContextを再開し、Workletモジュールの読込みを待って発声ノードを作る。`ChimeraProcessor.process()` はホストのフレーム要求数を `engine_render()` に渡し、WASMの出力バッファから `f32` PCMを取り出す。Rustの `Engine::render()` は通算出力位置で128フレーム境界を判断し、境界の冒頭でシーケンサーを更新して次の境界まで描く。上流試験は1、77、128、4,096、48,000フレームの要求で同じ通算位置のPCMをビット照合する。今回動かすのは収録側の再生許可の時刻で、入力と描画の手順はこの経路を通す。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

200 msの2試行の実測から、開始行から約438〜632 msの待機で既存の音声I/O収録範囲に全窓が入ると換算した。この範囲にある500 msを登録する。計測用Firefoxへのアタッチ、先行音56量子、48 kHzの256フレーム要求、3収録器、1秒、保持窓なしを固定する。Darwin通知で再生する条件と、開始行を改行まで受信し500 ms後に再生する条件を3組で交互に試す。ゲート受信の実測値は指定から0〜20 ms以内とする。発話入口からFirefoxのAudio Client末尾までの余裕が3組中2組以上で4 msを超えて増え、同時照合が増えるかを調べる。前端で要求を失った場合は、各表の範囲と発話開始の要求12・13を機器Writeで換算した時計で再照合する。[500 ms条件の登録](../cases/worklet-live-tsp-firefox-stdout-release-500ms.json)・[通知による再生許可](../tools/capture_worklet_system_pair.py)・[同時照合の判定](../tools/measure_worklet_tsp_io_trace_instruments.py)

| 組 | 開始行から再生許可までの実測 | 発話入口からAudio Client末尾までの余裕（Darwin） | 同じ余裕（500 ms） | 全計測窓の同時照合（Darwin / 500 ms） |
| --- | ---: | ---: | ---: | --- |
| 1 | 500.879 ms | −138.600 ms | +349.282 ms | 不成立 / 成立 |
| 2 | 500.159 ms | +35.008 ms | +333.525 ms | 不成立 / 成立 |
| 3 | 501.080 ms | Firefoxの行なし | +93.053 ms | 欠測 / 成立 |

500 ms条件の3試行すべてで、計測窓全体のcubeb・Audio Client・Audio Serverを照合できた。発話開始の要求12・13はサーバー予定位置と機器Writeに対応し、各要求の直後の機器周期には対象スレッドの状態区間とIOProcが1件ずつあった。Darwin条件では第2組の発話開始の局所窓だけを同じ方法で照合できた。第3組にFirefoxのAudio Client行がなく、3組が必要な登録済みの判定は保留した。比較できた2組の余裕は487.882 msと298.517 ms増えた。[判定と要求ごとの時刻](../runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-coverage/summary.json)

全6試行で構築位置は先行音の観測起点から7,168フレーム後にあり、発話WAVと発声状態は通常再生と一致した。固定上流の11試験を通過し、上流とのPCMの最大絶対差は1.17×10⁻¹⁰未満だった。生データの機器時計の起点、サーバー予定位置、各機器Write、状態区間を再計算し、解析の対応を確認した。収録と解析の1,928入力、1,674出力をサイズとSHA-256で検証した。出力合計326,056,889バイトはRTL9210B-CGに直接保存した。[収録コマンド、環境、入出力](../runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-a/manifest.json)・[解析コマンドと入出力](../runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-coverage/manifest.json)

発話開始の要求12・13に予定サンプル時刻の飛びはなかった。500 ms条件の要求12のAudio Client区間長は3.600〜3.984 msで、次のサーバー周期開始まで1.345〜1.726 msあった。以前に5.333 msの予算内で飛んだ2件では、同じ区間長が5.126 msと5.257 msで、余裕は207.5 µsと58.5 µsだった。次は収録を500 ms条件にそろえ、発話直前の量子に入る破棄描画だけで処理余裕を動かせるかを調べる。過去の1量子遅延の手順を参照し、破棄描画と最初の発話量子が同じ機器要求に入ることを確かめる。通常再生のPCMと発声状態を固定したまま、最初の発話要求の区間長と次の周期までの余裕を比較する。[要求とスレッド状態の実測](../runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-coverage/summary.json)・[従来の飛びの時刻と処理余裕](#確認用07で次のfirefox-ioが飛んだ周期を照合する)・[発話開始を1量子遅らせた対照](#確認用07の発話開始を1量子ずらして出力を同時採取する)・[準備描画の更新順](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L203)
## 確認用07の最初の機器要求に最後の破棄描画を移す

固定上流の `AudioEngine.build()` はContextを再開し、Workletモジュールを読み込んで発声ノードを作る。`ChimeraProcessor.process()` は出力配列の長さで `engine_render()` を呼び、WASMから得た `f32` を各出力チャンネルへ書く。Rustの `Engine::render()` は通算サンプル位置を128で割った余りから次の制御境界までの幅を求め、その境界でシーケンサーを更新する。上流のホスト要求長の試験は1、77、128、4,096、48,000フレームで同じPCMをビット比較する。今回の独立した破棄描画は調査用で、上流比較は本番ハンドルの発話位置で行う。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト要求長の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

再実装では `renderRealtimeEnglishVoice()` が同じ入力からスコアを作り、調査用の明示指定があると64フレームを1片とする破棄描画を予約する。`FixedVoiceEngine` の破棄用と本番用のハンドルは別で、最初の片でだけ0フレーム呼び出しを1,000回行う。以後は破棄用の累計を64ずつ進め、256に達したら解放する。発話の予約時刻は連続した量子がそろった時点に17量子を足す。両条件の最初の3片は待機量子0・2・4に置き、最後の片は早い条件で量子6、遅い条件で予約時刻の128 Contextフレーム前となる量子16に置く。待機量子はどちらも無音を返す。発話開始後は本番用のPCMと観測値を見て、従来の通常再生と照合する。[発話の公開入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L233)・[発話時刻の予約](../../../../web/prototypes/chimera-research/src/realtime-speech-capture.ts#L29)・[待機量子の処理](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L207)・[別ハンドルの更新と解放](../crates/vocal-wasm/host/fixed-voice.ts#L430)

500 msゲート、48 kHz、先行音56量子、3収録器と同じFirefoxを固定する。先頭3発話量子の配分が両条件で1＋2となり、遅い条件で最後の破棄描画と先頭の発話量子が同じ256フレーム要求に入ると予測する。前回の待機中の32フレーム片は約0.55〜0.80 msかかった。64フレーム片を予定位置に移した組の少なくとも2組で、Audio Client区間が0.4 ms以上延び、区間末尾から次のサーバー周期開始までの余裕が0.4 ms以上縮むことを支持条件とする。欠測を残し、比較可能な組が2組未満なら判定を保留する。周期の予算は256÷48,000秒。予算内または超過で時刻が飛んだ場合は、機器Writeと同じ周期のIOProc、Blocked・Runnable・Runningを照合する。[登録ケース](../cases/worklet-live-tsp-firefox-onset-load-64.json)・[従来の予算内の飛び](#確認用07で次のfirefox-ioが飛んだ周期を照合する)・[500 msの収録範囲](#確認用07で開始行から500-ms後に再生を許可する)

| 組 | 要求12のAudio Client区間（早い配置 → 発話直前） | 次のサーバー周期までの余裕（早い配置 → 発話直前） |
| --- | ---: | ---: |
| 1 | 2.118 → 2.901 ms | 3.202 → 2.444 ms |
| 2 | 2.234 ms → 欠測 | 3.090 ms → 欠測 |
| 3 | 2.180 → 3.042 ms | 3.156 → 2.287 ms |

全6試行で先頭3発話量子は要求12・13に1＋2で入り、最後の破棄描画は早い配置で要求7、発話直前で要求12に入った。最後の片の実測単体は0.840〜0.888 msだった。第1・3組ではAudio Client区間が0.782 msと0.863 ms延び、次のサーバー周期までの余裕は0.759 msと0.870 ms縮んだ。事前登録の2組以上という予測を支持した。第2組の発話直前条件では3つの音声I/O表を取得したものの、機器Writeの時計で換算すると対象FirefoxのAudio Client行は発話入口の127.876 ms前で終わり、比較対象から外れた。欠測を含むため全体の実行判定は不合格とした。[収録と判定](../runs/worklet-live-tsp-firefox-onset-load-64-20261122-a/summary.json)・[初版解析](../runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage/summary.json)・[欠測を機器時計で検算した解析](../runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage-verified/summary.json)

全6試行で発話WAVは通常再生のファイルとバイト一致し、発声状態も一致した。固定上流PCMの最大絶対差は1.17×10⁻¹⁰未満で、固定上流の11試験とViteビルドを通過した。6試行の構築位置は先行音の起点から7,168フレーム後、ゲートは500.331〜501.073 msだった。生データから3組の最後の片が入った要求を検算し、照合できた10周期で機器Write、スレッド状態、IOProcを確認した。収録と2解析の2,255入力・1,644出力のサイズとSHA-256を照合した。出力合計329,017,181バイトをRTL9210B-CGに保存した。[収録の環境とコマンド](../runs/worklet-live-tsp-firefox-onset-load-64-20261122-a/manifest.json)・[初版解析の入出力](../runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage/manifest.json)・[検算で再利用した入力](../runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage-verified/manifest.json)

発話開始の予定時刻の飛びは6試行ともなく、遅い配置でも次の周期まで2.287〜2.444 msあった。以前に予算内で飛んだ事例の余裕は59〜208 µsだった。次は先行する3片を64フレームに固定し、最後の片の描画量だけを変える。64フレームの実測を線形に外挿した224フレームを候補として、まず実測が予算5.333 msの直前に入るか確かめる。[以前の飛びの時刻](#確認用07で次のfirefox-ioが飛んだ周期を照合する)
## 確認用07の発話直前の破棄描画を224フレームに増やす

上流の `AudioEngine.build()` から `ChimeraProcessor.process()`、WASMの `engine_render()`、Rustの `Engine::render()` まで追った。Workletは出力バッファの幅で描画を求め、PCMを取り出す。Rustは現在の出力サンプル位置の128フレーム境界で制御を更新し、次の境界まで描画してから位置を進める。上流試験はバッファ幅1、77、128、4,096、48,000フレームで波形のビット一致を確認する。今回の224フレームは本番Workletの出力幅とは独立した、破棄用ハンドルだけの計算量である。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[バッファ幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

再実装の発話診断で最後の破棄描画の幅を指定できるようにした。待機量子0・2・4で64フレームずつ描画し、破棄用の通算位置192で次の描画を待機量子16に予約する。64フレーム条件は通算256、224フレーム条件は通算416で使い捨てハンドルを解放する。この時点まで本番の発声位置は0で、待機量子は無音を返す。待機量子17で本番の最初の128フレームを描画する。48 kHz・256フレーム要求の場合の機器周期は約5.333 ms。[実時間発話の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L233)・[待機量子に描画を予約する処理](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L207)・[破棄用ハンドルの累計と解放](../crates/vocal-wasm/host/fixed-voice.ts#L434)

前回の最後の64フレーム片は約0.84〜0.89 msで、同じ片と最初の発話量子を含む要求12は約2.90〜3.04 msだった。追加160フレームに1フレーム当たりの計時を当てはめると、約2.10〜2.22 ms増えて5.00〜5.26 msに達する。WASMの区間ごとの計算量が同じと仮定した予測である。3組中2組以上でAudio Client区間が1 ms以上伸び、次のサーバー周期までの余裕が1 ms以上縮むと事前登録した。5.333 msの予算内で次の周期までの余裕が0〜0.5 msだった件と、サンプル時刻が飛んだ件を記録する。両条件で先頭の3発話量子を要求12・13に1＋2で配分し、発話WAV・状態、500 msゲート、機器Writeを基準にした時計、要求12・13の状態窓を照合する。[224フレームの登録ケース](../cases/worklet-live-tsp-firefox-onset-load-224.json)・[64フレームの生データと結果](../runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage-verified/summary.json)

| 組 | 要求12のAudio Client区間（64 → 224フレーム） | 次のサーバー周期までの余裕（64 → 224フレーム） | 224フレーム条件の予定サンプル時刻 |
| --- | ---: | ---: | --- |
| 1 | 2.842 → 5.065 ms | 2.484 → 0.523 ms | 256フレームの飛びを補足窓で照合 |
| 2 | 欠測 → 4.681 ms | 欠測 → 0.628 ms | 連続 |
| 3 | 2.947 → 5.018 ms | 2.379 → 0.643 ms | 連続 |

最後の片は64フレーム条件で0.830〜0.840 ms、224フレーム条件で2.508〜2.753 msかかった。登録済みの窓は全窓または局所の要求10〜16で判定する。第1組の224フレーム条件では要求16の次を確認するための要求17が必要だったが、記録はその入口の2.139 ms前に終わった。第2組の64フレーム条件では要求12の入口より138.498 ms前に記録が終わった。登録済みの窓で比較できたのは第3組だけで、主判定は保留した。第1組を要求10〜15に限った補足窓では要求12・13を照合でき、2組ともAudio Client区間が2.071〜2.224 ms延び、次周期までの余裕が1.736〜1.961 ms縮んだ。0〜0.5 msの条件を満たした試行はなかった。[主判定](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage/summary.json)・[同じ生データによる補足解析](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/summary.json)

第1組の224フレーム条件で、飛ぶ直前のcubebは5.054 ms、Audio Clientは5.065 msで、どちらも5.333 msの予算内だった。Audio Clientの終了から523.459 µs後にサーバーは次周期のClient Startを記録し、その14.291 µs後に同じ出力ストリームのWriteが始まった。その周期の実測長は5.081416 msで、予定間隔5.333 msに対する許容差0.10 msを超えた。予定ホスト時刻と出力サンプル位置は一致し、状態の隙間と重複は0だった。対象FirefoxのI/Oスレッドはこの周期全体でBlockedで、IOProcは0件だった。次のサーバー周期には開始3.417 µs後にRunnable、3.750 µs後にRunning、周期開始25.209 µs後にIOProcが始まった。OSが通知を送った時刻と、その間に物理出力へ渡った波形は未観測である。[飛んだ周期と復帰を含む補足の実測](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/summary.json)・[Thread Stateの原データ](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/artifacts/1-split-onset-load-224/thread-state.xml)・[IOProcの原データ](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/artifacts/1-split-onset-load-224/audio-hal-client-io-cycle-ioproc.xml)

全6試行で最後の片は要求12にあり、発話WAVは通常再生とバイト一致し、発声状態も一致した。固定上流との差は最大1.17×10⁻¹⁰未満で、固定上流11試験とViteビルドが通過した。生のcubeb予定位置、Audio Client末尾、サーバーの予定位置、同じ機器Write、10周期のスレッド状態を独立に照合した。収録と2解析の2,486入力・1,630出力をサイズとSHA-256で検証し、350,241,550バイトの出力をRTL9210B-CGに保存した。次は224フレーム条件のままFirefoxのプロセスタップを併用する採取経路を確認し、予算内で飛んだ周期の前後に出たPCMを機器Writeへ対応させる。[収録と再現コマンド](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-a/manifest.json)・[登録窓の入出力](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage/manifest.json)・[補足窓の入出力](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/manifest.json)
## 確認用07の224フレーム条件でプロセスタップを併用する

固定上流の `AudioEngine.build()` はAudioContextを再開してWorkletを読み込み、`ChimeraProcessor.process()` が出力幅でWASMの `engine_render()` を呼ぶ。Rustは通算出力位置の128フレーム境界で制御を更新する。上流試験はホスト幅を変えてPCMのビット一致を確認する。今回は先頭発話の機器要求と同居する224フレームの破棄描画を固定し、本番用ハンドルから出るPCMと発声状態は上流および通常の再生と照合する。調査対象はWorkletから先の機器I/Oと、同じFirefox親PIDのCore Audioプロセスタップである。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[バッファ幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

計測ブラウザの準備通知を受けてタップを起動し、採取アプリの `AudioDeviceStart` が戻ってから同じ親PIDのxctrace開始を許可する。xctraceの開始行から500 ms後に発話を解放し、その後は従来の確認用07を再生する。初回の6試行では、再生前のFirefox親PIDをCore Audioの音声プロセスへ引く段でOSStatus 560947818が返り、システム収録を始められなかった。そこで計測ブラウザだけに無音の48 kHz Contextを先に開く処理を加え、出力サンプルが進んだことを確認してから準備通知を送る。タップとシステムの準備後に無音Contextを閉じ、通常の発話操作を始める。[初回の登録](../cases/worklet-live-tsp-firefox-onset-load-224-tap.json)・[初回の入出力](../runs/worklet-live-tsp-firefox-onset-load-224-tap-20261122-a/manifest.json)・[修正版](../cases/worklet-live-tsp-firefox-onset-load-224-tap-prime.json)・[収録ゲート](../tools/measure_worklet_live_song_process_tap.py#L287)

先行音は同じ波形を左右逆相で加え、差分によって中央の発話を除いて位置を合わせる。6試行中3試行以上で要求12・13を機器Write、スレッド状態、PCMの同じ時点に照合できると予測した。局所窓は要求10〜15、両端の相関は従来の計測設定を使う。時刻が飛んだ場合は、飛びの直前の要求の位置へ無音を挿入するモデルと、次の予定位置に挿入するモデルを比較する。候補の残差は相関窓から外した最大512フレームの両脇で計算し、残差0.025以下かつ他方との差0.03以上を採用条件とする。機器Writeは予定位置とホスト時計を用いてタップ側のサンプル区間に対応させる。[タップの先行音と局所比較](../tools/measure_worklet_tsp_device_tap.py#L171)・[事前登録](../cases/worklet-live-tsp-firefox-onset-load-224-tap-prime.json)

無音Contextを先に開いた6試行すべてで、Firefox親PIDのタップを準備してからxctraceを開始できた。タップ準備から開始行までは約1.463〜1.729秒、開始行からゲートまでは500.179〜500.902 msだった。全試行で先行音の起点から7,168フレーム後に発声器を構築し、224フレームの最後の描画を最初の発話量子と同じ要求12に対応付けた。5試行では音声I/Oの全窓、第5試行では要求10〜15の局所窓で、要求12・13の機器Write、タップPCM、スレッド状態を照合した。開始前の準備に失敗した初回と、局所照合前の収録判定は保存した。[初回](../runs/worklet-live-tsp-firefox-onset-load-224-tap-20261122-a/summary.json)・[無音Contextを開いた収録](../runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-a/summary.json)・[周期を照合した判定](../runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/summary.json)

生のステレオ差分を用いて先行音の両端1,024サンプルを検算し、相関係数は全12窓で小数点以下7桁に丸めて1.0000000だった。タップとcubebの両端を対応させるホスト時刻差は26.117〜26.138 ms、同じ試行の両端間での変動は最大0.003 msだった。全6試行でタップの照合区間にフレーム増減と完全無音の区間はなく、cubebの発話開始に予定時刻の飛びはなかった。要求12のcubeb処理時間は4.560〜4.852 msだった。既存のタップ付き収録の飛び2件には今回の機器Writeとの照合処理を適用し、256フレームの対応窓と無音フレーム数を従来の結果から再現した。予算内で飛んだ場合のPCMは引き続き未観測。[計測と照合結果](../runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/summary.json)・[既存のタップ付きの飛び](../runs/worklet-live-tsp-firefox-device-tap-20261122-repeat/summary.json)

全6試行で発話WAVと発声状態は通常再生に一致し、固定上流PCMの最大絶対差は1.17×10⁻¹⁰未満だった。固定上流11試験とViteビルドを通過した。初回・修正版・解析の2,111入力と1,610出力をサイズとSHA-256で検証し、330,786,804バイトをRTL9210B-CGに保存した。次は今回の同時収録の手順を維持し、最後の描画だけ224から256フレームへ増やして、発話開始の要求を5.333 msの予算に近づける。[修正版の環境とコマンド](../runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-a/manifest.json)・[解析の入出力](../runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/manifest.json)
## 確認用07のタップ付き条件で最後の破棄描画を256フレームに増やす

固定上流の `AudioEngine.build()` はAudioContextを再開してWorkletを読み込み、`ChimeraProcessor.process()` が出力幅でWASMの `engine_render()` を呼ぶ。Rustの `Engine::render()` は通算出力位置の128フレーム境界で制御を更新し、次の境界までのPCMを作る。上流試験はホスト幅1、77、128、4,096、48,000フレームで波形のビット一致を検証する。今回の変更先は本番とは別のWASMハンドルで、発話直前の破棄用 `vocal_render()` の1回の幅である。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

実時間発話の診断で、待機量子0・2・4にある64フレーム片と最初の1,000回の0フレーム呼び出しを維持する。破棄用ハンドルの通算位置192から、量子16の最後の片だけを224から256フレームへ変え、通算448で解放する。量子16は無音を出し、量子17は本番ハンドルの発話をサンプル0から出す。先行音の開始から56量子で通常の発声器を構築し、最初の発話量子と最後の準備片が同じ機器要求12に入ることを測る。タップ準備用の無音Context、500 msゲート、48 kHz・256フレームの機器要求を維持する。[発話の診断入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L243)・[待機量子の予約](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L208)・[破棄用ハンドルに描画する処理](../crates/vocal-wasm/host/fixed-voice.ts#L434)・[事前登録](../cases/worklet-live-tsp-firefox-onset-load-256-tap-prime.json)

前回のタップ付き224フレームの最後の片には2.527〜2.676 msかかり、要求12のcubeb処理は4.560〜4.852 msだった。追加の32フレームに0.36〜0.38 msかかると見積もり、5.333 msの予算まで0.5 ms以内に入る試行が1件以上と予測した。飛びが観測された場合、先行音の両端で時計をそろえ、飛びの直前の要求の先頭と次の予定位置にゼロを挿入する2つのモデルを比較する。機器Writeのサンプル位置に対応するタップPCMが無音かを調べ、同じ周期のFirefoxのスレッド状態とIOProcも確認する。[前回のタップ付き224フレームの結果](../runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/summary.json)・[タップの局所比較](../tools/measure_worklet_tsp_device_tap.py#L171)

| 項目 | 224フレーム、タップ付き（先行6試行） | 256フレーム、タップ付き（今回6試行） |
| --- | ---: | ---: |
| 最後の破棄描画の所要時間 | 2.527〜2.676 ms | 2.726〜2.781 ms |
| 同中央値 | 2.591 ms | 2.752 ms |
| 発話開始の要求12のcubeb処理時間 | 4.560〜4.852 ms | 4.723〜5.015 ms |
| 同中央値 | 4.748 ms | 4.891 ms |
| 5.333 msの予算まで0.5 ms以内 | 1試行 | 5試行 |

最後の片は全6試行で予定どおり要求12に入り、構築位置は先行音開始から7,168フレームだった。要求12の予算までの余裕は0.318〜0.610 ms、発話開始の予定サンプル時刻の飛びは0件だった。224フレームの先行実行と比べた破棄描画中央値の増分は0.161 msで、単純な外挿で見積もった0.36〜0.38 msより小さかった。タップとcubebの生PCMから先行音の両端を照合すると、1,024フレームずつの相関係数は12窓すべてで7桁に丸めて1.0000000だった。照合区間にタップPCMの増減や完全無音の区間はなく、要求12・13の後の12周期にIOProcが各1件記録された。[収録時の計時](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-a/summary.json)・[音声I/Oとタップの照合](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/summary.json)

同じサーバースレッドを要求した登録判定では、全窓を照合した6試行中5試行で、発話開始の機器Write、タップPCM、状態を結合できた。第2試行の要求12・13はともにサーバースレッド5264947でエンジン101・ストリーム0へ書いていた。次の要求14では同じ範囲のWriteがスレッド5256162にあった。サンプル位置285628564と256フレームの幅は一致し、スレッド5256162のAudio Server行の予定ホスト時刻は5264947の行と2.167 µs差、Writeは5256162の行の終了から17.833 µs後だった。ストリームの対応を補足で確認し、登録判定の欠測は保持した。2つのスレッドでその処理を分けた理由は観測していない。[登録判定](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/summary.json)・[補足の初版](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage-write-threads/summary.json)・[別スレッドのWriteと予定時刻の検算](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage-write-threads-verified/summary.json)

全6試行で発話WAVと発声状態は通常再生に一致した。固定上流PCMの最大絶対差は1.17×10⁻¹⁰未満で、固定上流11試験とViteビルドは通過した。224フレームのタップ付き解析は保存PCMとI/O表から再計算し、要約が一致した。今回の収録と3解析の2,058入力・1,564出力はサイズとSHA-256で検証し、323,321,988バイトをRTL9210B-CGに保存した。次は同じ同時収録の順序で最後の破棄描画を320フレームに増やす。今回実測した要求12の中央値の差0.144 msを32フレーム当たりの目安にすると、320フレームの中央値は約5.18 msとなる。[収録コマンドと環境](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-a/manifest.json)・[登録窓の解析](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/manifest.json)・[補足窓の検算](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage-write-threads-verified/manifest.json)
## 確認用07で最後の破棄描画を320フレームに増やす

固定上流の `AudioEngine.build()` でAudioContextを再開してWorkletを接続し、`ChimeraProcessor.process()` からWASMの `engine_render()` へ出力配列の幅を渡す。Rustは128フレームごとに制御を更新し、通算位置を進める。1、77、128、4,096、48,000フレームのホスト幅を使う上流試験でPCMのビット一致を確かめる。研究版の追加負荷は通常の発声用と別のハンドルに対する `vocal_render()` で、320は1呼び出しの上限4,096フレーム内にある。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

待機量子0・2・4に64フレームずつ、同16に320フレームを描く。破棄用ハンドルの通算位置512で解放してから、量子17で本番の最初の128フレームを描く。先行音開始から56量子の構築位置、無音Contextによるプロセスタップの準備、500 msゲート、48 kHz・256フレームの入出力を維持する。既存実測から要求12のcubeb処理の中央値を約5.18 msと外挿し、5.1 ms以上と事前登録した。欠落周期が現れた場合は、予定サンプル位置と機器Writeをスレッド状態へ対応させ、タップPCMでは直前の要求の先頭と次の予定位置に無音を挿入した2モデルを比較する。[診断の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L243)・[待機量子の予約](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L208)・[事前登録](../cases/worklet-live-tsp-firefox-onset-load-320-tap-prime.json)・[256フレームの実測](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/summary.json)

全6試行で最後の描画は最初の発話量子とともに要求12へ入った。最後の片に3.370〜3.400 ms、要求12のcubeb処理に5.441〜5.705 msを要した。処理時間の中央値は5.517 msで、外挿した5.18 msを上回った。全6件で5.333 msの予算を0.108〜0.372 ms超えた後、予定サンプル時刻が256フレーム飛んだ。[収録時の計時](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-a/summary.json)

全6試行のタップPCMはcubebより256フレーム長かった。飛びの直前の要求位置に無音を挿入するモデルの相対RMS残差は0.006573、次の予定位置に挿入するモデルは0.595626で、全6試行で直前の要求位置が選ばれた。直前の要求側の256フレームには左右とも完全にゼロの区間が162フレームあった。発話開始の音声I/Oを照合できた5試行では、飛んだ周期の機器Writeに対応する256フレームには完全無音がなく、先行音が続いていた。第3試行ではFirefoxのAudio Clientの記録が発話の85.143 ms前に終わっていた。同試行のPCMはcubebとタップから単独で再解析し、機器Writeとスレッド状態は欠測として保持した。[登録窓の結果](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage/summary.json)・[PCMを単独で照合した補足](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json)

機器Writeを照合できた5試行では、飛ぶ直前のAudio Client区間もすべて名目の予算5.333 msを超えた。実測の区間終了は次のサーバー周期開始より39.291〜280.417 µs先行しており、飛んだ周期の実測4.950〜5.077 msを通じてFirefoxのI/OスレッドはBlockedのままで、IOProcは0件だった。後続の発話要求13の後の周期にはIOProcが各1件あった。名目の予算と、同じ試行で実測したサーバー周期までの余裕はそれぞれ保持する。予算内で飛んだ以前の例と同じく、今回もAudio Clientの終了時刻だけでは次のI/Oが飛んだ理由を確定できない。[機器時計と状態窓](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json)・[224フレームの予算内の例](../runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/summary.json)

全6試行で通常再生のWAV・発声状態に一致し、固定上流とのPCM最大絶対差は1.17×10⁻¹⁰未満だった。Viteビルドと固定上流11試験を通過した。機器Write、スレッド状態、ゼロ挿入2モデルの残差は生データから独立に計算した。256フレームの結果を再計算して保存済みの要約と一致し、収録と2解析の2,146入力・1,571出力をサイズとSHA-256で検証した。出力321,613,795バイトはRTL9210B-CGに保存した。次は同じタップの順序のまま288フレームを試す。256と320の実測中央値からその中点を約5.204 msと見積もり、予算内の飛びとPCMを同時に採れるか確認する。[収録の入出力](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-a/manifest.json)・[登録の解析](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage/manifest.json)・[PCMの補足解析](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/manifest.json)
## 確認用07で最後の破棄描画を288フレームにする

固定上流の `AudioEngine.build()` はAudioContextを再開してWorkletを登録する。`ChimeraProcessor.process()` がホストの配列幅を `engine_render()` へ渡し、返ったPCMを各チャンネルへ書く。Rustでは通算出力位置の128フレーム境界で制御を更新し、次の境界まで描画する。上流試験は1、77、128、4,096、48,000フレームの要求でPCMのビット一致を照合する。今回の288フレームは本番の出力幅と独立した、診断時だけ使う破棄用ハンドルの1呼び出しの幅である。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

最初の3片は待機量子0・2・4に64フレームずつ置く。累計192で最後の片を量子16まで待ち、288フレーム描いて累計480で破棄用ハンドルを解放する。次の量子17で本番ハンドルの発話をサンプル0から出す。無音Context、500 msゲート、先行音56量子、48 kHzの256フレーム要求を固定し、先頭の発話量子と最後の片が同じ機器要求に入ったことを確認する。[診断の入口](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L243)・[最後の片の時刻](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L208)・[破棄用の描画と解放](../crates/vocal-wasm/host/fixed-voice.ts#L434)

過去のタップ付き実行の中央値4.891 msと5.517 msから、中点を5.204 msと見積もった。6試行中1試行以上で要求12のcubeb処理が予算5.333 ms以内で残り0.25 ms以内と登録した。予算内の飛びはcubebとAudio Clientの両方の処理時間を使って判定する。飛びがあれば、直前の要求の先頭と次の予定位置に無音を挿入した2モデルを比べ、機器Writeに対応するタップPCMと各周期のスレッド状態を照合する。[事前登録](../cases/worklet-live-tsp-firefox-onset-load-288-tap-prime.json)・[256フレームの実測](../runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/summary.json)・[320フレームの実測](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json)

全6試行で最後の片の通算位置480を要求12に照合した。描画時間は3.191〜3.394 ms、要求12のcubeb時間は5.213〜5.577 msで中央値は5.434 msだった。予算まで0.25 ms以内の試行は2件で、6試行すべてで要求12の後に予定サンプル時刻が256フレーム飛んだ。2件はcubebとAudio Clientがともに予算内で、4件はともに予算を超えた。[収録時の計時](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-a/summary.json)・[音声I/Oとの照合](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-coverage/summary.json)

| 予算内で飛んだ試行 | cubeb | Audio Client | Audio Client終了から次のサーバー開始まで | IOProcがなかった周期のBlocked |
| --- | ---: | ---: | ---: | ---: |
| 2 | 5.213 ms | 5.220 ms | 113.125 µs | 5.334709 ms |
| 5 | 5.258 ms | 5.266 ms | 451.667 µs | 4.956000 ms |

予算内の2件でも、飛んだ周期のサーバー処理と機器Writeは予定サンプル位置で連続した。FirefoxのI/Oスレッドは飛んだ周期の全区間でBlockedで、IOProcは0件だった。タップには256フレームの増分があった。2件とも直前側・次の予定位置側に完全にゼロのフレームは0で、事前登録の無音モデルの相対RMS残差は両位置とも約0.40546だった。第2試行には発話前に別の512フレームの飛びもあり、その増分を考慮して発話開始の窓を合わせた。[登録判定と機器Write](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-coverage/summary.json)

事後比較では、進むはずだった256フレームを1回余分に並べるモデル、隣の要求の波形を挿入するモデル、無音モデルを生PCMに当てはめた。予算内の2件では当該要求の反復モデルの相対RMS残差が0.008497で最小となった。先行音の近い波形が256フレームずつ2回続き、2回目は飛んだ周期の機器Writeに対応した。2区間の左右チャンネルをcubebの同じ256フレームと直接比較した残差は約0.0148だった。同相成分のRMSは両区間とも0だった。予算超過の4件では無音モデルが全件で選ばれ、直前側に162フレームの完全無音があった。どちらの条件でも飛んだ周期の機器Writeに対応するタップ区間に先行音があった。OSの通知経路、同相の発話成分、物理出力への伝わり方は未観測。[事後の無音・反復モデル比較](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-repetition/summary.json)・[再計算用のツール](../tools/measure_worklet_tsp_tap_gap_repetition.py)

通常再生の発話WAV・状態は全6試行で一致し、固定上流とのPCM最大絶対差は1.17×10⁻¹⁰未満だった。Viteビルドと固定上流11試験を通過した。生データで機器Write、スレッド状態、先行音の反復位置と両モデルの残差を独立に確認した。収録と2解析の1,807入力・1,571出力をサイズとSHA-256で検証し、342,635,895バイトをRTL9210B-CGへ保存した。次は発話開始の同じ要求に、先行音の逆相成分を維持したまま非ゼロの同相成分を加える対照を用意する。予算内で飛んだ周期について両成分を個別に照合する。[収録](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-a/manifest.json)・[登録の解析](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-coverage/manifest.json)・[事後比較の再現コマンド](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-repetition/manifest.json)
## 確認用07に同相の試験信号を加えて反復を調べる

上流の `AudioEngine.build()` はAudioContextを再開して発声Workletを登録する。`ChimeraProcessor.process()` は出力幅を `engine_render()` へ渡し、Rustの `Engine::render()` が通算位置の128フレーム境界で制御を更新した後、WASMのPCMを取り出す。上流試験は1、77、128、4,096、48,000フレームの要求でもPCMがビット一致することを確かめる。今回の試験信号は研究版の計測ページでだけ同じAudioContextへ加算し、発声用ハンドルの状態と書き出しWAVの比較は従来の入口で行う。[上流のContext](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

既存の逆相信号 `d` と、独立したシードで作る同相信号 `c` を先に作る。どちらも16フレームを1チップとする滑らかな符号系列で、`c` の最大振幅は1/512とした。計測用Workletは左へ `c+d`、右へ `c−d` を出し、内部の記録には元の `d` を残す。同じチャンネルへ入る本番の発話を `s` とすると、収録から `(L−R)/2` で `d`、`(L+R)/2` で `c+s` が得られる。発話開始の比較区間の `c+s` は登録した `c` と照合し、別の発話成分が重なった場合は残差に記録する。[系列を作る処理](../../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs#L1)・[左右に加えるWorklet](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js#L13)・[事前登録](../cases/worklet-live-tsp-firefox-onset-load-288-tap-prime-common.json)

発話前の無音Context、500 msゲート、先行音56量子、288フレームの最後の破棄描画、48 kHz・256フレームの機器要求を固定する。両処理時間が5.333 msの予算内で予定時刻が飛んだ事例では、逆相と同相の両成分で、当該要求の256フレームを反復するモデルが選ばれると予測した。飛びの前後512フレームを含む窓の相対RMS残差を0.025以下、次点との差を0.03以上とし、2回目のPCM区間を機器Writeに照合する。予算超過の事例と連続した要求は対照として記録する。[反復モデルの比較](../tools/measure_worklet_tsp_tap_gap_repetition.py#L23)・[前回の同相成分が0だった試行](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-repetition/summary.json)

全6試行で要求12の後に予定サンプル時刻が256フレーム飛び、その周期にIOProcはなかった。登録したグラフ位置2,048〜12,544フレームの先頭1,024フレームでは、第1・第4試行のタップとの対応を一意に決められなかった。元の判定を不合格として残した。登録窓で照合できた第5試行では、両成分の反復が見えた。補足では第1・第4試行の開始位置だけを3,072フレーム後ろへ移し、グラフ位置5,120〜12,544でcubebとタップの両端を合わせ直した。発話開始の比較点と判定基準は事前登録と同じで、補足後は全6試行で波形を機器Writeに照合できた。[登録窓の判定](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-coverage/summary.json)・[登録窓でのモデル比較](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition/summary.json)・[補足窓の判定](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition-trim/summary.json)

| 試行 | cubeb | Audio Client | Audio Clientの終了から次のAudio Serverの開始まで | 両成分の判定 |
| --- | ---: | ---: | ---: | --- |
| 1 | 5.252333 ms | 5.261291 ms | 310.625 µs | 無音挿入 |
| 2 | 5.588708 ms | 5.594083 ms | −254.125 µs | 無音挿入 |
| 3 | 5.462625 ms | 5.470125 ms | 250.083 µs | 無音挿入 |
| 4 | 5.336167 ms | 5.346625 ms | 344.500 µs | 256フレームの反復 |
| 5 | 5.314875 ms | 5.321292 ms | 357.791 µs | 256フレームの反復 |
| 6 | 5.616833 ms | 5.625708 ms | −299.250 µs | 無音挿入 |

反復した第4・第5試行では、逆相成分の相対RMS残差が0.008497、同相成分が0.0000314だった。cubebの左右平均から得た同じ256フレームをタップの各区間と直接比べても、相対RMS残差は約3×10⁻⁵だった。2回目の区間は飛んだ周期の機器Writeに対応した。無音挿入は両成分で直前の要求の先頭が選ばれ、残差は逆相が0.006573、同相が0.006521だった。予算内だった第1・第5試行で異なる結果が出たため、予算内の全事例で反復するという予測は支持されなかった。名目予算を超えた第4試行でも反復した。[処理時間の記録](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-a/summary.json)・[成分別の残差と機器Write](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition-trim/summary.json)

飛んだ周期の全区間でFirefoxのI/OスレッドがBlockedだったのは第1・第3・第4・第5試行。第2・第6試行ではRunningとRunnableも記録され、直前のAudio Clientが次のAudio Server開始後まで続いた。先行の288フレーム条件では次の周期が113.125 µs後に始まった試行でも反復しており、今回の結果と合わせると、Audio Client終了から次の周期開始までの単一の時間差だけで波形を分類するのは難しい。次は保存済みの288・320フレーム条件も含め、予定ホスト時刻、サーバーの実測開始、機器Writeの時刻を同じ相対座標で比べる。OS通知、発話成分が重なる区間、機器の物理出力の挙動は未観測。[同相を加える前の288フレーム](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-repetition/summary.json)・[320フレームの機器Write](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json)

全6試行で通常再生の発話WAVと発声状態が一致し、固定上流PCMの最大絶対差は1.17×10⁻¹⁰未満だった。Viteビルドと固定上流11試験を通過した。別計算で同相信号の符号系列を生成してcubeb生PCMを検証し、生のタップPCMから両モデルの残差、反復位置と機器Writeの対応を再計算した。収録と3解析の1,863入力・1,580出力をサイズとSHA-256で検証し、326,617,043バイトの出力をRTL9210B-CGへ保存した。[収録コマンドと環境](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-a/manifest.json)・[登録窓の解析](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-coverage/manifest.json)・[反復比較](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition/manifest.json)・[補足解析](../runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition-trim/manifest.json)

## 確認用07で予定時刻と機器Writeを三つの収録条件で比べる

固定上流の `AudioEngine.build()` が出力2チャネルのWorkletを作り、`ChimeraProcessor.process()` が1チャネル分のフレーム数をWASMの `engine_render()` へ渡した後、同じPCMを残りのチャネルに複製する。Rustでは通算位置を128フレームで割った余りに従って制御更新と合成を行う。上流試験は、128フレームを基準に1・77・4,096・48,000フレームで出力がビット一致することを確認する。今回はこの描画経路より後ろを観測し、保存したcubebの要求、Audio Client、Audio Server、機器Writeの順に対応させる。実時間の処理順は上流試験の対象外にある。[上流Context](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

発話開始の要求12から次に記録された要求までを使う。cubebとAudio Serverの予定サンプル番号、ホストの予定時刻を対応させ、欠落周期のWriteは256フレーム幅・同じサンプル番号・前後で共通するエンジンとストリームで特定する。出力サンプル位置はフレーム、traceの開始と持続時間はns、Core Audioのホスト時刻はMach tick。機器Writeの `current-host-time` を時刻に換算してtraceの実測開始を引き、三つの連続Writeの中央値でtrace時刻の原点を求める。原点の幅が25 µsを超える場合は予定時刻との比較を欠測とする。各時点から欠落周期の予定ホスト時刻を引き、cubeb復帰、Audio Client終了、Audio Serverの実測開始、機器Write開始を同じ軸に並べる。[時刻の読取り](../tools/measure_worklet_tsp_device_io.py#L161)・[サーバーとWriteの照合](../tools/measure_worklet_tsp_io_deadline.py#L60)

先行音の同相なし288フレーム、同相あり288フレーム、320フレームの各6試行を使う。PCMの分類は保存した無音・反復モデルを引き継ぎ、登録窓と補足窓の判定を保存する。Audio Client終了から欠落周期の機器Writeまでの時間を主指標とし、反復全件の値が無音挿入全件より大きければ既知の試行で分離したと判定する。両波形のある条件ごと、および全条件を対象に比較する。終点をAudio Server実測開始と予定ホスト時刻に替えた場合も確認する。照合不能の行も残し、特に320フレーム第3試行はPCMに限る。新規収録を要さず、元の大きなWAVやトレースの複製を作らない。[事前登録](../cases/worklet-live-tsp-firefox-onset-gap-write-timing.json)

予定時刻ではcubebの要求とAudio Serverの候補を合わせ、各表のサンプル番号は同じ表の中で前後の差を使った。cubebのローカルなサンプル番号は機器の絶対サンプル番号と異なっていた。欠落したWriteのサンプル番号はAudio Serverの行と一致した。17試行の機器Writeから求めた時計原点の幅は83〜250 ns。Writeは記録上の出力予定時刻より6.462〜6.861 ms早かった。この予定時刻は相対座標の原点に使い、コールバックの締切は別途実測する必要がある。[比較結果](../runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/summary.json)・[試行ごとの時刻表](../runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/artifacts/timing.csv)

| Audio Client終了からの終点 | 反復4件 | 無音挿入13件 | 反復の最小値 − 無音の最大値 |
| --- | ---: | ---: | ---: |
| 機器Writeの開始 | 121.459〜460.917 µs | 12.167〜319.084 µs | −197.625 µs |
| Audio Serverの実測開始 | 113.125〜451.667 µs | −299.250〜310.625 µs | −197.500 µs |
| 出力の予定ホスト時刻 | 6,848.583〜6,982.251 µs | 6,573.250〜6,919.542 µs | −70.959 µs |

全条件を合わせると3指標とも両群の範囲が重なり、予測は支持されなかった。主指標は同相あり288フレーム条件の中では最小35.749 µsの差で分かれ、同相なし288フレーム条件では−185.208 µsで重なった。320フレームは6件とも無音挿入で、第3試行は発話前にAudio Clientの記録が終わり時刻を照合できなかった。時刻が取れた17件では全件でClient終了後に機器Writeが始まった。同相ありの第2・第6試行では、Audio ServerはClient終了の254.125 µs、299.250 µs前に始まったが、WriteはClient終了の12.167 µs、15.208 µs後だった。いずれも無音挿入だった。他の15件では欠落周期中ずっとFirefoxのI/OスレッドがBlockedで、反復も無音挿入も生じた。時刻を結合できた全17件の欠落周期のIOProcは0件だった。[第3試行のPCMと欠測](../runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json)・[指標別の判定](../runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/summary.json)

再解析CLIは既存の結合関数と保存済みのPCM判定を使い、条件ごとに元の収録ケースとFirefoxビルドを照合する。別計算ではcubebのCSVと3種類のトレースXMLを直接読み、1 tickを125/3 nsとして、欠落周期の実測時点を1 ns以内で再現した。153入力と2出力のサイズ・SHA-256を検証し、20,263バイトの結果をRTL9210B-CGへ保存した。次は44.1 kHzのヘッドフォン条件を調べる。既存の48 kHz Contextでは278・279フレーム要求が混在したため、まず44.1 kHzのContextと機器の組でタップの校正と実際の要求幅を確かめる。[解析CLI](../tools/measure_worklet_tsp_gap_write_timing.py)・[実行コマンドと環境](../runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/manifest.json)・[先行の44.1 kHz機器の実測](#確認用07を共有contextで機器出力バッファまで照合する)

研究ワークスペースで次のコマンドを実行した。同じ入力で再解析し、要約とCSVが一致することも確認した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_gap_write_timing.py worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a
```

## 44.1 kHzのヘッドフォンでプロセスタップを校正する

固定上流の `AudioEngine.build(rate)` はHzで指定したレートをAudioContextへ渡し、`ChimeraProcessor.process()` が出力配列の幅をWASMの `engine_render()` に渡す。Rustの `Engine::render()` は通算サンプル位置の128フレーム境界で制御を更新し、単精度PCMを返す。ホスト幅1・77・128・4,096・48,000フレームでPCMが一致する上流試験と、研究版の44.1 kHz固定発声の検証を確認した。今回の校正では、既知の信号を同じ出力構成の計測用Workletへ通す。[上流Context](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[44.1 kHz固定発声](../runs/worklet-rate-44100-20261120-d/summary.json)

各機器の公称レートはCore AudioからHzで取得し、バッファの幅をフレームで読む。タップはステレオFloat32を事前確保した配列に蓄積し、コールバックごとに開始フレーム、幅、サンプル時刻、Mach時刻を付ける。ホスト時刻の差にMachの変換比を掛け、`フレーム数 ÷ 44,100` 秒と比較する。Workletは128フレームを予測し、機器とタップの幅は256フレームを予測する。先行音は48 kHz実行と同じ16フレーム間隔の逆相系列とし、連続16窓で元の信号に照合する。[事前登録](../cases/safari-process-tap-smooth-marker-44100.json)・[48 kHzの校正結果](../runs/safari-process-tap-smooth-marker-20261122-repeat/summary.json)・[タップのコールバック](../tools/chimera_process_tap.swift)

| 観測 | 初回 | 再実行 |
| --- | ---: | ---: |
| Context・機器の公称レート・タップのレート | 44,100 Hz | 44,100 Hz |
| Workletの1量子 | 128フレーム | 128フレーム |
| 機器のバッファとタップの1ブロック | 512フレーム | 512フレーム |
| タップ内のブロック数 | 85 | 84 |
| 既知の信号を連続して照合した長さ | 40,960フレーム | 40,960フレーム |
| 1,024フレーム窓の最小相関 | 0.999638 | 0.998779 |
| 1,024フレーム窓での最大相対RMS残差 | 0.001237 | 0.001266 |

Core Audioの出力機器を調べる小さなSwift CLIを追加した。登録済みUIDを持つヘッドフォンが44.1 kHzで接続されていることを確認し、校正中だけ既定の出力を切り替えた。Safariが再生し、タップの開始通知が届いた時点で公称レートとバッファ幅を再度取得した。両試行で元の内蔵スピーカーへ戻ったことを機器の設定を別途読み取って確認した。[出力機器の取得と選択](../tools/chimera_coreaudio_output_device.swift)・[校正時の出力復元](../tools/measure_safari_process_tap_calibration.py#L125)・[初回の機器記録](../runs/safari-process-tap-smooth-marker-44100-20261122-a/artifacts/output-device.json)・[再実行の機器記録](../runs/safari-process-tap-smooth-marker-44100-20261122-repeat/artifacts/output-device.json)

タップは予測した256フレームより大きく、両試行で512フレームにそろった。512 ÷ 44,100 ≈ 11.610 msで、記録したホスト時刻の間隔と理論値の絶対差の中央値は両回19.0 ns、最大22.7 nsだった。タップのサンプル時刻は毎回512フレーム進み、各試行で40窓が連続した。独立に生成した信号を使うと、40,960フレーム全体の単一位相・ゲインでの相対RMS残差は0.009498と0.011171だった。グラフの20,480フレームは、基準値がゼロになる30点で最大8.29×10⁻¹⁷の差があり、ほかは全ビットが一致した。人工の128フレーム欠落・重複・無音置換と連続対照も通過した。[初回の実測](../runs/safari-process-tap-smooth-marker-44100-20261122-a/summary.json)・[再実行の実測](../runs/safari-process-tap-smooth-marker-44100-20261122-repeat/summary.json)

出力選択のない既存48 kHz校正も回帰として実行し、26項目を通過した。別の既存検証では44.1 kHzの固定発声がCLIとWorkletで全83,072フレーム一致し、固定上流との最大絶対差は1.14×10⁻¹³だった。今回の校正からFirefoxの要求幅や物理出力までは確定できない。次は同じヘッドフォンを使うFirefoxで、44.1 kHzのContextと機器の組でのcubebの実測要求幅を取り、タップとI/Oを結合する窓の幅に使う。[48 kHzの回帰](../runs/safari-process-tap-smooth-marker-20261122-output-device-regression/summary.json)・[固定発声の比較](../runs/worklet-rate-44100-20261120-d/summary.json)・[既存のFirefoxの機器要求と先行音の照合](../tools/measure_worklet_tsp_device_preparation.py#L17)

研究ワークスペースで次を実行した。3実行の59入力と55出力をサイズとSHA-256で検証し、2,216,940バイトの出力をRTL9210B-CGに保存した。[初回の実行記録](../runs/safari-process-tap-smooth-marker-44100-20261122-a/manifest.json)・[再実行の記録](../runs/safari-process-tap-smooth-marker-44100-20261122-repeat/manifest.json)・[48 kHz回帰の実行記録](../runs/safari-process-tap-smooth-marker-20261122-output-device-regression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=30000000 ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py safari-process-tap-smooth-marker-44100-20261122-a /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app --case cases/safari-process-tap-smooth-marker-44100.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=30000000 ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py safari-process-tap-smooth-marker-44100-20261122-repeat /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app --case cases/safari-process-tap-smooth-marker-44100.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=30000000 ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py safari-process-tap-smooth-marker-20261122-output-device-regression /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app --case cases/safari-process-tap-smooth-marker.json
```

## Firefoxで44.1 kHzのcubeb要求とヘッドフォンへのWriteを照合する

固定上流の `AudioEngine.build(rate)` がHzで指定したレートでContextを開く。 `ChimeraProcessor.process()` は出力幅でWASMの `engine_render()` を呼び、Rustの `Engine::render()` は通算サンプル位置の128フレーム境界で制御を更新する。1・77・128・4,096・48,000フレームを比較する試験では出力がビット一致する。今回の校正では同じWorkletの128フレーム単位で既知の試験音を送り、外部で要求されるフレーム数と別に記録する。[上流Context](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

以前のFirefox計測版のcubebには48,000 Hzだけを採取する条件が、ストリームの生成と出力コールバックの両方にあった。44,100 Hzも採取対象に加え、cubebが指定したレートと、実際にコピーしたバッファのレートを記録する。出力専用・ステレオ・Float32の条件と、事前確保領域への収録は従来と同じ。Safariの44.1 kHz校正から機器とタップの512フレーム幅を予測し、Firefoxのcubebも同じ幅かを実測する。既知の逆相試験音のグラフ位置4,096〜20,480を観測し、cubebとタップのPCMを試験音の添字へ、cubebと機器Writeの時刻を出力予定時刻へ対応付ける。最初の結合の判定と補足は別に保存する。[事前登録](../cases/firefox-process-tap-cubeb-write-44100.json)・[cubeb計測差分](../tools/chimera-cubeb-output-snapshot.patch)・[Safariの校正](../runs/safari-process-tap-smooth-marker-44100-20261122-repeat/summary.json)

再ビルドでは、同梱したcubebの変更ファイルとCargo用のチェックサムを更新した。最初の増分ビルドは新しいcubebをコンパイルしなかった。cubebだけを強制しても、XULに入る `libgkrust.a` は旧コードを保持した。cubeb、`gkrust-shared`、`gkrust` のCargoキャッシュを退避し、Rustの静的ライブラリからXULまで再生成した。従来の48 kHz計測との比較に使うアプリを退避してからビルドし、最後に所定の場所へ戻す。[最初の増分ビルド](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122/gecko-build.log)・[cubebだけを強制したビルド](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-forced/gecko-build.log)・[最終ビルド](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/gecko-build.log)

ブラウザ側だけの予備実行で、最初の観測フレームはページが指定した開始位置より384フレーム後だった。PCMの先頭には既知信号の先頭があり、20,480フレームの全点が独立生成と一致した。予定位置と実際のWorkletフレームを両方記録し、PCMの連続性の検証は実測の先頭から行う。保存済みの48 kHzの6試行でも、新しい時刻の照合で21〜41件の連続した256フレームのWriteを復元した。[初回のブラウザ側の観測](/Volumes/RTL9210B-CG/voice-simulator/scratch/firefox-marker-fixture.67iMq8/graph.json)・[予定と実測を分けた予備実行](/Volumes/RTL9210B-CG/voice-simulator/scratch/firefox-marker-fixture.JQKr3I/graph.json)・[48 kHz回帰の元データ](../runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/summary.json)

第1版の初回は収録を完了した後、NumPyの真偽値をJSONに書き出せなかった。真偽値をPythonの型に直し、生ファイルとマニフェストを検証して同じ条件のまま再解析した。初回と再収録で、cubebが要求したレートとバッファのレートは44,100 Hz、幅は256フレームだった。機器の公称バッファとタップは512フレームだった。cubebの収録上限256個は約1.486秒であり、試験音の前に同じContextの無音で埋まった。タップには試験音が残り、初回は16,384フレームを相対RMS残差0.003535で照合できた。第2版では出力経路を保ち、タップとトレースの準備ができてから無音Contextを閉じ、試験音用のContextを新たに開く。試験信号と観測窓は第1版と同じにした。[初回の保存記録](../runs/firefox-process-tap-cubeb-write-44100-20261122-a/manifest.json)・[初回の再解析](../runs/firefox-process-tap-cubeb-write-44100-20261122-replay/summary.json)・[第1版の再収録](../runs/firefox-process-tap-cubeb-write-44100-20261122-repeat/summary.json)・[第2版の事前登録](../cases/firefox-process-tap-cubeb-write-44100-separate-prime.json)

| 第2版の観測 | 初回 | 再収録 |
| --- | ---: | ---: |
| Context・cubeb・機器・タップのレート | 44,100 Hz | 44,100 Hz |
| Worklet / cubeb / 機器Write / タップの幅 | 128 / 256 / 256 / 512 | 128 / 256 / 256 / 512 |
| タップの連続した試験音の照合長 | 16,384フレーム | 16,384フレーム |
| ホスト時刻で測った窓の両端の差 | 44.212 µs | 44.081 µs |
| 機器のサンプル番号から連続で照合したWrite | 64件 | 64件 |
| 補足の独立7窓での最大位置差 | 0.009432フレーム | 0.000001フレーム未満 |
| Writeに対応するPCMの最大相対RMS残差 | 0.008466 | 0.002575 |

第2版の両試行で無音用と試験音用の2つのcubebストリームを記録し、試験音を含むストリームを一意に特定した。44.1 kHzのcubeb要求とヘッドフォンへのWriteは256フレームで、機器の公称バッファとタップは512フレームだった。Audio Clientは試験音の窓内で64要求すべてを照合した。ホスト時刻を名目レートでサンプル番号へ換算する登録判定では、両端の差が約1.95フレームあり不合格となった。収録の終盤でAudio Serverの連続2行の予定ホスト時刻が、サンプル番号の進みから計算した間隔より約1.94フレーム分短くなっていた。同じ窓でタップの隣接するホスト時刻とサンプル時刻から求めた差は最大0.001フレームだった。予定ホスト時刻が変わった内部要因は未確定。[初回の時計と波形](../runs/firefox-process-tap-cubeb-write-44100-separate-prime-20261122-a/summary.json)・[再収録の時計と波形](../runs/firefox-process-tap-cubeb-write-44100-separate-prime-20261122-repeat/summary.json)

補足では、既知波形の最初の1,024フレームで対応する原点を決め、残りのWriteを機器のサンプル番号とタップの連続したサンプル時刻から位置付けた。原点の決定に使わなかった7窓で予測したPCM位置を再照合した後、ヘッドフォンへの64件のWriteそれぞれを、cubebとタップの両PCMから計算した残差で検証した。再収録でも64件が連続した。別計算では既知波形を整数式で生成し、両端の相関位置、XMLの予定ホスト時刻とWrite、Audio Client、左右差の最小二乗残差を再現した。トレースの出力スレッドは両試行とも `BuiltInHeadphoneOutputDevice` だった。試験後は内蔵スピーカーへ復元し、ハッシュが一致する従来のFirefox計測版も保持した。[補足の事前登録](../cases/firefox-process-tap-sample-clock-44100.json)・[初回の補足](../runs/firefox-process-tap-sample-clock-44100-20261122-a/summary.json)・[再収録の補足](../runs/firefox-process-tap-sample-clock-44100-20261122-repeat/summary.json)

7実行の186入力・655出力をサイズとSHA-256で照合した。トレースと判定を含む98,488,864バイトの出力をRTL9210B-CGに保存した。次はこの出力条件で確認用07の44.1 kHzの通常発話を用意し、CLIとWorkletのPCMを照合してから、発話開始の256フレーム要求と512フレームのタップに処理予算を対応させる。今回は連続した試験信号を検証した。負荷による欠落周期、音声の物理出力、実録音との試聴は引き続き調べる。[第2版の実行記録](../runs/firefox-process-tap-cubeb-write-44100-separate-prime-20261122-a/manifest.json)・[補足の実行記録](../runs/firefox-process-tap-sample-clock-44100-20261122-repeat/manifest.json)・[旧48 kHzの発話開始の観測](../runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/summary.json)

研究ワークスペースで第2版の収録と2件の補足を次の手順で実行した。ビルドした計測版と採取アプリはRTL9210B-CG上にある。

```bash
chimera_firefox_44100="/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox"
chimera_tap_app="/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 ../../.venv/bin/python tools/measure_firefox_output_marker.py firefox-process-tap-cubeb-write-44100-separate-prime-20261122-a "$chimera_firefox_44100" "$chimera_tap_app" --case cases/firefox-process-tap-cubeb-write-44100-separate-prime.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 ../../.venv/bin/python tools/measure_firefox_output_marker.py firefox-process-tap-cubeb-write-44100-separate-prime-20261122-repeat "$chimera_firefox_44100" "$chimera_tap_app" --case cases/firefox-process-tap-cubeb-write-44100-separate-prime.json
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_firefox_output_sample_clock.py firefox-process-tap-sample-clock-44100-20261122-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_firefox_output_sample_clock.py firefox-process-tap-sample-clock-44100-20261122-repeat --capture-run firefox-process-tap-cubeb-write-44100-separate-prime-20261122-repeat
```

## 確認用07を44.1 kHzで再生して発話開始を照合する

固定版の `AudioEngine.build(rate)` でContextを開き、`ChimeraProcessor.process()` が出力配列の幅を `engine_render()` へ渡す。Rustの `Engine::render()` は通算位置に基づいて128フレーム境界で更新する。上流のホスト幅可変テストでは128フレームを基準にPCMがビット一致する。研究版の英語発話では `prepareEnglishVoice()` が辞書と発話秒数から計画を作り、秒数と出力レートの積を丸めてPCM長を決める。CLIも同じ丸め方で、内部レートを出力レートの2倍に設定する。[上流Context](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[研究版の発話準備](../../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L277)・[CLIの出力フレーム](../crates/vocal-cli/src/timing_case/speech_voice.rs#L550)

入力は確認用07の保存ケースに固定し、内部96,000 Hzと出力48,000 Hzを88,200 Hzと44,100 Hzに変更する。2.2401362秒から98,790フレーム、最初の非ゼロを2,241±16フレームと見積もった。Firefoxの機器側では、工学上の最初の非ゼロ点と、64フレームのRMSが10⁻⁴を超える観測点を使う。同じContextの逆相信号からcubeb・タップの対応を求め、左右平均から発話を取り出す。校正で確認したWriteのサンプル番号を使い、発話開始を含む機器Writeへ対応付ける。[44.1 kHzの発話ケース](../cases/worklet-live-tsp-44100.json)・[機器収録の事前登録](../cases/worklet-live-tsp-44100-headphone-onset.json)・[連続信号の校正](../runs/firefox-process-tap-sample-clock-44100-20261122-repeat/summary.json)

通常再生のCLI、オフラインWorklet、実時間Workletは全98,790フレームでビット一致した。両Workletの発声状態は3,088点と声門の観測系列で一致した。実時間は128フレーム量子で772回描画し、最後は102フレームが有効だった。固定上流の44.1 kHz出力との最大絶対差は1.1642×10⁻¹⁰、最初のビット差は2,593フレームだった。最初の非ゼロは全経路で2,247フレーム。経過時間は50.952 msで、先行の48 kHz条件の50.8125 msから0.140 ms延びた。発話計画の秒単位の時刻とジェスチャーは48 kHzから変わらなかった。上流の `engine` と `english` の試験、Viteビルドも通過した。[通常再生の比較](../runs/worklet-live-tsp-44100-20261122-a/summary.json)・[固定上流の出力](../runs/worklet-live-tsp-44100-20261122-a/artifacts/upstream.f32le)・[実行記録](../runs/worklet-live-tsp-44100-20261122-a/manifest.json)

| 観測 | 250 msの初回 | 250 msの再収録・補足 | 400 msで再収録 |
| --- | ---: | ---: | ---: |
| CLIとWorkletの最初の非ゼロ | 2,247 | 2,247 | 2,247 |
| cubebとタップでRMSがしきい値を超えた発話内フレーム | 2,923 | 2,923 | 2,923 |
| 最初の非ゼロのWrite内位置 | 199フレーム | 欠測 | 199フレーム |
| RMSによる開始点のWrite内位置 | 107フレーム | 107フレーム | 107フレーム |
| タップの発話の相対RMS残差 | 0.090054 | 0.071420 | 0.071420 |

cubebと機器Writeは256フレーム、タップは512フレームだった。最初の非ゼロとRMSによる開始点はいずれも、ヘッドフォンへのWriteの256フレーム区間の中にあった。両点の直後のcubeb要求でサンプル時刻の飛びはなかった。照合したcubebの処理時間は2.455〜2.722 msで、256フレームの予算は5.805 ms。左右平均で取り出したcubeb PCMとCLIの相対RMS残差は1.62×10⁻⁸だった。タップではこれより大きく、cubebとタップの左右平均の差が10⁻⁶を初めて超えたのは3試行とも発話内3,238フレームだった。差はcubebからタップまでの間で現れ、開始点の対応は維持された。物理出力の波形と、その区間で差を作る処理は未確認。[初回の追加解析](../runs/worklet-live-tsp-44100-headphone-onset-20261122-review/summary.json)・[再収録の追加解析](../runs/worklet-live-tsp-44100-headphone-onset-20261122-repeat-review/summary.json)・[400 ms条件](../runs/worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a/summary.json)

250 msの再収録では、登録窓先頭の1,024フレームの相関が0.9681で、0.995の基準に届かなかった。先頭を1要求分だけ短くした補足では開始位置を照合できた。最初の非ゼロ点に対応する音声サーバー行は入っておらず、RMSによる開始点のWriteを確認した。再生許可を150 ms遅らせた400 ms条件では、同じ比較窓で両方のWriteを照合できた。元の不合格・欠測を保存し、後続の波形と時刻は生ファイルから独立に再計算した。[当初の欠測](../runs/worklet-live-tsp-44100-headphone-onset-20261122-repeat/summary.json)・[窓を短くした解析](../runs/worklet-live-tsp-44100-headphone-onset-20261122-repeat-review/manifest.json)・[400 ms条件の登録](../cases/worklet-live-tsp-44100-headphone-onset-gate-400ms.json)・[再収録の記録](../runs/worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a/manifest.json)

全6実行の1,460入力と534出力をサイズとSHA-256で照合し、132,151,804バイトの出力をRTL9210B-CGに保存した。次は400 ms条件で48 kHz時と同じ破棄描画を使い、実測した256フレーム幅に対する5.805 msの前後で、欠落周期とPCMの反復・無音挿入を比較する。[通常再生の手順](../runs/worklet-live-tsp-44100-20261122-a/manifest.json)・[250 msの収録](../runs/worklet-live-tsp-44100-headphone-onset-20261122-a/manifest.json)・[400 msの収録](../runs/worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a/manifest.json)

研究ワークスペースで次のコマンドを実行した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=180000000 ../../.venv/bin/python tools/measure_worklet_live_tsp_rate.py worklet-live-tsp-44100-20261122-a '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox'
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_onset.py worklet-live-tsp-44100-headphone-onset-20261122-a '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox' /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_onset.py worklet-live-tsp-44100-headphone-onset-20261122-repeat '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox' /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_onset.py worklet-live-tsp-44100-headphone-onset-20261122-review '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox' /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app --from-run worklet-live-tsp-44100-headphone-onset-20261122-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_onset.py worklet-live-tsp-44100-headphone-onset-20261122-repeat-review '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox' /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app --from-run worklet-live-tsp-44100-headphone-onset-20261122-repeat --trim-leading-anchor-frames 256
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_onset.py worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox' /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app --case cases/worklet-live-tsp-44100-headphone-onset-gate-400ms.json
```

## 44.1 kHzで発話直前の描画負荷を比較する

固定上流の `AudioEngine.build()` は指定レートでAudioContextを開き、`ChimeraProcessor.process()` が出力配列の幅をWASMの `engine_render()` へ渡す。Rustの `Engine::render()` は128フレーム境界で更新し、ホストのブロック幅を変えてもPCMが同じことを試験する。研究版の負荷計測では別の発声器を用意してPCMを破棄する。待機中に64フレームを3回描き、最後の片を最初の発話量子の直前へ置く。破棄描画の合計は288条件が480フレーム、416条件が608フレーム。発話側のレートと状態は44.1 kHzの通常再生と照合する。[上流の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ホスト幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[研究版の待機処理](../../../../web/prototypes/chimera-research/src/fixed-processor.ts#L201)

出力先と400 msの再生許可時刻は通常再生の収録とそろえる。呼び出しの最後の破棄描画を含む要求と最初の発話量子を含む要求を別々に同定し、256 ÷ 44,100 ≈ 5.805 msと比較する。288フレームで予算を下回り、416フレームで予算に達するか超えると予測した。サンプル番号の挙動を確認し、飛びがあればタップとcubebの両端の差分信号で増分を照合し、同相・逆相別に無音と反復のモデルを当てる。[事前登録](../cases/worklet-live-tsp-44100-headphone-load.json)・[48 kHzの288フレーム](#確認用07に同相の試験信号を加えて反復を調べる)・[44.1 kHzの無負荷対照](../runs/worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a/summary.json)

最初の4試行では、最後の破棄描画が256フレーム要求の後半（128フレーム目）、最初の発話量子が次の要求の先頭に入った。最後の破棄描画を含む要求のcubeb処理は288条件で3.330〜3.620 ms、416条件で4.702〜4.704 ms。全4試行で時間予算内に収まり、予定サンプル番号とタップPCMに飛びはなかった。予測した負荷の差を観測するため、既存の発話開始を1量子遅らせる設定を使い、最後の破棄描画と最初の発話量子を同じ要求に入れる比較を登録した。破棄描画量と出力先は維持した。Workletの観測JSONには各破棄描画が行われたContextフレームと累計フレームを保存した。[元の288条件](../runs/worklet-live-tsp-44100-headphone-load-20261122-1/summary.json)・[元の416条件](../runs/worklet-live-tsp-44100-headphone-load-20261122-2/summary.json)・[同じ要求へ置くケース](../cases/worklet-live-tsp-44100-headphone-load-same-request.json)

| 最後の破棄描画 | 1要求に含めた処理 | cubeb処理時間 | Audio Clientの処理時間 | 飛び |
| --- | --- | ---: | ---: | ---: |
| 288フレーム | 破棄描画 | 3.330〜3.620 ms | 3.337〜3.635 ms | 0/2 |
| 416フレーム | 破棄描画 | 4.702〜4.704 ms | 4.712〜4.717 ms | 0/2 |
| 288フレーム | 破棄描画と最初の発話量子 | 5.270〜5.468 ms | 5.285〜5.480 ms | 0/2 |
| 416フレーム | 破棄描画と最初の発話量子 | 6.339〜6.459 ms | 6.350〜6.471 ms | 1/2 |

二つの処理をまとめた4試行では、最後の破棄描画が要求の先頭、発話量子が128フレーム目だった。416条件の2試行はcubebとAudio Clientの両方が5.805 msを超えた。第2試行では予定サンプル番号が292フレーム飛び、タップには同じ292フレームの増分があった。第3試行は予算超過の後も256フレームずつ進んだ。予定区間と機器Writeの幅を固定した登録の照合では、両試行の負荷要求を機器Writeと結べなかった。補足ではAudio Serverの予定ホスト時刻とサンプル番号を使い、同じヘッドフォンへのWriteとAudio Clientを個別に復元した。サーバー行の開始から対象Writeまで、それぞれ6.507 ms、6.390 msかかった。[同一要求の288条件](../runs/worklet-live-tsp-44100-headphone-load-same-request-20261122-1/summary.json)・[飛びありの416条件](../runs/worklet-live-tsp-44100-headphone-load-same-request-20261122-2/summary.json)・[飛びなしの416条件](../runs/worklet-live-tsp-44100-headphone-load-same-request-20261122-3/summary.json)・[補足解析](../runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json)

飛びがあった試行では、対象要求のWriteは機器サンプル106,116から256フレームだった。次に照合したヘッドフォンのWriteは106,408から512フレームで、次のcubeb要求に対応するサーバーの予定位置106,664がその中央に入った。タップの両チャンネルが同時に完全ゼロとなる連続区間は293フレーム。サンプル番号に基づいてタップとWriteの位置を重ねると、このゼロ区間の209フレームが512フレームのWriteに重なった。この重なりはプロセスタップと機器Writeの位置を比較した結果で、アナログの出力波形は未観測。[Writeのサンプル番号とタップのゼロ区間](../runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json)

292フレームを無音または前後波形として挿入する補足では、同相・逆相とも無音モデルが最小だった。相対RMS残差はそれぞれ0.1577、0.1706で、0.025の基準に届かなかった。無音前後の離れた窓では先行信号が再び整列し、無音とその前後を含む波形は今回の挿入モデルで説明しきれなかった。予算超過だけから予定時刻の飛びは予測できず、飛びの幅がちょうど256フレームという予測も外れた。次は416フレームの同一要求条件を繰り返し、512フレームのWriteが続くときのタップ位置と無音前後の波形を照合する。[波形比較の登録](../cases/worklet-live-tsp-44100-headphone-late-write-review.json)・[モデルの残差](../runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json)

全8収録で44.1 kHzの発話WAV、ジェスチャー、発声状態が通常再生と一致した。Viteビルドと、WASMの分割描画の状態一致試験は通過した。要求時刻、タップの相関位置、ヘッドフォンWrite、無音・反復モデルを生ファイルから別計算した。9実行の1,372入力・1,373出力をサイズとSHA-256で照合し、273,099,049バイトの出力をRTL9210B-CGへ保存した。試行後の既定出力は内蔵スピーカーに戻した。[最初の計測記録](../runs/worklet-live-tsp-44100-headphone-load-20261122-1/manifest.json)・[条件をそろえた計測記録](../runs/worklet-live-tsp-44100-headphone-load-same-request-20261122-4/manifest.json)・[補足解析の実行記録](../runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/manifest.json)

研究ワークスペースで2つの比較と補足を実行した。

```bash
for trial in 1 2 3 4; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_load.py "worklet-live-tsp-44100-headphone-load-20261122-$trial" '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox' '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app' --trial "$trial"
done
for trial in 1 2 3 4; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_load.py "worklet-live-tsp-44100-headphone-load-same-request-20261122-$trial" '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox' '/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app' --trial "$trial" --case cases/worklet-live-tsp-44100-headphone-load-same-request.json
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_late_write.py worklet-live-tsp-44100-headphone-late-write-review-20261122-a
```


## 同じ416フレーム負荷を44.1 kHzで6回繰り返す

固定上流の `AudioEngine.build` は出力レートをHzで受けて2出力のWorkletを作る。`ChimeraProcessor.process` は出力配列の長さだけ `engine_render` を呼び、Rustから受け取った `f32` を左から右へ複製する。処理負荷の計算は、PCMを出力配列へ書いた後で、ホストブロック幅をサンプルレートで割った時間を分母にする。WASMの `engine_render` は長さを内部バッファの最大幅に制限する。Rustの `Engine::render` は通算サンプル数 `pos` から内部ブロック位相を求め、境界で制御を先に更新し、音響描画後に `pos` を進める。エンジン試験はイベントのサンプル位置を固定し、ホストブロック幅を1、77、128、4,096、48,000と変えて出力の全ビットを照合する。[音声グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Workletの出力](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASMの描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rustの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

再実装の確認用07で、最後の416フレームの破棄描画と最初の発話量子を、先行音が鳴る同じ256フレームの要求の位置0と128に置く。前回の2回はいずれも予算5.805 msを超え、うち1回で予定番号が292フレーム進み、次の予定位置をまたぐ512フレームの機器Writeとタップの独立した無音区間が見つかった。追加する6回は同じヘッドフォン、マーカー、400 msの採取ゲート、描画量に固定する。少なくとも1回で飛び・512フレームWrite・両チャンネル無音の組合せ、1回で予定番号の連続を予測する。観測はcubebの要求、Audio Client区間、ヘッドフォンWriteのサンプル位置、プロセスタップのPCMを用いる。比較窓、局所モデルの残差と欠測の扱いを収録前に登録した。[事前登録](../cases/worklet-live-tsp-44100-headphone-load-416-repeat.json)・[前回の生データ照合](../runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json)

第3試行のタップで前側アンカーだけが一意に決まらなかった。補足は既存の再解析機能を使い、前端だけを256フレームずつ最大1,024フレームまで後ろへ移し、最初に前後のアンカーとサンプル時計がそろった窓を採る。元の窓、時刻、負荷、試行番号は収録時の記録に残す。

### 収録とサンプル番号の照合

| 試行 | cubeb (ms) | Audio Client (ms) | 対象要求のWriteまで (ms) | 直後の飛び (フレーム) | タップ |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 6.715 | 6.748 | 6.799 | 308 | 観測窓で624フレーム増加。完全無音が309・317フレーム |
| 2 | 6.186 | 6.195 | 6.225 | 0 | 時計が連続。完全無音なし |
| 3 | 6.396 | 6.407 | 6.447 | 0 | 収録時に前側アンカー欠測。前端を256フレーム短縮して時計が連続。完全無音なし |
| 4 | 6.382 | 6.389 | 6.420 | 0 | 時計が連続。完全無音なし |
| 5 | 6.295 | 6.308 | 6.346 | 0 | 時計が連続。完全無音なし |
| 6 | 6.110 | 6.119 | 6.155 | 0 | 時計が連続。完全無音なし |

6回とも最後の416フレームを要求内の位置0で描画し、発話を位置128から出力した。発話WAVの98,790フレームと発声状態は通常再生と一致。6回ともcubebとAudio Clientで5.805 msを超えた。元の照合は1周期以内のWriteを要求していたため5回でWriteを同定できず、もう1回は前側アンカーの欠測でそこまで進まなかった。補足では予定ホスト時刻を25 µs以内、ヘッドフォンWriteを同じスレッドと予定サンプル番号で結び、Writeの開始を最大2周期まで許した。Writeのホスト時計からAudio Clientがcubeb区間を囲むことを確かめた。飛んだ区間に挟まるWriteは同じ機器エンジン・ストリームで照合する。第3試行の256フレーム短い補足窓では6,912フレームが連続した。[元の集約](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-analysis-v2/summary.json)・[第3試行の補足](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-3-trim-256/summary.json)・[生データに基づく最終集約](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/summary.json)

第1試行の予定番号の飛びは、出力要求45の後で308フレーム、6要求後の要求51の後で316フレーム。2件の合計624フレームは、逆相マーカーから取ったタップ窓の正味増加と一致した。要求51のcubebは2.750 ms、Audio Clientは2.764 msで予算内だった。同じ要求で、Audio Server行の開始からAudio Client開始まで4.186 ms、ヘッドフォンWrite開始までは6.992 msかかった。登録した1要求の比較は308フレーム側で再現と判定し、316フレーム側は同じ窓内の追加観測として記録した。[第1試行の生データ](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-1/manifest.json)・[要求51の時刻とWrite](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/summary.json)

| 飛び (フレーム) | 直前・直後の予定機器サンプル | 512フレームWriteの開始 | タップ中のWrite対応窓 | 完全無音区間 |
| ---: | --- | ---: | --- | --- |
| 292（前回） | 106116 → 106664 | 106408 | [3236, 3748) | [3152, 3445) |
| 308（今回の要求45） | 130508 → 131072 | 130816 | [3252, 3764) | [3152, 3461) |
| 316（今回の要求51） | 132352 → 132924 | 132668 | [5104, 5616) | [4996, 5313) |

3件とも、次の予定サンプルは512フレームWriteの位置256だった。先行信号と予定時刻で対応づけた各タップ窓では、直前要求の先頭の208フレーム後から両チャンネルが完全ゼロになり、その長さは飛びより1フレーム長かった。Writeに対応する区間と無音の重なりは各209フレームだった。タップはFirefoxプロセスのPCMを記録しており、アナログの記録はない。前回の292フレームの単一飛びでは、無音・反復の単純な局所モデルが許容残差を外れた。今回の第1試行は2箇所に飛びがあり、登録した単一飛びのモデル判定は欠測として保存した。

予定番号が連続した5回は、逆相マーカーの全窓の相対残差が0.000032程度だった。同相は0.03748〜0.03769で、絶対差10⁻⁵を初めて超える位置は5回とも発話描画開始の3,371フレーム後だった。最大差も0.001418で同じだった。以降の局所波形を比較するときは、飛びがない試行の同じ発話位置の残差も併記する。[前回の局所モデル](../runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json)・[今回の成分別残差](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/summary.json)

### 再現

Apple Silicon macOS 15.6.1、Xcode 26.2 (17C52)、Firefox 157.0の同じ計測ビルド、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1を使用。Audio ClientとAudio Serverを同じFirefoxのPIDに2秒間アタッチし、ゲートを400 msに固定した。ヘッドフォンのサンプルレートは44.1 kHz。試行ごとに既定出力を内蔵スピーカーへ戻した。生ファイルと解析の実体はRTL9210B-CGへ保存し、実行ID・要約・再現用のマニフェストは研究ワークスペースの `runs/` から開ける。集約の初回はcubebのパス階層を誤って参照し中断した。直してから、元の判定と短縮窓の補足を別々の実行IDで保存した。[収録のマニフェスト](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-6/manifest.json)・[最終解析のマニフェスト](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/manifest.json)

```sh
firefox=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox
probe=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
case_file=cases/worklet-live-tsp-44100-headphone-load-416-repeat.json
prefix=worklet-live-tsp-44100-headphone-load-416-repeat-20261122
for trial in 1 2 3 4 5 6; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=300000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_load.py "$prefix-$trial" "$firefox" "$probe" --case "$case_file" --trial "$trial"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_load.py "$prefix-3-trim-256" "$firefox" "$probe" --case "$case_file" --trial 3 --from-run "$prefix-3" --trim-leading-anchor-frames 256
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_load_repeat.py "$prefix-verified" --tap-review "$prefix-3-trim-256"
```

保存済みの6収録を再解析する場合は、最後のコマンドの出力実行IDを変える。収録ファイルの `blocks.csv` から `次の予定番号 − 現在の予定番号 − 要求幅` とcubebのホスト時刻差を計算し直した。トレースXMLのヘッドフォンWrite行のサンプル番号と幅、FirefoxのAudio Client行、ステレオ `f32` の完全ゼロの区間、発話WAVと状態も独立に確認した。上流の `cargo test --locked --offline -p chimera --test engine` は6件通過。再実装の `cargo test --locked --offline -p vocal-wasm --lib score_preparation_keeps_the_same_state_through_partial_last_block` は1件通過。従来の遅いWriteの解析は、元の不合格判定を含めた保存済みの要約全体とバイト一致した。[従来ケースの回帰](../runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-repeat-regression/manifest.json)


## 44.1 kHzタップの無音前後を64フレームで照合する

上流の `AudioEngine.build` はHzで `AudioContext` を作り、Workletをマスターゲイン経由で機器へつなぐ。`ChimeraProcessor.process` ではホストが渡す平面ステレオの1チャンネル分を `engine_render` に要求し、モノラルの `f32` PCMを左右に複製してから時間比を更新する。WASMのABIは描画長を内部バッファ幅に制限する。Rustの `Engine::render` は通算位置を内部ブロック幅で割った余りから制御更新の境界を選び、制御、発声、位置の加算の順に実行する。`output_does_not_depend_on_the_host_block_size` はイベントを同一のサンプル位置に置き、ホスト幅を変えたPCMをビット比較する。[グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

今回比べるのは再実装の下流にある二つの観測点。計測用FirefoxはAudioUnitの出力コールバックが返すバッファと予定サンプル番号を保存する。Swiftの `capture` はFirefoxのPIDを `CATapDescription` に渡し、プロセス単位のステレオを読み、PCMとサンプル時刻・ホスト時刻を保存する。同相は `(L+R)/2`、逆相は `(L−R)/2`。予定番号の飛びは次の開始番号から今の開始番号と要求幅256を引く。比較窓の開始をゼロとし、観測された完全ゼロの区間の両側で、先行信号のサンプル対応を求める。タップ上の位置は、先行信号を基準とした相対フレーム数で表す。[cubeb計測差分](../tools/chimera-cubeb-output-snapshot.patch)・[プロセスタップ](../tools/chimera_process_tap.swift#L121)・[前回の照合](../runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/summary.json)

比較前に、292・308・316フレームの3件と連続した第2試行の対応する2箇所、各64フレームの窓、ラグの探索幅、残差閾値を登録した。無音から256フレーム離れた窓では、逆相で求めた前後のラグ差が予定時刻の飛びに一致すると予測する。無音のすぐ外側は前の比較で単純な挿入を支持しなかったため、少なくとも1件で遠方のラグを使った残差が上がると予測する。同相・逆相に同じゲインが掛かったときに成り立つ相互予測も測る。[事前登録](../cases/worklet-live-tsp-44100-headphone-gap-edges.json)

### 遠方での位置合わせと無音直後の波形

登録した第1版では、無音の終端から256フレーム先の単独窓で、292・308フレームの飛びと対照1箇所の位置が決まらなかった。候補の範囲内で逆相マーカーが定値となり、最良候補と2フレーム以上離れた候補の残差差が0だった。位置を決められなかった3箇所を保持し、同じ64フレーム窓のうち128・256フレーム先を連結する補足条件を登録した。ラグの探索幅と残差の基準を共通にした。再実行した第1版でも判定は一致した。[第1版](../runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-a/summary.json)・[補足ケース](../cases/worklet-live-tsp-44100-headphone-gap-edges-joint-anchor.json)・[補足の結果](../runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/summary.json)

| 予定番号の飛び | 遠方でのラグ 前 → 後 (フレーム) | 無音のすぐ前の残差 同相 / 逆相 | 無音のすぐ後の残差 同相 / 逆相 | 64フレーム先の残差 同相 / 逆相 |
| --- | --- | --- | --- | --- |
| 292 | 0 → 292 | 0.000042 / 0.000028 | 0.801 / 0.833 | 0.000570 / 0.000627 |
| 308 | 0 → 308 | 0.000042 / 0.000028 | 0.801 / 0.833 | 0.000570 / 0.000627 |
| 316 | 308 → 624 | 0.000022 / 0.000023 | 0.903 / 0.881 | 0.000629 / 0.000486 |
| 対照の2箇所 | 0 → 0 | 0.000043以下 | 0.000035以下 | 0.000041以下 |

遠方で確定したラグで時刻をそろえ、64フレームごとに単一の比例係数を当てた。飛びの前後のラグ差は全3箇所で予定番号の飛びと整数フレームで一致した。先行信号から無音への入り口は、直前までcubebと一致した。無音の出口は64フレームの単一ゲインで説明できず、絶対差10⁻⁵を超えた最後のサンプルは、完全無音が終わった次の非ゼロ点を位置0として3箇所とも位置64だった。128フレーム先では全3箇所で両成分の相対残差が0.000044以下に戻った。この比較はプロセスタップとcubebのPCMに基づく。機器Writeの生の標本値とアナログ波形は未採取。[保存した波形と位置](../runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/summary.json)

無音直後の64フレームで、参照の両成分が1/4096以上の標本を採り、片方の成分から求めた標本ごとの係数で他方を予測した。292・308フレームの飛びでは各62点で両方向の残差が0.000036以下。推定係数は約−0.048〜1.048で、符号反転と1を超える値を含む。2箇所の整列済み128フレームはcubebでもタップでも標本が同一で、条件を変えた波形での追試は316フレーム側になる。316フレームの飛びは60点で同相→逆相が0.0141、逆相→同相が0.0391となり、後者は基準0.025を超えた。信号の振幅や形の異なる場合まで同じ係数で説明できるかは、292側の係数を固定して316側に適用し、両成分と連続対照で検証する。[成分別残差と係数範囲](../runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/summary.json)

### 再現と検算

macOS 15.6.1のApple Silicon、Python 3.14.4、NumPy 2.4.4。新しい収録は行わず、Firefox 157.0の保存済みcubebバッファと44.1 kHzのプロセスタップを読み出した。各入力は既存マニフェストのサイズ・SHA-256に照合してから読み込み、JSON要約をRTL9210B-CGの作業領域に記録した。位置の探索は逆相マーカーに対し、整数 `d` ごとに `g = (x·y)/(x·x)` と `||y−gx||₂/||y||₂` を求める。ここで `y` はタップ、`x` は時刻を `d` だけずらしたcubebのPCM。成分別残差は逆相で得た共通のラグを使う。独立の検算では生CSVとステレオPCMから零区間と3件の飛びを取り直し、正規化した行列を使うNumPyの最小二乗と直接の二乗和からラグ・残差・相互予測を再計算した。上流のエンジン6試験と再実装の分割描画試験を確認した。[解析コード](../tools/measure_worklet_tsp_44100_gap_edges.py)・[補足実行のマニフェスト](../runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_gap_edges.py worklet-live-tsp-44100-headphone-gap-edges-20261122-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_gap_edges.py worklet-live-tsp-44100-headphone-gap-edges-20261122-joint --case cases/worklet-live-tsp-44100-headphone-gap-edges-joint-anchor.json
```

同じ作業ツリーから再解析する際は、新しい出力実行IDを使う。


## 44.1 kHz無音出口のゲインを別の波形へ適用する

上流の `AudioEngine.build` はHzを受けてAudioContextを作り、Workletからマスターゲインを通して機器出力へ送る。`ChimeraProcessor.process` はホストの出力幅だけWASMを呼び、描画されたモノラル `f32` を左右へ複製してから処理時間比を更新する。WASMの `engine_render` が描画幅をバッファ上限で制限し、Rustの `Engine::render` は通算描画位置を基に境界で制御を更新し、発声を描画してから位置を進める。上流の `output_does_not_depend_on_the_host_block_size` はイベントを同じ標本位置に置いたままブロック幅を変え、同じPCMを得るか検査する。[グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

今回の二つの観測点はブラウザの音声グラフより後段にある。Firefoxの計測差分はAudioUnit出力コールバック末尾のバッファを返却直前にコピーする。Swiftの `TapBuffer.append` はCore AudioのコールバックでステレオFloat32を受け、平面配列は交互に詰め直し、標本時刻とホスト時刻を記録する。前の計測で確定した整数ラグでcubebとタップの `(L+R)/2` と `(L−R)/2` をそろえ、タップで完全な無音が終わった最初の非ゼロ点を位置0とする。無音のなかった対照は前の計測で置いた仮想境界を使用する。ゲインは無次元で、標本ごとに2成分を合わせる一つの最小二乗係数を292フレームの事例だけから計算する。[cubeb計測差分](../tools/chimera-cubeb-output-snapshot.patch#L237)・[採取コード](../tools/chimera_process_tap.swift#L48)・[確定したラグ](../runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/summary.json)

308フレーム側は292フレーム側と同じ入力と出力の再現対照。波形の異なる316フレーム側に係数を固定して適用すると、無音直後の少なくとも一方の成分で相対残差が0.025を超えると予測する。連続対照ではゲイン1が合格し、過渡ゲインを仮想境界に強制すると外れると予測する。位置0〜64を適用範囲とし、前64フレーム、後方の位置65〜127と128〜191も調べる。各標本の転用誤差が初めて絶対差10⁻⁵を超える位置を保存する。[事前登録](../cases/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer.json)

### 固定ゲインを適用した結果

292フレームの事例で位置0〜64の65標本から1本の係数列を求めた。参照PCMの同相・逆相が両方正確にゼロになる位置23は係数を推定できず、比較に使えたのは64標本。固定ゲインは−0.04808〜1.04808で、推定と転用に同じ係数を使った。308フレームの事例は今回の前後256フレームでも、cubebとタップの各観測点で292と一致した。[初回の判定](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-a/summary.json)・[標本ごとの記録](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-a/artifacts/edge-samples.csv)

| 対象 | ゲイン1の残差 同相 / 逆相 | 固定ゲインの残差 同相 / 逆相 | その対象自身に共通ゲインを当てた残差 同相 / 逆相 |
| --- | --- | --- | --- |
| 292（推定元）・308（同一波形） | 1.303 / 1.470 | 0.00002654 / 0.00000645 | 0.00002654 / 0.00000645 |
| 316（異なる波形） | 1.999 / 1.770 | 0.01171 / 0.01804 | 0.01164 / 0.00813 |
| 連続対照の早い箇所 | 0.00002779 / 0.00002785 | 0.793 / 0.826 | 0.00002302 / 0.00000447 |
| 連続対照の遅い箇所 | 0.00003383 / 0.00003309 | 0.891 / 0.870 | 0.00003682 / 0.00001510 |

表は位置0〜64の相対残差。固定ゲインは位置23を欠測とした。ゲイン1は65点、各対象自身の共通ゲインはその対象で係数を求められた点を使った。316の残差は同相1.17%、逆相1.80%で両方とも登録基準2.5%に収まり、「少なくとも一方が基準外」という予測は外れた。転用できた64点で絶対差10⁻⁵を初めて超えたのは同相の位置22、逆相の位置28で、両成分とも最後は位置64。最大差は同相2.38×10⁻⁵、逆相6.51×10⁻⁵だった。位置65以降はゲイン1で絶対差10⁻⁵以内に戻った。[転用の誤差と標本数](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-a/summary.json)

### 同じcubeb波形を使ったゼロ入力の対照

元の判定を保存した上で、ゲインが未同定の点を含む比較を登録した。cubebの値が正確にゼロの標本では、その標本に有限な係数を掛けた出力もゼロになる。各事例の256標本のcubeb波形は対応する連続対照と一致した。タップを照合すると、292・308の位置23では同相約−2.32×10⁻⁶、逆相約−4.63×10⁻⁶。316では位置23・39・55に該当する点があり、位置39の逆相は−4.98×10⁻⁵だった。対応する連続対照の同じ成分・標本は絶対値1.44×10⁻⁷以下だった。相対残差の基準内でも、同じ位置のPCMだけを比例変換するモデルではこの差が残る。隣接する標本が影響する処理や加算成分は、この比較だけでは区別できない。[補足の事前登録](../cases/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-zero-control.json)・[ゼロ入力と連続対照の結果](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/summary.json)

第1版で「端の外側はゲイン1で回復」と記録した判定には、今回の座標では完全無音に含まれる前64フレームを誤って入れた。第2版の照合では、飛びのある事例の前64フレームはタップの完全ゼロを、後方の位置65〜191はゲイン1での一致を検査した。第1版の3つの不合格と、転用に使えた標本数や残差は元のとおり保存した。[元の判定](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-a/summary.json)・[補足判定](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/summary.json)

### 再現と検算

Apple Silicon macOS 15.6.1、Python 3.14.4、NumPy 2.4.4を使用。Firefox 157.0で保存済みの44.1 kHzのPCM、各収録のマニフェストと前回検証したラグを照合した。新しい収録は行っていない。1,280行の比較用CSVとJSON要約を出力し、RTL9210B-CGに保存した。CSVは元の版と補足版でバイト一致した。独立の検算ではcubebの要求先頭に209標本を加えた位置から元PCMを読み、タップは保存済み境界から読み直した。Pythonの `struct` でステレオFloat32を展開し、`math.fsum` でゲイン・残差・最初と最後の閾値超過位置を再計算した。ゼロ入力での差も連続対照と直接照合した。上流のエンジン6試験と再実装の分割描画1試験は通過した。[実装](../tools/measure_worklet_tsp_44100_edge_gain_transfer.py)・[補足の実行記録](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_edge_gain_transfer.py worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-a
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_edge_gain_transfer.py worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control --case cases/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-zero-control.json
```

保存済みの収録を再解析する場合は、新しい出力実行IDを使う。


## 44.1 kHzの無音出口を隣接標本から予測する

上流では `AudioEngine.build` が出力レートをHzで受けてAudioContextを開く。`ChimeraProcessor.process` はホストの出力長を `engine_render` に渡し、モノラルのFloat32を左右に複製する。WASMは描画要求長を内部バッファ幅に制限する。Rustの `Engine::render` は通算サンプル位置から内部制御の境界を求め、制御更新、発声、位置の加算の順で進める。`output_does_not_depend_on_the_host_block_size` はイベントの位置を固定し、外側のブロック幅を変えてPCMをビット比較する。今回の入出力はこの音声グラフより後段で、計測用Firefoxが返すcubeb PCMと、Core Audioのタップが受け取るステレオPCMの同相・逆相成分を使う。cubeb側はAudioUnitコールバックの出力バッファ末尾を保存し、`TapBuffer.append` はタップの入力バッファを交互の2チャンネルの並びでコピーする。[グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[Firefox計測差分](../tools/chimera-cubeb-output-snapshot.patch#L237)・[タップの採取](../tools/chimera_process_tap.swift#L48)

波形の時刻対応は前回確定した値を使う。完全な無音のすぐ後を0とし、292フレームの事例の同相成分だけで、`タップ値 ÷ cubeb値` が初めて0.5以上になる候補をゲート位置に選ぶ。仮説は、ゲート後のPCM全体、またはゲートで取り除いた分に、共通の対称FIRが働くというもの。係数は無次元、FIRの直流利得は1に固定する。半幅1、4、8、16、32フレームの候補を登録し、前後の標本から作る行列の階数と条件数を確認する。292側の逆相と、波形の異なる316側の同相・逆相では係数を再推定しない。316のゼロ入力位置39の誤差低減を予測し、適用の採否は4つのゼロ入力点すべてと、各成分の窓全体の残差で判断する。308は292と同じ波形の再現対照として使う。[事前登録](../cases/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit.json)・[ゼロ入力の比較](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/summary.json)

### 推定したゲートと係数

292フレームの事例の同相成分で閾値0.5を初めて超えた位置は47だった。cubebの元CSVを別に読み、無音出口の位置0に47を加えると、3件とも次の256フレーム要求のPCM先頭に一致することを確認した。cubebの連結PCMで該当する標本番号は292側が12032、308側が11776、316側が13312だった。ゲートの位置をそのまま使い、292側の同相の位置−16〜111だけで推定した。[ゲート位置・階数・係数](../runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/summary.json)

対称FIRの中心係数を `h[0] = 1 − 2Σh[k]` と置いて、直流利得を1にする。ゲート後のPCMを `z[n]` とすると、その標本に `h[k](z[n−k]+z[n+k]−2z[n])` を足す形になる。取り除いたPCMにだけ適用する場合は、同じ寄与を取り除いたPCMから計算して引く。いずれも出力標本を中心とする実効モデルで、時刻をそろえた収録データを説明する。10候補とも行列は列フルランクで、条件数の最大は126.32だった。[解析実装](../tools/measure_worklet_tsp_44100_edge_neighbor_fit.py)・[全候補](../runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/summary.json)

| 処理対象とFIRの幅 | 316の相対残差 同相 / 逆相 | 316のゼロ入力4点での最大絶対誤差 | 判定 |
| --- | --- | --- | --- |
| ゲート後全体・17係数 | 0.007079 / 0.007048 | 2.66×10⁻⁵ | 基準外 |
| 取り除いた分・17係数 | 0.007084 / 0.007089 | 2.66×10⁻⁵ | 基準外 |
| ゲート後全体・33係数 | 0.002402 / 0.002387 | 4.64×10⁻⁶ | 合格 |
| 取り除いた分・33係数 | 0.002421 / 0.002422 | 4.06×10⁻⁶ | 合格 |
| ゲート後全体・65係数 | 0.00006852 / 0.00006842 | 3.21×10⁻⁸ | 合格 |
| 取り除いた分・65係数 | 0.00012216 / 0.00007055 | 1.17×10⁻⁷ | 合格 |

3・9係数の候補はゼロ入力位置39の誤差を減らせなかった。17係数では位置39は改善したが、位置55が基準外。登録範囲での最小の合格は両方式とも33係数だった。波形全体に65係数を適用するモデルでは、316側の全65標本の最大絶対誤差は同相2.38×10⁻⁷、逆相4.76×10⁻⁷未満だった。逆相のゼロ入力位置39でタップの値−4.98496×10⁻⁵に対し、予測は−4.98706×10⁻⁵。固定ゲインではこの位置の出力はゼロだった。前の回の固定ゲインの相対残差1.17%・1.80%に対し、65係数では両方約0.00685%だった。FIRは全65標本、固定ゲインはゲインを推定できた64標本で評価した。[固定ゲインの結果](../runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/summary.json)・[FIRの結果](../runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/summary.json)

ゲートなしの連続対照の遅い箇所では、全体を処理する65係数の相対残差は同相4.89×10⁻⁶、逆相4.04×10⁻⁶。ゲートで取り除いた分だけを処理する方式では、連続対照はゲイン1となり、約3.3×10⁻⁵だった。全体を処理する65係数の中心は0.9000005、そこから10・20・30標本離れた係数は絶対値9.11×10⁻⁷以下だった。係数の周波数応答を独立に計算すると、17,640 Hzで1.00091、19,845 Hzで0.50041、20,947.5 Hzで0.01523だった。これらは係数から予測した振幅で、試験音による実測は次の比較になる。保存データで再現できたのはタップに至る実効的な処理であり、OS内の作用箇所とアナログの出力は未確定。[係数と連続対照](../runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/summary.json)

### 再現と検算

macOS 15.6.1のApple Silicon、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1。Firefox 157.0の44.1 kHz保存PCMから作った照合済みCSVを読み、外部ディスクRTL9210B-CGに結果を保存した。初回は局所評価の引数を誤って渡したため実行できず、ケース内容を維持して引数を修正し、別IDで測定した。独立検算では左右対称の差分インパルスから全10行列を直接畳み込みで組み、SciPyのピボット付きQRで係数を再計算した。全係数が10⁻¹²以内、成分別の残差も10⁻¹²以内で一致した。元cubeb CSVでゲート位置を照合し、上流のエンジン6試験と再実装の分割描画1試験を確認した。[初回の実行記録](../runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-a/manifest.json)・[測定のマニフェスト](../runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_worklet_tsp_44100_edge_neighbor_fit.py worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b
```

保存済みの波形を再解析するときは新しい出力実行IDを使う。


## 44.1 kHzの連続音でタップの周波数応答を測る

上流の `AudioEngine.build` は指定HzでAudioContextを開き、出力をマスターゲインへつなぐ。`ChimeraProcessor.process` はホストが供給したフレーム数をWASMへ渡し、Rustの `Engine::render` が制御更新の境界を跨いでFloat32を描画する。WorkletはPCMを2出力に複製する。上流のブロック幅の試験ではイベントを同じ標本位置に置いたままホスト幅を変え、出力のビット一致を確かめる。今回は機器に向かう経路を切り分けるため、既存の計測用Workletに既知の逆相信号を送る。cubebの計測差分はFirefoxがAudioUnitへ返すバッファのPCMと予定時刻をコピーし、Core Audioのプロセスタップは同じPIDからステレオのFloat32とコールバック時刻を保存する。[上流グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[cubebの差分](../tools/chimera-cubeb-output-snapshot.patch#L237)・[タップの採取](../tools/chimera_process_tap.swift#L121)

前の解析から65係数の対称FIRを固定した。既存の滑らかな逆相マーカーの間に2,205・17,640・19,845・20,947.5 Hzの連続音を挿入する。両端のマーカーの位置でcubebとタップのPCMを別々に対応づけ、各8,000フレームの2窓で正弦・余弦への射影を取る。単位はPCM振幅、時刻はフレーム、位相は度。マーカーの分数位相から求めた微小な時刻差で複素比を補正し、係数から計算した振幅と位相に照合する。19,845 Hzは振幅比約0.5、20,947.5 Hzは約0.015を予測した。連続する2試行、各窓の許容差、既定出力の復元を登録してから採取する。[事前登録](../cases/firefox-process-tap-headphone-response-44100.json)・[固定したFIR](../runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/summary.json)

### 振幅比と位相の実測

2試行ともWorkletの30,720標本が同じPCMで、独立に生成した信号と一致した。外部ヘッドフォンの公称レートと両観測点は44.1 kHz。各登録窓を覆うcubebの104要求は256フレーム、タップの53ブロックは512フレームで、予定サンプル時刻が連続していた。試行ごとに既定出力を元の内蔵スピーカーへ戻した。[第1試行の生データ](../runs/firefox-process-tap-headphone-response-44100-20261122-1/manifest.json)・[第2試行の生データ](../runs/firefox-process-tap-headphone-response-44100-20261122-2/manifest.json)

初回の振幅比は第1試行で登録内。前後の分数位相を平均した補正では、後マーカーの−0.193フレームが混ざり、19,845 Hzの結果を実際の整列位置から15.65°ずらした。第2試行は後マーカーが+0.418フレームで、登録した0.25フレームの範囲を外れた。両試行の不合格を保存し、同じ計測範囲を各1,000フレームの小窓へ等分する補足を登録した。各小窓の2,205 Hzの位相を時刻の基準に用い、波形の残差と位相基準のみで定常性を判定した。FIRモデルとの一致度は定常性の選別に使っていない。[第1試行の登録判定](../runs/firefox-process-tap-headphone-response-44100-20261122-1/summary.json)・[第2試行の登録判定](../runs/firefox-process-tap-headphone-response-44100-20261122-2/summary.json)・[補足ケース](../cases/firefox-process-tap-headphone-response-44100-pilot-review.json)

| 周波数 (Hz) | 固定FIRの振幅比 | 実測振幅比（タップ ÷ cubeb） | 位相差の最大絶対値 (°) |
| ---: | ---: | ---: | ---: |
| 2,205 | 1.000050 | 1.000000 | 0（補正の基準） |
| 17,640 | 1.000908 | 1.000000 | 0.000003 |
| 19,845 | 0.500408 | 0.500000 | 0.000010 |
| 20,947.5 | 0.015234 | 0.016351 | 0.000116 |

第1試行は16小窓すべて、第2試行は16小窓中13が定常。29小窓の振幅比は周波数ごとに同じ値となり、事前に登録したFIRの許容差に収まった。19,845 Hzは−6.02 dB、20,947.5 Hzは−35.73 dBだった。測定したのはタップまでの経路で、物理的なヘッドフォン出力の周波数応答は未計測。[第1試行の補足結果](../runs/firefox-process-tap-headphone-response-44100-20261122-1-pilot-review/summary.json)・[第2試行の補足結果](../runs/firefox-process-tap-headphone-response-44100-20261122-2-pilot-review/summary.json)

第2試行の最後の3小窓はタップの再構成残差が0.0287〜0.1673だった。定常な第1試行を共通の先行信号でそろえ、PCMを標本ごとに比べると、試験信号上の位置22,736で初めて2試行のタップに差が出た。第2試行の次のタップブロックは位置22,748、次のcubeb要求は位置22,784だった。後半2小窓では19,845 Hzの振幅比が0.01575〜0.01578、20,947.5 Hzは0.000441〜0.000453。後マーカーの分数位相を直線近似した傾きは第1試行で−47.1 ppm、第2試行で+56.5 ppmだった。符号と大きさは、マーカーに対するタップPCMの位相の傾きから求めている。試験音の途中に渡されたバッファの予定時刻は両試行で連続していた。後半の帯域低下と分数位相に共通の切替があるかは、同じ連続音の長い収録で切替の前後を同時に測る。[定常判定・後マーカーの時刻](../runs/firefox-process-tap-headphone-response-44100-20261122-2-pilot-review/summary.json)

### 再現と検算

Apple Silicon macOS 15.6.1、Xcode 26.2 (17C52)、計測用Firefox 157.0、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4。2試行を順番に実行し、タップは各4秒収録した。先行試験と同じFirefox・XUL・プロセスタップを、マニフェスト記録のSHA-256で確認した。新しい試験音は既存の計測ページにケースの指定があるときだけ挿入する。補足は保存されたPCMと時刻を使う。独立の検算ではステレオFloat32を展開して実FFTの4ビンから複素振幅比を求め、4成分での逆変換から小窓の再構成残差を再計算した。raw PCMで定常窓数、位相差、差が出る最初の標本、時計の連続性を確認した。上流のエンジン6試験と再実装の分割描画1試験が通過した。JavaScriptの構文を確認した。[収録入口](../tools/measure_firefox_headphone_response_44100.py)・[試験音を生成するページ](../../../../web/prototypes/chimera-research/tools/capture-firefox-output-marker.mjs)・[補足のマニフェスト](../runs/firefox-process-tap-headphone-response-44100-20261122-2-pilot-review/manifest.json)

```sh
firefox=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox
tap=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
for trial in 1 2; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 ../../.venv/bin/python tools/measure_firefox_headphone_response_44100.py "firefox-process-tap-headphone-response-44100-20261122-$trial" "$firefox" "$tap"
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_firefox_headphone_response_44100.py "firefox-process-tap-headphone-response-44100-20261122-$trial-pilot-review" "$firefox" "$tap" --case cases/firefox-process-tap-headphone-response-44100-pilot-review.json
done
```

各実行IDは事前登録と対応している。新たに収録する場合は収録と補足の対応を別のケースに登録する。


## 44.1 kHzの連続音を延ばして帯域と位相の変化を追う

固定上流の `AudioEngine.build` はHzを受けてAudioContextを開く。`ChimeraProcessor.process` はホストの量子幅をWASMに渡してエンジンを描画し、PCMを左右に複製してから処理負荷を更新する。WASMの `engine_render` は内部バッファで描画長を制限する。Rustの `Engine::render` は通算位置から制御更新の境界を選び、制御・発声・位置の加算の順に進める。上流のブロック幅の試験はイベントの軸をサンプル番号に固定し、ホスト幅を変えてもPCMが同じか検査する。今回はエンジンから独立した既知音を同じ出力経路へ通す。計測用cubebはAudioUnitへ返す直前のバッファと予定サンプル番号を、Core Audioのタップは同じPIDのステレオFloat32と時刻を記録する。[上流グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[cubebの記録](../tools/chimera-cubeb-output-snapshot.patch#L237)・[タップの記録](../tools/chimera_process_tap.swift#L121)

44.1 kHz・同じ外部ヘッドフォンで同じ4周波数を使い、純音区間を18,048から49,152フレームへ延ばす。既存のFirefoxのPCM採取上限256要求、1 MiBに収める。前マーカーで2経路の整数位置を固定し、後マーカーの分数位相は観測値として残す。各400フレーム窓で複素振幅比を求め、200フレームずつ送る。2,205 Hzの伝達位相をアンラップして `位相 ÷ (2π × 2,205 / 44,100)` からフレーム単位の進み遅れを求め、その差分からppmを算出する。19,845 Hzの振幅比が0.20未満、傾きが20 ppm超となる状態をそれぞれ4窓連続で探す。3試行のうち2試行以上で持続する帯域低下を予測し、低域位相の傾きとの距離を512フレーム以内と予測する。候補の時刻と失敗を保存し、別収録の40標本周期と直接比べて最初に異なる波形を確認する。[事前登録](../cases/firefox-process-tap-headphone-drift-44100.json)・[短い試行の変化](../runs/firefox-process-tap-headphone-response-44100-20261122-2-pilot-review/summary.json)

### 長い収録で確認した変化

3試行のWorkletの61,440フレームはビット一致し、独立に生成した試験音にも一致した。回復用の後マーカーも含む対象区間で、毎回cubebの256フレーム要求224件とタップの512フレームブロック113件が連続し、両方の予定サンプル番号に飛びはなかった。各試行の229小窓のうち最初の4窓では、19,845 Hzの振幅比が約0.500だった。予測した持続的な帯域低下は3回すべてで現れた。[第1試行](../runs/firefox-process-tap-headphone-drift-44100-20261122-1/summary.json)・[第2試行](../runs/firefox-process-tap-headphone-drift-44100-20261122-2/summary.json)・[第3試行](../runs/firefox-process-tap-headphone-drift-44100-20261122-3/summary.json)

| 試行 | 波形が初めて変わった標本 | 位相の傾きが最初に閾値を超えた窓中心 | 帯域低下を最初に検出した窓中心 | 帯域低下までの追加時間 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 25,087 | 25,216 | 39,816 | 331.07 ms |
| 2 | 22,480 | 22,616 | 22,616 | 0 ms |
| 3 | 22,224 | 22,416 | 22,416 | 0 ms |

試行1の波形変化は、cubeb要求の先頭から255標本、タップブロックの先頭から191標本後。試行2・3では、それぞれcubeb要求内の位置208で始まり、タップブロック内では位置303と86だった。3件とも予定サンプル番号は変化点の前後で連続していた。時刻の推定は各ブロックのホスト時刻にブロック内のフレーム数を44,100 Hzで換算して加えた。両観測点のこの相対時刻は約28.5 msで、アナログ出力を基準にした遅延は計測していない。[イベントとブロック時刻](../runs/firefox-process-tap-headphone-drift-44100-20261122-1/summary.json)

第1試行は傾きが負になったあとも振幅比0.5付近を保った。約331 ms後に傾きが正へ変わり、そこで帯域が低下した。最初に位相が動いた時刻と帯域低下の時刻が512フレーム以内という予測は3試行中2回で成立した。補足の探索として同じ0.20の閾値を全窓に適用すると、最初に帯域が低下してから戻るまでの間隔は約327〜331 ms。試行2と3ではその後に再度低下した。これは今回の長さと環境で観測した範囲で、周期の再現性は未確認。[全小窓の系列](../runs/firefox-process-tap-headphone-drift-44100-20261122-2/summary.json)

### ホスト時計の傾きとの補足比較

3試行の判定を保った上で、帯域と位相の傾きが一定の区間を同じ条件で扱った。19,845 Hzの比が0.20未満または0.40以上、2,205 Hzの位相の傾きが絶対5 ppm以上の窓を、帯域と傾きの符号で連結する。12窓以上続いた区間の両端から3窓ずつ除いた。タップとcubebのブロック開始フレームをそれぞれのホスト時刻に回帰し、`(タップの1フレーム時間 − cubebの1フレーム時間) / 公称1フレーム時間` のppmを求めた。この量がPCMから得た位相オフセットの傾きと一致するか、判定前に許容差0.5 ppmを登録した。[補足のケース](../cases/firefox-process-tap-headphone-drift-44100-clock-plateaus.json)・[区間別の結果](../runs/firefox-process-tap-headphone-drift-44100-clock-plateaus-20261122-b/summary.json)

| 試行 | 19,845 Hzの比の中央値 | PCMから求めた傾き (ppm) | ホスト時計差 (ppm) | 両者の差 (ppm) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.49972 | −46.702 | −46.700 | −0.002 |
| 1 | 0.01547 | +44.851 | +44.883 | −0.033 |
| 2 | 0.01574 | +56.245 | +56.238 | +0.008 |
| 2 | 0.49976 | −32.905 | −32.919 | +0.014 |
| 2 | 0.01552 | +20.793 | +21.584 | −0.791 |
| 3 | 0.01574 | +56.056 | +56.079 | −0.023 |
| 3 | 0.49976 | −33.142 | −33.173 | +0.031 |
| 3 | 0.01552 | +20.675 | +21.379 | −0.705 |

8区間のすべてで、振幅比約0.0155のときは正、約0.5のときは負だった。比較的長い6区間は時計差と位相の傾きが0.033 ppm以内で一致した。末尾2区間はそれぞれ1,600・2,000標本分で、タップの開始時刻が3点・4点しかなく、差は0.791・0.705 ppmと基準を超えたため、全区間の判定は不合格。クロック1 tickは約41.7 nsで、短区間で生じた傾きの推定差の要因は確認が残る。時計の回帰はcubeb側の傾きに大きな変化があり、タップ側は全区間で公称値から0.52 ppm以内だった。帯域の変化がどの処理段で生じるかは、同じ機器・サンプルレートでネイティブのcubebプローブを使い、ブラウザを経由する収録と比較する。[補足のマニフェスト](../runs/firefox-process-tap-headphone-drift-44100-clock-plateaus-20261122-b/manifest.json)

### 再現と検算

macOS 15.6.1のApple Silicon、Xcode 26.2、計測用Firefox 157.0、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4。前回と同じFirefox・XUL・タップをSHA-256で照合して使用した。既定出力は各試行の後に内蔵スピーカーに戻した。独立の検算ではステレオPCMから実FFTの4ビンを読み出し、全687窓の複素比、位相の傾き、波形変化の標本、タップとcubebのブロック位置を確認した。補足の時計値は標準ライブラリの直線回帰で検算した。補足の初回はブロックCSVのファイル名をディレクトリとして渡したため、計測前に停止した。パスを直し、別IDで実行した。上流6試験・再実装1試験と、計測JavaScriptの構文検査を通過した。実体はRTL9210B-CGに保存した。[長い収録のコード](../tools/measure_firefox_headphone_drift_44100.py)・[時計比較のコード](../tools/measure_firefox_headphone_clock_plateaus_44100.py)

```sh
firefox=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-44100-20261122-link/build-dist.app/Contents/MacOS/firefox
tap=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
for trial in 1 2 3; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 ../../.venv/bin/python tools/measure_firefox_headphone_drift_44100.py "firefox-process-tap-headphone-drift-44100-20261122-$trial" "$firefox" "$tap"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_firefox_headphone_clock_plateaus_44100.py firefox-process-tap-headphone-drift-44100-clock-plateaus-20261122-b
```

記録済み収録の時計だけを再解析する場合は、最後のコマンドの出力実行IDを変える。


## 44.1 kHzの帯域変化をネイティブcubebで比較する

固定したCHIMERA上流の `AudioEngine.build` はHzでサンプルレートを指定し、`ChimeraProcessor.process` がホストの要求幅をWASMに渡す。WASMは描画幅を内部バッファ長に制限し、Rustの `Engine::render` は通算位置から制御境界を決め、制御更新、発声の描画、位置の加算の順で実行する。上流のエンジン試験はイベントの標本位置を固定して外側の要求幅を変え、PCMのビット一致を確認する。今回の直接出力では同じブラウザ計測用PCMをファイルから読み、固定cubebの出力コールバックに渡す。Rustプローブの `render` は通算出力フレームを保持し、モノラルFloat32から `[x, −x]` を書き込んで描画済みフレーム数を返す。AudioUnitに返す出力バッファのPCM・フレーム数と予定標本・ホスト時刻をcubebで記録し、同じPIDをCore Audioのプロセスタップで収録する。[上流グラフ](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[上流Worklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[WASM](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[Rust](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[ネイティブのプローブ](../tools/chimera-cubeb-output-probe.rs#L26)・[出力バッファの記録](../tools/chimera-cubeb-output-snapshot.patch#L237)・[タップ](../tools/chimera_process_tap.swift#L121)

44.1 kHzの同じ外部ヘッドフォン、ブラウザで保存した61,440フレームの信号、同じ逆相と4周波数を使う。プローブは256フレームを要求し、実際のcubeb・タップ・デバイスの幅は別に確かめる。ネイティブ3試行で19,845 Hzが最初に0.5付近、少なくとも1回は比0.20未満に低下すると予測する。ブラウザ長時間収録と同じ400フレーム・200フレーム刻みの窓と検出条件を使う。帯域と位相の変化の検出を、レート・時計・PCMの照合から独立した判定として保存する。[事前登録](../cases/native-cubeb-headphone-drift-44100.json)・[ブラウザの照合](../runs/firefox-process-tap-headphone-drift-44100-20261122-1/summary.json)

### ネイティブのPCM採取

既存のプローブで44.1 kHzの再生とタップ採取はできたが、計測用cubebには48 kHzのストリームとバッファだけを記録する条件があり、3回ともcubeb PCMが欠測した。固定cubeb `840f69c1b3f95accd582555e10abcef8ee67514b` の別ビルドで、ストリームとバッファの記録レートの照合だけを44.1 kHzに変えた。プローブの描画処理、バックエンドの本体、Cargo.lockは同一。旧ビルドと各収録を保存した。[旧ビルドの収録](../runs/native-cubeb-headphone-drift-44100-20261122-1/manifest.json)・[44.1 kHzの記録差分](../tools/chimera-cubeb-output-snapshot-44100.patch)・[変更後の収録](../runs/native-cubeb-headphone-drift-44100-20261122-snapshot-1/manifest.json)

変更後は3回ともcubebのPCMが得られた。タップの後マーカーの窓が61,440フレームのPCMを繰り返す境界まで含み、前端は一致したが後端の残差が基準を外れた。整数フレーム位置を拘束して後窓全体で分数遅延を合わせた残差は約0.035。信号の区間、窓幅、比較閾値を保ち、後マーカーだけを1,024フレーム手前の59,392〜60,415に移した補足では残差が約0.00089に収まった。記録された形式は44.1 kHz・2チャンネル・Float32を受け付ける専用ビルドのハッシュと `state.txt` の `ready` で照合した。[元の採取判定](../runs/native-cubeb-headphone-drift-44100-20261122-snapshot-1/summary.json)・[後マーカーの補足ケース](../cases/native-cubeb-headphone-drift-44100-tail-review.json)・[補足の結果](../runs/native-cubeb-headphone-drift-44100-20261122-snapshot-1-tail-review-verified/summary.json)

### ブラウザを経由しない出力の結果

同じ外部ヘッドフォンの公称レートは44.1 kHz、使用中の機器バッファは512フレーム。各試行では補足の照合窓に、cubebの256フレーム要求が220件、タップの512フレームブロックが111件あった。cubebが返した先頭61,440フレームは3回とも、保存したFirefoxのPCMと左右両方でビット一致した。試験音は2,205・17,640・19,845・20,947.5 Hz、純音区間は49,152フレーム。比較の全229小窓で窓幅400と移動幅200フレームを使用した。両観測点の予定サンプル番号は連続した。[第1試行](../runs/native-cubeb-headphone-drift-44100-20261122-snapshot-1-tail-review-verified/summary.json)・[第2試行](../runs/native-cubeb-headphone-drift-44100-20261122-snapshot-2-tail-review-verified/summary.json)・[第3試行](../runs/native-cubeb-headphone-drift-44100-20261122-snapshot-3-tail-review-verified/summary.json)

| 試行 | タップPCMが最初に変わった位置 | 帯域低下・低域位相変化の検出窓中心 | 最初の定常区間の19,845 Hz振幅比 | 低下後の振幅比の中央値 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 27,344 | 27,416 | 0.50000 | 0.0157385 |
| 2 | 27,088 | 27,216 | 0.50000 | 0.0157363 |
| 3 | 27,344 | 27,416 | 0.50000 | 0.0157376 |

3回とも高域の低下と位相の変化を同じ窓で検出した。初めて波形が変わった位置は3回ともcubeb要求内の208フレーム目で、次の要求の48フレーム手前だった。同じ位置をタップブロック上で数えるとそれぞれ273、416、507フレーム目だった。広帯域に戻った区間の19,845 Hzの振幅比は約0.49976。ネイティブでは3回とも先行する位相変化を伴わずに帯域が低下した。ブラウザの3回では1回で位相の変動が約331 ms先行した。[ブラウザ側の3試行](../runs/firefox-process-tap-headphone-drift-44100-clock-plateaus-20261122-b/summary.json)

### 時計の照合と残る差

ブラウザ側と同じ区間選択で切替の両端を除き、6つの定常区間を比較した。狭い帯域では2,205 Hzの位相の傾きが+56.06〜+56.53 ppm、広い帯域では−32.76〜−32.43 ppmだった。ホスト時刻から独立に求めた時計差との誤差は6区間とも0.02735 ppm以内で、登録した0.5 ppm基準に収まった。前後マーカーで比較すると、試験中にタップの相対位相は+0.425〜+0.433フレームまで進んだ。ブラウザ側と同じ符号・同程度の時計差と、高域の減衰・回復がネイティブの出力でも現れた。検証範囲はプロセスタップまでで、cubebより下のどの機構で変化したか、アナログのヘッドフォン出力も同じかは未確定。[区間別時計比較](../runs/native-cubeb-headphone-drift-44100-clock-plateaus-20261122-a/summary.json)

### 再現と検算

macOS 15.6.1 arm64、Xcode 26.2 (17C52)、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。固定cubebの既存作業ツリーは保持し、別ディレクトリにコピーした。初回のビルドでは既存のビルド指定を付けずにCMake内のCargoが待機したため、そのビルドだけを停止し、既存手順のフラグとオフライン指定で再開した。旧型の記録器には `format.csv` が印字されないため、確認した記録レートの制約と各実行の状態をマニフェストに残した。後マーカーをずらす補足の初回は解析コードの変数名の衝突と移動した変数の参照で中断した。元の収録を使ったまま、修正後の結果は別の実行IDに記録した。[ネイティブ比較の入口](../tools/measure_native_cubeb_headphone_drift_44100.py)・[最終マニフェスト](../runs/native-cubeb-headphone-drift-44100-20261122-snapshot-3-tail-review-verified/manifest.json)

独立検算は生PCMの実FFTを使い、左右のビット一致、全687小窓の複素比、イベントのブロック内位置、両方の予定番号の連続性を確かめた。時計差は標準ライブラリの直線回帰で再計算した。上流のエンジン6試験と再実装の分割描画1試験は通過。収録と再解析の実体はRTL9210B-CGに置き、収録後は内蔵スピーカーへ復元した。

```sh
storage=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output
stage="$storage/native-44100-probe-20261122"
test ! -e "$stage" && cp -R "$storage/cubeb-coreaudio-rs" "$stage" &&
  git -C "$stage" apply "$PWD/tools/chimera-cubeb-output-snapshot-44100.patch"
DOCS_RS=1 MACOSX_DEPLOYMENT_TARGET=15.0 CMAKE_TOOLCHAIN_FILE="$storage/coreaudio-only.cmake" \
  CARGO_NET_OFFLINE=true CARGO_HOME="$storage/cargo-home" CARGO_TARGET_DIR="$stage/target" \
  cargo build --locked --offline --release --example chimera-paired-output-probe --manifest-path "$stage/Cargo.toml"
probe="$stage/target/release/examples/chimera-paired-output-probe"
tap=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
for trial in 1 2 3; do
  id="native-cubeb-headphone-drift-44100-20261122-snapshot-$trial"
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=100000000 ../../.venv/bin/python tools/measure_native_cubeb_headphone_drift_44100.py "$id" "$probe" "$tap" --case cases/native-cubeb-headphone-drift-44100-snapshot.json
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_native_cubeb_headphone_drift_44100.py "$id-tail-review" "$probe" "$tap" --case cases/native-cubeb-headphone-drift-44100-tail-review.json --output-run-id "$id-tail-review-verified"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python tools/measure_firefox_headphone_clock_plateaus_44100.py native-cubeb-headphone-drift-44100-clock-plateaus-20261122-a --case cases/native-cubeb-headphone-drift-44100-clock-plateaus.json
```

同じ収録から再解析する場合は `--output-run-id` に新しい実行IDを指定する。

### 44.1 kHzの帯域変化をCore Audioの直接出力で比較する

固定上流の `processor.ts` の `process()` は出力チャンネルの長さを標本数として `engine_render()` に渡し、Wasmの連続したFloat32を先頭チャンネルへコピーする。ほかのチャンネルも同じ出力を受ける。`chimera-wasm/src/lib.rs` の `engine_render()` は確保済みの出力領域で `Engine::render()` を呼ぶ。本体は累積標本番号 `pos` の内部ブロック境界でシーケンサを発声時計の秒単位で進め、現在の声に標本数を渡してから `pos` を加算する。上流の `output_does_not_depend_on_the_host_block_size` は、同じ絶対標本番号で命令を適用したセッションを1・77・128・4096・48000標本の分割で比較する。今回の試験音は診断用の固定PCMで、先行ブラウザ収録から取り出した同じ61,440標本を使用する。[上流のWorklet](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[Wasmの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L176)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[ブロック分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

直接出力プローブは `run()` で `DefaultOutput` に44,100 HzのステレオFloat32を設定する。入力を求めるコールバックで `OutputProbe.write()` がバッファを検査し、`OutputPCM.write()` が累積フレーム `written` をもとに左右へ `[x,-x]` を書く。コールバックに渡る予定サンプル番号とホストtick、実際の入口時刻と書いた時刻を保持し、停止後にPCMとJSONを保存する。今回の設定では待機を追加せず、減衰を挿入するコールバック番号は収録の末尾より後、戻り値は常に0。採取の配置と時計はcubebの記録器と独立して確認する。開始位相と帯域の低下が直接出力にも現れると事前登録した。[直接出力のソース](../tools/chimera_output_deadline_probe.swift)・[試行と判定基準](../cases/coreaudio-headphone-drift-44100.json)

#### 収録と判定

3試行で機器、直接出力、タップの幅は512フレーム。比較区間に直接出力の要求110件とタップの要求111件があり、いずれも予定標本番号は連続した。先頭61,440フレームの左右は、それぞれブラウザの保存PCMとその符号反転にビット一致した。元の解析はFloat64へ変換済みの配列を32ビット整数と見なして比較したため、3試行ともPCM照合だけが不合格だった。生のFloat32をバイト列で照合し直す補足を登録し、初版の判定と収録を残した。端点や比較窓、閾値は初版の値を引き継いだ。[採取と解析の入口](../tools/measure_coreaudio_headphone_drift_44100.py)・[初版](../runs/coreaudio-headphone-drift-44100-20261122-1/summary.json)・[補足ケース](../cases/coreaudio-headphone-drift-44100-raw-review.json)

3試行とも、最初の窓の2,205・17,640・19,845・20,947.5 Hzのタップ/直接出力の比は1.00000・1.00000・0.50000・0.01635。帯域低下と正の位相傾斜の立ち上がりを検出した窓の中心は、3回ともフレーム27,216だった。定常40標本周期との波形差は3回ともフレーム27,088で始まり、直接出力コールバック先頭から464標本後、次の要求の48標本手前にあたる。タップ側ブロック内の位置は448・22・331と試行ごとに異なる。先行ネイティブcubebでも256フレームの要求境界の48標本手前で差が始まっていた。[第1試行](../runs/coreaudio-headphone-drift-44100-20261122-1-review/summary.json)・[第2試行](../runs/coreaudio-headphone-drift-44100-20261122-2-review/summary.json)・[第3試行](../runs/coreaudio-headphone-drift-44100-20261122-3-review/summary.json)

| 直接出力の試行 | 19,845 Hzの振幅比の中央値（低下時 → 回復後） | 2,205 Hzの位相傾斜（低下時 → 回復後、ppm） | 位相とホスト時計差の最大誤差（ppm） |
| --- | --- | --- | --- |
| 1 | 0.015733 → 0.499760 | +56.624 → −32.431 | 0.08192 |
| 2 | 0.015742 → 0.499762 | +56.434 → −32.289 | 0.05255 |
| 3 | 0.015732 → 0.499762 | +56.056 → −32.384 | 0.01153 |

先行ケースと同じ方法で、端の3窓ずつを除いて `(タップのns/標本 − 直接出力のns/標本) ÷ (10⁹/44100) × 10⁶` を求めた。タップの時計は公称値から±0.043 ppm以内で、直接出力の時計は振幅比が低い区間で−56.66〜−56.08 ppm、回復した区間で+32.31〜+32.39 ppmだった。6区間すべてで位相傾斜と時計差が登録基準0.5 ppm以内で一致した。ブラウザとcubebを含まない経路でも帯域と時計の関係を観測できた。比較の範囲は直接出力コールバックからプロセスタップまでで、Core Audio内の処理段とアナログ出力は未確認。次の対照では同じPCMの前へ1,024フレームの無音を加え、最初の波形差を再生開始と信号開始の両方から測る。[時計のケース](../cases/coreaudio-headphone-drift-44100-clock-plateaus.json)・[区間別の時計](../runs/coreaudio-headphone-drift-44100-clock-plateaus-20261122-a/summary.json)

#### 検算と再実行

macOS 15.6.1 arm64、Xcode 26.2 (17C52)、Python 3.14.4、NumPy 2.4.4。生PCMの整数ビット、全687窓の実FFTの4ビン、40標本周期との最初の差、開始時刻、タイムスタンプの連続性を独立に照合した。複素比の最大差は約 `1.06e-14`。生時計とFFT位相を標準ライブラリの直線回帰でも検算し、集約との傾きの差は `3.3e-10` ppm以下。固定上流のエンジン6試験と再実装の分割描画1試験が通過。従来のcubeb時計集約の再実行は先行の要約とバイト一致した。8実行の254入力・59出力をハッシュで確認し、外部に書いた出力は7,370,257バイト。各収録後に元の内蔵スピーカーを復元した。[従来ケースの再実行](../runs/native-cubeb-headphone-drift-44100-clock-plateaus-20261122-coreaudio-regression/manifest.json)・[時計集約のマニフェスト](../runs/coreaudio-headphone-drift-44100-clock-plateaus-20261122-a/manifest.json)

```sh
tap=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
for trial in 1 2 3; do
  id="coreaudio-headphone-drift-44100-20261122-$trial"
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=20000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$id" "$tap"
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$id-review" --review
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_firefox_headphone_clock_plateaus_44100.py coreaudio-headphone-drift-44100-clock-plateaus-20261122-a --case cases/coreaudio-headphone-drift-44100-clock-plateaus.json
```

同じ名前の実行は既に保存している。再収録ではケースに新しい試行IDを登録する。初版の不合格を再現するには各収録の `source/` に保存した測定コードを使う。

### 44.1 kHzの試験音の前に無音を挿入する

上流の `AudioEngine.build()` はステレオの `AudioWorkletNode` を構築し、`process()` は要求幅を `engine_render()` に渡す。Wasmの入口は確保済みのFloat32出力を使い、Rustの `Engine::render()` は描画した標本数を `pos` に足す。テストの `session()` は `pos` に対応する絶対標本番号で命令を注入し、`output_does_not_depend_on_the_host_block_size` で分割後のビット一致を確認する。今回は合成器が生成した値と出力側を切り分けるため、前回と同じ診断用のPCMファイルを直接出力する。[Workletの作成](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L116)・[描画の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

直接出力の `OutputPCM.write()` は累積出力フレーム `written` でファイルを参照し、モノラルのFloat32を左右逆相で書いてから `written` を増やす。PCMファイルに無音2ブロックを足しても、デバイスの開始手順、要求幅、採取時間は同じにする。出力先頭からの位置を `n`、試験信号の先頭からの位置を `s`、先頭の無音長を `L` として `n = s + L` とする。前後のマーカーと小窓は `s` 上で固定する。3組を収録順を入れ替えて測り、初回の波形差、帯域低下、位相の変化の座標を比較する。[直接出力の描画](../tools/chimera_output_deadline_probe.swift)・[事前登録](../cases/coreaudio-headphone-drift-44100-leading-silence.json)

6回とも44.1 kHzで、直接出力とタップは512フレーム。無音ありの先頭1,024フレームは左右それぞれ正のゼロと負のゼロで、続く61,440フレームは無音なしの入力と左右ともビット一致した。固定した40標本周期との最初の波形差は、全6回で出力フレーム27,088、次の出力要求の48フレーム手前だった。タップのブロック内位置は207〜457の範囲で変動した。最初の出力要求の予定ホスト時刻を0とした場合、波形差の位置を含むブロックから約614.240 msと求まった。[全6回の比較](../runs/coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-a/summary.json)

| 先頭の無音 | 波形差の開始（試験信号基準 / 出力基準、フレーム） | 帯域低下と正の位相傾斜を初めて検出した窓の中心（試験信号基準 / 出力基準、フレーム） |
| --- | --- | --- |
| 0フレーム | 27,088 / 27,088 | 27,216 / 27,216 |
| 1,024フレーム | 26,064 / 27,088 | 26,216 / 27,240 |

3組とも最初の差は信号開始を基準に1,024フレーム早まり、出力時刻は同じだった。帯域と位相を検出した窓は出力基準で24フレームずれた。分析窓は試験信号基準で200フレームごとに置く。1,024を200で割った余りが24なので、検出窓の差は出力上の窓の配置のずれと同じ幅だった。24フレーム単位で実際の切替時刻を比較するには、出力基準で窓を揃えた測定が要る。[無音ありの第1試行](../runs/coreaudio-headphone-drift-44100-leading-silence-1/summary.json)・[同じ組の無音なし](../runs/coreaudio-headphone-drift-44100-leading-control-1/summary.json)

19,845 Hzの振幅比は全試行で0.50000付近から0.01573付近へ低下し、約0.49976へ回復した。6試行各2区間で、低下中の位相傾斜は+56.06〜+57.00 ppm、回復後は−32.95〜−32.12 ppm。ホスト時計差との誤差は最大0.05213 ppmだった。タップの最初の予定ホスト時刻から直接出力の最初の予定ホスト時刻までの差は296.52〜302.19 ms。次の対照はタップ準備後に出力を始めるまでの待機だけを延ばし、両方の開始時計を基準に波形差の位置を追う。Core Audioでどの処理段が変化したか、アナログの出力に現れるかは未確認。[区間別の時計と振幅](../runs/coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-a/summary.json)

環境は前回と同じmacOS 15.6.1 arm64、Xcode 26.2、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4。生PCMから先頭の無音と原信号のビット、1,374窓の実FFTの複素比、最初の波形差、予定標本番号とホスト時刻を独立に確認した。FFTの複素比の最大差は約 `1.07e-14`、標準ライブラリの直線回帰との誤差は `4.9e-10` ppm以下。既存の直接出力3収録の結果は、変更後の解析で全項目一致した。固定上流エンジン6試験と再実装の分割描画1試験が通過。7実行の218入力・109出力のサイズとSHA-256を照合し、音声・時刻・ビルドの実体計14,752,741バイトをRTL9210B-CGへ保存した。各試行後の既定出力は元の内蔵スピーカーだった。[集約のマニフェスト](../runs/coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-a/manifest.json)

```sh
case_path=cases/coreaudio-headphone-drift-44100-leading-silence.json
tap=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
jq -r '.trials[].run_id' "$case_path" | while IFS= read -r trial; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$trial" "$tap" --case "$case_path"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/compare_coreaudio_headphone_leading_silence_44100.py coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-a
```

既存の収録を使って集約だけをやり直すときは、最後の行の実行IDを変える。

### 44.1 kHzでタップの先行時間を変える

固定上流では `AudioEngine.build()` が出力レートを持つ `AudioContext` にステレオの `AudioWorkletNode` を接続する。 `process()` が1チャンネル分の標本数を指定し、Wasmの `engine_render()` が確保済みのFloat32領域を返す。 `Engine::render()` は累積標本数 `pos` を内部ブロックに合わせて進め、テストの `output_does_not_depend_on_the_host_block_size` は同じ絶対標本で命令を適用すると呼び出し幅によらず同じPCMになることを確認する。今回も固定した診断PCMを直接出力し、両計測点の時計を比較する。[上流の出力準備](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[描画の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[分割幅の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

タップは `AudioDeviceStart()` の後に準備完了ファイルを出し、入力コールバックに渡る `sampleTime` と `hostTime` を記録する。 `capture()` はそのファイルを確認してから、指定の待機の後に1バイトを直接出力プローブへ送る。プローブはその通知の直後に `AudioOutputUnitStart()` を呼び、出力コールバックごとの `sampleTime`、`hostTime`、出力済みフレーム数を記録する。両者の先頭ブロックの `hostTime` をtickからmsに換算し、差を出力の遅れとして扱う。波形差の時刻はそれぞれのブロックの予定時刻にブロック内フレーム数を44,100 Hzで割った時間を加える。待機の設定値と実際の開始間隔を両方保存する。[タップの準備](../tools/chimera_process_tap.swift#L153)・[待機と通知](../tools/measure_coreaudio_output_error_pcm.py#L51)・[直接出力の開始](../tools/chimera_output_deadline_probe.swift#L278)・[事前登録](../cases/coreaudio-headphone-drift-44100-tap-wait.json)

100 msと350 msの比較では、全6回でPCMと時計の採取条件を通過した一方、最初の予定時刻同士の間隔は長い待機で55〜57 ms縮まった。登録した増分180〜340 msを満たす組はなかった。収録に含まれる時計の基準を読み返し、タップ開始API直前の基準から出力開始API直前の基準までの時間と、最初の予定時刻の間隔を区別した。待機を1,100 msに伸ばす補足を、次の収録前に登録した。[初版の判定](../runs/coreaudio-headphone-drift-44100-tap-wait-pairs-20261122-a/summary.json)・[待機を長くした補足ケース](../cases/coreaudio-headphone-drift-44100-tap-wait-extended.json)

#### 採取と開始時刻の比較

0.10・0.35・1.10秒の待機で、全12回の入力PCMはブラウザの61,440フレームと左右ともビット一致した。ヘッドフォンと出力は44.1 kHzで、直接出力とタップの採取幅は512フレーム。タップ開始API直前の基準から出力開始API直前の基準までの間隔は、追加した待機に応じて約0.25秒と約1秒延びた。ところが、タップの最初の予定時刻も、同じタップ開始API直前の基準に対して遅くなった。[初版の時計の再集約](../runs/coreaudio-headphone-drift-44100-tap-wait-pairs-20261122-review/summary.json)・[補足の時計と判定](../runs/coreaudio-headphone-drift-44100-tap-wait-extended-pairs-20261122-a/summary.json)

| 待機の変更 | 開始API直前の時計間隔の変化 | 最初のタップの予定時刻の変化（タップ開始API直前から測定） | タップと出力の最初の予定時刻の間隔の変化 |
| --- | --- | --- | --- |
| 100 → 350 ms | +243.21〜+254.50 ms | +199.21〜+209.23 ms | −56.73〜−55.35 ms |
| 100 → 1,100 ms | +999.57〜+1,006.90 ms | +919.87〜+931.98 ms | −29.70〜−21.20 ms |

出力開始API直前の基準から最初の出力コールバックの実際の入口までの時間も、待機100 msでは378.43〜380.19 ms、350・1,100 msでは278.08〜280.93 msと約100 ms異なった。最初の出力コールバックの入口からブロックに付いた予定ホスト時刻までは全試行で約13.1 msだった。開始APIへの待機と最初の予定ホスト時刻の間隔を別に記録すると、待機の変更が一方の開始時刻だけに伝わらなかったことを確かめられる。事前に定めた開始間隔の増分を満たす組は6組ともなく、開始基準を判別する比較は両ケースとも不成立だった。[時計の集約](../tools/compare_coreaudio_headphone_tap_wait_44100.py)

全12回で波形差の出力位置は27,088、最初の出力要求の予定時刻から約614.240 ms。19,845 Hzの振幅比の低下と正の位相傾斜の検出窓は、どちらも出力フレーム27,216を中心とする窓だった。タップの最初の予定時刻から波形差までの時間は、各組で最初の予定時刻の間隔の変化に0.020 ms以内で追従した。これは実測した時間差を使った記述で、事前の開始間隔の増分を満たした判定とは区別する。帯域が狭い時期と回復した時期の24区間では、位相傾斜と時計差が最大0.08958 ppmの差で一致した。[初回の短い待機](../runs/coreaudio-headphone-drift-44100-tap-wait-short-1/summary.json)・[1,100 msの第1試行](../runs/coreaudio-headphone-drift-44100-tap-wait-extended-long-1/summary.json)

次の対照は、既に継続出力中の同じプロセスへ後からタップを取り付ける。出力の対象プロセスとPCMを固定し、最初のタップの時刻を出力フレーム27,088より後ろへ持っていけるか確認した上で、取り付け時点から同じ帯域変化が再発するか測る。Core Audio内の処理段とアナログ出力は未確認。

#### 検算と再実行

macOS 15.6.1 arm64、Xcode 26.2、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4。生のFloat32と12回分の2,748窓の実FFTでビット、振幅、位相、最初の波形差を独立に再計算した。複素比の最大差は約 `1.07e-14`。生のhostTimeとFFT位相を標準ライブラリの直線回帰で確認し、傾斜の計算は集約と `4.9e-10` ppm以内で一致した。固定上流のエンジン6試験と再実装の分割描画1試験が通過し、先頭無音の比較を同じデータで再実行した要約はバイト一致した。17実行の535入力・221出力のサイズとSHA-256を照合し、測定データとビルドの実体28,236,623バイトをRTL9210B-CGに保存した。元の既定出力は全試行後に復元した。[先頭無音の回帰](../runs/coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-timestamps-regression/manifest.json)・[長い待機でのマニフェスト](../runs/coreaudio-headphone-drift-44100-tap-wait-extended-pairs-20261122-a/manifest.json)

```sh
tap_app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
for suffix in '' -extended; do
  experiment="coreaudio-headphone-drift-44100-tap-wait$suffix"
  trial_case="cases/$experiment.json"
  jq -r '.trials[].run_id' "$trial_case" | while IFS= read -r trial; do
    CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$trial" "$tap_app" --case "$trial_case"
  done
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/compare_coreaudio_headphone_tap_wait_44100.py "$experiment-pairs-20261122-a" --case "$trial_case"
done
```

保存済みの結果を再集約するときは、集約の行に新しい実行IDを指定する。両集約の終了コード1は時計の開始間隔の判定を反映している。

### 44.1 kHzの継続出力に後からタップを接続する

固定上流では `AudioEngine.build()` が `sampleRate` を指定してステレオ出力のWorkletを作る。 `process()` の要求幅が `engine_render()` に渡り、Float32の出力領域がチャンネルへコピーされる。Rustの `Engine::render()` は `pos` から内部の境界を決め、描画してから累積フレームを進める。 `output_does_not_depend_on_the_host_block_size` は絶対フレームを揃えた呼び出しの分割を比較する。通常の発声の出力と切り分けて、今回も同じ既知PCMをCore Audioの `DefaultOutput` から再生する。[出力の構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[Workletの描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Pythonの `capture()` がバイト1を送ると出力プローブが再生を始める。タップは対象PIDを指定した上で別プロセスから `AudioDeviceStart()` を呼ぶ。先行接続はタップ準備完了から100 ms後に出力へ通知し、後からの接続は出力への通知を先に済ませて1.38秒後にタップを起動する。登録した判定には制御側の待機と実際の開始時刻を区別し、両方の最初の予定ホスト時刻と標本番号を使う。[直接出力の開始](../tools/chimera_output_deadline_probe.swift#L278)・[タップの開始](../tools/chimera_process_tap.swift#L153)・[比較の事前登録](../cases/coreaudio-headphone-drift-44100-late-attach.json)

#### 帯域低下と位相の比較

共通の入力は先頭55,216フレームをブラウザ収録とビット一致させ、続けて位相を揃えた4周波数の40フレーム周期を反復した。先行接続はフレーム4,096のマーカー、後から接続した場合はフレーム122,880と125,952のマーカーを照合して位置を決めた。両条件で直接出力とタップは512フレーム幅で、予定サンプル番号は比較区間で連続した。後から接続したタップの最初の予定ホスト時刻は、先行試行で波形差が始まる出力フレーム27,088の予定時刻より1.028〜1.042秒後にあった。使用可能な純音の観測を各1.025〜1.034秒確保した。[収録と解析](../tools/measure_coreaudio_headphone_late_attach_44100.py)・[全試行の集約](../runs/coreaudio-headphone-drift-44100-late-attach-pairs-20261122-a/summary.json)

| タップの接続順 | 最初の帯域低下の窓中心（出力フレーム） | 最初のタップの予定時刻から帯域低下の窓中心まで | 低下直後の19,845 Hzの振幅比の中央値 | 同じ区間の2,205 Hzの位相傾斜 |
| --- | --- | --- | --- | --- |
| 出力の前 | 27,216 | 939.23〜953.42 ms | 0.015732〜0.015742 | +55.96〜+56.24 ppm |
| 出力の後 | 85,616 | 320.02〜333.47 ms | 0.015525〜0.015527 | +26.88〜+27.02 ppm |

先行接続では波形差が出力フレーム27,088で始まり、3回とも同じ分析窓で帯域低下と正の位相傾斜を検出した。後から接続した場合にも3回とも帯域低下が生じ、再発しないという事前予測は外れた。後から接続した試行では位相がまず負へ変化する窓をタップ開始から約60〜62 msで検出し、正の傾斜は帯域低下の次の窓、出力フレーム85,816で検出した。振幅比は約0.49979まで回復した後、出力フレーム114,216〜114,816を中心とする窓で再び0.20未満に低下した。[先行接続の第1試行](../runs/coreaudio-headphone-drift-44100-attach-before-1/summary.json)・[後から接続した第1試行](../runs/coreaudio-headphone-drift-44100-attach-late-1/summary.json)

位相傾斜とホスト時計の速度差を比べた18区間のうち16区間は0.5 ppm以内。後から接続した第2・第3試行の2度目の低下区間は末尾が短く、差はそれぞれ0.523・0.789 ppmだった。集約は採取の成否と予測の成否を分けて保持している。次は後から接続する時刻を2通りにして、低下の位置が出力フレームにそろうか、タップの開始に合わせて移るかを照合する。Core Audio内の処理段とヘッドフォンのアナログ出力は未確認。[位相傾斜と時計の集約](../runs/coreaudio-headphone-drift-44100-late-attach-pairs-20261122-a/summary.json)

#### 検算と再実行

macOS 15.6.1 arm64、Xcode 26.2、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4。生PCMのビット、二つの末尾マーカーの相関、1,366窓の実FFT、開始時計と18区間の傾斜を独立に検算した。複素比の最大差は `1.08e-14`、回帰の差は `8.1e-10` ppm以下。直接出力の従来3収録を再解析し、要約と一致した。固定上流のエンジン6試験と再実装の分割描画1試験が通過。7実行の224入力・109出力をサイズとSHA-256で照合し、収録やビルドの実体19,938,330バイトをRTL9210B-CGへ保存した。既定出力は各収録後に内蔵スピーカーへ復元した。[集約のマニフェスト](../runs/coreaudio-headphone-drift-44100-late-attach-pairs-20261122-a/manifest.json)

```sh
trial_case=cases/coreaudio-headphone-drift-44100-late-attach.json
tap_app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
jq -r '.trials[].run_id' "$trial_case" | while IFS= read -r trial; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$trial" "$tap_app" --case "$trial_case"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_late_attach_44100.py coreaudio-headphone-drift-44100-late-attach-pairs-20261122-a
```

保存済みデータを集約するときは、最後の行の実行IDを変える。

### 44.1 kHzで再生中にタップを接続する時刻を比較する

固定上流の `AudioEngine.build()` から `ChimeraProcessor.process()`、Wasmの `engine_render()`、Rustの `Engine::render()` と描画の分割試験を確認した。 `process()` が出力フレーム数を指定し、`Engine::render()` は描画したフレーム数だけ累積番号 `pos` を進める。今回の照合点は後段の出力とタップなので、この描画の代わりに前回と同じ既知PCMを直接出力へ渡す。[Workletの構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[描画の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Pythonで出力を開始する通知を送り、1.10秒または1.38秒後にタップを起動する。比較には実測した先頭予定ホスト時刻を使う。ペア内で長い待機から短い待機を引き、タップと出力の最初の予定時刻の間隔の増分を `Δ接続`、同じ帯域低下の窓中心を出力とタップで測った時間差を `Δ出力` と `Δタップ` とする。タップ時刻が基準なら `Δ出力 ≈ Δ接続` かつ `Δタップ ≈ 0`、出力時刻が基準なら `Δ出力 ≈ 0` かつ `Δタップ ≈ −Δ接続` となる。広い帯域を4窓観測してから、4窓続く最初の低下を比較する。許容差は15 msとし、仮説と観測の成立条件を採取前に記録した。[出力とタップの起動順](../tools/measure_coreaudio_output_error_pcm.py#L46)・[継承した試験音](../cases/coreaudio-headphone-drift-44100-late-attach.json)・[事前登録](../cases/coreaudio-headphone-drift-44100-attach-timing.json)

#### 接続時刻と帯域低下

3組の直接出力は先行ケースと同じPCMにビット一致し、出力とタップの幅は512フレーム、音声クロックは比較区間で連続した。1.10秒で接続した各試行では、最初の観測窓の19,845 Hzの振幅比は0.01144〜0.01764で、フレーム70,816を中心とする窓までに広い帯域に戻った。1.38秒側はこの回復の後から採取を始めた。登録した規則で安定した広帯域の後の低下を選ぶと、全試行で窓中心が出力フレーム85,616だった。[採取と比較の集約](../runs/coreaudio-headphone-drift-44100-attach-timing-pairs-20261122-a/summary.json)

| 組 | 長い待機でのタップ開始の遅れ（ms） | 出力開始から測った低下時刻の差（ms） | タップ開始から測った低下時刻の差（ms） |
| --- | --- | --- | --- |
| 1 | +210.9114 | +0.0008 | −210.8617 |
| 2 | +297.8757 | −0.0001 | −297.8458 |
| 3 | +262.7431 | +0.0005 | −262.6984 |

出力開始から約1,941.36 msに当たる同じ窓で変化し、タップ開始からの差は接続の遅れを逆向きに反映した。両差の残差は最大0.050 ms。出力時刻の差は同一窓の予定ホスト時刻を比較した値で、帯域低下の検出は200フレーム（約4.54 ms）刻みで行った。タップの開始に揃うという予測は外れ、登録した15 msの基準では3組とも出力開始に揃った。位相傾斜とホスト時計の速度差は27区間すべてで0.5 ppm以内（最大0.399 ppm）だった。[時刻の分類](../tools/measure_coreaudio_headphone_late_attach_44100.py)・[ペア別の集約](../runs/coreaudio-headphone-drift-44100-attach-timing-pairs-20261122-a/summary.json)

#### 先行接続の保存済み収録を再解析する

従来はフレーム55,216までだった先行接続の解析範囲を、別のケースで118,816まで延長した。入力と前マーカーによる位置合わせを固定し、400フレームの実FFTを200フレームずつ送って再計算した。全3収録で振幅比が0.20未満となる窓を、フレーム27,216・56,416・85,616・114,816で検出した。この測定範囲の3間隔はいずれも29,200フレーム（約662.13 ms）だった。85,616の低下を、そこより前から採取したデータと後から採取を始めたデータの両方で確認した。Core Audio内の処理段とアナログ出力は未確認。次は同じ試験音の連続区間と収録時間を延ばし、この間隔が続く範囲と終了条件を確認する。[範囲を延長したケース](../cases/coreaudio-headphone-drift-44100-attach-preserved.json)・[保存済み収録の再解析](../runs/coreaudio-headphone-drift-44100-attach-preserved-20261122-a/summary.json)

#### 検算と再実行

macOS 15.6.1 arm64、Xcode 26.2、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4。新規6試行の1,539窓は実FFT、先行収録3回の1,641窓は独立した複素正弦への射影で検算した。複素比の差は最大 `1.33e-14`、時計と位相の傾斜の計算差は `6.5e-10` ppm以下。上流のエンジン6試験と再実装の分割描画1試験が通過し、従来の接続順比較の集約要約はバイト一致した。9実行の290入力・111出力のサイズとSHA-256を照合し、音声・時刻とビルドの実体20,174,943バイトをRTL9210B-CGへ保存した。既定出力は全試行後に内蔵スピーカーへ復元した。[集約のマニフェスト](../runs/coreaudio-headphone-drift-44100-attach-timing-pairs-20261122-a/manifest.json)・[従来ケースの回帰](../runs/coreaudio-headphone-drift-44100-late-attach-pairs-20261122-timing-regression/manifest.json)

```sh
trial_case=cases/coreaudio-headphone-drift-44100-attach-timing.json
tap_app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
jq -r '.trials[].run_id' "$trial_case" | while IFS= read -r trial; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$trial" "$tap_app" --case "$trial_case"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_late_attach_44100.py coreaudio-headphone-drift-44100-attach-timing-pairs-20261122-a --case "$trial_case"
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/review_coreaudio_headphone_preserved_44100.py coreaudio-headphone-drift-44100-attach-preserved-20261122-a
```

保存データの再集約は、最後の2行の実行IDを変える。

### 44.1 kHzの帯域低下が長い再生で続くかを測る

固定上流では `AudioEngine.build()` がWorkletを接続し、`process()` の出力フレーム数をWasmの `engine_render()` へ渡す。Rustの `Engine::render()` は累積フレーム `pos` から内部更新境界を決め、描画してから `pos` を進める。 `output_does_not_depend_on_the_host_block_size` は同じ絶対位置で命令を適用したときのPCMを異なる分割幅で比べる。ここでは既知の連続音を使い、合成器の外の直接出力とプロセスタップの関係だけを追う。[Workletの構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

直接出力プローブの `OutputPCM.write()` は累積出力フレームで試験音の配列を引き、左右に逆相のFloat32を格納してからフレーム数を加算する。 `OutputProbe.write()` は各要求の予定サンプル番号とホスト時刻を保持する。タップは入力の生PCMと別の予定時計を記録する。既存の出力上限3秒を、意図的な処理遅延や戻り値の変更を加えない44.1 kHz PCMの採取に限って12秒へ広げる。512フレームで12秒なら要求は約1,034回で、出力の記録容量2,048件に収まる。タップは14秒で、既存の30秒上限に収まる。29,200フレーム間隔で低下が続くという予測と、その間隔から外れる基準は採取前に登録した。[直接出力の記録](../tools/chimera_output_deadline_probe.swift)・[タップの記録](../tools/chimera_process_tap.swift)・[事前登録](../cases/coreaudio-headphone-drift-44100-long-recurrence.json)

#### 反復の範囲

3回とも、44.1 kHz・512フレームの出力コールバック1,034件とタップのブロック1,186件を保存した。試験音の先頭55,216フレームは前回とビット一致し、以後の解析区間は同じ位相の40フレーム周期が続く。両PCMのビット照合、解析区間の予定サンプル番号の連続性、初期マーカーと末尾2マーカー、オーバーフローなしを確認した。窓中心でフレーム9,416〜511,416を測った。[収録と反復の集約](../runs/coreaudio-headphone-drift-44100-long-recurrence-20261122-a/summary.json)

| 試行 | 帯域低下の回数 | 最後の低下の窓中心（出力フレーム／秒） | その後の狭帯域の観測時間 | 終盤の19,845 Hzの振幅比の中央値 |
| --- | --- | --- | --- | --- |
| 1 | 11 | 318,616／7.225秒 | 4.372秒 | 0.0154233 |
| 2 | 11 | 318,016／7.211秒 | 4.385秒 | 0.0154240 |
| 3 | 12 | 347,216／7.873秒 | 3.723秒 | 0.0154251 |

31の低下間隔のうち26が29,200フレーム（662.13 ms）、5が28,600フレーム（648.53 ms）だった。200フレーム刻みの窓で600フレームの差を観測した。出力開始から3秒以降にも低下と回復の反復は見られたが、全試行で間隔が登録許容差400フレームを一度以上外れたため、同じ周期が連続するという予測は不成立だった。3回とも最後の低下から観測末尾まで広帯域への回復は観測されず、その間の振幅比の中央値は約0.01542だった。[第1試行](../runs/coreaudio-headphone-drift-44100-long-recurrence-1/summary.json)・[第2試行](../runs/coreaudio-headphone-drift-44100-long-recurrence-2/summary.json)・[第3試行](../runs/coreaudio-headphone-drift-44100-long-recurrence-3/summary.json)

通常の区間選択で位相傾斜とホスト時計差を照合できた65区間では、誤差は最大0.100 ppmだった。追加診断として、最後の低下から2周期分を除いた終盤を1本の直線で近似した。2,205 Hzの位相傾斜は+5.42〜+5.58 ppm、ホスト時計差は+5.69〜+6.79 ppmだった。近似の差は0.266〜1.218 ppmで、従来の0.5 ppmを2試行で超えた。出力側の予定時刻には隣接ブロック間で公称間隔から約25〜27 µs離れる点が少数あり、終盤全体の直線回帰残差は出力側で約13 µs、タップ側で約12 nsだった。狭帯域の持続は振幅比から判定し、この長い区間を一定の時計差として扱う精度は別に記録した。[時計の集約](../runs/coreaudio-headphone-drift-44100-long-recurrence-20261122-a/summary.json)

次の対照では直接出力を動かしたまま、狭帯域が続く時間に無音を挿入する。同じ4周波数の再開後も狭帯域が続くか、広帯域と反復が再び現れるかを、無音を挿入しない収録と照合する。Core Audio内の処理段、11.6秒以降の状態、アナログ出力は未確認。

#### 検算と再実行

macOS 15.6.1 arm64、Xcode 26.2、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4。生PCMのビット、3マーカーの相関、7,533小窓の実FFT、68区間の生ホスト時刻と位相の直線回帰を独立に検算した。複素比の差は最大 `1.10e-14`、回帰の差は `6.5e-10` ppm以下。上流エンジン6試験と再実装の分割描画1試験が通過した。直近の接続時刻比較の集約はバイト一致し、12秒を超える引数、48 kHzの長時間指定、PCMなしの長時間指定は再生を開始する前に拒否された。5実行の152入力・56出力のサイズとSHA-256を照合し、収録とビルドの実体35,558,254バイトをRTL9210B-CGへ保存した。元の内蔵スピーカーを全試行後に復元した。[集約のマニフェスト](../runs/coreaudio-headphone-drift-44100-long-recurrence-20261122-a/manifest.json)・[前回の比較の回帰](../runs/coreaudio-headphone-drift-44100-attach-timing-pairs-20261122-recurrence-regression/manifest.json)

```sh
trial_case=cases/coreaudio-headphone-drift-44100-long-recurrence.json
tap_app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
jq -r '.trials[].run_id' "$trial_case" | while IFS= read -r trial; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$trial" "$tap_app" --case "$trial_case"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_late_attach_44100.py coreaudio-headphone-drift-44100-long-recurrence-20261122-a --case "$trial_case"
```

保存済み収録を再集約する場合は最後の行の実行IDを変える。

### 44.1 kHzの狭帯域で無音を挟み試験音を再開する

上流の `AudioEngine.build()` からAudioWorklet、Wasmの `engine_render()`、Rustの `Engine::render()` を確認した。ホストから渡る標本数だけ音源を描画し、累積標本番号 `pos` を進める。描画幅から独立したこの時計は `output_does_not_depend_on_the_host_block_size` が検査する。本比較では外側の出力処理を調べるため、これまでと同じ4周波数のPCMを使い、出力の累積フレーム番号で無音の範囲を決める。[Workletの構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

直接出力の `OutputPCM.write()` は事前に確保した配列から、累積出力フレーム `written` に対応するPCMを左右逆相で出力する。今回はファイル内のフレーム384,000〜430,079に対して振幅包絡だけを変える。両端128フレームの半余弦と中央45,824フレームのゼロを使い、区間外では元の配列を保つ。両条件とも出力開始と停止は各1回で、出力コールバックとタップの時刻は無音をまたいで照合する。無音の直前にすでに狭帯域だった試行で、試験音の再開後に広帯域へ戻るかを判定する。[直接出力の記録](../tools/chimera_output_deadline_probe.swift)・[事前登録](../cases/coreaudio-headphone-drift-44100-silence-resumption.json)

#### 試験音の再開後の帯域

無音あり・なしの3組で44.1 kHz、直接出力とタップの512フレーム幅と予定サンプル番号の連続性を確認した。無音区間の外の入力はすべて基準PCMとビット一致した。両方のチャンネルが厳密にゼロの範囲を出力フレームで表すと、全3回の直接出力で `[384127, 429953)`（1.03914秒）、タップで `[384173, 429904)`（1.03698秒）だった。半余弦の係数が0になる端の標本も直接出力の範囲に含まれる。タップ側ではゼロ区間の始まりが46フレーム遅く、終わりが49フレーム早かった。無音の端と振幅比の判定窓は別に測定した。[採取時の集約](../runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-a/summary.json)・[左右PCMの再確認](../runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/summary.json)

| 組 | 無音ありの直前44窓の振幅比の中央値 | 無音ありの再開後の最初の窓 | 再開後の中央値（無音なし／無音あり） |
| --- | --- | --- | --- |
| 1 | 0.0154480 | 0.0154000 | 0.0154307／0.0154320 |
| 2 | 0.0154412 | 0.0153977 | 0.0154329／0.0154370 |
| 3 | 0.0154460 | 0.0153985 | 0.0154352／0.0154329 |

表は19,845 Hzのタップ/直接出力振幅比。再開後の最初の窓はランプ終了から136フレーム（3.08 ms）後に始まる。再開後約1.846秒の全窓で振幅比は0.01548未満で、広帯域の基準0.40を4窓連続で満たす組はなかった。無音なしの同じ出力フレームでも狭帯域が続き、再開後の中央値のペア差は最大約 `4.1e-6` だった。出力を維持した1.04秒の無音の後も狭帯域が続くという事前予測は3組で成立した。[試行とペアの比較](../runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/summary.json)

#### 無音をまたぐ位相と予定ホスト時刻

再開後の定常区間18件では、2,205 Hzの位相傾斜と予定ホスト時計の速度差は最大0.062 ppm以内で一致した。追加の比較では、前後の窓中心383,416と430,416で2,205 Hzの伝達位相を引き、1周期内の差をフレームへ換算した。全6回で位相は+0.216〜+0.230フレーム動き、予定ホスト時刻の両観測点の経過差は−0.849〜−0.827フレームだった。端点間の差は約1.05〜1.07フレームあり、無音なしにも現れた。同じ区間内で直接出力側の隣り合う予定ホスト時刻に、公称の512フレーム間隔から約+25・−27・+25 µs外れる3箇所が全試行にあった。端点間の位相と時計の差はこの観測で確認し、処理段との対応は未確定のまま残した。[位相と時計の集約](../runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/summary.json)

次は同じ約1.04秒の間に `AudioOutputUnitStop()` と `AudioOutputUnitStart()` を行う対照を登録する。試験音だけを無音にした今回の収録を基準に、出力を停止して再開したときの帯域と予定時計を比較する。

#### 検算と再実行

macOS 15.6.1 arm64、Xcode 26.2、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4。生の左右PCM、包絡と区間外のビット一致、全13,662小窓の実FFT、再開後18区間の回帰、前後窓の時計を独立に検算した。複素比の最大差は `1.11e-14`、再開後の時計回帰の差は `3.3e-10` ppm以下。固定上流エンジン6試験と再実装の分割描画1試験が通過し、従来の長い再生の集約はバイト一致した。無音の判定は採取時の左右差の確認に加え、別の集約で左右両方の生PCMからゼロ区間を確認した。9実行の303入力・111出力のサイズとSHA-256を照合し、収録とビルドの実体71,099,391バイトをRTL9210B-CGへ保存した。既定出力は全試行後に内蔵スピーカーへ復元した。[左右PCMの集約マニフェスト](../runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/manifest.json)・[長い再生の回帰](../runs/coreaudio-headphone-drift-44100-long-recurrence-20261122-resumption-regression/manifest.json)

```sh
trial_case=cases/coreaudio-headphone-drift-44100-silence-resumption.json
tap_app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
jq -r '.trials[].run_id' "$trial_case" | while IFS= read -r trial; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$trial" "$tap_app" --case "$trial_case"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_late_attach_44100.py coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review --case "$trial_case"
```

保存済み収録を再集約する場合は最後の行の実行IDを変える。

### 44.1 kHzの狭帯域でAudioUnitを停止してから再開する

固定上流の `AudioEngine.build()` は `AudioContext` とAudioWorkletを接続する。Workletは要求フレーム数をWasmの `engine_render()` に渡し、Rustの `Engine::render()` がフレーム数分だけ描画して累積位置 `pos` を進める。固定上流の分割試験は同じ位置に制御イベントを適用したときの描画が要求幅に依存しないことを確認する。今回は同じ既知PCMを直接出力し、出力開始・停止と音源内部のフレーム位置を分けて記録する。[Workletの構築](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[描画の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[エンジンの描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

出力プローブは通常、初期化済みのAudioUnitを開始し、指定の時間だけ出力して停止する。対照の動作では、コールバックから累積出力フレームが384,000に達したことを通知し、メイン側が停止と再開を行う。停止後にPCMの読み取り位置を430,080へ進める。出力した生PCMには実際に渡した左右サンプルだけを保存する。タップの前マーカーと後マーカーは停止前後それぞれの解析に使い、プログラムの停止時間と、予定ホスト時刻で表したブロック間隔も別に測る。広帯域への回復とその後の低下を予測し、採取の前に比較条件を登録した。[直接出力のプローブ](../tools/chimera_output_deadline_probe.swift)・[事前登録](../cases/coreaudio-headphone-drift-44100-output-restart.json)

#### 帯域と時計の再開

3回とも停止前の記録は384,000フレーム・750要求で終わり、同じAudioUnitの再開で元ファイルの430,080フレームからPCMを渡した。出力とタップの両区間は44.1 kHz・512フレーム。停止前と再開後の直接出力は対応する元PCMとビット一致した。停止APIが戻ってから再開APIを呼ぶまでと、直接出力の予定ホスト時刻上の空きには約83〜86 msの差があった。再開直後の直接出力の予定サンプル番号は全3回で0。タップ側の予定サンプル番号は停止区間をまたいで512ずつ進み、この間の両チャンネルにはデジタルゼロの時期があった。[時計と比較の集約](../runs/coreaudio-headphone-drift-44100-output-restart-20261122-a/summary.json)

| 試行 | 停止API復帰から再開API呼び出しまで | 直接出力の予定ホスト時刻上の空き | タップの連続したデジタルゼロ |
| --- | --- | --- | --- |
| 1 | 1,045.39 ms | 1,128.43 ms | 49,667フレーム（1,126.24 ms） |
| 2 | 1,049.82 ms | 1,135.75 ms | 49,989フレーム（1,133.54 ms） |
| 3 | 1,054.95 ms | 1,139.43 ms | 50,152フレーム（1,137.23 ms） |

停止前44窓の19,845 Hzの比は3回とも約0.01545。再開後に最初に測った400フレーム窓は元ファイルの430,216から始まり、振幅比は全試行で2,205・17,640・19,845・20,947.5 Hzの順に約1.00000・1.00000・0.50000・0.01635だった。音声だけを無音にして出力を維持した対照では、同じ窓の19,845 Hzは約0.01540で、その後も狭帯域だった。AudioUnitを止めた条件では3回とも広帯域へ戻り、その後に再び帯域低下を検出した。[停止前後の第1試行](../runs/coreaudio-headphone-drift-44100-output-restart-1/summary.json)・[出力を維持した無音対照](../runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/summary.json)

再開から27,088フレームで固定40フレーム周期との波形差が現れた。19,845 Hzの低下と2,205 Hzの位相傾斜を検出した窓の中心は、再開から27,136フレーム（約615.33 ms）だった。波形差の最初の位置は先行接続で初めて再生したときと一致した。帯域低下の中心は先行ケースの27,216から80フレームずれ、400フレーム窓を200フレームずつ進めたときの格子のずれと一致する。世界時刻の空きと試験音の累積位置が変わっても、再開を基準に初期の広帯域と低下の順序が揃った。再開後12区間でホスト時計の速度差と位相傾斜は最大0.127 ppm以内で一致した。[出力を再開した3試行の比較](../runs/coreaudio-headphone-drift-44100-output-restart-20261122-a/summary.json)

適用範囲は同じ外部ヘッドフォンと44.1 kHzの直接出力、プロセスタップまで。Core Audio内のどの状態が変わったかと、ヘッドフォン端子での波形は未確認。次は研究版のSafari再生で同じ試験音を使い、AudioContextの停止と再開でグラフ内のフレームとタップの帯域がそれぞれどう変わるかを測る。

#### 検算と再実行

macOS 15.6.1 arm64、Xcode 26.2、Swift 6.2.3、Python 3.14.4、NumPy 2.4.4。生PCMと元入力のビット、マーカー位置、停止前後の6,831小窓の実FFT、12区間の直線回帰、タップのゼロ範囲を独立に検算した。FFTでの複素比の差は最大 `1.11e-14`、回帰の差は `4.9e-10` ppm以下。Swift型検査、固定上流エンジン6試験と再実装の分割描画1試験が通過した。無音対照の集約は回帰実行でバイト一致した。5実行の174入力・56出力のサイズとSHA-256を照合し、音声・時刻とビルドの実体34,481,951バイトをRTL9210B-CGへ保存した。全試行で既定出力を内蔵スピーカーへ復元した。[集約マニフェスト](../runs/coreaudio-headphone-drift-44100-output-restart-20261122-a/manifest.json)・[無音対照の回帰](../runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-restart-regression/manifest.json)

```sh
trial_case=cases/coreaudio-headphone-drift-44100-output-restart.json
tap_app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
jq -r '.trials[].run_id' "$trial_case" | while IFS= read -r trial; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_drift_44100.py "$trial" "$tap_app" --case "$trial_case"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_coreaudio_headphone_restart_44100.py coreaudio-headphone-drift-44100-output-restart-20261122-a
```

既存の収録を再集約するときは、最後の行の実行IDを変える。

### Safariの44.1 kHzでAudioContextの停止・再開を照合する

固定上流の `AudioEngine.build()` は44.1 kHzなど指定のレートでAudioContextを作り、Workletへ出力する。 `process()` は要求フレーム数をWasmの `engine_render()` に渡し、エンジンの `render()` はフレーム数だけ累積位置を進める。分割幅のテストはこのフレーム位置で入力をそろえてPCMを比較する。直接出力との対照では、前回の試験用のFloat32をAudioBufferSourceNodeへ読み込み、既存の採取Workletで逆相出力する。同じフレーム位置を使ってグラフとプロセスタップを比較する。[上流のWorklet接続](../../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts#L110)・[描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L182)・[分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

Safariの既存計測はパイロット音を再生して出力しているWebKitのプロセスを特定する。今回、そのプロセスにタップを先に取り付けてから試験音を開始する。停止条件では `suspend()` と `resume()` の各時刻、Contextのフレーム位置、Workletの128フレームの要求列を記録する。グラフPCMの既知入力との比較、タップの前後マーカー、周波数ごとの振幅の判定を採取前に登録した。[既存のSafari採取器](../../../../web/prototypes/chimera-research/tools/capture-safari-process-tap.mjs)・[事前登録](../cases/safari-headphone-context-restart-44100.json)

#### グラフとプロセスタップの比較

Safari 18.6、同じ44.1 kHzの外部ヘッドフォンで、連続再生と `suspend()/resume()` を3組採取した。パイロットの出力と本試行の出力で同じWebKit GPUプロセスを確認した。全6回でグラフの526,336フレームが既知の直接出力用PCMとビット一致し、Workletの128フレーム要求は停止の前後を通して連続した。停止を完了してから再開を要求するまでContextのフレーム位置は変化しなかった。連続条件のWorklet実時刻間隔の最大は7〜11 ms、停止条件で最も長い間隔は1,125〜1,135 ms。タップは512フレームで、停止中の両チャンネルがゼロの範囲をまたいでも予定サンプル番号を連続して記録した。[全試行の集約](../runs/safari-headphone-context-restart-44100-20261122-a/summary.json)

| 組 | 停止中のContextの位置（試験音先頭から、フレーム） | 停止API完了〜再開API要求 | タップの両チャンネルがゼロだった時間 | 再開から19,845 Hzの低下を検出した窓中心 |
| --- | --- | --- | --- | --- |
| 1 | 384,000 | 1,045 ms | 1,126.55 ms | 26,616フレーム、603.54 ms |
| 2 | 384,000 | 1,046 ms | 1,129.61 ms | 26,816フレーム、608.07 ms |
| 3 | 384,128 | 1,045 ms | 1,116.85 ms | 27,088フレーム、614.24 ms |

停止前44窓の19,845 Hzは全条件で狭帯域で、同じ窓の2,205 Hzの振幅比は0.9を超えた。停止を挟んだ3回とも、再開後最初の測定窓で19,845 Hzの振幅比は約0.50000となり、表の時刻で再び低下した。どの回も直接出力で観測した27,136フレームから登録許容差2,048フレーム以内だった。連続条件の対応窓では約0.01542で、後続区間も狭帯域だった。変化はグラフより後のタップで観測された。[停止条件の試行3](../runs/safari-headphone-context-restart-44100-pause-3/summary.json)・[連続条件の試行3](../runs/safari-headphone-context-restart-44100-control-3/summary.json)

実験の停止区間とは別に、連続条件の第1試行と停止条件の第1試行のタップに、それぞれ161フレームと417フレームのデジタルゼロが2区間ずつ現れた。対応するグラフPCMと要求フレーム番号は連続していた。停止条件の第1試行では、完全にゼロの400フレームを相対残差の分母にしたため1窓で未定義値が出た。ゼロ信号をゼロで再構成した窓の残差を0とし、収録済みPCMから再集約した。修正はその1窓の残差に限られ、前後の帯域判定と振幅比は元の採取と一致した。グラフの後で生じたゼロ区間の原因、Core Audio内の処理箇所、ヘッドフォン端子の出力は未確認。次は同じ試験音と停止条件をFirefoxで採取し、Safariで観測した再開時の帯域変化の適用範囲を確認する。[残差の再確認](../runs/safari-headphone-context-restart-44100-pause-1-residual-review/summary.json)

#### 検算と再実行

macOS 15.6.1 arm64、Safari 18.6（20621.3.11.11.3）、Node v24.19.0、Xcode 26.2、Python 3.14.4、NumPy 2.4.4。グラフのビット、マーカー相関、15,023小窓の実FFT、停止中のタップの両チャンネルと予定時計を独立に検算した。複素比の最大差は `1.13e-14`。先行のSafari 44.1 kHz較正を改修後の採取器で再実行して通過した。JavaScriptの構文検査、固定上流のエンジン6試験と再実装の分割描画1試験も通過した。9実行の279入力・135出力のサイズとSHA-256を照合し、収録とビルドの実体50,796,435バイトをRTL9210B-CGへ保存した。既定出力は内蔵スピーカーへ復元した。[集約のマニフェスト](../runs/safari-headphone-context-restart-44100-20261122-a/manifest.json)・[較正の回帰](../runs/safari-process-tap-smooth-marker-44100-20261122-context-regression/manifest.json)

```sh
trial_case=cases/safari-headphone-context-restart-44100.json
tap_app=/Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app
jq -r '.trials[].run_id' "$trial_case" | while IFS= read -r trial; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python -B tools/measure_safari_headphone_context_restart_44100.py "$trial" "$tap_app"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_safari_headphone_context_restart_44100.py safari-headphone-context-restart-44100-20261122-a --summarize
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15000000 ../../.venv/bin/python -B tools/measure_safari_headphone_context_restart_44100.py safari-headphone-context-restart-44100-pause-1-residual-review --review safari-headphone-context-restart-44100-pause-1
```

保存済みの場合は末尾2行に新しい実行IDを指定して再集計できる。

### Firefoxの44.1 kHzでAudioContextの停止と出力要求を照合する

[事前登録](../cases/firefox-headphone-context-restart-44100.json)では、Safari・直接出力と同じ526,336フレームの既知PCMを使用する。44.1 kHzのハードウェア出力の手前と後を比べるために、3つの記録点を設ける。音源を読み出す `AudioBufferSourceNode.start()` は秒で指定し、`SharedContextMarker.process()` はグラフの `currentFrame`（フレーム）と `Date.now()`（エポックms）を記録しながら、各128フレームを左右 `x, -x` として渡す。停止要求の前後で `AudioContext.currentTime × sampleRate` を標本位置に換算し、停止中の位置と再開後の進行を照合する。[Firefoxの再生入口](../../../../web/prototypes/chimera-research/tools/capture-firefox-output-marker.mjs)・[Worklet](../../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)

固定したFirefoxのcubeb実装では `audiounit_output_callback` が最終出力バッファと `AudioTimeStamp` を取得する。`OutputSnapshot::record()` は左右1組8バイトとして確保済み領域へコピーし、`mSampleTime`（フレーム）と `mHostTime`（machのtick）、要求開始と記録終了のtickを残す。ファイルへ書くのはストリーム解放時。`browser_bridge()` はFirefox親PIDを起動直後に特定し、タップの準備後に試験音の開始を通知する。従来の先頭256要求では約1.49秒までしか保存できないため、今回は採取容量だけを増やす。前後でソースと予定時計の連続性を別々に照合し、タップは2組のマーカーで整列した窓ごとにソースに対する振幅比を比較する。[出力コールバックの計測パッチ](../tools/chimera-cubeb-output-snapshot.patch)・[親プロセスの採取](../tools/measure_worklet_live_song_process_tap.py)

固定Gecko `fdd757a2e09c9471cddf383e64e631e4ce178499` では `AudioContext::SuspendInternal()` が宛先とトラック群の停止を要求し、`MediaTrackGraphImpl::ApplyAudioContextOperationImpl()` が各トラックの停止カウントを増やす。`CheckDriver()` は有効な音声トラックが消えると `SystemClockDriver` への切り替えを予約する。再開は逆に `AudioCallbackDriver` を要求し、ドライバーが動いてから保留したトラックを再開する。`AudioCallbackDriver::StartStream()` は状態を Starting にしてから `cubeb_stream_start()` を呼ぶ。停止は `cubeb_stream_stop()` を経てcubebの直列キューでAudioUnitを止める。上流の `suspend-after-construct.html` はPromiseの完了順序と状態を、cubebの `test_dial_tone()` は通常のトーン出力を確認する。今回の前後マーカーと予定時計を伴う停止試験をそれらに補う。[GeckoのContext実装](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/webaudio/AudioContext.cpp#L1054)・[ドライバーの選択](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/MediaTrackGraph.cpp#L432)・[出力開始と停止](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/GraphDriver.cpp#L722)・[状態試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/testing/web-platform/tests/webaudio/the-audio-api/the-audiocontext-interface/suspend-after-construct.html)・[cubebの試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/third_party/rust/cubeb-coreaudio/src/backend/tests/tone.rs)

予備試行は先頭256要求を採る既存XULで実施した。グラフは入力とビット一致し、フレーム384,512で1,052 ms停止した。2つの試験音ストリームは予定サンプル番号0から始まった。停止中のタップには50,557フレームの左右デジタルゼロがあり、再開後26,704フレームで19,845 Hzの振幅比の低下を検出した。停止直前の44窓は狭帯域の前提を満たさなかった。前後のcubeb比較区間に対して採取長も不足し、予備試行の全体判定を不合格として保存した。独立の実FFTで2,501窓の4周波数を照合したところ、振幅比の最大誤差は1.1×10⁻¹⁴だった。[予備試行](../runs/firefox-headphone-context-restart-44100-pilot-256/summary.json)・[マニフェスト](../runs/firefox-headphone-context-restart-44100-pilot-256/manifest.json)

採取容量の変更は、先行比較の `chimera_output_snapshot.rs` に差分を適用して最大4,096要求、長時間設定に限り8 MiBを初期確保した。本試行では1ストリーム当たり3,072要求で打ち切る設定とする。初回の増分ビルドのXULは旧版とハッシュが一致したため、Rustの静的ライブラリと3クレートのキャッシュ指紋を退避して再リンクした。既存のFirefoxは別アプリとして保持した。ソース、ビルド、収録実体はRTL9210B-CGへ保存する。[採取容量の差分](../tools/chimera-cubeb-output-snapshot-long.patch)・[初回ビルド](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-context-restart-44100-20261122/gecko-build.log)・[再リンク](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-context-restart-44100-20261122-linked/gecko-build.log)

再リンクした初回はPlaywrightの起動用設定がアプリに含まれず、新しいウィンドウにタブが2個できて全6回が収録前に止まった。先行版と同じ `playwright.cfg` と `defaults/pref/00-playwright-prefs.js` を採取用アプリの `Contents/Resources` に入れ、試験条件を引き継いで別IDで再実行した。設定のSHA-256は順に `294a395f326b28c251f41f6f09ebe2a628362db222ad2f9b56665740f0f87e29` と `8c2d32801a924f2c2b133f1191d01213513c86e8d1e42e144e9cb1015ea71084`。採取用XULは `74b59e5a161071023f4c5661c76aa8d3fa75c809f71c8d4f3cd894ad64c2aa8d`。[初回6試行の集約](../runs/firefox-headphone-context-restart-44100-20261122-a/summary.json)・[ビルドのハッシュ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/firefox-context-restart-44100-20261122-linked/build-sha256.txt)

実行時はmacOS 15.6.1 arm64、Firefox 157.0、Node.js 24.19.0、Python 3.14.4、NumPy 2.4.4。44,100 Hz、HAL幅512の `BuiltInHeadphoneOutputDevice` を選択し、タップの待ち合わせを16秒の採取に合わせて延長した。各試行の終了時に既定出力を内蔵スピーカーへ戻した。次は実際に使ったコマンド。収録IDは [第2版ケース](../cases/firefox-headphone-context-restart-44100.json) にある。

```bash
base=/Volumes/RTL9210B-CG/voice-simulator/build
firefox="$base/chimera-cubeb-output/firefox-context-restart-44100-20261122-linked/build-dist.app/Contents/MacOS/firefox"
app="$base/chimera-process-tap/CHIMERA-PCM-Probe.app"
for trial in control-1 pause-1 pause-2 control-2 control-3 pause-3; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_firefox_headphone_context_restart_44100.py "firefox-headphone-context-restart-44100-$trial-retry" "$firefox" "$app"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=12000000 ../../.venv/bin/python tools/measure_firefox_headphone_context_restart_44100.py firefox-headphone-context-restart-44100-20261122-b --summarize
```

#### 3組の結果

| 組 | 停止時間 | cubebの予定ホスト時刻の間隔 | 再開後に最初に帯域が低下した位置 | 停止中のタップの左右ゼロ |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1,046 ms | 1,127.12 ms | 27,160フレーム（615.87 ms） | 49,868フレーム |
| 2 | 1,044 ms | 1,132.76 ms | 26,560フレーム（602.27 ms） | 50,374フレーム |
| 3 | 1,044 ms | 1,127.76 ms | 26,960フレーム（611.34 ms） | 49,897フレーム |

予定ホスト時刻の間隔は旧ストリームの最終要求先頭から新ストリームの初回要求先頭まで。停止条件のグラフは全3回でフレーム384,256に留まり、再開後も128フレームずつ進んだ。cubebは停止で別ストリームへ移り、新しい256フレーム要求の予定サンプル番号は0から始まった。連続対照は同じcubebストリームで予定番号が進んだ。タップの512フレームの予定時計は停止をまたいで進み、信号が途切れた期間をゼロで記録した。[全6収録と3組の判定](../runs/firefox-headphone-context-restart-44100-20261122-b/summary.json)

全6試行でグラフの526,336フレームは入力にビット一致した。cubebは前後の測定区間の左右がビット一致し、区間をマーカーまで広げて値を照合しても有限値の差はゼロ。マーカー区間の253フレームと369フレームではゼロの符号ビットだけが違った。19,845 Hzの変化が最初に観測できる点は、今回の3観測点ではプロセスタップだった。停止ありでは再開後の最初の窓が全3回とも約0.50000で、最初の低下は直接出力の窓中心27,136フレームから±576フレームの範囲に収まった。各試行で再開後にさらに3回、29,000〜29,200フレーム間隔で低下した。連続対照の比較後634窓では比は0.20未満のまま続いた。タップより後段のアナログ出力は未測定。次は別のContextから音を出し続け、主Contextを止めたときも同一のcubebストリームが残るかを照合する。[停止あり第1試行](../runs/firefox-headphone-context-restart-44100-pause-1-retry/summary.json)・[連続対照第1試行](../runs/firefox-headphone-context-restart-44100-control-1-retry/summary.json)

独立検算では各400フレームの倍精度実FFTのビン20・160・180・190を取り、左右差のタップと入力の振幅比を求めた。予備試行を含む17,522窓の最大差は約1.1×10⁻¹⁴。元のPCMとCSVから、グラフ・cubebのビット、タップの前後マーカー、予定時計、ゼロ区間、4窓持続判定を照合した。Safariの保存試行再解析は元の観測値と一致し、固定上流のエンジン6試験、再実装の分割描画1試験、JavaScriptとPythonの構文検査が通過した。17実行の648入力・251出力をサイズとSHA-256で確認し、採取実体はRTL9210B-CGに87,577,157バイト保存した。[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-firefox-context-restart-44100.py)・[Safari回帰](../runs/safari-headphone-context-restart-44100-20261122-firefox-regression-v2/summary.json)・[集約のマニフェスト](../runs/firefox-headphone-context-restart-44100-20261122-b/manifest.json)

### Firefoxで出力を維持したまま主AudioContextを止める

[事前登録](../cases/firefox-headphone-context-keep-output-44100.json)では、前回の主信号と停止手順を使い、全試行で同じページ内の別Contextから維持音を流す。Geckoの `AudioDestinationNode` はリアルタイムの宛先を `MediaTrackGraph::GetInstance()` へ登録する。グラフの検索キーはウィンドウID、標本レート、出力機器ID。今回の2つのContextはこれらが同じ設定になる。`AudioContext::SuspendInternal()` は自分のトラックと宛先を止める。グラフの `CheckDriver()` は共用グラフ全体の有効な音声トラックを調べるので、維持音のトラックが活動中なら `AudioCallbackDriver` を保持すると予測する。既存の `suspend-after-construct.html` はContextの状態とPromiseの完了順を確認する。今回の試行では、同じ出力ストリームの予定時計が主Contextの停止をまたいで進むかを追加で確認する。[宛先の登録](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/webaudio/AudioDestinationNode.cpp:448)・[グラフの検索キー](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/MediaTrackGraph.cpp:124)・[ドライバーの判定](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/MediaTrackGraph.cpp:391)・[状態試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/testing/web-platform/tests/webaudio/the-audio-api/the-audiocontext-interface/suspend-after-construct.html)

維持音は `y[n] = sin(2πn/40) / 1024`、44,100 Hzで1,102.5 Hz。主信号を `x[n]` とすると、cubebの左右はFloat32の `y+x, y−x` になり、半差は主信号、半和は維持音になる。主Contextの停止区間では左右がともに `y` になり、半差ゼロでも同相の音と256フレーム単位の予定時計が残ると予測する。タップの512フレームの予定時計と、停止区間の半和・半差も別々に確かめる。停止前の19,845 Hzが狭帯域なら、再開後も狭帯域が続く予測を、連続対照および前回の単一Contextと照合する。[前回の3組](../runs/firefox-headphone-context-restart-44100-20261122-b/summary.json)

Geckoの出力側では `MediaTrackGraphImpl::PlayAudio()` が各トラックの出力区間に音量を適用し、`AudioSegment::Mix()` を呼ぶ。混ぜたFloat32出力を `MixerCallback()` からドライバーへ渡す。維持音の位相はcubebの半和から周期40フレームの候補を照合して定めた。その位相と入力PCMから左右の合成値を計算し、APIの状態とは独立に同じ維持音が停止区間をまたいだかを確認した。タップの比較は半差で元の試験音、半和で維持音を追った。[グラフからミキサーへの受け渡し](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/MediaTrackGraph.cpp:1502)・[Float32の加算](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/AudioMixer.h:58)・[収録と解析](../tools/measure_firefox_headphone_context_restart_44100.py)

| 組 | 主Contextの停止時間 | cubebで維持音だけだったフレーム | タップの19,845 Hzの再開直後の振幅比 | 再開後の最大比 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1,047 ms | 46,336 | 0.01538774 | 0.01546113 |
| 2 | 1,045 ms | 46,336 | 0.01538575 | 0.01546202 |
| 3 | 1,044 ms | 46,080 | 0.01538785 | 0.01545370 |

3組の停止・連続全6試行で、主ContextのグラフPCMとcubebの混合PCMは計算値とビット一致した。停止した3回とも同じcubebストリームで256フレームずつ予定時刻が進み、比較区間で予定ホスト時刻の間隔の誤差は最大0.070 msだった。表のフレーム範囲では、cubebの左右が維持音とビット一致した。タップでも停止区間の中央で左右差はゼロ。同相維持音の1,102.5 Hzは全659窓で入力振幅の0.9999965倍以上を保った。停止前から狭帯域だった全3組で、再開後約2.88秒の測定末尾まで19,845 Hzの振幅比は0.015463未満だった。先行比較ではcubebのストリームが止まり、再開後の最初の窓は約0.50000だった。[今回の3組](../runs/firefox-headphone-context-keep-output-44100-20261122-a/summary.json)・[単一Contextの3組](../runs/firefox-headphone-context-restart-44100-20261122-b/summary.json)

前回と同じmacOS 15.6.1 arm64、Firefox 157.0の計測ビルド、44.1 kHzの外部ヘッドフォン、署名済みプロセスタップを使用した。最初の連続・停止各1試行はNumPyの真偽値をJSONに出力できず判定を書けなかったため、型を修正して元のPCMを再解析した。停止の第2試行は、cubeb内の前マーカーが34,048フレームで従来の探索区間0〜32,768の外にあった。初回の判定とPCMを保持し、cubebの探索末尾を65,536へ広げて再解析した。タップの探索、帯域の測定区間、閾値は初回と同じ。[第1試行の実行記録](../runs/firefox-headphone-context-keep-output-44100-pause-1/manifest.json)・[第2試行の初回判定](../runs/firefox-headphone-context-keep-output-44100-pause-2/summary.json)・[同じPCMの再解析](../runs/firefox-headphone-context-keep-output-44100-pause-2-review/summary.json)

生のFloat32とCSVを読み、維持音の位相を実FFTから再計算し、左右の混合値、停止中の維持音、cubebとタップの予定時計を照合した。主信号の4周波数を15,023窓の実FFTで検算し、振幅比の最大差は約1.1×10⁻¹⁴。停止中の維持音の659窓も照合した。単一Contextの保存済み試行の再解析は全観測値が一致し、固定上流エンジン6試験と再実装の分割描画1試験が通過した。10実行の449入力・140出力をサイズとSHA-256で確認し、実体78,515,018バイトをRTL9210B-CGに保存した。既定出力は内蔵スピーカーへ復元した。[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-firefox-context-keep-output-44100.py)・[マニフェスト](../runs/firefox-headphone-context-keep-output-44100-20261122-a/manifest.json)

次は別Contextの出力をデジタルゼロにして、cubebが同じように動き続けるかをまず確認する。時計が連続した場合は今回と同じ停止条件で比較し、維持音の1,102.5 Hz成分が帯域維持に寄与する可能性を検討する。Core Audio内の処理段とアナログ出力には引き続き観測点が要る。

```bash
base=/Volumes/RTL9210B-CG/voice-simulator/build
firefox="$base/chimera-cubeb-output/firefox-context-restart-44100-20261122-linked/build-dist.app/Contents/MacOS/firefox"
app="$base/chimera-process-tap/CHIMERA-PCM-Probe.app"
for trial in control-1 pause-1 pause-2 control-2 control-3 pause-3; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_firefox_headphone_context_restart_44100.py "firefox-headphone-context-keep-output-44100-$trial" "$firefox" "$app" --case keep-output
done
for trial in control-1 pause-1 pause-2; do
  id="firefox-headphone-context-keep-output-44100-$trial"
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=6000000 ../../.venv/bin/python tools/measure_firefox_headphone_context_restart_44100.py "$id-review" --case keep-output --review "$id"
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=12000000 ../../.venv/bin/python tools/measure_firefox_headphone_context_restart_44100.py firefox-headphone-context-keep-output-44100-20261122-a --case keep-output --summarize
```

### Firefoxで無音の別AudioContextを動かし続ける

[事前登録](../cases/firefox-headphone-context-silent-output-44100.json)では、維持用の40フレーム・2チャンネルのループと主Contextの停止約1.045秒を引き継ぐ。変更は別Contextのループの振幅をゼロにすること。Geckoの `AudioBufferSourceNodeEngine::IsActive()` が確認するのはバッファと開始時に設定される標本レート。`ProcessBlock()` はループ終端で位置を先頭に戻し、`CopyFromBuffer()` はデータのチャンネル数を用いて出力ブロックを埋める。現在の試験音は各チャンネルの値がゼロで、バッファには2チャンネルがある。`MediaTrack::IncrementSuspendCount()` は停止対象トラックを `mTracks` から `mSuspendedTracks` へ移す。別Contextのトラックが `mTracks` に残れば `AudioTrackPresent()` が活動中と判定し、`CheckDriver()` はcubebを使うドライバーを維持するはず。上流のループ期間試験は、指定フレームのループ出力と終端のゼロを確認する。今回の試行は実時間ドライバーの予定時計と両観測点のゼロを照合する。[ループと活動判定](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/webaudio/AudioBufferSourceNode.cpp:491)・[トラックの停止と復帰](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/dom/media/MediaTrackGraph.cpp:2242)・[ループ期間の試験](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-source/testing/web-platform/tests/webaudio/the-audio-api/the-audiobuffersourcenode-interface/audiobuffersource-duration-loop.html)

同相の維持音を `y[n]=0` にすると左右の合成値は `x[n], -x[n]` に戻る。主Contextが止まった間は左右ともゼロ。位相は定義できないので、256フレームごとの予定サンプル番号とホスト時計およびタップの512フレームごとの時計から継続を判定する。先行する同相音ありの実験では3組とも再開後に19,845 Hzの振幅比が約0.01539だった。ゼロに変えた3組でも停止前の狭帯域とストリームの継続が成立したとき、再開後の比が0.20未満を保つと予測する。主Context単独を止めた先行比較の約0.50000も参照する。[同相音の3組](../runs/firefox-headphone-context-keep-output-44100-20261122-a/summary.json)・[単一Contextの3組](../runs/firefox-headphone-context-restart-44100-20261122-b/summary.json)

前回と同じmacOS 15.6.1 arm64、Firefox 157.0とそのXUL、44.1 kHzの外部ヘッドフォン、署名済みプロセスタップを使用した。主信号は同じ526,336フレームのFloat32。ゼロのループは2チャンネルとも正のゼロで埋めた。主信号のグラフ内PCMはそのまま採取し、出力時計は別途照合した。[実行ケース](../cases/firefox-headphone-context-silent-output-44100.json)・[実時間ページ](../../../../web/prototypes/chimera-research/tools/capture-firefox-output-marker.mjs)・[収録と解析](../tools/measure_firefox_headphone_context_restart_44100.py)

```bash
base=/Volumes/RTL9210B-CG/voice-simulator/build
firefox="$base/chimera-cubeb-output/firefox-context-restart-44100-20261122-linked/build-dist.app/Contents/MacOS/firefox"
app="$base/chimera-process-tap/CHIMERA-PCM-Probe.app"
for trial in control-1 pause-1 pause-2 control-2 control-3 pause-3; do
  CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=25000000 ../../.venv/bin/python tools/measure_firefox_headphone_context_restart_44100.py "firefox-headphone-context-silent-output-44100-$trial" "$firefox" "$app" --case silent-output
done
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=12000000 ../../.venv/bin/python tools/measure_firefox_headphone_context_restart_44100.py firefox-headphone-context-silent-output-44100-20261122-a --case silent-output --summarize
```

| 組 | 主Contextの停止時間 | cubebの左右ゼロ | タップ中央の左右ゼロ | 再開直後の19,845 Hzの振幅比 | 再開後の最大比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 1,046 ms | 46,336フレーム | 44,286フレーム | 0.01538612 | 0.01545933 |
| 2 | 1,044 ms | 46,336フレーム | 44,286フレーム | 0.01538620 | 0.01545627 |
| 3 | 1,054 ms | 46,592フレーム | 44,542フレーム | 0.01538907 | 0.01545043 |

全6試行で主ContextのグラフPCMとcubebの左右PCMが期待値とビット一致した。停止ありの3回では同じcubebストリームが続き、256フレームの予定番号とホスト時計が停止区間をまたいで進んだ。予定ホスト時刻の間隔の誤差は最大0.070 ms未満。タップの512フレームの予定時計も停止中に進み、両端1,024フレームを除く中央は左右ともデジタルゼロだった。[3組の計測](../runs/firefox-headphone-context-silent-output-44100-20261122-a/summary.json)

停止前の狭帯域の前提は3組すべてで成立した。主信号の再開後は約2.87秒の観測末尾まで19,845 Hzの振幅比は0.015460未満。同相音ありの前回に対する再開直後の絶対差は最大1.62×10⁻⁶だった。無音の別Contextでも出力時計を維持でき、今回の条件では同相音を加える必要がなかった。この比較の観測点はプロセスタップまで。帯域変化のCore Audio内の処理段とヘッドフォンのアナログ出力は未同定。[同相音ありの比較](../runs/firefox-headphone-context-keep-output-44100-20261122-a/summary.json)・[出力を停止した比較](../runs/firefox-headphone-context-restart-44100-20261122-b/summary.json)

独立検算では生PCMの15,017窓から倍精度の実FFTで4周波数を取り、保存した振幅比との差を最大約1.1×10⁻¹⁴と確認した。cubebの139,264フレームとタップ中央の133,114フレームが左右ゼロだったことも元ファイルで照合した。別Contextなし・同相音ありの保存済み試行を当時のケース定義で再解析し、全観測値が一致した。固定上流エンジン6試験と再実装の分割描画1試験、JavaScriptとPythonの構文検査が通過した。7実行の324入力・139出力をサイズとSHA-256で確認し、実体78,550,443バイトをRTL9210B-CGに保存した。最終試行の後に既定出力が内蔵スピーカーへ戻ったことを確認した。[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-firefox-context-silent-output-44100.py)・[集約マニフェスト](../runs/firefox-headphone-context-silent-output-44100-20261122-a/manifest.json)
