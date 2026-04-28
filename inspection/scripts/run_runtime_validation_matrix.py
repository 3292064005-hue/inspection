#!/usr/bin/env python3
from __future__ import annotations

"""Execute and/or verify the release runtime-validation matrix.

This gate is the authoritative validator for release-time runtime evidence. It
can execute the simulation scenario, verify hardware evidence payloads, and now
also emits a machine-readable gate-status artifact consumed by the audit and
packaging stages.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from runtime_validation_common import (
    gate_status_path,
    load_matrix,
    resolve_evidence_root,
    scenario_evidence_path,
    release_topic_sets,
    sha256_file,
    utc_now,
    validate_evidence_payload,
)


def _run_sim_scenario(root: Path, trigger: str) -> None:
    """Execute the simulation scenario trigger inside the workspace root."""
    subprocess.run(['bash', '-lc', trigger], cwd=str(root), check=True)


def _write_gate_status(
    *,
    root: Path,
    evidence_root: str,
    matrix_path: Path,
    verification_mode: str,
    strict_hardware_evidence: bool,
    skip_sim_execution: bool,
    allow_missing_hardware_evidence: bool,
    sim_executed: int,
    sim_evidence_verified: int,
    hardware_evidence_verified: int,
    relaxed_skips: list[str],
    sim_skips: list[str],
    required_scenarios: list[str],
) -> Path:
    """Persist a normalized gate-status artifact for downstream audits.

    Args:
        root: Workspace root.
        evidence_root: Relative evidence root from the matrix summary.
        matrix_path: Absolute matrix path.
        verification_mode: ``strict`` or ``relaxed``.
        strict_hardware_evidence: Whether strict hardware evidence was required.
        skip_sim_execution: Whether simulation execution was skipped.
        allow_missing_hardware_evidence: Whether relaxed hardware skips were allowed.
        sim_executed: Number of executed simulation scenarios.
        sim_evidence_verified: Number of verified simulation evidence files.
        hardware_evidence_verified: Number of verified hardware evidence files.
        relaxed_skips: Scenario ids skipped under relaxed mode.
        sim_skips: Simulation scenarios intentionally skipped.
        required_scenarios: Required scenario ids from the matrix.

    Returns:
        The persisted gate-status path.

    Raises:
        No exception is intentionally raised by this helper.

    Boundary behavior:
        The written payload is deterministic and captures the exact gate mode so
        formal packaging can reject relaxed or stale validation artifacts.
    """
    target = gate_status_path(root, evidence_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    topic_sets = release_topic_sets(root)
    required_total = len(required_scenarios)
    verified_total = int(sim_evidence_verified) + int(hardware_evidence_verified)
    release_ready = bool(verification_mode == 'strict' and not skip_sim_execution and not relaxed_skips and not sim_skips and verified_total >= required_total)
    status = 'release_ready' if release_ready else 'internal_unvalidated'
    payload = {
        'schemaVersion': 1,
        'generatedAt': utc_now(),
        'passed': bool(release_ready),
        'status': status,
        'releaseGateEligible': release_ready,
        'verificationMode': verification_mode,
        'strictHardwareEvidence': bool(strict_hardware_evidence),
        'skipSimExecution': bool(skip_sim_execution),
        'allowMissingHardwareEvidence': bool(allow_missing_hardware_evidence),
        'matrixPath': matrix_path.relative_to(root).as_posix(),
        'matrixSha256': sha256_file(matrix_path),
        'requiredScenarioIds': list(required_scenarios),
        'simExecutedCount': int(sim_executed),
        'simEvidenceVerifiedCount': int(sim_evidence_verified),
        'hardwareEvidenceVerifiedCount': int(hardware_evidence_verified),
        'requiredScenarioVerifiedCount': verified_total,
        'releaseEvidenceTopics': topic_sets,
        'relaxedHardwareSkips': list(relaxed_skips),
        'simSkips': list(sim_skips),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description='Execute or verify the runtime validation matrix.')
    parser.add_argument('--workspace-root', default='.')
    parser.add_argument('--matrix-path', default='release/runtime_validation_matrix.yaml')
    parser.add_argument('--skip-sim-execution', action='store_true')
    parser.add_argument('--strict-hardware-evidence', action='store_true')
    parser.add_argument('--allow-missing-hardware-evidence', action='store_true')
    args = parser.parse_args()

    root = Path(args.workspace_root).resolve()
    matrix_path = root / args.matrix_path
    payload = load_matrix(matrix_path)
    try:
        evidence_root, _resolved_evidence_root = resolve_evidence_root(root, payload)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    scenarios = payload.get('scenarios', []) or []
    sim_executed = 0
    sim_evidence_verified = 0
    hardware_evidence_verified = 0
    relaxed_skips: list[str] = []
    sim_skips: list[str] = []
    required_scenarios: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict) or not scenario.get('required', False):
            continue
        scenario_id = str(scenario.get('id', '')).strip()
        if not scenario_id:
            continue
        required_scenarios.append(scenario_id)
        trigger = str(scenario.get('trigger', '')).strip()
        hardware = scenario.get('hardware', {}) or {}
        needs_hw = bool(hardware.get('stm32')) or bool(hardware.get('esp32s3'))
        if scenario_id == 'sim_closed_loop':
            if args.skip_sim_execution:
                sim_skips.append(scenario_id)
                continue
            if not trigger:
                print(f'scenario {scenario_id} missing trigger', file=sys.stderr)
                return 1
            _run_sim_scenario(root, trigger)
            sim_executed += 1
            evidence_path = scenario_evidence_path(root, evidence_root, scenario_id)
            if not evidence_path.exists():
                print(f'missing runtime validation evidence for {scenario_id}: {evidence_path}', file=sys.stderr)
                return 1
            evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
            if not isinstance(evidence, dict):
                print(f'invalid runtime validation evidence payload for {scenario_id}: {evidence_path}', file=sys.stderr)
                return 1
            errors = validate_evidence_payload(scenario_id, scenario, evidence, evidence_path)
            if errors:
                print(errors[0], file=sys.stderr)
                return 1
            sim_evidence_verified += 1
            continue
        evidence_path = scenario_evidence_path(root, evidence_root, scenario_id)
        if args.strict_hardware_evidence or needs_hw:
            if not evidence_path.exists():
                if args.allow_missing_hardware_evidence and not args.strict_hardware_evidence:
                    relaxed_skips.append(scenario_id)
                    continue
                print(f'missing runtime validation evidence for {scenario_id}: {evidence_path}', file=sys.stderr)
                return 1
            evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
            if not isinstance(evidence, dict):
                print(f'invalid runtime validation evidence payload for {scenario_id}: {evidence_path}', file=sys.stderr)
                return 1
            errors = validate_evidence_payload(scenario_id, scenario, evidence, evidence_path)
            if errors:
                print(errors[0], file=sys.stderr)
                return 1
            hardware_evidence_verified += 1
    verification_mode = 'strict' if args.strict_hardware_evidence and not args.allow_missing_hardware_evidence else 'relaxed'
    gate_status = _write_gate_status(
        root=root,
        evidence_root=evidence_root,
        matrix_path=matrix_path,
        verification_mode=verification_mode,
        strict_hardware_evidence=args.strict_hardware_evidence,
        skip_sim_execution=args.skip_sim_execution,
        allow_missing_hardware_evidence=args.allow_missing_hardware_evidence,
        sim_executed=sim_executed,
        sim_evidence_verified=sim_evidence_verified,
        hardware_evidence_verified=hardware_evidence_verified,
        relaxed_skips=relaxed_skips,
        sim_skips=sim_skips,
        required_scenarios=required_scenarios,
    )
    gate_payload = json.loads(gate_status.read_text(encoding='utf-8'))
    print(
        '[OK] runtime validation matrix evaluated: '
        f'{matrix_path} '
        f"(status={gate_payload.get('status', 'unknown')}, verification_mode={gate_payload.get('verificationMode', 'unknown')}, "
        f'sim_executed={sim_executed}, sim_evidence_verified={sim_evidence_verified}, hardware_evidence_verified={hardware_evidence_verified}, '
        f'relaxed_hardware_skips={len(relaxed_skips)}, sim_skips={len(sim_skips)}, gate_status={gate_status.relative_to(root).as_posix()})'
    )
    if sim_skips:
        print('[INFO] skipped sim execution for: ' + ', '.join(sim_skips))
    if relaxed_skips:
        print('[INFO] relaxed hardware evidence not required for: ' + ', '.join(relaxed_skips))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
