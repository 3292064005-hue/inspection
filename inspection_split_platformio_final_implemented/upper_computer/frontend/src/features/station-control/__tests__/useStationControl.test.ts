import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { effectScope } from 'vue';

const gateway = {
  startStation: vi.fn(async () => undefined),
  stopStation: vi.fn(async () => undefined),
  resetFault: vi.fn(async () => undefined),
  newBatch: vi.fn(async () => 'BATCH-NEW'),
  exportBatch: vi.fn(async () => ({ url: '/artifacts/exports/batch.zip' })),
};

vi.mock('@/shared/gateway/service', () => ({ getGateway: () => gateway }));

import { useStationControl } from '@/features/station-control/useStationControl';
import { useAppStore } from '@/entities/app/store';
import { useInspectionStore } from '@/entities/inspection/store';
import { useStationStore } from '@/entities/station/store';

describe('useStationControl', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    Object.values(gateway).forEach((fn: any) => fn.mockClear?.());
  });

  it('warns when offline and executes fault reset / export flows', async () => {
    const scope = effectScope();
    const api = scope.run(() => useStationControl());
    if (!api) throw new Error('control init failed');
    const appStore = useAppStore();
    const stationStore = useStationStore();
    const inspectionStore = useInspectionStore();

    stationStore.setConnectionState('OFFLINE');
    await api.onPrimaryAction();
    expect(appStore.latestNotice?.title).toBe('链路不可用');

    stationStore.setConnectionState('ONLINE');
    stationStore.applySnapshot({ ...stationStore.snapshot, phase: 'FAULT', mode: 'IDLE' });
    await api.onPrimaryAction();
    expect(gateway.resetFault).toHaveBeenCalled();

    appStore.confirmAction = vi.fn(async () => true);
    await api.createBatch();
    expect(gateway.newBatch).toHaveBeenCalled();
    await api.exportBatch();
    expect(gateway.exportBatch).toHaveBeenCalledWith(stationStore.snapshot.batchId);
    expect(inspectionStore.timeline.length).toBeGreaterThan(0);
    scope.stop();
  });
});
