from inspection_utils.protocol import Frame
from station_bridge.rx_parser import RXParser


def test_rx_parser_filters_duplicates():
    parser = RXParser(duplicate_window_sec=5.0)
    frame = Frame(cmd=0x80, seq=1, payload=b'{}').to_bytes()
    first = parser.feed(frame)
    second = parser.feed(frame)
    assert len(first) == 1
    assert second == []
