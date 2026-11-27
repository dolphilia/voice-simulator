# CHIMERA の発声原理とコードの読み順

対象は[調査ガイド](README.md)で固定した `c6147d0` です。人間の発声は、音素や演奏入力から調音器官と呼気の目標を作り、声門・口腔・鼻腔をつないだ気道で圧力と体積速度を計算して作ります。発話と歌唱で同じ音響コアを使うため、音素の並べ方、調音のタイミング、気道の数値計算をそれぞれコード上で追えます。[上流の音響設計と出典](upstream/docs/architecture.md)

```text
英語テキスト・IPA・歌詞と音符       舌・唇・顎の直接操作
               │                             │
               ▼                             │
        音素・音節 → ジェスチャー列 ────────┤
                           ▼
              調音器官の状態 → 声道断面積と長さ
                           │
        肺圧・声門面積 ──▶ 分岐気道の FDTD ──▶ 口・鼻・壁からの放射
               ▲           │                            │
               └─── 声門前後の圧力差                      ▼
                                                 間引き・出力処理 → PCM
```

## 1. 入力から声道形状まで

1. **音素と音節**。発話では `tokenize_ipa` または `EnglishG2P` を入口とし、英語は CMUdict と綴り規則で IPA に変換します。歌詞は `read_lyrics` で文字体系ごとのフロントエンドを呼び、音節の頭子音・核・末子音などを作ります。この版の歌詞入力には英語、韓国語、ロシア語、中国語（漢字・声調付きピンイン）の系統があります。日本語の調音比較を始めるなら IPA 入力で対象音素を指定し、CLI が表示する `warning` と音素時刻で実際に計画された音を確認できます。[IPA](upstream/crates/chimera/src/phonetics/ipa.rs)・[英語 G2P](upstream/crates/chimera/src/phonetics/english.rs)・[歌詞のルーター](upstream/crates/chimera/src/phonetics/syllables.rs)・[言語別の仕様](upstream/docs/language-front-ends.md)
2. **時間付きの調音目標**。`plan_utterance` / `plan_phrases` は音素の区間、持続時間、韻律を決め、重なり得る `Gesture` を作ります。歌唱の `plan_song` は音符の時刻に母音を合わせるための先行子音などを配置します。`GestureScore::blend_all` がその時点の有効度と強さで目標を混ぜ、`ArticulatorBank::step` が臨界減衰型の二次系で目標を追います。ジェスチャーは器官の位置だけでなく、呼気、声門の開大・閉鎖、F0、ビブラートなどにも作用します。[発話の計画](upstream/crates/chimera/src/phonetics/planner.rs)・[持続時間](upstream/crates/chimera/src/phonetics/durations.rs)・[歌唱の計画](upstream/crates/chimera/src/phonetics/sing.rs)・[ジェスチャー](upstream/crates/chimera/src/control/score.rs)・[調音運動](upstream/crates/chimera/src/control/articulators.rs)
3. **形状から断面積**。`HumanVocalTract::compute` が矢状面の内壁・外壁を作り、咽頭は水平、口腔は放射状、歯と唇の付近は垂直の測線で壁間距離を求めます。断面積は部位別の経験式 `A = α d^β`、唇は楕円開口で近似します。`resample` は気道セルごとに 8 点の調和平均を取り、狭窄を捉える最小面積も別に渡します。`HumanAirway::commit` が開閉速度とシミュレーション用の最短管長を制限します。成人男性・成人女性・子どもの `BodyMix` は器官の寸法と母音の目標姿勢に効きます。[形状と面積則](upstream/crates/chimera/src/anatomy/human.rs)・[面積の反映](upstream/crates/chimera/src/voice/human_airway.rs)・[母音の調整値](upstream/crates/chimera/src/phonetics/vowelTargets.generated.json)

## 2. 肺圧と声門の結合

