# 訓練資料拡張による共有スペクトル制御の結果

2026-10-05。包括品質目標は未達。最終音源は非ニューラルを維持し、同じ教師・全区間スペクトル表現・16特徴・c1..c8/L1 .5・WORLD変換・固定gain .25の下で、17文共有モデルと資料拡張モデルを比較した。

訓練候補96文（短48/長48）は教師出力前に固定した。旧17文209目標をbyte再利用し、新79文をKokoro jf_alpha/seed20261002/CPU4で生成した。旧2教師のraw byte再現と予測継続長一致を確認してから新生成へ進んだ。教師は自然さ資格ある正解ではなく、内部予測時刻も音響境界GTではない。

全96文を分母に残し、受理80文（短45長35）、1629対象区間。失敗は次のとおり。
- coverage-train-02 米を炊く。 全音素数不一致
- coverage-train-25 角を曲がる。 全音素順序に非同値
- coverage-train-30 箱を積む。 全音素順序に非同値
- coverage-train-39 朝の台所で黄色い箱を並べ一番端に赤い印をそっと付けました。 全音素順序に非同値
- coverage-train-43 朝の台所で青い布を広げ風で飛ばないよう両端に石を置きました。 全音素数不一致
- coverage-train-46 朝の台所で赤い鉛筆で太い線を引き下に短い名前を書きました。 全音素数不一致
- coverage-train-48 夕方の庭で黄色い箱を並べ一番端に赤い印をそっと付けました。 全音素順序に非同値
- coverage-train-52 夕方の庭で青い布を広げ風で飛ばないよう両端に石を置きました。 全音素数不一致
- coverage-train-55 夕方の庭で赤い鉛筆で太い線を引き下に短い名前を書きました。 全音素数不一致
- coverage-train-57 駅の近くで黄色い箱を並べ一番端に赤い印をそっと付けました。 全音素順序に非同値
- coverage-train-61 駅の近くで青い布を広げ風で飛ばないよう両端に石を置きました。 全音素数不一致
- coverage-train-64 駅の近くで赤い鉛筆で太い線を引き下に短い名前を書きました。 全音素数不一致
- coverage-train-66 山の麓で黄色い箱を並べ一番端に赤い印をそっと付けました。 全音素順序に非同値
- coverage-train-70 山の麓で青い布を広げ風で飛ばないよう両端に石を置きました。 全音素数不一致
- coverage-train-73 山の麓で赤い鉛筆で太い線を引き下に短い名前を書きました。 全音素数不一致
- coverage-train-75 町の広場で黄色い箱を並べ一番端に赤い印をそっと付けました。 全音素順序に非同値

最低80文・短32長32・全5母音・全対象3frameを事前登録どおり適用した。失敗を見た後の読み修正や代替文追加は行わなかった。新3fitの回帰は等発話平均目的のpenalty10/17を維持し、受理N文でlambda10*N/17を用いた。NNは同16→16tanh→16tanh→8、seed20261005、500step。最終直接/学生各128係数と標準化32値は不変。旧3モデルはhash再利用し、fitを繰り返さなかった。

訓練projected MSE {"native": 0.005716578883008448, "direct96": 0.001558951647939027, "neural96": 0.0007082592852959417, "student96": 0.0016000824655564294}。訓練lossと訓練672波形の認識は独立品質証拠ではない。確認文は新短8/長8と既知8を出力前固定し、native/旧direct/旧NN/旧student/新direct/新NN/新student×2指定の336診断波形を生成した。

native対比の整数誤り・全群結果:

legacy_diagnostic
- native: whisper 22→22/314、不通過群0; reazon 36→36/314、不通過群0; 工学 True、固定支持欠損0
- direct17: whisper 22→22/314、不通過群0; reazon 36→36/314、不通過群0; 工学 True、固定支持欠損0
- neural17: whisper 22→18/314、不通過群0; reazon 36→33/314、不通過群0; 工学 True、固定支持欠損0
- student17: whisper 22→20/314、不通過群0; reazon 36→36/314、不通過群0; 工学 True、固定支持欠損0
- direct96: whisper 22→20/314、不通過群0; reazon 36→36/314、不通過群0; 工学 True、固定支持欠損0
- neural96: whisper 22→22/314、不通過群0; reazon 36→36/314、不通過群0; 工学 True、固定支持欠損0
- student96: whisper 22→21/314、不通過群5; reazon 36→36/314、不通過群0; 工学 True、固定支持欠損0

