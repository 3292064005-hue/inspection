import { appEnv } from '@/shared/config/env';
import type {
  AuditEntry,
  GatewayCapabilities,
  GatewayEventName,
  GatewayHandler,
  GatewayStatusListener,
  GatewayStatusSnapshot,
  HmiGateway,
} from '@/shared/gateway/contracts';
import type {
  AuthSession,
  CountStats,
  DemoScenario,
  DiagnosticAction,
  DiagnosticsActionResult,
  DiagnosticsItem,
  InspectionResult,
  ReadModelStatus,
  RecipeProfile,
  ResultQuery,
  StationStateSnapshot,
} from '@/shared/types/domain';
import { HttpClient } from '@/shared/gateway/transport/httpClient';
import { GatewayWebSocketClient } from '@/shared/gateway/transport/websocketClient';

type HandlerBucket = { [K in GatewayEventName]: Set<GatewayHandler<K>> };
interface ApiEnvelope<T> { success: boolean; message: string; data: T; meta?: Record<string, any>; timestamp?: string }
interface WsTicketPayload { ticket: string; expiresAt: string }
interface ActionJobRecord<T = Record<string, unknown>> {
  jobId: string;
  status: string;
  result?: T;
  error?: { message?: string; detail?: string; code?: string };
  message?: string;
}

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
    'orchestrator.advice': new Set(),
  };
}

export class HttpGateway implements HmiGateway {
  private readonly handlers = createBuckets();
  private readonly statusListeners = new Set<GatewayStatusListener>();
  private readonly http = new HttpClient(appEnv.gatewayBaseUrl, { timeoutMs: appEnv.gatewayRequestTimeoutMs });
  private readonly ws = new GatewayWebSocketClient({
    url: appEnv.gatewayWsUrl,
    mode: 'http',
    onMessage: (data) => this.handleSocketMessage(data),
    onStatus: (status) => this.applyStatus(status),
    acquireTicket: async () => (await this.issueWsTicket()).ticket,
  });
  private status: GatewayStatusSnapshot = { mode: 'http', transport: 'IDLE', httpOk: false, wsOk: false, retryCount: 0, lastError: '', updatedAt: new Date().toISOString() };

  async connect(): Promise<void> {
    const ticket = await this.issueWsTicket();
    await this.ws.connect(ticket.ticket);
  }

  disconnect(): void {
    this.ws.close();
  }

  on<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void {
    this.handlers[event].add(handler as never);
  }

  off<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void {
    this.handlers[event].delete(handler as never);
  }

  onStatusChange(handler: GatewayStatusListener): () => void {
    this.statusListeners.add(handler);
    handler(this.status);
    return () => this.statusListeners.delete(handler);
  }

  getStatus(): GatewayStatusSnapshot {
    return this.status;
  }

  getCapabilities(): GatewayCapabilities {
    return {
      demoScenarioControl: {
        supported: false,
        reason: 'HTTP/真实后端模式不支持演示场景切换。',
      },
      cameraFrameSemantic: 'LATEST_RESULT_FRAME',
    };
  }

  async configureDemoScenario(_scenario: DemoScenario): Promise<void> {
    throw new Error('demo_scenario_control_unsupported_in_http_gateway');
  }

