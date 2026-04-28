#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
for package_dir in sorted((ROOT / 'src').iterdir()):
    if package_dir.is_dir():
        sys.path.insert(0, str(package_dir))

from inspection_hmi_gateway.action_contract import generated_client_excluded_operation_ids
from inspection_hmi_gateway.server.main import create_app

OPENAPI_TARGET = ROOT / 'frontend' / 'openapi' / 'inspection_gateway_openapi.json'
ACTION_TS_TARGET = ROOT / 'frontend' / 'src' / 'shared' / 'gateway' / 'generated' / 'actionApi.ts'
PUBLIC_TS_TARGET = ROOT / 'frontend' / 'src' / 'shared' / 'gateway' / 'generated' / 'gatewayApi.ts'
ACTION_PREFIXES = ('/api/v1/actions/',)
PUBLIC_PREFIXES = (
    '/api/v1/auth/',
    '/api/v1/station/',
    '/api/v1/results',
    '/api/v1/recipes',
    '/api/v1/diagnostics',
    '/api/v1/audit',
)
EXCLUDED_GENERATED_CLIENT_OPERATION_IDS = generated_client_excluded_operation_ids()
PUBLIC_EXCLUDED_OPERATION_IDS = {'activateRecipeDirect'}


class _SchemaRuntime:
    def __init__(self) -> None:
        self.event_bus = None
        self.node = None

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def health(self) -> dict[str, object]:
        return {'runtimeReady': False, 'mode': 'schema_export'}


