import asyncio

from inspection_hmi_gateway.ros_action_bridge import (
    ACTION_NAMES,
    RosActionBridge,
    native_action_availability,
    validate_action_payload,
)


class _GoalHandle:
    def __init__(self, request):
        self.request = request
        self.is_cancel_requested = False
        self.feedback = []
        self.final_state = ''

    def publish_feedback(self, feedback):
        self.feedback.append(feedback)

    def succeed(self):
        self.final_state = 'succeeded'

    def abort(self):
        self.final_state = 'aborted'

    def canceled(self):
        self.final_state = 'canceled'


class _Request:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class _ActionType:
    class Result:
        def __init__(self):
            self.accepted = False
            self.message = ''
            self.export_url = ''

    class Feedback:
        def __init__(self):
            self.phase = ''
            self.progress = 0.0
            self.detail_json = ''


class _Provider:
    def __init__(self, *, status_sequence=None):
        self.status_sequence = list(status_sequence or [{'status': 'COMPLETED', 'progress': 100, 'message': 'done', 'result': {}}])
        self.submit_calls = []
        self.cancel_calls = []
        self._job = None

    def submit(self, kind, payload, actor):
        self.submit_calls.append((kind, payload, actor))
        self._job = {'jobId': 'job-1', 'status': 'QUEUED', 'progress': 0, 'message': 'queued', 'result': {}}
        return self._job

    def get_job(self, _job_id):
        if self.status_sequence:
            self._job = {'jobId': 'job-1', **self.status_sequence.pop(0)}
        return self._job

    def cancel(self, job_id, actor):
        self.cancel_calls.append((job_id, actor))
        self._job = {'jobId': job_id, 'status': 'CANCELLED', 'progress': 100, 'message': 'cancelled', 'result': {}}
        return self._job



def test_action_name_registry_contains_expected_topics():
    assert ACTION_NAMES['start_batch'][1].endswith('/start_batch')
    assert ACTION_NAMES['export_batch'][0] == 'ExportBatch'



def test_native_action_availability_returns_shape():
    payload = native_action_availability()
    assert 'enabled' in payload
    assert 'actions' in payload



def test_validate_action_payload_rejects_missing_required_ids():
    assert validate_action_payload('start_batch', {'batchId': 'b-1'}) == 'recipeId is required'
    assert validate_action_payload('execute_replay', {'traceId': ''}) == 'traceId is required'
    assert validate_action_payload('export_batch', {'batchId': ''}) == 'batchId is required'
    assert validate_action_payload('switch_recipe_with_validation', {'recipeId': ''}) == 'recipeId is required'



def test_execute_callback_aborts_on_invalid_payload_without_submitting_job():
    bridge = RosActionBridge.__new__(RosActionBridge)
    bridge.provider = _Provider()
    bridge.poll_interval_sec = 0.01
    bridge.job_timeout_sec = 0.05

    goal_handle = _GoalHandle(_Request(batch_id='batch-1', recipe_id=''))
    execute = bridge._make_execute_callback('start_batch', _ActionType)
    result = asyncio.run(execute(goal_handle))

    assert goal_handle.final_state == 'aborted'
    assert result.accepted is False
    assert result.message == 'recipeId is required'
    assert bridge.provider.submit_calls == []



def test_execute_callback_cancels_job_on_timeout():
    bridge = RosActionBridge.__new__(RosActionBridge)
    bridge.provider = _Provider(status_sequence=[{'status': 'RUNNING', 'progress': 10, 'message': 'running', 'result': {}}] * 5)
    bridge.poll_interval_sec = 0.001
    bridge.job_timeout_sec = 0.002

    goal_handle = _GoalHandle(_Request(trace_id='trace-1'))
    execute = bridge._make_execute_callback('execute_replay', _ActionType)
    result = asyncio.run(execute(goal_handle))

    assert bridge.provider.submit_calls
    assert bridge.provider.cancel_calls and bridge.provider.cancel_calls[0][0] == 'job-1'
    assert goal_handle.final_state == 'aborted'
    assert result.accepted is False
    assert result.message == 'action_job_timeout'
    assert goal_handle.feedback


def test_bridge_can_disable_native_action_servers(monkeypatch):
    import sys
    import types
    import inspection_hmi_gateway.ros_action_bridge as module

    monkeypatch.setattr(module, 'native_action_availability', lambda: {'enabled': True, 'actions': [{'kind': 'start_batch', 'topic': '/inspection/actions/start_batch', 'type': 'StartBatch'}]})
    monkeypatch.setattr(module, '_load_action_type', lambda _name: _ActionType)

    fake_action_mod = types.ModuleType('rclpy.action')
    fake_action_mod.ActionServer = lambda *args, **kwargs: object()
    fake_action_mod.CancelResponse = types.SimpleNamespace(REJECT='reject', ACCEPT='accept')
    fake_action_mod.GoalResponse = types.SimpleNamespace(REJECT='reject', ACCEPT='accept')
    monkeypatch.setitem(sys.modules, 'rclpy.action', fake_action_mod)

    bridge = module.RosActionBridge(object(), enable_servers=False)
    assert bridge.enable_servers is False
    assert bridge.servers == []
    assert bridge.availability.get('serverMode') == 'disabled'
