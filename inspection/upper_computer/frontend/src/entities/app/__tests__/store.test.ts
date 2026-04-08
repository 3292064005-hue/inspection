import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAppStore } from '@/entities/app/store';

describe('app store', () => {
  beforeEach(() => setActivePinia(createPinia()));

  it('pushes and clears notices without maintenance-local state', () => {
    const store = useAppStore();
    store.pushNotice({ level: 'INFO', title: '提示', message: '系统消息' });
    expect(store.latestNotice?.title).toBe('提示');
    const id = store.latestNotice?.id as string;
    store.clearNotice(id);
    expect(store.latestNotice).toBeNull();
  });

  it('resolves confirm dialog promises', async () => {
    const store = useAppStore();
    const pending = store.confirmAction({ title: '确认', message: '继续？' });
    expect(store.confirm.open).toBe(true);
    store.settleConfirm(true);
    await expect(pending).resolves.toBe(true);
  });
});
