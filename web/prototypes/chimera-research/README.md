# CHIMERA 発声研究

固定母音 /i/ を AudioWorklet で生成し、試聴・WAV保存・観測JSONの保存ができます。実時間の発声では開始・停止や舌・唇を操作し、減衰まで保存できます。発話にはIPAや英語テキスト、歌唱には英語・韓国語・ロシア語・中国語の歌詞とMIDI番号・拍数を入力できます。中国語は漢字と声調付きピンインを受け付けます。入力はネイティブCLIと共通です。既定の出力は48 kHzモノラルで、WAVはIEEE浮動小数点です。[入力ケース](../../../research/experiments/chimera-rebuild/cases/vowel-voice-i.json)・[読解と検証結果](../../../research/experiments/chimera-rebuild/notes/worklet-fixed-voice.md)

## 起動

Rustの `wasm32-unknown-unknown` ターゲットとBun 1.4.4を使います。このディレクトリで実行します。

```bash
rustup target add wasm32-unknown-unknown
bun install --frozen-lockfile
bun run dev
```

Viteが表示したローカルURLで「固定母音 /i/ をレンダー」を押すとオフラインで合成します。「発声を開始」「発声を停止」で実時間の音声を採取できます。本番ビルドは `bun run build`、ローカル確認は `bun run preview` です。

「ビートボックス」では、記譜、テンポ、スウィングから1.3秒のビートをオフラインで合成します。観測間隔を切り替えて、休符を含む再生位置、声門と鼻端流量をWAV・観測JSONと照合できます。[ビート比較の条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-beatbox-pattern.md)

「実時間でビートを再生」では、指定した採取時間内にテンポ・スウィングを適用し、ビートを止めて再開できます。停止中の減衰も録り続けます。完了後はWAV、観測JSON、操作の適用フレームを含むCLI用の再実行ケースを保存できます。[実時間ビートの比較結果](../../../research/experiments/chimera-rebuild/notes/worklet-live-beatbox.md)

「鳴禽の持続音」では、48 kHzまたは96 kHzで、呼気の立ち上がりから停止後の減衰まで0.75秒のケースを再生します。加工前WAVと再実行ケースに加え、呼気・気嚢圧・左右の開口・実断面積・体積流量を観測JSONに保存できます。各観測点には出力フレームと内部サンプルの番号を併記します。[鳴禽の比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-songbird-sustain.md)

「鳴禽のコール」の「flute の途中停止を再生」は、48 kHzで移調したコールを開始し、途中で手動発声に切り替える登録ケースです。観測JSONでは、指示の前後でコール識別子、呼気目標と平滑値、9個の制御の目標と平滑値を確認できます。[コールの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-songbird-flute.md)

同じ「鳴禽のコール」の「再生ケース」で `trill` を選ぶと、48 kHzで18周期を自然終了まで再生します。観測JSONには64フレームごとの制御更新直後と開始指示の前後が入ります。[周期の比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-songbird-trill.md)・[Canary trillのMIDI比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-songbird-trill.md)

`trill` の観測対照では、制御区間の先頭・末尾、描画量子の末尾から観測位置を選べます。各条件の観測JSONには `renderCalls` として128フレーム量子内のWASM描画呼び出し回数も入ります。[観測位置と処理時間の比較](../../../research/experiments/chimera-rebuild/notes/worklet-songbird-trill-observation.md)

`chirps` は44.1 kHzで再生し、後半に重なるキーの呼気目標と音高目標を観測JSONで確認できます。比較スクリプトは宣言順と時刻順を試した二つのWAVを保存します。[キー順の比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-songbird-chirps.md)

`buzz` は96 kHzで8回の呼気パルスを再生します。観測JSONで呼気目標と平滑呼気を確認でき、比較スクリプトは最初と定常時の閾値通過間隔を出力します。[初回パルスの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-songbird-buzz.md)

