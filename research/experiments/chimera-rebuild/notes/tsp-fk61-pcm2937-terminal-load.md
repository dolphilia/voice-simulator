# FK61_01の口端標本5863・5864を作る入力

[前の区間走査](tsp-fk61-pcm2937-lip-window.md)では、下唇内面の三次ベジェ評価順を上流に揃えた試験版の口端流量を内部標本5863・5864だけ交換すると、冒頭から出力2937まで上流のPCMと一致した。今回はその2標本と直後の5865について、口端の負荷が受け取る入力を調べる。発話、声体、クロック、出力ゲインは前の計測から引き継いだ。口端の2節点は42・43、口端は43。口端放射の単位は cm³/s、圧力は dyn/cm²。内部96 kHz、出力48 kHz。

## 呼び出し経路と状態更新

上流の通常テキストCLIは [`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) でスコアの制御、肺圧の補間、声門面積を更新した後、内部標本ごとに [`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L827) を呼ぶ。口端節点の正味流入は初期流入を受け取り、枝42→43を足し、壁が外向きに動く流量を引いて作る。枝の計算は前の節点圧と枝の流量・慣性・運動量を参照する。壁は前の圧力・壁速度・壁変位を使う。節点42は `p' = p + Δt q/C` で圧力を更新する。

節点43ではコンプライアンス `C = V/(ρc²)` と並列の放射抵抗 `R`・慣性 `L` をCrank–Nicolson法で連成させる。負荷の慣性が前の標本より増えた場合、過去の慣性流量 `u₀` に `L₀/L` を掛けて運動量を保存してから連成式に渡す。面積 `A` を使う負荷の比例関係は `L ∝ A⁻¹ᐟ²`、`R ∝ A⁻¹`。口端の放射流量は抵抗枝と慣性枝の時間中点で評価する。 [上流の口端負荷](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1129)・[研究版の負荷と面積更新](../crates/vocal-core/src/airway.rs#L60)・[研究版のネットワーク更新](../crates/vocal-core/src/airway/network.rs)

\[
h=\Delta t/(2L),\quad g=1/(2R),\quad a=C/\Delta t,\quad
p'=\frac{p(a-h/2-g)+q-u_0}{a+h/2+g},\quad
u'=u_0+h(p+p'),\quad
u_{\mathrm{lip}}=(u_0+u')/2+g(p+p').
\]

