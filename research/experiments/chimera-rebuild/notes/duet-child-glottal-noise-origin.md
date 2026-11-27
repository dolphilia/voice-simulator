# 子ども声部の声門乱流振幅の差

体型別デュエットの子ども声部「Pop Dee」で、CHTLが最初に振幅差を記録したのは24,576出力サンプル目だった。両生成元とも声門が最大の乱流源で、振幅は研究版200.3411、固定上流200.2320だった。今回は同じ声部を単独で描画し、調音、声門、乱流計算の入力を保存する。[先行結果](duet-head-turbulence-body.md#実測)・[事前登録](../cases/duet-child-glottal-noise-origin.json)

## 読んだ経路と予測

- 参照版の `render::notes` は体型を指定して `HumanVoice` を生成し、最初の音のF0と肺圧9 cmH₂O・緊張0.55を設定する。`plan_song` のジェスチャーを `schedule` で登録し、`render_tracked` は48 kHzの出力768点ごとにテレメトリを採る。研究版の `speech_voice::run_song` も同じ声部を計画し、64出力フレームごとに調音・呼気を更新し、1出力フレームを内部96 kHzの2ステップで描画する。観測時刻は描画済みの出力サンプル数でそろえる。既存の `body_mix` と `engine` で体型の扱いと分割の不変性を確認する。[上流CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L485)・[研究版の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L260)
- `HumanAirway::update_noise` は声門を励起枝とする源を最初に登録する。`AirwayNetwork::compute_noise` は新しい流量を解く前に、直前の内部ステップの枝断面積 `A`（cm²）と流量 `U`（cm³/s）を読む。`Re = 2|U|/(ν√(πA))` が1,800を超える開口で、`x = Re²−1,800²` に対し、振幅は `3.2×10⁻⁶ x/(1+x/(12,000²−1,800²))` になる。内部96 kHzではレートの補正係数は1。ここでのレベルはフィルタ済みの雑音振幅を掛ける前の値である。研究版でも `Turbulence::step` は枝の更新より前に呼ばれる。[上流の乱流源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[上流の振幅計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[研究版の更新順序](../crates/vocal-core/src/airway/network.rs#L675)
- 固定上流の標準歌唱にはピッチドリフト5セントと、既定の粗さから得る周期ジッター・シマーがある。保存した研究版の入力はこれらを指定せず、音源の初期値は0である。ドリフトは最初の内部サンプルからF0に掛かり、ジッターとシマーは声門周期が折り返すときの周期・振幅倍率に反映される。設定を一つずつ変えて最初に動く量を測る。全部を0にしたときに残る差は、同一の振幅式への面積と流量の入力を交換して調べる。[上流の音源既定値](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L51)・[上流の声門振動](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[研究版の音源初期化](../crates/vocal-core/src/voice.rs#L92)

## 取得方法

保存した入力を通常のCLIで描画し、先行実行の91,200フレームとCHTLを各版内で照合した。研究版の観測器は同じ歌唱計画を独立に組み立て、内部 `step()` の直前に声門枝の値を読む。上流の観測器は作業ディスクに展開した固定コミットのコピーで、`compute_noise()` が最初の乱流源用に読んだ2値を記録する。観測器はそれぞれ同じ出力フレームの最後の内部ステップに記録し、通常CLIのPCMとビット単位で一致することを検査した。[上流に加えた観測](../tools/patches/upstream-duet-child-noise-drive.patch)・[固定上流の観測器](../tools/upstream_duet_child_noise_probe.rs)・[研究版の観測器](../tools/candidate_duet_child_noise_probe.rs)

## 実測

両版のジェスチャーは一致した。1出力サンプル目には既に唇端の断面積が研究版0.916585、上流0.917711 cm²、咽頭先頭が0.673931、0.673943 cm²だった。ゲートがまだ0の25サンプル目に声門の流量差が `1.09×10⁻⁶ cm³/s` を超えた。この初期の差は上流の3設定を0にした対照にも残った。最初の母音で声門乱流が立ち上がる区間は、唇位置・唇と咽頭の断面・ゲートが登録した許容差内で一致した。[差を初めに検出した位置](../runs/duet-child-glottal-noise-origin-20261122-phase-repeat/summary.json)

先行のCHTLが24,576で捉えた差を密に追うと、声門面積差が登録閾値を超えたのは24,385、乱流レベル差は24,387だった。独立計算は全6条件のレベルを保存した面積・流量から再現した。24,576では、研究版の励起枝は上流より細く、流量も小さかった。枝の断面積だけを交換する効果と流量だけを交換する効果を、二つの適用順を平均して求めると、面積が `+0.169917 dyn/cm²`、流量が `−0.060767 dyn/cm²`、合計が観測差 `+0.109149 dyn/cm²` になった。[振幅差の再構成](../runs/duet-child-glottal-noise-origin-20261122-phase-repeat/summary.json)

| 上流で変えた設定 | 24,576での振幅差（研究版−上流、dyn/cm²） | 観測窓内の最大絶対差（dyn/cm²） |
| --- | ---: | ---: |
| 既定値 | +0.109149 | 0.459224 |
| ドリフトのみ0 | +0.011758 | 0.118135 |
| ジッターのみ0 | +0.097875 | 0.403043 |
| シマーのみ0 | +0.109209 | 0.473625 |
| 3設定すべて0 | +6.54×10⁻¹³ | 5.75×10⁻¹² |

ドリフトだけを外すと、この観測窓内の最大差は約74%減った。シマーだけを外すとわずかに増えた。全部を0にすると窓内のF0と位相は一致し、乱流計算への入力の差は断面積が最大 `2.78×10⁻¹⁷ cm²`、流量が最大 `3.02×10⁻¹¹ cm³/s` に下がった。歌唱前の初期断面差と、体型別に上流が出力ゲインに掛ける係数0.875は次の比較に残る。[上流の体型別出力ゲイン](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L280)

初期舌先のみを上流の休止位置にそろえる追試では、最初の512サンプルで歌唱前の断面差が数値誤差内になり、両実装の声門流量と放射が0になった。[初期舌先の追試](duet-child-initial-tip.md)

## 再現

観測器の初回コンパイルは研究版のライブラリにリンク時最適化用のビットコードが無く停止した。研究版の観測器を `lto=off` でリンクして、通常CLIとのビット一致を確認した。第1版は位相の差を周期の折り返しを考慮せず集計していたため、第2版は円周上の最短差を使った。旧版の波形・観測値・判定と比較できるように両方を保存した。第2版で既定条件の窓内最大位相差は0.13076周期だった。[リンク時の停止](../runs/duet-child-glottal-noise-origin-20261122-a/manifest.json)・[第1版](../runs/duet-child-glottal-noise-origin-20261122-repeat/summary.json)・[第2版](../runs/duet-child-glottal-noise-origin-20261122-phase-repeat/summary.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_child_glottal_noise_origin.py duet-child-glottal-noise-origin-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ディレクトリと `/private/tmp` から第2版の各11判定と上流の `body_mix`・`engine` 計10試験が通過した。23出力が成功した全実行でバイト一致し、第2版の要約も一致した。標準ライブラリの `decimal` を使った別計算でも24,576の寄与を照合した。初回の停止を含む5実行の715入力・143出力を検査し、170,993,850バイトをRTL9210B-CGに保存した。[第2版の初回](../runs/duet-child-glottal-noise-origin-20261122-phase/manifest.json)・[別ディレクトリからの再実行](../runs/duet-child-glottal-noise-origin-20261122-phase-repeat/manifest.json)
