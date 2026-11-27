# 同じ /i/ の声門流量・放射・PCMを時系列で照合する

先行比較では `seems` の母音中央1.165秒の声道断面が両版で一致し、断面を固定した線形ピークは2,187.47 Hzだった。同じ窓のPCMには2,228.15 Hzと2,212.45 HzのLPC極が残った。今回は元のLPC窓と同じ1.1525〜1.1775秒を取り、声門流量、口端・鼻端・壁の放射流量、総放射流量の差分、間引き後の放射、DC除去後、PCMを比較する。声門流量から高域のパワー分布が分かれていることと、間引き直後にはPCMとほぼ同じ版間の極差が現れることを予測した。上流・研究版それぞれの通常音源設定を使う。[事前登録](../cases/tsp-seems-spectrum-stages.json)・[先行の断面比較](tsp-seems-tract-transfer.md)

固定上流の `compare tsp` は `render::say` を使い、男性の基準F0 112 Hz、50 msの計画開始、300 msの終端を渡す。 `HumanVoice::render` は内部96 kHzで、制御カウンタの更新、声門両側の節点圧の取得、`glottis.next` の開口算出、ポート面積の設定、気道の流量・圧力更新の順に進む。観測する声門流量はその気道更新直後の `net.u[gp]` で、口端・鼻端は放射負荷で更新された `rad_u` を読む。壁の放射流量を加えた総流量と前標本の総流量との差を内部レート倍し、出力用の時系列を作る。流量はcm³/s、時間微分はcm³/s²。声門は圧差の影響を受けるので、声門流量で差が観測されても音源設定だけを原因とするには別の対照がいる。[上流の発話](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[上流の描画](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[気道の放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1070)

放射差分はKaiser窓付きのFIRで2標本に1回出力され、固定ゲイン、25 HzのDC除去、ピーク保持・リリース、ソフトクリップを経て48 kHzのPCMになる。FIRやDC除去の履歴を保持するため、描画開始から窓末尾の後までを独立に再計算してから切り出す。5 Hz刻みのFFTは直接フーリエ和と照合する。高域の分布は帯域内の各ビンのパワーをその帯域の総和で割り、両版の絶対差の和の半分を測る。LPCは先行TSPと同じ低域通過、12 kHzへの間引き、25 ms・次数14で比較する。固定上流のブロック分割、解析のTypeScript由来の基準試験にも通す。[出力段の読解](duet-child-output-gain.md)・[上流のブロック試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)・[LPC基準](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L187)

## 高域差を確認した観測段

48 kHzのフレーム55,320〜56,519と、それに対応する96 kHzの2,400標本を測った。1950〜2600 Hz内で正規化したパワー分布の全変動距離は、声門流量0.2053、口端放射0.0958、総放射0.0915、PCM 0.0945だった。登録した0.1を最初に超えた観測点は声門流量だった。パワーの相対差は、200〜4500 Hzの総パワーに占める高域の割合で、声門流量では研究版が上流より1.00 dB高く、PCMでは0.13 dB低かった。この距離は高域内のパワーの配分を表し、後段で差が単調に増えることは仮定していない。5 Hz間隔はゼロ詰めした周波数表示の刻みである。

| 観測段 | 固定上流の高域LPC極 | 研究版の高域LPC極 | 研究版 − 固定上流 |
| --- | ---: | ---: | ---: |
| 放射の間引き直後 | 2,228.15 Hz | 2,212.41 Hz | −15.74 Hz |
| DC除去後 | 2,228.15 Hz | 2,212.45 Hz | −15.70 Hz |
| PCM | 2,228.15 Hz | 2,212.45 Hz | −15.70 Hz |
| 共通の出力段で再計算したPCM | 2,228.15 Hz | 2,212.45 Hz | −15.70 Hz |

二つの仮説が成立した。通常描画の先頭から56,600フレームまで、各版の放射差分を共通の独立計算へ入力すると、それぞれのPCMがビット一致した。この区間ではリミッター・ソフトクリップは作動しなかった。最終PCMの高域LPC差は出力段の違いを加えず、すでに異なる放射差分から再現できる。この観測では声門への圧差、音源設定、声道との動的な相互作用の寄与は分けていない。次は上流のドリフトのみを止め、同じ母音窓で声門流量の高域差とLPC差を測る。[全観測段の要約](../runs/tsp-seems-spectrum-stages-20261123-repeat/summary.json)

## 検証と再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。両版の通常CLIと観測付き描画が保存済みの各116,132 PCMフレームに一致した。総放射流量の和の最大差は2.28×10⁻¹³ cm³/s、放射の差分の最大誤差は1.17×10⁻¹⁰ cm³/s²。FFTと直接フーリエ和の最大相対差は1.27×10⁻¹⁴だった。固定上流のLPC基準とブロック試験を含む計8試験、研究版の17試験を通過した。計測4判定は別作業ディレクトリから再実行しても通過し、窓波形・スペクトル・LPC極・要約がバイト一致した。窓のNPZ、スペクトル、ログの実体はRTL9210B-CGに保存した。[初回のマニフェスト](../runs/tsp-seems-spectrum-stages-20261123-a/manifest.json)・[再実行のマニフェスト](../runs/tsp-seems-spectrum-stages-20261123-repeat/manifest.json)

間引き前が倍精度の観測値にも同じTSPの低域通過を適用できるよう、WAV読込と間引きを分離した。従来の候補レポートが使った12波形は、分離前に相当する式と波形バイトが一致した。SciPyはその照合時に録音の非音声チャンクを読み飛ばした。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_seems_spectrum_stages.py tsp-seems-spectrum-stages-new
```
