# CHIMERA の研究用再実装計画

作成日 2026-11-19。2026-11-20 に外部ディスクの運用を追記。再開地点と段階ごとの到達状況は[進捗記録](../../research/experiments/chimera-rebuild/progress.md)で確認する。

## 目的と到達点

CHIMERA の Rust エンジン、CLI、WebAssembly と AudioWorklet の構成を手本に、発声の各段階を単独で実行・観測できる研究用の合成器を一から実装する。上流で音が出るところまでの呼び出しを追い、入出力、状態変数、更新順序、式、制約を説明できる形にしてから、機構ごとに実装と検証を進める。調査対象は `c6147d0198890475dbe8a65a0bb8f56240c539b7` に固定する。[上流コミット](https://github.com/jamesondh/chimera-vocal-synth/commit/c6147d0198890475dbe8a65a0bb8f56240c539b7)・[取得と検証の記録](../reference/chimera-vocal-synth/README.md)・[発声原理とコードの索引](../reference/chimera-vocal-synth/architecture.md)

最初の成果は、CLI で一様管の応答を再現できる小さな Rust 実装とする。人間の発声を扱う最初の節目は、同じ入力から CLI とブラウザで発声し、調音目標 → 声道形状 → 声門面積と声門流量 → 放射 → PCM のどの段が変化したかを追えることとする。その後、歌唱、ビートボックス、体型差、動物音声、言語フロントエンドへ広げる。各機能は上流との対応、再現手順、観測できる状態、残る差を記録した時点で完了とする。

## 実装の構成

| 領域 | 配置案 | 技術と役割 |
| --- | --- | --- |
| 上流資料 | `docs/reference/chimera-vocal-synth/upstream/` | 履歴付きの固定版。コードの参照、比較用レンダー、仕様の根拠に使う |
| 研究ワークスペース | `research/experiments/chimera-rebuild/` | Rust 2024 / Cargo。`vocal-core` は DSP と調音、`vocal-cli` はオフライン実行と計測、`vocal-wasm` はブラウザ向け C ABI。初回は必要なクレートから作る |
| Web プロトタイプ | `web/prototypes/chimera-research/` | TypeScript、React、Vite、Bun、Web Audio API の AudioWorklet。Zustand は画面間で状態を共有する時点、Three.js は三次元観察が必要な時点で導入する |
| 解析と実験 | 研究ワークスペース内の `cases/`、`runs/`、`notes/` | 反復処理は CLI。独立計算や図の生成は必要に応じて既存の Python 研究環境を使う。Notebook は波形・試聴結果を対話的に見たい場合に使う |

Cargo と Bun のロックファイルを記録する。初期の動作確認には、固定した上流版で確認済みの Rust 1.94.1 と Bun 1.4.4 を使う。音響状態と係数は `f64`、PCM 出力は `f32` を基本とし、気道の単位は上流に合わせて CGS とする。比較データの SI 変換は入出力境界で明示する。内部サンプル、出力サンプル、制御更新、テレメトリの時刻は出力サンプル番号から対応を復元できるようにする。[Rust ワークスペース](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/Cargo.toml)・[Web の依存関係](https://github.com/jamesondh/chimera-vocal-synth/blob/c6147d0198890475dbe8a65a0bb8f56240c539b7/package.json)・[Voice Simulator の研究方針](../../research/README.md)

エンジンはケース定義と状態を受け取り、CLI と WASM の両方から同じレンダー経路を通る。CLI は圧力・流量・面積・出力波形を指定区間だけ詳しく保存できるようにする。Worklet はレンダー用バッファを事前に確保し、低頻度のテレメトリを返す。画面では同じ時刻の声道断面、圧力・流量、声門波形、スペクトル、操作またはジェスチャーを並べて観察できるようにする。固定姿勢の線形伝達関数、レンダー後の PCM、Web Audio の加工後出力は、それぞれ計測位置を表示する。[上流のリアルタイム設計](../reference/chimera-vocal-synth/upstream/docs/rust-engine.md)

CLI の入口に `render <ケース> <出力>` と `compare <基準の実行> <候補の実行> <比較ケース.json>` を用意した。`render` はケースに書かれた入力、観測区間、保存先を使い、波形と計測用の系列を出す。`compare` は保存済みの出力を読み、同じ計測器と区間で両方を評価する。エンジンの設定と計測器の設定をケースから追えるため、後から計測だけをやり直せる。

## 保存先と容量管理

| 保存先 | 置くもの |
| --- | --- |
| 内蔵の作業ツリー | ソース、固定上流の参照資料、ケース、ノート、進捗、実行ごとの `manifest.json` と `summary.json`、小容量の計測出力。進行中のデュエット検証データ、CLI のリリースビルド、Vite が参照するリリース版 WASM も当面は現在の場所を使う |
| 作業用 `RTL9210B-CG` | `/Volumes/RTL9210B-CG/voice-simulator/build/` に候補と固定上流の `target/debug` を配置済み。長時間・高密度の時系列、反復計測の中間ファイル、大きな WAV や録画は `/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs/<実行ID>/` に直接書き出す |
| 保存用 `CT2000X8` | `/Volumes/CT2000X8/voice-simulator/archive/` に、検証が済んで日常的な再計測から外れた大容量成果を保存する。移行済みの計測 CSV は元の実験パスから参照できる |

配置済みの内容とハッシュ照合は[初回の移動台帳](../../research/storage-migrations/2026-11-20-chimera-v1/verification.json)と[重複統合・外部保存の記録](../../research/storage-migrations/2026-11-20-chimera-runs-v2/verification.json)に記録する。研究ワークスペースでの扱いは[研究 README](../../research/README.md#chimeraの外部保存と作業領域)に従う。

### 実行前の容量確認

1. 大容量計測は、過去の出力サイズや短区間の試行から、候補・上流の出力、並行する試行、一時ファイル、ビルドが同時に占める最大容量を保存先ごとに見積もる。`df -h` で作業用ディスクと内蔵の実際の空きを確認し、見積もりと比較する。CSV の出力密度が不明なときは短区間で計測してから全区間に広げる。
2. 外部ディスクを使う前に `/usr/sbin/diskutil info` でマウント先、ボリューム UUID、書き込み可否を確認する。作業用の UUID は `3D26C0E2-12EF-4613-A693-E21C0D51D2E7`、保存用は `9B51F3F1-8509-4272-B72B-ABA311912659`。外部の入力を読む実行では、そのファイルが元の実験パスで読めることも確認する。
3. 指定したディスクが未接続、別ボリューム、読み取り専用、または容量不足なら、その書き込みを見送り、理由と再開条件を記録する。外部指定の出力は内蔵へ自動で振り替えない。読み出しやビルドも含めて該当ディスクに依存しない読解、ケース定義、小容量の既存比較は続けられる。

### 大容量計測と時系列の保存

共通の Python 計測処理 `record_measurement` と `upstream_baseline.py` では、`CHIMERA_RUN_STORAGE=rtl9210b` と `CHIMERA_RUN_BYTES` を指定すると外部ディスクに直接出力する。内蔵にある `runs/<実行ID>/artifacts/` から、元の相対階層に沿ったファイル単位のリンクで読める。マニフェストは相対パス、サイズ、SHA-256 と外部の出力先を記録する。既定の出力先は内蔵とする。[実行例](../../research/experiments/chimera-rebuild/README.md#大容量計測とcsvの保存)

時系列を後続比較の入力に使わないケースでは、`retain_csv` で調べたい列とサンプル区間を指定する。全区間で判定を行い、合格した実行は抜粋と元のCSVのハッシュを保存する。全時系列を後から読み返す比較と、失敗の調査に必要な系列は全件を保存する。外部出力の検証では同じ小規模ケースを内蔵と外部で実行し、決定的な出力の SHA-256 と測定値・判定を照合する。入れ子の成果も既存の比較・再現入口で読めることを確かめる。

### 保存用ディスクへの引き渡し

実行記録と結果要約を確定し、次の作業が常用する基準・再計測データを確認した上で、参照頻度の下がった成果を移す。`archive/<移行ID>/` にリポジトリからの相対階層を保ってコピーし、元とコピーのサイズ・SHA-256 をマニフェストの記録と照合する。元の実験パスのファイル単位リンクを保存先に向け、作業用ディスクに依存せず既存の読み出し手順で参照できることを確認してから作業用の実体を解放する。実行 ID、元の論理パス、保存先、サイズ、SHA-256、照合結果を `research/storage-migrations/` に残す。成功した出力に加え、失敗・欠測の分析に必要な出力も同じ手順で保存する。

ローカルに同じCSVが複数あるときは、計測の完了後に各ファイルの実体をSHA-256で照合し、同じボリューム上のハードリンクに統合できる。共有した成果は確定済みの実行記録として扱い、再実行には新しい実行IDを使う。圧縮した長期保管データは展開後のSHA-256を照合してから、元のパスで参照できる状態に戻す。

2026-11-27の整理では、同じハッシュとファイル属性を持つ確定済みの成果も統合し、旧CSVを移した後の保存領域でAPFSの透過圧縮を使った。圧縮後の通常読込で元のSHA-256を照合し、実験パスとマニフェストを維持する。新規の共通計測で保存するソースは、内蔵の `runs/.source-objects/` の内容を読み取り専用のハードリンクで共有する。全区間のCSVを後続で読まないケースには、事前登録で `retain_csv` を使って必要な列と区間を指定する。[移行と再読込の照合記録](../../research/storage-migrations/2026-11-27-chimera-runs-v3/verification.json)

## 実装順と段階の完了条件

各段階は、依存する段階の完了条件を満たしてから接続する。表の上流パスは固定版の `crates/chimera/src/` を基準にし、例外はワークスペースからのパスを記す。最初は人間の発声に絞り、同じコアに他の発声・操作を追加できるかを派生機能で確かめる。

| 段階 | 上流で最初に読む箇所 | 作るものと完了条件 |
| --- | --- | --- |
| **0 基準と実行環境** | `physics.rs`、`../tests/airway.rs`、`crates/chimera-cli/src/{main,render}.rs` | Cargo ワークスペースと単一ケース CLI の入口を作る。比較用の上流出力を再生成して、コミット、入力、計測手順、出力ハッシュ、ツールチェーンを保存する。一様管の仕様と最初の解析式を読解ノートに記録し、別の作業ディレクトリから手順を再実行できれば完了 |
| **1 一様管の伝搬と放射** | `airway/network.rs` の枝・節点・放射の更新、`airway/frequency.rs` | 固定断面の単管、体積速度のインパルス、並列 R–L の終端、線形周波数応答を実装。独立した解析値、時間応答、周波数応答で共鳴を照合し、無励振で減衰することを確認する。表の下に示す条件で検証する |
| **2 分岐・狭窄・可動壁** | `AirwayNetwork::step`、`compute_noise`、`voice/human_airway.rs` の分岐接続、`../tests/airway_adversarial.rs` | 鼻腔と側枝、壁損失、非線形損失、形状補間、体積変化による流量源、シード付き乱流源を一つずつ追加。分岐の正味流量、密閉空洞の圧縮、定常狭窄の圧力差、閉鎖解除後の過渡を測る。各機構の追加前後で、有限性、既存ケースへの影響、動的条件の安定性を確認する |
| **3 肺圧と声門の結合** | `sources/glottis.rs` の `next`、`voice/human_voice.rs` の `control` と `render`、`../tests/lung_port.rs` | 圧力境界、呼気・声門面積パルス、声門流量、間引きと出力段を実装。固定声道で肺圧を上げたときの発声開始、声帯の開大での消声、口側の閉鎖での圧差低下を観測し、面積と流量の変化を別々の系列で説明できれば完了 |
| **4 調音と母音** | `anatomy/human.rs` の `compute` と `resample`、`HumanAirway::commit`、`control/articulators.rs`、`crates/chimera-cli/src/calibrate.rs` | 矢状面形状、断面積と最小狭窄、部位ごとの速度制限、姿勢入力を接続。まず成人男性の `/i ɑ u/` と姿勢間遷移を計測し、次に基準ガイドの10母音へ広げる。固定姿勢の伝達関数、生成音の LPC、形状の連続性、F0 を照合し、差を残した母音も含めて全件記録する |
| **5 IPA・発話・歌唱** | `phonetics/{ipa,planner,durations,english,sing,syllables}.rs`、`control/score.rs` | IPA → 調音ジェスチャー → レンダーを通し、`ɑpɑ / ɑbɑ / ɑsɑ / ɑzɑ / ɑmɑ` の閉鎖・摩擦・鼻音を観測する。続いて英語テキスト、歌詞と MIDI 音符を接続し、子音と拍の関係、語尾での脱力、無音への復帰を確認する。入力音素、未対応記号、計画時刻、実測時刻を出力する |
| **6 WASM とブラウザ** | `engine.rs` のブロック処理、`crates/chimera-wasm/src/{lib,api}.rs`、`src/{worklet/processor,wasm/wire,audio/AudioEngine}.ts` | 第3段階の固定姿勢で WASM と Worklet の最小動作を確認し、第5段階までの発話・歌唱を接続する。CLI と共通ケースを再生し、波形と主要な内部状態を比較する。舌・唇の操作、IPA 入力、時系列表示、ケースの書き出しを E2E で確認する |
| **7 派生機能と評価** | `phonetics/beatbox.rs`、`control/beat_player.rs`、`creatures/` と `sources/`、上流の言語・音声評価資料 | ビートボックス、成人女性・子どもとの体型補間、歌詞の韓国語・ロシア語・中国語、鳴禽とその他の動物音声を順に追加する。各機能に代表ケース、観測点、上流との差を付ける。Web MIDI、三次元表示、録画やデュエットなどの操作・提示機能も対応表に載せ、着手順と根拠を更新する |

第1段階の基準ケースは、管長 17.5 cm、面積 3 cm²、40 セル、内部 96 kHz とする。上流の条件を揃え、放射の終端補正を含む 1/4 波長近似に対する第1〜第4共鳴の相対誤差を 3% 未満、FDTD インパルスと線形応答の対応するピークの相対誤差を 1.2% 未満とする。後者は固定姿勢と小信号で測り、壁損失なしのケースから始める。壁損失を追加したら同じ比較を再実行する。体積速度とその時間微分をそろえて比較し、共鳴周波数、相対誤差、インパルスの減衰、計算条件を保存する。[上流の一様管テストと閾値](../reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs)

## 比較の手順

| 確認したいこと | 比較対象と判定方法 |
| --- | --- |
| 式と数値計算の妥当性 | 一様管の解析解、独立した小規模の周波数領域計算、既知の圧力差と定常流などを使う。比較に使う計算はレンダーの定数・式・更新関数をそのまま呼ばない |
| 上流と機構の挙動が対応するか | 同じ形状、姿勢、入力、時刻、サンプルレート、設定可能な乱数シードで比較する。節点圧力、枝流量、壁の体積速度、声門面積と流量、放射を上流から取得できる位置で照合する。内部系列が必要な場合は比較専用の追跡コードと差分を保存し、上流の固定コミットを記録する |
| 生成音の違いがどこで生じるか | レンダーの長さ、ピーク、無音、F0、F1〜F3 と帯域幅、区間ごとの RMS、閉鎖・破裂・摩擦の実測時刻を測る。線形応答と LPC は測定列を分け、欠測には理由を付ける。乱流や位相の差は、整列条件を明示したスペクトル・区間測定・試聴で扱う |
| 実行経路で音が変わるか | 同じビルドと入力での再実行、イベントの絶対サンプル番号を保ったブロック分割、ネイティブと WASM の固定シナリオを照合する。単純な固定ケースからサンプル一致を検査し、差が出た場合は最初に異なるサンプルと最大差を出す。比較は加工前 PCM で行う |
| 実時間で動作するか | 16、32、44.1、48、96 kHz を、まず CLI とコアで試す。Worklet は実際に設定できたレートを記録する。通常の発声と無音への遷移で、有限性、レンダー中の割り当て、ブロック処理時間の中央値・p95・p99、出力の途切れを確認する。たとえば 48 kHz・128 サンプルでの処理予算は約 2.67 ms |
| 人間の音声にどれだけ近づいたか | 再現の基準ケースから独立した評価にする。録音は評価用に使い、調整用と確認用の入力を分ける。上流の TSP（発話）・CSD（歌唱）は実験設計の参考にし、音響指標と試聴結果を別に記録する |

共通の必須条件は、入力の再実行ができること、ケースで指定したサンプル数を満たすこと、PCM と検査対象の状態に非有限値がないこと。今後追加する比較の許容差は、先に上流と独立参照の測定条件を確認し、再実装の結果を見る前にケース定義へ書く。閾値を改訂する場合は、変更理由と版を残し、旧条件での結果も読み返せるようにする。[上流の境界条件テスト](../reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs)・[上流のブロック処理テスト](../reference/chimera-vocal-synth/upstream/crates/chimera/tests/engine.rs)・[発話評価](../reference/chimera-vocal-synth/upstream/docs/speech-comparison.md)・[歌唱評価](../reference/chimera-vocal-synth/upstream/docs/csd-comparison.md)

## 読解・実装・記録の進め方

一回の作業は「一つの機構」または「一つの比較条件」を単位にする。各段階の最初に依存するケースと前回の結論を確認し、以下の順で進める。

1. **読む**。入口から対象関数とテストまでたどる。固定コミット、ファイル、関数、必要なら行リンクを記録する。状態・単位・更新式・更新順序を自分の言葉と小さな図で説明し、資料の説明と現在の実装に差があれば両方の位置を示す。
2. **予測する**。例えば「唇を閉じると放射流量が減り、閉鎖の手前で圧力が上がる」のように、どの入力を変え、どの系列がどう変わるかを書く。無励振、開閉の極限、レートの違いなど、予測を反証できる最小ケースを選ぶ。
3. **作る**。式と入出力が見える最小の実装を加える。原典に沿った判断と、この研究環境で導入した判断を記録する。出典のあるコード、係数、辞書、図版を取り込む場合は由来を記し、上流コードを再利用する箇所には該当する著作権表示と MIT の通知を付ける。辞書とフォントは同梱条件を確認する。[上流ライセンス](../reference/chimera-vocal-synth/upstream/LICENSE)
4. **測る**。固定入力を上流・再実装・独立計算に通せる範囲で照合する。ケース ID、基準と候補のコミット、ローカル差分の有無、入力と設定、乱数シード、環境、実行コマンド、出力の所在とハッシュ、全件の判定を残す。差があれば、入力、計画、幾何、声門、伝搬、放射、出力の順に最初に差が出る系列を探す。
5. **引き継ぐ**。段階の完了条件に対する現在地、未解決の事象、次の一手を `progress.md` に一行ずつ残す。基準ケースの回帰が出た場合は再現を保存し、原因調査を次の作業項目にする。段階ごとに、親リポジトリの現在地から手順を読み直して再実行する。

### 保存する記録

| 記録 | 主な項目 |
| --- | --- |
| `notes/<機構>.md` | 読んだコード・出典、入出力と単位、式と離散化、数値安定化や近似の理由、検証した予測、残る疑問。根拠が実装、上流文書、論文、再現結果のどれかを示す |
| `cases/<ケース>.json` | 仮説、入力、状態の初期化、観測点、測定区間、指標、許容差、基準の版。検証に使うケースは比較前に固定する |
| `runs/<実行ID>/manifest.json` と結果要約 | 実行条件、全ケースの成功・失敗・欠測、数値差、計測器の版、出力の相対パス・サイズ・SHA-256。大きな WAV、時系列、画像の実体は[保存先と容量管理](#保存先と容量管理)に従い、入力、ハッシュ、要約を Git に残す |
| `findings.md` | 発見や改善候補の表。機構、観察された現象、根拠へのリンク、影響範囲、次の最小実験、状態（観察・仮説・検証済み・採否）を追記する |
| `progress.md` | 上流の関数・再実装の位置・対応ケース・機能状態の対応表と、直近の実行、段階の判定、次の作業。依存する機構がわかるようにする |

一度記録した計測結果は実行 ID ごと保持する。改善候補を試すときは、対応する再現版をベースラインとして固定し、変更する機構と判定指標を先に決める。発見が追加調査に広がる場合も、最小の再現ケースを残して工程を区切る。各段階の終了時に、必須ケースの合否と依存する次の作業を確認する。通過した範囲、再現に必要な差分、比較実験で採用する改善を対応表へ反映し、未達の条件は根拠となる実行とともに記録する。

## 最初に記録する調査テーマ

- **狭窄で面積を二通り持つ理由**。セルの調和平均と最小面積が、それぞれ慣性、閉鎖、乱流にどう効くかを調べる。同じ調音軌跡で粗い格子と細かい格子を比較し、閉鎖開始時刻、圧力ピークとスペクトルを記録する。[上流の断面積変換](../reference/chimera-vocal-synth/upstream/crates/chimera/src/anatomy/human.rs)
- **放射負荷と観測点**。口端の R–L 負荷が共鳴・減衰に与える効果と、全放射流量の時間差分を取り出す観測を追う。Voice Simulator の既存実験にある SI 体積速度と理想開口の観測を、単位と境界条件を揃えた比較に使えるか確かめる。[上流の放射処理](../reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs)・[理想開口の観測実験](../../research/experiments/autonomous-research-cycle/campaigns/nas-volume-velocity-observer-20261009-v1/report.md)
- **発声開始と閉鎖時の相互作用**。声門前後の圧力差、面積パルス、実流量、周期成分が変化する順を記録する。圧力フィードバックの寄与は同じ声門面積モデルで圧差入力だけを変えて調べる。固定 LF 駆動との比較は、管とピッチをそろえた別のケースで行う。[上流の声門ソース](../reference/chimera-vocal-synth/upstream/crates/chimera/src/sources/glottis.rs)・[既存の LF 駆動比較](../../research/experiments/autonomous-research-cycle/campaigns/nas-radiated-waveguide-mechanism-20261009-v1/report.md)
- **形状の連続性と音への影響**。上流で既定テストから除外されている、突き出した下唇を引き込むときの面積の不連続を再現する。幾何の差が放射に出るかを調べ、平滑化などの候補は閉鎖・破裂の時刻も測って評価する。[上流の形状連続性テスト](../reference/chimera-vocal-synth/upstream/crates/chimera/tests/geometry_continuity.rs)
- **既存波動管との対応**。固定一様管・同じ終端条件という共通部分で、到達時刻、共鳴、複素応答を照合する。日本語へ広げる場合は、日本語の音素・調音目標と遷移を専用ケースとして事前に定義する。[既存の波動管検証](../../research/experiments/autonomous-research-cycle/campaigns/nas-waveguide-tract-mechanism-20261008-v1/report.md)・[日本語五母音の既存実験](../../research/experiments/autonomous-research-cycle/campaigns/nas-waveguide-vowel-mechanism-20261008-v1/report.md)

## 現在の再開地点

全体監査の第6版では、固定 /i/ の停止後を48 kHzの一次PCMで照合し、枝の換算順を変えた隔離版も既存の許容差に収まった。第7段階に必要な実録音F2の人手注釈、TSP・CSDの試聴回答、物理MIDIは未登録。取得できた記録から取り込み、監査を更新する。[第6版の全体監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-audit.md#第6版で固定発声の停止後を一次pcmから照合する)・[一次記録の取込](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#未確認の観測)

第7段階第11版では、同じCoreMIDI端子の候補名が2つあると受動収録が止まる問題を修正した。候補2件・仮想入力1端子で押鍵、離鍵、48 kHzのCLIとのPCM一致を照合した。第7段階は72実行・161判定、同版を指定した全体監査は214判定に通過した。実機の収録と人手評価の取込条件は上記の手順に従う。[第11版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第11版でmidi入力の候補名と端子数を照合する)

第12版では、受動収録で操作しない別の端子を接続したままMIDIを切断する条件を加えた。切断後の購読は修正前の1件から0件になり、選択した端子の押鍵・離鍵と全PCMは同じ実行のCLIに対応した。第7段階で73実行・169判定、同版を指定した全体監査で99実行・214判定に通過した。[第12版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第12版で選択外のmidi入力の購読解除を照合する)

第13版では、同名の仮想MIDI端子が2つ開く条件で、選択UIDと押鍵・離鍵の受信IDを照合した。第7段階は74実行・176判定、全体監査は99実行・214判定に通過した。物理鍵盤の採取は後日に回し、実録音のF2評価に向けて既知F2と追加の低域共鳴を含む合成対照を優先する。[第13版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第13版で同名midi入力と受信元を照合する)・[F2の比較条件](../../research/experiments/chimera-rebuild/notes/tsp-lpc-pre-emphasis-recordings.md#比較方法)

第14版では既知F2を2075 Hzに固定し、125 Hzの周期励振に低域共鳴を加えた。追加共鳴760 Hzから800 Hzの間で、上流LPCの公開極には設計F2の近傍が残ったまま、調べた6窓のF2採択が低域へ切り替わった。第7段階で75実行・179判定、全体監査で99実行・214判定に通過した。次は追加共鳴の条件を固定し、励振のF0だけを変える。[合成対照](../../research/experiments/chimera-rebuild/notes/tsp-f2-intervening-resonance.md#固定したf0での実測)・[第14版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第14版で既知f2の採択の切り替わりを照合する)

第15版では追加共鳴を760 Hz・800 Hzに固定し、100〜400 Hzの7条件でF0を変えた。同一の共鳴・次数・窓でF0 125 Hzと比較した72組中33組で採択分類が変わった。低域を採った48窓には設計F2近傍の適格な極が残っていた。第7段階で76実行・182判定、全体監査で99実行・214判定を通過した。次はF0と共鳴を固定し、窓内の励振位相の寄与を測る。[励振の対照](../../research/experiments/chimera-rebuild/notes/tsp-f2-intervening-excitation.md#7種類のf0での採択結果)・[第15版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第15版で励振のf0による採択の変化を照合する)

第16版では追加共鳴760 HzとF0 125 Hzを固定し、1周期の96位相を3窓・2次数で測った。全576窓で設計F2の近傍が選ばれた。次数12で追加共鳴側の公開極は採択F1から最大199.31 Hz離れ、200 Hzを超えるという予測は反証された。次は先行対照の760 Hzと800 Hzの中点、780 Hzを1条件加え、同じ位相比較で境界を跨ぐか確かめる。実録音F2の注釈と試聴回答の照合は一次記録が取得された時点で再開する。物理MIDIは後日に回す。[窓内位相の計測](../../research/experiments/chimera-rebuild/notes/tsp-f2-intervening-phase.md)・[第16版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第16版で窓内の励振位相を照合する)

第17版ではF0 125 Hz・追加共鳴780 Hzの全96位相を比較した。次数12は全位相で低域極を選んだ。次数14は58位相で低域極、38位相で設計F2近傍を選び、12組の隣接位相で低域極とF1の間隔が200 Hzをまたいだ。低域極を選んだ全462窓で設計F2近傍の極も候補に残った。次は事前登録済みの実録音6窓で、同様に低域と高域の候補が共存するかを保存済みの極から照合する。実録音F2の精度と試聴は人の一次記録が得られた時点で評価し、物理MIDIの収録は後日に回す。[中点の位相比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-intervening-phase-midpoint.md)・[第17版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第17版で共鳴780-hzの切り替わりを照合する)

第18版では、実録音の `seems` の母音で窓開始を前後5 ms動かした。全121窓で低域の約1 kHzの極を採り、約2.3 kHzの極も採択可能だった。低域極の帯域幅が公開上限600 Hzを超えるという予測は外れた。次は既存のTSP結果を診断するため、F2の全候補の周波数・帯域幅・採択順を既存の評価結果と並べて出せるようにし、既知の録音1発話で観測を照合する。F2精度と試聴には、人の一次記録を使う。物理MIDIの収録は後日に回す。[実録音の窓移動](../../research/experiments/chimera-rebuild/notes/tsp-lpc-recording-window-shift.md)・[第18版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第18版で実録音の窓移動を照合する)

第19版では、TSP計測CLIに各窓のF2候補と採択順を出すオプションを追加した。全185窓を固定上流と独立LPCに照合し、177窓に複数候補があった。窓単位の結果から上流の中央値を復元し、従来の評価要約と固定上流出力がバイト一致することを確認した。次は診断を使い、確認用母音1つで録音・固定上流・研究版のF2差について、候補の位置と採択順のどちらに差があるかを照合する。評価精度と試聴は人の一次記録を待ち、物理MIDIは後日に回す。[候補レポート](../../research/experiments/chimera-rebuild/notes/tsp-f2-candidate-report.md)・[第19版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第19版でtsp候補レポートを照合する)

第20版では、同じ /i/ を録音・固定上流・研究版の計15窓で再分析した。標準3窓で録音との差は採択F2で1,192〜1,320 Hz、高域候補間では最大111.36 Hzだった。両合成の標準窓に850〜1150 Hzの生根がなく、F1を録音の値に揃えても採択は変わらなかった。次は合成2版の同じ母音中央で声道断面を取り、固定した形状の線形共鳴とPCMの高域候補を照合する。実録音F2の精度と試聴には人の一次記録を待ち、物理MIDIの収録は後日に回す。[3音源の比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-source-comparison.md)・[第20版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第20版で同じ母音の3音源を照合する)

第21版では `seems` の /i/ の1.165秒で両版の現在断面を採った。36セルの面積差は最大6×10⁻¹⁴ cm²、線形流量比の高域ピークは両版とも2,187.47 Hzだった。その窓のPCMには高域LPC極の15.70 Hz差が残る。線形ピークの丸め前の符号で判定した初版を保存し、既定の0.1 Hz以下を判別不能と記録した。次は同じ25 ms窓で声門流量と口端放射を採り、どの段から高域のスペクトルが分かれるか照合する。人による評価と実機の未確認項目を引き継ぐ。[発話途中の線形伝達](../../research/experiments/chimera-rebuild/notes/tsp-seems-tract-transfer.md)・[第21版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第21版で発話中の固定断面と線形応答を照合する)

第22版では `seems` の同じ25 ms窓で声門流量からPCMまでを観測した。声門流量で1,950〜2,600 Hzのパワー分布に差があり、高域LPCの版間差は放射の間引き直後15.74 Hz、PCM15.70 Hzだった。両版の放射差分を共通の独立した出力段に通し、解析窓を含む先頭56,600フレームのPCMをビット単位で再現した。次は固定上流の音源のドリフトだけを止め、同じ窓の声門流量とLPCを比較する。人による評価と実機の未確認項目を引き継ぐ。[声門流量からPCMまでの比較](../../research/experiments/chimera-rebuild/notes/tsp-seems-spectrum-stages.md)・[第22版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第22版で声門流量からpcmまでを照合する)

第23版では、固定上流のドリフト振幅を5セントから0にした。研究版との高域の声門流量パワー分布の距離は0.205から0.113、PCMのLPC極の絶対差は15.70 Hzから5.95 Hzに縮まった。極の位置関係は逆転した。次はドリフトを止めたまま声帯振動への圧差入力に既定条件の系列を使い、声門面積と有声度から出力までを照合する。実録音のF2注釈、TSP・CSDの試聴回答と物理MIDIの実測は未登録。[ドリフトだけを変えた比較](../../research/experiments/chimera-rebuild/notes/tsp-seems-drift-only.md)・[第23版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第23版でドリフトの寄与を照合する)

第24版では、ドリフトを止めたまま声帯に渡す圧力差を通常条件の系列に置き換えた。25 msの全2,400標本で有声ゲートの圧力成分が上限に達し、高域LPC極の移動は約0.0000014 Hzだった。次は同じ窓で上流の周期長のjitterだけを止めて、位相と研究版までの高域極の差を照合する。人による評価と実機の未確認項目を引き継ぐ。[圧差再入力の比較](../../research/experiments/chimera-rebuild/notes/tsp-seems-pressure-replay.md)・[第24版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第24版で圧差の再入力を照合する)

第25版では、ドリフト0の両版で周期長のジッターを切り替えた。同じ25 ms窓で、ジッターの追加により高域LPC極が固定上流で3.64 Hz、研究版で3.55 Hz下がった。ジッターを0に揃えたときの版間差は2.30 Hz。ジッター係数をそろえた条件では、全113,200内部標本で位相と瞬時F0が両版で一致した。次は振幅のシマーだけを揃えて残差を照合する。人による評価と実機の未確認項目を引き継ぐ。[周期長ジッターの比較](../../research/experiments/chimera-rebuild/notes/tsp-seems-period-jitter.md)・[第25版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第25版で周期長ジッターを照合する)

第26版では、ドリフトとジッターを0にした両版で、周期の振幅のシマーを0と0.042で比較した。シマーを揃えた両組で母音中央のLPC入力300標本と極が一致した。全発話のPCMでは冒頭から版間差があり、次は初期調音姿勢と気道断面を照合する。実録音のF2注釈、TSP・CSDの試聴回答と物理MIDIの計測は未登録。[周期振幅の比較](../../research/experiments/chimera-rebuild/notes/tsp-seems-amplitude-shimmer.md)・[第26版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第26版で周期振幅を照合する)

第27版では、音源を揃えた `seems` で研究版の初期舌先だけを休止位置に移した。初期口腔の面積差が最大1.054 cm²から7.99×10⁻¹⁵ cm²に縮まり、先頭50 msのPCMが一致した。全発話のPCMの最大差は4.66×10⁻¹⁰だった。次は別の確認用発話で同じ条件を揃え、発話単位の残差と母音・子音の区間を照合する。人による評価と実機の未確認項目を引き継ぐ。[初期舌先の比較](../../research/experiments/chimera-rebuild/notes/tsp-seems-initial-tip.md)・[第27版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第27版で初期舌先と発話前の放射を照合する)

第28版では、既存の確認用12発話で体型別ゲイン、音源の揺らぎ、初期舌先を固定上流に揃えた。全1,487,586 PCMフレームの最大差は1.86×10⁻⁹で、316音素の計画境界と−35 dBの発話区間が全件一致した。次はこのPCMを既存のTSP強勢母音の評価窓に通し、LPC候補、F2採択と欠測を確認する。実録音のF2注釈、TSP・CSDの試聴回答、物理MIDIの実測は未登録。[確認用12発話の比較](../../research/experiments/chimera-rebuild/notes/tsp-held-out-matched-speech.md)・[第28版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第28版で確認用12発話の全pcmを照合する)

第29版では、設定を揃えた合成を既存のTSP確認用4発話の12強勢母音に適用した。共通60窓でF2採択と欠測判定が一致した。研究版PCMを保って保存MFA境界だけを切り替えると、15窓のF2が変わり、最大差は109.53 Hzだった。実録音 `seems` の50%窓と両合成のF2採択差は1,234.78 Hzだった。[TSP強勢母音の再計測](../../research/experiments/chimera-rebuild/notes/tsp-matched-speech-formants.md)・[第29版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第29版で設定を揃えたpcmの強勢母音を照合する)

第30版では、同じ4発話の合成設定を揃えた状態から、整列用PCM16を作り直した。固定Rustと研究の変換処理は8入力で一致し、MFA 3.4.3を再実行すると両版の語34区間、音素110区間の境界が一致した。母音60窓の開始位置差は15窓から0窓になった。既存の録音 `seems` のF2採択差を次に調べる際は、人手注釈で候補の妥当性を確認する。TSP・CSD試聴回答は未登録で、物理MIDI計測は後日に回す。[MFA入力と境界の比較](../../research/experiments/chimera-rebuild/notes/tsp-matched-speech-mfa.md)・[第30版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第30版でmfa入力と再整列境界を照合する)

第31版では、確認用 `FK61_01` で初期舌先だけを旧値へ戻した。最初の50 msのPCMに最大0.00189の差が現れ、`again` 付近の9,600標本と /ɛ/–/n/ の2.040秒境界は一致した。旧境界を同じPCMへ適用すると90%窓が216標本ずれ、F2は109.53 Hz上がった。旧比較の境界差への音源設定の寄与、実録音F2の人手注釈、TSP・CSDの試聴回答は確認を続ける。物理MIDI計測は後日に回す。[初期舌先を戻した比較](../../research/experiments/chimera-rebuild/notes/tsp-again-initial-tip-mfa.md)・[第31版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第31版で初期舌先の寄与を照合する)

第32版では、同じ発話で周期長ジッターだけを0.00455から0へ変えた。周期境界と振幅倍率は独立計算に一致し、位相の初差は初回境界の次の内部標本だった。共通窓でF2は最大3.89 Hz動き、MFAの /ɛ/–/n/ 境界は両条件とも2.040秒だった。旧比較の境界差へのほかの音源設定の寄与、実録音F2の人手注釈、TSP・CSD試聴回答は引き続き確認する。物理MIDI計測は後日に回す。[周期長ジッターを止めた比較](../../research/experiments/chimera-rebuild/notes/tsp-again-period-jitter-mfa.md)・[第32版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第32版で周期長ジッターと整列境界を照合する)

第33版では、同じ発話で低速F0ドリフトだけを5セントから0へ戻した。MFAの /ɛ/–/n/ 境界は2.040秒から2.060秒へ動き、旧研究版の語・音素区間を再現した。90%窓のF2は、境界を固定すると−2.03 Hz、0セントPCMの窓を再整列境界にすると+101.67 Hz動いた。残る3発話でこの効果の範囲を調べる。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[低速F0ドリフトを止めた比較](../../research/experiments/chimera-rebuild/notes/tsp-again-pitch-drift-mfa.md)・[第33版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第33版で低速f0ドリフトと整列境界を照合する)

第34版では、低速F0ドリフトを止める比較を4発話の60窓へ広げた。旧差15窓のうち、女性の `again` と男性の `plea` の計10窓で旧位置を再現した。男性の `again` の5窓は基準位置を保ち、旧差のなかった45窓も同じ開始位置だった。一方、評価対象外の `FK61_02` の /i/–/l/ 境界は70 ms移動した。次は `MK61_01` の残る境界差を調べる。実録音F2の人手注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[4発話の比較](../../research/experiments/chimera-rebuild/notes/tsp-matched-pitch-drift-mfa.md)・[第34版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第34版で4発話のドリフト停止と整列窓を照合する)

第35版では、男性発話 `MK61_01` のドリフトを0に保って振幅シマーだけを0へ戻した。振幅倍率は最初の周期境界から変わり、固定窓のF2は最大1.30 Hz動いた。/ɛ/–/n/ 境界は2.030秒を保ち、旧比較の2.050秒に由来する5窓の開始差が残った。次は両方を0に保ち、周期長ジッターの寄与を調べる。人手によるF2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[振幅シマーを止めた比較](../../research/experiments/chimera-rebuild/notes/tsp-again-amplitude-shimmer-mfa.md)・[第35版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第35版で振幅シマーと男性発話の境界を照合する)

第36版では、同じ男性発話のドリフトとシマーを0に保ち、周期長ジッターだけを止めた。/ɛ/–/n/ 境界は2.030秒から2.050秒へ動き、残る5窓に加えて先に復元した `plea` の5窓も旧位置に一致した。同じ条件で旧研究版の語8区間と音素25区間を再現した。次は3つの音源変動を0にした条件を4発話へ適用し、窓と評価外の境界の再現範囲を測る。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[男性発話の周期長ジッター比較](../../research/experiments/chimera-rebuild/notes/tsp-again-male-period-jitter-mfa.md)・[第36版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第36版で男性発話の周期長ジッターと整列境界を照合する)

第37版では、3つの音源変動を0にした条件を4発話へ適用した。旧差15窓を同じ開始位置で再現し、残る45窓も基準位置を保った。語34区間と音素110区間のうち、旧比較と異なるのは `FK61_02` の `tall` の /ɔ/–/l/ 境界1か所だった。3変動0の1.650秒と旧版の1.680秒の差を、次はゲインだけ変えて調べる。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[4発話の音源変動停止](../../research/experiments/chimera-rebuild/notes/tsp-matched-source-variation-zero-mfa.md)・[第37版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第37版で3つの音源変動を止めた4発話を照合する)

第38版では、`FK61_02` の出力ゲインだけを旧値へ戻した。放射と間引き後の全標本が一致し、出力PCMは8/7倍の比例関係を保った。MFAの /ɔ/–/l/ 境界は1.650秒で、旧版の1.680秒との30 ms差が残った。旧ゲイン時と旧版の整列用PCM16の差は、同じ発話の先頭約251 msに収まった。次は初期舌先だけを旧値へ戻して冒頭の差と境界を照合する。人手によるF2注釈・TSPとCSDの試聴回答は未登録。物理MIDI計測は後日に回す。[出力ゲインの比較](../../research/experiments/chimera-rebuild/notes/tsp-tall-output-gain-mfa.md)・[第38版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第38版で出力ゲインとtallの境界を照合する)

第39版では、`FK61_02` で旧ゲインと3変動0を固定し、初期舌先だけを旧値へ戻した。旧研究版の無加工PCMと整列用PCMを各144,727標本、語9区間と音素30区間をすべて再現した。 `tall` の局所波形が同じまま /ɔ/–/l/ の境界は1.680秒へ動き、再整列で90%窓のF2が257.79 Hz変わった。次は整列用PCMの冒頭50 msだけを入れ替えて、境界を動かすのに十分か確かめる。人手によるF2注釈、TSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[初期舌先の比較](../../research/experiments/chimera-rebuild/notes/tsp-tall-initial-tip-mfa.md)・[第39版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第39版で初期舌先と旧tall境界の再現を照合する)

第40版では、`FK61_02` の整列用PCM16を50 msで分け、冒頭だけと50 ms以後だけをそれぞれ旧舌先条件へ置き換えた。どちらも /ɔ/–/l/ の旧1.680秒と語9区間・音素30区間を再現した。50 ms以後だけなら1.650秒に留まるという予測は外れた。次はケプストラム正規化の前後と対照の正規化統計を共用した場合の境界を調べる。実録音F2注釈、TSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[PCM16の区間交換](../../research/experiments/chimera-rebuild/notes/tsp-tall-mfa-preroll.md)・[第40版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第40版で冒頭と残りのpcm16の交換を照合する)

第41版では、`FK61_02` の対照PCMへ冒頭交換条件のCMVN統計だけを適用すると、`tall` の /ɔ/–/l/ が1.650秒から1.680秒へ動いた。逆の統計交換では戻らなかった。非圧縮MFCCの差は6フレーム、圧縮アーカイブを読み戻したMFCCの差は全302フレームにあり、次は最初の特徴量書き出しを非圧縮にして境界を照合する。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[CMVNの比較](../../research/experiments/chimera-rebuild/notes/tsp-tall-mfa-cmvn.md)・[第41版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第41版でcmvn統計と初回の精度判定を照合する)

第42版では、`FK61_02` の最初のMFCC保存だけをfloat32にした。対照の統計を共用すると正規化直後の差は先頭6フレームに収まり、最終の圧縮を読み戻すと全302フレームに再発した。対照の `tall` の境界が1.650秒から1.680秒へ動き、4条件の全区間が揃った。次は最初をfloat32に固定して最終の保存形式だけを変える。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[最初のMFCC保存形式の比較](../../research/experiments/chimera-rebuild/notes/tsp-tall-mfcc-input-compression.md)・[第42版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第42版で最初のmfcc保存形式を照合する)

第43版では、`FK61_02` の最初の保存をfloat32に固定し、最終MFCCをfloat32へ替えた。対照統計を共用した2発話で `tall` 周辺の特徴量差は消え、1.680秒の境界と全語・音素区間は4条件とも同じだった。1.650秒へ戻るという予測は外れた。次は第42版で境界が分かれた同一PCMの2条件からGMM-HMMの入力と経路の得点を採る。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[最終MFCC保存形式の比較](../../research/experiments/chimera-rebuild/notes/tsp-tall-mfcc-final-compression.md)・[第43版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第43版で最終のmfcc保存形式を照合する)

第44版では、`FK61_02` の同一PCMで1.650秒と1.680秒を選んだ経路を同じGMMと探索FSTで交差採点した。音素が異なるのは3フレームで、重み付き合計の差は−0.000152と+0.000130。合計値の照合誤差より差が小さいため、次はPDFの異なる5行だけを入力で交換し、MFAの経路選択を直接測る。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[GMM-HMM交差採点](../../research/experiments/chimera-rebuild/notes/tsp-tall-gmm-paths.md)・[第44版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第44版でgmm-hmm経路の交差採点を照合する)

第45版では、`FK61_02` の164〜168番の特徴行だけをGMM-HMMの入口で交換し、`tall` の終端を1.650秒から1.680秒へ動かした。残り297行だけの交換では1.650秒だった。両交換条件の全遷移ID・語音素区間は対応する対照と一致した。次は5行の部分集合を試し、境界を動かす最小の集合を確認する。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[特徴行の交換](../../research/experiments/chimera-rebuild/notes/tsp-tall-gmm-frame-swap.md)・[第45版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第45版でgmm-hmmへの5フレームの交換を照合する)

第46版では、`FK61_02` の5特徴行の32部分集合を通常MFAで再整列した。最小は165・166番と165・167番の2組で、166〜168番の3行も包含極小だった。全条件の経路が固定2経路の得点差の予測と一致した。次は同一PCMに1.650〜1.680秒の終端候補を適用し、LPCの窓位置によるF2の変動を調べる。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[特徴行の全部分集合](../../research/experiments/chimera-rebuild/notes/tsp-tall-gmm-frame-subsets.md)・[第46版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第46版でgmm-hmm特徴行の32部分集合を照合する)

第47版では、`FK61_02` の同一合成PCMで `tall` の母音終端を10 ms刻みで動かした。F2の幅は中央3窓の中央値で23.98 Hz、90%窓で257.79 Hzだった。16窓の開始標本と採択を固定上流と独立計算で照合した。次は録音側の `AA1` 区間で終端感度を測る。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[F2の終端感度](../../research/experiments/chimera-rebuild/notes/tsp-tall-f2-boundary-grid.md)・[第47版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第47版で母音終端に対するf2の感度を照合する)

第48版では、実録音 `FK61_02` の `tall` の `AA1` 終端を10 ms刻みで動かした。F2の幅は中央3窓の中央値で11.62 Hz、90%窓で72.21 Hz。90%窓で100 Hz以上動くという予測は外れた。標本位置には保存秒値の丸めに由来する1標本の差があり、初回判定を保存して再照合した。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[録音のF2感度](../../research/experiments/chimera-rebuild/notes/tsp-tall-recording-f2-boundary-grid.md)・[第48版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第48版で実録音の母音終端に対するf2の感度を照合する)

第49版では、人手注釈資料W06の `again` の中央窓を前後5 ms動かした。全121窓で2.1 kHz側を採り、2.9 kHz側も候補に残った。注釈資料のPCMと元録音の切り出しを照合した。次は元の窓を固定し、プリエンファシスに対する候補の変化を測る。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[W06の窓位置比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-annotation-w06-window-shift.md)・[第49版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第49版で注釈資料w06の窓位置とf2候補を照合する)

第50版では、W06の固定窓でプリエンファシスを0.001刻みで971点比較した。係数0.111と0.112の間で旧F1の帯域幅が500 Hzを越え、F2の採択が680.23 Hzから2,009.79 Hzへ切り替わった。次は同じ語の35%・65%の注釈窓を比較する。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[W06のプリエンファシス比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-annotation-w06-pre-emphasis.md)・[第50版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第50版でw06のプリエンファシスとf2の採択を照合する)

第51版では `again` の35%・65%窓を加えた。35%窓は高域を全点で採り、65%窓は係数0.190と0.191の間で旧F2の帯域幅が600 Hzを越えた。3窓の中央値は中央窓と同じ0.111〜0.112で切り替わった。次は対応音素の集約を通り、この差がTSPのF2費用にどの程度表れるかを照合する。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[3窓のプリエンファシス比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-annotation-again-pre-emphasis.md)・[第51版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第51版でagainの3注釈窓のf2採択と中央値を照合する)

第52版では、6話者36録音の部分集合で `again` の1トークンだけを差し替えた。1,187.60 Hzの入力差に対し、FKの話者中央値は114.75 Hz、F2診断費用は1.14460動いた。採点対象3群と総合点は一致した。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[TSPの話者集約と費用](../../research/experiments/chimera-rebuild/notes/tsp-again-f2-term-effect.md)・[第52版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第52版でagainのf2差をtspの診断費用まで照合する)

第53版では学習女性5名の /ɛ/ 39件を1件ずつ2値に差し替えた。参照中心が動いたのは16件、中心が同じまま評価の幅と費用が動いたのは12件だった。78条件のうち8件で幅の下限が効いた。実録音F2注釈とTSP・CSD試聴回答は未登録。物理MIDI計測は後日に回す。[学習参照の感度](../../research/experiments/chimera-rebuild/notes/tsp-f2-training-reference-sensitivity.md)・[第53版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第53版で学習側の1件がf2参照に与える影響を照合する)

第54版では学習女性を5名から10名に増やして、第53版と同じ39位置・2値を比較した。参照中心の最大変動は0.05633から0.03197オクターブに減った。FKのF2診断費用の最大変動は録音側で0.32981から0.63034へ増え、合成側は0.75983から0.11591へ減った。次は録音側で差が最大になった1位置で中心と幅を個別に固定して照合する。物理MIDIは後日に回し、人手F2注釈とTSP・CSD試聴の登録は引き続き保留する。[10名の比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-training-reference-ten-speakers.md)・[第54版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第54版で学習女性5名と10名のf2参照を照合する)

第55版では `FD19_10` の1音素で、参照中心と評価幅を個別に変えた。10名のFK録音側費用の増分0.63034を二つの差し替え順で平均すると、中心は0.07896、幅は0.55138だった。次は同じ介入に男性学習話者の残差を加えて、上流の評価幅と費用を照合する。物理MIDIは後日に回し、人手F2注釈とTSP・CSD試聴は未登録。[参照中心と評価幅の比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-reference-centre-width.md)・[第55版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第55版でf2の参照中心と評価幅を個別に照合する)

第56版では男性9名の54録音を加えて男女の残差をまとめた。女性の参照中心を保ったまま介入後の評価幅は0.07000から0.10677へ増え、FK録音側のF2診断費用の増分は0.63034から0.16354へ減った。男性4名の対照は女性のみの参照幅を再現した。次は第54版の39位置・2値でこの傾向を比較する。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[男女の残差の比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-reference-pooled-sexes.md)・[第56版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第56版で男女の学習残差をまとめたf2参照を照合する)

第57版では男女の参照を同じ39位置・2値で比較した。FK録音側の最大絶対変動は0.63034から0.40198へ減った。78条件の内訳は減少32、等しい42、増加4。FK合成側は男女の参照で全78条件が費用0となった。次は別の女性確認話者FLで同じ参照を検証する。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[39位置の比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-pooled-reference-sweep.md)・[第57版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第57版で男女をまとめたf2参照の78条件を照合する)

第58版ではFLの6録音を同じ参照と78条件で照合した。FL合成は女性のみ・男女とも全条件で費用0。FL録音では男女の参照で費用0が8条件になり、最大変動は0.54524から0.10408に減った。次は確認用のFKとFLの合成値を上流と同じ方法で集約し、確認女性全体のF2診断を調べる。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[確認話者FLの比較](../../research/experiments/chimera-rebuild/notes/tsp-f2-pooled-reference-held-fl.md)・[第58版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第58版で確認話者flのf2費用を照合する)

第59版では確認用のFK・FLを上流の文集合別集約に通した。上流の値は2,051.83 Hz相当で、女性参照の73条件、男女参照の78条件が費用0だった。15件の直接集約では2,045.90 Hzとなり、女性参照の5条件が正の費用から0へ変わった。次は確認女性の全発話へ広げる。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[文集合別の集約](../../research/experiments/chimera-rebuild/notes/tsp-f2-held-synth-over-sets.md)・[第59版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第59版で確認女性の合成f2の文集合別集約を照合する)

第60版では確認女性FK・FLの全120発話を測った。元の12発話の音素対応とF2は一致し、全発話を使った合成集約値は2,048.24 Hz相当になった。女性参照で正の費用が出た5条件が0になり、最も近い上端までの余裕は0.140 Hzだった。次は研究版で同じ確認発話を合成し、測定から費用まで照合する。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[全120発話の計測](../../research/experiments/chimera-rebuild/notes/tsp-f2-full-held-women.md)・[第60版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第60版で確認女性fkとflの全発話を照合する)

第61版では研究版の通常CLIで確認女性120発話を合成した。計画フレームと音素対応が全発話で一致し、PCMの最大差は1.49e-8。強勢付き /ɛ/ の70値とF2診断費用は固定上流と一致した。次は最初のPCM差が早いFK61_01を使い、音源から出力までのどの演算で初めて差が出るかを調べる。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[研究版の120発話](../../research/experiments/chimera-rebuild/notes/tsp-f2-full-held-candidate.md)・[第61版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第61版で研究版の確認女性120発話を照合する)

第62版ではFK61_01の最初のPCM差を追った。放射への差は内部標本3968から、間引きとDC除去の倍精度値では出力1984から現れ、1989でfloat32の中点をまたいだ。放射を交換する独立計算は入力側のPCMを再現した。次は最初に差が出る口端流量の更新を調べる。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[PCM差の追跡](../../research/experiments/chimera-rebuild/notes/tsp-fk61-pcm-first-difference.md)・[第62版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第62版でfk61_01の最初のpcm差を照合する)

第63版では、FK61_01の内部標本3968で口端セルの体積差分から流量が分かれることを確認した。倍精度で保存した体積の差分は1.11×10⁻¹⁶ cm³異なり、この差は60 Hzの平滑化を経て放射負荷へ入った。独立計算では平滑化後の流量だけを交換し、相手側の口端流量を1 ULPまで再現した。次は記録済みの断面で、面積と長さの変化分から体積差を求める式を個別に比較する。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[口端の読解と実測](../../research/experiments/chimera-rebuild/notes/tsp-fk61-lip-onset.md)・[第63版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第63版でfk61_01の口端流量の初差を照合する)

第64版では、口端1節点で面積と長さの変化分から体積差を求めた。内部標本3968の体積流量の誤差は約1.34億分の1になった。固定上流との最初のPCM差はfloat32の丸めで1989から1987へ早まった。次は標準版で、同じ発話の口端の断面差が生じる箇所を調音から再標本化まで追う。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[差分式の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-lip-volume-increment.md)・[第64版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第64版でfk61_01の口端の体積差分式を照合する)

第65版では、FK61_01の初期の口端平均面積差4.44×10⁻¹⁶ cm²を測定線45・46までさかのぼった。測定線45はx座標、46は接触後の隙間の差が面積に伝わった。標本3968では両版で同じ面積目標を登録しており、補間は初期値から差を引き継いだ。次は初期の唇端と測定線46の隙間を比べる。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[口端の断面の読解と実測](../../research/experiments/chimera-rebuild/notes/tsp-fk61-lip-area-origin.md)・[第65版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第65版でfk61_01の口端断面の初差を照合する)

第66版では、FK61_01の唇前端で体型変換の等価な2式が異なる値に丸められることを確認した。前端1箇所の演算順序を変えた試験版は、初期の測定線45・46と口端面積が固定上流に一致した。最初のPCM差は1989から1987へ早まり、最大差は同じだった。次はフレーム1985の測定線31付近で中心線距離の差を追う。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[唇前端の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-lip-front-origin.md)・[第66版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第66版でfk61_01の唇前端の体型変換を照合する)

第67版では、FK61_01のフレーム1985で測定線31のyが累積距離の丸め中点をまたがせることを確認した。距離計算で31のyだけを交換すると累積位置の初差は34へ移り、口端セル長の目標差は半減した。128標本の現在長の独立計算と、標準版・試験版の全PCMが一致した。次は唇前端を揃えた条件で初期の放射差を追う。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[中心線の距離と丸め](../../research/experiments/chimera-rebuild/notes/tsp-fk61-centerline-length-origin.md)・[第67版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第67版でfk61_01の累積距離と補間を照合する)

第68版では、FK61_01の唇前端を揃えた試験版で、3968の総放射流量の一致と時間換算による放射差分の1 ULP差を確認した。1987のPCM差は換算順を交換しても残り、独立計算で3972の口端流量だけを交換すると固定上流の値を再現した。次は口腔節点42と口端43をつなぐ枝を調べる。人手F2注釈とTSP・CSD試聴は未登録。物理MIDIは後日に回す。[放射成分の照合](../../research/experiments/chimera-rebuild/notes/tsp-fk61-lip-front-radiation.md)・[第68版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第68版でfk61_01の残る初期放射差を照合する)

第69版では、FK61_01の節点42と口端43を連続8内部標本で独立に再計算した。3968の節点42ではコンプライアンスの差で圧力が分かれ、次の標本の枝流量を上流に揃えるには左圧力と枝係数の両方の交換が必要だった。節点42の平滑後の体積注入を8標本で交換した出力段の比較では、1987までのPCMが上流に一致した。次は3969の注入差を体積の丸め、近隣への配分、平滑の順に調べる。F2の人手注釈とTSP・CSDの試聴は一次記録が得られた時点で再開し、物理MIDIは後日に回す。[枝と体積注入の照合](../../research/experiments/chimera-rebuild/notes/tsp-fk61-lip-front-terminal-branch.md)・[第69版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第69版で節点42から口端への流量差を照合する)

第70版では、FK61_01の節点42で面積と長さの積を丸めた差が、内部3969の体積速度に伝わることを確認した。途中の丸めを省いた独立計算では体積速度差が1.07×10⁻¹¹から1.73×10⁻¹⁸ cm³/sに縮んだ。平滑前の3969だけを交換して両段を再計算すると、局所比較で出力1987までのPCMが揃った。次は節点42の補間開始時の断面積と目標を、測定線およびセルへ集約する過程から照合する。人手F2注釈とTSP・CSDの試聴は一次記録が得られた時点で再開し、物理MIDIは後日に回す。[体積速度の初差](../../research/experiments/chimera-rebuild/notes/tsp-fk61-node42-volume-source.md)・[第70版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第70版で節点42の体積速度の初差を照合する)

第71版では、FK61_01の描画前の測定線43の面積だけを交換し、節点42の平均断面積を上流に揃えた。補間開始時の平均断面積の交換で内部3969の体積速度も上流を再現した。1985フレームの目標面積には、セル境界・測定線位置・面積の組み合わせが効いた。次は描画前の測定線43の下側交点の差を輪郭線分と交差計算に分ける。人手F2注釈とTSP・CSDの試聴は一次記録が得られた時点で再開し、物理MIDIは後日に回す。[測定線とセルの集約](../../research/experiments/chimera-rebuild/notes/tsp-fk61-node42-area-origin.md)・[第71版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第71版で節点42の再標本化と補間を照合する)

第72版では、FK61_01の描画前の測定線43が選んだ下唇内面の線分を特定した。上流と試験版で同じ制御点から、Bernstein基底の重み付き和とde Casteljau法の反復補間がそれぞれの端点を再現した。局所計算で上流の評価順に揃えると交差と節点42の平均断面積が一致した。次は下唇内面の7標本の評価順だけを切り替えた通常CLIで、内部3969の体積速度と全発話PCMを照合する。人手F2注釈とTSP・CSDの試聴は一次記録が得られた時点で再開し、物理MIDIは後日に回す。[測定線43の交差](../../research/experiments/chimera-rebuild/notes/tsp-fk61-ray43-intersection.md)・[第72版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第72版で測定線43の交差とベジェ曲線を照合する)

第73版では、下唇内面の7標本の評価順を上流に揃えた通常CLIでFK61_01を描画した。内部3969の節点42の体積速度が上流に揃い、PCMの初差は1987から2937へ移った。最大絶対差は1.86×10⁻⁹で揃い、相違フレームは2309から2355に増えた。次は固定上流の2937を含む範囲で間引きとDC除去の入出力を採り、残る差が生じる過程を照合する。F2の人手注釈とTSP・CSDの試聴は一次記録が得られた時点で再開し、物理MIDIは後日に回す。[全発話PCMの比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-lower-lip-bernstein-render.md)・[第73版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第73版で下唇内面の評価順と全発話pcmを照合する)

第74版では、固定上流と試験版の出力段を先頭3072フレームで照合した。2937は直前フレームのDC出力の交換で揃い、放射の口端成分だけを交換した再計算でも先頭から2937まで一致した。放射差分とFIR係数の積の版間差が最大の内部5851付近を起点に、どの時間範囲の口端放射が2937に伝わるか調べる。F2の人手注釈とTSP・CSDの試聴は一次記録が得られた時点で再開し、物理MIDIは後日に回す。[2937の出力段](../../research/experiments/chimera-rebuild/notes/tsp-fk61-pcm2937-output.md)・[第74版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第74版でpcm2937の放射入力と出力段を照合する)

第75版では、FK61_01の内部5800〜5875の全2,926連続区間で口端流量だけを上流へ交換した。冒頭から2937までのPCMが一致した区間は73で、最短は5863・5864の2標本だった。次は5863〜5865の終端流入とR–L負荷の状態を採り、口端流量が分かれた箇所を照合する。F2の人手注釈とTSP・CSDの試聴は一次記録が得られた時点で再開し、物理MIDIは後日に回す。[2937に効く口端流量](../../research/experiments/chimera-rebuild/notes/tsp-fk61-pcm2937-lip-window.md)・[第75版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第75版でpcm2937に効く口端流量の時間範囲を照合する)

第76版では、FK61_01の5863〜5865で旧慣性流量の交換が各標本の口端流量を最も大きく動かした。5863の正味流入差の約97.4%は枝42→43で、5856からの正味流入をそろえると冒頭からPCM 2937まで一致した。次は枝42→43に入る旧圧差・枝の慣性流量・慣性と損失を切り分ける。F2の人手注釈とTSP・CSDの試聴は未登録で、物理MIDIは後日に回す。 [終端負荷の計測](../../research/experiments/chimera-rebuild/notes/tsp-fk61-pcm2937-terminal-load.md)・[第76版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第76版でpcm2937に効く口端負荷の入力を照合する)

第77版では、5863〜5865の枝42→43の流量差を運動量履歴、節点の圧力差、慣性、損失に分解した。5856の枝の初期状態だけを上流にし、口端を逐次計算すると冒頭からPCM 2937まで一致した。次は5840〜5856で開始点を動かし、初期状態の差を旧流量と旧慣性に分ける。F2・TSP・CSDの人手評価は一次記録が得られた時点で再開し、物理MIDIは後日に回す。 [枝の読解と計測](../../research/experiments/chimera-rebuild/notes/tsp-fk61-pcm2937-branch-drive.md)・[第77版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第77版でpcm2937に効く枝42から43への運動量を照合する)

第78版では、5840〜5856の全17開始点で、枝42→43の旧流量だけを上流に揃えるとPCMが冒頭から2937まで一致した。旧慣性だけを交換した全条件は2937で差が残った。次は口端放射の初差3971より前を含む3968〜5840を採り、枝の流量差が最初に現れる標本を確かめる。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [旧流量と旧慣性の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-pcm2937-branch-seed.md)・[第78版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第78版で枝42から43への旧流量と旧慣性を照合する)

第79版では、固定上流と下唇の評価順を揃えた試験版を冒頭から採取した。枝41→42の初差は3969、枝42→43と口端放射の初差は3971だった。枝41→42の3970の流量差が節点42の圧力差になり、3971の枝42→43の流量差を説明した。次は節点41に入る枝40→41へさかのぼる。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [発声開始の枝流量の観測](../../research/experiments/chimera-rebuild/notes/tsp-fk61-branch-first-difference.md)・[第79版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第79版で口端への枝流量の初差を照合する)

第80版では、3969の節点41の流入差を枝40→41から、3968の節点40の体積源までさかのぼった。観測時の丸めた体積を使う差は2.13×10⁻¹¹ cm³/s、積を丸めない計算で残る差は5.15×10⁻¹⁸ cm³/sだった。次は節点40の1標本だけで体積差の展開式を試し、局所流量と口端、全PCMの影響を比較する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [節点40の体積差と流入経路](../../research/experiments/chimera-rebuild/notes/tsp-fk61-oral-onset-inflow.md)・[第80版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第80版で口腔の節点40から41への流入差を照合する)

第81版では、節点40の3968だけで展開式を使った。体積速度の絶対誤差は1.50×10⁻¹¹から4.90×10⁻¹⁹ cm³/sへ減り、口端の3971の差も縮んだ。固定上流とのPCMの初差は両条件とも2937。全発話では展開式の有無で7フレームが変わった。次は節点42の体積源が分かれる制御境界5632から5863・5864までを、既存の採取データで照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [一標本の展開式の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-node40-expanded-volume.md)・[第81版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第81版で節点40の展開式と全発話pcmを照合する)

第82版では、制御境界5632以降の節点42・43について、初期状態、枝41→42の流量系列、局所体積源、係数を個別に交換した。枝41→42の系列のみで5863の口端流量差の約93.7%を再現し、冒頭からPCM 2937まで一致した。次は枝41→42の差が10⁻¹² cm³/sに達する5675付近から、上流の枝と節点41の体積源・圧力を調べる。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [制御境界以降の二節点の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control5632-mouth-flow.md)・[第82版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第82版で制御境界5632以降の口端流量差を照合する)

第83版では、節点38〜43の連成計算で、5675の枝41→42の差には節点38〜41の体積源が大きく効き、5863では枝37→38の流量系列が最大の入力になった。口端の全区間を出力へ戻すと、枝37→38の流量と節点38〜41の体積源をともに揃えた条件でPCMが冒頭から2937まで一致した。次は口腔と咽頭の接続まで採取して枝37→38への入力を調べる。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [六節点の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control5632-upstream-drive.md)・[第83版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第83版で口腔六節点から枝41への入力を照合する)

第84版では、口腔の全16節点で咽頭流入と口腔内で生じる体積源を切り分けた。5863では節点28〜37の体積源の交換だけで枝37→38の流量差の約81.2%を再現し、咽頭流入を加えると約99.0%を再現して冒頭からPCM 2937まで一致した。次は単独交換の影響が最大だった節点34で、制御境界5632・5760の長さ補間と断面積の変化を個別に照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [口腔16節点の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control5632-oral-inlet.md)・[第84版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第84版で咽頭から口腔への流入と体積源を照合する)

第85版では、節点34の体積速度には断面積の交換が強く効き、節点28〜37をまとめた場合の枝37→38には長さの交換が約8.6倍強く効いた。形状と咽頭流入を揃え、5632の体積源の二段平滑器の開始値も交換すると冒頭からPCM 2937まで一致した。次は前の制御境界5504から、共通の長さを決める弧長と5632の平滑開始値を追う。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [形状と平滑履歴の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control5632-oral-geometry.md)・[第85版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第85版で口腔の形状補間と体積源の開始値を照合する)

第86版では、5504のセル長と長さ目標が一致し、5632・5760の口腔長の差が唇側の弧長に由来すると確認した。5631の二段平滑状態には5504より前の履歴が強く効き、5503終了時の状態と5504〜5631の断面積を揃えるとPCMが冒頭から2937まで一致した。次は3968〜5503の体積速度を採り、5503に残る履歴への寄与を区間ごとに調べる。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [中心線と平滑履歴の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control5504-oral-history.md)・[第86版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第86版で口腔の中心線と5504より前の平滑履歴を照合する)

第87版では、3968〜5503の体積速度の差を二段平滑の重みで分解した。5120〜5247の寄与が最も大きく、直前の4992〜5119とは逆向きだった。後続区間を固定した比較では、5120〜5247の入力だけを交換するとPCMが冒頭から2937まで一致した。次は寄与の大きかった節点29・34に絞り、4992・5120の断面積の差を再標本化と速度制限の前後で追う。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [発声初期からの寄与の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-onset-to-control5504-volume-history.md)・[第87版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第87版で発声初期からの体積源の寄与を照合する)

第88版では、4992・5120の節点29・34で代表面積の差が再標本化直後に現れ、速度制限を経た値にそのまま残ることを確認した。前ブロックの反復加算の丸めにより、5120で節点29の開始面積差は前の目標差の32倍になり、節点34では符号が逆転した。2節点の開始面積の交換でPCMが冒頭から2937まで一致した。次は標本番号から直接計算する補間を隔離ビルドで試し、終端面積と体積速度、全PCMを照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [面積の再標本化と反復加算](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control4992-5120-area-targets.md)・[第88版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第88版で断面積の再標本化と反復加算の丸めを照合する)

第89版では、節点29・34の2ブロックに直接補間を適用し、4箇所の終端面積が目標と一致した。固定上流とのPCM初差は2937で、差のあるフレーム数は2,355だった。試験結果を保存し、固定上流のPCM再現を改善する変更としては採用を見送った。次は上流の隔離ビルドにも同じ直接補間を適用し、補間方式を揃えたときの体積速度と出力を照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [直接補間の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control4992-5120-indexed-area.md)・[第89版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第89版で標本番号から直接求める断面積補間を照合する)

第90版では、上流にも同じ直接補間を適用した。両版で補間を揃えると、面積の最大差は4分の1、平滑後の体積速度のRMS差は約50分の1になった。PCM初差は2937で、相違フレーム数は2,355だった。次は補間方式を揃えたまま、対象2節点で体積差の展開式を比較し、平滑前に残った差分演算の残差を調べる。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [補間方式を揃えた比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control4992-5120-indexed-area-paired.md)・[第90版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第90版で両版の面積補間を揃えて比較する)

第91版では、両版の節点29・34で体積差の展開式を比較した。幾何由来の差を引いた体積速度のRMS残差が約11万分の1になった。PCMの初差は2937で、全発話のRMS差の低下は主に16682の丸め差が消えたことによる。次は16682までの放射と出力段を採取し、この標本で両版が `f32` へ渡した値を比較する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [体積差の展開式の比較](../../research/experiments/chimera-rebuild/notes/tsp-fk61-control4992-5120-expanded-volume-paired.md)・[第91版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第91版で両版の体積差の展開式を照合する)

第92版では、16682の変換直前の値が上流の展開式で+2.540×10⁻¹⁵動き、隣接PCM値の中点を越えたことを確認した。上流の口端履歴だけの往復交換でも同じPCM変化が生じた。DC除去の入力と履歴の寄与はほぼ同じだった。次は展開式どうしで最大差が残る104883で、放射差と丸めの寄与を照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [出力段の採取と検算](../../research/experiments/chimera-rebuild/notes/tsp-fk61-pcm16682-rounding.md)・[第92版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第92版でpcmフレーム16682の丸めを照合する)

第93版では、全発話の放射と出力段を再計算した。両版が展開式のとき、PCMのRMS差は約16分の1になり、変換前のRMS差は0.34%増えた。104883には新しい1 ULPの差があり、複数ULP差は小振幅の956フレームに集中した。次は別の確認用発話FK61_02で、変換前誤差とPCM差の指標を照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [全発話の誤差分布](../../research/experiments/chimera-rebuild/notes/tsp-fk61-full-pcm-rounding.md)・[第93版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第93版で全発話の丸め前後の差を照合する)

第94版では、確認用発話FK61_02の通常レンダーを全144,727フレーム照合した。変換前の差が最大の31148ではPCMが一致した。129260の1 ULP差がPCM差の二乗和の99.999%を占め、複数ULP差の681フレームはいずれもPCM振幅が10⁻⁶以下だった。次は同文の男性体型MK61_02で変換前とPCMの差を照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [確認用発話の検算](../../research/experiments/chimera-rebuild/notes/tsp-fk61-02-full-pcm-rounding.md)・[第94版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第94版で確認用発話fk61_02の丸め前後を照合する)

第95版では、同文の男性設定MK61_02を全144,727フレーム照合した。女性設定に対するPCMの最大差は0.125倍、変換前のRMS差は1.585倍だった。男性側の複数ULP差の67フレームはいずれもPCM振幅が10⁻⁶以下だった。次は確認用12発話で変換前とPCMの誤差の順位、および振幅別ULP数を集計する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [同文の男女設定の比較](../../research/experiments/chimera-rebuild/notes/tsp-mk61-02-full-pcm-rounding.md)・[第95版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第95版で男性体型mk61_02の丸め前後を照合する)

第96版では、確認用12発話の変換前とPCMのRMS差の順位相関が0.147で、66発話対中30対が逆転した。全発話で変換前の最大差のフレームはPCMが一致した。次はCSDのen001aの先頭2句で、声源と初期姿勢を揃えた対照に同じ出力段の計測を適用する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [確認用12発話の集計](../../research/experiments/chimera-rebuild/notes/tsp-held-out-pcm-rounding.md)・[第96版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第96版で確認用12発話の丸め前後の誤差順位を照合する)

第97版では、CSDの `en001a` の先頭2句で、201,600フレームの出力を両版それぞれ独立に再計算した。丸め前とPCMの最大絶対差はいずれも初拍前の20,363フレームで約1.413×10⁻¹¹。句間の2,160フレームでは丸め前のRMS差が1.524×10⁻¹⁴で、PCMは一致した。初回の検算で欠けていた微小な履歴のゼロ化を反映し、その初回結果と修正後を監査する。次は最初の内部標本で口端流量が分かれた入力を特定する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [歌唱の測定と再現](../../research/experiments/chimera-rebuild/notes/csd-en001a-two-phrase-pcm-rounding.md)・[第97版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第97版でcsdの先頭2句の丸め前後を照合する)

第98版では、CSDの `en001a` の先頭2内部標本で口端の体積源から放射流量までを照合した。最初の口端流量差の99.99999%は負荷への流量の交換で解消し、標本0の体積差分の微差が二段平滑の履歴を経て標本1に残った。端の面積とセル長は最初の制御更新より前に分かれていた。次は断面の再標本化と口腔中心線の計算を初期化時に照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [口端負荷の入力と交換条件](../../research/experiments/chimera-rebuild/notes/csd-en001a-first-lip-load.md)・[第98版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第98版でcsd冒頭の口端流量差を照合する)

第99版では、`en001a` の初期化直後と最初の出力フレーム後の口端形状を照合した。測定線の中心座標は0番、区間距離は4番、累積弧長は6番で最初に分かれた。末端セルの長さだけの交換で最初の体積速度差を両方向で再現した。面積差には口腔の両端、格子の累積距離、測定線の面積が関わった。次は最初に区間距離が変わる測定線3・4と累積の丸めが分かれる測定線5・6で、中心座標を個別に交換する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [初期幾何と入力交換の測定](../../research/experiments/chimera-rebuild/notes/csd-en001a-initial-oral-geometry.md)・[第99版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第99版でcsdの初期口端形状を照合する)

第100版では、`en001a` の測定線4・5の中心のx座標を距離計算だけで交換した。4番の交換ではPCMが一致した。5番の交換では6番の累積弧長だけが1 ULP変わり、口端セル長と最初の体積速度は各版の対照と一致した。元のPCMとの最大差は両版ともフレーム134,534で1 ULP。次は6番の微差に影響される咽頭の再標本化と体積源を照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [中心座標の往復交換](../../research/experiments/chimera-rebuild/notes/csd-en001a-centerline-coordinate-swap.md)・[第100版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第100版でcsdの中心座標交換を照合する)

第101版では、`en001a` の測定線5の座標交換に伴う代表面積の変化を咽頭セル7だけに確認した。初期面積だけの交換で座標交換後の201,600 PCMフレームを両版とも再現した。目標面積だけの交換では通常描画と一致し、最初の2内部標本の体積速度は全条件で一致した。次は第1制御ブロックの体積速度と節点・両枝の係数を照合する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [咽頭セル7の実測](../../research/experiments/chimera-rebuild/notes/csd-en001a-pharynx-cell7-source.md)・[第101版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第101版でcsdの咽頭セル7を照合する)

第102版では、`en001a` の第1制御ブロック128内部標本で咽頭セル7と両隣の流量収支を照合した。両版ともコンプライアンスが標本0で分かれ、それだけを交換すると同じ標本の圧力差を再現した。体積速度の最初の差は上流12、研究版8だった。次は標本0のコンプライアンス一値の交換で口端と出力に現れる差を追う。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [第1制御ブロックの読解と測定](../../research/experiments/chimera-rebuild/notes/csd-en001a-pharynx-cell7-first-block.md)・[第102版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第102版でcsdの咽頭セル7の第1制御ブロックを照合する)

第103版では、咽頭セル7のコンプライアンスを標本0だけ交換して、`en001a` の口端とPCMまで照合した。上流の放射とPCMは通常描画に一致した。研究版では標本2で全節点の圧力が一致した後、標本3で圧力差が再び現れ、標本100で口端流量が分かれた。次は標本3の更新前に残る枝・壁の履歴を切り分ける。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [一値交換の測定](../../research/experiments/chimera-rebuild/notes/csd-en001a-pharynx-cell7-compliance-pulse.md)・[第103版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第103版でcsdの咽頭セル7の一値交換を照合する)

第104版では、`en001a` の研究版で標本2の圧力が全点一致しても内側2枝の流量が分かれることを実測した。標本3の計算直前に両枝の前回流量を通常へ戻すと、標本3〜7の圧力と全PCMが通常描画に一致した。次は確認曲 `en005a` の同設定対照に進み、放射、丸め前、PCMの差を比較する。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [枝履歴の測定](../../research/experiments/chimera-rebuild/notes/csd-en001a-pharynx-cell7-branch-history.md)・[第104版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第104版でcsdの咽頭セル7の枝履歴を照合する)

第105版では確認曲 `en005a` の全36句、3,544,616出力フレームで放射からPCMまでを照合した。利得抑制が両版で1,103,539フレーム作動し、その更新を含めて全PCMを再現した。丸め前の最大差は調整曲と共通する第1拍前の20,363、PCMの最大差は第36句の3,214,976の1 ULPだった。次は登録済みのもう一つの確認曲 `en035a` で区間別の比較を行う。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [確認曲の全曲測定](../../research/experiments/chimera-rebuild/notes/csd-en005a-full-pcm-rounding.md)・[第105版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第105版でcsdの確認曲en005aの全曲を照合する)

第106版では確認曲 `en035a` の全76句・5,590,588出力フレームを照合した。丸め前の最大差は `en005a` と共通する冒頭にあり、PCMの最大差は第18句の1 ULPだった。利得抑制は両版で同じ618,105フレームに適用され、その間のPCM差は2フレームだった。次は調整曲 `en012a` で同じ区間別比較を行う。F2の人手注釈とTSP・CSD試聴回答は未登録で、物理MIDIは後日に回す。 [en035aの全曲測定](../../research/experiments/chimera-rebuild/notes/csd-en035a-full-pcm-rounding.md)・[第106版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第106版でcsdの確認曲en035aの全曲を照合する)

第107版では調整曲 `en012a` の全46句、6,613,334出力フレームを確認曲2曲と照合した。3曲の同じ版どうしで冒頭76,672 PCMフレームが一致し、共有区間の20,363に丸め前の最大差があった。en012aのPCM最大差は第14句で1 ULPだった。次は `en001a` の観測を先頭2句から全50句に拡張し、区間別の誤差と利得抑制を比較する。 [en012aの全曲測定](../../research/experiments/chimera-rebuild/notes/csd-en012a-full-pcm-rounding.md)・[第107版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第107版でcsdの調整曲en012aを確認曲2曲と照合する)

第108版では `en001a` の採取を先頭2句から全50句・3,110,400フレームに広げた。両版とも第3句の準備直後のフレーム195,520から短い採取と分かれた。同設定の両版間では、丸め前の最大差は4曲共通の冒頭、PCMの最大差は第46句の拍の直前にあった。CSDの登録4曲の全曲比較が揃ったため、次は基準10母音で欠測だった `/ɔ/` の高域2ピークを、固定姿勢で掃引上限と刻みを変えて再計測する。F2人手注釈と試聴回答は未登録で、物理MIDIは後日に回す。 [en001aの全曲測定](../../research/experiments/chimera-rebuild/notes/csd-en001a-full-pcm-rounding.md)・[第108版の監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第108版でcsdの調整曲en001aを全曲へ広げる)・[基準10母音の欠測](../../research/experiments/chimera-rebuild/notes/ten-vowel-benchmark.md)

第4段階の追加計測では、固定 `/ɔ/` の上限を約7,791 Hzに広げると、高域2ピークの右側3 dB交点がいずれも得られた。連続周波数の独立計算では高いピークの帯域幅は108.97 Hz。低いピークの両交点の幅525.00 Hzには高いピークも入る。元の4,600 Hzでの欠測を保持し、追加計測と合わせて計画全体の第7版で照合する。次は保存された `/ɔ/` の連続母音列と固定発声に同一のLPC設定を適用し、第1ピークの差を分析条件から切り分ける。 [掃引範囲と密度の比較](../../research/experiments/chimera-rebuild/notes/vowel-open-o-high-bandwidth.md)・[連続母音列と固定発声の既存結果](../../research/experiments/chimera-rebuild/notes/ten-vowel-benchmark.md)

`/ɔ/` の連続母音列と固定発声を全フレームで再現し、両波形に32通りのLPC条件をそろえて適用した。0.300秒開始、16 kHz・18次・100 msでは第1ピークが620.01 Hzと619.81 Hzになった。旧条件の未丸め差49.07 Hzは、波形と分析条件を交換する2経路の平均で、波形15.64 Hz、分析設定33.42 Hz、固定発声で開始窓を戻した効果0.00007 Hzに分かれた。次は連続母音列で第1ピークが732 Hzになる有声窓を固定し、12〜18次の根と600 Hzの帯域幅上限を照合する。 [設定を交差した比較](../../research/experiments/chimera-rebuild/notes/vowel-open-o-lpc-matched.md)

連続母音列の `/ɔ/` の一つの窓を固定して12〜18次を比較した。共有ラグは全次数で一致し、追加ラグを反映した係数更新で選別前の根が動いた。低域の第1ピークは732.38 Hzから619.47 Hzへ移り、帯域幅の上限を外す対照でも同じ差が出た。2.3 kHz付近は、12次では帯域幅が1,108.80 Hzで600 Hzの上限から外れ、14次で初めて指定した3帯域に公開ピークが揃った。次は計画の固定LF対照に戻り、保存した /ɑ/ の口端流量と総放射の交流RMSに出た差を、同じ22周期の倍音電力と放射の複素和から照合する。 [LPC次数の比較](../../research/experiments/chimera-rebuild/notes/vowel-open-o-lpc-orders.md)・[固定LFの保存結果](../../research/experiments/chimera-rebuild/notes/fixed-lf-glottal-flow.md#結果)

固定 /ɑ/ の通常発声とLF駆動を再描画し、22周期の口端流量と放射を照合した。LFで増えた口端流量の基本波が高次成分の減少を一部打ち消し、実測RMSの低下は2.85%だった。差分後の口端成分の減少は総放射の交流平均二乗の減少の94.85%を占め、第6・第7倍音だけで差分後の口端成分の減少の62.24%に相当した。旧5%判定を保存する。次は660 Hz・770 Hzの声門入力と口端伝達の複素比を通常発声・LF・固定姿勢の線形応答で照合し、声源の倍音と声道の応答を切り分ける。 [倍音電力と壁の寄与](../../research/experiments/chimera-rebuild/notes/fixed-lf-radiation-harmonic-budget.md)

第6・第7倍音で、固定LFの声門流量の振幅は66.14%と44.23%低下した。複素伝達比の変化は0.038%と0.171%で、口端流量の複素差を両条件の平均で分解すると伝達比の項は0.016%と0.054%だった。同一姿勢の連続時間線形応答は固定上流・研究版CLI・独立節点計算で照合し、有声観測との差は振幅比で最大0.28%、位相で最大0.093°だった。次は零平均流の小入力を同じ固定声道の時間領域に入れ、標本内の更新順序と発声時の流れによる差を調べるための基準を取る。 [複素比と平均二乗の内訳](../../research/experiments/chimera-rebuild/notes/fixed-lf-harmonic-transfer.md)

同じ固定 /ɑ/ を静止状態から励振し、0.60秒の計測で660 Hzと770 Hzの口端流量の複素応答を、離散節点方程式と相対2.39×10⁻⁹以内で照合した。離散化による振幅差は +0.0313%、−0.0436%、位相差は −0.0071°、−0.0059°だった。0.20秒の初回は尾部の打ち切りで不合格となり、判定と冒頭標本を照合して引き継いだ。有声との差は離散時間の基準でも振幅最大0.248%、位相最大0.099°。次は平均流量を変えた固定声門流量に同じ小信号を重ね、気道内の有限流量に伴う差を測る。 [小信号インパルスと離散応答](../../research/experiments/chimera-rebuild/notes/fixed-alpha-discrete-impulse.md)

同じ固定 /ɑ/ で定常流を0から139.89 cm³/sへ変えると、660 Hzと770 Hzの口端の小信号振幅は0.0463%、0.1311%低下し、位相差は −0.1169°、+0.0982°だった。上流・研究版の差波形と、二次損失を定常点で微分した節点計算を照合した。保存した有声時の複素比との距離は、通常発声・固定LFの両方で、零流量の基準より1.10〜1.43倍になった。次は同じ平均流量で保存した声門流量の周期成分を咽頭入口に戻し、無励振時と同じ固定姿勢で口端の倍音を照合する。 [定常流の比較](../../research/experiments/chimera-rebuild/notes/fixed-alpha-mean-flow.md)

通常発声と固定LFの声門流量を0.60秒分再入力し、固定上流の咽頭入口圧・口端流量・鼻端流量・総放射が元の有声記録と全標本でビット一致した。同じ平均流量で22周期を繰り返した条件でも、第6・第7倍音の口端複素比を相対1.76×10⁻⁸以内で再現した。定常点を線形化した予測との差は複素比で0.209〜0.373%。次は枝ごとの二次損失を圧力差として観測し、660 Hzと770 Hzの口端応答にどの枝が寄与したか、線形節点方程式で再構成する。 [周期列と全履歴の再入力](../../research/experiments/chimera-rebuild/notes/fixed-alpha-periodic-flow.md)

固定 /ɑ/ の38枝について、二次損失の定常点からの残差を枝の圧力入力として合成し、660 Hz・770 Hzの口端応答と線形予測の差を相対3.83×10⁻¹¹以内で再構成した。咽頭の口側にある3枝（節点25→26、26→27、27→28）の寄与は複素差の方向に射影すると46.3〜48.2%。初回に見つかった枝の番号差は、向き付きの両端を照合して解決した。次はこの3枝の二次損失を、それぞれ定常点での値と傾きを保つ式に置き換え、口端応答への影響を実際に再描画して測る。 [枝の寄与と対応表](../../research/experiments/chimera-rebuild/notes/fixed-alpha-branch-loss.md)

同じ固定 /ɑ/ を隔離ビルドで再描画し、二次損失を定常点の接線に替えると、1枝で18.29〜19.05%、3枝で46.33〜48.21%の複素差が減った。選択枝の寄与だけを引いた予測との差は、実際の変化に対して最大0.165%。他の枝の残差の変化も加えると、相対5.68×10⁻¹²以内で測定値を再構成できた。次は定常点の値と傾きを保ちながら、低流量で圧力損失が流れに仕事をする区間をなくした対照で、口端の変化を測る。 [接線への置き換えと再描画](../../research/experiments/chimera-rebuild/notes/fixed-alpha-loss-tangent.md)

同じ枝で順方向の接線の負の圧力差をゼロにし、逆流には元の二次損失を使った。対象枝の負の仕事率は丸め許容差内でゼロになり、定常流対照の観測は接線時とビット一致した。660 Hz・770 Hzの口端応答と線形予測との差は、1枝で4.92〜14.41%、3枝で12.48〜36.51%減った。受動化で生じた複素変化は、枝の局所圧力差と流量の変化を合算して相対6.49×10⁻¹²以内で再構成した。次は定常点以下で元の二次損失、定常点を超える順流だけで接線を使い、高流量側を変えた分を単独で測る。 [受動な圧力損失と口端応答](../../research/experiments/chimera-rebuild/notes/fixed-alpha-loss-passive.md)

固定 /ɑ/ で定常点を超える順流だけを接線に替えた。660 Hz・770 Hzの口端応答と線形予測との複素距離は、無変更対照に比べて1枝で3.56〜11.66%、3枝で4.43〜29.45%減少した。低流量側も変更した前回の受動化との比較では、通常発声の770 Hzで低流量側の変更が距離を増やした。口端の複素差を枝の残差から再構成し、負の仕事率が0標本であることを確認した。次は定常点以下の順流だけを前回の受動式に替え、高流量側との効果の和を両側を替えた観測と比べる。 [高流量側の対照](../../research/experiments/chimera-rebuild/notes/fixed-alpha-loss-high-flow.md)

低流量側だけを受動式に替えた固定 /ɑ/ の対照では、通常発声の770 Hzで低流量側の効果が高流量側の効果を弱め、残る6条件で強めた。個別の複素差の和と同時変更との差は、同時変更の0.00428〜0.02399%だった。この差は4条件の枝の圧力残差から再構成できた。次は二次損失を元の式に置き、固定LFの声門入力の110 Hzだけを通常発声の複素係数に替えて再描画する。口端の基本波だけを置換したときの交流RMS低下6.40%が、入口の基本波を変えた場合にどこまで現れるかを測る。 [低流量側との相互作用](../../research/experiments/chimera-rebuild/notes/fixed-alpha-loss-low-flow.md)・[口端での基本波置換](../../research/experiments/chimera-rebuild/notes/fixed-lf-radiation-harmonic-budget.md#観測結果)

固定LFの声門入力の110 Hzだけを通常発声に合わせると、口端交流RMSは通常発声比6.394%低下した。口端の110 Hzを直接置換した計算との差は0.0054パーセントポイントで、元の固定LFの5%判定は不合格のまま保存した。口端の660 Hzと770 Hzも固定LF比で0.0202%、0.0233%変化した。次は同じ2入力の枝流量と圧力を取り、入力係数が等しい2周波数で生じた口端の差を、枝の二次損失の変化から再構成する。 [声門流量の基本波を合わせた描画](../../research/experiments/chimera-rebuild/notes/fixed-alpha-lf-fundamental.md)

基本波を変更した2条件の枝の圧力損失から、660 Hzと770 Hzの口端の複素差を相対1.05×10⁻¹¹以内で再構成した。咽頭の口側3枝（節点25→28）は差の方向への射影で42.87%・49.09%を占めた。逆流の符号と係数を補正する項は660 Hzで+5.48%、770 Hzで−6.69%寄与した。次は同じ110 Hzの変更を正負両向きと半振幅で与え、660 Hz・770 Hzの複素差のうち、符号とともに反転する成分と、正負を平均しても残る成分の振幅依存性を測る。 [基本波変更と枝ごとの圧力損失](../../research/experiments/chimera-rebuild/notes/fixed-alpha-lf-fundamental-branch-loss.md)

同じ110 Hzの差を倍率±1・±0.5で与えると、全振幅での偶成分は660 Hz・770 Hzで奇成分の27.22%・30.23%だった。半振幅の奇成分を2倍した複素差は全振幅から10.01%・15.71%ずれ、偶成分を4倍した差は46.33%・72.51%ずれた。事前予想と比較手順の判定を両方保存した。次は同じ波形の枝状態を観測し、二次損失の差の奇成分・偶成分を枝ごとに再構成して、逆流の補正がそれぞれのずれに寄与する割合を測る。 [入力振幅と奇成分・偶成分](../../research/experiments/chimera-rebuild/notes/fixed-alpha-lf-fundamental-amplitude.md)

5条件の枝状態から、口端の奇・偶成分と振幅則からのずれを相対1.19×10⁻¹⁰以内で再構成した。比例・二次からのずれの方向への射影では、同じ標本で流向が条件間で異なる場合の逆流補正が100.03〜100.10%を占めた。枝別では節点26→27と25→26の補正が全4比較で上位だった。次はこの2枝のゼロ流量付近の損失を滑らかにつなぐ対照を描画し、両周波数の振幅則のずれと定常流を比較する。 [5条件における枝の損失](../../research/experiments/chimera-rebuild/notes/fixed-alpha-lf-fundamental-amplitude-branch-loss.md)

節点26→27と25→26の絶対流量60 cm³/s以内で損失を平滑化した。定常流の観測はビット一致した。振幅則のずれは660 Hzの奇成分で28.45%、偶成分で4.77%、770 Hzの奇成分で19.85%増え、770 Hzの偶成分で12.28%減った。差は無変更時の流量に新旧の損失式を適用した圧力差でほぼ再現できた。 [2枝の損失を平滑化した対照](../../research/experiments/chimera-rebuild/notes/fixed-alpha-lf-fundamental-smoothed-branches.md)

同じ2枝・5入力で幅を30 cm³/sにすると、偶成分のずれは無変更比で660 Hzが0.78%減、770 Hzが7.92%増となり、幅60での増減と両方とも逆になった。4比較の再描画と固定流量による予測の差は最大0.020パーセントポイントで、定常流は幅間でもビット一致した。 [幅30の再描画](../../research/experiments/chimera-rebuild/notes/fixed-alpha-lf-fundamental-smoothed-width-30.md)

同じ5入力を固定 /i/ に与えると、660 Hz・770 Hzの振幅則のずれの寄与上位3枝が、4比較すべてで咽頭から口腔へ移った。最大は節点34→35で、流向が条件間で分かれた標本の逆流補正が99.30〜99.92%を説明した。 [固定 /i/ の枝損失](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-lf-branch-loss.md)

固定 /i/ の34→35・35→36を幅60 cm³/sで平滑化すると、770 Hzの奇成分のずれは17.15%減り、偶成分のずれは29.23%増えた。固定流量による予測は全4比較の増減方向に一致し、660 Hz奇成分の誤差0.259パーセントポイントは事前の0.2ポイント基準を超えた。 [固定 /i/ の平滑化](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-lf-smoothed-branches.md)

声門と気道を結合した固定 /i/ でも同じ平滑化を適用した。切替標本で口腔2枝の流量が変わり、21標本後に咽頭入口圧、22標本後に声門流量に差が出た。声門面積は全標本で一致し、切替後の圧力ゲートは上限に達していた。放射から独立計算したPCMは両版と一致した。 [通常の固定 /i/ の平滑化](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-coupled-smoothing.md)

肺圧だけを3.6 cmH₂Oに下げると、切替後の全観測が圧力ゲートの遷移域に入った。口腔の平滑化の差は、切替から21標本後に咽頭入口圧、22標本後にフィルタ後の圧力差、23標本後に有声度と声門面積に現れた。面積差を絶対5.00×10⁻¹⁶ cm²以内で独立に再構成した。PCMは面積差より先に変化した。 [低い肺圧での声門面積の変化](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-low-pressure-smoothing.md)

同じ平滑化で声門モデルの入力圧力差だけを無変更系列に置換すると、面積は無変更とビット一致した。面積を介するPCM差は全変化のRMSの13.23%、全変化方向への射影は+3.06%で、最初のPCM差は置換しても同じフレームだった。 [圧力差の置換とPCMの内訳](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pressure-replay.md)

同じ3条件で壁・口端・鼻端の放射を直接採取した。壁の放射は口端より先に変化した。発声の保存PCMでは口端成分だけで最初の差を再現し、全差方向への口端の寄与は比較ごとに95.73%、96.24%、88.18%だった。 [放射成分とPCMの分解](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-radiation-components.md)

通常の固定発声CLIに壁と合算の放射流量を任意で出力できる観測を加えた。無変更の固定 /i/ で放射成分とPCMを隔離ビルドの全標本に照合し、観測指定やブロックサイズでPCMが変わらないことを確認した。次は固定発声のWASMで同じ観測点のデータを取得し、既存の出力クロックとCLIのCSVに照合する。 [通常CLIの放射流量](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-cli-radiation.md)

固定 /i/ のWasmとAudioWorkletで壁・口端・鼻端・合算の放射流量と微分を取得し、全32,768出力フレームを通常CLIに照合した。観測の有無とホスト分割でPCMが一致し、既存の観測から出力フレームの時刻を確認できた。次は固定母音の画面から観測の有無を選び、PCMと放射を共通の時刻で調べられるようにする。 [WasmとAudioWorkletの放射観測](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-wasm-radiation.md)

固定母音画面で放射観測を選び、PCM・放射成分・放射微分を共通の出力フレームのカーソルで比較できるようにした。ChromiumとFirefoxで全区間と20 msの表示を照合し、保存したWAV・観測JSONと再実行ケースの全32,768出力フレームを通常CLIに照合した。次は同じ固定姿勢で口蓋帆の開口だけを変え、鼻端流量が出る条件を調べる。 [固定母音画面での放射観測](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-radiation-screen.md)

口蓋帆の入力を変えた固定 /i/ では、観測ポートから鼻端へ最初の流量が届くまでに21内部標本かかった。口蓋帆の輪郭も変わるため、壁の放射とPCMは鼻端より先に閉条件と分かれた。開閉両条件のPCMを固定上流とWasmに照合し、ポートの流量式を保存した圧力から検査した。次は輪郭を固定した対照で、ポートの面積変化による寄与を調べる。 [口蓋帆の開閉比較](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-radiation.md)

固定 /i/ で輪郭とポート面積を交差した4条件を比較した。輪郭だけを変えると通常開閉の最初の壁放射・PCM差を再現し、ポートだけを開くとPCMの初差はフレーム7から22へ移った。定常窓で輪郭により変わる開口効果は、通常開閉のPCM差のRMSの23.16%だった。次は440 Hzと2,310 Hzで線形伝達と発声時の流量・放射の複素比を調べる。 [輪郭とポート面積の対照](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-port-only.md)

固定 /i/ の4条件で、離散時間の線形応答を通常CLIの微小入力に相対1.20×10⁻⁶以内で照合した。2,310 Hzでは線形負荷と声門流量の項が159.38°ずれて打ち消し合った。通常発声と微小信号の総放射複素比の差は最大1.90%で、3%の事前予測は不成立だった。次は最も差が大きかったポートのみ開条件で、平均流量に基づく二次損失の補正を調べる。 [倍音の伝達と声門流量](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-harmonic-transfer.md)

固定 /i/ のポートのみ開条件の2,310 Hzで、ポートの平均流量による抵抗補正は、鼻端の複素伝達誤差を1.030%から0.430%に縮めた。低下率58.28%は事前基準の10%を満たし、固定上流でも再現した。観測したポート損失を与える診断では0.268%の残差があり、次は同じ窓で口腔・鼻腔の固定枝の二次損失が残差をどこまで説明できるか調べる。 [平均流量で線形化したポート損失](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-mean-flow-tangent.md)

固定発声CLIで指定区間の全節点圧と枝流量を観測し、上流と有向の節点対で照合した。同じ2,310 Hzでは口腔・鼻腔の二次損失を加えると鼻端の複素誤差は0.268%から0.185%になった。減少率30.78%は事前基準の50%に届かなかった。次は咽頭・咽頭口腔接続・梨状窩など、同じ発声の声門上で残る枝の損失を比較する。 [口腔・鼻腔の二次損失](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-oral-nasal-loss.md)

同じ2,310 Hzで声門上の61枝を照合した。咽頭内、咽頭口腔接続、梨状窩の二次損失を加えると、鼻端の複素相対誤差は1.85×10⁻³から2.59×10⁻⁸に下がった。前回の残差方向への射影は咽頭内が96.94%、梨状窩入口が2.62%、咽頭口腔接続が0.44%。両版が再現したこの診断を基準に、次は咽頭内の各枝の平均流量から接線抵抗を求め、時系列の損失を入力せずに鼻端の寄与を近似できるか検証する。 [声門上の枝損失](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-supraglottal-loss.md)

咽頭内17枝の平均流量から接線抵抗を求めると、鼻端の複素相対誤差は咽頭内損失を省いた場合の0.180%から0.334%に増えた。50%改善の予測は不成立だった。最大寄与枝22→23には逆流がなく、接線近似で欠けた圧力損失は変動流量の二乗の2,310 Hz成分に一致した。次は110 Hzと2,200 Hzなど少数の周波数の組を使い、咽頭枝全体で同じ二次損失と鼻端の応答をどこまで再現できるか測る。 [咽頭枝の平均流量と周波数混合](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-mean-flow-tangent.md)

同じ固定 /i/ の咽頭内17枝に3組の周波数対を共通で使うと、2,310 Hzの鼻端の複素相対誤差は0.335%から0.0392%へ下がり、88.28%の改善を両版で再現した。少数の倍音で再構成した波形では逆流した5枝を見落とし、別の9枝に逆流が現れた。次は肺圧だけを7.2から5.76 cmH₂Oに変えた新しい収録に同じ3組を適用し、鼻端近似の適用範囲と逆流判定を照合する。 [少数の周波数対による二次損失の近似](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-harmonic-pairs.md)

肺圧5.76 cmH₂Oの新規収録でも、固定した3組で2,310 Hzの鼻端誤差が0.268%から0.0241%に下がり、事前の50%改善を満たした。固定上流と研究版のPCM全32,768標本が一致した。再構成波形は実際に逆流した4枝をすべて見落とし、別の5枝で逆流を検出した。次は3組の二乗項を保ったまま、逆流を求める波形に低次倍音を追加し、2つの肺圧で逆流符号を照合する。 [肺圧を下げた新規収録](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure.md)

逆流補正用の波形に第3〜第6倍音を加えると、符号不一致が7.2 cmH₂Oで5,924から236標本、5.76 cmH₂Oで4,266から80標本に減った。両肺圧で逆流した枝をすべて検出し、鼻端誤差の増加は事前基準の5%以内だった。次は枝の平均流量を保ち、声門の流量を入力とする離散節点解で咽頭の10周波数を計算し、実測の倍音と逆流をどこまで再現できるか調べる。 [逆流用の低次倍音](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-reversal-low-harmonics.md)

観測した声門流量から、各枝の平均流量で線形化した節点解を求めた。咽頭17枝×10周波数の複素流量誤差は7.2と5.76 cmH₂Oで0.183%と0.139%。逆流のある枝を両肺圧で全て検出し、符号不一致は215と69標本だった。次は声門流量の平均を入力とする定常の枝方程式で声門上の平均流量を求め、実測の枝平均を使う条件と同じ10周波数および逆流を比較する。 [声門流量から求めた咽頭の倍音](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-from-glottal-flow.md)

声門の平均流量から61枝の定常流量を求めると、実測平均に対するL2相対誤差は7.2と5.76 cmH₂Oで2.71%と2.15%。その平均を使った咽頭の10周波数の複素流量誤差は0.174%と0.133%で、逆流枝はすべて検出した。鼻端の平均流量は9.63%と7.45%過大だった。次は声門流量と形状から予測した10周波数で二次損失の時間平均を近似し、鼻端の分流の偏りが減るか調べる。 [声門上の定常分流](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-steady-flow.md)

声門流量と形状で予測した10周波数を使い、流向別の二次損失を時間平均すると、鼻端の平均流量の誤差は7.2と5.76 cmH₂Oで0.157%と0.0843%に下がった。補正後の咽頭流量は0.184%と0.139%の複素誤差で、逆流枝を全て検出した。次は同じ波形から二次損失の2,310 Hz成分を求め、声門入力と形状だけで鼻端の複素放射をどこまで再現できるか調べる。 [予測波形から求めた平均損失](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-averaged-loss.md)

同じ声門入力と形状を使い、予測した枝の二次損失で2,310 Hzの接線解を一度補正すると、鼻端放射の複素誤差は7.2と5.76 cmH₂Oで0.241%と0.199%になり、両版で事前基準を満たした。予測損失を元の粘性モデルに戻す対照では、口蓋帆ポートの圧力源の差が鼻端誤差に最も大きく寄与した。次は同じポートの観測流量を10周波数に限定した場合と全帯域の場合を、予測波形の損失に照合する。 [予測損失による鼻端放射の補正](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-pharynx-predicted-radiation.md)

口蓋帆ポートでは、10周波数から外れた成分の影響が、二次損失の複素残差方向への射影で両肺圧とも100%を超えた。他の60枝の予測を固定してポートだけを全帯域の実測で置き換えると、鼻端誤差は0.247%から0.0373%、0.202%から0.0197%に低下した。次の対照では、ポートに第7〜18倍音だけを追加し、実測から抽出した波形と声門入力から予測した波形で、取り戻せる損失成分と鼻端への寄与を測る。 [口蓋帆ポートの帯域比較](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-port-bandwidth.md#実測)

口蓋帆ポートに実測の第7〜18倍音を加えると、選択外の周波数を省いた影響の91.96%と83.87%を回復した。声門流量から予測した追加成分では、鼻端の複素誤差が0.247%から0.0656%、0.202%から0.0442%に減った。追加した中で流量係数の絶対差が最も大きい770 Hzと1,320 Hzを対象に、枝の二次損失の圧力源を一度戻すと差が減るか確かめる。 [ポートの中間倍音の比較](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-port-middle-harmonics.md#実測)

770 Hzと1,320 Hzに二次損失を一度戻すと、口蓋帆ポートの2成分の複素流量誤差は95.7%と96.5%減った。鼻端の2,310 Hz誤差は10.5%と11.7%減り、事前の25%基準には届かなかった。実測損失を使った場合の低下も11.0%と12.0%だった。次は、各倍音の流量係数が2,310 Hzの損失と鼻端の誤差へどう効くかを、基準波形まわりの微分と個別差し替えで比較する。 [2周波数の損失補正](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-port-loss-feedback.md#実測)

ポートの第1〜22倍音を個別に置き換えた二次損失の変化は、微分で相対7.37%と2.05%以内に予測できた。単独では2,420 Hzが両肺圧で最も鼻端誤差を減らした。7.2 cmH₂Oの残差方向への射影で選んだ110 Hzと2,420 Hzの組は、5.76 cmH₂Oで誤差を28.3%増やした。次は位相に相当する直交成分を含めた複素残差の大きさで2成分を選び、別肺圧と2,420 Hz単独の対照で確かめる。 [倍音ごとの鼻端への感度](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-port-loss-sensitivity.md#実測)

7.2 cmH₂Oで複素残差の大きさを最小にする1,320 Hzと2,420 Hzの組は、有限差し替えでも231組中の最良だった。同じ組で鼻端誤差は両肺圧で31.3%と17.6%減った。5.76 cmH₂Oでは別の組を含む全231組の改善率が25%未満だった。次は固定した1,320 Hzと2,420 Hzに予測二次損失を一度戻し、ポートの実測係数を使う対照で得た改善をどこまで回復できるか調べる。 [複素残差による2倍音の選択](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-port-complex-pair.md#実測)

1,320 Hzと2,420 Hzに予測した二次損失を一度戻すと、ポート流量の誤差は両肺圧で97.0%と96.6%、鼻端誤差は30.8%と19.8%減った。実測差し替えの鼻端改善量に対して98.6%と112.7%を回復した。次は肺圧7.2 cmH₂Oと声道輪郭を保ち、音響ポート面積だけを0.30から0.15 cm²へ変えた収録を追加する。同じ2倍音の補正を再選択せずに適用して、流量と鼻端の精度を測る。 [選んだ2倍音の予測補正](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-port-selected-pair-feedback.md#実測)

音響ポートだけを0.15 cm²にすると平均流量が33.8%減った。固定した2倍音への予測補正で流量誤差は95.1%減り、鼻端誤差の減少は3.31%だった。同じ2成分の実測差し替えによる改善量の83.3%で、事前基準を満たした。事後の対照ではポートの全帯域の実測損失だけで鼻端誤差が0.528%から0.0542%に減った。次は同じ狭開口の基準で、平均、22倍音内の係数、選択外の成分に残差を分ける。 [狭開口での検証](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-narrow-port-feedback.md#実測)

ポートの差し替え順6通りで平均すると、0.15 cm²の2,310 Hz損失残差への寄与は平均流量が−2.51%、22倍音内の係数が96.21%、選択外の成分が6.30%だった。22倍音の係数だけを実測にすると鼻端誤差は0.528%から0.115%に減った。次はポートの平均と他の枝の鼻端への圧力源を同じに保ち、22倍音すべての接線解へ予測した二次損失を一度戻す。実測の係数差し替えで得た改善と、先行する2成分補正を対照にする。 [狭開口の残差の内訳](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-narrow-port-bandwidth.md#実測)

狭開口の22成分すべてに予測二次損失を一度戻すと、流量係数の誤差は91.1%、鼻端誤差は78.15%減った。実測係数へ差し替えた場合の鼻端改善量の99.999%に相当する。事後対照で補正済みの第1〜22倍音に実測の第23〜44倍音を加えると、鼻端誤差は0.00871%まで下がった。次は同じ平均のもとで第23〜44倍音を声門流量と形状から予測し、実測を加えた対照の改善をどこまで回復できるか調べる。 [狭開口の22倍音の補正](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback.md#実測)

狭開口の第23〜44倍音に予測二次損失を一度戻すと、この帯域のポート流量係数のL2誤差は7.995%から0.333%に減った。鼻端誤差は低域だけの0.11526%から0.00861%となり、実測上位倍音の追加による改善量の100.09%を回復した。ポートの平均と他60枝の圧力源を評価時に固定した。次は同じ肺圧7.2 cmH₂Oで開口0.30 cm²の保存収録に第1〜22倍音と第23〜44倍音の補正を順に適用し、流量誤差と実測差し替えで得られる鼻端の改善量を照合する。 [第23〜44倍音の補正](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-narrow-port-upper-harmonics.md#実測)

開口0.30 cm²でも第23〜44倍音の流量係数のL2誤差は2.926%から0.02581%に減った。収録した上位倍音を加えた対照では、2,310 Hzの鼻端誤差が0.03379%から0.03857%へ増え、改善量80%の仮説は両版で不成立だった。予測した上位倍音を使う場合も同じ誤差の増加を再現した。次は0.30 cm²でポートの上位倍音と他60枝の2,310 Hz圧力源を独立に切り替え、鼻端誤差への影響を4条件で測る。 [0.30 cm²での比較](../../research/experiments/chimera-rebuild/notes/fixed-vowel-i-velum-wide-port-upper-harmonics.md#実測)

第6段階で計画報告の直接シリアライズを実装した。確認用07の英語計画ABIの割り当ては初回3,555回から2,269回、再計画2,010回から724回。JSON、数値スコア、PCM、内部観測は基準に一致した。次は英語計画の `TextPlan` を中間の値に変換する527回を調べ、時刻・調音スコア・PCMをそのまま保てるか比較する。[報告の直接出力](../../research/experiments/chimera-rebuild/notes/worklet-live-tsp-planner-direct-report-44100.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#英語計画の報告を直接シリアライズする2026-11-22)

続いて英語の `TextPlan` を直接シリアライズし、中間の計画値の527回をゼロにした。確認用07の英語計画ABIは初回1,742回、再計画197回で、計画報告、数値スコア、PCM、内部観測が基準に一致した。次はJSON出力領域の再利用を比較し、計画の長さが変わる場合とエラー時の内容も確認する。[英語計画の直接出力](../../research/experiments/chimera-rebuild/notes/worklet-live-tsp-planner-direct-text-plan-44100.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#英語の型付き発話計画を直接報告する2026-11-22)

計画JSONの出力領域を再利用し、同じインスタンスで確認用07を再計画したときのJSON出力を9回からゼロにした。英語計画ABIの初回は1,742回、再計画は188回。短い報告と不正入力を挟んで元の入力のJSONとスコアを再現した。通常のTS関数は呼び出しごとにWASMインスタンスを作るため、次は同じページの連続する英語計画でインスタンスを共有する条件を、出力のコピーと辞書の切り替えも含めて比較する。[計画JSONの出力領域](../../research/experiments/chimera-rebuild/notes/worklet-live-tsp-planner-report-buffer-44100.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#計画jsonの出力領域を再利用する2026-11-22)

同じページの英語オフライン発話と実時間発話でWASM計画器を共有した。確認用07のコンパイルは2回から1回になり、計画・数値スコア・PCMと内部観測は基準に一致した。辞書変更と初回の取得失敗後の復帰も確認した。次は初回の共有取得を待つ二つの呼び出しのうち片方を停止し、もう一方の発話が完了する条件を比較する。[英語計画器の共有](../../research/experiments/chimera-rebuild/notes/worklet-live-tsp-english-planner-reuse-44100.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#英語のwasm計画器をページで共有する2026-11-22)

英語の初回WASM取得を保留して実時間発話だけを止め、オフライン発話が完了する条件をFirefoxとChromiumの44.1 kHzで確認した。停止側はWorkletノードの生成前にContextを閉じ、再開後とオフラインの調音計画・PCM・内部観測は各基準に一致した。次は現行ツリーと保存出力を使って段階別の完了条件を再照合する。[停止と再開の比較](../../research/experiments/chimera-rebuild/notes/worklet-live-tsp-shared-wasm-abort-44100.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#共有wasm取得を待つ実時間発話を停止する2026-11-22)

段階別の第3版監査を実行し、第2版の判定と近時の英語・歌唱・WASM停止の比較を含む169判定が通った。現行のWebビルドとブラウザ採取時のWASMが一致し、英語と歌唱の全量子でネイティブ描画中の割り当てゼロを確認した。次に必要な一次記録は実録音F2の人手注釈、人によるTSP・CSD試聴回答、物理MIDIの発音イベントと音響出力。[第3版監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-audit.md#第3版-現行のブラウザと描画を照合)・[第7段階の未確認の観測](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#未確認の観測)

第7段階の物理MIDIに向け、既存CoreMIDI入力を固有IDで選び、CoreMIDI受信・通常のWeb MIDI・Worklet採用時刻・CLIとのPCM比較を保存する入口を追加した。仮想入力で12判定を再現し、入力なしでは未観測を記録した。物理鍵盤と人による録音評価の一次記録が得られた段階で照合する。[受動計測](../../research/experiments/chimera-rebuild/notes/worklet-midi-coremidi-passive.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#既存coremidi入力の受動計測を用意する2026-11-22)

CSDの第2版試聴資料は、音源対応と18 WAVから求める資料IDを回答CSVの全行に記録する。第1版と音声・音源対応のバイト一致、資料IDの不一致と欠落の拒否、第1版の集計の回帰を確認した。第2版で記録した人の試聴回答が得られた時点で、調整用・確認用の区分を保って集計する。[CSD第2版の資料と検証](../../research/experiments/chimera-rebuild/notes/csd-listening-packet-id.md)

TSPのF2注釈の取込で、配布資料に付属する試験回答と未記入の雛形を人手注釈として扱う指定を拒否するようにした。試験回答の従来の集計を再現し、実録音に対する判定件数を合成対照と分けて確認できる。実録音6窓の判定は人の回答を取得後に照合する。[F2の取込検証](../../research/experiments/chimera-rebuild/notes/tsp-f2-human-intake.md)

第7段階の第5版監査で、16項目・61実行を照合し、受動MIDIの受信とPCM、CSD試聴資料と回答、F2試験注釈を元データから再計算した。入力なしと不正な回答指定は4件の不合格として確認した。今後は実録音F2の注釈、人によるTSP・CSDの試聴回答、物理鍵盤のイベントと音響出力が得られたものから、対応する資料と計測条件を照合する。[第5版監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第5版の照合)・[未確認の観測と取得手順](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#未確認の観測)

CSDの試聴回答は、人手区分を指定すると資料IDに加えて記入内容を照合する。未記入の雛形と既知の試験回答を5条件で拒否し、従来の音源別集計も再現した。届いた試聴回答は `--kind human` を指定し、試聴に使った資料の実行IDに結び付ける。[受け付け条件の検証](../../research/experiments/chimera-rebuild/notes/csd-listening-packet-id.md#人手回答として受け付ける条件)

第7段階のChirp cascadeで、呼気0の短い放射を口腔食道腔の音高追従で再現した。放射微分の最初の差は時間差分の丸めに由来した。くちばし全6セルの観測を通常CLIに追加し、入口枝と終端負荷を個別に計測した。終端への流入を固定し、コンプライアンスの時間正規化を揃えると8内部サンプル後の放射流量も一致した。その次のサンプルでは終端への流入が分岐した。[鳴禽の放射の読解と比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#くちばし入口と放射負荷の丸めを分ける)

鳴禽の終端へ入る直列枝を再計算し、押鍵9内部サンプル後の最初の流量差を前回運動量の時間換算の順序で再現した。先端の圧力を交換する対照では差を再現できなかった。通常CLIと固定上流の64点をビット照合し、予測と反証を保存した。[鳴禽の最後の直列枝](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#最後の直列枝で運動量の時間換算を照合する)

同じくちばし断面を保った176.4 kHzでは、制御時間をそろえると押鍵8内部サンプル後、通常の制御刻みでは7内部サンプル後に終端流入が分かれた。前回運動量の置換による説明は制御刻みに依存し、時間をそろえた条件では手前セルの前回圧で差を再現した。192 kHzの先行結果を保持し、3条件の96点を両版でビット照合した。[44.1 kHz出力相当の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#441-khz出力相当で最初の流入差を比較する)

176.4 kHzの235点制御で先行した口腔食道腔の圧力差は、体積差を体積速度へ換算するときの除算と乗算に由来した。最初は体積速度で1 ULP、低域通過後と腔圧で2 ULPの差となる。通常CLIに観測列を加え、両版・3条件の圧力96点を独立計算でビット照合した。[口腔食道腔の圧力差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#1764-khzの口腔食道腔で最初の圧力差を再現する)

176.4 kHzの実験用ビルドで体積速度換算だけを乗算に替えると、固定上流との腔圧の初差は押鍵1点後から14点後、放射流量は8点後から11点後になった。くちばし内部で先に残る差は前回運動量の時間換算で再現した。外部ディスク上で通常版と実験版をビルドし、3条件の通常CLIの出力と差分を保存した。[体積速度換算の連続描画比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#体積速度の換算を替えて放射まで追う)

体積速度の乗算版を基準にくちばし内部5枝の運動量の計算順を揃えると、235点制御の2番目のセルへの流入差は押鍵3点後から5点後に移った。入口には線形係数による差が残り、放射流量の初差は11点後から10点後へ早まった。256点制御では放射流量が16点すべて固定上流と一致した。[内部枝と放射負荷の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#くちばし内部5枝で運動量の計算順を替える)

176.4 kHz・235点制御の入口枝で線形係数の慣性項を乗算に替えると、固定上流との入口流量の初差が押鍵4点後から5点後、放射流量が10点後から11点後に移った。残る入口流量の1 ULPは前回運動量の時間換算で再現できた。通常CLIで描画した3条件の入口流量144点を独立計算と照合した。[入口枝の線形係数の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#くちばし入口の線形係数だけを揃える)

くちばし入口で持ち越し運動量の時間換算まで揃えると、176.4 kHz・235点と256点制御の全16点でくちばし6セルの圧力・流入および放射流量が固定上流と一致した。保存した放射流量から上流の式で微分を復元し、235点の最後に残る腔圧差を枝の流量の加算順で再現した。[入口運動量と残差の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#くちばし入口の前回運動量を揃える)

観測を64内部サンプルに延ばして腔の流量収支を上流順に揃えると、235点制御の腔圧差は15点後から33点後へ移った。放射の初差は18点後のままで、その時点の終端流入は一致した。負荷の分子係数の括りだけを揃えた再計算で、最初の放射差が28点後に移った。[腔の収支と終端負荷の分離](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#口腔食道腔の流量収支を上流順に揃えて64点を観測する)

先端負荷の分子係数だけを上流順に揃えて連続描画すると、235点制御で放射流量の最初の差は押鍵18点後から60点後へ、256点制御では23点後から24点後へ移った。235点制御では23点後に最後の枝へ戻った変化を、前回の先端圧の置換で復元した。次は気管側首部に4点後から残る流量差を調べる。[先端負荷と枝への戻り](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#くちばし先端負荷の分子係数を連続描画で揃える)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#先端負荷の分子係数を揃えて枝へ戻る差を測る2026-11-23)

通常CLIに気管端の観測を加えた。235点制御で押鍵4点後、256点制御で5点後に現れる首部流量の1 ULPを、両端の前回圧と流量を固定し、持ち越し運動量の時間換算順だけを上流と揃えて復元した。次は首部の換算を替えた連続描画で腔圧と放射まで確認する。[気管側首部の読解](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管側の首部流量で最初の差を切り分ける)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管側の首部流量を前回運動量まで分解する2026-11-23)

首部1枝の持ち越し換算を揃えた連続描画では、上流との首部流量の初差は235点制御で4点後から6点後、256点制御で5点後から25点後へ移った。235点制御の残差は線形慣性項、256点制御の残差は前回の気管端圧の置換で復元した。次は235点制御で首部の線形慣性項の変更が腔圧と放射へ及ぶか調べる。[首部の連続描画と残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管側首部の前回運動量を連続描画で揃える)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管側首部の持ち越し換算を64点で比較する2026-11-23)

首部の線形慣性項を上流の乗算に揃えると、235点制御の流量初差は6点後から14点後、腔圧差は38点後から53点後へ移った。放射の観測列は両制御で対照と全64点一致した。残った首部流量差を直前の気管端圧の置換で復元したため、次は気管末端の壁流量と直列枝の流入を採取する。[線形慣性項の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管側首部の線形慣性項を連続描画で揃える)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管側首部の線形慣性項を64点で比較する2026-11-23)

気管末端の収支では、235点制御で押鍵12点後、256点制御で13点後の最初の圧力差を、最後の直列枝からの流入の置換で復元した。直列枝流量の最初の差は前回運動量の時間換算順で再現した。通常CLIの観測を活用し、次は気管最後の直列枝の換算順だけを切り替えた連続描画を比較する。[気管末端の収支](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管末端の圧力を直列枝と壁の流量に分ける)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管末端の圧力差を直列枝と壁の収支で照合する2026-11-23)

気管最後の直列枝の運動量換算を揃えると、上流との流入の初差は235点制御で8点後から13点後、256点制御で13点後から14点後へ移った。256点制御では首部流量の初差が25点後から16点後へ早まり、放射流量は両条件とも対照と全64点一致した。次は一つ手前のセルの圧力収支を観測する。[直列枝の連続描画](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管最後の直列枝の運動量換算を連続描画で揃える)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管最後の直列枝の運動量換算を64点で比較する2026-11-23)

通常CLIで気管の内部セルを番号指定して圧力収支を観測できるようにした。セル14の圧力差は235点制御の押鍵12点後と256点制御の13点後で、セル13からの流入の単独置換で解消した。235点制御では流入の初差を持ち越し運動量の換算順で復元した。次はこの枝1本で換算を揃え、後続の変化を調べる。[内部セルの圧力収支](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管端の一つ手前のセルで圧力収支を照合する)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管セル14の圧力収支を両側の直列枝まで分解する2026-11-23)

セル13から14へ入る枝の運動量の換算順を合わせると、235点制御で上流との流入の初差が押鍵9点後から12点後へ移った。残った差は直前のセル13圧の置換で再現できた。両制御で腔圧と放射は対照に全64点一致した。次は内部観測をセル13にも指定し、その収支を調べる。[直列枝の換算順の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管セル13から14へ入る枝の運動量換算を揃える)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管セル14への流入枝の換算順を64点で比較する2026-11-23)

セル13と14の同時観測では、235点制御の11点後と256点制御の10点後に現れるセル13圧差を、セル12からの流入の単独置換で復元した。その流入差も持ち越し運動量の換算順で再現した。次はこの換算だけを一様な気管内の全15直列枝で揃えた描画を比較する。[気管セル13の収支](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#セル13と14を同時に観測しセル13圧の起点を調べる)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#気管セル13の差を同時観測で切り分ける2026-11-23)

全15気管直列枝で運動量換算を揃えると、固定上流との気管端圧初差は235点制御で13点後から34点後、256点制御で14点後から40点後へ移った。気管内で最初に残った圧力差は鳴管側セル0で、左鳴管からの流量の置換で復元した。次は左鳴管側ポートで流量の初差を調べる。[全直列枝の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#気管内の全直列枝で運動量換算を揃える)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#全15気管直列枝の運動量換算を64点で比較する2026-11-23)

左鳴管から気管への流量は235点制御で押鍵19点後、256点制御で18点後に1 ULP分かれた。気管支側半セルの慣性を逆数との乗算に替え、線形項へ反映すると両条件の流量を復元できた。次はこの計算順を適用した連続描画で気管セル0と放射への影響を測る。[左鳴管ポートの診断](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左鳴管ポートの慣性を気管支側の半セルまで分解する)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#左鳴管ポートの初差を気管支側半セルまで分解する2026-11-23)

左鳴管ポートの気管支側半セルに逆数との乗算を適用すると、235点制御の気管入口圧の初差は22点後から31点後、256点制御では27点後から39点後に移った。変更の影響は両条件で気管端と首部に届き、放射流量は対照と64点一致した。左ポートに残る1 ULP差は235点制御で持ち越し、256点制御で現在の慣性の時間換算を置換して復元した。次は235点制御の持ち越し項を連続描画で検証する。[連続描画と残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左鳴管ポートの気管支側半セル慣性を連続描画で揃える)

左鳴管の持ち越し運動量の時間換算を揃えると、235点制御では固定上流との流量初差が23点後から27点後、気管入口圧の初差が31点後から36点後へ移った。残った左流量差は直前の左気管支末端圧で復元した。256点制御では19点後の左流量差が現在の慣性の時間換算に残り、次はその線形項だけを連続描画で揃える。[持ち越し換算の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左鳴管の持ち越し運動量の時間換算を連続描画で揃える)

左鳴管の現在の慣性を時間換算する順序を揃えると、256点制御の左流量の初差は19点後から48点後へ移った。残った流量差は閉鎖後の弁の再開時に出て、直前の気管入口圧を置換して復元できた。同じ19点後の右流量差は残った。次は右ポートの気管支側の半セルを上流順に計算した連続描画で、右に残る差を分ける。[線形慣性の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左鳴管の線形慣性の時間換算を連続描画で揃える)

右鳴管の気管支側半セルの慣性を揃えると、256点制御の19点後の右流量差が4 ULPから1 ULPに縮んだ。235点制御では28点後の差が同じ値で残り、変更の影響は30点後から現れた。残った最初の右流量差は両条件で持ち越し運動量の時間換算の置換で復元できた。次は右の持ち越し項だけを連続描画で揃える。[右鳴管の半セル比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右鳴管ポートの気管支側半セル慣性を連続描画で揃える)

右鳴管の持ち越し運動量の時間換算を揃えると、右流量の初差は235点制御で28点後から30点後、256点制御では19点後から41点後に移った。残る差はそれぞれ直前の右気管支末端圧と気管入口圧で復元した。次は通常CLIで右気管支末端への流入を観測し、末端圧の最初の差が出た標本の収支を調べる。[右鳴管の持ち越し換算比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右鳴管の持ち越し運動量の時間換算を連続描画で揃える)

通常CLIに左右の気管支末端への流入を観測する項目を追加した。右末端圧の25点後と19点後、左末端圧の26点後と23点後の初差を、直列枝からの流入だけの置換で復元した。流入自身の初差は線形係数の慣性項に由来し、半セルの幾何項と時間換算を両方そろえると再現できた。次は右の直列枝で線形係数の慣性項だけを連続描画で揃える。[左右の気管支末端の収支](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左右の気管支末端の圧力を直列枝流量から再計算する)

右気管支の最後の直列枝で線形係数の慣性を揃えると、枝流入の初差は235点制御で19点後から26点後、256点制御で18点後から25点後に移った。残差は持ち越し項にあり、235点制御では慣性の幾何項と時間換算の両方を変更すると上流値を復元した。次は同じ枝の持ち越し項を連続描画で揃える。[右気管支の線形慣性比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右気管支の最後の直列枝で線形慣性を連続描画で揃える)

右気管支の最後の直列枝で持ち越し慣性も揃えると、固定上流との流入初差は235点制御で押鍵26点後から27点後、256点制御では25点後から29点後へ移った。残りは両条件とも直前の手前セル圧の置換で消えた。次はそのセルへの流入を観測し、先行する圧力の起点を調べる。[右気管支の持ち越し慣性比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右気管支の最後の直列枝で持ち越し運動量を連続描画で揃える)

通常CLIに左右の気管支の内部セルを指定する観測を追加した。右セル1圧の23点後と26点後の初差はセル0からの流入で復元した。両条件の流入は押鍵19点後に初めて分かれ、線形係数の慣性項の置換で復元できた。左セル1圧の初差は末端側への流出で復元した。次は右のセル0から1への枝の線形慣性を連続描画で揃える。[気管支内部セルの収支](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左右の気管支の手前セルの圧力を流入から再計算する)

右気管支のセル0から1へ入る枝で線形慣性を揃えると、両条件で19点後の流量差が消えた。次に差が出た235点制御の22点後と256点制御の25点後は、持ち越し項に上流順の慣性と時間換算の両方を使うと流量を復元できた。次は同じ枝の持ち越し項の影響を連続描画で確認する。[右気管支の内部枝の線形慣性](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右気管支のセル0から1への枝で線形慣性を連続描画で揃える)

右気管支のセル0から1への枝で持ち越し項を揃えると、流入初差は235点制御で22点後から30点後、256点制御で25点後から32点後へ移った。残差は双方で直前のセル0圧の置換で消えた。次は空気嚢から右気管支へ入るポートの流量を観測し、セル0圧の初差を圧力収支に分ける。[右気管支の内部枝の持ち越し運動量](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右気管支のセル0から1への枝で持ち越し運動量を連続描画で揃える)

左右の気管支セル0を観測し、右の空気嚢ポートの流量初差が235点制御で22点後、256点制御で30点後と分かった。どちらも持ち越し項を上流順に置換して流量が一致し、セル0圧の初差も流入だけの置換で復元した。次は右ポート1本の持ち越し項を揃えた連続描画で、セル0圧と下流を照合する。[空気嚢ポートの流量とセル0圧](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#空気嚢ポートと左右の気管支セル0の圧力収支)

右の空気嚢ポートの持ち越し項を連続描画で揃え、流量初差は235点制御で43点後、256点制御で44点後に移った。残った差を気管入口圧の収支までさかのぼると、235点制御は左鳴管からの流入、256点制御は気管セル1への流出でそれぞれ初差を復元できた。次は256点制御で気管セル1から2への流出と前回圧を比較する。[右ポートの持ち越しと下流の残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右の空気嚢ポートで持ち越し運動量を連続描画で揃える)

256点制御の気管入口圧の39点後の差をセル10の壁までたどった。そのセルの壁面積の計算順を揃えると、セル1から2への流量初差は38点後から49点後、気管入口圧の初差は39点後から47点後へ移った。残る入口圧の差は右鳴管流量から戻る。次は右鳴管の線形係数の時間換算だけを揃えた連続描画で、46点後の鳴管流量と47点後の入口圧を照合する。[セル10の壁流量と気管入口圧の比較](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#256点制御の気管入口圧の差をセル10の壁までたどる)

右鳴管の線形慣性の時間換算を揃え、256点制御の右鳴管流量と右末端圧が上流と全64点一致した。気管入口圧は60点後に初めて分かれ、左鳴管からの流量だけの置換で復元できた。左気管支末端へ入る枝は両条件の18点後に分かれ、線形係数だけの置換で上流に一致した。次はその枝1本の線形慣性を上流順に揃える。[右鳴管の時間換算と左側の残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#右鳴管の線形慣性の時間換算を連続描画で揃える)

左気管支末端の直列枝で線形慣性を揃え、押鍵18点後の初差を両条件で解消した。次の流量差は235点制御の23点後と256点制御の22点後で、持ち越し運動量の慣性の組み立てと時間換算を両方揃えると復元した。次に同じ枝の持ち越し項を連続描画で照合する。[左末端枝の線形慣性と残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左気管支末端の直列枝で線形慣性を連続描画で揃える)

左気管支末端の枝の持ち越し項も揃えると、左末端への流量初差は235点制御の23点後、256点制御の22点後から、両条件とも26点後に移った。残差はセル1の前回圧、セル1圧の初差はセル0からの流入で復元した。次に左セル0から1への枝を対象に、19点後の流量差を分母の線形慣性から照合する。[左末端枝の持ち越しとセル1の残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左気管支末端の直列枝で持ち越し運動量を連続描画で揃える)

左気管支のセル0から1への枝で分母の線形慣性を揃え、両制御の押鍵19点後の流量差を解消した。残った24点後の差は持ち越し項の置換で復元できた。次はその持ち越し項を揃え、セル0・セル1の圧力と、初差が早まった左鳴管流量を連続描画で比較する。[左内部枝の線形慣性と残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左気管支のセル0から1への枝で線形慣性を連続描画で揃える)

左気管支のセル0から1への枝の持ち越し項を揃え、両条件で24点後の流量差を解消した。残った30点後の差はセル0の前回圧だけで復元し、セル0圧の差は左の空気嚢ポート流量までたどれた。次は左ポートの持ち越し項の時間換算を揃え、22点後と27点後の流量差と下流への影響を連続描画で照合する。[左内部枝の持ち越しと空気嚢側の残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左気管支のセル0から1への枝で持ち越し運動量を連続描画で揃える)

左の空気嚢ポートの持ち越し時間換算を揃え、22点後と27点後の流量差を解消した。256点制御では左右の気管支、鳴管流量と気管入口圧が上流と押鍵後64点で一致した。放射流量の差が現れる前に後退差分が分かれ、保存流量へ上流順の時間換算を適用するとその初差が消えた。次は放射流量の後退差分の換算だけを連続描画で揃える。[左の空気嚢ポートと放射側の残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#左の空気嚢ポートで持ち越し運動量を連続描画で揃える)

放射流量の後退差分の時間換算を揃え、差が現れる最初の点を235点制御で9点後から60点後、256点制御で11点後から24点後へ移した。残る放射差はくちばし端への流入を置換すると消えた。くちばし入口の流量は、半セル慣性を上流の演算順で求める局所計算で最初の差が消えた。次はこの枝だけで慣性の組み立てを揃え、連続描画で放射まで照合する。[放射の時間換算とくちばし入口の残差](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#放射流量の後退差分を連続描画で揃える)

くちばし入口の半セル慣性を揃え、235点制御・256点制御でくちばし全セルと放射流量・後退差分が押鍵後64点すべてで上流と一致した。気管の微小な差は記録に残し、同じ実験版を既存の44.1 kHzの全コールに適用して、呼気を伴う入力で内部放射とPCMへの影響を比較する。[半セル慣性と放射の対応](../../research/experiments/chimera-rebuild/notes/songbird-chirps-onset-radiation.md#くちばし入口の半セル慣性を連続描画で揃える)

44.1 kHzの `chirps` を全区間で比較した。実験版では内部放射の初差が1033点から1089点へ移り、標準版・実験版・固定上流の全48,510フレームのPCMが一致した。30差分は倍精度の内部状態を観測する比較用に保持し、64点の機構検証と全区間の結果を第7段階の監査へ追加する。[全区間の放射とPCM](../../research/experiments/chimera-rebuild/notes/songbird-calls.md#くちばし入口まで揃えた実験版を全コールで比較する)

第7段階の第10版監査で、鳴禽の短区間と全区間を元のCSV・WAVから再照合した。第9版の16項目・69実行を維持し、計71実行を確認した。研究ワークスペースと `/tmp` の各156判定が通過した。実録音F2、TSP・CSDの試聴、物理MIDIは、それぞれ対応する人手回答または実機の一次記録が得られた時点で照合する。[第10版監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第10版で鳴禽の短区間と全区間を照合する)・[未取得の観測](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#未確認の観測)

人手評価のTSP・CSD試聴とF2注釈について、既存の評価者用資料をZIPにまとめた。展開したページで再生・図の表示・CSV出力を照合し、試験CSVが元の資料IDのまま通常取込を通過した。人手回答が得られた資料から、既存の実行IDを使って集計する。[評価用ZIPと検証](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#試聴とf2注釈の資料を別の環境で開く)

全体監査の第4版で、第7段階第10版の71実行、評価者用ZIP、現行WASMの停止・再開の再採取を照合した。88実行の照合と各182判定が通過した。第7段階の監査に一次記録を指定した場合は、全体監査も元CSVと収録結果を再計算して取得状況を更新する。[段階別の第4版監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-audit.md#第4版で人手実機の取得状況まで照合する)

第7段階の第6版監査は、鳴禽の最初の放射差とTSP・CSDの試聴集計を元ファイルから再計算し、16項目・67実行を照合した。別の作業ディレクトリからも126判定が通過した。一次記録が届いた評価から、対応する試聴資料、注釈窓、収録条件と照合する。[第6版監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第6版の照合)・[残る一次記録](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#未確認の観測)

TSPの試聴では、空欄行の増減や改行の変更がある既知の試験CSVも、記入内容の照合で人手区分から除外する。既存資料と元の試験集計を再利用でき、入手した回答は同じ資料IDのもとで受け付ける。[TSPの取込検証](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#人手回答と試験回答の記入内容を照合する)

第7版監査は、登録済みのTSP・CSD試聴資料について、人手区分で保存した集計の実行IDを指定できる。資料ID、音源、元CSVから再計算した評価を照合し、取得済みの資料を区分別に記録する。試験集計を指定する対照は両資料で拒否し、引数なしの通常監査は16項目・69実行を照合して128判定に合格した。[第7版監査と実回答を受領した際のコマンド](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第7版で試聴回答の実行を照合する)

第8版監査は、実録音6窓のF2注釈を集計した実行IDも受け付ける。資料・録音窓・元CSVを照合し、上流の既定設定とプリエンファシス無適用の採択との差を比較できる窓で求める。判定者の不一致、欠測、合成対照への記入は観測に応じて記録する。[第8版の監査と受領時のコマンド](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第8版でf2注釈を照合する)

第9版監査では、実機をUIDで指定した受動計測を渡し、入力の一覧、CoreMIDIとWeb MIDIの受信、Workletが採用したフレーム、保存ケースとCLIのPCMを照合できる。仮想対照で両離鍵形式を検証し、仮想入力と入力欠測は実機の証拠として拒否した。実機を接続したら、操作者が確認した機器情報を収録時に記録する。[第9版監査と再開手順](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第9版で物理midiの収録を照合する)

第6段階で「確認用07」の英語計画ABIを六工程に分けた。初回3,555回、再計画2,010回の内訳は、辞書索引が各17回、JSON関連が各1,822回。発音と句の計画の差1,544回をコア計画の先行処理で再現し、計画とPCMが一致した。[工程別の計測](../../research/experiments/chimera-rebuild/notes/worklet-live-tsp-planner-allocation-44100.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#英語計画abiの割り当てを工程別に測る2026-11-22)

第6段階で44.1 kHzの英語発話「確認用07」を計数した。ネイティブの英語計画ABIは3,555回、スコア開始ABIは118回で、描画中の全772量子はゼロだった。PCMと声門・声道の観測は基準版と一致した。[発話準備と描画の計数](../../research/experiments/chimera-rebuild/notes/worklet-live-tsp-allocation-44100.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#441-khz英語発話の準備と描画を計数する2026-11-22)

第6段階で人間の乱流源を初期確保し、48 kHzの歌唱 `Pop Dee` の全713量子でネイティブ描画中の割り当てがゼロになった。歌唱PCM・ABI観測・断面が基準に一致し、最大3件の乱流源でフィルタ状態と注入圧の一致も確認した。[乱流源の初期確保](../../research/experiments/chimera-rebuild/notes/human-noise-source-reserve.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#人間の気道で乱流源を初期確保する2026-11-22)

第6段階で断面標本に二つの領域を使い、48 kHzの歌唱 `Pop Dee` の割り当てを1,477回から、初回の乱流源登録1回まで減らした。出力の一致と、再標本化の失敗後に確定済みの断面を読み出せることを確認した。[断面標本の再利用](../../research/experiments/chimera-rebuild/notes/tract-area-buffer-reuse.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#断面標本の領域を再利用する2026-11-22)

第6段階で接触補正後の標本を再利用し、48 kHzの歌唱 `Pop Dee` は2,953回から1,477回へ割り当てが減った。接触グリッドの割り当てはゼロになり、断面・PCM・ABI観測は基準版に一致した。[接触標本の再利用](../../research/experiments/chimera-rebuild/notes/contact-sample-buffer-reuse.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#接触補正後の標本を再利用する2026-11-22)

第6段階の描画時の計測で、接触補正前の測定線の領域を再利用した。48 kHzの歌唱 `Pop Dee` の割り当ては4,429回から2,953回に減り、断面・PCM・ABI観測は基準版に一致した。[測定線の再利用](../../research/experiments/chimera-rebuild/notes/contact-measurement-grid-reuse.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#接触補正前の測定線を再利用する2026-11-22)

第6段階で、接触グリッドの割り当てを累積距離・測定線・接触標本に分けて計数した。口蓋沿い累積距離の領域を再利用すると、48 kHzの歌唱 `Pop Dee` の割り当ては5,905回から4,429回に減り、断面・PCM・ABI観測が変更前に一致した。[接触グリッドの内訳と再利用](../../research/experiments/chimera-rebuild/notes/contact-roof-buffer-reuse.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#接触グリッドの口蓋沿い累積距離を再利用する2026-11-22)

第6段階の声道更新で、咽頭・口腔の再標本化先も再利用した。48 kHzの歌唱 `Pop Dee` の割り当ては8,857回から5,905回。断面・PCM・ABI観測が変更前と一致し、通常のブラウザと5体型の回帰も通過した。[再標本化先の再利用](../../research/experiments/chimera-rebuild/notes/tract-resample-buffer-reuse.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#再標本化の咽頭口腔セル領域を再利用する2026-11-22)

第6段階の声道更新で、制限用の咽頭・口腔セル列を再利用した。48 kHzの歌唱 `Pop Dee` の割り当ては11,809回から8,857回に減り、PCMとABI観測は変更前とビット一致した。4条件の制限前後の断面系列も一致した。[セル領域の再利用](../../research/experiments/chimera-rebuild/notes/tract-limited-buffer-reuse.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#制限用の咽頭口腔セル領域を再利用する2026-11-22)

第6段階の48 kHz歌唱 `Pop Dee` で、語境界の25量子に各16件増えた割り当てを、接触補正後の声道再計算に照合した。計11,809件を段階別に説明し、PCMとABI観測値の一致を確認した。[段階別の計数](../../research/experiments/chimera-rebuild/notes/song-render-allocation-phases.md)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#48-khz歌唱の声道更新の割り当てを照合する2026-11-22)

Firefoxでデジタルゼロを出す別Contextを動かしたまま主Contextを止めると、3回とも同じcubebストリームの時計が進み、再開後も19,845 Hzの振幅比は約0.01539の狭帯域が続いた。[無音で出力を維持した比較](../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md#firefoxで無音の別audiocontextを動かし続ける)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#firefoxで無音の別audiocontextを動かし続ける2026-11-22)

Firefoxで別Contextから同相音を出し、主Contextだけの停止・再開を連続対照と3組比較した。全3回の停止中にcubebの予定時計と維持音が連続し、主Context再開後も19,845 Hzの振幅比は約0.01539から始まって狭帯域が続いた。[出力を維持した場合の比較](../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md#firefoxで出力を維持したまま主audiocontextを止める)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#firefoxで出力を維持したまま主audiocontextを止める2026-11-22)

Firefox 157.0の44.1 kHzでも3組を比較した。全6回でグラフと測定区間のcubeb PCMは入力とビット一致した。停止ありの3回はcubebが別ストリームに切り替わり、タップの19,845 Hzの比が約0.50000に戻った後、602〜616 msで低下した。連続対照は狭帯域が続いた。[Firefoxの3観測点](../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md#firefoxの441-khzでaudiocontextの停止と出力要求を照合する)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#firefoxの441-khzでaudiocontextの停止と出力要求を照合する2026-11-22)

Safari 18.6の44.1 kHzで連続再生とAudioContextの停止・再開を3組比較した。全6回でWeb AudioグラフのPCMが入力とビット一致した。タップでは停止・再開後に19,845 Hzの比が約0.50000へ戻り、再開から604〜614 msで再び低下した。連続再生では約0.01542の狭帯域が続いた。[Safariの停止・再開](../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md#safariの441-khzでaudiocontextの停止再開を照合する)・[再開手順](../../research/experiments/chimera-rebuild/progress.md#safariの441-khzでaudiocontextの停止再開を照合する2026-11-22)

[TSP確認用07のFirefoxネイティブ計時](../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md#確認用07のfirefoxネイティブ計時)で、定常区間の `Date.now()` が超過を示した20量子をネイティブの同じ区間へ照合し、すべて予算内と確認した。最初の量子は4試行とも3.553〜4.020 msで予算を超えた。

[TSP確認用07の実時間発声](../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md#確認用07の実時間発声と開始時刻)をChromiumとFirefoxで再生した。各841量子に欠落がなく、全107,527フレームのPCMが保存ケースのCLI再演と一致した。Firefoxの再実行ではミリ秒刻みの処理時間のp99が3 msだった。

[TSP確認用07の英語発話ケース](../../research/experiments/chimera-rebuild/notes/worklet-english-voice.md#確認用07の発話ケースの読み込みと再演)をChromiumのオフラインAudioWorkletで描画し、保存ケースを再演したCLIと全107,527フレームでビット一致した。冒頭440 msで独立計算の位相の折り返し90回を観測と対応付けた。

[TSP確認用07の上流既定の揺らぎ](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#確認用07で上流既定の音源変動を適用)を発話CLIで指定し、冒頭440 msでF0・位相・声門面積が一致した。全PCMの最大差は `1.16×10⁻¹⁰`。

[TSP確認用07の初期舌先対照](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#確認用07の初期舌先と発話前の放射)で、初期座標を上流の休止位置にそろえると発話前50 msのPCMが消え、両版の最初の非ゼロが出力フレーム2,439で一致した。変更前の4.5625 msの最大残差では、口端の放射が総振幅の約99.8%を占めた。揺らぎを0にそろえた条件で全発話のPCM最大差は `2.33×10⁻¹⁰`。

[TSP確認用07の出力ゲイン対照](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#確認用07の出力ゲインをそろえた通常描画)で、実際の描画時に女性体型の出力係数0.875を適用し、揺らぎをそろえた上流との二重母音の最大PCM差が約1.49×10⁻⁸になった。全215,054内部サンプルは再実装のゲイン変更前後で一致し、残差の最大は発話前の4.5625 msにあった。

[TSP確認用07の上流音源変動の対照](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#確認用07の-fine-で声門の揺らぎをそろえる)では、上流の揺らぎ3成分を0にすると、観測区間の声門位相が再実装と一致し、二重母音のPCM最大差が0.70616から0.05726に減った。残った差の大半は女性体型のゲイン差と対応した。

[TSP確認用07の子音遷移](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#確認用07の再開口と歯の乱流)では、両実装の唇の再開口が796 ms、歯の乱流の開始が800 msで一致した。既存の低エネルギー区間は両合成とも閉鎖中に収まった。人の試聴回答と、先行する母音に残る波形差の起点は引き続き照合する。

[TSP確認用07の語・音素境界の比較](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#確認用07の低エネルギー区間と語音素)で、主しきい値の低エネルギー時間差215 msのうち、録音内の語間 `soap → saves` が200 msを占めることを確認した。固定上流と再実装はこの語境界で連続した。人の試聴回答が得られたら、速さと文中の間の判断を対応付ける。

[TSPの試聴回答と時間計測の照合](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#試聴のテンポと区間長の照合)では、18対の試聴素材について、録音・固定上流・再実装の108区間を再計算した。主しきい値では2対で、総区間長の長短の向きが、低エネルギー時間を差し引いたときの向きと逆になった。資料IDを確認した人の回答が得られたら、確認用の対で速さと文中の間を照合する。

[TSPの比較試聴](../../research/experiments/chimera-rebuild/notes/tsp-active-duration-original.md#比較試聴のページと回答の取り込み)では、既存18対を聴くページと、資料IDで音源を照合する回答取込を検証した。区分別の集計は試験回答で照合済みで、人の回答は受領後に取り込む。

[全段階の完了条件の照合](../../research/experiments/chimera-rebuild/notes/plan-evidence-audit.md#完了条件と観測値の照合)で、75実行の直接判定を対応付け、一様管のCLI再実行、10母音・9遷移、5発話、5出力レートを確認した。固定LF・既存波動管・Firefoxの時間予算で残った不合格を記録した。人手F2注釈、TSP・CSDの試聴回答、物理MIDIは第7段階の未観測として引き継ぐ。

[第7段階の第4版監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第4版の照合)では、16項目・56合格実行と保存済みの不合格1件を照合した。LPCの候補変更と試験用注釈の出所を一次出力で確認し、実録音の人手F2注釈、TSP・CSDの試聴回答、物理MIDIは直接の観測が残る項目として記録した。

[実録音6窓のLPC次数比較](../../research/experiments/chimera-rebuild/notes/tsp-lpc-order-recordings.md#実測)では、`seems` の14次が採った約1 kHzの候補が12次では根の推定段から消え、採択は約2.3 kHzに移った。`again` では採択差は79 Hz未満。実録音の正解F2の注釈は残る。

[F2幅180 Hzと430 Hzの対照](../../research/experiments/chimera-rebuild/notes/tsp-f2-harmonic-bandwidth.md#実測)では、幅430 Hzの12次・15件で根の推定段からF2の近傍が得られず、14次・21件は固定規則で近傍を採った。追加の300 Hz未満条件では、幅430 Hzで固定規則が採れた13件がF3に移った。実録音の正誤判定は人による注釈が残る。

[F0だけを変えた既知F2の対照](../../research/experiments/chimera-rebuild/notes/tsp-f2-harmonic-spacing.md#実測)では、F2を2,075 Hzに保ったまま平均スペクトルの帯域ピークが164.06 Hz動いた。7条件すべてで理論上の最強倍音の位置と一致し、固定上流のLPCは21窓×2次数で最大76.87 Hzの差だった。

[TSP録音のF2注釈資料](../../research/experiments/chimera-rebuild/notes/tsp-f2-annotation.md#実測と保存先)を作成した。録音2語の6窓に既知対照1窓を加え、推定器の採択値を伏せた試聴・観測、CSVの入出力、判定者間の差の集計を検証した。人の回答は未取得。

[第7段階の第3版監査](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第3版の照合)で、前版37実行にChromeの標準許可画面とCoreMIDI、体型別デュエットの14実行を加え、16項目・51実行を照合した。保存した入力イベント・PCM・放射から合否を再計算し、現行Rust・Webビルドと第0〜7段階の既存監査も通過した。物理MIDI、人による試聴、録音の正解F2は確認が残る。

[体積差の展開式の対照](../../research/experiments/chimera-rebuild/notes/duet-mixed-volume-difference.md#実測)では、混合体型の後続224点で可動壁の局所流量の最大数値誤差が約2,700分の1に減った。固定上流とのPCM最大差は両条件で `1.46×10⁻¹¹` で、閉鎖・再開口と密閉圧縮の判定も通過した。展開式を比較差分として保存した。

混合体型の放射を1.2倍した[ピーク制限の比較](../../research/experiments/chimera-rebuild/notes/duet-mixed-limiter-gain-order.md)では、基準ゲインだけが6,954フレームで制限に入った。体型係数を制限の前と後で適用すると、同じ放射でもPCMに最大0.05520034の差が生じた。[通常レベルの放射成分の比較](../../research/experiments/chimera-rebuild/notes/duet-mixed-radiation-origin.md)では、体型ゲインをそろえた後に残る放射の微小差が、内部サンプル50,049の口端流量から生じることを確認した。[口端負荷の比較](../../research/experiments/chimera-rebuild/notes/duet-mixed-lip-load-origin.md)では、断面更新直後の流入に差を見つけ、セル体積差分と平滑化から両版の流入を再現した。

子ども声部の[声門乱流の振幅差](../../research/experiments/chimera-rebuild/notes/duet-child-glottal-noise-origin.md)は、乱流の枝断面積・流量と音源設定の差まで照合した。[初期舌先の比較](../../research/experiments/chimera-rebuild/notes/duet-child-initial-tip.md)では、歌唱前の最初の512サンプルに生じた流量・放射・PCMの差が、休止位置をそろえると消えた。[出力ゲインの比較](../../research/experiments/chimera-rebuild/notes/duet-child-output-gain.md)では、さらに子ども体型の係数0.875を描画時に適用し、全91,200フレームのPCM差が最大 `9.09×10⁻¹³` まで縮むことを確認した。[混合体型の乱流](../../research/experiments/chimera-rebuild/notes/duet-mixed-glottal-noise-origin.md)でも振幅差を枝断面積と流量から説明し、音源設定をそろえた主計測窓の差は最大 `1.20×10⁻¹² dyn/cm²` 未満だった。[混合体型の初期舌先](../../research/experiments/chimera-rebuild/notes/duet-mixed-initial-tip.md)も休止位置にそろえると、最初の512サンプルの無発声時の過渡が消えた。[混合体型の出力ゲイン](../../research/experiments/chimera-rebuild/notes/duet-mixed-output-gain.md)までそろえた全97,920フレームのPCM最大差は `1.46×10⁻¹¹` だった。

第7段階の照合を更新した。後続のTSPのF1・F2評価、子ども・混合体型のデュエット、Web MIDIの権限応答は[第2版の実行証拠](../../research/experiments/chimera-rebuild/notes/plan-evidence-stage7.md#第2版の照合)を参照する。手動発声では[Chrome標準の許可画面](../../research/experiments/chimera-rebuild/notes/worklet-midi-browser-prompt.md)、[CoreMIDIの仮想送信元からの押鍵・離鍵](../../research/experiments/chimera-rebuild/notes/worklet-midi-coremidi.md)、[押鍵中の単一入力削除](../../research/experiments/chimera-rebuild/notes/worklet-midi-coremidi-unplug.md)、[同じ音を保持する2入力の順次削除](../../research/experiments/chimera-rebuild/notes/worklet-midi-coremidi-shared-note.md)を照合した。実機入力と人による試聴は確認が残る。

第0〜7段階の64件の代表実行を、判定と成果のハッシュまで照合した。TSPは元の登録8件を含む18録音で発話区間長を測り、108区間の両端を独立計算で確認した。固定版MFAで調整用2録音と確認用4録音の語・音素区間を照合し、女性設定で `coat to` の語間90 msが /t/ の閉鎖に含まれることを確認した。CSDは調整用 `en001a` 全50句と確認用 `en005a` 全36句、計192音符の注釈を歌唱計画に照合し、両曲の録音・固定上流・候補でF0を比較した。第3倍音による誤推定は調整用の4音符で確認した。確認用では探索上限を狭めても全フレームの判定が一致した。2曲の音量包絡と全86句の有声開始を上流の通常報告に照合し、調整用は有声開始の丸め前の値まで一致した。両曲192音符で5帯域の電力比、H1−H2、メルケプストラム距離を照合した。全26,217窓で上流の非周期性を再現した。2曲の有声区間はビブラートの対象に届かず、1.6秒の合成母音で検出の有無を確認した。配布注釈で選んだ調整用en012aと確認用en035aでは、録音で29/44音と17/39音にビブラートを検出した。再実装の無声歯摩擦音 /θ/ を追加し、F0の第3倍音誤推定による過大な深さも1音符で確認した。TSPの18対に加え、CSDで音量をそろえた6区間18音源の試聴素材とCSV記録欄を用意した。人による試聴結果は未記入。4曲でF0探索上限だけを変え、H1−H2とビブラートの集約を照合した。狭い条件は合成の高い外れ値を減らし、譜面より高い既知音ではオクターブ誤りが出た。突き出した下唇を引き込むときの断面積の段差を18件再現し、前方測定線の交差が最初に切り替わることを確認した。同じ引き込みを発声中に通し、面積の速度制限と補間の後にも口端放射とPCMに差が出ることを確認した。前方測定線の交差対を組織の厚さとして扱う実験条件で18件の段差が消え、通常の破裂音と唇歯摩擦音を照合した。同じ唇閉鎖を口腔12・18・22セルで比較し、最小断面による閉鎖時刻の一致と圧力・放射スペクトルの差を確認した。声帯へ渡す圧差だけを固定する対照を行い、口端閉鎖中の面積パルスと流量の寄与を分けた。固定 /ɑ/・110 Hzで通常の声門流量の再入力が完全一致することを確かめ、固定LFの比較では総放射の交流RMSが31.61%、口端流量の交流RMSは2.85%低下した。口端流量は登録した5%基準に届かなかった。一様管と並列R–L終端をそろえた波動管比較で、主波束は4.3 µs以内、最初の4共鳴は1.21%以内に一致した。96 kHzの振幅差1.49 dBは0.9 dB基準を超え、192 kHzでは0.82 dBに縮んだ。口端体積流量をSIへ変換し、0.5・1・2 mでの理想円盤の軸上音圧を独立Rayleigh積分に照合した。4 kHzの位相差は、後退差分の半サンプルを補正すると最大7.45°から0.197°以内に縮んだ。空間格子と時間刻みを分けた測定では、3,250 Hzの振幅差は時間刻みだけで0.210 dB、セル長だけで0.455 dB縮んだ。空間効果は時間効果の2.17倍で、登録した3倍には届かなかった。口端の半セル慣性を補う周波数領域の対照で残差は0.256 dBとなった。半セル慣性を加えた時間領域では、96 kHz・40セルの16点の最大振幅差は0.619 dBに縮み、クーラン数0.9792でも無入力でエネルギーが放射抵抗の散逸分だけ減ることを確認した。高域の残留が増えた条件も保存した。96 kHzの実時間発声で呼気停止をずらし、予算超過を採取開始から1,000量子目に2回観測した。V8の呼び出し予算を変えた12回で、JS→WASMラッパーの同期コンパイルが指定量子に移り、PCMが一致した。96 kHzの同じ発声で、0フレームの事前呼び出しを1,000回行うと、全6試行で同期コンパイルを採取前へ移し、PCMと音響状態は一致した。999回では採取の最初の量子に移った。準備を研究用オプションとした。同じContextで先行音を流した12試行では2,359,296サンプルが独立計算と一致した。発声ノードの構築をまたぐコールバック間隔は11試行で基準最大値を超え、先頭の発声量子にはラッパーとは別のWASM関数本体の遅延コンパイルが残った。同じWASMインスタンスで使い捨ての128フレームを描くと、登録した10関数が全6試行で本番の先頭量子から事前描画へ移った。PCMと音響状態が一致し、対照に比べ先頭量子の中央値は0.757 ms短く、構築は0.583 ms延びた。採取末尾の区間を測り、約1.05 MBの送信は中央値で転送0.054 ms、複製0.291 msだった。事前解放でWASM関数2件のコンパイルが初期化側へ移った。18試行の末尾は全て予算内で、過去の超過8件の原因は確定していない。通常の96 kHz固定発声はFirefoxとChromiumでPCM・音響観測がビット一致した。Firefoxの従来時計では初回1試行が予算判定を超えた。別試行のネイティブ計測で、2 ms表示の18量子は0.177〜0.662 msだった。48 kHzの実時間IPA発話 `ɑpɑ` はFirefox・Chromium・CLIとオフラインで全49,828フレームのPCMが一致した。Firefoxのネイティブ計測で、発話の先頭量子は3.566〜3.624 ms、冒頭32量子を除いたp99は1.284〜1.344 msだった。発話終了後のJSを呼ばない2量子を切り分け、確定計測の129判定を通過した。48 kHzの実時間歌唱 `Pop Dee` はFirefox・Chromium・CLIとオフラインで全91,200フレームのPCMが一致し、予定拍も揃った。初回179判定を通過し、再実行でFirefoxの通常計時1件が予算を超えた。Firefoxの最初のWorklet呼び出しはContext上の176.0〜192.0 msで、Chromiumは42.7 msだった。同じ歌唱の開始区間を測り、48試行でPCM・観測・拍が揃った。接続までのブラウザ差149〜151 msに対して、歌唱計画のWASM呼び出しの差は2.0〜2.1 msだった。Firefoxの再開とWorklet登録で長い待ちが入れ替わり、その合計は中央値で179と177 msだった。再開要求直後からWorklet登録を始める対照ではPCMと停止・再開が一致した。Firefoxの接続時間の差は対の中央値で初回2.5 ms短縮、再実行5.0 ms延長で、20 ms短縮には届かなかった。FirefoxとChromiumの実時間歌唱でHTTPとWorklet評価を計時し、48試行のPCMと観測が一致した。Firefoxの全12計時試行で登録時間の99.35%以上が評価前にあり、並行登録では長い待ちがHTTP要求の前または応答送出の後に現れた。Firefoxのネイティブプロファイルで18試行の登録、HTTP、評価を照合した。17試行でチャネル開設から送信まで129.3〜189.8 ms、もう1試行では応答受信完了からチャネル完了まで173.9 msかかった。同試行の親HTTPチャネルでも173.7 msの待ちを確認した。同じチャネルを親子間で照合し、現行順のIPC付き再計測2試行で、親への到達からメインスレッドの受信処理まで131.4〜134.8 msかかった。並行登録では送信前の待ちの位置が、親の開設・接続準備・キャッシュコールバックの前に分かれた。IPCフロー付きの12試行で、親I/Oへの到達からタスク投入まで2.0〜12.8 µsと測った。現行順の2試行で投入から受信処理まで128.625 msと133.290 msかかり、その間の親メインのCPU使用率は採取区間で約98.4%だった。スタックで親の待ちを調べ、Playwrightが確認用のHTTP応答を展開している区間と対応づけた。確認用本文の読込を歌唱後に移すと、現行順のIPC待ちの中央値は148.654 msから約0.015 msに低下した。音声・観測・予定拍の一致を確認し、実時間歌唱の標準採取に反映した。この条件で先頭の描画量子を分割して測った。Firefoxで定常部との差の83.1〜86.8%はWASM呼び出しにあり、先頭量子のJS観測コピーは0.036〜0.047 msだった。同じWASMインスタンスの使い捨て状態で256フレームを事前描画すると、Firefoxの先頭量子のWASM時間の中央値は未準備の約42%になり、全6試行で全量子が2.667 ms以内だった。構築時間は未準備に比べて中央値で6.64〜6.75 ms増えた。PCMと観測が基準と一致したため、事前描画を指定できる実験用の入口にした。量子内の印を外した比較では、128フレームの事前描画でも先頭量子は8試行すべてで予算を超えた。64フレーム刻みの比較で最短の192フレームは全8試行で全量子が2.667 ms以内だった。Worklet構築は256フレームより、同じ組の差の中央値で1.05〜1.17 ms短かった。48 kHzの同じContextで基準音を鳴らし続ける比較では、192フレームの事前描画で構築をまたぐ先行音の処理間隔が同じ組の差の中央値で5.22〜5.23 ms長くなった。先行音と歌唱の波形は基準に一致し、事前描画の全8試行で歌唱の全量子が予算内だった。Firefoxの出力側を追加照合すると、構築前後の408要求で256フレームの要求とグラフ前進が一致した。192フレームの事前描画後は、次の出力要求が予定より5.31〜7.43 ms遅れた。その後の間隔は約5.33 msに戻り、8要求先でも開始時刻のずれが残った。AudioIPCの4組では、192フレームの事前描画直後のサーバー送信間隔が全4試行で10.662〜10.681 msとなり、クライアントの開始間隔との差は5.5 µs以内だった。Audio Clientを追加した再採取で、各17要求のソケット送受信をFirefoxのCore AudioのI/O区間に対応づけた。次のI/O開始間隔は未準備5.319 ms、事前描画10.658 msだった。出力PCMの照合に逆相のフレーム印を導入した。Firefox内部の再実行では34判定に合格し、既知の欠落・重複・無音を区別できた。自作のCore Audio出力では、48 kHz・512フレームの予算を超える14 msの待機を入れた2回で、次のデバイスのサンプル時刻が512フレーム分飛んだ。Firefoxのプロセスタップで有効なPCMを取得するには、macOSのシステムオーディオ録音許可を確認し、既知波形の対照から構築前後の照合へ進む。[出力PCMの観測とCore Audioの対照](../../research/experiments/chimera-rebuild/notes/worklet-live-song-output-pcm.md)生トレースと書き出しはRTL9210B-CGの作業領域を使い、抽出結果と元トレースを確かめてから再生成可能な一時XMLを整理する。[AudioIPCの読解、予備採取と再現手順](../../research/experiments/chimera-rebuild/notes/worklet-live-song-audioipc.md)MFAの中間領域、高密度CSV、評価資料の実体は作業用ディスクに置く。[段階別の照合](../../research/experiments/chimera-rebuild/notes/plan-evidence-audit.md)・[MFAの確認用比較](../../research/experiments/chimera-rebuild/notes/tsp-phone-boundaries-held-out.md)・[閉鎖と放射の計測](../../research/experiments/chimera-rebuild/notes/tsp-coat-to-closure.md)・[CSDの調整用F0比較](../../research/experiments/chimera-rebuild/notes/csd-acoustic-f0-en001a.md)・[CSDの確認用F0比較](../../research/experiments/chimera-rebuild/notes/csd-acoustic-f0-en005a.md)・[CSDの音量・時間比較](../../research/experiments/chimera-rebuild/notes/csd-envelope-timing.md)・[CSDのスペクトル比較](../../research/experiments/chimera-rebuild/notes/csd-note-spectrum.md)・[CSDのビブラートと非周期性](../../research/experiments/chimera-rebuild/notes/csd-vibrato-aperiodicity.md)・[CSDの長音と録音の比較](../../research/experiments/chimera-rebuild/notes/csd-long-note-vibrato.md)・[CSDの試聴](../../research/experiments/chimera-rebuild/notes/csd-listening.md)・[F0探索上限の全曲対照](../../research/experiments/chimera-rebuild/notes/csd-f0-search-sensitivity.md)・[前突した下唇の段差](../../research/experiments/chimera-rebuild/notes/lip-tuck-area-continuity.md)・[速度制限と放射の計測](../../research/experiments/chimera-rebuild/notes/lip-tuck-voiced-radiation.md)・[交差対の厚さによる対照](../../research/experiments/chimera-rebuild/notes/lip-tuck-crossing-thickness.md)・[閉鎖の格子数比較](../../research/experiments/chimera-rebuild/notes/tract-grid-lip-closure.md)・[声門振動への圧差入力](../../research/experiments/chimera-rebuild/notes/glottal-pressure-feedback.md)・[固定LFと口端流量・放射](../../research/experiments/chimera-rebuild/notes/fixed-lf-glottal-flow.md)・[波動管とFDTDの共通終端](../../research/experiments/chimera-rebuild/notes/uniform-waveguide-matched.md)・[理想円盤での軸上音圧](../../research/experiments/chimera-rebuild/notes/uniform-axial-observation.md)・[空間格子・時間刻み・口端半セル](../../research/experiments/chimera-rebuild/notes/uniform-grid-rate-sensitivity.md)・[時間領域の半セル慣性とエネルギー](../../research/experiments/chimera-rebuild/notes/uniform-outlet-half-cell.md)・[96 kHzの呼気停止とWASMの同期コンパイル](../../research/experiments/chimera-rebuild/notes/worklet-realtime-release-alignment.md)・[起動時のWASMラッパー準備](../../research/experiments/chimera-rebuild/notes/worklet-wasm-wrapper-warmup.md)・[先行音が鳴るContextでの起動](../../research/experiments/chimera-rebuild/notes/worklet-wasm-wrapper-shared-context.md)・[WASM関数本体の事前描画](../../research/experiments/chimera-rebuild/notes/worklet-wasm-dsp-warmup.md)・[採取末尾の区間計測](../../research/experiments/chimera-rebuild/notes/worklet-finalization-phases.md)・[FirefoxとChromiumの固定発声・計時](../../research/experiments/chimera-rebuild/notes/worklet-realtime-cross-browser-96000.md)・[48 kHzの実時間IPA比較](../../research/experiments/chimera-rebuild/notes/worklet-live-ipa-cross-browser.md)・[48 kHzの実時間歌唱比較](../../research/experiments/chimera-rebuild/notes/worklet-live-song-cross-browser.md)・[歌唱開始前の区間計時](../../research/experiments/chimera-rebuild/notes/worklet-song-startup-phases.md)・[再開とWorklet登録を重ねた対照](../../research/experiments/chimera-rebuild/notes/worklet-song-parallel-registration.md)・[Worklet登録とモジュール評価の計時](../../research/experiments/chimera-rebuild/notes/worklet-song-module-evaluation.md)・[FirefoxのHTTPチャネルと登録の照合](../../research/experiments/chimera-rebuild/notes/worklet-song-firefox-registration-native.md)・[親子プロセス間のHTTP通知](../../research/experiments/chimera-rebuild/notes/worklet-song-firefox-http-channel.md)・[IPCタスク投入と親のCPU時間](../../research/experiments/chimera-rebuild/notes/worklet-song-firefox-ipc-queue.md)・[Playwrightの応答本文の展開](../../research/experiments/chimera-rebuild/notes/worklet-song-firefox-ipc-stack.md)・[歌唱量子の処理区間](../../research/experiments/chimera-rebuild/notes/worklet-live-song-render-phases.md)・[歌唱の事前描画](../../research/experiments/chimera-rebuild/notes/worklet-live-song-render-warmup.md)・[歌唱の事前描画フレーム数](../../research/experiments/chimera-rebuild/notes/worklet-live-song-render-warmup-frames.md)・[先行音が鳴るContextでの歌唱](../../research/experiments/chimera-rebuild/notes/worklet-live-song-shared-context.md)・[出力要求の時刻とグラフ前進](../../research/experiments/chimera-rebuild/notes/worklet-live-song-output-callback.md)

FirefoxのCore Audio出力の調査では、共有Contextの未準備と192フレーム事前描画について、cubebが返すPCMとプロセスタップを同時に採取した。事前描画ではcubebのPCMが連続したまま次の予定要求時刻が256フレーム飛び、タップで照合した区間も256フレーム延びた。歌唱を使わず固定cubebの1要求に8.4 msの待機を加える対照でも、この関係を再現した。完全にゼロだった区間はFirefoxで161フレーム、固定cubebの対照で162フレームだった。機器端子の波形と聴感は未測定。[Firefoxの同時採取](../../research/experiments/chimera-rebuild/notes/worklet-live-song-paired-output.md#実測)・[歌唱を使わない対照](../../research/experiments/chimera-rebuild/notes/cubeb-output-callback-probe.md#歌唱を使わないプロセスタップの同時採取)

## 初回の着手順序

1. 上流の固定コミットを確認し、一様管テスト、母音レンダー、IPA の VCV、歌唱とテレメトリの小例を再実行する。計測器にも版を付けて比較基準を登録する。
2. `physics.rs`、`AirwayNetwork::step` の固定管に必要な部分、`airway/frequency.rs`、対応するテストを読み、一様管の節点と枝、単位、時刻、境界、放射の式を一枚の技術ノートにまとめる。
3. 第0段階の CLI で一様管のケースを読み込み、条件をログに出せることを確認する。第1段階では、まず時間更新から独立した共鳴の計算を用意し、次にインパルスの時系列と照合する。ここまでのコード、測定、残る差を一件の実行記録として残してから分岐へ進む。
