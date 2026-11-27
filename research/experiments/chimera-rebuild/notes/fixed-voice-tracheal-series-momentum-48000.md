# 気管の直列枝12本で持ち越し運動量を揃える

## 読解と事前の予測

上流の [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は内部点ごとに肺の境界圧と声門開口を設定し、気道を更新する。[`AirwayNetwork::add_tube`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L441) は管の隣り合う節点を直列枝で結ぶ。[`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L955) は左右の半セルから慣性 `L`（g/cm⁴）と粘性抵抗を作り、静的な枝では前回運動量 `L×U_prev` に内部サンプルレート `Fs` を掛ける。前回流量 `U_prev` の単位は cm³/s、換算した項の単位は dyn/cm²。この圧を節点間圧力差に足し、枝の新しい流量を得る。流量を接続する節点の体積収支へ加減し、そこから圧力を更新する。気管末端の圧力を声門が読むのは次の内部点。

研究版の [`add_tube`](../crates/vocal-core/src/airway/human.rs#L405) が返す `AirwayTube.branches` は、管内部の連続した枝番号の範囲。肺ポートは固定圧の節点と最初のセルを、声門ポートは末端と咽頭を別途つなぐ。先行の隔離ビルドで [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) に加えた持ち越し圧の換算を、最初の1本からこの範囲へ広げる。上流の [`steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92) は断面が変わる場合の非線形損失を扱う。今回は断面一定の条件なので、慣性と抵抗を足した線形係数で駆動圧を割る。

[先行の枝1だけの実験](fixed-voice-tracheal-momentum-48000.md#連続描画での圧力とpcmの変化)では、8,198点目の枝2を流れる `U` が、セル1から出る流量として同じ時点の圧力差を作った。同じ丸め順を気管の12本に広げ、8,198点目の枝2とセル1が上流値に揃うと予測した。気管を出た後の声門流量と、ゲート停止を含む全PCMの差も記録する。[事前登録](../cases/fixed-voice-tracheal-series-momentum-48000.json)

## 末端圧の一致と肺・声門ポートに残る差

固定 `/i/` の同じゲート入力と声道姿勢を使った。先行の枝1だけのビルドを差分から復元し、その描画・波形を対照にした。隔離ビルドで変更するのは、持ち越し圧を上流順に計算する枝の範囲。観測区間は内部8,188〜8,239点目、PCMは出力48 kHzの93,056フレーム。ホスト分割を128と77にして両版を描画した。

8,197点目まで、13セルの圧力と流入は対照と一致した。8,198点目の枝2の流量は `0.1043749118920781` cm³/s、セル1の圧力は `4.1859964029261265` dyn/cm² で上流と一致した。末端のセル12の更新後圧力は、観測した52点すべてで上流とビット一致した。

| 観測点 | 上流との初差 | 置換による検算 |
| --- | ---: | --- |
| 肺ポートの流量 | 内部8,202 | 境界圧、下流圧、前回流量、慣性、抵抗は一致。持ち越し圧を `66.24929681515725` から上流の `66.24929681515727` dyn/cm² に替えると上流の `1.150224455155536` cm³/s を再現 |
| 気管入口の更新後圧力 | 内部8,207 | 肺ポートの流入だけを上流値に替えると入口圧を再現 |
| 声門枝の流量 | 内部8,217 | 左右圧、持ち越し圧、駆動圧が一致。抵抗を `408.97377106687344` から上流の `408.9737710668735` dyn·s/cm⁵ に替え、線形係数を再計算すると上流の `8.535131922566455×10⁻⁶` cm³/s を再現 |

枝1だけの対照では、声門流量の差が8,212点目に出ていた。12本を揃えた版では8,217点目に移り、その点で差が残る項を線形係数まで切り分けた。肺境界圧は全52点で一致した。気管の枝1〜5の初差は8,222点目以降、枝6〜12は52点すべてで一致した。[全時系列の初差](../runs/fixed-voice-tracheal-series-momentum-48000-a/summary.json)・[抵抗と持ち越し圧の十進検算](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-series-residuals-48000.json)

| 固定上流とのPCM比較 | 枝1のみ | 直列枝12本 |
| --- | ---: | ---: |
| ビット差のある出力フレーム | 10 | 16 |
| 最初に差が出た出力フレーム | 62,275 | 61,467 |
| 最大絶対差 | 1.1368684×10⁻¹³ | 2.2737368×10⁻¹³ |

どちらの版も差はゲート停止（出力54,656フレーム目）後に限られ、既存の許容差 `5×10⁻⁷` 以内だった。両版の全93,056フレームで、128・77の分割はビット一致した。この条件では気管末端圧の観測区間が上流と一致しても、停止後のPCMのビット差は増えた。次は肺ポートで同じ持ち越し換算を試す。声門のスリット抵抗も候補として記録し、肺ポートとは別の変更で測る。

## 実行と検証

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_tracheal_series_momentum.py fixed-voice-tracheal-series-momentum-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_tracheal_series_momentum.py" \
  fixed-voice-tracheal-series-momentum-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、各10判定と上流の各15試験に合格した。各実行につき節点1,352点、気管枝1,352点、声門枝104点の更新を有理数・十進数で再計算した。2回の実行でPCM、計測CSV、差分、要約を含む20出力がバイト一致した。366入力と52出力をハッシュ照合し、採取物13,455,314バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/fixed-voice-tracheal-series-momentum-48000-a/manifest.json)・[再実行マニフェスト](../runs/fixed-voice-tracheal-series-momentum-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-tracheal-series-momentum-48000.json)
