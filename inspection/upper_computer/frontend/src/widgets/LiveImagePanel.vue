<script setup lang="ts">
import { computed } from 'vue';
import { useInspectionStore } from '@/entities/inspection/store';
import { formatDateTime } from '@/shared/utils/format';
import SectionCard from '@/widgets/SectionCard.vue';

const inspectionStore = useInspectionStore();
const frameTime = computed(() => formatDateTime(inspectionStore.frame.capturedAt));
const frameLabel = computed(() => inspectionStore.frameViewMode === 'overlay' ? '标注叠加' : '原始视图');
const frameSemantic = computed(() => inspectionStore.frame.semantic === 'LIVE_STREAM' ? '实时流' : '最近处理图');
const frameDescription = computed(() => inspectionStore.frame.description || '显示最近一次处理结果对应的图像快照。');
</script>

<template>
  <SectionCard title="最新处理图像" subtitle="显示最近一次视觉处理结果对应的图像快照、叠加标注和采图时间。">
    <div class="flex h-full flex-col gap-3">
      <div class="relative flex-1 overflow-hidden rounded-2xl border border-slate-800 bg-slate-950">
        <img
          v-if="inspectionStore.frame.url"
          :src="inspectionStore.frame.url"
          alt="最新处理图像"
          class="h-full w-full object-cover"
        />
        <div v-else class="flex h-full items-center justify-center text-slate-500">等待最新处理图像…</div>
        <div class="absolute bottom-4 left-4 rounded-xl border border-slate-800/80 bg-slate-950/80 px-3 py-2 text-xs text-slate-200">
          捕获时间：{{ frameTime }}
        </div>
      </div>
      <div class="grid gap-3 md:grid-cols-4">
        <button
          class="rounded-2xl border px-3 py-3 text-left transition"
          :class="inspectionStore.frameViewMode === 'overlay' ? 'border-sky-400/30 bg-sky-500/10 text-sky-100' : 'border-slate-800/80 bg-slate-950/60 text-slate-300'"
          @click="inspectionStore.setFrameViewMode('overlay')"
        >
          <div class="data-label">图像模式</div>
          <div class="mt-1 text-sm font-semibold">标注叠加</div>
        </button>
        <button
          class="rounded-2xl border px-3 py-3 text-left transition"
          :class="inspectionStore.frameViewMode === 'raw' ? 'border-sky-400/30 bg-sky-500/10 text-sky-100' : 'border-slate-800/80 bg-slate-950/60 text-slate-300'"
          @click="inspectionStore.setFrameViewMode('raw')"
        >
          <div class="data-label">图像模式</div>
          <div class="mt-1 text-sm font-semibold">原始视图</div>
        </button>
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div class="data-label">当前模式</div>
          <div class="mt-1 text-sm font-semibold">{{ frameLabel }}</div>
        </div>
        <div class="rounded-2xl border border-slate-800/80 bg-slate-950/60 p-3">
          <div class="data-label">数据语义</div>
          <div class="mt-1 text-sm font-semibold">{{ frameSemantic }}</div>
          <div class="mt-1 text-xs text-slate-400">{{ frameDescription }}</div>
        </div>
      </div>
    </div>
  </SectionCard>
</template>
