from pathlib import Path
from inspection_hmi_gateway.server.runtime_assets import parse_bool_env, resolve_gateway_paths

def test_parse_bool_env_rejects_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_REQUIRE_FRONTEND_DIST', 'definitely')
    try:
        parse_bool_env('INSPECTION_HMI_REQUIRE_FRONTEND_DIST', default=False)
    except ValueError as exc:
        assert 'INSPECTION_HMI_REQUIRE_FRONTEND_DIST' in str(exc)
    else:
        raise AssertionError('expected ValueError')

def test_resolve_gateway_paths_requires_frontend_bundle_when_enabled(tmp_path, monkeypatch) -> None:
    users_path = tmp_path / 'users.yaml'; users_path.write_text('users: []\n', encoding='utf-8'); monkeypatch.setenv('INSPECTION_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    try:
        resolve_gateway_paths(log_root='logs/runtime', recipe_root='config/recipes', frontend_dist=str(tmp_path / 'missing_dist'), users_path=str(users_path), require_frontend_dist=True)
    except FileNotFoundError as exc:
        assert 'Frontend dist is required' in str(exc)
    else:
        raise AssertionError('expected FileNotFoundError')

def test_source_delivery_launches_default_frontend_dist_to_optional() -> None:
    root = Path(__file__).resolve().parents[2]
    bringup = (root / 'src' / 'inspection_bringup' / 'launch' / 'sim_stack.launch.py').read_text(encoding='utf-8')
    gateway = (root / 'src' / 'inspection_hmi_gateway' / 'launch' / 'hmi_gateway.launch.py').read_text(encoding='utf-8')
    assert 'build_simulated_stack' in bringup
    assert 'INSPECTION_HMI_REQUIRE_FRONTEND_DIST' in gateway
    assert "DeclareLaunchArgument('require_frontend_dist', default_value='false')" in gateway


def test_bringup_launch_enforces_strict_user_config() -> None:
    root = Path(__file__).resolve().parents[2]
    helper = (root / 'src' / 'inspection_bringup' / 'inspection_bringup' / 'sim_stack_common.py').read_text(encoding='utf-8')
    assert 'INSPECTION_HMI_STRICT_USER_CONFIG' in helper


def test_release_launches_use_runtime_relative_user_and_recipe_roots() -> None:
    root = Path(__file__).resolve().parents[2]
    real_launch = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    gateway_launch = (root / 'src' / 'inspection_hmi_gateway' / 'launch' / 'hmi_gateway.launch.py').read_text(encoding='utf-8')
    assert "DeclareLaunchArgument('recipe_root', default_value='config/recipes')" in real_launch
    assert "DeclareLaunchArgument('users_path', default_value='config/system/hmi_users.yaml')" in real_launch
    assert "DeclareLaunchArgument('users_path', default_value='config/system/hmi_users.yaml')" in gateway_launch
