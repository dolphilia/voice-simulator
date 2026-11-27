# 舌・口蓋と唇の接触による隙間の補正

## 固定上流の経路と観測量

固定版 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanAirway::apply` と `reapply` は `commit` から `HumanVocalTract::compute` を呼ぶ。前回の半極格子の `ray`（cm）を出発点に、接触補正は `GridSample::d`（cm）だけを更新する。内側・外側の点と中点は測定時の値を維持する。補正後の `d` が断面積に使われる。舌先と舌体の符号付き接触距離・法線は、`HumanVoice` が調音器の位置と法線速度を修正する際に使う。この単位は固定姿勢の幾何に絞る。[気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L214)・[舌の接触補正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1082)・[調音器の接触修正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L559)

`project_on` は外壁のうち軟口蓋から上切歯までを口蓋側の輪郭として扱い、最近接線分までの距離と、輪郭上の弧長位置を求める。舌先に近い点列と舌体の円弧について最小の符号付き距離を求め、空気側を正とする。接触の法線は最近接線分に垂直で、口蓋から声道の内部へ向く。格子側の `signed_gap` は閉じた舌輪郭への距離で、点が舌の内側なら負にする。内外は水平線の交差回数の偶奇で求める。成人男性では、口蓋に沿って両側の0.10 cmまでを探索し、舌が押し込まれると最大0.20 cmへ広げる。端点と半分の位置の4点を追加し、局所の最小距離を得る。[輪郭への射影と符号付き距離](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1415)・[探索範囲と混合](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1115)

口蓋輪郭からの距離に応じ、0.15〜0.25 cmの範囲で補正の影響を弱める。舌までの距離が0.60 cmへ近づくまで滑らかに補正し、0.45 cm以内から測定値を上限でも抑える。負の距離は0に丸め、上限を混ぜた後で舌までの距離を混ぜる。唇はその後、上切歯より前の格子に `max(0, 有効開き + Δx²/(2·0.6 cm))` を上限として適用する。`Δx` は中点から唇の端までの奥行き。下唇を引き込む `labiodental` を0〜0.5へ動かすと、有効開きは `aperture + 0.3·s/(1−s)`（`s` は三次補間の重み）で増え、0.5で上限の適用が外れる。[唇の補正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1159)

上流の形状テストは頂点の付近での断面積の連続性と、下唇の引き込み時の断面積の連続性を比較する。前突した下唇の引き込みには固定版で除外指定された別のテストがある。今回の比較では公開フレームの `ray`・`d` と、舌先・舌体の接触距離と法線を取得する。[頂点付近](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L206)・[通常の引き込み](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L236)・[前突時の既知ケース](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L274)

## 実装前に登録した比較

固定上流の公開フレームを事前に確認し、成人男性の固定1フレームを6条件登録した。領域別点数は19・24・6。点・距離は `10⁻⁹ cm`、法線の成分は `10⁻⁹` 未満の誤差で照合する。補正前の格子の点と `ray` は従来どおりに取得し、補正後の隙間、新たな閉鎖の本数、舌先と舌体の距離の符号を確認する。独立計算では輪郭への距離を線分へのベクトル射影、唇の上限を放物線で求める。

| 条件 | 予測 |
| --- | --- |
| 中立 | 舌側の補正は0。唇の上限で最小の隙間は0.70〜0.71 cm。[ケース](../cases/contact-neutral.json) |
| 上げた舌先 | 舌先の符号付き距離は正で約0.157 cm。口蓋側で最大約0.65 cm狭まる。[ケース](../cases/contact-raised-tip.json) |
| 舌体が口蓋に重なる | 舌体の距離は負で約−0.59 cm。閉鎖付近で最大約1.12 cm狭まる。[ケース](../cases/contact-closed-roof.json) |
| 唇の圧縮 | 開き−0.12 cmで、補正前は正の隙間があった3本が閉じる。[ケース](../cases/contact-compressed-lips.json) |
| 下唇の引き込み0.25 | 有効開き0.18 cm。最小の補正後の隙間は0.18〜0.19 cm。[ケース](../cases/contact-tuck-mid.json) |
| 下唇の引き込み0.5 | 唇の制限が外れ、最小の隙間は0.45〜0.46 cm。[ケース](../cases/contact-tuck-handover.json) |

## 実装と結果

Rustでは、矢状面を組み立てる際に口蓋、舌体、舌先に該当する点列の範囲を保持する。`contact_grid` は格子の各点と `ray_cm` を保ち、別の `gap_cm` に舌・口蓋と唇の補正を順に適用する。`inspect` は舌先・舌体の距離と法線を記録する。Pythonは線分への射影を配列で計算し、口蓋に沿う近傍点は `numpy.interp` で求める。輪郭の内外で符号が変わることはRustの単体テストでも確かめた。[Rustの接触補正](../crates/vocal-core/src/anatomy/contact.rs)・[独立比較](../tools/measure_contact.py)

| 条件 | 最小の補正後の隙間 | 主な結果 |
| --- | ---: | --- |
| 中立 | 0.7013 cm | 舌側は変化せず、唇の補正が最大0.4174 cm。[計測](../runs/contact-neutral-20261119-a/summary.json) |
| 上げた舌先 | 0.1606 cm | 舌先の接触距離は+0.1569 cm。口蓋側で最大0.6533 cm狭まった。[計測](../runs/contact-raised-tip-20261119-a/summary.json) |
| 舌体が口蓋に重なる | 0 cm | 舌体の接触距離は−0.5914 cm。口蓋側で最大1.1228 cm狭まった。[計測](../runs/contact-closed-roof-20261119-a/summary.json) |
| 唇の圧縮 | 0 cm | 0始まりの測定線46・47・48が閉じた。有効開き−0.12 cmなら放物線の上限は唇の端から約0.379 cmまで0になる。[計測](../runs/contact-compressed-lips-20261119-a/summary.json) |
| 下唇の引き込み0.25 | 0.1813 cm | 前方の6本はすべて正の隙間になった。[計測](../runs/contact-tuck-mid-20261119-a/summary.json) |
| 下唇の引き込み0.5 | 0.4543 cm | 補正前後で隙間の値が一致した。[計測](../runs/contact-tuck-handover-20261119-a/summary.json) |

6条件の全84項目が通過した。固定上流との補正後の隙間の最大絶対差は `9.66×10⁻¹⁵ cm` 未満、独立計算との差は `1.12×10⁻¹⁶ cm` 未満。上流との接触距離差は `1.12×10⁻¹⁵ cm` 未満、法線の各成分差は `5.67×10⁻¹⁵` 未満だった。今回の照合対象は固定姿勢の接触補正。面積の連続性は、断面積と気道への接続を実装してから候補側でも検証する。[圧縮の実行記録](../runs/contact-compressed-lips-20261119-a/manifest.json)・[舌先の実行記録](../runs/contact-raised-tip-20261119-a/manifest.json)
