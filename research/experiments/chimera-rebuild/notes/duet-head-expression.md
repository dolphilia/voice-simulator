# デュエットの表情と頭部の動き

## 固定上流

固定版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。各声部の `Head.frame` は可聴時刻で観測行を選ぶ。公演にテンポと頭拍を指定すると、`floor((t−downbeat) × BPM × 4 / 60)` を16で折り返す。頭拍より前、テンポ省略、一時停止中の拍番号は−1になる。`AnatomyView3D` は先にシーク世代の変更で `Expression` を作り直す。次にテレメトリと実経過秒を渡す。表情に与える経過秒の上限は0.5秒で、残像用の0.05秒と別に計算する。[声部と拍の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L154)・[シークと時計](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L173)

`mouthPressure` は口腔の末端から3点目のRMS圧力を読み、dyn/cm²から980.665で割ってcmH₂Oにする。口腔に3点なければ0。頬の目標は1.5〜7.0 cmH₂Oの滑らかな三次補間。6.5 Hz、減衰比0.32のばねで追い、表示値を−0.35〜1.25に収める。各小刻み幅を最大8 msにし、加速度 `ω²(target−x)−2ζωv` で速度を進めてから、更新後の速度で位置を進める。表示の制限はばねの内部位置を変えない。[圧力とばね](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/src/ui/render/expression.ts#L13-L45)

有声の判定はvoicing > 0.45、呼気ゲート > 0.3、F0 > 30 Hz、出力RMS > 0.004をすべて満たすこと。log₂ F0の基準を5秒、短期値を0.35秒で指数追従する。基準との差が14半音を超えると基準を初期化する。短期値との差が2.5半音を超えると音の持続秒を数え直す。眉は基準との偏差（半音）の1/6を0.12秒で追い、無声時は0.45秒で緩める。高い音が0.9〜1.9秒持続すると瞼を閉じる。まばたきの開始間隔には乱数を使う。拍をまたいだ際は、拍の途中に飛んだ場合も頷きのばねに速度を加える。小節頭の速度変化は−1.3、それ以外の拍は−0.8 rad/s。頭の傾きには、保持音の揺れと短期音高偏差を加える。[表情の更新順序](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/expression.ts#L48)

上流は首元を中心にX軸の傾きとZ軸の頷きを合成して頭部全体を回転させ、同じ変換で唇を画面へ投影する。皮膚の頬は横と前へ膨らませ、眉と瞼は眼球周りのポリラインの角度を変える。上流の12件の試験が通過した。そこには、実合成の両唇破裂音では頬が膨らみ鼻音・奥の閉鎖では小さいこと、高音の持続で瞼が閉じること、低フレームレートでも飛び越えた拍で頷くことが含まれる。[頬の変形](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L244)・[回転と瞼、眉](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L897)・[上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/expression.test.ts)

## 測る前の予測

同梱テレメトリの30,720サンプルで女声の圧力は約8.14 cmH₂O、男声は約0.54 cmH₂O。女声の頬のばねが先に正へ動く。50,000台のサンプルでは二声とも前の音より高くなるため、十分な出力がある区間で眉が上がる。人工系列では同じ音高のまま弱い声を挿入して有声判定を確認する。テンポを省略した通常公演と、120 BPMの診断条件をブラウザで使う。シーク直後の眉は移動元の高音との偏差を保たず、頬は移動先の圧力を初期位置から追い始める。[事前登録](../cases/duet-head-expression.json)

## 実装と実測

声部ごとに表情状態を持ち、同じCHTL行から調音姿勢と表情を求める。頬・眉・瞼・瞳は研究画面の線画に合わせて変形させた。頭部の回転は研究画面の首元を支点とし、X軸とZ軸の回転を合成した後に、向きに応じたX軸の反転を適用する。唇の投影にもこの行列を使う。上流の表情値と角度を照合し、頂点の造形は研究画面の式で検査する。まばたきには固定シードを声部ごとに与え、世代切り替え時に同じ初期状態へ戻す。「表情と頭部の動き」で調音の線画だけを静止姿勢のまま観察できる。一時停止では音響入力を止め、別の表示フレームでばねを減衰させる。[表情計算](../../../../web/prototypes/chimera-research/src/duet-head-expression.ts)・[表情と音源の接続](../../../../web/prototypes/chimera-research/src/duet-heads.tsx)・[頂点と回転](../../../../web/prototypes/chimera-research/src/duet-head-scene.ts)

129フレームの人工入力で、固定上流と同じ乱数列を与えた。圧力の差は0 cmH₂O、表情値と内部のばね状態の最大差は `2.50×10⁻¹⁶`。独立計算との差は `7.11×10⁻¹⁵` 以下だった。4.25 cmH₂Oのステップで頬の値は最大0.665。110 Hzから220 Hzに上げて持続すると眉は約1.0、瞼は0.869まで閉じた。出力RMS 0.002の220 Hzでは眉は上がらなかった。拍を3から5へ飛ばしても頷きが出た。シークを模擬して初期化すると、移動先の220 Hzが新しい基準になった。人工系列の結果は同じバイト列で再生成できた。[人工系列](../runs/duet-head-expression-20261120-repeat/artifacts/controlled-expression.json)・[判定](../runs/duet-head-expression-20261120-repeat/summary.json)

実ブラウザの960・390 pxで二声の圧力・音高・頭部の回転、停止と前後シークを採取し、2回とも21項目を通過した。390 pxの比較では同梱公演に120 BPMと0.1秒の頭拍を加えた。再実行で線画の実頂点と独立計算の最大座標差は `4.77×10⁻⁷ cm` 以下。表情を有効・無効にした同じ調音行の画像では、251・166画素が変化した。初回の実行はThree.jsの線材の型が広すぎてビルドが止まった。材質の型を明示して再実行し、登録した判定と許容差を維持した。[再実行](../runs/duet-head-expression-20261120-repeat/manifest.json)・[実画面](../runs/duet-head-expression-20261120-repeat/artifacts/expression-960-enabled.png)・[初回のビルド結果](../runs/duet-head-expression-20261120-a/manifest.json)

再生開始直後はフレームの間隔によって短い圧力パルスを拾う順が変わった。390 pxの再実行では女声の40行目（採取30,720サンプル）の8.14 cmH₂Oを得たが、960 pxの再実行では同じ口腔圧パルスの行を通過した。男声では224 ms間隔のフレームが32行目の5.15 cmH₂Oを得て、直後の頬の値が0.763になった。表情の更新は、上流と同様に各フレームで選んだ圧力をその経過時間のステップに与える。先に動く声部は、入力パルスが観測されるフレームに依存する。圧力をサブステップごとに観測行で補間する変更は別条件で比較できる。[再実行の時系列](../runs/duet-head-expression-20261120-repeat/artifacts/browser-expression.json)

既存の歌詞の比較は、表情で回転した頭部行列から唇の投影を再計算し、24項目を通過した。表情のスイッチを切った条件で、三次元頭部の28項目と残像の19項目も通過した。記録を保存する際に容量が不足したため、研究CLIの再生成可能なデバッグビルドキャッシュを整理した。[歌詞の回帰](../runs/duet-expression-mouth-regression-20261120/summary.json)・[三次元頭部の回帰](../runs/duet-expression-heads-regression-20261120/summary.json)・[残像の回帰](../runs/duet-expression-echo-regression-20261120/summary.json)
