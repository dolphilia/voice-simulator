# 予約を128フレームずらしたときに最初に変わる発声状態

## 上流の更新順

固定版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Safariで使った `playTune()` と同じ公開プランナーの `plan_song()` で、英語辞書から2音の「Pop Dee」を計画する。 `Engine::schedule()` は発声の時計に先行時間を足し、その分をジェスチャーの開始・終了に加える。出力は48 kHz、内部は96 kHz。 `HumanVoice::render()` は出力64サンプルごとに調音・呼気・音高の目標を更新し、出力1サンプルにつき内部計算を2回進める。予約を128フレームずらす今回の条件では、調音の更新格子上の位置は同じになる。[歌唱の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/singing.ts#L330)・[譜面の予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/engine.rs#L177)・[調音周期と描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L223)

各内部ステップで、声門は上下の圧差から振動の強さと開口面積を更新する。声門の位相は振動が出る前から `F0 / 内部レート / 周期の補正係数` だけ進む。声門面積をポートに適用した後、気道の計算は幾何を更新し、乱流の枝圧を加算してから枝流量と節点圧を更新する。乱流のレベルは枝の断面積と流量から求めたReynolds数に依存する。乱数と帯域フィルタは注入が0でも進み、注入時にはレベルにフィルタの出力を掛けた符号付き圧力が選択した枝へ入る。放射出力は口・鼻の流量に壁の寄与を加えた総量の時間微分で、間引きと出力処理を通ってPCMになる。[声門の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[乱流源の配置](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L329)・[乱流の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)・[放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1073)

## 条件と判定

前回のSafari録画から男声の設定、MIDI 60・64、各0.25拍、240 BPM、最初の拍0.35秒を読み込んだ。ネイティブでは描画前にブラウザの音源設定と自由な舌先を持つ中立姿勢を適用し、エンジンの16,384または16,512フレームまで描画してから同じ譜面を予約した。先行時間は1,440サンプル。予約直前を相対−1,441として採り、その後は出力1サンプルごとの状態から、位相、声門面積・流量、声門上下圧、乱流、放射の最初の規定値超過を調べた。2条件を通常の乱流量と、気道の乱流注入量だけを0にした状態でそれぞれ測った。[事前登録](../cases/upstream-song-schedule-state.json)・[ブラウザの基準](upstream-safari-song-fixed-schedule-frame.md)・[ネイティブの計測](../tools/upstream_song_schedule_state_probe.rs)

予約時の位相差が一定110 Hzで128出力サンプル進んだ値の0.02周期以内になること、通常条件でPCMの差がブラウザでの14,330サンプル目から128サンプル以内に現れることを事前に予測した。さらに、放射の差はPCM差より遅れず、乱流注入を0にしても位相とPCMに差が残ると予測した。音素と拍の比較は整数のサンプル位置で行った。[解析](../tools/measure_upstream_song_schedule_state.py)

## 実測

通常の乱流条件では、予約2位置のネイティブPCMがSafariの保存済みPCMとそれぞれ29,760サンプル全点でビット一致した。音素と拍も一致した。予約直前の声門位相は0.544340と0.838102周期で、差は0.293762周期。一定110 Hzで独立に計算した0.293333周期との差は0.000429周期だった。この時点でPCMに差は出ておらず、唇開きと呼気ゲートは全測定区間で登録した許容差内に収まった。[初回の結果](../runs/upstream-song-schedule-state-20261121-b/summary.json)・[再実行の結果](../runs/upstream-song-schedule-state-20261121-repeat-b/summary.json)

| 出力へ向かう差の観測点 | 通常の乱流 | 気道の乱流注入量0 |
| --- | ---: | ---: |
| 乱流が加算された枝圧の最初の差 | 14,256 | 加算なし |
| 声門面積の最初の差 | 20,878 | 20,878 |
| 放射流量の時間微分の最初の差 | 14,256 | 20,878 |
| PCMの最初のビット差 | 14,268 | 20,891 |
| PCM差が0.000001を超えた最初の位置 | 14,330 | 20,903 |

数値は譜面の時刻0からの出力サンプル番号。通常条件の14,256で初めて加算された圧力を採り、唯一活動していた乱流源が声門ポート70、注入先は両試行とも前方の咽頭枝13であることを確認した。声門の流量は両方で約159.421 cm³/s、乱流レベルは約0.0270748 dyn/cm²だが、枝圧は+0.00723553と−0.00369093 dyn/cm²だった。枝圧をレベルで割った値は+0.26724と−0.13632で、出力差はすでにフィルタを通過した乱流波形の値に現れている。ここでは声門面積は登録許容差内だった。[枝圧・活動源の記録](../runs/upstream-song-schedule-state-20261121-repeat-b/artifacts/probe.json)

乱流注入量を0にすると、最初にPCM差が閾値を超える位置は6,573サンプル、136.94 ms後ろに移った。その条件では最初の声門面積・流量の差と放射の差が同じ20,878サンプルで観測され、PCM差が後に続いた。比較は各出力サンプルの最後の内部ステップで行ったため、同じ出力サンプル内の2ステップのどちらが最初に変化したかは残る。乱流波形の差が、乱数の消費順とフィルタの履歴のどちらに最初に現れるかも未分離。[乱流注入の対照](../runs/upstream-song-schedule-state-20261121-repeat-b/summary.json)

## 照合と再現

初回の起動は計測用Pythonモジュールの読み込み先を誤り、上流ビルドと取得より前に終了した。修正後は計測を2回行い、最初に活動した乱流源の接続情報を追加してさらに2回実行した。後者の2回で取得判定各20件と予測各4件が通過。前後4回のPCM・計測CSVは全点でバイト一致した。側圧の初回値と閾値を別の読み取りで計算し直し、Safariの停止付き・連続録画の両方から切り出したPCMともバイト照合した。固定上流のブロック長と短音の拍位置のテストも各1件通過した。[変更前](../runs/upstream-song-schedule-state-20261121-a/manifest.json)・[変更前の再実行](../runs/upstream-song-schedule-state-20261121-repeat/manifest.json)・[接続情報を含む実行](../runs/upstream-song-schedule-state-20261121-b/manifest.json)・[再実行](../runs/upstream-song-schedule-state-20261121-repeat-b/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。各実行の入力20件と出力15件をサイズ・SHA-256で照合し、計122,944,884バイトをRTL9210B-CGに保存した。再実行は `/private/tmp` からPythonとスクリプトの絶対パスを指定した。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=70000000 ../../.venv/bin/python \
  tools/measure_upstream_song_schedule_state.py <実行ID>
```

次は研究版の同じ短い歌唱で予約前の描画量を128フレーム変え、今回同定した声門ポートから咽頭への最初の乱流注入と、放射・PCMに差が届く位置を固定上流と比べる。
