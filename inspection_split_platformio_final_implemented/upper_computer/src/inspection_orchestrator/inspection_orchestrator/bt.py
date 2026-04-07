from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

Status = str


@dataclass(slots=True)
class BTResult:
    status: Status
    actions: list[dict[str, object]] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


class BTNode:
    label: str

    def evaluate(self, context: dict[str, object]) -> BTResult:
        raise NotImplementedError


class Condition(BTNode):
    def __init__(self, label: str, predicate: Callable[[dict[str, object]], bool]) -> None:
        self.label = label
        self.predicate = predicate

    def evaluate(self, context: dict[str, object]) -> BTResult:
        ok = bool(self.predicate(context))
        return BTResult(status='SUCCESS' if ok else 'FAILURE', trace=[f'{self.label}:{"SUCCESS" if ok else "FAILURE"}'])


class Action(BTNode):
    def __init__(self, label: str, builder: Callable[[dict[str, object]], Iterable[dict[str, object]]]) -> None:
        self.label = label
        self.builder = builder

    def evaluate(self, context: dict[str, object]) -> BTResult:
        actions = [dict(item) for item in self.builder(context)]
        return BTResult(status='SUCCESS', actions=actions, trace=[f'{self.label}:SUCCESS'])


class Sequence(BTNode):
    def __init__(self, label: str, *children: BTNode) -> None:
        self.label = label
        self.children = children

    def evaluate(self, context: dict[str, object]) -> BTResult:
        actions: list[dict[str, object]] = []
        trace = [self.label]
        for child in self.children:
            result = child.evaluate(context)
            trace.extend(result.trace)
            if result.status != 'SUCCESS':
                return BTResult(status=result.status, actions=actions, trace=trace)
            actions.extend(result.actions)
        return BTResult(status='SUCCESS', actions=actions, trace=trace)


class Selector(BTNode):
    def __init__(self, label: str, *children: BTNode) -> None:
        self.label = label
        self.children = children

    def evaluate(self, context: dict[str, object]) -> BTResult:
        trace = [self.label]
        for child in self.children:
            result = child.evaluate(context)
            trace.extend(result.trace)
            if result.status == 'SUCCESS':
                return BTResult(status='SUCCESS', actions=result.actions, trace=trace)
        return BTResult(status='FAILURE', trace=trace)
