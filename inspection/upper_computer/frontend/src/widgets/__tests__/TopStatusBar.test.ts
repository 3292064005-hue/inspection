import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { describe, expect, it } from 'vitest';
import { nextTick } from 'vue';

import TopStatusBar from '@/widgets/TopStatusBar.vue';
import { useAuthStore } from '@/entities/auth/store';
import { useStationStore } from '@/entities/station/store';

describe('TopStatusBar', () => {
  it('renders current user label', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = mount(TopStatusBar, { global: { plugins: [pinia] } });
    const authStore = useAuthStore();
    const stationStore = useStationStore();
    authStore.setSession({ username: 'operator', displayName: '操作员', role: 'operator', issuedAt: '2026-03-31T12:00:00Z', expiresAt: '2026-03-31T23:59:59Z', lastSeenAt: '2026-03-31T12:00:00Z' });
    stationStore.snapshot.activeRecipeName = '测试配方';
    stationStore.snapshot.batchId = 'BATCH-TEST';
    await nextTick();
    expect(wrapper.text()).toContain('操作员 · operator');
    expect(wrapper.text()).toContain('测试配方');
  });
});
