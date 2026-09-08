import { test, expect } from '@playwright/test';

const baseUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:8080';

const screens = [
  { name: 'home', path: '/' },
  { name: 'vehicles', path: '/vehicles' },
];

test.describe('Desktop visual regression', () => {
  for (const screen of screens) {
    test(`${screen.name} — no visual delta vs baseline`, async ({ page }) => {
      await page.goto(`${baseUrl}${screen.path}`);
      await page.waitForLoadState('networkidle');

      await expect(page).toHaveScreenshot(`${screen.name}.png`, {
        fullPage: true,
        threshold: 0.02,
      });
    });
  }
});
