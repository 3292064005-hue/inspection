<script setup lang="ts">
import { computed } from 'vue';
import type { EChartsOption } from 'echarts';
import { useInspectionStore } from '@/entities/inspection/store';
import { useStationStore } from '@/entities/station/store';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import { kpiTargets } from '@/shared/config/kpiTargets';
import KpiChart from '@/widgets/KpiChart.vue';
import SectionCard from '@/widgets/SectionCard.vue';

const stationStore = useStationStore();
const inspectionStore = useInspectionStore();

const statistics = computed(() => inspectionStore.statistics);
const summary = computed(() => statistics.value?.summary ?? {
  total: 0,
  okCount: 0,
  ngCount: 0,
  recheckCount: 0,
  yieldRate: 0,
  avgCycleMs: 0,
  p95CycleMs: 0,
  sampleCount: 0,
});
const cycleTrend = computed(() => statistics.value?.cycleTrend ?? []);
const decisionBreakdown = computed(() => statistics.value?.decisionBreakdown ?? []);
const defectBreakdown = computed(() => statistics.value?.defectBreakdown ?? []);
const recipeBreakdown = computed(() => statistics.value?.recipeBreakdown ?? []);

const cycleTrendOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' as const },
  grid: { top: 24, left: 24, right: 18, bottom: 28, containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: cycleTrend.value.map((_, index) => `#${index + 1}`),
    axisLabel: { color: '#94a3b8' },
    axisLine: { lineStyle: { color: '#334155' } },
  },
  yAxis: {
    type: 'value' as const,
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#1e293b' } },
  },
  series: [
    {
      name: '节拍',
      type: 'line' as const,
      smooth: true,
      data: cycleTrend.value.map((item) => item.cycleMs),
    },
  ],
}));

const decisionStackOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' as const },
  grid: { top: 24, left: 24, right: 18, bottom: 28, containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: decisionBreakdown.value.map((item) => item.decision),
    axisLabel: { color: '#94a3b8' },
    axisLine: { lineStyle: { color: '#334155' } },
  },
  yAxis: {
    type: 'value' as const,
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#1e293b' } },
  },
  series: [
    {
      name: '数量',
      type: 'bar' as const,
      data: decisionBreakdown.value.map((item) => item.count),
    },
  ],
}));

const defectTrendOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'item' as const },
  legend: { bottom: 0, textStyle: { color: '#cbd5e1' } },
  series: [
    {
      name: '缺陷分布',
      type: 'pie' as const,
      radius: ['44%', '68%'],
      data: defectBreakdown.value.map((item) => ({ name: item.name, value: item.count })),
      label: { color: '#e2e8f0' },
    },
  ],
}));

const recipeYieldOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' as const },
  grid: { top: 24, left: 24, right: 18, bottom: 28, containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: recipeBreakdown.value.map((item) => item.recipeName),
    axisLabel: { color: '#94a3b8', rotate: 18 },
    axisLine: { lineStyle: { color: '#334155' } },
  },
  yAxis: {
    type: 'value' as const,
    max: 100,
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#1e293b' } },
  },
  series: [
    {
      name: '良率 %',
      type: 'bar' as const,
      data: recipeBreakdown.value.map((item) => Number((item.yieldRate * 100).toFixed(1))),
    },
  ],
}));
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />

    <div class="space-y-3">
      <div class="px-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">验收目标</div>
      <div class="grid gap-4 xl:grid-cols-3">
        <SectionCard title="检测准确率目标" subtitle="V1.0 验收目标">
          <div class="flex h-full items-center justify-center text-4xl font-semibold text-slate-100">{{ kpiTargets.detectionAccuracy }}</div>
        </SectionCard>
        <SectionCard title="分拣准确率目标" subtitle="V1.0 验收目标">
          <div class="flex h-full items-center justify-center text-4xl font-semibold text-slate-100">{{ kpiTargets.sortingAccuracy }}</div>
        </SectionCard>
        <SectionCard title="单件节拍目标" subtitle="计划书量化目标">
          <div class="flex h-full items-center justify-center text-4xl font-semibold text-slate-100">{{ kpiTargets.cycleTime }}</div>
        </SectionCard>
      </div>
    </div>

    <div class="space-y-3">
      <div class="px-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">运行指标</div>
      <div class="grid gap-4 xl:grid-cols-3">
        <SectionCard title="查询良率" subtitle="来自正式统计查询面">
          <div class="flex h-full items-center justify-center text-4xl font-semibold text-sky-200">{{ (summary.yieldRate * 100).toFixed(1) }}%</div>
        </SectionCard>
        <SectionCard title="P95 节拍" subtitle="来自 query-driven 样本窗口">
          <div class="flex h-full items-center justify-center text-4xl font-semibold text-amber-200">{{ summary.p95CycleMs.toFixed(0) }} ms</div>
        </SectionCard>
        <SectionCard title="样本总数" subtitle="与最近结果缓存解耦">
          <div class="flex h-full items-center justify-center text-4xl font-semibold text-emerald-200">{{ summary.total }}</div>
        </SectionCard>
      </div>
    </div>

    <div class="grid flex-1 gap-4 xl:grid-cols-2">
      <KpiChart title="查询样本节拍趋势" :option="cycleTrendOption" />
      <KpiChart title="结果分布" :option="decisionStackOption" />
      <KpiChart title="缺陷类型分布" :option="defectTrendOption" />
      <KpiChart title="配方维度良率对比" :option="recipeYieldOption" />
      <SectionCard title="运行稳定性指标" subtitle="统计页主数据来自结果查询面，运行快照仍展示实时工位指标。">
        <div class="grid gap-3 md:grid-cols-2">
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
            <div class="data-label">连续运行次数</div>
            <div class="mt-2 text-2xl font-semibold text-slate-100">{{ stationStore.stats.continuousRunCount }}</div>
          </div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
            <div class="data-label">实时平均节拍</div>
            <div class="mt-2 text-2xl font-semibold text-slate-100">{{ stationStore.stats.avgCycleMs.toFixed(1) }} ms</div>
          </div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
            <div class="data-label">查询样本窗口</div>
            <div class="mt-2 text-2xl font-semibold text-slate-100">{{ summary.sampleCount }}</div>
          </div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
            <div class="data-label">当前批次</div>
            <div class="mt-2 text-xl font-semibold text-slate-100">{{ stationStore.snapshot.batchId }}</div>
          </div>
        </div>
      </SectionCard>
    </div>
  </div>
</template>
