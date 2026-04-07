import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useRecipeStore } from '@/entities/recipe/store';
const makeRecipe = (id: string, version: string, enabled = false) => ({ id, name: `${id}-${version}`, version, targetPart: 'part', roi: [0,0,10,10], qrRoi: [0,0,10,10], thresholdsSummary: 'summary', sortRules: [], enabled, updatedAt: new Date().toISOString(), updatedBy: 'tester', changeNote: '' });
describe('recipe store', () => {
  beforeEach(() => setActivePinia(createPinia()));
  it('keeps recipe history and active recipe state', () => {
    const store = useRecipeStore();
    store.setRecipes([makeRecipe('r1','1.0.0',true)]);
    store.upsertRecipe(makeRecipe('r1','1.1.0'));
    store.beginEdit('r1');
    store.setDraftDirty(true);
    store.activateRecipe('r1');
    expect(store.activeRecipe?.id).toBe('r1');
    expect(store.editingRecipe?.version).toBe('1.1.0');
    expect(store.recipeHistory('r1')).toHaveLength(2);
  });
});
