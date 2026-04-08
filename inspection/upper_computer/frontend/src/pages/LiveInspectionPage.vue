<script setup lang="ts">
import { computed } from 'vue';
import { useInspectionStore } from '@/entities/inspection/store';
import { formatDuration } from '@/shared/utils/format';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import StatusFlow from '@/widgets/StatusFlow.vue';
import LiveImagePanel from '@/widgets/LiveImagePanel.vue';
import SectionCard from '@/widgets/SectionCard.vue';

const inspectionStore = useInspectionStore();
const current = computed(() => inspectionStore.selectedResult);
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />
    <StatusFlow />
    <div class="grid flex-1 gap-4 xl:grid-cols-[1.3fr_0.9fr]">
      <LiveImagePanel />

      <div class="flex flex-col gap-4">
        <SectionCard title="判定解释" subtitle="不只展示结果，还要展示为什么这么判。">
          <div v-if="current" class="space-y-4">
            <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
              <div class="data-label">说明</div>
              <ul class="mt-3 space-y-2 text-sm leading-6 text-slate-200">
                <li v-for="line in current.explanation" :key="line">• {{ line }}</li>
              </ul>
            </div>
            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
                <div class="data-label">规则指标</div>
                <div class="mt-2 text-lg font-semibold text-slate-100">{{ current.metricLabel }}：{{ current.metricValue }}</div>
              </div>
              <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
                <div class="data-label">节拍总计</div>
                <div class="mt-2 text-lg font-semibold text-slate-100">{{ formatDuration(current.cycleMs) }}</div>
              </div>
              <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
                <div class="data-label">二维码</div>
                <div class="mt-2 text-lg font-semibold text-slate-100">{{ current.qrText }}</div>
              </div>
              <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
                <div class="data-label">缺陷类型</div>
                <div class="mt-2 text-lg font-semibold text-slate-100">{{ current.defectType }}</div>
              </div>
            </div>
          </div>
          <div v-else class="rounded-2xl border border-dashed border-slate-700 p-4 text-slate-400">等待判定结果…</div>
        </SectionCard>

        <SectionCard title="阶段耗时拆解" subtitle="答辩时可直接解释感知-决策-执行闭环。">
          <div v-if="current" class="grid gap-3 md:grid-cols-2">
            <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
              <div class="data-label">放行</div>
              <div class="mt-2 text-xl font-semibold text-slate-100">{{ formatDuration(current.breakdown.feedingMs) }}</div>
            </div>
            <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
              <div class="data-label">采图</div>
              <div class="mt-2 text-xl font-semibold text-slate-100">{{ formatDuration(current.breakdown.captureMs) }}</div>
            </div>
            <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
              <div class="data-label">分析</div>
              <div class="mt-2 text-xl font-semibold text-slate-100">{{ formatDuration(current.breakdown.analyzeMs) }}</div>
            </div>
            <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
              <div class="data-label">分拣</div>
              <div class="mt-2 text-xl font-semibold text-slate-100">{{ formatDuration(current.breakdown.sortingMs) }}</div>
            </div>
          </div>
          <div v-else class="rounded-2xl border border-dashed border-slate-700 p-4 text-slate-400">等待节拍拆解…</div>
        </SectionCard>
      </div>
    </div>
  </div>
</template>
