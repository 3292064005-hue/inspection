import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useStationStore } from '@/entities/station/store';

describe('station store', () => {
  beforeEach(() => setActivePinia(createPinia()));
  it('derives health state from heartbeat freshness', () => {
    const now = new Date('2026-04-01T00:00:10.000Z').getTime();
    vi.spyOn(Date, 'now').mockReturnValue(now);
    const store = useStationStore();
    store.nowTick = now;
    store.applyHeartbeat({ source: 'vision', status: 'ONLINE', message: 'ok', timestamp: '2026-04-01T00:00:09.500Z' });
    expect(store.overallHealth).toBe('ONLINE');
    store.applyHeartbeat({ source: 'gateway', status: 'DEGRADED', message: 'slow', timestamp: '2026-04-01T00:00:09.000Z' });
    expect(store.overallHealth).toBe('DEGRADED');
    store.nowTick = now + 60_000;
    expect(store.hasStaleHeartbeat).toBe(true);
    expect(store.overallHealth).toBe('OFFLINE');
    vi.restoreAllMocks();
  });
});
