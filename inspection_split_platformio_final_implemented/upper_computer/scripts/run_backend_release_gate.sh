#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Release gate must reuse the same layered preflight as the required gate so
# full-suite green runs cannot bypass syntax/import/runtime regressions.
bash scripts/run_backend_required_tests.sh
bash scripts/run_backend_runtime_smoke_tests.sh
python3 -m pytest src/inspection_tests
