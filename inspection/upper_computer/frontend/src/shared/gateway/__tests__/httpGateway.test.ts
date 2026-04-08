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
      .mockResolvedValueOnce({ data: { batchId: 'BATCH-1', activeRecipeId: 'recipe-1', phase: 'READY' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-start-1', status: 'QUEUED' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-start-1', status: 'COMPLETED', result: { started: true } } })
      .mockResolvedValueOnce({ data: { jobId: 'job-stop-1', status: 'QUEUED' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-stop-1', status: 'COMPLETED', result: { stopped: true } } })
      .mockResolvedValueOnce({ data: { jobId: 'job-reset-1', status: 'QUEUED' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-reset-1', status: 'COMPLETED', result: { reset: true } } })
      .mockResolvedValueOnce({ data: { jobId: 'job-maint-1', status: 'QUEUED' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-maint-1', status: 'RUNNING' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-maint-1', status: 'COMPLETED', result: { phase: 'READY', maintenance: { requested: true, enabled: false, transitionState: 'ENTERING', supervisorMode: 'AUTO' } } } })
      .mockResolvedValueOnce({ data: { jobId: 'job-batch-1', status: 'QUEUED' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-batch-1', status: 'COMPLETED', result: { batchId: 'BATCH-NEW' } } })
      .mockResolvedValueOnce({ data: { id: 'result-1' } })
      .mockResolvedValueOnce({ data: { mode: 'HOT', degraded: false, repairRequired: false, projectionAvailable: true, fallbackEnabled: false, querySurface: 'projection', maintenanceState: 'IDLE', repairRunning: false, lastError: '', lastRepairAt: '', lastRepairReason: '', sourceSyncToken: 's1', materializedSyncToken: 'm1' } })
      .mockResolvedValueOnce({ data: { mode: 'HOT', degraded: false, repairRequired: false, projectionAvailable: true, fallbackEnabled: false, querySurface: 'projection', maintenanceState: 'IDLE', repairRunning: false, lastError: '', lastRepairAt: '2026-04-01T12:00:00Z', lastRepairReason: '', sourceSyncToken: 's2', materializedSyncToken: 'm2' } })
      .mockResolvedValueOnce({ data: [{ id: 'recipe-1' }] })
      .mockResolvedValueOnce({ data: { id: 'recipe-1', name: '配方 1' } })
      .mockResolvedValueOnce({ data: { activation: { recipeId: 'recipe-1' } } })
      .mockResolvedValueOnce({ data: [{ id: 'diag-1' }] })
      .mockResolvedValueOnce({ data: { jobId: 'job-diag-1', status: 'QUEUED' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-diag-1', status: 'RUNNING' } })
      .mockResolvedValueOnce({ data: { jobId: 'job-diag-1', status: 'COMPLETED', result: { action: 'CAPTURE_FRAME', success: true } } })
      .mockResolvedValueOnce({ data: [{ id: 1, action: 'LOGIN' }] });

    const gateway = new HttpGateway();
    expect(await gateway.getSession?.()).toEqual({ username: 'operator', displayName: '操作员', role: 'operator' });
    await gateway.logout?.();
    expect(await gateway.getStationSnapshot()).toEqual({ batchId: 'BATCH-1', phase: 'READY' });
    expect(await gateway.getCountStats()).toEqual({ total: 1, ok: 1, ng: 0, recheck: 0, yieldRate: 1 });
    await gateway.startStation();
    await gateway.stopStation();
    await gateway.resetFault();
    expect(await gateway.setMaintenanceMode(true)).toEqual({ phase: 'READY', maintenance: { requested: true, enabled: false, transitionState: 'ENTERING', supervisorMode: 'AUTO' } });
    expect(await gateway.newBatch()).toBe('BATCH-NEW');
    expect(await gateway.getResultDetail?.('result-1')).toEqual({ id: 'result-1' });
    expect(await gateway.getReadModelStatus?.()).toMatchObject({ mode: 'HOT', degraded: false });
    expect(await gateway.repairReadModel?.()).toMatchObject({ mode: 'HOT', lastRepairAt: '2026-04-01T12:00:00Z' });
    expect(await gateway.getRecipes()).toEqual([{ id: 'recipe-1' }]);
    expect(await gateway.saveRecipe({ id: 'recipe-1' } as any)).toEqual({ id: 'recipe-1', name: '配方 1' });
    await gateway.activateRecipe('recipe-1');
    expect(await gateway.getDiagnostics()).toEqual([{ id: 'diag-1' }]);
    expect(await gateway.runDiagnosticAction('CAPTURE_FRAME' as any)).toEqual({ action: 'CAPTURE_FRAME', success: true });
    expect(await gateway.getAuditEntries?.(10, 5)).toEqual([{ id: 1, action: 'LOGIN' }]);
    expect(gateway.getCapabilities?.().demoScenarioControl.supported).toBe(false);
    await expect(gateway.configureDemoScenario?.('balanced' as any)).rejects.toThrow('demo_scenario_control_unsupported_in_http_gateway');

    expect(requestMock).toHaveBeenNthCalledWith(1, '/api/v1/auth/session');
    expect(requestMock).toHaveBeenNthCalledWith(12, '/api/v1/actions/set-maintenance-mode', expect.objectContaining({ method: 'POST' }));
    expect(requestMock).toHaveBeenNthCalledWith(13, '/api/v1/actions/jobs/job-maint-1');
    expect(requestMock).toHaveBeenNthCalledWith(14, '/api/v1/actions/jobs/job-maint-1');
    expect(requestMock).toHaveBeenNthCalledWith(15, '/api/v1/actions/create-batch', expect.objectContaining({ method: 'POST' }));
    expect(requestMock).toHaveBeenNthCalledWith(16, '/api/v1/actions/jobs/job-batch-1');
    expect(requestMock).toHaveBeenNthCalledWith(17, '/api/v1/results/result-1');
    expect(requestMock).toHaveBeenCalledWith('/api/v1/actions/start-batch', expect.objectContaining({ method: 'POST', body: JSON.stringify({ recipeId: 'recipe-1', batchId: 'BATCH-1' }) }));
    expect(requestMock).toHaveBeenCalledWith('/api/v1/actions/stop-station', expect.objectContaining({ method: 'POST' }));
    expect(requestMock).toHaveBeenCalledWith('/api/v1/actions/reset-station', expect.objectContaining({ method: 'POST' }));
    expect(requestMock).toHaveBeenCalledWith('/api/v1/actions/diagnostics/capture-frame', expect.objectContaining({ method: 'POST' }));
    expect(requestMock).toHaveBeenCalledWith('/api/v1/actions/jobs/job-diag-1');
    expect(requestMock).toHaveBeenLastCalledWith('/api/v1/audit?limit=10&offset=5');
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
