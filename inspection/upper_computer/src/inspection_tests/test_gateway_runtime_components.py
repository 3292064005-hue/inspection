from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from inspection_hmi_gateway.runtime_components import GatewayArtifactResolver, GatewayReadModelProjector, RosServiceInvoker


class _Future:
    def __init__(self, result=None, *, done=True, exc: Exception | None = None):
        self._result = result
        self._done = done
        self._exc = exc
        self._callbacks = []

    def add_done_callback(self, callback):
        self._callbacks.append(callback)
        if self._done:
            callback(self)

    def result(self):
        if self._exc is not None:
            raise self._exc
        return self._result


class _Client:
    def __init__(self, *, available=True, future=None):
        self.available = available
        self.future = future or _Future(SimpleNamespace(success=True, message='ok'))

    def wait_for_service(self, timeout_sec: float):
        return self.available

    def call_async(self, request):
        self.request = request
        return self.future


class _Bus:
    def __init__(self):
        self.messages = []

    def broadcast(self, event: str, payload: dict):
        self.messages.append((event, payload))


class _State:
    def __init__(self):
        self.phase = 'BOOT'
        self.mode = 'IDLE'
        self.batch_id = 'BATCH-1'
        self.active_recipe_name = '配方'
        self.active_recipe_id = 'recipe-1'
        self.cycle_index = 0
        self.guidance = ''
        self.last_updated_at = ''
        self.absolute_stats = {'total': 0.0, 'ok': 0.0, 'ng': 0.0, 'recheck': 0.0, 'yieldRate': 0.0, 'avgCycleMs': 0.0}
        self.batch_baseline = {'total': 0.0, 'ok': 0.0, 'ng': 0.0, 'recheck': 0.0}
        self.continuous_run_count = 0
        self.latest_frame = {'url': '', 'capturedAt': '', 'annotated': False, 'semantic': 'LATEST_RESULT_FRAME', 'sourceEvent': 'inspection.result.created', 'description': ''}
        self.latest_fault = None
        self.diagnostics = []
        self.heartbeats = {}

    def snapshot_payload(self):
        return {'phase': self.phase, 'mode': self.mode, 'batchId': self.batch_id, 'activeRecipeName': self.active_recipe_name}

    def stats_payload(self):
        return {'total': 0, 'ok': 0, 'ng': 0, 'recheck': 0, 'yieldRate': 0.0, 'continuousRunCount': 0, 'avgCycleMs': 0.0}



def test_ros_service_invoker_returns_unavailable_and_timeout_messages():
    invoker = RosServiceInvoker(wait_service_timeout_sec=0.01, call_timeout_sec=0.01)
    unavailable = invoker.call(_Client(available=False), object(), service_name='/svc', unavailable_message='missing', timeout_message='timeout')
    assert unavailable.ok is False
    assert unavailable.message == 'missing'

    timeout = invoker.call(_Client(future=_Future(done=False)), object(), service_name='/svc', unavailable_message='missing', timeout_message='timeout')
    assert timeout.ok is False
    assert timeout.message == 'timeout'



def test_artifact_resolver_blocks_traversal_and_normalizes_paths(tmp_path: Path):
    logs_root = tmp_path / 'logs'
    logs_root.mkdir()
    resolver = GatewayArtifactResolver(logs_root)
    assert resolver.artifact_url('images/frame.png') == '/artifacts/images/frame.png'
    assert resolver.artifact_url('../outside.txt') == ''



def test_projector_joins_result_and_decision_and_emits_hmi_payload(tmp_path: Path):
    logs_root = tmp_path / 'logs'
    logs_root.mkdir()
    bus = _Bus()
    state = _State()
    projector = GatewayReadModelProjector(state=state, event_bus=bus, log_root=logs_root)

    result_msg = SimpleNamespace(
        detail_json='{"trace_id":"trace-1","processing_ms":18.2,"warnings":["偏色"]}',
        batch_id='BATCH-1',
        item_id=1,
        recipe_id='recipe-1',
        category='COLOR',
        defect_type='SHIFT',
        qr_text='QR001',
        score=0.82,
        image_path='images/raw.png',
        annotated_image_path='images/ann.png',
        stamp=SimpleNamespace(sec=0, nanosec=0),
    )
    projector.on_result(result_msg)
    projector.on_event('{"type":"decision_published","trace_id":"trace-1","decision":"NG","reason":"threshold"}')

    events = [event for event, _payload in bus.messages]
    assert 'inspection.result.created' in events
    merged = next(payload for event, payload in bus.messages if event == 'inspection.result.created')
    assert merged['decision'] == 'NG'
    assert 'threshold' in merged['explanation']
    assert merged['overlayUrl'] == '/artifacts/images/ann.png'
    camera_frame = next(payload for event, payload in bus.messages if event == 'camera.frame')
    assert camera_frame['semantic'] == 'LATEST_RESULT_FRAME'
    assert camera_frame['sourceEvent'] == 'inspection.result.created'



def test_projector_tolerates_non_numeric_processing_ms_and_cycle_index(tmp_path: Path):
    logs_root = tmp_path / 'logs'
    logs_root.mkdir()
    bus = _Bus()
    state = _State()
    projector = GatewayReadModelProjector(state=state, event_bus=bus, log_root=logs_root)

    result_msg = SimpleNamespace(
        detail_json='{"trace_id":"trace-bad","processing_ms":"oops"}',
        batch_id='BATCH-1',
        item_id=1,
        recipe_id='recipe-1',
        category='COLOR',
        defect_type='SHIFT',
        qr_text='QR001',
        score='not-a-number',
        image_path='images/raw.png',
        annotated_image_path='images/ann.png',
        stamp=SimpleNamespace(sec=0, nanosec=0),
    )
    projector.on_result(result_msg)
    projector.on_event('{"type":"decision_published","trace_id":"trace-bad","decision":"RECHECK"}')
    projector.on_event('{"type":"fsm_transition","cycle_index":"bad-index","time":"2026-01-01T00:00:00Z"}')

    merged = next(payload for event, payload in bus.messages if event == 'inspection.result.created')
    assert merged['metricValue'] == 0.0
    assert merged['cycleMs'] == 0.0
    assert merged['breakdown']['analyzeMs'] == 0.0
    assert state.cycle_index == 0


def test_projector_broadcasts_orchestrator_advice_for_hmi_consumers(tmp_path: Path):
    logs_root = tmp_path / 'logs'
    logs_root.mkdir()
    bus = _Bus()
    state = _State()
    projector = GatewayReadModelProjector(state=state, event_bus=bus, log_root=logs_root)

    projector.on_orchestrator_advice('{"type":"orchestrator_advice","tree":"recovery","status":"SUCCESS","durationMs":12,"actions":[{"action":"reset_fault","reason":"auto_recover"}],"time":"2026-04-08T00:00:00Z"}')

    advice = next(payload for event, payload in bus.messages if event == 'orchestrator.advice')
    assert advice['tree'] == 'recovery'
    assert advice['actions'][0]['action'] == 'reset_fault'
    assert state.latest_orchestrator_advice['status'] == 'SUCCESS'
