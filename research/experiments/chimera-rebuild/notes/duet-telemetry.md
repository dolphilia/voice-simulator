# デュエットの声部別テレメトリ

## 読解と事前登録

固定上流の `chimera render notes … --tele` は、音符と歌詞を `plan_song` で時刻付きの調音指示にし、`render_tracked` で音声を進めます。`TeleRecorder::new` は処理前に1行を採り、以後は768出力サンプルを処理するたびに `snap` を呼びます。終端の端数区間では追加の観測を作りません。音声長を `N`、ホップを `H` とすると、行数は `1 + floor(N/H)`、行 `i` の観測は `iH` サンプル処理した直後です。CLIの0始まりの出力トレースでは、同じ状態は `iH−1` 行に相当します。最初の行はステップ前です。[音符の読み込みと保存](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L529)・[処理を区切る順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L485)

`CHTL` の48バイトヘッダーはバージョン、出力サンプルレート、ホップ、行数、行幅、各配列の要素数、女性・子どもの混合係数を持ちます。ヘッダーの後はリトルエンディアンの `f32` で、行の幅は `11 + 17 + 3(P+O) + 2S`。`P` と `O` は咽頭・口腔のセル数、`S=32` は声門系列の点数です。11個のスカラーには長さ cm、軟口蓋ポート cm²、基本周波数 Hz、肺圧 cmH₂O、振幅RMS、乱流源の位置と強さ、ゲート、秒の時計が入ります。調音17軸の後にセルの面積 cm²、圧力RMS dyn/cm²、口側へ正の流量 cm³/s、声門面積と流量を格納します。[上流のバイナリ定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L411)・[上流の構造体](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L131)

上流の圧力RMSは内部4サンプルごとの二乗をホップ内で平均して平方根を採り、読み出しで和をリセットします。流量は制御周期ごとに `1−exp(−dt/0.03)` で平滑化します。声門波形は出力サンプルレートの履歴から直近の完結した2周期を読み、周期が足りないときは直近1,024サンプルを用います。既存の研究実装のPCM経路を通し、この採取を外から併設します。RMSはWAVへ実際に保存されるPCMから計算し、長さと流量は研究実装のセルの長さと独自の口側境界から取ります。上流の `render notes` は独自の初期調音や出力設定を使うため、同じ旋律でもセル値や波形の完全一致は仮定しません。[圧力と声門波形の蓄積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L425)・[流量の平滑化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L543)・[観測の読み出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L597)

