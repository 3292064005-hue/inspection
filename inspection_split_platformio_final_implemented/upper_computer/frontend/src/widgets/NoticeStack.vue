<script setup lang="ts">
import { useAppStore } from '@/entities/app/store';

const appStore = useAppStore();
</script>

<template>
  <div class="fixed bottom-4 right-4 z-30 flex w-[360px] flex-col gap-2">
    <div
      v-for="notice in appStore.notices"
      :key="notice.id"
      class="rounded-2xl border px-4 py-3 shadow-lg backdrop-blur"
      :class="notice.level === 'ERROR' ? 'border-rose-400/30 bg-rose-500/10 text-rose-100' : notice.level === 'WARN' ? 'border-amber-400/30 bg-amber-500/10 text-amber-100' : 'border-sky-400/30 bg-sky-500/10 text-sky-100'"
    >
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-semibold">{{ notice.title }}</div>
          <div class="mt-1 text-sm leading-6">{{ notice.message }}</div>
        </div>
        <button class="text-xs opacity-80 hover:opacity-100" @click="appStore.clearNotice(notice.id)">关闭</button>
      </div>
    </div>
  </div>
</template>
