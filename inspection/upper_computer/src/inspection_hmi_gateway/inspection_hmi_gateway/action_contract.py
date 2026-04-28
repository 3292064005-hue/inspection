from __future__ import annotations

"""Action contract definitions and execution-governance helpers.

The action registry is the single source of truth for gateway transport
metadata, execution-governance policy, compatibility-route lifecycle
governance, station capability expectations, and generated-client visibility.
Request payload schema validation remains enforced by the API request models.
"""

from dataclasses import dataclass
import os
from typing import Any

from inspection_utils.config_common import load_yaml
from inspection_utils.io_common import resolve_runtime_path


EXECUTOR_SUBMIT_TOPIC = '/inspection/action_executor/submit'
EXECUTOR_CANCEL_TOPIC = '/inspection/action_executor/cancel'
EXECUTOR_EVENT_TOPIC = '/inspection/action_executor/events'
EXPERIMENTAL_ACTIONS_ENV = 'INSPECTION_EXPERIMENTAL_ACTIONS_ENABLED'
ACTION_REGISTRY_ENV = 'INSPECTION_ACTION_REGISTRY_PATH'
DEFAULT_ACTION_REGISTRY_PATH = 'config/system/action_registry.yaml'
DEFAULT_ACTION_API_SURFACE = 'public_production'
PUBLIC_ACTION_API_SURFACE = 'public_production'
INTERNAL_ACTION_API_SURFACE = 'internal_experimental'




def _normalized_api_surface(value: str | None) -> str:
    normalized = str(value or DEFAULT_ACTION_API_SURFACE).strip().lower()
    return normalized or DEFAULT_ACTION_API_SURFACE


def _contract_matches_surface(contract: ActionContract, api_surface: str | None) -> bool:
    if api_surface is None:
        return True
    return _normalized_api_surface(contract.capability.api_surface) == _normalized_api_surface(api_surface)


def _public_contract_visible(contract: ActionContract, *, include_non_production: bool) -> bool:
    capability = contract.capability
    if not _contract_matches_surface(contract, PUBLIC_ACTION_API_SURFACE):
        return False
    if include_non_production:
        return bool(capability.public_catalog)
    return bool(capability.public_catalog and capability.availability == 'production_ready' and capability.visibility == 'visible')
class ActionPolicyError(PermissionError):
    """Raised when an action is visible in the catalog but cannot be executed."""

    def __init__(self, kind: str, reason: str, message: str) -> None:
        self.kind = str(kind or '').strip().lower()
        self.reason = str(reason or 'action_execution_blocked').strip() or 'action_execution_blocked'
        self.user_message = str(message or '动作当前不可执行。').strip() or '动作当前不可执行。'
        super().__init__(self.user_message)

    def to_payload(self) -> dict[str, str]:
        return {'code': self.reason, 'kind': self.kind, 'message': self.user_message}


class ActionDispatchError(RuntimeError):
    """Raised when a job record is created but execution transport cannot accept it."""

    def __init__(self, kind: str, reason: str, message: str, *, job_id: str = '', transport: str = '') -> None:
        self.kind = str(kind or '').strip().lower()
        self.reason = str(reason or 'action_transport_unavailable').strip() or 'action_transport_unavailable'
        self.user_message = str(message or '动作提交失败，执行链路当前不可用。').strip() or '动作提交失败，执行链路当前不可用。'
        self.job_id = str(job_id or '').strip()
        self.transport = str(transport or '').strip()
        super().__init__(self.user_message)

    def to_payload(self) -> dict[str, str]:
        return {
            'code': self.reason,
            'kind': self.kind,
            'message': self.user_message,
            'jobId': self.job_id,
            'transport': self.transport,
        }


