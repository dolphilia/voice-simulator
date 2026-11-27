# 固定 /i/ の壁・口端・鼻端の放射をPCMまで分解する

前回と同じ固定 /i/、肺圧3.6 cmH₂O、110 Hzの3条件を描画した。無変更、口腔2枝の平滑化、平滑化を保った声門入力圧力差の置換を比較する。圧力差の置換では声門面積を無変更の動きに揃え、気道の流量・圧力を更新する。切替は内部標本38,400で、96 kHzの全65,536標本と48 kHzの全32,768 PCMフレームを照合する。 [事前登録](../cases/fixed-vowel-i-radiation-components.json)・[圧力差を置換した前回の比較](fixed-vowel-i-pressure-replay.md)

## 放射体積流量の更新

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は、声門面積を設定してから `AirwayNetwork::step` を呼ぶ。枝流量の更新に続き、各節点の壁は旧圧力を受けて速度と変位を更新する。壁面積に速度を掛けた体積流量 `U_wall,node`（cm³/s）は節点の収支から引かれ、放射係数を掛けた値が壁成分として加算される。固定上流の咽頭と口腔の放射係数は0.25。次に節点圧と並列の慣性・抵抗負荷で口端と鼻端の流量を進める。壁の合計、口端、鼻端の順に足し、前標本の総流量との差に96,000 Hzを掛けて出力段へ渡す。研究版もCLIの `render-pcm` から同じ順序で気道を進め、流量差を時間刻みで割って微分する。 [通常発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[壁の係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L120)・[上流の壁と放射負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[研究版の壁と放射負荷](../crates/vocal-core/src/airway/network.rs#L747)

隔離ビルドで、上流の壁加算値と微分直前の総流量を記録した。研究版では既存の `NetworkSample` の壁加算値と総放射流量を採取した。口端・鼻端はそれぞれの放射負荷の流量を読む。上流のテストでは壁付き・壁なしの一様管でインパルス応答と周波数モデルを照合する。以前の停止区間の計測では壁ごとの質量・抵抗・剛性と各放射量も照合済み。 [時間領域と周波数領域の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)・[以前の壁と放射の収支](../tools/measure_fixed_voice_radiation_balance.py#L149)・[今回の計測コード](../tools/measure_fixed_vowel_i_radiation_components.py)

## 予測と比較方法

前回保存した総放射微分から口端・鼻端の微分を差し引くと、壁が先に変化すると予測できた。各成分を以前と同じFIR・間引き・ゲイン・直流除去へ通すと、窓全体では口端成分が全PCM差の方向への射影の約88〜96%を占め、最初に32ビットPCMで差が残るフレームは口端成分だけでも同じになると予測した。直接採取した流量を使って、この差し引きによる推定を確かめる。出力段の包絡リミッターが関与しないことを確認してから、加算前の成分に線形な出力処理を適用する。32ビットへの丸めは、各成分の差を丸め前の基準波形に足した後で行う。 [研究版の出力段](../crates/vocal-core/src/output.rs#L101)・[前回の観測の所在](../runs/fixed-vowel-i-pressure-replay-20261124-repeat/manifest.json)

## 実測

通常の平滑化では壁の放射微分が切替1標本後に変わり、口端は12標本後だった。声門面積を固定しても同じ時刻で変わった。通常の平滑化と面積を固定した平滑化の差では、壁が29標本後、口端が65標本後に変化した。鼻端流量の差は全比較で0。32ビットへ丸める前は壁成分が先行し、丸め後の最初の差は3比較すべてで口端成分だけの計算と同じフレームだった。 [各観測点と最初の差](../runs/fixed-vowel-i-radiation-components-20261124-registered/summary.json)

| 比較 | 壁の最初の放射差（内部標本） | 口端の最初の放射差（内部標本） | 全体と口端だけで最初に変わるPCMフレーム | 窓全体の口端／壁の射影 |
| --- | ---: | ---: | ---: | ---: |
| 通常の平滑化 − 無変更 | 38,401 | 38,412 | 19,210 | 95.73%／4.27% |
| 面積固定の平滑化 − 無変更 | 38,401 | 38,412 | 19,210 | 96.24%／3.76% |
| 通常の平滑化 − 面積固定の平滑化 | 38,429 | 38,465 | 19,325 | 88.18%／11.82% |

射影は各成分のPCM差と全成分のPCM差の内積を、全成分のエネルギーで割った値。通常の平滑化で最初に全PCM差が出たフレーム19,210では、丸め前の口端の変化は−1.047×10⁻¹⁰、壁は+4.433×10⁻¹²だった。壁成分だけを丸め前の基準に足した場合のPCM差は19,212から始まった。面積を介する比較では、壁成分だけの最初のPCM差は19,365だった。 [成分別の数値](../runs/fixed-vowel-i-radiation-components-20261124-registered/summary.json)

6描画すべてで、合算流量とその微分は実装の観測値とビット一致。版間の成分別流量の誤差は相対5.78×10⁻¹⁵以内。成分を加算して出力段を再計算した絶対誤差は8.49×10⁻¹⁶以内で、成分ごとの差を合算したときの絶対誤差は1.26×10⁻¹⁵以内だった。出力段のピークは0.066未満でリミッターは動作せず、独立計算の総出力を32ビットへ丸めると保存PCMに一致した。今回の観測追加後も前回の気道状態、圧力入力、PCMは全標本でビット一致した。 [観測のマニフェスト](../runs/fixed-vowel-i-radiation-components-20261124-registered/manifest.json)

次は通常の固定発声CLIの任意の観測項目として、壁・口端・鼻端と合算流量を追加する。無変更の固定 /i/ を最小ケースにして、隔離ビルドの流量、出力クロック、PCMと照合する。 [通常の固定発声CLI](../crates/vocal-cli/src/geometry_case/voice.rs#L157)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4の研究ワークスペースから実行した。再実行は `/tmp` からPythonとスクリプトを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_radiation_components.py fixed-vowel-i-radiation-components-20261124-registered
```

両実行で54判定と固定上流の一様管・狭窄・肺ポートの試験に通過した。要約と10成果はバイト一致し、RTL9210B-CG上で10成果の実体を共有した。前回の圧力置換、7.2・3.6 cmH₂Oの平滑化も、保存観測を現在のスクリプトで再集計して従来要約と一致した。 [初回のマニフェスト](../runs/fixed-vowel-i-radiation-components-20261124-registered/manifest.json)・[再実行のマニフェスト](../runs/fixed-vowel-i-radiation-components-20261124-repeat/manifest.json)

第31版の全体監査で成分別の放射、微分、PCMの照合を保存観測から再計算し、第30版と独立した2実行の成果を照合した。184実行・3,000成果・387判定に通過した。 [第31版の全体監査](../runs/plan-completion-v31-fixed-vowel-i-radiation-components-20261124/manifest.json)
