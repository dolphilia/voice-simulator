# 固定 /i/ の声門上の枝損失を閉じた範囲で照合する

固定 /i/ で口蓋帆ポートだけを0.30 cm²にした前回の通常発声では、口腔・鼻腔・ポートの損失を離散モデルに戻したところ、2,310 Hzの鼻端に0.185%の複素誤差が残った。今回は同じ収録を使い、咽頭内、咽頭口腔接続、梨状窩の二次損失を加えると、その誤差が90%以上減ると事前登録した。上顎洞ポートも接続範囲に含め、二次係数がゼロの対照として圧力収支を測る。 [前回の測定](fixed-vowel-i-velum-oral-nasal-loss.md#実測)・[事前登録](../cases/fixed-vowel-i-velum-supraglottal-loss.json)

固定上流の `HumanAirway` は咽頭末端と口腔入口を通常枝で結び、咽頭の声門上約2.6 cmから梨状窩を分岐させる。口蓋帆と上顎洞はポートで、上顎洞ポートは入口・出口の二次係数がともにゼロで、両側の半セル慣性も加えない。 `HumanVoice::render` が声門開口を渡すと、`AirwayNetwork::step` は前標本の節点圧と枝の運動量から当該標本の流量を解く。通常枝は上流側最小面積から下流平均面積への拡大と、その逆向きの係数の10%で損失を表す。定常狭窄の上流試験は、全セルと1/4セルの狭窄の流量をともにベルヌーイ近似に照合する。 [上流の分岐接続](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L150)・[上流の発声ループ](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371)・[枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L954)・[定常狭窄試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L92)

前回と同じく観測した声門流量を咽頭入口の体積流量源とする。声門枝自体はこの離散モデルから切り、入口につながる範囲の固定枝を両端の節点の対応で確かめる。枝流量の単位は cm³/s、圧力差と損失は dyn/cm²。幾何の係数を使う `K(U) U|U|` と、前標本の圧力差から慣性・粘性圧力を引いて求めた時系列を照合する。2,310 Hzの損失係数を全枝まとめて節点に戻す方法と、鼻端を読む転置方程式で枝ごとの寄与を求める方法も照合する。圧力や運動量が有限窓の前後で異なる分は端点項として記録する。 [前回の枝式と端点項](fixed-vowel-i-velum-oral-nasal-loss.md)・[研究版の接続](../crates/vocal-core/src/airway/human.rs#L222)

離散節点方程式を `A p = g + B N`、鼻端流量を `hᵀ p` と置いた。 `g` は正規化した声門流量、`N` は各枝の圧力源、`B` は枝インピーダンスの逆数を両端に符号を反転して入れた行列。 `Aᵀ z = h` を解くと、枝 `j` の鼻端への複素寄与は `(zᵀ B)ⱼ Nⱼ` になる。ここで転置は複素共役を取らない。直接の節点解と同じ振幅・位相が得られることを照合した。 [実装](../tools/measure_fixed_vowel_i_velum_supraglottal_loss.py)

## 実測

400〜500 msの9,600内部標本を解析した。直前1標本は枝の圧力差と端点項の計算に用いた。到達範囲は61枝で、口蓋帆1、口腔17、鼻腔21、咽頭17、咽頭口腔接続1、梨状窩入口1、梨状窩内2、上顎洞ポート1だった。時間領域の圧力収支は相対6.36×10⁻¹⁴以下、2,310 Hzの圧力収支は7.67×10⁻¹³以下。上顎洞では前標本圧から逆算した損失がゼロに設定した二次係数と許容差内で一致した。梨状窩内の3節点はいずれも最小面積と平均面積が0.90 cm²で、両方向の拡大損失はゼロだった。

| 戻した圧力源 | 鼻端の複素相対誤差 |
| --- | ---: |
| 前回の口蓋帆・口腔・鼻腔の二次損失 | 1.85413×10⁻³ |
| 声門上の全二次損失 | 2.58845×10⁻⁸ |
| 全二次損失と全61枝の端点項 | 1.31306×10⁻⁸ |

二次損失だけで前回の残差が99.9986%減り、事前の90%基準を両版で満たした。前回の残差方向への射影は咽頭内96.94%、梨状窩入口2.62%、咽頭口腔接続0.44%。今回追加した枝では、咽頭の節点22→23が鼻端に最も大きく寄与した。前回の50%仮説が不成立だった記録も再照合した。 [枝ごとの複素寄与と判定](../runs/fixed-vowel-i-velum-supraglottal-loss-20261124-repeat/summary.json)・[前回の判定](../runs/fixed-vowel-i-velum-oral-nasal-loss-20261124-repeat/summary.json)

この照合は、固定 /i/ の同じ発声・窓で観測した枝流量を入力とした。枝の端点項まで入れて残る1.31×10⁻⁸については、節点・壁・放射の端点項を個別には測っていない。次は寄与が大きかった咽頭内の枝を平均流量のまわりで線形化し、観測した二次損失を時間ごとに入力した今回の結果と比較する。

## 再実行

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で実行した。両版の既存時系列を入力としてSHA-256で照合し、研究ワークスペースと `/tmp` からの2回の解析で、各14判定が通り、要約がバイト一致した。固定上流の `airway_adversarial` は6件とも通過した。新しい再実行には末尾の実行IDを変更する。 [初回マニフェスト](../runs/fixed-vowel-i-velum-supraglottal-loss-20261124-registered/manifest.json)・[再実行マニフェスト](../runs/fixed-vowel-i-velum-supraglottal-loss-20261124-repeat/manifest.json)

```sh
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_fixed_vowel_i_velum_supraglottal_loss.py fixed-vowel-i-velum-supraglottal-loss-20261124-repeat
```

第40版の全体監査は219実行・3,706成果・453判定を通過した。今回の3実行の1,353入力と12出力をSHA-256で照合した。声道の観測時系列は前回のRTL9210B-CG上の収録を参照した。今回の外部SSDの追加出力は9ファイル、計14,171バイトだった。 [第40版の実行記録](../runs/plan-completion-v40-fixed-vowel-i-velum-supraglottal-loss-20261124/manifest.json)
