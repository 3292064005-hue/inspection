<script setup lang="ts">
import type { RecipeProfile } from '@/shared/types/domain';
import { formatDateTime } from '@/shared/utils/format';

defineProps<{
  recipes: RecipeProfile[];
}>();

const emit = defineEmits<{
  (e: 'activate', recipeId: string): void;
  (e: 'edit', recipe: RecipeProfile): void;
  (e: 'clone', recipe: RecipeProfile): void;
}>();
</script>

<template>
  <div class="overflow-hidden rounded-2xl border border-slate-800/80">
    <table class="min-w-full divide-y divide-slate-800 text-left text-sm">
      <thead class="bg-slate-900/90 text-slate-300">
        <tr>
          <th class="px-4 py-3">配方名</th>
          <th class="px-4 py-3">目标工件</th>
          <th class="px-4 py-3">阈值摘要</th>
          <th class="px-4 py-3">版本</th>
          <th class="px-4 py-3">更新时间</th>
          <th class="px-4 py-3 text-center">状态</th>
          <th class="px-4 py-3 text-right">操作</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-800 bg-slate-950/60">
        <tr v-for="recipe in recipes" :key="recipe.id">
          <td class="px-4 py-3 font-medium text-slate-100">{{ recipe.name }}</td>
          <td class="px-4 py-3 text-slate-300">{{ recipe.targetPart }}</td>
          <td class="px-4 py-3 text-slate-300">{{ recipe.thresholdsSummary }}</td>
          <td class="px-4 py-3 text-slate-300">{{ recipe.version }}</td>
          <td class="px-4 py-3 text-slate-400">{{ formatDateTime(recipe.updatedAt) }}</td>
          <td class="px-4 py-3 text-center">
            <span
              class="status-pill"
              :class="recipe.enabled ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-300' : 'border-slate-700 bg-slate-900 text-slate-300'"
            >
              {{ recipe.enabled ? '已启用' : '停用' }}
            </span>
          </td>
          <td class="px-4 py-3 text-right">
            <div class="flex justify-end gap-2">
              <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs font-medium text-slate-100 hover:border-slate-500" @click="emit('edit', recipe)">编辑</button>
              <button class="rounded-xl border border-slate-700 px-3 py-2 text-xs font-medium text-slate-100 hover:border-slate-500" @click="emit('clone', recipe)">克隆</button>
              <button
                class="rounded-xl border border-slate-700 px-3 py-2 text-xs font-medium text-slate-100 hover:border-slate-500"
                @click="emit('activate', recipe.id)"
              >
                切换为当前配方
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
