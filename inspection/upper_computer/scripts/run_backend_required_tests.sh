#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
python3 scripts/check_python_syntax.py
python3 scripts/check_gateway_contract_drift.py
bash scripts/run_backend_import_smoke_tests.sh
python3 -m pytest \
  src/inspection_tests/test_paths_resolution.py \
  src/inspection_tests/test_frame_binding.py \
  src/inspection_tests/test_vision_runtime_improvements.py \
  src/inspection_tests/test_bringup_runtime_contract.py \
  src/inspection_tests/test_control_plane_alignment.py \
  src/inspection_tests/test_action_contracts.py \
  src/inspection_tests/test_action_registry_completeness.py \
  src/inspection_tests/test_processor_transport_core.py \
  src/inspection_tests/test_compatibility_route_governance.py \
  src/inspection_tests/test_compatibility_routes_default_closed.py \
  src/inspection_tests/test_read_model_fail_closed_runtime.py \
  src/inspection_tests/test_gateway_result_store.py \
  src/inspection_tests/test_gateway_runtime_components.py \
  src/inspection_tests/test_node_health_registry.py \
  src/inspection_tests/test_lifecycle_governance_matrix.py \
  src/inspection_tests/test_managed_runtime.py \
  src/inspection_tests/test_telemetry_service.py \
  src/inspection_tests/test_trace_evidence_repository.py \
  src/inspection_tests/test_read_model_repository.py \
  src/inspection_tests/test_gateway_export_service.py \
  src/inspection_tests/test_gateway_recipe_store.py \
  src/inspection_tests/test_switch_recipe_validation_semantics.py \
  src/inspection_tests/test_gateway_public_contract_types.py \
  src/inspection_tests/test_action_job_service_transport.py \
  src/inspection_tests/test_qos_profiles.py \
  src/inspection_tests/test_validation_contract.py \
  src/inspection_tests/test_effective_runtime_bundle.py \
  src/inspection_tests/test_gateway_release_contract.py \
  src/inspection_tests/test_read_model_writer.py
