import { appEnv } from '@/shared/config/env';
import type { AuditEntry, GatewayEventName, GatewayHandler, GatewayStatusListener, GatewayStatusSnapshot, HmiGateway } from '@/shared/gateway/contracts';
import type { AuthSession, CountStats, DemoScenario, DiagnosticAction, DiagnosticsActionResult, DiagnosticsItem, InspectionResult, RecipeProfile, ResultQuery, StationStateSnapshot } from '@/shared/types/domain';
import { HttpClient } from '@/shared/gateway/transport/httpClient';
import { GatewayWebSocketClient } from '@/shared/gateway/transport/websocketClient';

type HandlerBucket = { [K in GatewayEventName]: Set<GatewayHandler<K>> };
interface ApiEnvelope<T> { success: boolean; message: string; data: T; meta?: Record<string, any>; timestamp?: string }
interface WsTicketPayload { ticket: string; expiresAt: string }

function createBuckets(): HandlerBucket {
  return {
    'station.state.updated': new Set(),
    'station.count.updated': new Set(),
    'inspection.result.created': new Set(),
    'fault.raised': new Set(),
    'fault.cleared': new Set(),
    'camera.frame': new Set(),
    'system.heartbeat': new Set(),
    'auth.session': new Set(),
  };
}

export class HttpGateway implements HmiGateway {
  private readonly handlers = createBuckets();
  private readonly statusListeners = new Set<GatewayStatusListener>();
  private readonly http = new HttpClient(appEnv.gatewayBaseUrl, { timeoutMs: appEnv.gatewayRequestTimeoutMs });
  private readonly ws = new GatewayWebSocketClient({ url: appEnv.gatewayWsUrl, mode: 'http', onMessage: (data) => this.handleSocketMessage(data), onStatus: (status) => this.applyStatus(status), acquireTicket: async () => (await this.issueWsTicket()).ticket });
  private status: GatewayStatusSnapshot = { mode: 'http', transport: 'IDLE', httpOk: false, wsOk: false, retryCount: 0, lastError: '', updatedAt: new Date().toISOString() };

