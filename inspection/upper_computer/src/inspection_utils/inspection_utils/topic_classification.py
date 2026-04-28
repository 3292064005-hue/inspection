from __future__ import annotations

"""Topic classification helpers for release evidence and diagnostics."""

from dataclasses import dataclass
from inspection_utils.config_common import load_yaml
from inspection_utils.io_common import resolve_runtime_path

DEFAULT_TOPIC_CLASSIFICATION_PATH = 'config/system/topic_classification.yaml'

@dataclass(frozen=True, slots=True)
class TopicClassification:
    """Normalized classification for one ROS topic.

    Args:
        topic: Fully qualified topic name.
        topic_class: One of ``core``, ``diagnostic``, or ``debug``.
        required_for_release_evidence: Whether strict release evidence requires the topic.
        profile: Optional runtime profile that enables the topic.
        summary: Human-readable rationale.

    Boundary behavior:
        Immutable and IO-free. Unknown topics are normalized to diagnostic by loader helpers.
    """
    topic: str
    topic_class: str
    required_for_release_evidence: bool
    profile: str = ''
    summary: str = ''
    def to_dict(self) -> dict[str, object]:
        return {'topic': self.topic, 'class': self.topic_class, 'requiredForReleaseEvidence': self.required_for_release_evidence, 'profile': self.profile, 'summary': self.summary}

def topic_classification_catalog(path: str = DEFAULT_TOPIC_CLASSIFICATION_PATH) -> dict[str, TopicClassification]:
    """Load the topic classification catalog.

    Args:
        path: Runtime-relative or absolute YAML path.

    Returns:
        Mapping from topic name to normalized classification.

    Raises:
        ValueError: The YAML root or ``topics`` field is not a mapping.

    Boundary behavior:
        Invalid rows are skipped; malformed roots fail fast to avoid ambiguous release evidence.
    """
    payload = load_yaml(resolve_runtime_path(path, start=__file__)) or {}
    if not isinstance(payload, dict):
        raise ValueError('topic classification payload must be a mapping')
    raw_topics = payload.get('topics', {})
    if not isinstance(raw_topics, dict):
        raise ValueError('topic classification topics must be a mapping')
    catalog: dict[str, TopicClassification] = {}
    for raw_topic, raw_item in raw_topics.items():
        topic = str(raw_topic or '').strip()
        if not topic or not isinstance(raw_item, dict):
            continue
        topic_class = str(raw_item.get('class', 'diagnostic') or 'diagnostic').strip().lower()
        if topic_class not in {'core', 'diagnostic', 'debug'}:
            topic_class = 'diagnostic'
        catalog[topic] = TopicClassification(topic, topic_class, bool(raw_item.get('requiredForReleaseEvidence', False)), str(raw_item.get('profile', '') or ''), str(raw_item.get('summary', '') or ''))
    return catalog

def topic_classification(topic: str, *, path: str = DEFAULT_TOPIC_CLASSIFICATION_PATH) -> TopicClassification:
    """Return normalized classification for one topic; unknown topics fail closed to diagnostic."""
    normalized = str(topic or '').strip()
    return topic_classification_catalog(path).get(normalized, TopicClassification(normalized, 'diagnostic', False, summary='unknown topic defaults to diagnostic'))

def core_release_topics(*, path: str = DEFAULT_TOPIC_CLASSIFICATION_PATH) -> list[str]:
    """Return topics that strict runtime evidence must observe."""
    return sorted(topic for topic, item in topic_classification_catalog(path).items() if item.topic_class == 'core' and item.required_for_release_evidence)
