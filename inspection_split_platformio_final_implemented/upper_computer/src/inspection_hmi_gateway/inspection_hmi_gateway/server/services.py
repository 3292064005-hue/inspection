from __future__ import annotations

"""Compatibility re-export layer for gateway services.

Routers and tests may still import from ``server.services``. The concrete implementations are now
split into query- and command-oriented modules to keep gateway read paths and state-changing paths
separate without breaking existing imports.
"""

from .query_services import (
    ActionQueryService as ActionGatewayService,
    AuditQueryService as AuditService,
    DiagnosticsQueryService,
    ExportQueryService,
    ReplayGatewayQueryService,
    RecipeQueryService,
    ResultQueryService,
    StationQueryService,
    TelemetryGatewayQueryService,
)
from .command_services import (
    ActionCommandService,
    DiagnosticsCommandService,
    ExportCommandService,
    RecipeCommandService,
    StationCommandService,
)


class StationService(StationQueryService, StationCommandService):
    pass


class ResultService(ResultQueryService):
    pass


class RecipeService(RecipeQueryService, RecipeCommandService):
    pass


class DiagnosticsService(DiagnosticsQueryService, DiagnosticsCommandService):
    pass


class ExportService(ExportQueryService, ExportCommandService):
    pass


class ActionService(ActionGatewayService, ActionCommandService):
    pass

__all__ = [
    'ActionCommandService',
    'ActionGatewayService',
    'ActionService',
    'AuditService',
    'DiagnosticsCommandService',
    'DiagnosticsService',
    'ExportCommandService',
    'ExportService',
    'ReplayGatewayQueryService',
    'RecipeCommandService',
    'RecipeService',
    'ResultService',
    'StationCommandService',
    'StationService',
    'TelemetryGatewayQueryService',
]
