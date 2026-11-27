# 軟口蓋摩擦音 /x/

上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7` に固定し、読解と予測を実装前に記録した。[登録ケース](../cases/velar-fricative.json)

## 読解

- 発話は IPA の区間を `plan_utterance` が受け取り、`inventory::phoneme` で体型別に目標を解決する。/x/ は無声摩擦音で基礎長0.12 s。舌背前後 `TbX` は2.3 cm、高さ `TbY` の既定値は7.7 cm。較正の設定は男性参照で狭窄0.18 cm²を狙い、実行時には生成済みの男性7.365、女性7.430、子ども7.499 cmの高さを使う。混合体型では三端点を体型の重みで補間する。較正値は目標姿勢であり、発話中の最小断面は調音補間と他の軸にも依存する。[目録](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L197)・[体型別目標の解決](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L264)・[較正表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/consonantTargets.generated.json)
- `oral_gestures_into` は高さを主要軸にして、音素区間を `[a,b]` とすると `a−8 ms` から `max(a+10 ms,b)` まで強さ40、立ち上がりと解放各30 ms、解放の保持45 msで駆動する。舌背だけを主要軸にする速度補正は `1+(1.3−1)×0.35=1.105`。前後の重みは0.25、立ち上がりと解放各50 ms。/xʲ/ は主要軸に含まれない前後だけに /j/ の3.8 cmを強さ3で加える。声門の開大は `a−15 ms` から `b+5 ms` の間に0.30 cm²を強さ6で指定する。話速が1より大きいと調音ジェスチャーのランプと保持が話速で割られる。[発声側](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L508)・[二次口蓋化と話速](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L737)・[口腔側](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/planner.rs#L820)
- `HumanAirway::commit` は姿勢から咽頭・口腔の代表断面と最小断面を準備し、管の目標を渡してから `update_noise` を呼ぶ。咽頭から口腔の順に、最小の正の断面積 `A` を探す。体型縮尺を `k` とすると、狭窄音源は `1.364×10⁻⁶ × [1−smoothstep(0.35 k²,0.90 k²,A)]` で重みづけされる。前後の注入位置は現在のセル長 `dx` に対して `max(1,round(0.9 k/dx))` セル離し、管端で制限する。咽頭と口腔の境目などで有効な枝が得られない場合は登録を省く。帯域は高域通過350 Hzと低域通過2600 Hz。歯への衝突は狭窄から切歯までの距離と狭窄の面積に追加の条件を持つ。[断面と乱流の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L310)
- `AirwayNetwork::compute_noise` は各内部ステップの枝流量 `U`（cm³/s）と面積 `A`（cm²）から `Re=2|U|/(ν√(πA))` を求める。開いた枝で `Re>1800` なら、振幅は `x=Re²−1800²` に対して `x/(1+x/(12000²−1800²))` に比例する。基準96 kHzからの換算は `√(96000/fs)`。フィルタを通した乱数を、流向に応じて枝へ圧力（dyn/cm²）として加える。音源の登録と実際の圧力注入は、この二段階により別々に調べられる。[注入式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1155)
- ロシア語の `word_before` は「х」を /x/ に写像する。歌唱では母音を拍に置くため、`sing` が既定長を0.8倍した子音を拍の手前へ配る。上流のロシア語試験は「в ти́хом」の発話と /t j/ を含む歌唱音節を確認する。既存の有声摩擦音試験で /x/ 自体の音響は扱われていないので、今回の IPA と歌唱の測定で補う。[ロシア語写像](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/russian.rs#L196)・[歌唱の時刻割当](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L193)・[ロシア語試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/russian.rs#L218)・[摩擦音試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voiced_fricatives.rs#L29)・[固定狭窄の圧力差試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

## 事前登録した予測

男性・同話速・同F0の /ɑxɑ/、/ixi/、/ɑxʲɑ/ を中央50%で比べる。前舌母音と二次口蓋化はそれぞれ舌背を0.20 cm以上前進させると予測する。調音目標は体型別の三端点と高速の混合条件で照合する。前後の母音に挟んだ男性の /x/ では中央区間の15%以上で狭窄音源が活動すると予測する。歯から体型換算4 cm以上離れた登録箇所には歯の音源が付かず、乱流倍率0の対照は配置を保って圧力が消えると予測する。「ти́хо」は2音節に分かれ、/x/ は第2拍直前の96 msを占める予定とする。先行母音と中央の咽頭・口腔の実断面を記録し、音源の位置と照合する。

## 第1版の反証と第2版の登録

第1版の93項目のうち22項目が外れた。固定上流と候補の計画・内部状態・PCMは許容差内で一致しており、最初に外れたのは計画の基礎長と実時間を同一視した条件だった。語中の発話には `klatt_durations` が適用される。既定120 ms、下限72 ms、語中の係数0.85で `72+(120−72)×0.85=112.8 ms`。高速条件はさらに1.3で割る。歌唱では既定長の0.8倍を明示長として渡すので、96 msの予測は通った。[第1版の判定](../runs/velar-fricative-20261120-a/summary.json)・[長さの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/durations.rs#L105)

音素区間全体で狭窄乱流の活動は検出されなかった。例えば男性 /ɑxɑ/ の中央は、最小正断面の中央値0.141 cm²で、候補セル20を一貫して選んだ。96 kHzの男性モデルでは咽頭のセル数が18で、咽頭の直後にある全体番号18に対応する枝がない。セル20が選ばれても後向きの注入先が18なら、狭窄源は登録されない。/ixi/ の中央は最小断面の中央値0.950 cm²で、面積からの登録上限0.90 cm²を超えた。いずれも声門乱流は中央全体で活動した。[第1版の時系列](../runs/velar-fricative-20261120-a/manifest.json)・[セル数と枝の定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L107)・[枝の割当て](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L356)

第2版では、部位の解剖学的長さから試行ごとの候補セル・前方・後方を計算し、登録の有無、登録時のゲインと低域通過周波数を独立に照合する。男性の二条件で枝の境界と面積閾値がそれぞれ中央の半分以上を占めると予測する。乱流を入れた条件は中央の半分以上で声門乱流が活動すると予測する。第1版の狭窄乱流の活動率は第2版でも測定し、両版の結果を残す。[第2版登録](../cases/velar-fricative-v2.json)

## 実装

既存の `fricative_gestures` に舌背を主要軸とする /x/ を追加し、生成済みの較正表を高さの選択に使った。調音ジェスチャーは IPA 発話・歌唱で共通。CLI の観測では最小断面、各音源の登録位置と圧力、舌背の位置に加え、登録理由の再計算に必要な咽頭・口腔のセル数と解剖学的長さを出力する。上流は固定のまま、既存の比較用プローブから同じ状態を採った。ブラウザでは歌詞入力から実時間の AudioWorklet で生成し、保存した入力を CLI で再実行する。[発話の調音](../crates/vocal-core/src/phonetics/speech.rs)・[較正表の読込](../crates/vocal-core/src/phonetics/catalog.rs)・[観測入口](../crates/vocal-cli/src/timing_case/speech_voice.rs)・[上流の観測プローブ](../tools/upstream_bilabial_probe.rs)・[比較用スクリプト](../tools/measure_velar_fricative.py)

## 第2版の実測

発話7条件と歌唱1条件で93項目が通過した。上流との調音ジェスチャー・内部状態は登録した許容差内で一致し、加工前PCMの最大絶対差は `4.66×10⁻¹⁰`。出力ブロック長128と77は全条件でWAVとPCMのCSVがバイト一致した。狭窄音源の登録が予測されたフレームは全件で登録と帯域が一致した。男性 /ixi/ は前後の母音を含めると10,304フレームに狭窄源が登録された。[第2版の結果](../runs/velar-fricative-20261120-b/summary.json)・[コマンドと出力の記録](../runs/velar-fricative-20261120-b/manifest.json)

| 条件 | 中央の舌背Xの中央値（cm） | 最小の正の目標断面の中央値（cm²） | 中央で多かった登録を妨げる条件 |
| --- | ---: | ---: | --- |
| 成人男性 /ɑxɑ/ | 2.171 | 0.141 | 枝の境界 100% |
| 成人男性 /ixi/ | 3.178 | 0.950 | 面積上限 100% |
| 成人男性 /ɑxʲɑ/ | 3.440 | 0.950 | 面積上限 100% |
| 成人女性 /ɑxɑ/ | 2.065 | 0.058 | 枝の境界 100% |
| 子ども /ixi/ | 3.200 | 0.520 | 面積上限 100% |
| 混合体型 /ɑxɑ/、話速1.3 | 2.160 | 0.123 | 枝の境界 100% |
| 成人男性「ти́хо」 | 2.886 | 0.805 | 枝の境界 52.8%、面積上限47.2% |

男性 /ixi/ の舌背は /ɑxɑ/ より1.007 cm前にあり、/ɑxʲɑ/ は1.268 cm前にあった。登録したすべての /x/ の区間で狭窄音源の活動率は0%。通常条件の中央では声門乱流が全フレームで活動した。乱流倍率0の /ɑxɑ/ は舌背、断面、音源登録を保ち、声門音源の前方枝圧力の中央区間のRMSが22.31 dyn/cm²から0になった。改善を試す際は、まず男性 /ɑxɑ/ の形状と入力を固定して、境界に当たる注入先の割当てだけを変え、狭窄音源の活動率、放射の帯域別電力と過渡を比べる。[第2版の中央区間の観測](../runs/velar-fricative-20261120-b/summary.json)

「ти́хо」は「ти́」「хо」の2音節。/x/ は0.904〜1.000 sで第2拍に終わった。ChromiumのAudioWorkletで舌背と声門を含む1,425点の時系列を採取し、91,200サンプルの加工前PCMをCLIと保存ケースの再演にビット単位で照合した。16音節の上流ロシア語デモの計画を現在のCLIで開くと、音響未対応は /tʃ/ のみ。[ブラウザの結果](../runs/velar-fricative-20261120-b/summary.json)・[デモの既存入力](../runs/russian-lyrics-20261120-repeat/artifacts/lyric-inputs.json)

固定上流の `russian`、`voiced_fricatives`、`airway_adversarial` の27テストを確認した。候補の `cargo fmt --all --check`、`cargo test --locked --workspace`、`cargo clippy --locked --workspace --all-targets -- -D warnings` が通過した。唇歯摩擦音の回帰はネイティブの110項目が通過した。[上流テスト](../runs/velar-fricative-20261120-b/artifacts/upstream-tests.log)・[唇歯摩擦音の回帰](../runs/labiodental-fricatives-20261120-velar-regression/manifest.json)

第2版は研究ディレクトリと `/tmp` から再実行し、両方で93項目を通過した。出力95件のうち、候補と上流のCSV・PCM、保存ケース、WASMを含む87件のSHA-256が一致した。要約ではブラウザの停止時刻の記録に差があり、舌背などの観測値照合とPCMの判定値は一致した。[再実行の記録](../runs/velar-fricative-20261120-repeat/manifest.json)
