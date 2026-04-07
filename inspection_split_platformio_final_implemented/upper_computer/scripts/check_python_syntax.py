#!/usr/bin/env python3
from __future__ import annotations
import pathlib, py_compile, sys

def main() -> int:
    failures=[]; files=sorted(pathlib.Path('src').rglob('*.py')) + sorted(pathlib.Path('scripts').rglob('*.py'))
    for path in files:
        try: py_compile.compile(str(path), doraise=True)
        except Exception as exc: failures.append((str(path), str(exc)))
    if failures:
        print('Python syntax check failed for the following files:', file=sys.stderr)
        for file_path, detail in failures: print(f'- {file_path}: {detail}', file=sys.stderr)
        return 1
    print(f'Python syntax check passed for {len(files)} files.')
    return 0
if __name__ == '__main__': raise SystemExit(main())
