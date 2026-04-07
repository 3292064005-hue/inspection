import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { describe, expect, it } from 'vitest';
import { nextTick } from 'vue';

import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import { useAppStore } from '@/entities/app/store';
import { useStationStore } from '@/entities/station/store';

describe('ConnectionBanner', () => {
  it('renders online and error guidance from stores', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = mount(ConnectionBanner, { global: { plugins: [pinia] } });
    const appStore = useAppStore();
    const stationStore = useStationStore();

    appStore.setConnectionState('ONLINE');
    stationStore.applyHeartbeat({ source: 'ROS2', timestamp: new Date().toISOString(), status: 'ONLINE', label: 'ROS2' } as any);
    await nextTick();
    expect(wrapper.text()).toContain('链路在线');

    appStore.setBootstrapError('初始化失败');
    await nextTick();
    expect(wrapper.text()).toContain('初始化失败');
  });
});
