from __future__ import annotations

import json
from types import SimpleNamespace

from inspection_hmi_gateway.native_action_client import NativeActionClientAdapter, native_action_client_availability


class _Future:
    def __init__(self, result):
        self._result = result

    def add_done_callback(self, callback):
        callback(self)

    def result(self):
        return self._result


class _GoalHandle:
    accepted = True

    def __init__(self, result_payload: dict[str, object] | None = None):
        self.cancelled = False
        self._result_payload = dict(result_payload or {})

    def get_result_async(self):
        result = SimpleNamespace(
            accepted=True,
            message='done',
            export_url='/artifacts/export.zip',
            result_json=json.dumps(self._result_payload, ensure_ascii=False),
        )
        return _Future(SimpleNamespace(status=4, result=result))

    def cancel_goal_async(self):
        self.cancelled = True
        return _Future(SimpleNamespace())


class _ActionClient:
    def __init__(self, _node, _action_type, _topic):
        self.goal = None

    def wait_for_server(self, timeout_sec: float):
        return True

    def send_goal_async(self, goal, feedback_callback=None):
        self.goal = goal
        if feedback_callback is not None:
            feedback_callback(SimpleNamespace(feedback=SimpleNamespace(phase='RUNNING', progress=0.5, detail_json='{"step":"mid"}')))
        return _Future(_GoalHandle({'started': True, 'batchId': 'B-1'}))


class _ActionType:
    class Goal:
        def __init__(self):
            self.batch_id = ''
            self.recipe_id = ''
            self.requested_by = ''


def test_native_action_client_availability_shape():
    payload = native_action_client_availability()
    assert 'enabled' in payload
    assert 'actions' in payload


def test_native_action_client_submits_feedback_and_result(monkeypatch):
    import inspection_hmi_gateway.native_action_client as module

    monkeypatch.setattr(module, 'native_action_client_availability', lambda: {'enabled': True, 'reason': '', 'actions': [{'kind': 'start_batch', 'topic': '/inspection/actions/start_batch', 'type': 'StartBatch'}]})
    monkeypatch.setattr(module, '_load_action_type', lambda _name: _ActionType)
    adapter = module.NativeActionClientAdapter.__new__(module.NativeActionClientAdapter)
    module.NativeActionClientAdapter.__init__(adapter, object())
    adapter._action_client_type = _ActionClient
    updates = []

    ok = adapter.submit({'jobId': 'job-1', 'kind': 'start_batch', 'payload': {'batchId': 'B-1', 'recipeId': 'R-1'}}, actor={'username': 'op'}, update=lambda job_id, **fields: updates.append((job_id, fields)))

    assert ok is True
    assert any(fields.get('status') == 'RUNNING' for _job_id, fields in updates)
    completed = next(fields for _job_id, fields in updates if fields.get('status') == 'COMPLETED')
    assert completed['result']['started'] is True
    assert completed['result']['batchId'] == 'B-1'
    assert adapter.snapshot()['metrics']['submitted'] == 1


def test_native_action_client_result_callback_preserves_business_payload():
    import inspection_hmi_gateway.native_action_client as module

    adapter = module.NativeActionClientAdapter.__new__(module.NativeActionClientAdapter)
    adapter.metrics = module.NativeActionClientMetrics()
    captured: list[dict[str, object]] = []
    adapter._updates = {'job-3': lambda _job_id, **fields: captured.append(fields)}
    adapter._goal_handles = {'job-3': object()}
    payload = {'batchId': 'B-9', 'success': True, 'snapshot': {'enabled': True}}
    wrapper = SimpleNamespace(
        status=4,
        result=SimpleNamespace(
            accepted=True,
            message='done',
            export_url='',
            result_json=json.dumps(payload, ensure_ascii=False),
        ),
    )

    adapter._on_result('job-3', _Future(wrapper))

    assert captured
    terminal = captured[-1]
    assert terminal['status'] == 'COMPLETED'
    assert terminal['result']['batchId'] == 'B-9'
    assert terminal['result']['success'] is True
    assert terminal['result']['snapshot'] == {'enabled': True}
    assert terminal['result']['accepted'] is True


def test_native_action_client_cancel(monkeypatch):
    import inspection_hmi_gateway.native_action_client as module

    monkeypatch.setattr(module, 'native_action_client_availability', lambda: {'enabled': True, 'reason': '', 'actions': [{'kind': 'start_batch', 'topic': '/inspection/actions/start_batch', 'type': 'StartBatch'}]})
    monkeypatch.setattr(module, '_load_action_type', lambda _name: _ActionType)
    adapter = module.NativeActionClientAdapter.__new__(module.NativeActionClientAdapter)
    module.NativeActionClientAdapter.__init__(adapter, object())
    adapter._goal_handles['job-2'] = _GoalHandle()
    adapter._updates['job-2'] = lambda *_args, **_kwargs: None

    assert adapter.cancel('job-2', {'username': 'op'}) is True
    assert adapter.snapshot()['metrics']['cancelled'] == 1
