#!/bin/bash
# macOSでVoice Simulatorの通常開発に必要な環境を用意する。
set -euo pipefail

root="$(cd -- "$(dirname -- "$0")/.." && pwd -P)"
rust_version=1.94.1
wasm_target=wasm32-unknown-unknown
bun_version=1.4.4
upstream_revision=c6147d0198890475dbe8a65a0bb8f56240c539b7
upstream_dir="$root/docs/reference/chimera-vocal-synth/upstream"
research_dir="$root/research"
chimera_dir="$research_dir/experiments/chimera-rebuild"
web_dir="$root/web/prototypes"
venv_dir="$research_dir/.venv"
venv_python="$venv_dir/bin/python"
npm_projects=(vowel-formant-prototype tube-vocal-tract waveguide-vocal-tract acoustic-fdtd-2d)
mode=setup
with_upstream=false
with_browsers=false

usage() {
    cat <<'EOF'
使用法 bash scripts/setup-macos.sh [--check | --verify] [--upstream] [--browsers]

通常           Homebrewのランタイム、Rust、Python仮想環境、Webの依存を用意する
--check        システムツールとRust/WASMの準備状況を確認する
--verify       導入済みの環境でRustテスト、WAV合成、全Web試作の本番ビルドを確認する
--upstream     固定上流を取得する。確認モードでは版と作業ツリーを検査する
--browsers     PlaywrightのChromium Headless ShellとFirefoxを追加する。
               --verifyでは起動を確認する
EOF
}

die() {
    printf '%s\n' "$*" >&2
    exit 1
}

for arg in "$@"; do
    case "$arg" in
        --check|--verify)
            [[ "$mode" == setup ]] || die '--check と --verify は同時に指定できません。'
            mode="${arg#--}"
            ;;
        --upstream) with_upstream=true ;;
        --browsers) with_browsers=true ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "不明な引数です $arg" ;;
    esac
done

[[ "$(uname -s)" == Darwin ]] || die 'このセットアップはmacOS用です。'
/usr/bin/xcode-select -p >/dev/null 2>&1 && /usr/bin/xcrun --find clang >/dev/null 2>&1 ||
    die '先に xcode-select --install を実行し、Command Line Toolsの導入を完了してください。'

if ! command -v brew >/dev/null; then
    if [[ -x /opt/homebrew/bin/brew ]]; then
        export PATH="/opt/homebrew/bin:$PATH"
    elif [[ -x /usr/local/bin/brew ]]; then
        export PATH="/usr/local/bin:$PATH"
    fi
fi
command -v brew >/dev/null || die 'Homebrewを導入してください。手順は docs/setup/macos.md にあります。'
export PATH="${CARGO_HOME:-$HOME/.cargo}/bin:$PATH"
command -v rustup >/dev/null || die 'rustupを導入してください。手順は docs/setup/macos.md にあります。'

node_bin="$(brew --prefix node@24)/bin"
python="$(brew --prefix python@3.14)/bin/python3.14"
if [[ "$mode" == setup ]]; then
    [[ -x "$node_bin/node" && -x "$node_bin/npm" ]] || brew install node@24
    [[ -x "$python" ]] || brew install python@3.14
fi
[[ -x "$node_bin/node" && -x "$node_bin/npm" ]] || die 'Node.js 24がありません。brew install node@24 を実行してください。'
[[ -x "$python" ]] || die 'Python 3.14がありません。brew install python@3.14 を実行してください。'
export PATH="$node_bin:$PATH"

if ! rustup run "$rust_version" rustc --version >/dev/null 2>&1; then
    [[ "$mode" == setup ]] || die "Rust $rust_version がありません。スクリプトを通常モードで実行してください。"
    rustup toolchain install "$rust_version" --profile minimal --no-self-update
fi
if ! rustup target list --toolchain "$rust_version" --installed | grep -Fx "$wasm_target" >/dev/null; then
    [[ "$mode" == setup ]] || die "WASMターゲットがありません。スクリプトを通常モードで実行してください。"
    rustup target add --toolchain "$rust_version" "$wasm_target"
fi
export RUSTUP_TOOLCHAIN="$rust_version"

printf 'Node.js %s / npm %s\n' "$(node --version)" "$(npm --version)"
"$python" --version
rustup run "$rust_version" rustc --version

