# 口腔・鼻腔の二次損失で固定 /i/ の鼻端の残差を調べる

ポートだけを開いた固定 /i/ の400〜500 msで、前回は観測したポート損失を戻しても2,310 Hzの鼻端に0.268%の複素誤差が残った。今回は口腔内と鼻腔内の隣接節点間に絞り、各枝の観測流量から求めた損失を加えると、この誤差が50%以上減ると事前登録した。 [前回の実測](fixed-vowel-i-velum-mean-flow-tangent.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-oral-nasal-loss.json)

上流の `HumanVoice::render` は制御更新と声門開口の更新を行い、`AirwayNetwork::step` で枝流量、壁速度と変位、節点圧と放射の順に更新する。隣接節点 `a→b` をつなぐ普通枝は、左と右の半セルから慣性と粘性抵抗を求める。順方向の二次係数は `K₊ = E(a,b) + 0.1 E(b,a)`、逆方向は `K₋ = E(b,a) + 0.1 E(a,b)`。ここで `E(a,b) = ρ·max(1/A_min(a) − 1/A(b),0)²/2`。面積は cm²、流量は cm³/sで、二次損失 `K(U) U|U|` は dyn/cm² になる。圧力差には前標本の節点圧を用いるので、観測する標本の直前を1標本含める。上流の定常狭窄試験は、セル全体とその一部の狭窄で枝流量をベルヌーイ式に照合する。 [上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[上流の枝更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L947)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)・[研究版の枝モデル](../crates/vocal-core/src/airway/network.rs#L145)

固定形状の枝では、標本 `n` の流量 `Uₙ` が `L fs (Uₙ−Uₙ₋₁) + R Uₙ + K(Uₙ) Uₙ|Uₙ| = pₐ,ₙ₋₁ − pᵦ,ₙ₋₁` を満たす。2,310 Hzは100 msに231周期を含む。有限窓では遅延した圧力と流量にそれぞれ窓端の補正項が生じる。これらを含む圧力収支を照合した上で、損失の複素係数 `N` を枝インピーダンス `Z` で割った `+N/Z, −N/Z` を両端の節点方程式に入れる。枝ごとの応答を足し合わせた値と、圧力源をまとめて解いた値を比較する。観測流量を入力とする診断なので、適用対象は同じ発声と測定窓とする。 [圧力源の導出](fixed-vowel-i-velum-mean-flow-tangent.md)

## 実測

ポート1枝、口腔17枝、鼻腔21枝で、両版の圧力収支は時間領域で相対6.36×10⁻¹⁴以下、窓端項を含む2,310 Hz成分で7.67×10⁻¹³以下だった。独立した一括節点解と枝別の重ね合わせは事前許容差10⁻⁹以内で一致した。鼻端の誤差は観測した放射流量を声門流量で割った複素伝達を基準に求めた。

| 観測流量から求めた損失を戻す範囲 | 鼻端の複素相対誤差 |
| --- | ---: |
| ポート | 0.26786% |
| ポートと口腔 | 0.17413% |
| ポートと鼻腔 | 0.27890% |
| ポートと口腔・鼻腔 | 0.18541% |

誤差の低下は30.78%で、事前予測の50%には届かなかった。ポート損失を戻した後の残差方向への射影は、口腔が+35.09%、鼻腔が−4.11%だった。口腔で鼻端への複素寄与の絶対値が最大だったのは節点44→45で、47→48が続いた。調べた39枝の窓端項を加えたとき、鼻端の相対誤差の変化は0.00000036ポイントだった。残る0.18541%には未観測の損失と窓端の効果が含まれうる。次は同じ収録の咽頭内、咽頭から口腔への接続、梨状窩の枝を比較する。 [枝別の複素係数](../runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/summary.json)

## 観測の実装と再実行

通常CLIの `fixed_voice_probe` で `internal_trace: true` と `network_trace_range: [38399, 48000]` を指定し、`render` で節点圧と枝流量を保存した。9,601行の先頭1行は圧力差の時刻を合わせるための前標本。CSVの既存列は前回の同じ範囲と一致し、全PCMも保存済みの発声と一致した。従来の観測指定でも全65,536行のCSVが保存済みの出力とバイト単位で一致した。先頭・末尾の1標本を指定でき、空区間、範囲外、内部観測を省略した入力は `inspect` と `render` の両方で拒否した。固定上流は隔離ビルドの `HumanVoice::render` で `step` 直後の `p` と `u` を保存し、同じPCMと前回の既存観測を再現した。定常狭窄試験にも通過した。 [CLIの観測指定](../README.md)・[固定上流の計測パッチ](../runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/artifacts/upper-voice.patch)

初回は5本の接続枝が両版で別の配列位置にあり、同じ配列番号で比較した時系列の照合に失敗した。枝を有向節点対で対応づけると、全節点・全枝の時系列差は各列のピークに対して最大3.28×10⁻¹³だった。初回の生データおよび損失の観測値は再実行と一致した。初回の比較エラーと、対応づけを直した後も不成立だった50%仮説はそれぞれ保存した。 [初回の判定](../runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-registered/summary.json)・[対応の修正後](../runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-aligned/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。研究ワークスペースと `/tmp` からの再実行で、要約と10点の観測成果がバイト単位で一致した。以下のコマンドは研究ワークスペースから実行し、新しい再計測には末尾の実行IDを変更する。仮説が不成立のためCLIは終了コード1を返し、測定結果は `summary.json` に残る。 [再実行マニフェスト](../runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_oral_nasal_loss.py fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat
```

第39版の全体監査は216実行・3,694成果・447判定を通過した。今回の4実行の1,711入力と51出力をSHA-256で照合した。RTL9210B-CGの47出力パスのうち内容が同じものをハードリンクでまとめ、25ファイル、計50,909,366バイトになった。 [全体監査の実行記録](../runs/plan-completion-v39-fixed-vowel-i-velum-oral-nasal-loss-20261124/manifest.json)
