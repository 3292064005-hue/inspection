import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useFaultStore } from '@/entities/fault/store';

describe('fault store', () => {
  beforeEach(() => setActivePinia(createPinia()));
  it('tracks active fault and history', () => {
    const store = useFaultStore();
    store.raiseFault({ id: 'fault-1', code: 'VISION_TIMEOUT', level: 'ERROR', message: 'camera timeout', recoverable: true, source: 'vision', timestamp: new Date().toISOString() });
    expect(store.activeFault?.id).toBe('fault-1');
    store.clearFault('fault-1');
    expect(store.activeFault).toBeNull();
    expect(store.history).toHaveLength(1);
  });
});