上流の `DuetPage` はWAVと各声部のファイルを読み、`TeleTrack` は再生秒 `t` から `floor(t·rate/H + 10⁻⁶)` を求めて、先頭から最終行までに制限します。`Head` はシークの世代も描画に渡します。固定上流の3件のテレメトリ試験と6件の再生試験で、形式、境界、切り詰め、中断を確認しました。この工程では、一度採った再生秒から各声部の行を選び、行番号・音源サンプル・F0・口唇の開きを研究画面に表示します。[上流の読出し](../../../../docs/reference/chimera-vocal-synth/upstream/src/show/tele.ts#L65)・[画面への接続](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L171)・[テスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts)

前回の48 kHzの二声では、音声長91,200・97,920フレームから、119・128行の採取を予測します。固定上流のCLIにも同じ旋律・体型・開始時刻を渡します。両CLIのファイルを、独立したPythonのバイト読出しと両実装のTypeScript読出しに通します。研究側のセル面積、圧力RMS、平滑化流量、加工前PCMのRMSを別の既存CLI経路から計算します。実ブラウザでは767・768・769、30,719・30,720・30,721サンプル、片方の採取が終わった位置、混合音源末尾と、再生中の前後シークを照合します。[事前登録](../cases/duet-telemetry.json)・[前回の二声音源](duet-transport.md#実装と実測)

## 実装と測定

`render-pcm-tele` は既存の歌唱スコア、`OutputStage`、WAVとCSVへの出力を通し、採取用の `Recorder` をつなぎます。圧力は内部4サンプルごと、流量は次の制御更新に入る直前、声門波形と振幅RMSは出力サンプルごとに読みます。表示用の時計は、この採取回数から `iH / rate` 秒を計算します。ブラウザでは同じ再生スナップショットから全声部の行を選びます。バイト数の合わない声部が含まれると公演の読込エラーを表示します。[CLIの採取](../crates/vocal-cli/src/timing_case/speech_voice/telemetry.rs)・[TypeScriptの読出し](../../../../web/prototypes/chimera-research/src/duet-telemetry.ts)・[研究画面](../../../../web/prototypes/chimera-research/src/duet-page.tsx)

初回は33項目すべてを通過しました。音源と同じサンプル0を基準に119行と128行を保存しました。両CLIで行数とセル数は同じで、すべての観測時計が `f32` の数値として一致しました。4ファイルのペイロードを候補と固定上流で読み出し、元のバイト列まで同じことをSHA-256で確認しました。上流は採取の有無でWAVが一致し、候補の各WAVは前回との比較でバイト一致しました。候補の第2声部を77フレームのホストブロックで実行しても、公開デモの128フレーム条件とテレメトリが一致しました。[初回の判定](../runs/duet-telemetry-20261120-a/summary.json)・[2種類の読出しの比較](../runs/duet-telemetry-20261120-a/artifacts/decoders.json)

独立したCLIトレースで、処理開始後の全採取行のF0・口唇開度・ゲート・セル面積・流量を照合しました。圧力RMSは3ホップをトレースから再計算し、最大差は約 `1.21×10⁻⁴ dyn/cm²` でした。WAVから再計算した振幅RMSは最大 `1.45×10⁻⁸` 差で、最初のホップでは声門波形も履歴から独立に復元できました。声帯が振動している間の周期境界と上流の圧力・流量そのものは、初期条件まで揃えた比較が残ります。[独立採取を含むマニフェスト](../runs/duet-telemetry-20261120-a/manifest.json)

固定上流との差は処理前の行にもあります。両声部とも、舌先の座標は候補で `(6.45, 7.30) cm`、上流で約 `(6.2414, 6.8105) cm` でした。他の15軸と初期F0、口唇開度は一致しました。固定上流の `ArticulatorBank::new` は初期舌先を `rest_tip` で計算し、研究CLIはこのケースに明記した座標を使います。最初の幾何寸法も異なり、例えば第1声部の口腔長は候補で8.2990 cm、上流で8.3379 cmでした。この二声で上流の波形まで比較するには、まず舌先座標だけを揃えた対照で初期セル面積と初回更新を測ります。[固定上流の初期姿勢](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L79)・[入力姿勢](../cases/song-voice-long.json)・[初回のバイナリと上流対照](../runs/duet-telemetry-20261120-a/manifest.json)

Chromiumの停止中のシークでは、音源位置767・768・769に対して両声部が0・768・768を表示しました。97,152では第1声部が90,624を保持し、第2声部は96,768を選びました。混合音源の末尾105,600では、それぞれ90,624と97,536を保持しました。再生中に前後へシークすると、両声部が切り替わった共通の時刻から行を選び直しました。ペイロードを4バイト切り詰めた試行では両デコーダーが拒否し、研究画面も再生を開始しませんでした。[ブラウザの出力](../runs/duet-telemetry-20261120-final/artifacts/browser-telemetry.json)

混合デモWAVの前回とのハッシュ照合を加え、研究ディレクトリと `/tmp` からの実行で各34項目を通過しました。環境はmacOS arm64、Rust 1.94.1、Bun 1.4.4、Node v24.19.0、Chromium 156.0.8078.4です。再生時計の回帰25項目と `vocal-cli`・`vocal-core` の14テストも通過しました。すべてのコマンド、入力と出力のSHA-256はマニフェストにあります。[最終実行](../runs/duet-telemetry-20261120-final/manifest.json)・[再実行](../runs/duet-telemetry-20261120-repeat/manifest.json)・[再生時計の回帰](../runs/duet-telemetry-transport-regression-20261120/manifest.json)
