#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
for package_dir in sorted((ROOT / 'src').iterdir()):
    if package_dir.is_dir():
        sys.path.insert(0, str(package_dir))

from inspection_hmi_gateway.action_contract import (  # noqa: E402
    ACTION_CONTRACTS,
    compatibility_route_catalog_from_registry,
    station_adapter_manifest_profiles,
    station_capability_profiles,
)

CAPABILITY_TARGET = ROOT / 'config' / 'system' / 'action_capability_matrix.yaml'
GOVERNANCE_TARGET = ROOT / 'config' / 'system' / 'action_governance.yaml'
COMPATIBILITY_TARGET = ROOT / 'config' / 'system' / 'compatibility_routes.yaml'
STATION_EXPECTATION_TARGET = ROOT / 'config' / 'system' / 'station_capability_expectations.yaml'
STATION_ADAPTER_MANIFEST_TARGET = ROOT / 'config' / 'system' / 'station_adapter_manifests.yaml'
STATION_STM32_TARGET = ROOT / 'config' / 'station' / 'station_stm32.yaml'
FW_CODES_TARGET = REPO_ROOT / 'firmware' / 'stm32_station_platformio' / 'lib' / 'inspection_station_contract' / 'generated' / 'inspection_station_action_codes_generated.hpp'
FW_PROFILE_TARGET = REPO_ROOT / 'firmware' / 'stm32_station_platformio' / 'include' / 'inspection_station_action_profile.h'
FW_FEATURES_TARGET = REPO_ROOT / 'firmware' / 'stm32_station_platformio' / 'lib' / 'inspection_station_contract' / 'generated' / 'inspection_station_capability_features_generated.hpp'


def render_action_payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    capability: dict[str, Any] = {'actions': {}}
    governance: dict[str, Any] = {'actions': {}}
    for kind, contract in ACTION_CONTRACTS.items():
        capability['actions'][kind] = {
            'availability': contract.capability.availability,
            'visibility': contract.capability.visibility,
            'execution_policy': contract.capability.execution_policy,
            'runtime_truth': contract.capability.runtime_truth,
            'summary': contract.capability.summary,
            'blocked_reason': contract.capability.blocked_reason,
            'public_catalog': contract.capability.public_catalog,
            'generated_client': contract.capability.generated_client,
            'delivery_class': contract.capability.delivery_class,
        }
        governance['actions'][kind] = {
            'tier': contract.governance.tier,
            'lifecycle': contract.governance.lifecycle,
            'sunsetRelease': contract.governance.sunset_release,
            'promotionCriteria': list(contract.governance.promotion_criteria),
            'requiredVerification': list(contract.governance.required_verification),
            'documentationRefs': list(contract.governance.documentation_refs),
            'uiLabel': contract.governance.ui_label,
            'apiPath': contract.api_path,
            'operationId': contract.operation_id,
        }
    return capability, governance


def render_compatibility_payload() -> dict[str, Any]:
    return {'routes': compatibility_route_catalog_from_registry()}


def _station_profile(name: str = 'stm32_station_default') -> dict[str, Any]:
    profiles = station_capability_profiles()
    profile = profiles.get(name)
    if not isinstance(profile, dict):
        raise ValueError(f'missing station capability profile: {name}')
    return profile


def render_station_expectation_payload() -> dict[str, Any]:
    return {'profiles': station_capability_profiles()}


def render_station_adapter_manifest_payload() -> dict[str, Any]:
    raw_profiles = station_adapter_manifest_profiles()
    capability_profiles = station_capability_profiles()
    manifests: dict[str, Any] = {'adapters': {}}
    for adapter_name, raw_profile in raw_profiles.items():
        capability_profile_name = str(raw_profile.get('capability_profile', '') or '').strip()
        capability_profile = capability_profiles.get(capability_profile_name, {}) if capability_profile_name else {}
        if not isinstance(capability_profile, dict):
            capability_profile = {}
        capability = capability_profile.get('firmware_capability_expectation', {}) if isinstance(capability_profile.get('firmware_capability_expectation', {}), dict) else {}
        base_features = [str(item).strip() for item in capability.get('features', []) if str(item).strip()]
        extra_features = [str(item).strip() for item in raw_profile.get('extra_capabilities', []) if str(item).strip()]
        merged_features = sorted(dict.fromkeys([*base_features, *extra_features]).keys())
        manifests['adapters'][adapter_name] = {
            'capability_profile': capability_profile_name,
            'capabilities': merged_features,
            'runtime_truth': str(raw_profile.get('runtime_truth', 'real') or 'real'),
            'source': str(raw_profile.get('source', 'builtin') or 'builtin'),
        }
    return manifests


def render_station_config_payload() -> dict[str, Any]:
    profile_name = 'stm32_station_default'
    profile = _station_profile(profile_name)
    existing = yaml.safe_load(STATION_STM32_TARGET.read_text(encoding='utf-8')) or {}
    if not isinstance(existing, dict):
        existing = {}
    existing.pop('capability_features', None)
    existing['station_capability_profile'] = profile_name
    existing['adapter_name'] = str(profile.get('adapter_name', 'serial') or 'serial')
    existing['protocol_version'] = str(profile.get('protocol_version', 'v1') or 'v1')
    existing['supported_action_codes'] = [int(item) for item in profile.get('supported_action_codes', [])]
    return existing


