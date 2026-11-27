# 両唇破裂音の閉鎖・開放と声門

比較するCHIMERAは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第5段階で /p b/ の口腔と声門のジェスチャーを発話の実時間レンダーへ接続する。

## 固定版の入口と機構

1. CLIの `speech` は最初の発話を50 msから計画し、予定時刻のジェスチャーを `HumanVoice::schedule` に渡す。音素は計画起点からさらに60 ms後に始まり、最後の発話後に350 msと200 msを足してWAV長を求める。[CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)
2. `inventory::phoneme` の /p b/ はともに優勢成分が唇の開きだけで、目標は −0.25 cm。母音の直後の閉鎖時刻の補正は5 msで、短い音では音素長から30 msを引いた非負の値が上限になる。実際のジェスチャーは補正後の時刻より22 ms早く保持に入り、音素終端より19 ms早く保持を解く。保持には最低10 ms相当の余裕を取り、`max(a+0.01,b−0.019)` で終端を求める。入り30 ms、出18 ms、強さ40、速度1.55倍、速度の延長45 ms。隣の母音が舌や顎を動かし、唇は優勢な閉鎖目標へ寄る。[目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L136)・[閉鎖時刻](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L712)・[口腔ジェスチャー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)
3. /p/ は音素区間の25%から声門開大を保持する。後続が母音で直前が /s/ でなければ、明示指定がないとき有気と判定する。有気は追加0.36 cm²で閉鎖区間の終端から20 ms（等速）先まで保持し、無気は0.22 cm²と4.8 ms。入りは35 ms、出は有気45 msと無気20 ms。/b/ の通常条件ではこの開大を作らない。話速が1を超える場合は調音・開大のランプと速度の延長を縮める。[有気の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L510)・[放気の上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/aspiration.rs)・[話速の後処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L748)
4. `HumanVoice::control` は出力64フレーム分ごとに目標を混合し、姿勢を更新して面積、最小断面、ポート面積を補間する。開大は基準面積にスコア値×`min(w/2,1)` を追加。呼気はスコア値×`min(w,1)` と呼気設定から肺のゲートを更新する。F0は基準重み0.02を加えた目標へ、対数領域で制御周期ごとに近づける。各内部サンプルで声門前後の圧差から声門面積を得て気道へ渡し、肺圧・声門・気道・放射を進める。[音源の制御周期とサンプル更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[制御式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)
5. 唇の最小断面が0.0002 cm²を下回ると音響ネットワーク上の閉鎖になる。上流の計測プローブでは声門の周期変動と気道乱流を0に設定し、既存エンジンの同じ入力・初期姿勢・F0で時系列を採取する。開放直後のPCMには、気道に蓄積した圧力の放出と動く形状の効果が入る。[気道の面積更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L234)・[高速発話での上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/fast_speech.rs)

## 実装前に登録した予測

各ケースを内側96 kHz、出力48 kHzで走らせ、計画・唇の姿勢・最小断面・口端と声門の流量・開大・PCMを観察する。計画時刻と重みの許容差は `10⁻¹²`、形状は絶対差 `10⁻⁹`、音響状態は列ごとのピーク比 `10⁻⁷`、PCMは絶対差 `10⁻⁶`。閉鎖・再開口は音素区間付近で、閉鎖時の口端流量と再開口後40 msのPCMピークを測る。[基準 /p/](../cases/bilabial-p.json)・[基準 /b/](../cases/bilabial-b.json)・[無気](../cases/bilabial-p-unaspirated.json)・[1.8倍速](../cases/bilabial-p-fast.json)

- /p/ の計画は209.38024〜289.13024 ms。唇目標の保持は192.38024〜270.13024 msとなる。/b/ は217.51984〜298.76984 msで、唇の保持は200.51984〜279.76984 ms。
- /p/ と無気の /p˭/ は同じ時刻の閉鎖を狙う。/p˭/ では声門の開大値と保持が小さくなる。/b/ では開大を作らず、唇の最小断面は両方の破裂音で閉鎖し、再開口の窓でPCMが戻る。
- 1.8倍速では音素を縮め、唇ランプ30/18 msと速度延長45 msをそれぞれ倍率で割る。異なるホストのブロック長でWAVと出力段の記録が一致する。

## 初回計測で見つかった閉鎖後の残留放射

`ɑpɑ` の初回は、唇の最小断面が閉鎖閾値を下回ったフレーム11,118と再開口の13,888で候補と上流が一致した。閉鎖区間の両端から10 msを除いた窓でも、上流に最大0.0037511 cm³/sの口端放射流量が残り、先に置いた `10⁻⁹ cm³/s` の基準は双方で不通過だった。閉鎖時は節点への枝流量と別に、放射負荷の慣性成分を内部サンプルごとに0.995倍して出力している。[初回の結果](../runs/bilabial-p-20261119-a/summary.json)・[初回のケースを含む実行記録](../runs/bilabial-p-20261119-a/manifest.json)・[上流の放射更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1102)

改訂した判定は、連続した閉鎖区間で、最初の口端放射流量から `0.995^(2n)` の独立計算で求めた減衰に絶対差 `10⁻¹⁰ cm³/s` 以下で一致し、再開口直前の残留率が0.1%以下になること。形状、計画時刻、他の音響値とPCMの許容差は初回の設定を使う。

1.8倍速では、最小断面による閉鎖が音素の計画開始から32.89 ms後で、閉鎖継続は284フレーム（5.92 ms）。初回の高速用判定は等速の30 msと鎮静後の残留率0.1%を流用し、固定上流と候補の双方が不通過だった。高速条件では、計画された音素区間内に閉鎖が始まり、少なくとも1制御周期ぶん続くことを確認する。再開口の時刻と全閉鎖区間での独立減衰式との照合を保ち、残留率は観測結果として記録する。短い閉鎖から等速相当の減衰量を要求するかどうかは、後続の発話品質の課題として初回の結果とともに残す。[最初の高速結果](../runs/bilabial-p-fast-20261119-b/summary.json)・[破裂の観測値を追加した高速結果](../runs/bilabial-p-fast-20261119-c/summary.json)

## 実装と比較結果

[発話計画](../crates/vocal-core/src/phonetics/speech.rs) は、既存の母音ジェスチャーに唇・開大・呼気・文末・ピッチを足す。[音源](../crates/vocal-core/src/voice.rs) では制御フレームで同じスコアを合成し、調音器と呼気・声門を更新する。計測CSVには出力1フレームの内部処理が終わった時点の値を保存する。最小断面で検出した閉鎖と再開口は `(frame+1)/48000` 秒。開放後5 ms内のPCMの最大絶対値を補助指標に加え、発話末尾と開放後40 msの判定は維持した。開大、圧力、流量、PCMの照合は周期変動と気道乱流を0にした条件で実施した。[CLI](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[比較器](../tools/measure_bilabial_stop.py)・[上流のMIT通知](../LICENSE-CHIMERA)

| 条件 | 最小断面による閉鎖 | 計画終端から再開口まで | 再開口から5 ms内のPCMピークまで | 候補と上流のPCM最大絶対差 |
| --- | ---: | ---: | ---: | ---: |
| [等速 /p/](../runs/bilabial-p-20261119-c/summary.json) | 57.71 ms | +0.224 ms | 3.396 ms | `1.82×10⁻¹²` |
| [等速 /b/](../runs/bilabial-b-20261119-c/summary.json) | 58.96 ms | −0.082 ms | 2.063 ms | `9.09×10⁻¹³` |
| [無気 /p/](../runs/bilabial-p-unaspirated-20261119-c/summary.json) | 57.71 ms | +0.224 ms | 3.396 ms | `3.64×10⁻¹²` |
| [1.8倍速 /p/](../runs/bilabial-p-fast-20261119-d/summary.json) | 5.92 ms | −5.496 ms | 3.313 ms | `1.86×10⁻⁹` |

4条件で閉鎖・再開口・開放直後のPCMピークのフレームが一致した。閉鎖中の放射流量と独立減衰式の差は最大 `1.0×10⁻¹⁵ cm³/s` 程度。通常の /b/ は唇が閉じ始めた時点で有声化の係数が約1を保ち、閉鎖中央では約0.072まで低下した。同じ時刻に向かう /p/ は有気指定で声門をより開き、閉鎖始点の係数は約0.020だった。無気の /p/ と有気の /p/ の唇の最小断面は全フレームで同じだった。[声門・放射の時系列](../runs/bilabial-p-20261119-c/artifacts/voicing.csv)・[有声条件の時系列](../runs/bilabial-b-20261119-c/artifacts/voicing.csv)

ホスト分割77・128フレームと別ディレクトリからの再実行を確認した。候補と上流の波形、出力段、観測CSV、計画の計32ファイルが各条件の先行実行とバイト一致した。候補の整形・ワークスペーステスト・Clippyと、上流の有気・高速発話テストが通過した。Clippyの初回判定で声門数値の検査式を整理する指摘があり、式を整理して再実行した。母音スコアと有声母音遷移の回帰は合計14ファイルで直前と一致した。[実行記録](../runs/bilabial-p-20261119-c/manifest.json)・[母音スコア](../runs/vowel-gesture-score-20261119-d/manifest.json)・[有声母音遷移](../runs/vowel-motion-voice-vowels-20261119-f/manifest.json)

声道形状から狭窄位置を求め、乱流源を自動設定する処理は /s z/ の工程につなぐ。今回の開放直後の波形は、気道の圧力・流量と幾何の変化による成分を比較した。
