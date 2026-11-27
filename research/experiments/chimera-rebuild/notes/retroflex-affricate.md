# そり舌破擦音 /tʂ/ の閉鎖と帯気

参照版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。先行の /ʂ/ は61項目が通過し、診断句「四是吃字人爱」に /tʂ ɻ ʔ/ が残った。 /tʂ/ の解放はその較正済み /ʂ/ の調音目標を使う。[先行結果](../runs/retroflex-fricative-20261120-repeat/summary.json)・[事前登録](../cases/retroflex-affricate.json)

## 音素から調音まで

上流のCLI `render::speech` は `tokenize_ipa` で `tʂ` を一つの音素として読み、 `plan_utterance` に渡す。既定長は140 msでKlatt表の個別項目がない。母音間の語中子音として最小84 msに伸縮幅56 msの0.85倍を加え、標準発話の区間は131.6 msになる。話速を上げる条件では音素区間と調音ランプ・解放保持が短くなる。[発話の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[IPAの複合音素](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/ipa.rs#L10)・[Klattの時間配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L122)

歌唱では `sung_lyrics` が漢字を `lyrics_to_syllables_with` に渡す。固定辞書で「知」は `zhi1`、「吃」は `chi1`。 `pinyin_syllable` は両者に声母 /tʂ/ と核 /ʅ/ を設定する。zh は無気・明示80 ms、ch は有気・要求VOT 90 msを指定する。 `plan_song` は明示長を優先し、ch には140 msの0.8倍の112 msを使う。どちらも声母の終端で音符の拍に届き、譜面のMIDI番号から決まるF0を使う。構造化譜面では両者に同じ声母長を明示できる。[歌詞の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L63)・[声母と時間の指定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L157)・[歌唱の音素配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L28)

区間を秒で `[a,b]`、切替を `s = a + 0.45(b − a)`、解放区間の起点を `r = max(a,s − 0.015)` とする。閉鎖は舌先X・Y `(5.45,10.05) cm`、無次元の反り0.95を速度倍率2で動かす。主目標の区間は `[a−0.031,max(a+0.010,s−0.020)]`。続く解放は /ʂ/ の舌先X 5.45 cm、体型別の舌先Y 9.730、9.738、9.750 cm、反り0.90へ速度倍率1.4で遷移する。区間は `[r−0.008,max(r+0.010,b)]`。両方とも強さ40、立上り30 ms、立下り18 msと解放保持45 msを使う。舌体は母音からの寄与を受け、口蓋化を指定すると /j/ の舌体X・Yを開大の終了まで重ねる。[目録の閉鎖と解放](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L219)・[破擦音の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L472)・[主目標の作り方](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)

無指定のIPAでは区間の15%から0.36 cm²の開大を指示し、終端に向けて最大30 msで閉じる。短い区間は開大の保持がなくなり、その区間内で閉じる。無気・有気の指定がある場合は区間の25%から開大し、無気は0.22 cm²を終端4.8 ms後まで保持して20 msで閉じる。有気は0.36 cm²を終端 `max(0,0.4 × 0.05 + 0.09 − 0.05) = 60 ms` 後まで保持し45 msで閉じる。指示が消える終端はそれぞれ音素終端から24.8、105.0 ms。声門が周期発声に戻る時刻は気道・呼気・声門の連成から別に測る。[開大と口蓋化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L508)・[無指定の閉じ方](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L678)

## 観測と事前の予測

各制御更新でスコアから舌先の座標と反りを動かし、口腔断面へ変換する。閉鎖で有効な枝流量が減り、狭窄が開くと正の狭窄断面を使って音源が登録される。狭窄音源の利得は体型換算面積0.35〜0.90 cm²の平滑曲線と枝の接続から計算する。歯の音源は歯までの距離・面積で別に重み付けされるため、解放後の主判定は狭窄源の活動で行う。枝流量・圧力注入・声門面積パルス・放射の各系列で順序を追う。[声道の反り](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L858)・[狭窄と歯の乱流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[声門と放射の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)

成人男女の標準発話で、閉鎖セルの両隣の流量停止、開口、狭窄乱流、周期発声の順を予測する。自然な単音対と声母を112 msにそろえた対照の両方で、有気の開大指示が80.2 ms長く残り、実測の周期復帰は20 ms以上遅れると予測する。等長対は帯気指定とVOTだけが異なる。同じ境界で測るため、音素長が違う自然な単音対の差と照合できる。上流の `sounds` は単一の音素化と /ʂ/ 解放を照合し、 `apical` は `zhi1`・`chi1` を含む歌唱で拍前後の舌先を検査する。このケースでは閉鎖・狭窄・周期復帰も追加で測る。[目録と字句解析の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sounds.rs)・[歌唱時の舌先の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/apical.rs#L57)

## 実装と実測

`affricate_gestures` にそり舌の閉鎖目標を加え、解放の舌先目標は /ʂ/ と同じ配列から計算する。声門・口蓋化の包絡と気道の更新は既存の仕組みを使う。CLIとWASMで /tʂ/ 単独の入力が乱流を有効にし、CSVでは舌先の反り、口腔セルごとの最小断面と枝流量、狭窄と歯の乱流が見える。固定上流の計測プログラムにも同じ観測点を追加した。[合成コア](../crates/vocal-core/src/phonetics/speech.rs#L406)・[共通の解放目標](../crates/vocal-core/src/phonetics/speech.rs#L759)・[上流用観測プログラム](../tools/upstream_bilabial_probe.rs#L257)

成人男女の /ɑtʂɑ/ では最長の連続閉鎖が6.75、6.27 msで、閉鎖セル両隣の枝流量は0 cm³/s。開口は計画の45%切替より31.85、23.26 ms早く、狭窄乱流が開口の0.85、4.83 ms後、周期パルスが開口の111.08、105.04 ms後に現れた。同じ成人男性の先行 /ɑtsɑ/ は閉鎖が40.48 ms、開口が切替の1.16 ms前だった。23 msに縮めた口蓋化の /tʂ/ は閾値以下の閉鎖が1出力フレーム、約0.021 msだった。この条件は標準発話の閉鎖長の基準64フレームを下回り、登録した計画・内部状態・PCMの照合は通過した。[そり舌破擦音の発話](../runs/retroflex-affricate-20261120-a/summary.json)・[歯茎破擦音の発話](../runs/alveolar-affricate-20261120-repeat/summary.json)

| MIDI 57の単音譜 | 無気 | 有気 | 有気の遅れ |
| --- | ---: | ---: | ---: |
| 開大指示が音素終端から残る時間 | 24.8 ms | 105.0 ms | 80.2 ms |
| 自然な声母長80・112 msでの周期復帰 | 32.125 ms | 104.875 ms | 72.750 ms |
| 声母長112 msでそろえたときの周期復帰 | 32.0625 ms | 104.875 ms | 72.8125 ms |

等長対では実測閉鎖がともに1,102フレーム、約22.96 msで、舌先X・Y・反り、口腔最小断面と選択音源セルの時系列が一致した。両 `voicing.csv` の該当する列を全出力フレームで引いた最大絶対差は0。計画切替または実測開口の遅い方から同じ窓で数えると、狭窄乱流は両方とも4,109フレームで活動した。音素長と調音をそろえても、有気指定で周期発声の復帰が遅れた。[単音対の判定と結果](../runs/retroflex-affricate-20261120-a/summary.json)・[両CSVの所在とハッシュ](../runs/retroflex-affricate-20261120-a/manifest.json)

4発話と5譜例の全ジェスチャーは固定上流と一致した。狭窄音源の登録フレームは独立式と一致し、歯への音源の帯域上限との差は `1.82×10⁻¹² Hz` 以下だった。加工前PCMの固定上流との差は最大 `9.31×10⁻¹⁰`。二音譜では声母開始前のフレーム0で放射流量の時間差分に `4.75×10⁻¹² cm³/s²` の差が観測され、最初に異なるPCMのビットはフレーム4,114だった。許容差を超える内部状態とPCMはなかった。実時間Chromiumで「知 吃」のPCM 91,200サンプルがCLIと保存ケースの再演でビット一致し、内部状態1,425点も照合した。[105項目の結果](../runs/retroflex-affricate-20261120-a/summary.json)

固定上流の関連23試験、候補の22試験とClippy、既存の /ts/ と /ʂ/ の歌唱の回帰8項目が通過した。既存の歌唱は計画JSON、時系列、PCMのハッシュを保存済みの実行と同じコマンドで照合した。[初回の手順と環境](../runs/retroflex-affricate-20261120-a/manifest.json)・[既存2譜例の回帰](../runs/retroflex-affricate-regression-20261120/summary.json)

研究ディレクトリで新しい実行IDを指定する。

```bash
python3 tools/measure_alveolar_affricate.py retroflex-affricate-local-1 --retroflex
```

スクリプトを絶対パスで `/tmp` から起動した再実行も105項目を通過した。CLIと固定上流の各計測値、時系列・PCM・WASMの67ファイルのSHA-256が初回と一致した。「四是吃字人爱」の音響未対応は /ɻ ʔ/ になった。[再実行の環境と出力ハッシュ](../runs/retroflex-affricate-20261120-repeat/manifest.json)・[再実行の判定](../runs/retroflex-affricate-20261120-repeat/summary.json)
