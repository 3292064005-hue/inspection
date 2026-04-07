import { describe, expect, it } from 'vitest';
import { formatDateTime, formatDuration, formatPercent } from '@/shared/utils/format';
import { decisionTone, healthTone, phaseLabel } from '@/shared/utils/status';

describe('format helpers', () => {
  it('formats datetime, percentages and durations', () => {
    expect(formatDateTime()).toBe('--');
    expect(formatDateTime('2026-04-01T00:00:00Z')).toContain('2026');
    expect(formatPercent(88.88)).toBe('88.9%');
    expect(formatDuration(640)).toBe('640 ms');
    expect(formatDuration(2500)).toBe('2.50 s');
  });
  it('maps status helpers', () => {
    expect(phaseLabel('ANALYZE')).toBe('图像分析');
    expect(decisionTone('NG')).toContain('rose');
    expect(healthTone('ONLINE')).toContain('emerald');
  });
});
