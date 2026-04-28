import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { GatewayStatusSnapshot, HmiGateway } from '@/shared/gateway/contracts';
import type { InspectionResult } from '@/shared/types/domain';

let statusListener: ((status: GatewayStatusSnapshot) => void) | null = null;

const gatewayStub: Partial<HmiGateway> = {
  connect: vi.fn(async () => undefined),
  disconnect: vi.fn(),
  on: vi.fn(),
  off: vi.fn(),
  onStatusChange: vi.fn((handler) => {
    statusListener = handler as (status: GatewayStatusSnapshot) => void;
    return () => {
      statusListener = null;
    };
  }),
  getStationSnapshot: vi.fn(),
  getCountStats: vi.fn(),
  getRecipes: vi.fn(),
  getResults: vi.fn(),
};

vi.mock('@/shared/config/env', () => ({
  appEnv: { gatewayMode: 'mock', gatewayBaseUrl: 'http://gateway.local', authAutoLogin: false, authUsername: '', authPassword: '' },
  transportStateToConnectionState: (state: string) => (state === 'ONLINE' ? 'ONLINE' : 'OFFLINE'),
}));

vi.mock('@/shared/gateway/service', () => ({ getGateway: () => gatewayStub }));

const sampleResult: InspectionResult = {
  id: 'result-bootstrap-1',
  timestamp: '2026-04-01T12:00:00.000Z',
  batchId: 'BATCH-001',
  recipeId: 'recipe-a',
  recipeName: 'Recipe A',
  decision: 'OK',
  defectType: '',
  qrText: 'QR-001',
  cycleMs: 980,
  traceId: 'trace-1',
  artifactCount: 1,
  explanation: ['启动补数'],
  breakdown: { feedingMs: 100, captureMs: 120, analyzeMs: 300, sortingMs: 200, totalMs: 980 },
};

describe('useHmiBootstrap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    statusListener = null;
    setActivePinia(createPinia());
    (gatewayStub.getStationSnapshot as ReturnType<typeof vi.fn>).mockResolvedValue({ batchId: 'BATCH-001', phase: 'READY', guidance: 'ready', maintenance: { enabled: false } });
    (gatewayStub.getCountStats as ReturnType<typeof vi.fn>).mockResolvedValue({ total: 1, ok: 1, ng: 0, recheck: 0, yieldRate: 100, avgCycleMs: 980, continuousRunCount: 1 });
    (gatewayStub.getRecipes as ReturnType<typeof vi.fn>).mockResolvedValue([{ id: 'recipe-a', name: 'Recipe A' }]);
    (gatewayStub.getResults as ReturnType<typeof vi.fn>).mockResolvedValue([sampleResult]);
  });

  it('hydrates recent results during bootstrap instead of relying on websocket-only updates', async () => {
    const { useHmiBootstrap } = await import('@/features/bootstrap/useHmiBootstrap');
    const { useInspectionStore } = await import('@/entities/inspection/store');
    const { useStationStore } = await import('@/entities/station/store');

    const bootstrap = useHmiBootstrap();
    await bootstrap.start();

    const inspectionStore = useInspectionStore();
    const stationStore = useStationStore();
    expect(gatewayStub.getResults).toHaveBeenCalledWith({ limit: 40, offset: 0 });
    expect(inspectionStore.recentResults).toHaveLength(1);
    expect(inspectionStore.recentResults[0].id).toBe('result-bootstrap-1');
    expect(stationStore.snapshot.batchId).toBe('BATCH-001');

    bootstrap.stop();
  });

  it('subscribes only to canonical finalized result events for first-party result handling', async () => {
    const { useHmiBootstrap } = await import('@/features/bootstrap/useHmiBootstrap');
    const bootstrap = useHmiBootstrap();

    await bootstrap.start();

    const registeredEvents = (gatewayStub.on as ReturnType<typeof vi.fn>).mock.calls.map(([event]) => event);
    expect(registeredEvents).toContain('inspection.result.finalized');
    expect(registeredEvents).not.toContain('inspection.result.created');

    bootstrap.stop();
  });


  it('re-synchronizes after a recovered reconnect event', async () => {
    const { useHmiBootstrap } = await import('@/features/bootstrap/useHmiBootstrap');
    const bootstrap = useHmiBootstrap();

    await bootstrap.start();
    expect(gatewayStub.getResults).toHaveBeenCalledTimes(1);
    expect(statusListener).not.toBeNull();

    statusListener?.({
      mode: 'mock',
      transport: 'ONLINE',
      httpOk: true,
      wsOk: true,
      retryCount: 1,
      lastError: '',
      updatedAt: '2026-04-01T12:00:01.000Z',
    });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(gatewayStub.getStationSnapshot).toHaveBeenCalledTimes(2);
    expect(gatewayStub.getCountStats).toHaveBeenCalledTimes(2);
    expect(gatewayStub.getRecipes).toHaveBeenCalledTimes(2);
    expect(gatewayStub.getResults).toHaveBeenCalledTimes(2);

    bootstrap.stop();
  });
});