音声ループの入口は `HumanVoice::render` です。呼気ゲートとジェスチャーが肺圧の目標を決め、肺の圧力境界は肺ポート流量の低域成分で補正されます。この補正によって、下気道の定常流抵抗と気管の音響的な終端に異なる抵抗を持たせています。声門は気管末端と咽頭入口の間の可変ポートです。[人間音声のループ](upstream/crates/chimera/src/voice/human_voice.rs)・[下気道とポート](upstream/crates/chimera/src/voice/human_airway.rs)

各内部サンプルで `ParametricGlottis::next` は声門前後の圧力差 `p_sub − p_supra` を受け取ります。指定された F0 を基に位相を進め、開放率、立ち上がりと閉鎖の形、ジッターなどで周期的な**開口面積**を作ります。圧力差を平滑化した値、声帯の開き、閉鎖指令で振動成分を調節し、漏れや静的開口を加えます。面積を受け取った気道ネットワークが実際の**声門流量**を次の半ステップで解きます。口腔を狭めると声門上圧にも影響し、有声摩擦音や有声閉鎖音で周期成分が弱まる経路があります。この版の人間声帯はパラメトリック面積パルスで、二質点声帯は上流設計書に記載された構想です。[声門ソース](upstream/crates/chimera/src/sources/glottis.rs)・[有声摩擦音の回帰テスト](upstream/crates/chimera/tests/voiced_fricatives.rs)・[上流の実装範囲](upstream/docs/architecture.md)

## 3. 分岐気道の FDTD

### 空間の表現

肺 → 気管 → 声門 → 咽頭 → 口腔 → 唇が主経路です。咽頭から、軟口蓋の可変ポートを通る鼻腔と、先端が閉じた梨状窩が分岐します。上顎洞は鼻腔の一地点に首管でつないだ空洞です。`HumanAirway::new` が接続を作り、`AirwayNetwork` が節点ごとの圧力 `p`（dyn/cm²）と枝ごとの体積速度 `U`（cm³/s）を持ちます。コードの長さと面積は cm と cm² です。画面の頭部断面は調音幾何を表示し、音響計算の空間は管の一次元断面列とその分岐で構成されます。[人間の気道接続](upstream/crates/chimera/src/voice/human_airway.rs)・[ネットワークのデータ構造](upstream/crates/chimera/src/airway/network.rs)・[物理定数](upstream/crates/chimera/src/physics.rs)

### 時間の更新

`AirwayNetwork::step` は、節点圧力を整数時刻、枝流量を半ステップに置くスタガード格子のリープフロッグ法です。内部時間刻みを `Δt` とすると、一回の更新は次の順です。[時間更新のコード](upstream/crates/chimera/src/airway/network.rs)

