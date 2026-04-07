import { defineStore } from 'pinia';
import type { RecipeProfile } from '@/shared/types/domain';

export const useRecipeStore = defineStore('recipe', {
  state: () => ({
    items: [] as RecipeProfile[],
    editingRecipeId: '' as string,
    draftDirty: false,
    historyMap: {} as Record<string, RecipeProfile[]>,
  }),
  getters: {
    activeRecipe: (state) => state.items.find((item) => item.enabled) ?? null,
    editingRecipe: (state) => state.items.find((item) => item.id === state.editingRecipeId) ?? null,
    recipeHistory: (state) => (recipeId: string) => state.historyMap[recipeId] ?? [],
  },
  actions: {
    setRecipes(recipes: RecipeProfile[]) {
      this.items = recipes;
      recipes.forEach((recipe) => {
        const history = this.historyMap[recipe.id] ?? [];
        if (!history.some((item) => item.version === recipe.version)) {
          this.historyMap[recipe.id] = [recipe, ...history].slice(0, 8);
        }
      });
    },
    upsertRecipe(recipe: RecipeProfile) {
      const idx = this.items.findIndex((item) => item.id === recipe.id);
      if (idx >= 0) this.items.splice(idx, 1, recipe);
      else this.items.unshift(recipe);

      const history = this.historyMap[recipe.id] ?? [];
      const deduped = [recipe, ...history.filter((item) => item.version !== recipe.version)];
      this.historyMap[recipe.id] = deduped.slice(0, 8);
    },
    activateRecipe(recipeId: string) {
      this.items = this.items.map((item) => ({ ...item, enabled: item.id === recipeId }));
    },
    beginEdit(recipeId: string) {
      this.editingRecipeId = recipeId;
    },
    setDraftDirty(value: boolean) {
      this.draftDirty = value;
    },
  },
});
