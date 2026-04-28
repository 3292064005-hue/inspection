import { mockActionCatalog } from '@/mocks/generated/actionCatalog';
import type {
  ActionCapabilityMatrix,
  ActionCatalogEntry,
  CameraFrame,
  CountStats,
  AuthSession,
  DemoScenario,
  DiagnosticAction,
  DiagnosticsActionResult,
  DiagnosticsItem,
  FaultEvent,
  HeartbeatStatus,
  InspectionResult,
  ObservedInspectionResult,
  ReadModelStatus,
  RecipeProfile,
  ResultQuery,
  ResultStatisticsQuery,
  ResultStatisticsSnapshot,
  StationPhase,
  StationStateSnapshot,
  TraceBundle,
} from '@/shared/types/domain';
import type {
  GatewayCapabilities,
  GatewayEventMap,
  GatewayEventName,
  GatewayHandler,
  GatewayStatusListener,
  GatewayStatusSnapshot,
  HmiGateway,
} from '@/shared/gateway/contracts';
import { appEnv } from '@/shared/config/env';

type HandlerSet<T extends GatewayEventName> = Set<GatewayHandler<T>>;

interface InternalState {
  snapshot: StationStateSnapshot;
  stats: CountStats;
  recipes: RecipeProfile[];
  results: InspectionResult[];
  faults: FaultEvent[];
  diagnostics: DiagnosticsItem[];
  readModelStatus: ReadModelStatus;
}

function nowIso(): string {
  return new Date().toISOString();
}

function randomId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function clampPercent(value: number): number {
  return Number(Math.max(0, Math.min(100, value)).toFixed(1));
}

