# アメリカアリゲーターの `dance`

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` のCLIは持続・停止・`bellow`・`growl`・`hiss` の後、48 kHzのフレーム336,000から2.2秒を描画する。末尾は441,600。上流の単発試験 `alligator-call-dance` は89,760フレームでPCMとテレメトリを照合する。上流の説明にある水面の揺れに対応する物理領域は実装に含まれず、本比較で観測するのは気道と体壁の放射である。[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[固定試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[気道の構築](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L24)

`dance` は音高18 Hz、口0と、粗さを所有する。ゲートは1.6秒まで1、1.7秒で0へ戻る。粗さは最初のキーに0、最後のキーに0.75があり、ゲート保持中から直線で上がる。音高と口はそれぞれ単一キーなので保持する。口0は端の断面0.05 cm²に対応する。開始音高の倍率は18 Hzを基準に掛ける。`hiss` はこのコールに含まれないため、切り替えとともに以前の `hiss` の所有が解除され、保存した手動値が戻る。目標の変更後には既存の制御境界と平滑化を経る。[danceのキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L116)・[コールの所有と補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L233)

平滑粗さ `c` は、周期境界の写像 `x ← (2.9+1.1c)x(1−x)`、周期長への寄与 `0.45c(x−0.5)`、振幅への寄与 `1.1c(x−0.5)` に入る。ジッター `0.01+0.05c` とシマー `0.05+0.25c` は粗さ0でも残り、瞬時F0には8セントのドリフトが作用する。声門面積で気道を駆動し、壁・口端・鼻端の放射流量を合成して差分を取り、さらに間引きと12 HzのDC除去を行う。そのためPCMのスペクトルは声門面積や気道圧と異なる。[声門係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/alligator.rs#L46)・[周期更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L182)・[描画と出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L365)

## 事前登録

48 kHzは公式順序の全PCM、44.1 kHzは `hiss` からの途中切り替えと24 Hzへの移調、96 kHzは18 Hzの単独を調べる。個別のキーから0.3〜0.9秒に粗さが上がることを確かめ、同区間を平均除去とHann窓で解析する。声門面積のピークは既定なら15〜21 Hz、移調なら20〜28 Hzの範囲を予測する。96 kHzの対照は同じ体型、初期状態、音高、口、鼻腔と呼気を使い、コールの代わりに同じサンプルで手動ゲートを開く。粗さ0で固定した対照より、コールの平均の周期長倍率が大きくなると予測する。音源以外の条件が一致したことを時系列で確認し、周期長倍率を位相と瞬時F0から逆算する。[登録した入力・計測範囲・許容差](../cases/alligator-dance.json)

## 実装と実測

既存の `AlligatorCall` に `Dance` のキーを追加した。CLIの `play_call` から同じ制御時計、キー補間、所有値の復帰、声門・気道の更新を通る。登録した3レートで、候補と上流の肺圧・声門位相・瞬時F0はサンプル単位で一致した。内部サンプルの位相増分と瞬時F0から求めた周期長倍率と、独立した周期境界の写像・乱数計算との差は最大 `2.22×10⁻¹⁶` だった。[コール定義](../crates/vocal-core/src/airway/alligator/call.rs#L54)・[計測器](../tools/measure_alligator_dance.py)・[実行の判定](../runs/alligator-dance-20261120-a/summary.json)

| 条件 | 開始要求・初回制御・所有終了の出力フレーム | 声門面積のピーク | PCMのピーク | PCMの最大絶対差 |
| --- | --- | ---: | ---: | ---: |
| 48 kHz、公式デモ全体 | 336,000・336,000・420,032 | 18.33 Hz | 36.67 Hz | `9.31×10⁻¹⁰` |
| 44.1 kHz、`hiss` から切り替え、24 Hz | 39,001・39,040・116,224 | 23.33 Hz | 46.67 Hz | `7.45×10⁻⁹` |
| 96 kHz、単独 | 17・64・168,128 | 18.33 Hz | 35.00 Hz | `1.16×10⁻¹⁰` |

ピークはいずれも最初の制御から0.3〜0.9秒の10〜80 Hz内で調べた。この窓の周波数刻みは約1.67 Hz。48 kHzの公式条件では気管端・咽頭入口の圧力と、壁面・口端・鼻端の体積速度がすべて18.33 Hzで最大となった。PCMの12〜25 Hzの帯域RMSは0.01828、25〜80 Hzは0.02705だった。放射流量の差分と出力段によって成分の比が変わりうる。個別の寄与は、保存した流量を同一の出力段に再入力して調べられる。[スペクトルと帯域RMS](../runs/alligator-dance-20261120-a/summary.json)

96 kHzの同じ窓で、粗さ0固定では11周期の周期長倍率が平均1.000、標準偏差0.00872だった。コールでは10周期が平均1.021、標準偏差0.02262だった。ゲート、肺圧、口先と鼻腔ポートの面積、平滑音高、瞬時F0は対照と一致した。粗さの曲線は周期境界の写像とジッターの両方に入るので、この比較は両方を含む効果を測っている。[粗さ0の対照](../runs/alligator-dance-20261120-a/summary.json)

44.1 kHzの切り替え要求39,001で `hiss` の目標は手動値0.12へ戻り、平滑値は39,040で変わった。同じ制御境界で新しい音高目標24 Hzと口の目標0が入った。53,001で呼気圧22 cmH₂Oと `hiss` 0への変更が目標に入り、音高31 Hz・粗さ0.65・口0.24の手動値は所有終了の116,224で目標に戻った。[境界を含む実測](../runs/alligator-dance-20261120-a/summary.json)

## 残る差と再現

公式CLIの441,600フレームを末尾まで照合した。全体で16フレームの単精度値に差があり、`dance` 開始後の105,600フレームでは4フレーム、最大絶対差 `2.27×10⁻¹³` だった。全体の最初の内部差は、持続音の内部サンプル1の肺流量に現れた。気管端圧の最初の差は46、声門流量は47、壁面放射は48に現れた。公式CLIとの最初のPCM差は出力73,414、`dance` 区間では全体の出力356,373だった。計測用の上流PCMと、公式CLIが書き出した浮動小数点WAVは全フレームでビット一致した。[公式波形と内部系列の照合](../runs/alligator-dance-20261120-a/summary.json)・[実行手順とSHA-256](../runs/alligator-dance-20261120-a/manifest.json)

研究ディレクトリと `/tmp` で同じケースを実行し、各316項目を通過した。要約とWAV・CSV・JSONの計測ファイル30件が一致した。`hiss` の変更前と変更後も、それぞれ280項目を通過し、要約と計測ファイル25件が一致した。[danceの再実行](../runs/alligator-dance-20261120-repeat/manifest.json)・[hissの変更前](../runs/alligator-hiss-before-dance-1/manifest.json)・[hissの回帰](../runs/alligator-hiss-dance-regression-20261120/manifest.json)
