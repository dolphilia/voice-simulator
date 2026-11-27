# 固定母音 /i/ の中心線距離

## 読解と予測

固定上流の `HumanVoice::render` は制御境界で `HumanAirway::apply` を呼ぶ。そこから `HumanVocalTract::compute` で矢状面の輪郭と測定線を求め、`resample` の咽頭・口腔の長さと断面を `AirwayNetwork::set_tube_targets` に渡す。研究版では `vocal-cli area` と `inspect` が `SagittalModel::area_profile` を使い、固定発声で使う長さは同系列から得る。先行の内部圧力観測では、この幾何の違いが咽頭セル0のコンプライアンス差として現れた。[上流の声道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L318)・[研究版CLI](../crates/vocal-cli/src/geometry_case.rs#L444)・[先行の圧力比較](fixed-voice-pharynx-onset-48000.md#最初の差はセル長から圧力へ伝わる)

測定線の内外端は輪郭との交差を使って求める。中点は座標ごとに `inner + (outer − inner) × 0.5`。中心線距離は喉頭蓋部の長さを初期値とし、後壁付近の水平線、口腔へ向かう扇形の線、唇付近の縦線の順で `s_i = s_(i−1) + hypot(x_i − x_(i−1), y_i − y_(i−1))` と更新する。位置・区間長・積算距離の単位はcm。両版とも `libm 0.2.16` の `hypot` を使う。後処理で採用する咽頭の長さは、扇形の測定線が口腔へ切り替わる最初の行の `s`。固定条件では長さを18で割って1セルの長さを得る。上流の `geometry_matches_typescript` は各線の区域・隙間・断面・積算距離と管長を検査し、`geometry_continuity` は接触の境界と母音間の連続性を検査する。[測定線の配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1027)・[上流の距離更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1223)・[研究版の積算](../crates/vocal-core/src/anatomy/area.rs#L74)・[上流の幾何試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs#L14)・[連続性試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L155)

固定姿勢の咽頭は測定線19で終わり、両実装の中点を同じ距離関数に通せば、それぞれの積算をビット一致で再現できると予測する。先行の長さの差は、距離計算に入る座標のいずれかで先に現れると考えた。各点と区間の初差、差が丸めで消える行、上流中点の一部を使った場合の咽頭全長を照合する。[事前登録](../cases/fixed-voice-centerline-i.json)

最初の実行では中点Xの差が測定線0、区間長の差が3→4、積算距離の差が6→7に現れた。断面の採取結果と輪郭を照合すると、測定線0の内側壁は喉頭蓋の基部から先端にかけての線分に当たる。上流の座標変換は成人男性の咽頭係数1にも `7 − (7 − y) × 1` を適用し、研究版はこの係数で `y` を使う。これが1点目の内側Xを動かしたと予測した。最初の12水平線の交差を座標から再計算し、基部Yと後壁の点列の単独・組合せ置換が積算の初差に及ぼす影響を調べる。[第1版の結果](../runs/fixed-voice-centerline-i-a/summary.json)・[上流の座標変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L696)・[研究版の座標変換](../crates/vocal-core/src/anatomy/body.rs#L65)

## 区間長と積算距離が最初に分かれる位置

通常CLIの `area` と固定上流の `--area` で各49線を採取し、同じ距離関数で全積算値をビット一致で再現した。独立十進計算との差は最大7.11×10⁻¹⁵ cm。内側Xと中点Xは測定線0で分かれるが、区間長に差が現れるのは3→4からで、この差は最初の加算で丸められる。先行する積算値が両方とも4.216907016537503 cmだった6→7で、区間長の差約7.77×10⁻¹⁶ cmが残り、積算値が初めて約8.88×10⁻¹⁶ cm分かれた。[全49線の距離](../runs/fixed-voice-centerline-i-v2-repeat/artifacts/centerline-comparison.csv)・[比較要約](../runs/fixed-voice-centerline-i-v2-repeat/summary.json)

咽頭と口腔が切り替わる測定線19では、両版の中点そのものは一致し、咽頭の全長は8.092899222322227 cmと8.092899222322226 cmで1 ULP異なった。境界までの中点のX座標だけを全て上流値に替えると全長が一致した。一点ずつ替えた14通りはいずれも元の全長と一致した。18で割ったセル長は先行の幾何と咽頭入口圧の観測で得た値に一致した。[比較要約](../runs/fixed-voice-centerline-i-v2-repeat/summary.json)・[先行の圧力比較](fixed-voice-pharynx-onset-48000.md#最初の差はセル長から圧力へ伝わる)

## 喉頭蓋と後壁の二つの丸め

水平線を前方4.6 cmから後方へ送り、内外輪郭に当たる線分を調べた。外壁は最初の交差、内壁は外壁の交差から1.5 cm先までにある最後の交差を使う。前後壁の保存座標から、先頭12線の内外端Xと中点Xを両版でビット一致に再計算できた。喉頭蓋基部の高さは研究版3.198 cm、上流3.1980000000000004 cm。基部の高さだけを置き換えると、最初に分かれた線0の内側Xと、積算が分かれる直前の線6の内側Xが上流に一致した。線7の外側Xは、同じ後壁線分の頂点11の高さの差から復元できた。上流のCatmull–Romの多項式と研究版のHermite基底式を同じ節点と補間位置0.75に適用すると、この高さはそれぞれ5.109375000000001 cmと5.109374999999999 cmになる。[上流の多項式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L201)・[研究版の基底式](../crates/vocal-core/src/anatomy.rs#L577)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-centerline-i.json)

線6の内側Xと線7の外側Xを両方替えると、線6の同じ積算値から始めた線7の積算が上流と一致した。各座標の単独置換では線7で研究版と同じ値になった。全12水平線に基部Yと上流後壁を適用した場合は、線7の最初の積算値と線19の咽頭全長がともに上流と一致した。今回の置換は採取済み座標を使う比較として実施した。次に2か所の演算順を実験用ビルドで個別に変え、通常の幾何・描画を通したときの中心線、セル長、声門上圧を比較する。[2項の置換結果](../runs/fixed-voice-centerline-i-v2-repeat/summary.json)・[独立検算コード](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-centerline-i.py)

## 実行記録

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で第1版の8判定と、第2版の各12判定を通過した。第2版は研究ワークスペースと `/tmp` から再実行し、要約がバイト一致した。3実行で各版の断面と輪郭の4 CSVも一致した。上流では形状の連続性5試験と基準値1試験が通過し、既知の突出した下唇の試験1件には無視指定が残る。計394入力と45出力を独立にハッシュ照合し、2,316,959バイトの出力をRTL9210B-CGに保存した。[初版のマニフェスト](../runs/fixed-voice-centerline-i-a/manifest.json)・[第2版のマニフェスト](../runs/fixed-voice-centerline-i-v2-repeat/manifest.json)・[上流の試験ログ](../runs/fixed-voice-centerline-i-v2-repeat/artifacts/upstream-geometry-tests.log)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_voice_centerline.py fixed-voice-centerline-i-new
```
