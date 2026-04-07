from __future__ import annotations

from inspection_supervisor.native_lifecycle_probe import NativeLifecycleProbe


class _Future:
    def __init__(self, result):
        self._result = result
    def done(self):
        return True
    def result(self):
        return self._result


class _StateResult:
    class _State:
        label = 'active'
    current_state = _State()


class _TransitionsResult:
    class _Transition:
        def __init__(self, label):
            self.label = label
    available_transitions = [_Transition('deactivate'), _Transition('shutdown')]


class _Client:
    def __init__(self, result):
        self._result = result
        class _SrvType:
            class Request:
                pass
        self.srv_type = _SrvType
    def wait_for_service(self, timeout_sec):
        return True
    def call_async(self, _request):
        return _Future(self._result)


class _Node:
    def create_client(self, srv_type, service_name):
        if service_name.endswith('/get_state'):
            return _Client(_StateResult())
        return _Client(_TransitionsResult())


def test_native_lifecycle_probe_reads_state_and_transitions():
    probe = NativeLifecycleProbe(_Node())
    if not probe.enabled:
        return
    assert probe.get_state('camera_node') == 'ACTIVE'
    assert probe.get_available_transitions('camera_node') == ['DEACTIVATE', 'SHUTDOWN']
    assert probe.wait_for_state('camera_node', 'ACTIVE', timeout_sec=0.01) is True
