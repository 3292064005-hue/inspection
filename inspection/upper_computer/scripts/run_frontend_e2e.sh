#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "Frontend package.json not found under $FRONTEND_DIR" >&2
  exit 2
fi

if [[ ! -x "$FRONTEND_DIR/node_modules/.bin/playwright" ]]; then
  echo "Playwright dependency missing. Run 'npm ci --prefix frontend' first." >&2
  exit 3
fi

chromium_path="${PLAYWRIGHT_CHROMIUM_EXECUTABLE:-}"
if [[ -z "$chromium_path" ]]; then
  if command -v chromium >/dev/null 2>&1; then
    chromium_path="$(command -v chromium)"
  elif command -v chromium-browser >/dev/null 2>&1; then
    chromium_path="$(command -v chromium-browser)"
  else
    echo "Chromium executable not found. Set PLAYWRIGHT_CHROMIUM_EXECUTABLE or install chromium." >&2
    exit 4
  fi
fi

export PLAYWRIGHT_CHROMIUM_EXECUTABLE="$chromium_path"
npm --prefix "$FRONTEND_DIR" run e2e
