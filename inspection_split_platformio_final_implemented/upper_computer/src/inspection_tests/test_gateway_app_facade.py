from __future__ import annotations

from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

if 'inspection_interfaces' not in sys.modules:
    inspection_interfaces = ModuleType('inspection_interfaces')
    srv_module = ModuleType('inspection_interfaces.srv')

    class _StartInspection:
        class Request:
            def __init__(self) -> None:
                self.recipe_id = ''
                self.batch_id = ''

    class _ResetFault:
        class Request:
            def __init__(self) -> None:
                self.operator_name = ''
                self.comment = ''

    srv_module.StartInspection = _StartInspection
    srv_module.ResetFault = _ResetFault
    inspection_interfaces.srv = srv_module
    sys.modules['inspection_interfaces'] = inspection_interfaces
    sys.modules['inspection_interfaces.srv'] = srv_module

from inspection_hmi_gateway.app_facade import GatewayAppFacade
from inspection_hmi_gateway.runtime_components import ServiceCallResult


class _EventBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def broadcast(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))


class _RosBridge:
    def __init__(self, start_result: ServiceCallResult | None = None, reset_result: ServiceCallResult | None = None) -> None:
        self.start_result = start_result or ServiceCallResult(True, 'ok')
        self.reset_result = reset_result or ServiceCallResult(True, 'reset-ok')
        self.start_calls = []
        self.reset_calls = []
        self.controls = []

    def call_start(self, request, *, unavailable_message: str, timeout_message: str):
        self.start_calls.append({'recipe_id': request.recipe_id, 'batch_id': request.batch_id, 'unavailable_message': unavailable_message, 'timeout_message': timeout_message})
        return self.start_result

    def call_reset_fault(self, request, *, unavailable_message: str, timeout_message: str):
        self.reset_calls.append({'operator_name': request.operator_name, 'comment': request.comment, 'unavailable_message': unavailable_message, 'timeout_message': timeout_message})
        return self.reset_result

    def publish_control(self, action: str) -> None:
        self.controls.append(action)

    def publish_capture_request(self, payload: dict) -> bool:
        return True


def _save_recipe(app: GatewayAppFacade, recipe_id: str, *, version: str = '1.0.0') -> None:
    app.save_recipe({
        'id': recipe_id,
        'name': recipe_id,
        'version': version,
        'updatedBy': 'tester',
        'targetPart': 'part',
        'changeNote': 'note',
        'roi': [1, 2, 3, 4],
        'qrRoi': [5, 6, 7, 8],
        'sortRules': [{'condition': 'decision == OK', 'action': 'BOX_OK'}],
    })


def _build_app(tmp_path: Path) -> GatewayAppFacade:
    bus = _EventBus()
    app = GatewayAppFacade(event_bus=bus, log_root=tmp_path / 'logs', recipe_root=tmp_path / 'recipes')
    _save_recipe(app, 'recipe-a', version='1.2.3')
    _save_recipe(app, 'recipe-b', version='2.0.0')
    return app


def test_call_start_blocks_when_active_recipe_and_activation_receipt_diverge(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    app.activate_recipe('recipe-a', operator='tester')
    app.refresh_recipes()
    app.state.active_recipe_id = 'recipe-b'
    bridge = _RosBridge()
    app.bind_ros_bridge(bridge)

    ok, message = app.call_start()

    assert ok is False
    assert '启动前配方校验失败' in message
    assert bridge.start_calls == []
    assert app.recipe_store.current_activation()['activationState'] == 'START_BLOCKED'
    assert app.state.recipe_activation_state == 'START_BLOCKED'


def test_call_start_updates_guidance_on_timeout_without_advancing_activation(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    receipt = app.activate_recipe('recipe-a', operator='tester')
    app.refresh_recipes()
    bridge = _RosBridge(start_result=ServiceCallResult(False, '启动请求超时。'))
    app.bind_ros_bridge(bridge)

    ok, message = app.call_start()

    assert ok is False
    assert message == '启动请求超时。'
    assert len(bridge.start_calls) == 1
    assert app.state.guidance == '启动请求超时。'
    assert app.recipe_store.current_activation()['activationState'] == receipt['activationState']


def test_call_start_marks_start_requested_and_runtime_result_acknowledges_recipe(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    app.activate_recipe('recipe-a', operator='tester')
    app.refresh_recipes()
    app.state.pending_batch_id = 'BATCH-42'
    bridge = _RosBridge(start_result=ServiceCallResult(True, 'started'))
    app.bind_ros_bridge(bridge)

    ok, _message = app.call_start()

    assert ok is True
    assert app.recipe_store.current_activation()['activationState'] == 'START_REQUESTED'
    result_msg = SimpleNamespace(
        detail_json='{"trace_id":"TRACE-1","processing_ms":12.3,"recipe_version":"1.2.3"}',
        batch_id='BATCH-42',
        item_id=1,
        recipe_id='recipe-a',
        category='COLOR',
        defect_type='NONE',
        qr_text='QR',
        score=0.98,
        image_path='images/raw.png',
        annotated_image_path='images/ann.png',
        stamp=SimpleNamespace(sec=0, nanosec=0),
    )
    app.projector.on_result(result_msg)

    activation = app.recipe_store.current_activation()
    assert activation['activationState'] == 'RUNTIME_ACKNOWLEDGED'
    assert activation['runtimeAcknowledged'] is True
    assert activation['runtimeObservedBatchId'] == 'BATCH-42'
    assert app.state.recipe_activation_state == 'RUNTIME_ACKNOWLEDGED'
    assert app.state.guidance == '运行链已确认当前激活配方。'


def test_reset_fault_falls_back_to_control_topic_when_service_missing(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    bridge = _RosBridge(reset_result=ServiceCallResult(False, '未找到 /inspection/reset_fault 服务。'))
    app.bind_ros_bridge(bridge)

    ok, message = app.reset_fault()

    assert ok is True
    assert message == '已退回控制话题复位。'
    assert bridge.controls == ['reset']
    assert app.state.guidance == '复位服务不可用，已退回控制话题复位。'
