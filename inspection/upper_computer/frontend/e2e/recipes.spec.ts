import { test, expect } from '@playwright/test';

test('mock mode recipes page exposes overview and editor affordances', async ({ page }) => {
  await page.goto('/recipes');
  await expect(page.getByText('配方总览')).toBeVisible();
  await expect(page.getByText('配方编辑器')).toBeVisible();
  await expect(page.getByRole('button', { name: /保存配方/i })).toBeVisible();
});