1. **形状と体積**。断面積、最小断面積、区間長を内部サンプルごとに目標へ線形補間します。セル体積 `V = A Δx` の変化を流量源 `−ΔV/Δt` に変換します。閉鎖に近いセルでは押し出す量を開いた隣接セルへ配り、配分後の量を二段のローパスで平滑化します。
2. **乱流源**。前の半ステップの流量と開口面積から各狭窄のレイノルズ数を求め、閾値を超えた成分に帯域制限ノイズを掛けて枝へ直列圧力源として加えます。声門の噴流、声門より上の狭窄、歯に当たる噴流では注入位置と帯域が異なります。前歯のノイズは噴流の速度と渦の大きさで帯域が動きます。[ノイズ源の位置と帯域](upstream/crates/chimera/src/voice/human_airway.rs)・[Krane の原論文](https://doi.org/10.1121/1.1862251)
3. **枝の流量**。通常の枝では、隣接セルの半区間を直列に足して慣性 `L = ρ/2 (Δxₐ/Aₐ + Δxᵦ/Aᵦ)` を求めます。新しい `U` は `(L/Δt + R)U + k |U|U = pₐ − pᵦ + p_noise + Φ_old/Δt` を符号別の二次式で解きます。`R` は線形抵抗、`k` は進行方向に応じた収縮・拡大損失です。`Φ_old` は前ステップの `L U` を基本とし、慣性低下時の既定の安定化処理では新しい `L` と前の `U` の積を使います。閉鎖した枝は流量と運動量をゼロにします。
4. **壁と節点圧力**。壁を質量・ばね・ダンパで近似して壁流量 `U_wall` を求めます。節点は音響コンプライアンス `C = V/(ρc²)` と正味流入から圧力を更新します。通常節点なら基本形は `C dp/dt = ΣU_in − ΣU_out − U_wall − dV/dt` です。分岐は局所振動が時間刻みを超えないようコンプライアンスに下限を設けます。閉鎖セルには別の圧力緩和処理があります。
5. **放射と出力**。口と鼻の終端に並列 R–L 放射負荷を付け、節点と Crank–Nicolson 法で結合します。口・鼻と重み付きの壁流量を加算し、その時間差分を放射信号とします。これは任意スケールの放射圧の近似です。`HumanVoice` は Kaiser 窓付き sinc フィルタで間引き、出力ゲイン、25 Hz の DC 除去、ピーク抑制を経て `f32` を返します。[間引き](upstream/crates/chimera/src/airway/decimator.rs)・[出力段](upstream/crates/chimera/src/voice/human_voice.rs)

48 kHz 出力の CLI 例では気道を 96 kHz で更新し、調音と幾何を出力 64 サンプルごと（約 1.33 ms）に計算します。`Engine` では `oversample_for` が内部レートを 60 kHz より高くする最小の整数倍率を選びます。管のセル数と最短長も `c Δt / Δx` を基に決めます。`Engine::render` にある 128 サンプル単位のスケジューラ処理は、幾何の 64 サンプル更新とは別の周期です。[時間刻みと音声ループ](upstream/crates/chimera/src/voice/human_voice.rs)・[セル数](upstream/crates/chimera/src/voice/human_airway.rs)・[ブロック処理](upstream/crates/chimera/src/engine.rs)

## 4. フォルマントと校正

| 観測値 | どう得るか | 読む場所 |
| --- | --- | --- |
| 固定姿勢の伝達関数 | 目標の断面積で線形化した回路を周波数ごとに木として解く。UI では声門の枝を切り、咽頭入口に単位体積速度を注入する | [線形化と木の計算](upstream/crates/chimera/src/airway/frequency.rs)・[WASM からの呼び出し](upstream/crates/chimera-wasm/src/api.rs) |
| 調整済みの調音目標 | 文献等の母音フォルマントに合わせ、舌・顎・唇などの姿勢を Nelder–Mead 法で探索する。`vowelTargets.generated.json` は結果の姿勢とモデル値を持つ | [基準母音データ](upstream/crates/chimera/src/phonetics/vowel_data.rs)・[目的関数と校正](upstream/crates/chimera-cli/src/calibrate.rs) |
| 合成波形のフォルマントと F0 | レンダー済み WAV に相当する PCM の短時間フレームから LPC と YIN で推定する。`render vowels` では姿勢を十分に保った区間を測る | [母音レンダー](upstream/crates/chimera-cli/src/render.rs)・[LPC](upstream/crates/chimera/src/analysis/lpc.rs)・[YIN 実装](upstream/crates/chimera/src/analysis/pitch.rs)・[YIN 原論文](https://doi.org/10.1121/1.1458024) |

固定姿勢の伝達関数はゼロ平均流周りの小信号モデルで、時間変動する声門、二次の流れ損失、乱流を含む WAV のスペクトルとは観測条件が異なります。まず一様管の共鳴、静止形状における伝達関数と FDTD の応答、駆動源を含む出力音声の順に照合すると、差が入り込む段を絞れます。[一様管とインパルス応答のテスト](upstream/crates/chimera/tests/airway.rs)・[線形化の実装](upstream/crates/chimera/src/airway/network.rs)

## 5. ブラウザとネイティブの境界

- **ブラウザ**。`main.tsx` が WASM を先に読み込み、`AudioEngine` が同じコンパイル済みモジュールを AudioWorklet へ渡します。メインスレッドの計画・形状 API は JSON を使い、音声スレッドの呼び出しは C ABI で、ジェスチャーは固定長バイナリです。固定版では `LAYOUT_VERSION = 1`、1 レコードは **272 バイト**です。古い設計書の 256 バイト表記からコードが変わっているため、構造を参照する際は次の対になった定義を使います。[起動](upstream/src/main.tsx)・[Worklet](upstream/src/worklet/processor.ts)・[Rust 側 ABI](upstream/crates/chimera-wasm/src/lib.rs)・[TypeScript 側の変換](upstream/src/wasm/wire.ts)
- **画面と音声**。気道圧力の RMS、面積、流量、声門周期波形は Worklet のテレメトリで取得します。固定姿勢の伝達関数はメインスレッドの別モデルから取得します。ブラウザ出力にはマスターゲインがあり、近接マイクの設定を有効にすると低域シェルフ、プレゼンスのピーキング EQ、コンプレッサー、メイクアップゲインを通ります。[可視化用モデル](upstream/src/ui/analysis.ts)・[Web Audio の出力グラフ](upstream/src/audio/AudioEngine.ts)
- **CLI**。`render speech` などは Rust のプランナーと `HumanVoice` を直接呼び、WAV へ書き出します。ブラウザと対応を取る場合は、音響コアの出力と Web Audio 側の出力処理を別の観測点として扱えます。[レンダーの実装](upstream/crates/chimera-cli/src/render.rs)・[WAV 書き出し](upstream/crates/chimera-cli/src/wav.rs)
- **派生モード**。ビートボックスは打音をジェスチャーへ展開し、`BeatPlayer` が拍に配置します。動物音声では `CreatureVoice` が別の気道接続と駆動源を使います。たとえば鳴禽は左右の気管支に独立した鳴管の振動源を持ちます。[打音定義](upstream/crates/chimera/src/phonetics/beatbox.rs)・[拍の進行](upstream/crates/chimera/src/control/beat_player.rs)・[動物音声](upstream/crates/chimera/src/creatures/voice.rs)・[鳴禽の接続](upstream/crates/chimera/src/creatures/songbird.rs)

## Voice Simulator で比較する観測点

| 調べたいこと | CHIMERA で確認する箇所 | Voice Simulator で対応する箇所 |
| --- | --- | --- |
| 励振から母音の共鳴が立つまで | 声門面積と流量を別々に取得し、同じ姿勢の線形応答と LPC を照合する | [LF 励振](../../../web/prototypes/waveguide-vocal-tract/src/audio/lf-source.ts)・[管のモデル](../../../web/prototypes/waveguide-vocal-tract/src/audio/tube-model.ts) |
| 閉鎖、破裂、摩擦のタイミング | `ɑpɑ` と `ɑbɑ` で閉鎖前後の周期成分、`ɑsɑ` と `ɑzɑ` でノイズ帯域と周期成分を比較する。音素時刻は計画値として使う | [子音イベントの調査](../../note/sibilant-syllable-event-notes.md) |
| 数値安定性と音響境界 | 分岐、狭窄、放射で何を安定化しているかを `airway_adversarial.rs` から本体へ逆にたどる | [二次元 FDTD のステップ更新](../../../web/prototypes/acoustic-fdtd-2d/src/sim/fdtd.ts) |

## 設計の経緯をたどる

`docs/architecture.md` の出典欄で、壁のインピーダンス、母音の音響目標、調音ジェスチャーの研究上の背景を確認できます。チューニングの判断は `docs/hill-climb/log.md` にあり、肺ポートや歯の摩擦源のコードと対応します。初期の TypeScript エンジンを確認するには、ローカルの `upstream/` で削除コミットの直前を開きます。[上流の出典一覧](upstream/docs/architecture.md#references-and-credits)・[調整履歴](upstream/docs/hill-climb/log.md)・[Rust への移植と実時間仕様](upstream/docs/rust-engine.md)

```bash
git ls-tree -r --name-only cd247a6^ -- src/engine
git show cd247a6^:src/engine/airway/network.ts
git log -p -- crates/chimera/src/voice/human_airway.rs
```
