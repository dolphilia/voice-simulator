# 混合体型の出力ゲインとPCM

女性係数0.4・子ども係数0.3の歌唱を、固定上流と同じ休止舌先・音源変動0にそろえた後も、PCMの全区間には最大0.08469647の差が残っていた。保存した研究版PCMを0.875倍すると差は `5.22×10⁻⁸` に減った。今回は研究版の `song_voice.voice.output_gain` だけを変更し、上流と同じ段で乗算が行われた場合を計測する。[事前登録](../cases/duet-mixed-output-gain.json)・[休止舌先の実測](duet-mixed-initial-tip.md#実測)

## 読解と予測

- 固定上流の `render::notes` から `plan_song`、`HumanVoice::new`、`HumanVoice::render` の順にたどる。混合体型の入力は保存済みの `upstream_duet_body_probe` に渡す。この入口は無変更の固定上流ライブラリを使って、通常の歌唱CLIと同じ音源設定・ジェスチャー登録・128フレーム分割で描画する。`BodyMix::weights` から成人男性・成人女性・子どもの重みはそれぞれ0.42・0.28・0.30になり、基準長の比は `0.42×1 + 0.28×0.9 + 0.30×0.74 = 0.894`。固定上流の `HumanVoice::new` は、長さ比0.9以下の体型に一律で0.875を掛ける。0.9から1.0の間で係数が0.875から1.0へ線形に増える。研究版の `run_song` は体型とは別に、ケースのゲインを `OutputStage::new` に渡す。[上流の歌唱入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L525)・[無変更の上流を使う混合体型観測器](../tools/upstream_duet_body_probe.rs)・[上流のゲイン設定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L280)・[研究版の歌唱入口](../crates/vocal-cli/src/timing_case/speech_voice.rs#L260)
- 96 kHzの放射流量変化率（cm³/s²）をFIRリングに書き、2内部サンプルごとに49タップのカイザー窓付きsincと畳み込む。ゲインを掛けて正規化振幅 `x` とし、`y[n] = x[n] − x[n−1] + e^(−2π×25/48000)y[n−1]` でDCを除く。出力状態は前回の `x` と `y`、ピーク包絡、保持フレーム数。包絡は大きな入力で更新し、25 ms保持した後、時定数0.2秒で減衰する。包絡が0.75超なら `0.75/包絡` の係数を掛け、結果の絶対値が0.85超なら `tanh` で圧縮する。最後にPCMを `f32` に丸める。`engine` はブロック分割でPCMが変わらないこととレートを変えた音量を、`body_mix` は混合体型の重み、音響応答、描画を確認する。[上流の間引き](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L55)・[上流の出力処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L395)・[研究版の出力処理](../crates/vocal-core/src/output.rs#L103)・[上流のエンジン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[上流の体型試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/body_mix.rs)
- ゲインはFIRの後で適用され、声源や気道の状態を変える項は無い。研究版のゲイン2条件で放射とFIRがビット一致し、変更後のPCMは上流との差が `6×10⁻⁸` 以下になると予測した。包絡は0.75以下を予測。ピーク制限が無ければ、PCM化した後に係数を掛ける場合との違いは主に丸めの位置に現れる。出力段の独立計算には、実装から係数を取得せずにベッセル関数からFIRを再設計し、直接畳み込みと `scipy.signal.lfilter` でDCを照合する。各観測点から包絡と保持残数も別に更新した。[計測CLI](../tools/measure_duet_child_output_gain.py)・[子ども声部の検証](duet-child-output-gain.md)・[既存の大振幅での出力段の検証](pcm-output.md)

## 再現

研究版は通常の `render-pcm-tele` と出力段の観測器を両ゲインで実行する。固定上流の既定音源は上流の無変更ライブラリによる混合体型観測と照合し、音源の変動をそろえた条件では先行の保存PCMと照合する。観測器の `.f64le` は1フレームごとに内部放射2点、FIR出力、ゲイン後、DC除去後、包絡、保持残数の順に並ぶ。PCMは別の `.f32le` に保存する。作業時の採取物と上流の一時展開先はRTL9210B-CGを使う。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_duet_child_output_gain.py --case mixed duet-mixed-output-gain-new
```

## 実測

研究版の二条件は全195,840点の内部放射と97,920点のFIR出力がビット一致した。研究版同士で最初に差が生じたのは、25,025出力フレーム目のゲイン乗算だった。同フレームのゲイン直後は基準で `1.132963045748668×10⁻¹⁰`、0.875倍で `9.913426650300846×10⁻¹¹`。ゲインをそろえた研究版と固定上流の間では、同じフレームの1点目の内部放射で数値が初めて異なった。包絡の最大値は基準で0.677572、ゲインをそろえた両版で0.592875。ピーク制限・ソフトクリップの発動は各条件で0フレームだった。[段別の実測](../runs/duet-mixed-output-gain-20261122-a/summary.json)

| 固定上流との全区間の最大絶対差 | 研究版の基準ゲイン | 描画時に0.875倍 |
| --- | ---: | ---: |
| 内部放射（cm³/s²） | 4.26×10⁻⁷ | 4.26×10⁻⁷ |
| 間引き後・ゲイン直後 | 0.08468856 | 1.41×10⁻¹³ |
| DC除去後 | 0.08469647 | 1.37×10⁻¹³ |
| PCM | 0.08469647 | 1.46×10⁻¹¹ |

描画時に係数を適用した結果は、すでに丸めたPCMを `f64` で0.875倍した結果の最大差 `5.22×10⁻⁸` より小さかった。後から換算したときの最大差が出た35,182フレーム目は、描画段でゲインをそろえると両実装で同じFloat32値になった。描画段でも残ったPCMのビット差は7,186フレーム。最初の28,039フレーム目と最大差の81,682フレーム目では、両版のDC除去後の値が隣接するFloat32値の中点を挟んだ。隣接値より離れていた5,520フレームでも、絶対差は最大 `2.14×10⁻¹⁴` 未満だった。ほぼ無音の区間でFloat32の刻みを単位に評価すると、絶対差の大きさとは異なる結果になる。[研究版の段別時系列](../runs/duet-mixed-output-gain-20261122-a/artifacts/matched-output.f64le)・[固定上流の段別時系列](../runs/duet-mixed-output-gain-20261122-a/artifacts/upstream-output.f64le)

独立FIRとの誤差は基準ゲインで正規化して最大 `6.41×10⁻¹⁶` 未満、独立DC計算との差は `2.24×10⁻¹⁶` 未満。包絡・保持残数は全フレームで一致し、制限の判定と丸めを通した独立計算は各条件のPCMとビット一致した。今回の混合体型で残る差は上流と研究版の放射の段ですでに観測できる。放射差の導入箇所と、ゲインの違いでどちらかの包絡だけが0.75を超える場合の効果は、別の計測で調べる。

放射を1.2倍した追試では、基準ゲインだけが6,954フレームで制限に入った。ゲインを掛ける位置によるPCM差は最大0.05520034だった。[ピーク制限の追試](duet-mixed-limiter-gain-order.md#実測)

通常レベルの放射差を分けた追試では、出力25,025フレームの1点目で口端流量に最初の差が出た。この時点で鼻端・壁の放射は0で、口端流量を時間差分にするとほぼ全差を再構成できた。[放射成分の追試](duet-mixed-radiation-origin.md#実測)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。研究ワークスペースと `/private/tmp` の2実行で、各10判定と5予測、固定上流10試験が通過し、25出力がバイト一致した。標準ライブラリでも体型の長さ比、PCMへの丸め、最初の差、Float32の表現上の差を再計算した。子ども声部の回帰は9判定と4予測、固定上流10試験が通過し、先行の27出力と一致した。3実行の432入力・99出力についてサイズとSHA-256を確認し、採取物109,088,065バイトをRTL9210B-CGに保存した。[初回](../runs/duet-mixed-output-gain-20261122-a/manifest.json)・[再実行](../runs/duet-mixed-output-gain-20261122-repeat/manifest.json)・[子ども声部の回帰](../runs/duet-child-output-gain-20261122-mixed-regression/manifest.json)
