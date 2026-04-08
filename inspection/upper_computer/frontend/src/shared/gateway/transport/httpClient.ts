import { appEnv } from '@/shared/config/env';
import { GatewayError } from '@/shared/gateway/errors';

export interface HttpClientOptions {
  timeoutMs?: number;
}

export class HttpClient {
  constructor(private readonly baseUrl: string, private readonly options: HttpClientOptions = {}) {}

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timeoutMs = this.options.timeoutMs ?? appEnv.gatewayRequestTimeoutMs;
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          ...(init.body ? { 'Content-Type': 'application/json' } : {}),
          ...(init.headers ?? {}),
        },
        signal: controller.signal,
      });

      if (!response.ok) {
        let detail: unknown = undefined;
        let message = '';
        try {
          const payload = (await response.json()) as {
            message?: string;
            detail?: unknown;
            error?: { detail?: unknown; code?: string };
          };
          detail = payload.error?.detail ?? payload.detail;
          if (typeof detail === 'object' && detail !== null && typeof (detail as { message?: unknown }).message === 'string') {
            message = String((detail as { message?: unknown }).message ?? '');
          }
          if (!message && typeof payload.message === 'string' && !payload.message.trim().startsWith('{')) {
            message = payload.message;
          }
        } catch {
          detail = undefined;
          message = '';
        }
        throw new GatewayError('HTTP', message || `HTTP ${response.status} ${response.statusText}`, detail);
      }

      if (response.status === 204) return undefined as T;
      const contentType = response.headers.get('content-type') ?? '';
      if (!contentType.includes('application/json')) {
        return { url: await response.text() } as T;
      }
      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new GatewayError('TIMEOUT', `Gateway request timeout: ${path}`);
      }
      if (error instanceof GatewayError) {
        throw error;
      }
      const message = error instanceof Error ? error.message : `Gateway request failed: ${path}`;
      throw new GatewayError('NETWORK', message);
    } finally {
      window.clearTimeout(timer);
    }
  }
}
