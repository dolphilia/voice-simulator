# 混合体型のピーク制限とゲインの適用位置

混合体型の休止舌先と音源変動0の歌唱では、基準ゲインで包絡の最大値が0.67757178だった。同じ放射波形を1.2倍すると、基準ゲインの包絡だけがしきい値0.75を超え、体型係数0.875を先に掛けた場合は下回ると予測した。波形を1.2倍する試験用の係数と、適用位置を変える体型係数0.875は別々に扱う。[事前登録](../cases/duet-mixed-limiter-gain-order.json)・[元の出力計測](duet-mixed-output-gain.md#実測)

## 読解と予測

- 固定上流の `HumanVoice::render` は気道計算が返す放射流量の時間微分（cm³/s²）をFIRに入れ、96 kHzから48 kHzへ間引く。FIRの出力にゲインを掛け、25 HzのDC除去を通した無次元の信号を `y[n]` とする。ゲインの前までのFIRと、その後のDC除去は線形なので、一定の1.2倍はどちらの入力位置でも同じ効果になる。計測では保存放射を1.2倍した系列をFIRに直接入れる経路と、通常レンダーのゲインに1.2を掛けて同じ効果を得る経路を照合する。上流の `output_does_not_depend_on_the_host_block_size` は同じイベントを保ってブロック分割を変えた場合にPCMビットが一致するかを確認する。混合体型は固定上流の観測器から渡し、レンダー本体の `output_gain` だけを対照用に設定する。[上流のレンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[間引き](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L55)・[上流のブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[固定上流の観測器](../tools/upstream_duet_child_noise_probe.rs)
- リミッターは `|y[n]|` が現在の包絡 `E` 以上なら包絡をその値に更新し、保持残数を1,200フレーム（25 ms）に戻す。小さな入力では保持残数を減らし、それが尽きた後は `exp(−1/(48000×0.2))` を1フレームごとに掛けて解放する。更新した包絡が0.75を上回る間は `0.75/E[n]` で減衰し、さらに0.85を超える値は `tanh` で圧縮し、最後に `f32` に丸める。保持・解放中は現在の `|y[n]|` が0.75未満でも減衰が続き得る。[上流の制限処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L399)・[研究版の出力段](../crates/vocal-core/src/output.rs#L103)
- 今回は1.2倍で基準条件の包絡が約0.81309まで上がる一方、体型係数を先に掛ける場合には約0.71145に収まると見込んだ。基準条件のピークを0.75に制限したPCMを後から0.875倍するとピークは0.65625になる。ソフトクリップが発動しないとき、体型係数 `q=0.875` の適用位置による差は、丸めの前では `q y[n] (1 − 0.75 / max(E[n], 0.75))`。`E[n]` が0.75以下なら差は0、0.75超なら、同じ包絡でも現在の入力に応じて正負と大きさが変わる。差の最大値は約0.05520と予測した。[既存の出力段の比較](pcm-output.md)

## 再現

先行実行で採取した放射を1.2倍し、両ゲイン条件の共通入力として保存する。上流の間引き器を使う既存の再生観測器、研究版の通常CLIと観測器、固定上流の歌唱レンダーを全97,920出力フレームで照合する。独立計算は `firwin` の係数による直接畳み込み、`lfilter`、保持期限を絶対フレーム番号で管理する包絡計算を使う。通常CLIは128、77フレームのブロック分割で試す。放射と出力の採取物はRTL9210B-CGへ直接保存する。[測定CLI](../tools/measure_duet_mixed_limiter_gain_order.py)・[保存放射の再生観測器](../tools/upstream_pcm_probe.rs)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_mixed_limiter_gain_order.py duet-mixed-limiter-gain-order-new
```

## 実測

基準ゲインの包絡は最大0.813086、体型係数を先に掛けた条件は0.711450だった。基準条件のPCM最大振幅は0.750000に制限された。体型係数を制限前に掛けたPCMのピークは0.711450、制限後に掛けたときは0.656250。両者の最大絶対差は47,713フレーム目で0.05520034だった。ソフトクリップはすべての条件で0フレーム。計算式から求めた適用位置の差と実測PCMの差は全区間で `5.37×10⁻⁸` 以内に収まった。[比較結果](../runs/duet-mixed-limiter-gain-order-20261122-a/summary.json)

基準ゲインの包絡が0.75を超えたのは34,695〜36,298、40,849〜44,219、47,710〜49,688フレームの計6,954フレームだった。係数の適用位置による差がFloat32の丸め用許容差 `6×10⁻⁸` を初めて超えたのは34,695フレーム目で、制限区間外では一度も超えなかった。基準条件の瞬時振幅が0.75以下でも、包絡を保持している4,935フレームと、解放で減衰している1,900フレームに差が残った。各区間の最大差は保持中0.050815、解放中0.047571だった。[包絡・保持残数・PCMの時系列](../runs/duet-mixed-limiter-gain-order-20261122-a/artifacts/candidate-base-output.f64le)

研究版の通常CLIは128・77のブロック分割でPCMがビット一致した。研究版の観測器、保存放射を再生した上流の間引き器と出力式、独立した出力計算も両ゲイン条件でPCMがビット一致した。固定上流の歌唱レンダーは放射の段で最大 `5.11×10⁻⁷ cm³/s²` の差があり、PCM差は最大 `7.28×10⁻¹²` だった。包絡・保持残数を介した制限の発動フレーム数はすべての経路で一致した。今回の対照は放射を倍率で変えたもので、発声機構自体を強く駆動したときの空気音や聴感は未測定。[固定上流の段別時系列](../runs/duet-mixed-limiter-gain-order-20261122-a/artifacts/upstream-base-output.f64le)・[同一放射の再生](../runs/duet-mixed-limiter-gain-order-20261122-a/artifacts/replay/base-pcm.csv)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。研究ワークスペースと `/private/tmp` から各9判定と5予測、固定上流10試験が通過し、28出力がバイト一致した。標準ライブラリでも保存した放射の倍率、包絡の保持・解放、Float32への丸め、ピークと発動フレーム数を照合した。通常レベルの混合体型の回帰は10判定と固定上流10試験を通過し、先行の25出力が一致した。3実行の435入力・105出力をサイズとSHA-256で照合し、採取物127,549,986バイトをRTL9210B-CGに保存した。[初回](../runs/duet-mixed-limiter-gain-order-20261122-a/manifest.json)・[再実行](../runs/duet-mixed-limiter-gain-order-20261122-repeat/manifest.json)・[通常レベルの回帰](../runs/duet-mixed-output-gain-20261122-limiter-regression/manifest.json)
