#!/usr/bin/env python3
from __future__ import annotations

"""Render a derived audit summary from the runtime-validation gate artifacts."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from runtime_validation_common import (
    audit_summary_path,
    gate_status_path,
    load_matrix,
    resolve_evidence_root,
    scenario_evidence_path,
    sha256_file,
    utc_now,
    release_topic_sets,
    validate_evidence_payload,
)


def _load_json(path: Path) -> Any:
    """Load JSON content and return ``None`` when decoding fails."""
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def _scenario_status(
    *,
    root: Path,
    evidence_root: str,
    scenario: dict[str, Any],
    gate_status: dict[str, Any] | None,
    gate_status_present: bool,
) -> dict[str, Any]:
    """Render audit status for one runtime-validation scenario."""
    scenario_id = str(scenario.get('id', '')).strip()
    tier = str(scenario.get('tier', scenario.get('priority', ''))).strip()
    required = bool(scenario.get('required', False))
    trigger = str(scenario.get('trigger', '')).strip()
    hardware = scenario.get('hardware', {}) or {}
    requires_hardware_evidence = bool(hardware.get('stm32')) or bool(hardware.get('esp32s3'))
    evidence_path = scenario_evidence_path(root, evidence_root, scenario_id)
    relaxed_gate = bool(
        isinstance(gate_status, dict)
        and str(gate_status.get('status', '')).strip() == 'internal_unvalidated'
        and str(gate_status.get('verificationMode', '')).strip() == 'relaxed'
    )
    relaxed_hardware_skips = set(gate_status.get('relaxedHardwareSkips', [])) if isinstance(gate_status, dict) else set()
    sim_skips = set(gate_status.get('simSkips', [])) if isinstance(gate_status, dict) else set()
    entry: dict[str, Any] = {
        'id': scenario_id,
        'tier': tier,
        'required': required,
        'trigger': trigger,
        'requiresHardwareEvidence': requires_hardware_evidence,
        'evidencePath': str(evidence_path.relative_to(root)),
        'evidencePresent': evidence_path.exists(),
        'status': 'not_ready',
        'missingEvidence': [],
        'validationErrors': [],
        'validationNotes': [],
    }
    if scenario_id == 'sim_closed_loop':
        strict_ready = bool(
            gate_status
            and bool(gate_status.get('releaseGateEligible', False))
            and str(gate_status.get('status', '')).strip() == 'release_ready'
            and str(gate_status.get('verificationMode', '')).strip() == 'strict'
            and scenario_id in set(gate_status.get('requiredScenarioIds', []))
            and scenario_id not in sim_skips
            and int(gate_status.get('simExecutedCount', 0)) > 0
            and int(gate_status.get('simEvidenceVerifiedCount', 0)) > 0
        )
        if strict_ready:
            entry['status'] = 'ready'
        elif relaxed_gate and scenario_id in sim_skips:
            entry['status'] = 'omitted_internal_unvalidated'
            entry['validationNotes'].append('sim_execution_skipped_internal')
        else:
            entry['status'] = 'execution_required'
        if gate_status is None:
            entry['validationErrors'].append('gate_status_invalid' if gate_status_present else 'gate_status_missing')
        elif not strict_ready and not (relaxed_gate and scenario_id in sim_skips):
            if str(gate_status.get('verificationMode', '')).strip() != 'strict':
                entry['validationNotes'].append('formal_release_requires_strict_gate')
            elif scenario_id in sim_skips:
                entry['validationErrors'].append('sim_execution_skipped')
            elif int(gate_status.get('simExecutedCount', 0)) <= 0:
                entry['validationErrors'].append('sim_execution_not_recorded')
            elif int(gate_status.get('simEvidenceVerifiedCount', 0)) <= 0:
                entry['validationErrors'].append('sim_evidence_not_verified')
        return entry

    if not evidence_path.exists():
        if relaxed_gate and scenario_id in relaxed_hardware_skips:
            entry['status'] = 'omitted_internal_unvalidated'
            entry['validationNotes'].append('hardware_evidence_omitted_internal')
            return entry
        entry['status'] = 'missing_evidence'
        entry['missingEvidence'].append(str(evidence_path.relative_to(root)))
        return entry
    entry['evidenceSha256'] = sha256_file(evidence_path)
    evidence = _load_json(evidence_path)
    if evidence is None:
        entry['status'] = 'invalid_evidence'
        entry['validationErrors'].append('evidence_json_decode_failed')
        return entry
    if not isinstance(evidence, dict):
        entry['status'] = 'invalid_evidence'
        entry['validationErrors'].append('evidence_payload_not_mapping')
        return entry
    errors = validate_evidence_payload(scenario_id, scenario, evidence, evidence_path)
    if errors:
        entry['status'] = 'invalid_evidence'
        entry['validationErrors'].extend(errors)
        return entry
    entry['status'] = 'ready'
    return entry


def render_audit(workspace_root: Path) -> Path:
    """Render the derived audit summary.

    Args:
        workspace_root: Repository root containing ``release/`` artifacts.

    Returns:
        The written ``audit_summary.json`` path.

    Raises:
        ValueError: When the runtime-validation matrix omits the evidence root.

    Boundary behavior:
        The audit is intentionally derived-only. It never upgrades missing or
        relaxed evidence into ``ready`` and it requires a matching strict gate
        status artifact before formal release eligibility is granted.
    """
    release_root = workspace_root / 'release'
    matrix_path = release_root / 'runtime_validation_matrix.yaml'
    payload = load_matrix(matrix_path)
    evidence_root, resolved_evidence_root = resolve_evidence_root(workspace_root, payload)
    gate_path = gate_status_path(workspace_root, evidence_root)
    gate_status = _load_json(gate_path) if gate_path.exists() else None
    topic_sets = release_topic_sets(workspace_root)
    matrix_sha = sha256_file(matrix_path)
    gate_ready = bool(
        isinstance(gate_status, dict)
        and bool(gate_status.get('releaseGateEligible', False))
        and str(gate_status.get('status', '')).strip() == 'release_ready'
        and str(gate_status.get('verificationMode', '')).strip() == 'strict'
        and str(gate_status.get('matrixSha256', '')).strip() == matrix_sha
    )

    scenarios = payload.get('scenarios', []) if isinstance(payload, dict) else []
    summary: list[dict[str, Any]] = []
    for item in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(item, dict):
            continue
        summary.append(_scenario_status(root=workspace_root, evidence_root=evidence_root, scenario=item, gate_status=gate_status if gate_ready else gate_status, gate_status_present=gate_path.exists()))

    required_entries = [entry for entry in summary if entry.get('required')]
    ready_required = all(entry.get('status') == 'ready' for entry in required_entries)
    release_gate_eligible = bool(gate_ready and ready_required)
    gate_mode = str(gate_status.get('verificationMode', '')).strip() if isinstance(gate_status, dict) else 'absent'
    if release_gate_eligible:
        overall_status = 'ready'
    elif isinstance(gate_status, dict) and str(gate_status.get('status', '')).strip() == 'internal_unvalidated' and gate_mode == 'relaxed':
        overall_status = 'internal_unvalidated'
    else:
        overall_status = 'missing_required_evidence'
    gate_errors: list[str] = []
    gate_notes: list[str] = []
    if gate_status is None:
        gate_errors.append('gate_status_invalid' if gate_path.exists() else 'gate_status_missing')
    elif not isinstance(gate_status, dict):
        gate_errors.append('gate_status_invalid')
    else:
        status = str(gate_status.get('status', '')).strip()
        if status not in {'release_ready', 'internal_unvalidated'}:
            gate_errors.append('gate_status_invalid_status')
        if str(gate_status.get('verificationMode', '')).strip() != 'strict':
            gate_notes.append('formal_release_requires_strict_gate')
        if str(gate_status.get('matrixSha256', '')).strip() != matrix_sha:
            gate_errors.append('gate_status_matrix_sha_mismatch')

    out = {
        'schemaVersion': 1,
        'generatedAt': utc_now(),
        'overallStatus': overall_status,
        'releaseGateEligible': release_gate_eligible,
        'verificationMode': gate_mode,
        'matrixPath': str(matrix_path.relative_to(workspace_root)),
        'matrixSha256': matrix_sha,
        'requiredEvidenceRoot': evidence_root,
        'gateStatusPath': str(gate_path.relative_to(workspace_root)),
        'gateStatusPresent': gate_path.exists(),
        'gateStatusSha256': sha256_file(gate_path) if gate_path.exists() else '',
        'gateValidationErrors': gate_errors,
        'gateValidationNotes': gate_notes,
        'releaseEvidenceTopics': topic_sets,
        'scenarioCount': len(summary),
        'readyCount': sum(1 for entry in summary if entry['status'] == 'ready'),
        'requiredReadyCount': sum(1 for entry in required_entries if entry['status'] == 'ready'),
        'requiredScenarioCount': len(required_entries),
        'scenarios': summary,
    }
    resolved_evidence_root.mkdir(parents=True, exist_ok=True)
    target = audit_summary_path(workspace_root, evidence_root)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace-root', default='.')
    parser.add_argument('--check-ready', action='store_true', help='Fail if the rendered audit is not formal-release ready.')
    args = parser.parse_args()
    try:
        target = render_audit(Path(args.workspace_root).resolve())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(target)
    if args.check_ready:
        payload = _load_json(target)
        if not isinstance(payload, dict) or not bool(payload.get('releaseGateEligible', False)):
            print(f'runtime validation audit is not release-ready: {target}', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
