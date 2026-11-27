# 低域の追加共鳴とTSPのF2採択

実録音 `again` の中央窓では、プリエンファシスを外すと採択されたF1が620.18 Hzから440.98 Hzに変わり、708.24 Hzの極が先にF2の条件を満たした。1999.73 Hzの公開極も残っていた。比較には設計F2が既知の周期信号を使う。今回はF1・F2・F3を620・2075・2915 Hzに保ち、帯域幅140 Hzの共鳴を一つ追加して中心周波数を700〜1020 Hzで変える。[録音の実測](tsp-lpc-pre-emphasis-recordings.md#実測)・[事前登録](../cases/tsp-f2-intervening-resonance.json)

固定上流のCLIは `compare::tsp::run` から `measure_pair` で録音と合成の音素を対応させる。 `Sig::new` が48 kHzから4分の1に間引き、 `measure` が単母音を `Sig::formants` に渡す。母音の35・50・65%を中心とする25 ms窓は12 kHzで300標本。公開の `estimate_formants` は窓内で `x[n] − 0.97 x[n−1]` を計算し、Hamming窓を掛け、自己相関に40 Hzのラグ窓を掛ける。Levinson–Durbin法は次数ごとに予測係数と残差を更新し、多項式の根の角度と半径から周波数と帯域幅をHzで求める。150 Hz以上、幅600 Hz以下の極を周波数順に公開する。TSPは1300 Hz未満・幅500 Hz未満の最初の極をF1とし、推定F1＋200 Hzより高く3500 Hz未満の最初の極をF2に採る。両方を採れた窓の中央値を母音の値にする。[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L115)・[音素対応と計測](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[採択規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[上流LPC](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)

既知波形の極は `exp(−πB/Fs ± j2πf/Fs)` で置く。追加の有無を比較し、追加する条件では既存の3対を保持して中心周波数だけを動かす。固定Rustから得た根と公開極を、自己相関のToeplitz行列を直接解いた予測係数の根と照合する。設計F2の近傍に根が得られたか、公開条件を満たすか、選択されたF1からの間隔が200 Hzを超えるかを順に記録する。上流の基準試験は自己相関、予測係数と残差、複素根、包絡をTypeScriptの保存値と比較する。TSP側の試験は音素の対応と欠測の扱いも確認する。[基準信号の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[TSP側の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)

## 固定したF0での実測

125 Hzの周期インパルスを1秒流し、12次・14次の各3窓を測った。追加なし、700 Hz、760 Hzでは各6窓で設計F2の近傍を採った。800〜1020 Hzの6条件では各6窓で追加共鳴の近傍を採った。この36窓でも設計F2に対応する2046.89〜2093.28 Hzの公開極はF2の周波数条件を満たしていた。設計F2が選ばれなくなった段は、候補を周波数順に採択する処理だった。計測した周波数の刻みでは、6系列すべての最初の切り替わりが760〜800 Hzに入った。[全54窓の結果](../runs/tsp-f2-intervening-resonance-20261123-repeat/summary.json)

| 12次・中央窓 | 推定F1 | 追加共鳴近傍の公開極 | 推定F1との間隔 | 採択F2 |
| --- | ---: | ---: | ---: | ---: |
| 760 Hzを追加 | 643.24 Hz | 841.73 Hz | 198.48 Hz | 2070.32 Hz |
| 800 Hzを追加 | 650.25 Hz | 885.47 Hz | 235.22 Hz | 885.47 Hz |

800 Hzの設計極と設計F1の間隔は180 Hzだった。採択に使う推定極の間隔は6窓で217.78〜235.22 Hzとなり、200 Hzを超えた。760 Hzを追加した6窓の推定間隔は187.40〜198.84 Hzだった。この差が、設計周波数だけで予測する境界より低い周波数で採択が切り替わった理由になった。実録音の真のF2を判断するには、人手注釈との照合が残る。次の対照では、760 Hzと800 Hzの共鳴を固定し、F0だけを動かして追加極の推定間隔と採択を測る。[上流の生根と公開極](../runs/tsp-f2-intervening-resonance-20261123-repeat/artifacts/upstream-envelopes.json)

## 再現と検証

追加なしの波形と6窓の固定Rust出力は、保存済みの12000 Hz・F0 125 Hz・F2帯域幅180 Hzの条件とバイト一致した。独立したToeplitz解法とコンパニオン行列で全54窓の根を再計算し、複素平面上の距離は最大 `1.78×10⁻¹⁰` だった。設計伝達関数と定常1周期のDFTの相対差は最大 `5.32×10⁻¹⁵` だった。研究ワークスペースと `/tmp` からの実行で各4判定、固定上流のLPC基準試験1件とTSP試験6件に通過した。3仮説は両実行で支持され、要約、波形、上流の全観測がバイト一致した。macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で実行し、2回の採取物2,811,186バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-f2-intervening-resonance-20261123-a/manifest.json)・[再実行](../runs/tsp-f2-intervening-resonance-20261123-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-tsp-f2-intervening-resonance-20261123.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_intervening_resonance.py tsp-f2-intervening-resonance-new
```