  async login(username: string, password: string): Promise<AuthSession> {
    const payload = await this.http.request<ApiEnvelope<AuthSession>>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getSession(): Promise<AuthSession> {
    const payload = await this.http.request<ApiEnvelope<AuthSession>>('/api/v1/auth/session');
    this.markHttpHealthy(true);
    return payload.data;
  }

  async logout(): Promise<void> {
    await this.http.request<ApiEnvelope<{ loggedOut: boolean }>>('/api/v1/auth/logout', { method: 'POST' });
    this.markHttpHealthy(true);
  }

  async getStationSnapshot(): Promise<StationStateSnapshot> {
    const payload = await this.http.request<ApiEnvelope<StationStateSnapshot>>('/api/v1/station/snapshot');
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getCountStats(): Promise<CountStats> {
    const payload = await this.http.request<ApiEnvelope<CountStats>>('/api/v1/station/stats');
    this.markHttpHealthy(true);
    return payload.data;
  }

  async startStation(): Promise<void> {
    const snapshot = await this.getStationSnapshot();
    const payload: Record<string, unknown> = {
      recipeId: String(snapshot?.activeRecipeId ?? '').trim() || 'default_recipe',
    };
    const batchId = String(snapshot?.batchId ?? '').trim();
    if (batchId) payload.batchId = batchId;
    const created = await this.http.request<ApiEnvelope<ActionJobRecord<{ started?: boolean; message?: string }>>>('/api/v1/actions/start-batch', { method: 'POST', body: JSON.stringify(payload) });
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('start_batch_job_submit_failed');
    await this.pollActionJob<{ started?: boolean; message?: string }>(jobId);
  }

  async stopStation(): Promise<void> {
    const created = await this.http.request<ApiEnvelope<ActionJobRecord<{ stopped?: boolean; message?: string }>>>('/api/v1/actions/stop-station', { method: 'POST', body: JSON.stringify({}) });
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('stop_station_job_submit_failed');
    await this.pollActionJob<{ stopped?: boolean; message?: string }>(jobId);
  }

  async resetFault(): Promise<void> {
    const created = await this.http.request<ApiEnvelope<ActionJobRecord<{ reset?: boolean; message?: string }>>>('/api/v1/actions/reset-station', { method: 'POST', body: JSON.stringify({}) });
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('reset_station_job_submit_failed');
    await this.pollActionJob<{ reset?: boolean; message?: string }>(jobId);
  }

  async setMaintenanceMode(enabled: boolean): Promise<StationStateSnapshot> {
    const created = await this.http.request<ApiEnvelope<ActionJobRecord<StationStateSnapshot>>>('/api/v1/actions/set-maintenance-mode', { method: 'POST', body: JSON.stringify({ enabled }) });
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('maintenance_action_job_submit_failed');
    return await this.pollActionJob<StationStateSnapshot>(jobId);
  }

  async newBatch(): Promise<string> {
    const created = await this.http.request<ApiEnvelope<ActionJobRecord<{ batchId: string }>>>('/api/v1/actions/create-batch', { method: 'POST', body: JSON.stringify({}) });
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('create_batch_job_submit_failed');
    const completed = await this.pollActionJob<{ batchId: string }>(jobId);
    return String((completed as any)?.batchId ?? '');
  }

  async getResults(query?: ResultQuery): Promise<InspectionResult[]> {
    const payload = await this.http.request<ApiEnvelope<InspectionResult[]>>(`/api/v1/results${this.toQueryString(query)}`);
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getResultDetail(resultId: string): Promise<InspectionResult> {
    const payload = await this.http.request<ApiEnvelope<InspectionResult>>(`/api/v1/results/${encodeURIComponent(resultId)}`);
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getReadModelStatus(): Promise<ReadModelStatus> {
    const payload = await this.http.request<ApiEnvelope<ReadModelStatus>>('/api/v1/results/read-model/status');
    this.markHttpHealthy(true);
    return payload.data;
  }

  async repairReadModel(): Promise<ReadModelStatus> {
    const payload = await this.http.request<ApiEnvelope<ReadModelStatus>>('/api/v1/results/read-model/repair', { method: 'POST' });
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getRecipes(): Promise<RecipeProfile[]> {
    const payload = await this.http.request<ApiEnvelope<RecipeProfile[]>>('/api/v1/recipes');
    this.markHttpHealthy(true);
    return payload.data;
  }

  async saveRecipe(recipe: RecipeProfile): Promise<RecipeProfile> {
    const payload = await this.http.request<ApiEnvelope<RecipeProfile>>('/api/v1/recipes', { method: 'POST', body: JSON.stringify(recipe) });
    this.markHttpHealthy(true);
    return payload.data;
  }

  async activateRecipe(recipeId: string): Promise<void> {
    await this.http.request<ApiEnvelope<{ activation: unknown }>>(`/api/v1/recipes/${encodeURIComponent(recipeId)}/activate`, { method: 'POST' });
    this.markHttpHealthy(true);
  }

  async getDiagnostics(): Promise<DiagnosticsItem[]> {
    const payload = await this.http.request<ApiEnvelope<DiagnosticsItem[]>>('/api/v1/diagnostics');
    this.markHttpHealthy(true);
    return payload.data;
  }

  async runDiagnosticAction(action: DiagnosticAction): Promise<DiagnosticsActionResult> {
    const route = this.diagnosticActionRoute(action);
    const created = await this.http.request<ApiEnvelope<ActionJobRecord>>(`${route}`, { method: 'POST', body: JSON.stringify({}) });
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('diagnostic_action_job_submit_failed');
    const completed = await this.pollActionJob<DiagnosticsActionResult>(jobId);
    return completed;
  }

  async exportBatch(batchId: string): Promise<{ url: string; jobId?: string }> {
    const payload = await this.http.request<ApiEnvelope<{ exportUrl: string; jobId: string }>>(`/api/v1/exports/${encodeURIComponent(batchId)}`, { method: 'POST' });
    this.markHttpHealthy(true);
    return { url: payload.data.exportUrl, jobId: payload.data.jobId };
  }

  async getAuditEntries(limit = 100, offset = 0): Promise<AuditEntry[]> {
    const payload = await this.http.request<ApiEnvelope<AuditEntry[]>>(`/api/v1/audit?limit=${limit}&offset=${offset}`);
    this.markHttpHealthy(true);
    return payload.data;
  }

  private diagnosticActionRoute(action: DiagnosticAction): string {
    switch (action) {
      case 'CAPTURE_FRAME':
        return '/api/v1/actions/diagnostics/capture-frame';
      case 'TEST_LIGHTING':
        return '/api/v1/actions/diagnostics/test-lighting';
      case 'TEST_SORT_ACTUATOR':
        return '/api/v1/actions/diagnostics/test-sort-actuator';
      default:
        throw new Error(`unsupported_diagnostic_action:${String(action)}`);
    }
  }

  private async pollActionJob<T>(jobId: string): Promise<T> {
    const deadline = Date.now() + Math.max(2000, appEnv.gatewayRequestTimeoutMs);
    let last: ActionJobRecord<T> | undefined;
    while (Date.now() < deadline) {
      const payload = await this.http.request<ApiEnvelope<ActionJobRecord<T>>>(`/api/v1/actions/jobs/${encodeURIComponent(jobId)}`);
      this.markHttpHealthy(true);
      last = payload.data;
      const status = String(last.status ?? '').toUpperCase();
      if (status === 'COMPLETED') {
        if (last.result === undefined) throw new Error('diagnostic_action_job_missing_result');
        return last.result;
      }
      if (status === 'FAILED' || status === 'CANCELLED') {
        throw new Error(String(last.error?.message ?? last.error?.detail ?? last.message ?? `diagnostic_action_job_${status.toLowerCase()}`));
      }
      await new Promise((resolve) => globalThis.setTimeout(resolve, 50));
    }
    throw new Error(`diagnostic_action_job_timeout:${String(last?.status ?? 'PENDING')}`);
  }

  private async issueWsTicket(): Promise<WsTicketPayload> {
    const payload = await this.http.request<ApiEnvelope<WsTicketPayload>>('/api/v1/auth/ws-ticket', { method: 'POST' });
    this.markHttpHealthy(true);
    return payload.data;
  }

  private handleSocketMessage(raw: { event?: string; type?: string; payload?: unknown; data?: unknown }): void {
    const eventName = raw.event ?? raw.type;
    const payload = raw.payload ?? raw.data;
    if (!eventName || !(eventName in this.handlers)) return;
    (this.handlers[eventName as GatewayEventName] as Set<(payload: unknown) => void>).forEach((handler) => handler(payload));
  }

  private applyStatus(status: GatewayStatusSnapshot): void {
    this.status = {
      ...status,
      httpOk: this.status.httpOk || status.httpOk,
      updatedAt: new Date().toISOString(),
    };
    this.statusListeners.forEach((listener) => listener(this.status));
  }

  private markHttpHealthy(ok: boolean): void {
    this.status = {
      ...this.status,
      httpOk: ok,
      updatedAt: new Date().toISOString(),
    };
    this.statusListeners.forEach((listener) => listener(this.status));
  }

  private toQueryString(query?: ResultQuery): string {
    if (!query) return '';
    const params = new URLSearchParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      params.set(key, String(value));
    });
    const encoded = params.toString();
    return encoded ? `?${encoded}` : '';
  }
}
