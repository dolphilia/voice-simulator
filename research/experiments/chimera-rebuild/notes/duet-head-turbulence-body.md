# 子ども体型と混合体型のデュエットの乱流源

## 上流の経路と事前登録

固定CHIMERA `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `render::notes()` は譜面と歌詞を `plan_song()` に渡し、予約したジェスチャーを `HumanVoice` で描画する。`render_tracked()` はサンプル0と768出力サンプルおきに `HumanVoice::telemetry()` を呼ぶ。テレメトリは、その時点で最大の乱流振幅とその枝番号を記録する。乱流振幅は枝の断面積と流量から得るレイノルズ数の閾値超過分を尺度化した値である。CHTLのヘッダーにはサンプルレート、セル数と体型係数を持つ。`TeleTrack` が再生秒を観測の行番号へ変換し、`DuetPage` は各声部の体型を取り出して `VoiceModel` を作る。固定上流の `branchS()` はそのグラフの内部枝を咽頭・口腔の区間内に写し、声門ポートなら0.2 cmを返す。[歌唱と採取](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L486)・[最大乱流源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L626)・[乱流モデル](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[枝位置](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L135)

咽頭の内部枝なら、その枝の開始からの1起算番号をセル数で割り、咽頭長を掛ける。口腔では同じ式に咽頭長を足す。位置と管長はcm、枝は整数、再生は秒から出力サンプルに換算する。`drawTurbulence()` は有効な枝と乱流強度を確認し、乱数を進めて生成位置から0.2〜1.4 cm下流の線分を描く。声道端を越えた点は省く。上流の `tele.test.ts` はCHTLの復号、`transport.test.ts` は再生とシークを扱う。今回のブラウザ検証では実際の表示に渡した線分と不透明度を独立計算し、Float32の頂点バッファまで比較した。[線分の生成](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1205)・[CHTLの試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts)・[再生時計の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/transport.test.ts)・[観測器](../../../../web/prototypes/chimera-research/tools/capture-duet-head-turbulence.mjs)

保存済みの二声を、譜面・時刻・音源設定を保って子どもと混合体型（女性係数0.4、子ども係数0.3）で描画する。各声部で0.25〜1.65秒の声門源と口腔源から最大振幅の行を一つずつ取り、静かな行0を加える。候補と固定上流で各生成元の枝範囲を使ったときに同じ位置と分類が得られ、候補の記録を固定上流の配置で読むと声門枝に差が出ると予測した。候補の混合WAV・CHTL・公演定義は試験用に生成し、普段のデュエット画面から一時配信した。[事前登録](../cases/duet-head-turbulence-body.json)・[検証CLI](../tools/measure_duet_head_turbulence_body.py)

固定上流の通常CLIの体型引数は男性・女性・子どもの3種類。混合体型では `plan_song()` と `HumanVoice` を通常CLIと同じ順序で呼ぶ観測プログラムを作り、同じ128サンプル分割とCHTLの採取間隔でPCM・乱流の4列を出した。子ども体型では、通常の上流CLIのPCMとビット一致し、そのCHTLの全119行でサンプル、咽頭長、口腔長、乱流振幅、枝番号も一致した。両体型でNativeの枝配置とWASMの枝配置が一致した。[上流CLIの体型引数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L519)・[上流観測プログラム](../tools/upstream_duet_body_probe.rs)・[判定](../runs/duet-turbulence-body-20261122-repeat/summary.json)

## 実測

| 体型と観測点 | 出力サンプル | 研究版の枝 | 固定上流の枝 | 生成元の枝配置を使った位置 |
| --- | ---: | ---: | ---: | ---: |
| 子ども・声門 | 25,344 | 59 | 57 | 0.20 cm |
| 子ども・口腔 | 43,008 | 33 | 33 | 11.5502 cm |
| 混合・声門 | 33,024 | 67 | 65 | 0.20 cm |
| 混合・口腔 | 49,920 | 40 | 40 | 13.8140 cm |

両実装で各体型の最大振幅を観測したサンプル位置は同じだった。咽頭・口腔のセル数は子どもで11・13、混合で15・16。声門枝は研究版で2つ大きい。差の起点は気道グラフの構築順序で、研究版は咽頭–口腔と梨状窩の接続を声門より先に番号付けし、固定上流は声門より後に接続する。候補の声門枝59・67を固定上流の配置で読む負の対照では、両方とも声門位置が欠測になった。左右の枝情報を丸ごと入れ替えた公演は、セル数の照合で読み込みを拒否した。[研究版の番号付け](../crates/vocal-core/src/airway/human.rs#L216)・[固定上流の番号付け](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L149)・[体型別の実測](../runs/duet-turbulence-body-20261122-repeat/summary.json)

乱流振幅の最初の差は、子どもでは24,576サンプルで研究版200.3411、固定上流200.2320、混合では33,792サンプルで76.2435、79.5409だった。枝の解釈と表示の照合は、各生成元が実際に出した振幅を入力として行った。研究版と固定上流のPCMにはサンプル0からビット差があり、振幅差の原因となる発声機構の切り分けは今回の範囲に含めていない。[研究版の記録](../runs/duet-turbulence-body-20261122-repeat/artifacts/duet-turbulence-body/show.json)・[子どもの上流時系列](../runs/duet-turbulence-body-20261122-repeat/artifacts/upper-1-noise.json)・[混合体型の上流時系列](../runs/duet-turbulence-body-20261122-repeat/artifacts/upper-2-noise.json)

子ども声部の追試では、24,576の振幅差を声門枝の断面積と流量から再構成し、ドリフト・ジッター・シマーを個別に切り分けた。[声門乱流の追試](duet-child-glottal-noise-origin.md)

混合体型の追試では、33,792での約3.297 dyn/cm²の差のうち約3.199 dyn/cm²が流量の寄与だった。毎出力サンプルの採取では33,309で振幅差が初めて許容差を超え、上流の3つの音源変動を0にそろえると観測窓の振幅差は最大 `1.20×10⁻¹² dyn/cm²` 未満に減った。[混合体型の声門乱流の追試](duet-mixed-glottal-noise-origin.md#実測)

960・390 CSS pxとも、再生中のシーク直後に声門源は40線分ずつ、口腔では唇端で打ち切られて子ども12、混合10線分になった。静かな行、一時停止、表示切り替えを通過した。独立投影との最大座標差は両実行で4.45×10⁻¹⁶ cm以下、不透明度の差は0で、Float32の描画バッファが一致した。[ブラウザの位置と線分の判定](../runs/duet-turbulence-body-20261122-repeat/summary.json)

## 再現

最初の試行は候補の二声を生成した後、上流の枝情報を観測するRustコードで候補側のフィールド名を使ったためコンパイルで停止した。固定上流の `Tube` の `branch_base` と `n` に修正し、ケースの条件は保持した。[初回の停止とコンパイルログ](../runs/duet-turbulence-body-20261122-a/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 ../../.venv/bin/python \
  tools/measure_duet_head_turbulence_body.py duet-turbulence-body-local
```

macOS 15.6.1 arm64、Python 3.14.4、Rust 1.94.1、Bun 1.4.4、Chromium 156.0.8078.4で実行した。研究ディレクトリと `/private/tmp` から各28判定および固定上流9試験が通過。混合WAV、二声のCHTL、候補の出力PCMとCSV、上流の四列とPCM、固定したシーク先の線分数が一致した。表示切り替えからの復帰と一時停止のサンプルはブラウザの操作時点で変わった。男声・女声の従来公演も20判定に通過した。4実行の1,081入力・92出力をサイズとSHA-256で検査し、採取物64,149,101バイトをRTL9210B-CGに保存した。[修正後](../runs/duet-turbulence-body-20261122-b/manifest.json)・[再実行](../runs/duet-turbulence-body-20261122-repeat/manifest.json)・[従来公演の回帰](../runs/duet-turbulence-body-20261122-original-regression/manifest.json)
