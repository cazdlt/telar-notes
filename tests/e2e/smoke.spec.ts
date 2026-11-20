import { expect, test } from '@playwright/test';

test.describe('Telar Notes smoke', () => {
  test('loads vault and renders explorer', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('#vault-switcher')).toContainText('vault');
    await expect(page.getByRole('treeitem', { name: 'welcome' })).toBeVisible();
    await expect(page.getByRole('treeitem', { name: 'second' })).toBeVisible();
  });

  test('opens a note, edits content, and persists autosave on reload', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('treeitem', { name: 'welcome' }).click();
    await expect(page.locator('#note-title-main')).toHaveText('welcome');

    const editor = page.locator('.cm-content');
    await expect(editor).toContainText('Initial smoke content.');

    const addition = 'Smoke edit persisted.';
    const saveResponse = page.waitForResponse(
      (res) => res.url().includes('/api/note') && res.request().method() === 'POST' && res.ok(),
    );
    await editor.click();
    await page.keyboard.press('Enter');
    await page.keyboard.type(addition);
    await saveResponse;
    await expect(page.locator('#save-status')).toContainText('Saved');

    await page.reload();
    await expect(page.locator('#note-title-main')).toHaveText('welcome');
    await expect(page.locator('.cm-content')).toContainText(addition);
  });

  test('opens search palette and finds a note', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: 'Search' }).click();
    const dialog = page.getByRole('dialog', { name: 'Search notes' });
    await expect(dialog).toBeVisible();

    await dialog.locator('#cmd-k-input').fill('Findable');
    const match = dialog.getByRole('button', { name: /second\.md/ });
    await expect(match).toBeVisible();
    await match.click();

    await expect(dialog).toBeHidden();
    await expect(page.locator('#note-title-main')).toHaveText('second');
    await expect(page.locator('.cm-content')).toContainText('Findable via search palette.');
  });

  test('opens settings modal', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: 'Settings' }).click();
    const dialog = page.getByRole('dialog', { name: 'Settings' });
    await expect(dialog).toBeVisible();

    await dialog.getByRole('button', { name: 'Close settings' }).click();
    await expect(dialog).toBeHidden();
  });
});
