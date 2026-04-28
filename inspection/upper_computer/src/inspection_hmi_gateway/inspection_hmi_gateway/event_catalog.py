from __future__ import annotations

from pathlib import Path
from typing import Any

from inspection_utils.config_common import load_yaml
from inspection_utils.io_common import resolve_runtime_path

DEFAULT_GATEWAY_EVENT_REGISTRY_PATH = 'config/system/gateway_event_registry.yaml'


def gateway_event_registry(path: str = DEFAULT_GATEWAY_EVENT_REGISTRY_PATH) -> dict[str, dict[str, Any]]:
    """Load the gateway event producer/consumer registry from configuration."""
    resolved = resolve_runtime_path(path, start=__file__)
    if not resolved.exists():
        return {}
    payload = load_yaml(resolved) or {}
    events = payload.get('events', payload) if isinstance(payload, dict) else {}
    return {str(name): dict(config) for name, config in dict(events).items()} if isinstance(events, dict) else {}


def validate_gateway_event_registry(*, project_root: Path, registry: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Validate that required gateway events have producer and consumer code anchors.

    Args:
        project_root: Repository root used to resolve configured file paths.
        registry: Optional pre-loaded registry payload.

    Returns:
        List of validation error strings. Empty means the registry is aligned.

    Boundary behavior:
        Validation is textual instead of AST-heavy so it can run inside fast CI
        and still catch the most common regression: producer/consumer strings
        drifting out of sync across backend, websocket transport, and frontend.
    """
    loaded = registry if registry is not None else gateway_event_registry()
    issues: list[str] = []
    if not isinstance(loaded, dict):
        return ['gateway_event_registry_invalid']
    contracts_text = (project_root / 'upper_computer' / 'frontend' / 'src' / 'shared' / 'gateway' / 'contracts.ts').read_text(encoding='utf-8')
    handler_text = (project_root / 'upper_computer' / 'frontend' / 'src' / 'shared' / 'gateway' / 'httpGateway.ts').read_text(encoding='utf-8')
    validation_text = (project_root / 'upper_computer' / 'frontend' / 'src' / 'shared' / 'gateway' / 'validation.ts').read_text(encoding='utf-8')
    for event_name, config in loaded.items():
        if not isinstance(config, dict):
            issues.append(f'{event_name}:invalid_config')
            continue
        required = bool(config.get('requiredConsumer', False))
        producer_file = str(config.get('producer_file', '')).strip()
        consumer_file = str(config.get('consumer_file', '')).strip()
        handler_file = str(config.get('handler_file', '')).strip()
        if producer_file:
            producer_path = project_root / producer_file
            if not producer_path.exists():
                issues.append(f'{event_name}:missing_producer_file')
            elif f"'{event_name}'" not in producer_path.read_text(encoding='utf-8') and f'"{event_name}"' not in producer_path.read_text(encoding='utf-8'):
                issues.append(f'{event_name}:producer_anchor_missing')
        if required:
            if f"'{event_name}'" not in contracts_text and f'"{event_name}"' not in contracts_text:
                issues.append(f'{event_name}:contracts_missing')
            if f"'{event_name}'" not in validation_text and f'"{event_name}"' not in validation_text:
                issues.append(f'{event_name}:validation_missing')
            if consumer_file:
                consumer_path = project_root / consumer_file
                if not consumer_path.exists():
                    issues.append(f'{event_name}:missing_consumer_file')
                else:
                    consumer_text = consumer_path.read_text(encoding='utf-8')
                    if f"'{event_name}'" not in consumer_text and f'"{event_name}"' not in consumer_text:
                        issues.append(f'{event_name}:consumer_anchor_missing')
            if handler_file:
                handler_path = project_root / handler_file
                if not handler_path.exists():
                    issues.append(f'{event_name}:missing_handler_file')
                else:
                    current_handler_text = handler_path.read_text(encoding='utf-8')
                    if f"'{event_name}'" not in current_handler_text and f'"{event_name}"' not in current_handler_text:
                        issues.append(f'{event_name}:handler_anchor_missing')
            if f"'{event_name}'" not in handler_text and f'"{event_name}"' not in handler_text:
                issues.append(f'{event_name}:handler_bucket_missing')
    return issues
