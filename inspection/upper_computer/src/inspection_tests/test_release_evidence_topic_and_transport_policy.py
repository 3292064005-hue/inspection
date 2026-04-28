from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOP = ROOT.parent
SCRIPTS_DIR = TOP / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
for package_dir in sorted((ROOT / 'src').iterdir()):
    if package_dir.is_dir() and str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))

from runtime_validation_common import release_topic_sets, validate_release_topic_evidence  # noqa: E402
from inspection_utils.transport_boundary import legacy_removal_status, transport_bridge_policy  # noqa: E402


def test_release_topic_evidence_counts_only_core_topics() -> None:
    topics = release_topic_sets(TOP)
    assert '/inspection/result' in topics['core']
    assert '/inspection/image_annotated' in topics['diagnostic']

    evidence = {
        'observedTopics': topics['core'] + topics['diagnostic'],
        'releaseTopics': topics['core'],
    }
    assert validate_release_topic_evidence(evidence, TOP) == []

    bad = {
        'observedTopics': topics['core'] + topics['diagnostic'],
        'releaseTopics': topics['core'] + ['/inspection/image_annotated'],
    }
    errors = validate_release_topic_evidence(bad, TOP)
    assert 'diagnostic_topic_counted_as_release_evidence:/inspection/image_annotated' in errors


def test_legacy_transport_policy_has_hard_removal_gate() -> None:
    policy = transport_bridge_policy('control')
    payload = policy.to_dict()
    assert payload['legacyTelemetryEnabled'] is True
    assert payload['zeroUsageRemovalAfterReleases'] == 2
    assert payload['removalCandidateWhenZeroUsage'] is True
    assert payload['releaseNoteRequired'] is True
    status = legacy_removal_status('control', {'2026.Q2': 0, '2026.Q3': 0})
    assert status['removalCandidate'] is True
    assert status['rollbackStrategy'] == 'tagged_release_hotfix_only'
