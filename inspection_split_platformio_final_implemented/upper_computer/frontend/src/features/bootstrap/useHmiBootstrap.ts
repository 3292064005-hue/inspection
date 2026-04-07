import { watch } from 'vue';

import { useAppStore } from '@/entities/app/store';
import { useAuthStore } from '@/entities/auth/store';
import { useFaultStore } from '@/entities/fault/store';
import { useInspectionStore } from '@/entities/inspection/store';
import { useRecipeStore } from '@/entities/recipe/store';
import { useStationStore } from '@/entities/station/store';
import { appEnv, transportStateToConnectionState } from '@/shared/config/env';
import type { GatewayEventMap, GatewayEventName, GatewayStatusSnapshot } from '@/shared/gateway/contracts';
import { getGateway } from '@/shared/gateway/service';


type GatewayHandlerMap = Partial<{ [K in GatewayEventName]: (payload: GatewayEventMap[K]) => void }>;
type RegisteredGatewayHandler = (payload: unknown) => void;

export function useHmiBootstrap() {
  const gateway = getGateway();
  const appStore = useAppStore();
  const stationStore = useStationStore();
  const inspectionStore = useInspectionStore();
  const faultStore = useFaultStore();
  const recipeStore = useRecipeStore();
  const authStore = useAuthStore();

  let clockTimer: ReturnType<typeof setInterval> | null = null;
  let statusUnsubscribe: (() => void) | null = null;
  let authUnwatch: (() => void) | null = null;
  let initialSyncDone = false;
  let handlersRegistered = false;
  let connecting = false;
  let recoveredRetryCount = -1;

  const handlers: GatewayHandlerMap = {
    'station.state.updated': (payload) => {
      stationStore.applySnapshot(payload);
      inspectionStore.pushTimeline('工位状态更新', `${payload.phase} / ${payload.guidance}`);
    },
    'station.count.updated': (payload) => stationStore.applyStats(payload),
    'inspection.result.created': (payload) => inspectionStore.applyResult(payload),
    'fault.raised': (payload) => {
      faultStore.raiseFault(payload);
      inspectionStore.pushTimeline('故障触发', `${payload.code} / ${payload.message}`, 'ERROR');
      appStore.pushNotice({ level: 'ERROR', title: payload.code, message: payload.message });
      stationStore.setConnectionState('DEGRADED');
      appStore.setConnectionState('DEGRADED');
    },
    'fault.cleared': (payload) => {
      faultStore.clearFault(payload.id);
      inspectionStore.pushTimeline('故障清除', `Fault ID: ${payload.id}`);
      appStore.pushNotice({ level: 'INFO', title: '故障已清除', message: `Fault ID: ${payload.id}` });
    },
    'camera.frame': (payload) => inspectionStore.applyFrame(payload),
    'system.heartbeat': (payload) => {
      stationStore.applyHeartbeat(payload);
      if (stationStore.connectionState !== 'ONLINE' && stationStore.connectionState !== 'DEGRADED') {
        stationStore.setConnectionState('ONLINE');
        appStore.setConnectionState('ONLINE');
      }
    },
    'auth.session': (payload) => authStore.setSession(payload),
  };

  function registerHandlers(): void {
    if (handlersRegistered) {
      return;
    }
    (Object.entries(handlers) as Array<[GatewayEventName, RegisteredGatewayHandler]>).forEach(([event, handler]) => {
      gateway.on(event, handler as never);
    });
    handlersRegistered = true;
  }

  function unregisterHandlers(): void {
    if (!handlersRegistered) {
      return;
    }
    (Object.entries(handlers) as Array<[GatewayEventName, RegisteredGatewayHandler]>).forEach(([event, handler]) => {
      gateway.off(event, handler as never);
    });
    handlersRegistered = false;
  }

  async function syncInitialSnapshot(reason = '初始同步'): Promise<void> {
    const [snapshot, stats, recipes] = await Promise.all([
      gateway.getStationSnapshot(),
      gateway.getCountStats(),
      gateway.getRecipes(),
    ]);
    stationStore.applySnapshot(snapshot);
    stationStore.applyStats(stats);
    recipeStore.setRecipes(recipes);
    inspectionStore.pushTimeline('系统快照同步', `${reason}：工位、统计与配方已更新。`);
  }

  function updateConnectionFromStatus(status: GatewayStatusSnapshot): void {
    appStore.setGatewayStatus(status);
    const mapped = transportStateToConnectionState(status.transport);
    if (mapped === 'ERROR') {
      appStore.setBootstrapError(status.lastError || '网关连接失败');
      stationStore.setConnectionState('ERROR');
      return;
    }
    appStore.setConnectionState(mapped);
    stationStore.setConnectionState(mapped);
  }

  async function recoverAfterReconnect(status: GatewayStatusSnapshot): Promise<void> {
    if (!initialSyncDone || status.transport !== 'ONLINE' || status.retryCount <= 0 || status.retryCount === recoveredRetryCount) {
      return;
    }
    recoveredRetryCount = status.retryCount;
    try {
      await syncInitialSnapshot('重连恢复');
      appStore.pushNotice({ level: 'INFO', title: '连接已恢复', message: '已重新同步工位快照、统计和配方。' });
    } catch (error) {
      const message = error instanceof Error ? error.message : '重连恢复失败';
      appStore.pushNotice({ level: 'WARN', title: '重连恢复失败', message });
    }
  }

  async function establishConnection(reason: string): Promise<void> {
    if (connecting || !authStore.session || appEnv.gatewayMode !== 'http') {
      return;
    }
    connecting = true;
    appStore.setConnectionState('CONNECTING');
    stationStore.setConnectionState('CONNECTING');
    try {
      await gateway.connect();
      const session = await gateway.getSession?.();
      if (session) {
        authStore.setSession(session);
      }
      await syncInitialSnapshot(reason);
      initialSyncDone = true;
      recoveredRetryCount = 0;
      appStore.setConnectionState('ONLINE');
      stationStore.setConnectionState('ONLINE');
      inspectionStore.pushTimeline('系统连接完成', `${reason}：初始快照、统计与配方已同步。`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '系统初始化失败';
      appStore.setBootstrapError(message);
      inspectionStore.pushTimeline('系统初始化失败', message, 'ERROR');
      throw error;
    } finally {
      connecting = false;
    }
  }

  async function restoreOrLogin(): Promise<void> {
    try {
      const restored = await gateway.getSession?.();
      if (restored) {
        authStore.setSession(restored);
        await establishConnection('恢复会话');
        return;
      }
    } catch {
      // fall through to auto login when session restore is unavailable or expired.
    }

    if (appEnv.authAutoLogin && appEnv.authUsername && appEnv.authPassword) {
      try {
        const session = await gateway.login?.(appEnv.authUsername, appEnv.authPassword);
        if (session) {
          authStore.setSession(session);
          await establishConnection('自动登录');
          return;
        }
      } catch (loginError) {
        const message = loginError instanceof Error ? loginError.message : '自动登录失败';
        appStore.pushNotice({ level: 'WARN', title: '自动登录失败', message });
      }
    }

    appStore.setConnectionState('OFFLINE');
    stationStore.setConnectionState('OFFLINE');
  }

  function startHeartbeatTicker(): void {
    if (clockTimer) {
      clearInterval(clockTimer);
    }
    clockTimer = setInterval(() => {
      stationStore.tick();
      appStore.tickMaintenanceMode();
      if (stationStore.overallHealth === 'OFFLINE') {
        stationStore.setConnectionState('OFFLINE');
        appStore.setConnectionState('OFFLINE');
      } else if (stationStore.overallHealth === 'DEGRADED') {
        stationStore.setConnectionState('DEGRADED');
        appStore.setConnectionState('DEGRADED');
      }
    }, 1000);
  }

  function cleanupRuntime({ clearSession = false }: { clearSession?: boolean } = {}): void {
    if (clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
    authUnwatch?.();
    authUnwatch = null;
    statusUnsubscribe?.();
    statusUnsubscribe = null;
    unregisterHandlers();
    gateway.disconnect();
    initialSyncDone = false;
    connecting = false;
    recoveredRetryCount = -1;
    appStore.setConnectionState('OFFLINE');
    stationStore.setConnectionState('OFFLINE');
    if (clearSession) {
      authStore.clear();
    }
  }

  async function start(): Promise<void> {
    appStore.setGatewayModeLabel(appEnv.gatewayMode === 'http' ? `HTTP / WS · ${appEnv.gatewayBaseUrl}` : 'Mock Gateway');
    registerHandlers();
    statusUnsubscribe =
      gateway.onStatusChange?.((status) => {
        updateConnectionFromStatus(status);
        void recoverAfterReconnect(status);
      }) ?? null;

    if (appEnv.gatewayMode === 'http') {
      await restoreOrLogin();
      authUnwatch = watch(
        () => authStore.session?.username ?? '',
        (username, previous) => {
          if (username && username !== previous) {
            void establishConnection('登录完成');
          }
        },
      );
    } else {
      await gateway.connect();
      await syncInitialSnapshot();
      initialSyncDone = true;
    }

    startHeartbeatTicker();
  }

  function stop(): void {
    cleanupRuntime({ clearSession: false });
  }

  return { start, stop };
}
