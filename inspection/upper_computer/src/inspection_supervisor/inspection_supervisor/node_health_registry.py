from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeHealth:
    name: str
    required: bool = True
    criticality: str = 'required'
    fault_domain: str = 'support'
    last_seen_monotonic: float = 0.0
    last_event: str = ''
    state: str = 'UNKNOWN'
    active: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    def mark(self, *, now: float, event: str = '', state: str | None = None, detail: dict[str, Any] | None = None) -> None:
        self.last_seen_monotonic = now
        if event:
            self.last_event = event
        if state is not None:
            self.state = state
            self.active = state in {'ACTIVE', 'RUNNING', 'READY', 'OK'}
        if detail is not None:
            self.detail = dict(detail)
            lifecycle_state = str(self.detail.get('lifecycle_state', '')).upper()
            if lifecycle_state:
                self.state = lifecycle_state
                self.active = lifecycle_state in {'ACTIVE', 'RUNNING', 'READY', 'OK'}

    def snapshot(self, *, now: float, timeout_sec: float) -> dict[str, Any]:
        age = max(0.0, now - self.last_seen_monotonic) if self.last_seen_monotonic else float('inf')
        healthy = age <= timeout_sec
        return {
            'name': self.name,
            'required': self.required,
            'criticality': self.criticality,
            'faultDomain': self.fault_domain,
            'last_seen_age_sec': None if age == float('inf') else round(age, 3),
            'healthy': healthy,
            'active': self.active,
            'state': self.state,
            'last_event': self.last_event,
            'detail': dict(self.detail),
        }


@dataclass(slots=True)
class NodeHealthRegistry:
    expected_nodes: list[str]
    required_nodes: set[str] = field(default_factory=set)
    node_classes: dict[str, str] = field(default_factory=dict)
    node_domains: dict[str, str] = field(default_factory=dict)
    nodes: dict[str, NodeHealth] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.required_nodes:
            self.required_nodes = set(self.expected_nodes)
        for name in self.expected_nodes:
            criticality = self.node_classes.get(name, 'required' if name in self.required_nodes else 'optional')
            self.nodes[name] = NodeHealth(
                name=name,
                required=name in self.required_nodes,
                criticality=criticality,
                fault_domain=self.node_domains.get(name, 'support'),
            )

    def ensure_node(self, name: str) -> NodeHealth:
        if name not in self.nodes:
            criticality = self.node_classes.get(name, 'optional')
            self.nodes[name] = NodeHealth(
                name=name,
                required=criticality != 'optional',
                criticality=criticality,
                fault_domain=self.node_domains.get(name, 'support'),
            )
        return self.nodes[name]

    def ingest_event(self, name: str, *, now: float, event_type: str = '', state: str | None = None, detail: dict[str, Any] | None = None) -> None:
        self.ensure_node(name).mark(now=now, event=event_type, state=state, detail=detail)

    def stale_nodes(self, *, now: float, timeout_sec: float, criticality: str | None = None) -> list[str]:
        stale: list[str] = []
        for name, node in self.nodes.items():
            if criticality is not None and node.criticality != criticality:
                continue
            if criticality is None and not node.required:
                continue
            if node.last_seen_monotonic == 0.0 or (now - node.last_seen_monotonic) > timeout_sec:
                stale.append(name)
        return sorted(stale)

    def missing_active_nodes(self, criticality: str | None = None) -> list[str]:
        return sorted(
            name
            for name, node in self.nodes.items()
            if (criticality is None or node.criticality == criticality) and node.required and not node.active
        )

    def all_required_active(self) -> bool:
        return not self.missing_active_nodes()

    def activation_progress(self) -> dict[str, int]:
        required = [node for node in self.nodes.values() if node.required]
        active = [node for node in required if node.active]
        return {'required': len(required), 'active': len(active)}

    def _fault_domain_status(self, *, now: float, timeout_sec: float) -> dict[str, dict[str, Any]]:
        domains: dict[str, dict[str, Any]] = {}
        for name, node in self.nodes.items():
            domain = node.fault_domain or 'support'
            entry = domains.setdefault(
                domain,
                {
                    'nodes': [],
                    'requiredNodes': [],
                    'optionalNodes': [],
                    'staleNodes': [],
                    'missingActiveNodes': [],
                },
            )
            entry['nodes'].append(name)
            if node.required:
                entry['requiredNodes'].append(name)
            else:
                entry['optionalNodes'].append(name)
            if node.last_seen_monotonic == 0.0 or (now - node.last_seen_monotonic) > timeout_sec:
                if node.required:
                    entry['staleNodes'].append(name)
            if node.required and not node.active:
                entry['missingActiveNodes'].append(name)
        for entry in domains.values():
            entry['nodes'] = sorted(entry['nodes'])
            entry['requiredNodes'] = sorted(entry['requiredNodes'])
            entry['optionalNodes'] = sorted(entry['optionalNodes'])
            entry['staleNodes'] = sorted(entry['staleNodes'])
            entry['missingActiveNodes'] = sorted(entry['missingActiveNodes'])
            entry['healthy'] = not entry['staleNodes'] and not entry['missingActiveNodes']
        return dict(sorted(domains.items()))

    def overall_status(self, *, now: float, timeout_sec: float) -> dict[str, Any]:
        critical_stale = self.stale_nodes(now=now, timeout_sec=timeout_sec, criticality='critical')
        required_stale = self.stale_nodes(now=now, timeout_sec=timeout_sec, criticality='required')
        optional_stale = self.stale_nodes(now=now, timeout_sec=timeout_sec, criticality='optional')
        critical_missing = self.missing_active_nodes(criticality='critical')
        required_missing = self.missing_active_nodes(criticality='required')
        fault_domains = self._fault_domain_status(now=now, timeout_sec=timeout_sec)
        degraded_fault_domains = [name for name, payload in fault_domains.items() if not bool(payload.get('healthy', False))]
        healthy = not critical_stale and not required_stale and not critical_missing and not required_missing
        return {
            'healthy': healthy,
            'critical_stale_nodes': critical_stale,
            'required_stale_nodes': required_stale,
            'optional_stale_nodes': optional_stale,
            'critical_missing_nodes': critical_missing,
            'required_missing_nodes': required_missing,
            'stale_nodes': sorted(set(critical_stale + required_stale)),
            'missing_active_nodes': sorted(set(critical_missing + required_missing)),
            'activation_progress': self.activation_progress(),
            'faultDomains': fault_domains,
            'degradedFaultDomains': degraded_fault_domains,
            'nodes': {name: node.snapshot(now=now, timeout_sec=timeout_sec) for name, node in sorted(self.nodes.items())},
        }
