from inspection_utils.protocol import Frame, FrameStreamParser, build_frame, parse_frame


def test_protocol_roundtrip():
    frame = build_frame(0x10, 2, b'ABC')
    cmd, seq, payload = parse_frame(frame)
    assert cmd == 0x10
    assert seq == 2
    assert payload == b'ABC'


def test_stream_parser_handles_chunking():
    frame = Frame(cmd=0x20, seq=3, payload=b'XYZ').to_bytes()
    parser = FrameStreamParser()
    out = []
    out.extend(parser.feed(frame[:2]))
    out.extend(parser.feed(frame[2:5]))
    out.extend(parser.feed(frame[5:]))
    assert len(out) == 1
    assert out[0].cmd == 0x20
    assert out[0].payload == b'XYZ'