def render_fw_codes_header() -> str:
    profile = _station_profile()
    routes = profile.get('firmware_routes', []) if isinstance(profile.get('firmware_routes', []), list) else []
    action_macros: list[str] = []
    codes: list[str] = []
    for index, raw_route in enumerate(routes):
        if not isinstance(raw_route, dict):
            continue
        macro = str(raw_route.get('action_code_macro', '')).strip() or f'INSPECTION_ACTION_CODE_{index + 1}'
        code = int(raw_route.get('action_code', 0))
        action_macros.append(f'#ifndef {macro}\n#define {macro} {code}U\n#endif')
        codes.append(f'static_cast<std::uint8_t>({macro})')
    count = max(len(codes), 1)
    array_body = ',\n        '.join(codes) if codes else '0U'
    return (
        '#pragma once\n\n'
        '#include <array>\n'
        '#include <cstdint>\n\n'
        + '\n\n'.join(action_macros)
        + '\n\nnamespace inspection_station_generated {\n\n'
        f'inline constexpr std::array<std::uint8_t, {count}> supported_action_codes() {{\n'
        '    return {\n'
        f'        {array_body}\n'
        '    };\n'
        '}\n\n'
        '}  // namespace inspection_station_generated\n'
    )


def render_fw_features_header() -> str:
    profile = _station_profile()
    capability = profile.get('firmware_capability_expectation', {}) if isinstance(profile.get('firmware_capability_expectation', {}), dict) else {}
    features = [str(item).strip() for item in capability.get('features', []) if str(item).strip()]
    count = max(len(features), 1)
    feature_body = ',\n        '.join(f'"{item}"' for item in features) if features else '""'
    return (
        '#pragma once\n\n'
        '#include <array>\n\n'
        'namespace inspection_station_generated {\n\n'
        f'inline constexpr std::array<const char*, {count}> capability_features() {{\n'
        '    return {\n'
        f'        {feature_body}\n'
        '    };\n'
        '}\n\n'
        '}  // namespace inspection_station_generated\n'
    )


def render_fw_profile_header() -> str:
    profile = _station_profile()
    routes = profile.get('firmware_routes', []) if isinstance(profile.get('firmware_routes', []), list) else []
    route_lines: list[str] = []
    for raw_route in routes:
        if not isinstance(raw_route, dict):
            continue
        action_code_macro = str(raw_route.get('action_code_macro', '')).strip()
        gpio_port_macro = str(raw_route.get('gpio_port_macro', '')).strip()
        gpio_pin_macro = str(raw_route.get('gpio_pin_macro', '')).strip()
        if not action_code_macro or not gpio_port_macro or not gpio_pin_macro:
            continue
        route_lines.append(f'    {{{action_code_macro}, {gpio_port_macro}, {gpio_pin_macro}}},')
    route_body = '\n'.join(route_lines) if route_lines else '    {0U, nullptr, 0U},'
    return (
        '#pragma once\n\n'
        '// Generated by upper_computer/scripts/sync_action_registry.py.\n'
        '#include <cstddef>\n'
        '#include <cstdint>\n'
        '#include "inspection_station_config.h"\n'
        '#include "../lib/inspection_station_contract/generated/inspection_station_action_codes_generated.hpp"\n\n'
        'struct InspectionStationActionRoute {\n'
        '    std::uint8_t action_code;\n'
        '    GPIO_TypeDef* gpio;\n'
        '    uint16_t pin;\n'
        '};\n\n'
        'constexpr InspectionStationActionRoute INSPECTION_STATION_ACTION_ROUTES[] = {\n'
        f'{route_body}\n'
        '};\n\n'
        'constexpr std::size_t INSPECTION_STATION_ACTION_ROUTE_COUNT =\n'
        '    sizeof(INSPECTION_STATION_ACTION_ROUTES) / sizeof(INSPECTION_STATION_ACTION_ROUTES[0]);\n'
    )


def _render_yaml(payload: dict[str, Any]) -> str:
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def render_all() -> dict[Path, str]:
    capability_payload, governance_payload = render_action_payloads()
    return {
        CAPABILITY_TARGET: _render_yaml(capability_payload),
        GOVERNANCE_TARGET: _render_yaml(governance_payload),
        COMPATIBILITY_TARGET: _render_yaml(render_compatibility_payload()),
        STATION_EXPECTATION_TARGET: _render_yaml(render_station_expectation_payload()),
        STATION_ADAPTER_MANIFEST_TARGET: _render_yaml(render_station_adapter_manifest_payload()),
        STATION_STM32_TARGET: _render_yaml(render_station_config_payload()),
        FW_CODES_TARGET: render_fw_codes_header(),
        FW_FEATURES_TARGET: render_fw_features_header(),
        FW_PROFILE_TARGET: render_fw_profile_header(),
    }


def sync() -> dict[Path, str]:
    outputs = render_all()
    for path, text in outputs.items():
        _write(path, text)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description='Render derived gateway/station governance assets from the action registry.')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = render_all()
    if args.check:
        mismatches = [path for path, text in outputs.items() if not path.exists() or path.read_text(encoding='utf-8') != text]
        if mismatches:
            print('derived action registry assets are out of date; run scripts/sync_action_registry.py', file=sys.stderr)
            for path in mismatches:
                print(f'  - {path.relative_to(REPO_ROOT)}', file=sys.stderr)
            return 1
        return 0
    sync()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
