import { expect, test, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/chat');
  await expect(page.getByRole('heading', { name: 'What are we firing up?' })).toBeVisible();
});

async function revealSidebar(page: Page): Promise<void> {
  const newChat = page.getByTestId('new-chat');
  if (await newChat.isVisible()) {
    return;
  }
  await page.getByRole('button', { name: 'Toggle Sidebar' }).click();
  await expect(newChat).toBeVisible();
}

test('shows the empty chat', async ({ page }, testInfo) => {
  await expect(page.getByText('Nothing leaves this page.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Plan a quiet weekend' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('empty.png') });
});

test('streams a reply from a starter prompt', async ({ page }, testInfo) => {
  await page.getByRole('button', { name: 'Plan a quiet weekend' }).click();
  await expect(page.getByTestId('message-user')).toContainText('Plan a quiet weekend');
  await expect(page.getByTestId('message-assistant')).toContainText('Leave one evening empty on purpose');
  await expect(page.getByTestId('stop')).toHaveCount(0);
  await revealSidebar(page);
  await expect(page.getByTestId('conversation')).toContainText('Plan a quiet weekend');
  await expect(page.getByTestId('chat-title')).toHaveText('Plan a quiet weekend');
  await page.screenshot({ path: testInfo.outputPath('conversation.png') });
});

test('sends a typed message, opens a new chat, and switches back', async ({ page }) => {
  await page.getByTestId('composer').fill('Explain signals in Angular');
  await page.getByTestId('send').click();
  await expect(page.getByTestId('message-assistant')).toContainText('computed signal');

  await revealSidebar(page);
  await page.getByTestId('new-chat').click();
  await expect(page.getByRole('heading', { name: 'What are we firing up?' })).toBeVisible();

  await revealSidebar(page);
  await page.getByTestId('conversation').click();
  await expect(page.getByTestId('message-user')).toContainText('Explain signals in Angular');
});

test('renames and deletes a chat', async ({ page }) => {
  await page.getByRole('button', { name: 'Draft a short note' }).click();
  await expect(page.getByTestId('message-assistant')).toContainText('Friday');

  await page.getByTestId('chat-menu').click();
  await page.getByRole('menuitem', { name: 'Rename' }).click();
  await page.getByTestId('rename-input').fill('Field notes');
  await page.getByTestId('rename-save').click();
  await expect(page.getByTestId('chat-title')).toHaveText('Field notes');
  await revealSidebar(page);
  await expect(page.getByTestId('conversation')).toContainText('Field notes');
  await page.getByTestId('conversation').click();

  await page.getByTestId('chat-menu').click();
  await page.getByRole('menuitem', { name: 'Delete' }).click();
  await expect(page.getByTestId('conversation')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'What are we firing up?' })).toBeVisible();
});

test('switches to light mode', async ({ page }, testInfo) => {
  await page.getByTestId('theme-toggle').click();
  await expect
    .poll(() => page.locator('html').evaluate((element) => element.classList.contains('dark')))
    .toBe(false);
  await page.screenshot({ path: testInfo.outputPath('light.png') });
});
