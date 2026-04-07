import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { getGateway } from '@/shared/gateway/service';
import { useAppStore } from '@/entities/app/store';
import { useInspectionStore } from '@/entities/inspection/store';
import type { DiagnosticAction, DiagnosticsItem } from '@/shared/types/domain';
import { fetchWithCache, invalidateCache } from '@/shared/query/cache';
import { deriveMaintenanceState } from '@/processes/maintenance-mode/machine';

const cooldownMs = 6500;

export function useDiagnostics() {
  const gateway = getGateway();
  const appStore = useAppStore();
  const inspectionStore = useInspectionStore();
  const items = ref<DiagnosticsItem[]>([]);
  const loading = ref(false);
  const actionBusy = ref<DiagnosticAction | ''>('');
  const nowTick = ref(Date.now());
  const actionLockUntil = ref<Record<DiagnosticAction, number>>({
    CAPTURE_FRAME: 0,
    TEST_LIGHTING: 0,
    TEST_SORT_ACTUATOR: 0,
  });

  async function load(force = false) {
    loading.value = true;
    try {
      items.value = await fetchWithCache('diagnostics:list', () => gateway.getDiagnostics(), { ttlMs: 4000, force, allowStale: true });
    } catch (error) {
      appStore.pushNotice({ level: 'ERROR', title: '诊断读取失败', message: error instanceof Error ? error.message : '未知错误' });
    } finally {
      loading.value = false;
    }
  }

  const cooldownRemaining = computed<Record<DiagnosticAction, number>>(() => ({
    CAPTURE_FRAME: Math.max(0, actionLockUntil.value.CAPTURE_FRAME - nowTick.value),
    TEST_LIGHTING: Math.max(0, actionLockUntil.value.TEST_LIGHTING - nowTick.value),
    TEST_SORT_ACTUATOR: Math.max(0, actionLockUntil.value.TEST_SORT_ACTUATOR - nowTick.value),
  }));

  const maintenanceState = computed(() => deriveMaintenanceState({
    enabled: appStore.maintenanceMode,
    busy: actionBusy.value !== '',
    hasCooldown: Object.values(cooldownRemaining.value).some((value) => value > 0),
  }));

  async function run(action: DiagnosticAction) {
    if (!appStore.maintenanceMode) {
      appStore.pushNotice({ level: 'WARN', title: '维护模式未开启', message: '危险动作已锁定，请先开启维护模式。' });
      return;
    }

    if (cooldownRemaining.value[action] > 0) {
      appStore.pushNotice({ level: 'WARN', title: '动作冷却中', message: `请等待 ${Math.ceil(cooldownRemaining.value[action] / 1000)} 秒后再执行。` });
      return;
    }

    const confirmed = await appStore.confirmAction({
      title: '执行维护动作？',
      message: '该动作会写入事件时间轴，并可能改变工位状态。确认继续？',
      tone: 'WARN',
      confirmLabel: '执行动作',
    });
    if (!confirmed) return;

    actionBusy.value = action;
    actionLockUntil.value[action] = Date.now() + cooldownMs;
    try {
      const result = await gateway.runDiagnosticAction(action);
      if (result.frame) inspectionStore.applyFrame(result.frame);
      if (result.updatedItems) items.value = result.updatedItems;
      invalidateCache('diagnostics:');
      inspectionStore.pushTimeline('维护动作执行', `${action} / ${result.message}`, result.success ? 'WARN' : 'ERROR');
      appStore.pushNotice({ level: result.success ? 'INFO' : 'ERROR', title: '维护动作结果', message: result.message });
    } catch (error) {
      appStore.pushNotice({ level: 'ERROR', title: '维护动作失败', message: error instanceof Error ? error.message : '未知错误' });
    } finally {
      actionBusy.value = '';
    }
  }

  let timer: ReturnType<typeof setInterval> | null = null;

  onMounted(() => {
    void load();
    timer = setInterval(() => {
      nowTick.value = Date.now();
    }, 500);
  });

  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
  });

  return { items, loading, actionBusy, cooldownRemaining, maintenanceState, load, run };
}
