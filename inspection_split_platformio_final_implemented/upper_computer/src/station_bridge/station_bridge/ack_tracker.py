from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


@dataclass(slots=True)
class PendingCommand:
    seq: int
    command_name: str
    trace_id: str
    item_id: int
    batch_id: str
    issued_at: float
    session_generation: int = 0
    acked: bool = False
    done: bool = False
    failed: bool = False
    cancelled: bool = False
    stale: bool = False
    rejected: bool = False
    superseded: bool = False
    timeout_expired: bool = False
    orphan_response: bool = False
    retry_index: int = 0
    terminal_reason: str = ''
    history: list[dict[str, Any]] = field(default_factory=list)

    def mark(self, state: str, *, reason: str = '') -> None:
        self.history.append({'time': round(time.monotonic(), 6), 'state': state, 'reason': reason})
        self.terminal_reason = reason or self.terminal_reason

    @property
    def state(self) -> str:
        if self.orphan_response:
            return 'orphaned'
        if self.cancelled:
            return 'cancelled'
        if self.rejected:
            return 'rejected'
        if self.superseded:
            return 'superseded'
        if self.timeout_expired:
            return 'timeout_expired'
        if self.stale:
            return 'stale'
        if self.failed:
            return 'failed'
        if self.done:
            return 'done'
        if self.acked:
            return 'acked'
        return 'sent'

    def to_dict(self) -> dict[str, object]:
        return {
            'seq': self.seq,
            'command_name': self.command_name,
            'trace_id': self.trace_id,
            'item_id': self.item_id,
            'batch_id': self.batch_id,
            'issued_at': self.issued_at,
            'session_generation': self.session_generation,
            'acked': self.acked,
            'done': self.done,
            'failed': self.failed,
            'cancelled': self.cancelled,
            'stale': self.stale,
            'rejected': self.rejected,
            'superseded': self.superseded,
            'timeout_expired': self.timeout_expired,
            'orphan_response': self.orphan_response,
            'retry_index': self.retry_index,
            'state': self.state,
            'terminal_reason': self.terminal_reason,
            'history': list(self.history),
        }


class AckTracker:
    def __init__(self) -> None:
        self._pending: dict[int, PendingCommand] = {}
        self._history: list[PendingCommand] = []

    def register(self, seq: int, command_name: str, trace_id: str, item_id: int, batch_id: str, retry_index: int = 0, session_generation: int = 0) -> PendingCommand:
        pending = PendingCommand(
            seq=seq,
            command_name=command_name,
            trace_id=trace_id,
            item_id=item_id,
            batch_id=batch_id,
            issued_at=time.monotonic(),
            retry_index=retry_index,
            session_generation=session_generation,
        )
        pending.mark('sent')
        self._pending[seq] = pending
        return pending

    def get(self, seq: int, *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self._pending.get(seq)
        if pending is None:
            return None
        if session_generation is not None and pending.session_generation != session_generation:
            return None
        return pending

    def _finalize(self, pending: PendingCommand) -> PendingCommand:
        self._history.append(pending)
        self._pending.pop(pending.seq, None)
        return pending

    def mark_ack(self, seq: int, *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self.get(seq, session_generation=session_generation)
        if pending is not None:
            pending.acked = True
            pending.mark('acked')
        return pending

    def mark_done(self, seq: int, *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self.get(seq, session_generation=session_generation)
        if pending is not None:
            pending.done = True
            pending.mark('done')
            self._finalize(pending)
        return pending

    def mark_failed(self, seq: int, reason: str = '', *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self.get(seq, session_generation=session_generation)
        if pending is not None:
            pending.failed = True
            pending.mark('failed', reason=reason)
        return pending

    def mark_rejected(self, seq: int, reason: str = '', *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self.get(seq, session_generation=session_generation)
        if pending is not None:
            pending.rejected = True
            pending.mark('rejected', reason=reason)
            self._finalize(pending)
        return pending

    def mark_superseded(self, seq: int, reason: str = '', *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self.get(seq, session_generation=session_generation)
        if pending is not None:
            pending.superseded = True
            pending.mark('superseded', reason=reason)
            self._finalize(pending)
        return pending

    def mark_timeout(self, seq: int, reason: str = '', *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self.get(seq, session_generation=session_generation)
        if pending is not None:
            pending.timeout_expired = True
            pending.mark('timeout_expired', reason=reason)
            self._finalize(pending)
        return pending

    def mark_stale(self, seq: int, reason: str = '', *, session_generation: int | None = None) -> PendingCommand | None:
        pending = self.get(seq, session_generation=session_generation)
        if pending is not None:
            pending.stale = True
            pending.mark('stale', reason=reason)
            self._finalize(pending)
        return pending

    def invalidate_other_generations(self, active_generation: int, *, reason: str = 'session_rollover') -> list[PendingCommand]:
        invalidated: list[PendingCommand] = []
        for seq, pending in list(self._pending.items()):
            if pending.session_generation != active_generation:
                pending.superseded = True
                pending.mark('superseded', reason=reason)
                invalidated.append(self._finalize(pending))
        return invalidated

    def record_orphan_response(self, seq: int, command_name: str, *, reason: str = '', trace_id: str = '', item_id: int = -1, batch_id: str = '', session_generation: int = 0) -> PendingCommand:
        orphan = PendingCommand(
            seq=seq,
            command_name=command_name,
            trace_id=trace_id,
            item_id=item_id,
            batch_id=batch_id,
            issued_at=time.monotonic(),
            orphan_response=True,
            failed=True,
            terminal_reason=reason,
            session_generation=session_generation,
        )
        orphan.mark('orphaned', reason=reason)
        self._history.append(orphan)
        return orphan

    def cancel_by_trace(self, trace_id: str) -> list[PendingCommand]:
        cancelled: list[PendingCommand] = []
        for seq, pending in list(self._pending.items()):
            if pending.trace_id == trace_id:
                pending.cancelled = True
                pending.mark('cancelled', reason='cancel_by_trace')
                cancelled.append(self._finalize(pending))
        return cancelled

    def oldest_pending(self, command_name: str | None = None, *, session_generation: int | None = None) -> PendingCommand | None:
        candidates = [item for item in self._pending.values() if (command_name is None or item.command_name == command_name) and (session_generation is None or item.session_generation == session_generation)]
        if not candidates:
            return None
        return min(candidates, key=lambda item: item.issued_at)

    def stale(self, timeout_sec: float, *, mark: bool = False, session_generation: int | None = None) -> list[PendingCommand]:
        now = time.monotonic()
        stale_items = [item for item in list(self._pending.values()) if (session_generation is None or item.session_generation == session_generation) and not item.done and not item.cancelled and (now - item.issued_at) > timeout_sec]
        if mark:
            for item in stale_items:
                self.mark_timeout(item.seq, reason=f'>{timeout_sec}s', session_generation=item.session_generation)
        return stale_items

    def snapshot(self) -> list[dict[str, object]]:
        records = list(self._pending.values()) + list(self._history[-48:])
        return [pending.to_dict() for pending in sorted(records, key=lambda item: item.issued_at)]
