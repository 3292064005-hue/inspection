from inspection_utils.lifecycle import ManagedNodeRuntime


def test_managed_runtime_transitions_and_history():
    runtime = ManagedNodeRuntime(node_name='camera_node')
    record = runtime.transition('CONFIGURE', reason='startup', hook=lambda _t: (True, 'configured'))
    assert record.success is True
    assert runtime.state == 'INACTIVE'
    record = runtime.transition('ACTIVATE', reason='startup')
    assert record.success is True
    assert runtime.state == 'ACTIVE'
    snapshot = runtime.snapshot()
    assert snapshot['lifecycle_state'] == 'ACTIVE'
    assert snapshot['history'][-1]['transition'] == 'ACTIVATE'


def test_managed_runtime_invalid_transition_goes_to_error():
    runtime = ManagedNodeRuntime(node_name='camera_node')
    record = runtime.transition('ACTIVATE', reason='invalid')
    assert record.success is False
    assert runtime.state == 'UNCONFIGURED'
    assert 'invalid transition' in runtime.last_message
