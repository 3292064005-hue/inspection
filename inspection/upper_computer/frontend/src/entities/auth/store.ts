import { defineStore } from 'pinia';
import type { AuthSession } from '@/shared/types/domain';

export const useAuthStore = defineStore('auth', {
  state: () => ({ session: null as AuthSession | null }),
  getters: {
    isAuthenticated: (state) => state.session !== null,
    displayLabel: (state) => state.session ? `${state.session.displayName} · ${state.session.role}` : '未认证',
    mustChangePassword: (state) => !!state.session?.mustChangePassword,
  },
  actions: {
    setSession(session: AuthSession | null) { this.session = session; },
    clear() { this.session = null; },
  },
});
