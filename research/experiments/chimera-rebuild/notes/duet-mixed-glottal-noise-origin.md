# 混合体型の声門乱流振幅差

女性係数0.4・子ども係数0.3の声部で、768出力サンプル間隔の記録の振幅が初めて異なったのは33,792だった。譜面は「Pop Dee」、MIDI 55・64を各1拍、120 BPM、開始0.64秒。先行の二声計測から同じ混合体型の声部を取り出し、声門枝の断面積と流量、乱流振幅の変化を出力サンプルごとに測る。研究版の初期舌先と出力ゲインは既存ケースの値で固定する。[事前登録](../cases/duet-mixed-glottal-noise-origin.json)・[先行の枝位置の測定](duet-head-turbulence-body.md#実測)

## 読解と予測

- 固定上流の通常歌唱CLIの `render::notes` は発音辞書と `plan_song` で譜面をジェスチャーに変え、`HumanVoice` に時刻付きで登録する。固定CLIの文字列の体型引数で指定できるのは3端点。それと同じ音源初期値・順序を使う `upstream_duet_body_probe` に混合体型を渡す。`BodyMix::weights` で成人男性・成人女性・子どもは0.42・0.28・0.30になり、長さの比は0.894。咽頭・口腔のセル数は15・16。声門は声門下と咽頭入口の接続で、気道グラフの登録順が異なるため、枝番号は研究版67、上流65になる。`body_mix` の試験には端点・重み、JSONの読み込み、補間した調音と音響特性、混合体型の描画があり、`engine` は制御を維持したブロック分割でも同じPCMになることを検査する。[歌唱CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[混合体型の入口](../tools/upstream_duet_body_probe.rs)・[上流の補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L325)・[体型の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)・[描画の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)
- `HumanAirway::update_noise` は調音更新時に最初の乱流源として声門を登録する。`HumanVoice::render` は内部96 kHzで声門上下の圧力差から次の声門面積を求め、気道に渡す。`AirwayNetwork::compute_noise` は次の枝の運動を解く前に、枝に保存されていた有効断面積 `A`（cm²）と体積流量 `U`（cm³/s）を読む。閉鎖閾値以下では振幅0。開いていれば `Re = 2|U| /(ν√(πA))`、`ν = μ/ρ`。閾値を超えた分 `x = max(0, Re² − 1800²)` に対して、振幅（dyn/cm²）は `g √(96000/f_s) x /(1 + x/(12000² − 1800²))`。この振幅値をテレメトリに残し、帯域制限した乱数との積を、流れの方向に応じた別の枝に圧力源として加える。各出力サンプルの採取は2回の内部更新のうち後の更新に対応する。[声門源の登録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L328)・[描画の更新順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝に入る圧力源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[研究版の乱流計算](../crates/vocal-core/src/airway/network/turbulence.rs#L124)
- 上流の既定設定ではドリフトが5セント、周期ジッターの係数が0.00455、振幅シマーの係数が0.042。ドリフトは32内部サンプルおきに瞬時F0を変え、ジッターとシマーは声門周期が折り返すときに周期の長さと振幅を変える。先行子ども声部ではこれらをそろえると、観測窓の振幅差が減った。今回も各設定を上流で一つずつ0にして、全て0にした対照を加える。振幅式の実装差がある場合は、それぞれ観測した面積・流量からの独立計算との残差に出る。乱流更新の入力側に差がある場合は、面積と流量を相手側の値に入れ替える二通りの順序を平均すれば、寄与の合計を実測の振幅差と比較できる。[上流の設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L348)・[上流の声門更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[子ども声部の対照](duet-child-glottal-noise-origin.md)

## 観測と再現

研究版の通常入口は `render-pcm-tele`。固定上流の混合体型観測器は無変更の上流ライブラリでビルドし、PCMと768サンプル刻みの最大乱流源を先行実行と照合する。追加の観測器は固定上流を一時展開し、声門乱流が実際に読んだ断面積と流量を同時に採取する。両版の観測器は保存PCMとビット照合し、初期状態の次から詳細系列の末尾までの疎な46行をそれぞれ照合する。波形全体は97,920サンプル、詳細時系列は35,328サンプル、主計測窓は33,024から34,560を含む。[固定上流の採取差分](../tools/patches/upstream-duet-child-noise-drive.patch)・[計測CLI](../tools/measure_duet_mixed_glottal_noise_origin.py)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_mixed_glottal_noise_origin.py duet-mixed-glottal-noise-origin-new
```

## 実測

33,792サンプルで最大だったのは、研究版は枝67、固定上流は枝65で、どちらも声門だった。振幅の詳細値は研究版76.243533、上流79.540855 dyn/cm²。両版のジェスチャーは一致し、全条件の枝入力から独立再計算した振幅は観測値と一致した。その時点で研究版の枝断面積は0.05698834 cm²、上流は0.05691022 cm²、流量はそれぞれ195.02182、199.43357 cm³/s。研究版から上流を引いた振幅差 `−3.297321 dyn/cm²` のうち、面積の寄与は `−0.098094`、流量の寄与は `−3.199227 dyn/cm²`。寄与の計算には、面積を先に入れ替える場合と流量を先に入れ替える場合の平均を使った。[チェックポイントと寄与の計算結果](../runs/duet-mixed-glottal-noise-origin-20261122-b/summary.json)

| 上流で0にした変動 | 33,792での振幅差の絶対値（dyn/cm²） | 計測窓の最大絶対差（dyn/cm²） |
| --- | ---: | ---: |
| 既定値 | 3.297321 | 62.512351 |
| ドリフト | 0.842430 | 17.178188 |
| ジッター | 2.717640 | 50.068819 |
| シマー | 3.230104 | 62.963526 |
| 3つ全て | 1.43×10⁻¹³未満 | 1.20×10⁻¹²未満 |

毎サンプルで比べると、既定上流では瞬時F0と位相が最初のサンプルから許容差を超え、振幅は33,309で初めて `10⁻⁷ dyn/cm²` を超えて離れた。そこではゲートは同じで、乱流更新前の流量に `1.37×10⁻⁶ cm³/s`、断面積に `4.68×10⁻¹⁰ cm²` の差があった。3つの変動を0にしたときは、主計測窓で両実装の枝断面積と声門位相が一致し、流量の最大差は `5.69×10⁻¹² cm³/s` 未満だった。25サンプル目に始まる無発声時の流量差はその対照にも残った。ドリフト単独を外した実行で振幅差の最大値は約73%縮んだ。シマー単独を外すと33,792の差は縮み、窓内の最大差は増えた。単一点の改善と窓全体の最大差は、同じ設定でも異なる判定になる。[各条件の時系列比較](../runs/duet-mixed-glottal-noise-origin-20261122-b/summary.json)

初期舌先の追試では、乱流更新後の声門流量は元の姿勢でサンプル4から差が生じ、サンプル24で `10⁻⁶ cm³/s` を超えた。初期舌先を休止位置にそろえると、最初の512サンプルで声門流量と放射は0になった。[初期舌先の追試](duet-mixed-initial-tip.md#実測)

初回は全波形と観測値を採取した後、NumPyの真偽値をJSONに書き出す段で停止した。声門枝番号をPythonの整数として判定する修正を加え、ケースの許容差と観測条件を固定したまま再実行した。初回の採取物と失敗記録も保存した。[初回の失敗記録](../runs/duet-mixed-glottal-noise-origin-20261122-a/manifest.json)・[修正後](../runs/duet-mixed-glottal-noise-origin-20261122-b/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ディレクトリと `/private/tmp` から各12判定・3予測と固定上流10試験が通過した。初回と修正後の観測データなど24出力、修正後の2実行では要約を含む25出力がバイト一致した。標準ライブラリでも流速と等価直径から振幅を再計算し、2実行の各211,968点で最大差は `1.71×10⁻¹³ dyn/cm²` 未満だった。子ども声部の回帰は11判定と固定上流10試験が通過し、先行の27出力に一致した。4実行の588入力・131出力のサイズとSHA-256を照合し、採取物189,794,326バイトをRTL9210B-CGに保存した。[再実行](../runs/duet-mixed-glottal-noise-origin-20261122-repeat/manifest.json)・[子ども声部の回帰](../runs/duet-child-glottal-noise-origin-20261122-mixed-regression/manifest.json)
