<script setup lang="ts">
import { useFaultStore } from '@/entities/fault/store';
import { formatDateTime } from '@/shared/utils/format';
import SectionCard from '@/widgets/SectionCard.vue';

const faultStore = useFaultStore();
</script>

<template>
  <SectionCard title="故障与告警" subtitle="故障优先级最高，必须给出恢复建议。">
    <div v-if="faultStore.activeFault" class="space-y-3">
      <div class="rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4">
        <div class="flex items-center justify-between">
          <div class="text-lg font-semibold text-rose-200">{{ faultStore.activeFault.code }}</div>
          <div class="text-sm text-rose-100">{{ formatDateTime(faultStore.activeFault.timestamp) }}</div>
        </div>
        <p class="mt-2 text-sm leading-6 text-rose-100">{{ faultStore.activeFault.message }}</p>
        <p class="mt-2 text-sm leading-6 text-rose-100">处理建议：{{ faultStore.activeFault.suggestion }}</p>
      </div>
    </div>
    <div v-else class="rounded-2xl border border-emerald-400/20 bg-emerald-500/5 p-4 text-sm text-emerald-200">
      当前无活动故障，工位处于可运行状态。
    </div>

    <div class="mt-4 space-y-2">
      <div class="data-label">最近故障记录</div>
      <div
        v-for="fault in faultStore.history.slice(0, 5)"
        :key="fault.id"
        class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-3 py-3"
      >
        <div class="flex items-center justify-between">
          <span class="font-medium text-slate-100">{{ fault.code }}</span>
          <span class="text-xs text-slate-400">{{ formatDateTime(fault.timestamp) }}</span>
        </div>
        <p class="mt-1 text-sm text-slate-300">{{ fault.message }}</p>
      </div>
    </div>
  </SectionCard>
</template>
