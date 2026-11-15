import {expect, test} from '@playwright/test';

import {
  apiBaseUrl,
  adminEmail,
  adminPassword,
  nonstaffEmail,
  actionEmail,
  adminLogin,
  expectLoggedInAdmin,
  collectThemeRuntimeErrors,
  expectAdminDocument,
  runChangelistAction,
} from './adminFixtures';

// The live Django-admin suite, sign-in boundary, theme, index pages and changelist actions. Split by admin area into admin*.spec.ts; each file runs
// its flows serially. @admin pins this live, DB-mutating admin suite to the chromium project
// (see playwright.config.ts) — firefox/webkit and the mobile devices skip it.
test.describe.serial('Django admin browser flows', {tag: '@admin'}, () => {
  test('requires authentication before showing the admin index', async ({page}) => {
    await page.goto(`${apiBaseUrl}/admin/`, {waitUntil: 'domcontentloaded'});

    await expect(page).toHaveURL(/\/admin\/login\//);
    await expect(page.getByLabel('Email')).toBeVisible();
  });

  test('rejects invalid admin credentials without entering the dashboard', async ({page}) => {
    await adminLogin(page, adminEmail, 'definitely-not-the-admin-password');

    await expect(page).toHaveURL(/\/admin\/login\//);
    await expect(page.locator('body')).toContainText(/Invalid email or password/i);
    await expect(page.locator('body')).not.toContainText(/Welcome to I2G Admin/i);
  });

  test('blocks a valid non-staff user at the admin password login boundary', async ({page}) => {
    await adminLogin(page, nonstaffEmail, adminPassword);

    await expect(page).toHaveURL(/\/admin\/login\//);
    await expect(page.locator('body')).toContainText(/Invalid email or password/i);
    await expect(page.locator('body')).not.toContainText(/Welcome to I2G Admin/i);
  });

  test('logs in through the deterministic password-mode admin login', async ({page}) => {
    await adminLogin(page);
    await expectLoggedInAdmin(page);
  });

  test('switches and persists the global admin theme without runtime errors', async ({page}) => {
    const themeRuntimeErrors = collectThemeRuntimeErrors(page);

    await page.goto(`${apiBaseUrl}/admin/login/?mode=password`, {waitUntil: 'domcontentloaded'});
    await page.evaluate(() => window.localStorage.removeItem('adminTheme'));
    await page.getByLabel('Email').fill(adminEmail);
    await page.getByLabel('Password').fill(adminPassword);
    await page.getByRole('button', {name: /sign in/i}).click();
    await expectLoggedInAdmin(page);

    const themeToggle = page.getByTestId('i2g-admin-theme-toggle');
    await expect(themeToggle).toBeVisible();
    await expect(themeToggle.locator('.i2g-admin-theme-toggle__icon')).not.toHaveText('');
    await expect(themeToggle.locator('.i2g-admin-theme-toggle__text')).toContainText(/Light|Dark|System/);

    await themeToggle.getByRole('button', {name: /switch admin theme/i}).click();
    const darkThemeChoice = themeToggle.locator('[data-admin-theme-choice="dark"]');
    await expect(darkThemeChoice).toBeVisible();
    await darkThemeChoice.click();
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);

    await page.reload({waitUntil: 'domcontentloaded'});
    await expect(page.locator('html')).toHaveClass(/(?:^|\s)dark(?:\s|$)/);
    expect(themeRuntimeErrors).toEqual([]);
  });

  test('loads the admin index and critical custom changelists', async ({page}) => {
    await adminLogin(page);
    await expectLoggedInAdmin(page);

    const adminPaths = [
      '/admin/authn/member/',
      '/admin/authn/contactemail/',
      '/admin/projects/project/',
      '/admin/projects/semester/',
      '/admin/cms/cmspage/',
      '/admin/event/event/',
      '/admin/mail/emailcampaign/',
      '/admin/system_intelligence/systemintelligenceconfig/',
    ];

    for (const path of adminPaths) {
      await expectAdminDocument(page, path);
    }
  });

  test('runs contact email bulk actions from the Unfold admin changelist', async ({page}) => {
    await adminLogin(page);
    await expectAdminDocument(page, '/admin/authn/contactemail/');

    await page.locator('input[name="q"]').fill(actionEmail);
    await page.locator('input[name="q"]').press('Enter');
    await expect(page.locator('body')).toContainText(actionEmail);

    await runChangelistAction(page, actionEmail, 'mark_verified');
    await expect(page.locator('body')).toContainText(/1 email\(s\) marked as verified/i);

    await page.locator('input[name="q"]').fill(actionEmail);
    await page.locator('input[name="q"]').press('Enter');
    await runChangelistAction(page, actionEmail, 'toggle_subscribe');
    await expect(page.locator('body')).toContainText(/Toggled subscription for 1 email\(s\)/i);
  });
});
