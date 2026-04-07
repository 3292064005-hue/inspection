#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / '.artifacts' / 'verification'

def scrub_output(text: str) -> str:
    normalized = str(text or '')
    root_str = str(ROOT)
    if root_str: normalized = normalized.replace(root_str, '<workspace_root>')
    return normalized

def main() -> int:
    if len(sys.argv) != 2: raise SystemExit('usage: write_verification_report.py <status-tsv>')
    status_path = Path(sys.argv[1]); rows=[]
    for line in status_path.read_text(encoding='utf-8').splitlines():
        if not line: continue
        name, required, returncode, logfile = line.split('\t', 3); log_path = Path(logfile); output = scrub_output(log_path.read_text(encoding='utf-8') if log_path.exists() else '(missing log)')
        rows.append({'name': name, 'required': required == '1', 'success': int(returncode) == 0, 'returncode': int(returncode), 'logFile': str(log_path.relative_to(ROOT)) if log_path.is_absolute() and ROOT in log_path.parents else str(log_path), 'output': output})
    generated_at = datetime.now(timezone.utc).isoformat(); build_metadata = {'gitSha': os.environ.get('GIT_SHA', '').strip(), 'buildId': os.environ.get('BUILD_ID', '').strip(), 'ciRunId': os.environ.get('GITHUB_RUN_ID', '').strip()}
    provenance_complete = bool(build_metadata['gitSha'] and (build_metadata['buildId'] or build_metadata['ciRunId']))
    if os.environ.get('STRICT_VERIFICATION_PROVENANCE', '').strip().lower() in {'1', 'true', 'yes', 'on'} and not provenance_complete:
        raise SystemExit('verification provenance is incomplete: set GIT_SHA and BUILD_ID/ci run id before generating a release manifest')
    payload = {'schemaVersion': 'v2', 'generatedAt': generated_at, 'statusSource': str(status_path.relative_to(ROOT)) if status_path.is_absolute() and ROOT in status_path.parents else str(status_path), 'allRequiredPassed': all(r['success'] or not r['required'] for r in rows), 'buildMetadata': build_metadata, 'provenanceComplete': provenance_complete, 'buildMode': 'release' if provenance_complete else 'development', 'sourceOfTruth': str((ARTIFACTS / 'verification_manifest.json').relative_to(ROOT)), 'results': rows}
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    manifest_json = json.dumps(payload, ensure_ascii=False, indent=2)
    (ARTIFACTS / 'verification_manifest.json').write_text(manifest_json, encoding='utf-8')
    (ARTIFACTS / 'FINAL_VERIFICATION.json').write_text(manifest_json, encoding='utf-8')
    lines=['# 最终复核报告','',f'- 生成时间：{generated_at}',f"- 状态源：{payload['statusSource']}",f"- 真值源：{payload['sourceOfTruth']}",f"- 必需步骤全部通过：{'是' if payload['allRequiredPassed'] else '否'}",f"- Git SHA：{build_metadata['gitSha'] or '(unknown)'}",f"- Build ID：{build_metadata['buildId'] or build_metadata['ciRunId'] or '(unknown)'}",f"- Provenance 完整：{'是' if provenance_complete else '否'}",'','## 执行结果','']
    for item in rows: lines += [f"### {item['name']}",'',f"- 必需：{'是' if item['required'] else '否'}",f"- 结果：{'通过' if item['success'] else '失败'}",f"- 日志：`{item['logFile']}`",'','```text',str(item['output']).strip() or '(no output)','```','']
    lines += ['## 说明','','- 本报告由 `scripts/validate_workspace.sh` + `scripts/write_verification_report.py` 自动生成。验证报告输出到仓库外的 .artifacts 目录，避免历史生成物继续充当代码事实源。','- 后端 required suites 为阻塞步骤；coverage 脚本改为覆盖真实 Python 包，并支持通过 `BACKEND_COVERAGE_FAIL_UNDER` 提升为阻断式闸门。','- Playwright 本地烟测默认跳过，避免把容器沙箱浏览器限制误判成源码缺陷；CI 可通过 `STRICT_E2E=1` 或本地 `RUN_PLAYWRIGHT_SMOKE=1` 开启。','- 发布模式网关要求前端构建产物存在；若缺失则应在启动期失败，而不是静默退化成“仅 API 存活”。']
    (ARTIFACTS / 'FINAL_VERIFICATION.md').write_text('\n'.join(lines), encoding='utf-8'); return 0
if __name__ == '__main__': raise SystemExit(main())
