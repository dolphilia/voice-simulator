# IPAから発話区間まで

比較するCHIMERAは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第5段階で、音素列を解析時刻と結び付け、後続の調音ジェスチャーが参照する区間を取り出す。

## 読んだ入口と更新順

1. [上流CLIの `speech`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110) は `/` で発話を分け、空白だけの断片を除く。最初の発話の基準時刻は50 ms。発話の後ろに350 msを進め、最後に200 msを足し、48 kHzのフレーム数へ丸める。
2. [`klatt_durations`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L95) は展開前の音素を `wordEnd` で区切り、句の最終母音、語内の母音数と末尾子音を数える。長さは `D = m + (I − m)p`。固有長 `I` と最小値 `m` は ms、文脈係数 `p` は無次元。基本表にない音素は目録の既定長、目録にもないものは80 msから設定する。無強勢では最小値も半分にし、無声破裂音の直後の有強勢母音には20 msを加える。音素の明示長さは秒で受け取って文脈計算を省くが、隣の音素を判定する際には同じ音素として扱う。
3. 同じ語にある母音と末尾の /ɹ/ は母音の時間を分け合う。双方に明示長さがないとき、母音側から /ɹ/ の分を引き、母音に40 ms以上を残す。語中で直後の母音につながる /ɹ/ ではこの処理が入らない。
4. [`expand`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L74) と [`plan_utterance`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L320) は、つづいて下降二重母音を55/45%、上昇を30/70%、三重母音を25/45/30%に配分する。展開後の長さを話速で割り、基準時刻の60 ms後から積算する。出力は秒単位の半開区間で、明示長さが0なら始点と終点が一致する。
5. [音素の既定値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L263) の調音目標は体型に応じて変わる。声の有無と既定長は共通。3体型の母音表は同じ26記号を持つ。発話頭・休止・阻害音に続く /ð/ は計画上の分類を破裂音に切り替える。長さの計算は手前で終わっているため、周囲の母音の長さには /ð/ の有声摩擦音としての係数が残る。

## 実装前の予測と判定

[ケース定義](../cases/speech-timing.json) に15入力を登録した。全音素について、展開前の長さ、展開後の分類・開始・終了、発話末尾までを上流の公開関数と比較する。時刻の許容差は絶対値1 ps。出力波形の比較に使う上流CLIの表示は1 ms刻みなので、開始マークは丸め幅0.5 msで比較し、WAVはフレーム数を照合する。

- 基準VCVでは語中の第1 /ɑ/ の長さが後続の有声摩擦音で長くなり、無声破裂音で短くなる。第2 /ɑ/ は先行子音によらず198.96 msになる。独立計算では /ɑ/ の240 msと、無強勢の最小50 msに文脈係数を適用する。
- 有強勢の語末 /æ/ を /t d s z n/ の前に置くと、固有230 msと最小80 msから `80 + 150 × 1.4 × f` msを得る。/t/ で227 ms、/d/ で332 ms、/z/ で416 ms。
- 200 msの /iɑ/ は60/140 ms、400 msの /uaɪ/ は100/180/120 msになる。話速1.6では展開前の長さが保たれ、発話内の各区間だけが1/1.6に縮む。
- /ʏ/ は字句解析を通り、明示長さがない条件でも計画時刻が進む。未認識の文字だけの発話もリード時間を持ち、スラッシュで区切られた空の断片は取り除かれる。調音まで通るかどうかは分類に表れる。
- 表に載る音素と展開規則の和集合を、単独・母音間・破裂音の直後・有声摩擦音の直前・明示長さと話速の5条件でも照合する。

基準を確定する前の読み合わせで、第6発話 `cɑ` の /c/ を未対応と見込んだ記入を破裂音に訂正した。上流目録の [無声硬口蓋破裂音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L167) と比較プローブで確認した。

## 実装と観測結果

[長さ規則](../crates/vocal-core/src/phonetics/timing/durations.rs) は、語の最終母音の位置を先に記録して、各音素の処理時に語内を再走査せずに判定する。[区間の実装](../crates/vocal-core/src/phonetics/timing.rs) は、展開元のインデックス、配分した長さ、話速適用後の時刻、グライド継続の有無を返す。展開した母音には強勢、明示F0、鼻音化、息漏れを伝える。CLIは原文のバイト範囲と診断も返す。話速は有限の正値、明示長さは有限の非負値を受け取る。実装途中の型検査で、CLIが所有する音素列の引数と入口のIDに型指定が必要と判明し、修正後にワークスペースのテストが通った。

長さ表52件は固定版の `durations::table`、音素の代替長71件は `inventory::consonants`、展開34件は `planner::{expand,is_rising}` から採取した。母音の分類表をIPA字句解析と共有する。[比較器](../tools/measure_speech_timing.py)・[固定版由来の表](../crates/vocal-core/src/phonetics/timing.generated.json)・[上流のMIT通知](../LICENSE-CHIMERA)

登録15件と、目録・長さ表・展開・較正母音から作った131記号×5条件が通過した。候補と上流ライブラリの長さ・時刻の差は比較した値で0 s。基準VCV、語末母音、話速に対する独立計算の最大差は `6.94×10⁻¹⁷ s`。上流CLIの15マークは最大0.390 msの差で、設定した丸め幅に収まった。上流の48 kHz WAVは202,527フレームで、候補区間から算出したフレーム数と一致した。[初回要約](../runs/speech-timing-20261119-a/summary.json)・[再実行要約](../runs/speech-timing-20261119-b/summary.json)

調音先が定義されていない /ʏ/ は `ɑʏɑ` で75.2 ms、長さ記号を付けると255 msを占めた。双方で発話計画の分類は `?` 相当で、後続母音の開始が179.8 msずれた。基準VCVの調音ジェスチャーと候補PCMは次の検証で扱う。

研究ワークスペースと `/tmp` での実行で、候補・上流の区間JSON、上流CLIのWAV、要約を含む9ファイルがバイト一致した。IPA字句解析は8ファイル、成人男性の母音遷移は9ファイルが直前の通過版と一致した。[区間の再実行](../runs/speech-timing-20261119-b/manifest.json)・[IPA字句解析](../runs/ipa-tokenization-20261119-c/manifest.json)・[母音遷移](../runs/vowel-motion-voice-vowels-20261119-e/manifest.json)
