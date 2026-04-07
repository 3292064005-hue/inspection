<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRecipeStore } from '@/entities/recipe/store';
import { useResultTrace } from '@/features/result-trace/useResultTrace';
import { formatDateTime, formatDuration } from '@/shared/utils/format';
import { decisionTone } from '@/shared/utils/status';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';

const recipeStore = useRecipeStore();
const {
  loading,
  detailLoading,
  detailError,
  items,
  pagedItems,
  filters,
  templates,
  summary,
  batchSummary,
  selectedId,
  selectedItem,
  page,
  pageSize,
  totalPages,
  detailImageMode,
  loadResults,
  loadResultDetail,
  resetFilters,
  nextPage,
  prevPage,
  toggleDetailImageMode,
  exportCurrentFilters,
  copyField,
  saveTemplate,
  applyTemplate,
  removeTemplate,
} = useResultTrace();

const recipeOptions = computed(() => recipeStore.items);
const detailImageUrl = computed(() => {
  if (!selectedItem.value) return '';
  return detailImageMode.value === 'overlay'
    ? selectedItem.value.overlayUrl ?? selectedItem.value.imageUrl ?? ''
    : selectedItem.value.imageUrl ?? selectedItem.value.overlayUrl ?? '';
});
const traceBundle = computed(() => selectedItem.value?.traceBundle ?? null);
const traceArtifacts = computed(() => traceBundle.value?.artifacts ?? selectedItem.value?.artifacts ?? []);
const traceEvents = computed(() => (traceBundle.value?.events ?? []).slice(0, 10));
const configSnapshotText = computed(() => traceBundle.value?.configSnapshot ? JSON.stringify(traceBundle.value.configSnapshot, null, 2) : '');
const runArtifactsText = computed(() => traceBundle.value?.runArtifacts ? JSON.stringify(traceBundle.value.runArtifacts, null, 2) : '');

function stringifyEvent(event: Record<string, unknown>): string {
  const phase = typeof event.phase === 'string' ? event.phase : typeof event.stage === 'string' ? event.stage : 'EVENT';
  const message = typeof event.message === 'string'
    ? event.message
    : typeof event.description === 'string'
      ? event.description
      : JSON.stringify(event);
  return `${phase} · ${message}`;
}

