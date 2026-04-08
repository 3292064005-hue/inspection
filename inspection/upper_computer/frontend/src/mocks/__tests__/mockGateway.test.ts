import { describe, expect, it } from 'vitest';
import { MockGateway } from '@/mocks/mockGateway';

describe('MockGateway', () => {
  it('connects and serves snapshot data', async () => {
    const gateway = new MockGateway();
    const authEvents: Array<{ username: string }> = [];
    gateway.on('auth.session', (payload) => authEvents.push(payload as { username: string }));
    await gateway.connect();
    const session = await gateway.login('operator', 'password');
    const snapshot = await gateway.getStationSnapshot();
    (gateway as any).state.results.unshift({
      id: 'result-test',
      timestamp: new Date().toISOString(),
      batchId: snapshot.batchId,
      recipeId: snapshot.activeRecipeId,
      recipeName: snapshot.activeRecipeName,
      decision: 'NG',
      defectType: '二维码缺失',
      qrText: 'QR-001',
      cycleMs: 1234,
      imageUrl: 'data:image/png;base64,raw',
      overlayUrl: 'data:image/png;base64,overlay',
      explanation: ['规则命中'],
      breakdown: {
        feedingMs: 100,
        captureMs: 200,
        analyzeMs: 300,
        sortingMs: 400,
        totalMs: 1234,
      },
    });
    const results = await gateway.getResults({ limit: 5 });
    const detail = await gateway.getResultDetail?.(results[0].id);
    expect(session.username).toBe('operator');
    expect(snapshot.batchId).toContain('BATCH');
    expect(Array.isArray(results)).toBe(true);
    expect(results.length).toBeGreaterThan(0);
    expect(detail?.traceBundle?.traceId).toContain(results[0].id);
    expect(detail?.artifacts?.length).toBeGreaterThan(0);
    expect(authEvents.length).toBeGreaterThan(0);
    gateway.disconnect();
  });
});
