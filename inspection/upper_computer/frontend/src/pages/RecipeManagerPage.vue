<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue';
import { useRecipeManagement } from '@/features/recipe-management/useRecipeManagement';
import ConnectionBanner from '@/widgets/ConnectionBanner.vue';
import RecipeTable from '@/widgets/RecipeTable.vue';
import SectionCard from '@/widgets/SectionCard.vue';

const {
  recipes,
  form,
  formPreview,
  diffPreview,
  validationErrors,
  saving,
  loading,
  hasUnsavedChanges,
  activeHistory,
  refreshRecipes,
  saveRecipe,
  activateRecipe,
  editRecipe,
  cloneRecipe,
  addRule,
  removeRule,
  resetEditor,
} = useRecipeManagement();

let refreshTimer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  refreshTimer = setInterval(() => {
    void refreshRecipes();
  }, 10000);
});

onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <div class="flex h-full flex-col gap-4">
    <ConnectionBanner />

    <SectionCard title="配方总览" subtitle="维护版本、启用状态与编辑入口。">
      <RecipeTable :recipes="recipes" @activate="activateRecipe" @edit="editRecipe" @clone="cloneRecipe" />
      <div class="mt-4 flex justify-end">
        <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="refreshRecipes(true)">
          {{ loading ? '刷新中…' : '刷新配方列表' }}
        </button>
      </div>
    </SectionCard>

    <SectionCard title="配方编辑器" subtitle="结构化配置、版本备注与差异预览。">
      <div class="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <div class="space-y-4 rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
          <div class="grid gap-3 md:grid-cols-2">
            <label class="space-y-2">
              <div class="data-label">配方名称</div>
              <input v-model="form.name" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            </label>
            <label class="space-y-2">
              <div class="data-label">目标工件</div>
              <input v-model="form.targetPart" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            </label>
            <label class="space-y-2">
              <div class="data-label">版本</div>
              <input v-model="form.version" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            </label>
            <label class="space-y-2">
              <div class="data-label">修改人</div>
              <input v-model="form.updatedBy" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            </label>
          </div>

          <label class="space-y-2">
            <div class="data-label">阈值摘要</div>
            <textarea v-model="form.thresholdsSummary" rows="3" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          </label>

          <label class="space-y-2">
            <div class="data-label">修改说明</div>
            <textarea v-model="form.changeNote" rows="3" class="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          </label>

          <div class="grid gap-4 md:grid-cols-2">
            <label class="space-y-2">
              <div class="data-label">ROI</div>
              <div class="grid grid-cols-4 gap-2">
                <input v-for="(_, index) in form.roi" :key="`roi-${index}`" v-model.number="form.roi[index]" type="number" class="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
              </div>
            </label>
            <label class="space-y-2">
              <div class="data-label">二维码 ROI</div>
              <div class="grid grid-cols-4 gap-2">
                <input v-for="(_, index) in form.qrRoi" :key="`qr-${index}`" v-model.number="form.qrRoi[index]" type="number" class="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
              </div>
            </label>
          </div>

          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-4">
            <div class="flex items-center justify-between">
              <div class="panel-title">分拣规则</div>
              <button class="rounded-xl border border-slate-700 px-3 py-2 text-sm text-slate-100 hover:border-slate-500" @click="addRule">新增规则</button>
            </div>
            <div class="mt-4 space-y-3">
              <div v-for="(rule, index) in form.sortRules" :key="index" class="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <input v-model="rule.condition" class="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" placeholder="条件" />
                <input v-model="rule.action" class="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" placeholder="动作" />
                <button class="rounded-xl border border-rose-500/30 px-3 py-2 text-sm text-rose-200" @click="removeRule(index)">删除</button>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap gap-3">
            <button class="rounded-2xl bg-sky-500 px-4 py-3 text-sm font-semibold text-white hover:bg-sky-400" @click="saveRecipe">
              {{ saving ? '保存中…' : '保存配方' }}
            </button>
            <button class="rounded-2xl border border-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 hover:border-slate-500" @click="resetEditor">重置编辑器</button>
            <span v-if="hasUnsavedChanges" class="inline-flex items-center rounded-full border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">存在未保存修改</span>
          </div>
        </div>

        <div class="space-y-4 rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4">
          <div>
            <div class="data-label">当前配置预览</div>
            <div class="mt-3 space-y-2 text-sm text-slate-200">
              <div v-for="line in formPreview" :key="line">{{ line }}</div>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-4">
            <div class="data-label">与当前版本差异</div>
            <div class="mt-3 space-y-2 text-sm text-slate-300">
              <div v-for="line in diffPreview" :key="line">• {{ line }}</div>
            </div>
          </div>

          <div class="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-4">
            <div class="data-label">历史版本</div>
            <div v-if="activeHistory.length" class="mt-3 space-y-2 text-sm text-slate-300">
              <div v-for="item in activeHistory" :key="`${item.id}-${item.version}`" class="rounded-2xl border border-slate-800/80 px-3 py-2">
                <div class="font-semibold text-slate-100">{{ item.version }}</div>
                <div class="mt-1">{{ item.updatedAt.slice(0, 19).replace('T', ' ') }}</div>
                <div class="mt-1 text-xs text-slate-400">{{ item.changeNote || '无备注' }}</div>
              </div>
            </div>
            <div v-else class="mt-3 text-sm text-slate-500">当前配方暂无历史版本。</div>
          </div>

          <div v-if="validationErrors.length" class="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-4 text-sm text-amber-200">
            <div class="font-semibold">保存前需修正</div>
            <ul class="mt-2 space-y-1">
              <li v-for="error in validationErrors" :key="error">• {{ error }}</li>
            </ul>
          </div>
        </div>
      </div>
    </SectionCard>
  </div>
</template>
