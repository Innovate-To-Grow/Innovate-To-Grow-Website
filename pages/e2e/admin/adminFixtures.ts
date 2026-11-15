import {expect, type Page} from '@playwright/test';

// Shared setup of the live Django-admin specs (admin*.spec.ts): the seeded accounts and records
// (manage.py seed_admin_e2e) and the admin page helpers.
export const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';
export const adminEmail = process.env.ADMIN_E2E_EMAIL ?? 'admin-e2e@example.com';
export const adminPassword = process.env.ADMIN_E2E_PASSWORD ?? 'admin-e2e-password';
export const nonstaffEmail = process.env.ADMIN_E2E_NONSTAFF_EMAIL ?? 'admin-e2e-nonstaff@example.com';
export const actionEmail = process.env.ADMIN_E2E_ACTION_EMAIL ?? 'action-e2e@example.com';
export const seededProjectTitle = 'E2E Solar Orchard Dashboard';
export const seededSemesterLabel = '2099-2 Fall';
export const seededEventTemplateName = 'E2E Event Copy Template';
export const themeRuntimeErrorPattern =
  /theme is not defined|adminTheme is not defined|themeBindings is not defined|openModal is not defined/i;

export async function adminLogin(page: Page, email = adminEmail, password = adminPassword) {
  await page.goto(`${apiBaseUrl}/admin/login/?mode=password`, {waitUntil: 'domcontentloaded'});
  await expect(page.locator('.login-title, h1, [role="heading"]').first()).toBeVisible();

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', {name: /sign in/i}).click();
}

export async function expectLoggedInAdmin(page: Page) {
  await expect(page).toHaveURL(/\/admin\/?(?:\?.*)?$/);
  await expect(page.locator('body')).toContainText(/Welcome to I2G Admin|Innovate To Grow Admin|I2G Admin/i);
}

export function collectThemeRuntimeErrors(page: Page) {
  const errors: string[] = [];

  page.on('console', (message) => {
    if (!['error', 'warning'].includes(message.type())) return;
    if (themeRuntimeErrorPattern.test(message.text())) errors.push(message.text());
  });

  page.on('pageerror', (error) => {
    if (themeRuntimeErrorPattern.test(error.message)) errors.push(error.message);
  });

  return errors;
}

export async function expectAdminDocument(page: Page, path: string) {
  const response = await page.goto(`${apiBaseUrl}${path}`, {waitUntil: 'domcontentloaded'});
  expect(response, `${path} returned a response`).not.toBeNull();
  expect(response?.status(), `${path} should load successfully`).toBeLessThan(400);
  await expect(page.locator('body')).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/Traceback|Internal Server Error/i);
}

export async function confirmAdminSaveIfRequired(page: Page, confirmationWord: string) {
  if (!/\/confirm-change\//.test(page.url())) return;

  await page.locator('#confirm-input').fill(confirmationWord);
  await page.locator('#confirm-btn').click();
}

export async function runChangelistAction(page: Page, rowText: string, actionValue: string) {
  const row = page.locator('tr', {hasText: rowText}).first();
  await expect(row, `Expected an admin row containing ${rowText}`).toBeVisible();
  await row.locator('input[name="_selected_action"]').check();
  await page.locator('select[name="action"]').selectOption(actionValue);
  await page.getByTitle('Run the selected action').click();

  if (/\/confirm-action\//.test(page.url())) {
    await page.locator('#confirm-input').fill('Contact Email');
    await page.getByRole('button', {name: /confirm action/i}).click();
  }
}
