# 固定声道の圧力結合とLF体積流量の比較

## 上流の更新と境界の条件

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7` の `HumanVoice::render` は、内部サンプルごとに前回の肺流量から境界圧を補正し、声門前後の節点圧差を `ParametricGlottis::next` に渡す。声門モデルは圧差、発声係数、振幅、開大、閉鎖、位相を更新して開口面積を返す。肺・音高・声門の設定をそろえるため、既存の固定母音と同じ `set_source` を使い、ドリフト、ジッタ、シマーと乱流を止めた。[上流の発声とPCM化](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[声帯の `next`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs#L151)・[通常発声と圧差固定の読解](glottal-pressure-feedback.md)

`AirwayNetwork::step` は、前の圧力と枝の運動量を使い、声門スリットを含む各枝で `L U/Δt + R U + K U |U| = Δp + m₀/Δt` を流向ごとに解く。ここで `L` は慣性、`R` は粘性抵抗、`K` は流向で決まる損失係数、`m₀` は面積変化を考慮した前の運動量。流量 `U` の単位は cm³/s、圧力は dyn/cm²、面積は cm²。気管末端から咽頭入口へ正の流量を与える場合、気管の収支から `U` を引き、咽頭の収支に同じ `U` を足す。その後、前の圧力で壁の速度と変位を更新し、放射負荷や圧縮性を含めて新しい節点圧を求める。口端・鼻端・重み付き壁流量の和をサンプル間で差分し、総放射を cm³/s² で観測する。間引き、直流除去、リミッタを通った48 kHzのPCMまでを照合する。[枝の収支から放射まで](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1027)・[上流の肺ポート試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs)・[声門の閉じ方と高域を測る試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/voice_source.rs)

固定駆動では、同じ枝の更新位置で指定値を両節点の収支に加える。声門枝の面積は0に設定し、その枝の流量は指定値で上書きする。声門の両端はこの固定声道で分岐節点のコンプライアンス下限の対象外で、他の枝や肺・壁・放射の系列を固定して比較できる。残している声帯の面積・発声係数の列は並行計算の観測値である。 `inspect` は `glottal_area_drives_port` で面積が駆動に使われるかを示す。固定上流は `git archive` で一時展開し、同じ枝を選ぶ差分を加えた。[候補の枝更新](../crates/vocal-core/src/airway/network.rs)・[候補の固定発声](../crates/vocal-core/src/voice.rs)・[上流の計測差分](../runs/fixed-lf-glottal-flow-20261121-b/artifacts/upstream-fixed-flow.patch)

## LF形状と事前登録

LFの二つの区間は、開口相の指数付き正弦波と、有限の戻り相の指数関数で流量の微分を表す。旧実験の位相係数 `Tp=0.4, Te=0.6, Ta=0.05, Ee=1` を用いた。戻り相の `ε` は `1−exp(−ε(1−Te))=εTa` を解き、開口相の `α` は一周期で微分の積分が0になるように決める。周期位相で解析積分して積分定数を `U(0)=0` とし、位相 `((n+1)×110 mod 96000)/96000` で標本化した。得られた無次元の流量を cm³/s に換算する尺度は、定常窓で通常条件と平均流量が一致するよう一度だけ計算した。波形は初めの50 msで `sin²` の包絡に沿って立ち上がる。微分形を別に数値積分して、解析積分の結果を照合した。[LF原論文](https://www.speech.kth.se/qpsr/1985/1985_26_4_001-013.pdf)・[固定LF係数の独立検算記録](../../autonomous-research-cycle/campaigns/nas-lf-source-mechanism-20261008-v1/fixture-audit.json)・[以前の放射付き波動管実験](../../autonomous-research-cycle/campaigns/nas-radiated-waveguide-mechanism-20261009-v1/report.md)

成人男性の固定 /ɑ/、閉じた軟口蓋、通常時の肺圧7.2 cmH₂O、F0 110 Hzを共通条件とした。通常の圧力結合、通常流量のサンプル単位の再入力、固定LFの三条件を0.6秒ずつ実行。定常窓は0.4〜0.6秒の22周期。通常流量を再入力すると節点圧からPCMまで一致すること、LFでは声門流量のH1−H2が1 dB以上変わり、口端流量と総放射の交流RMSがともに5%以上変わることを事前登録した。F0は流量から推定し、最大絶対誤差0.05 Hzで判定する。[ケースと判定基準](../cases/fixed-lf-glottal-flow.json)・[固定姿勢と呼気設定](../cases/vowel-voice-alpha.json)

## 結果

| 定常窓 | 通常の圧力結合 | 固定LF |
| --- | ---: | ---: |
| 推定F0 Hz | 110.000056 | 110.000056 |
| 声門流量の平均 cm³/s | 139.886 | 139.886 |
| 声門流量の交流RMS cm³/s | 146.308 | 146.089 |
| 声門流量のH1−H2 dB | 7.79 | 10.37 |
| 口端流量の交流RMS cm³/s | 149.962 | 145.683 |
| 口端流量の差分の交流RMS cm³/s² | 201,930 | 138,789 |
| 総放射の交流RMS cm³/s² | 206,436 | 141,188 |
| PCMの交流RMS | 0.11299 | 0.07677 |

**口端流量の交流RMSは2.85%低下し、5%の判定を満たさなかった。** 総放射の交流RMSは31.61%低下し、声門流量のH1−H2には2.57 dBの差が出た。口端流量の第1倍音は186.85から194.82 cm³/sへ増え、第3倍音は31.28から12.63 cm³/sへ低下した。差分だけを計算しても口端で31.27%低下するため、口端流量の高次成分の変化が、放射で見えた交流レベルの差に寄与している。差分は周波数の上昇に従って、今回の倍音帯域では大きな重みを与える。総放射から口・鼻の差分を引くと、壁の寄与の交流RMSは5,672から3,761 cm³/s²だった。鼻端流量は両条件で0。これらはモデル内部の観測値で、校正したマイク音圧や聴取による差は別に検証する。[初回の全判定](../runs/fixed-lf-glottal-flow-20261121-a/summary.json)・[差分と12倍音を含む再計測](../runs/fixed-lf-glottal-flow-20261121-b/summary.json)

ビット差は内部サンプル1で声門流量と声門前後圧、2で総放射、36で口端流量に初めて出た。総放射が口端より先に変わる時点では、壁の項が差を伝えている。48 kHzのPCMの最初の差は出力フレーム1。ピークの10⁻⁹を検出下限にした場合の時刻も要約に保存した。通常流量の再入力では、それぞれの実装のまま節点圧・流量・放射・PCMが完全一致した。各条件の上流との比較でもPCMが完全一致し、内部系列の最大ピーク相対誤差は3.60×10⁻¹³未満だった。LFの流量の解析積分と独立数値積分は最大2.28×10⁻¹³ cm³/s以内で一致した。[差が生じたサンプルと再入力の判定](../runs/fixed-lf-glottal-flow-20261121-b/summary.json)

2026-11-24の追加計測で、同じ22周期の両条件を再描画し、壁からの放射を直接採取した。口端流量の基本波だけを通常発声に置き換えるとRMSの低下は6.40%。総放射の交流平均二乗の減少の94.85%は口端差分の自己項で、5.07%が口端と壁の交差項だった。 [倍音電力の分解](fixed-lf-radiation-harmonic-budget.md#観測結果)

## 実行、保存、次の比較

通常の `vocal-cli inspect`、`render`、`render-pcm` を使う。 `fixed_voice_probe.internal_trace` で `render` の全内部サンプルを記録する。 `fixed_voice_probe.prescribed_flow_cm3_s` に有限の十進数文字列を内部サンプルの個数分並べる。長さが違う列、無限大、NaN、数値型の要素は出力を作る前に拒否し、負の流量は指定した符号で計測できた。ホストブロック77と128でPCMと出力段の観測が一致した。候補41試験、上流の声門・肺ポートの5試験、ClippyとWASMのコンパイル検査にも通過した。[以前の固定母音の合格実行](../runs/vowel-voice-alpha-20261119-f/manifest.json)・[再計測のコマンド、環境、出力](../runs/fixed-lf-glottal-flow-20261121-b/manifest.json)

```bash
cd /Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=250000000 ../../.venv/bin/python tools/measure_fixed_lf.py fixed-lf-glottal-flow-local-1
cargo test --workspace --locked
```

初回の判定は保持し、再計測でも同じ5%基準を使った。判定に使った全長のCSVは再計測で可逆圧縮し、入力・PCM・上流の内部系列とともに作業用ディスクに保存した。出力は初回の85.97 MBに対して再計測は43.94 MB。全39出力をハッシュ照合し、別の作業ディレクトリで再計測した32点の入力・音声・観測ファイルが圧縮展開後に前回と一致した。比較を広げるなら口端流量の交流RMSだけで結論を出さず、同一一様管・同一の終端インピーダンスで口端流量の複素伝達を照合する。口端の流量を遠方の音圧へ換算する場合は、音源の単位・放射位置・距離を固定した別ケースで扱う。[既存の一様管実験](../../autonomous-research-cycle/campaigns/nas-waveguide-tract-mechanism-20261008-v1/report.md)・[既存の理想開口観測](../../autonomous-research-cycle/campaigns/nas-volume-velocity-observer-20261009-v1/report.md)
