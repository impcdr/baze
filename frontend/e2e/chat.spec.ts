import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('kiln.theme.v2', 'light');
    localStorage.setItem('kiln.theme', 'light');
  });
  await page.goto('/chat');
  await expect(page.getByTestId('chat-title')).toHaveText('Studio invoices');
});

test('opens the seeded conversation at the latest message', async ({ page }, testInfo) => {
  await expect(page.getByTestId('message-user').first()).toContainText('studio invoices');
  await expect(page.getByTestId('message-assistant').last()).toContainText('Add invoice');
  const log = page.getByRole('log', { name: 'Conversation' });
  await expect
    .poll(() => log.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight))
    .toBeLessThan(48);
  await expect(page.getByTestId('message-user').last()).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('seed-bottom.png') });

  await log.evaluate((el) => {
    el.scrollTop = 0;
  });
  await expect(page.getByTestId('message-user').first()).toBeInViewport();
  await page.screenshot({ path: testInfo.outputPath('seed-top.png') });
});

test('sends a typed message', async ({ page }, testInfo) => {
  await page.getByTestId('composer').fill('Plan a quiet weekend');
  await page.getByTestId('send').click();
  await expect(page.getByTestId('message-assistant').last()).toContainText('Leave one evening empty on purpose');
  await expect(page.getByTestId('stop')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('reply.png') });
});

test('starts a new chat and switches back', async ({ page }, testInfo) => {
  await page.getByTestId('new-chat').click();
  await expect(page.getByRole('heading', { name: 'What should we talk through?' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Plan a quiet weekend' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('empty.png') });

  await page.getByTestId('chat-title').click();
  await page.getByTestId('conversation').click();
  await expect(page.getByTestId('chat-title')).toHaveText('Studio invoices');
  await expect(page.getByTestId('message-user').first()).toContainText('studio invoices');
});

test('renames and deletes a chat', async ({ page }) => {
  await page.getByTestId('chat-menu').click();
  await page.getByRole('menuitem', { name: 'Rename' }).click();
  await page.getByTestId('rename-input').fill('Field notes');
  await page.getByTestId('rename-save').click();
  await expect(page.getByTestId('chat-title')).toHaveText('Field notes');

  await page.getByTestId('chat-menu').click();
  await page.getByRole('menuitem', { name: 'Delete' }).click();
  await expect(page.getByRole('heading', { name: 'What should we talk through?' })).toBeVisible();
  await expect(page.getByTestId('message-user')).toHaveCount(0);
});
