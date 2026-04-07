#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
FAIL_UNDER="${BACKEND_COVERAGE_FAIL_UNDER:-0}"
ARTIFACT_DIR="$ROOT_DIR/.artifacts/verification"
mkdir -p "$ARTIFACT_DIR"
COVERAGE_ARGS=(--cov=inspection_supervisor --cov=inspection_orchestrator --cov=inspection_utils --cov=vision_processing --cov=inspection_hmi_gateway --cov-report=term-missing --cov-report=json:"$ARTIFACT_DIR/backend_coverage.json")
if [[ "$FAIL_UNDER" != "0" ]]; then COVERAGE_ARGS+=("--cov-fail-under=$FAIL_UNDER"); fi
python3 -m pytest "${COVERAGE_ARGS[@]}"   src/inspection_tests/test_paths_resolution.py   src/inspection_tests/test_frame_binding.py   src/inspection_tests/test_vision_runtime_improvements.py   src/inspection_tests/test_processor_runtime_support.py   src/inspection_tests/test_fsm_phase_runtime.py   src/inspection_tests/test_station_bridge_runtime_support.py   src/inspection_tests/test_bringup_runtime_contract.py   src/inspection_tests/test_control_plane_alignment.py   src/inspection_tests/test_gateway_result_store.py   src/inspection_tests/test_gateway_runtime_components.py   src/inspection_tests/test_node_health_registry.py   src/inspection_tests/test_lifecycle_governance_matrix.py   src/inspection_tests/test_lifecycle_manager.py   src/inspection_tests/test_lifecycle_executor.py   src/inspection_tests/test_mode_manager.py   src/inspection_tests/test_orchestrator_trees.py   src/inspection_tests/test_recovery_policy_v2.py   src/inspection_tests/test_bt_runtime.py   src/inspection_tests/test_validation_contract.py   src/inspection_tests/test_effective_runtime_bundle.py   src/inspection_tests/test_gateway_release_contract.py
