import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { pinia } from '@/app/pinia';
import { useRecipeStore } from '@/entities/recipe/store';
import { useAppStore } from '@/entities/app/store';

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/run' },
  { path: '/run', name: 'run', component: () => import('@/pages/RunDashboardPage.vue') },
  { path: '/live', name: 'live', component: () => import('@/pages/LiveInspectionPage.vue') },
  { path: '/trace', name: 'trace', component: () => import('@/pages/ResultTracePage.vue') },
  { path: '/stats', name: 'stats', component: () => import('@/pages/StatisticsPage.vue') },
  { path: '/recipes', name: 'recipes', component: () => import('@/pages/RecipeManagerPage.vue') },
  { path: '/diagnostics', name: 'diagnostics', component: () => import('@/pages/DiagnosticsPage.vue') },
  { path: '/settings', name: 'settings', component: () => import('@/pages/SettingsPage.vue') },
  { path: '/demo', name: 'demo', component: () => import('@/pages/DemoModePage.vue') },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to, from) => {
  if (from.name === 'recipes' && to.name !== 'recipes') {
    const recipeStore = useRecipeStore(pinia);
    if (recipeStore.draftDirty) {
      const appStore = useAppStore(pinia);
      const confirmed = await appStore.confirmAction({
        title: '离开配方页？',
        message: '当前存在未保存配方修改，离开后这些更改可能丢失。',
        tone: 'WARN',
        confirmLabel: '仍然离开',
      });
      if (!confirmed) return false;
      recipeStore.setDraftDirty(false);
    }
  }
  return true;
});

export default router;
