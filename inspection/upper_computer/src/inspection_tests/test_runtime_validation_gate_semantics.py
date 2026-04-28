from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import render_runtime_validation_audit  # noqa: E402
import render_split_release_manifest  # noqa: E402
import run_runtime_validation_matrix  # noqa: E402
import validate_split_environment  # noqa: E402
from runtime_validation_common import release_topic_sets  # noqa: E402


def _run_script_main(module, args: list[str]) -> tuple[int, str, str]:
    old_argv = sys.argv[:]
    stdout = io.StringIO()
    stderr = io.StringIO()
    try:
        sys.argv = [getattr(module, '__file__', 'script')] + args
        with redirect_stdout(stdout), redirect_stderr(stderr):
            rc = int(module.main())
    finally:
        sys.argv = old_argv
    return rc, stdout.getvalue(), stderr.getvalue()


def test_runtime_validation_runner_reports_gate_counts_for_relaxed_mode(tmp_path: Path) -> None:
    matrix_path = tmp_path / 'runtime_validation_matrix.yaml'
    matrix_payload = {
        'summary': {
            'requiredEvidenceRoot': 'release/runtime_validation_evidence',
            'topicClassificationPath': 'upper_computer/config/system/topic_classification.yaml',
        },
        'scenarios': [
            {
                'id': 'sim_closed_loop',
                'required': True,
                'trigger': 'echo sim',
                'hardware': {'stm32': False, 'esp32s3': False},
            },
            {
                'id': 'upper_computer_with_stm32',
                'required': True,
                'hardware': {'stm32': True, 'esp32s3': False},
            },
        ],
    }
    matrix_path.write_text(yaml.safe_dump(matrix_payload, sort_keys=False), encoding='utf-8')
    rc, stdout, stderr = _run_script_main(
        run_runtime_validation_matrix,
        [
            '--workspace-root',
            str(tmp_path),
            '--matrix-path',
            'runtime_validation_matrix.yaml',
            '--skip-sim-execution',
            '--allow-missing-hardware-evidence',
        ],
    )
    assert rc == 0, stderr
    assert 'matrix evaluated:' in stdout
    assert 'status=internal_unvalidated' in stdout
    assert 'sim_executed=0' in stdout
    assert 'sim_evidence_verified=0' in stdout
    assert 'hardware_evidence_verified=0' in stdout
    assert 'relaxed_hardware_skips=1' in stdout
    assert 'sim_skips=1' in stdout
    assert 'gate_status=release/runtime_validation_evidence/gate_status.json' in stdout
    gate_status = tmp_path / 'release' / 'runtime_validation_evidence' / 'gate_status.json'
    assert gate_status.exists()
    payload = yaml.safe_load(gate_status.read_text(encoding='utf-8'))
    assert payload['passed'] is False
    assert payload['status'] == 'internal_unvalidated'
    assert 'executed/verified' not in stdout


def test_validate_split_environment_marks_optional_checks_as_skip() -> None:
    rc, stdout, stderr = _run_script_main(validate_split_environment, ['--workspace-root', str(REPO_ROOT), '--mode', 'dev'])
    assert rc == 0, stderr
    assert '[SKIP] ubuntu_release:' in stdout
    assert '[SKIP] node:' in stdout
    assert '[SKIP] colcon:' in stdout
    assert '[SKIP] platformio:' in stdout
    assert '[SKIP] ros_distro:' in stdout
    assert '[FAIL]' not in stdout


