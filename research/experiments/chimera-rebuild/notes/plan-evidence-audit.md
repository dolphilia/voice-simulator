# 第0〜7段階の実行証拠の照合

2026-11-22の[完了条件と観測値の照合](#完了条件と観測値の照合)では、入力範囲と数値基準を直接確かめた。以下の表と保存集計は初回の監査結果を保持している。

第7段階の追加実装・録音評価・試聴準備は、2026-11-22の[再照合](plan-evidence-stage7.md)に記録した。このページの監査結果は2026-11-21時点の記録である。

2026-11-21。固定上流のコミットは `c6147d0198890475dbe8a65a0bb8f56240c539b7` で、上流の作業ツリーに差分はなかった。計画の段階と比較条件を、[登録した代表実行](../cases/plan-evidence-audit.json)のマニフェスト・判定・成果へたどった。保存済みの実行を読み直すのが今回の比較条件で、音響エンジンを再ビルドする必要はなかった。[計画](../../../../docs/plans/chimera-research-rebuild-plan.md#実装順と段階の完了条件)

| 段階 | 確認した完了条件 | 記録された差や観測範囲 |
| --- | --- | --- |
| 0 基準と実行環境 | 一様管テスト・母音・IPA・歌唱の4件で固定コミット、コマンド、環境、ハッシュを確認。単一ケースCLIと、別ディレクトリから初期PCM16を再取得して照合する手順がある。[初期記録](../runs/upstream-20261119-a/manifest.json)・[CLI仕様と再実行](compare-upstream-pcm16.md) | 基準のモノラルPCM16再レンダーは288,000フレームでビット一致。形式とケースを出力に明示する。 |
| 1 一様管 | 17.5 cm・3 cm²・40セル・96 kHzのインパルスと並列R–L放射を照合。第1〜4共鳴の1/4波長近似との差は最大1.396%、時間応答と線形応答との差は最大0.262%。末尾振幅のピーク比は `3.87×10⁻⁷`。[登録条件と式](uniform-tube.md)・[別ディレクトリの実行](../runs/uniform-tube-20261119-b/summary.json) | 固定断面・小信号での判定。軟壁での再実行も第2段階で確認。 |
| 2 気道グラフ | 壁損失、分岐の正味流量、固定狭窄の圧力差、密閉圧縮、放射端開閉、閉鎖を移動して解除した過渡、乱流の方向とシード、鼻腔と側枝の12実行を照合。[定常狭窄](pressure-port.md)・[動的閉鎖](sliding-closure.md)・[乱流](turbulence.md)・[鼻腔と側枝](nasal-network.md) | 鼻腔と側枝の代表実行は固定形状。密閉圧縮で連続近似との差は1.030%、離散化をそろえた独立計算とのピーク比は `5.62×10⁻¹⁴` 以内。 |
| 3 肺圧と声門 | 固定声道で肺圧から発声を開始し、声帯の開大と口端閉鎖で消声を観測。面積パルスと流量を別々に比較し、肺圧補償と出力段の独立計算も確認。[声門結合](glottal-coupling.md)・[呼気](lung-breath.md)・[間引きとPCM](pcm-output.md) | 口端閉鎖後の平均絶対圧差は有声時の22.5%。面積と圧差に応じた流量は独立計算に照合済み。 |
| 4 調音と母音 | 成人男性の `/i ɑ u/` の有声遷移と、10母音の固定姿勢・PCMおよび隣接9遷移を確認。線形応答、LPC、F0、各時刻の形状を別の系列で保存。[有声遷移](../runs/vowel-motion-voice-vowels-20261119-c/summary.json)・[10母音](ten-vowel-benchmark.md) | `/ɔ/` の帯域幅2点は掃引範囲で欠測。`/ʌ/ → /ɝ/` の最小断面に残る段差は両実装で記録。 |
| 5 IPA・英語発話・歌唱 | `ɑpɑ / ɑbɑ / ɑsɑ / ɑzɑ / ɑmɑ` の計202,527フレームに対し、計画、閉鎖・摩擦・鼻音、実測時刻、ブロック分割を照合。英語の音素・未対応記号と、歌詞・MIDIの拍、破裂音の語尾、無音の復帰を確認。[基準5発話](../runs/bilabial-nasal-vcv-20261119-b/summary.json)・[英語](../runs/english-frontend-20261119-g/summary.json)・[歌唱](sung-voice.md) | 基準5発話で上流との最大PCM差は `2.33×10⁻¹⁰`。既知の未対応例として `Strut` の `/ɹ/` を出力する。 |
| 6 WASMとブラウザ | 固定音でCLI・WASM・Workletの波形と状態を比較。英語発話、IPA、歌唱、舌・唇の手動操作、保存ケースのCLIでの再現を確認。選択フレームを断面、圧力・流量、声門波形、加工前PCMのスペクトルの観測に使う。[固定音](../runs/worklet-fixed-voice-20261119-tract-regression/summary.json)・[圧力と流量](worklet-tract-acoustics.md)・[声門](worklet-glottal-scope.md)・[スペクトル](worklet-pcm-spectrum.md) | CLI・Workletの16、32、44.1、48、96 kHzを確認。96 kHzの再実行で181,248フレームはCLIとビット一致。発声中と減衰中のp99は1 msで、減衰中の1量子は4 msだった。予算は1.333 msで、Context時計の途切れとWASMメモリ成長は0件。[96 kHz](worklet-realtime-voice-96000.md) |
| 7 派生機能と評価 | 成人女性・子ども・補間体型、ビートボックス、韓国語・ロシア語・中国語、鳴禽と他3種の代表入力と観測を確認。仮想Web MIDI、三次元、録画、デュエットに上流対応表と実行実績がある。[対応表](interaction-presentation.md)・[選択した実行の判定](../runs/plan-evidence-audit-20261121-a/summary.json) | 固定上流との機構比較を確認。人間の録音に対する評価は未実施。物理MIDIと許可画面も未照合。 |

計画にある追加調査のうち、格子境界で平均断面と最小断面が異なる振る舞いと、口端R–L負荷・放射の時間差分には比較記録がある。同じ調音軌跡を異なる格子で通した閉鎖時刻・圧力・スペクトルの対照、圧差だけを差し替える声門フィードバック、固定LF駆動、既存波動管との同一終端・同一単位の直接比較は今回の代表実行から完了を確認できなかった。`/ʌ/ → /ɝ/` で確認した段差とは別に、突き出した下唇を引き込む上流の無視指定テストに対応する条件も確認する必要がある。[調査項目](../../../../docs/plans/chimera-research-rebuild-plan.md#最初に記録する調査テーマ)

## 保存済みの成果を読み直した結果

64実行の1,173判定を確認し、1,382成果（計5,216,642,985バイト）のサイズとSHA-256、保存されたケース定義995件のSHA-256を照合した。成果の実体は内蔵1,175件、RTL9210B-CG 193件、CT2000X8 14件。初期マニフェストはケース別のログと成果を読む。上流の版欄が空の2件は、合成を使わないCSV保存の対照。件数はマニフェスト上の登録パス単位なので、同じ実体を参照するパスも含む。[監査のマニフェスト](../runs/plan-evidence-audit-20261121-a/manifest.json)・[保存先別の集計元](../runs/plan-evidence-audit-20261121-a/summary.json)

一様管と半極座標格子の内蔵・外部の対照は、指定したCSVや要約がバイト一致した。抜粋保存の試験では、全系列の判定後にフレーム1・2・4の2列が残り、元CSVの記録ハッシュは列指定を誤った試験に保存された全CSVと一致した。以前の移行台帳の約181 GiBから約45 GiBへの縮小と、今回の `du -sh runs` の45Gを確認した。`du` の値は外部のリンク先を含まない。今回のハッシュ照合は全移行台帳のうち登録実行に含まれるものが対象。[移行台帳](../../../storage-migrations/2026-11-20-chimera-runs-v2/verification.json)・[CSV保存の失敗対照](../runs/storage-bad-column-20261120/manifest.json)

研究ワークスペースで `../../.venv/bin/python tools/audit_plan_evidence.py plan-evidence-audit-20261121-a` を実行した。`/tmp` ではPythonとスクリプトを絶対パスで指定して実行IDを `plan-evidence-audit-20261121-repeat` に替えた。両回で12判定が通り、要約がバイト一致した。PythonとRustの版はマニフェスト、両ボリュームのUUIDと書き込み可否は実行ログに保存。[計測器](../tools/audit_plan_evidence.py)・[再実行](../runs/plan-evidence-audit-20261121-repeat/manifest.json)

## 人間の録音を用いる最初の比較

固定上流では `compare/tsp.rs::run` が `render::say` で本文を発話し、`align_synth` と `measure_pair` で録音と合成の共通音素を照合する。`say` は英語辞書から句を作り、体型別基準F0を使い、50 msから調音を計画し、計画末尾から300 ms後まで48 kHzで出力する。合成側の音素時刻は音声で再アラインされ、スコアの調音区間と区別される。歌唱の `compare.rs::compare_song` は楽譜の音符を時計として、定常部の帯域とF0を比較する。TSPの話者分割とCSDの曲分割は独立した評価を設けるために参照する。[発話の評価](../../../../docs/reference/chimera-vocal-synth/upstream/docs/speech-comparison.md)・[歌唱の評価](../../../../docs/reference/chimera-vocal-synth/upstream/docs/csd-comparison.md)

次の単位はTSPの4話者・8発話で行う発話区間長の比較とした。調整用と確認用は話者・文章リストの両方を分けた。同じ20 msのRMS窓で、録音、固定上流、再実装の開始点・終了点を測る。追加のアラインメントを使わず、意図的に前後の無音を足した対照で時間の測り方を検証できる。録音との差は発話ごとの数値として残し、聞き手の記録は別にする。歌唱と音素別評価は後続の単位とする。[事前登録](../cases/tsp-active-duration-pilot.json)

McGillの48 kHz版を作業用ディスクに `curl --fail --location --continue-at - --output 48k.zip.partial <配布URL>` で取得し、253,816,919バイトとSHA-256が上流の `tools/tsp/fetch.sh` の固定値と一致してから `48k.zip` として確定した。対象8件のディレクトリエントリを `zipfile.ZipFile.getinfo` で確認した。音声は未展開で、まだ解析や試聴を行っていない。ローカルのJVS・ITA・UTAUは言語・資料・利用条件が異なるため、この英語の比較にはTSPを選んだ。[配置とハッシュ](../cases/tsp-active-duration-pilot.json)・[McGillの配布ページ](https://www.mmsp.ece.mcgill.ca/Documents/Data/)・[TSPのライセンス](https://www.mmsp.ece.mcgill.ca/Documents/Data/TSP-Speech-Database/Licence.html)

本文だけで `vocal-cli inspect` を試すと、事前登録の8件は `/ð/`、`/ɹ/`、`/ʃ/`、`/dʒ/` の未対応が原因で全件停止した。`speech_voice::run` の入力は `speech_voice`、言語は `english` で、`english_text` の入口は発音の計画を返す。最初の判定を残し、同じ4話者の240録音に対応する本文を調べた。候補が計画を作れた本文は、調整用の男女が共通して1文、確認用の男女が共通して2文だった。合成可能な範囲で発話区間を先に測れるように、計6録音を追加条件に登録した。[入力検査と不合格](../runs/tsp-active-duration-inspect-20261121-a/summary.json)・[入力検査の再実行手順](../tools/inspect_tsp_pilot.py)・[合成可能な範囲の登録](../cases/tsp-active-duration-supported.json)

## 完了条件と観測値の照合

2026-11-22。段階の各条件を、それを直接測った元のケースと判定名に対応付けた。前回の `read_record()` で出力のサイズとSHA-256、保存されたケース、実行の状態を照合し、`audit_plan_completion.py` で対象入力の全件、実測値、既知の不合格を確認した。母音の集約に記載された21件は、元のマニフェストのハッシュと各出力を読み直した。今回の141判定は照合処理の結果で、元の実験の合否は各マニフェストに残る。[計画](../../../../docs/plans/chimera-research-rebuild-plan.md#実装順と段階の完了条件)・[事前登録と第2版](../cases/plan-completion-evidence.json)・[照合処理](../tools/audit_plan_completion.py)

一様管では、固定上流の `AirwayNetwork::step` が枝流量を更新し、節点の収支を進めて口端の抵抗枝と慣性枝の流量を求める。放射流量の時間差分は cm³/s² で、周波数応答との比較にはこの差分のスペクトルを角周波数で割った流量を使う。`uniform_tube_resonances_match_quarter_wave_theory` は開閉管の奇数モードに口端補正を適用し、時間応答との比較は軟壁の有無の両方を通す。再レンダーでは `vocal-cli inspect` で設定、`render` で全系列を取り、計48,000点ずつでサンプル番号と有限性を検査した。入口の0番だけに体積1 cm³を注入し、口端放射は39番で始まった。[上流の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[計測式と観測点](uniform-tube.md)

| 段階 | 照合した入力と観測 |
| --- | --- |
| 0 基準 | 上流の一様管・母音・IPA・歌唱の4ケース、保存時のコマンドとツールチェーン、別ディレクトリで再生成したPCM16の一致。固定上流の作業ツリーに差分なし。[基準記録](../runs/upstream-20261119-a/manifest.json)・[再生成](../runs/compare-upstream-pcm16-20261121-final/summary.json) |
| 1 一様管 | 17.5 cm・3 cm²・40セル・96 kHz。剛体の第1〜4共鳴の1/4波長近似からの最大差は1.396%（基準3%未満）。FDTDと線形応答の最大差は剛体0.262%、軟壁0.263%（基準1.2%未満）。設定と生系列は両条件とも保存済み基準とバイト一致。剛体の要約はJSONのキー順に違いがあり、値は全件一致した。[剛体の再レンダー](../runs/plan-completion-rigid-20261122/manifest.json)・[軟壁の再レンダー](../runs/plan-completion-soft-wall-20261122/manifest.json) |
| 2 分岐・狭窄・可動壁 | 分岐の正味収支、軟壁の体積速度、密閉時の圧縮、狭窄の圧力差、面積補間で生じる流量源、閉鎖解除後の過渡、乱流源の式とシード、鼻腔の側枝を直接測った判定がそろった。[判定と出力](../runs/plan-completion-evidence-20261122-repeat/summary.json) |
| 3 肺圧・声門 | 肺圧を上げた固定声道の発声開始、声帯を開いた場合の面積と流量のパルス抑制、閉口による声門前後圧差の低下、間引きとPCMの独立計算を照合した。[固定声道の条件](glottal-coupling.md)・[出力段](pcm-output.md) |
| 4 調音・母音 | 成人男性の `/i ɑ u/` の有声窓、基準10母音の線形応答・LPC・F0、隣接9遷移。各母音の個別実行をたどり、`/ɔ/` の帯域幅2点は元の欠測として保持した。[10母音と欠測](ten-vowel-benchmark.md) |
| 5 発話・歌唱 | `ɑpɑ / ɑbɑ / ɑsɑ / ɑzɑ / ɑmɑ` の並びを保存済みのケースと実測の両方で確認。計202,527フレーム。閉鎖・破裂、摩擦源、鼻音、英語の発音と未対応記号、歌唱での拍と音素、語尾の無音復帰を個別判定へ対応付けた。[基準5発話](../runs/bilabial-nasal-vcv-20261119-b/summary.json)・[歌唱](sung-voice.md) |
| 6 WASM・ブラウザ | 固定発声のCLI・WASM・WorkletのPCMと状態、手動の舌と唇、ケース出力と再読、IPA時系列、英語発話と歌唱を照合した。16・32・44.1・48・96 kHzの発声中と停止後に中央値・p95・p99がそろい、該当するネイティブ側の固定発声の描画割り当ては0回。48 kHzの保存済みブラウザ要約にはWASMメモリ成長回数の欄がない。同レートの固定WASM比較には領域の安定性の判定がある。歌唱は別のネイティブABI観測で11,809回の割り当てを記録した。[レート別の観測値](../runs/plan-completion-evidence-20261122-repeat/summary.json)・[歌唱の計時](worklet-live-song-cross-browser.md) |
| 7 派生機能・評価 | ビートボックス、体型、3言語、4種類の動物、MIDI、三次元、録画、デュエット、TSP・CSD・試聴準備を含む16項目を第4版の一次出力監査へ接続した。人手F2注釈、人による試聴回答、物理MIDIは直接の記録が必要なまま。[第4版と未確認の観測](plan-evidence-stage7.md#未確認の観測) |

追加調査は、[閉鎖時の平均・最小面積と格子](tract-grid-lip-closure.md)、[口端の放射と理想円盤の軸上音圧](uniform-axial-observation.md)、[声門の圧差を差し替える比較](glottal-pressure-feedback.md)と[固定LF流量](fixed-lf-glottal-flow.md)、[下唇を引く際の放射](lip-tuck-voiced-radiation.md)、[同じ終端での波動管とFDTD](uniform-waveguide-matched.md)および[半セル慣性の比較](uniform-outlet-half-cell.md)に対応した。

### 保存した不合格

- 初回の照合では、固定LFで口端流量の交流RMSが2.85%低下して5%の予測に届かなかった実行と、Firefoxの歌唱再実行でp99が3 msとなり予算2.667 msを超えた試行を、全判定が真であることを求める欄に登録していた。第2版では両者の不合格項目を明示し、固定LFの入力・ピッチ・PCMと、歌唱のPCM・拍・状態の判定を照合した。歌唱の全時間判定を通過した別の実行も登録した。各実験の閾値は元の値を使った。[初回の照合](../runs/plan-completion-evidence-20261122-a/summary.json)・[固定LF](../runs/fixed-lf-glottal-flow-20261121-b/summary.json)・[歌唱の時間超過](../runs/worklet-live-song-cross-browser-20261121-repeat/summary.json)
- 既存波動管との直接終端では96 kHz・3,250 Hzの振幅差1.49 dBが0.9 dB基準を超えた。半セルを足した比較では、登録した16周波数の最大差が0.619 dBに縮まった。96 kHzの固定発声ではFirefoxの3試行目が時間予算の判定を落とした実行も照合した。[直接終端の不合格](../runs/uniform-waveguide-matched-20261121-bandlimited-repeat/summary.json)・[半セルの比較](../runs/uniform-outlet-half-cell-20261121-b/summary.json)・[固定発声の時間超過](../runs/worklet-realtime-cross-browser-96000-20261121-a/summary.json)

### 再実行と保存

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS 15.6.1 arm64、Python 3.14.4、NumPy 2.4.4、Rust 1.94.1。研究ワークスペースと `/private/tmp` から第2版の照合を実行し、各141判定が通過して要約はバイト一致した。75実行の1,694出力、計2,953,723,837バイトを照合した。剛体・軟壁は現行の通常CLIで各5・10判定が通った。初回を含む今回の5実行で、717入力と17出力のサイズ・SHA-256を照合し、採取物24,193,918バイトをRTL9210B-CGに保存した。[第2版](../runs/plan-completion-evidence-20261122-b/manifest.json)・[別ディレクトリでの再実行](../runs/plan-completion-evidence-20261122-repeat/manifest.json)

メモリ上でFDTDと線形応答の許容差を0.2%にすると一様管の該当判定だけが落ち、隣接遷移を1件除くと遷移の全件確認だけが落ちた。保存したケースと計画の基準は元の値を使う。CoreMIDIの入出力を再照会し、各0件だった。[物理MIDIの計測条件](plan-evidence-stage7.md#未確認の観測)

```bash
export CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728
../../.venv/bin/python tools/audit_plan_completion.py plan-completion-evidence-new
../../.venv/bin/python tools/measure_uniform_tube.py plan-completion-rigid-new upstream-20261119-a
../../.venv/bin/python tools/measure_uniform_tube.py plan-completion-soft-wall-new upstream-20261119-a --rigid-run plan-completion-rigid-new
```

## 第3版 現行のブラウザと描画を照合

固定上流の `Engine::render` はブロック内のエンジン処理を進めて `f32` PCMを出す。`crates/chimera/tests/engine.rs` の `output_does_not_depend_on_the_host_block_size` は、同じサンプル番号に操作を入れ、1・77・4,096・48,000点のブロックで128点の場合と一致するか比較する。`src/worklet/processor.ts` はページからの調音スコアに処理時計のオフセットを付け、`stopSpeech` で `Engine::stop_speech` に停止を送る。今回追加した再実装の停止対照は、ページが共有モジュールを読み込む時点の中止を扱う。サンプルの比較はWASMのロード時計から独立した出力フレームを使う。発話・歌唱とも比較窓の全区間で、量子 `q` の先頭は `128q`、出力長は残るフレーム数と128の小さい方となる。[固定上流のブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[停止の比較と呼び出し順](worklet-live-tsp-shared-wasm-abort-44100.md)

第2版のケースと141判定は、同じ監査を再実行して保存した。その結果を基準に、第3版では英語発話・歌唱・ブラウザ間比較・共有取得の停止で使った6実行と、入力検証の割り当てが工程合計から漏れた失敗1実行を追加した。第3版の初回は歌唱の報告へ英語の声門系列を要求したため、`KeyError('glottal')` で要約の生成前に停止した。当時のソースを使って同じ歌唱の出力から例外を再現した。歌唱は元の出力が収録した観測列を全点比較し、英語は観測列と別に収録した声門系列も照合するよう修正した。[第2版の再実行](../runs/plan-completion-current-web-20261122/summary.json)・[第3版の事前登録](../cases/plan-completion-evidence.json)・[初回停止の独立再現](/Volumes/RTL9210B-CG/voice-simulator/scratch/plan-completion-v3-a-failure-reproduced.txt)

| 対象 | 第3版で直接確認した値 |
| --- | --- |
| 英語発話・44.1 kHz | 全98,790フレームでネイティブ・オフライン・実時間のPCMが一致。128フレームごとの全772量子でネイティブ描画時の割り当て0回 |
| 歌唱・48 kHz | 全91,200フレームでネイティブ・オフライン・実時間のPCMが一致。全713量子でネイティブ描画時の割り当て0回。第2版には改善前に観測した11,809回の記録がある |
| 英語の共有と停止 | FirefoxとChromiumの両方で、WASMの応答保留中に停止側のContextがノード生成前に終了。オフラインと再開後のPCMのハッシュを44.1 kHzの基準に照合。48 kHzではFirefoxとChromiumのWAVが一致 |
| 現行ビルド | 実行時のWeb・WASMホストソース54ファイルを停止・再開の採取時のハッシュと照合。現行Rust 52試験、固定上流の一様管・エンジン・英語・肺圧17試験が通過。通常のWebビルドのWASMがブラウザの採取に使ったWASMと一致 |

英語と歌唱の代表採取ではブラウザの中央値が各1 ms、p95・p99が各2 ms。ブロック予算を超えた量子は各1件だった。既存の時間予算不合格と、実録音F2の人手注釈、人によるTSP・CSD試聴、物理MIDIの未観測を引き継いだ。現行のCoreMIDI入出力は各0件。今回の照合で、英語と歌唱における描画の割り当てと音響出力の一致について新しい根拠がそろった。[第3版の要約](../runs/plan-completion-current-web-20261122-v3-repeat/summary.json)・[実測に必要な記録](plan-evidence-stage7.md#未確認の観測)

macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1、Bun 1.4.4。ワークスペースと `/tmp` で第3版の169判定が各回通過し、要約がバイト一致した。各監査で83実行の1,834出力、計3,217,166,290バイトを元の配置から読んだ。標準ライブラリの独立検算で、英語と歌唱の全量子の長さとゼロ割り当て、WAVの全PCM、今回の成功3実行の1,037入力と14出力のサイズ・SHA-256を照合した。新しい採取物の実体25,359バイトはRTL9210B-CGに保存した。[初回の成功記録](../runs/plan-completion-current-web-20261122-v3-b/manifest.json)・[別ディレクトリの再実行](../runs/plan-completion-current-web-20261122-v3-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-plan-completion-current-web.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-current-web-v3-new
```

## 第4版で人手・実機の取得状況まで照合する

固定上流の `compare::tsp::measure_pair` は録音と合成の対応音素を解決し、12 kHzへ間引いた音声から25 ms窓のF2をHzで求める。試聴回答は発話の速さ・間や歌唱の揺れ・自然さを人が比較する記録で、音響量の出力とは別に採取する。Web MIDIの上流入口は `connectMidi` からポート・チャンネル・音番号ごとの保持状態を更新する。押鍵・離鍵の結果は研究版のWorkletで同じ出力フレームに対応付ける。上流の試験はTSPの欠測と音素対応、MIDIの同音保持と抜線を照合する。[発話の音素照合](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[F2の観測窓](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[MIDIの保持](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts)・[MIDIの試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/live-control.test.ts)

全体監査の第3版は第7段階の第4版を読み、3項目の状態が未観測であることを確認していた。第4版では既存の169判定を照合し、第7段階の第10版にある71実行と評価用ZIPの準備結果を連結する。第7段階に登録した実行IDから試聴の元CSV、実録音の注釈、MIDIとWorkletの一次記録を再検査し、準備・試験の結果と一次記録の状態を照合する。一次記録の登録がなければ未観測、TSPまたはCSDだけなら試聴は部分取得と予測した。[第3版の保存記録](../runs/plan-completion-current-web-20261122-v3-repeat/manifest.json)・[第4版の事前登録](../cases/plan-completion-evidence.json)・[一次記録の照合手順](plan-evidence-stage7.md#未確認の観測)

初回の第4版は現行Webビルドと採取時のWASMの照合で不合格だった。第3版のRustソースと比較すると、鳴禽のくちばし・気管・気管支などを観測するフィールドや取り出し口が増えていた。WASMのSHA-256は `550b9b16…` から `5f8685ad…` に変わった。この差は採取する成果自体に関わるため、同じ英語発話条件で現行ビルドを再採取した。ChromiumとFirefoxで、取得を保留した実時間発話だけがオフライン側の完了前に停止し、再開側は同じWASMを利用した。計30判定が通過し、両ブラウザのオフライン・再開後の各98,790 PCMフレームが元のWAVとバイト一致した。[初回の不合格](../runs/plan-completion-evidence-20261123-v4-a/summary.json)・[再採取の事前登録](../cases/worklet-live-tsp-shared-wasm-abort-44100.json)・[現行WASMでの再採取](../runs/worklet-live-tsp-shared-wasm-abort-44100-20261123-v2/manifest.json)

全体監査に `--stage7-run` を追加した。指定がない場合は第7段階の第10版を使う。登録した試聴・注釈・MIDIの実行IDを読み、既存の照合処理で元のCSVやデジタルPCMを再検査する。調整用と確認用の票、F2の窓数、受信・採用時刻を元データから確かめ、第7段階が報告した取得状況と一致することを確認する。評価用ZIPは準備の証拠として記録した。状態をメモリ上で取得済みに変えた対照と、試験回答3件・仮想MIDIを一次記録として指定した対照は、対応する判定で不合格になった。TSPまたはCSDの片方だけ、F2の一部の窓、機器情報が未記入の場合は部分取得として扱うことを状態の対照で確かめた。[全体監査の入口](../tools/audit_plan_completion.py)・[状態の対照と独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/plan-completion-v4-20261123-verification.json)

ワークスペースと `/tmp` から各182判定を通過した。第3版の169判定と83実行の結果を保持し、88実行の1,878出力（3,255,363,867バイト）を元の配置から照合した。成功2件の要約と入力一覧はバイト一致した。現行Rust 52試験、固定上流17試験と通常のWebビルドが通過した。第7段階第10版の回帰は156判定に合格し、先行要約と一致した。初回の不合格と再採取を含む計2,021入力・38出力を独立にハッシュ照合した。採取物計21,807,253バイトをRTL9210B-CGに保存した。現行のCoreMIDI入出力は各0件で、実録音のF2、人手試聴、物理MIDIは未登録だった。[全体監査の再実行](../runs/plan-completion-evidence-20261123-v4-repeat/manifest.json)・[第7段階の回帰](../runs/stage7-evidence-aggregate-regression-20261123/summary.json)・[評価者用ZIP](plan-evidence-stage7.md#試聴とf2注釈の資料を別の環境で開く)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v4-new \
  --stage7-run stage7-evidence-update-20261123-songbird-repeat
```

## 第5版で固定発声のWASMメモリを一次記録から照合する

第2〜4版が48 kHzで欠測と報告したメモリ増加回数は、旧手動停止のWorkletが保存したJSONにあった。第5版では16、32、44.1、48、96 kHzの5レートで保存ケースと一次記録を読み、各レートで全量子の連続性と増加0回を確認した。旧48 kHzは91,264フレーム、現行Chromiumの手動停止は93,056フレーム。後者は第4版で採取したWASMと同じSHA-256だった。ネイティブ側の固定発声の割り当て0回は、既存の別実行でABIの計数を確認した値。[48 kHzの条件と比較](worklet-realtime-voice-48000-memory.md)・[先行のネイティブ比較](../runs/wasm-fixed-voice-20261119-realtime-regression/summary.json)・[第5版の設定](../cases/plan-completion-evidence.json)

全体監査は第4版の182判定を保持し、両回で192判定、90実行と1,905出力の照合、現行Rust 52試験、固定上流17試験、通常Webビルドに合格した。要約はバイト一致した。今回の採取2回と監査2回は計1,468入力と54出力を別にハッシュ照合し、出力のうち119,256,812バイトはRTL9210B-CGに保存した。第7段階の実録音F2、人手試聴、物理MIDIは未登録のままで、CoreMIDI入出力数はいずれも0件。[第5版の再実行要約](../runs/plan-completion-fixed-voice-memory-v5-repeat/summary.json)・[保存記録](../runs/plan-completion-fixed-voice-memory-v5-repeat/manifest.json)・[一次記録の取込](plan-evidence-stage7.md#未確認の観測)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-memory-new \
  --stage7-run stage7-evidence-update-20261123-songbird-repeat
```

## 第6版で固定発声の停止後を一次PCMから照合する

固定上流の `Engine::render` は内部の制御境界でバッファを分け、`HumanVoice::render` が内部96 kHzで声門・気道網を更新する。放射流量の時間微分を間引きフィルターに送り、48 kHzの出力時刻にゲイン、直流除去、リミッターの順で進めて `f32` に丸める。直流除去は前回入出力、リミッターは包絡と保持カウンタを引き継ぐ。上流の `output_does_not_depend_on_the_host_block_size` は同じイベント入力のPCMを複数の分割でビット比較する。今回は固定母音 /i/ でこの分割条件を照合し、停止後の比較を進める。[上流の描画入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L218)・[上流の出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[研究版の出力段](../crates/vocal-core/src/output.rs#L103)

第5版の192判定を保持し、停止後の5実行を一次記録へつなぐ。出力48 kHz、全93,056フレームを開放前、有声、停止後に分け、分割128・77、上流、換算順を揃えた版を比較する。対照と変更版は各分割間で一致し、上流との差は停止後だけに残ると予測する。変更版で13から11フレームに減り、初差55,880の1 ULPと最大絶対差は同じという局所計測の結果を一次PCMから確認する。初回のログ解析失敗は元の例外と出力を照合する。合否には持ち越し圧比較の既存閾値を使う。[事前登録](../cases/plan-completion-evidence.json)・[停止後の始点の読解](fixed-voice-release-output-48000.md)・[枝の連続比較](fixed-voice-release-lip-branch-48000.md#持ち越し圧を揃えた連続描画の結果)

保存したfloat32 WAVを読み直すと、5実行の対照は全PCMで一致し、変更版も分割128と77で一致した。枝47→48の持ち越し圧を上流順にした隔離版では7フレームが上流と一致するようになり、5フレームが新たに分かれた。差は停止後だけに現れ、初差55,880フレームと最大絶対差 `5.820766091346741e-11` は同じだった。Pythonの `struct` でRIFFの形式チャンクとデータを直接読んだ計算も同じ結果を得た。有声区間のPCMを1点変えた対照、上流参照の登録ハッシュを変えた対照、例外の登録文を変えた対照は、対応する判定が落ちた。初回は放射ログのラベル衝突で集計前に止まり、保存した14出力と例外を照合した。[監査の実装](../tools/audit_plan_completion.py)・[初回の例外](../runs/fixed-voice-release-output-48000-a/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-plan-completion-release-v6.json)

研究ワークスペースと `/tmp` から各213判定を通過した。98実行の2,122出力（3,396,687,207バイト）を照合し、現行Rust 52試験、固定上流17試験と通常Webビルドを通過した。監査2回の要約はバイト一致し、計994入力・12出力を別にハッシュ照合した。新規ログ23,886バイトをRTL9210B-CGに保存した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で実行した。[初回の監査](../runs/plan-completion-release-v6-a/manifest.json)・[再実行の要約](../runs/plan-completion-release-v6-repeat/summary.json)・[再実行マニフェスト](../runs/plan-completion-release-v6-repeat/manifest.json)

第7段階では実録音F2の人手注釈、人によるTSP・CSD試聴、物理MIDIの一次記録が未登録だった。登録元となる25件の合格マニフェストとCoreMIDIの実行時一覧を確認し、該当する人手・実機の取得実行は無く、入出力は各0件だった。第2版で保存した固定LF・波動管の直接終端・Firefoxの時間予算の不合格も引き継いだ。第5版で照合した各レートのWASMメモリ増加0回と、今回の隔離版のPCM差はそれぞれの採取条件に基づく。[一次記録の取込](plan-evidence-stage7.md#未確認の観測)・[保存した不合格](#保存した不合格)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-release-v6-new \
  --stage7-run stage7-evidence-update-20261123-songbird-repeat
```

## 第7版で固定母音 /ɔ/ の高域の欠測と追加計測を照合する

基準10母音の4,600 Hzの掃引で欠測だった /ɔ/ の2ピークに、掃引上限と周波数刻みを個別に変更した測定を追加した。4条件すべてで固定上流と研究CLIを実行し、従来の700点と欠測を再現した。上限を約7,791 Hzに延ばすと、低いピークの左右交点は4,209.25・4,734.25 Hz、高いピークの交点は4,513.02・4,621.99 Hzと独立に求められた。低いピークの右交点までの範囲は高いピークも含む。監査は保存された応答と節点・枝から交点の推定を再計算し、4条件の入力、応答、ピーク、要約の37成果を別ディレクトリからの再実行と照合する。 [事前登録](../cases/vowel-open-o-high-bandwidth.json)・[読解と測定](vowel-open-o-high-bandwidth.md)

初回の全体監査では、初回測定マニフェストの登録SHA-256が2文字不足していた。36件の条件別成果と要約は2実行でバイト一致しており、不合格は独立再実行のマニフェスト照合の1件だった。測定実行から計算した完全なSHA-256を登録し、初回監査の不合格も監査対象に加えた。 [初回の不合格マニフェスト](../runs/plan-completion-v7-open-o-bandwidth-20261124/manifest.json)・[修正後の登録](../cases/plan-completion-evidence.json)

修正後は第6版の214判定を引き継ぎ、第7版の103実行・2,224成果・222判定に通過した。追加計測2回と監査2回の計1,374入力・96出力をSHA-256で照合し、出力8,506,944バイトをRTL9210B-CGに保存した。実録音F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIの実測は後日に回す。 [修正後の全体監査](../runs/plan-completion-v7-open-o-bandwidth-20261124-verified/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v7-open-o-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第8版で /ɔ/ の連続母音列と固定発声のLPC差を照合する

元の2波形を全フレームで再現し、揃えた32条件ずつと固定発声の旧条件の計65窓で、LPCの入力・全根・公開ピークを照合した。旧条件の未丸め差49.07 Hzのうち、0.300秒開始で波形を交換した2経路の平均は15.64 Hz、分析設定を交換した平均は33.42 Hzだった。16 kHz・18次・100 msを共通にすると、0.300秒開始の差は0.20 Hzだった。初回に3ピーク以上を求める集計が1窓で不合格になり、元の実行を保存した。修正後は公開推定器の選別と独立計算をすべての窓で照合し、旧条件の最初の3ピークと、比較用の第1ピークをそれぞれ確認した。 [事前登録](../cases/vowel-open-o-lpc-matched.json)・[測定と初回の不合格](vowel-open-o-lpc-matched.md#観測結果)

第7版の222判定を引き継ぎ、第8版の107実行・2,263成果・230判定に通過した。4実行の985入力・39出力をSHA-256で照合し、10,420,804バイトをRTL9210B-CGに保存した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第8版のマニフェスト](../runs/plan-completion-v8-open-o-lpc-20261124/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v8-open-o-lpc-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第9版で /ɔ/ の固定窓のLPC次数と根の選別を照合する

先行計測と同じ分析入力を保存PCMからビット一致で復元し、12〜18次の公開推定器の応答を再計算した。第1ピークの12次と18次の差は帯域幅上限を外しても112.91 Hzだった。850〜1,250 Hzでは14次で根が現れ、2.3 kHz付近の12・13次の生の根は600 Hzの帯域幅上限で落ちていた。共有する自己相関と次数を上げる係数更新を照合し、全105根を独立計算に対応付けた。同じプローブのTSPで使う既定の設定も再実行し、従来の上流観測、スペクトルと要約に一致した。 [事前登録](../cases/vowel-open-o-lpc-orders.json)・[測定結果](vowel-open-o-lpc-orders.md#観測結果)・[TSPの回帰確認](../runs/tsp-lpc-pre-emphasis-20261124-order-probe-regression/manifest.json)

第8版の230判定を引き継ぎ、第9版は112実行・2,301成果・240判定に通過した。追加の4実行の660入力・33出力をSHA-256で照合し、出力1,330,492バイトをRTL9210B-CGに保存した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第9版のマニフェスト](../runs/plan-completion-v9-open-o-lpc-orders-20261124/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v9-open-o-lpc-orders-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第10版で固定LFの放射の減少を倍音と成分に分ける

通常発声と固定LFを、固定姿勢の /ɑ/、110 Hz、同じ22周期の区間で再描画した。保存PCMに全フレームが一致し、壁の放射を加えた総放射の差分を再構成できた。口端流量の基本波を通常発声の値に置換したスペクトル上の比較では、口端RMSが6.40%低下した。元の観測は2.85%低下で、旧5%判定の不合格を保持した。総放射の交流平均二乗の減少の94.85%は口端差分の自己項、5.07%は壁との交差項だった。監査で直接採取データと保存出力からこの内訳を再計算した。 [事前登録](../cases/fixed-lf-radiation-harmonic-budget.json)・[倍音と放射成分の測定](fixed-lf-radiation-harmonic-budget.md)・[旧判定](../runs/fixed-lf-glottal-flow-20261121-b/manifest.json)

第9版の240判定を引き継ぎ、第10版の115実行・2,321成果・247判定に通過した。追加の3実行の903入力・20出力をSHA-256で照合し、21,390,734バイトをRTL9210B-CGに保存した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIの実測は後日に回す。 [第10版の全体監査](../runs/plan-completion-v10-lf-radiation-budget-20261124/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v10-lf-budget-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第11版で固定LFの第6・第7倍音の入力と伝達を照合する

固定 /ɑ/ の660 Hzと770 Hzの複素口端流量差を、声門流量と伝達比の変化に分けた。伝達比の項はこの差の0.016%と0.054%だった。時系列の後退差分と窓端補正を含む独立計算は、前回の2成分の平均二乗差と一致した。固定上流、研究版の通常CLI、節点連立計算による固定姿勢の線形複素応答を照合し、新しい要約と8成果は異なる作業ディレクトリから再現した。旧5%判定は元の観測に対して不合格を保持した。 [ケース定義](../cases/fixed-lf-harmonic-transfer.json)・[読解と測定結果](fixed-lf-harmonic-transfer.md)・[旧判定](../runs/fixed-lf-glottal-flow-20261121-b/manifest.json)

第10版の247判定を引き継ぎ、第11版の118実行・2,353成果・254判定に通過した。新しい3実行の925入力・32出力をSHA-256で照合し、そのうち成果40,738バイトをRTL9210B-CGに保存した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第11版のマニフェスト](../runs/plan-completion-v11-lf-harmonic-transfer-20261124/manifest.json)・[照合結果](../runs/plan-completion-v11-lf-harmonic-transfer-20261124/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v11-lf-transfer-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第12版で固定 /ɑ/ の離散時間インパルス応答を照合する

96 kHz・0.60秒の固定声道の標本を両版で比較し、660 Hz・770 Hzの複素応答を枝・壁・口端の離散節点方程式に照合した。0.20秒の初回は減衰する尾部を打ち切ったため3判定が不合格だった。延長して旧記録と冒頭19,200標本がビット一致し、同じ許容差で21判定に通過した。異なる作業ディレクトリから再実行し、圧縮時系列など5成果と要約のバイト一致を確認した。 [事前登録と改訂理由](../cases/fixed-alpha-discrete-impulse.json)・[測定結果](fixed-alpha-discrete-impulse.md)・[初回の不合格](../runs/fixed-alpha-discrete-impulse-20261124-registered/summary.json)

第11版の254判定を引き継ぎ、第12版の122実行・2,392成果・262判定に通過した。新しい4実行の1,071入力・39出力をSHA-256で照合し、そのうち成果33,003,913バイトをRTL9210B-CGに保存した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第12版のマニフェスト](../runs/plan-completion-v12-discrete-alpha-20261124/manifest.json)・[全判定](../runs/plan-completion-v12-discrete-alpha-20261124/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v12-discrete-alpha-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第13版で固定 /ɑ/ の定常流に対する口端応答を照合する

固定気道の定常流を0と139.89 cm³/sにし、繰り返し実行と同条件の無加振系列から660 Hzと770 Hzの小信号応答を再計算した。差波形は固定上流と研究版で相対5.18×10⁻¹¹以内、複素応答は枝の二次損失を微分した独立計算と相対4.31×10⁻⁷以内で一致した。従来の小信号インパルス入口も保存時系列に一致した。 [事前登録](../cases/fixed-alpha-mean-flow.json)・[観測結果](fixed-alpha-mean-flow.md)

第12版の262判定を引き継ぎ、第13版は125実行・2,420成果・268判定に通過した。新しい3実行の960入力・28出力をSHA-256で照合した。RTL9210B-CG上で同一内容の圧縮観測1件をハードリンクで共用し、成果の実体は14,321,186バイトだった。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第13版のマニフェスト](../runs/plan-completion-v13-alpha-mean-flow-20261124/manifest.json)・[全判定](../runs/plan-completion-v13-alpha-mean-flow-20261124/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v13-alpha-mean-flow-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第14版で固定 /ɑ/ の周期流量と全履歴の再入力を照合する

通常発声・固定LFの全声門流量を固定上流に再入力し、上流の咽頭入口圧・口端流量・鼻端流量・総放射を各57,600標本で元の有声記録にビット一致させた。22周期の反復でも660 Hzと770 Hzの複素比を相対1.76×10⁻⁸以内で再現した。最初の実行はPythonの一時領域を開く処理で停止し、記録を保持した。修正後の2実行は各25判定を通過し、要約と7成果がバイト一致した。 [事前登録](../cases/fixed-alpha-periodic-flow.json)・[結果](fixed-alpha-periodic-flow.md)・[初回の停止](../runs/fixed-alpha-periodic-flow-20261124-registered/manifest.json)

第13版の268判定を引き継ぎ、第14版は128実行・2,450成果・275判定に通過した。初回を含む4実行の1,101入力・34出力をSHA-256で照合した。RTL9210B-CG上で同一の圧縮観測をハードリンクで共用し、成果の実体は31,369,990バイトだった。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第14版のマニフェスト](../runs/plan-completion-v14-alpha-periodic-flow-20261124/manifest.json)・[全判定](../runs/plan-completion-v14-alpha-periodic-flow-20261124/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v14-alpha-periodic-flow-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第15版で固定 /ɑ/ の口端応答を枝ごとの二次損失に分ける

最後の22周期と直前1標本の節点圧・枝流量を使い、二次損失の圧力差を38枝で求めた。定常点での接線を引いた残差から660 Hz・770 Hzの口端応答の複素差を、相対3.83×10⁻¹¹以内で再構成した。初回の枝番号のずれによる8判定の不合格を保持し、向き付きの両端を使って再照合した。観測の実体は初回と同じバイト列で、修正後の2実行の要約と6成果も一致した。 [事前登録](../cases/fixed-alpha-branch-loss.json)・[読解と結果](fixed-alpha-branch-loss.md)・[初回の不合格](../runs/fixed-alpha-branch-loss-20261124-registered/summary.json)

第14版の275判定を引き継ぎ、第15版は132実行・2,487成果・283判定に通過した。初回を含む4実行の1,127入力・37出力をSHA-256で照合した。同じ圧縮観測をRTL9210B-CGで1つにまとめ、成果の実体は53,439,065バイトだった。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第15版のマニフェスト](../runs/plan-completion-v15-alpha-branch-loss-20261124/manifest.json)・[全判定](../runs/plan-completion-v15-alpha-branch-loss-20261124/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v15-alpha-branch-loss-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第16版で固定 /ɑ/ の咽頭の1枝・3枝を接線化して照合する

固定上流と研究版の隔離ビルドで、対象枝の二次損失を定常点の接線に替えた。660 Hz・770 Hzで1枝は複素差の18.29〜19.05%、3枝は46.33〜48.21%を減らした。未選択枝の残差まで含めた再構成の最大相対誤差は5.68×10⁻¹²だった。定常流の初回2判定の不合格と観測を保存し、改訂判定は同じ波形を入口定常圧・基準流量に基づく尺度で照合した。2実行の要約と6成果はバイト一致した。 [事前登録と判定の改訂](../cases/fixed-alpha-loss-tangent.json)・[観測と計算](fixed-alpha-loss-tangent.md)・[旧判定](../runs/fixed-alpha-loss-tangent-20261124-rebuilt/summary.json)

第15版の283判定を引き継ぎ、第16版は136実行・2,520成果・291判定に通過した。停止した隔離ビルド2件を含む6実行の1,428入力・41出力をSHA-256で照合した。圧縮観測の重複を共用したRTL9210B-CG上の成果の実体は100,022,961バイトだった。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第16版のマニフェスト](../runs/plan-completion-v16-alpha-loss-tangent-20261124/manifest.json)・[全判定](../runs/plan-completion-v16-alpha-loss-tangent-20261124/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v16-alpha-loss-tangent-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```

## 第17版で固定 /ɑ/ の接線を受動化した対照を照合する

順方向の接線の負の圧力差をゼロにし、逆流には二次損失を使った。観測した対象枝の負の仕事率が丸め許容差内で消えること、定常流対照が接線時とビット一致することを確認した。再描画した660 Hz・770 Hzの複素応答の変化を、式を変えた枝の局所圧力差と、選択・未選択枝の流量が変わった分に分け、相対6.49×10⁻¹²以内で再構成した。 [事前登録](../cases/fixed-alpha-loss-passive.json)・[読解と結果](fixed-alpha-loss-passive.md)

第16版の291判定を引き継ぎ、第17版は139実行・2,544成果・297判定に通過した。新しい3実行の1,021入力・24出力をSHA-256で照合した。同じ圧縮観測を外部ディスク上で共用し、成果の実体は99,996,412バイトだった。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。 [第17版のマニフェスト](../runs/plan-completion-v17-alpha-loss-passive-20261124/manifest.json)・[全判定](../runs/plan-completion-v17-alpha-loss-passive-20261124/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-v17-alpha-loss-passive-new \
  --stage7-run stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding
```
