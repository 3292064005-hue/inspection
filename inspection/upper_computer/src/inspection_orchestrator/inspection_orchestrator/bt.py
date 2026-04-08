from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import yaml

Status = str

SUCCESS = 'SUCCESS'
FAILURE = 'FAILURE'
RUNNING = 'RUNNING'
CANCELLED = 'CANCELLED'
TIMEOUT = 'TIMEOUT'
VALID_STATUSES = {SUCCESS, FAILURE, RUNNING, CANCELLED, TIMEOUT}

_TEMPLATE_RE = re.compile(r'\$\{([^}]+)\}')


@dataclass(slots=True)
class BTResult:
    """Structured behavior-tree evaluation result.

    Args:
        status: Terminal status of the evaluated node.
        actions: Deferred actions proposed by the node.
        trace: Ordered human-readable trace for diagnostics and replay.
        duration_ms: Wall-clock evaluation time in milliseconds.

    Raises:
        ValueError: When ``status`` is outside the supported runtime contract.

    Boundary behavior:
        ``actions`` and ``trace`` default to empty collections so callers can
        safely append or serialize the result without null checks.
    """

    status: Status
    actions: list[dict[str, object]] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(f'Unsupported BT status: {self.status}')


class BTNode:
    """Base node contract for the local orchestrator behavior-tree runtime."""

    label: str

    def __init__(self, label: str, *, timeout_ms: int | None = None) -> None:
        self.label = str(label or self.__class__.__name__)
        self.timeout_ms = int(timeout_ms) if timeout_ms is not None else None

    def evaluate(self, context: dict[str, object]) -> BTResult:
        """Evaluate one node against the supplied orchestration context.

        Args:
            context: Immutable-by-convention evaluation context for the current tick.

        Returns:
            ``BTResult`` containing terminal status, deferred actions, and trace.

        Raises:
            No exception is propagated for normal predicate/action failures; node
            implementations must translate them into ``FAILURE``.

        Boundary behavior:
            Cooperative cancellation and deadline overruns are enforced here so
            child-node implementations do not need to duplicate those checks.
        """
        started = time.perf_counter()
        if is_cancel_requested(context):
            return BTResult(status=CANCELLED, trace=[f'{self.label}:{CANCELLED}'])
        result = self._evaluate(context)
        duration_ms = max(0, int(round((time.perf_counter() - started) * 1000)))
        if self._deadline_exceeded(context) or (self.timeout_ms is not None and duration_ms > self.timeout_ms):
            return BTResult(status=TIMEOUT, trace=[*result.trace, f'{self.label}:{TIMEOUT}'], duration_ms=duration_ms)
        if not result.trace:
            result.trace = [f'{self.label}:{result.status}']
        result.duration_ms = duration_ms
        return result

    def _deadline_exceeded(self, context: dict[str, object]) -> bool:
        deadline = context.get('__deadline_monotonic__')
        if deadline is None:
            return False
        try:
            return time.perf_counter() > float(deadline)
        except (TypeError, ValueError):
            return False

    def _evaluate(self, context: dict[str, object]) -> BTResult:
        raise NotImplementedError


class Condition(BTNode):
    def __init__(self, label: str, predicate: Callable[[dict[str, object]], bool], *, timeout_ms: int | None = None) -> None:
        super().__init__(label, timeout_ms=timeout_ms)
        self.predicate = predicate

    def _evaluate(self, context: dict[str, object]) -> BTResult:
        ok = bool(self.predicate(context))
        return BTResult(status=SUCCESS if ok else FAILURE, trace=[f'{self.label}:{SUCCESS if ok else FAILURE}'])


class Action(BTNode):
    def __init__(
        self,
        label: str,
        builder: Callable[[dict[str, object]], Iterable[dict[str, object]]],
        *,
        success_status: Status = SUCCESS,
        timeout_ms: int | None = None,
    ) -> None:
        super().__init__(label, timeout_ms=timeout_ms)
        if success_status not in VALID_STATUSES:
            raise ValueError(f'Unsupported action status: {success_status}')
        self.builder = builder
        self.success_status = success_status

    def _evaluate(self, context: dict[str, object]) -> BTResult:
        actions = [dict(item) for item in self.builder(context)]
        return BTResult(status=self.success_status, actions=actions, trace=[f'{self.label}:{self.success_status}'])


class Sequence(BTNode):
    def __init__(self, label: str, *children: BTNode, timeout_ms: int | None = None) -> None:
        super().__init__(label, timeout_ms=timeout_ms)
        self.children = tuple(children)

    def _evaluate(self, context: dict[str, object]) -> BTResult:
        actions: list[dict[str, object]] = []
        trace = [f'{self.label}:ENTER']
        for child in self.children:
            result = child.evaluate(context)
            trace.extend(result.trace)
            if result.status != SUCCESS:
                return BTResult(status=result.status, actions=[] if result.status in {FAILURE, TIMEOUT, CANCELLED} else actions, trace=trace)
            actions.extend(result.actions)
        trace.append(f'{self.label}:{SUCCESS}')
        return BTResult(status=SUCCESS, actions=actions, trace=trace)


