#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml

from runtime_validation_common import audit_summary_path, gate_status_path, sha256_file


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _runtime_validation_summary(root: Path) -> dict[str, Any]:
    matrix_path = root / 'release' / 'runtime_validation_matrix.yaml'
    payload = yaml.safe_load(matrix_path.read_text(encoding='utf-8')) or {}
    summary = payload.get('summary', {}) or {}
    evidence_root = str(summary.get('requiredEvidenceRoot', '')).strip()
    gate_path = gate_status_path(root, evidence_root) if evidence_root else None
    audit_path = audit_summary_path(root, evidence_root) if evidence_root else None
    scenarios = []
    for scenario in payload.get('scenarios', []) or []:
        if not isinstance(scenario, dict):
            continue
        scenario_id = str(scenario.get('id', '')).strip()
        if not scenario_id:
            continue
        evidence_path = root / evidence_root / f'{scenario_id}.json' if evidence_root else None
        evidence_present = bool(evidence_path and evidence_path.exists())
        scenarios.append({
            'id': scenario_id,
            'tier': str(scenario.get('tier', '')).strip(),
            'required': bool(scenario.get('required', False)),
            'requiresHardwareEvidence': bool(((scenario.get('hardware') or {}).get('stm32')) or ((scenario.get('hardware') or {}).get('esp32s3'))),
            'evidencePath': str(evidence_path.relative_to(root)) if evidence_path else '',
            'evidencePresent': evidence_present,
        })
    gate_payload = _load_json(gate_path) if gate_path and gate_path.exists() else None
    audit_payload = _load_json(audit_path) if audit_path and audit_path.exists() else None
    return {
        'matrixPath': 'release/runtime_validation_matrix.yaml',
        'matrixSha256': sha256_file(matrix_path),
        'requiredEvidenceRoot': evidence_root,
        'gateStatusPath': str(gate_path.relative_to(root)) if gate_path else '',
        'gateStatusPresent': bool(gate_path and gate_path.exists()),
        'gateVerificationMode': str(gate_payload.get('verificationMode', 'absent')) if gate_payload else 'absent',
        'gateEvaluationStatus': str(gate_payload.get('status', 'absent')) if gate_payload else 'absent',
        'gateReleaseEligible': bool(gate_payload.get('releaseGateEligible', False)) if gate_payload else False,
        'auditSummaryPath': str(audit_path.relative_to(root)) if audit_path else '',
        'auditSummaryPresent': bool(audit_path and audit_path.exists()),
        'auditOverallStatus': str(audit_payload.get('overallStatus', 'absent')) if audit_payload else 'absent',
        'formalReleaseEligible': bool(audit_payload.get('releaseGateEligible', False)) if audit_payload else False,
        'runtimeFormalReleaseEligible': bool(audit_payload.get('releaseGateEligible', False)) if audit_payload else False,
        'releaseEvidenceTopics': audit_payload.get('releaseEvidenceTopics', {}) if isinstance(audit_payload, dict) else {},
        'sourceDeliveryReleaseEligible': True,
        'sourceDeliveryStatus': 'ready_for_source_delivery',
        'sourcePackageRequiresFrontendBuild': True,
        'scenarios': scenarios,
    }


