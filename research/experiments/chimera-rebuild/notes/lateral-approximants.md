# /l ɫ/ の側方通路と英語発話

比較するCHIMERAは `c6147d0198890475dbe8a65a0bb8f56240c539b7`。舌先・舌体と側方通路の関係を調べ、`Hello world` を英語入力から波形まで通す。

## 固定版の処理と観測点

1. IPAと英語をそれぞれ `render::speech`、`render::say` から `plan_utterance` に渡す。英語の句では辞書の /l/ が母音の前にあれば保たれ、語末または次が母音以外なら /ɫ/ に変わる。`Hello world` では `hello` の /l/ の直後は /oʊ/、`world` の /l/ の直後は /d/。表示は `həlˈoʊwˈɝɫd`。[IPA入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L110)・[英語入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[異音規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/english.rs#L282)
2. 成人男性では /l ɫ/ の優勢軸は舌先 (6.25, 9.68) cmと側方開き1（無次元）。/ɫ/ は舌体 (1.9, 6.8) cmも強く指定する。`oral_gestures_into` は音素区間 `[a,b]` に対し、`a−0.008` から `max(a+0.010,b)` まで保持する。入り30 ms、出18 ms、強さ40、速度1.3、速度延長45 ms。/lʲ/ の舌体は自由なので /j/ 寄りの弱い目標が重なり、/ɫ/ の舌体は /ɫ/ が担う。有声のまま調音が変わる。[音素の目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L230)・[口腔の計画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)・[口蓋化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L737)
3. 64出力フレームごとに調音目標を混合し、臨界減衰のばねを半陰的Euler法で更新する。側方開きの固有周波数は10 Hz、基準姿勢の重みは0.05。先に速度を、次に位置を進め、舌先や舌体の口蓋への接触を補正した姿勢から断面を求める。`compute` で局所的な面積の突起を抑えた後、口腔・前方の格子点のうち中点が舌先から1.4 cm未満であれば、面積へ `0.35×側方開き cm²` の下限を適用する。1次元モデルの音響網には増えた断面が渡る。この効果は全体の口端流量で観測する。`resample` はセルごとの調和平均と最小断面を作る。固定姿勢で `lateral=0.8` を与えた既存ケースでは、点38・39の下限0.28 cm²を独立計算で確認済み。[調音器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/control/articulators.rs#L109)・[制御周期](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[側方開きの面積下限](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1213)・[再サンプリング](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1305)・[固定姿勢の検証](area-profile.md)
4. 上流の発話テストでは音素や句をTypeScriptの参照結果に照合し、音声では句末の消音、調音の面積変化では母音遷移を確かめる。口蓋化されたジェスチャーの成分と保持時間には専用テストがある。[音素と句の上流テスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_phonetics_text.rs#L82)・[句末の音声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/speech_quality.rs#L81)・[幾何の連続性](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs#L155)・[口蓋化のテスト](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sound_marks.rs#L145)

## 実装前の予測と判定

内部96 kHz、出力48 kHzで、/l ɫ/ の音素を45〜75%進んだ窓を比較する。側方開きありでは中央値0.65以上、口腔は閉鎖閾値 `0.0002 cm²` 以上、有声化係数の中央値0.6以上を予測する。開きを0にする対照では、同じ舌先・舌体・唇の軌跡を保ち、窓の25%以上で口腔が閉じ、口端流量のRMSが通常の2/3以下になると予測した。側方位置は独立したばねでも計算し、/ɫ/ と /lʲ/ については舌体も判定する。英語は `həlˈoʊwˈɝɫd`、48 kHzで57,845フレームを予測する。各ケースで周期変動とドリフトをそろえ、PCMの最大絶対差 `10⁻⁶`、ホスト分割77と128のバイト一致を確認する。`Hello world` は既定の乱流を使う。

[/l/](../cases/lateral-l.json)・[/l/ の開き0](../cases/lateral-l-closed.json)・[/ɫ/](../cases/lateral-dark.json)・[/ɫ/ の開き0](../cases/lateral-dark-closed.json)・[口蓋化](../cases/lateral-l-palatalized.json)・[英語文](../cases/lateral-hello.json)

## 実装と測定値

/l ɫ/ の口腔ジェスチャーは /w/ と歯茎摩擦音と同じ保持・ランプの式を共有する。口蓋化は /l/ で既存の舌体目標を使う。CLIは側方軸の位置と合成目標を記録する。比較用の `lateral_opening_scale=0` は側方軸の初期姿勢とジェスチャー目標へ適用し、同じ強さと速度の窓を使う。対照の実行前に、通常ケースと候補ソースのSHA-256を照合する。[発話計画](../crates/vocal-core/src/phonetics/speech.rs)・[CLIと比較項目](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[計測器](../tools/measure_lateral.py)・[上流のMIT通知](../LICENSE-CHIMERA)

| 条件 | 中央窓の口腔最小断面 | 窓に占める閉鎖の割合 | 口端流量のRMS |
| --- | ---: | ---: | ---: |
| [/l/](../runs/lateral-l-20261119-a/summary.json) | 0.34011 cm² | 0% | 168.83 cm³/s |
| [/l/ の側方開き0](../runs/lateral-l-closed-20261119-a/summary.json) | 0 cm² | 54.65% | 13.61 cm³/s |
| [/ɫ/](../runs/lateral-dark-20261119-a/summary.json) | 0.34011 cm² | 0% | 169.56 cm³/s |
| [/ɫ/ の側方開き0](../runs/lateral-dark-closed-20261119-a/summary.json) | 0 cm² | 57.93% | 16.84 cm³/s |

両対照で舌先と舌体の座標、唇の3軸は全フレームで同一。開くと口端流量のRMSが /l/ で12.41倍、/ɫ/ で10.07倍になった。舌体 (X,Y) の中央値は /l/ で (2.095, 5.788) cm、/ɫ/ で (1.904, 6.778) cm、/lʲ/ で (3.442, 7.496) cm。事前に予測した /ɫ/ の舌体の後退は観測した。舌体の高さはこの /ɑ/ 条件で予測と逆に /ɫ/ の方が高かった。舌体が自由な /l/ は前後の /ɑ/ の目標に従うため、/ɫ/ の目標を指定する前後で高さの関係が変わる。[口蓋化](../runs/lateral-l-palatalized-20261119-a/summary.json)・[/ɫ/ の計画と観測](../runs/lateral-dark-20261119-a/summary.json)

側方位置の合成と半陰的Euler法は候補・上流と最大 `2.85×10⁻¹²` の差で一致した。通常の /l ɫ/ の窓のうち、対照で閉鎖した582・617フレームに着目し、前と現在の制御周期での側方位置を線形補間して0.35を掛けた。測定した口腔の最小断面との差は最大 `3.50×10⁻¹⁵ cm²`。格子で置いた下限が制御周期の補間を通って音響セルに届くことを確認した。[明るい側音の独立計算](../runs/lateral-l-closed-20261119-b/summary.json)・[暗い側音の独立計算](../runs/lateral-dark-closed-20261119-b/summary.json)

`Hello world` は `həlˈoʊwˈɝɫd` と表示され、両方の側音を含む全音素を48 kHzの57,845フレームにレンダーした。通常の上流CLIとIPAの表示と長さが一致した。声門の周期変動とドリフトを止め、乱流を有効にした固定版とのPCM最大絶対差は `5.82×10⁻¹¹`。6条件全体では `1.87×10⁻⁹` 未満だった。[英語の比較](../runs/lateral-hello-20261119-a/summary.json)・[英語のWAV](../runs/lateral-hello-20261119-a/artifacts/pcm-128.wav)

`/tmp` から6条件を再実行した。波形・設定・計画・観測を含む59ファイルが初回とバイト一致し、側方開き0の2要約に線形補間した面積下限の照合を追加した。全実行で77フレームと128フレームの分割はWAVと出力段CSVが一致した。再実行と回帰の入出力をマニフェストのSHA-256に照合した。/w/、/s/、基準IPA発話の回帰は合計30ファイル一致し、英語発音の回帰は16ファイルが一致した。発音JSONでは /l ɫ/ の対応状態が50箇所変わった。[英語再実行の記録](../runs/lateral-hello-20261119-b/manifest.json)・[/w/ の回帰](../runs/approximant-w-english-20261119-c/summary.json)・[/s/ の回帰](../runs/sibilant-s-20261119-g/summary.json)・[基準IPAの回帰](../runs/bilabial-nasal-vcv-20261119-g/summary.json)・[英語発音の回帰](../runs/english-frontend-20261119-f/summary.json)

候補のワークスペーステストとClippy、上流の `speech_quality`、`golden_phonetics_text`、`geometry_continuity`、`sound_marks` の既定テストが通過した。幾何の試験では、唇歯音で突き出した下唇を引き込む既知の1件が上流の設定で除外された。[固定版テストのログ](../runs/lateral-hello-20261119-b/artifacts/upstream-tests.log)
