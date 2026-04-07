import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';

const loginMock = vi.fn();

vi.mock('@/shared/gateway/service', () => ({
  getGateway: () => ({ login: loginMock }),
}));

import AuthGate from '@/widgets/AuthGate.vue';
import { useAuthStore } from '@/entities/auth/store';
import { useAppStore } from '@/entities/app/store';

describe('AuthGate', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    loginMock.mockReset();
  });

  it('shows validation error for missing credentials', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const wrapper = mount(AuthGate, { global: { plugins: [pinia] } });

    await wrapper.find('form').trigger('submit.prevent');
    await nextTick();

    expect(wrapper.text()).toContain('请输入用户名和密码。');
    expect(loginMock).not.toHaveBeenCalled();
  });

  it('stores session and pushes bootstrap notice after successful login', async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    loginMock.mockResolvedValue({
      username: 'bootstrap-admin',
      displayName: '引导管理员',
      role: 'admin',
      issuedAt: '2026-04-02T00:00:00Z',
      expiresAt: '2026-04-02T23:59:59Z',
      lastSeenAt: '2026-04-02T00:00:00Z',
      mustChangePassword: true,
      bootstrap: true,
    });
    const wrapper = mount(AuthGate, { global: { plugins: [pinia] } });

    await wrapper.find('input[autocomplete="username"]').setValue(' bootstrap-admin ');
    await wrapper.find('input[autocomplete="current-password"]').setValue('secret');
    await wrapper.find('form').trigger('submit.prevent');
    await nextTick();
    await nextTick();

    const authStore = useAuthStore();
    const appStore = useAppStore();
    expect(loginMock).toHaveBeenCalledWith('bootstrap-admin', 'secret');
    expect(authStore.isAuthenticated).toBe(true);
    expect(appStore.latestNotice?.title).toBe('已使用引导管理员登录');
  });
});