  async connect(): Promise<void> {
    const ticket = await this.issueWsTicket();
    await this.ws.connect(ticket.ticket);
  }
  disconnect(): void { this.ws.close(); }
  on<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void { this.handlers[event].add(handler as never); }
  off<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void { this.handlers[event].delete(handler as never); }
  onStatusChange(handler: GatewayStatusListener): () => void { this.statusListeners.add(handler); handler(this.status); return () => this.statusListeners.delete(handler); }
  getStatus(): GatewayStatusSnapshot { return this.status; }
  configureDemoScenario(_scenario: DemoScenario): Promise<void> { return Promise.resolve(); }
  async login(username: string, password: string): Promise<AuthSession> { const payload = await this.http.request<ApiEnvelope<AuthSession>>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }); this.markHttpHealthy(true); return payload.data; }
  async getSession(): Promise<AuthSession> { const payload = await this.http.request<ApiEnvelope<AuthSession>>('/api/v1/auth/session'); this.markHttpHealthy(true); return payload.data; }
  async logout(): Promise<void> { await this.http.request<ApiEnvelope<{ loggedOut: boolean }>>('/api/v1/auth/logout', { method: 'POST' }); this.markHttpHealthy(true); }
  async getStationSnapshot(): Promise<StationStateSnapshot> { const payload = await this.http.request<ApiEnvelope<StationStateSnapshot>>('/api/v1/station/snapshot'); this.markHttpHealthy(true); return payload.data; }
  async getCountStats(): Promise<CountStats> { const payload = await this.http.request<ApiEnvelope<CountStats>>('/api/v1/station/stats'); this.markHttpHealthy(true); return payload.data; }
  async startStation(): Promise<void> { await this.http.request<ApiEnvelope<{ success: boolean }>>('/api/v1/station/start', { method: 'POST' }); this.markHttpHealthy(true); }
  async stopStation(): Promise<void> { await this.http.request<ApiEnvelope<{ success: boolean }>>('/api/v1/station/stop', { method: 'POST' }); this.markHttpHealthy(true); }
  async resetFault(): Promise<void> { await this.http.request<ApiEnvelope<{ success: boolean }>>('/api/v1/station/reset-fault', { method: 'POST' }); this.markHttpHealthy(true); }
  async newBatch(): Promise<string> { const payload = await this.http.request<ApiEnvelope<{ batchId: string }>>('/api/v1/station/new-batch', { method: 'POST' }); this.markHttpHealthy(true); return payload.data.batchId; }
  async getResults(query?: ResultQuery): Promise<InspectionResult[]> { const payload = await this.http.request<ApiEnvelope<InspectionResult[]>>(`/api/v1/results${this.toQueryString(query)}`); this.markHttpHealthy(true); return payload.data; }
  async getResultDetail(resultId: string): Promise<InspectionResult> { const payload = await this.http.request<ApiEnvelope<InspectionResult>>(`/api/v1/results/${encodeURIComponent(resultId)}`); this.markHttpHealthy(true); return payload.data; }
  async getRecipes(): Promise<RecipeProfile[]> { const payload = await this.http.request<ApiEnvelope<RecipeProfile[]>>('/api/v1/recipes'); this.markHttpHealthy(true); return payload.data; }
  async saveRecipe(recipe: RecipeProfile): Promise<RecipeProfile> { const payload = await this.http.request<ApiEnvelope<RecipeProfile>>('/api/v1/recipes', { method: 'POST', body: JSON.stringify(recipe) }); this.markHttpHealthy(true); return payload.data; }
  async activateRecipe(recipeId: string): Promise<void> { await this.http.request<ApiEnvelope<{ activation: unknown }>>(`/api/v1/recipes/${encodeURIComponent(recipeId)}/activate`, { method: 'POST' }); this.markHttpHealthy(true); }
  async getDiagnostics(): Promise<DiagnosticsItem[]> { const payload = await this.http.request<ApiEnvelope<DiagnosticsItem[]>>('/api/v1/diagnostics'); this.markHttpHealthy(true); return payload.data; }
  async runDiagnosticAction(action: DiagnosticAction): Promise<DiagnosticsActionResult> { const payload = await this.http.request<ApiEnvelope<DiagnosticsActionResult>>('/api/v1/diagnostics/actions', { method: 'POST', body: JSON.stringify({ action }) }); this.markHttpHealthy(true); return payload.data; }
  async exportBatch(batchId: string): Promise<{ url: string; jobId?: string }> { const payload = await this.http.request<ApiEnvelope<{ exportUrl: string; jobId: string }>>(`/api/v1/exports/${encodeURIComponent(batchId)}`, { method: 'POST' }); this.markHttpHealthy(true); return { url: payload.data.exportUrl, jobId: payload.data.jobId }; }
  async getAuditEntries(limit = 100, offset = 0): Promise<AuditEntry[]> { const payload = await this.http.request<ApiEnvelope<AuditEntry[]>>(`/api/v1/audit?limit=${limit}&offset=${offset}`); this.markHttpHealthy(true); return payload.data; }
  private async issueWsTicket(): Promise<WsTicketPayload> { const payload = await this.http.request<ApiEnvelope<WsTicketPayload>>('/api/v1/auth/ws-ticket', { method: 'POST' }); this.markHttpHealthy(true); return payload.data; }
  private handleSocketMessage(raw: { event?: string; type?: string; payload?: unknown; data?: unknown }): void { const eventName = raw.event ?? raw.type; const payload = raw.payload ?? raw.data; if (!eventName || !(eventName in this.handlers)) return; (this.handlers[eventName as GatewayEventName] as Set<(payload: unknown) => void>).forEach((handler) => handler(payload)); }
  private markHttpHealthy(httpOk: boolean): void { this.status = { ...this.status, httpOk, updatedAt: new Date().toISOString() }; this.statusListeners.forEach((listener) => listener(this.status)); }
  private applyStatus(status: GatewayStatusSnapshot): void { this.status = { ...status, httpOk: this.status.httpOk, updatedAt: new Date().toISOString() }; this.statusListeners.forEach((listener) => listener(this.status)); }
  private toQueryString(query?: ResultQuery): string { if (!query) return ''; const params = new URLSearchParams(); Object.entries(query).forEach(([key, value]) => { if (value === undefined || value === null || value === '') return; params.set(key, String(value)); }); const qs = params.toString(); return qs ? `?${qs}` : ''; }
}
