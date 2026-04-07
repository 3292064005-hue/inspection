<script setup lang="ts">
import { useInspectionStore } from '@/entities/inspection/store';
import { formatDateTime } from '@/shared/utils/format';
import SectionCard from '@/widgets/SectionCard.vue';

const inspectionStore = useInspectionStore();
</script>

<template>
  <SectionCard title="事件时间轴" subtitle="把状态、结果、故障放到同一条时间轴上。">
    <div class="space-y-3">
      <div
        v-for="entry in inspectionStore.timeline.slice(0, 12)"
        :key="entry.id"
        class="relative rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-3 pl-8"
      >
        <span
          class="absolute left-4 top-4 h-2.5 w-2.5 rounded-full"
          :class="entry.tone === 'ERROR' ? 'bg-rose-400' : entry.tone === 'WARN' ? 'bg-amber-400' : 'bg-sky-400'"
        />
        <div class="flex items-center justify-between gap-3">
          <div class="font-medium text-slate-100">{{ entry.title }}</div>
          <div class="text-xs text-slate-400">{{ formatDateTime(entry.time) }}</div>
        </div>
        <div class="mt-2 text-sm leading-6 text-slate-300">{{ entry.detail }}</div>
      </div>
    </div>
  </SectionCard>
</template>
