import { test, expect } from '@playwright/test';

test('mock mode trace page exposes filters and export actions', async ({ page }) => {
  await page.goto('/trace');
  await expect(page.getByText('结果追溯筛选')).toBeVisible();
  await expect(page.getByRole('button', { name: /导出全部结果/i })).toBeVisible();
  await expect(page.getByText('结果列表')).toBeVisible();
});
