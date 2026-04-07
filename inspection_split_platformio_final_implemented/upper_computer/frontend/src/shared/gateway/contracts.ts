import type {
  AuthSession,
  CameraFrame,
  CountStats,
  DemoScenario,
  DiagnosticAction,
  DiagnosticsActionResult,
  DiagnosticsItem,
  FaultEvent,
  HeartbeatStatus,
  InspectionResult,
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
  configureDemoScenario?(scenario: DemoScenario): Promise<void>;
  login?(username: string, password: string): Promise<AuthSession>;
  getSession?(): Promise<AuthSession>;
  logout?(): Promise<void>;
  getStationSnapshot(): Promise<StationStateSnapshot>;
  getCountStats(): Promise<CountStats>;
  startStation(): Promise<void>;
  stopStation(): Promise<void>;
  resetFault(): Promise<void>;
  newBatch(): Promise<string>;
  getResults(query?: ResultQuery): Promise<InspectionResult[]>;
  getResultDetail?(resultId: string): Promise<InspectionResult>;
  getRecipes(): Promise<RecipeProfile[]>;
  saveRecipe(recipe: RecipeProfile): Promise<RecipeProfile>;
  activateRecipe(recipeId: string): Promise<void>;
  getDiagnostics(): Promise<DiagnosticsItem[]>;
  runDiagnosticAction(action: DiagnosticAction): Promise<DiagnosticsActionResult>;
  exportBatch(batchId: string): Promise<{ url: string; jobId?: string }>;
  getAuditEntries?(limit?: number, offset?: number): Promise<AuditEntry[]>;
}
