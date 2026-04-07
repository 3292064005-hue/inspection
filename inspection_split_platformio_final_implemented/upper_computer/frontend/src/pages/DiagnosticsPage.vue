<script setup lang="ts">
import { computed } from 'vue';
import { useAppStore } from '@/entities/app/store';
import { useDiagnostics } from '@/features/diagnostics/useDiagnostics';
import { formatDuration } from '@/shared/utils/format';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import DiagnosticsCards from '@/widgets/DiagnosticsCards.vue';
import SectionCard from '@/widgets/SectionCard.vue';

const appStore = useAppStore();
const { items, loading, actionBusy, cooldownRemaining, maintenanceState, load, run } = useDiagnostics();

const maintenanceRemainingLabel = computed(() => appStore.maintenanceRemainingMs > 0 ? formatDuration(appStore.maintenanceRemainingMs) : '--');

function onMaintenanceToggle(event: Event) {
  const target = event.target as HTMLInputElement;
  if (target.checked) {
    appStore.armMaintenanceMode();
  } else {
    appStore.setMaintenanceMode(false);
  }
}
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />
    <DiagnosticsCards :items="items" :loading="loading" />

    <SectionCard title="维护模式操作" subtitle="危险动作必须先进入维护模式并经过统一确认弹窗。">
      <div class="mb-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
          <div>
            <div class="font-semibold text-slate-100">维护模式</div>
            <div class="mt-1 text-sm text-slate-300">关闭时禁止执行抓拍、补光和执行器测试。</div>
          </div>
          <label class="flex items-center gap-3 text-sm text-slate-100">
            <input :checked="appStore.maintenanceMode" type="checkbox" class="h-5 w-5" @change="onMaintenanceToggle" />
            {{ appStore.maintenanceMode ? '已启用' : '未启用' }}
          </label>
        </div>
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4 text-sm text-slate-300">
          <div>状态：<span class="font-semibold text-slate-100">{{ maintenanceState }}</span></div>
          <div class="mt-2">维护窗口剩余：{{ maintenanceRemainingLabel }}</div>
        </div>
      </div>

      <div class="grid gap-3 md:grid-cols-3">
        <button class="rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-4 text-sm font-semibold text-slate-100 hover:border-slate-500" :disabled="actionBusy !== ''" @click="run('CAPTURE_FRAME')">
          {{ actionBusy === 'CAPTURE_FRAME' ? '执行中…' : cooldownRemaining.CAPTURE_FRAME > 0 ? `冷却 ${Math.ceil(cooldownRemaining.CAPTURE_FRAME / 1000)}s` : '抓拍一帧' }}
        </button>
        <button class="rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-4 text-sm font-semibold text-slate-100 hover:border-slate-500" :disabled="actionBusy !== ''" @click="run('TEST_LIGHTING')">
          {{ actionBusy === 'TEST_LIGHTING' ? '执行中…' : cooldownRemaining.TEST_LIGHTING > 0 ? `冷却 ${Math.ceil(cooldownRemaining.TEST_LIGHTING / 1000)}s` : '测试补光' }}
        </button>
        <button class="rounded-2xl border border-slate-700 bg-slate-950/60 px-4 py-4 text-sm font-semibold text-slate-100 hover:border-slate-500" :disabled="actionBusy !== ''" @click="run('TEST_SORT_ACTUATOR')">
          {{ actionBusy === 'TEST_SORT_ACTUATOR' ? '执行中…' : cooldownRemaining.TEST_SORT_ACTUATOR > 0 ? `冷却 ${Math.ceil(cooldownRemaining.TEST_SORT_ACTUATOR / 1000)}s` : '测试分拣执行器' }}
        </button>
      </div>

      <div class="mt-4 flex justify-end">
        <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="load(true)">刷新诊断数据</button>
      </div>
    </SectionCard>
  </div>
</template>
