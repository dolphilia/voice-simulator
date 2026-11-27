# 歯茎破擦音 /ts/ の閉鎖と解放

参照版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第7段階の中国語歌唱に必要な声母を一つ追加する。既存の鼻音韻尾の再実行は152項目を通過し、「四是吃字人爱」の未対応一覧に /ts/ が残っていた。[先行計測](../runs/mandarin-nasal-rhymes-20261120-repeat/summary.json)・[事前登録](../cases/alveolar-affricate.json)

## 入口と状態の更新

音声 CLI の `speech` は `tokenize_ipa` と `plan_utterance` へ進む。字句解析で `ts` と連結弧付きの `t͡s` を一音素にする。既定の区間長は140 ms、Klatt 表に個別値が無いため語中・非クラスタの /ɑtsɑ/ は最小84 msに伸縮幅56 msの85%を加えた131.6 ms。等速を超えると区間長に加えて調音のランプと解放保持も話速で除す。[上流の音声入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[IPA](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/ipa.rs#L10)・[時間配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L122)

歌唱 CLI の `sung_lyrics` は漢字入力で辞書を読み、`lyrics_to_syllables_with` から `pinyin_syllable` に至る。固定辞書で「资」は `zi1`、「词」は `ci2`。両者の声母を `ts`、核を舌尖母音 `ɿ` とし、z に無気・明示80 ms、c に有気・要求VOT 90 msを付ける。 `plan_song` は明示長を保持し、c のように明示長が無いと既定140 msに0.8を掛ける。拍より前に声母を置き、核の開始を拍に合わせる。この版の歌唱のF0は譜面の音高に従うため、この2字を同じMIDI番号で比較できる。[歌詞 CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L63)・[中国語の声母と既定VOT](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L156)・[歌唱の時間配分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L28)

区間を秒の `[a,b]` とし、切替点を `s = a + 0.45(b − a)`、解放フェーズの起点を `r = max(a,s − 0.015)` とする。目録 `inventory::phoneme` の閉鎖は舌先座標 `(6.25,9.68) cm`、解放は /s/ の舌先X 6.3 cm・顎 0.3 cmと体型別に較正された舌先Y。 `planner::oral_gestures_into` は各フェーズの主目標を強さ40、立ち上がり30 ms、立ち下がり18 ms、解放時の保持45 msで足す。閉鎖の主目標は `[a − 0.031,max(a + 0.010,s − 0.020)]`、速度倍率2。解放は `[r − 0.008,max(r + 0.010,b)]`、速度倍率1.4。どちらも主目標に続けて舌体 `(3.2,7.4) cm` の補助目標を区間そのものに置く。舌体の強さ1.2と50 msのランプは、周囲の母音に舌体を追従させながら歯茎側へ引く。[目録と体型較正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L189)・[破擦音計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L472)・[調音ジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)

IPAで気音を指定しない場合、開大目標0.36 cm²は区間の15%から入り、終端へ向け最大30 msで下がる。短区間では保持時間が0になり、立ち下がりも短くなる。明示指定がある場合は破裂音と共通の枝で、開始は区間の25%。無気は0.22 cm²で終端4.8 ms後まで保持して20 msで下がり、有気は0.36 cm²で終端 `max(0,0.4 × 0.05 + 0.09 − 0.05) = 0.060 s` 後まで保持して45 msで下がる。口蓋化があれば開大指示の終わりまで /j/ 方向の舌体目標を重ねる。これらの時刻は指示の端点で、声門の周期パルスは結合した発声器を実行して測る。[開大と口蓋化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L508)

`HumanVoice::control` はスコアの目標と重みを調音器へ渡し、声道形状と気道の面積を更新する。 `HumanAirway::update_noise` は正の最小断面、歯までの距離、面積から歯に達する噴流の重みを決める。断面積と流量から得た速度を `v = |U|/A`、噴流直径を `D = 2√(A/π)`、歯での渦の幅を `δ = max(D,0.17d)` とすると、この実装の帯域上限は `vD/δ²`。各枝への雑音注入が圧力と流量を変え、放射と間引きを経てPCMに出る。閉鎖の幾何、歯への注入、声門周期の順序はそれぞれ別の系列から検出する。[声道と乱流](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)

## 先に立てた予測

成人男女の標準発話で口側の閉鎖、両隣の枝流量の停止、歯の乱流、周期パルスの順を確認する。2つの単音譜では「词」の開大指示が「资」より80.2 ms長く終端の先まで残り、実測した周期の復帰も終端基準で20 ms以上遅いと予測する。短縮・口蓋化と混合体型の高速条件はジェスチャーの式と固定上流照合で判定する。上流の発音テストは無気破擦音の短縮を含み、破擦音の音響テストは /tʃ dʒ/ の母音への移行を測る。 /ts/ の音響は今回の専用条件で測る。[中国語の上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/mandarin.rs#L149)・[上流の破擦音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs#L76)

## 実装と実測

再実装の `affricate_gestures` に2つの舌先主目標と2つの舌体補助目標を加えた。閉鎖は既存の /t d n/ と座標を共有し、解放は /s/ の較正目標を共有する。既存の破擦音と同じ経路で既定・明示開大を処理し、無気・有気と口蓋化までCLIとWASMで同じ計画を使う。両入口で /ts/ の既定乱流を有効にし、計測用CSVは口腔セル、両隣の枝流量、歯の乱流、声門面積を出す。[合成コア](../crates/vocal-core/src/phonetics/speech.rs#L404)・[CLIの観測点](../crates/vocal-cli/src/timing_case/speech_voice.rs#L940)・[WASMの乱流設定](../crates/vocal-wasm/src/planning.rs#L237)

成人男女の /ɑtsɑ/ では閉鎖が40.48、40.44 ms続き、閉鎖の両隣の枝流量は0 cm³/s。開口から0.81、1.04 msで歯の乱流が活動し、周期パルスが開口から89.00、87.69 msで戻った。歯の乱流の帯域上限は両体型で独立式との差が `3.64×10⁻¹² Hz` 以下だった。[4つの発話と独立式の結果](../runs/alveolar-affricate-20261120-a/summary.json)

| 同じMIDI 57の単音譜 | 资 zī | 词 cí |
| --- | ---: | ---: |
| /ts/ の計画長 | 80 ms | 112 ms |
| /ts/ 終端から開大指示が消えるまで | 24.8 ms | 105.0 ms |
| /ts/ 終端から実測の周期パルスまで | 32.125 ms | 104.875 ms |
| 同じ計測窓の定義による歯の乱流フレーム数 | 3,304 | 4,156 |

周期復帰の差は72.75 msで、開大指示の差は80.2 ms。声母長も32 ms異なるため、この結果には2つの入力変更が含まれる。開大だけの寄与を測るには、同じ明示長で `aspirated` と `vot` だけを切り替える対照が必要になる。[単音譜の比較](../runs/alveolar-affricate-20261120-a/summary.json)

23 msの口蓋化条件では、登録時の閉鎖検出窓が終わるまで狭窄が残り、標準発話用の判定は不通過だった。補足として両方の `short-palatalized/voicing.csv` で `(frame + 1) / 48000 ≥ t1` かつ `oral_minimum_cm2 ≥ 0.0002` の最初の行を探すと、候補・上流ともフレーム14,337、区間終端の5.708 ms後に開口した。短縮条件の登録判定はジェスチャー・内部状態・PCMの上流照合で、これらは通過した。[時系列の所在とハッシュ](../runs/alveolar-affricate-20261120-a/manifest.json)

全条件で計画ジェスチャーが固定上流の値と一致し、加工前PCMの最大絶対差は `1.86×10⁻⁹`。2音の歌唱は調音開始より前のフレーム0で放射流量の時間差分に `4.75×10⁻¹² cm³/s²` の差を観測し、最初のPCMのビット差は4,114フレームだった。登録した許容差を超える内部状態やPCMは無かった。Chromiumの通常の歌唱操作で「资 词」の加工前PCM 91,200サンプルがCLIと保存ケースの再演でビット一致した。診断句「四是吃字人爱」の音響未対応は /tʂ ɻ ʂ ʔ/ になった。[実行環境・手順](../runs/alveolar-affricate-20261120-a/manifest.json)・[69項目の結果](../runs/alveolar-affricate-20261120-a/summary.json)

研究ディレクトリで新しい実行IDを指定する。

```bash
python3 tools/measure_alveolar_affricate.py alveolar-affricate-local-1
```

上流の `mandarin`、`affricates`、`consonant_artifacts` は計18試験が通過した。候補の `cargo test --locked --workspace` は21試験が通過し、Clippyも通過した。既存の歯茎硬口蓋破擦音のCLI回帰は36項目を通過した。[上流試験を含む実行記録](../runs/alveolar-affricate-20261120-a/manifest.json)・[既存破擦音の回帰](../runs/alveolopalatal-affricates-regression-20261120-ts/summary.json)

同じコマンドを絶対パスで `/tmp` から起動し、69項目が再び通過した。CLI・上流の各計測値と時系列、PCM、WASMの計53ファイルのSHA-256が初回と一致した。ブラウザで1,425点の主要内部状態も照合した。[再実行の環境と出力ハッシュ](../runs/alveolar-affricate-20261120-repeat/manifest.json)・[再実行の結果](../runs/alveolar-affricate-20261120-repeat/summary.json)
