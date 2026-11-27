# 固定発声CLIで壁・口端・鼻端の放射を観測する

隔離ビルドで採取した放射の内訳を、通常の固定発声ケースから取得できるようにした。既存の `fixed_voice_probe` に `radiation_components: true` を設定すると、`render` のCSVに壁の放射流量 `wall_radiation_flow_cm3_s` と合算の `radiation_flow_cm3_s` が加わる。口端と鼻端は既存列 `lip_flow_cm3_s` と `nose_flow_cm3_s` で取得できる。任意の `internal_trace: true` と併用すると内部標本ごとの観測になり、省略時は各PCMフレームの最後の内部標本になる。既存の咽頭収支の観測とも併用できる。 [実行できる計測ケース](../cases/fixed-vowel-i-cli-radiation.json)・[前回の隔離ビルドによる観測](fixed-vowel-i-radiation-components.md)

## 気道からCLIへの受け渡し

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は声門面積を設定し、`AirwayNetwork::step` を呼ぶ。気道は枝流量、壁速度と変位、放射負荷を含む節点圧の順で進め、重み付き壁流量、口端流量、鼻端流量を足す。流量の単位はいずれも cm³/s。前標本からの合算流量差を内部時間幅で微分した値が出力段の入力（cm³/s²）になる。上流の一様管試験では、壁を使う条件と使わない条件でインパルス応答と周波数モデルのピークを照合する。 [上流の通常発声](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[壁と放射の合算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1053)・[差分の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1149)・[上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L68)

研究版のCLIは `render_fixed_voice` から `FixedVoice::step_source` を通る。口端・鼻端の流量と、気道がその標本で計算した壁・総流量を同じ `VoiceSample` から取得する。これら2つの値は既存の `NetworkSample` の値をそのまま書き出す。通常の `render-pcm` は同じ発声ケースで放射微分をFIR・間引き・直流除去・振幅制御へ渡す。96 kHzの固定発声から48 kHzのPCMへ間引く今回のケースでは、出力フレーム `k` は内部標本 `2k+1` に対応する。 [固定発声のCLI入口](../crates/vocal-cli/src/geometry_case.rs#L441)・[固定発声の標本](../crates/vocal-core/src/voice.rs#L215)・[壁と総放射の計算](../crates/vocal-core/src/airway/network.rs#L747)・[CSVの開き方と書き出し](../crates/vocal-cli/src/geometry_case/voice.rs)

## 照合する条件

肺圧3.6 cmH₂Oの無変更条件を使用し、観測の未指定、明示的な無効、出力フレーム刻み、内部標本刻み、咽頭入口の収支観測との併用を比較する。隔離ビルドの上流と研究版の壁・口端・鼻端・合算を基準とし、成分を実装と同じ順序で足して微分する。FIRと出力段からPCMを独立に作り、通常CLIの65,536内部標本の観測とブロックサイズ128・77の描画を照合する。 [事前に登録したケース](../cases/fixed-vowel-i-cli-radiation.json)・[照合スクリプト](../tools/measure_fixed_vowel_i_cli_radiation.py)

## 実測

通常CLIの全65,536内部標本で、壁・口端・鼻端・合算流量と放射微分が研究版の隔離計測にビット一致した。合算と微分を独立に再計算した値も通常CLIの観測にビット一致した。上流との誤差は流量で相対5.20×10⁻¹⁵以内、PCMで絶対2.33×10⁻¹⁰以内だった。放射微分から出力段を独立に計算すると、全32,768フレームのPCMにビット一致した。 [計測結果](../runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected-repeat/summary.json)

出力フレーム刻みの観測は全フレームで内部標本 `2k+1` の値と一致した。観測ありのCSVは壁と合算の2列を追加した。咽頭収支と併用しても、既存の7列と各値は維持された。観測の指定・無効・有効と、出力ブロック128・77の組み合わせでWAVと出力段のCSVは一致した。 `inspect` は観測を有効にしたケースで `voice.probe.radiation_components` を示した。 [標本の時刻と放射列](../runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected-repeat/artifacts/internal.csv)・[出力フレームのCSV](../runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected-repeat/artifacts/internal-pcm.csv)

初回の列構成判定では、検証コードが既存の咽頭収支を6列と数えていた。保存したCSVには従来の7列と新しい2列があり、流量・微分・PCMを含む残る10判定は成立した。既存7列を列名で照合するよう検証を修正し、初回の全出力と再描画の出力がバイト一致したことを確認した。 [初回の判定](../runs/fixed-vowel-i-cli-radiation-20261124-registered/summary.json)・[修正後の判定](../runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected/summary.json)

## 実行記録

macOS 15.6.1 arm64、Rust/Cargo 1.94.1、Python 3.14.4、NumPy 2.4.4で研究ワークスペースから実行した。再実行は `/tmp` からPythonとスクリプトを絶対パスで指定し、実行IDの末尾を `repeat` にした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 ../../.venv/bin/python \
  tools/measure_fixed_vowel_i_cli_radiation.py fixed-vowel-i-cli-radiation-20261124-schema-corrected
```

修正後の両実行で11判定に通過した。初回を含む3実行のCSV、WAV、ケース、`inspect` の出力を元の実行別パスからSHA-256で照合し、同じ内容はRTL9210B-CG上で実体を共有した。 [初回マニフェスト](../runs/fixed-vowel-i-cli-radiation-20261124-registered/manifest.json)・[修正後のマニフェスト](../runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-cli-radiation-20261124-schema-corrected-repeat/manifest.json)

第32版の全体監査は188実行・3,090成果・395判定に通過した。研究版のRustテスト52件、固定上流のテスト、Webのビルドも通過した。描画3実行と全体監査の1,422入力・90出力は、それぞれのマニフェストとSHA-256で一致した。 [全体監査の要約](../runs/plan-completion-v32-fixed-vowel-i-cli-radiation-20261124/summary.json)・[監査マニフェスト](../runs/plan-completion-v32-fixed-vowel-i-cli-radiation-20261124/manifest.json)