def test_render_runtime_validation_audit_detects_missing_release_readiness(tmp_path: Path) -> None:
    release_dir = tmp_path / 'release' / 'runtime_validation_evidence'
    release_dir.mkdir(parents=True)
    matrix_path = tmp_path / 'release' / 'runtime_validation_matrix.yaml'
    matrix_payload = {
        'summary': {
            'requiredEvidenceRoot': 'release/runtime_validation_evidence',
            'topicClassificationPath': 'upper_computer/config/system/topic_classification.yaml',
        },
        'scenarios': [
            {
                'id': 'sim_closed_loop',
                'tier': 'P0',
                'required': True,
                'trigger': 'echo sim',
                'hardware': {'stm32': False, 'esp32s3': False},
            },
            {
                'id': 'upper_computer_with_stm32',
                'tier': 'P0',
                'required': True,
                'hardware': {'stm32': True, 'esp32s3': False},
                'expectedChecks': [],
                'failureCriteria': [],
            },
        ],
    }
    matrix_path.write_text(yaml.safe_dump(matrix_payload, sort_keys=False), encoding='utf-8')
    target = render_runtime_validation_audit.render_audit(tmp_path)
    payload = yaml.safe_load(target.read_text(encoding='utf-8'))
    assert payload['releaseGateEligible'] is False
    assert payload['overallStatus'] == 'missing_required_evidence'
    assert 'gate_status_missing' in payload['gateValidationErrors']


def test_render_runtime_validation_audit_marks_relaxed_gate_as_internal_unvalidated(tmp_path: Path) -> None:
    release_dir = tmp_path / 'release' / 'runtime_validation_evidence'
    release_dir.mkdir(parents=True)
    matrix_path = tmp_path / 'release' / 'runtime_validation_matrix.yaml'
    matrix_payload = {
        'summary': {
            'requiredEvidenceRoot': 'release/runtime_validation_evidence',
            'topicClassificationPath': 'upper_computer/config/system/topic_classification.yaml',
        },
        'scenarios': [
            {
                'id': 'sim_closed_loop',
                'tier': 'P0',
                'required': True,
                'trigger': 'echo sim',
                'hardware': {'stm32': False, 'esp32s3': False},
            },
            {
                'id': 'upper_computer_with_stm32',
                'tier': 'P0',
                'required': True,
                'hardware': {'stm32': True, 'esp32s3': False},
                'expectedChecks': [],
                'failureCriteria': [],
            },
        ],
    }
    matrix_path.write_text(yaml.safe_dump(matrix_payload, sort_keys=False), encoding='utf-8')
    rc, _stdout, stderr = _run_script_main(
        run_runtime_validation_matrix,
        [
            '--workspace-root',
            str(tmp_path),
            '--matrix-path',
            'release/runtime_validation_matrix.yaml',
            '--skip-sim-execution',
            '--allow-missing-hardware-evidence',
        ],
    )
    assert rc == 0, stderr
    target = render_runtime_validation_audit.render_audit(tmp_path)
    payload = yaml.safe_load(target.read_text(encoding='utf-8'))
    assert payload['releaseGateEligible'] is False
    assert payload['overallStatus'] == 'internal_unvalidated'
    assert payload['verificationMode'] == 'relaxed'
    assert payload['gateValidationErrors'] == []
    assert 'formal_release_requires_strict_gate' in payload['gateValidationNotes']
    scenarios = {entry['id']: entry for entry in payload['scenarios']}
    assert scenarios['sim_closed_loop']['status'] == 'omitted_internal_unvalidated'
    assert scenarios['upper_computer_with_stm32']['status'] == 'omitted_internal_unvalidated'