「buzz → trill」は手動パラメータの設定、コールの切り替え、停止を含む48 kHzのケースです。観測JSONは通常の64フレーム刻みに加え、操作と制御境界の前後で識別子、目標、平滑値を保存します。[切り替えの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-songbird-switch.md)

「ウェッデルアザラシの持続音」では48 kHzまたは96 kHzで開始から停止後の減衰まで再生します。観測JSONには、呼気目標と肺圧、内部サンプルごとの壁面・口端・鼻端・総放射が入ります。WAVとCLI用の再実行ケースも保存できます。[アザラシの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-seal-sustain.md)

「ウェッデルアザラシの trill」では48 kHzの自然終了、44.1 kHzの途中停止、96 kHzの音高上限のケースを選べます。観測JSONで、コールの識別子、音高と呼気パラメータの目標・平滑値、固定肺圧を確認できます。[trillの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-seal-trill.md)・[Descending trillのMIDI比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-seal-trill.md)

「ウェッデルアザラシの zap」では48 kHzの公式デモの先頭、44.1 kHzの `trill → zap` の切り替え、96 kHzのパルス変調なしのケースを選べます。切り替え条件では、新しいキーを適用した制御区間の放射を内部サンプルごとに観測JSONへ保存します。[zapの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-seal-zap.md)

「ウェッデルアザラシの whistle」では48 kHzの公式デモの先頭、44.1 kHzの850 Hzへの移調と手動変更、96 kHzの単独コールを選べます。観測JSONに含まれる目標音高と平滑音高から、それぞれが最低になる時刻を比較できます。[whistleの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-seal-whistle.md)・[U whistleのMIDI比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-seal-whistle.md)

「ウェッデルアザラシの chug」では、48 kHzの公式デモ全体、44.1 kHzの120 Hzへの移調と手動操作、96 kHzの初期音高90 Hzのケースを選べます。観測JSONに声門位相・瞬時F0・開口面積・粗さを含みます。96 kHzのJSONは全108,000フレームの観測を保存します。[chugの比較条件と結果](../../../research/experiments/chimera-rebuild/notes/worklet-seal-chug.md)・[ChugのMIDI比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-seal-chug.md)

「アメリカアリゲーターの固定発声」では標準の開始・停止、口を広げた場合、鼻孔を最小にした場合、声門を開いた場合、無呼気を比較できます。観測JSONには、肺圧、声門面積・流量、鼻腔ポート、壁面・口端・鼻端の放射を含みます。[固定発声の比較と結果](../../../research/experiments/chimera-rebuild/notes/worklet-alligator-fixed-voice.md)

「MIDIでアメリカアリゲーターを演奏」では持続音と4種のコールを選べます。MIDI機器を接続して計測を開始し、演奏に使われた時刻・WAV・再実行ケースを保存できます。Hissを選ぶと観測JSONに声門・口腔乱流レベルと声門注入圧も入ります。[持続音の比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-alligator.md)・[Bellowの比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-alligator-call.md)・[Growlの比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-alligator-growl.md)・[Hissの比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-alligator-hiss.md)・[Water danceの比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-alligator-dance.md)

「アメリカアリゲーターの bellow」では公式デモ先頭、手動操作と途中停止、移調時の音高下限を比較できます。観測JSONにはコールID、制御時計、音高・粗さなどの目標と平滑値も含まれます。[bellowの比較と結果](../../../research/experiments/chimera-rebuild/notes/worklet-alligator-bellow.md)

「アメリカアリゲーターの growl」では公式デモ先頭、`bellow` からの切り替え、移調時の音高上限を比較できます。44.1 kHzの切り替えケースでは全フレームの目標と、内部2サンプルの声門・気道状態を保存します。[growlの比較と結果](../../../research/experiments/chimera-rebuild/notes/worklet-alligator-growl.md)

「アメリカアリゲーターの hiss」では公式デモ先頭、`growl` からの切り替え、96 kHzの単独コールを再生できます。観測JSONには声門・口腔の乱流レベルと声門の注入圧（dyn/cm²）も保存されます。[hissの比較と結果](../../../research/experiments/chimera-rebuild/notes/worklet-alligator-hiss.md)

