# そり舌接近音 /ɻ/ の頭子音と児化韻尾

参照版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行の /tʂ/ は105項目が通過し、「四是吃字人爱」の未対応は /ɻ ʔ/ だった。今回は /ɻ/ の発話と中国語歌唱をつなぐ。[先行結果](../runs/retroflex-affricate-20261120-repeat/summary.json)・[事前登録](../cases/retroflex-approximant.json)

## 音素から歌唱時刻まで

`render::speech` はIPA字句を `plan_utterance` に送る。 `inventory::phoneme` で /ɻ/ は有声・そり舌の接近音、既定長65 ms。Klatt表の個別値がないため、語中では最小39 msと残り26 msの0.85倍で61.1 ms、母音後の発話末では倍率をさらに1.4倍し69.94 msになる。話速で区間を割り、速度変更時にはランプと解放保持も短縮する。[発話入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[接近音の目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L226)・[子音の時間配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L186)

`sung_lyrics` は漢字辞書から「日」を `ri4` と読み、 `initial` と `pinyin_syllable` が /ɻ/ と舌尖母音 /ʅ/ を作る。「哪儿」の辞書列 `na3 er2` は `ERHUA_AFTER` の「哪」に該当し、 `rhotacize` が「哪」の音節に /ɻ/ を韻尾として足して鼻音化指定をクリアする。音節は /n a ɻ/ の一つで、児化を外した「哪」は /n a/ になる。後続の「儿」を独立に歌う語の扱いも、上流の `mandarin::erhua_merges_into_the_syllable_before` で照合されている。[歌詞入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L63)・[声母と舌尖母音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L187)・[児化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L348)・[児化の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/mandarin.rs#L133)

`plan_song` は頭子音と韻尾の既定長を0.8倍し、今回の音符では /ɻ/ に52 msを割り当てる。頭子音は核を拍までに引き渡す。韻尾は同じ音符の核の終端に続き、次の音符の頭子音の手前、または息継ぎ用に差し引いた句の終端に届く。メリスマの途中では韻尾を置かず、末尾音符に元の音節の韻尾を移す。鼻音の先行開放と句末保持は /m n ŋ/ の韻尾に限る。有声接近音で終わる句は上流の歌唱の脱力を使うため、句末での声門開大は接近音の調音と重なり得る。[歌唱の配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L193)・[核と韻尾の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L233)・[語尾の呼気と声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L567)

## 調音、声道と観測

舌先X・Yの主目標は `(5.4,9.55) cm`、無次元の反りは1.0。固定版で /ɻ/ の体型別の上書きはない。 `oral_gestures_into` は区間 `[a,b]` に対して `[a−0.008,max(a+0.010,b)]` に速度倍率1.3、強さ40、立上り30 ms、立下り18 ms、解放保持45 msを置く。口蓋化を指定した場合は舌体X・Yを /j/ の目標へ引く。この音素固有の遮断・開大はなく、スコアの呼気と圧力差で声門を動かす。[主目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[口蓋化と声門](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L545)

`ArticulatorBank::step` は無次元の反りに固有周波数9 Hzの臨界減衰を使う。各制御更新で、基準の重み0.05と発音の包絡から目標 `T` を作り、速度倍率を `s` として `ω=2π × 9 × s` とする。速度を `v ← v + Δt[ω²(T−x)−2ωv]`、位置を `x ← x + Δt·v` の順に更新する。これを独立の計測器で積分し、CSVの反りと比較する。反りは舌の輪郭、口腔断面、伝搬の順に反映される。隣接する声門面積ピークの時間差を声門F0の逆数に照らし、狭窄の前後で周期がつながるか判定する。[調音器の周波数表と積分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L24)・[反りを使う舌輪郭](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L858)・[声門から放射までの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

事前の予測では、標準発話と句中の児化韻尾で口腔が開いて周期発声が続く。「日」は `apical` 上流試験の拍前25 msと拍後250 msを使い、頭子音から /ʅ/ が舌先の反りを引き継ぐことを測る。句末の児化韻尾は声門の脱力を含むため、発声率と周期の境界は記述値として保存する。[舌尖母音の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/apical.rs#L57)・[予測と判定条件](../cases/retroflex-approximant.json)

## 実装と実測

再実装は /ɻ/ の三つの舌先目標と口蓋化を通常の発話・歌唱のスコアに渡す。すでに漢字とピンインの入力が生成していた /ɻ/ が同じ合成コアで発声できる。CLIと比較用の上流プログラムに舌先の反り、舌先位置、口腔・咽頭断面のCSV観測を接続した。今回の比較は両方で発話の乱流倍率0、歌唱の倍率1を使った。[合成コア](../crates/vocal-core/src/phonetics/speech.rs#L704)・[CLIの観測条件](../crates/vocal-cli/src/timing_case/speech_voice.rs#L951)・[上流の観測プログラム](../tools/upstream_bilabial_probe.rs#L269)

成人男女の標準発話で、音素中央の最小口腔断面はそれぞれ0.532、0.456 cm²、反りの中央値はともに0.925。語中61.1 ms、発話末69.94 msを照合し、発話末では呼気群の開大指示の保持が音素終端の45 ms後に始まった。反りを同じ包絡から独立に積分した結果と、候補・上流のCSVの最大絶対差は `2.49×10⁻¹³` だった。[発話・独立積分の値](../runs/retroflex-approximant-20261120-a/summary.json)

「日」の頭子音は0.448〜0.500秒で、拍から /ʅ/ が始まった。拍25 ms前から250 ms後で反りは0.944から0.857、舌先Xは0.065 cm移動した。核の正規化自己相関は0.924だった。「哪儿 妈」は「哪 妈」と比べて同じ0.910秒に次の頭子音 /m/ が始まり、第一音符の末尾52 msは /ɻ/ が担った。母音と /ɻ/ の境界0.858秒をまたぐ声門周期は4.542 ms、中央の最小口腔断面は0.544 cm²。「哪儿 ~」では /ɻ/ が第2音符の1.398〜1.450秒に移り、MIDI 60の261.626 Hzを引き継いだ。[頭子音・児化・メリスマの結果](../runs/retroflex-approximant-20261120-a/summary.json)

混合体型・話速1.35・口蓋化を組み合わせた /iɻʲi/ では、候補・上流とも音素内のフレーム9,854〜10,857で口腔最小断面が閉鎖閾値0.0002 cm²を下回った。連続1,004フレームで20.92 msに相当する。音素中央の声門発声率の中央値は約1を保った。体型、話速、母音、口蓋化を同時に変えた条件で、各要因の寄与は未測定。標準発話で登録した開放条件は通過した。[混合体型と標準発話の結果](../runs/retroflex-approximant-20261120-a/summary.json)・[全時系列の所在](../runs/retroflex-approximant-20261120-a/manifest.json)

4発話と4譜例のジェスチャーは固定上流と一致し、加工前PCMの最大絶対差は `1.16×10⁻¹⁰` だった。「日 哪儿」では放射流量の時間差分にフレーム0で `4.75×10⁻¹² cm³/s²` の差があり、最初のPCMのビット差は4,114フレーム。調音開始前の差で、全条件の内部状態とPCMは登録許容差以内だった。実時間Chromiumでの2譜例、計182,400サンプルはCLIと保存ケースの再演でビット一致し、各1,425点の音響状態も照合した。[104項目の判定](../runs/retroflex-approximant-20261120-a/summary.json)

固定上流の関連17試験、候補の22試験とClippy、既存の破擦音と鼻音韻尾のメリスマの回帰10項目が通過した。診断句「四是吃字人爱」で音響未対応に残ったのは /ʔ/。[実行環境と出力](../runs/retroflex-approximant-20261120-a/manifest.json)・[既存2譜例の回帰](../runs/retroflex-approximant-regression-20261120/summary.json)

研究ディレクトリで新しい実行IDを指定する。

```bash
python3 tools/measure_retroflex_approximant.py retroflex-approximant-local-1
```

スクリプトを絶対パスで `/tmp` から起動し、104項目を再び通過した。CLIと固定上流の各計測値、時系列・PCM・WASMの63ファイルのSHA-256が初回と一致した。[再実行の条件とハッシュ](../runs/retroflex-approximant-20261120-repeat/manifest.json)・[再実行の判定](../runs/retroflex-approximant-20261120-repeat/summary.json)