上流は `C × 96000` と `(a ± h/2) ± g`、研究版は `C / Δt` と `a ± (g + h/2)` の順で評価する。観測器は各版の演算順を独立に再計算する。放射出力は `(全壁 + 口端) + 鼻端` を差分化し、FIR・ゲイン・DC除去・リミッターを経てf32にする。 [R–Lの独立計算](../tools/measure_fixed_voice_release_lip_load.py#L100)・[出力段の独立計算](../tools/measure_tsp_fk61_pcm_first_difference.py#L29)

通常CLIの再描画に加え、固定上流の `uniform_tube_resonances_match_quarter_wave_theory`、`fdtd_impulse_response_agrees_with_frequency_domain_model`、`sealed_cavity_compression_follows_the_linearised_adiabatic_law` を含む `airway` と `airway_adversarial` を実行する。研究版と試験版では `immediate_port_update_keeps_other_geometry_ramps_active` で声門の即時面積更新中にも他の目標値の補間が進むことを確かめる。 [固定上流の管の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[固定上流の密閉腔の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の幾何補間の試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 事前登録

5863〜5865で、現在の正味流入より旧圧と旧慣性流量を合わせた交換の影響が大きく、負荷係数だけの交換は小さいと予測した。正味流入の内訳では枝42→43の差が体積源と壁流量の差を上回ると予測した。単標本では試験版の式に上流の入力を4群の全組合せで入れる。逐次計算では5856から状態を進め、初期履歴・正味流入系列・負荷係数系列を組み合わせ、5863・5864だけを以前の出力段へ戻す。節点42・43の観測値の検算と、2標本を交換したPCMの対照は合否条件として先に登録した。 [ケース定義](../cases/tsp-fk61-pcm2937-terminal-load.json)

## 実測

各版で通常CLI、観測版、保存済み比較の全116,132フレームがビット一致した。観測した40内部標本の枝・壁・節点・負荷を、各版の入力から再計算した。放射負荷だけを5856から進めた16標本でも旧状態と更新結果はビット一致した。

下表はいずれも cm³/s。口端差と枝の差は上流から試験版を引いた値。交換の4列は試験版に上流の入力を1群ずつ入れたときの口端流量変化。

| 内部標本 | 口端差 | 枝42→43の差 | 正味流入を交換 | 旧圧を交換 | 旧慣性流量を交換 | 負荷係数を交換 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5863 | −2.9431×10⁻¹¹ | −2.8638×10⁻¹¹ | −8.3524×10⁻¹² | +3.7303×10⁻¹³ | −2.1451×10⁻¹¹ | 0 |
| 5864 | −2.9061×10⁻¹¹ | −2.8287×10⁻¹¹ | −8.2565×10⁻¹² | +3.9790×10⁻¹³ | −2.1203×10⁻¹¹ | 0 |
| 5865 | −2.8699×10⁻¹¹ | −2.7995×10⁻¹¹ | −8.1712×10⁻¹² | +4.1211×10⁻¹³ | −2.0947×10⁻¹¹ | 0 |

5863では旧慣性流量と旧圧を同時に交換すると −2.1075×10⁻¹¹ cm³/s 動いた。正味流入の単独交換の約2.52倍で、旧慣性流量単独よりわずかに小さかった。枝42→43は正味流入差の約97.4%を占め、口端の体積源差は −7.50×10⁻¹³ cm³/s、壁流量を差し引く項の差は +1.24×10⁻¹⁵ cm³/sだった。この区間の放射抵抗と慣性は両版で等しく、コンプライアンスの差は約1.2×10⁻²¹ cm⁵/dynだった。負荷入力を4群とも交換すると、各標本で研究版の演算順のまま上流の口端流量に着地した。

5856から正味流入系列を交換し、得られた5863・5864の口端放射を試験版の出力段に入れると、冒頭から2937までPCMが一致した。2937のf32変換前は 2.4556801494487656×10⁻⁶ で、上流の口端値を直接入れた 2.4556801514453176×10⁻⁶ より約2.00×10⁻¹⁵ 小さい。5856の初期履歴だけを交換したときの変化は +2.00×10⁻¹⁵ で、2937のPCM差が残った。初期履歴・流入・負荷係数をすべて交換すると、2標本の口端流量と2937の変換前の値も直接交換と一致した。

単標本の旧慣性流量には、直前までに運ばれた差が含まれる。短区間の流入系列を交換すると、その差自体が小さくなる。枝42→43の差が先にどこから生じたかを追うには、5856の状態から同じ区間で枝の圧力差・運動量・慣性・損失を個別に交換し、口端の負荷と組み合わせる。

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、Rust 1.94.1、Python 3.14.4を使用した。実行コマンドの全引数と環境はマニフェストで確認できる。観測系列、枝・壁のCSV、テストログはRTL9210B-CGの `voice-simulator/scratch/chimera-runs/` にあり、ワークスペース内の実行ディレクトリから参照できる。

初回は3072フレームの出力と2937までの2938フレームをそのまま比較して集計が停止した。次の実行では変換前値の列番号が保存データと独立計算で異なり、PCM対照の判定が不合格になった。比較長と変換前の列を揃え、両方の採取データを保持した。 [初回マニフェスト](../runs/tsp-fk61-pcm2937-terminal-load-20261123-native/manifest.json)・[2回目の判定](../runs/tsp-fk61-pcm2937-terminal-load-20261123-repeat/summary.json)・[修正後の実行](../runs/tsp-fk61-pcm2937-terminal-load-20261123-certified/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_pcm2937_terminal_load.py tsp-fk61-pcm2937-terminal-load-new
```
