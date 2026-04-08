#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
python3 -m pytest \
  src/inspection_tests/test_control_plane_runtime_smoke.py \
  src/inspection_tests/test_runtime_node_callback_contract.py \
  src/inspection_tests/test_gateway_recipe_store.py \
  src/inspection_tests/test_gateway_result_store.py \
  src/inspection_tests/test_read_model_repository.py
