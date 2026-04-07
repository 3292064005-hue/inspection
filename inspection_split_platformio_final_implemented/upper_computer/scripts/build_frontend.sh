#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-real}"
cd "$(dirname "$0")/../frontend"
npm ci --prefer-offline --no-audit --progress=false
npm run "build:${MODE}"
