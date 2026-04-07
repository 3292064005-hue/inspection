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
        let detail = '';
        try {
          const payload = (await response.json()) as { detail?: string; message?: string };
          detail = payload.detail ?? payload.message ?? '';
        } catch {
          detail = '';
        }
        throw new GatewayError('HTTP', detail || `HTTP ${response.status} ${response.statusText}`);
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