def build_manifest(version_payload: dict[str, Any], runtime_validation: dict[str, Any], *, package_class: str = 'source_delivery', workspace_root: Path | None = None) -> dict[str, Any]:
    workspace_root = workspace_root or Path('.')
    frontend_bundle_included = (workspace_root / 'upper_computer' / 'frontend' / 'dist' / 'index.html').exists()
    runtime_formal = bool(runtime_validation.get('runtimeFormalReleaseEligible', False))
    formal_release_eligible = bool(package_class == 'formal_runnable_release' and frontend_bundle_included and runtime_formal)
    runtime_validation = dict(runtime_validation)
    runtime_validation['frontendBundleIncluded'] = frontend_bundle_included
    runtime_validation['formalReleaseEligible'] = formal_release_eligible
    notes = [
        'Top-level split-delivery CI validates upper-computer workspace, ROS2 Humble runtime, firmware compile gates, firmware contract tests, and protocol regressions.',
        'Rendered from release/version_manifest.yaml; do not hand-edit the generated manifest.',
    ]
    if package_class == 'formal_runnable_release':
        notes.extend([
            'This delivery is a formal runnable release only when formalReleaseEligible=true, strict runtime evidence is ready, and upper_computer/frontend/dist/index.html is included in the bundle.',
            'formalReleaseEligible is derived from strict runtime evidence and frontend bundle presence; missing either downgrades the package to non-formal even if packageClass was requested as formal_runnable_release.',
        ])
    else:
        notes.extend([
            'This delivery is a source package: the frontend dist bundle is intentionally excluded and must be built in the target workspace before strict gateway release mode is enabled.',
            'sourceDeliveryReleaseEligible=true only means the package is valid as source delivery; runtimeFormalReleaseEligible remains governed by strict runtime evidence.',
        ])
    notes.append('Release validation additionally requires release/runtime_validation_matrix.yaml, checked evidence payloads, and delivery documentation.')
    return {
        'schemaVersion': int(version_payload.get('schemaVersion', 1)),
        'releaseId': str(version_payload['releaseId']),
        'generatedFrom': 'release/version_manifest.yaml',
        'packageClass': package_class,
        'protocolVersion': str(version_payload['protocolVersion']),
        'components': {
            'upperComputerWorkspace': {
                'version': str(version_payload['workspaceVersion']),
                'path': 'upper_computer',
                'deliveryKind': 'runnable_workspace' if formal_release_eligible else 'source_workspace',
                'frontendBundleIncluded': frontend_bundle_included,
                'verificationWorkflow': '.github/workflows/split_delivery_ci.yml',
            },
            'stm32StationFirmware': {
                'firmwareVersion': str(version_payload['stm32StationFirmwareVersion']),
                'path': 'firmware/stm32_station_platformio',
                'platformioEnvironment': str(version_payload['platformioEnvironments']['stm32']),
            },
            'esp32CameraFirmware': {
                'firmwareVersion': str(version_payload['esp32CameraFirmwareVersion']),
                'path': 'firmware/esp32s3_camera_platformio',
                'platformioEnvironment': str(version_payload['platformioEnvironments']['esp32']),
            },
        },
        'compatibilityMatrix': [{
            'upperComputerWorkspaceVersion': str(version_payload['workspaceVersion']),
            'stm32StationFirmwareVersion': str(version_payload['stm32StationFirmwareVersion']),
            'esp32CameraFirmwareVersion': str(version_payload['esp32CameraFirmwareVersion']),
            'protocolVersion': str(version_payload['protocolVersion']),
            'status': 'supported',
        }],
        'runtimeValidation': runtime_validation,
        'formalReleaseEligible': formal_release_eligible,
        'notes': notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Render split release manifest from the version source of truth.')
    parser.add_argument('--workspace-root', default='.')
    parser.add_argument('--check', action='store_true', help='Fail if the checked-in manifest does not match the rendered output.')
    parser.add_argument('--package-class', choices=('source_delivery', 'formal_runnable_release'), default='source_delivery')
    args = parser.parse_args()

    root = Path(args.workspace_root).resolve()
    version_manifest = root / 'release' / 'version_manifest.yaml'
    split_manifest = root / 'release' / 'split_release_manifest.yaml'
    version_payload = yaml.safe_load(version_manifest.read_text(encoding='utf-8')) or {}
    rendered = build_manifest(version_payload, _runtime_validation_summary(root), package_class=args.package_class, workspace_root=root)
    rendered_text = yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False)
    if args.check:
        existing = split_manifest.read_text(encoding='utf-8') if split_manifest.exists() else ''
        if existing != rendered_text:
            print('split release manifest is out of date; run scripts/render_split_release_manifest.py', file=sys.stderr)
            return 1
        return 0
    split_manifest.write_text(rendered_text, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
