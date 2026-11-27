# 母音の調音ジェスチャーと目標の合成

比較するCHIMERAは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第5段階の発話区間を、既存の調音器に渡せる重み付き目標へ変換する。

## 上流の呼び出しと式

1. 上流CLIの `render speech` はスラッシュで発話を分け、`plan_utterance` が返したジェスチャーを `HumanVoice::schedule` へ渡す。計画の開始と終了は声のクロックで表した秒。ジェスチャー列と計画音素列は別々に返る。[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[発話計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L394)
2. 母音ごとに、すぐ前と次にある母音の区間から間隔 `d` を求める。隣がなければ間隔は80 ms。入りは `max(30 ms, 0.75d) + 10 ms`、出は `max(30 ms, 0.4d) + 10 ms`。直前から続く母音に明示の `glide` がある場合、その母音の入りは指定値と10 msの大きい方になり、前の母音の出はグライドの計画区間長と10 msの大きい方になる。音素間に子音があればこの上書きを適用しない。展開された二重母音の次の母音も、明示の `glide` がなければ通常の式を通る。[母音ランプ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L395)
3. 母音の目標値は較正データの舌体、顎、唇、舌根、喉頭、舌先の反りを使う。舌先の座標は反りが0.05を超える場合と /ɿ/ で使う。位置は cm、丸めや狭窄のつまみは無次元、軟口蓋のポート面積は cm²。目標を持たない成分は合成に参加しない。[較正母音の参照](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L165)
4. 各ジェスチャーの活性は入りで `(1−cos(πu))/2`、保持で1、出で `(1+cos(πu))/2`。正規化した時間 `u` はそのランプの0〜1。各制御成分で活性と強さの積を重みとし、重み付き平均と重みの総和を得る。速度倍率は適用窓内の最大値で、出の終端に `releaseHold` を足した時刻まで保持する。[活性と合成](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/score.rs#L273)
5. 音源の制御周期で合成結果を読み、基準姿勢の重み0.05を加えて調音器を更新する。軟口蓋は重みの半分を上限1で使って基準から移動する。速度倍率を適用するのは、その成分の合成重みが正のとき。調音器の位置は次に声道形状へ渡る。[制御周期](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[調音器の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)・[全成分と一成分の一致テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/score.rs#L443)・[早期リリースの上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/live_control.rs#L8)

## 実装前の判定条件

[登録ケース](../cases/vowel-gesture-score.json) では、成人男性の母音ジェスチャーを観察対象にする。制御間隔は96 kHzの120内部サンプル、1.25 ms。各入力の1,000フレームで活性、制御成分ごとの合成目標・重み・速度、調音器が実際に使った目標・位置・速度を比べる。時刻と目標・活性・重みは絶対差 `10⁻¹²`、調音器の状態は `10⁻¹⁰` 以下を許容する。

- `ɑpɑ` の /p/ は79.75 ms。最初の母音の出は41.9 ms、次の母音の入りは69.8125 msで、/p/ の中で両方が正になる幅は31.9625 ms。両母音の舌体目標が同じ条件では、重みが変わっても目標平均は2.022 cmを保つ。
- `ipɑ / ɑpɝ` では舌体の目標が変わり、/ɝ/ には舌先の座標も入る。`aɪ` の隣接した母音には40 msの下限が効く。1.6倍速の明示グライドでは /ɑ/ の出は後続 /i/ の計画長50 ms、/i/ の入りは指定された80 msとなる。その次で /t/ を挟む /ɿ/ の入りは50 msの子音間隔を使い47.5 ms。
- /ʏ/ には母音ジェスチャーがない。明示した255 msの長さが前後の /ɑ/ の間隔として残り、出112 msと入り201.25 msになる。
- 合成だけを観測するために入力した2件のジェスチャーでは、フレーム125で顎の重み2.5、目標0.8 cm。軟口蓋の目標は片方だけが持ち、重みは1。有効目標は `−0.15 + 0.5(0.95 + 0.15) = 0.4 cm²`。フレーム300は活性の外かつ速度保持の終端なので速度2を報告する。調音器の適用速度は重み0で1に戻る。フレーム301の合成速度も1。

## 初回照合で見つかった話速の処理

初回実行では、倍速条件の /ɑ/ の入りが候補70 ms、上流43.75 ms。フレーム33（41.25 ms）の活性に最初の差が生じた。発話区間そのものは一致した。上流の `plan_utterance` 末尾から `shorten_timing` へ進むと、話速が1を超えるときは組み立て済みのランプと速度の保持時間も話速で割る。ピッチと呼気に目標を持つジェスチャーはこの処理から外れる。1以下の話速に対してランプを伸ばす後処理はない。[初回の判定と予測の版](../runs/vowel-gesture-score-20261119-a/manifest.json)・[最初の差](../runs/vowel-gesture-score-20261119-a/summary.json)・[上流の後処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L748)

初回の予測に記録した1.6倍速の50・80・47.5 msは、後処理前の値だった。後処理を含む版では31.25・50・29.6875 msを予測し、0.8倍速の対照も追加した。0.8倍速では後続母音の計画長100 ms、明示した入り80 ms、子音100 msから求めた入り85 msになる。数値の許容差は初回の設定を使う。

## 実装と測定

[母音の計画](../crates/vocal-core/src/phonetics/gestures.rs) は直前と直後の母音区間を一巡で参照する。[合成](../crates/vocal-core/src/score.rs) は調音器17成分と音源5成分の目標をまとめて計算し、目標がある成分を更新する。候補は不在の目標を型で表し、上流ではNaNが不在を表す。この段階は固定したジェスチャー列を時刻で評価する。タグによる開放と期限切れの除去は後続のライブ制御で扱う。CLIの観測クロックは制御フレーム番号と周期の積で定義し、位置は各フレームの更新後に記録する。[較正目標の由来と照合](human-body-calibrated-vowels.md)・[上流のMIT通知](../LICENSE-CHIMERA)

成人男性の較正母音26件の目標が一致した。8入力、計8,000フレームで、活性、合成目標、重み、速度、調音器の追従を固定版と照合した値はすべて一致した。初回テンプレートの姿勢値を借用して変換する際にRustの所有権エラーが出たため、数値だけで構成する姿勢型をコピー可能にした。上流のスコア、早期リリース、発話の既存参照、速い発話の各テストと、候補のテスト・Clippyが通過した。[計測器](../tools/measure_vowel_gesture_score.py)・[最終の判定](../runs/vowel-gesture-score-20261119-b/summary.json)

`ɑpɑ` の重なりはフレーム176〜201で観測された。左右の母音で同じ舌体目標を共有するため、合成結果は重みが変わっても2.022 cm。独立した三角関数による活性と実効目標との差は最大 `5.33×10⁻¹⁵`。舌体目標が異なる `ipɑ` では、舌体の前後位置が150 msの3.639 cmから400 msの2.064 cmに移った。軟口蓋の制御実験では、重みが0のときでも速度窓の端で合成速度2が残り、調音器はその時点で基準速度1を使った。[独立計算と制御区間](../runs/vowel-gesture-score-20261119-b/summary.json)

研究ワークスペースと `/tmp` での実行で、候補・上流の観測JSON、設定、較正表、要約の5ファイルがバイト一致した。既存の発話区間9ファイルと、従来の調音器計測5ファイルも直前の通過版と一致した。[再実行](../runs/vowel-gesture-score-20261119-c/manifest.json)・[発話区間の回帰](../runs/speech-timing-20261119-c/manifest.json)・[調音器の回帰](../runs/articulation-vowels-free-20261119-g/manifest.json)

子音の閉鎖・摩擦・鼻音の制御と候補PCMの照合は後続。今回の `ɑpɑ` 比較では、子音が占める計画時間に母音側の目標がどう変わるかを観測した。
