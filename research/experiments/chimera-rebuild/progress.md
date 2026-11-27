# 進捗と再開地点

2026-11-21 時点。第0〜第6段階の計画条件を確認しました。第7段階ではビートボックス、体型別の幾何・気道・発声・較正目標、CLIとブラウザの英語・IPA発話・歌唱、実時間の手動発声中の体型切り替え、韓国語の音節化、閉鎖音・鼻音・渡り音・歯茎硬口蓋音・弾き音を含む韓国語歌唱を照合しました。ロシア語デモの全16音節と中国語の診断句「四是吃字人爱」の全6音節を実ブラウザとCLIで照合しました。動物4種では持続音と全コールのCLI比較を行い、ウェッデルアザラシ、アメリカアリゲーター、アフリカゾウは公式デモのPCMを末尾まで照合しました。鳴禽の持続音と停止はWASM・実時間AudioWorkletに接続し、48・96 kHzで照合しました。鳴禽のコール `flute` の開始・途中停止も実時間AudioWorkletとCLIで照合しました。周期コール `trill` も実時間ブラウザで18回の呼気パルスを照合しました。`chirps` の重なったキーも44.1 kHzの実時間ブラウザで照合し、キー順の差が放射とPCMへ伝わる時刻を追いました。96 kHzの `buzz` も実時間ブラウザで初回と定常時の呼気間隔を照合しました。`buzz` から `trill` への切り替えを実時間ブラウザで照合しました。ウェッデルアザラシの持続音と停止も実時間AudioWorkletで48・96 kHzを照合しました。アザラシの `trill` も実時間AudioWorkletの3レートで照合しました。`zap` の切り替えとパルス深さ0も実時間AudioWorkletで確認しました。`whistle` の目標音高と平滑音高が谷を迎える時刻を3レートで照合しました。`chug` の実時間観測も3レートで照合し、ウェッデルアザラシの持続音と全4コールのブラウザ比較を終えました。アメリカアリゲーターは、固定発声と全4コールを実時間ブラウザで照合し、48 kHzの公式デモ全体も確認しました。アフリカゾウは固定発声・経路変更と全3コールを実ブラウザの3レートで照合し、公式デモ全体を再現しました。鳴禽の観測位置・頻度と描画分割を比較しました。操作・提示機能の対応表を作り、手動発声のWeb MIDIを仮想入力で照合しました。固定姿勢とオフライン発話時刻の三次元断面をCLIと照合しました。合成音声と拍マーカーの録画を固定上流と照合しました。実時間の声道断面を2画面幅で照合し、同じ音声時計の三次元断面を含むMP4とWebM（VP9/Opus）を確認しました。デュエットの再生時計を照合しました。声部別テレメトリと歌詞を再生時計に接続しました。声部別の三次元頭部を観測行と照合しました。口元の文字の位置・退場・シーク直後を照合しました。頭部の輪郭の残像とシーク時の消失を照合しました。二声の表情と頭部の回転を照合しました。Web MIDIでは手動発声、鍵盤歌唱、ビートボックスの低音とハム、鳴禽の持続音とコール、ウェッデルアザラシの持続音とコール、アメリカアリゲーターの持続音とBellow、アフリカゾウの持続音と3コールを照合しました。最新の進捗と次の作業は末尾にあります。[実装計画](../../../docs/plans/chimera-research-rebuild-plan.md)

| 対象 | 上流の入口 | 再実装と確認 |
| --- | --- | --- |
| 第0段階の基準取得 | `crates/chimera/tests/airway.rs`、`chimera-cli` の `render` | [基準取得 CLI](tools/upstream_baseline.py)で一様管テスト・母音・IPA・歌唱の4ケースが成功。[実行記録](runs/upstream-20261119-a/manifest.json) |
| 第0段階の入力検査 | `physics.rs`、`TubeSpec`、`AirwayNetwork::check_cfl` | [固定ケース](cases/uniform-tube-rigid.json)を [CLI の `inspect`](crates/vocal-cli/src/main.rs) で読み、CGS の寸法と係数を JSON に出力。別ディレクトリ `/tmp` からも実行済み |
| 第1段階の伝搬と放射 | `AirwayNetwork::step`、`linear_elements`、`transfer_function` | [音響コア](crates/vocal-core/src/airway.rs)を CLI から実行し、[独立計測](tools/measure_uniform_tube.py)が事前の全条件を通過。初回と再実行の CSV・要約はバイト単位で一致。[結果](runs/uniform-tube-20261119-a/summary.json)・[再実行](runs/uniform-tube-20261119-b/manifest.json) |
| 第2段階の壁振動 | `TubeSpec::wall`、`AirwayNetwork::step` の壁更新、`transfer_function` の壁アドミタンス | [登録ケース](cases/uniform-tube-soft-wall.json)を [CLI](crates/vocal-cli/src/main.rs) で実行。上流の時系列11列、独立線形解析、端の圧力収支に照合し、10項目すべて通過。[読解](notes/uniform-tube-soft-wall.md)・[最終計測](runs/soft-wall-20261119-d/summary.json) |
| 第2段階の固定分岐と固定狭窄 | `AirwayNetwork::connect`、`finalize` の節点次数、`step` の二次損失と分岐コンプライアンス | [固定ネットワーク](crates/vocal-core/src/airway/network.rs)を [CLI](crates/vocal-cli/src/network_case.rs) から実行。対称分岐11項目と0.002 cm²の固定狭窄10項目が通過。[読解](notes/static-junction.md)・[対称分岐](runs/symmetric-junction-20261119-b/summary.json)・[固定狭窄](runs/narrow-junction-20261119-b/summary.json) |
| 第2段階の可動断面 | `set_tube_targets`、`begin_block`、`step` の体積源・閉鎖節点 | [面積補間と体積流量](crates/vocal-core/src/airway/network/geometry.rs)をグラフへ接続。密閉管と放射端の開閉をCLIで実行し、各8項目が通過。[読解](notes/moving-area.md)・[密閉管](runs/sealed-cavity-20261119-b/summary.json)・[放射端](runs/moving-aperture-20261119-b/summary.json) |
| 第2段階の固定圧力と定常狭窄 | `add_pressure_node`、`add_port`、`set_tube_targets`、`step` のポートと枝損失 | [気道グラフ](crates/vocal-core/src/airway/network.rs)に固定圧力とポートを接続。平均・最小断面を別々に補間し、上流時系列と独立定常式に照合。1セル9項目と1/4セル10項目が通過。[読解](notes/pressure-port.md)・[1セル](runs/steady-full-20261119-c/summary.json)・[1/4セル](runs/steady-quarter-20261119-a/summary.json) |
| 第2段階の気道グラフの壁振動 | `TubeSpec::wall`、`TubeSpec::radiating`、`AirwayNetwork::step` の壁と放射 | 単管で検証した壁更新をグラフに接続。壁面放射を有効にした固定一様管で、上流・単管・独立収支との8項目を通過。[読解](notes/network-wall.md)・[結果](runs/network-wall-20261119-c/summary.json) |
| 第2段階の加圧下の閉鎖移動と再開口 | `a_realistic_sliding_closure_with_trapped_pressure_releases_without_spikes`、`set_tube_targets`、`step` | [閉鎖軌跡](crates/vocal-cli/src/network_case/constriction.rs)を制御ブロックごとの断面目標に展開。軟壁管に固定圧力を与え、閉鎖の保持・移動・再開口を10項目で照合。[読解](notes/sliding-closure.md)・[結果](runs/sliding-closure-20261119-b/summary.json) |
| 第2段階のシード付き乱流源 | `HumanAirway::update_noise`、`set_noise_sources`、`compute_noise`、`Rng::next` | [帯域雑音と圧力注入](crates/vocal-core/src/airway/network/turbulence.rs)をグラフに接続し、正流・逆流・別シードの各7判定が通過。[読解](notes/turbulence.md)・[正流](runs/turbulence-forward-20261119-b/summary.json)・[逆流](runs/turbulence-reverse-20261119-b/summary.json)・[別シード](runs/turbulence-alternate-seed-20261119-b/summary.json) |
| 第2段階の鼻腔と側枝 | `HumanAirway::new`、`TubeSpec::perimeter`、`TubeSpec::viscous`、`add_cavity` | 62節点の固定グラフで軟口蓋の閉鎖・開放、梨状窩と上顎洞の切離を比較。口端・鼻端・壁面を個別に計測し、3条件で6・6・9項目が通過。[読解](notes/nasal-network.md)・[開放結果](runs/nasal-open-20261119-b/summary.json) |
| 第3段階の声門面積・圧力差・実流量 | `ParametricGlottis::next`、`HumanVoice::render`、`AirwayNetwork::set_port_area` | 圧力で駆動する固定ピッチの声門と時変ポートを接続。肺圧での立ち上がり、声帯開大と閉口による消声を各9項目で検証。[読解](notes/glottal-coupling.md)・[開大](runs/glottal-abduction-20261119-b/summary.json)・[閉鎖](runs/glottal-oral-closure-20261119-c/summary.json) |
| 第3段階の肺ポート補償と呼気 | `HumanAirway::new` の直列抵抗、`HumanVoice::control` と `render` の肺境界 | 低域の圧力補償と、操作・スコアの呼気を肺境界と声門へ接続。補償なし、補償あり、声門結合の3条件で8・9・9項目が通過。[読解](notes/lung-breath.md)・[補償あり](runs/lung-compensated-20261119-b/summary.json)・[声門結合](runs/lung-voiced-20261119-b/summary.json) |
| 第3段階の間引きとPCM出力 | `Decimator::with_taps`、`push`、`HumanVoice::render` の出力段 | FIR、DC除去、リミッターをモノラルf32 WAVに接続。一様管と声門出力を96 kHz→48 kHzで検証し、各12項目が通過。[読解](notes/pcm-output.md)・[一様管](runs/pcm-impulse-20261119-b/summary.json)・[声門](runs/pcm-voiced-20261119-b/summary.json) |
| 第3段階のジッタとシマー | `ParametricGlottis::next` の周期境界、`Rng::gauss` | 周期長と面積振幅の変動を声門に接続。一定差圧でのジッタのみ・シマーのみ、呼気と声道に結合した条件で8・8・10項目が通過。[読解](notes/glottal-cycle.md)・[ジッタ](runs/cycle-jitter-20261119-b/summary.json)・[シマー](runs/cycle-shimmer-20261119-b/summary.json)・[声門結合](runs/cycle-voiced-20261119-b/summary.json) |
| 第3段階のドリフトとビブラート | `ParametricGlottis::next` の32サンプル更新、`Drift::step` | 低速IIR、ビブラート位相、セントからHzへの変換を声門に接続。瞬時F0の独立計算を含め、ドリフトのみ、ビブラートのみ、呼気と声道との結合で8・10・9項目が通過。[読解](notes/glottal-pitch.md)・[ドリフト](runs/pitch-drift-20261119-b/summary.json)・[ビブラート](runs/pitch-vibrato-20261119-b/summary.json)・[声道との結合](runs/pitch-voiced-20261119-b/summary.json) |
| 第3段階のボーカルフライ | `HumanVoice::apply_source`、`ParametricGlottis::next` のF0補間、`shape` | 一定差圧で瞬時F0、周期長、開口時間、第2パルスを固定上流と独立計算に照合。5ケースの55項目が通過。[読解と結果](notes/glottal-fry.md) |
| 第3段階の交互周期 | `HumanVoice::apply_source` の `roughness`、`ParametricGlottis::next` の周期の偶奇 | 位相の折り返しで周期長倍率と面積振幅倍率を切り替える。一定差圧の対照と交互周期、呼気・声道との結合の3ケースで35項目が通過。[読解と結果](notes/glottal-diplophonia.md) |
| 第3段階の写像による周期変動 | ワニの `control`、`ParametricGlottis::next` の `chaos_x` | 一定差圧の固定点、周期2、周期4、非周期と、呼気・声道との結合を照合。位相から逆算した状態を含む5ケース57項目が通過。[読解と結果](notes/glottal-chaos.md) |
| 第4段階の矢状面輪郭 | `HumanVocalTract::new`・`compute`、`geom.rs` の補間 | 成人男性の中立姿勢と顎を開いた姿勢の15部位・305点を、それぞれ固定上流と照合。下顎の回転、舌の円弧と接線、輪郭の接続を含む全20項目が通過。[読解と結果](notes/sagittal-geometry.md) |
| 第4段階の半極座標格子 | `HumanVocalTract::compute` の測定格子、`geom.rs` の折れ線交差 | 咽頭・口腔・歯と唇の測定点と隙間を、5姿勢で各49本照合。逆向きの探索、途中の舌、隙間0、下唇の端より前の測定を含む全50項目が通過。[読解と結果](notes/semipolar-grid.md) |
| 第4段階の接触による隙間の補正 | `HumanVocalTract::compute` の接触処理、`project_on`、`signed_gap` | 測定点を保ったまま舌と口蓋、上下の唇の補正を順に適用。補正後の隙間、舌先・舌体の符号付き距離と法線を固定6姿勢で照合し、全84項目が通過。[読解と結果](notes/soft-tissue-contact.md) |
| 第4段階の断面積と中心線 | `HumanVocalTract::compute` の領域別面積、孤立ピークの抑制、`s` | 隙間を格子上の面積へ換算し、舌側面開口と声道の距離を求める。閉鎖と唇の横幅を含む固定6姿勢で全90項目が通過。[読解と結果](notes/area-profile.md) |
| 第4段階の咽頭・口腔セルへの割り当て | `HumanVocalTract::resample`、`epilarynx_area` | 声門上の断面を接続し、咽頭と口腔の等長セルへ8点の調和平均と最小断面を出力。元の格子点だけで検出できる閉鎖を含め、成人男性の固定7条件で全147項目が通過。[読解と結果](notes/resampled-tract.md) |
| 第4段階の固定姿勢の気道接続 | `HumanAirway::{new,apply,commit}`、`AirwayNetwork::snap_to_targets` | 面積・最小断面を気管、気道本管、鼻腔と側枝のグラフに接続。クーラン数による音響計算用の管長の下限、節点断面、圧力・流量と放射を5条件で照合し、全95項目が通過。[読解と結果](notes/fixed-human-airway.md) |
| 第4段階の固定母音の線形伝達関数 | 較正コマンドの `formants`、`AirwayNetwork::linear_elements`、`transfer_function` | 成人男性の較正済み `/i ɑ u/` と軟口蓋を開いた対照で、線形要素、総放射と口端・鼻端・壁の複素応答、共鳴ピークを照合。4条件・全64項目が通過。[読解と結果](notes/vowel-transfer.md) |
| 第4段階の固定母音の発声 | `HumanVoice::{control,render}`、`yin_pitch`、`estimate_formants` | 固定の `/i ɑ u/` と呼気ゲート0を通常のPCM出力へ接続。上流のPCM、呼気・声門・放射の系列、独立のF0・LPCを照合した。ナイキスト境界の根を記録し、第2版の4ケースで64項目が通過。[読解と結果](notes/fixed-vowel-voice.md) |
| 第4段階の調音器の時間更新 | `ArticulatorBank::{set_target,step}`、`rest_tip` | 全17成分の位置・速度・目標を計算。較正母音の切り替え、舌先の追従、速度倍率、軟口蓋の合成を照合し、4条件で32項目が通過。[読解と結果](notes/articulator-dynamics.md) |
| 第4段階の可動声道の断面目標 | `HumanVoice::{control,enforce_contacts}`、`HumanAirway::{apply,reapply,commit}` | 咽頭・口腔の平均断面と最小断面に変化率制限を適用し、舌先の補正後も同じフレームの開始時点を基準に再計算。母音遷移、唇の閉鎖・再開口、舌先接触と対照の4条件で37項目が通過。[読解と結果](notes/tract-area-control.md) |
| 第4段階の可動声道の音響更新 | `AirwayNetwork::{set_tube_targets,set_port_target,begin_block,step}` | 接触補正後に確定した目標からセル断面、セル長、軟口蓋ポートを補間。形状だけで駆動した唇・母音・舌先接触の3条件で全39項目が通過。[読解と結果](notes/moving-human-tract.md) |
| 第4段階の母音遷移の有声PCM | `HumanVoice::{control,render}`、`ParametricGlottis::next`、`Decimator::push` | 調音と呼気を同じ内部制御周期で更新。通常発声、軟口蓋の一時開放、呼気ゲート0の3ケースで、固定上流の内部系列とPCM、独立した出力段、F0・LPCを照合し、全67項目が通過。[読解と結果](notes/voiced-vowel-motion.md) |
| 第4段階の基準10母音と隣接遷移 | `render::vowels`、`calibrate::formants`、`yin_pitch`、`estimate_formants`、`HumanVocalTract::resample` | 全10母音の線形応答・固定発声、隣接9遷移、セル境界の最小断面を照合。/ɔ/ の高域帯域幅2点を欠測として保存し、/ʌ/ → /ɝ/ で最小断面に残る段差の位置を特定した。[読解と結果](notes/ten-vowel-benchmark.md) |
| 第5段階のIPA字句解析 | `phonetics::ipa::{tokenize_ipa,skipped_ipa}`、`render::speech` | 基準VCV、別表記、修飾、境界、未知記号をRustのCLIで出力。登録15入力と記号・修飾の組み合わせ1,296入力が固定上流と一致。原文UTF-8バイト範囲を追加。[読解と結果](notes/ipa-tokenization.md) |
| 第5段階の発話区間 | `phonetics::durations::klatt_durations`、`phonetics::planner::plan_utterance` | [区間の実装](crates/vocal-core/src/phonetics/timing.rs)をCLIに接続。登録15入力と目録131記号の655条件で、長さ・分類・開始と終了の時刻が固定上流版に一致。[読解と結果](notes/speech-timing.md) |
| 第5段階の母音ジェスチャーと合成 | `plan_utterance`、`GestureScore::blend_all`、`ArticulatorBank::step` | 成人男性の目標26件、発話と合成の8条件を照合。制御8,000フレームで活性、合成目標と重み、調音器の状態が一致。[読解と結果](notes/vowel-gesture-score.md) |
| 第5段階の両唇破裂音 | `plan_utterance`、`oral_gestures_into`、`HumanVoice::{control,render}` | `ɑpɑ`、`ɑbɑ`、無気の /p/、1.8倍速の4条件で、計画から声道・声門・PCMまで照合。閉鎖・再開口と開放後5 msのPCMピークのフレームが一致。[読解と結果](notes/bilabial-stop.md) |
| 第5段階の歯茎摩擦音 | `plan_utterance`、`HumanAirway::update_noise`、`AirwayNetwork::compute_noise` | `ˈɑsɑ`・`ˈɑzɑ`・乱流倍率0の3条件。調音・声門・励起枝と注入先・圧力注入・波形まで照合。歯の帯域と利得を独立計算で確認。[読解と結果](notes/sibilant-frication.md) |
| 第5段階の両唇鼻音と基準5発話 | `plan_utterance`、`nasal_closure_delay`、`ArticulatorBank::step` | `ɑmɑ`、後続 `/b p/`、発話末、基準5発話を照合。軟口蓋ポート、口端・鼻端の流量、計画と波形を比較。[読解と結果](notes/bilabial-nasal.md) |
| 第5段階の英語発音と句計画 | `render::say`、`EnglishG2P::to_phrases`、`arpabet_to_segments`、`plan_phrases` | 辞書126,052語。TypeScript参照504語・9件のARPAbet・38文と固定Rust版の区間・F0を照合。`Mom? Pop.` を音声へつなぎ、調音とPCMを比較。[読解と結果](notes/english-frontend.md) |
| 第5段階の歯茎破裂音 | `stop_closure_delay`、`pre_placed_behind_closure`、`oral_gestures_into` | /d t/ の舌先・舌体目標、1.8倍速、先行する舌先調音と英語 `Dad.` を照合。各口腔セルの最小断面をCSVへ追加。[読解と結果](notes/alveolar-stop.md) |
| 第5段階の声門摩擦音 | `plan_utterance`、`HumanAirway::update_noise`、`AirwayNetwork::compute_noise` | /h ɦ/ の開大と圧力注入を照合。乱流倍率0、内部48 kHzの独立計算、英語 `Hi.` の5条件。[読解と結果](notes/glottal-frication.md) |
| 第5段階の両唇軟口蓋接近音 | `oral_gestures_into`、`ArticulatorBank::step`、`HumanVocalTract::compute` | /w/ の同時5目標と実測断面、唇3軸の独立計算、隣接母音のLPCを確認。等速、1.8倍速、英語 `We.`、句末の4条件。[読解と結果](notes/labial-velar-approximant.md) |
| 第5段階の側音と英語文 | `oral_gestures_into`、`HumanVocalTract::compute`、`render::say` | /l ɫ/ の側方開き、2つの閉鎖対照、口蓋化、`Hello world` の6条件を確認。音素・IPA表示・計画・断面・流量・WAVを照合。[読解と結果](notes/lateral-approximants.md) |
| 第5段階の歌詞と音符の計画 | `lyrics_to_syllables`、`split_spelling`、`plan_song` | 英語歌詞、音節、MIDI番号、拍、頭子音・母音・末子音の区間、F0目標を照合。等速・高速、メリスマ、句境界、上昇グライドなど9譜例。[読解と結果](notes/song-timing.md) |
| 第5段階の歌唱の呼気・開大・PCM | `render::song`、`plan_song`、`plan_utterance` の `sung` と `let_go`、`HumanVoice::control` | `song_voice` の通常CLIで歌詞・拍からPCMを出力。長音、深さ0、高速、破裂音末尾を7項目ずつで照合。[読解と結果](notes/sung-voice.md) |
| 第6段階の固定姿勢WASM | `Engine::render`、`engine_new`、`engine_render`、Workletのバッファ受け渡し | C ABIを実装。固定 /i/ のPCM32,768フレームがCLI・WASM・固定上流でビット一致。各分割の135時点で声門・呼気・放射を照合。[読解と結果](notes/wasm-fixed-voice.md) |
| 第6段階の固定姿勢AudioWorklet | `AudioEngine.build`、`ChimeraProcessor.process`、上流E2Eの起動再試行 | Chromiumのオフライン出力をCLI・固定上流と照合。128フレーム×256ブロック、PCMのビットと声門など7系列の観測時刻、画面での再試行と保存を確認。[読解と結果](notes/worklet-fixed-voice.md) |
| 第6段階の実時間での固定発声 | `AudioEngine.start`・`watchLoad`、`HumanVoice::set_gate` | 48 kHzの開始・停止と減衰を採取。実測フレームで再生したCLIとビット一致し、予算とContext時計を検査。[読解と計測](notes/worklet-realtime-voice.md) |
| 第6段階のブラウザIPA発話 | `planUtterance`、`writeGestures`、`engine_schedule` | ブラウザで `ɑpɑ` を入力し、計画、PCM49,828フレーム、閉鎖・開口、観測3,115点をCLIと比較。未対応音素からの回復も確認。[読解と結果](notes/worklet-ipa-voice.md) |
| 第6段階のブラウザ英語歌唱 | `playTune`、`fetchGzText`、`planSong`、`plan_song` | ブラウザの歌詞・MIDI入力からPCM91,200フレームと内部状態1,425点をCLIに照合。辞書の2配信条件と未対応音素からの再試行を確認。[読解と結果](notes/worklet-song-voice.md) |
| 第6段階の舌・唇の実時間操作 | `AnatomyView.onMove`、`AudioEngine.setArtic`、`engine_set_artic`、`ArticulatorBank::step` | 3つの目標の適用フレーム、追従座標、断面・声門・呼気の観測を保存。各実行の時刻をCLI・固定上流に再入力して比較。[読解と結果](notes/worklet-manual-articulation.md) |
| 第6段階のIPA発話の時系列 | `SpeakPanel`、`ScoreView.planNow`、`humanTelemetry` | `ɑpɑ` の計画音素・口唇の最小断面積・PCMを共通の横軸に表示。固定上流の計画と保存データから図形を照合し、2画面幅でクリックとキー操作を確認。[読解と検証](notes/worklet-ipa-timeline.md) |
| 第6段階の再実行ケースの書き出し | `Engine::render`、`engine.rs` の時刻付き操作、候補CLIの `articulators.events` | 手動調音の画面からダウンロードしたケースを直接CLIに入力。制御時計、PCMと内部状態、同一フレームの呼気と調音の結合を照合。[読解と検証](notes/worklet-manual-case-export.md) |
| 第6段階のブラウザ英語発話 | `speakText`、`EnglishG2P`、`plan_phrases` | `Mom? Pop.` を英語画面から発声し、辞書、句の計画、鼻端流量・軟口蓋とPCMを照合。未対応音素からの再試行を確認。[読解と検証](notes/worklet-english-voice.md) |
| 第6段階の声道断面と時系列の同期 | `TubeView`、`HumanVoice::telemetry`、`AirwayNetwork::step` | 発話の選択時刻に対応した咽頭・口腔の実測断面を表示。65時点で全36セルをCLIと固定上流に照合し、2画面幅の図を独立計算で検証。[読解と検証](notes/worklet-tract-profile.md) |
| 第6段階の声道圧力と流量 | `HumanVoice::render`、`AirwayNetwork::{step,linear_elements}` | 断面と同じ時刻の節点圧力と口側境界の流量を表示。CLI・固定上流に照合し、閉鎖中の枝の停止と放射負荷の減衰を独立式で確認。[読解と検証](notes/worklet-tract-acoustics.md) |
| 第6段階の声門波形と時系列の同期 | `Stroboscope`、`HumanVoice::{render,telemetry}`、`ParametricGlottis::next` | 選択の前後12 msに面積と流量を実時刻で表示。49,828フレームの出力をCLI・固定上流と照合し、母音の周期と /p/ の閉鎖中の逆流を確認。[読解と検証](notes/worklet-glottal-scope.md) |
| 第6段階のPCMスペクトルと時系列の同期 | `SpectrumView`、`AudioEngine` の分析ノード、`Fft::transform` | 保存WAVと同じPCMから各選択窓の絶対dBFSスペクトルを表示し、全ビンをJSONに保存。2画面幅でCLI・上流・独立FFT・描画を照合。[読解と検証](notes/worklet-pcm-spectrum.md) |
| 第6段階の実時間IPA発話 | `speakPhrases`、`engine_schedule`、`Engine::{schedule,render}` | 描画量子の境界に `ɑpɑ` を配置。実時間・オフライン・CLIでPCMが一致し、量子番号、停止操作、処理予算、割り当てを検査。[読解と検証](notes/worklet-live-ipa.md) |
| 第6段階の声道走査の割り当て削減 | `HumanVocalTract::compute` の `fan_inner`、`ray_crossings` | 扇状走査線の交差の一時配列を固定長に変更。発話のPCM・内部観測とCLIの断面時系列は基準版に一致し、割り当ては48.81%削減。登録した60%は未達。[読解と判定](notes/fan-crossing-allocations.md) |
| 第6段階の矢状面輪郭の領域再利用 | `HumanAirway::commit`、`HumanFrame::with_capacity`、`HumanVocalTract::compute` | 制御器で輪郭フレームを保持し、舌・唇・軟口蓋の補間点を固定長配列にした。輪郭計算は1回あたり22件から0件。発話全体は走査線改修前から86.35%削減し、PCMと内部観測が一致した。[読解と判定](notes/contour-buffer-reuse.md) |
| 第6段階の実時間歌唱 | `playTune`、`AudioEngine.schedule`、`Engine::schedule` | 歌唱のスコアを実時間の量子境界に予約。二音のPCM 91,200フレームと1,425観測点がCLI・オフラインと一致。歌唱中の停止・再開、713量子と拍の時刻を確認。[読解と検証](notes/worklet-live-song.md) |
| 第6段階の測定線の領域再利用 | `HumanVocalTract::compute` の `f.grid`、研究版の `measurement_grid_into()` | 最大49本の測定線を初期確保し、48 kHz歌唱の描画中に測定線の割り当てを1,476回からゼロにした。PCM・ABI観測・4条件の断面が基準版に一致した。[読解と検証](notes/contact-measurement-grid-reuse.md) |
| 第6段階の接触標本の領域再利用 | `HumanVocalTract::compute` の接触補正、研究版の `contact_grid_into()` と `area_profile_from_contacts()` | 48 kHz歌唱の描画中に接触標本の割り当てを1,476回からゼロにした。全区間のPCM・ABI観測・4条件の断面が基準版に一致し、平行壁の断面を手計算に照合した。[読解と検証](notes/contact-sample-buffer-reuse.md) |
| 第6段階の断面標本の領域再利用 | `HumanVocalTract::{compute,resample}`、研究版の `area_profile_from_contacts_reusing()` | 48 kHz歌唱で断面生成の割り当てを1,476回からゼロにした。再標本化に失敗したときの確定済み断面と、次の成功時の領域再利用を確認した。[読解と検証](notes/tract-area-buffer-reuse.md) |
| 第6段階の乱流源の初期確保 | `HumanAirway::update_noise`、`AirwayNetwork::set_noise_sources`、研究版の `reserve_noise_sources()` | 48 kHz歌唱の全713量子で描画中の割り当てがゼロになった。3件の乱流源を使う試験でフィルタ状態と注入圧を確保なしの対照に照合した。[読解と検証](notes/human-noise-source-reserve.md) |
| 第6段階の44.1 kHz英語発話の割り当て | `plan_phrases`、`Engine::{schedule,render}`、研究版の `vocal_start_score_prepared()` | 確認用07で英語計画3,555回、スコア開始118回、全772描画量子でゼロ。通常のWorkletとCLIに全PCMと内部観測を照合した。[読解と検証](notes/worklet-live-tsp-allocation-44100.md) |
| 第6段階の英語計画ABIの工程別計数 | `EnglishG2P::{load_dict,to_phrases}`、`plan_phrases`、研究版の `PlanBuffers::store()` | 確認用07の初回3,555回と再計画2,010回を六工程に照合。1,544回の差はコア発音と句の計画にあり、JSON関連は各1,822回。計画・数値スコア・PCMと観測を照合した。[読解と検証](notes/worklet-live-tsp-planner-allocation-44100.md) |
| 第6段階の計画報告の直接シリアライズ | 上流の `planPhrases` とWASMの結果バッファ、研究版の `PlanBuffers::store()` | 確認用07の初回3,555回から2,269回、再計画2,010回から724回に減少。報告JSON・数値スコア・PCMをバイト照合し、英語発話と歌唱を通常経路で再生した。[読解と検証](notes/worklet-live-tsp-planner-direct-report-44100.md) |
| 第6段階の44.1 kHz固定発声 | `AudioEngine.build`、`engine_new`、`oversample_for`、`Decimator::push` | 44.1 kHz出力と88.2 kHz内部で固定 /i/ を実行。ブラウザの83,072フレームと649観測点をCLIと照合し、間引き係数、呼気の時定数と描画中のメモリを確認。[読解と検証](notes/worklet-realtime-voice-44100.md) |
| 第6段階の32 kHz固定発声 | `oversample_for`、`HumanAirway::new`、`check_cfl` | 32 kHz出力・内部64 kHz。咽頭・口腔は各12セルで、鼻腔のクーラン数0.91146が最大。ブラウザの60,416フレームと472観測点はCLIに一致した。[読解と検証](notes/worklet-realtime-voice-32000.md) |
| 第6段階の16 kHz固定発声 | `oversample_for`、`HumanVoice::render`、`Decimator::push` | 内部64 kHzで4倍・97タップの間引き。32 kHzと気道が一致し、共通時刻のゲート差は最大 `3.33×10⁻¹⁶`。ブラウザの30,208フレームはCLI・固定上流とビット一致した。[読解と検証](notes/worklet-realtime-voice-16000.md) |
| 第6段階の96 kHz固定発声 | `oversample_for`、`HumanVoice::render`、`Decimator::with_taps` | 出力・内部ともに96 kHzで倍率1。全181,248フレームで放射と間引き後が一致し、DC除去からPCMを独立計算で再現。ブラウザPCMもCLIとビット一致した。[読解と検証](notes/worklet-realtime-voice-96000.md) |
| 第7段階の単発キック `B` | `render::beatbox`、`beat_ready`、`BeatPlayer::gestures`、`kick`、`ejective` | 成人男性の単発レンダーをCLIへ接続し、4ジェスチャー、閉鎖と再開口、声門上の加圧、音のピークと減衰を照合。第2版の13項目が通過。[読解と検証](notes/beatbox-kick-b.md) |
| 第7段階の休符とスウィング | `Engine::sub_block_start`、`parse_beat`、`BeatPlayer::{start,step_time,tick,step_at}` | 固定テンポのパターンを音源描画中に予約。休符を含む再生位置、各打音の予約とジェスチャー、圧力とPCM、128・77フレームのホスト幅を12項目で照合。[読解と結果](notes/beatbox-pattern-swing.md) |
| 第7段階の単発ハイハット `t` | `hat`、`blow`、`oral_gestures_into`、`HumanAirway::update_noise` | 歯茎の閉鎖、摩擦の狭窄、呼気、声門開大を7ジェスチャーで接続。再開口後の乱流とPCM、無振動、波形末尾の減衰を13項目で照合。[読解と結果](notes/beatbox-hat-t.md) |
| 第7段階のキックとハイハットの混在パターン | `parse_beat`、`BeatPlayer::{tick,gestures}`、`GestureScore::blend_all` | 音色IDとアクセントを保持し、同じ声道への逐次予約に接続。近接した打音の喉頭、声門、呼気、乱流、PCMと再生位置を15項目で照合。[読解と結果](notes/beatbox-pattern-mixed-kit.md) |
| 第7段階の開ハイハット `tss` | `open_hat`、`BeatPlayer::{tick,gestures}`、`blow` | 休符から得る長さを音色へ渡し、摩擦と呼気終端の比例区間と上下限を照合。単発13項目、短いパターンと長いパターンの各16項目が通過。[読解と結果](notes/beatbox-open-hat.md) |
| 第7段階の唇歯スネア `Pf` | `snare`、`oral_gestures_into`、`blow`、`HumanAirway::update_noise` | 両唇閉鎖、呼気による圧力上昇、開口後の破裂と唇歯摩擦を接続。単発とアクセント付きパターンで各14項目を照合。[読解と結果](notes/beatbox-snare-pf.md) |
| 第7段階のリムショット `K` | `rimshot`、`ejective`、`HumanVoice::apply_source`、`ParametricGlottis::next` | 奥舌閉鎖、喉頭上昇による加圧、再開口後の放出を接続。上流と声門の揺らぎをそろえ、単発13項目、アクセント付きパターン15項目が通過。[読解と結果](notes/beatbox-rimshot-k.md) |
| 第7段階の吸気スネア `^K` | `inward_snare`、`oral_gestures_into`、`HumanVoice::control`、`AirwayNetwork::compute_noise` | 奥舌閉鎖から、負の肺圧による吸い込みと /x/ の摩擦へ接続。単発13項目とアクセント付きパターン16項目で瞬時の狭窄枝流量、前後の乱流圧、PCMを照合。[読解と結果](notes/beatbox-inward-snare.md) |
| 第7段階の舌打ち音 `!` | `tongue_click`、`HumanVocalTract::compute`、`ArticulatorBank::step`、`AirwayNetwork::step` | 舌先と奥舌の二重閉鎖、舌背下降、開口後の吸い込みを接続。単発13項目とアクセント付きパターン16項目で、閉鎖の間の体積・圧力、解除順、PCMを照合。[読解と結果](notes/beatbox-tongue-click.md) |
| 第7段階の唇を使う打音 `P!` | `lip_pop`、`oral_gestures_into`、`ArticulatorBank::step`、`AirwayNetwork::step` | 唇と奥舌の二重閉鎖、顎と舌背の下降、開唇時の流入を接続。単発13項目とパターン16項目で、口腔の体積・圧力、閉鎖中の口端放射の減衰、PCMを照合。[読解と結果](notes/beatbox-lip-pop.md) |
| 第7段階のクラッシュ `kch` | `crash`、`phoneme`、`oral_gestures_into`、`HumanAirway::update_noise` | 奥舌の破裂から丸めた摩擦へ接続。単発13項目とパターン各15項目で、狭窄乱流の位置、成人男性の較正値、摩擦時間の上下限、PCMを照合。[読解と結果](notes/beatbox-crash.md) |
| 第7段階の鼻音の打音 `m` | `hum`、`BeatPlayer::gestures`、`HumanVoice::control`、`HumanAirway::commit` | 閉唇、鼻端放射、有声のMIDI音高、休符込みの保持と下限を接続。単発15項目とパターン16項目を照合。[読解と結果](notes/beatbox-hum.md) |
| 第7段階のテンポ変更と停止・再開 | `BeatPlayer::{set_tempo,start,stop,step_at}`、`Engine::set_beat_playing`、`HumanVoice::cancel_score` | 操作を絶対出力フレームに指定。テンポ変更の支点、停止で消去した予約、残留する呼気とPCM、再開時の再生位置を18項目で照合。[読解と結果](notes/beatbox-transport.md) |
| 第7段階のAudioWorkletでの固定パターン | `AudioEngine::setBeat`、Workletの `beat`、`engine_set_beat`、`engine_beat_step` | 固定パターンをRustで予約し、画面からWAV・観測JSONを保存。2つの観測間隔で加工前PCM、休符を含む再生位置、MIDI 43・47のF0を17項目で照合。[読解と結果](notes/worklet-beatbox-pattern.md) |
| 第7段階の実時間ビート操作 | `setBeatTempo`、`setBeatPlaying`、Workletの `beat`、`Engine::set_beat_playing` | BPM・スウィング変更、停止と再開を出力フレームで記録。保存したケースでPCMと休符を含む再生位置を照合し、描画量子の連続性と処理時間も確認。[読解と結果](notes/worklet-live-beatbox.md) |
| 第7段階の体型補間と矢状面 | `BodyMix::{weights,blend,body}`、`HumanVocalTract::{new,compute,resample}` | 3端点と混合・丸めの8条件、中立と開放の2姿勢で重み、既定F0、輪郭、接触補正済みの断面、等長セルを130項目で照合。[読解と結果](notes/human-body-geometry.md) |
| 第7段階の体型別の固定気道 | `HumanAirway::{new,apply,commit}`、`calibrate::formants` | 気管・咽頭・口腔・鼻腔と側枝を体型ごとの断面・セル数で構成。固定姿勢の伝達関数、圧力・流量のインパルス応答、子どもの64 kHzでの安定性を7条件・100項目で照合。[読解と結果](notes/human-body-airway.md) |
| 第7段階の体型別の固定発声 | `Engine::default_f0`、`HumanVoice::{apply_source,control,render}`、`tests/body_source.rs` | 3端点・3体型の混合・同じ音高の比較・64 kHz直結で声門と肺境界を照合。CLIの固定姿勢ケースで既定音高と指定音高を使い、6条件・60項目を確認。[読解と結果](notes/human-body-fixed-voice.md) |
| 第7段階の体型別の較正済み母音目標 | `vowel_artic`、`ArticPatch::blend`、`calibrate::vowels`、`tests/body_mix.rs` | 3端点と混合2条件で26母音の部分目標を照合。固定 /a/ のセル・線形応答・発声を5体型、計458項目で確認。[読解と結果](notes/human-body-calibrated-vowels.md) |
| 第7段階の体型別の可動声道 | `HumanAirway::{apply,commit,reapply}`、`HumanVoice::enforce_contacts`、`AirwayNetwork::{begin_block,step}` | 体型別の断面制限・接触補正・内部補間を /i a u/ と子どもの接触ケースで照合。5条件70項目、有声PCMは4条件で確認。[読解と結果](notes/human-body-tract-motion.md) |
| 第7段階の体型別IPA発話 | `inventory::phoneme`、`planner::plan_utterance`、`HumanAirway::update_noise` | /ɑpɑ ɑsɑ ɑzɑ/ の母音と子音目標、両唇閉鎖、歯への乱流、PCMを3端点と混合の4条件46項目で照合。[読解と結果](notes/human-body-ipa.md) |
| 第7段階の体型別歌唱 | `sing::plan_song`、`SongOptions::body`、`HumanVoice::control` | MIDI 57・60・64と /pɑ sɑ zɑ/ の拍・頭子音・音高移行、閉鎖・乱流・PCMを4体型41項目で照合。[読解と結果](notes/human-body-song.md) |
| 第7段階の体型別英語発話 | `render::{text_f0,say}`、`EnglishG2P::to_phrases`、`planner::plan_phrases` | 同じ英語3句を3端点と混合体型で発話。混合体型の180 Hz指定を含む5条件で発音、語境界、句末の抑揚、閉鎖、鼻端流量とPCMの70項目を照合。[読解と結果](notes/human-body-english.md) |
| 第7段階のブラウザの体型別英語発話 | `speakPhrases`、`engine_set_body`、`Engine::make_voice` | 3端点、混合、混合の180 Hz指定でユーザー操作から発声し、ダウンロードしたケースをCLIで再実行。計画・PCM・3,711点の内部状態を照合。初回通過と再実行で各86項目を確認。[読解と結果](notes/worklet-english-body.md) |
| 第7段階のブラウザの体型別IPA発話 | `ipaToPhrases`、`speakPhrases`、`HumanAirway::update_noise` | 4体型のオフライン・実時間でケースを保存。加工前PCMと内部状態をCLIに照合し、/p/ の開閉と /s z/ の歯への注入を観測。初回と再実行で各136項目を確認。[読解と結果](notes/worklet-ipa-body.md) |
| 第7段階のブラウザの体型別歌唱 | `playTune`、`SongOptions::body`、`sing::plan_song` | 同じMIDIとIPA音節を4体型でオフライン・実時間に歌唱。保存ケースのCLIと加工前PCM・音響を照合し、頭子音中のF0移行、唇の開閉、語尾、停止と再開を検証。修正後と再実行で各112項目を確認。[読解と結果](notes/worklet-song-body.md) |
| 第7段階の手動発声中の体型切り替え | `setBody`、`engine_set_body`、`Engine::set_body` | 成人男性から成人女性への切り替えでセル数が18・18から15・16に変わり、唇と呼気の目標を引き継いでF0が205 Hzへ接近した。保存ケースを再生したCLIとPCM・内部状態が一致し、修正後と再実行で各12項目を確認。[読解と結果](notes/worklet-manual-body-switch.md) |
| 第7段階の韓国語歌詞 | `sung_lyrics`、`read_lyrics`、`korean::word_syllables`、`plan_song` | 完成形と字母の34入力で音節の綴り、頭・核・末子音、境界が上流と一致。両唇閉鎖音の3音をCLIとブラウザで歌唱し、録音したPCMと実時間から保存したケースを照合。初回通過と再実行で各40項目を確認。[読解と結果](notes/korean-lyrics.md) |
| 第7段階の舌背閉鎖 /k g/ | `phoneme`、`stop_closure_delay`、`oral_gestures_into`、`plan_song` | 発話7条件と韓国語歌唱2条件で目標、舌背位置、声道の閉鎖・開口、PCMを照合。歌詞の空白で /g/ が2音目の頭、/k/ が1音目の末尾に移ることを確認。実時間の保存ケースの再演を含め88項目を2回通過。[読解と結果](notes/velar-stops.md) |
| 第7段階の舌先・舌背の鼻音 /n ŋ/ | `nasal_closure_delay`、`oral_gestures_into`、`plan_utterance`、`plan_song` | 成人男性・成人女性を含む発話5条件と `국물`・`국 물` の歌唱を照合。/ŋ/ の閉鎖セル両側の枝流量は全観測点で0。鼻端流量を含む実時間観測と保存ケースの再演を含め80項目を2回通過。[読解と結果](notes/lingual-nasals.md) |
| 第7段階の舌背の渡り音 /j ɰ/ | `word_syllables`、`plan_song`、`oral_gestures_into` | 成人男性・成人女性を含む発話5条件と `빵야 ~`・`의사` の歌唱を照合。短時間LPC、顎の独立計算、音素と拍の関係、実時間の舌背位置と保存ケースの再演を含め69項目を2回通過。[読解と結果](notes/tongue-glides.md) |
| 第7段階の歯茎硬口蓋摩擦音 /ɕ ʑ/ | `inventory::phoneme`、`oral_gestures_into`、`HumanAirway::update_noise` | 発話6条件と「시야」で、体型の補間、声門開大、狭窄、歯への圧力注入とPCMを照合。乱流係数0の対照、実時間演奏からの保存と再演を含め各65項目を2回通過。[読解と結果](notes/alveolopalatal-fricatives.md) |
| 第7段階の歯茎硬口蓋破擦音 /tɕ dʑ/ | `inventory::phoneme`、`Manner::Affricate`、`affricate_folds`、`korean::onset_ipa` | 発話4条件と「아주 자 차 짜」の歌唱で、閉鎖の各枝流量、開口後の乱流、周期復帰を照合。帯気指定、短い音素、実時間の保存ケースの再演を含む42項目を2回通過。[読解と結果](notes/alveolopalatal-affricates.md) |
| 第7段階の歯茎弾き音 /ɾ/ | `Manner::Tap`、`oral_gestures_into`、`korean::onset_ipa` | 話速・母音・口蓋化を変えた発話8条件と「싫어」を照合。通常の /ɑɾɑ/ の0.188 msの閉鎖を声門の一周期がまたいだ。話速1.8の反証を保存し、第2版で全84項目を2回通過。[読解と結果](notes/alveolar-tap.md) |
| 第7段階のロシア語歌詞 | `Russian::word_after`、`word_before`、`lyrics_to_syllables_with` | 23入力・81音節の強勢・軟音・表示綴り・境界と、2譜例を上流に照合。ブラウザと保存ケースの再演を含め各75項目を2回通過。この実行時点のデモの未対応 /tʃ v x/ は、後続の16音節の全曲比較で解消した。[読解と結果](notes/russian-lyrics.md)・[デモ全体の比較](notes/postalveolar-affricate.md#実測) |
| 第7段階の唇歯摩擦音 /f v/ | `phoneme`、`oral_gestures_into`、`HumanVocalTract::compute`、`HumanAirway::update_noise` | 8発話と「ве́тер」で下唇端、口腔狭窄、音源の位置、乱流倍率0、声門開大を照合。112 Hz開始時の差を修正し、第2版の116項目を2回通過。[読解と結果](notes/labiodental-fricatives.md) |
| 第7段階の軟口蓋摩擦音 /x/ | `inventory::phoneme`、`oral_gestures_into`、`HumanAirway::update_noise` | 発話7条件と「ти́хо」で舌背位置、最小断面、音源登録、PCMを照合。狭窄乱流が出なかった理由を独立計算し、第2版の93項目を2回通過。[読解と結果](notes/velar-fricative.md) |
| 第7段階の後部歯茎破擦音 /tʃ/ とロシア語デモ | `plan_utterance`、`oral_gestures_into`、`affricate_folds`、`plan_song` | 発話5条件の閉鎖・解放・乱流・PCMを照合。ロシア語デモの全16音節・2句を上流と実ブラウザに照合し、58項目を2回通過。[読解と結果](notes/postalveolar-affricate.md) |
| 第7段階の中国語歌詞・基本歌唱 | `lyrics_to_syllables_with`、`MandarinLexicon`、`pinyin_syllable`、`plan_song` | 20入力・106音節と11入力の変調後の読みを上流と照合。漢字とピンインの同譜、声門開大、下降滑音、実時間ブラウザとCLIの再演を確認。[読解と結果](notes/mandarin-lyrics.md) |
| 第7段階の中国語の鼻音韻尾 | `plan_song`、`coda_approach`、`closure`、`HumanVoice::control` | 9譜例で母音中の先行鼻音化、舌体の移動、句末保持、16 kHzを照合。3譜例の閉鎖セルに隣接する枝流量は全152フレームで0。[読解と実測](notes/mandarin-nasal-rhymes.md) |
| 第7段階の歯茎破擦音 /ts/ | `inventory::phoneme`、`pinyin_syllable`、`Manner::Affricate`、`oral_gestures_into` | 発話4条件と中国語歌唱3譜例。主目標と舌体補助目標、閉鎖、歯の乱流、無気・有気の周期復帰を照合。「资 词」の実ブラウザと保存ケース再演を含めて69項目を2回通過。[読解と実測](notes/alveolar-affricate.md) |
| 第7段階のそり舌摩擦音 /ʂ/ | `inventory::phoneme`、`oral_gestures_into`、`HumanVocalTract::compute`、`HumanAirway::update_noise` | 発話4条件と「四 是」の歌唱で舌先の反り、狭窄、乱流、舌尖母音の周期性を照合。実ブラウザと保存ケース再演を含め61項目を2回通過。[読解と実測](notes/retroflex-fricative.md) |
| 第7段階のそり舌破擦音 /tʂ/ | `inventory::phoneme`、`Manner::Affricate`、`affricate_folds`、`mandarin::initial` | 発話4条件と歌唱5譜例で閉鎖と狭窄、等長の帯気対照、周期復帰を照合。「知 吃」の実ブラウザと保存ケース再演を含め105項目を2回通過。[読解と実測](notes/retroflex-affricate.md) |
| 第7段階のそり舌接近音 /ɻ/ | `inventory::phoneme`、`oral_gestures_into`、`mandarin::rhotacize`、`plan_song` | 発話4条件と歌唱4譜例で反りの独立積分、児化韻尾の時刻と周期、メリスマを照合。2譜例の実ブラウザと保存ケース再演を含め104項目を2回通過。[読解と実測](notes/retroflex-approximant.md) |
| 第7段階の声門閉鎖音 /ʔ/ | `Glottal::Stop`、`HumanVoice::control`、`ParametricGlottis::next`、`mandarin::pinyin_syllable` | 発話4条件と歌唱3譜例で閉鎖指示・静的開口の独立計算と周期復帰を照合。診断句の音響未対応欄は空。2譜例の実ブラウザと保存ケースの再演を含め98項目を2回通過。[読解と実測](notes/glottal-stop.md) |
| 第7段階の片側の鳴管音源 | `Songbird::sample`、`SyrinxLabia::next`、`SyrinxTable` | 8条件の開口率が固定上流と全サンプル一致。独立積分で変位と周期を照合し、ゲートの時定数が内部レートで変わることを確認。[読解と実測](notes/songbird-syrinx.md) |
| 第7段階の左右の鳴管と共通気管 | `songbird::create`、`Songbird::control`、`Songbird::sample`、`AirwayNetwork::step` | 6条件の開口率とポート面積が上流と全サンプル一致。独立計算で枝流量と気管入口の圧力を照合し、片側・両側の流量変化と放射を確認。[読解と実測](notes/songbird-airway.md) |
| 第7段階の鳴禽の持続音と停止 | `CreatureVoice::new`、`set_gate`、`control`、`render`、`Decimator` | 3レートの持続・停止と振幅制限を照合。5条件の253,875フレームと上流CLIの先頭1.6秒がビット一致。128・77フレームの分割に依存しないことを確認。[読解と実測](notes/songbird-sustain-pcm.md) |
| 第7段階の鳴禽の実時間WASM・AudioWorklet | `engine_set_creature`、`Engine::render`、Workletの `creature` と `process` | 持続・停止の108,000 PCMフレームがCLI・固定上流とビット一致。左右の流量・面積を含む1,772観測点をCLIと照合。書き出したケースはCLIで再実行できる。[読解と比較](notes/worklet-songbird-sustain.md)・[再実行要約](runs/worklet-songbird-20261120-repeat/summary.json) |
| 第7段階の鳴禽のコール `flute` | `CallDef::resolve`、`CreatureVoice::play_call`、`eval_call`、`end_call` | 4条件でキー補間、呼気の制御、移調、途中停止の目標と平滑値を照合。408,960フレームのPCMと上流CLIの先頭3.3秒がビット一致。[読解と実測](notes/songbird-flute.md) |
| 第7段階の鳴禽コールの実時間開始・停止 | Workletの `call`・`stopCall`、`CreatureVoice::play_call`・`end_call` | `flute` の途中停止と手動呼気への復帰を比較。32,160 PCMフレームがCLIと固定上流にビット一致。544観測点でCLIとの最大差0。[読解と比較](notes/worklet-songbird-flute.md)・[再実行要約](runs/worklet-songbird-flute-20261120-repeat/summary.json) |
| 第7段階の鳴禽の周期コールの実時間検証 | `songbird::trill`、`CreatureVoice::eval_call`、Workletの `call` | ブラウザで呼気目標の18回の交差を観測。76,800 PCMフレームはCLIと固定上流にビット一致。描画時間p95の変動を記録。[読解と結果](notes/worklet-songbird-trill.md)・[ヘッドレスシェル再試行](runs/worklet-songbird-trill-20261120-shell-retry/summary.json) |
| 第7段階の鳴禽の観測位置・頻度と処理時間 | 上流Workletの `process`・`creatureTelemetry`、再実装の `CreatureProcessor::process` と `vocal_songbird_render` | 3条件で描画呼び出しを1,802・1,202・602回と実測し、全36試行でPCMと観測状態を照合。処理時間p95の安定した短縮は未確認。[登録条件](cases/worklet-songbird-trill-observation.json)・[読解と実測](notes/worklet-songbird-trill-observation.md) |
| 第7段階の鳴禽コールのキー順と実時間出力 | `songbird::def` の `chirps`、`CallDef::resolve`、`CreatureVoice::eval_call` | 44.1 kHzの48,510 PCMフレームがCLI・固定上流とビット一致。宣言順と時刻順の対照では22,016で呼気、22,022で放射、22,028で判定閾値を超えるPCM差を観測。[読解と実測](notes/worklet-songbird-chirps.md)・[合成段の記録](runs/worklet-songbird-chirps-20261120-stages/summary.json) |
| 第7段階の鳴禽の初回呼気パルス | `songbird::def` の `buzz`、`CreatureVoice::eval_call` | 96 kHzで8交差、初回6,080・定常6,720フレーム。105,600 PCMフレームがブラウザとCLIでビット一致。固定上流の減衰部の1サンプル差も再現。[読解と実測](notes/worklet-songbird-buzz.md)・[再実行の要約](runs/worklet-songbird-buzz-20261120-repeat/summary.json) |
| 第7段階の鳴禽のコール切り替え | `CreatureVoice::set_params`、`play_call`、`end_call` | 9,601で手動目標が戻り、9,664で次の制御が反映。対照との放射差は9,665、PCM差が判定閾値を超えたのは9,676。ブラウザの57,600 PCMフレームはCLI・固定上流とビット一致。[実測](notes/worklet-songbird-switch.md)・[再実行](runs/worklet-songbird-switch-20261120-repeat/summary.json) |
| 第7段階の鳴禽の周期コールと切り替え | `songbird::trill`、`songbird::def`、`CreatureVoice::play_call`、`eval_call` | 全4コールを共有のキー評価器に接続。重なるキーの定義順、呼気目標の周期、切り替え時の演奏値を照合。上流CLI全体のPCM 344,994フレームがビット一致。[読解と実測](notes/songbird-calls.md) |
| 第7段階のアザラシの呼気パルス | `Seal::control`、`CreatureVoice::new`、`CreatureVoice::control` | 3レート・7条件で、初期化、ゲートと演奏値の平滑化、パルス位相と倍率を照合。3,901行の肺圧が上流と完全一致。[読解と実測](notes/seal-breath.md) |
| 第7段階のアザラシの気道と声門 | `mammal_airway`、`step_glottis`、`Seal::sample` | 3レート・5条件、計27,648内部サンプルで圧力、流量、声門開口、放射を照合。加圧から気管端と声門が応答する順序、無呼気の隙間を独立計算で確認。[登録ケース](cases/seal-airway.json)・[読解と実測](notes/seal-airway.md) |
| 第7段階のアザラシの持続音と停止 | `CreatureVoice::render`、`Seal::gain`、`Decimator::push` | 5条件で壁と口端の放射、間引き、DC除去、飽和、分割長とPCMを照合。上流CLIの先頭76,800フレームがビット一致。[登録ケース](cases/seal-sustain-pcm.json)・[読解と実測](notes/seal-sustain-pcm.md) |
| 第7段階のアザラシの実時間持続音と停止 | Workletの `creature`・`gate`、`CreatureVoice::control` と `Seal::sample` | 48・96 kHzの134,400 PCMフレームと13系列2,116点がCLIと一致。壁面放射が口端より56内部サンプル先行した。96 kHzの上流との最大PCM絶対差は `7.11×10⁻¹⁵`。[読解と実測](notes/worklet-seal-sustain.md)・[再実行](runs/worklet-seal-sustain-20261120-repeat/summary.json) |
| 第7段階のアザラシの下行コール `trill` | `seal::def`、`CreatureVoice::play_call`・`eval_call`・`end_call` | 3レートで指数補間、移調と制限、手動ゲートとの優先、自然終了と途中停止を照合。上流と目標・平滑値・肺圧が一致。[登録ケース](cases/seal-trill.json)・[読解と実測](notes/seal-trill.md) |
| 第7段階のアザラシの `trill` の実時間検証 | Workletの `call`・`stopCall`、`CreatureVoice::play_call` | 48・44.1・96 kHzの350,000 PCMフレームと27系列5,497点がCLIと一致。44.1 kHzの停止は23,221で目標へ、23,232で平滑値と肺圧へ反映。[読解と実測](notes/worklet-seal-trill.md)・[再実行](runs/worklet-seal-trill-20261120-repeat/summary.json) |
| 第7段階のアザラシの短い下行コール `zap` | `seal::def`、`CallDef::resolve`、`play_call` と `eval_call` | 3レートで音高とゲートの独立補間、深さ0への減衰、`trill` からの目標復帰と再生中の手動変更を照合。公式CLIの `zap` 区間32,160フレームがビット一致。[登録ケース](cases/seal-zap.json)・[読解と実測](notes/seal-zap.md) |
| 第7段階のアザラシの `zap` の実時間検証 | Workletの `call`・`cparams`、`CreatureVoice::play_call`・`eval_call` | 3レート380,160 PCMフレームと27系列6,027点がCLIと一致。44.1 kHzの切り替え指示8,301から、制御8,320、壁面・総放射の内部16,641、PCM差8,323を比較。[読解と実測](notes/worklet-seal-zap.md)・[再実行](runs/worklet-seal-zap-20261120-repeat/summary.json) |
| 第7段階のアザラシの `whistle` | `seal::def`、`CreatureVoice::eval_call` と `control` | 3レートで下降と上昇の指数補間、目標と平滑音高の谷、ゲートの直線下降と手動値への復帰を照合。比較した制御系列と肺圧が上流と一致。[登録ケース](cases/seal-whistle.json)・[読解と実測](notes/seal-whistle.md) |
| 第7段階のアザラシの `whistle` の実時間検証 | Workletの `call`・`cparams`、`CreatureVoice::eval_call`・`control` | 3レート560,160 PCMフレームと27系列8,771点がCLIと一致。目標と平滑音高の谷の間隔は6.67〜8.00 msで、対数IIRが両方の時刻を再現。[読解と実測](notes/worklet-seal-whistle.md)・[再実行](runs/worklet-seal-whistle-20261120-repeat/summary.json) |
| 第7段階のアザラシの `chug` と公式デモ全体 | `seal::def`、`Seal::control`、`ParametricGlottis::next` | 90 Hz、11 Hzの呼気パルスと粗さの減衰を3レートで照合。全条件で肺圧、声門位相、瞬時F0が一致。公式デモの `chug` 区間69,600フレームの最大PCM差は `6.78×10⁻²¹`。[第2版のケース](cases/seal-chug-v2.json)・[読解と実測](notes/seal-chug.md) |
| 第7段階のアザラシの `chug` と声門周期の実時間検証 | `Seal::control`、`ParametricGlottis::next`、アザラシ用WASMの観測列 | 3レート622,760 PCMフレームと35系列116,057点がCLIと一致。96 kHzで呼気の折り返し11回と声門の88回を照合し、全100周期の倍率を独立計算で再現。[読解と実測](notes/worklet-seal-chug.md)・[再実行](runs/worklet-seal-chug-20261120-repeat/summary.json) |
| 第7段階のアリゲーターの固定気道と発声 | `alligator::create`、`Alligator::control`、`mammal_airway` | 5条件で肺圧から声門・壁面・口端・鼻端の放射とPCMを照合。公式デモの先頭76,800フレームは最大差 `7.11×10⁻¹⁵`。制御境界での微小値消去と端への到達の関係を確認。[第2版のケース](cases/alligator-fixed-voice-v2.json)・[読解と実測](notes/alligator-fixed-voice.md) |
| 第7段階のアリゲーターの固定発声の実時間検証 | Workletの `creature`・`gate`、`Alligator::control`、`step_glottis` | 5条件120,878 PCMフレームと観測4,666点をCLIに照合。標準の壁面は内部48、口端と鼻端は139・143。[読解と実測](notes/worklet-alligator-fixed-voice.md)・[再実行](runs/worklet-alligator-fixed-20261120-repeat/summary.json) |
| 第7段階のアリゲーターの `bellow` | `alligator::def`、`CreatureVoice::eval_call`、`ParametricGlottis::next` | 3レートで目標と平滑値、途中停止、口腔乱流源の切り替えと全189周期を照合。公式 `bellow` 区間120,000フレームの最大PCM差は `9.31×10⁻¹⁰`。[登録ケース](cases/alligator-bellow.json)・[読解と実測](notes/alligator-bellow.md) |
| 第7段階のアリゲーターの `bellow` の実時間検証 | Workletの `cparams`・`call`・`stopCall`、`CreatureVoice::end_call`、`mammal_noise` | 3レート473,000 PCMフレームと71,383観測点がCLIと一致。44.1 kHzの停止で目標は53,107、平滑値は53,120で復帰を開始。実断面に対して乱流源の登録・解除は内部87・61サンプル先行。[事前登録](cases/worklet-alligator-bellow.json)・[読解と実測](notes/worklet-alligator-bellow.md)・[再実行](runs/worklet-alligator-bellow-20261120-repeat/summary.json) |
| 第7段階のアリゲーターの `growl` | `alligator::def`、`CreatureVoice::play_call`・`end_call`、`CallDef::resolve` | 3レートでゲートと音高の補間、上限、`bellow` からの手動値復帰を照合。公式 `growl` 区間52,800フレームはPCMがビット一致。[登録ケース](cases/alligator-growl.json)・[読解と実測](notes/alligator-growl.md) |
| 第7段階のアリゲーターの `growl` の実時間検証 | Workletの `cparams`・`call`、`CreatureVoice::end_call`・`control` | 3レートで396,392 PCMフレームと70,186観測点がCLIと一致。切り替え時に保留された `hiss` の復帰を、目標23,617から声門・放射・PCMまで照合。[事前登録](cases/worklet-alligator-growl.json)・[読解と実測](notes/worklet-alligator-growl.md) |
| 第7段階のアリゲーターの `hiss` | `alligator::def`、`Alligator::control`、`mammal_noise`、`AirwayNetwork::compute_noise` | 3レートで口腔乱流源の解除・再登録と声門乱流の注入圧を照合。有声ゲートは開始約1.1391秒で0.5に戻った。公式区間86,400フレームの最大PCM差は `5.68×10⁻¹⁴`。[登録ケース](cases/alligator-hiss.json)・[読解と実測](notes/alligator-hiss.md) |
| 第7段階のアリゲーターの `hiss` の実時間検証 | Workletの `call`、`mammal_noise`、`AirwayNetwork::compute_noise` | 3レート558,800 PCMフレームと116,978観測点がCLIと一致。96 kHzで声門注入圧を独立計算に照合し、口腔源の解除で変わる乱数の消費順を対照で確認。[事前登録](cases/worklet-alligator-hiss.json)・[読解と実測](notes/worklet-alligator-hiss.md) |
| 第7段階のアリゲーターの `dance` と公式デモ全体 | `alligator::def`、`CreatureVoice::eval_call`、`ParametricGlottis::next` | 3レートでキーの所有、周期長と低域を比較。公式デモ全441,600フレームの最大PCM差は `9.31×10⁻¹⁰`、`dance` 開始後の105,600フレームでは `2.27×10⁻¹³`。[登録ケース](cases/alligator-dance.json)・[読解と実測](notes/alligator-dance.md) |
| 第7段階のアリゲーターの `dance` の実時間検証 | Workletの `call`、`ParametricGlottis::next`、`AirwayNetwork::step` | 3レート746,600 PCMフレームと156,832観測点がCLIと一致。96 kHzで総放射流量とその差分のピークを18.33・35.00 Hzと測り、各経路から出力を再構成。[事前登録](cases/worklet-alligator-dance.json)・[読解と実測](notes/worklet-alligator-dance.md) |
| 第7段階のゾウの固定気道と放射経路 | `elephant::create`、`Elephant::control`・`sample`、`mammal_airway` | 3レートで口・鼻の断面、基部から鼻先までの伝搬、放射の振り分けを照合。公式冒頭76,800フレームの最大PCM差は `4.66×10⁻¹⁰`。[登録ケース](cases/elephant-fixed-voice.json)・[読解と実測](notes/elephant-fixed-voice.md) |
| 第7段階のゾウの固定発声の実時間検証 | Workletの `creature`・`cparams`、`Elephant::control`・`sample` | 3レート187,424 PCMフレームと54,939観測点がCLIと一致。経路変更だけを省く対照で、断面から口端・壁面・PCMと鼻の基部・入口弁・先端に差が現れる時刻を比較。[事前登録](cases/worklet-elephant-fixed-voice.json)・[読解と実測](notes/worklet-elephant-fixed-voice.md) |
| 第7段階のゾウの `rumble` | `elephant::def`、`CreatureVoice::eval_call`・`end_call` | 3レートで15→12 Hzの目標、移調、手動ゲート、所有終了を照合。公式冒頭249,600フレームと `rumble` 区間172,800フレームの最大PCM差はともに `3.73×10⁻⁹`。[登録ケース](cases/elephant-rumble.json)・[読解と実測](notes/elephant-rumble.md) |
| 第7段階のゾウの `rumble` の実時間検証 | Workletの `call`・`stopCall`、`CreatureVoice::control`、`AirwayNetwork::step` | 3レート657,600 PCMフレームと10,978観測点がCLIと一致。44.1 kHzで肺圧が立ち上がる前の64フレームに口端の放射とPCMを観測し、固定断面の対照と比較。[事前登録](cases/worklet-elephant-rumble.json)・[読解と実測](notes/worklet-elephant-rumble.md) |
| 第7段階のゾウの入口弁と発声モード | `LipReed::next`、`Elephant::control`・`sample` | 差圧ステップの自由開口は上流と一致。3レートで声門開大、自由開口と実断面、鼻先放射を照合し、最大PCM差は `3.73×10⁻⁹`。[登録ケース](cases/elephant-valve.json)・[読解と実測](notes/elephant-valve.md) |
| 第7段階のゾウの `trumpet` | `elephant::def`、`CreatureVoice::eval_call`・`end_call` | 3レートで指数補間、所有の切り替え、音高指定の対照、弁と放射を照合。公式の `trumpet` 区間84,000フレームは最大PCM差 `9.31×10⁻¹⁰`。[登録ケース](cases/elephant-trumpet.json)・[読解と実測](notes/elephant-trumpet.md) |
| 第7段階のゾウの `trumpet` の実時間検証 | `Elephant::sample`、`LipReed::next`、`CreatureVoice::eval_call` | 3レート4条件で620,368 PCMフレームと135,801観測行がCLIと一致。公式の弁作動60,288フレームでは実断面を面積下限が決めた。96 kHzの対照で音高指定の有無による差は0。[事前登録](cases/worklet-elephant-trumpet.json)・[読解と実測](notes/worklet-elephant-trumpet.md) |
| 第7段階のゾウの `squeak` と公式デモ全体 | `elephant::def`、`CreatureVoice::eval_call`、`Elephant::sample` | 3レートで短い呼気、所有の復帰、初期モードと実断面を照合。公式全381,600フレームの最大PCM差は `3.73×10⁻⁹`、末尾48,000フレームは `9.31×10⁻¹⁰`。[登録ケース](cases/elephant-squeak.json)・[読解と実測](notes/elephant-squeak.md) |
| 第7段階のゾウの `squeak` の実時間検証 | Workletの `call`、`CreatureVoice::control`、`Elephant::sample` | 3レート4条件のPCM 556,432フレームと72,795観測行がCLIと一致。公式デモ全381,600フレームをブラウザで照合し、96 kHzの初期モードの対照で自由開口が実断面を決める区間を確認。[事前登録](cases/worklet-elephant-squeak.json)・[読解と実測](notes/worklet-elephant-squeak.md) |
| 第7段階の操作・提示機能 | `MidiButton`、`AnatomyView3D`、`Clip`、`DuetPage` | 入出力、既存の研究用観測点、未照合範囲、着手順を対応表に記録。[操作と表示の対応表](notes/interaction-presentation.md) |
| 第7段階の手動発声のWeb MIDI | `connectMidi`、演奏側の `noteOn`・`noteOff`、Workletの `source` | 仮想2入力の14操作で上流と選択音が一致し、実ブラウザから書き出したケースでCLIのPCMをビット再現。物理MIDIと他の演奏経路は未測定。[事前登録](cases/worklet-midi-voice.json)・[読解と実測](notes/worklet-midi-voice.md) |
| 第7段階の固定姿勢の三次元断面 | `AnatomyView3D`、`Anatomy3D` の楕円リング | 固定 `/i/` と口唇開度0.30 cmの49測定線を実ブラウザで描画し、CLI・固定上流・頂点から復元した中心・面積を照合。2画面幅と視点の切り替えを検証済み。[事前登録](cases/worklet-tract-3d.json)・[読解と実測](notes/worklet-tract-3d.md) |
| 第7段階の発話時刻の三次元断面 | `HumanVoice` の制御更新、`HumanAirway::reapply`、`Anatomy3D` の楕円 | オフライン `ɑpɑ` の65時点・各49測定線をCLIと固定上流に照合。閉鎖前・閉鎖中・開放後で三次元断面と音響セルが同じフレームを使うこと、2画面幅での閉鎖マーカーと独立した面積復元を確認。[事前登録](cases/worklet-tract-3d-dynamic.json)・[読解と実測](notes/worklet-tract-3d-dynamic.md) |
| 第7段階の歌唱動画の収録 | `playTune` の開始・終了・中止、`AudioEngine::recordStream`、`Clip` | 48 kHzの実時間歌唱と2拍のマーカーを720×1280のMP4に保存。デコード後の2拍の差、末尾の無音、準備中・録画中の中止と再開を固定上流・CLIと照合した。[事前登録](cases/worklet-song-recording.json)・[読解と実測](notes/worklet-song-recording.md) |
| 第7段階のSafariでの歌唱録画中の停止 | `Clip`、研究版の `SongRecording` と `FixedProcessor.process()` | Contextを120〜121 ms停止。録画の復号音声と音声PTSは連続条件と一致し、停止位置付近の映像のPTS幅は5.0〜8.3 msだった。[事前登録](cases/worklet-live-song-fast-safari-recording-pause.json)・[読解と実測](notes/worklet-live-song-fast-safari-recording-pause.md) |
| 第7段階のSafari録画を止めるAPIの比較 | `Clip`、`AudioContext.suspend()`、`MediaRecorder.pause()` | Context停止では異なる壁時計値が6.7〜8.3 ms幅の映像PTSに残り、録画だけの一時停止ではその区間の映像が0枚で元信号9,216〜9,472サンプルが欠けた。[事前登録](cases/safari-recording-pause-clock-split.json)・[読解と実測](notes/safari-recording-pause-clock-split.md) |
| 第7段階のSafari録画で音声トラックの有無を比較 | `Clip`、公開WebKitの `MediaRecorderPrivateEncoder::appendVideoFrame()` | 同じContext停止で、音声付きの停止中の映像PTS幅は6.7〜8.3 ms。映像のみのPTS幅は対応する壁時計幅と1.34 ms以内で一致した。[事前登録](cases/safari-recording-video-clock.json)・[読解と実測](notes/safari-recording-video-clock.md) |
| 第7段階の固定上流の通常歌唱録画で途中停止 | `SingPanel.sing()`、`playTune()`、`Clip`、`ChimeraProcessor.process()` | Safariで約120 ms停止しても、録画音声の前後のオフセットは0サンプル変化。停止中に描かれた3枚は3.33 msの映像PTS幅に収まった。[事前登録](cases/upstream-safari-song-recording-pause.json)・[読解と実測](notes/upstream-safari-song-recording-pause.md) |
| 第7段階の固定上流で譜面の予約フレームを固定 | `ChimeraProcessor.handle()`、`Engine::schedule()`、`HumanVoice::telemetry()` | 同じ予約位置の連続・停止でPCM29,760サンプルと状態40〜41点が一致。予約を128フレーム遅らせると停止前にPCMが分かれた。[事前登録](cases/upstream-safari-song-fixed-schedule-frame.json)・[読解と実測](notes/upstream-safari-song-fixed-schedule-frame.md) |
| 第7段階の歌唱予約フレームと内部状態 | `Engine::schedule()`、`ParametricGlottis::next()`、`AirwayNetwork::compute_noise()` | 固定上流の最初のPCM差の経路を声門流から咽頭枝への乱流圧に絞った。乱流注入を止めると、PCM差の閾値超過が14,330から20,903サンプルへ移った。[事前登録](cases/upstream-song-schedule-state.json)・[読解と実測](notes/upstream-song-schedule-state.md) |
| 第7段階の研究版での歌唱予約前の描画 | `run_song()`、`speech_voice::render()`、`OutputStage::render_frame()` | 通常CLIから予約前の描画量を指定し、固定上流と同じ14,256サンプルに咽頭枝13の注入圧、14,330サンプルにPCM差の閾値超過を確認。乱流注入量0のPCMでは5サンプルの差が残った。[事前登録](cases/song-voice-schedule-state.json)・[読解と実測](notes/song-voice-schedule-state.md) |
| 第7段階の歌唱のピッチドリフト | `Engine::set_source()`、`ParametricGlottis::next()`、`PitchModulation::step()` | 通常の歌唱CLIでドリフト0・5セントを比較し、独立計算とF0を照合。上流と係数をそろえた有声区間でPCMのRMS誤差が57〜59%減った。[事前登録](cases/song-voice-schedule-drift.json)・[読解と実測](notes/song-voice-schedule-drift.md) |
| 第7段階の歌唱の周期ジッター | `HumanVoice::apply_source()`、`ParametricGlottis::next()`、`Glottis::step()` | 通常の歌唱CLIでジッター0.00455を指定し、固定上流の位相とF0に31,200点すべてでビット一致。有声区間のPCMのRMS誤差は83.7〜87.4%減った。[事前登録](cases/song-voice-schedule-jitter.json)・[読解と実測](notes/song-voice-schedule-jitter.md) |
| 第7段階の歌唱の振幅シマー | `HumanVoice::apply_source()`、`ParametricGlottis::next()`、`Glottis::step()` | シマー0.042で振幅倍率を独立計算と照合し、ドリフト0の上流と4条件でPCMの最大差1.46×10⁻¹¹。位相・F0と有声窓のPCMがビット一致した。[事前登録](cases/song-voice-schedule-shimmer.json)・[読解と実測](notes/song-voice-schedule-shimmer.md) |
| 第7段階の上流既定の歌唱音源 | `Engine::schedule()`、`ChimeraProcessor.process()`、研究版の `run_song()` | ドリフト5・ジッター0.00455・シマー0.042で、Safari保存PCMとCLIの最大差7.28×10⁻¹²。予約128フレーム差の通常乱流の閾値超過は両ネイティブとSafariで14,330サンプル。[事前登録](cases/song-voice-schedule-default-source.json)・[読解と実測](notes/song-voice-schedule-default-source.md) |
| 第7段階の研究版ブラウザ歌唱の音源設定と予備描画 | `Engine::schedule()`、`vocal_start_score_prepared()`、`prepareSongVoice()` | Chromiumの既存オフライン・実時間歌唱から予備描画2位置と乱流係数2設定を描画し、8試行のPCM各31,200点と声門など488観測点をCLIに照合した。[事前登録](cases/worklet-song-prepared-source.json)・[読解と実測](notes/worklet-song-prepared-source.md) |
| 第7段階の研究版Safariでの予備描画と途中停止 | `FixedVoiceEngine`、`RealtimeSpeechCapture`、Safariの `AudioContext.suspend()` | 予備描画16,384・16,512フレームでWorklet内の構築135〜142 ms、予備描画0で3〜4 ms。全16試行のPCMと、停止を含む予備描画付きの観測をCLI・Chromiumに照合。[事前登録](cases/worklet-safari-song-prepared-pause.json)・[読解と実測](notes/worklet-safari-song-prepared-pause.md) |
| 第7段階のSafariでの先行信号と歌唱構築 | `vocal_start_score_prepared()`、Safariの `AudioWorkletProcessor.process()` | 同じContextで予備描画16,384フレームを構築すると、先行信号のコールバック間隔が134〜159 msに広がった。0フレームでは4〜6 ms。全16試行で先行信号のPCMが独立計算に、歌唱PCMと観測値がSafari基準に一致した。[事前登録](cases/worklet-safari-song-prepared-shared-context.json)・[読解と実測](notes/worklet-safari-song-prepared-shared-context.md) |
| 第7段階のSafariでの歌唱予備描画の分割 | `vocal_start_score_preparation()`、`vocal_advance_score_preparation()`、`RealtimeSpeechCapture` | 本番の合成器で128フレーム×128片を描画し、先行信号の最大間隔を134〜141 msから4〜23 msへ短縮した。全16試行で歌唱PCMと観測点が一致し、歌唱開始は8ペアの中央値で275.5 ms遅くなった。[事前登録](cases/worklet-safari-song-split-score-preparation.json)・[読解と実測](notes/worklet-safari-song-split-score-preparation.md) |
| 第7段階のSafariでの歌唱予備描画の分割長 | `FixedProcessor.process()`、`advanceScorePreparation()` | 同じ予備描画を256フレームずつ進めると、128フレームずつの場合より歌唱開始が8ペアの中央値で167.5 ms早まった。第2片以降の先行信号の最大間隔の増加は中央値1 ms。歌唱PCMと状態は保存基準に一致した。[事前登録](cases/worklet-safari-song-score-preparation-block-size.json)・[読解と実測](notes/worklet-safari-song-score-preparation-block-size.md) |
| 第7段階のSafariでの歌唱予備描画片の処理時間 | `FixedProcessor.process()`、`Date.now()`、先行信号の `currentFrame` | 256フレーム分割では第1片が5〜8 ms、第2片が4〜5 ms。1 msを引いても量子予算2.667 msを超えたのは8試行とも最初の2片だった。後続片の無音出力までの中央値は128フレーム分割で1 ms、256フレーム分割で2 ms。[事前登録](cases/worklet-safari-song-score-preparation-timing.json)・[読解と実測](notes/worklet-safari-song-score-preparation-timing.md) |
| 第7段階のSafariで歌唱予備描画の最初の2片を短縮 | `FixedVoiceEngine.advanceScorePreparation()`、`vocal_advance_score_preparation()` | 第1・2片を64フレームにすると2片のピークがペア中央値で4 ms短縮した。最大値が最初に現れる位置は全8試行で第3片へ移り、最初の6片のピークは中央値1 ms短縮。先行信号と歌唱のPCMは基準に一致した。[事前登録](cases/worklet-safari-song-score-preparation-initial-blocks.json)・[読解と実測](notes/worklet-safari-song-score-preparation-initial-blocks.md) |
| 第7段階のSafariで歌唱予備描画を同じ位置から切り替える | `advanceScorePreparation()`、`vocal_advance_score_preparation()` | 累積256フレームまでの準備を128フレーム2片から64フレーム4片に変えると、次の256フレーム片はペア中央値で1 ms短縮した。歌唱開始は中央値3 ms延び、先行信号と歌唱のPCMと観測状態は保存基準に一致した。[事前登録](cases/worklet-safari-song-score-preparation-switch.json)・[読解と実測](notes/worklet-safari-song-score-preparation-switch.md) |
| 第7段階のSafariの出力PCMの較正 | `AudioContext`、Core Audioのプロセス出力状態と `CATapDescription` | 試験音の開始・停止・再開で同じWebKit GPUプロセスを特定。グラフの各20,480サンプルは独立計算に一致し、欠落・重複・無音128サンプルを対照で識別した。OSの録音許可要求でタップの入力PCMと時刻が欠測した。[事前登録](cases/safari-process-tap-calibration.json)・[読解と実測](notes/safari-process-tap-calibration.md) |
| 第7段階のSafariで試験音のI/O時刻を照合 | `AudioContext`、WebKit GPU、Core AudioのAudio Client | 同じPIDで停止中0件、再生中770・771件のI/Oサイクルを確認。開始間隔の中央値は2.667 ms、最大は4.78・5.15 ms。グラフのPCM各230,400サンプルは基準と一致した。[事前登録](cases/safari-audio-client-trace.json)・[読解と実測](notes/safari-audio-client-trace.md) |
| 第7段階のSafariの歌唱準備とCore AudioのI/O時刻 | `FixedProcessor`、WebKit GPU、Core AudioのAudio Client | 同量の一括・分割でグラフの最大間隔は143〜148 msから6〜10 msへ短縮。対応する窓のGPUの最大I/O開始間隔は全試行で約2.7 ms。先行・歌唱PCMと観測点が基準に一致した。[事前登録](cases/worklet-safari-song-audio-client.json)・[読解と実測](notes/worklet-safari-song-audio-client.md) |
| 第7段階のAudioUnitの戻り値とAudio Clientの較正 | WebKitの共有リング、`AudioUnit` の `OSStatus`、Audio Client | 16要求連続で `-1` を返した対照でサンプル時刻が連続し、Audio Clientの4表から戻り値の変化を識別できなかった。Safariの保存窓を付記込みで再集計して最大間隔の一致を確認した。[事前登録](cases/coreaudio-output-render-status.json)・[読解と実測](notes/coreaudio-output-render-status.md) |
| 第7段階のSafariの描画通知とWeb側の待機 | `RemoteAudioDestination::render`、`RemoteAudioDestinationProxy`、Core Audio | 準備前の123 I/OサイクルをGPUとWeb側の通知・待機に照合。準備中のGPU通知は一括・分割の2組で最大約2.7 ms。分割の1試行でWeb側の条件変数待ち7.143 msを観測した。[事前登録](cases/worklet-safari-song-output-notification.json)・[読解と実測](notes/worklet-safari-song-output-notification.md) |
| 第7段階のSafariのWeb側でのWorklet完了待ち | `RemoteAudioDestinationProxy`、`SharedAudioDestination::sharedRender`、`WTF::BinarySemaphore` | 同じ呼び出し元の最長待機は一括137〜139 ms、分割約5〜6 ms。同じWebContentのWorkletがその条件変数へ通知していた。先行音と歌唱のPCM、観測点は基準に一致した。[事前登録](cases/worklet-safari-song-webcontent-waits.json)・[読解と実測](notes/worklet-safari-song-webcontent-waits.md) |
| 第7段階のSafariの歌唱準備後の公開出力位置 | `RemoteAudioDestinationProxy::renderAudio()`、`BaseAudioContext::handlePreRenderTasks()`、`AudioContext::getOutputTimestamp()` | 一括2試行で公開位置が準備中に136 ms据え置かれ、その後に4,096フレーム進んだ。分割では準備と準備後の公開位置がグラフ位置に制約され、位置差は欠測した。[事前登録](cases/worklet-safari-song-output-position.json)・[読解と実測](notes/worklet-safari-song-output-position.md) |
| 第7段階のSafariのタップ採取と滑らかな試験音 | `AudioBufferSourceNode`、`CATapDescription`、Core Audioの入力時刻 | 48 kHzステレオのタップ採取が動作し、滑らかな逆相の既知信号を較正2試行で37,888・45,056点連続で照合。歌唱を含まない試行にも約128・256フレーム分の位相の遅れが現れた。[事前登録](cases/safari-process-tap-smooth-marker.json)・[読解と実測](notes/safari-process-tap-smooth-marker.md) |
| 第7段階のSafariの歌唱準備中のプロセス出力 | `renderRealtimeSongVoice()`、Core Audioタップ、既知信号の位相照合 | 一括2試行で両チャンネルが完全にゼロの区間6,305点と3,873点が現れ、分割では最長33点。歌唱・先行信号のグラフPCMは基準と一致し、プロセス出力では約10,368フレームの位相の遅れが現れた。[事前登録](cases/worklet-safari-song-process-output.json)・[読解と実測](notes/worklet-safari-song-process-output.md) |
| 第7段階のSafariの二つの無音とWebKitの出力順 | `RemoteAudioDestination::render()`、`CARingBuffer::fetchIfHasEnoughData()`、`PushPullFIFO::pull()` | 6,400不足→128の信号→3,968のFIFO無音をモデル化し、保存した2試行で中間波形と回復後の位相を照合した。最初の不足量子の後半で公開版の減衰波形は観測されなかった。[事前登録](cases/webkit-output-underrun.json)・[読解と照合](notes/webkit-output-underrun.md) |
| 第7段階のAudioUnitの戻り値と減衰PCM | `AudioOutputUnitAdaptor::inputProc()`、`DefaultOutput`、Core Audioタップ | 同じ512フレームの減衰は戻り値0・`-1` の両方でタップまで届いた。試行機のSafariとビルド番号末尾が一致するApple公開版のリング不足時には出力へ減衰を書く処理がなかった。[事前登録](cases/coreaudio-output-error-pcm.json)・[実測と版差](notes/coreaudio-output-error-pcm.md) |
| 第7段階のAudioUnitの要求バッファの入口と無音境界 | `AURenderCallback`、`DefaultOutput`、Core Audioタップ | 左右ゼロのバッファを保持しても、明示的にゼロを書いても、タップの完全ゼロは2,048フレームのうち1,953フレーム。Safariの保存波形で見えた95フレームの区間差を自作出力でも観測した。[事前登録](cases/coreaudio-output-buffer-entry.json)・[読解と実測](notes/coreaudio-output-buffer-entry.md) |
| 第7段階のSafariの予備描画分割長とプロセス出力 | `renderRealtimeSongVoice()`、`advanceScorePreparation()`、Core Audioタップ | 均等128と64×4＋256を比較し、後者で全8ペアの歌唱立ち上がりが162〜204 ms早まった。最長低振幅はペア中央値で110.5フレーム短く、加工前PCMと観測値は一致した。[事前登録](cases/worklet-safari-song-process-output-block-size.json)・[読解と実測](notes/worklet-safari-song-process-output-block-size.md) |
| 第7段階のSafariで冒頭をそろえた予備描画分割 | `advanceScorePreparation()`、グラフの第5片、Core Audioタップ | 64×4を固定し後続を128から256にすると、全8ペアでタップの歌唱が早まり、中央値は182.8 ms。加工前PCMと各488観測点は一致した。反転順の冒頭の低振幅に関する予測は未達。[事前登録](cases/worklet-safari-song-process-output-matched-start.json)・[読解と実測](notes/worklet-safari-song-process-output-matched-start.md) |
| 第7段階のFirefoxのcubeb・プロセスタップ同時採取 | `AudioCallbackDriver::Init()`、`audiounit_output_callback()`、`AudioDeviceCreateIOProcIDWithBlock()` | 事前描画2試行でcubebの4,352フレームは連続し、次の予定要求は256フレーム飛んだ。同じ両端のタップ区間は4,608フレームで、完全ゼロは161フレームだった。[ケース](cases/worklet-live-song-paired-output-smooth.json)・[読解と実測](notes/worklet-live-song-paired-output.md#滑らかな先行音での同時採取) |
| 第7段階のcubeb出力遅延の単独対照 | `cubeb_stream_init()`、`resampler.fill()`、`AudioDeviceCreateIOProcIDWithBlock()` | 歌唱なしで8.4 ms待機を1回加えた全4試行に、予定時刻の256フレームの飛びとタップ区間の256フレーム延長が現れた。返却PCMは全試行で一致し、完全ゼロは162フレームだった。[ケース](cases/cubeb-output-callback-process-tap.json)・[読解と実測](notes/cubeb-output-callback-probe.md#歌唱を使わないプロセスタップの同時採取) |
| 第7段階の歌唱F0の複数候補と連続性 | `Analyzer::pitch()`、`yin_pitch()`、`vibrato()` | 200 Hzの基本音を弱める対照で、約400 Hzの窓が12から0、最大差1.24 Hz。確認曲 `en035a` 第21音で両合成の外れ値が各4窓から0になったのは窓ごとの候補選択による。[ケース](cases/csd-f0-continuity.json)・[読解と実測](notes/csd-f0-continuity.md) |
| 第7段階のCSD全曲でのF0候補と倍音評価 | `compare_song()`、`Analyzer::note()`、`harmonic_db()` | 調整・確認各2曲の88,344窓で、両合成の高F0窓677件が窓ごとの候補選択で0になった。時間費用による追加変更は16窓。録音の365窓でF0が変わり、曲別中央値の変化は最大0.473セント。[ケース](cases/csd-f0-continuity-songs.json)・[読解と実測](notes/csd-f0-continuity-songs.md) |
| 第7段階のCSD録音でのF0候補の独立照合 | `yin_pitch()`、PCMの正規化相関、短時間スペクトル | `en001a` 第65音の最大差で、相関315.84 Hzと倍音間隔316.25 Hzが長いYIN候補316.83 Hzを支持。短い候補348.39 Hzの近傍で1.2〜3 kHzの差分が増え、局所最小を形成した。[ケース](cases/csd-f0-recording-period-evidence.json)・[読解と実測](notes/csd-f0-recording-period-evidence.md) |
| 第7段階の確認曲での録音F0候補 | `Analyzer::note()`、`yin_pitch()`の累積平均正規化 | `en035a` 第36音で、相関276.23 Hzと倍音間隔275.75 Hzが長い候補276.30 Hzを支持。短い候補301.06 Hzは正規化後に現れた浅い極小で採られた。[ケース](cases/csd-f0-recording-period-evidence-held-out.json)・[読解と実測](notes/csd-f0-recording-period-evidence-held-out.md) |
| 第7段階のCSD全曲でのYIN閾値 | `Analyzer::pitch()`と`yin_pitch()`の閾値・欠測 | 0.2→0.15で632窓が長い周期に移り、109窓でF0が欠測になった。譜面より600セント以上高い合成は677→269窓。H1−H2の音符中央値は延べ75音符で変わった。[ケース](cases/csd-f0-yin-threshold.json)・[読解と実測](notes/csd-f0-yin-threshold.md) |
| 第7段階の歌唱試聴回答の集計 | `compare_song()`の音符と既存の試聴ページの回答CSV | 保存済みの6区間について、A・B・Cの回答を音源別に集計し、未回答・判定不能と自然さの差なしを区別するCLIを作った。Chromeの実出力と既知の分布で照合。[ケース](cases/csd-listening-responses.json)・[集計方法](notes/csd-listening-responses.md) |
| 第7段階の機能別の実行証拠 | 派生機能、Web MIDI・表示・録画、`compare::tsp::run()`、`compare_song()` | 27実行・1,885判定・1,655出力を元のケースと照合し、現行のRust試験42件とWebビルドを確認。許可と物理MIDI、人の試聴、体型を変えたデュエットの範囲を明記した。[事前登録](cases/plan-evidence-stage7.json)・[再監査](notes/plan-evidence-stage7.md) |
| 第7段階のWeb MIDI権限と待機中の切断 | `Keys.MidiButton()`、`setMidi()`、`connectMidi()`、`disconnectMidi()` | 研究版の6パネルでChromeの許可・拒否、待機中の切断と遅い結果、新しい要求の購読を照合。手動発声・ビート・鳴禽の仮想入力でCLIとPCMがビット一致。[ケース](cases/worklet-midi-permission.json)・[比較と実測](notes/worklet-midi-permission.md) |
| 第7段階の子ども・混合体型のデュエット乱流 | `HumanVoice::telemetry()`、`TeleTrack`、`VoiceModel.branchS()`、`drawTurbulence()` | 2体型の声門・口腔の乱流源を生成元の枝配置で照合。声門はどちらも0.2 cm、口腔は子ども11.5502 cm・混合13.8140 cm。2画面幅、前後シークと左右の配置を交換した場合の拒否を検証。[ケース](cases/duet-head-turbulence-body.json)・[実測](notes/duet-head-turbulence-body.md) |
| 第7段階の実時間の三次元断面 | `ChimeraProcessor::process` のテレメトリ、`AudioEngine`、`AnatomyView3D` | 男性体型 `ɑpɑ` の閉鎖前・閉鎖中・開放後を960・390 pxで描画。4本の転送用領域を使い、ページ停止中もPCMと保存用の65点が一致することを確認した。[事前登録](cases/worklet-tract-3d-live.json)・[実装と実測](notes/worklet-tract-3d-live.md) |
| 第7段階の歌唱動画への声道断面の取り込み | `SingPanel`、`AnatomyView3D`、`Clip::begin` | 48 kHzの二音の歌唱を三次元断面付きMP4に保存。復号画像の出力フレーム番号から唇の閉鎖点と開いた輪郭を追い、CLIの投影・加工前PCM・固定上流の格子を照合した。[事前登録](cases/worklet-song-tract-recording.json)・[読解と実測](notes/worklet-song-tract-recording.md) |
| 第7段階のWebM録画 | `pickType`、`Clip::begin`・`stop`、`MediaRecorder` | MP4を選べない条件で固定上流と候補がVP9/Opusを選び、二音の歌唱をWebMに保存した。音声PTS、拍、閉鎖と母音の輪郭、末尾の無音を復号して照合した。[事前登録](cases/worklet-song-recording-webm.json)・[読解と実測](notes/worklet-song-recording-webm.md) |
| 第7段階のデュエットの再生時計 | `App` の `?show=`、`DuetPage`、`Transport` | 二声のCLI音源で、再生・一時停止・シーク・末尾・再開とグラフで流れる波形を固定上流と照合した。再開拒否中のシークでは、固定上流との差を測って候補に停止とノード解放を追加した。[事前登録](cases/duet-transport.json)・[読解と実測](notes/duet-transport.md) |
| 第7段階のデュエットの声部別テレメトリ | `render notes --tele`、`render_tracked`、`TeleRecorder`、`TeleTrack.indexAt` | 声部ごとにサンプル0と768サンプル間隔の観測を保存し、上流・候補の読出しとCLIの独立計算に照合した。研究画面の停止中・再生中のシークと、声部ごとの末尾保持を確認した。[事前登録](cases/duet-telemetry.json)・[読解と実測](notes/duet-telemetry.md) |
| 第7段階のデュエットの歌詞 | `DuetPage` の旋律読込、`sungWords`、`wordAt` | 既存の再生時計から二声の現在の音節を選び、休符・メリスマ・シークを比較した。48 kHzの拍境界2点で見つかった秒の丸め誤差だけを補正した。[事前登録](cases/duet-words.json)・[読解と実測](notes/duet-words.md) |
| 第7段階のデュエットの三次元頭部 | `Head`、`VoiceModel.articFromArray`、`AnatomyView3D` | 左右の頭部に各声部の17軸を渡し、実ブラウザの84頭部フレームを同じ観測行とCLIの11部位に照合した。固定上流の形状キャッシュは順序を逆にして差の起点を確認した。[事前登録](cases/duet-heads.json)・[読解と実測](notes/duet-heads.md) |
| 第7段階のデュエットの口元の歌詞 | `mouthWords`、`Anatomy3D.faceView`、`advanceTrail` | 2画面幅で口唇に基づく文字の配置を70件照合し、メリスマ・休符・再発音の履歴を検証した。前後シークは世代を使って文字の履歴を初期化する。[事前登録](cases/duet-mouth-words.json)・[読解と実測](notes/duet-mouth-words.md) |
| 第7段階のデュエットの輪郭の残像 | `AnatomyView3D`、`Anatomy3D.update`、`nearestEcho`、`resetMotion` | 固定上流と二声の64回の選択を照合した。2画面幅で残像の頂点、同じ姿勢に追加された画素、停止と前後シークの履歴切替を確認した。[事前登録](cases/duet-head-echoes.json)・[読解と実測](notes/duet-head-echoes.md) |
| 第7段階のデュエットの表情と頭部の動き | `Expression.update`、`mouthPressure`、`Spring.step`、`Anatomy3D.headPose` | 固定上流と独立計算で圧力・音高・拍の状態を照合した。実ブラウザで回転と顔の頂点、一時停止の減衰、前後シーク時の初期化を比較した。[事前登録](cases/duet-head-expression.json)・[読解と実測](notes/duet-head-expression.md) |

## 最後に確認した実行

- デュエットの表情は129人工フレームで固定上流と最大 `2.50×10⁻¹⁶` の差で一致し、実ブラウザの960・390 pxで2回とも21項目を通過しました。構成によって再生開始直後に選ばれる圧力パルスが異なることも記録しました。[実ブラウザの再実行](runs/duet-head-expression-20261120-repeat/manifest.json)・[型修正前の初回](runs/duet-head-expression-20261120-a/manifest.json)・[歌詞の回帰](runs/duet-expression-mouth-regression-20261120/manifest.json)・[残像の回帰](runs/duet-expression-echo-regression-20261120/manifest.json)・[三次元頭部の回帰](runs/duet-expression-heads-regression-20261120/manifest.json)
- デュエットの輪郭の残像は960・390 pxのChromiumで2回とも19項目を通過しました。人工時計で固定上流の64回の選択と不透明度を照合し、別ディレクトリで同じ人工時計の結果を再生成しました。残像に含まれた舌の最大差は `4.62×10⁻⁴ cm` で、固定上流の形状キャッシュに由来しました。[初回計測](runs/duet-head-echoes-20261120-a/manifest.json)・[再実行](runs/duet-head-echoes-20261120-repeat/manifest.json)・[三次元頭部の回帰28項目](runs/duet-echoes-heads-regression-20261120/manifest.json)・[歌詞の回帰24項目](runs/duet-echoes-mouth-observer-20261120/manifest.json)・[歌詞の初回観測の欠測](runs/duet-echoes-mouth-regression-20261120/manifest.json)
- 口元の文字は960・300 pxのChromiumで2回とも24項目を通過しました。固定上流と独立計算に対する配置の最大差は0.00050 CSS px以内でした。判定直後の別フレームを読んだ初回の1失敗も保存しました。[最終計測](runs/duet-mouth-words-20261120-final/manifest.json)・[再実行](runs/duet-mouth-words-20261120-repeat/manifest.json)・[初版の判定](runs/duet-mouth-words-20261120-a/summary.json)・[三次元頭部の回帰28項目](runs/duet-mouth-words-heads-regression-20261120/manifest.json)
- デュエットの三次元頭部は960・390 pxのChromiumで2回とも28項目を通過しました。11部位の描画頂点とCLIの最大座標差は `4.76×10⁻⁷ cm` でした。固定上流の3桁キーが一致する2行で生じた舌の差 `2.46×10⁻⁴ cm` は、上流のキャッシュを通さないと `3.55×10⁻¹⁵ cm` 以下でした。既存の歌詞の28項目も再実行しました。[最終実行](runs/duet-heads-20261120-final/manifest.json)・[再実行](runs/duet-heads-20261120-repeat/manifest.json)・[初版](runs/duet-heads-20261120-a/summary.json)・[歌詞の回帰](runs/duet-heads-words-regression-20261120/manifest.json)
- デュエットの歌詞は登録した87件の時刻比較で有理数の計算と一致し、ブラウザと合わせた28項目を2回通過しました。上流と同じ初期実装から変化したのは54,720と78,720の境界だけで、既存のWAV・テレメトリと対照のWAVは一致しました。初回の休符末尾のRMS判定と、丸め補正前の基準も保存しました。[最終実行](runs/duet-words-20261120-final/manifest.json)・[再実行](runs/duet-words-20261120-repeat/manifest.json)・[補正前](runs/duet-words-20261120-upstream-timing/manifest.json)・[再生時計の回帰](runs/duet-words-transport-regression-20261120/manifest.json)
- 声部別テレメトリは2回で各34項目を通過しました。二声の119・128点の観測時計は固定上流と一致し、採取を加えても前回のPCMと混合WAVは変化しませんでした。Chromiumでは768サンプルの境界で行を切り替え、混合音源末尾で90,624・97,536を保持しました。初期の舌先座標に上流との差を見つけました。既存の再生時計の25項目とRustの14テストも通過しました。[最終実行](runs/duet-telemetry-20261120-final/manifest.json)・[再実行](runs/duet-telemetry-20261120-repeat/manifest.json)・[測定の詳細](notes/duet-telemetry.md)
- デュエットの再生時計は仮想時計で候補・固定上流を各30操作、Chromiumで二声WAVの通常操作と再開拒否を検証し、最新の2実行で各25項目を通過しました。候補の表示と可聴時刻の推定との差は最大8.7 msで、前後のグラフ時計が示すPCMと二つの観測区間の波形が一致しました。再開拒否の修正前は候補の2項目が失敗しており、その時系列も保持しました。研究画面からの既存歌唱の回帰25項目も通過しました。[最新実行](runs/duet-transport-20261120-clock-bracket/manifest.json)・[再実行](runs/duet-transport-20261120-clock-bracket-repeat/manifest.json)・[修正前](runs/duet-transport-20261120-before-resume-fix/summary.json)・[歌唱の回帰](runs/duet-transport-song-regression-20261120/manifest.json)
- WebM（VP9/Opus）は最終構成の2回で各45項目が通過しました。二音 `Pop Dee` のPCM 91,200フレームがCLI・MP4と一致し、場面ごとの輪郭、復号後の拍と無音を確認しました。映像は29.84〜29.93 fps、復号した断面の識別番号は両方で58種類でした。三次元付きMP4の33項目、通常録画の23項目、実時間表示の47項目も通過し、最終の観測91,199を両形式で復号できました。第1版の音声PTS判定、候補の映像間隔超過、固定上流の間隔・終端超過の各実行を残しました。[最終のWebM](runs/worklet-song-webm-20261120-final/manifest.json)・[再実行](runs/worklet-song-webm-20261120-final-repeat/manifest.json)・[MP4回帰](runs/worklet-song-webm-mp4-regression-20261120-final/manifest.json)・[通常録画の回帰](runs/worklet-song-webm-plain-regression-20261120-final/manifest.json)・[実時間表示の回帰](runs/worklet-tract-live-webm-regression-20261120/manifest.json)・[失敗の記録](notes/worklet-song-recording-webm.md)
- 三次元断面付き歌唱録画は、別ディレクトリと最終実行で33項目を通過しました。最終のMP4から56種類の出力フレーム番号を復号でき、CLIから計算した輪郭との差は最大4.01 px、整列した音声との差は最大48.7 msでした。固定上流との格子の差は最大 `9.10×10⁻¹⁴`、加工前PCMの91,200フレームはCLIとビット一致しました。通常録画の回帰23項目と、実時間の三次元表示の回帰47項目も通過しました。[最終の録画](runs/worklet-song-tract-recording-20261120-final-retry/manifest.json)・[通常録画の回帰](runs/worklet-song-tract-baseline-regression-20261120/manifest.json)・[三次元表示の回帰](runs/worklet-tract-live-song-recording-regression-20261120-b/manifest.json)・[固定上流の画像間隔が超過した試行](runs/worklet-song-tract-recording-20261120-final/summary.json)

- 実時間の三次元断面は別ディレクトリで各47項目を通過しました。通常の2画面幅で全65点を受信し、閉鎖の前・中・後を表示しました。ページを約180 ms止めると8点の送信を省略しましたが、保存した断面と49,828フレームのPCMはオフラインと一致しました。オフライン三次元、通常の実時間IPA、歌唱録画、実時間ビートボックスの回帰78項目も通過しました。[最後の再実行](runs/worklet-tract-3d-live-20261120-repeat/manifest.json)・[回帰の実行一覧](notes/worklet-tract-3d-live.md#実装と実測)・[描画が遅れた実行](runs/worklet-tract-3d-live-20261120-b/summary.json)

- 歌唱の録画は作業ディレクトリを変えた2実行で各23項目を通過しました。2拍の映像と音声の差は最大38.24 ms未満で、加工前PCMの91,200フレームがCLIとビット一致しました。録画先に値0の入力を保つと末尾の無音を収録できました。従来の実時間歌唱の回帰25項目も通過しました。[最後に確認した録画](runs/worklet-song-recording-20261120-final/manifest.json)・[別ディレクトリからの再実行](runs/worklet-song-recording-20261120-repeat/manifest.json)・[実時間歌唱の回帰](runs/worklet-live-song-recording-regression-20261120/manifest.json)・[終端が欠けた実行](runs/worklet-song-recording-20261120-c/summary.json)

- `ɑpɑ` の三次元表示は、末端の完全閉鎖と同じフレームでの唇端音響セルの面積0 cm²を確認しました。生の測定線と49,828 PCMフレームはブラウザとCLIで一致しました。作業ディレクトリを変えた2実行で各23項目を通過し、計測・画像・WASM・要約の52ファイルが一致しました。固定の三次元57項目、従来の二次元12項目、Rust試験39件、整形とClippyも通過しました。[最後の再実行](runs/worklet-tract-3d-dynamic-20261120-repeat/manifest.json)・[固定三次元の回帰](runs/worklet-tract-static-motion-regression-20261120/manifest.json)・[二次元の回帰](runs/worklet-tract-profile-motion-regression-20261120/manifest.json)

- 固定姿勢の三次元表示は、研究ディレクトリと `/tmp` の実ブラウザで各57項目を通過しました。計測ファイル15件、キャプチャ9枚、比較の要約が一致しました。従来の二次元断面表示の回帰12項目も通過しました。[最後に確認した実行](runs/worklet-tract-3d-20261120-repeat/manifest.json)・[二次元表示の回帰](runs/worklet-tract-profile-3d-regression-20261120/manifest.json)・[初回の応答待ちの失敗](runs/worklet-tract-3d-20261120-a/manifest.json)

- Web MIDIの手動発声は、研究ディレクトリと `/tmp` の実ブラウザで各16項目を通過しました。第1版ではゲート0の準備区間で微小な信号を観測し、第2版ではMIDI入力を省いたCLI対照とビット一致しました。手動操作とケース書き出しの回帰20項目、上流試験2件、Rust試験39件も通過しました。[最後に確認した実行](runs/worklet-midi-voice-20261120-repeat/manifest.json)・[手動発声の回帰](runs/worklet-manual-midi-regression-20261120/manifest.json)・[初回の判定](runs/worklet-midi-voice-20261120-a/summary.json)

- 鳴禽の `trill` の観測対照は、各18試行の2実行で各183項目を通過しました。18,048観測行、量子別呼び出し回数、ケース・PCM・CLI出力・WASMの39ファイルが一致しました。2.67 msの処理予算をp95で超えた試行は、64フレーム先頭0件・64フレーム末尾1件・128フレーム末尾2件でした。従来の `trill` の回帰18項目とRust試験39件も通過しました。[最後に確認した対照](runs/worklet-songbird-trill-observation-20261120-repeat/manifest.json)・[従来条件の回帰](runs/worklet-songbird-trill-observation-regression-20261120/manifest.json)・[初回の比較器の失敗](runs/worklet-songbird-trill-observation-20261120-a/manifest.json)

- ゾウの `squeak` は研究ディレクトリと `/tmp` の実ブラウザ計測で各136項目を通過しました。公式順序のPCMの最大絶対差は全体が `3.73×10⁻⁹`、末尾48,000フレームが `9.31×10⁻¹⁰` でした。第1版の欠測を保存し、第2版で96 kHzの観測点21,664を追加しました。`trumpet` の回帰142項目、Rustの整形・Clippy・試験39件、固定上流の試験7件も通過しました。[最後に確認した再実行](runs/worklet-elephant-squeak-20261120-repeat/manifest.json)・[trumpetの回帰](runs/worklet-elephant-trumpet-squeak-regression-20261120/manifest.json)・[第1版の欠測](runs/worklet-elephant-squeak-20261120-a/manifest.json)

- ゾウの `trumpet` は研究ディレクトリと `/tmp` の実ブラウザで各142項目を通過しました。固定上流とのPCM最大絶対差は公式順序の全体が `3.73×10⁻⁹`、trumpetの区間が `9.31×10⁻¹⁰` でした。[初回合格](runs/worklet-elephant-trumpet-20261120-b/summary.json)・[最後に確認した再実行](runs/worklet-elephant-trumpet-20261120-repeat/manifest.json)・[初回の試験ビルド失敗](runs/worklet-elephant-trumpet-20261120-a/manifest.json)

- ゾウの固定発声の回帰80項目と `rumble` の回帰68項目が通過し、観測行と対照を含む計測ファイルが変更前と一致しました。Rustの整形・Clippy・試験38件と固定上流の試験7件も通過しました。[固定発声の回帰](runs/worklet-elephant-fixed-trumpet-regression-20261120/manifest.json)・[rumbleの回帰](runs/worklet-elephant-rumble-trumpet-regression-20261120/manifest.json)

- ゾウの `rumble` は既存のCLI基準202項目と照合し、研究ディレクトリと `/tmp` のブラウザ比較で各68項目を通過しました。10,978観測行と対照を含む16ファイルが一致しました。ゾウの固定発声の回帰80項目、Rustの整形・Clippy・試験37件も通過しました。[CLI基準](runs/elephant-rumble-20261120-repeat/manifest.json)・[ブラウザ再実行](runs/worklet-elephant-rumble-20261120-repeat/manifest.json)・[固定発声の回帰](runs/worklet-elephant-fixed-rumble-regression-20261120/manifest.json)

- ゾウの固定発声は固定上流とCLIの188項目、研究ディレクトリと `/tmp` のブラウザ比較で各80項目を通過しました。54,939観測行と対照を含む計20ファイルが一致しました。共有Workletの変更後もアリゲーターの固定発声86項目とRustの整形・Clippy・試験36件が通過しました。[CLI基準](runs/elephant-fixed-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-elephant-fixed-20261120-repeat/manifest.json)・[アリゲーターの回帰](runs/worklet-alligator-fixed-elephant-regression-20261120/manifest.json)

- アリゲーターの `dance` は固定上流とCLIの316項目、研究ディレクトリと `/tmp` のブラウザ比較で各288項目を通過しました。156,832観測行と13ファイルが一致しました。比較処理の変更後も `hiss` の311項目、116,978観測行、13ファイルが一致しました。Rustの整形・Clippy・試験35件と固定上流の7件も通過しました。[CLI基準](runs/alligator-dance-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-alligator-dance-20261120-repeat/manifest.json)・[hissの回帰](runs/worklet-alligator-hiss-dance-regression-20261120/manifest.json)

- アリゲーターの `hiss` は固定上流とCLIの280項目、研究ディレクトリと `/tmp` のブラウザ比較で各311項目を通過しました。13ファイルと116,978観測行が一致しました。観測形式の拡張後も固定発声86項目と `growl` 285項目の回帰、Rustの整形・Clippy・試験34件が通過しました。[CLI基準](runs/alligator-hiss-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-alligator-hiss-20261120-repeat/manifest.json)・[固定発声の回帰](runs/worklet-alligator-fixed-hiss-regression-20261120/manifest.json)・[growlの回帰](runs/worklet-alligator-growl-hiss-regression-20261120/manifest.json)

- アリゲーターの `growl` は固定上流とCLIの238項目、研究ディレクトリと `/tmp` のブラウザ比較で各285項目を通過しました。対照を含む16ファイルと70,186観測行が一致しました。比較処理を共通化した後の `bellow` は234項目を通過し、13ファイルと71,383観測行が変更前と一致しました。Rustの整形・Clippy・試験33件も通過しました。[CLI基準](runs/alligator-growl-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-alligator-growl-20261120-final/manifest.json)・[bellowの回帰](runs/worklet-alligator-bellow-growl-regression-20261120-final/manifest.json)

- アリゲーターの `bellow` は固定上流とCLIの204項目、研究ディレクトリと `/tmp` のブラウザ比較で各234項目を通過しました。71,383観測行と13ファイルが一致し、初回の口腔乱流源登録にあった描画中の割り当て1回は初期化時の確保で解消しました。[固定上流とCLI](runs/alligator-bellow-before-worklet-1/manifest.json)・[割り当ての不合格](runs/worklet-alligator-bellow-20261120-allocation-diagnostic/manifest.json)・[ブラウザ初回合格](runs/worklet-alligator-bellow-20261120-b/manifest.json)・[ブラウザ再実行](runs/worklet-alligator-bellow-20261120-repeat/manifest.json)

- 共有気道の変更後もアリゲーターの固定発声86項目、アザラシの持続音44項目、ゾウの公式デモ末尾までの361項目が通過し、計測ファイルは変更前と一致しました。Rustの整形・Clippy・試験32件も通過しました。[アリゲーターの回帰](runs/worklet-alligator-fixed-bellow-regression-20261120/manifest.json)・[アザラシの回帰](runs/worklet-seal-sustain-bellow-regression-20261120/manifest.json)・[ゾウの回帰](runs/elephant-squeak-bellow-regression-20261120/manifest.json)

- アリゲーターの固定発声は固定上流とCLIの342項目、研究ディレクトリと `/tmp` のブラウザ比較で各86項目に合格しました。全観測行と21ファイルが一致し、アザラシの持続音44項目と鳴禽の切り替え22項目の回帰も確認しました。[固定上流とCLI](runs/alligator-fixed-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-alligator-fixed-20261120-repeat/manifest.json)・[アザラシの回帰](runs/worklet-seal-sustain-alligator-regression-20261120/manifest.json)・[鳴禽の回帰](runs/worklet-songbird-switch-alligator-regression-20261120/manifest.json)

- アザラシの `chug` は固定上流とCLIの第2版247項目、研究ディレクトリと `/tmp` のブラウザ比較で各88項目を通過しました。全観測行と13ファイルが再実行で一致し、`whistle` の101項目と持続音44項目の回帰、Rustの試験30件も通過しました。[固定上流](runs/seal-chug-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-seal-chug-20261120-repeat/manifest.json)・[whistleの回帰](runs/worklet-seal-whistle-chug-regression-20261120/manifest.json)・[持続音の回帰](runs/worklet-seal-sustain-chug-regression-20261120/manifest.json)

- アザラシの `whistle` は固定上流とCLIの219項目、研究ディレクトリと `/tmp` からのブラウザ比較で各101項目を通過しました。[固定上流](runs/seal-whistle-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-seal-whistle-20261120-repeat/manifest.json)

- アザラシの `zap` は固定上流とCLIの199項目、実時間ブラウザを研究ディレクトリと `/tmp` から実行して各72項目を通過しました。観測行と再実行ケース・WAV・CSV・WASM・対照の16ファイルが一致し、アザラシの `trill` 65項目、鳴禽の切り替え22項目の回帰も確認しました。[固定上流](runs/seal-zap-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-seal-zap-20261120-repeat/manifest.json)・[trillの回帰](runs/worklet-seal-trill-zap-regression-20261120/manifest.json)・[鳴禽の回帰](runs/worklet-songbird-switch-seal-zap-regression-20261120/manifest.json)

- アザラシの `trill` は固定上流とCLIの189項目、研究ディレクトリと `/tmp` からのブラウザ比較で各65項目を通過しました。全観測行とWASM・WAV・CSV・書き出しケース13点が再実行で一致しました。アザラシの持続音44項目と鳴禽の切り替え22項目の回帰を確認しました。[固定上流](runs/seal-trill-before-worklet-1/manifest.json)・[ブラウザ再実行](runs/worklet-seal-trill-20261120-repeat/manifest.json)・[持続音の回帰](runs/worklet-seal-sustain-trill-regression-20261120/manifest.json)・[鳴禽の回帰](runs/worklet-songbird-switch-seal-trill-regression-20261120/manifest.json)

- ウェッデルアザラシの持続音と停止は研究ディレクトリと `/tmp` のブラウザ比較で各44項目が通過しました。WAVなど9ファイルと全観測値は再実行で一致しました。鳴禽の切り替え22項目・`buzz` 20項目の回帰とCargo試験26件、整形、Clippyも通過しました。[初回](runs/worklet-seal-sustain-20261120-a/manifest.json)・[再実行](runs/worklet-seal-sustain-20261120-repeat/manifest.json)・[切り替えの回帰](runs/worklet-songbird-switch-seal-regression-20261120/manifest.json)・[buzzの回帰](runs/worklet-songbird-buzz-seal-regression-20261120/manifest.json)

- ゾウの `squeak` は研究ディレクトリと `/tmp` から各361項目を通過し、要約と計測ファイル34件が一致しました。`trumpet` の回帰359項目・34件も通過し、要約と計測ファイルが変更前と一致しました。Cargo試験23件、整形、Clippy、固定上流の既存試験13件を確認しました。[最初の判定](runs/elephant-squeak-20261120-a/summary.json)・[再実行](runs/elephant-squeak-20261120-repeat/manifest.json)・[trumpetの回帰](runs/elephant-trumpet-squeak-regression-20261120/manifest.json)

- ゾウの `trumpet` は研究ディレクトリと `/tmp` から各359項目を通過し、要約と計測ファイル34件が一致しました。ゾウの弁の回帰216項目・28件、`rumble` の回帰202項目・26件、アリゲーターの `dance` の回帰316項目・30件も通過し、要約と計測ファイルが変更前と一致しました。Cargo試験23件、整形、Clippy、固定上流の既存試験13件を確認しました。[最初の判定](runs/elephant-trumpet-20261120-a/summary.json)・[再実行](runs/elephant-trumpet-20261120-repeat/manifest.json)・[弁の回帰](runs/elephant-valve-trumpet-regression-20261120/manifest.json)・[rumbleの回帰](runs/elephant-rumble-trumpet-regression-20261120/manifest.json)・[danceの回帰](runs/alligator-dance-trumpet-regression-20261120/manifest.json)

- ゾウの入口弁を研究ディレクトリと `/tmp` から実行し、各216項目を通過しました。要約と計測ファイル28件が一致しました。`rumble` の回帰202項目・26件と固定発声の回帰188項目・33件も通過し、要約と計測ファイルが変更前と一致しました。Cargo試験23件、整形、Clippy、固定上流の既存試験13件を確認しました。[初回結果](runs/elephant-valve-20261120-a/summary.json)・[再実行](runs/elephant-valve-20261120-repeat/manifest.json)・[rumbleの回帰](runs/elephant-rumble-valve-regression-20261120/manifest.json)・[固定発声の回帰](runs/elephant-fixed-voice-valve-regression-20261120/manifest.json)

- ゾウの `rumble` を研究ディレクトリと `/tmp` から実行し、各202項目を通過しました。要約と観測ファイル26件が一致しました。ゾウの固定発声の回帰188項目・33件とアリゲーターの回帰316項目・30件も通過し、観測ファイルが変更前と一致しました。Cargo試験23件、整形、Clippy、固定上流の既存試験13件を確認しました。[初回結果](runs/elephant-rumble-20261120-a/summary.json)・[再実行](runs/elephant-rumble-20261120-repeat/manifest.json)・[固定発声の回帰](runs/elephant-fixed-voice-rumble-regression-20261120/manifest.json)・[アリゲーターの回帰](runs/alligator-dance-rumble-regression-20261120/manifest.json)

- ゾウの固定発声と放射経路を研究ディレクトリと `/tmp` から実行し、各188項目を通過しました。要約と観測ファイル33件が一致しました。共有気道を使うアリゲーターの回帰316項目・30件、アザラシの回帰163項目・36件も通過し、観測ファイルが変更前と一致しました。Cargo試験23件、整形、Clippy、固定上流の既存試験13件を確認しました。[最終結果](runs/elephant-fixed-voice-20261120-b/summary.json)・[再実行](runs/elephant-fixed-voice-20261120-repeat/manifest.json)・[アリゲーターの回帰](runs/alligator-dance-elephant-regression-20261120/manifest.json)・[アザラシの回帰](runs/seal-sustain-elephant-regression-20261120/manifest.json)

- アリゲーターの `dance` は研究ディレクトリと `/tmp` から各316項目を通過し、要約と観測ファイル30件が一致しました。直前の `hiss` の回帰280項目と観測ファイル25件も変更前後で一致しました。Cargo試験23件、整形、Clippy、固定上流の既存試験7件を確認しました。[初回の判定](runs/alligator-dance-20261120-a/summary.json)・[再実行](runs/alligator-dance-20261120-repeat/manifest.json)・[hissの回帰](runs/alligator-hiss-dance-regression-20261120/manifest.json)

- アリゲーターの `hiss` は研究ディレクトリと `/tmp` で各280項目を通過し、要約と観測ファイル25件が一致しました。`growl` の回帰238項目と観測ファイル23件も変更前後で一致しました。Cargo試験23件、Clippy、固定上流の既存試験7件を確認しました。[初回の判定](runs/alligator-hiss-20261120-a/summary.json)・[再実行](runs/alligator-hiss-20261120-repeat/manifest.json)・[growlの回帰](runs/alligator-growl-hiss-regression-20261120/manifest.json)
- アリゲーターの `growl` は研究ディレクトリと `/tmp` で各238項目を通過し、要約と観測ファイル23件が一致しました。`bellow` の回帰204項目・観測ファイル23件も変更前後で一致しました。Cargo試験23件、Clippy、固定上流の既存試験7件を確認しました。[初回の判定](runs/alligator-growl-20261120-a/summary.json)・[再実行](runs/alligator-growl-20261120-repeat/manifest.json)・[bellowの回帰](runs/alligator-bellow-growl-regression-20261120/manifest.json)
- アリゲーターの `bellow` は研究ディレクトリと `/tmp` で各204項目を通過し、要約と観測ファイル23件が一致しました。固定気道の回帰も342項目と観測ファイル49件が一致しました。Cargo試験23件、Clippy、固定上流の既存試験7件を確認しました。[第1回の結果](runs/alligator-bellow-20261120-a/summary.json)・[再実行の要約](runs/alligator-bellow-20261120-repeat/summary.json)・[固定気道の回帰](runs/alligator-fixed-bellow-regression-20261120/manifest.json)
- アリゲーターの固定気道は研究ディレクトリと `/tmp` で各342項目が通過しました。要約と観測ファイル49件が一致しました。共有化後もアザラシの気道159項目・25ファイル、公式順序247項目・23ファイルが一致しました。Cargo試験23件、Clippy、この環境で有効な上流試験12件を確認しました。[第1版の判定](runs/alligator-fixed-voice-20261120-c/summary.json)・[再実行の要約](runs/alligator-fixed-voice-20261120-repeat/summary.json)・[アザラシの気道の回帰](runs/seal-airway-mammal-regression-20261120/manifest.json)・[アザラシの公式順序の回帰](runs/seal-chug-alligator-final-regression-20261120/manifest.json)
- アザラシの `chug` は、CSVの列順を修正し、独立肺圧の第2版で呼気位相差の影響に上界を設けました。既存の数値許容差を維持し、研究ディレクトリと `/tmp` で各247項目を通過しました。要約と観測ファイル23件が一致し、`whistle` の変更前後も219項目と23ファイルが一致しました。Cargo試験23件、Clippy、固定上流の既存試験7件も通過しました。[列順の失敗](runs/seal-chug-20261120-a/manifest.json)・[第1版の判定](runs/seal-chug-20261120-b/summary.json)・[再実行の要約](runs/seal-chug-20261120-repeat/summary.json)・[whistleの回帰](runs/seal-whistle-chug-v2-regression-20261120/manifest.json)
- アザラシの `whistle` は集計結果のJSON化を修正後、研究ディレクトリと `/tmp` で各219項目を通過しました。初回から観測ファイル23件が一致しました。公式CLIの `whistle` 区間72,000フレームで最大PCM差は `8.88×10⁻¹⁶`、全条件の最大差は `5.68×10⁻¹⁴` でした。`zap` の回帰199項目と23ファイルは変更前と一致しました。Cargo試験23件と上流試験7件も通過しました。[初回の失敗](runs/seal-whistle-20261120-a/manifest.json)・[再実行結果](runs/seal-whistle-20261120-repeat/summary.json)・[zapの回帰](runs/seal-zap-whistle-regression-20261120/manifest.json)
- アザラシの `zap` は研究ディレクトリと `/tmp` で各199項目を通過しました。要約と観測ファイル23件が一致しました。380,160フレーム中、上流とのPCM差は `trill` の既知の2フレームと96 kHzの `zap` の減衰中の1フレームで、最大 `1.78×10⁻¹⁵` でした。`trill` の回帰189項目と23ファイルも変更前と一致しました。Cargo試験23件と上流試験7件が通過しました。[初回](runs/seal-zap-20261120-a/manifest.json)・[再実行結果](runs/seal-zap-20261120-repeat/summary.json)・[trillの回帰](runs/seal-trill-zap-regression-20261120/manifest.json)
- アザラシの `trill` は研究ディレクトリと `/tmp` で各189項目を通過しました。計350,000フレームで上流とのPCM差は自然終了後の2フレーム、最大 `2.78×10⁻¹⁷`。要約とケース・CSV・WAVなど23ファイルが再実行で一致しました。持続音と停止の回帰163項目も通過し、変更前後で36ファイルが一致しました。[初回](runs/seal-trill-20261120-a/manifest.json)・[再実行の要約](runs/seal-trill-20261120-repeat/summary.json)・[持続音の回帰](runs/seal-sustain-trill-regression-20261120/manifest.json)
- アザラシの持続音と停止は研究ディレクトリと `/tmp` で各163項目を通過しました。要約とWAV・CSV・設定など36ファイルが一致しました。5条件の194,089フレーム中、上流との差は96 kHzと増幅条件の減衰中の計21フレームで、最大 `7.11×10⁻¹⁵` でした。気道の回帰159項目と観測25ファイルも変更前と一致しました。候補のCargo試験23件と上流の既存試験7件が通過しました。[初回](runs/seal-sustain-20261120-a/manifest.json)・[再実行](runs/seal-sustain-20261120-repeat/summary.json)・[気道の回帰](runs/seal-airway-pcm-regression-20261120/manifest.json)
- アザラシの気道と声門は研究ディレクトリと `/tmp` で各159項目を通過し、要約およびケース・設定・時系列25ファイルのSHA-256が一致しました。声門流量の最大絶対差は `9.09×10⁻¹³ cm³/s`。変更前後で固定肺圧の128項目と観測ファイル29件が一致しました。Cargo試験23件とClippyも通過しました。[初回](runs/seal-airway-20261120-a/manifest.json)・[再実行の要約](runs/seal-airway-20261120-repeat/summary.json)・[固定肺圧の回帰](runs/seal-breath-airway-regression-20261120/manifest.json)
- アザラシの固定肺圧は、独立積分の丸め誤差を補償加算で抑えた後、研究ディレクトリと `/tmp` で各128項目を通過しました。合否要約が一致し、ケース・設定・CSV・上流WAVの計29ファイルは初回を含めSHA-256が一致しました。候補のCargo試験23件と固定上流の既存試験7件も通過しました。[初回の判定](runs/seal-breath-20261120-a/summary.json)・[修正後の判定](runs/seal-breath-20261120-b/summary.json)・[再実行の記録](runs/seal-breath-20261120-repeat/manifest.json)
- 鳴禽の3コールと切り替えは、呼気の初回の立ち上がりを式で区別した第2版で各452項目を通過しました。WAV・CSV・キー定義など37ファイルのハッシュは初回、第2版、`/tmp` からの再実行で一致しました。上流CLI全体の344,994フレームはPCMがビット一致し、96 kHzの単独 `buzz` は減衰区間の1フレームに `5.56×10⁻²²` の差がありました。`flute` の回帰346項目も通過しました。[初回の判定](runs/songbird-calls-20261120-a/summary.json)・[第2版](runs/songbird-calls-20261120-b/manifest.json)・[再実行の判定](runs/songbird-calls-20261120-repeat/summary.json)・[既存コールの回帰](runs/songbird-calls-flute-regression-20261120/summary.json)
- `flute` は集計の型変換を修正後、研究ディレクトリと `/tmp` で各346項目を通過しました。WAV、CSV、設定、キー定義の30ファイルが再実行でハッシュ一致しました。内部放射の最大絶対差は `1.30×10⁻⁸ cm³/s²`、PCMは全フレームでビット一致。持続音の回帰298項目も通過しました。[初回の失敗](runs/songbird-flute-20261120-a/manifest.json)・[修正後](runs/songbird-flute-20261120-b/manifest.json)・[再実行の判定](runs/songbird-flute-20261120-repeat/summary.json)・[持続音の回帰](runs/songbird-flute-sustain-regression-20261120/summary.json)
- 鳴禽の持続音は研究ディレクトリと `/tmp` で各298項目を通過しました。固定上流との内部放射の最大絶対差は `1.50×10⁻⁸ cm³/s²`、PCMは全フレームでビット一致。WAV、CSV、設定等の36ファイルがハッシュ一致しました。既存の鳴禽の気道の回帰232項目と共有WAV出力の回帰12項目も通過しました。[初回](runs/songbird-sustain-pcm-20261120-a/manifest.json)・[再実行と数値](runs/songbird-sustain-pcm-20261120-repeat/summary.json)・[気道の回帰](runs/songbird-sustain-airway-regression-20261120/summary.json)・[PCM出力の回帰](runs/songbird-sustain-pcm-regression-20261120/summary.json)
- 左右の鳴管と気道は研究ディレクトリと `/tmp` から各232項目を通過しました。計181,824内部サンプルの開口とポート面積が固定上流と一致し、放射流量の時間微分の最大絶対差は `1.23×10⁻⁸ cm³/s²`。出力CSVとケース・設定JSONの24ファイルが再実行でハッシュ一致しました。片側の鳴管音源の回帰は71項目を通過しました。[初回](runs/songbird-airway-20261120-a/manifest.json)・[再実行と数値](runs/songbird-airway-20261120-repeat/summary.json)・[回帰](runs/songbird-airway-syrinx-regression-20261120/summary.json)
- 片側の鳴管音源は候補CLIのコンパイルエラーを修正後、研究ディレクトリと `/tmp` から各71項目を通過しました。固定上流との開口率差は計127,056サンプルで0。出力CSVと上流WAVの17ファイルのハッシュも再実行で一致しました。先行するビルドで前回の声門閉鎖音のネイティブ回帰86項目を確認しました。[初回中断](runs/songbird-syrinx-20261120-a/manifest.json)・[修正後](runs/songbird-syrinx-20261120-b/manifest.json)・[再実行と数値](runs/songbird-syrinx-20261120-repeat/summary.json)・[回帰](runs/syrinx-glottal-stop-regression-20261120/summary.json)
- 声門閉鎖音は研究ディレクトリと `/tmp` で各98項目を通過しました。固定上流との加工前PCMの最大絶対差は `3.73×10⁻⁹`。実ブラウザの278,400サンプルはCLIと保存ケースの再演でビット一致し、2回の時系列・波形・WASMの56ファイルがハッシュ一致しました。既存の声門摩擦音 /h/ の回帰は7項目を通過しました。[初回](runs/glottal-stop-20261120-a/manifest.json)・[再実行](runs/glottal-stop-20261120-repeat/manifest.json)・[数値と判定](runs/glottal-stop-20261120-repeat/summary.json)・[回帰](runs/glottal-stop-frication-regression-20261120/summary.json)
- そり舌接近音は研究ディレクトリと `/tmp` で各104項目を通過しました。固定上流との加工前PCMの最大絶対差は `1.16×10⁻¹⁰`。実ブラウザの計182,400サンプルはCLIと保存ケースの再演でビット一致し、時系列、PCM、WASMの63ファイルのハッシュも再実行で一致しました。既存の破擦音と鼻音韻尾のメリスマの回帰は10項目を通過しました。[初回](runs/retroflex-approximant-20261120-a/manifest.json)・[再実行](runs/retroflex-approximant-20261120-repeat/manifest.json)・[数値と判定](runs/retroflex-approximant-20261120-repeat/summary.json)・[回帰](runs/retroflex-approximant-regression-20261120/summary.json)
- そり舌破擦音は研究ディレクトリと `/tmp` で各105項目を通過しました。固定上流との加工前PCMの最大絶対差は `9.31×10⁻¹⁰`。ブラウザのPCM 91,200サンプルはCLIと保存ケースの再演でビット一致し、時系列、PCM、WASMの67ファイルのハッシュも再実行で一致しました。既存 /ts/・/ʂ/ の歌唱回帰は8項目を通過しました。[初回](runs/retroflex-affricate-20261120-a/manifest.json)・[再実行](runs/retroflex-affricate-20261120-repeat/manifest.json)・[数値と判定](runs/retroflex-affricate-20261120-repeat/summary.json)・[回帰](runs/retroflex-affricate-regression-20261120/summary.json)
- そり舌摩擦音は研究ディレクトリと `/tmp` で各61項目を通過しました。固定上流との加工前PCMの最大絶対差は `1.16×10⁻¹⁰`。ブラウザの91,200サンプルはCLIと保存ケースの再演でビット一致し、2回の時系列、PCM、WASMの39ファイルのハッシュも一致しました。初回の計測器エラーを保存し、既存 /s/ の回帰7項目を確認しました。[初回中断](runs/retroflex-fricative-20261120-a/manifest.json)・[修正後](runs/retroflex-fricative-20261120-b/manifest.json)・[再実行](runs/retroflex-fricative-20261120-repeat/manifest.json)・[数値と判定](runs/retroflex-fricative-20261120-repeat/summary.json)・[回帰](runs/sibilant-s-retroflex-regression-20261120/summary.json)
- 歯茎破擦音は研究ディレクトリと `/tmp` で各69項目を通過しました。固定上流との加工前PCMの最大絶対差は `1.86×10⁻⁹`。ブラウザの加工前PCM 91,200サンプルはCLIと保存ケースの再演でビット一致しました。再実行では時系列、PCM、WASMの53ファイルのハッシュが一致しました。既存の歯茎硬口蓋破擦音のCLI回帰は36項目を通過しました。[初回](runs/alveolar-affricate-20261120-a/manifest.json)・[再実行](runs/alveolar-affricate-20261120-repeat/manifest.json)・[数値と判定](runs/alveolar-affricate-20261120-repeat/summary.json)・[回帰](runs/alveolopalatal-affricates-regression-20261120-ts/summary.json)
- 鼻音韻尾の第2版は研究ディレクトリと `/tmp` の9譜例で各152項目を通過しました。「班」と「东」の169,440サンプルが実ブラウザ・CLI・保存ケースの再演でビット一致し、固定上流とのPCM最大絶対差は `4.66×10⁻¹⁰` でした。[第1版の結果](runs/mandarin-nasal-rhymes-20261120-a/summary.json)・[第2版](runs/mandarin-nasal-rhymes-20261120-b/manifest.json)・[再実行](runs/mandarin-nasal-rhymes-20261120-repeat/manifest.json)・[従来の鼻音の回帰](runs/lingual-nasals-20261120-nasal-rhyme-regression/summary.json)
- 中国語歌詞の第2版は研究ディレクトリと `/tmp` で各95項目を通過しました。4譜例で固定上流との最大PCM差は `2.91×10⁻¹¹`。漢字の2譜例は計254,400サンプルがブラウザとCLI・保存ケースの再演でビット一致しました。[初回の判定](runs/mandarin-lyrics-20261120-a/summary.json)・[第2版の記録](runs/mandarin-lyrics-20261120-b/manifest.json)・[再実行](runs/mandarin-lyrics-20261120-repeat/manifest.json)
- 後部歯茎破擦音 /tʃ/ は研究ディレクトリと `/tmp` の各58項目を通過しました。固定上流と加工前PCMの最大絶対差は `9.31×10⁻¹⁰`。ロシア語デモの454,629サンプルは実ブラウザ・CLI・保存ケースの再演でビット一致し、内部状態とWAVを含む68ファイルのハッシュも一致しました。[初回](runs/postalveolar-affricate-20261120-a/manifest.json)・[再実行](runs/postalveolar-affricate-20261120-repeat/manifest.json)・[韓国語の発話・歌唱の回帰](runs/alveolopalatal-affricates-20261120-postalveolar-regression/summary.json)
- 軟口蓋摩擦音 /x/ の第2版は研究ディレクトリと `/tmp` で各93項目を通過しました。固定上流とのPCM最大絶対差は `4.66×10⁻¹⁰`。「ти́хо」の91,200サンプルは実ブラウザ・CLI・保存ケースの再演でビット一致し、両実行の95出力のうち内部系列やWAVを含む87ファイルがハッシュ一致しました。[第1版の結果](runs/velar-fricative-20261120-a/summary.json)・[第2版](runs/velar-fricative-20261120-b/manifest.json)・[再実行](runs/velar-fricative-20261120-repeat/manifest.json)
- 唇歯摩擦音 /f v/ の第2版は研究ディレクトリと `/tmp` で各116項目を通過しました。固定上流とのPCM最大絶対差は `4.66×10⁻¹⁰`。「ве́тер」の91,200サンプルは実ブラウザ・CLI・保存ケースの再演でビット一致しました。[第1版の判定](runs/labiodental-fricatives-20261120-b/summary.json)・[第2版の再実行](runs/labiodental-fricatives-20261120-repeat/manifest.json)
- ロシア語歌詞で23入力・81音節と2譜例を照合し、研究ディレクトリと `/tmp` の実行は各75項目を通過しました。固定上流とのPCM最大絶対差は `1.46×10⁻¹¹`。2譜例の計278,400サンプルは実ブラウザ・CLI・保存ケースの再演でビット一致しました。[初回](runs/russian-lyrics-20261120-a/manifest.json)・[再実行](runs/russian-lyrics-20261120-repeat/manifest.json)
- 歯茎の弾き音 /ɾ/ は第2版を研究ディレクトリと `/tmp` から実行し、各84項目を通過しました。固定上流とのPCM最大絶対差は `1.49×10⁻⁸`。「싫어」の91,200サンプルは実ブラウザ、CLI、保存ケースの再演でビット一致しました。両実行の97ファイルがハッシュ一致しました。[第1版の予測不一致](runs/alveolar-tap-20261120-a/manifest.json)・[第2版の再実行](runs/alveolar-tap-20261120-repeat/manifest.json)
- /tɕ dʑ/ の発話と「아주 자 차 짜」の歌唱は、研究ディレクトリと `/tmp` の実行で各42項目を通過しました。固定上流とのPCMの最大絶対差は `9.31×10⁻¹⁰`。歌唱163,200サンプルは実ブラウザ・CLI・保存ケースの再演でビット一致し、両実行のケースや内部系列など57ファイルがハッシュ一致しました。[初回](runs/alveolopalatal-affricates-20261120-a/manifest.json)・[再実行](runs/alveolopalatal-affricates-20261120-repeat/manifest.json)
- /ɕ ʑ/ の発話と「시야」の歌唱は、研究ディレクトリと `/tmp` から各65項目を通過しました。固定上流とのPCM最大絶対差は `1.16×10⁻¹⁰`。実時間の歌唱91,200サンプルはCLI・保存ケースの再演とビット一致しました。両実行の77ファイルがハッシュ一致し、ブラウザの開始・停止時刻など実時間の記録には差が出ました。[初回](runs/alveolopalatal-fricatives-20261120-a/manifest.json)・[再実行](runs/alveolopalatal-fricatives-20261120-repeat/manifest.json)
- ブラウザの体型別歌唱は、計測器の修正後と `/tmp` からの再実行で112項目を通過しました。4体型の両モードでPCM 129,600フレームと2,025点の内部状態10系列がCLIと一致し、固定上流とのPCM差は最大 `9.31×10⁻¹⁰` でした。38ファイルのハッシュが一致し、実時間の記録5件では時計に依存する値に差が出ました。[再実行](runs/worklet-bodysong-20261120-repeat/manifest.json)・[欠測と比較結果](notes/worklet-song-body.md)
- ブラウザの体型別IPA発話は初回と `/tmp` からの再実行で136項目を通過しました。オフライン・実時間の加工前PCMと保存ケースのCLI結果が全4体型で一致し、8,404点の内部状態12系列も同値でした。上流とのPCM差は最大 `4.66×10⁻¹⁰`。再実行では39ファイルが一致し、実時間観測JSON4件の差は開始時刻・実行時の処理時間などの記録に現れました。[再実行](runs/worklet-bodyipa-20261120-repeat/manifest.json)・[比較結果](notes/worklet-ipa-body.md)
- ブラウザの体型別英語発話は計測器の修正後と `/tmp` からの再実行で86項目を通過しました。38ファイルのSHA-256が一致し、5条件のPCM 118,748フレームと内部状態10系列はCLIに一致しました。上流とのPCM差は最大 `3.73×10⁻⁹`。32フレーム間隔の観測では閉鎖検出が最大0.583 ms遅くなりました。[再実行](runs/worklet-bodyenglish-20261120-repeat/manifest.json)・[初回の停止理由と計測結果](notes/worklet-english-body.md)
- 体型別の英語発話は計測第2版と `/tmp` からの再実行で70項目を通過し、計画・波形・観測・要約を含む56ファイルが一致しました。上流とのPCM差は最大 `3.73×10⁻⁹`。初回は最小断面セル番号の相違で5項目が不合格となり、選ばれた互いのセルの面積差は最大 `1.36×10⁻¹⁸ cm²`、全セルの開閉判定は同じでした。既存の成人男性CLI・Workletの英語ケースも通過しました。[再実行](runs/bodyenglish-20261120-repeat/manifest.json)・[結果](runs/bodyenglish-20261120-repeat/summary.json)・[初回と回帰](notes/human-body-english.md)
- 体型別歌唱は初回と `/tmp` からの再実行で41項目を満たし、条件・計画・観測・PCM・要約の41ファイルが一致しました。第2・第3音への音高移行は4体型で頭子音区間内にあり、上流とのPCM差は最大 `9.31×10⁻¹⁰`。成人男性の二音の歌唱とブラウザ歌唱も回帰を通過しました。[結果](runs/bodysong-20261120-repeat/summary.json)・[再実行](runs/bodysong-20261120-repeat/manifest.json)・[回帰](notes/human-body-song.md#実装と結果)
- 体型別IPA発話は初回と `/tmp` からの再実行で46項目を満たし、入力・計画・観測・PCM・要約の41ファイルが一致しました。音素区間は4条件で一致し、上流とのPCM差は最大 `4.66×10⁻¹⁰` でした。成人男性の既存 /s/ とブラウザIPAの回帰も通過しました。[結果](runs/bodyipa-20261120-repeat/summary.json)・[再実行](runs/bodyipa-20261120-repeat/manifest.json)・[回帰](notes/human-body-ipa.md#実装と照合)
- 体型別の可動声道は初回通過と `/tmp` からの再実行がともに70項目を満たし、条件・観測・PCM・要約の83ファイルが一致しました。子どもの舌先接触では104回再計算しました。有声PCMと上流の差は最大 `1.11×10⁻¹⁶`。既存の可動声道、有声レンダー、ブラウザのIPAの回帰も通過しました。[結果](runs/bodymotion-20261120-repeat/summary.json)・[再実行](runs/bodymotion-20261120-repeat/manifest.json)・[初回の不合格と回帰](notes/human-body-tract-motion.md)
- 体型ごとの較正済み母音は、初回通過と `/tmp` からの再実行がともに458項目を満たし、条件・観測・PCM・要約の362ファイルが一致しました。固定 /a/ のPCMの上流との差は最大 `5.82×10⁻¹¹`。成人男性と子どもの中間は、F1が789.19 Hz、F2が1705.95 Hzでした。既存のジェスチャーと固定発声、ブラウザの成人男性IPAも回帰を通過しました。[結果](runs/calbody-20261120-repeat/summary.json)・[再実行](runs/calbody-20261120-repeat/manifest.json)・[回帰と初回の中断記録](notes/human-body-calibrated-vowels.md)
- 体型別の固定発声は初回通過と `/tmp` からの再実行で全60項目を満たし、ケース・観測・PCM・要約の56ファイルがバイト一致しました。上流とのPCMも6条件すべてでバイト一致し、110 Hzに揃えた女性の声門は男性より0.1296周期長く開きました。旧成人男性の固定発声とWorkletの回帰、ワークスペーステスト、Clippyも通過しました。[計測結果](runs/bodyvoice-20261120-repeat/summary.json)・[再実行](runs/bodyvoice-20261120-repeat/manifest.json)・[読解・回帰・初回の中断記録](notes/human-body-fixed-voice.md)
- 体型別の固定気道は初回と `/tmp` からの再実行で全100項目を通過し、観測・入力・要約など106ファイルがバイト一致しました。同じ /ɑ/ 姿勢で第1共鳴は成人男性730.71 Hz、子ども1,001.20 Hzでした。成人男性のインパルス・伝達関数、体型の幾何、ブラウザの固定発声も回帰を通過しました。[結果](runs/airbody-20261120-repeat/summary.json)・[再実行](runs/airbody-20261120-repeat/manifest.json)・[回帰](notes/human-body-airway.md#実装と結果)
- 体型補間は初回と `/tmp` からの再実行がともに130項目を通過し、177ファイルがバイト一致しました。固定上流との輪郭座標差は最大 `3.55×10⁻¹⁵ cm`、セルの面積差は最大 `1.73×10⁻¹⁴ cm²`。成人男性の中立輪郭、セル、ブラウザの固定ビートも回帰を通過しました。[初回](runs/body-20261120-a/summary.json)・[再実行](runs/body-20261120-repeat/manifest.json)・[回帰の記録](notes/human-body-geometry.md#実装と結果)
- 実時間のビート操作は2回とも13項目を通過しました。実測した5操作をCLIで再実行し、48 kHzの192,000サンプルと3,000観測点の再生位置・音源状態が一致しました。1,500量子は連続、処理時間p99は両回2 ms。処理予算超過は3件と1件で、初回の要約保存失敗も残しました。[初回の失敗記録](runs/worklet-live-beatbox-20261120-a/manifest.json)・[最初の通過](runs/worklet-live-beatbox-20261120-b/summary.json)・[再実行](runs/worklet-live-beatbox-20261120-repeat/summary.json)
- オフラインビート、実時間歌唱、CLIのビート操作も回帰を通過しました。以前の通過実行とPCMおよび対応する観測値が一致しました。[回帰結果](notes/worklet-live-beatbox.md#実装と計測)
- ブラウザの固定ビートパターンは2回とも17項目を通過しました。観測間隔64・77フレームで62,400サンプルのPCMがCLIとビット一致し、休符を含む再生位置も観測点すべてで一致しました。初回の選択欄の検出失敗も保存しています。[初回失敗](runs/worklet-beatbox-20261120-a/manifest.json)・[修正後](runs/worklet-beatbox-20261120-b/summary.json)・[再実行](runs/worklet-beatbox-20261120-repeat/summary.json)
- 別ディレクトリからの再実行ではWAV・観測・要約など18ファイルがバイト一致しました。CLIのテンポ変更とブラウザの固定母音・IPAも回帰を通過し、WAVと観測は対応する基準と一致しました。[回帰と比較元の記録](notes/worklet-beatbox-pattern.md#結果)
- ビートのテンポ変更と停止・再開は、48 kHzの88,800フレームで初回と `/tmp` からの再実行が各18項目を通過しました。停止で856.25 msの打音が取り消され、呼気の減衰は独立計算と一致しました。固定上流とのPCM最大差は `5.82×10⁻¹¹`。ホスト幅77・128・4,096のPCMは各実装内でバイト一致しました。[初回](runs/transport-20261120-1/summary.json)・[再実行](runs/transport-20261120-2/manifest.json)
- テンポ変更ケースの初回と再実行で15ファイル、固定テンポの音高付き `m`、スウィング、混在パターンの回帰で各12ファイルがバイト一致しました。候補のRust整形・Clippy・ワークスペーステストと固定上流の `beatbox`・`engine` が通過しました。[回帰と比較元の記録](notes/beatbox-transport.md#実装と結果)
- `m` 単発は194.417 msで閉唇し、247.354 msで振動ゲートが0.1に達しました。PCMから得た音高はMIDI 40で82.474 Hz、パターンのMIDI 43・47で97.959・123.711 Hz。保持時間の下限60 msと、休符込みの0.375・0.625秒から決まる保持終端を照合しました。PCMの固定上流との差は最大 `7.28×10⁻¹²` 以下でした。[読解と結果](notes/beatbox-hum.md)・[単発](runs/hum-20261120-single-a/manifest.json)・[パターン](runs/hum-20261120-pattern-a/manifest.json)
- `m` は `/tmp` からの再実行でも単発15項目とパターン16項目が通過し、計28ファイルがバイト一致しました。クラッシュの単発・下限・上限条件の回帰も各7ファイルが一致しました。[単発の再実行](runs/hum-20261120-single-repeat/manifest.json)・[パターンの再実行](runs/hum-20261120-pattern-repeat/manifest.json)・[回帰の記録](notes/beatbox-hum.md#結果)
- `kch` の単発は242.688 msで閉鎖を解除し、最初の狭窄乱流源23番は34番を経て持続部の28番へ移りました。下限と上限に達するパターンの摩擦と呼気の保持終端は353・553 ms。固定上流とのPCM差は最大 `2.92×10⁻¹¹` 以下でした。成人男性の較正値を取り込む前の初回不合格も保存しました。[読解と結果](notes/beatbox-crash.md)・[単発](runs/crash-20261120-single-b/manifest.json)・[下限](runs/crash-20261120-short-b/manifest.json)・[上限](runs/crash-20261120-long-b/manifest.json)
- `kch` は `/tmp` からの再実行でも単発13項目とパターン各15項目が通過し、波形、時系列、設定、要約など計35ファイルがバイト一致しました。単発 `K`、単発 `^K`、`P!` パターンの回帰も各7ファイルが一致しました。[単発の再実行](runs/crash-20261120-single-repeat/manifest.json)・[下限の再実行](runs/crash-20261120-short-repeat/manifest.json)・[上限の再実行](runs/crash-20261120-long-repeat/manifest.json)・[回帰の記録](notes/beatbox-crash.md#結果)
- `P!` は唇と奥舌を約120 ms閉じ、単発の空洞圧は−24,445 dyn/cm²に達しました。その時点の口端圧はほぼゼロで、開唇後の口端流量は−366.58 cm³/s。独立計算で顎と舌背、閉口中の口端圧と放射流量の減衰を照合しました。固定上流とのPCM差は最大 `7.28×10⁻¹²` 以下でした。[単発](runs/lip-pop-20261120-single-a/manifest.json)・[パターン](runs/lip-pop-20261120-pattern-a/manifest.json)
- `P!` は `/tmp` からの再実行でも単発13項目、パターン16項目が通過し、設定、PCM、時系列、要約など計23ファイルがバイト一致しました。舌打ち音は実装前後で単発・パターンの各7ファイルが一致しました。[単発の再実行](runs/lip-pop-20261120-single-repeat/manifest.json)・[パターンの再実行](runs/lip-pop-20261120-pattern-repeat/manifest.json)・[舌打ち単発の回帰](runs/lip-pop-20261120-click-after/manifest.json)・[舌打ちパターンの回帰](runs/lip-pop-20261120-pattern-after/manifest.json)
- 舌打ち音 `!` の単発とパターンで二重閉鎖が109.667 ms続き、閉鎖内の空洞体積は最大で約3.922 cm³に達しました。空洞圧は舌先の開口1出力フレーム前に最小となり、奥舌はその後も44.021 ms閉じていました。固定上流との差はPCM最大 `5.83×10⁻¹¹` 以下で、初回に見つかった実質ゼロの閉鎖セル番号の差と改訂判定も保存しました。[初回](runs/click-20261120-single-a/summary.json)・[単発](runs/click-20261120-single-b/manifest.json)・[パターン](runs/click-20261120-pattern-b/manifest.json)
- `!` は `/tmp` からの再実行でも単発13項目、パターン16項目が通過し、設定、PCM、時系列、要約など計23ファイルがバイト一致しました。吸気スネアの単発とパターンは舌打ちの実装前後で各7ファイルが一致しました。[舌打ち単発の再実行](runs/click-20261120-single-repeat/manifest.json)・[舌打ちパターンの再実行](runs/click-20261120-pattern-repeat/manifest.json)・[吸気スネア単発の回帰](runs/click-20261120-single-after/manifest.json)・[吸気スネアパターンの回帰](runs/click-20261120-pattern-after/manifest.json)
- 吸気スネア `^K` の単発の閉鎖が約46.85 ms続き、閉鎖中の肺境界圧は−11,007 dyn/cm²に達しました。開口後の狭窄枝流量は−1,785 cm³/sまで下がり、摩擦中の乱流圧注入を後方枝で観測しました。固定上流とのPCM差は単発で `1.87×10⁻⁹` 以下、パターンで `7.28×10⁻¹²` 以下でした。初回の採取時点のずれ、末尾ゲートの未達、並行実行時の中断と対処を記録しました。[読解と結果](notes/beatbox-inward-snare.md)・[単発](runs/inward-20261120-single-c/manifest.json)・[パターン](runs/inward-20261120-pattern-c/manifest.json)
- `^K` は `/tmp` からの再実行でも単発13項目、パターン16項目が通過し、設定、波形、時系列、要約など計23ファイルがバイト一致しました。上流の `beatbox`・`engine` と候補のRust整形・Clippy・ワークスペーステストが通過しました。[単発の再実行](runs/inward-20261120-single-repeat/manifest.json)・[パターンの再実行](runs/inward-20261120-pattern-repeat/manifest.json)
- `K` 単発の奥舌閉鎖が66.854 ms続き、閉鎖中の声門上圧は29,250 dyn/cm²に達しました。振動ゲートが最初に10⁻⁶を超えたのは閉鎖より約12 ms早い167.708 msです。初回は振動ゲートを全区間で10⁻⁶以下とした条件で不合格。初回を保存し、改訂後は単発とパターンの両方で声門面積・PCMを照合しました。固定上流との差はPCM最大 `5.83×10⁻¹¹` 以下でした。[旧単発](runs/rim-20261120-single-a/summary.json)・[旧パターン](runs/rim-20261120-pattern-a/summary.json)・[単発](runs/rim-20261120-single-b/manifest.json)・[パターン](runs/rim-20261120-pattern-b/manifest.json)
- `K` の単発とパターンは `/tmp` から再実行し、両方の設定、時系列、PCM、要約など計23ファイルがバイト一致しました。上流の `beatbox`・`engine`、候補のRust整形・Clippy・ワークスペーステストも通過しました。単発 `B`・`Pf` と `Pf` パターンのPCMは声門の揺らぎを有効にする前の回帰結果と一致しました。[単発の再実行](runs/rim-20261120-single-repeat/manifest.json)・[パターンの再実行](runs/rim-20261120-pattern-repeat/manifest.json)・[既存条件の回帰](notes/beatbox-rimshot-k.md#実装と検証)
- `Pf` の単発第2版とパターンは再実行も各14項目を通過しました。単発の再開口は238.688 ms、閉鎖中の声門上圧の上昇は12,285 dyn/cm²。固定上流とのPCM最大差は `1.46×10⁻¹¹` でした。初回は観測窓が232 msで閉鎖中に終わったので、初回結果を保存し、第2版で270 msまで延長しました。[初回](runs/pf-20261120-single-a/summary.json)・[単発の再実行](runs/pf-20261120-single-root/manifest.json)・[パターンの再実行](runs/pf-20261120-pattern-root/manifest.json)
- `tss` は3条件の再実行で各要約・時系列・WAVがバイト一致しました。240 BPMの短い条件と7休符の条件で摩擦終端は305 msと465 ms、ゲートが0.1を下回った時刻は409.354 msと569.354 ms。固定上流とのPCM最大差は `5.82×10⁻¹¹`。初回のパターン入力のエラーも保存しました。[単発](runs/open-hat-20261120-single-root/manifest.json)・[短い条件](runs/open-hat-20261120-short-root/manifest.json)・[長い条件](runs/open-hat-20261120-long-root/manifest.json)・[初回エラー](runs/open-hat-20261120-short-a/manifest.json)
- 混在パターン `B T> | - t` の40,320フレームは2回とも15項目を通過しました。11打音の予約と全フレームの再生位置が上流と一致。0.395–0.450秒で喉頭上昇、声門開大、呼気が重なり、固定上流とのPCM最大差は `2.91×10⁻¹¹` でした。128・77フレームのWAVはバイト一致し、単発 `B`・`t` とキックパターンの回帰も通過しました。[初回](runs/mixed-20261120-a/summary.json)・[再実行](runs/mixed-20261120-root/manifest.json)・[既存パターンの回帰](runs/mixed-20261120-kick-pattern-regression/summary.json)
- 単発 `t` の24,000フレームは2回とも13項目を通過しました。閉鎖は202.667–249.000 msで、固定上流とのPCM最大差は `7.28×10⁻¹²`。呼気と声門開大は独立計算に一致し、声門振動は全区間0でした。単発 `B` と発話の /s/ は回帰で従来のWAV・観測CSVに一致しました。[初回](runs/hat-t-20261120-a/summary.json)・[再実行](runs/hat-t-20261120-root/manifest.json)・[キック回帰](runs/hat-t-20261120-kick-regression/summary.json)・[摩擦音回帰](runs/hat-t-20261120-sibilant-regression/summary.json)
- `B . | - b>` の固定テンポ描画は2回とも12項目を通過しました。55,680フレームの再生位置が固定上流と一致し、PCMの最大差は `1.46×10⁻¹¹`。予約した10ステップのうち8件の時刻が区間内に到来し、打音は4件でした。ホスト幅128と77で、再実装のWAVと索引CSVはバイト一致しました。リポジトリルートから再実行したPCMと観測CSVも一致し、単発 `B` の回帰13項目が通過しました。[初回](runs/beat-pattern-20261120-a/summary.json)・[再実行](runs/beat-pattern-20261120-root/manifest.json)・[単発の回帰](runs/beat-pattern-20261120-kick-final/summary.json)
- キック `B` の24,000フレームのPCMは固定上流と最大 `7.28×10⁻¹²` 差でした。141.271 msで閉唇し、閉鎖中の声門上圧は15,314 dyn/cm²まで上がり、249.375 msで再開口しました。初回は閉じた口端セルを加圧の観測点としたため未達でした。声門上に変更した第2版は2回とも13項目が通過し、別ディレクトリからの再実行で結果要約・時系列・PCMが一致しました。既存の `ɑpɑ` のWAVと観測CSVも従来の通過実行と一致しました。[第1版](runs/kick-b-20261120-a/summary.json)・[第2版](runs/kick-b-20261120-b/summary.json)・[再実行](runs/kick-b-20261120-c/manifest.json)・[両唇破裂音の回帰](runs/kick-b-20261120-bilabial-regression/summary.json)
- 96 kHzは先行・再実行のCLI各17項目、ブラウザ3回の各13項目を通過しました。放射とPCMのサンプル番号が一致し、固定上流との最大PCM差は `2.91×10⁻¹¹`。発声中のp99は3回とも1 ms、全区間の予算超過は2・1・1量子でした。3回で共通した外れ値は減衰中の出力フレーム127,872で、Contextフレームは連続しました。[先行CLI](runs/worklet-rate-96000-20261120-native/summary.json)・[CLI再実行](runs/worklet-rate-96000-20261120-native-repeat/summary.json)・[ブラウザ](runs/worklet-rate-96000-20261120-a/summary.json)・[ブラウザ再実行](runs/worklet-rate-96000-20261120-b/summary.json)・[ルートからの再実行](runs/worklet-rate-96000-20261120-stage6-root/summary.json)
- 48 kHzの固定発声11項目、実時間IPA19項目、実時間歌唱25項目が通過しました。実時間IPAと歌唱のWAVおよび音響観測は以前の通過実行と一致しました。Cargoの整形・ワークスペーステスト・ClippyとTypeScriptの型検査も通過しました。[48 kHz](runs/worklet-rate-96000-20261120-48000-regression/manifest.json)・[IPA](runs/worklet-rate-96000-20261120-ipa-regression/manifest.json)・[歌唱](runs/worklet-rate-96000-20261120-song-regression/manifest.json)
- 16 kHzはCLI各19項目、ブラウザ各13項目を通過しました。PCMはCLI・ブラウザ・固定上流とビット一致し、236量子は連続。発声中のp99は両回4 ms、全区間の8 ms予算超過・WASMメモリ成長・ネイティブの描画中の割り当ては0件でした。32 kHzの回帰も通過し、WAVは前回の結果と一致しました。[CLI](runs/worklet-rate-16000-20261120-native/summary.json)・[CLI再実行](runs/worklet-rate-16000-20261120-native-repeat/summary.json)・[ブラウザ](runs/worklet-rate-16000-20261120-a/summary.json)・[ブラウザ再実行](runs/worklet-rate-16000-20261120-b/summary.json)・[32 kHz回帰](runs/worklet-rate-16000-20261120-32000-regression/manifest.json)
- 32 kHzはCLIとブラウザの各2回で、それぞれ13項目を通過しました。PCMはCLI・ブラウザでビット一致し、固定上流との最大差は `5.68×10⁻¹⁴`。発声中のp99は両回2 msで、全量子の予算超過・WASMメモリ成長・ネイティブ描画中の割り当ては0件でした。44.1 kHz、48 kHzの固定発声の回帰も通過しました。[CLI](runs/worklet-rate-32000-20261120-native/summary.json)・[CLI再実行](runs/worklet-rate-32000-20261120-native-repeat/summary.json)・[ブラウザ](runs/worklet-rate-32000-20261120-a/summary.json)・[ブラウザ再実行](runs/worklet-rate-32000-20261120-b/summary.json)・[44.1 kHz回帰](runs/worklet-rate-32000-20261120-44100-regression/manifest.json)・[48 kHz回帰](runs/worklet-rate-32000-20261120-48000-regression/manifest.json)
- 44.1 kHz固定発声は先行CLIが10項目、ブラウザが2回とも13項目を通過しました。WAVは83,072フレームでCLIとビット一致し、固定上流との差は最大 `1.14×10⁻¹³`。処理時間p99は両回2 ms、量子の予算超過とWASMメモリ成長は両回0件でした。ネイティブの描画中の割り当ては0件でした。ラベルの変更前に起きたブラウザのタイムアウトも保存しています。[先行CLI](runs/worklet-rate-44100-20261120-native/summary.json)・[ブラウザ初回](runs/worklet-rate-44100-20261120-a/manifest.json)・[修正後](runs/worklet-rate-44100-20261120-b/summary.json)・[再実行](runs/worklet-rate-44100-20261120-c/summary.json)
- 計測器の実行記録を整理したあともCLIとブラウザの比較が通過し、WAVと649観測点は直前と一致しました。最終実行では減衰中の1量子で4 msを観測しました。発声中のp99は2 msで、Contextフレームは連続しました。[CLIの再実行](runs/worklet-rate-44100-20261120-native-repeat/manifest.json)・[ブラウザの最終実行](runs/worklet-rate-44100-20261120-d/summary.json)
- 48 kHzの固定発声は11項目、舌と唇の操作・ケース書き出しは20項目の回帰が通過しました。Cargoの整形・ワークスペーステスト・ClippyとTypeScriptの型検査も通過しました。[48 kHz固定発声](runs/worklet-rate-44100-20261120-fixed-regression/manifest.json)・[手動調音](runs/worklet-rate-44100-20261120-manual-regression/manifest.json)
- 実時間の `Pop Dee` は2回とも25項目を通過しました。CLI・オフラインとのPCM差はゼロで、固定上流との最大差は `2.33×10⁻¹⁰`。冒頭32量子後のp99は両回2 ms、予算超過は全区間で各2量子、WASMメモリ増加は各0回でした。ネイティブの描画中の割り当ては両回11,809件で、語境界の25量子では16件から32件に増えました。[変更前の歌唱](runs/worklet-live-song-20261120-baseline/manifest.json)・[初回](runs/worklet-live-song-20261120-a/summary.json)・[再実行](runs/worklet-live-song-20261120-b/summary.json)
- 実時間IPAの19項目と、ブラウザがgzipを展開するオフライン歌唱の16項目が通過しました。IPAはWAV・主要な内部状態・割り当て件数が直前と一致し、歌唱はWAV・観測JSONが通常配信時と一致しました。Cargoの整形・ワークスペーステスト・Clippyと、TypeScriptの型検査も通過しました。[IPA](runs/worklet-live-song-20261120-ipa-regression/manifest.json)・[gzip歌唱](runs/worklet-live-song-20261120-raw-regression/manifest.json)
- `ɑpɑ` の輪郭領域の比較は、研究ワークスペースと `/tmp` から各11判定を通過しました。発話全体は23,370回から6,232回、冒頭32量子後は21,450回から5,720回。累積削減率は86.35%と86.30%でした。PCM49,828フレーム、内部観測、矢状面2条件と断面3条件が基準に一致。冒頭32量子後のp99は両回2 ms、全区間の予算超過は2量子と1量子でした。[事前の区間別計数](runs/contour-buffer-reuse-20261119-a/manifest.json)・[初回](runs/contour-buffer-reuse-20261119-b/summary.json)・[再実行](runs/contour-buffer-reuse-20261119-c/summary.json)
- 10母音遷移9項目、英語発話と歌唱の各15項目の回帰が通過しました。断面CSV、ブラウザのWAVと観測JSONは前回の通過結果とバイト一致しました。候補の `cargo fmt --all --check`、`cargo test --locked --workspace`、`cargo clippy --locked --workspace --all-targets -- -D warnings` も通過しました。[10母音](runs/contour-buffer-reuse-20261119-ten-vowels-regression/manifest.json)・[英語発話](runs/contour-buffer-reuse-20261119-english-regression/manifest.json)・[歌唱](runs/contour-buffer-reuse-20261119-song-regression/manifest.json)
- `ɑpɑ` で扇状走査線の固定長配列を2回比較しました。PCM・内部観測と母音・口唇・舌接触の時系列が基準版と一致しました。ネイティブの全量子の割り当ては45,656回から23,370回に減少し、60%削減の登録判定は両回で不通過でした。冒頭32量子以降のp99は1 msと2 msで、全区間の予算超過は両方とも2量子でした。10母音遷移・英語発話・英語歌唱の回帰も通過しました。[初回](runs/fan-crossing-allocations-20261119-a/summary.json)・[再実行](runs/fan-crossing-allocations-20261119-b/summary.json)・[回帰の記録](notes/fan-crossing-allocations.md#結果と採用判断)
- `ɑpɑ` の実時間収録は2回で各19判定が通過しました。48 kHzで390量子の番号は開始後に連続し、PCM49,828フレームはオフライン・CLIとビット一致。冒頭32量子以降の処理時間p99は2 ms、最大は開始量子の4 msでした。線形メモリの増加は0回で、ネイティブの割り当て・再割り当ては45,656回でした。[通過c](runs/worklet-live-ipa-20261119-c/manifest.json)・[再実行d](runs/worklet-live-ipa-20261119-d/manifest.json)・[先行2件の記録](notes/worklet-live-ipa.md#結果)
- スペクトル19項目、固定発声の実時間11項目、手動調音の再実行ケース20項目、英語発話・英語歌唱の各15項目の回帰が通過しました。オフラインの3条件は前の通過実行とWAV・観測JSONがバイト一致しました。[スペクトル](runs/worklet-pcm-spectrum-20261119-live-ipa-regression/summary.json)・[固定の実時間](runs/worklet-realtime-voice-20261119-live-ipa-regression/summary.json)・[手動調音](runs/worklet-manual-case-export-20261119-live-ipa-regression/summary.json)・[英語発話](runs/worklet-english-voice-20261119-live-ipa-regression/summary.json)・[英語歌唱](runs/worklet-song-voice-20261119-live-ipa-regression/summary.json)
- `ɑpɑ` のPCMスペクトルは幅ごとに独立レンダーし、2回で各19判定が通過しました。全ビンの独立FFTとの差は最大 `6.05×10⁻¹⁶`、固定上流との差は `1.93×10⁻¹⁵` の線形振幅。母音から閉鎖まで59.47 dB低下し、再開口を含む窓で50.14 dB戻りました。連続ダウンロードでタイムアウトした先行2件も保存しました。[通過c](runs/worklet-pcm-spectrum-20261119-c/manifest.json)・[再実行d](runs/worklet-pcm-spectrum-20261119-d/manifest.json)・[初回の記録](notes/worklet-pcm-spectrum.md#結果)
- 声門波形20項目、IPA時系列・英語発話・英語歌唱の各15項目の回帰が通過しました。4条件のWAVと観測JSONは従来の通過実行とバイト一致しました。[声門](runs/worklet-glottal-scope-20261119-spectrum-regression/summary.json)・[IPA](runs/worklet-ipa-timeline-20261119-spectrum-regression/summary.json)・[英語発話](runs/worklet-english-voice-20261119-spectrum-regression/summary.json)・[英語歌唱](runs/worklet-song-voice-20261119-spectrum-regression/summary.json)
- `ɑpɑ` の声門波形は研究ディレクトリと `/tmp` から各20判定が通過しました。面積・流量の全49,828フレームとPCMはCLIと一致。固定上流との差は面積で最大 `7.63×10⁻¹⁷ cm²`、流量で `2.30×10⁻¹¹ cm³/s`。母音の面積ピーク間隔は441フレーム、/p/ の閉鎖中の流量は最小−59.19 cm³/sでした。[初回](runs/worklet-glottal-scope-20261119-a/manifest.json)・[再実行](runs/worklet-glottal-scope-20261119-b/manifest.json)
- IPA時系列、断面・圧力・流量、英語発話、英語歌唱、固定姿勢の5回帰が通過しました。直前に通過した実行とPCM・既存観測が一致し、英語発話でも声門の各79,222出力フレームを保存できました。[IPA](runs/worklet-ipa-timeline-20261119-glottal-regression/summary.json)・[圧力と流量](runs/worklet-tract-acoustics-20261119-glottal-regression/summary.json)・[英語発話](runs/worklet-english-voice-20261119-glottal-regression/summary.json)・[英語歌唱](runs/worklet-song-voice-20261119-glottal-regression/summary.json)・[固定姿勢](runs/worklet-fixed-voice-20261119-glottal-regression/summary.json)
- `ɑpɑ` の圧力と流量は研究ディレクトリと `/tmp` から各20判定が通過しました。CLIとの数値差はゼロ、固定上流との最大差は圧力 `1.54×10⁻¹⁰ dyn/cm²`、流量 `2.16×10⁻¹¹ cm³/s`。閉鎖中は口端の直前の枝が止まり、放射流量の減衰は独立式と相対誤差 `4.0×10⁻¹⁵` 以内で一致しました。断面のみ・IPA時系列・英語発話の回帰も通過しました。[初回](runs/worklet-tract-acoustics-20261119-a/manifest.json)・[再実行](runs/worklet-tract-acoustics-20261119-b/manifest.json)・[断面のみ](runs/worklet-tract-profile-20261119-acoustics-regression/summary.json)・[IPA](runs/worklet-ipa-timeline-20261119-acoustics-regression/summary.json)・[英語発話](runs/worklet-english-voice-20261119-acoustics-regression/summary.json)
- `ɑpɑ` の声道断面は研究ディレクトリと `/tmp` から各12判定が通過しました。CLIと断面・PCMが一致し、固定上流との最大差は最小断面積で `2.31×10⁻¹³ cm²`、PCMで `1.82×10⁻¹²`。唇端の最小断面は256 msで0 cm²、352 msで6.418 cm²でした。観測列、図形座標、画像は再実行でハッシュが一致しました。[初回](runs/worklet-tract-profile-20261119-a/manifest.json)・[再実行](runs/worklet-tract-profile-20261119-b/manifest.json)
- 断面追加後にIPA時系列・英語発話・英語歌唱を各15項目、固定姿勢を12項目検証しました。IPA・英語・歌唱では直前の通過版と画面から保存したWAVが一致し、既存の観測JSONの項目も一致しました。英語発話の追加断面は104時点です。[IPA](runs/worklet-ipa-timeline-20261119-tract-regression/summary.json)・[英語発話](runs/worklet-english-voice-20261119-tract-regression/summary.json)・[歌唱](runs/worklet-song-voice-20261119-tract-regression/summary.json)・[固定姿勢](runs/worklet-fixed-voice-20261119-tract-regression/summary.json)
- `Mom? Pop.` のブラウザ発話は2回とも15項目を通過しました。計画休止は0.350秒、YINによるF0は150.38 Hzと93.96 Hz。/m/ の観測窓の鼻端流量ピークは310.96 cm³/s。CLIとPCM 79,222フレームはビット一致し、固定上流との差は最大 `2.33×10⁻¹⁰` でした。[初回](runs/worklet-english-voice-20261119-a/manifest.json)・[再実行](runs/worklet-english-voice-20261119-b/manifest.json)
- 手動調音のダウンロードケースをそのままCLIに渡し、2回とも20項目が通過しました。48 kHzで102,272フレームのPCMはCLIとビット一致し、固定上流との差は最大 `3.73×10⁻⁹`。同一制御フレームの調音と呼気、調音なし、制御境界外を固定時刻で検証しました。[初回](runs/worklet-manual-case-export-20261119-a/manifest.json)・[再実行](runs/worklet-manual-case-export-20261119-b/manifest.json)
- `ɑpɑ` の時系列表示は2回とも15項目が通過しました。2画面幅で図形座標を照合し、最大差は `1.14×10⁻¹³` SVG単位。/p/ の予定開始は209.380 ms、最初の閉鎖観測は231.667 msでした。PCM・観測JSON・画面から取得した図形のハッシュは2回で一致しました。[初回](runs/worklet-ipa-timeline-20261119-a/manifest.json)・[再実行](runs/worklet-ipa-timeline-20261119-b/manifest.json)
- 舌体のY・X、口唇開度を順に操作し、両実行で各13判定が通過しました。口端最小断面積は3.355から1.247 cm²へ減少し、独立計算との位置差は最大 `8.89×10⁻¹⁶ cm`。各回の適用フレームで再生したCLIとPCMはビット一致し、固定上流との最大差は `3.73×10⁻⁹` でした。再実行では発声前の最初のブロックでWASMメモリが1回増えました。[初回](runs/worklet-manual-articulation-20261119-a/manifest.json)・[再実行](runs/worklet-manual-articulation-20261119-b/manifest.json)
- `Pop Dee` の英語歌詞とMIDIをWeb画面から入力し、計画・PCMがCLIと一致しました。固定上流との差はPCMの最大絶対差 `2.33×10⁻¹⁰`。YINのF0は262.63 Hzと441.79 Hz、1.42秒の呼気ゲートは約1.000で開大面積は0.07535 cm²でした。通常配信の15判定と `/tmp` から生gzipを配信した16判定が通過し、両実行のWAV・観測JSONはハッシュが一致しました。初回はHTTP展開後と圧縮済みの辞書を比較した判定だけが不通過でした。[初回](runs/worklet-song-voice-20261119-a/summary.json)・[通常配信](runs/worklet-song-voice-20261119-b/manifest.json)・[再実行](runs/worklet-song-voice-20261119-c/manifest.json)
- `ɑpɑ` のブラウザ発話で、CLIと音素区間・ジェスチャーが一致し、PCM49,828フレームはビット一致しました。開閉の観測は1・15フレーム後で、16フレームの観測間隔から予測した範囲です。固定上流との差はPCMの最大絶対差 `1.82×10⁻¹²`。全12判定を別の作業ディレクトリから再実行しました。[ブラウザIPA](runs/worklet-ipa-voice-20261119-c/manifest.json)
- Chromiumの実時間発声で、開始・停止から減衰までのPCMがCLIとビット一致し、全11判定が通過しました。ブロック処理p99は発声2 ms、比較予算は2.667 ms。停止末尾のPCMピークは約 `3.59×10⁻¹⁰` でした。[実時間計測](runs/worklet-realtime-voice-20261119-d/manifest.json)・[再実行](runs/worklet-realtime-voice-20261119-e/manifest.json)
- 接続直後に512フレーム分のContextの飛びを検出しました。無音準備中の不連続を記録し、安定した境界から合成器と計測の時計を進めると、以降の721ブロックは連続しました。[修正前](runs/worklet-realtime-voice-20261119-c/summary.json)・[修正後](runs/worklet-realtime-voice-20261119-d/summary.json)
- 固定 /i/ のWeb画面から出力した48 kHzのWAVは、CLIとファイル全体のハッシュが一致しました。固定上流とのPCMもビット一致し、256時点の7系列はCLIとの差が0でした。読み込みを失敗させた後の再試行も含め、全12判定が通過しました。[ブラウザ実行](runs/worklet-fixed-voice-20261119-b/manifest.json)・[WASM回帰](runs/wasm-fixed-voice-20261119-worklet-regression/summary.json)
- 固定 /i/ の第6段階で16判定が通過しました。初回と `/tmp` からの再実行でPCMはビット一致、候補の声門・呼気・放射は差0、固定上流の7系列との最大差はピーク比 `1.58×10⁻¹³`。ABIの割り当ては0回、WASMバッファのアドレスも一致しました。[固定WASM](runs/wasm-fixed-voice-20261119-c/manifest.json)・[歌唱の回帰](runs/song-voice-long-20261119-wasm-regression/summary.json)
- `/tmp` から歌唱4ケースを再実行し、各7判定が通過しました。上流とのPCM最大絶対差は `2.33×10⁻¹⁰`。計画とPCM、平滑化F0と開大の独立照合、128/77フレーム分割の一致を確認しました。[長音](runs/song-voice-long-20261119-b/manifest.json)・[深さ0](runs/song-voice-flat-20261119-b/manifest.json)・[高速](runs/song-voice-fast-20261119-b/manifest.json)・[破裂音末尾](runs/song-voice-stop-20261119-b/manifest.json)
- 第1版の観測窓は、冒頭 /p/ の早期閉鎖と高速時に継続する閉鎖を捉えられませんでした。固定上流にも同じ動きがあり、理由と旧判定を保存して観測窓を第2版にしました。旧版と新版で波形・時系列・上流計画のハッシュは一致しました。[判定変更の根拠](notes/sung-voice.md#初回の判定と第2版の観測窓)・[高速の第1版](runs/song-voice-fast-20261119-a/summary.json)
- 既存の歌唱計画と英語発話は直前の通過版と計測要約・波形や中間出力が一致しました。高速 /p/ の回帰、Rustワークスペースの8テスト、Clippyと整形、固定上流の `engine`・`sing_fast`・`sung_release` の17テストも通過しました。[歌唱計画](runs/song-plan-20261119-c/manifest.json)・[英語発話](runs/lateral-hello-20261119-d/manifest.json)・[高速 /p/](runs/bilabial-p-fast-20261119-song-regression/summary.json)
- 歌唱の9譜例で音素区間・F0に固定上流との差は0でした。歌詞66件、綴りラベル44件、語の音節化8件がTypeScript参照と一致しました。240 BPMの `Strut` は4音目の母音が16.5 ms遅れ、`Pop Dee` の母音は拍に一致しました。[歌唱の計測結果](runs/song-plan-20261119-a/summary.json)
- 歌唱の計画を `/tmp` から再実行し、候補・上流・入力・要約を含む6ファイルが初回と一致しました。英語発話と発音、IPA区間の回帰も通過し、39ファイルが先行実行と一致しました。[歌唱の再実行](runs/song-plan-20261119-b/manifest.json)・[英語発話](runs/lateral-hello-20261119-c/summary.json)・[発話区間](runs/speech-timing-20261119-d/summary.json)
- /l ɫ/ の6条件を固定上流版に照合し、最大PCM差は `1.87×10⁻⁹` 未満でした。側方開きで中央窓の口端流量RMSが /l/ で12.41倍、/ɫ/ で10.07倍になりました。`Hello world` は `həlˈoʊwˈɝɫd`、48 kHz・57,845フレームです。[明るい側音](runs/lateral-l-closed-20261119-b/summary.json)・[暗い側音](runs/lateral-dark-closed-20261119-b/summary.json)・[英語の比較](runs/lateral-hello-20261119-a/summary.json)
- `/tmp` から側音の6条件を再実行し、59ファイルが先行実行と一致しました。2つの対照に、補間した側方開きから口腔の最小断面を求める比較を追加し、最大差は `3.50×10⁻¹⁵ cm²` でした。既存4検証の回帰も通過しました。[英語の再実行](runs/lateral-hello-20261119-b/manifest.json)・[面積下限](runs/lateral-l-closed-20261119-b/summary.json)・[英語発音の回帰](runs/english-frontend-20261119-f/summary.json)
- /w/ の4条件でジェスチャー、唇・舌体・口腔断面、LPC、PCMを固定上流と照合しました。PCMの最大絶対差は `2.91×10⁻¹¹`。等速 `ˈɑwɑ` のF1は420→717 Hz、`We.` のF2は982→2,229 Hz。`We.` は48 kHz・30,838フレームでした。[等速](runs/approximant-w-20261119-a/summary.json)・[英語](runs/approximant-w-english-20261119-a/summary.json)
- `/tmp` から /w/ の4条件を再実行し、音声・観測・設定を含む40ファイルが初回と一致しました。唇の独立計算の最大差は `6.18×10⁻¹⁴`。既存4検証の回帰が通過し、英語発音JSONでは /w/ の対応状態が43箇所変わりました。[英語の実行記録](runs/approximant-w-english-20261119-b/manifest.json)・[英語の回帰](runs/english-frontend-20261119-e/summary.json)・[基準IPAの回帰](runs/bilabial-nasal-vcv-20261119-f/summary.json)
- 声門摩擦音の5条件で調音計画、声門開大、圧力源、有声化、PCMを固定上流と照合しました。PCMの最大絶対差は `5.82×10⁻¹¹`。同じ調音で乱流を止めると /h/ 中央の3〜12 kHz電力が71.79 dB低下しました。`Hi.` のWAVは48 kHzの37,440フレームです。[無声](runs/glottal-h-20261119-a/summary.json)・[乱流対照](runs/glottal-h-muted-20261119-a/summary.json)・[有声](runs/glottal-voiced-20261119-a/summary.json)・[英語](runs/glottal-h-english-20261119-a/summary.json)
- `/tmp` から5条件を再実行し、音声と観測を含む49ファイルが一致しました。内部48 kHzでは、前サンプルの枝状態から計算した乱流振幅の最大誤差は `2.28×10⁻¹³ dyn/cm²`、同じ時刻の枝状態を使う対照は5.94 dyn/cm²でした。既存4検証の回帰も通過し、英語発音JSONでは /h/ の対応状態を確認しました。[内側48 kHzの照合](runs/glottal-h-48k-20261119-b/summary.json)・[英語の実行記録](runs/glottal-h-english-20261119-b/manifest.json)・[英語回帰](runs/english-frontend-20261119-d/summary.json)
- 歯茎破裂音の5条件で計画・閉鎖セル・再開口時刻・PCMを固定上流と照合しました。最大PCM差は `2.91×10⁻¹¹`。`Dad.` は42,636フレーム。1.8倍速の最初の /t/ は両実装で0.03418 cm²まで狭まり、初回の完全閉鎖の判定は不通過でした。[等速 /d/](runs/alveolar-d-20261119-b/summary.json)・[高速条件の初回](runs/alveolar-t-fast-20261119-a/summary.json)・[高速条件の再計測](runs/alveolar-t-fast-20261119-b/summary.json)・[英語](runs/alveolar-d-english-20261119-b/summary.json)
- 歯茎破裂音の5条件を `/tmp` から再実行し、観測・音声・計画・結果の50ファイルが先行実行と一致しました。両唇破裂音、歯茎摩擦音、基準IPA発話の回帰は30ファイル一致。英語の回帰は波形を含む16ファイル一致し、発音JSONの未対応一覧から /d t/ が外れました。[歯茎破裂音の再実行](runs/alveolar-d-english-20261119-c/manifest.json)・[英語](runs/english-frontend-20261119-c/summary.json)・[基準IPA](runs/bilabial-nasal-vcv-20261119-d/summary.json)・[両唇破裂音](runs/bilabial-p-20261119-f/summary.json)・[歯茎摩擦音](runs/sibilant-s-20261119-e/summary.json)
- 英語の86入力・514語・12件のARPAbet入力を比較し、参照との差は判定範囲では0でした。`Mom? Pop.` のF0目標は151.2 Hzと91.84 Hz。波形の長さは48 kHzで79,222フレーム、固定上流と周期変動・乱流を止めて比べたPCMの最大絶対差は `2.33×10⁻¹⁰` でした。[英語の計測結果](runs/english-frontend-20261119-b/summary.json)
- 英語の検証を `/tmp` から再実行し、発音・計画・音声・要約など17ファイルが初回とバイト一致しました。基準IPAの5発話の回帰もすべて通過し、比較した10ファイルが先行実行とバイト一致しました。[英語の実行記録](runs/english-frontend-20261119-b/manifest.json)・[IPAの回帰](runs/bilabial-nasal-vcv-20261119-c/summary.json)
- /m/ の5条件で音素・ジェスチャーの計画と、閉鎖・開口・流量切替の実測フレームが固定上流版と一致しました。PCMの差は最大 `2.33×10⁻¹⁰`。後続の /b/ は /p/ に比べ、軟口蓋ポートが0.01 cm²を下回る時刻を15.02 ms遅らせました。基準5発話は48 kHzの202,527フレームで一致しました。[鼻音](runs/bilabial-nasal-m-20261119-b/summary.json)・[後続子音の対照](runs/bilabial-nasal-mb-20261119-b/summary.json)・[基準5発話](runs/bilabial-nasal-vcv-20261119-b/summary.json)
- 両唇鼻音と基準5発話を `/tmp` から再実行し、時系列・PCM・設定・計画の45ファイルが同一でした。両唇破裂音と歯茎摩擦音の回帰も通過し、比較対象18ファイルが一致しました。軟口蓋の独立計算との差は最大 `7.22×10⁻¹² cm²` でした。[鼻音の実行記録](runs/bilabial-nasal-vcv-20261119-b/manifest.json)・[破裂音の回帰](runs/bilabial-p-20261119-e/manifest.json)・[摩擦音の回帰](runs/sibilant-s-20261119-d/manifest.json)
- /s z/ の摩擦音と乱流倍率0の対照が通過しました。比較したPCMの最大絶対差は `2.91×10⁻¹¹`。/s/ の狭窄は中央窓で中央値0.0974 cm²、/z/ は0.1332 cm²。/z/ の低域電力は先行母音より13.96 dB低下しました。/s/ の形状をそろえ、乱流を切ると3〜15 kHzの平均電力は61.14 dB低下しました。[無声](runs/sibilant-s-20261119-c/summary.json)・[有声](runs/sibilant-z-20261119-c/summary.json)・[乱流倍率の比較](runs/sibilant-s-muted-20261119-c/summary.json)
- /s z/ と乱流倍率0の3条件を `/tmp` から再実行し、候補・上流の観測CSV、PCM、設定、計画の27ファイルが先行実行とバイト一致しました。既存の両唇破裂音と固定狭窄の乱流も回帰を通過し、比較した12ファイルが直前と一致しました。[摩擦音の再実行](runs/sibilant-s-20261119-c/manifest.json)・[両唇破裂音](runs/bilabial-p-20261119-d/manifest.json)・[固定狭窄の乱流](runs/turbulence-forward-20261119-l/manifest.json)
- 両唇破裂音の4条件で、等速の再開口は計画された /p/ の終端より0.224 ms後、/b/ では0.082 ms前でした。1.8倍速の /p/ では閉鎖が5.92 msでした。最小断面で検出した閉鎖後の口端放射は、内部サンプルごとに0.995倍の減衰と一致しました。[無声](runs/bilabial-p-20261119-c/summary.json)・[有声](runs/bilabial-b-20261119-c/summary.json)・[無気](runs/bilabial-p-unaspirated-20261119-c/summary.json)・[高速](runs/bilabial-p-fast-20261119-d/summary.json)
- 両唇破裂音の再実行で、候補・上流の計画・PCM・CSVの比較対象32ファイルが一致しました。ホスト分割77・128フレームでもWAVと出力段のCSVが同一です。PCMと上流との差は最大 `1.87×10⁻⁹`。回帰では、母音スコアの5ファイルと従来の母音発声遷移の9ファイルが直前と一致しました。[無声の再実行](runs/bilabial-p-20261119-c/manifest.json)・[高速の判定](runs/bilabial-p-fast-20261119-d/manifest.json)・[母音スコア](runs/vowel-gesture-score-20261119-d/manifest.json)・[母音発声の回帰](runs/vowel-motion-voice-vowels-20261119-f/manifest.json)
- 母音ジェスチャー8条件を1.25 ms間隔で照合しました。比較点で活性・目標・位置・速度の上流との差は0。独立したランプと混合の計算では最大 `5.33×10⁻¹⁵`。基準 `ɑpɑ` で両母音の目標が同時に有効な幅は31.9625 ms、離散観測で26フレームでした。初回は高速条件でランプの後処理に差があり、固定上流の `shorten_timing` を確認して修正しました。[初回](runs/vowel-gesture-score-20261119-a/summary.json)・[修正後](runs/vowel-gesture-score-20261119-b/summary.json)
- 母音スコアを `/tmp` から再実行し、候補・上流の観測JSON、設定、較正表、要約の5ファイルがバイト一致しました。回帰では発話区間の9ファイルと従来の調音器計測の5ファイルも一致しました。[母音スコアの再実行](runs/vowel-gesture-score-20261119-c/manifest.json)・[発話区間](runs/speech-timing-20261119-c/manifest.json)・[従来の調音器計測](runs/articulation-vowels-free-20261119-g/manifest.json)
- 発話区間の登録15入力と条件表655件が通過しました。比較できた秒単位の値は上流のプローブと一致し、独立計算との差は最大 `6.94×10⁻¹⁷ s`。上流CLIの15マークの差は丸め幅内の最大0.390 msで、48 kHz WAVの202,527フレームとも一致しました。[初回](runs/speech-timing-20261119-a/manifest.json)・[再実行](runs/speech-timing-20261119-b/manifest.json)
- 発話区間を `/tmp` から再計測し、上流だけの基準WAVと候補・上流の区間JSONを含む比較対象9ファイルが初回とバイト一致しました。IPA字句解析の8ファイルと、成人男性母音遷移のCSV・WAVなど9ファイルも直前の通過版に一致。候補の整形、ワークスペーステスト、Clippyが通過しました。[区間の再計測](runs/speech-timing-20261119-b/manifest.json)・[IPAの回帰](runs/ipa-tokenization-20261119-c/manifest.json)・[母音遷移の回帰](runs/vowel-motion-voice-vowels-20261119-e/manifest.json)
- IPAの登録15入力で208個の音素・休止、19発話、45件の診断出現を記録しました。既知108記号に12種類の修飾を組み合わせた1,296入力も固定上流と一致し、登録したバイト位置に合格。候補の整形、テスト、Clippyと、上流の未対応・有気・破擦音・発音修飾の計38テストが通過しました。[IPA比較](runs/ipa-tokenization-20261119-b/manifest.json)
- IPA計測を `/tmp` から再実行し、ケース出力、個別CLIの出力、組み合わせ表、上流の出力、要約の9ファイルが一致しました。線形伝達、固定発声、調音軌跡、母音遷移の既存4ケースも通過し、比較対象44ファイルが直前と一致しました。[再実行](runs/ipa-tokenization-20261119-b/manifest.json)・[母音遷移の回帰](runs/vowel-motion-voice-vowels-20261119-d/manifest.json)
- 成人男性の基準10母音で上流とPCMがすべてバイト一致しました。定常窓の推定F0は110.0003〜110.0016 Hz、線形放射流量の最大差は各系列のピーク比 `7.41×10⁻¹⁴`。隣接9遷移では /ʌ/ → /ɝ/ の最大断面差を計測し、セル境界の前後の差も固定上流と照合しました。[最終測定](runs/vowels-reference-20261119-b/summary.json)・[断面の時系列](runs/vowels-reference-20261119-b-continuity/manifest.json)
- 初回の /ɛ ʌ ɝ/ の判定では、計測器の根の数え方が上流のLPC出力に適用される帯域幅選別と異なりました。除外された根まで数えないよう修正し、同じ波形・ケース・閾値ですべて再検証しました。[初回](runs/vowels-reference-20261119-a/summary.json)・[修正後](runs/vowels-reference-20261119-b/summary.json)
- 基準10母音を `/tmp` から再実行し、波形・時系列・出力段・境界検査を含む338ファイルが一致しました。親の要約も実行IDと参照ハッシュを除き同一でした。軟口蓋開放、固定無音、接触補正の既存3ケースでは比較対象32ファイルが一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と上流の解析・形状連続性のテストが通過しました。[全件の再実行](runs/vowels-reference-20261119-c/manifest.json)・[軟口蓋開放の回帰](runs/vowel-transfer-i-open-velum-20261119-d/manifest.json)・[接触の回帰](runs/tract-slew-contact-20261119-d/manifest.json)
- 母音遷移の3条件で計89,088出力フレームを確認しました。上流との差はPCMで最大 `2.33×10⁻¹⁰`、内部の音響系列で各ピーク比最大 `3.38×10⁻¹²`。通常発声の3窓の声門周期は約110 Hz。軟口蓋を開いた条件では鼻端流量が最大31.62 cm³/sになりました。[通常](runs/vowel-motion-voice-vowels-20261119-b/manifest.json)・[軟口蓋](runs/vowel-motion-voice-nasal-20261119-b/manifest.json)・[呼気ゲート0](runs/vowel-motion-voice-unvoiced-20261119-b/manifest.json)
- 研究ワークスペースと `/tmp` から同じ3ケースを実行し、候補と上流のPCM、内部系列、出力段、設定、イベント表、要約の36ファイルが一致しました。固定発声4条件、可動声道、断面目標、調音の既存7ケースも通過し、比較対象74ファイルが直前と一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と上流のホスト分割テストが通過しました。[再現](runs/vowel-motion-voice-vowels-20261119-c/manifest.json)・[固定発声の回帰](runs/vowel-voice-i-20261119-i/manifest.json)・[可動声道の回帰](runs/tract-motion-vowels-20261119-e/manifest.json)
- 可動声道3条件の110,592内部サンプルを測定しました。固定上流版との圧力・流量・放射の最大差は、各系列のピーク比 `2.42×10⁻¹²`。口腔中央の圧力収支から求めた体積源と独立計算との差は最大 `1.19×10⁻¹¹ cm³/s`。唇と舌による閉鎖を別々に検出し、母音遷移では軟口蓋の開放に伴い鼻端流量が最大22.72 cm³/sになりました。[唇](runs/tract-motion-lips-20261119-b/manifest.json)・[母音](runs/tract-motion-vowels-20261119-b/manifest.json)・[舌先](runs/tract-motion-contact-20261119-b/manifest.json)
- 可動声道の3ケースを `/tmp` から再実行し、候補・上流・独立計算のCSV、設定、イベント表、要約の計18ファイルが初回と一致しました。口端開閉、密閉管、移動狭窄、声門、固定声道・発声、断面と調音の既存9ケースも通過し、比較した52ファイルが直前の通過版とバイト一致しました。[口端開閉](runs/moving-aperture-20261119-p/manifest.json)・[閉鎖移動](runs/sliding-closure-20261119-m/manifest.json)・[固定発声](runs/vowel-voice-i-20261119-h/manifest.json)・[断面目標](runs/tract-slew-vowels-20261119-c/manifest.json)
- 断面目標を新しい実行IDで再生成して `--control-run` で指定した母音ケースも通過しました。候補・上流・独立計算のCSV、設定、イベント表、要約が最終検証と一致しました。[再生成した断面目標での実行](runs/tract-motion-vowels-20261119-d/manifest.json)
- 初回のClippyはセル数の検証関数を呼び出していなかったため不通過でした。初期化で検証を行うよう修正し、`cargo fmt`、`cargo test`、`cargo clippy` と可動声道3ケースを再実行しました。再実行の18ファイルは初回と一致しました。[最終検証の母音ケース](runs/tract-motion-vowels-20261119-c/manifest.json)
- 可動声道の4条件で計1,152制御フレームを照合しました。最大絶対差は固定上流と `1.03×10⁻¹³ cm²`、独立計算と `2.78×10⁻¹⁷ cm²`。唇末端セルの閉鎖は制限によって20 ms遅れ、舌先補正は104フレームで発生しました。候補の `cargo fmt`、`cargo test`、`cargo clippy`、上流の速い閉鎖時の圧力上限と接触の出力安定性の試験が通過しました。[母音](runs/tract-slew-vowels-20261119-b/manifest.json)・[唇](runs/tract-slew-lips-20261119-b/manifest.json)・[接触補正あり](runs/tract-slew-contact-20261119-b/manifest.json)・[接触補正なし](runs/tract-slew-contact-off-20261119-b/manifest.json)
- 可動声道の4ケースを `/tmp` から再実行し、候補・上流・独立計算のCSV、設定、イベント表、要約の計24ファイルが初回と一致しました。調音軌跡、固定母音の発声と線形応答、固定気道、再標本化、接触の既存8ケースも再実行し、比較対象64ファイルが直前の通過版とバイト一致しました。[調音の回帰](runs/articulation-vowels-free-20261119-c/manifest.json)・[固定発声の回帰](runs/vowel-voice-i-20261119-g/manifest.json)・[固定気道の回帰](runs/fixed-airway-neutral-20261119-i/manifest.json)・[接触の回帰](runs/contact-raised-tip-20261119-f/manifest.json)
- 4ケースの計944制御フレームで、候補の全17成分のCSVが上流とバイト一致しました。研究ディレクトリと `/tmp` からの再実行では24ファイル、既存5ケースでは直前の通過版と54ファイルが一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と、上流の母音間の幾何連続性試験が通過しました。[舌先座標指定](runs/articulation-vowels-pinned-20261119-b/manifest.json)・[舌先追従](runs/articulation-vowels-free-20261119-b/manifest.json)・[顎](runs/articulation-jaw-pace-20261119-b/manifest.json)・[軟口蓋](runs/articulation-blend-limits-20261119-b/manifest.json)・[PCMの回帰](runs/vowel-voice-i-20261119-f/manifest.json)
- 固定母音と呼気ゲート0の4ケースは、候補のPCMサンプルが全件で上流とバイト一致しました。定常F0は有声3条件で約110 Hz、LPCの周波数・帯域幅の差は `1.09×10⁻¹⁰ Hz` 未満。ホスト分割128・77でWAVと出力段CSVが一致し、別ディレクトリでも56ファイルが一致しました。既存8ケースでは90ファイルが直前の通過版と一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と上流のブロック分割・解析のテストを通過しました。`/u/` の初回はLPCのナイキスト境界の根で件数判定が不合格になり、旧条件・結果を保存して判定を改訂しました。[固定 /i/](runs/vowel-voice-i-20261119-e/manifest.json)・[固定 /ɑ/](runs/vowel-voice-alpha-20261119-e/manifest.json)・[固定 /u/](runs/vowel-voice-u-20261119-e/manifest.json)・[無励振](runs/vowel-voice-i-silent-20261119-e/manifest.json)・[旧条件の不合格](runs/vowel-voice-u-20261119-b/manifest.json)
- 固定母音の4ケースを研究ディレクトリと `/tmp` から再実行し、設定、候補・上流・独立計算のCSV、要約の48ファイルが一致しました。上流とのピーク周波数の最大差は `8.19×10⁻¹² Hz` 未満、独立計算との複素応答の差は成分ピーク比 `4.96×10⁻¹³` 未満。既存9ケースの63ファイルが直前の通過版と一致し、候補の `cargo fmt`、`cargo test`、`cargo clippy`、上流の解析ゴールデンテストと母音連続性試験も通過しました。[固定 /i/](runs/vowel-transfer-i-20261119-b/manifest.json)・[固定 /ɑ/](runs/vowel-transfer-alpha-20261119-b/manifest.json)・[固定 /u/](runs/vowel-transfer-u-20261119-b/manifest.json)・[軟口蓋開放](runs/vowel-transfer-i-open-velum-20261119-b/manifest.json)
- 固定姿勢の5ケースを研究ディレクトリと `/tmp` から再実行し、候補・上流・独立計算のCSV、入力格子、設定、要約の35ファイルが一致しました。上流の12観測系列との最大差は列ピーク比 `6.74×10⁻¹⁴` 未満。既存13ケースでは90ファイルが直前の通過版と一致し、候補の `cargo fmt`、`cargo test`、`cargo clippy` と上流の短い口腔の安定性テストを通過しました。初回の要約保存エラーは失敗記録に残しました。[短い口腔96 kHz](runs/fixed-airway-short-20261119-e/manifest.json)・[64 kHz](runs/fixed-airway-short-64k-20261119-e/manifest.json)・[唇の閉鎖](runs/fixed-airway-closed-lips-20261119-e/manifest.json)・[初回の失敗](runs/fixed-airway-neutral-20261119-a/manifest.json)
- セルの割り当て7ケースを研究ディレクトリと `/tmp` から実行し、候補・上流・独立計算のCSV、入力格子、設定、要約の49ファイルが一致しました。上流との差は境界 `7.11×10⁻¹⁵ cm` 未満、調和平均と最小断面は `3.74×10⁻¹⁴ cm²` 未満。既存12ケースで86ファイルが直前の通過版と一致し、候補の `cargo fmt`、`cargo test`、`cargo clippy` と上流の母音連続性・定常狭窄テストが通過しました。[中立姿勢](runs/resample-neutral-20261119-b/manifest.json)・[舌体の閉鎖](runs/resample-closed-roof-20261119-b/manifest.json)・[唇の閉鎖](runs/resample-compressed-lips-20261119-b/manifest.json)・[断面積の回帰](runs/area-lateral-20261119-c/manifest.json)・[PCMの回帰](runs/pcm-voiced-20261119-l/manifest.json)
- 断面積の6ケースを研究ディレクトリと `/tmp` から実行し、候補・上流・独立計算のCSV、設定、要約の計48ファイルのSHA-256が一致しました。固定上流との差は面積 `4.67×10⁻¹⁴ cm²` 未満、格子上の距離 `5.33×10⁻¹⁵ cm` 未満。既存12ケースで出力71ファイルが一致し、候補の `cargo fmt`、`cargo test`、`cargo clippy`、上流の較正済み母音の連続性テストが通過しました。[中立姿勢](runs/area-neutral-20261119-b/manifest.json)・[広げた唇](runs/area-wide-lips-20261119-b/manifest.json)・[舌側面](runs/area-lateral-20261119-b/manifest.json)・[接触補正の回帰](runs/contact-raised-tip-20261119-c/manifest.json)
- 接触補正の6ケースを研究ディレクトリと `/tmp` から実行し、候補と上流のCSV、独立計算、輪郭、設定、要約の計48ファイルのSHA-256が一致しました。固定上流との隙間の最大差は `9.66×10⁻¹⁵ cm` 未満。既存10ケースの出力44ファイルも一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と、上流の頂点・下唇のテストが通過しました。[上げた舌先](runs/contact-raised-tip-20261119-b/manifest.json)・[圧縮した唇](runs/contact-compressed-lips-20261119-b/manifest.json)・[引き込み0.5](runs/contact-tuck-handover-20261119-b/manifest.json)・[測定格子の回帰](runs/grid-labiodental-20261119-c/manifest.json)
- 格子の5ケースを研究ディレクトリと `/tmp` から実行し、座標・隙間・輪郭のCSV、設定、要約の計25ファイルのSHA-256が一致しました。固定上流との最大差は `3.56×10⁻¹⁵ cm` 未満。既存8ケースで出力38ファイルが直前の通過版と一致し、候補の `cargo fmt`、`cargo test`、`cargo clippy` と、上流の頂点・下唇のテストが通過しました。[中立姿勢](runs/grid-neutral-20261119-b/manifest.json)・[舌体を前下方へ移した姿勢](runs/grid-shifted-tongue-20261119-b/manifest.json)・[引き込んだ下唇](runs/grid-labiodental-20261119-b/manifest.json)・[矢状面の回帰](runs/sagittal-neutral-20261119-c/manifest.json)
- 矢状面の2ケースを研究ディレクトリと `/tmp` から実行し、候補・上流の座標CSV、設定、要約のSHA-256が一致しました。上流との最大座標差は `3.67×10⁻¹⁵ cm` 未満。既存の一様管、軟壁、狭窄、声帯開大、PCM、写像の6ケースではCSV・要約・WAVの32ファイルが直前の通過版と一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と上流の頂点をかすめる測定線のテストも通過しました。[中立姿勢](runs/sagittal-neutral-20261119-b/manifest.json)・[顎を開いた姿勢](runs/sagittal-open-jaw-20261119-b/manifest.json)・[PCMの回帰](runs/pcm-voiced-20261119-h/manifest.json)
- 写像の5ケースを研究ディレクトリと `/tmp` から実行し、候補・上流の時系列、周期ごとの状態CSV、設定、要約、結合ケースのWAVで計29ファイルのSHA-256が一致しました。固定上流の時系列との最大差はピーク比 `1.22×10⁻¹³` 未満。候補の `cargo fmt`、`cargo test`、`cargo clippy` と、上流の動物音源の32・48 kHzテストが通過しました。[周期4](runs/chaos-period-4-20261119-b/manifest.json)・[非周期](runs/chaos-aperiodic-20261119-b/manifest.json)・[結合](runs/chaos-voiced-20261119-b/manifest.json)
- 既存37ケースを再実行し、候補・上流のCSV、要約、WAVの計142ファイルのSHA-256が直前の通過版と一致しました。[一様管](runs/uniform-tube-20261119-s/manifest.json)・[口端閉鎖](runs/glottal-oral-closure-20261119-j/manifest.json)・[交互周期の結合](runs/diplophonia-voiced-20261119-c/manifest.json)
- 交互周期の3ケースを研究ディレクトリと `/tmp` から実行し、候補・上流のCSV、設定、要約、結合ケースのWAVのSHA-256が一致しました。固定124 Hz・交互周期0.7の条件で奇数周期は平均817.44サンプル、偶数周期は730.94サンプル。上流系列との最大差はピーク比 `9.77×10⁻¹⁴` 未満でした。[対照](runs/diplophonia-control-20261119-b/manifest.json)・[交互周期](runs/diplophonia-fixed-20261119-b/manifest.json)・[結合](runs/diplophonia-voiced-20261119-b/manifest.json)
- 既存34ケースを再実行し、候補・上流のCSV、要約、WAVの計129ファイルのSHA-256が直前の通過版と一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と、上流の開口時間・ブロック分割テストが通過しました。[一様管](runs/uniform-tube-20261119-r/manifest.json)・[ピッチ変動と声道の結合](runs/pitch-voiced-20261119-d/manifest.json)・[フライ](runs/fry-strong-20261119-d/manifest.json)
- フライ5ケースを研究ディレクトリと `/tmp` から実行し、両方で候補・上流のCSV、設定、要約のSHA-256が一致しました。125 Hzの条件にフライ0.8を加えると63.4 Hzになり、第2パルスは周期位相0.38004〜0.38069で始まりました。上流の全観測系列との最大差はピーク比 `8.31×10⁻¹⁶` 未満です。[強いフライ](runs/fry-strong-20261119-c/manifest.json)・[重なる条件](runs/fry-overlap-20261119-c/manifest.json)・[低F0](runs/fry-low-f0-20261119-c/manifest.json)
- 既存29ケースを再実行し、候補・上流のCSV、要約、WAVの計114ファイルのSHA-256が直前の通過版と一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と、上流の `folds_held_apart_meet_for_less_of_the_cycle` が通過しました。[一様管](runs/uniform-tube-20261119-q/manifest.json)・[声門開大](runs/glottal-abduction-20261119-g/manifest.json)・[声道結合のピッチ](runs/pitch-voiced-20261119-c/manifest.json)
- ドリフトとビブラートの3ケースを `/tmp` から再実行し、候補・上流のCSV、設定、要約、結合ケースのWAVが初回とバイト一致しました。瞬時F0はどのケースでも上流と全サンプルで一致し、全系列の最大差はピーク比 `1.19×10⁻¹³` 未満でした。結合ケースは77・128フレーム分割でも同一のWAVと出力段CSVを生成しました。[ドリフト](runs/pitch-drift-20261119-b/manifest.json)・[ビブラート](runs/pitch-vibrato-20261119-b/manifest.json)・[結合](runs/pitch-voiced-20261119-b/manifest.json)
- 既存26ケースを再実行し、候補・上流のCSV、要約、WAVの計101ファイルのSHA-256が直前の通過版と一致しました。候補の `cargo fmt`、`cargo test`、`cargo clippy` と、上流の `output_does_not_depend_on_the_host_block_size` も通過しました。[一様管](runs/uniform-tube-20261119-p/manifest.json)・[PCM](runs/pcm-voiced-20261119-d/manifest.json)・[周期変動](runs/cycle-voiced-20261119-c/manifest.json)
- 声門の周期変動3条件を `/tmp` から再実行し、候補・上流のCSV、要約、声門結合のWAVが初回とバイト一致しました。ジッタだけでは周期長の標準偏差が9.96サンプル、シマーだけでは面積ピークの相対標準偏差が8.26%でした。上流との時系列差は各列のピーク比で最大 `1.23×10⁻¹³` 未満。[ジッタ](runs/cycle-jitter-20261119-b/manifest.json)・[シマー](runs/cycle-shimmer-20261119-b/manifest.json)・[結合](runs/cycle-voiced-20261119-b/manifest.json)
- 既存23ケースを再実行し、候補と取得済みの上流のCSV、要約、PCMのWAVが直前の通過版とバイト一致しました。乱数実装を共有した気道乱流3条件も含みます。[乱流の再検証](runs/turbulence-forward-20261119-g/manifest.json)・[声門の再検証](runs/glottal-abduction-20261119-e/manifest.json)・[PCMの再検証](runs/pcm-voiced-20261119-c/manifest.json)
- PCMの2条件を `/tmp` から再実行し、WAV・CSV・計測要約が初回とバイト一致しました。1・77・128・4096フレームの分割で出力が一致し、声門ケースの上流との最終PCM差はピーク比 `1.56×10⁻¹⁰` 未満でした。32 kHzのゲインは `2.54×10⁻⁵`（−91.89 dB）、声門ケースのピークは0.75。[一様管](runs/pcm-impulse-20261119-b/manifest.json)・[声門](runs/pcm-voiced-20261119-b/manifest.json)
- 既存21ケースの回帰比較が通過し、候補CSVと要約、取得済みの上流CSVが直前の通過版とバイト一致しました。CSVとPCMは同じ一サンプル更新を共有します。[固定分岐](runs/symmetric-junction-20261119-k/manifest.json)・[閉鎖移動](runs/sliding-closure-20261119-g/manifest.json)・[声門開大](runs/glottal-abduction-20261119-d/manifest.json)・[補償付き声門](runs/lung-voiced-20261119-c/manifest.json)
- 肺ポート3条件を `/tmp` から再実行し、候補・上流のCSVと計測要約が初回とバイト一致しました。固定開口で補償を加えると、声門下圧が3.8350から7.2835 cmH₂Oに上がりました。補償時の追加抵抗は直流で0.784532、4 kHzで実部8.01020 dyn·s/cm⁵。上流時系列の最大差は各列のピーク比で `3.58×10⁻¹³`、複素抵抗の独立式との差は最大 `3.59×10⁻¹²` です。[補償なし](runs/lung-uncompensated-20261119-b/manifest.json)・[補償あり](runs/lung-compensated-20261119-b/manifest.json)・[声門結合](runs/lung-voiced-20261119-b/manifest.json)
- 既存18ケースを再実行し、候補CSVと計測要約、取得済みの上流CSVが直前の通過版とバイト一致しました。[閉鎖移動](runs/sliding-closure-20261119-f/manifest.json)・[鼻腔](runs/nasal-open-20261119-d/manifest.json)・[声門開大](runs/glottal-abduction-20261119-c/manifest.json)・[閉口](runs/glottal-oral-closure-20261119-d/manifest.json)
- 声門ケースを `/tmp` から再実行し、通過した候補・上流のCSVと計測要約は初回通過とバイト一致しました。発声ゲートの最初の正値は35.31 ms、閉口後の平均絶対圧力差は発声時の22.5%。上流18系列の最大差は各列のピーク比 `2.63×10⁻¹³` でした。[開大の再実行](runs/glottal-abduction-20261119-b/manifest.json)・[閉鎖の再実行](runs/glottal-oral-closure-20261119-c/manifest.json)
- 口端閉鎖の再実行 `b` は、複数の回帰検証を並行していたときに `cargo run ... inspect` がSIGKILLで終了しました。各処理の終了後、同じケース・ソースで単独実行した `c` が通過しました。[中断記録](runs/glottal-oral-closure-20261119-b/manifest.json)・[再実行](runs/glottal-oral-closure-20261119-c/manifest.json)
- 第2段階までの16ケースを再検証し、全件が通過しました。候補CSV・計測要約と、採取済みの上流CSVが直前の通過版とバイト一致しました。[定常狭窄](runs/steady-quarter-20261119-f/manifest.json)・[閉鎖移動](runs/sliding-closure-20261119-e/manifest.json)・[乱流](runs/turbulence-forward-20261119-d/manifest.json)・[鼻腔](runs/nasal-open-20261119-c/manifest.json)
- 鼻腔3条件を `/tmp` から再実行し、候補と上流のCSV・計測要約が初回とバイト一致しました。軟口蓋の閉鎖でポート流量と鼻端放射はゼロ、開放時の鼻端ピークは口端の8.31%。上顎洞の頸部アドミタンスのピークは730 Hzで、独立近似の729.34 Hzに対応しました。上流との最大差は時系列のピーク比 `1.25×10⁻¹⁴`、独立した複素応答との差は最大 `5.13×10⁻⁶` でした。[閉鎖](runs/nasal-closed-20261119-b/manifest.json)・[切離](runs/nasal-open-detached-20261119-b/manifest.json)・[開放](runs/nasal-open-20261119-b/manifest.json)
- 単管、分岐、可動断面、定常狭窄、壁振動、閉鎖移動、乱流の既存13ケースを再実行しました。全件が通過し、候補CSV・計測要約と、採取済みの上流CSVが直前の通過版とバイト一致しました。[分岐](runs/symmetric-junction-20261119-h/manifest.json)・[壁振動](runs/network-wall-20261119-f/manifest.json)・[閉鎖移動](runs/sliding-closure-20261119-d/manifest.json)・[乱流](runs/turbulence-forward-20261119-c/manifest.json)
- `turbulence-forward-20261119-b`、`turbulence-reverse-20261119-b`、`turbulence-alternate-seed-20261119-b` は `/tmp` から再実行。各条件の候補・上流のCSVと計測要約は初回通過とバイト一致しました。既定シードの上流17系列との差は各列のピーク比で最大 `1.11×10⁻¹³`、独立計算との注入波形差は3条件で最大 `1.64×10⁻¹⁵` でした。[正流](runs/turbulence-forward-20261119-b/manifest.json)・[逆流](runs/turbulence-reverse-20261119-b/manifest.json)・[別シード](runs/turbulence-alternate-seed-20261119-b/manifest.json)
- 既存10ケースを再実行し、候補のCSVと計測要約、上流時系列がある場合はそのCSVも、直前の通過版とバイト一致しました。Rustのテストでは同じ枝に対する利得変更後もフィルタ状態が継続し、登録解除で注入圧力がゼロになることを確認しました。[単管](runs/uniform-tube-20261119-j/manifest.json)・[固定狭窄](runs/narrow-junction-20261119-g/manifest.json)・[壁振動](runs/network-wall-20261119-e/manifest.json)・[閉鎖移動](runs/sliding-closure-20261119-c/manifest.json)
- `sliding-closure-20261119-b` は `/tmp` からの再実行。57,600サンプルで、上流113系列との差は各系列のピーク比で最大 `1.82×10⁻¹²`。移動時の放射ピークは再開口時の0.394%。閉鎖中の肺側セルの平均圧力は駆動圧の99.998%、口側セルの最大絶対圧力は駆動圧の `5.51×10⁻⁷` でした。候補・上流のCSV、計測要約は初回通過とバイト一致しました。[初回](runs/sliding-closure-20261119-a/manifest.json)・[再実行](runs/sliding-closure-20261119-b/manifest.json)
- 既存の剛体・軟壁単管、固定分岐・狭窄、密閉管圧縮、放射端の開閉、定常狭窄2条件、グラフの壁振動を再計測しました。9ケースとも通過し、候補のCSVと計測要約は直前の通過版とバイト一致しました。[固定分岐](runs/symmetric-junction-20261119-f/manifest.json)・[放射端の開閉](runs/moving-aperture-20261119-e/manifest.json)・[定常狭窄](runs/steady-quarter-20261119-c/manifest.json)・[グラフの壁振動](runs/network-wall-20261119-d/manifest.json)
- `network-wall-20261119-c` は `/tmp` からの再実行。候補と上流の CSV、計測要約が初回通過とバイト一致しました。48,000サンプルの時系列の最大差は各系列のピーク比で、上流21系列が `1.79×10⁻¹⁴`、単管9系列が `9.74×10⁻¹⁵`。壁面放射はサンプル1、口端は39で始まりました。[初回](runs/network-wall-20261119-a/manifest.json)・[再実行](runs/network-wall-20261119-c/manifest.json)
- 順番に剛体・軟壁単管、固定分岐・狭窄、密閉管圧縮・放射端開閉、定常狭窄2条件の8ケースが通過し、候補の CSV は直前の通過版とバイト一致しました。上流のプローブで、放射なしの密閉管の流量表記が `-0` から `0` に変わりました。壁面放射が無効なら加算を行わないよう調整し、再実行では上流 CSV も従来とバイト一致しました。[最初の再検証](runs/sealed-cavity-20261119-d/manifest.json)・[修正後](runs/sealed-cavity-20261119-e/manifest.json)・[単管の再検証](runs/soft-wall-20261119-h/manifest.json)
- `steady-full-20261119-c` と `steady-quarter-20261119-a` は `/tmp` から実行。6 cmH₂Oの駆動圧で定常流量は243.66と249.80 cm³/s。上流16系列の最大絶対差は各系列のピークに対して最大 `2.19×10⁻¹³`、独立定常式との流量の相対差は最大 `2.38×10⁻¹⁰` でした。1セル条件の再実行では候補と上流の CSV、および要約がそれぞれ初回通過とバイト一致しました。[1セル再実行](runs/steady-full-20261119-c/manifest.json)・[1/4セル](runs/steady-quarter-20261119-a/manifest.json)
- `steady-full-20261119-a` は計測後に NumPy の真偽値を JSON に書き出せず停止しました。入力・出力のハッシュから記録を復元し、計測器の値を Python の組み込み型にそろえて再実行しました。候補・上流の両 CSV は再実行と同一で、ケースと判定基準は同じです。[初回失敗](runs/steady-full-20261119-a/manifest.json)・[初回通過](runs/steady-full-20261119-b/manifest.json)
- 剛体・軟壁単管、対称分岐、固定狭窄、密閉管圧縮、放射端開閉の6ケースを再検証し、候補の CSV は対応する変更前の実行とバイト一致しました。[剛体](runs/uniform-tube-20261119-g/manifest.json)・[軟壁](runs/soft-wall-20261119-g/manifest.json)・[対称分岐](runs/symmetric-junction-20261119-d/manifest.json)・[固定狭窄](runs/narrow-junction-20261119-d/manifest.json)・[密閉管圧縮](runs/sealed-cavity-20261119-c/manifest.json)・[放射端開閉](runs/moving-aperture-20261119-c/manifest.json)
- `sealed-cavity-20261119-b` は `/tmp` からの再実行。5%圧縮後の圧力は72,368.80 dyn/cm²で、観測した共通時系列は固定上流版と数値が一致。連続近似との差は1.030%、独立して畳み込みと圧力積分を行った場合の時系列差はピーク比 `5.62×10⁻¹⁴` 以内でした。平滑化だけを外した探索的な離散計算では、連続近似との差は0.00134%でした。[実行記録](runs/sealed-cavity-20261119-b/manifest.json)・[初回判定](runs/sealed-cavity-20261119-a/summary.json)
- `moving-aperture-20261119-b` では、放射端の閉鎖区間で枝流量がゼロになり、開き直した区間に流量と放射が復帰しました。共通時系列の上流との差は各系列のピーク比で最大 `1.36×10⁻¹⁴`。独立計算では閉口側から内側セルへ最大36.80 cm³/sが配分されました。[実行記録](runs/moving-aperture-20261119-b/manifest.json)
- 以前の剛体・軟壁単管、対称分岐、固定狭窄を再実行し、候補の CSV は変更前とバイト一致しました。[剛体](runs/uniform-tube-20261119-f/manifest.json)・[軟壁](runs/soft-wall-20261119-f/manifest.json)・[対称分岐](runs/symmetric-junction-20261119-c/manifest.json)・[固定狭窄](runs/narrow-junction-20261119-c/manifest.json)
- `symmetric-junction-20261119-b` と `narrow-junction-20261119-b` は `/tmp` からの再実行。左右の分岐枝・放射流量は両ケースとも一致し、口端放射はサンプル39で始まりました。上流の各系列のピークに対する最大絶対差は対称で `3.90×10⁻¹⁵`、固定狭窄で `3.24×10⁻¹⁴`。対称ケースの12周波数における独立離散応答との差は複素応答のピーク比で最大 `1.68×10⁻⁷` でした。固定狭窄については二方向の損失を時間領域で照合しました。[対称分岐の実行記録](runs/symmetric-junction-20261119-b/manifest.json)・[固定狭窄の実行記録](runs/narrow-junction-20261119-b/manifest.json)
- 並列 R–L の終端計算を単管と分岐で共有した後に再実行し、剛体・軟壁単管の両方で既存のCSVとバイト一致しました。軟壁の計測要約も一致しました。[剛体再検証](runs/uniform-tube-20261119-e/manifest.json)・[軟壁再検証](runs/soft-wall-20261119-e/manifest.json)
- `soft-wall-20261119-d` は軟壁一様管 48,000 サンプルの別ディレクトリ `/tmp` からの再実行。第1共鳴は剛体時の 483.13 Hz から 527.83 Hz へ移動しました。時間応答と独立線形計算の最大差は 0.263%。上流と比べた時系列の最大絶対差は、各系列のピークに対して最大 `4.17×10⁻¹⁵` です。端の圧力収支は正味流入のピークに対して最大 `1.22×10⁻¹⁶`。上流テストの共鳴は表示精度 0.01 Hz で5件とも一致しました。[初回通過](runs/soft-wall-20261119-c/summary.json)・[再実行](runs/soft-wall-20261119-d/manifest.json)
- `uniform-tube-20261119-c` で同じ実装の剛体管を再測定しました。条件 JSON と CSV は第1段階の `uniform-tube-20261119-b` とバイト一致し、JSON の数値も一致。剛体ケースの上流との照合範囲は共鳴ピークです。[剛体再検証](runs/uniform-tube-20261119-c/manifest.json)
- 軟壁の初回2件は上流観測プローブのビルド時に中断されました。`a` は panic 戦略、`b` はリンク時最適化の不一致です。上流の `release` に合わせた設定で修正し、ケース、合否基準、候補時系列は同じ条件を使用しました。[失敗 a](runs/soft-wall-20261119-a/manifest.json)・[失敗 b](runs/soft-wall-20261119-b/manifest.json)

## 未達の条件と次の作業

第2段階の完了判定では、分岐の正味流量と壁損失、密閉空洞の圧縮、定常狭窄の圧力差、加圧下の閉鎖解除後の過渡、シード付き乱流を登録ケースで再確認しました。鼻腔・側枝は固定形状での接続と放射までを検証しました。[分岐](runs/nasal-open-20261119-b/summary.json)・[密閉空洞](runs/sealed-cavity-20261119-h/summary.json)・[定常狭窄](runs/steady-full-20261119-g/summary.json)・[閉鎖解除](runs/sliding-closure-20261119-d/summary.json)・[乱流](runs/turbulence-reverse-20261119-c/summary.json)

第3段階の計画上の条件は通過しました。肺圧による発声開始、開大による消声、口端閉鎖による圧差低下、面積と流量の独立照合、固定声道のPCM出力を確認しました。写像を使うワニの形状と鳴き声は第7段階で比較します。[声帯開大](runs/glottal-abduction-20261119-i/summary.json)・[口端閉鎖](runs/glottal-oral-closure-20261119-j/summary.json)・[呼気の結合](runs/lung-voiced-20261119-h/summary.json)・[PCM](runs/pcm-voiced-20261119-g/summary.json)

第4段階の基準は、/i ɑ u/ の固定発声と有声遷移、基準10母音の線形応答・LPC・F0、隣接9遷移と上流の形状連続性テストで照合しました。/ɔ/ の高域の帯域幅2点は掃引内で欠測です。/ʌ/ → /ɝ/ の最小断面に見つかった段差は、上流と候補の双方で観測されました。[10母音の測定](runs/vowels-reference-20261119-b/summary.json)・[有声遷移](runs/vowel-motion-voice-vowels-20261119-c/summary.json)

第5段階の登録済みのIPA・英語発話・英語歌唱の条件は通過しました。歌唱では予定音素区間、実測の開閉・発声時刻、頭子音中の音高遷移、長音と短音・破裂音の語尾、最後の無音まで確認しました。未対応音素は計画JSONに出ます。例として `Strut` の /ɹ/ は発声未対応です。[歌唱計画](runs/song-plan-20261119-c/summary.json)・[歌唱の発声](notes/sung-voice.md)

第6段階の条件を確認しました。固定 /i/ のCLI・WASM・AudioWorkletと共通ケースのPCM・内部状態を照合し、英語発話と歌詞・MIDIによる歌唱をブラウザに接続しました。舌・唇の操作、IPA入力、音素と波形の時系列、選択時刻の断面・圧力・流量・声門波形・スペクトル、ケースの保存とCLIでの再実行を実ブラウザで検証しました。登録した16・32・44.1・48・96 kHzの固定発声を照合し、実時間IPAの割り当て削減も通過しました。96 kHzの減衰時に観測した処理時間の外れ値は調査候補に残しています。[固定WASM](runs/wasm-fixed-voice-20261119-realtime-regression/manifest.json)・[固定Worklet](runs/worklet-fixed-voice-20261119-tract-regression/manifest.json)・[手動調音と保存](runs/worklet-manual-case-export-20261119-live-ipa-regression/manifest.json)・[時系列](runs/worklet-ipa-timeline-20261119-b/manifest.json)・[スペクトル](runs/worklet-pcm-spectrum-20261119-live-ipa-regression/manifest.json)・[割り当て削減](notes/contour-buffer-reuse.md)・[96 kHz](notes/worklet-realtime-voice-96000.md)

研究ワークスペースから今回の比較を再現するコマンド。実行IDは新しいものに差し替えます。

```bash
python3 tools/measure_worklet_realtime.py worklet-rate-96000-native-local-1 --output-rate 96000 --native-only
python3 tools/measure_worklet_realtime.py worklet-rate-96000-browser-local-1 --output-rate 96000
```

第7段階の手動発声では、一度の体型切り替えについて目標の引き継ぎ、声道の初期化、適用フレーム、CLIでの再現を確認しました。最新の再実行 `manual-bodyswitch-20261120-repeat` は全12項目を通過し、固定上流とのPCMの最大絶対差は `7.28×10⁻¹²` でした。スコア再生中の体型変更とビート時刻の引き継ぎ、歌詞の派生言語、動物音声、操作・提示機能の対応表を引き続き確認します。[登録ケース](cases/worklet-manual-body-switch.json)・[修正前の判定](runs/manual-bodyswitch-20261120-b/summary.json)・[再実行](runs/manual-bodyswitch-20261120-repeat/manifest.json)

第7段階の韓国語は音節化と `불 풀 뿔.` の歌唱を照合した後、/k g/ を追加して `먹어` と `먹 어` を実時間で歌唱しました。`velar-stops-20261120-repeat` は全88項目を通過し、固定上流とのPCMの最大絶対差は `1.86×10⁻⁹` でした。ロシア語・中国語、動物音声、操作・提示機能の対応表も第7段階に残っています。[舌背閉鎖の登録ケース](cases/velar-stops.json)・[初回の失敗記録](runs/velar-stops-20261120-a/manifest.json)・[再実行記録](runs/velar-stops-20261120-repeat/manifest.json)

/n ŋ/ の追加で `국물` と `국 물` を歌唱し、鼻腔への流量と閉鎖セルの枝流量を照合しました。第2版の `lingual-nasals-20261120-repeat` は全80項目を通過し、固定上流との最大PCM絶対差は `2.33×10⁻¹⁰` でした。[登録ケース](cases/lingual-nasals.json)・[第1版の判定](runs/lingual-nasals-20261120-c/summary.json)・[再実行の記録](runs/lingual-nasals-20261120-repeat/manifest.json)

/j ɰ/ の追加で `빵야 ~` と `의사` を歌唱し、渡り音が母音の拍で終わることを照合しました。直近の `tongue-glides-20261120-repeat` は全69項目を通過し、固定上流との最大PCM絶対差は `7.45×10⁻⁹` でした。試した韓国語例の残りは /dʑ tɕ ɕ ɾ/ です。[登録ケース](cases/tongue-glides.json)・[再実行記録](runs/tongue-glides-20261120-repeat/manifest.json)

歯茎硬口蓋摩擦音 /ɕ ʑ/ を追加しました。成人男性の声門開大は子音中央で0.30225・0.09225 cm²、歯への圧力RMSは31.75・12.61 dyn/cm²でした。乱流係数0で狭窄と歯の音源登録を同じに保ったまま、圧力注入が0になりました。韓国語で試した音節化の例には /tɕ dʑ ɾ/ が残っています。[登録ケース](cases/alveolopalatal-fricatives.json)・[再実行の要約](runs/alveolopalatal-fricatives-20261120-repeat/summary.json)

/tɕ dʑ/ の発話と「아주 자 차 짜」の歌唱を照合しました。口腔の閉鎖に隣接する枝流量は0で、成人男性のIPA発話では開口から歯の乱流が活動するまで1.90・1.44 ms、声門の周期復帰まで80.31・73.52 msでした。[登録ケース](cases/alveolopalatal-affricates.json)・[再実行の要約](runs/alveolopalatal-affricates-20261120-repeat/summary.json)

歯茎の弾き音 /ɾ/ の発話と「싫어」の歌唱を照合しました。固定上流と候補は、話速を上げると /ɑɾɑ/ の最小断面が0→0.089→0.324 cm²に増え、成人男性の /iɾi/ では完全閉鎖が42.02 ms続きました。第1版で狭窄予測が外れた記録を保持しました。[第1版の結果](runs/alveolar-tap-20261120-a/summary.json)・[第2版ケース](cases/alveolar-tap-v2.json)・[第2版の再実行](runs/alveolar-tap-20261120-repeat/summary.json)

ロシア語歌詞の音素化と音節化を追加しました。デモ「Ночной ветер」の歌詞の16音節と16音符を照合しました。音響合成に残る /tʃ v x/ は歌唱計画に記録されています。中国語歌詞、動物音声、操作・提示機能の対応表も第7段階に残っています。[登録ケース](cases/russian-lyrics.json)・[再実行の要約](runs/russian-lyrics-20261120-repeat/summary.json)

唇歯摩擦音 /f v/ を追加しました。補間体型 /v/ では、話速1.0・1.3で唇歯付近に狭窄音源を登録した割合が89.5%・41.1%でした。ロシア語デモの歌唱計画を現在のCLIで再度確認し、音響未対応欄は /tʃ x/ になりました。中国語歌詞、動物音声、操作・提示機能の対応表も第7段階に残っています。[第2版ケース](cases/labiodental-fricatives-v2.json)・[再実行の結果](runs/labiodental-fricatives-20261120-repeat/summary.json)

軟口蓋摩擦音 /x/ を追加しました。男性 /ixi/ と /ɑxʲɑ/ は /ɑxɑ/ より舌背がそれぞれ1.007 cmと1.268 cm前にありました。/ɑxɑ/ は枝の境界、/ixi/ は面積上限により、中央区間に狭窄源が登録されませんでした。「ти́хо」の /x/ は第2拍直前の96 msで、ロシア語デモの16音節に残る音響未対応は /tʃ/ です。中国語歌詞、動物音声、操作・提示機能の対応表も第7段階に残っています。[第2版ケース](cases/velar-fricative-v2.json)・[再実行の結果](runs/velar-fricative-20261120-repeat/summary.json)

後部歯茎破擦音 /tʃ/ を追加しました。成人男女の /ɑtʃɑ/ はスペクトルで検出した摩擦が各60 msで、摩擦終了から母音まで0・10 msでした。ロシア語デモ「Ночной ветер」は、16音節・16音符・2句の計画と音声を照合し、未対応音素は空です。中国語歌詞、動物音声、操作・提示機能の対応表が第7段階に残っています。[登録ケース](cases/postalveolar-affricate.json)・[再実行の要約](runs/postalveolar-affricate-20261120-repeat/summary.json)

中国語歌詞の漢字と声調付きピンインの音節化、拍の割付け、代表4譜例のPCMを照合しました。「妈麻马骂吗」と同じ5声調をピンインで書いた譜面の163,200サンプルはビット一致し、「你好」の「好」の滑音は終端に100 msを使いました。音響計画の未対応は、調査用の「四是吃字人爱」では /ts tʂ ɻ ʂ ʔ/。鼻音韻尾では音節の `nasalLead`、/n ŋ/ の明示長、`closing` を記録しました。動物音声と操作・提示機能の対応表も第7段階の未完了項目です。[第2版のケース](cases/mandarin-lyrics-v2.json)・[再実行の結果](runs/mandarin-lyrics-20261120-repeat/summary.json)

鼻音韻尾の歌唱に、母音中の軟口蓋の開き、条件付きの舌体移動、句末の閉鎖保持を追加しました。「班」は同じ音節の通常鼻音の対照より鼻腔への通路が141.63 ms早く開き、終端20〜80 ms後の閉鎖率は100%でした。「东」は48 kHzと16 kHzで音量の局所的な低下を照合しました。中国語で調査した「四是吃字人爱」の音響未対応は /ts tʂ ɻ ʂ ʔ/。動物音声と操作・提示機能の対応表も第7段階に残っています。[第2版のケース](cases/mandarin-nasal-rhymes-v2.json)・[第2版の要約](runs/mandarin-nasal-rhymes-20261120-b/summary.json)

歯茎破擦音 /ts/ を追加しました。MIDI 57の単音譜で「词」は「资」より声門開大の指示が80.2 ms長く残り、周期発声は72.75 ms遅く戻りました。この実行時の診断句「四是吃字人爱」の音響未対応は /tʂ ɻ ʂ ʔ/ でした。[登録ケース](cases/alveolar-affricate.json)・[歌唱計画の未対応欄と計測結果](runs/alveolar-affricate-20261120-repeat/summary.json)

そり舌摩擦音 /ʂ/ を追加しました。成人男性の発話では /s/ より狭窄が歯から1.672 cm遠く、歯側への雑音圧力は30.10から4.30 dyn/cm² RMSに下がりました。「是」の核 /ʅ/ が反りを保って周期発声することを照合しました。この実行時の診断句の音響未対応は /tʂ ɻ ʔ/ でした。[登録ケース](cases/retroflex-fricative.json)・[歌唱計画の未対応欄と計測結果](runs/retroflex-fricative-20261120-repeat/summary.json)

そり舌破擦音 /tʂ/ を追加しました。「知 zhī」「吃 chī」の自然な声母長と、112 msにそろえた対照を照合しました。等長対では舌先と口腔最小断面の時系列が一致し、有気で周期復帰が72.81 ms遅れました。この実行時の診断句の音響未対応は /ɻ ʔ/ でした。[登録ケース](cases/retroflex-affricate.json)・[歌唱計画の未対応欄と計測結果](runs/retroflex-affricate-20261120-repeat/summary.json)

そり舌接近音 /ɻ/ を追加しました。「日」の拍から舌尖母音が反りを引き継ぎ、「哪儿」の児化韻尾は母音の末尾52 msを占めました。句中では境界をまたぐ声門周期が4.54 msで、メリスマの韻尾は第2音符に移りました。この実行時の診断句の音響未対応は /ʔ/ でした。[登録ケース](cases/retroflex-approximant.json)・[未対応欄と測定](runs/retroflex-approximant-20261120-repeat/summary.json)

声門閉鎖音 /ʔ/ を追加しました。成人男性の標準 /ɑʔɑ/ は中央の口腔最小断面が5.333 cm²で、声門流量RMSは先行母音の約0.0154%に下がりました。「人爱」は「爱」の /ʔ/ が拍前48 msを占め、拍の約23 ms後に声門の周期発声が戻りました。「四是吃字人爱」の6音節は音響未対応欄が空になり、診断ケースの照合を終えました。第7段階には鳴禽とその他の動物音声、Web MIDI・三次元表示・録画・デュエットの対応表が残っています。[登録ケース](cases/glottal-stop.json)・[実測と未対応欄](runs/glottal-stop-20261120-repeat/summary.json)

片側の鳴管音源が完了しました。基準の指定2,600 Hzに対し実測は2,603.321 Hzで、周期表と独立積分の周期比から2,603.319 Hzを予測できました。ゲートを閉じる間も変位は基準と一致し、ゲートの時定数は192 kHzで2.602 ms、48 kHzで10.406 msでした。[登録ケース](cases/songbird-syrinx.json)・[数値と判定](runs/songbird-syrinx-20261120-repeat/summary.json)

左右の鳴管と共通気管の結合を照合しました。片側から両側へ設定を変えると、同じ側の開口列を保ったまま枝流量が変わりました。両側の放射に2,600 Hzと3,900 Hzのビンのピークが見え、無呼気では開口中も圧力・流量・放射が0でした。[登録ケース](cases/songbird-airway.json)・[実測と独立計算](notes/songbird-airway.md#実装と実測)

鳴禽の持続音をPCMへ接続しました。48 kHzでは開始指示73が制御フレーム128で呼気に反映され、PCMは135から出ました。停止指示11567は11584で適用されました。増幅の条件では振幅制限が942フレームに作用し、固定上流のPCMと一致しました。[登録ケース](cases/songbird-sustain-pcm.json)・[比較と観測時刻](runs/songbird-sustain-pcm-20261120-repeat/summary.json)

`flute` のキー補間と移調を照合しました。途中停止の17,291フレームで目標音高が手動の3,000 Hzへ戻り、17,344で平滑値が変化しました。標準条件では呼気開始前に非ゼロのPCMが出ることも記録しました。[登録ケース](cases/songbird-flute.json)・[観測と残る仮説](notes/songbird-flute.md#実装と実測)

`trill`、`chirps`、`buzz` を追加しました。`trill` の18周期、`chirps` の重なりにおける定義順の効果、`buzz` の初回と定常の間隔、切り替えに伴う張力・純度・音程差の目標復帰を照合しました。[登録ケース](cases/songbird-calls.json)・[改訂の条件](cases/songbird-calls-v2.json)・[実測と残る差](notes/songbird-calls.md#実装と実測)

アメリカアリゲーターとアフリカゾウは持続音と全コールを公式CLIの末尾まで照合しました。第7段階には動物音声のWASM・AudioWorkletと操作画面の接続、Web MIDI・三次元表示・録画・デュエットの対応表が残っています。[アリゲーターの全区間の判定](runs/alligator-dance-20261120-a/summary.json)・[ゾウの全区間の判定](runs/elephant-squeak-20261120-a/summary.json)

鳴禽の持続音と停止を実時間AudioWorkletで照合しました。48・96 kHzの加工前PCM 108,000フレームが固定上流・CLIとビット一致し、呼気・気嚢圧・左右の開口、実断面積、流量のCLI比較も最大差0でした。ブラウザの起動待ちを初回レンダー前に限定し、開始後の描画間隔を128フレームにそろえました。第7段階にはブラウザの鳴禽コールと他の動物の接続、Web MIDI・三次元表示・録画・デュエットの対応表が残っています。[実装と差の記録](notes/worklet-songbird-sustain.md)・[最後に確認した再実行](runs/worklet-songbird-20261120-final/manifest.json)

鳴禽の `flute` の代表ケースは、48 kHzの実時間ブラウザで32,160フレームのPCMと544観測点を比較しました。途中停止17,291で目標音高が3,000 Hzへ戻り、平滑音高は次の制御更新17,344で下がり始めました。CLI・固定上流とPCMがビット一致し、別ディレクトリからの再実行も通過しました。従来の持続音の48・96 kHzはWAVと全観測値が一致しました。第7段階には周期コールと切り替えのブラウザ比較、他の動物の接続、操作・提示機能の対応表が残っています。[読解と測定](notes/worklet-songbird-flute.md)・[最後に確認したコールの実行](runs/worklet-songbird-flute-20261120-repeat/manifest.json)・[持続音回帰](runs/worklet-songbird-sustain-flute-regression-20261120/summary.json)

`trill` を48 kHzの実時間ブラウザで照合しました。呼気目標の立ち上がりは18回で、間隔は2,944または3,008フレーム。76,800フレームのPCMは固定上流・CLIとビット一致しました。Chrome・ヘッドレスシェルの再試行は18項目が通過しました。処理時間p95はヘッドレスシェルの別実行で3 msとなり、2.67 msの予算を超えました。観測頻度を変える性能対照、残る鳴禽コールのブラウザ比較、他の動物音声・操作機能の対応が未達です。[読解と差の記録](notes/worklet-songbird-trill.md)・[最後に確認した実行](runs/worklet-songbird-trill-20261120-shell-retry/manifest.json)・[処理時間が超過した実行](runs/worklet-songbird-trill-20261120-shell-check/summary.json)

`chirps-44100` の実時間ブラウザ比較を完了しました。48,510フレームがCLI・固定上流とビット一致し、762観測点における制御と主な音響状態も一致しました。宣言順と時刻順をCLIで対照し、入力差は22,016の呼気、放射の差は22,022、PCMが判定閾値を超えたのは22,028であることを確認しました。第7段階の残りは `buzz` とコール切り替えの実時間比較、観測頻度の性能対照、他の動物音声と操作・提示機能です。[読解と順序の対照](notes/worklet-songbird-chirps.md)・[最後に確認した実行](runs/worklet-songbird-chirps-20261120-stages/manifest.json)

`buzz-96000` の実時間ブラウザ比較を完了しました。呼気目標0.6の上向き交差は8回で、初回間隔6,080と定常6,720フレームが独立計算の格子上の結果と一致しました。CLIと105,600 PCMフレームでビット一致し、固定上流との差は減衰中の1サンプルで約 `5.56e-22` でした。最初の放射差が気嚢圧0の出力195にあり、正の呼気目標より先に出ることを記録しました。第7段階ではコール切り替え、観測頻度の性能対照、他の動物音声、操作・提示機能が残ります。[読解と差の記録](notes/worklet-songbird-buzz.md)・[最後に確認した実行](runs/worklet-songbird-buzz-20261120-repeat/manifest.json)

`buzz → trill` の実時間ブラウザ比較を完了しました。57,600 PCMフレームがCLI・固定上流とビット一致し、913観測点で主要な状態も一致しました。切り替えの指示時刻9,601で手動目標が復帰し、9,664で平滑値と新しい音高目標が変わりました。切り替えを省いた対照との差は9,665で放射に現れ、9,676でPCMの判定閾値を超えました。これで鳴禽の持続音、全4コールの代表ケース、途中停止・切り替えを実時間ブラウザで照合しました。第7段階には鳴禽の観測頻度と処理時間の対照、他の動物音声のブラウザ接続、操作・提示機能が残ります。[読解と対照](notes/worklet-songbird-switch.md)・[最後に確認した実行](runs/worklet-songbird-switch-20261120-repeat/manifest.json)

次は上流の `engine_set_creature`・`engine_set_gate`、`seal::control`、再実装の `SealVoice::render` を開きます。ウェッデルアザラシの持続・停止の代表ケースをWASMとAudioWorkletに接続し、呼気・肺圧と口端・鼻端・壁面の放射、加工前PCMをCLIと照合します。固定上流とCLIの基準を研究ディレクトリから再実行します。[上流の種切り替え](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L465)・[上流アザラシの制御](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/seal.rs#L50)・[再実装の出力経路](crates/vocal-core/src/seal_voice.rs#L210)・[持続音のケース](cases/seal-sustain-pcm.json)

```bash
python3 tools/measure_seal_sustain_pcm.py seal-sustain-before-worklet-1
```

研究ディレクトリで声門閉鎖音を再演します。

```bash
python3 tools/measure_glottal_stop.py glottal-stop-local-1
```

研究ディレクトリでそり舌接近音を再演します。

```bash
python3 tools/measure_retroflex_approximant.py retroflex-approximant-local-1
```

研究ディレクトリでそり舌破擦音を再演します。

```bash
python3 tools/measure_alveolar_affricate.py retroflex-affricate-local-1 --retroflex
```

研究ディレクトリでそり舌摩擦音を再演します。

```bash
python3 tools/measure_retroflex_fricative.py retroflex-fricative-local-1
```

研究ディレクトリで歯茎破擦音を再演します。

```bash
python3 tools/measure_alveolar_affricate.py alveolar-affricate-local-1
```

研究ディレクトリで鼻音韻尾を再演します。

```bash
python3 tools/measure_mandarin_nasal_rhymes.py mandarin-nasal-rhymes-local-1
```

研究ディレクトリでロシア語デモを再演する場合のコマンドです。実行IDは新しい名前を使います。

```bash
python3 tools/measure_postalveolar_affricate.py postalveolar-affricate-local-1
```

手動発声と体型の回帰コマンド。

```bash
python3 tools/measure_worklet_manual_articulation.py worklet-manual-body-baseline-local-1 --case-export
python3 tools/measure_body_fixed_voice.py body-fixed-voice-local-1
```

デュエットは二声の音源・観測列・歌詞・三次元頭部を同じ再生時計に接続し、口元の文字を表示します。輪郭の残像、表情、頭部の回転、圧力の輪、気流の軌跡、乱流源を前後シークを含めて照合しました。デュエットの別体型での乱流源、VP8経路、他ブラウザでの録画、物理機器と他のMIDI演奏経路が残っています。[操作と表示の対応表](notes/interaction-presentation.md)・[三次元頭部](notes/duet-heads.md)

研究ディレクトリからWebMを再実行します。研究用の仮想環境を有効にして、新しい実行IDを指定します。

```bash
python3 tools/measure_worklet_song_recording.py worklet-song-webm-local-1 --webm
```

研究ディレクトリでデュエットの再生時計を再実行します。

```bash
python3 tools/measure_duet_transport.py duet-transport-local-1
```

研究ディレクトリでデュエットのテレメトリを再実行します。

```bash
python3 tools/measure_duet_telemetry.py duet-telemetry-local-1
```

研究ディレクトリから、デュエットの歌詞を再実行します。

```bash
python3 tools/measure_duet_words.py duet-words-local-1
```

研究ディレクトリから、デュエットの三次元頭部を再実行します。

```bash
python3 tools/measure_duet_heads.py duet-heads-local-1
```

研究ディレクトリから、デュエットの口元の歌詞を再実行します。

```bash
python3 tools/measure_duet_mouth_words.py duet-mouth-words-local-1
```

研究ディレクトリから、デュエットの輪郭の残像を再実行します。

```bash
python3 tools/measure_duet_head_echoes.py duet-head-echoes-local-1
```

研究ディレクトリから、デュエットの表情と頭部の動きを再実行します。

```bash
python3 tools/measure_duet_head_expression.py duet-head-expression-local-1
```

研究ディレクトリから、デュエットの三次元の圧力表示を再実行します。

```bash
python3 tools/measure_duet_head_pressure.py duet-head-pressure-local-1
```

### 三次元の圧力表示の検証

- 完了した項目。固定上流のテレメトリ・表情テスト6件と、固定上流の `Beams.poly`、CLIの断面、Chromiumの960・390 CSS pxを比較した28項目が通過した。二声の閉鎖・開口、停止時の中立色、前後シークの最初の色、表示の切り替えも照合した。[事前登録](cases/duet-head-pressure.json)・[読解と実測](notes/duet-head-pressure.md)
- 最後に確認した実行。修正後と再実行で28件すべて合格。固定上流の3桁キャッシュが46,080サンプルに保持した形状差は、キャッシュを通さない直接計算と比較して説明できた。採取失敗2件の記録も保存した。[最後の結果](runs/duet-head-pressure-20261120-repeat/summary.json)・[マニフェスト](runs/duet-head-pressure-20261120-repeat/manifest.json)・[初回計測](notes/duet-head-pressure.md#初回計測と再実行)
- 保存先。二声のCHTLとリリース版WASMは内蔵から読む。圧力比較は短区間のため内蔵で実行した。高密度の系列や長時間の録画を行う場合は、共通計測スクリプトの外部直接出力を使う。[保存先と容量管理](../../../docs/plans/chimera-research-rebuild-plan.md#保存先と容量管理)

### 気流の粒子の検証

- 完了した項目。二声に独立した200粒子を実装し、符号付き流量・断面積を使う積分、投影、寿命、再配置を固定上流と独立計算に照合した。960・390 CSS pxの実ブラウザで、停止、再開、前後シークの最初の描画、次のフレーム、表示切替を確認した。[登録ケース](cases/duet-head-airflow.json)・[読解と実測](notes/duet-head-airflow.md)
- 最後に確認した実行。気流は2回とも20項目に合格。再実行で前後シーク後の3,176線分について、粒子の更新とブラウザの描画バッファを照合した。圧力の回帰28項目、固定上流の9試験、候補WASMの25試験も通過した。[気流の再実行](runs/duet-head-airflow-20261120-repeat/summary.json)・[圧力の回帰](runs/duet-head-pressure-20261120-airflow-regression/summary.json)・[気流のマニフェスト](runs/duet-head-airflow-20261120-repeat/manifest.json)

### 乱流源の三次元位置の検証

- 完了した項目。候補のCLIが記録した枝配置を公演に添え、声門と口腔を区別して乱流線分を描いた。固定上流と同じ格子で枝の位置、乱数、強度の閾値、口端の打ち切りを比較した。[読解と実測](notes/duet-head-turbulence.md)・[登録ケース](cases/duet-head-turbulence.json)
- 最後に確認した実行。Chromiumの2画面幅で乱流の20項目を2回確認し、圧力28、気流20、テレメトリ34項目の回帰に合格。テレメトリの回帰の成果は作業用ディスクに直接出力した。研究ディレクトリで `python3 tools/measure_duet_head_turbulence.py duet-head-turbulence-local-1` から再実行する。[乱流の再実行](runs/duet-head-turbulence-20261120-repeat/summary.json)・[テレメトリの回帰](runs/duet-telemetry-20261120-noise-layout-regression/manifest.json)

### 実時間IPAの体型切り替えの検証

- 完了した項目。子どもと混合体型の `ɑpɑ` で、各65時点の測定線49本、全音響セル、PCMをCLIと照合した。960・390 CSS pxで体型を逆の順に切り替え、前回の表示が消え、最初の断面とセル数が新しい体型に対応することを確認した。CLIから採った17軸の姿勢で固定上流の形状を検証した。[体型別の登録ケース](cases/worklet-tract-3d-body.json)・[読解と実測](notes/worklet-tract-3d-body.md)
- 最後に確認した実行。体型別の3回の実行で各38項目、男性体型の回帰で47項目、固定上流の体型・形状・閉鎖の11試験に合格した。体型別の成果物は作業用RTL9210B-CGに直接出力した。[体型別の最終判定](runs/worklet-tract-3d-body-20261120-final/summary.json)・[外部保存先とハッシュ](runs/worklet-tract-3d-body-20261120-final/manifest.json)・[男性体型の回帰](runs/worklet-tract-3d-live-20261120-body-regression/summary.json)
- 未達の条件。固定上流とのPCMには最大 `4.66×10⁻¹⁰` の差が残り、最初に差が出た出力フレームを記録した。[上流との差](notes/worklet-tract-3d-body.md#実測)

### VP8/Opusの形式選択と歌唱録画

- 完了した項目。MP4とVP9/Opusを拒否する条件で、候補と固定上流の `Clip` がVP8/Opusを選ぶことを問い合わせ順と復号結果で照合した。候補の二拍の歌唱では加工前WAVがCLI・先行VP9・MP4と一致し、唇閉鎖2区間と母音2区間の輪郭、ブラウザ内の再生、録画前と録画中の中止、再録画も確認した。[登録ケース](cases/worklet-song-recording-vp8.json)・[読解と実測](notes/worklet-song-recording-vp8.md)
- 最後に確認した実行。Chrome 157のVP8は2回とも48項目を通過。VP9の対照45項目、MP4の回帰33項目も通過した。空白が長かった試行の復号PTSと作画時刻を保存し、候補と固定上流ともに作画段階で大きな空白が始まった例を確認した。録画の成果物は作業用RTL9210B-CGへ直接出力した。[VP8の最終実行](runs/worklet-song-vp8-20261120-chrome-final/summary.json)・[最終実行のマニフェスト](runs/worklet-song-vp8-20261120-chrome-final/manifest.json)・[VP9の対照](runs/worklet-song-vp9-20261120-chrome-control/summary.json)・[MP4の回帰](runs/worklet-song-vp8-mp4-regression-20261120/summary.json)
### Firefoxの歌唱録画

- 完了した項目。Firefoxの対応判定を使い、候補と固定上流の `Clip` がVP8/Opusを選んだことを、問い合わせと実ファイルで照合した。候補のPCM全91,200フレームはCLIと、WAVと119時点の格子は固定Chromiumと一致した。復号した拍、無音、閉鎖と母音の4区間、ブラウザ内の再生、収録前と収録中の中止・再録画を確認した。[登録ケース](cases/worklet-song-recording-firefox.json)・[読解と実測](notes/worklet-song-recording-firefox.md)
- 最後に確認した実行。Firefox 157の初回・再実行は各46項目、共有の音声時刻計測を変更した後のChrome VP8は48項目に合格した。Firefoxの出力は約23 fpsで、復号音声の最初のフレームに312サンプルの破棄が反映された。計測用Firefoxと出力は作業用RTL9210B-CGに配置した。[Firefoxの再実行](runs/worklet-song-firefox-20261120-repeat/summary.json)・[マニフェスト](runs/worklet-song-firefox-20261120-repeat/manifest.json)・[Chromeの回帰](runs/worklet-song-firefox-vp8-regression-20261120/summary.json)
- 未達の条件。Firefoxで映像の間隔が50 msになる処理段は未分離。[録画の比較](notes/worklet-song-recording-firefox.md#実測と残る差)

### 固定上流の3D頭部の歌唱録画

- 完了した項目。通常の歌唱画面からJoyfulを分岐音声と3D頭部で保存し、28音の予約、計測表示の抑制と復帰、映像と音声、完走・中止後のトラックを照合した。初回コピーの時点で古い頭部に計測が残り、復号した先頭画像にも現れた。[事前登録](cases/worklet-song-recording-upstream-head.json)・[実測と先頭画像](notes/worklet-song-recording-upstream-head.md#実測)
- 最後に確認した実行。最終版は13項目、研究版の三次元断面録画の回帰は33項目を通過した。最終版の包絡相関は0.9962、復号音声と描画時のF0差は11.5セント未満だった。配信時のWASM採取の誤りと修正を保存した。動画と復号データはRTL9210B-CGへ直接出力した。[最終結果](runs/worklet-song-upstream-head-20261120-final/summary.json)・[最終マニフェスト](runs/worklet-song-upstream-head-20261120-final/manifest.json)・[研究版の回帰](runs/worklet-song-upstream-head-20261120-tract-regression/summary.json)
- 改善候補。上流の先頭画像の計測表示を防ぐため、最初の計測なし描画を待つ案を記録した。[観測と対照案](notes/worklet-song-recording-upstream-head.md#実測)

### Web MIDIによる鍵盤歌唱

- 完了した項目。既存のMIDI入力から鍵盤歌唱を選べるようにし、歌詞カーソル、タグ付きの調音と音高、押下と解放をRustの共通経路で処理した。仮想MIDIの `la ma -` で閉唇、母音の継続、保持音への復帰、最後の解放後の減衰を確認した。[事前登録](cases/worklet-midi-song.json)・[読解と実測](notes/worklet-midi-song.md)
- 最後に確認した実行。最終試行16項目、手動MIDIの回帰16項目、コア15件、WASM25件が通過。採用フレームから再実行したCLIと加工前WAVは173,824フレームがビット一致した。UTF-8変換をWorkletの外へ移した準備エラーの修正も記録した。大きな成果物はRTL9210B-CGへ直接保存した。[最終判定](runs/worklet-midi-song-20261120-final/summary.json)・[マニフェスト](runs/worklet-midi-song-20261120-final/manifest.json)・[手動MIDIの回帰](runs/worklet-midi-song-20261120-manual-regression/summary.json)
- 未達の条件。最初の押下の4 msについて、計画生成と声道更新の寄与は未分離。末子音のある語尾、物理機器、動物のMIDI経路とビートボックスの低音が比較範囲に残る。[差の記録](notes/worklet-midi-song.md#比較結果)・[操作と表示の対応表](notes/interaction-presentation.md)
- 次に開くファイルは `cases/worklet-midi-beatbox.json`、上流の `src/ui/store.ts`・`crates/chimera/src/control/beat_player.rs`、研究版のWebの `src/fixed-processor.ts` と `tools/measure_beatbox_transport.py`。同じ仮想入力で鼻に抜ける低音とパターンが採用する音番号を比較する。手動MIDIの回帰は `python3 tools/measure_worklet_midi.py worklet-midi-voice-local-1`、鍵盤歌唱は `python3 tools/measure_worklet_midi_song.py worklet-midi-song-local-1` で再実行する。[次のケース](cases/worklet-midi-beatbox.json)



## Web MIDIによるビートボックスの低音とハム

- 完了した項目。研究版の実時間ビートへWeb MIDIを接続し、保持音への復帰、最後に押した音でハムのセルを編集する操作、同じ採用フレームからのCLI再実行を実装した。固定上流の画面とネイティブEngineで、保持中の40への復帰、閉唇と鼻端への流れ、2.2秒の音番号47のハムを照合した。[事前登録](cases/worklet-midi-beatbox.json)・[読解と実装](notes/worklet-midi-beatbox.md)
- 最後に確認した実行。登録17項目、手動MIDIと鍵盤歌唱の回帰が各16項目、ビートのテンポ・停止・再開の回帰が13項目合格した。Rustのコア15件とWASM25件も通過した。研究版WAVは139,200フレームがCLIとビット一致。正式試行の全フレームを判定した後、2本の高密度CSVを214.3 MBから25.6 MBに抜粋した。RTL9210B-CGに元のハッシュと再実行に使うWAV・ケースを保存した。[結果](runs/worklet-midi-beatbox-20261121-b/summary.json)・[マニフェスト](runs/worklet-midi-beatbox-20261121-b/manifest.json)・[初回の障害](runs/worklet-midi-beatbox-20261121-a/failure.json)・[手動MIDIの回帰](runs/worklet-midi-beatbox-20261121-manual-regression/summary.json)・[実時間ビートの回帰](runs/worklet-midi-beatbox-20261121-transport-regression/summary.json)・[鍵盤歌唱の回帰](runs/worklet-midi-beatbox-20261121-singing-regression/summary.json)
- 未達の条件。固定上流と研究版の同時刻の鼻端流量の最大差は3.04×10⁻¹¹ cm³/sで、最初に差が生じる演算は未特定。実機のWeb MIDIと許可画面、低音と有声打音を同時に鳴らす比較、動物へのMIDI経路が残る。
- 次に開くファイルは `cases/worklet-midi-songbird.json`、固定上流の `src/ui/store.ts` の `creatureKeyHz`、`src/ui/components/BestiaryPanel.tsx` の `KeysMode`、`crates/chimera/src/creatures/songbird.rs` の `def`。研究版側は `web/prototypes/chimera-research/src/creature-processor.ts` と `tools/measure_worklet_songbird.py` から読む。鳴禽の持続音と停止の基準を48・96 kHzで再実行し、25項目が合格した。[鳴禽の最新基準](runs/worklet-midi-songbird-20261121-baseline/summary.json)。持続音の既存条件は環境を確認して `python3 tools/measure_worklet_songbird.py worklet-songbird-sustain-midi-baseline-local-1 songbird-sustain-before-browser-1` で再測定する。完了したビートの再計測は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=402653184 python3 tools/measure_worklet_midi_beatbox.py worklet-midi-beatbox-local-1`。[次の登録ケース](cases/worklet-midi-songbird.json)

## Web MIDIによる鳴禽の持続音

- 完了した項目。固定上流のBestiaryと研究版の画面で、60 → 67 → 60への持ち替え、全解放、0と127のオクターブ折り返しを照合した。実時間AudioWorkletが採用した音番号とフレームを保存し、同じRustの処理でCLIから再実行できるようにした。[登録条件](cases/worklet-midi-songbird.json)・[読解と検証](notes/worklet-midi-songbird.md)
- 最後に確認した実行。正式17項目、持続音回帰25項目、コール回帰18項目、Rust40件が合格。48 kHzの144,000フレームが候補CLIとビット一致し、固定上流ともサンプル差0。同一フレームの押下と解放で呼気が0でも短い音が生じ、口腔食道腔の容積追従を0にすると無音になった。3本の高密度CSVは全フレームの判定後に180.3 MBから37.4 MBへ抜粋してRTL9210B-CGに保存した。[正式結果](runs/worklet-midi-songbird-20261121-rev2/summary.json)・[マニフェスト](runs/worklet-midi-songbird-20261121-rev2/manifest.json)・[改訂前の判定](runs/worklet-midi-songbird-20261121-final/summary.json)
- 未達の条件。左右の流量に最初の微差が出たフレームは10,114・10,115。最大差は2.98×10⁻¹³ cm³/sで、内部刻みのどの演算が最初かは未特定。実機と許可画面、動物コールの開始・移調・再発音、他の動物の鍵盤入力の比較が残る。
- 次に `cases/worklet-midi-songbird-call.json` と、固定上流の `src/ui/store.ts` にある `noteOn`・`playCall`、`crates/chimera/src/creatures/voice.rs` にある `play_call`・`eval_call`、研究版の `crates/vocal-core/src/songbird_voice/call.rs` を開く。コールの現行動作は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 python3 tools/measure_worklet_songbird_flute.py worklet-midi-songbird-call-baseline-local-1 songbird-flute-before-worklet-1` で再計測できる。[コールの登録条件](cases/worklet-midi-songbird-call.json)・[コールの最新基準](runs/worklet-midi-songbird-20261121-flute-regression/summary.json)

## Web MIDIによる鳴禽コールの開始と再発音

- 完了した項目。鳴禽のMIDIパネルで持続音と4種のコールを選べるようにした。fluteでは60と67でフレーズ全体を移調し、解放後も呼気包絡が進むこと、次の押下で先頭へ戻ること、コールの最後の制御点から50 msを過ぎた境界で自動終了することを固定上流と照合した。[登録条件](cases/worklet-midi-songbird-call.json)・[読解と検証](notes/worklet-midi-songbird-call.md)
- 最後に確認した実行。初回と別の作業ディレクトリからの再実行で12項目合格。研究版WAVの117,600フレームはCLIとビット一致し、固定上流とのPCMの差も0。鳴禽持続音MIDI17項目、既存flute18項目、Rust40件が通過。高密度CSVは全フレームの判定後に108.3 MBから33.1 MBへ抜粋した。[再実行の結果](runs/worklet-midi-songbird-call-20261121-final/summary.json)・[マニフェスト](runs/worklet-midi-songbird-call-20261121-final/manifest.json)
- 未達の条件。候補と固定上流では最初の押下7フレーム後から左右ポート流量に微差があり、最大差は1.35×10⁻¹³ cm³/s。差が最初に生じる内部演算は未特定。実機MIDI、flute以外の鳴禽コールの個別MIDI比較、他の動物への接続が残る。
- 次に `cases/worklet-midi-seal.json`、固定上流の `src/ui/store.ts` の `creatureKeyHz` と `crates/chimera/src/creatures/seal.rs` の `def`、候補の `crates/vocal-core/src/seal_voice.rs` と `web/prototypes/chimera-research/src/creature-processor.ts` を開く。ウェッデルアザラシ持続音の48・96 kHz基準は44項目が合格した。再実行は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=402653184 python3 tools/measure_worklet_seal_sustain.py worklet-midi-seal-baseline-local-1 seal-sustain-before-worklet-1`。[次の登録条件](cases/worklet-midi-seal.json)・[アザラシの基準結果](runs/worklet-midi-seal-20261121-baseline/summary.json)

## Web MIDIによるウェッデルアザラシの持続音

- 完了した項目。鳴禽と共通の鍵盤写像をアザラシの持続音とCLIに接続した。固定版の通常画面で保持音への復帰、音域外の127の折り返し、解放後の呼気を照合し、固定Rustで声門・放射・PCMを測った。[事前登録](cases/worklet-midi-seal.json)・[読解と検証](notes/worklet-midi-seal.md)
- 最後に確認した実行。正式11項目、鳴禽MIDI回帰17項目、アザラシのzap回帰72項目、Rust40件が合格。48 kHzの139,200フレームがブラウザとCLIでビット一致し、固定上流とのPCM差も0。独立肺圧計算の初回の位相ずれは補正し、変更前の判定も保存した。全フレーム判定後、CSV2本を120.5 MBから34.1 MBへ抜粋し、RTL9210B-CGに保存した。[正式結果](runs/worklet-midi-seal-20261121-final/summary.json)・[マニフェスト](runs/worklet-midi-seal-20261121-final/manifest.json)・[初回の結果](runs/worklet-midi-seal-20261121-a/summary.json)
- 未達の条件。放射の時間微分に最大9.78×10⁻⁸ cm³/s²の差があり、最初の微差はフレーム6,291の壁面放射に現れた。内部演算の位置は未特定。物理MIDI、アザラシコールと他種への鍵盤入力が残る。
- 次に `cases/worklet-midi-seal-call.json`、上流の `creatures/seal.rs` のLaser chirpと `creatures/voice.rs` の `play_call`、候補の `crates/vocal-core/src/seal_voice/call.rs` と `tools/measure_worklet_seal_zap.py` を開く。既存のzapは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=402653184 python3 tools/measure_worklet_seal_zap.py worklet-midi-seal-call-baseline-local-1 seal-zap-before-worklet-1` で再計測できる。[次の登録条件](cases/worklet-midi-seal-call.json)・[既存コールの最新結果](runs/worklet-midi-seal-20261121-zap-regression/summary.json)

## Web MIDIによるウェッデルアザラシのコール

- 完了した項目。アザラシのMIDIパネルに4種のコールの選択を追加した。Laser chirpでは60・67を523.25 Hzと783.99 Hzの開始目標に割り当て、離鍵後の発声、下降の移調、再発音での目標の切り替え、自然終了を固定上流と照合した。押下と離鍵の採用フレームをCLIで再実行できる。[登録条件](cases/worklet-midi-seal-call.json)・[読解と検証](notes/worklet-midi-seal-call.md)
- 最後に確認した実行。正式11項目、持続音MIDI回帰11項目、鳴禽コールMIDI回帰12項目、既存zap回帰72項目、Rust40件が合格。ブラウザとCLIは43,200フレームのWAVがビット一致し、固定上流とのPCM最大差は1.39×10⁻¹⁷。CSV2本は全フレームで判定後、36.2 MBから13.9 MBに抜粋した。独立計算の初回の不足設定と出力も保存した。[正式結果](runs/worklet-midi-seal-call-20261121-final/summary.json)・[マニフェスト](runs/worklet-midi-seal-call-20261121-final/manifest.json)・[初回の停止](runs/worklet-midi-seal-call-20261121-a/failure.json)・[既存zap回帰](runs/worklet-midi-seal-call-20261121-zap-regression/summary.json)
- 未達の条件。最初の押下19フレーム後に壁面放射で微差が出た。放射の時間微分の差は最大6.57×10⁻⁸ cm³/s²で、内部の演算は未特定。物理MIDI、Laser chirp以外のアザラシコールの個別MIDI比較、アリゲーターとゾウへの接続が残る。
- 次に `cases/worklet-midi-alligator.json`、固定上流の `src/ui/store.ts` の `creatureKeyHz` と `creatures/alligator.rs` の `def`、候補の `crates/vocal-core/src/airway/alligator.rs` の `AlligatorVoice::set_params` を開く。既存のアリゲーター固定発声は86項目が合格した。基準の再実行は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 python3 tools/measure_worklet_alligator_fixed_voice.py worklet-midi-alligator-baseline-local-1 alligator-fixed-before-worklet-1`。[アリゲーターの登録条件](cases/worklet-midi-alligator.json)・[最新基準](runs/worklet-midi-alligator-20261121-baseline/summary.json)

## Web MIDIによるアメリカアリゲーターの持続音

- 完了した項目。アリゲーターの鍵盤を12〜120 Hzへ割り当て、60→67→60の持ち替え、全解放、キー0の約16.35 Hzへの折り返しを固定上流と照合した。画面から保存した採用フレームをCLIで再実行し、同じ声門と音響出力を得られるようにした。[登録条件](cases/worklet-midi-alligator.json)・[読解と検証](notes/worklet-midi-alligator.md)
- 最後に確認した実行。正式10項目、固定発声86項目、Bellow 234項目、アザラシコールMIDI 11項目、Rust40件が合格。ブラウザとCLIのWAVは144,000フレームでビット一致し、固定RustとのPCM最大差は9.31×10⁻¹⁰。全内部サンプルで判定した後、CSV2本を268.6 MBから72.9 MBへ抜粋してRTL9210B-CGに保存し、成果14ファイルのSHA-256を照合した。[正式結果](runs/worklet-midi-alligator-20261121-coordinate/summary.json)・[マニフェスト](runs/worklet-midi-alligator-20261121-coordinate/manifest.json)・[Bellowの基準](runs/worklet-midi-alligator-20261121-bellow-regression/summary.json)
- 未達の条件。固定版との最初の微差は押下47内部サンプル後の声門の駆動差圧と流量にあり、放射の時間微分の最大差は3.93×10⁻⁷ cm³/s²。差を生む個々の演算と、物理MIDI・許可画面、各コールとゾウへの鍵盤入力の比較が残る。
- 次に、Bellowの移調と再発音の登録条件、固定上流の `src/ui/store.ts` の `creatureKeyHz` と `noteOn`、`crates/chimera/src/creatures/{alligator,voice}.rs`、研究版の `crates/vocal-core/src/airway/alligator/call.rs` を開く。既存のBellowは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 python3 tools/measure_worklet_alligator_bellow.py worklet-midi-alligator-call-baseline-local-1 alligator-bellow-before-worklet-1` で再計測できる。[Bellowの登録条件](cases/worklet-midi-alligator-call.json)

## Web MIDIによるアメリカアリゲーターのBellow

- 完了した項目。MIDIパネルにアリゲーター4種のコールを接続した。Bellowを60・67で移調し、呼気目標1→0、実測呼気1→0.9780の再発音、離鍵後の継続、自然終了で音高とchaosの目標が元へ戻ることを固定上流と照合した。採用フレームをCLIで再実行できる。[登録条件](cases/worklet-midi-alligator-call.json)・[読解と検証](notes/worklet-midi-alligator-call.md)
- 最後に確認した実行。正式75項目、持続音MIDI回帰10項目、既存Bellow回帰234項目、Rust40件が合格。候補のブラウザとCLIは163,200フレームでビット一致し、固定Rustとの差は最大5.82×10⁻¹¹。初回の終了後の呼気予測の不合格も全時系列とともに保存した。正式実行のCSVは317.5 MBから141.1 MBへ抜粋しRTL9210B-CGに保存した。成果17ファイルのSHA-256と測定窓を照合した。[最新結果](runs/worklet-midi-alligator-call-20261121-retained/summary.json)・[保存記録](runs/worklet-midi-alligator-call-20261121-retained/manifest.json)・[初回の判定](runs/worklet-midi-alligator-call-20261121-a/summary.json)
- 未達の条件。最初の微差は呼気上昇から6内部サンプル後の気管入口圧に現れた。枝・壁・節点のどの演算で生じたかは未特定。物理MIDI・許可画面、Bellow以外のアリゲーターコールの個別MIDI比較、ゾウへの鍵盤入力が残る。
- 次に、ゾウの持続音の登録条件、固定上流の `src/ui/store.ts` の `creatureKeyHz`、`crates/chimera/src/creatures/elephant.rs` の `Elephant::control` と `def`、研究版の `crates/vocal-core/src/airway/elephant.rs` と `tools/measure_worklet_elephant_fixed_voice.py` を開く。既存の固定発声は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_worklet_elephant_fixed_voice.py worklet-midi-elephant-baseline-local-1 elephant-fixed-before-worklet-1` で再計測できる。[ゾウの登録条件](cases/worklet-midi-elephant.json)・[合格済みの固定発声](runs/worklet-elephant-fixed-20261120-repeat/summary.json)

## Web MIDIによるアフリカゾウの持続音

- 完了した項目。声門の8〜45 Hzへ鍵盤を割り当てた。音の持ち替え、全解放、MIDI 0の約8.18 Hzへの折り返し、鼻の弁と鼻先の流量を固定上流と照合した。通常画面の採用フレームを保存し、CLIから同じ音と状態を再実行できる。[登録条件](cases/worklet-midi-elephant.json)・[読解と検証](notes/worklet-midi-elephant.md)
- 最後に確認した実行。正式14項目、既存の固定発声回帰80項目、Bellow MIDI回帰75項目、Rust40件が合格。ブラウザとCLIの170,400フレームはビット単位で一致し、固定上流とのPCM最大差は9.31×10⁻¹⁰。肺ポートの最初の流量の微差は運動量項の丸めを独立式で再現した。CSVは172.5 MBから103.5 MBに絞ってRTL9210B-CGへ保存し、成果16ファイルのハッシュと測定窓を照合した。[正式結果](runs/worklet-midi-elephant-20261121-lung/summary.json)・[マニフェスト](runs/worklet-midi-elephant-20261121-lung/manifest.json)・[固定発声の回帰](runs/worklet-midi-elephant-20261121-fixed-regression/summary.json)・[BellowのMIDI回帰](runs/worklet-midi-elephant-20261121-bellow-regression/summary.json)
- 未達の条件。枝の演算順を統一したときに後続の微差がどこまで変わるかは未検証。物理MIDIと許可画面、ゾウのコールMIDI、他種の残るコールの個別比較が残る。初回の起動は測定器のインポートで停止し、経緯を読解ノートに記録した。
- 次に、Rumbleの登録条件、固定上流の `crates/chimera/src/creatures/elephant.rs` の `def` と `voice.rs` の `eval_call`、研究版の `crates/vocal-core/src/airway/elephant/call.rs` と `tools/measure_worklet_elephant_rumble.py` を開く。固定時刻から開始するRumbleは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=603979776 ../../.venv/bin/python tools/measure_worklet_elephant_rumble.py worklet-midi-elephant-call-baseline-local-1 elephant-rumble-20261120-repeat` で再計測できる。[Rumbleの登録条件](cases/worklet-midi-elephant-call.json)・[既存Rumbleの合格結果](runs/worklet-elephant-rumble-20261120-repeat/summary.json)

## Web MIDIによるアフリカゾウのRumble

- 完了した項目。ゾウの3コールをMIDIパネルに接続し、Rumbleの開始目標17.52 Hz・26.25 Hz、離鍵後の自動呼気、再発音時の声門位相と鼻先流量、自然終了時の目標復帰を固定上流と照合した。ブラウザで保存した押下・離鍵の採用フレームをCLIで再実行できる。[登録条件](cases/worklet-midi-elephant-call.json)・[読解と検証](notes/worklet-midi-elephant-call.md)
- 最後に確認した実行。正式16項目、既存Rumble回帰68項目、持続音MIDI回帰14項目、Rust40件が合格。ブラウザとCLIは223,200フレームでビット一致し、固定上流との差は最大3.73×10⁻⁹。最初の肺ポート流量の微差を、直列枝と壁を含む独立式と運動量項を置き換えた対照で再現した。CSVは229.6 MBから76.7 MBに絞ってRTL9210B-CGに保存し、成果17ファイルのハッシュと測定窓を照合した。[正式結果](runs/worklet-midi-elephant-call-20261121-onset/summary.json)・[実行マニフェスト](runs/worklet-midi-elephant-call-20261121-onset/manifest.json)・[既存Rumble回帰](runs/worklet-midi-elephant-call-20261121-rumble-regression/summary.json)・[持続音MIDI回帰](runs/worklet-midi-elephant-call-20261121-held-regression/summary.json)
- 未達の条件。最初の運動量項の差は再現した。後続フレームで他の演算がどの程度加わるかは未検証。物理MIDI・許可画面、TrumpetとSqueakの個別MIDIによる弁挙動、他種の残る個別コールが残る。
- 次に、Trumpetの登録条件、固定上流の `crates/chimera/src/creatures/elephant.rs` のTrumpet定義と `voice.rs` の `eval_call` の音高ロール、研究版の `crates/vocal-core/src/airway/elephant/call.rs` と `tools/measure_worklet_elephant_trumpet.py` を開く。既存のTrumpetは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 ../../.venv/bin/python tools/measure_worklet_elephant_trumpet.py worklet-midi-elephant-trumpet-baseline-local-1 elephant-trumpet-20261120-repeat` で再計測できる。[Trumpetの登録条件](cases/worklet-midi-elephant-trumpet.json)・[固定時刻から開始するTrumpetの合格結果](runs/worklet-elephant-trumpet-20261120-repeat/summary.json)

## Web MIDIによるアフリカゾウのTrumpet

- 完了した項目。通常画面でTrumpetにMIDI 60・67を送り、固定上流が16.35・24.50 Hzを受け取ることを確認した。押下と離鍵の時刻を固定して番号を交換し、両実装でそれぞれ弁と放射の全CSVとPCMが一致した。弁の目標380→520→470 Hzと、差圧から得た弁状態を独立計算で照合した。[登録条件](cases/worklet-midi-elephant-trumpet.json)・[読解と検証](notes/worklet-midi-elephant-trumpet.md)
- 最後に確認した実行。正式15項目、固定Trumpet回帰142項目、Rust40件が合格。ブラウザとCLIの127,200フレームはビット一致し、固定上流とのPCM最大差は9.31×10⁻¹⁰。通常・交換対照のCSV4本を356.6 MBから94.9 MBに絞ってRTL9210B-CGへ保存し、成果22ファイルのハッシュを照合した。[正式結果](runs/worklet-midi-elephant-trumpet-20261121-final/summary.json)・[保存記録](runs/worklet-midi-elephant-trumpet-20261121-final/manifest.json)・[回帰](runs/worklet-midi-elephant-trumpet-20261121-regression/summary.json)
- 未達の条件。最初の微差は呼気上昇の3フレーム後の肺ポート流量に現れた。ここで差を生む演算は未特定。Squeakの個別MIDIと鼻の弁、物理MIDI・許可画面、他種の残る個別コールが残る。
- 次に、Squeakの登録条件、固定上流の `crates/chimera/src/creatures/elephant.rs` のSqueak定義と `crates/chimera/src/sources/valves.rs` の `LipReed::next`、研究版の `crates/vocal-core/src/airway/elephant/call.rs` と `tools/measure_worklet_elephant_squeak.py` を開く。固定時刻のSqueakは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 ../../.venv/bin/python tools/measure_worklet_elephant_squeak.py worklet-midi-elephant-squeak-baseline-local-1 elephant-squeak-20261120-repeat` で再計測できる。[Squeakの登録条件](cases/worklet-midi-elephant-squeak.json)・[既存Squeakの合格結果](runs/worklet-elephant-squeak-20261120-repeat/summary.json)

## Web MIDIによるアフリカゾウのSqueak

- 完了した項目。既存のMIDI入口からSqueakを鳴らし、240 ms後の再発音で実断面が1.88556→1.80359 cm²になることを固定上流・独立式と照合した。両発音後40 msの各1,920フレームは面積下限が実断面を決めた。音番号だけを交換した対照で、両実装のそれぞれのPCM・全CSVが一致した。[登録条件](cases/worklet-midi-elephant-squeak.json)・[読解と検証](notes/worklet-midi-elephant-squeak.md)
- 最後に確認した実行。正式18項目、固定Squeak回帰136項目、TrumpetのMIDI回帰15項目、Rust40件が合格。ブラウザとCLIの64,800フレームはビット一致し、固定上流とのPCM最大差は9.31×10⁻¹⁰。CSV4本を163.8 MBから56.9 MBへ絞ってRTL9210B-CGに保存し、成果22ファイルのハッシュを照合した。[正式結果](runs/worklet-midi-elephant-squeak-20261121-final/summary.json)・[実行記録](runs/worklet-midi-elephant-squeak-20261121-final/manifest.json)・[固定Squeakの回帰](runs/worklet-midi-elephant-squeak-20261121-fixed-regression/summary.json)・[Trumpetの回帰](runs/worklet-midi-elephant-squeak-20261121-trumpet-regression/summary.json)
- 未達の条件。最初の微差は呼気上昇の5フレーム後の肺ポート流量に現れた。今回の値でその微差を生む演算は未特定。弁を初期化した対照は同じ差圧を使った一更新で、気道を再計算した場合は未検証。物理MIDIと許可画面、アリゲーターなどの残る個別コールのMIDI確認が残る。
- 次に、Growlの登録条件と固定上流の `crates/chimera/src/creatures/alligator.rs` の `def`・`control`、研究版の `crates/vocal-core/src/airway/alligator/call.rs` と `tools/measure_worklet_alligator_growl.py` を開く。固定時刻のGrowlは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 ../../.venv/bin/python tools/measure_worklet_alligator_growl.py worklet-midi-alligator-growl-baseline-local-1 alligator-growl-before-worklet-1` で再計測できる。[Growlの登録条件](cases/worklet-midi-alligator-growl.json)・[既存Growlの合格結果](runs/worklet-alligator-growl-20261120-final/summary.json)

## Web MIDIによるアメリカアリゲーターのGrowl

- 完了した項目。通常画面からMIDI 60・67でGrowlを鳴らし、開始目標32.7032・48.9994 Hzを確認した。再発音で呼気目標は0.39778から1に戻り、平滑呼気は0.49615から0.54914へ上昇した。声門位相が進み、口先実断面は約1.848896 cm²を保った。各離鍵後の発声と、コール終了時の手動目標への復帰を確認した。[登録条件](cases/worklet-midi-alligator-growl.json)・[読解と検証](notes/worklet-midi-alligator-growl.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各76項目、BellowのMIDI回帰75項目、固定Growl回帰285項目、Rust40件が合格。正式実行でブラウザ・CLI・固定RustのPCMは79,200フレームがビット一致し、ブラウザとCLIの55観測列は差0だった。CSV2本を152.8 MBから86.7 MBに絞ってRTL9210B-CGへ保存し、成果17ファイルのSHA-256を照合した。[正式結果](runs/worklet-midi-alligator-growl-20261121-final/summary.json)・[実行記録](runs/worklet-midi-alligator-growl-20261121-final/manifest.json)・[Bellowの回帰](runs/worklet-midi-alligator-growl-20261121-bellow-regression/summary.json)・[固定Growlの回帰](runs/worklet-midi-alligator-growl-20261121-fixed-regression/summary.json)
- 未達の条件。総放射に最初の微差を生む演算は未特定。初回のPCMには2フレームで最大1.82×10⁻¹²の差が残った。物理MIDIと許可画面、HissやWater danceなど個別コールのMIDI確認が残る。[初回の差](runs/worklet-midi-alligator-growl-20261121-a/summary.json)
- 次に、Hissの登録条件、固定上流の `crates/chimera/src/creatures/alligator.rs` の `def`・`control` と `crates/chimera/src/creatures/mammal.rs` の `mammal_noise`、研究版の `tools/measure_worklet_alligator_hiss.py` を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=805306368 ../../.venv/bin/python tools/measure_worklet_alligator_hiss.py worklet-midi-alligator-hiss-baseline-local-1 alligator-hiss-before-worklet-1` で再計測する。[Hissの登録条件](cases/worklet-midi-alligator-hiss.json)・[既存の比較](notes/worklet-alligator-hiss.md)

## Web MIDIによるアメリカアリゲーターのHiss

- 完了した項目。通常のMIDI画面でHissの乱流3系列を内部2サンプル分ずつ採取できるようにした。採用時刻を保って音番号を交換し、候補と上流それぞれの全PCMと内部系列が一致した。両離鍵後の窓では有声ゲートと口腔乱流が0で、乱流を止めた固定上流のPCM RMSは4窓で通常時の0.0581〜0.0633%だった。[登録条件](cases/worklet-midi-alligator-hiss.json)・[読解と検証](notes/worklet-midi-alligator-hiss.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各89項目、固定Hiss回帰311項目、GrowlのMIDI回帰76項目、Rust40件が合格した。正式実行の115,200フレームはブラウザとCLIでビット一致し、1,800時点の61観測列は差0。CSV3本を347.6 MBから148.3 MBに絞ってRTL9210B-CGに保存し、成果20ファイルのSHA-256を照合した。[正式結果](runs/worklet-midi-alligator-hiss-20261121-final/summary.json)・[実行と保存記録](runs/worklet-midi-alligator-hiss-20261121-final/manifest.json)・[固定Hissの回帰](runs/worklet-midi-alligator-hiss-20261121-fixed-regression/summary.json)・[GrowlのMIDI回帰](runs/worklet-midi-alligator-hiss-20261121-growl-regression/summary.json)
- 未達の条件。固定上流との差は最初に口端流量・壁の体積流量・総放射に現れ、PCMの最大差は3.64×10⁻¹²だった。最初の差を生んだ演算、物理MIDIと許可画面、Water danceなど残るコールのMIDI比較は未検証。
- 次に、Water danceの登録条件と、固定上流の `crates/chimera/src/creatures/alligator.rs` の `def`、研究版の `crates/vocal-core/src/airway/alligator/call.rs` と `tools/measure_worklet_alligator_dance.py` を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_alligator_dance.py worklet-midi-alligator-dance-baseline-local-1 alligator-dance-before-worklet-1` で再計測する。[Water danceの登録条件](cases/worklet-midi-alligator-dance.json)・[既存の音響比較](notes/worklet-alligator-dance.md)

## Web MIDIによるアメリカアリゲーターのWater dance

- 完了した項目。通常画面からMIDI 36・41を送り、声門の周期周波数16.09・21.46 Hzを確認した。声門面積・気管端圧・咽頭入口圧と壁面・口端・鼻端の流量ピークは16・22 Hz。総流量の時間差分の段で32・44 Hzが最大になり、PCMにも同じピークが現れた。離鍵後の発声と、再発音で粗さ目標が0に戻る瞬間の呼気・声門位相の連続性を確認した。[登録条件](cases/worklet-midi-alligator-dance.json)・[読解と検証](notes/worklet-midi-alligator-dance.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各95項目、固定Water dance回帰288項目、HissのMIDI回帰89項目、Rust40件が合格。ブラウザとCLIは156,000フレームでビット一致し、2,438時点の55観測列は差0。CSV2本を328.1 MBから235.2 MBに絞ってRTL9210B-CGへ保存し、成果17ファイルのSHA-256を照合した。[正式結果](runs/worklet-midi-alligator-dance-20261121-final/summary.json)・[実行と保存記録](runs/worklet-midi-alligator-dance-20261121-final/manifest.json)・[固定時刻の回帰](runs/worklet-midi-alligator-dance-20261121-fixed-regression/summary.json)・[HissのMIDI回帰](runs/worklet-midi-alligator-dance-20261121-hiss-regression/summary.json)
- 未達の条件。固定上流との最初の微差は肺流量・口端流量・総放射に現れ、PCMの最大差は3.73×10⁻⁹だった。最初の差を生んだ演算、物理MIDIと許可画面、鳴禽・アザラシの残るコールの個別比較は未検証。
- 次に、ウェッデルアザラシのDescending trillの登録条件、固定上流の `crates/chimera/src/creatures/seal.rs` の `def`、研究版の `crates/vocal-core/src/seal_breath.rs` と `tools/measure_worklet_seal_trill.py` を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_seal_trill.py worklet-midi-seal-trill-baseline-local-1 seal-trill-before-worklet-1` で再計測する。[Descending trillの登録条件](cases/worklet-midi-seal-trill.json)・[既存の音響比較](notes/worklet-seal-trill.md)

## Web MIDIによるウェッデルアザラシのDescending trill

- 完了した項目。MIDI 60・67で音高目標を523.25・783.99 Hzに移調し、同じ経過時間のパルス周波数目標が一致することを確認した。第2音の2.948秒で音高目標が40 Hzに達し、パルス周波数目標は8.535 Hzから6 Hzまで下がった。再発音時は位相を引き継いだ一更新の式が実測肺圧に一致し、位相を0から始める対照と差が出た。[登録条件](cases/worklet-midi-seal-trill.json)・[読解と検証](notes/worklet-midi-seal-trill.md)
- 最後に確認した実行。第1版は独立ゲートだけが不合格で、制御時計の丸めに起因すると確認した。その閾値を改訂した第2版は15項目、固定Trill回帰65項目、Laser chirpのMIDI回帰13項目、Rust40件が合格した。ブラウザとCLIは288,000フレームでビット一致し、4,500時点の31列は差0。CSVを277.0 MBから147.8 MBに絞ってRTL9210B-CGに保存し、正式実行の成果15ファイルのSHA-256を照合した。[初回の判定](runs/worklet-midi-seal-trill-20261121-a/summary.json)・[正式結果](runs/worklet-midi-seal-trill-20261121-final/summary.json)・[実行と保存記録](runs/worklet-midi-seal-trill-20261121-final/manifest.json)・[固定時刻の回帰](runs/worklet-midi-seal-trill-20261121-fixed-regression/summary.json)・[Laser chirpの回帰](runs/worklet-midi-seal-trill-20261121-zap-regression/summary.json)
- 未達の条件。固定上流との最初の微差は壁面流量と総放射にあり、正式実行のPCMの最大差は1.42×10⁻¹⁴。最初の差を生む演算、物理MIDIと許可画面、アザラシと鳴禽の残るコールのMIDI比較は未検証。
- 次に、U whistleの登録条件、固定上流の `crates/chimera/src/creatures/seal.rs` の `def`、研究版の `tools/measure_worklet_seal_whistle.py` の音高の谷の計測を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_seal_whistle.py worklet-midi-seal-whistle-baseline-local-1 seal-whistle-before-worklet-1` で再計測する。[U whistleの登録条件](cases/worklet-midi-seal-whistle.json)・[既存の音響比較](notes/worklet-seal-whistle.md)

## Web MIDIによるウェッデルアザラシのU whistle

- 完了した項目。MIDI 60・67で目標の谷は191.058・286.263 Hz、平滑値の谷は193.616・290.096 Hzで、両音とも6.667 ms遅れた。対数IIRは両方の谷のフレームを再現し、離鍵後の発声と再発音時の呼気・音高の追従を確認した。[登録条件](cases/worklet-midi-seal-whistle.json)・[読解と検証](notes/worklet-midi-seal-whistle.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各25項目、固定時刻のWhistle回帰101項目、TrillのMIDI回帰15項目、Rust40件が合格した。ブラウザとCLIは115,200フレームがビット一致し、1,800時点の29列の差は0。CSVを102.0 MBから69.0 MBに絞ってRTL9210B-CGへ保存し、正式実行の成果15ファイルのSHA-256を照合した。[正式結果](runs/worklet-midi-seal-whistle-20261121-final/summary.json)・[保存記録](runs/worklet-midi-seal-whistle-20261121-final/manifest.json)・[固定時刻の回帰](runs/worklet-midi-seal-whistle-20261121-fixed-regression/summary.json)・[TrillのMIDI回帰](runs/worklet-midi-seal-whistle-20261121-trill-regression/summary.json)
- 未達の条件。固定上流との差は壁面流量と総放射に最初に現れ、正式実行のPCMの最大差は1.39×10⁻¹⁷だった。最初の差を作る演算、物理MIDIと許可画面、残る動物コールのMIDI比較は未検証。
- 次に、Chugの登録条件、固定上流の `crates/chimera/src/creatures/seal.rs` の `def`、研究版の `tools/measure_worklet_seal_chug.py` の声門・呼気パルス周期の計測を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_seal_chug.py worklet-midi-seal-chug-baseline-local-1 seal-chug-before-worklet-1` で再計測する。[Chugの登録条件](cases/worklet-midi-seal-chug.json)・[既存の音響比較](notes/worklet-seal-chug.md)

## Web MIDIによるウェッデルアザラシのChug

- 完了した項目。MIDI 24・31の声門周期は64.197・96.369 Hzで、呼気パルスの実測周波数は両音とも11.029 Hzだった。離鍵後の呼気ゲートは約1で、パルス外の肺圧は5 dyn/cm²以下だった。再発音時に呼気と声門の位相が進み、第2音の終盤で周期倍率のジッターを除いたRMSが0.02126から0.00708へ下がった。アザラシの4コールの個別MIDI照合を終えた。[登録条件](cases/worklet-midi-seal-chug.json)・[読解と検証](notes/worklet-midi-seal-chug.md)
- 最後に確認した実行。初回は計測器が肺圧の手動目標列を読み込まず停止した。その修正後、作業ツリーと`/tmp`から各17項目、固定時刻のChug回帰88項目、Rust40件が合格した。ブラウザとCLIは96,000フレームがビット一致し、1,500時点の33列は差0。CSVを93.1 MBから78.2 MBに絞ってRTL9210B-CGへ保存し、正式実行の成果15ファイルのSHA-256を照合した。[初回の記録](runs/worklet-midi-seal-chug-20261121-a/manifest.json)・[正式結果](runs/worklet-midi-seal-chug-20261121-final/summary.json)・[保存記録](runs/worklet-midi-seal-chug-20261121-final/manifest.json)・[固定時刻の回帰](runs/worklet-midi-seal-chug-20261121-fixed-regression/summary.json)
- 未達の条件。固定上流との差は壁面流量・総放射に最初に現れ、正式PCMの最大差は7.28×10⁻¹²だった。最初の演算箇所、物理MIDIと許可画面、Canary trillなど鳴禽の残るコールのMIDI比較は未検証。
- 次に、Canary trillの登録条件、固定上流の `crates/chimera/src/creatures/songbird.rs` の `trill` と `def`、研究版の `tools/measure_worklet_songbird_trill.py` のパルス時刻の照合を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_songbird_trill.py worklet-midi-songbird-trill-baseline-local-1 songbird-trill-before-worklet-1` で再計測する。[Canary trillの登録条件](cases/worklet-midi-songbird-trill.json)・[既存の合格結果](runs/worklet-songbird-trill-20261120-repeat/summary.json)

## Web MIDIによる鳴禽のCanary trill

- 完了した項目。鍵盤で最初の上昇音の範囲が移り、第1音は再発音まで9パルス、第2音は18パルスだった。離鍵後の両窓で2回・3回の立ち上がりと左右からの流量を確認した。再発音の平滑呼気と音高を直前の値から独立に再現し、開口×0.03 cm²は全フレームで枝の断面と一致した。[登録条件](cases/worklet-midi-songbird-trill.json)・[読解と検証](notes/worklet-midi-songbird-trill.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各17項目、固定時刻のTrill回帰18項目、Flute phraseのMIDI回帰14項目、Rust40件に合格した。ブラウザ・CLI・固定Rustは正式実行の115,200 PCMフレームでビット一致し、1,800時点の17観測列はブラウザとCLIの差0。CSVを103.8 MBから83.0 MBに絞ってRTL9210B-CGへ保存した。[正式結果](runs/worklet-midi-songbird-trill-20261121-final/summary.json)・[保存記録](runs/worklet-midi-songbird-trill-20261121-final/manifest.json)・[固定時刻の回帰](runs/worklet-midi-songbird-trill-20261121-fixed-regression/summary.json)・[Flute phraseの回帰](runs/worklet-midi-songbird-trill-20261121-flute-regression/summary.json)
- 未達の条件。押下6内部サンプル後の総放射の微差を生む演算は未特定。初回の上流とのPCM最大差は1.14×10⁻¹³だった。物理MIDIと許可画面、Chirp cascadeとFinch buzzの個別MIDI比較が残る。[初回結果](runs/worklet-midi-songbird-trill-20261121-a/summary.json)
- 次に、Chirp cascadeの登録条件、固定上流の `crates/chimera/src/creatures/songbird.rs` の `chirp_keys` と `crates/chimera/src/creatures/voice.rs` の `eval_call`、研究版の `tools/measure_worklet_songbird_chirps.py` のキー順の対照を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_songbird_chirps.py worklet-midi-songbird-chirps-baseline-local-1 songbird-chirps-before-worklet-1` で再計測する。[Chirp cascadeの登録条件](cases/worklet-midi-songbird-chirps.json)・[既存の合格結果](runs/worklet-songbird-chirps-20261120-repeat/summary.json)

## Web MIDIによる鳴禽のChirp cascade

- 完了した項目。MIDI 60・67でコールを移調し、再発音直前の平滑呼気と音高から次の1制御更新を再現した。離鍵後も左右の流量が残った。キーを時刻順に並べ替えた対照では、押下から23,680フレームでまず呼気と気嚢圧が分岐し、19フレーム後にPCM差が閾値を超えた。音高目標の分岐は両音ともそれより後だった。[登録条件](cases/worklet-midi-songbird-chirps.json)・[読解と検証](notes/worklet-midi-songbird-chirps.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各20項目、固定時刻のChirps回帰21項目、TrillのMIDI回帰17項目、Rust40件が合格した。ブラウザとCLIの105,600 PCMフレームはビット一致し、1,650時点の17列の差は0。4本のCSVを合計160.0 MBから128.3 MBに絞ってRTL9210B-CGに保存し、正式実行の21成果物のSHA-256を照合した。[正式の結果](runs/worklet-midi-songbird-chirps-20261121-final/summary.json)・[実行と保存記録](runs/worklet-midi-songbird-chirps-20261121-final/manifest.json)・[固定時刻の回帰](runs/worklet-midi-songbird-chirps-20261121-fixed-regression/summary.json)・[Trillの回帰](runs/worklet-midi-songbird-chirps-20261121-trill-regression/summary.json)
- 未達の条件。固定上流と総放射が最初に分岐するのは押下6内部サンプル後で、差を生む演算箇所は未特定。PCM差は減衰中の1点で最大8.88×10⁻¹⁶。物理MIDI機器と許可画面、Finch buzzの個別MIDI比較が残る。
- 次に、Finch buzzの登録条件、固定上流の `crates/chimera/src/creatures/songbird.rs` の `buzz_keys`、研究版の `tools/measure_worklet_songbird_buzz.py` の閾値交差の照合を開く。固定時刻の比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_songbird_buzz.py worklet-midi-songbird-buzz-baseline-local-1 songbird-buzz-before-worklet-1` で再計測する。[Finch buzzの登録条件](cases/worklet-midi-songbird-buzz.json)・[既存の合格結果](runs/worklet-songbird-buzz-20261120-repeat/summary.json)

## Web MIDIによる鳴禽のFinch buzz

- 完了した項目。両音で最初の呼気目標間隔3,008フレーム、後続3,328／3,392フレームを確認した。第1音7回・第2音8回の目標交差は有理数計算の格子に一致し、平滑呼気は128／192フレーム遅れた。離鍵窓で左右の流量と各2回の交差を確認した。鳴禽4コールと、動物4種の全15コールの仮想MIDI比較を終えた。[登録条件](cases/worklet-midi-songbird-buzz.json)・[読解と検証](notes/worklet-midi-songbird-buzz.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各19項目、固定時刻のBuzz回帰20項目、ChirpsのMIDI回帰20項目、Rust40件に合格した。Chirps回帰の初回は計測関数の引数で停止した。採取出力を保存して修正後に再実行した。WorkletとCLIは79,200 PCMフレームでビット一致し、1,238時点の23列で差0。CSV2本を合計74.4 MBから69.8 MBに絞りRTL9210B-CGへ保存し、正式実行15成果物のSHA-256を照合した。[正式結果](runs/worklet-midi-songbird-buzz-20261121-final/summary.json)・[保存記録](runs/worklet-midi-songbird-buzz-20261121-final/manifest.json)・[回帰初回の停止](runs/worklet-midi-songbird-buzz-20261121-chirps-regression/manifest.json)・[修正後の回帰](runs/worklet-midi-songbird-buzz-20261121-chirps-regression-rerun/summary.json)
- 未達の条件。固定上流との最初の差は押下6内部サンプル後の総放射で、差を生んだ演算は未特定。正式実行のPCM差は減衰中1フレームの最大1.32×10⁻²³。物理MIDI機器と許可画面、手動発声の動的音高を固定上流の合成器で描画した場合の比較が残る。
- 次に、手動発声の動的音高の登録条件、固定上流の `src/ui/store.ts` の `noteOn`・`noteOff` と `crates/chimera/src/voice/human_voice.rs` の `set_source`・`render`、候補の `web/prototypes/chimera-research/src/manual-replay.ts` と `tools/measure_worklet_midi.py` を開く。選択音と候補波形の既存比較は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_midi.py worklet-midi-voice-pitch-baseline-local-1` で再計測する。[動的音高の登録条件](cases/worklet-midi-voice-pitch.json)・[既存の合格結果](runs/worklet-midi-voice-20261120-repeat/summary.json)

## Web MIDIによる手動発声の音高切り替え

- 完了した項目。候補と上流の通常画面で保持音45→57→45→全解放を照合し、同じ採用時刻で固定Rustと候補を描画した。110 Hzから220 Hzへの初回平滑値は111.689 Hzで、声門位相は連続した。音高だけ110 Hzに固定した対照では、採用時に声門が分岐し、17フレーム後にPCM差が閾値を超えた。[登録条件](cases/worklet-midi-voice-pitch.json)・[読解と検証](notes/worklet-midi-voice-pitch.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各13項目、従来のMIDI所有16項目、可動母音26項目、Rust40件に合格。初回はCSVの読み込みで停止し、採取したWAV・CSVを保存して修正した。正式実行のブラウザとCLIは124,416 PCMフレームがビット一致。3本のCSVは全行の主要列を保持し、237.9 MBから130.5 MBに絞ってRTL9210B-CGへ保存した。25成果物のSHA-256を照合した。[正式結果](runs/worklet-midi-voice-pitch-20261121-final/summary.json)・[実行と保存記録](runs/worklet-midi-voice-pitch-20261121-final/manifest.json)・[初回の停止](runs/worklet-midi-voice-pitch-20261121-a/failure.json)
- 未達の条件。固定上流との初期の微差は押下前の口腔断面、咽頭側圧、口端流量に見え、PCMの全区間最大差は2.18×10⁻¹¹だった。内部サンプル0と1のどの演算で差が始まるか、物理機器のMIDI入力と許可画面は未検証。
- 次に、鍵盤歌唱の末子音の登録条件、固定上流の `crates/chimera/src/phonetics/sing.rs` の `plan_note_off` と `tail`、候補の `crates/vocal-core/src/phonetics/live_song.rs` を開く。開音節と母音継続の回帰は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_midi_song.py worklet-midi-song-coda-baseline-local-1`。[末子音の登録条件](cases/worklet-midi-song-coda.json)・[既存の鍵盤歌唱の合格結果](runs/worklet-midi-song-20261120-final/summary.json)

## Web MIDIによる鍵盤歌唱の語末 /p/

- 完了した項目。capの最後の離鍵で末子音を追加し、計画の最大荷重の開始−1 msと下降開始61.5 msを独立計算と照合した。両版の実閉鎖・再開口は離鍵後52.354・96.000 ms。語末を省いた対照には閉鎖がなかった。完全閉鎖時の口端流量は独立した放射の減衰式に従った。[登録条件](cases/worklet-midi-song-coda.json)・[読解と検証](notes/worklet-midi-song-coda.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各13項目、開音節の回帰16項目、Rust40件に合格。初回は固定基準のID照合で停止し、ファイル名から拡張子を外して修正した。正式実行のブラウザ・CLIは108,288 PCMフレームでビット一致。4本のCSVを全行保持して83.9 MBから77.8 MBに削減し、RTL9210B-CGに保存した。27成果物のSHA-256を照合した。[正式結果](runs/worklet-midi-song-coda-20261121-final/summary.json)・[実行と保存記録](runs/worklet-midi-song-coda-20261121-final/manifest.json)・[初回の停止](runs/worklet-midi-song-coda-20261121-a/failure.json)・[開音節の回帰](runs/worklet-midi-song-coda-20261121-open-regression/summary.json)
- 未達の条件。固定上流とのPCM最大差は9.31×10⁻¹⁰で、最初の内部差は押下前の最初の口端流量・総放射に見えた。差を作る演算、物理MIDI機器と許可画面は未検証。計画に記載した保存済み実行を再計測する共通CLIは未実装。
- 次に、保存済み実行の比較条件、`crates/vocal-cli/src/main.rs` の `run`、`tools/measure_worklet_midi_pitch.py` のWAV・時系列の読み出しを開く。基準の再取得は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 ../../.venv/bin/python tools/measure_worklet_midi_pitch.py compare-saved-voice-baseline-local-1`。保存済みの基準と候補を同時刻で照合するCLIの入口を追加する。[次の登録条件](cases/compare-saved-voice-run.json)・[保存済み基準のマニフェスト](runs/worklet-midi-voice-pitch-20261121-final/manifest.json)

## 保存済みの波形と時系列を比較するCLI

- 完了した項目。`vocal-cli compare` でマニフェストに載るモノラルfloat32 WAVと観測CSVを読み、SHA-256を照合して指定の半開区間を比較する。候補の内部全サンプルと固定上流の出力末尾観測を同じ座標へ揃え、以前のフレーム全件と4状態列の指標を再現した。[登録条件](cases/compare-saved-voice-run.json)・[読解、仕様と再実行](notes/compare-saved-voice-run.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各10項目、区間外の改変確認などを含む正式12項目、Rust40件、`vocal-cli` のClippyが通過。PCMの13,082ビット差と最大絶対差2.18×10⁻¹¹は既存記録と独立計算に一致。元WAV・CSVは既存の外部実体をそのまま読み、計測スクリプトの初回停止後も成果を保存した。[正式結果](runs/compare-saved-voice-20261121-verified/summary.json)・[実行とハッシュ](runs/compare-saved-voice-20261121-verified/manifest.json)・[初回の停止](runs/compare-saved-voice-20261121-a/failure.json)
- 未達の条件。初期の固定上流マニフェストのケース別成果とPCM16は未対応。今回の形式では最初の放射差が内部サンプル1、声門流量差が内部サンプル5に現れることを再取得した。押下前に微差を作る演算の特定は別の比較として残る。
- 次に、PCM16の登録条件、固定上流の `crates/chimera-cli/src/compare.rs` の `read_wav`、候補の `crates/vocal-cli/src/saved_compare/input.rs` の `Manifest`・`Wave` を開く。現行の比較の回帰は `../../.venv/bin/python tools/measure_saved_voice_compare.py compare-saved-voice-baseline-local-1`。初期基準の母音WAVを同一形式とfloat32換算の対照で比較する。[PCM16の登録条件](cases/compare-upstream-pcm16.json)・[初期の固定上流マニフェスト](runs/upstream-20261119-a/manifest.json)

## 初期の固定上流のPCM16を保存済み比較に接続

- 完了した項目。初期マニフェストのケース別成果とモノラルPCM16を比較CLIで読み、成果のケースIDと状態を出力に記録した。保存済みの48 kHz・288,000フレームは固定上流のPCM16再レンダーとビット一致し、独立換算したfloat32との差は全点で0。量子化前との差2.44×10⁻⁵を丸め式で再現した。[登録条件](cases/compare-upstream-pcm16.json)・[読解と実測](notes/compare-upstream-pcm16.md)
- 最後に確認した実行。作業ツリーと`/tmp`の各11項目、float32・CSV比較の回帰12項目、Rust40件、`vocal-cli` のClippy、上流のWAV出力テストが通過。正式実行の26成果をSHA-256で照合し、RTL9210B-CGの生成物を既存の実行パスから再比較した。[正式結果](runs/compare-upstream-pcm16-20261121-final/summary.json)・[実行と保存記録](runs/compare-upstream-pcm16-20261121-final/manifest.json)・[float32回帰](runs/compare-upstream-pcm16-20261121-float-regression/summary.json)
- 未達の条件。PCM24・PCM32整数や多チャンネルの入力は今回の比較対象外。計画全体の成果を完了条件の行ごとに照合する監査と、録音を評価用に分けた確認が残る。物理MIDIの比較も未検証。
- 次に、計画書の第0〜7段階、比較の手順、成果物の条件を、進捗表から実行マニフェスト・判定内容へたどって照合する。`sed -n '54,104p' ../../../docs/plans/chimera-research-rebuild-plan.md` と `rg -n '第[0-7]段階|未達の条件' progress.md` で着手する。人間の音声評価は、固定上流の `docs/speech-comparison.md` と `docs/csd-comparison.md`、研究の利用方針と `research/data/sample-index.csv` を開いて、再現基準と独立した評価の証拠を確認する。[計画の段階条件](../../../docs/plans/chimera-research-rebuild-plan.md#実装順と段階の完了条件)・[音声データの利用方針](../../README.md#音声データの利用方針)

## 第0〜7段階の実行証拠の照合

- 完了した項目。64件の代表実行を計画の条件と照合し、1,173判定、成果1,382件のサイズとSHA-256、保存したケース定義995件のSHA-256を確認した。RTL9210B-CGとCT2000X8の実体も元の実験パスで読めた。内蔵・外部対照の指定成果、CSVの抜粋と失敗時の全系列は登録条件を満たした。[段階別の照合](notes/plan-evidence-audit.md)・[登録条件](cases/plan-evidence-audit.json)
- 最後に確認した実行。`plan-evidence-audit-20261121-a` と `/tmp` からの `plan-evidence-audit-20261121-repeat` は各12項目を通過し、要約がバイト一致した。TSPの48 kHz版を作業用ディスクに取得し、固定上流と同じSHA-256と登録8件の格納を確認した。アーカイブは未展開。[初回](runs/plan-evidence-audit-20261121-a/manifest.json)・[再実行](runs/plan-evidence-audit-20261121-repeat/summary.json)・[TSPの配置と出典](cases/tsp-active-duration-pilot.json)
- 未達の条件。録音との独立比較と試聴は未実施。96 kHzの減衰時に見つけた処理時間の外れ値、物理MIDIと許可画面、同一終端・単位にそろえた既存波動管との対照なども残る。[96 kHzの結果](runs/worklet-rate-96000-20261120-stage6-root/summary.json)・[調査項目の到達範囲](notes/plan-evidence-audit.md)
- 次に `cases/tsp-active-duration-pilot.json` と `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run`、固定上流 `crates/chimera-cli/src/render.rs` の `say` を開く。`rg -n 'render-pcm|speech_voice' crates/vocal-cli/src/main.rs` で候補の通常入口を確認し、登録した8発話のうち調整用と確認用を分けて発話区間長の測定を実装する。公開アーカイブの確認は `shasum -a 256 /Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-reference/tsp-v2/48k.zip`。[次の比較条件](cases/tsp-active-duration-pilot.json)

## TSPの発話区間長を測る入力の確認

- 完了した項目。候補の `speech_voice::run` に固定上流のTSP本文を入力した。元の登録8件は未対応音素で停止したため不合格を保存。同じ4話者の240件では6件で計画を作成できた。男女で共通する文だけを各分割で選び、調整用2録音、確認用4録音を登録した。音声の実体や計測値は選定に使っていない。[最初の条件](cases/tsp-active-duration-pilot.json)・[合成可能な範囲の条件](cases/tsp-active-duration-supported.json)
- 最後に確認した実行。`../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-active-duration-inspect-20261121-a` で元の登録8件の停止を確認し、240件について入力ハッシュと終了コードを保存した。`/tmp` から絶対パスで再実行した要約もバイト一致。停止した音素の組み合わせは各録音IDに記録した。[マニフェスト](runs/tsp-active-duration-inspect-20261121-a/manifest.json)・[判定と各入力](runs/tsp-active-duration-inspect-20261121-a/summary.json)・[再実行](runs/tsp-active-duration-inspect-20261121-repeat/manifest.json)
- 未達の条件。録音と合成の発話区間長の比較、試聴は未実施。元の8件で必要な `/ð/`、`/ɹ/`、`/ʃ/`、`/dʒ/` は合成未対応。
- 次に `cases/tsp-active-duration-supported.json` と `tools/measure_body_english.py` の `measure_native_endpoint`・`measure_variant` の入口を開き、候補の `render-pcm` と固定上流の `render text --float` で6件を取得する。入力検査は `../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-active-duration-inspect-local-1` で再現できる。独立RMSの前後無音対照を先に実行し、発話区間長を2組に分けて保存する。[読解と格納先](notes/plan-evidence-audit.md#人間の録音を用いる最初の比較)

## TSP録音と合成の発話区間長

- 完了した項目。調整用2録音、確認用4録音について固定上流と候補を通常のCLIから生成し、録音と同じRMS窓で発話区間長を測った。主しきい値での両合成の差は全件0 ms。録音との差は符号付きで−410〜+325 ms。独立した畳み込みで36区間の開始・終了が一致した。音量をそろえた試聴用の6対と、別の記録欄を用意した。[計測条件](cases/tsp-active-duration-supported.json)・[読解と結果](notes/tsp-active-duration.md)
- 最後に確認した実行。`tsp-active-duration-20261121-a` と `/tmp` からの `tsp-active-duration-20261121-repeat` は各6項目を通過し、要約を含む53成果がバイト一致。上流のTSP試験6件とCLIのWAV試験1件も通過した。舌先の初期位置だけを揃えた対照は男女とも発話前50 msが厳密に無音となり、MA02_07の副しきい値での余分な50 msが消えた。[正式結果](runs/tsp-active-duration-20261121-repeat/summary.json)・[保存記録](runs/tsp-active-duration-20261121-repeat/manifest.json)・[舌先の対照](runs/tsp-startup-resting-tip-20261121-a/summary.json)
- 未達の条件。この比較は合成可能な3文の区間長を対象とした。元の事前登録8件の音素不足、より広い録音評価、歌唱評価、人の試聴、合成2版の有声部の波形差が残る。[元の入力検査](runs/tsp-active-duration-inspect-20261121-a/summary.json)・[試聴手順](runs/tsp-active-duration-20261121-repeat/artifacts/listening/README.md)
- 次は、元の登録8件のうち6件に現れる `/ð/` を調べる。研究ワークスペースで `rg -n 'DH|"ð"|DH_OPENING' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics` を実行し、`inventory.rs`・`durations.rs`・`planner.rs` の歯音、直前が休止や阻害音のときの閉鎖、鼻音後の開大を読む。固定上流と候補の予測を小さなケースに登録し、`/ð/` だけで停止していた調整用2録音の本文を通常の入口で再確認する。[発話入口](crates/vocal-cli/src/timing_case/speech_voice.rs)・[元の事前登録](cases/tsp-active-duration-pilot.json)

## 有声歯摩擦音 /ð/ の文脈とTSP本文

- 完了した項目。`/ð/` の発話頭・休止後・阻害音後の閉鎖、母音間の狭窄と鼻音後の開大をCLIとWASMに接続した。破擦音を含む10条件とTSP本文2件で計画・内部状態・PCMを固定上流に照合。TSPの4話者240件のうち計画を作れる本文が6件から32件に増えた。[ケース](cases/dental-dh.json)・[読解と実測](notes/dental-dh.md)・[TSP入力の再検査](runs/tsp-active-duration-inspect-20261121-dental/summary.json)
- 最後に確認した実行。`dental-dh-20261121-affricates` の76判定、ワークスペース41試験、上流6試験、Clippyが通過。WASMではCLIと234,197フレームがビット一致した。`/tmp` からの64判定の再実行は要約と元CSV40件のハッシュが初回と一致した。全時系列を判定後に必要な範囲を抜粋し、再実行成果は約11.9 MBになった。第3版の新規2条件の全系列はRTL9210B-CGに保存。[最終結果](runs/dental-dh-20261121-affricates/summary.json)・[保存情報](runs/dental-dh-20261121-affricates/manifest.json)・[WASM照合](runs/dental-dh-20261121-wasm-final/summary.json)
- 未達の条件。新しく合成できた2件の録音との比較、元の登録8件のうち残る6件の `/ɹ/`、`/ʃ/`、`/dʒ/`、試聴と歌唱の独立評価が残る。調整済み音源で行った固定上流比較の最大PCM差は `3.73×10⁻⁹`。[調整用本文の比較](runs/dental-dh-20261121-affricates/summary.json)・[先行する録音比較](notes/tsp-active-duration.md)
- 次に `cases/tsp-active-duration-pilot.json` と `tools/measure_tsp_active_duration.py` を開き、`rg -n 'CASE|implementation|input_support_run' tools/measure_tsp_active_duration.py` で測定の入口を確認する。新しく合成できる `FA01_01` と `MA01_01` を元の調整用として固定し、確認用の話者分割を維持して登録し直す。同じRMS窓で録音と通常入口の合成を確認する。残るIPAの実装は `/ɹ/` の調音から進める。[現行の録音比較条件](cases/tsp-active-duration-supported.json)・[計画](../../../docs/plans/chimera-research-rebuild-plan.md)

## /ð/ 対応後のTSP録音比較

- 完了した項目。元の調整用 `FA01_01` と `MA01_01`、確認用FK・MKの4録音を追加し、既存の6録音を含めた12録音を同じ方法で比較した。主しきい値では両合成の区間長差が最大5 ms、追加6件では候補が録音より25〜455 ms長かった。独立計算で72区間の両端、先行6録音の計測値と12 WAVのハッシュが一致した。音量をそろえた試聴用12対を保存した。[条件](cases/tsp-active-duration-after-dh.json)・[実測と読解](notes/tsp-active-duration-after-dh.md)
- 最後に確認した実行。`tsp-active-duration-after-dh-20261121-a` と `/tmp` からの再実行は各6判定を通過し、101成果がバイト一致した。舌先対照の第1版は先頭50 msに入る `/ð/` の準備放射のため不合格で保存。第2版では先頭の調音準備を除外するガードを式から求め、最初の出力時刻と副しきい値の境界を上流へ照合し、全6判定を通過した。[本測定](runs/tsp-active-duration-after-dh-20261121-repeat/summary.json)・[独立検証](runs/tsp-active-duration-after-dh-20261121-independent/summary.json)・[第1版の判定](runs/tsp-startup-after-dh-20261121-a/summary.json)・[第2版の判定](runs/tsp-startup-after-dh-20261121-b/summary.json)
- 未達の条件。元の8録音のうち2件を測定済み。残る6件の入力には `/ɹ/`、`/ʃ/`、`/dʒ/` が必要。人による試聴、同じ音響アラインメントでの音素別比較、歌唱の独立評価、発声部の波形差の分析が残る。[元の8件](cases/tsp-active-duration-pilot.json)・[試聴手順](runs/tsp-active-duration-after-dh-20261121-repeat/artifacts/listening/README.md)
- 次に固定上流 `phonetics/inventory.rs` の `/ɹ/` と `durations.rs` の語末側の母音比を読む。`rg -n '"ɹ"|rhotic' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/{inventory,durations,planner}.rs` で始め、英語の歯茎接近音と対応済みのそり舌接近音 `/ɻ/` の姿勢・閉鎖・持続時間を照合する。元の確認用 `FK61_01` と `MK61_01` は現状 `/ɹ/` だけが未対応なので、通常入口での再検査に使う。`../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-inspect-local-1` で現状を実行できる。[入力の再検査](runs/tsp-active-duration-inspect-20261121-dental/summary.json)

## 英語の接近音 /ɹ/ と確認用TSP本文

- 完了した項目。`/ɹ/` の舌先・唇・舌根と補助の舌体目標を発話と歌唱の共用処理に追加した。IPA7条件、英語歌唱1条件、元の確認用TSP本文2件を通常のCLIで生成し、固定上流と独立したばね計算に照合した。語末の母音と `/ɹ/` の時間配分は既存の処理で上流と一致した。4話者240本文のうち合成できる本文は32件から130件に増えた。[読解と実測](notes/english-rhotic.md)・[TSPの入力検査](runs/tsp-active-duration-inspect-20261121-rhotic/summary.json)
- 最後に確認した実行。`english-rhotic-20261121-final` は83判定を通過し、上流との最大PCM差は `3.73×10⁻⁹`。WASMのIPA・歌唱・TSPはCLIと合計259,584フレームがビット一致。固定上流28試験、候補41試験、Clippyが通過した。第1版の不合格を残し、第2版で子音長を各音素の最短長から計算する判定に改めた。元CSV40件のハッシュは両版で一致し、第2版の外部保存成果は約12.5 MB。[第2版の結果](runs/english-rhotic-20261121-final/summary.json)・[第1版の結果](runs/english-rhotic-20261121-b/summary.json)・[保存とハッシュ](runs/english-rhotic-20261121-final/manifest.json)・[WASM照合](runs/english-rhotic-20261121-wasm/summary.json)
- 未達の条件。新たに合成した `FK61_01`、`MK61_01` の録音比較と試聴、音響アラインメントによる音素別評価、歌唱の独立評価が残る。元の登録8件のうち `/ʃ/` を必要とする調整用2件と `/dʒ/` を必要とする確認用2件は未対応。波形の微小差が調音開始前の放射にもあり、原因は未分離。[波形と判定](notes/english-rhotic.md#実装と実測)・[録音比較の現状](notes/tsp-active-duration-after-dh.md)
- 次に `cases/tsp-active-duration-after-dh.json` と `tools/measure_tsp_active_duration.py` の `measure` を開く。`rg -n 'held_out_ids|comparison_run|input_support_run' cases/tsp-active-duration-after-dh.json tools/measure_tsp_active_duration.py` で確認し、元の登録から `FK61_01` と `MK61_01` を確認用に追加して、調整用4件と確認用10件を同じRMS窓で測る。登録したケースを `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_tsp_active_duration.py tsp-active-duration-after-rhotic-local-1 --case cases/tsp-active-duration-after-rhotic.json` で実行する。[先行条件](cases/tsp-active-duration-after-dh.json)・[計測器](tools/measure_tsp_active_duration.py)

## /ɹ/ 対応後のTSP録音比較

- 完了した項目。元の確認用 `FK61_01` と `MK61_01` を追加し、調整用4件・確認用10件の発話区間長を測った。追加2件では候補が録音より110 ms、85 ms短く、合成同士の差は5 ms、0 ms。先行12件の計測値と両合成WAV24件を再現し、直接畳み込みで全84区間の両端を照合した。試聴用14対を保存した。[比較条件](cases/tsp-active-duration-after-rhotic.json)・[読解と結果](notes/tsp-active-duration-after-rhotic.md)
- 最後に確認した実行。初回と `/tmp` からの再実行は各6判定、独立検証5判定、舌先対照6判定を通過。上流のTSP試験6件とWAV試験1件も通過。元CSV14件とログを除く117成果が同じで、1回分の保存成果は作業用ディスクに約26.4 MB。独立検証の初回はCSV抜粋設定の適用で保存エラーになり、結果とエラーを残して再実行した。舌先対照で `MK61_01` の副しきい値の開始が0から75 msへ移り、固定上流に揃った。[本測定](runs/tsp-active-duration-after-rhotic-20261121-repeat/summary.json)・[保存記録](runs/tsp-active-duration-after-rhotic-20261121-repeat/manifest.json)・[独立検証](runs/tsp-active-duration-after-rhotic-20261121-independent-final/summary.json)・[舌先対照](runs/tsp-startup-after-rhotic-20261121-a/summary.json)
- 未達の条件。元の8録音のうち、`/ʃ/` を含む調整用2件と `/dʒ/` を含む確認用2件が未測定。通常経路の有声部の波形差、共通の音響アラインメントによる音素別測定、人による試聴、歌唱の独立評価が残る。[元の登録](cases/tsp-active-duration-pilot.json)・[試聴手順](runs/tsp-active-duration-after-rhotic-20261121-repeat/artifacts/listening/README.md)
- 次に `phonetics/inventory.rs` の `/ʃ/` の支配軸と較正、`planner.rs` の口腔ジェスチャー、`durations.rs` の時間を読む。研究ワークスペースで `rg -n '"ʃ"|"SH"' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/{inventory,planner,durations,english}.rs` を実行する。対応済みの `/ɕ/` と `/tʃ/` の解放区間を対照に、摩擦量、狭窄、唇の形状を事前登録する。元の調整用 `FA01_02` と `MA01_02` は `/ʃ/` 対応後に `../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-inspect-sh-local-1` で再検査する。[最新の入力検査](runs/tsp-active-duration-inspect-20261121-rhotic/summary.json)

## 無声後部歯茎摩擦音 /ʃ/ と調整用TSP本文

- 完了した項目。発話と歌唱に `/ʃ/` を接続し、`/tʃ/` の解放目標を共用した。歯への乱流、声門下圧、母音間の狭窄を固定上流と独立式に照合し、乱流を切ると成人男性の3〜15 kHzのパワーが49.23 dB下がった。4話者240本文のうち合成可能な本文は130件から170件。元の調整用 `FA01_02`、`MA01_02` は各133,824フレームを合成した。[事前登録](cases/postalveolar-fricative-sh.json)・[読解と実測](notes/postalveolar-fricative-sh.md)・[入力再検査](runs/tsp-active-duration-inspect-20261121-sh/summary.json)
- 最後に確認した実行。12条件の118判定が通過し、同じ初期条件の固定上流との最大PCM差は `4.66×10⁻¹⁰`。WASMとCLIは278,656フレームがビット一致。固定上流29試験、候補41試験とClippyが通過した。先行 `/tʃ/` の2ブロック割りと上流PCMを再現した。約1.71 GBの時系列はRTL9210B-CGで全フレームを判定し、約14.4 MBの成果を保存した。[本測定](runs/postalveolar-fricative-sh-20261121-a/summary.json)・[保存記録](runs/postalveolar-fricative-sh-20261121-a/manifest.json)・[WASM照合](runs/postalveolar-fricative-sh-20261121-wasm/summary.json)
- 未達の条件。元の登録8件のうち確認用 `FK61_02` と `MK61_02` だけが `/dʒ/` により合成未対応。今回の調整用2件の実録音との比較、共通の音響アラインメント、試聴、歌唱の独立評価が残る。`/ʃ/` の制御開始前に見える微小な放射差は未分離。[登録8件の判定](runs/tsp-active-duration-inspect-20261121-sh/summary.json)・[実測](notes/postalveolar-fricative-sh.md#計画と摩擦の実測)
- 次に固定上流の `phonetics/inventory.rs` と `planner.rs`、`tests/affricates.rs` の `/dʒ/` を開く。`rg -n '"dʒ"|affricate_folds|voiced affricate' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/{src/phonetics/{inventory,planner},tests/affricates}.rs` を実行し、`/tʃ/` と同じ口腔の解放と、閉鎖中の有声性を比較する。対応後は `../../.venv/bin/python tools/inspect_tsp_pilot.py tsp-inspect-dzh-local-1` で元の8件を再検査し、今回と次回で追加できる計4件を、調整用と確認用を維持してまとめて録音比較する。[先行の録音比較](notes/tsp-active-duration-after-rhotic.md)

## 有声後部歯茎破擦音 /dʒ/ と元のTSP登録8件

- 完了した項目。発話と歌唱へ `/dʒ/` を接続し、閉鎖付近の低域比、解放の乱流、短い歌唱の開大を固定上流と独立式に照合した。170件から198件に合成可能範囲が広がり、元の登録8件すべての本文が発話計画を通過した。新規確認用 `FK61_02`、`MK61_02` は各144,727フレームを合成した。[読解と実測](notes/voiced-postalveolar-affricate-dzh.md)・[入力検査](runs/tsp-active-duration-inspect-20261121-dzh/summary.json)
- 最後に確認した実行。第2版の11条件で86判定を通過。固定上流との最大PCM差は `2.33×10⁻¹⁰`、WASMとCLIは247,375フレームがビット一致。固定上流12試験、候補41試験とClippyを通過した。第1版の男性条件は完全閉鎖の予測が外れたため不合格で保持し、第2版では開いた狭窄と正の枝流量を照合した。高密度CSV44件をRTL9210B-CG上で検査し、第2版の保存成果は約13.3 MB。[第2版の結果](runs/postalveolar-affricate-dzh-20261121-final/summary.json)・[第1版の結果](runs/postalveolar-affricate-dzh-20261121-b/summary.json)・[保存とハッシュ](runs/postalveolar-affricate-dzh-20261121-final/manifest.json)・[WASM照合](runs/postalveolar-affricate-dzh-20261121-wasm/summary.json)
- 未達の条件。追加の調整用 `FA01_02`、`MA01_02` と確認用 `FK61_02`、`MK61_02` の録音比較、共通の音響アラインメント、人による試聴、歌唱の独立評価が残る。標準の男性 `/dʒ/` に通路が残る原因と、制御準備前の放射の微小差は未分離。[検証と残る差](notes/voiced-postalveolar-affricate-dzh.md)
- 次に `cases/tsp-active-duration-after-rhotic.json`、`tools/measure_tsp_active_duration.py`、`tools/verify_tsp_active_duration.py` を開く。`rg -n 'calibration_ids|held_out_ids|comparison_run|input_support_run' cases/tsp-active-duration-after-rhotic.json` を実行し、調整用と確認用に2件ずつ追加する。ケースを登録後、`CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python tools/measure_tsp_active_duration.py tsp-active-duration-original-local-1 --case cases/tsp-active-duration-original.json` で調整用6件・確認用12件を測り、先行14件と独立検証する。[先行条件](cases/tsp-active-duration-after-rhotic.json)

## 元のTSP登録8件を含む18録音の発話区間長

- 完了した項目。調整用 `FA01_02`・`MA01_02`、確認用 `FK61_02`・`MK61_02` を追加し、調整用6件・確認用12件を計測した。元の登録8件の元の分割と、全108区間の両端を独立検証した。追加4件は実録音より180〜520 ms長く、主しきい値の両端は固定上流と一致した。先行14件の測定値と合成WAV28件のハッシュも一致した。[条件](cases/tsp-active-duration-original.json)・[読解と計測結果](notes/tsp-active-duration-original.md)
- 最後に確認した実行。初回と `/tmp` からの再実行は各6判定、元の登録を含む独立検証は7判定、舌先対照は8判定を通過。上流のTSP試験6件とCLIのWAV試験1件も通過した。ログを除く149成果と元CSV18件のハッシュが一致し、RTL9210B-CG上の保存成果は1回約35.0 MB。追加2男性の副しきい値の開始は舌先対照で上流と一致し、`MA01_02` の終端は同じ最大RMSを使う別の対照で一致した。[本測定](runs/tsp-active-duration-original-20261121-repeat/summary.json)・[独立検証](runs/tsp-active-duration-original-20261121-independent-final/summary.json)・[舌先対照](runs/tsp-startup-original-20261121-a/summary.json)・[マニフェスト](runs/tsp-active-duration-original-20261121-repeat/manifest.json)
- 未達の条件。共通の音響アラインメントによる音素別評価、人による18対の試聴、歌唱の独立評価、通常経路の有声部の波形差が残る。固定版MFAの実行ファイルとキャッシュは今回確認した環境に無かった。[試聴手順](runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md)・[波形差の起点](notes/tsp-active-duration-original.md#発話前の放射と終端のしきい値)
- 次に固定上流の `crates/chimera-cli/src/compare/tsp.rs` の `over_noise_floor`・`mfa_command`・`align_synth` と `tools/tsp/{setup.sh,mfa.yaml,alignment.tsv.gz}` を開く。`rg -n 'fn (over_noise_floor|mfa_command|align_synth)|ALIGN_FLOOR_DB' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs` を実行する。MFA 3.4.3と `english_us_arpa` v3.0.0を動かせる環境を作業用ディスクに用意し、まず調整用の同じ本文1件を録音と両合成で照合する。辞書表記・時刻の単位・丸め・無音/ノイズ床を登録して `mfa version` と `mfa align` の結果を残す。[上流の手順](../../../docs/reference/chimera-vocal-synth/upstream/docs/speech-comparison.md#method)

## 1本文のTSP録音と両合成の音素・語境界

- 完了した項目。RTL9210B-CGにmacOS arm64用MFA 3.4.3と上流と同じハッシュの `english_us_arpa` v3.0.0を用意した。調整用 `FA01_02` と `MA01_02` の録音・上流合成・候補合成を同じMFA設定で整列した。録音の時刻は小数3桁で上流の保存版と一致。4合成で辞書どおり27音素が得られ、`to` の母音だけが録音と異なり、26音素を対応付けた。[登録条件](cases/tsp-phone-boundaries-calibration.json)・[読解と結果](notes/tsp-phone-boundaries-calibration.md)
- 最後に確認した実行。`tsp-phone-boundaries-20261121-final` は7判定を通過し、6波形の二度の整列と初回・再実行の時刻が一致した。別のRust照合でアラインメント入力535,296フレームがビット一致。候補は録音より語と語間の合計が280・290 ms長く、語間は180・210 ms。成果は約2.58 MB。作業用ディスクに残るMFAの一時領域は約1.0 GiBだったため、同じ6入力の再計測は2 GiBを見込む。[最終結果](runs/tsp-phone-boundaries-20261121-final/summary.json)・[保存情報](runs/tsp-phone-boundaries-20261121-final/manifest.json)・[Rust照合](runs/tsp-phone-boundaries-20261121-noise-rust/summary.json)
- 未達の条件。元の確認用4録音の音素別比較、MFAが無音に割り当てた部分の閉鎖と間の切り分け、人による試聴、歌唱の独立評価が残る。同じ本文以外で元注釈の再現が成り立つかは未確認。[音素と時刻の全結果](runs/tsp-phone-boundaries-20261121-final/summary.json)・[18対の試聴](runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md)
- 次に `cases/tsp-phone-boundaries-calibration.json` と `tools/measure_tsp_phone_boundaries.py` の `pronunciation`・`measurement` を開く。`rg -n 'def (pronunciation|match_phones|measurement)|recording_ids' tools/measure_tsp_phone_boundaries.py cases/tsp-phone-boundaries-calibration.json` を実行して、元の確認用 `FK61_01`・`MK61_01`、`FK61_02`・`MK61_02` の2本文を入力にできるようケースを拡張する。比較条件は調整用で確認した版を引き継ぎ、`CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python tools/measure_tsp_phone_boundaries.py tsp-phone-boundaries-local-1` で調整用を再現できる。[再現手順](notes/tsp-phone-boundaries-calibration.md#実行環境と保存)

## 元のTSP確認用4録音の語・音素境界

- 完了した項目。元の確認用2本文・4録音と両合成、計12波形を同じMFA設定で整列した。録音の語・音素境界はミリ秒単位で固定上流の保存注釈と一致し、各合成の発話計画も一致した。候補の区間長は録音より本文1で50・130 ms短く、本文2で110・380 ms長かった。音素の対応は本文1で22／25、本文2で27／30だった。[登録条件](cases/tsp-phone-boundaries-held-out.json)・[読解と実測](notes/tsp-phone-boundaries-held-out.md)
- 最後に確認した実行。確認用と調整用の再実行が各7判定、独立検証が3判定、固定上流の試験が6件通過。12波形の二度の整列結果と調整用の先行要約を再現し、Rustと合成用MFA入力1,043,436フレームがビット一致した。確認用63成果は4.39 MB、作業領域はRTL9210B-CG上の約1.0 GiB。初回に停止したディスク確認は、タイムアウト時も同じUUIDとマウント先をカーネルから照合できるようにした。[確認用の結果](runs/tsp-phone-boundaries-held-out-20261121-a/summary.json)・[保存記録](runs/tsp-phone-boundaries-held-out-20261121-a/manifest.json)・[独立検証](runs/tsp-phone-boundaries-held-out-20261121-verified/summary.json)
- 未達の条件。両合成の音響境界には最大50 msの差があり、整列前の波形にも差を確認した。MFAが `coat to` の語間に割り当てた90・110 msと /t/ 閉鎖の対応、個々の音響境界を動かす波形の区間、人による試聴、歌唱の独立評価が残る。[試聴手順](runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md)・[音響境界の差](notes/tsp-phone-boundaries-held-out.md#語と音素の実測)
- 次に、`runs/tsp-phone-boundaries-held-out-20261121-a/artifacts/aligned-1-synth/FK61_02-candidate/FK61_02-candidate.json`、`runs/tsp-active-duration-original-20261121-repeat/artifacts/FK61_02/inspect.json`、`crates/vocal-cli/src/timing_case/speech_voice.rs` を開く。`rg -n 'coat|UW0|sil' runs/tsp-phone-boundaries-held-out-20261121-a/artifacts/aligned-1-synth/FK61_02-candidate/FK61_02-candidate.json` で境界を確認し、女性の `coat to` で /t/ の狭窄面積、短時間電力、語と無音の時刻を揃える条件を先に登録する。[再現コマンド](notes/tsp-phone-boundaries-held-out.md#実行と保存)・[次の小さな実験](findings.md)

## TSPの `coat to` で語間と破裂音の閉鎖を比較

- 完了した項目。確認用 `FK61_02` の女性設定で、MFAの語間90 msを両合成の口腔断面と放射の時系列に重ねた。全4,320フレームで口腔セル8の最小断面が0 cm²、清浄PCMの5 ms窓は先行母音比−10 dB以下だった。閉鎖を担う舌先の2ジェスチャーは11 ms重なり、独立式と一致した。[登録条件](cases/tsp-coat-to-closure.json)・[実測と図](notes/tsp-coat-to-closure.md#比較結果)
- 最後に確認した実行。正式8判定と上流12試験、候補15試験を通過し、通常CLIと保存WAVおよび上流プローブと通常PCMを各144,727フレームで照合した。初回は累積電力の差で桁落ちし、直接平均への修正後は矩形畳み込みとの差が最大 `1.42×10⁻¹⁴ dB` になった。初回と正式の各14成果は、RTL9210B-CGに保存してSHA-256を照合した。正式成果は約26.8 MB。[初回](runs/tsp-coat-to-closure-20261121-a/summary.json)・[正式結果](runs/tsp-coat-to-closure-20261121-final/summary.json)・[実行記録](runs/tsp-coat-to-closure-20261121-final/manifest.json)
- 未達の条件。男性設定の110 msおよび実録音の閉鎖への一般化は未検証。両版の完全な0への到達に64フレーム差があった。初期舌先と放射の差、個々の有声区間とMFAの境界への波形の寄与、人による試聴、CSDによる歌唱評価が残る。[観測した差](notes/tsp-coat-to-closure.md#比較結果)
- 次に、固定上流の `docs/csd-comparison.md`、`tools/fetch-csd.sh`、`crates/chimera-cli/src/compare.rs` の `load_notes`・`render_notes` と `compare/score.rs` の `held_out` を開く。`rg -n 'fn (csd_ipa|load_notes|render_notes|compare_song|held_out)' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/{compare.rs,compare/score.rs}` で入口を確認する。作業用ディスクには現時点でCSDがないため、同ディスクの `scratch/chimera-reference` に必要な入力を取得し、ハッシュと利用条件を記録する。調整用1曲と確認用1曲を固定し、まず音素の変換、音符の時刻・ピッチ、計画が遅れた音符の件数を上流と照合する。[固定上流のCSD手順](../../../docs/reference/chimera-vocal-synth/upstream/docs/csd-comparison.md)

## CSDの調整用・確認用2曲の歌唱計画

- 完了した項目。固定上流の分割で調整用 `en001a`、確認用 `en005a` を選び、注釈と録音の4ファイルをRTL9210B-CGに取得した。192音符の音節、句境界、丸め前の母音開始、ピッチジェスチャーを候補と固定上流で照合した。F0の独立計算との差は最大 `5.68×10⁻¹⁴ Hz`、母音開始が注釈から30 msを超えた音符は両曲で0件。[登録条件](cases/csd-song-planning.json)・[読解と実測](notes/csd-song-planning.md)
- 最後に確認した実行。初回と `/tmp` からの計測は各17判定、既存の歌唱計画は6判定、固定上流は歌唱7件と比較19件を通過した。4入力はZIP中央ディレクトリのCRC32とSHA-256を照合し、全ZIPの未完ファイルを除いた状態からのRange再取得でも一致した。録音と注釈は約24.46 MB。上流の通常比較で録音・上流合成のピッチなどを保存した。[正式結果](runs/csd-song-planning-20261121-final/summary.json)・[実行記録](runs/csd-song-planning-20261121-final/manifest.json)・[取得した入力](runs/csd-song-planning-20261121-final/artifacts/selected-inputs.json)
- 未達の条件。今回の2曲にメリスマと30 ms超の音符は現れなかった。録音と候補合成の音響比較には、句を同じ出力時計で連続して描画する処理が必要。人による発話・歌唱の試聴は未実施。[上流の音響比較結果](runs/csd-song-planning-20261121-final/artifacts/csd/report.md)
- 次に、固定上流の `crates/chimera-cli/src/compare.rs` の `render_notes`・`compare_song` と候補の `crates/vocal-cli/src/timing_case/speech_voice.rs` の `run_song` を開く。`rg -n 'fn (render_notes|compare_song|run_song)|render_end_seconds' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs crates/vocal-cli/src/timing_case/speech_voice.rs` を実行し、`en001a` の先頭2句で単一の出力時計に計画を載せる比較を登録する。録音と同じ長さのPCMを作る経路へ接続し、句間の状態の連続性と最初の差を測る。[上流・候補に渡した句](runs/csd-song-planning-20261121-final/artifacts/song-inputs.json)・[最小比較の記録](findings.md)

## CSDの先頭2句の連続描画

- 完了した項目。既存の `song_voice` に絶対時刻付きの `scores` と描画終端を追加し、調整用 `en001a` の先頭2句を一つの発声器で64.8秒の時計に載せた。第1句がある場合だけ句間のPCMが残り、RMSは0.025383だった。短い描画と長い描画の先頭および128・77フレーム分割でPCMが一致。上流プローブの192,000フレームは通常比較の全曲WAVと一致した。[条件](cases/csd-continuous-song.json)・[読解と実測](notes/csd-continuous-song.md)
- 最後に確認した実行。初回と `/tmp` からの再実行で各9判定、上流17試験、単一譜例の回帰7判定とClippyが通過。候補と上流の呼気ゲートを独立式で照合し、同じ初期設定でPCM最大差は `1.41×10⁻¹¹` だった。RTL9210B-CGに書いた候補CSV約1.84 GBは、検証後に必要な区間と元のハッシュを残し、正式成果は約88.1 MB。[正式結果](runs/csd-continuous-song-20261121-repeat/summary.json)・[保存記録](runs/csd-continuous-song-20261121-repeat/manifest.json)・[単一譜例の回帰](runs/csd-continuous-song-20261121-legacy/summary.json)
- 未達の条件。通常上流と候補はフレーム0で瞬時F0と口端流量に差があった。瞬時F0の初回偏差はドリフトの式で再現し、通常出力をそろえるために各設定がPCMへどれだけ影響するかは残る。候補の全曲PCM、録音との音響比較、人による試聴も未検証。[差の発生箇所](notes/csd-continuous-song.md#実測)
- 次に、`runs/csd-song-planning-20261121-final/artifacts/song-inputs.json`、`tools/measure_csd_continuous_song.py`、固定上流の `compare.rs` の `Analyzer::note` を開く。 `rg -n 'def (record_variant|measurement)|fn note\(' tools/measure_csd_continuous_song.py ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs` を実行する。まず `en001a` の全50句を録音長で描画し、安定母音の同じ窓から録音・上流・候補の実測F0と欠測を比較する。[通常上流の歌唱評価](runs/csd-song-planning-20261121-final/artifacts/csd/report.md)・[録音長と保存の手順](notes/csd-continuous-song.md#実行と保存)

## CSDの調整用全曲の実測F0と第3倍音の対照

- 完了した項目。 `en001a` 全50句・86音符を録音長で描画し、録音・固定上流・候補を同じ4,032のフレーム中心で測った。全音符でF0を取得し、固定上流の通常報告を丸め幅内で再現した。録音との音符別絶対差の中央値は固定上流11.58、候補12.01セント。両合成で約+700セントだった4音符は、第3倍音が強いときにYINが短い遅延を採ったことを確認した。別ケースで上限だけを変えると4音符が譜面から16セント以内になった。[全曲の登録](cases/csd-acoustic-f0-en001a.json)・[読解と実測](notes/csd-acoustic-f0-en001a.md)・[倍音の対照](runs/csd-f0-third-harmonic-en001a-20261121-verified/summary.json)
- 最後に確認した実行。全曲の初回と `/tmp` からの再実行で各8判定、倍音の対照で各5判定、固定上流20試験と候補Clippyを通過した。出力CSV省略時の先頭2句、全曲の最初の192,000フレーム、128・77フレーム分割でPCMを照合した。正式成果はRTL9210B-CGに約14.31 MB。通常条件と対照を別々に保存した。[正式結果](runs/csd-acoustic-f0-en001a-20261121-final/summary.json)・[マニフェスト](runs/csd-acoustic-f0-en001a-20261121-final/manifest.json)・[音符別の図](runs/csd-acoustic-f0-en001a-20261121-final/artifacts/note-f0.png)
- 未達の条件。確認用 `en005a` の候補PCMと録音との音響比較、倍音対照の独立曲での検証、歌唱の試聴が残る。通常の固定上流と候補のPCMは最初の口端流量と瞬時F0に差があり、設定ごとの寄与は未分離。[全曲と倍音対照](notes/csd-acoustic-f0-en001a.md#全曲の測定)
- 次に `cases/csd-acoustic-f0-en001a.json`、`tools/measure_csd_song_f0.py`、`runs/csd-song-planning-20261121-final/artifacts/csd/report.json` を開く。 `rg -n 'def (render_song|measurement_windows|reference_error)|en005a' tools/measure_csd_song_f0.py cases/csd-song-planning.json` で測定の入口と確認用の登録を確認する。確認用 `en005a` を全36句で描画し、元の±7半音でF0と有声率を測る。倍音の対照は通常成績とは別の固定条件で検証する。[確認用の登録と注釈](notes/csd-song-planning.md#実測)

## CSDの確認用全曲の実測F0と探索上限の対照

- 完了した項目。確認用 `en005a` の全36句・106音符を録音長で描画し、録音・固定上流・候補を同じ4,707のフレーム中心で測った。全波形で106音符のF0を取得し、固定上流の通常報告を丸め幅内で再現した。録音との音符別絶対差の中央値は固定上流17.98、候補19.25セント。上限+7・+5半音の対照で14,121フレームのF0と有声判定が一致した。通常条件の先頭で平滑化F0とゲートがそろう一方、瞬時F0と口端流量で差が出ることを先頭20 msの状態記録で確認した。[読解と実測](notes/csd-acoustic-f0-en005a.md)・[通常条件](cases/csd-acoustic-f0-en005a.json)・[探索上限の対照条件](cases/csd-f0-upper-bound-en005a.json)
- 最後に確認した実行。通常計測の8判定と探索上限対照の4判定は初回と `/tmp` からの再実行で通り、WAV・CSV・要約をバイト照合した。調整用 `en001a` の回帰は以前のWAV・F0のCSV・要約と一致。先頭20 msの対照は5判定を通過した。正式成果はRTL9210B-CGに通常約17.66 MB、探索上限約1.53 MB、初期状態約1.67 MB。[通常計測のマニフェスト](runs/csd-acoustic-f0-en005a-20261121-final/manifest.json)・[探索上限の再実行](runs/csd-f0-upper-bound-en005a-20261121-repeat/summary.json)・[先頭20 msの対照](runs/csd-acoustic-f0-en005a-startup-20261121-a/summary.json)
- 未達の条件。確認用に調整用と同じ第3倍音誤推定の事例は現れなかった。先頭フレームのPCM差に対する姿勢・声源変動・ゲインの個別の寄与は未分離。音量包絡とタイミング、スペクトル、人による発話・歌唱の試聴は未評価。[未分離の設定と観測](notes/csd-acoustic-f0-en005a.md#pcmの最初の差を調べた対照)
- 次に、CSDの音量包絡と時間差を調べる。固定上流の `compare.rs` と2曲の既存WAVを開く。 `rg -n 'fn (envelope_db|envelope_lag|compare_song)' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs` で呼び出しと定義を確認し、10 ms窓と遅延の探索条件を登録する。調整用 `en001a` から、上流の通常レポート、独立計算、候補と録音の比較を行う。[上流の通常報告](runs/csd-song-planning-20261121-final/artifacts/csd/report.md)

## CSDの音量包絡と句の有声開始

- 完了した項目。調整用と確認用の既存WAVを照合し、3波形で各曲の10 ms包絡と±300 msの相関を測った。録音に対する固定上流・候補の最良ラグは両者とも `en001a` で0 ms、 `en005a` で+10 ms。全86句で有声開始が得られ、両合成の値は82句で一致、残る4句で5〜10 ms差が出た。最初に分かれた窓ではYINの正規化差が0.2をまたいだ。[登録と測定方法](cases/csd-envelope-timing.json)・[読解と実測](notes/csd-envelope-timing.md)
- 最後に確認した実行。独立計算、通常報告、上流スコア、既知時差を含む17判定を初回と `/tmp` からの再実行で確認した。調整用の録音・固定上流の丸め前の有声開始は全100件で一致した。スコアの列参照を誤った不合格実行と、初版の丸め幅での合格を保持した。包絡・相関・句別のCSVなど正式成果は約4.00 MBでRTL9210B-CGに保存した。[正式な結果](runs/csd-envelope-timing-20261121-final/summary.json)・[再実行](runs/csd-envelope-timing-20261121-repeat/manifest.json)・[不合格の記録](runs/csd-envelope-timing-20261121-score/summary.json)
- 未達の条件。確認用の録音で最大210 msの開始差があった句は、録音の周期を探索左端で検出した。前の音節由来かは未確定。音符のスペクトル、試聴、先頭放射への設定ごとの寄与は未評価。[残る有声開始の差](notes/csd-envelope-timing.md#句ごとの実測)・[発見と次の対照](findings.md)
- 次に、音符のスペクトルを調べる。 `rg -n 'fn (power|harmonic_db|mcd|compare_song)|const (BANDS|N_MEL|N_CEP)' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs` で固定上流の窓、周波数帯、メル帯域とMCDを確認する。調整用の少数音符と既知周波数を先に登録し、上流の通常報告と独立計算を照合してから全調整用と確認用に進める。[上流の通常報告](runs/csd-song-planning-20261121-final/artifacts/csd/report.json)

## CSD音符の帯域電力、H1−H2、メルケプストラム距離

- 完了した項目。調整用の5音符で直接DFTと既知倍音を照合し、同じ計測を両曲192音符に適用した。3波形で計13,323のスペクトル窓、12,611のH1−H2を取得。固定上流の通常報告と調整用の丸め前のスコアを再現した。録音との平均MCDは調整用で固定上流7.72、候補7.58 dB、確認用で9.20、9.96 dB。通常F0を取り違えた代表窓のH1−H2は、同じFFTでF0を差し替えると固定上流で45.63、候補で41.63 dB変わった。[登録と予測](cases/csd-note-spectrum.json)・[読解と実測](notes/csd-note-spectrum.md)
- 最後に確認した実行。少数音符の5判定、全曲13判定、固定上流の20試験を通過した。 `/tmp` からの全曲再実行で要約とCSVが一致。F0対照のJSONの配列を読み出し損ねた最初の少数音符実行も保存した。正式成果は約2.30 MBで、CSVなどの実体は作業用ディスクに置いた。[最初の実行](runs/csd-note-spectrum-20261121-pilot/manifest.json)・[全曲](runs/csd-note-spectrum-20261121-all/summary.json)・[再実行](runs/csd-note-spectrum-20261121-repeat/manifest.json)
- 未達の条件。参照F0の変更を音符・曲のH1−H2中央値まで適用した影響は未評価。確認曲で帯域が近くMCDが大きい音符の差の原因と、人による発話・歌唱の試聴が残る。[局所差と追試候補](findings.md)
- 次に、有声F0時系列からのビブラートと非周期性を調べる。 `rg -n 'fn (vibrato|note\(|vibrato_reads|periodic_modulation|vibrato_is_absent)|const (VIB_RATE|VIB_MIN_RUN)' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs` で連続有声区間、線形トレンド、自己相関、欠測の扱いを読む。既知変調と無変調・区間分断のケースを先に登録し、両曲の保存済みF0表と上流の通常報告で照合する。[F0の計測器](tools/measure_csd_song_f0.py)・[上流レポート](runs/csd-song-planning-20261121-final/artifacts/csd/report.json)

## CSDのビブラートと非周期性

- 完了した項目。両曲192音符、3波形26,217窓でYINの非周期性を照合し、先行F0表で省いた電力ゲート以下の349窓を同じPCMから補完した。調整用の丸め前の上流スコアまで再現した。最長の連続有声は調整用320 ms、確認用290 msで、曲中のビブラートは評価対象外だった。別の1.6秒母音では両合成で35セント設定から33.94セント・5.79 Hzを検出し、0セントでは検出されなかった。[読解と実測](notes/csd-vibrato-aperiodicity.md)・[実曲の条件](cases/csd-vibrato-aperiodicity.json)・[長母音の条件](cases/csd-vibrato-long-vowel.json)
- 最後に確認した実行。実曲の17判定と長母音の6判定を初回と `/tmp` からの再実行で確認した。上流20試験と先行F0の回帰8判定に通過し、通常条件のF0表・WAV・要約に差がなかった。正式成果は実曲約4.08 MB、長母音約1.79 MB。CSV・PCMの実体はRTL9210B-CGにある。[実曲の記録](runs/csd-vibrato-aperiodicity-20261121-repeat/manifest.json)・[長母音の記録](runs/csd-vibrato-long-vowel-20261121-repeat/manifest.json)・[F0回帰](runs/csd-acoustic-f0-en001a-20261121-aperiodicity-regression/summary.json)
- 未達の条件。人間の歌唱で0.4秒以上の連続有声区間を持つ音符を評価する。確認曲第97音の非周期性はゲート以下の窓を含めると1.435709になり、指標が音符尾部に反応した。振幅と周期の別を追う対照と、人による発話・歌唱の試聴は残る。[実曲の結果と発見](notes/csd-vibrato-aperiodicity.md#既知周期と2曲の結果)
- 次に、配布ZIPの注釈からビブラートを評価できる長さの音符を先に探す。 `rg -n 'class RemoteZip|def parse_notes|def phrase_inputs' tools/fetch_csd_inputs.py tools/measure_csd_song_planning.py` で部分取得と分割の入口を確認する。安定区間で80窓以上を取り得る調整用と確認用を音響結果に触れる前に別ケースへ登録し、選んだ曲だけを取得して固定上流と候補の通常CLIで照合する。[元の選定記録](cases/csd-song-planning.json)

## CSDの長音を含む録音に対するビブラート評価

- 完了した項目。英語aキー50曲7,220音符の注釈だけで調整用 `en012a` と確認用 `en035a` を選び、選定後に2曲の録音を取得した。再実装に不足した `/θ/` を固定上流の較正値と開大に沿って追加し、同じ曲の計294音符・62,127窓を評価した。録音のビブラート検出は調整用29/44、確認用17/39。固定上流は44/44・37/39、候補は44/44・38/39。確認用の第21音の異常な深さは、第3倍音によるF0誤推定の対照で再現した。[選定・実装・実測](notes/csd-long-note-vibrato.md)・[評価ケース](cases/csd-long-note-vibrato.json)
- 最後に確認した実行。固定上流の通常描画、候補の128・77分割、調整用の丸め前のスコアを含む全曲23判定が通過した。 `/θ/` の独立式・固定上流一致など5判定、候補ワークスペース41試験、固定上流20試験、ClippyとWASMビルドを確認した。最初の未対応音素による停止と、注釈のパス検査での停止も記録に残した。全曲の出力約115.24 MBと録音約44.85 MBは作業用ディスクに保存した。[全曲のマニフェスト](runs/csd-long-note-vibrato-20261121-theta/manifest.json)・[F0対照](runs/csd-long-note-vibrato-f0-control-20261121-a/summary.json)・[無声歯摩擦音の対照](runs/csd-dental-theta-20261121-verified/summary.json)
- 未達の条件。F0探索上限の変更で全曲のビブラート割合やH1−H2がどれだけ変わるかは未測定。人による録音・固定上流・候補の試聴は発話と歌唱とも未実施。[倍音の対照と範囲](notes/csd-long-note-vibrato.md#第3倍音がビブラート推定に入る対照)
- 次に、CSDの既存PCMから試聴用素材を作る。 `rg -n '試聴|音量|順番' runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md notes/csd-long-note-vibrato.md` でTSPの既存手順と歌唱の観測を開く。録音で検出された長音と検出されなかった長音の区間を事前登録し、録音・固定上流・候補の時刻とレベルをそろえた試聴ファイル、順序、採点欄を別に検証する。[既存の発話試聴手順](runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md)

## CSDの比較試聴素材

- 完了した項目。調整用・確認用の各3区間を事前登録し、録音・固定上流・候補の18音源を同じ注釈時刻から切り出した。安定区間を−26 dBFSにそろえ、外部ディスクに48 kHz PCM16で保存した。最大のRMS差は0.000033 dB。各区分でA・B・Cの位置を入れ替え、音源名を伏せたローカル再生とCSVの画面を作った。音源の鍵は別ファイルに保存した。[試聴ページ](runs/csd-listening-20261121-verified/artifacts/listening/index.html)・[ケースと方法](notes/csd-listening.md)
- 最後に確認した実行。音源の時刻・量子化・順序とブラウザの12判定に通過した。Chromeは18音源を実際に再生し、日本語・引用符・改行のCSVを書き出した。2つの画面幅でも横はみ出しがなかった。 `/tmp` からの再実行で音声・ページ・要約・検証結果が一致した。合計約3.66 MBで作業用ディスクに保存し、記入欄は空であることを確認した。[正式実行](runs/csd-listening-20261121-verified/manifest.json)・[ブラウザの検証](runs/csd-listening-20261121-verified/artifacts/browser-verification.json)・[再実行](runs/csd-listening-20261121-repeat/manifest.json)
- 未達の条件。人による発話18対と歌唱6区間の試聴は未実施。F0探索上限が曲全体のH1−H2とビブラートへ及ぼす影響は、代表窓と代表音符の対照から先が残る。[発話の試聴](runs/tsp-active-duration-original-20261121-repeat/artifacts/listening/README.md)・[倍音の対照](notes/csd-long-note-vibrato.md#第3倍音がビブラート推定に入る対照)
- 次に、保存した通常条件を基準にF0探索上限の影響を曲全体で独立に評価する。 `rg -n 'def (measure|vibrato|h1h2)|search_upper_semitones' tools/measure_csd_long_note_f0_control.py tools/measure_csd_vibrato_aperiodicity.py tools/measure_csd_note_spectrum.py cases/csd-long-note-vibrato-f0-control.json` で既存の対照を開く。探索上限だけを変える条件を先に登録し、ビブラートとH1−H2について曲別の有声率・欠測の変化も保存する。[全音符の通常条件](runs/csd-long-note-vibrato-20261121-theta/summary.json)

## CSD全曲のF0探索上限の対照

- 完了した項目。4曲486音符・計88,344窓について、探索上限を+7から+5半音へ変えた対照を実施した。録音のF0と全波形の有声判定は一致し、+600セント以上の合成677窓が消えた。H1−H2の音符中央値が延べ22件で変化し、 `en035a` のビブラートは固定上流37→39音、候補38→39音を検出した。別の既知音では倍音を含む409.35 Hzの入力が約1オクターブ低く出た。[4曲の結果と既知音](notes/csd-f0-search-sensitivity.md)
- 最後に確認した実行。全曲37判定、既知音3判定、固定上流20試験に通過した。1,340窓を従来の独立計測で照合した。 `/tmp` からの再実行で両要約と圧縮CSVがバイト一致し、CSVを展開した全窓とH1−H2の集計も確認した。正式成果約7.95 MBは作業用ディスクに置いた。[全曲の再実行](runs/csd-f0-search-sensitivity-20261121-repeat/manifest.json)・[既知音の再実行](runs/csd-f0-search-detuned-tone-20261121-repeat/manifest.json)
- 未達の条件。上限の変更で生じる真の高音の誤りが、実曲の別の歌手や曲で起きる割合は未測定。人による発話と歌唱の試聴は未実施。[既知音で確認した差](notes/csd-f0-search-sensitivity.md#譜面より高い既知音の対照)・[比較試聴ページ](runs/csd-listening-20261121-verified/artifacts/listening/index.html)
- 次に、計画にある「突き出した下唇を引き込む場合の断面積の不連続」を扱う。 `rg -n 'no_area_jumps_as_a_protruded_lower_lip_tucks|contact-tuck' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs progress.md` で既知の除外テストと以前の固定姿勢を開く。上流の400分割（0.0025刻み）の設定と試験結果を確認し、段差の前後で輪郭、上限・下限の交差、セル面積のどれが先に分かれるかを観測するケースを登録する。[固定姿勢の先行試験](notes/soft-tissue-contact.md)・[段階別の記録](notes/plan-evidence-audit.md)

## 前突した下唇を引き込む場合の断面積

- 完了した項目。固定上流の除外試験と同じ12条件を4,812姿勢から開始し、計6,887姿勢を観測した。固定上流と候補で18件・0.210〜0.514 cm²の段差を再現した。前方1本目または2本目で、下唇内面を横切る点が1個から3個へ増え、最も高い交差に移ることを確認した。代表例では中心線距離の差し替えだけで、口腔セル18の0.40814 cm²の増加が再現された。[読解と観測](notes/lip-tuck-area-continuity.md)・[事前登録](cases/lip-tuck-area-continuity.json)
- 最後に確認した実行。固定上流の既定試験5件と候補ワークスペース41試験、測定の8判定、既存中立姿勢の独立計算に合格。除外指定の試験は既知の18件を出して終了コード101。36姿勢の輪郭・格子・セルの通常CLI出力と独立計算を照合し、全姿勢の両実装の最大面積差は1.17×10⁻¹³ cm²。正式成果はRTL9210B-CGに約10.18 MB保存した。 `/tmp` からの再実行で決定的な332出力がバイト一致した。[正式実行と成果](runs/lip-tuck-area-continuity-20261121-verified/manifest.json)・[再実行](runs/lip-tuck-area-continuity-20261121-repeat/manifest.json)・[中立姿勢の回帰](runs/lip-tuck-area-regression-20261121-a/summary.json)
- 未達の条件。計測は制御周期ごとの速度制限を適用する前の形状まで。段差が放射やPCMに残る量、候補の平滑化が閉鎖・破裂・摩擦に与える影響、人による発話と歌唱の試聴はいずれも未測定。[計画の比較条件](../../../docs/plans/chimera-research-rebuild-plan.md#最初に記録する調査テーマ)
- 次に、`rg -n 'labiodental|mouth|radiation|slew' cases/tract-slew-lips.json tools/measure_tract_control.py tools/measure_labiodental_fricatives.py ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs` で動的計測と上流の速度制限を開く。今回の代表姿勢の前後を通る短い引き込み軌跡を事前登録し、同じ駆動でセル目標、速度制限後の面積、圧力、口端放射とPCMを順に照合する。[代表例の両端](runs/lip-tuck-area-continuity-20261121-verified/artifacts/event-01/)

## 前突した下唇の引き込みによる発声中の放射差

- 完了した項目。肺圧設定7.2 cmH₂O、F0 110 Hzの発声を始めてから128 ms後に、下唇の引き込みだけを変えた。口腔セル13の平均・最小面積の段差は0.318・0.419 cm²。速度制限後の目標は0.237・0.217 cm²で、内部サンプル128刻みの補間を照合した。口端の圧力・流量・放射は最初の出力フレーム、PCMは1フレーム後に固定姿勢との差が出た。速度制限だけを緩めると、最初の1.33 msと20 ms内のPCM最大差が逆方向に変化した。[読解と結果](notes/lip-tuck-voiced-radiation.md)・[事前登録](cases/lip-tuck-voiced-radiation.json)
- 最後に確認した実行。固定上流と候補の発声PCMは固定・引き込みとも11,520フレームでビット一致した。15判定、固定上流2試験、候補41試験、既存の母音遷移26判定が通過した。実体はRTL9210B-CGへ各約20.19 MBを保存し、別作業位置からの再実行で決定的な30出力が一致した。[正式実行](runs/lip-tuck-voiced-radiation-20261121-a/manifest.json)・[再実行](runs/lip-tuck-voiced-radiation-20261121-repeat/manifest.json)・[既存の母音遷移](runs/lip-tuck-voiced-regression-20261121-a/summary.json)
- 未達の条件。前方測定線の交差処理を変えた場合の連続性、閉鎖・破裂・摩擦の時刻と放射、実際に聴取できる差の評価が残る。録音との人による発話・歌唱比較も未実施。[比較の範囲と次の最小ケース](notes/lip-tuck-voiced-radiation.md#再現と保存)
- 次に、`rg -n 'fn fan_floor|let forward|fn measure' crates/vocal-core/src/anatomy/grid.rs` で交差の向きと組織厚さの既存計算を開く。前方の縦線に現れる交差対を厚さとして扱う条件を事前登録し、静止の前突12条件と通常の唇歯条件、今回の有声中の放射で、対象の修正と閉鎖の回帰を順に比較する。[交差の静止計測](notes/lip-tuck-area-continuity.md)・[既存の唇歯摩擦音の比較](notes/labiodental-fricatives.md)

## 前方測定線で下唇の組織厚さを数える比較

- 完了した項目。前方の縦線が下唇内面の折り返しを通るとき、組織厚さだけを隙間から引く実験機能を実装した。前突12条件で0.05 cm²を超える段差が18→0件になり、代表の有声軌跡で固定姿勢に対する20 msのPCM残差は従来の2.57%に縮んだ。通常の引き込み36条件では閉鎖セルに差がなく、破裂音2本で閉鎖・再開口・破裂時刻、唇歯摩擦音9条件でPCMが一致した。[読解と比較結果](notes/lip-tuck-crossing-thickness.md)・[事前登録](cases/lip-tuck-crossing-thickness.json)
- 最後に確認した実行。12判定に合格した。18区間の両端は固定上流の輪郭から独立に計算し、面積の最大差は1.40×10⁻¹³ cm²。既定41試験・実験42試験とClippyも通過した。正式成果はRTL9210B-CGへ約202 MB保存した。 `/tmp` から再実行して決定的な185出力がバイト一致した。歌唱の読取項目で中断した初回の記録を残した。[別ディレクトリからの再実行](runs/lip-tuck-crossing-thickness-20261121-repeat/manifest.json)[正式な実行と成果](runs/lip-tuck-crossing-thickness-20261121-b/manifest.json)・[中断記録](runs/lip-tuck-crossing-thickness-20261121-a/interruption.json)
- 未達の条件。深い引き込みの一部では再現版との平均断面差が最大0.791 cm²に達する。実験条件でこの姿勢を発声させた場合の聴取評価や、録音との発話・歌唱試聴は未実施。[残る差と実験の範囲](notes/lip-tuck-crossing-thickness.md#静止時と発声中の結果)
- 次に、`rg -n 'SUBSAMPLES|CLOSURE_AREA|area_at|fn resample' crates/vocal-core/src/anatomy/resample.rs tools/measure_resample.py` で面積の離散化を開く。既存の唇閉鎖軌跡を使い、同じ内部サンプルレートで安定に使える粗・細の格子数だけを事前登録し、閉鎖・再開口時刻、圧力ピーク、放射スペクトルを照合する。[既存の閉鎖軌跡](cases/tract-slew-lips.json)・[計画の調査項目](../../../docs/plans/chimera-research-rebuild-plan.md#最初に記録する調査テーマ)

## 口腔の格子数による唇閉鎖の感度

- 完了した項目。CLIに口腔セル数を指定する入口を追加し、96 kHzで12・18・22セルに同じ唇閉鎖を通した。管長の補正は全条件で0。最小断面による口端の閉鎖・再開口は17,087・31,233内部サンプルで一致し、平均断面に同じ閾値を当てたときの閉鎖は0.66〜2.56 ms遅れた。再開口後20 msの8–24 kHzのPCM帯域値には最大2.31 dBの差があった。[比較の記録](notes/tract-grid-lip-closure.md)・[事前登録](cases/tract-grid-lip-closure.json)
- 最後に確認した実行。16判定に合格し、各格子の固定上流参照とのPCM差は最大9.10×10⁻¹³。10姿勢の独立積分、全制御周期の速度制限、実サンプルの断面積補間、既定18セルの既存軌跡も照合した。候補41試験、上流2試験、Clippy、WASMのチェックに通過した。RTL9210B-CGへ保存し、別の作業ディレクトリから再実行して決定的な84出力が一致した。[正式な結果と成果](runs/tract-grid-lip-closure-20261121-b/manifest.json)・[再実行](runs/tract-grid-lip-closure-20261121-repeat/manifest.json)・[出力時計を直す前の観測](runs/tract-grid-lip-closure-20261121-a/summary.json)
- 未達の条件。閉鎖点が口腔内を移動してセル境界を通る条件の感度と、録音との人による試聴評価が残る。今回の口端セルでは格子間で閉鎖時刻が変わるという予測に反し、最小断面が同じになった。[閉鎖時刻と残る差](notes/tract-grid-lip-closure.md#閉鎖時刻と断面を二通り持つ効果)
- 次に、`rg -n 'pressure_drop|fn step|oral-closure' crates/vocal-core/src/voice.rs crates/vocal-core/src/glottis.rs tools/measure_glottal_coupling.py` で声門の圧力結合と既存の閉鎖試験を開く。同一の軌跡・声門設定で声門の振動計算に入力する圧差だけを固定または記録系列に差し替え、声門面積・流量・放射の順に評価する。[既存の声門結合](notes/glottal-coupling.md)

## 声帯に渡す圧差だけを固定した唇閉鎖の対照

- 完了した項目。前回の18セル軌跡で、口端が閉じる17,087内部サンプルから声帯への圧差だけを6,633 dyn/cm²に固定した。6.72 ms後に発声係数・声門面積・声門流量の差が生じ、続いて実圧差と放射、PCMに差が出た。閉鎖中の面積パルスは開口時と同程度に残り、平均声門流量は開口時の5.26%、口端流量は0だった。通常時の実圧差を逐次再入力すると、両版でそれぞれ通常条件をビット単位で再現した。[読解と実験](notes/glottal-pressure-feedback.md)・[事前登録](cases/glottal-pressure-feedback.json)
- 最後に確認した実行。17判定、上流5試験、候補41試験、既存の簡略気道の閉鎖の回帰、ClippyとWASMのコンパイル検査に通過した。運動量を独立計算で逆算した実圧差は最大1.02×10⁻¹⁰ dyn/cm²以内、固定上流とのPCMの最大差は1.82×10⁻¹²。出力約50.75 MBはRTL9210B-CGへ保存した。別の作業ディレクトリからの再実行で決定的な36出力が一致した。[正式な測定](runs/glottal-pressure-feedback-20261121-b/manifest.json)・[再実行](runs/glottal-pressure-feedback-20261121-repeat/manifest.json)・[既存閉鎖の回帰](runs/glottal-pressure-feedback-regression-20261121-a/summary.json)
- 未達の条件。圧力結合の音源と固定LF駆動を、管・基本周波数・音響観測点をそろえて比較する工程が残る。代表の唇閉鎖で得た値の聴取評価と、録音との発話・歌唱試聴も未実施。[範囲と残る比較](notes/glottal-pressure-feedback.md#実行と保存)
- 次に、`rg -n 'LF|体積速度|放射' ../autonomous-research-cycle/campaigns/nas-radiated-waveguide-mechanism-20261009-v1/report.md notes/glottal-pressure-feedback.md` で固定LF波形と体積速度の定義を開く。同じ管とF0を固定し、両音源の流量と放射を共通の観測点で採る比較を事前登録する。[計画の調査項目](../../../docs/plans/chimera-research-rebuild-plan.md#最初に記録する調査テーマ)

## 固定声道を圧力結合と固定LFで駆動

- 完了した項目。固定 /ɑ/・110 Hzで通常の圧力結合、通常時の流量の再入力、固定LFの三条件を実行した。気管末端から咽頭入口に同じ流量を渡す境界を実装し、再入力がそれぞれの実装で節点圧からPCMまで完全一致することを確認した。LFは流量の解析積分と数値積分が2.28×10⁻¹³ cm³/s以内で一致し、通常時と平均流量を139.886 cm³/sにそろえた。総放射の交流RMSは31.61%低下した。[事前登録](cases/fixed-lf-glottal-flow.json)・[読解と結果](notes/fixed-lf-glottal-flow.md)
- 最後に確認した実行。再計測の15判定のうち14件を通過した。固定上流とのPCMは三条件とも完全一致。候補41試験、上流5試験、ClippyとWASMのコンパイル検査も通過した。各実行の39出力をハッシュ照合し、別ディレクトリからの再計測で32点の入力・音声・観測ファイルが復元後に一致した。可逆圧縮した再計測の出力は約43.94 MBで、RTL9210B-CGに保存した。[初回の実行](runs/fixed-lf-glottal-flow-20261121-a/manifest.json)・[再計測](runs/fixed-lf-glottal-flow-20261121-b/manifest.json)・[数値と判定](runs/fixed-lf-glottal-flow-20261121-b/summary.json)
- 未達の条件。口端流量の交流RMSの変化は2.85%で、事前登録した5%には届かなかった。総放射と口端流量差分では30%以上の変化があり、登録基準と結果を両方残した。発話・歌唱の人による試聴と、既存波動管との同一終端での照合が残る。[差分の観測](notes/fixed-lf-glottal-flow.md#結果)
- 次に、`rg -n '終端|反射|複素|放射' notes/uniform-tube.md ../autonomous-research-cycle/campaigns/nas-waveguide-tract-mechanism-20261008-v1/report.md` を実行し、既存の波動管と一様管FDTDで共通にできる終端を調べる。管と終端の条件を事前登録し、到達時間、共鳴、指定流量から口端流量への複素応答を測る。[計画の調査項目](../../../docs/plans/chimera-research-rebuild-plan.md#最初に記録する調査テーマ)

## 一様管FDTDと波動管の共通R–L終端

- 完了した項目。17.5 cm・3 cm²の剛体一様管で同じ入口流量と並列R–L終端を使い、96 kHz・40セルと192 kHz・80セルを比較した。口端の主波束は両方式で4.3 µs以内、最初の4共鳴は最大1.21%以内だった。細かい格子で2.75〜3.75 kHzの最大複素差は42.3%低下した。固定上流の時系列は相対ピーク誤差6.12×10⁻¹⁵以内、既存のC波動管の固定反射経路は1.98×10⁻¹⁸以内だった。[読解と数値](notes/uniform-waveguide-matched.md)・[基準ケース](cases/uniform-waveguide-matched.json)
- 最後に確認した実行。0.5秒と3秒の9系列の先頭が一致した。3秒条件を共通の6 kHz因果FIRで再解析すると、口端流量とその差分の複素応答は独立の離散式と4.0×10⁻⁹以内で一致し、34項目中33項目を通過した。従来の一様管CSVのバイト一致、候補41試験、上流3試験、Clippy、WASMのコンパイルを確認した。全時系列は可逆圧縮し、3秒の約144.11 MBをRTL9210B-CGに置いた。再解析の出力は約30 kBで、別ディレクトリからの再実行で4出力が一致した。[0.5秒](runs/uniform-waveguide-matched-20261121-b/manifest.json)・[3秒](runs/uniform-waveguide-matched-20261121-long/manifest.json)・[確定判定](runs/uniform-waveguide-matched-20261121-bandlimited-b/summary.json)・[再実行](runs/uniform-waveguide-matched-20261121-bandlimited-repeat/manifest.json)
- 未達の条件。96 kHzで3,250 Hzの振幅差1.49 dBが0.9 dB基準を超えた。時間刻み・セル長・端の処理の寄与は個別未評価。理想開口の音圧との照合、人による発話・歌唱の試聴も残る。[残差の説明](notes/uniform-waveguide-matched.md#照合結果と残る差)
- 次に、`rg -n '体積速度|バッフル|軸上|距離' notes/uniform-waveguide-matched.md ../autonomous-research-cycle/campaigns/nas-volume-velocity-observer-20261009-v1/report.md` で放射の観測条件を開く。3 cm²の開口と共通の口端流量を再利用し、CGSからSIに換算して固定距離の軸上音圧を独立計算と照合する。[計画の放射の調査項目](../../../docs/plans/chimera-research-rebuild-plan.md#最初に記録する調査テーマ)

## 口端流量から理想開口の軸上音圧を測る

- 完了した項目。3 cm²の同じ口端流量から、SI単位で0.5・1・2 mの軸上音圧を出す `vocal-cli observe-axis` を追加した。候補、固定上流、波動管の5系列を通した。Rayleigh積分と閉形式の相対複素誤差は2.39×10⁻¹⁴以内。4 kHzでは後退差分の半サンプルを補正すると、有限円盤に対する最大位相差が7.45°から0.197°以内に縮んだ。[読解と測定値](notes/uniform-axial-observation.md)・[登録条件](cases/uniform-axial-observation.json)
- 最後に確認した実行。155判定、候補41試験、固定上流3試験、Clippy、WASMのコンパイルを通過した。定常流量の補助試験で最後の応答後に無音の点を出すよう修正した。各条件の最初の20 msなど約1.80 MBをRTL9210B-CGへ保存し、別ディレクトリの実行で観測設定とCSVの30点をハッシュ照合した。[確定実行](runs/uniform-axial-observation-20261121-b/manifest.json)・[初回条件の再実行](runs/uniform-axial-observation-20261121-repeat/manifest.json)
- 未達の条件。理想円盤では口端の1経路を扱う。鼻腔・壁面を含む場合の位置・放射負荷は個別未評価。共通終端の96 kHz比較には0.9 dBを超える振幅差が残り、発話・歌唱の人による試聴評価も残る。[観測の範囲](notes/uniform-axial-observation.md#実行と保存)・[波動管との残差](notes/uniform-waveguide-matched.md#照合結果と残る差)
- 次に、`rg -n 'Courant|クーラン|振幅差|セル長' notes/uniform-waveguide-matched.md crates/vocal-core/src/airway.rs` で上行の1.49 dB差の条件を開く。空間格子と内部レートをそれぞれ固定する対照を登録し、3,250 Hz付近の振幅・位相の差を独立離散式と照合する。[元の比較の事前登録](cases/uniform-waveguide-matched.json)

## 一様管のセル長と時間刻みを分けた3,250 Hzの対照

- 完了した項目。20・40セル×96・192 kHzと192 kHz・80セルで入口流量と終端をそろえた。40セルで時間刻みを半分にすると3,250 Hzの振幅差が0.210 dB改善。192 kHzでセル長を半分にすると0.455 dB改善した。伝達行列で口端の半セル慣性を足し戻すと、96 kHz・40セルの差は−1.487 dBから+0.256 dBとなり、絶対値が82.8%減った。[実測と段別の式](notes/uniform-grid-rate-sensitivity.md)・[事前登録](cases/uniform-grid-rate-sensitivity.json)
- 最後に確認した実行。候補と固定上流の全時系列は相対ピーク誤差1.45×10⁻¹⁴未満、帯域制限後の複素応答は独立節点式に3.15×10⁻⁹以下で一致した。41判定中40件、候補41試験、上流3試験を通過。新規時系列は先頭25 msを保存し、約1.61 MBをRTL9210B-CGに置いた。別ディレクトリから再実行した要約・設定・波形など16点が一致した。[確定実行](runs/uniform-grid-rate-sensitivity-20261121-a/manifest.json)・[再実行](runs/uniform-grid-rate-sensitivity-20261121-repeat/manifest.json)
- 未達の条件。主比較の空間効果は時間効果の2.17倍で、事前登録の3倍には届かなかった。192 kHz・80セルでも範囲を広げると3,350 Hzで1.54 dB差が残る。半セル慣性を加えた時間領域の安定性、発話・歌唱の試聴も未評価。[判定を含む結果](runs/uniform-grid-rate-sensitivity-20261121-a/summary.json)
- 次に、`rg -n '半セル|放射端|慣性' notes/uniform-grid-rate-sensitivity.md crates/vocal-core/src/airway.rs` で放射端の状態更新を開く。半セル慣性を直列に加える実験条件を登録し、40セル・96 kHzを基準に口端の複素応答、無入力の減衰、安定性を照合する。[周波数領域の対照](notes/uniform-grid-rate-sensitivity.md#口端の半セル)

## 口端の半セル慣性を加えた時間領域の検証

- 完了した項目。固定一様管のCLIに口端の半セル慣性を直列に加える実験条件を実装した。96 kHz・40セルで3,250 Hzの差は−1.487 dBから+0.278 dB、登録16点の最大差は3.05 dBから0.619 dBになった。口端で変わった最初のサンプルは39、入口圧に戻るのは78。クーラン数0.9792の47セルまで、放射の散逸と離散エネルギーの収支を照合した。[読解と結果](notes/uniform-outlet-half-cell.md)・[事前登録](cases/uniform-outlet-half-cell.json)
- 最後に確認した実行。33判定、候補41試験、固定上流3試験、Clippy、WASMのコンパイルを通過した。全区間を判定して先頭25 msを保存し、確定実行の約647 kBをRTL9210B-CGに置いた。別ディレクトリからの再実行で設定・初期波形など9点と、追加診断を除いた要約が一致した。[確定実行](runs/uniform-outlet-half-cell-20261121-b/manifest.json)・[判定と数値](runs/uniform-outlet-half-cell-20261121-b/summary.json)
- 未達の条件。今回のエネルギー検証は剛体・管内粘性なしの条件で、半セルありでは30.07 kHz付近の残留が増えた。発話・歌唱の人による試聴と、実時間発声の96 kHzで過去に1量子だけ計算予算を超えた条件の原因切り分けが残る。[半セルの減衰](notes/uniform-outlet-half-cell.md#口端の応答と減衰)・[96 kHzの時間計測](notes/worklet-realtime-voice-96000.md)
- 次に、`rg -n '127,872|量子|ゲート' notes/worklet-realtime-voice-96000.md cases/worklet-realtime-voice-96000.json` で第6段階の実時間条件を開く。固定発声のゲートを閉じる時刻だけを変え、遅い量子が減衰時刻と描画開始からの量子番号のどちらに追随するかを、フレームの連続性と分けて測る。[第6段階の確認条件](../../../docs/plans/chimera-research-rebuild-plan.md#比較の手順)

## 96 kHzの描画量子とWASMラッパーの同期コンパイル

- 完了した項目。呼気停止を動かした12回で、Worklet時計上の超過2件はいずれも1,000量子目、うち1件は発声中だった。事前登録した反復数に届かず帰属は保留した。別の対照では、V8のラッパーの呼び出し予算を既定・640・1,200に動かし、初回と再実行の全12回で対応する量子に同期コンパイルが出た。うち4量子がトレース上で1.333 msの予算を超えた。[読解と結果](notes/worklet-realtime-release-alignment.md)・[呼気停止の事前登録](cases/worklet-realtime-release-alignment.json)・[V8の回数の事前登録](cases/worklet-wasm-wrapper-threshold.json)
- 最後に確認した実行。停止対照137判定、トレース初回と `/tmp` からの再実行の各85判定、通常の96 kHzの13判定を通過した。比較全回のContextフレームは連続し、PCMは候補CLIとビット一致、固定上流との差は最大2.92×10⁻¹¹未満。圧縮した停止対照とトレース2実行は合計約27.70 MBをRTL9210B-CGに保存した。[停止対照](runs/worklet-release-alignment-20261121-a/summary.json)・[同期コンパイル初回](runs/worklet-wasm-wrapper-threshold-20261121-a/summary.json)・[再実行](runs/worklet-wasm-wrapper-threshold-20261121-repeat/manifest.json)・[通常の96 kHz](runs/worklet-rate-96000-20261121-wrapper-regression/summary.json)
- 未達の条件。以前の個々の2〜4 msの内訳は未測定。採取末尾の量子も2回予算を超えており、完了通知と転送の時間を別途測る余地がある。ラッパー準備を起動へ移した場合の効果と実機の物理出力、発話・歌唱の人による試聴が残る。[トレースとWorklet時計の範囲](notes/worklet-realtime-release-alignment.md#v8の呼び出し回数を動かす対照)
- 次に、研究ワークスペースから `rg -n 'vocal_render|MAX_FRAMES' crates/vocal-wasm/{host/fixed-voice.ts,src/lib.rs}` と `rg -n 'constructor|this.engine|process\(' ../../../web/prototypes/chimera-research/src/live-processor.ts` を実行する。0フレーム入力が状態を進めないことを確認し、初期化時に同じエクスポートを準備する条件を事前登録する。通常のChromium設定で初期化時間、起動フレーム、初回と1,000量子目の処理、全PCM、観測値を冷間実行と照合する。冷間実行は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 ../../.venv/bin/python tools/measure_worklet_wrapper_threshold.py worklet-wasm-wrapper-threshold-next` で再現できる。[再現と保存](notes/worklet-realtime-release-alignment.md#再現と保存)

## 実時間発声のWASMラッパーを初期化時に準備

- 完了した項目。Workletのコンストラクターで同じWASMレンダー関数を0フレーム入力で呼ぶ実験条件を加えた。実時間96 kHzの計18試行で、準備0回・999回・1,000回のコンパイルは採取の1,000量子目・先頭・採取前に各6回現れた。準備1,000回の同期コンパイルは0.213〜0.251 ms。PCMと音響状態は全試行でビット一致した。[読解と結果](notes/worklet-wasm-wrapper-warmup.md)・[事前登録](cases/worklet-wasm-wrapper-warmup.json)
- 最後に確認した実行。初回と `/tmp` からの再実行で各156判定を通過。PCMの候補CLIとのビット一致、固定上流との最大差2.92×10⁻¹¹未満、Contextフレームの連続性を確かめた。候補コア・WASMの計41試験とWASMのClippy、従来経路の85判定も通過した。ブラウザ出力とトレースを可逆圧縮し、主比較2実行の約21.35 MBをRTL9210B-CGに保存した。[初回](runs/worklet-wasm-wrapper-warmup-20261121-a/manifest.json)・[再実行](runs/worklet-wasm-wrapper-warmup-20261121-repeat/summary.json)・[従来経路](runs/worklet-wasm-wrapper-threshold-20261121-warmup-regression/summary.json)
- 未達の条件。既に再生中のノードと物理出力への影響、他のブラウザの挙動は未測定で、準備は研究用オプションとした。1,000回条件で採取末尾の処理が1回2.236 msだった。発話・歌唱の人による試聴も残る。[起動と処理予算の計測](notes/worklet-wasm-wrapper-warmup.md#結果)
- 次に、研究ワークスペースから `rg -n 'AudioContext|AudioWorkletNode|connect\(' ../../../web/prototypes/chimera-research/src/realtime-fixed-voice.ts` でノード接続を確認する。同一Contextの既存ノードが目印付きの音を再生している間に、準備0回・1,000回のノードを追加する。既存ノードの処理時刻と出力の欠落を別々に計測し、起動で超過を移す先の負荷を確かめる。基準の単独ノードは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=350000000 ../../.venv/bin/python tools/measure_worklet_wrapper_warmup.py worklet-wasm-wrapper-warmup-next` で再現できる。[再現と保存](notes/worklet-wasm-wrapper-warmup.md#再現と保存)

## 先行音が鳴るAudioContextで発声ノードを追加

- 完了した項目。通常の発声開始の前に、同じContextへ既知PCMの先行音を接続した。96 kHzの計12試行で先行音のフレームは連続し、2,359,296サンプルが独立計算と一致した。発声音も単独ContextのPCM・音響状態に一致した。準備ありの同期コンパイルは全6試行でコンストラクター内に現れた。構築をまたぐ先行音のコールバック間隔は12回中11回でその試行の基準最大値を超えた。[読解と判定](notes/worklet-wasm-wrapper-shared-context.md)・[事前登録](cases/worklet-wasm-wrapper-shared-context.json)
- 最後に確認した実行。確定実行と `/tmp` からの再実行で各166判定、先行音を追加しない従来経路で85判定を通過した。主比較の先行音、発声音、観測JSON、生トレースを可逆圧縮して約23.96 MBをRTL9210B-CGに保存した。モジュールの配信で止まった実行と、取得後の要約の直列化で止まった実行も保存した。後者の先行音・トレースは保存データを再解析した。[確定実行](runs/worklet-wasm-wrapper-shared-context-20261121-c/manifest.json)・[再実行](runs/worklet-wasm-wrapper-shared-context-20261121-repeat/summary.json)・[従来経路の回帰](runs/worklet-wasm-wrapper-threshold-20261121-shared-regression/summary.json)・[初回の欠測](runs/worklet-wasm-wrapper-shared-context-20261121-a/manifest.json)・[直列化で止まった実行](runs/worklet-wasm-wrapper-shared-context-20261121-b/manifest.json)
- 未達の条件。既存音を観測した位置はグラフ内の混合前。物理出力の途切れや人による発話・歌唱の試聴が残る。ラッパー準備後でも採取の最初の量子は6回中5回で予算を超え、WASM関数本体の遅延コンパイルを全試行で観測した。コンストラクター全体と先頭量子の負荷の内訳は未分離。[残る差](notes/worklet-wasm-wrapper-shared-context.md#結果)
- 次に、研究ワークスペースから `rg -n 'WebAssembly.Instance|warmupRenderWrapper|vocal_new|vocal_start|vocal_render' crates/vocal-wasm/{host/fixed-voice.ts,src/lib.rs}` でWASMの状態と描画入口を確認する。使い捨ての状態で最初の128フレームを描き、発声本番は新規ハンドルから始める対照を事前登録する。関数番号ごとのコンパイル位置、初期化と処理時間、先行音と発声音のPCMを照合する。基準の共有Contextは `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=400000000 ../../.venv/bin/python tools/measure_worklet_shared_context.py worklet-wasm-wrapper-shared-context-next` で再現できる。[再現と欠測](notes/worklet-wasm-wrapper-shared-context.md#欠測と再現)

## 使い捨ての128フレームでWASM関数本体を準備

- 完了した項目。固定発声の同じWASMインスタンスでゲート0の使い捨て状態を描画・解放し、本番を新規ハンドルで始める実験条件を作った。事前登録した10関数は両対照の12試行で本番の先頭、128フレームの6試行で事前描画へ移った。使い捨て状態を作成して解放するだけの条件と比べて本番先頭の中央値は1.207から0.450 ms、構築は4.930から5.513 msになった。[読解と結果](notes/worklet-wasm-dsp-warmup.md)・[事前登録](cases/worklet-wasm-dsp-warmup.json)
- 最後に確認した実行。初回と `/tmp` の再実行で各292判定、従来の共有Contextで166判定に合格した。発声音と音響状態は従来の基準と同じで、先行音は計3,538,944サンプルが独立計算と一致した。波形・観測・トレースを可逆圧縮し、主比較2実行の約33.62 MBをRTL9210B-CGに保存した。[初回](runs/worklet-wasm-dsp-warmup-20261121-a/manifest.json)・[再実行](runs/worklet-wasm-dsp-warmup-20261121-repeat/summary.json)・[従来経路](runs/worklet-wasm-wrapper-shared-context-20261121-dsp-regression/summary.json)
- 未達の条件。構築全体の追加負荷は同じオーディオスレッドにあり、準備は研究用にとどめた。ゲートを開く量子と終了量子には別の遅延コンパイルが残る。物理出力と他ブラウザ、人による発話・歌唱の試聴は未確認。[起動と残る処理](notes/worklet-wasm-dsp-warmup.md#結果)
- 次に、研究ワークスペースで `rg -n 'this.post|this.port.close|engine.close|observations\[this.row' ../../../web/prototypes/chimera-research/src/live-processor.ts` を実行し、末尾量子が報告する処理時間の範囲と解放順を確認する。通常どおり全データを返す条件で、描画・結果の準備・転送・ハンドル解放の境界をトレースに記し、超過と関数番号の位置を照合する。基準の事前描画は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=440000000 ../../.venv/bin/python tools/measure_worklet_dsp_warmup.py worklet-wasm-dsp-warmup-next` で再現できる。[再実行コマンド](notes/worklet-wasm-dsp-warmup.md#再現と保存)

## 採取末尾の描画・送信・解放を分けて測定

- 完了した項目。96 kHzの固定発声で末尾量子に区間印を付けた。約1.05 MBの送信時間の中央値は通常の転送0.054 ms、複製0.291 ms。事前解放で関数48・41のコンパイルが構築に移り、末尾の解放は中央値0.081から0.013 ms。関数46は全試行のメッセージ作成で観測した。全18試行の発声音・音響観測がビット一致した。[読解と結果](notes/worklet-finalization-phases.md)・[事前登録](cases/worklet-finalization-phases.json)
- 最後に確認した実行。初回と `/tmp` からの再実行で各320判定、従来経路で166判定を通過。音声・観測・トレースは可逆圧縮して主比較2実行の約33.60 MBをRTL9210B-CGに保存した。過去8件の末尾超過も生トレースとハッシュから確認した。[初回](runs/worklet-finalization-phases-20261121-a/summary.json)・[再実行](runs/worklet-finalization-phases-20261121-repeat/manifest.json)・[従来経路](runs/worklet-wasm-wrapper-shared-context-20261121-finalization-regression/summary.json)・[過去の末尾超過](notes/worklet-finalization-phases.md#過去の予算超過)
- 未達の条件。今回の末尾は全試行で1.333 ms以内で、過去の超過の原因は確定していない。物理出力、非Chromiumの96 kHzの固定発声、人による発話・歌唱の試聴が残る。[今回の範囲](notes/worklet-finalization-phases.md#結果)
- 次に、研究ワークスペースから `rg -n 'firefox|chromium.launch|captureRealtime' ../../../web/prototypes/chimera-research/tools/{capture-song-recording,capture-worklet}.mjs` を実行し、既存のPlaywright Firefox配置と固定発声の開始・保存を確認する。同じ96 kHz・128フレームの通常経路をFirefoxで採取するケースを事前登録し、実際のレート、PCM・内部状態、フレーム連続性と利用できるWorklet時計をCLI・固定上流・Chromiumと照合する。[既存のFirefox計測と配置](notes/worklet-song-recording-firefox.md#再実行)・[通常の96 kHz基準](notes/worklet-realtime-voice-96000.md)

## FirefoxとChromiumの96 kHz固定発声

- 完了した項目。通常経路の12試行で、FirefoxとChromiumの96 kHz・128フレーム、PCMと音響観測のビット一致、採取中のフレーム連続性を確認した。CLIとのPCMは一致し、固定上流との最大差は2.92×10⁻¹¹未満だった。Firefoxの追加診断4試行で、2 ms表示の18量子が実測0.177〜0.662 msと分かった。ネイティブな発声p99は0.216〜0.350 msだった。[読解と結果](notes/worklet-realtime-cross-browser-96000.md)・[通常条件](cases/worklet-realtime-cross-browser-96000.json)・[Firefoxの追加診断条件](cases/worklet-realtime-firefox-native-clock-96000.json)
- 最後に確認した実行。通常は初回98/99判定、`/tmp` 再実行99/99判定。追加診断2実行は各13判定を通った。最初のプロファイルに含まれた省略可能な列の読取失敗を修正し、取得済みデータも残した。通常と追加診断の4実行は圧縮後計約24.64 MBをRTL9210B-CGに保存した。[通常初回](runs/worklet-realtime-cross-browser-96000-20261121-a/summary.json)・[通常再実行](runs/worklet-realtime-cross-browser-96000-20261121-repeat/summary.json)・[追加診断再実行](runs/worklet-realtime-firefox-native-clock-96000-20261121-repeat/summary.json)・[取得済みの中断記録](runs/worklet-realtime-firefox-native-clock-96000-20261121-a/interruption.json)
- 未達の条件。Firefoxの通常初回で発声p99が1.51 msになった判定を保持した。追加診断で高分解能の区間を測ったのは別試行で、初回の実際の処理時間や物理出力は未確認。Firefoxの実時間IPA発話と、人による発話・歌唱の試聴が残る。[計時の範囲と残る差](notes/worklet-realtime-cross-browser-96000.md#firefoxのネイティブな時計との照合)
- 次に、研究ワークスペースから `rg -n 'captureSpeech|browser_engine|firefox.launch' ../../../web/prototypes/chimera-research/tools/capture-worklet.mjs` を実行する。通常の `ɑpɑ` 実時間発話を48 kHzのFirefoxで採る条件を登録し、固定上流・CLI・ChromiumとのPCM、操作の採用フレーム、処理時計を照合する。[実時間IPAの通常条件](notes/worklet-live-ipa.md)・[Firefoxの配置とコマンド](notes/worklet-realtime-cross-browser-96000.md#再現と保存)

## FirefoxとChromiumの48 kHz実時間IPA発話

- 完了した項目。通常の12試行で、実時間・オフライン・CLIの `/ɑpɑ/` のPCM全49,828点がビット一致した。ブラウザ間で音響観測3,115行とスコア・声門・声道も一致した。固定上流との最大PCM差は1.82×10⁻¹²。唇の閉鎖と再開口はブラウザで11,119と13,903フレーム、CLIと上流で11,118と13,888だった。Firefoxの終了後にJSを呼ばないネイティブ区間を分け、発話を実行した414区間を照合した。[事前登録](cases/worklet-live-ipa-cross-browser.json)・[読解と結果](notes/worklet-live-ipa-cross-browser.md)
- 最後に確認した実行。`/tmp` からの再実行で129判定、従来の `--live` で19判定を通過した。比較の全計測2回は各85成果をハッシュで照合し、可逆圧縮した約76.03 MBをRTL9210B-CGへ保存した。計測器の未対応入力とWASM取得待ちで中断した2件、およびネイティブ区間の数え方で127/129だった最初の全計測も保存した。[確定実行](runs/worklet-live-ipa-cross-browser-20261121-repeat/manifest.json)・[従来経路](runs/worklet-live-ipa-20261121-cross-browser-regression/manifest.json)・[最初の全計測](runs/worklet-live-ipa-cross-browser-20261121-c/summary.json)・[入力の中断](runs/worklet-live-ipa-cross-browser-20261121-a/interruption.json)・[応答待ちの中断](runs/worklet-live-ipa-cross-browser-20261121-b/interruption.json)
- 未達の条件。Firefoxの4プロファイルで、最初の発話量子が3.566〜3.624 msとなり、2.667 msの予算を超えた。冒頭32量子を除いたp99は1.284〜1.344 ms。先頭の負荷の内訳、物理出力の途切れ、人による発話・歌唱の試聴が残る。[区間別の計時](notes/worklet-live-ipa-cross-browser.md#firefoxのネイティブな時計との照合)
- 次に、研究ワークスペースで `rg -n 'captureSong|renderRealtimeSongVoice' ../../../web/prototypes/chimera-research/{tools/capture-worklet.mjs,src/render-fixed-voice.ts}` を実行し、48 kHz歌唱の入口を開く。FirefoxとChromiumで通常の同一スコアを使う比較を事前登録し、予定拍・出力PCM・声道・処理区間をCLIと固定上流へ照合する。既存Chromiumの基準は `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=200000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-baseline-next --live` で確認できる。[既存の歌唱ケース](cases/worklet-live-song.json)・[歌唱の読解と再現](notes/worklet-live-song.md)

## FirefoxとChromiumの48 kHz実時間歌唱

- 完了した項目。通常の12試行で `Pop Dee` のPCM全91,200点が、両ブラウザの実時間・オフライン、CLIでビット一致。音響観測1,425行と計画も一致した。拍の出力位置は24,000と48,000フレーム、固定上流との最大PCM差は2.33×10⁻¹⁰。停止でContextを閉じて再度完了した。歌詞の拒否確認を現在の機能に合わせ、音節がない `...` からの復帰に変えた。[事前登録](cases/worklet-live-song-cross-browser.json)・[読解と測定](notes/worklet-live-song-cross-browser.md)
- 最後に確認した実行。初回179/179、`/tmp` からの再実行178/179、従来の実時間とgzip辞書の回帰26/26。主比較2回で各85成果をハッシュ照合し、可逆圧縮した約125.91 MBをRTL9210B-CGに保存した。両実行の展開後WAV28点は一致した。[初回](runs/worklet-live-song-cross-browser-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-cross-browser-20261121-repeat/manifest.json)・[従来経路](runs/worklet-live-song-20261121-cross-browser-regression/manifest.json)
- 未達の条件。再実行のFirefox通常試行1件で、冒頭32量子を除いたp99が3.00 msとなり予算2.667 msを超えた。別のFirefoxネイティブ診断4試行では同区間のp99は1.710〜1.774 ms、先頭の量子は全4回で3.601〜3.962 msだった。最初のWorkletコールバックはContext上でChromium42.7 ms、Firefox176.0〜192.0 ms。開始までの内訳、物理出力の途切れ、人による発話・歌唱の試聴が残る。[時間の差と判定](notes/worklet-live-song-cross-browser.md#context上の開始と描画時間)
- 次に、研究ワークスペースから `rg -n 'withRealtimeContext|prepareSongVoice|audioWorklet.addModule|node.connect' ../../../web/prototypes/chimera-research/src/render-fixed-voice.ts` を実行する。同じ `Pop Dee` の開始前に、Context再開、WASM準備、辞書、計画、Worklet登録と接続を区間別に採る対照を事前登録する。開始時刻とPCMに影響を与えないか既存ケースで照合する。[比較の再現コマンド](notes/worklet-live-song-cross-browser.md#再現と保存)

## 実時間歌唱の開始前の処理時間

- 完了した項目。Context生成から接続までの区間を通常の歌唱入口から測れるようにした。辞書の取得状態と確定済み音節の対照を含む48試行でPCM 91,200点、音響観測1,425行、予定拍とジェスチャーが基準に一致した。固定上流との最大PCM差は2.33×10⁻¹⁰。Firefoxで辞書取得済みの接続までの差は約149〜151 msで、歌唱計画のWASM呼び出しの差は2.0〜2.1 ms。再開とWorklet登録の待ちの比率は入れ替わり、合計の中央値は179と177 msだった。[事前登録](cases/worklet-song-startup-phases.json)・[読解と数値](notes/worklet-song-startup-phases.md)
- 最後に確認した実行。初回123/125、`/tmp` からの再実行125/125。各17件の上流試験、通常のgzip辞書・停止・再開、音節のCLI描画も確認した。主比較各150成果のハッシュを照合し、約30.35 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-startup-phases-20261121-a/manifest.json)・[再実行](runs/worklet-song-startup-phases-20261121-repeat/manifest.json)
- 未達の条件。初回のFirefoxで計時ありとなしの開始位置が許容幅より512フレーム多くずれ、再実行は128フレームで通過した。初回の時間差に対する計時の寄与は未分離。接続差の半分以上が歌唱計画という予測は不成立。音節を直接渡す比較でChromiumの80%短縮も未達だった。再開とWorklet登録に共通する待ち、先頭の描画負荷、物理出力の途切れと人による試聴は残る。[初回判定と再実行の差](notes/worklet-song-startup-phases.md#別ディレクトリからの再実行)
- 次に、研究ワークスペースから `rg -n 'loadFixedModule|withRealtimeContext|audioWorklet.addModule|node.connect' ../../../web/prototypes/chimera-research/src/render-fixed-voice.ts ../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts` を実行する。固定上流と同じく再開要求の直後からWorklet登録を始める対照を事前登録し、同じ `Pop Dee` で現行順との接続時間、区間の重なり、PCM、停止・再開を照合する。[今回の再現コマンド](notes/worklet-song-startup-phases.md#再現と保存)

## Context再開とWorklet登録を重ねる実時間歌唱

- 完了した項目。固定上流と同じタイミングで登録を始める研究用条件を実装した。現行順と合わせて32通常試行、停止と再開で保存した4試行のPCM各91,200点、音響観測1,425行、予定拍・調音計画が基準と一致した。Firefoxでは計画と登録が重なり、計画後に147.5〜148.5 msの登録待ちが残った。接続までの対の差は中央値で初回2.5 ms短縮、再実行5.0 ms延長だった。[事前登録](cases/worklet-song-parallel-registration.json)・[読解と結果](notes/worklet-song-parallel-registration.md)
- 最後に確認した実行。初回と `/tmp` からの再実行は各95機能判定、固定上流の試験は各17件を通過した。並行登録の保留中に閉じたContextの拒否を処理し、接続後の停止と再開も両ブラウザで通過した。従来のIPAの停止・復帰とPCMを照合した。二回分の各119成果はハッシュ検査済みで、約25.58 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-parallel-registration-20261121-a/manifest.json)・[再実行](runs/worklet-song-parallel-registration-20261121-repeat/manifest.json)
- 未達の条件。Firefoxの20 ms短縮は両実行で未達で、並行登録は研究用とした。Firefoxで登録待ちが長くなる時点をモジュールの取込・評価・通知に分ける測定が残る。最初の描画量子の処理負荷、物理出力での途切れ、人による試聴も残る。[再実行と判断](notes/worklet-song-parallel-registration.md#再実行と判断)
- 次に、研究ワークスペースから `rg -n 'registerFixedWorklet|registerProcessor|type: "ready"' ../../../web/prototypes/chimera-research/src/{render-fixed-voice,fixed-processor}.ts` を実行する。Worklet側のモジュール評価と `registerProcessor` の時刻を採る最小ケースを事前登録し、同じ歌唱をメイン側の登録開始・完了と照合する。[比較の再現コマンド](notes/worklet-song-parallel-registration.md#再現と保存)

## 実時間歌唱のWorklet登録とモジュール評価

- 完了した項目。メイン、ローカルHTTP、Workletの3か所で登録前後を計時した。Firefoxの全12計時試行では登録時間の99.35%以上が評価前にあった。並行登録はHTTP要求前が長い3試行と、応答送出から評価までが長い3試行に分かれた。計時用・通常用の全48試行のPCM各91,200点、音響観測1,425行と開始からの拍が基準と一致した。[事前登録](cases/worklet-song-module-evaluation.json)・[読解と時間の分解](notes/worklet-song-module-evaluation.md)
- 最後に確認した実行。初回と `/tmp` からの再実行は各133機能判定、固定上流の試験は各17件を通過。計時付き並行登録の停止・再開と従来のIPAも照合した。各151成果をハッシュ検査し、展開したWAV48本が一致した。約30.24 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-module-evaluation-20261121-a/manifest.json)・[再実行](runs/worklet-song-module-evaluation-20261121-repeat/manifest.json)
- 未達の条件。計時の有無で接続時間の差の中央値は全条件で20 ms以内だった。再実行のFirefoxの並行登録1対には138 msの差があり、計画完了後に差が広がった。待ちがHTTP境界の前後で移るブラウザ内の原因、最初の描画量子の処理負荷、物理出力と人による試聴は残る。[再実行と外れた対](notes/worklet-song-module-evaluation.md#再実行と残る差)
- 次に、研究ワークスペースで `rg -n 'profiler_command|thread_intervals|MOZ_PROFILER_STARTUP' tools/measure_worklet{_firefox_native_clock,_live_ipa_cross_browser}.py` を実行し、既存のFirefoxネイティブ計時を開く。同じ `Pop Dee` の現行順・並行登録で `AudioWorklet.addModule` と取得タスクのマーカーを採れる条件を事前登録し、HTTP要求と最初の計測文の位置に合わせる。[今回の再現コマンド](notes/worklet-song-module-evaluation.md#再現と保存)

## FirefoxのHTTPチャネルとWorklet登録の照合

- 完了した項目。Firefoxのプロファイルにメインの印を追加し、18試行で登録・評価・HTTPを対応づけた。5 msの時刻差を見込んだ評価前の割合は全試行で95.9%以上。17試行でチャネルを開いてから送信まで129.3〜189.8 ms、並行登録1試行で応答受信完了からチャネル完了まで173.9 msかかった。同試行の親プロセスにも173.7 msの区間があった。PCM全91,200点、音響観測1,425行、計画と拍はCLI・ブラウザの基準と一致した。[事前登録](cases/worklet-song-firefox-registration-native.json)・[読解と結果](notes/worklet-song-firefox-registration-native.md)
- 最後に確認した実行。修正後と `/tmp` からの再実行で各43判定を通過し、3実行で上流試験各17件を通過した。初回の2件は丸め済みの印で絞り込んだ集計が取りこぼした。初回の41/43を保存し、同じ生ログをネイティブ区間で読み直して全6件を対応づけた。ソースと成果をハッシュ検査し、成果約56.85 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-firefox-registration-native-20261121-a/manifest.json)・[修正後](runs/worklet-song-firefox-registration-native-20261121-b/manifest.json)・[再実行](runs/worklet-song-firefox-registration-native-20261121-repeat/manifest.json)
- 未達の条件。送信前の待ちはチャネル開設後にあり、取得タスクの開始より前に待つという予測に合わなかった。名前付き取得タスクのマーカーは得られなかった。送信前または受信後の待ちを生む処理、最初の描画量子の内訳、物理出力と人による試聴が残る。[待ち時間の位置](notes/worklet-song-firefox-registration-native.md#再実行と待ち時間の位置)
- 次に、研究ワークスペースで `rg -n 'content_network_timing|fetch_evidence|controls_containing_registration' tools/measure_worklet_song_firefox_registration_native.py` を実行する。初回 `2-parallel` の生プロファイルを開き、`HttpChannelChild::ContinueAsyncOpen` と親の `nsHttpChannel::OnStopRequest` を起点に、現行順・並行登録で同じチャネルの親子間通知とキューを照合するケースを登録する。[再現コマンドと成果の場所](notes/worklet-song-firefox-registration-native.md#再現と保存)

## Firefoxの親子プロセス間のHTTP通知

- 完了した項目。保存済み18試行のHTTPチャネルを親子間で照合し、通常画面からIPC付きで8試行を追加した。現行順の長い待ちが再現した2回では、親のI/Oスレッドへの到達からメインスレッド上の受信処理まで131.4 msと134.8 msかかった。並行登録で送信前に長く待つ位置は、親のチャネル開設前、接続準備前、キャッシュコールバック前に分かれた。子の完了マーカーが遅れた1回は、子の停止IPC処理からメインの完了マーカーまでに約26.3 msかかった。[事前登録](cases/worklet-song-firefox-http-channel.json)・[読解と観測](notes/worklet-song-firefox-http-channel.md)
- 最後に確認した実行。初回の採取と `/tmp` からの追加採取は各183判定中183件と211判定中211件を通過。停止ログのコンマで取りこぼした照合を修正し、保存プロファイルの再解析で182判定を通過した。26試行でPCM・観測・計画・拍が基準と一致し、追加採取の2実行で固定上流の試験各17件を通過した。新規成果約30.04 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-firefox-http-channel-20261121-ipc/manifest.json)・[追加採取](runs/worklet-song-firefox-http-channel-20261121-repeat/manifest.json)・[全生ログの再解析](runs/worklet-song-firefox-http-channel-20261121-verified/manifest.json)
- 未達の条件。親のメインスレッドで遅れたIPCをどのタスクや優先度が妨げたか、キャッシュ照会とコールバック待ちの内訳は未特定。受信後に親の完了処理まで173.7 msかかった保存試行ではIPCが無効だった。最初の描画量子の負荷、物理出力と人による試聴が残る。[IPCの計測と残る差](notes/worklet-song-firefox-http-channel.md#ipcを採れた8試行)
- 次に、研究ワークスペースで `rg -n 'ipc_messages|peer_transfer_end_to_parent_handler|parent_begin_connect_end_to_cache_callback' tools/measure_worklet_song_firefox_http_channel.py` を実行する。再実行 `1-serial` と `2-serial` の親プロファイルの受信から処理の区間を開き、スレッドの活動区間とIPCタスクの投入・実行を追う。同じチャネルに結べる印を定めてから、通常画面で現行順と並行登録を追加比較する。[再現と保存](notes/worklet-song-firefox-http-channel.md#再現と保存)

## Firefoxの親メインスレッドへのIPCタスク投入

- 完了した項目。保存済み8試行を再解析し、通常の歌唱画面でフロー付きの12試行を追加した。全12件で到達からタスク投入まで2.0〜12.8 µs。現行順で長い待ちを再現した2回では、投入から受信処理まで128.625 msと133.290 msかかった。親メインはCPUの標本で覆えた時間の約98.4%で実行していた。[事前登録](cases/worklet-song-firefox-ipc-queue.json)・[読解と観測](notes/worklet-song-firefox-ipc-queue.md)
- 最後に確認した実行。追加採取2実行で69件と75件の判定、上流試験各17件を通過した。初版はフローの文字列表を復元せず識別子の照合に失敗した。初版の判定を保持し、修正後の全生ログの再解析で20試行の端点を再現した。追加12試行のPCM・観測・計画・拍は基準と一致し、新規成果約76.11 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-firefox-ipc-queue-20261121-a/manifest.json)・[再実行](runs/worklet-song-firefox-ipc-queue-20261121-repeat/manifest.json)・[全生ログの再解析](runs/worklet-song-firefox-ipc-queue-20261121-verified/manifest.json)
- 未達の条件。 `Runnable` の実行名と優先度は取得できておらず、親メインが先に処理した仕事は未特定。物理出力、最初の描画量子の負荷、人による試聴は引き続き未計測。[投入とCPU時間](notes/worklet-song-firefox-ipc-queue.md#フローの照合)
- 次に、研究ワークスペースで `rg -n 'sampled_cpu|runnable_execution_candidates|queue_to_handler_ms' tools/measure_worklet_song_firefox_ipc_queue.py` を実行する。親メイン用のスタック採取を使い、現行順と並行登録で同じIPCフローを基準にOS・Gecko・JavaScriptの採取区間を照合する小さいケースを登録する。[再現と保存](notes/worklet-song-firefox-ipc-queue.md#再現と保存)

## FirefoxのWorklet取得とPlaywrightの応答本文の展開

- 完了した項目。現行順で投入後137.535〜182.982 ms待った3試行では、CPU重みの94.6〜95.9%がPlaywrightの `NetworkObserver.js` を含むスタックだった。WASMと辞書の応答本文を歌唱完了後に読むと、現行順の待ちの中央値が148.654 msから0.013 msと0.015 msになった。Context作成開始から接続までの現行順の中央値は227 msから63 msと59 ms。既定の実時間歌唱採取にも延期を採用した。[事前登録と追試](cases/worklet-song-firefox-ipc-stack.json)・[読解と計測](notes/worklet-song-firefox-ipc-stack.md)
- 最後に確認した実行。初回の現行順1件は、同一HTTPチャネルの本文到達を1件と仮定した集計が取りこぼした。68/69判定を保存し、分割された到達マーカーをリストで読み直した。延期2実行は各121判定、固定上流の関連試験は各17件を通過した。18試行のPCM・観測・計画・拍は基準と一致した。FirefoxとChromiumの標準採取2実行は各177/179判定で、歌詞エラーからの復帰、停止と再開、PCMと資産は照合できた。成果はスタック比較約130.48 MB、標準採取約125.68 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-firefox-ipc-stack-20261121-a/manifest.json)・[延期](runs/worklet-song-firefox-ipc-stack-20261121-deferred/manifest.json)・[既定化後の再実行](runs/worklet-song-firefox-ipc-stack-20261121-repeat/manifest.json)・[標準採取の再実行](runs/worklet-live-song-cross-browser-20261121-deferred-default-repeat/manifest.json)
- 未達の条件。Firefoxの通常時計のp99は、標準採取の各2試行で3.00 msとなり描画の基準を超えた。別のネイティブ計測4試行では冒頭32量子を除くp99は1.713〜1.800 msで、先頭量子は3.43〜4.08 msだった。最初の量子で負荷が高い処理の内訳、物理出力の時刻、人による試聴が残る。[標準採取の計時](notes/worklet-song-firefox-ipc-stack.md#標準の歌唱採取)
- 次に、研究ワークスペースで `rg -n 'process\(|renderInto|readObservation|firstOutputFrame' ../../../web/prototypes/chimera-research/src/fixed-processor.ts` を実行する。資産の検証を歌唱後に行う既定条件で、`process()` の先頭2量子のWASM呼び出しと観測処理を切り分けるケースを登録する。[再現と保存](notes/worklet-song-firefox-ipc-stack.md#再現と保存)

## Firefoxの歌唱開始時のWASM描画とJS観測

- 完了した項目。先頭2量子と冒頭32量子を描画した後の2量子に境界マーカーを追加した。計時付きの全6試行で、先頭量子が定常部より長くなった分の83.1〜86.8%はWASM呼び出し内にあった。先頭量子の2回のWASM呼び出しは3.312〜3.507 ms、JSの観測コピーは0.036〜0.047 msだった。[事前登録](cases/worklet-live-song-render-phases.json)・[読解と計測](notes/worklet-live-song-render-phases.md)
- 最後に確認した実行。初回と `/tmp` からの再実行は各58判定、固定上流試験各17件を通過した。全12試行のPCM・観測・予定拍・調音計画が基準と一致し、各演算区間とプロファイルをRTL9210B-CGに約33.72 MB保存した。[初回](runs/worklet-live-song-render-phases-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-render-phases-20261121-repeat/manifest.json)
- 未達の条件。マーカーのない全6試行で先頭量子が2.667 msの予算を超え、第2量子は無印1回、計時付き5回で超えた。WASM区間のどの処理が最初に長くなるか、物理出力の時刻、人による試聴が残る。[処理時間の分布](notes/worklet-live-song-render-phases.md#再実行と処理時間の分布)
- 次に、研究ワークスペースで `rg -n 'warmupRenderWrapper|configureHandle|mark\?\.\("wasm-' crates/vocal-wasm/host/fixed-voice.ts` を実行する。本番と同じWASMインスタンスで0フレーム呼び出しと使い捨て状態の事前描画を対照し、先頭量子のWASM区間とPCMを照合するケースを登録する。[既存の事前描画方式](notes/worklet-wasm-dsp-warmup.md)

## Firefoxの歌唱開始前の使い捨て状態による事前描画

- 完了した項目。同じスコアを同じWASMインスタンス上の別の発声状態に設定し、未準備、0フレーム1,000回、64フレームを4回描画する条件を比較した。事前描画で先頭量子のWASM時間の中央値が未準備の41.6〜41.9%になり、事前描画の全6試行で全量子が2.667 ms以内だった。構築の中央値は未準備より6.64〜6.75 ms増えた。PCM全91,200点、観測1,425行、調音計画と拍は一致した。[事前登録](cases/worklet-live-song-render-warmup.json)・[読解と結果](notes/worklet-live-song-render-warmup.md)
- 最後に確認した実行。修正後と `/tmp` からの再実行は各127判定、固定上流試験は各17件を通過した。初回のNumPy整数のJSON変換エラーを保存し、元の生データから127判定を再照合した。従来の固定発声の事前描画と歌唱の区間計時は292判定と58判定を通過した。全27 WAVが基準とバイト一致した。入力1,356件と出力320件のハッシュを確認し、計測成果約107.98 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-render-warmup-20261121-a/manifest.json)・[修正後](runs/worklet-live-song-render-warmup-20261121-b/manifest.json)・[再実行](runs/worklet-live-song-render-warmup-20261121-repeat/manifest.json)・[固定発声の回帰確認](runs/worklet-wasm-dsp-warmup-20261121-score-regression/manifest.json)・[歌唱区間計時の回帰確認](runs/worklet-live-song-render-phases-20261121-warmup-regression/manifest.json)
- 未達の条件。事前描画を指定できる研究用の入口を用意した。FirefoxのWASM関数内部でコンパイルやメモリの状態が処理時間に占める割合、必要な事前描画の最短フレーム数、本番の量子に印を入れないときの効果、物理出力の時刻、人による試聴が残る。[時間差と残る条件](notes/worklet-live-song-render-warmup.md#再実行と処理時間)
- 次に、研究ワークスペースで `rg -n 'renderPreparation|traceRenderPhases' ../../../web/prototypes/chimera-research/src/{render-fixed-voice,fixed-processor}.ts` を実行し、歌唱の準備を渡す箇所を開く。同じ `Pop Dee` で未準備と64、128、256フレームの事前描画を比較する条件を登録する。量子内の印を外した状態で、ネイティブ区間の先頭2量子、構築時間、PCMを照合する。[今回の再現コマンド](notes/worklet-live-song-render-warmup.md#再現と保存)

## Firefoxの歌唱開始に必要な事前描画フレーム数

- 完了した項目。48 kHzの `Pop Dee` で本番量子内の印を外し、未準備と64・128・256フレームを比較した。128フレームの先頭量子は2.723〜2.923 msで全8回が予算超過だったため、192と256の追加比較を登録した。192フレームは先頭量子が1.779〜1.866 ms、全8試行の全量子が予算内。同じ組で256フレームより構築時間の差の中央値が1.05〜1.17 ms短かった。[4条件の事前登録](cases/worklet-live-song-render-warmup-frames.json)・[192フレームの事前登録](cases/worklet-live-song-render-warmup-intermediate.json)・[読解と結果](notes/worklet-live-song-render-warmup-frames.md)
- 最後に確認した実行。4条件の初回と `/tmp` からの再実行は各157判定、192と256の追加比較は各81判定、既存の比較の回帰確認は127判定、固定上流の関連試験は各17件を通過した。57本のWAVが基準とバイト一致した。入力1,365件と出力424件のハッシュを照合し、計測成果約154.04 MBをRTL9210B-CGに保存した。[4条件の初回](runs/worklet-live-song-render-warmup-frames-20261121-a/manifest.json)・[4条件の再実行](runs/worklet-live-song-render-warmup-frames-20261121-repeat/manifest.json)・[追加比較の初回](runs/worklet-live-song-render-warmup-intermediate-20261121-a/manifest.json)・[追加比較の再実行](runs/worklet-live-song-render-warmup-intermediate-20261121-repeat/manifest.json)・[既存指定の回帰確認](runs/worklet-live-song-render-warmup-20261121-frame-option-regression/manifest.json)
- 未達の条件。128フレームで最初の2量子が予算を満たす予測は外れた。192フレームの構築は中央値で6.8〜6.9 msだった。同じContextですでに再生している音声への構築の影響、WASM内で先頭の処理が長くなる原因、物理出力と人による試聴が残る。[128フレームで残った予算超過](notes/worklet-live-song-render-warmup-frames.md#64128256フレームの比較)・[192フレームの結果](notes/worklet-live-song-render-warmup-frames.md#192フレームの追加比較)
- 次に、研究ワークスペースで `rg -n 'installSharedContextMarker|withRealtimeContext' ../../../web/prototypes/chimera-research/{tools/capture-worklet.mjs,src/render-fixed-voice.ts}` を実行する。96 kHz固定発声で使った先行音の検査を読み、同じ48 kHz Contextで先行音を鳴らしながら歌唱ノードを追加するケースを登録する。未準備と192フレームで構築をまたぐ先行音のPCM、コールバック開始間隔、歌唱の先頭2量子を対照する。[既存の先行音の測定](notes/worklet-wasm-wrapper-shared-context.md)・[今回の再現コマンド](notes/worklet-live-song-render-warmup-frames.md#再現と保存)

## Firefoxの先行音が鳴るContextでの歌唱の構築

- 完了した項目。48 kHzの先行音を192量子以上処理したContextに `Pop Dee` の歌唱ノードを追加した。192フレームの事前描画で、構築をまたぐ先行音の間隔は同じ組で引いた増分の中央値が5.22〜5.23 msだった。8組の差は、構築時間の増分と0.056 ms以内で一致した。先行音512量子のPCMとフレーム列は独立計算と一致し、事前描画の8試行で歌唱の全量子が予算内だった。[事前登録](cases/worklet-live-song-shared-context.json)・[読解と結果](notes/worklet-live-song-shared-context.md)
- 最後に確認した実行。修正後と `/tmp` からの再実行は各133判定、上流試験各17件を通過した。初回はNumPyの真偽値をJSONに書けず失敗したため、元の記録を保存して133判定を再照合した。24試行の先行音と歌唱を波形全体で確認した。従来の共有Context固定発声と先行音を加えない歌唱計時は166判定と58判定を通過。5実行で入力1,366件と出力326件をハッシュ照合し、成果約107.75 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-shared-context-20261121-a/manifest.json)・[修正後](runs/worklet-live-song-shared-context-20261121-b/manifest.json)・[再実行](runs/worklet-live-song-shared-context-20261121-repeat/manifest.json)・[固定発声の回帰確認](runs/worklet-wasm-wrapper-shared-context-20261121-song-regression/manifest.json)・[歌唱計時の回帰確認](runs/worklet-live-song-render-phases-20261121-shared-context-regression/manifest.json)
- 未達の条件。予備照合では構築を含むFirefoxの出力コールバックの予算は5.333 msで、事前描画の8試行は6.600〜6.958 msかかった。出力バッファを渡した時刻、音声機器での欠落、聴感、WASM内部で先頭の処理が長くなる原因は未確認。[出力コールバックの予備照合](notes/worklet-live-song-shared-context.md#出力コールバックの予備照合)
- 次に、研究ワークスペースで `rg -n 'constructor_gap|thread_intervals|profiler_command' tools/{measure_worklet_live_song_shared_context,measure_worklet_firefox_native_clock,measure_worklet_live_ipa_cross_browser}.py` を実行する。同じプロファイルの `AudioCallbackDriver::DataCallback`、リアルタイム予算、`GraphRunner::OneIteration` を起点に、構築を含む出力バッファの要求と処理の時刻を保存するケースを登録する。[今回の再現コマンド](notes/worklet-live-song-shared-context.md#再現と保存)

## Firefoxの出力要求とグラフ前進の対応

- 完了した項目。48 kHzの共有Contextで保存済み16試行と新規8試行を比較した。歌唱ノード構築前後の408要求はすべて256フレームで、グラフ前進と先行音の連続した128フレーム量子2個に対応した。事前描画の全12試行で構築直後の出力要求が予定より5.31〜7.43 ms遅れ、続く間隔が約5.33 msに戻った後も8回先で5.32〜7.40 msのずれが残った。予備に読んだ1組を除いても予測を満たした。[事前登録](cases/worklet-live-song-output-callback.json)・[読解と結果](notes/worklet-live-song-output-callback.md)
- 最後に確認した実行。新規採取は133判定と固定上流の17試験を通過。保存分と新規分の解析、および `/tmp` からの再解析は各242判定で、JSONまでバイト単位で一致した。24試行の先行音PCMと歌唱WAVは基準に一致し、入力558件と出力79件のハッシュを照合した。新規採取の成果約26.7 MBをRTL9210B-CGに保存した。[新規採取](runs/worklet-live-song-shared-context-20261121-output-fresh/manifest.json)・[解析](runs/worklet-live-song-output-callback-20261121-a/manifest.json)・[再解析](runs/worklet-live-song-output-callback-20261121-repeat/manifest.json)
- 未達の条件。構築後の次の出力要求は新規採取でほぼ2要求分後、保存済みではそこからさらに1.60〜2.10 ms後に始まった。この差が生じた位置、Firefoxが渡す出力バッファのPCM、音声機器での欠落と聴感が残る。[要求ごとの時刻とフレーム数](runs/worklet-live-song-output-callback-20261121-a/summary.json)
- 次に、研究ワークスペースで `rg -n 'DRIVER|DISPATCH|ADVANCE|locate_callbacks' tools/measure_worklet_live_song_output_callback.py` を実行する。AudioIPCのサーバー側のコールバック、クライアントへの要求送信と応答、クライアントの `DataCallback` を同じ時間軸で照合する条件を登録し、構築の前後でどの区間から間隔が広がるかを確かめる。[今回の再現コマンド](notes/worklet-live-song-output-callback.md#再現と保存)

## FirefoxのAudioIPCの端点を調べる予備採取

- 完了した項目。48 kHz・256フレームの出力要求で、AudioIPCのサーバーからクライアントへの要求、共有メモリを使う処理、応答後のコピーを読解した。Firefoxの診断ログとシステムトレースで試した採取範囲を記録し、XMLから指定PID・TIDの送受信を抽出するツールを作った。既知ソケットの全プロセス収録で、7バイトの送受信12組のfd・バイト数・時刻を照合した。[事前登録](cases/worklet-live-song-audioipc.json)・[読解、欠測と再現手順](notes/worklet-live-song-audioipc.md)
- 最後に確認した実行。Firefoxの通常の歌唱入力を事前描画あり・なしで1組再採取し、歌唱・先行音の34判定と成果39件のハッシュ確認を通過した。AudioIPCのログ16件は空だった。生トレースはRTL9210B-CGに保存し、抽出後に再生成可能な一時XML約1.30 GBを整理した。[Firefoxの最終確認](runs/worklet-live-song-audioipc-20261121-pilot-verified-b/manifest.json)
- 未達の条件。Firefoxのサーバーでの要求発行・応答受信時刻が欠測。全プロセスの単発対照では開始通知と実際の収録開始が約0.7〜0.9秒ずれ、歌唱の全プロセス収録では保存が完了せず、通常より処理時間も増えた。4組を用いた予測の判定、Firefoxが機器に渡すPCMと聴感の確認は残る。[全プロセス収録の失敗記録](runs/worklet-live-song-audioipc-20261121-system-pair/manifest.json)
- 次に、研究ワークスペースで `rg -n 'shared_context_marker|songUrl|click\(' ../../../web/prototypes/chimera-research/tools/capture-worklet.mjs` を実行する。先行音が動き始めてから収録を準備し、構築を行う時刻を独立に記録する条件を1組登録する。実際の収録範囲に17要求すべてが入ることを確認したうえで、サーバー・クライアントの同じ要求を送受信の順序とバイト数で対応づける。採取による構築時間の増分も、ログだけの対照に照合する。[抽出コマンド](notes/worklet-live-song-audioipc.md#再現と保存)

## Firefoxのサーバー送信とクライアントの出力要求の対応

- 完了した項目。先行音192量子の後に収録を起動し、歌唱ノードの構築を解放する時刻を保存した。Audio System Traceの3条件では収録範囲、AudioIPC端点、先行音採取にそれぞれ欠測があった。System Call Traceだけに絞ると約2.32秒の実データに未準備・事前描画の前後17要求が全件入り、各方向16バイトの送受信とGeckoのコールバックを一意に照合できた。直後のサーバー送信間隔は5.319 msと10.672 msで、クライアントの処理開始間隔との差は両条件とも2.4 µs以内だった。増分5.353 msのうち要求の往復が5.269 ms、応答後から次の送信までが0.085 msだった。[結果と再現手順](notes/worklet-live-song-audioipc.md#システムコールだけを採った1組)
- 最後に確認した実行。システムコールのみの採取とトレースなしの回帰確認はいずれも34判定を通過した。34要求で256フレームの要求とグラフ前進、先行音2量子を個別に検証した。時刻の比較は合成17要求の対照でも通過し、1バイトを変えた対照は棄却された。4件の採取から計42成果のサイズとハッシュを照合した。RTL9210B-CGに生トレースと抽出結果を残し、再生成可能な一時XMLを3.95 GB整理した。[計測のマニフェスト](runs/worklet-live-song-audioipc-20261121-gated-syscalls/manifest.json)・[回帰確認](runs/worklet-live-song-audioipc-20261121-gated-regression/manifest.json)
- 未達の条件。音声機器が要求する時刻、サーバー実時間コールバックの入口、音声機器へ渡したPCMが未取得。確認した組では送信時点で間隔が広がっている。登録済み4組中3組以上の再現性と、サーバー側で広がり始める箇所は未判定。[元の判定基準](cases/worklet-live-song-audioipc.json)
- 次に、研究ワークスペースで `rg -n 'minimum_trials_meeting_prediction|pilot_rounds|marker_ready_offset_ms' cases/worklet-live-song-audioipc{,-system-calls}.json` を実行する。システムコールのみの採取を元の4組の比較順へ広げ、全17要求を照合して増分2 msと両側の差0.5 msの登録条件を判定する。別の1組でXcodeのAudio Clientをシステムコールと併用し、機器による要求時刻とソケット送信を同じ窓で取得できるか確認する。[現在の再現コマンド](notes/worklet-live-song-audioipc.md#1組を再現する)

## Firefoxの出力要求を4組で照合し、音声I/Oの開始へ遡る

- 完了した項目。登録した4組では、事前描画の全4試行で構築直後のサーバー送信間隔が10.662〜10.681 msとなり、予算より2 ms以上長く、クライアントの開始間隔との差は5.5 µs以内だった。未準備の有効3試行は5.312〜5.323 ms。音声I/Oを加えた再採取では、各17要求をFirefoxのCore AudioのI/O区間に対応づけ、開始間隔が未準備5.319 ms、事前描画10.658 msであることを確かめた。[4組の結果](runs/worklet-live-song-audioipc-20261121-series-analysis/summary.json)・[音声I/Oの読解と結果](notes/worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)
- 最後に確認した実行。4組は採取117/118判定で、最初の未準備だけ終了待ちのタイムアウトと構築後3要求のトレース欠測があった。保存済みの歌唱WAV・観測・スコアは8試行で基準と一致した。136要求でフレーム数を、133要求で16バイトの送受信を照合した。Audio Clientの再採取は34判定を通過し、当初の事前描画で2.312 ms増えた構築時間が、再採取では0.669 msの増加に収まった。元トレースと照合結果はRTL9210B-CGに保存した。[4組の採取](runs/worklet-live-song-audioipc-20261121-series-a/manifest.json)・[Audio Clientの再採取](runs/worklet-live-song-audioipc-20261121-audio-client-repeat/manifest.json)
- 未達の条件。観測したのはFirefox親プロセスのCore AudioのI/O区間。機器へ渡すPCMの連続性、機器での欠落と人による聴感の評価は残る。音声機器のI/O区間を使った有効な比較は1組なので、別機器や別レートへの一般化も未確認。[測定範囲と残る差](notes/worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)
- 次に、研究ワークスペースで `rg -n 'shared_context_marker|saveSharedContextMarker' ../../../web/prototypes/chimera-research/tools/capture-worklet.mjs` を実行する。番号付きの先行音を同じ48 kHzの出力経路で採り、正常な期間のフレーム一致を先に確認したうえで、I/O間隔が広がる構築直後に欠落、繰り返し、無音のどれが出るかを比較する。[フレーム印を生成するWorklet](../../../web/prototypes/chimera-research/tools/shared-context-marker-worklet.js)

## 出力PCMの照合器とCore Audioの要求時刻の対照

- 完了した項目。Firefoxの先行音を左右逆相にできるようにし、差分からフレーム番号を復元する解析と、試験プロセスを指定するCore Audioのプロセスタップを用意した。内部対照で34判定を通過し、合成した出力で各256フレームの欠落・繰り返し・無音・印のみの消失を別々に検出した。実際のFirefoxプロファイルに対応する4,352フレームでも、入れた欠落を復元した。[ケース](cases/worklet-live-song-process-tap.json)・[読解と対照](notes/worklet-live-song-output-pcm.md)
- 最後に確認した実行。Firefoxのタップ接続では歌唱と先行音の34判定が通り、タップ準備通知が来なかった2試行のPCMは欠測として保存した。別の自作AudioUnitでは512フレームの予算10.667 msに対し8.4 msの待機で要求時刻は連続した。14 msにした2試行では次のホスト間隔が21.333 ms、要求されたサンプル時刻が512フレーム分飛び、アプリの送出連番は連続した。生データの整数時刻とフレーム順を再計算して確認した。[Firefox接続](runs/worklet-live-song-process-tap-20261121-bridge-a/manifest.json)・[欠測の分析](runs/worklet-live-song-process-tap-20261121-bridge-analysis/summary.json)・[AudioUnitの再実行](runs/worklet-live-song-output-deadline-20261121-native512-repeat/manifest.json)
- 未達の条件。macOSのシステムオーディオ録音許可が利用できることを確認できず、既知の試験音とFirefoxのプロセス出力を採れていない。Firefoxの出力PCMの欠落・繰り返し・無音、実機に渡るPCMと聴感は未判定。AudioUnitの対照で観測したのは512フレームの要求時刻で、Firefoxの256フレームの出力PCMは別に測る必要がある。[プロセスタップの許可待ちの記録](runs/worklet-live-song-process-tap-20261121-staged-probe/manifest.json)
- 次に、研究ワークスペースで `rg -n 'minimum_contiguous_frames|maximum_error_marker_units' cases/worklet-live-song-process-tap-probe.json` を実行する。macOSでCHIMERA PCM Probeのシステムオーディオ録音許可を確認後、`tools/measure_worklet_live_song_process_tap.py` で既知PCMの照合を再開する。合格を確認したらFirefoxのプロセス出力を1組取り、同じ解析で構築前後を比較する。専用のFirefoxで追加観測が必要な場合は、macOSのcubebバックエンドの `audio-dump` を別条件として調べる。[再現コマンド](notes/worklet-live-song-output-pcm.md#再現)

## Firefoxと同じcubebで256フレームの要求時刻と出力PCMを照合

- 完了した項目。Playwright 1.64.1のGeckoと `cubeb-coreaudio` のコミットを照合した。固定版cubebがCore Audioに返すバッファと時刻を同時に採るパッチを用意し、Firefox同梱のソースに適用できることを確認した。自作プログラムで256フレーム要求を再現し、8.4 msの待機を入れた4試行は、次の予定ホスト時刻まで10.667 msとなり、機器のサンプル時刻が256フレーム飛んだ。対照4試行の機器サンプル時刻と、全8試行でcubebが返すPCMの連番は連続した。[ケース](cases/cubeb-output-callback-probe.json)・[読解と実測](notes/cubeb-output-callback-probe.md)
- 最後に確認した実行。初回と `/tmp` からの再実行で各52判定、固定版cubebの等レートの試験1件を通過した。8試行で各4,352フレームのステレオPCMが独立計算とビット一致した。入力12件と出力36件のサイズとSHA-256を照合し、採取成果約2.16 MBをRTL9210B-CGに保存した。[初回](runs/cubeb-output-callback-20261121-a/manifest.json)・[再実行](runs/cubeb-output-callback-20261121-repeat/manifest.json)
- 未達の条件。試験用Firefoxのビルドと歌唱構築中の出力PCMの採取は未実施。機器のサンプル時刻が飛んだ間の実出力と人による試聴は未判定。専用アプリのシステムオーディオ録音許可が利用できることも未確認。[測定範囲](notes/cubeb-output-callback-probe.md#実測)・[プロセスタップの記録](runs/worklet-live-song-process-tap-20261121-staged-probe/manifest.json)
- 次に、研究ワークスペースで `rg -n 'CHIMERA_FIREFOX' ../../../web/prototypes/chimera-research/tools/capture-worklet.mjs` を実行する。固定GeckoとPlaywrightの差分に計測パッチを加え、外部ディスク上で `./mach build` する。その試験ビルドで未準備・192フレーム事前描画を1組採り、先行音の連番と出力時刻を照合する。録音許可が利用できる場合は、既知PCMのプロセスタップの対照も再開する。[Firefoxに載せる次の比較](notes/cubeb-output-callback-probe.md#firefoxに載せる次の比較)

## cubeb計測を組み込むFirefoxのネイティブビルドと比較入口

- 完了した項目。Playwright 1.64.1が指定するGeckoをRTL9210B-CGに取得し、Jugglerとcubeb計測を適用した。同梱cubebの40ファイルのチェックサムを照合した。macOS SDK 26.5、WASI SDK 34、ホスト・ターゲットのClang設定と短い一時領域を用意し、構成を完了した。既存の歌唱入口に `--cubeb-output` を追加した。[ケース](cases/worklet-live-song-cubeb-output.json)・[読解と再現](notes/worklet-live-song-cubeb-output.md)
- 最後に確認した実行。配布版Firefoxで34判定、実プロファイルを使った合成入力で8判定、更新したcubebの既定128ブロックの対照で52判定を通過した。新しい入口で配布版Firefoxを検証すると、71判定中69判定を通過し、想定した2試行でcubeb出力の欠測を検出した。自作の再生で256ブロック、左右65,536フレームを採取した。試験用Firefoxのコンパイルでは、更新した計測パッチを含むcubebライブラリが生成された。[先行音の回帰](runs/worklet-live-song-cubeb-output-20261121-marker-regression/manifest.json)・[解析の対照](runs/worklet-live-song-cubeb-output-20261121-analysis-control/summary.json)・[欠測の対照](runs/worklet-live-song-cubeb-output-20261121-missing-output-control/manifest.json)・[既定上限の回帰](runs/cubeb-output-callback-20261121-block-limit-regression/manifest.json)・[ビルドログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-mach-build-256.log)
- 未達の条件。試験用Firefoxの起動と、歌唱ノード構築を含む試行の出力PCMは未確認。物理機器側の音と聴感の条件も残る。[比較位置](notes/worklet-live-song-cubeb-output.md#読解と比較位置)
- 次に、RTL9210B-CGの `gecko-mach-build-256.log` と `gecko-cubeb-song.log` を確認する。稼働中のビルドの成功後に `post-build-cubeb-song.sh` がPlaywrightで起動を確認して、`worklet-live-song-cubeb-output-20261121-native-a` を実行する。歌唱の採取が完了したら `runs/worklet-live-song-cubeb-output-20261121-native-a/summary.json` を開き、先行音の境界をcubebのPCMに結びつけ、未準備・事前描画の時刻と波形を照合する。[再現コマンド](notes/worklet-live-song-cubeb-output.md#再現)・[ビルド後のログ](/Volumes/RTL9210B-CG/voice-simulator/build/chimera-cubeb-output/gecko-cubeb-song.log)

## 試験用Firefoxで歌唱構築前後の要求時刻とPCMを採取

- 完了した項目。Clang 21で失敗したZucchiniの単体テストの型を修正し、該当8テストを通してFirefoxのビルドを完了した。Playwright 1.64.1が接続したNightly 157.0で、採取の有無、未準備と192フレーム事前描画を比較した。事前描画ありの両試行で次の要求まで10.667 msとなり、機器のサンプル時刻が256フレーム飛んだ。未準備は両試行とも5.333 msで連続した。[ビルドと実測](notes/worklet-live-song-cubeb-output.md#試験用firefoxの実測)
- 最後に確認した実行。初回と `/private/tmp` からの再実行で各71判定、固定上流の17テストに合格した。採取した全4試行で前後4,352フレームの先行音が独立計算した連番と一致し、欠落、繰り返し、無音は0だった。構築時間の差は−0.114〜+0.187 msで2 msの条件内。入力568件と出力106件のサイズとSHA-256を照合し、採取成果約32.03 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-cubeb-output-20261121-native-a/manifest.json)・[再実行](runs/worklet-live-song-cubeb-output-20261121-native-repeat/manifest.json)
- 未達の条件。機器のサンプル時刻が飛んだ区間で、cubebより後ろの信号に欠落、繰り返し、無音が生じるかは未測定。機器から実際に出た音と人による試聴は未確認。[既知PCMのプロセスタップの記録](notes/worklet-live-song-output-pcm.md#実行した採取と対照)
- 次に、`notes/worklet-live-song-output-pcm.md` の再現手順を開く。プロセスタップの録音許可が利用できる場合は、まず通常の `measure_worklet_live_song_process_tap.py <実行ID> <専用アプリ>` で既知PCMを照合する。校正が成立した後、同じFirefoxの構築前後17要求をタップPCMとcubebで対応づける。[再現手順](notes/worklet-live-song-output-pcm.md#再現)

## cubebとプロセスタップの同時採取と時刻照合

- 完了した項目。同じ試験用Firefoxのcubebとプロセスタップに採取を指示する入口を追加した。先行音の64量子でタップを起動し、192量子とタップの準備を待って歌唱ノードを構築する。二地点のPCMを先行音の両端で合わせ、欠落、繰り返し、無音、時刻の飛びを別々に測る。[ケース](cases/worklet-live-song-paired-output.json)・[読解と照合方法](notes/worklet-live-song-paired-output.md)
- 最後に確認した実行。模擬タップの8判定、試験用Firefoxで準備通知だけを模擬した再判定の17判定、cubeb単独採取の71判定を通過した。早期通知は先行音8,192フレーム、構築を含む要求は24,576フレームに現れた。最初の対照でWAVの読み出しに失敗した2判定を保存し、展開した同じ生データで歌唱WAV全体の一致を確認した。全5実行の入力458件と出力106件を照合し、採取成果約24.37 MBをRTL9210B-CGに保存した。[時計の対照](runs/worklet-live-song-paired-output-20261121-clock-control/summary.json)・[再判定](runs/worklet-live-song-paired-output-20261121-gate-reanalysis/summary.json)・[回帰](runs/worklet-live-song-paired-output-20261121-cubeb-regression/manifest.json)
- 未達の条件。専用アプリの既知PCMの再校正は35秒でタイムアウトし、システムオーディオの録音許可とタップ実データは確認できなかった。校正が不合格のときに同時採取を開始しないことを確認した。機器から出た音と聴感も未確認。[校正の再試行](runs/worklet-live-song-process-tap-20261121-calibration-recheck/manifest.json)
- 次に、`notes/worklet-live-song-paired-output.md` の再現を開く。既知PCMの校正が通ったアプリと実行IDを `--paired-process-tap` に渡して1組採る。同じ構築前後17要求の `paired_output` で、タップの連番と両端の時刻差を実データから確認する。[同時採取の再現手順](notes/worklet-live-song-paired-output.md#再現)

## 歌唱の事前描画を3つの無音量子に分ける比較

- 完了した項目。録音の校正待ちの間に、48 kHzの共有Contextで `Pop Dee` に使う192フレームの事前描画を、構築中に行う場合と、無音中の第1・3・5量子で64フレームずつ行う場合で比較した。一括処理の4試行では構築を含む機器要求が6.51〜6.83 msで、次の機器のサンプル時刻が各256フレーム飛んだ。分割の4試行では構築から最後の準備まで各要求が最大3.80 msに収まり、前後17要求の窓で時刻の飛びは0だった。歌唱の先頭2量子は毎回2.667 ms以内だった。[事前登録](cases/worklet-live-song-split-preparation.json)・[読解と結果](notes/worklet-live-song-split-preparation.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行で各109判定、既存の採取条件の回帰確認で71判定、固定上流試験は毎回17件に合格した。全16試行の歌唱WAVは保存済みの再実装基準とバイト一致した。上流との差は初めてフレーム4,114に現れ、最大2.329 × 10⁻¹⁰で従来の許容幅内だった。採取のある14試行の先行音を各4,352フレーム照合した。入力854件・出力243件のサイズとSHA-256を確認し、計測データ約66.31 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-split-preparation-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-split-preparation-20261121-repeat/manifest.json)・[回帰確認](runs/worklet-live-song-cubeb-output-20261121-split-regression/manifest.json)
- 未達の条件。分割の第1片は4試行とも構築を含む機器要求に入った。さらに処理予算を確保できるか、別のレートや要求サイズでも成立するか、機器の実出力と聴感は未確認。プロセスタップの既知PCMは直近の校正が不合格だった。[録音の校正](runs/worklet-live-song-process-tap-20261121-calibration-recheck/manifest.json)
- 次に、`notes/worklet-live-song-split-preparation.md` の「比較の設計」を開き、研究ワークスペースで `rg -n 'nextPreparationFrame|advanceRenderPreparation' ../../../web/prototypes/chimera-research/src/fixed-processor.ts` を実行する。第1片を次の機器要求へ送る条件を登録し、現在の分割と同じ先行音・歌唱で最も長い要求を比べる。録音の校正が通った時点で同じ窓のプロセスタップ採取を再開する。[今回の再現手順](notes/worklet-live-song-split-preparation.md#再現)

## 分割した事前描画の開始を2量子遅らせる比較

- 完了した項目。48 kHz・256フレーム要求の共有Contextで、`Pop Dee` の3片の事前描画を無音中の第3・5・7量子で開始する条件を追加した。全4試行で第1片は構築の次の要求に移った。構築から3つ後までの要求のピークは3.76〜5.28 msから1.89〜3.53 msとなり、同組の短縮の中央値は1.83 msだった。開始までの3,072フレーム、歌唱の観測、先行音と歌唱のPCMは揃った。[事前登録](cases/worklet-live-song-deferred-split-preparation.json)・[読解と実測](notes/worklet-live-song-deferred-split-preparation.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各77判定、従来条件の回帰確認は109判定、固定上流のテストは各17件を通過した。全14試行の歌唱WAVが再実装の基準とバイト一致。先行音は各4,352フレームを独立計算と照合した。入力857件と出力225件のサイズ・SHA-256を確認し、計測データ約59.77 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-deferred-split-preparation-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-deferred-split-preparation-20261121-repeat/manifest.json)・[回帰確認](runs/worklet-live-song-split-preparation-20261121-deferred-regression/manifest.json)
- 未達の条件。第1片を後ろへ移した4試行は時計と歌唱量子の判定に合格。従来分割では5.049 msと5.283 msで次の機器の予定サンプル時刻が256フレーム飛び、うち1回は歌唱の先頭量子も超過した。名目周期内の処理でも飛びが生じる条件、録音側の校正と機器から出た音の連続性は未確認。[時刻の内訳](notes/worklet-live-song-deferred-split-preparation.md#名目予算の直前で発生した時刻の飛び)・[タップ校正](runs/worklet-live-song-process-tap-20261121-calibration-recheck/manifest.json)
- 次に、`notes/cubeb-output-callback-probe.md` の再現を開き、研究ワークスペースで `rg -n 'delay_us|target_callback_budget|sample_time_gap' tools/{measure_cubeb_output_callback.py,chimera-cubeb-output-probe.rs}` を実行する。48 kHz・256フレームで遅延だけを名目周期の前後に振る条件を登録し、機器時刻の飛びとPCMの連続を別々に測る。校正が通った時点でプロセスタップの同時採取を再開する。[既知PCMの対照](notes/cubeb-output-callback-probe.md#再現)

## 256フレームの機器要求で時刻が飛ぶ範囲の対照

- 完了した項目。Firefoxと同じ固定版cubebと48 kHzの既知PCMを用い、65番目の処理にだけ0〜8.4 msの待機を10段階で加えた。各段階8回の計80試行で、約4.95 ms以下は0/32、5.05 ms設定は5/8、5.175 ms以上は40/40で、次の機器サンプル時刻が256フレーム飛んだ。最短の飛びは実測5.051833 msで、5.333 msの名目周期より約0.2815 ms短かった。返却PCMの連番は全試行で一致した。[事前登録](cases/cubeb-output-callback-deadline-sweep.json)・[読解と実測](notes/cubeb-output-callback-deadline-sweep.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各600判定、従来の無待機と8.4 msの対照は56判定、固定版cubebの等レート試験は1件に合格した。各4,352フレームの左右信号を独立計算と照合し、生CSVの2時計も再確認した。入力20件と出力342件のSHA-256とサイズを確認し、計測データ約22.70 MBをRTL9210B-CGに保存した。[初回](runs/cubeb-output-deadline-sweep-20261121-a/manifest.json)・[再実行](runs/cubeb-output-deadline-sweep-20261121-repeat/manifest.json)・[従来条件の回帰](runs/cubeb-output-callback-20261121-deadline-regression/manifest.json)
- 未達の条件。最長の連続と最短の飛びは0.33 µs離れていたが、5.05 ms付近の試行数は8回。機器要求長が変わったときの余裕、ドライバ内部の締め切り、実出力の連続性は未確認。[観測範囲](notes/cubeb-output-callback-deadline-sweep.md#実測)
- 次に、`notes/cubeb-output-callback-deadline-sweep.md` の再現を開き、研究ワークスペースで `rg -n 'requested_frames|base_case|delay_us' tools/measure_cubeb_output_callback.py cases/cubeb-output-callback-{probe,deadline-sweep}.json` を実行する。実際に48 kHz・512フレームで動くことを確認し、名目周期との差がほぼ一定の時間か周期に比例するかを区別できる待機値を事前登録する。既知PCMのタップ校正が通った場合は同時採取も再開する。[今回の再現手順](notes/cubeb-output-callback-deadline-sweep.md#再現)

## 512フレーム要求で時刻が飛ぶ前後の比較

- 完了した項目。同じ固定版cubeb、48 kHz、内蔵出力で、実機の要求長が512フレームであることを確認した。初回と再実行では、飛びのなかった最長9.911417 msと飛びのあった最短10.084042 msの間が、名目周期に比例する予測とだけ重なった。追加比較で実測10.005000 msの飛びと10.064250 msの連続があり、処理時間に単一の境目を置く判定は成立しなかった。[事前登録](cases/cubeb-output-callback-deadline-sweep-512.json)・[追加の登録](cases/cubeb-output-callback-deadline-sweep-512-refined.json)・[実測](notes/cubeb-output-callback-deadline-sweep-512.md#実測)
- 最後に確認した実行。初回、`/private/tmp` からの再実行、追加比較は各40試行・600判定を通過した。全120試行の左右8,704フレームが独立計算とビット一致した。256フレームの従来対照の56判定、保存済み80試行の再照合、固定版cubebの2件と固定上流CHIMERAの1件の試験を通過した。入力39件と出力504件を照合し、計測データ約64.98 MBをRTL9210B-CGへ保存した。[初回](runs/cubeb-output-deadline-sweep-512-20261121-a/manifest.json)・[再実行](runs/cubeb-output-deadline-sweep-512-20261121-repeat/manifest.json)・[追加比較](runs/cubeb-output-deadline-sweep-512-20261121-refined/manifest.json)・[従来条件の回帰](runs/cubeb-output-callback-20261121-size-regression/manifest.json)
- 未達の条件。予定ホスト時刻への返却時の残り時間で比較すると、512フレームの全試行では飛びの有無の重なりが約0.0054 msで、処理時間だけの場合より小さかった。ドライバの締め切りの位置と、Firefoxでも同じ量で連続性を説明できるかは未確認。機器から実際に出た音も未確認。[探索結果と限界](notes/cubeb-output-callback-deadline-sweep-512.md#予定ホスト時刻と返却時刻の差)
- 次に、`notes/worklet-live-song-deferred-split-preparation.md` を開き、研究ワークスペースで `rg -n 'host_time|returned|entered' tools/{inspect_firefox_cubeb_output,measure_cubeb_output_callback}.py` を実行する。保存済みのFirefoxの生CSVで `mHostTime − 返却前時刻` を再計算し、256フレームの既知PCM対照の連続群と飛び群に照合する。プロセスタップの既知PCMの校正が通れば、実出力との同時採取を再開する。[Firefoxの実測](notes/worklet-live-song-deferred-split-preparation.md#実測)・[今回の再現](notes/cubeb-output-callback-deadline-sweep-512.md#再現)

## 返却時に残る時間でFirefoxの機器時刻を判別

- 完了した項目。48 kHz・256フレームの既知PCM対照80試行から、返却前に残る時間の判定範囲を固定した。Firefoxの34試行で構築をまたぐ要求を再照合し、飛び12回と連続22回を判別した。名目周期と処理時間だけで見落とした2回では、残り時間が1.804750 msと1.569750 msだった。いずれも次の機器時刻で256フレーム飛び、先行音の返却PCMは連続した。[事前登録](cases/worklet-live-song-cubeb-return-time.json)・[読解と実測](notes/worklet-live-song-cubeb-return-time.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各115判定、要約のSHA-256は一致した。前後510区間は両方法とも正答した。通常入口を用いた新規6試行は109判定、固定上流の17テストを通過し、飛び2回と連続4回を両方法で判別した。3実行の入力1,541件と出力97件を照合し、新規採取約25.34 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-cubeb-return-time-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-cubeb-return-time-20261121-repeat/manifest.json)・[回帰確認](runs/worklet-live-song-split-preparation-20261121-return-time-regression/manifest.json)
- 未達の条件。今回のFirefox側の条件は48 kHz・256フレームの `Pop Dee`。ほかの歌唱で判定できるか、装置側の実際の返却期限、機器から出た音の連続性は未確認。[比較範囲](notes/worklet-live-song-cubeb-return-time.md#実測)・[録音の校正](notes/worklet-live-song-paired-output.md)
- 次に、`cases/song-voice-fast.json` を開き、研究ワークスペースで `rg -n 'song_voice_case|build_comparison|planned_beats' tools/{measure_worklet_live_song_render_phases,measure_worklet_live_song_shared_context}.py cases/worklet-song-voice.json` を実行する。既存の短い歌唱ケースのCLIと固定上流の比較を確認してから、同じ先行音で事前描画の配置と返却時刻を比べる条件を登録する。プロセスタップの校正が通れば、同時採取も再開する。[短い歌唱の入力](cases/song-voice-fast.json)・[今回の再現](notes/worklet-live-song-cubeb-return-time.md#再現)

## 短い音符の歌唱で事前描画と返却時刻を照合

- 完了した項目。歌唱画面に `song-voice-fast` の短音プリセットを接続した。240 BPM・各4分の1拍・乱流係数0の歌唱をCLI、固定上流、オフラインWorkletで基準化した。Firefoxの18試行で歌唱開始は3,072フレーム後に揃い、歌唱PCM全49,200フレームがCLI基準とバイト一致した。返却時の残り時間で飛び7回と連続11回を判別した。分割開始を2量子遅らせた6回は時刻が連続し、同組のピーク短縮の中央値は1.82 msだった。[事前登録](cases/worklet-live-song-fast-return-time.json)・[読解と結果](notes/worklet-live-song-fast-return-time.md)
- 最後に確認した実行。CLIは7判定、オフラインWorkletは15判定、Firefoxの短音3実行は各120判定、長音の回帰は77判定を通過した。初回の採取設定に残っていた長音用の末尾補完64フレームを、短音の80フレームに修正して6試行を再確認した。入力1,556件・出力384件を照合し、波形や採取データ約261.0 MBをRTL9210B-CGに保存した。[基準](runs/worklet-song-voice-fast-20261121-return-reference/manifest.json)・[初回](runs/worklet-live-song-fast-return-time-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-return-time-20261121-repeat/manifest.json)・[採取設定の再確認](runs/worklet-live-song-fast-return-time-20261121-schedule-confirmation/manifest.json)・[長音の回帰](runs/worklet-live-song-deferred-split-preparation-20261121-fast-regression/manifest.json)
- 未達の条件。短音と長音には音符の長さ、テンポ、第2音の音高、乱流係数の差がある。個別の設定が返却時刻にどう影響したかは未分離。機器から出た音の連続性は校正待ち。[比較した条件](notes/worklet-live-song-fast-return-time.md#基準と比較条件)
- 次に、`cases/song-voice-fast.json` と `notes/worklet-live-song-fast-return-time.md` を開く。研究ワークスペースで `rg -n 'turbulence|noiseScale' ../../../web/prototypes/chimera-research/src/{main.tsx,render-fixed-voice.ts} crates/vocal-cli/src/timing_case/speech_voice.rs` を実行する。短音の同じスコアと先行音で、乱流係数だけを0と1に変える条件を登録し、基準波形と声門・放射の変化、最初の返却位置を比較する。[今回の再現](notes/worklet-live-song-fast-return-time.md#再現)

## 短音の歌唱の乱流係数を0と1で比較

- 完了した項目。歌唱画面の乱流係数を調整できるようにした。短音の同じスコアで係数0と1を比較し、最初の差を声門乱流圧の20,294フレーム目、声門上圧・流量と放射の20,295フレーム目、PCMの20,309フレーム目に確認した。固定上流でも同じ順序だった。Firefoxでは前後の先行音と、係数ごとの歌唱PCMと計画を16試行で照合した。[事前登録](cases/worklet-live-song-fast-turbulence.json)・[読解と結果](notes/worklet-live-song-fast-turbulence.md)
- 最後に確認した実行。係数1のオフライン基準は16判定、短音の初回と `/private/tmp` からの再実行は各164判定、長音の回帰は15判定に合格した。固定上流の摩擦試験、再実装のフィルタ状態の試験も通過した。入力1,100件と出力308件を照合し、計測データ約320.19 MBをRTL9210B-CGに保存した。[オフライン基準](runs/worklet-song-voice-fast-20261121-turbulence-one/manifest.json)・[初回](runs/worklet-live-song-fast-turbulence-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-turbulence-20261121-repeat/manifest.json)・[長音の回帰](runs/worklet-song-voice-20261121-turbulence-regression/manifest.json)
- 未達の条件。構築要求での返却時の残り時間の対応差の中央値は+0.193 msと+0.632 msで、絶対値0.5 ms未満の予測は再実行で外れた。歌唱の波形に差が出るより前の処理時間差を、乱流係数の影響として切り分けるには追加の対照が必要。機器から出た音も未確認。[返却時刻と波形](notes/worklet-live-song-fast-turbulence.md#実測)
- 次に、`notes/worklet-live-song-fast-turbulence.md` と `crates/vocal-core/src/airway/human/frication.rs` を開く。研究ワークスペースで `rg -n 'register_turbulence|set_noise_gain|noise_scale' crates/vocal-core/src/{airway,voice.rs} tools/upstream_bilabial_probe.rs` を実行する。全体の乱流係数1を保って声門乱流源のゲインだけを0にするケースを登録し、圧力・放射・PCMの最初の差を比べる。録音の校正が通れば機器から出た音と照合する。[今回の再現](notes/worklet-live-song-fast-turbulence.md#再現)

## 短音の歌唱で声門の乱流源を抑えた対照（2026-11-21）

- 完了した項目。声門乱流源の注入先、乱数とフィルタ更新を保ったまま、CLIのケース設定から声門源のゲインを調整できるようにした。全体係数1で声門源のゲインを0にすると、全体係数0との最初のPCM差は20,309から27,285フレームへ移った。狭窄源の活動と放射流量の時間微分の最初の差は27,277フレームで揃った。[事前登録](cases/song-voice-fast-glottis-source.json)・[読解と結果](notes/song-voice-fast-glottis-source.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行で各18件の取得判定、2件の予測、および固定上流の17試験が通過した。結果JSONはバイト一致した。入力268件と出力50件のサイズ・SHA-256を確認し、約346.71 MBをRTL9210B-CGに保存した。[初回](runs/song-voice-fast-glottis-source-20261121-a/manifest.json)・[再実行](runs/song-voice-fast-glottis-source-20261121-repeat/manifest.json)
- 未達の条件。狭窄源から歯の乱流源までの間に現れる差を、まだ源ごとに切り分けていない。今回の個別設定はCLIで検証した。Firefoxの返却時刻への影響と音声機器から出た波形は未確認。
- 次に開くファイルと実行するコマンド。`notes/song-voice-fast-glottis-source.md` と `crates/vocal-core/src/airway/human/frication.rs` を開き、研究ワークスペースで `rg -n 'register_turbulence|constriction|teeth' crates/vocal-core/src/airway/human/frication.rs tools/upstream_bilabial_probe.rs` を実行する。声門源の倍率0と全体係数1を維持し、狭窄源のゲインだけを0にするケースを事前登録する。既存の対照は外部保存を指定する[再現コマンド](notes/song-voice-fast-glottis-source.md#再現)で確認する。

## 短音の歌唱で狭窄の乱流も抑えた対照（2026-11-21）

- 完了した項目。CLIから狭窄の乱流源のゲインを設定できるようにした。全体係数1で声門・狭窄のゲインを0にすると、全体係数0との最初のPCM差は27,285から27,968フレームへ移った。歯の励起は27,927フレーム、順方向の枝圧と放射は次の制御更新の27,968フレームで現れた。登録時の流量0により低域通過周波数が0だった41フレームの区間を両版で確認した。[事前登録](cases/song-voice-fast-constriction-source.json)・[読解と結果](notes/song-voice-fast-constriction-source.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各16判定・6予測・固定上流21試験が通過し、結果JSONはバイト一致した。候補のCargoワークスペースの41試験、従来2条件とのWAV・CSVの一致を確認した。入力276件と出力30件のサイズ・SHA-256を照合し、172.25 MBをRTL9210B-CGに保存した。[初回](runs/song-voice-fast-constriction-source-20261121-a/manifest.json)・[再実行](runs/song-voice-fast-constriction-source-20261121-repeat/manifest.json)
- 未達の条件。41フレームの遅れが歯の低域通過周波数に下限を入れるとどの程度変わるかは未検証。出力フレーム内の内部サンプルの順序、ブラウザでの同条件の再現、機器からの音声出力も未確認。
- 次に開くファイルと実行するコマンド。`notes/song-voice-fast-constriction-source.md` と `crates/vocal-core/src/airway/human/frication.rs` を開く。`rg -n 'let top|lowpass_hz|lowpass_amount' crates/vocal-core/src/airway/{human/frication.rs,network/turbulence.rs}` で歯の帯域とフィルタの更新を確認する。歯の低域通過周波数だけに1,200 Hzの下限を設ける対照を事前登録し、変化を今回の波形と比較する。[今回の再現コマンド](notes/song-voice-fast-constriction-source.md#実装と再現)

## 短音で歯の乱流の低域通過周波数に下限を設ける対照（2026-11-21）

- 完了した項目。CLIから歯の低域通過周波数の下限だけを設定できるようにした。下限1,200 Hzで歯の励起・注入圧・放射・PCMの初回が27,927フレームに揃い、基準の41フレームの間隔がなくなった。直前の閉鎖64フレームではPCMが一致した。独立フィルタで注入圧の最大誤差 `5.88 × 10⁻¹⁵ dyn/cm²` を確認した。[事前登録](cases/song-voice-fast-teeth-lowpass-floor.json)・[読解と結果](notes/song-voice-fast-teeth-lowpass-floor.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行で各8判定・4予測を満たし、結果JSONがバイト一致した。Cargoワークスペースの41試験を通過。入力276件と出力18件のサイズ・SHA-256を照合し、94.61 MBをRTL9210B-CGに保存した。[初回](runs/song-voice-fast-teeth-lowpass-floor-20261121-a/manifest.json)・[再実行](runs/song-voice-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)
- 未達の条件。固定上流とのPCM差の最大は `2.76 × 10⁻³`。今回の対照はCLIで実施し、出力フレーム内での順序、ブラウザでの波形、実機出力と聴感は未確認。
- 次に開くファイルと実行するコマンド。`crates/vocal-wasm/src/lib.rs` の `vocal_start_score_with_body()` と `start_score()`、Web側の `src/render-fixed-voice.ts` の `prepareSongVoice()` を開く。研究ワークスペースで `rg -n 'noiseScale|vocal_start_score_with_body' ../../../web/{prototypes/chimera-research/src,shared} crates/vocal-wasm/src/lib.rs` を実行し、歌唱スコアの乱流設定をWASMに渡す経路を読む。下限0と1,200 Hzの2条件について、声門・狭窄の倍率0を保ち、オフラインWorkletでCLIのPCMに照合するケースを事前登録する。[今回の再現コマンド](notes/song-voice-fast-teeth-lowpass-floor.md#実装と再現)

## 歯の乱流フィルタの設定を歌唱Workletへ渡す（2026-11-21）

- 完了した項目。歌唱画面の声門・狭窄のゲイン倍率と歯の低域通過周波数の下限を、スコアと一緒にWASMへ渡し、再実行ケースに保存した。下限0 Hzと1,200 Hzで各49,200フレームのPCMと769点の10項目の状態がCLIと一致した。全体係数0からのPCM初回差は登録どおり各27,968と27,927フレームで、閉鎖末尾64フレームは一致した。[事前登録](cases/worklet-song-fast-teeth-lowpass-floor.json)・[読解と結果](notes/worklet-song-fast-teeth-lowpass-floor.md)
- 最後に確認した実行。Chromiumの初回と `/private/tmp` からの再実行は各50判定・4予測を満たし、結果JSONと画面から保存したWAV・観測・再実行ケースがバイト一致した。保存したケースのCLI再描画とCargoワークスペースの41試験を確認した。入力578件と出力42件を照合し、6.26 MBをRTL9210B-CGに保存した。[初回](runs/worklet-song-fast-teeth-lowpass-floor-20261121-a/manifest.json)・[再実行](runs/worklet-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)
- 未達の条件。Chromiumのオフライン処理で検証した。64フレーム間隔のWorklet観測では放射の正確な分岐位置を読めない。実時間歌唱の開始時刻、連続性、機器から出た波形と聴感は未確認。
- 次に開くファイルと実行するコマンド。`tools/measure_worklet_live_song_cross_browser.py` と `fixed-processor.ts` の `process()` を開く。研究ワークスペースで `rg -n 'turbulence|scheduledContextFrame|first_output_frame' tools/measure_worklet_live_song_cross_browser.py ../../../web/prototypes/chimera-research/{src/fixed-processor.ts,tools/capture-worklet.mjs}` を実行する。Chromiumの実時間歌唱で下限0と1,200 Hzの開始位置と前後の連続性を比較し、今回のオフラインPCMと照合する条件を登録する。[今回の再現](notes/worklet-song-fast-teeth-lowpass-floor.md#再現)

## 短音の実時間歌唱で歯の乱流フィルタの設定を照合（2026-11-21）

- 完了した項目。通常歌唱と並列観測で下限0 Hzと1,200 Hzを比較した。歌唱の49,200フレームはオフラインとビット一致した。連続8量子の始点から3,072フレーム後に開始し、歌唱の385量子が連続した。並列ノードは最終量子の補完80フレームと前後の無音を検証した。[登録条件](cases/worklet-live-song-fast-teeth-lowpass-floor.json)・[読解と結果](notes/worklet-live-song-fast-teeth-lowpass-floor.md)
- 最後に確認した実行。初回の6件の不一致を保存した。連続区間の始点を追加し、並列観測を絶対フレームで照合する改訂後の2実行は各50判定を通過した。両条件の最初のPCM差は通常・並列とも27,927フレーム。入力817件と出力108件を照合し、12.89 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-a/manifest.json)・[改訂後](runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-b/manifest.json)・[再実行](runs/worklet-live-song-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)
- 未達の条件。最初の量子から常に3,072フレームで始まるという予測は外れた。12試行中8試行で開始待ちのフレームが飛び、連続8量子を数え直した。飛びの発生箇所と原因、機器から出た音と聴感は未確認。
- 次に開くファイルと実行するコマンド。`tools/shared-context-marker.mjs`、`src/worklet-clock.ts` と[今回の初期判定の記録](notes/worklet-live-song-fast-teeth-lowpass-floor.md#初回の判定と計測の改訂)を開く。研究ワークスペースで `rg -n 'shared_context_marker|startupDiscontinuities|startupContiguousFirstContextFrame' ../../../web/prototypes/chimera-research/{tools,src} tools/measure_worklet_live_song_teeth_lowpass_floor.py` を実行する。Chromiumで先行信号が継続するContextと今回の開始待ちを比較する条件を登録する。

## 短音の実時間歌唱で先行信号と開始待ちを比較（2026-11-21）

- 完了した項目。短音 `Pop Dee`、歯のフィルタ下限1,200 Hzを固定し、無音から始める条件と先行信号を流したContextを比較した。無音からの8試行はすべて開始待ちに256〜1,024フレーム飛んだ。先行信号ありの8試行は飛び0。連続8量子の始点から3,072フレームの予約と、全49,200フレームの歌唱PCMおよび先行信号の一致を確認した。[事前登録](cases/worklet-live-song-fast-context-lead.json)・[読解と結果](notes/worklet-live-song-fast-context-lead.md)
- 最後に確認した実行。初回は先行信号ありの歌唱枝で採取の末尾が欠けた。入力が届いた量子を記録開始にする改訂後の初回と `/private/tmp` からの再実行は各130判定を通過した。初回を含め入力814件と出力252件を照合し、27.34 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-context-lead-20261121-a/manifest.json)・[改訂後](runs/worklet-live-song-fast-context-lead-20261121-b/manifest.json)・[再実行](runs/worklet-live-song-fast-context-lead-20261121-repeat/manifest.json)
- 未達の条件。既知信号の振幅と先に動かした音声グラフの寄与は未分離。ユーザー操作からの総所要時間、機器から出た波形と聴感も未測定。
- 次に開くファイルと実行するコマンド。`tools/shared-context-marker.mjs` と `tools/measure_worklet_live_song_context_lead.py` の先行信号の作成・照合を開く。研究ワークスペースで `rg -n 'createBuffer|source\.start|marker_observations' ../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs tools/measure_worklet_live_song_context_lead.py` を実行する。同じ長さとグラフで先行PCMだけを0にした条件を登録し、開始待ちと歌唱PCMを今回の先行信号ありと比較する。[今回の再現](notes/worklet-live-song-fast-context-lead.md#再現)

## 短音の実時間歌唱で先行PCMだけを0にする対照（2026-11-21）

- 完了した項目。同じ先行枝で既知信号と全サンプル0を比較した。両条件の各8試行で、先行枝の512量子すべてに128フレームの入力が届いた。開始待ちの飛びは0で、最初の歌唱呼び出しから3,072フレーム後に始まった。歌唱PCM49,200フレームと状態769行はオフラインと一致した。[事前登録](cases/worklet-live-song-fast-zero-lead-pcm.json)・[読解と結果](notes/worklet-live-song-fast-zero-lead-pcm.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各146判定・2予測を満たした。予約位置に合わせた先行枝と歌唱枝の生波形を独立照合した。入力544件と出力184件のサイズ・SHA-256を確認し、20.39 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-zero-lead-pcm-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-zero-lead-pcm-20261121-repeat/manifest.json)
- 未達の条件。先行枝を32量子より短く動かした場合の連続性、ユーザー操作から歌唱までの総所要時間、機器から出た波形は未測定。
- 次に開くファイルと実行するコマンド。`tools/shared-context-marker.mjs` と `tools/measure_worklet_live_song_zero_lead_pcm.py` を開き、研究ワークスペースで `rg -n 'ready_quanta|captureQuanta|lead_from_startup_frames' ../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs tools/measure_worklet_live_song_zero_lead_pcm.py` を実行する。先行PCMが0の条件で待つ量子数だけを8と32に変える比較を登録し、開始待ちの飛びと歌唱PCMを検査する。[今回の再現](notes/worklet-live-song-fast-zero-lead-pcm.md#再現)

## 無音の先行枝を8量子と32量子で比較（2026-11-21）

- 完了した項目。先行PCMとグラフを揃え、通知までの量子数を8と32で比較した。両条件の各8試行で開始待ちの飛びは0。先行枝の最初の観測から歌唱開始までの短縮は対応する8組で61.33〜66.67 ms、中央値65.33 msだった。全49,200フレームの歌唱PCMと769点の状態はオフラインと一致した。[事前登録](cases/worklet-live-song-fast-zero-lead-wait.json)・[読解と結果](notes/worklet-live-song-fast-zero-lead-wait.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各146判定・3予測を満たした。先行PCMが全サンプル0で、512量子すべてに128フレームの入力が届いた。絶対フレームを使って別途生PCMを照合し、入力550件と出力184件を検証して20.39 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-zero-lead-wait-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-zero-lead-wait-20261121-repeat/manifest.json)
- 未達の条件。計測用の先行枝での結果で、通常画面側に先行処理を実装したときの操作からの総時間、8量子より短い条件、実機出力は未計測。
- 次に開くファイルと実行するコマンド。`src/render-fixed-voice.ts` の `withRealtimeContext()` と `renderRealtimeSongVoice()`、`tools/shared-context-marker.mjs` の接続順を開く。研究ワークスペースで `rg -n 'withRealtimeContext|renderRealtimeSongVoice|registerFixedWorklet|readyQuanta' ../../../web/prototypes/chimera-research/{src/render-fixed-voice.ts,tools/shared-context-marker.mjs}` を実行する。8量子の無音先行を試験用設定として通常画面の実時間経路に接続する比較条件を登録し、操作からの時間と歌唱PCMを通常の開始経路と照合する。[今回の再現](notes/worklet-live-song-fast-zero-lead-wait.md#再現)

## 歌唱画面の試験設定で8量子の無音先行を検証（2026-11-21）

- 完了した項目。`?songSilentLead=8` で歌唱画面の実時間再生が無音先行を選べる。2回の直接出力で開始待ちの飛びは通常7/8、無音先行0/8。クリックから歌唱先頭の描画までは組内差の中央値 +24 msだった。並列観測を含む全32試行でPCM49,200フレーム、状態769点、計画がオフラインと一致した。[事前登録](cases/worklet-live-song-fast-app-silent-lead.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各282判定・7予測を満たした。並列観測で予約、開始待ちの飛び、歌唱の前後のPCMを独立照合した。入力546件と出力264件のサイズ・SHA-256を確認し、25.59 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-app-silent-lead-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-app-silent-lead-20261121-repeat/manifest.json)
- 未達の条件。他のブラウザ、機器からの音、聴感は未確認。先行枝の準備は32.3〜41.2 msを要し、登録とグラフの稼働開始、通知の寄与は分けていない。
- 次に開くファイルと実行するコマンド。`src/render-fixed-voice.ts` の `registerFixedWorklet()` と `renderRealtimeSongVoice()`、`src/song-silent-lead.ts` の `prepareSongSilentLead()` を開く。研究ワークスペースで `rg -n 'registerFixedWorklet|silent_lead_start|prepareSongSilentLead|addModule' ../../../web/prototypes/chimera-research/src/{render-fixed-voice,song-silent-lead}.ts` を実行する。8量子と接続順を維持したまま2つのWorklet登録を並行させる比較を登録し、クリック時間、開始待ちの飛び、PCMを照合する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead.md#再現)

## 歌唱画面の無音先行で2つのWorklet登録を比較（2026-11-21）

- 完了した項目。`songSilentLeadRegistration=parallel` で2本の登録を重ねられる。全64試行で開始待ちの飛びは0。PCM49,200フレーム、状態769点、歌唱計画はオフライン基準と一致した。直接出力16組の組内差の中央値は登録 −1.0 ms、クリックから描画開始 −4.0 ms。改訂後の直接出力8組のクリックは中央値 +0.5 msだった。[事前登録と改訂](cases/worklet-live-song-fast-app-silent-lead-registration.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead-registration.md)
- 最後に確認した実行。初回方式の再実行は並列観測1試行で最終量子の時刻が重なった。旧判定を保存し、観測中だけ接続を保持した2実行は各322件の取得判定を通過した。標準ライブラリでPCMとマニフェストの入力1,112件・出力528件を照合した。51.22 MBをRTL9210B-CGに保存した。両登録の保留中に停止し、同じ画面で再生し直せた。[初回方式の失敗](runs/worklet-live-song-fast-app-silent-lead-registration-20261121-repeat/manifest.json)・[改訂後](runs/worklet-live-song-fast-app-silent-lead-registration-20261121-b/manifest.json)・[改訂後の再実行](runs/worklet-live-song-fast-app-silent-lead-registration-20261121-repeat-v2/manifest.json)
- 未達の条件。操作からの短縮は反復ごとの組内差の符号が揃わなかった。ブラウザ内の評価が同時に進んだか、切断の何が重複フレームを生んだか、他ブラウザと機器からの出力、聴感は未確認。
- 次に開くファイルと実行するコマンド。`src/song-silent-lead-processor.ts`、`src/song-silent-lead.ts`、`src/worklet-clock.ts` を開く。研究ワークスペースで `rg -n 'SONG_SILENT_LEAD_QUANTA|readyContextFrame|STARTUP_CONTIGUOUS_QUANTA' ../../../web/prototypes/chimera-research/src/{fixed-worklet-types,song-silent-lead,song-silent-lead-processor,worklet-clock}.ts` を実行する。直列登録と歌唱側の予約を揃え、先行枝の8量子と4量子を比較する条件を登録する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead-registration.md#再現)

## 歌唱画面の無音先行で4量子と8量子を比較（2026-11-21）

- 完了した項目。`?songSilentLead=4` で4量子の先行を試せる。歌唱側の開始待ちの飛びは各16試行で0。先行枝の連続区間先頭から歌唱開始までは中央値512フレーム短縮。クリックから歌唱先頭までは直接出力8組で中央値20.5 ms短縮した。全32試行でPCM49,200フレーム、状態769点、計画がオフラインと一致した。[事前登録](cases/worklet-live-song-fast-app-silent-lead-four-quanta.json)・[区間計時と結果](notes/worklet-live-song-fast-app-silent-lead-four-quanta.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各338件の取得判定・7予測を通過。前後の無音とPCMを独立照合し、入力558件と出力264件のサイズ・SHA-256を検証した。大容量成果25.61 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-repeat/manifest.json)
- 未達の条件。先行枝に有効入力が届かない256〜512フレームを27試行で観測した。コールバック自体の欠落と入力条件外の量子は区別していない。Firefox、機器からの波形、聴感は未測定。
- 次に開くファイルと実行するコマンド。`tools/measure_worklet_live_song_cross_browser.py` の `capture()` と `tools/measure_worklet_live_song_app_silent_lead.py` の `measure()` を開く。研究ワークスペースで `rg -n 'def capture|def measure|browser_engine|hold_output_probe_connections' tools/measure_worklet_live_song_{cross_browser,app_silent_lead}.py` を実行する。Firefoxで直列登録の4量子と8量子を比較するケースを登録し、今回と同じPCM・時計に照合する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead-four-quanta.md#再現)

## Firefoxで無音先行を修正し4量子と8量子を比較（2026-11-21）

- 完了した項目。修正前のFirefoxでは先行枝の入力チャンネルが空だった。音源に割り当てる前に0のチャンネルを作ると解消した。修正後のFirefox32試行と同じ修正版のChromium16試行で歌唱の開始待ちの飛びは0。PCM49,200フレーム・状態769点・歌唱計画はオフラインと一致した。Firefoxでは全16組で先行区間から開始まで512フレーム短縮し、クリック時間は直接出力8組で中央値11.5 ms短縮した。[登録条件](cases/worklet-live-song-fast-app-silent-lead-firefox.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead-firefox.md)
- 最後に確認した実行。起動先未設定と未展開バッファでの失敗を保存した。修正後2回のFirefoxとChromium再検証は各338件の取得判定・7予測を通過。Firefoxの4実行とChromium再検証で入力1,425件・出力484件のサイズとSHA-256を検証した。実行時の大容量成果41.85 MBをRTL9210B-CGに保存した。[修正前](runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-b/manifest.json)・[Firefoxの再実行](runs/worklet-live-song-fast-app-silent-lead-firefox-20261121-repeat/manifest.json)・[Chromiumの再検証](runs/worklet-live-song-fast-app-silent-lead-four-quanta-20261121-buffer-init/manifest.json)
- 未達の条件。同じ修正版のChromiumでは16試行中12件で先行枝の有効入力が観測されない256フレームがあった。その区間にコールバックが呼ばれたかは未判定。Safari、機器出力、聴感は未検証。
- 次に開くファイルと実行するコマンド。`src/song-silent-lead-processor.ts` の `process()` と `tools/measure_worklet_live_song_app_silent_lead.py` の `compare_startup()` を開く。研究ワークスペースで `rg -n 'firstValidInputFrame|validInputQuanta|lead_frames_without_valid_input|currentFrame' ../../../web/prototypes/chimera-research/src/song-silent-lead-processor.ts tools/measure_worklet_live_song_app_silent_lead.py` を実行する。Chromiumで先行枝の初期コールバックのフレーム番号と各入力の形状・条件を記録する対照を登録し、欠けたコールバックと入力の欠測を区別する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead-firefox.md#再現)

## Chromiumの無音先行で256フレームの欠測を切り分け（2026-11-21）

- 完了した項目。`songSilentLeadTrace=1` で先行Workletの開始から通知までの入力列を採取した。32試行中23件で最初の呼び出し直後の2量子に記録がなく、取得した215件のコールバックはすべて128フレームの0入力だった。全32試行で歌唱の開始待ちは連続し、PCM49,200フレームと状態769点、計画はオフラインと一致した。[事前登録](cases/worklet-live-song-fast-app-silent-lead-input-trace.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead-input-trace.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各370件の取得判定・9予測を通過した。標準ライブラリでフレームとPCMを独立に照合し、入力564件・出力264件のサイズ・SHA-256を確認した。大容量成果25.64 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-app-silent-lead-input-trace-20261121-repeat/manifest.json)
- 未達の条件。欠けた時刻でChromiumのグラフ時計全体が進んだのか、先行ノードの呼び出しが飛んだのかは未判定。機器出力と聴感は未計測。
- 次に開くファイルと実行するコマンド。`tools/capture-worklet.mjs` の `captureTracedRealtime()` と `captureSong()`、`tools/measure_worklet_wrapper_threshold.py` の `inspect_trace()` を開く。研究ワークスペースで `rg -n 'Tracing.start|captureTracedRealtime|captureSong|inspect_trace|trace_categories' ../../../web/prototypes/chimera-research/tools/capture-worklet.mjs tools/measure_worklet_wrapper_threshold.py` を実行する。先行Workletの最初の呼び出し直後の2量子を対象に、通常画面の再生でChromiumの描画要求とWorkletの計時を同時採取するケースを登録する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead-input-trace.md#再現)

## Chromiumのネイティブトレースで無音先行のフレーム番号を照合（2026-11-21）

- 完了した項目。32試行の215マーカーすべてを作者コード実行・128フレーム描画・描画要求に対応づけた。初回のフレーム番号が飛んだ23件すべてで、前後のコールバックは同じ256フレーム要求に属する隣り合う描画だった。初回の `currentFrame` は登録要求時のContextフレームと一致。全32試行で歌唱側は連続し、PCM49,200フレームと状態769点、計画はオフラインと一致した。[事前登録](cases/worklet-live-song-fast-app-silent-lead-native-trace.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead-native-trace.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各402件の取得判定を通過した。間の2量子でグラフ描画だけが実行されるという予測は0/23で、結果を保存した。入力574件と出力296件のサイズ・SHA-256を照合し、大容量成果30.10 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-app-silent-lead-native-trace-20261121-repeat/manifest.json)
- 未達の条件。初回の時計と登録時の時計は照合済み。Chromium内部で時計を書き換えた行やグラフロック取得を直接は観測していない。機器からの音と聴感は未計測。
- 次に開くファイルと実行するコマンド。`src/render-fixed-voice.ts` の `withRealtimeContext()` と `registerFixedWorklet()`、`tools/worklet_song_native_trace.py` の `inspect_trace()` を開く。研究ワークスペースで `rg -n 'withRealtimeContext|registerFixedWorklet|context.resume|registration_context_frame' ../../../web/prototypes/chimera-research/src/render-fixed-voice.ts tools/worklet_song_native_trace.py` を実行する。Chromiumで最初のWorklet登録をContext再開前に行う対照を登録し、最初の時計の飛び、描画順と歌唱PCMを照合する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead-native-trace.md#再現)

## ChromiumでContextの再開前にWorkletを登録（2026-11-21）

- 完了した項目。`songRegisterBeforeResume=1` で合成Workletを停止中に登録できる。初回フレーム番号の飛びは従来13/16、再開前登録0/16で、先行Workletの141マーカーをネイティブ描画と照合した。クリックから歌唱先頭までは直接出力8組で中央値10 ms短縮。全32試行で歌唱側は連続し、PCM49,200フレームと状態769点、計画はオフラインと一致した。[事前登録](cases/worklet-live-song-fast-app-silent-lead-register-before-resume.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead-register-before-resume.md)
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各434件の取得判定・8予測を通過。登録保留中の停止、登録拒否後の再試行をChromiumで確認した。入力580件・出力296件のサイズとSHA-256を照合し、大容量成果30.11 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-app-silent-lead-register-before-resume-20261121-repeat/manifest.json)
- 未達の条件。再開前登録の条件で先行枝の寄与は未分離。再開前登録でのSafari・Firefoxの操作、機器出力、聴感は未検証。
- 次に開くファイルと実行するコマンド。`src/render-fixed-voice.ts` の `renderRealtimeSongVoice()` と `captureWorklet()`、`tools/measure_worklet_live_song_app_silent_lead.py` の `compare_startup()` を開く。研究ワークスペースで `rg -n 'registerBeforeResume|silentLeadQuanta|registerFixedWorklet|configured_input_quanta_before_voice' ../../../web/prototypes/chimera-research/src/render-fixed-voice.ts tools/measure_worklet_live_song_app_silent_lead.py` を実行する。Chromiumで再開前登録をそろえ、先行枝なしと4量子の無音先行を比較する条件を登録する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead-register-before-resume.md#再現)

## Chromiumで再開前登録をそろえ無音先行の寄与を比較（2026-11-21）

- 完了した項目。歌唱画面で再開前登録を固定し、無音先行なしと4量子を比較した。全32試行で開始待ちの欠落は0、歌唱開始は初回から3,072フレーム後。PCM49,200フレーム、状態769点、歌唱計画はオフライン基準と一致した。直接出力8組では先行なしのクリックから歌唱先頭までが中央値9.5 ms短く、譜面準備からノード生成までは中央値10.95 ms短かった。[事前登録](cases/worklet-live-song-fast-app-silent-lead-preregister-presence.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead-preregister-presence.md)
- 未達の条件。今回の入力は短音1曲とHeadless Chromiumの組み合わせ。Firefox・Safariでの再開前登録、機器出力、聴感は未検証。固定上流PCMとの差は歯フィルタ下限1,200 Hzの基準と同じだった。
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各346件の取得判定と6件の予測を通過した。並列観測16試行の絶対フレーム、前後の無音、歌唱PCMを標準ライブラリでも照合した。各回の入力285件、出力132件のサイズとSHA-256を照合し、大容量成果2回分の25.64 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-app-silent-lead-preregister-presence-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。`src/render-fixed-voice.ts` の `withRealtimeContext()` と `tools/measure_worklet_live_song_app_silent_lead.py` の `compare_resume_registration()`、Firefoxで4・8量子を取得したノートを開く。研究ワークスペースで `rg -n 'registerWhileSuspended|compare_resume_registration|CHIMERA_FIREFOX' ../../../web/prototypes/chimera-research/src/render-fixed-voice.ts tools/measure_worklet_live_song_app_silent_lead.py` を実行する。Firefoxで再開前登録をそろえた先行なしと4量子の対照を登録し、登録時の状態、歌唱の開始待ち、PCMを確認する。[Firefoxでの比較](notes/worklet-live-song-fast-app-silent-lead-firefox.md)・[今回の再現](notes/worklet-live-song-fast-app-silent-lead-preregister-presence.md#再現と保存先)

## Firefoxで停止中のWorklet登録と先行枝の寄与を照合（2026-11-21）

- 完了した項目。Firefox 157.0で無音先行なしと4量子を比較した。全32試行でContext停止中に登録が完了し、開始待ちの欠落は0、歌唱開始は初回から3,072フレーム。PCM49,200フレーム、状態769点、計画はオフライン基準と保存済みChromiumに一致した。先行枝なしの直接出力でクリックから歌唱先頭までは8組で中央値21.5 ms短かった。[事前登録](cases/worklet-live-song-fast-app-silent-lead-preregister-firefox.json)・[読解と結果](notes/worklet-live-song-fast-app-silent-lead-preregister-firefox.md)
- 未達の条件。Safariの再開前登録、機器出力と聴感は未検証。Firefoxでは先行枝の登録区間がChromiumより長かった。登録中のHTTP取得・評価の寄与は未分離。固定上流PCMとの差は歯フィルタ下限1,200 Hzの基準と同じだった。
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各346件の取得判定と6件の予測を通過。固定上流のホストブロック分割と短音の拍位置の試験も各1件通過した。各回の入力285件、出力132件のサイズとSHA-256を照合し、2回分の26.03 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-app-silent-lead-preregister-firefox-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-app-silent-lead-preregister-firefox-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。固定上流の `AudioEngine.build()` と研究版の `withRealtimeContext()`、歌唱の取得スクリプトを開く。研究ワークスペースで `rg -n 'Safari|ctx.resume|registerWhileSuspended|register_before_resume' ../../../docs/reference/chimera-vocal-synth/upstream/src/audio/AudioEngine.ts ../../../web/prototypes/chimera-research/src/render-fixed-voice.ts ../../../web/prototypes/chimera-research/tools/capture-worklet.mjs` を実行する。Safariで先行枝なしの短音1曲を使い、操作時の再開と停止中に登録してからの再開を対照に、登録・再開の完了と歌唱PCMを確認する。[今回の再現](notes/worklet-live-song-fast-app-silent-lead-preregister-firefox.md#再現と保存先)

## macOS SafariでWorklet登録と再開の順序を比較（2026-11-21）

- 完了した項目。Safari 18.6の歌唱画面で全16試行の登録と再開が完了。最初の番号の飛びは再開後登録7/8、停止中登録0/8だった。全試行で連続区間から歌唱開始まで3,072フレーム、PCM49,200フレーム、状態769点と計画はオフライン基準と一致した。直接出力4組では停止中の登録でクリックから歌唱先頭まで中央値25.5 ms短縮した。[事前登録](cases/worklet-live-song-fast-safari-resume-order.json)・[読解・計測と再現](notes/worklet-live-song-fast-safari-resume-order.md)
- 未達の条件。再開後登録で最初のフレーム番号が0となる内部処理、実際の描画呼び出しが飛んだか、iOS Safariでの再開、機器出力と聴感は未検証。並列観測の欠測でAudioWorkletのラッパーが回収されたかは直接観測していない。
- 最後に確認した実行。修正後の初回と `/private/tmp` からの再実行で各166件の取得判定が通過。登録・PCMに関する予測4件を支持し、両順が初回から連続する予測2件は反例を保存した。ページ待ちと並列観測の失敗を含む4実行の入力・出力をハッシュ照合し、大容量成果19.93 MBをRTL9210B-CGに保存した。[失敗1](runs/worklet-live-song-fast-safari-resume-order-20261121-a/manifest.json)・[失敗2](runs/worklet-live-song-fast-safari-resume-order-20261121-b/manifest.json)・[修正後](runs/worklet-live-song-fast-safari-resume-order-20261121-c/manifest.json)・[再実行](runs/worklet-live-song-fast-safari-resume-order-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。`render-fixed-voice.ts` の `registerFixedWorklet()` と `captureWorklet()`、Safariの取得と並列観測のコードを開く。研究ワークスペースで `rg -n 'registerFixedWorklet|node_start|add_module_complete|currentFrame' ../../../web/prototypes/chimera-research/{src/render-fixed-voice.ts,tools/capture-safari-song.mjs,tools/song-output-probe-worklet.js}` を実行する。再開後登録のSafariで、登録完了からノード生成までにContextの時計を進める対照を登録し、最初の2量子のフレーム番号とPCMを照合する。

## Safariで登録完了からノード生成までのContextフレームを比較（2026-11-21）

- 完了した項目。再開後登録を固定した16試行で、登録完了と生成が同じContextフレームだった7試行は最初0から次に1,664〜1,920へ進んだ。実測で128フレーム以上進んだ9試行は連続した。並列観測8試行でも最初の2値が一致した。PCM49,200フレームと状態769点、計画は全試行でオフラインと一致。公開WebKitの修正前の初期値0と描画後の更新が計測結果と整合することを記録した。[事前登録](cases/worklet-live-song-fast-safari-node-after-registration.json)・[読解・計測と再現](notes/worklet-live-song-fast-safari-node-after-registration.md)・[WebKitの修正](https://github.com/WebKit/WebKit/commit/a0b5d79d7218)
- 未達の条件。Safariのネイティブ描画の全呼び出し数、修正を含むWebKitでの比較、iOSと機器出力・聴感は未検証。待機の実測は10〜27 msで、クリックからの時間差は試行ごとにばらついた。
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各186件の取得判定に合格した。先頭から両条件が連続するという予測は2件で反例を保存し、待機による連続化・通常の飛びの再現・PCM一致の予測6件を支持した。各回の入力274件・出力76件をサイズとSHA-256で照合し、大容量成果12.45 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-safari-node-after-registration-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-safari-node-after-registration-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。Safariの取得スクリプトと公開WebKitの作成時刻の回帰テストを開く。研究ワークスペースで `rg -n 'registration_hold_start|suspend_request|startupSecondContextFrame|currentFrame' ../../../web/prototypes/chimera-research/{tools/capture-safari-song.mjs,src/realtime-speech-capture.ts,src/fixed-processor.ts}` と `/usr/bin/safaridriver --version` を実行する。短いオシレーターで先に進めたContextを停止し、Workletの評価・ノード構築・再開直後でそれぞれ番号を取る対照を設計する。[公開の回帰テスト](https://github.com/WebKit/WebKit/blob/a0b5d79d7218/LayoutTests/imported/w3c/web-platform-tests/webaudio/the-audio-api/the-audioworklet-interface/audioworkletglobalscope-creation-time.https.html)

## Safariの停止中のWorklet作成位置と再開後のサンプルを照合（2026-11-21）

- 完了した項目。Safari 18.6で停止前にContextを4,096または4,224フレーム進めた8試行は、モジュール評価・コンストラクター・最初の `process()` までは0を報告し、次から `P+128` 以降にそろった。未描画の対照8試行は0から128刻み。再開後4量子の全8,192入力サンプルを独立した連番PCMと照合し、全点ビット一致を確認した。[事前登録](cases/worklet-safari-clock-at-creation.json)・[読解・実測・再現](notes/worklet-safari-clock-at-creation.md)
- 未達の条件。Safari内部の更新位置は公開コードとの照合。修正を含むビルド、iOS、歌唱時の機器出力と聴感は未検証。番号の飛びと入力PCMの連続性を分離できた範囲は、この再開直後の4量子。
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各取得64件を通過した。公開回帰テストに相当する作成位置の一致は先に進めた条件で反例を保存した。各回の入力10件・出力11件を照合し、成果219,847バイトをRTL9210B-CGに保存した。WebDriverを共通化した歌唱画面の並列観測も、448量子とWAV一致を再確認した。[初回](runs/worklet-safari-clock-at-creation-20261121-a/manifest.json)・[再実行](runs/worklet-safari-clock-at-creation-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。歌唱の `WorkletStartup.ready()` と `RealtimeSpeechCapture.ready()`、Safariの歌唱採取スクリプトを開く。研究ワークスペースで `rg -n 'STARTUP_CONTIGUOUS_QUANTA|armedContextFrame|registerBeforeResume|installStartupObservation' ../../../web/prototypes/chimera-research/{src/worklet-clock.ts,src/realtime-speech-capture.ts,src/render-fixed-voice.ts,tools/capture-safari-song.mjs}` を実行する。先に進めて停止したContextからの歌唱を1曲で再現し、初回ラベルの飛び、再同期、実際の歌唱位置とグラフPCMの対応を照合する。

## Safariで停止中に登録した歌唱Workletの再同期を照合（2026-11-21）

- 完了した項目。Safari 18.6の通常歌唱で、先にContextを4,096〜5,120フレーム進めて停止した。接続後再開の8試行は番号0から `P+128` へ進みコールバック9回で再同期し、生成前再開の8試行は `P+128` から連続して8回で予約した。全16試行の予約は停止位置 `P+3,200`、PCM49,200フレーム、状態769点、計画はオフラインと一致した。並列観測8件の予約位置から独立に生PCMを照合した。[事前登録](cases/worklet-live-song-fast-safari-paused-registration.json)・[読解・実測・再現](notes/worklet-live-song-fast-safari-paused-registration.md)
- 未達の条件。歌唱を始めてから停止・再開した場合の状態継続、機器出力、聴感は未検証。クリックから歌唱先頭までの差は組ごとに変動した。
- 最後に確認した実行。初回と `/private/tmp` からの再実行は各取得判定178件が通過。予測8件を支持し、両条件が初回番号から連続するという判定2件には反例を保存した。固定上流のブロック長・短音のテストは各1件通過した。入力275件・出力76件を各回でハッシュ照合し、大容量成果12.48 MBをRTL9210B-CGに保存した。[初回](runs/worklet-live-song-fast-safari-paused-registration-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-safari-paused-registration-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。`FixedProcessor.process()`、`RealtimeSpeechCapture.record()` と並列出力採取を開く。研究ワークスペースで `rg -n 'process\(|record\(|elapsedWallMs|currentFrame|captureQuanta' ../../../web/prototypes/chimera-research/{src/fixed-processor.ts,src/realtime-speech-capture.ts,tools/song-output-probe-worklet.js}` を実行する。同じ短い歌唱で、すでに描画しているContextを一度停止・再開する条件と連続再生を比較し、停止前後の絶対フレーム、PCMと観測状態を照合する。

## Safariで歌唱途中の停止・再開を照合（2026-11-21）

- 完了した項目。歌唱途中に停止した8試行でContextの番号が停止中に固定され、コールバックの間隔は136〜149 ms、フレーム番号の差は128だった。連続条件の同じ出力位置の間隔は2〜3 ms。停止位置を挟むPCMと状態値を含め、全16試行のPCM49,200フレームと観測769点、歌唱計画がオフラインと一致した。[事前登録](cases/worklet-live-song-fast-safari-mid-song-pause.json)・[実測と再現](notes/worklet-live-song-fast-safari-mid-song-pause.md)
- 未達の条件。停止・再開を歌唱録画に適用した場合の音声・映像の時刻、機器出力と聴感は未検証。今回の比較はSafari 18.6、48 kHz、短音「Pop Dee」のWeb Audioグラフ内。
- 最後に確認した実行。初回と `/private/tmp` からの再実行で各取得判定182件が通過した。途中の停止と状態・PCMの予測8件を支持し、歌唱開始前のフレーム番号の連続性に関する2件には反例を保管した。各回の入力275件と出力76件のハッシュを照合し、成果12.47 MBをRTL9210B-CGに保存した。上流の2試験と既存のSafari停止中登録の回帰比較も通過した。[初回](runs/worklet-live-song-fast-safari-mid-song-pause-20261121-a/manifest.json)・[再実行](runs/worklet-live-song-fast-safari-mid-song-pause-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究版の `SongRecording` と固定上流の `Clip`、`cases/worklet-song-recording.json` を開く。研究ワークスペースで `rg -n 'MediaRecorder|currentTime|elapsed|schedule\(|finish\(' ../../../web/prototypes/chimera-research/src/song-recording.ts ../../../docs/reference/chimera-vocal-synth/upstream/src/song/record.ts` を実行する。通常録画の入出力を確認し、歌唱中の停止・再開を入れた場合の符号化後PCMと映像PTSを照合するケースを登録する。

## Safariで歌唱録画中の停止とメディア時刻を照合（2026-11-21）

- 完了した項目。通常の録画操作から連続・停止の各4試行を取得。加工前PCM49,200フレーム、状態769点と計画は全試行でオフラインと一致した。Contextを120〜121 ms保持しても、復号したAAC音声66,560サンプルと音声PTSは全試行で一致した。映像の停止位置付近の4〜5枚は5.0〜8.3 msに収まり、音声・映像とも壁時計の停止時間を保つ予測は支持されなかった。[事前登録](cases/worklet-live-song-fast-safari-recording-pause.json)・[読解と実測](notes/worklet-live-song-fast-safari-recording-pause.md)
- 未達の条件。映像に短い同位置フレームが生じる内部の経路、固定上流での停止付き録画、他ブラウザでの同条件、機器出力と聴感は未検証。固定上流PCMとの差は歯フィルタ下限1,200 Hzの基準と同じだった。
- 最後に確認した実行。修正後の2実行は各70件の取得判定を通過した。相関が1を越えた変更前の2実行も保存した。4実行で各277件の入力と52件の出力をハッシュ照合し、計21,469,281バイトをRTL9210B-CGに保存した。固定上流の2試験、通常録画の保存済み2音声の整列、非録画の並列観測付き停止1試行も通過した。[変更前の初回](runs/worklet-live-song-fast-safari-recording-pause-20261121-a/manifest.json)・[変更前の再実行](runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat/manifest.json)・[修正後](runs/worklet-live-song-fast-safari-recording-pause-20261121-b/manifest.json)・[修正後の再実行](runs/worklet-live-song-fast-safari-recording-pause-20261121-repeat-b/manifest.json)
- 次に開くファイルと実行するコマンド。研究版の `SongRecording` とSafariの採取スクリプトを開く。研究ワークスペースで `rg -n 'MediaRecorder|captureStream|currentTime|suspend\(|resume\(' ../../../web/prototypes/chimera-research/{src/song-recording.ts,tools/capture-safari-song.mjs}` を実行する。短い目印付きの信号でContextだけを停止する条件と `MediaRecorder.pause()` だけを使う条件を事前登録し、壁時計とContext時計で描いた目印のPTSを照合する。

## SafariでAudioContextの停止とMediaRecorderの一時停止を照合（2026-11-21）

- 完了した項目。連続、AudioContextだけ停止、録画だけ一時停止の各6試行を比較。Contextだけ停止では固定された音声時計と進む壁時計を持つ映像5〜6枚が6.7〜8.3 msのPTS幅で残り、録画音声の窓間オフセットは変わらなかった。録画だけ一時停止では停止中の映像が0枚で、元信号が192.0〜197.3 ms欠けた。全試行でAACフレームのPTSは連続した。[ケース](cases/safari-recording-pause-clock-split.json)・[読解と実測](notes/safari-recording-pause-clock-split.md)
- 未達の条件。計測はSafari 18.6のH.264/AACと短いチャープ。映像だけの録画、固定上流のSafariでの停止付き録画、別ブラウザ、機器出力は未検証。録画だけを止めた場合に、停止中のContext時間より欠けた元信号が45.3〜48.0 ms短い理由も残る。追加取得時はWebDriverのタイムアウトと、接続済みセッションの応答が再発した。[追加取得の記録](runs/safari-recording-pause-clock-split-20261121-c/summary.json)・[最後のSafari取得](runs/safari-recording-pause-clock-split-20261121-d/summary.json)
- 最後に確認した実行。修正後の取得2回は各72件と予測30件が通過。最新解析器での再解析は9試行・72件が通過し、元の結果とバイト一致。固定上流の2件も通過した。失敗・再解析を含む6実行の23,662,530バイトをRTL9210B-CGに保存し、全マニフェストの入力と出力をハッシュ照合した。[取得](runs/safari-recording-pause-clock-split-20261121-b/manifest.json)・[再取得](runs/safari-recording-pause-clock-split-20261121-repeat-b/manifest.json)・[再解析](runs/safari-recording-pause-clock-split-20261121-reanalysis/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'captureStream|new MediaStream|appendVideoFrame' ../../../web/prototypes/chimera-research/tools/capture-safari-recording-clock-split.mjs notes/safari-recording-pause-clock-split.md` と `/usr/bin/safaridriver --version` を実行する。短い動画の音声トラックの有無のみを変える条件を登録し、同じContext停止前後の壁時計マーカーと動画PTSを比較する。取得できた動画は `tools/measure_safari_recording_pause_clock_split.py <実行ID> --from-run safari-recording-pause-clock-split-20261121-repeat-b` で再解析できる。

## Safariで録画トラックの構成と映像PTSを照合（2026-11-21）

- 完了した項目。8試行で同じ48 kHzチャープと240 ms前後のContext停止を使い、録画に音声を加えるかだけを変更した。停止中の5〜6枚は、音声付きで6.7〜8.3 ms、映像のみで131.7〜166.7 msのPTS幅になった。映像のみのPTS幅と同じ2枚の壁時計幅との差は最大1.34 ms。音声付きの録画では停止前後で音声サンプルのオフセット変化は0だった。[事前登録](cases/safari-recording-video-clock.json)・[読解・実測](notes/safari-recording-video-clock.md)
- 未達の条件。固定上流のSafariに通常の歌唱録画中の停止を入れた比較、他ブラウザ、機器出力は未検証。公開WebKitの時計選択は観測と整合した。インストール済みのSafariと公開コードの厳密なリビジョンの対応は未確認。
- 最後に確認した実行。研究ワークスペースと `/private/tmp` からの2回で各42件の取得判定と8件の予測が通過した。欠測なし。各12件の入力・25件の出力をハッシュ照合し、比較2実行の4,262,758バイトをRTL9210B-CGへ保存した。共通解析の変更後に前回の9録画を再解析し、要約は保存済みとバイト一致。固定上流の2件も通過した。[初回](runs/safari-recording-video-clock-20261121-a/manifest.json)・[再実行](runs/safari-recording-video-clock-20261121-repeat/manifest.json)・[回帰確認](runs/safari-recording-pause-clock-split-20261121-video-clock-regression/manifest.json)
- 次に開くファイルと実行するコマンド。固定上流の `SingPanel`、`playTune()`、`AudioEngine.recordStream()` と `Clip` を開く。研究ワークスペースで `rg -n 'onStart|onEnd|recordStream|class Clip|function playTune' ../../../docs/reference/chimera-vocal-synth/upstream/src/{ui/components/SingPanel.tsx,ui/singing.ts,audio/AudioEngine.ts,song/record.ts}` を実行する。固定上流の通常の録画操作で短い歌唱の120 ms停止を事前登録し、研究版の通常録画と合成PCM、録画の音声PTS、映像PTSを照合する。

## 固定上流の通常歌唱録画にSafariで停止を入れて照合（2026-11-21）

- 完了した項目。固定上流の通常の「Record video」から、同じ2音の譜面で連続・停止を各4試行取得した。停止した4試行は120〜122 ms保持し、描画の絶対フレームは前後で128刻みだった。録画音声は研究版と同様に前後のオフセット変化が0サンプル、停止中の3枚は各3.33 msの映像PTS幅で残った。[事前登録](cases/upstream-safari-song-recording-pause.json)・[読解と実測](notes/upstream-safari-song-recording-pause.md)
- 未達の条件。上流内で加工前PCMが異なる組の差は停止前から始まった。同じエンジンフレームで譜面を受けた4試行は停止の有無を含めてビット一致したが、最初に分かれる内部状態は未確定。今回の比較は通常歌唱での録画時刻で、上流と研究版の合成設定や映像マーカーには差がある。他ブラウザと機器出力は未測定。[前奏とPCM](notes/upstream-safari-song-recording-pause.md#加工前pcmに現れた差)
- 最後に確認した実行。後半の測定窓までPCMを取得した2実行は各36件の取得と6件の予測を通過。末尾の25 msが足りなかった最初の2実行も保存し、計4実行の各18入力・27出力をハッシュ照合した。固定上流のWASM再ビルド、2件の上流試験、前回録画の再解析を通過した。固定上流の大容量出力9,631,129バイトをRTL9210B-CGに保存した。[修正後](runs/upstream-safari-song-recording-pause-20261121-b/manifest.json)・[再実行](runs/upstream-safari-song-recording-pause-20261121-repeat-b/manifest.json)・[共通解析の回帰](runs/safari-recording-pause-clock-split-20261121-upstream-regression/manifest.json)
- 次に開くファイルと実行するコマンド。固定上流の `ChimeraProcessor.handle()`、`Engine::schedule()`、`AudioEngine.quiet()` とPCM採取スクリプトを開く。研究ワークスペースで `rg -n 'engine_schedule|engine_clock|research-armed|quiet\(' ../../../docs/reference/chimera-vocal-synth/upstream/src/{worklet/processor.ts,audio/AudioEngine.ts} ../../../web/prototypes/chimera-research/tools/capture-upstream-safari-recording-pause.mjs` を実行する。譜面を同じエンジンフレームに受け渡す対照を登録し、連続描画と途中停止のPCMと状態の進行を照合する。

## 固定上流で譜面の予約フレームをそろえて停止前後のPCMと状態を照合（2026-11-21）

- 完了した項目。通常の「Record video」で譜面の予約をエンジン16,384または16,512フレームに固定し、8試行取得した。同じ予約フレームで、連続・停止を合わせた4試行ずつの各29,760サンプルはビット一致。状態は40または41点が一致した。予約だけを128フレーム遅らせると、停止前の14,330サンプル目でPCM差が0.000001を超えた。[事前登録](cases/upstream-safari-song-fixed-schedule-frame.json)・[読解と実測](notes/upstream-safari-song-fixed-schedule-frame.md)
- 未達の条件。予約フレームをずらしたときの、譜面に相対的な最初の内部状態差は未特定。絶対エンジンフレームをそろえた状態通知では29,184フレームで調音・声門流量などに最初の差が見えた。各6量子の通知より細かい比較、別ブラウザ、機器出力は未測定。
- 最後に確認した実行。初回と別ディレクトリからの再実行で各48件の取得判定と11件の予測を通過した。固定上流の2試験と、予約位置を固定しない通常録画の4試行も通過した。比較2回は各入力21件・出力28件をハッシュ照合し、RTL9210B-CGへ14,600,099バイトを保存した。[初回](runs/upstream-safari-song-fixed-schedule-frame-20261121-a/manifest.json)・[再実行](runs/upstream-safari-song-fixed-schedule-frame-20261121-repeat/manifest.json)・[通常録画の回帰](runs/upstream-safari-song-recording-pause-20261121-fixed-schedule-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'schedule|noise|glottis|render' tools/{upstream_song_probe.rs,upstream_live_song_probe.rs,measure_song_constriction_source.py}` を実行する。同じ短い譜面で予約前の描画量だけを128フレームずらし、譜面に相対的なサンプル位置で声門面積・流量、乱流、放射を照合するケースを登録する。

## 歌唱予約を128フレームずらしたときの声門と乱流を照合（2026-11-21）

- 完了した項目。固定上流のネイティブ描画に前回のSafariと同じ譜面・予約位置を通し、両位置で29,760サンプルがビット一致した。予約直前から声門位相は0.293762周期異なった。通常の乱流条件で最初に差が出力へ届く前に、14,256サンプルで声門の乱流源が前方の咽頭枝13へ逆符号の圧力を加えた。PCM差の閾値超過は通常14,330、乱流注入量0では20,903サンプルだった。[事前登録](cases/upstream-song-schedule-state.json)・[読解・実測と再現](notes/upstream-song-schedule-state.md)
- 未達の条件。乱流波形の差に対する乱数の消費順とフィルタ履歴の寄与は未分離。48 kHzの観測では内部96 kHzの2ステップのどちらから差が伝わったかを判定していない。研究版で同じ予約前の描画量をそろえた比較が残る。
- 最後に確認した実行。接続情報を追加した2回は各20件の取得判定と4件の予測を通過した。追加前も含む4回でPCMと計測CSVはバイト一致。各20件の入力・15件の出力をハッシュ照合し、RTL9210B-CGへ122,944,884バイトを保存した。固定上流の2試験も通過した。[初回](runs/upstream-song-schedule-state-20261121-b/manifest.json)・[再実行](runs/upstream-song-schedule-state-20261121-repeat-b/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'schedule|render|noise|glottis' crates/vocal-cli/src/{live_song_case.rs,timing_case/speech_voice.rs} crates/vocal-core/src/airway/{human/frication.rs,network/turbulence.rs} tools/measure_song_constriction_source.py` を実行する。研究版の通常の歌唱描画で予約前のサンプル数だけを変えるケースを作り、最初の乱流注入・放射・PCM差を今回の固定上流に照合する。

## 研究版で歌唱予約前の描画量を変えて固定上流と照合（2026-11-21）

- 完了した項目。通常の歌唱CLIで予約前の描画を16,384または16,512フレーム進め、状態を保持したまま短い譜面を予約できるようにした。音素境界は固定上流と整数サンプルで一致。通常乱流の最初の枝圧差は14,256サンプルの咽頭枝13、PCM差の最初の閾値超過は14,330サンプルで、いずれも固定上流と一致した。[事前登録](cases/song-voice-schedule-state.json)・[読解と実測](notes/song-voice-schedule-state.md)
- 未達の条件。乱流注入量0では声門面積・放射の分岐は両版とも20,878サンプルで、PCM差の閾値超過は上流20,903、研究版20,908サンプルだった。同じ予約位置で比べても有声化後のPCMに最大約0.47〜0.48の差がある。予約時の声門位相に差があり、既定のピッチドリフトや周期揺らぎの寄与は未分離。
- 最後に確認した実行。初回と別ディレクトリからの再実行は各16件の取得判定と5件の予測を通過。各123入力・30出力をハッシュ照合し、RTL9210B-CGに計215,132,778バイトを保存した。予備描画を指定しない短音で、声門乱流18件と狭窄乱流16件の回帰判定も通過した。[初回](runs/song-voice-schedule-state-20261121-a/manifest.json)・[再実行](runs/song-voice-schedule-state-20261121-repeat/manifest.json)・[声門の回帰](runs/song-voice-fast-glottis-source-20261121-warm-up-regression/manifest.json)・[狭窄の回帰](runs/song-voice-fast-constriction-source-20261121-warm-up-regression/manifest.json)
- 次に開くファイルと実行するコマンド。`research/experiments/chimera-rebuild/` で `rg -n 'drift|jitter|shimmer|set_source' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs crates/vocal-core/src/voice.rs tools/upstream_song_schedule_state_probe.rs` を実行する。固定上流のピッチドリフトだけを0にする条件を別ケースに登録し、同じ2つの予備描画長で予約時の位相、声門流量、有声化後のPCMを測る。

## 歌唱予約前からのピッチドリフトを0・5セントで比較（2026-11-21）

- 完了した項目。通常の歌唱CLIに `pitch_drift_cents` を追加し、固定上流と同じ初期F0・予約前描画長でドリフト係数0・5セントを照合した。予約直後のF0比は三帯域IIRの独立計算と一致。係数を両版でそろえると、選んだ有声区間のRMS誤差が57〜59%減った。同じ実装内でドリフト係数を変えたときの最初の声門面積・放射の差は20,878サンプルだった。[事前登録](cases/song-voice-schedule-drift.json)・[読解と実測](notes/song-voice-schedule-drift.md)
- 未達の条件。0セントでも、上流に残る周期ジッターで予約時に約0.042周期の絶対位相差が残った。位相差は周期倍率の独立計算で説明できた。シマーと発声後の気道・出力の寄与は未分離。前回の乱流注入量0での予約2位置間のPCM閾値超過は、ドリフト量をそろえても両版で1〜2サンプルの差が残る。
- 最後に確認した実行。比較2回は各53判定に合格し、160入力・43出力の各ハッシュと、29件のPCM・CSV・要約のバイト一致を確認した。設定省略時は16判定と5予測に合格し、従来のPCM・CSV・要約21件と一致した。固定上流と研究版のテストは各15件通過。比較2回の実体276,598,178バイトをRTL9210B-CGに保存した。[初回](runs/song-voice-schedule-drift-20261121-a/manifest.json)・[再実行](runs/song-voice-schedule-drift-20261121-repeat/manifest.json)・[回帰](runs/song-voice-schedule-state-20261121-drift-regression/manifest.json)
- 次に開くファイルと実行するコマンド。`research/experiments/chimera-rebuild/` で `rg -n 'jitter|cycle_period_scale|cycle_factors' crates/vocal-core/src/{glottis,voice}.rs tools/measure_glottal_cycle.py ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/{sources/glottis,voice/human_voice}.rs` を実行する。ピッチドリフト0のまま研究版で周期ジッターのみ0.00455にしたケースを登録し、予約時の位相と有声区間のPCMを今回の固定上流に照合する。

## 周期ジッターをそろえた歌唱の位相とPCMを照合（2026-11-21〜22）

- 完了した項目。通常の歌唱CLIに `period_jitter` を追加した。ドリフト0の固定上流に研究版のジッター0.00455をそろえ、予約後の位相とF0が全4条件で各31,200点ビット一致することと、独立位相積分との一致を確かめた。有声区間のPCM誤差RMSは83.7〜87.4%減った。乱流注入量0で予備描画128フレーム差がPCMに届く位置も、両版で20,910サンプルに一致した。[事前登録](cases/song-voice-schedule-jitter.json)・[読解と実測](notes/song-voice-schedule-jitter.md)
- 未達の条件。同じ位相でも有声化時の声門上下圧・面積・流量・放射とPCMには差が残る。シマーの寄与は未分離。口端面積には最小断面と有効断面の列の違いがあり、保存済みの対応列で読み直すと最大差5.7×10⁻¹⁴ cm²だった。[残差と観測列](notes/song-voice-schedule-jitter.md#口端面積の照合位置)
- 最後に確認した実行。初回と別ディレクトリからの再実行は各42判定（予測14件を含む）に合格。各156入力・30出力をハッシュ照合し、21件のPCM・CSV・要約と抜粋前の8件の出力段CSVは両回で一致した。RTL9210B-CGに実体計185,151,372バイトを保存した。既存のテストは両版で各15件通過。設定省略と明示的な0の回帰も以前の出力と一致した。[初回](runs/song-voice-schedule-jitter-20261121-a/manifest.json)・[再実行](runs/song-voice-schedule-jitter-20261121-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。`research/experiments/chimera-rebuild/` で `rg -n 'shimmer|cycle_amplitude_scale|cycle_factors|lip_minimum_cm2' crates/vocal-core/src/{glottis,voice}.rs tools/{measure_glottal_cycle,measure_song_schedule_drift}.py ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/{sources/glottis,voice/human_voice}.rs` を実行する。研究版でドリフト0とジッター0.00455を固定し、シマーのみ0.042にした対照を登録。声門面積からPCMまでの差を追い、口端は最小断面どうしを比較する。

## 振幅シマーをそろえた短い歌唱を照合（2026-11-22）

- 完了した項目。研究版の通常の歌唱CLIに `amplitude_shimmer` を加えた。ドリフト0・ジッター0.00455・シマー0.042で、振幅倍率が独立計算と全点一致。口端最小断面は両版の対応列で照合した。固定上流との最大差は声門面積1.18×10⁻¹⁵ cm²、PCM1.46×10⁻¹¹。有声窓のPCMは4条件とも全600サンプルが一致した。[事前登録](cases/song-voice-schedule-shimmer.json)・[実測と読解](notes/song-voice-schedule-shimmer.md)
- 未達の条件。全PCMのビット差は条件ごとに5〜11点で、最初の差は全4条件で11,692サンプル。放射差分は11,104サンプルで約4.7×10⁻¹² cm³/s²の差が見えた。96 kHzでの最初の演算差は未特定。既定のドリフト5セントを含む条件とSafariの出力には今回の研究版の設定をまだ通していない。
- 最後に確認した実行。初回と別ディレクトリからの再実行は各34判定（予測14件を含む）に合格し、各157入力・30出力をハッシュとサイズで照合した。PCM、CSV、要約21件と抜粋前のCSVハッシュ8件が一致した。RTL9210B-CGに歌唱比較2回で189,854,466バイトを保存。固定圧のシマー回帰8判定、上流テスト15件、研究版テスト41件、WASMターゲットのコンパイル確認も通過した。[初回](runs/song-voice-schedule-shimmer-20261122-a/manifest.json)・[再実行](runs/song-voice-schedule-shimmer-20261122-repeat/manifest.json)・[固定圧の回帰](runs/glottal-cycle-shimmer-20261122-song-regression/manifest.json)
- 次に開くファイルと実行するコマンド。`research/experiments/chimera-rebuild/` で `rg -n 'worklet.f32le|appliedFrame|drift|amplitude_shimmer' tools/measure_{upstream_song_schedule_state,song_schedule_shimmer}.py cases/{upstream-song-schedule-state,song-voice-schedule-drift}.json` を実行する。通常の上流音源と同じドリフト5・ジッター0.00455・シマー0.042のCLI条件を登録し、固定上流ネイティブと、予約フレームをそろえたSafariの加工前PCMに照合する。

## 上流既定の短い歌唱をSafariとCLIで照合（2026-11-22）

- 完了した項目。通常の歌唱CLIにドリフト5・ジッター0.00455・シマー0.042を指定し、固定上流のネイティブ4条件と、Safari 18.6の保存済み連続・停止試行を照合した。位相・F0はネイティブ同士で全31,200点がビット一致。SafariとCLIのPCMの最大差は7.28×10⁻¹²。予約だけを128フレームずらすと通常乱流は3経路で14,330、乱流注入量0は両ネイティブで20,903サンプルで閾値を超えた。[事前登録](cases/song-voice-schedule-default-source.json)・[読解と実測](notes/song-voice-schedule-default-source.md)
- 未達の条件。固定上流とCLIには条件ごとに4〜9点のPCMビット差があり、最初の差は11,692サンプル。放射差分には11,104サンプルで差が見えた。96 kHzの内部で最初に分かれる演算は未特定。研究版のブラウザ歌唱経路での同じ音源設定と、予約前の状態の保持は未照合。
- 最後に確認した実行。別ディレクトリからの再実行を含めて各33判定（予測19件を含む）が通過。各165入力・30出力をハッシュとサイズで照合し、21件のPCM・CSV・要約と、抜粋前のCSV8件のハッシュが一致した。実体計192,429,130バイトをRTL9210B-CGに保存した。上流の既存試験は12件通過した。[初回](runs/song-voice-schedule-default-source-20261122-a/manifest.json)・[再実行](runs/song-voice-schedule-default-source-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。`research/experiments/chimera-rebuild/` で `rg -n 'vocal_start_score_with_turbulence|vocal_score_buffer|renderRealtimeSongVoice|set_base_pitch' crates/vocal-wasm/src/lib.rs ../../../web/prototypes/chimera-research/src/render-fixed-voice.ts` を実行する。研究版の既存WASM歌唱入口で同じ3つの音源設定を指定し、予備描画の状態を引き継いで予約したときの加工前PCMと声門状態を今回のCLIに照合する。

## 研究版のWASM歌唱で予約前の状態を引き継ぐ（2026-11-22）

- 完了した項目。既存のオフライン・実時間の歌唱画面に「上流音源の比較」プリセットを加えた。設定したドリフト・ジッター・シマーを予備描画から有効にし、同じ声門と気道と出力段の状態を保って譜面を予約した。Chromiumの8試行で各31,200点のPCMはCLIとビット一致し、各488点の位相・流量など11系列も一致。画面から保存したケースのCLI再生も照合した。[事前登録](cases/worklet-song-prepared-source.json)・[読解と実測](notes/worklet-song-prepared-source.md)
- 未達の条件。研究版のブラウザと固定上流のPCMには最大2.91×10⁻¹¹の差があり、同じ予約位置で最初のビット差が11,692サンプルに見えた。今回の研究版のブラウザ検証はChromium。Safariの予約前描画を含む構築時間と途中停止の照合、機器出力の照合が残る。
- 最後に確認した実行。初回と別ディレクトリからの再実行が各48判定を通過し、各280入力・45出力をハッシュ照合した。WASM・PCM・CSV・再実行ケース・要約26件が一致し、比較2回の実体計25,915,668バイトをRTL9210B-CGに保存した。従来短音の回帰15判定、WASMの既存26テスト、固定上流のブロック長の試験も通過。[初回](runs/worklet-song-prepared-source-20261122-a/manifest.json)・[再実行](runs/worklet-song-prepared-source-20261122-repeat/manifest.json)・[短音の回帰](runs/worklet-song-voice-fast-20261122-prepared-regression/manifest.json)
- 次に開くファイルと実行するコマンド。`research/experiments/chimera-rebuild/` で `rg -n '歌唱プリセット|songRegisterBeforeResume|suspend\(|sourcePreparation' ../../../web/prototypes/chimera-research/{tools/capture-safari-song.mjs,src/render-fixed-voice.ts} crates/vocal-wasm/host/fixed-voice.ts` を実行する。今回保存したCLIとChromiumのケースを基準に、研究版Safariで同じプリセットの実時間歌唱を予約し、構築時間とContextの停止前後のPCMを照合する条件を登録する。

## 研究版Safariで予備描画の構築時間と途中停止を照合（2026-11-22）

- 完了した項目。「上流音源の比較」プリセットをSafariの通常歌唱から実行し、Worklet内の合成器構築時間を計測した。直接出力では予備描画0が3〜4 ms、16,384・16,512フレームが135〜142 ms。修正後の全16試行のPCMは各31,200サンプルが基準とビット一致した。停止6試行でContext時計が停止完了から再開まで一定で、描画は `P−128` と `P` で連続した。並列観測の4試行でも同じ絶対フレームからPCMが取れた。[事前登録](cases/worklet-safari-song-prepared-pause.json)・[読解と実測](notes/worklet-safari-song-prepared-pause.md)
- 未達の条件。Worklet内の構築時間にはWASMインスタンスと合成器の準備も含む。予備描画中に同じContextでほかの音源を先行させたときの描画間隔、機器出力のサンプル欠落、構築の分割は未測定。
- 最後に確認した実行。初回はオフライン観測の列名の読出しを誤り、6試行の判定が止まった。修正後に初回の保存データを再照合し、次の2実行は各63判定に合格した。各271入力・74出力をサイズとハッシュで確認し、18件のPCM・ケース・WASMが両実行で一致。合格分の8,626,556バイトをRTL9210B-CGに保存した。従来の短音プリセットのSafariのPCMも基準と一致した。[初回の判定](runs/worklet-safari-song-prepared-pause-20261122-a/manifest.json)・[修正後](runs/worklet-safari-song-prepared-pause-20261122-b/manifest.json)・[反転順の実行](runs/worklet-safari-song-prepared-pause-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。`research/experiments/chimera-rebuild/` で `rg -n 'scoreConstruction|shared_context_marker|songOutputProbe|startFrame' ../../../web/prototypes/chimera-research/{src/fixed-processor.ts,tools/shared-context-marker.mjs,tools/song-output-probe.mjs} tools/measure_worklet_safari_song_prepared_pause.py` を実行する。同じSafari Contextに先行信号を入れ、予備描画0と16,384の構築前後を連続録音し、先行音のフレーム間隔とPCMと歌唱予約を照合する。

## Safariで歌唱構築中の先行信号を照合（2026-11-22）

- 完了した項目。同じAudioContextで既知の信号を先に流し、「上流音源の比較」プリセットで予備描画0と16,384フレームを比較した。先行信号の構築に重なる最大コールバック間隔は4〜6 msから134〜159 msに広がり、8ペアの増加の中央値は132.5 msだった。全16試行で最大間隔前後のContextフレームが128刻みで続き、先行PCM各51,200サンプル、歌唱PCM各31,200サンプル、各488観測点が基準と一致した。[事前登録](cases/worklet-safari-song-prepared-shared-context.json)・[読解と実測](notes/worklet-safari-song-prepared-shared-context.md)
- 未達の条件。出力機器での欠落と聴感、予備描画を同じ合成器に保持して分割した場合の先行信号と歌唱の挙動は未測定。
- 最後に確認した実行。初回はJSON要約の型変換で失敗し、保存したデータを修正版で再照合した。後続2実行は順序を反転し、各80判定と2予測を満たした。初回を含む全273入力・83〜84出力を実行ごとにハッシュ照合し、採取物計16,847,950バイトをRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-prepared-shared-context-20261122-a/manifest.json)・[修正後](runs/worklet-safari-song-prepared-shared-context-20261122-b/manifest.json)・[順序反転](runs/worklet-safari-song-prepared-shared-context-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'vocal_start_score_prepared|advanceRenderPreparation|sourcePreparation|set_score' crates/vocal-wasm/{src/lib.rs,host/fixed-voice.ts} ../../../web/prototypes/chimera-research/src/fixed-processor.ts` を実行する。同じ合成器上の16,384フレームを分割して描画する条件を登録し、先行信号の最大間隔、歌唱開始までの時間、PCMと声門の観測値を今回の一括条件に照合する。

## Safariで歌唱に使う状態を保ったまま予備描画を分割（2026-11-22）

- 完了した項目。予備描画16,384フレームを構築時の一括と128フレームずつの分割で比較した。8ペアで先行信号の最大間隔は118〜135 ms短縮し、歌唱開始は256〜284 ms延びた。全16試行で先行PCM各81,920サンプル、歌唱PCM各31,200サンプル、各488観測点が基準と一致した。0フレームと257フレームの末尾もRustで検証した。[事前登録](cases/worklet-safari-song-split-score-preparation.json)・[読解と実測](notes/worklet-safari-song-split-score-preparation.md)
- 未達の条件。出力機器での欠落、聴感、128フレーム以外の分割長での歌唱開始と先行信号の間隔は未測定。分割の8試行では、最長間隔は第1片と同じContextフレームの直前に現れた。
- 最後に確認した実行。順序を反転した2実行で各100判定と2予測を通過。各274入力・84出力をハッシュ照合し、WASM・ケース・PCM・WAVの33ファイルが一致。従来の一括経路は80判定、研究版WASMの全27テストと上流のブロック長のテストも通過した。3実行の採取物計18,972,283バイトをRTL9210B-CGに置いた。[初回](runs/worklet-safari-song-split-score-preparation-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-split-score-preparation-20261122-repeat/manifest.json)・[従来経路](runs/worklet-safari-song-prepared-shared-context-20261122-split-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'scorePreparationBlockFrames|advanceScorePreparation|preparation_window_max_gap' ../../../web/prototypes/chimera-research/src/{render-fixed-voice,fixed-processor}.ts crates/vocal-wasm/host/fixed-voice.ts tools/measure_worklet_safari_song_split_score_preparation.py` を実行する。128と256フレームの分割を登録し、第1片を含む間隔と分割中の間隔を分けて、歌唱開始までの時間・PCM・観測値を比較する。

## Safariで歌唱予備描画の分割長128・256フレームを比較（2026-11-22）

- 完了した項目。Contextの出力量子128フレームを保ち、16,384フレームの予備描画を128片と64片で比較した。8ペアで歌唱開始は147〜216 ms早まり、中央値は167.5 ms。第2片以降の先行信号の最大間隔はペア中央値で1 ms増えた。全16試行で先行PCM各81,920点、歌唱PCM各31,200点、声門・放射などの各488観測点が基準に一致した。[事前登録](cases/worklet-safari-song-score-preparation-block-size.json)・[読解と実測](notes/worklet-safari-song-score-preparation-block-size.md)
- 未達の条件。各準備片が量子の処理予算に占める時間と出力機器でのサンプルの欠落、聴感は未測定。256フレーム分割では、計測窓全体の最長間隔が第1片のContextフレームの直前・直後に各4試行現れた。
- 最後に確認した実行。順序を反転した2実行で各104判定と3予測が成立。各275入力・84出力を照合し、WASM・ケース・PCM・WAVなど33ファイルが一致した。従来の一括と分割の回帰100判定、研究版WASMの端数片、上流のブロック長のテストも通過した。3実行の採取物計20,033,383バイトはRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-score-preparation-block-size-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-score-preparation-block-size-20261122-repeat/manifest.json)・[従来条件の回帰](runs/worklet-safari-song-split-score-preparation-20261122-block-size-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'advanceScorePreparation|scorePreparation|performance\.now|Date\.now' ../../../web/prototypes/chimera-research/src/{fixed-processor,realtime-speech-capture,fixed-worklet-types}.ts tools/measure_worklet_safari_song_split_score_preparation.py` を実行する。各準備片の処理時間をContextフレーム付きで記録し、第1片と後続片の中央値・p95・p99・2.667 ms超過件数を先行信号の間隔と照合する条件を登録する。

## Safariで歌唱予備描画の各片と量子の予算を照合（2026-11-22）

- 完了した項目。128・256フレーム分割の全1,536片をWASM呼び出しと無音出力までで計時し、同じContextフレームの先行信号と照合した。256フレームの第1片は5〜8 ms、第2片は4〜5 msで、8試行すべてでこの2片が1 msの丸めを考慮した超過に該当した。128フレーム分割の後続1,016片では同条件の超過は0件。全16試行で先行信号と歌唱PCM、声門などの観測値が基準に一致した。[事前登録](cases/worklet-safari-song-score-preparation-timing.json)・[読解と実測](notes/worklet-safari-song-score-preparation-timing.md)
- 未達の条件。2〜3 msに記録された片は1 msの計時精度では予算超過を個別に判別できない。機器への転送、出力サンプルの欠落、聴感、最初の片を短くしたときの負荷は未測定。
- 最後に確認した実行。順序を反転した2実行で各120判定と6予測が成立。各276入力・92出力をハッシュ照合し、33ファイルが一致した。計時を省いた対照104判定、上流の6テスト、研究版WASMの端数片のテストも通過。3実行の採取物20,501,930バイトをRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-score-preparation-timing-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-score-preparation-timing-20261122-repeat/manifest.json)・[計時なしの回帰](runs/worklet-safari-song-score-preparation-block-size-20261122-timing-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'advanceScorePreparation|scorePreparationBlockFrames|process_through_silence_ms' ../../../web/prototypes/chimera-research/src/fixed-processor.ts crates/vocal-wasm/host/fixed-voice.ts tools/song_score_preparation_timing.py` を実行する。256フレーム固定と、最初の2片を64フレームずつにした条件を事前登録し、最初の6片の負荷、歌唱開始、先行信号と歌唱のPCMを比較する。

## Safariで歌唱予備描画の最初の2片を64フレームに短縮（2026-11-22）

- 完了した項目。16,384フレームの予備描画を、256フレーム固定64片と、最初2片を64フレームにした66片で比較した。8ペアで最初の2片のピークは中央値4 ms、最初の6片のピークは中央値1 ms短縮し、歌唱開始は中央値1.5 ms延びた。最大処理時間が最初に現れる位置は全8試行で第3片に移った。全16試行で先行PCM各81,920点、歌唱PCM各31,200点、声門などの各488観測点が基準に一致した。[事前登録](cases/worklet-safari-song-score-preparation-initial-blocks.json)・[読解と実測](notes/worklet-safari-song-score-preparation-initial-blocks.md)
- 未達の条件。1 msの丸めを考慮しても短い片を使う条件の第3片8件と第4片4件が2.667 msの予算を超えた。最初の256フレーム片にかかる時間が、それまでの描画量と呼び出し回数のどちらを変えると短くなるかは未測定。出力機器の欠落と聴感も未測定。
- 最後に確認した実行。順序を反転した2実行で各120判定と3予測が成立した。各276入力・92出力のハッシュを照合し、WASM・ケース・PCM・WAVなど33ファイルが一致した。従来条件の回帰120判定、TypeScriptホストでの端数を含む5条件と無効な4条件、上流のブロック長試験も通過した。3実行の採取物20,588,201バイトはRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-score-preparation-initial-blocks-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-score-preparation-initial-blocks-20261122-repeat/manifest.json)・[従来条件の回帰](runs/worklet-safari-song-score-preparation-timing-20261122-initial-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'scorePreparationSplit|initialBlocks|startup_window_blocks|preparation_lengths' crates/vocal-wasm/host/fixed-voice.ts ../../../web/prototypes/chimera-research/src/fixed-processor.ts tools/{measure_worklet_safari_song_split_score_preparation,song_score_preparation_timing}.py` を実行する。最初の256フレームを64フレーム4片か128フレーム2片で準備する条件を登録し、256フレームに切り替えた直後の処理時間、先行信号と歌唱PCMを照合する。

## Safariで累積256フレームから歌唱予備描画を切り替える（2026-11-22）

- 完了した項目。最初の256フレームを128フレーム2片か64フレーム4片に分けた。切り替え後の最初の256フレーム片は128フレーム条件の7/8試行で4 ms、64フレーム条件の全8試行で3 msで、ペア中央値は1 ms短縮した。歌唱開始は中央値3 ms延びた。全16試行で先行PCM各81,920点、歌唱PCM各31,200点と各488観測点が保存基準に一致した。切り替え位置から歌唱へ進むWASM対照でも一括・2片・4片で一致した。[事前登録](cases/worklet-safari-song-score-preparation-switch.json)・[読解と実測](notes/worklet-safari-song-score-preparation-switch.md)
- 未達の条件。64フレーム4片の切り替え後は、3 msの記録が2.667 msの予算に収まったか、1 ms刻みの計時では判別できない。グラフ外の転送、出力機器での欠落と聴感は未測定。
- 最後に確認した実行。順序を反転した2実行で各128判定と4予測が成立。各276入力・92出力をハッシュ照合し、33ファイルが一致した。従来条件の回帰120判定と上流のブロック長試験も通過した。3実行の採取物20,519,597バイトをRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-score-preparation-switch-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-score-preparation-switch-20261122-repeat/manifest.json)・[従来条件の回帰](runs/worklet-safari-song-score-preparation-initial-blocks-20261122-switch-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'processObject|sampleTime|calibration|permission|afplay' tools/{chimera_process_tap.swift,measure_worklet_live_song_process_tap.py} notes/worklet-live-song-output-pcm.md` を実行する。Safariの試験用ステレオ信号を対象に、先行信号の連番とPCM、採取側のホスト時刻とサンプル時刻を照合する較正ケースを登録する。許可や対象プロセス選択で採取できない場合は、その段階の結果を残す。

## Safariの試験音をCore Audioの出力プロセスへ対応づける（2026-11-22）

- 完了した項目。Safariで逆相ステレオの試験音を開始、停止、再開し、同じ `com.apple.WebKit.GPU` プロセスの出力状態の変化を確認した。開始と再開のグラフPCM、各20,480サンプルは独立計算にビット一致した。連続・128サンプルの欠落・重複・無音置換の4対照を識別した。クリックで状態が変わらない試行では同じボタンへのSpaceキー操作で復旧し、採取アプリを起動しない条件を別ディレクトリからも再現した。[事前登録](cases/safari-process-tap-calibration.json)・[読解と実測](notes/safari-process-tap-calibration.md)
- 未達の条件。初回のタップは8秒以内に開始通知を返さなかった。保存したPIDに対する `kTCCServiceAudioCapture` の許可要求を確認した。タップによる実PCM、サンプル時刻・ホスト時刻、出力経路での欠落・重複・無音の実測は未取得。再試行のうち2回はSafariの再生ボタンが反応せず、採取アプリを起動する手前で止まった。
- 最後に確認した実行。グラフ対照は2実行とも17判定に合格し、先行PCMは初回と同じSHA-256だった。初回は17判定中16件が成立。許可要求は別実行でOSログに照合した。失敗を含む7実行の91入力・50出力をハッシュ照合し、採取物1,214,559バイトはRTL9210B-CGに保存した。[初回](runs/safari-process-tap-calibration-20261122-a/manifest.json)・[許可要求](runs/safari-process-tap-calibration-20261122-permission/summary.json)・[グラフ対照の再現](runs/safari-process-tap-calibration-20261122-graph-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。`notes/safari-process-tap-calibration.md` の実行手順を開く。OSの採取許可が利用できる状態で、研究ワークスペースから `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=50000000 ../../.venv/bin/python tools/measure_safari_process_tap_calibration.py <新規実行ID> /Volumes/RTL9210B-CG/voice-simulator/build/chimera-process-tap/CHIMERA-PCM-Probe.app` を実行し、対象PIDのPCM連続16,384点と時刻の条件を照合する。

## Safariの試験音とCore AudioのI/Oサイクルを照合（2026-11-22）

- 完了した項目。Safariで既知信号を流し、対象のWebKit GPUプロセスにxctraceのAudio Clientをアタッチした。停止中の対象サイクルは2実行とも0件、再生中は770・771件で、全件がグラフの観測範囲に入った。開始間隔は中央値2.667 ms、最大4.78・5.15 ms。再開後のグラフPCM各230,400サンプルは独立計算にビット一致した。[事前登録](cases/safari-audio-client-trace.json)・[読解と実測](notes/safari-audio-client-trace.md)
- 未達の条件。I/O区間の長さからWeb側の描画負荷、共有バッファの不足、出力PCMの欠落は決められない。停止と試験音で較正した計時を負荷ありの歌唱へ接続する段階と、許可待ちのプロセスタップによる実PCMの較正が残る。
- 最後に確認した実行。研究ワークスペースと `/private/tmp` から各17判定を通過。各17入力・159出力のハッシュを照合し、双方のグラフPCMがバイト一致した。従来のグラフ対照も17判定を通過し、3実行の採取物84,231,017バイトはRTL9210B-CGに保存した。[初回](runs/safari-audio-client-trace-20261122-a/manifest.json)・[再実行](runs/safari-audio-client-trace-20261122-repeat/manifest.json)・[従来経路の回帰](runs/safari-process-tap-calibration-20261122-audio-client-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'Audio Client|trace_start_epoch_ms|scorePreparationTrace|shared_context_marker|addModule' tools/measure_safari_audio_client_trace.py ../../../web/prototypes/chimera-research/tools/{capture-safari-song,capture-safari-process-tap}.mjs` を実行する。先行音を保持して歌唱ノード作成前に短いI/O記録を始め、一括予備描画と分割の構築周辺を比較する。実PCMは別の較正結果に基づいて判定する。

## Safariの歌唱準備に重なるCore AudioのI/O時刻を比較（2026-11-22）

- 完了した項目。通常のSafari歌唱画面で、予備描画16,384フレームの一括と67片への分割を4ペアで比較した。準備窓のグラフの最大間隔は一括143〜148 ms、分割6〜10 ms。GPU側のI/O開始間隔の最大値は全8試行で2.678〜2.698 msだった。各試行で先行PCM229,376サンプル、歌唱PCM31,200サンプル、声門などの488観測点が基準に一致した。[事前登録](cases/worklet-safari-song-audio-client.json)・[読解と実測](notes/worklet-safari-song-audio-client.md)
- 未達の条件。GPU側のI/O周期までを観測した。共有リングの読み出しで欠落・重複・無音が出たか、出力機器でどう聞こえるかは未判定。試験音のプロセスタップはmacOSのシステムオーディオ録音許可待ちである。[録音許可待ちの記録](notes/safari-process-tap-calibration.md#実測)
- 最後に確認した実行。順序を反転した2実行で各70判定と2予測を満たした。各276入力・374出力をハッシュ照合し、WASM・ケース・PCM・WAVの17ファイルが一致した。保存したI/Oの全24窓も再集計して一致した。従来経路は未達だったクリック操作をSpaceによる代替で復旧し、80判定と2予測を通過した。固定上流のブロック長試験も通過した。失敗時を含む4実行の採取物180,889,564バイトをRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-audio-client-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-audio-client-20261122-repeat/manifest.json)・[従来経路の欠測](runs/worklet-safari-song-prepared-shared-context-20261122-audio-client-regression/manifest.json)・[従来経路の再実行](runs/worklet-safari-song-prepared-shared-context-20261122-audio-client-regression-retry/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'maximum_interval_epoch_ms|sampleTime|processObject|marker_pcm' tools/{measure_worklet_safari_song_audio_client,measure_safari_process_tap_calibration}.py tools/chimera_process_tap.swift` を実行する。公開WebKitの共有リングの入出力で、読み出しとサンプル番号を追える計測点を確認する。録音許可が利用できる状態で、先行信号を対象に試験音のタップを較正し、同じ歌唱準備窓のPCMを判定する。[試験音の再実行手順](notes/safari-process-tap-calibration.md#実行と保存)

## AudioUnitの戻り値を較正しSafariのOverloadを再集計（2026-11-22）

- 完了した項目。自作AudioUnitで出力要求16回分の戻り値だけを `-1` にした。6試行の計192要求をAudio ClientのI/O区間に対応づけ、機器のサンプル時刻の飛びは0フレームだった。Audio Clientの4表に戻り値や固有のイベントは現れなかった。Safariの保存8試行では `Cycle; Overload` 12件が準備の約225〜272 ms前に出ており、付記を加えて再集計した24窓の最大間隔は以前と一致した。[事前登録](cases/coreaudio-output-render-status.json)・[読解と実測](notes/coreaudio-output-render-status.md)
- 未達の条件。試験機のSafariで共有リングの読み出し結果と実際の出力PCMは未観測。公開WebKitの不足時の波形処理には変更履歴があり、試験機のSafariとの厳密な版対応が未確定。タップを使うPCMの採取はmacOSのシステムオーディオ録音許可待ちである。[出力PCM較正](notes/safari-process-tap-calibration.md#実測)
- 最後に確認した実行。初回16判定、別ディレクトリでの反転順17判定、保存窓を再集計した実行18判定と、各2予測が成立した。以前の14 ms待機の対照も8判定、固定上流のブロック長試験も通過。4実行の計201入力・585出力をハッシュ照合し、採取物124,435,338バイトをRTL9210B-CGに保存した。予備試行の `xctrace --launch` は対象が制限時刻に `SIGKILL` で終了し、PIDへのアタッチに切り替えた。[初回](runs/coreaudio-output-render-status-20261122-a/manifest.json)・[反転順](runs/coreaudio-output-render-status-20261122-repeat/manifest.json)・[再集計](runs/coreaudio-output-render-status-20261122-archive-audit/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'decode_marker|sampleTime|hostTime|processObject' tools/{measure_safari_process_tap_calibration.py,chimera_process_tap.swift}` を実行する。Safariの試験信号を使い、録音許可が利用できる状態で既存のタップのPCM・サンプル時刻・ホスト時刻を較正する。公開版を独立に検証する場合は、既知の先行音でリングの読み出し成功・不足と番号の対応を先に計測する。[試験音の実行手順](notes/safari-process-tap-calibration.md#実行と保存)

## Safariの歌唱準備中のGPU通知を照合（2026-11-22）

- 完了した項目。準備前のI/Oサイクル123件すべてでGPU通知が1件ずつ記録され、Web側の待機完了と直前のGPU通知の差は最大20.4 µs。System Call TraceをGPUのPIDに限り、記録開始通知から20 msで歌唱を解放した。順序を変えた2組で全4試行の3窓を覆い、準備中の通知間隔の最大値は2.682〜2.697 ms。グラフの最大間隔は分割で128〜135 ms短くなり、PCMと観測点が基準に一致した。分割1試行ではWeb側の条件変数待ち7.143 msを別に確認した。[事前登録](cases/worklet-safari-song-output-notification.json)・[読解と実測](notes/worklet-safari-song-output-notification.md)
- 未達の条件。同時計測の生データは準備開始より前に途切れ、準備窓でサイクル単位の照合は未確認。一括準備中のWeb側の待機と、FIFO残量・共有リング内のPCMは未取得。既存タップの再試行では対象PIDとブラウザ内の既知音を確認し、8秒の開始待ちで実出力の採取が欠測した。今回の対象PIDのOSログからは録音許可の状態を確定できなかった。[タップの再試行](runs/safari-process-tap-calibration-20261122-render-status-followup/summary.json)
- 最後に確認した実行。対象PIDを絞った2組で各31判定を通過。全4試行の窓を照合し、各実行2予測が成立した。固定上流のブロック長試験も通過。欠測を含む12実行の2,181入力・1,571出力をハッシュ照合し、採取物2,150,421,065バイトをRTL9210B-CGに保存した。最終の2組と解析は40,732,931バイトだった。[先行音の照合](runs/worklet-safari-song-output-notification-20261122-all-analysis/summary.json)・[準備窓の照合](runs/worklet-safari-song-output-notification-20261122-gpu-20-series/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'PROXY|proxy_wait_completions|--release-delay-ms|capture_all_processes' tools/{measure_safari_output_notifications,measure_worklet_safari_song_audio_client}.py` を実行する。Web側の描画スレッドを一括準備窓で記録し、保存済みの分割の `psynch_cvwait` と呼び出し元を照合する。出力PCMは録音許可が利用できる状態で、先に試験音によるタップの較正を通す。[再現コマンド](notes/worklet-safari-song-output-notification.md#実行と保存)

## SafariのWeb側が歌唱準備中にWorklet完了を待つ箇所を特定（2026-11-22）

- 完了した項目。先行音で2つの描画スレッドが立ったWebContentへ記録を付け、順序を反転した2組で比較した。共有出力 `sharedRender()` の条件変数待ちは一括137.053・139.470 ms、分割4.716・6.402 msだった。全4試行でWorklet側の `BinarySemaphore::signal()` と待機の条件変数アドレスを照合し、復帰まで3.5〜8.0 µsだった。先行PCM・歌唱PCM・488観測点は基準と一致した。[事前登録](cases/worklet-safari-song-webcontent-waits.json)・[読解と実測](notes/worklet-safari-song-webcontent-waits.md)
- 未達の条件。一括の準備窓内のMach復帰は各1件で、各窓12件と先頭からの区間網羅を使う初回判定は未達。別の判定で単一の完了済み待機が準備窓に133.0・136.8 ms重なることを確認し、25 ms以下という予測を反証した。準備終了後に復帰が密集したときの書き込みフレーム数、FIFO残量と実出力PCMは未測定。[初回判定](runs/worklet-safari-song-webcontent-waits-20261122-analysis/summary.json)・[同一条件変数の照合](runs/worklet-safari-song-webcontent-waits-20261122-completed-waits/summary.json)
- 最後に確認した実行。研究ワークスペースと `/private/tmp` からの採取で各31判定に合格し、4試行の完了待機を補助解析で照合した。固定上流のホストブロック長試験も通過した。4実行の計1,218入力・396出力のSHA-256を照合し、採取物71,711,094バイトはRTL9210B-CGに置いた。[初回採取](runs/worklet-safari-song-webcontent-waits-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-webcontent-waits-20261122-repeat/manifest.json)・[補助解析](runs/worklet-safari-song-webcontent-waits-20261122-completed-waits/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'mach_gaps_at_most_100_us|completed_wait_and_signal|sampleTime' tools/{measure_safari_webcontent_waits.py,chimera_process_tap.swift}` を実行する。準備後に密集したMach復帰の間に、共有リングへどの時点で何フレーム進んだかを追える計測点を選ぶ。録音許可が利用できる状態で、既知信号のタップを較正してから同じ入力の出力PCMを照合する。[再現コマンド](notes/worklet-safari-song-webcontent-waits.md#実行と保存)

## Safariの一括準備後に公開出力位置の進みを照合（2026-11-22）

- 完了した項目。通常の歌唱画面で予備描画を一括・分割し、`getOutputTimestamp()` とその前後の `currentTime` を記録した。一括2試行では、準備中の公開値が136 ms据え置かれ、準備終了付近の二つの公開時刻で位置が4,096フレーム進んだ。対応する10〜11 msには各1件のMach待機完了が入った。全4試行の先行PCM、歌唱PCM、各488観測点は基準に一致した。[事前登録](cases/worklet-safari-song-output-position.json)・[読解と実測](notes/worklet-safari-song-output-position.md)
- 未達の条件。基準窓で切り詰めを除いた連続点を4組以上採る条件は、4試行中3試行で未達だった。公開時刻ごとの補助解析を追加し、元の判定を保存した。分割の最大位置差と一括との倍率、共有リングへの個別の書き込み、出力PCMは未測定。[当初の判定](runs/worklet-safari-song-output-position-20261122-analysis/summary.json)
- 最後に確認した実行。採取2回の各31判定と、補助解析2回の各18判定が通過した。生データから一括2試行の位置差と先行音の量子数を再計算した。初回判定を含む計1,573入力・400出力はサイズとSHA-256が一致し、採取物71,412,812バイトはRTL9210B-CGに置いた。固定上流のホストブロック長の試験も通過した。[採取1](runs/worklet-safari-song-output-position-20261122-a/manifest.json)・[採取2](runs/worklet-safari-song-output-position-20261122-repeat/manifest.json)・[時刻照合](runs/worklet-safari-song-output-position-20261122-alignment/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'grouped_recovery_step|mach_returns_between_published_times|sampleTime' tools/{measure_safari_output_positions.py,chimera_process_tap.swift}` を実行する。既知の試験音でCore Audioタップを較正できたら、一括準備の終了付近の先行信号をフレーム番号で照合する。採取が欠測する場合は、公開WebKitのリングの読み書き位置とFIFOの無音補完を既知の入力で別に検証する。[再現コマンド](notes/worklet-safari-song-output-position.md#実行と保存)・[試験音の較正](notes/safari-process-tap-calibration.md#実行と保存)

## Safariのタップ採取を滑らかな試験音で較正（2026-11-22）

- 完了した項目。Safariの既知信号を48 kHzステレオでプロセスタップから採取し、試験音の二値列を三次補間で滑らかにした。相関と分数遅延から、較正2試行で最長37,888・45,056サンプルの連番を確認した。128フレームの欠落・重複・無音と、0.25フレーム遅延を加えた対照も識別した。[事前登録](cases/safari-process-tap-smooth-marker.json)・[読解と実測](notes/safari-process-tap-smooth-marker.md)
- 未達の条件。従来の急な段差では連続判定が69点に留まった。滑らかな信号の初回ではグラフPCMのゼロ15点だけに最大5.18×10⁻¹⁷の差があり、元の判定を保存して参照値ゼロにだけ許容誤差を加えた。初回と2回目のタップで採取時刻が連続したまま約128・256フレーム分の位相の遅れが現れた。変化が生じた処理段と、一括・分割準備時の出力は未確認。[従来の試験音](runs/safari-process-tap-calibration-20261122-output-position-followup/summary.json)・[初回の滑らかな試験音](runs/safari-process-tap-smooth-marker-20261122-a/summary.json)
- 最後に確認した実行。改訂後の2実行は各26判定、従来のグラフ対照は17判定に合格。固定上流のホストブロック長試験も通過した。5実行の77入力・76出力をサイズとSHA-256で照合し、実体2,945,867バイトをRTL9210B-CGに保存した。[改訂後](runs/safari-process-tap-smooth-marker-20261122-b/manifest.json)・[別ディレクトリからの再実行](runs/safari-process-tap-smooth-marker-20261122-repeat/manifest.json)・[回帰](runs/safari-process-tap-calibration-20261122-smooth-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'marker_position_frames|anchorHostTime|songConstruction|waitForSystemTrace' tools/{smooth_tap_marker.py,chimera_process_tap.swift} ../../../web/prototypes/chimera-research/tools/capture-safari-song.mjs` を実行する。同じ試験音を通常の歌唱画面の先行信号として流し、タップ開始後に準備なし・一括・分割を解放する。予備描画を入れない対照に現れた時刻と位相の差を考慮して、同じ窓の波形を比較する。[再現コマンド](notes/safari-process-tap-smooth-marker.md#実行と保存)

## Safariの歌唱準備前後のプロセス出力を照合（2026-11-22）

- 完了した項目。準備なし・一括・分割を通常の歌唱画面から実行し、滑らかな先行信号をCore Audioタップで追った。一括2試行では完全ゼロが約131 msと約81 msの2区間に分かれて現れ、分割の最長は約0.69 msだった。両条件ともタップの入力時刻は連続し、歌唱の加工前PCMと各488観測点は保存基準と一致した。[事前登録](cases/worklet-safari-song-process-output.json)・[読解と実測](notes/worklet-safari-song-process-output.md)
- 未達の条件。初回は量子長・サンプルレートの設定漏れでタップの解析が止まった。当初の判定と生データを保存し、条件表の値で再照合した。一括の回復後に約10,368フレーム、分割に約256フレームの位相の遅れが残った。準備なしでも1試行で約11 msずつの完全ゼロが二度現れた。各無音区間の発生箇所と、機器端子のPCMは未測定。[初回の判定](runs/worklet-safari-song-process-output-20261122-a/summary.json)
- 最後に確認した実行。順序を反転した2組は各73判定と3予測を満たし、旧較正の回帰17判定と上流のホストブロック長試験も通過した。初回を含む計863入力・205出力をサイズとSHA-256で照合し、採取物25,074,936バイトをRTL9210B-CGに保存した。[再採取](runs/worklet-safari-song-process-output-20261122-b/manifest.json)・[反転順](runs/worklet-safari-song-process-output-20261122-repeat/manifest.json)・[較正の回帰](runs/safari-process-tap-smooth-marker-20261122-song-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'phase_displacement_frames|quiet_runs|fetchIfHasEnoughData|fadeOutToSilence' tools/measure_worklet_safari_song_process_output.py notes/worklet-safari-song-process-output.md` を実行する。公開WebKitの読み書き順と確定した入力要求から、リング不足とFIFOの無音補完を個別に再現し、二つの無音の間に通る先行信号を照合する。[読解と再現手順](notes/worklet-safari-song-process-output.md#実行と保存)

## Safariの二つの無音区間を公開WebKitの処理と照合（2026-11-22）

- 完了した項目。共有リングの読み出し位置とFIFOの残量を別に記録するモデルで、長い停止後の6,400フレームの読み出し不足、128フレームの信号、3,968フレームのFIFO無音を再現した。保存済み一括2試行で、間の80点は相対RMS残差0.000352・0.000371、前後の位相は10,368フレームの遅れの予測から0.086フレーム未満だった。モデルの書き込み上限2,048では後段の無音が2,048フレーム短くなった。[事前登録](cases/webkit-output-underrun.json)・[読解と照合](notes/webkit-output-underrun.md)
- 未達の条件。保存波形の完全ゼロは二つとも予測区間より95フレーム短い。最初の不足量子の64〜95点は、対象にした30・33の位置候補すべてで完全ゼロだった。公開版が出力バッファに書く減衰がタップに現れない理由と、実際のSafariの個別のリング書き込みは未確認。[端点の照合](runs/webkit-output-underrun-20261122-repeat/summary.json)
- 最後に確認した実行。研究ワークスペースと別ディレクトリからの各38判定が通過し、PCM・位置記録・要約の11出力のSHA-256が一致した。計30入力・22出力をサイズとSHA-256で照合し、採取物1,518,694バイトをRTL9210B-CGに保存した。固定上流のホストブロック長試験も通過した。[初回](runs/webkit-output-underrun-20261122-a/manifest.json)・[再実行](runs/webkit-output-underrun-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'returnStatus|OSStatus|renderStatus|app_command|sampleTime' tools/{chimera_output_deadline_probe.swift,measure_coreaudio_output_render_status.py,chimera_process_tap.swift,measure_worklet_live_song_process_tap.py}` を実行する。自作AudioUnitで同じ減衰PCMをバッファに書き、正常と `-1` の戻り値だけを切り替えて採取する。タイムスタンプとバッファ内容を保存し、減衰の観測条件を確認する。[既存の戻り値の対照](notes/coreaudio-output-render-status.md)

## AudioUnitの戻り値と不足時の減衰を照合（2026-11-22）

- 完了した項目。既定出力の自作AudioUnitで、512フレームの減衰と1,536フレームのゼロを同じPCMで書き、4要求の戻り値を0・`-1` に切り替えた。反転順の2組とも減衰をタップへ採取でき、相対RMS残差は最大8.09×10⁻⁵だった。試行機のSafari 18.6とビルド番号末尾が一致する公開WebKitでは、リング不足時に出力バッファへ減衰を書き込む処理がなかった。[事前登録](cases/coreaudio-output-error-pcm.json)・[実測と版差](notes/coreaudio-output-error-pcm.md)
- 未達の条件。自作対照の512フレーム要求で得た結果を、Safariの各要求の戻り値や機器端子の波形には照合していない。Safari稼働バイナリと公開版の厳密な対応、および実際にリングが不足したときの出力バッファの内容は未確認。
- 最後に確認した実行。研究ワークスペースと別ディレクトリの各41判定、従来の計測8判定、固定上流のホストブロック長試験が通過。3実行の45入力・60出力をサイズとSHA-256で照合し、採取物7,368,458バイトをRTL9210B-CGに保存した。比較用のPCMは4試行でハッシュが一致した。[初回](runs/coreaudio-output-error-pcm-20261122-a/manifest.json)・[反転順](runs/coreaudio-output-error-pcm-20261122-repeat/manifest.json)・[回帰](runs/coreaudio-output-deadline-20261122-error-pcm-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'class OutputPCM|native_zero_tail|tap_alignment_change' tools/{chimera_output_deadline_probe.swift,measure_coreaudio_output_error_pcm.py}` を実行する。既定出力のコールバックへ渡されたバッファを、書き込む前に観測する。旧版の不足処理に対応する保持条件と明示的なゼロ条件を照合し、Safariの最初の無音を説明できる状態を確かめる。[版差と再現手順](notes/coreaudio-output-error-pcm.md#safariと公開ソースの版)

## AudioUnitの要求バッファの入口と無音の境界を照合（2026-11-22）

- 完了した項目。自作の既定出力で、保持と明示的ゼロを2組で比較した。前後を含む32要求で、再利用されたバッファの入口は左右全サンプルがゼロだった。両条件とも返した2,048フレームの中央で無音を観測し、タップの完全ゼロ区間は全4試行で1,953フレーム。差の95フレームは、Safariで観測した二つの無音区間と一致した。[事前登録](cases/coreaudio-output-buffer-entry.json)・[読解と実測](notes/coreaudio-output-buffer-entry.md)
- 未達の条件。自作の512フレーム要求で初期値と採取時の境界を確認した。稼働中のSafariの要求バッファ、その境界に作用する処理段、機器端子の波形は未観測。既知PCMが再利用された場合と未知内容の代替はネイティブ実機の4試行で発生せず、出力デバイスを動かさない小対照で保持・代替を確認した。
- 最後に確認した実行。別ディレクトリから順序を反転した実行を含め、各74判定に合格。従来の減衰対照41判定と固定上流のホストブロック長試験も通過した。3実行の60入力・84出力をサイズ・SHA-256で照合し、採取物11,099,869バイトをRTL9210B-CGに保存した。[初回](runs/coreaudio-output-buffer-entry-20261122-a/manifest.json)・[反転順](runs/coreaudio-output-buffer-entry-20261122-repeat/manifest.json)・[従来条件の回帰](runs/coreaudio-output-error-pcm-20261122-entry-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'songScorePreparationBlock|advanceScorePreparation|compare_tap' ../../../web/prototypes/chimera-research/src/{main.tsx,render-fixed-voice.ts,fixed-processor.ts} tools/measure_worklet_safari_song_process_output.py` を実行する。研究版の歌唱で128フレーム分割と現行の256フレーム分割を同じ出力採取に通し、歌唱開始までの時間、無音と位相の変化、加工前PCMを照合する。[分割長の既存比較](notes/worklet-safari-song-score-preparation-block-size.md)・[出力採取の再現手順](notes/worklet-safari-song-process-output.md#実行と保存)

## Safariの予備描画分割長とプロセス出力を比較（2026-11-22）

- 完了した項目。通常のSafari歌唱で、均等128と64×4＋256の2条件を同じタップ経路で比較した。後者で全8ペアの歌唱立ち上がりが162.2〜204.0 ms早まり、中央値は168.8 msだった。先行音の最長低振幅区間はペア中央値で110.5フレーム短かった。全16試行の各31,200サンプルの歌唱PCM、各488観測点と譜面は保存基準と一致した。[事前登録](cases/worklet-safari-song-process-output-block-size.json)・[読解と実測](notes/worklet-safari-song-process-output-block-size.md)
- 未達の条件。256フレームを使う条件で位相の遅れの絶対量が約128フレーム増えたペアが1組あった。今回の二つのスケジュールは冒頭と後続の片がともに異なる。個々の変更が先行音の差に与えた影響、機器端子の波形、聴感は未測定。
- 最後に確認した実行。順序を反転した2組で各208判定と5予測が成立し、従来の条件の回帰も73判定を通った。固定上流のホストブロック長試験と研究版WASMの末尾片の試験も通過。3実行の848入力・395出力をサイズとSHA-256で確認し、採取物47,086,670バイトをRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-process-output-block-size-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-process-output-block-size-20261122-repeat/manifest.json)・[回帰](runs/worklet-safari-song-process-output-20261122-block-size-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'initial_blocks|compare_block_sizes|compare_song_onset' cases/worklet-safari-song-process-output-block-size.json tools/measure_worklet_safari_song_process_output.py` を実行する。冒頭4片を64フレームでそろえ、後続だけを128・256に切り替える。歌唱の立ち上がりと、冒頭および後続の先行音への影響を同じ窓と出力経路で照合する。[採取コマンド](notes/worklet-safari-song-process-output-block-size.md#実行と保存)

## Safariで冒頭4片をそろえた予備描画を比較（2026-11-22）

- 完了した項目。冒頭64×4を固定して後続だけを128・256に切り替え、先行音の窓を冒頭、切り替え付近、後続に分けた。256では準備が中央値167.5 ms短縮し、タップの歌唱立ち上がりは全8ペアで162.7〜220.4 ms、中央値182.8 ms早まった。全16試行で歌唱PCM31,200サンプル、各488観測点と譜面が保存基準に一致した。[事前登録](cases/worklet-safari-song-process-output-matched-start.json)・[読解と実測](notes/worklet-safari-song-process-output-matched-start.md)
- 未達の条件。反転順で、冒頭の最長低振幅区間のペア差の中央値が410フレームとなり、絶対値128フレーム以内の予測を外れた。長い低振幅区間の開始は推定した切り替えより前に集中し、後続の片の長さに帰属できない。1ペアで準備前後の位相の遅れの絶対量が約256フレーム増えた。機器端子の波形と聴感は未測定。[反転順の保存判定](runs/worklet-safari-song-process-output-matched-start-20261122-repeat/summary.json)
- 最後に確認した実行。計測の各216判定に合格。予測は初回7件中7件、反転順7件中6件。既定ケースの73判定、固定上流のホスト幅試験、研究版WASMの末尾片試験も通過した。3実行の848入力・395出力をサイズとSHA-256で照合し、採取物47,077,995バイトをRTL9210B-CGに保存した。[初回](runs/worklet-safari-song-process-output-matched-start-20261122-a/manifest.json)・[反転順](runs/worklet-safari-song-process-output-matched-start-20261122-repeat/manifest.json)・[回帰](runs/worklet-safari-song-process-output-20261122-matched-start-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[Firefoxの同時採取ノート](notes/worklet-live-song-paired-output.md#再現)を開き、研究ワークスペースで `rg -n 'paired_process_tap|probe_run|calibration' tools/measure_worklet_live_song_shared_context.py cases/worklet-live-song-paired-output.json` を実行する。RTL9210B-CG上の既存の試験用Firefoxを使い、同じ先行音の較正が通った採取器を `--cubeb-output` と `--paired-process-tap` の手順につなぐ。まず未準備と192フレームの事前描画を1組採り、cubebが返すPCMとプロセス出力を同じ時計で照合する。

## Firefoxでcubebとプロセスタップを同時採取（2026-11-22）

- 完了した項目。滑らかな逆相信号で二地点の両端を照合し、未準備と192フレーム事前描画を2組採取した。事前描画の2試行ではcubebが連続した4,352フレームを返し、次の予定要求は256フレーム飛んだ。タップの同じ区間は4,608フレームで、うち161フレームが左右とも完全ゼロだった。歌唱の91,200サンプル・1,425観測点・譜面は同じ現行WASMの基準に一致した。[事前登録](cases/worklet-live-song-paired-output-smooth.json)・[読解と実測](notes/worklet-live-song-paired-output.md#滑らかな先行音での同時採取)
- 未達の条件。段差のある信号は再校正でも最長71フレームしか連続照合できなかった。滑らかな信号の初回はタップの左端が採取の立ち上がりに重なり、基準WASMも旧版だった。判定を保存し、100 msの待機と現行版での歌唱基準に変更した。タップの無音の境界を変える処理段、機器端子の波形、聴感は未観測。[再校正の失敗](runs/worklet-live-song-process-tap-20261122-paired-calibration/summary.json)・[初回の欠測](runs/worklet-live-song-paired-output-smooth-20261122-a/summary.json)
- 最後に確認した実行。同時採取は別ディレクトリでの再実行を含め各40判定に合格。固定上流の各17試験、現行オフライン基準の15判定、独立生成の波形4対照、従来のcubeb単独2試行の再解析も通過。5実行の1,180入力・183出力をサイズとSHA-256で照合し、採取物・基準205,004,932バイトをRTL9210B-CGに保存した。[初回の有効な実行](runs/worklet-live-song-paired-output-smooth-20261122-b/manifest.json)・[再実行](runs/worklet-live-song-paired-output-smooth-20261122-repeat/manifest.json)・[歌唱基準](runs/worklet-song-voice-20261122-paired-reference/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'delay_us|snapshot|requested_frames|tap' tools/{chimera-cubeb-output-probe.rs,measure_cubeb_output_callback.py,measure_worklet_live_song_process_tap.py}` を実行する。固定cubebの最小対照で48 kHz・256フレームの同じ滑らかなPCMを返し、1要求だけ遅延を変える。タップで増えた位置と完全ゼロの95フレーム差が、歌唱を始めない対照でも出るかを照合する。[cubebの遅延対照](notes/cubeb-output-callback-probe.md)

## 歌唱なしでcubebの出力遅延とタップの無音を照合（2026-11-22）

- 完了した項目。固定cubebの単独出力で0・8.4 msの待機を計4ペア比較した。全8試行の返却PCM各32,768フレームはビット一致。遅延ありの4試行で次の予定要求時刻が256フレーム飛び、タップの対応区間が4,352から4,608フレームに延びた。対象要求の先頭に256点のゼロを加えたモデルの相対RMS残差は0.368〜0.369%だった。[事前登録](cases/cubeb-output-callback-process-tap.json)・[読解と実測](notes/cubeb-output-callback-probe.md#歌唱を使わないプロセスタップの同時採取)
- 未達の条件。全遅延試行で完全ゼロは162フレームで、Firefoxと同じ161フレームという予測は不成立だった。差の1点は区間終端で、Firefoxでも約2.64×10⁻¹⁰だった。境界の値を生む処理段、機器端子の波形、聴感は未観測。[保存判定](runs/cubeb-output-callback-process-tap-20261122-repeat/summary.json)
- 最後に確認した実行。同時採取2実行の各68判定、従来入口の回帰56判定、固定CHIMERAのホスト幅試験と固定cubebの等レート試験が通過。別計算の試験音、生CSVの時刻、生PCMの無音境界も照合した。3実行の46入力・126出力をサイズとSHA-256で確認し、6,934,138バイトをRTL9210B-CGに保存した。[初回](runs/cubeb-output-callback-process-tap-20261122-a/manifest.json)・[再実行](runs/cubeb-output-callback-process-tap-20261122-repeat/manifest.json)・[回帰](runs/cubeb-output-callback-20261122-paired-probe-regression/manifest.json)
- 次に開くファイルと実行するコマンド。歌唱の評価に戻り、研究ワークスペースで `rg -n 'def |search_upper_semitones|yin' tools/{measure_csd_f0_detuned_tone,measure_csd_f0_search_sensitivity}.py` を実行する。F0の固定上限を狭めたときのオクターブ誤りを、複数の周期候補と前後の連続性を使う別の推定条件で比較する。まず既知の409.35 Hz波形と保存済みの `en035a` 第21音で、既存報告と合成PCMを保存したまま効果を測る。[譜面外の既知音と残差](notes/csd-f0-search-sensitivity.md#譜面より高い既知音の対照)

## 歌唱F0で周期候補と時間方向の選択を比較（2026-11-22）

- 完了した項目。±7半音の探索を維持し、各窓の周期候補から、窓ごとの費用だけで選ぶ条件と時間方向の費用も加える条件を比較した。既知の409.35 Hzを保持し、基本音を一時的に弱めた200 Hz信号では約400 Hzの窓が12から0になった。確認曲 `en035a` 第21音の両合成は各4窓から0に改善し、窓ごとの候補選択と追跡で結果は一致した。録音の80窓は従来のF0と同じだった。[登録](cases/csd-f0-continuity.json)・[読解と実測](notes/csd-f0-continuity.md)
- 未達の条件。連続性による補正の効果は既知波形で確認した。新条件での全曲の録音・合成の比較と、実録音での音高の正解時系列、人による試聴は残る。[第2版の窓別結果](runs/csd-f0-continuity-20261122-repeat/artifacts/pitch-tracks.csv)
- 最後に確認した実行。第1版を保存し、第2版の初回と別ディレクトリからの再実行は各20判定・11予測に合格。1,027窓のCSVと要約はバイト一致。固定上流20試験と、旧条件4曲88,344窓の37判定も通過し、旧条件の要約と4本のCSVは保存基準とバイト一致した。4実行の169入力・23出力をサイズとSHA-256で確認し、6,485,037バイトをRTL9210B-CGに保存した。[第1版](runs/csd-f0-continuity-20261122-a/manifest.json)・[第2版](runs/csd-f0-continuity-20261122-b/manifest.json)・[再実行](runs/csd-f0-continuity-20261122-repeat/manifest.json)・[旧条件の回帰](runs/csd-f0-search-sensitivity-20261122-continuity-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'def (measure_track|load_all|note_track|h1h2)' tools/{measure_csd_f0_continuity,measure_csd_f0_search_sensitivity,measure_csd_note_spectrum}.py` を実行する。費用係数をこの版で固定し、調整曲と確認曲それぞれで窓ごとの候補選択と追跡を全曲に適用する。録音のF0が変わる最初の窓、音符別の有声率とビブラート、同じFFTを使うH1−H2への伝播を調べる。[曲別評価の基準](notes/csd-f0-search-sensitivity.md#4曲の結果)

## CSDの全4曲で周期候補と追跡の指標を照合（2026-11-22）

- 完了した項目。固定した費用係数で調整用・確認用各2曲の録音と両合成、486音符88,344窓を比較した。有声の85,940窓は全条件で一致。両合成の譜面より600セント以上高い677窓が窓ごとの候補選択で0になり、H1−H2の音符中央値は両合成の延べ22音符で変わった。時間費用は追加で16窓のF0を選び直し、その時点でのH1−H2とビブラートの検出件数は窓選択条件と一致した。[事前登録](cases/csd-f0-continuity-songs.json)・[読解と実測](notes/csd-f0-continuity-songs.md)
- 未達の条件。録音の曲別F0中央値の変化は最大0.473セントで、窓別には365窓が変わり最大164.41セントだった。録音のどちらの候補が実際のF0に近いか、音符間の遷移、人による試聴は未評価。[窓別の記録](runs/csd-f0-continuity-songs-20261122-a/artifacts/en001a-continuity-frames.csv.gz)
- 最後に確認した実行。初回と別ディレクトリからの再実行は各54判定・6予測に合格し、4曲の圧縮CSVと要約はバイト一致。固定上流20試験も通過した。以前の1音符・既知波形の再実行は20判定・11予測に合格し、CSVと要約が保存基準と一致した。3実行の174入力・21出力をサイズとSHA-256で照合し、採取物10,780,065バイトをRTL9210B-CGに保存した。[初回](runs/csd-f0-continuity-songs-20261122-a/manifest.json)・[再実行](runs/csd-f0-continuity-songs-20261122-repeat/manifest.json)・[1音符の回帰](runs/csd-f0-continuity-20261122-songs-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'def (period_window|period_candidates|spectrum_and_lags|direct_power)' tools/{measure_csd_f0_search_sensitivity,measure_csd_f0_continuity,measure_csd_f0_third_harmonic,measure_csd_note_spectrum}.py` を実行する。録音の最大差が出た `en001a` 第65音の49.42564秒と前後の安定窓を固定する。短時間スペクトルの倍音間隔と波形の周期を独立に測り、二つの候補で判定が分かれる最初の条件を記録する。[残った推定差](notes/csd-f0-continuity-songs.md#実測)

## CSD録音で推定差が最大のF0候補を照合（2026-11-22）

- 完了した項目。`en001a` 第65音の47窓を全曲比較に照合し、焦点と前後11窓を独立に測った。最大差の49.42564秒では従来348.39 Hz、候補選択316.83 Hzに対し、20 msの相関315.84 Hzと40 msの倍音間隔316.25 Hzが長い候補を支持した。閾値0.2を最初に下回る126ラグから127へ進んで止まり、127→128ラグで1.2〜3 kHzの差分が増えた。閾値0.15・1.2 kHz低域通過の各対照で長い周期を得た。[事前登録](cases/csd-f0-recording-period-evidence.json)・[実測と帯域の寄与](notes/csd-f0-recording-period-evidence.md#実測)
- 未達の条件。今回の範囲は調整曲の1音符。録音の声帯振動の参照時系列、別の録音への閾値・フィルタ条件の一般化、実際の聴感は未評価。[再実行の判定](runs/csd-f0-recording-period-evidence-20261122-verified-repeat/summary.json)
- 最後に確認した実行。費用係数と録音の参照照合を追加した前後の4実行が各6判定・4予測に合格し、全実行の相関CSV・スペクトルCSV・要約がバイト一致。固定上流20試験と別計算の二乗差を照合した。112入力・24出力をサイズとSHA-256で確認し、採取物342,425バイトをRTL9210B-CGに保存した。[参照照合後](runs/csd-f0-recording-period-evidence-20261122-verified-a/manifest.json)・[別ディレクトリの再実行](runs/csd-f0-recording-period-evidence-20261122-verified-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'def (evidence|probe_frames|band_difference|load_inputs|load_all)' tools/{measure_csd_f0_recording_period_evidence,measure_csd_envelope_timing,measure_csd_f0_search_sensitivity}.py` を実行する。確認曲 `en035a` の録音で差が最大の第36音、49.72006秒と前後の窓を登録し、同じ相関と倍音間隔を照合する。確認用で長い曲を読み込む入口を使い、閾値0.15と1.2 kHz低域通過が登録した候補に与える影響を別々に記録する。[曲別の比較と調整曲の残差](notes/csd-f0-continuity-songs.md#実測)

## 確認曲 `en035a` の録音F0候補を独立照合（2026-11-22）

- 完了した項目。確認曲の第36音83窓を保存済み結果と照合し、焦点49.72006秒の前後11窓を測った。従来の301.06 Hzに対し、相関276.23 Hzと40 msの倍音間隔275.75 Hzが長い276.30 Hzを支持した。146→147ラグで1.2〜3 kHzの差分が増え、総二乗差が減っても正規化後の値が上がって短いラグに止まった。焦点では閾値0.15、1.2 kHz低域通過の両条件で長い候補に移った。[事前登録](cases/csd-f0-recording-period-evidence-held-out.json)・[読解と実測](notes/csd-f0-recording-period-evidence-held-out.md)
- 未達の条件。閾値0.15では、通常の評価区間より前の補助窓49.69506秒で短い候補287.01 Hzが残った。固定閾値を4曲に適用した場合のF0と無声化への影響、声帯振動の参照記録、人による試聴評価は残る。[窓別の測定](runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/summary.json)
- 最後に確認した実行。初回と別ディレクトリの再実行で各6判定・4予測に合格し、二つのCSVと要約がバイト一致した。旧ケースの回帰も保存基準とバイト一致。固定上流20試験と生PCMからの二乗差の別計算を照合した。3実行の108入力・18出力をサイズとSHA-256で確認し、採取物259,380バイトをRTL9210B-CGに保存した。[初回](runs/csd-f0-recording-period-evidence-held-out-20261122-a/manifest.json)・[再実行](runs/csd-f0-recording-period-evidence-held-out-20261122-repeat/manifest.json)・[調整曲の回帰](runs/csd-f0-recording-period-evidence-20261122-held-out-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'def (measure_track|select_period|note_track)|yin_threshold' tools/{measure_csd_f0_continuity,measure_csd_f0_search_sensitivity,measure_csd_f0_recording_period_evidence}.py` を実行する。同じPCM、±7半音の探索範囲、電力ゲートを保ち、CMND閾値だけを0.2から0.15へ変える。4曲の録音・両合成で周期選択が変わった窓とYINの閾値を通らなくなった窓を測り、既知の弱い基本音と譜面より高い既知音、今回の補助窓を対照にする。[既知波形の対照](notes/csd-f0-continuity.md#実測)・[確認曲の結果](notes/csd-f0-recording-period-evidence-held-out.md#実測)

## CSD全4曲でYIN閾値0.2と0.15を比較（2026-11-22）

- 完了した項目。固定PCMの4曲486音符88,344窓で、YINの閾値だけを下げた。632窓はF0を得たまま長い周期へ移り、109窓はCMNDが閾値未満にならず欠測になった。合成の譜面より600セント以上高い窓は677→269で、確認曲の246窓はすべて長いラグへ移った。H1−H2の音符中央値は延べ75音符で変わった。既知409.35 Hzは0.024 Hz以内で一致し、基本波の弱い200 Hzでは約400 Hzの12窓が残った。[事前登録](cases/csd-f0-yin-threshold.json)・[読解と実測](notes/csd-f0-yin-threshold.md)
- 未達の条件。残った高音側の269窓は調整曲 `en001a` の両合成。録音の真のF0や聴感に基づく採否は未評価。今回の閾値変更は研究用の分析条件で、比較の既定値は0.2を使う。[4曲の窓別結果](runs/csd-f0-yin-threshold-20261122-repeat/summary.json)
- 最後に確認した実行。計測前に止まった初回のインポートエラーを記録した。修正後と別ディレクトリで各51判定・5予測に合格し、圧縮CSV4本、既知波形CSV、要約がバイト一致した。固定上流20試験と別計算で1,101窓・既知波形202窓を照合した。2実行の140入力・18出力をサイズとSHA-256で確認し、採取物8,875,888バイトをRTL9210B-CGに保存した。[初回の停止と再現](notes/csd-f0-yin-threshold.md#再現)・[修正後の実行](runs/csd-f0-yin-threshold-20261122-b/manifest.json)・[再実行](runs/csd-f0-yin-threshold-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'observations.csv|listening-key|rating|export' tools/{prepare_csd_listening.py,csd_listening.html} notes/csd-listening.md` を実行する。既存の歌唱試聴6区間から、回答CSVと音源対応表を検証して集計する入口を作る。分割別に揺れの評点と自然さの選択をまとめ、未回答と判定不能を別に数える。音源の並べ替えと回答の欠落を含む既知入力で照合し、人による回答を受け取れる状態にする。[歌唱試聴の実行記録](notes/csd-listening.md#試聴画面と検証)

## 歌唱のブラインド試聴回答を音源別に集計（2026-11-22）

- 完了した項目。既存の6区間について、回答CSVを素材の実行IDと音源対応表にひも付けて検証し、揺れの評点と自然さの選択を調整・確認用に分けて集計するCLIを追加した。実ブラウザと手入力相当の2試験回答で、予定12行・受領9行・記入4行の各分布を照合した。空欄、判定不能、差なし、0点を区別し、区間の自由記述を保持した。[事前登録](cases/csd-listening-responses.json)・[読解と集計条件](notes/csd-listening-responses.md)
- 未達の条件。人による試聴回答は未取得。現行CSVには素材の識別子が無いため、回答を集計するときは実際に試聴した素材の実行IDを指定する。[試聴ページ](runs/csd-listening-20261121-verified/artifacts/listening/index.html)・[集計手順](notes/csd-listening-responses.md#再現と回答の集計)
- 最後に確認した実行。作業場所を変えた2実行で各11判定とChromeでの18 WAVの再生が成立し、元の試験CSV・音源対応後の回答・要約・ブラウザ検査結果がバイト一致した。通常コマンドでも試験CSVの集計が一致し、重複区間の対照は理由を記録して停止した。4実行の82入力・16出力をサイズとSHA-256で確認し、採取物20,435バイトをRTL9210B-CGに保存した。[初回](runs/csd-listening-responses-20261122-a/manifest.json)・[再実行](runs/csd-listening-responses-20261122-repeat/manifest.json)・[通常コマンド](runs/csd-listening-responses-20261122-fixture-cli/manifest.json)・[重複対照](runs/csd-listening-responses-20261122-duplicate-fixture/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n '第7段階|実行証拠|未照合|未実施' ../../../docs/plans/chimera-research-rebuild-plan.md notes/{plan-evidence-audit,interaction-presentation}.md cases/plan-evidence-audit.json` を実行する。実装済み機能の代表ケースと実測、CSD・TSPの評価、操作・提示機能について、前回の監査以後に増えた成果から第7段階の完了条件を項目ごとに再照合する。実行で確かめた項目と、追加実装・実機・人による評価が必要な項目を根拠付きで記録する。[従来の証拠監査](notes/plan-evidence-audit.md)

## 第7段階の実行証拠を再照合（2026-11-22）

- 完了した項目。派生音声、操作・提示機能、録音評価の27実行・1,885判定・1,655出力を元のケースごとに照合した。ロシア語デモ16音節と中国語の診断句6音節について、初期の未対応が解消し、全区間の描画と実ブラウザの再演を検証した実行への参照を更新した。集計が先行実行のケースを参照する場合を監査処理で扱えるようにした。[登録](cases/plan-evidence-stage7.json)・[項目別の実行証拠](notes/plan-evidence-stage7.md)
- 未達の条件。CoreMIDIの入出力ポートは0件で、物理鍵盤の入力とブラウザの許可画面は未照合。子ども・混合体型のデュエットでの枝位置と、人による試聴回答の検証も残る。実行証拠の要約では、従来の実ブラウザ・音響測定と現行ソースの試験・ビルドの範囲を記録した。[残る条件](notes/plan-evidence-stage7.md#照合した項目)
- 最後に確認した実行。修正後と別ディレクトリで各38判定が通過し、要約がバイト一致した。現行Rust試験42件、固定上流19試験と現行Webビルドに成功。旧監査の64実行・12判定も再実行して旧要約とバイト一致した。Bunの起動失敗と先行ケースの照合失敗を保存し、5実行の新規採取ログ41,270バイトを作業用ディスクに置いた。[再実行](runs/stage7-evidence-audit-20261122-repeat/manifest.json)・[旧監査の回帰](runs/plan-evidence-audit-20261122-stage7-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースから `rg -n 'requestMIDIAccess|connectMidi|disconnectMidi|installMidi' ../../../docs/reference/chimera-vocal-synth/upstream/src/ui/{midi.ts,store.ts} ../../../web/prototypes/chimera-research/{src/main.tsx,tools/fake-midi.mjs}` を実行する。物理ポートを必要としない条件で、Chromiumの実際の権限経路を使う許可・拒否と、応答待ちの間の切断を固定上流と比較する。既存の仮想MIDI比較を回帰に使い、権限経路と入力ポートを別々に確認する。[操作・表示の対応表](notes/interaction-presentation.md)

## Web MIDIの許可・拒否と待機中の切断を照合（2026-11-22）

- 完了した項目。Chromeの標準APIで許可、拒否、許可後の再試行を固定上流と研究版6パネルで比較した。ビート・動物の5パネルにも接続待ち中の切断を追加し、古い許可・拒否で新しい接続の表示や購読が変わらないことを全6パネルで確認した。固定上流では、内部で切断して再試行した後に古い拒否を返すと一時的に拒否の表示になった。[事前登録](cases/worklet-midi-permission.json)・[読解と実測](notes/worklet-midi-permission.md)
- 未達の条件。物理機器とブラウザの許可ダイアログの表示・操作は未照合。標準APIの応答と画面の比較はヘッドレスChromeの独立した試験コンテキストで行った。試聴回答と、子ども・混合体型のデュエットでの枝位置の照合も残る。[検証の範囲](notes/worklet-midi-permission.md#再現)・[第7段階の実行証拠](notes/plan-evidence-stage7.md#照合した項目)
- 最後に確認した実行。最初の権限設定でのタイムアウトと、変更前の21判定中10件の未達を保存した。変更後と別ディレクトリの再実行で各21判定・固定上流2試験を通過し、観測JSONと要約がバイト一致した。仮想入力の回帰は手動発声16・ビート17・鳴禽14判定に通過。7実行の1,395入力・64出力をサイズとSHA-256で照合した。[初回の停止](runs/worklet-midi-permission-20261122-before/manifest.json)・[変更前](runs/worklet-midi-permission-20261122-before-v2/summary.json)・[再実行](runs/worklet-midi-permission-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'branch|layout|radius|body' tools/measure_duet_head_turbulence.py ../../../web/prototypes/chimera-research/src/{duet-page.tsx,duet-head-turbulence.ts,duet-telemetry.ts} notes/duet-head-turbulence.md` を実行する。デュエットの声部を子ども・混合体型に替え、同じ観測フレームの乱流源と枝位置をCLI・固定上流・ブラウザの描画で照合する。[既存の乱流源とシークの実測](notes/duet-head-turbulence.md)

## 子どもと混合体型のデュエットで乱流源を照合（2026-11-22）

- 完了した項目。既存の二声の体型を替え、通常のCLIでCHTLとPCMを生成した。声門枝は子ども59、混合67で固定上流より2つ大きく、接続の追加順に差があった。各生成元の配置では声門は0.2 cm、口腔は両実装でそれぞれ11.5502 cm・13.8140 cm。2画面幅で前後シーク直後の線分とバッファを照合し、左右の枝配置の入れ替えは拒否された。[事前登録](cases/duet-head-turbulence-body.json)・[読解と実測](notes/duet-head-turbulence-body.md)
- 未達の条件。乱流振幅が異なる最初の観測フレームは声部別に記録した。振幅・PCMの差を生む機構の切り分け、人の試聴、物理MIDIの入力は未検証。[生成元の比較](notes/duet-head-turbulence-body.md#実測)
- 最後に確認した実行。固定上流の型名の取り違えで止まった初回を保存した。修正後と別ディレクトリの再実行で各28判定・固定上流9試験が通過。子ども体型の上流観測プログラムは通常の上流CLIのPCMと観測119行に一致した。両実行の音源・CHTL・観測値と固定シークの線分は一致し、再生中の表示切り替えと停止の時刻は変動した。従来公演の回帰20判定も通過。4実行の1,081入力・92出力を検査した。[初回の停止](runs/duet-turbulence-body-20261122-a/manifest.json)・[再実行](runs/duet-turbulence-body-20261122-repeat/manifest.json)・[従来公演の回帰](runs/duet-turbulence-body-20261122-original-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'fn (formants|measure_pair|match_phones)|F1|F2' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs tools/measure_tsp_phone_boundaries.py` を実行する。TSPの保存済み確認用4発話で、MFAで対応が確定した強勢付き単母音から、固定上流の規則と独立計算に沿ってF1・F2を比較する。録音との差と、境界付近の窓が欠測や推定に与える影響を区別して記録する。[確認用の音素境界](notes/tsp-phone-boundaries-held-out.md)

## TSP確認用4発話のF1・F2と窓位置（2026-11-22）

- 完了した項目。録音・固定上流・研究版で共通の強勢付き単母音12か所を測定した。固定の3中心では108窓すべてでF1・F2が揃い、10・90%窓では66/72が母音区間外を含んだ。50%窓と比較できた71窓のうち35窓でどちらかが100 Hz超動き、録音 `FK61_02` の `lent` で1窓が欠測だった。[登録](cases/tsp-stressed-vowel-formants-held-out.json)・[読解と実測](notes/tsp-stressed-vowel-formants-held-out.md)
- 未達の条件。固定のF2選択が優先した約993 Hzの極と、約2324 Hzの極のどちらを録音 `MK61_01` の `seems` で共鳴として追えるかは未検証。録音の正解F1・F2の注釈と人の評価は未取得。境界寄りの結果はこの4発話に限る。[極の選択が変わった窓](notes/tsp-stressed-vowel-formants-held-out.md#実測)
- 最後に確認した実行。初回はナイキスト周波数の極が8窓で異なり、全極照合が不合格だった。負の実根と帯域幅が対応する条件を登録し、初回結果を保存した。改訂後と別ディレクトリで各4判定と固定上流7試験が通過し、180窓・36中央値の要約と固定Rustの全極はバイト一致した。3実行の90入力・15出力を確認し、採取物175,908バイトをRTL9210B-CGに保存した。[初回](runs/tsp-stressed-vowel-formants-held-out-20261122-a/manifest.json)・[改訂後](runs/tsp-stressed-vowel-formants-held-out-20261122-final/manifest.json)・[再実行](runs/tsp-stressed-vowel-formants-held-out-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'f2_min_gap_hz|def independent_poles|def window|fn formants' tools/measure_tsp_stressed_vowel_formants.py ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs` を実行する。既存の `MK61_01` の `seems` と同じ話者の `plea` だけを使い、固定版のF2選択とF2に帯域幅の条件を足した対照を、同じ窓のスペクトル包絡と照合する。採用極の継続性と欠測を変えた規則ごとに記録する。

## TSPのF2選択とLPC包絡・平滑化スペクトル（2026-11-22）

- 完了した項目。同じ録音の `seems` と `plea` 各3窓で、F2に帯域幅300 Hz未満だけを加えた。`seems` は986–993 Hzから2284–2324 Hzに移り、移動先は平滑化ピリオドグラムの高域ピークから10 Hz以内。`plea` のF2と全窓のF1・欠測数は従来と同じ。差が生じる段を極の選択に絞った。[事前登録](cases/tsp-f2-bandwidth-envelope.json)・[読解と実測](notes/tsp-f2-bandwidth-envelope.md)
- 未達の条件。探索的な300 Hz条件は同じ話者の /i/ 2語で検証した。残る確認用母音の欠測・極の置き換わり方や、音声の正解共鳴との対応は未検証。既知の極では幅広い候補しか無い場合に欠測した。[実測と対照](notes/tsp-f2-bandwidth-envelope.md#実測)
- 最後に確認した実行。初回と別ディレクトリからの再実行で各7判定・4予測と固定上流の基準試験1件を通過した。固定Rustの極を前回結果および独立LPCに照合し、包絡は複素多項式評価、平滑ピリオドグラムは直接DFTと照合した。保存出力4点がバイト一致し、6窓・7206点から局所最大を再集計した。38入力・12出力を検査し、802,610バイトの採取物をRTL9210B-CGに保存した。[初回](runs/tsp-f2-bandwidth-envelope-20261122-a/manifest.json)・[再実行](runs/tsp-f2-bandwidth-envelope-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'def select|def summarize_peaks|candidate_f2_bandwidth_limit_hz|matched_vowels_per_utterance' tools/measure_tsp_f2_bandwidth_envelope.py cases/{tsp-f2-bandwidth-envelope,tsp-stressed-vowel-formants-held-out}.json` を実行する。今回の2語を除く確認用の10母音を固定の300 Hz条件で調べ、録音・固定上流・研究版のうち最初に極が変わる窓や欠測する窓の包絡を照合する。

## TSPの未使用10母音でのF2帯域幅条件（2026-11-22）

- 完了した項目。3生成元の90窓を比較した。300 Hz未満で置き換わったのは録音 `FK61_01` の `again` の3窓だけで、追加欠測は無かった。最初と最大移動の窓には元の極と移動先の両方に局所最大があり、F2の中央値は2073.45から2913.42 Hzへ動いた。既定の比較には固定上流のF2を使う。[事前登録](cases/tsp-f2-bandwidth-held-out.json)・[読解と実測](notes/tsp-f2-bandwidth-held-out.md)
- 未達の条件。追加欠測が出る予測は今回の90窓で成立しなかった。2つのピークのどちらが録音のF2に相当するかは未確定で、300 Hz条件の精度向上は検証できていない。[窓別データ](runs/tsp-f2-bandwidth-held-out-20261122-repeat/summary.json)
- 最後に確認した実行。作業場所を変えた2実行で各6判定と固定上流の基準試験1件を通過し、要約と両包絡の数値ファイルがバイト一致した。極は独立LPC、LPC包絡は複素多項式、ピリオドグラムは直接DFTと照合した。既存2語の回帰7判定も通過して4出力が以前と一致した。93入力・16出力を確認し、701,033バイトをRTL9210B-CGに保存した。[初回](runs/tsp-f2-bandwidth-held-out-20261122-a/manifest.json)・[再実行](runs/tsp-f2-bandwidth-held-out-20261122-repeat/manifest.json)・[既存2語の回帰](runs/tsp-f2-bandwidth-envelope-20261122-order-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'def select|estimate_formants|lpc_envelope_db|fn poly_roots' tools/measure_tsp_f2_bandwidth_envelope.py tools/upstream_tsp_f2_envelope_probe.rs ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs` を実行する。既知の共役極を持つ小さな全極フィルタで、低いF2の帯域幅だけを変えた対照を2つ生成する。固定規則と300 Hz条件が既知のF2を追えるかを、同じ入力・窓と解析式で照合する。

## 既知の全極フィルタでのF2帯域幅条件（2026-11-22）

- 完了した項目。設計F2が2075 Hzで帯域幅を180・430 Hzに変えた2波形を作った。幅430 Hzの14次では固定規則が2090 Hzを採り、300 Hz未満の条件は設計F3に対応する2910 Hzを採った。12次では固定規則が2207 Hzにずれ、帯域幅の判定より先にLPC極の推定で差が出た。幅180 Hzは両次数・両規則とも設計F2付近だった。[事前登録](cases/tsp-f2-bandwidth-known-poles.json)・[読解と実測](notes/tsp-f2-bandwidth-known-poles.md)
- 未達の条件。幅430 Hzでも固定規則が両次数で設計F2から120 Hz以内に収まる予測は12次で反証された。12次で帯域が広がり周波数がずれた要因は未分離。TSP録音の正解F2も未確定。[12窓の値](runs/tsp-f2-bandwidth-known-poles-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所で各5判定・固定上流の基準試験1件に合格。2波形・要約・包絡・固定RustのJSONの5出力がバイト一致し、局所最大を別に再集計した。44入力・14出力を照合し、採取物1,521,952バイトをRTL9210B-CGに保存した。[初回](runs/tsp-f2-bandwidth-known-poles-20261122-a/manifest.json)・[再実行](runs/tsp-f2-bandwidth-known-poles-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'lag_window_hz|40\.0|def independent_poles' tools/measure_tsp_stressed_vowel_formants.py tools/upstream_tsp_f2_envelope_probe.rs ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs` を実行する。430 Hz幅・12次の50%窓を固定し、上流の自己相関ラグ窓40 Hzとラグ窓を外した対照で、係数・低い極・設計F2との差を比較する。

## 12次LPCの自己相関ラグ窓（2026-11-22）

- 完了した項目。保存した幅430 Hz・12次の300標本に、ラグ窓40 Hzと重みなしの0 Hzを適用した。最初の差は自己相関ラグ1の重み付けで、係数列は `a[1]` から変わった。F2は2205.57から2211.56 Hz、帯域幅は546.12から496.85 Hzへ動いた。[事前登録](cases/tsp-lpc-lag-window.json)・[読解と実測](notes/tsp-lpc-lag-window.md)
- 未達の条件。条件数の増加は予測どおりだった。設計F2に近づく予測は反証され、差は130.57から136.56 Hzに広がった。この1窓で残った周波数差の要因は未分離。[二条件の要約](runs/tsp-lpc-lag-window-20261122-repeat/summary.json)
- 最後に確認した実行。作業場所の異なる2実行で各5判定と固定上流の基準試験1件が通過した。40 Hzは先行の係数・極・選択・包絡と一致。要約・Rustの段階別出力・スペクトル・定数の差分が再実行とバイト一致した。54入力・12出力を確認し、採取物270,266バイトをRTL9210B-CGに保存した。[初回](runs/tsp-lpc-lag-window-20261122-a/manifest.json)・[再実行](runs/tsp-lpc-lag-window-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'pre_emph|0\.97|def solve_independently' tools/measure_tsp_lpc_lag_window.py tools/upstream_tsp_lpc_lag_probe.rs ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs` を実行する。同じ保存窓・12次・ラグ窓40 Hzで上流のプリエンファシス係数0.97と0を比べ、最初に差が出る標本から自己相関とF2までを照合する。

## 12次LPCのプリエンファシス（2026-11-22）

- 完了した項目。幅430 Hzの300標本で、40 Hzラグ窓と12次を固定し、係数0.97と0を比較した。最初の差は2番目の標本に現れ、自己相関はラグ0、予測係数は `a[1]` から変わった。設計F2との差は130.57から9.65 Hzに縮まり、Toeplitz行列の条件数は18.90倍になった。[事前登録](cases/tsp-lpc-pre-emphasis.json)・[読解と実測](notes/tsp-lpc-pre-emphasis.md)
- 未達の条件。この1窓で両予測が成立した。14次・録音・他の励振条件でのF2の周波数差、欠測、数値条件は未検証。録音の正解F2も未確定。[二条件の要約](runs/tsp-lpc-pre-emphasis-20261122-repeat/summary.json)
- 最後に確認した実行。2実行で各4判定と固定上流の基準試験1件が通過し、0.97条件は先行実行と一致した。再実行で要約・段階別Rust出力・包絡データがバイト一致し、前処理の300標本と13ラグを別計算で照合した。62入力・10出力を確認し、採取物355,872バイトをRTL9210B-CGに保存した。[初回](runs/tsp-lpc-pre-emphasis-20261122-a/manifest.json)・[再実行](runs/tsp-lpc-pre-emphasis-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'pre_emph|fn observe|def inspect_variant|def filtered_wave' tools/upstream_tsp_lpc_pre_emphasis_probe.rs tools/measure_tsp_lpc_pre_emphasis.py tools/measure_tsp_stressed_vowel_formants.py` を実行する。保存録音 `MK61_01` の `seems` と `FK61_01` の `again` の基準3窓でプリエンファシス係数だけを切り替え、F2候補、両包絡、欠測、条件数を照合する。

## TSP録音2語のプリエンファシス（2026-11-22）

- 完了した項目。実録音6窓でプリエンファシス0.97と0を比較した。5窓でF2が100 Hz以上動き、新しい欠測は無かった。`again` の中央窓では係数0でF1が下がり、1999.73 Hzの極が候補に残った状態で708.24 HzがF2に採られた。両語で条件数の中央値が増えた。[事前登録](cases/tsp-lpc-pre-emphasis-recordings.json)・[読解と実測](notes/tsp-lpc-pre-emphasis-recordings.md)
- 未達の条件。録音の正解F2は未取得。この2語では採用極の変動と数値条件の変化まで確認した。別の音素・話者での推定精度や人の評価は残る。[6窓の要約](runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所の2実行で各5判定と固定上流の基準試験1件が通過し、要約、6窓のRust出力、包絡がバイト一致した。プローブの一括実行後も既知の極の対照で4判定を通過し、先行出力3点と一致した。3実行で93入力・25出力を確認し、採取物1,619,866バイトをRTL9210B-CGに保存した。[初回](runs/tsp-lpc-pre-emphasis-recordings-20261122-a/manifest.json)・[再実行](runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/manifest.json)・[合成対照の回帰](runs/tsp-lpc-pre-emphasis-20261122-batch-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'def main|evidence|TSP|MIDI|デュエット|試聴' tools/audit_stage7_evidence.py cases/plan-evidence-stage7.json notes/plan-evidence-stage7.md` を実行する。TSPのF1・F2評価、体型別デュエット、Web MIDIの許可応答の後続実行を登録し、第7段階の既存の判定と照合する。計画の完了条件に照らし、録音の正解注釈、人による試聴、実機入力と許可画面の証拠がどこまで揃ったかを更新する。

## 第7段階の実行証拠を更新（2026-11-22）

- 完了した項目。前版の27実行を保持し、TSP母音評価、子ども・混合体型のデュエット、Web MIDIの権限応答の10実行を追加した。計画の16項目を37実行に結び付けた。母音内の36中央値と境界寄りを含む180窓、実録音6窓の前処理対照、二声の生成元別の枝描画と2表示幅、MIDIの6画面の応答を照合した。[事前登録](cases/plan-evidence-stage7.json)・[記録と検証範囲](notes/plan-evidence-stage7.md#第2版の照合)
- 未達の条件。物理MIDIの入力・出力ポートは0件で、押鍵・離鍵とブラウザの標準許可画面を操作した証拠は未取得。人による試聴回答と録音の正解F2注釈も未取得。体型別デュエットの乱流振幅差を生む演算段は未分離。[未確認の範囲](notes/plan-evidence-stage7.md#検証が残る範囲)
- 最後に確認した実行。監査3実行で各53判定が通過し、要約がバイト一致した。1,990判定・1,746出力を確認し、現行Rust42試験、上流19試験、WASM・TypeScript・Viteのビルドを通過した。第0〜7段階の回帰は64実行・12判定で旧要約と一致した。今回の4実行の890入力・17出力を検査し、採取ログ35,204バイトをRTL9210B-CGに保存した。[更新後の監査](runs/stage7-evidence-update-20261122-linked-plan/manifest.json)・[全段階の回帰](runs/plan-evidence-audit-20261122-stage7-update-regression/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'headless|setPermission|requestMIDIAccess|async function' ../../../web/prototypes/chimera-research/tools/capture-midi-permission.mjs ../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts` を実行する。標準設定の独立ブラウザプロファイルで研究版の手動発声画面を開き、許可ダイアログの表示、拒否、再試行後の許可を実際の画面とAPI応答で照合する。ダイアログが出ない場合は、ブラウザの版と権限状態を保存する。

## Chrome標準のWeb MIDI許可ダイアログ（2026-11-22）

- 完了した項目。研究版の手動発声と固定上流Playを独立したChromeプロファイルから操作した。初回拒否と直後の再試行は両方とも `NotAllowedError` になった。Chromeのサイト設定をリセットして同じページから再試行すると許可できた。両画面ともSysEx無効・入力0件で接続し、切断時に購読が1件から0件になった。[事前登録](cases/worklet-midi-browser-prompt.json)・[読解と実測](notes/worklet-midi-browser-prompt.md)
- 未達の条件。標準APIから得られた入力ポートは0件で、CoreMIDI経由の受信、物理鍵盤からの押鍵・離鍵と機器出力は未観測。人による試聴回答と録音の正解F2注釈も未取得。
- 最後に確認した実行。作業場所を変えた最終2実行で各11判定と固定上流2試験が通過した。8実行の入力と成果のサイズ・SHA-256を照合し、初期3ログの追記と観測の失敗を保存した。Chromeのログを分離した後は全出力が各マニフェストと一致した。採取物8,377,145バイトをRTL9210B-CGに保存した。[最終実行](runs/worklet-midi-browser-prompt-20261122-final/manifest.json)・[再実行](runs/worklet-midi-browser-prompt-20261122-final-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[手動発声のMIDI入力の読解](notes/worklet-midi-voice.md)を開き、研究ワークスペースで `rg -n 'MIDISourceCreate|MIDIReceived|requestMIDIAccess|listenMidi' tools ../../../web/prototypes/chimera-research/{src,tools}` を実行する。CoreMIDIに一時的な仮想送信元を登録して標準Web MIDIへ押鍵・離鍵を1回ずつ届ける。入力の列挙、バイト列、選択音とゲートを観測する。

## CoreMIDIの仮想送信元からの手動発声（2026-11-22）

- 完了した項目。研究版の手動発声と固定上流Playで、接続済みの状態からCoreMIDI仮想送信元を追加した。音57の押鍵・離鍵は両方で信頼済みイベントとして届き、保持音と呼気は押鍵・離鍵に対応した。明示ホスト時刻を持つイベントはブラウザ時刻で順序が一致した。固定上流の声門F0からドリフトを独立計算で除くと保持中は219.82–219.99 Hzだった。[ケース](cases/worklet-midi-coremidi.json)・[読解と実測](notes/worklet-midi-coremidi.md)
- 未達の条件。押鍵中にポートが消える場合と物理鍵盤は未観測。固定上流Playの既定の姿勢を使ったため、上流との加工前PCM比較は姿勢と適用時刻をそろえる別ケースに残した。人による試聴回答と録音の正解F2注釈も未取得。
- 最後に確認した実行。作業場所の異なる2実行で各26判定と固定上流の2試験に合格。研究版の加工前PCMは各128,000・128,256フレームがCLIとビット一致した。CDP権限、時刻0、補正前F0で未達だった旧版を保存した。4実行の1,100入力と35出力のサイズ・SHA-256を照合し、44,118,094バイトをRTL9210B-CGに保存した。[第3版](runs/worklet-midi-coremidi-20261122-c/manifest.json)・[再実行](runs/worklet-midi-coremidi-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[CoreMIDI送信の観測](notes/worklet-midi-coremidi.md)を開き、研究ワークスペースで `rg -n 'source.remove|statechange|liftWhere|inputs.delete' tools/capture_coremidi_source.swift ../../../web/prototypes/chimera-research/{tools/capture-midi-coremidi.mjs,src/midi-input.ts} ../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts` を実行する。同じ仮想送信元を音57の押鍵中に除去する条件を登録し、ポートの状態イベントから呼気の減衰までを測る。

## 押鍵中のCoreMIDI送信元削除（2026-11-22）

- 完了した項目。A3を保持したまま仮想送信元を除去した。離鍵を送らず、同じIDの入力が消えると両画面が呼気を解放した。研究版の正規化ゲートはNote Off対照と最大 `1.67×10⁻¹⁶` の差で、固定上流の時定数は両条件とも70 msだった。別のCoreMIDIクライアントへの削除通知には251.62–252.38 msかかった。[ケース](cases/worklet-midi-coremidi-unplug.json)・[読解と実測](notes/worklet-midi-coremidi-unplug.md)
- 未達の条件。複数のCoreMIDI入力が同じ音を保持する場合の抜線、CoreMIDI内部で通知が待つ理由、物理鍵盤の入出力は未観測。人による試聴回答と録音の正解F2注釈も未取得。
- 最後に確認した実行。別の作業場所から第2版の各35判定と固定上流の2試験に合格。研究版の各140,800フレームはCLIとビット一致した。第1版の2実行とNote Offの回帰を含む5実行で1,401入力・50出力を照合し、78,763,126バイトをRTL9210B-CGに保存した。[第2版](runs/worklet-midi-coremidi-unplug-20261122-notification/manifest.json)・[再実行](runs/worklet-midi-coremidi-unplug-20261122-notification-repeat/manifest.json)・[Note Off回帰](runs/worklet-midi-coremidi-20261122-unplug-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[押鍵中の削除の観測](notes/worklet-midi-coremidi-unplug.md)を開き、研究ワークスペースで `rg -n 'startHelper|waitSource|owners|liftWhere' ../../../web/prototypes/chimera-research/{tools/capture-midi-coremidi.mjs,src/midi-input.ts} ../../../docs/reference/chimera-vocal-synth/upstream/src/ui/midi.ts` を実行する。2つのCoreMIDI送信元が同じA3を保持した状態から順に除去し、最後の所有者が消えた時点で初めてゲートが下がるかを確認する。

## CoreMIDIの2入力による同じ音の保持（2026-11-22）

- 完了した項目。2つの仮想入力から同じチャンネルでA3を押し、A、Bの順に外した。研究版と固定上流PlayはAが消えた後もBの所有で発声を維持し、Bが消えてから1回だけ呼気を解放した。研究版の正規化ゲートは単一入力の削除対照と一致し、固定上流の時定数は両条件とも70 msだった。[ケース](cases/worklet-midi-coremidi-shared-note.json)・[読解と実測](notes/worklet-midi-coremidi-shared-note.md)
- 未達の条件。逆の順序での削除、物理鍵盤の入出力と抜き差しは未観測。子ども体型の歌唱で生じたPCM・乱流振幅差の起点、人による試聴回答と録音の正解F2注釈も未確認。
- 最後に確認した実行。異なる作業場所で各31判定と固定上流の2試験に合格し、研究版の両171,776フレームが各回のCLIとビット一致した。単一入力削除35判定、通常離鍵26判定の回帰も通過。4実行の1,122入力・40出力を照合し、68,928,791バイトをRTL9210B-CGに保存した。[再実行](runs/worklet-midi-coremidi-shared-note-20261122-repeat/manifest.json)・[単一入力削除の回帰](runs/worklet-midi-coremidi-unplug-20261122-shared-regression/manifest.json)・[通常離鍵の回帰](runs/worklet-midi-coremidi-20261122-shared-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[体型別デュエットの乱流実測](notes/duet-head-turbulence-body.md#実測)を開き、研究ワークスペースで `rg -n 'noise_level|noise_node|render_tracked|render_voice' tools/upstream_duet_body_probe.rs tools/measure_duet_head_turbulence_body.py crates/vocal-core/src ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs` を実行する。子ども声部の最初の振幅差が記録された24,576サンプル付近で、両生成元の調音目標、枝の断面積・流量と乱流振幅を対応させ、どの段から差が現れるかを測る。

## 子ども声部の声門乱流振幅の差（2026-11-22）

- 完了した項目。24,576出力サンプルでの `0.109149 dyn/cm²` の差を枝断面積と流量から再構成した。面積の寄与は `+0.169917`、流量は `−0.060767 dyn/cm²`。全ジェスチャーが一致し、登録した窓で乱流レベルを枝入力から両版とも独立計算で再現した。上流のドリフト、ジッター、シマーを0に揃えると、窓内の最大振幅差は0.459224から `5.75×10⁻¹² dyn/cm²` 未満になった。[ケース](cases/duet-child-glottal-noise-origin.json)・[読解と実測](notes/duet-child-glottal-noise-origin.md)
- 未達の条件。音源設定をそろえた対照にも歌唱前の断面積・流量差が残る。初期姿勢の寄与、体型別出力ゲインとPCM、混合体型の乱流振幅差は未分離。物理MIDI、人による試聴、録音の正解F2も未取得。
- 最後に確認した実行。作業場所を変えた第2版の2実行で各11判定・上流10試験が通過し、各版の観測器と通常CLIが91,200フレームのPCMでビット一致した。成功した4実行で23出力が一致し、版ごとの要約も一致した。5実行の715入力・143出力を照合し、170,993,850バイトをRTL9210B-CGに保存した。[第2版](runs/duet-child-glottal-noise-origin-20261122-phase/manifest.json)・[再実行](runs/duet-child-glottal-noise-origin-20261122-phase-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[子ども声部の実測](notes/duet-child-glottal-noise-origin.md#実測)を開き、研究ワークスペースで `rg -n 'rest_tip|resting_tip|snap_to_targets|for_speech_with_body' crates/vocal-core/src/{anatomy.rs,articulators.rs,voice.rs} ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/{control/articulators.rs,voice/human_voice.rs}` を実行する。音源変動を0で揃え、研究版の初期舌先だけを固定上流と同じ休止座標にすると、最初の唇端・咽頭先頭の断面積とゲート0の流量差が消えるかを数十サンプルで比較する。

## 子ども声部の初期舌先と無発声時の過渡（2026-11-22）

- 完了した項目。音源変動を0にそろえた歌唱条件で、研究版のケースの初期舌先だけを独立計算した休止位置 `[6.241412821929657, 6.810460479056529] cm` に移した。両版の初期断面積は最大 `7.77×10⁻¹⁶ cm²` の差に収まり、最初の512出力サンプルで声門流量・放射・PCMがともに0になった。最初の差が描画前の初期形状にあることを確認した。[ケース](cases/duet-child-initial-tip.json)・[読解と実測](notes/duet-child-initial-tip.md)
- 未達の条件。全区間のPCM差に対する体型別出力ゲインの寄与は描画段で未検証。保存PCMを用いた探索では最大差が0.0472802から `2.98×10⁻⁸` に減った。混合体型の乱流振幅差、物理MIDI、人による試聴、録音の正解F2も未確認。[実測](notes/duet-child-initial-tip.md#実測)
- 最後に確認した実行。異なる作業場所で各10判定と3予測、固定上流11試験が通過した。上流の既知の下唇形状1試験は除外設定。各研究版観測器の91,200フレームが通常CLIとビット一致し、両実行で20出力が一致した。先行乱流比較も11判定が通過し、27出力が以前の実行と一致した。3実行の431入力・85出力を照合し、採取物81,090,980バイトをRTL9210B-CGに保存した。[初回](runs/duet-child-initial-tip-20261122-a/manifest.json)・[再実行](runs/duet-child-initial-tip-20261122-repeat/manifest.json)・[乱流比較の回帰](runs/duet-child-glottal-noise-origin-20261122-tip-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[初期舌先をそろえた実測](notes/duet-child-initial-tip.md#実測)を開き、研究ワークスペースで `rg -n 'output_gain|limiter|dc_pole|gain' crates/vocal-core/src/output.rs crates/vocal-cli/src/timing_case/speech_voice.rs ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs` を実行する。休止位置の条件を固定し、子ども体型の出力ゲイン係数0.875だけを描画段に適用して、放射からDC除去・リミッター・PCMまでを照合する。

## 子ども声部の出力ゲインとPCM（2026-11-22）

- 完了した項目。休止舌先と音源変動をそろえた歌唱で、研究版ケースのゲインだけを `5.5×10⁻⁷` から `4.8125×10⁻⁷` にした。研究版の2条件で内部放射・FIR出力はビット一致し、最初の差は18,305フレーム目のゲイン乗算だった。固定上流との全91,200フレームのPCM最大差は0.04728022から `9.09×10⁻¹³` に減り、ピーク制限・ソフトクリップはどの条件でも作動しなかった。[ケース](cases/duet-child-output-gain.json)・[読解と実測](notes/duet-child-output-gain.md)
- 未達の条件。上流との残る微小差は、18,305フレーム目の2点目の内部放射に現れ、PCMでは23,671フレーム目で最初に丸め先が分かれた。放射の微小差を生む処理と、制限が作動する振幅でのゲインは未分離。混合体型の乱流差、物理MIDI、人による試聴、録音の正解F2も未確認。[段別の結果](runs/duet-child-output-gain-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所で各9判定と4予測、固定上流10試験が通過し、27出力がバイト一致した。研究版の2条件と上流の既定音源で観測器のPCMがそれぞれ通常CLIと一致した。初期舌先の回帰でも10判定が通過し、先行の20出力と一致した。3実行の429入力・92出力を照合し、採取物90,400,440バイトをRTL9210B-CGに保存した。[初回](runs/duet-child-output-gain-20261122-a/manifest.json)・[再実行](runs/duet-child-output-gain-20261122-repeat/manifest.json)・[初期舌先の回帰](runs/duet-child-initial-tip-20261122-gain-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[混合体型の乱流実測](notes/duet-head-turbulence-body.md#実測)を開き、研究ワークスペースで `rg -n 'noise_level|noise_node|noise_branches|BodyMix|without_all_three' tools/{upstream_duet_body_probe.rs,measure_duet_head_turbulence_body.py,upstream_duet_child_noise_probe.rs} ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs` を実行する。CHTLで最初に振幅差が出た33,792出力サンプルの前後で、混合体型の枝の位置、面積と流量を採る。上流の既定音源とドリフト・ジッター・シマーを0にする対照を、同じ枝入力の乱流振幅の独立計算に照合する。

## 混合体型の声門乱流振幅差（2026-11-22）

- 完了した項目。33,792サンプルの最大源は両版とも声門。研究版から上流を引いた振幅差 `−3.297321 dyn/cm²` を枝断面積の `−0.098094` と流量の `−3.199227 dyn/cm²` に分けた。詳細系列では33,309で初めて振幅差が許容差を超えた。3つの音源変動を0にそろえると、観測窓の振幅最大差は62.512351から `1.20×10⁻¹² dyn/cm²` 未満に減った。[ケース](cases/duet-mixed-glottal-noise-origin.json)・[読解と実測](notes/duet-mixed-glottal-noise-origin.md)
- 未達の条件。25サンプル目に始まる無発声時の流量差は音源をそろえた後も残った。混合体型で初期舌先と体型ゲインをそろえたときのPCM差は未分離。物理MIDI、人による試聴、録音の正解F2も未確認。[比較系列](runs/duet-mixed-glottal-noise-origin-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所で各12判定と3予測、固定上流10試験が通過し、25出力がバイト一致した。両版の既定条件の97,920フレームを各版の無変更の入口と照合した。JSONの真偽値の型で停止した初回の採取物を保存し、24出力が修正後と一致した。子ども声部の回帰も11判定を通過。4実行の588入力・131出力を照合し、採取物189,794,326バイトをRTL9210B-CGに保存した。[初回](runs/duet-mixed-glottal-noise-origin-20261122-a/manifest.json)・[再実行](runs/duet-mixed-glottal-noise-origin-20261122-repeat/manifest.json)・[子ども声部の回帰](runs/duet-child-glottal-noise-origin-20261122-mixed-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[混合体型の測定結果](notes/duet-mixed-glottal-noise-origin.md#実測)を開き、研究ワークスペースで `rg -n 'resting_tip|rest_tip|for_speech_with_body|snap_to_targets' tools/measure_duet_child_initial_tip.py crates/vocal-core/src/{anatomy.rs,articulators.rs,voice.rs} ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/{control/articulators.rs,voice/human_voice.rs}` を実行する。混合体型の音源変動を0にそろえ、研究版の初期舌先だけを独立計算した休止位置に合わせて、描画前の断面積とゲート0の流量・放射を比べる。

## 混合体型の初期舌先と無発声時の過渡（2026-11-22）

- 完了した項目。研究版の初期舌先だけを独立計算した休止位置 `[6.241412821929657, 6.810460479056529] cm` に変更した。元の姿勢では唇端の断面積が描画前に最大約0.000941 cm²異なり、放射は1サンプル目、更新後の声門流量は4サンプル目から差が出た。変更後は最初の512サンプルで両実装とも流量・放射・PCMが0。咽頭先頭は元の混合体型の姿勢でも一致した。[ケース](cases/duet-mixed-initial-tip.json)・[読解と実測](notes/duet-mixed-initial-tip.md)
- 未達の条件。全97,920フレームのPCM差への出力ゲインの寄与は描画段で未検証。保存波形へ0.875を適用する予備計算では最大差が0.08469647から `5.22×10⁻⁸` に減った。咽頭先頭への初期舌先の影響が体型で異なる理由、物理MIDI、人による試聴、録音の正解F2も未確認。[実測と予備計算](notes/duet-mixed-initial-tip.md#実測)
- 最後に確認した実行。異なる作業場所で各11判定と5予測、固定上流15試験が通過し、20出力がバイト一致した。研究版の両条件の各97,920フレームは通常CLIと一致し、元の姿勢と上流のPCMは先行実行と一致した。子ども声部の回帰は体型名を係数に展開してから比較する修正で11判定と3予測が通過。失敗した回帰を含む5実行の730入力と130出力を照合し、採取物105,045,440バイトをRTL9210B-CGに保存した。[最終実行](runs/duet-mixed-initial-tip-20261122-final/manifest.json)・[再実行](runs/duet-mixed-initial-tip-20261122-repeat/manifest.json)・[子ども声部の回帰](runs/duet-child-initial-tip-20261122-mixed-regression-final/manifest.json)
- 次に開くファイルと実行するコマンド。[混合体型の出力ゲインの予備計算](notes/duet-mixed-initial-tip.md#実測)を開き、研究ワークスペースで `rg -n 'output_gain|envelope|dc_pole' tools/measure_duet_child_output_gain.py crates/vocal-core/src/output.rs crates/vocal-cli/src/timing_case/speech_voice.rs ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs` を実行する。混合体型の休止舌先と音源を固定し、描画段で出力ゲインだけを0.875倍にして、全区間の放射・FIR・DC除去・ピーク制限・PCMを独立計算と固定上流に照合する。

## 混合体型の出力ゲインとPCM（2026-11-22）

- 完了した項目。休止舌先と音源変動をそろえた混合体型で、研究版の出力ゲインだけを0.875倍にした。研究版の二条件で放射とFIRはビット一致し、25,025フレーム目でゲイン乗算から差が生じた。固定上流との全97,920フレームのPCM最大差は0.08469647から `1.46×10⁻¹¹` へ縮んだ。包絡は両版の全条件で0.75以下だった。[ケース](cases/duet-mixed-output-gain.json)・[読解と実測](notes/duet-mixed-output-gain.md)
- 未達の条件。係数をそろえた後の差は25,025フレーム目の内部放射ですでに現れ、PCMでは28,039フレーム目で最初に丸め先が異なった。放射差の導入箇所と、ゲイン条件によってリミッターの作動が変わるレベルでは未検証。物理MIDI、人による試聴、録音の正解F2も未確認。[段別の比較](runs/duet-mixed-output-gain-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所で各10判定と5予測、固定上流10試験が通過し、25出力がバイト一致した。研究版2条件のPCMは通常CLIと、上流の既定音源のPCMは無変更ライブラリの混合体型観測器と一致した。子ども声部の回帰も9判定に合格し、先行の27出力と一致した。3実行の432入力・99出力を照合し、採取物109,088,065バイトをRTL9210B-CGに保存した。[初回](runs/duet-mixed-output-gain-20261122-a/manifest.json)・[再実行](runs/duet-mixed-output-gain-20261122-repeat/manifest.json)・[子ども声部の回帰](runs/duet-child-output-gain-20261122-mixed-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[固定声道での出力段の読解](notes/pcm-output.md)を開き、研究ワークスペースで `rg -n 'limiter|0\.75|hold_frames|independent_limiter' tools/{upstream_pcm_probe.rs,measure_pcm_output.py,measure_duet_child_output_gain.py} crates/vocal-core/src/output.rs` を実行する。同じ混合体型の放射波形を定数倍し、基準ゲインの包絡だけが0.75を超える対照を登録する。0.875の適用位置で変わるピーク・保持・解放とPCMを独立計算に照合する。

## 混合体型のピーク制限とゲインの適用位置（2026-11-22）

- 完了した項目。保存した放射を1.2倍すると、基準ゲインのみ6,954フレームでピーク制限が作動した。係数0.875を制限前に掛けるとPCMピーク0.711450、制限後では0.656250となり、差は最大0.05520034だった。しきい値を下回った信号でも保持・解放の間は差が残り、制限区間外は丸め許容差内だった。[ケース](cases/duet-mixed-limiter-gain-order.json)・[読解と実測](notes/duet-mixed-limiter-gain-order.md)
- 未達の条件。通常レベルでゲインをそろえても25,025フレーム目の内部放射に微小差がある。その導入箇所、発声機構自体を強く駆動した場合の音、物理MIDI、人による試聴、録音の正解F2は未確認。[通常レベルの段別比較](runs/duet-mixed-output-gain-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所で各9判定と5予測、固定上流10試験が通過し、28出力がバイト一致した。通常CLIの128・77分割、同一放射の再生と独立計算で両ゲインのPCMをビット照合した。通常レベルの混合体型の回帰は10判定が通過し、25出力が一致した。3実行の435入力・105出力を照合し、採取物127,549,986バイトをRTL9210B-CGに保存した。[初回](runs/duet-mixed-limiter-gain-order-20261122-a/manifest.json)・[再実行](runs/duet-mixed-limiter-gain-order-20261122-repeat/manifest.json)・[通常レベルの回帰](runs/duet-mixed-output-gain-20261122-limiter-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[混合体型の放射で差が初めて出た実行](notes/duet-mixed-output-gain.md#実測)を開き、研究ワークスペースで `rg -n 'rad_prev_total|radiated_flow|wall_radiation_flow_cm3_s|radiation_flow_derivative_cm3_s2' crates/vocal-core/src/airway/network.rs ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs` を実行する。通常レベルの25,025フレーム前後で口端・鼻端・壁の放射とその差分を内部サンプル単位で採り、どの成分に最初の差が現れるかを比較する。

## 混合体型で最初に異なる放射成分（2026-11-22）

- 完了した項目。最初の差は内部サンプル50,049（出力フレーム25,025の1点目）の口端流量にあった。流量差 `4.69×10⁻¹⁷ cm³/s` から放射差 `4.50×10⁻¹² cm³/s²` を `6.25×10⁻¹⁷ cm³/s²` 未満の誤差で再構成した。壁成分は次の内部サンプルで初めて異なり、鼻端は採取区間で0だった。[ケース](cases/duet-mixed-radiation-origin.json)・[読解と実測](notes/duet-mixed-radiation-origin.md)
- 未達の条件。口端流量の違いが放射負荷の入力と負荷の演算のどこで生じるかは未分離。物理MIDI、人による試聴、録音の正解F2も未確認。[初出点と直前の値](runs/duet-mixed-radiation-origin-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所で各5判定と3予測、研究版3試験、固定上流9試験が通過し、8出力がバイト一致した。両版の全97,920フレームのPCMと先頭50,304点の内部放射が先行実行とビット一致した。ピーク制限の回帰も9判定が通過し、28出力が先行と一致した。3実行の435入力・66出力を照合し、採取物56,128,036バイトをRTL9210B-CGへ保存した。[初回](runs/duet-mixed-radiation-origin-20261122-a/manifest.json)・[再実行](runs/duet-mixed-radiation-origin-20261122-repeat/manifest.json)・[ピーク制限の回帰](runs/duet-mixed-limiter-gain-order-20261122-radiation-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[口端流量の初出点](notes/duet-mixed-radiation-origin.md#実測)を開き、研究ワークスペースで `rg -n 'half_conductance|half_inertance_gain|old_load_flow|let ur =|rad_l_prev' crates/vocal-core/src/airway.rs ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs` を実行する。内部サンプル50,049の更新前圧力と口端への流入、コンプライアンス、放射抵抗・慣性、慣性枝の旧状態を採り、同じ式で再計算して最初の差を切り分ける。

## 混合体型で口端放射負荷に差が入る箇所（2026-11-22）

- 完了した項目。内部50,049で両版の更新前圧力と慣性枝流量は0。口端への流入は断面更新直後から `1.64×10⁻¹⁶ cm³/s` 異なった。この流入が口端流量差 `4.69×10⁻¹⁷ cm³/s` のほぼ全量を説明し、負荷の演算残差は `5.52×10⁻²² cm³/s` だった。丸めた新旧セル体積の差分と60 Hzの平滑化2段で両版の流入を再現した。[ケース](cases/duet-mixed-lip-load-origin.json)・[読解と実測](notes/duet-mixed-lip-load-origin.md)
- 未達の条件。体積の積を丸めずに差分を求める予備計算では流入差が `1.90×10⁻¹⁹ cm³/s` まで減った。積の差の式を変えた場合の全区間の効果と既存ケースへの影響は未検証。物理MIDI、人による試聴、録音の正解F2も未確認。[予備計算の値](runs/duet-mixed-lip-load-origin-20261122-repeat/summary.json)
- 最後に確認した実行。異なる作業場所で各6判定と3予測、研究版3試験、固定上流9試験が通過し、10出力がバイト一致した。通常CLIと先行の全97,920フレームのPCM、および48点の口端流量に照合し、初出点を厳密分数でも再計算した。初回の照合処理の停止を保全し、成功した3実行の447入力と、保全分を含む4実行の67出力を照合した。採取物14,568,725バイトをRTL9210B-CGに保存した。[停止記録](runs/duet-mixed-lip-load-origin-20261122-a/failure.json)・[最終実行](runs/duet-mixed-lip-load-origin-20261122-final/manifest.json)・[再実行](runs/duet-mixed-lip-load-origin-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[口端セルの体積の予備計算](notes/duet-mixed-lip-load-origin.md#実測)を開き、研究ワークスペースで `rg -n 'let raw =|volume_cm3|first_pole|MIN_CELL_AREA_CM2|vol_lp_coef' crates/vocal-core/src/airway/{network.rs,network/geometry.rs} ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs` を実行する。同じ断面積とセル長の系列から、既存の体積差分と積の差を展開した計算を高精度参照に照合し、初出点と追加区間で流量差への影響を測る。

## 混合体型で口端セルの体積差を展開する数値対照（2026-11-22）

- 完了した項目。展開式の未平滑流量を厳密分数に照合した。後続224点の最大誤差は `9.40×10⁻¹²` から `3.44×10⁻¹⁵ cm³/s` に減った。内部50,049で断面更新後の流入に最初の差が現れ、面積・セル長と発声計画は両条件で一致した。固定上流との全PCMの最大差は両条件とも `1.46×10⁻¹¹` だった。閉鎖・再開口と密閉圧縮は両条件で既存の判定を通過した。[事前登録](cases/duet-mixed-volume-difference.json)・[読解と実測](notes/duet-mixed-volume-difference.md)
- 未達の条件。展開式は比較差分として保存した。面積と長さが逆方向に変化して体積差がほぼ0になる場合は未測定。第7段階の物理MIDI、人による試聴、録音の正解F2も未確認。[第7段階の検証範囲](notes/plan-evidence-stage7.md#検証が残る範囲)
- 最後に確認した実行。研究ワークスペースと `/private/tmp` から各8判定、固定上流6試験が通過した。通常CLIと観測器は各条件とも全97,920フレームでビット一致した。再実行間で18出力がバイト一致し、290入力と42出力を照合した。採取物20,067,162バイトをRTL9210B-CGに保存した。[初回](runs/duet-mixed-volume-difference-20261122-a/manifest.json)・[再実行](runs/duet-mixed-volume-difference-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[第7段階の第2版照合](notes/plan-evidence-stage7.md#第2版の照合)を開き、研究ワークスペースで `rg -n 'duet|midi|listening|checks' cases/plan-evidence-stage7.json tools/audit_stage7_evidence.py` を実行する。第2版以降の混合体型デュエットとChrome・仮想CoreMIDIの実入力経路を既存の完了条件に結び付け、今のRust・Webと保存実行の証拠を照合する。機器と人の観測を必要とする条件は測定済みの範囲と区別して記録する。

## 第7段階の実行証拠を第3版へ更新（2026-11-22）

- 完了した項目。第2版の37実行と必須判定・成果を保持し、MIDIと体型別デュエットの14実行を追加した。全16項目・51実行の2,185判定と2,059出力を照合した。元の保存データから、Chrome両画面の許可状態、CoreMIDIの3操作の信頼済みイベントと研究版のPCM一致、2体型の全PCMの上流との差、混合体型の放射差の初出点を再確認した。[登録ケース](cases/plan-evidence-stage7.json)・[第3版の読解と結果](notes/plan-evidence-stage7.md#第3版の照合)
- 未達の条件。現在のCoreMIDIは入出力とも0件。物理入力・機器出力、人による試聴、録音の正解F2は未確認。試験用の回答と実測した音響指標の範囲を記録した。[未確認の範囲](notes/plan-evidence-stage7.md#実行と未確認の範囲)
- 最後に確認した実行。研究ワークスペースと `/private/tmp` の2実行で各76判定。現行Rust42試験、固定上流の比較19試験とMIDI 2試験、WASM・TypeScript・Viteの通常ビルドが通過した。第0〜7段階の回帰は64実行・12判定で旧要約に一致した。監査3実行の701入力・14出力を照合し、採取ログ25,488バイトをRTL9210B-CGに保存した。[第3版初回](runs/stage7-evidence-update-20261122-v3-a/manifest.json)・[再実行](runs/stage7-evidence-update-20261122-v3-repeat/manifest.json)・[第0〜7段階の回帰](runs/plan-evidence-audit-20261122-stage7-v3-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[実録音のF2感度比較](notes/tsp-lpc-pre-emphasis-recordings.md)を開き、研究ワークスペースで `rg -n 'def |diagnostics|spectra' tools/measure_tsp_lpc_pre_emphasis_recordings.py cases/tsp-lpc-pre-emphasis-recordings.json` を実行する。`seems` と `again` の登録6窓を起点に、元の推定器の採択値を伏せた波形・スペクトログラムと時刻を記録し、音響上の根拠、判定不能、複数判定者の差を保存できる最小の注釈手順を、既知のF2を持つ対照で検証する。

## TSP録音のF2注釈資料と回答取込（2026-11-22）

- 完了した項目。録音2語の6窓と合成対照1窓の注釈ページを作成した。波形・スペクトログラム・時刻・試聴からF2と根拠を記録し、判断困難・音声や区間の不適・無回答を保存できる。既知のF2 2,075 Hzに対する平均スペクトルの帯域ピークは2,126.95 Hzで、差は51.95 Hz。試験用の2人分の回答を通常のCLIに取り込み、70 Hz差と200 Hz差を事前条件100 Hzに照合した。[事前登録](cases/tsp-f2-annotation.json)・[読解と実測](notes/tsp-f2-annotation.md)・[注釈ページ](runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)
- 未達の条件。実際の判定者の回答は0件で、録音6窓のF2に対する上流採択の正誤は未判定。物理MIDIと人によるTSP・CSDの試聴結果も未確認。[注釈の検証範囲](notes/tsp-f2-annotation.md#実測と保存先)
- 最後に確認した実行。研究ワークスペースと `/private/tmp` で各8判定、固定上流1試験を通過し、判定者用資料と要約など23出力がバイト一致した。保存先のリンクから開いたChromeでも7音声・7画像とCSV出力を検証した。3実行の48入力・54出力を照合し、採取物3,134,838バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-f2-annotation-20261122-repeat/manifest.json)・[試験回答の取込](runs/tsp-f2-annotation-20261122-fixtures/manifest.json)
- 次に開くファイルと実行するコマンド。[注釈資料の使い方](notes/tsp-f2-annotation.md#使い方)を開く。実際の回答がある場合は同節の `collect` で取り込み、2人以上の根拠と周波数を照合してから上流の採択値と比較する。回答を待つ間は `rg -n 'power_spectrum|control_peak|synthetic_f2_hz' tools/measure_tsp_f2_annotation.py cases/tsp-f2-annotation.json` を実行し、同じ既知の声道極を保って励振の周期だけを変える対照で、帯域ピークと倍音間隔の関係を測る。

## TSPの既知F2で励振周期を変更した対照（2026-11-22）

- 完了した項目。F2を2,075 Hz・帯域幅180 Hzに固定し、F0を100〜400 Hzの7条件で比較した。平均スペクトルのピークは164.06 Hz動き、全条件で理論上の最強倍音から2.35 Hz以内だった。固定上流の21窓×2次数のLPCは全件でF2を返し、最大誤差は76.87 Hz。120 Hzを超える外れの予測は反証された。[事前登録](cases/tsp-f2-harmonic-spacing.json)・[読解と実測](notes/tsp-f2-harmonic-spacing.md)
- 未達の条件。幅430 Hzでの同じF0の比較を残す。実録音の正解F2の注釈、人による試聴、物理MIDIも未確認。[注釈資料](notes/tsp-f2-annotation.md#使い方)
- 最後に確認した実行。研究ワークスペースと `/private/tmp` から、各4判定と固定上流7試験が通過した。最終2実行で13出力がバイト一致した。平均スペクトルの共用後も前回の注釈資料と要約をバイト照合した。5実行の119入力・81出力を照合し、採取物6,670,421バイトをRTL9210B-CGに保存した。[最終実行](runs/tsp-f2-harmonic-spacing-20261122-final/manifest.json)・[再実行](runs/tsp-f2-harmonic-spacing-20261122-final-repeat/manifest.json)・[注釈資料の回帰](runs/tsp-f2-annotation-20261122-harmonic-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[帯域幅を変えた既知極の実測](notes/tsp-f2-bandwidth-known-poles.md#実測)を開き、`rg -n 'wide-f2|bandwidths_hz|candidate_f2_bandwidth_limit_hz' cases/tsp-f2-bandwidth-known-poles.json tools/measure_tsp_f2_known_poles.py` を実行する。同じ7条件でF2の帯域幅だけを430 Hzに変更し、F2に近い候補の有無と上流の採択段を照合する。人の注釈が届いた場合は注釈用CLIの `collect` から録音評価を進める。

## TSPの既知F2で帯域幅を180 Hzから430 Hzへ広げる対照（2026-11-22）

- 完了した項目。同じ7種類のF0の各3窓・2次数を両幅で比較した。帯域幅430 Hzでは12次・15件で600 Hzの選別前から近傍の根が無く、14次・21件では固定規則が近傍を採った。300 Hz未満の追加条件では、固定規則が近傍を採っていた430 Hzの13件と180 Hzの3件がF3に移った。[事前登録](cases/tsp-f2-harmonic-bandwidth.json)・[読解と実測](notes/tsp-f2-harmonic-bandwidth.md)
- 未達の条件。実録音の候補極の次数依存と、録音のF2の正解注釈は未確認。人による試聴と物理MIDIの確認も残る。[TSP注釈の手順](notes/tsp-f2-annotation.md#使い方)
- 最後に確認した実行。研究ワークスペースと `/private/tmp` で各5判定と固定上流7試験を通過し、波形・根・要約など4出力がバイト一致した。従来の2波形の回帰も5判定、上流1試験、6出力の一致を確認した。3実行の78入力・19出力を照合し、採取物5,117,672バイトをRTL9210B-CGに保存した。[初回](runs/tsp-f2-harmonic-bandwidth-20261122-a/manifest.json)・[再実行](runs/tsp-f2-harmonic-bandwidth-20261122-repeat/manifest.json)・[既存対照の回帰](runs/tsp-f2-known-poles-20261122-harmonic-bandwidth-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[録音6窓の比較](notes/tsp-lpc-pre-emphasis-recordings.md#実測)を開き、`rg -n 'order|filtered_wave|def prepare|run_probes' tools/measure_tsp_lpc_pre_emphasis_recordings.py tools/measure_tsp_stressed_vowel_formants.py` を実行する。保存録音の `seems` と `again` で入力窓とプリエンファシスを固定して12次・14次の候補差を測る。判定者のCSVが届いた場合は、先に注釈用CLIで照合して正誤判定に使う。

## TSP録音6窓のLPC次数によるF2候補の差（2026-11-22）

- 完了した項目。同じ録音窓と前処理で12次・14次を比較した。`seems` の3窓は14次から12次で約1.3 kHz高くなり、既定の約1 kHzの極は変更次数の生の根の段から近傍に無かった。`again` は79 Hz未満の移動。既定次数の録音6窓を保存済み出力と照合した。生の複素根の照合では実軸上の丸めを見つけ、初回の判定を保持した上で全根を対応付けた。[事前登録](cases/tsp-lpc-order-recordings.json)・[読解と実測](notes/tsp-lpc-order-recordings.md)
- 未達の条件。実録音の正解F2の注釈は未取得。試聴の回答と物理MIDIの計測も未確認。[注釈資料の使い方](notes/tsp-f2-annotation.md#使い方)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#実行と未確認の範囲)
- 最後に確認した実行。第2版の2実行で各4判定と固定上流7試験が通過し、根・要約など3出力がバイト一致した。プリエンファシスの回帰では5判定、固定上流1試験、8出力の一致を確認した。初回を含む136入力・25出力を照合し、採取物1,607,391バイトをRTL9210B-CGに保存した。[初回](runs/tsp-lpc-order-recordings-20261122-a/manifest.json)・[第2版再実行](runs/tsp-lpc-order-recordings-20261122-repeat/manifest.json)・[プリエンファシスの回帰](runs/tsp-lpc-pre-emphasis-recordings-20261122-order-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[第7段階の実行証拠](notes/plan-evidence-stage7.md#第3版の照合)を開き、`rg -n 'tsp|listening|physical|midi' cases/plan-evidence-stage7.json tools/audit_stage7_evidence.py` を実行する。追加された録音・既知対照・注釈の検証を監査に結び付け、候補値や検証用の回答から人手注釈が得られたと判定しないことを確かめる。実際のCSVが届いた場合は、注釈用CLIの `collect` を先に実行する。

## 第7段階の監査にF2の観測と注釈の出所を追加（2026-11-22）

- 完了した項目。第3版の51実行を保持し、実録音と既知対照・注釈資料の5実行を追加した。16項目・56合格実行の2,207判定、2,113出力と、別途保全した初回不合格の5出力を照合した。一次出力から実録音6窓のF2採択と合成試験回答の一致を再計算し、録音の初回と修正版の上流観測が一致することを確認した。[第4版の事前登録](cases/plan-evidence-stage7.json)・[読解と結果](notes/plan-evidence-stage7.md#第4版の照合)
- 未達の条件。実録音の人手F2注釈、人によるTSP・CSD試聴、物理MIDIの対応するイベントと音響出力の観測は未取得。監査時のCoreMIDI入出力は各0件だった。[未確認の観測と必要な記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別の作業場所の2実行で各88判定が通過し、要約がバイト一致した。現行Rust42試験、固定上流21試験、WASM・TypeScript・Viteのビルドを確認した。第0〜7段階の64実行に対する回帰は12判定を通過し、旧要約と一致した。監査3実行の729入力・14出力を確認し、採取ログ26,173バイトをRTL9210B-CGに保存した。[第4版再実行](runs/stage7-evidence-update-20261122-v4-repeat/manifest.json)・[第0〜7段階の回帰](runs/plan-evidence-audit-20261122-stage7-v4-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[計画の段階別完了条件](../../../docs/plans/chimera-research-rebuild-plan.md#実装順と段階の完了条件)と[全段階の監査ケース](cases/plan-evidence-audit.json)を開き、`rg -n '基準5発話|較正母音|実時間|対応表|未確認' progress.md notes/plan-evidence-audit.md notes/plan-evidence-stage7.md` を実行する。完了条件を代表実行の検証範囲と一項目ずつ照合し、成果が読めることだけを根拠にしている条件は、対象を直接確かめた実行から補う。人の回答や実機が必要な項目は、対応する記録が得られた場合に計測する。

## 全段階の完了条件と観測値の照合（2026-11-22）

- 完了した項目。段階ごとの条件を75実行の入力・判定・観測値へ対応付けた。一様管は両壁条件で各48,000点を再計測した。剛体の1/4波長近似との最大差は1.396%、FDTDと線形の最大差は剛体0.262%・軟壁0.263%。基準10母音・9遷移、基準5発話の202,527フレーム、5レートの実時間の観測を照合した。固定LF、既存波動管とFDTD、Firefoxの固定発声と歌唱の4実行で不合格の項目を保持した。[事前登録](cases/plan-completion-evidence.json)・[読解と照合](notes/plan-evidence-audit.md#完了条件と観測値の照合)
- 未達の条件。第7段階の実録音の人手F2注釈、TSP・CSDの人による試聴、物理MIDIを入力元とした計測は未取得。歌唱のネイティブABIで11,809回の割り当てを確認し、一部のFirefox試行では1 ms刻みの時間計測で予算を超えた。音響機器端子での出力と聴感は未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)・[歌唱の計時](notes/worklet-live-song-cross-browser.md)
- 最後に確認した実行。第2版の2実行は各141判定を通過し、要約がバイト一致した。固定上流を参照する現行CLIの一様管は剛体5判定、軟壁10判定を通過した。両条件の解析設定・候補の生系列と軟壁の上流時系列は、それぞれ保存基準とバイト一致。剛体の要約はキー順だけが変わった。初回も含む717入力と17出力を照合し、採取物24,193,918バイトをRTL9210B-CGへ保存した。[初回](runs/plan-completion-evidence-20261122-a/manifest.json)・[再実行](runs/plan-completion-evidence-20261122-repeat/manifest.json)・[剛体](runs/plan-completion-rigid-20261122/manifest.json)・[軟壁](runs/plan-completion-soft-wall-20261122/manifest.json)
- 次に開くファイルと実行するコマンド。[第7段階の未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)から取得できた記録を処理する。F2の回答を受領した場合は `../../.venv/bin/python tools/measure_tsp_f2_annotation.py collect --help` で引数を確認し、資料IDと照合して取り込む。物理MIDIが使える場合は[既存の仮想入力計測](notes/worklet-midi-coremidi.md)と同じ出力時計で、A3の1押鍵と1離鍵を採る。

## TSP比較試聴のページと資料ID付き回答（2026-11-22）

- 完了した項目。調整用6対・確認用12対の録音と研究版のWAVを保持し、A/Bでテンポと文中の間を比較するページを作った。CSVを元の資料・音源・区分に対応付け、未回答・同程度・判定不能と自由記述を記録できる。試験回答2件の集計を手計算に照合した。[事前登録](cases/tsp-listening-responses.json)・[試聴ページ](runs/tsp-listening-responses-20261122-final/artifacts/listening/index.html)・[読解と実測](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)
- 未達の条件。人のTSP・CSD試聴回答と実録音の人手F2注釈は未取得。CoreMIDIは入出力各0件で、物理鍵盤の入力と出力音を観測できていない。[必要な記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別々の作業場所で各7判定、固定上流TSP 6試験を通過し、全47出力がバイト一致した。Chromeで音源36件の読み込みと長さ、逐次再生、390 px幅、CSV書き出しを確認した。通常取込の試験回答は手計算と一致し、表記を変えた試験回答と空欄を人による回答として登録する対照は拒否した。6実行の315入力と145出力を照合し、採取物45,947,026バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-listening-responses-20261122-repeat/manifest.json)・[試験回答の集計](runs/tsp-listening-responses-20261122-fixture/summary.json)・[拒否](runs/tsp-listening-responses-20261122-reject-fixture/manifest.json)
- 次に開くファイルと実行するコマンド。[TSPの回答手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を開き、回答が得られたら `../../.venv/bin/python tools/measure_tsp_listening.py collect --help` で取込を確認する。確認用の有効な回答を既存の発話区間長の差へ対応付ける。CSD、F2、物理MIDIには[対応する観測手順](notes/plan-evidence-stage7.md#未確認の観測)を使う。

## TSPの試聴回答と時間計測の照合（2026-11-22）

- 完了した項目。録音・固定上流・再実装の各2条件を、保存済みの窓RMSから合計108区間再計算した。36試聴WAVの標本数は主しきい値の区間長と一致。−35 dBで全18対中2対の長短の向きが低エネルギー時間を除くと逆になった。試験回答2件の原CSVを再読し、資料・音源・区分を照合して7件の事前判定と一致させた。[事前登録](cases/tsp-listening-timing.json)・[読解と実測](notes/tsp-active-duration-original.md#試聴のテンポと区間長の照合)
- 未達の条件。人のTSP・CSD試聴回答と実録音F2の人手注釈は未取得。物理MIDIの入力・出力は観測できていない。低エネルギー時間に含まれる子音と、聴取者が文中の間として認識する箇所の対応は未確認。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。異なる作業場所で各4判定と固定上流6試験が通過し、結果3件と上流の標準出力がバイト一致した。Cargoのログにロック待ちの差があった。別の畳み込みでも108条件の低エネルギー区間が一致した。回答を指定しない実行は3判定が通過し、試聴対の計測JSONが同一だった。3実行の220入力・14出力を照合し、採取物265,746バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-listening-timing-20261122-repeat/manifest.json)・[音響量のみ](runs/tsp-listening-timing-20261122-acoustic/manifest.json)
- 次に開くファイルと実行するコマンド。[試聴と取込の手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を開く。人のCSVを受領したら `tools/measure_tsp_listening.py collect` を実行し、その実行IDを `../../.venv/bin/python tools/measure_tsp_listening_timing.py <新しい実行ID> --responses <取込実行ID>` へ渡す。まず確認用07の速さと文中の間の回答を、主しきい値の各指標と照合する。

## TSP確認用07の低エネルギー区間と語・音素の対応（2026-11-22）

- 完了した項目。録音と両合成を同じMFA設定で整列した。主しきい値の録音−再実装の低エネルギー時間差215 msのうち、200 msは録音の `soap → saves` の語間に重なった。両合成に同じ箇所の語間区間はなく、再実装では語末の `P` に70 msが重なった。録音の語間への割当は副しきい値でも200 ms。整列時の発話範囲確認に先行実行の保存済み18録音を指定できるようにした。[事前登録](cases/tsp-phone-boundaries-listening-07.json)・[読解と実測](notes/tsp-active-duration-original.md#確認用07の低エネルギー区間と語音素)
- 未達の条件。語間のうち子音の閉鎖や摩擦の成分がどれだけを占めるかと、人の試聴で間として聞こえるかは未確認。TSP・CSDの試聴回答、人手F2注釈、物理MIDIの観測も未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。整列と調整用回帰で各7判定、固定上流TSPの6試験が通過した。配分の2実行は各3判定で、全2出力がバイト一致した。独立検証の3判定で、合成の整列用PCM16計215,054フレームが固定上流Rustの計算結果と一致し、録音の境界は保存されたミリ秒値に一致した。5実行の82入力・70出力を照合し、実体3,962,445バイトをRTL9210B-CGに保存した。MFA作業領域は同じディスクに各約1.0 GiB残った。[整列](runs/tsp-phone-boundaries-listening-07-20261122-a/manifest.json)・[配分の再実行](runs/tsp-listening-gaps-20261122-repeat/manifest.json)・[独立検証](runs/tsp-phone-boundaries-listening-07-20261122-verified/manifest.json)
- 次に開くファイルと実行するコマンド。[確認用07の配分](runs/tsp-listening-gaps-20261122-repeat/artifacts/attribution.json)の690〜890 msに対応する波形と、元の[試聴ページ](runs/tsp-listening-responses-20261122-final/artifacts/listening/index.html)を開く。回答が届いたら `tools/measure_tsp_listening.py collect` と `tools/measure_tsp_listening_timing.py --responses` で照合する。合成側の閉鎖を追加観測する場合は、`soap` 語末の `P` と `saves` 語頭の `S` を同じ時計で測る。

## TSP確認用07の /p/ の閉鎖と /s/ の歯の乱流（2026-11-22）

- 完了した項目。両実装の唇の閉鎖は33,970〜38,208フレームで一致し、/p/ に割り当てられた低エネルギー時間は全点がその中に入った。再開口は796 ms、放射のピークは798.854 ms、歯の乱流の開始は800 ms。MFAの /s/ 始端は820 msだった。計画と主ジェスチャーの区間を独立式へ照合した。[事前登録](cases/tsp-soap-saves-transition.json)・[読解と実測](notes/tsp-active-duration-original.md#確認用07の再開口と歯の乱流)
- 未達の条件。発話全体での両PCMの最大差は0.70616で、/p/ より前の `fine` の二重母音内にある。発話先頭のPCM差が入り始める内部状態の順序はこの観測点からは確定できない。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIは未観測。[出力差と次の観測](notes/tsp-active-duration-original.md#確認用07の再開口と歯の乱流)・[必要な記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別の作業場所から各6判定、固定上流13試験を通過した。各107,527フレームは通常CLIから保存版および観測器に照合した。要約・PCM・抜粋など9出力が一致し、既存の `coat to` 回帰は8判定と6出力の一致を確認した。387入力・40出力を照合し、採取物37,944,715バイトをRTL9210B-CGに保存した。[初回](runs/tsp-soap-saves-transition-20261122-a/manifest.json)・[再実行](runs/tsp-soap-saves-transition-20261122-repeat/manifest.json)・[回帰](runs/tsp-coat-to-closure-20261122-soap-saves-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[確認用07の試聴ページ](runs/tsp-listening-responses-20261122-final/artifacts/listening/index.html)と[録音の語間の配分](runs/tsp-listening-gaps-20261122-repeat/artifacts/attribution.json)を照合する。回答が得られたら `tools/measure_tsp_listening.py collect` と `tools/measure_tsp_listening_timing.py --responses` を使う。波形差を調べる場合は `runs/tsp-soap-saves-transition-20261122-repeat/summary.json` を開き、発話開始から `fine` の二重母音までの声門と放射を同じ時計で採る。

## TSP確認用07の fine の波形差と上流の音源変動（2026-11-22）

- 完了した項目。上流のドリフト・ジッター・シマーを0にすると、42,240内部サンプルのF0と声門位相が再実装に一致した。二重母音のPCM最大差は0.70616から0.05726に低下した。上流内では、音源の差が初回のF0・位相から声門面積と流量の内部22,710、放射の22,711、Float32の出力11,378へ順に現れた。差し引きで残った二重母音の差は、観測された女性体型の出力係数を用いたDC除去後の独立計算へ照合した。[事前登録](cases/tsp-fine-source-variation.json)・[読解と実測](notes/tsp-active-duration-original.md#確認用07の-fine-で声門の揺らぎをそろえる)
- 未達の条件。3種類の揺らぎの個別寄与、最初の舌先による放射の箇所、実際の描画中に女性体型ゲインをそろえた比較は残る。人によるTSP・CSDの試聴、実録音F2の人手注釈、物理MIDIは未観測。[第7段階の必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。計画を保存JSONから再読した初回は通常CLIと微小差があった。修正版では同じ計画関数を使って全PCMが通常CLIと一致した。別の作業場所で各3判定、固定上流10試験、研究版11試験が通過し、結果と観測の15出力が一致した。先行の子音回帰は6判定と6出力の一致。初回を含め539入力・76出力を照合し、採取物66,829,140バイトをRTL9210B-CGへ保存した。[初回](runs/tsp-fine-source-variation-20261122-a/manifest.json)・[修正版の再実行](runs/tsp-fine-source-variation-20261122-repeat/manifest.json)・[回帰](runs/tsp-soap-saves-transition-20261122-fine-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[段ごとの実測](runs/tsp-fine-source-variation-20261122-repeat/summary.json)を開く。体型ゲインを調べるときは `tools/measure_tsp_fine_variation.py` と `tools/measure_duet_child_output_gain.py` の独立計算を読み、同じ音源条件でゲインだけの対照を登録する。人の回答が得られたら、先に[試聴の取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)から結果を照合する。

## TSP確認用07の女性体型ゲインを通常描画で照合（2026-11-22）

- 完了した項目。研究版の出力ゲインだけを `5.5×10⁻⁷` から `4.8125×10⁻⁷` に変更した。両条件の内部215,054サンプルと間引き値はビット一致し、出力段の最初の差は乗算後に出た。揺らぎをそろえた上流との二重母音のPCM最大差は `1.49×10⁻⁸`。予測した `1×10⁻⁶` 以下だった。[事前登録](cases/tsp-fine-output-gain.json)・[読解と実測](notes/tsp-active-duration-original.md#確認用07の出力ゲインをそろえた通常描画)
- 未達の条件。ゲインを合わせた発話全体の最大差は冒頭4.5625 msの0.00189。初期舌先がこの残差に与える寄与は今回の対照では未確認。人のTSP・CSDの試聴回答、実録音F2への人手注釈、物理MIDIは未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。異なる作業場所で各5判定と固定上流・研究版21試験が通過し、要約・両PCM・状態系列など10出力がバイト一致した。通常CLIと観測器の全PCMを各条件で照合し、FIR・DC除去・リミッターを独立計算した。272入力と28出力を照合し、採取物72,963,714バイトをRTL9210B-CGに保存した。[初回](runs/tsp-fine-output-gain-20261122-a/manifest.json)・[再実行](runs/tsp-fine-output-gain-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[ゲインを合わせた実行](runs/tsp-fine-output-gain-20261122-repeat/summary.json)と `tools/measure_tsp_startup.py` の `resting_tip` を開く。初期舌先を調べるときは同じ音源とゲインで座標だけの対照を登録し、4.5625 ms付近を観測する。試聴回答が得られたら、既存の[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の初期舌先と発話前の放射を照合（2026-11-22）

- 完了した項目。ゲインをそろえた候補で、舌先の初期座標2値だけを上流の休止位置へ変更した。揺らぎ0の上流と発話前50 msのPCMが全点0で一致し、最初の非ゼロは両方とも2,439フレーム。従来の最大差があった4.5625 msでは口端が総振幅の約99.8%を占めた。変更後は発話全体の最大PCM差が `2.33×10⁻¹⁰`、`fine` の二重母音区間の差は0だった。[事前登録](cases/tsp-fine-initial-tip.json)・[読解と実測](notes/tsp-active-duration-original.md#確認用07の初期舌先と発話前の放射)
- 未達の条件。既定の上流のドリフト・ジッター・シマーを候補にも指定した組み合わせの波形と内部状態を照合する。実録音F2への人手注釈、人によるTSP・CSD試聴、物理MIDIは未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回は成分計算で `COLUMNS` のインポートが欠けたため停止し、出力を保全した。修正版と別ディレクトリでの再実行は各6判定・事前予測3件、上流と研究版の21試験を通過し、要約・PCM・内部系列など7出力が一致した。出力ゲインの回帰は5判定と10出力の一致。418入力と49出力を照合し、採取物124,574,370バイトをRTL9210B-CGに保存した。[初回失敗](runs/tsp-fine-initial-tip-20261122-a/failure.json)・[再実行](runs/tsp-fine-initial-tip-20261122-repeat/manifest.json)・[ゲイン対照の回帰](runs/tsp-fine-output-gain-20261122-tip-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の既定と揺らぎ0の比較](runs/tsp-fine-source-variation-20261122-repeat/summary.json)と[休止位置を合わせたケース](runs/tsp-fine-initial-tip-20261122-repeat/artifacts/resting-tip-case.json)を開く。`rg -n 'pitch_drift_cents|period_jitter|amplitude_shimmer' crates/vocal-cli/src/timing_case/speech_voice.rs crates/vocal-core/src/glottis.rs` で設定から声門までの経路を確認する。同じ舌先とゲインで上流の通常設定を適用するケースを先に登録し、通常CLIの全PCMと観測した声門位相を照合する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07で固定上流の既定の揺らぎを照合（2026-11-22）

- 完了した項目。発話CLIのケースで3つの揺らぎを個別指定できるようにした。確認用07で休止位置とゲインを固定し、上流既定の値を指定すると、冒頭440 msのF0・声門位相・面積は全42,240内部サンプルで上流と一致した。全PCMの最大差は0.66125から `1.16×10⁻¹⁰` に縮んだ。周期の折り返しは90回。乱数と3本のIIRからのF0、位相増分、振幅倍率、放射と出力段を独立計算に照合した。[事前登録](cases/tsp-fine-source-defaults.json)・[読解と実測](notes/tsp-active-duration-original.md#確認用07で上流既定の音源変動を適用)
- 未達の条件。同じ揺らぎ設定でのブラウザの描画は未照合。全PCMの最大残差は出力フレーム96,435で、内部状態の観測窓より後にある。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIは未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。4回の計測は各8判定と上流・研究版24試験を通過し、要約・PCM・系列など10出力が一致した。省略時の回帰は6判定と7出力の一致を確認した。5実行の717入力・68出力を照合し、採取物61,208,846バイトをRTL9210B-CGへ保存した。[初回](runs/tsp-fine-source-defaults-20261122-a/manifest.json)・[最終再実行](runs/tsp-fine-source-defaults-20261122-final/manifest.json)・[回帰](runs/tsp-fine-initial-tip-20261122-source-defaults-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[確認用07の設定](runs/tsp-fine-source-defaults-20261122-final/artifacts/source-defaults-case.json)と[既存のブラウザ英語発話比較](notes/worklet-english-voice.md)を開く。リポジトリのルートで `rg -n 'renderEnglishVoice|speech_voice|engine_.*score' web/prototypes/chimera-research/src/render-fixed-voice.ts research/experiments/chimera-rebuild/crates/vocal-wasm/src/lib.rs` を実行し、同じ発話設定をWASMへ渡して保存ケースから再演できるか比較する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07のブラウザ読み込みとCLI再演（2026-11-22）

- 完了した項目。英語の発話ケースをブラウザで開き、揺らぎ・舌先・ゲインをWASMに渡して再実行ケースへ保存した。ChromiumのオフラインPCMは元のCLIと保存ケースのCLI再演に全107,527フレームでビット一致した。冒頭440 msの660観測点でCLIとF0・位相・面積・流量・呼気・放射が一致し、90回の位相の折り返しを独立計算へ対応付けた。固定上流との全PCM最大差は `1.16×10⁻¹⁰`。[事前登録](cases/worklet-tsp-source-defaults.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の発話ケースの読み込みと再演)
- 未達の条件。同じ設定での実時間発声開始の時計とPCMは未照合。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIは未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回の確認用07で各10判定、固定上流と研究版の43試験が通過し、要約・ケース・PCM・観測など9出力がバイト一致した。既存回帰の拒否入力 `Strut` は実装済みの /ɹ/ を含むため、初回の停止を保全し、未対応の /ʒ/ を含む `Measure.` へ更新した。修正版は15判定を通過し、既存のPCMなど9出力に一致した。1,090入力・49出力を照合し、採取物103,241,798バイトをRTL9210B-CGへ保存した。[再実行](runs/worklet-tsp-source-defaults-20261122-repeat/manifest.json)・[初回回帰の中断](runs/worklet-english-voice-20261122-tsp-source-defaults-regression/manifest.json)・[第2版の回帰](runs/worklet-english-voice-20261122-tsp-source-defaults-regression-v2/manifest.json)
- 次に開くファイルと実行するコマンド。[保存したブラウザケース](runs/worklet-tsp-source-defaults-20261122-repeat/artifacts/browser-case.json)と[実時間IPAの対照](notes/worklet-live-ipa-cross-browser.md)を開く。リポジトリのルートで `rg -n 'withRealtimeContext|renderRealtimeIpaVoice|renderEnglishVoice|captureWorklet' web/prototypes/chimera-research/src/render-fixed-voice.ts` を実行し、同じ設定で実時間の開始と加工前PCMを観測する条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の実時間発声とContext時計（2026-11-22）

- 完了した項目。読み込んだ英語発話ケースを実時間で再生し、停止できるようにした。ChromiumとFirefoxの各841量子に欠落がなく、全107,527フレームのPCMと発話内3,361観測点がオフライン版と一致した。保存ケースのCLI再演もビット一致した。採取開始は準備完了から2,048フレーム後、最初の非ゼロは両ブラウザとも発話内フレーム2,439。固定上流とのPCM最大差は `1.16×10⁻¹⁰` だった。[事前登録](cases/worklet-live-tsp-source-defaults.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の実時間発声と開始時刻)
- 未達の条件。Firefoxの再実行では `Date.now()` のp99が3 msで、2.667 msの予算を超えた。1 ms刻みのため、ネイティブ時計で個々の量子の長さを照合する。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIは未観測。[計時の記録](runs/worklet-live-tsp-source-defaults-20261122-repeat/summary.json)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。FirefoxでWASMの2回目の応答通知を待って停止した初回を保全した。コンパイルへ渡るバイト列を照合する修正版は2回とも21判定、上流11試験と研究版WASM 27試験を通過し、ケースとPCMなど13出力が一致した。オフラインの回帰は10判定と8出力の一致。1,104入力・66出力を確認し、採取物59,262,298バイトをRTL9210B-CGへ保存した。[初回の中断](runs/worklet-live-tsp-source-defaults-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-source-defaults-20261122-repeat/manifest.json)・[オフラインの回帰](runs/worklet-tsp-source-defaults-20261122-live-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[FirefoxのIPAネイティブ計時](notes/worklet-live-ipa-cross-browser.md#firefoxのネイティブな時計との照合)と[確認用07の量子列](runs/worklet-live-tsp-source-defaults-20261122-repeat/artifacts/firefox/browser.json)を開く。`rg -n 'native_timing|compare_clocks|native_marker' tools/measure_worklet_live_ipa_cross_browser.py tools/measure_worklet_firefox_native_clock.py` を実行し、Firefoxの `WorkletNodeEngine::ProcessBlock` を確認用07の採取量子へ対応付ける条件を先に登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07のFirefoxネイティブ計時（2026-11-22）

- 完了した項目。同一試行のWorklet記録をネイティブの `ProcessBlock` と `CallProcess` に対応付けた。修正後の4試行で定常区間の外側p99は1.680〜1.767 ms。`Date.now()` で超過した20量子はすべてネイティブでは予算内だった。最初の量子は4試行とも3.553〜4.020 msだった。PCM、観測、計画、WASMは通常再生と一致した。[事前登録](cases/worklet-live-tsp-firefox-native-clock.json)・[読解と実測](notes/worklet-english-voice.md#確認用07のfirefoxネイティブ計時)
- 未達の条件。最初の量子の超過はJavaScript呼び出しの中にあり、WASM描画、状態観測、コピーの内訳が未測定。プロファイラーを付けていない過去の試行のネイティブ区間は未取得。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[量子対応表](runs/worklet-live-tsp-firefox-native-clock-20261122-b/artifacts/firefox-2/aligned-quanta.csv)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回は集計JSONの型変換で停止し、両試行のプロファイルと量子表を保全した。修正版は2実行で各13判定、上流11試験が通過した。通常再生の回帰は21判定が通過し、PCMなど12出力が前回の通常再生とバイト一致した。4実行の1,103入力・82出力を照合し、採取物55,558,340バイトをRTL9210B-CGへ保存した。[初回](runs/worklet-live-tsp-firefox-native-clock-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-firefox-native-clock-20261122-repeat/manifest.json)・[回帰](runs/worklet-live-tsp-source-defaults-20261122-native-clock-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[確認用07の量子表](runs/worklet-live-tsp-firefox-native-clock-20261122-b/artifacts/firefox-2/aligned-quanta.csv)と[既存の歌唱計時スクリプト](tools/measure_worklet_live_song_render_phases.py)を開く。リポジトリのルートで `rg -n 'tracedQuanta|render-start|observation-start' web/prototypes/chimera-research/src/fixed-processor.ts` を実行し、最初と定常の量子で処理内訳を比べる条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の先頭量子の処理内訳（2026-11-22）

- 完了した項目。FirefoxでPCMコピー・声門系列転送・状態観測・WASM呼び出しを分けて計時した。先頭量子の時間増分2.273〜2.383 msのうち85.6〜89.8%が `vocal_render` の呼び出しに含まれた。先頭32フレームの呼び出しから定常の同じ位置より長かった。マーカーを入れても保存ケース、PCM、発話状態が通常再生と一致した。[事前登録](cases/worklet-live-tsp-firefox-render-phases.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の先頭量子の処理内訳)
- 未達の条件。WASM内の制御更新とサンプルごとの伝搬を個別に計時する。最初の量子の超過に対して、描画の結果を変えずに使える改善は未検証。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。英語の2実行は各39判定と固定上流11試験を通過した。歌唱の初回回帰は旧基準とのWASMハッシュ照合だけが不合格で、現行WASMの保存基準を明示した再計測は58判定を通過した。4実行の1,115入力・168出力を照合し、採取物79,386,865バイトをRTL9210B-CGへ保存した。[英語の再実行](runs/worklet-live-tsp-firefox-render-phases-20261122-repeat/manifest.json)・[歌唱の初回回帰](runs/worklet-live-song-render-phases-20261122-speech-regression/manifest.json)・[歌唱の再計測](runs/worklet-live-song-render-phases-20261122-speech-current-reference/manifest.json)
- 次に開くファイルと実行するコマンド。[音響コアの制御更新](crates/vocal-core/src/voice.rs#L581)と[WASMの描画入口](crates/vocal-wasm/src/lib.rs#L965)を開く。研究ワークスペースで `rg -n 'step_with_glottal_pressure|begin_tract_block|render_frame|CONTROL_OUTPUT_FRAMES' crates/vocal-core/src/voice.rs crates/vocal-wasm/src/lib.rs` を実行し、制御更新を含む32フレーム区間と隣接する区間に計時点を置く条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07のWASM内の調音制御と気道伝搬（2026-11-22）

- 完了した項目。Firefoxで調音・断面更新と、声門ポート設定・気道伝搬の一部をWASM内部で計時した。4試行の先頭量子でループが定常から1.799〜2.344 ms長くなり、調音・断面更新の割合は24.6〜26.2%だった。半分以上を占めるという予測は成立しなかった。全条件で従来のPCM、発話計画と観測にビット一致した。[事前登録](cases/worklet-live-tsp-firefox-wasm-core-phases.json)・[読解と実測](notes/worklet-english-voice.md#確認用07のwasm内の調音制御と気道伝搬)
- 未達の条件。制御更新以外の1.340〜1.729 msの増分には、気道、声門、間引きなどが含まれる。気道の計時は各量子で8ステップを採った。先頭量子を予算内に収める方法と、その準備にかかる時間は未検証。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと別の作業ディレクトリの各89判定、両ブラウザの通常再生の21判定、固定上流11試験と研究版WASM 27試験が通過した。固定上流との最大PCM差は `1.16×10⁻¹⁰`。3実行の844入力・130出力を照合し、採取物89,349,005バイトをRTL9210B-CGへ保存した。[初回](runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-firefox-wasm-core-phases-20261122-repeat/manifest.json)・[通常再生の回帰](runs/worklet-live-tsp-source-defaults-20261122-wasm-core-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[事前描画のWASMホスト](crates/vocal-wasm/host/fixed-voice.ts#L409)と[実時間の英語発話](../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L232)を開く。リポジトリのルートで `rg -n 'warmupRenderHandle|renderPreparationBlock|renderPreparation|renderRealtimeEnglishVoice' research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice.ts web/prototypes/chimera-research/src/{fixed-processor,render-fixed-voice}.ts` を実行する。準備なし、0フレーム呼び出し、使い捨ての発声器での事前描画を同じ発話で比べ、採取開始、PCM、最初の量子と準備期間の計時条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の先頭量子と事前描画（2026-11-22）

- 完了した項目。準備なし、0フレーム呼び出し、同じ呼び出しに続けた256フレームの事前描画をFirefoxで各6試行実施した。事前描画の先頭量子は1.898〜2.073 msで6件とも予算内だった。全18試行でPCMと発声状態が通常再生に一致し、採取は準備時計の確定から2,048フレーム後、発話内の最初の非ゼロは2,439フレームだった。固定上流との差は最大 `1.16×10⁻¹⁰`。[事前登録](cases/worklet-live-tsp-firefox-render-preparation.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の先頭量子と事前描画)
- 未達の条件。同期の事前描画はWorklet構築の中央値を6.28〜6.38 ms増やし、構築開始から先頭採取量子の完了までを3.37〜3.54 ms延ばした。構築と採取の両方の負担を抑える分割方法、および構築中の機器コールバックと実際の出力は未検証。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2実行の各151判定、通常再生の21判定、固定上流11試験と研究版WASM 27試験が通過した。採取時計と各区間の時間をプロファイルと量子表から再計算した。3実行の853入力・174出力を照合し、採取物118,275,574バイトをRTL9210B-CGへ保存した。[初回](runs/worklet-live-tsp-firefox-render-preparation-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-firefox-render-preparation-20261122-repeat/manifest.json)・[通常再生の回帰](runs/worklet-live-tsp-source-defaults-20261122-render-preparation-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[歌唱の分割準備](notes/worklet-live-song-split-preparation.md)と[Workletの待機処理](../../../web/prototypes/chimera-research/src/fixed-processor.ts#L192)を開く。リポジトリのルートで `rg -n 'advanceRenderPreparation|nextPreparationFrame|stableWasmBuffers|pendingPreparation' web/prototypes/chimera-research/src/{fixed-processor,render-fixed-voice}.ts research/experiments/chimera-rebuild/crates/vocal-wasm/host/fixed-voice.ts` を実行する。同じ256フレームを32フレームずつ待機量子で描画する対照を登録し、本番の観測バッファ、採取開始、最も重い待機量子と先頭量子を照合する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の待機量子に事前描画を分ける（2026-11-22）

- 完了した項目。256フレームを32フレームずつ待機中に描画した。分割6試行で構築が同期条件から中央値で5.67〜5.73 ms短くなった。待機中の最長量子は1.334 ms、先頭の採取量子は最長2.056 ms。全18試行で採取の開始条件、全PCM、発話状態と通常再生が一致し、固定上流のPCMとの差は最大 `1.16×10⁻¹⁰` だった。[事前登録](cases/worklet-live-tsp-firefox-split-preparation.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の待機量子に事前描画を分ける)
- 未達の条件。別ノードを含む共有Contextや機器側の要求とPCMの連続性は、この発話では未観測。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2実行の各157判定、通常再生の21判定、固定上流11試験と研究版WASM 27試験が通過した。分割6試行の48片をプロファイルから再照合し、強制メモリ拡張後の観測ビューの復帰も確認した。3実行の861入力・174出力を照合し、採取物118,322,767バイトをRTL9210B-CGへ保存した。[初回](runs/worklet-live-tsp-firefox-split-preparation-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-firefox-split-preparation-20261122-repeat/manifest.json)・[通常再生の回帰](runs/worklet-live-tsp-source-defaults-20261122-split-preparation-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[歌唱の共有Contextでの分割実測](notes/worklet-live-song-split-preparation.md)と[機器要求の解析](tools/inspect_firefox_cubeb_output.py)を開く。研究ワークスペースで `rg -n 'shared_context_marker|split_preparation_timing|inspect_capture' tools/measure_worklet_live_song_shared_context.py tools/inspect_firefox_cubeb_output.py ../../../web/prototypes/chimera-research/tools/capture-worklet.mjs` を実行する。確認用07を既知の先行PCMが流れるContextで再生し、構築から第8片までの機器要求とPCMを同期条件・分割条件で照合する条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07を共有Contextで機器出力バッファまで照合する（2026-11-22）

- 完了した項目。48 kHzのContextと44.1 kHz出力の組み合わせで、実測した278〜279フレーム要求をグラフの前進と対応付けた。同期描画は6試行とも構築直後に予定時計が256フレーム飛んだ。分割の6試行は構築から第8片まで予算内で、5試行では観測窓全体で時計が連続した。全18試行でcubebの先行PCM、Workletの発話PCMと観測値に不連続や設定差はなかった。[第2版の事前登録](cases/worklet-live-tsp-firefox-device-preparation-v2.json)・[読解と実測](notes/worklet-english-voice.md#確認用07を共有contextで機器出力バッファまで照合する)
- 未達の条件。分割の1試行では採取開始を含む384フレームのグラフ反復で最初の3量子が5.837 msを使い、次の予定時刻が飛んだ。採取開始時に機器要求へ発話量子が集まる条件と、物理出力の連続性は未検証。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[該当する試行](runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/summary.json)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。最初の起動前の中断と固定256フレーム条件の不合格を保存した。可変長条件の2実行で各196判定、通常再生の21判定、固定上流11試験とWASM 27試験が通過した。4実行の1,207入力・413出力を照合し、採取物207,507,660バイトをRTL9210B-CGへ保存した。[起動前の中断](runs/worklet-live-tsp-firefox-device-preparation-20261122-a/failure.json)・[固定長条件](runs/worklet-live-tsp-firefox-device-preparation-20261122-b/manifest.json)・[可変長の再実行](runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/manifest.json)・[通常再生の回帰](runs/worklet-live-tsp-source-defaults-20261122-device-preparation-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[可変長要求の照合](tools/inspect_firefox_cubeb_output.py#L31)と[再実行の発話量子表](runs/worklet-live-tsp-firefox-device-preparation-20261122-v2-repeat/artifacts/2-split/aligned-quanta.csv)を開く。研究ワークスペースで `rg -n 'graph_advance_frames|reference_frame_starts|scheduledContextFrame|first_capture_start_ms' tools/{inspect_firefox_cubeb_output,measure_worklet_live_song_output_callback,measure_worklet_live_tsp_firefox_render_preparation}.py` を実行する。8片の準備を固定し、採取開始が同じ機器要求に入る発話量子数と、1要求の合計時間・時計の飛びの関係を確認するケースを登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の採取開始を1量子ずらす（2026-11-22）

- 完了した項目。事前描画8片を固定し、採取開始を `A + 2,048` と `A + 2,176` で比較した。先頭3量子の1要求への集中は7/8から0/8、要求の予算余裕の中央値は1.47〜1.65 ms増えた。全16試行で先行音は独立計算に、発話PCMと観測値は通常再生に一致した。固定上流とのPCMの最大差は `1.16×10⁻¹⁰`。[事前登録](cases/worklet-live-tsp-firefox-device-onset.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の採取開始を1量子ずらす)
- 未達の条件。従来の開始で予定時刻が256フレーム飛んだ2試行のうち1試行は、コールバックが5.492 msで要求予算5.813 ms以内だった。返却後にどの区間で飛びが生じたかとヘッドフォンでの出力の連続性は未検証。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[再実行の要求別結果](runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/summary.json)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2実行の各185判定、通常再生の21判定、固定上流11試験とWASM 27試験が通過した。16試行で先頭3量子の所属と、528要求の時刻差・先行音を生データから検算した。3実行の905入力・254出力を照合し、採取物132,256,568バイトをRTL9210B-CGへ保存した。[初回](runs/worklet-live-tsp-firefox-device-onset-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/manifest.json)・[通常再生の回帰](runs/worklet-live-tsp-source-defaults-20261122-device-onset-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[音声機器のI/O区間の採取](notes/worklet-live-song-audioipc.md#音声機器のio区間を追加した1組)と[再実行4組目の発話量子表](runs/worklet-live-tsp-firefox-device-onset-20261122-repeat/artifacts/4-split/aligned-quanta.csv)を開く。研究ワークスペースで `rg -n 'audio-hal-client-io-cycle|host_time|scheduled_host_minus_return_ms' tools notes/worklet-live-song-audioipc.md` を実行する。先頭3量子が集まる条件でcubebと音声サーバーのI/O区間を同時に採取し、返却と次の要求時刻を結ぶ条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の出力要求をAudio ClientとAudio Serverへ対応付ける（2026-11-22）

- 完了した項目。現在の外部ヘッドフォンは48 kHz・256フレームの要求だった。8試行でcubebとAudio Client・Audio Serverの8窓を一意に照合した。予定時計が飛んだ7件ではFirefox側の中間I/Oがなく、音声サーバーは連続するサンプル位置へ書き込んでいた。1件はcubebが5.269 ms、FirefoxのI/Oが5.275 msで予算5.333 ms以内だった。全試行で先行音のPCMが連続し、発話PCMと発声状態も通常再生に一致した。[事前登録](cases/worklet-live-tsp-firefox-device-io.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の出力要求をaudio-clientとaudio-serverへ対応付ける)
- 未達の条件。音声サーバーが中間のサンプル位置へ書いたPCMの内容と、FirefoxのI/O要求が飛ぶ条件は未確定。今回の予算内の事例は48 kHzで、先行した44.1 kHz・278〜279フレームの事象との同時採取は残る。人によるTSP・CSD試聴、実録音のF2注釈、物理MIDIも未観測。[再実行のI/O時刻と書き込み位置](runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。同時採取2実行の各97判定、通常再生の21判定、固定上流11試験とWASM 27試験が通過した。元の時刻とサンプル位置から8窓と7件の飛びを検算した。3実行の915入力・1,350出力を照合し、採取物351,992,385バイトをRTL9210B-CGへ保存した。[初回](runs/worklet-live-tsp-firefox-device-io-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-firefox-device-io-20261122-repeat/manifest.json)・[通常再生の回帰](runs/worklet-live-tsp-source-defaults-20261122-device-io-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[歌唱の同時PCM採取](notes/worklet-live-song-paired-output.md)と[予算内で飛んだ試行のサーバー記録](runs/worklet-live-tsp-firefox-device-io-20261122-repeat/artifacts/2-draw/audio-hal-io-cycle-hardware.xml)を開く。研究ワークスペースで `rg -n 'paired-process-tap|inspect_pair|server_write_cycles' tools/{measure_worklet_live_song_shared_context,inspect_firefox_cubeb_output,measure_worklet_tsp_device_io}.py` を実行する。予備の機器設定を確認し、同期描画と分割描画について同じ先行PCMをcubebとプロセスタップで同時に採り、サーバーの中間の書き込み位置に対応するサンプルを調べる条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07のI/OとプロセスタップのPCMを同時に照合する（2026-11-22）

- 完了した項目。通常画面の確認用07で同期描画と分割描画を比較し、同じ試行のcubeb、Audio Client、Audio ServerとFirefoxのプロセスタップを照合した。有効なタップ窓7試行のうち、同期描画4試行で予定時刻が256フレーム飛んだ。無音161フレームは飛びの直前の要求位置にあり、サーバーの中間Writeに対応するタップ側の256フレームには先行音があった。全8試行で発話波形と発声状態が通常再生に一致した。[登録ケース](cases/worklet-live-tsp-firefox-device-tap.json)・[読解、照合、再現コマンド](notes/worklet-english-voice.md#確認用07のio時刻とプロセスタップのpcmを照合する)
- 未達の条件。4件の飛びは5.333 msの予算を超えた。予算内に飛ぶ場合と44.1 kHzの機器要求での同時採取、音声サーバーの全プロセス混合と物理出力、無音の境界を変えた処理段の確認が残る。TSP・CSDの人による試聴、実録音のF2注釈、物理MIDIも未観測。[判定に必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回はタップの準備通知の欠測で116判定中115通過。待機上限を650 msから950 msにして再実行し、123判定が通過した。通常発話の21判定、固定上流11試験とWASM 27試験も通過した。歌唱は以前の基準とのWASMハッシュ差で40判定中39通過と記録し、現行WASMのオフライン基準を取り直して波形と観測の一致を確認した。5実行の1,518入力・1,493出力を照合し、530,490,453バイトをRTL9210B-CGへ保存した。4件の無音位置と256点の波形を生データから検算した。[初回](runs/worklet-live-tsp-firefox-device-tap-20261122-a/manifest.json)・[第2版](runs/worklet-live-tsp-firefox-device-tap-20261122-repeat/manifest.json)・[通常発話の回帰](runs/worklet-live-tsp-source-defaults-20261122-device-tap-regression/manifest.json)・[現行WASMの歌唱基準](runs/worklet-song-voice-20261122-device-tap-reference/manifest.json)
- 次に開くファイルと実行するコマンド。[1量子遅延のケース](cases/worklet-live-tsp-firefox-device-onset.json)と[予算内で飛んだ事例](runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)を開く。研究ワークスペースで `rg -n 'split-late|delay_one_quantum|capture_tap' tools/measure_worklet_live_tsp_firefox_render_preparation.py` を実行する。同じ分割準備の従来開始と1量子遅延を同じタップ採取へ登録し、先頭3量子が同じ要求に入るかと、飛びに対応するタップPCMを比較する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の発話開始を1量子ずらして同時採取する（2026-11-22）

- 完了した項目。48 kHz・256フレーム要求で各4組を2実行した。8組すべてで、1量子遅延により先頭3量子の配分が2＋1から1＋2になった。最も重い要求の予算余裕の中央値は0.717〜0.916 ms増えた。1組では余裕が0.561 ms減った。16試行で通常再生の発話WAV・状態が一致し、cubebとタップの先行音は連続した。[事前登録](cases/worklet-live-tsp-firefox-device-tap-onset.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の発話開始を1量子ずらして出力を同時採取する)
- 未達の条件。16試行の観測窓に予定サンプル時刻の飛びがなく、予算内で飛ぶ場合のPCMは未観測。44.1 kHzでの同時採取、全プロセスの混合波形と機器端子、試聴、録音F2の実注釈、物理MIDIも未観測。[予算内の既存例](runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)・[第7段階に必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回と別ディレクトリからの再実行は各255判定と固定上流11試験を通過した。生PCMとバッファの位置から量子の配分を再計算し、672要求のI/O時刻を検算した。672入力・2,794出力のサイズとハッシュを照合し、650,877,203バイトをRTL9210B-CGへ保存した。[初回](runs/worklet-live-tsp-firefox-device-tap-onset-20261122-a/manifest.json)・[再実行](runs/worklet-live-tsp-firefox-device-tap-onset-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[予算内で飛んだ同期描画の試行](runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)と[前後20要求の採取ケース](cases/worklet-live-tsp-firefox-device-tap-onset.json)を開く。研究ワークスペースで `rg -n 'window_radius_requests|condition_order|reference_io_run' cases/worklet-live-tsp-firefox-device-{io,tap,tap-onset}.json` を実行する。同期描画で過去に出た予算内の飛びを陽性対照にし、同じ範囲で構築直後と発話開始時の飛びをタップPCMまで対応付ける条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07の同期描画で発話開始付近の飛びを採る（2026-11-22）

- 完了した項目。48 kHz・256フレーム要求で、第64量子と第1量子からのタップ起動を各8試行採った。早期起動の7試行で構築位置がタップなしの24,576フレームまで戻った。16件の構築直後の飛びでは局所比較が全件で直前の要求位置を選び、161〜162点の完全ゼロを数えた。中間Writeに対応するタップ側の先行音はcubebの波形と相対RMS残差0.76〜0.91%で一致した。[局所比較と実測](notes/worklet-english-voice.md#確認用07の同期描画で発話開始付近の飛びを採る)
- 未達の条件。16試行で発話開始付近の飛びは0件で、予算内の飛びが発生した時点のタップPCMは未観測。タップの有無と先行音の形によるWorklet時間の差が残る。44.1 kHzでの同時採取、全プロセスの混合波形と機器端子、実録音のF2注釈、人によるTSP・CSD試聴と物理MIDIも未確認。[予算内の既存例](runs/worklet-live-tsp-firefox-device-io-20261122-repeat/summary.json)・[第7段階に必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2実行は各256判定と上流11試験を通過した。発話WAVは全16試行で通常再生とバイト一致した。672要求の生時刻と挿入位置を再計算し、673入力・2,794出力のサイズとハッシュを照合した。採取物669,232,343バイトはRTL9210B-CGに保存した。[第64量子起動](runs/worklet-live-tsp-firefox-device-tap-draw-20261122-a/manifest.json)・[第1量子起動](runs/worklet-live-tsp-firefox-device-tap-draw-early-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[先行音の待機処理](../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs)と[早期起動の結果](runs/worklet-live-tsp-firefox-device-tap-draw-early-20261122-a/summary.json)を開く。研究ワークスペースで `rg -n 'waitForSystemTrace|trace_attach_quanta|capture_tap' tools/measure_worklet_tsp_device_tap.py ../../../web/prototypes/chimera-research/tools/shared-context-marker.mjs` を実行する。滑らかな先行音と構築位置をそろえたままタップの有無を切り替え、先頭2量子のWorklet時間、cubeb、Audio Clientの順に差を比較する条件を登録する。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07のタップ対照と予算内の飛びを照合する（2026-11-22）

- 完了した項目。先行音前に準備を始め、タップの有無を比べる全4組で構築位置を24,576フレームにそろえた。先頭2量子のWASMの対応差の中央値は+0.041 ms。各段で短くなった組と長くなった組が各2組だった。タップ付きの第2・4組で予算内に返却した後に予定時刻が飛んだ2件を同時採取し、直前の要求に対応するタップPCMで完全ゼロ161フレーム、中間Writeに対応する位置で先行音の復帰を確認した。[登録と実測](notes/worklet-english-voice.md#確認用07の同期描画でタップの有無を比較する)
- 未達の条件。FirefoxのクライアントI/Oが次の周期に起動しなかった仕組みと、全プロセス混合後や出力機器端子のPCMの確認が残る。44.1 kHzでの同時採取、実録音のF2注釈、人によるTSP・CSD試聴、物理MIDIは未観測。[第7段階の観測範囲](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回は1組が構築位置を満たし、先行音前から準備するケースは4組すべてが満たした。2実行の各244判定、固定上流の各11試験が通過し、16試行の発話WAVが通常再生と一致した。生時刻の672要求と予算内の2件の局所PCMを検算し、677入力・2,754出力のハッシュとサイズを照合した。記録した668,214,246バイトはRTL9210B-CGに保存した。[初回](runs/worklet-live-tsp-firefox-device-tap-draw-control-20261122-a/manifest.json)・[先行音前の依頼](runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[予算内の第2組のAudio Client](runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/artifacts/2-tap/audio-hal-client-io-cycle.xml)と[第4組のAudio Server](runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/artifacts/4-tap/audio-hal-io-cycle-hardware.xml)を開く。研究ワークスペースで `jq '.tap_draw.gaps[] | select(.includes_onset)' runs/worklet-live-tsp-firefox-device-tap-draw-control-early-20261122-a/summary.json` を実行する。飛んだ2件と同じ実行で飛ばなかった要求を、I/Oの起動・返却・Writeの同じ時刻軸に置き、返却から次のクライアント起動予定までの区間を調べる。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07のサーバー周期とFirefoxのIOProcの欠落を照合する（2026-11-22）

- 完了した項目。8試行・24要求を同じI/O時刻軸へ置いた。予算内で飛んだ2件では、前のFirefox I/Oは次のサーバー処理開始より207.5 µs、58.5 µs先に終わった。欠けた周期にもサーバーのClient StartとWriteがあり、同じFirefox I/OスレッドのIOProcは見つからなかった。[時刻軸と予測](cases/worklet-live-tsp-firefox-io-deadline.json)・[生データとClient Startの比較](notes/worklet-english-voice.md#確認用07で次のfirefox-ioが飛んだ周期を照合する)
- 未達の条件。サーバーのClient StartからFirefoxのIOProcまでの通知、起床、実行開始の区間は未観測。予算内の第2組の既存収録にMachのスケジューラ記録はなかった。全プロセス混合後および機器端子、44.1 kHzでの同時採取、実録音のF2注釈、人による試聴、物理MIDIも未確認。[観測範囲](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。時刻軸の2実行は各56判定を通過し、要約と時刻表がバイト一致した。Client StartとIOProcの抽出は24判定を通過した。51件の開始時刻と欠けた3周期のIOProcを生XMLから再計算し、1,341入力・23出力のサイズとハッシュを照合した。追加抽出したトレース表はRTL9210B-CGへ保存した。[時刻軸の実行](runs/worklet-live-tsp-firefox-io-deadline-20261122-repeat/manifest.json)・[Client Startの実行](runs/worklet-live-tsp-firefox-io-client-start-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[予算内で飛んだ周期の対応表](runs/worklet-live-tsp-firefox-io-client-start-20261122-a/artifacts/client-start-slots.csv)と[System Traceの起動処理](tools/capture_worklet_system_pair.py)を開く。 `/usr/bin/xcrun xctrace list instruments | rg 'Audio Client|Audio Server|Thread State Trace'` で収録器を確認する。各周期のFirefox I/Oスレッドの実行可能化と実行開始を記録する条件を登録し、飛んだ周期と連続する周期で並べる。試聴回答を受領した場合は[取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を使う。

## TSP確認用07でFirefoxのI/Oスレッド状態を照合する（2026-11-22）

- 完了した項目。再生前にThread State Traceを開始し、4試行のうち3試行で出力窓を照合した。構築直後に予算を超えて256フレーム飛んだ3件では、前のI/Oが次のサーバー開始を2.305〜2.892 ms越えた。同じ実行区間がI/O終了後も2.542〜3.625 µs続き、以後2.159〜2.691 msは待機だった。欠けた3周期のIOProcは0回で、発話開始付近の連続する9周期には各1回あった。[条件と実測](notes/worklet-english-voice.md#確認用07で欠けた周期のfirefox-ioスレッドの状態を読む)・[12周期の詳細](runs/worklet-live-tsp-firefox-io-thread-state-20261122-continuations/summary.json)
- 未達の条件。再生前収録の第2試行は発話開始のI/Oが欠測。予算超過で欠けた3周期のサーバー実測開始間隔は4.998〜5.055 msで、予定5.333 msとの許容差0.100 msを外れた。予算内で飛んだ既存2件のスレッド状態は未観測。全プロセス混合後、機器端子、44.1 kHzでの同時採取、実録音F2、人による試聴、物理MIDIも未確認。[欠測と判定](runs/worklet-live-tsp-firefox-io-thread-state-20261122-continuations/summary.json)・[第7段階の観測範囲](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。最初の6試行、タップ準備後の4試行、再生前の4試行の採取条件と欠測を保存した。再生前の4試行は発話WAVと発声状態が通常再生に一致し、固定上流11試験を通過した。第2版の状態判定を保持し、第3版は同じXMLを参照して前の実行の末尾を区別した。生XMLから12周期の状態とIOProcを独立に照合し、時刻軸の回帰は旧要約とバイト一致した。7実行の2,321入力・5,403出力のサイズとハッシュを照合した。大容量の採取物はRTL9210B-CGに置いた。[初回収録](runs/worklet-live-tsp-firefox-io-thread-state-capture-20261122-a/manifest.json)・[タップ準備後](runs/worklet-live-tsp-firefox-io-thread-state-capture-gated-20261122-a/manifest.json)・[再生前](runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-20261122-a/manifest.json)・[第2版](runs/worklet-live-tsp-firefox-io-thread-state-20261122-preplay/manifest.json)・[第3版](runs/worklet-live-tsp-firefox-io-thread-state-20261122-continuations/manifest.json)・[時刻軸の回帰](runs/worklet-live-tsp-firefox-io-deadline-20261122-thread-state-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[再生前収録のケース](cases/worklet-live-tsp-firefox-io-thread-state-capture-preplay.json)と[試行ごとのI/O行](runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-20261122-a/summary.json)を開く。研究ワークスペースで `jq '.trials[] | {pair, onset: .device_onset_requests, client_rows: .system_io.client_pid_cycles}' runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-20261122-a/summary.json` を実行する。先行音を80量子から56量子に短縮する条件を別ケースに登録し、採取末尾と発話開始の時刻差を再測定する。予算内で飛んだ場合に、前のI/Oの終了から次の周期のRunnable、Running、IOProcを同じ時計で照合する。

## TSP確認用07の先行音を短縮して収録末尾を比較する（2026-11-22）

- 完了した項目。80量子の既存4試行と56量子の新規6試行を比較し、構築位置が全試行で10,240から7,168フレームへ64 ms前進することを確認した。全窓の照合は80量子が3/4、56量子が1/6。56量子では全6試行で音声I/Oの3表が最大5.058 ms以内に途切れ、目次上のトレース期間よりも前だった。[事前登録](cases/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の先行音を56量子にしてioの収録範囲を測る)
- 未達の条件。56量子の5試行は発話開始直前までにAudio Client行が途切れ、同じ基準で試した局所窓も欠測。予算内の発話開始で予定が飛ぶ場合のスレッド状態は未観測。全窓を照合した第6試行でも構築直後に欠けた周期のサーバー開始間隔が0.100 msの許容差を外れた。[判定と欠測](runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-cutoffs/summary.json)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。56量子の全6試行で発話WAVと発声状態は通常再生に一致し、固定上流11試験が通過した。生XMLから4周期のスレッド状態とIOProc、音声I/O各表の末尾を独立に照合した。前版の判定と、参照収録3試行での局所窓と全窓の対応を再確認した。採取物と抽出XMLの実体はRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q-20261122-a/manifest.json)・[第1版](runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-a/manifest.json)・[末尾を追加した第2版](runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-cutoffs/manifest.json)・[従来解析の再実行](runs/worklet-live-tsp-firefox-io-thread-state-20261122-local-window-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[56量子の収録ケース](cases/worklet-live-tsp-firefox-io-thread-state-capture-preplay-56q.json)と[第2版の集計](runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-cutoffs/summary.json)を開く。研究ワークスペースで `jq '.trials[] | {pair, acquisition: .acquisition}' runs/worklet-live-tsp-firefox-io-thread-state-preplay-56q-20261122-cutoffs/summary.json` を実行する。56量子でThread State Traceの有無だけを切り替える条件を登録し、Audio Client、Audio Server、機器Writeの末尾が同じ入出力の発話開始を覆うか比べる。

## TSP確認用07のThread State Trace併用と収録末尾を比較する（2026-11-22）

- 完了した項目。56量子・1秒で4組を交互に収録した。音声I/Oのみでは全窓4/4、併用では全窓0/4、発話開始の局所窓1/4。構築位置が一致した2組では、音声I/Oのみの条件で発話開始までの余裕が511.523〜812.966 ms増えた。併用で照合できた局所窓の2周期には各1回のIOProcと実行区間があった。[収録と比較](notes/worklet-english-voice.md#確認用07でthread-state-traceの有無を比較する)・[組内の結果](runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-followup/summary.json)
- 未達の条件。第3組の併用条件は構築が128フレーム、第4組の音声I/Oのみの条件は256フレーム遅れ、構築位置がそろった4組での判定は保留した。予算内で発話開始のI/Oが飛んだときのスレッド状態は未観測。音声I/O表が早く終わる内部要因も未特定。[登録条件](cases/worklet-live-tsp-firefox-trace-instruments-56q.json)・[初版の判定](runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-cutoffs/summary.json)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。8試行で通常再生との発話WAVおよび発声状態の一致、固定上流との差と11試験を確認した。生XMLとcubebの生時刻から4組の差、全8試行の3表の末尾、局所窓の2周期を独立に照合し、保存済みの予算内の飛び2件を再検出した。3実行の1,791入力・2,064出力をサイズとハッシュで照合し、大容量成果をRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-a/manifest.json)・[初版](runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-cutoffs/manifest.json)・[追加抽出](runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-followup/manifest.json)
- 次に開くファイルと実行するコマンド。[収録器の切替ケース](cases/worklet-live-tsp-firefox-trace-instruments-56q.json)、[追加抽出](runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-followup/summary.json)、[トレース起動](tools/capture_worklet_system_pair.py#L56)を開く。研究ワークスペースで `/usr/bin/xcrun xctrace help record | rg -- '--window'` と `jq '.paired' runs/worklet-live-tsp-firefox-trace-instruments-56q-20261122-followup/summary.json` を実行する。1秒の全プロセス収録で3収録器を維持し、`--window 900ms` の有無を変える条件を登録する。今回の8試行では末尾900 msの起点が全窓の最初の要求より159.7 ms以上早かった。保持窓を有効にした収録で、実際に残る音声I/Oと状態を照合する。

## TSP確認用07の終了前900 msの保持窓を比較する（2026-11-22）

- 完了した項目。3収録器・先行音56量子で4組を採取した。900 msを指定した4試行では19.525〜34.204 msが保持され、Writeの絶対ホスト時刻からは保持区間が発話開始より463.049〜497.968 ms後に始まっていた。保持窓なしは音声I/Oと状態の全窓2/4、保持窓ありは0/4だった。[実測と時計の検算](notes/worklet-english-voice.md#確認用07で終了前900-msの保持窓を比較する)・[両条件の全結果](runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-write-clock/summary.json)
- 未達の条件。保持窓ありの目次の起点はWriteから求めた起点と1.345〜1.363秒ずれた。登録した2 ms以内の時計で4組を評価できないため、収録余裕の差の判定は保留した。予算内で発話開始のI/Oが飛んだときの状態、全プロセス混合後や機器端子のPCM、44.1 kHz、実録音F2、人による試聴と物理MIDIは未確認。[初版](runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-coverage/summary.json)・[時計の検算後](runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-write-clock/summary.json)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。8試行の発話WAV・状態と固定上流11試験を照合した。生XMLとcubebの生時刻からWriteの時計換算、Audio Serverの同一予定ホスト時刻、発話入口を独立に検算した。3実行の5,031入力・2,930出力をサイズとハッシュで照合し、採取物はRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-a/manifest.json)・[初版解析](runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-coverage/manifest.json)・[時計の検算](runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-write-clock/manifest.json)
- 次に開くファイルと実行するコマンド。[トレース起動処理](tools/capture_worklet_system_pair.py#L56)、[FirefoxのPID取得](tools/measure_worklet_live_song_process_tap.py#L271)、[時計の検算](runs/worklet-live-tsp-firefox-retained-trace-window-56q-20261122-write-clock/summary.json)を開く。研究ワークスペースで `/usr/bin/xcrun xctrace help record | rg -- '--attach|--all-processes'` を実行する。先行音56量子・1秒・3収録器を固定し、全プロセスとFirefoxへの `--attach` を比較する条件を登録する。Firefoxと音声サーバーの関連行、機器Write、ステート表のすべてが照合できるかを判定する。

## TSP確認用07で全プロセス収録とFirefoxへのアタッチを比較する（2026-11-22）

- 完了した項目。3収録器で4組を採り、アタッチした全4試行にAudio Server、機器Write、Thread Stateの表があることを確認した。発話開始で3表と状態を同時に照合できた全窓は全プロセス0/4、アタッチ1/4。第2組のアタッチ条件で予定位置が256フレームずつ進む同じ機器ストリームと、2周期のIOProcを照合した。[比較の読解と実測](notes/worklet-english-voice.md#確認用07で計測用firefoxへのアタッチを比較する)・[全試行の判定](runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-coverage/summary.json)
- 未達の条件。第3組のアタッチ条件は機器Writeの末尾がDarwin開始通知とFirefoxの最初のデータ要求より早く、FirefoxのAudio Client行が欠測した。登録した4組での判定と、予算内で発話開始のI/Oが飛んだときのスレッド状態は未確認。全プロセス混合後や機器端子のPCM、44.1 kHz、実録音F2、人による試聴、物理MIDIも残る。[欠測と時刻](runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-coverage/summary.json)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。8試行の発話WAVと発声状態が通常再生に一致し、固定上流の11試験が通過した。生XMLからPID、組内差、対象の機器Writeとスレッド状態の2周期を独立に照合した。状態表の行数と実測された末尾を再集計し、新しい状態行の開始と音声I/Oの終了が全8試行で1機器周期以内にあることを確認した。4実行の7,124入力・2,611出力をサイズとハッシュで照合した。採取物はRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-a/manifest.json)・[同時照合](runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-coverage/manifest.json)・[状態表の集計](runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-state-scope/manifest.json)・[状態行の開始時刻を加えた集計](runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-state-scope-late-rows/manifest.json)
- 次に開くファイルと実行するコマンド。[記録開始の待機処理](tools/capture_worklet_system_pair.py)、[音声収録の開始処理](tools/measure_worklet_tsp_device_io.py#L47)、[アタッチの比較結果](runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-coverage/summary.json)を開く。研究ワークスペースで `jq '.trials[] | {pair, condition, acquisition}' runs/worklet-live-tsp-firefox-attached-trace-56q-20261122-coverage/summary.json` を実行する。同じ収録の標準出力の開始行とDarwin通知を単調時計で取り、Firefoxの最初のデータ要求と音声I/Oの末尾を並べる。二つの通知の順序を確認してから、再生ゲートの時点を切り替える対照条件を登録する。

## TSP確認用07の開始通知を測って再生時点を早める（2026-11-22）

- 完了した項目。同じ単調時計で比較した4試行で、開始行の受信はDarwin通知に639.943〜1,550.192 ms先行した。ゲート200 msの別ケースでは実測200.843 msと201.065 msで再生を許可した。先行条件の2試行でAudio Clientが83行と91行あり、第2組の要求13でAudio Client・Audio Server・機器Writeを照合した。[通知の比較](runs/worklet-live-tsp-firefox-trace-start-signals-56q-20261122-timing/summary.json)・[再生時点の変更と照合](runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage-onset-edges/summary.json)
- 未達の条件。200 ms条件では発話開始の要求12が両試行で収録の前端より早く、全窓と局所窓の同時照合は0/2だった。対照2試行はFirefoxのAudio Client行が欠測しており、2組の収録余裕の差は判定を保留した。予算内で飛んだ要求のスレッド状態は未観測。[事前登録した判定](runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage/summary.json)・[前端の検算](runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage-onset-edges/summary.json)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。8試行で発話WAVと発声状態が通常再生と一致し、各収録で固定上流11試験を通過した。通知の差、機器時計の起点、200 msゲートの時刻、要求13のサーバー予定位置と機器Writeを独立に照合した。5実行の2,647入力と2,292出力をサイズとハッシュで照合した。採取物はRTL9210B-CGに保存した。[同時観測の収録](runs/worklet-live-tsp-firefox-trace-start-signals-56q-20261122-a/manifest.json)・[通知の集計](runs/worklet-live-tsp-firefox-trace-start-signals-56q-20261122-timing/manifest.json)・[200 ms対照の収録](runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-a/manifest.json)・[初版解析](runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage/manifest.json)・[前端の検算](runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage-onset-edges/manifest.json)
- 次に開くファイルと実行するコマンド。[200 msのケース](cases/worklet-live-tsp-firefox-stdout-release-200ms.json)、[前端の検算](runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage-onset-edges/summary.json)、[再生ゲート](tools/capture_worklet_system_pair.py)を開く。研究ワークスペースで `jq '.trials[] | {pair,condition,onset_overlap_audit}' runs/worklet-live-tsp-firefox-stdout-release-200ms-20261122-coverage-onset-edges/summary.json` を実行する。物理時計で換算した共通範囲は開始行から約438〜632 msなので、500 ms条件を別ケースへ事前登録し、Darwin対照と同時に採る。生データで前端を合わせ、発話開始2要求でAudio Client、Audio Server、機器Write、スレッド状態の各表を照合する。

## TSP確認用07の開始行から500 ms後に再生する（2026-11-22）

- 完了した項目。500 ms条件の3試行すべてでcubeb・Audio Client・Audio Serverの全窓を照合し、発話開始の2要求で機器Write、スレッド状態、IOProcを対応付けた。Darwin条件は1試行で発話開始の局所窓を照合できた。比較できた2組でAudio Client末尾までの余裕は298.517 msと487.882 ms増えた。[事前登録](cases/worklet-live-tsp-firefox-stdout-release-500ms.json)・[読解、判定、検算](notes/worklet-english-voice.md#確認用07で開始行から500-ms後に再生を許可する)
- 未達の条件。第3組のDarwin条件にはFirefoxのAudio Client行がなく、3組での予測判定は保留した。今回は発話開始に予定時刻の飛びがなく、予算内で飛ぶ要求のスレッド状態は未観測。44.1 kHzの機器要求、物理出力、試聴、実録音のF2注釈、物理MIDIも未観測。[比較の全判定](runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-coverage/summary.json)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。全6試行で発話WAVと発声状態が通常再生に一致し、固定上流11試験を通過した。生データから音声サーバーと機器Writeの時計、発話開始後の状態周期を独立に照合した。1,928入力・1,674出力のサイズとハッシュを検証し、326,056,889バイトの出力をRTL9210B-CGに保存した。[収録のマニフェスト](runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-a/manifest.json)・[解析のマニフェスト](runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-coverage/manifest.json)
- 次に開くファイルと実行するコマンド。[破棄描画の準備と再生開始](../../../web/prototypes/chimera-research/src/fixed-processor.ts#L203)と[500 ms条件の要求12・13](runs/worklet-live-tsp-firefox-stdout-release-500ms-20261122-coverage/summary.json)を開く。研究ワークスペースで `rg -n 'hasPendingRenderPreparation|advanceRenderPreparation|firstQuantumOffset' ../../../web/prototypes/chimera-research/src` を実行する。通常再生のPCMを固定し、発話最初の量子と同じ機器要求に入る準備描画だけを調整できるかを確認する。要求12の処理時間と、終了から次のサーバー周期開始までの間隔を過去の予算内の飛びと比較する。

## TSP確認用07の最初の発話要求に最後の破棄描画を移す（2026-11-22）

- 完了した項目。通常画面から明示的に指定した調査条件で、最後の64フレームの破棄描画を要求7から最初の発話と同じ要求12へ移した。全6試行で発話PCMと状態は通常再生に一致した。照合できた2組でAudio Client区間は0.782 msと0.863 ms延び、次周期までの余裕は0.759 msと0.870 ms縮んだ。[登録ケース](cases/worklet-live-tsp-firefox-onset-load-64.json)・[読解と結果](notes/worklet-english-voice.md#確認用07の最初の機器要求に最後の破棄描画を移す)
- 未達の条件。第2組の発話直前条件は機器時計で発話入口の127.876 ms前にAudio Clientの記録が終わり、全体の実行判定は不合格。2組の計測では次の周期まで2.287〜2.444 msあり、発話の予定時刻の飛びは全6試行で起きなかった。予算内で飛んだ要求のスレッド状態、44.1 kHzの機器要求、物理出力、試聴、実録音のF2注釈、物理MIDIは未観測。[欠測を含む判定](runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage-verified/summary.json)・[第7段階の未確認項目](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。固定上流11試験とViteビルドが通過。生データを使い、準備描画の要求位置、機器Write、10周期のスレッド状態、Audio Client末尾から次周期開始までの差を独立に照合した。従来の500 ms対Darwinの集計も保存済みのデータから再計算し、保存要約との一致を確認した。収録と2解析の2,255入力・1,644出力をサイズとハッシュで検証し、329,017,181バイトの出力をRTL9210B-CGへ保存した。[収録](runs/worklet-live-tsp-firefox-onset-load-64-20261122-a/manifest.json)・[初版解析](runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage/manifest.json)・[機器時計で検算した解析](runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage-verified/manifest.json)
- 次に開くファイルと実行するコマンド。[破棄用ハンドルの描画](crates/vocal-wasm/host/fixed-voice.ts#L430)と[64フレームの結果](runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage-verified/summary.json)を開く。研究ワークスペースで `jq '.trials[] | {pair,condition,first_request}' runs/worklet-live-tsp-firefox-onset-load-64-20261122-coverage-verified/summary.json` を実行する。発話直前の配置と先行3片を固定し、最後の片だけ224フレームに増やすケースを登録する。要求12の所要時間、予算までの余裕、次周期のスレッド状態を64フレームの条件と比較する。

## TSP確認用07の発話直前の破棄描画を224フレームに増やす（2026-11-22）

- 完了した項目。最後の描画片だけ64から224フレームへ増やした。第1組の224フレーム条件でcubebが約5.054 ms、Audio Clientが約5.065 msで処理を終えた後、予定時刻が256フレーム飛んだ。機器Writeが続いた周期の約5.081 msを通じて対象FirefoxのI/OスレッドはBlockedで、IOProcは0件。次のサーバー周期でRunnable、Running、IOProcを観測した。[登録ケース](cases/worklet-live-tsp-firefox-onset-load-224.json)・[読解と実測](notes/worklet-english-voice.md#確認用07の発話直前の破棄描画を224フレームに増やす)
- 未達の条件。登録済みの窓で比較できたのは第3組で、2組以上を必要とする主判定は保留。要求10〜15の補足窓で第1組を照合した。飛んだ周期のスレッド状態は調査用の負荷を加えた1件で取得し、負荷を加えない事例での状態、OS通知、タップと物理出力の波形、44.1 kHzの同時採取、試聴、実録音のF2注釈、物理MIDIが残る。[主判定](runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage/summary.json)・[補足窓の判定](runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/summary.json)
- 最後に確認した実行。全6試行で通常再生とのWAV・状態一致、固定上流11試験、Viteビルドを確認。生データから256フレームの飛び、機器Write、10周期のスレッド状態を独立に照合した。旧64フレームの配置比較は生データで保存済み判定を再現した。収録と2解析の2,486入力・1,630出力をサイズとハッシュで照合し、350,241,550バイトをRTL9210B-CGへ保存した。[収録](runs/worklet-live-tsp-firefox-onset-load-224-20261122-a/manifest.json)・[登録窓の解析](runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage/manifest.json)・[補足窓の解析](runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/manifest.json)
- 次に開くファイルと実行するコマンド。[タップ採取の入口](tools/measure_worklet_tsp_device_tap.py#L66)と[今回の飛びと状態](runs/worklet-live-tsp-firefox-onset-load-224-20261122-coverage-local/summary.json)を開く。研究ワークスペースで `rg -n 'trace_before_playback|collect_tap|tap_attach_quanta' tools/measure_worklet_live_tsp_firefox_render_preparation.py tools/measure_worklet_tsp_device_tap.py tools/capture_worklet_system_pair.py` を実行する。224フレームの発話と機器要求を固定し、Firefoxのプロセスタップが音声I/Oと同時に成立する開始順序を確かめる。飛びが出た場合は先行音の位置を機器Writeに対応させる。

## TSP確認用07の224フレーム条件でプロセスタップを併用する（2026-11-22）

- 完了した項目。発話前に無音Contextを開いてFirefox親PIDのタップを準備し、システム収録の開始後に無音Contextを閉じて発話を始めた。全6試行で要求12・13のタップPCM、機器Write、スレッド状態を照合した。第5試行は局所窓で照合した。[修正版のケース](cases/worklet-live-tsp-firefox-onset-load-224-tap-prime.json)・[読解と結果](notes/worklet-english-voice.md#確認用07の224フレーム条件でプロセスタップを併用する)
- 未達の条件。無音Contextを開かない初回は6試行ともタップ起動前に停止した。修正版の6試行に発話開始の予定時刻の飛びはなく、予算内で飛んだ周期のタップPCMは未観測。物理出力のPCM、44.1 kHzの同時収録、試聴、実録音のF2注釈、物理MIDIも残る。[初回](runs/worklet-live-tsp-firefox-onset-load-224-tap-20261122-a/summary.json)・[修正後の判定](runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/summary.json)
- 最後に確認した実行。通常再生の発話WAV・状態と固定上流11試験を全6試行で確認。生のステレオPCMの両端、機器Write、12周期のスレッド状態とIOProcを独立に照合した。既存の飛び2件で機器Writeに対応するPCMを再計算し、保存済みの結果を再現した。2,111入力・1,610出力をサイズとハッシュで確認し、330,786,804バイトをRTL9210B-CGへ保存した。[初回の収録](runs/worklet-live-tsp-firefox-onset-load-224-tap-20261122-a/manifest.json)・[修正版の収録](runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-a/manifest.json)・[解析](runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/manifest.json)
- 次に開くファイルと実行するコマンド。[発話の診断条件](../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L243)と[同時収録のケース](cases/worklet-live-tsp-firefox-onset-load-224-tap-prime.json)を開く。研究ワークスペースで `jq '.trials[] | {pair,alignment_scope,onset_requests}' runs/worklet-live-tsp-firefox-onset-load-224-tap-prime-20261122-coverage/summary.json` を実行する。同じ無音Contextとタップの開始順、500 msゲート、先行3片を固定し、最後の片だけ256フレームへ増やす。実時間予算とサンプル時刻を測り、飛んだ周期があればPCMを機器Writeへ対応させる。

## TSP確認用07のプロセスタップ併用で最後の破棄描画を256フレームに増やす（2026-11-22）

- 完了した項目。全6試行で発話開始時の要求12に最後の256フレームの破棄描画が入り、cubeb処理は4.723〜5.015 msだった。5試行で5.333 msの予算まで0.5 ms以内になった。全試行でタップPCMと発話開始のスレッド状態を照合した。[事前登録](cases/worklet-live-tsp-firefox-onset-load-256-tap-prime.json)・[読解と実測](notes/worklet-english-voice.md#確認用07のタップ付き条件で最後の破棄描画を256フレームに増やす)
- 未達の条件。発話開始で予定時刻が飛ぶ事例は今回も未観測。登録済みの機器Writeの結合では第2試行の次周期が別のサーバースレッドだったため、全体の判定は不合格。補足ではサンプル位置・予定ホスト時刻・エンジンとストリームを照合し、機器Writeを確認した。予算内の飛びのPCM、物理出力、44.1 kHzの同時収録、試聴、実録音のF2注釈、物理MIDIは未観測。[登録判定](runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/summary.json)・[別スレッドの補足照合](runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage-write-threads-verified/summary.json)
- 最後に確認した実行。全6試行で通常再生の発話WAVと発声状態、固定上流11試験、Viteビルドを確認した。生のタップPCMとcubebの先行音、12周期のIOProcとスレッド状態、同じ機器ストリームのWriteを独立に照合した。224フレームのタップ付き解析の要約も再現した。収録と3解析の2,058入力・1,564出力をサイズとハッシュで検証し、323,321,988バイトをRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-a/manifest.json)・[登録窓解析](runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/manifest.json)・[別スレッドの補足初版](runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage-write-threads/manifest.json)・[補足窓の検算](runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage-write-threads-verified/manifest.json)
- 次に開くファイルと実行するコマンド。[発話直前の診断設定](../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L243)と[256フレーム条件の結果](runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/summary.json)を開く。研究ワークスペースで `jq '.trials[] | {pair,onset_requests,write_check:.onset_device_write_error}' runs/worklet-live-tsp-firefox-onset-load-256-tap-prime-20261122-coverage/summary.json` を実行する。最後の破棄描画だけ320フレームに増やして要求12を5.333 msへ近づけ、飛びが出た場合は機器WriteとタップPCMを照合する。

## TSP確認用07のプロセスタップ併用で最後の破棄描画を320フレームに増やす（2026-11-22）

- 完了した項目。全6試行で要求12は5.441〜5.705 msかかり、予算を超えた後に予定時刻が256フレーム飛んだ。無音挿入モデルは全6試行で直前の要求位置を選び、機器Writeまで照合した5試行では飛んだ周期に対応するタップPCMに先行音が残った。5試行の同じ周期のFirefoxのI/OスレッドはBlockedでIOProcがなかった。[事前登録](cases/worklet-live-tsp-firefox-onset-load-320-tap-prime.json)・[読解と実測](notes/worklet-english-voice.md#確認用07で最後の破棄描画を320フレームに増やす)
- 未達の条件。第3試行は発話前にAudio Clientの記録が終わり、波形のみ補足で照合した。全試行の照合は不合格のまま。予算内で飛んだ周期のタップPCM、物理出力、44.1 kHzの同時収録、試聴、実録音のF2注釈、物理MIDIは未観測。[登録判定](runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage/summary.json)・[第3試行を含むPCMの補足](runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json)
- 最後に確認した実行。通常再生とのWAV・発声状態一致、Viteビルド、固定上流11試験を通過。生PCMから無音区間と残差を再計算し、機器Write、スレッド状態とIOProcを独立に照合した。256フレームのタップ付き解析も保存要約と一致した。2,146入力・1,571出力をサイズとハッシュで検証し、321,613,795バイトの出力をRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-a/manifest.json)・[解析](runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage/manifest.json)・[PCMの補足解析](runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/manifest.json)
- 次に開くファイルと実行するコマンド。[発話の診断設定](../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L243)と[320フレーム条件の結果](runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json)を開く。研究ワークスペースで `jq '.trials[] | {pair,onset_requests,covered_onset_gaps}' runs/worklet-live-tsp-firefox-onset-load-320-tap-prime-20261122-coverage-pcm-review/summary.json` を実行する。500 msゲートとタップの開始順を維持して最後の片だけ288フレームにし、5.333 msの予算内の飛びが生じた場合にタップの無音位置と機器Writeを照合する。

## TSP確認用07の288フレーム条件で予算内の飛びとタップPCMを照合する（2026-11-22）

- 完了した項目。全6試行で発話開始の要求の後に予定時刻が256フレーム飛んだ。cubebとAudio Clientがともに5.333 msの予算内だった2件では、飛んだ周期にIOProcがなく、タップで同じ先行音の256フレームが2回続き、2つ目は機器Writeに対応した。予算超過の4件では無音挿入モデルが選ばれた。[事前登録](cases/worklet-live-tsp-firefox-onset-load-288-tap-prime.json)・[読解と実測](notes/worklet-english-voice.md#確認用07で最後の破棄描画を288フレームにする)
- 未達の条件。事前登録の無音モデルは予算内の2件で残差が約0.405となり、予測を支持しなかった。事後の反復モデルは残差約0.0085で一致した。2件の該当区間の同相成分は0だった。発話成分のある反復区間、OS通知、物理出力、44.1 kHzの同時収録、試聴、実録音のF2注釈、物理MIDIが未観測。[登録判定](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-coverage/summary.json)・[事後比較](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-repetition/summary.json)
- 最後に確認した実行。収録・登録の解析・事後比較が通過。全6試行の発話WAVと状態が通常再生に一致し、Viteビルドと固定上流11試験を確認した。生データから機器Write、スレッド状態とIOProc、先行音の反復位置とモデルの残差を独立に照合した。1,807入力・1,571出力をサイズとハッシュで検証し、342,635,895バイトをRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-a/manifest.json)・[解析](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-coverage/manifest.json)・[事後比較](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-repetition/manifest.json)
- 次に開くファイルと実行するコマンド。[先行音とタップの照合](tools/measure_worklet_tsp_device_tap.py#L171)と[反復モデルの実装](tools/measure_worklet_tsp_tap_gap_repetition.py#L20)を開く。研究ワークスペースで `jq '.events[] | {trial,within_budget,selected,stereo_blocks}' runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-20261122-repetition/summary.json` を実行する。同じ採取手順で非ゼロの同相成分を加える対照を登録し、次の機器Writeに対応する区間で両成分の反復を測る。

## TSP確認用07で同相と逆相の反復を照合する（2026-11-22）

- 完了した項目。288フレーム条件に独立した同相信号を加え、両成分をcubebとタップの生PCMで別々に照合した。全6試行で要求12の後に256フレーム飛んだ。第4・第5試行では両成分とも256フレームの反復を示し、2回目が機器Writeに対応した。ほか4試行では両成分で無音挿入が選ばれた。[事前登録](cases/worklet-live-tsp-firefox-onset-load-288-tap-prime-common.json)・[読解と実測](notes/worklet-english-voice.md#確認用07に同相の試験信号を加えて反復を調べる)
- 未達の条件。予算内の第1試行で無音挿入、第5試行で反復が観測され、予算内の全試行で反復する予測は不支持。第1・第4試行は元の窓の先頭が一意に合わず、登録判定の不合格を保存した。補足では開始点を3,072フレーム後ろへ移して両試行を照合した。OS通知、発話成分が重なる区間、物理出力、44.1 kHzの同時収録、試聴、実録音のF2注釈、物理MIDIは未観測。[登録窓](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-coverage/summary.json)・[6試行の判定](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition-trim/summary.json)
- 最後に確認した実行。全6試行の通常再生WAV・発声状態・固定上流PCM、Viteビルド、固定上流11試験を確認した。生PCMから同相信号、両モデルの残差、反復位置と機器Writeの対応を独立に検算した。収録と3解析の1,863入力・1,580出力をサイズとハッシュで検証し、326,617,043バイトをRTL9210B-CGに保存した。[収録](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-a/manifest.json)・[登録窓解析](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-coverage/manifest.json)・[反復比較](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition/manifest.json)・[補足解析](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition-trim/manifest.json)
- 次に開くファイルと実行するコマンド。[トレースの解析](tools/measure_worklet_tsp_io_trace_instruments.py)と[補足照合](runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition-trim/summary.json)を開く。研究ワークスペースで `jq '.events[] | {trial,within_budget,selected,second_block_matches_device_write}' runs/worklet-live-tsp-firefox-onset-load-288-tap-prime-common-20261122-repetition-trim/summary.json` を実行する。同相なしの288フレームと320フレームの保存トレースを加え、飛んだ周期の予定ホスト時刻を起点にAudio Client終了・Audio Server開始・機器Writeを並べて、PCMの形態と照合する。

## TSP確認用07の欠落周期を機器Writeの時計で比較する（2026-11-22）

- 完了した項目。保存済みの288・320フレーム条件の18試行でPCM判定を確認し、17試行のcubeb、Audio Client、Audio Server、機器Writeを欠落周期の予定ホスト時刻へそろえた。Client終了からWriteまでの間隔は反復121.459〜460.917 µs、無音挿入12.167〜319.084 µsで重なった。Audio ServerがClient終了前に始まった2試行でも、Writeは終了後だった。[事前登録](cases/worklet-live-tsp-firefox-onset-gap-write-timing.json)・[読解と実測](notes/worklet-english-voice.md#確認用07で予定時刻と機器writeを三つの収録条件で比べる)
- 未達の条件。主指標と、終点を実測サーバー開始・予定ホスト時刻に替えた指標のどれも全条件では波形を分けられなかった。320フレームの第3試行はPCMを確認し、音声I/O時刻は欠測のまま保持した。OS通知、物理出力、44.1 kHzの同時収録、試聴、実録音のF2注釈、物理MIDIが未観測。[試行ごとの判定](runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/summary.json)
- 最後に確認した実行。CLIが通過し、別計算でcubeb CSVとAudio Client・Audio Server・機器WriteのXMLを読み直して17試行の時刻を1 ns以内で再現した。18件のPCM判定、153入力・2出力のサイズとハッシュを確認し、20,263バイトの比較結果をRTL9210B-CGに保存した。[実行記録](runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/manifest.json)・[試行ごとの時刻表](runs/worklet-live-tsp-firefox-onset-gap-write-timing-20261122-a/artifacts/timing.csv)
- 次に開くファイルと実行するコマンド。[44.1 kHz機器での先行収録](cases/worklet-live-tsp-firefox-device-preparation-v2.json)と[タップの校正を読む処理](tools/measure_worklet_tsp_device_tap.py#L26)を開く。`/usr/sbin/system_profiler SPAudioDataType -detailLevel mini` で機器を確認し、現在44.1 kHzで接続されている外部ヘッドフォンを候補に、Context、タップ、機器それぞれのレートと要求幅を校正ケースで確かめる。

## 44.1 kHzでヘッドフォンとプロセスタップを校正する（2026-11-22）

- 完了した項目。SafariのContext、ヘッドフォン、プロセスタップのレートが両試行で44.1 kHzだった。Workletは128フレーム、機器とタップは512フレームで、逆相の試験信号を各40,960フレーム連続して照合した。校正中に選んだ出力先を元へ戻した。[事前登録](cases/safari-process-tap-smooth-marker-44100.json)・[読解と実測](notes/worklet-english-voice.md#441-khzのヘッドフォンでプロセスタップを校正する)
- 未達の条件。機器とタップが256フレームという事前予測は外れ、両試行の512フレームをそのまま保存した。同じレート・出力先のFirefoxでは、cubebの実際の要求幅、機器Writeとの対応、確認用07の発話開始は未観測。物理出力、試聴、実録音のF2注釈、物理MIDIも未観測。[幅の予測の判定](runs/safari-process-tap-smooth-marker-44100-20261122-repeat/summary.json)
- 最後に確認した実行。44.1 kHzの2回と既存48 kHzの回帰が通過した。別計算でグラフPCM、タップの位相とホスト時計を再現した。59入力・55出力をサイズとハッシュで検証し、2,216,940バイトをRTL9210B-CGに保存した。[初回](runs/safari-process-tap-smooth-marker-44100-20261122-a/manifest.json)・[再実行](runs/safari-process-tap-smooth-marker-44100-20261122-repeat/manifest.json)・[48 kHz回帰](runs/safari-process-tap-smooth-marker-20261122-output-device-regression/manifest.json)
- 次に開くファイルと実行するコマンド。[Firefoxの要求と先行音の照合](tools/measure_worklet_tsp_device_preparation.py#L17)、[タップの校正を読む処理](tools/measure_worklet_tsp_device_tap.py#L26)、[先行の可変長要求ケース](cases/worklet-live-tsp-firefox-device-preparation-v2.json)を開く。研究ワークスペースで `../../.venv/bin/python tools/measure_worklet_live_tsp_firefox_render_preparation.py --help` を実行し、44.1 kHzのFirefoxで既知信号とcubebの要求を採る入口を確認する。同じヘッドフォンの公称レートと合わせ、実測した幅に基づいてタップ・書込みとの照合を登録する。

## Firefoxで44.1 kHzのcubeb要求と機器Writeを照合する（2026-11-22）

- 完了した項目。44.1 kHzも採取するFirefox計測版をビルドし、128フレームのWorklet、256フレームのcubebとヘッドフォンへのWrite、512フレームのタップを測った。無音と試験音に別のContextを使い、試験音のcubeb PCMを採取した。機器のサンプル番号で、各試行のWrite64件をタップ波形と照合した。[読解と実測](notes/worklet-english-voice.md#firefoxで441-khzのcubeb要求とヘッドフォンへのwriteを照合する)・[補足結果](runs/firefox-process-tap-sample-clock-44100-20261122-repeat/summary.json)
- 未達の条件。第1版は最初の試験で要約の型変換に失敗し、再解析と再収録では収録枠が無音で埋まった。第2版のホスト時刻による照合の両端差は約44 µsで、登録判定は2回とも不合格だった。判定を維持し、別のケースでサンプル番号による補足を通した。確認用07の44.1 kHzでの発話開始と負荷による欠落、物理出力、試聴、実録音のF2注釈、物理MIDIは未観測。[第1版の再解析](runs/firefox-process-tap-cubeb-write-44100-20261122-replay/summary.json)・[第2版の登録結果](runs/firefox-process-tap-cubeb-write-44100-separate-prime-20261122-a/summary.json)・[補足のケース](cases/firefox-process-tap-sample-clock-44100.json)
- 最後に確認した実行。第2版の2収録と後続2解析で、元のトレースXMLからAudio Client・ヘッドフォンへのWrite・両PCMを独立に照合した。採取後に既定出力を戻し、従来版XULのSHA-256を確認した。全7実行の186入力・655出力をサイズとハッシュで検証し、98,488,864バイトの出力をRTL9210B-CGに保存した。[収録](runs/firefox-process-tap-cubeb-write-44100-separate-prime-20261122-repeat/manifest.json)・[補足解析](runs/firefox-process-tap-sample-clock-44100-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[発話のブラウザ用ケース](cases/worklet-live-tsp-source-defaults.json)と[固定発声の44.1 kHzの先行実行](runs/worklet-rate-44100-20261120-d/summary.json)、[発話の計時と同時収録の入口](tools/measure_worklet_live_tsp_firefox_render_preparation.py)を開く。研究ワークスペースで `jq '{longest_joint_writes,verification_anchors}' runs/firefox-process-tap-sample-clock-44100-20261122-repeat/summary.json` を実行する。確認用07の発話を44.1 kHzでCLIとWorkletに通し、そのPCM・状態を基準に、発話開始の256フレーム要求とタップの512フレームブロックを照合する。

## 確認用07の44.1 kHz発話と機器Writeを照合する（2026-11-22）

- 完了した項目。CLI、オフラインWorklet、実時間Workletの98,790フレームと共有観測が一致した。最初の非ゼロは上流も含めて2,247フレームだった。外部ヘッドフォンのcubebとWriteは256フレーム、タップは512フレーム。左右平均によるRMS開始点は2,923フレームで両経路が一致し、250 msの初回と400 msの収録では、最初の非ゼロ点とRMS開始点を別々のWriteへ照合した。[実測と読解](notes/worklet-english-voice.md#確認用07を441-khzで再生して発話開始を照合する)・[400 msの照合](runs/worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a/summary.json)
- 未達の条件。250 msの再収録では、窓前端を短くした補足でPCMを回復した。トレースに最初の非ゼロ点のAudio Server行はなく欠測として残した。通常の発話開始では予定時計の飛びはなく、44.1 kHzで負荷を掛けた場合の欠落周期の波形は未観測。物理出力、試聴、実録音のF2注釈、物理MIDIも未観測。[再収録の登録判定](runs/worklet-live-tsp-44100-headphone-onset-20261122-repeat/summary.json)・[短縮窓の判定](runs/worklet-live-tsp-44100-headphone-onset-20261122-repeat-review/summary.json)
- 最後に確認した実行。独立にRIFF、WAV、既知信号の相関位置、トレースXMLを再計算して一致した。上流の発話・エンジン試験とViteビルドが通過した。6実行の1,460入力・534出力をサイズとハッシュで確認し、132,151,804バイトをRTL9210B-CGへ保存した。収録後は元の内蔵スピーカーへ復元した。[通常再生](runs/worklet-live-tsp-44100-20261122-a/manifest.json)・[250 msの初回](runs/worklet-live-tsp-44100-headphone-onset-20261122-a/manifest.json)・[400 msでの再収録](runs/worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[400 msの収録ケース](cases/worklet-live-tsp-44100-headphone-onset-gate-400ms.json)と[48 kHzでの288フレーム負荷](cases/worklet-live-tsp-firefox-onset-load-288-tap-prime-common.json)を開く。研究ワークスペースで `jq '.onset_device_writes | map_values(map({cubeb_index,frames,server_sample_time}))' runs/worklet-live-tsp-44100-headphone-onset-gate-400ms-20261122-a/summary.json` を実行する。無負荷の発話と、最後の破棄描画を加えた発話を同じ44.1 kHz機器で比べ、5.805 msを前後する要求の時計、タップPCM、機器Writeを照合する。

## 44.1 kHzで破棄描画と発話を同じ要求に入れて比較する（2026-11-22）

- 完了した項目。288・416フレームの破棄描画を含む8収録で、通常の発話PCM・発声状態を再現した。破棄描画と最初の発話量子を1要求にまとめると、288条件は2回とも予算内。416条件は2回とも予算超過し、1回で予定時刻とタップの長さに292フレームの差が生じた。同試行に512フレームの機器Writeと293フレームのタップ無音区間があった。[読解と実測](notes/worklet-english-voice.md#441-khzで発話直前の描画負荷を比較する)・[生ファイルの補足照合](runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json)
- 未達の条件。最初の比較は別々の機器要求で処理され、416条件も予算内だった。同一要求にした416条件の登録照合では、どちらも遅いWriteを結べず欠測。補足でAudio Clientと機器Writeを確認した。292フレームの飛びの局所PCMは、無音・反復モデルのいずれも許容残差内にならなかった。タップ無音の前後の処理、512フレームのWriteの再現頻度と物理出力は未確認。[飛びの登録結果](runs/worklet-live-tsp-44100-headphone-load-same-request-20261122-2/summary.json)・[予算超過でも飛びなしの登録結果](runs/worklet-live-tsp-44100-headphone-load-same-request-20261122-3/summary.json)・[補足の事前登録](cases/worklet-live-tsp-44100-headphone-late-write-review.json)
- 最後に確認した実行。Viteビルド、WASMの分割描画試験、生PCMの相関、Audio Clientと機器Writeの時刻、局所モデルの最小二乗残差を確認した。9実行の1,372入力と1,373出力をサイズとハッシュで検証し、273,099,049バイトをRTL9210B-CGへ保存した。[同一要求の実行記録](runs/worklet-live-tsp-44100-headphone-load-same-request-20261122-4/manifest.json)・[補足解析の再現手順](runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[同一要求とする比較ケース](cases/worklet-live-tsp-44100-headphone-load-same-request.json)と[遅いWriteの解析](tools/measure_worklet_tsp_44100_late_write.py)を開く。研究ワークスペースで `jq '.trials | map_values({timing,writes_inside_scheduled_gap,gap_pcm})' runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json` を実行する。416条件で過負荷後の機器Writeの幅と予定時計、タップの無音前後の波形を追加収録し、512フレームのWriteと292フレームの飛びが再び対応するか検証する。


## 44.1 kHzで416フレームの破棄描画を6回再収録する（2026-11-22）

- 完了した項目。6回すべてで最後の破棄描画を要求内の位置0、発話開始を128に置き、同じ発話WAVと状態を得た。cubebは6.110〜6.715 ms、Audio Clientは6.119〜6.748 msで、全回で予算の5.805 msを超えた。1回で飛び・512フレームのWrite・タップの無音を再現し、5回は予定番号が連続した。同じ収録の後続の予算内要求でも316フレーム飛び、同じ形のWriteと無音を確認した。[事前登録](cases/worklet-live-tsp-44100-headphone-load-416-repeat.json)・[読解と実測](notes/worklet-english-voice.md#同じ416フレーム負荷を441-khzで6回繰り返す)
- 未達の条件。収録時の判定では5回が遅いWrite、1回がタップの前側アンカーで不合格。前者は生XML、後者は前端だけ256フレーム短い窓で照合し、元の判定を保存した。局所の単一挿入モデルは今回の2箇所の飛びには適用しなかった。無音前後の波形変化の由来、機器Writeの標本値、アナログ出力は未確認。[元の集約](runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-analysis-v2/summary.json)・[短い窓での第3試行](runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-3-trim-256/summary.json)・[照合後の判定](runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/summary.json)
- 最後に確認した実行。時刻、ヘッドフォンWriteの幅とサンプル番号、完全ゼロの区間をCSV・XML・PCMから検算した。上流のエンジン6試験と再実装の分割描画1試験が通過し、従来解析は元の要約とバイト一致。11実行の1,698入力と1,033出力をサイズとSHA-256で検証し、192,913,814バイトの出力をRTL9210B-CGに記録した。既定出力は内蔵スピーカーへ復元した。[最終実行のマニフェスト](runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/manifest.json)
- 次に開くファイルと実行するコマンド。[飛びの集約処理](tools/measure_worklet_tsp_44100_load_repeat.py)と[前回の292フレームの局所比較](runs/worklet-live-tsp-44100-headphone-late-write-review-20261122-a/summary.json)を開く。研究ワークスペースで `jq '.trials[] | {target_gap_frames, pcm: (.pcm | {stereo_zero_spans,wide_write_windows,other_gaps,continuous_residuals})}' runs/worklet-live-tsp-44100-headphone-load-416-repeat-20261122-verified/summary.json` を実行する。292・308・316フレームの3件と連続した第2試行で、無音開始・終了の前後64フレームのマーカーの位置と、同相・逆相の残差を別々に測る。


## 44.1 kHzの無音前後を64フレームで照合する（2026-11-22）

- 完了した項目。292・308・316フレームの3件と連続対照2箇所で、遠方のラグ差が予定番号の飛びと整数フレームで一致した。無音直前は両成分の残差0.000043以下。直後64フレームでは0.801〜0.903に増え、128フレーム先は0.000044以下に戻った。292と308の飛びは、出口から128フレームのPCMがcubebとタップの各観測点で同じだった。[事前登録](cases/worklet-live-tsp-44100-headphone-gap-edges.json)・[読解と実測](notes/worklet-english-voice.md#441-khzタップの無音前後を64フレームで照合する)
- 未達の条件。第1版の単独窓では飛び2件と対照1箇所で逆相マーカーが定値で、位置は欠測。128・256フレーム先を連結した補足で回復し、元の不合格は保持した。316フレームの飛びは逆相から同相を予測したときの残差が0.0391で0.025を超えた。共通ゲインの適用範囲、波形処理の発生段、アナログ出力は未確定。[元の判定](runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-a/summary.json)・[補足のケース](cases/worklet-live-tsp-44100-headphone-gap-edges-joint-anchor.json)・[補足の結果](runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/summary.json)
- 最後に確認した実行。3収録の生CSVとPCMで時刻差、無音端、成分別のラグと比例残差を独立計算した。上流のエンジン6試験と分割描画1試験が通過。補足の集約は合格し、元の不合格判定を再現した。3解析の67入力と3出力をサイズとSHA-256で照合し、出力159,678バイトをRTL9210B-CGに記録した。[補足のマニフェスト](runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/manifest.json)・[第1版の再実行](runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-original-recheck/manifest.json)
- 次に開くファイルと実行するコマンド。[境界解析](tools/measure_worklet_tsp_44100_gap_edges.py)を開き、研究ワークスペースで `jq '.captures[].request_records[] | {gap_frames,after: .after.near_cross_gain_at_far_lag}' runs/worklet-live-tsp-44100-headphone-gap-edges-20261122-joint/summary.json` を実行する。292フレーム側から推定した標本ごとの係数を固定し、既知マーカーの波形が違う316フレーム側の同相・逆相PCMを予測する。連続した対照と比較し、係数だけで再現できない最初の標本を特定する。


## 44.1 kHzの無音出口で固定ゲインを検証する（2026-11-22）

- 完了した項目。292フレームの飛びから推定したゲインを316フレーム側へ固定適用した。無音直後の相対残差は同相0.01171、逆相0.01804。共通ゲインを推定できた64点で誤差10⁻⁵を最初に超えた位置は同相22、逆相28。cubebがゼロでもタップが10⁻⁶を超えた標本を3件すべてで確認し、同じcubeb波形の連続対照と対応づけた。[事前登録](cases/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer.json)・[読解と実測](notes/worklet-english-voice.md#441-khz無音出口のゲインを別の波形へ適用する)
- 未達の条件。316で相対残差が0.025を超える予測は不成立。292の位置23のゲインは推定できず、転用比較では欠測。第1版は完全無音の内側の前64フレームをゲイン1の回復判定に含めていた。補足で前方はタップの完全ゼロ、後方はゲイン1の回復をそれぞれ検査した。元の不合格と測定値は保存した。波形処理の発生段とアナログ出力は未確定。[第1版の結果](runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-a/summary.json)・[ゼロ入力の補足](runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/summary.json)
- 最後に確認した実行。生PCMとCSVからラグ・残差・誤差が出る最初と最後の標本を再計算した。上流のエンジン6試験と再実装の分割描画1試験が通過。2解析の55入力と4出力をサイズとSHA-256で検証し、出力573,415バイトをRTL9210B-CGに記録した。[補足のマニフェスト](runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/manifest.json)
- 次に開くファイルと実行するコマンド。[固定ゲイン実装](tools/measure_worklet_tsp_44100_edge_gain_transfer.py)と[全標本のCSV](runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/artifacts/edge-samples.csv)を開く。研究ワークスペースで `jq '.zero_input_comparisons | map_values(map(select(.exceeds_control_floor)))' runs/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer-20261122-zero-control/summary.json` を実行する。隣接するcubeb標本を使う線形モデルを片方の信号で求め、係数を固定して別の成分と316側のゼロ入力位置を予測する。同じ波形の292と308は独立の波形として数えず、行列の階数から識別できる係数を確認する。


## 44.1 kHzの無音出口を対称FIRで照合する（2026-11-22）

- 完了した項目。292の同相成分から求めたゲートは無音終了後の位置47で、3件とも次のcubeb要求のPCM先頭と一致した。全候補の行列は列フルランク。33・65係数の両方式が登録基準に合格し、ゲート後全体を65係数で処理した場合、316の残差は両成分約0.00685%、ゼロ入力4標本の最大絶対誤差は3.21×10⁻⁸だった。[事前登録](cases/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit.json)・[読解と実測](notes/worklet-english-voice.md#441-khzの無音出口を隣接標本から予測する)
- 未達の条件。17係数以下はゼロ入力4点の基準を満たさなかった。連続対照でも全波形にFIRを適用した方が残差が小さかったが、19,845 Hz付近への減衰の直接測定、OS内の適用段、アナログ出力は未確認。初回は解析関数の余分な引数で失敗し、別IDでやり直した。[初回のマニフェスト](runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-a/manifest.json)・[候補と連続対照](runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/summary.json)
- 最後に確認した実行。直接畳み込みとピボット付きQRで係数と残差を再計算し、元のcubeb CSVでゲート位置を照合した。上流のエンジン6試験と再実装の分割描画1試験が通過した。入力16件、出力1件をサイズとSHA-256で確認し、65,664バイトの出力をRTL9210B-CGに記録した。[合格した実行のマニフェスト](runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/manifest.json)
- 次に開くファイルと実行するコマンド。[FIR推定の入口](tools/measure_worklet_tsp_44100_edge_neighbor_fit.py)と[44.1 kHzの連続マーカー](cases/worklet-live-tsp-44100-headphone-load-416-repeat.json)を開く。研究ワークスペースで `jq '.models["filter_gated_pcm/32"] | {center_coefficient,positive_offset_coefficients,relative_residuals_and_absolute_errors}' runs/worklet-live-tsp-44100-headphone-gap-edge-neighbor-fit-20261122-b/summary.json` を実行する。44.1 kHzの連続な既知音で17,640・19,845・20,947.5 Hzをcubebとタップに通し、推定した係数を固定したまま振幅比・位相を照合する。


## 44.1 kHzのタップの帯域を連続音で直接測る（2026-11-22）

- 完了した項目。2収録の定常29小窓で、17,640・19,845・20,947.5 Hzのタップ/cubeb振幅比が1.00000・0.50000・0.01635となり、固定FIRの予測に一致した。2,205 Hz基準の補正後の最大位相差は0.000116°。各収録の対象窓でcubebは256幅の104要求、タップは512幅の53ブロックを数え、予定サンプル時刻は連続だった。[事前登録](cases/firefox-process-tap-headphone-response-44100.json)・[読解と実測](notes/worklet-english-voice.md#441-khzの連続音でタップの周波数応答を測る)
- 未達の条件。第1版は後マーカーの分数位相の影響で、第1試行は位相、第2試行は窓の照合が不合格。補足では同じ生データを1,000フレーム窓で再解析し、定常性の条件を外れた第2試行の最後の3小窓を保存した。位置22,736からタップが変わり、19,845 Hzは後半で0.01575〜0.01578に低下した。変化と分数位相の傾きの因果、処理の適用段、物理出力は未確定。[第1版の判定](runs/firefox-process-tap-headphone-response-44100-20261122-1/summary.json)・[補足条件](cases/firefox-process-tap-headphone-response-44100-pilot-review.json)・[変動を含む補足](runs/firefox-process-tap-headphone-response-44100-20261122-2-pilot-review/summary.json)
- 最後に確認した実行。元のステレオPCMの実FFTで全32小窓の振幅・位相・残差を検算した。2試行のWorkletのPCMと、時刻の連続性も確認。上流のエンジン6試験、再実装の分割描画1試験、計測ページの構文確認が通過した。4実行の122入力と54出力をサイズとSHA-256で検証し、5,139,824バイトをRTL9210B-CGへ記録した。既定出力は内蔵スピーカーへ復元した。[補足のマニフェスト](runs/firefox-process-tap-headphone-response-44100-20261122-2-pilot-review/manifest.json)
- 次に開くファイルと実行するコマンド。[連続音の収録と解析](tools/measure_firefox_headphone_response_44100.py)を開き、研究ワークスペースで `jq '.windows[] | {source_frames,stationary,phase_correction_frames,frequencies:[.frequencies[]|{hz,amplitude_ratio}]}' runs/firefox-process-tap-headphone-response-44100-20261122-2-pilot-review/summary.json` を実行する。同じ4周波数を長く再生して、帯域と低域位相の傾きが変化する前後を連続した小窓で追い、cubebとタップのブロック時刻に対応づける。


## 44.1 kHzのタップの帯域とホスト時計の変化を追う（2026-11-22）

- 完了した項目。純音区間を約1.11秒に延ばした3試行すべてで19,845 Hzの振幅比が約0.5から約0.0155へ低下した。2試行で位相の変化と帯域低下を同じ小窓で検出。1試行では位相が負に動き始めてから331.07 ms後に帯域が低下した。各試行のcubeb224要求・タップ113ブロックで予定サンプル番号は連続した。[事前登録](cases/firefox-process-tap-headphone-drift-44100.json)・[読解と実測](notes/worklet-english-voice.md#441-khzの連続音を延ばして帯域と位相の変化を追う)
- 未達の条件。最初の変化が毎回512フレーム以内にそろう予測は1試行で不成立。時計の補足比較では8区間中6区間の傾きが0.033 ppm以内で一致したが、末尾2区間は0.705・0.791 ppmと基準0.5 ppmを超えた。プログラム内の原因の箇所と物理出力は未計測。[2つの変化が離れた試行](runs/firefox-process-tap-headphone-drift-44100-20261122-1/summary.json)・[時計比較の補足条件](cases/firefox-process-tap-headphone-drift-44100-clock-plateaus.json)・[補足の結果](runs/firefox-process-tap-headphone-drift-44100-clock-plateaus-20261122-b/summary.json)
- 最後に確認した実行。生PCMから全687窓を実FFTで検算し、波形の最初の差と対応するブロック時刻を再計算した。ホスト時計差の補足は別の直線回帰で一致を確認した。上流6試験と再実装1試験、および計測ページの構文検査が通過。4実行の87入力・79出力をサイズとSHA-256で照合し、出力8,570,304バイトをRTL9210B-CGへ記録した。既定出力を内蔵スピーカーに復元した。[第3試行のマニフェスト](runs/firefox-process-tap-headphone-drift-44100-20261122-3/manifest.json)・[補足のマニフェスト](runs/firefox-process-tap-headphone-drift-44100-clock-plateaus-20261122-b/manifest.json)
- 次に開くファイルと実行するコマンド。[ネイティブcubebの出力プローブ](tools/chimera-cubeb-output-probe.rs)と[ネイティブの同時収録](tools/measure_cubeb_output_process_tap.py)を開く。研究ワークスペースで `jq '.trials | map_values(map({band,source_window_centers,pilot_slope_ppm,host_difference_ppm}))' runs/firefox-process-tap-headphone-drift-44100-clock-plateaus-20261122-b/summary.json` を実行する。同じヘッドフォン、44.1 kHz、256フレーム幅にそろえて4周波数の連続音をネイティブcubebから出力し、ホスト時計差の符号と19,845 Hzの振幅比を比較する。


## 44.1 kHzの帯域変化をネイティブcubebで照合する（2026-11-22）

- 完了した項目。同じ外部ヘッドフォンでブラウザのPCM61,440フレームをネイティブcubebから出力し、3試行の左右のPCMがビット一致。220のcubeb要求と111のタップブロックの予定番号は連続し、幅はそれぞれ256と512だった。3回とも19,845 Hzの比が0.50000から約0.01574へ低下し、位相の変化は同じ小窓。立ち上がり後の6区間のホスト時計差とPCM位相の傾きの差は0.02735 ppm以内だった。[事前登録](cases/native-cubeb-headphone-drift-44100.json)・[読解と実測](notes/worklet-english-voice.md#441-khzの帯域変化をネイティブcubebで比較する)
- 未達の条件。旧ビルドは48 kHz専用の記録条件でcubeb PCMが欠測。44.1 kHzの別ビルドで採取した3回も、試験音を反復する境界が後マーカー窓に入り、当初の判定は不合格。後窓を1,024フレーム前へ移した再解析で照合し、元の6回の結果を残した。Core Audio内の作用箇所とアナログの出力は未確定。[旧ビルドの結果](runs/native-cubeb-headphone-drift-44100-20261122-1/summary.json)・[44.1 kHz収録の元の結果](runs/native-cubeb-headphone-drift-44100-20261122-snapshot-1/summary.json)・[採取済みPCMの再解析](runs/native-cubeb-headphone-drift-44100-20261122-snapshot-1-tail-review-verified/summary.json)
- 最後に確認した実行。生のFloat32とCSVから全687小窓の実FFT、cubebのビット一致、時計の連続性と傾きを独立に検算した。上流エンジン6試験と再実装の分割描画1試験が通過。10実行の367入力・103出力をサイズとSHA-256で検証し、12,643,531バイトの出力をRTL9210B-CGに保存した。既定出力は内蔵スピーカーへ復元した。[時計の照合](runs/native-cubeb-headphone-drift-44100-clock-plateaus-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[Core Audioの直接出力プローブ](tools/chimera_output_deadline_probe.swift)と[プロセスタップの同時採取](tools/measure_coreaudio_output_error_pcm.py)を開き、研究ワークスペースで `jq '.trials | map_values(map({band,median_band_amplitude_ratio,pilot_slope_ppm,host_difference_ppm,error_ppm}))' runs/native-cubeb-headphone-drift-44100-clock-plateaus-20261122-a/summary.json` を実行する。同じヘッドフォンに同じ44.1 kHzのPCMをCore Audioの直接出力コールバックから送り、cubebを経由する場合の帯域・位相・時計と照合する。

## 44.1 kHzの帯域変化をCore Audioの直接出力で照合する（2026-11-22）

- 完了した項目。44.1 kHzの同じPCMをCore Audioの `DefaultOutput` へ渡し、出力要求とプロセスタップを3回同時に採取した。全試行で入力61,440フレームの左右がビット一致し、予定標本番号が連続した。直接出力とタップの幅は512フレーム。19,845 Hzの振幅比は0.50000から0.01573〜0.01574へ低下し、正の位相傾斜を同じ窓の中心27,216で検出した。6区間の位相傾斜とホスト時計差の誤差は最大0.08192 ppm。波形の差は同じフレーム27,088で始まり、次の直接出力要求の48フレーム手前だった。[読解と結果](notes/worklet-english-voice.md#441-khzの帯域変化をcore-audioの直接出力で比較する)・[全試行の時計](runs/coreaudio-headphone-drift-44100-clock-plateaus-20261122-a/summary.json)
- 未達の条件。初版の3収録は、Float64へ変換済みの配列を使ったビット照合だけが不合格だった。元の生PCMを使い、初版の判定を保持して補足で全件を検証した。Core Audio内のどの段で帯域が変わるかと、ヘッドフォンのアナログ出力は未確認。[初版](runs/coreaudio-headphone-drift-44100-20261122-1/summary.json)・[再解析](runs/coreaudio-headphone-drift-44100-20261122-1-review/summary.json)
- 最後に確認した実行。生PCMのビットと全687小窓の実FFT、直接出力とタップの予定標本番号、6区間のホスト時計を独立に検算した。固定上流のエンジン6試験と再実装の分割描画1試験が通過。従来のネイティブcubeb時計集約の要約はバイト一致した。8実行の254入力・59出力のハッシュを確認し、音声、時刻、ビルドの実体は計7,370,257バイトをRTL9210B-CGへ保存した。出力は内蔵スピーカーへ復元した。[時計比較の実行](runs/coreaudio-headphone-drift-44100-clock-plateaus-20261122-a/manifest.json)・[従来ケースの再実行](runs/native-cubeb-headphone-drift-44100-clock-plateaus-20261122-coreaudio-regression/summary.json)
- 次に開くファイルと実行するコマンド。[直接出力の収録と解析](tools/measure_coreaudio_headphone_drift_44100.py)と[登録した基準ケース](cases/coreaudio-headphone-drift-44100.json)を開く。研究ワークスペースで `jq '.events | map_values({source_frame, direct: .direct.frames_after_block_start, tap: .tap.frames_after_block_start})' runs/coreaudio-headphone-drift-44100-20261122-1-review/summary.json` を実行する。同じPCMの前へ1,024フレームの無音を挿入するケースを登録し、差の開始が出力開始からの標本番号と信号開始のどちらに追従するか照合する。

## 44.1 kHzの試験音前の無音で帯域変化の時刻を照合する（2026-11-22）

- 完了した項目。先頭の無音0・1,024フレームを3組採取し、全6回の入力PCM、予定標本番号、512フレーム幅を照合した。波形差は全6回で出力フレーム27,088から観測された。無音ありでは試験信号先頭からの位置が1,024フレーム早まった。帯域が狭い区間では振幅比が約0.01573、回復後は約0.49976。位相とホスト時計差は12区間で最大0.05213 ppmの差だった。[登録ケース](cases/coreaudio-headphone-drift-44100-leading-silence.json)・[集約](runs/coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-a/summary.json)
- 未達の条件。切替を決めたCore Audio内の処理段とアナログ出力は未確認。タップ起動と出力起動の間隔も同時に大きく変える対照は未測定。帯域と位相の検出窓は出力基準で24フレーム異なるが、先頭無音による窓の配置のずれと同じ幅で、測定窓の分解能は200フレーム刻みだった。[座標と比較区間](notes/worklet-english-voice.md#441-khzの試験音の前に無音を挿入する)
- 最後に確認した実行。生PCMのビット、1,374窓の実FFT、最初に変わる標本と区間の時計を独立に検算した。従来の直接出力3回を保存データから解析し直し、既存の結果と一致した。上流のエンジン6試験と再実装の分割描画1試験が通過。7実行の218入力と109出力を照合し、出力実体14,752,741バイトをRTL9210B-CGへ保存した。既定出力は内蔵スピーカーへ復元した。[マニフェスト](runs/coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[タップの準備と出力開始](tools/measure_coreaudio_output_error_pcm.py)と[直接出力の計測](tools/measure_coreaudio_headphone_drift_44100.py)を開く。研究ワークスペースで `jq '.trials | map_values(.events.waveform_departure | {output_frame, ms_from_first_output_timestamp, tap: .tap.containing})' runs/coreaudio-headphone-drift-44100-leading-silence-pairs-20261122-a/summary.json` を実行する。次のケースでは既存の100 msの待機を基準に、タップ準備後に出力を始めるまでの待機を追加し、予定ホスト時刻の間隔が実際にずれた試行を比較する。

## 44.1 kHzで直接出力とタップの開始時刻を照合する（2026-11-22）

- 完了した項目。タップ準備後の待機を100→350 msと100→1,100 msに変え、各3組を収録した。全12回でPCMのビット、両時計の連続性、512フレーム幅、元のデバイスへの復元を確認した。最初の波形差は全12回で出力フレーム27,088。19,845 Hzの帯域低下と回復に対応する24区間では、位相傾斜と予定ホスト時計差が最大0.08958 ppmの差で一致した。[読解と比較](notes/worklet-english-voice.md#441-khzでタップの先行時間を変える)
- 未達の条件。出力開始API直前の時刻とタップ開始API直前の時刻の間隔は長い待機で約1秒延びたが、最初のタップの予定時刻も約0.93秒遅れた。最初の予定時刻同士の間隔は21〜30 ms縮まり、250 msの追加待機でも約55〜57 ms縮まった。事前の開始間隔の増加を満たした組は0/6。初版と補足の不成立を保持し、Core Audio内の処理段とアナログ出力は未確認。[初版](runs/coreaudio-headphone-drift-44100-tap-wait-pairs-20261122-a/summary.json)・[補足](runs/coreaudio-headphone-drift-44100-tap-wait-extended-pairs-20261122-a/summary.json)
- 最後に確認した実行。生PCM、2,748窓のFFT、最初の波形差と両観測点の時計を独立に検算した。固定上流エンジン6試験と再実装の分割描画1試験が通過。先頭無音の要約は回帰実行でバイト一致した。17実行の535入力・221出力を照合し、実体28,236,623バイトをRTL9210B-CGに保存した。既定出力は元の内蔵スピーカーに復元した。[補足のマニフェスト](runs/coreaudio-headphone-drift-44100-tap-wait-extended-pairs-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[直接出力と開始通知](tools/measure_coreaudio_output_error_pcm.py)と[タップの起動](tools/chimera_process_tap.swift)を開く。研究ワークスペースで `jq '.trials | map_values({startup_timing_ms,start_host_gap_ms,output_frame:.events.waveform_departure.output_frame})' runs/coreaudio-headphone-drift-44100-tap-wait-extended-pairs-20261122-a/summary.json` を実行する。出力を先に始め、継続出力中のプロセスへ後からタップを取り付ける対照を登録する。タップの最初の予定時刻を直接出力フレーム27,088の後ろへ移したとき、同じ帯域変化が接続後に生じるか調べる。

## 44.1 kHzの継続出力に後からタップを接続する（2026-11-22）

- 完了した項目。接続順だけを変えた3組を収録した。先行接続の波形差は3回ともフレーム27,088。後から接続した試行の最初のタップの予定時刻は、その出力フレームの予定時刻より1.028〜1.042秒後だった。後から接続した3回とも19,845 Hzの帯域低下を検出した。窓中心は出力フレーム85,616、タップ初回から320.02〜333.47 ms後で、振幅比は約0.49978から約0.01553へ落ちた。[事前登録](cases/coreaudio-headphone-drift-44100-late-attach.json)・[集約](runs/coreaudio-headphone-drift-44100-late-attach-pairs-20261122-a/summary.json)
- 未達の条件。後から接続すれば帯域低下が再発しないという予測は不成立。18区間の位相とホスト時計の照合では16区間が0.5 ppm以内で、末尾2区間は0.523・0.789 ppmの差があった。Core Audio内の処理段、変化を決める開始時刻、アナログ出力は未確定。[読解と結果](notes/worklet-english-voice.md#441-khzの継続出力に後からタップを接続する)
- 最後に確認した実行。生PCM、末尾マーカー、全1,366窓の実FFTと時計を独立に検算し、既存の直接出力3収録の解析結果とも一致した。上流エンジン6試験と再実装の分割描画1試験が通過。7実行の224入力・109出力のサイズとハッシュを照合し、実体19,938,330バイトをRTL9210B-CGへ保存した。全試行で既定出力は内蔵スピーカーへ復元した。[マニフェスト](runs/coreaudio-headphone-drift-44100-late-attach-pairs-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[後から接続する条件](cases/coreaudio-headphone-drift-44100-late-attach.json)と[収録・時計の集約](tools/measure_coreaudio_headphone_late_attach_44100.py)を開く。研究ワークスペースで `jq '.trials | map_values({attachment, first_tap_ms_from_prior_event, band_frame:.events.band_drop.source_frame, band_ms:.event_ms_from_first_tap_timestamp.band_drop})' runs/coreaudio-headphone-drift-44100-late-attach-pairs-20261122-a/summary.json` を実行する。後から接続する待機1.38秒と、それより約0.28秒短い条件を登録し、最初の帯域低下の出力フレームとタップからの時刻を比較する。

## 44.1 kHzの帯域低下で接続時刻と出力時刻を照合する（2026-11-22）

- 完了した項目。接続待機1.10秒と1.38秒の3組で、先頭予定ホスト時刻の間隔を210.91〜297.88 ms変えた。広帯域から低下する窓の中心は、全6回で出力フレーム85,616に揃った。先行接続の保存済み3収録でも同じ位置を含む4回の低下を観測し、窓中心の間隔は各29,200フレームだった。[新規比較](runs/coreaudio-headphone-drift-44100-attach-timing-pairs-20261122-a/summary.json)・[保存済み収録の再解析](runs/coreaudio-headphone-drift-44100-attach-preserved-20261122-a/summary.json)
- 未達の条件。タップ開始に揃うという予測は不成立。観測の範囲は約3秒の直接出力で、帯域変化を生むCore Audio内の処理段とアナログ出力は未確定。400フレーム窓で200フレーム刻みの測定であり、予定時刻の小数点以下は窓中心の換算精度を示す。[読解と検証](notes/worklet-english-voice.md#441-khzで再生中にタップを接続する時刻を比較する)
- 最後に確認した実行。1,539小窓の実FFT、先行収録の1,641小窓の独立射影、両時計を検算した。新規比較の27区間で位相傾斜と時計差が0.5 ppm以内。上流のエンジン6試験と再実装の分割描画1試験が通過し、従来の接続順比較の集約はバイト一致した。9実行の290入力・111出力を照合し、実体20,174,943バイトをRTL9210B-CGへ保存した。元の既定出力は全試行で復元した。[集約のマニフェスト](runs/coreaudio-headphone-drift-44100-attach-timing-pairs-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[直接出力プローブ](tools/chimera_output_deadline_probe.swift)と[保存済みPCMの再解析](tools/review_coreaudio_headphone_preserved_44100.py)を開く。研究ワークスペースで `jq '.trials | map_values([.spans[] | select(.band == "reduced") | .first_center_frame])' runs/coreaudio-headphone-drift-44100-attach-preserved-20261122-a/summary.json` を実行する。同じ4周波数で試験音と採取を3秒より長くするケースを登録し、29,200フレーム間隔の持続と終了を測る。

## 44.1 kHzの長い再生で帯域低下の反復と終了を測る（2026-11-22）

- 完了した項目。同じ4周波数の直接出力を12秒に延長して3回収録。入力PCM、両予定時計、機器の44.1 kHzと512フレーム幅、前後のマーカーを照合した。低下は11・11・12回で、最後の低下は出力から7.211〜7.873秒。その後11.597秒の観測末尾まで19,845 Hzの振幅比は約0.01542だった。[事前登録](cases/coreaudio-headphone-drift-44100-long-recurrence.json)・[全試行の集約](runs/coreaudio-headphone-drift-44100-long-recurrence-20261122-a/summary.json)
- 未達の条件。同じ29,200フレーム間隔が連続する予測は3回とも不成立。31間隔中26が29,200、5が28,600フレームだった。通常の65区間の位相傾斜と時計差は最大0.100 ppm。狭帯域が続く長い終盤の回帰は2回で0.5 ppmの差を超えた。観測末尾以降とCore Audio内の処理段、アナログ出力は未確認。[読解・検証](notes/worklet-english-voice.md#441-khzの帯域低下が長い再生で続くかを測る)
- 最後に確認した実行。7,533窓の実FFTと68区間の独立回帰、PCMのビット、前後マーカー、予定時計を検算した。上流エンジン6試験と再実装の分割描画1試験が通過。接続時刻比較の集約は回帰実行でバイト一致した。5実行の152入力と56出力を照合し、実体35,558,254バイトをRTL9210B-CGに保存した。元の既定出力は全収録後に復元した。[集約のマニフェスト](runs/coreaudio-headphone-drift-44100-long-recurrence-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[直接出力の連続PCM](tools/chimera_output_deadline_probe.swift)と[試験音と帯域の集約](tools/measure_coreaudio_headphone_late_attach_44100.py)を開く。研究ワークスペースで `jq '.trials | map_values(.recurrence | {drop_frames,terminal_band,terminal_clock})' runs/coreaudio-headphone-drift-44100-long-recurrence-20261122-a/summary.json` を実行する。狭帯域が安定した区間に無音を入れ、直接出力を動かしたまま同じ試験音を再開させる最小条件を登録する。

## 44.1 kHzの狭帯域で無音を挟み試験音を再開する（2026-11-22）

- 完了した項目。狭帯域が安定した後に約1.04秒の無音を入れる条件と連続出力の3組を収録した。全試行で出力とタップの予定サンプル番号が連続し、無音ありの左右PCMでデジタルゼロを確認した。再開後の最初の窓の19,845 Hzの比は約0.01540。その後約1.846秒の全窓で0.01548未満に収まった。[事前登録](cases/coreaudio-headphone-drift-44100-silence-resumption.json)・[左右PCMとペアの集約](runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/summary.json)
- 未達の条件。今回の条件は直接出力のコールバックが続くときの無音。出力の停止と再開、1.846秒を超える再開後の観測、Core Audio内の処理段、アナログ出力は未確認。無音をまたぐ端点間の低域位相と時計には、連続出力側にも約1フレームの差があった。[読解と検証](notes/worklet-english-voice.md#441-khzの狭帯域で無音を挟み試験音を再開する)
- 最後に確認した実行。生の左右PCM、13,662窓の実FFT、再開後18区間の回帰を独立に検算した。上流エンジン6試験と再実装の分割描画1試験が通過。従来の長い再生の集約はバイト一致した。9実行の303入力・111出力を照合し、実体71,099,391バイトをRTL9210B-CGへ保存した。既定出力は元の内蔵スピーカーへ復元した。[集約マニフェスト](runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/manifest.json)
- 次に開くファイルと実行するコマンド。[直接出力プローブ](tools/chimera_output_deadline_probe.swift)と[無音後の計測](tools/measure_coreaudio_headphone_late_attach_44100.py)を開く。研究ワークスペースで `jq '.trials | map_values(.resumption | {gap_applied, post_first_ratio, post_median_ratio, phase_across_gap})' runs/coreaudio-headphone-drift-44100-silence-resumption-20261122-stereo-review/summary.json` を実行する。次は同じ約1.04秒の間に `AudioOutputUnitStop()` と `AudioOutputUnitStart()` を行い、試験音だけを無音にした今回と、再開時の予定時計と帯域を比べる。

## 44.1 kHzの狭帯域でAudioUnitを停止してから再開する（2026-11-22）

- 完了した項目。同じAudioUnitを停止し、約1.05秒後に再開する条件を3回採取した。前後のPCMは元データにビット一致し、出力の予定サンプル番号は3回とも再開時に0へ戻った。19,845 Hzの比は約0.50000から始まり、再開後の波形差は27,088フレーム、帯域低下の窓中心は27,136フレームだった。PCMだけを無音にした対照では約0.01540の狭帯域が続いた。[事前登録](cases/coreaudio-headphone-drift-44100-output-restart.json)・[全3組の集約](runs/coreaudio-headphone-drift-44100-output-restart-20261122-a/summary.json)
- 未達の条件。停止と再開のAPI間は1,045.39〜1,054.95 ms、直接出力の予定ホスト時計の空きは1,128.43〜1,139.43 ms。タップの予定サンプル番号は無音の間も進んだ。処理段の特定、ブラウザの再開条件への適用と、アナログ出力の照合は残る。[読解と計測](notes/worklet-english-voice.md#441-khzの狭帯域でaudiounitを停止してから再開する)
- 最後に確認した実行。生PCM、6,831窓の実FFT、12区間の時計、タップのゼロ区間を独立に検算した。Swift型検査、固定上流エンジン6試験と再実装の分割描画1試験が通過し、PCMだけの無音対照の集約はバイト一致した。5実行の174入力・56出力を照合し、実体34,481,951バイトをRTL9210B-CGに保存した。既定出力は内蔵スピーカーへ復元した。[マニフェスト](runs/coreaudio-headphone-drift-44100-output-restart-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[Safariのプロセスタップ計測](tools/measure_safari_process_tap_calibration.py)と[直接出力の比較](tools/measure_coreaudio_headphone_restart_44100.py)を開く。研究ワークスペースで `jq '.pairs' runs/coreaudio-headphone-drift-44100-output-restart-20261122-a/summary.json` を実行する。研究版のSafariで同じ44.1 kHz試験音とAudioContextの停止・再開を使い、グラフ内PCMとタップの帯域が再開前後でどう変わるかを比較する。

## Safariの44.1 kHzでAudioContextの停止・再開を照合する（2026-11-22）

- 完了した項目。Safari 18.6で連続再生・停止再開を3組採取した。全6回でWeb Audioグラフの526,336フレームが入力とビット一致した。停止再開ではタップの19,845 Hzが約0.50000へ戻り、再開後26,616・26,816・27,088フレームで帯域低下を検出した。連続再生では約0.01542の狭帯域が続いた。[事前登録](cases/safari-headphone-context-restart-44100.json)・[集約](runs/safari-headphone-context-restart-44100-20261122-a/summary.json)
- 未達の条件。停止前にタップだけで断続的なゼロ区間が2試行に見られた。完全ゼロの1窓で相対残差が未定義になった計算を修正し、元の判定を保存した。原因となる出力側の処理段、Firefoxの比較、アナログ出力は未確認。[読解と検証](notes/worklet-english-voice.md#safariの441-khzでaudiocontextの停止再開を照合する)・[残差の再解析](runs/safari-headphone-context-restart-44100-pause-1-residual-review/summary.json)
- 最後に確認した実行。入力ビット、15,023窓の実FFT、マーカー、予定時計、タップの無音を独立に照合した。Safari 44.1 kHz較正の回帰、固定上流エンジン6試験と再実装の分割描画1試験が通過。9実行の279入力・135出力を照合し、実体50,796,435バイトをRTL9210B-CGへ保存した。既定出力は内蔵スピーカーに戻した。[実行マニフェスト](runs/safari-headphone-context-restart-44100-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[Firefoxの出力マーカー計測](tools/measure_firefox_output_marker.py)と[Safariのグラフ・タップ比較](tools/measure_safari_headphone_context_restart_44100.py)を開く。研究ワークスペースで `jq '.pairs' runs/safari-headphone-context-restart-44100-20261122-a/summary.json` を実行する。Firefoxでも同じ44.1 kHz試験音・AudioContextの停止時間を使い、グラフPCM・出力要求・タップの再開前後を測る。

## Firefoxの44.1 kHzでAudioContextの停止と出力要求を照合する（2026-11-22）

- 完了した項目。44.1 kHzの連続・停止再開を3組採取し、各試行でグラフ128・cubeb256・タップ512フレームの3観測点を同時に記録した。全6回でグラフと測定区間のcubeb PCMが入力とビット一致した。停止ありの3回はcubebが別ストリームに切り替わり、予定サンプル番号が0から始まった。タップの19,845 Hzの振幅比は約0.50000に戻り、再開から602〜616 msで低下した。連続対照は約0.01542の狭帯域が続いた。[事前登録](cases/firefox-headphone-context-restart-44100.json)・[3組の集約](runs/firefox-headphone-context-restart-44100-20261122-b/summary.json)
- 未達の条件。旧ビルドの予備試行はcubebの採取長と停止前の狭帯域の前提が不足した。再リンク後の初回6回はPlaywrightの起動設定が不足して欠測となり、同じ測定条件を引き継いで再試行した。Context停止とストリーム停止を分けた場合の帯域挙動、Core Audio内の処理段、アナログ出力が残る。[読解と検証](notes/worklet-english-voice.md#firefoxの441-khzでaudiocontextの停止と出力要求を照合する)・[予備試行](runs/firefox-headphone-context-restart-44100-pilot-256/summary.json)・[初回の集約](runs/firefox-headphone-context-restart-44100-20261122-a/summary.json)
- 最後に確認した実行。17,522窓の実FFT、左右PCMのビット、前後マーカー、予定時計とタップのゼロ区間を独立に検証した。上流エンジン6試験と再実装の分割描画1試験が通過し、Safariの採取済み停止試行の再解析は元の観測値と一致した。17実行の648入力・251出力を照合し、実体87,577,157バイトをRTL9210B-CGに保存した。既定出力を内蔵スピーカーへ復元した。[集約マニフェスト](runs/firefox-headphone-context-restart-44100-20261122-b/manifest.json)
- 次に開くファイルと実行するコマンド。[Firefoxの試験音とContext操作](../../../web/prototypes/chimera-research/tools/capture-firefox-output-marker.mjs)と[3観測点の測定](tools/measure_firefox_headphone_context_restart_44100.py)を開く。研究ワークスペースで `jq '.pairs[] | {continuous_remained_narrow,suspended_cubeb_changed_stream,suspended_drop_frames_from_resume}' runs/firefox-headphone-context-restart-44100-20261122-b/summary.json` を実行する。別のContextで先行音を鳴らし続ける対照を登録し、主Contextを約1.045秒停止した間もcubebのストリームと予定サンプル番号が連続する条件で、同じ再開後の帯域を比べる。

## Firefoxで出力を維持したまま主AudioContextを止める（2026-11-22）

- 完了した項目。別Contextから44.1 kHzの同相音を出し、連続再生と主Contextだけの停止・再開を3組比較した。全6回でグラフPCMとcubebの左右の混合値は期待値にビット一致した。停止中も同じcubebストリームの予定サンプル番号が進み、左右に維持音だけが残った。再開後の19,845 Hzの比は3回とも約0.01539で始まり、観測末尾まで0.015463未満だった。[事前登録](cases/firefox-headphone-context-keep-output-44100.json)・[3組の判定](runs/firefox-headphone-context-keep-output-44100-20261122-a/summary.json)
- 未達の条件。最初の2試行に真偽値の保存エラー、第2停止試行にcubeb前マーカーの探索不足があった。元の収録と判定を保存し、同じ測定区間と閾値で再解析した。維持音をデジタルゼロにしても帯域が維持されるか、Core Audio内の処理段、アナログ出力は未確認。[読解と検証](notes/worklet-english-voice.md#firefoxで出力を維持したまま主audiocontextを止める)・[第2停止の初回](runs/firefox-headphone-context-keep-output-44100-pause-2/summary.json)・[再解析](runs/firefox-headphone-context-keep-output-44100-pause-2-review/summary.json)
- 最後に確認した実行。主信号15,023窓・停止中の維持音659窓の実FFT、左右PCM、予定時計を独立に照合した。単一Contextの保存済み試行の再解析は既存結果と一致し、上流エンジン6試験と再実装の分割描画1試験が通過した。10実行の449入力・140出力を照合し、実体78,515,018バイトをRTL9210B-CGに保存した。既定出力は内蔵スピーカーへ復元した。[集約マニフェスト](runs/firefox-headphone-context-keep-output-44100-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[Firefoxの試験ページ](../../../web/prototypes/chimera-research/tools/capture-firefox-output-marker.mjs)と[出力維持ケース](cases/firefox-headphone-context-keep-output-44100.json)を開く。研究ワークスペースで `jq '.trials | map_values({suspend, cubeb_same_stream, keeper_output, post: .resumption.post_first_ratio})' runs/firefox-headphone-context-keep-output-44100-20261122-a/summary.json` を実行する。別Contextの出力だけをデジタルゼロにする条件を登録し、同じcubebストリームと予定時計が続く試行で、主Context再開後の帯域を今回と比較する。

## Firefoxで無音の別AudioContextを動かし続ける（2026-11-22）

- 完了した項目。44.1 kHzで別Contextの出力をデジタルゼロにし、主Contextの連続・停止再開を3組比較した。停止中も同じcubebストリームの時計が進み、cubebとタップの停止区間では左右ゼロを確認した。全6回でグラフ・cubebのPCMが期待値とビット一致した。再開後の19,845 Hzの振幅比は約0.01539で始まり、測定末尾まで0.015460未満だった。[事前登録](cases/firefox-headphone-context-silent-output-44100.json)・[判定と同相音ありとの照合](runs/firefox-headphone-context-silent-output-44100-20261122-a/summary.json)
- 未達の条件。帯域が変わるCore Audio内の処理段と、ヘッドフォンのアナログ出力は未確認。第6段階の歌唱経路では保存済みの48 kHzのネイティブABIに描画中の割り当て11,809回が残る。現行コードでの再現と、語境界で増える割り当ての出所を確認する。[出力比較の読解と実測](notes/worklet-english-voice.md#firefoxで無音の別audiocontextを動かし続ける)・[歌唱の割り当て](notes/worklet-live-song.md#結果)
- 最後に確認した実行。15,017窓の実FFT、cubebとタップのゼロおよび予定時計を生データから照合した。単一Context・同相音維持の保存済み2試行は再解析で全観測値が一致した。固定上流エンジン6試験と再実装の分割描画1試験が通過した。7実行の324入力・139出力を照合し、実体78,550,443バイトをRTL9210B-CGに保存した。既定出力は内蔵スピーカーへ復元した。[集約マニフェスト](runs/firefox-headphone-context-silent-output-44100-20261122-a/manifest.json)
- 次に開くファイルと実行するコマンド。[歌唱の比較入口](tools/measure_worklet_song.py)、[ネイティブABIの割り当て計数](crates/vocal-wasm/src/lib.rs)、[調音接触補正](crates/vocal-core/src/voice.rs)を開く。研究ワークスペースで `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=150000000 ../../.venv/bin/python tools/measure_worklet_song.py worklet-live-song-allocation-current-20261122-a --live` を使い、`Pop Dee` の現行の計数を取り直す。語境界の前後と接触補正の `apply()`・`reapply()` に計数点を設ける最小比較を事前登録し、PCMと内部系列が元の経路と一致することを確かめる。

## 48 kHz歌唱の声道更新の割り当てを照合する（2026-11-22）

- 完了した項目。現行の `Pop Dee` で旧記録と同じ11,809回を再現した。25量子で16回増えた分は、各量子で接触補正が2回の声道再計算を追加したことで説明できた。声道更新1回につき8件で、接触グリッド3、面積プロファイル1、再標本化2、セル列の複製2。初回量子の追加1件は乱流源登録内で、全体に未分類件数はなかった。[事前登録](cases/song-render-allocation-phases.json)・[量子別と全体の判定](runs/song-render-allocation-phases-20261122-b/summary.json)
- 未達の条件。最初の確認コマンドはテスト名のモジュール指定が不足し、試験を選択できなかった。正式な計測は修正したフィルターで実行済み。計測はネイティブの割り当て回数で、WASMのアロケーターやブラウザの処理予算に対する改善効果は未測定。声道更新のセル複製も現状は毎回確保している。[読解と実測](notes/song-render-allocation-phases.md)
- 最後に確認した実行。計測の有無で91,200標本と1,425点のABI全23値がビット一致し、通常のブラウザのPCMと12観測列も一致した。診断2回の要約と生データはバイト一致。計測機能を指定しない歌唱の回帰25判定、上流15試験、再実装38試験が通過した。4実行の809入力・68出力を照合し、実体343,437,813バイトをRTL9210B-CGに保存した。[診断マニフェスト](runs/song-render-allocation-phases-20261122-b/manifest.json)・[通常経路の回帰](runs/worklet-live-song-allocation-probe-regression-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[断面の更新](crates/vocal-core/src/airway/tract_control.rs)と[等長セルの構造](crates/vocal-core/src/anatomy/resample.rs)を開く。研究ワークスペースで `jq '{phase_totals,focus_ranges,residuals}' runs/song-render-allocation-phases-20261122-b/summary.json` を実行する。`raw` から `limited` への複製で咽頭・口腔のセル容量を再利用するケースを登録し、前周期の基準断面、接触補正後の断面、PCMのビットを照合しながら2,952件の削減予測を検証する。

## 制限用の咽頭・口腔セル領域を再利用する（2026-11-22）

- 完了した項目。初期化した2組のセル領域を、周期開始と接触補正後の再計算で使い回した。48 kHzの歌唱 `Pop Dee` の割り当ては11,809回から8,857回、語境界の25量子は各32回から24回になった。91,200標本と全ABI観測が変更前とビット一致し、通常CLIの4ケース・45,360行の制限前後の断面もバイト一致した。[事前登録](cases/tract-limited-buffer-reuse.json)・[読み解きと結果](notes/tract-limited-buffer-reuse.md)・[集約](runs/tract-limited-buffer-reuse-20261122-b/summary.json)
- 未達の条件。再標本化による `raw` のセル割り当て2,952件は今回の計測にも残った。通常ブラウザのp99は変更前後とも2 ms、予算を超えた量子は2件。今回の計時は1 ms刻みだった。[ブラウザ計測](runs/worklet-live-song-limited-buffer-reuse-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` からの検証は要約・生PCM・観測・量子別CSVが一致した。生データから断面制限と割り当て差を検算した。通常の歌唱25判定、5体型・姿勢条件の70判定、上流12試験、再実装38試験が通過した。5実行の807入力・148出力を照合し、実体484,596,157バイトをRTL9210B-CGに保存した。[マニフェスト](runs/tract-limited-buffer-reuse-20261122-b/manifest.json)・[体型の回帰](runs/tract-limited-buffer-reuse-body-regression-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[再標本化](crates/vocal-core/src/anatomy/resample.rs)と[断面更新](crates/vocal-core/src/airway/tract_control.rs)を開く。研究ワークスペースで `jq '{resample: .phase_totals.resample, total: .allocations, shape: .geometry_byte_equal}' runs/tract-limited-buffer-reuse-20261122-b/summary.json` を実行する。再標本化先の `raw` のセル列を再利用するケースを登録し、今回の系列を基準に、減る件数と断面・PCMを比較する。

## 再標本化の咽頭・口腔セル領域を再利用する（2026-11-22）

- 完了した項目。前の `raw` のセル領域を再標本化先に使い、48 kHzの `Pop Dee` の割り当てを8,857回から5,905回へ減らした。再標本化の2,952回がゼロになり、語境界の25量子は各24回から16回になった。CLIの4ケース・45,360行、歌唱のPCM 91,200標本と1,425点のABI全23値が変更前と一致した。無効な面積の検査を経ても再利用先を保持することを確認した。[事前登録](cases/tract-resample-buffer-reuse.json)・[計測結果](runs/tract-resample-buffer-reuse-20261122-b/summary.json)・[読解と実装](notes/tract-resample-buffer-reuse.md)
- 未達の条件。接触グリッドに4,428件、面積プロファイルに1,476件、初回の乱流源登録に1件が残る。今回の1 ms刻みのブラウザ計測は変更前後ともp99が2 ms、予算超過が2量子だった。[ブラウザ計測](runs/worklet-live-song-resample-buffer-reuse-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` からの候補実行で要約・生PCM・観測・量子別CSVがバイト一致し、断面制限と割り当て差を独立に検算した。通常歌唱25判定、体型別70判定、再実装39試験、固定上流17試験が通過した。4実行の684入力・142出力を照合し、実体476,140,493バイトをRTL9210B-CGに保存した。[候補のマニフェスト](runs/tract-resample-buffer-reuse-20261122-b/manifest.json)・[体型の回帰](runs/tract-resample-buffer-reuse-body-regression-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[接触グリッド](crates/vocal-core/src/anatomy/contact.rs)と[測定線](crates/vocal-core/src/anatomy/grid.rs)を開く。研究ワークスペースで `jq '{contact: .phase_totals.contact_grid, area: .phase_totals.area_profile}' runs/tract-resample-buffer-reuse-20261122-b/summary.json` を実行する。口蓋沿い累積距離、測定線と標本変換を区切って計数し、累積距離の領域だけを再利用する候補を、今回の断面とPCMを基準に比較する。

## 接触グリッドの口蓋沿い累積距離を再利用する（2026-11-22）

- 完了した項目。接触グリッド4,428回の割り当てを、累積距離・測定線・接触標本の各1,476回に分解した。累積距離用の領域を初回の形状計算から保持し、48 kHzの `Pop Dee` 全体の割り当てを5,905回から4,429回へ減らした。語境界の25量子は各16回から12回。通常CLIの4ケース・45,360行、歌唱PCM 91,200標本、1,425点のABI全23値が変更前と一致した。[内訳の事前登録](cases/contact-grid-allocation-breakdown.json)・[再利用の事前登録](cases/contact-roof-buffer-reuse.json)・[読解・実装・結果](notes/contact-roof-buffer-reuse.md)
- 未達の条件。測定線・接触標本・面積プロファイルに各1,476件、初回の乱流源登録に1件の割り当てが残る。ブラウザの1 ms刻みの計時では変更前後ともp99は2 ms、予算を超えた量子は2件だった。[ブラウザ計測](runs/worklet-live-song-contact-roof-buffer-reuse-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` から再現し、要約・PCM・ABI観測・量子別CSVがバイト一致した。生データから断面制限と割り当て差を検算した。内訳・再利用で各22判定、通常歌唱25判定、5体型・姿勢条件の70判定、再実装40試験、固定上流12試験が通過した。5実行の822入力・156出力を照合し、実体486,674,297バイトをRTL9210B-CGに保存した。[候補のマニフェスト](runs/contact-roof-buffer-reuse-20261122-b/manifest.json)・[体型の回帰](runs/contact-roof-buffer-reuse-body-regression-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[測定線の生成](crates/vocal-core/src/anatomy/grid.rs)と[接触標本の生成](crates/vocal-core/src/anatomy/contact.rs)を開く。研究ワークスペースで `jq '{contact_grid: .phase_totals.contact_grid, measurement_grid: .phase_totals.measurement_grid, contact_samples: .phase_totals.contact_samples}' runs/contact-roof-buffer-reuse-20261122-b/summary.json` を実行する。測定線 `GridSample` の領域だけを再利用する比較を登録し、減る件数と断面・PCMを今回の実行に照合する。

## 接触補正前の測定線を再利用する（2026-11-22）

- 完了した項目。測定線の領域を制御器に保持し、48 kHzの `Pop Dee` で測定線の割り当て1,476件を解消した。歌唱全体は4,429回から2,953回、語境界の25量子は各12回から8回。CLIの4条件・45,360行と歌唱PCM 91,200標本、1,425点のABI全23値は変更前と一致した。平行壁の間隔を変え、測定線が空になるフレームを挟んでも正しい隙間と同じ確保先を確認した。[事前登録](cases/contact-measurement-grid-reuse.json)・[読解と結果](notes/contact-measurement-grid-reuse.md)
- 未達の条件。接触標本と面積プロファイルに各1,476件、初回の乱流源登録に1件残る。ブラウザのp99は前後とも2 ms。計時の予算超過は前回2量子、今回は1量子で、各版1実行での観察値だった。[割り当て](runs/contact-measurement-grid-reuse-20261122-b/summary.json)・[通常歌唱](runs/worklet-live-song-contact-measurement-grid-reuse-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` から22判定を再現し、要約・生PCM・ABI観測・量子別計数・断面がバイト一致した。独立に断面制限と量子ごとの割り当て差を検算した。通常歌唱25判定、体型・姿勢70判定、再実装41試験と下唇の交差厚さ付き15試験、固定上流12試験が通過した。4実行の684入力・142出力のハッシュを照合し、実体476,395,009バイトをRTL9210B-CGに保存した。[候補のマニフェスト](runs/contact-measurement-grid-reuse-20261122-b/manifest.json)・[体型の回帰](runs/contact-measurement-grid-reuse-body-regression-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[接触標本](crates/vocal-core/src/anatomy/contact.rs)と[面積への変換](crates/vocal-core/src/anatomy/area.rs)を開く。研究ワークスペースで `jq '{samples: .phase_totals.contact_samples, profile: .phase_totals.area_profile, total: .allocations}' runs/contact-measurement-grid-reuse-20261122-b/summary.json` を実行する。接触標本 `ContactSample` の領域を保持し、断面計算へ借用で渡す候補を事前登録する。今回の量子別割り当て、断面、PCMを基準に照合する。

## 接触補正後の標本を再利用する（2026-11-22）

- 完了した項目。接触標本を制御器に保持し、断面生成にスライスを渡した。48 kHzの `Pop Dee` で接触グリッドの描画中の割り当てはゼロになった。歌唱全体は2,953回から1,477回、語境界25量子では各8回から4回だった。CLIの4条件・45,360行、歌唱PCM 91,200標本、1,425点のABI全23値は基準と一致した。平行壁の試験で測定点がない場合のエラー、同じ領域への再書き込み、先頭の断面を確認した。[事前登録](cases/contact-sample-buffer-reuse.json)・[読解と結果](notes/contact-sample-buffer-reuse.md)
- 未達の条件。面積プロファイルに1,476件、初回の乱流源登録に1件の割り当てが残る。ブラウザ計時のp99は前後とも2 msで、予算を超えた量子は前回1、今回は2だった。各版1実行での観察値。[割り当て](runs/contact-sample-buffer-reuse-20261122-b/summary.json)・[通常歌唱](runs/worklet-live-song-contact-sample-buffer-reuse-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` から22判定を再現し、要約・PCM・ABI観測・量子別計数・断面がバイト一致した。独立に断面制限と量子別割り当て差を検算した。通常歌唱25判定、体型・姿勢70判定、再実装42試験と下唇の交差厚さ付き16試験、固定上流12試験が通過した。4実行の684入力・142出力を照合し、実体476,394,281バイトをRTL9210B-CGに保存した。[候補のマニフェスト](runs/contact-sample-buffer-reuse-20261122-b/manifest.json)・[体型の回帰](runs/contact-sample-buffer-reuse-body-regression-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[断面標本の生成](crates/vocal-core/src/anatomy/area.rs)と[最後に確定した断面の保持](crates/vocal-core/src/airway/tract_control.rs)を開く。研究ワークスペースで `jq '{profile: .phase_totals.area_profile, turbulence: .phase_totals.turbulence, total: .allocations}' runs/contact-sample-buffer-reuse-20261122-b/summary.json` を実行する。断面標本の領域を再利用する比較を登録し、計算が失敗しても最後に確定した断面を読み出せる条件を含める。

## 断面標本の領域を再利用する（2026-11-22）

- 完了した項目。確定済みと作業中の断面標本に二つの領域を使い、48 kHzの `Pop Dee` で断面生成の割り当てを1,476回からゼロにした。歌唱全体は1,477回から1回、語境界の25量子は各4回からゼロ。CLIの4条件・45,360行、歌唱PCM 91,200標本、1,425点のABI全23値は基準と一致した。平行壁と、固定セル数で再標本化に失敗する姿勢からの復帰で、確保先と確定済み断面を確認した。[事前登録](cases/tract-area-buffer-reuse.json)・[読解と結果](notes/tract-area-buffer-reuse.md)
- 未達の条件。初回量子の乱流源登録に1件残る。ブラウザ計時のp99は前後とも2 msで、予算超過は前後とも2量子、WASMメモリ成長は前後とも0回だった。[割り当て](runs/tract-area-buffer-reuse-20261122-b/summary.json)・[通常歌唱](runs/worklet-live-song-tract-area-buffer-reuse-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` から22判定を再現し、要約・PCM・ABI観測・量子別計数・断面がバイト一致した。CSVから断面制限と配列入出力から割り当て差を独立に検算した。通常歌唱25判定、体型・姿勢70判定、再実装43試験と下唇の交差厚さ付き17試験、固定上流12試験が通過した。4実行の684入力・142出力を照合し、実体476,395,215バイトをRTL9210B-CGに保存した。[候補のマニフェスト](runs/tract-area-buffer-reuse-20261122-b/manifest.json)・[体型の回帰](runs/tract-area-buffer-reuse-body-regression-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[人間の乱流源選択](crates/vocal-core/src/airway/human/frication.rs)と[乱流源の領域と状態](crates/vocal-core/src/airway/network/turbulence.rs)を開く。研究ワークスペースで `jq '{turbulence: .phase_totals.turbulence, total: .allocations}' runs/tract-area-buffer-reuse-20261122-b/summary.json` と `head -2 runs/tract-area-buffer-reuse-20261122-b/artifacts/allocations-by-quantum.csv` を実行する。人間の初期化で `reserve_noise_sources()` を使う条件を登録し、初回と複数源の登録・更新で計数、フィルタ状態、同じシードの音が一致するか比較する。

## 人間の気道で乱流源を初期確保する（2026-11-22）

- 完了した項目。人間の気道の初期化で乱流源の二つの領域を各3件分確保し、48 kHzの `Pop Dee` 全713量子の描画中の割り当てを1回からゼロにした。CLIの4条件・45,360行、歌唱PCM 91,200標本、1,425点のABI全23値は基準に一致した。最大3件の乱流源を増減・並べ替えした試験では、512内部サンプルのフィルタ状態と注入圧が事前確保なしの対照とビット一致した。[事前登録](cases/human-noise-source-reserve.json)・[読解と結果](notes/human-noise-source-reserve.md)
- 未達の条件。44.1 kHzの英語発話でコマンド適用時と描画中に残る割り当ては現行版で未計測。今回の歌唱のブラウザ計時はp99が前後とも2 ms、予算超過は前回2量子、今回は1量子だった。計時は各版1実行。[歌唱の計数](runs/human-noise-source-reserve-20261122-b/summary.json)・[ブラウザ計測](runs/worklet-live-song-human-noise-source-reserve-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` から22判定を再現した。通常歌唱25判定、歯茎摩擦音7判定、体型・姿勢70判定、再実装44試験と下唇の交差厚さ付き18試験、固定上流の破擦音とエンジン9試験が通過した。歯の乱流源の5,568フレームの帯域を独立式に照合した。5実行の806入力・156出力を照合し、実体531,106,329バイトをRTL9210B-CGに保存した。[候補のマニフェスト](runs/human-noise-source-reserve-20261122-b/manifest.json)・[歯茎摩擦音の比較](runs/sibilant-s-human-noise-source-reserve-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[44.1 kHz発話の計測](tools/measure_worklet_live_tsp_rate.py)と[ネイティブABIの発話計数](crates/vocal-wasm/src/lib.rs#L2205)を開く。研究ワークスペースで `jq '{pcm, timing, checks}' runs/worklet-live-tsp-44100-20261122-a/summary.json` を実行する。英語発話「確認用07」のコマンド適用時と実際の描画量子を計数する条件を事前登録し、保存済みの98,790標本と内部観測を基準に比較する。

## 44.1 kHz英語発話の準備と描画を計数する（2026-11-22）

- 完了した項目。確認用07の英語計画ABIで3,555回、スコア開始ABIで118回、全772量子のネイティブ描画で0回を観測した。保存済みの全PCM 98,790フレーム、3,088点の観測、声門2系列、129時点の声道断面・圧力・流量がビット一致した。最初の非ゼロは2,247フレーム、固定上流とのPCM最大差は1.16×10⁻¹⁰。[事前登録](cases/worklet-live-tsp-allocation-44100.json)・[読解と実測](notes/worklet-live-tsp-allocation-44100.md)
- 未達の条件。英語計画の3,555件の工程別内訳とスコア開始の118件の内訳は未同定。Firefoxでは全量子のp99が保存済み2 msに対して今回は3 ms、予算超過は2量子に対して9量子。各版1実行で、ネイティブの配分計数とブラウザのタイミングは別の観測点。[Firefox再計測](runs/worklet-live-tsp-44100-allocation-regression-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` から20判定を再現し、PCM・観測・計数がバイト一致した。生データからPCM・観測と1,544回の制御周期を独立検算した。Firefoxの11判定、再実装44試験、固定上流の英語・エンジン11試験が通過した。3実行の521入力・54出力を照合し、実体41,583,296バイトをRTL9210B-CGに保存した。[候補のマニフェスト](runs/worklet-live-tsp-allocation-44100-20261122-b/manifest.json)
- 次に開くファイルと実行するコマンド。[英語計画と辞書索引](crates/vocal-wasm/src/planning.rs#L278)と[英語の音素・句の計画](crates/vocal-core/src/phonetics/english.rs#L373)を開く。研究ワークスペースで `jq '{planner_allocations, setup_allocations, render_allocations}' runs/worklet-live-tsp-allocation-44100-20261122-b/summary.json` を実行する。索引の構築、句の計画、スコアと報告の生成の割り当てを同じ入力で独立に計数するケースを登録する。

## 英語計画ABIの割り当てを工程別に測る（2026-11-22）

- 完了した項目。確認用07の初回3,555回を六工程に分けた。JSON関連は1,822回、辞書索引は17回。再計画の2,010回への減少は、発音と句の計画の1,544回とスコア領域の1回だった。コア計画だけ先行させると初回ABIは2,011回となり、通常初回と同じ計画と数値スコアを得た。[事前登録](cases/worklet-live-tsp-planner-allocation-44100.json)・[先行処理の事前登録](cases/worklet-live-tsp-planner-prewarm-44100.json)・[読解と結果](notes/worklet-live-tsp-planner-allocation-44100.md)
- 未達の条件。最初の再計画で1回だけ減るという予測は外れた。コア内で音素・継続時間・較正表を遅延初期化しているが、各表の割り当て件数は未計測。報告値の構築1,282件は再計画でも残った。Firefoxの今回は全量子のp99が2 msで、約2.90 msの予算超過は3量子。[通常計数の集計](runs/worklet-live-tsp-planner-allocation-44100-20261122-c/summary.json)・[Firefoxの計時](runs/worklet-live-tsp-44100-planner-regression-20261122/summary.json)
- 最後に確認した実行。通常の工程別計数30判定、コア計画の先行処理31判定、Firefox11判定、再実装44試験、固定上流の英語とエンジン11試験が通過した。PCM 98,790標本、内部観測、声門・声道の時系列は基準に一致し、772量子で描画中のネイティブ割り当てはゼロだった。6実行の954入力・127出力を照合し、実体59,858,240バイトをRTL9210B-CGに保存した。[通常計数](runs/worklet-live-tsp-planner-allocation-44100-20261122-c/manifest.json)・[先行処理](runs/worklet-live-tsp-planner-prewarm-44100-20261122-b/manifest.json)
- 次に開くファイルと実行するコマンド。[報告と数値スコアの格納](crates/vocal-wasm/src/planning.rs#L191)と[報告の読み出し](crates/vocal-wasm/host/planning.ts)を開く。研究ワークスペースで `jq '{planner_phase_allocations, cold_json_allocations}' runs/worklet-live-tsp-planner-allocation-44100-20261122-c/summary.json` を実行する。ジェスチャー入り報告値を構築する工程について、直接のJSONシリアライズを比較する条件を登録し、同じJSON、数値スコア、PCMを合否条件にする。

## 英語計画の報告を直接シリアライズする（2026-11-22）

- 完了した項目。既存の計画値とジェスチャーを借用してJSONへ直接書き出した。中間の報告値は1,282回から0回、文字列化は13回から9回。英語計画ABIは初回3,555回から2,269回、再計画2,010回から724回に減った。確認用07のJSON 17,014バイト、F64スコア、全PCM 98,790標本と内部観測が基準とバイト一致した。[事前登録](cases/worklet-live-tsp-planner-direct-report-44100.json)・[読解と結果](notes/worklet-live-tsp-planner-direct-report-44100.md)
- 未達の条件。英語の計画値を `serde_json::Value` にする工程は527回、出力バイト列の確保などは9回残る。ブラウザの単回計時では英語発話と歌唱のp99は2 ms、予算超過は各2量子だった。[英語計画の内訳](runs/worklet-live-tsp-planner-direct-report-44100-20261122-b/summary.json)・[通常の英語発話](runs/worklet-live-tsp-44100-direct-report-regression-20261122/summary.json)・[通常の歌唱](runs/worklet-live-song-direct-report-regression-20261122/summary.json)
- 最後に確認した実行。研究ワークスペースと `/tmp` から31判定を再現した。通常の英語発話11判定、歌唱25判定、再実装46試験と固定上流の対応試験が通過した。従来のJSONのキー順・省略フィールド・エラー・スコアのリセットも照合した。4実行の836入力・86出力を照合し、実体211,700,911バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](runs/worklet-live-tsp-planner-direct-report-44100-20261122-b/manifest.json)・[量子別のCSV](runs/worklet-live-tsp-planner-direct-report-44100-20261122-b/artifacts/allocations-by-quantum.csv)
- 次に開くファイルと実行するコマンド。[英語の計画値の生成](crates/vocal-wasm/src/planning.rs#L310)と[報告の出力](crates/vocal-wasm/src/planning/report.rs)を開く。研究ワークスペースで `jq '{planner_phase_allocations, planner_phase_totals}' runs/worklet-live-tsp-planner-direct-report-44100-20261122-b/summary.json` を実行する。英語の `TextPlan` を中間値へ変換する工程を直接のシリアライズに置き換える条件を登録し、時刻、調音スコア、JSON、PCMを前回と照合する。

## 英語の型付き発話計画を直接報告する（2026-11-22）

- 完了した項目。英語の `TextPlan` を借用してJSONへ直接書き出した。中間の英語計画値は初回・再計画とも527回からゼロ。英語計画ABI全体は初回2,269回から1,742回、再計画724回から197回に減った。確認用07のJSON 17,014バイト、数値スコア、全98,790フレームのPCMと内部観測は基準にバイト一致した。[事前登録](cases/worklet-live-tsp-planner-direct-text-plan-44100.json)・[読解と結果](notes/worklet-live-tsp-planner-direct-text-plan-44100.md)
- 未達の条件。JSON出力には各9回、発音と句の計画には初回1,715回、再計画171回が残る。単回のFirefox計時ではp99は前後とも2 ms、予算超過は前回2量子、今回は7量子だった。[割り当て計数](runs/worklet-live-tsp-planner-direct-text-plan-44100-20261122-b/summary.json)・[Firefoxの通常発話](runs/worklet-live-tsp-44100-direct-text-plan-regression-20261122/summary.json)
- 最後に確認した実行。ワークスペースと `/tmp` から31判定と全削減予測を再現。独立に22音素区間と余韻を再計算し、描画中の割り当てが全772量子でゼロと確認した。通常のFirefox発話11判定、固定上流11試験、再実装47試験が通過した。3実行の574入力・62出力を検証し、実体41,670,866バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](runs/worklet-live-tsp-planner-direct-text-plan-44100-20261122-b/manifest.json)
- 次に開くファイルと実行するコマンド。[報告バッファの格納](crates/vocal-wasm/src/planning.rs#L191)と[ページ側のABI読み出し](crates/vocal-wasm/host/planning.ts)を開く。研究ワークスペースで `jq '{planner_phase_allocations, planner_phase_totals}' runs/worklet-live-tsp-planner-direct-text-plan-44100-20261122-b/summary.json` を実行する。既存のJSON出力領域を再利用する対照を登録し、同じ入力の再計画と、長い報告・短い報告・エラーを切り替える条件を確認する。

## 計画JSONの出力領域を再利用する（2026-11-22）

- 完了した項目。計画JSONを保持している領域に直接書き、確認用07の再計画はJSON出力9回からゼロ、ABI全体197回から188回になった。初回は1,742回。長い計画を短い計画、不正入力、元の長い計画へ切り替え、JSONの長さ、エラー、スコアの復元を確認した。報告を途中まで書いて失敗した場合も、次の呼び出しで通常の報告に戻った。[事前登録](cases/worklet-live-tsp-planner-report-buffer-44100.json)・[読解と結果](notes/worklet-live-tsp-planner-report-buffer-44100.md)
- 未達の条件。TSの通常の計画関数は呼び出しごとに新しいWASMインスタンスを作る。初回のJSON出力は9回。FirefoxとChromiumの単回計時のp99はともに2 ms、予算超過はそれぞれ6量子と1量子だった。[Firefoxの通常発話](runs/worklet-live-tsp-44100-report-buffer-final-20261122/summary.json)・[Chromiumの通常歌唱](runs/worklet-live-song-report-buffer-final-20261122/summary.json)
- 最後に確認した実行。ワークスペースと `/tmp` から36判定を再現。PCM、調音スコアと内部観測は基準にバイト一致し、描画中の割り当ては全772量子でゼロ。Firefoxの11判定、Chromiumの25判定、再実装48試験と固定上流の対応試験が通過した。失敗した最初の計測を保存し、入力検証の計数範囲を直して再実行した。最終版4実行の854入力と88出力を照合し、実体211,741,056バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](runs/worklet-live-tsp-planner-report-buffer-44100-20261122-c/manifest.json)・[修正前の判定](runs/worklet-live-tsp-planner-report-buffer-44100-20261122-a/summary.json)
- 次に開くファイルと実行するコマンド。[ページ側でのインスタンス生成と読み出し](crates/vocal-wasm/host/planning.ts)と[英語計画の通常の呼び出し元](../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L280)を開く。研究ワークスペースで `jq '{planner_phase_allocations, planner_phase_totals, planner_predictions}' runs/worklet-live-tsp-planner-report-buffer-44100-20261122-c/summary.json` を実行する。英語計画を同じページで2回行うケースを登録し、入力と辞書が変わる場合の報告・以前のスコアのコピー・描画を、毎回インスタンスを作る条件と照合する。

## 英語のWASM計画器をページで共有する（2026-11-22）

- 完了した項目。確認用07のオフライン発話と実時間発話を同一ページで続けた際、ページ側でのWASMコンパイルは2回から1回になり、計画器は1個だった。同じ綴りの辞書の母音を `æ` から `ʌ` に差し替え、既に返した計画・スコアの一致と、初回取得でのHTTP 503からの復帰を確認した。[事前登録](cases/worklet-live-tsp-english-planner-reuse-44100.json)・[読解と結果](notes/worklet-live-tsp-english-planner-reuse-44100.md)
- 未達の条件。同じWASM取得を待つ二つの呼び出しの片方を途中で中止する条件の観測が残る。通常発話の44.1 kHzの単回計時ではp99が2〜3 ms、予算超過は1〜12量子だった。[44.1 kHzの再実行](runs/worklet-live-tsp-english-planner-reuse-44100-20261122-b/summary.json)
- 最後に確認した実行。ワークスペースと `/tmp` から18判定を再現し、44.1 kHzの全98,790フレームのPCM・内部観測・調音計画が基準に一致した。48 kHzのFirefox・Chromiumは停止操作を含む21判定を通過した。TS型検査、再実装のWASM31試験、固定上流11試験にも合格。3実行の846入力と64出力を照合し、実体78,707,854バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](runs/worklet-live-tsp-english-planner-reuse-44100-20261122-b/manifest.json)・[48 kHzの比較](runs/worklet-live-tsp-english-planner-reuse-48000-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[共有モジュールの読み込み](../../../web/prototypes/chimera-research/src/render-fixed-voice.ts#L76)と[ブラウザ内対照](../../../web/prototypes/chimera-research/tools/capture-english-planner-reuse.mjs)を開く。研究ワークスペースで `jq '{planner_reuse, checks}' runs/worklet-live-tsp-english-planner-reuse-44100-20261122-b/summary.json` を実行する。初回のWASM取得を遅延させ、同じ取得を待つ実時間とオフラインのうち実時間を停止する対照を登録し、Contextの終了、取得数、オフラインの計画とPCMを照合する。

## 共有WASM取得を待つ実時間発話を停止する（2026-11-22）

- 完了した項目。確認用07を使い、初回WASM取得の応答を保留して実時間発話とオフライン発話を重ねた。応答を渡す前に実時間側のContextがWorkletノードの生成前に閉じ、オフライン側は応答解放後に完了した。その後の実時間発話も成功し、取得・コンパイル・計画器生成は各1回だった。[事前登録](cases/worklet-live-tsp-shared-wasm-abort-44100.json)・[読解と結果](notes/worklet-live-tsp-shared-wasm-abort-44100.md)
- 未達の条件。今回の停止と再開の比較範囲は、英語の同一ページ内の44.1 kHz。計画全体では第7段階で人による試聴、実録音のF2注釈、物理MIDIの一次記録が残っている。[残る一次観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。ワークスペースと `/tmp` からFirefoxとChromiumの各15判定を再現した。停止しなかったオフライン描画と再開した実時間描画は、全98,790フレームのPCM・調音計画・内部観測が各基準に一致した。固定上流のPCMとの差は最大1.16×10⁻¹⁰。独立検算で558入力・28出力を照合し、実体43,516,757バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](runs/worklet-live-tsp-shared-wasm-abort-44100-20261122-b/manifest.json)・[判定](runs/worklet-live-tsp-shared-wasm-abort-44100-20261122-b/summary.json)
- 次に開くファイルと実行するコマンド。[段階別の既存監査](notes/plan-evidence-audit.md#完了条件と観測値の照合)と[監査の入口](tools/audit_plan_completion.py)を開く。研究ワークスペースで `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/audit_plan_completion.py plan-completion-current-web-20261122` を実行する。現行のブラウザ成果を計画の条件に対応付け、既存の判定と残る一次観測を照合する。

## 現行ビルドで段階別の完了条件を照合する（2026-11-22）

- 完了した項目。第2版の141判定を再現し、第3版に英語発話・歌唱・共有WASMの停止と再開の結果を加えた。英語98,790フレーム、歌唱91,200フレームのネイティブ・オフライン・実時間のPCMはそれぞれ一致した。ネイティブの描画割り当ては各772・713量子でゼロ。現行のWASMとブラウザ採取時のWASM、および実行時ソース54ファイルを照合した。[第3版の事前登録](cases/plan-completion-evidence.json)・[監査記録](notes/plan-evidence-audit.md#第3版-現行のブラウザと描画を照合)
- 未達の条件。第7段階では実録音F2の人手注釈、人によるTSP・CSD試聴、物理MIDIのイベントと対応する音響出力の一次記録が残る。現行のCoreMIDI入出力は各0件。[未確認の観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。ワークスペースと `/tmp` から169判定を再現し、要約はバイト一致。各83実行、1,834出力を照合した。現行Rust 52試験、固定上流17試験、通常のWASM・TypeScript・Viteビルドが通過した。今回の成功3実行の採取物25,359バイトをRTL9210B-CGに保存した。歌唱に存在しない声門系列を要求して最初の監査が停止した事象は再現条件を残した。[再実行のマニフェスト](runs/plan-completion-current-web-20261122-v3-repeat/manifest.json)・[要約](runs/plan-completion-current-web-20261122-v3-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)と[F2の注釈資料](notes/tsp-f2-annotation.md#使い方)を開く。研究ワークスペースで `jq '{test_counts: .current_web.test_counts, coremidi: .current_web.coremidi_endpoints, outstanding: .unverified_evaluation_evidence}' runs/plan-completion-current-web-20261122-v3-repeat/summary.json` を実行する。判定者のCSV、試聴回答、物理MIDIの入力が得られた段階で対応する収録・取込の一次記録から照合を再開する。

## 既存CoreMIDI入力の受動計測を用意する（2026-11-22）

- 完了した項目。入力の固有IDを取得し、同じ入力をCoreMIDIの受信クライアントと通常のWeb MIDI画面で観測する入口を追加した。仮想対照の押鍵とベロシティ0の離鍵でバイト列が一致し、保持音57と220 Hzの目標、採用フレーム、CLIとブラウザのPCMを照合した。[事前登録](cases/worklet-midi-coremidi-passive.json)・[実装と手順](notes/worklet-midi-coremidi-passive.md)
- 未達の条件。現行のCoreMIDI入出力は各0件で、物理鍵盤の一次記録が残る。実録音F2の人手注釈と、人によるTSP・CSDの試聴回答も未登録。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。仮想対照の2回は各12判定、従来経路は26判定が通った。入力なしでは取得判定が不合格になり、未観測の記録を保存した。独立検算で1,146入力・32出力とPCMを照合し、実体44,117,519バイトをRTL9210B-CGに保存した。[受動観測の再実行](runs/worklet-midi-coremidi-passive-fixture-20261122-repeat/summary.json)・[入力なし](runs/worklet-midi-coremidi-passive-no-input-20261122/summary.json)
- 次に開くファイルと実行するコマンド。[実機の受動計測](notes/worklet-midi-coremidi-passive.md#実行と結果)を開き、研究ワークスペースで `/usr/bin/xcrun swift tools/capture_coremidi_source.swift --list-inputs` を実行する。物理鍵盤が列挙された時点で `--physical-source <UID>` の通常入口へ通し、F2注釈・試聴のCSVも到着したものから対応する資料IDで照合する。

## CSD試聴回答を資料IDで照合する（2026-11-22）

- 完了した項目。第2版のCSD試聴ページと記入用CSVの全行に、18 WAVと音源対応のSHA-256で求めた資料IDを付けた。取込時にIDを再計算し、異なる資料・混在するID・ID列欠落を拒否する。18 WAVと対応表は第1版と一致した。[生成条件](cases/csd-listening.json)・[検証記録](notes/csd-listening-packet-id.md)
- 未達の条件。人によるCSD・TSPの回答、実録音F2の手動注釈、物理MIDIの一次記録は未取得。現行のCoreMIDI入出力は各0件。[未確認の観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。ワークスペースと `/tmp` から生成13判定と回答検証14判定を再現し、各要約が同一。第1版の11判定、通常取込、固定上流のビブラート試験も通過した。資料IDを変えたCSVの拒否を保存し、7実行の216入力・74出力と音声のハッシュを照合した。成果の実体7,328,317バイトをRTL9210B-CGに保存した。[資料](runs/csd-listening-packet-20261122-a/manifest.json)・[回答検証の再実行](runs/csd-listening-packet-responses-20261122-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[CSD第2版の試聴ページ](runs/csd-listening-packet-20261122-a/artifacts/listening/index.html)と[集計手順](notes/csd-listening-responses.md#再現と回答の集計)を開く。実際のCSVが届いたら、研究ワークスペースから `tools/collect_csd_listening_responses.py` に `--package-run csd-listening-packet-20261122-a` と匿名の回答ID・CSVを渡す。TSP・F2の回答、物理鍵盤も対応する一次記録が得られた段階で照合する。

## TSPの人手F2注釈を受け付ける条件を検証する（2026-11-22）

- 完了した項目。TSPのF2注釈の受け付けで、資料に同梱した試験回答と空の雛形を人の回答として登録できた問題を再現し、修正した。行順や文字コードの表記を変えた同一の試験回答も拒否した。実録音の測定・判断困難・音声不適の件数を合成対照と分けて記録できる。[事前登録](cases/tsp-f2-annotation.json)・[受け付けの検証](notes/tsp-f2-human-intake.md)
- 未達の条件。実録音6窓への人手注釈、TSP・CSDの人による試聴、物理鍵盤の記録は未取得。現行CoreMIDI入出力は各0件。[資料と必要な一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。試験入力を通常の合成区分で集計すると従来の全窓と一致した。ワークスペースと `/tmp` の再実行で、既知の試験回答の拒否を再現。固定上流の欠測試験1件が通過し、7実行の80入力・8出力を独立照合した。成果の実体3,950バイトをRTL9210B-CGに保存した。[試験入力の再実行](runs/tsp-f2-intake-synthetic-repeat-20261122/summary.json)・[拒否の記録](runs/tsp-f2-intake-reject-rewritten-repeat-20261122/manifest.json)
- 次に開くファイルと実行するコマンド。[F2の判定者向けページ](runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)と[集計手順](notes/tsp-f2-annotation.md#使い方)を開く。実際の回答を受領したら、研究ワークスペースで `tools/measure_tsp_f2_annotation.py collect` に `--packet tsp-f2-annotation-20261122-repeat --kind human` と該当のCSVを渡し、資料IDと録音窓の判定を照合する。

## 第7段階の一次記録の照合を更新する（2026-11-22）

- 完了した項目。第4版の56実行と16項目を保持し、受動MIDI、CSD試聴、F2試験注釈の5実行を追加した。MIDIの受信バイトと128,000標本のPCM、CSDの18 WAVと試験CSV、F2の録音窓の判定件数を元ファイルから照合した。入力なしと回答の拒否4件も各実行の記録と照合した。[事前登録](cases/plan-evidence-stage7.json)・[読解と実測](notes/plan-evidence-stage7.md#第5版の照合)
- 未達の条件。実録音F2の人手注釈と、人によるTSP・CSDの試聴回答は未登録。CoreMIDI入出力は各0件で、物理鍵盤のイベントと音響出力は未観測。[資料と取得手順](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各102判定が通過し、要約はバイト一致した。61実行の2,162出力、現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常Webビルドを照合した。監査2実行の642入力と12出力を再検証し、24,431バイトのログをRTL9210B-CGに保存した。[再実行の要約](runs/stage7-evidence-update-20261122-v5-repeat/summary.json)・[マニフェスト](runs/stage7-evidence-update-20261122-v5-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)から、回答や物理入力に対応する資料と収録手順を開く。監査結果は研究ワークスペースで `jq '.coverage | {intake_followup, native_midi_endpoints, unverified_evaluation_evidence}' runs/stage7-evidence-update-20261122-v5-repeat/summary.json` を実行して確認する。新しい一次記録が得られたものから個別の取込または収録を実行する。

## CSD試聴の人手回答を登録する条件を検証する（2026-11-22）

- 完了した項目。人手区分を指定した取込で、空欄と既知の試験回答を集計前に拒否するようにした。書式違い、第1版、複数入力の途中の拒否を確認した。通常区分と試験区分で従来の件数と音源への対応を再現した。拒否時も匿名IDに対応する入力のサイズとハッシュを記録する。[事前登録](cases/csd-listening-responses.json)・[読解と実測](notes/csd-listening-packet-id.md#人手回答として受け付ける条件)
- 未達の条件。実際のCSD試聴回答は未取得。実録音F2の人手注釈、TSPの試聴回答、物理MIDIのイベントと音響出力も未取得。確認時に接続されたCoreMIDI入力は0件だった。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各16判定で要約が一致し、第1版13判定と固定上流のビブラート試験1件が通過した。5条件の拒否で集計を保存しなかった。比較前2実行と確定10実行の391入力・33出力を照合し、採取物44,591バイトをRTL9210B-CGに保存した。[確定版の再実行](runs/csd-human-intake-verify-final-repeat-20261122/manifest.json)・[複数入力の拒否](runs/csd-human-intake-reject-final-batch-20261122/manifest.json)
- 次に開くファイルと実行するコマンド。[試聴ページ](runs/csd-listening-packet-20261122-a/artifacts/listening/index.html)と[集計手順](notes/csd-listening-responses.md#再現と回答の集計)を開く。回答を受領したら研究ワークスペースで `../../.venv/bin/python tools/collect_csd_listening_responses.py` に新しい実行ID、`--package-run csd-listening-packet-20261122-a --kind human` と `--response` に匿名ID・CSVを渡し、原本の区間別回答と集計を照合する。

## Chirp cascadeの押鍵直後の放射差を切り分ける（2026-11-22）

- 完了した項目。呼気0で口腔食道腔の断面が縮み、圧力が立ち上がった後、6内部サンプル目に放射が現れることを、通常CLIと固定上流で再現した。最初の16点は先行のMIDI実行と一致した。追従を0にすると放射が消えた。最初の差は同じ流量を刻みで割るか標本レートを掛けるかによる末尾1ビットだった。[事前登録](cases/songbird-chirps-onset-radiation.json)・[読解と実測](notes/songbird-chirps-onset-radiation.md)
- 未達の条件。乗算での再計算でも、8内部サンプル後には放射流量そのものの差が残った。負荷の圧力・流量で最初に分かれた演算は未確認。第7段階の試聴、実録音のF2人手注釈、物理鍵盤のイベントと音響出力も未取得で、今回の照会でCoreMIDI入力は0件だった。[観測の残り](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。第1版の31判定を保持した。第2版は研究ワークスペースと `/tmp` の各34判定を通過し、要約が一致した。固定上流の鳴禽を含む7試験も通過。断面・圧力と放射微分16点、3実行の394入力・42出力を独立に照合した。採取物2,666,757バイトをRTL9210B-CGに保存した。[第2版の再実行](runs/songbird-chirps-onset-radiation-20261122-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[再実装の並列R–L負荷](crates/vocal-core/src/airway.rs#L89)と[上流のくちばし端の更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1125)を開く。研究ワークスペースで `jq '.derivative_replay, .variants.archived.first_differences' runs/songbird-chirps-onset-radiation-20261122-repeat/summary.json` を実行する。同じ16点の負荷への入力圧と枝流量を照合する。

## Chirp cascadeのくちばし入口と放射負荷を照合する（2026-11-22）

- 完了した項目。通常CLIにくちばし全6セルの圧力・断面・流入枝の観測を追加し、固定上流の同じ位置を測った。入口枝の最初の流量差は押鍵4内部サンプル後の慣性の時間正規化で再現した。放射負荷のコンプライアンスの時間正規化を揃えると8内部サンプル後の流量差が消え、加減算の括りも揃えると終端への流入が分かれる直前まで圧力と流量が一致した。追従0は圧力・流量ともに全点ゼロ。[事前登録](cases/songbird-chirps-beak-load.json)・[読解と検証](notes/songbird-chirps-onset-radiation.md#くちばし入口と放射負荷の丸めを分ける)
- 未達の条件。押鍵9内部サンプル後からは終端へ入る流量が分かれる。この比較は192 kHzでの押鍵直後16点を扱った。人による試聴、実録音F2の注釈、物理MIDIの一次記録は未取得。CoreMIDI入力は今回も0件だった。[残る観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。第1版29判定を保存した。確定版は作業ツリーと `/tmp` から各36判定を通過し、要約と採取CSVが一致した。上流6試験と現行Rust 52試験が通過。第2版初期の保存失敗2件を含む5実行の688入力・63出力を照合し、採取物5,199,945バイトをRTL9210B-CGに保存した。[初回の保存失敗](runs/songbird-chirps-beak-load-20261122-b/manifest.json)・[確定版の再実行](runs/songbird-chirps-beak-load-20261122-c-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[第7段階の監査ケース](cases/plan-evidence-stage7.json)と[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)を開く。研究ワークスペースで `jq '.rounding_replay, .hypotheses' runs/songbird-chirps-beak-load-20261122-c-repeat/summary.json` を実行して今回の照合を確認する。回答または物理入力が得られたものは、対応する試聴資料・注釈窓・収録条件から一次記録を照合する。

## 第7段階に鳴禽の放射と試聴の照合を追加する（2026-11-22）

- 完了した項目。第5版の16項目・61実行を保持し、鳴禽の放射とTSP・CSDの試聴の6実行を追加した。鳴禽の圧力・枝流量の差、TSPの36 WAVと回答、CSDの試験CSVと採点を元ファイルから照合した。採取後に止まった鳴禽の2実行と人手区分の拒否4実行も確認した。[事前登録](cases/plan-evidence-stage7.json)・[読解と結果](notes/plan-evidence-stage7.md#第6版の照合)
- 未達の条件。実録音のF2注釈とTSP・CSDの人による試聴回答は未登録。CoreMIDI入出力は各0件で、物理鍵盤のイベントと対応する音響出力は未観測。[資料と取得手順](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各126判定を通過し、要約はバイト一致した。67実行の2,250出力を照合し、現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常のWebビルドが通過した。監査2実行の680入力・12出力を確認し、24,305バイトの採取ログをRTL9210B-CGに保存した。[再実行の要約](runs/stage7-evidence-update-20261122-v6-repeat/summary.json)・[マニフェスト](runs/stage7-evidence-update-20261122-v6-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)にある該当の資料と手順を開く。研究ワークスペースで `jq '.coverage | {renewal, native_midi_endpoints, unverified_evaluation_evidence}' runs/stage7-evidence-update-20261122-v6-repeat/summary.json` を実行すると今回の要約と一次記録の取得状況を確認できる。人の回答または物理MIDIの入力が得られた時点で、個別の登録・収録を行う。

## TSPの試験回答を記入内容で照合する（2026-11-22）

- 完了した項目。既知の試験回答が空欄行の増減・所見の空白と改行の変更で旧版の人手区分を通ることを再現した。更新後は記入済みの観測を照合し、書式を変更した3条件を、空欄と複数回答の途中の拒否と合わせて確認した。試験入力の記入数・テンポと間の票は元の集計に一致した。[事前登録](cases/tsp-listening-intake-equivalence.json)・[読解と実測](notes/tsp-active-duration-original.md#人手回答と試験回答の記入内容を照合する)
- 未達の条件。TSP・CSDの人による試聴、実録音F2の人手注釈、物理鍵盤のイベントと対応する音響出力は未取得。物理MIDIの入力一覧は空だった。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各5判定を再現し、固定上流のTSP 6試験が通過した。5件の拒否で集計の出力は0件。元の試験回答の集計はバイト一致した。比較前と確定版の10実行で402入力と30出力、取込CSVのサイズとSHA-256を照合し、13,046バイトの採取物をRTL9210B-CGに保存した。[確定版の要約](runs/tsp-listening-intake-equivalence-20261122-final-repeat/summary.json)・[通常の試験集計](runs/tsp-listening-intake-equivalence-20261122-final-synthetic/manifest.json)
- 次に開くファイルと実行するコマンド。[TSP試聴ページ](runs/tsp-listening-responses-20261122-final/artifacts/listening/index.html)と[回答の取込手順](notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)を開く。人の試聴回答を受領したら、研究ワークスペースで `tools/measure_tsp_listening.py collect` に新しい実行IDと `--packet tsp-listening-responses-20261122-final --kind human`、匿名IDを付けたCSVを渡す。

## 試聴回答の集計実行を第7段階の監査に接続する（2026-11-23）

- 完了した項目。TSPとCSDの人手区分の集計実行を、資料・元のWAV・回答CSVに照合する入口を用意した。通常入口で試験区分の2実行を拒否し、隔離した試験入力で片方だけの登録と資料ID・元CSVのハッシュ・集計の不一致を確認した。第6版の67実行と16項目を保持し、TSPの取込に関する2実行を追加した。[事前登録](cases/plan-evidence-stage7.json)・[読解と実行手順](notes/plan-evidence-stage7.md#第7版で試聴回答の実行を照合する)
- 未達の条件。実際のTSP・CSD試聴回答と実録音F2の人手注釈は未登録。CoreMIDI入出力は各0件で、物理鍵盤のイベントと音響出力が残る。[評価資料と取得手順](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。ワークスペースと `/tmp` の各128判定で要約が一致した。69実行の2,262出力を照合し、現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常Webビルドが通過した。拒否の対照を含む3実行の1,042入力・13出力を検証し、監査ログ24,300バイトをRTL9210B-CGに保存した。[再実行の要約](runs/stage7-evidence-update-20261123-listening-repeat/summary.json)・[試験集計の拒否](runs/stage7-evidence-update-20261123-listening-reject-fixtures/manifest.json)
- 次に開くファイルと実行するコマンド。[評価資料と取得手順](notes/plan-evidence-stage7.md#未確認の観測)を開く。試聴CSVの収集後、研究ワークスペースで `tools/audit_stage7_evidence.py` に実行IDと、対応する `--tsp-listening-run` または `--csd-listening-run` を渡す。監査要約の `coverage.human_listening` で提出行・記入行と観測の区分を照合する。

## 実録音のF2注釈を第7段階の監査に接続する（2026-11-23）

- 完了した項目。F2注釈実行を資料ID、WAVと図、元CSV、録音の標本窓へ結び付け、中央値と判定者間の範囲を再計算した。比較可能な窓で上流既定とプリエンファシス無適用のF2偏差を求める。試験集計と、所見の改行を変えた既知の試験回答は通常入口で拒否した。[事前登録](cases/plan-evidence-stage7.json)・[読解と実行手順](notes/plan-evidence-stage7.md#第8版でf2注釈を照合する)
- 未達の条件。実録音6窓の人手F2注釈、TSP・CSDの人による試聴回答は未取得。CoreMIDI入出力は各0件で、物理鍵盤のイベントと対応する音響出力も未観測。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。ワークスペースと `/tmp` から各128判定が通り、要約と入力一覧が一致した。第7版の16項目・69実行を保持した。通常Rust 52試験、固定上流の比較19試験、MIDI 2試験、Webビルドが通過した。5実行の1,069入力・17出力を照合し、採取物26,023バイトをRTL9210B-CGに保存した。[再実行の要約](runs/stage7-evidence-update-20261123-f2-repeat/summary.json)・[試験集計の拒否](runs/stage7-f2-20261123-reject-synthetic/summary.json)
- 次に開くファイルと実行するコマンド。[評価ページと取込手順](notes/tsp-f2-annotation.md#使い方)を開く。実回答を取り込んだ後、研究ワークスペースで `tools/audit_stage7_evidence.py` に新しい実行IDと `--f2-annotation-run`、保存した注釈実行のIDを渡す。要約の `coverage.human_f2_annotations` で取得した録音窓と比較可能な窓を照合する。

## 物理MIDIの受動計測を第7段階の監査に接続する（2026-11-23）

- 完了した項目。計測時の入力UID・機器一覧、信頼済みWeb MIDI、押鍵・離鍵の保持時間、Workletの採用フレームとPCMを照合する入口を追加した。2種類の離鍵形式を仮想対照で検算し、仮想入力と入力欠測を物理MIDIの証拠として拒否した。[事前登録](cases/plan-evidence-stage7.json)・[読解と検証結果](notes/plan-evidence-stage7.md#第9版で物理midiの収録を照合する)
- 未達の条件。CoreMIDI入出力は各0件で、物理鍵盤による通常画面からの収録は未実施。実録音F2の注釈、TSP・CSDの人による試聴回答も未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各128判定が通り、要約と入力一覧は一致した。16項目・69実行・2,262出力を照合し、現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常Webビルドが通過した。4実行の1,416入力・14出力を照合し、採取ログ24,120バイトをRTL9210B-CGに保存した。[再実行の要約](runs/stage7-evidence-update-20261123-midi-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[実機の受動計測](notes/worklet-midi-coremidi-passive.md#実行と結果)を開く。研究ワークスペースから `/usr/bin/xcrun swift tools/capture_coremidi_source.swift --list-inputs` を実行し、接続機器が列挙されたら `--physical-source` で収録して `--physical-midi-run` で監査する。先に届いた人手の回答は対応する資料IDから照合する。

## くちばし端への最初の流入差を直列枝で再現する（2026-11-23）

- 完了した項目。192 kHzの通常CLIと固定上流から押鍵・追従0を再実行した。最後の枝の64点を独立計算でビット再現した。押鍵9内部サンプル後は先端側の圧力差の寄与が丸めで一致し、前回運動量の時間換算を入れ替えると上流流量が再現された。先端側の前回圧だけで再現する予測は不成立として保存した。[事前登録](cases/songbird-chirps-beak-tip-inflow.json)・[読解と比較](notes/songbird-chirps-onset-radiation.md#最後の直列枝で運動量の時間換算を照合する)
- 未達の条件。流量差の説明は192 kHzの押鍵直後16点に限る。CoreMIDI入力の一覧は空で、物理鍵盤の観測、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各10判定が通り、要約と64点の再計算系列が一致した。現行Rust 52試験と固定上流6試験も通過した。2実行の276入力と22出力を照合し、採取物2,014,450バイトをRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-beak-tip-inflow-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[枝の読解](notes/songbird-chirps-onset-radiation.md#最後の直列枝で運動量の時間換算を照合する)を開き、研究ワークスペースで `jq '{hypotheses, first_difference, term_substitutions}' runs/songbird-chirps-beak-tip-inflow-20261123-repeat/summary.json` を実行する。追加のレートを比較する際は同じ音高・形状で枝の圧力、運動量、流量を比較する。実機入力または人の回答が得られたものは該当の一次資料から第7段階の監査へ登録する。

## 44.1 kHz出力相当で鳴禽の流入差を比較する（2026-11-23）

- 完了した項目。176.4 kHzで全6セルのくちばし断面を保ち、制御時間をそろえた235点、通常の256点、追従0の3条件で両版の枝流量を計96点ビット復元した。235点では押鍵8点後の差を手前のセル圧で説明でき、256点では7点後の差をセル圧または運動量項で再現した。両条件で運動量項だけで説明できる予測は235点で外れた。[事前登録](cases/songbird-chirps-beak-tip-inflow-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#441-khz出力相当で最初の流入差を比較する)
- 未達の条件。235点で先行した、押鍵1内部点後の口腔食道腔圧の差が生じる演算は未分離。物理MIDIの接続入力は0件で、実機のイベント・音声、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各14判定が通り、要約と採取CSVが一致した。共通化した192 kHzの回帰は10判定に合格し、前回の要約と系列にバイト一致した。現行Rust 52試験と固定上流6試験が通過した。3実行の416入力・43出力を照合し、採取物3,348,261バイトをRTL9210B-CGに保存した。[176.4 kHzの再実行](runs/songbird-chirps-beak-tip-inflow-44100-20261123-repeat/summary.json)・[192 kHzの回帰](runs/songbird-chirps-beak-tip-inflow-20261123-rate-regression/summary.json)
- 次に開くファイルと実行するコマンド。[176.4 kHzの比較ノート](notes/songbird-chirps-onset-radiation.md#441-khz出力相当で最初の流入差を比較する)を開く。研究ワークスペースで `jq '.hypotheses, (.conditions.matched_time.first_difference)' runs/songbird-chirps-beak-tip-inflow-44100-20261123-repeat/summary.json` を実行する。235点条件の口腔食道腔を調べる場合は押鍵直後2点の体積差・注入流量・節点圧を照合する。実機や人の回答が得られたら対応する資料から第7段階の監査へ登録する。

## 176.4 kHzの口腔食道腔で圧力差の起点を確認する（2026-11-23）

- 完了した項目。通常CLIに `observe_oec` を追加し、両枝の流量を採取した。3条件・両版の腔圧96点をビット再現した。235点制御の押鍵1内部点後に生の体積速度が1 ULP分かれ、換算だけを乗算に揃えると腔圧の2 ULP差が再現した。256点制御では収支の差が圧力増分の丸めで消えた。[事前登録](cases/songbird-chirps-oec-pressure-44100.json)・[読解と置換比較](notes/songbird-chirps-onset-radiation.md#1764-khzの口腔食道腔で最初の圧力差を再現する)
- 未達の条件。体積速度の換算を変えて全区間を描画したときの放射までの伝播は未検証。CoreMIDI入力は0件で、物理MIDIの収録、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各27判定が通り、要約・観測列・再計算が一致した。現行Rust 52試験、固定上流9試験が通過した。2実行の286入力・32出力を照合し、採取物2,471,317バイトをRTL9210B-CGへ保存した。参考マニフェストのハッシュを誤記した初回は採取前に停止した。[再実行の要約](runs/songbird-chirps-oec-pressure-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[口腔食道腔の読解](notes/songbird-chirps-onset-radiation.md#1764-khzの口腔食道腔で最初の圧力差を再現する)を開く。研究ワークスペースで `jq '.hypotheses, .conditions.matched_time' runs/songbird-chirps-oec-pressure-44100-20261123-repeat/summary.json` を実行する。次に放射への伝播を調べる場合は235点制御で体積速度の換算だけを替え、腔圧、くちばし端、放射を同じ16点で比較する。実機または人の回答が得られたら該当する資料を第7段階の監査に通す。

## 体積速度換算の差を連続描画で放射まで追う（2026-11-23）

- 完了した項目。外部ディスク上の隔離ビルドで換算の1行だけを乗算に替えた。176.4 kHzの235点制御で固定上流との腔圧の初差が1点後から14点後に、放射流量が8点後から11点後に移った。最初に残るくちばし内部枝の差は前回運動量の時間換算、押鍵9点後の放射微分差は時間差分の換算で再現した。[事前登録](cases/songbird-chirps-volume-rate-propagation-44100.json)・[読解と連続描画](notes/songbird-chirps-onset-radiation.md#体積速度の換算を替えて放射まで追う)
- 未達の条件。残るくちばし内部枝の演算を変更した連続描画は未検証。物理MIDI入力は0件で、実機のイベントと音声、実録音のF2注釈、人によるTSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各17判定が通り、要約・入力一覧・採取CSVと両バイナリのSHA-256が一致した。通常版は保存済みCSVを再現し、実験版の注入と腔圧は各48点を独立計算で復元した。3実行の435入力と30出力を照合し、採取物1,839,617バイトをRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-volume-rate-propagation-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[連続描画の読解](notes/songbird-chirps-onset-radiation.md#体積速度の換算を替えて放射まで追う)を開く。研究ワークスペースで `jq '.hypotheses, .conditions.matched_time.first_residual_interior_beak_branch' runs/songbird-chirps-volume-rate-propagation-44100-20261123-repeat/summary.json` を実行する。続く描画対照では今回の乗算版を基準に、内部枝の運動量の換算だけを変更する。実機または人の回答が得られたら該当する資料を第7段階の監査に通す。

## くちばし内部の運動量の換算順を連続描画で比較する（2026-11-23）

- 完了した項目。隔離ビルドに前回の体積速度の乗算を適用してから、内部5枝の運動量の計算順だけを替えた。235点制御では2番目のセルへの流入差が3点後から5点後に移った。先端セルへの流入差は9点後のまま、放射流量差は11点後から10点後へ早まり、予測は外れた。入口4点後の差を線形係数で復元し、放射の残差は終端の流入を替える対照で切り分けた。256点制御の放射流量は全16点で上流と一致した。[事前登録](cases/songbird-chirps-beak-momentum-propagation-44100.json)・[読解と比較](notes/songbird-chirps-onset-radiation.md#くちばし内部5枝で運動量の計算順を替える)
- 未達の条件。くちばし入口の線形係数を替えた連続描画は未実施。物理MIDIの入力は0件で、実機のイベントと音声、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各22判定が通り、要約・入力一覧・採取CSVと両ビルドのSHA-256が一致した。3実行の444入力と27出力を照合し、採取物1,635,503バイトをRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-beak-momentum-propagation-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[入口と終端の比較](notes/songbird-chirps-onset-radiation.md#くちばし内部5枝で運動量の計算順を替える)を開く。研究ワークスペースから `jq '.hypotheses, (.conditions.matched_time | {first_beak_inlet_replay, terminal_load_comparison})' runs/songbird-chirps-beak-momentum-propagation-44100-20261123-repeat/summary.json` を実行する。続く描画対照では入口枝の線形係数のみを変更する。物理入力または人の回答が得られたら該当する資料を監査する。

## くちばし入口枝の線形係数を連続描画で揃える（2026-11-23）

- 完了した項目。隔離ビルドで、内部5枝の運動量を揃えた対照に入口枝の線形係数の乗算だけを加えた。235点制御で入口流量の初差は4点後から5点後、放射流量の初差は10点後から11点後へ移った。残る入口の差は前回運動量の時間換算で再現した。256点制御と追従0では対照と実験版のCSVがバイト一致した。[事前登録](cases/songbird-chirps-beak-inlet-rate-propagation-44100.json)・[読解と比較](notes/songbird-chirps-onset-radiation.md#くちばし入口の線形係数だけを揃える)
- 未達の条件。くちばし入口の前回運動量項を変更した連続描画は未実施。CoreMIDI入力は0件で、物理MIDIの収録、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各28判定が通り、入力一覧・要約・CSV・差分・入口流量の再計算系列と両ビルドのSHA-256が一致した。3条件の対照・実験版・固定上流で入口流量144点を再現した。2実行の304入力と20出力を照合し、採取物1,291,086バイトをRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-beak-inlet-rate-propagation-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[入口の係数と運動量の比較](notes/songbird-chirps-onset-radiation.md#くちばし入口の線形係数だけを揃える)を開く。研究ワークスペースで `jq '.hypotheses, .conditions.matched_time.first_residual_inlet_replay' runs/songbird-chirps-beak-inlet-rate-propagation-44100-20261123-repeat/summary.json` を実行する。次に入口を変更する場合は前回運動量の時間換算だけを切り替える。実機の収録または人の回答が届いたら、対応する資料から第7段階の監査へ登録する。

## くちばし入口の前回運動量を連続描画で揃える（2026-11-23）

- 完了した項目。隔離ビルドの入口1枝で運動量の時間換算を揃えた。235点・256点制御ではくちばし全6セルの圧力・流入と放射流量が固定上流と全16点一致した。保存流量の差を上流の式で再計算すると放射微分も16点一致した。235点で15点後に残った腔圧差は節点収支の加算順を揃える1更新で復元した。[事前登録](cases/songbird-chirps-beak-inlet-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#くちばし入口の前回運動量を揃える)
- 未達の条件。気管側の首部流量は235点制御で4点後、256点制御で5点後から差が残る。235点制御で15点後に現れた腔圧差の後続伝搬は観測窓外。物理MIDIの入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各28判定が通り、入力・要約・CSV・差分・再計算と両バイナリのSHA-256が一致した。2実行の310入力と20出力を照合し、採取物1,287,274バイトをRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-beak-inlet-momentum-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[残った腔圧の照合](notes/songbird-chirps-onset-radiation.md#くちばし入口の前回運動量を揃える)を開く。研究ワークスペースで `jq '.hypotheses, .conditions.matched_time.first_residual_pressure_replay' runs/songbird-chirps-beak-inlet-momentum-44100-20261123-repeat/summary.json` を実行する。後続伝搬を調べる場合は235点条件で観測窓を延ばし、腔の収支順を切り替える。実機の収録または人の回答を受領したものは対応する資料から第7段階の監査へ登録する。

## 腔の流量収支の順序を替えて観測を64点へ延ばす（2026-11-23）

- 完了した項目。235点制御では腔圧の最初の差が15点後から33点後へ、くちばし入口流量の差が16点後から29点後へ移った。放射流量の初差は18点後のままで、保存した終端流入を固定して上流の括りへ替えた独立計算では28点後へ移った。256点制御では実験版の腔圧差が54点後から45点後へ早まり、放射流量の初差は23点後で同じだった。[事前登録](cases/songbird-chirps-oec-sum-order-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#口腔食道腔の流量収支を上流順に揃えて64点を観測する)
- 未達の条件。終端の係数の括りを変更して描画した場合に、先端圧の差がくちばし内部へ戻る位置は未検証。気管側首部の残差も残る。物理MIDI入力は0件で、実機の入出力記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。固定上流・対照は前回の16点を再現し、対照・実験版・上流の腔圧と入口流量を各576点照合した。研究ワークスペースと `/tmp` で各46判定が通り、3実行の477入力と54出力を照合した。採取物6,350,902バイトをRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[終端負荷の切り分け](notes/songbird-chirps-onset-radiation.md#口腔食道腔の流量収支を上流順に揃えて64点を観測する)を開く。研究ワークスペースで `jq '.hypotheses, .conditions.matched_time.terminal_operation_swaps' runs/songbird-chirps-oec-sum-order-44100-20261123-repeat/summary.json` を実行する。次に連続描画を調べる場合は終端負荷の分子側の括りを揃える。実機または人手の記録は対応する資料から第7段階の監査へ登録する。

## 先端負荷の分子係数を揃えて枝へ戻る差を測る（2026-11-23）

- 完了した項目。隔離されたRustビルドでくちばし先端の旧圧係数の括りだけを揃えた。176.4 kHzの235点制御では、固定上流との放射流量の初差が押鍵18点後から60点後へ移った。対照への変更の影響は18点後の先端圧から23点後の最後の枝流量へ戻り、前回先端圧の置換で復元できた。256点制御では放射流量の初差が23点後から24点後へ移った。[事前登録](cases/songbird-chirps-terminal-numerator-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#くちばし先端負荷の分子係数を連続描画で揃える)
- 未達の条件。235点制御の気管側首部流量は4点後、腔圧とくちばし入口流量は53点後に上流との差が残った。放射微分は235点制御で9点後、256点制御で11点後から差が残る。CoreMIDI入力は0件で、物理MIDIの記録、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各58判定を通過し、要約、CSV、差分、両ビルドのSHA-256を再現した。独立照合で306入力・18出力を確認し、採取物1,455,878バイトをRTL9210B-CGに保存した。Cargoログは並行ビルド順、一時パス、所要時間が異なった。現行Rust 52試験、固定上流9試験が通過した。[再実行の要約](runs/songbird-chirps-terminal-numerator-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[先端負荷と気管側の残差](notes/songbird-chirps-onset-radiation.md#くちばし先端負荷の分子係数を連続描画で揃える)を開き、`jq '.conditions.matched_time | {first_return, neck: .terminal_numerator_minus_upstream.oec_neck_inflow_cm3_s}' runs/songbird-chirps-terminal-numerator-44100-20261123-repeat/summary.json` で前回状態を確認する。次は235点制御の押鍵後5点で気管側首部の前後の圧力と枝係数を採り、4点後の差を局所置換する。実機または人手の記録は第7段階の監査へ登録する。

## 気管側の首部流量を前回運動量まで分解する（2026-11-23）

- 完了した項目。通常CLIに `observe_oec_neck` を加え、176.4 kHz・3条件と固定上流の押鍵後16点を採取した。235点制御では4点後、256点制御では5点後に現れた首部流量の最初の1 ULPを、前回運動量の時間換算だけの置換で復元した。両条件の直前の気管端圧・腔圧・首部流量は上流と一致した。[事前登録](cases/songbird-chirps-oec-neck-44100.json)・[読解と比較](notes/songbird-chirps-onset-radiation.md#気管側の首部流量で最初の差を切り分ける)
- 未達の条件。首部の演算順を替えた連続描画と、気管端圧・腔圧・放射への後続の影響は未検証。今回のCoreMIDI入力は0件で、物理MIDIの記録、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各27判定を通過し、両版の流量96点をビット照合した。308入力と28出力のハッシュを確認し、採取物2,593,490バイトをRTL9210B-CGに保存した。上流の採取プログラムの実行ファイルには実行先パスの差があり、機械語セクションの一致を確認した。現行Rustの52試験と固定上流の気道6試験が通過した。[再実行の要約](runs/songbird-chirps-oec-neck-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[首部の初差](notes/songbird-chirps-onset-radiation.md#気管側の首部流量で最初の差を切り分ける)を開き、`jq '.conditions.matched_time.first_flow_diagnosis | {offset, different_terms, term_swaps}' runs/songbird-chirps-oec-neck-44100-20261123-repeat/summary.json` で置換結果を確認する。次は首部1枝の運動量換算だけを替え、押鍵後64点で気管端圧、腔圧、くちばしと放射を照合する。

## 気管側首部の持ち越し換算を64点で比較する（2026-11-23）

- 完了した項目。隔離したRustビルドで気管側の首部1枝の持ち越し換算だけを揃えた。176.4 kHzの235点制御で上流との首部流量の初差は押鍵4点後から6点後、256点制御で5点後から25点後になった。235点制御の腔圧は38点後に対照と分かれ、放射流量とくちばし全6セルは対照と全64点一致した。256点制御で対照と最初に異なる放射流量は61点後だった。[事前登録](cases/songbird-chirps-oec-neck-momentum-44100.json)・[読解と比較](notes/songbird-chirps-onset-radiation.md#気管側首部の前回運動量を連続描画で揃える)
- 未達の条件。235点制御で残った6点後の流量差は線形慣性項の単独置換で復元済みで、その変更を適用した連続描画が残る。256点制御では13点後から上流と異なる気管端圧の起点が未分離。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各60判定を通過し、首部流量・腔圧・先端圧・放射流量と微分を各576点照合した。314入力と36出力のハッシュを確認し、採取物4,600,764バイトをRTL9210B-CGに保存した。要約と採取CSV、差分と候補バイナリが一致した。上流採取バイナリは機械語部分を照合した。現行Rustの52試験と固定上流の気道6試験が通過した。[再実行の要約](runs/songbird-chirps-oec-neck-momentum-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[首部運動量の連続描画](notes/songbird-chirps-onset-radiation.md#気管側首部の前回運動量を連続描画で揃える)を開き、`jq '.conditions.matched_time.first_residual_neck_flow | {offset, different_terms, term_swaps}' runs/songbird-chirps-oec-neck-momentum-44100-20261123-repeat/summary.json` で6点後の残差を確認する。次は首部1枝の線形慣性項だけを変え、6点後の流量差と腔圧・放射への影響を64点で照合する。

## 気管側首部の線形慣性項を64点で比較する（2026-11-23）

- 完了した項目。隔離したRustビルドで首部1枝の線形慣性項だけを `L/dt` から `L × fs` に替えた。235点制御で固定上流との首部流量の初差は6点後から14点後、腔圧は38点後から53点後へ移った。256点制御で上流との差が出る時刻は同じだった。両条件とも放射系列は対照と64点一致した。[事前登録](cases/songbird-chirps-oec-neck-linear-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#気管側首部の線形慣性項を連続描画で揃える)
- 未達の条件。235点制御で12点後、256点制御で13点後に生じた最初の気管端圧差は、起点の切り分けが残る。直前の気管端圧を置換して、14点後および25点後の首部流量の差を復元できた。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各56判定を通過し、首部・腔・先端・放射の独立計算を各576点照合した。比較の共通部は先行実行の要約・再計算系列・46判定を再現した。316入力と20出力のハッシュを照合し、採取物2,576,042バイトをRTL9210B-CGに保存した。両実行の要約、CSV、差分と候補バイナリは一致した。固定上流の気道6試験は通過した。[再実行の要約](runs/songbird-chirps-oec-neck-linear-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[気管端に残る差](notes/songbird-chirps-onset-radiation.md#気管側首部の線形慣性項を連続描画で揃える)を開き、`jq '.conditions.matched_time.first_residual_neck_flow | {offset, pressure_swaps}' runs/songbird-chirps-oec-neck-linear-44100-20261123-repeat/summary.json` で残差を確認する。235点制御の押鍵後13点で、気管末端の前回圧、手前直列枝からの流入、壁流量、首部への流出を採り、12点後の気管端圧を局所計算で照合する。

## 気管末端の圧力差を直列枝と壁の収支で照合する（2026-11-23）

- 完了した項目。通常CLIに気管末端の直列枝流量、壁流量と変位などの観測を加えた。235点制御で押鍵12点後、256点制御で13点後に現れる気管端圧の1 ULP差は、直列枝からの流入だけを替えて復元した。直列枝流量の初差は8点後と13点後で、前回運動量の時間換算の順序だけを揃えて再現した。[事前登録](cases/songbird-chirps-trachea-end-balance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#気管末端の圧力を直列枝と壁の流量に分ける)
- 未達の条件。気管最後の直列枝に運動量換算順の変更を適用した連続描画と、より上流の気管節点の差の起点は未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各47判定を通過し、気管端圧、壁流量・変位、直列枝流量を各96点ビット照合した。通常CLIの既存列も一致した。316入力と28出力のハッシュを照合し、採取物2,711,250バイトをRTL9210B-CGに保存した。現行Rust52試験と固定上流の気道9試験が通過した。[再実行の要約](runs/songbird-chirps-trachea-end-balance-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[気管末端の圧力収支](notes/songbird-chirps-onset-radiation.md#気管末端の圧力を直列枝と壁の流量に分ける)を開き、`jq '.conditions.matched_time | {first_differences, first_pressure_residual, terms: .first_inlet_flow_residual.term_substitutions}' runs/songbird-chirps-trachea-end-balance-44100-20261123-repeat/summary.json` を確認する。次は気管最後の直列枝1本で持ち越し運動量の換算順だけを切り替え、64点で気管端圧・首部流量・腔圧・放射への影響を追う。

## 気管最後の直列枝の運動量換算を64点で比較する（2026-11-23）

- 完了した項目。隔離したRustビルドで気管最後の直列枝1本の運動量換算順を揃えた。上流との流入の初差は235点制御で8点後から13点後、256点制御で13点後から14点後へ移った。256点制御の首部流量差は25点後から16点後へ早まった。両条件とも腔圧・くちばし・放射は対照と全64点一致した。[事前登録](cases/songbird-chirps-trachea-end-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#気管最後の直列枝の運動量換算を連続描画で揃える)
- 未達の条件。235点制御の気管端の一つ手前の圧力が12点後に分かれる起点は未分離。その圧力差の置換で、13点後の最後の枝流入を復元した。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの人による試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各103判定を通過した。固定上流と対照の先頭16点を再現し、両実行の結果系列、差分、候補バイナリは一致した。324入力と36出力のハッシュを照合し、採取物5,182,400バイトをRTL9210B-CGに保存した。上流採取バイナリは機械語部分の一致を確認した。固定上流の気道9試験が通過した。[再実行の要約](runs/songbird-chirps-trachea-end-momentum-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[手前のセル圧の残差](notes/songbird-chirps-onset-radiation.md#気管最後の直列枝の運動量換算を連続描画で揃える)を開き、`jq '.conditions.matched_time.first_residual_tracheal_inflow | {inputs: .first_difference.inputs, term_substitutions}' runs/songbird-chirps-trachea-end-momentum-44100-20261123-repeat/summary.json` を実行する。気管端の一つ手前のセルについて流入、流出、壁流量を押鍵後13点まで採り、12点後の圧力差を照合する。

## 気管セル14の圧力収支を両側の直列枝まで分解する（2026-11-23）

- 完了した項目。内部セル番号を指定する通常CLIの観測を追加した。セル14の圧力差は235点制御の押鍵12点後、256点制御の13点後で、セル13からの流入だけを置換すると両条件で消えた。235点制御の9点後の流入差を前回運動量の換算順、256点制御の12点後の流入差をセル13の前回圧の置換で復元した。[事前登録](cases/songbird-chirps-trachea-interior-balance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#気管端の一つ手前のセルで圧力収支を照合する)
- 未達の条件。セル13から14へ流れる直列枝の運動量換算を変えた全体の連続描画と、256点制御で10点後から残るセル13圧の起点は未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。修正後は研究ワークスペースと `/tmp` で各59判定を通過し、圧力、壁流量、壁変位、流入量の各96点をビット照合した。初回の配列変換エラーを含む480入力と38出力を照合し、採取物3,895,868バイトをRTL9210B-CGに保存した。通常CLIと固定上流の複数セル指定・入力検証、現行Rustの52試験と固定上流の気道9試験を確認した。[再実行の要約](runs/songbird-chirps-trachea-interior-balance-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[気管内部セルの圧力収支](notes/songbird-chirps-onset-radiation.md#気管端の一つ手前のセルで圧力収支を照合する)を開き、`jq '.conditions.matched_time | {first_differences, terms: .first_inlet_flow_residual.term_substitutions}' runs/songbird-chirps-trachea-interior-balance-44100-20261123-repeat/summary.json` を実行する。次はセル13から14への直列枝1本だけの持ち越し運動量の換算を揃え、64点でセル14と15の圧力、首部流量、腔圧と放射を比較する。

## 気管セル14への流入枝の換算順を64点で比較する（2026-11-23）

- 完了した項目。隔離したRustビルドでセル13から14へ入る直列枝1本の持ち越し換算を揃えた。235点制御では流入の初差が押鍵9点後から12点後へ移り、残る差は11点後のセル13圧の置換で消えた。256点制御の初差は12点後のまま。両条件で腔圧、くちばし、放射流量が対照と全64点一致した。[事前登録](cases/songbird-chirps-trachea-interior-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#気管セル13から14へ入る枝の運動量換算を揃える)
- 未達の条件。セル13圧が235点制御で11点後、256点制御で10点後から分かれる原因は未分離。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各157判定が通過した。気管セル14・15の流入・圧力・壁の運動、首部・腔・くちばし先端と放射を各576点ビット照合した。326入力と36出力のハッシュを照合し、採取物7,092,508バイトをRTL9210B-CGに保存した。候補の両バイナリと観測CSVが一致し、固定上流の気道9試験が通過した。[再実行の要約](runs/songbird-chirps-trachea-interior-momentum-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[セル14への流入の残差](notes/songbird-chirps-onset-radiation.md#気管セル13から14へ入る枝の運動量換算を揃える)を開き、`jq '.conditions.matched_time.first_residual_interior_inflow | {inputs: .first_difference.inputs, term_substitutions}' runs/songbird-chirps-trachea-interior-momentum-44100-20261123-repeat/summary.json` を実行する。次は `observe_trachea_interior_cells` にセル13と14を指定し、セル13圧の初差の前後で流入・流出・壁流量を照合する。

## 気管セル13の差を同時観測で切り分ける（2026-11-23）

- 完了した項目。セル13と14を同時観測し、235点制御の押鍵11点後と256点制御の10点後に現れたセル13圧の差を、セル12からの流入だけの置換で復元した。流入の初差は両条件とも持ち越し運動量の換算順だけで再現した。共通の計測CLIはケースファイルを指定して観測点を選べる。[事前登録](cases/songbird-chirps-trachea-cell13-balance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#セル13と14を同時に観測しセル13圧の起点を調べる)
- 未達の条件。運動量の時間換算を一様気管の全直列枝で揃えた場合の連続描画と、壁・放射への影響は未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各102判定に合格した。セル13・14の圧力、流入量、壁流量・変位を各96点ビット照合し、先行ケースの6系列と36判定を再現した。322入力と28出力を照合し、採取物3,180,380バイトをRTL9210B-CGに保存した。固定上流の気道9試験を通過した。[再実行の要約](runs/songbird-chirps-trachea-cell13-balance-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[セル13の収支と置換](notes/songbird-chirps-onset-radiation.md#セル13と14を同時に観測しセル13圧の起点を調べる)を開き、`jq '.conditions | map_values({first_differences, terms: .first_inlet_flow_residual.term_substitutions})' runs/songbird-chirps-trachea-cell13-balance-44100-20261123-repeat/summary.json` を実行する。次は気管内の全15直列枝で運動量の換算だけを揃え、セル13・14・15、首部、腔、放射を押鍵後64点で照合する。

## 全15気管直列枝の運動量換算を64点で比較する（2026-11-23）

- 完了した項目。隔離Rustビルドで同じ運動量の時間換算を気管内の全15直列枝に適用した。気管端圧の初差は235点制御で13点後から34点後、256点制御で14点後から40点後へ移った。気管内で最初に残る圧力差は鳴管側セル0で、同じ標本の左鳴管からの流量だけを置換して復元した。放射流量と微分は対照と全64点一致した。[事前登録](cases/songbird-chirps-trachea-all-momentum-44100.json)・[読解と比較](notes/songbird-chirps-onset-radiation.md#気管内の全直列枝で運動量換算を揃える)
- 未達の条件。左鳴管から気管への流量が235点制御で19点後、256点制御で18点後に初めて分かれる起点は未照合。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各859判定が通過し、全15枝の流量を各576点ビット照合した。328入力と36出力のハッシュを照合し、採取物11,631,244バイトをRTL9210B-CGに保存した。固定上流の気道9試験は通過した。[再実行の要約](runs/songbird-chirps-trachea-all-momentum-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[セル0の最初の圧力差](notes/songbird-chirps-onset-radiation.md#気管内の全直列枝で運動量換算を揃える)を開き、`jq '.results | map_values(.cell_0_pressure)' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-songbird-trachea-all-momentum-20261123.json` を実行する。左鳴管ポートの初差の前後で、弁面積、両側の前回圧と流量、使われた慣性を採り、流量を独立に再計算する。

## 左鳴管ポートの初差を気管支側半セルまで分解する（2026-11-23）

- 完了した項目。先行の通常CLIと固定上流のCSVを使い、左ポートの流量を32点ずつ再計算した。235点制御で押鍵19点後、256点制御で18点後に生じた1 ULP差を、気管支側の半セルの慣性を逆数との乗算で求め、線形項だけを置換すると復元できた。[事前登録](cases/songbird-chirps-left-syrinx-port-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左鳴管ポートの慣性を気管支側の半セルまで分解する)
- 未達の条件。左ポートの半セル慣性の計算順を変更した連続描画は未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各26判定が通過し、両版と3条件の流量192点をビット照合した。共通式で首部の既存6系列も再現した。58入力と4出力のハッシュを照合し、再計算出力364,300バイトをRTL9210B-CGへ保存した。固定上流の気道6試験、リアルタイム処理3試験が通過した。[再実行の要約](runs/songbird-chirps-left-syrinx-port-44100-20261123-repeat/summary.json)
- 次に開くファイルと実行するコマンド。[左ポートの初差](notes/songbird-chirps-onset-radiation.md#左鳴管ポートの慣性を気管支側の半セルまで分解する)を開き、`jq '.conditions | map_values(.first_flow_residual.term_swaps)' runs/songbird-chirps-left-syrinx-port-44100-20261123-repeat/summary.json` を実行する。次に隔離Rustビルドで左ポートの気管支側の半セル項だけを上流の計算順に替え、左ポート流量から気管セル0、首部、放射までを64点で比較する。

## 左鳴管の気管支側半セル慣性を64点で比較する（2026-11-23）

- 完了した項目。左鳴管ポートの気管支側半セルだけで慣性の計算順を揃えた。流量の初差は235点制御で押鍵19点後から23点後、256点制御で18点後から19点後へ移った。気管入口圧の初差は22点後から31点後、27点後から39点後へ移った。両条件で実験と対照の放射流量・差分は全64点で一致した。[事前登録](cases/songbird-chirps-left-syrinx-half-inertance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左鳴管ポートの気管支側半セル慣性を連続描画で揃える)
- 未達の条件。左ポートに残る1 ULP差は235点制御で持ち越し運動量、256点制御で現在の慣性の時間換算の置換で消えた。各変更の連続描画と、右ポートの初差は未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測と資料](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各86判定を通過し、3条件・3版の流量と気管入口圧を各576点ビット照合した。342入力と26出力を照合し、採取物5,324,228バイトをRTL9210B-CGに保存した。既存の局所解析26判定と出力の一致、固定上流の気道・実時間処理9試験を確認した。[再実行の要約](runs/songbird-chirps-left-syrinx-half-inertance-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-syrinx-half-inertance-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[連続描画と残差](notes/songbird-chirps-onset-radiation.md#左鳴管ポートの気管支側半セル慣性を連続描画で揃える)を開き、`jq '.conditions.matched_time.first_residual_port_flow | {offset, different_terms, term_swaps}' runs/songbird-chirps-left-syrinx-half-inertance-44100-20261123-repeat/summary.json` を実行する。この実験差分を対照に加え、235点制御の左ポートだけで持ち越し運動量の時間換算を揃える。左の23点後の差、右ポートの初差、気管入口圧を追う。

## 左鳴管の持ち越し運動量の時間換算を64点で比較する（2026-11-23）

- 完了した項目。左ポートの持ち越し運動量の時間換算だけを揃え、235点制御の左流量の初差を23点後から27点後、気管入口圧の初差を31点後から36点後へ移した。27点後の左流量は直前の左気管支末端圧を置換して復元した。256点制御は19点後の左流量差が残り、現在の慣性の時間換算を置換して復元した。放射流量・差分は対照と64点一致した。[事前登録](cases/songbird-chirps-left-syrinx-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左鳴管の持ち越し運動量の時間換算を連続描画で揃える)
- 未達の条件。256点制御の左ポートで現在の慣性の時間換算を揃えた連続描画と、235点制御の26点後の左気管支末端圧の起点は未検証。右ポートの換算は局所置換まで確認した。物理MIDI入力は0件。実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各105判定を通過した。左右ポート流量と気管入口圧をそれぞれ576点ビット照合した。固定上流の気道・実時間処理9試験が通過した。348入力と26出力を照合し、採取物6,389,228バイトをRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-left-syrinx-momentum-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-syrinx-momentum-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[左鳴管の残差](notes/songbird-chirps-onset-radiation.md#左鳴管の持ち越し運動量の時間換算を連続描画で揃える)を開き、`jq '.conditions.native_block.first_residual_port_flow | map_values({offset, different_terms, term_swaps})' runs/songbird-chirps-left-syrinx-momentum-44100-20261123-repeat/summary.json` を確認する。今回の差分を対照に加え、256点制御の左ポートの現在の慣性の時間換算だけを揃え、左右流量と気管入口圧、放射への効果を64点で測る。

## 左鳴管の線形慣性の時間換算を64点で比較する（2026-11-23）

- 完了した項目。左ポートの現在の慣性の時間換算だけを乗算に替え、256点制御の左流量の初差を19点後から48点後へ移した。残る差は弁が再開した標本で、47点後の気管入口圧の単独置換で復元した。右の19点後の差、両条件の気管末端と放射の初差の時刻は維持された。気管入口の39点後の差はセル1の38点後の圧力を通った。[事前登録](cases/songbird-chirps-left-syrinx-linear-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左鳴管の線形慣性の時間換算を連続描画で揃える)
- 未達の条件。右ポートの気管支側半セル慣性を揃えた連続描画と、235点制御で26点後に差が出る左気管支末端圧の起点は未検証。256点制御の気管セル1で38点後に分かれるセル2向きの流出も起点が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` で各106判定を通過。左右流量と気管入口圧はそれぞれ576点を各回でビット照合した。固定上流の気道と実時間処理9試験、気管セル1の追加12判定が通過した。368入力と26出力を照合し、採取物6,389,138バイトをRTL9210B-CGへ保存した。[再実行要約](runs/songbird-chirps-left-syrinx-linear-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-syrinx-linear-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右に残った差](notes/songbird-chirps-onset-radiation.md#左鳴管の線形慣性の時間換算を連続描画で揃える)を開き、`jq '.conditions.native_block.first_residual_port_flow.right | {offset, different_terms, candidate, upstream, term_swaps}' runs/songbird-chirps-left-syrinx-linear-44100-20261123-repeat/summary.json` を実行する。今回の差分を対照に加え、右気管支側半セルの幾何項だけを逆数との乗算に変え、256点制御の19点後に残る線形項と持ち越し項の差を区別する。

## 右鳴管の気管支側半セル慣性を64点で比較する（2026-11-23）

- 完了した項目。右鳴管ポートの気管支側半セルだけを上流の計算順に揃え、256点制御で19点後の右流量差を4 ULPから1 ULPへ縮めた。235点制御では右流量が対照と30点後から分かれ、上流との初差は28点後で維持された。両条件の残差は持ち越し換算の単独置換で消えた。放射流量とその差分は対照と64点一致した。[事前登録](cases/songbird-chirps-right-syrinx-half-inertance-44100.json)・[読解と予測値の照合](notes/songbird-chirps-onset-radiation.md#右鳴管ポートの気管支側半セル慣性を連続描画で揃える)
- 未達の条件。右の持ち越し運動量の時間換算は局所置換まで確認した。235点制御の左気管支末端圧と、256点制御の気管セル1から2の流出の起点は未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各106判定を通過し、各回で左右流量と気管入口圧をそれぞれ576点ビット照合した。左線形ケースの既存判定と出力、固定上流の気道・実時間処理9試験も確認した。354入力と26出力を照合し、採取物6,391,408バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-right-syrinx-half-inertance-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-syrinx-half-inertance-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右流量の残差](notes/songbird-chirps-onset-radiation.md#右鳴管ポートの気管支側半セル慣性を連続描画で揃える)を開き、`jq '.conditions | map_values(.first_residual_port_flow.right | if . then {offset, different_terms, term_swaps} else . end)' runs/songbird-chirps-right-syrinx-half-inertance-44100-20261123-repeat/summary.json` を実行する。今回の差分を対照に加え、右ポートの持ち越し運動量の時間換算だけを変え、235点制御の28点後と256点制御の19点後の右流量、気管入口圧、放射を再比較する。

## 右鳴管の持ち越し運動量の時間換算を64点で比較する（2026-11-23）

- 完了した項目。右ポートの持ち越し項だけを上流の換算順に揃えた。右流量の初差が235点制御で28点後から30点後、256点制御で19点後から41点後に移った。右流量の残差は235点制御で直前の右気管支末端圧、256点制御で直前の気管入口圧を置換すると復元した。放射流量と差分は対照と64点一致した。[事前登録](cases/songbird-chirps-right-syrinx-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#右鳴管の持ち越し運動量の時間換算を連続描画で揃える)
- 未達の条件。右気管支末端圧の最初の差は235点制御の25点後、256点制御の19点後に残る。該当点の前回圧と右ポート流量は上流に一致し、気管支末端に入る枝流量は未観測。左気管支末端圧と、256点制御の気管セル1から2への流出の起点も未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各108判定を通過し、各回で左右流量と気管入口圧をそれぞれ576点ビット照合した。右半セルの既存106判定と出力を再現し、固定上流の気道・実時間処理9試験を確認した。356入力と26出力を照合し、採取物6,388,996バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-right-syrinx-momentum-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-syrinx-momentum-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右流量の残差](notes/songbird-chirps-onset-radiation.md#右鳴管の持ち越し運動量の時間換算を連続描画で揃える)と [CLIの鳴禽ケース](crates/vocal-cli/src/songbird_case.rs)を開き、`jq '.conditions | map_values(.experiment_minus_upstream.right_bronchus_pressure_dyn_cm2)' runs/songbird-chirps-right-syrinx-momentum-44100-20261123-repeat/summary.json` を実行する。右気管支末端へ入る直列枝流量と手前セルの圧力を固定上流と候補の通常CLI計測に加え、235点制御の25点後、256点制御の19点後の末端圧の収支を比べる。

## 左右の気管支末端圧を直列枝流量から再計算する（2026-11-23）

- 完了した項目。通常CLIに左右の気管支末端の観測を追加した。右末端圧の初差は235点制御の25点後と256点制御の19点後、左では26点後と23点後で、すべて流入だけの置換で復元した。枝流入の最初の差は右が19点後と18点後、左は両条件で18点後で、線形係数の慣性項を上流順にすると復元できた。[事前登録](cases/songbird-chirps-bronchus-end-balance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左右の気管支末端の圧力を直列枝流量から再計算する)
- 未達の条件。右気管支末端へ入る直列枝で線形慣性項を揃えた連続描画は未検証。256点制御の気管セル1から2への流出の起点も残っている。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各56判定を通過し、両版と両側の流量・圧力をそれぞれ768点ビット照合した。346入力と32出力を照合し、採取物8,082,750バイトをRTL9210B-CGに保存した。先行の右持ち越しケースを現行CLIで再描画して107判定を通過した。Rustワークスペース52試験と固定上流の気道・実時間処理9試験も通過した。[再実行の要約](runs/songbird-chirps-bronchus-end-balance-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-bronchus-end-balance-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[気管支末端圧の内訳](notes/songbird-chirps-onset-radiation.md#左右の気管支末端の圧力を直列枝流量から再計算する)を開き、`jq '.conditions.matched_time.right.first_branch_residual | {first_difference, term_substitutions}' runs/songbird-chirps-bronchus-end-balance-44100-20261123-repeat/summary.json` を実行する。右気管支の最後の直列枝1本の線形係数で、半セルの計算とサンプルレートによる換算を上流順に揃え、右気管支末端圧と右鳴管流量を連続描画で比較する。

## 右気管支の最後の直列枝の線形慣性を64点で比較する（2026-11-23）

- 完了した項目。右の末端枝1本で線形係数の慣性だけを上流順に揃えた。右気管支流入の初差は235点制御で押鍵19点後から26点後、256点制御で18点後から25点後へ移った。右末端圧の初差は25点後から26点後、19点後から29点後へ移った。235点制御の右鳴管流量の初差は30点後から27点後へ早まり、前回の右気管支末端圧を置換して復元した。放射流量と差分は対照と全64点一致した。[事前登録](cases/songbird-chirps-right-bronchus-linear-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#右気管支の最後の直列枝で線形慣性を連続描画で揃える)
- 未達の条件。右の末端枝の持ち越し項を上流順に揃えた連続描画は未検証。235点制御の26点後では半セルと時間換算の両方の置換、256点制御の25点後では時間換算のみの置換でも流入が一致した。256点制御の気管セル1から2への流出の起点も残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各180判定を通過した。別計算で右気管支の流入と圧力を各576点照合し、先行の末端収支の45判定と全再計算系列を再現した。固定上流の気道・実時間処理9試験が通過した。360入力と26出力を照合し、採取物8,313,492バイトをRTL9210B-CGへ保存した。[再実行要約](runs/songbird-chirps-right-bronchus-linear-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-bronchus-linear-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[線形慣性の比較](notes/songbird-chirps-onset-radiation.md#右気管支の最後の直列枝で線形慣性を連続描画で揃える)を開き、`jq '.conditions | map_values(.bronchus_balance.right.experiment.first_branch_residual | {offset: .first_difference.offset, term_substitutions})' runs/songbird-chirps-right-bronchus-linear-44100-20261123-repeat/summary.json` を実行する。今回の差分を対照に加え、同じ直列枝の持ち越し項を上流順の慣性と `(L × Uprev) × fs` で計算し、両制御の流入、末端圧、右鳴管流量を比較する。

## 右気管支の最後の直列枝の持ち越し運動量を64点で比較する（2026-11-23）

- 完了した項目。右の末端枝の持ち越し項を揃え、235点制御の流入初差を押鍵26点後から27点後、256点制御を25点後から29点後へ移した。残った差は直前の手前セル圧だけで復元した。235点制御の右鳴管流量の初差は27点後から32点後に移った。放射流量とその差分は対照と全64点一致した。[事前登録](cases/songbird-chirps-right-bronchus-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#右気管支の最後の直列枝で持ち越し運動量を連続描画で揃える)
- 未達の条件。右気管支の手前セル圧が最初に分かれる235点制御の23点後、256点制御の26点後では、前回圧と末端への流出が一致していた。手前セルへ入る直列枝の流量と、その上流の圧力の観測が残る。256点制御の気管セル1から2への流出の起点も未検証。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各180判定を通過した。別計算で右気管支の流量と圧力を各576点照合した。線形慣性ケースの既存180判定と再計算JSON、固定上流の気道・実時間処理9試験を確認した。366入力と26出力を照合し、採取物8,312,847バイトをRTL9210B-CGへ保存した。[再実行要約](runs/songbird-chirps-right-bronchus-momentum-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-bronchus-momentum-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右末端枝の残差](notes/songbird-chirps-onset-radiation.md#右気管支の最後の直列枝で持ち越し運動量を連続描画で揃える)を開き、`jq '.conditions | map_values(.experiment_minus_upstream.right_bronchus_end_upstream_pressure_dyn_cm2)' runs/songbird-chirps-right-bronchus-momentum-44100-20261123-repeat/summary.json` で手前セル圧の初差を確認する。右気管支の手前セルへの直列枝流入と先頭セル圧を観測し、23点後と26点後の圧力収支を比べる。

## 左右の気管支セル1の圧力収支を比較する（2026-11-23）

- 完了した項目。左右の気管支の内部セルを指定できる通常CLI観測を追加した。右のセル1圧の初差は235点制御の押鍵23点後と256点制御の26点後で、流入のみの置換で復元した。右へ入る枝流量の初差は両条件とも19点後で、前回流量0と両端圧の一致を確認し、線形係数の慣性項だけで差を復元した。左セル1圧は末端側への流出を置換して復元した。[事前登録](cases/songbird-chirps-bronchus-interior-balance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左右の気管支の手前セルの圧力を流入から再計算する)
- 未達の条件。右のセル0から1への直列枝の線形係数だけを揃えた連続描画は未検証。左末端枝と、256点制御の気管セル1から2への流出についても連続描画の確認が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各68判定が通過し、流量と圧力を各768点ビット照合した。観測なしの候補・固定上流CSVも再現した。366入力と32出力を照合し、採取物8,472,852バイトをRTL9210B-CGへ保存した。現行Rust52試験、固定上流の気道・実時間処理9試験、先行の右気管支持ち越しケース179判定が通過した。[再実行要約](runs/songbird-chirps-bronchus-interior-balance-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-bronchus-interior-balance-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右の流入枝の初差](notes/songbird-chirps-onset-radiation.md#左右の気管支の手前セルの圧力を流入から再計算する)を開き、`jq '.conditions | map_values(.right.first_branch_residual | {offset:.first_difference.offset, term_substitutions})' runs/songbird-chirps-bronchus-interior-balance-44100-20261123-repeat/summary.json` を実行する。右のセル0から1への枝に先行の末端枝と同じ線形慣性の対照を追加し、19点後の初差、セル1圧、末端流入、右鳴管流量を連続描画で照合する。

## 右気管支のセル0から1への枝の線形慣性を64点で比較する（2026-11-23）

- 完了した項目。右のセル0から1への枝で線形係数の慣性を上流順に揃え、両条件の押鍵19点後の初差を解消した。次の流量差は235点制御の22点後と256点制御の25点後で、持ち越し項の慣性の組み立てと時間換算を両方揃えると復元した。セル1圧は両条件で初差が遅れ、235点制御の右鳴管流量は32点後から27点後へ早まった。放射流量は対照と64点一致した。[事前登録](cases/songbird-chirps-right-bronchus-interior-linear-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#右気管支のセル0から1への枝で線形慣性を連続描画で揃える)
- 未達の条件。右のセル0から1への枝の持ち越し項をそろえた連続描画は未検証。左気管支末端枝と256点制御の気管セル1から2への流出についても連続描画が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各252判定を通過した。右セル1の枝流量と圧力を別計算で各576点照合し、先行する右末端枝2ケースの各180判定と全再計算系列を再現した。固定上流の気道・実時間処理9試験も通過した。368入力と26出力を照合し、採取物10,144,558バイトをRTL9210B-CGへ保存した。[再実行要約](runs/songbird-chirps-right-bronchus-interior-linear-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-bronchus-interior-linear-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右内部枝の最初の残差](notes/songbird-chirps-onset-radiation.md#右気管支のセル0から1への枝で線形慣性を連続描画で揃える)を開き、`jq '.conditions | map_values(.bronchus_interior_balance.right.experiment.first_branch_residual | {offset:.first_difference.offset, term_substitutions})' runs/songbird-chirps-right-bronchus-interior-linear-44100-20261123-repeat/summary.json` を実行する。今回の差分を対照に加え、同じ枝の持ち越し項だけを上流順の慣性と `(L × Uprev) × fs` で計算し、セル1圧から右鳴管までの影響を調べる。

## 右気管支のセル0から1への枝の持ち越し運動量を64点で比較する（2026-11-23）

- 完了した項目。隔離Rustビルドで右内部枝の持ち越し項を揃えた。235点制御の押鍵22点後と256点制御の25点後の流量は、予測値で固定上流とビット一致した。次の初差は30点後と32点後へ移り、いずれも前回のセル0圧だけの置換で消えた。放射流量とその後退差分は対照と全64点一致した。[事前登録](cases/songbird-chirps-right-bronchus-interior-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#右気管支のセル0から1への枝で持ち越し運動量を連続描画で揃える)
- 未達の条件。セル0圧の初差は235点制御の29点後と256点制御の30点後。その直前のセル0圧と同じ標本のセル1向き流量は一致しており、空気嚢側のポート流量を観測する作業が残る。左気管支末端枝と256点制御の気管セル1から2への流出も調査が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各252判定を通過した。右セル1への流入と圧力を別計算で各576点照合した。先行3ケースの保存CSVから180・180・252判定と再計算結果を再現し、固定上流の気道・実時間処理9試験も通過した。374入力と26出力を照合し、採取物10,139,600バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-right-bronchus-interior-momentum-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-bronchus-interior-momentum-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[鳴禽の気道構成](crates/vocal-core/src/airway/songbird.rs)と[CLIの入口](crates/vocal-cli/src/main.rs)を開き、`jq '.conditions | map_values(.experiment_minus_upstream.right_bronchus_1_upstream_pressure_dyn_cm2)' runs/songbird-chirps-right-bronchus-interior-momentum-44100-20261123-repeat/summary.json` でセル0圧の初差を確認する。空気嚢から右気管支のセル0へ入るポート流量を観測し、29点後と30点後の圧力収支を照合する。

## 空気嚢ポートと左右の気管支セル0の圧力収支を比較する（2026-11-23）

- 完了した項目。通常CLIに左右気管支のセル0の観測を追加した。右セル0圧の初差は235点制御の押鍵29点後と256点制御の30点後で、ポート流入だけの置換で両方とも復元した。右ポートの流量初差は22点後と30点後で、持ち越し項を `(L × Uprev) × fs` にすると上流と一致した。左セル0圧の初差はセル1への流出だけで復元した。[事前登録](cases/songbird-chirps-bronchus-inlet-balance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#空気嚢ポートと左右の気管支セル0の圧力収支)
- 未達の条件。右の空気嚢ポートの持ち越し項を揃えた連続描画は未検証。左末端枝と256点制御の気管セル1から2への流出も調査が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各96判定を通過した。左右・両版のポート流量とセル0圧を各768点ビット照合し、独立十進計算でも両式の残差を確認した。現行Rust52試験、固定上流の気道と実時間処理9試験が通過した。372入力と32出力をハッシュ照合し、採取物9,120,290バイトをRTL9210B-CGに保存した。CSVと要約を含む13出力が再実行でバイト一致した。[再実行要約](runs/songbird-chirps-bronchus-inlet-balance-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-bronchus-inlet-balance-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[ポートの比較](tools/measure_songbird_chirps_bronchus_inlet_balance_44100.py)を開き、`jq '.conditions | map_values(.right.first_port_residual | {offset, different_terms, term_swaps})' runs/songbird-chirps-bronchus-inlet-balance-44100-20261123-repeat/summary.json` を実行する。右の空気嚢ポート1本について持ち越し項だけを上流順に変え、22点後と30点後の流量と、その先のセル0・セル1圧を連続描画で追う。

## 右の空気嚢ポートの持ち越し運動量を64点で比較する（2026-11-23）

- 完了した項目。隔離Rustビルドで右の空気嚢ポートの持ち越し項を揃え、235点制御の22点後と256点制御の30点後で予測どおり固定上流と一致した。次の差は43点後と44点後で、直前のセル0圧で復元した。右気管支で下流から戻る差を調べ、気管入口圧の初差は235点制御では左鳴管流量、256点制御では気管セル1への流出の単独置換で復元した。放射流量と後退差分は対照と全64点一致した。[事前登録](cases/songbird-chirps-right-sac-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#右の空気嚢ポートで持ち越し運動量を連続描画で揃える)
- 未達の条件。256点制御で気管入口からセル1へ入る流量差の起点と、235点制御で左鳴管に先に現れる流量差の連続描画の検証が残る。実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得で、物理MIDI入力は0件だった。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各119判定を通過し、下流の36判定と再計算結果も一致した。ポート流量とセル0圧を各1,152点、右セル1への流入と圧力を各384点照合した。370入力と26出力をハッシュ照合し、採取物8,014,368バイトをRTL9210B-CGに保存した。候補固有の診断列による初回の集計失敗を保存した。[再実行要約](runs/songbird-chirps-right-sac-momentum-44100-20261123-b-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-sac-momentum-44100-20261123-b-repeat/manifest.json)・[失敗時の記録](runs/songbird-chirps-right-sac-momentum-44100-20261123/manifest.json)
- 次に開くファイルと実行するコマンド。[気管の内部観測](tools/measure_songbird_chirps_trachea_interior_momentum_44100.py)を開き、`jq '.conditions.native_block.trachea | {offset, single_substitutions}' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-right-sac-momentum-downstream-20261123.json` を実行する。256点制御で気管セル1から2への流出とその前後の圧力を観測し、気管入口圧へ戻る初差を絞る。

## 256点制御の気管入口圧の差をセル10の壁までたどる（2026-11-23）

- 完了した項目。256点制御の気管入口圧の差を保存済みのセル1・2とその先の収支からさかのぼり、セル10の28点後の圧力差を壁流量だけで復元した。隔離Rustビルドでセル10の壁面積の計算順を揃えると、セル1から2への流量の初差は38点後から49点後、気管入口圧の初差は39点後から47点後へ移った。両制御で放射の観測値は対照と全64点一致した。[事前登録](cases/songbird-chirps-trachea-cell10-wall-surface-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#256点制御の気管入口圧の差をセル10の壁までたどる)
- 未達の条件。256点制御で残る気管入口圧の47点後は右鳴管流量で復元した。右鳴管の初差は46点後で、線形係数の時間換算だけで局所的に消える。連続描画の照合と235点制御の左鳴管の初差の調査が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各1,278判定が通過した。独立十進計算で枝流量8,640点と壁流量・圧力各8,064点を照合し、固定上流の12試験も通過した。384入力と26出力をハッシュ照合し、採取物6,689,286バイトをRTL9210B-CGに保存した。描画前の入力ハッシュの転記違いをケース第2版で修正した。[再実行要約](runs/songbird-chirps-trachea-cell10-wall-surface-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-trachea-cell10-wall-surface-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右鳴管ポートの比較](tools/measure_songbird_chirps_right_syrinx_half_inertance_44100.py)を開き、`jq '.remaining["46"] | {linear_time_conversion_only,term_swaps}' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-trachea-cell10-syrinx-20261123.json` を実行する。右鳴管ポートの線形係数の時間換算だけを揃え、押鍵46点後の流量と47点後の気管入口圧を連続描画で追う。

## 右鳴管の線形慣性の時間換算を64点で比較する（2026-11-23）

- 完了した項目。右鳴管だけで線形慣性の時間換算を上流順に切り替え、235点制御の45点後と256点制御の46点後の流量を予測値に照合した。256点制御では右鳴管流量と右末端圧が上流と全64点一致し、気管入口圧の初差が47点後から60点後へ移った。両条件の放射流量と後退差分は対照と全64点一致した。[事前登録](cases/songbird-chirps-right-syrinx-linear-time-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#右鳴管の線形慣性の時間換算を連続描画で揃える)
- 未達の条件。残る入口圧の初差は235点制御の37点後と256点制御の60点後で、左鳴管流量の単独置換で消えた。左気管支の末端へ入る枝では両条件の18点後に線形係数に由来する初差があり、その係数を揃えた連続描画が残る。実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得で、物理MIDI入力は0件だった。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各78判定、固定上流の12試験、先行の再計算45判定と左側の追加12判定が通過した。両鳴管の流量1,152点と入口圧576点を独立計算に照合し、388入力と26出力をハッシュ照合した。採取物7,230,504バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-right-syrinx-linear-time-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-right-syrinx-linear-time-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[右の末端枝で線形慣性を揃えた差分](tools/measure_songbird_chirps_right_bronchus_linear_44100.py)を開き、`jq '.conditions | map_values(.bronchus_end.first_branch_residual | {first_difference,term_substitutions})' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-right-syrinx-linear-time-left-20261123.json` を実行する。左気管支末端へ入る枝1本で線形係数の慣性の組み立てと時間換算を上流順に揃え、18点後の流量とその先の左末端圧・鳴管流量を追う。

## 左気管支末端への枝の線形慣性を64点で比較する（2026-11-23）

- 完了した項目。左末端へ入る枝1本で分母の線形慣性を揃え、両条件の押鍵18点後の流量差を解消した。次の流量差は235点制御の23点後と256点制御の22点後で、持ち越し運動量の慣性と時間換算を揃えて局所的に復元した。気管入口圧の初差は37点後から38点後、60点後から63点後へ移った。放射の2列は対照と全64点一致した。[事前登録](cases/songbird-chirps-left-bronchus-linear-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左気管支末端の直列枝で線形慣性を連続描画で揃える)
- 未達の条件。左末端枝の持ち越し項を揃えた連続描画は未検証。235点制御の左末端圧の初差は26点後から23点後へ早まり、同じ標本の流入だけの置換で消えた。実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得で、物理MIDI入力は0件だった。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各141判定を通過した。両側の末端流量と圧力を独立十進計算で各1,152点照合し、固定上流の12試験と先行の右鳴管比較を再現した。392入力と26出力をハッシュ照合し、採取物10,596,362バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-left-bronchus-linear-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-bronchus-linear-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[左末端枝の実験差分](tools/measure_songbird_chirps_left_bronchus_linear_44100.py)を開き、`jq 'map_values({offset,variants})' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-linear-momentum-20261123.json` を実行する。同じ枝で持ち越し運動量の慣性と時間換算だけを上流順に揃え、最初の流量差と左末端圧から気管入口圧までの変化を比較する。

## 左気管支末端への枝の持ち越し運動量を64点で比較する（2026-11-23）

- 完了した項目。左末端枝1本の持ち越し項を揃え、235点制御の押鍵23点後と256点制御の22点後の流量を予測どおり固定上流と一致させた。両条件に残った26点後の枝流量差はセル1の前回圧だけで復元した。気管入口圧の初差は235点制御では38点後から41点後に移り、256点制御では63点後から57点後へ早まった。放射の2列は対照と全64点一致した。[事前登録](cases/songbird-chirps-left-bronchus-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左気管支末端の直列枝で持ち越し運動量を連続描画で揃える)
- 未達の条件。左セル1圧の初差はセル0からの流入だけで復元した。その枝は両条件で19点後に分かれ、線形係数だけの置換で流量が上流と一致した。この係数を変えた連続描画が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各144判定を通過した。末端流量と圧力を別の十進計算で各1,152点照合し、先行の141判定と全再計算系列、左セル1の12判定、固定上流の12試験を確認した。394入力と26出力をハッシュ照合し、採取物10,587,710バイトをRTL9210B-CGに保存した。修正後の描画CSVは初回集計が停止した際の6出力とも一致した。[再実行要約](runs/songbird-chirps-left-bronchus-momentum-44100-20261123-b-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-bronchus-momentum-44100-20261123-b-repeat/manifest.json)・[初回の失敗記録](runs/songbird-chirps-left-bronchus-momentum-44100-20261123/manifest.json)
- 次に開くファイルと実行するコマンド。[左側の差分を作る計測器](tools/measure_songbird_chirps_left_bronchus_linear_44100.py)を開き、`jq '.conditions | map_values(.first_branch_residual | {offset:.first_difference.offset,term_substitutions})' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-momentum-inner-20261123.json` を実行する。左気管支セル0から1への枝で分母の線形慣性だけを上流順に揃え、19点後の流量とセル1・末端の圧力を連続描画で照合する。

## 左気管支のセル0から1への枝の線形慣性を64点で比較する（2026-11-23）

- 完了した項目。左セル0から1への枝で分母の線形慣性を揃え、両条件の押鍵19点後の流量差を解消した。次の流量差は両条件の24点後で、持ち越し項だけの置換で復元した。左鳴管の初差は235点制御で42点後から31点後、256点制御で57点後から32点後へ早まった。放射の2列は対照と全64点一致した。[事前登録](cases/songbird-chirps-left-bronchus-interior-linear-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左気管支のセル0から1への枝で線形慣性を連続描画で揃える)
- 未達の条件。左セル0から1への枝の持ち越し項を揃えた連続描画が残る。235点制御の24点後は既存の慣性と上流順の時間換算でも復元し、256点制御では慣性の組み立ても揃える必要があった。実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得で、物理MIDI入力は0件だった。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各177判定を通過した。左セル1と両側の末端の流量・圧力を独立十進計算で各1,728点照合した。先行の141・144判定と全再計算系列、固定上流12試験を再現した。396入力と26出力をハッシュ照合し、採取物12,118,940バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-left-bronchus-interior-linear-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-bronchus-interior-linear-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[左内部枝の比較コード](tools/measure_songbird_chirps_left_bronchus_linear_44100.py)を開き、`jq 'map_values({offset,variants})' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-interior-linear-momentum-20261123.json` を実行する。同じ枝の持ち越し項だけを上流順に揃え、24点後の流量とセル0・セル1圧、その先の左鳴管流量を照合する。

## 左気管支のセル0から1への枝の持ち越し運動量を64点で比較する（2026-11-23）

- 完了した項目。左セル0から1への枝だけで持ち越し項を上流順に揃え、両制御の押鍵24点後の流量が予測値で一致した。次の差は両条件の30点後で、セル0の前回圧だけの置換で消えた。256点制御の右鳴管流量と気管入口圧は固定上流と全64点一致し、放射の2列は両制御で対照と全64点一致した。[事前登録](cases/songbird-chirps-left-bronchus-interior-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左気管支のセル0から1への枝で持ち越し運動量を連続描画で揃える)
- 未達の条件。セル0圧の初差は235点制御で26点後、256点制御で27点後で、左の空気嚢ポート流入だけで復元した。ポート流量の22点後と27点後の初差は持ち越し項の時間換算で消え、その変更を揃えた連続描画が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各180判定を通過した。左セル1と両側の末端の流量・圧力を独立十進計算で各1,728点照合し、左空気嚢側の追加38判定も再現した。398入力と26出力をハッシュ照合し、採取物12,109,884バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-left-bronchus-interior-momentum-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-bronchus-interior-momentum-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[空気嚢ポートの比較コード](tools/measure_songbird_chirps_right_sac_momentum_44100.py)を開き、`jq '.conditions | map_values(.first_port_residual | {offset,term_swaps})' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-bronchus-interior-momentum-inlet-20261123.json` を実行する。左ポート1本の持ち越し項を上流順に揃え、22点後と27点後の流量、セル0・1圧と左鳴管流量を比較する。

## 左の空気嚢ポートの持ち越し運動量を64点で比較する（2026-11-23）

- 完了した項目。左の空気嚢ポートで持ち越し項を上流順に揃え、235点制御の22点後と256点制御の27点後の流量を予測値とビット照合した。256点制御の左右の気管支、両鳴管流量、気管入口圧は全64点で固定上流と一致した。235点制御のポート流量の初差は54点後、セル0圧の初差は53点後へ移った。放射の2列は対照と全64点一致した。[事前登録](cases/songbird-chirps-left-sac-momentum-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#左の空気嚢ポートで持ち越し運動量を連続描画で揃える)
- 未達の条件。235点制御の気管入口圧は41点後に分かれ、その差は気管セル1への流出で復元した。放射流量の後退差分は9点後と11点後に分かれ、サンプルレートの乗算へ揃えた局所計算では初差が60点後と24点後へ移った。連続描画での換算変更が残る。実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得で、物理MIDI入力は0件だった。[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各122判定、先行の右ポート119判定、気管入口と放射の13判定、固定上流12試験を確認した。ポート流量とセル0圧を独立十進計算で各1,152点照合した。398入力と26出力をハッシュ照合し、採取物8,014,914バイトをRTL9210B-CGに保存した。[再実行要約](runs/songbird-chirps-left-sac-momentum-44100-20261123-repeat/summary.json)・[保存記録](runs/songbird-chirps-left-sac-momentum-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[放射流量を時間差分へ換算する箇所](crates/vocal-core/src/airway/network.rs#L791)を開き、`jq '.conditions | map_values({radiation_flow_first_difference,derivative_first_difference,with_upstream_scale})' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-left-sac-momentum-output-20261123.json` を実行する。その換算だけを上流順に揃え、同じ入力の連続描画で差が9点後・11点後から60点後・24点後へ移るか確認する。

## 放射流量の後退差分を64点で比較する（2026-11-23）

- 完了した項目。放射流量の後退差分だけを、サンプルレートを掛ける上流の式に揃えた。上流との初差は235点制御で9点後から60点後、256点制御で11点後から24点後へ移った。両条件の最初の効果と変更点数は事前予測に一致し、差分以外の全列、押鍵前、追従0のCSVを対照と照合した。[事前登録](cases/songbird-chirps-radiation-derivative-scale-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#放射流量の後退差分を連続描画で揃える)
- 未達の条件。残る放射流量の初差はくちばし終端への流入から復元した。くちばしセル0への流量の初差は235点制御で53点後、256点制御で18点後。半セル慣性の組み立てを揃えた局所計算では上流と一致した。その変更の連続描画が残る。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[半セル慣性の置換](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-radiation-derivative-scale-20261123-verification.json)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各35判定と固定上流15試験に合格した。有理数から各実行2,754点をビット照合した。全402入力と24出力をハッシュ照合し、11出力を再現した。採取物計4,599,904バイトはRTL9210B-CGに保存した。[再実行の要約](runs/songbird-chirps-radiation-derivative-scale-44100-20261123-repeat/summary.json)・[再実行の保存記録](runs/songbird-chirps-radiation-derivative-scale-44100-20261123-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[半セル慣性の組み立て](crates/vocal-core/src/airway/network.rs#L86)を開き、`jq '.runs[] | .conditions | map_values(.inlet_replay | if . then {offset,variants} else . end)' /Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-radiation-derivative-scale-20261123-verification.json` を実行する。くちばしセル0へ入る枝だけで `dx × (1/A)` を適用し、53点後と18点後の流量、終端への流入、放射流量と後退差分を比較する。

## くちばし入口の半セル慣性を64点で比較する（2026-11-23）

- 完了した項目。くちばし入口の両端の半セル慣性を上流順に揃えた。235点制御の53点後と256点制御の18点後の流量が事前の予測値で一致し、両条件でくちばし6セルの圧力・流入・断面と放射流量・後退差分が全64点でビット一致した。追従0のCSVと3条件の押鍵前は対照と一致した。[事前登録](cases/songbird-chirps-beak-inlet-half-inertance-44100.json)・[読解と結果](notes/songbird-chirps-onset-radiation.md#くちばし入口の半セル慣性を連続描画で揃える)
- 未達の条件。気管末端の壁流量の2点後の差が残る。235点制御ではOEC圧の38点後と気管入口圧の41点後にも差が残った。現在の実験は追従更新の直後64点を対象としており、呼気を伴う全コールのPCMへの影響を次に確認する。物理MIDI入力は0件で、実機の記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。[残差](runs/songbird-chirps-beak-inlet-half-inertance-44100-20261123-repeat/summary.json)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各50判定、固定上流12試験、72桁十進計算の入口収支各576点を照合した。408入力と24出力をハッシュ照合し、11出力はバイト一致した。採取物計4,605,764バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/songbird-chirps-beak-inlet-half-inertance-44100-20261123-repeat/manifest.json)・[独立照合結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/songbird-beak-inlet-half-inertance-20261123-verification.json)
- 次に開くファイルと実行するコマンド。[全コールの比較コード](tools/measure_songbird_calls.py#L109)と[既存の44.1 kHz入力](runs/songbird-calls-20261120-repeat/artifacts/chirps-44100/case.json)を開き、`jq -r '.outputs[] | select(.path | startswith("artifacts/chirps-44100/")) | [.path,.bytes,.sha256] | @tsv' runs/songbird-calls-20261120-repeat/manifest.json` を実行する。今回の30差分を隔離ビルドに復元し、既存の通常 `render-pcm` 入力で全48,510フレームの内部放射・間引き・PCMを、保存済みの標準版と固定上流に照合する。

## 44.1 kHzの鳴禽chirpsを全区間でPCMまで比較する（2026-11-23）

- 完了した項目。通常の `render-pcm` で30差分適用版を既存の `chirps` 入力に通した。放射の初差が1033点から1089点へ移り、最終PCMは標準版・実験版・上流で全48,510フレームがビット一致した。制御と呼気、128・77フレーム分割、独立FIR・DC除去も照合した。[事前登録](cases/songbird-chirps-full-pcm-44100.json)・[読解と実測](notes/songbird-calls.md#くちばし入口まで揃えた実験版を全コールで比較する)
- 未達の条件。内部放射の最大絶対差は約1.129×10⁻⁸ cm³/s²のままで、呼気前の1089点目に差が残った。第7段階の監査への追加登録が残る。実機MIDIの記録、実録音F2の人手注釈、TSP・CSDの試聴回答は未取得。物理MIDI入力は0件だった。[比較の残差](runs/songbird-chirps-full-pcm-44100-20261123-repeat/summary.json)・[必要な観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各63判定、固定上流の7試験、RIFF・CSVによる独立照合を確認した。77フレーム分割で計測CSVを省いた初回の停止を含め、531入力と24出力をハッシュ照合した。成功2実行では9出力がバイト一致し、採取物計94,348,294バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/songbird-chirps-full-pcm-44100-20261123-repeat/manifest.json)・[初回の停止記録](runs/songbird-chirps-full-pcm-44100-20261123/manifest.json)
- 次に開くファイルと実行するコマンド。[第7段階の監査ケース](cases/plan-evidence-stage7.json)と[監査コード](tools/audit_stage7_evidence.py#L474)を開き、`jq '.evidence[] | select(.topic == "songbird")' cases/plan-evidence-stage7.json` を実行する。既存の鳴禽証拠を維持し、入口で揃えた64点の比較と今回の全区間のPCM照合を追加する。停止記録と一次観測の未取得状態も保持する。

## 第7段階の鳴禽証拠を第10版で照合する（2026-11-23）

- 完了した項目。第9版の69実行と128判定を維持し、鳴禽の3条件の短区間と `chirps` の全区間を元のCSV・WAVから照合した。短区間では3,840値と入口の効果の初点が一致し、全区間では内部放射の初差1033点・1089点と全48,510点のPCM一致を再現した。停止時点までに保存された4出力と、77フレーム分割での停止理由を照合した。[第10版の事前登録](cases/plan-evidence-stage7.json)・[読解と実測](notes/plan-evidence-stage7.md#第10版で鳴禽の短区間と全区間を照合する)
- 未達の条件。全コールの内部放射には微小差が残る。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDI入出力は各0件だった。[必要な一次観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。16項目・71実行・2,284出力を照合し、研究ワークスペースと `/tmp` の各156判定が通過した。要約・入力一覧は一致し、778入力と12出力をハッシュ照合した。圧力・PCM・停止ハッシュの変更を個別に検出した。現行Rust 52試験、固定上流の比較19試験とMIDI 2試験、通常Webビルドが通過し、採取ログ計24,520バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/stage7-evidence-update-20261123-songbird-repeat/manifest.json)・[独立照合結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/stage7-songbird-audit-20261123-verification.json)
- 次に開くファイルと実行するコマンド。[一次観測と資料の一覧](notes/plan-evidence-stage7.md#未確認の観測)を開き、`../../.venv/bin/python tools/audit_stage7_evidence.py --help` で取込済み実行を指定する引数を確認する。回答を受領した項目は対応する資料IDを照合して登録し、物理入力が接続されたときは `/usr/bin/swift tools/capture_coremidi_source.swift --list-inputs` で取得元を確かめてから、保存された受動計測ケースで押鍵・離鍵を採る。

## 試聴・F2注釈のZIPを展開先で検証する（2026-11-23）

- 完了した項目。TSP試聴18対、CSD試聴6区間、F2注釈7窓を通常ファイルのZIPにまとめた。別フォルダで音声61件・図7枚、資料ID付きCSVの出力を検証した。書き出した3件の試験CSVを元の資料IDで通常取込へ通した。[事前登録](cases/stage7-review-archives.json)・[ZIPと取込手順](notes/plan-evidence-stage7.md#試聴とf2注釈の資料を別の環境で開く)
- 未達の条件。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。再照会時もCoreMIDIの入力は0件だった。[必要な一次観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各27判定、3種の通常取込、別の `unzip` による77ファイルのハッシュ照合を確認した。3つのZIPはバイト一致した。273入力と33出力を照合し、出力計31,271,568バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/stage7-review-archives-20261123-repeat/manifest.json)・[独立照合結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/stage7-review-archives-20261123-verification.json)
- 次に開くファイルと実行するコマンド。[評価者用ZIPと元の実行ID](notes/plan-evidence-stage7.md#試聴とf2注釈の資料を別の環境で開く)を開く。回答を受領したら該当資料の `collect --help` または `--help` を確認し、人手区分で得た集計実行を `tools/audit_stage7_evidence.py` に渡す。物理入力が得られたら `/usr/bin/swift tools/capture_coremidi_source.swift --list-inputs` で収録元を特定する。

## 段階別監査の第4版で最新の成果と一次記録を照合する（2026-11-23）

- 完了した項目。第3版の169判定を保持し、第7段階第10版の71実行と評価者用ZIPを全体監査へ接続した。指定した試聴・注釈・MIDIの一次記録から取得状況を再計算できる。初回監査で現行WASMと旧採取の差を検出したため、Chromium・Firefoxで再採取し、各98,790点のPCMの一致と停止・再開を確認した。[第4版の事前登録](cases/plan-completion-evidence.json)・[比較と再採取](notes/plan-evidence-audit.md#第4版で人手実機の取得状況まで照合する)
- 未達の条件。実録音のF2注釈、TSP・CSDの人手試聴、物理MIDIの一次記録は未登録で、CoreMIDI入出力は各0件だった。試験回答と仮想MIDIを取得として扱う指定は照合で不合格になった。[第7段階の未取得項目](notes/plan-evidence-stage7.md#未確認の観測)・[取得状態の独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/plan-completion-v4-20261123-verification.json)
- 最後に確認した実行。全体監査の2回で各182判定、88実行と1,878出力を照合した。第7段階の156判定の回帰は変更前と一致した。WASM再採取、初回の不合格を含む2,021入力・38出力を照合し、採取物21,807,253バイトをRTL9210B-CGに保存した。[全体監査の再実行](runs/plan-completion-evidence-20261123-v4-repeat/manifest.json)・[第7段階の回帰](runs/stage7-evidence-aggregate-regression-20261123/summary.json)
- 次に開くファイルと実行するコマンド。[評価者用ZIPと元の実行ID](notes/plan-evidence-stage7.md#試聴とf2注釈の資料を別の環境で開く)から得た回答を取り込む。物理MIDIの入力は `/usr/bin/swift tools/capture_coremidi_source.swift --list-inputs` で確認する。一次記録の指定を付けて第7段階の監査を実行できたら、`../../.venv/bin/python tools/audit_plan_completion.py plan-completion-with-observations --stage7-run <第7段階の監査実行ID>` で全体へ反映する。

## 48 kHz固定発声のWASMメモリを一次記録で確認する

- 完了した項目。旧48 kHz実行のWorklet JSONにあったメモリ増加0回を全体監査へ反映し、手動停止の要約にも回数と初回フレームを出力した。保存5レートと現行Chromiumの48 kHzを照合した。現行の2回で各93,056フレームがCLIとビット一致し、727量子で増加0回、発声・減衰のp99は各1 msだった。[事前登録](cases/worklet-realtime-voice.json)・[読解と再採取](notes/worklet-realtime-voice-48000-memory.md)
- 未達の条件。固定上流との差は出力4,102フレーム目の声門上圧に現れ、PCMの最大絶対差は4.66×10⁻¹⁰だった。内部サンプルごとの圧力差の起点は未観測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録で、CoreMIDI入出力は各0件だった。[波形差の起点](notes/worklet-realtime-voice-48000-memory.md#再採取と差の起点)・[必要な一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。ワークスペースと `/tmp` から第5版監査の各192判定に合格し、90実行と1,905出力を照合した。要約はバイト一致した。採取と監査の4実行の計1,468入力と54出力を独立にハッシュ照合した。Workletの観測欄欠落・量子欠落などの6対照が落ちることを確認し、採取物のうち119,256,812バイトをRTL9210B-CGに置いた。[監査の保存記録](runs/plan-completion-fixed-voice-memory-v5-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-chimera-fixed-voice-memory.json)
- 次に開くファイルと実行するコマンド。[研究版の声門と気道の更新](crates/vocal-core/src/voice.rs#L238)と[上流プローブの採取点](tools/upstream_vowel_voice_probe.rs#L163)を開き、`jq '.observations["worklet-rate-48000-memory-current"].first_state_differences' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-chimera-fixed-voice-memory.json` を実行する。一次記録が得られた項目は[取込手順](notes/plan-evidence-stage7.md#未確認の観測)に従い、第7段階を照合してから全体監査の `--stage7-run` に渡す。

## 48 kHz固定発声の咽頭入口圧を内部サンプルで照合する

- 完了した項目。通常CLIに咽頭入口の収支を採る項目を追加した。固定 `/i/` の最初の圧力差は内部8,205点目で、声門流入は一致していた。咽頭セル長を上流値で計算したコンプライアンスに置換すると上流の圧力を復元した。先頭4,120出力フレームは保存済みのPCMと各版で一致し、固定上流ともビット一致した。[事前登録](cases/fixed-voice-pharynx-onset-48000.json)・[読解と実行](notes/fixed-voice-pharynx-onset-48000.md)
- 未達の条件。全咽頭長の1 ULPの差が生じる中心線上の区間は未特定。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録で、CoreMIDI入出力は各0件だった。[幾何への追跡](notes/fixed-voice-pharynx-onset-48000.md#最初の差はセル長から圧力へ伝わる)・[取得が必要な記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各13判定で要約が一致した。圧力を各実行104点、独立の有理数計算と十進計算で照合した。全体監査は192判定が通過し、通常ビルドのWASMは先行の採取と一致した。3実行の計726入力と38出力をハッシュ照合し、出力のうち6,199,861バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-pharynx-onset-48000-repeat/manifest.json)・[全体監査](runs/plan-completion-pharynx-onset-regression/summary.json)
- 次に開くファイルと実行するコマンド。[研究版の中心線距離](crates/vocal-core/src/anatomy/area.rs#L74)と[上流の咽頭境界位置](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1235)を開き、`jq '.verified["fixed-voice-pharynx-onset-48000-repeat"]' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharynx-onset-48000.json` を実行する。同じ固定姿勢で境界前後の中心線位置と加算する長さを比較する。一次記録が得られた項目は[第7段階の取込手順](notes/plan-evidence-stage7.md#未確認の観測)で照合する。

## 固定母音 /i/ の中心線で咽頭全長の初差を追う

- 完了した項目。全49測定線の積算距離を通常CLIと固定上流の座標から再計算した。中点Xの初差は測定線0、区間長の初差は3→4、積算の初差は6→7だった。線6の内側Xと線7の外側Xを生む喉頭蓋基部・後壁の丸めを独立に復元し、両方を替えると最初の積算値と咽頭全長が上流に一致した。[事前登録](cases/fixed-voice-centerline-i.json)・[読解と結果](notes/fixed-voice-centerline-i.md)
- 未達の条件。通常の幾何生成で同じ2か所の演算順を揃えた場合の、声門上圧とPCMへの影響は未観測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録も未登録で、CoreMIDI入出力は各0件だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。第1版の8判定と第2版の各12判定が通過した。研究ワークスペースと `/tmp` の第2版要約はバイト一致した。上流の幾何6試験が通過し、既知の下唇試験1件は無視指定だった。3実行の394入力と45出力を独立照合し、採取物2,316,959バイトをRTL9210B-CGへ置いた。[再実行の保存記録](runs/fixed-voice-centerline-i-v2-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-centerline-i.json)
- 次に開くファイルと実行するコマンド。[研究版の体型座標変換](crates/vocal-core/src/anatomy/body.rs#L64)と[後壁の補間](crates/vocal-core/src/anatomy.rs#L577)を開き、`jq '.rear_ray_replay | {epiglottis_base_y_cm, accumulated_at_event_cm}' runs/fixed-voice-centerline-i-v2-repeat/summary.json` を実行する。2か所を一つずつ上流順にした実験版で、咽頭長と発声直後の上圧を比較する。

## 中心線の二つの演算順を通常の固定発声で比較する

- 完了した項目。基部Y、咽頭後壁、両変更の3実験を標準と比較した。両変更で測定線7の積算・咽頭長・セル長・内部8,205点目の声門上圧が上流に一致した。全93,056フレームで各版の128・77分割が一致した。両変更のPCM最大絶対差は標準の256分の1、ビット差のあるフレームは16から18へ増えた。[事前登録](cases/fixed-voice-centerline-render-48000.json)・[各条件と比較結果](notes/fixed-voice-centerline-render-48000.md)
- 未達の条件。両変更版の声門上圧の初差は8,210点目で、声門流入だけの置換で復元できた。その流量差が生じた枝の演算は未特定。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録で、CoreMIDI入出力は各0件だった。[残る圧力差](notes/fixed-voice-centerline-render-48000.md#幾何から声門上圧とpcmまでの結果)・[人手と実機の記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各35判定、両変更版の解剖モデル9試験、独立計算の各208圧力値を確認した。24出力をバイト照合した。不足入力による初回2実行を含め580入力と90出力をハッシュ照合し、出力のうち22,389,948バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-centerline-render-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-centerline-render-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の枝の更新](crates/vocal-core/src/airway/network.rs#L189)と[上流の声門ポートの更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '.variants.combined.first_pressure_difference_terms' runs/fixed-voice-centerline-render-48000-repeat/summary.json` を実行する。内部8,210点目の声門流入について、圧差と持ち越し運動量、線形・非線形損失を別々に採取する。

## 固定発声の声門枝で慣性の時間換算を照合する

- 完了した項目。声門枝の圧差・流量・慣性と損失を両版で採り、8,210点目の初差を線形項の時間換算まで追った。声門枝の `L/dt` を `L×Fs` に揃えた実験版は、先行する流量を保ち、8,210点目の流量と声門上圧が上流に一致した。PCMは93,056フレームの両分割で一致し、上流との最初の差が59,761フレーム目に移った。[事前登録](cases/fixed-voice-glottal-branch-48000.json)・[読解と結果](notes/fixed-voice-glottal-branch-48000.md)
- 未達の条件。流量と声門上圧の次の初差は8,215点目。持ち越し運動量をサンプルレートで換算する局所計算で流量を復元した。その項だけを変えた連続描画は未観測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録で、CoreMIDI入出力は各0件だった。[次の差の検算](notes/fixed-voice-glottal-branch-48000.md#連続描画での効果)・[人手と実機の記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各16判定に合格し、第1版の9判定を保持した。固定上流の12試験と各156枝流量の独立検算を確認した。第2版の要約と観測・WAVをバイト照合し、437入力・54出力をハッシュ照合した。採取した出力のうち10,523,181バイトはRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-glottal-branch-48000-v2-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-branch-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の持ち越し項](crates/vocal-core/src/airway/network.rs#L192)と[上流の運動量保存](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '."fixed-voice-glottal-branch-48000-v2-repeat".equation.remaining_difference' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-branch-48000.json` を実行する。慣性換算を揃えた実験版で、声門枝の持ち越し項だけを上流順にして8,215点目と全PCMを比較する。

## 固定発声の声門枝で持ち越し運動量を比較する

- 完了した項目。先行版の保存ソースと差分から枝・圧力のCSVを再現した。持ち越し項だけを上流順にした通常描画では8,214点目までの流量が先行版と一致し、8,215点目の流量と声門上圧が上流に一致した。93,056フレームの両分割のPCMは一致し、上流との差は16から13フレームへ減った。初差は4,802フレーム目に移った。[事前登録](cases/fixed-voice-glottal-momentum-48000.json)・[読解と結果](notes/fixed-voice-glottal-momentum-48000.md)
- 未達の条件。流量と声門上圧の次の初差は8,217点目。気管末端圧とスリット抵抗の置換で流量が一致した。抵抗差は掛け算の順で復元した。気管末端の圧力差の起点は未観測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録で、CoreMIDI入出力は各0件だった。[次の差の内訳](notes/fixed-voice-glottal-momentum-48000.md#連続描画と次の差)・[人手と実機の記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各11判定と、各実行の固定上流12試験を確認した。各52内部点の独立検算、CSV・WAV・差分のバイト照合が通った。296入力と28出力をハッシュ照合し、採取物6,006,342バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-glottal-momentum-48000-repeat/manifest.json)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-momentum-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の声門上下圧](crates/vocal-core/src/voice.rs#L214)と[上流の壁・節点更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1054)を開き、`jq '.remaining_flow_difference | {sample,left_pressure:.differing_values.left_pressure,resistance:.differing_values.resistance}' runs/fixed-voice-glottal-momentum-48000-repeat/summary.json` を実行する。気管末端圧を作る8,216点目の前回圧・流量・壁流出・コンプライアンスを採取する。

## 固定発声の気管末端圧を直列枝まで追う

- 完了した項目。8,216点目の更新前圧力、声門・壁流出、コンプライアンスは一致した。気管枝からの流入を上流値に置き換えると、更新後圧力の2 ULP差が消えた。流入の初差は8,215点目、一つ手前のセルから読む圧力の初差は8,214点目だった。[事前登録](cases/fixed-voice-subglottal-balance-48000.json)・[読解と結果](notes/fixed-voice-subglottal-balance-48000.md)
- 未達の条件。一つ手前のセルの圧力差を作った更新項と、直列枝内部への寄与は未分離。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。入力一覧の再確認では物理MIDI入力が見つからなかった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` から各11判定、各12上流試験、各104点の独立検算が通過した。300入力と36出力をハッシュ照合し、採取物4,665,713バイトをRTL9210B-CGに保存した。CSV・PCM・計測差分は一致し、要約では上流プローブの実行ファイルのハッシュだけが異なった。[再実行の保存記録](runs/fixed-voice-subglottal-balance-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-subglottal-balance-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の直列枝更新](crates/vocal-core/src/airway/network.rs#L189)と[上流の直列枝の係数](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L955)を開き、`jq '{first_difference_by_field, minimum: .first_pressure_difference.minimum_upstream_substitutions}' runs/fixed-voice-subglottal-balance-48000-repeat/summary.json` を実行する。気管の一つ手前のセルの8,213点目の収支と、末端に入る枝の8,214〜8,215点目の入力・係数を比較する。

## 気管の最後から2番目の節点と前後の直列枝を比較する

- 完了した項目。8,213点目の流入を置き換えて、一つ手前の節点の最初の圧力差を復元した。前後の枝で流量が初めて分かれた8,213・8,215点目は、ともに肺側の圧力の置換だけで流量が上流と一致した。慣性と抵抗を足した線形係数は全52点で一致した。[事前登録](cases/fixed-voice-tracheal-penultimate-48000.json)・[読解と結果](notes/fixed-voice-tracheal-penultimate-48000.md)
- 未達の条件。8,213点目に流入枝が読む肺側の圧力差を作った更新は未特定。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各8判定と固定上流の12試験、各312点の独立検算に通過した。採取CSV、上流PCM、計測差分など13出力がバイト一致した。354入力と44出力をハッシュ照合し、採取物4,903,689バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-tracheal-penultimate-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-penultimate-48000.json)
- 次に開くファイルと実行するコマンド。[上流の肺境界更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)と[研究版の呼気から気道への入力](crates/vocal-core/src/voice.rs#L214)を開き、`jq '.first_branch_flow_differences["tracheal-in"] | {sample:.candidate.internal_sample, candidate:.candidate.left_pressure, upstream:.upstream.left_pressure,minimum_upstream_substitutions}' runs/fixed-voice-tracheal-penultimate-48000-repeat/summary.json` を実行する。同じ固定発声のゲート初期について、肺ポートから気管末端までの圧力と流量を一度に採る。

## 気管全域で最初の流量差を運動量の換算まで追う

- 完了した項目。肺ポートから気管末端までの13セル・13枝を同時に採取した。流量の初差は肺側から最初の直列枝の8,196点目で、持ち越し運動量の換算順を置き換えると流量と直後のセル圧が上流値に一致した。肺境界圧の初差は8,220点目だった。[事前登録](cases/fixed-voice-tracheal-onset-48000.json)・[読解と結果](notes/fixed-voice-tracheal-onset-48000.md)
- 未達の条件。枝1だけを換算し直した連続描画で残る圧力差とPCMへの影響は未計測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回の節点欠測を保存し、計測コード修正後の各8判定と各9上流試験に通過した。成功した各実行で節点1,352点と枝1,352点を独立に再計算し、360入力と40出力をハッシュ照合した。採取物7,339,349バイトをRTL9210B-CGに保存した。[初回の失敗記録](runs/fixed-voice-tracheal-onset-48000-a/manifest.json)・[再実行の保存記録](runs/fixed-voice-tracheal-onset-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-onset-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の持ち越し圧](crates/vocal-core/src/airway/network.rs#L189)と[上流の運動量保存](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '.earliest_flow_events[] | {cell,sample,minimum_upstream_substitutions,flow_with_upstream_history}' runs/fixed-voice-tracheal-onset-48000-repeat/summary.json` を実行する。最初の直列枝だけを隔離ビルドで `(L×U_prev)×Fs` にし、通過する内部圧・流量と全PCMを比較する。

## 気管の最初の直列枝の運動量換算を連続描画で比較する

- 完了した項目。枝1だけの持ち越し運動量を上流順に換算し、8,196点目の流量とセル圧が上流に一致した。上流とPCMが異なるフレームは13から10へ減り、最初の差は4,802から62,275フレーム目に移った。両版とも128・77分割で全93,056フレームがビット一致した。[事前登録](cases/fixed-voice-tracheal-momentum-48000.json)・[読解と結果](notes/fixed-voice-tracheal-momentum-48000.md)
- 未達の条件。気管全域の次の初差は8,198点目の枝2の同じ運動量換算。末端の圧力初差は対照の8,216点目から8,211点目に移った。一様気管の全直列枝で換算を揃えた連続描画は未計測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDI入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各9判定と固定上流の各9試験、各2,704点の圧力・枝流量の独立検算に通過した。CSV、WAV、差分など15出力をバイト照合し、356入力と44出力をハッシュ照合した。採取物13,299,100バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-tracheal-momentum-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-momentum-48000.json)
- 次に開くファイルと実行するコマンド。[今回の選択と換算順の差分](runs/fixed-voice-tracheal-momentum-48000-repeat/artifacts/candidate-tracheal-history.patch)を開き、`jq '.earliest_flow_events[] | {cell,sample,minimum_upstream_substitutions,flow_with_upstream_history}' runs/fixed-voice-tracheal-momentum-48000-repeat/summary.json` を実行する。一様気管の直列枝12本に適用する対照を事前登録し、同じ内部区間と停止を含むPCMを比較する。

## 気管の直列枝12本の換算を揃え、肺・声門ポートの残差を測る

- 完了した項目。8,198点目の枝2の流量とセル1の圧力が上流に一致し、末端圧は観測した52点すべてで一致した。気管側で残る最初の差は8,202点目の肺ポートの持ち越し圧、声門流量の最初の差は8,217点目の抵抗だった。PCMのビット差は枝1のみの10フレームから16フレームへ増え、全件がゲート停止後だった。[事前登録](cases/fixed-voice-tracheal-series-momentum-48000.json)・[読解と結果](notes/fixed-voice-tracheal-series-momentum-48000.md)
- 未達の条件。肺ポートの運動量と声門スリット抵抗の連続描画での効果は未分離。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各10判定と上流各15試験、および各2,808点の独立検算に通過した。20出力をバイト照合し、366入力と52出力をハッシュ照合した。採取物13,455,314バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-tracheal-series-momentum-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-series-momentum-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の肺ポート構築](crates/vocal-core/src/airway/human.rs#L225)と[上流の運動量更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '.earliest_flow_events[] | {cell,sample,minimum_upstream_substitutions,flow_with_upstream_history}' runs/fixed-voice-tracheal-series-momentum-48000-repeat/summary.json` を実行する。今回の直列枝12本を対照に、肺ポートの持ち越し項だけを上流順にする。声門スリット抵抗は別の比較に残す。

## 肺ポートにも運動量換算を適用し、気管全域を照合する

- 完了した項目。8,202点目の肺ポート流量と8,207点目の気管入口圧が上流値に一致した。肺境界圧、気管13セルの圧力、肺ポートを含む13枝の流量が観測の全52点で一致した。上流PCMとのビット差は停止後の16から15フレームへ減った。[事前登録](cases/fixed-voice-lung-port-momentum-48000.json)・[読解と結果](notes/fixed-voice-lung-port-momentum-48000.md)
- 未達の条件。8,217点目に残る声門流量の差はスリット抵抗の換算順で復元済み。声門抵抗だけを変更した連続描画と停止後のPCMは未計測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各10判定と上流各15試験、各2,808点の独立検算に通過した。20出力をバイト照合し、376入力と52出力をハッシュ照合した。採取物13,456,806バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-lung-port-momentum-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-lung-port-momentum-48000.json)
- 次に開くファイルと実行するコマンド。[研究版のポートの抵抗](crates/vocal-core/src/airway/network.rs#L95)と[上流のスリット抵抗](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1009)を開き、`jq '.glottal_flow_difference.port | {sample,minimum_upstream_substitutions,candidate_resistance:.candidate.resistance,upstream_resistance:.upstream.resistance}' runs/fixed-voice-lung-port-momentum-48000-repeat/summary.json` を実行する。今回の版を対照にし、声門ポートのスリット抵抗の演算順だけを上流に揃える。

## 声門スリット抵抗を揃え、PCM差より前の放射を測る

- 完了した項目。8,217点目の声門抵抗・線形係数・流量が上流に一致し、観測の52点すべてで声門流量と肺・気管の観測値が一致した。上流とのPCMビット差は15から17フレームへ増えた。延長観測で、フレーム末尾の量のうち放射流量微分が両版とも内部8,207点目に最初に分かれることを確認した。[事前登録](cases/fixed-voice-glottal-slit-48000.json)・[読解と結果](notes/fixed-voice-glottal-slit-48000.md)
- 未達の条件。8,207点目の放射流量微分で、流量和と時間換算のどちらが差を作るかは未分離。4,802出力フレーム目のPCM差への寄与は未特定。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDI入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。主比較は各11判定、上流各15試験、各2,808点の独立検算に通過した。延長観測は初回のハッシュ誤記を訂正し、各8判定に合格した。両比較の再実行で計31出力をバイト照合し、計762入力と76出力をハッシュ照合した。採取物22,518,680バイトをRTL9210B-CGに保存した。[主比較の再実行](runs/fixed-voice-glottal-slit-48000-repeat/manifest.json)・[延長観測の再実行](runs/fixed-voice-glottal-slit-prefix-48000-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の放射出力](crates/vocal-core/src/airway/network.rs#L791)と[固定上流の放射出力](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)を開き、`jq '.results.reordered.first_acoustic_differences.radiation_derivative_cm3_s2' runs/fixed-voice-glottal-slit-prefix-48000-repeat/summary.json` を実行する。8,206〜8,207点目の両版で壁・口端・鼻端の流量和と差分、時間換算を採る。

## 放射流量微分の初差を咽頭入口の壁面積まで追う

- 完了した項目。偶数点を含む採取で初差は内部8,206点目と判明した。咽頭入口の壁面積の計算順から壁流量和の差を再現した。8,206点目の微分は壁流量和と時間換算の置換、8,207点目は壁流量和だけの置換で上流に一致した。PCMが分かれた出力4,802フレーム目では、口端流量と前回流量和の置換で放射微分が一致した。[事前登録](cases/fixed-voice-radiation-balance-48000.json)・[読解と結果](notes/fixed-voice-radiation-balance-48000.md)
- 未達の条件。壁面積と放射微分の計算順を変えた連続描画、およびPCM差への各項の効果は未計測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回は保存差分を適用する関数の呼び出しを修正し、成功した各実行で6判定と固定上流の9試験、壁4,608点と微分128点の独立検算に通過した。10出力がバイト一致し、386入力と36出力をハッシュ照合した。採取物10,963,041バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-radiation-balance-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-radiation-balance-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の壁面積](crates/vocal-core/src/airway/network.rs#L34)と[上流の周長係数](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L560)を開き、`jq '.events | with_entries(.value |= .minimum_upstream_substitutions)' runs/fixed-voice-radiation-balance-48000-repeat/summary.json` を実行する。最初に放射を生む咽頭入口の壁面積だけを上流順にした隔離描画を作り、観測された初差がどう移動するかを測る。

## 咽頭入口の壁面積の演算順を連続描画で比較する

- 完了した項目。咽頭入口1セルの壁面積を上流順にし、8,206・8,207点目の壁流量和と4,802出力フレーム目のPCMを上流と一致させた。上流とのPCMの差は17から15フレームへ減り、最初の差は停止後の55,880フレーム目へ移った。[事前登録](cases/fixed-voice-pharyngeal-wall-surface-48000.json)・[読解と結果](notes/fixed-voice-pharyngeal-wall-surface-48000.md)
- 未達の条件。放射流量微分は8,206・8,213点目で時間換算の差が残る。`ΔU×Fs` の局所計算では次の差が8,220点目へ移る。時間換算を揃えた連続描画とPCMは未計測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各10判定と固定上流の各9試験、各実行の壁4,608点・微分128点の独立検算に通過した。再実行間で14出力がバイト一致し、396入力と40出力をハッシュ照合した。採取物19,869,384バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-pharyngeal-wall-surface-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-wall-surface-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の放射微分](crates/vocal-core/src/airway/network.rs#L791)と[上流の時間換算](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)を開き、`jq '.events | with_entries(.value |= .remaining_difference.minimum_upstream_substitutions)' runs/fixed-voice-pharyngeal-wall-surface-48000-repeat/summary.json` を実行する。今回の壁面積を対照に、最終の放射流量微分だけを `ΔU×Fs` にした連続描画を比較する。

## 放射微分をサンプルレートで換算し残る咽頭の差を追う

- 完了した項目。放射微分だけを `ΔU×Fs` にすると8,206・8,213点目が上流と一致し、残る初差は8,220点目だった。8,220点目の放射は節点13の壁入力圧、8,219点目の入口圧は咽頭内へ向かう流出の置換で再現した。対照と変更版の全93,056 PCMフレームはビット一致した。[事前登録](cases/fixed-voice-radiation-derivative-48000.json)・[読解と結果](notes/fixed-voice-radiation-derivative-48000.md)
- 未達の条件。8,219点目の咽頭流出を決める直列枝の項は未採取。上流とのPCM差は停止後の15フレームに残る。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各11判定と上流の各9試験、および各実行の壁4,608点・微分128点の独立計算が通過した。14出力をバイト照合し、402入力と40出力をハッシュ照合した。採取物19,868,364バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-radiation-derivative-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-radiation-derivative-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の直列枝更新](crates/vocal-core/src/airway/network.rs#L189)と[上流の直列枝の係数](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L955)を開き、`jq '.events["8220"] | {control:.control.derivative, multiply_rate:.multiply_rate.derivative, upstream:.upstream.derivative, residual:.remaining_difference.minimum_upstream_substitutions}' runs/fixed-voice-radiation-derivative-48000-repeat/summary.json` を実行する。8,218〜8,219点目の咽頭の最初の直列枝を採り、圧差・持ち越し運動量・損失を照合する。

## 咽頭入口の直列枝の持ち越し圧を連続描画で検証する

- 完了した項目。8,218・8,219点目の枝流量差を持ち越し圧の置換で再現した。節点13→14の枝だけを上流順に換算した隔離ビルドで、両点の流量、8,219点目の入口圧と8,220点目の放射微分が上流とビット一致した。全93,056フレームでPCMのビット差は停止後の15から12フレームへ減った。[枝の事前登録](cases/fixed-voice-pharyngeal-entry-branch-48000.json)・[連続描画の事前登録](cases/fixed-voice-pharyngeal-entry-momentum-48000.json)・[読解と結果](notes/fixed-voice-pharyngeal-entry-branch-48000.md)
- 未達の条件。残る最初の枝流量差は8,229点目で、節点14の圧力の置換で上流の流量を再現した。節点14で最初に分かれる8,214点目の圧力収支は未採取。放射微分は8,231点目に差が残る。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2ケースを各2回実行し、いずれも8判定に合格した。固定上流の試験は枝の採取で各9件、連続描画で各12件通過した。別の十進計算と生PCMで照合し、採取・描画計23出力のバイト一致と832入力・84出力のハッシュを確認した。採取物29,218,515バイトをRTL9210B-CGに保存した。[枝の再実行](runs/fixed-voice-pharyngeal-entry-branch-48000-repeat/manifest.json)・[連続描画の再実行](runs/fixed-voice-pharyngeal-entry-momentum-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-entry-momentum-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の節点更新](crates/vocal-core/src/airway/network.rs#L675)と[上流の圧力更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)を開き、`jq '{first_branch_flow_difference,first_radiation_difference,residual:.next_branch_event.minimum_upstream_substitutions}' runs/fixed-voice-pharyngeal-entry-momentum-48000-repeat/summary.json` を実行する。節点14の8,213・8,214点目の体積収支と更新前後の圧力を採り、残差の最初の項を分ける。

## 咽頭の次セルの圧力差を枝の慣性換算まで追う

- 完了した項目。8,214点目の節点14の圧力差を、枝14→15の流出だけの置換で復元した。流出の初差は8,207点目で、左右の圧力と慣性が一致した状態で、現在慣性の時間換算 `L/dt` と `L×Fs` が分かれた。8,213点目は流出差が正味流量に残らず、8,214点目に圧力、8,215点目に壁流量へ伝わった。[事前登録](cases/fixed-voice-pharyngeal-second-cell-48000.json)・[読解と結果](notes/fixed-voice-pharyngeal-second-cell-48000.md)
- 未達の条件。枝14→15の慣性換算だけを揃えた連続描画と停止後のPCMは未計測。現行比較の入口側の枝流量差は8,229点目に残る。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。ソース参照と判定側の型の誤りを修正し、各8判定と固定上流の各9試験に通過した。各実行で両版の壁と節点各104点、枝208点を十進計算で照合した。成功した2実行の380入力・44出力をハッシュ照合し、14出力のバイト一致を確認した。採取物9,287,311バイトをRTL9210B-CGに保存した。[修正前の判定](runs/fixed-voice-pharyngeal-second-cell-48000-b/summary.json)・[再実行の保存記録](runs/fixed-voice-pharyngeal-second-cell-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の枝更新](crates/vocal-core/src/airway/network.rs#L189)と[上流の直列枝更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '.first_outgoing_event | {sample:.candidate.internal_sample,candidate:.candidate.inertance_per_step,upstream:.upstream.inertance_per_step,minimum_upstream_substitutions}' runs/fixed-voice-pharyngeal-second-cell-48000-repeat/summary.json` を実行する。枝14→15の現在慣性だけを `L×Fs` で換算し、8,207点目の流出、8,214点目の節点圧、8,229点目の流入と全PCMを対照と比較する。

## 咽頭の2本目の枝の現在慣性を連続描画で揃える

- 完了した項目。枝14→15の現在慣性の換算だけを上流順にした隔離版で、8,207点目の流出、8,214点目の節点14圧、8,229点目の流入が上流とビット一致した。流出の次の差は8,218点目で、持ち越し圧の単独置換で復元した。8,221点目の放射微分は節点15の壁流量の単独置換で復元した。[事前登録](cases/fixed-voice-pharyngeal-second-cell-inertance-48000.json)・[読解と結果](notes/fixed-voice-pharyngeal-second-cell-48000.md#現在慣性だけを変える連続描画の予測)
- 未達の条件。変更版と上流のPCMに停止後の12フレームの差があり、最大絶対差は対照の `2.27×10⁻¹³` から `5.82×10⁻¹¹` に増えた。枝14→15の持ち越し圧まで揃えた連続描画と停止後のPCM差の起点は未計測。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各9判定と固定上流の各12試験が通過した。各実行の壁・節点各104点、枝208点を十進数で検算し、生PCMから差の数・位置・最大値を再計算した。19出力をバイト比較し、計392入力と56出力のハッシュを照合した。採取物20,882,248バイトをRTL9210B-CGに保存した。[再実行マニフェスト](runs/fixed-voice-pharyngeal-second-cell-inertance-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-inertance-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の枝更新](crates/vocal-core/src/airway/network.rs#L189)と[上流の運動量の換算](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '.first_remaining_outgoing.outgoing_branch | {sample:.candidate.internal_sample,minimum_upstream_substitutions}' runs/fixed-voice-pharyngeal-second-cell-inertance-48000-repeat/summary.json` を実行する。枝14→15の持ち越し圧だけを `(L_carry×U_prev)×Fs` に揃え、8,218点目の流出、8,221点目の節点15の壁と放射、全PCMへの影響を比べる。

## 咽頭の2本目の枝の持ち越し圧を連続描画で揃える

- 完了した項目。枝14→15の持ち越し圧を揃えると、観測52点で両枝の流量と節点14の圧力・壁流量が上流と一致した。8,221点目の節点15の壁運動と放射微分は上流に一致した。放射微分の初差は8,237点目へ移り、節点17・21の壁流量の同時置換で復元した。[事前登録](cases/fixed-voice-pharyngeal-second-cell-history-48000.json)・[読解と結果](notes/fixed-voice-pharyngeal-second-cell-48000.md#持ち越し圧を揃えた連続描画の結果)
- 未達の条件。節点15の壁面積と流量には差が残る。停止後の上流と異なるPCMは12から13フレームへ増え、初差55,880フレーム目の発生段は未採取。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各9判定・固定上流の各12試験が通過した。各実行の壁と節点各104点、枝208点と生PCMを独立に照合した。19出力のバイト一致と404入力・56出力のハッシュを確認し、採取物20,882,400バイトをRTL9210B-CGに保存した。[再実行マニフェスト](runs/fixed-voice-pharyngeal-second-cell-history-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-pharyngeal-second-cell-history-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の出力段](crates/vocal-core/src/output.rs#L103)と[固定上流の出力段](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L395)を開き、`jq '.pcm.reordered_upstream | {first_bit_difference_frame,first_bit_difference_values,maximum_absolute_error}' runs/fixed-voice-pharyngeal-second-cell-history-48000-repeat/summary.json` を実行する。55,880フレーム目の前後で、内部放射、間引き器、直流除去とリミッターの状態を通常CLIの経路から採る。

## 停止後に最初に分かれるPCMを放射履歴から復元する

- 完了した項目。55,880フレーム目ではFIR係数・ゲイン・直流除去係数が一致し、放射履歴の置換で候補の出力段から上流PCMを再現した。直流除去の前回入力単独の置換でも同じ `f32` 値に丸まった。この点ではリミッターは作動していなかった。中央タップの111,737点目を含む4内部点は放射の単一点置換でPCMが一致した。[事前登録](cases/fixed-voice-release-output-48000.json)・[読解と結果](notes/fixed-voice-release-output-48000.md)
- 未達の条件。採取範囲の先頭111,697点目ですでに放射入力が分かれていた。置換でPCMが復元した4点で、壁・口端・鼻端・前回流量和のどの差が効くかは未採取。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回は放射ログ名の衝突で集計が止まり、ログ名を分けた各6判定と固定上流の各6試験が通過した。全PCMを先行実行と照合し、各実行の出力段51点を有理数・十進数で検算した。15出力がバイト一致し、374入力・46出力のハッシュを確認した。採取物7,324,297バイトをRTL9210B-CGに保存した。[初回の記録](runs/fixed-voice-release-output-48000-a/manifest.json)・[再実行マニフェスト](runs/fixed-voice-release-output-48000-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の放射流量の出力](crates/vocal-core/src/airway/network.rs#L791)と[固定上流の放射流量微分](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)を開き、`jq '."fixed-voice-release-output-48000-repeat".single_radiation_substitutions' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-output-48000.json` を実行する。内部111,732・111,734・111,737・111,738点目の放射成分を採って、保存したFIRと出力段の入力に置換する。

## 停止後の前回流量和を口端の流量まで分ける

- 完了した項目。4対象点で壁・口端・鼻端と前回流量和を採り、放射微分と出力55,880フレーム目のPCMを復元する最少の組を記録した。111,733・111,736点目は口端流量だけを上流値にし、隣接する2つの微分にも反映すると上流PCMに丸まった。111,732・111,738点目では、成分の局所置換で得た上流PCMが、隣接する微分へ反映した組では得られなかった。[事前登録](cases/fixed-voice-release-radiation-48000.json)・[読解と結果](notes/fixed-voice-release-radiation-48000.md)
- 未達の条件。111,733・111,736点目の口端流量差を作る放射負荷の項は未採取。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各6判定と固定上流の各9試験が通過し、全93,056 PCMフレームは各版の先行実行と一致した。各実行の壁972点と放射27点を十進数で検算した。23出力のバイト一致と、計394入力・62出力のハッシュを確認し、採取物6,587,929バイトをRTL9210B-CGに保存した。[再実行マニフェスト](runs/fixed-voice-release-radiation-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-radiation-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の口端負荷](crates/vocal-core/src/airway.rs#L89)と[固定上流の終端負荷](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)を開き、`jq '."fixed-voice-release-radiation-48000-repeat".previous_totals_split' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-radiation-48000.json` を実行する。111,733・111,736点目の口端流入、更新前圧、開口、放射負荷の状態から流量差を再計算する。

## 停止後の口端流量差を中点式の入力まで追う

- 完了した項目。全19点で口端の開口・放射係数が一致し、111,733・111,736点目の流量は更新前圧・持ち越し流量・流入の置換で上流と一致した。更新前圧だけでも55,880フレーム目の丸め先が一致した。口端負荷単体を連続更新すると、上流の流入系列で差が約1桁縮まり、初期状態も上流値に揃えると全19点の口端流量が一致した。[事前登録](cases/fixed-voice-release-lip-load-48000.json)・[読解と結果](notes/fixed-voice-release-lip-load-48000.md)
- 未達の条件。口端の更新前圧と枝流入は採取した先頭の111,725点目ですでに異なる。対象2点で流入差は直列枝から来るが、その枝のどの項が差を生むかは未採取。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各5判定と固定上流の各9試験が通過した。全PCMを保存済み出力と照合し、各実行の口端負荷57点を十進数で検算した。26出力のバイト一致と410入力・68出力のハッシュを確認し、実体6,667,395バイトをRTL9210B-CGに保存した。[再実行の保存記録](runs/fixed-voice-release-lip-load-48000-repeat/manifest.json)・[十進計算と連続再計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-load-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の直列枝の更新](crates/vocal-core/src/airway/network.rs#L189)と[固定上流の枝の中間項](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '."fixed-voice-release-lip-load-48000-repeat".replayed_sequence' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-load-48000.json` を実行する。111,733・111,736点目を含む区間で、口端直前の枝の両端圧・持ち越し運動量・方向別損失を採り、枝流量の差を再計算する。

## 停止後の口端直前の枝の圧差と持ち越し圧を照合する

- 完了した項目。枝47→48で、111,733・111,736点目は左圧・右圧・持ち越し圧の置換で上流流量と一致した。採取区間の慣性換算と抵抗は一致した。復元した枝流量だけを口端負荷に与える局所計算ではPCMは候補と同じ値に丸まった。測定圧を与える連続計算では、左右圧・初期流量と持ち越し圧の換算順を揃えると対象2点が上流と一致した。[事前登録](cases/fixed-voice-release-lip-branch-48000.json)・[読解と結果](notes/fixed-voice-release-lip-branch-48000.md)
- 未達の条件。口端直前の枝の持ち越し圧だけを変更した気道網全体の連続描画は未計測。両端圧と流量は採取区間の先頭で既に分かれており、停止後の55,880フレーム目のPCMには差が残る。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各5判定と固定上流の各12試験が通過した。全PCMを保存済みの出力と照合し、各実行で枝57点を十進数で検算した。32出力がバイト一致し、420入力と80出力をハッシュ照合した。採取物6,814,535バイトをRTL9210B-CGに保存した。[再実行マニフェスト](runs/fixed-voice-release-lip-branch-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-branch-48000.json)
- 次に開くファイルと実行するコマンド。[研究版の枝更新](crates/vocal-core/src/airway/network.rs#L189)と[上流の運動量換算](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)を開き、`jq '."fixed-voice-release-lip-branch-48000-repeat".prescribed_pressure_sequence' /Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-branch-48000.json` を実行する。この枝の持ち越し圧だけを `(L_carry×U_prev)×Fs` にする隔離版を作り、枝流量、口端圧・流量と55,880フレーム目を含む全PCMを比較する。

## 口端直前の持ち越し圧を揃えた全PCMを測る

- 完了した項目。枝47→48の持ち越し圧だけを上流順にすると、上流とPCMが異なる停止後のフレームは13から11へ減った。7フレームが新たに一致し、5フレームが新たに分かれた。最大絶対差は `5.82×10⁻¹¹`、初差は55,880フレーム目で両条件とも同じ。枝流量と口端流量は19点の最大差が増えた。変更は隔離版の比較差分として保存した。[事前登録](cases/fixed-voice-release-lip-history-48000.json)・[読解と結果](notes/fixed-voice-release-lip-branch-48000.md#持ち越し圧を揃えた連続描画の結果)
- 未達の条件。55,880フレーム目の1 ULP差と、枝47→48の圧力・前回流量の差は残る。各条件のPCMは既存許容差に収まった。実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIの一次記録は未登録。CoreMIDIの入力一覧は空だった。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。各6判定と固定上流の各12試験に通過した。各実行の枝・口端負荷各76点と生PCMを十進数で検算した。41出力のバイト一致と432入力・96出力のハッシュを確認し、採取物8,188,892バイトをRTL9210B-CGに保存した。[再実行マニフェスト](runs/fixed-voice-release-lip-history-48000-repeat/manifest.json)・[独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-history-48000.json)
- 次に開くファイルと実行するコマンド。[第5版の全体監査](notes/plan-evidence-audit.md#第5版で固定発声のwasmメモリを一次記録から照合する)と[監査のケース定義](cases/plan-completion-evidence.json)を開き、`jq '.pcm | {control_upstream,reordered_upstream}' runs/fixed-voice-release-lip-history-48000-repeat/summary.json` で固定発声の許容差と残差を確認する。これまでの停止後の計測を全体監査へ接続し、固定発声以外の未達条件と一次記録の所在を再照合する。

## 固定発声の停止後の一次PCMを全体監査に接続する

- 完了した項目。第5版の192判定を保持し、停止後の5計測と初回の集計エラーを保存ハッシュ・ケース・出力で照合した。48 kHzの全93,056フレームで、対照と変更版は分割128・77でそれぞれ同一。上流差は停止後の13から11フレーム、初差55,880の1 ULPと最大絶対差 `5.82e-11` は同じで、既存許容差 `5e-7` に収まった。[事前登録](cases/plan-completion-evidence.json)・[監査と独立計算](notes/plan-evidence-audit.md#第6版で固定発声の停止後を一次pcmから照合する)
- 未達の条件。比較した隔離版は55,880フレーム目の差が残る。固定LF・直接終端・一部のFirefox試行に保存した不合格がある。第7段階の実録音F2の人手注釈、TSP・CSD試聴回答、物理MIDIは未登録で、CoreMIDI入出力は各0件だった。[保存した不合格](notes/plan-evidence-audit.md#保存した不合格)・[人手と実機の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。研究ワークスペースと `/tmp` の各213判定、現行Rust 52試験、固定上流17試験、通常Webビルドに通過した。98実行の2,122出力を照合し、2回の要約はバイト一致した。計994入力・12出力を別にハッシュ照合し、新規ログ23,886バイトをRTL9210B-CGに保存した。[再実行マニフェスト](runs/plan-completion-release-v6-repeat/manifest.json)
- 次に開くファイルと実行するコマンド。[第7段階の取込手順](notes/plan-evidence-stage7.md#未確認の観測)と[受動MIDI計測](notes/worklet-midi-coremidi-passive.md#実行と結果)を開き、`jq '{listening_runs,f2_annotation_run,physical_midi_run}' runs/stage7-evidence-update-20261123-songbird-repeat/manifest.json` と `/usr/bin/swift tools/capture_coremidi_source.swift --list-inputs` で登録と収録元を確認する。取得した回答と実機の記録を取り込んだら、第7段階の監査を更新し、その合格実行IDを第6版の `--stage7-run` に指定する。

## CoreMIDI受動収録で同じ端子の表示名を扱う

- 完了した項目。異なる候補名2件で1端子が開いたまま60秒で停止する状況を仮想入力で再現した。待つ端子数を分けると、通常画面の押鍵と離鍵、220 Hz、無音復帰を確認できた。全PCMは各実行のCLIとビット一致した。[事前登録](cases/worklet-midi-coremidi-input-aliases.json)・[読解と結果](notes/worklet-midi-coremidi-passive.md#端子名と表示名が異なる入力)
- 未達の条件。物理鍵盤のCoreMIDI入力は0件で、候補名が異なる実機での収録は未観測。仮想入力を物理入力の実行IDとして指定した対照は監査で拒否した。実録音F2の人手注釈、TSP・CSDの試聴回答も未登録。[一次記録の状況](notes/plan-evidence-stage7.md#第11版でmidi入力の候補名と端子数を照合する)
- 最後に確認した実行。受動収録の各12判定、共有ノートの2入力条件の31判定、固定上流の2試験に通過した。第7段階第11版は72実行・161判定、全体監査は214判定に通過した。修正前と仮想入力の拒否を含む7実行の2,448入力・45出力を照合し、実体48,571,707バイトをRTL9210B-CGに保存した。[第7段階のマニフェスト](runs/stage7-evidence-update-20261123-midi-aliases/manifest.json)・[全体監査のマニフェスト](runs/plan-completion-release-v6-midi-aliases/manifest.json)
- 次に開くファイルと実行するコマンド。[受動MIDIの収録手順](notes/worklet-midi-coremidi-passive.md#実行と結果)を開き、`/usr/bin/swift tools/capture_coremidi_source.swift --list-inputs` で実機のUIDを確認する。仮想入力で続ける場合は [採取器の `observeMidi`](../../../web/prototypes/chimera-research/tools/capture-midi-coremidi.mjs#L23) を開き、対象外の入力1件を接続した条件で `tools/measure_worklet_midi_coremidi.py` の受動経路を検証する。人手回答が届いたら該当資料のCSVを取り込み、第7段階の監査に実行IDを渡す。[評価資料と取込](notes/plan-evidence-stage7.md#未確認の観測)

## MIDI受動収録で選択外の購読を解除する

- 完了した項目。選択外の無操作端子を含む仮想2端子で、切断後に購読1件が残る状況を再現した。登録済みラッパーで解除すると0件になった。別の `EventTarget` へ切断後に直接イベントを送った対照でも、コールバックの呼び出しが1回から0回になった。選択端子の押鍵・離鍵、220 Hz、無音復帰、CLIとの全PCM一致は維持した。[事前登録](cases/worklet-midi-coremidi-idle-input.json)・[読解と採取](notes/worklet-midi-coremidi-passive.md#選択外の入力が接続された状態での購読解除)
- 未達の条件。CoreMIDI入出力は各0件。物理端子からのイベントと対応するWorklet PCM、実録音F2の人手注釈、TSP・CSDの試聴回答は未登録。[第12版の状況](notes/plan-evidence-stage7.md#第12版で選択外のmidi入力の購読解除を照合する)
- 最後に確認した実行。仮想受動収録は別ディレクトリから各13判定、既存1端子は12判定、共有ノートは31判定、固定上流は2試験に通過した。第7段階第12版は73実行・169判定、全体監査は99実行・214判定に通過した。修正前を含む7実行の2,354入力・58出力を照合し、実体78,165,670バイトをRTL9210B-CGに保存した。[第7段階マニフェスト](runs/stage7-evidence-update-20261123-midi-idle/manifest.json)・[全体監査マニフェスト](runs/plan-completion-release-v6-midi-idle/manifest.json)
- 次に開くファイルと実行するコマンド。[実機の受動収録](notes/worklet-midi-coremidi-passive.md#実行と結果)を開き、`/usr/bin/swift tools/capture_coremidi_source.swift --list-inputs` で収録元を確認する。物理鍵盤が列挙されたらUIDと機器名を指定して通常の `--physical-source` で採取する。人手回答は[取込手順](notes/plan-evidence-stage7.md#未確認の観測)の資料IDに照合し、取得済みの実行を `tools/audit_stage7_evidence.py` に指定する。

## 受動MIDI収録で同名の2端子を識別する

- 完了した項目。Chromeで同名2端子が開いている場合に12秒で停止する問題を仮想入力で再現した。選択したCoreMIDI UIDとChromeの押鍵・離鍵のIDを照合し、同名の別端子からの余分な受信とIDの不一致を検出できた。2回とも48 kHzの全PCMがCLIに一致した。[事前登録](cases/worklet-midi-coremidi-same-name.json)・[読解と検証](notes/worklet-midi-coremidi-passive.md#同名の入力を受信イベントで照合する)
- 未達の条件。物理MIDI鍵盤は接続可能で、今回の指示に従って収録は後日に回す。実録音F2の人手注釈、TSP・CSDの試聴回答は未登録。固定録音6窓の正解F2との照合には、人手注釈が必要。[一次記録の状態](notes/plan-evidence-stage7.md#未確認の観測)・[録音6窓](notes/tsp-lpc-pre-emphasis-recordings.md#実測)
- 最後に確認した実行。仮想入力2回の各13判定、別名の無操作入力13判定、共有ノート31判定、固定上流2試験を通過した。第7段階第13版は74実行・176判定、全体監査は99実行・214判定に通過した。7実行の2,364入力・53出力をハッシュ照合し、63,321,115バイトをRTL9210B-CGに保存した。[第13版のマニフェスト](runs/stage7-evidence-update-20261123-midi-same-name/manifest.json)・[全体監査](runs/plan-completion-release-v6-midi-same-name/manifest.json)
- 次に開くファイルと実行するコマンド。[録音のプリエンファシス比較](notes/tsp-lpc-pre-emphasis-recordings.md#実測)と[既知F2の励振対照](notes/tsp-f2-harmonic-bandwidth.md#固定上流の読解と観測点)を開く。`jq '.windows[4] | {word, center, variants:[.variants[] | {pre_emphasis_coefficient, fixed_selection}]}' runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/summary.json` で `again` の中央窓の採択を確認する。設計F2を固定し、低域の追加共鳴だけを変えた合成対照で、採択が切り替わる条件を測る。

## 低域の追加共鳴がF2の採択を変える条件を測る

- 完了した項目。設計F2を2075 Hzに固定した9波形・54窓を照合した。F0 125 Hzで追加共鳴を760 Hzから800 Hzに動かすと、12次・14次の6窓すべてでF2の採択先が低域へ切り替わった。800〜1020 Hzの36窓でも設計F2の近傍極が有資格のまま残り、切り替わりをF2の採択規則で説明できた。[事前登録](cases/tsp-f2-intervening-resonance.json)・[読解と検証](notes/tsp-f2-intervening-resonance.md)
- 未達の条件。現在の切り替わり区間はF0 125 Hzでの760〜800 Hz。F0を変えた場合と、実録音に対する推定F2の正誤は未確認。人手F2注釈とTSP・CSDの試聴回答は未登録で、物理鍵盤の収録は後日に回す。[一次記録の取込](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。比較は別ディレクトリから各4判定、固定上流のLPC基準1件・TSP6件を通過した。要約、波形、Rustの出力はバイト一致した。第7段階第14版は75実行・179判定、全体監査は99実行・214判定に通過した。合成対照と監査の4実行で969入力・24出力を照合し、2,835,477バイトをRTL9210B-CGに保存した。[実測のマニフェスト](runs/tsp-f2-intervening-resonance-20261123-repeat/manifest.json)・[全体監査のマニフェスト](runs/plan-completion-release-v6-f2-intervening/manifest.json)
- 次に開くファイルと実行するコマンド。[既知F2の倍音間隔比較](notes/tsp-f2-harmonic-spacing.md)と[今回の合成ケース](cases/tsp-f2-intervening-resonance.json)を開く。`jq '[.windows[] | select(.added_pole_hz == 760 or .added_pole_hz == 800) | {added_pole_hz,order,center,added_mode_gap_from_selected_f1_hz,association}]' runs/tsp-f2-intervening-resonance-20261123-repeat/summary.json` で基準を確認し、追加共鳴を760 Hz・800 Hzに固定したままF0だけを変える。

## F0だけを変えて追加共鳴のF2採択を比較する

- 完了した項目。F0 100〜400 Hzの7条件、追加共鳴なし・760 Hz・800 Hzの21波形を126窓で照合した。同じ共鳴・次数・窓のF0 125 Hzとの差は72組中33組。低域の公開極を採った48窓では、設計F2の近傍極がF2の条件を満たすまま残った。固定した窓の励振位相も記録した。[事前登録](cases/tsp-f2-intervening-excitation.json)・[読解と検証](notes/tsp-f2-intervening-excitation.md)
- 未達の条件。F0による倍音配置と、固定窓に入る励振位相の寄与を個別に測る対照が残る。実録音のF2正解値とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[実測の範囲](notes/tsp-f2-intervening-excitation.md#7種類のf0での採択結果)・[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリから各5判定、固定上流のLPC基準1件・TSP6件を通過した。要約・波形・上流出力がバイト一致した。第7段階第15版は76実行・182判定、全体監査は99実行・214判定。比較と監査の4実行で986入力・24出力を照合し、6,563,828バイトをRTL9210B-CGに保存した。[対照のマニフェスト](runs/tsp-f2-intervening-excitation-20261123-repeat/manifest.json)・[全体監査マニフェスト](runs/plan-completion-release-v6-f2-excitation/manifest.json)
- 次に開くファイルと実行するコマンド。[励振の読解と結果](notes/tsp-f2-intervening-excitation.md)と[ケース定義](cases/tsp-f2-intervening-excitation.json)を開く。`jq -c '.windows[] | select(.added_pole_hz==760 and .order==12 and (.f0_hz==100 or .f0_hz==125)) | {f0_hz,center,start_sample,excitation_phase_samples,added_mode_gap_from_selected_f1_hz,association}' runs/tsp-f2-intervening-excitation-20261123-repeat/summary.json` で先行の位相と採択を確認する。760 Hzの追加共鳴とF0 125 Hzを固定し、周期インパルスと窓の相対位相だけを変える対照を測る。

## 固定した追加共鳴で励振位相を1周期調べる

- 完了した項目。F0 125 Hz、追加共鳴760 Hzを固定し、1周期内の遅延96通りを3時刻・2次数の576窓で照合した。全窓で設計F2近傍を採った。次数12で低域側の公開極とF1は最大199.31 Hz離れ、200 Hz境界を越えて採択が切り替わるという予測は反証された。[ケース定義](cases/tsp-f2-intervening-phase.json)・[読解と結果](notes/tsp-f2-intervening-phase.md)
- 未達の条件。760 Hzと800 Hzの間にある条件で、位相だけでも200 Hz境界と採択をまたぐか未計測。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリから各5判定、固定上流のLPC基準1試験・TSP 6試験に通過した。要約・窓標本・上流出力はバイト一致。第7段階第16版は77実行・185判定、全体監査は99実行・214判定に通過した。4実行の985入力と24出力をハッシュ照合した。[測定マニフェスト](runs/tsp-f2-intervening-phase-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-phase/manifest.json)
- 次に開くファイルと実行するコマンド。[位相ケース](cases/tsp-f2-intervening-phase.json)と[測定コード](tools/measure_tsp_f2_intervening_phase.py)を開き、`jq '{predictions, phase_results}' runs/tsp-f2-intervening-phase-20261123-repeat/summary.json` で採択と間隔を確認する。先行の追加共鳴760 Hzと800 Hzの中点780 Hzを別ケースに登録し、同じF0と窓で位相を1周期比較する。

## 追加共鳴780 Hzで励振位相による採択の切り替わりを調べる

- 完了した項目。F0 125 Hz、追加共鳴780 Hzを固定し、96位相を3時刻・2次数の576窓で照合した。次数12は全位相で追加共鳴側を採り、次数14は58位相で追加共鳴側、38位相で設計F2近傍を採った。切り替わった12組の隣接位相でF1と低域極の間隔が200 Hzをまたいだ。低域へ移った全462窓で設計F2近傍の極が候補に残った。[事前登録](cases/tsp-f2-intervening-phase-midpoint.json)・[読解と実測](notes/tsp-f2-intervening-phase-midpoint.md)
- 未達の条件。実録音の窓に低域極と高域極が共存する場合の採択の変化を確かめる。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。780 Hzの比較を異なる作業ディレクトリから行い、各6判定、固定上流のLPC基準1試験とTSP 6試験を通過した。要約・波形・上流出力はバイト一致し、共通化後の760 Hzも既存出力とバイト一致した。第7段階第17版は78実行・189判定、全体監査は99実行・214判定に通過した。5実行の1,021入力・30出力のSHA-256を照合した。[780 Hz再実行](runs/tsp-f2-intervening-phase-midpoint-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-phase-midpoint/manifest.json)
- 次に開くファイルと実行するコマンド。[実録音の次数比較ケース](cases/tsp-lpc-order-recordings.json)と[保存した上流の極](runs/tsp-lpc-order-recordings-20261122-repeat/artifacts/upstream-envelopes.json)を開く。`jq -c '.windows[] | {utterance,word,center,start_sample,change}' runs/tsp-lpc-order-recordings-20261122-repeat/summary.json` で6つの窓と候補の差を確認する。低域・高域の候補が共存する1窓を登録し、1周期を目安に窓開始を数標本ずらして間隔と採択を測る。

## 実録音の窓開始をずらしてF2候補を調べる

- 完了した項目。登録済みの実録音 `seems` の強勢母音を選び、次数14の25 ms窓を前後5 msで1標本ずつ動かした。全121窓で983.01〜996.26 Hzの極を採り、約2.3 kHzの極も候補に残った。低域の帯域幅は436.96〜558.54 Hzで、600 Hzを超えて採択が変わるという予測は外れた。[事前登録](cases/tsp-lpc-recording-window-shift.json)・[読解と実測](notes/tsp-lpc-recording-window-shift.md)
- 未達の条件。既存の評価出力から、採択されなかった公開極とその帯域幅を比較しやすい診断形式にする。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回と別の作業ディレクトリの再実行で各5判定、固定上流のLPC基準1試験・TSP 6試験に通過し、3出力はバイト一致した。第7段階第18版は79実行・192判定、全体監査は99実行・214判定に通過した。4実行の987入力・24出力をSHA-256で照合した。[再実行マニフェスト](runs/tsp-lpc-recording-window-shift-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-recording-window-shift/manifest.json)
- 次に開くファイルと実行するコマンド。[TSP評価の計測入口](tools/measure_tsp_stressed_vowel_formants.py)と[固定上流の窓ごとの結果](runs/tsp-stressed-vowel-formants-held-out-20261122-repeat/artifacts/upstream-formants.json)を開く。`jq -c '.MK61_01.sources.recording[] | select(.index==13) | .windows[]' runs/tsp-stressed-vowel-formants-held-out-20261122-repeat/artifacts/upstream-formants.json` で `seems` の既定窓を確認し、公表極・帯域幅・適格なF2候補と選定順を読み出す診断を既存TSPの結果に照合する。

## TSP評価に窓ごとのF2候補を出す

- 完了した項目。既存TSP CLIの `--f2-candidates` で、全185窓の公開極、帯域幅、F2の候補順位、採択と除外理由、中央値への寄与を出力した。177窓に複数候補があった。録音 `seems` の中央では993.37 Hzが選ばれ、2,323.81 Hzと2,862.40 Hzも候補に残った。[事前登録](cases/tsp-f2-candidate-report.json)・[診断の読解と再実行](notes/tsp-f2-candidate-report.md)
- 未達の条件。録音・固定上流・研究版でF2が異なる確認用母音について、候補位置と採択順位のどちらに差があるかを照合する。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。既定とオプション付きの実行が固定上流のLPC基準1試験・TSP 6試験に通過し、従来の評価要約と固定上流出力は保存済み基準とバイト一致した。診断の再実行で3出力が一致した。別の照合CLIで5判定を通過し、第7段階第19版は81実行・196判定、全体監査は99実行・214判定に通過した。6実行の1,049入力・30出力をSHA-256で照合した。[候補レポートの照合](runs/tsp-f2-candidate-report-20261123-verify/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-candidate-report/manifest.json)
- 次に開くファイルと実行するコマンド。[候補レポート](runs/tsp-f2-candidates-20261123-on/artifacts/f2-candidates.json)と[評価要約](runs/tsp-f2-candidates-20261123-on/summary.json)を開く。`jq -c '.windows[] | select(.utterance=="MK61_01" and .word=="seems" and .center==0.5) | {source,phone_index,f2_hz,poles}' runs/tsp-f2-candidates-20261123-on/artifacts/f2-candidates.json` で録音と合成の候補順を確認し、差を局所化する最小の共通母音を選ぶ。

## 同じ母音の録音と合成でF2の採択差を分ける

- 完了した項目。共通の `seems` の /i/ を3音源・15窓で再分析した。標準窓で合成と録音の採択差は1,192.04〜1,320.22 Hzで、同じ高域候補を比べた差は最大111.36 Hzだった。録音側が最初に採る約1 kHzの帯域に合成側の生根がなく、合成側のF1を録音と同じ値に固定しても採択は変わらなかった。[事前登録](cases/tsp-f2-source-comparison.json)・[比較の結果](notes/tsp-f2-source-comparison.md)
- 未達の条件。固定上流と研究版の高域候補の差を、発声中の声道断面と線形共鳴に照らして調べる。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。異なる作業ディレクトリからいずれも計測4判定、固定上流LPC基準1試験・TSP 6試験を通過し、要約・窓標本・固定上流出力はバイト一致した。第7段階第20版は82実行・199判定、全体監査は99実行・214判定に通過した。4実行の1,001入力・24出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-f2-source-comparison-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-source-comparison/manifest.json)
- 次に開くファイルと実行するコマンド。[発話状態を観測する入口](tools/measure_tsp_coat_to.py)と[声道の線形計測](notes/vowel-transfer.md)を開く。`jq -c '.windows[] | select(.center==0.5) | {source,start_sample,selected,bands}' runs/tsp-f2-source-comparison-20261123-repeat/summary.json` で対象位置を確認する。合成2版の母音中央1窓の実際の声道断面を取り、固定した形状の高域の線形共鳴をPCMの高域候補と照合する。

## 発話中の /i/ の断面で線形共鳴を測る

- 完了した項目。合成 `seems` の1.165秒で咽頭と口腔の36セルを採取し、実効断面を固定して線形応答を求めた。面積差は最大5.87×10⁻¹⁴ cm²、高域ピークは両版とも2,187.47 Hz。PCMの高域LPC極には15.70 Hz差があった。線形の丸め前の符号一致を記録した初版を保存し、0.1 Hz以下を判別不能にした。[ケース](cases/tsp-seems-tract-transfer.json)・[読解と結果](notes/tsp-seems-tract-transfer.md)
- 未達の条件。PCMの15.70 Hz差が出る段を、この時刻の断面比較だけでは特定できていない。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。通常CLIと観測付き描画の各116,132 PCMフレームは各版で一致した。891周波数点の独立求解を照合し、初版を別ディレクトリから再現、第2版でも断面・応答はバイト一致した。第2版は5判定・上流4試験・研究版17試験、第7段階第21版は83実行・202判定、全体監査は99実行・214判定に通過した。5実行の1,379入力・36出力をSHA-256で照合した。[第2版のマニフェスト](runs/tsp-seems-tract-transfer-20261123-resolved/manifest.json)・[全体監査](runs/plan-completion-release-v6-seems-tract/manifest.json)
- 次に開くファイルと実行するコマンド。[発話の音源と放射を観測する計測器](tools/measure_tsp_fine_variation.py)と[今回の応答](runs/tsp-seems-tract-transfer-20261123-resolved/summary.json)を開く。`jq '{completed_frames,pcm_poles_hz,linear_delta_hz,pcm_delta_hz}' runs/tsp-seems-tract-transfer-20261123-resolved/summary.json` で観測時刻を確認し、同じ25 ms窓の声門流量・口端放射・PCMを両版で採ってスペクトルを照合する。

## 同じ /i/ の声門流量からPCMまでの高域差を測る

- 完了した項目。`seems` の /i/ の同じ25 ms窓で、声門流量の高域パワー分布の距離が0.205、口端0.096、PCM0.094と測った。LPC極の版間差は放射の間引き直後15.74 Hz、最終PCM15.70 Hzだった。両版の放射差分を共通の出力段へ通し、先頭56,600フレームのPCMをビット単位で再現した。[事前登録](cases/tsp-seems-spectrum-stages.json)・[観測と再計算](notes/tsp-seems-spectrum-stages.md)
- 未達の条件。声門流量の差に対するドリフトと気道からの圧差の寄与を切り分ける。実録音のF2注釈、TSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回とも計測4判定、固定上流8試験、研究版17試験を通過した。各通常CLIと観測付き描画の全116,132フレームが揃い、窓・スペクトル・固定LPC・要約は再実行でバイト一致した。第7段階第22版は84実行・205判定、全体監査は99実行・214判定に通過した。4実行の1,257入力・28出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-seems-spectrum-stages-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-seems-spectrum-stages/manifest.json)
- 次に開くファイルと実行するコマンド。[上流発話の観測器](tools/upstream_tsp_closure_probe.rs)と[先行の音源変動比較](tools/measure_tsp_fine_variation.py)を開く。`jq '{pcm_frame_interval,spectra,lpc_high_candidate_minus_upstream_hz}' runs/tsp-seems-spectrum-stages-20261123-repeat/summary.json` で通常条件を確認し、上流のドリフトだけを止めた対照を同じ25 ms窓で比較する。

## 同じ /i/ で上流のドリフトだけを止める

- 完了した項目。固定上流のドリフト振幅を5セントから0にすると、研究版までの声門流量の高域パワー分布の距離が0.205から0.113に縮み、PCMの高域LPC極の版間差は−15.70 Hzから+5.95 Hzになった。最初に瞬時F0と位相が変わり、声門面積と流量、圧差の順に変化した。瞬時F0の比は113,200標本で独立計算と一致した。[事前登録](cases/tsp-seems-drift-only.json)・[読解と結果](notes/tsp-seems-drift-only.md)
- 未達の条件。残った5.95 Hz差について、声帯へ戻る圧差がどこまで影響するか未計測。実録音のF2注釈、TSP・CSDの試聴回答は未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回とも計測6判定、上流4試験を通過し、要約、計画、観測窓、スペクトル、瞬時F0とLPC結果はバイト一致した。第7段階第23版は85実行・209判定、全体監査は99実行・214判定に通過した。4実行の1,033入力・32出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-seems-drift-only-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-seems-drift-only/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の声門状態を採るパッチ](tools/patches/upstream-tsp-fine-source-states.patch)と[今回の比較コード](tools/measure_tsp_seems_drift_only.py)を開く。`jq '{first_different_internal_sample, lpc_high_poles_hz, pcm_frame_interval}' runs/tsp-seems-drift-only-20261123-repeat/summary.json` で圧差が初めて異なる標本を見て、ドリフトを止めた条件で声門に渡す圧差だけを既定条件の系列に置き換える対照を登録する。

## 同じ /i/ で声帯への圧差入力を差し替える

- 完了した項目。ドリフト0の固定上流に通常条件の圧差を再入力した。窓内2,400標本で有声ゲートの圧力成分が上限に達し、瞬時F0と位相は一致した。声門流量の高域パワー分布の距離は3.42×10⁻¹⁰、LPC極の移動は−1.42×10⁻⁶ Hz。再入力は全232,264内部標本で供与側と一致し、自己圧差の再入力では全116,132 PCMフレームが一致した。[事前登録](cases/tsp-seems-pressure-replay.json)・[読解と結果](notes/tsp-seems-pressure-replay.md)
- 未達の条件。研究版との残差約5.95 Hzに対する周期長のjitterの寄与を調べる。圧差差し替えの効果量は母音中央1窓で確認した。実録音F2の注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回とも計測9判定、固定上流4試験を通過し、圧差系列、窓、スペクトル、固定LPC、要約はバイト一致した。先行のドリフト計測も同じ観測入口で再現した。第7段階第24版は86実行・213判定、全体監査は99実行・214判定に通過した。5実行の1,094入力・46出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-seems-pressure-replay-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-seems-pressure-replay/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の声門振動](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs)と[研究版の音源初期化](crates/vocal-core/src/voice.rs)を開く。`jq '{window_pressure, lpc_high_poles_hz, first_different_internal_sample}' runs/tsp-seems-pressure-replay-20261123-repeat/summary.json` で固定して比較する窓を確認する。ドリフト0のまま上流のjitter係数だけを0にし、周期境界・位相・振幅と高域LPC極を採る比較を登録する。

## 同じ /i/ で周期長ジッターを切り替える

- 完了した項目。ドリフト0の両版にジッター0.00455を加えたときの高域LPC極の移動は、固定上流−3.64 Hz、研究版−3.55 Hz。ジッターを両版とも0にすると版間差は5.95 Hzから2.30 Hzに縮んだ。両版の最初の位相差は第872内部標本。ジッター係数をそろえた両版の瞬時F0と位相は113,200内部標本すべてで一致した。[事前登録](cases/tsp-seems-period-jitter.json)・[読解と結果](notes/tsp-seems-period-jitter.md)
- 未達の条件。残る2.30 Hz差に対する振幅のシマーの寄与を調べる。今回の効果量は母音中央1窓での結果。実録音F2の注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回とも計測7判定、上流4試験と研究版17試験を通過し、要約・周期系列・窓・スペクトル・LPC・計画がバイト一致した。先行の圧差再入力も同じ入口で再現した。第7段階第25版は87実行・218判定、全体監査は99実行・214判定に通過した。5実行の1,348入力・54出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-seems-period-jitter-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-seems-period-jitter/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の周期振幅の更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs)と[研究版の `source_variation` 読み込み](crates/vocal-cli/src/timing_case/speech_voice.rs)を開く。`jq '{lpc_high_poles_hz,cycle_models,candidate_minus_upstream_also_jitter_zero_hz}' runs/tsp-seems-period-jitter-20261123-repeat/summary.json` で同じ窓と周期を確認する。両版のジッターとドリフトを0にそろえた条件で、シマー0と0.042を比較するケースを登録する。

## 同じ /i/ で周期振幅のシマーを切り替える

- 完了した項目。ドリフト・ジッターを0にした両版で、シマー0.042の追加により高域LPC極が2.3033 Hz下がった。シマー0と0.042のどちらに揃えても、LPC入力300標本と極が一致した。シマーの差は第871内部標本の振幅倍率、第8,081標本の声門面積と流量に現れた。シマーを揃えた両版は113,200内部標本すべてで振幅倍率が一致した。[事前登録](cases/tsp-seems-amplitude-shimmer.json)・[読解と結果](notes/tsp-seems-amplitude-shimmer.md)
- 未達の条件。シマーを揃えても発話冒頭の舌先位置と口端流量は内部第0標本、PCMは第0フレームから異なる。初期調音姿勢と気道断面の寄与を調べる。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回とも計測8判定、上流4試験と研究版17試験を通過し、要約・周期系列・窓・スペクトル・LPC・計画はバイト一致した。先行のジッター比較も共通の観測器で再現した。第7段階第26版は88実行・223判定、全体監査は99実行・214判定に通過した。5実行の1,485入力・59出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-seems-amplitude-shimmer-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-seems-amplitude-shimmer/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の `HumanVoice::new`](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs)と[研究版の `for_speech_with_body`](crates/vocal-core/src/voice.rs)を開く。`jq '.across_engines.shimmer_zero | {first_different_internal_sample,first_different_pcm_frame,first_pcm_frame_over_tolerance}' runs/tsp-seems-amplitude-shimmer-20261123-repeat/summary.json` で冒頭の最初の差を確認する。音源設定を揃えたまま初期調音姿勢だけを一致させ、初期の断面積、圧差、口端流量とPCMを採る対照を登録する。

## 同じ発話で初期舌先と発話前の放射を照合する

- 完了した項目。音源設定を揃えた `seems` で研究版の舌先を固定上流の休止位置に揃えた。口腔の初期実効面積の最大差は1.054 cm²から7.99×10⁻¹⁵ cm²に縮まり、冒頭2,400 PCMフレームはビット一致した。全116,132フレームの最大PCM差は4.66×10⁻¹⁰、母音中央のLPC入力の差は0だった。[事前登録](cases/tsp-seems-initial-tip.json)・[読解と結果](notes/tsp-seems-initial-tip.md)
- 未達の条件。初期姿勢と音源設定を揃えたときの全PCMの一致範囲を、別の確認用発話へ広げて調べる。実録音F2の注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回とも計測5判定、上流9試験と研究版17試験を通過し、初期断面、観測窓、計画と要約がバイト一致した。上流の下唇の連続性試験1件は既存の `ignore` 指定。先行の1.165秒の断面・線形応答の比較も再現した。第7段階第27版は89実行・227判定、全体監査は99実行・214判定に通過した。5実行の1,496入力・54出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-seems-initial-tip-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-seems-initial-tip/manifest.json)
- 次に開くファイルと実行するコマンド。[初期舌先の比較コード](tools/measure_tsp_seems_initial_tip.py)と[確認用発話の評価ケース](cases/tsp-active-duration-original.json)を開く。`jq '.splits.held_out | keys' runs/tsp-active-duration-original-20261121-repeat/summary.json` で確認用発話を確認する。比較済みの2発話に続く確認用発話を選び、対応する体型の出力ゲイン、音源設定と初期舌先を揃え、全PCMの残差と母音・子音の観測区間を比較するケースを登録する。

## 確認用12発話で音源と初期舌先を揃える

- 完了した項目。確認用12発話に固定上流と同じ音源、初期舌先、体型別ゲインを適用した。PCM全1,487,586フレームの最大差は1.86×10⁻⁹で、閾値1×10⁻⁶の超過は0件。計画音素316区間と−35 dBの発話区間が全件一致した。最大差は女性2発話の /i/ と /ɝ/ に各1標本あり、隣接するfloat32値の1刻みだった。[事前登録](cases/tsp-held-out-matched-speech.json)・[読解と結果](notes/tsp-held-out-matched-speech.md)
- 未達の条件。このPCMを入力したときに既存のTSP強勢母音のLPC候補とF2採択がどこまで揃うか未計測。実録音F2の注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2回とも計測6判定、上流10試験と研究版17試験が通過し、PCM、入力、計画、要約の38出力がバイト一致した。第7段階第28版は90実行・231判定、全体監査は99実行・214判定に通過した。4実行の1,396入力・94出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-held-out-matched-speech-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-held-out-matched-speech/manifest.json)
- 次に開くファイルと実行するコマンド。[既存TSPの強勢母音計測](tools/measure_tsp_stressed_vowel_formants.py)と[評価ケース](cases/tsp-stressed-vowel-formants-held-out.json)を開く。`jq '.measurement' cases/tsp-stressed-vowel-formants-held-out.json` で分析窓、間引き、採択の設定を確認する。保存した設定合わせ後の両版のPCMに同じ窓を適用し、公開LPC極・F2の採択と欠測を比較するケースを登録する。

## 設定を揃えたPCMでTSPの強勢母音を再計測する

- 完了した項目。既存の4発話・12強勢母音で、共通60窓の両版の公開極は最大5.90×10⁻⁷ Hz差で、F2候補順・欠測は一致した。同じ研究版PCMに保存MFAの別境界を使うと15窓のF2が変わり、最大差は109.53 Hzだった。録音 `seems` の中央窓の採択993.37 Hzと両合成の2,228.15 Hzには1,234.78 Hzの差が残った。[事前登録](cases/tsp-matched-speech-formants.json)・[読解と結果](notes/tsp-matched-speech-formants.md)
- 未達の条件。設定合わせ後の両版を既存のMFA入力形式へ変換したPCMと、その再整列境界が未計測。録音の正解F2は人手注釈が必要で、TSP・CSDの試聴回答も未登録。物理鍵盤の収録は後日に回す。[一次記録](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。最初の試行では計測前にハッシュ関数のインポート漏れで終了した。修正後の2回は計測7判定と上流7試験に通過し、固定出力、候補レポート、窓別比較と要約はバイト一致した。第7段階第29版は91実行・235判定、全体監査は99実行・214判定に通過した。4実行の1,086入力・26出力をSHA-256で照合した。[再実行のマニフェスト](runs/tsp-matched-speech-formants-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-matched-speech-formants/manifest.json)
- 次に開くファイルと実行するコマンド。[MFAのノイズ添加とPCM16変換](tools/measure_tsp_phone_boundaries.py)と[確認用の整列ケース](cases/tsp-phone-boundaries-held-out.json)を開く。`jq '.aligner' cases/tsp-phone-boundaries-held-out.json` で乱数種・音響モデル・実行環境を確認する。同じ4発話の設定合わせ後PCMを両版とも既存条件で変換し、MFA入力の差と音素境界を照合するケースを登録する。

## 設定を揃えた合成4組をMFAで再整列する

- 完了した項目。量子化前の両版には最大1.86×10⁻⁹の標本差が残った。固定Rustと研究の変換は全8入力で一致し、合成4組はPCM16全521,718標本と語34区間、音素110区間の境界が一致した。60窓の開始位置差は15窓から0窓、最大216標本から0標本になった。[事前登録](cases/tsp-matched-speech-mfa.json)・[読解と結果](notes/tsp-matched-speech-mfa.md)
- 未達の条件。録音 `seems` の50%窓と合成でF2の自動採択に1,234.78 Hz差がある。録音のF2人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリから各4判定、固定上流6試験に通過した。主要30出力はバイト一致した。第7段階第30版は92実行・239判定、全体監査は99実行・214判定に通過した。4実行の1,160入力・76出力をSHA-256で照合し、成果4,429,135バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-matched-speech-mfa-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-matched-speech-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[録音のF2注釈手順](notes/tsp-f2-human-intake.md)と[判定者向け資料](runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)を開く。記入済みCSVが届いたら、研究ワークスペースで `CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 ../../.venv/bin/python tools/measure_tsp_f2_annotation.py collect tsp-f2-human-new --packet tsp-f2-annotation-20261122-repeat --kind human --response 'rater-a=/path/to/observations.csv'` を実行する。境界の原因を細分する場合は `FK61_01` で初期舌先だけを旧設定へ戻す比較を事前登録する。[最小の対照](findings.md)

## 初期舌先だけを戻して again の境界を測る

- 完了した項目。確認用 `FK61_01` で初期舌先だけを旧値に戻し、発話計画と音源条件を固定した。最初の50 msのPCMに最大0.00189の差が出たが、`again` 付近の9,600標本と語・音素の整列境界は一致した。/ɛ/–/n/ 境界は2.040秒、90%窓のF2は2,034.56 Hzだった。同じPCMへ旧境界を適用したときのF2差109.53 Hzを再現した。[事前登録](cases/tsp-again-initial-tip-mfa.json)・[読解と結果](notes/tsp-again-initial-tip-mfa.md)
- 未達の条件。旧比較の境界差への音源の揺らぎと出力ゲインの寄与は未分離。実録音のF2注釈とTSP・CSDの試聴回答は未登録。物理鍵盤は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各8判定と上流11試験に通過し、主要25出力がバイト一致した。第7段階第31版は93実行・243判定、全体監査は99実行・214判定に通過した。4実行の1,398入力・68出力をSHA-256で照合し、成果3,992,009バイトをRTL9210B-CGに保存した。[計測の再実行](runs/tsp-again-initial-tip-mfa-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-again-initial-tip-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[周期長ジッターの読解](notes/tsp-seems-period-jitter.md)と[再整列の計測コード](tools/measure_tsp_again_initial_tip_mfa.py)を開く。研究ワークスペースで `jq '.speech_voice.source_variation' runs/tsp-again-initial-tip-mfa-20261123-repeat/artifacts/matched-case.json` を実行する。同じ発話・姿勢・出力ゲインに周期長ジッターだけを旧値へ戻した対照を事前登録する。人手のデータが届いた場合は[既存の取り込み手順](notes/plan-evidence-stage7.md#未確認の観測)を使う。

## 周期長ジッターを止めて again の境界を測る

- 完了した項目。確認用 `FK61_01` で周期長ジッターだけを0にした。位相の初差は初回周期境界の次の内部831標本、声門面積・流量は8,083、通常PCMは出力4,059標本だった。固定した5窓でF2は最大3.89 Hz動き、MFAの /ɛ/–/n/ 境界は2.040秒、90%窓の開始は24,185標本のままだった。合成PCMの変化より早く出るMFA入力の差は、全発話に依存する雑音床の振幅から再計算できた。[事前登録](cases/tsp-again-period-jitter-mfa.json)・[読解と測定](notes/tsp-again-period-jitter-mfa.md)
- 未達の条件。旧比較の境界差への低速F0ドリフト、振幅シマー、出力ゲインの寄与は未分離。実録音F2の注釈とTSP・CSD試聴回答は未登録。物理鍵盤は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各10判定と上流13試験が通り、主要27出力がバイト一致した。初期舌先の回帰では主要25出力が一致した。第7段階第32版の94実行・247判定、全体監査の99実行・214判定が通過した。5実行の1,585入力・100出力をSHA-256で照合し、成果13,212,098バイトをRTL9210B-CGに保存した。[計測](runs/tsp-again-period-jitter-mfa-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-again-period-jitter-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[低速F0ドリフトの読解](notes/tsp-seems-drift-only.md)と[再整列の計測コード](tools/measure_tsp_again_initial_tip_mfa.py)を開く。研究ワークスペースで `jq '.speech_voice.source_variation' runs/tsp-again-period-jitter-mfa-20261123-repeat/artifacts/matched-case.json` を実行し、同じ発話で低速F0ドリフトだけを5セントから0へ戻す対照を事前登録する。人手のデータが届いた場合は[既存の取り込み手順](notes/plan-evidence-stage7.md#未確認の観測)を使う。

## 低速F0ドリフトを止めて旧整列境界を照合する

- 完了した項目。確認用 `FK61_01` で低速F0ドリフトだけを5セントから0にした。全232,264内部標本で瞬時F0比の独立計算との差は最大2.89×10⁻¹³セントだった。 /ɛ/–/n/ 境界は2.040秒から2.060秒へ動き、旧研究版の語8区間と音素25区間すべてが再現された。90%窓は、境界固定ではF2が−2.03 Hz、0セントPCMの境界を再整列結果へ変えると+101.67 Hz動いた。境界差10 ms以内という予測は外れた。[事前登録](cases/tsp-again-pitch-drift-mfa.json)・[読解と測定](notes/tsp-again-pitch-drift-mfa.md)
- 未達の条件。この設定変更で旧境界差が再現する範囲は1発話のみ確認した。旧差の残る10窓は `MK61_01` にある。実録音F2注釈とTSP・CSD試聴回答は未登録で、物理鍵盤は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各11判定・上流13試験に通過し、主要28出力がバイト一致した。初回監査はNumPyの真偽値のJSON変換で失敗し、修正後に第7段階第33版の95実行・251判定、全体監査の99実行・214判定に通過した。初回失敗も含む6実行の2,217入力・109出力をSHA-256で照合し、成果17,012,057バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-again-pitch-drift-mfa-20261123-repeat/manifest.json)・[初回監査の失敗](runs/stage7-evidence-update-20261123-again-pitch-drift-mfa/manifest.json)・[全体監査](runs/plan-completion-release-v6-again-pitch-drift-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[4発話の事前条件](cases/tsp-matched-speech-mfa.json)と[今回の計測コード](tools/measure_tsp_again_initial_tip_mfa.py)を開く。研究ワークスペースで `jq -r '[.[] | select(.candidate_minus_upstream_samples[0] != 0)] | group_by(.utterance)[] | [.[0].utterance, length] | @tsv' runs/tsp-matched-speech-mfa-20261123-repeat/artifacts/window-comparisons.json` を実行する。 `MK61_01` の旧差10窓と残る2発話を同じ条件で再整列し、旧境界の再現範囲を照合する。

## 4発話で低速F0ドリフトによる整列窓の再現範囲を測る

- 完了した項目。低速F0ドリフトだけを止める比較を4発話・60窓へ広げた。女性の `again` と男性の `plea` の計10窓で旧開始位置を再現した。全15窓を再現するという予測は外れた。旧差のない45窓は開始位置を保った。評価対象外では `FK61_02` の `he`–`lent` が70 ms早まった。瞬時F0比は521,718出力フレームで独立計算と最大2.90×10⁻¹³セント差だった。[事前登録](cases/tsp-matched-pitch-drift-mfa.json)・[読解と測定](notes/tsp-matched-pitch-drift-mfa.md)
- 未達の条件。 `MK61_01` の `again` では旧2.050秒の /ɛ/–/n/ 境界を再現できず、5窓の差が残った。実録音F2の注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各8判定・上流7試験に通過し、主要57出力がバイト一致した。第7段階第34版の96実行・255判定、全体監査の99実行・214判定に通過した。4実行の1,475入力・130出力をSHA-256で照合し、成果14,507,281バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-matched-pitch-drift-mfa-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-matched-pitch-drift-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[振幅シマーの読解](notes/tsp-seems-amplitude-shimmer.md)と[4発話の計測コード](tools/measure_tsp_matched_pitch_drift_mfa.py)を開く。研究ワークスペースで `jq '.speech_voice.source_variation' runs/tsp-matched-pitch-drift-mfa-20261123-repeat/artifacts/MK61_01/drift_zero.json` を実行し、ドリフト0の `MK61_01` でシマーだけを0にする対照を事前登録する。人手のデータが届いた場合は[取り込み手順](notes/plan-evidence-stage7.md#未確認の観測)を使う。

## 振幅シマーを止めて男性発話 again の境界を測る

- 完了した項目。 `MK61_01` のドリフト0条件で振幅シマーだけを0にした。振幅倍率は最初の周期境界の内部標本番号871で分かれた。瞬時F0と位相は一致し、固定窓のF2は最大1.30 Hz動いた。再整列した語8区間・音素25区間は基準と一致し、/ɛ/–/n/ 境界は2.030秒のままだった。[事前登録](cases/tsp-again-amplitude-shimmer-mfa.json)・[読解と測定](notes/tsp-again-amplitude-shimmer-mfa.md)
- 未達の条件。旧2.050秒境界に対応する `again` の5窓は再現しなかった。残る周期長ジッター、初期姿勢、ゲインとの関係は未分離。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各10判定・上流13試験に通過し、主要26出力がバイト一致した。ドリフト比較の回帰でも主要27出力が一致した。第7段階第35版の97実行・259判定、全体監査の99実行・214判定に通過した。5実行の1,645入力・103出力をSHA-256で照合し、成果16,757,502バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-again-amplitude-shimmer-mfa-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-again-amplitude-shimmer-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[周期長ジッターの読解](notes/tsp-seems-period-jitter.md)と[通常CLIと整列の計測コード](tools/measure_tsp_again_initial_tip_mfa.py)を開く。研究ワークスペースで `jq '.speech_voice.source_variation' runs/tsp-again-amplitude-shimmer-mfa-20261123-repeat/artifacts/shimmer_zero-case.json` を実行し、シマーとドリフトを0に保ったまま `MK61_01` の周期長ジッターだけを0へ戻す比較を事前登録する。[人手データの取り込み](notes/plan-evidence-stage7.md#未確認の観測)

## 男性発話で周期長ジッターを止めて残る5窓を測る

- 完了した項目。ドリフトとシマーを0にした `MK61_01` で周期長ジッターだけを0にした。位相は最初の周期境界の次の内部標本872から分かれ、固定窓のF2は最大19.13 Hz動いた。/ɛ/–/n/ 境界は2.030秒から2.050秒へ移り、事前予測の10 msを超えた。 `again` の5窓と `plea` の5窓が同じ条件で旧位置に一致し、旧研究版の語8区間と音素25区間を再現した。[事前登録](cases/tsp-again-male-period-jitter-mfa.json)・[読解と測定](notes/tsp-again-male-period-jitter-mfa.md)
- 未達の条件。3つの音源変動を止めた条件を4発話へ適用した場合の60窓と評価外の境界は未確認。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各10判定・上流13試験に通過し、主要26出力がバイト一致した。振幅シマー比較の回帰でも主要26出力が一致した。第7段階第36版の98実行・264判定、全体監査の99実行・214判定に通過した。5実行の1,659入力・102出力をSHA-256で照合し、成果16,586,404バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-again-male-period-jitter-mfa-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-again-male-period-jitter-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[4発話の計測コード](tools/measure_tsp_matched_pitch_drift_mfa.py)と[4発話の窓定義](cases/tsp-matched-pitch-drift-mfa.json)を開く。研究ワークスペースで `jq '.speech_voice.source_variation' runs/tsp-again-male-period-jitter-mfa-20261123-repeat/artifacts/jitter_zero-case.json` を実行する。同じ音源の3係数を0にした条件を4発話へ適用し、旧15窓と `FK61_02` の評価外の /i/–/l/ 境界を照合する。[最小の対照](findings.md)

## 4発話で音源の3変動を止め、全境界を照合する

- 完了した項目。ドリフト、周期長ジッター、振幅シマーを0にすると、旧差15窓すべての開始位置を再現し、残る45窓の開始位置も保った。 `FK61_02` の `he`–`lent` は旧位置の0.330秒へ戻った。旧比較と同じ開始位置で60窓を測ると、旧PCMとのF2差は最大3.09×10⁻⁵ Hzだった。[事前登録](cases/tsp-matched-source-variation-zero-mfa.json)・[読解と測定](notes/tsp-matched-source-variation-zero-mfa.md)
- 未達の条件。旧比較との全区間の差は `FK61_02` の `tall` の /ɔ/–/l/ 境界（1.650秒対1.680秒）に残った。実録音F2の注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各8判定と上流7試験に通過し、主要57出力がバイト一致した。ドリフトのみの回帰でも主要57出力が一致した。第7段階第37版の99実行・269判定と全体監査の99実行・214判定に通過した。5実行の1,708入力・189出力をSHA-256で照合し、成果21,807,123バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-matched-source-variation-zero-mfa-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-matched-source-variation-zero-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[整列用雑音の前処理](tools/measure_tsp_phone_boundaries.py)と[4発話の読解](notes/tsp-matched-source-variation-zero-mfa.md)を開く。研究ワークスペースで `jq '.speech_voice.voice.output_gain' runs/tsp-matched-source-variation-zero-mfa-20261123-repeat/artifacts/FK61_02/variation_zero.json runs/tsp-active-duration-original-20261121-repeat/artifacts/FK61_02/candidate.json` を実行し、ゲインだけを旧値へ戻す対照を事前登録する。[最小の対照](findings.md)

## 出力ゲインだけを旧値へ戻して tall の境界を測る

- 完了した項目。音源の3変動を0に保ち、`FK61_02` のゲインを8/7倍へ戻した。独立計算は両条件のPCM全標本と一致し、旧ゲインへの変更で固定窓のF2は最大2.86×10⁻⁵ Hz動いた。 `tall` の /ɔ/–/l/ 境界は1.650秒のままだった。旧研究版との整列用PCM16の差4,679標本は冒頭約251 msに収まり、`tall` 周辺の12,000標本は一致した。[事前登録](cases/tsp-tall-output-gain-mfa.json)・[読解と測定](notes/tsp-tall-output-gain-mfa.md)
- 未達の条件。旧研究版の1.680秒境界を再現できなかった。冒頭波形の差と初期舌先の関係は未検証。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回はMFAへ渡すサンプルレートの配置が合わず停止し、途中波形と設定を保存した。修正後は別ディレクトリで各9判定・上流8試験に通過し、主要22出力がバイト一致した。第7段階第38版の100実行・274判定と全体監査の99実行・214判定に通過した。成功4実行の1,493入力・60出力をSHA-256で照合し、成果5,962,411バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-tall-output-gain-mfa-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-output-gain-mfa/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-output-gain-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[初期舌先を戻した比較](notes/tsp-again-initial-tip-mfa.md)と[今回の測定コード](tools/measure_tsp_tall_output_gain_mfa.py)を開く。研究ワークスペースで `jq '.speech_voice.posture.tongue_tip_cm' runs/tsp-tall-output-gain-mfa-20261123-repeat/artifacts/old_gain-case.json runs/tsp-active-duration-original-20261121-repeat/artifacts/FK61_02/candidate.json` を実行する。出力ゲインは旧値、音源の3変動は0に固定し、初期舌先だけを旧値に戻す対照を登録する。

## 初期舌先だけを戻して tall の旧境界を再現する

- 完了した項目。 `FK61_02` の旧ゲインと音源3変動0の条件で初期舌先だけを旧値へ戻した。冒頭の調音座標差は独立計算と最大9.99×10⁻¹⁶ cm差だった。旧研究版の無加工PCMと整列用PCM16を各144,727標本再現し、語9区間と音素30区間が一致した。 `tall` の /ɔ/–/l/ は1.650秒から1.680秒へ動いた。固定窓のF2は5点とも一致し、再整列した90%窓で257.79 Hz上がった。[事前条件](cases/tsp-tall-initial-tip-mfa.json)・[読解と測定](notes/tsp-tall-initial-tip-mfa.md)
- 未達の条件。先頭約251 msにある整列用PCM16の差4,679標本のうち、境界を動かすのに十分な範囲は未確認。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各9判定・上流11試験に通過し、25出力がバイト一致した。ゲイン比較の回帰で20出力がバイト一致した。第7段階第39版の101実行・279判定と全体監査の99実行・214判定を通過した。5実行の1,677入力・92出力をSHA-256で照合し、成果7,921,160バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-tall-initial-tip-mfa-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-initial-tip-mfa/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-initial-tip-mfa/manifest.json)
- 次に開くファイルと実行するコマンド。[今回の測定](tools/measure_tsp_tall_initial_tip_mfa.py)と[MFAの入口](tools/measure_tsp_phone_boundaries.py)を開く。研究ワークスペースで `jq '.mfa_pcm.matched_to_old_render' runs/tsp-tall-initial-tip-mfa-20261123-repeat/summary.json` を実行し、対照の整列用PCM16の先頭2,400標本だけを旧舌先条件に置き換える比較を登録する。MFAの設定と評価区間は今回のものを使う。

## MFA入力の冒頭50 msと残りを交換して tall の境界を測る

- 完了した項目。 `FK61_02` の整列用PCM16で冒頭2,400標本だけを旧舌先に替えた条件と、2,400標本目以後だけを旧舌先に替えた条件を再整列した。対照との差はそれぞれ2,367標本と2,312標本。どちらも語9区間・音素30区間と /ɔ/–/l/ の1.680秒境界を旧舌先条件と同じ位置に再現した。50 ms以後だけなら1.650秒に留まるという予測は外れた。共通の無加工PCMを使ったLPCでは90%窓が324標本遅れ、F2は257.79 Hz上がった。[事前条件](cases/tsp-tall-mfa-preroll.json)・[読解と実測](notes/tsp-tall-mfa-preroll.md)
- 未達の条件。発話全体のケプストラム正規化とGMM-HMMの整列経路のどちらで遠方の差が現れるかは未分離。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各7判定・上流7試験に通過し、20出力がバイト一致した。第7段階第40版の102実行・284判定と全体監査の99実行・214判定を通過した。4実行の1,279入力・56出力をSHA-256で照合し、成果2,461,107バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-tall-mfa-preroll-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-mfa-preroll/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-mfa-preroll/manifest.json)
- 次に開くファイルと実行するコマンド。[正規化処理の読解](notes/tsp-tall-mfa-preroll.md#次の切り分け)と[PCM16の交換コード](tools/measure_tsp_tall_mfa_preroll.py)を開く。研究ワークスペースで `unzip -p /Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-mfa/downloads/english_us_arpa.zip english_us_arpa/meta.json | jq '.features | {uses_cmvn, frame_length, frame_shift, sample_frequency}'` を実行する。対照と冒頭だけを交換した条件の正規化前後のMFCCを採り、対照の正規化統計を共用する最小比較を事前登録する。

## MFAのCMVN統計だけを交換して tall の境界と特徴量を測る

- 完了した項目。対照PCMに冒頭交換側の統計だけを適用すると、`tall` は1.650秒から1.680秒へ動いた。逆の統計交換でも1.680秒になり、対照へ戻るという予測は外れた。非圧縮MFCCの差は先頭6フレーム、MFAの圧縮MFCCを読み戻した差は全302フレームにあった。対照統計の共用で局所の正規化後の最大係数差は0.62403から0.52988に減った。[事前条件](cases/tsp-tall-mfa-cmvn.json)・[読解と実測](notes/tsp-tall-mfa-cmvn.md)
- 未達の条件。最初のMFCCの圧縮と正規化後の圧縮が境界に与える寄与は未分離。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回はfloat64で二乗した独立計算の統計判定が不合格。float32で二乗してからfloat64で積算する第2版で、列和・二乗和と件数は完全一致し、初回の特徴量ハッシュと境界も保持した。別ディレクトリで各5判定・上流6試験に通過し18出力がバイト一致した。冒頭交換の回帰では21出力が一致した。第7段階第41版の103実行・290判定、全体監査の99実行・214判定に通過した。初回を含む6実行の1,325入力・94出力をSHA-256で照合し、成果5,477,273バイトをRTL9210B-CGに保存した。[初回](runs/tsp-tall-mfa-cmvn-20261123-a/manifest.json)・[再実行](runs/tsp-tall-mfa-cmvn-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-mfa-cmvn/manifest.json)
- 次に開くファイルと実行するコマンド。[今回の観測器](tools/probe_mfa_cmvn.py)と[インストール済みMFAのMfccFunction](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-mfa/env/lib/python3.11/site-packages/montreal_forced_aligner/corpus/features.py:164)を開く。研究ワークスペースで `jq '.feature_differences.own_stats' runs/tsp-tall-mfa-cmvn-20261123-repeat/summary.json` を実行し、最初のMFCC書き出しだけを非圧縮にする比較を事前登録する。

## MFAの最初のMFCC保存だけを非圧縮にする

- 完了した項目。最初のarkをfloat32で保存すると全4条件の行列が保存前のMFCCと完全一致した。対照統計の共用では正規化直後の差が先頭6フレームに収まり、最終の圧縮を読み戻すと全302フレームへ広がった。局所の最大係数差は0から0.53006になった。対照の `tall` が1.650秒から1.680秒へ動き、4条件の語9区間・音素30区間が旧位置に揃った。[事前条件](cases/tsp-tall-mfcc-input-compression.json)・[読解と実測](notes/tsp-tall-mfcc-input-compression.md)
- 未達の条件。最終保存の圧縮を外した比較が未実施で、そこで生じた特徴量差とGMM-HMMの経路が境界にどう寄与するかは未分離。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各5判定・上流6試験に通過し、主要28出力がバイト一致した。CMVN比較の回帰では18出力が一致した。第7段階第42版の104実行・295判定、全体監査の99実行・214判定を通過した。5実行の1,331入力・90出力をSHA-256で照合し、成果4,772,593バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-tall-mfcc-input-compression-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-mfcc-input-compression/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-mfcc-input-compression/manifest.json)
- 次に開くファイルと実行するコマンド。[保存形式の観測器](tools/probe_mfa_mfcc_archive.py)と[MFAのFinalFeatureFunction](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-mfa/env/lib/python3.11/site-packages/montreal_forced_aligner/corpus/features.py:268)を開く。研究ワークスペースで `jq '.observations.float32.feature_differences.both_control_stats' runs/tsp-tall-mfcc-input-compression-20261123-repeat/summary.json` を実行する。最初の保存をfloat32に固定し、最終保存だけをfloat32へ変える比較を事前登録する。

## MFAの最終MFCC保存だけを非圧縮にする

- 完了した項目。最初の保存をfloat32に固定し、最終保存を圧縮からfloat32へ変更した。対照統計を共用した場合、最終読み戻しの差は302フレームから先頭6フレームへ縮まり、`tall` 付近の最大係数差は0.53006から0になった。4条件すべてで語9区間と音素30区間は一致した。 `tall` は1.680秒のままで、対照が1.650秒へ戻るという予測は外れた。[事前条件](cases/tsp-tall-mfcc-final-compression.json)・[読解と実測](notes/tsp-tall-mfcc-final-compression.md)
- 未達の条件。最初の保存形式で1.650秒と1.680秒に分かれた同一PCMの条件について、GMM-HMMが読む特徴量、遷移ID列、経路の尤度差は未確認。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各6判定・上流6試験に通過し、27出力がバイト一致した。最初の保存形式の回帰も27出力が一致した。第7段階第43版の105実行・300判定、全体監査の99実行・214判定に通過した。5実行の1,361入力・99出力をSHA-256で照合し、成果5,099,331バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-tall-mfcc-final-compression-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-mfcc-final-compression/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-mfcc-final-compression/manifest.json)
- 次に開くファイルと実行するコマンド。[今回の次の切り分け](notes/tsp-tall-mfcc-final-compression.md#次の切り分け)と[KalpyのGmmAligner](/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-mfa/env/lib/python3.11/site-packages/kalpy/gmm/align.py:113)を開く。研究ワークスペースで `jq '.observations | map_values(.tall_vowel_intervals.control)' runs/tsp-tall-mfcc-input-compression-20261123-repeat/summary.json` を実行する。同一PCMの2経路を対象に、整列器へ渡す特徴量、遷移ID、フレーム別の尤度を測るケースを事前登録する。

## 同一PCMの1.650秒と1.680秒のGMM-HMM経路を交差採点する

- 完了した項目。2条件のモデルとFSTは同一で、302×40の特徴行列と遷移・語IDを保存した。音素ID差は165〜167番、PDF差は164〜168番。1.680秒経路から1.650秒経路を引いた重み付き得点は、圧縮開始で−0.00015213、float32開始で+0.00013016となった。音響項の差は `tall` 周辺だけにあり、遅い経路を支持するグラフ項と拮抗した。[事前条件](cases/tsp-tall-gmm-paths.json)・[読解と実測](notes/tsp-tall-gmm-paths.md)
- 未達の条件。合計得点の照合差0.00015744と0.00058640は経路間差より大きく、僅差の順位の安定性と、差のある5フレームだけを移した場合の境界は未確認。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回はKalpy行列の読み込み方を誤り交差採点で停止した。修正後の2実行は各7判定・上流6試験を通過し、主要24出力が一致した。初回と再実行の両 `decoder.npz` はバイト一致した。第7段階第44版の106実行・305判定と全体監査の99実行・214判定に通過した。5実行の1,364入力・86出力をSHA-256で照合し、成果1,784,789バイトをRTL9210B-CGに保存した。[初回](runs/tsp-tall-gmm-paths-20261123-a/manifest.json)・[再実行](runs/tsp-tall-gmm-paths-20261123-repeat/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-gmm-paths/manifest.json)
- 次に開くファイルと実行するコマンド。[デコーダの観測器](tools/probe_mfa_tall_gmm_paths.py)と[今回の測定ノート](notes/tsp-tall-gmm-paths.md#実測)を開く。研究ワークスペースで `jq '.different_pdf_frames' runs/tsp-tall-gmm-paths-20261123-repeat/summary.json` を実行する。164〜168番の5行だけと、残りの行だけをそれぞれ交換し、元のGMM-HMMで再整列する対照を事前登録する。

## GMM-HMMの特徴5行だけを交換して tall の境界を再現する

- 完了した項目。通常MFAで使用したモデル・FST・設定を固定し、164〜168番だけをfloat32開始の特徴に替えると、`tall` は1.650秒から1.680秒へ動いた。残り297行だけを替える条件では1.650秒だった。両方とも対応する対照の全遷移・語ID列と語9区間・音素30区間を再現し、固定2経路の得点差は5行の供給元と一致した。[事前条件](cases/tsp-tall-gmm-frame-swap.json)・[読解と実測](notes/tsp-tall-gmm-frame-swap.md)
- 未達の条件。164〜168番のどの部分集合で境界を動かせるかは未確認。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各5判定・上流6試験に通過し、34出力がバイト一致した。交差採点の回帰では24出力が一致した。第7段階第45版の107実行・310判定と全体監査の99実行・214判定に通過した。5実行の1,400入力・108出力をSHA-256で照合し、成果4,336,472バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-tall-gmm-frame-swap-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-gmm-frame-swap/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-gmm-frame-swap/manifest.json)
- 次に開くファイルと実行するコマンド。[特徴行の交換入口](tools/probe_mfa_tall_gmm_frame_swap.py)と[今回の測定ノート](notes/tsp-tall-gmm-frame-swap.md#実測)を開く。研究ワークスペースで `jq '{tall_range,margins_for_two_fixed_paths}' runs/tsp-tall-gmm-frame-swap-20261123-repeat/summary.json` を実行する。5行の32部分集合を再整列するケースを登録し、固定2経路の得点差が符号を変える組と実際の経路を照合する。

## GMM-HMMの5行の全32部分集合から最小の交換を特定する

- 完了した項目。PCM、モデル、FST、探索設定を固定し、164〜168番の全32部分集合を再整列した。14条件で `tall` の /ɔ/–/l/ 境界が1.650秒から1.680秒へ動いた。境界を変える最小は165・166番と165・167番の2組。166〜168番の3行も、境界を変える真部分集合を持たなかった。全32条件で固定2経路の得点差の符号と通常MFAの選択が一致した。[事前条件](cases/tsp-tall-gmm-frame-subsets.json)・[読解と実測](notes/tsp-tall-gmm-frame-subsets.md)
- 未達の条件。同一PCMでの境界の違いがLPCのF2推定に与える影響は未測定。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回は保存済み区間JSONのパスの誤りで停止した。次はCMVN索引の並びの仮定で停止したため、観測器を修正して再実行した。別ディレクトリで各6判定と上流6試験に通過し、202出力がバイト一致した。前回の5行交換の回帰では33出力が一致した。差は実行ログに限られた。第7段階第46版は108実行・315判定、全体監査は99実行・214判定に通過した。6実行の1,587入力・523出力をSHA-256で照合し、成果42,046,552バイトをRTL9210B-CGに保存した。[観測器の停止](runs/tsp-tall-gmm-frame-subsets-20261123-recheck/manifest.json)・[再実行](runs/tsp-tall-gmm-frame-subsets-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-gmm-frame-subsets/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-gmm-frame-subsets/manifest.json)
- 次に開くファイルと実行するコマンド。[今回の測定ノート](notes/tsp-tall-gmm-frame-subsets.md#実測)と[LPC窓の比較入口](tools/measure_tsp_tall_mfa_preroll.py)を開く。研究ワークスペースで `jq '.last_window' runs/tsp-tall-mfa-preroll-20261123-repeat/summary.json` を実行する。保存済みの同一PCMで /ɔ/ の開始位置を固定し、終端を1.650・1.660・1.670・1.680秒としたときの中央3窓のF2中央値と90%窓を比較するケースを事前登録する。

## 同一合成PCMで tall の母音終端に対するF2の感度を測る

- 完了した項目。同じ `FK61_02` の合成音声で、母音終端だけを1.650〜1.680秒の10 ms刻みで動かした。中央3窓のF2中央値の幅は23.98 Hz、90%窓は257.79 Hz。全16窓で固定上流と独立計算が一致し、欠測はなかった。90%窓のF2は全条件で2番目の極だった。[事前条件](cases/tsp-tall-f2-boundary-grid.json)・[読解と実測](notes/tsp-tall-f2-boundary-grid.md)
- 未達の条件。録音側の同じ語での終端感度は未測定。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各6判定と上流7試験を通過し、要約と窓別計測を含む4出力がバイト一致した。第7段階第47版は109実行・320判定、全体監査は99実行・214判定に通過した。4実行の1,512入力・24出力をSHA-256で照合し、成果71,876バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-tall-f2-boundary-grid-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-f2-boundary-grid/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-f2-boundary-grid/manifest.json)
- 次に開くファイルと実行するコマンド。[今回の計測入口](tools/measure_tsp_tall_f2_boundary_grid.py)と[録音側の境界](runs/tsp-phone-boundaries-held-out-20261121-a/artifacts/aligned-1-recording/FK61_02/FK61_02.json)を開く。研究ワークスペースで `jq '.tiers.phones.entries[] | select(.[0] > 1.4 and .[1] <= 1.75)' runs/tsp-phone-boundaries-held-out-20261121-a/artifacts/aligned-1-recording/FK61_02/FK61_02.json` を実行する。録音側の `AA1` の開始を固定し、保存時刻の前後を10 ms刻みで測る対照を事前登録する。

## tall の実録音で母音終端に対するF2の感度を測る

- 完了した項目。実録音 `FK61_02` の `tall` で `AA1` の終端を1.670〜1.700秒へ動かした。F2の幅は中央3窓の中央値で11.62 Hz、90%窓で72.21 Hz。90%窓が100 Hz以上動くという予測は外れた。全16窓で固定上流と独立計算の開始標本・採択が一致し、欠測はなかった。[事前条件](cases/tsp-tall-recording-f2-boundary-grid.json)・[読解と実測](notes/tsp-tall-recording-f2-boundary-grid.md)
- 未達の条件。人手注釈資料の `again` で窓位置が候補順位に与える感度は未測定。実録音F2注釈とTSP・CSD試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回はfloat32秒値を切り捨てて標本化したときの1標本差で不合格。第2版で開始標本を再計算し、2実行とも各5判定・上流7試験を通過した。合成側の回帰も以前の窓と要約が一致した。第7段階第48版は110実行・325判定、全体監査は99実行・214判定に通過した。6実行の1,572入力・36出力をSHA-256で照合し、成果120,049バイトをRTL9210B-CGに保存した。[初回](runs/tsp-tall-recording-f2-boundary-grid-20261123-a/manifest.json)・[再実行](runs/tsp-tall-recording-f2-boundary-grid-20261123-repeat/manifest.json)・[第7段階監査](runs/stage7-evidence-update-20261123-tall-recording-f2-boundary-grid/manifest.json)・[全体監査](runs/plan-completion-release-v6-tall-recording-f2-boundary-grid/manifest.json)
- 次に開くファイルと実行するコマンド。[窓位置の比較入口](tools/measure_tsp_lpc_recording_window_shift.py)と[人手注釈の取込](notes/tsp-f2-human-intake.md)を開く。研究ワークスペースで `jq '.trials.W06 | {utterance,word,center,analysis_samples}' runs/tsp-f2-annotation-20261122-repeat/artifacts/reference.json` を実行する。資料W06の `FK61_01` の `again` の中央窓だけを前後に動かし、候補極と採択の感度を事前登録する。

## 人手注釈資料W06の窓位置とF2候補を照合する

- 完了した項目。人手注釈のW06が指す `FK61_01` の `again` の中央窓で、開始を前後5 ms・1標本刻みで調べた。全121窓で2.1 kHz側を採り、2.9 kHz側も全窓で候補に残った。採択値の変動幅は97.10 Hz、欠測は0件。資料W06のWAVは元録音の切り出しとバイト一致した。[事前条件](cases/tsp-f2-annotation-w06-window-shift.json)・[読解と実測](notes/tsp-f2-annotation-w06-window-shift.md)
- 未達の条件。W06の窓を固定したときのプリエンファシスによる候補切り替えの係数は未測定。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各7判定と上流7試験に通過し、5出力がバイト一致した。既定の `seems` の回帰も結果を再現した。第7段階第49版は111実行・330判定、全体監査は99実行・214判定に通過した。5実行の1,568入力・30出力をSHA-256で照合し、成果431,906バイトをRTL9210B-CGに保存した。[実測の再実行](runs/tsp-f2-annotation-w06-window-shift-20261123-repeat/manifest.json)・[第49版の監査](runs/stage7-evidence-update-20261123-annotation-w06-window-shift/manifest.json)・[全体監査](runs/plan-completion-release-v6-annotation-w06-window-shift/manifest.json)
- 次に開くファイルと実行するコマンド。[録音のプリエンファシスの比較入口](tools/measure_tsp_lpc_pre_emphasis_recordings.py)と[W06の測定ノート](notes/tsp-f2-annotation-w06-window-shift.md#実測)を開く。研究ワークスペースで `jq '.trials.W06 | {analysis_samples,held_out_lpc_f2_hz}' runs/tsp-f2-annotation-20261122-repeat/artifacts/reference.json` を実行する。基準窓を固定して、既定0.97と0の間のF2候補の選択境界を調べるケースを事前登録する。

## W06のプリエンファシスとF2の切り替わりを測る

- 完了した項目。W06の同じ300標本を使い、プリエンファシスを0.001刻みで971点比較した。切り替わりは0.111〜0.112の1回で、約468 Hzの極の帯域幅が500 Hzを越え、約680 Hzの極がF1へ繰り上がった。F2採択は680.23 Hzから2,009.79 Hzへ移り、欠測は0件だった。[事前条件](cases/tsp-f2-annotation-w06-pre-emphasis.json)・[読解と実測](notes/tsp-f2-annotation-w06-pre-emphasis.md)
- 未達の条件。 `again` の35%・65%の窓で同じ機構が起こるかは未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDI鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。2実行とも3判定と上流7試験に通過し、4出力がバイト一致した。既存の6窓の回帰では9出力が一致した。第7段階第50版は112実行・335判定、全体監査は99実行・214判定に通過した。5実行の1,565入力・34出力をSHA-256で照合し、29,489,084バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-f2-annotation-w06-pre-emphasis-20261123-repeat/manifest.json)・[第50版の監査](runs/stage7-evidence-update-20261123-annotation-w06-pre-emphasis/manifest.json)・[全体監査](runs/plan-completion-release-v6-annotation-w06-pre-emphasis/manifest.json)
- 次に開くファイルと実行するコマンド。[係数比較の入口](tools/measure_tsp_f2_annotation_w06_pre_emphasis.py)を開き、研究ワークスペースで `jq '.trials | {W07: .W07.analysis_samples, W02: .W02.analysis_samples}' runs/tsp-f2-annotation-20261122-repeat/artifacts/reference.json` を実行する。W07とW02の固定窓で係数範囲を照合し、低域の極の出現とF1からの間隔・帯域幅による採択変化を事前登録する。

## again の35%・65%注釈窓と3窓のF2中央値を比較する

- 完了した項目。35%窓は971係数で高域を採択し、65%窓では0.190〜0.191で低域F2候補の幅が600 Hzを越えた。3窓の中央値は中央窓の切り替わりと同じ0.111〜0.112で822.19 Hzから2,009.79 Hzに移った。新規1,942条件を固定上流と独立計算で照合した。[事前条件](cases/tsp-f2-annotation-again-pre-emphasis.json)・[読解と実測](notes/tsp-f2-annotation-again-pre-emphasis.md)
- 未達の条件。この1トークンの中央値の変動が、複数トークンを集めたTSPのF2費用に与える影響は未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDI鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。別ディレクトリで各5判定と上流7試験を通過し、6出力がバイト一致した。W06の回帰は以前の入力窓・上流出力・要約を再現した。第7段階第51版は113実行・340判定、全体監査は99実行・214判定に通過した。5実行の1,584入力・32出力をSHA-256で照合し、成果71,828,147バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-f2-annotation-again-pre-emphasis-20261123-repeat/manifest.json)・[第51版の監査](runs/stage7-evidence-update-20261123-annotation-again-pre-emphasis/manifest.json)・[全体監査](runs/plan-completion-release-v6-annotation-again-pre-emphasis/manifest.json)
- 次に開くファイルと実行するコマンド。[固定上流のTSP比較](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)と[対応音素の先行出力](runs/tsp-stressed-vowel-formants-held-out-20261122-repeat/summary.json)を開く。研究ワークスペースで `rg -n 'fn (values|costs)|MIN_TOKENS' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs` を実行する。固定した対応音素列に今回の1トークンのF2を入れて、音素内中央値、支持数3件の条件、参照からの費用を照合するケースを登録する。

## again の1トークンのF2差をTSPの診断費用まで追う

- 完了した項目。実録音6話者36本で固定上流の合成・整列・対応音素を得た。 `again` のF2の差1,187.60 Hzに対し、FKの話者中央値の差は114.75 Hz、診断費用は1.28932から0.14472になった。採点対象3群と総合点は一致した。支持数2件と学習女性4名では費用が欠測になった。[事前条件](cases/tsp-again-f2-term-effect.json)・[読解と実測](notes/tsp-again-f2-term-effect.md)
- 未達の条件。学習用の録音側の1トークンに差が入った場合の参照中央値・MADと費用への影響は未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDI鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。最初の起動はPythonの読み込み漏れで実行記録の作成前に停止した。修正後は別ディレクトリから各4判定と上流6試験を通過し、5出力がバイト一致した。第7段階第52版は114実行・344判定、全体監査は99実行・214判定に通過。4実行の1,538入力・26出力をSHA-256で照合し、成果557,346バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-again-f2-term-effect-20261123-repeat/manifest.json)・[第52版の監査](runs/stage7-evidence-update-20261123-again-f2-term-effect/manifest.json)・[全体監査](runs/plan-completion-release-v6-again-f2-term-effect/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の参照の集約](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1169)と[固定した36録音の音素対応](runs/tsp-again-f2-term-effect-20261123-repeat/artifacts/native.json)を開く。研究ワークスペースで `jq '{training,reference}' runs/tsp-again-f2-term-effect-20261123-repeat/artifacts/native.json` を実行する。学習側39件の有効な /ɛ/ のF2を一件ずつ動かす対照を事前登録し、話者中央値、参照中央値、MAD、確認側の費用への差を照合する。

## 学習側の1トークンによるTSPのF2参照の感度を照合する

- 完了した項目。学習女性5名の /ɛ/ 39件に対し、一件ずつ2値に差し替える計78条件を実行した。参照中心が動いた位置は16件、中心と独立に評価の幅と費用が動いた位置は12件。8条件で幅に0.07の下限が効いた。FKの録音と合成を固定し、上流と独立計算を全条件で照合した。[事前条件](cases/tsp-f2-training-reference-sensitivity.json)・[読解と実測](notes/tsp-f2-training-reference-sensitivity.md)
- 未達の条件。学習話者数を増やした場合の参照の感度は未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDI鍵盤の計測は後日に回す。[未確認の観測](notes/plan-evidence-stage7.md#未確認の観測)
- 最後に確認した実行。初回はRustの文書コメントの形式でコンパイル失敗。修正後は別ディレクトリから各3判定・上流6試験に通過し、4出力が一致した。第52版の回帰も再現した。第7段階第53版は115実行・349判定、全体監査は99実行・214判定に通過した。初回を含む6実行の1,569入力・35出力をSHA-256で照合し、成果389,338バイトをRTL9210B-CGに保存した。[初回](runs/tsp-f2-training-reference-sensitivity-20261123-a/manifest.json)・[再実行](runs/tsp-f2-training-reference-sensitivity-20261123-repeat/manifest.json)・[第53版の監査](runs/stage7-evidence-update-20261123-f2-training-reference-sensitivity/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-training-reference-sensitivity/manifest.json)
- 次に開くファイルと実行するコマンド。[資料の抽出条件](cases/tsp-again-f2-term-effect.json)と[参照計算の入口](tools/measure_tsp_f2_training_reference_sensitivity.py)を開く。研究ワークスペースで `jq '.statistics.by_speaker' runs/tsp-f2-training-reference-sensitivity-20261123-repeat/summary.json` を実行する。学習女性を増やす際の収録の選び方と、同じ39件・同じ2値を用いる対照を事前登録する。

## 学習女性を10名に増やして同じF2差し替えを照合する（2026-11-23）

- 完了した項目。注釈で選んだFF〜FJの30録音から有効な強勢付き /ɛ/ のF2を37件追加し、元の39位置と2値で78条件を再計測した。参照中心の最大変動は0.05633から0.03197オクターブに減った。診断費用の最大変動は録音側で0.32981から0.63034へ増え、合成側で0.75983から0.11591へ減った。全費用が安定するという事前予測を棄却した。[事前登録](cases/tsp-f2-training-reference-ten-speakers.json)・[読解と実測](notes/tsp-f2-training-reference-ten-speakers.md)
- 未達の条件。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。学習参照は女性の部分集合で比較した。TSP全コホートでの感度は未検証。
- 最後に確認した実行。研究ワークスペースと別ディレクトリで各4判定・上流6試験を通過し、主要9出力がバイト一致した。元の5名と `again` の回帰の上流出力・要約も一致した。追加37件のF2の独立計算は最大7.89e-11 Hz差で、欠測の判定も一致した。第7段階第54版は116実行・353判定、全体監査は99実行・214判定に通過した。6実行の1,595入力・45出力をSHA-256で照合し、成果794,213バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-f2-training-reference-ten-speakers-20261123-repeat/manifest.json)・[第54版の監査](runs/stage7-evidence-update-20261123-f2-training-reference-ten-speakers/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-training-reference-ten-speakers/manifest.json)
- 次に開くファイルと実行するコマンド。[計測ノート](notes/tsp-f2-training-reference-ten-speakers.md#実測)と[独立計算](tools/measure_tsp_f2_training_reference_ten_speakers.py)を開く。研究ワークスペースで `jq '.interventions[] | select(.utterance == "FD19_10" and .slot == 15)' runs/tsp-f2-training-reference-ten-speakers-20261123-repeat/summary.json` を実行する。この1位置で無介入時と介入後の中心・幅を組み合わせ、同じFK値に対する費用とゼロ境界の判定を事前登録する。

## 同じF2介入で参照中心と評価幅の寄与を分ける（2026-11-23）

- 完了した項目。5名と10名で、`FD19_10` の対応音素列の15番に対する参照中心と評価幅を個別に固定した。10名のFK録音側の増分0.63034は、両順序の平均で中心0.07896、幅0.55138だった。合成側は無介入と中心だけでは0、幅だけで0.11591、両方で0.02291。第54版のノートの費用0という記述を保存済み上流出力と照合して訂正した。[事前登録](cases/tsp-f2-reference-centre-width.json)・[読解と実測](notes/tsp-f2-reference-centre-width.md)
- 未達の条件。今回の参照幅は女性話者の残差から算出した。男性学習話者を含めた上流の参照幅に対する感度は未確認。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。24点の差は0で、別ディレクトリから各4判定と上流6試験を通過し、5出力がバイト一致した。第7段階第55版は117実行・356判定、全体監査は99実行・214判定に通過した。4実行の1,563入力・24出力をSHA-256で照合し、成果40,527バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-f2-reference-centre-width-20261123-repeat/manifest.json)・[第55版の監査](runs/stage7-evidence-update-20261123-f2-reference-centre-width/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-reference-centre-width/manifest.json)
- 次に開くファイルと実行するコマンド。[音素対応の計測](tools/measure_tsp_again_f2_term_effect.py)と[10名の再計算](tools/measure_tsp_f2_training_reference_ten_speakers.py)、固定上流の `compare/tsp.rs` の `reference` を開く。研究ワークスペースで `jq '.cohorts.ten_speakers' runs/tsp-f2-reference-centre-width-20261123-repeat/artifacts/inputs.json` を実行する。上流の注釈で `EH1` が存在する男性学習話者はMA、MB、MC、MD、MF、MG、MH、MI、MJの9名。各話者で先頭6録音を選ぶ手順と、女性10名・FK・同じ1介入を固定する対照を事前登録する。

## 男女19名の残差をまとめたF2参照を照合する（2026-11-23）

- 完了した項目。男性9名の54録音から有効F2を69件追加し、女性10名とFKを固定した。男性4名では中心の下限に届かず、残差数は女性のみと同じ10。男性9名では19件が入り、女性FDの1介入後の幅は男女で0.10677、女性のみで0.07000オクターブだった。FK録音側の診断費用の増分は0.63034から0.16354へ減った。[事前登録](cases/tsp-f2-reference-pooled-sexes.json)・[読解と実測](notes/tsp-f2-reference-pooled-sexes.md)
- 未達の条件。確認したのは男女の学習19名から各6録音を選び、女性側の1位置だけを替えた場合の挙動。39位置全体で同じ感度になるかは未検証。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。追加の録音F2はWAVからの独立計算と最大2.19e-10 Hz差。参照の数値308点と欠測状態は上流と独立計算で一致した。別ディレクトリの再実行は各4判定、上流6試験に通過し、8出力がバイト一致した。女性10名の回帰の上流数値と要約も一致した。第7段階第56版は118実行・360判定、全体監査は99実行・214判定に通過。5実行の1,609入力・42出力をSHA-256で照合し、成果849,545バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-f2-reference-pooled-sexes-20261123-repeat/manifest.json)・[第56版の監査](runs/stage7-evidence-update-20261123-f2-reference-pooled-sexes/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-reference-pooled-sexes/manifest.json)
- 次に開くファイルと実行するコマンド。[プール参照の独立集計](tools/measure_tsp_f2_reference_pooled_sexes.py)と[元の感度計測](cases/tsp-f2-training-reference-sensitivity.json)を開く。研究ワークスペースで `jq '.held_cost_change' runs/tsp-f2-reference-pooled-sexes-20261123-repeat/summary.json` と `jq '.training | keys' runs/tsp-f2-training-reference-sensitivity-20261123-repeat/artifacts/inputs.json` を実行する。第54版と同じ39位置と2値、同じFK、同じ男女19名を使い、女性のみとの組比較を事前登録する。

## 男女をまとめたF2参照を39位置で比較する（2026-11-23）

- 完了した項目。女性のみと男女19名で、第54版と同じ39位置・2値を1件ずつ差し替えた。録音側の最大変動は0.63034から0.40198へ減り、増加4・減少32・同値42条件だった。男女参照の費用はFK合成の全78条件で0だった。女性中心と女性内MADは両参照で一致した。[事前登録](cases/tsp-f2-pooled-reference-sweep.json)・[読解と実測](notes/tsp-f2-pooled-reference-sweep.md)
- 未達の条件。確認用は女性FKの1話者で、別の確認話者に同じ傾向が出るかは未検証。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。第54版の女性のみ78条件と第56版の男女の1条件を再現した。156条件が固定上流と独立計算で一致し、別ディレクトリで各4判定・上流6試験に通過した。入力、上流出力、要約、パッチの4出力がバイト一致した。第7段階第57版は119実行・363判定、全体監査は99実行・214判定に通過。4実行の1,583入力・24出力をSHA-256で照合し、成果970,487バイトをRTL9210B-CGに保存した。[再実行](runs/tsp-f2-pooled-reference-sweep-20261123-repeat/manifest.json)・[第57版の監査](runs/stage7-evidence-update-20261123-f2-pooled-reference-sweep/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-pooled-reference-sweep/manifest.json)
- 次に開くファイルと実行するコマンド。[録音の計測入口](tools/measure_tsp_again_f2_term_effect.py)と[今回の独立集計](tools/measure_tsp_f2_pooled_reference_sweep.py)を開く。研究ワークスペースで `jq '.statistics.zero_cost_conditions' runs/tsp-f2-pooled-reference-sweep-20261123-repeat/summary.json` を実行する。女性確認話者FLのEH1付き録音の辞書順先頭6件はFL67_03、FL67_04、FL68_03、FL68_04、FL68_07、FL69_01。同じ参照と介入で、FKとFLの費用0の件数を比較する条件を事前登録する。

## 確認話者FLでF2診断のゼロ費用を照合する（2026-11-23）

- 完了した項目。FLの6録音と対応する合成から、強勢付き /ɛ/ のF2を各10件測った。中央値の差は86.33 Hz。FL合成側の費用は女性参照・男女参照とも全78条件で0だった。正の費用が出るという事前予測は外れた。FL録音では男女の参照で8条件が費用0となり、最大変動は0.54524から0.10408に減った。 [事前登録](cases/tsp-f2-pooled-reference-held-fl.json)・[読解と実測](notes/tsp-f2-pooled-reference-held-fl.md)
- 未達の条件。FKとFLの値は各文集合について照合した。通常の上流報告で両方の合成値を集約した費用は未照合。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。FL録音のF2は元WAVからの独立計算と最大2.02e-11 Hz差。基準と78条件で学習参照を再現し、診断費用316点で固定上流と独立計算が一致した。別ディレクトリで各4判定・上流6試験を通過し、8出力がバイト一致。学習側女性10名の回帰も数値が一致した。第7段階第58版は120実行・367判定、全体監査は99実行・214判定に通過。5実行の1,619入力・42出力をSHA-256で照合し、成果1,278,887バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-f2-pooled-reference-held-fl-20261123-repeat/manifest.json)・[第58版の監査](runs/stage7-evidence-update-20261123-f2-pooled-reference-held-fl/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-pooled-reference-held-fl/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の `over_sets` と `score`](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs) と [FL比較の独立計算](tools/measure_tsp_f2_pooled_reference_held_fl.py) を開く。研究ワークスペースで `jq '.common.held_synth | length' runs/tsp-f2-pooled-reference-sweep-20261123-repeat/artifacts/inputs.json runs/tsp-f2-pooled-reference-held-fl-20261123-repeat/artifacts/inputs.json` を実行する。支持数5と10のFK・FLの文集合を固定し、上流の文集合ごとの中央値の集約が同じ78条件の費用0に与える影響を事前登録する。

## 確認女性の合成F2を文集合ごとに集約する（2026-11-23）

- 完了した項目。FKの5件とFLの10件を上流の `over_sets` で集約すると2,051.83 Hz相当、15件の直接集約では2,045.90 Hzだった。女性参照の費用0は上流方式で73条件、直接集約で78条件。男女参照では両方式とも78条件だった。両集合を2件にした対照は支持数4で欠測を再現した。 [事前登録](cases/tsp-f2-held-synth-over-sets.json)・[読解と実測](notes/tsp-f2-held-synth-over-sets.md)
- 未達の条件。確認用FK・FLの部分文集合からの集約を照合した。両話者の全発話については未照合。実録音F2の人手注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。固定上流と独立計算は費用632点で、474点の有限値と158点の欠測が一致した。別ディレクトリで各4判定・上流6試験が通過し、5出力がバイト一致した。第7段階第59版は121実行・370判定、全体監査は99実行・214判定に通過。4実行の1,593入力・24出力をSHA-256で照合し、成果136,044バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-f2-held-synth-over-sets-20261123-repeat/manifest.json)・[第59版の監査](runs/stage7-evidence-update-20261123-f2-held-synth-over-sets/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-held-synth-over-sets/manifest.json)
- 次に開くファイルと実行するコマンド。[録音の抽出と整列](tools/measure_tsp_again_f2_term_effect.py) と [文集合の集約](tools/measure_tsp_f2_held_synth_over_sets.py) を開く。研究ワークスペースで `jq '.held|map_values(length)' runs/tsp-f2-held-synth-over-sets-20261123-repeat/artifacts/inputs.json` を実行する。上流注釈のFK・FLは各60録音。全発話の選択と保存済みの2参照・78介入を事前登録し、部分文集合での合成F2と費用の分布を照合する。

## 確認女性FK・FLの全120発話を照合する（2026-11-23）

- 完了した項目。各60発話を整列し、録音・合成ともFK34件、FL36件の有効F2を得た。元の12発話の音素対応、秒区間、F2は一致した。合成の上流集約値は2,051.83から2,048.24 Hz相当に下がり、女性参照で正だった5条件も0になった。最も近い費用0の上端までの余裕は0.140 Hz。 [事前登録](cases/tsp-f2-full-held-women.json)・[読解と実測](notes/tsp-f2-full-held-women.md)
- 未達の条件。確認用120発話の固定上流での集約を照合した。研究版による全120発話の合成と同じ幅での診断は未照合。人手F2注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。録音70件の独立計算との差は最大1.52e-10 Hzで、欠測状態も一致した。費用632点で固定上流と独立計算が一致。別ディレクトリで各4判定・上流6試験を通過し、9出力がバイト一致した。第7段階第60版は122実行・374判定、全体監査は99実行・214判定に通過。4実行の1,627入力・32出力をSHA-256で照合し、成果1,406,827バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-f2-full-held-women-20261123-repeat/manifest.json)・[第60版の監査](runs/stage7-evidence-update-20261123-f2-full-held-women/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-full-held-women/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の発話入口](tools/measure_tsp_held_out_matched_speech.py) と [共通MFA比較](tools/measure_tsp_matched_speech_mfa.py) を開く。研究ワークスペースで `jq '.references["FA/FA01_03/13/before"].female' runs/tsp-f2-full-held-women-20261123-repeat/artifacts/inputs.json` を実行する。同じ120発話と学習参照を事前登録し、研究版の発話、音素対応、F2集約、費用の順に差を照合する。

## 研究版の確認女性120発話を固定上流と照合する（2026-11-23）

- 完了した項目。通常CLIで120発話を描画し、計画・音素境界は全発話で一致した。PCMの最初の差は17発話でフレーム1989、最大差は `FK65_05` で1.49e-8。強勢付き /ɛ/ の合成F2はFK34件・FL36件すべて一致し、2,048.24 Hz相当と全78条件の費用0を再現した。PCM差が許容差を超える、整列または対象F2に差が出る、費用判定が変わるという3予測は外れた。 [事前登録](cases/tsp-f2-full-held-candidate.json)・[読解と実測](notes/tsp-f2-full-held-candidate.md)
- 未達の条件。PCMの最初の差を出力標本で特定した。どの内部演算で初めて差が生じるかは未特定。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。研究版WAVの独立LPCとの差は最大3.77e-11 Hzで、採択状態も一致。既存の6発話のPCMから最初の差と最大値を再計算し一致した。別ディレクトリで各3判定・上流6試験を通過し、12出力がバイト一致。第7段階第61版は123実行・378判定、全体監査は99実行・214判定に通過。4実行の1,879入力・40出力をSHA-256で照合し、成果3,221,737バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-f2-full-held-candidate-20261123-repeat/manifest.json)・[第61版の監査](runs/stage7-evidence-update-20261123-f2-full-held-candidate/manifest.json)・[全体監査](runs/plan-completion-release-v6-f2-full-held-candidate/manifest.json)
- 次に開くファイルと実行するコマンド。[既存の内部観測の準備](tools/measure_tsp_held_out_matched_speech.py) と [研究版の細粒度観測](tools/candidate_tsp_fine_probe.rs) を開く。研究ワークスペースで `jq '.stages.FK61_01' runs/tsp-f2-full-held-candidate-20261123-repeat/summary.json` を実行する。フレーム1989の前後で、放射、間引き、DC除去、float32への変換を順に採って固定上流の差と照合する。

## FK61_01の最初のPCM差を放射までさかのぼる（2026-11-23）

- 完了した項目。口端流量と放射差分は内部標本3968から異なり、間引きとDC除去は出力1984から異なった。float32で初めて差が出た出力1989では二つの値が丸め中点を挟んだ。係数の一致と放射入力交換で、入力側のPCMを2048フレームで再現した。標本3968は128内部標本の制御更新境界で、口端流量と放射差分が両方で初めて非ゼロになった。 [事前登録](cases/tsp-fk61-pcm-first-difference.json)・[読解と実測](notes/tsp-fk61-pcm-first-difference.md)
- 未達の条件。口端流量に最初の差が出る、口腔末端から口端までの演算は未特定。人手F2注釈とTSP・CSDの試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。通常CLI・観測器・保存済みPCMは全発話でビット一致。順序を揃えた独立再計算は各実装の倍精度の値とPCMを再現した。別ディレクトリで各4判定に通過し、4出力がバイト一致した。第7段階第62版は124実行・381判定、全体監査は99実行・214判定に通過。4実行の1,860入力・22出力をSHA-256で照合し、成果326,153バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-pcm-first-difference-20261123-repeat/manifest.json)・[第62版の監査](runs/stage7-evidence-update-20261123-fk61-pcm-first-difference/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-pcm-first-difference/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版で口端流量を読む箇所](crates/vocal-core/src/voice.rs) と [上流の気道ネットワーク](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs) を開く。研究ワークスペースで `jq '.source_differences.lip_cm3_s' runs/tsp-fk61-pcm-first-difference-20261123-repeat/summary.json` を実行する。内部標本3967〜3970を固定し、制御境界の口端の断面、枝流量、圧力と慣性・抵抗の更新を比較する。

## FK61_01の口端流量差を体積差分までさかのぼる（2026-11-23）

- 完了した項目。内部標本3952〜3979で口端セルの幾何、平滑化、放射負荷を照合した。標本3968の倍精度の体積差分は1.11×10⁻¹⁶ cm³異なった。平滑化後の流量を交換すると相手側の口端流量を両方向とも1 ULPまで再現した。観測した面積と長さから中間の積を丸めずに計算すると、生の流量差は−4.29×10⁻¹⁹ cm³/sだった。 [事前登録](cases/tsp-fk61-lip-onset.json)・[読解と実測](notes/tsp-fk61-lip-onset.md)・[次の実験候補](findings.md)
- 未達の条件。口端セルの断面の微差が調音・幾何計算のどこで発生したかは未特定。体積差分の改善式は未比較。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。各実装の通常CLI・観測器・保存済みPCMは全116,132フレームでビット一致。研究ワークスペースと別ディレクトリで各5判定、上流9試験、研究版1試験に通過し、5出力がバイト一致した。第7段階第63版は125実行・385判定、全体監査は99実行・214判定に通過。5実行の2,040入力と33出力をSHA-256で照合し、成果87,581バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-lip-onset-20261123-repeat/manifest.json)・[第63版の監査](runs/stage7-evidence-update-20261123-fk61-lip-onset/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-lip-onset/manifest.json)
- 次に開くファイルと実行するコマンド。[体積を更新する処理](crates/vocal-core/src/airway/network/geometry.rs#L130)と[丸めの独立計算](tools/measure_tsp_fk61_lip_onset.py)を開く。研究ワークスペースで `jq '{event,volume_rounding}' runs/tsp-fk61-lip-onset-20261123-repeat/summary.json` を実行する。同じ断面と長さで変化分から体積差を求める式を事前登録し、誤差と口端流量を比較する。

## FK61_01の口端で体積差分の求め方を比較する（2026-11-23）

- 完了した項目。口端1節点だけの差分式をRustの試験ビルドで比較した。内部3968の体積流量の絶対誤差が9.40×10⁻¹²から7.02×10⁻²⁰ cm³/sに減り、放射差分の固定上流との差も縮んだ。PCMの最初の差は予測に反して1989から1987へ早まった。1987の変換直前値は隣接float32値の中点を挟んだ。標準版と試験版の全発話で異なるPCMは9フレーム、最大差は1.46×10⁻¹¹だった。 [事前登録](cases/tsp-fk61-lip-volume-increment.json)・[読解と実測](notes/tsp-fk61-lip-volume-increment.md)
- 未達の条件。初期の口端断面差の発生箇所は未特定。この比較は1発話と口端1節点に限る。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。初回はRustの試験用ケース2件が不足し、次の2実行は要約のNumPy真偽値で停止した。修正後、別ディレクトリから各5判定とRustの2試験に通過し、4出力がバイト一致した。失敗時に保存したPCMと観測列も同じだった。第7段階第64版は126実行・389判定、全体監査は99実行・214判定に通過。7実行の2,344入力と40出力をSHA-256で照合し、成果2,062,517バイトをRTL9210B-CGに保存した。 [初回](runs/tsp-fk61-lip-volume-increment-20261123/manifest.json)・[再実行](runs/tsp-fk61-lip-volume-increment-20261123-recheck/manifest.json)・[第64版の監査](runs/stage7-evidence-update-20261123-fk61-lip-volume-increment/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-lip-volume-increment/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の断面制御](crates/vocal-core/src/airway/tract_control.rs#L180)と[上流の断面更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L230)を開く。研究ワークスペースで `jq '.event | map_values({old_area,area_cm2,old_length,length_cm,area_increment})' runs/tsp-fk61-lip-onset-20261123-repeat/summary.json` を実行する。標準版を使い、発話前と3968の口端セルの面積について、測定線、再標本化、開口制限、ネットワークに登録された値の順に比較する。

## FK61_01の口端セルの面積差を測定線まで追う（2026-11-23）

- 完了した項目。発話前の口端断面積の差4.44×10⁻¹⁶ cm²は、軸上位置が一致した測定線45・46の面積差に由来した。45の中央x座標と46の接触補正後の隙間を個別に交換し、それぞれ相手側の面積を再現した。標本3968では面積目標と速度制限結果が一致し、補間中は初期値の差を引き継いだ。口端セルの調和平均と標本3968・3969の補間を独立に照合した。 [事前登録](cases/tsp-fk61-lip-area-origin.json)・[読解と実測](notes/tsp-fk61-lip-area-origin.md)
- 未達の条件。発話前の測定線45のx座標と46の接触補正後の隙間が、輪郭と接触上限のどの演算で分かれたかは未特定。今回の比較は女性1発話の口端5時点。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。各側の通常CLI・観測器・保存済みPCMは全116,132フレームでビット一致。研究ワークスペースと別ディレクトリで各4判定、固定上流の幾何試験、研究版の補間試験に通過し、5出力がバイト一致した。第7段階第65版は127実行・393判定、全体監査は99実行・214判定に通過。6実行の2,207入力・44出力をSHA-256で照合し、成果431,111バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-lip-area-origin-20261123-ray-repeat/manifest.json)・[第65版の監査](runs/stage7-evidence-update-20261123-fk61-lip-area-origin/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-lip-area-origin/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の唇接触](crates/vocal-core/src/anatomy/contact.rs#L60)と[上流の唇接触](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1165)を開く。研究ワークスペースで `jq '.initial_ray_diagnostics' runs/tsp-fk61-lip-area-origin-20261123-ray-repeat/summary.json` を実行する。描画前の姿勢を固定し、両唇端の座標、45・46の中央x座標、接触上限と光線の隙間の最小を比較する。

## FK61_01の唇前端の体型変換を照合する（2026-11-23）

- 完了した項目。描画前のテンプレートxの8.21 cmは一致し、独立計算では体型変換のスケール前に7.1306と7.130600000000001 cmへ分かれた。唇前端1箇所だけ固定上流の式を使う試験版で、測定線45・46と口端セルが固定上流に一致した。最初のPCM差は予測に反して1989から1987に早まり、最大差は1.86265×10⁻⁹だった。 [事前登録](cases/tsp-fk61-lip-front-origin.json)・[読解と実測](notes/tsp-fk61-lip-front-origin.md)
- 未達の条件。フレーム1985の口端セルの長さ目標に2.22×10⁻¹⁶ cmの差が残った。累積軸上位置は測定線31で最初に異なる。これが局所の中央座標、距離の計算、累積時の丸めのどこに由来するかは未特定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。全116,132フレームで各条件の通常CLIと観測器が一致し、標準版はアーカイブにも一致した。別ディレクトリで各3判定とRustの2試験に通過し、6出力がバイト一致した。第7段階第66版は128実行・396判定、全体監査は99実行・214判定に通過。4実行の1,921入力・30出力をSHA-256で照合し、成果1,009,806バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-lip-front-origin-20261123-repeat/manifest.json)・[第66版の監査](runs/stage7-evidence-update-20261123-fk61-lip-front-origin/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-lip-front-origin/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の中心線距離](crates/vocal-core/src/anatomy/area.rs#L89)と[上流の累積処理](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1225)を開く。研究ワークスペースで `jq -s '[.[] | select(.completed_frames == 1985) | .tract.grid[30:33]]' runs/tsp-fk61-lip-front-origin-20261123-repeat/artifacts/{upstream,trial}.jsonl` を実行する。フレーム1985の測定線31の前後で、中央座標の差と距離・累積の丸めを照合する。

## FK61_01の中心線距離と口端セル長を照合する（2026-11-23）

- 完了した項目。測定線31のy座標の差で30→31の距離が異なり、累積時の和が隣接する倍精度値の中点を挟んだ。試験版で距離計算に渡す31のyだけを交換すると累積位置の初差は34に移り、口端セル長の目標差は2.22×10⁻¹⁶から1.11×10⁻¹⁶ cmに減った。補間の独立計算では3条件の現在長が128標本で一致し、最初の2標本の実測とも一致した。 [事前登録](cases/tsp-fk61-centerline-length-origin.json)・[読解と実測](notes/tsp-fk61-centerline-length-origin.md)
- 未達の条件。測定線31のyが光線と輪郭のどの演算で分かれるかは未特定。今回のyの交換では標準版と試験版のPCMが一致した。唇前端の面積を揃えた試験版には冒頭PCM差が残っている。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。通常CLIと観測器、標準版と試験版の各116,132 PCMフレームはビット一致。別ディレクトリで各3判定・Rustの2試験が通過し、6出力がバイト一致した。第7段階第67版は129実行・400判定、全体監査は99実行・214判定に通過した。4実行の1,928入力と30出力をSHA-256で照合し、成果968,318バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-centerline-length-origin-20261123-repeat/manifest.json)・[第67版の監査](runs/stage7-evidence-update-20261123-fk61-centerline-length-origin/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-centerline-length-origin/manifest.json)
- 次に開くファイルと実行するコマンド。[唇前端の試験版](tools/tsp_fk61_lip_front_observation.py)と[口端流量の観測](tools/measure_tsp_fk61_lip_onset.py)を開く。研究ワークスペースで `jq '.pcm' runs/tsp-fk61-lip-front-origin-20261123-repeat/summary.json` を実行する。唇前端の演算順序を揃えた条件で、内部標本3968の体積流量、枝と壁の流量、放射の最初の差を照合する。

## FK61_01の唇前端を揃えた後の放射差を照合する（2026-11-23）

- 完了した項目。試験版は内部3968で固定上流と口端流量・総放射流量が一致した。乗算と除算の時間換算で放射差分が1 ULPずれた。時間換算の交換で出力1987のPCM差は残った。口端放射の交換と、事後に試した内部3972の口端流量1標本の交換は、どちらも独立計算で出力1987までのPCMを固定上流に揃えた。 [事前登録](cases/tsp-fk61-lip-front-radiation.json)・[読解と実測](notes/tsp-fk61-lip-front-radiation.md)
- 未達の条件。口端節点43の手前にある節点42では、3968の新圧力と3969の体積注入に差が出た。42–43の枝を通じて3972の口端流量に伝わる経路は未分離。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。各条件の通常CLI・観測器・保存済みPCMは全116,132フレームで一致。別ディレクトリで各5判定・Rustの11試験に通過し、10出力がバイト一致した。第7段階第68版は130実行・404判定、全体監査は99実行・214判定に通過。4実行の1,958入力・40出力をSHA-256で照合し、成果2,640,591バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-lip-front-radiation-20261123-repeat/manifest.json)・[第68版の監査](runs/stage7-evidence-update-20261123-fk61-lip-front-radiation/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-lip-front-radiation/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の枝の更新](crates/vocal-core/src/airway/network.rs#L723)と[上流の枝の更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L922)を開く。研究ワークスペースで `awk -F, '$1>=3968 && $1<=3972 && ($2==42 || $2==43)' runs/tsp-fk61-lip-front-radiation-20261123-repeat/artifacts/{upstream,trial}-nodes.csv` を実行する。節点42・43の圧力、体積流量、枝流量を時刻に揃え、42–43の枝の圧差と状態を別々に比較する。

## FK61_01の節点42から口端への流量差を照合する（2026-11-23）

- 完了した項目。内部3968の節点42の圧力差はコンプライアンスの交換で再現した。3969の枝42→43では左圧力と枝係数の同時交換で流量が揃った。二節点を8標本連続で再計算し、圧力・枝・壁・口端流量を観測に照合した。追加の対照で節点42の体積注入を8標本分交換し、口端の放射成分の変化で1987までのPCMが上流に一致した。 [読解と実測](notes/tsp-fk61-lip-front-terminal-branch.md)・[比較条件](cases/tsp-fk61-lip-front-terminal-branch.json)
- 未達の条件。節点42の3969の注入差について、体積差の丸めと狭窄セルからの配分の寄与を分ける。体積注入の交換による全発話のPCMは未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。通常CLI・観測器・保存済みPCMは条件ごとに全116,132フレームで一致。修正後は別ディレクトリの両実行で各5判定・Rustの11試験に通過し、18出力がバイト一致した。第7段階第69版は131実行・408判定、全体監査は99実行・214判定に通過。4実行の1,998入力・56出力をSHA-256で照合し、成果2,744,058バイトをRTL9210B-CGに保存した。初回の配列比較の失敗も保持した。 [初回の失敗](runs/tsp-fk61-terminal-branch-20261123-check/manifest.json)・[再実行](runs/tsp-fk61-terminal-branch-20261123-repeat/manifest.json)・[第69版の監査](runs/stage7-evidence-update-20261123-fk61-terminal-branch/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-terminal-branch/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の体積注入](crates/vocal-core/src/airway/network/geometry.rs#L110)と[上流の体積注入](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)を開く。研究ワークスペースで `awk -F, '$1>=3968 && $1<=3969 && $2>=41 && $2<=43 {print $1,$2,$5,$6,$8,$10,$11,$12}' runs/tsp-fk61-terminal-branch-20261123-repeat/artifacts/{upstream,trial}-nodes.csv` を実行する。新旧体積から求めた流量と配分後の値を照合し、平滑前の最初の差を特定する。

## FK61_01の節点42で体積速度の初差を照合する（2026-11-23）

- 完了した項目。内部3969で、丸めた面積・長さの積の差が体積速度に伝わった。時間換算順を揃えても差が残り、近隣への配分は0件だった。積の途中の丸めを省いた独立計算で、体積速度の版間差は1.07×10⁻¹¹から1.73×10⁻¹⁸ cm³/sに縮んだ。平滑前の3969の1標本だけを交換して2段の平滑と口端負荷を再計算すると、出力1987までのPCMが上流に一致した。 [比較条件](cases/tsp-fk61-node42-volume-source.json)・[読解と実測](notes/tsp-fk61-node42-volume-source.md)
- 未達の条件。節点42で補間開始時点の断面積差に寄与する測定線と、セルへ面積を集約する過程を特定する。体積速度の演算を変える比較は局所で実施し、全発話のPCMへの効果は未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。通常CLI・観測器・保存済みPCMは条件ごとに全116,132フレームで一致。別ディレクトリの両実行で各5判定・Rustの11試験に通過し、実行ログを除く21出力がバイト一致した。第7段階第70版は132実行・411判定、全体監査は99実行・214判定に通過。4実行の2,041入力・62出力をSHA-256で照合し、成果4,826,072バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-node42-volume-source-20261123-repeat/manifest.json)・[第70版の監査](runs/stage7-evidence-update-20261123-fk61-node42-volume-source/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-node42-volume-source/manifest.json)
- 次に開くファイルと実行するコマンド。[口端セルの測定線と集約](notes/tsp-fk61-lip-area-origin.md)と[既存スナップショット](tools/tsp_fk61_lip_area_snapshot.rs#L46)を開く。研究ワークスペースで `awk -F, '$1>=3968 && $1<=3969 && $2==42 {print $1,$2,$5,$6,$7,$9,$10,$11,$12}' runs/tsp-fk61-node42-volume-source-20261123-repeat/artifacts/{upstream,trial}-geometry.csv` を実行する。口端の一つ手前のセルについて、更新前の断面積と面積の補間先を分けて照合する。

## FK61_01の節点42の測定線と補間を照合する（2026-11-23）

- 完了した項目。節点42の平均断面積に測定線42〜45が寄与した。描画前は測定線43の面積だけを交換すると節点42の値が上流に一致した。1985フレームの目標面積は、セル境界、測定線位置、測定線面積を揃えると一致した。補間開始時の面積だけを上流に揃えた局所再計算は、内部3969の体積速度を再現した。 [比較条件](cases/tsp-fk61-node42-area-origin.json)・[読解と実測](notes/tsp-fk61-node42-area-origin.md)
- 未達の条件。測定線43の下側交点のy座標に1 ULPの差がある。輪郭線分の端点と光線交差の計算を分け、差が出る最初の演算を特定する。今回の面積交換は局所再計算で、全発話のPCMは未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。通常CLI、観測器、保存済みPCMは条件ごとに全116,132フレームでビット一致。別ディレクトリの両実行で各5判定・Rustの2試験に通過し、観測と要約を含む6出力がバイト一致した。第7段階第71版は133実行・414判定、全体監査は99実行・214判定に通過。4実行の2,023入力・30出力をSHA-256で照合し、成果1,134,806バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-node42-area-origin-20261123-repeat/manifest.json)・[第71版の監査](runs/stage7-evidence-update-20261123-fk61-node42-area-origin/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-node42-area-origin/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の測定線の構築](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1027)と[研究版の測定線と交差](crates/vocal-core/src/anatomy/grid.rs#L95)を開く。研究ワークスペースで `jq -c 'select(.completed_frames==0) | .tract.grid[43]' runs/tsp-fk61-node42-area-origin-20261123-repeat/artifacts/{upstream,trial}.jsonl` を実行する。測定線43が当たった下側輪郭線分を同定し、線分の端点、交差距離、交点座標の順に照合する。

## FK61_01の測定線43と下唇の3次ベジェ曲線を照合する（2026-11-23）

- 完了した項目。測定線43の光線は各版で一致し、下側には下唇内面の標本1→2の線分を採った。始点のみの交換で下側の交差、隙間、節点42の断面積が上流に一致した。採取後の独立計算では、同じ4制御点についてBernstein基底による重み付き和とde Casteljau法が両版の端点を再現した。 [ケース定義](cases/tsp-fk61-ray43-intersection.json)・[読解と実測](notes/tsp-fk61-ray43-intersection.md)
- 未達の条件。下唇内面の評価順だけを変更した全発話の描画、内部3969の体積速度、PCMへの影響は未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。全116,132フレームの通常CLI・観測器・保存済みPCMが条件ごとにビット一致。別ディレクトリの両実行で各5判定・Rustの2試験に通過し、6出力がバイト一致した。第7段階第72版は134実行・418判定、全体監査は99実行・214判定に通過。4実行の2,025入力・30出力をSHA-256で照合し、成果1,260,094バイトをRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-ray43-intersection-20261123-repeat/manifest.json)・[第72版の監査](runs/stage7-evidence-update-20261123-fk61-ray43-intersection/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-ray43-intersection/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の3次ベジェ曲線](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L159)と[研究版の下唇内面](crates/vocal-core/src/anatomy.rs#L529)を開く。研究ワークスペースで `jq '.coverage.f2_followup.synthetic_controls.fk61_ray43_intersection.exploratory_lower_lip_curves.trial' runs/stage7-evidence-update-20261123-fk61-ray43-intersection/summary.json` を実行する。唇前端の体型変換を上流に揃えた条件に、下唇内面の7標本の評価だけを上流式に切り替えた一時ビルドを加え、初期形状、3969の体積速度、全発話PCMを比べる。

## 下唇内面の評価順を変えてFK61_01の全発話を照合する（2026-11-23）

- 完了した項目。下唇内面の7点にBernstein基底を使った一時ビルドを通常CLIから実行した。測定線43と節点42の描画前の形状、内部3969の体積速度・平滑後の注入が上流に一致した。PCMの初差が1987から2937へ遅れ、全発話の最大絶対差は1.86×10⁻⁹で揃った。相違フレーム数は2309から2355に増えた。 [ケース定義](cases/tsp-fk61-lower-lip-bernstein-render.json)・[読解と実測](notes/tsp-fk61-lower-lip-bernstein-render.md)
- 未達の条件。2937の固定上流の放射入力と倍精度出力を採って、先頭3072フレームで差が生じた段階を照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。通常CLIと観測器は全116,132フレームでビット一致。別ディレクトリの両実行で各4判定・Rustの6試験に通過し、11出力がバイト一致した。第7段階第73版は135実行・423判定、全体監査は99実行・214判定に通過した。4実行の2,070入力・40出力をSHA-256で照合し、成果2,932,298バイトをRTL9210B-CGに保存した。準備と集計の失敗も記録した。 [再実行](runs/tsp-fk61-lower-lip-bernstein-render-20261123-full-repeat/manifest.json)・[第73版の監査](runs/stage7-evidence-update-20261123-fk61-lower-lip-bernstein-render/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-lower-lip-bernstein-render/manifest.json)
- 次に開くファイルと実行するコマンド。[既存の上流出力段の取得](tools/measure_tsp_fk61_pcm_first_difference.py#L147)と[独立した出力段](tools/measure_tsp_fk61_pcm_first_difference.py#L29)を開く。研究ワークスペースで `jq '{first_pcm_output_stage,radiation_prefix}' runs/tsp-fk61-lower-lip-bernstein-render-20261123-full-repeat/summary.json` を実行する。固定上流の観測長を3072に揃え、2937の前後の放射、間引き、DC除去とPCMの中点を照合する。

## FK61_01のPCM2937で生じる丸めを放射入力まで照合する（2026-11-23）

- 完了した項目。上流と試験版の放射および倍精度出力段を3072フレームまで独立再計算した。2937のPCMは隣接float32値に分かれた。直前のDC出力を交換すると2937の値が上流に一致し、口端放射流量の交換で先頭から2937までが上流に一致した。時間差分の順序と現在の内部2標本の交換では2937の差が残った。 [比較条件](cases/tsp-fk61-pcm2937-output.json)・[読解と実測](notes/tsp-fk61-pcm2937-output.md)
- 未達の条件。口端放射流量を、現在のFIRへの寄与が最大だった内部5851付近とそれ以前の履歴に分け、2937の丸めに効いた入力範囲と流量差の発生箇所を絞る。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。固定上流の全116,132フレームで、通常CLI・観測器・保存済みPCMが一致。別ディレクトリの両実行で各4判定・Rustの1試験に通過し、4出力がバイト一致した。第7段階第74版は136実行・426判定、全体監査は99実行・214判定に通過した。4実行の1,820入力・24出力をSHA-256で照合し、成果515,606バイトをRTL9210B-CGに保存した。初回の集計停止と採取データの再解析も記録した。 [再実行](runs/tsp-fk61-pcm2937-output-20261123-verified-repeat/manifest.json)・[第74版の監査](runs/stage7-evidence-update-20261123-fk61-pcm2937-output/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-pcm2937-output/manifest.json)
- 次に開くファイルと実行するコマンド。[時刻別の放射入力の交換](tools/measure_tsp_fk61_pcm2937_output.py#L84)と[口端負荷の更新](crates/vocal-core/src/airway.rs#L89)を開く。研究ワークスペースで `jq '{rounding,largest_fir:.radiation_window_swaps.largest_exact_fir_term,lip_only:(.radiation_component_swaps[] | select(.components==["lip_cm3_s"] and .derivative_order=="bernstein"))}' runs/tsp-fk61-pcm2937-output-20261123-verified-repeat/summary.json` を実行する。保存した口端放射系列で5851付近の寄与を時刻別に照合し、対象標本の終端流入とR–L負荷を採る範囲を決める。

## FK61_01のPCM2937に効く口端放射の時間範囲を照合する（2026-11-23）

- 完了した項目。内部5800〜5875内の全2,926連続区間で口端流量を交換した。2937で一致した1,044区間のうち、冒頭から2937までが一致したのは73区間。後者の最短は5863・5864の2標本だった。単一標本の線形寄与が最大だった5849の交換では、冒頭からのPCMに2933で差が出た。 [ケース定義](cases/tsp-fk61-pcm2937-lip-window.json)・[読解と実測](notes/tsp-fk61-pcm2937-lip-window.md)
- 未達の条件。5863〜5865の口端へ入る流量、旧圧力、放射負荷の状態を採り、口端の流量差が生じる経路を照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。通常CLIと観測器が一致した保存済み系列から両版の出力段を再現した。別ディレクトリの両実行で各4判定に通過し、2出力がバイト一致した。第7段階第75版は137実行・430判定、全体監査は99実行・214判定に通過した。4実行の1,807入力・16出力をSHA-256で照合し、成果203,099バイトをRTL9210B-CGに保存した。JSON保存に失敗した4実行の走査配列も一致した。 [再実行](runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/manifest.json)・[第75版の監査](runs/stage7-evidence-update-20261123-fk61-pcm2937-lip-window/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-pcm2937-lip-window/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の終端負荷](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1129)と[研究版の終端更新](crates/vocal-core/src/airway.rs#L89)を開く。研究ワークスペースで `jq '{shortest_intervals, first_and_last:.controls.first_shortest, strongest_linear_term}' runs/tsp-fk61-pcm2937-lip-window-20261123-certified-repeat/summary.json` を実行する。5863〜5865とその手前の口端の終端流入・圧力・放射負荷を採取して、流量差が生じる段階を調べる。

## FK61_01の口端流量を作る正味流入と放射負荷の履歴を照合する（2026-11-23）

- 完了した項目。5863〜5865で、旧慣性流量は4入力群のうち単標本の口端流量に最も大きく効いた。5863では枝42→43が正味流入差の97.4%を占めた。5856から正味流入の系列を上流にし、5863・5864の口端流量を試験版の出力段に戻すと、冒頭からPCM 2937まで一致した。 [ケース定義](cases/tsp-fk61-pcm2937-terminal-load.json)・[読解と実測](notes/tsp-fk61-pcm2937-terminal-load.md)
- 未達の条件。枝42→43の差が、節点42・43の圧力差、枝に残る運動量、幾何係数や損失のどこから来るかを、同じ区間で調べる。2937より後のPCM、実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。`tsp-fk61-pcm2937-terminal-load-20261123-certified` は5判定とRustの11試験に通過した。3版の通常CLI・観測版・既存PCMは各116,132フレームで一致し、口端の逐次計算は各版16内部標本で一致した。比較長と保存列の選択に起因した2回の失敗を保持した。第7段階第76版は138実行・434判定、全体監査は99実行・214判定に通過した。3実行の1,988入力・34出力をSHA-256で照合し、外部出力2,816,954バイトをRTL9210B-CGに保存した。 [計測マニフェスト](runs/tsp-fk61-pcm2937-terminal-load-20261123-certified/manifest.json)・[第76版の監査](runs/stage7-evidence-update-20261123-fk61-pcm2937-terminal-load/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-pcm2937-terminal-load/manifest.json)
- 次に開くファイルと実行するコマンド。[枝・壁・2節点の再計算](tools/measure_tsp_fk61_lip_front_terminal_branch.py#L106)と[上流の枝更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1033)を開く。研究ワークスペースで `jq '{focus: [.focus[] | .inflow_deltas_upstream_minus_trial_cm3_s], history: [.history_exchanges[] | {groups, first_difference_through_focus, precast_shift}]}' runs/tsp-fk61-pcm2937-terminal-load-20261123-certified/summary.json` を実行する。既存の枝・節点の観測系列を入力にし、5856から枝の入力群を個別に交換する。

## FK61_01の枝42→43の流量に残る運動量履歴を照合する（2026-11-23）

- 完了した項目。5863〜5865の枝流量差を、独立した式で最大0.85 ULPの残差で再現した。5863の差 −2.864×10⁻¹¹ cm³/sに対し、運動量履歴の寄与は −2.907×10⁻¹¹ cm³/s。5856の枝の初期状態だけを交換して口端を再計算すると、冒頭からPCM 2937まで一致した。圧力系列の影響の方が大きいという予測は棄却した。 [ケース定義](cases/tsp-fk61-pcm2937-branch-drive.json)・[読解と測定](notes/tsp-fk61-pcm2937-branch-drive.md)
- 未達の条件。5856に持ち越された枝の旧流量・旧慣性のうち、どちらがPCM 2937の差に効いたかを調べる。2937より後のPCM、実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。元の通常CLIの採取を使い、2ディレクトリで各5判定に通過して要約がバイト一致した。第7段階第77版は139実行・438判定、全体監査は99実行・214判定に通過した。4実行の入力1,902件と出力14件をSHA-256で照合した。監査の外部出力24,687バイトはRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-pcm2937-branch-drive-20261123-repeat/manifest.json)・[第77版の監査](runs/stage7-evidence-update-20261123-fk61-pcm2937-branch-drive/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-pcm2937-branch-drive/manifest.json)
- 次に開くファイルと実行するコマンド。[枝の履歴を進める計測器](tools/measure_tsp_fk61_pcm2937_branch_drive.py#L26)と[上流の観測CSV](runs/tsp-fk61-pcm2937-terminal-load-20261123-certified/artifacts/upstream-branch.csv)を開く。研究ワークスペースで `jq '{hypotheses, initial:(.sequence_exchanges[] | select(.groups==["initial_branch"])), focus: [.focus[] | .decomposition.flow_terms_cm3_s]}' runs/tsp-fk61-pcm2937-branch-drive-20261123-repeat/summary.json` を実行する。5840〜5856の開始標本を走査し、旧流量と旧慣性を個別に交換する。旧運動量には組み合わせた値の積を入れる。

## FK61_01の枝42→43の旧流量と旧慣性を開始点ごとに交換する（2026-11-23）

- 完了した項目。5840〜5856の17開始点と4交換条件を比較した。旧流量だけで17条件とも冒頭からPCM 2937まで一致し、旧慣性だけでは17条件とも2937で差が残った。5840で交換した流量の差の約97.87%が5863まで残った。独立した一次近似の残差は全68条件で最大約7.80 ULPだった。 [ケース定義](cases/tsp-fk61-pcm2937-branch-seed.json)・[読解と測定](notes/tsp-fk61-pcm2937-branch-seed.md)
- 未達の条件。今回の採取開始5840より前に、枝42→43の旧流量が分かれた時刻と要因を調べる。2937より後のPCM、実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。元の通常CLIの採取データを使い、2ディレクトリで計測5判定に通過して結果要約がバイト一致した。第7段階第78版は140実行・442判定、全体監査は99実行・214判定に通過した。4実行の1,912入力と14出力をSHA-256で照合し、外部出力24,652バイトはRTL9210B-CGに保存した。 [再実行](runs/tsp-fk61-pcm2937-branch-seed-20261123-repeat/manifest.json)・[第78版の監査](runs/stage7-evidence-update-20261123-fk61-pcm2937-branch-seed/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-pcm2937-branch-seed/manifest.json)
- 次に開くファイルと実行するコマンド。[枝の観測器](tools/tsp_fk61_terminal_branch_observation.py#L34)と[固定上流の枝更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)を開く。研究ワークスペースで `jq '{matching_starts_by_group, maximum_linear_residual_ulps, first_start: [.sweep[] | select(.start_sample==5840)]}' runs/tsp-fk61-pcm2937-branch-seed-20261123-repeat/summary.json` を実行する。次のケースでは3968〜5840を採り、枝が初めて分かれる時刻とその直前の状態を検算する。

## FK61_01の枝41→42と枝42→43の初差を冒頭から観測する（2026-11-23）

- 完了した項目。固定上流と下唇の評価順を揃えた試験版で、枝41→42は3969、枝42→43と口端放射は3971で初めて分かれた。3971で節点42の旧圧だけを上流に交換すると枝42→43が一致した。3970で枝41→42の流量だけを交換すると、その旧圧の元になる節点42の更新後圧力も一致した。 [ケース定義](cases/tsp-fk61-branch-first-difference.json)・[読解と測定](notes/tsp-fk61-branch-first-difference.md)
- 未達の条件。3968の節点41の微小な圧力差を体積差から再現した。3969で節点41に入る流量が分かれた起点を枝40→41へさかのぼる。2937より後のPCM、実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各5判定とRustの11試験に通過し、採取系列17点と要約がバイト一致した。全発話の通常CLI、観測版、保存済みPCMは各版でビット一致した。第7段階第79版は141実行・446判定、全体監査は99実行・214判定に通過した。4実行の2,234入力・56出力をSHA-256で照合し、外部出力52,721,024バイトをRTL9210B-CGに保存した。 [計測の再実行](runs/tsp-fk61-branch-first-difference-20261123-repeat/manifest.json)・[第79版の監査](runs/stage7-evidence-update-20261123-fk61-branch-first-difference/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-branch-first-difference/manifest.json)
- 次に開くファイルと実行するコマンド。[枝の観測器](tools/tsp_fk61_terminal_branch_observation.py#L34)と[上流の枝更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1028)を開く。研究ワークスペースで `jq '{trial:(.chronologies.trial|{mouth,edges:(.edges|map_values(.flow)),cell41:.cells["41"].new_pressure_dyn_cm2}), first_series:.first_branches.series.sample}' runs/tsp-fk61-branch-first-difference-20261123-repeat/summary.json` を実行する。次のケースで3968〜3970の枝40→41と節点40〜42の収支を採る。

## FK61_01の節点40の体積源から節点41までを照合する（2026-11-23）

- 完了した項目。3969の節点41の流入差 +1.6794×10⁻¹⁶ cm³/s の大半は枝40→41から来た。枝の駆動を1標本さかのぼると、3968の節点40で、丸めた体積から計算した体積速度差 +2.1316×10⁻¹¹ cm³/s が二段平滑と圧力更新を経て枝に伝わっていた。面積と長さの積を丸めない独立計算で、体積速度差は +5.1474×10⁻¹⁸ cm³/s になった。 [ケース定義](cases/tsp-fk61-oral-onset-inflow.json)・[読解と測定](notes/tsp-fk61-oral-onset-inflow.md)
- 未達の条件。節点40の3968だけに体積差の展開式を入れた試験ビルドで、口端とPCMに伝わる差を通常版と比較する。2937より後のPCM、実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各5判定とRustの11試験に通過し、採取系列17点と要約がバイト一致した。第7段階第80版は142実行・450判定、全体監査は99実行・214判定に通過した。4実行の2,274入力・56出力をSHA-256で照合し、RTL9210B-CGに外部出力2,033,408バイトを保存した。 [計測の再実行](runs/tsp-fk61-oral-onset-inflow-20261123-repeat/manifest.json)・[第80版の監査](runs/stage7-evidence-update-20261123-fk61-oral-onset-inflow/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-oral-onset-inflow/manifest.json)
- 次に開くファイルと実行するコマンド。[研究版の体積源](crates/vocal-core/src/airway/network/geometry.rs#L110)と[混合体型の展開式パッチ](tools/patches/candidate-expanded-volume-difference.patch#L31)を開く。研究ワークスペースで `jq '{node40_volume_source, node41_input_deltas, hypotheses}' runs/tsp-fk61-oral-onset-inflow-20261123-repeat/summary.json` を実行する。節点40の3968に絞った体積源の展開式を一時ビルドで試し、全発話のPCMと口端の初差を採る。

## FK61_01の節点40の体積差の展開式を全発話で照合する（2026-11-23）

- 完了した項目。節点40の3968だけに展開式を適用した。体積速度の絶対誤差が1.50×10⁻¹¹から4.90×10⁻¹⁹ cm³/sに減り、口端の3971の上流との差は1.2876×10⁻¹⁷から3.7963×10⁻¹⁸ cm³/sに縮んだ。固定上流とのPCM初差は両条件とも2937で、展開式の有無で異なるPCMは全116,132フレーム中7フレーム。 [ケース定義](cases/tsp-fk61-node40-expanded-volume.json)・[読解と測定](notes/tsp-fk61-node40-expanded-volume.md)
- 未達の条件。PCM 2937に効く5863・5864の口端流量差を、節点42の体積源が分かれる制御境界5632以降の圧力・幾何・枝流量から説明する。初差の後も含めた全PCMの差は今回記録した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各5判定および各条件のRust補間試験に通過した。採取・一時パッチの13ファイルと要約がバイト一致した。第7段階第81版は143実行・454判定、全体監査は99実行・214判定に通過した。4実行の2,310入力・46出力をSHA-256で照合し、外部出力9,826,142バイトをRTL9210B-CGに保存した。 [計測の再実行](runs/tsp-fk61-node40-expanded-volume-20261123-repeat/manifest.json)・[第81版の監査](runs/stage7-evidence-update-20261123-fk61-node40-expanded-volume/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-node40-expanded-volume/manifest.json)
- 次に開くファイルと実行するコマンド。[先行の枝と節点の採取](notes/tsp-fk61-branch-first-difference.md)と[節点42の体積源の再計算](tools/measure_tsp_fk61_node42_volume_source.py#L121)を開く。研究ワークスペースで `jq '{node42:.chronologies.trial.cells["42"], mouth_first:.chronologies.trial.mouth}' runs/tsp-fk61-branch-first-difference-20261123-repeat/summary.json` を実行する。5632〜5879の採取済みの枝・節点・放射を照合し、初期の丸め差と後続の幾何補間から入る差を切り分ける。

## FK61_01の制御境界5632以降の口端流量差を切り分ける（2026-11-23）

- 完了した項目。5632の節点42では補間後の長さに1 ULPの差があり、体積速度差の約98.76%を説明した。5632〜5875で4入力群を交換した16条件では、枝41→42だけの交換で5863の口端流量差の約93.7%を再現し、冒頭からPCM 2937まで一致した。局所の244標本で両版の体積源・枝・壁・節点圧・口端負荷を再計算した。 [ケース定義](cases/tsp-fk61-control5632-mouth-flow.json)・[読解と測定](notes/tsp-fk61-control5632-mouth-flow.md)
- 未達の条件。5632の節点42だけを交換しても5863の口端流量は変わらなかった。枝41→42の差が増える5675〜5781で、節点41の体積源・圧力と枝40→41からの流入を採り、支配的な上流入力を特定する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。元の通常CLIの観測を用い、2ディレクトリで各5判定に通過した。結果要約と保存した軌道がバイト一致した。第7段階第82版は144実行・458判定、全体監査は99実行・214判定に通過した。4実行の2,042入力・16出力をSHA-256で照合し、外部出力373,534バイトをRTL9210B-CGに保存した。 [計測の再実行](runs/tsp-fk61-control5632-mouth-flow-20261123-repeat/manifest.json)・[第82版の監査](runs/stage7-evidence-update-20261123-fk61-control5632-mouth-flow/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control5632-mouth-flow/manifest.json)
- 次に開くファイルと実行するコマンド。[境界以降の二節点モデル](tools/measure_tsp_fk61_control5632_mouth_flow.py#L56)と[枝と節点の観測器](tools/tsp_fk61_terminal_branch_observation.py#L34)を開く。研究ワークスペースで `jq '{native_checkpoints, matching_groups}' runs/tsp-fk61-control5632-mouth-flow-20261123-repeat/summary.json` を実行する。節点41の体積源、枝40→41、枝41→42に入る圧力差を5675〜5781の前後で測る。

## FK61_01の枝41→42の流量差を口腔の六節点で照合する（2026-11-23）

- 完了した項目。節点38〜43の連成計算で、5675では節点38〜41の体積源、5863では枝37→38の流量系列の交換が枝41→42を最も大きく動かした。5863の枝41→42の差の約83.6%を枝37→38だけで、約99.8%を局所の体積源と合わせて再現した。PCM 2937まで一致する条件は、2標本を戻した場合に16組、全区間を戻した場合に8組だった。 [ケース定義](cases/tsp-fk61-control5632-upstream-drive.json)・[読解と測定](notes/tsp-fk61-control5632-upstream-drive.md)
- 未達の条件。枝37→38へ伝わった差を、咽頭側から口腔へ入る流量と、口腔上流側の局所体積源に分ける。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各5判定とRustの11試験に通過した。全発話の通常CLIと観測版を照合し、採取系列17点・状態軌道・要約はバイト一致した。第7段階第83版は145実行・462判定、全体監査は99実行・214判定に通過した。4実行の2,368入力・58出力をSHA-256で照合し、外部出力9,751,308バイトをRTL9210B-CGに保存した。 [計測の再実行](runs/tsp-fk61-control5632-upstream-drive-20261123-repeat/manifest.json)・[第83版の監査](runs/stage7-evidence-update-20261123-fk61-control5632-upstream-drive/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control5632-upstream-drive/manifest.json)
- 次に開くファイルと実行するコマンド。[上流の口腔と咽頭の接続](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L150)と[六節点の連成計算](tools/measure_tsp_fk61_control5632_upstream_drive.py#L24)を開く。研究ワークスペースで `jq '{native_checkpoints, matching_groups}' runs/tsp-fk61-control5632-upstream-drive-20261123-repeat/summary.json` を実行する。取得範囲を口腔の咽頭側入口まで広げ、同じ5632〜5875の入出力と体積源を照合する。

## FK61_01の咽頭から口腔への流入と口腔16節点の体積源を分ける（2026-11-23）

- 完了した項目。固定上流・試験版の口腔16節点を連成し、5632〜5875の枝・壁・節点圧・口端負荷を観測と照合した。5863の枝37→38の流量差は、節点28〜37の体積源だけの交換で約81.2%、咽頭流入だけで約17.8%、両方で約99.0%を再現した。口端の全区間を戻した5条件でPCMが冒頭から2937まで一致した。 [ケース定義](cases/tsp-fk61-control5632-oral-inlet.json)・[読解と測定](notes/tsp-fk61-control5632-oral-inlet.md)
- 未達の条件。節点34の体積源の差を断面積と長さの変化に切り分ける。PCMの交換比較は2937まで。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各5判定とRustの11試験に通過した。全発話の通常CLIと観測版を照合し、採取系列17点・状態軌道・要約はバイト一致した。第7段階第84版は146実行・466判定、全体監査は99実行・214判定に通過した。4実行の2,412入力・58出力をSHA-256で照合し、外部出力21,179,874バイトをRTL9210B-CGに保存した。 [計測の再実行](runs/tsp-fk61-control5632-oral-inlet-20261123-repeat/manifest.json)・[第84版の監査](runs/stage7-evidence-update-20261123-fk61-control5632-oral-inlet/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control5632-oral-inlet/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `HumanAirway::commit` と `set_tube_targets`、研究版の `begin_tract_block` と `set_geometry_targets` を開く。研究ワークスペースで `jq '.per_node_volume["34"].checkpoints | with_entries(select(.key=="5632" or .key=="5760" or .key=="5863"))' runs/tsp-fk61-control5632-oral-inlet-20261123-repeat/summary.json` を実行する。5632・5760の制御境界で口腔長の目標・補間開始値・長さ増分を採取し、面積と長さの個別交換を評価する。 [上流の管の目標](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L318)・[上流の補間](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L647)・[研究版の管の目標](crates/vocal-core/src/airway/human.rs#L341)・[研究版の補間](crates/vocal-core/src/airway/network.rs#L420)

## FK61_01の口腔体積源を断面積・長さ・平滑開始値に分ける（2026-11-23）

- 完了した項目。5632・5760の目標と補間を採取し、節点34の体積速度は断面積の交換でより大きく変わると確認した。節点28〜37をまとめた交換では、5863の枝37→38への変化は長さが断面積の約8.6倍。形状と咽頭流入に加えて平滑器の開始値を揃えると冒頭からPCM 2937まで一致した。 [ケース定義](cases/tsp-fk61-control5632-oral-geometry.json)・[読解と測定](notes/tsp-fk61-control5632-oral-geometry.md)
- 未達の条件。5632の平滑器の開始値が異なる過程を一つ前の制御ブロックまでさかのぼる。解剖学的な長さ目標の差を唇側と咽頭端の弧長に分ける。PCMの交換比較の判定範囲は2937まで。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。Rustの観測コードの借用エラーを修正し、2ディレクトリで各4判定とRustの11試験に通過した。計測と監査の4実行で2,467入力・70出力をSHA-256で照合し、RTL9210B-CGへ23,137,223バイト保存した。第7段階第85版は147実行・471判定、全体監査は99実行・214判定に通過した。 [再実行](runs/tsp-fk61-control5632-oral-geometry-20261123-repeat/manifest.json)・[第85版の監査](runs/stage7-evidence-update-20261123-fk61-control5632-oral-geometry/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control5632-oral-geometry/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `HumanVocalTract::resample` に渡す唇と咽頭端の弧長、研究版の `AreaProfile` の対応箇所を開く。研究ワークスペースで `jq '.coverage.f2_followup.synthetic_controls.fk61_control5632_oral_geometry.filter_initial_state_control' runs/stage7-evidence-update-20261123-fk61-control5632-oral-geometry/summary.json` を実行する。前の制御境界5504から採取し、弧長の差がセル長補間と平滑履歴に伝わる順序を照合する。 [上流の弧長と分岐位置](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1234)・[研究版の弧長と分岐位置](crates/vocal-core/src/anatomy/area.rs#L131)

## FK61_01の口腔の弧長と5504より前の平滑履歴を照合する（2026-11-23）

- 完了した項目。5504の口腔長の目標と5631の更新後のセル長は固定上流・試験版で一致した。5632・5760の口腔長の差は唇までの弧長に現れた。5631の第二極に対し、5503終了時の平滑状態だけの交換は、同区間の断面積だけの交換の約67倍の変化を生んだ。両方を揃えた8組で、PCMが冒頭から2937まで一致した。 [ケース定義](cases/tsp-fk61-control5504-oral-history.json)・[読解と測定](notes/tsp-fk61-control5504-oral-history.md)
- 未達の条件。5503に残った平滑状態の差を、発声初期からの局所体積速度とそれ以前の状態の寄与に切り分ける。PCMの交換比較の範囲は2937まで。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各4判定・Rustの11試験に通過し、採取系列・軌道・要約の28出力がバイト一致した。第7段階第86版は148実行・475判定、全体監査は99実行・214判定に通過した。4実行の2,545入力・76出力をSHA-256で照合し、RTL9210B-CGへ37,046,058バイト保存した。 [再実行](runs/tsp-fk61-control5504-oral-history-20261123-repeat/manifest.json)・[第86版の監査](runs/stage7-evidence-update-20261123-fk61-control5504-oral-history/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control5504-oral-history/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `AirwayNetwork::step` と研究版の `MovingAreas::step` を開く。研究ワークスペースで `jq '{endpoints,seed:.conditions.filter_seed.second_pole_delta_l2_cm3_s,area:.conditions.area.second_pole_delta_l2_cm3_s}' runs/tsp-fk61-control5504-oral-history-20261123-repeat/summary.json` を実行する。次の採取を3968〜5503へ広げ、同じ二段平滑の重みで5503への寄与を時刻ごとに分ける。 [上流の体積源](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L832)・[研究版の体積源](crates/vocal-core/src/airway/network/geometry.rs#L110)・[発声初期の対照](notes/tsp-fk61-oral-onset-inflow.md)

## FK61_01の発声初期から5503までに生じる体積源の寄与を照合する（2026-11-23）

- 完了した項目。3968〜5503の体積速度の差を二段平滑の閉形式で分け、5503の観測差に照合した。5120〜5247の寄与が最大で、4992〜5119とはほぼ逆向きだった。寄与は主に節点29・34の断面積に由来した。後続区間を固定した交換比較では、5120〜5247の入力だけでPCMが冒頭から2937まで一致した。 [ケース定義](cases/tsp-fk61-onset-to-control5504-volume-history.json)・[読解と測定](notes/tsp-fk61-onset-to-control5504-volume-history.md)
- 未達の条件。4992・5120の節点29・34の断面積の差が、再標本化、速度制限、標本ごとの補間加算のどこで現れるかを切り分ける。PCMの交換比較は2937まで。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各4判定・Rustの11試験に通過し、採取系列・軌道・要約の28出力がバイト一致した。第7段階第87版は149実行・479判定、全体監査は99実行・214判定に通過した。4実行の2,609入力・76出力をSHA-256で照合し、RTL9210B-CGへ168,436,187バイト保存した。 [再実行](runs/tsp-fk61-onset-to-control5504-volume-history-20261123-repeat/manifest.json)・[第87版の監査](runs/stage7-evidence-update-20261123-fk61-onset-to-control5504-volume-history/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-onset-to-control5504-volume-history/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `HumanVocalTract::resample` と `HumanAirway::commit`、研究版の `HumanTractControl` と `limit_tube` を開く。研究ワークスペースで `jq '{strongest_block,peak_sample,previous:.blocks["4992"].measured,current:.blocks["5120"].measured}' runs/tsp-fk61-onset-to-control5504-volume-history-20261123-repeat/summary.json` を実行する。節点29・34の断面積を速度制限の前後で採り、観測した増分と符号を照合する。 [上流の再標本化](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[上流の速度制限](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L233)・[研究版の速度制限](crates/vocal-core/src/airway/tract_control.rs#L309)

## FK61_01の節点29・34で断面積の再標本化と補間の丸めを照合する（2026-11-23）

- 完了した項目。4992・5120の代表面積と最小面積を3版で再計算した。上流と試験版の代表面積の差は速度制限前に現れた。前ブロックの128回の反復加算で、5120の開始面積差は節点29で前の目標差の32倍、節点34では逆符号になった。開始面積を2節点で揃えた条件でPCMが冒頭から2937まで一致した。 [ケース定義](cases/tsp-fk61-control4992-5120-area-targets.json)・[読解と測定](notes/tsp-fk61-control4992-5120-area-targets.md)
- 未達の条件。標本番号から直接計算する補間によって終了時の丸め差が縮むか、局所の体積速度や全PCMへ伝わるかを検証する。今回の交換比較は2937まで。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各4判定・Rustの11試験に通過し、格子・面積・軌道・要約の34出力がバイト一致した。上流の形状連続性試験は5件に通過し、既知の1件は既定どおり除外された。第7段階第88版は150実行・484判定、全体監査は99実行・214判定に通過した。4実行の2,687入力・88出力をSHA-256で照合し、RTL9210B-CGに167,281,561バイト保存した。 [再実行](runs/tsp-fk61-control4992-5120-area-targets-20261123-repeat/manifest.json)・[第88版の監査](runs/stage7-evidence-update-20261123-fk61-control4992-5120-area-targets/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control4992-5120-area-targets/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `begin_block` と研究版の `MovingAreas::step` を開く。研究ワークスペースで `jq '.coverage.f2_followup.synthetic_controls.fk61_control4992_5120_area_targets.boundary_roundoff' runs/stage7-evidence-update-20261123-fk61-control4992-5120-area-targets/summary.json` を実行する。隔離ビルドで節点29・34の4992・5120ブロックの代表面積を開始値と標本番号から直接計算し、終了面積・体積速度・口端流量・全発話PCMを基準と比較する。 [上流の増分](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)・[研究版の面積加算](crates/vocal-core/src/airway/network/geometry.rs#L124)

## FK61_01の節点29・34で代表面積の直接補間を比較する（2026-11-23）

- 完了した項目。隔離ビルドで4992・5120の2ブロックの代表面積を開始値と標本番号で計算した。全512標本が有理数の直線の丸め値と一致し、4箇所で終端面積が目標に達した。口端流量の両ビルド間の初差は5006。固定上流とのPCM初差は2937、差のあるフレームは2,355で基準と同じ。局所の面積残差を減らした結果を保存し、固定上流とのPCM再現を改善する変更としては採用を見送った。 [ケース定義](cases/tsp-fk61-control4992-5120-indexed-area.json)・[読解と測定](notes/tsp-fk61-control4992-5120-indexed-area.md)
- 未達の条件。補間方式を両版で揃えた状態で、目標面積と開始面積の差が体積速度と放射に残るかを照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2ディレクトリで各5判定と各ビルドの補間試験に通過し、採取・全PCM・隔離パッチ・要約など24出力がバイト一致した。第7段階第89版は151実行・488判定、全体監査は99実行・214判定に通過した。4実行の2,713入力・66出力をSHA-256で照合し、RTL9210B-CGへ60,289,074バイト保存した。 [再実行](runs/tsp-fk61-control4992-5120-indexed-area-20261123-repeat/manifest.json)・[第89版の監査](runs/stage7-evidence-update-20261123-fk61-control4992-5120-indexed-area/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control4992-5120-indexed-area/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `AirwayNetwork::step` と研究版の隔離パッチを開く。研究ワークスペースで `jq '.coverage.f2_followup.synthetic_controls.fk61_control4992_5120_indexed_area.pcm_diagnostics' runs/stage7-evidence-update-20261123-fk61-control4992-5120-indexed-area/summary.json` を実行する。上流の同じ2節点・2ブロックで直接補間を試し、両方が同じ補間を使う条件の体積速度とPCMを照合する。 [上流の面積加算](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L845)・[研究版の隔離パッチ](runs/tsp-fk61-control4992-5120-indexed-area-20261123-repeat/artifacts/indexed-area.patch)

## FK61_01の上流と研究版で面積補間を揃えて比較する（2026-11-23）

- 完了した項目。上流の隔離ビルドでも直接補間を試し、対象2節点・2ブロックの512標本を有理数の直線に照合した。4条件を比較し、両版を直接補間に揃えると面積の最大差が4分の1、平滑後の体積速度のRMS差が約50分の1になることを確認した。全4条件で口端初差3971、PCM初差2937が残った。 [事前登録](cases/tsp-fk61-control4992-5120-indexed-area-paired.json)・[読解と測定](notes/tsp-fk61-control4992-5120-indexed-area-paired.md)
- 未達の条件。補間条件を揃えた状態で、体積差の展開式を適用して平滑前の体積速度の演算残差と放射への影響を照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。観測パッチの競合を解消した後、2ディレクトリで各4判定と各上流ビルドのRust試験9件に通過し、採取・全発話出力・隔離パッチ・要約を含む24出力がバイト一致した。第7段階第90版は152実行・492判定、全体監査は99実行・214判定に通過した。4実行の2,541入力・66出力をSHA-256で照合し、RTL9210B-CGに60,291,574バイト保存した。 [再実行](runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/manifest.json)・[第90版の監査](runs/stage7-evidence-update-20261123-fk61-control4992-5120-indexed-area-paired/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control4992-5120-indexed-area-paired/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `AirwayNetwork::step`、研究版の `MovingAreas::step` と体積差の展開式の記録を開く。研究ワークスペースで `jq '.comparisons["indexed:indexed"].raw_volume_difference_decomposition' runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/summary.json` を実行する。節点29・34の4992と5120からの2ブロックで体積差の展開式を比較する。 [上流の体積差](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L869)・[研究版の体積差](crates/vocal-core/src/airway/network/geometry.rs#L133)・[既存の展開式](notes/tsp-fk61-node40-expanded-volume.md)

## FK61_01の上流と研究版で体積差の展開式を比較する（2026-11-23）

- 完了した項目。両版の断面積補間を揃えたまま節点29・34の4992〜5247で体積差を展開した。幾何由来の差を引いたRMS残差は1.151×10⁻¹¹から1.039×10⁻¹⁶ cm³/sに減った。最初に変わる体積源は両版とも4992の節点29だった。全発話PCMの初差2937は残り、上流の展開式で16682の丸め差が消えた。 [事前登録](cases/tsp-fk61-control4992-5120-expanded-volume-paired.json)・[読解と測定](notes/tsp-fk61-control4992-5120-expanded-volume-paired.md)
- 未達の条件。16682で `f32` の丸め境界を越えた直前の値と放射各成分の寄与を確かめる。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。2実行の各5判定、上流の気道試験9件と研究版の補間試験1件に通過した。隔離パッチ、採取、全PCM、要約の27出力がバイト一致した。第7段階第91版は153実行・496判定、全体監査は99実行・214判定に通過した。4実行の2,823入力・72出力をSHA-256で照合し、RTL9210B-CGに60,298,436バイト保存した。 [再実行](runs/tsp-fk61-control4992-5120-expanded-volume-paired-20261123-repeat/manifest.json)・[第91版の監査](runs/stage7-evidence-update-20261123-fk61-control4992-5120-expanded-volume-paired/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-control4992-5120-expanded-volume-paired/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `HumanVoice::render` と研究用の `replay`・`midpoint_report` を開く。研究ワークスペースで `jq '.within_version.upstream.pcm.first' runs/tsp-fk61-control4992-5120-expanded-volume-paired-20261123-repeat/summary.json` を実行する。口・壁・鼻の放射を冒頭から16682の前後まで採取し、FIR、DC除去とリミッターを経た時点で `f32` の中点に対する距離を比較する。 [上流の出力処理](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L399)・[出力段の独立計算](tools/measure_tsp_fk61_pcm_first_difference.py#L29)

## FK61_01のPCMフレーム16682で丸め境界を照合する（2026-11-23）

- 完了した項目。4条件の全PCMを再現し、16,704フレームで放射・FIR・DC除去・包絡を独立計算に照合した。上流の展開式で16682の変換直前の値が+2.540×10⁻¹⁵動き、隣接する `f32` 値の中点を越えた。口端履歴だけの双方向交換でも同じPCMを再現した。 [ケース定義](cases/tsp-fk61-pcm16682-rounding.json)・[読解と測定](notes/tsp-fk61-pcm16682-rounding.md)
- 未達の条件。展開式どうしで最大差が残った104883の変換直前を観測し、後半に残る版間差を `f64` とPCMの双方で測る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流のエンジン試験6件と研究版の一様管試験3件が各ビルドで通り、全PCM、観測系列、ハッシュ記録と結果要約の3出力が2実行で一致した。第7段階第92版は154実行・500判定、全体監査は99実行・214判定に通過した。4実行の2,777入力・28出力をSHA-256で照合し、RTL9210B-CGに25,022,497バイト保存した。 [再実行](runs/tsp-fk61-pcm16682-rounding-20261123-repeat/manifest.json)・[第92版の監査](runs/stage7-evidence-update-20261123-fk61-pcm16682-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-pcm16682-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。観測器の `capture` と出力再計算の `replay` を開く。研究ワークスペースで `jq '.rounding, .stage_differences.upstream.linear_response_to_difference' runs/tsp-fk61-pcm16682-rounding-20261123-registered/summary.json` を実行する。104883までの出力履歴を照合し、変換前の誤差分布とPCMの差が生じるフレームを比較する。 [出力の採取](tools/measure_tsp_fk61_pcm16682_rounding.py#L33)・[独立計算](tools/measure_tsp_fk61_pcm_first_difference.py#L29)

## FK61_01の全発話で丸め前とPCMの誤差を照合する（2026-11-24）

- 完了した項目。4条件の全発話で放射と出力段を再計算した。通常式どうしから展開式どうしにすると、PCMのRMS差は約16分の1になり、変換前のRMS差は0.34%増えた。104883では上流だけが丸め境界を越えた。差のある2,351フレームのうち1 ULPは1,395にとどまり、99%以上という予測は棄却した。 [事前登録](cases/tsp-fk61-full-pcm-rounding.json)・[読解と測定](notes/tsp-fk61-full-pcm-rounding.md)
- 未達の条件。別の確認用発話でも、変換前の最大差とPCMの最大差の位置、振幅ごとのULP差の傾向を照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。4条件で通常CLI・観測版・保存済みPCMが全116,132フレーム一致した。上流のエンジン試験6件と研究版の一様管試験3件が各ビルドで通り、計測の5判定に通過した。全発話の観測系列とPCMのハッシュ記録、要約は2実行でバイト一致した。第7段階第93版は155実行・504判定、全体監査は99実行・214判定に通過した。4実行の2,793入力・28出力をSHA-256で照合し、RTL9210B-CGに179,216,081バイト保存した。 [再実行](runs/tsp-fk61-full-pcm-rounding-20261124-repeat/manifest.json)・[第93版の監査](runs/stage7-evidence-update-20261124-fk61-full-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-full-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。全発話の `compare` と既存の確認用FK61_02のケース定義を開く。研究ワークスペースで `jq '.utterances.FK61_02.matched_pcm' runs/tsp-held-out-matched-speech-20261123-repeat/summary.json` を実行する。同じ48 kHzの通常レンダーの変換前誤差とPCM差を集計し、FK61_01の結果と比較する。 [全発話の集計](tools/measure_tsp_fk61_full_pcm_rounding.py#L54)・[FK61_02の発話条件](runs/tsp-held-out-matched-speech-20261123-repeat/artifacts/FK61_02/matched-case.json)

## FK61_02の通常レンダーで丸め前とPCMの誤差を照合する（2026-11-24）

- 完了した項目。通常CLIと観測版で保存済みの全144,727フレームを再現し、放射からPCMまでの出力段を独立計算に照合した。変換前の最大差31148ではPCMが一致し、129260の1 ULP差がPCM差の二乗和の99.999%を占めた。複数ULP差の681フレームはすべてPCM振幅10⁻⁶以下だった。 [事前登録](cases/tsp-fk61-02-full-pcm-rounding.json)・[読解と測定](notes/tsp-fk61-02-full-pcm-rounding.md)
- 未達の条件。同文の男性体型MK61_02で振幅別ULP数と丸め前後の最大差の位置を照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流のエンジン試験6件、研究版の一様管試験3件と計測の4判定に通過した。全発話の観測系列、PCMのハッシュ記録、要約の3出力は2実行でバイト一致した。第7段階第94版は156実行・508判定、全体監査は99実行・214判定に通過した。4実行の2,788入力・24出力をSHA-256で照合し、RTL9210B-CGに112,807,668バイト保存した。 [再実行](runs/tsp-fk61-02-full-pcm-rounding-20261124-repeat/manifest.json)・[第94版の監査](runs/stage7-evidence-update-20261124-fk61-02-full-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-fk61-02-full-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。通常CLIの入口 `normal_pcm`、観測の `capture`、集計の `amplitude_groups` を開く。研究ワークスペースで `jq '.utterances.MK61_02.matched_pcm' runs/tsp-held-out-matched-speech-20261123-repeat/summary.json` を実行する。144,727フレームの保存PCMを基準に、最大差82703を含む男性体型の全発話を比較する。 [通常CLI](tools/measure_tsp_fk61_lip_onset.py#L41)・[採取](tools/measure_tsp_fk61_pcm16682_rounding.py#L32)・[MK61_02の発話条件](runs/tsp-held-out-matched-speech-20261123-repeat/artifacts/MK61_02/matched-case.json)

## 同文の男性体型MK61_02で丸め前とPCMの誤差を照合する（2026-11-24）

- 完了した項目。通常CLIと観測版に保存された体型を渡し、男性側の全144,727フレームを保存PCMに照合した。女性側に対するPCM最大差は0.125倍、変換前のRMS差は1.585倍だった。82703のPCM最大差は1 ULP。複数ULP差の67フレームはいずれもPCM振幅10⁻⁶以下だった。 [事前登録](cases/tsp-mk61-02-full-pcm-rounding.json)・[読解と測定](notes/tsp-mk61-02-full-pcm-rounding.md)
- 未達の条件。変換前の誤差とPCM差による順位、および複数ULP差が低振幅に集中する傾向を確認用12発話で照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流のエンジン試験6件、研究版の一様管試験3件と計測の4判定に通過した。観測系列、PCMのハッシュ記録、要約の3出力は2実行でバイト一致した。共通化後のFK61_02再計算も保存済み要約と完全一致した。第7段階第95版は157実行・512判定、全体監査は99実行・214判定に通過した。4実行の2,801入力・24出力をSHA-256で照合し、RTL9210B-CGに111,272,464バイト保存した。 [再実行](runs/tsp-mk61-02-full-pcm-rounding-20261124-repeat/manifest.json)・[第95版の監査](runs/stage7-evidence-update-20261124-mk61-02-full-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-mk61-02-full-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。保持済みの確認用セットの `build_probes`・`measure_one` と、今回の `analyze_observation` を開く。研究ワークスペースで `jq '.utterances | keys' runs/tsp-held-out-matched-speech-20261123-repeat/summary.json` を実行する。同じビルドで12発話を通常入口から描画し、丸め前・PCMの誤差順位と振幅別ULP数を集約する。 [確認用セットの計測](tools/measure_tsp_held_out_matched_speech.py#L112)・[共通の集計](tools/measure_tsp_fk61_02_full_pcm_rounding.py#L47)

## 確認用12発話で丸め前とPCMの誤差順位を照合する（2026-11-24）

- 完了した項目。12発話の1,487,586フレームで通常CLI・観測版・保存PCMを照合し、変換前とPCMのRMS差を集計した。順位相関は0.147で、66対中30対が逆転した。全発話で変換前の最大差のフレームはPCMが一致し、複数ULP差の4,582フレームはすべてPCM振幅10⁻⁶以下だった。 [事前登録](cases/tsp-held-out-pcm-rounding.json)・[読解と測定](notes/tsp-held-out-pcm-rounding.md)
- 未達の条件。CSDの先頭2句で、声源と初期姿勢を揃えた上流との間に出る変換前とPCMの差を照合する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。初回は男性側の個別記録にだけある男女比較の仮説を共通項目の照合に含めた。共通の測定値の照合と男女の誤差比の再計算に修正し、初回データの再計算と修正後の2実行で全6判定に通過した。最後の2実行の25出力はバイト一致した。第7段階第96版は158実行・517判定、全体監査は99実行・214判定に通過した。5実行の3,087入力・96出力をSHA-256で照合し、RTL9210B-CGに1,194,726,121バイト保存した。 [初回の不合格記録](runs/tsp-held-out-pcm-rounding-20261124-registered/manifest.json)・[再実行](runs/tsp-held-out-pcm-rounding-20261124-repeat/manifest.json)・[第96版の監査](runs/stage7-evidence-update-20261124-held-out-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-held-out-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。CSDの `csd-continuous-song` のケース、同設定の歌唱を採取する `measurement`、全発話の集計に使った `compare` を開く。研究ワークスペースで `jq '.song, .phrases, .measurement.short_frames' cases/csd-continuous-song.json` を実行する。en001aの先頭2句の同設定対照で、句間を含めて出力丸め前後の差を追う。 [CSDの対照条件](cases/csd-continuous-song.json)・[歌唱の採取](tools/measure_csd_continuous_song.py#L91)・[振幅と丸めの集計](tools/measure_tsp_fk61_full_pcm_rounding.py#L54)

## CSDの先頭2句で丸め前後と句間を照合する（2026-11-24）

- 完了した項目。`en001a` の先頭2句の201,600出力フレームを、初期姿勢と声源を揃えた固定上流と研究版で比較した。両版の403,200内部標本の放射からPCMまでを独立に再計算した。最大PCM差は1.413×10⁻¹¹で、丸め前の最大差と同じ20,363フレームだった。句間の2,160フレームはPCMが一致した。 [ケース定義](cases/csd-en001a-two-phrase-pcm-rounding.json)・[読解と測定](notes/csd-en001a-two-phrase-pcm-rounding.md)
- 未達の条件。丸め前とPCMの最大差が異なる位置に出るという予測は不成立だった。最初の内部標本で口端流量が分かれた原因は切り分けが必要。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。初回の独立計算は上流の微小な履歴のゼロ化を含まず不合格だった。上流の制御更新を反映して初回観測を再検算し、修正後の2実行は各4判定に通過した。要約を含む7出力は修正後の2実行で一致し、要約を除く6出力は初回とも一致した。第7段階第97版は159実行・522判定、全体監査は99実行・214判定に通過した。5実行の3,096入力・42出力をSHA-256で照合し、出力165,900,830バイトをRTL9210B-CGに保存した。 [初回の不合格](runs/csd-en001a-two-phrase-pcm-rounding-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/manifest.json)・[第97版の監査](runs/stage7-evidence-update-20261124-csd-en001a-two-phrase-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-two-phrase-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。同設定上流の姿勢の初期化、上流の気道の口端負荷、先行実験の負荷履歴の独立計算を開く。研究ワークスペースで `jq '.source_field_order, (.initial_source_rows | map_values(.[0:2]))' runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/summary.json` を実行する。最初の制御更新前後の唇端面積・終端圧力・放射負荷を観測し、最初に分かれた値だけを交換する比較を事前登録する。 [姿勢の初期化](tools/upstream_csd_continuous_probe.rs#L61)・[上流の口端負荷](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1121)・[負荷履歴の検算](tools/measure_tsp_fk61_pcm2937_terminal_load.py#L54)

## CSD冒頭の口端流量差を体積源と放射負荷に分ける（2026-11-24）

- 完了した項目。`en001a` の同設定対照で全201,600 PCMフレームを先行実行に照合し、最初の2内部標本で口端への制御目標、面積、長さ、体積、二段平滑、放射負荷を独立に再計算した。最初の口端流量差4.674×10⁻¹⁷ cm³/sは、負荷への流入だけを交換すると両方向で99.99999%が解消した。標本1では平滑前の局所体積速度は両版で一致し、平滑状態に最初の差が残った。 [ケース定義](cases/csd-en001a-first-lip-load.json)・[読解と測定](notes/csd-en001a-first-lip-load.md)
- 未達の条件。制御更新より前に、口端の面積とセル長の微差が生じていた。初期姿勢からそれらが分かれた演算は今回の観測点より上流にある。実録音のF2人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流の一様管・狭窄の9試験、研究版の幾何補間の1試験と計測の各4判定に通過した。研究ワークスペースと `/tmp` からの2実行で、要約と4出力がバイト一致した。第7段階の第98版は160実行・526判定、全体監査は99実行・214判定に通過した。4実行の2,950入力・28出力をSHA-256で照合し、出力185,416バイトをRTL9210B-CGに保存した。 [初回の実行](runs/csd-en001a-first-lip-load-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-first-lip-load-20261124-repeat/manifest.json)・[第98版の監査](runs/stage7-evidence-update-20261124-csd-en001a-first-lip-load/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-first-lip-load/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `HumanVocalTract::resample` と研究版の `HumanTractControl::with_oral_cells`、`resample_reusing` を開く。研究ワークスペースで `jq '.upstream[0], .candidate[0] | {old_area, old_length, target_area_cm2, target_length_cm}' runs/csd-en001a-first-lip-load-20261124-repeat/artifacts/lip-observations.json` を実行する。末端セルの調音面積を得る断面標本と中心線の弧長を初期化時に採取し、面積と長さを個別に交換するケースを登録する。 [上流の再標本化](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[研究版の初期化](crates/vocal-core/src/airway/tract_control.rs#L134)・[研究版の再標本化](crates/vocal-core/src/anatomy/resample.rs#L46)

## CSDの初期姿勢で口端セルの面積と長さを照合する（2026-11-24）

- 完了した項目。`en001a` の初期化直後と最初の出力フレーム後で、49本の測定線の両版の中心座標、区間距離、累積弧長、面積を比較した。初差は順に0、4、6番。口端の弧長が研究版で3.553×10⁻¹⁵ cm短く、気道のセル長は2.220×10⁻¹⁶ cm短かった。末端セルの長さだけを交換して、標本0の体積速度差1.066×10⁻¹¹ cm³/sを両方向で再現した。 [ケース定義](cases/csd-en001a-initial-oral-geometry.json)・[読解と測定](notes/csd-en001a-initial-oral-geometry.md)
- 未達の条件。累積座標と口腔の両端を揃えると初期面積差が半減するという予測は不成立。測定線5の中心座標の由来と、その座標だけを交換した場合に口端まで残る差は未検証。実録音のF2人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。初回は研究版の単体試験が読むJSON2件が隔離先になく停止した。2件を入力に加え、2実行で各4判定に通過し、要約と5出力がバイト一致した。保存済みPCMの201,600フレームを両版で照合した。第7段階の第99版は161実行・531判定、全体監査は99実行・214判定に通過した。5実行の3,146入力・35出力をSHA-256で照合し、出力309,685バイトをRTL9210B-CGに保存した。 [初回の停止](runs/csd-en001a-initial-oral-geometry-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-initial-oral-geometry-20261124-repeat/manifest.json)・[第99版の監査](runs/stage7-evidence-update-20261124-csd-en001a-initial-oral-geometry/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-initial-oral-geometry/manifest.json)
- 次に開くファイルと実行するコマンド。上流の測定線と中心線を作る `HumanVocalTract::compute`、研究版の `area_profile_from_contacts_reusing`、先行の中点照合 `midpoint_report` を開く。研究ワークスペースで `jq -c 'select(.completed_frames==0) | .tract.centerline[3:7]' runs/csd-en001a-initial-oral-geometry-20261124-repeat/artifacts/{upstream,candidate}.jsonl` を実行する。測定線4と5のx座標の個別交換を登録し、区間距離と口端のセル長、標本0の体積速度までを測る。 [上流の中心線](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1219)・[研究版の断面](crates/vocal-core/src/anatomy/area.rs#L72)・[中点の独立計算](tools/measure_tsp_fk61_centerline_length_origin.py#L61)

## CSDの中心座標を交換して累積弧長まで追う（2026-11-24）

- 完了した項目。`en001a` の中心間距離へ渡す測定線4・5のx座標を両方向で交換した。4番の交換では最初の区間距離が相手と一致し、累積値とPCMは元の版に一致した。5番の交換では6番の累積値だけが1 ULP変わり、7番で再び元の値と一致した。口端の体積速度と最初の放射流量は各版の対照と一致したが、最初にPCMが分かれる出力フレームは上流3,300、研究版7,299。対照との最大差は両版でフレーム134,534の1 ULP。 [ケース定義](cases/csd-en001a-centerline-coordinate-swap.json)・[読解と測定](notes/csd-en001a-centerline-coordinate-swap.md)
- 未達の条件。事後の独立計算で、測定線6の弧長差が初期化時と最初の制御更新で咽頭セル7の代表面積を動かすと見積もった。そのセルの面積・体積源の実測とPCMへの経路は未確認。実録音のF2人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。両版の各4条件で出力201,600フレームずつのPCMと計画を比較した。上流の幾何の6試験と研究版の再標本化の1試験を通過し、上流で既知の問題として無効化された試験は1件だった。研究ワークスペースと `/tmp` からの2実行で各5判定が通り、要約と5出力がバイト一致した。第7段階の第100版は162実行・536判定、全体監査は99実行・214判定に通過した。4実行の3,008入力・30出力をSHA-256で照合し、出力11,176,432バイトをRTL9210B-CGに保存した。 [初回](runs/csd-en001a-centerline-coordinate-swap-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-centerline-coordinate-swap-20261124-repeat/manifest.json)・[第100版の監査](runs/stage7-evidence-update-20261124-csd-en001a-centerline-coordinate-swap/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-centerline-coordinate-swap/manifest.json)
- 次に開くファイルと実行するコマンド。上流の再標本化 `HumanVocalTract::resample`、研究版の `AreaProfile::cell` と `MovingAreas::step` を開く。研究ワークスペースで `jq '.upstream | {native:[.native["0"].grid[6][0],.native["1"].grid[6][0]], ray5:[.ray5["0"].grid[6][0],.ray5["1"].grid[6][0]]}' runs/csd-en001a-centerline-coordinate-swap-20261124-repeat/artifacts/observations.json` を実行する。咽頭セル7の再標本化の入力と出力を採取し、初期面積と制御目標を個別に交換する比較を登録する。 [上流の再標本化](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[研究版のセル補間](crates/vocal-core/src/anatomy/resample.rs#L95)・[移動体積の計算](crates/vocal-core/src/airway/network/geometry.rs#L99)

## CSDの咽頭セル7で初期面積と目標面積を切り分ける（2026-11-24）

- 完了した項目。`en001a` の測定線5の交換で咽頭の代表面積が変わるのはセル7だけだった。両版で初期面積だけを交換すると測定線5交換の201,600 PCMフレームをビット再現し、目標面積だけを交換すると通常描画と一致した。内部標本0・1では、体積速度と二段平滑後の速度が全条件で一致した。 [ケース定義](cases/csd-en001a-pharynx-cell7-source.json)・[読解と測定](notes/csd-en001a-pharynx-cell7-source.md)
- 未達の条件。事後の逐次計算では、初期面積の交換による配分前の体積速度差は上流の標本12、研究版の標本8で最初に現れると予測した。残り126標本の実測と、セル7のコンプライアンス・両隣の枝を経る差の切り分けが残る。実録音のF2人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流の基準幾何・気道の7試験、研究版の再標本化の1試験に通過した。研究ワークスペースと `/tmp` からの2実行の各3判定に通過し、要約と5出力がバイト一致した。第7段階の第101版は163実行・541判定、全体監査は99実行・214判定に通過した。4実行の3,016入力・30出力をSHA-256で照合し、出力14,271,381バイトをRTL9210B-CGに保存した。 [初回](runs/csd-en001a-pharynx-cell7-source-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-pharynx-cell7-source-20261124-repeat/manifest.json)・[第101版の監査](runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-source/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-source/manifest.json)
- 次に開くファイルと実行するコマンド。上流と研究版の `AirwayNetwork::step`、先行の節点体積源の独立計算 `replay` を開く。研究ワークスペースで `jq '.trials | map_values({native:.native.first_samples, initial_only:.initial_only.first_samples})' runs/csd-en001a-pharynx-cell7-source-20261124-repeat/summary.json` を実行する。セル7と前後の枝で初回制御ブロックの128標本を採取し、体積源、コンプライアンス、枝の慣性・抵抗、圧力差と流量の初差を比較する。 [上流の更新順](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L833)・[研究版の更新順](crates/vocal-core/src/airway/network.rs)・[独立計算](tools/measure_tsp_fk61_node42_volume_source.py#L85)

## CSDの咽頭セル7で第1制御ブロックの流量収支を照合する（2026-11-24）

- 完了した項目。`en001a` の通常描画と咽頭セル7の初期面積だけを交換した描画を比較した。両版でコンプライアンスを単独交換すると、標本0の圧力差を再現した。内側の枝流量は標本1から分かれ、配分前の体積速度は上流で標本12から20点、研究版で標本8から32点で異なった。先頭128内部標本で全節点の体積速度、3節点の圧力・壁運動、4枝の流量を独立に照合した。 [事前登録](cases/csd-en001a-pharynx-cell7-first-block.json)・[読解と測定](notes/csd-en001a-pharynx-cell7-first-block.md)
- 未達の条件。今回の局所モデルには外側2枝の流量を観測値で与えた。標本0の圧力差だけで後続の口端やPCMがどこまで変わるかは未照合。実録音のF2人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。初回の集計で観測列の取り込み漏れを修正した。新しい2実行で上流の気道・幾何の7試験と研究版の再標本化の1試験、計測の各18判定に通過した。各条件の201,600 PCMフレームと全歌唱計画は先行実行と一致し、観測CSV・PCM・観測パッチ・要約を含む2実行の10出力もバイト一致した。第7段階第102版は164実行・545判定、全体監査は99実行・214判定に通過した。4実行の3,062入力・38出力をSHA-256で照合し、40,065,953バイトをRTL9210B-CGに保存した。 [修正後の初回](runs/csd-en001a-pharynx-cell7-first-block-20261124-verified/manifest.json)・[再実行](runs/csd-en001a-pharynx-cell7-first-block-20261124-repeat/manifest.json)・[第102版の監査](runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-first-block/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-first-block/manifest.json)
- 次に開くファイルと実行するコマンド。両版の `AirwayNetwork::step` の圧力更新と、歌唱の放射からPCMまでの再計算を開く。研究ワークスペースで `jq '.sides | map_values({earliest_pressure_observed, swap: .swaps.native_receives_initial_only.compliance})' runs/csd-en001a-pharynx-cell7-first-block-20261124-repeat/summary.json` を実行する。通常描画の節点20で標本0のコンプライアンスだけを切り替え、最初の口端流量差とPCM差が出る標本を比較する。 [上流の圧力更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1121)・[研究版の圧力更新](crates/vocal-core/src/airway/network.rs#L788)・[出力段の再計算](tools/measure_csd_en001a_two_phrase_pcm_rounding.py)

## CSDの咽頭セル7のコンプライアンス一値を交換して出力への伝搬を追う（2026-11-24）

- 完了した項目。標本0だけコンプライアンスを交換し、両版で節点20の圧力差を再現した。上流は標本1の節点21まで差が届き、全放射とPCMは通常と一致した。研究版は標本2で全71節点の圧力が一致しても標本3で差が再び現れ、壁放射86、口端流量100、最初のPCM差26,133へと続いた。標本2の内側2枝の流量を局所モデルで再計算し、その履歴だけで標本3の圧力差を再現した。 [事前登録](cases/csd-en001a-pharynx-cell7-compliance-pulse.json)・[読解と測定](notes/csd-en001a-pharynx-cell7-compliance-pulse.md)
- 未達の条件。研究版で標本3の圧力差を再現する枝履歴は局所モデルの計算値。描画中の枝状態を採って、履歴の値と個別交換を確かめる。実録音のF2人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流の気道・幾何の7試験と研究版の再標本化の1試験を通過した。両版の各3条件の放射からPCMまでを独立に再計算し、2実行の各20判定に通過した。要約と6出力はバイト一致した。第7段階第103版は165実行・549判定、全体監査は99実行・214判定に通過した。4実行の3,120入力・32出力をSHA-256で照合し、130,294,526バイトをRTL9210B-CGに保存した。 [初回](runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-repeat/manifest.json)・[第103版の監査](runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-compliance-pulse/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-compliance-pulse/manifest.json)
- 次に開くファイルと実行するコマンド。両版の枝の慣性と流量履歴の更新、観測コードの `observe`、読解ノートの「標本3で圧力差が戻る理由の検算」を開く。研究ワークスペースで `jq '.sides | map_values(.sample_zero)' runs/csd-en001a-pharynx-cell7-compliance-pulse-20261124-repeat/summary.json` と検算コマンドを実行する。両版の内部標本0〜4で節点19〜22と接続枝の流量・慣性履歴、壁の速度・変位を採り、標本3の更新前に各履歴だけを通常へ戻す比較を登録する。 [上流の枝更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L923)・[研究版の枝更新](crates/vocal-core/src/airway/network.rs#L724)・[観測コード](tools/tsp_fk61_terminal_branch_observation.py#L42)・[検算](notes/csd-en001a-pharynx-cell7-compliance-pulse.md#標本3で圧力差が戻る理由の検算)

## CSDの咽頭セル7で圧力差を保持した枝の前回流量を照合する（2026-11-24）

- 完了した項目。両版の6条件で、先頭8内部標本の枝の履歴を採取した。研究版の標本2の流量差は事前予測どおり、枝19→20で−1.059×10⁻²²、枝20→21で+2.118×10⁻²² cm³/sだった。標本3で両方の前回流量を通常値に戻すと、標本3〜7の71節点の圧力と全201,600 PCMフレームが通常描画と一致した。 [事前登録](cases/csd-en001a-pharynx-cell7-branch-history.json)・[読解と実測](notes/csd-en001a-pharynx-cell7-branch-history.md)
- 未達の条件。確認曲 `en005a` では同設定の先頭20 msの対照まで済んでいる。歌唱中に放射からPCMまでに出る差と、調整曲 `en001a` との再現範囲を照合する。実録音のF2人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流の気道・幾何の7試験と研究版の再標本化の1試験を通過した。両版の各6条件について、体積源、壁・節点圧力と前回流量、歌唱計画とPCMを照合し、2実行の各36判定に通過した。要約、PCMと計画、観測CSV、パッチを含む18出力がバイト一致した。第7段階第104版は166実行・553判定、全体監査は99実行・214判定に通過した。4実行の3,153入力・54出力をSHA-256で照合し、23,401,951バイトをRTL9210B-CGに保存した。 [初回](runs/csd-en001a-pharynx-cell7-branch-history-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-pharynx-cell7-branch-history-20261124-repeat/manifest.json)・[第104版の監査](runs/stage7-evidence-update-20261124-csd-en001a-pharynx-cell7-branch-history/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-pharynx-cell7-branch-history/manifest.json)
- 次に開くファイルと実行するコマンド。確認曲 `en005a` の先頭20 msの比較、同設定上流の `matched` モード、既存の放射・出力段の `replay_output` を開く。研究ワークスペースで `jq '.id, .song, .frames, .normal_run' cases/csd-acoustic-f0-en005a-startup.json` と `jq 'keys' runs/csd-acoustic-f0-en005a-startup-20261121-a/summary.json` を実行する。通常の録音長の譜面を保持し、同設定の歌唱中に放射とfloat32変換の前後で差が出る範囲を事前登録する。 [確認曲の観測](notes/csd-acoustic-f0-en005a.md#pcmの最初の差を調べた対照)・[同設定の採取](tools/measure_csd_f0_startup.py)・[出力段の検算](tools/measure_csd_en001a_two_phrase_pcm_rounding.py#L203)

## 確認曲en005aで全曲の放射とPCMへの丸めを照合する（2026-11-24）

- 完了した項目。固定上流と研究版の設定を揃え、全36句、3,544,616フレームの放射からPCMを照合した。利得抑制が両版で1,103,539フレーム作動し、その処理を含む独立計算がPCMとビット一致した。丸め前の最大差は調整曲と共通する第1拍前の20,363、PCMの最大差は第36句の3,214,976で1 ULPだった。 [事前登録](cases/csd-en005a-full-pcm-rounding.json)・[全曲の測定](notes/csd-en005a-full-pcm-rounding.md)
- 未達の条件。丸め前とPCMの最大差が同じ位置に出るという予測は不成立だった。別の確認曲 `en035a` でも、第1拍前、譜面区間、終端以降を分けて比較する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。最初の2回は全曲の採取を完了した後、独立計算がリミッターの作動を検出して停止した。両方の停止記録と採取物を保持してリミッターを計算し、2回の再検算は各7判定に通過した。上流の歌唱と微小履歴の16試験、研究版の一様管3試験に通過し、解析要約を含む7出力がバイト一致した。監査は同名の採取ケースと検算ケースのSHA-256を照合するよう修正し、第7段階第105版の167実行・558判定、全体監査の99実行・214判定に通過した。7実行の5,779入力・50出力をSHA-256で照合した。RTL9210B-CGの成果の実体はハードリンクによる重複参照を除いて2,423,514,912バイトだった。 [初回の停止](runs/csd-en005a-full-pcm-rounding-20261124-registered/manifest.json)・[別ディレクトリからの停止](runs/csd-en005a-full-pcm-rounding-20261124-repeat/manifest.json)・[修正後の検算](runs/csd-en005a-full-pcm-rounding-20261124-verified-repeat/manifest.json)・[第105版の監査](runs/stage7-evidence-update-20261124-csd-en005a-full-pcm-rounding-verified/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en005a-full-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。確認曲 `en035a` の既存の `candidate-case.json` と、全曲比較の `plan_details`・`precast_values`・`compare_song` を開く。研究ワークスペースで `jq '.song_voice | {seconds:.render_end_seconds, phrases:(.scores|length), notes:([.scores[].notes[]]|length)}' runs/csd-long-note-vibrato-20261121-theta/artifacts/en035a/candidate-case.json` を実行する。第1拍前の共通する出力の範囲と、譜面区間の丸め前・PCM・利得抑制の比較条件を固定する。 [確認曲の既存測定](notes/csd-long-note-vibrato.md#録音と両合成の実測)・[全曲比較の入口](tools/measure_csd_en005a_full_pcm_rounding.py#L184)

## 確認曲en035aの全曲を第1拍前・譜面区間・終端以降で照合する（2026-11-24）

- 完了した項目。両版の全76句・5,590,588フレームを独立に再計算した。丸め前の最大差は `en005a` と共通する冒頭の20,363、PCMの最大差は第18句の1,637,779で1 ULPだった。利得抑制は両版で同じ618,105フレームに作動し、そのうちPCMは2フレームで分かれた。各曲の同じ版どうしで冒頭154,496 PCMフレームがビット一致した。 [事前登録](cases/csd-en035a-full-pcm-rounding.json)・[全曲の測定](notes/csd-en035a-full-pcm-rounding.md)
- 未達の条件。調整曲 `en012a` の全曲でも同じ区間別集計を再現し、確認曲2件と比較する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流の歌唱と微小履歴の16試験、研究版の一様管3試験が通過した。両版で通常の上流と研究版の保存PCMを照合し、全曲の出力段の計算を確認した。別ディレクトリからの2実行は各7判定に通過し、要約、圧縮した観測、PCMハッシュ、パッチ、譜面計画の7出力がバイト一致した。第7段階第106版は168実行・562判定、全体監査は99実行・214判定に通過した。4実行の3,150入力・32出力をSHA-256で照合し、3,997,254,571バイトをRTL9210B-CGに保存した。 [初回](runs/csd-en035a-full-pcm-rounding-20261124-registered/manifest.json)・[再実行](runs/csd-en035a-full-pcm-rounding-20261124-repeat/manifest.json)・[第106版の監査](runs/stage7-evidence-update-20261124-csd-en035a-full-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en035a-full-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。調整曲 `en012a` の保存済みの `candidate-case.json` と全曲比較の `plan_details`・`intervals` を開く。研究ワークスペースで `jq '.song_voice | {seconds:.render_end_seconds, phrases:(.scores|length), notes:([.scores[].notes[]]|length)}' runs/csd-long-note-vibrato-20261121-theta/artifacts/en012a/candidate-case.json` を実行する。その譜面の第1拍、終端と録音長から区間を事前登録し、同設定の出力を区間別に確認曲2件へ照合する。 [調整曲の既存測定](notes/csd-long-note-vibrato.md#録音と両合成の実測)・[区間別の計算](tools/measure_csd_en035a_full_pcm_rounding.py#L59)

## 調整曲en012aの全曲を確認曲2曲と照合する（2026-11-24）

- 完了した項目。全46句・6,613,334出力フレームで、通常の両版の保存PCMと、観測した放射からPCMまでを照合した。同じ版の3曲で冒頭76,672 PCMフレームが一致し、丸め前の最大差は共通区間の20,363に現れた。en012aのPCM最大差は第14句の1 ULP。利得抑制は両版で同じ3,216,415フレームに作動し、そのうちPCMに差が出たのは24フレームだった。 [事前登録](cases/csd-en012a-full-pcm-rounding.json)・[読解と測定](notes/csd-en012a-full-pcm-rounding.md)
- 未達の条件。調整曲 `en001a` の同設定による出力段の採取は先頭2句までで、全50句の集計が残る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。上流の歌唱・微小履歴の16試験、研究版の一様管3試験と2実行の各7判定に通過した。観測、PCMハッシュ、観測パッチ、譜面計画と要約の7出力は2実行でバイト一致した。第7段階第107版は169実行・566判定、全体監査は99実行・214判定に通過した。4実行の3,179入力・32出力をSHA-256で照合し、RTL9210B-CGに4,829,115,526バイト保存した。 [初回](runs/csd-en012a-full-pcm-rounding-20261124-registered/manifest.json)・[再実行](runs/csd-en012a-full-pcm-rounding-20261124-repeat/manifest.json)・[第107版の監査](runs/stage7-evidence-update-20261124-csd-en012a-full-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en012a-full-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。`en001a` の先頭2句のケースと、区間比較の `study_inputs`・`plan_details` を開く。研究ワークスペースで `jq '.song_voice | {seconds:.render_end_seconds, phrases:(.scores|length), notes:([.scores[].notes[]]|length)}' runs/csd-acoustic-f0-en001a-20261121-final/artifacts/candidate-case.json` を実行する。保存済みの研究版は全50句・86音符・64.8秒。公式の上流PCMを別の保存実行から参照し、全3,110,400フレームの区間と比較条件を事前登録する。 [先頭2句の計測](notes/csd-en001a-two-phrase-pcm-rounding.md)・[区間比較の入力](tools/measure_csd_en035a_full_pcm_rounding.py#L19)・[上流の公式PCM](runs/csd-song-planning-20261121-final/artifacts/csd/en001a-synth.wav)

## 調整曲en001aの採取を先頭2句から全曲へ広げる（2026-11-24）

- 完了した項目。全50句・86音符、両版の各3,110,400 PCMフレームを照合した。全曲と先頭2句はそれぞれ同じ版で195,520 PCMフレーム一致し、第3句の準備後の最初の制御更新で放射とPCMが分かれた。同設定の両版間では丸め前の最大差は4曲共通の冒頭、PCM最大差は第46句の拍の直前で1 ULPだった。 [事前登録](cases/csd-en001a-full-pcm-rounding.json)・[読解と測定](notes/csd-en001a-full-pcm-rounding.md)
- 未達の条件。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。既存の母音比較で欠測だった `/ɔ/` の高域の3 dB帯域幅は、元の掃引条件より広い範囲での確認が残る。
- 最後に確認した実行。上流の歌唱・微小履歴16試験、研究版の一様管3試験と2実行の各8判定に通過した。要約を含む主要7出力は2実行でバイト一致した。第7段階第108版は170実行・570判定、全体監査は99実行・214判定に通過した。4実行の3,216入力・32出力をSHA-256で照合した。圧縮観測の重複1件をハードリンクで共用し、RTL9210B-CGの成果の実体は重複分を除いて1,079,330,292バイトだった。 [初回](runs/csd-en001a-full-pcm-rounding-20261124-registered/manifest.json)・[再実行](runs/csd-en001a-full-pcm-rounding-20261124-repeat/manifest.json)・[第108版の監査](runs/stage7-evidence-update-20261124-csd-en001a-full-pcm-rounding/manifest.json)・[全体監査](runs/plan-completion-release-v6-csd-en001a-full-pcm-rounding/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `calibrate::formants` と、研究ワークスペースの `peak_rows`・`independent_response` を開く。研究ワークスペースで `jq '.peaks' runs/vowels-reference-20261119-b-linear-open-o/summary.json` を実行する。4,238 Hzと4,570 Hz付近で欠測だった3 dB交点を、同じ断面と注入・終端条件で、掃引上限と刻みを一つずつ変えて測るケースを登録する。 [固定母音のケース](cases/vowel-transfer-open-o.json)・[帯域幅の検算](tools/measure_vowel_transfer.py#L101)・[上流の固定姿勢](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/calibrate.rs#L138)

## 固定 /ɔ/ の高域2ピークの3 dB交点を照合する（2026-11-24）

- 完了した項目。固定姿勢の応答を4グリッド・計13,495点で上流、研究版、独立計算に通した。上限4,600 Hzでの欠測を再現し、拡張した条件で両方の交点を確認した。低いピークの幅525.00 Hzは隣のピークを含み、高いピークの幅は108.97 Hzだった。 [事前登録](cases/vowel-open-o-high-bandwidth.json)・[読解と測定](notes/vowel-open-o-high-bandwidth.md)
- 未達の条件。固定 /ɔ/ と上流の連続母音列の第1 LPCピークの差には、発声条件と分析条件が混在している。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各26判定、固定上流の解析ゴールデン1試験と研究版の一様管3試験に通過し、条件別の36出力と要約はバイト一致した。全体監査の初回にマニフェストのSHA-256が2文字不足していたため、実ファイルのハッシュで登録し直した。修正後は第7版の103実行・222判定を通過した。4実行の1,374入力・96出力をSHA-256で照合し、RTL9210B-CGに8,506,944バイト保存した。 [初回計測](runs/vowel-open-o-high-bandwidth-20261124-registered/manifest.json)・[再実行](runs/vowel-open-o-high-bandwidth-20261124-repeat/manifest.json)・[初回監査の不合格](runs/plan-completion-v7-open-o-bandwidth-20261124/manifest.json)・[修正後の全体監査](runs/plan-completion-v7-open-o-bandwidth-20261124-verified/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `render::vowels`、`estimate_formants` と固定発声側の測定窓を開く。研究ワークスペースで `jq '.vowels[] | select(.ipa=="ɔ") | {voice_run, lpc_hz_and_bandwidth}' runs/vowels-reference-20261119-b/summary.json` を実行する。48 kHzの保存済み波形2件に同一の有声窓とLPC設定を適用し、571 Hzと619.81 Hzの差のうち分析条件に由来する分を測る。 [既存の比較](notes/ten-vowel-benchmark.md#結果)・[上流の連続母音列](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L829)

## 連続母音列と固定発声の /ɔ/ のLPC条件を揃える（2026-11-24）

- 完了した項目。連続・固定の保存PCMを全フレーム再現し、65窓のLPCを公開推定器と独立計算で照合した。0.300秒開始の16 kHz・18次・100 msでは620.01 Hzと619.81 Hz。旧条件の未丸め差49.07 Hzを、波形15.64 Hz、分析設定33.42 Hz、固定側の開始時刻差0.00007 Hzに分けた。 [事前登録](cases/vowel-open-o-lpc-matched.json)・[読解と測定](notes/vowel-open-o-lpc-matched.md)
- 未達の条件。分析を揃えても旧設定の32 ms・12 kHz・12次では、0.300秒開始で31.49 Hzの差が残った。16 kHz・12次で2ピークになる条件と、同じ入力を18次にした条件の間で、根と採択が変わる次数を確認する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。初回は、比較用の有声窓に公開ピーク3つ以上を求めた集計が1条件で不合格だった。2ピークの結果を保存し、旧条件の3値の再現と、比較用窓の第1ピークおよび全根からの選別の照合を分けた。修正後の2実行は各11判定に通過し、2波形、分析窓、根、CLI報告と要約の6成果が一致した。計画全体の第8版は107実行・230判定に通過。4実行の985入力・39出力をSHA-256で照合し、RTL9210B-CGに10,420,804バイト保存した。 [初回の不合格](runs/vowel-open-o-lpc-matched-20261124-registered/manifest.json)・[修正後の計測](runs/vowel-open-o-lpc-matched-20261124-verified/manifest.json)・[再実行](runs/vowel-open-o-lpc-matched-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v8-open-o-lpc-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。上流の `estimate_formants` の帯域幅選別と、保存済み `analysis-windows.npz` の `lpc_28`・`lpc_29` を開く。研究ワークスペースで `jq '.conditions[] | select(.index==28 or .index==29) | {order,raw_peaks}' runs/vowel-open-o-lpc-matched-20261124-repeat/summary.json` を実行する。0.375秒から100 ms、16 kHzの3点平均を固定し、LPC 12〜18次の全根と採択の変化を事前登録する。 [上流の推定器](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[保存済みの分析入力](runs/vowel-open-o-lpc-matched-20261124-repeat/artifacts/analysis-windows.npz)

## /ɔ/ の固定窓でLPCの次数と帯域幅選別を照合する（2026-11-24）

- 完了した項目。先行実行と同じ1,600標本をPCMから復元し、12〜18次の105根を独立計算で照合した。第1ピークの112.91 Hzの差は帯域幅の選別を外しても残り、共有ラグからの係数更新で生じた。2 kHz台の12次・13次の根は600 Hzの帯域幅選別で落ち、14次で初めて3帯域の公開ピークが揃った。 [事前登録](cases/vowel-open-o-lpc-orders.json)・[実測と読解](notes/vowel-open-o-lpc-orders.md)
- 未達の条件。14次で3帯域が揃う結果は、この1窓について確認した。固定LF対照で口端流量のRMS差が5%に達しなかった理由を、基本波から高次の成分まで同じ定常区間で照合する工程が残る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの各4判定と固定上流の解析ゴールデン試験が通過した。分析窓、7次数の観測と要約が一致し、TSPの既存のプリエンファシス比較も既定値のまま再現した。計画全体の第9版は112実行・240判定に通過した。4実行の660入力・33出力をSHA-256で照合し、RTL9210B-CGに1,330,492バイト保存した。 [初回](runs/vowel-open-o-lpc-orders-20261124-registered/manifest.json)・[再実行](runs/vowel-open-o-lpc-orders-20261124-repeat/manifest.json)・[既定値の回帰確認](runs/tsp-lpc-pre-emphasis-20261124-order-probe-regression/manifest.json)・[全体監査](runs/plan-completion-v9-open-o-lpc-orders-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。固定LF実験の `stats` と、上流の放射差分の更新を開く。研究ワークスペースで `jq '{lf_minus_coupled_relative_ac_rms,checks}' runs/fixed-lf-glottal-flow-20261121-b/summary.json` を実行する。保存した固定 /ɑ/ の通常の圧力結合・固定LFの同じ22周期で、口端流量の電力差と放射差分の倍音ごとの増幅、および壁の寄与を照合するケースを事前登録する。 [固定LFの比較](notes/fixed-lf-glottal-flow.md#結果)・[既存の倍音集計](tools/measure_fixed_lf.py#L198)

## 固定 /ɑ/ のLF駆動で口端流量と総放射の差を倍音に分ける（2026-11-24）

- 完了した項目。通常発声と固定LFの上流・研究版PCMを各28,800フレームで保存波形と照合した。22周期で壁、口端、鼻端、放射差分を直接採取し、独立計算で全ビンの交流平均二乗を再現した。口端流量は基本波の増加で高次成分の減少が和らぎ、RMS低下は2.85%。差分後は第6・第7倍音が口端成分の減少の62.24%を占め、口端差分の自己項が総放射の減少の94.85%だった。 [事前登録](cases/fixed-lf-radiation-harmonic-budget.json)・[読解と測定](notes/fixed-lf-radiation-harmonic-budget.md)
- 未達の条件。旧5%判定は実測の口端流量に対して不合格のまま。660 Hzと770 Hzで、声門流量の変化と声道内での伝達の違いの寄与を個別に照合する工程が残る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIはユーザーの指定で後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各21判定に通過し、固定上流の声門・肺ポートの5試験も通過した。観測、計測差分、倍音ごとの平均二乗差、要約がバイト一致した。計画全体の第10版は115実行・247判定に通過し、3実行の903入力・20出力をSHA-256で照合した。RTL9210B-CGに21,390,734バイト保存した。 [初回](runs/fixed-lf-radiation-harmonic-budget-20261124-registered/manifest.json)・[再実行](runs/fixed-lf-radiation-harmonic-budget-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v10-lf-radiation-budget-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。固定LF実験の `stats` と、固定母音の上流・研究版の線形伝達を開く。研究ワークスペースで `jq '.stats | map_values(.lip_flow_cm3_s.over_glottal_flow[5:7])' runs/fixed-lf-glottal-flow-20261121-b/summary.json` を実行する。660 Hzと770 Hzで、通常発声・LF・同一姿勢の線形応答を複素数で照合するケースを登録する。 [既存の複素比](tools/measure_fixed_lf.py#L198)・[固定 /ɑ/ の線形伝達](cases/vowel-transfer-alpha.json)

## 固定 /ɑ/ の第6・第7倍音で声門入力と口端伝達を分ける（2026-11-24）

- 完了した項目。22周期の内部標本から、通常発声・固定LFの声門流量と口端流量をFFTと直接DFTで照合した。660 Hzの声門流量は66.14%、770 Hzは44.23%低下した。複素伝達比の変化は0.038%、0.171%。伝達比の項が口端流量の複素差に占める割合は0.016%、0.054%で、後退差分後の平均二乗差も声門入力の項がほぼ全てを説明した。同じ姿勢の線形応答を上流・研究版CLI・独立した節点連立計算で照合した。 [事前登録](cases/fixed-lf-harmonic-transfer.json)・[読解と計測](notes/fixed-lf-harmonic-transfer.md)
- 未達の条件。連続時間線形応答と有声の観測比には、振幅で最大0.28%、位相で最大0.093°の差が残った。全帯域の口端流量に関する旧5%判定は元の観測に対して不合格。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各22判定と固定上流の解析ゴールデン試験に通過した。要約と8成果がバイト一致し、第11版の全体監査は118実行・2,353成果・254判定に通過した。新しい3実行の925入力・32出力をSHA-256で照合し、そのうち成果40,738バイトをRTL9210B-CGに保存した。 [初回](runs/fixed-lf-harmonic-transfer-20261124-registered/manifest.json)・[再実行](runs/fixed-lf-harmonic-transfer-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v11-lf-harmonic-transfer-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.frequencies[] | {frequency_hz, continuous_linear_lip_transfer, observed_minus_linear_phase_deg}' runs/fixed-lf-harmonic-transfer-20261124-repeat/summary.json` を実行する。`render_fixed_airway` の単発流量と、`AirwayNetwork::step` の枝・壁・並列放射負荷の更新式を読む。同じ固定 /ɑ/ の零平均流で小入力を2振幅で入れるケースを登録し、口端応答を注入流量で割って両周波数の複素比と尾部の収束を測る。 [時間領域CLI](crates/vocal-cli/src/geometry_case.rs#L495)・[上流の枝と壁の更新](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1015)

## 固定 /ɑ/ の零流量まわりの離散応答を照合する（2026-11-24）

- 完了した項目。固定声道に2振幅のインパルスを入れ、両版の各57,600標本・12観測列を照合した。口端流量の初着は35番で、咽頭から口端までの枝数と一致した。660 Hzと770 Hzの口端の複素応答は離散節点計算と相対2.39×10⁻⁹以内で一致。連続時間との差は振幅で +0.0313%、−0.0436%、位相で −0.0071°、−0.0059°だった。2振幅を正規化した系列の初差は咽頭入口圧の標本1で、最初の枝の二次損失を含めて再現した。 [事前登録](cases/fixed-alpha-discrete-impulse.json)・[読解と結果](notes/fixed-alpha-discrete-impulse.md)
- 未達の条件。有声観測と離散応答の差は振幅で最大0.248%、位相で最大0.099°残る。平均流量を変えた条件でこの差を測る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。
- 最後に確認した実行。0.20秒の初回は尾部の打ち切りで3判定が不合格。旧判定を保存し、許容差を保って0.60秒に延長した。冒頭19,200標本と旧結果を照合し、研究ワークスペースと `/tmp` から各21判定・固定上流の2試験に通過した。要約と5成果がバイト一致し、全体監査の第12版は122実行・2,392成果・262判定に通過した。新しい4実行の1,071入力・39出力をSHA-256で照合し、そのうち成果33,003,913バイトをRTL9210B-CGに保存した。 [初回の不合格](runs/fixed-alpha-discrete-impulse-20261124-registered/manifest.json)・[延長](runs/fixed-alpha-discrete-impulse-20261124-extended/manifest.json)・[再実行](runs/fixed-alpha-discrete-impulse-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v12-discrete-alpha-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.frequencies[] | {frequency_hz, voiced_over_discrete}' runs/fixed-alpha-discrete-impulse-20261124-repeat/summary.json` を実行する。`prescribed_flow` の入口と上流の体積速度を指定する観測差分を読み、一定の声門流量を収束させた後に、同じ小入力を加える・加えない対照を登録する。平均流量ゼロと通常発声の平均流量を比較し、差波形から660 Hz・770 Hzの複素応答を求める。 [研究版の固定流量](crates/vocal-cli/src/geometry_case/voice.rs#L43)・[上流の固定流量](tools/measure_fixed_lf.py#L45)

## 固定 /ɑ/ の小信号応答を定常流の違いで比べる（2026-11-24）

- 完了した項目。固定気道CLIで定常流とインパルスの標本番号を指定できるようにした。零流量と有声時の平均139.88579 cm³/sで差波形を測り、両版の時系列と、枝抵抗 `R+2KQ` による離散計算を照合した。660 Hzと770 Hzの口端小信号振幅は0.0463%、0.1311%低下し、位相は −0.1169°、+0.0982°変化した。定常流の影響が最初に現れた咽頭入口圧は摂動の1標本後で、最初の枝の増分抵抗から再現した。 [事前登録](cases/fixed-alpha-mean-flow.json)・[読解と計測](notes/fixed-alpha-mean-flow.md)
- 未達の条件。定常流を有声時の平均に合わせると、保存した有声時の複素比への距離は1.10〜1.43倍に広がった。周期的な声門流量を与えたときの差を固定声道で測る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。
- 最後に確認した実行。両版の差波形を相対5.18×10⁻¹¹以内、離散計算による複素応答を相対4.31×10⁻⁷以内で照合した。研究ワークスペースと `/tmp` から各39判定と固定上流の狭窄試験に通過し、要約と6成果がバイト一致した。第13版の全体監査は125実行・2,420成果・268判定に通過。3実行の960入力・28出力をSHA-256で照合し、圧縮時系列の重複を統合したRTL9210B-CGの成果の実体は14,321,186バイトだった。 [初回](runs/fixed-alpha-mean-flow-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-mean-flow-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v13-alpha-mean-flow-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.frequencies[] | {frequency_hz, voiced_residual}' runs/fixed-alpha-mean-flow-20261124-repeat/summary.json` を実行する。固定流量入力の入口と固定気道CLIを読み、保存した声門流量の周期列を同じ平均値の定常流と比較する。線形予測からの差が最初に見える位置を、咽頭入口、喉の節点、口端の順に調べる。 [現在の入力](crates/vocal-cli/src/geometry_case.rs#L505)・[保存した流量の再入力](tools/measure_fixed_lf.py#L45)

## 固定 /ɑ/ に保存した声門流量の周期成分を再入力する（2026-11-24）

- 完了した項目。固定気道CLIに周期流量の入力を追加し、定常流・22周期を反復する入力・0.60秒全履歴の入力を固定上流と研究版で比較した。全履歴の入力では固定上流の咽頭入口圧、口端流量、鼻端流量、総放射が元の通常発声・固定LFの全57,600標本とビット一致した。22周期の反復でも660 Hzと770 Hzの口端複素比は相対1.76×10⁻⁸以内で再現した。定常点の線形予測と両周波数の複素比には0.209〜0.373%の差があった。 [事前登録](cases/fixed-alpha-periodic-flow.json)・[読解と結果](notes/fixed-alpha-periodic-flow.md)
- 未達の条件。周期入力時に生じた応答と定常点を線形化した予測の差を、枝ごとの圧力損失に分ける。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。
- 最後に確認した実行。初回は計測スクリプトの一時領域を開く処理で停止した。処理を直した後は研究ワークスペースと `/tmp` から各25判定と固定上流の狭窄試験に通過した。要約と7成果がバイト一致し、第14版の全体監査は128実行・2,450成果・275判定に通過した。初回を含む4実行の1,101入力・34出力をSHA-256で照合し、重複をまとめたRTL9210B-CG上の成果の実体は31,369,990バイトだった。 [初回の停止](runs/fixed-alpha-periodic-flow-20261124-registered/manifest.json)・[修正後](runs/fixed-alpha-periodic-flow-20261124-verified/manifest.json)・[再実行](runs/fixed-alpha-periodic-flow-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v14-alpha-periodic-flow-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions | map_values([.frequencies[] | {frequency_hz, periodic_over_linear_at_mean}])' runs/fixed-alpha-periodic-flow-20261124-repeat/summary.json` を実行する。枝の向きに応じた二次損失係数と、線形節点計算での枝の入力位置を確認する。660 Hz・770 Hzで定常点からの非線形な圧力差を枝ごとに取り出し、口端流量への寄与の和を今回の線形予測との差に照合する。 [上流の枝流量](../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L952)・[現在の離散線形予測](tools/measure_fixed_alpha_periodic_flow.py#L133)

## 固定 /ɑ/ の口端応答の差を枝ごとの二次損失に分ける（2026-11-24）

- 完了した項目。最後の22周期とその直前1標本で、全節点の圧力と枝流量を採取した。咽頭入口につながる38枝の二次損失から、定常点での値と傾きを引いた圧力差を求めた。各枝の寄与の複素和は、線形予測と口端実測の差を相対3.83×10⁻¹¹以内で再構成した。咽頭の口側の3枝（節点25→26、26→27、27→28）の合計は、差の方向への射影で46.3〜48.2%。梨状窩への3枝の複素和は差の大きさに対して0.079%未満だった。 [事前登録](cases/fixed-alpha-branch-loss.json)・[読解と結果](notes/fixed-alpha-branch-loss.md)
- 未達の条件。枝の寄与は観測した流量から分解した値。実際に枝の二次損失を変えた際の他の枝の流量と口端応答の変化を次に測る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。
- 最後に確認した実行。初回は両版の枝番号をそのまま比較して8判定が不合格だった。向き付きの両端で5枝の対応を取り直し、初回と生の観測がビット一致したまま、同じ閾値で各42判定と上流の狭窄試験に通過した。別ディレクトリから要約と6成果がバイト一致し、第15版の全体監査は132実行・2,487成果・283判定に通過した。4実行の1,127入力・37出力をSHA-256で照合し、重複を一つにまとめたRTL9210B-CG上の成果は53,439,065バイトだった。 [初回の不合格](runs/fixed-alpha-branch-loss-20261124-registered/manifest.json)・[対応付け後](runs/fixed-alpha-branch-loss-20261124-aligned/manifest.json)・[再実行](runs/fixed-alpha-branch-loss-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v15-alpha-branch-loss-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions | map_values(.strongest_branches)' runs/fixed-alpha-branch-loss-20261124-repeat/summary.json` を実行する。上流の枝流量の二次方程式と、研究版の `Branch::step` を読む。最も寄与した節点26→27の1枝、次に節点25→28の3枝を対象に、二次損失の定常点での値・傾きを保つ接線に置き換えた対照を登録する。 [研究版の枝更新](crates/vocal-core/src/airway/network.rs#L189)・[枝ごとの複素寄与](runs/fixed-alpha-branch-loss-20261124-repeat/artifacts/branch-contributions.csv)

## 固定 /ɑ/ の咽頭で1枝・3枝の二次損失を接線に替える（2026-11-24）

- 完了した項目。固定上流と研究版の隔離ビルドで、標本76,800から1枝または3枝の二次損失を定常点での値と傾きが等しい接線に替えた。660 Hz・770 Hzの口端応答と線形予測との差は、1枝で18.29〜19.05%、3枝で46.33〜48.21%減った。対象枝の前回の寄与だけを引いた予測は実測変化と最大0.165%の差。未選択枝の残差の変化を加えると相対5.68×10⁻¹²以内で再構成できた。 [事前登録](cases/fixed-alpha-loss-tangent.json)・[読解と計測](notes/fixed-alpha-loss-tangent.md)
- 未達の条件。接線では低い正方向流量で瞬間の損失仕事率が負になる区間があった。定常点での値と傾きを保ったままその区間をなくした対照で、口端応答への影響を測る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。
- 最後に確認した実行。差分挿入位置と組み込み辞書の依存を修正した。初回の定常流対照の2不合格は、ほぼゼロの信号ピークを基準にして生じた。定常入口圧と基準流量に基づく正規化に改訂し、初回の生観測と判定を保存した。別ディレクトリからの再実行も含め各57判定と上流の狭窄試験に通過し、要約と6成果が一致。第16版の全体監査は136実行・2,520成果・291判定に通過した。6実行の1,428入力・41出力をSHA-256で照合し、圧縮観測を重複統合したRTL9210B-CG上の成果の実体は100,022,961バイトだった。 [初回の定常流判定](runs/fixed-alpha-loss-tangent-20261124-rebuilt/manifest.json)・[改訂後](runs/fixed-alpha-loss-tangent-20261124-dc-scaled/manifest.json)・[再実行](runs/fixed-alpha-loss-tangent-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v16-alpha-loss-tangent-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions | map_values(map_values(.candidate.frequencies))' runs/fixed-alpha-loss-tangent-20261124-repeat/summary.json` を実行する。隔離差分と枝更新式を読む。順方向で接線の負の部分をゼロにし、逆方向では元の二次損失を維持する1枝・3枝の対照を事前登録して、同じ流量で口端応答を再描画する。 [隔離差分の作成](tools/measure_fixed_alpha_loss_tangent.py#L58)・[低流量域の観測](notes/fixed-alpha-loss-tangent.md#再描画した口端応答)

## 固定 /ɑ/ の接線を受動化して口端応答を照合する（2026-11-24）

- 完了した項目。順方向の接線の負の圧力差をゼロにし、逆方向は元の二次損失を使った。両版・両入力・1枝と3枝の対照で、切替直後と末尾22周期に丸め許容差を超える負の仕事率は0標本だった。定常流対照の波形は接線時とビット一致した。口端応答と定常点の線形予測との差は、1枝で4.92〜14.41%、3枝で12.48〜36.51%減った。接線時の流量に受動式を適用した圧力差と、選択・未選択枝の流量の変化で、接線時からの複素差を相対6.49×10⁻¹²以内で再構成した。 [事前登録](cases/fixed-alpha-loss-passive.json)・[読解と計測](notes/fixed-alpha-loss-passive.md)
- 未達の条件。今回の式では定常点より低い順流域も一部変わる。定常点以下で元の二次損失を使い、高流量側だけを変えた場合の寄与を測る。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDIは後日に回す。
- 最後に確認した実行。固定上流の狭窄試験と、研究ワークスペース・`/tmp` からの各64判定に通過し、要約と6成果がバイト一致した。第17版の全体監査は139実行・2,544成果・297判定に通過。3実行の1,021入力・24出力をSHA-256で照合し、圧縮観測の重複をまとめたRTL9210B-CG上の成果の実体は99,996,412バイトだった。 [初回](runs/fixed-alpha-loss-passive-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-loss-passive-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v17-alpha-loss-passive-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions | map_values(map_values(.candidate.frequencies))' runs/fixed-alpha-loss-passive-20261124-repeat/summary.json` を実行する。枝更新の駆動項と定常点の接線を読み、定常点以下の順流・逆流は元の二次損失、定常点を超える順流だけは接線とする対照を登録する。660 Hzと770 Hzについて、接線を使う範囲だけを変えたときの口端応答と仕事率を測る。 [隔離ビルドの枝更新](tools/measure_fixed_alpha_loss_tangent.py#L58)・[圧力差の成分分解](tools/measure_fixed_alpha_loss_passive.py#L56)

## 固定 /ɑ/ の定常点を超える順流だけを接線に替える（2026-11-24）

- 完了した項目。固定上流と研究版の隔離ビルドで同じ1枝・3枝を再描画した。660 Hz・770 Hzの口端応答と線形予測との複素距離は、無変更時から1枝で3.56〜11.66%、3枝で4.43〜29.45%減少した。前回の受動化と比較すると、通常発声の770 Hzでは定常点以下の変更が線形予測との距離を増やした。選択枝の負の仕事率は0標本、両版の時系列は相対1.96×10⁻¹⁴以内、両対照との差は独立した離散計算で相対3.75×10⁻¹¹以内まで照合した。 [事前登録](cases/fixed-alpha-loss-high-flow.json)・[読解と条件別の結果](notes/fixed-alpha-loss-high-flow.md)
- 未達の条件。低流量側単独の効果と、高流量側と同時に変更した際の相互作用は未計測。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。増分抵抗を独立計算で二重に数えた初回2実行の不合格16判定ずつを保存した。残差の算出を修正し、閾値と生観測を保ったまま各72判定を通過。別ディレクトリからの要約と6成果はバイト一致した。第18版の全体監査は144実行・2,586成果・306判定に通過した。5実行の1,335入力・42出力をSHA-256で照合し、重複統合後のRTL9210B-CG上の成果の実体は100,023,990バイトだった。 [初回の不合格](runs/fixed-alpha-loss-high-flow-20261124-registered/manifest.json)・[修正後](runs/fixed-alpha-loss-high-flow-20261124-residual/manifest.json)・[再実行](runs/fixed-alpha-loss-high-flow-20261124-residual-repeat/manifest.json)・[全体監査](runs/plan-completion-v18-alpha-loss-high-flow-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions | map_values(map_values(.candidate.frequencies))' runs/fixed-alpha-loss-high-flow-20261124-residual-repeat/summary.json` を実行する。高流量側を元の二次損失に戻し、定常点以下の順流だけに前回の受動式を使う対照を登録する。無変更からの低流量側と高流量側それぞれの複素変化を足し、両側を同時に変えた前回の観測と照合する。 [枝の切替](tools/measure_fixed_alpha_loss_tangent.py#L58)・[両対照での複素差](tools/measure_fixed_alpha_loss_high_flow.py#L78)

## 固定 /ɑ/ の低流量側の効果と高流量側との相互作用を測る（2026-11-24）

- 完了した項目。定常点以下の順流だけを受動式に替えて、通常発声と固定LF、1枝と3枝、660 Hzと770 Hzを比較した。通常発声の770 Hzで低流量側の効果が高流量側の効果を弱め、残る6条件では強めた。個別効果の複素和と同時変更との差は0.00428〜0.02399%。4条件の枝の圧力残差から、同時変更の複素差に対して相対1.14×10⁻¹¹以内で再構成した。丸め許容差を超える負の仕事率は0標本だった。 [事前登録](cases/fixed-alpha-loss-low-flow.json)・[読解と実測](notes/fixed-alpha-loss-low-flow.md)
- 未達の条件。固定LFで口端流量が旧目標の5%以上減るという判定は、元の描画では不合格。口端の基本波を置換する計算上の対照では6.40%減り、声門入力を変更して再描画した場合は未計測。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各70判定と固定上流の狭窄試験を通過し、要約と6成果はバイト一致した。第19版の全体監査は147実行・2,610成果・312判定に通過。新しい3実行の1,065入力・24出力をSHA-256で照合し、重複統合後のRTL9210B-CG上の成果の実体は99,997,735バイトだった。 [初回](runs/fixed-alpha-loss-low-flow-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-loss-low-flow-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v19-alpha-loss-low-flow-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '17,32p' notes/fixed-lf-radiation-harmonic-budget.md` と `sed -n '53,100p' tools/measure_fixed_alpha_periodic_flow.py` を実行する。元の二次損失で固定 /ɑ/ を使い、固定LFの再入力の基本波110 Hzだけを通常発声と同じ複素係数にする対照を事前登録する。平均と他の入力倍音を保って再描画し、全帯域の口端交流RMSと660 Hz・770 Hzへの波及を測る。 [口端での基本波置換](notes/fixed-lf-radiation-harmonic-budget.md#観測結果)・[周期入力の構成](tools/measure_fixed_alpha_periodic_flow.py#L53)

## 固定LFの声門流量の110 Hzを通常発声と揃える（2026-11-24）

- 完了した項目。固定 /ɑ/ の通常発声と固定LFの周期再入力を再現した。固定LFの声門流量の110 Hzだけを通常発声に合わせると、口端流量の交流RMS低下は通常発声比2.853%から6.394%になった。口端の基本波のみを直接置換した予測との差は0.00537パーセントポイント。入力係数を維持した660 Hzと770 Hzでも、口端係数に0.0202%と0.0233%の複素差が現れた。最初の差は咽頭入口圧で切替標本、口端流量で35標本後だった。 [事前登録](cases/fixed-alpha-lf-fundamental.json)・[読解と計測](notes/fixed-alpha-lf-fundamental.md)
- 未達の条件。元の固定LFの口端交流RMS低下は5%判定に未達。5%以上の低下は基本波を合わせた対照で確認した。660 Hzと770 Hzの差が最初に生じた枝と、各枝の圧力損失の寄与は未計測。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各22判定と固定上流の狭窄試験に通過し、要約と5成果はバイト一致した。第20版の全体監査は150実行・2,636成果・318判定に通過。新しい3実行の1,069入力・26出力をSHA-256で照合し、圧縮観測の重複をまとめたRTL9210B-CG上の成果の実体は16,613,115バイトだった。 [初回](runs/fixed-alpha-lf-fundamental-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-lf-fundamental-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v20-alpha-lf-fundamental-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions.candidate.frequencies' runs/fixed-alpha-lf-fundamental-20261124-repeat/summary.json` と `sed -n '86,124p;179,214p' tools/measure_fixed_alpha_branch_loss.py` を実行する。固定LFと基本波を合わせた対照の節点圧・枝流量を採取し、定常点からの圧力残差の差分を枝ごとに口端へ伝搬させるケースを事前登録する。入力係数が等しい660 Hzと770 Hzで、観測した複素差をどの枝が生んだか照合する。 [枝状態の採取](tools/measure_fixed_alpha_branch_loss.py#L86)・[離散節点計算](tools/measure_fixed_alpha_branch_loss.py#L179)

## 固定LFの基本波変更で生じた660 Hz・770 Hzの差を枝まで追う（2026-11-24）

- 完了した項目。固定LFと110 Hzだけを変更した入力を固定上流と研究版で再描画し、口端の660 Hz・770 Hzの複素差を枝の二次損失から相対1.05×10⁻¹¹以内で再構成した。咽頭3枝（節点25→28）の射影寄与は42.87%・49.09%。逆流補正の寄与は+5.48%・−6.69%だった。圧力と速度の観測から慣性・粘性を除いた損失でも口端差を再構成した。最初の圧力差は標本76,800の節点13、最初の枝流量と残差の差は76,801の節点13→14で確認した。 [事前登録](cases/fixed-alpha-lf-fundamental-branch-loss.json)・[式と観測結果](notes/fixed-alpha-lf-fundamental-branch-loss.md)
- 未達の条件。基本波の入力差の極性と大きさを変えた際の、高次倍音の振幅依存性は未計測。元の固定LFの5%判定は不合格として保持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合で、物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各20判定と固定上流の狭窄試験に通過し、要約と8成果がバイト一致した。第21版の全体監査は153実行・2,668成果・324判定に通過。新しい3実行の1,081入力・32出力をSHA-256で照合し、圧縮観測の重複をまとめたRTL9210B-CG上の成果の実体は53,882,152バイトだった。 [初回](runs/fixed-alpha-lf-fundamental-branch-loss-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-lf-fundamental-branch-loss-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v21-alpha-lf-fundamental-branches-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions.candidate.frequencies' runs/fixed-alpha-lf-fundamental-branch-loss-20261124-repeat/summary.json` と `sed -n '56,72p' tools/measure_fixed_alpha_lf_fundamental.py` を実行する。固定LFの同じ110 Hzの入力差を正負両向きと半振幅で与える対照を事前登録し、660 Hz・770 Hzの口端複素差が極性とともに反転する成分と、正負を平均しても残る成分を測る。 [110 Hz入力の組み立て](tools/measure_fixed_alpha_lf_fundamental.py#L56)・[今回の圧力成分](notes/fixed-alpha-lf-fundamental-branch-loss.md#実測)

## 固定LFの基本波変更の振幅を正負に振る（2026-11-24）

- 完了した項目。110 Hzだけを倍率±1・±0.5で変え、660 Hz・770 Hzの口端の奇成分と偶成分を求めた。全振幅で偶成分は奇成分の27.22%・30.23%。半振幅の奇成分を2倍しても全振幅の複素係数とは10.01%・15.71%ずれ、偶成分を4倍した差は46.33%・72.51%ずれた。3つの事前予想は両周波数で外れた。両版の時系列は相対2.03×10⁻¹⁴以内で、奇成分・偶成分の直接DFTとFFTの差は奇成分に対して相対1.98×10⁻¹²以内で一致した。 [事前登録](cases/fixed-alpha-lf-fundamental-amplitude.json)・[読解と実測](notes/fixed-alpha-lf-fundamental-amplitude.md)
- 未達の条件。比例と二次の予測からずれた成分を、枝の圧力残差や逆流域の変化へ帰属させる計測は未実施。元の固定LFの5%判定は不合格として保持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合で、物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。初回2実行は負の全振幅の実行名を全履歴保存の指定として扱い、描画後の集計で停止した。保存区間を呼び出し時に明示するように直し、初回の生観測と修正後の切替直後・末尾2ブロックをビット照合した。修正後は研究ワークスペースと `/tmp` から各25判定に通過し、要約と7成果が一致。既存の周期・全履歴の再入力も要約と7成果が保存結果と一致した。第22版の全体監査は157実行・2,710成果・333判定に通過。完了した4実行の1,239入力・42出力と、停止した2実行の266保存入力・22出力をSHA-256で照合した。重複を統合したRTL9210B-CG上で、既存の観測を除く成果の実体は67,488,861バイトだった。 [初回の停止記録](runs/fixed-alpha-lf-fundamental-amplitude-20261124-registered/failure.json)・[修正後](runs/fixed-alpha-lf-fundamental-amplitude-20261124-windowed/manifest.json)・[再実行](runs/fixed-alpha-lf-fundamental-amplitude-20261124-windowed-repeat/manifest.json)・[全体監査](runs/plan-completion-v22-alpha-lf-fundamental-amplitude-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions.candidate.outputs.flow_lips' runs/fixed-alpha-lf-fundamental-amplitude-20261124-windowed-repeat/summary.json` と `sed -n '95,163p' tools/measure_fixed_alpha_lf_fundamental_branch_loss.py` を実行する。同じ5入力の末尾22周期について枝流量と節点圧を採取し、660 Hz・770 Hzの奇成分・偶成分を枝の圧力残差から再構成する。順流式と逆流補正の寄与に分け、半振幅での比例・二次からのずれがどちらに現れるか照合する。 [枝損失の分解](tools/measure_fixed_alpha_lf_fundamental_branch_loss.py#L95)・[今回の奇成分・偶成分](notes/fixed-alpha-lf-fundamental-amplitude.md#実測)

## 固定LFの振幅則からのずれを枝の損失で再構成する（2026-11-24）

- 完了した項目。固定 /ɑ/ の同じ5条件を固定上流と研究版で再描画した。660 Hz・770 Hzの口端の奇成分・偶成分と比例・二次からのずれを、枝の圧力損失の変化から相対1.19×10⁻¹⁰以内で再構成した。4つのずれの方向への射影では、条件間で流向が異なる標本の逆流補正が100.03〜100.10%を占めた。節点26→27、25→26の補正が枝別で上位2枝だった。 [事前登録](cases/fixed-alpha-lf-fundamental-amplitude-branch-loss.json)・[読解と実測](notes/fixed-alpha-lf-fundamental-amplitude-branch-loss.md)
- 未達の条件。上位枝のゼロ流量付近の損失を滑らかにした際の口端の変化は未計測。元の固定LFの5%判定は不合格として保持する。実録音F2の人手注釈とTSP・CSDの試聴回答は未照合で、物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各29判定と固定上流の狭窄試験に通過し、要約と14成果がバイト一致した。第23版の全体監査は160実行・2,754成果・339判定に通過。新しい3実行の1,139入力・44出力をSHA-256で照合し、重複をまとめたRTL9210B-CG上の成果の実体は132,818,955バイトだった。 [初回](runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v23-alpha-lf-fundamental-amplitude-branches-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions.candidate.frequency_contrasts[] | select(.contrast | endswith("_gap"))' runs/fixed-alpha-lf-fundamental-amplitude-branch-loss-20261124-repeat/summary.json` と `sed -n '189,209p' crates/vocal-core/src/airway/network.rs` を実行する。節点26→27・25→26の絶対流量60 cm³/s以内で圧力損失を滑らかにつなぎ、定常点と区間外の元の損失式を保つ対照を事前登録する。同じ5入力で口端のずれ、定常流、力学的な収支を測る。 [今回の比較結果](notes/fixed-alpha-lf-fundamental-amplitude-branch-loss.md#実測)・[既存のコアの枝更新](crates/vocal-core/src/airway/network.rs#L189)

## 固定 /ɑ/ の上位2枝でゼロ流量付近の損失を平滑化する（2026-11-24）

- 完了した項目。節点26→27・25→26の絶対流量60 cm³/s以内で損失をC²級でつなぐ対照を両版の隔離ビルドで描画した。振幅則からのずれは、770 Hzの偶成分で12.28%減り、660 Hzの奇・偶成分と770 Hzの奇成分で28.45%・4.77%・19.85%増えた。定常流対照はビット一致し、丸め許容差を超える負の仕事率は0標本だった。口端の変化は相対9.82×10⁻¹⁰以内で再構成し、流量が変わった分は振幅則からのずれの変化に対して最大0.166%だった。 [事前登録](cases/fixed-alpha-lf-fundamental-smoothed-branches.json)・[実測と幅の予測](notes/fixed-alpha-lf-fundamental-smoothed-branches.md)
- 未達の条件。幅30 cm³/sで固定流量から予測した770 Hz偶成分のずれの増加は未描画。元の固定LFの5%判定は不合格として保持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合で、物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各45判定、固定上流の狭窄試験に通過し、要約と6成果がバイト一致した。既存の4種類の隔離差分も保存値に一致した。第24版の全体監査は163実行・2,778成果・345判定に通過。新しい3実行の1,159入力・24出力をSHA-256で照合し、重複をまとめたRTL9210B-CG上の成果の実体は125,062,952バイトだった。 [初回](runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v24-alpha-lf-smoothed-branches-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.conditions.candidate.frequency_contrasts[] | select(.contrast | endswith("_gap"))' runs/fixed-alpha-lf-fundamental-smoothed-branches-20261124-repeat/summary.json` と `sed -n '50,74p' tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py` を実行する。幅30 cm³/sを事前登録し、同じ2枝・5入力で、770 Hzの偶成分のずれが無変更比で増えるという予測と、元の流量から求めた直接効果を再描画で照合する。 [幅の予測](notes/fixed-alpha-lf-fundamental-smoothed-branches.md#次の幅を決める予測)・[直接効果の計測](tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py#L74)

## 固定 /ɑ/ の上位2枝で平滑化幅を30 cm³/sに狭める（2026-11-24）

- 完了した項目。同じ2枝・5入力で幅30を描画した。無変更から見た偶成分の二次からのずれは、660 Hzで幅60の+4.77%から−0.78%、770 Hzで−12.28%から+7.92%に転じた。奇成分を含む4比較で固定流量の事前予測と最大0.020パーセントポイント差で一致。全幅の定常流観測はビット一致し、丸め許容差を超える負の仕事率は0標本。口端流量の変化は相対3.04×10⁻⁹以内で再構成した。 [事前登録](cases/fixed-alpha-lf-fundamental-smoothed-width-30.json)・[読解、実測、流量帯別の探索](notes/fixed-alpha-lf-fundamental-smoothed-width-30.md)
- 未達の条件。この幅依存性は固定 /ɑ/ で確認した。固定 /i/ での枝の寄与と、流量帯別に変更した際の挙動は未計測。元の固定LFの5%判定は不合格として保持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各57判定と固定上流の狭窄試験に通過し、要約と6成果はバイト一致した。第25版の全体監査は166実行・2,802成果・351判定に通過。新しい3実行の1,182入力・24出力をSHA-256で照合し、重複をまとめたRTL9210B-CG上の成果の実体は125,045,799バイトだった。 [初回](runs/fixed-alpha-lf-fundamental-smoothed-width-30-20261124-registered/manifest.json)・[再実行](runs/fixed-alpha-lf-fundamental-smoothed-width-30-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v25-alpha-lf-smoothed-width-30-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '{source_case,geometry_reference_run,measurement}' cases/fixed-voice-centerline-i.json` と `sed -n '95,172p' tools/measure_fixed_alpha_lf_fundamental_amplitude_branch_loss.py` を実行する。固定 /i/ に同じ5入力を与える対照を事前登録し、節点・枝を形状に対応させる。元の損失式で口端660 Hz・770 Hzの奇・偶成分のずれを再構成し、寄与が大きい枝と逆流補正の割合を固定 /ɑ/ と比較する。 [固定 /i/ の形状基準](cases/fixed-voice-centerline-i.json)・[枝の圧力損失の分解](tools/measure_fixed_alpha_lf_fundamental_amplitude_branch_loss.py#L95)

## 固定 /i/ に同じ声門流量を与えて枝損失を比較する（2026-11-24）

- 完了した項目。固定 /ɑ/ の5入力を固定 /i/ に与え、口端660 Hz・770 Hzの比例・二次からの複素差を枝損失から相対5.84×10⁻¹¹以内で再構成した。寄与上位3枝は4比較すべてで咽頭から口腔の34→35、35→36、33→34に移った。流向が条件間で分かれた標本の逆流補正は99.30〜99.92%。770 Hz偶成分のずれの大きさは /ɑ/ の20.43%だった。最初の差は標本76,800で節点13の圧力に、次の標本で枝13→14の流量と圧力残差に現れた。 [事前登録](cases/fixed-vowel-i-lf-branch-loss.json)・[読解と実測](notes/fixed-vowel-i-lf-branch-loss.md)
- 未達の条件。口腔上位枝を平滑化した効果は未計測。保存した /ɑ/ の固定LFの5%判定は引き続き不合格。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各26判定と上流の狭窄試験に通過。要約と15成果はバイト一致し、固定 /ɑ/ の要約と枝別CSVを再集計で再現した。第26版の全体監査は169実行・2,848成果・357判定に通過。新しい3実行の1,197入力・46出力をSHA-256で照合し、RTL9210B-CG上の重複統合後の出力の実体は128,293,528バイトだった。 [初回](runs/fixed-vowel-i-lf-branch-loss-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v26-fixed-vowel-i-lf-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.shape_comparison[] | [.frequency_hz,.contrast,.i.ranked_branches]' runs/fixed-vowel-i-lf-branch-loss-20261124-repeat/summary.json` と `sed -n '70,140p' tools/measure_fixed_alpha_lf_fundamental_smoothed_branches.py` を実行する。固定 /i/ の34→35・35→36を幅60 cm³/sで平滑化する対照を事前登録する。同じ5入力の元の流量を使って変化を予測し、再描画して口端の複素差と定常流を照合する。 [枝の位置と寄与](notes/fixed-vowel-i-lf-branch-loss.md#最も狭い位置と寄与の最大点)

## 固定 /i/ の口腔上位2枝を幅60 cm³/sで平滑化する（2026-11-24）

- 完了した項目。口腔の枝34→35・35→36を平滑化し、無変更比で660 Hzの奇・偶成分のずれは18.28%・26.28%増、770 Hzでは奇成分が17.15%減、偶成分が29.23%増だった。事前予測と全4比較の増減が一致。定常流の観測はビット一致し、負の仕事率は丸め許容差を超えなかった。口端の複素差を相対4.41×10⁻¹⁰以内で再構成した。 [事前登録](cases/fixed-vowel-i-lf-smoothed-branches.json)・[読解と実測](notes/fixed-vowel-i-lf-smoothed-branches.md)
- 未達の条件。660 Hz奇成分の再描画と固定流量予測の差0.259ポイントは事前の0.2ポイント基準を超えた。通常の固定 /i/ 発声での平滑化効果は未計測。元の固定LFの5%判定は不合格として保持する。実録音F2の人手注釈とTSP・CSDの試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各56判定と固定上流の狭窄試験に通過。要約と6成果がバイト一致し、固定 /ɑ/ の幅60・30でも保存した要約を再構成した。第27版の全体監査は172実行・2,872成果・363判定に通過。新しい3実行の1,238入力・24出力をSHA-256で照合し、重複をまとめたRTL9210B-CG上の成果の実体は125,197,323バイトだった。 [初回](runs/fixed-vowel-i-lf-smoothed-branches-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-lf-smoothed-branches-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v27-fixed-vowel-i-lf-smoothing-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '{posture,voice,fixed_airway}' cases/vowel-voice-i.json` と `sed -n '193,251p' crates/vocal-core/src/voice.rs` を実行する。通常の固定 /i/ 発声を無変更条件から再現し、同じ2枝が幅60 cm³/sに入る区間を数える。平滑化を適用する対照を事前登録し、口端流量、咽頭入口圧、声門流量、PCMの最初の差とその後の変化を観測する。 [固定 /i/ の発声ケース](cases/vowel-voice-i.json)・[通常発声のCLI](crates/vocal-cli/src/geometry_case.rs#L441)

## 声門と気道を結合した固定 /i/ で口腔2枝を平滑化する（2026-11-24）

- 完了した項目。通常の7.2 cmH₂O、110 Hzの固定 /i/ を無変更対照として再現した。幅60 cm³/sの平滑化で予測どおり38,400に局所差が出て、21標本後に咽頭入口圧、22標本後に声門流量が変化した。声門面積は全標本で一致し、切替後のフィルタ済み圧力差は発声ゲートの上限を上回った。PCMの差のRMSは無変更の0.00179%。両版の放射観測から全PCMを独立に再構成した。 [事前登録](cases/fixed-vowel-i-coupled-smoothing.json)・[読解、計測、圧力ゲート](notes/fixed-vowel-i-coupled-smoothing.md)
- 未達の条件。圧力ゲートが上限に達する前の肺圧での効果は未計測。固定流量の660 Hz奇成分の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各12判定と固定上流の狭窄・肺ポート試験に通過。要約と7成果はバイト一致した。第28版の全体監査は175実行・2,900成果・369判定に通過。新しい3実行の1,226入力・28出力をSHA-256で照合し、重複をまとめたRTL9210B-CG上の成果の実体は24,041,800バイトだった。 [初回](runs/fixed-vowel-i-coupled-smoothing-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-coupled-smoothing-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v28-fixed-vowel-i-coupled-smoothing-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '{voice,measurement}' cases/vowel-voice-i.json` と `sed -n '221,236p' crates/vocal-core/src/glottis.rs` を実行する。肺圧だけを下げた通常発声で、圧力ゲートの遷移域に入る区間を定める。同じ2枝を幅60 cm³/sで平滑化する比較を事前登録し、フィルタ後の声門上下圧差、声門面積、声門流量、PCMを両版で照合する。 [今回の圧力ゲートの観測](notes/fixed-vowel-i-coupled-smoothing.md#声門面積が同じまま流量が変わる理由)

## 低い肺圧の固定 /i/ で平滑化の効果を声門面積まで追う（2026-11-24）

- 完了した項目。肺圧だけを3.6 cmH₂Oに下げ、固定 /i/ の口腔2枝を幅60 cm³/sで平滑化した。切替後の全27,136標本が圧力ゲートの遷移域に入った。咽頭入口圧は切替21標本後、フィルタ後の圧力差は22標本後、有声度と面積は23標本後に分かれた。面積差は最大6.73×10⁻⁸ cm²で、圧力差から絶対5.00×10⁻¹⁶ cm²以内で再構成した。PCM差のRMSは無変更の0.000416%で、両版のPCM差は全フレームで一致した。 [事前登録](cases/fixed-vowel-i-low-pressure-smoothing.json)・[読解と実測](notes/fixed-vowel-i-low-pressure-smoothing.md)
- 未達の条件。PCMの差のうち声門面積の変化を介する割合は未計測。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各13判定と固定上流の狭窄・肺ポート試験に通過。要約と8成果はバイト一致し、7.2 cmH₂Oの既存要約も再集計に一致した。第29版の全体監査は178実行・2,930成果・375判定に通過。新しい3実行の1,253入力・30出力をSHA-256で照合し、RTL9210B-CG上の重複統合後の成果の実体は28,051,198バイトだった。 [初回](runs/fixed-vowel-i-low-pressure-smoothing-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-low-pressure-smoothing-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v29-fixed-vowel-i-low-pressure-smoothing-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '41,92p' tools/measure_glottal_feedback.py` と `jq '.results.upstream | {first_internal_sample,pressure_gate,first_pcm_frame}' runs/fixed-vowel-i-low-pressure-smoothing-20261124-repeat/summary.json` を実行する。3.6 cmH₂Oの平滑化を維持し、声門モデルに渡す圧力差だけを平滑化前の保存系列に置換する。気道が解く声門上下圧と枝流量を観測し、面積を介する作用が加わる場合のPCMと比較する。 [今回の比較と次の対照](notes/fixed-vowel-i-low-pressure-smoothing.md#実測)

## 固定 /i/ の平滑化で声門モデルに渡す圧力差だけを置換する（2026-11-24）

- 完了した項目。3.6 cmH₂Oの固定 /i/ で、口腔2枝の平滑化を維持しながら声門モデルの入力圧力差を無変更の値に置換した。声門面積は全65,536標本で無変更とビット一致し、実圧力差と声門流量は変化した。面積を介するPCM差は全PCM差のRMSの13.23%、全変化方向への射影は+3.06%。最初の全PCM差は置換の有無にかかわらずフレーム19,210。面積経由の差は独立計算で19,214、保存した32ビットPCMで19,325に最初に出た。 [事前登録](cases/fixed-vowel-i-pressure-replay.json)・[読解、実測、丸めの照合](notes/fixed-vowel-i-pressure-replay.md)
- 未達の条件。壁・口端・鼻端の放射を別々に直接観測した上でのPCMの内訳は未計測。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各27判定と固定上流の狭窄・肺ポート試験に通過。要約と10成果はバイト一致し、従来の7.2・3.6 cmH₂Oの要約も再集計で一致した。第30版の全体監査は181実行・2,964成果・381判定に通過。新しい3実行の1,278入力・34出力をSHA-256で照合し、RTL9210B-CG上の重複統合後の成果の実体は46,168,480バイトだった。 [初回](runs/fixed-vowel-i-pressure-replay-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pressure-replay-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v30-fixed-vowel-i-pressure-replay-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `jq '.pressure_replay.editions.upstream' runs/fixed-vowel-i-pressure-replay-20261124-repeat/summary.json` と `sed -n '1052,1078p;1135,1153p' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs` を実行する。3条件を保ち、壁・口端・鼻端の放射流量を独立に観測するケースを事前登録する。合算した放射の微分とPCMを再構成し、最初のPCM差と測定窓のRMSのうち各放射成分が担う分を比較する。 [今回のPCM比較](notes/fixed-vowel-i-pressure-replay.md#実測)

## 固定 /i/ の壁・口端・鼻端の放射をPCMまで分解する（2026-11-24）

- 完了した項目。3.6 cmH₂Oの固定 /i/ の3条件で、壁・口端・鼻端・合算の放射流量を直接採取した。通常の平滑化で壁は切替1標本後、口端は12標本後に変化した。保存PCMの最初の差は、3比較とも口端成分だけで再現した。全PCM差の方向への口端の寄与は95.73%、96.24%、88.18%。鼻端は全比較で変化しなかった。両版の6描画で合算流量と微分はビット一致し、成分別の出力差の合算は独立計算と絶対1.26×10⁻¹⁵以内で一致した。 [事前登録](cases/fixed-vowel-i-radiation-components.json)・[読解と実測](notes/fixed-vowel-i-radiation-components.md)
- 未達の条件。通常の固定発声CLIで総放射と各成分をまとめて出力する観測項目は未実装。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各54判定と固定上流の一様管・狭窄・肺ポート試験に通過した。要約と10成果がバイト一致した。第31版の全体監査は184実行・3,000成果・387判定に通過。新しい3実行の1,306入力・36出力をSHA-256で照合し、RTL9210B-CG上の重複統合後の成果の実体は55,182,993バイトだった。 [初回](runs/fixed-vowel-i-radiation-components-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-radiation-components-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v31-fixed-vowel-i-radiation-components-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '157,247p' crates/vocal-cli/src/geometry_case/voice.rs` と `jq '.radiation_components.output_reconstruction' runs/fixed-vowel-i-radiation-components-20261124-repeat/summary.json` を実行する。固定発声CLIの任意観測に壁・口端・鼻端と合算流量を加える比較を事前登録する。無変更の固定 /i/ を通常の入口で描画し、今回の隔離ビルドの流量・微分、出力クロック、PCMと照合する。 [観測とPCMの内訳](notes/fixed-vowel-i-radiation-components.md#実測)

## 固定発声CLIで放射成分を取得する（2026-11-24）

- 完了した項目。通常の固定発声CLIの `fixed_voice_probe.radiation_components` を有効にすると、`render` のCSVに壁と合算の放射流量が加わり、既存の口端・鼻端の列と合わせて取得できる。固定 /i/ の全65,536内部標本で4つの流量と放射微分が研究版の隔離観測にビット一致した。観測の有無、咽頭収支との併用、出力フレームと内部標本の対応を確認した。独立計算のPCMは全32,768フレームにビット一致した。固定上流との差は流量で相対5.20×10⁻¹⁵以内、PCMで絶対2.33×10⁻¹⁰以内。 [事前登録](cases/fixed-vowel-i-cli-radiation.json)・[読解・実測](notes/fixed-vowel-i-cli-radiation.md)
- 未達の条件。Wasm・ブラウザ側から同じ放射成分を取得する観測は未実装。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。初回は既存の咽頭収支の列数を検証側が6と見込んだため、列構成の1判定が落ちた。既存7列を列名で照合する修正後、研究ワークスペースと `/tmp` から各11判定に通過した。3回のケース、CSV、WAV、`inspect` 出力はバイト一致した。第32版の全体監査は188実行・3,090成果・395判定に通過した。新しい4実行の1,422入力・90出力をSHA-256で照合し、RTL9210B-CG上の86出力は重複統合後に77,491,787バイトだった。 [初回](runs/fixed-vowel-i-cli-radiation-20261124-registered/manifest.json)・[修正後](runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected/manifest.json)・[再実行](runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected-repeat/manifest.json)・[全体監査](runs/plan-completion-v32-fixed-vowel-i-cli-radiation-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'nose_flow_cm3_s|OBSERVATION_WORDS' crates/vocal-wasm/src/lib.rs` と `jq '.checks' runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected-repeat/summary.json` を実行する。Wasmから壁・口端・鼻端・合算を得る対照を事前登録し、既存の観測ABI、出力フレームの対応、PCMを通常CLIと照合する。 [Wasmの出力フレーム処理](crates/vocal-wasm/src/lib.rs#L976)・[CLIの比較結果](runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected-repeat/summary.json)

## 固定 /i/ のWasmとAudioWorkletで放射流量を取得する（2026-11-24）

- 完了した項目。既存ケースの `fixed_voice_probe.radiation_components` を有効にし、壁・口端・鼻端・合算の流量と微分をWasmとブラウザの通常の固定発声入口で取得した。全32,768フレームで通常CLIと放射・PCMがビット一致した。3種類のホスト分割と観測の有無で既存の観測とPCMは一致し、描画中のネイティブ割り当ては0件だった。固定上流との差は流量・微分で最大相対3.12×10⁻¹³、PCMで最大絶対2.33×10⁻¹⁰。 [事前登録](cases/fixed-vowel-i-wasm-radiation.json)・[読解と実測](notes/fixed-vowel-i-wasm-radiation.md)
- 未達の条件。固定母音画面から放射観測を選択し、曲線をPCMと同じ時刻で見る操作は未実装。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。Node.jsの型変換とブラウザの取得ハッシュ判定を修正し、元の判定を保存した。研究ワークスペースと `/tmp` の両方から各21判定に通過し、要約と19成果がバイト一致した。44.1 kHz英語発話の停止・再開と従来の48 kHz固定発声を現行Wasmで再照合した。第33版の全体監査は195実行・3,204成果・406判定に通過。今回の9実行の3,287入力・149出力をSHA-256で照合し、RTL9210B-CG上の出力は重複統合後に131,706,805バイトだった。 [描画の再実行](runs/fixed-vowel-i-wasm-radiation-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v33-fixed-vowel-i-wasm-radiation-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '1458,1487p' ../../../web/prototypes/chimera-research/src/main.tsx` と `jq '.captures.enabled.fields' runs/fixed-vowel-i-wasm-radiation-20261124-repeat/artifacts/browser.json` を実行する。固定母音画面で観測の有無を選び、放射系列とPCMを同じ出力フレーム番号で比較する操作を事前登録する。画面の保存結果を通常CLIと全フレームで照合する。 [固定母音の操作画面](../../../web/prototypes/chimera-research/src/main.tsx#L1458)

## 固定母音画面でPCMと放射を同じ時刻に表示する（2026-11-24）

- 完了した項目。既存の肺圧7.2 cmH₂Oの固定 /i/ で放射観測を選び、PCM・放射成分・放射微分を共通のカーソルで比較できるようにした。ChromiumとFirefoxで全区間と20 msの表示、キーボードとグラフによる選択、幅390 pxの表示を確認した。ダウンロードのWAVと放射5値は通常CLIの全32,768フレームと一致し、再実行ケースも同じ結果を出した。固定上流のPCMにもビット一致した。 [事前登録](cases/fixed-vowel-i-radiation-screen.json)・[読解と実測](notes/fixed-vowel-i-radiation-screen.md)
- 未達の条件。既存の閉じた口蓋帆の設定では鼻端流量が全点で0だった。開口条件での端別放射と固定上流の壁・合算流量は未照合。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各19判定に通過し、要約と24成果がバイト一致した。Chromiumのデスクトップ画像はグラフ枠の角8画素で最大1階調の差があったため、両画像を保存した。現行Webで44.1 kHzの英語発話の停止・再開30判定を再確認した。第34版の全体監査は199実行・3,286成果・413判定に通過。新しい4実行の1,922入力・82出力をSHA-256で照合し、RTL9210B-CG上の出力は重複統合後に45,279,008バイトだった。 [初回](runs/fixed-vowel-i-radiation-screen-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-radiation-screen-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v34-fixed-vowel-i-radiation-screen-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'velum_cm2|velum_port' crates/vocal-core/src/airway/human.rs` と `jq '.posture.velum_cm2' cases/vowel-voice-i.json` を実行する。肺圧と姿勢を揃え、口蓋帆の開口だけを変える対照を事前登録する。鼻端・口端・PCMの最初の差を通常CLIとWasmで測り、固定上流の共通観測に照合する。 [画面の固定入力](cases/vowel-voice-i.json)・[研究版の気道](crates/vocal-core/src/airway/human.rs)

## 固定 /i/ の口蓋帆を開いて放射を比べる（2026-11-24）

- 完了した項目。固定発声CLIに口蓋帆ポートの面積・流量・両端圧を観測する指定を追加した。口蓋帆の入力−0.15と0.30 cm²を比較し、35セルで初期断面積も変化した。ポート流量は標本31、鼻端流量は52、壁の放射は14、口端流量は48で差が生じた。PCMの最初の差はフレーム7。開条件の定常鼻端流量のRMSは71.09 cm³/s。ポートの圧力残差はピーク比3.37×10⁻¹⁴以内で、開閉両条件の全PCMが固定上流・通常CLI・Wasmでビット一致した。 [事前登録](cases/fixed-vowel-i-velum-radiation.json)・[読解と実測](notes/fixed-vowel-i-velum-radiation.md)
- 未達の条件。口蓋帆の開口と輪郭変形それぞれの作用は未分離。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。初回は検証側が `inspect` の入力側の表示を考慮しておらず、2判定が落ちた。修正後は研究ワークスペースと `/tmp` で各26判定と固定上流の鼻音化試験に通過した。初回を含む3実行は40成果でバイト一致し、修正後の要約も一致した。第35版の全体監査は203実行・3,427成果・421判定に通過。今回の4実行の1,572入力・141出力をSHA-256で照合し、RTL9210B-CG上の出力は重複統合後に94,833,364バイトだった。 [初回](runs/fixed-vowel-i-velum-radiation-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-radiation-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v35-fixed-vowel-i-velum-radiation-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `rg -n 'set_port_area|velum_port' crates/vocal-core/src/airway/{network,human}.rs` と `jq '.contrast.candidate.first_difference_internal_samples' runs/fixed-vowel-i-velum-radiation-20261124-repeat/summary.json` を実行する。閉条件の咽頭・口腔の輪郭を固定し、ポート面積だけを0.30 cm²にした対照を事前登録する。通常の開条件・閉条件と照合して、鼻端より早い壁放射の差と定常窓のPCM差を調べる。 [開閉の測定値](notes/fixed-vowel-i-velum-radiation.md#実測)

## 固定 /i/ で口蓋帆の輪郭とポート面積の作用を分ける（2026-11-24）

- 完了した項目。固定発声CLIに `fixed_voice_probe.velum_area_override_cm2` を加え、輪郭とポート面積の4条件を通常CLIと固定上流で比較した。ポートだけを開くと壁の初差は内部標本33、PCMはフレーム22。輪郭だけの変化で通常開閉の壁14、PCMフレーム7を再現し、通常開条件とフレーム0〜21がビット一致した。定常窓で輪郭により変わる開口効果のRMSは通常開閉差の23.16%。版間のPCM差はポートだけを開いた条件のフレーム20,437の1 ULPで、独立計算で丸めを再現した。 [事前登録](cases/fixed-vowel-i-velum-port-only.json)・[読解と実測](notes/fixed-vowel-i-velum-port-only.md)
- 未達の条件。輪郭により開口効果が変わる周波数帯について、線形伝達と結合した声門の寄与は未分離。固定流量の予測精度と元の固定LFの5%判定は従来の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` で各35判定と固定上流の鼻音化試験に通過し、要約と33成果がバイト一致した。第36版の全体監査は206実行・3,509成果・427判定に通過した。今回の3実行の1,468入力・82出力をSHA-256で照合し、RTL9210B-CG上の出力は重複統合後に106,972,805バイトだった。 [初回](runs/fixed-vowel-i-velum-port-only-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-port-only-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v36-fixed-vowel-i-velum-port-only-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '1,120p' crates/vocal-cli/src/geometry_case/transfer.rs` と `jq '.contrasts.candidate | {steady_pcm_rms,relative_pcm_interaction_rms}' runs/fixed-vowel-i-velum-port-only-20261124-repeat/summary.json` を実行する。通常開閉の非加算成分に目立った440 Hzと2,310 Hzを事前登録し、固定声道の線形伝達と通常発声の声門流量・端別放射の複素比を同じ4条件で照合する。 [分析する周波数の根拠](notes/fixed-vowel-i-velum-port-only.md#実測)

## 固定 /i/ の440 Hzと2,310 Hzで線形負荷と声門流量を照合する（2026-11-24）

- 完了した項目。口蓋帆の輪郭とポート面積の4条件で、通常CLI、固定上流、独立連立計算の連続時間伝達が相対1.19×10⁻¹³以内で一致した。離散時間のモデルは通常CLIの微小入力の総放射を相対1.20×10⁻⁶以内で再現した。2,310 Hzでは線形負荷と声門流量の各項が総差の約2.8倍で、相対位相159.38°のため打ち消し合った。 [事前登録](cases/fixed-vowel-i-velum-harmonic-transfer.json)・[読解と実測](notes/fixed-vowel-i-velum-harmonic-transfer.md)
- 未達の条件。通常発声の総放射複素比と微小信号の差に関する3%仮説は不成立だった。最大はポートのみ開いた2,310 Hzの1.90%で、差の方向への鼻端の射影は82.74%。二次損失の寄与は未分離。従来の固定流量予測精度と元の固定LFの5%判定を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` でそれぞれ19判定中18判定が成立し、同じ3%仮説が不成立だった。固定上流の一様管試験に通過し、要約と41成果はバイト一致。第37版の全体監査はこの不合格を照合し、209実行・3,619成果・433判定に通過した。今回の3実行の1,537入力・110出力をSHA-256で照合し、RTL9210B-CG上の出力は重複統合後に62,569,718バイトだった。 [初回](runs/fixed-vowel-i-velum-harmonic-transfer-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-harmonic-transfer-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v37-fixed-vowel-i-velum-harmonic-transfer-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '145,166p;189,205p' crates/vocal-core/src/airway/network.rs` と `jq '.conditions.port_only.response[] | select(.frequency_hz == 2310)' runs/fixed-vowel-i-velum-harmonic-transfer-20261124-repeat/summary.json` を実行する。ポートのみ開いた条件の定常窓で平均ポート流量を求め、流向別の二次損失をその平均まわりで線形化する対照を事前登録する。2,310 Hzの鼻端の振幅・位相の残差を無補正の離散モデルに照合する。 [測定した複素比](notes/fixed-vowel-i-velum-harmonic-transfer.md#実測)

## 固定 /i/ の平均ポート流量で2,310 Hzの鼻端を補正する（2026-11-24）

- 完了した項目。ポートだけを0.30 cm²開いた固定 /i/ の400〜500 msで、平均流量31.992 cm³/sを動作点に二次損失を線形化した。鼻端の複素相対誤差は1.030%から0.430%へ低下し、改善率58.28%は事前基準の10%を満たした。圧力収支と独立した圧力源計算を照合し、固定上流でも同じ判定を得た。 [事前登録](cases/fixed-vowel-i-velum-mean-flow-tangent.json)・[読解と実測](notes/fixed-vowel-i-velum-mean-flow-tangent.md)
- 未達の条件。観測したポート二次損失を戻す診断でも鼻端に0.268%の複素誤差があり、他の枝と窓端項の寄与は未測定。第37版の総放射の3%仮説は不成立の記録を保存した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの再計測で各10判定が通り、上流の定常狭窄試験も通過した。要約と6点のCLI出力がバイト一致した。第38版の全体監査は212実行・3,643成果・439判定に通過した。今回の3実行の1,529入力・24出力をSHA-256で照合し、RTL9210B-CG上の出力は重複統合後に21,178,507バイトだった。 [初回](runs/fixed-vowel-i-velum-mean-flow-tangent-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-mean-flow-tangent-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v38-fixed-vowel-i-velum-mean-flow-tangent-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '145,205p' crates/vocal-core/src/airway/network.rs` と `jq '.editions.candidate | {nose_residual_after_observed_port_loss, responses}' runs/fixed-vowel-i-velum-mean-flow-tangent-20261124-repeat/summary.json` を実行する。同じ固定 /i/ と同じ窓で口腔・鼻腔の固定枝の流量と両端圧を観測し、二次損失を鼻端の複素残差へ戻す対照を事前登録する。 [残差の測定値](notes/fixed-vowel-i-velum-mean-flow-tangent.md#実測)

## 固定 /i/ の口腔と鼻腔の枝損失で2,310 Hzの鼻端の残差を調べる（2026-11-24）

- 完了した項目。通常の固定発声CLIに、内部標本の指定範囲で全節点圧と枝流量を保存する観測を加えた。固定上流の枝は有向節点対で照合し、全系列でピーク相対差3.28×10⁻¹³以下だった。口腔17枝・鼻腔21枝の二次損失で、鼻端の複素誤差は0.268%から0.185%へ縮んだ。 [事前登録](cases/fixed-vowel-i-velum-oral-nasal-loss.json)・[読解と測定](notes/fixed-vowel-i-velum-oral-nasal-loss.md)
- 未達の条件。改善率30.78%で事前の50%仮説は不成立。口腔と鼻腔の各寄与の向きが異なり、測定対象の枝の窓端項では残る0.185%の誤差を説明できなかった。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。初回の枝番号による照合エラーを保存し、修正後は研究ワークスペースと `/tmp` の各実行で測定14判定が通り、50%仮説だけが不成立だった。2回の要約と10成果がバイト一致し、上流の定常狭窄試験も通過。第39版の全体監査は216実行・3,694成果・447判定に通過した。今回の1,711入力・51出力のSHA-256を照合し、RTL9210B-CG上の出力は重複統合後に50,909,366バイトだった。 [初回](runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v39-fixed-vowel-i-velum-oral-nasal-loss-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '145,162p' ../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs` と `jq '.editions.candidate | {nose_residual_after_all_tested_losses, nose_transfer_changes}' runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/summary.json` を実行する。同じ収録の咽頭内、咽頭口腔接続、梨状窩を対象に、残る鼻端の複素誤差への寄与を事前登録して測る。 [測定時系列](runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/artifacts/)

## 固定 /i/ の声門上61枝で2,310 Hzの鼻端の誤差を照合する（2026-11-24）

- 完了した項目。前回の通常CLI・固定上流の収録を使い、声門上の61枝の圧力収支を独立計算に照合した。咽頭内・咽頭口腔接続・梨状窩の二次損失を戻すと鼻端の複素相対誤差は1.85×10⁻³から2.59×10⁻⁸へ下がり、両版で事前基準の90%低下を満たした。前回の残差方向の96.94%は咽頭内が占めた。 [事前登録](cases/fixed-vowel-i-velum-supraglottal-loss.json)・[読解と実測](notes/fixed-vowel-i-velum-supraglottal-loss.md)
- 未達の条件。同じ発声で観測した枝流量を使う診断であり、平均流量による近似精度は未測定。枝の端点項まで戻した複素相対誤差は1.31×10⁻⁸で、節点・壁・放射の端点項は未評価。第39版の50%仮説は不成立の記録を維持する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの解析で各14判定が通り、要約がバイト一致。上流の `airway_adversarial` は6件すべて通過した。第40版の全体監査は219実行・3,706成果・453判定に通過した。今回の1,353入力・12出力のSHA-256を照合し、RTL9210B-CG上の追加出力は14,171バイトだった。 [初回](runs/fixed-vowel-i-velum-supraglottal-loss-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-supraglottal-loss-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v40-fixed-vowel-i-velum-supraglottal-loss-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '74,146p' tools/measure_fixed_vowel_i_velum_mean_flow_tangent.py` と `jq '.editions.candidate | {projection_onto_prior_residual, nose_relative_error}' runs/fixed-vowel-i-velum-supraglottal-loss-20261124-repeat/summary.json` を実行する。咽頭内17枝の同じ窓の平均流量を用いる接線抵抗を事前登録し、他の枝の今回の圧力源を保った対照で、鼻端の複素応答を照合する。 [咽頭内の観測](notes/fixed-vowel-i-velum-supraglottal-loss.md#実測)

## 固定 /i/ の咽頭17枝を平均流量で線形化する（2026-11-24）

- 完了した項目。咽頭内17枝で流向別の二次損失を平均流量まわりで線形化し、抵抗を直接加えた節点解と、枝の圧力源を帰還させた独立解を相対10⁻⁹以内で照合した。鼻端の複素誤差は、咽頭内損失を省いた0.180%から0.334%に増加した。逆流のない最大寄与枝22→23では、接線で近似できなかった損失が変動流量の二乗の2,310 Hz成分に一致し、110 Hzと2,200 Hzの組の寄与が最大だった。 [事前登録](cases/fixed-vowel-i-pharynx-mean-flow-tangent.json)・[読解と実測](notes/fixed-vowel-i-pharynx-mean-flow-tangent.md)
- 未達の条件。50%改善仮説は両版で不成立。少数の周波数対で咽頭全体の応答を近似できるかは未検証で、逆流のある枝では流向による係数の切り替えも調べる。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` で8件の照合が成立し、50%改善仮説だけが不成立だった。要約はバイト単位で一致し、固定上流の定常狭窄試験に通過した。第41版の全体監査は222実行・3,718成果・459判定に通過した。今回の1,369入力・12出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に13,214バイトだった。 [初回](runs/fixed-vowel-i-pharynx-mean-flow-tangent-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-mean-flow-tangent-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v41-fixed-vowel-i-pharynx-mean-flow-tangent-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '98,154p' tools/measure_fixed_vowel_i_pharynx_mean_flow_tangent.py` と `jq '.editions.candidate.branches[] | select(.nodes == [22,23])' runs/fixed-vowel-i-pharynx-mean-flow-tangent-20261124-repeat/summary.json` を実行する。110 Hzの倍音対の上位数組で2,310 Hzの二乗項を構成する対照を事前登録し、鼻端の複素誤差と、逆流がある枝の係数切替の影響を照合する。 [周波数対の観測](notes/fixed-vowel-i-pharynx-mean-flow-tangent.md#節点2223で差が生じる項)

## 固定 /i/ の咽頭17枝を3組の周波数対で近似する（2026-11-24）

- 完了した項目。枝22→23の前回観測から選んだ3組を咽頭17枝に共通に使い、2,310 Hzの鼻端の複素相対誤差は観測流量に接線抵抗を掛けた場合の0.335%から0.0392%へ下がった。両版で88.28%改善し、事前基準の50%を満たした。全周波数積と符号付き時系列から直接求めた圧力損失を照合した。 [事前登録](cases/fixed-vowel-i-pharynx-harmonic-pairs.json)・[読解と実測](notes/fixed-vowel-i-pharynx-harmonic-pairs.md)
- 未達の条件。17枝の圧力係数のL2相対誤差は56.46%。再構成波形は観測で逆流した5枝をすべて見落とし、別の9枝に逆流が現れた。同一の収録で周波数対を選定し評価したため、他の肺圧での精度は未検証。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` で各11判定が通過し、要約はバイト単位で一致した。固定上流の定常狭窄試験に通過した。第42版の全体監査は225実行・3,730成果・465判定に通過し、前回の平均流量による50%改善仮説の不成立も再現した。今回の1,385入力・12出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に13,160バイトだった。 [初回](runs/fixed-vowel-i-pharynx-harmonic-pairs-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-harmonic-pairs-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v42-fixed-vowel-i-pharynx-harmonic-pairs-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '37,61p' tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py` と `jq '.measurement | {pairs_hz, steady_window_internal_samples}' cases/fixed-vowel-i-pharynx-harmonic-pairs.json` を実行する。肺圧だけを7.2から5.76 cmH₂Oに変えた通常CLIと固定上流の収録を事前登録し、同じ周波数対を固定したまま鼻端誤差と逆流判定を照合する。 [比較条件と逆流の測定](notes/fixed-vowel-i-pharynx-harmonic-pairs.md#実測)

## 肺圧5.76 cmH₂Oの新規収録で同じ周波数対を照合する（2026-11-24）

- 完了した項目。固定 /i/ の肺圧だけを7.2から5.76 cmH₂Oに変更し、通常CLIと固定上流で全節点・全枝とPCMを収録した。両版の全32,768 PCM標本がビット一致し、平均声門流量は134.138から109.501 cm³/sに下がった。前回と同じ3組で2,310 Hzの鼻端誤差は0.268%から0.0241%へ下がり、事前の50%改善基準を両版で満たした。 [事前登録](cases/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure.json)・[読解と実測](notes/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure.md)
- 未達の条件。再構成波形は観測した4本の逆流枝を見落とし、別の5枝で逆流を過検出した。枝圧力のL2相対誤差は55.33%。2つの肺圧の固定 /i/ 以外での精度は未検証。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの実行で各18判定が通り、要約と10点の観測成果がバイト単位で一致した。上流の定常狭窄試験にも通過した。第43版の全体監査は228実行・3,766成果・471判定に通過した。今回の1,647入力・36出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に50,201,407バイトだった。 [初回](runs/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v43-fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '59,104p' tools/measure_fixed_vowel_i_pharynx_harmonic_pairs.py` と `jq '.editions.candidate.reversal_branch_detection' runs/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure-20261124-repeat/summary.json` を実行する。3組による二乗項を保ち、逆流を判定する波形だけに低次倍音を追加する対照を事前登録し、両肺圧で枝流向と鼻端の誤差を照合する。 [両版の逆流判定](notes/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure.md#実測)

## 逆流補正用の波形に第3〜第6倍音を加える（2026-11-24）

- 完了した項目。3組の圧力源を保ち、逆流用の波形に330、440、550、660 Hzだけを加えた。符号不一致は7.2 cmH₂Oで5,924から236標本、5.76 cmH₂Oで4,266から80標本に減り、逆流のある枝をそれぞれ5/5本と4/4本検出した。過検出枝は両肺圧で0。鼻端複素誤差の増加は0.51%と0.27%で、全事前基準を両版で満たした。 [事前登録](cases/fixed-vowel-i-pharynx-reversal-low-harmonics.json)・[読解と実測](notes/fixed-vowel-i-pharynx-reversal-low-harmonics.md)
- 未達の条件。逆流標本の見落としと過検出が各肺圧で残る。再構成には各枝の実測倍音を使っており、節点モデルが与える流量を入力とした場合は未検証。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。初回はNumPyの論理値のJSON変換で失敗し、実行記録を保存した。判定をPythonの論理値に変換した後、研究ワークスペースと `/tmp` で各16判定が通り、要約がバイト単位で一致した。固定上流の定常狭窄試験も通過した。第44版の全体監査は232実行・3,780成果・479判定に通過した。今回の1,492入力・14出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に13,737バイトだった。 [初回](runs/fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v44-fixed-vowel-i-pharynx-reversal-low-harmonics-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '117,162p' tools/measure_fixed_vowel_i_velum_harmonic_transfer.py` と `jq '.pressures | map_values(.candidate.sign_added_low_harmonics)' runs/fixed-vowel-i-pharynx-reversal-low-harmonics-20261124-repeat/summary.json` を実行する。各枝の平均流量を保ち、声門の流量を入力とする節点解で咽頭の10周波数の複素流量を求め、実測の倍音と逆流符号を両肺圧で照合する。 [基準の符号判定](notes/fixed-vowel-i-pharynx-reversal-low-harmonics.md#実測)

## 声門流量から咽頭の10周波数と逆流を求める（2026-11-24）

- 完了した項目。声門流量を咽頭入口へ注入する離散節点解で、平均流量まわりの接線抵抗を加えると、7.2と5.76 cmH₂Oの咽頭17枝×10周波数の複素流量誤差は0.1834%と0.1386%だった。逆流枝を全て検出し、符号不一致は215と69標本で、両版が事前基準を満たした。観測圧力と損失から直接求めた枝流量も全61枝で照合した。 [事前登録](cases/fixed-vowel-i-pharynx-from-glottal-flow.json)・[読解と実測](notes/fixed-vowel-i-pharynx-from-glottal-flow.md)
- 未達の条件。枝平均は観測入力に残り、接線抵抗の最大周波数誤差は両肺圧とも660 Hzに出た。逆流符号の標本単位の差は残っている。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` の実行で各15判定が通り、要約がバイト一致した。固定上流の `airway_adversarial` の6試験に通過した。第45版の全体監査は235実行・3,792成果・485判定に通過した。今回の1,448入力・12出力をSHA-256で照合し、RTL9210B-CGの追加出力は14,207バイトだった。 [初回](runs/fixed-vowel-i-pharynx-from-glottal-flow-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-from-glottal-flow-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v45-fixed-vowel-i-pharynx-from-glottal-flow-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '85,124p' tools/measure_fixed_vowel_i_pharynx_from_glottal_flow.py` と `jq '.pressures | map_values(.candidate.models.mean_flow_tangent.reversal)' runs/fixed-vowel-i-pharynx-from-glottal-flow-20261124-repeat/summary.json` を実行する。声門の平均流量から全声門上枝の定常流量を求める対照を事前登録し、実測の枝平均を使ったときと同じ10周波数・逆流判定を比較する。 [実測の枝平均を使った基準](notes/fixed-vowel-i-pharynx-from-glottal-flow.md#実測)

## 声門の平均流量から声門上の定常分流を求める（2026-11-24）

- 完了した項目。声門入口の平均流量を与え、口端・鼻端をゲージ圧0とした定常枝の方程式を解いた。経路圧力差と非線形節点の独立解が一致し、全61枝のL2相対誤差は7.2と5.76 cmH₂Oで2.71%と2.15%だった。その枝平均を使った10周波数の咽頭流量誤差は0.1736%と0.1328%。逆流した枝をすべて検出し、符号不一致は212と69標本だった。両肺圧で定常分流と10周波数・逆流の事前基準に到達した。 [事前登録](cases/fixed-vowel-i-pharynx-steady-flow.json)・[読解と実測](notes/fixed-vowel-i-pharynx-steady-flow.md)
- 未達の条件。鼻端平均流量が9.63%と7.45%過大。観測二次損失の時間平均を戻すと枝平均に相対1.12×10⁻¹⁰以内で一致した。次は予測した10周波数を使って、この平均損失を近似する。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` の両実行で各20判定が通り、要約がバイト単位で一致した。上流の定常狭窄試験も通過した。第46版の全体監査は238実行・3,804成果・491判定に通過した。今回の1,460入力・12出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に13,106バイトだった。 [初回](runs/fixed-vowel-i-pharynx-steady-flow-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-steady-flow-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v46-fixed-vowel-i-pharynx-steady-flow-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '94,128p' tools/measure_fixed_vowel_i_pharynx_steady_flow.py` と `jq '.pressures | map_values(.candidate | {oral_and_nasal_mean_flow_cm3_s,path_loss_difference_due_to_averaging_dyn_cm2})' runs/fixed-vowel-i-pharynx-steady-flow-20261124-repeat/summary.json` を実行する。予測した10周波数で再構成した流量から流向別の二次損失を平均し、定常の分流を補正する比較を事前登録する。 [鼻端分流の基準](notes/fixed-vowel-i-pharynx-steady-flow.md#実測)

## 予測した10周波数で二次損失の時間平均を求める（2026-11-24）

- 完了した項目。声門流量と形状から予測した10周波数で流向別の二次損失を時間平均した。鼻端平均流量の誤差は7.2 cmH₂Oで9.63%から0.157%、5.76 cmH₂Oで7.45%から0.0843%。全枝平均の誤差も両肺圧で98%以上減った。咽頭の10周波数と逆流の事前基準も両版で満たした。 [事前登録](cases/fixed-vowel-i-pharynx-averaged-loss.json)・[読解と実測](notes/fixed-vowel-i-pharynx-averaged-loss.md)
- 未達の条件。今回の比較は平均分流と枝流量で、二次損失の2,310 Hz成分を予測したときの鼻端放射を未照合。逆流符号の不一致は215と69標本残った。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの各20判定に通過し、要約がバイト単位で一致した。上流の定常狭窄試験にも通過した。第47版の全体監査は241実行・3,816成果・497判定に通過した。今回の1,474入力・12出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に13,142バイトだった。 [初回](runs/fixed-vowel-i-pharynx-averaged-loss-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-averaged-loss-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v47-fixed-vowel-i-pharynx-averaged-loss-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '58,116p' tools/measure_fixed_vowel_i_pharynx_averaged_loss.py` と `jq '.pressures | map_values(.candidate.mean_loss_path_correction_dyn_cm2)' runs/fixed-vowel-i-pharynx-averaged-loss-20261124-repeat/summary.json` を実行する。同じ予測枝流量の波形から流向別の二次損失を計算し、2,310 Hzの複素圧力源を離散節点解に戻して鼻端放射を照合する対照を事前登録する。 [予測波形と分流の基準](notes/fixed-vowel-i-pharynx-averaged-loss.md#実測)

## 予測した二次損失から2,310 Hzの鼻端放射を求める（2026-11-24）

- 完了した項目。声門流量と固定形状から予測した61枝の波形を使い、接線抵抗で計上済みの部分を除いた二次損失を節点解に戻した。鼻端の複素誤差は7.2と5.76 cmH₂Oで0.912%から0.241%、0.818%から0.199%に低下し、両版で事前基準を満たした。窓端項を含む観測損失対照は鼻端流量比を相対1.32×10⁻⁸以内で再現した。 [事前登録](cases/fixed-vowel-i-pharynx-predicted-radiation.json)・[読解と実測](notes/fixed-vowel-i-pharynx-predicted-radiation.md)
- 未達の条件。全枝の圧力源のL2相対誤差は23.38%と21.94%。元の粘性モデルへ圧力源を戻したとき、鼻端への残差が最も大きい枝は口蓋帆ポート30→49だった。範囲は固定 /i/ の2肺圧・2,310 Hz。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` の各19判定に通過し、要約はバイト単位で一致した。固定上流の `airway_adversarial` の6試験も通過した。第48版の全体監査は244実行・3,828成果・503判定に通過した。今回の1,490入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は14,243バイトだった。 [初回](runs/fixed-vowel-i-pharynx-predicted-radiation-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-pharynx-predicted-radiation-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v48-fixed-vowel-i-pharynx-predicted-radiation-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '58,122p' tools/measure_fixed_vowel_i_pharynx_predicted_radiation.py` と `jq '.pressures | map_values(.candidate | {largest_nose_contribution_error,nose_transfer_error_by_branch_group})' runs/fixed-vowel-i-pharynx-predicted-radiation-20261124-repeat/summary.json` を実行する。口蓋帆ポート30→49の観測流量を10周波数に限定した波形と全帯域の波形で二次損失を求め、予測波形との差と鼻端への寄与を両肺圧で比較する。 [残差の根拠](notes/fixed-vowel-i-pharynx-predicted-radiation.md#実測)

## 口蓋帆ポートの2,310 Hz損失残差を帯域と係数に分ける（2026-11-24）

- 完了した項目。固定 /i/ の口蓋帆ポート30→49で、平均流量、10周波数の係数、選択外の成分の影響を独立に比較した。選択外成分の影響は二次損失の残差方向に118.1%と110.9%を占め、同じ10周波数内の係数誤差が一部を相殺した。他の60枝を予測に固定してポートだけを全帯域の実測にすると、鼻端の複素誤差は7.2と5.76 cmH₂Oで0.247%から0.0373%、0.202%から0.0197%になった。 [事前登録](cases/fixed-vowel-i-velum-port-bandwidth.json)・[読解と実測](notes/fixed-vowel-i-velum-port-bandwidth.md)
- 未達の条件。測定は固定 /i/ の2肺圧と2,310 Hzに限った。残差に効く周波数の組合せと、観測なしで補正できる割合は未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` の各35判定に通過し、要約はバイト単位で一致した。固定上流の定常狭窄試験に通過し、第49版の全体監査の247実行・3,840成果・509判定もすべて通過した。3実行の1,508入力・12出力をSHA-256で照合した。RTL9210B-CGへの追加出力は重複統合後に13,124バイトだった。 [初回](runs/fixed-vowel-i-velum-port-bandwidth-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-port-bandwidth-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v49-fixed-vowel-i-velum-port-bandwidth-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '28,110p' tools/measure_fixed_vowel_i_velum_port_bandwidth.py` と `jq '.pressures | map_values(.candidate | {residual_projection_fraction,conditions})' runs/fixed-vowel-i-velum-port-bandwidth-20261124-repeat/summary.json` を実行する。第7〜18倍音（770〜1,980 Hz）をポートだけに追加し、実測から抽出した波形と声門流量から予測した波形で損失と鼻端放射を照合するケースを事前登録する。 [比較の根拠](notes/fixed-vowel-i-velum-port-bandwidth.md#次の比較)

## 口蓋帆ポートの第7〜18倍音で二次損失を補う（2026-11-24）

- 完了した項目。口蓋帆ポートに実測の第7〜18倍音を追加し、省いた周波数による損失差を両肺圧で91.96%と83.87%回復した。声門流量から予測した12成分を使うと、2,310 Hzの鼻端複素誤差が0.247%から0.0656%、0.202%から0.0442%に下がった。比較は他60枝の圧力源とポートの平均・既存10周波数を固定して行い、両版で事前基準に到達した。 [事前登録](cases/fixed-vowel-i-velum-port-middle-harmonics.json)・[読解と実測](notes/fixed-vowel-i-velum-port-middle-harmonics.md)
- 未達の条件。追加12成分の流量係数に10.00%と7.31%のL2相対誤差が残り、絶対差の上位2成分は770 Hzと1,320 Hzだった。固定 /i/ の2肺圧と固定開口で検証した。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` の各40判定に通過し、要約はバイト単位で一致した。固定上流の `airway_adversarial` の全6試験と、第50版の全体監査の250実行・3,852成果・515判定に通過した。3実行の1,524入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,649バイトだった。 [初回](runs/fixed-vowel-i-velum-port-middle-harmonics-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-port-middle-harmonics-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v50-fixed-vowel-i-velum-port-middle-harmonics-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '67,117p' tools/measure_fixed_vowel_i_pharynx_predicted_radiation.py` と `jq '.pressures | map_values(.candidate.middle_band.coefficients_cm3_s | map(select(.frequency_hz == 770 or .frequency_hz == 1320)))' runs/fixed-vowel-i-velum-port-middle-harmonics-20261124-repeat/summary.json` を実行する。この2成分の接線解へ予測した二次損失の圧力源を一度戻す対照を事前登録し、ポート流量と2,310 Hzの鼻端放射を比較する。 [次の比較](notes/fixed-vowel-i-velum-port-middle-harmonics.md#次の比較)

## 口蓋帆ポートの770 Hzと1,320 Hzを二次損失で補正する（2026-11-24）

- 完了した項目。各枝の二次圧力損失から接線抵抗に含まれる項を引き、770 Hzと1,320 Hzの接線解に一度戻した。口蓋帆ポートの2成分のL2相対誤差は7.2と5.76 cmH₂Oで95.7%と96.5%減り、50%基準を満たした。観測損失を使う対照は2成分の実測流量と相対6.44×10⁻⁸以内で一致した。 [事前登録](cases/fixed-vowel-i-velum-port-loss-feedback.json)・[読解と実測](notes/fixed-vowel-i-velum-port-loss-feedback.md)
- 未達の条件。ポートの2成分だけを差し替えた場合、2,310 Hzの鼻端誤差が10.5%と11.7%減り、事前の25%基準に届かなかった。観測損失対照でも減少率は11.0%と12.0%で、2成分の差し替えで説明できる範囲は限られた。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各56判定を実行し、鼻端の25%基準だけが偽だった。要約はバイト単位で一致し、固定上流の `airway_adversarial` の全6試験に通過した。第51版の全体監査は同じ不成立を復元し、253実行・3,864成果・521判定に通過した。1,540入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,595バイトだった。 [初回](runs/fixed-vowel-i-velum-port-loss-feedback-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-port-loss-feedback-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v51-fixed-vowel-i-velum-port-loss-feedback-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '128,154p' tools/measure_fixed_vowel_i_velum_port_loss_feedback.py` と `jq '.pressures | map_values(.candidate.conditions)' runs/fixed-vowel-i-velum-port-loss-feedback-20261124-repeat/summary.json` を実行する。第1〜22倍音の複素流量係数を変えたときの2,310 Hz損失の微分を求め、各成分を1つずつ実測に差し替えた場合の鼻端誤差と照合するケースを事前登録する。 [次の比較](notes/fixed-vowel-i-velum-port-loss-feedback.md#次の比較)

## 第1〜22倍音に対する口蓋帆ポートの損失感度を測る（2026-11-24）

- 完了した項目。各倍音を単独で実測に差し替えた2,310 Hzの二次損失変化を、微分で相対7.37%と2.05%の誤差で予測し、両肺圧・両版で10%基準を満たした。単独差し替えの最大改善は両肺圧で2,420 Hzで、鼻端誤差が21.34%と9.59%減った。損失の微分では基本周波数との差の項が支配した。 [事前登録](cases/fixed-vowel-i-velum-port-loss-sensitivity.json)・[読解と実測](notes/fixed-vowel-i-velum-port-loss-sensitivity.md)
- 未達の条件。7.2 cmH₂Oの射影順位で選んだ110 Hzと2,420 Hzの組は鼻端誤差を11.09%減らし、5.76 cmH₂Oでは28.27%増やした。25%基準は不成立。直交成分を含めた選択と実測差し替えを使わない補正は未検証。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。先行実行に保存した既知の不成立とハッシュを照合するように読込を修正した。研究ワークスペースと `/tmp` からの各44判定は、2成分の選択基準だけが偽で要約がバイト単位で一致した。固定上流の全6試験と、第52版の全体監査の256実行・3,876成果・527判定に通過した。1,556入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,649バイトだった。 [初回](runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v52-fixed-vowel-i-velum-port-loss-sensitivity-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '93,135p' tools/measure_fixed_vowel_i_velum_port_loss_sensitivity.py` と `jq '.pressures | map_values(.candidate | {reference_selected_pair_hz,combined_replacements})' runs/fixed-vowel-i-velum-port-loss-sensitivity-20261124-repeat/summary.json` を実行する。複素残差の大きさで2成分を選び、同じ組を5.76 cmH₂Oの有限差し替えで検証する対照を事前登録する。 [次の比較](notes/fixed-vowel-i-velum-port-loss-sensitivity.md#次の比較)

## 鼻端の複素残差で口蓋帆ポートの2倍音を選ぶ（2026-11-24）

- 完了した項目。7.2 cmH₂Oの再実装版で微分から予測した複素残差の絶対値を最小にする1,320 Hzと2,420 Hzの組を選んだ。実測係数への有限差し替えでも231組中の最良で、鼻端誤差が31.26%減った。選択を固定した5.76 cmH₂Oでは17.61%減り、両肺圧で2,420 Hz単独と前回の射影順位の組を上回った。 [事前登録](cases/fixed-vowel-i-velum-port-complex-pair.json)・[読解と実測](notes/fixed-vowel-i-velum-port-complex-pair.md)
- 未達の条件。5.76 cmH₂Oで最良の550 Hzと1,320 Hzも17.80%改善で、全231組が25%基準に届かなかった。検証は固定形状・固定平均の実測差し替え。予測損失だけで回復できる量、別の開口での改善は未確認。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの各52判定では5.76 cmH₂Oを含む25%基準だけが偽で、要約はバイト単位で一致した。固定上流の全6試験と第53版の全体監査の259実行・3,888成果・533判定に通過した。1,568入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,577バイトだった。 [初回](runs/fixed-vowel-i-velum-port-complex-pair-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-port-complex-pair-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v53-fixed-vowel-i-velum-port-complex-pair-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '45,75p' tools/measure_fixed_vowel_i_velum_port_loss_feedback.py` と `jq '.pressures | map_values(.candidate | {fixed_selected_pair,single_control})' runs/fixed-vowel-i-velum-port-complex-pair-20261124-repeat/summary.json` を実行する。1,320 Hzと2,420 Hzに予測二次損失の残差を一度戻し、ポート係数の実測差し替えで得た鼻端改善率と比べるケースを事前登録する。 [次の比較](notes/fixed-vowel-i-velum-port-complex-pair.md#次の比較)

## 選んだ1,320 Hzと2,420 Hzを予測二次損失で補正する（2026-11-24）

- 完了した項目。固定 /i/ の22倍音の予測から二次損失を求め、1,320 Hzと2,420 Hzの接線解に一度戻した。両肺圧・両版で流量50%減少と鼻端改善量80%回復の事前基準に達した。7.2と5.76 cmH₂Oで鼻端誤差は30.82%と19.85%減り、実測差し替えで得た改善量の98.58%と112.74%を回復した。共通計算を基準群と追加群の両方に対応させ、先行の770 Hzと1,320 Hzの全判定と要約を再現した。 [事前登録](cases/fixed-vowel-i-velum-port-selected-pair-feedback.json)・[読解と実測](notes/fixed-vowel-i-velum-port-selected-pair-feedback.md)
- 未達の条件。補正は固定 /i/・固定開口0.30 cm²で検証した。別開口で同じ2成分が有効か、別母音や開閉する場合に有効かは未確認。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの各60判定と上流の全6試験に通過し、両要約はバイト単位で一致した。第54版の全体監査は262実行・3,900成果・539判定に通過した。1,586入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,757バイトだった。 [初回](runs/fixed-vowel-i-velum-port-selected-pair-feedback-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-port-selected-pair-feedback-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v54-fixed-vowel-i-velum-port-selected-pair-feedback-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '41,64p' tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py` と `jq '.pressures | map_values(.candidate | {feedback_frequencies,conditions})' runs/fixed-vowel-i-velum-port-selected-pair-feedback-20261124-repeat/summary.json` を実行する。肺圧7.2 cmH₂Oと声道輪郭を固定して音響ポートだけを0.15 cm²にし、候補と固定上流の枝流量・圧力を収録する。1,320 Hzと2,420 Hzの補正を固定して比較するケースを事前登録する。 [次の比較](notes/fixed-vowel-i-velum-port-selected-pair-feedback.md#次の比較)

## 0.15 cm²の口蓋帆ポートで同じ2倍音を補正する（2026-11-24）

- 完了した項目。肺圧と輪郭を固定してポート面積だけを半分にした2版の収録を追加した。ポート平均流量は33.8%減り、粘性抵抗が2.828倍になった。1,320 Hzと2,420 Hzの予測補正で流量誤差が95.1%、鼻端誤差が3.31%減った。同じ2成分の実測差し替えの改善量の83.3%を回復し、全事前基準に達した。 [事前登録](cases/fixed-vowel-i-velum-narrow-port-feedback.json)・[読解と実測](notes/fixed-vowel-i-velum-narrow-port-feedback.md)
- 未達の条件。狭開口の鼻端誤差の大半は2成分だけでは残った。全帯域の観測ポート損失を使った事後対照では0.528%から0.0542%に低下した。狭開口で残るポート損失を平均、22倍音内の係数、選択外成分に分ける比較は未実施。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` から各38判定に通過し、要約と主要な収録成果はバイト単位で一致した。第55版の全体監査は265実行・3,956成果・545判定に通過した。1,855入力・56出力のSHA-256を照合し、19の重複出力を統合した。RTL9210B-CGの追加出力は統合後に51,800,343バイトだった。 [初回](runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v55-fixed-vowel-i-velum-narrow-port-feedback-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '35,101p' tools/measure_fixed_vowel_i_velum_port_bandwidth.py` と `jq '.editions | map_values({conditions,opening_change})' runs/fixed-vowel-i-velum-narrow-port-feedback-20261124-repeat/summary.json` を実行する。0.15 cm²の収録から予測の22倍音、実測平均、実測の22倍音、全帯域の実測を順に切り替え、2,310 Hzのポート圧力源への寄与を測る対照を事前登録する。 [次の比較](notes/fixed-vowel-i-velum-narrow-port-feedback.md#次の比較)

## 狭い口蓋帆ポートの損失残差を3要因に分ける（2026-11-24）

- 完了した項目。0.15 cm²で平均、22倍音内の係数、選択外成分を独立に実測へ置き換えた全8条件を照合した。差し替え順6通りの平均で2,310 Hzのポート損失残差への射影は−2.51%、96.21%、6.30%だった。22倍音内の係数だけで鼻端誤差が0.528%から0.115%、平均も替えると0.0778%へ低下した。 [事前登録](cases/fixed-vowel-i-velum-narrow-port-bandwidth.json)・[読解と実測](notes/fixed-vowel-i-velum-narrow-port-bandwidth.md)
- 未達の条件。選択外成分が残差の50%以上を説明する仮説は両版で不成立だった。今回の22倍音は実測差し替えで検証した。22成分すべてへ予測損失を戻してどこまで改善を再現できるかは未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの各24判定は、選択外の50%基準だけが偽で要約はバイト単位で一致した。固定上流の全6試験と、第56版の全体監査の268実行・3,968成果・551判定に通過した。1,641入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,649バイトだった。 [初回](runs/fixed-vowel-i-velum-narrow-port-bandwidth-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-narrow-port-bandwidth-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v56-fixed-vowel-i-velum-narrow-port-bandwidth-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '45,81p' tools/measure_fixed_vowel_i_velum_port_loss_feedback.py` と `jq '.editions | map_values({conditions,port_loss_residual_projection_fractions})' runs/fixed-vowel-i-velum-narrow-port-bandwidth-20261124-repeat/summary.json` を実行する。平均と他60枝の鼻端への圧力源を固定し、22倍音すべての接線解に予測二次損失を一度戻す。2成分補正と22成分の実測差し替えを対照にするケースを事前登録する。 [次の比較](notes/fixed-vowel-i-velum-narrow-port-bandwidth.md#次の比較)

## 狭い口蓋帆ポートの22倍音すべてを一度補正する（2026-11-24）

- 完了した項目。0.15 cm²で第1〜22倍音すべてに予測二次損失を一度戻すと、流量係数の誤差は91.15%、鼻端誤差は78.1538%減った。鼻端は0.52758%から0.11526%へ下がり、実測係数の差し替えによる改善量を99.9992%回復した。両版で流量と鼻端の事前基準を満たした。 [事前登録](cases/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback.json)・[読解と実測](notes/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback.md)
- 未達の条件。補正後にも残る鼻端誤差に対し、実測の第23〜44倍音を加える事後対照では0.00871%まで減った。第23〜44倍音の予測による改善は未測定。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの各157判定に通過し、要約はバイト単位で一致した。固定上流の全6試験と、第57版の全体監査の271実行・3,980成果・557判定に通過した。1,657入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,865バイトだった。 [初回](runs/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v57-fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '122,145p' tools/measure_fixed_vowel_i_pharynx_steady_flow.py` と `jq '.editions | map_values({conditions,feedback_frequencies})' runs/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback-20261124-repeat/summary.json` を実行する。補正済み第1〜22倍音と基準平均を固定し、第23〜44倍音を声門流量と形状から予測して加えた場合を、実測の同じ22倍音で得られた改善と照合するケースを事前登録する。 [次の比較](notes/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback.md#次の比較)

## 狭い口蓋帆ポートの第23〜44倍音を予測する（2026-11-24）

- 完了した項目。補正済み第1〜22倍音を固定して第23〜44倍音に予測損失を一度戻すと、上位倍音の流量係数のL2誤差は7.995%から0.333%に減った。鼻端誤差は低域だけの0.11526%から0.00861%に下がり、実測追加で得た改善量の100.09%を回復した。接線解でも鼻端誤差は0.00735%だったが、実測上位倍音を加えた対照に対する鼻端伝達の差は予測補正で約36分の1に縮まった。 [事前登録](cases/fixed-vowel-i-velum-narrow-port-upper-harmonics.json)・[読解と実測](notes/fixed-vowel-i-velum-narrow-port-upper-harmonics.md)
- 未達の条件。開口0.15 cm²、肺圧7.2 cmH₂O、固定 /i/、観測点2,310 Hzに限って検証した。鼻端評価ではポートの平均と他60枝の圧力源を固定した。開口0.30 cm²で同じ帯域の予測が有効かは未確認。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` からの各159判定と固定上流の全6試験に通過し、両要約はバイト単位で一致した。第58版の全体監査は274実行・3,992成果・563判定に通過した。1,673入力・12出力をSHA-256で照合し、RTL9210B-CGの追加出力は重複統合後に13,757バイトだった。 [初回](runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v58-fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '24,43p' tools/measure_fixed_vowel_i_velum_port_selected_pair_feedback.py` と `jq '.editions | map_values({conditions, hypotheses})' runs/fixed-vowel-i-velum-narrow-port-upper-harmonics-20261124-repeat/summary.json` を実行する。肺圧7.2 cmH₂Oの開口0.30 cm²の保存収録を使い、同じ第1〜22倍音と第23〜44倍音の補正を順に行う比較を事前登録する。 [次の比較](notes/fixed-vowel-i-velum-narrow-port-upper-harmonics.md#次の比較)

## 口蓋帆ポートを0.30 cm²に広げて第23〜44倍音を比較する（2026-11-24）

- 完了した項目。音響ポートの上書き面積だけが異なる保存収録を照合した。0.30 cm²で第1〜22倍音を補正し、その低域を固定して第23〜44倍音に予測損失を一度戻すと、追加帯域のポート流量係数のL2誤差は2.926%から0.02581%へ減った。予測上位倍音を足した鼻端伝達は、収録から抽出した上位倍音を足す対照と相対1.25×10⁻⁷以内で一致した。 [事前登録](cases/fixed-vowel-i-velum-wide-port-upper-harmonics.json)・[読解と実測](notes/fixed-vowel-i-velum-wide-port-upper-harmonics.md)
- 未達の条件。収録係数を足した対照でも鼻端誤差が0.03379%から0.03857%へ増え、80%回復の仮説は両版で不成立だった。ポートの平均と他60枝の基準圧力源を固定した結果で、他枝の損失を観測へ切り替えた場合は未検証。実録音F2の人手注釈とTSP・CSD試聴回答は未照合。物理MIDI鍵盤はユーザーの指示により後日に回す。
- 最後に確認した実行。研究ワークスペースと `/tmp` の各310判定で鼻端の80%回復だけが不成立となり、要約はバイト単位で一致した。固定上流の全6試験と、第59版の全体監査の277実行・4,004成果・569判定に通過した。1,655入力・12出力をSHA-256で照合し、RTL9210B-CGへの追加出力は重複統合後に13,721バイトだった。 [初回](runs/fixed-vowel-i-velum-wide-port-upper-harmonics-20261124-registered/manifest.json)・[再実行](runs/fixed-vowel-i-velum-wide-port-upper-harmonics-20261124-repeat/manifest.json)・[全体監査](runs/plan-completion-v59-fixed-vowel-i-velum-wide-port-upper-harmonics-20261124/manifest.json)
- 次に開くファイルと実行するコマンド。研究ワークスペースで `sed -n '109,134p' tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py` と `jq '.editions | map_values(.wide_nose_change)' runs/fixed-vowel-i-velum-wide-port-upper-harmonics-20261124-repeat/summary.json` を実行する。0.30 cm²でポート上位倍音の有無と他60枝の2,310 Hz圧力源の予測・観測を独立に切り替える4条件を事前登録する。 [次の比較](notes/fixed-vowel-i-velum-wide-port-upper-harmonics.md#次の比較)
