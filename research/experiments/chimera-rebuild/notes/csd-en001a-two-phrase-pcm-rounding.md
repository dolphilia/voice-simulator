# CSD en001aの先頭2句で丸め前とPCMの差を照合する

英語の歌唱 `en001a` の先頭2句について、初期姿勢、声源の設定、出力ゲインを合わせた固定上流の対照と研究版を比較する。登録済みの短い描画は48 kHzで201,600フレーム、内部96 kHzで403,200標本。先行の同設定比較の最大PCM差は1.413×10⁻¹¹だった。 [先頭2句の既存実験](../cases/csd-continuous-song.json)・[先行実行の要約](../runs/csd-continuous-song-20261121-repeat/summary.json)

## 通常の入口と観測点

上流の `render song` は `plan_song` のジェスチャーを同じ `HumanVoice` に予約する。既存の同設定対照は、同じ計画器を使い、発声を進める前に姿勢を設定して気道をその目標へ揃え、声門のドリフト、ジッター、シマーをゼロにする。研究版の `render-pcm` は `run_song` で両句の `score_with_body` を作って一度に予約する。発声器と出力段は句の境界をまたいで状態を保持する。 [上流の歌唱CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L245)・[既存の同設定対照](../tools/upstream_csd_continuous_probe.rs)・[研究版の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L270)

