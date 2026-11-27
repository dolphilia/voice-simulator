# アメリカアリゲーターの `hiss`

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の公式CLIは持続・停止・`bellow`・`growl` に続き、48 kHzのフレーム249,600から `hiss` を86,400フレーム描画する。固定試験の単発シナリオ `alligator-call-hiss` は70,560フレームを使う。公式順序では前の声門・気道・乱数・フィルタを保持する。[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)

## キーと乱流

`hiss` は声門開大の指示と口を所有する。ゲートは0〜0.1秒で0→1、1.2秒まで保持、1.3秒で0へ戻る。声門の指示は1、口は0.9から、1.3秒の0・0.02へそれぞれ0秒から直線補間する。1.2秒のキーには両項目がないため、ゲートだけがその時刻まで1を保つ。最後のキー1.3秒に50 msを加えた時刻を厳密に超える制御境界まで所有する。音高のキーも移調基準もなく、`growl` が所有していた音高と粗さは切り替え時に手動値へ戻る。[キーの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L109)・[コール評価と手動値の復帰](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L215)

平滑値を `h` とすると、上流は開大 `0.02+0.8h` cm²と駆動振幅 `0.9(1−h)` cm²を指定する。定常開口0.826 cm²は隙間0.006 cm²を含む。声門モデルはさらに4 msの一次平滑化を通す。有声ゲートは平滑差圧と開大から求め、開大による係数は0.08〜0.22 cm²の範囲で1→0へ下がる。位相と揺らぎの内部状態は、発声が弱くなっても更新される。音響系の口先目標は `0.05+12·mouth` cm²で、口腔終端セルを除く最小の正断面が2 cm²未満のときだけ、その枝の乱流源を登録する。[気道と声門への適用](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)・[有声ゲートと開口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱流源の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L77)

声門の乱流源は常に登録される。気道の更新では、直前に計算した枝流量 `U`（cm³/s）と枝開口 `A`（cm²）から `Re=2|U|/(ν√(πA))` を求める。`Re≤1800` では係数0、超える場合は `q=Re²−1800²` として `6×10⁻⁶ √(96000/fs) q/(1+q/(12000²−1800²))` を使う。シード12345の一様乱数は登録された各源が内部サンプルごとに1つ読み、係数0でも進む。声門の乱数を250 Hzの一次ハイパスと4000 Hzの一次ローパス2段に通し、係数を掛けて流れの向きに応じた枝に圧力を注入する。口腔乱流源の登録が変われば、声門に次に割り当てられる乱数の位置も変わる。[気道の乱流更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1156)・[乱流フィルタ状態の引き継ぎ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L785)

## 事前登録

48 kHzは公式順序、44.1 kHzは `growl` からの途中切り替えと手動編集、96 kHzは単独コールを比較する。44.1 kHzで `hiss` に110 Hzを渡しても、切り替え前に指定した手動音高55 Hzが使われ、その後の手動音高60 Hzは受付時に反映されると予測する。0.4〜0.7秒では有声ゲートが小さく、口腔乱流源が外れ、声門乱流とPCMが残ると予測する。その区間の実開口を、平滑な開大指示からさらに4 msのフィルタを通した開口の独立計算と比較する。0.826 cm²は指示を1に固定した場合の開口である。固定上流側で乱流の倍率だけを0にする96 kHzの対照では、同じ測定窓のPCM RMSが通常の0.1倍以下に下がると予測する。[登録した条件](../cases/alligator-hiss.json)

## 実装と実測

項目ごとのキー列に `hiss` を追加し、移調基準を省略できるようにした。気道に既にある圧力注入を観測し、声門乱流の順方向・逆方向の枝に入る圧力の和を記録した。口腔乱流の枝と声門乱流の枝は別である。候補と上流の声門・口腔の乱流レベルを比較し、候補の流量・開口と口腔源の有無から、声門のレベルと帯域フィルタ通過後の注入圧を再計算した。全条件で独立計算のレベルは一致し、注入圧の最大差は `9.09×10⁻¹³ dyn/cm²` だった。[コールの実装](../crates/vocal-core/src/airway/alligator/call.rs)・[注入圧の観測](../crates/vocal-core/src/airway/mammal.rs)・[独立計算](../tools/measure_alligator_hiss.py)

48 kHzの公式順序では、開始から8 ms後に実断面1.84924 cm²、制御ブロックの目標断面2.08259 cm²で口腔乱流源が外れた。開始1.14秒後には実断面2.00120 cm²、目標断面1.99045 cm²で再登録された。0.4〜0.7秒は有声ゲートも口腔乱流も0で、声門の注入圧は147.83 dyn/cm² RMSだった。96 kHzの同区間では通常のPCM RMSが0.11869、上流の乱流倍率だけを0にした対照では `4.16×10⁻⁵` で、通常値の約0.035%だった。[乱流の時間経過と対照](../runs/alligator-hiss-20261120-a/summary.json)

上流との照合後に、内部系列で開始0.7秒以降に有声ゲートが初めて0.5以上になるサンプルを調べた。3条件とも開始1.1391秒で、ゲート目標は高いままだった。48 kHzでは約1.223秒で有声ゲートは0.95に達し、1.248秒の観測では0.99650だった。ゲートが解放に入り始める前から、閉じていく声門で再び周期発声が始まる。PCMの無声区間と終端の有声区間を区別して比較できる。[公式順序の内部系列](../runs/alligator-hiss-20261120-a/artifacts/official-prefix-48000/pcm-128.csv)

44.1 kHzでは切り替えフレーム19,009で手動の55 Hzと粗さ0.27が目標に戻り、次の制御境界19,072でも指定した110 Hzへの移調は生じなかった。フレーム24,001で音高目標は60 Hzに、呼気圧の目標は20 cmH₂Oに変わった。自然終了78,656で手動の口0.25と `hiss=0.17` が目標に戻った。[切り替えと手動編集](../runs/alligator-hiss-20261120-a/summary.json)

全558,800出力フレームで声門位相と瞬時F0は上流と一致した。公式 `hiss` 区間86,400フレームには6件のPCMビット差があり、最大差は `5.68×10⁻¹⁴`。44.1 kHzと96 kHzには各1件、最大差はそれぞれ `2.27×10⁻¹³` と `3.73×10⁻⁹` だった。公式順序の最初の内部差は先行する保持音の肺ポート流量、他の2条件では口が動き始めた内部サンプル256と64の口端放射・合成放射に現れた。[観測列ごとの比較](../runs/alligator-hiss-20261120-a/summary.json)

登録した280項目を研究ディレクトリと `/tmp` で実行し、要約と観測ファイル25件のSHA-256が一致した。`growl` の238項目と観測ファイル23件も実装の変更前後で一致した。[別ディレクトリからの再実行](../runs/alligator-hiss-20261120-repeat/manifest.json)・[growlの回帰](../runs/alligator-growl-hiss-regression-20261120/manifest.json)
