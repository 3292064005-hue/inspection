import { computed, reactive, ref, watch } from 'vue';
import type { InspectionResult, ReadModelStatus, ResultQuery } from '@/shared/types/domain';
import { useAuthStore } from '@/entities/auth/store';
import { useAppStore } from '@/entities/app/store';
import { GatewayError } from '@/shared/gateway/errors';
import { getGateway } from '@/shared/gateway/service';
import { fetchWithCache } from '@/shared/query/cache';

const FILTER_STORAGE_KEY = 'inspection-hmi-trace-filters';
const TEMPLATE_STORAGE_KEY = 'inspection-hmi-trace-templates';

interface FilterTemplate {
  id: string;
  name: string;
  filters: ResultQuery;
}

function loadFilterSnapshot(): ResultQuery {
  try {
    const raw = localStorage.getItem(FILTER_STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as ResultQuery;
  } catch {
    return {};
  }
}

function loadTemplates(): FilterTemplate[] {
  try {
    const raw = localStorage.getItem(TEMPLATE_STORAGE_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as FilterTemplate[];
  } catch {
    return [];
  }
}

function toCsv(items: InspectionResult[]): string {
  const headers = ['timestamp', 'batchId', 'recipeName', 'decision', 'defectType', 'qrText', 'cycleMs', 'traceId', 'artifactCount'];
  const rows = items.map((item) => [
    item.timestamp,
    item.batchId,
    item.recipeName,
    item.decision,
    item.defectType ?? '',
    item.qrText ?? '',
    item.cycleMs,
    item.traceId ?? '',
    item.artifactCount ?? 0,
  ]);
  return [headers, ...rows].map((row) => row.map((cell) => `"${String(cell).split('"').join('""')}"`).join(',')).join('\n');
}

function emptyReadModelStatus(): ReadModelStatus {
  return {
    mode: 'UNKNOWN',
    degraded: false,
    lastError: '',
    repairRequired: false,
    projectionAvailable: false,
    fallbackEnabled: false,
    querySurface: 'projection',
    maintenanceState: 'IDLE',
    repairRunning: false,
    lastRepairAt: '',
    lastRepairReason: '',
    sourceSyncToken: '',
    materializedSyncToken: '',
  };
}

function parseReadModelStatusFromError(error: unknown): ReadModelStatus | null {
  const detail = error instanceof GatewayError ? error.detail : undefined;
  if (!detail || typeof detail !== 'object') return null;
  const candidate = (detail as { readModelStatus?: unknown }).readModelStatus;
  if (!candidate || typeof candidate !== 'object') return null;
  const raw = candidate as Partial<ReadModelStatus>;
  return {
    ...emptyReadModelStatus(),
    ...raw,
    mode: String(raw.mode ?? 'UNKNOWN'),
    lastError: String(raw.lastError ?? ''),
    querySurface: String(raw.querySurface ?? 'projection'),
    maintenanceState: String(raw.maintenanceState ?? 'IDLE'),
    lastRepairAt: String(raw.lastRepairAt ?? ''),
    lastRepairReason: String(raw.lastRepairReason ?? ''),
    sourceSyncToken: String(raw.sourceSyncToken ?? ''),
    materializedSyncToken: String(raw.materializedSyncToken ?? ''),
    degraded: Boolean(raw.degraded),
    repairRequired: Boolean(raw.repairRequired),
    projectionAvailable: Boolean(raw.projectionAvailable),
    fallbackEnabled: Boolean(raw.fallbackEnabled),
    repairRunning: Boolean(raw.repairRunning),
  };
}

export function useResultTrace() {
  const gateway = getGateway();
  const appStore = useAppStore();
  const authStore = useAuthStore();
  const loading = ref(false);
  const detailLoading = ref(false);
  const detailError = ref('');
  const items = ref<InspectionResult[]>([]);
  const selectedId = ref('');
  const selectedDetail = ref<InspectionResult | null>(null);
  const page = ref(1);
  const pageSize = ref(12);
  const detailImageMode = ref<'overlay' | 'raw'>('overlay');
  const templates = ref<FilterTemplate[]>(loadTemplates());
  const readModelStatus = ref<ReadModelStatus | null>(null);
  const repairingReadModel = ref(false);
  let detailRequestToken = 0;
  const filters = reactive<ResultQuery>({
    batchId: '',
    recipeId: '',
    qrText: '',
    defectType: '',
    decision: '',
    from: '',
    to: '',
    ...loadFilterSnapshot(),
  });

  watch(filters, () => {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
    page.value = 1;
  }, { deep: true });

  watch(templates, (value) => {
    localStorage.setItem(TEMPLATE_STORAGE_KEY, JSON.stringify(value));
  }, { deep: true });

  const pagedItems = computed(() => {
    const start = (page.value - 1) * pageSize.value;
    return items.value.slice(start, start + pageSize.value);
  });
  const totalPages = computed(() => Math.max(1, Math.ceil(items.value.length / pageSize.value)));
  const selectedListItem = computed(() => items.value.find((item) => item.id === selectedId.value) ?? null);
  const selectedResult = computed<InspectionResult | null>(() => {
    if (selectedDetail.value && selectedDetail.value.id === selectedId.value) {
      return { ...(selectedListItem.value ?? {}), ...selectedDetail.value } as InspectionResult;
    }
    return selectedListItem.value;
  });
  const summary = computed(() => ({
    total: items.value.length,
    ok: items.value.filter((item) => item.decision === 'OK').length,
    ng: items.value.filter((item) => item.decision === 'NG').length,
    recheck: items.value.filter((item) => item.decision === 'RECHECK').length,
  }));
  const batchSummary = computed(() => {
    const bucket = new Map<string, { count: number; ok: number; ng: number }>();
    items.value.forEach((item) => {
      const current = bucket.get(item.batchId) ?? { count: 0, ok: 0, ng: 0 };
      current.count += 1;
      current.ok += item.decision === 'OK' ? 1 : 0;
      current.ng += item.decision === 'NG' ? 1 : 0;
      bucket.set(item.batchId, current);
    });
    return Array.from(bucket.entries()).slice(0, 8);
  });
  const canRepairReadModel = computed(() => ['maintainer', 'admin'].includes(authStore.session?.role ?? ''));
  const hasReadModelIssue = computed(() => !!readModelStatus.value && (readModelStatus.value.degraded || readModelStatus.value.repairRequired || !!readModelStatus.value.lastError));
  const readModelStatusLabel = computed(() => {
    if (!readModelStatus.value) return '结果读模型状态未知';
    if (readModelStatus.value.repairRunning) return '结果读模型正在 repair';
    if (readModelStatus.value.repairRequired) return '结果读模型需要显式 repair';
    if (readModelStatus.value.degraded) return '结果读模型处于降级状态';
    return '结果读模型健康';
  });

  async function refreshReadModelStatus(force = false): Promise<ReadModelStatus | null> {
    if (!gateway.getReadModelStatus) return null;
    try {
      const cacheKey = 'results:read-model-status';
      const status = await fetchWithCache(cacheKey, () => gateway.getReadModelStatus!(), { ttlMs: 4000, force, allowStale: !force });
      readModelStatus.value = status;
      return status;
    } catch {
      return readModelStatus.value;
    }
  }

  async function loadResultDetail(resultId: string, force = false): Promise<void> {
    if (!resultId) {
      selectedDetail.value = null;
      detailError.value = '';
      detailLoading.value = false;
      return;
    }
    if (!gateway.getResultDetail) {
      selectedDetail.value = null;
      detailError.value = '当前网关未提供结果详情接口。';
      return;
    }
    const requestToken = ++detailRequestToken;
    detailLoading.value = true;
    detailError.value = '';
    try {
      const cacheKey = `result-detail:${resultId}`;
      const detail = await fetchWithCache(cacheKey, () => gateway.getResultDetail!(resultId), { ttlMs: 6000, force, allowStale: true });
      if (requestToken !== detailRequestToken) return;
      selectedDetail.value = detail;
      await refreshReadModelStatus(force);
    } catch (error) {
      if (requestToken !== detailRequestToken) return;
      selectedDetail.value = null;
      const embeddedStatus = parseReadModelStatusFromError(error);
      if (embeddedStatus) readModelStatus.value = embeddedStatus;
      detailError.value = error instanceof Error ? error.message : '结果详情加载失败';
      appStore.pushNotice({ level: 'ERROR', title: '结果详情加载失败', message: detailError.value });
      if (!embeddedStatus) await refreshReadModelStatus(true);
    } finally {
      if (requestToken === detailRequestToken) detailLoading.value = false;
    }
  }

  watch(selectedId, (value) => {
    selectedDetail.value = null;
    detailError.value = '';
    if (!value) return;
    void loadResultDetail(value);
  });

  async function loadResults(force = false) {
    loading.value = true;
    try {
      const cacheKey = `results:${JSON.stringify(filters)}`;
      items.value = await fetchWithCache(cacheKey, () => gateway.getResults({ ...filters }), { ttlMs: 6000, force, allowStale: true });
      if (!selectedListItem.value && items.value[0]) {
        selectedId.value = items.value[0].id;
      }
      if (!items.value.some((item) => item.id === selectedId.value)) {
        selectedId.value = items.value[0]?.id ?? '';
      } else if (selectedId.value) {
        void loadResultDetail(selectedId.value, force);
      }
      if (page.value > totalPages.value) page.value = totalPages.value;
      await refreshReadModelStatus(force);
    } catch (error) {
      const embeddedStatus = parseReadModelStatusFromError(error);
      if (embeddedStatus) readModelStatus.value = embeddedStatus;
      const message = error instanceof Error ? error.message : '结果查询失败';
      appStore.pushNotice({ level: 'ERROR', title: '结果查询失败', message });
      if (!embeddedStatus) await refreshReadModelStatus(true);
    } finally {
      loading.value = false;
    }
  }

  async function repairReadModel() {
    if (!gateway.repairReadModel) {
      appStore.pushNotice({ level: 'WARN', title: '网关未提供 repair 能力', message: '当前部署不支持显式 read-model repair。' });
      return;
    }
    repairingReadModel.value = true;
    try {
      readModelStatus.value = await gateway.repairReadModel();
      appStore.pushNotice({ level: 'INFO', title: '结果读模型已 repair', message: '已触发重建并刷新查询状态。' });
      await loadResults(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : '结果读模型 repair 失败';
      appStore.pushNotice({ level: 'ERROR', title: '结果读模型 repair 失败', message });
      await refreshReadModelStatus(true);
    } finally {
      repairingReadModel.value = false;
    }
  }

  function resetFilters() {
    filters.batchId = '';
    filters.recipeId = '';
    filters.qrText = '';
    filters.defectType = '';
    filters.decision = '';
    filters.from = '';
    filters.to = '';
    page.value = 1;
  }

  function nextPage() {
    page.value = Math.min(totalPages.value, page.value + 1);
  }

  function prevPage() {
    page.value = Math.max(1, page.value - 1);
  }

  function toggleDetailImageMode(mode: 'overlay' | 'raw') {
    detailImageMode.value = mode;
  }

  function exportCurrentFilters(scope: 'all' | 'page' = 'all') {
    const selection = scope === 'all' ? items.value : pagedItems.value;
    const csv = toCsv(selection);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    appStore.setExportedUrl(url);
    appStore.pushNotice({ level: 'INFO', title: '筛选结果已导出', message: `共导出 ${selection.length} 条结果。` });
  }

  async function copyField(value?: string, label = '字段') {
    if (!value) {
      appStore.pushNotice({ level: 'WARN', title: `没有可复制的${label}`, message: '当前结果不包含该字段。' });
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      appStore.pushNotice({ level: 'INFO', title: `${label}已复制`, message: value });
    } catch {
      appStore.pushNotice({ level: 'ERROR', title: `复制${label}失败`, message: '浏览器未授予剪贴板权限。' });
    }
  }

  function saveTemplate() {
    const snapshot = JSON.parse(JSON.stringify(filters)) as ResultQuery;
    const activeFields = Object.values(snapshot).filter((value) => value !== '').length;
    if (!activeFields) {
      appStore.pushNotice({ level: 'WARN', title: '没有可保存的筛选条件', message: '请至少填写一个筛选条件。' });
      return;
    }
    templates.value.unshift({
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: `模板 ${templates.value.length + 1}`,
      filters: snapshot,
    });
    templates.value = templates.value.slice(0, 8);
    appStore.pushNotice({ level: 'INFO', title: '筛选模板已保存', message: '后续可一键恢复当前条件。' });
  }

  function applyTemplate(templateId: string) {
    const template = templates.value.find((item) => item.id === templateId);
    if (!template) return;
    Object.assign(filters, template.filters);
  }

  function removeTemplate(templateId: string) {
    templates.value = templates.value.filter((item) => item.id !== templateId);
  }

  return {
    loading,
    detailLoading,
    detailError,
    items,
    pagedItems,
    filters,
    templates,
    summary,
    batchSummary,
    selectedId,
    selectedItem: selectedResult,
    selectedListItem,
    selectedDetail,
    page,
    pageSize,
    totalPages,
    detailImageMode,
    readModelStatus,
    hasReadModelIssue,
    readModelStatusLabel,
    canRepairReadModel,
    repairingReadModel,
    loadResults,
    loadResultDetail,
    refreshReadModelStatus,
    repairReadModel,
    resetFilters,
    nextPage,
    prevPage,
    toggleDetailImageMode,
    exportCurrentFilters,
    copyField,
    saveTemplate,
    applyTemplate,
    removeTemplate,
  };
}
