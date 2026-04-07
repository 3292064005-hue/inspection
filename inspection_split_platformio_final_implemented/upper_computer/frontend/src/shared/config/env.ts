import type { DemoScenario } from '@/shared/types/domain';
import type { GatewayTransportState } from '@/shared/gateway/contracts';

export type GatewayMode = 'mock' | 'http';

function normalizeGatewayMode(value: string | undefined): GatewayMode {
  return value === 'http' ? 'http' : 'mock';
}

function trimSlash(value: string): string {
  return value.replace(/\/$/, '');
}

function toNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function toBoolean(value: string | undefined, fallback: boolean): boolean {
  if (value === undefined) return fallback;
  return ['1', 'true', 'yes', 'on'].includes(value.toLowerCase());
}

function normalizeScenario(value: string | undefined): DemoScenario {
  return value === 'stress' || value === 'throughput' ? value : 'balanced';
}

const gatewayBaseUrl = trimSlash(import.meta.env.VITE_GATEWAY_BASE_URL ?? 'http://127.0.0.1:8080');

export const appEnv = {
  gatewayMode: normalizeGatewayMode(import.meta.env.VITE_GATEWAY_MODE),
  gatewayBaseUrl,
  gatewayWsUrl: import.meta.env.VITE_GATEWAY_WS_URL ?? `${gatewayBaseUrl.replace(/^http/i, 'ws')}/ws/v1`,
  gatewayRequestTimeoutMs: toNumber(import.meta.env.VITE_GATEWAY_REQUEST_TIMEOUT_MS, 8000),
  gatewayRetryBaseMs: toNumber(import.meta.env.VITE_GATEWAY_RETRY_BASE_MS, 1000),
  gatewayRetryMaxMs: toNumber(import.meta.env.VITE_GATEWAY_RETRY_MAX_MS, 15000),
  gatewayMaxReconnectRetries: toNumber(import.meta.env.VITE_GATEWAY_MAX_RECONNECT_RETRIES, 999),
  heartbeatOfflineMs: toNumber(import.meta.env.VITE_HEARTBEAT_OFFLINE_MS, 6000),
  heartbeatDegradedMs: toNumber(import.meta.env.VITE_HEARTBEAT_DEGRADED_MS, 3000),
  demoScenario: normalizeScenario(import.meta.env.VITE_DEMO_SCENARIO),
  maintenanceUnlockMs: toNumber(import.meta.env.VITE_MAINTENANCE_UNLOCK_MS, 10 * 60 * 1000),
  authAutoLogin: toBoolean(import.meta.env.VITE_AUTH_AUTO_LOGIN, false),
  authUsername: import.meta.env.VITE_AUTH_USERNAME ?? '',
  authPassword: import.meta.env.VITE_AUTH_PASSWORD ?? '',
};

export function transportStateToConnectionState(state: GatewayTransportState): 'CONNECTING' | 'ONLINE' | 'RECONNECTING' | 'OFFLINE' | 'ERROR' {
  switch (state) {
    case 'CONNECTING':
      return 'CONNECTING';
    case 'ONLINE':
      return 'ONLINE';
    case 'RECONNECTING':
      return 'RECONNECTING';
    case 'ERROR':
      return 'ERROR';
    case 'OFFLINE':
    case 'IDLE':
    default:
      return 'OFFLINE';
  }
}
