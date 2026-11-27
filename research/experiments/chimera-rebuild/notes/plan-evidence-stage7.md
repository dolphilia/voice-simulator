# 第7段階の実行証拠を再照合

2026-11-22。固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` を基準に、第7段階の計画にある派生機能と、録音を使う評価の記録を点検した。各代表実行について、元のケース、固定上流版、機能を確かめる具体的なチェック、出力のサイズ・SHA-256を照合した。現行のソースに対するRustの試験とWebのビルドも実行した。保存済みの音響・ブラウザ測定の照合と、現行ソースのビルド確認はそれぞれの観測範囲で扱う。[計画の完了条件](../../../../docs/plans/chimera-research-rebuild-plan.md#実装順と段階の完了条件)・[対象の登録](../cases/plan-evidence-stage7.json)・[前回の監査](plan-evidence-audit.md)

後続実行を含む監査結果は[第2版の照合](#第2版の照合)、[第3版の照合](#第3版の照合)、[第4版の照合](#第4版の照合)に記録した。

## 上流の入口と観測の範囲

- `BeatPlayer::tick()` は音声側の秒時計で休符を含むステップを進め、`gestures()` が打音の先行時間と調音ジェスチャーを予約する。代表実行で、休符、BPM・スウィングの変更、停止時の予約消去、再開位置、発生したPCMを照合した。固定上流には打音・分割と描画中の割り当ての試験がある。[予約とジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/beat_player.rs#L165)・[打音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/beatbox.rs)・[実時間ビート](worklet-live-beatbox.md)
- 言語別の歌詞処理は文字列を音節・音素へ変換し、`plan_song()` が譜面から拍と音高を秒とHzに割り当てる。歌唱計画に未対応音素が残っていた初期の実行と、それを解消した計画・PCM・ブラウザの再演を照合した。ロシア語のデモ全体と中国語の診断句は別の譜面を使う。[韓国語の音節化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/korean.rs#L277)・[ロシア語の単語変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/russian.rs#L86)・[中国語の音節化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs)・[歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs)
- `connectMidi()` は `requestMIDIAccess({ sysex: false })` の完了後に、ポートとチャンネルで押鍵の所有者を管理する。最後の所有者が離れたときに離鍵する。研究側の仮想ポートの試験では、この後の音高Hz・声門ゲート・レンダー量子の位置・PCMを確認している。ブラウザが提供する許可画面と、実機の接続・離鍵の経路は別の観測を要する。[上流の接続と切断](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L71)・[仮想ポートの入力](../../../../web/prototypes/chimera-research/tools/fake-midi.mjs)・[現行の対応表](interaction-presentation.md)
- `compare::tsp::run()` は録音と合成を別々にアラインし、`measure_pair()` が共通音素を照合する。CSDの `compare_song()` は譜面の音符注釈を時計にして、時間、F0、非周期性、H1−H2とビブラートを比較する。今回の監査では発話時間・音素境界、歌唱音符・窓別の計測、別に用意した試聴ページと回答の集計までを照合した。[TSPの対比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[TSPの音素照合テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1544)・[CSDの曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)

## 照合した項目

| 項目 | 実行で確認した範囲 |
| --- | --- |
| ビートボックス | 実時間の打音予約と休符、テンポ・スウィング、停止と再開、CLIとの波形一致。[実時間操作](worklet-live-beatbox.md) |
| 成人女性・子ども・体型補間 | 3端点と混合で固定発声のPCMと内部状態、較正目標、形状、共鳴。子どもと混合体型の三次元描画も確認。[固定発声](human-body-fixed-voice.md)・[較正目標](human-body-calibrated-vowels.md)・[三次元表示](worklet-tract-3d-body.md) |
| 韓国語 | 完成形と字母の音節と拍、実時間歌唱、保存ケースの再演。[韓国語歌唱](korean-lyrics.md) |
| ロシア語 | 強勢・軟音・綴りの音節化と歌唱に加え、デモ「Ночной ветер」全16音節と16音符。初期の未対応 `/tʃ v x/` が解消し、実ブラウザ・CLI・保存ケースの再演で454,629サンプルを照合した。[初期の歌詞比較](russian-lyrics.md)・[デモ全体](postalveolar-affricate.md#実測) |
| 中国語 | 漢字・ピンイン、変調、基本譜例。後続の診断句「四是吃字人爱」全6音節・6音符では未対応欄が空になり、実ブラウザとCLIの再演でPCMを照合した。[基本歌唱](mandarin-lyrics.md)・[診断句](glottal-stop.md#実装と実測) |
| 鳴禽 | 固定上流の4コールと公式CLIの全体PCM、Finch buzzの仮想MIDI入力と再演。[4コール](songbird-calls.md)・[MIDIの対照](worklet-midi-songbird-buzz.md) |
| ウェッデルアザラシ | `Chug` を鍵盤で再発音させ、放した後のパルスと呼気、自然終端での復帰、CLI再演を照合。[MIDIの対照](worklet-midi-seal-chug.md) |
| アメリカアリゲーター | `Water dance` の鍵盤入力、発声周期と倍音、離鍵後のコールを照合。[MIDIの対照](worklet-midi-alligator-dance.md) |
| アフリカゾウ | `Squeak` の弁の状態とPCM。打鍵の音高を取り替えても波形が一致する対照を収録。[MIDIの対照](worklet-midi-elephant-squeak.md) |
| Web MIDI | 仮想ポートで押鍵の優先順、離鍵、実時間の音高とゲート、波形を固定上流・CLIへ照合。今回のCoreMIDIは入出力ポートとも0件で、物理入力の確認は残る。ブラウザの許可画面の検証も残る。[手動発声のMIDI](worklet-midi-voice-pitch.md) |
| 三次元表示 | 子ども・混合体型の閉鎖前後、格子とセル、960・390 px表示、体型切り替えの初回描画。[体型の表示](worklet-tract-3d-body.md) |
| 録画 | MP4・WebM VP9/Opus・VP8/OpusとFirefoxの形式選択。記録した動画で音声の時計、拍、声道断面を照合。[MP4](worklet-song-tract-recording.md)・[VP9](worklet-song-recording-webm.md)・[VP8](worklet-song-recording-vp8.md)・[Firefox](worklet-song-recording-firefox.md) |
| デュエット | 二声の時計、声部別ファイル、前後シーク、口元の描画、乱流の位置。代表素材で照合し、子ども・混合体型の枝位置は未照合。[声部別の観測](duet-telemetry.md)・[乱流と描画](duet-head-turbulence.md) |
| TSPの録音と合成 | 発話の有音区間を調整6件・確認12件で計測。確認用のうち4発話は、録音と両合成のMFAによる音素・語の境界まで照合。[18発話](tsp-active-duration-original.md)・[確認用の音素境界](tsp-phone-boundaries-held-out.md) |
| CSDの録音と合成 | 調整曲・確認曲の長音を含む294音符で固定上流の通常報告を再現。F0閾値対照は4曲486音符88,344窓まで照合。[長音比較](csd-long-note-vibrato.md)・[全曲の窓別対照](csd-f0-yin-threshold.md) |
| 人による試聴 | TSPの18対とCSDの6区間に試聴素材がある。CSDでは再生・CSV・集計を既知の試験入力で照合した。人による回答の記録は今回の代表実行に含まれない。[TSPの試聴資料](tsp-active-duration-original.md)・[CSDの試聴と回答](csd-listening-responses.md) |

## 監査で見つかった参照先の扱い

最初の実行では `bun` がPATHに無く、Rust試験の後でWebビルドが停止した。既存の計測器と同じく、利用できるコマンドを選び、この環境ではローカルキャッシュのBun 1.4.4を `npx --offline` で起動した。第2実行ではWebビルドが通り、試聴回答の集計が参照するケースに限り監査が失敗した。`record_measurement()` は先行実行を入力とするとき、元のファイルをマニフェストに記録する。監査側はそのケースを今回の実行にもう一度保存した場合と同じパスで探していた。修正後は `runs/` 内の入力を先行実行から照合し、通常のケースは従来どおり実行時のスナップショットから照合する。[初回の停止](../runs/stage7-evidence-audit-20261122-a/manifest.json)・[ハッシュ照合の失敗を含む判定](../runs/stage7-evidence-audit-20261122-b/summary.json)・[参照先の判定](../tools/audit_plan_evidence.py#L71)

## 再現

研究ワークスペースから次のコマンドを実行した。`/private/tmp` からの再実行では同じPythonとスクリプトを絶対パスで指定した。既存の波形・動画・観測CSVは元の論理パスから照合し、現行Webの検証用ビルドは作業用ディスクの一時ディレクトリに出力した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python \
  tools/audit_stage7_evidence.py stage7-evidence-audit-local
```

第7段階の27実行について1,885判定を読み、1,655出力のサイズとSHA-256（計7,702,387,396バイト）、986件のケース定義の参照を照合した。現行のRustワークスペースで42試験、固定上流の曲比較で19試験が通過し、現行のWASM・TypeScript・Viteのビルドも通過した。環境はmacOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1、Bun 1.4.4。修正後の2実行は各38判定が通過し、要約がバイト一致した。従来の第0〜7段階監査64実行も再実行し、12判定を通過して旧要約とバイト一致した。失敗2実行を含む今回の監査5実行の1,051入力・21出力もサイズとSHA-256を照合し、新規採取ログの実体41,270バイトをRTL9210B-CGに保存した。[修正後の第7段階の実行](../runs/stage7-evidence-audit-20261122-c/manifest.json)・[別ディレクトリの再実行](../runs/stage7-evidence-audit-20261122-repeat/manifest.json)・[第0〜7段階の回帰](../runs/plan-evidence-audit-20261122-stage7-regression/manifest.json)

今回の未照合項目のうち、ブラウザのWeb MIDI許可と拒否は、接続機器がなくても同一環境で比較できる。物理ポートからの入力と人による試聴は、それぞれ実機と回答が得られた時点で、既存の出力時計・集計手順を使って評価する。

監査後に、ChromiumのWeb MIDI権限応答と接続の取り消しを試験コンテキストで照合した。[追試の記録](worklet-midi-permission.md)

子ども・混合体型のデュエットで、声門と口腔の枝位置およびシーク直後の乱流表示を照合した。生成元の枝配置を保持する条件で、体型別の検証を追加した。[デュエットの追試](duet-head-turbulence-body.md)

## 第2版の照合

2026-11-22。[保存された監査のケース第2版](../runs/stage7-evidence-update-20261122-linked-plan/artifacts/source/research/experiments/chimera-rebuild/cases/plan-evidence-stage7.json)は、前版の27実行を保持して後続10実行を追加した。保存されたケース定義のうち、各実行のケースIDに対応するファイル名と定義内のIDを確認する。ファイル名が `mandarin-lyrics-v2.json` のように版を含む場合は、実行が実際に参照したファイル名を登録した。前版のマニフェストをSHA-256で確認し、前版の項目、ケースID、必須判定が第2版の対応項目と一致することを照合した。

| 追加した実行証拠 | 固定上流との比較と到達範囲 |
| --- | --- |
| TSPのF1・F2 | `measure_pair` が音素を対応させ、12 kHzの母音内3窓で `Sig::formants` がF1・F2を得る。4発話の一致した主強勢単母音は12か所。録音、固定上流、研究版の36個の中央値を照合し、境界付近を含む180窓を確認した。2録音6窓のプリエンファシス比較では5窓でF2が100 Hz以上動き、追加欠測は0。既知の極を持つ波形、帯域幅条件、ラグ窓とプリエンファシスの対照も登録した。[上流の窓規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L528)・[母音の実測](tsp-stressed-vowel-formants-held-out.md)・[2録音の感度](tsp-lpc-pre-emphasis-recordings.md) |
| 子ども・混合体型のデュエット | 二声の生成元ごとの声道グラフから枝を参照した。声門源は両声部とも0.2 cm、口腔源は11.5502 cmと13.8140 cm。960・390 CSS pxで再生時計に対する乱流源の位置とシーク直後の描画を照合した。上流は子どもを通常CLIに、混合体型を観測プログラムに結び付けた。成人男声・女声の従来公演も回帰で再生した。[体型別の照合](duet-head-turbulence-body.md)・[従来公演の回帰](../runs/duet-turbulence-body-20261122-original-regression/manifest.json) |
| Web MIDIの権限応答 | `connectMidi()` が標準APIの結果を受けて購読を開始する経路を、固定上流と研究版の6画面で確認した。許可・拒否・再接続、取り消し後に遅く届いた結果、購読解除を観測。試験用Chromiumコンテキストで、許可時の入力0件・SysEx無効を確認した。[上流の接続](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L71)・[権限応答の記録](worklet-midi-permission.md) |

監査のハッシュ照合・ビルド・必須観測は各53判定が通った。音響の予測については、確認用F2の帯域幅条件での追加欠測、既知の幅広いF2に対する12次の固定規則、ラグ窓を外したときの誤差縮小の3件が反証された。各予測の結果は実行が正しく測れたことと別に要約へ残した。[第2版の要約](../runs/stage7-evidence-update-20261122-repeat/summary.json)

### 検証が残る範囲

