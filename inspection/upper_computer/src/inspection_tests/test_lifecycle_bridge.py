from inspection_utils.lifecycle_bridge import lifecycle_state_payload, lifecycle_transition_name


def test_lifecycle_transition_name_maps_known_ids_and_labels():
    assert lifecycle_transition_name(transition_id=1) == 'CONFIGURE'
    assert lifecycle_transition_name(label='activate') == 'ACTIVATE'
    assert lifecycle_transition_name(label='transition_deactivate') == 'DEACTIVATE'
    assert lifecycle_transition_name(label='inactive_shutdown') == 'SHUTDOWN'


def test_lifecycle_state_payload_maps_active():
    state_id, label = lifecycle_state_payload('ACTIVE')
    assert state_id == 3
    assert label == 'active'


class _Response:
    def __init__(self):
        self.success = True


class _Request:
    class _Transition:
        def __init__(self, *, id: int | None = None, label: str = ''):
            self.id = id
            self.label = label

    def __init__(self, *, id: int | None = None, label: str = ''):
        self.transition = self._Transition(id=id, label=label)


def test_change_state_handler_returns_false_when_transition_handler_raises():
    from inspection_utils.lifecycle_bridge import LifecycleCompatibilityBridge

    bridge = LifecycleCompatibilityBridge.__new__(LifecycleCompatibilityBridge)
    bridge.transition_handler = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('boom'))

    response = _Response()
    updated = bridge._handle_change_state(_Request(label='activate'), response)
    assert updated.success is False
