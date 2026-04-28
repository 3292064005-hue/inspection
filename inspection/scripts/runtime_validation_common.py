from __future__ import annotations

"""Shared helpers for runtime-validation gate execution and audit rendering."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

PLACEHOLDER_PREFIXES = ('REPLACE_WITH_',)
REQUIRED_ARTIFACT_KEYS = ('logs', 'screenshots', 'videos', 'reports')


def utc_now() -> str:
    """Return an RFC3339 UTC timestamp suitable for audit artifacts."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def load_matrix(path: Path) -> dict[str, Any]:
    """Load and type-check the runtime validation matrix payload."""
    payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if not isinstance(payload, dict):
        raise ValueError('runtime validation matrix payload must be a mapping')
    return payload


def resolve_evidence_root(root: Path, payload: dict[str, Any]) -> tuple[str, Path]:
    """Resolve the configured evidence root from the matrix summary section."""
    summary = payload.get('summary', {}) or {}
    evidence_root = str(summary.get('requiredEvidenceRoot', '')).strip()
    if not evidence_root:
        raise ValueError('runtime validation matrix summary.requiredEvidenceRoot is required')
    return evidence_root, (root / evidence_root)


def scenario_evidence_path(root: Path, evidence_root: str, scenario_id: str) -> Path:
    """Return the canonical evidence path for one scenario id."""
    return root / evidence_root / f'{scenario_id}.json'


def gate_status_path(root: Path, evidence_root: str) -> Path:
    """Return the canonical strict/relaxed gate status artifact path."""
    return root / evidence_root / 'gate_status.json'


def audit_summary_path(root: Path, evidence_root: str) -> Path:
    """Return the canonical audit summary artifact path."""
    return root / evidence_root / 'audit_summary.json'


def sha256_file(path: Path) -> str:
    """Return a stable SHA-256 digest for a file payload."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_jsonable(payload: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-serializable payload."""
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()




def repository_root_from_evidence_path(evidence_path: Path) -> Path:
    """Infer the repository root from a scenario evidence path.

    Args:
        evidence_path: Path below ``release/runtime_validation_evidence``.

    Returns:
        Repository root when the canonical release layout is detected; otherwise
        the evidence file parent is used as a safe fallback.
    """
    parts = [part for part in evidence_path.resolve().parts]
    if 'release' in parts:
        release_index = len(parts) - 1 - list(reversed(parts)).index('release')
        if release_index > 0:
            return Path(*parts[:release_index])
    return evidence_path.resolve().parent


