import { defineStore } from 'pinia';
import type { ConnectionState } from '@/shared/types/domain';
import type { GatewayStatusSnapshot } from '@/shared/gateway/contracts';

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
