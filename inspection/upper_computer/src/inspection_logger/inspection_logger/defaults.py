from __future__ import annotations

from inspection_utils.station_common import DECISION_OUTPUT_TOPIC, SORT_REQUEST_TOPIC

CORE_BAG_TOPICS = [
    '/inspection/image_raw',
    '/inspection/result',
    '/inspection/camera/status',
    '/inspection/capture_request',
    DECISION_OUTPUT_TOPIC,
    SORT_REQUEST_TOPIC,
    '/station/state',
    '/station/count_stats',
    '/station/fault',
    '/inspection/events',
]

DIAGNOSTIC_BAG_TOPICS = [
    '/inspection/image_annotated',
    '/inspection/result_raw',
    '/inspection/diagnostics',
]

DEFAULT_BAG_TOPICS = list(CORE_BAG_TOPICS)


def core_bag_topics() -> list[str]:
    """Return the canonical logger allow-list for core production evidence.

    Returns:
        Ordered topic list required to reconstruct the production main loop.

    Boundary behavior:
        Diagnostic side channels are intentionally excluded so default runtime
        evidence stays aligned with business-closure metrics.
    """
    return list(CORE_BAG_TOPICS)


def diagnostic_bag_topics() -> list[str]:
    """Return the optional diagnostics/debug rosbag topic allow-list."""
    return list(DIAGNOSTIC_BAG_TOPICS)


def default_bag_topics() -> list[str]:
    """Return the default logger rosbag topic allow-list."""
    return list(DEFAULT_BAG_TOPICS)