「アメリカアリゲーターの dance」では公式デモ全体、`hiss` からの切り替え、96 kHzの単独コールを再生できます。コール開始から0.3〜0.9秒は全内部サンプルを保存し、声門・壁面・口端・鼻端とPCMの低域を比較できます。[danceの比較と結果](../../../research/experiments/chimera-rebuild/notes/worklet-alligator-dance.md)

「アフリカゾウの固定発声」では公式デモの固定発声、口から鼻への経路変更、口側を維持するケース、無呼気を再生できます。観測JSONに口先と軟口蓋の断面、鼻の基部・入口・先端の圧力、入口弁の流量、壁面・口端・鼻先の放射を保存します。[固定発声の比較と結果](../../../research/experiments/chimera-rebuild/notes/worklet-elephant-fixed-voice.md)

「MIDIでアフリカゾウを演奏」では持続音、Rumble、Trumpet、Squeakを選べます。採取したWAV、観測JSON、再実行ケースを保存できます。観測には声門の位相・音高、鼻の弁の開口、鼻先・口端の流量が含まれます。[持続音MIDIの比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-elephant.md)・[RumbleのMIDI比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-elephant-call.md)・[TrumpetのMIDI比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-elephant-trumpet.md)・[SqueakのMIDI比較](../../../research/experiments/chimera-rebuild/notes/worklet-midi-elephant-squeak.md)

「アフリカゾウの rumble」では48 kHzの公式デモ先頭、44.1 kHzの移調と途中停止、96 kHzの自然終了を再生できます。観測JSONにはコールID、制御時計、ゲート・音高・呼気圧・経路・粗さの目標を含みます。[rumbleの比較と結果](../../../research/experiments/chimera-rebuild/notes/worklet-elephant-rumble.md)

「アフリカゾウの trumpet」では公式順序、`rumble` からの置き換えと途中停止、コールの音高指定（700 Hz）の有無を比べるケースを再生できます。観測JSONに弁音高・モードの目標と平滑値、弁の差圧・変位・速度・自由開口を保存します。実断面は `trunk_valve_area_cm2` で確認できます。[trumpetの観測条件と読解](../../../research/experiments/chimera-rebuild/notes/worklet-elephant-trumpet.md)

「アフリカゾウの squeak」では48 kHzの公式デモ全体、44.1 kHzの `trumpet` からの置き換えと途中停止、96 kHzの初期モード0と1を再生できます。観測JSONで、コールIDが変わる時刻と弁音高の目標が変わる時刻、自由開口が実断面を決める区間を調べられます。[squeakの観測条件と読解](../../../research/experiments/chimera-rebuild/notes/worklet-elephant-squeak.md)

「舌と唇の操作」では、発声を始めた後に舌体の座標と口唇開度を動かします。表示値は目標のcm値です。停止後の観測JSONに、Workletが目標を適用したフレームと、追従している舌体座標や口端断面積が入ります。[手動操作の読解と検証](../../../research/experiments/chimera-rebuild/notes/worklet-manual-articulation.md)

「MIDI鍵盤の発声」でMIDI入力を接続し、「MIDI計測を開始」を押してから鍵盤を弾けます。停止後はWAV、適用された音とフレームの観測JSON、CLIで再演できるケースを保存できます。[MIDI入力の読解と検証](../../../research/experiments/chimera-rebuild/notes/worklet-midi-voice.md)

「声道の三次元断面」で固定 `/i/` と口唇開度0.30 cmの姿勢を選べます。測定線を選ぶと、声門からの距離、有効隙間、計算面積を表示します。観測JSONには描画に使った頂点も入ります。[固定姿勢の三次元表示と検証](../../../research/experiments/chimera-rebuild/notes/worklet-tract-3d.md)

