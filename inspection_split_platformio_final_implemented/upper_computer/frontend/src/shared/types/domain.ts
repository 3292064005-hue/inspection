export type StationPhase =
  | 'BOOT'
  | 'IDLE'
  | 'READY'
  | 'FEEDING'
  | 'POSITION_CHECK'
  | 'CAPTURE'
  | 'ANALYZE'
  | 'SORTING'
  | 'COUNT_UPDATE'
  | 'FAULT';

export type StationMode = 'IDLE' | 'AUTO' | 'DEBUG' | 'FAULT';
export type Decision = 'OK' | 'NG' | 'RECHECK';
export type SourceName = 'ROS2' | 'STM32' | 'ESP32-S3' | 'vision' | 'gateway';
export type HealthStatus = 'ONLINE' | 'DEGRADED' | 'OFFLINE';
export type ConnectionState = 'BOOTING' | 'CONNECTING' | 'ONLINE' | 'RECONNECTING' | 'DEGRADED' | 'OFFLINE' | 'ERROR';
export type DiagnosticAction = 'CAPTURE_FRAME' | 'TEST_LIGHTING' | 'TEST_SORT_ACTUATOR';
export type DemoScenario = 'balanced' | 'stress' | 'throughput';
export type UserRole = 'viewer' | 'operator' | 'maintainer' | 'process_engineer' | 'admin';

export interface AuthSession {
  username: string;
  displayName: string;
  role: UserRole;
  issuedAt: string;
  expiresAt: string;
  lastSeenAt?: string;
  clientIp?: string;
  userAgent?: string;
  bootstrap?: boolean;
  mustChangePassword?: boolean;
}

export interface CycleBreakdown {
  feedingMs: number;
  captureMs: number;
  analyzeMs: number;
  sortingMs: number;
  totalMs: number;
}

export interface StationStateSnapshot {
  phase: StationPhase;
  mode: StationMode;
  batchId: string;
  activeRecipeId: string;
  activeRecipeName: string;
  cycleIndex: number;
  lastUpdatedAt: string;
  guidance: string;
}

export interface CountStats {
  total: number;
  ok: number;
  ng: number;
  recheck: number;
  yieldRate: number;
  continuousRunCount: number;
  avgCycleMs: number;
}

export interface ArtifactRef {
  kind: string;
  path: string;
  url?: string;
  source?: string;
}

export interface TraceBundle {
  traceId: string;
  traceUrl?: string;
  eventCount?: number;
  artifactCount?: number;
  runArtifacts?: Record<string, unknown>;
  configSnapshot?: Record<string, unknown>;
  artifacts?: ArtifactRef[];
  summary?: Record<string, unknown>;
  events?: Record<string, unknown>[];
}

export interface InspectionResult {
  id: string;
  timestamp: string;
  batchId: string;
  recipeId: string;
  recipeName: string;
  decision: Decision;
  category?: string;
  defectType?: string;
  qrText?: string;
  metricValue?: number;
  metricLabel?: string;
  cycleMs: number;
  traceId?: string;
  traceUrl?: string;
  artifactCount?: number;
  imageUrl?: string;
  overlayUrl?: string;
  artifacts?: ArtifactRef[];
  traceBundle?: TraceBundle;
  explanation: string[];
  breakdown: CycleBreakdown;
}

export interface FaultEvent {
  id: string;
  code: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  message: string;
  timestamp: string;
  recoverable: boolean;
  source?: string;
  suggestion?: string;
}

export interface RecipeRule {
  condition: string;
  action: string;
}

export interface RecipeProfile {
  id: string;
  name: string;
  version: string;
  targetPart: string;
  roi: number[];
  qrRoi: number[];
  thresholdsSummary: string;
  sortRules: RecipeRule[];
  enabled: boolean;
  updatedAt: string;
  updatedBy?: string;
  changeNote?: string;
}

export interface HeartbeatStatus {
  source: SourceName;
  status: HealthStatus;
  latencyMs?: number;
  message?: string;
  timestamp: string;
}

export interface CameraFrame {
  url: string;
  capturedAt: string;
  annotated: boolean;
}

export interface DiagnosticsItem {
  id: string;
  name: string;
  value: string;
  status: HealthStatus;
  note: string;
}

export interface DiagnosticsActionResult {
  action: DiagnosticAction;
  success: boolean;
  message: string;
  executedAt: string;
  frame?: CameraFrame;
  updatedItems?: DiagnosticsItem[];
}

export interface ResultQuery {
  batchId?: string;
  recipeId?: string;
  decision?: Decision | '';
  defectType?: string;
  qrText?: string;
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}
