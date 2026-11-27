# デュエットの頭部の輪郭の残像

## 固定上流の処理

対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。デュエットの `Head.frame` は音源の可聴位置から観測行を選ぶ。調音値は停止中も渡されるが、そのときの `tele` は空になる。`AnatomyView3D` は表示時間を1フレームにつき最大0.05秒に制限し、シーク世代が変わると形状計算の前に `Anatomy3D.resetMotion` を呼ぶ。リセットは残像の履歴と最終採取秒を初期化する。表示時計の累積値は引き続き使う。[音源と観測行](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/DuetPage.tsx#L154)・[フレーム順序](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/AnatomyView3D.tsx#L173)・[リセット](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L681)

`Anatomy3D.update` は口腔の形状から舌の輪郭、顎の回転を反映した顎先、2回のChaikin補間を使った上下唇、および開口時の三次元の口の縁を得る。開口は正中の唇の高さの差 `upperLip[6].y − lowerLip[6].y > 0.02 × 体型スケール` で判定する。頂点は体型座標のcmで、各ポリラインのXYZをf32で保持する。`tele` があり、直前の採取から28 ms以上過ぎたときだけ、表示時計と線の写しを履歴に追加し、120 msより古い点を捨てる。表示時計が `t` のとき `t−90 ms`、`t−60 ms`、`t−30 ms` の各時刻に最も近い採取を探す。差が16 ms未満の採取だけを描き、同距離なら古い側を保持する。係数は古い順に0.10、0.17、0.24で、視点の側面度を掛ける。固定側面で係数はそのままになる。停止中は時刻だけ進み、残像は描かれない。再開時に採取条件を通れば履歴を再利用し、長い停止で対象時刻から外れたものは表示しない。[輪郭、採取、描画](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/src/ui/render/anatomy3d.ts#L837-L891)・[開口の判定](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/anatomy3d.ts#L1030)・[線の不透明度](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/render/beams3d.ts#L162)

上流の再生時計とテレメトリの既存試験は計9件通過した。時計試験は再生中のシークで音源が再始動し、世代が増えることを確認する。テレメトリ試験は時刻の前後の行選択と末尾の保持を検査する。残像の採取列は今回、固定上流の三次元レンダラーで線を受け取る箇所から観測する。[時計試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/transport.test.ts#L100)・[観測列の試験](../../../../docs/reference/chimera-vocal-synth/upstream/tests/tele.test.ts#L47)

## 測る前の予測

48 kHzの同梱デモの二声を使う。人工時計で16 msごとに進む区間では32 msごとに採取し、現在の姿勢から約32・64・96 ms前の輪郭を描ける。160 ms相当のフレーム停止は表示時計の50 msとして処理されるため、再開直後には停止以前の輪郭が見える場合がある。シーク後の最初の表示は履歴を初期化してから新しい位置を採取する。新しい世代に遅れた採取が揃うと段階的に残像が戻る。通常ブラウザでは19,968〜43,008サンプル間の開閉を見て、同一サンプルを一時停止で描いた画像と比べる。[事前登録](../cases/duet-head-echoes.json)

## 実装と実測

可聴時計で声部ごとの観測行を選び、ブラウザのフレーム時計で残像の採取時刻と表示時刻を進める。画面を一時停止しても表示時計は進み、残像への採取と描画は止まる。二声は同じ表示時計を使い、履歴は声部ごとに保持する。同じ観測行が続いても、上流と同様に時間の条件を満たせば採取する。シークと公演の先頭への巻き戻りでは、履歴を消してから移動先の位置を採取する。開口時は右と左の口角で三次元の上下の縁を結ぶ。残像の顎は研究画面で描いている下顎骨、唇は平滑化前の輪郭をコピーする。色と正投影は研究画面に合わせた。[時計の接続](../../../../web/prototypes/chimera-research/src/duet-page.tsx)・[時間選択](../../../../web/prototypes/chimera-research/src/duet-head-echoes.ts)・[履歴頂点の作画](../../../../web/prototypes/chimera-research/src/duet-head-scene.ts)

登録した26フレームを二声に与え、固定上流の `Anatomy3D.update` が `Beams.line` に渡した線を採取した。男声と女声で各32件の残像が選ばれ、候補と独立した時刻計算は全件で採取時刻・位置・不透明度が一致した。160 msに相当する人工フレームでは累積時刻0.230秒から0.280秒まで進み、停止前の姿勢が復帰後にも表示された。開口の縁を含む描画は男声15件・女声29件。人工時計の結果は同じバイト列で再生成できた。[時刻と線の採取](../runs/duet-head-echoes-20261120-repeat/artifacts/controlled-echoes.json)

男声では、観測43行目（33,024サンプル）を採取した残像が、40,608サンプルの描画で初めて直接計算から `4.62×10⁻⁴ cm` 離れた。この舌の頂点は、上流41行目（31,488サンプル）の直接計算をf32へ丸めた点と一致した。41〜43行は17軸を小数3桁に丸めると同じキーになる。キャッシュを通さない上流と候補WASMの最大座標差は両声部で `2.67×10⁻¹⁵ cm` 以下だった。幾何の差の起点は残像の選択より前の `VoiceModel.frame` にある。[固定上流のキャッシュ](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/analysis.ts#L81)・[過去の順序反転実験](duet-heads.md#実装と実測)

Chromiumの960・390 pxで2回とも19項目を通過した。描いた過去の頂点は各声部の採取時の現役頂点と一致した。前後シーク後の初回と一時停止では残像がなく、新しい位置で再生を続けると戻った。再実行では同じ観測行の描画で960 pxの1,281画素、390 pxの618画素が残像によって変化した。頭部や圧力による表情、気流の粒子は別の機構として残る。[初回計測](../runs/duet-head-echoes-20261120-a/summary.json)・[再実行と設定](../runs/duet-head-echoes-20261120-repeat/manifest.json)・[再生中の画像](../runs/duet-head-echoes-20261120-repeat/artifacts/echo-960-playing.png)・[同じ姿勢の停止中](../runs/duet-head-echoes-20261120-repeat/artifacts/echo-960-paused.png)

口元の歌詞の回帰では、休符末尾に文字のないフレームを逐次ポーリングで待った初回が30秒でタイムアウトした。描画コミットを監視し、メリスマ・休符・再発音の最初の該当フレームを一度の再生で採取するよう計測器を変更した。条件未達時にも終端までの履歴を保存する。登録済みのケースとアプリの描画は維持し、歌詞の回帰24項目を通過した。[観測の欠測](../runs/duet-echoes-mouth-regression-20261120/manifest.json)・[監視方式の回帰](../runs/duet-echoes-mouth-observer-20261120/summary.json)。三次元頭部の回帰28項目も通過した。[三次元頭部の回帰](../runs/duet-echoes-heads-regression-20261120/summary.json)