「IPA発話」で「三次元断面を観測する」を選ぶと、「IPAを実時間で発声」で声道の形が発声中に変わります。レンダー完了後は、「出力フレーム」で測定線と音響セルを同じ観測フレームに切り替えられます。`ɑpɑ` では192・256・352 msで閉鎖前・閉鎖中・開放後を比較できます。[オフラインの検証](../../../research/experiments/chimera-rebuild/notes/worklet-tract-3d-dynamic.md)・[実時間の検証](../../../research/experiments/chimera-rebuild/notes/worklet-tract-3d-live.md)

「再実行ケースを保存」で、初期姿勢と調音・呼気の操作を `worklet-articulation-case.json` に書き出せます。このファイルを研究ワークスペースの `vocal-cli` に直接渡すと、ブラウザが生成したPCMを再現できます。[再実行コマンドと比較結果](../../../research/experiments/chimera-rebuild/notes/worklet-manual-case-export.md)

## ブラウザ比較

Chromiumのヘッドレスシェルを一度入れ、[研究ディレクトリ](../../../research/experiments/chimera-rebuild/)から比較スクリプトを実行します。Node 24と研究環境のPython、固定上流のチェックアウトを使います。

```bash
node node_modules/playwright-core/cli.js install --only-shell chromium
```

```bash
python3 tools/measure_worklet_fixed.py worklet-fixed-voice-local-1
python3 tools/measure_worklet_realtime.py worklet-realtime-voice-local-1
python3 tools/measure_worklet_manual_articulation.py worklet-manual-articulation-local-1
python3 tools/measure_worklet_manual_articulation.py worklet-manual-case-export-local-1 --case-export
python3 tools/measure_worklet_ipa.py worklet-ipa-voice-local-1
python3 tools/measure_worklet_ipa.py worklet-ipa-timeline-local-1 --timeline
python3 tools/measure_worklet_tract_profile.py worklet-tract-profile-local-1
python3 tools/measure_worklet_tract_profile.py worklet-tract-3d-dynamic-local-1 --dynamic-3d
python3 tools/measure_worklet_tract_profile.py worklet-tract-3d-live-local-1 --live-3d
python3 tools/measure_worklet_tract_profile.py worklet-tract-acoustics-local-1 --acoustics
python3 tools/measure_worklet_ipa.py worklet-glottal-scope-local-1 --scope
python3 tools/measure_worklet_ipa.py worklet-pcm-spectrum-local-1 --spectrum
python3 tools/measure_worklet_ipa.py worklet-live-ipa-local-1 --live
python3 tools/measure_worklet_english.py worklet-english-voice-local-1
python3 tools/measure_worklet_song.py worklet-song-voice-local-1
python3 tools/measure_worklet_song_recording.py worklet-song-recording-local-1
python3 tools/measure_worklet_song_recording.py worklet-song-tract-recording-local-1 --tract
python3 tools/measure_worklet_beatbox.py worklet-beatbox-local-1
python3 tools/measure_worklet_live_beatbox.py worklet-live-beatbox-local-1
python3 tools/measure_songbird_sustain_pcm.py songbird-sustain-local-1
python3 tools/measure_worklet_songbird.py worklet-songbird-local-1 songbird-sustain-local-1
python3 tools/measure_songbird_flute.py songbird-flute-local-1
python3 tools/measure_worklet_songbird_flute.py worklet-songbird-flute-local-1 songbird-flute-local-1
python3 tools/measure_songbird_calls.py songbird-calls-local-1
python3 tools/measure_worklet_songbird_trill.py worklet-songbird-trill-local-1 songbird-calls-local-1
python3 tools/measure_worklet_songbird_trill_observation.py worklet-songbird-trill-observation-local-1 songbird-calls-local-1
python3 tools/measure_worklet_songbird_chirps.py worklet-songbird-chirps-local-1 songbird-calls-local-1
python3 tools/measure_worklet_songbird_buzz.py worklet-songbird-buzz-local-1 songbird-calls-local-1
python3 tools/measure_worklet_songbird_switch.py worklet-songbird-switch-local-1 songbird-calls-local-1
python3 tools/measure_seal_sustain_pcm.py seal-sustain-local-1
python3 tools/measure_worklet_seal_sustain.py worklet-seal-sustain-local-1 seal-sustain-local-1
python3 tools/measure_seal_trill.py seal-trill-local-1
python3 tools/measure_worklet_seal_trill.py worklet-seal-trill-local-1 seal-trill-local-1
python3 tools/measure_seal_zap.py seal-zap-local-1
python3 tools/measure_worklet_seal_zap.py worklet-seal-zap-local-1 seal-zap-local-1
python3 tools/measure_seal_whistle.py seal-whistle-local-1
python3 tools/measure_worklet_seal_whistle.py worklet-seal-whistle-local-1 seal-whistle-local-1
python3 tools/measure_seal_chug.py seal-chug-local-1 --revision 2
python3 tools/measure_worklet_seal_chug.py worklet-seal-chug-local-1 seal-chug-local-1
python3 tools/measure_alligator_fixed_voice.py alligator-fixed-local-1 --revision 2
python3 tools/measure_worklet_alligator_fixed_voice.py worklet-alligator-fixed-local-1 alligator-fixed-local-1
python3 tools/measure_alligator_bellow.py alligator-bellow-local-1
python3 tools/measure_worklet_alligator_bellow.py worklet-alligator-bellow-local-1 alligator-bellow-local-1
python3 tools/measure_alligator_growl.py alligator-growl-local-1
python3 tools/measure_worklet_alligator_growl.py worklet-alligator-growl-local-1 alligator-growl-local-1
python3 tools/measure_alligator_hiss.py alligator-hiss-local-1
python3 tools/measure_worklet_alligator_hiss.py worklet-alligator-hiss-local-1 alligator-hiss-local-1
python3 tools/measure_alligator_dance.py alligator-dance-local-1
python3 tools/measure_worklet_alligator_dance.py worklet-alligator-dance-local-1 alligator-dance-local-1
python3 tools/measure_elephant_fixed_voice.py elephant-fixed-voice-local-1
python3 tools/measure_worklet_elephant_fixed_voice.py worklet-elephant-fixed-local-1 elephant-fixed-voice-local-1
python3 tools/measure_elephant_rumble.py elephant-rumble-local-1
python3 tools/measure_worklet_elephant_rumble.py worklet-elephant-rumble-local-1 elephant-rumble-local-1
python3 tools/measure_elephant_trumpet.py elephant-trumpet-local-1
python3 tools/measure_worklet_elephant_trumpet.py worklet-elephant-trumpet-local-1 elephant-trumpet-local-1
python3 tools/measure_elephant_squeak.py elephant-squeak-local-1
python3 tools/measure_worklet_elephant_squeak.py worklet-elephant-squeak-local-1 elephant-squeak-local-1
```

