import {expect, test, type Page} from '@playwright/test';

const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';
const adminEmail = process.env.ADMIN_E2E_EMAIL ?? 'admin-e2e@example.com';
const adminPassword = process.env.ADMIN_E2E_PASSWORD ?? 'admin-e2e-password';

async function openSyncManager(page: Page) {
  await page.goto(`${apiBaseUrl}/admin/login/?mode=password`);
  await page.getByLabel('Email', {exact: true}).fill(adminEmail);
  await page.getByLabel('Password', {exact: true}).fill(adminPassword);
  await page.getByRole('button', {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/admin\/?$/);
  await page.goto(`${apiBaseUrl}/admin/event/event/`);
  await page.getByRole('link', {name: 'E2E Event Copy Template', exact: true}).click();
  await page.getByRole('link', {name: 'Manage sync', exact: true}).first().click();
  await expect(page).toHaveURL(/\/sheet-sync\/$/);
}

// The seed database contains no Google credentials and no worker is started.
// This exercises the actual server-rendered management form without provider writes.
test.describe.serial('Registration sheet management', {tag: '@admin'}, () => {
  test('persists settings, rejects conflicting columns, and works on mobile', async ({page}, testInfo) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await openSyncManager(page);
    const managerUrl = page.url();

    await page.locator('input[name="sync_mode"][value="manual"]').check();
    await page.locator('#id_header_row').fill('3');
    await page.getByRole('button', {name: 'Save settings', exact: true}).click();
    await page.reload();
    await expect(page.locator('input[name="sync_mode"][value="manual"]')).toBeChecked();
    await expect(page.locator('#id_header_row')).toHaveValue('3');

    await page.getByLabel('First Name sheet column', {exact: true}).fill('A');
    await page.getByLabel('Last Name sheet column', {exact: true}).fill('A');
    await page.getByRole('button', {name: 'Save settings', exact: true}).click();
    await expect(page.getByText('Each sheet column can be mapped to only one field.', {exact: true})).toBeVisible();
    await page.goto(managerUrl);
    await expect(page.getByLabel('First Name sheet column', {exact: true})).toBeEmpty();
    await expect(page.locator('#id_header_row')).toHaveValue('3');

    await page.locator('input[name="sync_mode"][value="interval"]').check();
    await page.locator('#id_interval_minutes').selectOption('15');
    await page.getByRole('button', {name: 'Save settings', exact: true}).click();
    await page.reload();
    await expect(page.locator('input[name="sync_mode"][value="interval"]')).toBeChecked();
    await expect(page.locator('#id_interval_minutes')).toHaveValue('15');
    await page.screenshot({path: testInfo.outputPath('sync-management-desktop.png')});

    await page.setViewportSize({width: 390, height: 844});
    await expect(page.getByRole('button', {name: 'Save settings', exact: true})).toBeVisible();
    await expect(page.getByRole('button', {name: 'Preview changes', exact: true})).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await page.screenshot({path: testInfo.outputPath('sync-management-mobile.png'), fullPage: true});

    // Restore the isolated fixture for other admin browser flows.
    await page.locator('input[name="sync_mode"][value="automatic"]').check();
    await page.locator('#id_header_row').fill('1');
    await page.getByRole('button', {name: 'Save settings', exact: true}).click();
    expect(errors).toEqual([]);
  });
});
