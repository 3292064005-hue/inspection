from __future__ import annotations

from typing import Any

from ..context import GatewayAppContext
from ..service_common import app_facade


class ResultCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def repair_read_model(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        payload = app_facade(self.context).repair_read_model()
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='READ_MODEL_REPAIR', resource='/results/read-model', details=payload)
        return payload
