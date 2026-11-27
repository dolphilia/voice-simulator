# 韓国語歌詞の音節化

## 固定上流の読解

- CLIの `syllables` は `sung_lyrics`、ブラウザは `lyricsToSyllables` を入口として同じ歌詞ルーターに着く。`read_lyrics` は前処理で曲がったアポストロフィを揃え、各言語が連続して読める文字を一語にする。ハングルの完成形か結合用の現代初声が韓国語の開始文字で、語の中には現代の中声・終声も入る。区切りの空白、句読点、独立した `~` と `-` の処理は共通。独立したメリスマ記号は直前の母音を別の音符へ延ばし、句読点は直前の音節に句末を付ける。[CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L117)・[WASMの呼び出し元](../../../../docs/reference/chimera-vocal-synth/upstream/src/wasm/engine.ts#L155)・[歌詞ルーター](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/syllables.rs#L235)
- `compose` は直前の文字と入力中の文字を見て、初声と中声を `0xAC00 + (初声番号 × 21 + 中声番号) × 28` にする。終声のない完成形に結合用終声が続けば、その番号（1〜27）だけ足す。再分解は基点との差を588と28で割った商・余りで初声19・中声21・終声28の表を引く。ここで持つ状態は元の完成形1文字、頭子音、渡り音、母音、最大2要素の末子音。古い結合字母で構成された音節と孤立した現代字母からは音節を出さない。[合成と分解](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/korean.rs#L24)
- `join` は同じ語の左から右へ隣接ブロックを書き換える。まず無音の初声を前の末子音で埋める場合を処理し、次にㅎの脱落・帯気化、特定の語幹の例外、終声の単純化・中和、流音化、鼻音化または濃音化の順で処理する。語末では末子音を七つの音に中和する。IPAに変えるときは前の確定した末子音を参照し、例えば `먹어` は /mʌ.gʌ/、空白で区切った `먹 어` は /mʌk.ʌ/ になる。音節表示用には、音の書き換え前の完成形を保持する。[隣接規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/korean.rs#L141)・[IPAへの変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/korean.rs#L228)・[上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/syllables.rs#L79)
- 平音 `불` と激音 `풀` の頭子音は同じ /p/ に `aspirated=true` と異なる `vot`（0.045秒、0.090秒）を付ける。濃音 `뿔` は `aspirated=false`。歌唱計画はこれらを調音計画に渡す。帯気の開大目標を破裂の後まで保持する秒数は話速1で `max(0, 0.4 × 0.05 + vot − 0.05)`。濃音では `0.4 × 0.012` を用いる。値はジェスチャーの保持部分を表す。声門が振動し始める実測時刻にはランプ、声門と肺・声道の状態も効く。[音符から音素への変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L37)・[開大を決める式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L509)・[上流の評価資料](../../../../docs/reference/chimera-vocal-synth/upstream/docs/language-front-ends.md#korean)

## 事前登録

完成形、独立したPythonのNFD、終声だけ分解した例について完全な音節JSONを比べる。結合規則の対照、古い字母、英語混在、メリスマ、句末を含める。歌唱では `불 풀 뿔.` の音符3個を同じ設定で使い、拍、声門開大の保持時間と目標、出力区間のPCMと観測時刻を比較する。現行の調音器の対応範囲は準備済みのIPA音素の一覧で確認し、今回のレンダーは閉鎖と語内の母音を同条件で比べられる両唇閉鎖音を選んだ。[登録ケース](../cases/korean-lyrics.json)・[現在の調音対応表](../crates/vocal-core/src/phonetics/speech.rs#L208)

### 初回判定とケース改訂

初回 `a` は、上流とCLIがともに115,200フレームを生成したところで、登録した112,800フレームと不一致になった。最後の音素は1.95秒で終わる。レンダー長に使う計画終端は名目上の拍の終端2.00秒と音素終端の大きい方で、さらに0.40秒の余韻を足すため2.40秒となる。また `~,` ではチルダの直後が空白でも入力末尾でもないため、両実装ともメリスマを作らず、直前の「야」を句末にした。第2版はこの出力長とラベルを登録し、空白を挟む `~ ,` を対照に加えた。数値の許容差は維持した。[初回の判定](../runs/korean-lyrics-20261120-a/manifest.json)・[初回のCLI計画](../runs/korean-lyrics-20261120-a/artifacts/settings.json)・[初回の混在入力に対する上流JSON](../runs/korean-lyrics-20261120-a/artifacts/lyric-upstream/mixed.json)

## 実装と実測

Rustの歌詞ルーターが文字範囲で英語とハングルを振り分ける。ハングルでは入力の読み進めと同時に完成形を組み立ててから、語内の書き換えとIPAへの変換を行う。語末、メリスマ、句末は英語と同じルーターで印を付ける。CLIの歌詞・歌唱ケースとWASMの歌唱計画からこの入口を使う。[歌詞ルーター](../crates/vocal-core/src/phonetics/syllables.rs)・[韓国語の実装](../crates/vocal-core/src/phonetics/korean.rs)・[出典のライセンス](../LICENSE-CHIMERA)

```bash
python3 tools/measure_korean_lyrics.py korean-lyrics-local-1
```

- 第2版の `b` では34入力の音節JSONが、固定上流の通常の `chimera syllables` と一致した。末子音の移動、鼻音化、流音化、ㅎの扱い、語幹例外、古い結合字母、英語混在、メリスマ、語末と句末を比較した。独立にNFDへ変換した結果と終声だけを分解した結果も、それぞれ完成形の音節と一致した。[入力と測定値](../runs/korean-lyrics-20261120-b/summary.json)・[実行と環境](../runs/korean-lyrics-20261120-b/manifest.json)
- `불 풀 뿔.` の音符で母音は0.5・1.0・1.5秒に始まった。破裂後の声門開大の保持時間は15・60・4.8 ms、加算目標は0.36・0.36・0.22 cm²。上流と音素区間・ジェスチャーが一致し、全115,200フレームの最大PCM絶対差は `7.28×10⁻¹²` だった。最初のビット差は4114番で絶対差 `1.82×10⁻¹²`。候補ではホストの128・77フレーム分割でWAV・CSVが同一だった。[音響照合](../runs/korean-lyrics-20261120-b/summary.json)
- Chromiumでは完成形と字母をオフラインで、字母を実時間で歌唱した。3経路のPCMがCLIとビット一致し、64フレームごとの1,800点で内部状態を照合した。実時間の画面から保存した字母歌詞のケースをCLIで再合成してもPCMは一致した。英語の回帰比較は固定の歌詞66件、綴り44件、語の音節分割8件を通過した。RustのテストとClippyも通過した。[ブラウザの実行記録](../runs/korean-lyrics-20261120-b/manifest.json)・[英語の回帰](../runs/korean-lyrics-20261120-english-regression/summary.json)
- `/tmp` を作業ディレクトリにした再実行も40項目を通過した。初回通過時と再実行で音節JSON、CLIのPCM CSV、CLI・ブラウザ3経路・保存ケースの各WAVのSHA-256を照合し、それぞれ一致した。固定上流との最初の観測差は0番の放射流量の時間微分で `4.75×10⁻¹²` cm³/s²、声門流量は2番で `3.11×10⁻²³` cm³/sだった。比較した唇・呼気ゲート・開大・声門F0は一致した。[再実行の記録](../runs/korean-lyrics-20261120-repeat/manifest.json)・[再実行の判定](../runs/korean-lyrics-20261120-repeat/summary.json)

## 今回の音響比較の範囲

この比較時点では、単語例をそれぞれ一音節一音符に割り当てると、`song_plan` の `unavailable_speech_symbols` に /dʑ g j k n tɕ ŋ ɕ ɰ ɾ/ が現れた。続く実験では /k g/ を追加し、`먹어` と `먹 어` の歌唱で閉鎖と解放を照合した。[現在の対応音素](../crates/vocal-core/src/phonetics/speech.rs#L208)・[舌背閉鎖の実験](velar-stops.md)
