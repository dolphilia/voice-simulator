# 中国語歌唱の鼻音韻尾 /n/・/ŋ/

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`。母音から鼻音への流量の移り方と句末保持を実装前に登録した。[登録ケース](../cases/mandarin-nasal-rhymes.json)

## 読解

- `pinyin_syllable` は「班」「帮」「东」「英」の韻尾に明示長 `/n/ 0.07 s` または `/ŋ/ 0.08 s` を置き、`nasalLead=0.6` と `closing=0.2 s` を伴う。歌唱の `plan_song` は拍を絶対秒にし、同じ句の次の頭子音と現在の韻尾を引いて母音区間 `[a,b]` を決める。メリスマの終端では元の音節の韻尾を使う。句末の休止枠は最終句50 ms、途中の句120 msで、その音符長の30%を超えない。閉じる韻の指定がある鼻音から `closing_spans` と句末の `final_coda` を作る。[中国語音節](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/mandarin.rs#L145)・[歌唱時間と韻尾](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L220)
- 鼻への通路は `nasal vowel` を `b−0.060` から `b+0.020 s` まで強さ2、面積目標0.30 cm²とし、立上がりを `min(0.6(b−a),0.25)` 秒、下降を0.03秒にする。鼻子音そのものの軟口蓋制御には、既存の強さ4と面積0.45 cm²のジェスチャーが重なる。舌体の `coda approach` は `b−0.010` から `b+0.020 s`、立上がりは `min(0.15,0.5(b−a))` 秒。/n/ は強さ0.6で舌体X/Yを3.2/7.4 cmへ、/ŋ/ は強さ1.2で、母音のYが6.95 cm未満ならYを7.95 cmへ、Xが3.0 cmを超えればXを2.83 cmへ寄せる。男性の /ɑ/ はYだけ、/i/ はXだけ、/ʊ̠/ はどちらも条件外。[鼻腔の先行制御と舌体](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L296)・[舌体の条件](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L337)・[母音の較正](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/vowelTargets.generated.json)
- 句末の韻尾が鼻音一つなら、韻尾終端を `T` として `T−0.03 s` から閉鎖と軟口蓋を追加する。最終句では主要な閉鎖軸を `T+0.10` まで強さ40で保ち、0.12秒で解放する。軟口蓋は0.45 cm²を強さ4で `T+0.25` まで保つ。次の句がある場合の保持は `min(0.10,clamp(次の拍−次の頭子音長−0.05−T,0,0.15))` 秒で、下降は0.05秒。閉鎖目標は /n/ の舌先X/Y 6.25/9.68 cm、/ŋ/ の舌背Y 8.35 cm、/m/ の唇開度 −0.25 cm。舌体や顎の副軸のロックを増やさない。これらは発話スコアとピッチの後、ビブラートの前に追加される。[句末保持](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L311)・[主要軸の抽出](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/sing.rs#L362)・[閉鎖の目標](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/phonetics/inventory.rs#L136)
- `HumanVoice::control` はジェスチャーを混合して調音器を前進させ、声道の面積・鼻のポート目標を次の内部ブロックへ渡す。体型の線形尺度を `k` とすると鼻の目標面積は `max(0,velum)k²`、実面積はブロック内の補間を経る。閉鎖は最小断面積、鼻へ回る流れは鼻端流量とポート流量（cm³/s）で測る。上流の試験は「东」の局所的な落ち込みを40 ms窓で測り、「安」の韻尾が解ける際の再上昇を監視する。候補の比較には未実装の /ʔ/ が要らない「班」「帮」を使い、狭い母音は同じ「东」を使う。[声の制御時点](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L457)・[ポート面積](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L1270)・[上流の音響試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/mandarin_rhymes.rs#L93)

## 事前登録した予測

「班」と「帮」を同じ音高・長さで生成し、舌先と舌背の閉鎖、鼻端流量、句末の保持を比べる。「英」と「东」は先行母音による舌背の条件分岐を確認する。「班，五」は次の句に備え、最終句の「班」より短く保持する。「班 ~」では2音目に韻尾が移る。閉じる韻の指定を外した構造化入力は対照にする。既定の48 kHzに加え「东」を16 kHzで合成し、音量の落ち込みと内部状態を確かめる。鼻端流量とポート面積を含め、実時間ブラウザの保存ケースをCLIで再演する。

## 第1版の反証と第2版の登録

第1版の149項目のうち14項目が外れた。固定上流・候補とも、7条件で閉鎖中の鼻端RMS比が80%を下回った。「班」で76.2%、「帮」で57.5%、「东」で65.9%だった。最小断面は0 cm²まで達し、観測上は鼻端にも流量があった。鼻端と口端のRMSは異なる放射端の振幅であり、その比から閉鎖を横切る流れは決められない。第2版では口側の閉鎖と鼻端・鼻のポートを引き続き検証し、「班」「帮」「东」の閉鎖セル両側の流量を直接測る。初回のRMS比と判定を記録した。[第1版の結果](../runs/mandarin-nasal-rhymes-20261120-a/summary.json)・[第2版ケース](../cases/mandarin-nasal-rhymes-v2.json)・[閉鎖時の枝流量の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L925)

## 実装と独立計算

拍と音素の割付け時に、韻尾がある音符と句末の保持時間を決め、既存の体型別スコア組立てで発話の調音・ピッチの後に追加する。閉鎖保持は発話と同じ主要軸・姿勢を使う。CLIの歌唱にも `tract_profile_frames` と `tract_profile_acoustics` を接続し、指定フレームで断面積・圧力・枝流量を取り出せるようにした。[歌唱のスコア](../crates/vocal-core/src/phonetics/song.rs#L354)・[鼻音化のジェスチャー](../crates/vocal-core/src/phonetics/song.rs#L490)・[CLIの観測設定](../crates/vocal-cli/src/timing_case/speech_voice.rs#L67)

計測器は拍とF0、ジェスチャーの `t0/t1`、立上がり・下降、ターゲットを独立に求めた。軟口蓋については、制御周期ごとに正弦・余弦の包絡から重みの和 `W` を求め、初期位置から重み付き目標までを `min(1,W/2)` 倍した有効目標にする。角周波数 `24π rad/s` の臨界減衰系を離散更新して実位置を求め、開いた面積をブロック内で線形補間した。この系列をCLIの有効目標・実位置・ポート面積に照合した。[韻尾の計測器](../tools/measure_mandarin_nasal_rhymes.py)・[ポートの独立計算](../tools/measure_bilabial_nasal.py#L46)

## 実測

48 kHzの8譜例と16 kHzの「东」で、第2版の152項目を通過した。固定上流との加工前PCMの最大絶対差は `4.66×10⁻¹⁰`、軟口蓋の独立計算の最大絶対差は `2.08×10⁻¹² cm²`。すべての譜例で出力ブロック長128と77のWAVとPCMのCSVがバイト一致した。「班」と「东」はChromiumのAudioWorkletでも、鼻端流量とポート面積を含む2,648点を照合した。実ブラウザ・CLIと保存ケースの再演は計169,440サンプルがビット一致した。[第2版の結果](../runs/mandarin-nasal-rhymes-20261120-b/summary.json)・[コマンドと環境](../runs/mandarin-nasal-rhymes-20261120-b/manifest.json)

| 条件 | 鼻ポートが0.01 cm²に達した先行時間（ms） | 閉鎖中の鼻端RMS比 | 採取した閉鎖フレーム数 | 閉鎖中の口端最大流量（cm³/s） |
| --- | ---: | ---: | ---: | ---: |
| 班 | 182.83 | 76.2% | 32 | 171.56 |
| 帮 | 182.83 | 57.5% | 60 | 421.10 |
| 东、48 kHz | 131.35 | 65.9% | 60 | 296.24 |
| 班、通常の鼻音の対照 | 41.21 | 76.3% | — | — |

閉鎖セルの両隣の枝流量は、抽出した3譜例・計152フレームのすべてで、固定上流・候補とも0 cm³/sだった。口端の放射流量は同じ閉鎖時点にも残った。その波形は閉鎖より先にある声道各部の応答を含む。残った口端流量のうち移動壁による押し引きの寄与を調べるには、同じ閉鎖・時刻の「帮」で、閉鎖より口端側だけの体積流量源を変えて比較する。[閉鎖断面と枝流量](../runs/mandarin-nasal-rhymes-20261120-b/summary.json)・[移動壁流量の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L834)

「班」は対照より鼻の通路が141.63 ms早く開いた。最後の音素が終わる20〜80 ms後の閉鎖率は、「班」「帮」で100%、通常鼻音の対照で0%。「班，五」では閉鎖の追加保持が100 msから70 msに短くなり、「班 ~」では韻尾と保持が2音目へ移った。「班」の終端付近の最大音量は韻尾終端50 ms前より4.18 dB低く、「帮」の鼻音部は母音の基準部より8.67 dB低かった。「东」の音量の局所的な落ち込みは48 kHzで0.0014 dB、16 kHzで0.0317 dBだった。[音量・時刻・対照](../runs/mandarin-nasal-rhymes-20261120-b/summary.json)

固定上流の2スイート12テスト、候補のワークスペース試験21件と整形・Clippyを確認した。既存の鼻音と韓国語歌唱はネイティブ回帰68項目が通過した。これまでの中国語4譜例とロシア語・韓国語の計6譜例の保存ケースをCLIで点検し、従来の計画JSONと一致した。[上流のテスト出力](../runs/mandarin-nasal-rhymes-20261120-b/artifacts/upstream-tests.log)・[既存の鼻音の回帰](../runs/lingual-nasals-20261120-nasal-rhyme-regression/summary.json)

第2版は研究ディレクトリと `/tmp` の両方で152項目を通過した。出力126件のうち、閉鎖断面の圧力・枝流量、内部状態のCSV、PCM、保存ケース、WASMを含む117件のSHA-256が一致した。ブラウザの実行時刻を含む記録に差があり、観測値とPCMの判定値は一致した。[別ディレクトリからの再実行](../runs/mandarin-nasal-rhymes-20261120-repeat/manifest.json)
