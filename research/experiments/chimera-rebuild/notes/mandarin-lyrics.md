# 中国語歌詞の音節化と歌唱計画

上流を `c6147d0198890475dbe8a65a0bb8f56240c539b7` に固定した。辞書、読みの事前登録、歌唱の観測点を先に記録した。[登録ケース](../cases/mandarin-lyrics.json)

## 読解

- 歌詞は `lyrics_to_syllables_with` から文字種ごとの読みへ入る。声調付きピンインは英語と文字を共有するため先に候補を読み進める。候補を辞退した場合はその終端を覚え、同じ語の途中だけをピンインとして取り直すことを防ぐ。句読点は直前の音節の `phraseEnd`、単語の終端は `wordEnd` になる。[振り分け](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/syllables.rs#L222)
- `MandarinLexicon` は圧縮辞書を解凍したUTF-8のタブ区切りから、単字表と複数字表、最長語長を作る。漢字列の各位置で長い候補から見て、該当しなければ一字を引く。未知の文字は空欄で位置を保つ。次に「不」「一」を後続音節の声調で処理し、連続する第三声は最後を残して第二声にする。出力は文字に対応する声調番号付きの読み。句読点で分かれた漢字列は別々に処理される。[辞書と変調](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L30)
- `pinyin_syllable` は読み番号を分け、声母、介音、主母音、韻尾を得る。例えば「举 ju3」は無気の /tɕ/ と /y/、軽声の「的 de5」は無気の /t/ と /ə/。有気の破裂音と破擦音はVOT 90 ms、無気の破擦音は明示長80 ms。韻尾 /n ŋ/ は70、80 msで、先行母音の鼻音化割合0.6と終端移行の上限0.20秒を持つ。児化では `ɻ` を末尾に置き、先行する鼻音韻尾や下降滑音を置き換える。[音素と韻尾](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L157)・[音節と児化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L248)
- ピンイン入力は声調記号と数字を受け、元の綴りを表示する。数字0は軽声5。アポストロフィや数字の境目の内側では最大6文字の有効な音節を長い順に試す。語頭は声調の明記が必要で、語中の無標は頻出の軽声音節に限る。英語のアクセント付き綴りとの混同は上流の試験にもある。[発音の区切り](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L475)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/mandarin.rs)
- 音節の出力に声調のピッチベンドは付かない。歌唱は `f=440×2^((MIDI−69)/12)` の音高を使い、拍の秒は `60/BPM`。中国語の下降滑音では核の長さを `V`、終端移行の上限を `C` とすると、末尾の `min(C,0.6V)/2` 秒を滑音に割り当て、その長さを調音ランプにも渡す。鼻音韻尾がある音節では、軟口蓋の開き、舌の韻尾への接近、句末の閉鎖保持も計画に入る。[上流の歌唱計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L247)
- 固定辞書は `tools/build-mandarin.ts` が mozillazg の `pinyin-data` と `phrase-pinyin-data` の固定版から作る。単字の代表読みと、単字列と異なる読みを持つ語句、または「儿」を含む語句を収録する。固定版のgzipと、両者の著作権表示を含むMIT通知を一緒に収録する。[辞書の生成](../../../../docs/reference/chimera-vocal-synth/upstream/tools/build-mandarin.ts)・[辞書のライセンス通知](../../../../docs/reference/chimera-vocal-synth/upstream/public/data/MANDARIN-PINYIN-LICENSE.txt)

## 事前登録した予測

「银行」と「行走」の行は異なる読みになる。「我你好」は第三声の連続が2・2・3となる。音節の綴り、IPA、帯気指定、韻尾と境界を上流と照合する。「妈麻马骂吗」と「mā má mǎ mà ma5」は同じ音符で同じPCMになると予測する。「你好」の「好」は核の終わり100 msが滑音への移行になる。未対応の子音を含む語句は音素と時刻を計画から読み出し、候補の実時間経路では漢字の歌唱と保存ケースの再演を確認する。

## 実装と計測

