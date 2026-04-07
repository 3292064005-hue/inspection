from pathlib import Path


def test_repository_asset_status_manifest_exists_and_covers_generated_and_compat_assets() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = root / 'docs' / 'REPOSITORY_ASSET_STATUS.md'
    assert manifest.exists()
    text = manifest.read_text(encoding='utf-8')
    assert '主链有效资产' in text
    assert '兼容保留资产' in text
    assert '自动生成 / 示例 / 只读说明资产' in text
    assert 'config/system/system.yaml' in text
    assert '.artifacts/verification/FINAL_VERIFICATION.md' in text
    assert 'full_stack.launch.py' in text


def test_readme_links_to_repository_asset_status_manifest() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'README.md').read_text(encoding='utf-8')
    assert 'docs/REPOSITORY_ASSET_STATUS.md' in text
