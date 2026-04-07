from __future__ import annotations


def classify_severity(*, decision: str, defect_type: str, valid: bool, score: float) -> str:
    decision = str(decision).upper()
    defect_type = str(defect_type or 'NONE').upper()
    if decision == 'RECHECK':
        return 'recheck'
    if decision == 'NG':
        if not valid or defect_type in {'IMAGE_QUALITY', 'NO_CONTOUR', 'AREA_OUT_OF_RANGE', 'BAD_ORIENTATION'}:
            return 'soft_fail'
        return 'hard_fail'
    if score < 0.25:
        return 'warning'
    return 'info'
