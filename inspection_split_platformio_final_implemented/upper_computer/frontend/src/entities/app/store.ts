import { defineStore } from 'pinia';
import type { ConnectionState } from '@/shared/types/domain';
import type { GatewayStatusSnapshot } from '@/shared/gateway/contracts';
import { appEnv } from '@/shared/config/env';

export interface UiNotice {
  id: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  title: string;
  message: string;
  createdAt: string;
}

interface ConfirmState {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  cancelLabel: string;
  tone: 'INFO' | 'WARN' | 'ERROR';
  resolve?: (value: boolean) => void;
}

const defaultConfirmState = (): ConfirmState => ({
  open: false,
  title: '',
  message: '',
  confirmLabel: '确认',
  cancelLabel: '取消',
  tone: 'WARN',
});

export const useAppStore = defineStore('app', {
  state: () => ({
    connectionState: 'BOOTING' as ConnectionState,
    bootstrapError: '' as string,
    maintenanceMode: false,
    maintenanceUnlockExpiresAt: 0,
    pendingActionLabel: '' as string,
    notices: [] as UiNotice[],
    exportedUrl: '' as string,
    exportState: 'idle' as 'idle' | 'requesting' | 'ready' | 'failed',
    gatewayModeLabel: '' as string,
    gatewayStatus: null as GatewayStatusSnapshot | null,
    confirm: defaultConfirmState(),
  }),
  getters: {
    hasBlockingError: (state) => state.connectionState === 'ERROR',
    latestNotice: (state) => state.notices[0] ?? null,
    maintenanceRemainingMs: (state) => Math.max(0, state.maintenanceUnlockExpiresAt - Date.now()),
  },
  actions: {
    setConnectionState(state: ConnectionState) {
      this.connectionState = state;
    },
    setBootstrapError(message: string) {
      this.bootstrapError = message;
      this.connectionState = 'ERROR';
    },
    setGatewayModeLabel(label: string) {
      this.gatewayModeLabel = label;
    },
    setGatewayStatus(status: GatewayStatusSnapshot) {
      this.gatewayStatus = status;
    },
    setPendingAction(label: string) {
      this.pendingActionLabel = label;
    },
    armMaintenanceMode(durationMs = appEnv.maintenanceUnlockMs) {
      this.maintenanceMode = true;
      this.maintenanceUnlockExpiresAt = Date.now() + durationMs;
      this.pushNotice({
        level: 'WARN',
        title: '维护模式已启用',
        message: `危险动作已解锁，持续 ${Math.ceil(durationMs / 60000)} 分钟。`,
      });
    },
    setMaintenanceMode(enabled: boolean) {
      this.maintenanceMode = enabled;
      this.maintenanceUnlockExpiresAt = enabled ? Date.now() + appEnv.maintenanceUnlockMs : 0;
      this.pushNotice({
        level: enabled ? 'WARN' : 'INFO',
        title: enabled ? '维护模式已启用' : '维护模式已关闭',
        message: enabled ? '危险动作已解锁，所有测试动作都会写入事件时间轴。' : '已恢复到运行保护状态。',
      });
    },
    tickMaintenanceMode() {
      if (this.maintenanceMode && this.maintenanceUnlockExpiresAt > 0 && Date.now() >= this.maintenanceUnlockExpiresAt) {
        this.maintenanceMode = false;
        this.maintenanceUnlockExpiresAt = 0;
        this.pushNotice({
          level: 'INFO',
          title: '维护模式已自动关闭',
          message: '维护窗口已到期，系统已恢复运行保护状态。',
        });
      }
    },
    pushNotice(input: Omit<UiNotice, 'id' | 'createdAt'>) {
      this.notices.unshift({
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        createdAt: new Date().toISOString(),
        ...input,
      });
      this.notices = this.notices.slice(0, 10);
    },
    clearNotice(id: string) {
      this.notices = this.notices.filter((item) => item.id !== id);
    },
    setExportedUrl(url: string) {
      this.exportedUrl = url;
      this.exportState = url ? 'ready' : 'idle';
    },
    setExportState(state: 'idle' | 'requesting' | 'ready' | 'failed') {
      this.exportState = state;
    },
    confirmAction(input: Partial<Omit<ConfirmState, 'open' | 'resolve'>> & Pick<ConfirmState, 'title' | 'message'>): Promise<boolean> {
      return new Promise((resolve) => {
        this.confirm = {
          ...defaultConfirmState(),
          ...input,
          open: true,
          resolve,
        };
      });
    },
    settleConfirm(result: boolean) {
      this.confirm.resolve?.(result);
      this.confirm = defaultConfirmState();
    },
  },
});
