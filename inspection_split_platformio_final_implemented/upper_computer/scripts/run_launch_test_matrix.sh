#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCH_DIR="$ROOT_DIR/src/inspection_tests/launch"

if [[ ! -d "$LAUNCH_DIR" ]]; then
  echo "Launch test directory not found: $LAUNCH_DIR" >&2
  exit 2
fi

mapfile -t launch_tests < <(find "$LAUNCH_DIR" -maxdepth 1 -type f -name '*.launch.py' | sort)
if [[ ${#launch_tests[@]} -eq 0 ]]; then
  echo "No launch tests found under $LAUNCH_DIR" >&2
  exit 3
fi

python -m pytest "${launch_tests[@]}"
