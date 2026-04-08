import { defineStore } from 'pinia';
import { appEnv } from '@/shared/config/env';
import type { ConnectionState, CountStats, HealthStatus, HeartbeatStatus, SourceName, StationStateSnapshot } from '@/shared/types/domain';

const defaultSnapshot: StationStateSnapshot = {
  phase: 'BOOT',
  mode: 'IDLE',
  batchId: 'BATCH-20260331-001',
  activeRecipeId: '',
  activeRecipeName: '--',
  cycleIndex: 0,
  lastUpdatedAt: new Date().toISOString(),
  guidance: '等待系统连接。',
  supervisorMode: 'STOPPED',
  maintenance: {
    requested: false,
    enabled: false,
    transitionState: 'LOCKED',
    supervisorMode: 'STOPPED',
    source: 'default',
  },
};

const defaultStats: CountStats = {
  total: 0,
  ok: 0,
  ng: 0,
  recheck: 0,
  yieldRate: 0,
  continuousRunCount: 0,
  avgCycleMs: 0,
};

function freshnessStatus(heartbeat: HeartbeatStatus, nowTick: number): HealthStatus {
  const ageMs = nowTick - new Date(heartbeat.timestamp).getTime();
  if (ageMs > appEnv.heartbeatOfflineMs) return 'OFFLINE';
  if (ageMs > appEnv.heartbeatDegradedMs || heartbeat.status === 'DEGRADED') return 'DEGRADED';
  return 'ONLINE';
}

export const useStationStore = defineStore('station', {
  state: () => ({
    connectionState: 'BOOTING' as ConnectionState,
    snapshot: defaultSnapshot,
    stats: defaultStats,
    heartbeats: {} as Record<SourceName, HeartbeatStatus>,
    nowTick: Date.now(),
  }),
  getters: {
    isFaulted: (state) => state.snapshot.phase === 'FAULT',
    isRunning: (state) => state.snapshot.mode === 'AUTO',
    heartbeatList(state) {
      return (Object.values(state.heartbeats) as HeartbeatStatus[]).map((heartbeat) => ({
        ...heartbeat,
        derivedStatus: freshnessStatus(heartbeat, state.nowTick),
        ageMs: state.nowTick - new Date(heartbeat.timestamp).getTime(),
      }));
    },
    overallHealth(): HealthStatus {
      const list = this.heartbeatList;
      if (list.length === 0) return 'OFFLINE';
      if (list.some((item) => item.derivedStatus === 'OFFLINE')) return 'OFFLINE';
      if (list.some((item) => item.derivedStatus === 'DEGRADED')) return 'DEGRADED';
      return 'ONLINE';
    },
    hasStaleHeartbeat(): boolean {
      return this.heartbeatList.some((item) => item.ageMs > appEnv.heartbeatDegradedMs);
    },
  },
  actions: {
    applySnapshot(snapshot: StationStateSnapshot) {
      this.snapshot = snapshot;
    },
    applyStats(stats: CountStats) {
      this.stats = stats;
    },
    applyHeartbeat(heartbeat: HeartbeatStatus) {
      this.heartbeats[heartbeat.source] = heartbeat;
    },
    setConnectionState(state: ConnectionState) {
      this.connectionState = state;
    },
    tick() {
      this.nowTick = Date.now();
    },
  },
});
