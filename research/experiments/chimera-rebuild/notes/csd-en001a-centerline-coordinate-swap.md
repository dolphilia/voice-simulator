# CSD初期姿勢の測定線4・5を交換する

`en001a` の初期姿勢では、上流と研究版の中心線で区間距離が測定線4、累積弧長が測定線6で最初に分かれた。今回は中心間距離の計算で使うx座標だけを、双方の実測から交換する。 [初期口端形状の照合](csd-en001a-initial-oral-geometry.md#中心線の初差と末端セル)・[ケース定義](../cases/csd-en001a-centerline-coordinate-swap.json)

## 呼び出しと独立計算

上流の同設定対照は `HumanAirway::apply` から `HumanVocalTract::compute` を経由して、初期姿勢の測定線を得る。中心間距離は `geom::dist` が座標差を `libm::hypot` に渡して計算する。研究版は通常の歌唱から `ArticulatedVoice::for_speech_with_body`、`HumanTractControl` を経由し、`area_profile_from_contacts_reusing` で各線の中心座標を読む。座標差に使う `Point::norm` も `libm::hypot` を使う。中心線は喉頭入口の長さから始まり、距離を測定線番号順に倍精度で足す。咽頭端と口端の累積値の差（cm）をセル数で割る前に、安定性の下限を適用する。同じ弧長軸で末端セルの断面を8点補間し、調和平均（cm²）を得る。 [上流の歌唱対照](../tools/upstream_csd_continuous_probe.rs#L52)・[上流の中心線](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1219)・[上流の距離関数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L34)・[研究版の中心線](../crates/vocal-core/src/anatomy/area.rs#L72)・[再標本化](../crates/vocal-core/src/anatomy/resample.rs#L74)

交換した座標は最初の姿勢適用と制御更新で距離を求める時だけ使い、出力1フレームの終了時に通常の計算へ戻す。測定線の元の座標、開口幅、断面積も別に採る。区間距離は十進90桁の計算と照合し、下流は採取した距離の逐次加算から弧長、末端セル、内部標本0・1の体積源と口端負荷を独立に再現する。上流の幾何の基準試験と連続性試験、研究版の再標本化試験を比較に用いる。 [区間距離の独立計算](../tools/measure_tsp_fk61_centerline_length_origin.py#L30)・[口端負荷の独立計算](../tools/measure_fixed_voice_release_lip_load.py#L100)・[上流の連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs)

## 事前に決めた条件

3番の座標は両版で同じなので、4番のx座標を交換すると3→4の距離は揃うが、4番の累積値は従来どおりと予測した。6番の座標も同じなので、5番のx座標を交換すると5→6の距離と6番の累積値が揃うと予測した。より口側にも座標差があるため、4番と5番の両方を交換しても口端セル長は少なくとも一方向で分かれると予測した。条件は交換なし、4番、5番、4と5番を両版に適用する。 [事前登録の条件と判定基準](../cases/csd-en001a-centerline-coordinate-swap.json)

## 交換が伝わった範囲

4番を交換すると3→4の区間距離は相手と一致し、4番の累積値も元の版と一致した。初期化直後と最初の制御更新後の両方で、全49本の累積弧長と両版それぞれの全PCMが元の版に一致した。5番だけを交換した場合は5→6の距離と6番の累積値が相手と一致し、累積値が動いたのは6番だけだった。4・5番を同時に交換した場合も、両版それぞれの累積弧長とPCMは5番だけの交換と一致した。 [中心線とPCMの保存結果](../runs/csd-en001a-centerline-coordinate-swap-20261124-registered/summary.json)

6番では累積弧長が約3.79749 cmで、差は4.441×10⁻¹⁶ cm（1 ULP）だった。6→7の距離は両条件で0.2924834941882849 cm。加算値が4 cmを超えると隣接する倍精度値の間隔は8.882×10⁻¹⁶ cmになり、どちらの和も同じ4.089970477897158 cmへ丸められた。咽頭端と口端の弧長、末端セル長は両方向とも元の版の値になった。標本0の口端の体積速度差1.066×10⁻¹¹ cm³/sと、標本0・1の口端流量は、どの交換でも各版の対照に一致した。次の制御更新後の出力65フレーム時点では、使用した全中心座標、累積弧長、格子の値が通常条件に戻った。 [3時点の中心線と最初の口端負荷](../runs/csd-en001a-centerline-coordinate-swap-20261124-registered/artifacts/observations.json)

5番の交換によるPCMの初差は、上流側でフレーム3,300、研究版側で7,299だった。差のあるフレームはそれぞれ8,688・89,610。元の版に対する最大絶対差は両方向ともフレーム134,534の7.276×10⁻¹²で、その箇所では隣接する `f32` 値が相互に入れ替わった。一方、両版間の最大差はすべての条件でフレーム20,363にあった。 [全条件のPCM](../runs/csd-en001a-centerline-coordinate-swap-20261124-registered/artifacts/pcm.npz)・[初差と最大差の集計](../runs/csd-en001a-centerline-coordinate-swap-20261124-registered/summary.json)

事後の再標本化では、咽頭15セルのうち測定線5〜7の区間と重なるセルは0始まりの7・8番だった。5番交換による初期代表面積の変化はセル7に現れ、上流で−8.882×10⁻¹⁶ cm²、研究版で+1.332×10⁻¹⁵ cm²と計算した。最初の目標でもセル7が変わり、セル8の代表面積は一致した。次は両版のセル7でこの見積もりを実測に照合し、初期面積と最初の目標だけを交換して体積源を再計算する。その差が後続PCMの初差とフレーム134,534へ届く経路を調べる。 [再標本化の独立計算](../tools/measure_tsp_fk61_lip_area_origin.py#L94)・[研究版の咽頭セル数](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/artifacts/research-plan.json)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。通常の歌唱入口に接続したまま上流と研究版を隔離してビルドし、全8描画の歌唱計画と201,600フレームずつのPCMを比較した。上流の幾何の6試験と研究版の再標本化の1試験が通った。上流で既知の問題として無効化されている唇歯音の試験1件はスキップされた。作業用のRTL9210B-CGに採取値、圧縮PCMとハッシュ、観測差分を保存した。 [実行コマンドと保存先](../runs/csd-en001a-centerline-coordinate-swap-20261124-registered/manifest.json)

研究ワークスペースと `/tmp` から独立に実行し、各5判定と3つの事前予測を確認した。観測、PCMハッシュと計画、圧縮PCM、両版の観測差分、要約の6出力がバイト一致した。 [再実行のマニフェスト](../runs/csd-en001a-centerline-coordinate-swap-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_csd_en001a_centerline_coordinate_swap.py csd-en001a-centerline-coordinate-swap-new
```