比較は、本番ビルドで画面から保存したWAVと観測JSONを使用します。実行IDを変えると別の記録が残ります。[比較ケース](../../../research/experiments/chimera-rebuild/cases/worklet-fixed-voice.json)

実時間の観測JSONには、Workletの処理時間と開始・停止を適用したフレーム番号が入ります。比較の実行記録にある `replay-case.json` はCLIにも渡せます。[実時間の読解と比較](../../../research/experiments/chimera-rebuild/notes/worklet-realtime-voice.md)

「実時間の発声」の「出力サンプルレート」では48,000 Hz、44,100 Hz、32,000 Hz、16,000 Hz、96,000 Hzを選べます。内部レートは選択順に96,000 Hz、88,200 Hz、64,000 Hz、64,000 Hz、96,000 Hzです。追加レートでは約1秒の発声と停止後の減衰を保存し、観測JSONに実際のAudioContextとWorkletのレート、内部レート、制御更新間隔を記録します。[44.1 kHz](../../../research/experiments/chimera-rebuild/notes/worklet-realtime-voice-44100.md)・[32 kHz](../../../research/experiments/chimera-rebuild/notes/worklet-realtime-voice-32000.md)・[16 kHz](../../../research/experiments/chimera-rebuild/notes/worklet-realtime-voice-16000.md)・[96 kHz](../../../research/experiments/chimera-rebuild/notes/worklet-realtime-voice-96000.md)

