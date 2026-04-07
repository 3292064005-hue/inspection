import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { GatewayStatusSnapshot } from '@/shared/gateway/contracts';

const requestMock = vi.fn();
const connectMock = vi.fn(async (_ticket?: string) => undefined);
const closeMock = vi.fn();
let capturedSocketOptions: any;

vi.mock('@/shared/config/env', () => ({
  appEnv: {
    gatewayBaseUrl: 'http://gateway.local',
    gatewayRequestTimeoutMs: 5000,
    gatewayWsUrl: 'ws://gateway.local/ws/v1',
  },
}));

vi.mock('@/shared/gateway/transport/httpClient', () => ({
  HttpClient: class {
    request = requestMock;
  },
}));

vi.mock('@/shared/gateway/transport/websocketClient', () => ({
  GatewayWebSocketClient: class {
    constructor(options: any) {
      capturedSocketOptions = options;
    }

    connect = connectMock;
    close = closeMock;
  },
}));

import { HttpGateway } from '@/shared/gateway/httpGateway';

describe('HttpGateway', () => {
  beforeEach(() => {
    requestMock.mockReset();
    connectMock.mockClear();
    closeMock.mockClear();
    capturedSocketOptions = undefined;
  });

  it('connects with a ws ticket and forwards socket events/status', async () => {
    requestMock.mockResolvedValueOnce({ data: { ticket: 'ws-ticket-1', expiresAt: '2026-04-01T00:00:00Z' } });
    const gateway = new HttpGateway();

    const statusEvents: GatewayStatusSnapshot[] = [];
    const unsubscribe = gateway.onStatusChange((status) => statusEvents.push(status));
    const stationHandler = vi.fn();
    gateway.on('station.state.updated', stationHandler);

    await gateway.connect();
    expect(connectMock).toHaveBeenCalledWith('ws-ticket-1');

    capturedSocketOptions.onStatus({
      mode: 'http',
      transport: 'ONLINE',
      httpOk: false,
      wsOk: true,
      retryCount: 0,
      lastError: '',
      updatedAt: 'ignored',
    });
    capturedSocketOptions.onMessage({ event: 'station.state.updated', payload: { batchId: 'B1' } });

    expect(stationHandler).toHaveBeenCalledWith({ batchId: 'B1' });
    expect(gateway.getStatus?.().transport).toBe('ONLINE');
    expect(statusEvents.length).toBeGreaterThan(1);

    gateway.off('station.state.updated', stationHandler);
    capturedSocketOptions.onMessage({ event: 'station.state.updated', payload: { batchId: 'B2' } });
    expect(stationHandler).toHaveBeenCalledTimes(1);

    unsubscribe();
    gateway.disconnect();
    expect(closeMock).toHaveBeenCalled();
  });


  it('covers session, station, recipe, diagnostics and audit helpers', async () => {
    requestMock
      .mockResolvedValueOnce({ data: { username: 'operator', displayName: '操作员', role: 'operator' } })
      .mockResolvedValueOnce({ data: { loggedOut: true } })
      .mockResolvedValueOnce({ data: { batchId: 'BATCH-1', phase: 'READY' } })
      .mockResolvedValueOnce({ data: { total: 1, ok: 1, ng: 0, recheck: 0, yieldRate: 1 } })
      .mockResolvedValueOnce({ data: { success: true } })
      .mockResolvedValueOnce({ data: { success: true } })
      .mockResolvedValueOnce({ data: { success: true } })
      .mockResolvedValueOnce({ data: { batchId: 'BATCH-NEW' } })
      .mockResolvedValueOnce({ data: { id: 'result-1' } })
      .mockResolvedValueOnce({ data: [{ id: 'recipe-1' }] })
      .mockResolvedValueOnce({ data: { id: 'recipe-1', name: '配方 1' } })
      .mockResolvedValueOnce({ data: { activation: { recipeId: 'recipe-1' } } })
      .mockResolvedValueOnce({ data: [{ id: 'diag-1' }] })
      .mockResolvedValueOnce({ data: { action: 'CAPTURE_FRAME', success: true } })
      .mockResolvedValueOnce({ data: [{ id: 1, action: 'LOGIN' }] });

    const gateway = new HttpGateway();
    expect(await gateway.getSession?.()).toEqual({ username: 'operator', displayName: '操作员', role: 'operator' });
    await gateway.logout?.();
    expect(await gateway.getStationSnapshot()).toEqual({ batchId: 'BATCH-1', phase: 'READY' });
    expect(await gateway.getCountStats()).toEqual({ total: 1, ok: 1, ng: 0, recheck: 0, yieldRate: 1 });
    await gateway.startStation();
    await gateway.stopStation();
    await gateway.resetFault();
    expect(await gateway.newBatch()).toBe('BATCH-NEW');
    expect(await gateway.getResultDetail?.('result-1')).toEqual({ id: 'result-1' });
    expect(await gateway.getRecipes()).toEqual([{ id: 'recipe-1' }]);
    expect(await gateway.saveRecipe({ id: 'recipe-1' } as any)).toEqual({ id: 'recipe-1', name: '配方 1' });
    await gateway.activateRecipe('recipe-1');
    expect(await gateway.getDiagnostics()).toEqual([{ id: 'diag-1' }]);
    expect(await gateway.runDiagnosticAction('CAPTURE_FRAME' as any)).toEqual({ action: 'CAPTURE_FRAME', success: true });
    expect(await gateway.getAuditEntries?.(10, 5)).toEqual([{ id: 1, action: 'LOGIN' }]);
    await expect(gateway.configureDemoScenario?.('balanced' as any)).resolves.toBeUndefined();

    expect(requestMock).toHaveBeenNthCalledWith(1, '/api/v1/auth/session');
    expect(requestMock).toHaveBeenNthCalledWith(8, '/api/v1/station/new-batch', expect.objectContaining({ method: 'POST' }));
    expect(requestMock).toHaveBeenNthCalledWith(9, '/api/v1/results/result-1');
    expect(requestMock).toHaveBeenNthCalledWith(15, '/api/v1/audit?limit=10&offset=5');
  });

  it('marks http healthy for login, result queries and batch exports', async () => {
    requestMock
      .mockResolvedValueOnce({ data: { username: 'operator', displayName: '操作员', role: 'operator' } })
      .mockResolvedValueOnce({ data: [{ id: 'r1' }] })
      .mockResolvedValueOnce({ data: { exportUrl: '/artifacts/exports/batch.zip', jobId: 'job-1' } });

    const gateway = new HttpGateway();

    const session = await gateway.login?.('operator', 'secret');
    const results = await gateway.getResults({ batchId: 'BATCH-1', decision: 'NG' });
    const exported = await gateway.exportBatch('BATCH-1');

    expect(session?.role).toBe('operator');
    expect(results).toEqual([{ id: 'r1' }]);
    expect(exported).toEqual({ url: '/artifacts/exports/batch.zip', jobId: 'job-1' });
    expect(requestMock).toHaveBeenNthCalledWith(1, '/api/v1/auth/login', expect.objectContaining({ method: 'POST' }));
    expect(requestMock).toHaveBeenNthCalledWith(2, '/api/v1/results?batchId=BATCH-1&decision=NG');
    expect(requestMock).toHaveBeenNthCalledWith(3, '/api/v1/exports/BATCH-1', expect.objectContaining({ method: 'POST' }));
    expect(gateway.getStatus?.().httpOk).toBe(true);
  });
});
