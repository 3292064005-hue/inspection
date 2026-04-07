<script setup lang="ts">
import { computed } from 'vue';
import { useStationStore } from '@/entities/station/store';
import { useFaultStore } from '@/entities/fault/store';
import { useAppStore } from '@/entities/app/store';
import { useAuthStore } from '@/entities/auth/store';
import { formatDateTime, formatDuration } from '@/shared/utils/format';
import { healthTone, phaseLabel } from '@/shared/utils/status';

const stationStore = useStationStore();
const faultStore = useFaultStore();
const appStore = useAppStore();
const authStore = useAuthStore();

const heartbeatList = computed(() => stationStore.heartbeatList);
</script>

<template>
  <header class="sticky top-0 z-20 border-b border-slate-800/70 bg-slate-950/90 backdrop-blur">
    <div class="mx-auto flex max-w-[1920px] items-center justify-between gap-4 px-4 py-3">
      <div class="flex items-center gap-4">
        <div>
          <div class="text-xs uppercase tracking-[0.3em] text-sky-300">Inspection HMI</div>
          <div class="text-xl font-semibold text-white">ROS2 桌面视觉质检与自动分拣工作站</div>
        </div>
        <span class="status-pill border-sky-400/20 bg-sky-500/10 text-sky-200">
          {{ phaseLabel(stationStore.snapshot.phase) }}
        </span>
        <span v-if="faultStore.activeFault" class="status-pill border-rose-400/25 bg-rose-500/15 text-rose-200">
          故障锁定
        </span>
        <span v-if="appStore.maintenanceMode" class="status-pill border-amber-400/25 bg-amber-500/15 text-amber-200">
          维护模式 {{ formatDuration(appStore.maintenanceRemainingMs) }}
        </span>
      </div>

      <div class="flex flex-wrap items-center gap-3 text-sm">
        <div class="rounded-2xl border border-slate-800/70 px-3 py-2">
          <div class="text-slate-400">当前账号</div>
          <div class="font-semibold text-slate-100">{{ authStore.displayLabel }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800/70 px-3 py-2">
          <div class="text-slate-400">当前配方</div>
          <div class="font-semibold text-slate-100">{{ stationStore.snapshot.activeRecipeName }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800/70 px-3 py-2">
          <div class="text-slate-400">当前批次</div>
          <div class="font-semibold text-slate-100">{{ stationStore.snapshot.batchId }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800/70 px-3 py-2">
          <div class="text-slate-400">最近更新</div>
          <div class="font-semibold text-slate-100">{{ formatDateTime(stationStore.snapshot.lastUpdatedAt) }}</div>
        </div>
        <div class="flex gap-2">
          <span
            v-for="heartbeat in heartbeatList"
            :key="heartbeat.source"
            :class="['status-pill', healthTone(heartbeat.derivedStatus)]"
          >
            {{ heartbeat.source }} · {{ heartbeat.latencyMs }} ms
          </span>
        </div>
      </div>
    </div>
  </header>
</template>