def _export_openapi(target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        users_path = tmp_root / 'users.yaml'
        users_path.write_text(yaml.safe_dump({'users': {}}, allow_unicode=True, sort_keys=False), encoding='utf-8')
        app = create_app(
            log_root=str(tmp_root / 'logs'),
            recipe_root=str(tmp_root / 'recipes'),
            frontend_dist=str(tmp_root / 'frontend_dist'),
            users_path=str(users_path),
            runtime_factory=_SchemaRuntime,
            require_frontend_dist=False,
        )
        payload = app.openapi()
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return payload


def _schema_ref_name(ref: str) -> str:
    return str(ref).rsplit('/', 1)[-1]


def _to_pascal(name: str) -> str:
    parts = re.split(r'[^0-9A-Za-z]+', str(name or '').strip())
    return ''.join(part[:1].upper() + part[1:] for part in parts if part)


def _ts_type(schema: dict[str, Any], components: dict[str, Any]) -> str:
    if '$ref' in schema:
        return _schema_ref_name(str(schema['$ref']))
    if 'enum' in schema:
        values = schema.get('enum') or []
        return ' | '.join(json.dumps(value, ensure_ascii=False) for value in values) or 'string'
    if 'anyOf' in schema:
        parts = [_ts_type(item, components) for item in schema.get('anyOf', []) if item.get('type') != 'null']
        return ' | '.join(dict.fromkeys(parts)) or 'unknown'
    if 'oneOf' in schema:
        parts = [_ts_type(item, components) for item in schema.get('oneOf', [])]
        return ' | '.join(dict.fromkeys(parts)) or 'unknown'
    schema_type = schema.get('type')
    if schema_type == 'string':
        return 'string'
    if schema_type in {'integer', 'number'}:
        return 'number'
    if schema_type == 'boolean':
        return 'boolean'
    if schema_type == 'array':
        return f"Array<{_ts_type(schema.get('items', {}), components)}>"
    if schema_type == 'object' or 'properties' in schema:
        properties = schema.get('properties', {}) or {}
        required = {str(item) for item in schema.get('required', [])}
        if not properties:
            additional = schema.get('additionalProperties')
            if isinstance(additional, dict):
                return f"Record<string, {_ts_type(additional, components)}>"
            if additional is False:
                return 'Record<string, never>'
            return 'Record<string, unknown>'
        parts: list[str] = ['{']
        for key in sorted(properties):
            value = properties[key]
            optional = '?' if key not in required else ''
            parts.append(f"  {key}{optional}: {_ts_type(value, components)};")
        additional = schema.get('additionalProperties')
        if isinstance(additional, dict):
            parts.append(f"  [key: string]: {_ts_type(additional, components)};")
        parts.append('}')
        return '\n'.join(parts)
    return 'unknown'


def _emit_schema(name: str, schema: dict[str, Any], components: dict[str, Any], emitted: dict[str, str]) -> None:
    if name in emitted:
        return
    if '$ref' in schema:
        ref_name = _schema_ref_name(str(schema['$ref']))
        component = components.get(ref_name, {})
        _emit_schema(ref_name, component, components, emitted)
        return
    for value in (schema.get('properties', {}) or {}).values():
        if isinstance(value, dict) and '$ref' in value:
            ref_name = _schema_ref_name(str(value['$ref']))
            _emit_schema(ref_name, components.get(ref_name, {}), components, emitted)
        elif isinstance(value, dict) and value.get('items', {}).get('$ref'):
            ref_name = _schema_ref_name(str(value['items']['$ref']))
            _emit_schema(ref_name, components.get(ref_name, {}), components, emitted)
    body = _ts_type(schema, components)
    if body.startswith('{'):
        emitted[name] = f"export interface {name} {body}\n"
    else:
        emitted[name] = f"export type {name} = {body};\n"


def _request_schema_name(operation_id: str, schema: dict[str, Any]) -> str:
    if '$ref' in schema:
        return _schema_ref_name(str(schema['$ref']))
    return f"{_to_pascal(operation_id)}Request"


def _selected_operations(openapi_payload: dict[str, Any], *, prefixes: tuple[str, ...], excluded_operation_ids: set[str] | None = None) -> list[dict[str, Any]]:
    excluded = excluded_operation_ids or set()
    paths = openapi_payload.get('paths', {}) or {}
    operations: list[dict[str, Any]] = []
    for path, methods in sorted(paths.items()):
        if not any(path.startswith(prefix) for prefix in prefixes):
            continue
        if not isinstance(methods, dict):
            continue
        for method, operation in sorted(methods.items()):
            if method.lower() not in {'get', 'post'} or not isinstance(operation, dict):
                continue
            operation_id = str(operation.get('operationId', '')).strip()
            if not operation_id or operation_id in excluded:
                continue
            request_schema_name = ''
            request_schema_payload: dict[str, Any] = {}
            request_body = operation.get('requestBody', {}) or {}
            content = request_body.get('content', {}) if isinstance(request_body, dict) else {}
            json_body = content.get('application/json', {}) if isinstance(content, dict) else {}
            schema = json_body.get('schema', {}) if isinstance(json_body, dict) else {}
            if isinstance(schema, dict) and schema:
                request_schema_name = _request_schema_name(operation_id, schema)
                request_schema_payload = schema
            params = []
            for param in operation.get('parameters', []) or []:
                if not isinstance(param, dict):
                    continue
                params.append({
                    'name': str(param.get('name', '')),
                    'in': str(param.get('in', 'query')),
                    'required': bool(param.get('required', False)),
                    'schema': param.get('schema', {}) if isinstance(param.get('schema', {}), dict) else {},
                })
            operations.append({
                'operationId': operation_id,
                'method': method.upper(),
                'path': path,
                'requestSchema': request_schema_name,
                'requestSchemaPayload': request_schema_payload,
                'parameters': params,
            })
    return operations


def _emit_param_interface(operation: dict[str, Any], components: dict[str, Any], emitted_lines: list[str]) -> str:
    params = operation.get('parameters', []) or []
    if not params:
        return ''
    name = f"{_to_pascal(operation['operationId'])}Params"
    emitted_lines.append(f"export interface {name} {{")
    for param in params:
        optional = '?' if not param['required'] else ''
        emitted_lines.append(f"  {param['name']}{optional}: {_ts_type(param['schema'], components)};")
    emitted_lines.append('}')
    emitted_lines.append('')
    return name


def _generate_ts(
    openapi_payload: dict[str, Any],
    *,
    prefixes: tuple[str, ...],
    target: Path,
    route_var_name: str,
    operation_type_name: str,
    request_adapter_name: str,
    client_factory_name: str,
    excluded_operation_ids: set[str] | None = None,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    components = (openapi_payload.get('components', {}) or {}).get('schemas', {}) or {}
    operations = _selected_operations(openapi_payload, prefixes=prefixes, excluded_operation_ids=excluded_operation_ids)
    emitted_schemas: dict[str, str] = {}
    for operation in operations:
        schema_name = operation['requestSchema']
        schema_payload = operation['requestSchemaPayload']
        if schema_name and schema_payload:
            if '$ref' in schema_payload:
                _emit_schema(schema_name, components.get(schema_name, {}), components, emitted_schemas)
            else:
                _emit_schema(schema_name, schema_payload, components, emitted_schemas)

    lines = ['// Generated by scripts/sync_gateway_contracts.py. Do not edit by hand.', '']
    for name in sorted(emitted_schemas):
        lines.append(emitted_schemas[name].rstrip())
        lines.append('')

    param_names: dict[str, str] = {}
    for operation in operations:
        param_names[operation['operationId']] = _emit_param_interface(operation, components, lines)

    lines.append(f'export const {route_var_name} = {{')
    for operation in operations:
        schema_ts = operation['requestSchema'] or 'void'
        lines.append(
            f"  {operation['operationId']}: {{ method: '{operation['method']}' as const, path: '{operation['path']}' as const, requestSchema: '{schema_ts}' as const }},"
        )
    lines.append('} as const;')
    lines.append('')
    lines.append(f'export type {operation_type_name} = keyof typeof {route_var_name};')
    lines.append("export type GatewayHttpMethod = 'GET' | 'POST';")
    lines.append('')
    lines.append(f'export interface {request_adapter_name} {{')
    lines.append('  request<T>(path: string, init: { method: GatewayHttpMethod; query?: Record<string, unknown>; body?: unknown }): Promise<T>;')
    lines.append('}')
    lines.append('')
    lines.append('export function renderGatewayPath(pathTemplate: string, params: Record<string, unknown> = {}): string {')
    lines.append("  return pathTemplate.replace(/\\{([^}]+)\\}/g, (_, key: string) => encodeURIComponent(String(params[key] ?? '')));")
    lines.append('}')
    lines.append('')
    lines.append('export function appendGatewayQuery(path: string, query?: Record<string, unknown>): string {')
    lines.append('  if (!query) return path;')
    lines.append('  const params = new URLSearchParams();')
    lines.append('  for (const [key, value] of Object.entries(query)) {')
    lines.append("    if (value === undefined || value === null || value === '') continue;")
    lines.append('    if (Array.isArray(value)) {')
    lines.append('      value.forEach((item) => params.append(key, String(item)));')
    lines.append('      continue;')
    lines.append('    }')
    lines.append('    params.append(key, String(value));')
    lines.append('  }')
    lines.append('  const qs = params.toString();')
    lines.append('  if (!qs) return path;')
    lines.append("  return `${path}${path.includes('?') ? '&' : '?'}${qs}`;")
    lines.append('}')
    lines.append('')
    lines.append(f'export function {client_factory_name}(adapter: {request_adapter_name}) {{')
    lines.append('  return {')
    for operation in operations:
        op_id = operation['operationId']
        route_ref = f'{route_var_name}.{op_id}'
        path_params = [p for p in operation['parameters'] if p['in'] == 'path']
        query_params = [p for p in operation['parameters'] if p['in'] == 'query']
        params_name = param_names.get(op_id) or ''
        schema_name = operation['requestSchema']
        if params_name and schema_name:
            signature = f'params: {params_name}, payload: {schema_name}'
            query_expr = '{' + ', '.join(f"{p['name']}: params.{p['name']}" for p in query_params) + '}' if query_params else 'undefined'
            lines.append(f'    async {op_id}<T>({signature}): Promise<T> {{')
            lines.append(f'      const path = renderGatewayPath({route_ref}.path, params as Record<string, unknown>);')
            lines.append(f'      return adapter.request<T>(path, {{ method: {route_ref}.method, query: {query_expr}, body: payload }});')
        elif params_name:
            signature = f'params: {params_name}'
            query_expr = '{' + ', '.join(f"{p['name']}: params.{p['name']}" for p in query_params) + '}' if query_params else 'undefined'
            lines.append(f'    async {op_id}<T>({signature}): Promise<T> {{')
            if path_params:
                path_expr = '{' + ', '.join(f"{p['name']}: params.{p['name']}" for p in path_params) + '}'
                lines.append(f'      const path = renderGatewayPath({route_ref}.path, {path_expr});')
            else:
                lines.append(f'      const path = {route_ref}.path;')
            lines.append(f'      return adapter.request<T>(path, {{ method: {route_ref}.method, query: {query_expr}, body: undefined }});')
        elif schema_name:
            signature = f'payload: {schema_name}'
            lines.append(f'    async {op_id}<T>({signature}): Promise<T> {{')
            lines.append(f'      return adapter.request<T>({route_ref}.path, {{ method: {route_ref}.method, body: payload }});')
        else:
            lines.append(f'    async {op_id}<T>(): Promise<T> {{')
            lines.append(f'      return adapter.request<T>({route_ref}.path, {{ method: {route_ref}.method, body: undefined }});')
        lines.append('    },')
    lines.append('  };')
    lines.append('}')

    text = '\n'.join(lines).rstrip() + '\n'
    target.write_text(text, encoding='utf-8')
    return text


def sync(openapi_target: Path = OPENAPI_TARGET, action_ts_target: Path = ACTION_TS_TARGET, public_ts_target: Path = PUBLIC_TS_TARGET) -> tuple[str, str, str]:
    payload = _export_openapi(openapi_target)
    action_ts_text = _generate_ts(
        payload,
        prefixes=ACTION_PREFIXES,
        target=action_ts_target,
        route_var_name='gatewayActionRoutes',
        operation_type_name='GatewayActionOperationId',
        request_adapter_name='GatewayActionRequestAdapter',
        client_factory_name='createGatewayActionClient',
        excluded_operation_ids=EXCLUDED_GENERATED_CLIENT_OPERATION_IDS,
    )
    public_ts_text = _generate_ts(
        payload,
        prefixes=PUBLIC_PREFIXES,
        target=public_ts_target,
        route_var_name='gatewayApiRoutes',
        operation_type_name='GatewayApiOperationId',
        request_adapter_name='GatewayApiRequestAdapter',
        client_factory_name='createGatewayApiClient',
        excluded_operation_ids=PUBLIC_EXCLUDED_OPERATION_IDS,
    )
    return openapi_target.read_text(encoding='utf-8'), action_ts_text, public_ts_text


def main() -> int:
    parser = argparse.ArgumentParser(description='Export gateway OpenAPI and generate frontend gateway contracts.')
    parser.add_argument('--openapi-target', default=str(OPENAPI_TARGET))
    parser.add_argument('--action-ts-target', default=str(ACTION_TS_TARGET))
    parser.add_argument('--public-ts-target', default=str(PUBLIC_TS_TARGET))
    args = parser.parse_args()
    sync(Path(args.openapi_target), Path(args.action_ts_target), Path(args.public_ts_target))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
