from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for package_root in (ROOT / 'src').iterdir():
    if package_root.is_dir() and (package_root / package_root.name).is_dir():
        sys.path.insert(0, str(package_root.resolve()))