@dataclass(frozen=True, slots=True)
class ActionCapability:
    """Describes the delivery maturity and execution policy of an action."""

    availability: str
    visibility: str = 'visible'
    execution_policy: str = 'allowed'
    runtime_truth: str = 'real'
    summary: str = ''
    blocked_reason: str = ''
    experimental_env: str = EXPERIMENTAL_ACTIONS_ENV
    public_catalog: bool = True
    generated_client: bool = True
    internal_client: bool = False
    api_surface: str = DEFAULT_ACTION_API_SURFACE
    delivery_class: str = 'official'

    def submit_state(self) -> tuple[bool, str]:
        policy = str(self.execution_policy or 'blocked').strip().lower()
        if policy == 'allowed':
            return True, ''
        if policy == 'experimental':
            enabled = str(os.environ.get(self.experimental_env, '')).strip().lower() in {'1', 'true', 'yes', 'on'}
            if enabled:
                return True, ''
            return False, self.blocked_reason or f'enable_{self.experimental_env.lower()}'
        return False, self.blocked_reason or 'action_execution_blocked'

    def to_dict(self) -> dict[str, object]:
        allowed, reason = self.submit_state()
        return {
            'availability': self.availability,
            'visibility': self.visibility,
            'executionPolicy': self.execution_policy,
            'runtimeTruth': self.runtime_truth,
            'summary': self.summary,
            'submitEnabled': allowed,
            'submitReason': reason,
            'experimentalEnv': self.experimental_env if self.execution_policy == 'experimental' else '',
            'publicCatalog': self.public_catalog,
            'generatedClient': self.generated_client,
            'internalClient': self.internal_client,
            'apiSurface': self.api_surface,
            'deliveryClass': self.delivery_class,
        }


@dataclass(frozen=True, slots=True)
class ActionGovernance:
    """Describe lifecycle governance metadata for one action."""

    tier: str = 'official'
    lifecycle: str = 'ga'
    sunset_release: str = ''
    promotion_criteria: tuple[str, ...] = ()
    required_verification: tuple[str, ...] = ()
    documentation_refs: tuple[str, ...] = ()
    ui_label: str = ''

    def to_dict(self) -> dict[str, object]:
        return {
            'tier': self.tier,
            'lifecycle': self.lifecycle,
            'sunsetRelease': self.sunset_release,
            'promotionCriteria': list(self.promotion_criteria),
            'requiredVerification': list(self.required_verification),
            'documentationRefs': list(self.documentation_refs),
            'uiLabel': self.ui_label,
        }


@dataclass(frozen=True, slots=True)
class ActionContract:
    """Static action metadata exposed to API, ROS bridges, and executors."""

    kind: str
    ros_type: str
    topic: str
    required_payload: tuple[str, ...] = ()
    capability: ActionCapability = ActionCapability(availability='production_ready')
    governance: ActionGovernance = ActionGovernance()
    api_path: str = ''
    operation_id: str = ''

    def to_dict(self) -> dict[str, object]:
        return {
            'kind': self.kind,
            'type': self.ros_type,
            'topic': self.topic,
            'requiredPayload': list(self.required_payload),
            'capability': self.capability.to_dict(),
            'governance': self.governance.to_dict(),
            'apiPath': self.api_path,
            'operationId': self.operation_id,
        }


def _load_action_registry_payload() -> dict[str, Any]:
    raw_path = str(os.environ.get(ACTION_REGISTRY_ENV, DEFAULT_ACTION_REGISTRY_PATH) or DEFAULT_ACTION_REGISTRY_PATH)
    resolved = resolve_runtime_path(raw_path, start=__file__)
    if not resolved.exists():
        raise FileNotFoundError(f'action registry is required: {resolved}')
    payload = load_yaml(resolved) or {}
    if not isinstance(payload, dict):
        raise ValueError('action registry payload must be a mapping')
    return payload