onMounted(() => {
  void loadResults();
});
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />

    <div class="panel p-4">
      <div class="panel-title">结果追溯筛选</div>
      <div class="mt-4 grid gap-3 md:grid-cols-4 xl:grid-cols-7">
        <input v-model="filters.batchId" class="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm" placeholder="批次号" />
        <select v-model="filters.recipeId" class="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm">
          <option value="">全部配方</option>
          <option v-for="recipe in recipeOptions" :key="recipe.id" :value="recipe.id">{{ recipe.name }}</option>
        </select>
        <select v-model="filters.decision" class="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm">
          <option value="">全部结果</option>
          <option value="OK">OK</option>
          <option value="NG">NG</option>
          <option value="RECHECK">RECHECK</option>
        </select>
        <input v-model="filters.defectType" class="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm" placeholder="缺陷类型" />
        <input v-model="filters.qrText" class="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm" placeholder="二维码 / 工件号" />
        <input v-model="filters.from" type="datetime-local" class="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm" />
        <input v-model="filters.to" type="datetime-local" class="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm" />
      </div>
      <div class="mt-4 flex flex-wrap gap-3">
        <button class="rounded-2xl bg-sky-500 px-4 py-3 text-sm font-semibold text-white hover:bg-sky-400" @click="loadResults(true)">{{ loading ? '查询中…' : '执行查询' }}</button>
        <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="resetFilters">重置条件</button>
        <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="saveTemplate">保存为模板</button>
        <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="exportCurrentFilters('all')">导出全部结果</button>
        <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="exportCurrentFilters('page')">导出当前页</button>
      </div>
      <div v-if="templates.length" class="mt-4 flex flex-wrap gap-2">
        <button v-for="template in templates" :key="template.id" class="rounded-full border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs text-slate-200 hover:border-slate-500" @click="applyTemplate(template.id)">{{ template.name }}</button>
        <button v-for="template in templates" :key="`${template.id}-remove`" class="rounded-full border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200" @click="removeTemplate(template.id)">删除 {{ template.name }}</button>
      </div>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <div class="panel min-h-0 p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="panel-title">结果列表</div>
          <div class="flex items-center gap-3 text-sm text-slate-300">
            <span>共 {{ items.length }} 条</span>
            <select v-model="pageSize" class="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
              <option :value="8">8 / 页</option>
              <option :value="12">12 / 页</option>
              <option :value="20">20 / 页</option>
            </select>
          </div>
        </div>
        <div class="mt-4 grid gap-3">
          <button v-for="item in pagedItems" :key="item.id" class="rounded-2xl border px-4 py-3 text-left transition" :class="selectedId === item.id ? 'border-sky-400/40 bg-sky-500/10' : 'border-slate-800/70 bg-slate-950/60 hover:border-slate-600'" @click="selectedId = item.id">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div class="text-sm text-slate-400">{{ formatDateTime(item.timestamp) }}</div>
                <div class="mt-1 text-base font-semibold text-slate-100">{{ item.recipeName }} / {{ item.batchId }}</div>
              </div>
              <span :class="['status-pill', decisionTone(item.decision)]">{{ item.decision }}</span>
            </div>
            <div class="mt-3 flex flex-wrap gap-3 text-sm text-slate-300">
              <span>缺陷：{{ item.defectType ?? '--' }}</span>
              <span>二维码：{{ item.qrText ?? '--' }}</span>
              <span>节拍：{{ formatDuration(item.cycleMs) }}</span>
              <span>追溯：{{ item.traceId ?? '--' }}</span>
              <span>证据：{{ item.artifactCount ?? 0 }}</span>
            </div>
          </button>
        </div>
        <div class="mt-4 flex items-center justify-between text-sm text-slate-300">
          <button class="rounded-xl border border-slate-700 px-3 py-2 hover:border-slate-500" @click="prevPage">上一页</button>
          <div>第 {{ page }} / {{ totalPages }} 页</div>
          <button class="rounded-xl border border-slate-700 px-3 py-2 hover:border-slate-500" @click="nextPage">下一页</button>
        </div>
      </div>

      <div class="flex min-h-0 flex-col gap-4">
        <div class="panel p-4">
          <div class="panel-title">查询摘要</div>
          <div class="mt-4 grid gap-3 md:grid-cols-4 xl:grid-cols-2">
            <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4"><div class="data-label">总数</div><div class="mt-2 text-2xl font-semibold text-slate-100">{{ summary.total }}</div></div>
            <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4"><div class="data-label">OK</div><div class="mt-2 text-2xl font-semibold text-emerald-300">{{ summary.ok }}</div></div>
            <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4"><div class="data-label">NG</div><div class="mt-2 text-2xl font-semibold text-rose-300">{{ summary.ng }}</div></div>
            <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4"><div class="data-label">RECHECK</div><div class="mt-2 text-2xl font-semibold text-amber-300">{{ summary.recheck }}</div></div>
          </div>
        </div>

        <div class="panel min-h-0 p-4">
          <div class="flex items-center justify-between gap-3">
            <div class="panel-title">结果详情</div>
            <div class="flex flex-wrap gap-2">
              <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-200" @click="toggleDetailImageMode('overlay')">标注图</button>
              <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-200" @click="toggleDetailImageMode('raw')">原图</button>
              <button :disabled="!selectedId || detailLoading" class="rounded-xl border border-slate-700 px-3 py-2 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-50" @click="selectedId && loadResultDetail(selectedId, true)">{{ detailLoading ? '加载中…' : '刷新详情' }}</button>
            </div>
          </div>
          <div v-if="selectedItem" class="mt-4 space-y-4">
            <img v-if="detailImageUrl" :src="detailImageUrl" alt="detail" class="h-[240px] w-full rounded-2xl object-cover" />
            <div class="grid gap-3 md:grid-cols-2">
              <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4 text-sm text-slate-300">
                <div>时间：{{ formatDateTime(selectedItem.timestamp) }}</div>
                <div class="mt-2">配方：{{ selectedItem.recipeName }}</div>
                <div class="mt-2">批次：{{ selectedItem.batchId }}</div>
                <div class="mt-2">节拍：{{ formatDuration(selectedItem.cycleMs) }}</div>
                <div class="mt-2">Trace：{{ selectedItem.traceId ?? '--' }}</div>
                <div class="mt-2">证据数量：{{ traceBundle?.artifactCount ?? selectedItem.artifactCount ?? 0 }}</div>
              </div>
              <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4 text-sm text-slate-300">
                <div>缺陷：{{ selectedItem.defectType ?? '--' }}</div>
                <div class="mt-2">二维码：{{ selectedItem.qrText ?? '--' }}</div>
                <div class="mt-2">指标：{{ selectedItem.metricLabel ?? '--' }} / {{ selectedItem.metricValue ?? '--' }}</div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs" @click="copyField(selectedItem.qrText, '二维码')">复制二维码</button>
                  <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs" @click="copyField(selectedItem.id, '结果ID')">复制结果ID</button>
                  <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs" @click="copyField(selectedItem.traceId, 'Trace ID')">复制 Trace ID</button>
                  <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs" @click="copyField(traceBundle?.traceUrl, 'Trace URL')">复制 Trace URL</button>
                </div>
              </div>
            </div>
            <div v-if="detailError" class="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">{{ detailError }}</div>
            <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4">
              <div class="data-label">判定说明</div>
              <ul class="mt-3 space-y-2 text-sm text-slate-200"><li v-for="line in selectedItem.explanation" :key="line">• {{ line }}</li></ul>
            </div>
            <div class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4">
              <div class="flex items-center justify-between gap-3"><div class="data-label">追溯摘要</div><div class="text-xs text-slate-400">事件 {{ traceBundle?.eventCount ?? 0 }} · 证据 {{ traceBundle?.artifactCount ?? traceArtifacts.length }}</div></div>
              <div class="mt-3 grid gap-3 md:grid-cols-2">
                <div class="rounded-2xl border border-slate-800/70 bg-slate-950/50 p-4 text-sm text-slate-300"><div>Trace URL：{{ traceBundle?.traceUrl ?? '--' }}</div><div class="mt-2">结果 Trace：{{ selectedItem.traceId ?? '--' }}</div></div>
                <div class="rounded-2xl border border-slate-800/70 bg-slate-950/50 p-4 text-sm text-slate-300"><div>明细来源：{{ detailLoading ? '正在刷新详情…' : '详情已同步' }}</div><div class="mt-2">运行摘要：{{ traceBundle?.summary ? '已加载' : '未提供' }}</div></div>
              </div>
            </div>
            <div v-if="traceArtifacts.length" class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4">
              <div class="data-label">证据文件</div>
              <div class="mt-3 space-y-2 text-sm text-slate-200">
                <div v-for="artifact in traceArtifacts" :key="`${artifact.kind}-${artifact.path}`" class="rounded-2xl border border-slate-800/70 bg-slate-950/50 px-4 py-3">
                  <div class="font-semibold text-slate-100">{{ artifact.kind }}</div>
                  <div class="mt-1 break-all text-slate-400">{{ artifact.path }}</div>
                  <div v-if="artifact.url" class="mt-2"><a :href="artifact.url" target="_blank" rel="noreferrer" class="text-sky-300 hover:text-sky-200">打开证据</a></div>
                </div>
              </div>
            </div>
            <div v-if="traceEvents.length" class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4">
              <div class="data-label">Trace 事件</div>
              <ul class="mt-3 space-y-2 text-sm text-slate-200"><li v-for="(event, index) in traceEvents" :key="`${selectedItem.id}-event-${index}`" class="rounded-2xl border border-slate-800/70 bg-slate-950/50 px-4 py-3">{{ stringifyEvent(event) }}</li></ul>
            </div>
            <div v-if="configSnapshotText || runArtifactsText" class="grid gap-4 md:grid-cols-2">
              <div v-if="configSnapshotText" class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4"><div class="data-label">配置快照</div><pre class="mt-3 overflow-auto rounded-2xl bg-slate-950/70 p-3 text-xs text-slate-300">{{ configSnapshotText }}</pre></div>
              <div v-if="runArtifactsText" class="rounded-2xl border border-slate-800/70 bg-slate-950/60 p-4"><div class="data-label">运行产物</div><pre class="mt-3 overflow-auto rounded-2xl bg-slate-950/70 p-3 text-xs text-slate-300">{{ runArtifactsText }}</pre></div>
            </div>
          </div>
          <div v-else class="mt-6 text-sm text-slate-500">暂无选中的结果。</div>
        </div>

        <div class="panel p-4">
          <div class="panel-title">批次摘要</div>
          <div class="mt-4 space-y-2 text-sm text-slate-300">
            <div v-for="entry in batchSummary" :key="entry[0]" class="rounded-2xl border border-slate-800/70 bg-slate-950/60 px-4 py-3"><div class="font-semibold text-slate-100">{{ entry[0] }}</div><div class="mt-1">总数 {{ entry[1].count }} · OK {{ entry[1].ok }} · NG {{ entry[1].ng }}</div></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
