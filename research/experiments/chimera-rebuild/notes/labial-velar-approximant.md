# /w/ の丸め・舌体・母音への遷移

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第5段階の `Hello world` に必要な /w/ を、唇と舌体の組み合わせから調べる。

## 固定版の処理

1. `render::speech` はIPAを、`render::say` は辞書から区切った英語を `plan_utterance` に渡す。`inventory::phoneme` の /w/ は有声の両唇軟口蓋接近音。成人男性の目標は、唇の開き0.28 cm、突き出し1 cm、幅の正規化値0.05、舌体 (2.45, 7.45) cm。5軸がすべて優勢。成人男性には目録の基準値を使う。発話時間の目録では固有長80 ms、短縮時の下限60 msを使う。発話位置と前後の音素で区間を調整する。[IPA入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[英語入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[音素](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L223)・[時間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L72)
2. `oral_gestures_into` は優勢5軸を一つのスコアに置く。音素を `[a,b]` とすると保持は `a−0.008` から `max(a+0.010,b)`。入りと出の余弦ランプは30 msと18 ms、強さ40、速度1.3、速度延長45 ms。話速が1を超えるとランプと速度延長を話速で割る。口蓋化の指定があっても、舌体の2座標はすでに /w/ が担う。通常の /w/ は有声で、口腔の目標を主に変える。発話末では息を切る開大が終端の45 ms後に来る。[口腔スコアの振り分け](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L483)・[目標と保持](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[口蓋化と話速](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L737)・[句末](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L597)
3. `HumanVoice::control` は64出力フレームごとに音素の目標を重ね、基準姿勢を重み0.05で加える。各唇軸を固有周波数11 Hzの臨界減衰とし、調音速度を掛けた角周波数で速度、位置の順に更新する。舌体の座標はそれぞれ12 Hzで動き、口蓋への接触補正を受ける。`HumanVocalTract::compute` は突き出しで唇端の輪郭を前へ動かし、幅の値を成人男性では `1.1+3.5×幅` cmに写す。開きと舌輪郭、顎などを合わせて面積を計算する。幾何連続性の上流テストは調音軸の掃引と母音間の遷移を検査する。突き出した下唇を唇歯音へ移す既知の不連続は別条件で記録されている。[制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[調音器の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)・[唇輪郭](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L805)・[幅](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1080)・[幾何連続性](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L119)

## 実装前の予測と判定

母音間の等速と1.8倍速、英語の語頭 `We.`、IPAの句末 /w/ を96 kHz内部・48 kHz出力で調べる。口端・口腔は閉鎖閾値0.0002 cm²より開き、/w/ の中央30%で唇の突き出しの中央値0.55 cm以上、幅0.45以下、有声化係数の中央値0.7以上を見込む。開き・突き出し・幅を独立したばねとスコアの計算に照合する。音素を55%進んだ時刻を中心とする24 msのPCMを、16 kHzへ変換して18次LPCで測る。/w/ に対して隣接する /ɑ/ のF1、`We.` の /i/ のF2は50 Hz以上高いと予測した。比較では周期変動と乱流を0とし、PCMの最大絶対差 `10⁻⁶`、77・128のホスト分割でバイト一致を判定する。

[等速](../cases/approximant-w.json)・[1.8倍速](../cases/approximant-w-fast.json)・[英語](../cases/approximant-w-english.json)・[句末](../cases/approximant-w-final.json)

## 実装と測定値

同じ5成分を一つのジェスチャーで指定し、既存の音素区間、母音合成、調音器、声道モデルを通した。CSVは出力フレーム `n` の最後の内部サンプルを処理した状態で、時刻は `(n+1)/48000` 秒。唇のばねを独立に計算して比べると、開き・突き出し・幅の全条件で最大差は `6.18×10⁻¹⁴` だった。速度保持窓に母音が重なる部分も計算の対象に含めた。[発話計画](../crates/vocal-core/src/phonetics/speech.rs)・[音声CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[独立計算と比較器](../tools/measure_labial_velar.py)・[上流のMIT通知](../LICENSE-CHIMERA)

| 条件 | /w/ 中央30%の口腔最小断面 | LPCで推定したフォルマントの推移 | 固定上流とのPCM最大絶対差 |
| --- | ---: | --- | ---: |
| [等速 ˈɑwɑ](../runs/approximant-w-20261119-a/summary.json) | 0.2091 cm² | F1 419.64 → 716.70 Hz | `3.64×10⁻¹²` |
| [1.8倍速 ˈɑwɑ](../runs/approximant-w-fast-20261119-a/summary.json) | 0.3186 cm² | F1 473.37 → 694.99 Hz | `2.91×10⁻¹¹` |
| [英語 We.](../runs/approximant-w-english-20261119-a/summary.json) | 0.1830 cm² | F2 981.72 → 2228.65 Hz | `3.64×10⁻¹²` |
| [句末 ˈɑw](../runs/approximant-w-final-20261119-a/summary.json) | 0.1888 cm² | F1 715.54 → 402.42 Hz（先行 /ɑ/ → /w/） | `7.28×10⁻¹²` |

等速の /w/ 中央の突き出しの中央値は0.9693 cm、幅0.0786、有声化係数は約1。1.8倍速では突き出し0.8857 cm、幅0.1566で、短縮時の口腔はより広かった。`We.` は `wi` から48 kHz・30,838フレームのWAVになった。すべての窓で登録した次数のフォルマントを拾えた。数値は20 ms台の移動中のPCMをLPCで測ったもので、音響共鳴を固定姿勢で測るときの条件は母音ベンチマークに示す。句末 /w/ の脱力は音素終端の45 ms後に始まり、最後の20 msのPCMピークは `3.15×10⁻¹¹` だった。[英語のWAV](../runs/approximant-w-english-20261119-a/artifacts/pcm-128.wav)・[母音の固定姿勢計測](ten-vowel-benchmark.md)

4条件を `/tmp` から再実行し、波形・計画・時系列・結果の40ファイルが初回とバイト一致した。77フレームと128フレームのホスト分割でも、同じWAVと出力段CSVを得た。各実行の入出力はマニフェストのSHA-256と照合した。声門摩擦音、歯茎破裂音、基準IPAの回帰で30ファイル、英語発音の回帰で16ファイルが一致した。英語発音JSONの差は /w/ の対応状態を表す43箇所だった。[再実行の記録](../runs/approximant-w-english-20261119-b/manifest.json)・[英語の回帰](../runs/english-frontend-20261119-e/summary.json)・[基準IPAの回帰](../runs/bilabial-nasal-vcv-20261119-f/summary.json)

候補の `cargo test --locked --workspace` とClippy、上流の `speech_quality`、`golden_phonetics_text`、`geometry_continuity` の既定テストが通過した。突き出した下唇の唇歯音への移行を検査する既知の1件は、固定上流の既定設定で除外される。[上流テストの結果](../runs/approximant-w-20261119-b/artifacts/upstream-tests.log)・[除外条件](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L274)
