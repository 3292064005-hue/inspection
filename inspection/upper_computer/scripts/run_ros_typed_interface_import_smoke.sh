#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source /opt/ros/humble/setup.bash
source install/setup.bash
python3 - <<'PY'
from inspection_interfaces.msg import (
    ActionExecutorEvent,
    CaptureRequest,
    ControlCommand,
    DiagnosticsSnapshot,
    SupervisorStateEnvelope,
)
assert ActionExecutorEvent and CaptureRequest and ControlCommand and DiagnosticsSnapshot and SupervisorStateEnvelope
print('typed interface import smoke: ok')
PY
