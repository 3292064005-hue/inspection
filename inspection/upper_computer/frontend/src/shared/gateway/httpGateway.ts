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
  ActionCapabilityMatrix,
  ActionCatalogEntry,
  ActionJobUpdate,
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
  ResultStatisticsQuery,
  ResultStatisticsSnapshot,
  StationStateSnapshot,
} from '@/shared/types/domain';
import { HttpClient } from '@/shared/gateway/transport/httpClient';
import { GatewayWebSocketClient } from '@/shared/gateway/transport/websocketClient';
import { createGatewayActionClient, type EmptyActionRequest, type MaintenanceModeRequest, type StartBatchRequest, type SwitchRecipeRequest, type ExportBatchRequest } from '@/shared/gateway/generated/actionApi';
import { createGatewayApiClient, type GetInspectionResultsParams, type GetInspectionResultStatisticsParams, type RecipeSortRuleRequest, type SaveRecipeRequest } from '@/shared/gateway/generated/gatewayApi';

type HandlerBucket = { [K in GatewayEventName]: Set<GatewayHandler<K>> };
interface ApiEnvelope<T> { success: boolean; message: string; data: T; meta?: Record<string, any>; timestamp?: string }
interface WsTicketPayload { ticket: string; expiresAt: string }
interface ActionJobRecord<T = Record<string, unknown>> {
  jobId: string;
  kind?: string;
  status: string;
  progress?: number;
  result?: T;
  error?: { message?: string; detail?: string; code?: string };
  message?: string;
}

type ActionJobListener = (job: ActionJobRecord<any>) => void;

function toInspectionResultsParams(query?: ResultQuery): GetInspectionResultsParams {
  return {
    batchId: query?.batchId,
    recipeId: query?.recipeId,
    decision: query?.decision,
    defectType: query?.defectType,
    qrText: query?.qrText,
    from: query?.from,
    to: query?.to,
    limit: query?.limit,
    offset: query?.offset,
  };
}

function toInspectionStatisticsParams(query?: ResultStatisticsQuery): GetInspectionResultStatisticsParams {
  return {
    ...toInspectionResultsParams(query),
    sampleLimit: query?.sampleLimit,
  };
}

function toFixedLengthRoi(value: unknown): number[] {
  const source = Array.isArray(value) ? value : [];
  return [0, 1, 2, 3].map((index) => {
    const raw = source[index];
    return typeof raw === 'number' && Number.isFinite(raw) ? raw : Number(raw ?? 0) || 0;
  });
}

function toSaveRecipeRequest(recipe: RecipeProfile): SaveRecipeRequest {
  const sortRules = Array.isArray(recipe.sortRules) ? recipe.sortRules : [];
  return {
    id: String(recipe.id ?? ''),
    name: String(recipe.name ?? ''),
    version: String(recipe.version ?? ''),
    targetPart: String(recipe.targetPart ?? ''),
    roi: toFixedLengthRoi(recipe.roi),
    qrRoi: toFixedLengthRoi(recipe.qrRoi),
    thresholdsSummary: String(recipe.thresholdsSummary ?? ''),
    sortRules: sortRules.map((rule): RecipeSortRuleRequest => ({
      condition: String(rule?.condition ?? ''),
      action: String(rule?.action ?? ''),
    })),
    enabled: Boolean(recipe.enabled),
    updatedAt: recipe.updatedAt ? String(recipe.updatedAt) : undefined,
    updatedBy: recipe.updatedBy ? String(recipe.updatedBy) : undefined,
    changeNote: recipe.changeNote ? String(recipe.changeNote) : undefined,
  };
}

