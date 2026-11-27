# 固定した励振周期と追加共鳴に対する窓内位相の比較

前回のF0比較では、25 ms窓に入る周期インパルスの間隔と位相が同時に変わった。追加共鳴760 Hz・F0 125 Hzの次数12、中央0.50秒の窓では、採択F1の約643.24 Hzと追加共鳴に近い公開極約841.73 Hzが198.48 Hz離れ、厳密に200 Hzを超える条件の直前にあった。今回は追加共鳴、励振周期、窓位置を固定し、1周期96標本の中で励振開始を1標本ずつ遅らせる。次数12では両方の採択が現れ、追加共鳴側が採られるときも設計F2近傍の極が残ると予測した。[先行比較](tsp-f2-intervening-excitation.md)・[実行前のケース定義](../cases/tsp-f2-intervening-phase.json)

固定上流のCLIエントリから `compare::tsp::run`、音素を照合する `measure_pair`、窓ごとに測る `Sig::formants` を辿った。`Sig::new` で48 kHz波形を4分の1に間引く。今回は合成信号を直接12 kHzで作り、その後段を観測する。母音区間の35・50・65%を中心に25 msの窓を切り出す。1秒の比較信号の窓開始は4050・5850・7650標本で、局所座標での励振位相は開始標本からパルス列の遅延を引いた96標本の剰余とする。窓の先頭標本を励振の標本と同じ位相で切る場合は0になる。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[TSPの計測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)

`analysis::lpc` は窓の中で `x[n] - 0.97 x[n-1]` を計算し、窓の前の標本は0として扱う。Hamming窓を掛けたのち、自己相関と40 Hzのラグ窓からLevinson–Durbin法で次数12または14の多項式を得る。Durand–Kerner法で求めた生根のうち上半平面の根を周波数・帯域幅（Hz）に変換し、150 Hz以上かつ帯域幅600 Hz以下を周波数昇順で公開する。TSPは1,300 Hz未満かつ帯域幅500 Hz未満で最も低い極をF1とし、F1より200 Hzを超えて上、かつ3,500 Hz未満で最も低い極をF2にする。窓ごとに前処理と根推定をやり直すため、定常波形の振幅スペクトルが等しくても候補は変わり得る。固定上流のTypeScript対照とTSPの音素照合と欠測処理の試験を動かし、同じ窓をToeplitz行列の直接解法と複素根で照合する。[LPC計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[LPC試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[TSP試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)

## 全96位相の実測

620・760・2075・2915 Hzの4共鳴を通した合成信号で、励振開始の96標本、3時刻、2次数の全576窓にF2が得られ、すべて設計F2の2075 Hzから120 Hz以内の極を選んだ。追加共鳴に最も近い公開極と採択F1との間隔は、次数12では位相93標本で最大199.305 Hzだった。位相だけで200 Hzをまたいで採択が入れ替わるという事前予測2件は外れた。先行のF0変更で見つかった切り替わりは、この固定F0・固定共鳴では位相を1周期すべて動かしても起きなかった。

| LPC次数 | 設計F2近傍を採択した位相 | 採択F2の範囲 | F1と追加共鳴近傍の公開極との間隔 |
| --- | ---: | ---: | ---: |
| 12 | 96 / 96 | 2052.48〜2114.56 Hz | 189.09〜199.31 Hz |
| 14 | 96 / 96 | 2034.69〜2084.30 Hz | 186.95〜195.97 Hz |

次は先行条件の中点780 Hzを1条件加え、次数12の200 Hz境界と採択の対応を同じ手順で測る。今回は鋭い周期パルスで測った。実録音のF2精度は、人が確認したF2と対応窓を照合して判定する。[全576窓と仮説の判定](../runs/tsp-f2-intervening-phase-20261123-repeat/summary.json)

## 再実行と保存

先行対照との遅延0の波形・上流の生根・公開極・採択は一致した。定常末尾96標本のDFTを、設計上の4対の極の複素伝達応答と励振の遅延因子に照合した最大相対誤差は9.08×10⁻¹⁵。同じ相対位相を3中心から切った窓同士の標本差は波形のピーク比で最大4.10×10⁻¹⁵で、全位相の採択分類も一致した。固定上流と独立計算の最大差は複素根で1.01×10⁻⁹、公開極の周波数・帯域幅で5.03×10⁻⁸ Hzだった。

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。各回で計測5判定、固定上流のRustとTypeScriptの基準1試験、TSP 6試験に合格した。2回目は `/tmp` から絶対パスで実行し、要約JSON、固定上流の出力、保存波形のSHA-256が初回と一致した。基準波形1本と観測窓を圧縮NPZに保存し、全96波形は登録ケースから再生成できる。出力の実体はRTL9210B-CGに保存した。[初回マニフェスト](../runs/tsp-f2-intervening-phase-20261123-a/manifest.json)・[再実行マニフェスト](../runs/tsp-f2-intervening-phase-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_intervening_phase.py tsp-f2-phase-new
```