def _capability_from_mapping(payload: dict[str, Any]) -> ActionCapability:
    return ActionCapability(
        availability=str(payload.get('availability', 'production_ready') or 'production_ready'),
        visibility=str(payload.get('visibility', 'visible') or 'visible'),
        execution_policy=str(payload.get('execution_policy', payload.get('executionPolicy', 'allowed')) or 'allowed'),
        runtime_truth=str(payload.get('runtime_truth', payload.get('runtimeTruth', 'real')) or 'real'),
        summary=str(payload.get('summary', '') or ''),
        blocked_reason=str(payload.get('blocked_reason', payload.get('blockedReason', '')) or ''),
        experimental_env=str(payload.get('experimental_env', payload.get('experimentalEnv', EXPERIMENTAL_ACTIONS_ENV)) or EXPERIMENTAL_ACTIONS_ENV),
        public_catalog=bool(payload.get('public_catalog', payload.get('publicCatalog', True))),
        generated_client=bool(payload.get('generated_client', payload.get('generatedClient', True))),
        internal_client=bool(payload.get('internal_client', payload.get('internalClient', False))),
        api_surface=str(payload.get('api_surface', payload.get('apiSurface', DEFAULT_ACTION_API_SURFACE)) or DEFAULT_ACTION_API_SURFACE),
        delivery_class=str(payload.get('delivery_class', payload.get('deliveryClass', 'official')) or 'official'),
    )


def _governance_from_mapping(payload: dict[str, Any]) -> ActionGovernance:
    return ActionGovernance(
        tier=str(payload.get('tier', 'official') or 'official'),
        lifecycle=str(payload.get('lifecycle', 'ga') or 'ga'),
        sunset_release=str(payload.get('sunset_release', payload.get('sunsetRelease', '')) or ''),
        promotion_criteria=tuple(str(item) for item in payload.get('promotion_criteria', payload.get('promotionCriteria', ())) if str(item).strip()),
        required_verification=tuple(str(item) for item in payload.get('required_verification', payload.get('requiredVerification', ())) if str(item).strip()),
        documentation_refs=tuple(str(item) for item in payload.get('documentation_refs', payload.get('documentationRefs', ())) if str(item).strip()),
        ui_label=str(payload.get('ui_label', payload.get('uiLabel', '')) or ''),
    )


def _build_action_contracts() -> dict[str, ActionContract]:
    payload = _load_action_registry_payload()
    raw_actions = payload.get('actions', payload)
    if not isinstance(raw_actions, dict):
        raise ValueError('action registry actions must be a mapping')
    contracts: dict[str, ActionContract] = {}
    for raw_kind, raw_contract in raw_actions.items():
        kind = str(raw_kind or '').strip().lower()
        if not kind or not isinstance(raw_contract, dict):
            continue
        contracts[kind] = ActionContract(
            kind=kind,
            ros_type=str(raw_contract.get('ros_type', raw_contract.get('rosType', '')) or ''),
            topic=str(raw_contract.get('topic', '') or ''),
            required_payload=tuple(str(item) for item in raw_contract.get('required_payload', raw_contract.get('requiredPayload', ())) if str(item).strip()),
            capability=_capability_from_mapping(raw_contract.get('capability', {}) if isinstance(raw_contract.get('capability', {}), dict) else {}),
            governance=_governance_from_mapping(raw_contract.get('governance', {}) if isinstance(raw_contract.get('governance', {}), dict) else {}),
            api_path=str(raw_contract.get('api_path', raw_contract.get('apiPath', '')) or ''),
            operation_id=str(raw_contract.get('operation_id', raw_contract.get('operationId', '')) or ''),
        )
    if not contracts:
        raise ValueError('action registry resolved to an empty contract set')
    return contracts


ACTION_CONTRACTS: dict[str, ActionContract] = _build_action_contracts()


def action_contract(kind: str) -> ActionContract:
    """Return the normalized action contract for ``kind``."""
    normalized = str(kind or '').strip().lower()
    return ACTION_CONTRACTS[normalized]


def action_catalog(*, include_non_production: bool = True, api_surface: str | None = None) -> list[dict[str, object]]:
    """Return action catalog entries filtered by API surface and visibility."""
    items: list[dict[str, object]] = []
    for contract in ACTION_CONTRACTS.values():
        if api_surface is None:
            if not include_non_production and not _public_contract_visible(contract, include_non_production=False):
                continue
        elif _normalized_api_surface(api_surface) == PUBLIC_ACTION_API_SURFACE:
            if not _public_contract_visible(contract, include_non_production=include_non_production):
                continue
        elif not _contract_matches_surface(contract, api_surface):
            continue
        items.append(contract.to_dict())
    return items


