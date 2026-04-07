import { appEnv } from '@/shared/config/env';
import type { GatewayStatusSnapshot, GatewayTransportState } from '@/shared/gateway/contracts';

interface WebSocketEnvelope {
  event?: string;
  type?: string;
  payload?: unknown;
  data?: unknown;
}

export interface GatewayWebSocketClientOptions {
  url: string;
  mode: 'http' | 'mock';
  onMessage: (payload: WebSocketEnvelope) => void;
  onStatus: (status: GatewayStatusSnapshot) => void;
  acquireTicket?: () => Promise<string>;
}

function createStatus(mode: 'http' | 'mock', transport: GatewayTransportState, retryCount: number, lastError = '', wsOk = false): GatewayStatusSnapshot {
  return { mode, transport, httpOk: mode === 'http', wsOk, retryCount, lastError, updatedAt: new Date().toISOString() };
}

export class GatewayWebSocketClient {
  private socket: WebSocket | null = null;
  private retryCount = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private lastPongAt = 0;
  private manualClose = false;
  private activeTicket = '';

  constructor(private readonly options: GatewayWebSocketClientOptions) {}

  async connect(ticket: string): Promise<void> {
    if (!ticket) throw new Error('缺少 WebSocket 凭证。');
    this.manualClose = false;
    this.activeTicket = ticket;
    this.setStatus('CONNECTING', '', false);
    return new Promise<void>((resolve, reject) => {
      const url = new URL(this.options.url);
      url.searchParams.set('ticket', ticket);
      const socket = new WebSocket(url);
      this.socket = socket;
      socket.onopen = () => {
        this.retryCount = 0;
        this.lastPongAt = Date.now();
        this.startHeartbeat();
        this.setStatus('ONLINE', '', true);
        resolve();
      };
      socket.onerror = () => {
        this.setStatus('ERROR', 'WebSocket connect failed', false);
        reject(new Error('WebSocket connect failed'));
      };
      socket.onmessage = (event) => {
        this.lastPongAt = Date.now();
        try {
          const envelope = JSON.parse(event.data) as WebSocketEnvelope;
          if (envelope.type === 'pong' || envelope.event === 'gateway.pong') {
            this.setStatus('ONLINE', '', true);
            return;
          }
          this.options.onMessage(envelope);
        } catch {
          this.setStatus('ERROR', '接收到无效 WebSocket 消息。', false);
        }
      };
      socket.onclose = (closeEvent) => {
        if (this.socket === socket) this.socket = null;
        this.stopHeartbeat();
        if (!this.manualClose) {
          this.scheduleReconnect(`WS closed (${closeEvent.code})`);
        } else {
          this.setStatus('OFFLINE', '连接已关闭', false);
        }
      };
    }).catch((error) => {
      this.scheduleReconnect(error instanceof Error ? error.message : 'WebSocket connect failed');
      throw error;
    });
  }

  close(): void {
    this.manualClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.stopHeartbeat();
    this.socket?.close();
    this.socket = null;
    this.activeTicket = '';
    this.setStatus('OFFLINE', '连接已关闭', false);
  }

  private scheduleReconnect(reason: string): void {
    if (this.manualClose || this.reconnectTimer) return;
    this.retryCount += 1;
    this.setStatus('RECONNECTING', reason, false);
    if (this.retryCount > appEnv.gatewayMaxReconnectRetries) {
      this.setStatus('ERROR', `重连次数已超过上限：${reason}`, false);
      return;
    }
    const delay = Math.min(appEnv.gatewayRetryBaseMs * 2 ** Math.max(0, this.retryCount - 1), appEnv.gatewayRetryMaxMs);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      const reconnect = async () => {
        const refreshedTicket = this.options.acquireTicket ? await this.options.acquireTicket() : this.activeTicket;
        if (!refreshedTicket) {
          this.setStatus('ERROR', '缺少重连凭证。', false);
          return;
        }
        this.activeTicket = refreshedTicket;
        await this.connect(refreshedTicket);
      };
      void reconnect().catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'WebSocket reconnect failed';
        this.setStatus('ERROR', message, false);
      });
    }, delay);
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
      const age = Date.now() - this.lastPongAt;
      if (age > appEnv.heartbeatOfflineMs) {
        this.socket.close();
        return;
      }
      try {
        this.socket.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() }));
      } catch {
        this.socket.close();
      }
    }, Math.max(1000, Math.floor(appEnv.heartbeatDegradedMs / 2)));
  }

  private stopHeartbeat(): void {
    if (!this.heartbeatTimer) return;
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  private setStatus(transport: GatewayTransportState, lastError = '', wsOk = false): void {
    this.options.onStatus(createStatus(this.options.mode, transport, this.retryCount, lastError, wsOk));
  }
}
