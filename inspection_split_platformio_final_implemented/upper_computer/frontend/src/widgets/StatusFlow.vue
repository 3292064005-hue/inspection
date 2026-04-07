<script setup lang="ts">
import { computed } from 'vue';
import { useStationStore } from '@/entities/station/store';
import { phaseLabel, phaseOrder } from '@/shared/utils/status';

const stationStore = useStationStore();

const activeIndex = computed(() => phaseOrder.indexOf(stationStore.snapshot.phase));
</script>

<template>
  <div class="grid gap-3 md:grid-cols-5 xl:grid-cols-9">
    <div
      v-for="(phase, index) in phaseOrder"
      :key="phase"
      class="rounded-2xl border px-3 py-3 text-center transition"
      :class="
        index === activeIndex
          ? 'border-sky-400/40 bg-sky-500/10 text-sky-100'
          : index < activeIndex
            ? 'border-emerald-400/20 bg-emerald-500/5 text-emerald-200'
            : 'border-slate-800/80 bg-slate-900/50 text-slate-400'
      "
    >
      <div class="text-[11px] uppercase tracking-[0.2em]">Step {{ index + 1 }}</div>
      <div class="mt-1 text-sm font-semibold">{{ phaseLabel(phase) }}</div>
    </div>
  </div>
</template>
