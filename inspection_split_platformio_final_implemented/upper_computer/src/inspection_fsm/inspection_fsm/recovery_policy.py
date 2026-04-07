from __future__ import annotations


def classify_fault(code: str) -> str:
    code = (code or '').upper()
    if 'ESTOP' in code:
        return 'hard'
    if 'CRC' in code or 'HEARTBEAT' in code:
        return 'soft'
    if 'TIMEOUT' in code:
        return 'soft'
    if 'SERVO' in code or 'BLOCKED' in code:
        return 'manual'
    return 'soft'
