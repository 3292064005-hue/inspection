import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';
const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ?? (existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
const useExternalServer = process.env.PLAYWRIGHT_EXTERNAL_SERVER === '1';
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:4173';
export default defineConfig({
  testDir: './e2e', timeout: 30_000, retries: 0,
  use: {
    baseURL,
    trace: 'on-first-retry',
    launchOptions: chromiumExecutable ? { executablePath: chromiumExecutable, args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'] } : {},
  },
  webServer: useExternalServer ? undefined : { command: 'npm run build:mock && npm run preview -- --host 127.0.0.1 --port 4173', url: baseURL, reuseExistingServer: true, timeout: 120_000 },
});
