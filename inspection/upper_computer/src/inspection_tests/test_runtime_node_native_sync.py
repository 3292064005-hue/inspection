from inspection_utils.lifecycle import ManagedNodeRuntime
from inspection_utils.runtime_node import InspectionRuntimeNode


class _Node(InspectionRuntimeNode):
    def __init__(self):
        self.lifecycle_runtime = ManagedNodeRuntime(node_name='test_node')
        self._native_transition_reason = 'native-test'

    def on_configure(self):
        return True, 'configured'

    def on_activate(self):
        return True, 'active'


def test_runtime_node_syncs_native_callbacks_into_managed_runtime():
    node = _Node()
    node.on_configure()
    assert node.lifecycle_runtime.state == 'INACTIVE'
    node.on_activate()
    assert node.lifecycle_runtime.state == 'ACTIVE'
