import { afterEach, describe, expect, it, vi } from 'vitest';
import { HttpClient } from '@/shared/gateway/transport/httpClient';
import { GatewayError } from '@/shared/gateway/errors';

describe('HttpClient', () => {
  afterEach(() => vi.restoreAllMocks());

  it('always sends credentialed JSON requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({ success: true }) });
    vi.stubGlobal('fetch', fetchMock);
    const client = new HttpClient('http://gateway');
    await client.request('/api/v1/health', { method: 'POST', body: JSON.stringify({ ok: true }) });
    expect(fetchMock).toHaveBeenCalledWith('http://gateway/api/v1/health', expect.objectContaining({ credentials: 'include', method: 'POST', headers: expect.objectContaining({ Accept: 'application/json', 'Content-Type': 'application/json' }) }));
  });

  it('maps aborted requests to TIMEOUT gateway errors', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn((_url, init?: RequestInit) => new Promise((_resolve, reject) => { init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))); }));
    vi.stubGlobal('fetch', fetchMock);
    const client = new HttpClient('http://gateway', { timeoutMs: 5 });
    const pending = expect(client.request('/slow')).rejects.toMatchObject({ code: 'TIMEOUT' } satisfies Partial<GatewayError>);
    await vi.advanceTimersByTimeAsync(10);
    await pending;
    vi.useRealTimers();
  });

  it('preserves structured detail for non-2xx responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      headers: { get: () => 'application/json' },
      json: async () => ({ error: { code: 'READ_MODEL_UNAVAILABLE', detail: { message: 'projection unavailable', readModelStatus: { degraded: true, repairRequired: true } } } }),
      text: async () => '',
    });
    vi.stubGlobal('fetch', fetchMock);
    const client = new HttpClient('http://gateway');
    await expect(client.request('/api/v1/results')).rejects.toMatchObject({
      code: 'HTTP',
      message: 'projection unavailable',
      detail: { message: 'projection unavailable', readModelStatus: { degraded: true, repairRequired: true } },
    } satisfies Partial<GatewayError>);
  });
});
