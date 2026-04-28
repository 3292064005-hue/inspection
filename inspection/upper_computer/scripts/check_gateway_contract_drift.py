#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from sync_gateway_contracts import OPENAPI_TARGET, ACTION_TS_TARGET, PUBLIC_TS_TARGET, sync


def main() -> int:
    parser = argparse.ArgumentParser(description='Fail if generated gateway contracts are out of date.')
    parser.add_argument('--openapi-target', default=str(OPENAPI_TARGET))
    parser.add_argument('--action-ts-target', default=str(ACTION_TS_TARGET))
    parser.add_argument('--public-ts-target', default=str(PUBLIC_TS_TARGET))
    args = parser.parse_args()

    expected_openapi = Path(args.openapi_target)
    expected_action_ts = Path(args.action_ts_target)
    expected_public_ts = Path(args.public_ts_target)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        openapi_text, action_ts_text, public_ts_text = sync(
            tmp_root / 'inspection_gateway_openapi.json',
            tmp_root / 'actionApi.ts',
            tmp_root / 'gatewayApi.ts',
        )
    current_openapi = expected_openapi.read_text(encoding='utf-8') if expected_openapi.exists() else ''
    current_action_ts = expected_action_ts.read_text(encoding='utf-8') if expected_action_ts.exists() else ''
    current_public_ts = expected_public_ts.read_text(encoding='utf-8') if expected_public_ts.exists() else ''
    if current_openapi != openapi_text or current_action_ts != action_ts_text or current_public_ts != public_ts_text:
        print('gateway contracts are out of date; run python3 scripts/sync_gateway_contracts.py', flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
