import { computed, ref } from 'vue';
import { getGateway } from '@/shared/gateway/service';
import { useAppStore } from '@/entities/app/store';
import { useStationStore } from '@/entities/station/store';
import { useInspectionStore } from '@/entities/inspection/store';

export function useStationControl() {
  const gateway = getGateway();
  const appStore = useAppStore();
  const stationStore = useStationStore();
  const inspectionStore = useInspectionStore();
  const actionBusy = ref(false);

  const primaryActionLabel = computed(() => {
    if (stationStore.snapshot.phase === 'FAULT') return '故障复位';
    return stationStore.isRunning ? '停止工位' : '启动工位';
  });

  async function runAction(label: string, executor: () => Promise<void>) {
    actionBusy.value = true;
    appStore.setPendingAction(label);
    try {
      await executor();
      appStore.pushNotice({ level: 'INFO', title: label, message: `${label}执行完成。` });
      inspectionStore.pushTimeline('主控操作', `${label}执行完成。`);
    } catch (error) {
      const message = error instanceof Error ? error.message : `${label}失败`;
      appStore.pushNotice({ level: 'ERROR', title: label, message });
      inspectionStore.pushTimeline('主控操作失败', `${label} / ${message}`, 'ERROR');
      throw error;
    } finally {
      actionBusy.value = false;
      appStore.setPendingAction('');
    }
  }

  async function onPrimaryAction() {
    if (stationStore.connectionState === 'OFFLINE' || stationStore.connectionState === 'RECONNECTING') {
      appStore.pushNotice({ level: 'WARN', title: '链路不可用', message: '当前网关不可用，禁止启动工位。' });
      return;
    }

    if (stationStore.snapshot.phase === 'FAULT') {
      await runAction('故障复位', () => gateway.resetFault());
      return;
    }

    if (stationStore.isRunning) {
      const confirmed = await appStore.confirmAction({
        title: '停止当前工位？',
        message: '工位将退出自动循环并回到待机态。',
        tone: 'WARN',
        confirmLabel: '停止工位',
      });
      if (!confirmed) return;
      await runAction('停止工位', () => gateway.stopStation());
      return;
    }

    await runAction('启动工位', () => gateway.startStation());
  }

  async function createBatch() {
    const confirmed = await appStore.confirmAction({
      title: '创建新批次？',
      message: '当前统计将归零，并切换到新的批次号。',
      tone: 'WARN',
      confirmLabel: '创建批次',
    });
    if (!confirmed) return;

    await runAction('新建批次', async () => {
      const batchId = await gateway.newBatch();
      appStore.pushNotice({ level: 'INFO', title: '批次已创建', message: `当前批次：${batchId}` });
    });
  }

  async function exportBatch() {
    appStore.setExportState('requesting');
    try {
      await runAction('导出当前批次', async () => {
        const result = await gateway.exportBatch(stationStore.snapshot.batchId);
        appStore.setExportedUrl(result.url);
        appStore.pushNotice({ level: 'INFO', title: '导出完成', message: `导出路径：${result.url}` });
      });
      appStore.setExportState('ready');
    } catch {
      appStore.setExportState('failed');
    }
  }

  return {
    actionBusy,
    primaryActionLabel,
    onPrimaryAction,
    createBatch,
    exportBatch,
  };
}
