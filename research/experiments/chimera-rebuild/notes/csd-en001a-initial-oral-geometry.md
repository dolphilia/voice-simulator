# CSD冒頭の口端面積とセル長を決める幾何

`en001a` の最初の口端流量差は、口端への体積源の入力にさかのぼれた。初期姿勢を気道へ反映した時点で、口端セルの面積は1 ULP、長さは4 ULP分かれていた。そこで最初の制御更新を挟む2時点を採り、測定線から口端セルまでの幾何を照合する。 [先行の口端負荷の比較](csd-en001a-first-lip-load.md#実測)・[ケース定義](../cases/csd-en001a-initial-oral-geometry.json)

## 呼び出しと更新順

固定上流では、初期姿勢を設定した歌唱用の対照から `HumanAirway::apply` と `snap_to_targets` を呼ぶ。通常の制御更新も `HumanAirway::apply` を通る。研究版の `run_song` は `ArticulatedVoice::for_speech_with_body` で初期姿勢から声道を構築し、後続の制御更新で `HumanTractControl::apply` を使う。どちらも矢状面の測定線に接触を反映して開口の間隔（cm）を決め、各線の断面積（cm²）を得る。中心線は測定線の中心点をつないだ折れ線で、喉頭入口の長さを加えた位置から隣接中心間の距離を順に足す。固定上流の `dist` と研究版の `Point::norm` はともに `libm::hypot` を使う。咽頭端と最後の測定線の累積距離の差が口腔長になる。 [上流の歌唱対照](../tools/upstream_csd_continuous_probe.rs#L52)・[上流の中心線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1219)・[研究版の断面計算](../crates/vocal-core/src/anatomy/area.rs#L72)・[研究版の初期化](../crates/vocal-core/src/airway/tract_control.rs#L134)

再標本化は咽頭端から口端までを等長セルに割り、各セルの幅を8等分した区間の中点で断面積を線形補間する。その8点の調和平均を代表面積とする。元の格子でセル内にある測定線も最小面積の候補に含め、面積が10⁻⁵ cm²以下の点があれば閉鎖セルにする。制御更新では速度制限を経て気道の目標面積を設定する。セル長は安定性で求めた口腔長の下限を適用してからセル数で割る。上流の連続性試験は調音器を動かして断面の跳びを検査し、研究版の再標本化の試験は入力検査と再実行時の保存領域を検査する。 [上流の再標本化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[上流の目標長](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L310)・[研究版のセル計算と試験](../crates/vocal-core/src/anatomy/resample.rs#L74)・[上流の連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs)

## 事前に決めた条件

最初の弧長差は、末端セルの補間に使う測定線までに現れると予測した。口腔の両端と格子の累積距離を揃えると初期面積差は両方向で半分以上減り、格子の面積だけの交換では半分に届かないと予測した。気道の初期長と制御目標はいずれも安定性の下限より長い条件とした。最初の更新で使うセルの面積系列と長さ系列も別々に交換し、丸め済みの体積差がどう変わるかを測る。 [事前の予測と合否基準](../cases/csd-en001a-initial-oral-geometry.json)

## 初回の停止と再現方法

初回の上流では中心間距離、累積弧長、末端セルを採取できた。研究版は `cargo test --lib resample` のコンパイルに必要な `contour-buffer-reuse.json` と `bilabial-p.json` が一時ビルド先になく、比較前に終了した。隔離先への入力にこの2件を加え、ケースの仮説と判定基準は事前登録どおりに使った。 [初回のマニフェスト](../runs/csd-en001a-initial-oral-geometry-20261124-registered/manifest.json)・[停止時のログ](../runs/csd-en001a-initial-oral-geometry-20261124-registered/artifacts/cargo.log)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_csd_en001a_initial_oral_geometry.py csd-en001a-initial-oral-geometry-new
```

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使った。上流の幾何の6試験と研究版の再標本化の1試験に通過した。上流で既に無効化されていた連続性試験1件はテスト実行時にスキップされた。修正後の2実行で全4判定を通過し、要約・両版の格子・PCMのハッシュと歌唱計画・観測パッチの6出力がバイト一致した。初回と修正後の上流の格子と観測パッチも一致した。作業用のRTL9210B-CGで全PCMを照合し、幾何系列と照合に使ったハッシュを保存した。 [修正後の実行](../runs/csd-en001a-initial-oral-geometry-20261124-corrected/manifest.json)・[再実行](../runs/csd-en001a-initial-oral-geometry-20261124-repeat/manifest.json)

## 中心線の初差と末端セル

49本の測定線は両版で同じ領域順だった。初期化直後と最初の出力フレーム後の両方で、中心の座標は測定線0、区間距離は4、累積弧長は6で最初に分かれた。測定線6の中心座標と、その直前までの累積距離は一致した。測定線5の中心のx座標が分かれたため、5から6の区間距離は上流で0.43088697443263646 cm、研究版で0.4308869744326368 cmだった。その区間距離を足した値は、隣接する倍精度値の中点から上流側が−2.220×10⁻¹⁶ cm、研究版側が+1.110×10⁻¹⁶ cmにあり、両側へ丸められた。プログラムの区間距離を90桁で求めた独立計算へ照合したときの最大誤差は、2時点・両版を通して0.701 ULPだった。 [中心線の観測値](../runs/csd-en001a-initial-oral-geometry-20261124-repeat/artifacts/upstream.jsonl)・[研究版の観測値](../runs/csd-en001a-initial-oral-geometry-20261124-repeat/artifacts/candidate.jsonl)・[最近接丸めの検算](../tools/measure_tsp_fk61_centerline_length_origin.py#L61)

両時点で咽頭端の測定線19は同じ弧長だった。口端は研究版が3.553×10⁻¹⁵ cm短く、末端セル長は両時点とも2.220×10⁻¹⁶ cm短かった。16セル分に安定性の下限を適用し、両版とも解剖上の口腔長をそのまま使うことを確認した。気道の初期値、制御目標、最初の出力後の値は先行の口端負荷の観測と一致した。 [2時点の長さと先行観測との照合](../runs/csd-en001a-initial-oral-geometry-20261124-repeat/summary.json)

## 入力交換と体積速度

末端セルの補間に使う測定線は45〜48。初期姿勢の代表面積の差は1 ULPだった。上流側を基準にした独立計算で、口腔の両端だけを交換すると+12 ULP、格子の弧長座標だけでは−13 ULP、格子の面積だけでは+2 ULP動いた。両端と弧長座標を一緒に交換すると、両方向で相手との差が2倍に増え、面積差が半分以上減るという予測は不成立だった。3つの入力をすべて交換した場合は相手の面積と最小断面が一致した。最初の出力フレーム後では格子の面積だけの交換でも相手の代表面積が得られた。 [8通りの入力交換と補間の内訳](../runs/csd-en001a-initial-oral-geometry-20261124-repeat/summary.json)

最初の内部標本について、初期値と制御目標を交換してから128分の1の更新を再計算した。末端セル長だけを交換すると両方向で相手の体積速度（差の絶対値1.066×10⁻¹¹ cm³/s）を再現した。面積だけの交換では体積速度は元の版と一致した。面積と長さを共に交換すると、更新前後の体積も相手と一致した。 [最初の体積速度の交換結果](../runs/csd-en001a-initial-oral-geometry-20261124-repeat/summary.json)

次は測定線3・4の区間と5・6の区間を対象に、中心のx座標だけを往復で交換する。同じ中心点を与えたときの区間距離、累積の丸め、咽頭端と口端、最初の体積速度までを照合する。
