<script setup lang="ts">
import { computed } from 'vue';
import { useAppStore } from '@/entities/app/store';
import { useSettingsStore } from '@/entities/settings/store';
import { appEnv } from '@/shared/config/env';
import { cacheKeys, invalidateCache } from '@/shared/query/cache';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import SectionCard from '@/widgets/SectionCard.vue';

const settings = useSettingsStore();
const appStore = useAppStore();
const cacheCount = computed(() => cacheKeys().length);

function persist() {
  settings.persist();
}

function clearCache() {
  invalidateCache();
  localStorage.clear();
  appStore.pushNotice({ level: 'INFO', title: '本地缓存已清空', message: '刷新页面后会按默认设置重新初始化。' });
}
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />
    <div class="grid gap-4 xl:grid-cols-2">
      <SectionCard title="界面与刷新" subtitle="控制显示模式，不影响主控逻辑。">
        <div class="space-y-4">
          <label class="flex items-center justify-between rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
            <span>默认全屏展示</span>
            <input v-model="settings.fullScreenByDefault" type="checkbox" class="h-5 w-5" @change="persist" />
          </label>
          <label class="flex items-center justify-between rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
            <span>显示高级指标</span>
            <input v-model="settings.showAdvancedMetrics" type="checkbox" class="h-5 w-5" @change="persist" />
          </label>
          <label class="flex items-center justify-between rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
            <span>提示音开关</span>
            <input v-model="settings.soundEnabled" type="checkbox" class="h-5 w-5" @change="persist" />
          </label>
        </div>
      </SectionCard>

      <SectionCard title="数据保留与性能" subtitle="HMI 运行优先稳，不追求无意义高帧率。">
        <div class="space-y-4">
          <label class="block rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
            <div class="mb-2">日志保留天数</div>
            <input v-model="settings.archiveDays" type="number" min="3" max="90" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2" @change="persist" />
          </label>
          <label class="block rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">
            <div class="mb-2">刷新模式</div>
            <select v-model="settings.refreshMode" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2" @change="persist">
              <option value="smooth">平滑模式</option>
              <option value="performance">性能优先</option>
            </select>
          </label>
        </div>
      </SectionCard>

      <SectionCard title="运行环境" subtitle="把当前构建与连接模式显式展示出来。以下设置仅影响当前 HMI 客户端。">
        <div class="space-y-3 text-sm text-slate-200">
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">网关模式：{{ appEnv.gatewayMode }}</div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">网关地址：{{ appEnv.gatewayBaseUrl }}</div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">演示场景：{{ appEnv.demoScenario }}</div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">重连基线：{{ appEnv.gatewayRetryBaseMs }} ms</div>
          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 px-4 py-4">缓存条目：{{ cacheCount }}</div>
        </div>
      </SectionCard>

      <SectionCard title="客户端维护与缓存" subtitle="用于演示或长时间运行后的本地重置，不会改写后端系统配置。">
        <div class="space-y-4">
          <button class="w-full rounded-2xl border border-slate-700 px-4 py-4 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="clearCache">清空本地缓存</button>
        </div>
      </SectionCard>
    </div>
  </div>
</template>
