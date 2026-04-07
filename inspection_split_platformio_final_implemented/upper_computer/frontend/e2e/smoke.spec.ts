import { test, expect } from '@playwright/test';

test('mock mode dashboard loads top header and navigation', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('ROS2 桌面视觉质检与自动分拣工作站')).toBeVisible();
  await expect(page.getByRole('link', { name: /运行总览/i })).toBeVisible();
});
