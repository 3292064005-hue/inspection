import { describe, expect, it } from 'vitest';
import { transportStateToConnectionState } from '@/shared/config/env';

describe('transportStateToConnectionState', () => {
  it('maps ONLINE to ONLINE', () => {
    expect(transportStateToConnectionState('ONLINE')).toBe('ONLINE');
  });

  it('maps IDLE to OFFLINE', () => {
    expect(transportStateToConnectionState('IDLE')).toBe('OFFLINE');
  });
});