function createBuckets(): HandlerBucket {
  return {
    'station.state.updated': new Set(),
    'station.count.updated': new Set(),
    'inspection.result.observed': new Set(),
    'inspection.result.finalized': new Set(),
    'inspection.result.created': new Set(),
    'fault.raised': new Set(),
    'fault.cleared': new Set(),
    'camera.frame': new Set(),
    'system.heartbeat': new Set(),
    'auth.session': new Set(),
    'orchestrator.advice': new Set(),
    'action.job.updated': new Set(),
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
  private readonly actionJobs = new Map<string, ActionJobRecord<any>>();
  private readonly actionApi = createGatewayActionClient({
    request: async <T>(path: string, init: { method: 'GET' | 'POST'; query?: Record<string, unknown>; body?: unknown }): Promise<T> => {
      const query = init.query ? new URLSearchParams(Object.entries(init.query).filter(([, value]) => value !== undefined && value !== null && value !== '').map(([key, value]) => [key, String(value)])).toString() : '';
      const resolvedPath = query ? `${path}${path.includes('?') ? '&' : '?'}${query}` : path;
      return this.http.request<T>(resolvedPath, {
        method: init.method,
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
      });
    },
  });
  private readonly actionJobListeners = new Map<string, Set<ActionJobListener>>();
  private readonly gatewayApi = createGatewayApiClient({
    request: async <T>(path: string, init: { method: 'GET' | 'POST'; query?: Record<string, unknown>; body?: unknown }): Promise<T> => {
      const query = init.query ? new URLSearchParams(Object.entries(init.query).filter(([, value]) => value !== undefined && value !== null && value !== '').map(([key, value]) => [key, String(value)])).toString() : '';
      const resolvedPath = query ? `${path}${path.includes('?') ? '&' : '?'}${query}` : path;
      return this.http.request<T>(resolvedPath, {
        method: init.method,
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
      });
    },
  });

  private status: GatewayStatusSnapshot = { mode: 'http', transport: 'IDLE', httpOk: false, wsOk: false, retryCount: 0, lastError: '', updatedAt: new Date().toISOString() };

  async connect(): Promise<void> {
    const ticket = await this.issueWsTicket();
    await this.ws.connect(ticket.ticket);
  }

  disconnect(): void {
    this.ws.close();
    this.actionJobListeners.clear();
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
    const payload = await this.gatewayApi.loginGatewaySession<ApiEnvelope<AuthSession>>({ username, password });
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getSession(): Promise<AuthSession> {
    const payload = await this.gatewayApi.getGatewaySession<ApiEnvelope<AuthSession>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async logout(): Promise<void> {
    await this.gatewayApi.logoutGatewaySession<ApiEnvelope<{ loggedOut: boolean }>>();
    this.markHttpHealthy(true);
  }

  async getStationSnapshot(): Promise<StationStateSnapshot> {
    const payload = await this.gatewayApi.getStationSnapshot<ApiEnvelope<StationStateSnapshot>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getCountStats(): Promise<CountStats> {
    const payload = await this.gatewayApi.getStationStats<ApiEnvelope<CountStats>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async startStation(): Promise<void> {
    const snapshot = await this.getStationSnapshot();
    const payload: StartBatchRequest = {
      recipeId: String(snapshot?.activeRecipeId ?? '').trim() || 'default_recipe',
    };
    const batchId = String(snapshot?.batchId ?? '').trim();
    if (batchId) payload.batchId = batchId;
    const created = await this.actionApi.submitStartBatchAction<ApiEnvelope<ActionJobRecord<{ started?: boolean; message?: string }>>>(payload);
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('start_batch_job_submit_failed');
    await this.awaitActionJob<{ started?: boolean; message?: string }>(jobId);
  }

  async stopStation(): Promise<void> {
    const payload: EmptyActionRequest = {};
    const created = await this.actionApi.submitStopStationAction<ApiEnvelope<ActionJobRecord<{ stopped?: boolean; message?: string }>>>(payload);
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('stop_station_job_submit_failed');
    await this.awaitActionJob<{ stopped?: boolean; message?: string }>(jobId);
  }

  async resetFault(): Promise<void> {
    const created = await this.actionApi.submitResetStationAction<ApiEnvelope<ActionJobRecord<{ reset?: boolean; message?: string }>>>({});
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('reset_station_job_submit_failed');
    await this.awaitActionJob<{ reset?: boolean; message?: string }>(jobId);
  }

  async setMaintenanceMode(enabled: boolean): Promise<StationStateSnapshot> {
    const payload: MaintenanceModeRequest = { enabled };
    const created = await this.actionApi.submitMaintenanceModeAction<ApiEnvelope<ActionJobRecord<StationStateSnapshot>>>(payload);
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('maintenance_action_job_submit_failed');
    return await this.awaitActionJob<StationStateSnapshot>(jobId);
  }

  async newBatch(): Promise<string> {
    const payload: EmptyActionRequest = {};
    const created = await this.actionApi.submitCreateBatchAction<ApiEnvelope<ActionJobRecord<{ batchId: string }>>>(payload);
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('create_batch_job_submit_failed');
    const completed = await this.awaitActionJob<{ batchId: string }>(jobId);
    return String(completed?.batchId ?? '');
  }

  async getResults(query?: ResultQuery): Promise<InspectionResult[]> {
    const payload = await this.gatewayApi.getInspectionResults<ApiEnvelope<InspectionResult[]>>(toInspectionResultsParams(query));
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getResultStatistics(query?: ResultStatisticsQuery): Promise<ResultStatisticsSnapshot> {
    const payload = await this.gatewayApi.getInspectionResultStatistics<ApiEnvelope<ResultStatisticsSnapshot>>(toInspectionStatisticsParams(query));
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getResultDetail(resultId: string): Promise<InspectionResult> {
    const payload = await this.gatewayApi.getInspectionResultDetail<ApiEnvelope<InspectionResult>>({ result_id: resultId });
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getReadModelStatus(): Promise<ReadModelStatus> {
    const payload = await this.gatewayApi.getInspectionReadModelStatus<ApiEnvelope<ReadModelStatus>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async repairReadModel(): Promise<ReadModelStatus> {
    const payload = await this.gatewayApi.repairInspectionReadModel<ApiEnvelope<ReadModelStatus>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getRecipes(): Promise<RecipeProfile[]> {
    const payload = await this.gatewayApi.getRecipes<ApiEnvelope<RecipeProfile[]>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async saveRecipe(recipe: RecipeProfile): Promise<RecipeProfile> {
    const payload = await this.gatewayApi.saveRecipe<ApiEnvelope<RecipeProfile>>(toSaveRecipeRequest(recipe));
    this.markHttpHealthy(true);
    return payload.data;
  }

  async activateRecipe(recipeId: string): Promise<void> {
    const payload: SwitchRecipeRequest = { recipeId, dryRun: false };
    const created = await this.actionApi.submitSwitchRecipeAction<ApiEnvelope<ActionJobRecord<{ activation?: unknown }>>>(payload);
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('switch_recipe_job_submit_failed');
    await this.awaitActionJob<{ activation?: unknown }>(jobId);
  }

  async getDiagnostics(): Promise<DiagnosticsItem[]> {
    const payload = await this.gatewayApi.getDiagnosticsSnapshot<ApiEnvelope<DiagnosticsItem[]>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async runDiagnosticAction(action: DiagnosticAction): Promise<DiagnosticsActionResult> {
    const created = await this.submitDiagnosticAction(action, {});
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('diagnostic_action_job_submit_failed');
    return await this.awaitActionJob<DiagnosticsActionResult>(jobId);
  }

  async exportBatch(batchId: string): Promise<{ url: string; jobId?: string }> {
    const payload: ExportBatchRequest = { batchId };
    const created = await this.actionApi.submitExportBatchAction<ApiEnvelope<ActionJobRecord<{ exportUrl?: string; url?: string }>>>(payload);
    this.markHttpHealthy(true);
    const jobId = String(created.data?.jobId ?? '').trim();
    if (!jobId) throw new Error('export_batch_job_submit_failed');
    const completed = await this.awaitActionJob<{ exportUrl?: string; url?: string }>(jobId);
    const url = String(completed?.exportUrl ?? completed?.url ?? '').trim();
    if (!url) throw new Error('export_batch_result_missing_url');
    return { url, jobId };
  }

  async getActionCatalog(includeNonProduction = false): Promise<ActionCatalogEntry[]> {
    const payload = await this.actionApi.getActionCatalog<ApiEnvelope<ActionCatalogEntry[]>>({ include_non_production: includeNonProduction });
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getActionCapabilityMatrix(): Promise<ActionCapabilityMatrix> {
    const payload = await this.actionApi.getActionCapabilityMatrix<ApiEnvelope<ActionCapabilityMatrix>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  async getAuditEntries(limit = 100, offset = 0): Promise<AuditEntry[]> {
    const payload = await this.gatewayApi.getAuditEntries<ApiEnvelope<AuditEntry[]>>({ limit, offset });
    this.markHttpHealthy(true);
    return payload.data;
  }

  private submitDiagnosticAction(action: DiagnosticAction, payload: EmptyActionRequest): Promise<ApiEnvelope<ActionJobRecord>> {
    switch (action) {
      case 'CAPTURE_FRAME':
        return this.actionApi.submitDiagnosticCaptureFrameAction<ApiEnvelope<ActionJobRecord>>(payload);
      case 'TEST_LIGHTING':
        return this.actionApi.submitDiagnosticTestLightingAction<ApiEnvelope<ActionJobRecord>>(payload);
      case 'TEST_SORT_ACTUATOR':
        return this.actionApi.submitDiagnosticTestSortActuatorAction<ApiEnvelope<ActionJobRecord>>(payload);
      default:
        throw new Error(`unsupported_diagnostic_action:${String(action)}`);
    }
  }

  private isTerminalActionJob(job: ActionJobRecord<any> | null | undefined): boolean {
    const status = String(job?.status ?? '').toUpperCase();
    return status === 'COMPLETED' || status === 'FAILED' || status === 'CANCELLED';
  }

  private normalizeActionJobRecord<T>(value: unknown): ActionJobRecord<T> | null {
    if (!value || typeof value !== 'object') return null;
    const payload = value as Partial<ActionJobUpdate> & { result?: T };
    const jobId = String(payload.jobId ?? '').trim();
    if (!jobId) return null;
    return {
      jobId,
      kind: typeof payload.kind === 'string' ? payload.kind : undefined,
      status: String(payload.status ?? ''),
      progress: typeof payload.progress === 'number' ? payload.progress : undefined,
      result: payload.result,
      error: payload.error,
      message: typeof payload.message === 'string' ? payload.message : undefined,
    };
  }

  private rememberActionJob<T>(job: ActionJobRecord<T>): ActionJobRecord<T> {
    this.actionJobs.set(job.jobId, job);
    return job;
  }

  private notifyActionJobListeners(job: ActionJobRecord<any>): void {
    const listeners = this.actionJobListeners.get(job.jobId);
    if (!listeners || listeners.size === 0) return;
    listeners.forEach((listener) => listener(job));
    if (this.isTerminalActionJob(job)) {
      this.actionJobListeners.delete(job.jobId);
    }
  }

  private awaitActionJobPush(jobId: string, timeoutMs: number): Promise<ActionJobRecord<any> | null> {
    const cached = this.actionJobs.get(jobId);
    if (cached && this.isTerminalActionJob(cached)) {
      return Promise.resolve(cached);
    }
    return new Promise((resolve) => {
      const waitMs = Math.max(10, timeoutMs);
      const listeners = this.actionJobListeners.get(jobId) ?? new Set<ActionJobListener>();
      const listener: ActionJobListener = (job) => {
        cleanup();
        resolve(job);
      };
      const cleanup = () => {
        globalThis.clearTimeout(timer);
        const current = this.actionJobListeners.get(jobId);
        current?.delete(listener);
        if (current && current.size === 0) {
          this.actionJobListeners.delete(jobId);
        }
      };
      const timer = globalThis.setTimeout(() => {
        cleanup();
        resolve(null);
      }, waitMs);
      listeners.add(listener);
      this.actionJobListeners.set(jobId, listeners);
    });
  }

  private unwrapTerminalActionJob<T>(job: ActionJobRecord<T>): T {
    const status = String(job.status ?? '').toUpperCase();
    if (status === 'COMPLETED') {
      if (job.result === undefined) throw new Error('action_job_missing_result');
      return job.result;
    }
    if (status === 'FAILED' || status === 'CANCELLED') {
      throw new Error(String(job.error?.message ?? job.error?.detail ?? job.message ?? `action_job_${status.toLowerCase()}`));
    }
    throw new Error(`action_job_not_terminal:${status}`);
  }

  private async fetchActionJob<T>(jobId: string): Promise<ActionJobRecord<T>> {
    const payload = await this.actionApi.getActionJob<ApiEnvelope<ActionJobRecord<T>>>({ job_id: jobId });
    this.markHttpHealthy(true);
    const normalized = this.normalizeActionJobRecord<T>(payload.data);
    if (!normalized) throw new Error('action_job_payload_invalid');
    return this.rememberActionJob(normalized);
  }

  private async awaitActionJob<T>(jobId: string): Promise<T> {
    const deadline = Date.now() + Math.max(2000, appEnv.gatewayRequestTimeoutMs);
    let last = this.actionJobs.get(jobId) as ActionJobRecord<T> | undefined;
    while (Date.now() < deadline) {
      if (last && this.isTerminalActionJob(last)) {
        return this.unwrapTerminalActionJob(last);
      }
      const waitBudget = Math.min(250, Math.max(25, deadline - Date.now()));
      const pushed = await this.awaitActionJobPush(jobId, waitBudget);
      if (pushed) {
        last = pushed as ActionJobRecord<T>;
        if (this.isTerminalActionJob(last)) {
          return this.unwrapTerminalActionJob(last);
        }
        continue;
      }
      last = await this.fetchActionJob<T>(jobId);
      if (this.isTerminalActionJob(last)) {
        return this.unwrapTerminalActionJob(last);
      }
    }
    throw new Error(`action_job_timeout:${String(last?.status ?? 'PENDING')}`);
  }

  private async issueWsTicket(): Promise<WsTicketPayload> {
    const payload = await this.gatewayApi.issueGatewayWsTicket<ApiEnvelope<WsTicketPayload>>();
    this.markHttpHealthy(true);
    return payload.data;
  }

  private handleSocketMessage(raw: { event?: string; type?: string; payload?: unknown; data?: unknown }): void {
    const eventName = raw.event ?? raw.type;
    const payload = raw.payload ?? raw.data;
    if (!eventName) return;
    if (eventName === 'action.job.updated') {
      const job = this.normalizeActionJobRecord(payload);
      if (job) {
        this.rememberActionJob(job);
        this.notifyActionJobListeners(job);
      }
    }
    if (!(eventName in this.handlers)) return;
    (this.handlers[eventName as GatewayEventName] as Set<(jobPayload: unknown) => void>).forEach((handler) => handler(payload));
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

}
