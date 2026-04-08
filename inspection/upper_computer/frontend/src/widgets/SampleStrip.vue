<script setup lang="ts">
import { useInspectionStore } from '@/entities/inspection/store';
import { formatDateTime } from '@/shared/utils/format';
import { decisionTone } from '@/shared/utils/status';
import SectionCard from '@/widgets/SectionCard.vue';

const inspectionStore = useInspectionStore();
</script>

<template>
  <SectionCard title="最近样本流" subtitle="展示最近 10 个工件，服务于答辩演示和快速追溯。">
    <div class="grid h-full gap-3 md:grid-cols-2 xl:grid-cols-5">
      <article
        v-for="sample in inspectionStore.recentResults.slice(0, 10)"
        :key="sample.id"
        class="cursor-pointer overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950/60 transition hover:border-slate-600"
        @click="inspectionStore.selectResult(sample.id)"
      >
        <img v-if="sample.overlayUrl" :src="sample.overlayUrl" :alt="sample.id" class="h-28 w-full object-cover" />
        <div class="space-y-2 p-3">
          <div class="flex items-center justify-between">
            <span :class="['status-pill', decisionTone(sample.decision)]">{{ sample.decision }}</span>
            <span class="text-[11px] text-slate-400">{{ sample.defectType }}</span>
          </div>
          <div class="text-sm font-medium text-slate-100">{{ sample.recipeName }}</div>
          <div class="text-xs text-slate-400">{{ formatDateTime(sample.timestamp) }}</div>
        </div>
      </article>
    </div>
  </SectionCard>
</template>
