#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPPER_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${UPPER_DIR}/frontend"
cd "${FRONTEND_DIR}"
npm ci
npm test
npm run typecheck
npm run lint
npm run build:real
python3 "${SCRIPT_DIR}/report_frontend_bundle_sizes.py" "${FRONTEND_DIR}/dist" "${UPPER_DIR}/.artifacts/verification/frontend_release_bundle_report.json"
test -f "${FRONTEND_DIR}/dist/index.html"
echo "frontend release validation passed"
