from __future__ import annotations

DEFAULT_BAG_TOPICS = [
    '/inspection/image_raw',
    '/inspection/image_annotated',
    '/inspection/result',
    '/inspection/result_raw',
    '/inspection/camera/status',
    '/inspection/capture_request',
    '/station/sort_cmd',
    '/station/state',
    '/station/count_stats',
    '/station/fault',
    '/inspection/events',
    '/inspection/diagnostics',
]


def default_bag_topics() -> list[str]:
    """Return the canonical logger rosbag topic allow-list."""
    return list(DEFAULT_BAG_TOPICS)
