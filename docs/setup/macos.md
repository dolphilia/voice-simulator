# クリーンインストール後の macOS 開発環境

Web プロトタイプ、Python の解析環境、CHIMERA の Rust CLI と WASM を一から構築します。通常の開発、固定母音の合成、全 Web プロトタイプのビルドは Git の内容だけで始められます。過去の計測や聴取実験を再開するときは、後半の手順で研究データと外部ディスクを確認します。

## 1. 再インストール前に控えるもの

- GitHub へのログイン手段と、再開するブランチ・コミットを控えます。未反映のコミット、作業中の変更、未追跡ファイルをローカルのバックアップに入れます。`git status --short --branch` と `git rev-parse HEAD` で確認できます。
- `research/data/` 以下の音声、実験ごとの未追跡データ、SQLite の索引、利用許諾の記録、ローカル設定を保全します。CHIMERA では `research/experiments/chimera-rebuild/runs/*/artifacts/` と `runs/.source-objects/` を、リンクを維持できる形式で同じコピー工程に含めます。[研究データの保存方針](../../research/README.md#大容量データの保存先)
- CHIMERA の固定上流にローカル変更がある場合や、特定の外部ツールでしか再現できない計測に取り組んでいる場合は、その作業ツリー、バイナリ、環境の版も保全します。研究ごとの依存は各実行の `manifest.json` やノートから確認できます。
- `node_modules/`、`dist/`、通常の Rust `target/`、`research/.venv/` はソースから再構築できます。解析ライブラリを旧環境と同じ版にそろえる必要がある場合は、再インストール前に `research/.venv/bin/python -m pip freeze` の出力も保存します。

## 2. macOS の初期ツールとリポジトリ

1. ターミナルで `xcode-select --install` を実行し、ダイアログから Command Line Tools を導入します。完了後に `xcode-select -p` と `git --version` の出力を確認します。[Apple の導入手順](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools)
2. Homebrew を公式手順で導入し、インストーラーの案内に従って `brew shellenv` をログインシェルの設定に追加します。Apple Silicon の標準配置で、現在のシェルに読み込むコマンドは `eval "$(/opt/homebrew/bin/brew shellenv)"` です。Intel の標準配置は `/usr/local/bin/brew` です。[Homebrew の導入手順](https://docs.brew.sh/Installation)
3. 公式手順で rustup を導入し、ターミナルを開き直して `rustup --version` を確認します。通常のインストーラーで選択肢が出る場合は `Customize installation` から既定ツールチェーンに `none` を指定できます。プロジェクトが使う Rust と WASM ターゲットは次節のスクリプトが導入します。[rustup の導入手順](https://rustup.rs/)・[WASM ターゲットの追加方法](https://rust-lang.github.io/rustup/cross-compilation.html)
4. 必要に応じて GitHub に再認証します。HTTPS で GitHub CLI を使う場合のコマンドは `brew install gh`、`gh auth login --hostname github.com --git-protocol https --web`、`gh auth setup-git` です。[GitHub CLI の認証手順](https://cli.github.com/manual/gh_auth_login)・[Git の認証設定](https://cli.github.com/manual/gh_auth_setup-git)

以前に近いパスで再開する場合は、次の場所に取得します。別の場所でも通常開発は可能です。バックアップした変更がある場合は、対応するブランチとコミットを確認してから戻します。

```bash
mkdir -p "$HOME/github"
cd "$HOME/github"
git clone https://github.com/dolphilia/voice-simulator.git
cd voice-simulator
```

## 3. 依存関係の導入と動作確認

リポジトリのルートで実行します。初回はパッケージの取得にネットワーク接続が必要です。

```bash
bash scripts/setup-macos.sh
bash scripts/setup-macos.sh --verify
```

| 依存関係 | セットアップで使う版・配置 |
| --- | --- |
| Node.js / npm | Homebrew の `node@24`。npm の 4 プロトタイプは各 `package-lock.json` から導入 |
| Python | Homebrew の `python@3.14` から `research/.venv` を作成し、`research/requirements.txt` を導入 |
| Rust / WASM | `1.94.1` と `wasm32-unknown-unknown`。ビルドは `Cargo.lock` を使用 |
| Bun | CHIMERA の Web で `npx` 経由の `bun@1.4.4` と `bun.lock` を使用 |

Homebrew の更新に応じて Node.js と Python のパッチ版は進みます。Python の依存は `requirements.txt` が指定する範囲で解決されます。旧計測の数値を厳密に再現するときは当時の実行記録と依存の版を参照してください。[Node.js 24](https://formulae.brew.sh/formula/node@24)・[Python 3.14](https://formulae.brew.sh/formula/python@3.14)・[Bun のロックファイルを用いた導入](https://bun.com/docs/pm/cli/install)

`--verify` では Python の依存と import、Rust ワークスペースのテスト、固定母音 /i/ の 48 kHz WAV、5 つの Web プロトタイプの本番ビルドを確認します。導入前後にシステムツールの状態だけを調べる場合は `bash scripts/setup-macos.sh --check` を使います。既存の `research/.venv` が旧環境のパスを参照している場合は、ディレクトリを退避してセットアップを再実行します。[Python 仮想環境の仕様](https://docs.python.org/3/library/venv.html)

上流との比較や自動ブラウザ試験も使う場合は、対応するフラグを付けます。両方必要な場合の例です。

```bash
bash scripts/setup-macos.sh --upstream --browsers
bash scripts/setup-macos.sh --verify --upstream --browsers
```

`--upstream` は比較用の独立したチェックアウトを `docs/reference/chimera-vocal-synth/upstream/` に用意し、`c6147d0198890475dbe8a65a0bb8f56240c539b7` に固定します。既存の上流が別の版、変更済み、または途中までしか取得できていない場合は、作業ツリーを保全して別の場所へ退避し、再実行します。`--verify --upstream` は上流の気道テストも実行します。[上流ソース調査ガイド](../reference/chimera-vocal-synth/README.md)

`--browsers` は、ロックファイルと対応する Playwright の Chromium Headless Shell と Firefox を入れます。`--verify --browsers` では両方を起動します。特定の計測で指定するブラウザの版や実行ファイルは各ノートを参照してください。[Playwright のブラウザ管理](https://playwright.dev/docs/browsers)

## 4. 日常の開発

新しいターミナルで Homebrew の Node.js を使うため、`export PATH="$(brew --prefix node@24)/bin:$PATH"` を実行します。頻繁に使う場合は、Homebrew の設定より後に同じ行をログインシェルの設定へ追加できます。

**フォルマント試作**はルートから起動し、ターミナルに表示されたローカル URL を開きます。`tube-vocal-tract`、`waveguide-vocal-tract`、`acoustic-fdtd-2d` も同じ方法で起動できます。

```bash
cd web/prototypes/vowel-formant-prototype
npm run dev -- --host 127.0.0.1
```

**CHIMERA** は別のターミナルで、リポジトリのルートから次を実行します。表示されたローカル URL で「固定母音 /i/ をレンダー」を試せます。

```bash
cd web/prototypes/chimera-research
RUSTUP_TOOLCHAIN=1.94.1 npx --yes --package=bun@1.4.4 -- bun run dev --host 127.0.0.1
```

**Python の解析**はルートから `research/.venv/bin/python` で実行できます。Notebook が必要な場合は `research/.venv/bin/python -m pip install notebook` の後、`research/.venv/bin/python -m notebook research` で開きます。CLI の入出力と計測のコマンドは [CHIMERA 研究ワークスペース](../../research/experiments/chimera-rebuild/README.md)を参照してください。

## 5. バックアップした実験を再開する

以前から使っていた外部ディスクを接続し、マウント先と UUID を確認します。`diskutil info /Volumes/RTL9210B-CG` のように確認できます。ボリュームを別のものに交換した場合は、絶対パスを持つリンクや既存の保存先チェックを確認し、新しい保存先への移行を済ませてから新規計測を開始します。

| ボリューム | UUID | 保管するもの |
| --- | --- | --- |
| `/Volumes/RTL9210B-CG` | `3D26C0E2-12EF-4613-A693-E21C0D51D2E7` | `voice-simulator/scratch/chimera-runs/` の作業成果、`scratch/chimera-reference/` の参照データ、`scratch/chimera-mfa/` の整列環境とモデル。固有の計測用 Firefox が必要なら `voice-simulator/build/chimera-cubeb-output/` |
| `/Volumes/CT2000X8` | `9B51F3F1-8509-4272-B72B-ABA311912659` | `voice-simulator/archive/` の波形・動画・計測 CSV。APFS の透過圧縮を利用しているため、別媒体へ戻す場合はコピー先の空き容量も確認 |
| `/Volumes/CCCOMA_X64FRE_JA-JP_DV9` | `B7863180-5738-36A9-BAEF-7CB3008381B3` | 旧実験で使う `voice-simulator-data/`。必要な実験を再開するときに接続 |

CHIMERA のローカル成果を退避済みのチェックアウトから新しいクローンに戻す場合は、以下で転送予定を確認します。Homebrew 版 rsync を `brew install rsync` で用意し、`backup_repo` を実際のバックアップの場所に変更してリポジトリのルートで実行します。

```bash
backup_repo=/path/to/backed-up/voice-simulator
runs=research/experiments/chimera-rebuild/runs
rsync -aH --ignore-existing --dry-run --itemize-changes \
  --include='/*/' --include='/.source-objects/***' --include='/*/artifacts/***' --exclude='*' \
  "$backup_repo/$runs/" "$runs/"
```

内容を確認したら、同じコマンドから `--dry-run` を外して実行します。`-aH` でシンボリックリンクとハードリンクを維持し、`--ignore-existing` で復元先の既存ファイルを保護します。先に個別コピーしていた場合、ハードリンクの共有が崩れていないか下の照合で確認してください。マニフェストや集計結果は再開する Git の版とそろえます。この例の対象は CHIMERA のローカル成果です。ほかの研究データや索引はバックアップから元の研究パスに戻します。

作業用・保管用の 2 ボリュームをマウントして、リポジトリのルートで次を実行します。

```bash
research/.venv/bin/python -B research/experiments/chimera-rebuild/tools/check_restored_storage.py
```

2 ボリュームのマウント先・UUID・書き込み可否を確認し、内蔵・作業用・保管用の代表 3 実行について、保存ファイルのサイズと SHA-256、最近の実行で共有しているソースのハードリンクを照合します。照合時に研究データへの書き込みは発生しません。`--run-id <実行ID>` を繰り返して別の実行を指定できます。新規の外部出力を始めるときは、空き容量を確認し、`CHIMERA_RUN_STORAGE=rtl9210b` と容量の見積もりを設定します。[出力先と容量の指定](../../research/experiments/chimera-rebuild/README.md#大容量計測とcsvの保存)・[CHIMERA の移行と再読込の記録](../../research/storage-migrations/2026-11-27-chimera-runs-v3/verification.json)・[旧実験の保存方針](../plans/repository-data-storage-amendment-2026-10-08.md)

### 個別の計測で使うツール

- TSP の強制アラインメントは別の micromamba 環境で Python 3.11 と Montreal Forced Aligner 3.4.3 を使用します。環境を再構築するコマンドと辞書・モデルの確認方法は実験ノートにあります。[TSP 音素境界の実行環境](../../research/experiments/chimera-rebuild/notes/tsp-phone-boundaries-calibration.md#実行環境と保存)
- Safari、CoreAudio、MIDI の実機計測を再開するときは実験ノートに従って対象機器と macOS の権限を設定します。Instruments の `xctrace` を使う計測はフル版 Xcode が必要です。通常の Cargo のデバッグ出力は新しいクローンで再生成できます。[Apple のコマンドラインツール一覧](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools)・[Firefox と CoreAudio の計測環境](../../research/experiments/chimera-rebuild/notes/worklet-live-song-cubeb-output.md)
