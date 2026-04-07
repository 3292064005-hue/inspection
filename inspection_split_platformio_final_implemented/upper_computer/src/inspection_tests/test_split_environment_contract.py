from pathlib import Path


def test_validate_split_environment_supports_modes_and_release_requirements() -> None:
    root = Path(__file__).resolve().parents[3]
    text = (root / 'scripts' / 'validate_split_environment.py').read_text(encoding='utf-8')
    assert "choices=('dev', 'ci', 'release')" in text
    assert "ubuntu == '22.04'" in text
    assert "node_major in {20, 22}" in text
    assert "args.mode == 'release'" in text
    assert "expect_ros = (args.expect_ros or ('humble' if args.mode == 'release' else '')).strip()" in text


def test_read_model_policy_defaults_disable_query_side_refresh() -> None:
    root = Path(__file__).resolve().parents[3]
    policy = (root / 'upper_computer' / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'read_model_policy.py').read_text(encoding='utf-8')
    config = (root / 'upper_computer' / 'config' / 'system' / 'read_model.yaml').read_text(encoding='utf-8')
    assert 'READ_MODEL_QUERY_REFRESH_DISABLED' in policy
    assert 'query_side_trace_refresh:' in config


def test_replay_api_uses_projection_page_queries() -> None:
    root = Path(__file__).resolve().parents[3]
    repository = (root / 'upper_computer' / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'read_model_repository.py').read_text(encoding='utf-8')
    service = (root / 'upper_computer' / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'replay_service.py').read_text(encoding='utf-8')
    router = (root / 'upper_computer' / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'replay.py').read_text(encoding='utf-8')
    assert 'def query_trace_page(' in repository
    assert 'batch_id: str = ' in service
    assert 'page_ok(' in router
    assert 'limit: int = Query' in router
    assert 'offset: int = Query' in router
