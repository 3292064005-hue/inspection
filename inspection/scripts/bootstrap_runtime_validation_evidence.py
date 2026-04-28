#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description='Populate missing runtime validation evidence files from templates.')
    parser.add_argument('--workspace-root', default='.')
    parser.add_argument('--force', action='store_true', help='Overwrite existing evidence files.')
    args = parser.parse_args()

    root = Path(args.workspace_root).resolve()
    template_root = root / 'release' / 'runtime_validation_evidence' / 'templates'
    evidence_root = root / 'release' / 'runtime_validation_evidence'
    if not template_root.exists():
        print(f'missing template root: {template_root}', file=sys.stderr)
        return 1
    copied = 0
    skipped = 0
    for template in sorted(template_root.glob('*.json')):
        target = evidence_root / template.name
        if target.exists() and not args.force:
            skipped += 1
            continue
        shutil.copyfile(template, target)
        copied += 1
    print(f'[OK] runtime validation evidence bootstrap finished (copied={copied}, skipped={skipped})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
