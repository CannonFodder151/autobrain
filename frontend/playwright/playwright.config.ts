import { defineConfig, devices } from '@playwright/test';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:8080';

export default defineConfig({
  testDir: 'tests',
  snapshotDir: 'tests/visual/__screenshots__',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: baseUrl,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop-1280',
      use: devices['Desktop Chrome'],
    },
    {
      name: 'desktop-1440',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'desktop-1920',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1920, height: 1080 } },
    },
  ],
});
