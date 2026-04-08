import type { AuditEntry, GatewayCapabilities, HmiGateway, GatewayEventName, GatewayHandler, GatewayStatusListener } from '@/shared/gateway/contracts';
import {
  gatewayValidators,
  parseCountStats,
  parseInspectionResult,
  parseDiagnosticsActionResult,
  parseReadModelStatus,
  parseRecipeProfile,
  parseStationStateSnapshot,
  validateDiagnosticsArray,
  validateRecipesArray,
  validateResultsArray,
} from '@/shared/gateway/validation';
import type { AuthSession, DemoScenario, DiagnosticAction, ResultQuery } from '@/shared/types/domain';
import { useAppStore } from '@/entities/app/store';
import { toGatewayError } from '@/shared/gateway/errors';

function reportValidationError(message: string): void {
  try {
    const appStore = useAppStore();
    appStore.pushNotice({ level: 'ERROR', title: '网关数据校验失败', message });
  } catch {
    // ignore when no active pinia yet
  }
}

export class SafeGateway implements HmiGateway {
  private readonly handlerMap = new Map<GatewayHandler<any>, GatewayHandler<any>>();

  constructor(private readonly inner: HmiGateway) {}

  connect(): Promise<void> {
    return this.inner.connect();
  }

  disconnect(): void {
    this.inner.disconnect();
    this.handlerMap.clear();
  }

  onStatusChange?(handler: GatewayStatusListener): () => void {
    return this.inner.onStatusChange?.(handler) ?? (() => undefined);
  }

  getStatus() {
    return this.inner.getStatus?.() ?? {
      mode: 'mock',
      transport: 'OFFLINE',
      httpOk: false,
      wsOk: false,
      retryCount: 0,
      lastError: '',
      updatedAt: new Date().toISOString(),
    };
  }

  getCapabilities(): GatewayCapabilities {
    return this.inner.getCapabilities?.() ?? {
      demoScenarioControl: { supported: false, reason: '当前网关未声明演示场景能力。' },
      cameraFrameSemantic: 'LATEST_RESULT_FRAME',
    };
  }

  configureDemoScenario?(scenario: DemoScenario): Promise<void> {
    return this.inner.configureDemoScenario?.(scenario) ?? Promise.reject(new Error('demo_scenario_control_unavailable'));
  }

  login?(username: string, password: string): Promise<AuthSession> {
    return this.inner.login?.(username, password) ?? Promise.reject(new Error('login not supported'));
  }

  getSession?(): Promise<AuthSession> {
    return this.inner.getSession?.() ?? Promise.reject(new Error('getSession not supported'));
  }

  logout?(): Promise<void> {
    return this.inner.logout?.() ?? Promise.resolve();
  }

  getAuditEntries?(limit?: number, offset?: number): Promise<AuditEntry[]> {
    return this.inner.getAuditEntries?.(limit, offset) ?? Promise.resolve([]);
  }

  on<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void {
    const wrapped: GatewayHandler<T> = (payload) => {
      try {
        const validated = gatewayValidators[event](payload);
        handler(validated as never);
      } catch (error) {
        const gatewayError = toGatewayError(error, `事件 ${event} 校验失败`);
        reportValidationError(gatewayError.message);
      }
    };

    this.handlerMap.set(handler, wrapped);
    this.inner.on(event, wrapped);
  }

  off<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void {
    const wrapped = this.handlerMap.get(handler) as GatewayHandler<T> | undefined;
    if (wrapped) {
      this.inner.off(event, wrapped);
      this.handlerMap.delete(handler);
      return;
    }
    this.inner.off(event, handler);
  }

  async getStationSnapshot() {
    return parseStationStateSnapshot(await this.inner.getStationSnapshot());
  }

  async getCountStats() {
    return parseCountStats(await this.inner.getCountStats());
  }

  startStation(): Promise<void> {
    return this.inner.startStation();
  }

  stopStation(): Promise<void> {
    return this.inner.stopStation();
  }

  resetFault(): Promise<void> {
    return this.inner.resetFault();
  }

  async setMaintenanceMode(enabled: boolean) {
    return parseStationStateSnapshot(await this.inner.setMaintenanceMode(enabled));
  }

  newBatch(): Promise<string> {
    return this.inner.newBatch();
  }

  async getResults(query?: ResultQuery) {
    return validateResultsArray(await this.inner.getResults(query));
  }

  async getResultDetail(resultId: string) {
    if (!this.inner.getResultDetail) {
      throw new Error('getResultDetail not supported');
    }
    return parseInspectionResult(await this.inner.getResultDetail(resultId));
  }

  async getReadModelStatus() {
    if (!this.inner.getReadModelStatus) {
      throw new Error('getReadModelStatus not supported');
    }
    return parseReadModelStatus(await this.inner.getReadModelStatus());
  }

  async repairReadModel() {
    if (!this.inner.repairReadModel) {
      throw new Error('repairReadModel not supported');
    }
    return parseReadModelStatus(await this.inner.repairReadModel());
  }

  async getRecipes() {
    return validateRecipesArray(await this.inner.getRecipes());
  }

  async saveRecipe(recipe: any) {
    return parseRecipeProfile(await this.inner.saveRecipe(recipe));
  }

  activateRecipe(recipeId: string): Promise<void> {
    return this.inner.activateRecipe(recipeId);
  }

  async getDiagnostics() {
    return validateDiagnosticsArray(await this.inner.getDiagnostics());
  }

  async runDiagnosticAction(action: DiagnosticAction) {
    return parseDiagnosticsActionResult(await this.inner.runDiagnosticAction(action));
  }

  async exportBatch(batchId: string) {
    const payload = await this.inner.exportBatch(batchId);
    if (!payload || typeof payload.url !== 'string') {
      throw toGatewayError(undefined, 'Gateway payload validation failed: exportBatch');
    }
    return payload;
  }
}
