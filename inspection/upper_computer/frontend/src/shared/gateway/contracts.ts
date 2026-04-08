import type {
  AuthSession,
  CameraFrame,
  CameraFrameSemantic,
  CountStats,
  DemoScenario,
  DiagnosticAction,
  DiagnosticsActionResult,
  DiagnosticsItem,
  FaultEvent,
  HeartbeatStatus,
  InspectionResult,
  OrchestratorAdviceEvent,
  ReadModelStatus,
  RecipeProfile,
  ResultQuery,
  StationStateSnapshot,
} from '@/shared/types/domain';

export interface GatewayEventMap {
  'station.state.updated': StationStateSnapshot;
  'station.count.updated': CountStats;
  'inspection.result.created': InspectionResult;
  'fault.raised': FaultEvent;
  'fault.cleared': { id: string };
  'camera.frame': CameraFrame;
  'system.heartbeat': HeartbeatStatus;
  'auth.session': AuthSession;
  'orchestrator.advice': OrchestratorAdviceEvent;
}

export type GatewayEventName = keyof GatewayEventMap;
export type GatewayHandler<T extends GatewayEventName> = (payload: GatewayEventMap[T]) => void;

export type GatewayTransportState = 'IDLE' | 'CONNECTING' | 'ONLINE' | 'RECONNECTING' | 'OFFLINE' | 'ERROR';

export interface GatewayStatusSnapshot {
  mode: 'mock' | 'http';
  transport: GatewayTransportState;
  httpOk: boolean;
  wsOk: boolean;
  retryCount: number;
  lastError: string;
  updatedAt: string;
}

export type GatewayStatusListener = (status: GatewayStatusSnapshot) => void;

export interface DemoScenarioCapability {
  supported: boolean;
  reason: string;
}

export interface GatewayCapabilities {
  demoScenarioControl: DemoScenarioCapability;
  cameraFrameSemantic: CameraFrameSemantic;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  actor: string;
  role: string;
  action: string;
  resource: string;
  result: string;
  correlationId: string;
  details: Record<string, unknown>;
}

export interface HmiGateway {
  connect(): Promise<void>;
  disconnect(): void;
  on<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void;
  off<T extends GatewayEventName>(event: T, handler: GatewayHandler<T>): void;
  onStatusChange?(handler: GatewayStatusListener): () => void;
  getStatus?(): GatewayStatusSnapshot;
  getCapabilities?(): GatewayCapabilities;
  configureDemoScenario?(scenario: DemoScenario): Promise<void>;
  login?(username: string, password: string): Promise<AuthSession>;
  getSession?(): Promise<AuthSession>;
  logout?(): Promise<void>;
  getStationSnapshot(): Promise<StationStateSnapshot>;
  getCountStats(): Promise<CountStats>;
  startStation(): Promise<void>;
  stopStation(): Promise<void>;
  resetFault(): Promise<void>;
  setMaintenanceMode(enabled: boolean): Promise<StationStateSnapshot>;
  newBatch(): Promise<string>;
  getResults(query?: ResultQuery): Promise<InspectionResult[]>;
  getResultDetail?(resultId: string): Promise<InspectionResult>;
  getReadModelStatus?(): Promise<ReadModelStatus>;
  repairReadModel?(): Promise<ReadModelStatus>;
  getRecipes(): Promise<RecipeProfile[]>;
  saveRecipe(recipe: RecipeProfile): Promise<RecipeProfile>;
  activateRecipe(recipeId: string): Promise<void>;
  getDiagnostics(): Promise<DiagnosticsItem[]>;
  runDiagnosticAction(action: DiagnosticAction): Promise<DiagnosticsActionResult>;
  exportBatch(batchId: string): Promise<{ url: string; jobId?: string }>;
  getAuditEntries?(limit?: number, offset?: number): Promise<AuditEntry[]>;
}
