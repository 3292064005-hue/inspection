#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Report frontend JS bundle sizes and optionally enforce budgets.')
    parser.add_argument('root', nargs='?', default='frontend/dist')
    parser.add_argument('report_path', nargs='?', default='.artifacts/verification/frontend_bundle_report.json')
    parser.add_argument('--max-total-js-kib', type=float, default=None)
    parser.add_argument('--max-largest-bundle-kib', type=float, default=None)
    parser.add_argument('--fail-on-budget', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    assets_dir = root / 'assets'
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not assets_dir.exists():
        report_path.write_text(json.dumps({'status': 'missing_assets_dir', 'root': str(root)}, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0
    bundles = []
    total_js = 0
    for path in sorted(assets_dir.glob('*.js')):
        size = path.stat().st_size
        total_js += size
        bundles.append({'file': path.name, 'sizeBytes': size, 'sizeKiB': round(size / 1024.0, 3)})
    bundles.sort(key=lambda item: item['sizeBytes'], reverse=True)
    largest_bundle_kib = round((bundles[0]['sizeBytes'] / 1024.0), 3) if bundles else 0.0
    report = {
        'status': 'ok',
        'assetRoot': str(assets_dir),
        'totalJsBytes': total_js,
        'totalJsKiB': round(total_js / 1024.0, 3),
        'largestBundleKiB': largest_bundle_kib,
        'budget': {
            'maxTotalJsKiB': args.max_total_js_kib,
            'maxLargestBundleKiB': args.max_largest_bundle_kib,
        },
        'largestBundles': bundles[:10],
    }
    budget_failures: list[str] = []
    if args.max_total_js_kib is not None and report['totalJsKiB'] > args.max_total_js_kib:
        budget_failures.append(f"total JS {report['totalJsKiB']} KiB exceeds budget {args.max_total_js_kib} KiB")
    if args.max_largest_bundle_kib is not None and largest_bundle_kib > args.max_largest_bundle_kib:
        budget_failures.append(f"largest bundle {largest_bundle_kib} KiB exceeds budget {args.max_largest_bundle_kib} KiB")
    if budget_failures:
        report['status'] = 'budget_exceeded'
        report['budgetFailures'] = budget_failures
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if budget_failures and args.fail_on_budget:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
