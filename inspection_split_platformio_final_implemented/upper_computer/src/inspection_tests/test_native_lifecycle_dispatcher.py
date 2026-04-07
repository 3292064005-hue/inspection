from inspection_supervisor.lifecycle_clients import LifecycleCommand
from inspection_supervisor.native_lifecycle_dispatcher import NativeLifecycleDispatcher


class FakeNode:
    def create_client(self, *_args, **_kwargs):
        raise AssertionError('create_client should not be called when disabled')


def test_dispatcher_falls_back_when_lifecycle_msgs_unavailable():
    dispatcher = NativeLifecycleDispatcher(FakeNode())
    dispatcher.enabled = False
    calls = []
    result = dispatcher.dispatch(
        LifecycleCommand(node='camera_node', transition='ACTIVATE', target_state='ACTIVE'),
        fallback=lambda payload: calls.append(payload),
    )
    assert result['mode'] == 'topic_fallback'
    assert calls and calls[0]['node'] == 'camera_node'


def test_dispatcher_rejects_empty_node_without_fallback():
    dispatcher = NativeLifecycleDispatcher(FakeNode())
    dispatcher.enabled = False
    calls = []
    result = dispatcher.dispatch(
        LifecycleCommand(node='', transition='ACTIVATE', target_state='ACTIVE'),
        fallback=lambda payload: calls.append(payload),
    )
    assert result['mode'] == 'rejected'
    assert result['reason'] == 'node_required'
    assert calls == []


def test_dispatcher_falls_back_for_unknown_transition_without_client_call():
    dispatcher = NativeLifecycleDispatcher(FakeNode())
    dispatcher.enabled = True
    dispatcher._change_state_type = object()
    dispatcher._transition_type = object()
    calls = []
    result = dispatcher.dispatch(
        LifecycleCommand(node='camera_node', transition='PAUSE', target_state='UNKNOWN'),
        fallback=lambda payload: calls.append(payload),
    )
    assert result['mode'] == 'topic_fallback'
    assert result['reason'] == 'unsupported_transition'
    assert calls and calls[0]['transition'] == 'PAUSE'


def test_dispatcher_rejects_standard_nodes_instead_of_topic_fallback():
    dispatcher = NativeLifecycleDispatcher(FakeNode())
    dispatcher.enabled = False
    calls = []
    result = dispatcher.dispatch(
        LifecycleCommand(node='inspection_hmi_node', transition='ACTIVATE', target_state='ACTIVE'),
        fallback=lambda payload: calls.append(payload),
    )
    assert result['mode'] == 'rejected'
    assert result['reason'] == 'native_lifecycle_unavailable'
    assert calls == []
