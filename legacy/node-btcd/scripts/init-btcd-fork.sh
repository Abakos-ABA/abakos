#!/usr/bin/env bash
# Clone btcd and apply Abakos PoUW patches (Linux/macOS/CI)
# Creates node/.btcd-fork/ (gitignored) at btcsuite/btcd v0.24.2
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FORK="$ROOT/.btcd-fork"
PATCH="$ROOT/fork/patches/abakos-pouw.patch"
TAG="v0.24.2"

if [[ -d "$FORK" ]]; then
  echo "Already exists: $FORK"
  echo "Delete it to re-clone, or run: git -C $FORK apply $PATCH"
  exit 0
fi

echo "Cloning btcd $TAG into $FORK ..."
git clone --depth 1 --branch "$TAG" https://github.com/btcsuite/btcd.git "$FORK"

cd "$FORK"
git checkout -b abakos-pouw
if [[ ! -f "$PATCH" ]]; then
  echo "Missing patch file: $PATCH" >&2
  exit 1
fi
git apply "$PATCH"
echo ""
echo "Done. node/go.mod should contain:"
echo "  replace github.com/btcsuite/btcd => ./.btcd-fork"
echo ""
echo "Verify: cd node && go test ./fork/..."
