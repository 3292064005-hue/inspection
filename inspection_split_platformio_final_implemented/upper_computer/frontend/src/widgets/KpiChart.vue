<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { EChartsOption } from 'echarts';
import { BarChart, LineChart, PieChart } from 'echarts/charts';
import { CanvasRenderer } from 'echarts/renderers';
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { init, use } from 'echarts/core';
import type { ECharts } from 'echarts/core';

use([LineChart, BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  title: string;
  option: EChartsOption;
}>();

const container = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;
let resizeObserver: ResizeObserver | null = null;

function render() {
  if (!container.value) return;
  if (!chart) chart = init(container.value);
  chart.setOption(props.option, true);
  chart.resize();
}

onMounted(() => {
  render();
  resizeObserver = new ResizeObserver(() => render());
  if (container.value) resizeObserver.observe(container.value);
});

watch(() => props.option, () => render(), { deep: true });

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  chart?.dispose();
});
</script>

<template>
  <div class="panel p-4">
    <div class="panel-title mb-4">{{ title }}</div>
    <div ref="container" class="h-[280px] w-full" />
  </div>
</template>
