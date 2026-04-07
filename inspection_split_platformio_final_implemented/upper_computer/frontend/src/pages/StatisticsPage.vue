<script setup lang="ts">
import { computed } from 'vue';
import type { EChartsOption } from 'echarts';
import { useInspectionStore } from '@/entities/inspection/store';
import { useStationStore } from '@/entities/station/store';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import KpiChart from '@/widgets/KpiChart.vue';
import SectionCard from '@/widgets/SectionCard.vue';

const stationStore = useStationStore();
const inspectionStore = useInspectionStore();

function percentile(values: number[], p: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
}

const samples = computed(() => [...inspectionStore.recentResults].slice(0, 40).reverse());
const cycleValues = computed(() => samples.value.map((item) => item.cycleMs));
const p95Cycle = computed(() => percentile(cycleValues.value, 95));

const cycleTrendOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' as const },
  grid: { top: 24, left: 24, right: 18, bottom: 28, containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: samples.value.map((_, index) => `#${index + 1}`),
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
      data: samples.value.map((item) => item.cycleMs),
    },
  ],
}));

const decisionStackOption = computed<EChartsOption>(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' as const },
  grid: { top: 24, left: 24, right: 18, bottom: 28, containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: samples.value.map((_, index) => `#${index + 1}`),
    axisLabel: { color: '#94a3b8' },
    axisLine: { lineStyle: { color: '#334155' } },
  },
  yAxis: {
    type: 'value' as const,
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#1e293b' } },
  },
  series: [
    { name: 'OK', type: 'bar' as const, stack: 'decision', data: samples.value.map((item) => item.decision === 'OK' ? 1 : 0) },
    { name: 'NG', type: 'bar' as const, stack: 'decision', data: samples.value.map((item) => item.decision === 'NG' ? 1 : 0) },
    { name: 'RECHECK', type: 'bar' as const, stack: 'decision', data: samples.value.map((item) => item.decision === 'RECHECK' ? 1 : 0) },
  ],
}));

const defectTrendOption = computed<EChartsOption>(() => {
  const defectMap = new Map<string, number>();
  inspectionStore.recentResults.forEach((item) => {
    const key = item.decision === 'OK' ? '无缺陷' : item.defectType ?? '未知';
    defectMap.set(key, (defectMap.get(key) ?? 0) + 1);
  });
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' as const },
    legend: { bottom: 0, textStyle: { color: '#cbd5e1' } },
    series: [
      {
        name: '缺陷分布',
        type: 'pie' as const,
        radius: ['44%', '68%'],
        data: Array.from(defectMap.entries()).map(([name, value]) => ({ name, value })),
        label: { color: '#e2e8f0' },
      },
    ],
  };
});

const recipeYieldOption = computed<EChartsOption>(() => {
  const recipeMap = new Map<string, { ok: number; total: number }>();
  inspectionStore.recentResults.forEach((item) => {
    const current = recipeMap.get(item.recipeName) ?? { ok: 0, total: 0 };
    current.total += 1;
    current.ok += item.decision === 'OK' ? 1 : 0;
    recipeMap.set(item.recipeName, current);
  });
  const labels = Array.from(recipeMap.keys());
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' as const },
    grid: { top: 24, left: 24, right: 18, bottom: 28, containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: labels,
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
        data: labels.map((label) => {
          const current = recipeMap.get(label);
          return current && current.total ? Number(((current.ok / current.total) * 100).toFixed(1)) : 0;
        }),
      },
    ],
  };
});
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />
    <div class="grid gap-4 xl:grid-cols-5">
      <SectionCard title="检测准确率" subtitle="V1.0 验收目标">
        <div class="flex h-full items-center justify-center text-4xl font-semibold text-slate-100">≥ 95%</div>
      </SectionCard>
      <SectionCard title="分拣准确率" subtitle="V1.0 验收目标">
        <div class="flex h-full items-center justify-center text-4xl font-semibold text-slate-100">≥ 98%</div>
      </SectionCard>
      <SectionCard title="单件节拍" subtitle="计划书量化目标">
        <div class="flex h-full items-center justify-center text-4xl font-semibold text-slate-100">≤ 2.5 s</div>
      </SectionCard>
      <SectionCard title="当前良率" subtitle="来自实时统计">
        <div class="flex h-full items-center justify-center text-4xl font-semibold text-sky-200">{{ stationStore.stats.yieldRate.toFixed(1) }}%</div>
      </SectionCard>
      <SectionCard title="P95 节拍" subtitle="最近 40 件样本">
        <div class="flex h-full items-center justify-center text-4xl font-semibold text-amber-200">{{ p95Cycle.toFixed(0) }} ms</div>
      </SectionCard>
    </div>

    <div class="grid flex-1 gap-4 xl:grid-cols-2">
      <KpiChart title="最近样本节拍趋势" :option="cycleTrendOption" />
      <KpiChart title="最近样本结果堆叠" :option="decisionStackOption" />
      <KpiChart title="缺陷类型分布" :option="defectTrendOption" />
      <KpiChart title="配方维度良率对比" :option="recipeYieldOption" />
      <SectionCard title="稳定性指标" subtitle="把答辩常用指标直接固化在 UI。">
        <div class="grid gap-3 md:grid-cols-2">
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
            <div class="data-label">连续运行次数</div>
            <div class="mt-2 text-2xl font-semibold text-slate-100">{{ stationStore.stats.continuousRunCount }}</div>
          </div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
            <div class="data-label">平均节拍</div>
            <div class="mt-2 text-2xl font-semibold text-slate-100">{{ stationStore.stats.avgCycleMs.toFixed(1) }} ms</div>
          </div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
            <div class="data-label">最近样本数</div>
            <div class="mt-2 text-2xl font-semibold text-slate-100">{{ inspectionStore.recentResults.length }}</div>
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