function makeFrameSvg(decision: string, recipeName: string, cycle: number): string {
  const color =
    decision === 'OK' ? '#22c55e' : decision === 'NG' ? '#ef4444' : decision === 'RECHECK' ? '#f59e0b' : '#38bdf8';

  const svg = `
  <svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
    <defs>
      <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#0f172a" />
        <stop offset="100%" stop-color="#1e293b" />
      </linearGradient>
    </defs>
    <rect width="960" height="540" fill="url(#bg)" rx="24" />
    <rect x="140" y="90" width="680" height="360" rx="24" fill="#0b1220" stroke="#38bdf8" stroke-opacity="0.5" stroke-width="3" />
    <rect x="280" y="150" width="400" height="240" rx="24" fill="#111827" stroke="${color}" stroke-width="6" />
    <rect x="322" y="184" width="130" height="130" rx="16" fill="#38bdf8" fill-opacity="0.18" stroke="#38bdf8" stroke-dasharray="10 8" />
    <text x="480" y="420" fill="#e2e8f0" font-size="24" text-anchor="middle" font-family="Arial">Recipe: ${recipeName}</text>
    <text x="480" y="454" fill="#94a3b8" font-size="18" text-anchor="middle" font-family="Arial">Cycle #${cycle}</text>
    <text x="480" y="290" fill="${color}" font-size="72" font-weight="700" text-anchor="middle" font-family="Arial">${decision}</text>
  </svg>
  `;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function createStatus(transport: GatewayStatusSnapshot['transport'], retryCount = 0, lastError = '', wsOk = true): GatewayStatusSnapshot {
  return {
    mode: 'mock',
    transport,
    httpOk: true,
    wsOk,
    retryCount,
    lastError,
    updatedAt: nowIso(),
  };
}

export class MockGateway implements HmiGateway {
  private handlers: Partial<{ [K in GatewayEventName]: HandlerSet<K> }> = {};
  private statusListeners = new Set<GatewayStatusListener>();
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private scheduledTimeouts = new Set<ReturnType<typeof setTimeout>>();
  private running = false;
  private runToken = 0;
  private scenario: DemoScenario = appEnv.demoScenario;
  private status = createStatus('IDLE');

  private session: AuthSession = {
    username: 'operator',
    displayName: 'Mock 操作员',
    role: 'operator',
    issuedAt: nowIso(),
    expiresAt: new Date(Date.now() + 12 * 60 * 60 * 1000).toISOString(),
    lastSeenAt: nowIso(),
  };

  private state: InternalState = {
    snapshot: {
      phase: 'IDLE',
      mode: 'IDLE',
      batchId: 'BATCH-20260331-001',
      activeRecipeId: 'recipe-cap-red',
      activeRecipeName: '红盖瓶盖检测',
      cycleIndex: 0,
      lastUpdatedAt: nowIso(),
      guidance: '工位待机，可开始单件自动检测。',
      supervisorMode: 'PAUSED',
      maintenance: {
        requested: false,
        enabled: false,
        transitionState: 'LOCKED',
        supervisorMode: 'PAUSED',
        source: 'mock_gateway',
      },
    },
    stats: {
      total: 0,
      ok: 0,
      ng: 0,
      recheck: 0,
      yieldRate: 0,
      continuousRunCount: 0,
      avgCycleMs: 0,
    },
    recipes: [
      {
        id: 'recipe-cap-red',
        name: '红盖瓶盖检测',
        version: '1.0.0',
        targetPart: '红色盖体',
        roi: [240, 120, 520, 300],
        qrRoi: [320, 160, 160, 160],
        thresholdsSummary: 'HSV 红色阈值 + 面积下限 + 二维码 ROI',
        sortRules: [
          { condition: 'decision == OK', action: 'BOX_OK' },
          { condition: 'decision == NG', action: 'BOX_NG' },
          { condition: 'decision == RECHECK', action: 'BOX_RECHECK' },
        ],
        enabled: true,
        updatedAt: nowIso(),
        updatedBy: 'system',
        changeNote: '默认演示配方',
      },
      {
        id: 'recipe-tray-green',
        name: '绿色托盘方向判定',
        version: '1.1.0',
        targetPart: '绿色托盘',
        roi: [220, 100, 560, 320],
        qrRoi: [280, 180, 180, 120],
        thresholdsSummary: 'HSV 绿色阈值 + 长宽比 + 缺口方向',
        sortRules: [
          { condition: 'decision == OK', action: 'BOX_OK' },
          { condition: 'decision != OK', action: 'BOX_NG' },
        ],
        enabled: false,
        updatedAt: nowIso(),
        updatedBy: 'system',
        changeNote: '演示方向性检测',
      },
    ],
    readModelStatus: {
      mode: 'HOT',
      degraded: false,
      lastError: '',
      repairRequired: false,
      projectionAvailable: true,
      fallbackEnabled: false,
      querySurface: 'projection',
      maintenanceState: 'IDLE',
      repairRunning: false,
      lastRepairAt: '',
      lastRepairReason: '',
      sourceSyncToken: 'mock-source-token',
      materializedSyncToken: 'mock-source-token',
    },
    diagnostics: [
      {
        id: 'ros2-node',
        name: 'ROS2 节点',
        value: 'inspection_hmi / station_bridge / vision_processing',
        status: 'ONLINE',
        note: '节点在线，消息频率稳定',
      },
      {
        id: 'serial-link',
        name: 'STM32 串口链路',
        value: '/dev/ttyUSB0 @ 115200',
        status: 'ONLINE',
        note: '心跳正常，无丢包',
      },
      {
        id: 'camera-stream',
        name: 'ESP32-S3 图像链路',
        value: 'JPEG 640×480 / 8 FPS',
        status: 'DEGRADED',
        note: '偶发 1~2 帧延迟，可继续运行',
      },
      {
        id: 'lighting',
        name: '补光状态',
        value: 'PWM 72%',
        status: 'ONLINE',
        note: '亮度稳定',
      },
      {
        id: 'sort-actuator',
        name: '分拣执行器',
        value: 'Servo #2',
        status: 'ONLINE',
        note: '复位时间 260 ms',
      },
    ],
    results: [],
    faults: [],
  };

  async connect(): Promise<void> {
    this.setStatus('CONNECTING');
    this.emit('station.state.updated', this.state.snapshot);
    this.emit('station.count.updated', this.state.stats);
    this.emit('auth.session', this.session);
    this.emit('camera.frame', {
      url: makeFrameSvg('READY', this.state.snapshot.activeRecipeName, 0),
      capturedAt: nowIso(),
      annotated: true,
      semantic: 'LATEST_RESULT_FRAME',
      sourceEvent: 'inspection.result.observed',
      description: '最近一次演示结果对应的图像快照。',
    });
    this.startHeartbeat();
    this.setStatus('ONLINE');
  }

  disconnect(): void {
    this.running = false;
    this.runToken += 1;
    this.stopHeartbeat();
    this.clearScheduledTimeouts();
    this.setStatus('OFFLINE');
  }

  on<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void {
    const current = (this.handlers[event] as HandlerSet<T> | undefined) ?? new Set<GatewayHandler<T>>();
    current.add(handler);
    this.handlers[event] = current as HandlerSet<any>;
  }

  off<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void {
    const current = this.handlers[event] as HandlerSet<T> | undefined;
    current?.delete(handler);
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
      demoScenarioControl: { supported: true, reason: '' },
      cameraFrameSemantic: 'LATEST_RESULT_FRAME',
    };
  }

  async configureDemoScenario(scenario: DemoScenario): Promise<void> {
    this.scenario = scenario;
    this.patchSnapshot({ guidance: `演示场景已切换：${scenario}` });
  }

  async login(_username: string, _password: string): Promise<AuthSession> {
    this.session = { ...this.session, lastSeenAt: nowIso() };
    return { ...this.session };
  }

  async getSession(): Promise<AuthSession> {
    this.session = { ...this.session, lastSeenAt: nowIso() };
    return { ...this.session };
  }

  async logout(): Promise<void> {
    return Promise.resolve();
  }

  async getStationSnapshot(): Promise<StationStateSnapshot> {
    return { ...this.state.snapshot };
  }

  async getCountStats(): Promise<CountStats> {
    return { ...this.state.stats };
  }

  async startStation(): Promise<void> {
    if (this.state.snapshot.phase === 'FAULT' || this.running) return;
    this.running = true;
    this.runToken += 1;
    this.patchSnapshot({
      mode: 'AUTO',
      phase: 'READY',
      guidance: '自动循环已启动，等待单件放行。',
    });
    this.runCycle(this.runToken);
  }

  async stopStation(): Promise<void> {
    this.running = false;
    this.runToken += 1;
    this.clearScheduledTimeouts();
    this.patchSnapshot({
      mode: 'IDLE',
      phase: 'IDLE',
      guidance: '工位已停止。',
    });
  }

  async resetFault(): Promise<void> {
    this.running = false;
    this.runToken += 1;
    this.clearScheduledTimeouts();

    const latestFault = this.state.faults[0];
    if (latestFault) this.emit('fault.cleared', { id: latestFault.id });

    this.patchSnapshot({
      mode: 'IDLE',
      phase: 'IDLE',
      guidance: '故障已复位，可重新启动。',
    });
  }

  async setMaintenanceMode(enabled: boolean): Promise<StationStateSnapshot> {
    this.patchSnapshot({
      mode: enabled ? 'DEBUG' : 'IDLE',
      guidance: enabled ? '维护模式已生效，可执行手动单步动作。' : '已退出维护模式，恢复运行保护状态。',
      supervisorMode: enabled ? 'MAINTENANCE' : 'PAUSED',
      maintenance: {
        requested: enabled,
        enabled,
        transitionState: enabled ? 'ENABLED' : 'LOCKED',
        supervisorMode: enabled ? 'MAINTENANCE' : 'PAUSED',
        source: 'mock_gateway',
      },
    });
    return { ...this.state.snapshot, maintenance: { ...this.state.snapshot.maintenance } };
  }

  async newBatch(): Promise<string> {
    const batchId = `BATCH-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${String(this.state.stats.total + 1).padStart(3, '0')}`;
    this.state.stats = {
      total: 0,
      ok: 0,
      ng: 0,
      recheck: 0,
      yieldRate: 0,
      continuousRunCount: 0,
      avgCycleMs: 0,
    };
    this.patchSnapshot({
      batchId,
      cycleIndex: 0,
      guidance: '已创建新批次，统计已清零。',
    });
    this.emit('station.count.updated', this.state.stats);
    return batchId;
  }

  async getResults(query?: ResultQuery): Promise<InspectionResult[]> {
    let results = [...this.state.results];
    const { batchId, recipeId, decision, defectType, qrText, from, to } = query ?? {};
    if (batchId) results = results.filter((item) => item.batchId.includes(batchId));
    if (recipeId) results = results.filter((item) => item.recipeId === recipeId);
    if (decision) results = results.filter((item) => item.decision === decision);
    if (defectType) results = results.filter((item) => (item.defectType ?? '').includes(defectType));
    if (qrText) results = results.filter((item) => (item.qrText ?? '').includes(qrText));
    if (from) {
      const fromIso = new Date(from).toISOString();
      results = results.filter((item) => item.timestamp >= fromIso);
    }
    if (to) {
      const toIso = new Date(to).toISOString();
      results = results.filter((item) => item.timestamp <= toIso);
    }
    return results;
  }


  async getResultStatistics(query?: ResultStatisticsQuery): Promise<ResultStatisticsSnapshot> {
    const results = await this.getResults(query);
    const ordered = [...results].sort((left, right) => String(right.timestamp).localeCompare(String(left.timestamp)));
    const sampleLimit = Math.max(1, Number(query?.sampleLimit ?? 120));
    const cycleValues = ordered.map((item) => item.cycleMs).filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);
    const percentileIndex = cycleValues.length ? Math.min(cycleValues.length - 1, Math.max(0, Math.ceil(0.95 * cycleValues.length) - 1)) : 0;
    const okCount = ordered.filter((item) => item.decision === 'OK').length;
    const ngCount = ordered.filter((item) => item.decision === 'NG').length;
    const recheckCount = ordered.filter((item) => item.decision === 'RECHECK').length;
    const defectCounts = new Map<string, number>();
    const recipeCounts = new Map<string, { recipeName: string; total: number; okCount: number; ngCount: number; recheckCount: number }>();
    ordered.forEach((item) => {
      const defect = item.decision === 'OK' ? '无缺陷' : item.defectType ?? '未知';
      defectCounts.set(defect, (defectCounts.get(defect) ?? 0) + 1);
      const current = recipeCounts.get(item.recipeId) ?? { recipeName: item.recipeName, total: 0, okCount: 0, ngCount: 0, recheckCount: 0 };
      current.total += 1;
      if (item.decision === 'OK') current.okCount += 1;
      else if (item.decision === 'NG') current.ngCount += 1;
      else current.recheckCount += 1;
      recipeCounts.set(item.recipeId, current);
    });
    return {
      filters: {
        batchId: query?.batchId,
        recipeId: query?.recipeId,
        decision: query?.decision || undefined,
        defectType: query?.defectType,
        qrText: query?.qrText,
        from: query?.from,
        to: query?.to,
      },
      summary: {
        total: ordered.length,
        okCount,
        ngCount,
        recheckCount,
        yieldRate: ordered.length ? Number((okCount / ordered.length).toFixed(4)) : 0,
        avgCycleMs: ordered.length ? Number((ordered.reduce((sum, item) => sum + item.cycleMs, 0) / ordered.length).toFixed(3)) : 0,
        p95CycleMs: cycleValues.length ? Number(cycleValues[percentileIndex].toFixed(3)) : 0,
        sampleCount: Math.min(ordered.length, sampleLimit),
      },
      decisionBreakdown: [
        { decision: 'OK', count: okCount },
        { decision: 'NG', count: ngCount },
        { decision: 'RECHECK', count: recheckCount },
      ].filter((item) => item.count > 0),
      defectBreakdown: Array.from(defectCounts.entries()).map(([name, count]) => ({ name, count })).sort((left, right) => right.count - left.count || left.name.localeCompare(right.name)),
      recipeBreakdown: Array.from(recipeCounts.entries()).map(([recipeId, value]) => ({ recipeId, recipeName: value.recipeName, total: value.total, okCount: value.okCount, ngCount: value.ngCount, recheckCount: value.recheckCount, yieldRate: value.total ? Number((value.okCount / value.total).toFixed(4)) : 0 })).sort((left, right) => right.total - left.total || left.recipeId.localeCompare(right.recipeId)),
      cycleTrend: ordered.slice(0, sampleLimit).reverse().map((item) => ({ id: item.id, timestamp: item.timestamp, cycleMs: item.cycleMs, decision: item.decision, recipeId: item.recipeId, recipeName: item.recipeName })),
      readModelStatus: { ...this.state.readModelStatus },
    };
  }

  async getResultDetail(resultId: string): Promise<InspectionResult> {
    const item = this.state.results.find((entry) => entry.id === resultId);
    if (!item) throw new Error(`Result not found: ${resultId}`);
    const traceBundle = this.buildTraceBundle(item);
    return {
      ...item,
      traceId: traceBundle.traceId,
      traceUrl: traceBundle.traceUrl,
      artifactCount: traceBundle.artifactCount,
      artifacts: traceBundle.artifacts,
      traceBundle,
    };
  }

  async getReadModelStatus(): Promise<ReadModelStatus> {
    return { ...this.state.readModelStatus };
  }

  async repairReadModel(): Promise<ReadModelStatus> {
    this.state.readModelStatus = {
      ...this.state.readModelStatus,
      degraded: false,
      repairRequired: false,
      projectionAvailable: true,
      repairRunning: false,
      maintenanceState: 'IDLE',
      lastError: '',
      lastRepairAt: nowIso(),
      lastRepairReason: 'mock_manual_repair',
      materializedSyncToken: this.state.readModelStatus.sourceSyncToken,
    };
    return { ...this.state.readModelStatus };
  }

  async getRecipes(): Promise<RecipeProfile[]> {
    return [...this.state.recipes];
  }

  async saveRecipe(recipe: RecipeProfile): Promise<RecipeProfile> {
    const idx = this.state.recipes.findIndex((item) => item.id === recipe.id);
    const nextRecipe = { ...recipe, updatedAt: nowIso() };
    if (idx >= 0) this.state.recipes.splice(idx, 1, nextRecipe);
    else this.state.recipes.unshift(nextRecipe);
    return nextRecipe;
  }

  async activateRecipe(recipeId: string): Promise<void> {
    this.state.recipes = this.state.recipes.map((item) => ({ ...item, enabled: item.id === recipeId }));
    const active = this.state.recipes.find((item) => item.id === recipeId);
    if (!active) return;
    this.patchSnapshot({
      activeRecipeId: active.id,
      activeRecipeName: active.name,
      guidance: `已切换配方：${active.name}`,
    });
  }

  async getDiagnostics(): Promise<DiagnosticsItem[]> {
    return [...this.state.diagnostics];
  }

  async runDiagnosticAction(action: DiagnosticAction): Promise<DiagnosticsActionResult> {
    if (!this.state.snapshot.maintenance.enabled) {
      throw new Error('维护模式未生效，危险动作已锁定。');
    }
    let message = '动作已执行';
    let frame: CameraFrame | undefined;

    if (action === 'CAPTURE_FRAME') {
      frame = {
        url: makeFrameSvg('CAPTURE', this.state.snapshot.activeRecipeName, this.state.snapshot.cycleIndex),
        capturedAt: nowIso(),
        annotated: true,
        semantic: 'LATEST_RESULT_FRAME',
        sourceEvent: 'inspection.result.observed',
        description: '最近一次演示结果对应的图像快照。',
      };
      this.emit('camera.frame', frame);
      message = '已抓拍一帧并更新图像预览。';
    }

    if (action === 'TEST_LIGHTING') {
      this.patchDiagnostic('lighting', {
        value: `PWM ${70 + Math.round(Math.random() * 12)}%`,
        status: 'ONLINE',
        note: '补光测试完成，亮度响应正常。',
      });
      message = '补光测试完成，响应正常。';
    }

    if (action === 'TEST_SORT_ACTUATOR') {
      this.patchDiagnostic('sort-actuator', {
        value: 'Servo #2 / Test Pulse',
        status: 'ONLINE',
        note: '测试动作执行完成，回程正常。',
      });
      message = '分拣执行器测试完成，回程时间正常。';
    }

    return {
      action,
      success: true,
      message,
      executedAt: nowIso(),
      frame,
      updatedItems: [...this.state.diagnostics],
    };
  }

  async exportBatch(batchId: string): Promise<{ url: string; jobId?: string }> {
    return { url: `/exports/${batchId}.zip`, jobId: `mock-export-${batchId}` };
  }

  private startHeartbeat(): void {
    if (this.heartbeatTimer) return;
    this.heartbeatTimer = setInterval(() => {
      const sources: HeartbeatStatus[] = [
        { source: 'ROS2', status: 'ONLINE', latencyMs: this.scenario === 'throughput' ? 18 : 28, timestamp: nowIso() },
        { source: 'STM32', status: 'ONLINE', latencyMs: 16, timestamp: nowIso() },
        {
          source: 'ESP32-S3',
          status: this.running ? (this.scenario === 'stress' ? 'DEGRADED' : 'ONLINE') : 'ONLINE',
          latencyMs: this.running ? (this.scenario === 'throughput' ? 28 : 62) : 41,
          timestamp: nowIso(),
        },
      ];
      sources.forEach((item) => this.emit('system.heartbeat', item));
    }, 1500);
  }

  private stopHeartbeat(): void {
    if (!this.heartbeatTimer) return;
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
  }

  private schedule(delay: number, callback: () => void): void {
    const timer = setTimeout(() => {
      this.scheduledTimeouts.delete(timer);
      callback();
    }, delay);
    this.scheduledTimeouts.add(timer);
  }

  private clearScheduledTimeouts(): void {
    this.scheduledTimeouts.forEach((timer) => clearTimeout(timer));
    this.scheduledTimeouts.clear();
  }

  private runCycle(runToken: number): void {
    if (!this.running || runToken !== this.runToken) return;
    this.clearScheduledTimeouts();
    const phases: Array<{ phase: StationPhase; delay: number; guidance: string }> = [
      { phase: 'FEEDING', delay: 350, guidance: '闸门打开，允许单件进入检测位。' },
      { phase: 'POSITION_CHECK', delay: 320, guidance: '检测位传感器确认工件到位。' },
      { phase: 'CAPTURE', delay: 280, guidance: '触发采图并更新当前帧。' },
      { phase: 'ANALYZE', delay: this.scenario === 'throughput' ? 320 : 460, guidance: '规则视觉分析中，等待判定结果。' },
      { phase: 'SORTING', delay: 300, guidance: '执行分拣动作。' },
      { phase: 'COUNT_UPDATE', delay: 280, guidance: '更新计数、写入日志并回到 READY。' },
    ];

    let totalDelay = 0;
    for (const item of phases) {
      totalDelay += item.delay;
      this.schedule(totalDelay, () => {
        if (!this.running || runToken !== this.runToken) return;
        this.patchSnapshot({ phase: item.phase, guidance: item.guidance });
      });
    }

    const cycleMs = this.scenario === 'throughput'
      ? 1280 + Math.round(Math.random() * 280)
      : 1700 + Math.round(Math.random() * 550);

    this.schedule(totalDelay + 80, () => {
      if (!this.running || runToken !== this.runToken) return;
      const result = this.generateResult(cycleMs);
      this.state.results.unshift(result);
      this.state.results = this.state.results.slice(0, 240);

      this.emit('camera.frame', {
        url: result.overlayUrl ?? result.imageUrl ?? makeFrameSvg(result.decision, result.recipeName, this.state.snapshot.cycleIndex),
        capturedAt: nowIso(),
        annotated: true,
        semantic: 'LATEST_RESULT_FRAME',
        sourceEvent: 'inspection.result.observed',
        description: '最近一次演示结果对应的图像快照。',
      });
      const observed: ObservedInspectionResult = { ...result, decision: undefined, stage: 'OBSERVED' };
      this.emit('inspection.result.observed', observed);
      this.emit('inspection.result.finalized', result);
      this.updateStats(result);
      this.maybeRaiseFault();
      this.patchSnapshot({
        phase: this.state.snapshot.phase === 'FAULT' ? 'FAULT' : 'READY',
        guidance: this.state.snapshot.phase === 'FAULT' ? '当前处于故障锁定，等待人工复位。' : '本周期完成，等待下一件工件。',
      });
      if (this.running && this.state.snapshot.phase !== 'FAULT' && runToken === this.runToken) {
        this.schedule(this.scenario === 'throughput' ? 420 : 900, () => this.runCycle(runToken));
      }
    });
  }

  private generateResult(cycleMs: number): InspectionResult {
    const roll = Math.random();
    const decision = this.scenario === 'stress'
      ? (roll < 0.52 ? 'OK' : roll < 0.86 ? 'NG' : 'RECHECK')
      : this.scenario === 'throughput'
        ? (roll < 0.82 ? 'OK' : roll < 0.94 ? 'NG' : 'RECHECK')
        : (roll < 0.76 ? 'OK' : roll < 0.93 ? 'NG' : 'RECHECK');
    const defectType = decision === 'OK' ? '无' : decision === 'NG'
      ? ['二维码缺失', '颜色偏差', '轮廓缺口', '方向错误'][Math.floor(Math.random() * 4)]
      : '边界样本';
    const recipe = this.state.recipes.find((item) => item.enabled) ?? this.state.recipes[0];
    const cycleIndex = this.state.snapshot.cycleIndex + 1;
    const metricLabel = decision === 'NG' && defectType === '颜色偏差'
      ? '色域偏差'
      : decision === 'NG' && defectType === '轮廓缺口'
        ? '缺口面积比'
        : '规则匹配分';
    const metricValue = decision === 'OK' ? 96.4 : Number((72 + Math.random() * 16).toFixed(1));
    const overlayUrl = makeFrameSvg(decision, recipe.name, cycleIndex);

    this.patchSnapshot({ cycleIndex });

    return {
      id: randomId('result'),
      timestamp: nowIso(),
      batchId: this.state.snapshot.batchId,
      recipeId: recipe.id,
      recipeName: recipe.name,
      decision,
      category: decision === 'OK' ? '合格件' : '异常件',
      defectType,
      qrText: decision === 'NG' && defectType === '二维码缺失' ? '解码失败' : `PART-${1000 + cycleIndex}`,
      metricLabel,
      metricValue,
      cycleMs,
      imageUrl: overlayUrl,
      overlayUrl,
      explanation: decision === 'OK'
        ? ['颜色阈值命中', '二维码解码成功', '轮廓面积位于允许区间内']
        : decision === 'NG'
          ? [`异常类型：${defectType}`, '建议复核当前 ROI 与照明稳定性', '已路由至 NG 料盒']
          : ['处于边界样本区间', '建议进入复检料盒人工确认', '已保留图像与判定记录'],
      breakdown: {
        feedingMs: 320,
        captureMs: 280,
        analyzeMs: Math.max(350, cycleMs - 980),
        sortingMs: 260,
        totalMs: cycleMs,
      },
    };
  }


  async getActionCatalog(includeNonProduction = false): Promise<ActionCatalogEntry[]> {
    return mockActionCatalog
      .filter((item) => includeNonProduction || (item.capability.visibility === 'visible' && item.governance.tier === 'official'))
      .map((item) => ({ ...item, requiredPayload: [...item.requiredPayload] }));
  }

  async getActionCapabilityMatrix(): Promise<ActionCapabilityMatrix> {
    const items = await this.getActionCatalog(true);
    return Object.fromEntries(items.map((item) => [item.kind, item]));
  }


  private buildTraceBundle(result: InspectionResult): TraceBundle {
    const traceId = result.traceId ?? `${result.id}-trace`;
    const artifacts = [
      { kind: 'raw', path: `/artifacts/mock/${traceId}/raw.png`, url: result.imageUrl, source: 'mock' },
      { kind: 'annotated', path: `/artifacts/mock/${traceId}/annotated.png`, url: result.overlayUrl, source: 'mock' },
    ];
    return {
      traceId,
      traceUrl: `/api/v1/replay/traces/${encodeURIComponent(traceId)}`,
      eventCount: 4,
      artifactCount: artifacts.length,
      summary: { decision: result.decision, defectType: result.defectType ?? '', cycleMs: result.cycleMs },
      runArtifacts: { bag_recording: { enabled: false }, evidence_writer: { mode: 'mock', artifactCount: artifacts.length } },
      configSnapshot: { recipeId: result.recipeId, recipeName: result.recipeName, batchId: result.batchId },
      artifacts,
      events: [
        { phase: 'FEEDING', message: '工件已进入检测位。' },
        { phase: 'CAPTURE', message: '采集图像完成。' },
        { phase: 'ANALYZE', message: `判定结果：${result.decision}` },
        { phase: 'SORTING', message: '结果已路由到目标料盒。' },
      ],
    };
  }

  private updateStats(result: InspectionResult): void {
    const next = { ...this.state.stats };
    next.total += 1;
    next.ok += result.decision === 'OK' ? 1 : 0;
    next.ng += result.decision === 'NG' ? 1 : 0;
    next.recheck += result.decision === 'RECHECK' ? 1 : 0;
    next.yieldRate = clampPercent((next.ok / next.total) * 100);
    next.continuousRunCount += 1;
    next.avgCycleMs = Number((((this.state.stats.avgCycleMs * (next.total - 1)) + result.cycleMs) / next.total).toFixed(1));
    this.state.stats = next;
    this.emit('station.count.updated', next);
  }

  private maybeRaiseFault(): void {
    const triggerThreshold = this.scenario === 'stress' ? 0.18 : this.scenario === 'throughput' ? 0.04 : 0.08;
    if (Math.random() > triggerThreshold) return;
    const fault: FaultEvent = {
      id: randomId('fault'),
      code: ['CAMERA_TIMEOUT', 'POSITION_TIMEOUT', 'SERVO_RETURN_SLOW'][Math.floor(Math.random() * 3)],
      level: 'WARN',
      message: '当前周期检测到可恢复异常，已暂停自动循环。',
      timestamp: nowIso(),
      recoverable: true,
      suggestion: '检查检测位是否有卡滞，确认补光与图像链路稳定后执行复位。',
    };
    this.state.faults.unshift(fault);
    this.patchSnapshot({
      phase: 'FAULT',
      mode: 'FAULT',
      guidance: '工位进入故障锁定状态。',
    });
    this.running = false;
    this.runToken += 1;
    this.clearScheduledTimeouts();
    this.emit('fault.raised', fault);
  }

  private patchSnapshot(patch: Partial<StationStateSnapshot>): void {
    this.state.snapshot = {
      ...this.state.snapshot,
      ...patch,
      lastUpdatedAt: nowIso(),
    };
    this.emit('station.state.updated', this.state.snapshot);
  }

  private patchDiagnostic(id: string, patch: Partial<DiagnosticsItem>): void {
    this.state.diagnostics = this.state.diagnostics.map((item) => item.id === id ? { ...item, ...patch } : item);
  }

  private emit<T extends GatewayEventName>(event: T, payload: GatewayEventMap[T]): void {
    const current = this.handlers[event] as HandlerSet<T> | undefined;
    current?.forEach((handler) => handler(payload));
  }

  private setStatus(transport: GatewayStatusSnapshot['transport'], lastError = '', wsOk = true): void {
    this.status = createStatus(transport, 0, lastError, wsOk);
    this.statusListeners.forEach((listener) => listener(this.status));
  }
}
