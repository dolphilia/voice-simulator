# 停止後のPCM差に効く放射成分

## 読解と事前の予測

固定上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は [`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053) から各内部点の放射微分を受け取る。気道網はまず、節点圧と前回の速度・変位から各壁の速度を更新し、壁面積との積に放射割合を掛けて足す。次に口端と鼻端の放射負荷を節点圧と結合して流量を求める。壁、口端、鼻端の流量（cm³/s）の和 `U[n]` から前回の和 `U[n−1]` を引き、内部レートを掛けた値（cm³/s²）がFIR入力になる。前回の和は今回値で更新されるため、1点の和の差は隣接する2つの微分に逆符号で入る。[終端と放射微分](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)・[時間応答と周波数応答を照合する上流試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

候補では [気道網の壁と節点更新](../crates/vocal-core/src/airway/network.rs#L747) を経由し、これまでの隔離差分により微分の時間換算は上流と同じ乗算となっている。通常の [`render-pcm`](../crates/vocal-cli/src/main.rs#L452) で追加観測し、先行レンダーと同じ出力を保てるかを確認する。55,880フレーム目では内部111,732・111,734・111,737・111,738点目の放射入力のどの1点を上流値に置き換えてもPCMが一致した。これらの点で何が異なるかを確認し、微分の局所置換と、流量和を揃えて次点の微分にも反映する置換を比較する。[先行の出力段比較](fixed-voice-release-output-48000.md#放射の履歴からpcm差を復元する)・[事前登録](../cases/fixed-voice-release-radiation-48000.json)

## 前回流量和を口端の流量まで分ける

通常CLIと固定上流に放射の観測だけを加え、保存済みのFIR入力、出力段、全93,056フレームのPCMを再現した。内部111,731〜111,739点目の壁流量和、口端・鼻端とそれらの合計、前回の合計から、各点の微分をビット単位で再計算できた。4対象点の鼻端流量は両版でゼロ。壁流量和、口端流量、前回の流量和には差があった。[測定値と置換の結果](../runs/fixed-voice-release-radiation-48000-a/summary.json)

| 内部点 | 上流の微分を復元する局所置換 | 上流PCMを復元する局所置換 | 隣接する微分にも反映した場合に上流PCMを復元する置換 |
| --- | --- | --- | --- |
| 111,732 | 壁・口端・前回の和 | 口端・前回の和 | 全組み合わせで未一致 |
| 111,734 | 壁・口端・前回の和 | 前回の和 | 前回の和と壁、または前回の和と口端 |
| 111,737 | 壁・口端・前回の和 | 前回の和 | 前回の和 |
| 111,738 | 前回の和 | 前回の和 | 全組み合わせで未一致 |

表は各条件で最少の組を示す。局所置換はFIRに入る微分をその1点だけ入れ替える。隣接する微分にも反映する条件では、変更した流量和を同じ番号の微分と次の微分に使う。111,738点目では壁と口端の差が合算で打ち消され、今回の流量和はビット一致した。111,732・111,738点目では、差分を取る前後で同じ流量和を共有すると丸め先は候補と同じだった。[独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-radiation-48000.json)

111,734・111,737点目の前回流量和を、元の111,733・111,736点目へさかのぼった。111,736点目では候補と上流の口端流量差は `−9.5923×10⁻¹⁴` cm³/s、壁流量和の差は `−5.3291×10⁻¹⁵` cm³/s。111,733点目と111,736点目のどちらでも、口端流量だけを置き換えて流量和を作り、その点と次点の放射微分を計算すると55,880フレーム目が上流PCMに丸まった。次はこの2点の口端負荷について、枝からの流入、更新前圧、放射慣性・抵抗と持ち越し流量を採る。[口端を分離した十進計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-radiation-48000.json)

## 実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_release_radiation.py fixed-voice-release-radiation-48000-a

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_release_radiation.py" \
  fixed-voice-release-radiation-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各6判定と固定上流の各9試験に合格した。研究版のホスト分割128・77と上流の各9点で、各実行の壁972点と放射27点を十進数で再計算した。独立計算でも最少の置換と、2微分に反映したときのPCMを再現した。再実行間でCSV・PCM・差分の23出力がバイト一致した。固定上流の一時プローブの実行ファイルはハッシュが異なった。全2実行の394入力と62出力をハッシュ照合し、採取物6,587,929バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-release-radiation-48000-repeat/manifest.json)・[十進計算と生PCM](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-radiation-48000.json)
