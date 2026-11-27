# CHIMERA のソース調査ガイド

CHIMERA は、肺圧、声門の開閉、舌や唇の動きから、発話・歌唱・ビートボックスを生成する物理モデリング音声合成器です。同じ Rust の音響コアを、ネイティブ CLI とブラウザの WebAssembly から呼び出せます。はじめに[原理とコードの読み順](architecture.md)を読み、母音レンダーのフォルマントや子音のスペクトログラムを確認すると、各モデルの出力を対応付けて追えます。

原典を読みながら研究用に組み直す工程と検証条件は、[CHIMERA の研究用再実装計画](../../plans/chimera-research-rebuild-plan.md)を参照してください。

## 取得元と対象版

- 取得日（日本時間） 2026-11-19
- 対象コミット `c6147d0198890475dbe8a65a0bb8f56240c539b7`（取得時の `main`）。[コミット](https://github.com/jamesondh/chimera-vocal-synth/commit/c6147d0198890475dbe8a65a0bb8f56240c539b7)・[同版のツリー](https://github.com/jamesondh/chimera-vocal-synth/tree/c6147d0198890475dbe8a65a0bb8f56240c539b7)
- ローカルの `upstream/` に Git 履歴付きで取得済み。ソース、設計文書、テスト、同梱辞書を含む追跡対象は 310 ファイル。`upstream/` は独立したチェックアウトとして親リポジトリの Git 管理から除外しています。
- 本体は MIT ライセンス。辞書とフォントは同梱の個別ライセンスを参照してください。[本体](upstream/LICENSE)・[辞書](upstream/public/data/)・[フォント](upstream/public/fonts/)

別の環境で同じ版を取得するには、Voice Simulator のルートで次を実行します。

```bash
git clone https://github.com/jamesondh/chimera-vocal-synth.git docs/reference/chimera-vocal-synth/upstream &&
  git -C docs/reference/chimera-vocal-synth/upstream switch --detach c6147d0198890475dbe8a65a0bb8f56240c539b7
```

以下のコマンドは `docs/reference/chimera-vocal-synth/upstream` を作業ディレクトリにします。

## 音を生成して観測する

ネイティブ CLI の実行には Rust/Cargo が必要です。母音列は調整済みの 10 母音を順に発声し、WAV と、波形から推定した F0・フォルマントを出力します。IPA 比較では、同じ母音で子音を挟んだ `ɑpɑ / ɑbɑ / ɑsɑ / ɑzɑ / ɑmɑ` を一つの WAV にまとめ、各音素の**計画上の開始時刻**を秒で表示します。`render text` では英語文字列から IPA を作る経路も通ります。

```bash
mkdir -p out/reference
cargo build --locked --release -p chimera-cli
target/release/chimera render vowels male out/reference/vowels-male
target/release/chimera render speech out/reference/ipa-vcv 'ɑpɑ / ɑbɑ / ɑsɑ / ɑzɑ / ɑmɑ' male
target/release/chimera render text out/reference/english 'Hello world.' male
target/release/chimera diagnose out/reference-diagnose | tee out/reference/diagnose.txt
bun tools/spectrogram.ts out/reference/ipa-vcv.wav out/reference/ipa-vcv.png 'IPA VCV' 8000 12
```

`diagnose` は固定の英語文を合成し、母音中央付近のフォルマント、帯域幅、鼻腔開口の頻度、長時間スペクトル、長さ、ピッチを集計します。鼻腔開口の頻度は、鼻音が隣接しない母音を対象にした内部の開口面積の測定です。スペクトログラムは 8 kHz まで、窓長 12 ms で作成します。[CLI の入口](upstream/crates/chimera-cli/src/main.rs)・[診断の定義](upstream/crates/chimera-cli/src/diagnose.rs)・[描画ツール](upstream/tools/spectrogram.ts)

歌唱では同じレンダーから、WAV、100 Hz の調音軌跡 JSON、768 サンプル間隔（48 kHz では 16 ms）のテレメトリを取得できます。下の例は等しい入力を作りやすいよう、ビブラートを 0 にしています。調音 JSON の `keys` が `frames` 各行の列順です。テレメトリには咽頭・口腔の断面積、圧力 RMS、流量、声門面積と流量の波形などが含まれます。[レンダーと形式定義](upstream/crates/chimera-cli/src/render.rs)・[テレメトリの読み取り実装](upstream/src/show/tele.ts)

```bash
mkdir -p out/reference
cat > out/reference/melody.json <<'JSON'
{"bpm":120,"lyrics":"hello world","notes":[[60,1],[62,1],[64,2]],"vibrato":0}
JSON
target/release/chimera render notes out/reference/melody.json out/reference/melody female \
  --artic out/reference/articulators.json --tele out/reference/voice.tele
```

### 確認した出力

| 対象 | 結果 | ローカル出力 |
| --- | --- | --- |
| `render vowels male` | 6.00 秒、F0 推定値は 109.1〜110.5 Hz。`/i/` の LPC F1/F2 は 338/2266 Hz、`/ɑ/` は 698/1322 Hz | [WAV](upstream/out/reference/vowels-male.wav)・[測定値](upstream/out/reference/vowels-male.txt) |
| `render speech` | 5 種の VCV で 4.22 秒。`p` と `s` の計画上の開始はそれぞれ 0.209 秒と 1.800 秒 | [WAV](upstream/out/reference/ipa-vcv.wav)・[スペクトログラム](upstream/out/reference/ipa-vcv.png)・[音素時刻](upstream/out/reference/ipa-vcv.txt) |
| `render text` | `Hello world.` を IPA に変換し、1.21 秒の WAV を生成 | [WAV](upstream/out/reference/english.wav)・[IPA](upstream/out/reference/english.txt) |
| `render notes` | 3 音で 2.70 秒、調音 271 フレーム、テレメトリ 169 フレーム | [WAV](upstream/out/reference/melody.wav)・[調音 JSON](upstream/out/reference/articulators.json)・[テレメトリ](upstream/out/reference/voice.tele) |
| `diagnose` | 強勢母音の F1/F2 中央値誤差は 6%/7%（測定可能 19/19）。基準は上流の調整目標 | [診断ログ](upstream/out/reference/diagnose.txt)・[診断用 WAV](upstream/out/reference-diagnose/) |

CLI の WAV は 48 kHz・モノラルで、既定は 16 ビット PCM。波形比較には `--float` で 32 ビット浮動小数点を選べます。母音ログの `LPC` は出力音声の推定値、`model` は調整済みテーブルの値です。Voice Simulator 側で比較する場合も、どちらを測った値か記録してください。[WAV 書き出し](upstream/crates/chimera-cli/src/wav.rs)・[母音の測定コード](upstream/crates/chimera-cli/src/render.rs)

VCV のスペクトログラムでは、最初の `/p/` と `/b/` に母音間の閉鎖区間、中央の `/s/` と `/z/` に高域へ広がる摩擦成分が見えます。末尾の `/m/` では高域が弱まり、低域の周期成分が続きます。[スペクトログラム](upstream/out/reference/ipa-vcv.png)

## ブラウザで操作する

Apple Silicon macOS で Rust 1.94.1、Bun 1.4.4 を使いました。Bun が PATH にない環境では、以下の `bun` を `npx --yes --package=bun@1.4.4 -- bun` に置き換えられます。

```bash
rustup target add wasm32-unknown-unknown
bun install --frozen-lockfile
bun run build
bun run preview
```

[ローカルプレビュー](http://127.0.0.1:5318/)で `Play` → `Breathe` を選び、舌・顎・唇を動かすと、声道断面、スペクトル、声門波形を合わせて観察できます。`Speak` の IPA モードには CLI の VCV と同じ入力を渡せます。開発サーバーを使う場合は `bun run dev` でポート 5317 を開きます。[上流の起動手順](upstream/README.md)・[ポート設定](upstream/vite.config.ts)

## 検証に使うテスト

```bash
cargo test --locked -p chimera --test airway --test airway_adversarial
cargo test --locked -p chimera --test lung_port --test stop_spans --test voiced_fricatives
cargo test --locked -p chimera --test engine
cargo test --locked --workspace --no-fail-fast
bun test tests                 # bun run build 後に実行
```

- **気道の数値モデル**。一様管の共鳴と 1/4 波長近似、インパルスと線形周波数応答、狭窄・分岐・閉鎖解除の安定性を比較します。[基本テスト](upstream/crates/chimera/tests/airway.rs)・[境界条件のテスト](upstream/crates/chimera/tests/airway_adversarial.rs)
- **発声と調音の結合**。肺圧が声門に届くこと、閉鎖の開始と解除、有声摩擦音で周期源が弱まることを測ります。[肺ポート](upstream/crates/chimera/tests/lung_port.rs)・[閉鎖音](upstream/crates/chimera/tests/stop_spans.rs)・[有声摩擦音](upstream/crates/chimera/tests/voiced_fricatives.rs)
- **実行基盤**。低いデバイスサンプルレート、ホストのブロック長に対する波形の一致、実時間用 ABI の割り当て、ネイティブ/WASM の固定シナリオを確認します。[Rust エンジン](upstream/crates/chimera/tests/engine.rs)・[リアルタイム ABI](upstream/crates/chimera-wasm/tests/realtime.rs)・[WASM テスト](upstream/tests/wasm-engine.test.ts)
- **録音との比較**。上流は英語発話用の TSP、歌唱用の CSD を別に扱います。上記の CLI 診断や固定テストの数値と対応する評価範囲を確認できます。[英語発話の比較](upstream/docs/speech-comparison.md)・[歌唱の比較](upstream/docs/csd-comparison.md)

この環境では Rust が **274 件成功・既定で除外 2 件**、Bun が **73 件成功**です。除外は下唇の断面積連続性に関する既知のケースと、時間のかかる母音再校正テストです。ネイティブと WASM の固定シナリオの音声サンプルはビット単位で一致しました。Vite の本番ビルドとヘッドレス Chromium での上流 E2E も通過しました。E2E はデスクトップ・モバイルの表示幅で調音操作、発話、歌唱などを確認しています。[Rust ログ](upstream/out/reference/rust-tests.log)・[Bun ログ](upstream/out/reference/bun-tests.log)・[E2E ログ](upstream/out/reference/e2e.log)・[画面キャプチャ](upstream/out/reference/e2e/desktop-3-speak.png)

E2E を再実行する場合は、`bun run preview` を起動したまま別の端末で実行します。

```bash
./node_modules/.bin/playwright-core install chromium --only-shell
bun tools/e2e.ts http://127.0.0.1:5318/ out/reference/e2e
```
