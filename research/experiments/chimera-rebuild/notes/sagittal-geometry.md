# 成人男性の矢状面輪郭

## 固定上流の経路と座標

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` では `HumanAirway::apply` と `reapply` が `commit` を呼び、`HumanVocalTract::compute` が体型と調音姿勢から輪郭と計測格子を作る。`resample` は同じフレームの計測格子から気道セルの断面積を求める。この単位では格子の前に作られる座標と輪郭を取り出す。静的な体型ランドマークと姿勢の入力から、1フレームの点列が決まる。[気道の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L215)・[輪郭の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L736)

頭部座標は前方が `x` 正、上方が `y` 正で、単位はcm。中立の声門が原点になる。成人男性の基準では体型スケールと咽頭の縦比率が1。テンプレートの `x>0.5 cm` は `0.5+0.86(x−0.5)` に置き換える。下顎の点はこの写像の後で顎関節 `(-2.5,10.5) cm` を中心に回す。回転角は顎の開きに負号を付け、関節から初期の下切歯までの距離で割った値（rad）。舌体中心と舌先は頭部座標で指定し、顎の回転は舌の裏側がつながる口腔底に作用する。[体型と中立姿勢](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L285)・[座標の変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L655)

後壁・硬口蓋・鼻腔の固定ランドマークは一様Catmull–Rom曲線で結ぶ。外壁は口蓋垂の口腔側の先端より0.3 cm下で咽頭後壁を切り、そこから軟口蓋、硬口蓋、上唇をつなぐ。軟口蓋は口蓋の後端を起点に開口の指定（cm²）を角度へ写し、中心線に厚さを付ける。硬口蓋との根元は二次の重みで接続位置に寄せる。内壁は喉頭蓋から0.05 cm上で舌の背面の点列につなぎ、舌先、舌の裏側、口腔底、下切歯、下唇へ続く。描画用の喉頭蓋には谷の点があり、音響用内壁はこの窪みをまたぐ。上下の壁は三次・二次Bézier曲線と円弧から作る。[外壁と唇](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L748)・[舌と内壁](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L824)・[補間関数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L160)

舌体は半径2.25 cmの円弧を32点で採り、前側は舌先への接線条件から角度を決める。唇の端は顎の開き、前突、開口の指定から決まり、身体に結び付く根元は上唇では頭部、下唇では顎を基準にする。上流の `a_ray_grazing_a_polyline_vertex_sees_no_tissue_layer_that_is_not_there` は、頂点をかすめても厚さのない組織を数えず、較正済み母音でも断面が飛ばないことを検査する。今回の点列はその交差計算への入力になり、直接比較は `compute_new` の公開フレームと `palate()` から採取する。[舌の円弧](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L829)・[描画用の点列](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1238)・[上流の形状テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L206)

## 実装前に登録した比較

成人男性の中立姿勢1フレームと、顎の開きだけを0.6 cmから1.2 cmへ増やした1フレームを使う。時刻に依存しない観測なので、サンプル区間の代わりに点列の部位名と点番号を固定する。外壁、内壁、舌、軟口蓋、上下の唇と歯、顎骨、喉頭蓋、鼻腔、硬口蓋、3つの基準点を照合し、各点の距離差を `10⁻¹⁰ cm` 未満とする。半径と接線の直交、複素数で求めた下顎の剛体回転、軟口蓋と後壁のつなぎ目、咽頭の高さ5 cmでの隙間も独立に測る。下切歯の高さは中立で7.18〜7.19 cm、顎を開く条件で6.63〜6.64 cmと予測した。[中立姿勢](../cases/sagittal-neutral.json)・[顎を開いた姿勢](../cases/sagittal-open-jaw.json)

## 実装と結果

固定ランドマークを補間して保持する `SagittalModel` と、姿勢から得る `SagittalFrame` をRustコアに追加した。Catmull–Rom曲線は端点と接線を使うHermite形式で評価し、Bézier曲線はde Casteljau法で評価した。固定観測用の実装ではフレームごとに輪郭の配列を確保する。座標の係数とランドマークは固定上流に由来する。[Rustの形状モデル](../crates/vocal-core/src/anatomy.rs)・[上流データのライセンス](../LICENSE-CHIMERA)

通常の `inspect` から入力と点数を、`geometry` から部位と点番号付きの座標を出力した。固定上流の公開 `compute_new` と同じ入力を使い、両姿勢とも15部位305点の順序が一致した。各点の距離差は最大 `3.67×10⁻¹⁵ cm` 未満。独立計算した下顎の点との差は最大 `1.99×10⁻¹⁵ cm` 未満で、舌の半径と接線、壁の接続も含め全20項目が通過した。[計測器](../tools/measure_sagittal.py)・[中立姿勢の実行記録](../runs/sagittal-neutral-20261119-b/manifest.json)・[顎を開いた姿勢の実行記録](../runs/sagittal-open-jaw-20261119-b/manifest.json)

下切歯の座標は `(5.8443, 7.1854) cm` から `(5.6043, 6.6356) cm` へ移った。舌先は両方で `(5.617, 7.3) cm`、高さ5 cmの咽頭の隙間は約1.9721 cm。顎だけを変えたため、口腔底と下切歯は回転し、頭部座標で指定した舌先と咽頭の観測点は同じ座標だった。確認した範囲は成人男性の固定2姿勢。測定格子・接触による補正・音響断面の生成は次の単位で照合する。[中立姿勢の計測](../runs/sagittal-neutral-20261119-b/summary.json)・[顎を開いた姿勢の計測](../runs/sagittal-open-jaw-20261119-b/summary.json)
