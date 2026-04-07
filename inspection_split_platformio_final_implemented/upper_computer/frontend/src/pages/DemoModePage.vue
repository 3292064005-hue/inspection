<script setup lang="ts">
import { ref } from 'vue';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import { useInspectionStore } from '@/entities/inspection/store';
import { useStationStore } from '@/entities/station/store';
import { decisionTone, phaseLabel } from '@/shared/utils/status';
import { formatPercent } from '@/shared/utils/format';
import { getGateway } from '@/shared/gateway/service';
import type { DemoScenario } from '@/shared/types/domain';
import { useAppStore } from '@/entities/app/store';

const inspectionStore = useInspectionStore();
const stationStore = useStationStore();
const appStore = useAppStore();
const gateway = getGateway();
const scenario = ref<DemoScenario>('balanced');

async function applyScenario() {
  await gateway.configureDemoScenario?.(scenario.value);
  appStore.pushNotice({ level: 'INFO', title: '演示场景已切换', message: `当前场景：${scenario.value}` });
}
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />
    <div class="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
      <div class="text-sm text-slate-300">演示场景</div>
      <select v-model="scenario" class="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
        <option value="balanced">balanced</option>
        <option value="stress">stress</option>
        <option value="throughput">throughput</option>
      </select>
      <button class="rounded-xl bg-sky-500 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-400" @click="applyScenario">应用场景</button>
    </div>
    <div class="grid gap-4 xl:grid-cols-[1.4fr_0.8fr]">
      <div class="panel overflow-hidden p-3">
        <img
          v-if="inspectionStore.frame.url"
          :src="inspectionStore.frame.url"
          alt="demo-frame"
          class="h-[560px] w-full rounded-2xl object-cover"
        />
      </div>

      <div class="flex flex-col gap-4">
        <div class="panel p-5">
          <div class="text-sm uppercase tracking-[0.25em] text-slate-400">当前状态</div>
          <div class="mt-3 text-4xl font-semibold text-white">{{ phaseLabel(stationStore.snapshot.phase) }}</div>
          <div class="mt-3 text-slate-300">{{ stationStore.snapshot.guidance }}</div>
        </div>

        <div class="panel p-5">
          <div class="text-sm uppercase tracking-[0.25em] text-slate-400">当前结果</div>
          <div class="mt-3">
            <span
              v-if="inspectionStore.currentResult"
              :class="['status-pill text-xl', decisionTone(inspectionStore.currentResult.decision)]"
            >
              {{ inspectionStore.currentResult.decision }}
            </span>
          </div>
          <div class="mt-3 text-slate-200">{{ inspectionStore.currentResult?.defectType ?? '等待结果' }}</div>
        </div>

        <div class="grid gap-4 md:grid-cols-2">
          <div class="panel p-5">
            <div class="data-label">总数</div>
            <div class="mt-2 text-4xl font-semibold text-slate-100">{{ stationStore.stats.total }}</div>
          </div>
          <div class="panel p-5">
            <div class="data-label">良率</div>
            <div class="mt-2 text-4xl font-semibold text-sky-200">{{ formatPercent(stationStore.stats.yieldRate) }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