IPAの検証ではCLIの `bilabial-p` と初期姿勢・音源を合わせ、ブラウザの入力からPCMまで比較します。調音に対応する子音は `p b t d s z m h ɦ w l ɫ` です。[IPA発話の読解と結果](../../../research/experiments/chimera-rebuild/notes/worklet-ipa-voice.md)

IPA発話をレンダーすると、計画音素、口唇の最小断面積、PCM波形が同じ横軸に表示されます。図をクリックするか「出力フレーム」のスライダーを動かすと、選択した時刻の音素と、直前までに得た口唇の観測値を確認できます。スライダーにフォーカスした状態では左右キーで1フレームずつ移動できます。[時系列の表示と比較](../../../research/experiments/chimera-rebuild/notes/worklet-ipa-timeline.md)

同じフレーム選択で、咽頭から口腔までの声道断面を確認できます。濃い色がセル内の最小断面、淡い色が平均断面を示し、高さは円の相当直径に比例します。図の上に断面を採取した時刻が表示され、数値は観測JSONの `tract` に保存されます。[声道断面の表示と比較](../../../research/experiments/chimera-rebuild/notes/worklet-tract-profile.md)

断面図の下には、同じ時刻のセル中心の圧力と口側境界の流量を表示します。「観測セル」を選ぶと値と単位を確認できます。流量は口端側が正で、口端の点は外気への放射流量です。観測JSONでは `tract.acoustics` に入ります。[圧力と流量の照合](../../../research/experiments/chimera-rebuild/notes/worklet-tract-acoustics.md)

「声門波形」は選択時刻を0 msとした前後12 msの面積と流量です。流量の正方向は気管から咽頭で、負の値は逆流を示します。発話の全出力フレームの系列を観測JSONの `glottal` に保存できます。[声門波形の照合](../../../research/experiments/chimera-rebuild/notes/worklet-glottal-scope.md)

「PCMスペクトル」は選択時刻を中心に保存WAVと同じPCMを分析します。2,048点のBlackman窓を使い、発話の前後をゼロで埋めます。画面は共通のdBFS目盛で、窓に入った実データの点数と表示帯域の最大ビンを示します。「スペクトルJSONを保存」でDCからナイキストまでの振幅と窓の範囲を保存できます。[スペクトルの照合](../../../research/experiments/chimera-rebuild/notes/worklet-pcm-spectrum.md)

「IPAを実時間で発声」は発話の前にAudioContextの描画量子を確認し、同じ調音スコアを実時間で再生します。「IPAを停止」で途中の再生を終了できます。発話が完了すると、WAV、時系列と観測JSONを確認できます。観測JSONの `realtime` にはContextのフレームと量子ごとの処理時間が入ります。[実時間の発話と比較](../../../research/experiments/chimera-rebuild/notes/worklet-live-ipa.md)

「英語発話」で `Mom? Pop.` などを入力すると、発音と句の計画が表示されます。WAVと観測JSONに加え、同じ時系列表示で計画音素と波形を確認できます。観測JSONには鼻端流量と軟口蓋のポート面積も入ります。発音に未対応の音素が含まれる場合は、その音素を画面に表示します。[英語発話の読解と検証](../../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md)

「歌唱」の初期値は二音の `Pop Dee` です。MIDI番号と拍数を空白で区切り、1行に1音ずつ指定します。「歌唱をレンダー」でオフライン合成し、「実時間で歌唱」で再生します。実時間の再生は「歌唱を停止」で中断できます。完了後はWAVと音節・拍・ジェスチャー・呼気ゲート・開大面積・F0の観測JSONを保存できます。実時間の観測には開始の予約フレームと量子ごとの処理時間も入ります。辞書は初回の歌唱操作で読み込み、未対応の音素は画面に表示します。[歌唱の検証ケース](../../../research/experiments/chimera-rebuild/cases/worklet-song-voice.json)・[実時間の歌唱と比較](../../../research/experiments/chimera-rebuild/notes/worklet-live-song.md)

