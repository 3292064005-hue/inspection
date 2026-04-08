from pathlib import Path


def test_runtime_docs_describe_experimental_action_gate_and_topic_destinations() -> None:
    root = Path(__file__).resolve().parents[2]
    upper_readme = (root / 'README.md').read_text(encoding='utf-8')
    top_readme = (root.parent / 'README.md').read_text(encoding='utf-8')
    compose = (root / 'docker-compose.yml').read_text(encoding='utf-8')

    for text in (upper_readme, top_readme, compose):
        assert 'INSPECTION_EXPERIMENTAL_ACTIONS_ENABLED' in text

    assert '/inspection/camera/status' in upper_readme
    assert '/inspection/result_raw' in upper_readme
    assert '/inspection/image_annotated' in upper_readme


def test_diagnostics_node_claims_consumption_of_camera_and_debug_topics() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_diagnostics' / 'inspection_diagnostics' / 'diagnostics_node.py').read_text(encoding='utf-8')
    assert "/inspection/camera/status" in text
    assert "/inspection/result_raw" in text
    assert "/inspection/image_annotated" in text