def test_strict_runtime_evidence_and_frontend_dist_enable_formal_manifest(tmp_path: Path) -> None:
    release_dir = tmp_path / 'release'
    evidence_dir = release_dir / 'runtime_validation_evidence'
    evidence_dir.mkdir(parents=True)
    config_dir = tmp_path / 'upper_computer' / 'config' / 'system'
    config_dir.mkdir(parents=True)
    (config_dir / 'topic_classification.yaml').write_text((REPO_ROOT / 'upper_computer' / 'config' / 'system' / 'topic_classification.yaml').read_text(encoding='utf-8'), encoding='utf-8')
    dist_dir = tmp_path / 'upper_computer' / 'frontend' / 'dist'
    dist_dir.mkdir(parents=True)
    (dist_dir / 'index.html').write_text('<!doctype html><title>ok</title>\n', encoding='utf-8')
    (release_dir / 'version_manifest.yaml').write_text(
        yaml.safe_dump(
            {
                'schemaVersion': 1,
                'releaseId': 'test-release',
                'protocolVersion': 'v1',
                'workspaceVersion': 'upper-computer-test',
                'stm32StationFirmwareVersion': 'stm32-test',
                'esp32CameraFirmwareVersion': 'esp32-test',
                'platformioEnvironments': {'stm32': 'native', 'esp32': 'native'},
            },
            sort_keys=False,
        ),
        encoding='utf-8',
    )
    matrix_payload = {
        'summary': {
            'requiredEvidenceRoot': 'release/runtime_validation_evidence',
            'topicClassificationPath': 'upper_computer/config/system/topic_classification.yaml',
        },
        'scenarios': [
            {
                'id': 'sim_closed_loop',
                'tier': 'P0',
                'required': True,
                'trigger': 'true',
                'hardware': {'stm32': False, 'esp32s3': False},
                'expectedChecks': ['start_batch_closed_loop'],
                'failureCriteria': ['action_job_not_terminal'],
                'requiresTopicEvidence': True,
            },
        ],
    }
    (release_dir / 'runtime_validation_matrix.yaml').write_text(yaml.safe_dump(matrix_payload, sort_keys=False), encoding='utf-8')
    topic_sets = release_topic_sets(tmp_path)
    (evidence_dir / 'sim_closed_loop.json').write_text(
        json.dumps(
            {
                'schemaVersion': 1,
                'scenarioId': 'sim_closed_loop',
                'executedAt': '2026-04-28T00:00:00Z',
                'operator': 'ci',
                'gitCommit': 'testcommit',
                'notes': 'strict simulation evidence generated by test',
                'passed': True,
                'expectedChecks': [{'name': 'start_batch_closed_loop', 'passed': True, 'evidence': 'sim check passed'}],
                'failureCriteria': [{'name': 'action_job_not_terminal', 'observed': False, 'details': 'not observed'}],
                'observedTopics': topic_sets['core'] + topic_sets['diagnostic'],
                'releaseTopics': topic_sets['core'],
                'diagnosticTopics': topic_sets['diagnostic'],
                'artifacts': {'logs': ['logs/sim.log'], 'screenshots': [], 'videos': [], 'reports': ['reports/sim.json']},
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=False,
        ) + '\n',
        encoding='utf-8',
    )
    rc, stdout, stderr = _run_script_main(

        run_runtime_validation_matrix,
        [
            '--workspace-root',
            str(tmp_path),
            '--matrix-path',
            'release/runtime_validation_matrix.yaml',
            '--strict-hardware-evidence',
        ],
    )
    assert rc == 0, stderr
    assert 'status=release_ready' in stdout
    target = render_runtime_validation_audit.render_audit(tmp_path)
    payload = yaml.safe_load(target.read_text(encoding='utf-8'))
    assert payload['releaseGateEligible'] is True

    version_payload = yaml.safe_load((release_dir / 'version_manifest.yaml').read_text(encoding='utf-8'))
    runtime_summary = render_split_release_manifest._runtime_validation_summary(tmp_path)
    rendered = render_split_release_manifest.build_manifest(version_payload, runtime_summary, package_class='formal_runnable_release', workspace_root=tmp_path)
    (release_dir / 'split_release_manifest.yaml').write_text(yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False), encoding='utf-8')
    assert rendered['packageClass'] == 'formal_runnable_release'
    assert rendered['formalReleaseEligible'] is True
    assert rendered['runtimeValidation']['frontendBundleIncluded'] is True
    assert '/inspection/image_annotated' in rendered['runtimeValidation']['releaseEvidenceTopics']['diagnostic']
