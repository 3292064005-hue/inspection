<script setup lang="ts">
import { useStationStore } from '@/entities/station/store';
import { formatDuration, formatPercent } from '@/shared/utils/format';
import SectionCard from '@/widgets/SectionCard.vue';

const stationStore = useStationStore();
</script>

<template>
  <SectionCard title="实时统计" subtitle="围绕良率、节拍、连续运行次数展示 KPI。">
    <div class="grid grid-cols-2 gap-3">
      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
        <div class="data-label">总数</div>
        <div class="data-value mt-2">{{ stationStore.stats.total }}</div>
      </div>
      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
        <div class="data-label">OK</div>
        <div class="data-value mt-2 text-emerald-300">{{ stationStore.stats.ok }}</div>
      </div>
      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
        <div class="data-label">NG</div>
        <div class="data-value mt-2 text-rose-300">{{ stationStore.stats.ng }}</div>
      </div>
      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
        <div class="data-label">复检</div>
        <div class="data-value mt-2 text-amber-300">{{ stationStore.stats.recheck }}</div>
      </div>
      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
        <div class="data-label">良率</div>
        <div class="data-value mt-2">{{ formatPercent(stationStore.stats.yieldRate) }}</div>
      </div>
      <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
        <div class="data-label">平均节拍</div>
        <div class="data-value mt-2">{{ formatDuration(stationStore.stats.avgCycleMs) }}</div>
      </div>
    </div>

    <div class="mt-3 rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
      <div class="data-label">连续运行次数</div>
      <div class="mt-2 text-2xl font-semibold text-slate-100">{{ stationStore.stats.continuousRunCount }}</div>
    </div>
  </SectionCard>
</template>
