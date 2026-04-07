import type {
  ArtifactRef,
  AuthSession,
  CameraFrame,
  CountStats,
  DiagnosticsActionResult,
  DiagnosticsItem,
  FaultEvent,
  HeartbeatStatus,
  InspectionResult,
  RecipeProfile,
  RecipeRule,
  StationStateSnapshot,
  TraceBundle,
} from '@/shared/types/domain';
import type { GatewayEventMap, GatewayEventName } from '@/shared/gateway/contracts';
import { GatewayError } from '@/shared/gateway/errors';

function fail(label: string, detail?: unknown): never {
  throw new GatewayError('VALIDATION', `Gateway payload validation failed: ${label}`, detail);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function expectObject(value: unknown, label: string): Record<string, unknown> {
  if (!isObject(value)) fail(label, value);
  return value;
}

function expectString(value: unknown, label: string): string {
  if (typeof value !== 'string') fail(label, value);
  return value;
}

function expectNumber(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(label, value);
  return value;
}

function expectBoolean(value: unknown, label: string): boolean {
  if (typeof value !== 'boolean') fail(label, value);
  return value;
}

function expectArray<T>(value: unknown, label: string, parser: (value: unknown, label: string) => T): T[] {
  if (!Array.isArray(value)) fail(label, value);
  return value.map((item, index) => parser(item, `${label}[${index}]`));
}

function expectOptional<T>(value: unknown, label: string, parser: (value: unknown, label: string) => T): T | undefined {
  return value === undefined || value === null ? undefined : parser(value, label);
}

function parseRecipeRule(value: unknown, label: string): RecipeRule {
  const object = expectObject(value, label);
  return {
    condition: expectString(object.condition, `${label}.condition`),
    action: expectString(object.action, `${label}.action`),
  };
}

export function parseStationStateSnapshot(value: unknown): StationStateSnapshot {
  const object = expectObject(value, 'StationStateSnapshot');
  return {
    phase: expectString(object.phase, 'StationStateSnapshot.phase') as StationStateSnapshot['phase'],
    mode: expectString(object.mode, 'StationStateSnapshot.mode') as StationStateSnapshot['mode'],
    batchId: expectString(object.batchId, 'StationStateSnapshot.batchId'),
    activeRecipeId: expectString(object.activeRecipeId, 'StationStateSnapshot.activeRecipeId'),
    activeRecipeName: expectString(object.activeRecipeName, 'StationStateSnapshot.activeRecipeName'),
    cycleIndex: expectNumber(object.cycleIndex, 'StationStateSnapshot.cycleIndex'),
    lastUpdatedAt: expectString(object.lastUpdatedAt, 'StationStateSnapshot.lastUpdatedAt'),
    guidance: expectString(object.guidance, 'StationStateSnapshot.guidance'),
  };
}

export function parseCountStats(value: unknown): CountStats {
  const object = expectObject(value, 'CountStats');
  return {
    total: expectNumber(object.total, 'CountStats.total'),
    ok: expectNumber(object.ok, 'CountStats.ok'),
    ng: expectNumber(object.ng, 'CountStats.ng'),
    recheck: expectNumber(object.recheck, 'CountStats.recheck'),
    yieldRate: expectNumber(object.yieldRate, 'CountStats.yieldRate'),
    continuousRunCount: expectNumber(object.continuousRunCount, 'CountStats.continuousRunCount'),
    avgCycleMs: expectNumber(object.avgCycleMs, 'CountStats.avgCycleMs'),
  };
}

export function parseHeartbeatStatus(value: unknown): HeartbeatStatus {
  const object = expectObject(value, 'HeartbeatStatus');
  return {
    source: expectString(object.source, 'HeartbeatStatus.source') as HeartbeatStatus['source'],
    status: expectString(object.status, 'HeartbeatStatus.status') as HeartbeatStatus['status'],
    latencyMs: typeof object.latencyMs === 'number' ? expectNumber(object.latencyMs, 'HeartbeatStatus.latencyMs') : 0,
    message: typeof object.message === 'string' ? expectString(object.message, 'HeartbeatStatus.message') : undefined,
    timestamp: expectString(object.timestamp, 'HeartbeatStatus.timestamp'),
  };
}

export function parseCameraFrame(value: unknown): CameraFrame {
  const object = expectObject(value, 'CameraFrame');
  return {
    url: expectString(object.url, 'CameraFrame.url'),
    capturedAt: expectString(object.capturedAt, 'CameraFrame.capturedAt'),
    annotated: expectBoolean(object.annotated, 'CameraFrame.annotated'),
  };
}

export function parseFaultEvent(value: unknown): FaultEvent {
  const object = expectObject(value, 'FaultEvent');
  return {
    id: expectString(object.id, 'FaultEvent.id'),
    code: expectString(object.code, 'FaultEvent.code'),
    level: expectString(object.level, 'FaultEvent.level') as FaultEvent['level'],
    message: expectString(object.message, 'FaultEvent.message'),
    timestamp: expectString(object.timestamp, 'FaultEvent.timestamp'),
    recoverable: expectBoolean(object.recoverable, 'FaultEvent.recoverable'),
    source: typeof object.source === 'string' ? expectString(object.source, 'FaultEvent.source') : undefined,
    suggestion: expectOptional(object.suggestion, 'FaultEvent.suggestion', expectString),
  };
}

export function parseInspectionResult(value: unknown): InspectionResult {
  const object = expectObject(value, 'InspectionResult');
  const breakdown = expectObject(object.breakdown, 'InspectionResult.breakdown');
  return {
    id: expectString(object.id, 'InspectionResult.id'),
    timestamp: expectString(object.timestamp, 'InspectionResult.timestamp'),
    batchId: expectString(object.batchId, 'InspectionResult.batchId'),
    recipeId: expectString(object.recipeId, 'InspectionResult.recipeId'),
    recipeName: expectString(object.recipeName, 'InspectionResult.recipeName'),
    decision: expectString(object.decision, 'InspectionResult.decision') as InspectionResult['decision'],
    category: expectOptional(object.category, 'InspectionResult.category', expectString),
    defectType: expectOptional(object.defectType, 'InspectionResult.defectType', expectString),
    qrText: expectOptional(object.qrText, 'InspectionResult.qrText', expectString),
    metricValue: expectOptional(object.metricValue, 'InspectionResult.metricValue', expectNumber),
    metricLabel: expectOptional(object.metricLabel, 'InspectionResult.metricLabel', expectString),
    cycleMs: expectNumber(object.cycleMs, 'InspectionResult.cycleMs'),
    traceId: expectOptional(object.traceId, 'InspectionResult.traceId', expectString),
    traceUrl: expectOptional(object.traceUrl, 'InspectionResult.traceUrl', expectString),
    artifactCount: expectOptional(object.artifactCount, 'InspectionResult.artifactCount', expectNumber),
    imageUrl: expectOptional(object.imageUrl, 'InspectionResult.imageUrl', expectString),
    overlayUrl: expectOptional(object.overlayUrl, 'InspectionResult.overlayUrl', expectString),
    artifacts: expectOptional(object.artifacts, 'InspectionResult.artifacts', (item, label) => expectArray(item, label, parseArtifactRef)),
    traceBundle: expectOptional(object.traceBundle, 'InspectionResult.traceBundle', parseTraceBundle),
    explanation: expectArray(object.explanation, 'InspectionResult.explanation', expectString),
    breakdown: {
      feedingMs: expectNumber(breakdown.feedingMs, 'InspectionResult.breakdown.feedingMs'),
      captureMs: expectNumber(breakdown.captureMs, 'InspectionResult.breakdown.captureMs'),
      analyzeMs: expectNumber(breakdown.analyzeMs, 'InspectionResult.breakdown.analyzeMs'),
      sortingMs: expectNumber(breakdown.sortingMs, 'InspectionResult.breakdown.sortingMs'),
      totalMs: expectNumber(breakdown.totalMs, 'InspectionResult.breakdown.totalMs'),
    },
  };
}

export function parseRecipeProfile(value: unknown): RecipeProfile {
  const object = expectObject(value, 'RecipeProfile');
  return {
    id: expectString(object.id, 'RecipeProfile.id'),
    name: expectString(object.name, 'RecipeProfile.name'),
    version: expectString(object.version, 'RecipeProfile.version'),
    targetPart: expectString(object.targetPart, 'RecipeProfile.targetPart'),
    roi: expectArray(object.roi, 'RecipeProfile.roi', expectNumber),
    qrRoi: expectArray(object.qrRoi, 'RecipeProfile.qrRoi', expectNumber),
    thresholdsSummary: expectString(object.thresholdsSummary, 'RecipeProfile.thresholdsSummary'),
    sortRules: expectArray(object.sortRules, 'RecipeProfile.sortRules', parseRecipeRule),
    enabled: expectBoolean(object.enabled, 'RecipeProfile.enabled'),
    updatedAt: expectString(object.updatedAt, 'RecipeProfile.updatedAt'),
    updatedBy: expectOptional(object.updatedBy, 'RecipeProfile.updatedBy', expectString),
    changeNote: expectOptional(object.changeNote, 'RecipeProfile.changeNote', expectString),
  };
}

export function parseDiagnosticsItem(value: unknown): DiagnosticsItem {
  const object = expectObject(value, 'DiagnosticsItem');
  return {
    id: expectString(object.id, 'DiagnosticsItem.id'),
    name: expectString(object.name, 'DiagnosticsItem.name'),
    value: expectString(object.value, 'DiagnosticsItem.value'),
    status: expectString(object.status, 'DiagnosticsItem.status') as DiagnosticsItem['status'],
    note: expectString(object.note, 'DiagnosticsItem.note'),
  };
}

export function parseDiagnosticsActionResult(value: unknown): DiagnosticsActionResult {
  const object = expectObject(value, 'DiagnosticsActionResult');
  return {
    action: expectString(object.action, 'DiagnosticsActionResult.action') as DiagnosticsActionResult['action'],
    success: expectBoolean(object.success, 'DiagnosticsActionResult.success'),
    message: expectString(object.message, 'DiagnosticsActionResult.message'),
    executedAt: expectString(object.executedAt, 'DiagnosticsActionResult.executedAt'),
    frame: expectOptional(object.frame, 'DiagnosticsActionResult.frame', parseCameraFrame),
    updatedItems: expectOptional(object.updatedItems, 'DiagnosticsActionResult.updatedItems', (item, label) => expectArray(item, label, parseDiagnosticsItem)),
  };
}


export function parseAuthSession(value: unknown): AuthSession {
  const object = expectObject(value, 'AuthSession');
  return {
    username: expectString(object.username, 'AuthSession.username'),
    displayName: expectString(object.displayName, 'AuthSession.displayName'),
    role: expectString(object.role, 'AuthSession.role') as AuthSession['role'],
    issuedAt: expectString(object.issuedAt, 'AuthSession.issuedAt'),
    expiresAt: expectString(object.expiresAt, 'AuthSession.expiresAt'),
    lastSeenAt: expectString(object.lastSeenAt, 'AuthSession.lastSeenAt'),
    clientIp: expectOptional(object.clientIp, 'AuthSession.clientIp', expectString),
    userAgent: expectOptional(object.userAgent, 'AuthSession.userAgent', expectString),
  };
}


function parseArtifactRef(value: unknown): ArtifactRef {
  const object = expectObject(value, 'ArtifactRef');
  return {
    kind: expectString(object.kind, 'ArtifactRef.kind'),
    path: expectString(object.path, 'ArtifactRef.path'),
    url: expectOptional(object.url, 'ArtifactRef.url', expectString),
    source: expectOptional(object.source, 'ArtifactRef.source', expectString),
  };
}

function parseTraceBundle(value: unknown): TraceBundle {
  const object = expectObject(value, 'TraceBundle');
  return {
    traceId: expectString(object.traceId, 'TraceBundle.traceId'),
    traceUrl: expectOptional(object.traceUrl, 'TraceBundle.traceUrl', expectString),
    eventCount: expectOptional(object.eventCount, 'TraceBundle.eventCount', expectNumber),
    artifactCount: expectOptional(object.artifactCount, 'TraceBundle.artifactCount', expectNumber),
    runArtifacts: typeof object.runArtifacts === 'object' && object.runArtifacts !== null ? object.runArtifacts as Record<string, unknown> : undefined,
    configSnapshot: typeof object.configSnapshot === 'object' && object.configSnapshot !== null ? object.configSnapshot as Record<string, unknown> : undefined,
    summary: typeof object.summary === 'object' && object.summary !== null ? object.summary as Record<string, unknown> : undefined,
    artifacts: expectOptional(object.artifacts, 'TraceBundle.artifacts', (item, label) => expectArray(item, label, parseArtifactRef)),
    events: expectOptional(object.events, 'TraceBundle.events', (item, label) => expectArray(item, label, (entry, _entryLabel) => expectObject(entry, 'TraceBundle.events[]') as Record<string, unknown>)),
  };
}

function parseFaultCleared(value: unknown): { id: string } {
  const object = expectObject(value, 'FaultCleared');
  return { id: expectString(object.id, 'FaultCleared.id') };
}

export const gatewayValidators: {
  [K in GatewayEventName]: (value: unknown) => GatewayEventMap[K];
} = {
  'station.state.updated': (value) => parseStationStateSnapshot(value),
  'station.count.updated': (value) => parseCountStats(value),
  'inspection.result.created': (value) => parseInspectionResult(value),
  'fault.raised': (value) => parseFaultEvent(value),
  'fault.cleared': (value) => parseFaultCleared(value),
  'camera.frame': (value) => parseCameraFrame(value),
  'system.heartbeat': (value) => parseHeartbeatStatus(value),
  'auth.session': (value) => parseAuthSession(value),
};

export function validateResultsArray(value: unknown): InspectionResult[] {
  return expectArray(value, 'InspectionResult[]', (item) => parseInspectionResult(item));
}

export function validateRecipesArray(value: unknown): RecipeProfile[] {
  return expectArray(value, 'RecipeProfile[]', (item) => parseRecipeProfile(item));
}

export function validateDiagnosticsArray(value: unknown): DiagnosticsItem[] {
  return expectArray(value, 'DiagnosticsItem[]', (item) => parseDiagnosticsItem(item));
}
