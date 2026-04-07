from __future__ import annotations

from vision_processing.processor_runtime import ProcessorArtifactRuntime


class _Writer:
    def close(self, *, timeout_sec: float) -> None:
        raise RuntimeError('flush timeout')


class _NodeStub:
    def __init__(self) -> None:
        self.artifact_writer = _Writer()
        self.artifact_writer_flush_timeout_sec = 0.1
        self.artifact_backpressure_threshold = 0.8
        self.events = []

    def _emit_event(self, name: str, **payload) -> None:
        self.events.append((name, payload))


def test_close_artifact_writer_converts_cleanup_failure_to_event() -> None:
    node = _NodeStub()
    runtime = ProcessorArtifactRuntime(node)

    ok, error = runtime.close_artifact_writer()

    assert ok is False
    assert 'flush timeout' in error
    assert node.artifact_writer is None
    assert node.events[-1][0] == 'artifact_writer_close_failed'
