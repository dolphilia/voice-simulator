# 声門閉鎖音 /ʔ/ と周期発声の復帰

参照版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。前回の /ɻ/ は104項目が通過し、中国語の診断句「四是吃字人爱」に音響未対応の /ʔ/ が残った。[先行結果](../runs/retroflex-approximant-20261120-repeat/summary.json)・[事前登録](../cases/glottal-stop.json)

## 入力と閉鎖指示

発話CLIは `render::speech` から `tokenize_ipa` と `plan_utterance` を通る。 /ʔ/ は目録で無声の声門音、既定長60 ms。語中の母音間ではKlatt表の既定40 ms、最小30 msを使い、 `30 + (40−30) × 0.85 = 38.5 ms`。歌唱は目録の60 msに0.8を乗じ、今回の音符では48 msを使う。[発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L173)・[時間配分表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L45)・[歌唱の子音長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L28)

歌唱CLIの `sung_lyrics` は漢字辞書から「人」を `ren2`、「爱」を `ai4` と読み、 `pinyin_syllable` が /ɻ ə n/ と /ʔ aɪ/ を作る。後者はピンインに声母が無いときの挿入規則を通る。 `plan_song` は /ʔ/ を拍前に置き、二重母音の最初の /a/ の開始を拍にそろえる。固定上流の `mandarin` 試験はこの音素列を、 `sound_marks` は /ʔ/ に口蓋化指定が付き得ないことを照合する。 `er` は同じ声門頭子音を持つ語のフォームント推移を検査する。[歌詞入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L63)・[ピンインの声門挿入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L324)・[音素列の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/mandarin.rs#L40)・[修飾の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sound_marks.rs#L127)・[児化しない「儿」の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/er.rs#L59)

`plan_utterance` は口腔調音の主目標を加えず、区間 `[a,b]` に無次元の閉鎖目標1.0を強さ8で置く。ランプは立上り12 ms、立下り15 msで、話速倍率に応じて短縮する。 `HumanVoice::control` はスコアから閉鎖の重み `w` と値 `q` を取り出し、基準閉鎖0の場合の指示を `q × min(1,w/2)` にする。このケースでは単一ジェスチャーで `q=1`。重み `w` は強さ8に正弦の二乗で上がり余弦の二乗で下がる包絡を掛けた値。[閉鎖のジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L506)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)

## 声門断面から流量まで

`ParametricGlottis::next` は内部ステップで声門前後の圧力差 `ΔP=P_sub−P_supra` を平滑化する。発声率の目標は圧力条件、声帯の開大条件、前ステップの `1−c` の積で、 `c` は閉鎖指示を時定数4 msで平滑化した無次元量。次に周期位相を進め、断面積を出す前に `c` と静的開口 `S` を更新する。cm²の面積は `振動振幅 × 発声率 × パルス + S(1−0.92c)`。静的開口は開大の指示と声門後端の隙間 `(0.008+0.03×breathiness)×体型スケール²` cm²の和を同じ4 msで平滑化する。位相0.98以上でパルスは0なので、その試料では独立に静的面積を再構成できる。 `c=1` でも静的項は8%残る。[平滑化係数と発声率](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L109)・[面積の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L201)・[体型と隙間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L340)

面積は `set_port_area` で声門ポートに渡され、次の `AirwayNetwork::step` が枝流量を更新する。閉鎖指示、静的面積、振動成分、枝流量はそれぞれ異なる段階で変化するため、口腔断面と同時に観測する。「人爱」と全6音節の診断句は固定上流と通常のCLI、加工前ブラウザ出力で照合する。[声門から気道・放射への更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L383)

## 事前の予測

標準の成人男女の /ɑʔɑ/ は中央の口腔断面が0.10 cm²を超え、声門側で発声率が0.15以下、流量RMSが先行母音の25%以下になる。回復した周期は計画終端から180 ms以内の区間で、声門面積ピーク間隔と実測F0により検出する。短い明示長と話速変化では指示、独立式、内部状態とPCMを照合する。歌唱には前の鼻音の閉鎖の持ち越しがあり得るため、口腔断面と流量は記述値を残す。[観測窓と判定](../cases/glottal-stop.json)

## 実装と実測

