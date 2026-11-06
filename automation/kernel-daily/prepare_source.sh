#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$DIR/config.json"
SRC="$(jq -r '.kernel.src' "$CONFIG")"
REPO="$(jq -r '.kernel.repo' "$CONFIG")"
BRANCH="$(jq -r '.kernel.branch' "$CONFIG")"

if [ -d "$SRC/.git" ]; then
  echo "kernel source already present: $SRC"
  if [ "${KERNEL_DAILY_UPDATE_SOURCE:-0}" = "1" ]; then
    git -C "$SRC" fetch --depth 1 origin "$BRANCH"
    git -C "$SRC" reset --hard FETCH_HEAD
  fi
else
  mkdir -p "$(dirname "$SRC")"
  GIT_TERMINAL_PROMPT=0 git clone --depth 1 --filter=blob:none --sparse \
    --branch "$BRANCH" "$REPO" "$SRC"
fi

mapfile -t SPARSE < <(jq -r '.kernel.sparse_dirs[]' "$CONFIG")
git -C "$SRC" sparse-checkout set "${SPARSE[@]}"

echo "kernel: $(git -C "$SRC" rev-parse --short HEAD) $(git -C "$SRC" describe --tags --always 2>/dev/null || true)"
