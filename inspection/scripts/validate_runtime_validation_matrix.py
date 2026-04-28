#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import yaml

REQUIRED_SCENARIOS = {
    'sim_closed_loop': {'start_batch_closed_loop', 'maintenance_mode_gate', 'diagnostic_capture_frame'},
    'upper_computer_with_stm32': {'serial_handshake_capabilities', 'supported_action_code_reject'},
    'upper_computer_with_esp32s3': {'camera_health_endpoint_ready', 'snapshot_capture_success'},
    'full_hardware_closed_loop': {'capture_process_decision_cycle', 'sort_execution_roundtrip', 'read_model_projection_ready'},
}


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate the release runtime validation matrix definition.')
    parser.add_argument('--workspace-root', default='.')
    parser.add_argument('--matrix-path', default='release/runtime_validation_matrix.yaml')
    args = parser.parse_args()

    root = Path(args.workspace_root).resolve()
    matrix_path = root / args.matrix_path
    if not matrix_path.exists():
        return _fail(f'missing runtime validation matrix: {matrix_path}')
    payload = yaml.safe_load(matrix_path.read_text(encoding='utf-8')) or {}
    if not isinstance(payload, dict):
        return _fail('runtime validation matrix payload must be a mapping')
    scenarios = payload.get('scenarios', [])
    if not isinstance(scenarios, list):
        return _fail('runtime validation matrix scenarios must be a list')
    by_id = {str(item.get('id', '')).strip(): item for item in scenarios if isinstance(item, dict)}
    missing = [scenario_id for scenario_id in REQUIRED_SCENARIOS if scenario_id not in by_id]
    if missing:
        return _fail(f'missing required runtime scenarios: {", ".join(missing)}')
    for scenario_id, required_checks in REQUIRED_SCENARIOS.items():
        scenario = by_id[scenario_id]
        if not bool(scenario.get('required', False)):
            return _fail(f'scenario {scenario_id} must remain required=true')
        checks = {str(item).strip() for item in scenario.get('expectedChecks', []) if str(item).strip()}
        if not required_checks.issubset(checks):
            missing_checks = ', '.join(sorted(required_checks - checks))
            return _fail(f'scenario {scenario_id} is missing required expectedChecks: {missing_checks}')
        failures = {str(item).strip() for item in scenario.get('failureCriteria', []) if str(item).strip()}
        if not failures:
            return _fail(f'scenario {scenario_id} must declare at least one failureCriteria item')
        hardware = scenario.get('hardware', {})
        if not isinstance(hardware, dict) or not hardware:
            return _fail(f'scenario {scenario_id} must declare hardware coverage')
        if not str(scenario.get('trigger', '')).strip():
            return _fail(f'scenario {scenario_id} must declare a trigger command or procedure')
    summary = payload.get('summary', {}) or {}
    evidence_root = str(summary.get('requiredEvidenceRoot', '')).strip()
    if not evidence_root:
        return _fail('runtime validation matrix summary.requiredEvidenceRoot is required')
    topic_classification_path = str(summary.get('topicClassificationPath', '')).strip()
    if not topic_classification_path:
        return _fail('runtime validation matrix summary.topicClassificationPath is required')
    if not (root / topic_classification_path).exists():
        return _fail(f'runtime validation topic classification path is missing: {topic_classification_path}')
    print(f'[OK] runtime validation matrix: {matrix_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
