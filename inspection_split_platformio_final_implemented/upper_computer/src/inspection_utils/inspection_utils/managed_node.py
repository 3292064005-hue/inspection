from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from std_msgs.msg import String

from .lifecycle import ManagedNodeRuntime
from .lifecycle_bridge import LifecycleCompatibilityBridge
from .logging_tools import event_to_json, safe_json_loads
from .param_parsing import parameter_as_bool
from .qos import qos_profile
from .runtime_node import runtime_node_capabilities


class ManagedNodeMixin:
    lifecycle_node_name: str
    lifecycle_runtime: ManagedNodeRuntime
    lifecycle_event_pub: Any
    lifecycle_command_sub: Any
    lifecycle_bridge: Any

    def setup_managed_runtime(self, *, node_name: str, enable_param: str = 'managed_runtime_enabled', autostart_param: str = 'managed_runtime_autostart') -> None:
        self.declare_parameter(enable_param, True)
        self.declare_parameter(autostart_param, True)
        self.lifecycle_node_name = node_name
        self.lifecycle_runtime = ManagedNodeRuntime(node_name=node_name)
        self.lifecycle_event_pub = self.create_publisher(String, '/inspection/events', qos_profile('event'))
        self.lifecycle_command_sub = self.create_subscription(String, '/inspection/lifecycle/command', self._on_lifecycle_command, qos_profile('control'))
        self.lifecycle_bridge = LifecycleCompatibilityBridge(
            node=self,
            node_name=node_name,
            transition_handler=self.transition_lifecycle,
            snapshot_handler=self.lifecycle_runtime.snapshot,
        )
        if parameter_as_bool(self, enable_param, default=True) and parameter_as_bool(self, autostart_param, default=True):
            self.transition_lifecycle('CONFIGURE', reason='autostart')
            self.transition_lifecycle('ACTIVATE', reason='autostart')
        else:
            self._publish_lifecycle_state('managed_runtime_idle', reason='manual_start_required')

    @property
    def lifecycle_state(self) -> str:
        return self.lifecycle_runtime.state

    def is_active(self) -> bool:
        return self.lifecycle_state == 'ACTIVE'

    def _native_trigger(self, transition: str, *, reason: str) -> dict[str, object] | None:
        method_name = {
            'CONFIGURE': 'trigger_configure',
            'ACTIVATE': 'trigger_activate',
            'DEACTIVATE': 'trigger_deactivate',
            'CLEANUP': 'trigger_cleanup',
            'SHUTDOWN': 'trigger_shutdown',
        }.get(transition, '')
        method = getattr(self, method_name, None)
        if not callable(method):
            return None
        self._native_transition_reason = str(reason or '')
        before = len(getattr(self.lifecycle_runtime, 'transition_history', []))
        try:
            result = method()
        except Exception as exc:
            return self.lifecycle_runtime.transition(transition, reason=reason, hook=lambda _transition: (False, str(exc))).to_dict()
        finally:
            self._native_transition_reason = ''
        if len(getattr(self.lifecycle_runtime, 'transition_history', [])) > before:
            latest = self.lifecycle_runtime.transition_history[-1]
            return latest.to_dict()
        success = False if result is False else True
        return self.lifecycle_runtime.transition(transition, reason=reason, hook=lambda _transition: (success, '')).to_dict()

    def transition_lifecycle(self, transition: str, *, reason: str = '') -> dict[str, object]:
        native_record = self._native_trigger(transition, reason=reason)
        if native_record is not None:
            self._publish_lifecycle_state(
                'lifecycle_transition',
                reason=reason,
                transition=transition,
                success=bool(native_record.get('success', True)),
                message=str(native_record.get('message', '')),
            )
            return native_record
        self._managed_transition_hook_active = True
        try:
            record = self.lifecycle_runtime.transition(transition, reason=reason, hook=self._dispatch_transition_hook)
        finally:
            self._managed_transition_hook_active = False
        self._publish_lifecycle_state('lifecycle_transition', reason=reason, transition=transition, success=record.success, message=record.message)
        return record.to_dict()

    def _dispatch_transition_hook(self, transition: str) -> tuple[bool, str] | bool | None:
        method_name = {
            'CONFIGURE': 'on_configure',
            'ACTIVATE': 'on_activate',
            'DEACTIVATE': 'on_deactivate',
            'CLEANUP': 'on_cleanup',
            'SHUTDOWN': 'on_shutdown',
        }.get(transition, '')
        method = getattr(self, method_name, None)
        if method is None:
            return True, ''
        return method()

    def _matches_lifecycle_target(self, payload: dict[str, Any]) -> bool:
        target = str(payload.get('node', '')).strip()
        return not target or target == self.lifecycle_node_name

    def _on_lifecycle_command(self, msg: String) -> None:
        payload = safe_json_loads(msg.data)
        if not self._matches_lifecycle_target(payload):
            return
        transition = str(payload.get('transition', payload.get('command', ''))).upper()
        if transition == 'LIFECYCLE_TRANSITION':
            transition = str(payload.get('transition', '')).upper()
        if transition not in {'CONFIGURE', 'ACTIVATE', 'DEACTIVATE', 'CLEANUP', 'SHUTDOWN'}:
            return
        self.transition_lifecycle(transition, reason=str(payload.get('reason', 'external_command')))

    def _publish_lifecycle_state(self, event_type: str, **fields: Any) -> None:
        if getattr(self, 'lifecycle_event_pub', None) is None:
            return
        msg = String()
        availability = getattr(getattr(self, 'lifecycle_bridge', None), 'availability', None)
        bridge_payload = asdict(availability) if availability is not None and is_dataclass(availability) else {'enabled': False, 'reason': 'not_initialized', 'services': ()}
        payload = {
            'node': self.lifecycle_node_name,
            'lifecycle_state': self.lifecycle_state,
            'lifecycle_bridge': bridge_payload,
            'runtime': runtime_node_capabilities().to_dict(),
            **self.lifecycle_runtime.snapshot(),
            **fields,
        }
        msg.data = event_to_json(event_type, **payload)
        self.lifecycle_event_pub.publish(msg)
