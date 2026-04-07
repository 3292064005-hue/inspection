import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockCtor = vi.fn();
const httpCtor = vi.fn();
const safeCtor = vi.fn((inner: any) => ({ wrapped: inner }));

vi.mock('@/shared/config/env', () => ({ appEnv: { gatewayMode: 'mock' } }));
vi.mock('@/mocks/mockGateway', () => ({ MockGateway: class { constructor() { mockCtor(); } } }));
vi.mock('@/shared/gateway/httpGateway', () => ({ HttpGateway: class { constructor() { httpCtor(); } } }));
vi.mock('@/shared/gateway/safeGateway', () => ({ SafeGateway: class { constructor(inner: any) { return safeCtor(inner) as any; } } }));

describe('gateway service singleton', () => {
  beforeEach(async () => {
    vi.resetModules();
    mockCtor.mockClear();
    httpCtor.mockClear();
    safeCtor.mockClear();
  });

  it('returns a memoized safe mock gateway in mock mode', async () => {
    const { getGateway } = await import('@/shared/gateway/service');
    const first = getGateway();
    const second = getGateway();
    expect(first).toBe(second);
    expect(mockCtor).toHaveBeenCalledTimes(1);
    expect(httpCtor).not.toHaveBeenCalled();
    expect(safeCtor).toHaveBeenCalledTimes(1);
  });
});
