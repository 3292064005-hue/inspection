from __future__ import annotations

from pathlib import Path

import pytest

launch = pytest.importorskip('launch')
if not hasattr(launch, 'LaunchContext'):
    pytest.skip('real ROS launch package unavailable', allow_module_level=True)
from launch import LaunchContext
from launch.launch_description_sources import PythonLaunchDescriptionSource


def _resolve_description(path: Path):
    source = PythonLaunchDescriptionSource(str(path))
    return source.get_launch_description(LaunchContext())


def test_bringup_entrypoints_resolve_into_launch_descriptions() -> None:
    root = Path(__file__).resolve().parents[2]
    launch_dir = root / 'src' / 'inspection_bringup' / 'launch'
    for filename in ['real_station.launch.py', 'sim_stack.launch.py', 'offline_replay.launch.py']:
        description = _resolve_description(launch_dir / filename)
        assert description is not None
        assert getattr(description, 'entities', None)
