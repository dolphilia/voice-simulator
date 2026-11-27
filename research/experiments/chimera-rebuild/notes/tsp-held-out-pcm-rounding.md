# 確認用12発話で丸め前とPCMの誤差順位を照合する

同文のFK61_02とMK61_02では、変換前のRMS差とPCMのRMS差の大きい条件が逆になった。既存の確認用セットでは、同じ6文を女性・男性の各発話設定で描画している。固定した12ケースを同じ通常経路から描画し、発話ごとの誤差順位、最大差の位置、振幅別ULP数を比較する。 [同文の先行計測](tsp-mk61-02-full-pcm-rounding.md)・[確認用ケースの登録](../cases/tsp-held-out-matched-speech.json)

## 通常レンダーと観測

固定上流の `render text` が `say` で文章を発話計画に変換し、体型の基準F0と調音を使って描画する。研究版の `render-pcm` も確認用に保存した体型・発話端の調音・ゲインを読む。両版で、内部96 kHzの壁・口・鼻の放射体積速度（cm³/s）を合計し、前標本との差から cm³/s² の入力を得る。49タップのFIRと2対1の間引き後にゲインを適用し、DC除去の状態と包絡を更新する。リミッターが作動しない場合、DC除去後の値が `f32` へ丸められる。独立計算は各発話の冒頭から行う。 [上流の発話CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[放射の合算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1143)・[FIR](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63)・[上流の出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L397)・[研究版の出力](../crates/vocal-core/src/output.rs#L103)

各版で通常CLIと観測器を一度ずつビルドして全発話に使う。上流のエンジン試験はレート変更時の発声の有限性とRMSを、研究版の一様管試験は壁放射を変えたときの伝搬の状態を確認する。検算に使う全区間の声門流量と放射、出力段、PCMを発話単位で圧縮し、RTL9210B-CGに保存する。 [上流の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L104)・[研究版の試験](../crates/vocal-core/tests/uniform_tube.rs#L32)

## 事前に決めた条件

全1,487,586フレームを保存済みPCMと照合する。変換前とPCMのRMS差の順位が逆になる発話対があり、同文の男女も少なくとも1対が逆転すると予測した。同率は平均順位に置く。変換前とPCMの最大差が別のフレームに現れるのは9発話以上、PCM振幅10⁻⁶以下の複数ULP差は発話を合算した件数で95%以上と予測した。前2回の個別観測FK61_02・MK61_02は、集計の再現性を検証するためにも使う。 [ケース定義](../cases/tsp-held-out-pcm-rounding.json)

## 実測

全12発話で、両版の通常CLIと観測版が保存済みPCMとビット一致した。既存の初差、最大差、差のあるフレーム数を再現し、内部2,975,172標本の放射から全出力を再計算できた。リミッターは全発話で非作動だった。変換前の最大差が出たフレームのPCMは全12発話で一致し、PCM最大差は別のフレームに現れた。 [各発話の測定と照合](../runs/tsp-held-out-pcm-rounding-20261124-corrected/summary.json)

| 発話 | 変換前RMS差 | PCM RMS差 | 変換前の順位 | PCMの順位 |
| --- | ---: | ---: | ---: | ---: |
| MK64_09 | 1.498×10⁻¹⁴ | 1.536×10⁻¹² | 1 | 4 |
| MK61_02 | 1.293×10⁻¹⁴ | 6.136×10⁻¹³ | 2 | 6 |
| MK61_01 | 1.263×10⁻¹⁴ | 9.674×10⁻¹⁴ | 3 | 9 |
| MK64_08 | 1.214×10⁻¹⁴ | 4.505×10⁻¹⁴ | 4 | 11 |
| MK62_02 | 1.181×10⁻¹⁴ | 9.822×10⁻¹⁴ | 5 | 8 |
| MK62_04 | 1.089×10⁻¹⁴ | 1.274×10⁻¹² | 6 | 5 |
| FK64_09 | 9.321×10⁻¹⁵ | 3.071×10⁻¹² | 7 | 3 |
| FK61_01 | 8.830×10⁻¹⁵ | 5.479×10⁻¹² | 8 | 1 |
| FK61_02 | 8.156×10⁻¹⁵ | 4.896×10⁻¹² | 9 | 2 |
| FK64_08 | 7.399×10⁻¹⁵ | 3.581×10⁻¹³ | 10 | 7 |
| FK62_02 | 7.208×10⁻¹⁵ | 4.523×10⁻¹⁴ | 11 | 10 |
| FK62_04 | 7.149×10⁻¹⁵ | 2.160×10⁻¹⁴ | 12 | 12 |

RMS差の順位は66発話対中30対で逆転し、Spearmanの順位相関は0.147だった。最大絶対差の順位相関は−0.296で、36対が逆転し、4対は片方の指標で同率だった。同文の男女6対はすべて男性設定で変換前のRMS差が大きく、PCMのRMS差では6対中4対で大小が逆転した。

複数ULP差の4,582フレームは全件でPCM振幅10⁻⁶以下だった。境界より大きい1,410,387フレームのうち差のある715フレームはすべて1 ULPだった。事後集計では、各発話でPCM差が最大の1フレームにその差の二乗和の69.29〜99.999%が集中していた。この1フレームを各発話から除いてPCMのRMS差を再計算すると、変換前のRMS差との順位相関は0.294になった。 [順位と振幅別ULP数](../runs/tsp-held-out-pcm-rounding-20261124-corrected/summary.json)

次はCSDの `en001a` の先頭2句で、初期姿勢・声源・ゲインを揃えた上流の対照と研究版に同じ出力段の計測を適用する。歌唱の句間を含めて、丸め前の最大差とPCMの最大差が現れる時刻を照合する。 [CSDの同設定対照のケース](../cases/csd-continuous-song.json)

## 初回の照合と再実行

初回は通常CLI、観測版、保存済みPCMが全発話で一致した。個別記録との照合では、MK61_02に追加で保存された男女比較の仮説まで、各発話に共通する仮説と同じ辞書として比較し、不合格になった。共通する仮説と観測結果を照合し、男女のRMS比と最大差の比は今回のFK61_02・MK61_02から独立に再計算するよう修正した。初回データの再計算でも個別2発話の照合に通り、12発話の測定値と順位は初回と一致した。 [初回のマニフェスト](../runs/tsp-held-out-pcm-rounding-20261124-registered/manifest.json)・[初回の結果](../runs/tsp-held-out-pcm-rounding-20261124-registered/summary.json)

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使用した。上流のエンジン試験6件、研究版の一様管試験3件に通過した。採取と一時ビルドにはRTL9210B-CGを使用した。

修正後の実行を研究ワークスペースと `/tmp` から行い、各6判定に通過した。観測系列、PCMのハッシュ記録、要約の25出力が両方でバイト一致した。このうち観測系列とPCMのハッシュ記録の24出力は初回とも一致した。 [修正後のマニフェスト](../runs/tsp-held-out-pcm-rounding-20261124-corrected/manifest.json)・[再実行のマニフェスト](../runs/tsp-held-out-pcm-rounding-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_held_out_pcm_rounding.py tsp-held-out-pcm-rounding-new
```
