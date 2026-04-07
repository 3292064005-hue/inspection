<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute } from 'vue-router';

const route = useRoute();

const links = computed(() => [
  { to: '/run', label: '运行首页', desc: '工位主控 / 实时操作' },
  { to: '/live', label: '实时检测', desc: '视觉说明 / 节拍拆解' },
  { to: '/trace', label: '结果追溯', desc: '按批次 / 时间检索' },
  { to: '/stats', label: '统计分析', desc: 'KPI / 缺陷分布' },
  { to: '/recipes', label: '配方管理', desc: 'ROI / 阈值 / 规则' },
  { to: '/diagnostics', label: '设备诊断', desc: '链路状态 / 手动检测' },
  { to: '/settings', label: '系统设置', desc: '界面 / 刷新模式' },
  { to: '/demo', label: '答辩展示', desc: '大屏模式' },
]);
</script>

<template>
  <aside class="panel sticky top-[88px] h-[calc(100vh-104px)] w-[260px] shrink-0 p-4">
    <div class="mb-4 text-xs uppercase tracking-[0.3em] text-slate-400">Navigation</div>
    <nav class="space-y-2">
      <RouterLink
        v-for="item in links"
        :key="item.to"
        :to="item.to"
        class="block rounded-2xl border px-4 py-3 transition"
        :class="
          route.path === item.to
            ? 'border-sky-400/30 bg-sky-500/10 text-sky-100'
            : 'border-slate-800/80 bg-slate-900/60 text-slate-300 hover:border-slate-700 hover:bg-slate-900'
        "
      >
        <div class="font-medium">{{ item.label }}</div>
        <div class="mt-1 text-xs text-slate-400">{{ item.desc }}</div>
      </RouterLink>
    </nav>
  </aside>
</template>
