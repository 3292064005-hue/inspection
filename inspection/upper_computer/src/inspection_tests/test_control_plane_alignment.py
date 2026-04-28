from __future__ import annotations

from pathlib import Path

from inspection_hmi_gateway.server.operations.command_services import ActionCommandService
from inspection_fsm.control_dispatch import dispatch_control_command
from inspection_fsm.fsm_core import StationEvent
from inspection_utils.control_protocol import STOP_COMMAND, extract_control_command, normalize_control_command


class _FakeActionJobService:
    def __init__(self) -> None:
        self.submissions: list[dict] = []
        self.jobs: dict[str, dict] = {}

    def submit(self, kind: str, *, payload: dict, actor: dict) -> dict:
        job = {
            'jobId': f'{kind}-job-1',
            'kind': kind,
            'status': 'COMPLETED',
            'result': {'stopped': True, 'message': '已发布停止指令。'},
        }
        self.submissions.append({'kind': kind, 'payload': dict(payload), 'actor': dict(actor)})
        self.jobs[job['jobId']] = dict(job)
        return dict(job)

    def get_job(self, job_id: str) -> dict | None:
        return self.jobs.get(job_id)


class _FakeContext:
    def __init__(self) -> None:
        self.audit_entries: list[dict] = []
        self._action_job_service = _FakeActionJobService()

    def action_job_service(self) -> _FakeActionJobService:
        return self._action_job_service

    def audit(self, **payload) -> None:
        self.audit_entries.append(payload)


def test_station_stop_submits_canonical_action_job() -> None:
    context = _FakeContext()
    service = ActionCommandService(context)  # type: ignore[arg-type]

    response = service.submit('stop_station', {}, actor={'username': 'operator', 'role': 'operator'})

    assert response['kind'] == 'stop_station'
    assert context.action_job_service().submissions == [{'kind': 'stop_station', 'payload': {}, 'actor': {'username': 'operator', 'role': 'operator'}}]


def test_normalize_control_command_preserves_known_values_and_edge_inputs() -> None:
    assert normalize_control_command('STOP') == STOP_COMMAND
    assert normalize_control_command(' cancel_item ') == 'cancel'
    assert normalize_control_command(None) == ''
    assert normalize_control_command('  ') == ''
    assert normalize_control_command('custom-command') == 'custom-command'


def test_fsm_control_dispatch_centralizes_stop_and_cancel_semantics() -> None:
    stop_dispatch = dispatch_control_command('STOP')
    assert stop_dispatch is not None
    assert stop_dispatch.command == STOP_COMMAND
    assert stop_dispatch.event == StationEvent.PAUSE
    assert stop_dispatch.compatibility_mode is True

    cancel_dispatch = dispatch_control_command('cancel_item')
    assert cancel_dispatch is not None
    assert cancel_dispatch.command == 'cancel'
    assert cancel_dispatch.event == StationEvent.CANCEL


def test_extract_control_command_prefers_action_then_command() -> None:
    assert extract_control_command({'action': ' STOP '}) == STOP_COMMAND
    assert extract_control_command({'command': 'cancel_item'}) == 'cancel'
    assert extract_control_command({}) == ''


def test_fsm_runtime_uses_managed_runtime_and_canonical_node_name() -> None:
    root = Path(__file__).resolve().parents[2]
    node_text = (root / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_node.py').read_text(encoding='utf-8')
    ingress_text = (root / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_ingress.py').read_text(encoding='utf-8')
    assert 'class FSMNode(ManagedNodeMixin, InspectionRuntimeNode)' in node_text
    assert "setup_managed_runtime(node_name='inspection_fsm_node')" in node_text
    assert 'class FsmIngressAdapter' in ingress_text
    assert 'dispatch_control_command' in ingress_text


def test_orchestrator_runtime_uses_managed_runtime_and_active_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_orchestrator' / 'inspection_orchestrator' / 'orchestrator_node.py').read_text(encoding='utf-8')
    assert 'class OrchestratorNode(ManagedNodeMixin, InspectionRuntimeNode)' in text
    assert "setup_managed_runtime(node_name='inspection_orchestrator_node')" in text
    assert 'if not self.is_active() or not self.last_supervisor:' in text
    assert 'self.typed_state_sub = self.create_subscription(SupervisorStateEnvelope, SUPERVISOR_STATE_TOPIC_TYPED' in text
    assert 'self.typed_diagnostics_sub = self.create_subscription(DiagnosticsSnapshot, DIAGNOSTICS_TOPIC_TYPED' in text
    assert "self.typed_control_pub = self.create_publisher(ControlCommand, CONTROL_TOPIC_TYPED" in text


def test_supervisor_only_marks_lifecycle_dispatch_after_successful_queue() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_supervisor' / 'inspection_supervisor' / 'supervisor_node.py').read_text(encoding='utf-8')
    assert "if dispatch_result.get('queued', False):" in text
    assert "'dispatched': bool(dispatch_result.get('queued', False))" in text