候補は辞書をRustのコアにgzipで包んで同梱し、漢字を初めて読むときに展開する。CLIとWASMはこのコアと同じデータを使う。辞書の35,654行に含まれる54,766件の読みを単体試験で変換した。ブラウザの歌唱画面から両辞書のライセンスを開ける。ピンインの区切りは末尾から各位置の到達可能な切れ目を計算し、各位置で最大6文字を調べる。探索を繰り返す長い不正入力を、再帰なしで処理する。漢字の声調番号は任意の `song_plan.mandarin_words` で観測できる。音節JSONは `closing` と `nasalLead` を保持し、下降滑音の時間配分に `closing` を使う。[発音器](../crates/vocal-core/src/phonetics/mandarin.rs)・[振り分け](../crates/vocal-core/src/phonetics/syllables.rs)・[歌唱の配分](../crates/vocal-core/src/phonetics/song.rs)・[辞書の通知](../data/MANDARIN-PINYIN-LICENSE.txt)

初回は95項目中94項目を通過した。「四是吃字人爱」の未対応音素は登録した5種類と一致した。初回登録の一覧で `ɻ` を末尾に置いたが、候補の計画はUnicodeコードポイント順に並べていた。表示順を第2版に反映した。音素の集合、音響条件、実装は第1版のまま扱った。[初回の判定](../runs/mandarin-lyrics-20261120-a/summary.json)・[第2版の条件](../cases/mandarin-lyrics-v2.json)

## 実測

20入力・106音節の完全な音節JSONが固定上流と一致した。読み番号を採取した11入力では、「银行」は `yin2 hang2`、「行走」は `xing2 zou3`、「我你好」は `wo2 ni2 hao3`。数字0を使った `de0` は `de5` に表示され、軽声の `de5` は /t˭ə/、第二声の `de2` は /t˭ɤ/ になった。「哪儿」は /naɻ/ の一音節、「女儿」は二音節のまま。アクセント付き英語の `café` は `caf` が英語として残り、後半だけのピンイン解釈を抑止した。[音節JSONと声調番号](../runs/mandarin-lyrics-20261120-a/summary.json)

漢字とピンインを使った「妈麻马骂吗」の同譜は、MIDI 57・60・62・64・65を同じ時刻に使い、音響ジェスチャーと163,200サンプルの加工前PCMがビット一致した。「你好」の母音核は0.5秒と1.0秒に始まり、最後の滑音 /ʊ̠/ は1.35秒から1.45秒までの100 msを占めた。「八趴」は両方とも /pa/ で、後者に90 msのVOT指定が入り、声門開大目標は0.22から0.36 cm²へ変わった。このVOTは入力の指定値であり、実音響から検出した時間は別に計測する。[拍・滑音・声門開大の照合](../runs/mandarin-lyrics-20261120-a/summary.json)

4譜例で上流との加工前PCM最大絶対差は `2.91×10⁻¹¹`。漢字の2譜例の計254,400サンプルは実ブラウザ・CLI・保存ケースの再演でビット一致した。固定上流の5試験スイート41テスト、候補のワークスペース試験21件、Rustの整形とClippyを確認した。既存の「Ночной ветер」「ти́хо」「아주 자 차 짜」の保存ケースを現在の `vocal-cli inspect` に通し、以前の `settings.json` と完全一致した。[初回の実行コマンドとハッシュ](../runs/mandarin-lyrics-20261120-a/manifest.json)・[上流のテスト出力](../runs/mandarin-lyrics-20261120-a/artifacts/upstream-tests.log)

この実行では未対応音素が /ts tʂ ɻ ʂ ʔ/ だった。後続の実行では診断句「四是吃字人爱」の未対応欄が空になり、全6音節のPCMを実ブラウザとCLIで照合した。鼻音韻尾の音節JSONには `nasalLead` と短い /n ŋ/ が出る。鼻腔へ移る際の調音と句末閉鎖の保持も実測した。[診断句の実測](glottal-stop.md#実装と実測)・[鼻音韻尾の実測](mandarin-nasal-rhymes.md)・[第2版の計画ケース](../cases/mandarin-lyrics-v2.json)・[上流の鼻音韻尾](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L296)

第2版は研究ディレクトリと `/tmp` の両方で95項目を通過した。87出力のうち、要約・音節JSON・CLIの観測CSV・PCM・保存ケース・WASMを含む78出力のSHA-256が一致した。ビルドログやブラウザの生の観測JSONには実行間の差があり、要約はバイト一致した。[第2版の実行](../runs/mandarin-lyrics-20261120-b/manifest.json)・[別ディレクトリでの再実行](../runs/mandarin-lyrics-20261120-repeat/manifest.json)
