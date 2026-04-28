from __future__ import annotations

from pathlib import Path


def test_generated_gateway_api_requests_are_strongly_typed() -> None:
    generated = (Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'shared' / 'gateway' / 'generated' / 'gatewayApi.ts').read_text(encoding='utf-8')
    assert 'export interface SaveRecipeRequest {' in generated
    assert 'export interface LoginGatewaySessionRequest {' in generated
    assert 'export interface ChangeGatewayPasswordRequest {' in generated
    assert 'export type SaveRecipeRequest = Record<string, unknown>;' not in generated
    assert 'export type LoginGatewaySessionRequest = Record<string, unknown>;' not in generated
    assert 'export type ChangeGatewayPasswordRequest = Record<string, unknown>;' not in generated


def test_http_gateway_uses_explicit_payload_mapping_instead_of_request_casts() -> None:
    http_gateway = (Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'shared' / 'gateway' / 'httpGateway.ts').read_text(encoding='utf-8')
    assert 'toSaveRecipeRequest(recipe)' in http_gateway
    assert 'as unknown as SaveRecipeRequest' not in http_gateway
