import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

vi.mock('@/shared/gateway/validation', () => ({
  gatewayValidators: { 'station.state.updated': (payload: any) => ({ ...payload, validated: true }) },
  parseCountStats: (payload: any) => ({ ...payload, parsed: true }),
  parseInspectionResult: (payload: any) => ({ ...payload, parsed: true }),
  parseDiagnosticsActionResult: (payload: any) => ({ ...payload, parsed: true }),
  parseRecipeProfile: (payload: any) => ({ ...payload, parsed: true }),
  parseStationStateSnapshot: (payload: any) => ({ ...payload, parsed: true }),
  validateDiagnosticsArray: (payload: any) => payload,
  validateRecipesArray: (payload: any) => payload,
  validateResultsArray: (payload: any) => payload,
  parseReadModelStatus: (payload: any) => ({ ...payload, parsed: true }),
}));

import { SafeGateway } from '@/shared/gateway/safeGateway';

describe('SafeGateway', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('validates gateway events before dispatch', async () => {
    const handlers = new Map<string, any>();
    const inner: any = {
      connect: vi.fn(),
      disconnect: vi.fn(),
      on: vi.fn((event: string, handler: any) => handlers.set(event, handler)),
      off: vi.fn(),
      getStationSnapshot: vi.fn(async () => ({ phase: 'READY' })),
      getCountStats: vi.fn(async () => ({ total: 1 })),
      startStation: vi.fn(async () => undefined),
      stopStation: vi.fn(async () => undefined),
      resetFault: vi.fn(async () => undefined),
      setMaintenanceMode: vi.fn(async () => ({ phase: 'READY', maintenance: { requested: true } })),
      newBatch: vi.fn(async () => 'BATCH-1'),
      getResults: vi.fn(async () => [{ id: 'r1' }]),
      getResultDetail: vi.fn(async () => ({ id: 'r1' })),
      getReadModelStatus: vi.fn(async () => ({ mode: 'HOT', degraded: false })),
      repairReadModel: vi.fn(async () => ({ mode: 'HOT', degraded: false, repairRunning: false })),
      getRecipes: vi.fn(async () => [{ id: 'recipe-1' }]),
      saveRecipe: vi.fn(async (payload: any) => payload),
      activateRecipe: vi.fn(async () => undefined),
      getDiagnostics: vi.fn(async () => [{ id: 'diag-1' }]),
      runDiagnosticAction: vi.fn(async () => ({ action: 'CAPTURE_FRAME' })),
      exportBatch: vi.fn(async () => ({ url: '/artifacts/exports/batch.zip' })),
    };
    const gateway = new SafeGateway(inner);
    const handler = vi.fn();
    gateway.on('station.state.updated', handler as any);
    handlers.get('station.state.updated')?.({ batchId: 'B1' });
    expect(handler).toHaveBeenCalledWith({ batchId: 'B1', validated: true });
  });

  it('covers snapshot/result/recipe/export helpers', async () => {
    const inner: any = {
      connect: vi.fn(async () => undefined),
      disconnect: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
      getStationSnapshot: vi.fn(async () => ({ phase: 'READY' })),
      getCountStats: vi.fn(async () => ({ total: 1 })),
      startStation: vi.fn(async () => undefined),
      stopStation: vi.fn(async () => undefined),
      resetFault: vi.fn(async () => undefined),
      setMaintenanceMode: vi.fn(async () => ({ phase: 'READY', maintenance: { requested: true } })),
      newBatch: vi.fn(async () => 'BATCH-1'),
      getResults: vi.fn(async () => [{ id: 'r1' }]),
      getResultDetail: vi.fn(async () => ({ id: 'r1' })),
      getReadModelStatus: vi.fn(async () => ({ mode: 'HOT', degraded: false })),
      repairReadModel: vi.fn(async () => ({ mode: 'HOT', degraded: false, repairRunning: false })),
      getRecipes: vi.fn(async () => [{ id: 'recipe-1' }]),
      saveRecipe: vi.fn(async (payload: any) => payload),
      activateRecipe: vi.fn(async () => undefined),
      getDiagnostics: vi.fn(async () => [{ id: 'diag-1' }]),
      runDiagnosticAction: vi.fn(async () => ({ action: 'CAPTURE_FRAME' })),
      exportBatch: vi.fn(async () => ({ url: '/artifacts/exports/batch.zip' })),
    };
    const gateway = new SafeGateway(inner);
    expect((await gateway.getStationSnapshot()) as any).toMatchObject({ parsed: true });
    expect((await gateway.getCountStats()) as any).toMatchObject({ parsed: true });
    expect((await gateway.setMaintenanceMode(true)) as any).toMatchObject({ parsed: true });
    expect(await gateway.newBatch()).toBe('BATCH-1');
    expect(await gateway.getResults()).toEqual([{ id: 'r1' }]);
    expect((await gateway.getResultDetail?.('r1')) as any).toMatchObject({ parsed: true });
    expect((await gateway.getReadModelStatus?.()) as any).toMatchObject({ parsed: true });
    expect((await gateway.repairReadModel?.()) as any).toMatchObject({ parsed: true });
    expect((await gateway.getRecipes()) as any).toEqual([{ id: 'recipe-1' }]);
    expect((await gateway.saveRecipe({ id: 'recipe-1' })) as any).toMatchObject({ parsed: true });
    await gateway.activateRecipe('recipe-1');
    expect(await gateway.getDiagnostics()).toEqual([{ id: 'diag-1' }]);
    expect((await gateway.runDiagnosticAction('CAPTURE_FRAME' as any)) as any).toMatchObject({ parsed: true });
    expect(await gateway.exportBatch('BATCH-1')).toEqual({ url: '/artifacts/exports/batch.zip' });
  });
});
