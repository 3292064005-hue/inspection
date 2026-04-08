import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { effectScope, nextTick } from 'vue';

const getRecipesMock = vi.fn();
const activateRecipeMock = vi.fn();
const saveRecipeMock = vi.fn();

vi.mock('@/shared/gateway/service', () => ({
  getGateway: () => ({
    getRecipes: getRecipesMock,
    activateRecipe: activateRecipeMock,
    saveRecipe: saveRecipeMock,
  }),
}));

import { useRecipeManagement } from '@/features/recipe-management/useRecipeManagement';
import { useAppStore } from '@/entities/app/store';
import { useRecipeStore } from '@/entities/recipe/store';
import { invalidateCache } from '@/shared/query/cache';

describe('useRecipeManagement', () => {
  beforeEach(() => {
    localStorage.clear();
    invalidateCache();
    setActivePinia(createPinia());
    getRecipesMock.mockReset();
    activateRecipeMock.mockReset();
    saveRecipeMock.mockReset();
  });

  it('loads recipes and activates selected recipe with notice feedback', async () => {
    getRecipesMock.mockResolvedValue([
      {
        id: 'recipe-a',
        name: '配方A',
        version: '1.0.0',
        targetPart: '零件A',
        roi: [1, 2, 3, 4],
        qrRoi: [5, 6, 7, 8],
        thresholdsSummary: 'summary',
        sortRules: [{ condition: 'decision == OK', action: 'BOX_OK' }],
        enabled: true,
        updatedAt: '2026-04-02T00:00:00Z',
        updatedBy: 'alice',
        changeNote: 'note',
      },
    ]);

    const scope = effectScope();
    const api = scope.run(() => useRecipeManagement());
    if (!api) throw new Error('composable init failed');
    await api.refreshRecipes(true);
    await nextTick();

    expect(api.recipes.value).toHaveLength(1);
    await api.activateRecipe('recipe-a');

    const appStore = useAppStore();
    const recipeStore = useRecipeStore();
    expect(activateRecipeMock).toHaveBeenCalledWith('recipe-a');
    expect(recipeStore.activeRecipe?.id).toBe('recipe-a');
    expect(appStore.latestNotice?.title).toBe('配方已切换');
    scope.stop();
  });

  it('validates and saves recipes with patch-version bump', async () => {
    getRecipesMock.mockResolvedValue([]);
    saveRecipeMock.mockImplementation(async (payload) => ({ ...payload, name: payload.name }));

    const scope = effectScope();
    const api = scope.run(() => useRecipeManagement());
    if (!api) throw new Error('composable init failed');
    await api.refreshRecipes(true);
    await nextTick();

    api.form.name = '新配方';
    api.form.targetPart = '新工件';
    api.form.updatedBy = 'operator';
    api.form.changeNote = '新增阈值';
    api.form.sortRules = [{ condition: 'decision == OK', action: 'BOX_OK' }];
    await api.saveRecipe();

    const recipeStore = useRecipeStore();
    expect(saveRecipeMock).toHaveBeenCalled();
    expect(String(saveRecipeMock.mock.calls[0][0].version)).toBe('1.0.1');
    expect(recipeStore.items).toHaveLength(1);
    scope.stop();
  });
});