IPA発話と歌唱の既存経路に /ʔ/ の閉鎖目標を接続した。観測を有効にしたケースでは、制御が適用された閉鎖指示 `glottal_closure_command`、声門の周期位相 `glottal_phase`、口腔セルの断面をCSVに書き出す。計測器はジェスチャーの包絡と制御更新時刻から指示を計算し、位相0.98以上の試料で静的面積の式を比較する。7条件での最大誤差は閉鎖指示が `2.64×10⁻¹¹`、静的面積が `8.38×10⁻¹⁵ cm²`。[発話計画](../crates/vocal-core/src/phonetics/speech.rs)・[計測器](../tools/measure_glottal_stop.py)・[結果と判定](../runs/glottal-stop-20261120-a/summary.json)

表の中央は閉鎖の計画区間の60〜85%。流量比は同区間の声門流量RMSを閉鎖前のRMSで割った値。単独の「爱」の閉鎖前には周期発声がなく、流量比の分母は句中と条件が異なる。復帰時刻は計画終端から、連続する声門面積ピークの条件を満たした最初のピークまでを示す。[観測範囲と復帰条件](../cases/glottal-stop.json)

| 条件 | 計画長 (ms) | 中央の口腔最小断面 (cm²) | 中央の発声率中央値 | 声門流量比 (%) | 周期復帰 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 成人男性の /ɑʔɑ/ | 38.50 | 5.333 | 0.00850 | 0.01544 | 26.53 |
| 成人女性の /ɑʔɑ/ | 38.50 | 3.623 | 0.00850 | 0.01371 | 25.82 |
| 混合体型、1.35倍速 /iʔi/ | 28.52 | 0.653 | 0.03742 | 0.32920 | 23.25 |
| 成人男性、閉鎖長11 msの /ɑʔɑ/ | 11.00 | 5.384 | 0.17235 | 10.62471 | 28.90 |
| 「爱」 | 48.00 | 4.451 | 0.00110 | 5.71223 | 23.02 |
| 「人爱」 | 48.00 | 2.254 | 0.00286 | 0.01272 | 23.02 |
| 「四是吃字人爱」 | 48.00 | 2.254 | 0.00286 | 0.01279 | 22.98 |

標準の /ɑʔɑ/ は口腔が開いたまま、声門の周期発声と流量が事前の閾値まで落ちた。平滑化した閉鎖が最大の時点での静的開口比は約8.00005%。11 ms条件では約8.0444%まで近づいたが、中央の発声率中央値は0.172で、同一成人男性の標準条件の0.00850を上回った。静的開口比の最小値、観測区間での発声率、流量は異なる量で、閉鎖長の効果は個別に測れる。[独立計算と内部状態](../runs/glottal-stop-20261120-a/summary.json)

「人爱」では /n/ が0.952秒で終わり、/ʔ/ が1.000秒の拍まで48 msを使った。その約23 ms後に声門の周期が復帰した。「四是吃字人爱」も第6音節の拍に /a/ が始まり、診断句の音響未対応欄は空になった。2譜例を48 kHzで実行し、計278,400サンプルが実ブラウザ、CLI、保存ケースからの再演でビット一致した。[歌唱計画とブラウザの判定](../runs/glottal-stop-20261120-a/summary.json)

固定上流との加工前PCMの最大絶対差は7条件で `3.73×10⁻⁹`、全条件で事前の許容差内。「人爱」の厳密比較では、放射流量の時間微分がフレーム0で `4.75×10⁻¹² cm³/s²`、声門流量がフレーム2で `3.11×10⁻²³ cm³/s` 異なった。PCMで初めてビット差が出たのはフレーム4,114。閉鎖指示と位相は全フレームで一致し、放射の微小差は /ʔ/ の計画開始より前に観測された。[内部系列とPCMの所在](../runs/glottal-stop-20261120-a/manifest.json)

研究ディレクトリと `/tmp` からの実行で各98項目を通過した。内部時系列、波形、WASMの56ファイルのSHA-256が一致し、既存の声門摩擦音 /h/ の回帰は7項目を通過した。[再実行の判定](../runs/glottal-stop-20261120-repeat/summary.json)・[再実行のファイルハッシュ](../runs/glottal-stop-20261120-repeat/manifest.json)・[/h/ の回帰](../runs/glottal-stop-frication-regression-20261120/summary.json)
