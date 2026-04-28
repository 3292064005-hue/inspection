from pathlib import Path


def test_architecture_document_covers_effective_and_compatibility_assets() -> None:
    root = Path(__file__).resolve().parents[2]
    architecture = root / 'docs' / 'ARCHITECTURE.md'
    assert architecture.exists()
    text = architecture.read_text(encoding='utf-8')
    assert '## 资产权威源与文档收敛' in text
    assert '### 主链有效资产' in text
    assert '### 兼容保留资产' in text
    assert '### 自动生成与验证资产' in text
    assert 'upper_computer/config/system/system.yaml' in text
    assert '.artifacts/verification/verification_manifest.json' in text
    assert 'upper_computer/src/inspection_bringup/launch/sim_stack.launch.py' in text


def test_upper_computer_readme_links_to_architecture_document() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'README.md').read_text(encoding='utf-8')
    assert 'upper_computer/docs/ARCHITECTURE.md' in text


def test_architecture_and_mock_gateway_align_on_finalized_result_event() -> None:
    root = Path(__file__).resolve().parents[2]
    architecture = (root / 'docs' / 'ARCHITECTURE.md').read_text(encoding='utf-8')
    mock_gateway = (root / 'frontend' / 'src' / 'mocks' / 'mockGateway.ts').read_text(encoding='utf-8')
    assert '第一方消费者与 mock 演示链已全部切换到 canonical 事件 `inspection.result.finalized`' in architecture
    assert "this.emit('inspection.result.finalized', result);" in mock_gateway
    assert "this.emit('inspection.result.created', result);" not in mock_gateway