内部の壁・口・鼻の放射体積速度（cm³/s）の和を前標本から差分化し、放射入力（cm³/s²）を得る。49タップのFIRを使い、内部2標本ごとに出力1フレームを作る。ゲイン適用後は前回の入力とDC出力を使って高域通過を計算し、ピーク包絡と保持時間を更新してから `f32` に変換する。計装版はこの順序を保ち、内部の流量と出力段を保存する。上流の `sing_fast` と `sung_release` は無声・有声の切り替わりや次の音への解放を検査する。 [放射の合算と差分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1143)・[FIR](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[研究版の出力段](../crates/vocal-core/src/output.rs#L103)・[速い歌唱の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sing_fast.rs)・[解放の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/sung_release.rs)

## 事前に決めた条件

通常版と計装版の同設定上流を既存のmatched PCMへ照合する。研究版の通常CLIと観測CLIは現行の同じ入力で照合し、過去の歌唱PCMとの差も記録する。放射の初差は出力フレーム0に対応する内部2標本内に、PCMの最大差は初拍より前に出ると予測した。丸め前とPCMの最大差の位置は異なり、複数ULPの差の95%以上はPCM振幅10⁻⁶以下に出ると予測した。第1拍前、そこから句間まで、句間、第2拍前の準備、第2句の5区間で集計する。 [ケース定義](../cases/csd-en001a-two-phrase-pcm-rounding.json)

## 微小な履歴のゼロ化と初回判定

初回は通常版・計装版・先行実行のPCMが各版でビット一致し、独立検算だけが不合格になった。固定上流の `HumanVoice::render` は最初の内部標本と以降128標本ごとに `control` を呼ぶ。このケースでは96 kHz内部、48 kHz出力で、制御間隔は出力64フレームに相当する。最初に `AirwayNetwork::begin_block` が `flush_tiny` で放射体積速度の前回合計を検査する。同じ制御更新で `dc_x`、`dc_y`、`lim_env` も検査し、絶対値が10⁻³⁰未満の履歴はゼロにする。その後に放射の差分を計算し、FIR出力が揃った時点でゲイン、DC除去、包絡・保持カウンターを更新する。上流の `denormals` 試験は開口・閉鎖や呼気停止の後に非正規化数が残らないことを検査する。 [上流の標本時計](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L382)・[制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L506)・[気道履歴のゼロ化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L756)・[上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/denormals.rs)

初回の検算はこの更新を含んでいなかった。内部標本62,720では、直前の放射合計 −6.620×10⁻³¹ cm³/s を引くと 6.356×10⁻²⁶ cm³/s² になるが、観測値は0だった。観測した放射をそのままFIRへ渡しても、出力フレーム30,592ではDCの前入力9.494×10⁻³¹がゼロ化されるため差が出た。このDC履歴の処理を外した検算では、DC出力81,280フレームとPCM 15,830フレームが固定上流の観測から外れた。独立計算に上流の閾値と更新順を反映し、合否基準と計装を保ったまま初回の観測を再検算した。 [初回の不合格結果](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-registered/summary.json)・[独立計算](../tools/measure_csd_en001a_two_phrase_pcm_rounding.py)

## 実測

201,600出力フレームと403,200内部標本を、両版それぞれの観測に対して独立計算とビット照合した。最大包絡は両版とも約0.6163で、リミッターは作動しなかった。放射の初差は内部標本0の口の体積速度に現れた。その時点で声門の位相・面積・流量と壁・鼻の放射は一致した。続いて壁の放射が内部標本1、声門前後の差圧が5、声門流量が6で分かれた。 [内部系列と出力段の照合](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/summary.json)

| 比較区間（出力フレーム） | 変換前のRMS差 | PCMのRMS差 |
| --- | ---: | ---: |
| 初拍前 [0, 115200) | 1.113×10⁻¹³ | 1.118×10⁻¹³ |
| 初拍から句間まで [115200, 135600) | 8.732×10⁻¹⁵ | 5.094×10⁻¹⁴ |
| 句間 [135600, 137760) | 1.524×10⁻¹⁴ | 0 |
| 第2句の準備 [137760, 143102) | 2.983×10⁻¹⁵ | 0 |
| 第2句 [143102, 201600) | 8.931×10⁻¹⁵ | 3.793×10⁻¹⁵ |
| 全区間 [0, 201600) | 8.435×10⁻¹⁴ | 8.605×10⁻¹⁴ |

全区間での最大絶対差は変換前が1.4132619365×10⁻¹¹、PCMが1.4132619103×10⁻¹¹で、双方とも初拍前の出力フレーム20,363に現れた。最大差の位置は異なるという仮説は不成立だった。PCMの1 ULP差は993フレームで、全例で変換前の2値が丸めの中点をまたいだ。複数ULPの101,441フレームは全件で振幅10⁻⁶以下だった。このうち振幅が最も大きい箇所でも6.045×10⁻⁸だった。 [仮説の判定とフレーム別の数値](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/summary.json)

## 再現と次の切り分け

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4を使った。上流は `sing_fast`、`sung_release`、`denormals`、研究版は `uniform_tube` を実行した。ビルド、観測と圧縮出力には作業用のRTL9210B-CGを使い、実行コマンド・環境・ソースのハッシュはマニフェストに記録した。 [修正後のマニフェスト](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-corrected/manifest.json)・[再実行のマニフェスト](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/manifest.json)

隔離してビルドした修正後の2実行は各4判定に通過し、要約と6出力がバイト一致した。6出力は内部・出力系列、PCMハッシュ、上流と研究版の観測差分、両版の歌唱計画で、初回とも一致した。 [上流の試験結果](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/artifacts/upper-tests.log)・[研究版の試験結果](../runs/csd-en001a-two-phrase-pcm-rounding-20261124-repeat/artifacts/research-tests.log)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_csd_en001a_two_phrase_pcm_rounding.py csd-en001a-two-phrase-pcm-rounding-new
```

次は同設定の先頭2内部標本で、最初の制御更新前後の唇端面積、終端の圧力、放射負荷と流量を照合する。固定上流と研究版で最初に分かれた入力を特定し、その値だけを入れ替える対照で、内部標本0の口の流量がどの程度再現されるかを確かめる。 [同じ姿勢条件の観測入口](../tools/upstream_csd_continuous_probe.rs)・[唇の終端負荷を検算した先行ケース](../cases/tsp-fk61-pcm2937-terminal-load.json)
