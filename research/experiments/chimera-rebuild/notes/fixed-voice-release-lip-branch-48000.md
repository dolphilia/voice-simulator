# 停止後の口端直前の枝で流量差を調べる

## 読解と事前の予測

上流は [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) の内部ステップで節点圧を読み、[`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L922) で枝の流量（cm³/s）を両端の体積収支へ加える。口端へ入る枝の正方向は節点47から48。現在慣性 `L`（g/cm⁴）は両隣接半セルの長さと断面積から計算し、粘性抵抗は周長・長さ・断面積から求める。圧差（dyn/cm²）と乱流圧、前回の流量から持ち越した運動量の時間換算を加えて駆動圧を得る。

上流の [枝の更新式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029) では `L×Fs+R` が線形項になる。駆動圧の符号に応じて方向別の二次損失を選び、枝流量を解いて次回用の流量・運動量・慣性を保存する。研究版の [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) は時間刻みでの除算を使う。枝の後で壁速度と流出を更新し、口端では枝流入から壁流出を差し引いて並列R–L負荷を解く。[上流の定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92) は方向別の流量損失を使う枝計算を圧力差から照合する。

前回の計測では停止後の111,733・111,736点目の口端純流入差が、枝からの流入差と一致した。この枝では左右圧と持ち越しの差が寄与すると予測する。係数と駆動圧の各項を直接採り、流量差を再現する最小の置換を求める。口端負荷へ復元した流量を渡し、更新前圧や慣性枝流量を保った局所置換でPCMの丸め先がどう変わるかも測る。[先行の口端負荷](fixed-voice-release-lip-load-48000.md#更新前圧と連続する流入の寄与)・[事前登録](../cases/fixed-voice-release-lip-branch-48000.json)

## 左右圧と持ち越し圧が枝流量差を作る

節点47→48を採取し、全19点で両端圧を口端負荷の観測と対応づけ、枝流量が口端の流入に使われたことを確認した。対象区間で現在慣性・その時間換算・抵抗・線形項はビット一致した。最小断面積と方向別損失にはわずかな差があり、実際に使われた逆方向の損失だけを上流値に替えた再計算では、全19点の枝流量が元の候補値に丸まった。[枝の観測と結果要約](../runs/fixed-voice-release-lip-branch-48000-a/summary.json)・[独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-branch-48000.json)

111,733・111,736点目は、左圧・右圧・持ち越し圧をすべて上流値にすると枝流量がビット一致した。両点の圧差と持ち越し圧の誤差は符号が逆で、駆動圧では一部が打ち消された。表は候補から上流を引いた値を示す。[駆動圧の内訳と局所置換](../runs/fixed-voice-release-lip-branch-48000-a/summary.json)

| 内部点 | 左圧の差（dyn/cm²） | 右圧の差（dyn/cm²） | 持ち越し圧の差（dyn/cm²） | 枝流量の差（cm³/s） |
| --- | --- | --- | --- | --- |
| 111,733 | −2.9896×10⁻¹² | +1.6342×10⁻¹² | +3.1264×10⁻¹² | −7.5495×10⁻¹⁴ |
| 111,736 | −5.3291×10⁻¹⁵ | −1.0827×10⁻¹² | −1.8474×10⁻¹² | −3.9080×10⁻¹⁴ |

各対象点で復元した枝流量を候補の口端負荷へ渡すと、口端流量はそれぞれ `−7.237664980760854` と `−7.926760496778579` cm³/s になった。これを隣接する2つの放射微分に反映しても、55,880フレーム目は候補と同じ値に丸まった。この計算では候補の口端負荷に記録された更新前圧と持ち越し流量から出発した。[口端と出力段までの再計算](../runs/fixed-voice-release-lip-branch-48000-a/summary.json)

測定した左右圧を外部入力とし、枝の式を111,725点目から連続で解く対照も行った。左右圧の系列と開始時の前回流量を上流に揃えると、対象2点の流量差は `−7.11×10⁻¹⁵` と `−9.77×10⁻¹⁵` cm³/s まで縮まった。この条件で持ち越し圧も `(L_carry×U_prev)×Fs` にすると両点がビット一致した。次は、この枝だけで持ち越し圧を換算し直した気道網全体の連続描画を測り、左右圧のフィードバックと停止後のPCMの応答を確認する。[測定圧を使った連続計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-branch-48000.json)

## 実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_release_lip_branch.py fixed-voice-release-lip-branch-48000-a

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_release_lip_branch.py" \
  fixed-voice-release-lip-branch-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各5判定と固定上流の各12試験に合格した。各実行で研究版のホスト分割128・77と固定上流について各19点の枝流量と口端との時刻対応を十進数で照合した。全93,056フレームと先行の口端負荷・放射・出力段の観測結果を再現した。32出力が再実行間でバイト一致し、計420入力と80出力のハッシュを照合した。固定上流の一時プローブは実行ファイルのハッシュが異なった。採取物6,814,535バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-release-lip-branch-48000-repeat/manifest.json)・[十進数での独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-branch-48000.json)

## 枝47→48の持ち越し圧だけを連続描画で揃える予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は成功した内部更新ごとに気道の放射を間引き器へ渡す。気道の [枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029) は前回の流量（cm³/s）と慣性（g/cm⁴）から保存した運動量を読み、慣性が下がった場合は現在慣性と前回流量から持ち越し量を求める。その運動量（g/(cm·s)）を内部レートで掛けて圧力（dyn/cm²）にし、左右圧と乱流圧の項に加える。枝が出した流量から両端の節点圧を更新し、次の内部点の枝と壁運動がそれを読む。研究版では [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) へ渡す対象枝の持ち越し項だけを、計測時に選んだ短い区間と同じ枝に対して全描画で乗算順にする。[上流の狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[ホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

測定した左右圧を固定して前回流量を上流から与えた連続計算では、この換算を追加すると111,733・111,736点目の枝流量が上流と一致した。気道網全体での連続描画では、変化した流量が次の圧力と前回運動量に戻る。そのため、枝の換算式は独立計算との一致を検証し、枝流量と口端負荷、出力55,880フレーム目および全PCMの差の大きさは実測する。[先行の連続再計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-branch-48000.json)・[事前登録](../cases/fixed-voice-release-lip-history-48000.json)

## 持ち越し圧を揃えた連続描画の結果

気道網全体を描画し、口端へ入る枝47→48だけの持ち越し圧を上流順にした。採取全19点で、各条件の前回流量・慣性から持ち越し圧と枝流量を再計算できた。変更版と上流との差は、前回の局所比較と同様に左右圧と持ち越し圧の置換で、111,733・111,736点目の枝流量まで復元できた。実際の連続描画では、測定した左右圧を与える先行の計算と異なる圧力・前回流量の系列になった。[枝47→48だけに適用するRust差分](../runs/fixed-voice-release-lip-history-48000-repeat/artifacts/reordered/candidate-release-lip-history.patch)・[中間項と置換](../runs/fixed-voice-release-lip-history-48000-repeat/summary.json)

観測19点で上流との差の最大絶対値は、枝流量が `3.18×10⁻¹³` から `3.93×10⁻¹³` cm³/s、口端流量が `1.60×10⁻¹³` から `2.02×10⁻¹³` cm³/s に増えた。対象の111,733・111,736点目だけを見ると、枝流量は上流から遠ざかり、口端放射流量は上流に近づいた。放射微分を採った81点では、上流と異なる点が80から78に減り、最大絶対差は `1.33×10⁻⁸` から `1.50×10⁻⁸` cm³/s² に増えた。[区間別の測定値](../runs/fixed-voice-release-lip-history-48000-repeat/summary.json)

全93,056 PCMフレームでは、上流と異なる停止後のフレームが13から11に減った。対照と変更版をフレームごとに照合すると、7フレームが新たに一致し、5フレームが新たに分かれた。最大絶対差は `5.8207661×10⁻¹¹`、最初の差は55,880フレーム目で両条件とも同じだった。この点の丸め直前の値は上流との境界へ近づき、`f32` では対照と同じ側に丸まった。既存の絶対許容差 `5×10⁻⁷` と2分割のビット一致は両条件で確認した。ビット差の数、内部誤差と最大PCM差を別々に記録する。[生PCMとフレームの変化](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-history-48000.json)

## 持ち越し圧を揃えた描画の実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_release_lip_history.py fixed-voice-release-lip-history-48000-a

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_release_lip_history.py" \
  fixed-voice-release-lip-history-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各6判定と固定上流の各12試験に合格した。各実行の両条件・両分割の枝と口端負荷各76点を十進数で再計算し、生PCMからフレーム差と最大値を照合した。対照のPCM・枝・放射・出力段は先行採取と一致した。再実行で41出力がバイト一致し、計432入力と96出力のハッシュを検証した。採取物8,188,892バイトをRTL9210B-CGに保存した。変更は隔離版の比較差分として保存した。[再実行マニフェスト](../runs/fixed-voice-release-lip-history-48000-repeat/manifest.json)・[独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-history-48000.json)
