# 固定母音 /i/ の中心線の演算順と描画

## 読解と予測

固定上流の `HumanVocalTract::compute` は、喉頭蓋基部を `p(0.3, 2.4)` に喉頭の移動を加えて求める。成人男性の咽頭係数は1で、上流では `7 − (7 − 2.4) × 1` の順に計算する。研究版の `BodyParameters::point` は係数1でその変換を省き、基部を `2.4 + larynx` から作る。後壁のテンプレート節点と区間分割は同じで、上流の `catmull_rom` は3次の単項式を加え、研究版の `template_spline` は隣り合う節点位置と接線をHermite基底で加える。どちらの式も幾何学的には同じ曲線を表す。各座標はcm。基部と後壁が格子の内外端を決め、その中点をつないだ積算距離から咽頭端の位置が得られる。[基部の座標変換](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs#L696)・[上流の後壁補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/geom.rs#L192)・[研究版の補間](../crates/vocal-core/src/anatomy.rs#L578)・[前回の座標置換](fixed-voice-centerline-i.md#喉頭蓋と後壁の二つの丸め)

上流の `HumanAirway::commit` はこの長さと断面を等長セルへ割り当てる。固定姿勢の研究版では通常CLIの `inspect` と `render_fixed_voice` が同じ気道を構築し、咽頭セル0のコンプライアンスを `C = A × dx / (ρc²)` で求める。内部96 kHzでは、壁・流入・流出を加えた流量に `dt / C` を掛け、前の圧力に加える。PCMは48 kHzへ間引く。この伝搬を、座標と輪郭を検査する上流の `geometry_matches_typescript` および操作の適用時刻を揃えたブロック分割試験と対応させる。[上流の管長と断面](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L232)・[通常CLIでの気道構築](../crates/vocal-cli/src/geometry_case.rs#L367)・[幾何の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_geometry.rs#L15)・[分割の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs#L78)

前回の保存座標からは、基部Yと後壁を同時に上流へ揃えたときだけ測定線7の積算と咽頭全長が一致した。隔離した実験用ソースで基部Yの1点と咽頭後壁だけを個別に差し替え、同じ前段から計算した場合の予測として登録する。咽頭全長が一致すれば、内部8,205点目で最初に見えた圧力差も消えると予測した。その後の圧力残差やPCMは、旧版と同じゲート時刻を使って実測する。[事前登録](../cases/fixed-voice-centerline-render-48000.json)・[圧力差をコンプライアンスで復元した条件](fixed-voice-pharynx-onset-48000.md#最初の差はセル長から圧力へ伝わる)

## 幾何から声門上圧とPCMまでの結果

作業用ディスク上の隔離ソースで、標準、喉頭蓋基部Yだけ、後壁の式だけ、両方の4通りをビルドした。喉頭蓋の差分は基部1点に適用し、後壁の差分は咽頭後壁の生成に適用した。各版を通常の `geometry`、`area`、`inspect`、`render`、`render-pcm` で実行した。標準の輪郭・断面・内部圧力・全PCMは保存済みの基準とバイト一致した。[基部の差分](../runs/fixed-voice-centerline-render-48000-c/artifacts/epiglottis.patch)・[後壁の差分](../runs/fixed-voice-centerline-render-48000-c/artifacts/posterior.patch)・[4条件の結果](../runs/fixed-voice-centerline-render-48000-c/summary.json)

両変更で測定線7の積算と線19の咽頭全長が上流に一致した。全長は8.092899222322227 cmから8.092899222322226 cmへ、セル長は0.44960551235123486 cmから0.44960551235123475 cmへ変わった。内部8,205点目の声門上圧は、両変更で約4.787924008824975×10⁻¹³ dyn/cm²の上流値に一致した。単独変更の各版では咽頭全長・セル長・この点の圧力は標準と同じだった。独立計算は、各版の内部8188〜8239点の圧力をビット一致で復元した。[保持した観測点](../runs/fixed-voice-centerline-render-48000-c/summary.json)・[両変更の内部CSV](../runs/fixed-voice-centerline-render-48000-c/artifacts/combined/internal.csv)

両変更で残った声門上圧の最初の差は内部8,210点目だった。壁流出はそれ以前の8,206点目で分かれ、8,210点目では声門流入も約1.917196516622917×10⁻⁹ cm³/sの付近で異なった。この点の前回圧・コンプライアンス・咽頭セル1への流出・断面移動由来の流量は一致していた。圧力収支に声門流入の上流値だけを入れると上流圧を復元した。次の比較では、8,210点目で声門枝へ渡った圧差、前回流量、慣性、粘性抵抗、非線形損失を採り、最初に差が生じる項を切り分ける。[残った項と置換](../runs/fixed-voice-centerline-render-48000-c/summary.json)・[研究版の枝の更新](../crates/vocal-core/src/airway/network.rs#L189)・[上流の枝の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029)

48 kHzの全93,056フレームで、各版の128・77フレーム分割はビット一致した。上流との最大絶対差は両変更で標準の256分の1に縮んだ。ビット差があるフレームは16から18へ増え、最初の差は7,868フレーム目から4,802フレーム目へ移った。後壁だけの版も最大絶対差を同じ値に下げた。声門上圧の再現性と、全区間に分布するPCM丸め差の改善度は別々に記録する。[全区間の比較](../runs/fixed-voice-centerline-render-48000-c/summary.json)

| 実験条件 | 声門上圧の初差（内部サンプル） | PCMの初差（フレーム） | PCMで異なるフレーム数 | PCM最大絶対差 |
| --- | ---: | ---: | ---: | ---: |
| 標準 | 8,205 | 7,868 | 16 | 4.657×10⁻¹⁰ |
| 喉頭蓋基部Y | 8,205 | 4,802 | 13 | 4.657×10⁻¹⁰ |
| 咽頭後壁 | 8,205 | 4,802 | 10 | 1.819×10⁻¹² |
| 両変更 | 8,210 | 4,802 | 18 | 1.819×10⁻¹² |

## 実行環境と再現確認

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で実行した。初回は隔離ソースにMandarinの辞書がなく、ビルドが停止した。辞書を含めた2回目では4条件の出力まで採取し、Rustの単体試験をコンパイルする段階で2つの埋め込みケースファイルが不足した。辞書とライセンス、試験ケースをスナップショットの入力に登録し直した。両実行の失敗ログと得られた成果を保存した。[初回のビルドログ](../runs/fixed-voice-centerline-render-48000-a/artifacts/cargo.log)・[2回目のビルドログ](../runs/fixed-voice-centerline-render-48000-b/artifacts/cargo.log)

修正後は研究ワークスペースと `/tmp` から各35判定に合格し、両変更版の解剖モデル9試験を各回で通過した。4条件の輪郭・断面・形状設定・内部観測・両分割のWAVの計24出力が実行間でバイト一致した。独立検算で各回の圧力208点と全PCMを照合した。失敗分も含め計580入力と90出力をハッシュで照合し、成果のうち22,389,948バイトをRTL9210B-CGへ保存した。[再実行のマニフェスト](../runs/fixed-voice-centerline-render-48000-repeat/manifest.json)・[独立検算の結果](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-centerline-render-48000.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_centerline_render.py fixed-voice-centerline-render-48000-new
```
