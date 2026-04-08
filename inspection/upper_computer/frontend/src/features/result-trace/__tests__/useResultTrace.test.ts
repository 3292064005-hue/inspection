import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import type { HmiGateway } from '@/shared/gateway/contracts';
import type { InspectionResult } from '@/shared/types/domain';

const gatewayStub: Partial<HmiGateway> = {
  getResults: vi.fn(),
  getResultDetail: vi.fn(),
  getReadModelStatus: vi.fn(),
  repairReadModel: vi.fn(),
};

vi.mock('@/shared/gateway/service', () => ({
  getGateway: () => gatewayStub,
}));

const baseResult: InspectionResult = {
  id: 'result-1',
  timestamp: '2026-04-01T12:00:00.000Z',
  batchId: 'BATCH-001',
  recipeId: 'recipe-a',
  recipeName: 'Recipe A',
  decision: 'NG',
  defectType: '二维码缺失',
  qrText: 'QR-001',
  cycleMs: 1200,
  traceId: 'trace-1',
  artifactCount: 2,
  explanation: ['规则命中'],
  breakdown: {
    feedingMs: 100,
    captureMs: 200,
    analyzeMs: 300,
    sortingMs: 400,
    totalMs: 1200,
  },
};

describe('useResultTrace', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
    vi.clearAllMocks();
    (gatewayStub.getResults as ReturnType<typeof vi.fn>).mockResolvedValue([baseResult]);
    (gatewayStub.getReadModelStatus as ReturnType<typeof vi.fn>).mockResolvedValue({
      mode: 'HOT',
      degraded: false,
      repairRequired: false,
      projectionAvailable: true,
      fallbackEnabled: false,
      querySurface: 'projection',
      maintenanceState: 'IDLE',
      repairRunning: false,
      lastError: '',
      lastRepairAt: '',
      lastRepairReason: '',
      sourceSyncToken: 's1',
      materializedSyncToken: 'm1',
    });
    (gatewayStub.repairReadModel as ReturnType<typeof vi.fn>).mockResolvedValue({
      mode: 'HOT',
      degraded: false,
      repairRequired: false,
      projectionAvailable: true,
      fallbackEnabled: false,
      querySurface: 'projection',
      maintenanceState: 'IDLE',
      repairRunning: false,
      lastError: '',
      lastRepairAt: '2026-04-01T12:05:00.000Z',
      lastRepairReason: '',
      sourceSyncToken: 's2',
      materializedSyncToken: 'm2',
    });
    (gatewayStub.getResultDetail as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...baseResult,
      traceBundle: {
        traceId: 'trace-1',
        eventCount: 2,
        artifactCount: 2,
        artifacts: [
          { kind: 'raw', path: 'raw.png', url: '/artifacts/raw.png' },
          { kind: 'annotated', path: 'annotated.png', url: '/artifacts/annotated.png' },
        ],
        events: [
          { phase: 'CAPTURE', message: '采图完成' },
          { phase: 'ANALYZE', message: '分析完成' },
        ],
      },
    });
  });

  it('loads list results and enriches the selected result with detail trace bundle', async () => {
    const { useResultTrace } = await import('@/features/result-trace/useResultTrace');
    const trace = useResultTrace();
    await trace.loadResults(true);
    await vi.waitFor(() => {
      expect(trace.selectedItem.value?.traceBundle?.traceId).toBe('trace-1');
    });
    expect(trace.selectedItem.value?.artifactCount).toBe(2);
    expect(gatewayStub.getResultDetail).toHaveBeenCalledWith('result-1');
  });

  it('supports read-model status refresh and repair flow', async () => {
    const { useResultTrace } = await import('@/features/result-trace/useResultTrace');
    const trace = useResultTrace();
    await trace.refreshReadModelStatus(true);
    expect(trace.readModelStatus.value?.mode).toBe('HOT');
    await trace.repairReadModel();
    expect(gatewayStub.repairReadModel).toHaveBeenCalled();
  });
});
