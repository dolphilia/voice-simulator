#!/bin/bash
# PlaywrightのJugglerとcubeb計測を固定Geckoの作業ツリーに適用する。
set -euo pipefail

if [[ $# != 2 ]]; then
  echo "使い方: bash $0 <Geckoのチェックアウト> <Playwrightのチェックアウト>" >&2
  exit 2
fi

tools=$(cd "$(dirname "$0")" && pwd -P)
checkout=$(cd "$1" && pwd -P)
playwright=$(cd "$2" && pwd -P)
browser_patches="$playwright/browser_patches/firefox"
vendor="$checkout/third_party/rust/cubeb-coreaudio"
patch="$tools/chimera-cubeb-output-snapshot.patch"
libcxx_test_patch="$tools/chimera-firefox-zucchini-libcxx.patch"
case_path="$tools/../cases/worklet-live-song-cubeb-output.json"

validate_head() {
  local expected actual
  expected=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$case_path" "$2")
  actual=$(git -C "$1" rev-parse HEAD)
  if [[ "$expected" != "$actual" ]]; then
    echo "ケースとチェックアウトのコミットが一致しません ($1)" >&2
    return 1
  fi
}

validate_head "$checkout" gecko_revision
validate_head "$playwright" playwright_revision
if [[ -e "$checkout/juggler" ]] || [[ -n $(git -C "$checkout" status --porcelain) ]]; then
  echo '固定版Geckoの未変更のチェックアウトを指定してください' >&2
  exit 1
fi

git -C "$checkout" apply --check "$browser_patches/patches/bootstrap.diff"
git -C "$checkout" apply --check --directory=third_party/rust/cubeb-coreaudio "$patch"
git -C "$checkout" apply --check "$libcxx_test_patch"
git -C "$checkout" apply "$browser_patches/patches/bootstrap.diff"
cp -R "$browser_patches/juggler" "$checkout/juggler"
git -C "$checkout" apply --directory=third_party/rust/cubeb-coreaudio "$patch"
git -C "$checkout" apply "$libcxx_test_patch"

python3 - "$vendor" <<'PY'
from hashlib import sha256
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
checksum = root / '.cargo-checksum.json'
record = json.loads(checksum.read_text())
for path in ('src/backend/mod.rs', 'src/backend/chimera_output_snapshot.rs'):
    record['files'][path] = sha256((root / path).read_bytes()).hexdigest()
for path, digest in record['files'].items():
    if sha256((root / path).read_bytes()).hexdigest() != digest:
        raise SystemExit(f'cubebのチェックサム不一致: {path}')
checksum.write_text(json.dumps(record, sort_keys=True, separators=(',', ':')) + '\n')
print(f'cubebのチェックサム: {len(record["files"])}件一致')
PY

git -C "$checkout" diff --check -- third_party/rust/cubeb-coreaudio third_party/zucchini
git -C "$checkout" apply --reverse --check "$browser_patches/patches/bootstrap.diff"
git -C "$checkout" apply --reverse --check --directory=third_party/rust/cubeb-coreaudio "$patch"
git -C "$checkout" apply --reverse --check "$libcxx_test_patch"
shasum -a 256 "$browser_patches/patches/bootstrap.diff" "$patch" "$libcxx_test_patch" "$vendor/.cargo-checksum.json"
