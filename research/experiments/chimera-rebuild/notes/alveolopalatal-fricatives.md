# 歯茎硬口蓋摩擦音 /ɕ ʑ/

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。韓国語歌唱の /ɕ/ と、後続の破擦音 /tɕ dʑ/ の解放部分に使う狭窄を準備する。[事前登録](../cases/alveolopalatal-fricatives.json)

## 計画と制御

- 歌詞から音節を作るとき、韓国語の ㅅ は後続の母音や渡り音に応じて /ɕ/ になる。「시야」は /ɕi.ja/ と予測する。IPA 直入力では /ɕ/ と /ʑ/ の両方を母音で挟む。[韓国語の音素選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/korean.rs#L248)・[音節化の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/syllables.rs#L98)
- `inventory::phoneme` は体型別の較正を適用する。舌先の前後位置は 5.85 cm、舌体は (3.6, 7.75) cm、顎は 0.3 cm、唇の突出は 0 cm、幅の制御値は 0.7。舌先高の既定値 9.5 cm は較正値で置き換わる。較正時の面積目標は /ɕ/ が 0.17 cm²、/ʑ/ が 0.19 cm²。体型補間は成人男性・成人女性・子どもの重み `[(1−c)(1−f), (1−c)f, c]` で行う。[音素表と体型補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L215)・[較正値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/consonantTargets.generated.json)
- `planner::oral_gestures_into` は七つの調音軸を一つの目標に束ねる。区間 `[t₀,t₁]` に対し、開始は `t₀−8 ms`、終了は `max(t₀+10 ms,t₁)`。立ち上がり 30 ms、解放 18 ms、解放ランプが終わった後も追従速度の倍率を維持する時間 45 ms、強さ 40、追従速度の倍率 1.3。話速が1を超えるとランプと保持時間を話速で割る。別の声門開大ジェスチャーは `t₀−15 ms` に始まり、/ɕ/ は `t₁+5 ms` まで強さ6で 0.30 cm²、/ʑ/ は `t₁` まで強さ3で 0.09 cm²。制御ブロックごとに、開大目標に活動度と体型の面積倍率を掛けて基礎開大に足す。実測の声門面積は呼気と振動でも変化する。[声門の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L530)・[口腔の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)

## 狭窄から乱流への結合

`HumanVoice::control` の姿勢更新で `HumanAirway::update_noise` が咽頭・口腔を走査し、正の最小断面積 `A` とそのセル中心 `s` を選ぶ。体型の縮尺を `k`、歯までの実距離を `L` とし、`smooth(a,b,x)` を区間外で飽和する三次補間とする。歯の重みは `smooth(1,1.5,L/k) · [1−smooth(2.6,4,L/k)] · [1−smooth(0.2,0.5,A/k²)]`。本管の乱流配置が有効で、重みが 0.001 を超えると歯の乱流源を登録する。[登録と配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)

帯域は設定時点の枝流量 `U` (cm³/s) と枝面積 `Aⱼ` (cm²) を使う。噴流径 `D=2√(Aⱼ/π)`、歯に届く渦の径 `δ=max(D,0.17L)`、上限 `F=|U|D/(Aⱼδ²)` (Hz) とし、帯域によるゲイン補正は `√(5000/max(F,1200))`。内部サンプルごとに `AirwayNetwork::compute_noise` がレイノルズ数から注入強度を求め、帯域処理した乱数を正流なら歯、逆流なら狭窄の後方に圧力として加える。したがって歯の乱流源の登録と、流れに伴う圧力注入の有無を別々に測る。[帯域設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L381)・[サンプルごとの圧力注入](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)

## 予測と反証

成人男性で /ɕ/ の区間中央の声門開大が /ʑ/ より 0.1 cm² 以上大きく、通常の発話の区間中央では歯の音源が過半のフレームで活動する。乱流係数0では歯の音源を幾何学的に登録しても、強度と圧力注入が0になる。体型3種と補間体型は較正目標と歯の帯域・ゲインを独立計算する。歌唱では「시야」の音節、/ɕ/ 中の圧力注入、実ブラウザの加工前 PCM と保存ケースの再実行を照合する。上流の有声摩擦音の試験と同じ1 kHzの二段ローパスで声の低域を観測する。上流の試験の数値閾値は /z v/ のものなので、/ʑ/ の低域は測定値を記録する。[上流の有声摩擦音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voiced_fricatives.rs#L29)

## 実装と実測

再実装の `speech::sibilant_gestures` で七軸の目標を既存の開放子音ジェスチャーへ渡し、/s z/ と共通の声門開大を使う。CLI と WebAssembly の IPA では音素列から乱流を有効にする。歌唱には既存の乱流設定が使われる。固定上流の観測プローブと候補CLIの両方に、顎、舌、唇、口腔セルごとの断面と乱流の観測を接続した。[調音計画](../crates/vocal-core/src/phonetics/speech.rs#L571)・[候補CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs#L886)・[WASMのIPA計画](../crates/vocal-wasm/src/planning.rs#L237)・[上流観測プローブ](../tools/upstream_bilabial_probe.rs#L226)

48 kHz の出力、96 kHz の内部計算で測定した。発話の数値は子音区間の25〜75%、歌唱の歯への圧力は子音区間全体を集計した。声門開大は制御値の中央値、狭窄は乱流検出用の最小断面の中央値。低域は先行母音に対する1 kHz二段ローパス後の電力比。

| 条件 | 狭窄 (cm²) | 声門開大 (cm²) | 歯への圧力 RMS (dyn/cm²) | 低域 (dB) |
| --- | ---: | ---: | ---: | ---: |
| 成人男性 /ɕ/ | 0.1834 | 0.30225 | 31.75 | −27.80 |
| 成人男性 /ʑ/ | 0.2220 | 0.09225 | 12.61 | −11.48 |
| 成人女性 /ɕ/・話速1.35 | 0.1788 | 0.24482 | 16.80 | −22.39 |
| 子ども /ʑ/ | 0.1237 | 0.05052 | 5.00 | −6.11 |
| 補間体型 /ɕ/ | 0.1507 | 0.24755 | 19.20 | −26.51 |
| 成人男性 /ɕ/・乱流係数0 | 0.1834 | 0.30225 | 0.00 | −36.26 |
| 成人男性「시야」 | 0.1809 | 0.30225 | 33.50 | 比較母音なし |

通常の発話5条件は中央窓の全フレームで歯の乱流が活動した。乱流係数0の対照では狭窄の位置と面積、歯までの距離、音源登録がフレームごとに一致し、圧力注入は0になった。上限周波数はわずかに変わった。設定に参照される流量が乱流圧力を加えた履歴に依存するためと考えられる。人工的に枝流量を共通化した比較で、この解釈を確かめられる。[全観測値と判定](../runs/alveolopalatal-fricatives-20261120-a/summary.json)

固定上流との加工前PCMの最大絶対差は成人男性 /ʑ/ の `1.16×10⁻¹⁰`。独立計算による歯の上限周波数とゲインの差は全観測点で最大 `1.82×10⁻¹² Hz` と `1.96×10⁻²¹`。ブラウザの AudioWorklet で「시야」の91,200サンプルを取得し、CLI と保存ケースの再実行の両方にビット一致した。/ɕ/ は第1音の拍まで96 ms。ブラウザから得た8系列もCLI・固定上流と照合した。[固定上流とブラウザの実行](../runs/alveolopalatal-fricatives-20261120-a/manifest.json)・[保存ケース](../runs/alveolopalatal-fricatives-20261120-a/artifacts/browser/siya-case.json)

既存の /s z/ の回帰試験は全項目通過。各9ファイルのPCM・計画・観測系列が以前の通過版とバイト一致した。/z/ の要約はキー順だけが異なった。候補のワークスペーステスト18件、整形検査、Clippy、上流テスト17件が通過した。最初の起動ではシステムの Python に NumPy がなく、既存の研究用仮想環境に切り替えて実行した。[/s/ の回帰](../runs/sibilant-s-20261120-alveolopalatal-regression/manifest.json)・[/z/ の回帰](../runs/sibilant-z-20261120-alveolopalatal-regression/manifest.json)

研究ディレクトリと `/tmp` の両方から実行し、各65項目を通過した。PCM、ケース、内部系列など77ファイルが同じSHA-256だった。ブラウザの開始フレームと停止までの時間など、実時間の時計に依存する記録には差が出た。要約の数値差は停止までの時間 `0.704 → 0.70933 s` のみ。[別ディレクトリからの再実行](../runs/alveolopalatal-fricatives-20261120-repeat/manifest.json)
