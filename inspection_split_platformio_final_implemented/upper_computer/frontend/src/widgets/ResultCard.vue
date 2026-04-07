<script setup lang="ts">
import { computed } from 'vue';
import { useInspectionStore } from '@/entities/inspection/store';
import { formatDuration, formatDateTime } from '@/shared/utils/format';
import { decisionTone } from '@/shared/utils/status';
import SectionCard from '@/widgets/SectionCard.vue';

const inspectionStore = useInspectionStore();
const result = computed(() => inspectionStore.selectedResult);
</script>

<template>
  <SectionCard title="当前判定结果" subtitle="必须解释为什么判为 OK / NG / RECHECK。">
    <div v-if="result" class="space-y-4">
      <div class="flex items-center justify-between">
        <span :class="['status-pill', decisionTone(result.decision)]">{{ result.decision }}</span>
        <span class="text-sm text-slate-400">{{ formatDateTime(result.timestamp) }}</span>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div class="data-label">缺陷类型</div>
          <div class="mt-1 text-base font-semibold text-slate-100">{{ result.defectType }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div class="data-label">二维码 / 编号</div>
          <div class="mt-1 text-base font-semibold text-slate-100">{{ result.qrText }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div class="data-label">{{ result.metricLabel }}</div>
          <div class="mt-1 text-base font-semibold text-slate-100">{{ result.metricValue }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div class="data-label">单件节拍</div>
          <div class="mt-1 text-base font-semibold text-slate-100">{{ formatDuration(result.cycleMs) }}</div>
        </div>
      </div>

      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
        <div class="data-label">节拍拆解</div>
        <div class="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-200">
          <div>放行：{{ formatDuration(result.breakdown.feedingMs) }}</div>
          <div>采图：{{ formatDuration(result.breakdown.captureMs) }}</div>
          <div>分析：{{ formatDuration(result.breakdown.analyzeMs) }}</div>
          <div>分拣：{{ formatDuration(result.breakdown.sortingMs) }}</div>
        </div>
      </div>

      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
        <div class="data-label">规则解释</div>
        <ul class="mt-2 space-y-2 text-sm leading-6 text-slate-200">
          <li v-for="line in result.explanation" :key="line">• {{ line }}</li>
        </ul>
      </div>
    </div>

    <div v-else class="flex h-full items-center justify-center rounded-2xl border border-dashed border-slate-700 text-slate-500">
      等待第一条判定结果
    </div>
  </SectionCard>
</template>
