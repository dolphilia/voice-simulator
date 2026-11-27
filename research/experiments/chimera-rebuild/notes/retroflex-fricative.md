# そり舌摩擦音 /ʂ/ の舌先と乱流

参照版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。前回は /ts/ の69項目が通過し、診断句「四是吃字人爱」に /tʂ ɻ ʂ ʔ/ が残った。 /ʂ/ は単独の声母に加え、次の /tʂ/ の解放に使われる。[先行計測](../runs/alveolar-affricate-20261120-repeat/summary.json)・[今回の事前登録](../cases/retroflex-fricative.json)

## 入力と調音スコア

上流の発話 CLI `render::speech` は IPA を字句解析し、`plan_utterance` へ渡す。歌唱 CLI `sung_lyrics` は漢字辞書の「四」`si4`、「是」`shi4` を `pinyin_syllable` へ渡し、声母を /s/ と /ʂ/、核を /ɿ/ と /ʅ/ に分ける。ここでの声調番号は歌唱のF0を動かさず、`plan_song` が音符の音高を使う。両声母の既定長は120 msで、歌唱は既定値に0.8を掛けた96 msを拍の前に置く。発話の /ʂ/ にはKlatt表の個別値がなく、母音間では `72 + (120 − 72) × 0.85 = 112.8 ms`。 /s/ はKlatt表の最小60 ms、既定105 msから98.25 msになる。[発話の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[時間配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L122)・[ピンインから舌尖母音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L287)・[歌唱の声母の長さ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L28)

`inventory::phoneme` では /ʂ/ の主目標を舌先X 5.45 cm、舌先Y 9.70 cm、反り0.9とする。較正ファイルがYだけを成人男性9.730 cm、成人女性9.738 cm、子ども9.750 cmに上書きし、混合体型では体型の重みで内挿する。 `planner::oral_gestures_into` は摩擦区間 `[a,b]` に、強さ40、速度倍率1.3、立ち上がり30 ms、立ち下がり18 ms、解放保持45 msの主目標を `[a−0.008,max(a+0.010,b)]` で置く。そり舌の定義は顎の主目標と歯茎音用の舌体補助目標を持たない。無声の声門開大0.30 cm²を `[a−0.015,b+0.005]` に強さ6、両側30 msのランプで重ねる。口蓋化を指定すると /j/ 方向の舌体X・Yが `[a,b]` に重なり、話速を上げると区間長とランプ・保持時間が短くなる。[子音の目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L189)・[体型混合](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L264)・[調音の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[声門・口蓋化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L529)

## 声道の断面と音源

`HumanVoice::control` のスコア合成と調音器更新後、`HumanVocalTract::compute` は反りを0〜1に収める。舌刃の二次ベジェの制御点を `(0.18 + 0.5 × 反り) × 体型スケール` cm上に置き、舌下輪郭の制御点は反りに比例して後ろへ動く。扇形の測線に舌組織が複数回交差するときは、上壁までの距離から組織の厚さを引いて空気の幅を得る。これは反った先端の下に空気がある形状にも適用される。断面に変換してから口腔・咽頭セルへ集約する。[反りと輪郭](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L858)・[測線と組織厚](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L949)

`HumanAirway::update_noise` は咽頭・口腔の正の最小断面を選び、体型換算面積0.35〜0.90 cm²の平滑遷移と枝の接続から狭窄乱流を登録する。歯の音源では、体型換算した上流距離が1.0〜1.5 cmで立ち上がり、2.6〜4.0 cmで下がる。面積が0.2〜0.5 cm²で増えるほど、歯に届く噴流も弱くなる。流量 `U` と面積 `A` から速度 `|U|/A`、直径 `2√(A/π)` を得て、渦の幅を直径と歯までの距離の17%の大きい方とした式で歯の帯域上限を決める。音源が登録されることと、流れによって圧力注入が発生することを別々に観測する。 `HumanVoice::render` は内部ステップごとに声門の圧差から面積を更新し、気道伝搬と放射を処理して間引いたPCMを返す。[乱流と帯域](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[音響更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

上流試験 `mandarin::apical_vowels_follow_their_consonant` は「四是」の母音の割付けを検査する。 `apical.rs` は3体型の舌尖母音の舌先目標が対応する摩擦音よりY方向に約0.11 cm低いこと、拍の25 ms前と250 ms後で姿勢変化が小さいことを確認する。周期性には60 ms窓の正規化自己相関を使う。今回もこの窓で母音部を測り、 /s/ と /ʂ/ の差は同じ母音を使うIPA発話でも確認する。[中国語の割付け試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/mandarin.rs#L127)・[舌尖母音の運動試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/apical.rs)

## 先に立てた予測

成人男性の同じ母音に挟まれた /s/ と /ʂ/ の中央区間を比べ、 /ʂ/ の舌先Xが0.4 cm以上後方、反りが0.7以上、正の最小断面と歯の距離が0.15 cm以上長いと予測する。狭窄乱流の活動は中央区間の25%以上、倍率0の対照は注入が0とする。「四 是」は拍と音高を一致させ、舌尖母音の姿勢と周期性を照合する。歌唱には核の /ɿ/ と /ʅ/ の違いも含まれる。独立式は音源の登録・利得・帯域を保存した状態から再構成し、上流比較は全ジェスチャー、内部状態と加工前PCMを対象にする。

## 実装と実測

再実装の `fricative_gestures` は、 /ʂ/ の3成分を主目標として既存の摩擦音の時間包絡に渡す。声門開大、口蓋化、気道の解法、雑音注入は既存実装を通る。CLIとWASMの通常入口で /ʂ/ を検出して乱流を有効にし、観測する場合は舌先の反りと狭窄源の枝の計算に必要なセル数・声道長もCSVに出す。[合成コア](../crates/vocal-core/src/phonetics/speech.rs#L748)・[CLIの観測点](../crates/vocal-cli/src/timing_case/speech_voice.rs#L953)・[WASMの乱流設定](../crates/vocal-wasm/src/planning.rs#L237)

成人男性の同じ母音に挟まれた2音で、中央30〜70%を測った。 /ʂ/ の舌先は0.848 cm後方にあり、選択された狭窄は歯から1.672 cm遠くなった。歯の音源はどちらも中央区間全体で活動したが、 /ʂ/ の歯側への雑音圧力は4.30 dyn/cm² RMSで、 /s/ の30.10 dyn/cm² RMSの約14%だった。狭窄源の圧力は9.73から13.06 dyn/cm² RMSに増えた。入力の音素を替えると舌先X・Y・反りと舌体の目標が同時に変わるため、各成分の寄与は個別に未測定。乱流倍率0では候補・上流とも舌先と狭窄の形状・音源の登録が変わらず、圧力注入は全区間で0になった。[発話と乱流対照の結果](../runs/retroflex-fricative-20261120-b/summary.json)

「四 是」の音高は両方MIDI 57。 /ʂ/ の拍25 ms前から /ʅ/ の拍250 ms後までに、舌先の反りは0.890から0.857へ変わり、X方向の変位は0.024 cmだった。拍150〜330 ms後のPCMから得た周期性は「四」の /ɿ/ で0.9238、「是」の /ʅ/ で0.9239。予定した舌先の変位・周期性をどちらも満たした。実時間Chromiumから出た加工前PCM 91,200サンプルはCLIと書き出したケースの再演とビット一致し、1,425点の内部状態も照合できた。[歌唱・ブラウザの結果](../runs/retroflex-fricative-20261120-b/summary.json)

4発話と歌唱で、計画は固定上流と一致し、狭窄乱流の独立計算と観測の登録フレームも一致した。歯の帯域上限の独立式との差は `3.64×10⁻¹² Hz` 以下。候補と上流のPCMの最大絶対差は `1.16×10⁻¹⁰`。通常発話の比較では加工前PCMのビット差が12,167フレームで始まり、先行して放射流量の時間差分にフレーム0で `4.75×10⁻¹² cm³/s²` の差を観測した。記録した全条件で許容差を超えた内部状態と波形は無かった。[全61項目と差の記録](../runs/retroflex-fricative-20261120-b/summary.json)・[出力ファイルとハッシュ](../runs/retroflex-fricative-20261120-b/manifest.json)

初回は口腔セルの比較器が要求する閉鎖閾値を渡していなかったため、音声取得後に中断した。先行ケースの0.0002 cm²を参照し、調音の反りの比較キーと、声門ポートの音源番号 `−2` の扱いも修正した。事前登録した入力と判定条件で61項目を通過した。固定上流の関連20試験、候補の22試験とClippy、既存 /s/ の7項目も通過した。[初回中断の記録](../runs/retroflex-fricative-20261120-a/manifest.json)・[既存 /s/ の回帰](../runs/sibilant-s-retroflex-regression-20261120/summary.json)

研究ディレクトリで新しい実行IDを指定する。

```bash
python3 tools/measure_retroflex_fricative.py retroflex-fricative-local-1
```

スクリプトを絶対パスで `/tmp` から起動した再実行でも61項目が通過した。同じ時系列、PCM、WASMの39ファイルのSHA-256と、CLI・固定上流の計測値が一致した。「四是吃字人爱」の音響未対応は /tʂ ɻ ʔ/ になった。[再実行のコマンドと出力ハッシュ](../runs/retroflex-fricative-20261120-repeat/manifest.json)・[再実行の数値と判定](../runs/retroflex-fricative-20261120-repeat/summary.json)
