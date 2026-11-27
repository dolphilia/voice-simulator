# 実時間AudioWorkletでのアフリカゾウの `rumble`

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。Bestiaryから `AudioEngine` を経て送られる `call`・`stopCall` は、WorkletからWASMのコール操作に届く。公式CLIは持続1.2秒と停止0.4秒の後、48 kHzの76,800フレームで開始し、停止後の余韻まで172,800フレームを同じ声門・気道・フィルタで描画する。固定試験の `elephant-call-rumble` と22 Hz指定の `elephant-pitched` は、PCM・区間RMS・テレメトリ・ホスト分割を検査する。実時間試験はコールのキー解決、開始・停止、手動値の更新時に割り当てがないことを検査する。[画面の入口](../../../../docs/reference/chimera-vocal-synth/upstream/src/ui/components/BestiaryPanel.tsx#L52)・[Workletのコール操作](../../../../docs/reference/chimera-vocal-synth/upstream/src/worklet/processor.ts#L170)・[WASM操作](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-wasm/src/lib.rs#L527)・[公式CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L743)・[波形試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_creatures.rs#L94)・[実時間試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/creature_realtime.rs#L41)

`CallDef::resolve` はキーを解決して所有する項目を決める。`rumble` は音高・経路・モードを所有し、呼気圧と粗さは手動目標に追従する。開始時の制御時計を保存し、64出力フレームごとにキーを読む。経路の目標は1、音高は0〜2.7秒に15→12 Hzで変化し、移調は指定音高を基準14 Hzで割った倍率を掛けて8〜45 Hzに収める。ゲートは0〜0.3秒で0→1、2.7秒まで1、3.1秒で0になる。手動ゲートとの大きい方を取り、立ち上がり12 ms、解放60 msで平滑化する。肺圧は `980.665×呼気圧×平滑ゲート` dyn/cm²。停止要求、またはコール時計が最終キーから50 msを超える制御境界で保存した手動目標が戻る。音高と経路の平滑値は次の制御更新から追従する。[キーと所有](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/types.rs#L179)・[rumbleのキー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L138)・[開始・評価・停止](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L235)・[制御の順序](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L339)

平滑経路 `t` から口先 `0.05+10(1−t)` cm²と軟口蓋 `0.1+6t` cm²を設定し、制御区間内で断面を補間する。口腔の体積変化は流量源 `−ΔV/Δt`（cm³/s）として気道に入り、閉鎖に近いセルでは開いている隣接セルと分担し、60 Hzの一次低域通過で平滑化する。肺圧が0でも、この体積変化と枝・壁・放射負荷の更新で放射が生じうる。ゾウの内部レートと出力レートは同じで、総放射の差分からゲイン・DC除去・振幅制限を経て単精度PCMを得る。[経路の断面と固定弁](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/elephant.rs#L66)・[体積変化による流量源](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L835)・[出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/creatures/voice.rs#L365)・[CLIの読解と実測](elephant-rumble.md)

## 事前登録

48 kHzの公式先頭249,600フレーム、44.1 kHzの移調と途中停止、96 kHzの自然終了を実ブラウザで再生する。加工前PCMはCLIとビット一致、観測値は最大差0。独立のキー補間、ゲート、40 msの経路の平滑化、断面の線形移行をブラウザで測った系列に照合する。44.1 kHzでは開始要求173から初回制御192、手動変更30,013、ゲートの優先切り替え、停止61,913から平滑値が動く61,952の前後を連続観測する。48・96 kHzでは0.6〜1.2秒と2.0〜2.6秒のブラウザ観測から平均瞬時F0を二窓で比較する。

44.1 kHzの最初の256フレームで、経路を初期値0.05に維持する対照を測る。コールの代わりに開始要求173で音高だけを `15×22/14` Hzに設定し、呼気ゲート0と他の初期値を共有させる。どちらも同じ平滑音高と肺圧0で、断面の動くケースだけ口端の放射と加工前PCMが現れると予測する。観測窓は192〜255、PCMピークは0.001以上とし、肺圧が最初に正になる256も観測する。[ブラウザの登録条件](../cases/worklet-elephant-rumble.json)・[CLIと独立計算の登録条件](../cases/elephant-rumble.json)

## ブラウザへの接続

ゾウのWASMに `rumble` の開始と停止を追加し、固定発声と同じ合成器を使った。CLIに合わせて同じフレームでは手動目標、ゲート、コール操作の順に適用する。観測ABIの第2版は既存29列の後にコールID、制御時計、ゲート目標、音高・呼気圧・粗さの目標を加えた。固定発声の保存形式は29列のまま。画面から書き出した入力をCLIで描画し、観測値と加工前PCMを照合した。固定上流とCLIの比較基準には、対象版・継承するケース・上流の観測CSVとWAVのハッシュを確認した既存実行を使った。[WASMの操作と観測](../crates/vocal-wasm/src/elephant.rs)・[観測列](../crates/vocal-wasm/host/elephant.ts)・[比較手順](../tools/measure_worklet_elephant_rumble.py)・[固定上流の基準](../runs/elephant-rumble-20261120-repeat/manifest.json)

## 実測

Chromium 156.0.8078.4のAudioWorkletは、48・44.1・96 kHzの全657,600フレームで加工前PCMがCLIとビット一致した。10,978観測点でコールと音響の状態も最大差0だった。次の表の固定上流との差は、いずれも登録した許容差内だった。公式 `rumble` の172,800フレームでは出力82,528で最初のビット差があり、この区間の最大差も `3.73×10⁻⁹` だった。[ブラウザと固定上流の比較](../runs/worklet-elephant-rumble-20261120-a/summary.json)

| 条件 | 出力フレーム | 観測点 | 固定上流と最初に差が出た系列と出力フレーム | PCM最大絶対差 |
| --- | ---: | ---: | --- | ---: |
| 公式先頭 48 kHz | 249,600 | 3,903 | 肺流量 1 | `3.73×10⁻⁹` |
| 移調・途中停止 44.1 kHz | 76,000 | 1,882 | 壁面・口端・総放射 197 | `1.86×10⁻⁹` |
| 自然終了 96 kHz | 332,000 | 5,193 | 肺流量 136 | `1.86×10⁻⁹` |

44.1 kHzでは開始要求173、初回制御192。指定22 Hzに対する目標は23.57143 Hzだった。30,013では呼気圧22 cmH₂Oと粗さ0.6が即座に目標に入り、音高と経路はコールが保持した。40,064で手動ゲート0.95、54,848でコールの0.8が目標に適用された。停止61,913で手動目標31 Hzと経路0.2が復帰し、39フレーム後の61,952で平滑値が変化しゲート目標0が入った。96 kHzの自動終了は302,528で、音高目標は12 Hzから14 Hzに戻った。ブラウザの64フレームごとの観測で、二つの登録区間の平均瞬時F0は48 kHzで14.004→12.504 Hz、96 kHzで14.060→12.507 Hzだった。[制御境界と瞬時F0](../runs/worklet-elephant-rumble-20261120-a/summary.json)

### 呼気前の断面変化と放射

44.1 kHzの192で口先と軟口蓋が動き、口端と総放射およびPCMが同じフレーム、壁面は193で最初に非ゼロになった。肺圧の立ち上がりは256で、192〜255の64フレーム（約1.45 ms）では鼻先の放射も0だった。この区間の加工前PCMはピーク0.18883、RMS 0.12525。初期断面を固定し、同じ平滑音高・瞬時F0と肺圧を保った対照では、口端・壁面・鼻先の放射とPCMが0だった。[断面を固定したケース](../runs/worklet-elephant-rumble-20261120-a/artifacts/fixed-shape-prebreath-case.json)・[観測と対照](../runs/worklet-elephant-rumble-20261120-a/summary.json)

### 実時間と再実行

既存のCLI基準202項目のハッシュを確認して再利用した。ブラウザは研究ディレクトリと `/tmp` の両方で68項目を通過し、10,978観測行と、WASM・ブラウザWAV・再実行ケース・CLIのWAVとCSV・断面固定の対照の計16ファイルが一致した。CLIのWAV・CSV計6ファイルは既存基準にも一致した。128フレームの処理時間p95は48・44.1・96 kHzの順に2・2・1 msで各予算内。Workletの計時は `Date.now` の1 ms刻みだった。44.1 kHzの開始・手動編集・停止を含むネイティブ描画の割り当ては0回だった。[CLI基準](../runs/elephant-rumble-20261120-repeat/manifest.json)・[ブラウザの再実行](../runs/worklet-elephant-rumble-20261120-repeat/manifest.json)

ゾウの固定発声の回帰80項目を通過し、54,939観測行と固定経路の対照を含む19ファイルが変更前と一致した。Rustは `cargo fmt --all --check`、`cargo clippy --locked --workspace --all-targets -- -D warnings`、`cargo test --locked --workspace --release` を通過し、試験は37件だった。[固定発声の回帰](../runs/worklet-elephant-fixed-rumble-regression-20261120/manifest.json)
