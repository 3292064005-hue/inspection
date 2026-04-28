from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from generate_mock_action_catalog import render  # noqa: E402


def test_mock_action_catalog_is_generated_from_public_action_registry() -> None:
    target = ROOT / 'frontend' / 'src' / 'mocks' / 'generated' / 'actionCatalog.ts'
    generated = render()
    current = target.read_text(encoding='utf-8')
    assert current == generated
    assert 'diagnostic_capture_frame' in current
    assert 'run_benchmark' not in current
    assert 'qa_tooling' not in current
