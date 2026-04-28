<script setup lang="ts">
import { computed } from 'vue';
import { useDiagnostics } from '@/features/diagnostics/useDiagnostics';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import DiagnosticsCards from '@/widgets/DiagnosticsCards.vue';
import SectionCard from '@/widgets/SectionCard.vue';

const {
  items,
  loading,
  actionBusy,
  cooldownRemaining,
  maintenance,
  maintenanceEnabled,
  maintenanceRequested,
  maintenanceTransitionState,
  maintenanceState,
  diagnosticGovernance,
  governanceHighlights,
  load,
  run,
  toggleMaintenance,
} = useDiagnostics();

const maintenanceTransitionLabel = computed(() => {
  if (maintenanceEnabled.value) return '系统已确认进入维护模式';
  if (maintenanceTransitionState.value === 'ENTERING' || maintenanceRequested.value) return '等待系统确认进入维护模式';
  if (maintenanceTransitionState.value === 'EXITING') return '等待系统确认退出维护模式';
  return '系统未处于维护模式';
});

const governanceCards = computed(() => [
  { action: '抓拍一帧', detail: diagnosticGovernance.value.CAPTURE_FRAME },
  { action: '测试补光', detail: diagnosticGovernance.value.TEST_LIGHTING },
  { action: '测试分拣执行器', detail: diagnosticGovernance.value.TEST_SORT_ACTUATOR },
]);

function governanceTone(tier?: string): string {
  if (tier === 'compatibility') return 'border-amber-500/40 bg-amber-500/10 text-amber-200';
  if (tier === 'experimental') return 'border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-200';
  return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200';
}

async function onMaintenanceToggle(event: Event) {
  const target = event.target as HTMLInputElement;
  await toggleMaintenance(target.checked);
}
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />
    <DiagnosticsCards :items="items" :loading="loading" />

    <SectionCard title="维护模式操作" subtitle="危险动作必须先进入系统维护模式并经过统一确认弹窗。">
      <div class="mb-4 grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <div class="flex items-center justify-between gap-3 rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
          <div>
            <div class="font-semibold text-slate-100">维护模式</div>
            <div class="mt-1 text-sm text-slate-300">关闭时禁止执行抓拍、补光和执行器测试。</div>
          </div>
          <label class="flex items-center gap-3 text-sm text-slate-100">
            <input :checked="maintenanceRequested || maintenanceEnabled" type="checkbox" class="h-5 w-5" @change="onMaintenanceToggle" />
            {{ maintenanceEnabled ? '已生效' : maintenanceRequested ? '切换中' : '未启用' }}
          </label>
        </div>
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4 text-sm text-slate-300">
          <div>状态：<span class="font-semibold text-slate-100">{{ maintenanceState }}</span></div>
          <div class="mt-2">切换：{{ maintenanceTransitionLabel }}</div>
          <div class="mt-2">Supervisor：{{ maintenance.supervisorMode }}</div>
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

    <SectionCard title="动作治理分级" subtitle="前端显式展示正式 / 兼容 / 实验能力分级，避免非正式动作与正式能力混用。">
      <div class="grid gap-4 lg:grid-cols-3">
        <article v-for="card in governanceCards" :key="card.action" class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4 text-sm text-slate-300">
          <div class="flex items-center justify-between gap-2">
            <div class="font-semibold text-slate-100">{{ card.action }}</div>
            <span class="rounded-full border px-2 py-1 text-xs font-semibold" :class="governanceTone(card.detail?.governance.tier)">
              {{ card.detail?.governance.uiLabel || card.detail?.governance.tier || '未声明' }}
            </span>
          </div>
          <div class="mt-3 space-y-2" v-if="card.detail">
            <div>生命周期：{{ card.detail.governance.lifecycle }}</div>
            <div>执行策略：{{ card.detail.capability.executionPolicy }}</div>
            <div>运行真值：{{ card.detail.capability.runtimeTruth }}</div>
            <div v-if="card.detail.governance.sunsetRelease">退役版本：{{ card.detail.governance.sunsetRelease }}</div>
            <div class="text-slate-400">{{ card.detail.capability.summary }}</div>
          </div>
          <div class="mt-3 text-slate-500" v-else>未获取到动作治理元数据。</div>
        </article>
      </div>

      <div class="mt-4 rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
        <div class="font-semibold text-slate-100">非正式能力总览</div>
        <div class="mt-3 grid gap-3 lg:grid-cols-2">
          <article v-for="entry in governanceHighlights" :key="entry.kind" class="rounded-2xl border border-slate-800 bg-slate-900/60 px-4 py-3 text-sm text-slate-300">
            <div class="flex items-center justify-between gap-2">
              <div class="font-medium text-slate-100">{{ entry.kind }}</div>
              <span class="rounded-full border px-2 py-1 text-xs font-semibold" :class="governanceTone(entry.governance.tier)">{{ entry.governance.uiLabel || entry.governance.tier }}</span>
            </div>
            <div class="mt-2">可见性：{{ entry.capability.visibility }} / 提交：{{ entry.capability.submitEnabled ? '允许' : '禁止' }}</div>
            <div v-if="entry.capability.submitReason" class="mt-1">阻断原因：{{ entry.capability.submitReason }}</div>
            <div v-if="entry.governance.promotionCriteria.length" class="mt-1">转正条件：{{ entry.governance.promotionCriteria.join('；') }}</div>
          </article>
        </div>
      </div>
    </SectionCard>
  </div>
</template>
