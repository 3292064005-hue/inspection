import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAppStore } from '@/entities/app/store';

describe('app store', () => {
  beforeEach(() => setActivePinia(createPinia()));
  it('arms and auto-expires maintenance mode', () => {
    const baseNow = new Date('2026-04-01T00:00:00.000Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(baseNow);
    const store = useAppStore();
    store.armMaintenanceMode(1_000);
    expect(store.maintenanceMode).toBe(true);
    vi.spyOn(Date, 'now').mockReturnValue(baseNow + 2_000);
    store.tickMaintenanceMode();
    expect(store.maintenanceMode).toBe(false);
    vi.restoreAllMocks();
  });
  it('resolves confirm dialog promises', async () => {
    const store = useAppStore();
    const pending = store.confirmAction({ title: '确认', message: '继续？' });
    expect(store.confirm.open).toBe(true);
    store.settleConfirm(true);
    await expect(pending).resolves.toBe(true);
  });
});
