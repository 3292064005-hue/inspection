from __future__ import annotations

from pathlib import Path
from datetime import datetime, UTC
from typing import Any
import json


def append_jsonl(path: str | Path, record: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')


def utc_now_str() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def safe_json_loads(raw: str | bytes | None, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is None:
        default = {}
    if raw is None:
        return dict(default)
    try:
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        value = json.loads(raw)
        return value if isinstance(value, dict) else dict(default)
    except Exception:
        return dict(default)


def build_event_record(event_type: str, **fields: Any) -> dict[str, Any]:
    record = {'type': event_type, **fields}
    record.setdefault('time', utc_now_str())
    return record


def event_to_json(event_type: str, **fields: Any) -> str:
    return json.dumps(build_event_record(event_type, **fields), ensure_ascii=False, sort_keys=True)
