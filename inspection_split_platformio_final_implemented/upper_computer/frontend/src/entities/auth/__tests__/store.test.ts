import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useAuthStore } from '@/entities/auth/store';

describe('auth store', () => {
  beforeEach(() => setActivePinia(createPinia()));
  it('tracks session and password change requirement', () => {
    const store = useAuthStore();
    expect(store.isAuthenticated).toBe(false);
    store.setSession({ username: 'alice', displayName: 'Alice', role: 'process_engineer', issuedAt: new Date().toISOString(), expiresAt: new Date().toISOString(), mustChangePassword: true });
    expect(store.isAuthenticated).toBe(true);
    expect(store.mustChangePassword).toBe(true);
    expect(store.displayLabel).toContain('Alice');
    store.clear();
    expect(store.displayLabel).toBe('未认证');
  });
});
