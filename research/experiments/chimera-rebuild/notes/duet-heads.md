# デュエットの三次元頭部と調音姿勢

## 固定上流

対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。今回の単位は、各声部の録音済み調音姿勢から三次元頭部を描き、時計の進行とシークに追従するまでとする。[事前登録](../cases/duet-heads.json)

`DuetPage` はテレメトリの体型と採取レートから `VoiceModel` を選び、外側の二声の視点を内向きにする。頭部の描画ごとに `Transport.time()` の可聴位置を秒で読み、`TeleTrack.indexAt` に渡す。観測行は `max(0, min(frames − 1, floor(seconds × sampleRate / hop + 10⁻⁶)))`。欠けた頭部姿勢を補間せず、区間内の最後の採取行を保持する。`message` は行の先頭11スカラーを読み、続く17個の f32 から顎、舌背・舌尖、舌根、唇、軟口蓋、喉頭と喉頭内外・側方の各値を取得する。位置と開度は cm、軟口蓋のポート目標は cm²、反り・横引きなどは無次元。座標は前方が +X、上方が +Y、安静声門が原点。上流の `articFromArray` は位置・単位を変換せず、軸名へ展開する。[声部の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L155)・[採取列の読み出し](../../../../docs/reference/chimera-vocal-synth/upstream/src/show/tele.ts#L60)・[軸名の展開と形状キャッシュ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L75)

`AnatomyView3D` はシーク世代が変わったとき、姿勢を更新する前に `resetMotion` を呼ぶ。これにより表情、輪郭の残像、粒子の軌跡、声帯表示の位相が前の再生位置から持ち越されない。一時停止時も現位置の17軸は残り、表情と音響表示へのテレメトリが空になる。続いて `VoiceModel.frame` が体型別の矢状面を計算する。上流では17軸を小数3桁に丸めたキーで形状を再利用する。`Anatomy3D.update` は顎軸周りの回転を下顎外形へ適用し、舌、歯列、軟口蓋、上下唇を形状から置き、視点方向に応じて正中線の濃さを調整する。WebGL描画は最後に表示用キャンバスへ転写される。[更新順と停止](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/src/ui/components/AnatomyView3D.tsx#L173-L230)・[状態の初期化と描画](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L681)

固定上流の `tests/transport.test.ts` と `tests/tele.test.ts` は9件通過した。シーク中の音源再始動・世代更新と、境界・末尾の行選択を検査する。上流の図形の連続性は `geometry_continuity.rs` が扱う。今回の試験は再生操作とWebGLへ渡る頂点までを接続して測る。[時計のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/transport.test.ts#L100)・[観測行のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts#L47)・[幾何のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L119)

## 測る前の予測

二つの48 kHzトラックは768サンプルごとに採取される。767と768で行0から行1へ移り、105,600では男声は118行目、女声は127行目を保持する。男声の口唇開度は19,968で約−0.135 cm、30,720で約1.938 cm。女声は30,720で約−0.061 cm、43,008で約1.938 cm。そこに対応する描画の下唇と画素が各声部で変化する。録音済みの同じバイト列を上流と候補に与えることで、合成時の姿勢の差を持ち込まずに頭部の経路を調べる。候補の幾何は候補CLIから得たcmの点列にも照合する。[入力の採取と生成](duet-telemetry.md)

## 初回結果とキャッシュの追試

第1版の実行は23項目を通過した。実ブラウザで採取した84頭部フレームのCLIに対する頂点最大差は `4.76×10⁻⁷ cm`。固定上流の男声45行目の形状は、サンプル34,560の17軸に対する候補形状と舌で最大 `2.46×10⁻⁴ cm` 離れ、同じ実行中の上流42行目の形状と完全に一致した。両行の3桁キーは同じだった。第2版では入力と許容差を維持し、42→45、45→42および `airwayFrame` 直接呼び出しで再計算する対照を加えた。仮説は、差の発生が姿勢の軸展開より後、矢状面の計算より前のキャッシュ参照にあること。初回のケースと判定は実行元の写しに保存した。[初回結果](../runs/duet-heads-20261120-a/summary.json)・[第2版の登録](../cases/duet-heads.json)

## 実装と実測

候補の `DuetPage` は再生時計のスナップショットから声部ごとの観測行を一度選び、数値の表と頭部描画に共有する。頭部ごとにRustの `SagittalModel` をWASMに持ち、既存の `Articulation::from_axis_values` で17軸を解釈する。長さ付きのf64の列に11部位を詰め、Three.jsが実際に読む頂点にf32で転写する。新しい行またはシーク世代では頂点を更新し、同じ行を描く間は形状を再利用する。声部の体型とカメラの向きは分離し、下唇と下顎は実測姿勢に従う。頭蓋、耳など外側の輪郭は模式図として体型に合わせて拡縮する。奥行きのある唇は、正中の内唇の終点を通り、左右の口角が口唇幅の端にくる。三次元表示は声部別の観測を持つ画面を開いたときに読み込む。[再生時計と観測行の共有](../../../../web/prototypes/chimera-research/src/duet-page.tsx)・[WASMの形状出力](../crates/vocal-wasm/src/duet_head.rs)・[三次元の作画](../../../../web/prototypes/chimera-research/src/duet-head-scene.ts)

Chromiumの960・390 pxで28項目を通過し、作業ディレクトリを変えた再実行でも同じ判定だった。各幅で一時停止13位置、再生中のシーク3件の最初の描画と時計が進んだ時点、一時停止後の2時点を採取した。84頭部フレームで固定上流・バイト列の独立読出し・画面の17軸が一致した。CLIに対する描画頂点の最大座標差は `4.76×10⁻⁷ cm`。開口に伴う下唇の最大変位は男声1.67 cm、女声1.21 cm。変化した画素は同じ声部・同じ視点の比較で3,400〜7,608画素だった。三次元投影の検査では口角の奥行きと左右の視点反転も確認した。[第2版の計測](../runs/duet-heads-20261120-final/summary.json)・[実行条件](../runs/duet-heads-20261120-final/manifest.json)・[別ディレクトリからの再実行](../runs/duet-heads-20261120-repeat/manifest.json)・[歌詞の回帰28項目](../runs/duet-heads-words-regression-20261120/manifest.json)

男声の42→45行では、固定上流は42行の輪郭を2回返した。逆順では45行の輪郭を2回返した。キャッシュを通さず計算すると、上流と候補CLIの11部位の最大座標差は `3.55×10⁻¹⁵ cm` だった。先に訪れた姿勢が残る理由を `VoiceModel.frame` のキャッシュまで絞れた。候補では採取行単位で形状を更新するため、固定時刻に直接シークしたときも同じ行の輪郭を再現できる。先に訪れた姿勢が表示に与える影響を評価するには、同じ2行の形状を複数の画面倍率で投影して最小可視差を測る。[上流のキャッシュ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L81)・[反転と直接計算](../runs/duet-heads-20261120-final/summary.json)

上流の幾何連続性テストは5件が通過し、突き出した下唇を引き込む条件は上流の指定どおり1件除外された。口付近への文字の投影、輪郭の残像、表情や流れの時間応答は別の作業単位として残る。[幾何連続性テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs)
