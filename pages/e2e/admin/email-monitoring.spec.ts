import {expect, test, type Page} from '@playwright/test';

// Mail → Delivery Operations → Email Monitoring: the one delivery page (it absorbed the Delivery Dashboard, now its
// Amazon SES tab). The seeded E2E database has no AWS, Graph or SMTP credentials, so nothing here reaches a provider:
// the Amazon SES tab shows its "not configured" notice and empty figures.
const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL ?? 'http://127.0.0.1:8000';
const adminEmail = process.env.ADMIN_E2E_EMAIL ?? 'admin-e2e@example.com';
const adminPassword = process.env.ADMIN_E2E_PASSWORD ?? 'admin-e2e-password';
const monitoring = '/admin/mail/email-monitoring/';

async function adminLogin(page: Page) {
  await page.goto(`${apiBaseUrl}/admin/login/?mode=password`, {waitUntil: 'domcontentloaded'});
  await page.getByLabel('Email').fill(adminEmail);
  await page.getByLabel('Password').fill(adminPassword);
  await page.getByRole('button', {name: /sign in/i}).click();
  await expect(page).toHaveURL(/\/admin\/?(?:\?.*)?$/);
}

const sections = (page: Page) => page.getByRole('navigation', {name: 'Email monitoring sections'});

async function expectCurrentTab(page: Page, name: string) {
  await expect(sections(page).locator('a[aria-current="page"]')).toHaveCount(1);
  await expect(sections(page).getByRole('link', {name, exact: true})).toHaveAttribute('aria-current', 'page');
}

// @admin pins this live admin suite to the chromium project (see playwright.config.ts), like admin.spec.ts.
test.describe.serial('Email Monitoring, the unified delivery page', {tag: '@admin'}, () => {
  let pageErrors: string[] = [];

  test.beforeEach(async ({page}) => {
    pageErrors = [];
    page.on('pageerror', (error) => pageErrors.push(error.message));
    await adminLogin(page);
  });

  test.afterEach(() => {
    expect(pageErrors).toEqual([]);
  });

  test('sends the old Delivery Dashboard address to the Amazon SES tab with its query string', async ({page}) => {
    const response = await page.goto(`${apiBaseUrl}/admin/mail/delivery-dashboard/?days=90`);

    expect(response?.status()).toBe(200);
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}ses/?days=90`);
    await expectCurrentTab(page, 'Amazon SES');
    await expect(page.locator('select[name="days"]')).toHaveValue('90');
    await expect(page.getByRole('heading', {name: /^Key figures/})).toBeVisible();
    await expect(page.getByText('SES attempts', {exact: true})).toBeVisible();
    await expect(page.getByRole('heading', {name: 'Daily SES attempts and errors'})).toBeVisible();
    await expect(page.getByRole('heading', {name: /^Suppressed recipients/})).toBeVisible();
    await expect(page.getByText('Bounce / Complaint')).toHaveCount(0);

    await page.locator('select[name="days"]').selectOption('365');
    await page.getByRole('button', {name: 'Apply'}).click();
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}ses/?days=365`);
    await expect(page.locator('select[name="days"]')).toHaveValue('365');
  });

  test('keeps the old JSON endpoint answering with the same payload as the new one', async ({page}) => {
    const old = await page.request.get(`${apiBaseUrl}/admin/mail/delivery-dashboard/data/?days=7`, {maxRedirects: 0});
    const current = await page.request.get(`${apiBaseUrl}${monitoring}ses/data/?days=7`, {maxRedirects: 0});

    expect(old.status()).toBe(200);
    expect(current.status()).toBe(200);
    const [oldBody, currentBody] = [await old.json(), await current.json()];
    expect(oldBody.window_days).toBe(7);
    expect(Object.keys(oldBody).sort()).toEqual(Object.keys(currentBody).sort());
    expect(oldBody.summary).toEqual(currentBody.summary);
  });

  test('switches between the five tabs and keeps the range on the telemetry ones', async ({page}) => {
    await page.goto(`${apiBaseUrl}${monitoring}?range=30d`);

    await expectCurrentTab(page, 'Overview');
    await expect(page.getByRole('heading', {name: 'Bounce processing'})).toBeVisible();
    await expect(page.locator('[data-monitor-kpis] .i2g-monitor-tile')).toHaveCount(6);
    await expect(page.getByRole('heading', {name: /^Recipients and API attempts/})).toBeVisible();
    await expect(page.getByRole('heading', {name: /^Trends/})).toBeVisible();
    await expect(page.getByRole('heading', {name: /^Broadcast campaigns/})).toBeVisible();

    await sections(page).getByRole('link', {name: 'Email log', exact: true}).click();
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}emails/?range=30d`);
    await expectCurrentTab(page, 'Email log');
    await expect(page.locator('select[name="range"]')).toHaveValue('30d');

    await sections(page).getByRole('link', {name: 'Bounce reports', exact: true}).click();
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}bounces/?range=30d`);
    await expectCurrentTab(page, 'Bounce reports');

    await sections(page).getByRole('link', {name: 'Bounced addresses', exact: true}).click();
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}addresses/`);
    await expectCurrentTab(page, 'Bounced addresses');
    await expect(page.getByRole('navigation', {name: 'Review status'})).toBeVisible();

    await sections(page).getByRole('link', {name: 'Amazon SES', exact: true}).click();
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}ses/`);
    await expectCurrentTab(page, 'Amazon SES');
    await expect(page.locator('select[name="days"]')).toHaveValue('183');

    await sections(page).getByRole('link', {name: 'Overview', exact: true}).click();
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}`);
    await expectCurrentTab(page, 'Overview');
  });

  test('shows the custom range dates only when a custom range is chosen', async ({page}) => {
    await page.goto(`${apiBaseUrl}${monitoring}`);
    const from = page.getByLabel('From', {exact: true});

    await expect(from).toBeHidden();
    await page.locator('select[name="range"]').selectOption('custom');
    await expect(from).toBeVisible();
    await from.fill('2026-01-01');
    await page.getByLabel('To', {exact: true}).fill('2026-01-31');
    await page.locator('select[name="provider"]').selectOption('ses');
    await page.getByRole('button', {name: 'Apply'}).click();

    await expect(page).toHaveURL(/range=custom&start=2026-01-01&end=2026-01-31&provider=ses/);
    await expect(page.getByRole('heading', {name: /^Key figures/})).toContainText('jan 01, 2026 – jan 31, 2026');
  });

  test('leads the sidebar and the Delivery Operations tabs to the merged page', async ({page}) => {
    await page.goto(`${apiBaseUrl}/admin/mail/settings/`);

    const sidebarLink = page.getByRole('link', {name: 'Delivery Operations', exact: true});
    await expect(sidebarLink).toHaveAttribute('href', monitoring);
    const tabs = page.locator('#tabs-items');
    await expect(tabs.getByRole('link', {name: 'Email Monitoring', exact: true})).toHaveAttribute('href', monitoring);
    await expect(tabs.getByRole('link', {name: 'Notification Delivery', exact: true})).toBeVisible();
    await expect(tabs.getByRole('link', {name: 'Delivery Rates', exact: true})).toBeVisible();
    await expect(tabs.getByRole('link', {name: 'Delivery Dashboard'})).toHaveCount(0);

    await tabs.getByRole('link', {name: 'Email Monitoring', exact: true}).click();
    await expect(page).toHaveURL(`${apiBaseUrl}${monitoring}`);
    await expect(tabs.getByRole('link', {name: 'Email Monitoring', exact: true})).toHaveClass(/active/);
    await expect(sidebarLink).toHaveAttribute('href', monitoring);
  });
});
