# 固定母音 /i/ の声門枝で生じる流量差

## 読解と予測

固定版の `HumanVoice::render` は呼気を進め、前回の声門上下圧の差を声帯モデルに渡す。その面積を `HumanAirway` が作った声門ポートへ入れ、`AirwayNetwork::step` が枝流量、壁流量、節点圧力の順に更新する。研究版の `FixedVoice::step_source` も同じ向きで声門流量を解く。成人男性の声門ポートは気管末端から咽頭セル0に向かい、長さ0.3 cmのスリットと両隣の半セルを含む。面積の単位はcm²、流量はcm³/s、圧差はdyn/cm²。上流の狭窄試験は定常流をBernoulliの式に、ホスト分割試験は更新をまたいだ出力を基準のPCMに照合する。[上流の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[ポートの定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L153)・[研究版の描画](../crates/vocal-core/src/voice.rs#L214)・[狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[ホスト分割試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

慣性 `L` はスリットと半セルの寄与、粘性抵抗 `R` はスリット幅と開口の逆数の3乗に比例する項、非線形係数 `K` は入口と出口の損失から構成される。枝では前回流量を `U_prev` として、慣性が増すときは前回の運動量を使い、減るときは `L × U_prev` を使う。駆動量 `C` は上下圧の差と雑音源に、持ち越した運動量を時間で割って足した値。線形項を `B = L/dt + R` とし、流量は相応の符号の `K` で `2C / (B + sqrt(B² + 4K|C|))` を使う。上流は運動量 `L × U` を保存し、次の標本でサンプルレートを掛ける。研究版は直前の慣性と流量を持ち、慣性を時間で割ってから流量を掛ける。抵抗のスリット幅・逆面積のべき乗も、上流は連続する掛け算、研究版は積をまとめてから掛ける。[係数と更新式](../crates/vocal-core/src/airway/network.rs#L81)・[上流の係数と運動量](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L990)

前回の両変更版では、内部8,210点目で声門流入に初差が出た。両実装で圧差と前回流量は揃い、係数または時間換算の丸めから流量が分かれると予測した。通常の描画から対象枝だけを52内部点記録し、保存済みの波形と圧力を維持した状態で、各項を置き換えて初差を復元する。[事前登録](../cases/fixed-voice-glottal-branch-48000.json)・[前回の両変更版](fixed-voice-centerline-render-48000.md#幾何から声門上圧とpcmまでの結果)

第1版では8,210点目の駆動量・非線形損失が一致し、線形項だけを上流値にすると流量が一致した。元の状態を固定した区間の検算では、抵抗だけの置換は従来の流量を保ち、慣性の時間換算だけの置換は8,210点目と8,211点目をそれぞれ上流に揃えた。8,188〜8,209点には流量が変わる点がなかった。そのため、声門枝だけで線形項の慣性を `L × Fs` へ変え、連続描画でも8,210点目の流量と圧力が揃うかを第2版に登録した。[第1版の計測](../runs/fixed-voice-glottal-branch-48000-a/summary.json)・[第2版の予測](../cases/fixed-voice-glottal-branch-48000.json)

## 線形項に入る慣性の時間換算

上流と中心線の両変更版をそれぞれ隔離し、通常の描画に声門枝だけの記録を加えた。候補の8,240内部点の観測系列、上流の出力点の系列と4,120フレームのPCMは、各版の保存済み成果にバイト一致した。52点の記録では、圧差・面積・前回流量・慣性が8,210点目で一致していた。持ち越し項は既に丸めが異なったが、駆動圧ではその差が消えていた。分母につながる慣性の時間換算値は研究版 `2265.027547494078`、上流 `2265.0275474940777`。抵抗も `408.97377107833364` と `408.9737710783337` で微小に異なる。有理数演算と中間丸めを使う検算で、慣性換算の単独置換から上流流量 `1.917196516622917e-9` cm³/sを復元した。抵抗の単独置換からは元の流量 `1.9171965166229166e-9` cm³/sを得た。[研究版の枝](../runs/fixed-voice-glottal-branch-48000-v2/artifacts/candidate-branch.csv)・[固定上流の枝](../runs/fixed-voice-glottal-branch-48000-v2/artifacts/upstream-branch.csv)・[実行の要約](../runs/fixed-voice-glottal-branch-48000-v2/summary.json)

## 連続描画での効果

隔離した実験版では声門枝の線形項だけで `L × Fs` を使った。8,188〜8,209点の流量は実験前とビット一致し、8,210点目では上流の流量と声門上圧に一致した。次の初差は流量・声門上圧とも8,215点目だった。この点では線形項が一致し、持ち越し運動量の時間換算の差が駆動圧に残る。実験版の `0.0032871204163718217` dyn/cm²を上流の `0.0032871204163718213` dyn/cm²へ置き換えると上流の流量を復元した。上流と同じ `(L × U_prev) × Fs` を実験版の持ち越し運動量に適用してもこの駆動量と流量を得た。次はこの持ち越し項だけを同じ順にし、初差と全PCMを比較する。[実験用差分](../runs/fixed-voice-glottal-branch-48000-v2/artifacts/candidate-inertance-scale.patch)・[連続描画の観測](../runs/fixed-voice-glottal-branch-48000-v2/artifacts/scaled-branch.csv)・[上流の持ち越し式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)

48 kHzの全93,056フレームで、128・77フレームの分割はビット一致した。慣性換算を揃えると、上流とのPCMの最初の差は4,802フレーム目から59,761フレーム目へ移り、ビット差があるフレームは18から16へ減った。最大絶対差は約1.819×10⁻¹²。実験前の両変更版との違いは14フレームだった。[全区間の比較](../runs/fixed-voice-glottal-branch-48000-v2/summary.json)

## 実行環境と再現確認

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で実行した。第1版の9判定を保持し、第2版は研究ワークスペースと `/tmp` から各16判定に合格した。固定上流のエンジンと気道の各6試験が通過した。第2版の要約、3条件の声門枝CSV、研究版の内部系列、両分割のWAVは実行間でバイト一致した。独立十進計算は各回156点の枝流量を照合し、8,215点目の持ち越し項の単独置換も再現した。3実行の計437入力と54出力をハッシュで照合し、出力のうち10,523,181バイトをRTL9210B-CGに保存した。[再実行のマニフェスト](../runs/fixed-voice-glottal-branch-48000-v2-repeat/manifest.json)・[上流の試験](../runs/fixed-voice-glottal-branch-48000-v2-repeat/artifacts/upstream-tests.log)・[独立検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-glottal-branch-48000.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_glottal_branch.py fixed-voice-glottal-branch-48000-new
```