- **録音評価。** TSPとCSDで音響計測の実行がある。録音の正解F2注釈と人による試聴回答は登録実行に含まれない。CSDの回答集計は試験データとして記録されている。[録音2語の比較](tsp-lpc-pre-emphasis-recordings.md)・[CSDの試聴回答の集計](csd-listening-responses.md)
- **Web MIDI。** 監査後に研究版の手動発声と固定上流Playで、Chromeの標準ダイアログによる拒否、権限リセット後の許可、切断時の購読解除を確認した。CoreMIDIの仮想送信元から両画面へ押鍵・離鍵を送り、信頼済みイベントと音源を照合した。同じ音を保持する2入力を順に外すと、最後の入力が消えたところで呼気が減衰した。物理ポートからの押鍵・離鍵は未観測。[標準ダイアログの追試](worklet-midi-browser-prompt.md)・[CoreMIDI経由の比較](worklet-midi-coremidi.md)・[単一入力の削除](worklet-midi-coremidi-unplug.md)・[同音を保持する2入力](worklet-midi-coremidi-shared-note.md)
- **体型別のデュエット。** 生成元ごとの枝位置・描画を照合済み。子ども・混合体型とも、最初の声門乱流振幅差を枝断面積と流量から説明できた。初期舌先をそろえると、歌唱前の最初の512サンプルで流量・放射・PCMが0になった。体型ゲインもそろえた全区間のPCM最大差は子ども声部 `9.09×10⁻¹³`、混合体型 `1.46×10⁻¹¹`。いずれも音源変動0の対照で、混合体型の微小な残差は放射から観測された。[体型別の差](duet-head-turbulence-body.md#実測)・[子ども声部](duet-child-glottal-noise-origin.md)・[子ども声部の出力ゲイン](duet-child-output-gain.md)・[混合体型の声門乱流](duet-mixed-glottal-noise-origin.md)・[混合体型の初期舌先](duet-mixed-initial-tip.md)・[混合体型の出力ゲイン](duet-mixed-output-gain.md)
- **大振幅時の出力ゲイン。** 混合体型と同じ放射を1.2倍すると、基準ゲインのみ6,954フレームでピーク制限が作動した。体型係数の適用位置によるPCMの最大差は0.05520034で、ピーク包絡の保持・解放中にも差が続いた。通常入口、固定上流と同一放射の再生、独立出力計算で制限の発動を照合した。[ピーク制限とゲインの適用位置](duet-mixed-limiter-gain-order.md#実測)
- **混合体型の放射の微小差。** 通常レベルの残差が生じた出力フレーム25,025の1点目で、口端流量の差から放射差を復元した。壁成分の差は次の内部サンプルで現れ、鼻端は観測窓で0だった。[放射の成分別比較](duet-mixed-radiation-origin.md#実測)
- **口端流量差の導入箇所。** 初出点で口端への流入を断面・枝・壁の各更新後に採り、断面更新直後にすでに差があったことを確認した。中点のR–L負荷と体積の時間差分・平滑化から、口端流量とその差を再構成した。[口端負荷と体積流量の比較](duet-mixed-lip-load-origin.md#実測)
- **可動壁の体積差の数値対照。** 通常CLIで体積差の式を展開すると、後続224点の局所流量の最大誤差が約2,700分の1になった。固定上流とのPCM最大差は両条件とも `1.46×10⁻¹¹` で、閉鎖・再開口と密閉圧縮の既存条件を通過した。[展開式の比較](duet-mixed-volume-difference.md#実測)

### 第2版の再現結果

前版と同じ監査CLIでケース第2版を読み込む。研究ワークスペースから実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-update-new
```

16項目・37実行の1,990判定と1,746出力（計7,728,584,215バイト）をまたいで、出力のサイズ・SHA-256と1,234件のケース定義の参照を照合した。現行Rustワークスペース42試験と固定上流の比較19試験が通過した。Webの通常ビルドでWASMの生成、TypeScript型検査、Viteの成果生成を確認した。研究ディレクトリと `/private/tmp` からの実行、計画書に本節への参照を追加した後の実行で、各53判定と同じ要約を得た。旧来の第0〜7段階監査64実行の回帰も12判定に合格し、旧要約と一致した。今回の4実行の890入力・17出力を別に確認し、採取ログ35,204バイトをRTL9210B-CGに保存した。[第2版初回](../runs/stage7-evidence-update-20261122-a/manifest.json)・[別ディレクトリの再実行](../runs/stage7-evidence-update-20261122-repeat/manifest.json)・[計画参照の追加後](../runs/stage7-evidence-update-20261122-linked-plan/manifest.json)・[全段階の回帰](../runs/plan-evidence-audit-20261122-stage7-update-regression/manifest.json)

## 第3版の照合

第2版の定義と37実行に、Chromeの標準許可画面とCoreMIDIの4実行、子ども声部と混合体型のデュエットの10実行を追加した。前版のケーススナップショットと新しい登録を比較し、以前登録していた必須判定と必要ファイルも照合する。追加実行はマニフェストのSHA-256を固定した。実行ごとの判定に加え、元のイベントJSONとPCMを監査CLIでもう一度読む。[事前登録](../cases/plan-evidence-stage7.json)・[監査CLI](../tools/audit_stage7_evidence.py)

- 上流Playの `MidiButton` から `connectMidi`、`attach`、`press`・`lift` へたどる。入力ポートIDとMIDIのチャンネルを所有者とし、音番号ごとに保持する集合を管理する。最初の所有で押鍵、最後の所有者の離鍵や切断で解放を通知する。解除済みの接続要求を世代番号で無効にし、同じ音を別入力が押さえている間は呼気目標を維持する。上流の `live-control.test.ts` は複数鍵盤、チャンネル、入力消失、許可待ちの切断を試す。音57は `440 × 2^((57−69)/12) = 220 Hz`。保存データでは、画面の権限状態、信頼済みイベントのバイト列と切断件数、128フレーム単位で信号を適用した研究版の加工前PCMを確認する。[上流の所有状態](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L21)・[上流のMIDI試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L84)・[研究版の入力](../../../../web/prototypes/chimera-research/src/midi-input.ts)
- 上流の `render::notes` が歌詞と譜面からジェスチャーを予約し、`HumanVoice::render` が声門と気道を内部96 kHzで更新して放射流量の時間差分を得る。間引き後に体型ゲイン、DC除去、包絡の更新、ピーク制限を経て48 kHzのPCMを得る。通常レベルのPCMは2体型とも全フレームを先行ケースの許容差で比較する。放射系列では口端、鼻端、壁を独立に比較し、ゼロでない差の最初の内部サンプルを数える。過大入力の制限や体積差の展開式の機構別試験は、保存された元の観測範囲で照合する。[上流の歌唱CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[上流の放射からPCMまで](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[研究版の出力段](../crates/vocal-core/src/output.rs)

### 一次出力からの再計算

| 対象 | 確認した内容 |
| --- | --- |
| Chromeの標準許可画面 | 研究版と固定上流で拒否・許可のボタン操作記録があり、権限は `prompt → denied → prompt → granted` と遷移した。切断後の購読は両画面で0件。4枚の画面記録を照合した。 |
| CoreMIDI仮想入力 | 通常の離鍵、単一入力の削除、同音を保持する2入力の順次削除で、両画面の信頼済みバイト列と削除通知0・1・2件が登録どおりだった。研究版のWorkletとCLIのPCMは操作ごとの128,256・140,800・171,776フレームでビット一致した。離鍵のCLI PCMをメモリ上で1標本だけ変える対照では、その操作の判定だけが不合格になった。 |
| 体型別デュエット | 子ども声部91,200フレームの上流とのPCM最大差は `9.09×10⁻¹³`、混合体型97,920フレームは `1.46×10⁻¹¹`。ともに元の許容差 `6×10⁻⁸` を満たした。混合体型で口端は内部50,049、壁は50,050で最初の差があり、観測した50,304点で鼻端の差は0だった。 |

[第3版の出力と判定](../runs/stage7-evidence-update-20261122-v3-repeat/summary.json)

### 実行と未確認の範囲

16項目・51実行に対し、記録済み2,185判定、2,059出力（8,048,569,576バイト）、1,541件のケース定義参照を照合した。研究ワークスペースと `/private/tmp` を起点とした2実行は各76判定で、要約がバイト一致した。現行Rust42試験、固定上流の比較19試験とMIDI 2試験、WASM・TypeScript・Viteの通常ビルドを確認した。第0〜7段階の従来監査は64実行で12判定を通過し、第2版当時の要約とバイト一致した。監査3実行の701入力・14出力を照合し、新規採取ログ25,488バイトをRTL9210B-CGに保存した。環境はmacOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1、Bun 1.4.4。[初回のマニフェスト](../runs/stage7-evidence-update-20261122-v3-a/manifest.json)・[別ディレクトリの再実行](../runs/stage7-evidence-update-20261122-v3-repeat/manifest.json)・[第0〜7段階の回帰](../runs/plan-evidence-audit-20261122-stage7-v3-regression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-third-new
```

物理鍵盤による押鍵・離鍵・抜線と出力機器での音は未観測。現在のCoreMIDIは入出力とも0件だった。TSPとCSDの試聴素材は用意済みで、回答集計の登録データは試験入力。TSP録音には正解F2の注釈がなく、登録済みの結果は同じ波形に対する推定値と感度の比較を示す。[試聴回答の扱い](csd-listening-responses.md)・[録音のF2感度](tsp-lpc-pre-emphasis-recordings.md)

後続の比較でTSP録音6窓と合成対照1窓の手動F2注釈を準備した。合成対照と試験回答で図・試聴・取込を検証し、人による回答欄は未記入の状態で保存した。[F2注釈資料の検証](tsp-f2-annotation.md#実測と保存先)

## 第4版の照合

第3版の51実行を保持し、LPC次数・帯域幅・倍音間隔、注釈資料、注釈を読み込む試験に関する5実行を追加した。初回の複素根照合の不合格は個別に登録した。前版の必須判定と必要出力、新規のマニフェストと成果のハッシュを確認し、数値の検証が通過したことと研究上の予測が成立したことを別々に記録する。[第3版の保存定義](../runs/stage7-evidence-update-20261122-v3-repeat/artifacts/source/research/experiments/chimera-rebuild/cases/plan-evidence-stage7.json)・[第4版の事前登録](../cases/plan-evidence-stage7.json)

### 保存した根・極・注釈CSVの照合

- 上流の `measure_pair` は録音と合成の対応音素を `Sig` に渡す。`Sig::formants` は12 kHzの300標本窓に `estimate_formants` を適用する。LPCの複素根から偏角で周波数、半径の対数で帯域幅を求め、公開された一覧からF1より200 Hz超かつ3,500 Hz未満の最初の候補をF2として採る。`a_missing_measurement_has_no_cost` は欠測をスコアへ加えないことを検証する。監査では保存された根と公開極を読み、既知対照42件と84件の採択、実録音6窓の12次・14次の採択を再計算した。`seems` の既定14次の採択から12次への移動は3窓とも約1.3 kHzで、12次の生の根には旧候補の100 Hz未満の近傍が無かった。`again` は79 Hz未満だった。[上流の比較入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓と採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[欠測の扱い](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1528)・[録音の次数比較](tsp-lpc-order-recordings.md#実測)
- 初回実行では `independent_raw_roots` だけが不合格だった。第2版の結果に対応する上流の根・公開極・包絡のJSONは初回とバイト一致し、窓ごとのF2の変化と帰属段も一致した。最終の合格から初回不合格の有無を推測せず、初回の記録・元のケース・全出力を照合した。録音比較で大きな変化があっても同じ候補が残るという予測と、幅180 Hz条件でLPCの採択が120 Hzを超えて外れるという予測は、各実行で反証された。[最初の不合格](../runs/tsp-lpc-order-recordings-20261122-a/manifest.json)・[録音の再実行](../runs/tsp-lpc-order-recordings-20261122-repeat/manifest.json)・[倍音間隔の対照](tsp-f2-harmonic-spacing.md#実測)
- 注釈資料の原本では、録音6窓と既知対照1窓の300標本、同じ資料IDが記入された未回答のCSVを確認した。試験用2人分のCSVから一致1窓・不一致1窓を独立に再計算した。合成回答のラベルをメモリ上で人の回答に変えると、出所の判定だけが不合格になった。保存失敗の期待項目に別の判定を指定した場合も不合格になった。[判定者用資料](../runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)・[試験用CSVと集計](../runs/tsp-f2-annotation-20261122-fixtures/manifest.json)

### 未確認の観測

| 観測 | 確認済みの範囲 | 判定に必要な記録 |
| --- | --- | --- |
| 実録音のF2注釈 | 注釈資料の録音6窓、既知対照、合成回答のCSV取り込みと集計。人手取込で既知の試験回答と照合し、実録音の判定件数を記録する | 同じ資料IDの録音窓を評価した判定者の周波数・根拠・判定不能の回答。[判定者向けページ](../runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)・[取込の検証](tsp-f2-human-intake.md) |
| TSP・CSDの人による試聴 | 素材の再生、回答CSV、CSDの資料IDと試験入力による集計を検証済み | 実際の試聴者が記録した回答。[TSPの試聴ページ](../runs/tsp-listening-responses-20261122-final/artifacts/listening/index.html)・[TSPの回答手順](tsp-active-duration-original.md#比較試聴のページと回答の取り込み)・[CSD第2版の試聴ページ](../runs/csd-listening-packet-20261122-a/artifacts/listening/index.html)・[CSDの回答手順](csd-listening-responses.md) |
| 物理MIDI | Chromeの許可画面、仮想CoreMIDIの押鍵・離鍵と切断、研究版とCLIの波形一致。既存入力の受動計測と、第9版でその採取元・PCMを再計算する手順を仮想対照で検証済み。CoreMIDI入出力は各0件 | 物理鍵盤を入力元とするブラウザのイベントとWorklet PCMの対応、および操作者が確認した機器情報。[受動収録の手順と対照](worklet-midi-coremidi-passive.md) |

### 再現結果

16項目・56合格実行の2,207判定と2,113出力（8,054,094,483バイト）、1,554件のケース定義参照を照合した。別途保存した不合格1件の全5出力（324,422バイト）も確認した。研究ワークスペースと `/private/tmp` から各88判定を通過して、要約はバイト一致した。現行Rust42試験、固定上流の比較19試験とMIDI 2試験、WASM・TypeScript・Viteの通常ビルドも通過した。第0〜7段階の64実行の回帰は12判定で先行の要約と一致した。監査3実行の729入力・14出力を照合し、採取ログ26,173バイトはRTL9210B-CGに保存した。環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4。[初回](../runs/stage7-evidence-update-20261122-v4-a/manifest.json)・[再実行](../runs/stage7-evidence-update-20261122-v4-repeat/manifest.json)・[第0〜7段階の回帰](../runs/plan-evidence-audit-20261122-stage7-v4-regression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-fourth-new
```

## 第5版の照合

第4版の56実行と16項目を保持し、受動MIDI、CSD試聴資料と回答、F2注釈の取込に関する5実行を追加した。比較する固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。ケースでは、各資料ID・受信バイト・採用時刻・集計結果を元データから復元でき、登録済みの4件の不合格も当初の理由で確認できると予測した。[第4版の保存定義](../runs/stage7-evidence-update-20261122-v4-repeat/artifacts/source/research/experiments/chimera-rebuild/cases/plan-evidence-stage7.json)・[第5版の事前登録](../runs/stage7-evidence-update-20261122-v5-repeat/artifacts/source/research/experiments/chimera-rebuild/cases/plan-evidence-stage7.json)

- **MIDI。** 固定上流の `connectMidi` は標準の許可を得た後に `attach` を呼ぶ。購読処理は入力IDとチャンネルごとに鍵を保持し、上位4ビットが `0x90` のとき速度が正なら押鍵、速度が0なら離鍵にする。購読を更新すると切断済み入力の保持鍵を解放する。上流の所有権テストは、同音を別入力で保持中の離鍵と、残りの入力の切断を順に確認する。今回の保存済み仮想対照では、独立したCoreMIDI受信と通常のWeb MIDIがどちらも `90 39 5D` と `90 39 00` を受信した。受信時刻の差は663.050 ms。研究版は48 kHzの出力フレーム15,872で音57を採り、47,872で解放した。どちらも128フレームの量子境界で、ブラウザと通常CLIの128,000 PCM標本はビット一致した。[上流の購読](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts#L48)・[所有権テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts#L65)・[受動測定の記録](worklet-midi-coremidi-passive.md#実行と結果)
- **CSD。** 固定上流の `compare_song` は楽譜と録音を読み、録音の標本数÷標本レートで合成の長さを決める。楽譜の最低・最高音を各7半音広げた解析範囲を両音声で使う。ビブラート試験は既知の周期波形でレートと深さを照合する。今回の監査では、試聴資料の18 WAVそれぞれのSHA-256、A・B・Cの対応表、回答列の定義を含む資料IDを再計算した。音声と対応表は第1版と一致し、試験CSV 2件の自然さの票を調整用・確認用に分けて保存済み集計と照合した。[上流の歌唱比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[周期変調の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1329)・[資料と回答の照合](csd-listening-packet-id.md)
- **F2。** 上流の `measure_pair` が録音と合成の対応音素を揃え、`Sig::formants` が母音内3か所の各300標本を12 kHzで解析する。欠測をスコアへ加えないことは上流の試験で確認する。監査は録音6窓と合成対照1窓の資料を照合した。試験用2人分の元CSVから一致1窓・不一致1窓を再計算し、録音窓の回答は測定2件、曖昧1件、測定不能1件と確認した。[上流の音素対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[フォルマント計測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[欠測のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1528)・[取込の試験記録](tsp-f2-human-intake.md)

4件の不合格もマニフェストと元の結果で照合した。物理MIDIの入力なしではイベントと音声が未観測となり、CSDの別資料IDとF2の表記変更済み試験回答・空欄では集計が作られなかった。今回のCoreMIDI入出力は各0件。実録音F2の人手注釈、人によるTSP・CSD試聴、物理MIDIのイベントと音響出力は[未確認の観測](#未確認の観測)に残した。[監査の要約](../runs/stage7-evidence-update-20261122-v5-repeat/summary.json)

### 第5版の再現結果

各102判定が通過し、研究ワークスペースと `/private/tmp` から得た要約はバイト一致した。16項目・61合格実行で、過去の2,248合格判定と2,162出力（8,072,457,450バイト）、ケース定義参照1,636件を照合した。現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、WASM・TypeScript・Viteの通常ビルドも通過した。監査2実行の642入力と12出力を独立に照合し、採取ログ計24,431バイトをRTL9210B-CGに保存した。環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4。[ワークスペースからの実行](../runs/stage7-evidence-update-20261122-v5-a/manifest.json)・[/tmpからの再実行](../runs/stage7-evidence-update-20261122-v5-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-fifth-new
```

## 第6版の照合

第5版の16項目・61実行を保持し、鳴禽の放射2実行、TSPとCSDの試聴資料・試験集計4実行を追加した。今回のケースでは、出力のハッシュに加え、枝流量の更新順序と試聴回答の資料ID・採点を元ファイルから再計算する条件を登録した。上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。[第5版の保存定義](../runs/stage7-evidence-update-20261122-v5-repeat/artifacts/source/research/experiments/chimera-rebuild/cases/plan-evidence-stage7.json)・[第6版の事前登録](../cases/plan-evidence-stage7.json)

- **鳴禽。** 上流は `Songbird::sample` で鳴管面積を更新してから `AirwayNetwork::step` を進める。くちばし端では圧力と並列R–L負荷の慣性流量が状態となり、抵抗枝の中点流量と慣性枝の前後平均を加えた後に時間差分を取る。192 kHzの最初の16内部サンプルで、くちばし入口の流量差が4、終端圧力差が6、放射流量差が8、終端への流入差が9サンプル後に現れることをCSVから再計算した。各版の放射流量から時間差分を復元し、固定開口のR–L負荷も圧力から独立に再計算した。追従0の圧力と流量はゼロ。採取後にJSON保存で停止した2実行では、元のエラーと確定版に一致する4本の観測CSVをそれぞれ照合した。[上流の鳴禽](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L109)・[放射の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)・[一様管の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[鳴禽の観測点](songbird-chirps-onset-radiation.md#くちばし入口と放射負荷の丸めを分ける)
- **TSP。** 上流の `compare tsp` は `measure_pair` で48 kHzの録音と合成の音素列を対応させ、区間ごとの観測を比較する。試験の `matching_keeps_only_the_same_phones_in_order` は同じ音素を同順に選ぶ規則を確認する。試聴の速さと文中の間には回答者の選択を用いる。試聴資料の36 WAVと元のフレーム数・ハッシュ、利用条件、資料IDを再計算した。試験CSV 2件の元行から、調整用12枠の提出7・記入3、確認用24枠の提出14・記入3と、速さ・間の票を照合した。未記入と試験CSVを人手区分で取り込もうとした各実行は拒否を再確認した。[上流の録音との比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[音素対応試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1544)・[試聴資料と回答の照合](tsp-active-duration-original.md#比較試聴のページと回答の取り込み)
- **CSD。** 上流の `compare_song` は注釈と同じ秒座標に合成を置く。ビブラートの比較は5 ms刻みの有声区間から周期と深さを推定し、既知の周期信号でHzとセントの値を確認する。試聴の揺れは0〜3などの無単位の評点で、自然さの選好と別に集計する。監査は試験CSV 2件の元バイト列とハッシュ、調整用・確認用の揺れの評価と自然さの票を照合した。空欄と、先に0点の入力を置き後続に既知の試験CSVを含めた組は、人手区分で集計が保存されなかった。メモリ上でTSPの試験回答を人手区分に変えた場合とCSDの確認用の評点1件を増やした場合は、それぞれ対象の判定だけが不合格になった。[上流の曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[ビブラートの既知信号試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)・[人手取込の検証](csd-listening-packet-id.md#人手回答として受け付ける条件)

実録音F2の人手注釈とTSP・CSDの人による試聴回答は未登録。CoreMIDI入出力は各0件で、物理鍵盤のイベントと対応する音響出力は未観測。[必要な一次記録と手順](#未確認の観測)

### 第6版の再現結果

16項目・67実行の2,343合格判定、2,250出力（8,089,738,770バイト）、1,646件のケース定義参照を照合した。別途、追加した6件の停止・拒否のハッシュと元の理由を確認した。ワークスペースと `/private/tmp` の各126判定が通過し、要約はバイト一致した。現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、WASM・TypeScript・Viteの通常ビルドも通過した。監査2実行の680入力・12出力を再照合し、採取ログ計24,305バイトはRTL9210B-CGに保存した。環境はmacOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4。[ワークスペースでの実行](../runs/stage7-evidence-update-20261122-v6-a/manifest.json)・[再実行のマニフェスト](../runs/stage7-evidence-update-20261122-v6-repeat/manifest.json)・[要約](../runs/stage7-evidence-update-20261122-v6-repeat/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-sixth-new
```

## 第7版で試聴回答の実行を照合する

固定上流の `compare tsp` は48 kHzの録音と合成を同じ音素の順で対応させ、調音速度を音素時間の合計秒数当たりの個数で求める。音素対応の試験では、同じ音素だけを両列で順に採ることを確かめる。`compare csd` は楽譜の秒座標上で録音と合成を揃え、音符の持続区間の音高を5 ms刻みで観測する。ビブラートは既知の周期変調を使う試験でHzとセントを照合する。今回の監査が受け付ける試聴結果は、TSP 18対の速さと間の選択、CSD 6区間の揺れの評点と自然さの選択で、音響量と試聴回答を別に数える。[上流の発話比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[音素対応試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1544)・[上流の歌唱比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[ビブラート試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L1330)

第7版の監査は `--tsp-listening-run` と `--csd-listening-run` で、通常CLIの人手区分で取り込んだ実行を受け付ける。集計実行と試聴資料のマニフェスト、登録済み資料のID、各WAV・元CSVのSHA-256を照合する。既知の試験回答と空欄を検査した上で、匿名IDごとの回答を音源へ戻し、調整用と確認用に分けて元CSVから集計を再計算する。回答の人手区分は提出時の申告に基づく。結果には実行ID、回答CSV数、区分ごとの予定行・提出行・記入行と票を記録する。片方だけ正しく登録された場合は試聴全体を一部取得とし、指定がない資料には未登録を表示する。以前の鳴禽・試聴・F2・MIDIの照合を保持し、TSPの書式変更を拒否した試験と試験区分の集計を加えた。[事前登録](../cases/plan-evidence-stage7.json)・[回答を照合する処理](../tools/audit_stage7_listening_runs.py)

人の回答を受領し、対応する[取込手順](#未確認の観測)で実行を保存した後、研究ワークスペースから次のように監査する。実行IDは取得済みの資料に対応するものだけを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-listening-new \
  --tsp-listening-run tsp-listening-human-new \
  --csd-listening-run csd-listening-human-new
```

保存済みのTSP・CSDの試験集計を両方指定すると、通常入口はそれぞれの出所区分で拒否した。外部作業ディスクの一時領域に隔離した試験入力で、片方だけの登録、CSVハッシュ・資料ID・票数の不一致を両資料について検出した。この対照で使った回答は実際の試聴結果の記録に含まれない。実際の試聴回答、実録音F2注釈、物理MIDIのイベントと対応する音響出力は引き続き未取得。[試験集計の拒否](../runs/stage7-evidence-update-20261123-listening-reject-fixtures/summary.json)・[未登録時の監査](../runs/stage7-evidence-update-20261123-listening-a/summary.json)

16項目・69実行で、2,349件の合格判定と2,262出力（8,089,745,853バイト）、1,648件のケース定義参照を照合した。研究ワークスペースと `/tmp` から各128判定に合格し、要約と入力一覧が一致した。現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、WASM・TypeScript・Viteの通常ビルドが通過した。試験集計を明示した不合格も含め、3実行の1,042入力・13出力を独立に照合した。採取ログ計24,300バイトをRTL9210B-CGに保存した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4。[再実行の要約](../runs/stage7-evidence-update-20261123-listening-repeat/summary.json)・[再実行のマニフェスト](../runs/stage7-evidence-update-20261123-listening-repeat/manifest.json)

## 第8版でF2注釈を照合する

上流のF2測定は12 kHzの300標本窓でLPCの極から候補を得る。固定上流の `Sig::formants` は母音内の3窓で同じ条件を使い、得られたF2を中央値にまとめる。欠測は上流の試験で費用が計算されないことを確認する。手動注釈との照合では、母音全体を一つの値にはまとめず、録音IDと12 kHzの標本範囲で六つの窓を一つずつ対応付ける。[固定上流のF2採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[欠測の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)・[注釈の取込と差の算出](tsp-f2-human-intake.md#実録音の注釈を第7段階の監査で照合する)

人手区分で取り込んだ実行は `--f2-annotation-run` で監査に指定できる。資料ID、WAV・図、元の回答CSV、保存した判定、LPCの採択元を照合する。実録音の各窓の件数・中央値と既定／プリエンファシス無適用のF2偏差を `coverage.human_f2_annotations` に記録する。判定者の数値が既定の100 Hz超に分かれた窓と数値が無い窓には偏差を付けない。合成対照だけに注釈を付けても、実録音の取得は未登録として表示する。[事前登録](../cases/plan-evidence-stage7.json)・[照合処理](../tools/audit_stage7_f2_annotations.py)

実録音の注釈を受領し、[資料と取込手順](#未確認の観測)を使って集計した後、研究ワークスペースから取得済みのF2実行IDを指定する。`--tsp-listening-run` と `--csd-listening-run` に対応する試聴の実行IDも同時に指定できる。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-new \
  --f2-annotation-run tsp-f2-human-new
```

通常入口では、保存済みの試験集計を人手注釈の実行IDとして指定すると拒否した。取り込み側も所見の改行だけを書き換えた既知の試験CSVを拒否した。隔離した対照では6窓中5窓と全6窓の受領状態を区別し、単独測定、一致、不一致、判断困難、合成対照だけの記入をそれぞれ確かめた。100 Hz以内の対照では中央値2,095 Hzを使って値を再計算し、範囲335 Hzの不一致の対照には偏差を付けなかった。実際のF2注釈とTSP・CSDの試聴回答は未登録。CoreMIDI入出力は各0件で、物理鍵盤のイベントと音響出力は未観測。[監査での拒否](../runs/stage7-f2-20261123-reject-synthetic/summary.json)・[取込での拒否](../runs/stage7-f2-20261123-reject-multiline/manifest.json)・[現時点の要約](../runs/stage7-evidence-update-20261123-f2-repeat/summary.json)

第7版の16項目・69実行と2,262出力を保持した。研究ワークスペースと `/tmp` から各128判定を通過し、要約と入力一覧は一致した。現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常Webビルドも通過した。F2の取込と拒否を含む5実行の1,069入力・17出力を独立に照合し、採取物26,023バイトをRTL9210B-CGに保存した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4。[再実行のマニフェスト](../runs/stage7-evidence-update-20261123-f2-repeat/manifest.json)

## 第9版で物理MIDIの収録を照合する

固定上流の `Keys` が開く `setMidi` は `connectMidi` から `attach` へ進み、ポートIDとチャンネルで押鍵の所有者を管理する。MIDI 1.0では `0x90` の正ベロシティが押鍵、`0x80` とベロシティ0の `0x90` が離鍵。最後の所有者が離れると `noteOff` が保持音の一覧を更新し、通常の発声ではゲートも更新する。固定上流の試験は同じ音の複数所有者、両離鍵形式、抜線、権限要求中の切断を確認する。[上流のMIDI入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/Keys.tsx)・[保持とルーティング](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[発声状態の更新](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/store.ts)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts)

第9版の `--physical-midi-run` は収録時のUIDとエンドポイント一覧、ネイティブ受信、同じポートの信頼済みWeb MIDI、通常画面の保持音を照合する。保持時間はCoreMIDIの到着差を100万で割ってmsに換算し、ブラウザのイベント時刻差もそれぞれの時計で求める。Workletの採用フレームを64で割って保存ケースの制御位置に対応させ、押鍵400 ms後から離鍵までのF0とゲートを独立計算と比較する。音57の目標は220 Hz。押鍵前と離鍵後の無音、48 kHzの全float32 PCMとCLIの一致も再計算する。機器一覧と操作者の機器情報を収録元の記録に残す。音声の取得点はスピーカーへ送る前のデジタルPCM。[事前登録](../cases/plan-evidence-stage7.json)・[監査の実装](../tools/audit_stage7_physical_midi.py)・[収録と監査のコマンド](worklet-midi-coremidi-passive.md#実行と結果)

通常入口では仮想入力と入力欠測を別々の理由で拒否した。仮想対照を再計算すると、CoreMIDIとWeb MIDIの保持は663.050042 msと663.0 ms。Workletの採用フレームは15,872と47,872で、128,000点のPCMはビット一致した。隔離した対照で離鍵を `90 39 00` から `80 39 40` に置き換えても、同じ13判定と観測値を得た。別チャンネル、信頼済みでないイベント、ブラウザ側399 msの保持、PCMの1点変更では対応する判定が不合格になった。PCMの差は変更した20,000フレーム目で見つかった。[仮想入力の拒否](../runs/stage7-midi-20261123-reject-fixture/summary.json)・[入力なしの拒否](../runs/stage7-midi-20261123-reject-no-input/summary.json)・[独立検証のスクリプト](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-stage7-physical-midi-20261123.py)・[検算結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-stage7-physical-midi-20261123.json)

研究ワークスペースと `/tmp` から各128判定に合格し、要約と入力一覧が一致した。前版の16項目・69実行・2,262出力、現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常Webビルドを照合した。拒否の対照を含む4実行の1,416入力・14出力をサイズとSHA-256で独立に検証し、採取ログ計24,120バイトをRTL9210B-CGに保存した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4。現行のCoreMIDI入出力は各0件。物理鍵盤、実録音のF2注釈、人によるTSP・CSDの試聴回答は未取得。[通常実行のマニフェスト](../runs/stage7-evidence-update-20261123-midi-a/manifest.json)・[再実行の要約](../runs/stage7-evidence-update-20261123-midi-repeat/summary.json)

## 第10版で鳴禽の短区間と全区間を照合する

固定上流の `render::creature` はコールのキーを `CreatureVoice::render` に渡す。内部サンプルごとに `Songbird::sample` が左右の鳴管開口を更新し、`AirwayNetwork::step` が気道を進める。総放射流量と前回流量の差に内部レートを掛けてcm³/s²とし、97タップのFIRで4点に1回の出力へ間引く。ゲインを掛けてから前回の入力と出力を使ってDCを除き、振幅を制限してf32のPCMへ丸める。固定上流の一様管試験は時間応答と周波数応答を、鳴き声の試験はTypeScriptとの包絡とテレメトリを照合する。[コール描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[気道の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L107)・[放射後退差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)・[間引きとDC除去](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)・[一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[鳴き声の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L136)

第9版の16項目と69実行を基準に固定した。今回追加する監査では、短区間の入口流量に最初に現れる変化と、くちばしから放射までの20列×64点を、各条件の採取CSVから照合する。全コールは放射の初差を内部1033点と1089点、間引きとDC除去を出力258点と275点に再現し、全48,510点のPCMが一致すると予測した。初回の停止は、同じ入力の77フレーム分割で `--no-trace` が拒否されたコマンド、理由、停止時点までの成果を照合する。[事前登録](../cases/plan-evidence-stage7.json)・[第9版の保存記録](../runs/stage7-evidence-update-20261123-midi-repeat/manifest.json)

短区間では235点制御の53点後、256点制御の18点後の入口流量が予測値と一致した。追従0を含む3条件で各1,280値が上流とビット一致し、保存した放射流量から後退差分を再現した。全コールでは放射、間引き、DC除去の初差と件数を再計算し、登録値と一致した。44.1 kHzの全48,510出力点は、標準版・実験版・上流のCSV、両版の77・128フレーム分割のWAV、FIRとDC除去から独立に求めたPCMで一致した。初回の停止で記録された4出力を再照合し、停止前の128フレーム版のWAV・CSV・設定JSONが成功版とバイト一致した。[鳴禽の追加判定](../runs/stage7-evidence-update-20261123-songbird-repeat/summary.json)・[初回の停止記録](../runs/songbird-chirps-full-pcm-44100-20261123/manifest.json)

第9版の登録69実行と128判定を維持し、2実行と28判定を追加した。16項目・71実行の2,462合格判定と2,284出力（8,129,980,463バイト）、1,656件のケース定義参照を照合した。研究ワークスペースと `/tmp` の各156判定、現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常Webビルドが通過した。要約と入力一覧は両実行で一致し、計778入力と12出力をハッシュ照合した。監査の採取ログ計24,520バイトはRTL9210B-CGに保存した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、Bun 1.4.4で実行した。[初回のマニフェスト](../runs/stage7-evidence-update-20261123-songbird-a/manifest.json)・[再実行のマニフェスト](../runs/stage7-evidence-update-20261123-songbird-repeat/manifest.json)

隔離した照合では、短区間のセル圧1点の変更で該当する一致判定が落ちた。全区間のPCM1点を変更すると、差分集計、2つのWAV、PCMの独立計算との照合で不合格となった。停止マニフェストの登録ハッシュを変更すると停止理由の照合が不合格となった。実録音F2の人手注釈、TSP・CSDの試聴回答、実機MIDIは未登録で、CoreMIDI入出力は各0件だった。[差分対照と保存物の独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/stage7-songbird-audit-20261123-verification.json)・[必要な一次観測](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-songbird-new
```

## 試聴とF2注釈の資料を別の環境で開く

固定上流の `measure_pair` は対応する音素を録音と合成から取り、`Sig::formants` は12 kHzの300標本窓からF2をHzで求める。音響量と試聴回答を対応させるため、評価側は波形と図、観測窓番号、資料IDを保持する。歌唱の `compare_song` は譜面の時刻を基準に周期性やビブラートを測り、試聴では別に揺れと自然さを記録する。区間・音源を対応させる表は回答集計だけに使う。既存のブラウザ試験は音声の再生、図の読み込み、カンマ・引用符・改行を含むCSV出力を検証する。[発話の比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[F2の窓](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[歌唱比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[注釈のブラウザ試験](../../../../web/prototypes/chimera-research/tools/verify-tsp-f2-annotation.mjs)

登録済みの評価者用HTMLは音声と図に相対パスを使い、回答をブラウザ内でCSVにする。研究ワークスペースの見かけのファイルはRTL9210B-CGへのリンクだった。ZIPの各項目を通常ファイルにすれば、同じ外部ディスクを持たない展開先でもページを開けて、元の資料IDのCSVが得られると予測した。試聴18対、歌唱6区間、F2注釈7窓の入力ハッシュを固定してから変換する。実録音の利用条件はTSP試聴とF2注釈のZIPに同じ通知を含め、CSDは元のREADMEを含める。[比較条件](../cases/stage7-review-archives.json)・[元のTSP試聴](tsp-active-duration-original.md#比較試聴のページと回答の取り込み)・[元のF2注釈資料](tsp-f2-annotation.md#使い方)・[元のCSD試聴と集計](csd-listening-responses.md)

| 資料 | 観測範囲 | ZIP内のファイル数 | 回答の取込で指定する元の実行ID |
| --- | --- | ---: | --- |
| [TSP試聴](../runs/stage7-review-archives-20261123-repeat/artifacts/tsp-listening.zip) | 18対、音声36件 | 39 | `tsp-listening-responses-20261122-final` |
| [CSD試聴](../runs/stage7-review-archives-20261123-repeat/artifacts/csd-listening.zip) | 6区間、音声18件 | 21 | `csd-listening-packet-20261122-a` |
| [F2注釈](../runs/stage7-review-archives-20261123-repeat/artifacts/tsp-f2.zip) | 7窓、音声7件、図7枚 | 17 | `tsp-f2-annotation-20261122-repeat` |

各ZIPを個別のフォルダに展開し、`index.html` を開く。ページから書き出したCSVが取込の入力になる。生成したZIPは評価者用のページ、音源、図、空欄の回答用CSV、利用条件の通常ファイルだけを収めている。音源対応表と採択値は元の実行に保存されている。展開先のChrome 157.0.8103.79で音声61件とF2の図7枚、モバイル幅、資料IDとCSVの書き出しを検証した。TSP試聴とF2注釈のブラウザ試験CSVは元の出力とバイト一致した。3件とも通常の取込CLIで試験区分のまま集計され、元の資料IDを確認した。[TSP試験CSVの取込](../runs/stage7-review-archives-tsp-response-20261123/summary.json)・[CSD試験CSVの取込](../runs/stage7-review-archives-csd-response-20261123/summary.json)・[F2試験CSVの取込](../runs/stage7-review-archives-f2-response-20261123/summary.json)

研究ワークスペースと `/tmp` の各27判定を通過し、3つのZIPと要約がバイト一致した。別の `unzip` でZIPのCRCを検査し、計77ファイルを展開して元のSHA-256と照合した。試験CSVの取込を含めて273入力と33出力をハッシュ照合し、出力計31,271,568バイトをRTL9210B-CGに保存した。macOS 15.6.1 arm64、Python 3.14.4、Node.js 24.19.0で実行した。評価者からの回答と物理MIDIは未取得。[再実行の保存記録](../runs/stage7-review-archives-20261123-repeat/manifest.json)・[独立照合コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-stage7-review-archives-20261123.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/prepare_stage7_review_archives.py stage7-review-archives-local
```

## 第11版でMIDI入力の候補名と端子数を照合する

第10版の16項目・71実行を保持し、受動収録で2つの名前候補が1端子に対応する条件を追加した。成功版と修正前のChrome記録で、ともに候補2件と開いた端子1件を照合した。修正前はネイティブ受信が待機に入った後、押鍵前の端子数照合で60秒後に停止した。成功版では同じ端子のCoreMIDI受信と信頼済みWeb MIDIの押鍵・離鍵が一致し、48 kHzの128,256フレームがCLIとビット一致した。[比較条件と読解](worklet-midi-coremidi-passive.md#端子名と表示名が異なる入力)・[監査のケース定義](../cases/plan-evidence-stage7.json)

72実行の2,293出力と現行Rust 52試験、固定上流19比較試験・2ブラウザ側試験、通常Webビルドを確認し、161判定に通過した。全体監査にこの版を指定し、214判定に通過した。収録の仮想入力を物理MIDIの一次記録として指定すると、入力元の照合で拒否した。物理入力は0件で、実録音F2の人手注釈とTSP・CSDの試聴回答も未登録だった。[第11版の結果](../runs/stage7-evidence-update-20261123-midi-aliases/summary.json)・[仮想入力の拒否](../runs/stage7-midi-alias-reject-fixture-20261123/summary.json)・[全体監査](../runs/plan-completion-release-v6-midi-aliases/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-midi-aliases-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-midi-aliases-new \
  --stage7-run stage7-midi-aliases-new
```

## 第12版で選択外のMIDI入力の購読解除を照合する

第11版の161判定と72実行を保持し、無操作の仮想端子を追加した受動収録を登録した。修正前後のChrome記録で開いた2端子、購読対象の端子ID、選択端子だけのNote On・Offを確認した。修正前の既知の不合格は選択外の購読1件で、CLIとのPCM比較は通過していた。修正後は購読0件となり、選択端子の音57の採用点と48 kHzの129,024フレームを元のWAVから再照合した。[事前登録と観測点](worklet-midi-coremidi-passive.md#選択外の入力が接続された状態での購読解除)・[修正前のマニフェスト](../runs/worklet-midi-coremidi-idle-before-20261123/manifest.json)・[第12版のケース](../cases/plan-evidence-stage7.json)

73実行の2,302出力と現行Rust 52試験、固定上流の19比較試験・2ブラウザ側試験、通常Webビルドを確認し、169判定を通過した。この版を指定した全体監査は99実行の2,128出力と214判定を通過した。CoreMIDI入出力は各0件で、物理MIDI、実録音F2の人手注釈、TSP・CSDの試聴回答は未登録。[第12版の監査結果](../runs/stage7-evidence-update-20261123-midi-idle/summary.json)・[全体監査の結果](../runs/plan-completion-release-v6-midi-idle/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-midi-idle-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-midi-idle-new \
  --stage7-run stage7-midi-idle-new
```

## 第13版で同名MIDI入力と受信元を照合する

第12版の73実行・169判定を保ち、同名の仮想端子を2つ開いた受動収録を追加した。保存済みの修正前の採取では両端子が開いたまま録音前に停止し、修正後は選択UIDとChromeの受信IDが一致した。CoreMIDIとChromeの押鍵・離鍵、32,000フレーム間隔の採用点、48 kHzの全128,384フレームを元の記録から再計算した。Chrome側の送信元やメッセージ数を変えた対照は、収録後の対応付けで拒否した。[読解と比較条件](worklet-midi-coremidi-passive.md#同名の入力を受信イベントで照合する)・[第13版の定義](../cases/plan-evidence-stage7.json)

74実行・2,311出力を照合し、169件の既存判定を含む176判定を通過した。現行Rust 52試験、固定上流の19比較試験・2ブラウザ側試験、通常Webビルドも通過した。物理鍵盤での収録は後日に回す。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録で、次は既知F2の対照を使って採択規則を検証する。[第13版の監査結果](../runs/stage7-evidence-update-20261123-midi-same-name/summary.json)・[一次記録の取込](#未確認の観測)

第13版を指定した全体監査は、99実行の2,128出力を照合して214判定に通過した。仮想収録の修正前と回帰を含む7実行の2,364入力・53出力を別にハッシュ照合し、実体63,321,115バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-midi-same-name/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-midi-same-name-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-midi-same-name-new \
  --stage7-run stage7-midi-same-name-new
```

## 第14版で既知F2の採択の切り替わりを照合する

第13版の74実行・176判定を保ち、設計F2を2075 Hzに固定した9波形を追加した。上流Rustが返した公開極からF1・F2の採択を再計算した。追加共鳴760 Hzでは6窓とも設計F2近傍を採り、800 Hzでは6窓とも追加共鳴の近傍を採った。800〜1020 Hzの36窓では設計F2近傍の極も周波数条件を満たしていた。録音の正解値は引き続き人手注釈として扱う。[事前登録・読解・全窓の実測](tsp-f2-intervening-resonance.md)・[第14版のケース](../cases/plan-evidence-stage7.json)

75実行・2,317出力を照合し、179判定を通過した。現行Rust 52試験、固定上流19比較試験・2ブラウザ側試験、通常Webビルドが通過した。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録で、物理鍵盤の採取は後日に回す。[第14版の要約](../runs/stage7-evidence-update-20261123-f2-intervening/summary.json)・[一次記録の取込](#未確認の観測)

第14版を指定した全体監査は、99実行の2,128出力を照合して214判定に通過した。合成対照の2実行と両監査の969入力・24出力を別にハッシュ照合し、実体2,835,477バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-f2-intervening/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-intervening-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-intervening-new \
  --stage7-run stage7-f2-intervening-new
```

## 第15版で励振のF0による採択の変化を照合する

第14版の75実行・179判定を保持し、設計F2と追加共鳴を固定してF0だけを変えた対照を加えた。21波形・126窓で、上流が返した公開極からF2の採択を再計算し、固定窓に入る励振位相を標本番号から照合した。F0 125 Hzと比較して33組でF2の採択分類が変わった。低域を採った全48窓に、周波数条件を満たす設計F2近傍の極が残っていた。[仮説と比較条件](tsp-f2-intervening-excitation.md)・[第15版の登録](../cases/plan-evidence-stage7.json)

76実行の2,323出力を照合し、182判定を通過した。現行Rust 52試験、固定上流19比較試験・2ブラウザ側試験、通常Webビルドにも通過した。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の採取は後日に回す。[第15版の要約](../runs/stage7-evidence-update-20261123-f2-excitation/summary.json)・[一次記録の取込](#未確認の観測)

第15版を指定した全体監査は、99実行の2,128出力を照合し214判定を通過した。比較2実行と両監査の986入力・24出力をハッシュ照合し、実体6,563,828バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-f2-excitation/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-excitation-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-excitation-new \
  --stage7-run stage7-f2-excitation-new
```

## 第16版で窓内の励振位相を照合する

第15版の76実行・182判定を保持し、F0 125 Hzと追加共鳴760 Hzを固定した96位相の対照を加えた。保存した上流の公開極から全576窓の相対位相、採択、間隔を再計算した。両次数で全96位相が設計F2近傍を採り、位相による採択の切り替わりを予測した2項目は成立しなかった。監査はこれらの判定結果を記録したまま、77実行の2,329出力と185判定を照合した。現行Rust 52試験、固定上流19比較試験・2ブラウザ側試験、通常Webビルドが通過した。[比較条件と結果](tsp-f2-intervening-phase.md)・[第16版の要約](../runs/stage7-evidence-update-20261123-f2-phase/summary.json)

第16版を指定した全体監査は、別の作業ディレクトリから99実行の2,128出力と214判定を照合した。比較2実行と両監査の985入力・24出力のSHA-256を独立に確認した。出力の合計3,537,895バイトのうち、波形・固定上流出力・試験ログなど1,295,003バイトはRTL9210B-CGにある。実録音F2の人手注釈、TSP・CSDの試聴回答は未登録。物理鍵盤の採取は後日に回す。[全体監査](../runs/plan-completion-release-v6-f2-phase/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-phase-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-phase-new \
  --stage7-run stage7-f2-phase-new
```

## 第17版で共鳴780 Hzの切り替わりを照合する

第16版までの77実行・185判定を保持し、780 Hzの全位相対照を加えた。公開極から576窓の採択、相対位相、F1と低域極の間隔を再計算した。次数14の採択は低域58位相・設計F2近傍38位相で、12組の隣接位相が200 Hzの境界をまたいだ。次数12を含め、低域極を選んだ462窓すべてで設計F2近傍の適格な極が残った。第7段階は78実行の2,335出力と189判定を照合した。[比較条件と結果](tsp-f2-intervening-phase-midpoint.md)・[第17版の要約](../runs/stage7-evidence-update-20261123-f2-phase-midpoint/summary.json)

第17版を指定した全体監査は、別の作業ディレクトリから99実行の2,128出力と214判定に通過した。現行Rust 52試験、固定上流19比較試験・2ブラウザ側試験、通常Webビルドも通過した。780 Hzの2実行、760 Hzの回帰確認、両監査に登録した1,021入力・30出力のSHA-256を照合し、波形・上流出力・試験ログなど1,926,378バイトをRTL9210B-CGに保存した。実録音F2の注釈、TSP・CSDの試聴回答は未登録。物理鍵盤の採取は後日に回す。[全体監査](../runs/plan-completion-release-v6-f2-phase-midpoint/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-phase-midpoint-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-phase-midpoint-new \
  --stage7-run stage7-f2-phase-midpoint-new
```

## 第18版で実録音の窓移動を照合する

第17版の78実行・189判定を保持し、録音 `seems` の前後5 msの比較を加えた。上流の保存済みの生根と公開極から窓位置、F2の採択、帯域幅による選別を再計算した。全121窓で低域極が採られ、約2.3 kHzの極も適格だった。低域の帯域幅が600 Hzを超えることで採択が変わるという予測は成立しなかった。第7段階は79実行の2,341出力と192判定に通過した。[実録音の窓比較](tsp-lpc-recording-window-shift.md)・[第18版の要約](../runs/stage7-evidence-update-20261123-f2-recording-window-shift/summary.json)

第18版を指定した全体監査は、別の作業ディレクトリから99実行・214判定に通過した。比較2実行と両監査の987入力・24出力をSHA-256で照合し、計測用波形・固定上流出力・試験ログなど320,194バイトをRTL9210B-CGに保存した。実録音F2の注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の採取は後日に回す。[全体監査](../runs/plan-completion-release-v6-f2-recording-window-shift/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-recording-window-shift-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-recording-window-shift-new \
  --stage7-run stage7-f2-recording-window-shift-new
```

## 第19版でTSP候補レポートを照合する

第18版までの79実行・192判定を保持し、既存のTSP計測CLIの候補出力と照合実行を加えた。全185窓の候補を再集計し、複数候補177窓、F1なし3窓、波形外3窓を確認した。固定上流と独立LPCの採択と中央値に一致し、オプション有無の既存要約と固定上流出力もバイト一致した。第7段階は81実行の2,348出力と196判定を通過した。[候補レポートの使い方](tsp-f2-candidate-report.md)・[第19版の要約](../runs/stage7-evidence-update-20261123-f2-candidate-report/summary.json)

第19版を指定した全体監査は、別の作業ディレクトリから99実行の2,128出力と214判定に通過した。計測3実行と照合・監査の計6実行に登録した1,049入力・30出力をSHA-256で照合し、診断JSON・固定上流出力・ログなど743,414バイトはRTL9210B-CGに保存した。実録音F2の注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[全体監査](../runs/plan-completion-release-v6-f2-candidate-report/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-candidate-report-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-candidate-report-new \
  --stage7-run stage7-f2-candidate-report-new
```

## 第20版で同じ母音の3音源を照合する

第19版までの81実行・196判定を保持し、同じ /i/ の3音源・15窓の比較を加えた。固定上流の生根と公開極から標準6組の差を再計算した。低域極を採った録音に対し、両合成の対応する全6窓では登録した低域の生根が得られなかった。高域候補同士で比べた差は標準窓で最大111.36 Hzだった。第7段階は82実行の2,354出力と199判定を照合した。[3音源の比較](tsp-f2-source-comparison.md)・[第20版の要約](../runs/stage7-evidence-update-20261123-f2-source-comparison/summary.json)

第20版を指定した全体監査は、別の作業ディレクトリから99実行の2,128出力と214判定に通過した。比較2実行と両監査の1,001入力・24出力のSHA-256を照合し、窓標本・上流出力・ログなど107,671バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[全体監査](../runs/plan-completion-release-v6-f2-source-comparison/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-source-comparison-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-source-comparison-new \
  --stage7-run stage7-f2-source-comparison-new
```

## 第21版で発話中の固定断面と線形応答を照合する

第20版までの82実行・199判定を保持し、`seems` の /i/ の1.165秒で断面を採った対照を加えた。両版の通常描画と同一のPCMが出ることを確認し、線形流量比から2,187.47 Hzの高域ピークを再計算した。断面を固定したピーク差は0.1 Hz以下で判別不能、PCMの高域LPC極の差は15.70 Hzだった。第7段階は83実行の2,362出力と202判定を通過した。[比較と判定の改訂](tsp-seems-tract-transfer.md)・[第21版の要約](../runs/stage7-evidence-update-20261123-seems-tract/summary.json)

第21版を指定した全体監査は、別の作業ディレクトリから99実行の2,128出力と214判定に通過した。比較3実行と両監査の1,379入力・36出力をSHA-256で照合し、断面・線形応答・試験ログなど370,540バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[全体監査](../runs/plan-completion-release-v6-seems-tract/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-seems-tract-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-seems-tract-new \
  --stage7-run stage7-seems-tract-new
```

## 第22版で声門流量からPCMまでを照合する

第21版までの83実行・202判定を保持し、`seems` の同じ25 ms窓のスペクトルと出力段の再計算を加えた。声門流量の高域パワー分布の距離0.205を保存したスペクトルから確認した。固定上流プローブの公開極から、版間の差が放射の間引き直後15.74 Hz、PCM15.70 Hzであることを再計算した。各版の入力を共通の出力段に通した再計算は先頭56,600フレームでPCMと一致した。第7段階は84実行の2,370出力と205判定を通過した。[観測と出力段の再計算](tsp-seems-spectrum-stages.md)・[第22版の要約](../runs/stage7-evidence-update-20261123-seems-spectrum-stages/summary.json)

第22版を指定した全体監査は、別の作業ディレクトリから99実行の2,128出力と214判定に通過した。比較2実行と両監査の1,257入力・28出力をSHA-256で照合し、窓波形・スペクトル・試験ログなど919,117バイトをRTL9210B-CGに保存した。実録音のF2注釈、TSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[全体監査](../runs/plan-completion-release-v6-seems-spectrum-stages/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-seems-spectrum-stages-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-seems-spectrum-stages-new \
  --stage7-run stage7-seems-spectrum-stages-new
```

## 第23版でドリフトの寄与を照合する

第22版までの84実行・205判定を保持し、固定上流のドリフト振幅だけを5セントから0にした `seems` の対照を加えた。保存した113,200標本の瞬時F0からセント差を再計算し、乱数とフィルターから求めた系列に照合した。保存した声門流量スペクトルと固定上流LPCから、研究版との分布距離の縮小0.092069とLPC極の絶対差の縮小9.7539 Hzを再計算した。第7段階は85実行の2,380出力と209判定に通過した。[対照の結果](tsp-seems-drift-only.md)・[第23版の要約](../runs/stage7-evidence-update-20261123-seems-drift-only/summary.json)

第23版を指定した全体監査は、別の作業ディレクトリから99実行の2,128出力と214判定に通過した。比較2実行と両監査の1,033入力・32出力をSHA-256で照合した。観測窓、瞬時F0、スペクトルや試験ログなど1,023,792バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[全体監査](../runs/plan-completion-release-v6-seems-drift-only/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-seems-drift-only-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-seems-drift-only-new \
  --stage7-run stage7-seems-drift-only-new
```

## 第24版で圧差の再入力を照合する

第23版までの85実行・209判定を保持し、`seems` の /i/ で、ドリフト停止の声帯へ通常条件の圧力差を再入力する対照を加えた。監査は保存した113,200標本の圧差を振動器の入力と照合し、平滑化後の圧差の上限判定を再計算した。25 msの両条件で圧力成分は2,400標本すべてで上限に達した。声門流量の高域パワー分布の距離3.42×10⁻¹⁰とLPC極の移動−1.42×10⁻⁶ Hzも保存出力から確認した。第7段階は86実行の2,392出力と213判定に通過した。[比較と圧差の記録](tsp-seems-pressure-replay.md)・[第24版の要約](../runs/stage7-evidence-update-20261123-seems-pressure-replay/summary.json)

第24版を指定した全体監査は99実行の2,128出力と214判定に通過した。比較2実行、先行ドリフト計測の再確認と両監査の1,094入力・46出力をSHA-256で照合した。圧差系列、解析窓、スペクトルと試験ログなど20,817,009バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-seems-pressure-replay/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-seems-pressure-replay-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-seems-pressure-replay-new \
  --stage7-run stage7-seems-pressure-replay-new
```

## 第25版で周期長ジッターを照合する

第24版までの86実行・213判定を保持し、`seems` の /i/ の周期長ジッターを、固定上流と研究版でそれぞれ0から0.00455にする対照を加えた。監査は保存した先頭113,200内部標本から周期境界、位相と振幅倍率を再計算した。両版で第872標本から位相が分かれ、ジッターの値をそろえた条件の位相と瞬時F0は両版で一致した。固定LPCからジッター追加に伴う極の移動が上流−3.6422 Hz、研究版−3.5512 Hzであることを再計算した。第7段階は87実行の2,407出力と218判定に通過した。[比較の記録](tsp-seems-period-jitter.md)・[第25版の要約](../runs/stage7-evidence-update-20261123-seems-period-jitter/summary.json)

第25版を指定した全体監査は99実行の2,128出力と214判定に通過した。比較2実行、圧差ケースの再確認と両監査の1,348入力・54出力をSHA-256で照合した。周期系列、圧差系列、観測窓、スペクトルや試験ログなど20,962,521バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-seems-period-jitter/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-seems-period-jitter-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-seems-period-jitter-new \
  --stage7-run stage7-seems-period-jitter-new
```

## 第26版で周期振幅を照合する

第25版までの87実行・218判定を保持し、`seems` の /i/ でシマーだけを0または0.042にする対照を加えた。監査は保存した瞬時F0から周期境界と振幅倍率を独立計算し、両版で第871内部標本から振幅差が生じることを確認した。シマーを揃えた両条件のLPC入力300標本とLPC極が一致し、声門流量の高域スペクトルの距離は最大2.15×10⁻¹⁴だった。第7段階は88実行の2,423出力と223判定に通過した。[周期振幅の比較](tsp-seems-amplitude-shimmer.md)・[第26版の要約](../runs/stage7-evidence-update-20261123-seems-amplitude-shimmer/summary.json)

第26版を指定した全体監査は99実行の2,128出力と214判定に通過した。比較2実行、ジッターケースの再確認と両監査の1,485入力・59出力をSHA-256で照合した。周期系列、窓、スペクトル、試験ログなど18,340,570バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-seems-amplitude-shimmer/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-seems-amplitude-shimmer-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-seems-amplitude-shimmer-new \
  --stage7-run stage7-seems-amplitude-shimmer-new
```

## 第27版で初期舌先と発話前の放射を照合する

第26版までの88実行・223判定を保持し、`seems` の初期舌先だけを固定上流に揃えた対照を加えた。初期断面からセルごとの面積と長さの差を再計算し、冒頭2,400 PCMフレームの最大差が0.0025693944から0になったことを保存波形で照合した。同区間の口端流量の最大差は4.22×10⁻¹² cm³/sで、母音中央のLPC入力も一致した。第7段階は89実行の2,440出力と227判定に通過した。[初期舌先の計測](tsp-seems-initial-tip.md)・[第27版の要約](../runs/stage7-evidence-update-20261123-seems-initial-tip/summary.json)

第27版を指定した全体監査は99実行の2,128出力と214判定に通過した。比較2実行、発話中の断面計測の再確認、両監査の1,496入力・54出力をSHA-256で照合した。放射系列、初期断面、PCMの観測窓と試験ログなど2,529,524バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-seems-initial-tip/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-seems-initial-tip-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-seems-initial-tip-new \
  --stage7-run stage7-seems-initial-tip-new
```

## 第28版で確認用12発話の全PCMを照合する

第27版までの89実行・227判定を保持し、既存の確認用12発話について体型別ゲイン、初期舌先と音源の揺らぎを固定上流に揃えた。監査では保存した両版の全PCMから最大差1.86×10⁻⁹と、全12発話が1×10⁻⁶以下であることを再計算した。計画音素の境界と−35 dBの発話区間も12発話で一致した。第7段階は90実行の2,481出力と231判定に通過した。[確認用発話の計測](tsp-held-out-matched-speech.md)・[第28版の要約](../runs/stage7-evidence-update-20261123-held-out-matched-speech/summary.json)

第28版を指定した全体監査は99実行の2,128出力と214判定に通過した。比較2実行と両監査の1,396入力・94出力をSHA-256で照合した。PCM、発話入力、計画、試験ログなど23,013,330バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-held-out-matched-speech/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-held-out-matched-speech-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-held-out-matched-speech-new \
  --stage7-run stage7-held-out-matched-speech-new
```

## 第29版で設定を揃えたPCMの強勢母音を照合する

第28版までの90実行・231判定を保持し、設定を揃えたPCMで既存のTSP確認用4発話・12強勢母音を再計測した。監査では固定出力と窓別比較を突き合わせ、開始を揃えた60窓でF2採択値が許容差内に収まることを確認した。同じ研究版PCMで保存MFA境界だけを変えたときは、開始がずれた15窓すべてでF2が変わった。 `seems` の中央窓の合成F2は2,228.15 Hz、録音の採択は993.37 Hzだった。第7段階は91実行の2,488出力と235判定に通過した。[母音窓と採択の比較](tsp-matched-speech-formants.md)・[第29版の要約](../runs/stage7-evidence-update-20261123-matched-speech-formants/summary.json)

第29版を指定した全体監査は99実行の2,128出力と214判定に通過した。修正後の比較2実行と両監査の1,086入力・26出力をSHA-256で照合した。公開極、候補順、窓比較と試験ログなど1,196,333バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-matched-speech-formants/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-matched-speech-formants-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-matched-speech-formants-new \
  --stage7-run stage7-matched-speech-formants-new
```

## 第30版でMFA入力と再整列境界を照合する

第29版までの91実行・235判定を保持し、MFAの入力PCM16、本文・辞書、再整列のJSON、窓の開始標本を照合した。第30版は92実行の2,520出力と239判定に通過した。固定上流が保存済みの入力と境界を再現し、設定を揃えた合成の4組すべてでPCM16と語・音素の境界が一致した。60窓の開始位置差は保存時の15窓から0窓になった。[比較条件と結果](tsp-matched-speech-mfa.md)・[第30版の要約](../runs/stage7-evidence-update-20261123-matched-speech-mfa/summary.json)

第30版を指定した全体監査は99実行の2,128出力と214判定に通過した。計測2回と監査2回の1,160入力・76出力をSHA-256で照合し、採取ログと成果4,429,135バイトをRTL9210B-CGに保存した。実録音のF2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-matched-speech-mfa/summary.json)・[一次記録の取込](#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-matched-speech-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-matched-speech-mfa-new \
  --stage7-run stage7-matched-speech-mfa-new
```

## 第31版で初期舌先の寄与を照合する

第30版の92実行・239判定を保持し、確認用 `FK61_01` で初期舌先のみを旧値へ戻す対照を加えた。ケース、PCM、整列区間から、最初の50 msの差、`again` の /ɛ/–/n/ 境界、90%窓の位置を再計算した。最大PCM差は0.00189で、境界は2.040秒、90%窓は24,185標本のままだった。保存済みの旧境界を参照すると、以前の216標本の窓位置差を再現できた。第7段階は93実行の2,548出力と243判定に通過した。[単一変更の比較](tsp-again-initial-tip-mfa.md)・[第31版の要約](../runs/stage7-evidence-update-20261123-again-initial-tip-mfa/summary.json)

第31版を指定した全体監査は99実行・214判定に通過した。計測2回と監査2回の1,398入力・68出力をSHA-256で照合し、成果3,992,009バイトをRTL9210B-CGに保存した。録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-again-initial-tip-mfa/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-again-initial-tip-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-again-initial-tip-mfa-new \
  --stage7-run stage7-again-initial-tip-mfa-new
```

## 第32版で周期長ジッターと整列境界を照合する

第31版の93実行・243判定を保持し、確認用 `FK61_01` の周期長ジッターだけを0へ戻した比較を加えた。ケースの差、周期系列の初差、同じ周期番号の振幅倍率、MFA境界、固定窓のF2を成果物から再計算した。位相は内部831標本から異なり、/ɛ/–/n/ 境界は2.040秒で一致した。第7段階は94実行の2,578出力と247判定に通過した。[周期長ジッターの比較](tsp-again-period-jitter-mfa.md)・[第32版の要約](../runs/stage7-evidence-update-20261123-again-period-jitter-mfa/summary.json)

第32版を指定した全体監査は99実行・214判定に通過した。周期長ジッターの計測2回、初期舌先の回帰1回、監査2回の1,585入力・100出力をSHA-256で照合し、成果13,212,098バイトをRTL9210B-CGに保存した。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[全体監査](../runs/plan-completion-release-v6-again-period-jitter-mfa/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-again-period-jitter-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-again-period-jitter-mfa-new \
  --stage7-run stage7-again-period-jitter-mfa-new
```

## 第33版で低速F0ドリフトと整列境界を照合する

低速F0ドリフトを止めた場合の瞬時F0比、初期位相、MFAの区間、固定窓と再整列窓のF2を照合した。2.040秒から2.060秒へ移動した境界は、保存済みの旧研究版と一致した。10 ms以内という事前予測が外れた判定は実行要約に保存した。監査の初回ではNumPy型の真偽値をJSONに直列化できず停止した。Pythonの真偽値に変換し、同じ入力で再実行した。[事前登録と測定](tsp-again-pitch-drift-mfa.md)・[監査の初回失敗](../runs/stage7-evidence-update-20261123-again-pitch-drift-mfa/manifest.json)・[修正後の監査](../runs/stage7-evidence-update-20261123-again-pitch-drift-mfa-recheck/summary.json)

第32版の94実行・247判定を保持し、第33版は95実行の2,609出力と251判定に通過した。第33版を指定した全体監査は99実行・214判定に通過した。初回失敗を含む6実行の2,217入力・109出力をSHA-256で照合し、成果17,012,057バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-again-pitch-drift-mfa/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-again-pitch-drift-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-again-pitch-drift-mfa-new \
  --stage7-run stage7-again-pitch-drift-mfa-new
```

## 第34版で4発話のドリフト停止と整列窓を照合する

第33版の単独比較を4発話に広げ、5セントと0セントのケース、各音素の境界と開始標本、固定RustのF2を保存した結果から照合した。ドリフトを止めると旧比較の15窓のうち10窓で開始標本が一致した。残る5窓は男性の `again` で基準と同じ開始標本だった。旧差がない45窓は基準の開始位置を保った。全15窓を再現するという予測は外れた判定として記録した。[4発話の比較](tsp-matched-pitch-drift-mfa.md)・[第34版の要約](../runs/stage7-evidence-update-20261123-matched-pitch-drift-mfa/summary.json)

第33版の95実行・251判定を保持し、第34版は96実行の2,668出力と255判定に通過した。第34版を指定した全体監査は99実行・214判定に通過した。計測2回と監査2回の1,475入力・130出力をSHA-256で照合し、成果14,507,281バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-matched-pitch-drift-mfa/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-matched-pitch-drift-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-matched-pitch-drift-mfa-new \
  --stage7-run stage7-matched-pitch-drift-mfa-new
```

## 第35版で振幅シマーと男性発話の境界を照合する

第34版の96実行・255判定を保持し、男性発話 `MK61_01` のドリフト0で振幅シマーだけを停止した対照を加えた。ケース、瞬時F0、位相、振幅倍率、MFA境界、固定RustのF2から、最初の振幅差が周期境界の標本番号871に現れ、旧MFA位置を再現した窓が0であることを照合した。第7段階は97実行の2,698出力と259判定に通過した。[振幅シマーの比較](tsp-again-amplitude-shimmer-mfa.md)・[第35版の要約](../runs/stage7-evidence-update-20261123-again-amplitude-shimmer-mfa/summary.json)

第35版を指定した全体監査は99実行・214判定に通過した。計測2回、ドリフト比較の回帰1回、監査2回の1,645入力・103出力をSHA-256で照合し、成果16,757,502バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-again-amplitude-shimmer-mfa/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-again-amplitude-shimmer-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-again-amplitude-shimmer-mfa-new \
  --stage7-run stage7-again-amplitude-shimmer-mfa-new
```

## 第36版で男性発話の周期長ジッターと整列境界を照合する

ドリフトとシマーを0にした男性発話で周期長ジッターだけを停止した。ケースの変更箇所、位相の初差、同じ周期番号の振幅倍率、MFAの境界とF2採択を元の成果物で照合した。/ɛ/–/n/ の境界は2.030秒から2.050秒へ動き、旧研究版の語8区間・音素25区間と一致した。旧 `again` の5窓はすべて開始標本を再現した。境界移動10 ms以内という予測は不成立として保存した。[周期長ジッターの比較](tsp-again-male-period-jitter-mfa.md)・[第36版の要約](../runs/stage7-evidence-update-20261123-again-male-period-jitter-mfa/summary.json)

第35版の97実行・259判定を保持し、第36版は98実行の2,728出力と264判定に通過した。第36版を指定した全体監査は99実行・214判定に通過した。計測2回、シマー比較の回帰1回、監査2回の1,659入力・102出力をSHA-256で照合し、成果16,586,404バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-again-male-period-jitter-mfa/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-again-male-period-jitter-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-again-male-period-jitter-mfa-new \
  --stage7-run stage7-again-male-period-jitter-mfa-new
```

## 第37版で3つの音源変動を止めた4発話を照合する

4発話のドリフト・周期長ジッター・振幅シマーを0にした。語・音素の保存境界、固定RustのF2、変更した音源設定を照合した。旧差15窓をすべて再現し、残る45窓は開始位置を保った。評価対象外の `he`–`lent` は旧位置の0.330秒に揃った。旧研究版との境界差は `FK61_02` の `tall` の /ɔ/–/l/ のみに残った。[4発話の計測](tsp-matched-source-variation-zero-mfa.md)・[第37版の要約](../runs/stage7-evidence-update-20261123-matched-source-variation-zero-mfa/summary.json)

第36版の98実行・264判定を保持し、第37版は99実行の2,787出力と269判定に通過した。全体監査は99実行・214判定に通過した。計測2回、ドリフトのみの回帰1回、監査2回の1,708入力・189出力をSHA-256で照合し、成果21,807,123バイトをRTL9210B-CGに保存した。[全体監査](../runs/plan-completion-release-v6-matched-source-variation-zero-mfa/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-matched-source-variation-zero-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-matched-source-variation-zero-mfa-new \
  --stage7-run stage7-matched-source-variation-zero-mfa-new
```

## 第38版で出力ゲインとtallの境界を照合する

ゲインだけを旧値へ戻した入力ケース、独立計算による出力PCM、MFAの境界と窓のF2を照合した。旧研究版との整列用PCM16の差4,679標本は標本番号12,071以前にあり、`tall` 周辺の12,000標本は一致した。 `tall` の /ɔ/–/l/ 境界は1.650秒のままで、旧位置を再現する予測は不成立として記録した。初回の計測はMFAに渡すサンプルレートの配置が原因で停止し、修正後に別IDで再実行した。[出力ゲインの比較](tsp-tall-output-gain-mfa.md)・[第38版の要約](../runs/stage7-evidence-update-20261123-tall-output-gain-mfa/summary.json)

第37版の99実行・269判定を保持し、第38版は100実行の2,811出力と274判定に通過した。全体監査は99実行・214判定に通過した。計測2回と監査2回の1,493入力・60出力のサイズとSHA-256を照合した。計測と監査の成果5,962,411バイトはRTL9210B-CG上にある。[第38版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-output-gain-mfa/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-output-gain-mfa/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-output-gain-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-output-gain-mfa-new \
  --stage7-run stage7-tall-output-gain-mfa-new
```

## 第39版で初期舌先と旧tall境界の再現を照合する

`FK61_02` の旧ゲイン・音源3変動0の条件で初期舌先2座標だけを旧研究版の値へ移した。無加工float32と整列用PCM16を旧版の一次WAVに照合し、各144,727標本が一致した。語9区間と音素30区間、`tall` の1.680秒の境界と固定・再整列のLPC窓開始を整列JSONと上流LPC出力から再集計した。第38版の100実行・274判定を保持し、第39版は101実行の2,839出力と279判定に通過した。[初期舌先の測定](tsp-tall-initial-tip-mfa.md)・[第39版の要約](../runs/stage7-evidence-update-20261123-tall-initial-tip-mfa/summary.json)

全体監査は99実行・214判定に通過した。計測2回と回帰1回、監査2回の1,677入力・92出力のサイズとSHA-256を照合した。成果7,921,160バイトをRTL9210B-CGに保存した。[第39版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-initial-tip-mfa/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-initial-tip-mfa/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-initial-tip-mfa-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-initial-tip-mfa-new \
  --stage7-run stage7-tall-initial-tip-mfa-new
```

## 第40版で冒頭と残りのPCM16の交換を照合する

`FK61_02` の整列用PCM16を2,400標本で分け、対照と旧舌先から各区間を選んだ4条件を照合した。冒頭だけを交換した条件の差は2,367標本、50 ms以後だけを交換した条件の差は2,312標本。 `tall` 周辺の12,000標本は全条件で一致した。2つの交換条件はともに旧舌先の語・音素区間と1.680秒の境界を再現した。50 ms以後だけなら境界は動かないという予測が外れたことを、MFAの区間JSONから再集計して保存した。[測定ノート](tsp-tall-mfa-preroll.md)・[第40版の要約](../runs/stage7-evidence-update-20261123-tall-mfa-preroll/summary.json)

第39版の101実行・279判定を保持し、第40版は102実行の2,861出力と284判定に通過した。全体監査は99実行・214判定に通過した。計測2回と監査2回の1,279入力・56出力のサイズとSHA-256を照合し、成果2,461,107バイトをRTL9210B-CGに保存した。[第40版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-mfa-preroll/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-mfa-preroll/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-mfa-preroll-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-mfa-preroll-new \
  --stage7-run stage7-tall-mfa-preroll-new
```

## 第41版でCMVN統計と初回の精度判定を照合する

`FK61_02` の2種類のPCM16に、それぞれ自身ともう一方のCMVN統計を適用した。入力WAVと正規化前のMFCCを同じ音声の条件へ、実際に適用した統計を供給元へ照合した。正規化前の読み戻しでは全302フレームに差があり、非圧縮のMFCCの差は先頭6フレームに収まった。4条件の一次MFA出力から境界を集計した。交換音声に対照統計を使えば1.650秒へ戻るという予測は外れた。初回はfloat64で二乗した独立計算が不合格になった。二乗精度だけを修正した再実行で、一次特徴量のハッシュと境界を維持したことを確認した。[CMVNの測定](tsp-tall-mfa-cmvn.md)・[第41版の要約](../runs/stage7-evidence-update-20261123-tall-mfa-cmvn/summary.json)

第40版の102実行・284判定を保持し、第41版は103実行の2,881出力と290判定に通過した。全体監査は99実行・214判定に通過した。初回の不合格を含む6実行の1,325入力・94出力をSHA-256で照合し、成果5,477,273バイトをRTL9210B-CGに保存した。[第41版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-mfa-cmvn/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-mfa-cmvn/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-mfa-cmvn-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-mfa-cmvn-new \
  --stage7-run stage7-tall-mfa-cmvn-new
```

## 第42版で最初のMFCC保存形式を照合する

`FK61_02` の4条件について、最初と最終のark種別を実行時に確認した。圧縮側の特徴量と全区間は第41版に一致し、最初をfloat32にした側では最初の読み戻しを保存前のMFCCに照合した。対照統計を共用した場合は正規化直後の差が6フレームになり、最終圧縮で302フレームへ広がった。非圧縮開始側の4条件が1.680秒へ揃ったことを一次区間JSONから確認した。[測定ノート](tsp-tall-mfcc-input-compression.md)・[第42版の要約](../runs/stage7-evidence-update-20261123-tall-mfcc-input-compression/summary.json)

第41版の103実行・290判定を保持し、第42版は104実行の2,910出力と295判定に通過した。全体監査は99実行・214判定に通過した。計測2回、回帰1回、監査2回の1,331入力・90出力をSHA-256で照合し、成果4,772,593バイトをRTL9210B-CGに保存した。[第42版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-mfcc-input-compression/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-mfcc-input-compression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-mfcc-input-compression-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-mfcc-input-compression-new \
  --stage7-run stage7-tall-mfcc-input-compression-new
```

## 第43版で最終のMFCC保存形式を照合する

`FK61_02` の4条件で最初のMFCCと正規化後の特徴量は両保存形式の間でビット一致した。最終非圧縮側では正規化直後の値と最終読み戻しが一致した。同じ対照統計の2発話で、最終の差は302フレームから6へ減り、`tall` 周辺の差は0になった。最終保存の変更で1.650秒へ戻るという予測は外れ、両側4条件の全区間が同じだった。特徴量と区間JSONを独立に再集計した。[測定ノート](tsp-tall-mfcc-final-compression.md)・[第43版の要約](../runs/stage7-evidence-update-20261123-tall-mfcc-final-compression/summary.json)

第42版の104実行・295判定を保持し、第43版は105実行の2,939出力と300判定に通過した。全体監査は99実行・214判定に通過した。計測2回、回帰1回、監査2回の1,361入力・99出力をSHA-256で照合し、成果5,099,331バイトをRTL9210B-CGに保存した。[第43版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-mfcc-final-compression/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-mfcc-final-compression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-mfcc-final-compression-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-mfcc-final-compression-new \
  --stage7-run stage7-tall-mfcc-final-compression-new
```

## 第44版でGMM-HMM経路の交差採点を照合する

`FK61_02` の同一PCMから得た2つの特徴行列は302×40。探索FSTと実効モデルは同一で、音素IDの違いは165〜167番にあった。保存したフレーム別尤度とグラフ費用から、1.680秒経路の重み付き得点差−0.00015213、+0.00013016を再集計した。合計得点の照合差が経路間差より大きいことを記録した。Kalpy呼び出し形式の誤りで交差採点が停止した初回を保存し、修正後と両方の採取行列・経路が一致することを照合した。[測定ノート](tsp-tall-gmm-paths.md)・[第44版の要約](../runs/stage7-evidence-update-20261123-tall-gmm-paths/summary.json)

第43版の105実行・300判定を保持し、第44版は106実行の2,965出力と305判定に通過した。全体監査は99実行・214判定に通過した。初回を含む5実行の1,364入力・86出力をSHA-256で照合し、成果1,784,789バイトをRTL9210B-CGに保存した。[第44版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-gmm-paths/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-gmm-paths/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-gmm-paths-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-gmm-paths-new \
  --stage7-run stage7-tall-gmm-paths-new
```

## 第45版でGMM-HMMへの5フレームの交換を照合する

`FK61_02` のGMM-HMM入力で、164〜168番の5行をfloat32開始から取ると1.680秒の経路を選び、残り297行をfloat32開始から取ると1.650秒の経路を選んだ。4条件の実効モデル・探索FST・設定、特徴行の供給元、遷移IDと語・音素区間を照合した。固定2経路の再構成得点は、5行の供給元が同じなら一致した。[測定ノート](tsp-tall-gmm-frame-swap.md)・[第45版の要約](../runs/stage7-evidence-update-20261123-tall-gmm-frame-swap/summary.json)

第44版の106実行・305判定を保持し、第45版は107実行の3,000出力と310判定に通過した。全体監査は99実行・214判定に通過した。計測2回、回帰1回、監査2回の1,400入力・108出力をSHA-256で照合し、成果4,336,472バイトをRTL9210B-CGに保存した。[第45版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-gmm-frame-swap/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-gmm-frame-swap/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-gmm-frame-swap-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-gmm-frame-swap-new \
  --stage7-run stage7-tall-gmm-frame-swap-new
```

## 第46版でGMM-HMM特徴行の32部分集合を照合する

`FK61_02` のPCM・モデル・FST・探索設定を固定し、164〜168番の5特徴行について全32部分集合を再整列した。1.680秒を選んだ14条件の最小は165・166番と165・167番の2組だった。166・167・168番の3行にも、境界を切り替える真部分集合がなかった。保存された各入力を再構成し、2経路の得点差をフレーム別尤度とグラフ費用から独立に再集計した。実際に選ばれた経路と得点差の符号は全32条件で一致した。[読解・事前条件・実測](tsp-tall-gmm-frame-subsets.md)・[第46版の要約](../runs/stage7-evidence-update-20261123-tall-gmm-frame-subsets/summary.json)

初回は対照の区間JSONの保存パスの誤りで、マニフェスト発行前に停止した。次の実行は、CMVNを読む観測器が数値順の索引を辞書順と仮定して停止した。失敗時と修正後の入力行列ハッシュが一致することを確認した。第45版の107実行・310判定を保持し、第46版は108実行の3,203出力と315判定に通過した。[停止時のマニフェスト](../runs/tsp-tall-gmm-frame-subsets-20261123-recheck/manifest.json)・[第46版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-gmm-frame-subsets/manifest.json)

全体監査は99実行・214判定に通過した。CMVNの読取失敗を含む6実行の1,587入力・523出力をSHA-256で照合し、成果42,046,552バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-gmm-frame-subsets/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-gmm-frame-subsets-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-gmm-frame-subsets-new \
  --stage7-run stage7-tall-gmm-frame-subsets-new
```

## 第47版で母音終端に対するF2の感度を照合する

`FK61_02` の音声と母音開始を固定し、終端1.650〜1.680秒の4条件で16窓を比較した。両端は実際の通常MFA、内側2点は感度測定用に指定した。区間と音声から窓を切り出し直し、独立LPCの極と、上流の極から選び直したF2を照合した。中央3窓の中央値は23.98 Hz、90%窓は257.79 Hzの幅があった。両端の測定値は先行ケースを再現した。[事前条件と実測](tsp-tall-f2-boundary-grid.md)・[第47版の要約](../runs/stage7-evidence-update-20261123-tall-f2-boundary-grid/summary.json)

第46版の108実行・315判定を保持し、第47版は109実行の3,209出力と320判定に通過した。[第47版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-f2-boundary-grid/manifest.json)

要約の1.660秒条件のF2だけをメモリ上で1 Hz増やした対照では、元データとの照合が不合格になった。全体監査は99実行・214判定に通過した。測定2実行と監査2実行の1,512入力・24出力をSHA-256で照合し、成果71,876バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-f2-boundary-grid/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-f2-boundary-grid-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-f2-boundary-grid-new \
  --stage7-run stage7-tall-f2-boundary-grid-new
```

## 第48版で実録音の母音終端に対するF2の感度を照合する

`FK61_02` の `tall` の保存済み実録音とMFAのAA1区間から、終端1.670〜1.700秒の4条件・16窓を再計算した。中央3窓のF2中央値は11.62 Hz、90%窓は72.21 Hzの幅だった。100 Hz以上という予測は外れた。上流極から選び直した順位は全4条件で2番目と一致した。標本移動を整数の等差とした初回判定は不合格。保存時刻のfloat32丸めを反映した第2版と初回で、上流と独立計算の出力はそれぞれバイト一致した。[実測と初回判定](tsp-tall-recording-f2-boundary-grid.md)・[初回のマニフェスト](../runs/tsp-tall-recording-f2-boundary-grid-20261123-a/manifest.json)

第47版の109実行・320判定を保持し、第48版は110実行の3,215出力と325判定に通過した。[第48版のマニフェスト](../runs/stage7-evidence-update-20261123-tall-recording-f2-boundary-grid/manifest.json)

要約の90%窓の採択順位をメモリ上で2から3に変えると、上流極からの再集計と初回結果の保持の2判定が落ちた。全体監査は99実行・214判定に通過した。初回の不合格と合成側の回帰を含む6実行の1,572入力・36出力をSHA-256で検証し、成果120,049バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-tall-recording-f2-boundary-grid/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-tall-recording-f2-boundary-grid-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-tall-recording-f2-boundary-grid-new \
  --stage7-run stage7-tall-recording-f2-boundary-grid-new
```

## 第49版で注釈資料W06の窓位置とF2候補を照合する

人手注釈のW06が指す元録音の窓と切り出し音声を確認した。元の窓を前後60標本ずらした121窓では、2.1 kHz側と2.9 kHz側がすべて適格だった。全窓で2.1 kHz側を採択し、欠測と帯域間の切り替わりは0件だった。監査は元のPCM16、間引き系列、注釈資料の標本位置を照合し、固定上流の公開極と生根から帯域ごとの候補と順位の判定を再計算した。[ケースと実測](tsp-f2-annotation-w06-window-shift.md)・[第49版の要約](../runs/stage7-evidence-update-20261123-annotation-w06-window-shift/summary.json)

第48版の110実行・325判定を保持し、第49版は111実行の3,221出力と330判定に通過した。[第49版のマニフェスト](../runs/stage7-evidence-update-20261123-annotation-w06-window-shift/manifest.json)

要約にある2.9 kHz側の周波数下限をメモリ上で1 Hz変えた対照は、元データからの候補範囲の判定に失敗した。全体監査は99実行・214判定に通過した。測定2実行、既定ケースの回帰、監査2実行の1,568入力・30出力をSHA-256で照合し、成果431,906バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-annotation-w06-window-shift/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-annotation-w06-window-shift-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-annotation-w06-window-shift-new \
  --stage7-run stage7-annotation-w06-window-shift-new
```

## 第50版でW06のプリエンファシスとF2の採択を照合する

W06の固定300標本でプリエンファシス0〜0.970の971点を比較した。0.111と0.112の間で、従来のF1の帯域幅が500 Hzを越えた。従来のF2がF1に採られ、約2,010 Hzの候補がF2として選ばれた。監査は元の間引き系列から同じ窓を切り出し、全条件の独立計算と、切り替え前後の複素根・帯域幅・採択を再照合した。先行の係数0・既定0.97も再現した。[測定ノート](tsp-f2-annotation-w06-pre-emphasis.md)・[第50版の要約](../runs/stage7-evidence-update-20261123-annotation-w06-pre-emphasis/summary.json)

第49版の111実行・330判定を保持し、第50版は112実行の3,227出力と335判定に通過した。[第50版のマニフェスト](../runs/stage7-evidence-update-20261123-annotation-w06-pre-emphasis/manifest.json)

保存した要約の切り替わりをメモリ上で0.112〜0.113へ移した対照は不合格になった。全体監査は99実行・214判定に通過した。測定2実行、既存6窓の回帰、監査2実行の1,565入力・34出力をSHA-256で照合し、成果29,489,084バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-annotation-w06-pre-emphasis/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-annotation-w06-pre-emphasis-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-annotation-w06-pre-emphasis-new \
  --stage7-run stage7-annotation-w06-pre-emphasis-new
```

## 第51版でagainの3注釈窓のF2採択と中央値を照合する

同じ実録音の35%・65%窓を新規に各971係数で計測し、保存済みの中央窓と組み合わせた。35%窓は常に高域を採択。65%窓では係数0.190〜0.191で対応する低いF2極の幅が600 Hzを越えた。3窓のF2中央値は0.111〜0.112で切り替わり、全点で有効窓数は3だった。監査は注釈WAVと元の標本を照合し、全条件の独立計算、公開極からの採択、中央値を再計算した。[測定ノート](tsp-f2-annotation-again-pre-emphasis.md)・[第51版の要約](../runs/stage7-evidence-update-20261123-annotation-again-pre-emphasis/summary.json)

第50版の112実行・335判定を保持し、第51版は113実行の3,234出力と340判定に通過した。[第51版のマニフェスト](../runs/stage7-evidence-update-20261123-annotation-again-pre-emphasis/manifest.json)

要約の係数0.112の中央値だけを1 Hz変えた対照では、中央値の再計算が不合格になった。全体監査は99実行・214判定に通過した。測定2回、中央窓の回帰、監査2回の1,584入力・32出力をSHA-256で照合し、成果71,828,147バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-annotation-again-pre-emphasis/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-annotation-again-pre-emphasis-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-annotation-again-pre-emphasis-new \
  --stage7-run stage7-annotation-again-pre-emphasis-new
```

## 第52版でagainのF2差をTSPの診断費用まで照合する

固定上流の合成・MFA整列・音素対応・集約を36収録で実行し、確認用FKの録音の1トークンだけを差し替えた。話者中央値は1,675.16 Hzから1,789.91 Hzへ、学習参照に対するF2費用は1.28932から0.14472へ移った。採点群と総合点は一致した。監査はアーカイブ中の全36 WAVのハッシュ、対象F2の既定値、話者中央値、参照の広がりと費用を再計算した。支持数2件ではF2診断が欠測、3件では有効で、女性学習話者4名では参照が欠測だった。[測定ノート](tsp-again-f2-term-effect.md)・[第52版の要約](../runs/stage7-evidence-update-20261123-again-f2-term-effect/summary.json)

第51版の113実行・340判定を保持し、第52版は114実行の3,241出力と344判定に通過した。[第52版のマニフェスト](../runs/stage7-evidence-update-20261123-again-f2-term-effect/manifest.json)

要約の差し替え後の費用だけを0.1増やす対照は、費用の再計算で不合格になった。全体監査は99実行・214判定に通過した。測定2回、監査2回の1,538入力・26出力をSHA-256で照合し、成果557,346バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-again-f2-term-effect/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-again-f2-term-effect-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-again-f2-term-effect-new \
  --stage7-run stage7-again-f2-term-effect-new
```

## 第53版で学習側の1件がF2参照に与える影響を照合する

元の音素対応で学習側の有効F2 39件を特定し、2値の計78条件を固定上流の `values`、`reference`、`costs` に通した。中心が変わる位置は16件、中心が同じまま評価の幅が変わる位置は12件。幅の下限を使った8条件も再計算した。確認側のF2と支持数を固定し、最後に学習側を元へ戻すと参照と費用は基準を再現した。初回の観測コードは `E0753` で停止し、入力のハッシュとログを保存した。[測定ノート](tsp-f2-training-reference-sensitivity.md)・[初回のマニフェスト](../runs/tsp-f2-training-reference-sensitivity-20261123-a/manifest.json)

第52版の114実行・344判定を保持し、第53版は115実行の3,247出力と349判定に通過した。[第53版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-training-reference-sensitivity/manifest.json)

幅の下限が効いた条件数を要約上だけ変えた対照は、MADと費用の再集計で不合格だった。全体監査は99実行・214判定に通過した。初回を含む6実行の1,569入力・35出力をSHA-256で照合し、成果389,338バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-training-reference-sensitivity/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-training-reference-sensitivity-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-training-reference-sensitivity-new \
  --stage7-run stage7-f2-training-reference-sensitivity-new
```

## 第54版で学習女性5名と10名のF2参照を照合する

追加30録音の個別SHA-256をTSPアーカイブと照合し、上流MFAと音素対応から得た37件のF2をWAVから独立計算した。最大差は `7.89e-11 Hz`。元の39位置、差し替え2値、FKの測定値を固定し、全78条件を再集計した。10名でも幅だけが変わる位置は12件で、幅の下限が効く条件は8件から9件になった。録音・合成の診断費用がともに安定するという予測の不成立も保存した。[測定と実装](tsp-f2-training-reference-ten-speakers.md)・[再実行のマニフェスト](../runs/tsp-f2-training-reference-ten-speakers-20261123-repeat/manifest.json)

第54版は116実行の3,257出力と353判定に通過した。参照中心と幅の比較は女性10名の部分集合まで確認した。人手F2注釈とTSP・CSD試聴の集計は回答の到着を待つ。物理MIDIは後日に回す。[第54版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-training-reference-ten-speakers/manifest.json)

同版を指定した全体監査は99実行・214判定に通過した。新旧入口の回帰を含む6実行の1,595入力・45出力をSHA-256で照合し、成果794,213バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-training-reference-ten-speakers/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-training-reference-ten-speakers-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-training-reference-ten-speakers-new \
  --stage7-run stage7-f2-training-reference-ten-speakers-new
```

## 第55版でF2の参照中心と評価幅を個別に照合する

第53・54版の保存入力から `FD19_10` の対応音素列の15番を再集計した。2中心×3幅×2コホート×録音・合成の24点で、上流の `costs` と独立計算の絶対差、ゼロ境界、診断費用が一致した。10名の合成側の両方を替えた条件は費用0.02291。観測の複製で費用だけを0へ替えた場合とゼロ判定だけを反転した場合は、いずれも独立照合で不合格だった。[数値と内訳](tsp-f2-reference-centre-width.md#実測)・[再実行のマニフェスト](../runs/tsp-f2-reference-centre-width-20261123-repeat/manifest.json)

第55版は117実行の3,263出力と356判定に通過した。人手によるF2注釈、TSP・CSDの試聴回答と物理MIDIの状態は引き続き未確認。[第55版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-reference-centre-width/manifest.json)

同版での全体監査は99実行・214判定に通過した。4実行の1,563入力と24出力をSHA-256で照合し、成果40,527バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-reference-centre-width/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-reference-centre-width-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-reference-centre-width-new \
  --stage7-run stage7-f2-reference-centre-width-new
```

## 第56版で男女の学習残差をまとめたF2参照を照合する

男性54録音のWAVをTSPアーカイブと照合し、上流の音素対応から得たF2の69件を男性用14次LPCで独立に再計算した。最大差は `2.19e-10 Hz` で、欠測判定も一致した。男性4名の対照ではプールに入る残差は女性の10件、男性9名を加えると19件だった。監査の期待値だけを14件に書き換えた対照は不合格となった。録音側の費用増分は女性のみで0.63034、男女で0.16354だった。[読解と実測](tsp-f2-reference-pooled-sexes.md)・[再実行のマニフェスト](../runs/tsp-f2-reference-pooled-sexes-20261123-repeat/manifest.json)

第56版は118実行の3,273出力と360判定に通過した。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。[第56版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-reference-pooled-sexes/manifest.json)

同版での全体監査は99実行・214判定に通過した。5実行の1,609入力と42出力をSHA-256で照合し、成果849,545バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-reference-pooled-sexes/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-reference-pooled-sexes-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-reference-pooled-sexes-new \
  --stage7-run stage7-f2-reference-pooled-sexes-new
```

## 第57版で男女をまとめたF2参照の78条件を照合する

第54版の39位置と置換2値、第56版の男性9名の測定値を固定した。女性10名と男女19名の156条件を、同じ観測入口の1回のビルドから実行した。全条件で参照中心、残差、MAD、幅とFK費用が独立計算と一致した。男女の参照で録音側の費用変動は32条件で減り、42条件で等しく、4条件で増えた。増加を0とした監査上の対照は不合格だった。[計測と結果](tsp-f2-pooled-reference-sweep.md)・[再実行のマニフェスト](../runs/tsp-f2-pooled-reference-sweep-20261123-repeat/manifest.json)

第57版は119実行の3,279出力と363判定に通過した。人手F2注釈とTSP・CSD試聴の回答は未登録。物理MIDIは後日に回す。[第57版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-pooled-reference-sweep/manifest.json)

同版での全体監査は99実行・214判定に通過した。4実行の1,583入力と24出力をSHA-256で照合し、成果970,487バイトをRTL9210B-CGに保存した。[全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-pooled-reference-sweep/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-pooled-reference-sweep-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-pooled-reference-sweep-new \
  --stage7-run stage7-f2-pooled-reference-sweep-new
```

## 第58版で確認話者FLのF2費用を照合する

FLの6録音から録音・合成の各10件を測定した。録音のF2を元WAVから再計算し、最大差は `2.02e-11 Hz` だった。第57版の学習参照を基準と全78条件で再現し、FLの診断費用316点を独立集計と照合した。FL合成は両参照で全78条件が費用0。男女参照の件数を77にした監査対照は不合格だった。正の費用が出るという予測の不成立も保存した。 [読解と計測](tsp-f2-pooled-reference-held-fl.md)・[再実行のマニフェスト](../runs/tsp-f2-pooled-reference-held-fl-20261123-repeat/manifest.json)

第58版は120実行の3,289出力と367判定を通過した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第58版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-pooled-reference-held-fl/manifest.json)

同版での全体監査は99実行・214判定に通過した。5実行の1,619入力と42出力をSHA-256で照合し、成果1,278,887バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-pooled-reference-held-fl/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-pooled-reference-held-fl-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-pooled-reference-held-fl-new \
  --stage7-run stage7-f2-pooled-reference-held-fl-new
```

## 第59版で確認女性の合成F2の文集合別集約を照合する

FKの5件とFLの10件から集約し、上流の `over_sets`、15件の直接集約、各集合の不足対照を比較した。無介入と78条件の2参照・4方式で、費用632点のうち474点の有限値と158点の欠測が独立計算と一致した。女性参照では集約方法により5条件の正の費用が0へ変わった。両集合不足で欠測になった費用を0とした対照は不合格だった。 [集約と実測](tsp-f2-held-synth-over-sets.md)・[再実行のマニフェスト](../runs/tsp-f2-held-synth-over-sets-20261123-repeat/manifest.json)

第59版は121実行の3,295出力と370判定に通過した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第59版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-held-synth-over-sets/manifest.json)

同版の全体監査は99実行・214判定に通過した。4実行の1,593入力と24出力をSHA-256で照合し、成果136,044バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-held-synth-over-sets/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-held-synth-over-sets-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-held-synth-over-sets-new \
  --stage7-run stage7-f2-held-synth-over-sets-new
```

## 第60版で確認女性FKとFLの全発話を照合する

確認女性FK・FLの全120発話で対応音素を取得した。元の12発話の対応、境界、F2は一致した。録音の有効F2をWAVから独立計算した70点の最大差は `1.52e-10 Hz`。合成F2の上流集約値は2,048.24 Hz相当で、女性参照と男女参照の両方で全78条件の費用が0だった。部分文集合の女性参照の件数73を監査に入れた対照は不合格だった。 [全発話の比較](tsp-f2-full-held-women.md)・[再実行のマニフェスト](../runs/tsp-f2-full-held-women-20261123-repeat/manifest.json)

第60版は122実行の3,305出力と374判定に通過した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第60版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-full-held-women/manifest.json)

同版の全体監査は99実行・214判定に通過した。4実行の1,627入力と32出力をSHA-256で照合し、成果1,406,827バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-full-held-women/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-full-held-women-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-full-held-women-new \
  --stage7-run stage7-f2-full-held-women-new
```

## 第61版で研究版の確認女性120発話を照合する

研究版の通常CLIで120発話を合成し、固定上流との予定区間、PCM、音素対応、F2と診断費用を照合した。PCM差は全120発話にあり、最初の差はフレーム1989、最大は `1.49e-8` だった。保存済みの共通6発話のPCMからも、最初の差と最大値を再計算できた。音素対応と対象 `/ɛ/` の70件は固定上流と一致した。保存したLPC窓からの再計算との差も最大 `3.77e-11 Hz` だった。PCM差を0件とした監査対照は不合格となった。 [計測と実測](tsp-f2-full-held-candidate.md)・[再実行のマニフェスト](../runs/tsp-f2-full-held-candidate-20261123-repeat/manifest.json)

第61版は123実行の3,319出力と378判定に通過した。女性参照・男女参照の全78条件が両実装で費用0だった。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第61版のマニフェスト](../runs/stage7-evidence-update-20261123-f2-full-held-candidate/manifest.json)

同版の全体監査は99実行・214判定に通過した。4実行の1,879入力と40出力をSHA-256で照合し、成果3,221,737バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-f2-full-held-candidate/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-f2-full-held-candidate-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-f2-full-held-candidate-new \
  --stage7-run stage7-f2-full-held-candidate-new
```

## 第62版でFK61_01の最初のPCM差を照合する

通常CLI・観測器・保存済みPCMを発話全体で照合した。先頭2048フレームを再計算し、放射差分は内部標本3968、間引きとDC除去は出力1984、float32のPCMは出力1989で最初に異なることを確認した。放射入力を交換した独立再計算は入力側のPCMを再現した。時刻1989の両値はfloat32の丸め中点を挟んだ。間引きの最初の差の期待値を1989に書き換えた対照は不合格だった。 [読解と実測](tsp-fk61-pcm-first-difference.md)・[再実行のマニフェスト](../runs/tsp-fk61-pcm-first-difference-20261123-repeat/manifest.json)

第62版は124実行の3,324出力と381判定に通過した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第62版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-pcm-first-difference/manifest.json)

同版の全体監査は99実行・214判定に通過した。4実行の1,860入力と22出力をSHA-256で照合し、成果326,153バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-pcm-first-difference/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-pcm-first-difference-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-pcm-first-difference-new \
  --stage7-run stage7-fk61-pcm-first-difference-new
```

## 第63版でFK61_01の口端流量の初差を照合する

内部標本3952〜3979で、口端セルの幾何、60 Hzの平滑化とR–L負荷を独立に再計算した。標本3968の倍精度の体積差分は1.11×10⁻¹⁶ cm³異なり、枝と壁はその標本で口端の流入量を変えなかった。平滑化後の流量だけを交換し、両方向とも1 ULPで相手側の口端流量を再現した。各実装について全116,132フレームの通常CLI・観測器・保存済みPCMはビット一致。上流9試験と研究版1試験に通過した。 [読解と実測](tsp-fk61-lip-onset.md)・[再実行のマニフェスト](../runs/tsp-fk61-lip-onset-20261123-repeat/manifest.json)

第63版は125実行の3,332出力と385判定に通過した。PCMハッシュ、元の観測列、平滑化とR–L負荷の再計算、流入の交換、体積積の丸めを照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第63版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-lip-onset/manifest.json)

同版の全体監査は99実行・214判定に通過した。初回、試験を含む2実行、第7段階監査、全体監査の2,040入力と33出力をSHA-256で照合し、成果87,581バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-lip-onset/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-lip-onset-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-lip-onset-new \
  --stage7-run stage7-fk61-lip-onset-new
```

## 第64版でFK61_01の口端の体積差分式を照合する

口端1節点だけ体積差の式を切り替えた試験版の通常CLIと観測器は全116,132 PCMフレームでビット一致した。内部標本3968の体積流量の絶対誤差は約9.40×10⁻¹²から7.02×10⁻²⁰ cm³/sに減った。固定上流との最初のPCM差は1989から1987へ早まり、変換直前値はfloat32の丸め中点を挟んだ。 [読解と実測](tsp-fk61-lip-volume-increment.md)・[再実行](../runs/tsp-fk61-lip-volume-increment-20261123-recheck/manifest.json)

第64版は126実行の3,339出力と389判定に通過した。口端の観測列、発話全体のPCM、FIR・DC除去の先頭2048フレームを使って、独立計算、予測の結果、PCMの丸めを再照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第64版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-lip-volume-increment/manifest.json)

同版の全体監査は99実行・214判定に通過した。失敗3実行を含む7実行の2,344入力と40出力をSHA-256で照合した。成果2,062,517バイトはRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-lip-volume-increment/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-lip-volume-increment-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-lip-volume-increment-new \
  --stage7-run stage7-fk61-lip-volume-increment-new
```

## 第65版でFK61_01の口端断面の初差を照合する

描画前と制御更新の前後を含む5時点で、両版の測定線と口端セルを照合した。初期セルの平均面積差4.44×10⁻¹⁶ cm²は測定線45・46の面積の交換で再現した。45は中央のx座標、46は接触補正後の隙間から、それぞれ面積差が伝わった。内部標本3968の平均面積目標は一致し、現在値に初期差が持ち越された。 [読解と実測](tsp-fk61-lip-area-origin.md)・[再実行](../runs/tsp-fk61-lip-area-origin-20261123-ray-repeat/manifest.json)

第65版は127実行の3,347出力と393判定に通過した。測定線から口端の8中点と平均面積を再計算し、測定線の入力交換と先行の標本3968・3969の補間を照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第65版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-lip-area-origin/manifest.json)

同版の全体監査は99実行・214判定に通過した。初回と事後の交換を含む6実行について2,207入力と44出力をSHA-256で照合し、成果431,111バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-lip-area-origin/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-lip-area-origin-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-lip-area-origin-new \
  --stage7-run stage7-fk61-lip-area-origin-new
```

## 第66版でFK61_01の唇前端の体型変換を照合する

描画前の唇前端のテンプレートxは8.21 cmで一致し、体型変換が倍精度の隣接値を返した。唇前端1箇所を上流と同じ順序で計算した試験版は、測定線45・46と初期の口端セルが固定上流と一致した。最初のPCM差は1989から1987へ早まり、最大差は1.86265×10⁻⁹だった。各条件の通常CLIと観測器は全116,132フレームでビット一致した。 [読解と実測](tsp-fk61-lip-front-origin.md)・[再実行](../runs/tsp-fk61-lip-front-origin-20261123-repeat/manifest.json)

第66版は128実行の3,356出力と396判定に通過した。観測座標から接触上限、面積、口端セルを独立計算し、保存したPCMから試験版の最初と最大の差を照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第66版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-lip-front-origin/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測2実行と監査2実行の1,921入力と30出力をSHA-256で照合し、成果1,009,806バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-lip-front-origin/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-lip-front-origin-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-lip-front-origin-new \
  --stage7-run stage7-fk61-lip-front-origin-new
```

## 第67版でFK61_01の累積距離と補間を照合する

フレーム1985の測定線31の中心yの差から区間距離が異なり、累積位置が隣接する倍精度値の中点を挟んだ。距離の計算で31のyだけを交換すると初差は31から34へ移り、口端セル長の目標差は半分になった。標準版と試験版の全116,132 PCMフレームは一致した。事後に補間を独立に再計算し、3条件の現在長が128標本で一致することと、最初の2標本の計算が観測と合うことを確認した。 [読解と実測](tsp-fk61-centerline-length-origin.md)・[計測の再実行](../runs/tsp-fk61-centerline-length-origin-20261123-repeat/manifest.json)

第67版は129実行の3,365出力と400判定に通過した。中心座標と区間距離、累積の中点、口端セルの長さ目標、128標本分の補間、全PCMの計測を再照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第67版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-centerline-length-origin/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の1,928入力と30出力をSHA-256で照合し、成果968,318バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-centerline-length-origin/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-centerline-length-origin-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-centerline-length-origin-new \
  --stage7-run stage7-fk61-centerline-length-origin-new
```

## 第68版でFK61_01の残る初期放射差を照合する

唇前端を揃えた試験版は、内部3968で固定上流と口端流量・総放射流量が一致した。放射差分の最初の差は同じ標本の時間換算の丸めに生じた。時間換算を揃えた独立計算でも出力1987のPCM差が残った。口端の放射成分、または内部3972の口端流量1標本を交換すると、出力1987までのPCMが固定上流に一致した。 [成分別の実測](tsp-fk61-lip-front-radiation.md)・[計測の再実行](../runs/tsp-fk61-lip-front-radiation-20261123-repeat/manifest.json)

第68版は130実行の3,379出力と404判定に通過した。全節点の壁面放射と収支、口端の幾何とR–L負荷、放射成分、間引き、丸めと交換条件を再照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第68版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-lip-front-radiation/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の1,958入力・40出力をSHA-256で照合し、成果2,640,591バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-lip-front-radiation/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-lip-front-radiation-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-lip-front-radiation-new \
  --stage7-run stage7-fk61-lip-front-radiation-new
```

## 第69版で節点42から口端への流量差を照合する

FK61_01の内部標本3968の節点42は、体積流量が試験版と固定上流で同じで、コンプライアンスの交換で新圧力が揃った。3969の枝42→43は左圧力と枝係数を同時に交換すると固定上流の流量に一致した。3968〜3975の二節点の連続再計算で圧力・壁・枝・口端流量がそれぞれの観測に一致した。事後に平滑後の体積注入を8内部標本で交換したところ、口端成分の変化だけで1987までのPCMが揃った。 [ケース定義](../cases/tsp-fk61-lip-front-terminal-branch.json)・[検証の詳細](tsp-fk61-lip-front-terminal-branch.md)

第69版は131実行の3,401出力と408判定に通過した。初回の保存配列の比較失敗を保持し、観測値が修正後と一致したことを確認した。人手F2注釈とTSP・CSD試聴回答は未登録。物理MIDIは後日に回す。 [第69版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-terminal-branch/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の1,998入力・56出力をSHA-256で照合し、成果2,744,058バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-terminal-branch/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-terminal-branch-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-terminal-branch-new \
  --stage7-run stage7-fk61-terminal-branch-new
```

## 第70版で節点42の体積速度の初差を照合する

FK61_01の節点42は内部3969で体積速度が分かれた。各版で丸めた面積・長さの積の差が体積速度へ伝わり、2段の平滑にも同じ標本から差が残った。3952〜3979に近隣への配分はなかった。局所再計算で平滑前の3969だけを交換すると、出力1987までのPCMが固定上流と一致した。 [ケース定義](../cases/tsp-fk61-node42-volume-source.json)・[枝と体積注入の比較](tsp-fk61-node42-volume-source.md)

第70版は132実行の3,426出力と411判定に通過した。幾何、配分、体積速度、平滑から出力段までを保存値から再計算した。人手F2注釈、TSP・CSD試聴は未登録。物理MIDIは後日に回す。 [第70版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-node42-volume-source/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の2,041入力・62出力をSHA-256で照合し、成果4,826,072バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-node42-volume-source/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-node42-volume-source-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-node42-volume-source-new \
  --stage7-run stage7-fk61-node42-volume-source-new
```

## 第71版で節点42の再標本化と補間を照合する

FK61_01の節点42には、描画前と1985フレームの双方で測定線42〜45が入った。描画前は測定線43の面積だけの交換でセルの平均断面積が上流に一致した。補間開始時の面積を揃えた局所計算では3969の体積速度が上流に一致した。1985フレームではセル境界、測定線の位置、測定線の面積を同時に揃えると平均断面積が一致した。 [ケース定義](../cases/tsp-fk61-node42-area-origin.json)・[幾何と補間の実測](tsp-fk61-node42-area-origin.md)

第71版は133実行の3,435出力と414判定に通過した。観測した4時点の再標本化、補間の128標本の反復加算と保存済みの状態、面積交換を再計算した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第71版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-node42-area-origin/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の2,023入力・30出力をSHA-256で照合し、成果1,134,806バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-node42-area-origin/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-node42-area-origin-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-node42-area-origin-new \
  --stage7-run stage7-fk61-node42-area-origin-new
```

## 第72版で測定線43の交差とベジェ曲線を照合する

FK61_01の測定線43は、描画前の3条件で下唇内面の添字1→2を同じ光線で横切った。試験版の線分の始点だけを上流に揃えると、下側の交差距離と隙間、測定線の面積、節点42の平均断面積が上流に一致した。採取後の独立計算では、復元した同じ制御点のBernstein基底とde Casteljau法による評価で、両版の端点差を再現した。 [ケース定義](../cases/tsp-fk61-ray43-intersection.json)・[線分と曲線の実測](tsp-fk61-ray43-intersection.md)

第72版は134実行の3,444出力と418判定に通過した。4時点の輪郭からの交差、採用線分と光線の交換、曲線の追加対照を再計算した。人手F2注釈、TSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第72版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-ray43-intersection/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の2,025入力・30出力をSHA-256で照合し、成果1,260,094バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-ray43-intersection/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-ray43-intersection-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-ray43-intersection-new \
  --stage7-run stage7-fk61-ray43-intersection-new
```

## 第73版で下唇内面の評価順と全発話PCMを照合する

下唇内面だけをBernstein基底で評価した試験版を通常CLIと観測器で描画した。FK61_01の描画前の測定線43と内部3969の節点42の体積速度が固定上流に一致した。全発話で最初のPCM差は1987から2937へ移った。最大差は1.86×10⁻⁹で揃い、相違フレーム数は2309から2355に増えた。試験版の2937の変換前値は、隣接float32値の中点を1.41×10⁻¹⁴下回った。 [ケース定義](../cases/tsp-fk61-lower-lip-bernstein-render.json)・[全発話比較](tsp-fk61-lower-lip-bernstein-render.md)

第73版は135実行の3,458出力と423判定に通過した。形状の採取、体積源、口端負荷、先頭3072フレームの出力処理、全PCMの比較を再計算した。試験入力不足と観測器の挿入位置の失敗を記録した4実行も照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第73版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-lower-lip-bernstein-render/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の2,070入力・40出力をSHA-256で照合し、成果2,932,298バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-lower-lip-bernstein-render/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-lower-lip-bernstein-render-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-lower-lip-bernstein-render-new \
  --stage7-run stage7-fk61-lower-lip-bernstein-render-new
```

## 第74版でPCM2937の放射入力と出力段を照合する

FK61_01の固定上流と試験版の最初のPCM差は2937だった。両版の変換直前値は隣接float32の中点を挟んだ。DC除去の直前フレームの出力だけを上流から交換すると2937のPCMが揃った。放射の口端成分を上流に揃えた場合は、冒頭から2937までのPCMが一致した。 [ケース定義](../cases/tsp-fk61-pcm2937-output.json)・[出力段の比較](tsp-fk61-pcm2937-output.md)

第74版は136実行の3,464出力と426判定に通過した。先頭3072フレームの放射から出力までの独立計算と、入力時刻、放射成分、DC状態の交換を照合した。人手F2注釈、TSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第74版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-pcm2937-output/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の1,820入力・24出力をSHA-256で照合し、成果515,606バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-pcm2937-output/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-pcm2937-output-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-pcm2937-output-new \
  --stage7-run stage7-fk61-pcm2937-output-new
```

## 第75版でPCM2937に効く口端流量の時間範囲を照合する

FK61_01の内部5800〜5875の全2,926連続区間で口端流量を上流に交換した。2937で上流と同じ値に丸められたのは1,044区間、冒頭から2937まで一致したのは73区間だった。後者のうち最短は5863・5864の2標本。線形近似と逐次再計算の最大残差は2.99×10⁻¹⁹だった。 [ケース定義](../cases/tsp-fk61-pcm2937-lip-window.json)・[時間範囲の比較](tsp-fk61-pcm2937-lip-window.md)

第75版は137実行の3,466出力と430判定に通過した。走査した全区間・線形の寄与・要約を再計算し、初回のJSON保存失敗で保持した走査配列4件も照合した。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIは後日に回す。 [第75版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-pcm2937-lip-window/manifest.json)

同版の全体監査は99実行・214判定に通過した。計測と監査の4実行の1,807入力・16出力をSHA-256で照合し、成果203,099バイトをRTL9210B-CGに保存した。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-pcm2937-lip-window/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-pcm2937-lip-window-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-pcm2937-lip-window-new \
  --stage7-run stage7-fk61-pcm2937-lip-window-new
```

## 第76版でPCM2937に効く口端負荷の入力を照合する

固定上流・研究版・試験版の通常CLIと観測版を照合し、口端の枝・壁・節点・R–L負荷を記録した。5863〜5865の単標本比較では旧慣性流量が口端流量を最も大きく動かした。5856から正味流入系列を上流と同じにした条件で、冒頭から2937までのPCMが一致した。 [ケース定義](../cases/tsp-fk61-pcm2937-terminal-load.json)・[読解と測定](tsp-fk61-pcm2937-terminal-load.md)

138実行の3,488出力と434判定を確認した。2回の集計失敗から保持した各17出力を修正後の採取データと照合した。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [計測マニフェスト](../runs/tsp-fk61-pcm2937-terminal-load-20261123-certified/manifest.json)・[第76版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-pcm2937-terminal-load/manifest.json)

全体監査は99実行・214判定に通過した。計測・第7段階監査・全体監査の3実行について、1,988入力と34出力をSHA-256で照合した。RTL9210B-CGに置いた出力の合計は2,816,954バイト。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-pcm2937-terminal-load/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-pcm2937-terminal-load-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-pcm2937-terminal-load-new \
  --stage7-run stage7-fk61-pcm2937-terminal-load-new
```

## 第77版でPCM2937に効く枝42から43への運動量を照合する

固定上流と試験版の観測入力で枝と口端の更新を再計算した。枝の流量差を表す独立式は、5863〜5865で観測された差に最大0.85 ULPで一致した。5856の枝の初期状態を交換した16条件でPCMが冒頭から2937まで一致した。圧力系列を交換した条件の方が効くという予測は棄却した。 [ケース定義](../cases/tsp-fk61-pcm2937-branch-drive.json)・[枝の読解と測定](tsp-fk61-pcm2937-branch-drive.md)

139実行の3,489出力と438判定に通過した。枝の計算を元の観測入力からやり直し、別ディレクトリの実行要約とも照合した。全体監査は99実行・214判定に通過した。計測2件と監査2件の入力1,902件・出力14件をSHA-256で照合した。外部の出力はRTL9210B-CGに保存し、容量の合計は24,687バイトだった。 [第77版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-pcm2937-branch-drive/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-pcm2937-branch-drive/manifest.json)

F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIは後日に回す。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-pcm2937-branch-drive-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-pcm2937-branch-drive-new \
  --stage7-run stage7-fk61-pcm2937-branch-drive-new
```

## 第78版で枝42から43への旧流量と旧慣性を照合する

5840〜5856の17開始点で、旧流量・旧慣性の交換を全68条件で比較した。旧流量だけの17条件と、両方を交換した17条件は冒頭からPCM 2937まで一致した。旧慣性だけの17条件では差が残った。独立した一次近似の残差は枝流量の約7.80 ULP以内だった。 [ケース定義](../cases/tsp-fk61-pcm2937-branch-seed.json)・[読解と測定](tsp-fk61-pcm2937-branch-seed.md)

140実行・3,490出力・442判定を確認した。計測要約は元の観測値から再計算し、別ディレクトリでもバイト一致した。全体監査は99実行・214判定に通過した。計測2件・監査2件の入力1,912件と出力14件をSHA-256で照合し、RTL9210B-CGに置いた出力は計24,652バイトだった。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第78版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-pcm2937-branch-seed/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-pcm2937-branch-seed/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-pcm2937-branch-seed-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-pcm2937-branch-seed-new \
  --stage7-run stage7-fk61-pcm2937-branch-seed-new
```

## 第79版で口端への枝流量の初差を照合する

固定上流と下唇の評価順を揃えた試験版で、枝41→42は3969、枝42→43と口端放射は3971で初めて分かれた。3971で節点の圧力だけを上流に交換すると枝42→43の流量が一致した。その圧力差は3970に枝41→42から伝わった。 [ケース定義](../cases/tsp-fk61-branch-first-difference.json)・[読解と測定](tsp-fk61-branch-first-difference.md)

141実行・3,512出力・446判定を確認した。冒頭5,880内部標本を検算し、先行計測との重複と、別ディレクトリでの再実行の要約・採取系列を照合した。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第79版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-branch-first-difference/manifest.json)

全体監査では99実行・214判定が通過した。計測の2実行と監査の2実行について、2,234入力・56出力をSHA-256で照合した。RTL9210B-CGに保存した出力は計52,721,024バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-branch-first-difference/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-branch-first-difference-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-branch-first-difference-new \
  --stage7-run stage7-fk61-branch-first-difference-new
```

## 第80版で口腔の節点40から41への流入差を照合する

3969の枝40→41の流量差は、ほぼ全量が直前の節点40の圧力差で説明できた。3968の節点40で、丸めた体積の差から求めた体積速度差は +2.13×10⁻¹¹ cm³/s、面積と長さの積を丸めない計算では +5.15×10⁻¹⁸ cm³/s だった。 [ケース定義](../cases/tsp-fk61-oral-onset-inflow.json)・[読解と測定](tsp-fk61-oral-onset-inflow.md)

142実行・3,534出力・450判定に通過した。先行する採取と共通区間を照合し、枝、内部節点、体積源の二段平滑、口端負荷を元データから再計算した。別ディレクトリでの再実行の採取系列と要約も照合した。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第80版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-oral-onset-inflow/manifest.json)

全体監査は99実行・214判定に通過した。計測2件と監査2件の2,274入力・56出力をSHA-256で照合し、RTL9210B-CGの出力は計2,033,408バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-oral-onset-inflow/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-oral-onset-inflow-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-oral-onset-inflow-new \
  --stage7-run stage7-fk61-oral-onset-inflow-new
```

## 第81版で節点40の展開式と全発話PCMを照合する

節点40の3968だけで体積差の展開式を使い、局所流量の誤差を1.50×10⁻¹¹から4.90×10⁻¹⁹ cm³/sへ減らした。固定上流とのPCMの初差は両条件とも2937だった。展開式の有無で変わったPCMは、全116,132フレームのうち7フレームだった。 [事前登録](../cases/tsp-fk61-node40-expanded-volume.json)・[測定と結果](tsp-fk61-node40-expanded-volume.md)

143実行・3,551出力・454判定に通過した。局所の枝・壁・体積源と出力段を独立に再計算し、2回の通常レンダーと観測データを照合した。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第81版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-node40-expanded-volume/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行について2,310入力・46出力をSHA-256で照合し、RTL9210B-CGに保存した出力は計9,826,142バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-node40-expanded-volume/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-node40-expanded-volume-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-node40-expanded-volume-new \
  --stage7-run stage7-fk61-node40-expanded-volume-new
```

## 第82版で制御境界5632以降の口端流量差を照合する

5632の節点42では、補間後のセル長の1 ULPの差が体積速度差の約98.76%を説明した。5632〜5875で4入力群の全16組を交換し、枝41→42の流量系列のみで5863の口端流量差の約93.7%を再現した。口端の5863・5864だけを戻した条件と全区間を戻した条件で、どちらも冒頭からPCM 2937まで一致した。 [ケース定義](../cases/tsp-fk61-control5632-mouth-flow.json)・[読解と測定](tsp-fk61-control5632-mouth-flow.md)

144実行・3,553出力・458判定を確認した。両版の体積源と、枝、壁、節点圧、口端負荷を元データから再計算し、別ディレクトリでの結果要約と状態軌道を照合した。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第82版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control5632-mouth-flow/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,042入力・16出力をSHA-256で照合した。RTL9210B-CGの出力は合計373,534バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control5632-mouth-flow/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control5632-mouth-flow-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control5632-mouth-flow-new \
  --stage7-run stage7-fk61-control5632-mouth-flow-new
```

## 第83版で口腔六節点から枝41への入力を照合する

節点38〜43を連成して5632〜5875を再計算した。枝41→42への流量差のうち、5675では局所体積源の影響が上流境界より大きく、5863では枝37→38の系列の交換で約83.6%を再現した。口端流量を全区間戻す比較では、上流境界と節点38〜41の体積源を交換した8条件でPCMが冒頭から2937まで一致した。 [ケース定義](../cases/tsp-fk61-control5632-upstream-drive.json)・[読解と測定](tsp-fk61-control5632-upstream-drive.md)

145実行・3,576出力・462判定に通過した。通常CLIと観測版、元の二節点比較の対照、32組の交換と6節点の体積源単独交換を照合した。別ディレクトリでの採取と状態軌道も一致した。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第83版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control5632-upstream-drive/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,368入力・58出力をSHA-256で照合した。RTL9210B-CGの出力は合計9,751,308バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control5632-upstream-drive/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control5632-upstream-drive-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control5632-upstream-drive-new \
  --stage7-run stage7-fk61-control5632-upstream-drive-new
```

## 第84版で咽頭から口腔への流入と体積源を照合する

節点28〜43を連成して5632〜5875を再計算した。5863の枝37→38の差は、節点28〜37の体積源だけで約81.2%、枝27→28からの咽頭流入だけで約17.8%、両方を交換すると約99.0%を再現した。咽頭流入が最大という事前予測は棄却した。口端流量を全区間戻した5条件で、冒頭からPCM 2937まで一致した。 [ケース定義](../cases/tsp-fk61-control5632-oral-inlet.json)・[読解と測定](tsp-fk61-control5632-oral-inlet.md)

146実行・3,599出力・466判定に通過した。入口での枝流量の加算順、通常CLIと観測版、六節点の対照条件、32組の交換と16節点の体積源単独交換を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第84版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control5632-oral-inlet/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,412入力・58出力をSHA-256で照合した。RTL9210B-CGの出力は合計21,179,874バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control5632-oral-inlet/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control5632-oral-inlet-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control5632-oral-inlet-new \
  --stage7-run stage7-fk61-control5632-oral-inlet-new
```

## 第85版で口腔の形状補間と体積源の開始値を照合する

制御境界5632・5760の口腔長・断面積の目標と補間を照合した。節点34の体積速度には断面積が強く効いた。節点28〜37の体積源をまとめて交換すると、5863の枝37→38では長さの交換による変化が面積の約8.6倍だった。両方の形状と咽頭流入に加えて二段平滑器の開始値を揃えるとPCMが冒頭から2937まで一致した。 [ケース定義](../cases/tsp-fk61-control5632-oral-geometry.json)・[読解と測定](tsp-fk61-control5632-oral-geometry.md)

147実行・3,628出力・471判定に通過した。通常CLIと観測版、増分からの形状再計算、16組の形状交換、平滑器の開始値と演算設定の4対照を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第85版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control5632-oral-geometry/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,467入力・70出力をSHA-256で照合した。RTL9210B-CGの出力は合計23,137,223バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control5632-oral-geometry/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control5632-oral-geometry-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control5632-oral-geometry-new \
  --stage7-run stage7-fk61-control5632-oral-geometry-new
```

## 第86版で口腔の中心線と5504より前の平滑履歴を照合する

5504・5632・5760の中心線と弧長を照合した。5504の唇・咽頭端までの弧長は一致し、5632・5760の口腔長の差は唇側にあった。5504〜5631の断面積の交換と比べ、5503終了時の平滑状態だけを交換した変化は、5631での第二極10節点のL2ノルムで約67倍だった。両方を揃えた8組でPCMが冒頭から2937まで一致した。 [ケース定義](../cases/tsp-fk61-control5504-oral-history.json)・[読解と測定](tsp-fk61-control5504-oral-history.md)

148実行・3,660出力・475判定に通過した。通常CLI、弧長の再計算、平滑器の離散式、32組の交換条件、二つの作業ディレクトリでの再現を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第86版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control5504-oral-history/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,545入力・76出力をSHA-256で照合した。RTL9210B-CGの出力は合計37,046,058バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control5504-oral-history/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control5504-oral-history-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control5504-oral-history-new \
  --stage7-run stage7-fk61-control5504-oral-history-new
```

## 第87版で発声初期からの体積源の寄与を照合する

3968〜5503の体積速度の差を、5503の両極に対する標本別の寄与に分解した。5120〜5247が最大で、直前の4992〜5119とは寄与がほぼ逆向きだった。後続区間を固定した比較では、5120〜5247だけの入力交換でもPCMが冒頭から2937まで一致した。 [ケース定義](../cases/tsp-fk61-onset-to-control5504-volume-history.json)・[読解と測定](tsp-fk61-onset-to-control5504-volume-history.md)

149実行・3,692出力・479判定に通過した。通常CLIとの一致、二段平滑の逐次計算と閉形式、全区間・ブロック単独・連続区間の交換結果と再現性を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第87版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-onset-to-control5504-volume-history/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,609入力・76出力をSHA-256で照合した。RTL9210B-CGの出力は合計168,436,187バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-onset-to-control5504-volume-history/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-onset-to-control5504-volume-history-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-onset-to-control5504-volume-history-new \
  --stage7-run stage7-fk61-onset-to-control5504-volume-history-new
```

## 第88版で断面積の再標本化と反復加算の丸めを照合する

4992・5120の節点29・34では、代表面積の差は再標本化の時点で現れ、速度制限後も残った。5120の補間開始面積の差は前ブロックの目標差より大きく、前の128回の加算の丸めで説明できた。5120〜5247の2節点の開始面積を上流に揃えると、冒頭からPCM 2937まで一致した。 [ケース定義](../cases/tsp-fk61-control4992-5120-area-targets.json)・[読解と測定](tsp-fk61-control4992-5120-area-targets.md)

150実行・3,730出力・484判定に通過した。通常CLIとの一致、再標本化・速度制限・補間の逐次計算、全12箇所の終了面積の丸め誤差、開始面積と目標面積の個別交換を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第88版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control4992-5120-area-targets/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,687入力・88出力をSHA-256で照合した。RTL9210B-CGの出力は合計167,281,561バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control4992-5120-area-targets/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control4992-5120-area-targets-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control4992-5120-area-targets-new \
  --stage7-run stage7-fk61-control4992-5120-area-targets-new
```

## 第89版で標本番号から直接求める断面積補間を照合する

節点29・34の4992・5120ブロックに直接補間を適用した。全512標本の面積を有理数の直線と照合し、4箇所の終端面積が目標に一致した。固定上流とのPCM初差は2937、差のあるフレーム数は2,355で、基準と同じだった。2ビルド間では14フレームが変わった。 [ケース定義](../cases/tsp-fk61-control4992-5120-indexed-area.json)・[読解と測定](tsp-fk61-control4992-5120-indexed-area.md)

151実行・3,757出力・488判定に通過した。通常CLI、調音の補間、局所の体積源・枝流量・圧力、口端出力、全発話PCMとそのRMSを照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第89版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control4992-5120-indexed-area/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,713入力・66出力をSHA-256で照合した。RTL9210B-CGの出力は合計60,289,074バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control4992-5120-indexed-area/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control4992-5120-indexed-area-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control4992-5120-indexed-area-new \
  --stage7-run stage7-fk61-control4992-5120-indexed-area-new
```

## 第90版で両版の面積補間を揃えて比較する

上流の隔離ビルドにも4992・5120の節点29・34に直接補間を適用した。両版が直接補間を使う条件では、対象512標本の面積の最大差が反復加算の4分の1、平滑後の体積速度のRMS差が約50分の1になった。4条件の全てで口端初差3971、PCM初差2937が残った。 [ケース定義](../cases/tsp-fk61-control4992-5120-indexed-area-paired.json)・[読解と測定](tsp-fk61-control4992-5120-indexed-area-paired.md)

152実行・3,784出力・492判定に通過した。上流の通常CLIと観測版、局所の幾何・体積速度・枝流量・節点圧、放射、全PCMを再計算し、研究版の保存済み出力と照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第90版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control4992-5120-indexed-area-paired/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,541入力・66出力をSHA-256で照合した。RTL9210B-CGの出力は合計60,291,574バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control4992-5120-indexed-area-paired/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control4992-5120-indexed-area-paired-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control4992-5120-indexed-area-paired-new \
  --stage7-run stage7-fk61-control4992-5120-indexed-area-paired-new
```

## 第91版で両版の体積差の展開式を照合する

面積補間を揃えた両版で、節点29・34の4992と5120からの2ブロックに体積差の展開式を適用した。幾何由来の差を引いた演算残差はRMSで1.151×10⁻¹¹から1.039×10⁻¹⁶ cm³/sに減った。PCM初差は2937。通常式の版間差の二乗和の99.90%を占めたフレーム16682の差が、上流に展開式を適用すると消えた。 [ケース定義](../cases/tsp-fk61-control4992-5120-expanded-volume-paired.json)・[読解と測定](tsp-fk61-control4992-5120-expanded-volume-paired.md)

153実行・3,814出力・496判定に通過した。局所の体積源、二段平滑、枝・壁・節点圧、冒頭の放射と出力段を再計算し、全発話PCMを4条件で照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第91版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-control4992-5120-expanded-volume-paired/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,823入力・72出力をSHA-256で照合した。RTL9210B-CGの出力は合計60,298,436バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-control4992-5120-expanded-volume-paired/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-control4992-5120-expanded-volume-paired-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-control4992-5120-expanded-volume-paired-new \
  --stage7-run stage7-fk61-control4992-5120-expanded-volume-paired-new
```

## 第92版でPCMフレーム16682の丸めを照合する

上流と研究版の通常式・展開式を再描画し、4条件の通常CLI、観測版、保存済みPCMを全116,132フレームで照合した。上流の展開式が16682の `f32` の中点を越えた。口端流量の履歴を単独で双方向に交換すると移植元のPCMを再現した。 [ケース定義](../cases/tsp-fk61-pcm16682-rounding.json)・[読解と測定](tsp-fk61-pcm16682-rounding.md)

154実行・3,822出力・500判定に通過した。4条件の放射と出力段、28通りの放射成分の交換、16682の丸めを再計算した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第92版のマニフェスト](../runs/stage7-evidence-update-20261123-fk61-pcm16682-rounding/manifest.json)

全体監査は99実行・214判定に通過した。4実行の2,777入力・28出力をSHA-256で照合した。RTL9210B-CGの出力は合計25,022,497バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-pcm16682-rounding/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-pcm16682-rounding-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-pcm16682-rounding-new \
  --stage7-run stage7-fk61-pcm16682-rounding-new
```

## 第93版で全発話の丸め前後の差を照合する

同じ4条件で全116,132フレームの出力を採取した。両版が展開式のとき、PCMのRMS差は約16分の1、変換前のRMS差は1.00337倍だった。104883では丸め前の上流と研究版の値が中点をまたぎ、PCMの差は1 ULPだった。差のある2,351フレームのうち956は複数ULPで、99%以上が1 ULPという予測は棄却した。 [ケース定義](../cases/tsp-fk61-full-pcm-rounding.json)・[読解と測定](tsp-fk61-full-pcm-rounding.md)

155実行・3,830出力・504判定に通過した。4条件の全発話の放射からPCMまでを再計算し、隣接値と中点、丸めの前後の誤差分布を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第93版のマニフェスト](../runs/stage7-evidence-update-20261124-fk61-full-pcm-rounding/manifest.json)

全体監査は99実行・214判定に通過した。4実行の2,793入力・28出力をSHA-256で照合した。RTL9210B-CGの出力は合計179,216,081バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-full-pcm-rounding/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-full-pcm-rounding-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-full-pcm-rounding-new \
  --stage7-run stage7-fk61-full-pcm-rounding-new
```

## 第94版で確認用発話FK61_02の丸め前後を照合する

確認用発話FK61_02の通常レンダーで、両版のCLI・観測版・保存済みPCMが全144,727フレーム一致した。129260の1 ULP差がPCM差の二乗和の99.999%を占め、複数ULP差の681フレームはすべてPCM振幅10⁻⁶以下だった。 [ケース定義](../cases/tsp-fk61-02-full-pcm-rounding.json)・[読解と測定](tsp-fk61-02-full-pcm-rounding.md)

156実行・3,836出力・508判定に通過した。FK61_02では全発話の放射と出力段、丸めの中点、振幅ごとのULP数を再計算した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第94版のマニフェスト](../runs/stage7-evidence-update-20261124-fk61-02-full-pcm-rounding/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,788入力・24出力をSHA-256で照合した。RTL9210B-CGの出力は合計112,807,668バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-fk61-02-full-pcm-rounding/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-fk61-02-full-pcm-rounding-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-fk61-02-full-pcm-rounding-new \
  --stage7-run stage7-fk61-02-full-pcm-rounding-new
```

## 第95版で男性体型MK61_02の丸め前後を照合する

同文の男性設定で、通常CLI・観測版・保存済みPCMを全144,727フレーム照合した。女性設定に対する男性設定の最大PCM差は0.125倍で、丸め前のRMS差は1.585倍だった。最大PCM差82703は1 ULPで、複数ULP差はすべてPCM振幅10⁻⁶以下だった。 [ケース定義](../cases/tsp-mk61-02-full-pcm-rounding.json)・[読解と測定](tsp-mk61-02-full-pcm-rounding.md)

157実行・3,842出力・512判定に通過した。男性設定の全発話で放射からPCMまでを再計算し、振幅別のULP数と女性設定との誤差比を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第95版のマニフェスト](../runs/stage7-evidence-update-20261124-mk61-02-full-pcm-rounding/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の4実行で2,801入力・24出力をSHA-256で照合した。RTL9210B-CGの出力は合計111,272,464バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-mk61-02-full-pcm-rounding/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-mk61-02-full-pcm-rounding-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-mk61-02-full-pcm-rounding-new \
  --stage7-run stage7-mk61-02-full-pcm-rounding-new
```

## 第96版で確認用12発話の丸め前後の誤差順位を照合する

確認用12発話の通常CLI・観測版・保存PCMを全1,487,586フレームで照合した。変換前とPCMのRMS差の順位相関は0.147で、66発話対中30対が逆転した。複数ULP差の4,582フレームはすべてPCM振幅10⁻⁶以下だった。試行間の比較では初回の不合格と修正後の実行を照合し、初回観測と修正後の観測のSHA-256が一致したことを確認対象にした。 [ケース定義](../cases/tsp-held-out-pcm-rounding.json)・[読解と測定](tsp-held-out-pcm-rounding.md)

158実行・3,870出力・517判定に通過した。12発話の放射からPCMまで、個別2発話の測定、順位と振幅別件数、初回の不合格記録を照合した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第96版のマニフェスト](../runs/stage7-evidence-update-20261124-held-out-pcm-rounding/manifest.json)

全体監査は99実行・214判定に通過した。計測と監査の5実行で3,087入力・96出力をSHA-256で照合した。RTL9210B-CGの出力は合計1,194,726,121バイトだった。 [全体監査のマニフェスト](../runs/plan-completion-release-v6-held-out-pcm-rounding/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_stage7_evidence.py stage7-held-out-pcm-rounding-new
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-held-out-pcm-rounding-new \
  --stage7-run stage7-held-out-pcm-rounding-new
```

## 第97版でCSDの先頭2句の丸め前後を照合する

初期姿勢と声源を揃えた `en001a` の同設定比較を追加した。201,600出力フレーム、403,200内部標本の放射合計・差分、FIR、DC除去、包絡、保持とPCMを元の系列から再計算した。最大絶対差は丸め前とPCMで同じ20,363フレーム、句間の2,160フレームでは丸め前のRMS差が1.524×10⁻¹⁴でPCMは一致した。微小な履歴をゼロにする処理を欠いた初回の不合格を保存し、修正後の2実行とバイト一致した6出力、および修正後の要約を照合した。 [ケース定義](../cases/csd-en001a-two-phrase-pcm-rounding.json)・[読解と測定](csd-en001a-two-phrase-pcm-rounding.md)

159実行・3,880出力・522判定に通過した。第97版を参照した全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第97版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-two-phrase-pcm-rounding/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-two-phrase-pcm-rounding/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-rounding-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-rounding-new \
  --stage7-run stage7-evidence-csd-rounding-new
```

## 第98版でCSD冒頭の口端流量差を照合する

`en001a` の先頭2句を同設定で描画し、両版の通常レンダー・観測版・保存済みの全201,600 PCMフレームを照合した。内部標本0・1の口端の制御目標、体積差分、二段平滑、放射負荷を独立計算と照合した。最初の口端流量差のうち99.99999%は負荷へ入る流量の単独交換で解消した。別の作業ディレクトリからの再実行と、要約を含む5出力のSHA-256が一致した。 [ケース定義](../cases/csd-en001a-first-lip-load.json)・[読解と測定](csd-en001a-first-lip-load.md)

160実行・3,888出力・526判定に通過した。第98版を参照した全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第98版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-first-lip-load/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-first-lip-load/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-first-lip-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-first-lip-new \
  --stage7-run stage7-evidence-csd-first-lip-new
```

## 第99版でCSDの初期口端形状を照合する

`en001a` の全201,600 PCMフレームを両版それぞれの保存済み出力と照合した。初期化直後と最初の出力フレーム後の格子を元に、中心線の区間距離・累積弧長、末端セルの再標本化と口腔長、最初の体積速度を再計算した。末端セル長だけの交換で最初の体積速度差を両方向で再現した。初回に研究版の試験入力が欠けて停止した記録、初回にも採取できた上流観測と修正後の一致、および修正後の2実行の要約を含む6出力の一致を確認した。 [ケース定義](../cases/csd-en001a-initial-oral-geometry.json)・[読解と測定](csd-en001a-initial-oral-geometry.md)

161実行・3,897出力・531判定に通過した。第99版を参照した全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第99版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-initial-oral-geometry/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-initial-oral-geometry/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-initial-oral-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-initial-oral-new \
  --stage7-run stage7-evidence-csd-initial-oral-new
```

## 第100版でCSDの中心座標交換を照合する

`en001a` の初期化と最初の制御更新で、測定線4・5の中心のx座標を距離計算に限って往復交換した。両版の各4条件で全PCM 201,600フレームずつと歌唱計画を照合した。4番の交換は累積値もPCMも対照に一致した。5番の交換で累積値が動いたのは測定線6だけで、口端セル長と初期体積速度は一致した。PCMの相違は上流8,688フレーム、研究版89,610フレームで、両版とも対照との最大差はフレーム134,534の1 ULPだった。元の中心座標、口端負荷、PCMを読み直して判定を再現し、別のディレクトリから得た6出力をハッシュ照合した。 [ケース定義](../cases/csd-en001a-centerline-coordinate-swap.json)・[読解と測定](csd-en001a-centerline-coordinate-swap.md)

162実行・3,906出力・536判定に通過した。第100版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第100版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-centerline-coordinate-swap/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-centerline-coordinate-swap/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-centerline-swap-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-centerline-swap-new \
  --stage7-run stage7-evidence-csd-centerline-swap-new
```

## 第101版でCSDの咽頭セル7を照合する

`en001a` の測定線5を交換したときの咽頭セル7を実測し、初期面積、最初の目標面積と内部標本0・1での体積の差分、二段平滑後の体積速度を照合した。両版で初期面積だけの交換が座標交換の201,600 PCMフレームを再現した。目標面積だけの交換では通常描画と一致した。最初の2内部標本の体積速度は全条件で一致した。2実行の要約、観測、PCM、PCMハッシュと計画、両版の観測差分の計6出力はバイト一致した。 [ケース定義](../cases/csd-en001a-pharynx-cell7-source.json)・[読解と測定](csd-en001a-pharynx-cell7-source.md)

163実行・3,915出力・541判定に通過した。第101版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第101版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-source/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-source/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-pharynx-cell7-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-pharynx-cell7-new \
  --stage7-run stage7-evidence-csd-pharynx-cell7-new
```

## 第102版でCSDの咽頭セル7の第1制御ブロックを照合する

`en001a` の初期面積だけを交換する条件を、両版で通常描画と比較した。96 kHzの先頭128内部標本で全節点の体積速度・配分・平滑を再計算し、節点19〜21の圧力と壁、4枝の流量を照合した。コンプライアンスのみの交換で標本0の圧力差を再現した。体積速度の差は上流で標本12から20点、研究版で標本8から32点に現れた。各201,600 PCMフレームと歌唱計画を先行実行に照合し、別々の一時ビルドで得た観測CSV・PCM・観測パッチ・要約の10出力をハッシュ照合した。 [ケース定義](../cases/csd-en001a-pharynx-cell7-first-block.json)・[読解と測定](csd-en001a-pharynx-cell7-first-block.md)

164実行・3,928出力・545判定に通過した。第102版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第102版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-first-block/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-first-block/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-pharynx-first-block-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-pharynx-first-block-new \
  --stage7-run stage7-evidence-csd-pharynx-first-block-new
```

## 第103版でCSDの咽頭セル7の一値交換を照合する

`en001a` の咽頭セル7のコンプライアンスを標本0だけ、同じ版の初期面積交換時の値へ切り替えた。両版で節点20の圧力差を再現した。上流の放射とPCMは通常と完全に一致した。研究版は標本2で全節点の圧力が一致しても標本3で再び差が現れ、壁放射86、口端流量100、出力PCM 26,133の順に最初の差を観測した。局所モデルの枝履歴を交換すると標本3の圧力差を再現した。6条件の各403,200内部標本の放射と各201,600フレームのPCMを再計算し、別の作業ディレクトリから再実行して得た圧力・放射、PCM、計画、パッチ、要約の7出力をハッシュ照合した。 [ケース定義](../cases/csd-en001a-pharynx-cell7-compliance-pulse.json)・[読解と検算](csd-en001a-pharynx-cell7-compliance-pulse.md)

165実行・3,938出力・549判定に通過した。第103版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第103版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-compliance-pulse/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-compliance-pulse/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-pharynx-compliance-pulse-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-pharynx-compliance-pulse-new \
  --stage7-run stage7-evidence-csd-pharynx-compliance-pulse-new
```

## 第104版でCSDの咽頭セル7の枝履歴を照合する

`en001a` の標本0で咽頭セル7のコンプライアンス一値を交換した。研究版では標本2で全節点の圧力が通常と一致した時点でも、枝19→20と20→21に予測どおりの微小な流量差を実測した。標本3の枝の求解前に両方の前回流量を戻すと、その後の観測圧力と201,600 PCMフレームが通常描画に一致した。左右個別・壁の履歴の交換ではPCMの差が残った。全12条件の先頭8標本で各5枝・4節点を再計算し、異なる作業ディレクトリからの2実行で18出力のハッシュを照合した。 [ケース定義](../cases/csd-en001a-pharynx-cell7-branch-history.json)・[読解と実測](csd-en001a-pharynx-cell7-branch-history.md)

166実行・3,959出力・553判定に通過した。第104版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第104版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-branch-history/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-branch-history/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-pharynx-branch-history-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-pharynx-branch-history-new \
  --stage7-run stage7-evidence-csd-pharynx-branch-history-new
```

## 第105版でCSDの確認曲en005aの全曲を照合する

`en005a` の全36句・106音符で、両版の各7,089,232内部標本と3,544,616出力フレームを照合した。両版とも1,103,539フレームで利得抑制が作動したため、その処理を含めて出力を再計算する実装を追加した。両版のPCMはそれぞれ独立計算とビット一致した。丸め前の最大差は第1拍前の20,363、PCMの最大差は第36句の3,214,976で1 ULP。両方の初回採取と停止記録を残し、元データを再検算して得た7出力は2実行でバイト一致した。 [ケース定義](../cases/csd-en005a-full-pcm-rounding.json)・[全曲の結果](csd-en005a-full-pcm-rounding.md)

167実行・3,966出力・558判定に通過した。第105版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [修正前の監査](../runs/stage7-evidence-update-20261124-csd-en005a-full-pcm-rounding/manifest.json)・[第105版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en005a-full-pcm-rounding-verified/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en005a-full-pcm-rounding/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-en005a-full-pcm-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-en005a-full-pcm-new \
  --stage7-run stage7-evidence-csd-en005a-full-pcm-new
```

## 第106版でCSDの確認曲en035aの全曲を照合する

`en035a` の全76句・109音符の通常設定を固定上流の公式PCMと照合した。同設定の両合成では、各11,181,176内部標本と5,590,588出力フレームを独立に再計算した。丸め前の最大差は `en005a` と一致する冒頭の20,363フレーム、PCMの最大差は第18句で1 ULP。利得抑制は両版で同じ618,105フレームに作動し、そのうちPCMが分かれたのは2フレームだった。別ディレクトリからの独立した2実行で、全曲の採取、PCMハッシュ、譜面計画、パッチと要約の7出力がバイト一致した。 [ケース定義](../cases/csd-en035a-full-pcm-rounding.json)・[実測と再現](csd-en035a-full-pcm-rounding.md)

168実行・3,976出力・562判定に通過した。第106版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第106版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en035a-full-pcm-rounding/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en035a-full-pcm-rounding/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-en035a-full-pcm-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-en035a-full-pcm-new \
  --stage7-run stage7-evidence-csd-en035a-full-pcm-new
```

## 第107版でCSDの調整曲en012aを確認曲2曲と照合する

`en012a` の全46句・185音符の通常出力を両版の保存PCMと照合した。同設定で描画した各13,226,668内部標本と6,613,334出力フレームを独立に再計算した。固定上流と研究版それぞれで冒頭76,672 PCMフレームが確認曲2曲と一致した。丸め前の最大差はその範囲の20,363、PCMの最大差は第14句の1 ULPだった。利得抑制の作動は両版で同じ3,216,415フレーム。2回の採取は各7判定に通過し、要約を含む7出力は同じSHA-256を示した。 [ケース定義](../cases/csd-en012a-full-pcm-rounding.json)・[実測と再現](csd-en012a-full-pcm-rounding.md)

第107版は169実行・3,986出力・566判定に通過した。第107版を参照する全体監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第107版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en012a-full-pcm-rounding/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en012a-full-pcm-rounding/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-en012a-full-pcm-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-en012a-full-pcm-new \
  --stage7-run stage7-evidence-csd-en012a-full-pcm-new
```

## 第108版でCSDの調整曲en001aを全曲へ広げる

`en001a` の全50句・86音符について、両版の独立計算を各6,220,800内部標本と3,110,400出力フレームで照合した。先頭2句の計画は両版とも一致し、第3句の準備直後の出力195,520で先頭2句のPCMと分かれた。4曲の丸め前最大差は共通の冒頭の20,363にあった。en001aのPCM最大差は第46句の拍の直前に1 ULP現れた。2回の採取は各8判定に通過した。 [ケース定義](../cases/csd-en001a-full-pcm-rounding.json)・[実測と再現](csd-en001a-full-pcm-rounding.md)

第108版は170実行・3,996出力・570判定に通過した。同版を参照する計画全体の監査も99実行・214判定に通過した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第108版のマニフェスト](../runs/stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding/manifest.json)・[全体監査のマニフェスト](../runs/plan-completion-release-v6-csd-en001a-full-pcm-rounding/manifest.json)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912
../../.venv/bin/python tools/audit_stage7_evidence.py stage7-evidence-csd-en001a-full-pcm-new
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-csd-en001a-full-pcm-new \
  --stage7-run stage7-evidence-csd-en001a-full-pcm-new
```
