from pathlib import Path


def test_gateway_split_modules_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    gateway = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway'
    assert (gateway / 'app_components.py').exists()
    assert (gateway / 'runtime_projection.py').exists()
    assert (gateway / 'read_model_trace_queries.py').exists()
    assert (gateway / 'read_model_replay_queries.py').exists()
    assert (gateway / 'server' / 'metadata_database.py').exists()
    assert (gateway / 'server' / 'metadata_table_access.py').exists()


def test_config_split_modules_exist_and_facade_exports_runtime_bundle_builder() -> None:
    root = Path(__file__).resolve().parents[2]
    utils = root / 'src' / 'inspection_utils' / 'inspection_utils'
    assert (utils / 'config_errors.py').exists()
    assert (utils / 'resource_loader.py').exists()
    assert (utils / 'profile_resolver.py').exists()
    assert (utils / 'recipe_validator.py').exists()
    assert (utils / 'compatibility_validator.py').exists()
    assert (utils / 'runtime_bundle_builder.py').exists()
    config_text = (utils / 'config.py').read_text(encoding='utf-8')
    assert 'build_effective_runtime_bundle' in config_text
