from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
UPPER_ROOT = REPO_ROOT / 'upper_computer'

FORMAL_DOCS = [
    REPO_ROOT / 'README.md',
    REPO_ROOT / 'docs' / 'SPLIT_DEPLOYMENT.md',
    REPO_ROOT / 'docs' / 'STM32_SERIAL_PROTOCOL.md',
    REPO_ROOT / 'docs' / 'ESP32S3_CAMERA_API.md',
    UPPER_ROOT / 'README.md',
    UPPER_ROOT / 'docs' / 'ARCHITECTURE.md',
    UPPER_ROOT / 'frontend' / 'README.md',
    REPO_ROOT / 'firmware' / 'stm32_station_platformio' / 'README.md',
    REPO_ROOT / 'firmware' / 'esp32s3_camera_platformio' / 'README.md',
]


def _lines_to_check(path: Path) -> list[str]:
    lines = path.read_text(encoding='utf-8').splitlines()
    filtered: list[str] = []
    for line in lines:
        if '不再在正式说明中混用工作区相对路径' in line:
            continue
        if '文档中的文件引用统一使用**仓库根相对路径**' in line:
            continue
        filtered.append(line)
    return filtered


def test_documentation_path_rule_is_explicit_in_top_readme() -> None:
    text = FORMAL_DOCS[0].read_text(encoding='utf-8')
    assert '## 文档路径规范' in text
    assert '仓库根相对路径' in text
    assert '不再在正式说明中混用工作区相对路径' in text


def test_formal_docs_use_repo_root_relative_paths_for_cross_workspace_file_references() -> None:
    banned_fragments = [
        '`docs/ARCHITECTURE.md`',
        '`frontend/README.md`',
        '`frontend/openapi/inspection_gateway_openapi.json`',
        '`frontend/src/shared/gateway/generated/actionApi.ts`',
        '`config/system/action_governance.yaml`',
        '`config/system/transport_bridge_policy.yaml`',
        '`config/system/compatibility_routes.yaml`',
        '`config/system/station_protocol_contract.yaml`',
        '`config/station/station_stm32.yaml`',
        '`config/camera/camera_esp32s3.yaml`',
        '`config/camera/camera.yaml`',
        '`config/station/station.yaml`',
        '`config/recipes/*.yaml`',
        '`config/profiles/*.yaml`',
        '`src/inspection_bringup/launch/*.launch.py`',
        '`src/inspection_bringup/launch/sim_stack.launch.py`',
        '`src/shared/gateway/httpGateway.ts`',
        '`src/shared/gateway/generated/actionApi.ts`',
    ]
    for path in FORMAL_DOCS:
        for line in _lines_to_check(path):
            for fragment in banned_fragments:
                assert fragment not in line, f"{path} still contains workspace-relative reference: {fragment}"


def test_configuration_document_refs_use_repo_root_relative_paths() -> None:
    files = [
        UPPER_ROOT / 'config' / 'system' / 'action_governance.yaml',
        UPPER_ROOT / 'config' / 'system' / 'transport_bridge_policy.yaml',
    ]
    for path in files:
        text = path.read_text(encoding='utf-8')
        assert 'upper_computer/docs/ARCHITECTURE.md' in text
        assert 'migration_guide: docs/ARCHITECTURE.md' not in text
        assert '- docs/ARCHITECTURE.md' not in text
