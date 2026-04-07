<script setup lang="ts">
import { computed } from 'vue';
import { useAppStore } from '@/entities/app/store';
import { useStationStore } from '@/entities/station/store';
import { useStationControl } from '@/features/station-control/useStationControl';
import { deriveExportFlowState } from '@/processes/export-flow/machine';
import SectionCard from '@/widgets/SectionCard.vue';

const stationStore = useStationStore();
const appStore = useAppStore();
const { actionBusy, primaryActionLabel, onPrimaryAction, createBatch, exportBatch } = useStationControl();

const exportState = computed(() => deriveExportFlowState({
  busy: appStore.exportState === 'requesting',
  exportedUrl: appStore.exportedUrl,
  failed: appStore.exportState === 'failed',
}));
</script>

<template>
  <SectionCard title="主控操作" subtitle="按工位状态智能切换主按钮，所有动作统一走 feature/action 层。">
    <div class="space-y-3">
      <button
        class="w-full rounded-2xl px-4 py-4 text-lg font-semibold transition"
        :class="
          stationStore.snapshot.phase === 'FAULT'
            ? 'bg-rose-500 text-white hover:bg-rose-400'
            : stationStore.isRunning
              ? 'bg-slate-100 text-slate-950 hover:bg-white'
              : 'bg-sky-500 text-white hover:bg-sky-400'
        "
        :disabled="actionBusy || stationStore.connectionState === 'ERROR'"
        @click="onPrimaryAction"
      >
        {{ actionBusy ? `处理中：${appStore.pendingActionLabel || primaryActionLabel}` : primaryActionLabel }}
      </button>

      <div class="grid grid-cols-2 gap-3">
        <button
          class="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm font-medium text-slate-200 hover:border-slate-600 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="actionBusy"
          @click="createBatch"
        >
          新建批次
        </button>
        <button
          class="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm font-medium text-slate-200 hover:border-slate-600 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="actionBusy"
          @click="exportBatch"
        >
          {{ appStore.exportState === 'requesting' ? '导出中…' : '导出当前批次' }}
        </button>
      </div>

      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
        <div class="data-label">运行指引</div>
        <div class="mt-2 text-sm leading-6 text-slate-200">{{ stationStore.snapshot.guidance }}</div>
        <div class="mt-3 flex flex-wrap gap-2 text-xs">
          <span class="status-pill border-slate-700 bg-slate-900 text-slate-300">链路：{{ stationStore.connectionState }}</span>
          <span class="status-pill border-slate-700 bg-slate-900 text-slate-300">模式：{{ stationStore.snapshot.mode }}</span>
          <span class="status-pill border-slate-700 bg-slate-900 text-slate-300">循环：#{{ stationStore.snapshot.cycleIndex }}</span>
          <span class="status-pill border-slate-700 bg-slate-900 text-slate-300">导出：{{ exportState }}</span>
        </div>
      </div>
    </div>
  </SectionCard>
</template>