class Selector(BTNode):
    def __init__(self, label: str, *children: BTNode, timeout_ms: int | None = None) -> None:
        super().__init__(label, timeout_ms=timeout_ms)
        self.children = tuple(children)

    def _evaluate(self, context: dict[str, object]) -> BTResult:
        trace = [f'{self.label}:ENTER']
        for child in self.children:
            result = child.evaluate(context)
            trace.extend(result.trace)
            if result.status == SUCCESS:
                trace.append(f'{self.label}:{SUCCESS}')
                return BTResult(status=SUCCESS, actions=result.actions, trace=trace)
            if result.status in {RUNNING, CANCELLED, TIMEOUT}:
                trace.append(f'{self.label}:{result.status}')
                return BTResult(status=result.status, actions=result.actions, trace=trace)
        trace.append(f'{self.label}:{FAILURE}')
        return BTResult(status=FAILURE, trace=trace)


ActionBuilder = Callable[[dict[str, object]], Iterable[dict[str, object]]]
_ACTION_BUILDERS: dict[str, ActionBuilder] = {}


def register_action_builder(name: str, builder: ActionBuilder) -> None:
    key = str(name or '').strip()
    if not key:
        raise ValueError('Action builder name is empty.')
    _ACTION_BUILDERS[key] = builder


def context_get(context: dict[str, object], path: str, default: Any = None) -> Any:
    current: Any = context
    for part in str(path or '').split('.'):
        part = part.strip()
        if not part:
            continue
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
            continue
        if isinstance(current, (list, tuple)) and part.isdigit():
            index = int(part)
            if index < 0 or index >= len(current):
                return default
            current = current[index]
            continue
        return default
    return current


def is_cancel_requested(context: dict[str, object]) -> bool:
    explicit = context.get('__cancel_requested__')
    if explicit is not None:
        return bool(explicit)
    return bool(context_get(context, 'control.cancel_requested', False))


def _substitute_template(value: Any, context: dict[str, object]) -> Any:
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            resolved = context_get(context, match.group(1).strip(), '')
            return '' if resolved is None else str(resolved)

        return _TEMPLATE_RE.sub(_replace, value)
    if isinstance(value, list):
        return [_substitute_template(item, context) for item in value]
    if isinstance(value, dict):
        return {str(key): _substitute_template(item, context) for key, item in value.items()}
    return copy.deepcopy(value)


def evaluate_check(spec: dict[str, Any] | bool | None, context: dict[str, object]) -> bool:
    if isinstance(spec, bool):
        return spec
    if spec is None:
        return False
    if not isinstance(spec, dict):
        raise ValueError(f'Unsupported condition spec: {spec!r}')
    op = str(spec.get('type', 'bool')).strip().lower()
    if op == 'bool':
        return bool(context_get(context, str(spec.get('path', '')), spec.get('default', False)))
    if op == 'equals':
        return context_get(context, str(spec.get('path', '')), None) == spec.get('value')
    if op == 'not_equals':
        return context_get(context, str(spec.get('path', '')), None) != spec.get('value')
    if op == 'in':
        candidates = spec.get('values', [])
        if not isinstance(candidates, (list, tuple, set)):
            return False
        return context_get(context, str(spec.get('path', '')), None) in candidates
    if op == 'non_empty':
        value = context_get(context, str(spec.get('path', '')), spec.get('default', None))
        return bool(value)
    if op == 'all_of':
        items = spec.get('items', [])
        return all(evaluate_check(item, context) for item in items if item is not None)
    if op == 'any_of':
        items = spec.get('items', [])
        return any(evaluate_check(item, context) for item in items if item is not None)
    if op == 'not':
        return not evaluate_check(spec.get('item'), context)
    raise ValueError(f'Unsupported condition operator: {op}')


def _static_action_builder(actions: list[dict[str, Any]]) -> ActionBuilder:
    def _builder(context: dict[str, object]) -> list[dict[str, object]]:
        return [dict(_substitute_template(item, context)) for item in actions]

    return _builder


def build_node_from_spec(spec: dict[str, Any]) -> BTNode:
    if not isinstance(spec, dict):
        raise ValueError(f'Behavior-tree spec must be a mapping, got {type(spec).__name__}.')
    node_type = str(spec.get('type', '')).strip().lower()
    label = str(spec.get('label') or node_type or 'node')
    timeout_ms = int(spec['timeout_ms']) if 'timeout_ms' in spec and spec.get('timeout_ms') is not None else None
    if node_type == 'sequence':
        children = tuple(build_node_from_spec(child) for child in spec.get('children', []))
        return Sequence(label, *children, timeout_ms=timeout_ms)
    if node_type == 'selector':
        children = tuple(build_node_from_spec(child) for child in spec.get('children', []))
        return Selector(label, *children, timeout_ms=timeout_ms)
    if node_type == 'condition':
        check = spec.get('check')
        return Condition(label, lambda ctx, check=check: evaluate_check(check, ctx), timeout_ms=timeout_ms)
    if node_type == 'action':
        builder_name = str(spec.get('builder', '')).strip()
        if builder_name:
            builder = _ACTION_BUILDERS.get(builder_name)
            if builder is None:
                raise ValueError(f'Unknown action builder: {builder_name}')
        else:
            raw_actions = spec.get('actions', [])
            if not isinstance(raw_actions, list):
                raise ValueError(f'Action node actions must be a list: {label}')
            builder = _static_action_builder(raw_actions)
        status = str(spec.get('status', SUCCESS)).strip().upper() or SUCCESS
        return Action(label, builder, success_status=status, timeout_ms=timeout_ms)
    raise ValueError(f'Unsupported behavior-tree node type: {node_type}')


def load_tree_catalog(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    if not isinstance(payload, dict):
        raise ValueError('Behavior-tree catalog must be a mapping at the document root.')
    trees = payload.get('trees')
    if not isinstance(trees, dict) or not trees:
        raise ValueError('Behavior-tree catalog must contain a non-empty trees mapping.')
    return payload
