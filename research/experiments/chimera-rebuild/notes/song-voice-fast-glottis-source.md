# 短い音符の歌唱で声門の乱流源だけを抑える

短音の `Pop Dee` では、全体の乱流係数を0から1にしたときの最初の差が、0始まりで第20,294フレームの声門側の枝圧に現れた。今回は全体の係数を1に保ち、声門乱流源のゲインに掛ける倍率だけを0にする。波形の差が最初に現れる場所と、残る乱流源を調べる。[前回の計測](worklet-live-song-fast-turbulence.md#実測)・[事前登録](../cases/song-voice-fast-glottis-source.json)

## 呼び出しと状態の更新

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `Engine::render()` は内部ブロック境界で予定を進め、`HumanVoice::render()` が1出力フレームにつき内部サンプルを2回生成する。このケースでは出力48 kHz、内部96 kHz。制御更新の `HumanVoice::control()` はスコアを評価し、`HumanAirway::apply()` で声道断面を更新する。`commit()` の最後に呼ばれる `update_noise()` は、声門ポートを励起枝として、咽頭側を順方向、気管側を逆方向の注入先に選ぶ。ゲインの既定値は `3.2 × 10⁻⁶`、帯域は高域通過300 Hzと低域通過3,500 Hz。狭窄と歯の乱流源は、声道の幾何と流れに応じて別に決まる。[上流エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[発声の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs)・[乱流源の配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs)

音響網は枝の流量を進める前に、`compute_noise()` で前の流量 `U`（cm³/s）と開口面積 `A`（cm²）から `Re = 2 × |U| ÷ (ν × √(πA))` を計算する。`Re > 1800` の開いた枝で、レベルは `源のゲイン × 全体の係数 × √(96000 ÷ 内部レート) × 飽和させた (Re² − 1800²)` になる。白色雑音の乱数列と高域・低域フィルタの状態は、レベルが0の間も進む。したがって今回は源を配列から外さず、ゲインだけを0にして乱数の呼び出し順と保持するフィルタを揃えた。各枝の圧力源の配列は共有されるので、声門側の枝圧は他の源の寄与を含み得る。[上流の乱流計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[再実装の乱流計算](../crates/vocal-core/src/airway/network/turbulence.rs)

再実装ではCLIの `song_voice.turbulence.glottis_gain_multiplier` を `ArticulatedVoice::enable_turbulence_with_glottis_gain()` に渡す。調音や接触補正で乱流源を登録し直すたびに、保持している倍率が声門源に適用される。省略時の倍率は1。比較プローブは固定上流を書き換えず、既存の `HumanAirway::noise_gain.glottis` に倍率を掛ける。固定上流の `sing_fast` は短音の拍、`engine` はホストの分割の不変性を検査する。再実装の `retains_filter_state_when_gain_changes()` はゲイン変更時に同じフィルタ状態から次の圧力が変わることを検査する。[CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[発声状態](../crates/vocal-core/src/voice.rs)・[乱流源の登録](../crates/vocal-core/src/airway/human/frication.rs)・[上流比較プローブ](../tools/upstream_bilabial_probe.rs)・[短音の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)

## 比較条件

全体係数0の保存出力、全体係数1で全源を有効にする再描画、全体係数1で声門源のゲインだけを0にする再描画を同じスコアで重ねる。最初のPCMビット差、絶対差10⁻⁶を初めて超える位置、声門上圧・流量と放射の差は別々に記録する。声門源自身のレベル、注入先の番号、狭窄と歯の源の初回の活動も照合する。通常のCLIの `inspect`、`render`、`render-pcm` を使い、固定上流のPCMと128・77フレーム分割を比較する。[比較の入口](../tools/measure_song_glottis_source.py)・[元の短音入力](../cases/song-voice-fast.json)

## 実測

全体係数0を基準にした最初の差を、0始まりの48 kHz出力フレームで示す。候補CLIと固定上流で全ての位置が揃った。制御の呼気ゲート、声門の開大、目標音高と歌唱計画は全区間で一致した。[初回の結果](../runs/song-voice-fast-glottis-source-20261121-a/summary.json)・[再実行の結果](../runs/song-voice-fast-glottis-source-20261121-repeat/summary.json)

| 観測 | 全ての乱流源を有効 | 声門源のゲイン0 |
| --- | ---: | ---: |
| 声門側の順方向の枝圧 | 20,294 | 差なし |
| 狭窄側の順方向の枝圧 | 27,277 | 27,277 |
| 放射流量の時間微分 | 20,295 | 27,277 |
| 声門上圧 | 20,295 | 27,918 |
| 声門流量 | 20,295 | 27,919 |
| PCMのビット列 | 20,309 | 27,285 |
| PCMの絶対差が10⁻⁶を超える | 20,380 | 27,292 |

声門源を抑えるとPCMのビット差は6,976フレーム（145.33 ms）後ろへ移った。声門源のゲインとレベルは全区間0で、注入先の番号は全源を有効にした条件と揃った。残った狭窄の乱流源は27,277フレーム目に活動を始め、同じ出力フレームで枝圧と放射が分岐した。歯の乱流源のレベルが初めて正になるのは27,927フレーム目で、歯の順方向の枝圧の最初の差は27,968フレーム目だった。レベルは励起の大きさを表し、枝圧はフィルタを通った雑音と流れの向きを反映する。[枝とレベルの比較](../runs/song-voice-fast-glottis-source-20261121-repeat/summary.json)

両実行で18件の取得判定と2件の予測が成立し、結果のJSONはバイト一致した。固定上流の3試験スイートは各実行で計17件が通過した。声門源を抑えた49,200フレームについて、上流と候補のPCM絶対誤差の最大値は `2.91 × 10⁻¹¹`、放射流量の時間微分の最大差は `2.29 × 10⁻⁷ cm³/s²`（上流のピーク比 `2.03 × 10⁻¹³`）だった。設定を省いた再描画は両版とも保存済みの係数1の波形とバイト一致した。別途、Python標準ライブラリの `csv` と `struct` で両版の保存時系列とfloat32の波形を比較し、表のうち枝圧、放射、声門上圧、PCMの初回差と、残る乱流源の初回活動を再確認した。[候補の時系列](../runs/song-voice-fast-glottis-source-20261121-repeat/artifacts/glottis_gain_zero/voicing.csv)・[上流の時系列](../runs/song-voice-fast-glottis-source-20261121-repeat/artifacts/glottis_gain_zero/upstream-voicing.csv)

ブラウザと実機の音声出力は未計測。次は全体係数1、声門源の倍率0を維持し、狭窄源のゲインだけを0にして、歯の乱流源が働く位置と最初の放射・PCM差を測る。狭窄源を抑えたことによる流量の変化も記録する。

## 再現

研究ワークスペースから実行する。`<実行ID>` は未使用の名前に置き換える。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=260000000 ../../.venv/bin/python \
  tools/measure_song_glottis_source.py <実行ID>
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で計測した。再実行ではPythonとスクリプトを絶対パスで指定し、作業ディレクトリを `/private/tmp` にした。マニフェストの入力268件と出力50件のサイズ・SHA-256を照合し、計測ファイル346.71 MBを作業用のRTL9210B-CGに保存した。[初回のマニフェスト](../runs/song-voice-fast-glottis-source-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/song-voice-fast-glottis-source-20261121-repeat/manifest.json)

`cargo test --locked -p vocal-core -p vocal-cli` の15試験が通過した。整形後のリリースビルドでも、`render-pcm <ケースJSON> <新規WAV> <新規CSV> 128` で両条件の保存済みWAV・CSVとのバイト一致を確認した。追加照合の初回は同じ一時出力名を使い、2条件目が上書き防止で終了コード1になった。条件ごとに出力名を分けて成功した。倍率−0.5の入力はCLIの `inspect` が終了コード1で拒否した。全体の整形確認では `phonetics.rs` の既存のモジュール宣言順を指摘された。今回のRust変更箇所を個別に確認し、CLIの新規行を整形した。