def action_submit_state(kind: str) -> tuple[bool, str]:
    """Resolve whether the current process may submit ``kind``."""
    return action_contract(kind).capability.submit_state()


def ensure_action_submit_allowed(kind: str) -> ActionContract:
    """Validate that an action may be submitted before any job record is created."""
    contract = action_contract(kind)
    allowed, reason = contract.capability.submit_state()
    if allowed:
        return contract
    raise ActionPolicyError(contract.kind, reason, contract.capability.summary or '动作当前不可执行。')


def validate_action_payload(kind: str, payload: dict[str, Any]) -> str:
    normalized = str(kind or '').strip().lower()
    contract = ACTION_CONTRACTS.get(normalized)
    if contract is None:
        return f'unsupported_action_kind:{normalized}'
    for key in contract.required_payload:
        value = payload.get(key, '')
        if isinstance(value, bool):
            continue
        if value is None:
            return f'{key} is required'
        if not str(value).strip():
            return f'{key} is required'
    return ''


def payload_from_goal(kind: str, request: Any) -> dict[str, Any]:
    normalized = str(kind or '').strip().lower()
    if normalized == 'start_batch':
        return {'batchId': str(getattr(request, 'batch_id', '')), 'recipeId': str(getattr(request, 'recipe_id', ''))}
    if normalized == 'reset_station':
        return {'reason': str(getattr(request, 'reason', '')), 'resumeAfter': False}
    if normalized == 'execute_replay':
        return {'traceId': str(getattr(request, 'trace_id', ''))}
    if normalized == 'export_batch':
        return {'batchId': str(getattr(request, 'batch_id', ''))}
    if normalized == 'run_benchmark':
        return {'profileName': str(getattr(request, 'profile_name', 'default'))}
    if normalized == 'switch_recipe_with_validation':
        return {'recipeId': str(getattr(request, 'recipe_id', '')), 'dryRun': bool(getattr(request, 'validate_only', False))}
    if normalized == 'stop_station':
        return {'reason': str(getattr(request, 'reason', ''))}
    if normalized == 'set_maintenance_mode':
        return {'enabled': bool(getattr(request, 'enabled', False))}
    if normalized == 'create_batch':
        return {'requestedBy': str(getattr(request, 'requested_by', ''))}
    if normalized == 'diagnostic_capture_frame':
        return {'requestSource': str(getattr(request, 'request_source', ''))}
    if normalized == 'diagnostic_test_lighting':
        return {'requestSource': str(getattr(request, 'request_source', ''))}
    if normalized == 'diagnostic_test_sort_actuator':
        return {'requestSource': str(getattr(request, 'request_source', ''))}
    return {}


def action_capability_matrix(*, api_surface: str | None = None, include_non_production: bool = True) -> dict[str, dict[str, object]]:
    """Return the effective capability matrix filtered by API surface."""
    catalog = action_catalog(include_non_production=include_non_production, api_surface=api_surface)
    return {
        str(item['kind']): {
            **dict(item.get('capability', {})),
            'governance': dict(item.get('governance', {})),
            'apiPath': str(item.get('apiPath', '')),
            'operationId': str(item.get('operationId', '')),
        }
        for item in catalog
        if isinstance(item, dict) and str(item.get('kind', '')).strip()
    }


