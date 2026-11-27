# アメリカアリゲーターの固定気道と発声

固定上流版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。CLIの `render creature alligator` は初期値で1.2秒間ゲートを開き、0.4秒間閉じた後、`bellow`・`growl`・`hiss`・`dance` に進む。今回は固定した演奏値とゲートで、先頭76,800フレームと独立した条件を測る。上流の固定試験には8種のアリゲーターのケースがあり、PCMの窓とテレメトリ、ホストの分割長の不変性を検査する。無励振時には、別の試験で微小状態の減衰を確認する。[CLIの呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[減衰試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L187)

## 声門から三つの放射経路へ

`mammal_airway` は固定肺圧を直列ポートで気管につなぎ、気管と咽頭の間を声門ポートでつなぐ。咽頭末端は口腔入口へ直結し、鼻腔入口へは軟口蓋ポートで分岐する。気管・咽頭・口腔・鼻腔の管長は30・18・24・26 cm、基礎断面積は6・7・6・1.8 cm²。セル数は `floor(L / (k·c/fs/0.93))` を3から上限の間に収める。粗さ係数 `k` は気管が1.6、他は1.3。咽頭と口腔の壁面流量は係数1で放射に加わり、気管と鼻腔の壁には同じ寄与が付かない。口端と鼻端は別々の放射負荷を持つ。肺は `P × 980.665 × gate` dyn/cm²で、固定圧を与える直列抵抗は `ρc/(2A)`。[気道の構築](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L51)・[セル数と肺境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/build.rs#L7)

`Alligator::control` は口側のセル中心が0.85を越える範囲に `0.05+12·mouth` cm²、鼻腔ポートに `0.4+1.6·nostrils` cm²を指定する。初期化は目標へ即時に移すため体積変化を励起しない。声門の乱流源は常に登録し、口腔内では終端セルを除く最小断面が2 cm²未満のときだけ別の乱流源を登録する。声門の駆動振幅は `0.9(1−hiss)` cm²、開大は `0.02+0.8·hiss` cm²。これに定常隙間0.006 cm²を加え、時定数4 msで面積を平滑化する。発声圧の基準は1.5 cmH₂Oで、発声ゲートは平滑差圧で決まる。粗さは周期境界の写像に加え、ジッター `0.01+0.05·chaos` とシマー `0.05+0.25·chaos` にも入る。[制御の係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L45)・[乱流源の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L77)・[声門の式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)

`CreatureVoice::render` は64出力フレームごとに制御を更新し、ゲートを立ち上がり12 ms、降下60 msで一次平滑化する。60 kHz以下は内部2倍、超える場合は1倍。内部サンプルごとに前時点の気管端と咽頭入口の差圧を声門に読み、面積を更新してから気道の流量・圧力・放射を更新する。壁・口端・鼻端を合算した流量の時間差分を出力し、間引き、ゲイン `2.8×10⁻⁷`、12 HzのDC除去、振幅0.7からのソフトリミッターを通してf32 PCMにする。[声門の接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/mammal.rs#L104)・[制御と出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)

## 事前の予測

圧力を入れたサンプルで肺ポートと気管入口が応答し、気管セル数と同じステップ数を経て声門流量が始まる。その次のステップで、咽頭の圧力を使って壁が放射する。鼻腔ポートと、口端・鼻端の放射はセルを通る遅れを持つ。標準の口先断面0.29 cm²では口腔の乱流源が登録され、口だけを0.5に変更すると登録が外れる。鼻孔だけを最小にしたときは、鼻腔ポートが1.68 cm²から0.4 cm²に減り、なお鼻端から放射が生じる。44.1 kHzの `hiss=1` と無呼気の96 kHzでは、面積がそれぞれ0.826 cm²または0.026 cm²へ向かう指数応答を、レンダーの状態を読まない式で検査する。[登録した入力・区間・閾値](../cases/alligator-fixed-voice.json)

## 実装と実測

アザラシの気道の組み立てと声門の更新を共通モジュールに移し、種ごとの寸法・開口・壁放射と乱流の設定を渡すようにした。PCMの間引き・DC除去・飽和もアザラシと共用した。上流側は実際に描画している気道から圧力・流量と放射を採取した。声門位相・瞬時F0・発声ゲートは上流の声門をもう一つ用意し、実際の気道の更新前の差圧を入力して測った。観測用声門の面積は実際の声門ポートの面積と全内部サンプルで照合する。[気道の実装](../crates/vocal-core/src/airway/mammal.rs)・[アリゲーターの設定](../crates/vocal-core/src/airway/alligator.rs)・[上流の観測器](../tools/upstream_alligator_probe.rs)

48 kHzの標準条件では、肺ポートと気管入口が内部サンプル0で応答し、46で気管端の圧力、47で声門からの流量、48で咽頭の壁面放射が現れた。鼻腔ポートの流れは82、口端放射は139、鼻端放射は143で始まった。最初のPCMは出力フレーム24だった。口の開きを0.02から0.5にすると、口先断面は0.29から6.05 cm²に増え、口腔セル40にあった乱流源の登録が外れた。鼻孔を最小にしてもポート面積は0.4 cm²で、鼻端放射の絶対ピークは877.13 cm³/sだった。44.1 kHzの `hiss=1` では、呼気が内部サンプル256で反映され、発声ゲートは0のまま0.826 cm²への開口を確認した。

測定の最初の試行では、連続する内部サンプル番号を第1列に置く既存のCSV読み込み規則に対して、複数行に繰り返される出力フレーム番号を先に出していた。列順の修正後は、独立ゲート計算に渡す時定数のキー名が合わず、2回目の試行が `KeyError: 'attack_seconds'` で停止した。先頭ケースの実データと測定コードのスナップショットを保持し、従来のキーに明示的に対応させた。[CSV読み込みの失敗](../runs/alligator-fixed-voice-20261120-a/manifest.json)・[2回目が使った計測器](../runs/alligator-fixed-voice-20261120-b/artifacts/source/tools/measure_alligator_fixed_voice.py)

第1版で残った6件の不一致は、48 kHzの3条件で口端・鼻端の最短経路長を最初の非ゼロ放射と等しいとした判定だった。標準条件では最短の128・132に対し139・143だった。44.1 kHzの `hiss` の両端は最短時刻373・376と一致した。第2版では最短時刻を通常経路の下限とし、制御境界の `begin_block` を省く固定姿勢の短い上流対照を追加した。初期断面と各音響サンプルの更新は同じで、微小な圧力・流量の整理を行う制御経路だけが異なる。x86_64の浮動小数点状態レジスタを使う上流の減衰試験は、今回のarm64環境の実行対象外だった。[第1版の結果](../runs/alligator-fixed-voice-20261120-c/summary.json)・[第2版の条件](../cases/alligator-fixed-voice-v2.json)・[上流の制御境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)

対照では、口端と鼻端が4条件すべてで最短時刻に応答した。標準条件での先頭の絶対流量は、口端 `2.06×10⁻⁵¹ cm³/s`、鼻端 `1.28×10⁻⁵² cm³/s`。通常の制御境界では極小の節点圧力や枝流量を消去するため、最初の非ゼロ値の検出が11内部サンプル遅れた。44.1 kHzでは両端への到達が次の制御境界より前にあり、対照と通常経路の時刻が一致した。[第2版の計測値](../runs/alligator-fixed-voice-20261120-d/summary.json)

5条件の120,878出力フレームで、固定上流と声門の位相・瞬時F0は一致し、面積の最大差は `8.88×10⁻¹⁶ cm²`。観測用声門と実際のポート面積は全条件で一致した。公式デモの最初の76,800フレームでは、停止区間のフレーム73,414にだけビット差があり、最大差は `7.11×10⁻¹⁵` だった。登録した停止末尾のPCM RMSは持続区間の `2.96×10⁻⁵` 倍だった。

第2版の342項目を研究ディレクトリと `/tmp` から実行し、要約と観測ファイル49件のSHA-256が一致した。アザラシの気道と公式コール順序も、共通化の前後で要約と全観測ファイルが一致した。[別ディレクトリからの実行](../runs/alligator-fixed-voice-20261120-repeat/manifest.json)・[気道の回帰](../runs/seal-airway-mammal-regression-20261120/manifest.json)・[コールの回帰](../runs/seal-chug-alligator-final-regression-20261120/manifest.json)
