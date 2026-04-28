#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for package_dir in sorted((ROOT / 'src').iterdir()):
    if package_dir.is_dir():
        sys.path.insert(0, str(package_dir))

from inspection_hmi_gateway.action_contract import ACTION_CONTRACTS

INTERFACE_ACTION_DIR = ROOT / 'src' / 'inspection_interfaces' / 'action'


def expected_action_types() -> dict[str, str]:
    return {
        kind: contract.ros_type
        for kind, contract in ACTION_CONTRACTS.items()
        if contract.capability.execution_policy == 'allowed'
        and contract.capability.generated_client
        and contract.capability.public_catalog
    }


def main() -> int:
    expected = expected_action_types()
    missing: list[str] = []
    invalid_result_contracts: list[str] = []
    for kind, ros_type in sorted(expected.items()):
        action_path = INTERFACE_ACTION_DIR / f'{ros_type}.action'
        if not action_path.exists():
            missing.append(f'{kind}:{ros_type}')
            continue
        text = action_path.read_text(encoding='utf-8')
        if 'string result_json' not in text:
            invalid_result_contracts.append(f'{kind}:{ros_type}:missing_result_json')
    if missing:
        print('missing generated ROS action interface definitions for registry actions:', file=sys.stderr)
        for item in missing:
            print(f'  - {item}', file=sys.stderr)
        return 1
    if invalid_result_contracts:
        print('native-first ROS action result contracts are incomplete:', file=sys.stderr)
        for item in invalid_result_contracts:
            print(f'  - {item}', file=sys.stderr)
        return 1
    print(f'action registry completeness check passed: {len(expected)} native-first action contracts have matching .action definitions and result_json result payload support')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
