<script setup lang="ts">
import { computed } from 'vue';
import { useAppStore } from '@/entities/app/store';
import { useStationStore } from '@/entities/station/store';

const appStore = useAppStore();
const stationStore = useStationStore();

const tone = computed(() => {
  if (appStore.connectionState === 'ONLINE') return 'border-emerald-400/20 bg-emerald-500/10 text-emerald-200';
  if (appStore.connectionState === 'DEGRADED') return 'border-amber-400/20 bg-amber-500/10 text-amber-200';
  if (appStore.connectionState === 'RECONNECTING') return 'border-amber-400/20 bg-amber-500/10 text-amber-200';
  if (appStore.connectionState === 'OFFLINE') return 'border-rose-400/20 bg-rose-500/10 text-rose-200';
  if (appStore.connectionState === 'ERROR') return 'border-rose-400/20 bg-rose-500/10 text-rose-200';
  return 'border-sky-400/20 bg-sky-500/10 text-sky-100';
});

const message = computed(() => {
  switch (appStore.connectionState) {
    case 'CONNECTING':
      return '正在连接 HMI 网关并同步初始快照…';
    case 'RECONNECTING':
      return '网关连接正在恢复中，系统会在恢复后自动重新同步。';
    case 'ONLINE':
      return stationStore.hasStaleHeartbeat ? '链路在线，但存在心跳老化，请关注图像与控制延迟。' : '链路在线，允许执行自动循环。';
    case 'DEGRADED':
      return '链路处于降级状态，请关注心跳和图像延迟。';
    case 'OFFLINE':
      return '链路离线，主控操作将被限制。';
    case 'ERROR':
      return appStore.bootstrapError || appStore.gatewayStatus?.lastError || '系统初始化失败。';
    default:
      return '系统启动中…';
  }
});
</script>

<template>
  <div :class="['rounded-2xl border px-4 py-3 text-sm', tone]">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <span class="font-semibold">{{ appStore.connectionState }}</span>
        <span class="ml-2">{{ message }}</span>
      </div>
      <div class="flex flex-wrap gap-3 text-xs text-current/80">
        <span v-if="appStore.gatewayModeLabel">网关：{{ appStore.gatewayModeLabel }}</span>
        <span v-if="appStore.gatewayStatus">WS: {{ appStore.gatewayStatus.wsOk ? 'OK' : 'DOWN' }} · HTTP: {{ appStore.gatewayStatus.httpOk ? 'OK' : 'DOWN' }}</span>
        <span v-if="appStore.gatewayStatus?.retryCount">重连次数：{{ appStore.gatewayStatus.retryCount }}</span>
        <span v-if="appStore.exportedUrl">最近导出：{{ appStore.exportedUrl }}</span>
      </div>
    </div>
  </div>
</template>
