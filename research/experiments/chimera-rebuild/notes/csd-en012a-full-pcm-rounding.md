# CSDの調整曲 en012a の全曲を確認曲2曲と照合する

`en012a` は長音の事前選定で登録した調整曲。前回の長音測定の録音長、185音符、46句をそのまま使う。`en005a` と `en035a` の両確認曲では第1拍前の20,363フレームに丸め前の最大差があり、PCMの最大差は譜面区間にあった。今回も第1拍前・譜面区間・終端以降を分け、同じ版どうしで共有する冒頭PCMがその地点を含むか調べる。 [今回の事前登録](../cases/csd-en012a-full-pcm-rounding.json)・[長音での選定と既存の実行](csd-long-note-vibrato.md#注釈による選定)

## 描画の入口と観測点

固定上流の `compare_song` は録音の長さを確定し、`render_notes` で音符の音高、開始と終了の秒を読んで句ごとに `plan_song` を呼ぶ。60 BPMの指定では、音符間隔の秒がそのまま拍数になる。句から生成した全ジェスチャーを一つの `HumanVoice` の時刻に登録する。今回の計測器はこの順で通常設定を再描画し、固定上流の公式CLIで保存済みの全曲PCMに照合する。同設定の比較では、研究用プローブで初期姿勢、声源の変動、息成分と出力ゲインを揃える。研究版は通常の `vocal-cli render-pcm` と `inspect` を使う。上流のテストは速い句でも母音開始が拍に合うことと、句末母音が放される時刻を確認する。 [固定上流の曲比較](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L829)・[句の予約](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare.rs#L259)・[同設定のプローブ](../tools/upstream_csd_continuous_probe.rs#L61)・[拍の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs#L29)・[母音の放し方の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs#L48)

内部標本は96 kHz。壁、口、鼻の放射体積速度（cm³/s）の合計を1時刻前から差分し、時刻幅で割った値（cm³/s²）をFIRに渡す。FIRの和は最古の入力から順に加え、2標本ごとに48 kHzの出力を出す。その後にゲイン、DC除去、ピーク包絡の更新を行う。前回の包絡を越えた絶対振幅は包絡を更新し、保持標本数を揃える。包絡が0.75を超えると、利得抑制を掛けてからfloat32へ丸める。上流の制御境界での微小履歴のゼロ化も独立計算に含める。 [固定上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[FIRの加算順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[研究版の出力段](../crates/vocal-core/src/output.rs#L107)・[微小履歴の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs#L68)

## 全曲の測定結果

上流の通常出力は公式CLIの保存波形と、研究版の通常出力は保存波形・ジェスチャー計画とそれぞれ一致した。同設定で観測を加えた両版も、観測を加える前の計画とPCMを再現した。放射体積速度の合算・差分の13,226,668内部標本と、FIR以降の6,613,334出力フレームを各版で独立に再計算し、float32のPCMが全フレームで一致した。

| 区間（0起点・終端を含まない） | 丸め前の最大絶対差（フレーム） | PCM最大絶対差（フレーム） | PCM差が1 ULPの数 | PCM差が複数ULPの数 | 利得抑制の作動数（各版） |
| --- | ---: | ---: | ---: | ---: | ---: |
| 第1拍前 [0, 80,002) | 1.413×10⁻¹¹（20,363） | 5.821×10⁻¹¹（78,963） | 989 | 66,241 | 0 |
| 譜面区間 [80,002, 6,503,328) | 1.961×10⁻¹³（2,879,999） | 7.451×10⁻⁹（1,449,218） | 22,828 | 137,809 | 3,216,415 |
| 譜面終端以降 [6,503,328, 6,613,334) | 4.920×10⁻¹⁴（6,582,028） | 7.276×10⁻¹²（6,507,152） | 1,668 | 59,389 | 0 |

観測項目の初差は内部標本0の口端流量にあり、同じ標本で放射の合計とその時間差分も分かれた。壁は標本1、声門流量は標本6、鼻は標本305,430から分かれた。全曲のPCM最大差は第14句の30.192秒にあった。丸め前には7.952×10⁻¹⁵離れた両版の値がfloat32の中点の両側に位置し、変換後は1 ULP離れた。そのフレームは全曲PCMの二乗誤差の38.25%を占めた。除外するとRMS差は4.685×10⁻¹²から3.681×10⁻¹²に下がった。複数ULP差は263,439フレームで、全て両版のPCM絶対値が10⁻⁶以下だった。該当する最大振幅は4.420×10⁻⁷。利得抑制の作動フレームは両版で一致し、作動中にPCMが分かれたのは24フレームだった。事前登録した5つの予測はすべて成立した。 [採取と集計](../runs/csd-en012a-full-pcm-rounding-20261124-registered/summary.json)

最大PCM差のフレームでは両版ともピーク包絡が約1.058で、利得抑制が作動していた。上流ではDC除去後の値−0.0955121909642に抑制を掛け、その後の−0.06773752346634をfloat32へ変換した。最大差の検証には丸め前の値と一緒に包絡と丸め中点を保存すると、利得抑制後のどの値を比較したかを追える。 [出力状態の採取](../runs/csd-en012a-full-pcm-rounding-20261124-registered/artifacts/output-trace.npz)・[丸めの観測点](../runs/csd-en012a-full-pcm-rounding-20261124-registered/summary.json)

固定上流、研究版それぞれで `en012a` は確認曲2曲と最初の76,672 PCMフレーム（1.597秒）を共有した。丸め前の最大差が出た20,363フレームはこの範囲内にある。全曲のPCM最大差はいずれも譜面区間の1 ULPだった。

| 曲 | PCM最大絶対差 | 句 | 利得抑制が作動したフレーム数（各版） |
| --- | ---: | --- | ---: |
| en012a | 7.451×10⁻⁹ | 第14句 | 3,216,415 |
| en005a | 1.490×10⁻⁸ | 第36句 | 1,103,539 |
| en035a | 2.980×10⁻⁸ | 第18句 | 618,105 |

次は先頭2句で採取済みの調整曲 `en001a` を、保存済みの全50句・3,110,400フレームに拡張する。全曲の丸め前最大差が冒頭に残るか、PCM最大差が譜面区間に移るかを測る。 [en001aの先頭2句の観測](csd-en001a-two-phrase-pcm-rounding.md)・[録音長と全曲の設定](../runs/csd-acoustic-f0-en001a-20261121-final/artifacts/candidate-case.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。事前登録のSHA-256は `287d980a67c3059303f53badc159c56a9f52d2b54695d3c0d8eb3dbf8fdbc3e2`。長さの比から、`en035a` の約1.9 GiBの圧縮観測に対して今回は約2.2 GiBと見積もった。圧縮前の放射系列、一時CSV、描画用ビルドを含む見積もりは1回あたり14 GiB。開始時に空き336 GiBを確認したRTL9210B-CGに直接保存した。`en035a` と同じ描画・独立計算のCLIに今回のケースを渡し、確認曲2件の要約とPCMを参照して区間別の比較を記録した。上流の歌唱と微小履歴の16試験と研究版の一様管3試験が通過した。 [計測CLI](../tools/measure_csd_en035a_full_pcm_rounding.py)・[初回のマニフェスト](../runs/csd-en012a-full-pcm-rounding-20261124-registered/manifest.json)

研究ワークスペースと `/tmp` からの両実行で各7判定が通過した。圧縮観測は1実行あたり2,413,177,457バイトだった。観測、PCMハッシュ、両版の観測パッチと譜面計画、要約の7出力は同じSHA-256を示した。 [別ディレクトリからの再実行](../runs/csd-en012a-full-pcm-rounding-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=15032385536 \
  ../../.venv/bin/python tools/measure_csd_en035a_full_pcm_rounding.py csd-en012a-full-pcm-new \
  --case cases/csd-en012a-full-pcm-rounding.json
```
