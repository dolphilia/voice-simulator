# 歌詞の音節化とMIDI音符の時間計画

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の歌詞からタイムラインを作る。音符の開始時刻、母音の実際の計画時刻、子音の区間とF0目標を観測する。

## 固定版の処理

1. `render::song` は英語辞書と歌詞から音節を得て、MIDI番号・拍長・音節を `SungNote` として並べる。デモ曲では歌詞が先に尽きると音節を先頭から繰り返す。`lyrics_to_syllables` には複数言語を選ぶ入口があり、ここでは第5段階の英語処理を追う。英語は辞書または綴り規則の完全形で語を読み、母音間の子音のうち合法な最長接尾部を後の音節の頭へ送る。ラベルの綴りはUTF-16で読み、入力のハイフンで手動分割できる。句読点は休止の境界、空白に囲まれた `~`・`-` は前の母音を別の音符で保つ指定になる。[歌唱CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L245)・[音節分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/syllables.rs#L41)・[綴りラベル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/syllables.rs#L97)・[英語の歌詞](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/syllables.rs#L197)
2. `plan_song` は `60/BPM` に拍長を掛け、最初の拍から順に秒を足す。`440×2^((MIDI−69)/12)` Hzを音符の音高にする。頭子音は母音の拍より前に新しいF0で置き、末子音は元の音高を保つ。既定の歌唱子音長は目録の0.8倍。前の末子音と次の頭子音で母音に50 ms残せなくなると、子音長を比例圧縮し、各子音には最低12 msを残す。圧縮後の母音は最低20 ms。その合計が拍長を超えれば後続の母音は遅れる。[音高変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/math.rs#L165)・[子音圧縮](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L98)・[拍と音素の配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L167)
3. メリスマの連鎖は最後にだけ元の末子音と下降する二重母音の後半を出す。下降二重母音の後半は母音の持続時間の20%。上昇二重母音の前半は原則50 msで拍より前へ出し、主要母音を拍に置く。途中の句の終わりには上限120 ms、最後の句には上限50 msの余白を残す。どちらもその音符の30%が上限になる。各句は先頭の子音長と発話計画が加える呼気先行60 msを拍から引いた時刻から計画する。歌唱のF0目標は音素の区間ごとに強さ6、入り・出のランプは `min(60 ms,max(8 ms,区間長/2))`。同じ拍時刻を保つ条件を `sing_fast` が、上昇二重母音の拍を `rising` が確かめている。[句末と二重母音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L208)・[歌唱のF0目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L658)・[高速の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)・[上昇二重母音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/rising.rs)

## 実装前の予測と判定

120 BPMで1拍の `Pop Dee` は母音が0.5秒と1秒に始まる。2番目の頭 /d/ は0.952秒からA4の440 Hzを目標にする。240 BPM・各1/4拍では /p/ と /d/ を各12 msに縮め、母音を0.5秒と0.5625秒に保つ。`Strut` の反復は1音符62.5 msに4子音48 msと母音20 msが収まり切らず、1音符あたり5.5 msずつ遅れる。`Hi ~ Pop.` と `Pop ~ Dee.` は下降グライドと末子音をそれぞれメリスマの最後に回し、`Hi, We.` は句の境界で計画を分ける。直接指定した `ua` の /u/ は0.45秒から0.5秒、/a/ は拍の0.5秒から。音素・強勢・境界を固定版と一致させ、時刻とF0は絶対差 `10⁻¹⁰` を許容する。[予測とケース定義](../cases/song-plan.json)

## 実装と観測結果

歌詞の音節は発音の完全形から作り、歌唱タイムラインは既存の発話区間の表現を使う。音符ごとに予定の拍と、圧縮後に実際に割り当てた母音核の開始・終了を保持する。これで、間に母音以外の音素が挟まらないメリスマや上昇グライドでも音符ごとの母音開始をたどれる。歌唱のF0ジェスチャーは句ごとに母音、子音の順で追加する。`unavailable_speech_symbols` は現在の発話レンダーに追加が必要な記号を示す。`Strut` の最速ケースでは /ɹ/ が該当する。[音節化](../crates/vocal-core/src/phonetics/syllables.rs)・[拍の計画](../crates/vocal-core/src/phonetics/song.rs)・[CLI](../crates/vocal-cli/src/song_case.rs)・[上流のMIT通知](../LICENSE-CHIMERA)

| 譜例 | 観測した区間と音高 |
| --- | --- |
| 等速 `Pop Dee` | /ɑ/ が0.500 s、/i/ が1.000 s。/d/ の440 Hz目標は0.952 sから始まる。前の末子音 /p/ はC4の261.63 Hzの目標を保つ |
| 240 BPMの `Pop Dee` | /p d/ を12 msずつに短縮し、/i/ は拍どおり0.5625 sに始まる |
| 240 BPMで `Strut` を4音 | 予定からの遅れは0、5.5、11.0、16.5 ms。初めの3音の母音は各20 ms |
| `Hi ~ Pop.` と `Pop ~ Dee.` | `Hi` の /ɪ/ は2音目の最後86.4 ms、`Pop` の末尾 /p/ は継続音の後半1.384 sから現れる |
| `Hi, We.` | 第1句は0.880 sで終わり、第2句の /w/ は0.952 s、母音 /i/ は第2拍の1.000 s |
| `ua` の直接指定 | /u/ が0.450〜0.500 s、/a/ が0.500〜1.450 s |

繰り返しと空の譜例を含む9ケースの音素・強勢・時刻・F0目標が固定上流と一致した。拍の合計とMIDIの独立計算との比較でも数値差0だった。TypeScript参照は英語歌詞33件を辞書あり・なしで計66件、綴りラベル44件、子音分割を含む語の音節化8件で一致。`Hello world!` の歌詞では `world` の末子音が /l d/ のまま歌唱用の音節に入る。英語の通常発話では句を作る段階で /ɫ d/ になる。[譜例の出力](../runs/song-plan-20261119-a/artifacts/candidate.json)・[固定版と参照データの照合](../runs/song-plan-20261119-a/summary.json)・[英語発話の確認](lateral-approximants.md)

`/tmp` から同じケースを再実行し、全入力、候補の `inspect`・`render`、固定上流、辞書、要約の6ファイルが初回とバイト一致した。英語発話・英語発音・IPA区間の回帰も通過し、比較した39ファイルが先行実行と一致した。再実行の入力と出力はマニフェストのSHA-256を照合した。テンポ0、拍長0、音節が空の歌詞への音符指定、歌詞と直接指定した音節を同時に渡す場合にはエラーを確認した。候補のワークスペーステストとClippy、上流の `sing_fast`、`rising`、`golden_phonetics_text` が通過した。[再計測の記録](../runs/song-plan-20261119-b/manifest.json)・[英語の発話](../runs/lateral-hello-20261119-c/summary.json)・[英語発音](../runs/english-frontend-20261119-g/summary.json)・[発話区間](../runs/speech-timing-20261119-d/summary.json)
