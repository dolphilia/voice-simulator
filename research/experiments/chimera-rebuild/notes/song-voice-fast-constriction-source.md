# 短音の歌唱で狭窄を抑えた後に残る歯の乱流

`Pop Dee` の短音では、全体の乱流係数を1にして声門源を抑えると、狭窄源の乱流が先に放射に届いた。今回は同じスコア、全体係数1、声門ゲイン0を維持し、狭窄源のゲインも0にする。全体係数0と声門だけを抑えた前回の保存出力を使い、歯の乱流源が残るかと、放射・PCMに差が出る位置を調べる。[前回の結果](song-voice-fast-glottis-source.md#実測)・[事前登録](../cases/song-voice-fast-constriction-source.json)

## 上流の呼び出しと観測点

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `Engine::render()` から `HumanVoice::render()` に進む。48 kHzの出力1フレームにつき96 kHzで声門と気道を2回更新する。調音の制御境界では `HumanVoice::control()` がスコアを評価し、`HumanAirway::apply()` と `commit()` で形状を確定して `update_noise()` を呼ぶ。そこで声門、狭窄、歯の順に源を登録する。`set_noise_sources()` は旧リストの励起枝と順方向の注入先が一致する場合にフィルタ内部状態を引き継ぐ。[上流エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs)・[登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs)・[音響網](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)

狭窄源は咽頭と口腔で最小の正の断面 `A_min` を持つ位置から選ぶ。ゲインは `1.364 × 10⁻⁶ × (1 − smooth(0.35 k², 0.9 k², A_min))`、`k` は体型の寸法倍率で、`smooth` は区間の両端で傾きが0になる補間。歯の源は狭窄源と同じ励起枝および逆方向の注入先を使い、順方向の注入先を歯付近に置く。歯までの距離 `x` と最小断面が噴流の重みを決める。制御更新直前の励起枝の面積 `A`（cm²）と体積流量 `U`（cm³/s）から `v = |U|/A`、`d = 2√(A/π)`、`δ = max(d, 0.17 x)`、低域通過周波数 `v d/δ²`（Hz）を計算する。歯のゲインは幾何の重みに `3.0 × 10⁻⁶ × √(5000/max(低域通過周波数, 1200))` を掛ける。[狭窄と歯の幾何](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs)・[独立計算](../tools/measure_sibilant.py)

各内部サンプルの `AirwayNetwork::step()` は注入圧をゼロに戻し、前の流量から `Re = 2|U|/(ν√(π A))` を算出する。初期シード12,345の雑音を高域通過1段、低域通過2段で濾波し、開口かつ `Re > 1800` の枝ではゲインと飽和させた `Re² − 1800²` から注入圧を作る。流れの向きで注入先を選び、その後で枝流量・節点圧・放射を更新する。流量が変わると次のサンプルで歯の励起も変わり得る。共有する枝の圧は合算値なので、各源の活動は個別のゲインとレベルで読む。比較用の時系列は各出力フレーム末尾の観測で、上流の低域通過周波数欄はプローブが登録時の幾何と流量から復元する。[乱流の時系列更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[上流の観測処理](../tools/upstream_bilabial_probe.rs)

上流の `voiced_fricatives` は有声摩擦音の狭窄で母音より周期成分が弱くなることを、`affricates` は閉鎖解除後の摩擦から母音へのつながりを検査する。`sing_fast` は短音の拍、`engine` はレンダー分割を検査する。候補の `retains_filter_state_when_gain_changes()` はゲインを変えたときのフィルタ状態の継承を検査する。[有声摩擦音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voiced_fricatives.rs)・[破擦音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs)・[短音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)・[分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[フィルタ状態](../crates/vocal-core/src/airway/network/turbulence.rs)

## 実測

全体係数0を基準にした最初の差を、0始まりの48 kHz出力フレームで示す。歯の登録と励起レベルは各条件そのものの初回位置。表の全ての位置が候補CLIと固定上流で揃った。[初回の結果](../runs/song-voice-fast-constriction-source-20261121-a/summary.json)・[再実行の結果](../runs/song-voice-fast-constriction-source-20261121-repeat/summary.json)

| 観測 | 声門源を抑えた前回 | 声門源と狭窄源を抑えた今回 |
| --- | ---: | ---: |
| 歯の乱流源が登録される | 26,688 | 26,688 |
| 歯の励起レベルが正になる | 27,927 | 27,927 |
| 歯の順方向の枝圧 | 27,968 | 27,968 |
| 放射流量の時間微分 | 27,277 | 27,968 |
| 声門上圧 | 27,918 | 27,985 |
| 声門流量 | 27,919 | 27,985 |
| PCMのビット列 | 27,285 | 27,968 |
| PCMの絶対差が10⁻⁶を超える | 27,292 | 27,972 |

狭窄源を抑えると、最初のPCM差は683フレーム（14.23 ms）後ろへ移った。狭窄源の枝番号と登録区間は維持され、声門と狭窄のゲイン・レベルは全区間0。歯の励起レベルが正になる位置は前回と同じだが、最初の励起レベルは候補で0.965610から0.965512 dyn/cm²へ変わった。歯のゲイン欄はこの時点で両条件とも同じなので、狭窄源の注入圧による流量の変化が、歯の励起の大きさにも戻っている。[先行条件との比較](../runs/song-voice-fast-constriction-source-20261121-repeat/summary.json)

27,904フレームの制御更新で歯の励起枝は39から40に変わった。登録時の枝面積と流量は0で、低域通過周波数も0。枝の組が変わるとフィルタ状態は0から始まり、低域通過2段の更新係数 `1 − exp(−2πf/96000)` も `f=0` で0になる。27,927フレームで励起レベルが正になってからも圧力は0のまま進み、次の制御更新の27,968フレームで枝面積0.0237446 cm²、体積流量70.7805 cm³/sに更新された。式から低域通過周波数は2,786.0998 Hz。順方向の枝圧が約−0.33237 dyn/cm²となり、その出力フレームで放射とPCMが初めて分岐した。励起レベルから実際の注入までの間隔は41フレーム（0.854 ms）。前回・今回とも同じ制御境界で注入が始まった。[候補の系列](../runs/song-voice-fast-constriction-source-20261121-repeat/artifacts/voicing.csv)・[上流の系列](../runs/song-voice-fast-constriction-source-20261121-repeat/artifacts/upstream-voicing.csv)

両実行で16件の取得判定、両版で計6件の予測、および固定上流の21試験が通過した。候補と上流のPCM最大絶対差は `2.91 × 10⁻¹¹`。歯を登録した1,408フレームで独立に計算した低域通過周波数との最大差は候補で `9.09 × 10⁻¹³ Hz`。ゲインの最大差は候補・上流とも `8.47 × 10⁻²²` だった。標準ライブラリの `csv` と `struct` で保存済みの時系列とPCMを別途読み、初回の励起・枝圧・放射・PCM位置と、最初の注入時の周波数を再確認した。上流の周波数欄は復元値で、ゲイン欄は上流の実際の設定値を読んだ。[照合結果](../runs/song-voice-fast-constriction-source-20261121-repeat/summary.json)

同じ出力フレームの内部2サンプルの順序、ブラウザ、音声機器から出た波形は未確認。次の対照では同じスコアと制御刻みで歯の低域通過周波数だけに1,200 Hzの下限を設け、41フレームの間隔と、閉鎖中および開口直後の放射を比較する。

## 実装と再現

ケースの `turbulence.constriction_gain_multiplier` をCLIから渡し、調音を更新するたびに、幾何で決まる狭窄源のゲインに倍率を掛ける。倍率0でも狭窄源の枝配置、登録順序、乱数の消費とフィルタ更新は続く。歯の登録は噴流の幾何と流速で決まり、固定上流の比較プローブでは公開されている `noise_gain.constriction` に同じ倍率を掛ける。省略時の倍率は1。通常のCLIで `inspect`、`render`、`render-pcm` を使用し、PCMは128と77フレームの分割で照合する。[CLIの入力](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[発声の設定](../crates/vocal-core/src/voice.rs)・[乱流源の配置](../crates/vocal-core/src/airway/human/frication.rs)・[計測](../tools/measure_song_constriction_source.py)

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=160000000 ../../.venv/bin/python \
  tools/measure_song_constriction_source.py <実行ID>
cargo test --locked --workspace
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用。再実行は `/private/tmp` からPythonとスクリプトの絶対パスを指定し、結果JSONは初回とバイト一致した。入力276件、出力30件のサイズとSHA-256を照合した。計測ファイル172.25 MBをRTL9210B-CGに直接保存し、前回の高密度データは既存のパスを参照した。Cargoワークスペースの41試験が通過し、従来の全源有効と声門だけを抑えた条件のWAV・CSVも保存済みの出力とバイト一致した。倍率−0.5を指定したケースは `inspect` が終了コード1で拒否した。[初回のマニフェスト](../runs/song-voice-fast-constriction-source-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/song-voice-fast-constriction-source-20261121-repeat/manifest.json)
