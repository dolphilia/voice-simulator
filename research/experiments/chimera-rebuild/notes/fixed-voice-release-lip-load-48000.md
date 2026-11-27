# 停止後の口端流量差を放射負荷の入力まで追う

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は内部点ごとに声門面積を更新し、気道網の枝、壁、節点と放射を進める。口端の開口面積 `A`（cm²）から、慣性 `L=8ρ/(3π√(πA))`（g/cm⁴）と抵抗 `R=128ρc/(9π²A)`（dyn·s/cm⁵）を算出する。節点の体積と空気の弾性率から求めるコンプライアンス `C`（cm⁵/dyn）、更新前圧 `p₀`（dyn/cm²）、枝からの流入に体積源と壁流出を加味した流入 `U_in`（cm³/s）、慣性枝の持ち越し流量 `U_L₀` を、並列R–L負荷と節点圧の中点方程式に渡す。開口が狭まって慣性が増すときは保持した運動量に合わせて持ち越し流量を換算する。[上流の終端分岐](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1119)

内部刻みを `dt`、`h=dt/(2L)`、`g=1/(2R)` とすると、更新後圧を `p₁=(p₀(C/dt−h/2−g)+U_in−U_L₀)/(C/dt+h/2+g)` と解く。慣性枝は `U_L₁=U_L₀+h(p₀+p₁)`、口端放射は `(U_L₀+U_L₁)/2+g(p₀+p₁)`。研究版の [`RadiationLoad::step`](../crates/vocal-core/src/airway.rs#L89) は同じ中点式を、`C/dt` の除算と `g+h/2` の先行加算で評価する。固定上流は内部レートを掛け、慣性項と抵抗項を順に加減算する。新しい圧力と慣性枝流量は次点に渡る。上流の [一様管の時間・周波数応答試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68) はこの放射終端を含む共鳴を確認する。

前回の置換では、111,733・111,736点目の口端流量だけで出力55,880フレーム目の丸め先が変わった。固定姿勢での比較を使い、同じ開口から同じ抵抗と慣性が得られると予測する。更新前圧・流入・持ち越し流量と演算順を個別に置き換え、得られた口端流量を保存済みの前後の放射微分と出力段へ戻す。[先行調査](fixed-voice-release-radiation-48000.md#前回流量和を口端の流量まで分ける)・[事前登録](../cases/fixed-voice-release-lip-load-48000.json)

## 更新前圧と連続する流入の寄与

口端の節点48について、内部111,725〜111,743点目の全19点で開口面積 `3.620599371410219` cm²、コンプライアンス `1.2347926574736667×10⁻⁶` cm⁵/dyn、放射慣性・抵抗がビット一致した。両版の演算順で各点を再計算し、節点圧、慣性枝流量と口端流量を再現した。観測の先頭ですでに更新前圧、慣性枝の持ち越し流量、壁の前後の流入が分かれていた。[最初の差と各項の観測値](../runs/fixed-voice-release-lip-load-48000-a/summary.json)

111,733・111,736点目とも、**更新前圧・慣性枝の持ち越し流量・流入**をすべて上流値に置くと、研究版の演算順で口端流量が上流とビット一致した。中点式の圧力に掛ける係数と分母はこの2点で両版が一致し、演算順だけを替えた結果も元の候補値と一致した。更新前圧だけを置換した口端流量を同じ点と次点の放射微分に反映すると、55,880フレーム目のPCMが上流に丸まった。[置換とPCM](../runs/fixed-voice-release-lip-load-48000-a/summary.json)

| 内部点 | 候補の口端流量（cm³/s） | 上流の口端流量（cm³/s） | 更新前圧の差（候補−上流、dyn/cm²） | 枝からの流入差（候補−上流、cm³/s） |
| --- | --- | --- | --- | --- |
| 111,733 | −7.237664980760874 | −7.237664980760938 | +1.6342×10⁻¹² | −7.5495×10⁻¹⁴ |
| 111,736 | −7.926760496778590 | −7.926760496778494 | −1.0827×10⁻¹² | −3.9080×10⁻¹⁴ |

対象2点で、壁を差し引いた節点流入の差は、その前の直列枝流量の差と同じ値だった。壁流量の差は加減算の丸めで消えた。111,725点目に採った圧力・慣性枝流量から19点の中点式を続けて解くと、初期状態だけの置換後の残差は約 `+6.66×10⁻¹⁴` と `−1.00×10⁻¹³` cm³/s だった。流入系列だけを上流値にすると残差は約 `−4.44×10⁻¹⁵` と `+5.33×10⁻¹⁵` cm³/s に縮まった。初期状態と流入系列を上流値にした場合、研究版の演算順で19点すべての口端流量が上流と一致した。この結果は、測定済みの流入を順に与えた口端負荷単体の再計算による。[十進計算と連続再計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-load-48000.json)

## 実行と検証

```bash
# 研究用ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_release_lip_load.py fixed-voice-release-lip-load-48000-a

# /tmp から実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_release_lip_load.py" \
  fixed-voice-release-lip-load-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で各5判定と固定上流の各9試験に合格した。各実行で研究版のホスト分割128・77と固定上流の各19点、計57点を十進数で検算した。観測追加後も全93,056フレームが各版の保存済みPCMとビット一致した。再実行間で26出力がバイト一致し、計410入力と68出力のハッシュを照合した。固定上流の一時プローブの実行ファイルはハッシュが異なった。採取物6,667,395バイトをRTL9210B-CGに保存した。[再実行マニフェスト](../runs/fixed-voice-release-lip-load-48000-repeat/manifest.json)・[独立計算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-release-lip-load-48000.json)