def compatibility_route_catalog_from_registry() -> dict[str, dict[str, object]]:
    """Return compatibility-route governance metadata from the registry."""
    payload = _load_action_registry_payload()
    raw_catalog = payload.get('compatibility_routes', {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_catalog, dict):
        return {}
    catalog: dict[str, dict[str, object]] = {}
    for raw_name, raw_item in raw_catalog.items():
        name = str(raw_name or '').strip()
        if not name or not isinstance(raw_item, dict):
            continue
        catalog[name] = {
            'enabled': bool(raw_item.get('enabled', True)),
            'canonical_route': str(raw_item.get('canonical_route', raw_item.get('canonicalRoute', '/api/v1/actions/*')) or '/api/v1/actions/*'),
            'deprecation_phase': str(raw_item.get('deprecation_phase', raw_item.get('deprecationPhase', 'frozen')) or 'frozen'),
            'sunset_release': str(raw_item.get('sunset_release', raw_item.get('sunsetRelease', '')) or ''),
            'migration_guide': str(raw_item.get('migration_guide', raw_item.get('migrationGuide', '')) or ''),
            'consumers': [str(item) for item in raw_item.get('consumers', ()) if str(item).strip()],
            'routes': [str(item) for item in raw_item.get('routes', ()) if str(item).strip()],
        }
    return catalog



def public_action_contracts() -> dict[str, ActionContract]:
    """Return action contracts that belong to the public production HTTP surface."""
    return {kind: contract for kind, contract in ACTION_CONTRACTS.items() if _contract_matches_surface(contract, PUBLIC_ACTION_API_SURFACE)}


def internal_action_contracts() -> dict[str, ActionContract]:
    """Return action contracts routed through the internal experimental HTTP surface."""
    return {kind: contract for kind, contract in ACTION_CONTRACTS.items() if _contract_matches_surface(contract, INTERNAL_ACTION_API_SURFACE)}


def public_action_capability_matrix(*, include_non_production: bool = False) -> dict[str, dict[str, object]]:
    """Return the public capability matrix exposed on the public HTTP surface."""
    return action_capability_matrix(api_surface=PUBLIC_ACTION_API_SURFACE, include_non_production=include_non_production)


def internal_action_capability_matrix() -> dict[str, dict[str, object]]:
    """Return the internal experimental capability matrix."""
    return action_capability_matrix(api_surface=INTERNAL_ACTION_API_SURFACE, include_non_production=True)


def public_action_operation_ids() -> set[str]:
    """Return submit operation ids mapped to the public production action plane."""
    return {contract.operation_id for contract in public_action_contracts().values() if contract.operation_id}


def internal_action_operation_ids() -> set[str]:
    """Return submit operation ids mapped to the internal experimental action plane."""
    return {contract.operation_id for contract in internal_action_contracts().values() if contract.operation_id}

def station_capability_profiles() -> dict[str, dict[str, Any]]:
    """Return station capability expectations and firmware route profiles."""
    payload = _load_action_registry_payload()
    raw_profiles = payload.get('station_capability_profiles', {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_profiles, dict):
        return {}
    profiles: dict[str, dict[str, Any]] = {}
    for raw_name, raw_profile in raw_profiles.items():
        name = str(raw_name or '').strip()
        if not name or not isinstance(raw_profile, dict):
            continue
        profiles[name] = dict(raw_profile)
    return profiles




def station_adapter_manifest_profiles() -> dict[str, dict[str, Any]]:
    """Return station-adapter manifest profiles derived from the registry."""
    payload = _load_action_registry_payload()
    raw_profiles = payload.get('station_adapter_manifests', {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_profiles, dict):
        return {}
    profiles: dict[str, dict[str, Any]] = {}
    for raw_name, raw_profile in raw_profiles.items():
        name = str(raw_name or '').strip()
        if not name or not isinstance(raw_profile, dict):
            continue
        profiles[name] = dict(raw_profile)
    return profiles

def generated_client_excluded_operation_ids() -> set[str]:
    """Return action-submit operation IDs that must stay out of generated clients."""
    return {contract.operation_id for contract in ACTION_CONTRACTS.values() if contract.operation_id and not contract.capability.generated_client}


def generated_client_contracts() -> dict[str, ActionContract]:
    """Return the subset of action-submit contracts that should enter the public generated client."""
    return {kind: contract for kind, contract in ACTION_CONTRACTS.items() if contract.capability.generated_client}


def internal_client_contracts() -> dict[str, ActionContract]:
    """Return the subset of action-submit contracts that should enter the internal SDK."""
    return {kind: contract for kind, contract in ACTION_CONTRACTS.items() if contract.capability.internal_client}
