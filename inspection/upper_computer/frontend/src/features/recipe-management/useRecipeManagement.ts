import { computed, reactive, ref, watch } from 'vue';
import { getGateway } from '@/shared/gateway/service';
import { useRecipeStore } from '@/entities/recipe/store';
import { useAppStore } from '@/entities/app/store';
import type { RecipeProfile } from '@/shared/types/domain';
import { fetchWithCache, invalidateCache } from '@/shared/query/cache';

const DRAFT_STORAGE_KEY = 'inspection-hmi-recipe-draft';

function cloneRecipeProfile<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function nextPatchVersion(version: string): string {
  const parts = version.split('.').map((item) => Number(item));
  if (parts.length !== 3 || parts.some((item) => Number.isNaN(item))) return '1.0.0';
  parts[2] += 1;
  return parts.join('.');
}

function blankRecipe(): RecipeProfile {
  return {
    id: `recipe-${Math.random().toString(36).slice(2, 8)}`,
    name: '新配方',
    version: '1.0.0',
    targetPart: '待定义工件',
    roi: [240, 120, 520, 300],
    qrRoi: [320, 160, 160, 160],
    thresholdsSummary: 'HSV 阈值 + 面积约束',
    sortRules: [
      { condition: 'decision == OK', action: 'BOX_OK' },
      { condition: 'decision != OK', action: 'BOX_NG' },
    ],
    enabled: false,
    updatedAt: new Date().toISOString(),
    updatedBy: 'operator',
    changeNote: '初始化配方',
  };
}

function loadDraft(): RecipeProfile | null {
  try {
    const raw = localStorage.getItem(DRAFT_STORAGE_KEY);
    return raw ? JSON.parse(raw) as RecipeProfile : null;
  } catch {
    return null;
  }
}

function recipeDiff(current: RecipeProfile, baseline: RecipeProfile | null): string[] {
  if (!baseline) return ['新建配方'];
  const diff: string[] = [];
  if (current.name !== baseline.name) diff.push(`名称：${baseline.name} → ${current.name}`);
  if (current.targetPart !== baseline.targetPart) diff.push(`目标工件：${baseline.targetPart} → ${current.targetPart}`);
  if (current.thresholdsSummary !== baseline.thresholdsSummary) diff.push(`阈值摘要：${baseline.thresholdsSummary} → ${current.thresholdsSummary}`);
  if (current.roi.join(',') !== baseline.roi.join(',')) diff.push(`ROI：${baseline.roi.join(', ')} → ${current.roi.join(', ')}`);
  if (current.qrRoi.join(',') !== baseline.qrRoi.join(',')) diff.push(`QR ROI：${baseline.qrRoi.join(', ')} → ${current.qrRoi.join(', ')}`);
  if (current.sortRules.length !== baseline.sortRules.length) diff.push(`规则条数：${baseline.sortRules.length} → ${current.sortRules.length}`);
  return diff.length ? diff : ['当前修改仅涉及版本或备注'];
}

