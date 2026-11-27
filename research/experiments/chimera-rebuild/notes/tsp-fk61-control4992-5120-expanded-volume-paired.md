# FK61_01の両版で体積差の展開式を試す

前の計測では、節点29・34の面積補間を上流と研究版の双方で直接式に揃えると、平滑後の体積速度のRMS差が約50分の1になった。平滑前では、幾何から厳密に求めた版間差を引いても1.151×10⁻¹¹ cm³/sのRMS残差があった。同じ版を対照にし、同じ2節点で体積差の演算だけを切り替える。 [前回の計測](tsp-fk61-control4992-5120-indexed-area-paired.md#実測)

## 通常入口から体積源まで

上流は `render text` の `text` で英語の発話計画を描画し、`HumanVoice::render` の内部標本ごとに気道を進める。`AirwayNetwork::begin_block` は制御目標までの面積・長さの増分を決める。`AirwayNetwork::step` は面積・最小面積・長さを更新し、前の体積 `vol[k]` と新体積の差を計算する。研究版は `render-pcm` で同じ発話を描画し、`AirwayNetwork::step_with_prescribed_flow` から `MovingAreas::step` を呼ぶ。節点の面積には体積計算用の下限を適用し、前後の体積は cm³、体積速度は cm³/s で保持する。上流は差に時間刻みの逆数を掛け、研究版は時間刻みで割る。 [上流CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L225)・[上流の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の気道更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827)・[研究版の描画](../crates/vocal-cli/src/main.rs#L452)・[研究版の体積源](../crates/vocal-core/src/airway/network/geometry.rs#L110)

体積用の下限を適用した断面積を `A`、長さを `d` とし、旧面積と旧長を上書き前に読む。通常式の体積差は `(A_old*d_old) − (A_new*d_new)`、展開式は `(A_old−A_new)*d_old + A_new*(d_old−d_new)`。どちらも圧縮時の流量が正になる。展開式でも通常の体積を状態に保存する。最小断面積が閾値を下回るセルの流量配分、節点ごとの二段平滑、枝と壁の流量、節点圧、口と鼻と壁の放射、FIRとDC除去は従来の経路を通る。上流の密閉腔試験は圧縮後の圧力を断熱則と照合し、研究版の補間試験は声門ポートを更新する間も他セルの補間が進むことを確かめる。 [上流の圧縮試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)・[1標本での先行計測](tsp-fk61-node40-expanded-volume.md)

## 事前に決めた条件

節点29・34の4992〜5119と5120〜5247で、各版の体積速度と有理数の参照値のRMS誤差、版間差に残る演算残差のRMSがいずれも100分の1以下になると予測した。PCMの初差は2937に残ると予測した。観測するのは局所の4990〜5875、放射と出力段の冒頭3,072フレーム、全発話の口端とPCM。標本番号は0始まり。ケース定義を計測前に固定した。 [ケース定義](../cases/tsp-fk61-control4992-5120-expanded-volume-paired.json)

## 実測

対象512標本で、有理数で計算した各版の体積速度に対するRMS誤差は、上流で8.819×10⁻¹²から7.213×10⁻¹⁷ cm³/s、研究版で8.581×10⁻¹²から7.697×10⁻¹⁷ cm³/sに減った。両版の差から幾何に由来する差を引いたRMS残差は1.151×10⁻¹¹から1.039×10⁻¹⁶ cm³/sになった。丸めを除いても幾何だけで1.670×10⁻¹¹ cm³/sの差があり、展開式で観測された平滑前の差の大きさと一致した。平滑後のRMS差は3.315×10⁻¹⁴から3.361×10⁻¹⁴ cm³/sへ上がった。

| 上流／研究版 | 平滑前のRMS差（cm³/s） | 演算残差のRMS（cm³/s） | 全PCMの最大絶対差 | 全PCMのRMS差 | 差のあるフレーム |
| --- | ---: | ---: | ---: | ---: | ---: |
| 通常／通常 | 2.146×10⁻¹¹ | 1.151×10⁻¹¹ | 1.863×10⁻⁹ | 5.469×10⁻¹² | 2,355 |
| 通常／展開 | 1.951×10⁻¹¹ | 8.819×10⁻¹² | 1.863×10⁻⁹ | 5.469×10⁻¹² | 2,355 |
| 展開／通常 | 1.944×10⁻¹¹ | 8.581×10⁻¹² | 1.164×10⁻¹⁰ | 3.430×10⁻¹³ | 2,351 |
| 展開／展開 | 1.670×10⁻¹¹ | 1.039×10⁻¹⁶ | 1.164×10⁻¹⁰ | 3.424×10⁻¹³ | 2,351 |

各版で最初に変わったのは4992の節点29の体積速度と二段平滑の状態。節点圧の初差は上流4994の節点34、研究版4992の節点29。口端流量と放射の初差は、上流で5009、研究版で5006だった。4通りの版間比較では、口端の初差は3971、PCMの初差は2937だった。2937の `f32` 変換前の版間差は1.509×10⁻¹⁴から1.516×10⁻¹⁴になり、丸めの境界をまたいだままだった。 [全4条件と経路ごとの初差](../runs/tsp-fk61-control4992-5120-expanded-volume-paired-20261123-registered/summary.json)

計測後に全PCMを調べると、通常式どうしの差の二乗和の99.90%がフレーム16682の1標本に集中していた。上流だけを展開式にした場合も、この標本は研究版と一致した。16682を除くRMS差は通常式どうしで1.749×10⁻¹³、展開式どうしで3.424×10⁻¹³。16682の2つの `f32` 値の中点は0.01834604237228632。今回保存した出力段はフレーム3071までなので、16682で境界を跨ぐ直前の値や、口・壁・鼻から各々どれだけ寄与したかの照合は残る。次の比較では冒頭から16682までの放射と出力段を再計算し、リミッターの作動を確認した上で `f32` に渡す値を測る。 [全PCMの格納先](../runs/tsp-fk61-control4992-5120-expanded-volume-paired-20261123-registered/manifest.json)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。通常CLIと観測版の116,132フレームをビット照合した。両版の面積と長さ、前後の体積、補間の記録、処置前の口端・放射・PCMは各版の対照と一致し、局所の流量・圧力と出力段も独立計算に一致した。対照を展開式の観測として入力する試行では、展開式と局所更新の2判定が計画どおり不合格になった。

各実行で上流の気道試験9件と研究版の補間試験1件、計測の5判定に通過した。採取、隔離パッチ、全発話PCMと要約の計27出力は2実行でバイト一致した。大容量出力と一時ビルドはRTL9210B-CGに置いた。 [初回のマニフェスト](../runs/tsp-fk61-control4992-5120-expanded-volume-paired-20261123-registered/manifest.json)・[再実行のマニフェスト](../runs/tsp-fk61-control4992-5120-expanded-volume-paired-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_control4992_5120_expanded_volume_paired.py tsp-fk61-control4992-5120-expanded-volume-paired-new
```
