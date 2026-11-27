# 鳴禽の片側の鳴管音源

参照版は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。今回は鳴管を構成する片側の振動子を対象にする。左右の出力と気道を接続する前に、変位、変位の微分、開口を同じサンプルで照合する。[事前登録](../cases/songbird-syrinx.json)

## 呼び出しと境界

`chimera-cli render creature songbird` は種の定義から `CreatureVoice` を生成する。48 kHz出力では `oversample=4` なので内部は192 kHz。64出力フレームごとに演奏パラメータを平滑化し、`Songbird::control` が左右に指定音高・駆動・張力・側別ゲートを割り当てる。右の指定音高は、左の指定音高に半音間隔の比を掛けた値。空気嚢の圧力は別のパラメータから計算され、振動子の常微分方程式には入らない。`Songbird::sample` は各振動子の開口率に0.03 cm²を掛け、気管につながるポート面積を更新して気道を1ステップ進める。CLIのWAVはここから放射と出力段を経た結果。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[内部レートと制御](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L148)・[レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L369)・[左右への割り当てとポート](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/songbird.rs#L85)

## 周期表と離散化

状態は無次元変位 `x`、無次元時間 `τ` に対する変位の微分 `y`、平滑化ゲート。初期状態は `x=0.2+0.05×seed`、`y=0`、ゲート0。seedは乱数の種を消費せず、左右の初期変位を変える。駆動と張力の正規化入力をそれぞれ `α=0.09…0.6`、`β=0.2…1.3` に写す。方程式は `dx/dτ=y`、`dy/dτ=−α−βx−x³−x²y+x²−xy`。[状態と方程式](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinx.rs#L80)

13×13の表は同じ方程式を時間刻み0.002で積分し、後半の変位の最小・最大と、0を上向きに横切る間隔から1周期の無次元時間 `T` を記録する。表に空欄がある場合、読み込み時に右隣、次のβ行の同じ列の順で周期を補い、双方が無ければ10にする。変位範囲に用いる隣は右だけで、無ければ下限−1、上限1。再取得した `T` と変位の上下限はβ行・α列の双線形補間で求める。上端の座標は最終添字より0.0001内側に制限される。[表の生成条件](../../../../docs/reference/chimera-vocal-synth/upstream/tools/gen-syrinx-table.ts)・[補完と補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinx.rs#L37)

指定音高が `f0` Hz、内部レートが `fs` Hz のとき、1サンプルの無次元時間は `Δτ=T×f0/fs`。これを `max(1,⌈Δτ/0.06⌉)` 等分し、4次Runge–Kutta法で進める。変位が非有限または絶対値10超なら `(0.2,0)` に戻す。積分後の変位を表の上下限で0〜1へ正規化し、二乗して、`g ← g + 0.002×(gate−g)` で更新した `g` を掛ける。ゲートと開口率は無次元で、振動の方程式に戻る経路はない。サンプル数で見たゲートの時定数は `−1/ln(0.998)`、秒ではその値を内部レートで割る。[一サンプルの更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinx.rs#L112)

## 事前の予測と照合

固定駆動・張力で指定音高を2600 Hzから5200 Hzにすると、変位の定常周波数比は2に近づく。表の補間誤差を調べるため、別の積分法で得た周期 `T_ref` から `f0×T/T_ref` を計算し、実測周波数と比較する。ゲートを閉じる区間では変位と微分が基準ケースに一致し、開口の減衰だけが変わる。48 kHzと192 kHzのゲート時定数は、同じ更新係数から秒単位で4倍の差が出る。音高0の対照では初期変位が保持される。上端補間と格子点も対象に含める。[入力・測定窓・許容差](../cases/songbird-syrinx.json)

固定上流の `valves_match_typescript` は鳴管単体の2,000サンプルを動的な入力で検査し、上流の `table_is_filled` は表の周期の有限性を検査する。動物の通し試験は左右と気道を含むレンダーを、リアルタイム試験は準備後のレンダーや操作で割り当てが発生しないことを検証する。今回の比較では上流Rustの片側開口列と、TypeScriptから作った単体フィクスチャの双方を使う。[単体フィクスチャ検査](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L216)・[表の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinx.rs#L154)・[リアルタイム試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

## 実装と実測

合成コアの `SyrinxLabia` は入力が変わった時点で周期・変位範囲・分割数を計算し、次の制御更新までその値を使う。CLIの `inspect` でこの計算結果、`render` で変位・微分・ゲート・開口の内部系列を出す。周期表データは固定上流のものを使い、SHA-256は `ea1d6c66f5b0f608db27672aed9ec920fa6aec7de92d7392c42ce40718a44841`。TypeScriptフィクスチャは参照版のファイルを計測時に読む。[振動子](../crates/vocal-core/src/syrinx.rs)・[CLI入口](../crates/vocal-cli/src/syrinx_case.rs)・[元の表](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/syrinxTable.generated.json)・[MITライセンス](../LICENSE-CHIMERA)

初回は補間座標を計算するクロージャーの引数型が解決せず、候補CLIのコンパイルで中断した。引数に `f64` を指定し、ケースと判定条件を保ったまま再実行した。初回に生成した固定上流のWAVは7.2秒で、持続音の指定2,600 Hzに対し上流CLIの推定値は2,609.8 Hz。これは気道と放射を含む音の値で、片側の変位から測る周波数とは観測点が異なる。[初回マニフェスト](../runs/songbird-syrinx-20261120-a/manifest.json)・[コンパイラの記録](../runs/songbird-syrinx-20261120-a/artifacts/cargo.log)・[上流CLIの結果](../runs/songbird-syrinx-20261120-a/artifacts/upstream-songbird.log)

8条件・計127,056サンプルで、候補と固定上流Rustの開口率が全サンプル一致した。音高を毎サンプル更新し、途中で駆動・張力・ゲートを変える2,000サンプルはTypeScriptフィクスチャとも一致した。開口率の独立照合は、閉形式のゲートと、候補が出力した変位の正規化・二乗を組み合わせて実施した。指定音高が一定かつ正の6条件では、変位そのものをSciPyのDOP853で別に積分した。CSVのサンプル0は最初の積分後で、比較時刻は `(sample+1)×Δτ`。基準条件の差はサンプル0の変位で約 `2.96×10⁻¹⁰` から現れた。最初の512サンプルで全6条件の変位差は `3.16×10⁻⁵` 以下、微分差は `5.81×10⁻⁵` 以下だった。[比較結果](../runs/songbird-syrinx-20261120-b/summary.json)

| 条件 | 内部レート (Hz) | 指定音高 (Hz) | 周期表の周期 (τ) | 独立積分の周期 (τ) | 変位の実測周波数 (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 基準 | 192,000 | 2,600 | 6.080478 | 6.072726 | 2,603.321 |
| 1オクターブ上 | 192,000 | 5,200 | 6.080478 | 6.072726 | 5,206.640 |
| 低い内部レート | 48,000 | 2,600 | 6.080478 | 6.072726 | 2,603.325 |
| 格子点 | 192,000 | 2,600 | 5.675000 | 5.674748 | 2,600.115 |
| 表の上端 | 192,000 | 2,600 | 4.337015 | 4.336622 | 2,600.231 |

基準と1オクターブ上の周波数比は1.9999994。基準で指定より約3.32 Hz高い主な差は、積分前の時間尺度にある。周期表の6.080478を使って独立積分の周期6.072726を秒に直すと、2,603.319 Hzと予測できる。格子点の差は約0.12 Hzで、補間点と格子点では表の値と連続方程式の周期のずれが異なった。格子点と補間点では駆動・張力も異なるため、補間の寄与を定量化するには同一の駆動・張力で表引きと直接積分による時間尺度を切り替える。[周期の内訳](../runs/songbird-syrinx-20261120-b/summary.json)

192 kHzの基準条件では、0.050秒から0.090秒までゲートを閉じても変位と微分は全サンプルで一致した。再開直前の平滑化ゲートは `2.10×10⁻⁷`。立ち上がりの実測時定数は192 kHzで2.602 ms、48 kHzで10.406 msで、比は4。音高0の対照は変位0.25・微分0を4,096サンプル保ち、ゲートに応じて開口率だけが変化した。[ゲートの照合](../runs/songbird-syrinx-20261120-b/summary.json)

研究ディレクトリと `/tmp` からの実行で各71項目を通過し、開口率と時系列のCSV16件、上流の基準WAV1件でSHA-256が一致した。固定上流の単体、通し、リアルタイム試験は計8件を通過した。前回の声門閉鎖音のネイティブ回帰は先行するビルドで86項目を通過した。[修正後の実行](../runs/songbird-syrinx-20261120-b/manifest.json)・[別ディレクトリからの実行](../runs/songbird-syrinx-20261120-repeat/manifest.json)・[ネイティブの回帰](../runs/syrinx-glottal-stop-regression-20261120/summary.json)
