from __future__ import annotations
import re
from typing import Any
_RESULT_SANITIZE_RE = re.compile(r'[^A-Za-z0-9._-]+')
def _slug(value: Any) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    return _RESULT_SANITIZE_RE.sub('-', raw).strip('-._')[:120]
def canonical_result_id(*, result_id: Any = '', trace_id: Any = '', batch_id: Any = '', item_id: Any = '', timestamp: Any = '') -> str:
    explicit = _slug(result_id)
    if explicit:
        return explicit
    batch = _slug(batch_id)
    item = _slug(item_id)
    ts = _slug(timestamp)
    trace = _slug(trace_id)
    parts = [part for part in (batch, item, ts) if part]
    if parts:
        return 'result-' + '-'.join(parts)
    if trace:
        return f'result-{trace}'
    return 'result-unknown'