export function useRecipeManagement() {
  const gateway = getGateway();
  const appStore = useAppStore();
  const recipeStore = useRecipeStore();
  const saving = ref(false);
  const loading = ref(false);
  const editingBaseVersion = ref('1.0.0');
  const form = reactive<RecipeProfile>(blankRecipe());

  const recipes = computed(() => recipeStore.items);
  const activeHistory = computed(() => recipeStore.recipeHistory(form.id));
  const currentEditingRecipe = computed(() => recipeStore.items.find((item) => item.id === form.id) ?? null);
  const formPreview = computed(() => [
    `ROI：${form.roi.join(', ')}`,
    `QR ROI：${form.qrRoi.join(', ')}`,
    `修改人：${form.updatedBy || '--'}`,
    `备注：${form.changeNote || '--'}`,
    ...form.sortRules.map((rule, index) => `规则 ${index + 1}：${rule.condition} → ${rule.action}`),
  ]);
  const diffPreview = computed(() => recipeDiff(form, currentEditingRecipe.value));
  const validationErrors = computed(() => {
    const errors: string[] = [];
    if (!form.name.trim()) errors.push('配方名称不能为空');
    if (!form.targetPart.trim()) errors.push('目标工件不能为空');
    if (!form.updatedBy?.trim()) errors.push('请填写修改人');
    if (!form.changeNote?.trim()) errors.push('请填写修改说明');
    if (form.roi.length !== 4 || form.roi.some((item) => Number.isNaN(Number(item)))) errors.push('ROI 必须为 4 个数字');
    if (form.qrRoi.length !== 4 || form.qrRoi.some((item) => Number.isNaN(Number(item)))) errors.push('QR ROI 必须为 4 个数字');
    if (!form.sortRules.length) errors.push('至少保留 1 条分拣规则');
    if (form.sortRules.some((item) => !item.condition.trim() || !item.action.trim())) errors.push('分拣规则的条件和动作不能为空');
    return errors;
  });
  const hasUnsavedChanges = ref(false);

  watch(form, () => {
    hasUnsavedChanges.value = true;
    recipeStore.setDraftDirty(true);
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(form));
  }, { deep: true });

  async function refreshRecipes(force = false) {
    loading.value = true;
    try {
      const items = await fetchWithCache('recipes:list', () => gateway.getRecipes(), { ttlMs: 8000, force, allowStale: true });
      recipeStore.setRecipes(items);
      if (!recipeStore.editingRecipeId && items[0]) recipeStore.beginEdit(items[0].id);
    } catch (error) {
      appStore.pushNotice({ level: 'ERROR', title: '读取配方失败', message: error instanceof Error ? error.message : '未知错误' });
    } finally {
      loading.value = false;
    }
  }

  function populate(recipe?: RecipeProfile) {
    const source = recipe ? cloneRecipeProfile(recipe) : loadDraft() ?? blankRecipe();
    Object.assign(form, source);
    editingBaseVersion.value = source.version;
    hasUnsavedChanges.value = false;
    recipeStore.setDraftDirty(false);
  }

  async function activateRecipe(recipeId: string) {
    try {
      await gateway.activateRecipe(recipeId);
      recipeStore.activateRecipe(recipeId);
      invalidateCache('recipes:');
      appStore.pushNotice({ level: 'INFO', title: '配方已切换', message: `当前启用：${recipeStore.items.find((item) => item.id === recipeId)?.name ?? recipeId}` });
    } catch (error) {
      appStore.pushNotice({ level: 'ERROR', title: '配方切换失败', message: error instanceof Error ? error.message : '未知错误' });
    }
  }

  function editRecipe(recipe: RecipeProfile) {
    recipeStore.beginEdit(recipe.id);
    populate(recipe);
  }

  function cloneRecipe(recipe: RecipeProfile) {
    populate({
      ...cloneRecipeProfile(recipe),
      id: `recipe-${Math.random().toString(36).slice(2, 8)}`,
      name: `${recipe.name}-复制`,
      version: nextPatchVersion(recipe.version),
      enabled: false,
      updatedBy: form.updatedBy || 'operator',
      changeNote: `基于 ${recipe.name} 复制`,
    });
  }

  function addRule() {
    form.sortRules.push({ condition: '', action: '' });
  }

  function removeRule(index: number) {
    if (form.sortRules.length === 1) return;
    form.sortRules.splice(index, 1);
  }

  async function resetEditor() {
    if (hasUnsavedChanges.value) {
      const confirmed = await appStore.confirmAction({
        title: '放弃当前配方编辑？',
        message: '当前表单存在未保存修改，继续会丢失这些内容。',
        tone: 'WARN',
        confirmLabel: '放弃修改',
      });
      if (!confirmed) return;
    }
    localStorage.removeItem(DRAFT_STORAGE_KEY);
    populate();
  }

  async function saveRecipe() {
    if (validationErrors.value.length) {
      appStore.pushNotice({ level: 'WARN', title: '配方校验失败', message: validationErrors.value.join('；') });
      return;
    }

    saving.value = true;
    try {
      if (form.version === editingBaseVersion.value) {
        form.version = nextPatchVersion(form.version);
      }
      form.updatedAt = new Date().toISOString();
      const saved = await gateway.saveRecipe({ ...form, sortRules: cloneRecipeProfile(form.sortRules) });
      recipeStore.upsertRecipe(saved);
      invalidateCache('recipes:');
      hasUnsavedChanges.value = false;
      recipeStore.setDraftDirty(false);
      localStorage.removeItem(DRAFT_STORAGE_KEY);
      appStore.pushNotice({ level: 'INFO', title: '配方已保存', message: `${saved.name} 已保存为 ${saved.version}` });
    } catch (error) {
      appStore.pushNotice({ level: 'ERROR', title: '配方保存失败', message: error instanceof Error ? error.message : '未知错误' });
    } finally {
      saving.value = false;
    }
  }

  void refreshRecipes();
  populate();

  return {
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
    populate,
    saveRecipe,
    activateRecipe,
    editRecipe,
    cloneRecipe,
    addRule,
    removeRule,
    resetEditor,
  };
}
