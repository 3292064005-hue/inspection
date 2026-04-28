#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
FRONTEND_DIST_DIR="$FRONTEND_DIR/dist"
LOG_DIR="$ROOT_DIR/.artifacts/verification/logs"
STATUS_TSV="$LOG_DIR/status.tsv"
FRONTEND_DIST_PREEXISTED=0
if [[ -d "$FRONTEND_DIST_DIR" ]]; then
  FRONTEND_DIST_PREEXISTED=1
fi

cleanup_generated_frontend_dist() {
  if [[ "$FRONTEND_DIST_PREEXISTED" -eq 0 ]]; then
    rm -rf "$FRONTEND_DIST_DIR"
  fi
}

trap cleanup_generated_frontend_dist EXIT

mkdir -p "$LOG_DIR"
: > "$STATUS_TSV"

run_step() {
  local name="$1"
  local required="$2"
  shift 2
  local safe_name
  safe_name="$(printf '%s' "$name" | tr '[:upper:] ' '[:lower:]_' | tr -cd 'a-z0-9_')"
  local log_file="$LOG_DIR/${safe_name}.log"
  set +e
  "$@" >"$log_file" 2>&1
  local rc=$?
  set -e
  printf '%s\t%s\t%s\t%s\n' "$name" "$required" "$rc" "$log_file" >> "$STATUS_TSV"
  if [[ "$rc" -ne 0 && "$required" = "1" ]]; then
    python3 "$ROOT_DIR/scripts/write_verification_report.py" "$STATUS_TSV"
    exit "$rc"
  fi
}

cd "$ROOT_DIR"
run_step "Backend syntax check" 1 python3 scripts/check_python_syntax.py
run_step "Action registry drift check" 1 python3 scripts/sync_action_registry.py --check
run_step "Action registry completeness" 1 python3 scripts/validate_action_registry_completeness.py
run_step "Gateway contract drift check" 1 python3 scripts/check_gateway_contract_drift.py
run_step "Backend required tests" 1 bash scripts/run_backend_required_tests.sh
run_step "Backend runtime smoke tests" 1 bash scripts/run_backend_runtime_smoke_tests.sh
if [[ "${ENABLE_BACKEND_RELEASE_GATE:-0}" = "1" ]]; then
  run_step "Backend release gate" 1 bash scripts/run_backend_release_gate.sh
else
  printf '%s\t%s\t%s\t%s\n' "Backend release gate" "0" "0" "$LOG_DIR/backend_release_gate.log" >> "$STATUS_TSV"
  printf '%s\n' 'Skipped locally. Set ENABLE_BACKEND_RELEASE_GATE=1 to execute the full backend release gate.' > "$LOG_DIR/backend_release_gate.log"
fi
run_step "Backend coverage report" 0 bash scripts/run_backend_coverage_report.sh

if [[ -x "$FRONTEND_DIR/node_modules/.bin/vitest" && -x "$FRONTEND_DIR/node_modules/.bin/vite" && -x "$FRONTEND_DIR/node_modules/.bin/vue-tsc" ]]; then
  printf '%s\n' 'Frontend dependencies already present; install step skipped.' > "$LOG_DIR/frontend_install.log"
  printf '%s\t%s\t%s\t%s\n' "Frontend install" "1" "0" "$LOG_DIR/frontend_install.log" >> "$STATUS_TSV"
else
  run_step "Frontend install" 1 npm ci --prefix "$FRONTEND_DIR" --prefer-offline --no-audit --progress=false
fi

run_step "Frontend unit tests" 1 npm --prefix "$FRONTEND_DIR" test
run_step "Frontend typecheck" 1 npm --prefix "$FRONTEND_DIR" run typecheck
run_step "Frontend lint" 1 npm --prefix "$FRONTEND_DIR" run lint
run_step "Frontend build" 1 npm --prefix "$FRONTEND_DIR" run build:real
FRONTEND_BUNDLE_ARGS=("$FRONTEND_DIR/dist" "$ROOT_DIR/.artifacts/verification/frontend_bundle_report.json")
if [[ -n "${FRONTEND_MAX_TOTAL_JS_KIB:-}" ]]; then
  FRONTEND_BUNDLE_ARGS+=(--max-total-js-kib "${FRONTEND_MAX_TOTAL_JS_KIB}")
fi
if [[ -n "${FRONTEND_MAX_LARGEST_BUNDLE_KIB:-}" ]]; then
  FRONTEND_BUNDLE_ARGS+=(--max-largest-bundle-kib "${FRONTEND_MAX_LARGEST_BUNDLE_KIB}")
fi
if [[ "${STRICT_FRONTEND_BUNDLE_BUDGET:-0}" = "1" ]]; then
  FRONTEND_BUNDLE_ARGS+=(--fail-on-budget)
  run_step "Frontend bundle report" 1 python3 scripts/report_frontend_bundle_sizes.py "${FRONTEND_BUNDLE_ARGS[@]}"
else
  run_step "Frontend bundle report" 0 python3 scripts/report_frontend_bundle_sizes.py "${FRONTEND_BUNDLE_ARGS[@]}"
fi
if [[ "${STRICT_FRONTEND_COVERAGE:-0}" = "1" ]]; then
  run_step "Frontend coverage" 1 npm --prefix "$FRONTEND_DIR" run coverage
else
  run_step "Frontend coverage" 0 npm --prefix "$FRONTEND_DIR" run coverage
fi

if [[ "${STRICT_E2E:-0}" = "1" || "${RUN_PLAYWRIGHT_SMOKE:-0}" = "1" ]]; then
  run_step "Frontend Playwright smoke" "${STRICT_E2E:-0}" bash scripts/run_frontend_e2e.sh
else
  printf '%s\t%s\t%s\t%s\n' "Frontend Playwright smoke" "0" "0" "$LOG_DIR/frontend_playwright_smoke.log" >> "$STATUS_TSV"
  printf '%s\n' 'Skipped locally. Set RUN_PLAYWRIGHT_SMOKE=1 or STRICT_E2E=1 to execute browser smoke tests.' > "$LOG_DIR/frontend_playwright_smoke.log"
fi

if [[ "${ENABLE_ROS_RELEASE_GATE:-0}" = "1" ]]; then
  run_step "ROS colcon release gate" 1 bash scripts/validate_ros_workspace.sh
  run_step "ROS runtime validation" 1 bash scripts/run_ros2_humble_runtime_validation.sh
else
  printf '%s\t%s\t%s\t%s\n' "ROS colcon release gate" "0" "0" "$LOG_DIR/ros_colcon_release_gate.log" >> "$STATUS_TSV"
  printf '%s\n' 'Skipped locally. Set ENABLE_ROS_RELEASE_GATE=1 in a ROS 2 Humble environment with colcon installed to execute build/test release gates.' > "$LOG_DIR/ros_colcon_release_gate.log"
fi

python3 "$ROOT_DIR/scripts/write_verification_report.py" "$STATUS_TSV"