def load_topic_classification(root: Path) -> dict[str, dict[str, Any]]:
    """Load topic classification rows used by release-evidence validation.

    Args:
        root: Repository root.

    Returns:
        Mapping of topic name to normalized classification metadata.

    Boundary behavior:
        Missing classification config fails closed to an empty catalog. A strict
        release in that state cannot prove any core topic evidence and therefore
        cannot accidentally count diagnostic topics as release proof.
    """
    path = root / 'upper_computer' / 'config' / 'system' / 'topic_classification.yaml'
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    raw_topics = payload.get('topics', {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_topics, dict):
        return {}
    catalog: dict[str, dict[str, Any]] = {}
    for raw_topic, raw_item in raw_topics.items():
        topic = str(raw_topic or '').strip()
        if not topic or not isinstance(raw_item, dict):
            continue
        topic_class = str(raw_item.get('class', 'diagnostic') or 'diagnostic').strip().lower()
        if topic_class not in {'core', 'diagnostic', 'debug'}:
            topic_class = 'diagnostic'
        catalog[topic] = {
            'class': topic_class,
            'requiredForReleaseEvidence': bool(raw_item.get('requiredForReleaseEvidence', False)),
            'profile': str(raw_item.get('profile', '') or ''),
            'summary': str(raw_item.get('summary', '') or ''),
        }
    return catalog


def release_topic_sets(root: Path) -> dict[str, list[str]]:
    """Return core, diagnostic, and debug topic partitions for evidence reports."""
    catalog = load_topic_classification(root)
    return {
        'core': sorted(topic for topic, item in catalog.items() if item.get('class') == 'core' and item.get('requiredForReleaseEvidence')),
        'diagnostic': sorted(topic for topic, item in catalog.items() if item.get('class') == 'diagnostic'),
        'debug': sorted(topic for topic, item in catalog.items() if item.get('class') == 'debug'),
    }


def _observed_topic_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        result: set[str] = set()
        for key, raw in value.items():
            if isinstance(raw, dict) and raw.get('observed') is False:
                continue
            if raw is False:
                continue
            result.add(str(key))
        return result
    if isinstance(value, list):
        result = set()
        for item in value:
            if isinstance(item, dict):
                topic = str(item.get('topic', '')).strip()
                if topic and item.get('observed', True) is not False:
                    result.add(topic)
            else:
                topic = str(item).strip()
                if topic:
                    result.add(topic)
        return result
    return set()


def validate_release_topic_evidence(evidence: dict[str, Any], root: Path) -> list[str]:
    """Validate that strict runtime evidence separates core and diagnostic topics.

    Args:
        evidence: Scenario evidence payload.
        root: Repository root containing ``topic_classification.yaml``.

    Returns:
        Normalized error codes. An empty list means all configured core release
        topics were observed and no diagnostic topic was counted as release proof.

    Boundary behavior:
        ``observedTopics`` may contain diagnostic topics for troubleshooting, but
        ``releaseTopics`` may contain only configured core topics.
    """
    topics = release_topic_sets(root)
    core_topics = set(topics['core'])
    diagnostic_topics = set(topics['diagnostic']) | set(topics['debug'])
    observed = _observed_topic_names(evidence.get('observedTopics', evidence.get('topicsObserved', [])))
    release_topics = _observed_topic_names(evidence.get('releaseTopics', []))
    if not observed:
        return ['observedTopics_missing']
    missing_core = sorted(core_topics - observed)
    errors: list[str] = [f'core_topic_not_observed:{topic}' for topic in missing_core]
    if release_topics:
        missing_release_core = sorted(core_topics - release_topics)
        errors.extend(f'core_topic_not_in_releaseTopics:{topic}' for topic in missing_release_core)
        diagnostic_counted = sorted(release_topics & diagnostic_topics)
        errors.extend(f'diagnostic_topic_counted_as_release_evidence:{topic}' for topic in diagnostic_counted)
    else:
        errors.append('releaseTopics_missing')
    unknown_release = sorted(topic for topic in release_topics if topic not in core_topics and topic not in diagnostic_topics)
    errors.extend(f'unknown_release_topic:{topic}' for topic in unknown_release)
    return errors


def is_placeholder(value: Any) -> bool:
    """Return whether a string field still contains template placeholder text."""
    if isinstance(value, str):
        token = value.strip()
        return any(token.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)
    return False


def validate_evidence_payload(
    scenario_id: str,
    scenario: dict[str, Any],
    evidence: dict[str, Any],
    evidence_path: Path,
) -> list[str]:
    """Validate one scenario evidence payload against the matrix contract.

    Args:
        scenario_id: Scenario id from the matrix.
        scenario: Full scenario definition from the matrix.
        evidence: Parsed JSON evidence payload.
        evidence_path: Concrete evidence file location for error reporting.

    Returns:
        A list of normalized validation error codes. The list is collapsed into a
        single file-qualified message so callers can surface one precise error.

    Raises:
        No exception is raised; callers decide how to surface validation errors.

    Boundary behavior:
        Placeholder markers, empty artifact lists, missing checks, and failure
        criteria regressions are all treated as hard validation failures.
    """
    errors: list[str] = []
    if str(evidence.get('scenarioId', '')).strip() != scenario_id:
        errors.append('scenarioId_mismatch')
    if is_placeholder(evidence.get('executedAt')):
        errors.append('executedAt_placeholder')
    if is_placeholder(evidence.get('operator')):
        errors.append('operator_placeholder')
    if is_placeholder(evidence.get('gitCommit')):
        errors.append('gitCommit_placeholder')
    if is_placeholder(evidence.get('notes')):
        errors.append('notes_placeholder')

    expected_checks = evidence.get('expectedChecks', [])
    expected_names = [str(item) for item in scenario.get('expectedChecks', [])]
    if not isinstance(expected_checks, list):
        errors.append('expectedChecks_missing')
    else:
        seen_names = []
        for item in expected_checks:
            if not isinstance(item, dict):
                errors.append('expectedChecks_invalid_item')
                continue
            name = str(item.get('name', '')).strip()
            seen_names.append(name)
            if name not in expected_names:
                errors.append(f'unexpected_check:{name}')
            if not bool(item.get('passed', False)):
                errors.append(f'check_not_passed:{name}')
            if is_placeholder(item.get('evidence')) or not str(item.get('evidence', '')).strip():
                errors.append(f'check_evidence_missing:{name}')
        if seen_names != expected_names:
            errors.append('expectedChecks_order_or_names_mismatch')

    failure_entries = evidence.get('failureCriteria', [])
    expected_failures = [str(item) for item in scenario.get('failureCriteria', [])]
    if not isinstance(failure_entries, list):
        errors.append('failureCriteria_missing')
    else:
        seen_names = []
        for item in failure_entries:
            if not isinstance(item, dict):
                errors.append('failureCriteria_invalid_item')
                continue
            name = str(item.get('name', '')).strip()
            seen_names.append(name)
            if name not in expected_failures:
                errors.append(f'unexpected_failure_criterion:{name}')
            if bool(item.get('observed', False)):
                errors.append(f'failure_observed:{name}')
            if is_placeholder(item.get('details')):
                errors.append(f'failure_details_placeholder:{name}')
        if seen_names != expected_failures:
            errors.append('failureCriteria_order_or_names_mismatch')

    artifacts = evidence.get('artifacts', {})
    if not isinstance(artifacts, dict):
        errors.append('artifacts_missing')
    else:
        artifact_count = 0
        for key in REQUIRED_ARTIFACT_KEYS:
            values = artifacts.get(key)
            if not isinstance(values, list):
                errors.append(f'artifacts_{key}_missing')
                continue
            for value in values:
                artifact_count += 1
                text = str(value).strip()
                if not text or is_placeholder(text):
                    errors.append(f'artifact_placeholder:{key}')
        if artifact_count == 0:
            errors.append('artifacts_empty')

    if str(scenario.get('requiresTopicEvidence', '')).strip().lower() in {'1', 'true', 'yes'} or str(scenario_id) in {'sim_closed_loop', 'full_hardware_closed_loop'}:
        root = repository_root_from_evidence_path(evidence_path)
        errors.extend(validate_release_topic_evidence(evidence, root))

    if not bool(evidence.get('passed', False)):
        errors.append('passed_false')
    if errors:
        joined = ', '.join(errors)
        return [f'{evidence_path}: {joined}']
    return []