「歌唱を録画」は、合成音声と拍・MIDI番号・経過時刻を縦長の動画に収めます。自然終了後に試聴して「歌唱の動画を保存」を選べます。「録画を中止」はその回の録画を破棄します。再生・保存に使える動画形式はブラウザの対応状況で決まります。比較スクリプトはFFmpegとffprobeで動画の同期と無音区間を測ります。[録画の検証](../../../research/experiments/chimera-rebuild/notes/worklet-song-recording.md)

「録画に声道の三次元断面を含める」を選ぶと、声道と出力フレーム番号も動画に入ります。末端が閉じると橙色の点になり、開くと輪郭が現れます。保存する観測JSONに測定線と作画時刻が入り、動画の識別欄と照合できます。[三次元断面の録画と検証](../../../research/experiments/chimera-rebuild/notes/worklet-song-tract-recording.md)

MP4を選べない場合は、ブラウザが対応するWebMを保存します。研究用の比較では、MP4の対応判定を無効にしたChromiumから録画し、実際に保存されたVP9/Opusの音声と画像を検査できます。[WebMの形式選択と検証](../../../research/experiments/chimera-rebuild/notes/worklet-song-recording-webm.md)

「デュエットの再生時計」では、二声を混合した2.2秒のWAVを再生し、可聴時刻から求めた音源フレーム番号を表示します。一時停止中も位置を変更でき、末尾に達すると「最初から再生」に切り替わります。[デュエットの素材と時刻の照合](../../../research/experiments/chimera-rebuild/notes/duet-transport.md)

同じ画面の「声部別のテレメトリ」には、各声部の観測行、採取サンプル、F0、口唇開度が表示されます。シークや一時停止では二声に同じ再生時刻を使います。各声部の記録が終わると、その声部の最後の観測を保持します。[形式と境界の検証](../../../research/experiments/chimera-rebuild/notes/duet-telemetry.md)

「声部別の三次元頭部」では、同じ観測行から声部ごとの舌、唇、顎などの形状を描画します。一時停止中もスライダーで姿勢を調べられます。頭蓋や耳の輪郭は向きを示す模式図です。[調音姿勢と描画の照合](../../../research/experiments/chimera-rebuild/notes/duet-heads.md)

歌っている音節は唇の前に表示します。前方の空きが狭ければ顎の下に移り、音節が変わると前の文字は薄れて消えます。シーク後は移動先の文字から表示します。[文字の投影と履歴の検証](../../../research/experiments/chimera-rebuild/notes/duet-mouth-words.md)

再生中だけ、直近の舌・下顎・唇の輪郭を薄く重ねます。シーク後は移動先の観測から残像を作り始めます。[輪郭の履歴と表示の検証](../../../research/experiments/chimera-rebuild/notes/duet-head-echoes.md)

口腔圧で頬が膨らみ、音高と拍で眉や頭が動きます。調音姿勢を固定した向きで調べるときは「表情と頭部の動き」のチェックを外せます。公演の設定に `bpm` と任意の `downbeat`（秒）を入れると、頷きが拍に反応します。[表情とシークの検証](../../../research/experiments/chimera-rebuild/notes/duet-head-expression.md)

「声部別の歌詞」では、各声部の現在の音節を拍に合わせて表示します。休符は空表示になり、メリスマでは親の音節を引き継ぎます。旋律ファイルに音節が含まれている場合はその値を使い、歌詞だけの場合は既存の辞書とWASMで音節化します。[歌詞とシークの検証](../../../research/experiments/chimera-rebuild/notes/duet-words.md)
