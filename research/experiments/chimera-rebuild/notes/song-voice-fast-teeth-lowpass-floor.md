# 歯の乱流フィルタの低域通過周波数に下限を設ける対照

短音の `Pop Dee` で声門と狭窄の乱流を抑えると、歯の励起レベルが正になってから注入圧が出るまで41出力フレーム待った。この発生順序を調べるため、固定上流の再現版を基準に、歯の低域通過周波数だけに1,200 Hzの下限を設ける。声門・狭窄の倍率0、全体係数1、歯の乱流源の配置、乱数シード12,345を揃える。[前回の観測](song-voice-fast-constriction-source.md#実測)・[事前登録](../cases/song-voice-fast-teeth-lowpass-floor.json)

## 呼び出しと独立計算

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `Engine::render()` は発声器を呼び、`HumanVoice::render()` は48 kHz出力の各フレームで声門と音響網を96 kHzで2回進める。出力64フレームごとの `control()` から `HumanAirway::apply()`、`commit()`、`update_noise()` を通じて注入源を更新する。歯の源の位置とゲインは狭窄の面積と歯までの距離に依存する。前の制御区間の終端で採った励起枝の面積（cm²）と体積流量（cm³/s）から噴流速度 `v = |U|/A`、直径 `d = 2√(A/π)`、渦の大きさ `δ = max(d, 0.17 × 歯までの距離)` を求める。固定上流は歯の低域通過周波数 `f_jet = v d / δ²`（Hz）をそのまま使う。分帯によるゲイン補正には `√(5000/max(f_jet, 1200))` を使う。[エンジン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs)・[制御と発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs)・[歯の帯域](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs)

`set_noise_sources()` は励起枝と順方向の注入先が前回の登録と揃えば状態を引き継ぐ。`compute_noise()` は直前の流量と面積による励起レベルを計算し、乱数を高域通過1段（1,200 Hz）と低域通過2段に通す。低域通過の状態は各段で差分の `1 − exp(−2πf/96000)` 倍だけ進む。第2段の出力に励起レベルを掛け、順方向の枝に足すか、逆方向の枝から引く。音響網はこの注入圧を使って流量・節点圧・放射を進める。上流の `affricates` は閉鎖解除から摩擦・母音への連続性、`voiced_fricatives` は摩擦音区間の低域成分、`engine` はホスト分割の不変性を検査する。今回はこの3種を含む前回の試験結果を基準に使った。候補のワークスペースでは乱流のフィルタ状態の継承と既定の歌唱も再試験した。[音響網](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[破擦音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/affricates.rs)・[有声摩擦音](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voiced_fricatives.rs)・[ホスト分割](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[候補の状態継承](../crates/vocal-core/src/airway/network/turbulence.rs)

独立計算は27,904〜27,967フレームで、直前の登録に同じ励起枝と注入先の組がないことを観測列で確認し、初期フィルタ状態を0とした。そこまでの登録数と96 kHzの内部回数から乱数の開始位置を求め、3源のうち最後の歯に割り当てられた乱数列だけを取り出す。`scipy.signal.lfilter` で高域通過1段と低域通過2段を直列に計算し、フレーム末尾に観測した励起レベルを掛けて、順方向枝圧から逆方向枝圧を引いた値と照合した。両枝に圧を加え得る声門源と狭窄源を抑えているため、この差から歯の注入圧を復元できる。励起レベル自体は保存した観測値を使う。[参照乱数](../tools/measure_turbulence.py)・[独立計算と判定](../tools/measure_song_teeth_lowpass_floor.py)

## 実測

時刻は0始まりの48 kHz出力フレーム。枝圧からPCMまでの初回差は全体係数0を基準とした。下限を省略したCLIと固定上流の初回位置は全て一致した。[再実行の結果](../runs/song-voice-fast-teeth-lowpass-floor-20261121-repeat/summary.json)

| 観測 | 固定上流・再現版 | 下限1,200 Hz |
| --- | ---: | ---: |
| 歯の励起レベルが正になる | 27,927 | 27,927 |
| 歯の順方向の枝圧 | 27,968 | 27,927 |
| 放射流量の時間微分 | 27,968 | 27,927 |
| 声門上圧 | 27,985 | 27,944 |
| 声門流量 | 27,985 | 27,945 |
| PCMのビット列 | 27,968 | 27,927 |
| PCMの絶対差が10⁻⁶を超える | 27,972 | 27,939 |

フィルタの周波数は歯の初回登録の26,688フレーム目から分岐した。両条件で励起レベルは27,926フレーム目まで0で、次のフレームでは0.965512 dyn/cm²で揃った。下限ありの順方向の注入圧は同じフレームで−0.00672106 dyn/cm²となり、41フレーム（0.854 ms）あった注入までの間隔が出力フレーム単位で0になった。励起レベル自身の最初の差は3フレーム後の27,930で、注入で変化した流量が以降の励起に戻る挙動と整合する。独立計算で最初の注入位置が一致し、圧力誤差の最大は `5.88 × 10⁻¹⁵ dyn/cm²` だった。[候補の時系列](../runs/song-voice-fast-teeth-lowpass-floor-20261121-repeat/artifacts/voicing.csv)・[基準の時系列](../runs/song-voice-fast-constriction-source-20261121-repeat/artifacts/voicing.csv)

開口直前の閉鎖区間64フレームでは下限あり、再現版、全体係数0のPCMが揃った。再現版との差のRMSは、最初の開口区間で `3.11 × 10⁻⁴`、次の制御区間で `1.48 × 10⁻³`。次の制御更新では両条件の低域通過周波数が1,200 Hzを超えていたが、更新までのフィルタ状態と音響網の流量が異なり、PCM差は続いた。固定上流との最大PCM差は `2.76 × 10⁻³`。この結果は短音1ケースでの変化を示す。ブラウザでの波形照合、同じ出力フレーム内の内部サンプルの順序、実機出力と聴感は未確認。[区間計測と固定上流との差](../runs/song-voice-fast-teeth-lowpass-floor-20261121-repeat/summary.json)

## 実装と再現

CLIの `turbulence.teeth_lowpass_floor_hz` を加え、指定時は歯のフィルタに `max(f_jet, 下限)` を渡す。分帯によるゲイン補正は元の `f_jet` を使う。省略時の下限は0 Hz。計測はCLIの `inspect`、`render`、`render-pcm` を使い、候補のまま基準を再描画して保存済みPCMと時系列にバイト照合する。比較に使った固定上流の保存済み出力は、前回のケースとマニフェストで検証してから読む。[候補の配置](../crates/vocal-core/src/airway/human/frication.rs)・[発声設定](../crates/vocal-core/src/voice.rs)・[ケース入力](../crates/vocal-cli/src/timing_case/speech_voice.rs)

研究ワークスペースから実行する。`<実行ID>` には未使用のIDを指定する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=180000000 ../../.venv/bin/python \
  tools/measure_song_teeth_lowpass_floor.py <実行ID>
cargo test --locked --workspace
```

初回と `/private/tmp` からの再実行で各8件の取得判定と4件の予測を満たし、結果JSONはバイト一致した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使用。入力276件と出力18件のサイズ・SHA-256を照合し、94.61 MBをRTL9210B-CGに保存した。基準の再描画では出力が一致したことをハッシュで残した。候補のCargoワークスペースの41試験が通過。明示的な下限0 Hzも省略と同じWAV・CSVを生成し、−1 Hzは `inspect` が終了コード1で拒否した。[初回のマニフェスト](../runs/song-voice-fast-teeth-lowpass-floor-20261121-a/manifest.json)・[再実行のマニフェスト](../runs/song-voice-fast-teeth-lowpass-floor-20261121-repeat/manifest.json)
