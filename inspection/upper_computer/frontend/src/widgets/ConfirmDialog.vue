<script setup lang="ts">
import { useAppStore } from '@/entities/app/store';

const appStore = useAppStore();

function close(result: boolean) {
  appStore.settleConfirm(result);
}
</script>

<template>
  <div
    v-if="appStore.confirm.open"
    class="fixed inset-0 z-40 flex items-center justify-center bg-slate-950/70 px-4 backdrop-blur-sm"
  >
    <div class="w-full max-w-lg rounded-3xl border border-slate-800 bg-slate-950 p-6 shadow-2xl">
      <div class="text-xs uppercase tracking-[0.28em] text-slate-500">操作确认</div>
      <div class="mt-3 text-2xl font-semibold text-white">{{ appStore.confirm.title }}</div>
      <div class="mt-3 leading-7 text-slate-300">{{ appStore.confirm.message }}</div>
      <div class="mt-6 flex justify-end gap-3">
        <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-200 hover:border-slate-500" @click="close(false)">
          {{ appStore.confirm.cancelLabel }}
        </button>
        <button
          class="rounded-2xl px-4 py-3 text-sm font-semibold text-white"
          :class="appStore.confirm.tone === 'ERROR' ? 'bg-rose-500 hover:bg-rose-400' : appStore.confirm.tone === 'WARN' ? 'bg-amber-500 hover:bg-amber-400 text-slate-950' : 'bg-sky-500 hover:bg-sky-400'"
          @click="close(true)"
        >
          {{ appStore.confirm.confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>
