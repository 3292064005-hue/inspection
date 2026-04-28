from __future__ import annotations

from pathlib import Path

from inspection_logger.defaults import DEFAULT_BAG_TOPICS
from inspection_utils.topic_contracts import DECISION_OUTPUT_TOPIC, SORT_REQUEST_TOPIC, SORT_REQUEST_LEGACY_TOPIC


def test_decision_and_sort_request_topics_are_split_across_runtime_components() -> None:
    root = Path(__file__).resolve().parents[2]
    topic_contract_text = (root / 'src' / 'inspection_utils' / 'inspection_utils' / 'topic_contracts.py').read_text(encoding='utf-8')
    decision_text = (root / 'src' / 'inspection_decision' / 'inspection_decision' / 'decision_node.py').read_text(encoding='utf-8')
    fsm_text = (root / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_node.py').read_text(encoding='utf-8')
    bridge_text = (root / 'src' / 'station_bridge' / 'station_bridge' / 'station_bridge_node.py').read_text(encoding='utf-8')

    assert DECISION_OUTPUT_TOPIC in topic_contract_text
    assert SORT_REQUEST_TOPIC in topic_contract_text
    assert SORT_REQUEST_LEGACY_TOPIC in topic_contract_text
    assert 'DECISION_OUTPUT_TOPIC' in decision_text
    assert 'DECISION_OUTPUT_TOPIC' in fsm_text
    assert 'SORT_REQUEST_TOPIC' in fsm_text
    assert 'SORT_REQUEST_TOPIC' in bridge_text
    assert DECISION_OUTPUT_TOPIC in DEFAULT_BAG_TOPICS
    assert SORT_REQUEST_TOPIC in DEFAULT_BAG_TOPICS
