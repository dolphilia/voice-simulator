# IPA入力の字句解析と未対応記号

2026-11-19。固定上流版 `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第5段階の入口。入力はUTF-8文字列、出力は連続した音素と区切り、修飾フラグ、秒で表す長さの明示値、診断。発声計画で使う区間の開始時刻と長さは後続工程で決める。

## 呼び出しと状態

- [render::speech](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L112) は入力全体の診断を先に出し、スラッシュで分割した空欄以外を `tokenize_ipa` に渡す。例えば `ɑpɑ/ɑbɑ` は字句解析単体では6音素・語末フラグなし、発話CLIでは2つの独立した入力になる。
- [tokenize_ipa と SkippedIpa](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/ipa.rs#L42) は限定したNFC表で正準分解・結合順序・合成を扱い、異表記を置換し、上下の結合弧を除く。続いて既知の二文字音素を先に確認し、続くU+0300〜U+036Fの結合記号を集める。既知記号は母音文字、複数文字の候補、[子音目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L282) の和集合。
- [字句の処理順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/ipa.rs#L156) では強勢を保留して次の母音に渡す。半角空白と `. , |` は直前の音素に語末を付け、コンマと縦棒は0.16秒の `_` を追加する。長音記号またはコロンで直前の明示長さを1.7倍する。初回の基準は母音文字で始まる音素が0.15秒、その他が0.09秒。直前の母音に鼻音化・息漏れの結合記号が付く。口蓋化は声門音を除く子音、`ʱ` は有声の閉鎖音または破擦音で適用される。`ʰ` と `˭` は直前の要素の有気フラグを上書きする。
- 診断は未知記号、受理したが合成用の定義がない音素、適用外の修飾に分かれ、各区分で初出順・重複なし。全体で認識できる母音の判定には[較正表と二重母音の展開](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L158)を使う。[plan_utterance](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L320) はこの音素列を受け、長さを決めてから二重母音を展開する。
- 上流で確認するテストは未対応記号、発音修飾、破擦音、有気・無気の扱いを検査する。[skipped_ipa](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/skipped_ipa.rs)・[sound_marks](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sound_marks.rs)・[aspiration](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/aspiration.rs)・[affricates](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs)

## 実装前の予測と判定

[登録ケース](../cases/ipa-tokenization.json) でVCV5組、無空白のスラッシュ、二重母音・破擦音、修飾、長音の重なり、非ASCII空白、空入力、適用外の記号、全目録を比較する。固定上流を先に実行し、予測に使った表と記号数を確認した。上流の音素・強勢・長さ・フラグ、診断と発話分割を一致させる。手書きの予測に加え、上流の全108記号に12種類の修飾を組み合わせて照合する。

原文上の位置は追加の観測項目。0始まりで終端を含まないUTF-8バイト範囲を使う。音素の範囲は字句として読んだ表記と同時に読んだ結合記号を含む。保留した強勢、別に読んだ長音や語末記号は音素の範囲へ加えない。コンマと縦棒で追加した休止はその記号の範囲を持つ。診断は上流の一覧に加えて出現ごとの範囲を残し、未対応記号の重複も調べられる。正準結合順序で並べ替えた範囲を統合する場合は、元のバイト範囲全体で囲む。

## 実装と検証結果

[候補の字句解析](../crates/vocal-core/src/phonetics/ipa.rs) は正準化の各文字に原文範囲を伝え、合成・別表記の置換では関係する範囲を統合する。合成用の定義の有無は、子音目録、較正母音、上流の展開表から得る。候補の表は [catalog.generated.json](../crates/vocal-core/src/phonetics/ipa/catalog.generated.json) と [nfc.generated.json](../crates/vocal-core/src/phonetics/ipa/nfc.generated.json)。前者は[上流プローブ](../tools/upstream_ipa_probe.rs) の `--catalog` で取得し、後者は固定上流の既存表のSHA-256を照合した。どちらも [MITの通知](../LICENSE-CHIMERA) とともに保存する。

[登録した入力と結果](../runs/ipa-tokenization-20261119-b/summary.json) で、15入力の音素・休止208個、発話19組、診断の出現45件を確認した。全108記号と12種類の修飾の1,296入力も通過。上流との音素列、強勢、明示長さ、修飾フラグ、診断一覧と発話分割に差はなかった。バイト位置の一致は登録した原文範囲と独立したUTF-8境界検査で判定した。[候補の位置付きJSON](../runs/ipa-tokenization-20261119-b/artifacts/tokenization.json)・[上流の公開APIの結果](../runs/ipa-tokenization-20261119-b/artifacts/upstream-tokenization.json)

- `ɑpɑ/ɑbɑ` の字句列では両側を続けて読めるが、発話を分けると元の入力のバイト範囲 `[0,5)` と `[6,11)` に分かれる。
- `ʏ` には合成用の定義がなく、`ʏː` の字句は明示長さ0.255秒を持ち、`noSound` の診断が付く。音を持たない字句が計画時刻にどう効くかは次の工程で測る。
- 未知記号 `🙂` を2回含む例では、上流互換の一覧には1回だけ表示する。候補の診断出現にはバイト4〜8と8〜12を保持した。
- NFCをIPAで使う表に限定するため、例えば `A` と結合アキュートはそのまま `A` の診断となり、明示的に入力した `Á` は別の未知記号となる。これは固定上流と同じ挙動。

コマンド、上流版、入力、候補ソース、表データ、出力のハッシュは[実行記録](../runs/ipa-tokenization-20261119-b/manifest.json)に収録した。