prospective_once
- native: whisper 51→51/656、不通過群0; reazon 60→60/656、不通過群0; 工学 True、固定支持欠損0
- direct17: whisper 51→47/656、不通過群4; reazon 60→54/656、不通過群3; 工学 True、固定支持欠損0
- neural17: whisper 51→48/656、不通過群0; reazon 60→57/656、不通過群4; 工学 True、固定支持欠損0
- student17: whisper 51→49/656、不通過群2; reazon 60→56/656、不通過群2; 工学 True、固定支持欠損0
- direct96: whisper 51→48/656、不通過群4; reazon 60→52/656、不通過群0; 工学 True、固定支持欠損0
- neural96: whisper 51→52/656、不通過群9; reazon 60→56/656、不通過群2; 工学 True、固定支持欠損0
- student96: whisper 51→46/656、不通過群2; reazon 60→53/656、不通過群0; 工学 True、固定支持欠損0

資料拡張対旧モデル:
- legacy_diagnostic/direct96/whisper: 22→20/314、不通過群0
- legacy_diagnostic/direct96/reazon: 36→36/314、不通過群0
- legacy_diagnostic/neural96/whisper: 18→22/314、不通過群12
- legacy_diagnostic/neural96/reazon: 33→36/314、不通過群6
- legacy_diagnostic/student96/whisper: 20→21/314、不通過群6
- legacy_diagnostic/student96/reazon: 36→36/314、不通過群0
- prospective_once/direct96/whisper: 47→48/656、不通過群10
- prospective_once/direct96/reazon: 54→52/656、不通過群0
- prospective_once/neural96/whisper: 48→52/656、不通過群14
- prospective_once/neural96/reazon: 57→56/656、不通過群0
- prospective_once/student96/whisper: 49→46/656、不通過群4
- prospective_once/student96/reazon: 56→53/656、不通過群2

新学生対新直接回帰:
- legacy_diagnostic/whisper: 20→21/314、不通過群8
- legacy_diagnostic/reazon: 36→36/314、不通過群0
- prospective_once/whisper: 48→46/656、不通過群4
- prospective_once/reazon: 52→53/656、不通過群6

訓練の工学診断（全672分母、独立品質証拠ではない）: {"native": {"expected": 96, "completed": 96, "E0_pass": 96, "support_complete": 96, "missing_support": [], "training_not_independent_quality": true}, "direct17": {"expected": 96, "completed": 96, "E0_pass": 96, "support_complete": 96, "missing_support": [], "training_not_independent_quality": true}, "neural17": {"expected": 96, "completed": 96, "E0_pass": 96, "support_complete": 96, "missing_support": [], "training_not_independent_quality": true}, "student17": {"expected": 96, "completed": 96, "E0_pass": 96, "support_complete": 95, "missing_support": [{"id": "coverage-train-27/neutral/student17", "indices": [7]}], "training_not_independent_quality": true}, "direct96": {"expected": 96, "completed": 96, "E0_pass": 96, "support_complete": 95, "missing_support": [{"id": "coverage-train-27/neutral/direct96", "indices": [7]}], "training_not_independent_quality": true}, "neural96": {"expected": 96, "completed": 96, "E0_pass": 96, "support_complete": 96, "missing_support": [], "training_not_independent_quality": true}, "student96": {"expected": 96, "completed": 96, "E0_pass": 96, "support_complete": 95, "missing_support": [{"id": "coverage-train-27/neutral/student96", "indices": [7]}], "training_not_independent_quality": true}}

限定支持 {"native": true, "direct17": false, "neural17": false, "student17": false, "direct96": false, "neural96": false, "student96": false}

最終依存は新16文×2指定×5非ニューラル方式、160組/320生成で通常・OS隔離と診断波形の完全一致を確認した。NN/教師/訓練/保存波形/旧係数/ネットワークを実拒否。bundleにWAV/PTなし。MCP c0/c9以降、LF0/LPF、HMM時計・状態を全1008波形で独立再検査した。工学・単独実行と知覚品質を区別する。

費用 {"setup": 118, "teacher": 81, "dsp": 3738, "inverse": 63, "audit": 14, "train": 3, "render": 1328, "ai": 2028}、ASR新1740、完全一致再利用276。初期helperコピーの不存在を残し、必要sourceを追加した。教師領域の隔離拒否を生成前に拡張し、同一wave/text/engineの旧17評価cache再利用をASR前に固定した。旧結果/封印/閾値/予算の上書きなし。

未達: 日本語の当該非ニューラル音源に資格ある知覚評価、独立最終品質確認、広い文脈/複数声の一般化。既知文や少数確認の合格を全体品質へ読み替えない。

このスペクトル経路は、中央窓gate不足・17文共有制御・資料拡張の3不通過に達した。次は時間/励振/調音の別経路へ切り替える。残額内の研究を継続し、ここで全体を終了しない。
