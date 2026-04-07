from __future__ import annotations

from .health_model import DiagnosticsSnapshot


def finalize_snapshot(snapshot: DiagnosticsSnapshot) -> DiagnosticsSnapshot:
    levels = [channel.level for channel in snapshot.channels.values()]
    if 'ERROR' in levels:
        snapshot.overall_level = 'ERROR'
        snapshot.summary = 'one or more critical channels degraded'
    elif 'WARN' in levels:
        snapshot.overall_level = 'WARN'
        snapshot.summary = 'one or more channels degraded'
    else:
        snapshot.overall_level = 'OK'
        snapshot.summary = 'healthy'
    return snapshot
