# 固定発声の停止後に生じる最初のPCM差

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は、気道網が返す放射流量微分（cm³/s²）を内部点ごとに [`Decimator::push`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/decimator.rs#L63) に渡す。出力48 kHz・内部96 kHzでは49タップのKaiser窓付きFIRを使い、2内部点ごとに、古い放射から順に対応する係数との積を加算して出力する。研究版は通常CLIの [`render-pcm`](../crates/vocal-cli/src/main.rs#L452) から [`OutputStage::render_frame`](../crates/vocal-core/src/output.rs#L76) に同じ原理の間引きを接続する。FIRの係数と履歴の両方を採り、それぞれの寄与を単独で検算する。

間引き後はゲインを掛け、今回入力 `x`、前回入力 `x_prev`、前回直流除去値 `y_prev` から `y=x−x_prev+a×y_prev` を計算する。ゲイン以後の値はPCMのフルスケールを1とした無次元量で、`a` は25 Hzに対応する係数。出力段はピーク包絡と保持フレーム数を更新し、包絡が0.75を超えると振幅を縮め、その結果の絶対値が0.85を超える場合に滑らかに制限する。最後に `f32` に丸める。上流の [出力処理](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L395) と研究版の [`OutputStage::push`](../crates/vocal-core/src/output.rs#L103) を照合し、[上流のホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78) と同じ128・77でも比較する。

前回に保存した全PCMでは、55,880フレーム目の変更版は `0.0006782786222174764`、上流は `0.0006782785640098155` で、差は隣接する `f32` 値1個分だった。両方とも絶対値が小さいため、FIR入力または直流除去の履歴にあった微小差が丸め境界をまたいだ可能性を調べる。対象点を含み、49タップの履歴も覆う短い窓を先に固定する。[前回のPCM比較](../runs/fixed-voice-pharyngeal-second-cell-history-48000-repeat/summary.json)・[事前登録](../cases/fixed-voice-release-output-48000.json)

## 放射の履歴からPCM差を復元する

観測したFIR係数49個、ゲイン、直流除去の係数はビット一致した。最初に採った内部111,697点目ですでに放射入力に差があり、最初の出力観測である55,872フレーム目では間引き値と直流除去の前回状態が分かれていた。この採取範囲では、最初のPCM差より手前の小さな差まで確認できた。[放射・間引き・出力の照合](../runs/fixed-voice-release-output-48000-b/summary.json)

55,880フレーム目は包絡が約0.235で、利得制限とソフトクリップのどちらも作動しなかった。変換直前の倍精度値は、候補で `0.0006782785931138374`、上流で `0.0006782785931110302`。隣接する `f32` 値の中点 `0.0006782785931136459` に対し、それぞれ約 `+1.91×10⁻¹⁶` と `−2.62×10⁻¹⁵` で、異なる側へ丸まった。[対象フレームの実測値](../runs/fixed-voice-release-output-48000-b/summary.json)

現在のFIRに入る49点の放射履歴だけを上流値に替えると、候補の係数・直流除去状態のままで上流のPCMを復元した。直流除去の前回入力と前回出力を一緒に替えた場合、両項の影響がほぼ打ち消し合い、元の候補PCMに丸まった。前回入力の単独置換でも上流のPCMに丸まる。前回入力は1つ前の間引き出力にゲインを掛けた値で、この置換は直流除去の係数差を必要としない。[FIRと直流除去の独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-output-48000.json)

現在の放射履歴では、内部111,732・111,734・111,737・111,738点目のどの1点を上流値にしても、対象PCMは上流と同じ側へ丸まった。各1点で丸め境界を越えられるため、これらは残差の原因を絞るための観測点として扱う。次は中央タップに当たる111,737点目を含む4点で、壁・口端・鼻端と前回の放射流量和を照合する。[単一点置換の計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-output-48000.json)

## 実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_release_output.py fixed-voice-release-output-48000-b

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_release_output.py" \
  fixed-voice-release-output-48000-repeat
```

初回の `-a` は、先行パッチの放射成分ログと今回のFIR入力ログが同名だったため、集計で終了した。初回の描画とログを残し、今回のログ名を分けた後に新しい実行IDで再計測した。[初回のマニフェスト](../runs/fixed-voice-release-output-48000-a/manifest.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各6判定と固定上流の各6試験に合格した。研究版の分割128・77と上流について各17点、計51点の出力段を有理数と十進数で再計算した。全93,056フレームは両版ともそれぞれの先行の合成PCMとビット一致した。再実行でCSV・PCM・差分の15出力がバイト一致し、374入力と46出力のハッシュを照合した。固定上流の一時プローブは実行ファイルのハッシュが異なった。成功した計測の実体7,324,297バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-release-output-48000-repeat/manifest.json)・[十進計算と生PCMの照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-output-48000.json)