if "$with_upstream"; then
    if [[ ! -e "$upstream_dir" && ! -L "$upstream_dir" && "$mode" == setup ]]; then
        git clone --no-checkout https://github.com/jamesondh/chimera-vocal-synth.git "$upstream_dir"
        git -C "$upstream_dir" switch --detach "$upstream_revision"
    fi
    [[ -d "$upstream_dir" ]] || die "固定上流がありません $upstream_dir"
    upstream_root="$(git -C "$upstream_dir" rev-parse --show-toplevel 2>/dev/null)" ||
        die "固定上流のGit作業ツリーを確認できません $upstream_dir"
    [[ "$upstream_root" == "$(cd -- "$upstream_dir" && pwd -P)" ]] ||
        die "固定上流は独立したGitチェックアウトとして用意してください $upstream_dir"
    [[ "$(git -C "$upstream_dir" rev-parse HEAD)" == "$upstream_revision" ]] ||
        die "固定上流の版が異なります。docs/setup/macos.md の復旧手順を確認してください。"
    [[ -z "$(git -C "$upstream_dir" status --porcelain)" ]] ||
        die '固定上流にローカル変更があります。変更を保管したうえで比較用チェックアウトを用意してください。'
    printf '固定上流 %s\n' "$upstream_revision"
fi

if [[ "$mode" == check ]]; then
    printf '%s\n' 'システムツールの確認が完了しました。WebやPythonの依存は通常モードで導入できます。'
    exit 0
fi

bun() {
    npx --yes --package="bun@$bun_version" -- bun "$@"
}

if [[ "$mode" == setup && ! -e "$venv_dir" && ! -L "$venv_dir" ]]; then
    "$python" -m venv "$venv_dir"
fi
if [[ ! -x "$venv_python" ]] || ! "$venv_python" -c '
import sys
from pathlib import Path
assert sys.version_info[:2] == (3, 14)
assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve()
' "$venv_dir"; then
    die 'research/.venv を利用できません。既存フォルダをリポジトリ外へ退避し、通常モードで作成してください。'
fi

if [[ "$mode" == setup ]]; then
    "$venv_python" -m pip install -r "$research_dir/requirements.txt"
    for project in "${npm_projects[@]}"; do
        (cd -- "$web_dir/$project" && npm ci --include=dev)
    done
    (cd -- "$web_dir/chimera-research" && NODE_ENV=development bun install --frozen-lockfile)
    if "$with_browsers"; then
        (
            cd -- "$web_dir/chimera-research"
            node node_modules/playwright-core/cli.js install --only-shell chromium
            node node_modules/playwright-core/cli.js install firefox
        )
    fi
    printf '%s\n' 'セットアップが完了しました。bash scripts/setup-macos.sh --verify で動作を確認できます。'
    exit 0
fi

"$venv_python" -m pip check
"$venv_python" -c 'import matplotlib, numpy, scipy; print(f"matplotlib {matplotlib.__version__} / numpy {numpy.__version__} / scipy {scipy.__version__}")'
verification_dir="$(mktemp -d "${TMPDIR:-/tmp}/voice-simulator-setup.XXXXXX")"
trap 'rm -rf -- "$verification_dir"' EXIT
(
    cd -- "$chimera_dir"
    cargo test --workspace --locked
    cargo run --locked --release -p vocal-cli -- render-pcm \
        cases/vowel-voice-i.json "$verification_dir/voice.wav" --no-trace
)
"$venv_python" -c '
import sys
import numpy as np
from scipy.io import wavfile
rate, pcm = wavfile.read(sys.argv[1])
assert rate == 48000 and pcm.ndim == 1 and pcm.size and np.isfinite(pcm).all() and np.any(pcm)
print(f"WAV {rate} Hz / {pcm.size} フレーム")
' "$verification_dir/voice.wav"
for project in "${npm_projects[@]}"; do
    (cd -- "$web_dir/$project" && npm run build)
done
(cd -- "$web_dir/chimera-research" && bun run build)

if "$with_upstream"; then
    (cd -- "$upstream_dir" && cargo test --locked -p chimera --test airway)
fi
if "$with_browsers"; then
    (
        cd -- "$web_dir/chimera-research"
        node --input-type=module -e '
import { chromium, firefox } from "playwright-core";
for (const [name, engine] of [["Chromium", chromium], ["Firefox", firefox]]) {
  const browser = await engine.launch({ headless: true });
  console.log(`${name} ${browser.version()}`);
  await browser.close();
}'
    )
fi
printf '%s\n' '動作確認が完了しました。'
