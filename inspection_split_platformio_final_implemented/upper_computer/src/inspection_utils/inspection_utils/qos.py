from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:  # pragma: no cover - depends on ROS runtime
    from rclpy.duration import Duration
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, LivelinessPolicy, QoSProfile, ReliabilityPolicy
except Exception:  # pragma: no cover
    QoSProfile = Any  # type: ignore
    Duration = Any  # type: ignore
    DurabilityPolicy = HistoryPolicy = LivelinessPolicy = ReliabilityPolicy = None  # type: ignore


@dataclass(frozen=True, slots=True)
class QoSProfileSpec:
    """Declarative QoS profile specification.

    Attributes:
        name: Logical profile name.
        reliability: Reliability policy label.
        depth: Queue depth.
        history: History policy label.
        durability: Durability policy label.
        deadline_ms: Expected message deadline in milliseconds.
        liveliness: Liveliness policy label.
        lease_duration_ms: Liveliness lease duration in milliseconds.
    """

    name: str
    reliability: str
    depth: int
    history: str = 'KEEP_LAST'
    durability: str = 'VOLATILE'
    deadline_ms: int = 0
    liveliness: str = 'AUTOMATIC'
    lease_duration_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            'name': self.name,
            'reliability': self.reliability,
            'depth': self.depth,
            'history': self.history,
            'durability': self.durability,
            'deadlineMs': self.deadline_ms,
            'liveliness': self.liveliness,
            'leaseDurationMs': self.lease_duration_ms,
        }


QOS_SPECS = {
    'sensor_data': QoSProfileSpec(name='sensor_data', reliability='BEST_EFFORT', depth=5, durability='VOLATILE', deadline_ms=120, liveliness='AUTOMATIC', lease_duration_ms=500),
    'result': QoSProfileSpec(name='result', reliability='RELIABLE', depth=20, durability='VOLATILE', deadline_ms=500, liveliness='AUTOMATIC', lease_duration_ms=1000),
    'event': QoSProfileSpec(name='event', reliability='RELIABLE', depth=50, durability='VOLATILE', deadline_ms=1000, liveliness='AUTOMATIC', lease_duration_ms=3000),
    'station_state': QoSProfileSpec(name='station_state', reliability='RELIABLE', depth=20, durability='VOLATILE', deadline_ms=250, liveliness='AUTOMATIC', lease_duration_ms=1000),
    'control': QoSProfileSpec(name='control', reliability='RELIABLE', depth=20, durability='VOLATILE', deadline_ms=250, liveliness='MANUAL_BY_TOPIC', lease_duration_ms=1000),
    'diagnostics': QoSProfileSpec(name='diagnostics', reliability='RELIABLE', depth=20, durability='TRANSIENT_LOCAL', deadline_ms=1000, liveliness='AUTOMATIC', lease_duration_ms=5000),
    'lifecycle': QoSProfileSpec(name='lifecycle', reliability='RELIABLE', depth=20, durability='TRANSIENT_LOCAL', deadline_ms=1000, liveliness='AUTOMATIC', lease_duration_ms=5000),
    'replay': QoSProfileSpec(name='replay', reliability='RELIABLE', depth=100, durability='VOLATILE', deadline_ms=2000, liveliness='AUTOMATIC', lease_duration_ms=5000),
}


def qos_profile(name: str) -> QoSProfile | QoSProfileSpec:
    """Build a ROS QoS profile or return the declarative spec in test mode."""
    spec = QOS_SPECS[name]
    if ReliabilityPolicy is None or QoSProfile is Any:
        return spec
    reliability = ReliabilityPolicy.BEST_EFFORT if spec.reliability == 'BEST_EFFORT' else ReliabilityPolicy.RELIABLE
    history = HistoryPolicy.KEEP_LAST
    durability = DurabilityPolicy.TRANSIENT_LOCAL if spec.durability == 'TRANSIENT_LOCAL' else DurabilityPolicy.VOLATILE
    liveliness = LivelinessPolicy.MANUAL_BY_TOPIC if spec.liveliness == 'MANUAL_BY_TOPIC' else LivelinessPolicy.AUTOMATIC
    kwargs: dict[str, object] = {
        'reliability': reliability,
        'history': history,
        'depth': spec.depth,
        'durability': durability,
        'liveliness': liveliness,
    }
    if spec.deadline_ms > 0 and Duration is not Any:
        kwargs['deadline'] = Duration(nanoseconds=int(spec.deadline_ms) * 1_000_000)
    if spec.lease_duration_ms > 0 and Duration is not Any:
        kwargs['liveliness_lease_duration'] = Duration(nanoseconds=int(spec.lease_duration_ms) * 1_000_000)
    return QoSProfile(**kwargs)


def qos_summary() -> dict[str, dict[str, object]]:
    """Return the declarative QoS profile summary."""
    return {name: spec.to_dict() for name, spec in QOS_SPECS.items()}


def qos_policy_matrix() -> list[dict[str, object]]:
    """Return the ordered QoS policy matrix used by diagnostics and tests."""
    return [spec.to_dict() for _name, spec in QOS_SPECS.items()]


def qos_compatibility_warnings(*, publisher: str, subscriber: str) -> list[str]:
    """Return coarse compatibility warnings between two logical QoS profiles.

    Args:
        publisher: Publisher-side logical QoS profile name.
        subscriber: Subscriber-side logical QoS profile name.

    Returns:
        A list of human-readable warnings describing risky or incompatible
        combinations.
    """
    warnings: list[str] = []
    pub = QOS_SPECS[publisher]
    sub = QOS_SPECS[subscriber]
    if pub.reliability != sub.reliability and pub.reliability == 'BEST_EFFORT' and sub.reliability == 'RELIABLE':
        warnings.append('publisher_best_effort_to_reliable_subscriber')
    if pub.durability != sub.durability:
        warnings.append('durability_mismatch')
    if pub.deadline_ms and sub.deadline_ms and pub.deadline_ms > sub.deadline_ms:
        warnings.append('publisher_deadline_slower_than_subscriber_expectation')
    return warnings
