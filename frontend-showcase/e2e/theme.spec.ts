import { expect, test } from '@playwright/test';

test('switches to light mode', async ({ page }, testInfo) => {
  await page.goto('/showcase');
  await page.getByTestId('theme-toggle').click();
  await expect
    .poll(() => page.locator('html').evaluate((element) => element.classList.contains('dark')))
    .toBe(true);
  await page.getByTestId('theme-toggle').click();
  await expect
    .poll(() => page.locator('html').evaluate((element) => element.classList.contains('dark')))
    .toBe(false);
  await page.screenshot({ path: testInfo.outputPath('light.png') });
});
