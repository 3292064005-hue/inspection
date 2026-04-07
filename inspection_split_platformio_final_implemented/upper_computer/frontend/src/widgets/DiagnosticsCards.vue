<script setup lang="ts">
import type { DiagnosticsItem } from '@/shared/types/domain';
import { healthTone } from '@/shared/utils/status';

defineProps<{
  items: DiagnosticsItem[];
  loading?: boolean;
}>();
</script>

<template>
  <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
    <article
      v-for="item in items"
      :key="item.id"
      class="panel p-4"
    >
      <div class="flex items-center justify-between gap-3">
        <div class="text-base font-semibold text-slate-100">{{ item.name }}</div>
        <span :class="['status-pill', healthTone(item.status)]">{{ item.status }}</span>
      </div>
      <div class="mt-3 text-lg font-medium text-sky-200">{{ item.value }}</div>
      <div class="mt-2 text-sm leading-6 text-slate-300">{{ item.note }}</div>
    </article>
    <article v-if="loading" class="panel flex items-center justify-center p-4 text-slate-400">诊断信息刷新中…</article>
  </div>
</template>
